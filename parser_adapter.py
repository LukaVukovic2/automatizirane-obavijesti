"""
parser_adapter.py — Parses Njuskalo search results HTML into Listing dicts.

Extracts listings from the EntityList section titled "Njuskalo oglasi"
or "Sniff ads". Handles both regular individual listings and featured-store
cards (which bundle multiple subitems).
"""

import logging
import re
from typing import TypedDict

from bs4 import BeautifulSoup, Tag


class _ListingRequired(TypedDict):
    listing_id: str
    title: str
    price: str
    url: str


class Listing(_ListingRequired, total=False):
    area: str
    rooms: str
    location: str


class ParserError(Exception):
    """Raised when parsing fails unexpectedly."""


_ID_RE = re.compile(r'/oglas/([A-Za-z0-9]{1,64})(?:[/?#]|$)')
# Njuskalo uses numeric IDs at the end of the URL slug, e.g. oglas-51297387
_SLUG_ID_RE = re.compile(r'oglas-(\d+)$')

_log = logging.getLogger(__name__)

_VALID_SECTION_TITLES = {"Njuškalo oglasi", "Sniff ads"}


def _extract_listing_id(url: str) -> str | None:
    # Try the canonical /oglas/<id> pattern first
    m = _ID_RE.search(url)
    if m:
        return m.group(1)
    # Fall back to numeric ID at end of URL slug (oglas-NNNNN)
    m = _SLUG_ID_RE.search(url)
    if m:
        return m.group(1)
    return None


def _abs_url(href: str) -> str:
    if href.startswith("/"):
        return "https://www.njuskalo.hr" + href
    return href


def _parse_regular_li(li: Tag) -> Listing | None:
    """Parse a regular individual listing <li>."""
    article = li.find("article", class_="entity-body")
    if not article:
        return None

    # URL + title from h3.entity-title > a.link
    h3 = article.find("h3", class_="entity-title")
    if not h3:
        return None
    a_tag = h3.find("a", class_="link")
    if not a_tag or not a_tag.get("href"):
        return None

    url = _abs_url(a_tag["href"])

    # listing_id: prefer name attribute (numeric), else extract from URL
    listing_id = a_tag.get("name") or _extract_listing_id(url)
    if not listing_id:
        _log.warning("Could not extract listing_id from %r; skipping", url)
        return None

    title_span = a_tag.find("span")
    title = title_span.get_text(strip=True) if title_span else a_tag.get_text(strip=True)

    # Price from div.entity-prices strong.price
    price = ""
    prices_div = article.find("div", class_="entity-prices")
    if prices_div:
        price_tag = prices_div.find("strong", class_="price")
        if price_tag:
            price = price_tag.get_text(strip=True)

    listing: Listing = {
        "listing_id": listing_id,
        "title": title,
        "price": price,
        "url": url,
    }

    # Location from entity-description: text following "Lokacija:" caption
    desc = article.find("div", class_="entity-description")
    if desc:
        caption = desc.find("span", class_="entity-description-itemCaption")
        if caption and "lokacija" in caption.get_text(strip=True).lower():
            # The location text is the next text node / sibling
            loc_parts = []
            for sibling in caption.next_siblings:
                text = sibling.get_text(strip=True) if hasattr(sibling, "get_text") else str(sibling).strip()
                if text and text not in ("<br/>", ""):
                    loc_parts.append(text)
                    break
            loc = ", ".join(loc_parts).strip()
            if loc:
                listing["location"] = loc

    return listing


def _parse_subitem_li(li: Tag) -> Listing | None:
    """Parse a subitem inside a featured-store card."""
    h3 = li.find("h3", class_="entity-subitem-title")
    if not h3:
        return None
    a_tag = h3.find("a", class_="link")
    if not a_tag or not a_tag.get("href"):
        return None

    url = _abs_url(a_tag["href"])
    listing_id = a_tag.get("name") or _extract_listing_id(url)
    if not listing_id:
        _log.warning("Could not extract listing_id from subitem %r; skipping", url)
        return None

    title_span = a_tag.find("span")
    title = title_span.get_text(strip=True) if title_span else a_tag.get_text(strip=True)

    return {
        "listing_id": listing_id,
        "title": title,
        "price": "",   # subitems don't show price in search results
        "url": url,
    }


def parse_listings(html: str) -> list[Listing]:
    """
    Parse Njuskalo search results HTML and return a list of Listing dicts.

    Processes both individual regular listings and subitems from
    featured-store cards. Raises ParserError on unexpected exceptions.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        raise ParserError(f"Failed to parse HTML: {exc}") from exc

    try:
        results: list[Listing] = []

        for section in soup.find_all("section", class_=lambda c: c and "EntityList" in c):
            h2 = section.find("h2")
            if not h2 or h2.get_text(strip=True) not in _VALID_SECTION_TITLES:
                continue

            ul = section.find("ul", class_=lambda c: c and "EntityList-items" in c)
            if not ul:
                continue

            for li in ul.find_all("li", recursive=False):
                classes = " ".join(li.get("class", []))

                if "FeaturedStore" in classes:
                    # Agency card: extract each subitem
                    for subitem in li.find_all("li", class_="entity-subitem"):
                        listing = _parse_subitem_li(subitem)
                        if listing:
                            results.append(listing)
                else:
                    # Regular individual listing
                    listing = _parse_regular_li(li)
                    if listing:
                        results.append(listing)

        _log.debug("Parsed %d listings from search results", len(results))
        return results

    except Exception as exc:
        raise ParserError(f"Unexpected error while parsing listings: {exc}") from exc
