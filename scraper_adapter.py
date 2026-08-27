"""
scraper_adapter.py — Fetches the Njuskalo search results page.

Uses Playwright with a persistent browser profile (.browser_profile/) to
appear as a normal browser session. The profile must be seeded first by
running seed_browser.py once.

Anti-detection measures:
- Real Chromium engine (same TLS fingerprint as a normal browser)
- Persistent session cookies carried across requests
- Random pre-request delay (3-12s) to avoid precise polling patterns
- Visits the homepage occasionally to mimic natural browsing behaviour
"""

import logging
import os
import random
import time

_log = logging.getLogger(__name__)

_PROFILE_DIR = os.path.join(os.path.dirname(__file__), ".browser_profile")
_PROFILE_READY_FLAG = os.path.join(_PROFILE_DIR, ".ready")

# Occasionally visit the homepage to look like a real user browsing around.
# This counter is in-process only; resets on restart (that's fine).
_cycle_count = 0
_HOMEPAGE_EVERY_N_CYCLES = 8  # visit homepage roughly every 8 scrapes


class ScraperError(Exception):
    """Raised when the HTTP fetch fails or returns a bot-detection page."""


def _is_captcha(html: str) -> bool:
    return (
        "ShieldSquare Captcha" in html
        or "<title>ShieldSquare" in html
        or ("shieldsquare" in html.lower() and "EntityList" not in html)
    )


def _profile_ready() -> bool:
    return os.path.exists(_PROFILE_READY_FLAG)


def fetch_html(search_url: str) -> str:
    """
    Fetch the Njuskalo search results page using Playwright.

    Raises ScraperError if the profile hasn't been seeded yet, or if a
    bot-detection page is returned (run seed_browser.py to refresh).
    """
    global _cycle_count

    if not _profile_ready():
        raise ScraperError(
            "Browser profile not found. Run 'python seed_browser.py' once to establish a session."
        )

    # Human-like random delay before each request (3–12 seconds)
    delay = random.uniform(3, 12)
    _log.debug("Waiting %.1fs before fetch (anti-detection jitter)", delay)
    time.sleep(delay)

    from playwright.sync_api import sync_playwright

    _cycle_count += 1
    visit_homepage = (_cycle_count % _HOMEPAGE_EVERY_N_CYCLES == 0)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=_PROFILE_DIR,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1280, "height": 800},
            locale="hr-HR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Patch webdriver flag — headless Chromium sets this to true by default
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Occasionally visit the homepage first to mimic natural browsing
        if visit_homepage:
            _log.debug("Visiting homepage (periodic natural behaviour)")
            try:
                page.goto("https://www.njuskalo.hr/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(1, 3))
            except Exception:
                pass  # non-critical

        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

        # Wait for listing content to appear
        try:
            page.wait_for_selector("section.EntityList", timeout=15000)
        except Exception:
            pass

        html = page.content()
        context.close()

    if _is_captcha(html):
        # Invalidate the profile so the user knows to re-seed
        if os.path.exists(_PROFILE_READY_FLAG):
            os.remove(_PROFILE_READY_FLAG)
        # Log a snippet to help diagnose what page was returned
        from bs4 import BeautifulSoup as _BS
        _title = _BS(html, "html.parser").find("title")
        _log.error("Bot-detection page title: %s", _title.get_text() if _title else "NO TITLE")
        _log.debug("Bot-detection HTML snippet: %s", html[:500])
        raise ScraperError(
            "Bot-detection page returned. Run 'python seed_browser.py' to refresh the session."
        )

    _log.debug("Fetched %s — %d bytes", search_url, len(html))
    return html
