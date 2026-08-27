# Requirements Document

## Introduction

This feature adds a lightweight Python monitoring service that watches a configured Njuškalo real-estate search URL and sends Telegram notifications whenever new listings appear. It reuses the scraping layer from the [FraneCal/realestate-listings-pipeline](https://github.com/FraneCal/realestate-listings-pipeline) repository (Playwright + BeautifulSoup, `scrape_leaf_entries.py` and `parser_ultrafast.py`) and adds a polling loop, a JSON-based ID store, and a Telegram dispatch layer on top.

The service runs as a simple polling script — no web app, no database, no dashboard. Speed and simplicity are the primary design constraints.

## Glossary

- **Monitor**: The top-level Python service (`monitor.py`) that orchestrates the polling loop.
- **Scraper**: The reused Njuškalo HTML scraping component from `scrape_leaf_entries.py` in the upstream repo.
- **Parser**: The reused HTML-to-JSON parsing component from `parser_ultrafast.py` in the upstream repo.
- **Listing**: A single real-estate advertisement on Njuškalo.hr, identified by a unique numeric or alphanumeric Njuškalo listing ID extracted from the listing URL or page data.
- **Listing_ID**: The unique identifier for a Listing, derived from the Njuškalo ad URL or the `id` field in the parsed JSON output.
- **ID_Store**: The local file `previous_ids.json` that persists the set of Listing_IDs observed in the most recent completed run.
- **Notifier**: The component responsible for composing and sending Telegram messages.
- **Telegram_Bot**: The Telegram Bot API endpoint used to deliver notifications, identified by `TELEGRAM_BOT_TOKEN`.
- **Search_URL**: The fully-qualified Njuškalo search URL configured via the `NJUSKALO_SEARCH_URL` environment variable.
- **Check_Interval**: The delay in minutes between polling cycles, configured via `CHECK_INTERVAL_MINUTES`.
- **First_Run**: The first execution of the Monitor when the ID_Store file does not yet exist.
- **New_Listing**: A Listing whose Listing_ID is present in the current scrape result but absent from the ID_Store.

---

## Requirements

### Requirement 1: Configuration Loading

**User Story:** As an operator, I want all credentials and settings loaded from environment variables or a `.env` file, so that no secrets are ever hardcoded or committed to Git.

#### Acceptance Criteria

1. THE Monitor SHALL load `NJUSKALO_SEARCH_URL`, `CHECK_INTERVAL_MINUTES`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` from environment variables, treating whitespace-only values as absent, with `.env` file support via `python-dotenv`.
2. IF `NJUSKALO_SEARCH_URL` is absent or empty at startup, THEN THE Monitor SHALL log a descriptive error message and exit with a non-zero status code.
3. IF `TELEGRAM_BOT_TOKEN` is absent or empty at startup, THEN THE Monitor SHALL log a descriptive error message and exit with a non-zero status code.
4. IF `TELEGRAM_CHAT_ID` is absent or empty at startup, THEN THE Monitor SHALL log a descriptive error message and exit with a non-zero status code.
5. IF `CHECK_INTERVAL_MINUTES` is absent, THEN THE Monitor SHALL default to an interval of 5 minutes.
6. IF `CHECK_INTERVAL_MINUTES` is present but is not an integer in the range 1 to 1440 inclusive, THEN THE Monitor SHALL log a descriptive error message and exit with a non-zero status code.
7. THE project repository SHALL include a `.gitignore` file that lists `.env` as an excluded path, so that credential files are never tracked by Git.

---

### Requirement 2: Scraping Current Listings

**User Story:** As an operator, I want the service to retrieve the current listings from Njuškalo for a configured search URL, so that I always have an up-to-date picture of available properties.

#### Acceptance Criteria

1. WHEN a polling cycle begins, THE Monitor SHALL invoke the Scraper against `NJUSKALO_SEARCH_URL` to download the search-results HTML.
2. WHEN the Scraper completes successfully, THE Monitor SHALL invoke the Parser to extract structured listing data from the downloaded HTML.
3. THE Parser SHALL produce, for each Listing, at minimum: `listing_id`, `title`, `price`, `url`; and optionally `area`, `rooms`, `location` where available in the page HTML.
4. IF the Scraper raises an exception or returns a value that is `None`, an empty string, or HTML with no parseable listing structure, THEN THE Monitor SHALL log the error, skip the current polling cycle, and wait for the next Check_Interval before retrying.
5. IF the Parser raises an exception, THEN THE Monitor SHALL log the error, skip the current polling cycle, and wait for the next Check_Interval before retrying.
6. WHEN the Parser completes successfully but returns zero listings, THE Monitor SHALL log a warning indicating that no listings were found (which may indicate a site layout change), skip the current polling cycle, and wait for the next Check_Interval.
7. THE Scraper SHALL reuse the existing Playwright-based page-fetch logic from `scrape_leaf_entries.py` without rewriting it.

---

### Requirement 3: Listing ID Extraction

**User Story:** As a developer, I want each listing identified by a stable unique ID, so that the service can reliably detect new listings across runs.

#### Acceptance Criteria

1. THE Parser SHALL extract each Listing_ID from the final path segment of the Njuškalo listing URL (e.g., the segment after `/oglas/`), where the segment consists solely of alphanumeric characters (`[A-Za-z0-9]`) and is between 1 and 64 characters in length.
2. IF a Listing_ID cannot be extracted from a listing's URL, THEN THE Monitor SHALL log a warning for that listing and skip it without halting the cycle.
3. THE Monitor SHALL treat two listings as identical if and only if their Listing_IDs are equal under case-sensitive string comparison.

---

### Requirement 4: ID Store Persistence

**User Story:** As an operator, I want the service to remember which listings it has already seen, so that repeated runs do not re-notify for old listings.

#### Acceptance Criteria

1. THE Monitor SHALL read the ID_Store from `previous_ids.json` at the start of each polling cycle.
2. IF `previous_ids.json` does not exist, THEN THE Monitor SHALL treat the ID_Store as empty and proceed as a First_Run.
3. THE Monitor SHALL write the updated ID_Store to `previous_ids.json` in a manner that guarantees the file is not left in a corrupt or partial state if the process is interrupted during the write.
4. THE Monitor SHALL store Listing_IDs as a JSON array of strings in `previous_ids.json`.
5. IF `previous_ids.json` exists but contains invalid JSON, THEN THE Monitor SHALL log an error, treat the ID_Store as empty, overwrite the file with a valid empty array, and continue.
6. IF `previous_ids.json` exists but is unreadable due to file permissions or an I/O error, THEN THE Monitor SHALL log an error, treat the ID_Store as empty, and proceed as a First_Run.
7. WHEN the ID_Store exceeds 1,000 entries, THE Monitor SHALL retain only the 1,000 most recently added Listing_IDs when writing the updated ID_Store, to prevent unbounded file growth.

---

### Requirement 5: First-Run Baseline Behaviour

**User Story:** As an operator, I want the service to silently establish a baseline on its first run, so that I am not flooded with notifications for listings that were already on the market.

#### Acceptance Criteria

1. WHEN the ID_Store is empty and the scrape returns one or more listings, THE Monitor SHALL store those Listing_IDs in the ID_Store without sending any Telegram notifications.
2. WHEN the ID_Store is empty (First_Run), THE Monitor SHALL log a message stating that baseline IDs have been saved and that notifications will begin from the next run.
3. IF the ID_Store is empty and the scrape fails or returns zero listings, THEN THE Monitor SHALL leave the ID_Store empty, log a message indicating the baseline could not be established, and retry on the next polling cycle.
4. WHEN the ID_Store is empty and the scrape returns zero listings (genuinely empty market), THE Monitor SHALL write an explicit empty array `[]` to `previous_ids.json` to mark that the first run completed, so that subsequent runs proceed as normal polling cycles.
5. IF the ID_Store is non-empty, THEN THE Monitor SHALL treat the current run as a normal polling cycle subject to new-listing detection.

---

### Requirement 6: New Listing Detection

**User Story:** As an operator, I want to be alerted only to genuinely new listings that appeared since the last check, so that I can act quickly without being distracted by old listings.

#### Acceptance Criteria

1. WHEN a polling cycle runs and the ID_Store is non-empty, THE Monitor SHALL compute the set difference: `new_ids = current_ids − stored_ids`.
2. THE Monitor SHALL consider only Listing_IDs in `new_ids` as New_Listings for the purposes of notification.
3. WHEN no New_Listings are found, THE Monitor SHALL log a message indicating no new listings were detected and take no further action for that cycle, including skipping the ID_Store update.
4. WHEN one or more New_Listings are found, THE Monitor SHALL log the count of new listings detected.
5. WHEN one or more New_Listings are found in a cycle, THE Monitor SHALL update the ID_Store to the union of `stored_ids` and `current_ids`, so that IDs accumulate and are never re-notified.
6. WHEN a polling cycle runs and the ID_Store is empty (first run after baseline was established with zero listings), THE Monitor SHALL treat all `current_ids` as New_Listings and proceed with notification.
7. IF the current scrape returns zero listings, THE Monitor SHALL skip the set-difference computation, log a warning, and leave the ID_Store unchanged for that cycle.

---

### Requirement 7: Telegram Notification

**User Story:** As an operator, I want to receive a Telegram message for each new listing with key property details, so that I can quickly evaluate whether to act.

#### Acceptance Criteria

1. WHEN one or more New_Listings are detected, THE Notifier SHALL send a Telegram message to `TELEGRAM_CHAT_ID` using `TELEGRAM_BOT_TOKEN` via the Telegram Bot API `sendMessage` method.
2. IF multiple New_Listings are detected in a single cycle, THEN THE Notifier SHALL batch them into a single Telegram message (or the minimum number of messages required to stay within Telegram's 4096-character limit), with individual listing entries separated by a blank line, to avoid spam.
3. THE Notifier SHALL format each listing entry in the message using the following template, omitting any field whose value is `null`, an empty string, or absent from the listing data:

   ```
   🏠 NEW NJUŠKALO LISTING
   Title: [title]
   Price: [price]
   Area: [area]
   Rooms: [rooms]
   Location: [location]
   [listing URL]
   Detected: [ISO-8601 timestamp in local time]
   ```

4. THE Notifier SHALL send listing URLs as plain clickable links (not markdown-escaped) using `parse_mode=None` or equivalent, so that Telegram renders them as hyperlinks.
5. IF the Telegram API returns a non-2xx HTTP status code, THEN THE Notifier SHALL log the error with the HTTP status code and response body, retry the send once after a 5-second delay, and log a final failure if the retry also fails.
6. IF the Telegram API is unreachable due to a network error, THEN THE Notifier SHALL log the error and continue to the next polling cycle without crashing.

---

### Requirement 8: Polling Loop

**User Story:** As an operator, I want the service to check for new listings automatically at a regular interval, so that I am notified promptly without manual intervention.

#### Acceptance Criteria

1. THE Monitor SHALL repeat the scrape-detect-notify-persist cycle indefinitely until the process is terminated.
2. WHEN a cycle completes, THE Monitor SHALL wait `CHECK_INTERVAL_MINUTES` minutes (an integer in the range 1 to 1440 inclusive) before beginning the next cycle.
3. WHEN a `KeyboardInterrupt` or `SIGTERM` signal is received, THE Monitor SHALL log a shutdown message, exit with status code 0, and leave `previous_ids.json` in its last valid persisted state.
4. WHEN a polling cycle completes successfully, THE Monitor SHALL log the cycle start time, end time, and count of new listings found.
5. IF logging the cycle start time fails, THE Monitor SHALL still log the end time and count of new listings found.
6. IF an unhandled exception occurs within a polling cycle, THE Monitor SHALL log the exception type and message, and continue to the next polling cycle without terminating.

---

### Requirement 9: Logging

**User Story:** As an operator, I want structured log output for every run, so that I can diagnose problems and verify the service is working correctly.

#### Acceptance Criteria

1. THE Monitor SHALL emit log messages to stdout using Python's `logging` module at `INFO` level by default; each log line SHALL include at minimum: a UTC timestamp, severity level, and message text.
2. WHEN an error or exception occurs, THE Monitor SHALL emit an `ERROR`-level log message regardless of the configured log level, including the exception type and message.
3. THE Monitor SHALL format the UTC timestamp in each log line as ISO 8601 (e.g., `2024-01-15T10:30:00Z`).
4. IF the `LOG_LEVEL` environment variable is set to `DEBUG`, THEN THE Monitor SHALL emit additional diagnostic messages including the number of listings scraped and the number of IDs loaded from the ID_Store.
5. IF the `LOG_LEVEL` environment variable is set to a value other than `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`, THEN THE Monitor SHALL log a warning and fall back to `INFO` level.

---

### Requirement 10: Repository Hygiene

**User Story:** As a developer, I want the project to follow standard Python repository conventions so that it is easy to set up and safe to commit.

#### Acceptance Criteria

1. THE project SHALL include a `requirements.txt` listing all direct Python dependencies with exact pinned versions in `==` format (e.g., `python-dotenv==1.0.1`).
2. THE project SHALL include a `.gitignore` that excludes `.env`, `previous_ids.json`, `backend/`, `*.log`, and standard Python build artifacts (`__pycache__`, `*.pyc`, `.venv`).
3. THE project SHALL include a `README.md` with the following sections: Setup (installation steps), Configuration (all required and optional environment variables), Telegram Setup (how to obtain a Bot token and Chat ID), and Running the Service (command to start the monitor).
4. THE project SHALL include a `.env.example` file that lists all required environment variable names (`NJUSKALO_SEARCH_URL`, `CHECK_INTERVAL_MINUTES`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) and optional variable names (`LOG_LEVEL`) with clearly marked placeholder values (e.g., `your_bot_token_here`) and no real credentials.
