
# Implementation Plan: Njuškalo Telegram Notifier

## Overview

Implement a lightweight Python polling service that watches a Njuškalo real-estate search URL and sends Telegram notifications for new listings. The implementation is structured in dependency order: repository scaffolding first, then individual modules (`config`, `id_store`, `parser_adapter`, `detector`, `scraper_adapter`, `notifier`), logging setup, the main `monitor.py` entry point, and finally smoke tests. Each module is immediately followed by its tests so bugs are caught early.

## Tasks

- [x] 1. Project scaffold and repository hygiene
  - [x] 1.1 Create `.gitignore` excluding `.env`, `previous_ids.json`, `backend/`, `*.log`, `__pycache__`, `*.pyc`, `.venv`
  - [x] 1.2 Create `.env.example` with all required and optional variable names and placeholder values
  - [x] 1.3 Create `requirements.txt` with pinned `==` versions for all direct dependencies (`python-dotenv`, `requests`, `hypothesis`, `pytest`, `playwright`, `beautifulsoup4`)
  - [x] 1.4 Create `README.md` with Setup, Configuration, Telegram Setup, and Running the Service sections
  - [x] 1.5 Create `tests/` directory with empty `__init__.py`
  - **Requirements: 10.1, 10.2, 10.3, 10.4, 1.7**

- [x] 2. `config.py` — Configuration loader
  - [x] 2.1 Implement `Config` frozen dataclass with fields: `search_url`, `bot_token`, `chat_id`, `check_interval_minutes`, `log_level`
  - [x] 2.2 Implement `ConfigError` exception class
  - [x] 2.3 Implement `load_config()`: load `.env` via `python-dotenv`, strip values, treat whitespace-only as absent, validate required vars, parse `CHECK_INTERVAL_MINUTES` with range check, validate/fallback `LOG_LEVEL`
  - **Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

- [x] 3. `config.py` — Unit and property-based tests
  - [x] 3.1 Write property test (P1): whitespace-only env var values are treated as absent
    - **Validates: Requirements 1.1**
  - [x] 3.2 Write property test (P2): `CHECK_INTERVAL_MINUTES` boundary enforcement — reject values outside [1, 1440], accept values inside
    - **Validates: Requirements 1.6**
  - [x] 3.3 Write example-based unit tests: missing required vars each cause `ConfigError`; default interval is 5; invalid `LOG_LEVEL` falls back to `INFO`
  - **Test file: `tests/test_config.py`**

- [x] 4. `id_store.py` — ID store persistence
  - [x] 4.1 Define `ID_STORE_PATH = "previous_ids.json"` and `MAX_STORE_SIZE = 1000`
  - [x] 4.2 Implement `read_ids() -> set[str]`: return empty set if file absent (`FileNotFoundError`), unreadable (`OSError`), or invalid JSON (`json.JSONDecodeError`); log appropriate error in each case; overwrite with `[]` on invalid JSON
  - [x] 4.3 Implement `write_ids(ids: set[str], recently_added: list[str]) -> None`: if `len(ids) > MAX_STORE_SIZE` retain only the `MAX_STORE_SIZE` most recently added IDs; write to temp file then `os.replace()` for atomicity
  - **Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

- [x] 5. `id_store.py` — Unit and property-based tests
  - [x] 5.1 Write property test (P5): ID store round-trip integrity — write then read returns equal set (up to 1000-entry cap); persisted file is always valid JSON
    - **Validates: Requirements 4.3, 4.4**
  - [x] 5.2 Write property test (P6): ID store size cap — stores with > 1000 entries are truncated to the 1000 most recently added IDs
    - **Validates: Requirements 4.7**
  - [x] 5.3 Write property test (P8): ID store accumulates on new-listing cycle — after a cycle, persisted store equals `stored_ids ∪ current_ids`
    - **Validates: Requirements 6.5**
  - [x] 5.4 Write example-based unit tests: absent file → empty set; invalid JSON → empty set + file overwritten with `[]`; unreadable file → empty set; atomic write leaves original untouched on failure
  - **Test file: `tests/test_id_store.py`**

- [x] 6. `parser_adapter.py` — Parser adapter
  - [x] 6.1 Define `Listing` TypedDict with required fields (`listing_id`, `title`, `price`, `url`) and optional fields (`area`, `rooms`, `location`)
  - [x] 6.2 Implement `_extract_listing_id(url: str) -> str | None` using the regex `r'/oglas/([A-Za-z0-9]{1,64})(?:[/?#]|$)'`
  - [x] 6.3 Implement `ParserError` exception class
  - [x] 6.4 Implement `parse_listings(html: str) -> list[Listing]`: call upstream `parser_ultrafast`, convert output to `Listing` dicts, log and skip entries where `listing_id` cannot be extracted, raise `ParserError` on upstream exception
  - **Requirements: 2.2, 2.3, 3.1, 3.2**

- [x] 7. `parser_adapter.py` — Unit and property-based tests
  - [x] 7.1 Write property test (P3): listing ID extraction correctness — conforming `/oglas/<id>` segments are extracted exactly; non-conforming URLs return `None`
    - **Validates: Requirements 3.1, 3.2**
  - [x] 7.2 Write example-based unit tests: URL with valid ID segment; URL without `/oglas/`; URL with ID longer than 64 chars; URL with non-alphanumeric characters in segment
  - **Test file: `tests/test_parser_adapter.py`**

- [x] 8. `detector.py` — New listing detector
  - [x] 8.1 Implement `detect_new(current: list[Listing], stored_ids: set[str]) -> list[Listing]`: return listings whose `listing_id` is in `current` but not in `stored_ids`; comparison is case-sensitive string equality
  - **Requirements: 6.1, 6.2, 3.3**

- [x] 9. `detector.py` — Unit and property-based tests
  - [x] 9.1 Write property test (P4): case-sensitive ID equality — two strings differing only in case are treated as distinct IDs
    - **Validates: Requirements 3.3**
  - [x] 9.2 Write property test (P7): new listing detection is exact set difference — `detect_new` returns exactly `current_ids − stored_ids`
    - **Validates: Requirements 6.1, 6.2**
  - **Test file: `tests/test_detector.py`**

- [x] 10. `scraper_adapter.py` — Scraper adapter
  - [x] 10.1 Implement `ScraperError` exception class
  - [x] 10.2 Implement `fetch_html(search_url: str) -> str`: import and call the upstream `scrape_leaf_entries` function; raise `ScraperError` on any exception from the upstream module
  - **Requirements: 2.1, 2.7**

- [x] 11. `notifier.py` — Telegram notifier
  - [x] 11.1 Define constants: `TELEGRAM_API_BASE`, `MAX_MESSAGE_LENGTH = 4096`, `RETRY_DELAY_SECONDS = 5`
  - [x] 11.2 Implement `_format_listing(listing: Listing) -> str`: apply the message template from Requirement 7.3; omit label lines for fields that are `None`, `""`, or absent; include ISO-8601 local timestamp in the `Detected` field
  - [x] 11.3 Implement `_batch_listings(listings: list[Listing]) -> list[str]`: concatenate formatted entries separated by a blank line; split into chunks of at most 4096 characters on listing boundaries (never mid-listing)
  - [x] 11.4 Implement `send_new_listings(listings: list[Listing], bot_token: str, chat_id: str) -> None`: call `_batch_listings`, send each chunk via `requests.post` to `sendMessage` with `parse_mode` omitted; on non-2xx response retry once after `RETRY_DELAY_SECONDS`; on `requests.RequestException` log and continue
  - **Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6**

- [x] 12. `notifier.py` — Unit and property-based tests
  - [x] 12.1 Write property test (P9): message batches respect the 4096-character limit — no batch exceeds 4096 chars; no listing is split across batches
    - **Validates: Requirements 7.2**
  - [x] 12.2 Write property test (P10): message format omits absent fields — formatted string contains all present required fields and does not contain label lines for absent/null optional fields
    - **Validates: Requirements 7.3**
  - [x] 12.3 Write example-based unit tests: non-2xx response → one retry after 5 s; two consecutive non-2xx → final failure logged; network error → no crash; `parse_mode` absent from request payload
  - **Test file: `tests/test_notifier.py`**

- [x] 13. Logging setup
  - [x] 13.1 Implement `setup_logging(log_level: str) -> None` (in `monitor.py` or a shared `logging_setup.py`): configure the root logger to emit to stdout with an ISO-8601 UTC formatter (`%(asctime)sZ %(levelname)s %(message)s`), set the level from `Config.log_level`
  - **Requirements: 9.1, 9.2, 9.3, 9.4, 9.5**

- [x] 14. Logging — Unit and property-based tests
  - [x] 14.1 Write property test (P11): log lines always contain UTC ISO-8601 timestamp, severity, and message — for any log record at any level with arbitrary message text
    - **Validates: Requirements 9.1, 9.3**
  - [x] 14.2 Write example-based unit tests: `DEBUG` level emits additional diagnostic messages; invalid `LOG_LEVEL` emits a warning and falls back to `INFO`
  - **Test file: `tests/test_logging_setup.py`**

- [x] 15. `monitor.py` — Main polling loop
  - [x] 15.1 Implement `run_cycle(config: Config) -> int`: read ID store → `fetch_html` → `parse_listings` → handle scraper/parser errors (log + return 0) → handle zero listings (log warning + return 0) → `detect_new` → first-run baseline path (save IDs, no notify, return 0) → notify → write ID store → return new count; log cycle start time, end time, and new listing count
  - [x] 15.2 Implement `main()`: call `load_config()`, exit on `ConfigError`; call `setup_logging`; register `SIGTERM` handler; run polling loop with `time.sleep(config.check_interval_minutes * 60)` between cycles; catch `KeyboardInterrupt` for clean shutdown (exit 0); catch `Exception` inside loop body to log and continue
  - **Requirements: 2.4, 2.5, 2.6, 4.1, 4.2, 5.1, 5.2, 5.3, 5.4, 6.3, 6.4, 6.5, 6.6, 6.7, 7.1, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**

- [x] 16. `monitor.py` — Unit tests
  - [x] 16.1 Write example-based unit tests: scraper exception → cycle skipped (returns 0); parser returns `[]` → warning logged, no store write; first-run with listings → IDs saved, no Telegram call, baseline message logged; first-run with zero listings → empty array written, retry message logged; `KeyboardInterrupt` → `sys.exit(0)`; unhandled exception in cycle body → loop continues
  - **Test file: `tests/test_monitor.py`**

- [x] 17. Smoke tests
  - [x] 17.1 Write static assertions: `.gitignore` contains `.env` and `previous_ids.json`; `.env.example` lists all four required variable names; `requirements.txt` uses `==` pinned versions for all direct dependencies
  - **Test file: `tests/test_smoke.py`**
  - **Requirements: 10.1, 10.2, 10.4**

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"] },
    { "wave": 2, "tasks": ["2"] },
    { "wave": 3, "tasks": ["3"] },
    { "wave": 4, "tasks": ["4"] },
    { "wave": 5, "tasks": ["5"] },
    { "wave": 6, "tasks": ["6"] },
    { "wave": 7, "tasks": ["7"] },
    { "wave": 8, "tasks": ["8"] },
    { "wave": 9, "tasks": ["9"] },
    { "wave": 10, "tasks": ["10"] },
    { "wave": 11, "tasks": ["11"] },
    { "wave": 12, "tasks": ["12"] },
    { "wave": 13, "tasks": ["13"] },
    { "wave": 14, "tasks": ["14"] },
    { "wave": 15, "tasks": ["15"] },
    { "wave": 16, "tasks": ["16"] },
    { "wave": 17, "tasks": ["17"] }
  ]
}
```

## Notes

- The scraper adapter (`scraper_adapter.py`, task 10) wraps the upstream `scrape_leaf_entries.py` from the `FraneCal/realestate-listings-pipeline` repo without modification. That upstream file must be present in the project before the scraper adapter can be tested end-to-end; unit tests for the adapter mock the upstream call.
- The `parser_adapter.py` similarly wraps `parser_ultrafast.py` from the upstream repo. Mock the upstream call in unit tests.
- All property-based tests use **Hypothesis**. Each test is tagged with a comment in the form `# Feature: njuskalo-telegram-notifier, Property N: <description>`.
- The `write_ids` / `os.replace()` atomic write is best-effort on Windows (not guaranteed atomic), which is acceptable for this use case.
- No integration tests against the live Njuškalo site or the real Telegram API are included; those are run manually by the operator before deployment.
