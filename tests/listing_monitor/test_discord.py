"""
Unit tests for listing_monitor/discord.py — task 5.1

Covers build_embed():
  - title and url are set correctly
  - color is always 3447003
  - price field included when non-empty
  - price field omitted when empty string
  - area field included when non-empty, omitted when empty/absent
  - rooms field included when non-empty, omitted when empty/absent
  - location field included when non-empty, omitted when empty/absent
  - fields list is empty when all optional fields are absent/empty and price is empty
  - all four fields present when all values are non-empty
  - location field has inline=False; price/area/rooms have inline=True
  - returns a plain dict (JSON-serialisable)
"""

import json

import pytest

from listing_monitor.discord import EMBED_COLOR, build_embed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_listing(**overrides):
    """Return a Listing with all fields populated, with optional overrides."""
    base = {
        "listing_id": "51297387",
        "title": "Lijepi stan u centru",
        "price": "600 €/mj",
        "url": "https://www.njuskalo.hr/iznajmljivanje-stanova/oglas-51297387",
        "area": "55 m²",
        "rooms": "2",
        "location": "Zagreb, Gornji grad",
    }
    base.update(overrides)
    return base


def _field_names(embed: dict) -> list[str]:
    return [f["name"] for f in embed.get("fields", [])]


# ---------------------------------------------------------------------------
# Title and URL
# ---------------------------------------------------------------------------

class TestBuildEmbedTitleAndUrl:
    def test_title_matches_listing_title(self):
        listing = _full_listing()
        embed = build_embed(listing)
        assert embed["title"] == listing["title"]

    def test_url_matches_listing_url(self):
        listing = _full_listing()
        embed = build_embed(listing)
        assert embed["url"] == listing["url"]


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------

class TestBuildEmbedColor:
    def test_color_is_always_3447003(self):
        embed = build_embed(_full_listing())
        assert embed["color"] == EMBED_COLOR

    def test_color_correct_for_minimal_listing(self):
        listing = {
            "listing_id": "1",
            "title": "T",
            "price": "",
            "url": "https://example.com",
        }
        embed = build_embed(listing)
        assert embed["color"] == 3447003


# ---------------------------------------------------------------------------
# Price field
# ---------------------------------------------------------------------------

class TestBuildEmbedPrice:
    def test_price_field_included_when_non_empty(self):
        embed = build_embed(_full_listing(price="500 €/mj"))
        assert "Cijena" in _field_names(embed)

    def test_price_field_value_correct(self):
        embed = build_embed(_full_listing(price="500 €/mj"))
        price_field = next(f for f in embed["fields"] if f["name"] == "Cijena")
        assert price_field["value"] == "500 €/mj"

    def test_price_field_is_inline(self):
        embed = build_embed(_full_listing(price="500 €/mj"))
        price_field = next(f for f in embed["fields"] if f["name"] == "Cijena")
        assert price_field["inline"] is True

    def test_price_field_omitted_when_empty_string(self):
        embed = build_embed(_full_listing(price=""))
        assert "Cijena" not in _field_names(embed)

    def test_price_field_omitted_when_absent(self):
        listing = {
            "listing_id": "1",
            "title": "T",
            "price": "",
            "url": "https://example.com",
        }
        embed = build_embed(listing)
        assert "Cijena" not in _field_names(embed)


# ---------------------------------------------------------------------------
# Area field
# ---------------------------------------------------------------------------

class TestBuildEmbedArea:
    def test_area_field_included_when_non_empty(self):
        embed = build_embed(_full_listing(area="60 m²"))
        assert "Površina" in _field_names(embed)

    def test_area_field_value_correct(self):
        embed = build_embed(_full_listing(area="60 m²"))
        area_field = next(f for f in embed["fields"] if f["name"] == "Površina")
        assert area_field["value"] == "60 m²"

    def test_area_field_is_inline(self):
        embed = build_embed(_full_listing(area="60 m²"))
        area_field = next(f for f in embed["fields"] if f["name"] == "Površina")
        assert area_field["inline"] is True

    def test_area_field_omitted_when_empty_string(self):
        embed = build_embed(_full_listing(area=""))
        assert "Površina" not in _field_names(embed)

    def test_area_field_omitted_when_absent(self):
        listing = {
            "listing_id": "1",
            "title": "T",
            "price": "100€",
            "url": "https://example.com",
        }
        embed = build_embed(listing)
        assert "Površina" not in _field_names(embed)


# ---------------------------------------------------------------------------
# Rooms field
# ---------------------------------------------------------------------------

class TestBuildEmbedRooms:
    def test_rooms_field_included_when_non_empty(self):
        embed = build_embed(_full_listing(rooms="3"))
        assert "Sobe" in _field_names(embed)

    def test_rooms_field_value_correct(self):
        embed = build_embed(_full_listing(rooms="3"))
        rooms_field = next(f for f in embed["fields"] if f["name"] == "Sobe")
        assert rooms_field["value"] == "3"

    def test_rooms_field_is_inline(self):
        embed = build_embed(_full_listing(rooms="3"))
        rooms_field = next(f for f in embed["fields"] if f["name"] == "Sobe")
        assert rooms_field["inline"] is True

    def test_rooms_field_omitted_when_empty_string(self):
        embed = build_embed(_full_listing(rooms=""))
        assert "Sobe" not in _field_names(embed)

    def test_rooms_field_omitted_when_absent(self):
        listing = {
            "listing_id": "1",
            "title": "T",
            "price": "100€",
            "url": "https://example.com",
        }
        embed = build_embed(listing)
        assert "Sobe" not in _field_names(embed)


# ---------------------------------------------------------------------------
# Location field
# ---------------------------------------------------------------------------

class TestBuildEmbedLocation:
    def test_location_field_included_when_non_empty(self):
        embed = build_embed(_full_listing(location="Zagreb, Gornji grad"))
        assert "Lokacija" in _field_names(embed)

    def test_location_field_value_correct(self):
        embed = build_embed(_full_listing(location="Zagreb, Gornji grad"))
        loc_field = next(f for f in embed["fields"] if f["name"] == "Lokacija")
        assert loc_field["value"] == "Zagreb, Gornji grad"

    def test_location_field_is_not_inline(self):
        embed = build_embed(_full_listing(location="Zagreb"))
        loc_field = next(f for f in embed["fields"] if f["name"] == "Lokacija")
        assert loc_field["inline"] is False

    def test_location_field_omitted_when_empty_string(self):
        embed = build_embed(_full_listing(location=""))
        assert "Lokacija" not in _field_names(embed)

    def test_location_field_omitted_when_absent(self):
        listing = {
            "listing_id": "1",
            "title": "T",
            "price": "100€",
            "url": "https://example.com",
        }
        embed = build_embed(listing)
        assert "Lokacija" not in _field_names(embed)


# ---------------------------------------------------------------------------
# Combined / edge cases
# ---------------------------------------------------------------------------

class TestBuildEmbedCombined:
    def test_all_four_fields_present_when_all_values_non_empty(self):
        embed = build_embed(_full_listing())
        names = _field_names(embed)
        assert "Cijena" in names
        assert "Površina" in names
        assert "Sobe" in names
        assert "Lokacija" in names

    def test_no_fields_when_price_and_optionals_all_empty(self):
        listing = {
            "listing_id": "1",
            "title": "T",
            "price": "",
            "url": "https://example.com",
            "area": "",
            "rooms": "",
            "location": "",
        }
        embed = build_embed(listing)
        assert embed["fields"] == []

    def test_only_price_when_optionals_absent(self):
        listing = {
            "listing_id": "1",
            "title": "T",
            "price": "400€",
            "url": "https://example.com",
        }
        embed = build_embed(listing)
        assert _field_names(embed) == ["Cijena"]

    def test_return_value_is_json_serialisable(self):
        embed = build_embed(_full_listing())
        # Should not raise
        serialised = json.dumps(embed)
        parsed = json.loads(serialised)
        assert parsed["title"] == _full_listing()["title"]

    def test_return_value_is_plain_dict(self):
        embed = build_embed(_full_listing())
        assert type(embed) is dict  # noqa: E721 — exact type check, not isinstance


# ---------------------------------------------------------------------------
# send_discord — unit tests (task 5.2)
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from listing_monitor.discord import send_discord


@dataclass(frozen=True)
class _FakeSearcher:
    id: str = "test"
    name: str = "Test Searcher"
    search_url: str = "https://example.com/search"
    webhook_url: str = "https://discord.com/api/webhooks/test/token"


def _minimal_listing():
    return {
        "listing_id": "99999",
        "title": "Testni oglas",
        "price": "500 €/mj",
        "url": "https://www.njuskalo.hr/oglas/99999",
    }


class TestSendDiscord2xx:
    def test_returns_true_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"
        with patch("requests.post", return_value=mock_resp):
            result = send_discord(_FakeSearcher(), _minimal_listing())
        assert result is True

    def test_returns_true_on_204(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.text = ""
        with patch("requests.post", return_value=mock_resp):
            result = send_discord(_FakeSearcher(), _minimal_listing())
        assert result is True

    def test_posts_embeds_payload(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"
        with patch("requests.post", return_value=mock_resp) as mock_post:
            send_discord(_FakeSearcher(), _minimal_listing())
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "embeds" in payload
        assert isinstance(payload["embeds"], list)
        assert len(payload["embeds"]) == 1

    def test_posts_to_webhook_url(self):
        searcher = _FakeSearcher()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"
        with patch("requests.post", return_value=mock_resp) as mock_post:
            send_discord(searcher, _minimal_listing())
        posted_url = mock_post.call_args[0][0] if mock_post.call_args[0] else mock_post.call_args[1]["url"]
        assert posted_url == searcher.webhook_url


class TestSendDiscordNon2xx:
    def test_returns_false_on_400(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        with patch("requests.post", return_value=mock_resp):
            result = send_discord(_FakeSearcher(), _minimal_listing())
        assert result is False

    def test_returns_false_on_500(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("requests.post", return_value=mock_resp):
            result = send_discord(_FakeSearcher(), _minimal_listing())
        assert result is False

    def test_logs_status_code_on_non_2xx(self, caplog):
        import logging
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        with patch("requests.post", return_value=mock_resp):
            with caplog.at_level(logging.ERROR, logger="listing_monitor.discord"):
                send_discord(_FakeSearcher(), _minimal_listing())
        assert "429" in caplog.text

    def test_logs_truncated_body_on_non_2xx(self, caplog):
        import logging
        long_body = "x" * 500
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = long_body
        with patch("requests.post", return_value=mock_resp):
            with caplog.at_level(logging.ERROR, logger="listing_monitor.discord"):
                send_discord(_FakeSearcher(), _minimal_listing())
        # The logged body should be truncated to ≤200 chars
        logged = caplog.text
        # Find the portion after the status code in the log message
        assert "503" in logged
        # The body preview in the log should not exceed 200 chars of the body content
        assert long_body[:200] in logged
        assert long_body[201:] not in logged


class TestSendDiscordNetworkError:
    def test_returns_false_on_request_exception(self):
        import requests as req_mod
        with patch("requests.post", side_effect=req_mod.RequestException("connection refused")):
            result = send_discord(_FakeSearcher(), _minimal_listing())
        assert result is False

    def test_does_not_raise_on_request_exception(self):
        import requests as req_mod
        # Should not raise even when requests raises
        with patch("requests.post", side_effect=req_mod.RequestException("timeout")):
            try:
                send_discord(_FakeSearcher(), _minimal_listing())
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"send_discord raised unexpectedly: {exc}")

    def test_logs_exception_message_on_network_error(self, caplog):
        import logging
        import requests as req_mod
        with patch("requests.post", side_effect=req_mod.RequestException("dns lookup failed")):
            with caplog.at_level(logging.ERROR, logger="listing_monitor.discord"):
                send_discord(_FakeSearcher(), _minimal_listing())
        assert "dns lookup failed" in caplog.text
