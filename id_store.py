"""
id_store.py — ID Store for Njuškalo Telegram Notifier

Manages reading from and writing to ``previous_ids.json``, which tracks
listing IDs that have already been seen.  All I/O is synchronous.  The
write path uses a write-to-temp-then-rename pattern to prevent partial
writes and keep the on-disk file always valid.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

ID_STORE_PATH = "previous_ids.json"
MAX_STORE_SIZE = 1000


# ---------------------------------------------------------------------------
# read_ids — task 4.2
# ---------------------------------------------------------------------------
def read_ids() -> set[str]:
    """
    Read the stored set of listing IDs from ID_STORE_PATH.

    Returns an empty set if the file is absent, unreadable, or contains
    invalid JSON (logs an appropriate error in each case).
    On invalid JSON, also overwrites the file with a valid empty array.
    """
    try:
        with open(ID_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data)
    except FileNotFoundError:
        logger.debug("ID store file '%s' not found; starting with empty set.", ID_STORE_PATH)
        return set()
    except OSError as e:
        logger.error(
            "ID store file '%s' is unreadable (I/O error: %s); starting with empty set.",
            ID_STORE_PATH,
            e,
        )
        return set()
    except json.JSONDecodeError as e:
        logger.error(
            "ID store file '%s' contains invalid JSON (%s); overwriting with empty array and starting fresh.",
            ID_STORE_PATH,
            e,
        )
        try:
            with open(ID_STORE_PATH, "w", encoding="utf-8") as f:
                f.write("[]")
        except OSError as write_err:
            logger.error(
                "Failed to overwrite corrupt ID store file '%s': %s",
                ID_STORE_PATH,
                write_err,
            )
        return set()


# ---------------------------------------------------------------------------
# write_ids — task 4.3
# ---------------------------------------------------------------------------
def write_ids(ids: set[str], recently_added: list[str]) -> None:
    """
    Persist *ids* to previous_ids.json atomically.

    If len(ids) > MAX_STORE_SIZE, retain only the MAX_STORE_SIZE most
    recently added IDs (as tracked by the *recently_added* ordering).
    Uses write-to-temp-then-os.replace() for crash safety so the
    original file is never left in a partial state.

    Size-cap algorithm:
    - Start from the tail of *recently_added* (most recent entries last).
    - Fill up to MAX_STORE_SIZE slots; any remaining capacity is filled
      from IDs in *ids* that never appeared in *recently_added*.
    """
    if len(ids) > MAX_STORE_SIZE:
        # IDs that were explicitly tracked as recently added (most recent last)
        recent_in_ids = [id_ for id_ in recently_added if id_ in ids]
        # Take the tail — the MAX_STORE_SIZE most recently added
        kept: list[str] = recent_in_ids[-MAX_STORE_SIZE:]
        remaining_capacity = MAX_STORE_SIZE - len(kept)
        if remaining_capacity > 0:
            # Fill remaining capacity from ids not already in recently_added
            extra = [id_ for id_ in ids if id_ not in set(recently_added)]
            kept.extend(extra[:remaining_capacity])
        ids_to_write = kept
    else:
        ids_to_write = list(ids)

    tmp_path = ID_STORE_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(ids_to_write, f)
        os.replace(tmp_path, ID_STORE_PATH)
    except OSError as e:
        logger.error(
            "Failed to write ID store to '%s': %s",
            ID_STORE_PATH,
            e,
        )
