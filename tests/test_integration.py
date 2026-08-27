"""
tests/test_integration.py — integration tests for the listing_monitor pipeline.

These tests exercise real file I/O with the actual config.json and .env files
present on disk.  They are excluded from the default pytest run and must be
invoked explicitly:

    pytest -m integration

Each test is skipped automatically if the required files are absent, or if the
webhook environment variables defined in config.json are not populated in .env,
so that CI environments without secrets do not fail.
"""

import json
import os

import pytest

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.json")
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")

_missing_config = not os.path.exists(_CONFIG_PATH)
_missing_env = not os.path.exists(_ENV_PATH)

pytestmark = pytest.mark.integration

_skip_if_no_files = pytest.mark.skipif(
    _missing_config or _missing_env,
    reason="Skipped: config.json or .env is absent",
)


# ---------------------------------------------------------------------------
# Integration test 1: load_config with real files
# ---------------------------------------------------------------------------

@_skip_if_no_files
def test_load_config_with_real_files():
    """
    load_config() reads the real config.json and resolves env vars from the
    real .env file.  Verifies that a PipelineConfig is returned with at least
    one Searcher, a valid interval, and that every Searcher has non-empty fields.

    Skipped automatically when the Discord webhook env vars declared in
    config.json are absent from .env (expected in dev environments that have
    not been fully configured for the multi-searcher pipeline).
    """
    from listing_monitor.config import load_config, ConfigError, PipelineConfig, Searcher

    try:
        # load_config calls load_dotenv() internally — real .env is on disk
        config = load_config(_CONFIG_PATH)
    except ConfigError as exc:
        # If the only reason we can't load is missing webhook env vars, skip
        # rather than fail — the test environment is simply not fully configured.
        pytest.skip(f"load_config raised ConfigError (env vars not set?): {exc}")

    assert isinstance(config, PipelineConfig)
    assert 1 <= config.check_interval_minutes <= 1440
    assert len(config.searchers) >= 1

    for searcher in config.searchers:
        assert isinstance(searcher, Searcher)
        assert searcher.id.strip()
        assert searcher.name.strip()
        assert searcher.search_url.strip()
        assert searcher.webhook_url.strip()


# ---------------------------------------------------------------------------
# Integration test 2: read_store + write_store round-trip on a temp file
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_read_write_store_round_trip(tmp_path):
    """
    write_store() followed by read_store() on the same temp file preserves the
    searcher-keyed structure (modulo the 1,000-ID cap).

    This test does NOT require config.json or .env — it only exercises the
    state module's file I/O.
    """
    from listing_monitor.state import read_store, write_store

    store_path = str(tmp_path / "test_store.json")

    original_store = {
        "apartments": ["id1", "id2", "id3"],
        "houses": ["id4", "id5"],
        "studios": [],
    }

    write_store(original_store, path=store_path)
    loaded_store = read_store(path=store_path)

    # Top-level keys must match
    assert set(loaded_store.keys()) == set(original_store.keys())

    # Each searcher's list must match in order and content
    for searcher_id, expected_ids in original_store.items():
        assert loaded_store[searcher_id] == expected_ids, (
            f"Mismatch for searcher {searcher_id!r}: "
            f"expected {expected_ids!r}, got {loaded_store[searcher_id]!r}"
        )


@pytest.mark.integration
def test_read_write_store_round_trip_large(tmp_path):
    """
    When a searcher has more than 1,000 IDs, write_store enforces the cap and
    read_store returns at most 1,000 IDs for that searcher (most recent retained).
    """
    from listing_monitor.state import read_store, write_store, MAX_IDS_PER_SEARCHER

    store_path = str(tmp_path / "test_store_large.json")

    # Build a store with 1,200 IDs for one searcher and a small list for another
    large_ids = [f"listing-{i:04d}" for i in range(1200)]
    small_ids = ["a", "b", "c"]

    original_store = {
        "big_searcher": large_ids,
        "small_searcher": small_ids,
    }

    write_store(original_store, path=store_path)
    loaded_store = read_store(path=store_path)

    # The capped searcher should have at most MAX_IDS_PER_SEARCHER entries
    assert len(loaded_store["big_searcher"]) == MAX_IDS_PER_SEARCHER
    # The cap retains the MOST RECENT (last) entries
    assert loaded_store["big_searcher"] == large_ids[-MAX_IDS_PER_SEARCHER:]

    # The small searcher is unaffected
    assert loaded_store["small_searcher"] == small_ids


@pytest.mark.integration
def test_read_store_absent_file(tmp_path):
    """
    read_store() returns {} when the target file does not exist.
    """
    from listing_monitor.state import read_store

    nonexistent_path = str(tmp_path / "nonexistent.json")
    result = read_store(path=nonexistent_path)
    assert result == {}


@pytest.mark.integration
def test_write_store_creates_valid_json(tmp_path):
    """
    write_store() creates a valid JSON file that can be parsed independently
    of read_store — verifying the file format itself.
    """
    from listing_monitor.state import write_store

    store_path = str(tmp_path / "direct_check.json")

    store = {"searcher_a": ["x1", "x2"], "searcher_b": ["y1"]}
    write_store(store, path=store_path)

    assert os.path.exists(store_path)
    with open(store_path, encoding="utf-8") as f:
        raw = json.load(f)

    assert raw == store


@pytest.mark.integration
def test_write_store_atomic_no_tmp_leftover(tmp_path):
    """
    After write_store() completes successfully, the sibling .tmp file
    should not be present (os.replace moved it into place).
    """
    from listing_monitor.state import write_store

    store_path = str(tmp_path / "atomic.json")
    tmp_file = store_path + ".tmp"

    write_store({"s": ["1", "2", "3"]}, path=store_path)

    assert os.path.exists(store_path), "Final store file should exist"
    assert not os.path.exists(tmp_file), ".tmp file should be gone after atomic replace"
