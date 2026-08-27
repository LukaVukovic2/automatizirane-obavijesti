"""
listing_monitor/monitor.py — Polling loop and per-searcher monitoring cycle.

Entry point: python -m listing_monitor.monitor  OR  python listing_monitor/monitor.py
"""

from __future__ import annotations

import logging
import os

from scraper_adapter import fetch_html, ScraperError
from parser_adapter import parse_listings, ParserError
from detector import detect_new
from listing_monitor.state import get_ids_for_searcher, update_store_for_searcher, Store
from listing_monitor.discord import send_discord
from listing_monitor.config import Searcher, PipelineConfig

_log = logging.getLogger(__name__)


def check_searcher(searcher: Searcher, store: Store) -> Store:
    """
    Execute one scrape-detect-notify cycle for a single Searcher.

    Returns an updated Store (the input store is not mutated).
    All exceptions from fetch_html and parse_listings are caught and logged;
    the original store is returned unchanged on any failure.

    Internal flow (12 steps):
    1.  Resolve stored IDs for this searcher.
    2.  Detect first-run (searcher.id absent from store).
    3.  Fetch HTML — ScraperError → log + return original store.
    4.  Parse listings — ParserError → log + return original store.
    5.  Zero listings → log warning + return original store (no ID update).
    6.  First-run → save baseline IDs, log, NO Discord calls, return updated store.
    7.  Detect new listings via detect_new.
    8.  No new listings → log + return original store.
    9.  Log count of new listings.
    10. For each new listing: send_discord; on success, update store.
    11. Return the (possibly incrementally updated) store.
    12. Bare Exception catch-all → log type, message, and searcher name, return original store.
    """
    try:
        # Step 1 — stored IDs for this searcher
        stored_ids = get_ids_for_searcher(store, searcher.id)

        # Step 2 — first-run detection
        is_first_run = searcher.id not in store

        # Step 3 — fetch HTML
        try:
            html = fetch_html(searcher.search_url)
        except ScraperError as exc:
            _log.error("ScraperError za searchera %r: %s", searcher.name, exc)
            return store

        # Step 4 — parse listings
        try:
            listings = parse_listings(html)
        except ParserError as exc:
            _log.error("ParserError za searchera %r: %s", searcher.name, exc)
            return store

        # Step 5 — zero listings
        if not listings:
            _log.warning("Nema oglasa za searchera %r - preskakanje ažuriranja ID storea", searcher.name)
            return store

        # Step 6 — first-run baseline
        if is_first_run:
            updated_store = store
            all_current_ids = [listing["listing_id"] for listing in listings]
            for listing in listings:
                updated_store = update_store_for_searcher(
                    updated_store,
                    searcher.id,
                    listing["listing_id"],
                    all_current_ids,
                )
            _log.info(
                "Prvo izvršavanje za searchera %r - spremljeno %d baseline IDeva, bez slanja obavijesti",
                searcher.name,
                len(listings),
            )
            return updated_store

        # Step 7 — detect new listings
        new_listings = detect_new(listings, stored_ids)

        # Step 8 — no new listings
        if not new_listings:
            _log.info("Nema novih oglasa za %r", searcher.name)
            return store

        # Step 9 — log count
        _log.info("Pronađeno novih oglasa: %d za searcher %r", len(new_listings), searcher.name)

        # Step 10 — notify and update store per successful post
        all_current_ids = [listing["listing_id"] for listing in listings]
        updated_store = store
        for listing in new_listings:
            success = send_discord(searcher, listing)
            if success:
                updated_store = update_store_for_searcher(
                    updated_store,
                    searcher.id,
                    listing["listing_id"],
                    all_current_ids,
                )

        # Step 11 — return the incrementally updated store
        return updated_store

    # Step 12 — catch-all for unexpected errors
    except Exception as exc:
        _log.error(
            "Neočekivani %s u check_searcheru za %r: %s",
            type(exc).__name__,
            searcher.name,
            exc,
        )
        return store


def run_cycle(config: PipelineConfig, store: Store) -> Store:
    """
    Call check_searcher for every Searcher in config order.
    Returns the cumulative updated Store.
    """
    for searcher in config.searchers:
        store = check_searcher(searcher, store)
    return store


def main() -> None:
    """
    Load config, set up logging, install signal handlers, run polling loop.
    """
    import signal
    import sys
    import time
    import random

    from listing_monitor.config import load_config, ConfigError
    from listing_monitor.state import read_store, write_store

    # Resolve log level from environment (load_config calls load_dotenv internally,
    # but LOG_LEVEL may also be set directly in the shell environment).
    log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    # Attempt to reuse root-level logging setup if available
    try:
        from logging_setup import setup_logging  # type: ignore[import]
        setup_logging(log_level)
    except ImportError:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Load config — exit with code 1 on failure
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    _log.info(
        "Učitan config: %d searcher(s), interval=%d min",
        len(config.searchers),
        config.check_interval_minutes,
    )

    # SIGTERM handler
    def _handle_sigterm(signum: int, frame: object) -> None:
        _log.info("Received SIGTERM — shutting down")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    # Polling loop
    while True:
        try:
            store = read_store()
            store = run_cycle(config, store)
            write_store(store)
        except KeyboardInterrupt:
            _log.info("KeyboardInterrupt received — shutting down")
            sys.exit(0)
        except Exception as exc:
            _log.error(
                "Neočekivani %s u petlji: %s - nastavak na idući ciklus",
                type(exc).__name__,
                exc,
            )

        sleep_seconds = config.check_interval_minutes * 60 + random.uniform(0, 30)
        _log.info("Vrijeme do idućeg ciklusa %.0fs", sleep_seconds)
        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            _log.info("Prekid izvršavanja skripte...")
            sys.exit(0)


if __name__ == "__main__":
    main()
