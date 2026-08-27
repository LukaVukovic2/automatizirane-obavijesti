"""
Property-based tests for listing_monitor.
Feature: njuskalo-discord-pipeline
"""

import json
import os
import tempfile
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from listing_monitor.config import ConfigError, load_config


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_valid_json(s: str) -> bool:
    """Return True iff *s* can be parsed as JSON without error."""
    try:
        json.loads(s)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Property 1: Invalid JSON config always rejected
# ---------------------------------------------------------------------------

# Feature: njuskalo-discord-pipeline, Property 1: Invalid JSON config always rejected
@given(st.text().filter(lambda s: not _is_valid_json(s)))
@settings(max_examples=100)
def test_invalid_json_config_raises(invalid_json: str) -> None:
    """
    **Validates: Requirements 1.4**

    For any string that is not valid JSON, load_config must raise ConfigError.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(invalid_json)
        tmp_path = tmp.name

    try:
        with pytest.raises(ConfigError):
            load_config(tmp_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Helpers for Property 2
# ---------------------------------------------------------------------------

_VALID_SEARCHER_ENTRY = {
    "id": "test-searcher",
    "name": "Test Searcher",
    "search_url": "https://www.njuskalo.hr/test",
    "discord_webhook_env": "PROP2_TEST_WEBHOOK",
}

_VALID_WEBHOOK_URL = "https://discord.com/api/webhooks/12345/test-token"


def _write_config_with_interval(interval: Any) -> str:
    """Write a config JSON with the given check_interval_minutes value to a temp file.
    Returns the temp file path. The caller is responsible for deleting it."""
    config = {
        "check_interval_minutes": interval,
        "searchers": [_VALID_SEARCHER_ENTRY],
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(config, tmp)
        return tmp.name


# ---------------------------------------------------------------------------
# Property 2: Out-of-range or non-integer check_interval_minutes always rejected
# ---------------------------------------------------------------------------

# Feature: njuskalo-discord-pipeline, Property 2: Out-of-range or non-integer check_interval_minutes always rejected
@given(st.integers().filter(lambda n: not (1 <= n <= 1440)))
@settings(max_examples=100)
def test_out_of_range_interval_raises(out_of_range_int: int) -> None:
    """
    **Validates: Requirements 1.6**

    For any integer outside [1, 1440], load_config must raise ConfigError.
    """
    tmp_path = _write_config_with_interval(out_of_range_int)
    try:
        os.environ["PROP2_TEST_WEBHOOK"] = _VALID_WEBHOOK_URL
        with pytest.raises(ConfigError):
            load_config(tmp_path)
    finally:
        os.environ.pop("PROP2_TEST_WEBHOOK", None)
        os.unlink(tmp_path)


# Feature: njuskalo-discord-pipeline, Property 2: Out-of-range or non-integer check_interval_minutes always rejected
@given(
    st.text().filter(
        lambda s: not s.strip().lstrip("-").isdigit()
    )
)
@settings(max_examples=100)
def test_non_integer_string_interval_raises(non_int_string: str) -> None:
    """
    **Validates: Requirements 1.6**

    For any string that is not parseable as an integer,
    load_config must raise ConfigError when used as check_interval_minutes.
    """
    tmp_path = _write_config_with_interval(non_int_string)
    try:
        os.environ["PROP2_TEST_WEBHOOK"] = _VALID_WEBHOOK_URL
        with pytest.raises(ConfigError):
            load_config(tmp_path)
    finally:
        os.environ.pop("PROP2_TEST_WEBHOOK", None)
        os.unlink(tmp_path)


# Feature: njuskalo-discord-pipeline, Property 2: Out-of-range or non-integer check_interval_minutes always rejected
@given(
    st.one_of(
        st.floats(allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.lists(st.integers()),
        st.dictionaries(st.text(), st.integers()),
        st.none(),
    )
)
@settings(max_examples=100)
def test_non_integer_type_interval_raises(non_int_value: Any) -> None:
    """
    **Validates: Requirements 1.6**

    For floats, booleans, lists, dicts, and None used as check_interval_minutes,
    load_config must raise ConfigError.
    """
    tmp_path = _write_config_with_interval(non_int_value)
    try:
        os.environ["PROP2_TEST_WEBHOOK"] = _VALID_WEBHOOK_URL
        with pytest.raises(ConfigError):
            load_config(tmp_path)
    finally:
        os.environ.pop("PROP2_TEST_WEBHOOK", None)
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Shared strategy helpers
# ---------------------------------------------------------------------------

def valid_searcher_strategy() -> st.SearchStrategy[dict]:
    """Generate a valid searcher dict with all required fields populated."""
    return st.fixed_dictionaries({
        "id": st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
            min_size=1,
            max_size=20,
        ),
        "name": st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        "search_url": st.just("https://www.njuskalo.hr/search"),
        "discord_webhook_env": st.just("DISCORD_WEBHOOK_TEST"),
    })


# ---------------------------------------------------------------------------
# Property 4: Duplicate Searcher IDs always rejected
# ---------------------------------------------------------------------------

# Feature: njuskalo-discord-pipeline, Property 4: Duplicate Searcher IDs always rejected
@given(st.lists(valid_searcher_strategy(), min_size=2, max_size=10))
@settings(max_examples=100)
def test_duplicate_searcher_ids_raises(searchers: list[dict]) -> None:
    """
    **Validates: Requirements 1.10**

    For any searchers array containing two or more entries that share the same
    id value, calling load_config SHALL raise ConfigError.
    """
    # Force a collision: set all entries to the same id as the first entry
    shared_id = searchers[0]["id"]
    for s in searchers:
        s["id"] = shared_id

    config_data = {
        "check_interval_minutes": 5,
        "searchers": searchers,
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(config_data, tmp)
        tmp_path = tmp.name

    # Provide a dummy env var so webhook resolution doesn't fail before the
    # duplicate-ID check (which happens earlier in load_config).
    env_patch = {"DISCORD_WEBHOOK_TEST": "https://discord.com/api/webhooks/test"}

    try:
        original_env = {k: os.environ.get(k) for k in env_patch}
        os.environ.update(env_patch)
        with pytest.raises(ConfigError):
            load_config(tmp_path)
    finally:
        # Restore environment
        for k, v in original_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A valid non-empty text that also strips to non-empty (no whitespace-only)
_non_empty_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
).filter(lambda s: s.strip() != "")

# A valid env-var name: uppercase letters, digits, underscores, must start with a letter/underscore
_env_var_name = st.from_regex(r"[A-Z][A-Z0-9_]{1,30}", fullmatch=True)

@st.composite
def valid_searcher_entry_strategy(draw) -> dict:
    """Draw a valid config-file Searcher entry (id, name, search_url, discord_webhook_env)."""
    return {
        "id": draw(_non_empty_text),
        "name": draw(_non_empty_text),
        "search_url": draw(_non_empty_text),
        "discord_webhook_env": draw(_env_var_name),
    }


# ---------------------------------------------------------------------------
# Property 5: Searcher objects correctly mapped from config entries
# ---------------------------------------------------------------------------

# Feature: njuskalo-discord-pipeline, Property 5: Searcher objects correctly mapped from config entries
@given(st.lists(valid_searcher_entry_strategy(), min_size=1, max_size=10))
@settings(max_examples=100)
def test_searcher_objects_correctly_mapped(entries: list) -> None:
    """
    **Validates: Requirements 2.1, 2.2**

    For any list of N valid Searcher entries in config.json, load_config SHALL produce
    exactly N Searcher frozen dataclass objects where each object's id, name, search_url,
    and webhook_url match the corresponding config entry and resolved environment variable.
    """
    # Ensure unique ids across entries (duplicate ids would cause ConfigError)
    seen_ids: set = set()
    for entry in entries:
        if entry["id"] in seen_ids:
            return  # skip examples with duplicate ids — they're tested in Property 4
        seen_ids.add(entry["id"])

    # Build a unique webhook URL for each entry and set it as an env var
    webhook_values = {
        entry["discord_webhook_env"]: f"https://discord.com/api/webhooks/{i}/token"
        for i, entry in enumerate(entries)
    }
    # If two entries share the same env var name, they'd resolve to the same URL — that's fine
    # but we need to be consistent: the last entry's env var name wins for shared names.
    # Actually each entry gets the same URL for the same env var name, which is valid.

    config_data = {
        "check_interval_minutes": 5,
        "searchers": entries,
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(config_data, tmp)
        tmp_path = tmp.name

    try:
        # Set all required env vars
        old_env: dict = {}
        for env_var, url in webhook_values.items():
            old_env[env_var] = os.environ.get(env_var)
            os.environ[env_var] = url

        try:
            result = load_config(tmp_path)
        finally:
            # Restore env vars
            for env_var, old_val in old_env.items():
                if old_val is None:
                    os.environ.pop(env_var, None)
                else:
                    os.environ[env_var] = old_val
    finally:
        os.unlink(tmp_path)

    # Assert exactly N Searcher objects
    assert len(result.searchers) == len(entries), (
        f"Expected {len(entries)} searchers, got {len(result.searchers)}"
    )

    # Assert each Searcher's fields match the config entry
    for i, (searcher, entry) in enumerate(zip(result.searchers, entries)):
        assert searcher.id == entry["id"], (
            f"Searcher {i}: id mismatch: {searcher.id!r} != {entry['id']!r}"
        )
        assert searcher.name == entry["name"], (
            f"Searcher {i}: name mismatch: {searcher.name!r} != {entry['name']!r}"
        )
        assert searcher.search_url == entry["search_url"], (
            f"Searcher {i}: search_url mismatch: {searcher.search_url!r} != {entry['search_url']!r}"
        )
        expected_webhook = webhook_values[entry["discord_webhook_env"]]
        assert searcher.webhook_url == expected_webhook, (
            f"Searcher {i}: webhook_url mismatch: {searcher.webhook_url!r} != {expected_webhook!r}"
        )


# ---------------------------------------------------------------------------
# Property 3: Missing or empty required Searcher fields always rejected
# ---------------------------------------------------------------------------

# Feature: njuskalo-discord-pipeline, Property 3: Missing or empty required Searcher fields always rejected

# Non-empty, non-whitespace-only text strategy for valid field values
_non_empty_text = st.text(min_size=1).filter(lambda s: s.strip() != "")

# Strategy that produces a value that is "bad": either absent (None sentinel)
# or an empty / whitespace-only string.
_bad_value = st.one_of(
    st.just(None),          # signals "absent" — we'll delete the key below
    st.just(""),
    st.text().filter(lambda s: s.strip() == ""),
)

_REQUIRED_FIELDS = ("id", "name", "search_url", "discord_webhook_env")


@st.composite
def _searcher_with_one_bad_field(draw: st.DrawFn) -> dict:
    """
    Draw a searcher dict that has all four required fields filled with valid
    values, then corrupt exactly one randomly chosen field (remove the key or
    replace its value with an empty/whitespace string).
    """
    # discord_webhook_env must be usable as an env var name (no null bytes,
    # since the OS rejects null characters in environment variable keys/values).
    _env_safe_text = st.text(
        min_size=1,
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    ).filter(lambda s: s.strip() != "")
    base = {
        "id": draw(_non_empty_text),
        "name": draw(_non_empty_text),
        "search_url": draw(_non_empty_text),
        "discord_webhook_env": draw(_env_safe_text),
    }
    bad_field = draw(st.sampled_from(_REQUIRED_FIELDS))
    bad_val = draw(_bad_value)
    if bad_val is None:
        del base[bad_field]
    else:
        base[bad_field] = bad_val
    return base


@given(bad_searcher=_searcher_with_one_bad_field())
@settings(max_examples=100)
def test_missing_or_empty_searcher_field_raises(bad_searcher: dict) -> None:
    """
    **Validates: Requirements 1.8, 1.9**

    For any Searcher object where at least one required field (id, name,
    search_url, discord_webhook_env) is absent or an empty/whitespace-only
    string, load_config SHALL raise ConfigError identifying the offending
    Searcher.
    """
    config_data = {
        "check_interval_minutes": 5,
        "searchers": [bad_searcher],
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(config_data, tmp)
        tmp_path = tmp.name

    # Provide a valid env var so validation doesn't fail for the wrong reason
    # (env-var resolution) *before* it reaches the field-presence check.
    # The field check runs first in load_config, so in practice this env var
    # will only be reached when the bad field happens to be discord_webhook_env
    # (which is tested separately by being absent/empty anyway).
    env_var_name = bad_searcher.get("discord_webhook_env", "DUMMY_WEBHOOK_ENV")
    # Guard against env var names that are invalid on the OS (contain '=', null
    # bytes, or are empty/whitespace-only).  When the generated value is already
    # bad the field-presence check in load_config will raise ConfigError before
    # the env-var resolution step, so using a dummy name is safe.
    def _is_valid_env_var_name(name: str) -> bool:
        return bool(name) and name.strip() != "" and "=" not in name and "\x00" not in name

    if not _is_valid_env_var_name(env_var_name):
        env_var_name = "DUMMY_WEBHOOK_ENV"

    old_val = os.environ.get(env_var_name)
    os.environ[env_var_name] = "https://discord.com/api/webhooks/test/token"

    try:
        with pytest.raises(ConfigError):
            load_config(tmp_path)
    finally:
        os.unlink(tmp_path)
        if old_val is None:
            os.environ.pop(env_var_name, None)
        else:
            os.environ[env_var_name] = old_val
