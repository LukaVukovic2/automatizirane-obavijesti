"""
seed_browser.py — Run this once to establish a valid browser session.

Opens a visible Chrome window to njuskalo.hr. Once the page loads with
real listings (not a captcha), press Enter to save the session and close.
After this, monitor.py will reuse the session headlessly.
"""

import os
import shutil
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get('NJUSKALO_SEARCH_URL', 'https://www.njuskalo.hr/')

PROFILE_DIR = os.path.join(os.path.dirname(__file__), ".browser_profile")
READY_FLAG = os.path.join(PROFILE_DIR, ".ready")

# Clear any stale profile so we start fresh
if os.path.exists(PROFILE_DIR):
    shutil.rmtree(PROFILE_DIR)
os.makedirs(PROFILE_DIR)

print("Opening browser... please wait for the page to fully load.")
print("If you see a captcha, wait for it to resolve automatically.")
print()

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
        locale="hr-HR",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()

    print("Loading njuskalo.hr homepage...")
    page.goto("https://www.njuskalo.hr/", wait_until="domcontentloaded", timeout=60000)

    import time
    time.sleep(4)

    print(f"Loading search page: {url[:80]}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Auto-dismiss GDPR consent dialog if present
    try:
        # Try common "Accept all" / "Prihvati" button selectors
        for selector in [
            "button:has-text('Prihvati sve')",
            "button:has-text('Prihvati')",
            "button:has-text('Accept all')",
            "button:has-text('Accept')",
            ".didomi-accept-notice-button",
            "#didomi-notice-agree-button",
        ]:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                print(f"Dismissed consent dialog via: {selector}")
                time.sleep(1)
                break
    except Exception as e:
        print(f"Could not auto-dismiss consent dialog: {e}")

    # Wait up to 20s for listings to appear
    try:
        page.wait_for_selector("section.EntityList", timeout=20000)
        print("\nListings loaded successfully!")
    except Exception:
        print("\nListings did not appear — you may need to solve a captcha manually in the browser.")

    input("\nPress Enter when the page shows real listings (not a captcha) to save the session and exit...")
    context.close()

# Mark profile as ready
open(READY_FLAG, "w").close()
print("\nSession saved. You can now run: python monitor.py")
