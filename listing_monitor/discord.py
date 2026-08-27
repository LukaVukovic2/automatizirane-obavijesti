"""
listing_monitor/discord.py — Discord embed builder and webhook notifier.

Provides build_embed() for constructing Discord embed payloads from Listing
dicts, and send_discord() for posting them to a webhook URL.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from parser_adapter import Listing

if TYPE_CHECKING:
    from listing_monitor.config import Searcher

_log = logging.getLogger(__name__)

EMBED_COLOR = 3447003  # Discord blue


class DiscordError(Exception):
    """Wraps HTTP or network failure from a Discord webhook call."""


def build_embed(listing: Listing) -> dict:
    """
    Build a Discord embed dict from a Listing.

    The embed always includes:
      - title: listing["title"] (links to listing["url"])
      - color: 3447003

    Fields included:
      - "Cijena" (price) — always included when non-empty
      - "Površina" (area)   — only when non-empty
      - "Sobe" (rooms)      — only when non-empty
      - "Lokacija" (location) — only when non-empty

    Returns a plain dict suitable for JSON serialisation.
    """
    embed: dict = {
        "title": listing["title"],
        "url": listing["url"],
        "color": EMBED_COLOR,
        "fields": [],
    }

    # Price — always included when non-empty
    price = listing.get("price", "")
    if price:
        embed["fields"].append({"name": "Cijena", "value": price, "inline": True})

    # Optional fields — included only when non-empty strings
    area = listing.get("area", "")
    if area:
        embed["fields"].append({"name": "Površina", "value": area, "inline": True})

    rooms = listing.get("rooms", "")
    if rooms:
        embed["fields"].append({"name": "Sobe", "value": rooms, "inline": True})

    location = listing.get("location", "")
    if location:
        embed["fields"].append({"name": "Lokacija", "value": location, "inline": False})

    return embed


def send_discord(searcher: "Searcher", listing: Listing) -> bool:
    """
    POST one embed to searcher.webhook_url.

    Returns True on 2xx, False on non-2xx or network error.
    Logs the HTTP status code and truncated response body on failure.
    Does NOT raise; callers check the boolean return value.
    """
    import requests  # imported here to keep the module importable without requests installed

    payload = {"embeds": [build_embed(listing)]}

    try:
        response = requests.post(
            searcher.webhook_url,
            json=payload,
            timeout=10,
        )
    except requests.RequestException as exc:
        _log.error(
            "Discord webhook network error for searcher %r (listing %r): %s",
            searcher.name,
            listing.get("listing_id"),
            exc,
        )
        return False

    if 200 <= response.status_code < 300:
        return True

    body_preview = response.text[:200] if response.text else ""
    _log.error(
        "Discord webhook returned HTTP %d for searcher %r (listing %r): %s",
        response.status_code,
        searcher.name,
        listing.get("listing_id"),
        body_preview,
    )
    return False
