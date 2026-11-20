from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://" + "www.facebook.com/marketplace/category/vehicles/"
PROFILE = Path.home() / ".carhunter" / "facebook-test-profile"

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=False,
        viewport={"width": 1440, "height": 900},
    )

    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    input("Wait until vehicle listings appear, then press ENTER...")

    cards = page.locator('a[href*="/marketplace/item/"]')

    print("\nLISTINGS FOUND:", cards.count())

    for i in range(min(cards.count(), 10)):
        card = cards.nth(i)

        print("\n--- VEHICLE", i + 1, "---")
        print("URL:", card.get_attribute("href"))
        print("TEXT:", card.inner_text()[:500])

        images = card.locator("img")
        if images.count():
            print("IMAGE:", images.first.get_attribute("src"))

    input("\nPress ENTER to close...")
    browser.close()
