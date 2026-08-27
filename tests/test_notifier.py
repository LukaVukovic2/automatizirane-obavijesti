"""
tests/test_notifier.py — Unit and property-based tests for notifier.py.

Property tests:
  P9  — Message batches respect the 2000-character limit (Discord webhook)
  P10 — Listing message format omits absent/null optional fields

Example-based tests:
  - Non-2xx response triggers one retry after RETRY_DELAY_SECONDS
  - Network error (RequestException) does not crash; function returns
  - payload uses 'content' field (not 'text' or parse_mode)
"""

from __future__ import annotations

import string
from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

from notifier import (
    MAX_MESSAGE_LENGTH,
    RETRY_DELAY_SECONDS,
    _batch_listings,
    _format_listing,
    send_new_listings,
)
from parser_adapter import Listing


# ---------------------------------------------------------------------------
# Helpers / strategies
# ---------------------------------------------------------------------------

def _make_listing(
    *,
    listing_id: str = "abc123",
    title: str = "Test Listing",
    price: str = "1000 €",
    url: str = "https://www.njuskalo.hr/oglas/abc123",
    area: Optional[str] = None,
    rooms: Optional[str] = None,
    location: Optional[str] = None,
) -> Listing:
    listing: Listing = {
        "listing_id": listing_id,
        "title": title,
        "price": price,
        "url": url,
    }
    if area is not None:
        listing["area"] = area
    if rooms is not None:
        listing["rooms"] = rooms
    if location is not None:
        listing["location"] = location
    return listing


# Strategy: printable text for field values (avoid control chars that would confuse length)
_printable = st.text(alphabet=string.printable, min_size=0, max_size=200)

# Strategy: a single Listing with varied optional fields
_listing_strategy = st.fixed_dictionaries(
    {
        "listing_id": st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20),
        "title": _printable,
        "price": _printable,
        "url": st.just("https://www.njuskalo.hr/oglas/test123"),
    },
    optional={
        "area": _printable.filter(bool),
        "rooms": _printable.filter(bool),
        "location": _printable.filter(bool),
    },
)


# ---------------------------------------------------------------------------
# Property 9: Message batches respect the 4096-character limit
# Feature: njuskalo-telegram-notifier, Property 9: batches respect 4096-char limit
# **Validates: Requirements 7.2**
# ---------------------------------------------------------------------------

@given(st.lists(_listing_strategy, min_size=0, max_size=30))
@settings(max_examples=200)
def test_batches_respect_max_message_length(listings: list) -> None:
    """
    For any list of listings, every batch produced by _batch_listings must be
    at most MAX_MESSAGE_LENGTH characters long.
    """
    batches = _batch_listings(listings)
    for batch in batches:
        assert len(batch) <= MAX_MESSAGE_LENGTH, (
            f"Batch length {len(batch)} exceeds {MAX_MESSAGE_LENGTH}:\n{batch[:200]}…"
        )


@given(st.lists(_listing_strategy, min_size=0, max_size=30))
@settings(max_examples=200)
def test_batches_contain_all_listings(listings: list) -> None:
    """
    Every listing that goes in must appear in exactly one batch (no listing is
    dropped or duplicated). We verify by counting the header line occurrences.
    """
    header = "🏠 NEW NJUŠKALO LISTING"
    batches = _batch_listings(listings)
    total_headers = sum(batch.count(header) for batch in batches)
    assert total_headers == len(listings)


@given(st.lists(_listing_strategy, min_size=2, max_size=30))
@settings(max_examples=100)
def test_batches_never_split_mid_listing(listings: list) -> None:
    """
    No listing entry should be split across two batches. Each batch must be a
    well-formed concatenation of complete formatted listings.
    """
    header = "🏠 NEW NJUŠKALO LISTING"
    batches = _batch_listings(listings)
    for batch in batches:
        # The batch must start with the header (leading entry starts the chunk)
        assert batch.startswith(header), f"Batch does not start with listing header:\n{batch[:100]}"


# ---------------------------------------------------------------------------
# Property 10: Listing message format omits absent/null optional fields
# Feature: njuskalo-telegram-notifier, Property 10: format omits absent fields
# **Validates: Requirements 7.3**
# ---------------------------------------------------------------------------

@given(
    has_area=st.booleans(),
    has_rooms=st.booleans(),
    has_location=st.booleans(),
    area_val=_printable.filter(bool),
    rooms_val=_printable.filter(bool),
    location_val=_printable.filter(bool),
)
@settings(max_examples=200)
def test_format_omits_absent_optional_fields(
    has_area: bool,
    has_rooms: bool,
    has_location: bool,
    area_val: str,
    rooms_val: str,
    location_val: str,
) -> None:
    """
    For any combination of optional fields being present or absent, _format_listing
    must include labels for present fields and omit labels for absent ones.
    """
    listing = _make_listing(
        area=area_val if has_area else None,
        rooms=rooms_val if has_rooms else None,
        location=location_val if has_location else None,
    )
    formatted = _format_listing(listing)

    if has_area:
        assert "Area:" in formatted
    else:
        assert "Area:" not in formatted

    if has_rooms:
        assert "Rooms:" in formatted
    else:
        assert "Rooms:" not in formatted

    if has_location:
        assert "Location:" in formatted
    else:
        assert "Location:" not in formatted


@pytest.mark.parametrize("field,label", [("area", "Area"), ("rooms", "Rooms"), ("location", "Location")])
def test_empty_string_optional_field_omitted(field: str, label: str) -> None:
    """An optional field set to empty string must be omitted from the formatted output."""
    listing = _make_listing(**{field: ""})  # type: ignore[arg-type]
    formatted = _format_listing(listing)
    assert f"{label}:" not in formatted


def test_format_required_fields_always_present() -> None:
    """Title, Price, URL, and Detected must always appear regardless of optional fields."""
    listing = _make_listing()
    formatted = _format_listing(listing)
    assert "🏠 NEW NJUŠKALO LISTING" in formatted
    assert "Title:" in formatted
    assert "Price:" in formatted
    assert listing["url"] in formatted
    assert "Detected:" in formatted


def test_format_detected_is_iso8601() -> None:
    """The Detected line must contain an ISO-8601 timestamp (basic format check)."""
    import re
    listing = _make_listing()
    formatted = _format_listing(listing)
    # Match "Detected: 2024-01-15T10:30:00" (with optional timezone offset)
    assert re.search(r"Detected: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", formatted)


# ---------------------------------------------------------------------------
# Example-based: send_new_listings HTTP behaviour
# **Validates: Requirements 7.4, 7.5, 7.6**
# ---------------------------------------------------------------------------

class TestSendNewListingsRetry:
    """Non-2xx response → retry once after RETRY_DELAY_SECONDS, then give up."""

    def test_non_2xx_retries_once(self) -> None:
        listing = _make_listing()
        bad_response = MagicMock()
        bad_response.ok = False
        bad_response.status_code = 429
        bad_response.text = "Too Many Requests"

        with (
            patch("notifier.requests.post", return_value=bad_response) as mock_post,
            patch("notifier.time.sleep") as mock_sleep,
        ):
            send_new_listings([listing], webhook_url="https://discord.com/api/webhooks/123/abc")

        # Two POSTs: original + one retry
        assert mock_post.call_count == 2
        # Sleep called once with RETRY_DELAY_SECONDS between the two attempts
        mock_sleep.assert_called_once_with(RETRY_DELAY_SECONDS)

    def test_success_on_first_attempt_no_retry(self) -> None:
        listing = _make_listing()
        ok_response = MagicMock()
        ok_response.ok = True

        with (
            patch("notifier.requests.post", return_value=ok_response) as mock_post,
            patch("notifier.time.sleep") as mock_sleep,
        ):
            send_new_listings([listing], webhook_url="https://discord.com/api/webhooks/123/abc")

        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()

    def test_success_on_retry_no_further_attempt(self) -> None:
        listing = _make_listing()
        bad_response = MagicMock(ok=False, status_code=500, text="error")
        ok_response = MagicMock(ok=True)

        with (
            patch("notifier.requests.post", side_effect=[bad_response, ok_response]) as mock_post,
            patch("notifier.time.sleep"),
        ):
            send_new_listings([listing], webhook_url="https://discord.com/api/webhooks/123/abc")

        assert mock_post.call_count == 2


class TestSendNewListingsNetworkError:
    """RequestException → log and continue, no crash."""

    def test_network_error_does_not_raise(self) -> None:
        import requests as req
        listing = _make_listing()

        with patch("notifier.requests.post", side_effect=req.ConnectionError("timeout")):
            # Must not raise
            send_new_listings([listing], webhook_url="https://discord.com/api/webhooks/123/abc")

    def test_network_error_no_retry(self) -> None:
        """On a network error we log and return immediately — no retry attempt."""
        import requests as req
        listing = _make_listing()

        with (
            patch("notifier.requests.post", side_effect=req.ConnectionError("timeout")) as mock_post,
            patch("notifier.time.sleep") as mock_sleep,
        ):
            send_new_listings([listing], webhook_url="https://discord.com/api/webhooks/123/abc")

        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()


class TestPayloadFormat:
    """Discord webhook payload must use 'content' field; no 'parse_mode' or 'text'."""

    def test_payload_uses_content_field(self) -> None:
        listing = _make_listing()
        ok_response = MagicMock(ok=True)

        with patch("notifier.requests.post", return_value=ok_response) as mock_post:
            send_new_listings([listing], webhook_url="https://discord.com/api/webhooks/123/abc")

        assert mock_post.call_count == 1
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json", {})
        assert "content" in payload
        assert "parse_mode" not in payload
        assert "text" not in payload


class TestEmptyListings:
    """Sending an empty list must not make any HTTP calls."""

    def test_empty_listings_no_post(self) -> None:
        with patch("notifier.requests.post") as mock_post:
            send_new_listings([], webhook_url="https://discord.com/api/webhooks/123/abc")
        mock_post.assert_not_called()
