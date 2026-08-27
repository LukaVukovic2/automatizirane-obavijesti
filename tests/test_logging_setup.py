"""
Tests for logging_setup.setup_logging.

Task 14.1 — Property-based test (P11): log lines contain UTC ISO-8601 timestamp, severity, message
Task 14.2 — Example-based unit tests
"""

import io
import logging
import re

import hypothesis.strategies as st
from hypothesis import given, settings

from logging_setup import setup_logging

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Pattern for a valid log line: ISO-8601 UTC timestamp, Z suffix, level, message
_LOG_PATTERN = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\s+\w+\s+.+'
)

VALID_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _capture_log_output(log_level: str, message: str, level: int) -> str:
    """Set up logging with the given log_level, emit one message, capture output."""
    buf = io.StringIO()
    setup_logging(log_level)
    root = logging.getLogger()
    # Replace the handler's stream with our buffer for capture
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler):
            h.stream = buf
    root.log(level, "%s", message)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# P11: Log lines always contain UTC ISO-8601 timestamp, severity, and message
# Feature: njuskalo-telegram-notifier, Property 11: log lines always contain UTC ISO-8601 timestamp, severity, and message
# ---------------------------------------------------------------------------

_level_strategy = st.sampled_from([
    (name, getattr(logging, name)) for name in VALID_LEVELS
])

_message_strategy = st.text(min_size=1, max_size=200).filter(
    lambda s: "\n" not in s and "\r" not in s
)


@given(level_pair=_level_strategy, message=_message_strategy)
@settings(max_examples=200)
def test_log_line_contains_iso8601_utc_timestamp(level_pair, message):
    """Every log line must contain an ISO-8601 UTC timestamp ending in Z.

    **Validates: Requirements 9.1, 9.3**
    """
    level_name, level_int = level_pair
    output = _capture_log_output(level_name, message, level_int)
    if output:  # Only assert if the message was actually emitted
        assert re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', output), \
            f"No ISO-8601 UTC timestamp found in: {output!r}"


@given(level_pair=_level_strategy, message=_message_strategy)
@settings(max_examples=200)
def test_log_line_contains_severity_level(level_pair, message):
    """Every log line must contain the severity level name.

    **Validates: Requirements 9.1, 9.3**
    """
    level_name, level_int = level_pair
    output = _capture_log_output(level_name, message, level_int)
    if output:
        assert level_name in output, f"Level name {level_name!r} not found in: {output!r}"


@given(level_pair=_level_strategy, message=_message_strategy)
@settings(max_examples=200)
def test_log_line_contains_message_text(level_pair, message):
    """Every log line must contain the original message text.

    **Validates: Requirements 9.1, 9.3**
    """
    level_name, level_int = level_pair
    output = _capture_log_output(level_name, message, level_int)
    if output:
        assert message in output, f"Message {message!r} not found in: {output!r}"


# ---------------------------------------------------------------------------
# Task 14.2 — Example-based unit tests
# ---------------------------------------------------------------------------

class TestSetupLoggingDebugLevel:
    def test_debug_level_emits_debug_messages(self):
        """When LOG_LEVEL=DEBUG, DEBUG messages are emitted."""
        buf = io.StringIO()
        setup_logging("DEBUG")
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.stream = buf
        logging.debug("debug message here")
        assert "debug message here" in buf.getvalue()

    def test_info_level_suppresses_debug_messages(self):
        """When LOG_LEVEL=INFO, DEBUG messages are NOT emitted."""
        buf = io.StringIO()
        setup_logging("INFO")
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.stream = buf
        logging.debug("suppressed debug message")
        assert "suppressed debug message" not in buf.getvalue()


class TestSetupLoggingInvalidLevel:
    def test_invalid_log_level_falls_back_to_info(self):
        """An invalid LOG_LEVEL value should fall back to INFO."""
        setup_logging("INVALID_LEVEL")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_invalid_log_level_emits_warning(self):
        """An invalid LOG_LEVEL must emit a WARNING to the configured handler."""
        import sys
        buf = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = buf
        try:
            setup_logging("BOGUS")
        finally:
            sys.stdout = original_stdout
        output = buf.getvalue()
        # setup_logging installs a StreamHandler(sys.stdout) and then emits the
        # warning — so the warning lands in buf while sys.stdout is redirected.
        assert "WARNING" in output, f"Expected WARNING in output: {output!r}"

    def test_invalid_log_level_warning_content(self):
        """The warning message for an invalid LOG_LEVEL should mention the invalid value."""
        import sys
        buf = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = buf
        try:
            setup_logging("NOT_A_LEVEL")
        finally:
            sys.stdout = original_stdout
        output = buf.getvalue()
        assert "NOT_A_LEVEL" in output, \
            f"Expected invalid level name 'NOT_A_LEVEL' in warning: {output!r}"


class TestLogLineFormat:
    def test_log_line_format_is_correct(self):
        """A real log line should match the expected ISO-8601 UTC format."""
        buf = io.StringIO()
        setup_logging("INFO")
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.stream = buf
        logging.info("test message for format check")
        line = buf.getvalue().strip()
        assert _LOG_PATTERN.match(line), f"Log line does not match expected format: {line!r}"
        assert line.endswith("test message for format check")

    def test_log_line_ends_with_message(self):
        """The message text appears at the end of the formatted log line."""
        buf = io.StringIO()
        setup_logging("INFO")
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.stream = buf
        test_msg = "unique-sentinel-message-xyz"
        logging.info(test_msg)
        assert buf.getvalue().strip().endswith(test_msg)
