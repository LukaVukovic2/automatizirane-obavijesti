"""
monitor.py — Main entry point for the Njuškalo Discord Notifier.

Task 15.1: run_cycle(config: Config) -> int
Task 15.2: main()
"""

import logging
import random
import signal
import sys
import time
from datetime import datetime, timezone

from config import Config, ConfigError, load_config
from id_store import read_ids, write_ids
from scraper_adapter import ScraperError, fetch_html
from parser_adapter import ParserError, parse_listings
from detector import detect_new
from notifier import send_new_listings
from logging_setup import setup_logging

_log = logging.getLogger(__name__)


def run_cycle(config: Config) -> int:
    """
    Execute one scrape-detect-notify-persist cycle.
    Returns the count of new listings found (0 on error or no new listings).
    """
    cycle_start = datetime.now(timezone.utc)
    _log.info("Ciklus započinje")

    # 1. Read ID store
    stored_ids = read_ids()
    is_first_run = len(stored_ids) == 0

    # 2. Scrape
    try:
        html = fetch_html(config.search_url)
    except ScraperError as exc:
        _log.error("Scraper failed: %s", exc)
        return 0

    # 3. Parse
    try:
        listings = parse_listings(html)
    except ParserError as exc:
        _log.error("Parser failed: %s", exc)
        return 0

    # 4. First-run with zero listings (Req 5.3 / 5.4):
    #    Write explicit [] to mark first run completed; log and return 0.
    if is_first_run and not listings:
        write_ids(set(), [])
        _log.info(
            "Prvo izvršavanje: pronađeno nula oglasa; zapisan prazan baseline u ID store",
            "Nije moguće uspostaviti baseline - pokušaj u idućem ciklusu",
        )
        return 0

    # 5. Handle zero listings on a non-first-run cycle (Req 2.6 / 6.7):
    #    Log warning, skip ID store update, return 0.
    if not listings:
        _log.warning("Parser vraća nula oglasa; moguće promjene u layoutu websitea.")
        return 0

    # 6. First-run baseline with actual listings (Req 5.1 / 5.2):
    #    Save IDs, log baseline message, NO Telegram notify, return 0.
    if is_first_run:
        current_ids = [lst["listing_id"] for lst in listings]
        write_ids(set(current_ids), current_ids)
        _log.info(
            "Prvo izvršavanje: spremljeno %d baseline IDeva. Obavijesti će početi od idućeg izvršavanja.",
            len(current_ids),
        )
        return 0

    # 7. Detect new listings (Req 6.1 / 6.2)
    new_listings = detect_new(listings, stored_ids)

    if not new_listings:
        # Req 6.3: no new listings — log, skip ID store update
        _log.info("Nisu otkriveni novi oglasi.")
        cycle_end = datetime.now(timezone.utc)
        _log.info("Ciklus je uspješno završen")

        return 0

    _log.info("Broj otkrivenih oglasa: %d", len(new_listings))

    # 8. Write updated ID store BEFORE notifying — union of stored_ids ∪ current_ids (Req 6.5)
    # Persisting first ensures that even if the Discord call fails or the process
    # is interrupted, the IDs are recorded and we never re-notify for the same listing.
    current_ids = [lst["listing_id"] for lst in listings]
    new_ids = [lst["listing_id"] for lst in new_listings]
    union_ids = stored_ids | set(current_ids)
    write_ids(union_ids, new_ids)

    # 9. Notify (Req 7.1)
    send_new_listings(new_listings, config.webhook_url)

    cycle_end = datetime.now(timezone.utc)
    _log.info(
        "Ciklus je uspješno završen; novi oglasi: %d",
        len(new_listings),
    )
    return len(new_listings)


def main() -> None:
    """Entry point. Runs the polling loop indefinitely."""
    # Load and validate config; exit immediately on error (Req 1.2–1.6)
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config.log_level)

    # Register SIGTERM handler for clean shutdown (Req 8.3)
    def _handle_sigterm(signum, frame):
        _log.info("Zaprimljen SIGTERM; gašenje...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    _log.info(
        "Praćenje započelo. Interval provjere: %d min.", config.check_interval_minutes
    )

    # Polling loop (Req 8.1 / 8.2 / 8.6)
    try:
        while True:
            try:
                run_cycle(config)
            except Exception as exc:
                # Req 8.6: unhandled exception in loop body → log and continue
                _log.error(
                    "Unhandled exception in polling cycle: %s: %s",
                    type(exc).__name__,
                    exc,
                )
            # Sleep for the configured interval plus up to 20% random jitter
            # so requests don't land on a perfectly predictable schedule
            base_sleep = config.check_interval_minutes * 60
            jitter = random.uniform(0, base_sleep * 0.2)
            time.sleep(base_sleep + jitter)
    except KeyboardInterrupt:
        # Req 8.3: clean shutdown on Ctrl-C
        _log.info("Prekid izvršavanja skripte...")
        sys.exit(0)


if __name__ == "__main__":
    main()
