"""
Unit tests for monitor.py — task 16.1.

Covers:
  - Scraper exception              → cycle skipped (returns 0), no write
  - Parser returns []              → warning logged, no store write
  - First-run with listings        → IDs saved, no Discord notification, baseline logged
  - First-run with zero listings   → empty array written, retry message logged
  - KeyboardInterrupt in loop      → sys.exit(0)
  - Unhandled exception in cycle   → loop continues
"""

import logging
import sys
from unittest.mock import patch, MagicMock

import pytest

from monitor import run_cycle, main
from config import Config
from scraper_adapter import ScraperError
from parser_adapter import ParserError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(**kwargs):
    defaults = {
        "search_url": "https://www.njuskalo.hr/prodaja-stanova",
        "webhook_url": "https://discord.com/api/webhooks/123/abc",
        "check_interval_minutes": 1,
        "log_level": "DEBUG",
    }
    defaults.update(kwargs)
    return Config(**defaults)


def make_listing(listing_id="abc123"):
    return {
        "listing_id": listing_id,
        "title": "Test Title",
        "price": "100 EUR",
        "url": f"https://www.njuskalo.hr/oglas/{listing_id}",
    }


# ---------------------------------------------------------------------------
# Tests: Scraper exception → cycle skipped
# ---------------------------------------------------------------------------

class TestRunCycleScraperError:
    def test_scraper_exception_returns_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        with (
            patch("monitor.read_ids", return_value=set()),
            patch("monitor.fetch_html", side_effect=ScraperError("network down")),
            patch("monitor.write_ids") as mock_write,
        ):
            result = run_cycle(config)
        assert result == 0
        mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Parser returns [] → warning logged, no store write
# ---------------------------------------------------------------------------

class TestRunCycleParserReturnsEmpty:
    def test_parser_empty_returns_0_no_store_write(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        with (
            patch("monitor.read_ids", return_value={"old123"}),
            patch("monitor.fetch_html", return_value="<html>"),
            patch("monitor.parse_listings", return_value=[]),
            patch("monitor.write_ids") as mock_write,
        ):
            result = run_cycle(config)
        assert result == 0
        mock_write.assert_not_called()

    def test_parser_empty_logs_warning(self, tmp_path, monkeypatch, caplog):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        with (
            patch("monitor.read_ids", return_value={"old123"}),
            patch("monitor.fetch_html", return_value="<html>"),
            patch("monitor.parse_listings", return_value=[]),
            patch("monitor.write_ids"),
            caplog.at_level(logging.WARNING, logger="monitor"),
        ):
            run_cycle(config)
        assert any("zero listings" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests: First-run with listings → IDs saved, no Telegram, baseline logged
# ---------------------------------------------------------------------------

class TestRunCycleFirstRunWithListings:
    def test_first_run_saves_ids_no_telegram(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        listing = make_listing("new001")
        with (
            patch("monitor.read_ids", return_value=set()),
            patch("monitor.fetch_html", return_value="<html>"),
            patch("monitor.parse_listings", return_value=[listing]),
            patch("monitor.write_ids") as mock_write,
            patch("monitor.send_new_listings") as mock_notify,
        ):
            result = run_cycle(config)
        assert result == 0
        mock_write.assert_called_once()
        mock_notify.assert_not_called()

    def test_first_run_logs_baseline_message(self, tmp_path, monkeypatch, caplog):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        listing = make_listing("new001")
        with (
            patch("monitor.read_ids", return_value=set()),
            patch("monitor.fetch_html", return_value="<html>"),
            patch("monitor.parse_listings", return_value=[listing]),
            patch("monitor.write_ids"),
            patch("monitor.send_new_listings"),
            caplog.at_level(logging.INFO, logger="monitor"),
        ):
            run_cycle(config)
        messages = " ".join(r.message.lower() for r in caplog.records)
        assert "baseline" in messages or "first run" in messages


# ---------------------------------------------------------------------------
# Tests: First-run with zero listings → empty array written, retry logged
# ---------------------------------------------------------------------------

class TestRunCycleFirstRunWithZeroListings:
    def test_first_run_zero_listings_writes_empty_array(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        with (
            patch("monitor.read_ids", return_value=set()),
            patch("monitor.fetch_html", return_value="<html>"),
            patch("monitor.parse_listings", return_value=[]),
            patch("monitor.write_ids") as mock_write,
            patch("monitor.send_new_listings"),
        ):
            result = run_cycle(config)
        assert result == 0
        mock_write.assert_called_once_with(set(), [])

    def test_first_run_zero_listings_logs_retry_message(self, tmp_path, monkeypatch, caplog):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        with (
            patch("monitor.read_ids", return_value=set()),
            patch("monitor.fetch_html", return_value="<html>"),
            patch("monitor.parse_listings", return_value=[]),
            patch("monitor.write_ids"),
            patch("monitor.send_new_listings"),
            caplog.at_level(logging.INFO, logger="monitor"),
        ):
            run_cycle(config)
        messages = " ".join(r.message.lower() for r in caplog.records)
        assert "baseline" in messages or "retry" in messages or "zero" in messages


# ---------------------------------------------------------------------------
# Tests: KeyboardInterrupt → sys.exit(0)
# ---------------------------------------------------------------------------

class TestMainKeyboardInterrupt:
    def test_keyboard_interrupt_in_loop_exits_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        with (
            patch("monitor.load_config", return_value=config),
            patch("monitor.setup_logging"),
            patch("monitor.run_cycle", side_effect=KeyboardInterrupt),
            patch("monitor.time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Tests: Unhandled exception in cycle body → loop continues
# ---------------------------------------------------------------------------

class TestMainUnhandledExceptionContinues:
    def test_unhandled_exception_in_cycle_loop_continues(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = make_config()
        call_count = 0

        def side_effect_run_cycle(cfg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("unexpected failure")
            raise KeyboardInterrupt  # stop the loop after the second call

        with (
            patch("monitor.load_config", return_value=config),
            patch("monitor.setup_logging"),
            patch("monitor.run_cycle", side_effect=side_effect_run_cycle),
            patch("monitor.time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert call_count == 2
        assert exc_info.value.code == 0
