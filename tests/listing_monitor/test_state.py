"""
Unit tests for listing_monitor/state.py — tasks 3.1 and 3.2

Covers:
  - read_store: absent file → {}
  - read_store: invalid JSON → log error, overwrite with {}, return {}
  - read_store: OSError → log error, return {}
  - read_store: valid file → correct dict returned
  - get_ids_for_searcher: key present → set of IDs
  - get_ids_for_searcher: key absent → empty set
  - update_store_for_searcher: immutability (original store not mutated)
  - update_store_for_searcher: new_id appended correctly
  - update_store_for_searcher: cap enforcement (>1000 → retain last 1000)
  - update_store_for_searcher: other searchers preserved unchanged
  - write_store: round-trip (write then read returns same data)
  - write_store: atomic swap via .tmp file
  - write_store: cap enforcement per searcher
  - write_store: OSError logged, not raised
"""

import json
import logging
from unittest.mock import patch

import pytest

from listing_monitor.state import (
    ID_STORE_PATH,
    MAX_IDS_PER_SEARCHER,
    Store,
    get_ids_for_searcher,
    read_store,
    update_store_for_searcher,
    write_store,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def chdir_tmp(tmp_path, monkeypatch):
    """Run every test in a fresh temp directory so previous_ids.json is isolated."""
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# read_store — file absent
# ---------------------------------------------------------------------------


class TestReadStoreAbsent:
    def test_returns_empty_dict_when_file_missing(self):
        assert read_store() == {}

    def test_no_error_logged_when_file_missing(self, caplog):
        with caplog.at_level(logging.ERROR, logger="listing_monitor.state"):
            read_store()
        assert caplog.records == []


# ---------------------------------------------------------------------------
# read_store — invalid JSON
# ---------------------------------------------------------------------------


class TestReadStoreInvalidJson:
    def test_returns_empty_dict_on_corrupt_json(self, tmp_path):
        (tmp_path / ID_STORE_PATH).write_text("not valid json", encoding="utf-8")
        assert read_store() == {}

    def test_overwrites_corrupt_file_with_empty_object(self, tmp_path):
        (tmp_path / ID_STORE_PATH).write_text("{bad json}", encoding="utf-8")
        read_store()
        content = (tmp_path / ID_STORE_PATH).read_text(encoding="utf-8")
        assert json.loads(content) == {}

    def test_logs_error_on_corrupt_json(self, tmp_path, caplog):
        (tmp_path / ID_STORE_PATH).write_text("!!!garbage!!!", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="listing_monitor.state"):
            read_store()
        assert len(caplog.records) >= 1

    def test_logs_error_on_corrupt_json_contains_path(self, tmp_path, caplog):
        (tmp_path / ID_STORE_PATH).write_text("{broken}", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="listing_monitor.state"):
            read_store()
        assert any(ID_STORE_PATH in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# read_store — OSError
# ---------------------------------------------------------------------------


class TestReadStoreOSError:
    def test_returns_empty_dict_on_oserror(self, tmp_path):
        (tmp_path / ID_STORE_PATH).write_text('{"a": ["1"]}', encoding="utf-8")
        with patch("builtins.open", side_effect=OSError("permission denied")):
            result = read_store()
        assert result == {}

    def test_logs_error_on_oserror(self, tmp_path, caplog):
        (tmp_path / ID_STORE_PATH).write_text('{"a": ["1"]}', encoding="utf-8")
        with patch("builtins.open", side_effect=OSError("permission denied")):
            with caplog.at_level(logging.ERROR, logger="listing_monitor.state"):
                read_store()
        assert len(caplog.records) >= 1


# ---------------------------------------------------------------------------
# read_store — valid file
# ---------------------------------------------------------------------------


class TestReadStoreValid:
    def test_returns_correct_dict_from_valid_file(self, tmp_path):
        store = {"apartments": ["id1", "id2"], "houses": ["id3"]}
        (tmp_path / ID_STORE_PATH).write_text(json.dumps(store), encoding="utf-8")
        assert read_store() == store

    def test_returns_empty_dict_from_empty_object(self, tmp_path):
        (tmp_path / ID_STORE_PATH).write_text("{}", encoding="utf-8")
        assert read_store() == {}

    def test_custom_path_is_honoured(self, tmp_path):
        custom_path = str(tmp_path / "custom_store.json")
        store = {"s1": ["a", "b"]}
        with open(custom_path, "w", encoding="utf-8") as f:
            json.dump(store, f)
        assert read_store(custom_path) == store


# ---------------------------------------------------------------------------
# get_ids_for_searcher
# ---------------------------------------------------------------------------


class TestGetIdsForSearcher:
    def test_returns_set_when_key_present(self):
        store: Store = {"apartments": ["id1", "id2", "id3"]}
        result = get_ids_for_searcher(store, "apartments")
        assert result == {"id1", "id2", "id3"}

    def test_returns_empty_set_when_key_absent(self):
        store: Store = {"apartments": ["id1"]}
        result = get_ids_for_searcher(store, "houses")
        assert result == set()

    def test_returns_empty_set_for_empty_store(self):
        result = get_ids_for_searcher({}, "any_searcher")
        assert result == set()

    def test_returns_set_deduplicates_list(self):
        store: Store = {"s1": ["a", "a", "b"]}
        result = get_ids_for_searcher(store, "s1")
        assert result == {"a", "b"}

    def test_does_not_mutate_store(self):
        store: Store = {"s1": ["id1"]}
        get_ids_for_searcher(store, "s1")
        assert store == {"s1": ["id1"]}


# ---------------------------------------------------------------------------
# update_store_for_searcher — basic behaviour
# ---------------------------------------------------------------------------


class TestUpdateStoreForSearcher:
    def test_returns_new_store_with_id_appended(self):
        store: Store = {"s1": ["id1", "id2"]}
        result = update_store_for_searcher(store, "s1", "id3", ["id1", "id2", "id3"])
        assert "id3" in result["s1"]

    def test_new_id_at_end_of_list(self):
        store: Store = {"s1": ["id1", "id2"]}
        result = update_store_for_searcher(store, "s1", "id3", ["id1", "id2", "id3"])
        assert result["s1"][-1] == "id3"

    def test_creates_new_entry_for_absent_searcher(self):
        store: Store = {}
        result = update_store_for_searcher(store, "s1", "id1", ["id1"])
        assert result == {"s1": ["id1"]}

    def test_preserves_other_searchers(self):
        store: Store = {"s1": ["a"], "s2": ["b", "c"]}
        result = update_store_for_searcher(store, "s1", "d", ["a", "d"])
        assert result["s2"] == ["b", "c"]

    def test_does_not_mutate_original_store(self):
        store: Store = {"s1": ["id1", "id2"]}
        original_list = list(store["s1"])
        update_store_for_searcher(store, "s1", "id3", ["id1", "id2", "id3"])
        assert store["s1"] == original_list

    def test_does_not_mutate_other_searcher_lists(self):
        store: Store = {"s1": ["a"], "s2": ["b"]}
        original_s2 = list(store["s2"])
        update_store_for_searcher(store, "s1", "c", ["a", "c"])
        assert store["s2"] == original_s2

    def test_returns_new_dict_object(self):
        store: Store = {"s1": ["id1"]}
        result = update_store_for_searcher(store, "s1", "id2", ["id1", "id2"])
        assert result is not store


# ---------------------------------------------------------------------------
# update_store_for_searcher — cap enforcement
# ---------------------------------------------------------------------------


class TestUpdateStoreCapEnforcement:
    def test_list_within_cap_is_not_truncated(self):
        """When len <= MAX_IDS_PER_SEARCHER, no truncation occurs."""
        existing = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER - 1)]
        store: Store = {"s1": existing}
        result = update_store_for_searcher(store, "s1", "new", existing + ["new"])
        assert len(result["s1"]) == MAX_IDS_PER_SEARCHER

    def test_list_at_cap_plus_one_is_truncated(self):
        """When appending pushes len to MAX+1, result must be exactly MAX."""
        existing = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER)]
        store: Store = {"s1": existing}
        result = update_store_for_searcher(store, "s1", "new", existing + ["new"])
        assert len(result["s1"]) == MAX_IDS_PER_SEARCHER

    def test_cap_retains_most_recent_entries(self):
        """After truncation, the retained entries are the last MAX_IDS_PER_SEARCHER."""
        existing = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER)]
        store: Store = {"s1": existing}
        result = update_store_for_searcher(store, "s1", "newest", existing + ["newest"])
        # "newest" must be in the result (it was just added)
        assert "newest" in result["s1"]
        # "id0" was the oldest and must have been evicted
        assert "id0" not in result["s1"]

    def test_cap_retains_exactly_max_ids(self):
        """For a heavily oversized list, exactly MAX_IDS_PER_SEARCHER entries are retained."""
        existing = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER + 500)]
        store: Store = {"s1": existing}
        result = update_store_for_searcher(store, "s1", "brand_new", existing + ["brand_new"])
        assert len(result["s1"]) == MAX_IDS_PER_SEARCHER


# ---------------------------------------------------------------------------
# write_store — round-trip
# ---------------------------------------------------------------------------


class TestWriteStoreRoundTrip:
    def test_write_then_read_returns_same_store(self, tmp_path):
        store: Store = {"apartments": ["id1", "id2"], "houses": ["id3"]}
        path = str(tmp_path / ID_STORE_PATH)
        write_store(store, path)
        assert read_store(path) == store

    def test_write_empty_store(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        write_store({}, path)
        assert read_store(path) == {}

    def test_write_creates_file(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        write_store({"s1": ["id1"]}, path)
        assert (tmp_path / ID_STORE_PATH).exists()

    def test_write_valid_json(self, tmp_path):
        store: Store = {"s1": ["a", "b", "c"]}
        path = str(tmp_path / ID_STORE_PATH)
        write_store(store, path)
        content = (tmp_path / ID_STORE_PATH).read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed == store

    def test_write_overwrites_existing_file(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        write_store({"s1": ["old"]}, path)
        write_store({"s1": ["new"]}, path)
        assert read_store(path) == {"s1": ["new"]}

    def test_tmp_file_not_present_after_successful_write(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        write_store({"s1": ["id1"]}, path)
        assert not (tmp_path / (ID_STORE_PATH + ".tmp")).exists()


# ---------------------------------------------------------------------------
# write_store — cap enforcement
# ---------------------------------------------------------------------------


class TestWriteStoreCapEnforcement:
    def test_oversized_list_is_capped_on_write(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        ids = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER + 100)]
        write_store({"s1": ids}, path)
        result = read_store(path)
        assert len(result["s1"]) == MAX_IDS_PER_SEARCHER

    def test_cap_retains_most_recent_ids(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        ids = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER + 10)]
        write_store({"s1": ids}, path)
        result = read_store(path)
        # Most recent (last) entries are retained
        assert result["s1"][-1] == f"id{MAX_IDS_PER_SEARCHER + 9}"
        # Oldest entries are dropped
        assert "id0" not in result["s1"]

    def test_list_at_exact_cap_is_not_truncated(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        ids = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER)]
        write_store({"s1": ids}, path)
        result = read_store(path)
        assert len(result["s1"]) == MAX_IDS_PER_SEARCHER

    def test_original_store_not_mutated_by_cap(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        ids = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER + 50)]
        original_len = len(ids)
        store: Store = {"s1": ids}
        write_store(store, path)
        # The in-memory store must not be modified
        assert len(store["s1"]) == original_len

    def test_multiple_searchers_each_capped_independently(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        oversized = [f"id{i}" for i in range(MAX_IDS_PER_SEARCHER + 200)]
        small = ["a", "b", "c"]
        write_store({"s1": oversized, "s2": small}, path)
        result = read_store(path)
        assert len(result["s1"]) == MAX_IDS_PER_SEARCHER
        assert result["s2"] == small


# ---------------------------------------------------------------------------
# write_store — OSError handling
# ---------------------------------------------------------------------------


class TestWriteStoreOSError:
    def test_does_not_raise_on_oserror(self, tmp_path):
        path = str(tmp_path / ID_STORE_PATH)
        with patch("builtins.open", side_effect=OSError("disk full")):
            # Must not raise
            write_store({"s1": ["id1"]}, path)

    def test_logs_error_on_oserror(self, tmp_path, caplog):
        path = str(tmp_path / ID_STORE_PATH)
        with patch("builtins.open", side_effect=OSError("disk full")):
            with caplog.at_level(logging.ERROR, logger="listing_monitor.state"):
                write_store({"s1": ["id1"]}, path)
        assert len(caplog.records) >= 1

    def test_logs_error_contains_path(self, tmp_path, caplog):
        path = str(tmp_path / ID_STORE_PATH)
        with patch("builtins.open", side_effect=OSError("no space")):
            with caplog.at_level(logging.ERROR, logger="listing_monitor.state"):
                write_store({"s1": ["id1"]}, path)
        assert any(ID_STORE_PATH in r.message for r in caplog.records)
