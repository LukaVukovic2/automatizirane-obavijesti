"""
Unit tests for id_store.read_ids() — task 4.2.

Covers:
  - File absent       → FileNotFoundError → empty set returned
  - File unreadable   → OSError           → empty set returned
  - Invalid JSON      → json.JSONDecodeError → empty set returned, file overwritten with []
  - Valid JSON array  → correct set[str] returned
"""

import json
import os
import stat

import pytest

import id_store
from id_store import read_ids, ID_STORE_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def chdir_tmp(tmp_path, monkeypatch):
    """Run every test in a fresh temp directory so previous_ids.json is isolated."""
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReadIdsAbsent:
    def test_returns_empty_set_when_file_missing(self):
        assert read_ids() == set()

    def test_logs_debug_when_file_missing(self, caplog):
        import logging
        with caplog.at_level(logging.DEBUG, logger="id_store"):
            read_ids()
        assert any("not found" in r.message.lower() for r in caplog.records)


class TestReadIdsInvalidJson:
    def test_returns_empty_set_on_invalid_json(self, tmp_path):
        (tmp_path / ID_STORE_PATH).write_text("not valid json", encoding="utf-8")
        assert read_ids() == set()

    def test_overwrites_file_with_empty_array_on_invalid_json(self, tmp_path):
        (tmp_path / ID_STORE_PATH).write_text("{bad}", encoding="utf-8")
        read_ids()
        content = (tmp_path / ID_STORE_PATH).read_text(encoding="utf-8")
        assert json.loads(content) == []

    def test_logs_error_on_invalid_json(self, tmp_path, caplog):
        import logging
        (tmp_path / ID_STORE_PATH).write_text("!!!garbage!!!", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="id_store"):
            read_ids()
        assert any("invalid json" in r.message.lower() for r in caplog.records)


class TestReadIdsUnreadable:
    @pytest.mark.skipif(os.name == "nt", reason="chmod is unreliable on Windows for this scenario")
    def test_returns_empty_set_when_unreadable(self, tmp_path):
        p = tmp_path / ID_STORE_PATH
        p.write_text('["abc"]', encoding="utf-8")
        p.chmod(0o000)
        try:
            assert read_ids() == set()
        finally:
            p.chmod(0o644)

    @pytest.mark.skipif(os.name == "nt", reason="chmod is unreliable on Windows for this scenario")
    def test_logs_error_when_unreadable(self, tmp_path, caplog):
        import logging
        p = tmp_path / ID_STORE_PATH
        p.write_text('["abc"]', encoding="utf-8")
        p.chmod(0o000)
        try:
            with caplog.at_level(logging.ERROR, logger="id_store"):
                read_ids()
            assert any("unreadable" in r.message.lower() for r in caplog.records)
        finally:
            p.chmod(0o644)

    def test_returns_empty_set_when_open_raises_oserror(self, tmp_path):
        """Platform-independent: mock open() to raise OSError → read_ids returns empty set."""
        from unittest.mock import patch, mock_open
        p = tmp_path / ID_STORE_PATH
        p.write_text('["abc"]', encoding="utf-8")
        with patch("builtins.open", side_effect=OSError("permission denied")):
            assert read_ids() == set()

    def test_logs_error_when_open_raises_oserror(self, tmp_path, caplog):
        """Platform-independent: mock open() to raise OSError → error is logged."""
        import logging
        from unittest.mock import patch
        p = tmp_path / ID_STORE_PATH
        p.write_text('["abc"]', encoding="utf-8")
        with patch("builtins.open", side_effect=OSError("permission denied")):
            with caplog.at_level(logging.ERROR, logger="id_store"):
                read_ids()
        assert any("unreadable" in r.message.lower() for r in caplog.records)


class TestWriteIdsAtomicity:
    def test_original_file_untouched_when_os_replace_fails(self, tmp_path, monkeypatch):
        """If os.replace raises during write_ids, the original file must be unchanged."""
        from unittest.mock import patch
        from id_store import write_ids, ID_STORE_PATH

        # Arrange: create a valid existing store
        original_ids = ["existing1", "existing2", "existing3"]
        original_content = json.dumps(original_ids)
        (tmp_path / ID_STORE_PATH).write_text(original_content, encoding="utf-8")

        # Act: attempt to write new IDs but make os.replace fail
        new_ids = {"new1", "new2"}
        with patch("id_store.os.replace", side_effect=OSError("simulated replace failure")):
            write_ids(new_ids, list(new_ids))

        # Assert: original file content is unchanged
        result = (tmp_path / ID_STORE_PATH).read_text(encoding="utf-8")
        assert json.loads(result) == original_ids

    def test_logs_error_when_os_replace_fails(self, tmp_path, monkeypatch, caplog):
        """write_ids must log an error when os.replace raises."""
        import logging
        from unittest.mock import patch
        from id_store import write_ids

        (tmp_path / ID_STORE_PATH).write_text('["existing"]', encoding="utf-8")

        with patch("id_store.os.replace", side_effect=OSError("simulated replace failure")):
            with caplog.at_level(logging.ERROR, logger="id_store"):
                write_ids({"new1"}, ["new1"])

        assert any("failed to write" in r.message.lower() for r in caplog.records)


class TestReadIdsValid:
    def test_returns_correct_set_from_valid_array(self, tmp_path):
        ids = ["abc123", "def456", "ghi789"]
        (tmp_path / ID_STORE_PATH).write_text(json.dumps(ids), encoding="utf-8")
        assert read_ids() == set(ids)

    def test_returns_empty_set_from_empty_array(self, tmp_path):
        (tmp_path / ID_STORE_PATH).write_text("[]", encoding="utf-8")
        assert read_ids() == set()

    def test_returns_set_deduplicates_duplicates(self, tmp_path):
        ids = ["abc", "abc", "xyz"]
        (tmp_path / ID_STORE_PATH).write_text(json.dumps(ids), encoding="utf-8")
        assert read_ids() == {"abc", "xyz"}


# ---------------------------------------------------------------------------
# Property-based tests — P5: ID store round-trip integrity
# ---------------------------------------------------------------------------

# Feature: njuskalo-telegram-notifier, Property 5: ID store round-trip integrity

from hypothesis import given, settings
import hypothesis.strategies as st

from id_store import write_ids, MAX_STORE_SIZE

# Strategy: lists of text strings acting as IDs, up to 1000 entries
id_list_strategy = st.lists(
    st.text(min_size=1, max_size=64),
    min_size=0,
    max_size=MAX_STORE_SIZE,
)


class TestP5IdStoreRoundTripIntegrity:
    """
    **Validates: Requirements 4.3, 4.4**

    Property 5: For any list of ID strings (up to 1000 entries), writing them
    to the store and reading back SHALL produce a set equal to the original
    input.  The persisted file SHALL always be valid JSON after a write.
    """

    @given(ids=id_list_strategy)
    @settings(max_examples=100)
    def test_round_trip_returns_equal_set(self, ids):
        """Write a set of IDs then read back; the result must equal the written set."""
        ids_set = set(ids)
        # recently_added mirrors the ids list order (no cap needed here, len <= 1000)
        write_ids(ids_set, ids)
        result = read_ids()
        assert result == ids_set

    @given(ids=id_list_strategy)
    @settings(max_examples=100)
    def test_persisted_file_is_always_valid_json(self, ids):
        """After any write the on-disk file must be parseable as JSON."""
        ids_set = set(ids)
        write_ids(ids_set, ids)
        with open(ID_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)  # raises if invalid JSON
        # Sanity check: the file contains a list of strings
        assert isinstance(data, list)
        assert all(isinstance(item, str) for item in data)


# ---------------------------------------------------------------------------
# Property-based tests — P6: ID store size cap
# ---------------------------------------------------------------------------

# Feature: njuskalo-telegram-notifier, Property 6: ID store size cap

import string as _string

# Strategy: generate a fixed pool of unique IDs as zero-padded integers then
# sample a size > MAX_STORE_SIZE from that pool.  Using integer-derived strings
# avoids the slow unique-text generation that triggers Hypothesis HealthChecks.

def _make_oversized_id_list(draw):
    """Composite strategy: draw a list of > MAX_STORE_SIZE unique string IDs."""
    extra = draw(st.integers(min_value=1, max_value=200))
    total = MAX_STORE_SIZE + extra
    # Use zero-padded integer strings: guaranteed unique and fast to generate
    start = draw(st.integers(min_value=0, max_value=10_000))
    return [f"id{start + i:06d}" for i in range(total)]


oversized_ids_strategy = st.composite(_make_oversized_id_list)()


class TestP6IdStoreSizeCap:
    """
    **Validates: Requirements 4.7**

    Property 6: For any ID store that exceeds 1,000 entries, after writing
    the store to disk the file SHALL contain at most 1,000 entries, and those
    entries SHALL be the 1,000 most recently added IDs.
    """

    @given(ids=oversized_ids_strategy)
    @settings(max_examples=100)
    def test_written_file_contains_at_most_max_store_size_entries(self, ids):
        """After writing an oversized store, the file must contain at most MAX_STORE_SIZE entries."""
        ids_set = set(ids)
        # recently_added tracks all ids in insertion order
        write_ids(ids_set, ids)
        with open(ID_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) <= MAX_STORE_SIZE

    @given(ids=oversized_ids_strategy)
    @settings(max_examples=100)
    def test_written_file_contains_most_recently_added_ids(self, ids):
        """After writing an oversized store, the file SHALL contain the MAX_STORE_SIZE most recently added IDs."""
        ids_set = set(ids)
        # recently_added is the full list; the last MAX_STORE_SIZE entries are the most recent
        write_ids(ids_set, ids)
        with open(ID_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        stored_set = set(data)
        expected_ids = set(ids[-MAX_STORE_SIZE:])
        assert stored_set == expected_ids


# ---------------------------------------------------------------------------
# Property-based tests — P8: ID store accumulates on new-listing cycle
# ---------------------------------------------------------------------------

# Feature: njuskalo-telegram-notifier, Property 8: ID store accumulates on new-listing cycle


def _make_cycle_sets(draw):
    """
    Composite strategy: draw stored_ids and current_ids such that
    current_ids - stored_ids is non-empty (i.e. at least one new ID exists).
    """
    # Draw a base pool of IDs to share between stored and current
    shared = draw(st.frozensets(st.text(min_size=1, max_size=32), max_size=500))
    # Draw a non-empty set of new IDs that are definitely not in shared
    new_ids = draw(
        st.frozensets(
            st.text(min_size=1, max_size=32).filter(lambda x: x not in shared),
            min_size=1,
            max_size=200,
        )
    )
    stored_ids = set(shared)
    current_ids = set(shared) | set(new_ids)
    return stored_ids, current_ids


cycle_sets_strategy = st.composite(_make_cycle_sets)()


class TestP8IdStoreAccumulatesOnNewListingCycle:
    """
    **Validates: Requirements 6.5**

    Property 8: For any non-empty set of new_ids detected in a cycle, after
    the cycle completes the persisted ID store SHALL equal stored_ids ∪
    current_ids — IDs are never removed during a normal update.
    """

    @given(sets=cycle_sets_strategy)
    @settings(max_examples=100)
    def test_persisted_store_equals_union_after_cycle(self, sets):
        """After a cycle, read_ids() must return exactly stored_ids ∪ current_ids (subject to cap)."""
        stored_ids, current_ids = sets

        # Simulate the cycle: union = stored ∪ current
        union = stored_ids | current_ids
        # recently_added = only the genuinely new IDs (those not already stored)
        new_ids = list(current_ids - stored_ids)

        write_ids(union, new_ids)
        result = read_ids()

        if len(union) <= MAX_STORE_SIZE:
            # No cap needed — result must equal the full union
            assert result == union
        else:
            # Cap applies: result must be a subset of union and have MAX_STORE_SIZE entries
            assert result.issubset(union)
            assert len(result) == MAX_STORE_SIZE

    @given(sets=cycle_sets_strategy)
    @settings(max_examples=100)
    def test_stored_ids_are_never_removed_during_normal_update(self, sets):
        """IDs that were already stored must still be present after the cycle (subject to cap)."""
        stored_ids, current_ids = sets
        union = stored_ids | current_ids
        new_ids = list(current_ids - stored_ids)

        write_ids(union, new_ids)
        result = read_ids()

        if len(union) <= MAX_STORE_SIZE:
            # All stored IDs must survive
            assert stored_ids.issubset(result)
        else:
            # Cap applies — at least stored IDs that fit within the cap survive
            # The guarantee: result is still drawn from the correct pool
            assert result.issubset(union)
            assert len(result) == MAX_STORE_SIZE
