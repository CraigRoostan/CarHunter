"""Manually export authenticated local Playwright session. Treat output as a password."""
import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

profile = Path.home() / '.carhunter' / 'facebook-test-profile'
output = Path.home() / '.carhunter' / 'facebook-state.b64'
output.parent.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch_persistent_context(str(profile), headless=False)
    try:
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto('https://www.facebook.com/marketplace/category/vehicles/', wait_until='domcontentloaded')
        input('Log in manually if needed. When vehicle cards are visible, press ENTER...')
        if page.locator('a[href*="/marketplace/item/"]').count() == 0:
            raise SystemExit('No vehicle cards visible; not exporting session.')
        state = browser.storage_state()
        output.write_text(base64.b64encode(json.dumps(state).encode()).decode(), encoding='ascii')
        output.chmod(0o600)
        print('Session state saved locally at:', output)
        print('Do NOT upload this file to GitHub or this chat; it contains login credentials.')
    finally:
        browser.close()
