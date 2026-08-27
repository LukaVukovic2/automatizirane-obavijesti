"""
config.py — Configuration loader for the Njuškalo Discord Notifier.

Task 2.1: Config frozen dataclass
Task 2.2: ConfigError exception class
Task 2.3: load_config() factory function
"""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Immutable value object holding all validated runtime configuration.

    Fields
    ------
    search_url : str
        Fully-qualified Njuškalo search URL (NJUSKALO_SEARCH_URL env var).
    webhook_url : str
        Discord incoming webhook URL (DISCORD_WEBHOOK_URL env var).
    check_interval_minutes : int
        Polling interval in minutes; always in the inclusive range [1, 1440]
        (CHECK_INTERVAL_MINUTES env var, default 5).
    log_level : str
        Python logging level name; always one of DEBUG / INFO / WARNING /
        ERROR / CRITICAL (LOG_LEVEL env var, default "INFO").
    """

    search_url: str
    webhook_url: str
    check_interval_minutes: int  # always in [1, 1440]
    log_level: str               # always one of DEBUG/INFO/WARNING/ERROR/CRITICAL


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when required config is missing or invalid."""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

_logger = logging.getLogger(__name__)


def load_config() -> Config:
    """Load configuration from environment (with python-dotenv .env support).

    Validation rules (applied in order):
    1. Load `.env` via python-dotenv.
    2. Strip each env var value; treat empty-after-strip as absent (None).
    3. Require NJUSKALO_SEARCH_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID —
       raise ConfigError if absent or empty.
    4. CHECK_INTERVAL_MINUTES defaults to 5; if present must be an int in
       [1, 1440]; raise ConfigError if unparseable or out of range.
    5. LOG_LEVEL defaults to "INFO"; if present and not in the valid set,
       log a warning and fall back to "INFO".

    Raises
    ------
    ConfigError
        If any required variable is absent/empty, or CHECK_INTERVAL_MINUTES
        is present but invalid.
    """
    load_dotenv()

    def _get(name: str) -> str | None:
        """Return stripped env var value, or None if absent/whitespace-only."""
        raw = os.environ.get(name)
        if raw is None:
            return None
        stripped = raw.strip()
        return stripped if stripped else None

    # --- Required variables -------------------------------------------------
    search_url = _get("NJUSKALO_SEARCH_URL")
    if not search_url:
        raise ConfigError(
            "NJUSKALO_SEARCH_URL is required but was not set or is empty."
        )

    webhook_url = _get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise ConfigError(
            "DISCORD_WEBHOOK_URL is required but was not set or is empty."
        )

    # --- Optional: CHECK_INTERVAL_MINUTES -----------------------------------
    interval_raw = _get("CHECK_INTERVAL_MINUTES")
    if interval_raw is None:
        check_interval_minutes = 5
    else:
        try:
            check_interval_minutes = int(interval_raw)
        except ValueError:
            raise ConfigError(
                f"CHECK_INTERVAL_MINUTES must be an integer, got: {interval_raw!r}"
            )
        if not (1 <= check_interval_minutes <= 1440):
            raise ConfigError(
                f"CHECK_INTERVAL_MINUTES must be in [1, 1440], got: {check_interval_minutes}"
            )

    # --- Optional: LOG_LEVEL ------------------------------------------------
    log_level_raw = _get("LOG_LEVEL")
    if log_level_raw is None:
        log_level = "INFO"
    else:
        candidate = log_level_raw.upper()
        if candidate in _VALID_LOG_LEVELS:
            log_level = candidate
        else:
            _logger.warning(
                "LOG_LEVEL %r is not valid; falling back to INFO. "
                "Valid values: %s",
                log_level_raw,
                ", ".join(sorted(_VALID_LOG_LEVELS)),
            )
            log_level = "INFO"

    return Config(
        search_url=search_url,
        webhook_url=webhook_url,
        check_interval_minutes=check_interval_minutes,
        log_level=log_level,
    )
