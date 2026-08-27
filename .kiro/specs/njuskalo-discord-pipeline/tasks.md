# Implementation Plan: njuskalo-discord-pipeline

## Overview

Build the `listing_monitor/` package on top of the existing root-level modules. Work proceeds in dependency order: data models and config loading first, then state management, then Discord notification, then the polling loop, and finally repository hygiene and tests. The existing root-level pipeline is never modified.

## Tasks

- [x] 1. Create the `listing_monitor` package skeleton and data models
  - Create `listing_monitor/__init__.py` (empty)
  - Define the `Searcher` frozen dataclass (`id`, `name`, `search_url`, `webhook_url`) in `listing_monitor/config.py`
  - Define the `PipelineConfig` frozen dataclass (`check_interval_minutes`, `searchers: tuple[Searcher, ...]`) in `listing_monitor/config.py`
  - Define the `ConfigError` exception class in `listing_monitor/config.py`
  - _Requirements: 1.1, 2.1, 8.1_

- [x] 2. Implement `load_config()` in `listing_monitor/config.py`
  - [x] 2.1 Implement file reading and JSON parsing with error handling
    - Call `load_dotenv()` before reading the file
    - Handle `FileNotFoundError`, `OSError`, and `json.JSONDecodeError` — raise `ConfigError` with descriptive messages
    - _Requirements: 1.1, 1.3, 1.4_

  - [x] 2.2 Implement `check_interval_minutes` validation
    - Default to 5 when the key is absent
    - Raise `ConfigError` when the value is present but not an integer in [1, 1440]
    - _Requirements: 1.5, 1.6_

  - [x] 2.3 Implement `searchers` array validation
    - Raise `ConfigError` when `searchers` is absent or empty
    - For each entry: validate all four required fields (`id`, `name`, `search_url`, `discord_webhook_env`) are present and non-empty strings, raise identifying the offending entry
    - Raise `ConfigError` on duplicate `id` values
    - _Requirements: 1.7, 1.8, 1.9, 1.10_

  - [x] 2.4 Implement webhook env-var resolution
    - For each Searcher entry read `os.environ[discord_webhook_env]`; raise `ConfigError` identifying the Searcher if the variable is absent or empty
    - Construct and return the `PipelineConfig` with all resolved `Searcher` objects
    - _Requirements: 1.11, 2.1, 2.2_

  - [-]* 2.5 Write property test for `load_config` — Property 1: Invalid JSON always rejected
    - **Property 1: Invalid JSON config always rejected**
    - **Validates: Requirements 1.4**

  - [-]* 2.6 Write property test for `load_config` — Property 2: Out-of-range interval always rejected
    - **Property 2: Out-of-range or non-integer check_interval_minutes always rejected**
    - **Validates: Requirements 1.6**

  - [-]* 2.7 Write property test for `load_config` — Property 3: Missing/empty Searcher field always rejected
    - **Property 3: Missing or empty required Searcher fields always rejected**
    - **Validates: Requirements 1.8, 1.9**

  - [-]* 2.8 Write property test for `load_config` — Property 4: Duplicate Searcher IDs always rejected
    - **Property 4: Duplicate Searcher IDs always rejected**
    - **Validates: Requirements 1.10**

  - [ ]* 2.9 Write property test for `load_config` — Property 5: Searcher objects correctly mapped
    - **Property 5: Searcher objects correctly mapped from config entries**
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 2.10 Write unit tests for `load_config`
    - Test missing file, empty `searchers` array, missing env var, valid two-searcher config, default interval
    - _Requirements: 1.1–1.12_

- [x] 3. Implement `listing_monitor/state.py`
  - [x] 3.1 Implement `read_store()`, `get_ids_for_searcher()`, and `update_store_for_searcher()`
    - `read_store`: return `{}` on `FileNotFoundError`; log error, overwrite with `{}`, and return `{}` on `json.JSONDecodeError`; log and return `{}` on `OSError`
    - `get_ids_for_searcher`: return empty set when key is absent
    - `update_store_for_searcher`: return a new `Store` (no mutation) with `new_id` appended; enforce `MAX_IDS_PER_SEARCHER = 1000` cap (retain most recent)
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.7_

  - [x] 3.2 Implement `write_store()` with atomic write
    - Write to a `.tmp` file, call `fsync`, then `os.replace()` to atomically swap into place
    - Enforce 1,000-ID cap per searcher when serialising
    - Log and continue on `OSError` during write
    - _Requirements: 5.3, 5.4_

  - [ ]* 3.3 Write property test for `state` — Property 11: Store round-trip preserves structure
    - **Property 11: ID_Store round-trip preserves searcher-keyed structure**
    - **Validates: Requirements 5.1**

  - [ ]* 3.4 Write property test for `state` — Property 12: Store cap retains at most 1,000 IDs
    - **Property 12: ID_Store cap retains at most 1,000 IDs per Searcher**
    - **Validates: Requirements 5.4**

  - [ ]* 3.5 Write unit tests for `state.py`
    - Test absent file, corrupt JSON (overwrite behaviour), `get_ids_for_searcher` on missing key, `update_store_for_searcher` immutability, cap enforcement
    - _Requirements: 5.1–5.7_

- [x] 4. Checkpoint — Ensure all tests pass for config and state modules
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement `listing_monitor/discord.py`
  - [x] 5.1 Implement `build_embed(listing)`
    - Set embed `title` (links to `listing["url"]`), `color: 3447003`
    - Always include `price` field when non-empty; include `area`, `rooms`, `location` fields only when non-empty strings
    - Return a plain `dict` ready for JSON serialisation
    - _Requirements: 6.1_

  - [x] 5.2 Implement `send_discord(searcher, listing)`
    - POST `{"embeds": [build_embed(listing)]}` to `searcher.webhook_url` using `requests`
    - Return `True` on 2xx; log HTTP status code and truncated (≤200 chars) response body, return `False` on non-2xx
    - Catch `requests.RequestException`, log the message, return `False`; do not raise
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 5.3 Write property test for `discord` — Property 13: Embed omits absent optional fields
    - **Property 13: Discord embed omits absent optional fields**
    - **Validates: Requirements 6.1**

  - [ ]* 5.4 Write unit tests for `discord.py`
    - Test `build_embed` with all fields present and with each optional field absent/empty
    - Test `send_discord` on 2xx success, non-2xx failure (log content), and `RequestException`
    - _Requirements: 6.1–6.4_

- [x] 6. Implement `listing_monitor/monitor.py` — `check_searcher` and `run_cycle`
  - [x] 6.1 Implement `check_searcher(searcher, store) -> Store`
    - Follow the design's 12-step flow: resolve stored IDs, detect first-run, call `fetch_html`, call `parse_listings`, handle zero-listings case, handle first-run baseline (no Discord), call `detect_new`, iterate new listings calling `send_discord` + `update_store_for_searcher` per successful post
    - Catch `ScraperError`, `ParserError`, and bare `Exception` — log with Searcher name and return original store unchanged
    - _Requirements: 3.1–3.8, 4.1–4.5, 6.5, 6.6_

  - [x] 6.2 Implement `run_cycle(config, store) -> Store`
    - Call `check_searcher` for every Searcher sequentially in config order
    - Return the cumulative updated Store
    - _Requirements: 2.3, 3.8, 7.1_

  - [ ]* 6.3 Write property test for `monitor` — Property 6: Every Searcher processed each cycle
    - **Property 6: Every configured Searcher is processed each cycle**
    - **Validates: Requirements 2.3, 3.8**

  - [ ]* 6.4 Write property test for `monitor` — Property 7: Searcher failure does not block others
    - **Property 7: Searcher failure does not prevent other Searchers from running**
    - **Validates: Requirements 3.4, 3.6, 3.7, 10.4**

  - [ ]* 6.5 Write property test for `monitor` — Property 8: Detection is set difference
    - **Property 8: New listing detection is the set difference of current vs. stored IDs**
    - **Validates: Requirements 4.1, 4.5, 10.1**

  - [ ]* 6.6 Write property test for `monitor` — Property 9: First-run baseline, no Discord calls
    - **Property 9: First-run baseline saves all IDs with no Discord calls**
    - **Validates: Requirements 4.2, 10.3**

  - [ ]* 6.7 Write property test for `monitor` — Property 10: No-new-listings leaves store unchanged
    - **Property 10: No-new-listings cycle leaves ID_Store unchanged**
    - **Validates: Requirements 4.3, 10.2**

  - [ ]* 6.8 Write property test for `monitor` — Property 14: One POST per new listing
    - **Property 14: One HTTP POST per new listing**
    - **Validates: Requirements 6.2, 10.2**

  - [ ]* 6.9 Write property test for `monitor` — Property 15: Discord failure prevents ID store update
    - **Property 15: Discord failure prevents ID_Store update for that listing**
    - **Validates: Requirements 6.3, 6.5, 10.5**

  - [ ]* 6.10 Write property test for `monitor` — Property 16: Successful cycle persists union of IDs
    - **Property 16: Successful cycle persists union of previous and current IDs**
    - **Validates: Requirements 6.6, 10.6**

  - [ ]* 6.11 Write unit tests for `monitor.py`
    - Test `check_searcher` for: `ScraperError`, `ParserError`, zero listings, first-run baseline, no new listings, partial Discord failure
    - Test `run_cycle` sequential ordering; test multi-searcher isolation (one fails, others succeed)
    - _Requirements: 3.1–3.8, 4.1–4.5, 10.1–10.6_

- [x] 7. Implement `listing_monitor/monitor.py` — `main()` entry point and signal handling
  - [x] 7.1 Implement `main()`
    - Call `load_config()`; catch `ConfigError`, print to stderr, call `sys.exit(1)`
    - Call `setup_logging` (reuse root-level `logging_setup.py`)
    - Install `SIGTERM` handler that logs shutdown and calls `sys.exit(0)`
    - Run indefinite polling loop: `store = read_store()` once per cycle, `store = run_cycle(config, store)`, `write_store(store)`, sleep with jitter; catch bare `Exception` in loop body and log without terminating; catch `KeyboardInterrupt` and exit cleanly
    - _Requirements: 7.1–7.4, 8.1, 8.2_

  - [ ]* 7.2 Write unit tests for `main()` signal handling
    - Test `KeyboardInterrupt` exits with code 0; test `ConfigError` exits with code 1
    - _Requirements: 7.3_

- [x] 8. Checkpoint — Ensure all tests pass for discord and monitor modules
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Add repository hygiene files
  - [x] 9.1 Create `config.json` at project root with two example Searcher entries
    - Include `check_interval_minutes: 15` and two Searcher objects matching the design example
    - _Requirements: 9.1, 1.2_

  - [x] 9.2 Update `.env.example` with multi-searcher webhook naming convention
    - Add `DISCORD_WEBHOOK_APARTMENTS` and `DISCORD_WEBHOOK_HOUSES` placeholder entries with explanatory comments
    - Retain existing entries to keep the old pipeline working
    - _Requirements: 9.2_

  - [x] 9.3 Update `.gitignore` to exclude `.env` and `previous_ids.json`
    - Check whether entries already exist before appending
    - _Requirements: 9.3_

  - [x] 9.4 Add "Adding a New Searcher" section to `README.md`
    - Four-step guide: create webhook → add to `.env` → add Searcher to `config.json` → restart monitor
    - _Requirements: 9.4_

  - [x] 9.5 Update `requirements.txt` with all new direct dependencies pinned to exact versions
    - Ensure `requests`, `python-dotenv`, `hypothesis`, `pytest`, `pytest-mock` are listed with `==` pins
    - _Requirements: 9.5_

- [x] 10. Write integration tests
  - [x]* 10.1 Write integration tests for `load_config` + `read_store`/`write_store` round-trip
    - Mark with `pytest.mark.integration`; skip if `config.json` or `.env` is absent
    - Verify `read_store` + `write_store` on a temp file preserves structure
    - _Requirements: 10.1–10.6_

- [x] 11. Final checkpoint — Ensure all tests pass
  - Run `pytest tests/listing_monitor/` (unit + property) and confirm 0 failures
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property-based tests use `hypothesis` with `@settings(max_examples=100)`; each test references its design property number
- The existing root-level modules (`monitor.py`, `config.py`, `id_store.py`, etc.) must not be modified
- `listing_monitor` modules import `fetch_html`, `parse_listings`, and `detect_new` directly from root-level modules — no duplication
- Integration tests require explicit `pytest -m integration` and a real `config.json`/`.env`; they are excluded from the default run
- The atomic write in `write_store` uses a `.tmp` sibling file + `os.replace()`; `fsync` is called before the replace

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2", "2.5", "2.6", "2.7", "2.8", "2.9"] },
    { "id": 4, "tasks": ["3.3", "3.4", "2.10", "5.1"] },
    { "id": 5, "tasks": ["3.5", "5.2", "6.1"] },
    { "id": 6, "tasks": ["5.3", "5.4", "6.2"] },
    { "id": 7, "tasks": ["6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10", "7.1"] },
    { "id": 8, "tasks": ["6.11", "7.2", "9.1", "9.2", "9.3", "9.4", "9.5"] },
    { "id": 9, "tasks": ["10.1"] }
  ]
}
```
