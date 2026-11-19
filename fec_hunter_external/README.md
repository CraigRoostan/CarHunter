# Fast Easy Car Hunter collector

Continuously polls a permitted vehicle marketplace and posts new and repriced
listings to the Base44 ingestion API, where they are valued against CAP and ranked.

Runs on its own host. It is not part of the web app and needs no inbound ports.

## What it does each cycle

1. Reads its configuration from the dashboard (interval, areas, price band, sources).
2. Polls each enabled source, newest first, and stops paging once a whole page is
   already known (a full sweep runs every 12 cycles so older price changes are caught).
3. Deduplicates on `source` + `source_listing_id`, across every search area.
4. Sends only genuinely new listings and listings whose asking price changed.
5. Downloads those listings' photographs, validates and re-encodes them, and stores them
   permanently through the app. A listing whose pictures have not changed is skipped, so
   nothing is uploaded twice.
6. Records the outcome locally and posts a heartbeat so the dashboard can show
   whether the collector is alive.

## Install

```bash
cd collector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then edit .env
```

Python 3.11 or newer. The browser engine needs Chromium, installed once per host:

```bash
playwright install chromium
```

The Docker image already contains it.

## Configure

`.env` on the collector host only. Never commit it.

| Variable | Purpose |
| --- | --- |
| `INGEST_KEY` | The key generated on the dashboard under Collector. Required. |
| `BASE44_URL` | Defaults to `https://fasteasycar.base44.app`. |
| `HUNTER_DB` | SQLite file for the seen-listing store. Defaults to `data/hunter.sqlite3`. |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | eBay developer app credentials, needed only for the eBay source. |
| `SAVED_PAGES_DIR` | Folder of pages saved from a browser, for the manual capture source. |
| `BROWSER_HEADLESS` | `false` shows the browser window, for watching a permitted profile work. |
| `RUN_ONCE` | `1` runs a single cycle and exits, for testing. |
| `LOG_LEVEL` | `INFO` by default. |

Interval, search areas, radii, price band, seller preference and which sources are
enabled all live in the dashboard (Collector button on Marketplace Opportunities), so
they can be changed without touching the host.

## Run

```bash
python run.py
```

For a one-off check:

```bash
RUN_ONCE=1 python run.py
```

Only one instance may run against a given database; a second exits immediately rather
than scanning twice.

## Deploy

Any always-on host: a £4 VPS, Railway, Fly.io, Render, or a Raspberry Pi in the office.
`DEPLOYMENT.md` covers environment variables, Railway and VPS steps, cost, health checks
and restarts. Docker:

```bash
docker build -t fec-hunter .
docker run -d --restart unless-stopped --env-file .env -v hunter-data:/app/data fec-hunter
```

A systemd unit works the same way if you prefer bare Python:

```ini
[Service]
WorkingDirectory=/opt/fec-hunter
EnvironmentFile=/opt/fec-hunter/.env
ExecStart=/opt/fec-hunter/.venv/bin/python run.py
Restart=always
```

## Sources

| Key | State | Notes |
| --- | --- | --- |
| `ebay` | Working | Official eBay Browse API. Needs the two credentials above. |
| `saved_pages` | Working | Manual capture: parses pages a person saved from their own browser. Fetches nothing. |
| `fixture` | Working | Synthetic listings for proving the pipeline. Always flagged as sample data. Do not leave on. |
| `facebook_marketplace` | Not available | See `docs/FACEBOOK_MARKETPLACE_ACCESS.md`. The adapter refuses rather than scraping. |

Adding a source means one file in `hunter/sources/` exposing `collect(config, store,
cycle)`, plus one line in the registry. Nothing else changes.

## Browser collection

`hunter/browser/` is the Playwright engine, kept separate from scheduling and ingestion so
a site's markup can be repaired on its own:

| File | Job |
| --- | --- |
| `extract.py` | Reads a page into listing records. Standard library only, so it is tested offline. |
| `session.py` | Launches Chromium, fetches a page, and detects an access wall. |
| `profiles.py` | Per-site data: search URL, id pattern, optional patterns. `permitted` gates it. |
| `adapter.py` | Drives a permitted profile: search page, cards, detail page, one listing at a time. |

There are no stealth patches, fingerprint spoofing or proxy rotation, and no profile is
permitted for a site that forbids automated access. A site that shows a login wall or a
CAPTCHA raises `SourceBlocked`: the source is paused for six hours, then a week, and the
reason appears in the dashboard. It is never retried in a loop.

## Manual capture

`SAVED_PAGES_DIR` is a folder of `.html` pages saved from a browser. The collector parses
them with the same extractor and sends anything new. It never contacts the site, never
logs in and never scrolls, so it stays inside what a person is already allowed to view.
Save a search page to capture many listings at once, or a single listing page for one.
This is a bridge until a licensed source is connected, not a bulk scraper.

## Tests

```bash
cd collector
python -m unittest discover -s tests -t .
```

Covers structured extraction, the no-invention rule, price parsing (a year is never read
as a price), card extraction, login-wall detection, deduplication, price changes and the
block cooldown. The fixtures are synthetic and are not reported as real listings.

## Failure behaviour

- A source that cannot run (missing credentials, rate limit, upstream error) is
  reported in the heartbeat and skipped; the other sources still run.
- A source that refuses access is paused, not retried: six hours, then a week.
- A failed cycle backs off exponentially, up to 30 minutes, then resumes the
  configured interval.
- A rejected ingest key stops retrying and says so, because retrying cannot fix it.
- Listings are marked as seen only after Base44 has accepted them, so a failed send
  is retried next cycle rather than lost.
- Nothing overlapping: cycles are sequential and a lock file prevents a second process.

## Troubleshooting

- **401 from Base44**: the key was rotated. Generate a new one and update `.env`.
- **`eBay needs EBAY_CLIENT_ID`**: the source is enabled but the host has no
  credentials. Add them or turn the source off.
- **Listings arrive but nothing is valued**: the vehicle is missing a year or mileage.
  The dashboard flags these as review required by design; nothing is invented.
- **Nothing at all arrives**: check the heartbeat in the dashboard. `No source enabled`
  means the sources list is empty.
