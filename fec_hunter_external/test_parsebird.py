
"""Test Parsebird Facebook Marketplace API.

Search for vehicles around Maidstone, Kent.

This script:
1. Connects to Apify using your API token.
2. Runs the Parsebird Marketplace scraper.
3. Downloads the returned listings.
4. Saves the results locally as JSON.
5. Prints a summary of the first five listings.

Run:
    python test_parsebird.py
"""

import json
import os
import sys
from pathlib import Path

from apify_client import ApifyClient


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ACTOR = "parsebird/facebook-marketplace-scraper"

SEARCH_INPUT = {
    "vehicleSearches": [
        {
            "make": "all",
            "location": "Maidstone, Kent, UK",
        }
    ],
    "searchRadiusKm": 40,
    "minPrice": 500,
    "maxPrice": 5000,
    "dateListed": "last_24_hours",
    "vehicleMinYear": 2008,
    "maxListings": 20,
    "fetchDetails": True,
    "deduplicateListings": True,
    "monitoringMode": True,
}

OUTPUT_FILE = Path("parsebird_test_results.json")


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    token = os.environ.get("APIFY_TOKEN")

    if not token:
        print("ERROR: APIFY_TOKEN is missing.")
        print("Set your Apify token before running.")
        sys.exit(1)

    client = ApifyClient(token)

    print("=" * 55)
    print("FAST EASY CAR - PARSEBIRD API TEST")
    print("=" * 55)

    print()
    print("Actor:", ACTOR)
    print("Location: Maidstone, Kent")
    print("Radius: 40 km")
    print("Price range: GBP 500 - 5000")
    print("Maximum listings: 20")
    print("Monitoring mode: Enabled")
    print()

    try:
        print("Starting Parsebird scraper...")

        run = client.actor(ACTOR).call(
            run_input=SEARCH_INPUT
        )

        if not run:
            print("ERROR: No run information returned.")
            return

        run_status = run.get("status")
        run_id = run.get("id")
        dataset_id = run.get("defaultDatasetId")

        print()
        print("Run status:", run_status)
        print("Run ID:", run_id)

        if run_status != "SUCCEEDED":
            print(
                "Scraper did not complete successfully."
            )
            print(
                "Check the run logs in Apify Console."
            )
            return

        if not dataset_id:
            print("ERROR: No dataset ID returned.")
            return

        print()
        print("Downloading results...")

        items = list(
            client.dataset(dataset_id).iterate_items()
        )

        print("Listings returned:", len(items))

        # Save raw data for schema inspection.
        OUTPUT_FILE.write_text(
            json.dumps(
                items,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

        OUTPUT_FILE.chmod(0o600)

        print("Results saved to:", OUTPUT_FILE.resolve())

        if not items:
            print()
            print("No listings returned.")
            print(
                "Check the search settings and "
                "monitoring configuration."
            )
            return

        print()
        print("=" * 55)
        print("FIRST FIVE RESULTS")
        print("=" * 55)

        for index, item in enumerate(items[:5], start=1):

            print()
            print(f"--- LISTING {index} ---")

            if not isinstance(item, dict):
                print("Unexpected record:", type(item).__name__)
                continue

            print("Available fields:", list(item.keys()))

            for field in [
                "title",
                "name",
                "price",
                "listingPrice",
                "location",
                "url",
                "listingUrl",
                "id",
                "listingId",
                "createdAt",
                "postedAt",
            ]:
                if field in item:
                    print(f"{field}: {item[field]}")

            vehicle = item.get("vehicle")

            if isinstance(vehicle, dict):
                print(
                    "Vehicle fields:",
                    list(vehicle.keys()),
                )

        print()
        print("=" * 55)
        print("TEST COMPLETE")
        print("=" * 55)

    except Exception as error:

        print()
        print("ERROR:", type(error).__name__)
        print(str(error))
        print()
        print(
            "Check your API token, actor access, "
            "input schema and Apify run logs."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

