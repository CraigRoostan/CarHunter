
"""Export an authenticated Facebook Playwright session.

Run locally on your Mac.

The script:
1. Opens your existing Playwright browser profile.
2. Allows manual Facebook login if required.
3. Checks that Marketplace vehicle listings are visible.
4. Exports the browser session to a private local file.

WARNING:
The exported file contains sensitive authentication credentials.
Never upload it to GitHub or share its contents.
"""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


PROFILE_DIR = (
    Path.home()
    / ".carhunter"
    / "facebook-test-profile"
)

OUTPUT_FILE = (
    Path.home()
    / ".carhunter"
    / "facebook-state.b64"
)

MARKETPLACE_URL = (
    "https://"
    + "www.facebook.com/marketplace/category/vehicles/"
)


def main():
    PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Starting Facebook authentication browser...")

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={
                "width": 1440,
                "height": 900,
            },
        )

        try:
            page = (
                browser.pages[0]
                if browser.pages
                else browser.new_page()
            )

            print("Opening Facebook Marketplace...")

            page.goto(
                MARKETPLACE_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print()
            print("Log into Facebook manually if required.")
            print("Navigate to the Vehicles category.")
            print("Wait until vehicle listings are visible.")
            print()

            input(
                "Press ENTER when vehicle listings are visible..."
            )

            listing_links = page.locator(
                'a[href*="/marketplace/item/"]'
            )

            count = listing_links.count()

            print()
            print("Vehicle listings detected:", count)

            if count == 0:
                print(
                    "No vehicle listings detected. "
                    "Session will not be exported."
                )
                return

            state = browser.storage_state()

            encoded_state = base64.b64encode(
                json.dumps(state).encode("utf-8")
            ).decode("ascii")

            OUTPUT_FILE.write_text(
                encoded_state,
                encoding="ascii",
            )

            OUTPUT_FILE.chmod(0o600)

            print()
            print("SUCCESS: Facebook session exported.")
            print("Saved to:", OUTPUT_FILE)
            print()
            print(
                "IMPORTANT: This file contains sensitive "
                "Facebook authentication credentials."
            )
            print(
                "Do not upload it to GitHub or share it."
            )

        finally:
            browser.close()


if __name__ == "__main__":
    main()

