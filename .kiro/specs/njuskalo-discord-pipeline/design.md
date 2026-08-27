# Design Document — njuskalo-discord-pipeline

## Overview

This document describes the technical design for extending the existing single-searcher Njuškalo Discord Notifier into a multi-searcher pipeline. The new code lives entirely in a `listing_monitor/` package and reuses the existing root-level `fetch_html`, `parse_listings`, and `detect_new` functions without modification.

The core idea is a data-driven fan-out: an operator declares N independent Searchers in `config.json`. Each Searcher is an isolated unit with its own scrape URL and Discord webhook. The polling loop iterates over the Searcher list sequentially, calling a generic `check_searcher(searcher)` function for each one. All state (seen listing IDs) is stored in a single `previous_ids.json` file keyed by Searcher ID, so each Searcher's history is fully isolated from every other.

### Key Design Decisions

- **Config-file-driven, not environment-variable-driven.** The original service read a single `NJUSKALO_SEARCH_URL` from `.env`. With multiple searchers, a flat env-var approach becomes unwieldy. A structured `config.json` is the natural representation for a list of named objects with heterogeneous fields.
- **Webhook URLs stay in `.env`; only the env-var _name_ goes in `config.json`.** This keeps credentials out of version control while letting operators name their webhooks descriptively (e.g., `DISCORD_WEBHOOK_APARTMENTS`).
- **No parallelism.** Searchers run sequentially to keep failure isolation simple and avoid hammering Njuškalo concurrently. The scraper already applies per-request random delays, so sequential execution is the right default.
- **Write-after-success per listing.** A Discord failure leaves the listing ID un-persisted, enabling automatic retry on the next cycle. This guarantees at-least-once delivery at the cost of occasional duplicate notifications (acceptable for a property-alert use case).
- **One embed per listing, one HTTP POST per embed.** This matches Discord's recommended usage for webhook embeds and allows granular per-listing failure tracking.

---

## Architecture

The service follows a simple sequential pipeline, executed once per polling cycle for every configured Searcher.

```
startup
  │
  ▼
listing_monitor/config.py
  load_config()  →  PipelineConfig(check_interval_minutes, searchers: list[Searcher])
  │
  ▼
listing_monitor/monitor.py
  main()
  │
  └── polling loop ──────────────────────────────────────────────────────────┐
        │                                                                     │
        for searcher in config.searchers:                                     │
          check_searcher(searcher)                                            │
          │                                                                   │
          ├── listing_monitor/state.py: read_store()                         │
          │       → {searcher_id: [listing_ids]}                             │
          │                                                                   │
          ├── scraper_adapter.fetch_html(searcher.search_url)                │
          │       → html: str                                                 │
          │                                                                   │
          ├── parser_adapter.parse_listings(html)                            │
          │       → current: list[Listing]                                   │
          │                                                                   │
          ├── detector.detect_new(current, stored_ids_for_searcher)          │
          │       → new_listings: list[Listing]                              │
          │                                                                   │
          └── for listing in new_listings:                                   │
                listing_monitor/discord.py: send_discord(searcher, listing)  │
                  → success: bool                                             │
                if success:                                                   │
                  listing_monitor/state.py: write_store(updated_store)       │
                                                                             │
        sleep(check_interval_minutes * 60 + jitter)  ◄───────────────────────┘
```

### Package Layout

```
listing-notifying-app/
├── listing_monitor/           ← NEW package
│   ├── __init__.py
│   ├── config.py              ← PipelineConfig, Searcher dataclass, load_config()
│   ├── monitor.py             ← main(), polling loop, check_searcher()
│   ├── state.py               ← read_store(), write_store()
│   └── discord.py             ← send_discord(), build_embed()
├── config.py                  ← UNCHANGED (single-searcher pipeline)
├── monitor.py                 ← UNCHANGED
├── id_store.py                ← UNCHANGED
├── scraper_adapter.py         ← UNCHANGED (imported by listing_monitor)
├── parser_adapter.py          ← UNCHANGED (imported by listing_monitor)
├── detector.py                ← UNCHANGED (imported by listing_monitor)
├── notifier.py                ← UNCHANGED
├── logging_setup.py           ← UNCHANGED
├── config.json                ← NEW operator config file
└── previous_ids.json          ← UPDATED schema (keyed by searcher ID)
```

---

## Components and Interfaces

### `listing_monitor/config.py`

Responsible for loading `config.json`, validating all fields, resolving webhook env vars, and producing a `PipelineConfig` value object.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Searcher:
    id: str               # unique key; becomes the key in previous_ids.json
    name: str             # human-readable label used in log messages
    search_url: str       # full Njuškalo search URL
    webhook_url: str      # resolved Discord webhook URL (from env var)

@dataclass(frozen=True)
class PipelineConfig:
    check_interval_minutes: int   # in [1, 1440]; default 5
    searchers: tuple[Searcher, ...]

class ConfigError(Exception):
    """Raised on any config validation failure. Callers exit with status 1."""

def load_config(config_path: str = "config.json") -> PipelineConfig:
    """
    Load and validate config.json.
    Calls load_dotenv() so .env is honoured.
    Raises ConfigError on any validation failure.
    """
```

Validation order (first failure raises immediately):
1. `load_dotenv()` — populate env from `.env` file if present.
2. Open and parse `config.json`; raise on `FileNotFoundError`, `OSError`, `json.JSONDecodeError`.
3. Validate `check_interval_minutes`: missing → 5; present but not integer in [1,1440] → raise.
4. Validate `searchers` key exists and is a non-empty list; raise if absent or empty.
5. For each Searcher entry: validate all four required fields are present and non-empty strings; raise identifying the offending Searcher.
6. Validate no two Searchers share the same `id`; raise on duplicate.
7. Resolve `discord_webhook_env` → `webhook_url` for every Searcher; raise if env var is absent or empty.

### `listing_monitor/state.py`

Responsible for reading and writing `previous_ids.json` in its new per-searcher-keyed format.

```python
# Type alias for the full store
Store = dict[str, list[str]]   # { searcher_id: [listing_id, ...] }

ID_STORE_PATH = "previous_ids.json"
MAX_IDS_PER_SEARCHER = 1000

def read_store() -> Store:
    """
    Read previous_ids.json and return as a dict.
    - FileNotFoundError  → return {}
    - json.JSONDecodeError → log error, overwrite with {}, return {}
    - OSError            → log error, return {}
    """

def write_store(store: Store) -> None:
    """
    Persist store to previous_ids.json atomically.
    Uses write-to-temp-file + fsync + os.replace().
    Enforces MAX_IDS_PER_SEARCHER cap per searcher entry (retains most recent).
    """

def get_ids_for_searcher(store: Store, searcher_id: str) -> set[str]:
    """Return the stored ID set for a Searcher; empty set if absent."""

def update_store_for_searcher(
    store: Store,
    searcher_id: str,
    new_id: str,
    all_current_ids: list[str],
) -> Store:
    """
    Return a new Store with new_id added to the searcher's entry.
    all_current_ids is used to determine recency ordering for the size cap.
    Does NOT mutate the input store.
    """
```

Note: `write_store` is called incrementally — once per successfully notified listing — to satisfy the per-listing write-after-success requirement. Each call reads from the returned value of `update_store_for_searcher` chained across the new listings.

### `listing_monitor/discord.py`

Responsible for building Discord embed payloads and posting them via HTTP.

```python
from parser_adapter import Listing

class DiscordError(Exception):
    """Wraps HTTP or network failure from a Discord webhook call."""

def build_embed(listing: Listing) -> dict:
    """
    Build a Discord embed dict from a Listing.
    - title: listing["title"] (links to listing["url"])
    - fields: price always included if non-empty; area, rooms, location
      included only when non-empty.
    Returns a plain dict suitable for JSON serialisation.
    """

def send_discord(searcher: "Searcher", listing: Listing) -> bool:
    """
    POST one embed to searcher.webhook_url.
    Returns True on 2xx, False on non-2xx or network error.
    Logs the HTTP status code and truncated response body on failure.
    Does NOT raise; callers check the boolean return value.
    """
```

The payload structure sent to Discord:

```json
{
  "embeds": [
    {
      "title": "<listing title>",
      "url": "<listing URL>",
      "color": 3447003,
      "fields": [
        { "name": "Cijena", "value": "...", "inline": true },
        { "name": "Površina", "value": "...", "inline": true },
        { "name": "Sobe", "value": "...", "inline": true },
        { "name": "Lokacija", "value": "...", "inline": false }
      ]
    }
  ]
}
```

Optional fields (`area`, `rooms`, `location`) are included in `fields` only when the corresponding `Listing` value is a non-empty string.

### `listing_monitor/monitor.py`

Entry point and polling loop.

```python
def check_searcher(searcher: Searcher, store: Store) -> Store:
    """
    Execute one scrape-detect-notify cycle for a single Searcher.
    Returns an updated Store (the input store is not mutated).
    All exceptions from fetch_html, parse_listings are caught and logged;
    the original store is returned unchanged on any failure.
    """

def run_cycle(config: PipelineConfig, store: Store) -> Store:
    """
    Call check_searcher for every Searcher in order.
    Returns the updated Store after all Searchers have been processed.
    """

def main() -> None:
    """
    Load config, set up logging, install signal handlers, run polling loop.
    """
```

`check_searcher` internal flow:

1. Call `state.read_store()` ... actually `store` is passed in as a parameter — the store is read once per cycle in `run_cycle`, not once per searcher. This avoids N file reads per cycle and ensures a consistent view within a cycle.
2. `stored_ids = state.get_ids_for_searcher(store, searcher.id)`
3. `is_first_run = searcher.id not in store`
4. `html = fetch_html(searcher.search_url)` — catch `ScraperError`, log with searcher name, return original store.
5. `listings = parse_listings(html)` — catch `ParserError`, log with searcher name, return original store.
6. If `not listings`: log warning with searcher name, return original store (no ID store update).
7. If `is_first_run`: save all current IDs as baseline (no Discord), return updated store.
8. `new_listings = detect_new(listings, stored_ids)`
9. If `not new_listings`: log "no new listings for <name>", return original store.
10. Log count of new listings with searcher name.
11. For each listing in `new_listings`: call `send_discord(searcher, listing)`; if True, call `update_store_for_searcher`.
12. Return the (possibly incrementally updated) store.

The per-listing write approach means the store passed to `write_store` at the end of `run_cycle` reflects only the listings that were successfully posted to Discord.

---

## Data Models

### `config.json`

```json
{
  "check_interval_minutes": 15,
  "searchers": [
    {
      "id": "apartments",
      "name": "Apartments Zagreb ≤600€ pets OK",
      "search_url": "https://www.njuskalo.hr/iznajmljivanje-stanova?geo[locationIds]=1250,1253&price[max]=600&petsAllowed=1",
      "discord_webhook_env": "DISCORD_WEBHOOK_APARTMENTS"
    },
    {
      "id": "houses",
      "name": "Houses Zagreb rent",
      "search_url": "https://www.njuskalo.hr/iznajmljivanje-kuca?geo[locationIds]=1250",
      "discord_webhook_env": "DISCORD_WEBHOOK_HOUSES"
    }
  ]
}
```

### `previous_ids.json` (updated schema)

```json
{
  "apartments": ["51297387", "51310042", "51318899"],
  "houses": ["51200010", "51200011"]
}
```

Keys are Searcher IDs as declared in `config.json`. Values are arrays of listing ID strings. Each array is capped at 1,000 entries (most recently added retained). An absent key means First_Run for that Searcher.

### `Listing` TypedDict (unchanged, from `parser_adapter.py`)

```python
class Listing(TypedDict, total=False):
    listing_id: str   # required
    title: str        # required
    price: str        # required
    url: str          # required
    area: str         # optional
    rooms: str        # optional
    location: str     # optional
```

### `.env` (updated naming convention)

```dotenv
# One entry per Searcher — name must match discord_webhook_env in config.json
DISCORD_WEBHOOK_APARTMENTS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_HOUSES=https://discord.com/api/webhooks/...

# Global settings
CHECK_INTERVAL_MINUTES is now in config.json — no longer read from .env
LOG_LEVEL=INFO
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Invalid JSON config always rejected

*For any* string that is not valid JSON (truncated, garbled, or otherwise malformed), calling `load_config` with that content as `config.json` SHALL raise `ConfigError`.

**Validates: Requirements 1.4**

---

### Property 2: Out-of-range or non-integer check_interval_minutes always rejected

*For any* `check_interval_minutes` value that is either outside [1, 1440] or not parseable as an integer, calling `load_config` SHALL raise `ConfigError`.

**Validates: Requirements 1.6**

---

### Property 3: Missing or empty required Searcher fields always rejected

*For any* Searcher object where at least one required field (`id`, `name`, `search_url`, `discord_webhook_env`) is absent or an empty/whitespace-only string, calling `load_config` SHALL raise `ConfigError` identifying the offending Searcher.

**Validates: Requirements 1.8, 1.9**

---

### Property 4: Duplicate Searcher IDs always rejected

*For any* `searchers` array containing two or more entries that share the same `id` value, calling `load_config` SHALL raise `ConfigError`.

**Validates: Requirements 1.10**

---

### Property 5: Searcher objects correctly mapped from config entries

*For any* list of N valid Searcher entries in `config.json`, `load_config` SHALL produce exactly N `Searcher` frozen dataclass objects where each object's `id`, `name`, `search_url`, and `webhook_url` match the corresponding config entry and resolved environment variable respectively.

**Validates: Requirements 2.1, 2.2**

---

### Property 6: Every configured Searcher is processed each cycle

*For any* list of N Searchers in a `PipelineConfig`, calling `run_cycle` SHALL invoke `check_searcher` exactly once for each Searcher, in the order they appear in the config.

**Validates: Requirements 2.3, 3.8**

---

### Property 7: Searcher failure does not prevent other Searchers from running

*For any* list of N Searchers where the Searcher at position K raises `ScraperError`, `ParserError`, or an unhandled exception, `run_cycle` SHALL still invoke `check_searcher` for all other N−1 Searchers and each of those cycles SHALL complete normally.

**Validates: Requirements 3.4, 3.6, 3.7, 10.4**

---

### Property 8: New listing detection is the set difference of current vs. stored IDs

*For any* list of current Listings and any set of stored IDs, `detect_new(current, stored_ids)` SHALL return exactly the Listings whose `listing_id` is in `current` but not in `stored_ids`. Case-sensitive string equality is used.

**Validates: Requirements 4.1, 4.5, 10.1**

---

### Property 9: First-run baseline saves all IDs with no Discord calls

*For any* set of N current Listings when a Searcher has no entry in the ID_Store (`is_first_run = True`), `check_searcher` SHALL make zero calls to `send_discord` and the returned Store SHALL contain all N listing IDs for that Searcher.

**Validates: Requirements 4.2, 10.3**

---

### Property 10: No-new-listings cycle leaves ID_Store unchanged

*For any* current listing list where every listing's ID is already in the stored set for that Searcher, `check_searcher` SHALL make zero calls to `send_discord` and return a Store identical to the one passed in.

**Validates: Requirements 4.3, 10.2**

---

### Property 11: ID_Store round-trip preserves searcher-keyed structure

*For any* `Store` mapping of Searcher IDs to listing ID arrays, calling `write_store(store)` followed by `read_store()` SHALL return a mapping equal to the original (modulo the 1,000-ID cap per searcher).

**Validates: Requirements 5.1**

---

### Property 12: ID_Store cap retains at most 1,000 IDs per Searcher

*For any* Searcher whose ID array exceeds 1,000 entries, after `write_store` + `read_store` the array for that Searcher SHALL contain at most 1,000 entries.

**Validates: Requirements 5.4**

---

### Property 13: Discord embed omits absent optional fields

*For any* Listing with any subset of optional fields (`area`, `rooms`, `location`) set to empty strings or absent, `build_embed` SHALL produce an embed whose `fields` list contains entries only for the non-empty values.

**Validates: Requirements 6.1**

---

### Property 14: One HTTP POST per new listing

*For any* N new Listings passed through a successful `check_searcher` cycle, exactly N HTTP POST requests SHALL be made to the Searcher's webhook URL (one per listing).

**Validates: Requirements 6.2, 10.2**

---

### Property 15: Discord failure prevents ID_Store update for that listing

*For any* Listing where `send_discord` returns False (non-2xx or network error), that Listing's ID SHALL NOT be present in the Store returned by `check_searcher`.

**Validates: Requirements 6.3, 6.5, 10.5**

---

### Property 16: Successful cycle persists union of previous and current IDs

*For any* initial Store and any current listing list (all listings successfully posted), the Store returned by `check_searcher` for that Searcher SHALL contain every ID that was in the previous store entry UNION every ID in the current listing list.

**Validates: Requirements 6.6, 10.6**

---

## Error Handling

### Config loading errors

All errors in `load_config` raise `ConfigError` with a descriptive message that includes the context (file path, Searcher ID, field name, invalid value). `main()` catches `ConfigError`, prints to stderr, and calls `sys.exit(1)`.

### Per-cycle errors (caught, logged, cycle continues)

| Situation | Behaviour |
|---|---|
| `ScraperError` from `fetch_html` | Log error with Searcher name, skip Searcher, continue to next |
| `ParserError` from `parse_listings` | Log error with Searcher name, skip Searcher, continue to next |
| Zero listings returned | Log warning with Searcher name, skip ID store update, continue |
| Any other exception in `check_searcher` | Log exception type, message, and Searcher name, continue to next |

### Discord notification errors

| Situation | Behaviour |
|---|---|
| Non-2xx HTTP response | `send_discord` logs status code + response body (truncated to 200 chars), returns False |
| `requests.RequestException` (network error) | `send_discord` logs exception message, returns False |
| `False` returned by `send_discord` | `check_searcher` does NOT call `update_store_for_searcher` for that listing; listing will be retried next cycle |

### ID store I/O errors

| Situation | Behaviour |
|---|---|
| File absent | `read_store` returns `{}`, all Searchers treated as First_Run |
| Invalid JSON | `read_store` logs error, overwrites file with `{}`, returns `{}` |
| `OSError` on read | `read_store` logs error, returns `{}` |
| `OSError` on write | `write_store` logs error; in-memory state still correct for remainder of cycle |

### Signal handling

`SIGTERM` and `KeyboardInterrupt` are caught in `main()`. The handler logs a shutdown message and calls `sys.exit(0)`. The ID store is left in its last valid persisted state. No special cleanup is attempted; the atomic write strategy means the file is never partially written.

---

## Testing Strategy

### Test framework

`pytest` with `pytest-mock` for mocking. `hypothesis` for property-based tests (minimum 100 iterations per property, configured via `@settings(max_examples=100)`).

### Unit tests (example-based)

Located in `tests/listing_monitor/`. One test file per module:

- `test_config.py` — valid config loading, default values, specific error cases (missing file, empty searchers, unknown env var)
- `test_state.py` — absent file returns `{}`, corrupt file overwrites, `get_ids_for_searcher` on missing key
- `test_discord.py` — `build_embed` with all fields present; `send_discord` 2xx success, non-2xx failure, network error
- `test_monitor.py` — `check_searcher` wiring (ScraperError, ParserError, zero listings, first-run, no new listings); signal handling; `run_cycle` sequential order

### Property-based tests (Hypothesis)

Located in `tests/listing_monitor/test_properties.py`.

Each test is tagged with a comment referencing the design property it validates:

```python
# Feature: njuskalo-discord-pipeline, Property 1: Invalid JSON config always rejected
@given(st.text().filter(lambda s: not _is_valid_json(s)))
@settings(max_examples=100)
def test_invalid_json_config_raises(invalid_json): ...
```

Property → test mapping:

| Property | Hypothesis strategy |
|---|---|
| 1 — Invalid JSON rejected | `st.text()` filtered to non-valid-JSON strings |
| 2 — Bad check_interval rejected | `st.integers().filter(lambda n: not 1 <= n <= 1440)` and `st.text().filter(not int-parseable)` |
| 3 — Missing Searcher field rejected | `st.fixed_dictionaries(...)` with randomly nulled fields |
| 4 — Duplicate Searcher IDs rejected | `st.lists(searcher_strategy, min_size=2)` with forced ID collision |
| 5 — Searcher mapping correct | `st.lists(valid_searcher_strategy, min_size=1, max_size=10)` |
| 6 — All Searchers processed | `st.lists(searcher_strategy, min_size=1, max_size=10)` |
| 7 — Failure isolation | `st.lists(searcher_strategy, min_size=2)` + injected exception at random index |
| 8 — Detection is set difference | `st.lists(listing_strategy)` + `st.frozensets(st.text())` |
| 9 — First-run baseline | `st.lists(listing_strategy, min_size=0)` with empty store |
| 10 — No-new-listings unchanged | `st.lists(listing_strategy, min_size=1)` with all IDs pre-stored |
| 11 — Store round-trip | `st.dictionaries(st.text(), st.lists(st.text()))` |
| 12 — Store cap | `st.lists(st.text(), min_size=1001)` per searcher |
| 13 — Embed omits absent fields | `st.fixed_dictionaries` with optional fields set to `""` or absent |
| 14 — One POST per listing | `st.lists(listing_strategy, min_size=1, max_size=20)` |
| 15 — Discord failure no ID write | `st.sampled_from(range(300, 600))` for status codes |
| 16 — Successful cycle union | `st.frozensets(st.text())` for initial store + `st.lists(listing_strategy)` |

### Integration tests

A single `tests/test_integration.py` file with `pytest.mark.integration` that:
- Calls `load_config` with a real `config.json` and real `.env` (skipped if file absent)
- Verifies `read_store` + `write_store` round-trip on a temp file

Integration tests are excluded from the default `pytest` run and require explicit `pytest -m integration`.
