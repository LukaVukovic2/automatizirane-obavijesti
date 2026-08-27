"""
tests/test_config.py — Property-based tests for config.py.

**Validates: Requirements 1.1**
"""

import os
import string
from unittest.mock import patch

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

from config import ConfigError, load_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ENV = {
    "NJUSKALO_SEARCH_URL": "https://www.njuskalo.hr/iznajmljivanje-stanova?geo_id=1",
    "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/123456789/abcdefghijklmnop",
}


# ---------------------------------------------------------------------------
# Property 1: Whitespace-only env var values are treated as absent
# Feature: njuskalo-telegram-notifier, Property 1: whitespace env vars treated as absent
# ---------------------------------------------------------------------------

@given(st.text(alphabet=string.whitespace, min_size=1))
@settings(max_examples=100)
def test_whitespace_search_url_treated_as_absent(whitespace_value: str) -> None:
    """For any whitespace-only NJUSKALO_SEARCH_URL, load_config() must raise ConfigError."""
    env = {**_VALID_ENV, "NJUSKALO_SEARCH_URL": whitespace_value}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ConfigError):
            load_config()


@given(st.text(alphabet=string.whitespace, min_size=1))
@settings(max_examples=100)
def test_whitespace_webhook_url_treated_as_absent(whitespace_value: str) -> None:
    """For any whitespace-only DISCORD_WEBHOOK_URL, load_config() must raise ConfigError."""
    env = {**_VALID_ENV, "DISCORD_WEBHOOK_URL": whitespace_value}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ConfigError):
            load_config()


# ---------------------------------------------------------------------------
# Property 2: CHECK_INTERVAL_MINUTES boundary enforcement
# Feature: njuskalo-telegram-notifier, Property 2: CHECK_INTERVAL_MINUTES boundary enforcement
# ---------------------------------------------------------------------------

# **Validates: Requirements 1.6**

@given(st.integers().filter(lambda x: x < 1 or x > 1440))
@settings(max_examples=100)
def test_interval_out_of_range_raises_config_error(interval: int) -> None:
    """For any integer outside [1, 1440], load_config() must raise ConfigError."""
    env = {**_VALID_ENV, "CHECK_INTERVAL_MINUTES": str(interval)}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ConfigError):
            load_config()


@given(st.integers(min_value=1, max_value=1440))
@settings(max_examples=100)
def test_interval_in_range_accepted(interval: int) -> None:
    """For any integer in [1, 1440], load_config() must accept it and set check_interval_minutes."""
    env = {**_VALID_ENV, "CHECK_INTERVAL_MINUTES": str(interval)}
    with patch.dict(os.environ, env, clear=True):
        config = load_config()
        assert config.check_interval_minutes == interval


# ---------------------------------------------------------------------------
# Example-based unit tests (Task 3.3)
# **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**
# ---------------------------------------------------------------------------

class TestMissingRequiredVars:
    """Each missing required variable must raise ConfigError."""

    def test_missing_search_url_raises_config_error(self) -> None:
        """NJUSKALO_SEARCH_URL absent → ConfigError."""
        env = {
            "DISCORD_WEBHOOK_URL": _VALID_ENV["DISCORD_WEBHOOK_URL"],
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError):
                load_config()

    def test_missing_webhook_url_raises_config_error(self) -> None:
        """DISCORD_WEBHOOK_URL absent → ConfigError."""
        env = {
            "NJUSKALO_SEARCH_URL": _VALID_ENV["NJUSKALO_SEARCH_URL"],
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError):
                load_config()


class TestDefaultInterval:
    """CHECK_INTERVAL_MINUTES absent → default value of 5."""

    def test_absent_interval_defaults_to_5(self) -> None:
        """When CHECK_INTERVAL_MINUTES is not set, check_interval_minutes must be 5."""
        with patch.dict(os.environ, _VALID_ENV, clear=True):
            config = load_config()
            assert config.check_interval_minutes == 5


class TestLogLevelFallback:
    """LOG_LEVEL handling: invalid falls back to INFO, valid values are accepted."""

    def test_invalid_log_level_falls_back_to_info(self) -> None:
        """An unrecognised LOG_LEVEL (e.g. 'VERBOSE') must not raise and must resolve to 'INFO'."""
        env = {**_VALID_ENV, "LOG_LEVEL": "VERBOSE"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.log_level == "INFO"

    def test_valid_log_level_debug_accepted(self) -> None:
        """LOG_LEVEL='DEBUG' is a valid value and must be stored as-is."""
        env = {**_VALID_ENV, "LOG_LEVEL": "DEBUG"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.log_level == "DEBUG"

    def test_valid_log_level_warning_accepted(self) -> None:
        """LOG_LEVEL='WARNING' is a valid value and must be stored as-is."""
        env = {**_VALID_ENV, "LOG_LEVEL": "WARNING"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.log_level == "WARNING"

    def test_valid_log_level_error_accepted(self) -> None:
        """LOG_LEVEL='ERROR' is a valid value and must be stored as-is."""
        env = {**_VALID_ENV, "LOG_LEVEL": "ERROR"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.log_level == "ERROR"

    def test_valid_log_level_critical_accepted(self) -> None:
        """LOG_LEVEL='CRITICAL' is a valid value and must be stored as-is."""
        env = {**_VALID_ENV, "LOG_LEVEL": "CRITICAL"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.log_level == "CRITICAL"
