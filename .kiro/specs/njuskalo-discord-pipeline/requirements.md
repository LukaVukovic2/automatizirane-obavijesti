# Requirements Document

## Introduction

This feature extends the existing Njuškalo Discord Notifier from a single-search, single-channel monitor into a multi-searcher pipeline. Instead of one hardcoded Njuškalo search URL sending notifications to one Discord channel, operators configure any number of independent **Searchers** in a `config.json` file. Each Searcher has its own Njuškalo search URL and its own Discord webhook, so different property searches (e.g., apartments vs. houses, different cities, different price ranges) can fan out to different Discord channels with zero Python changes.

The implementation reuses all existing scraping, parsing, detection, and notification infrastructure. Only the coordination layer (config loading, the monitoring loop, and state management) changes to become searcher-aware.

---

## Glossary

- **Monitor**: The top-level Python service (`listing_monitor/monitor.py`) that orchestrates the polling loop across all Searchers.
- **Searcher**: A single configured Njuškalo search, identified by a unique string ID. Each Searcher encapsulates a `search_url` and a reference to a Discord webhook environment variable.
- **Searcher_ID**: The unique string identifier for a Searcher, as declared in `config.json`. Used as the key in `previous_ids.json`.
- **Search_URL**: The fully-qualified Njuškalo search URL associated with a Searcher.
- **Discord_Webhook**: An incoming Discord webhook URL used to post new-listing notifications. The actual URL is stored in `.env`; `config.json` holds only the environment variable name.
- **Config_File**: The `config.json` file at the project root that defines the global polling interval and the list of Searchers.
- **Scraper**: The existing Playwright-based page-fetch component (`scraper_adapter.py` / `fetch_html`) reused without modification.
- **Parser**: The existing HTML-to-Listing parsing component (`parser_adapter.py` / `parse_listings`) reused without modification.
- **Listing**: A single real-estate advertisement on Njuškalo.hr with fields `listing_id`, `title`, `price`, `url`, and optionally `area`, `rooms`, `location`.
- **Listing_ID**: The unique identifier for a Listing extracted from the Njuškalo ad URL (see existing `_extract_listing_id` logic).
- **ID_Store**: The `previous_ids.json` file that persists seen Listing_IDs, keyed by Searcher_ID.
- **New_Listing**: A Listing whose Listing_ID is present in a scrape result but absent from the ID_Store entry for that Searcher.
- **Check_Interval**: The global delay in minutes between full polling cycles, sourced from `config.json`.
- **First_Run**: The state of a Searcher when its Searcher_ID has no entry in the ID_Store.
- **Polling_Cycle**: One iteration of the loop that runs `check_searcher` for every configured Searcher.
- **Embed**: A Discord message embed object containing structured fields (title, price, area, rooms, location) rendered as a rich card.

---

## Requirements

### Requirement 1: Configuration File

**User Story:** As an operator, I want to declare all my Njuškalo searches in a single `config.json` file so that I can add, remove, or change searches without touching any Python code.

#### Acceptance Criteria

1. THE Config_Loader SHALL read `config.json` from the project root directory at startup.
2. THE `config.json` file SHALL contain a top-level integer field `check_interval_minutes` and a top-level array field `searchers`.
3. WHEN `config.json` is absent or cannot be read, THE Config_Loader SHALL log a descriptive error and exit with a non-zero status code.
4. WHEN `config.json` contains invalid JSON syntax, THE Config_Loader SHALL log a descriptive error and exit with a non-zero status code.
5. IF `check_interval_minutes` is absent from `config.json`, THEN THE Config_Loader SHALL default to an interval of 5 minutes.
6. IF `check_interval_minutes` is present but is not an integer in the range 1 to 1440 inclusive, THEN THE Config_Loader SHALL log a descriptive error and exit with a non-zero status code.
7. THE `searchers` array SHALL contain one or more Searcher objects; IF the array is empty or absent, THEN THE Config_Loader SHALL log a descriptive error and exit with a non-zero status code.
8. EACH Searcher object in `config.json` SHALL have the following fields: `id` (non-empty string), `name` (non-empty string), `search_url` (non-empty string), `discord_webhook_env` (non-empty string naming an environment variable).
9. IF any Searcher object is missing a required field or contains an empty value for a required field, THEN THE Config_Loader SHALL log a descriptive error identifying the offending Searcher and exit with a non-zero status code.
10. IF two or more Searcher objects share the same `id` value, THEN THE Config_Loader SHALL log a descriptive error and exit with a non-zero status code.
11. WHEN `discord_webhook_env` names an environment variable that is absent or empty at startup, THE Config_Loader SHALL log a descriptive error identifying the Searcher and exit with a non-zero status code before constructing any Searcher objects.
12. THE Monitor SHALL support adding a new Searcher by adding one JSON object to the `searchers` array in `config.json` with no Python changes required.

---

### Requirement 2: Searcher Data Model

**User Story:** As a developer, I want each Searcher to be represented as a structured object so that the monitoring loop can treat all searches generically without per-type branching.

#### Acceptance Criteria

1. THE Config_Loader SHALL produce a `Searcher` frozen dataclass for each entry in the `searchers` array, containing: `id: str`, `name: str`, `search_url: str`, `webhook_url: str` (the resolved environment variable value).
2. THE Config_Loader SHALL resolve `discord_webhook_env` to its runtime value by reading the named environment variable (with `.env` file support via `python-dotenv`) and store the result in `webhook_url`.
3. THE Monitor SHALL invoke `check_searcher(searcher)` with a `Searcher` object for every configured Searcher in each Polling_Cycle; THE Monitor SHALL NOT define or call per-type functions such as `check_apartments()` or `check_houses()`.

---

### Requirement 3: Per-Searcher Monitoring Cycle

**User Story:** As an operator, I want each configured Searcher to independently scrape its search URL, detect new listings, and notify its Discord channel, so that different searches do not interfere with each other.

#### Acceptance Criteria

1. WHEN `check_searcher(searcher)` is called, THE Monitor SHALL invoke the existing `fetch_html(searcher.search_url)` function to download the search-results HTML.
2. WHEN `fetch_html` completes successfully, THE Monitor SHALL invoke the existing `parse_listings(html)` function to extract structured listing data.
3. WHEN one or more New_Listings are detected for a Searcher, THE Monitor SHALL invoke `send_discord(searcher, listing)` for each New_Listing and only update the ID_Store entry for that Searcher after the Discord call succeeds.
4. IF `parse_listings` raises a `ParserError`, THEN THE Monitor SHALL log the error including the Searcher name, skip that Searcher for the current cycle, and continue with the remaining Searchers regardless of whether the log write succeeds.
5. IF `parse_listings` returns zero listings, THEN THE Monitor SHALL log a warning including the Searcher name, skip the ID_Store update for that Searcher, and continue with the remaining Searchers regardless of whether the log write succeeds.
6. IF `fetch_html` raises a `ScraperError`, THEN THE Monitor SHALL log the error including the Searcher name, skip that Searcher for the current cycle, and continue with the remaining Searchers regardless of whether the log write succeeds.
7. IF an unhandled exception occurs inside `check_searcher`, THEN THE Monitor SHALL log the exception type, message, and Searcher name, and continue processing the remaining Searchers in the current cycle.
8. THE Monitor SHALL run `check_searcher` for each Searcher sequentially in the order they appear in `config.json`.

---

### Requirement 4: New Listing Detection

**User Story:** As an operator, I want each Searcher to alert me only to listings that appeared since the last check for that search, so that I am not re-notified about listings I have already seen.

#### Acceptance Criteria

1. WHEN `check_searcher` runs for a Searcher whose Searcher_ID is present in the ID_Store, THE Monitor SHALL compute the set difference: `new_listings = [l for l in current_listings if l.id not in previous_ids]`.
2. WHEN `check_searcher` runs for a Searcher whose Searcher_ID has no entry in the ID_Store (First_Run), THE Monitor SHALL save the current Listing_IDs as the baseline for that Searcher, NOT execute any notification-sending code, and log a message stating baseline IDs have been saved.
3. WHEN no New_Listings are found for a Searcher, THE Monitor SHALL log a message indicating no new listings were detected for that Searcher and skip the ID_Store update.
4. WHEN one or more New_Listings are found for a Searcher, THE Monitor SHALL log the Searcher name and the count of new listings detected.
5. THE Monitor SHALL treat two Listing_IDs as identical if and only if they are equal under case-sensitive string comparison (reusing the existing `detect_new` function unchanged).

---

### Requirement 5: ID Store — Per-Searcher State

**User Story:** As an operator, I want each Searcher to maintain independent state so that one Searcher's failures or resets do not affect the others.

#### Acceptance Criteria

1. THE ID_Store SHALL be persisted in a single `previous_ids.json` file, structured as a JSON object keyed by Searcher_ID, where each value is an array of Listing_ID strings (e.g., `{"apartments": ["id1", "id2"], "houses": ["id3"]}`).
2. WHEN the ID_Store is read at cycle start, THE Monitor SHALL retrieve only the array for the active Searcher_ID; absent keys SHALL be treated as an empty array (First_Run for that Searcher).
3. THE Monitor SHALL write updates to the ID_Store atomically only when an update is being performed: write to a temporary file, call `fsync`, then use `os.replace()` to swap it into place, so the file is never left in a corrupt or partial state.
4. WHEN a Searcher's ID_Store entry exceeds 1,000 Listing_IDs, THE Monitor SHALL retain only the 1,000 most recently added Listing_IDs for that Searcher when writing the updated entry.
5. IF `previous_ids.json` does not exist, THE Monitor SHALL treat all Searchers as First_Run.
6. IF `previous_ids.json` contains invalid JSON, THE Monitor SHALL log an error, treat all Searchers as First_Run, overwrite the file with a valid empty object `{}`, and continue.
7. IF `previous_ids.json` is unreadable due to an I/O error, THE Monitor SHALL log an error and treat all Searchers as First_Run for the current cycle.

---

### Requirement 6: Discord Notification — Embeds

**User Story:** As an operator, I want new-listing notifications posted to Discord as rich embeds so that I can quickly scan title, price, size, and location at a glance.

#### Acceptance Criteria

1. WHEN a New_Listing is found, THE Notifier SHALL post a Discord message to the Searcher's `webhook_url` containing a single embed object with the following fields populated from the listing where the value is non-empty: `title` (embed title linking to the listing URL), `price` (embed field), `area` (embed field, omitted if absent), `rooms` (embed field, omitted if absent), `location` (embed field, omitted if absent).
2. THE Notifier SHALL send one Discord embed per New_Listing (one HTTP POST per listing) rather than batching multiple listings into one message.
3. IF the Discord webhook returns a non-2xx HTTP status code, THEN THE Notifier SHALL log the error with the HTTP status code and response body and return a failure indicator without updating the ID_Store for that listing.
4. IF the Discord webhook is unreachable due to a network error, THEN THE Notifier SHALL log the error and return a failure indicator without updating the ID_Store for that listing.
5. WHEN the Discord call fails (non-2xx or network error), THE Monitor SHALL NOT mark the corresponding Listing_ID as processed in the ID_Store, so that delivery is retried on the next Polling_Cycle.
6. WHEN the Discord call succeeds (2xx response), THE Monitor SHALL mark the Listing_ID as processed in the ID_Store.

---

### Requirement 7: Polling Loop

**User Story:** As an operator, I want the service to automatically check all configured searches at a regular interval so that I am notified promptly without manual intervention.

#### Acceptance Criteria

1. THE Monitor SHALL repeat the Polling_Cycle indefinitely: for each Searcher, call `check_searcher(searcher)`; wait `check_interval_minutes` minutes; repeat.
2. WHEN a Polling_Cycle completes, THE Monitor SHALL wait the configured `check_interval_minutes` before beginning the next Polling_Cycle; THE Monitor SHALL NOT start a new cycle while a previous one is still running (no overlapping cycles).
3. WHEN a `KeyboardInterrupt` or `SIGTERM` signal is received, THE Monitor SHALL attempt to log a shutdown message, exit with status code 0, and leave `previous_ids.json` in its last valid persisted state, continuing through each shutdown step even if a prior step fails.
4. IF an unhandled exception occurs outside of a `check_searcher` call but inside the polling loop body, THE Monitor SHALL log the exception type and message and continue to the next Polling_Cycle without terminating.

---

### Requirement 8: Module Structure

**User Story:** As a developer, I want the new multi-searcher code organised in a `listing_monitor` package so that the existing root-level scripts remain intact and the new components are clearly separated.

#### Acceptance Criteria

1. THE project SHALL contain a `listing_monitor/` package directory with an `__init__.py` and the following modules: `config.py` (config loading and `Searcher` dataclass), `monitor.py` (polling loop and `check_searcher`), `state.py` (ID_Store read/write), `discord.py` (Discord embed notifications).
2. THE `listing_monitor/monitor.py` module SHALL serve as the entry point invoked via `python -m listing_monitor.monitor` or `python listing_monitor/monitor.py`.
3. THE existing root-level modules (`scraper_adapter.py`, `parser_adapter.py`, `detector.py`, `id_store.py`, `config.py`, `monitor.py`, `notifier.py`) SHALL remain present and unmodified so that the existing single-searcher pipeline continues to function.
4. THE `listing_monitor` package modules SHALL import `fetch_html` from the root-level `scraper_adapter` module and `parse_listings` from the root-level `parser_adapter` module without copying or duplicating their implementations.
5. THE `listing_monitor` package modules SHALL import `detect_new` from the root-level `detector` module without duplicating its implementation.

---

### Requirement 9: Environment and Repository Hygiene

**User Story:** As a developer, I want the project to follow standard conventions for secrets and documentation so that it is easy to set up and safe to commit.

#### Acceptance Criteria

1. THE project SHALL include a `config.json` at the project root with a complete, commented example showing at least one Searcher entry.
2. THE project SHALL include an updated `.env.example` that documents the Discord webhook environment variable naming convention (e.g., `DISCORD_WEBHOOK_APARTMENTS=https://discord.com/api/webhooks/...`) with placeholder values and no real credentials.
3. THE `.gitignore` SHALL list `.env` and `previous_ids.json` as excluded paths so that credentials and state files are never tracked by Git.
4. THE `README.md` SHALL include a section titled "Adding a New Searcher" explaining the four steps: (1) create a Discord webhook, (2) add the webhook URL to `.env`, (3) add a new Searcher object to `config.json`, (4) restart the monitor.
5. THE `requirements.txt` SHALL list all direct Python dependencies with exact pinned versions in `==` format.

---

### Requirement 10: Testing

**User Story:** As a developer, I want the key behaviours covered by automated tests so that regressions are caught before deployment.

#### Acceptance Criteria

1. THE test suite SHALL include a test that verifies new-listing detection: given a list of current listings and a non-empty set of stored IDs, `check_searcher` (or the detection logic it uses) returns only the listings whose IDs are not in the stored set.
2. THE test suite SHALL include a test that verifies no-new-listings behaviour: when all current listing IDs are already in the stored set, no Discord call is made.
3. THE test suite SHALL include a test that verifies First_Run baseline behaviour: when a Searcher has no entry in the ID_Store, no Discord call is made and the current IDs are saved.
4. THE test suite SHALL include a test that verifies multi-searcher isolation: when two Searchers are configured and one fails (raises `ScraperError`), the other Searcher's cycle completes normally.
5. THE test suite SHALL include a test that verifies Discord-failure safety: when the Discord webhook returns a non-2xx response, the failing listing's ID is NOT written to the ID_Store.
6. THE test suite SHALL include a test that verifies ID_Store persistence: after a successful cycle, the ID_Store contains the union of previously stored IDs and all current listing IDs for that Searcher.
