from pathlib import Path
from playwright.sync_api import sync_playwright
import re

PROFILE = Path.home() / ".carhunter" / "facebook-test-profile"

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=False,
        viewport={"width": 1440, "height": 900},
    )

    page = browser.pages[0] if browser.pages else browser.new_page()

    print("Opening Facebook Marketplace...")
    page.goto(
        "https://" + "www.facebook.com/marketplace/category/vehicles/",
        wait_until="domcontentloaded",
        timeout=60000,
    )

    print("\nSelect a vehicle listing manually in the browser.")
    print("Wait until its details and description are visible.")
    input("\nPress ENTER when the vehicle details are open...")

    print("\n" + "=" * 50)
    print("VEHICLE DETAILS")
    print("=" * 50)

    print("\nCurrent URL:", page.url)

    # Facebook may display details in a dialog or main page.
    dialog = page.locator('[role="dialog"]')
    if dialog.count():
        text = dialog.last.inner_text(timeout=10000)
    else:
        text = page.locator("body").inner_text(timeout=10000)

    print("\nVISIBLE DETAILS:")
    print(text[:6000])

    print("\nPOTENTIAL MILEAGE:")
    mileage = re.findall(
        r"\b[\d,]+\s*(?:miles|mi|km)\b",
        text,
        flags=re.IGNORECASE,
    )
    print(mileage[:10] if mileage else "Not detected")

    print("\nPOTENTIAL REGISTRATION:")
    registrations = re.findall(
        r"\b[A-Z]{2}\d{2}\s?[A-Z]{3}\b",
        text,
        flags=re.IGNORECASE,
    )
    print(registrations[:10] if registrations else "Not detected")

    print("\nIMAGES FOUND:")
    images = page.locator('img')
    print("Total images:", images.count())

    input("\nPress ENTER to close the browser...")
    browser.close()
