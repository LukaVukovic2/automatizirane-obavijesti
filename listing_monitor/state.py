import json
import logging
import os

logger = logging.getLogger(__name__)

# Type alias for the full store: { searcher_id: [listing_id, ...] }
Store = dict[str, list[str]]

ID_STORE_PATH = "previous_ids.json"
MAX_IDS_PER_SEARCHER = 1000


def read_store(path: str = ID_STORE_PATH) -> Store:
    """
    Read previous_ids.json and return as a dict.

    - FileNotFoundError  → return {}
    - json.JSONDecodeError → log error, overwrite file with {}, return {}
    - OSError            → log error, return {}
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning(
                "ID store at %r has unexpected format (got %s, expected dict) "
                "— this is likely the old single-searcher flat array; resetting to {}",
                path,
                type(data).__name__,
            )
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            except OSError as write_exc:
                logger.error("Failed to overwrite old-format ID store at %r: %s", path, write_exc)
            return {}
        return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.error("ID store at %r contains invalid JSON: %s — resetting to {}", path, exc)
        # Best-effort overwrite with empty object
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)
        except OSError as write_exc:
            logger.error("Failed to overwrite corrupted ID store at %r: %s", path, write_exc)
        return {}
    except OSError as exc:
        logger.error("Could not read ID store at %r: %s", path, exc)
        return {}


def get_ids_for_searcher(store: Store, searcher_id: str) -> set[str]:
    """Return the stored ID set for a Searcher; empty set if absent."""
    return set(store[searcher_id]) if searcher_id in store else set()


def update_store_for_searcher(
    store: Store,
    searcher_id: str,
    new_id: str,
    all_current_ids: list[str],
) -> Store:
    """
    Return a new Store with new_id added to the searcher's entry.

    Does NOT mutate the input store.
    Enforces MAX_IDS_PER_SEARCHER cap, retaining the most recent entries.
    """
    new_store: Store = {k: list(v) for k, v in store.items()}

    current_list = list(new_store.get(searcher_id, []))
    current_list.append(new_id)

    # Enforce cap — retain only the last MAX_IDS_PER_SEARCHER entries
    if len(current_list) > MAX_IDS_PER_SEARCHER:
        current_list = current_list[-MAX_IDS_PER_SEARCHER:]

    new_store[searcher_id] = current_list
    return new_store


def write_store(store: Store, path: str = ID_STORE_PATH) -> None:
    """
    Persist store to path atomically.

    - Caps each searcher's ID list to MAX_IDS_PER_SEARCHER most recent entries
      before serialising.
    - Writes to a sibling .tmp file, calls fsync, then uses os.replace() to
      atomically swap it into place so the file is never left in a partial state.
    - On OSError, logs the error and returns without raising.

    Requirements 5.3, 5.4
    """
    tmp_path = path + ".tmp"
    # Enforce cap per searcher before writing
    capped: Store = {
        searcher_id: ids[-MAX_IDS_PER_SEARCHER:] if len(ids) > MAX_IDS_PER_SEARCHER else list(ids)
        for searcher_id, ids in store.items()
    }
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(capped, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.error("Could not write ID store to %r: %s", path, exc)
