import logging
import time
from datetime import datetime

import requests

from parser_adapter import Listing

DISCORD_WEBHOOK_MAX_LENGTH = 2000  # Discord's content field limit
MAX_MESSAGE_LENGTH = 2000
RETRY_DELAY_SECONDS = 5

_log = logging.getLogger(__name__)


def _format_listing(listing: Listing) -> str:
    """Format a single listing for a Discord message."""
    lines = ["🏠 NOVI NJUŠKALO OGLAS"]
    lines.append(f"Naslov: {listing.get('title', '')}")
    lines.append(f"Cijena: {listing.get('price', '')}")
    for field, label in (("area", "Area"), ("rooms", "Rooms"), ("location", "Lokacija")):
        value = listing.get(field)
        if value:
            lines.append(f"{label}: {value}")
    lines.append(listing.get("url", ""))
    lines.append(f"Otkriveno: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def _batch_listings(listings: list[Listing]) -> list[str]:
    """Batch formatted listings into chunks of at most MAX_MESSAGE_LENGTH chars."""
    separator = "\n\n"
    batches = []
    current_parts: list[str] = []
    current_len = 0

    for listing in listings:
        formatted = _format_listing(listing)
        # Length if we add this listing to the current batch
        addition_len = (len(separator) if current_parts else 0) + len(formatted)

        if current_parts and current_len + addition_len > MAX_MESSAGE_LENGTH:
            # Flush the current batch
            batches.append(separator.join(current_parts))
            current_parts = [formatted]
            current_len = len(formatted)
        else:
            current_parts.append(formatted)
            current_len += addition_len

    if current_parts:
        batches.append(separator.join(current_parts))

    return batches


def send_new_listings(listings: list[Listing], webhook_url: str) -> None:
    """Send Discord messages for the given new listings via webhook."""
    batches = _batch_listings(listings)

    for batch in batches:
        payload = {"content": batch}
        _send_with_retry(webhook_url, payload)


def _send_with_retry(url: str, payload: dict) -> None:
    """Send a single POST request, retrying once on non-2xx response."""
    for attempt in range(2):
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.ok:
                return
            _log.error(
                "Discord webhook returned non-2xx status %d: %s",
                response.status_code,
                response.text[:200],
            )
            if attempt == 0:
                _log.info("Retrying after %d seconds...", RETRY_DELAY_SECONDS)
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                _log.error("Final failure sending Discord message after retry.")
        except requests.RequestException as exc:
            _log.error("Network error sending Discord message: %s", exc)
            return
