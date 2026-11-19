# Deploying the collector

The collector is the only part of the hunter that runs outside Base44. It scans the
sources you have permission to scan, sends what it finds to the app, and reports back
every cycle. It needs one small always-on Linux host and nothing else.

## What the host needs

| | |
| --- | --- |
| CPU | 1 vCPU is enough; Chromium is only used by browser sources |
| Memory | 1 GB minimum, 2 GB comfortable (Chromium is the reason) |
| Disk | 2 GB; the SQLite store is a few hundred kilobytes |
| Network | Outbound HTTPS only. No inbound ports, no domain, no TLS certificate |

## Environment variables

Set these on the host (or in Railway's variables panel). `.env` is read from the working
directory; real environment variables win.

| Variable | Required | Purpose |
| --- | --- | --- |
| `INGEST_KEY` | yes | Generated on Marketplace Opportunities → Collector API. The collector's only credential. |
| `BASE44_URL` | no | Defaults to `https://fasteasycar.base44.app`. |
| `HUNTER_DB` | no | SQLite path. Defaults to `data/hunter.sqlite3`. Put it on a volume. |
| `LOG_LEVEL` | no | `INFO` by default. |
| `IDLE_POLL_SECONDS` | no | How often an idle collector re-reads the dashboard. Defaults to `60`. |
| `BROWSER_HEADLESS` | no | `true` by default. `false` shows the window, for watching a permitted profile. |
| `PAGE_DELAY_SECONDS` | no | Pause between detail pages. Defaults to `2.5`. |
| `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` | only for eBay | From the eBay developer programme (free). |
| `SAVED_PAGES_DIR` | only for manual capture | Folder of pages a person saved themselves. |
| `RUN_ONCE` | no | `1` runs a single cycle and exits, for testing. |

### Handling the key

- Generate it on the dashboard, paste it into the host's environment. It is never sent
  anywhere except Base44, in the `x-ingest-key` header.
- Do not commit `.env`. `collector/.gitignore` already excludes it.
- Rotating the key on the dashboard immediately invalidates the old one. The collector
  stops with a clear message rather than retrying a rejected key, so a rotation is a
  visible event, not a silent outage.
- No other credential is needed. The collector holds no Base44 login and no database
  password.

## Idle when there is nothing to scan

A collector with no permitted feed available is **idle**, not broken. It keeps checking in
so the dashboard knows the host is alive, but it logs the reason once instead of repeating it
every cycle, and it never reports an error for a state you chose.

It is idle in three cases:

1. **Collection is switched off.** `collector_enabled` is false on the dashboard. The
   collector posts `idle` with "Idle: collection is switched off in the dashboard", logs one
   line, then waits `IDLE_POLL_SECONDS` and re-reads the dashboard. Nothing is scanned and
   nothing is sent.
2. **No source is enabled.** `collector_sources` is empty. Same quiet behaviour, with
   "Idle: no source is enabled in the dashboard".
3. **A source reports itself unavailable.** For example Facebook Marketplace, which always
   refuses. The cycle completes normally, the reason appears in the heartbeat message and on
   the dashboard, and no error is raised.

To run in this state deliberately, leave `collector_sources` empty. The host stays up, the
container stays healthy, and turning a source on later takes effect within one idle poll. The
dashboard strip reads **Idle** rather than *Running* or *Not responding*, and the last
successful scan keeps its real value instead of being refreshed by an idle check-in.

## Option A: Railway

1. Push this repository to GitHub (or use `railway up` from `collector/`).
2. New project → Deploy from repo → set **Root Directory** to `collector`. Railway picks
   up the `Dockerfile`.
3. Variables: add `INGEST_KEY`, and `HUNTER_DB=/app/data/hunter.sqlite3`.
4. Add a **Volume** mounted at `/app/data`. Without it the seen-listings are lost on every
   deploy, and the next scan re-sends everything (the ingestion API still deduplicates, so
   the cost is traffic, not duplicate vehicles).
5. Set the restart policy to **Always**. Railway restarts a container that exits, and its
   health check uses the `HEALTHCHECK` in the Dockerfile.
6. Deploy. The first cycle runs immediately; watch the logs for `Cycle 1:`.

## Option B: a small VPS

```bash
# On the server
git clone <your repo> fec-hunter && cd fec-hunter/collector
cp .env.example .env && nano .env          # paste INGEST_KEY
docker compose up -d --build
docker compose logs -f
```

`docker-compose.yml` already sets `restart: unless-stopped` and caps the log size. On
reboot, Docker starts the container again.

Prefer bare Python? Use the systemd unit in `README.md`; it sets `Restart=always`.

## Monitoring

Three independent signals, all of them already wired:

1. **Base44 heartbeat.** Every cycle the collector posts its status, what it scanned, what
   it sent, its hostname and its version. Marketplace Opportunities shows the collector's
   state, the last successful scan and the last failure message.
2. **Health check.** The loop rewrites `data/collector.heartbeat` at the start of every
   cycle. The image's `HEALTHCHECK` fails when that file is older than fifteen minutes, so
   an orchestrator restarts a stuck process rather than leaving it silent.
3. **Logs.** One line per cycle, plus a line per failure. `docker compose logs -f`.

## Expected cost

Approximate, and worth checking against current pricing:

| Host | Monthly |
| --- | --- |
| Railway Hobby, 1 GB container running continuously | roughly $5–15 |
| Hetzner CX22 (2 vCPU / 4 GB) | roughly €5 |
| Any 2 GB VPS (DigitalOcean, Vultr, Lightsail) | roughly £5–10 |

The app itself is billed separately. A 5-minute cadence costs nothing extra: it is one
small JSON request per cycle, plus image uploads when a source supplies new photographs.

## What the host does each cycle

1. Reads its configuration from the dashboard (interval, areas, price band, sources).
2. Polls each enabled source, newest first, stopping when a page is already known.
3. Deduplicates on source + listing id, across every search area.
4. Sends new and repriced listings to `marketplaceIngest`.
5. Downloads and prepares the photographs of those listings, then sends them to
   `marketplacePhotoIngest`, which stores them privately and writes them onto the record.
6. Posts a heartbeat and sleeps until the next cycle.

Cycles never overlap: the loop is sequential and a lock file stops a second process using
the same database.

## Verifying a deployment

```bash
# One cycle, verbose, no daemon
RUN_ONCE=1 LOG_LEVEL=INFO python run.py
```

A healthy run ends with `Cycle 1: <source>: N new, 0 updated, 0 repriced; N photographs
stored`. Then check Marketplace Opportunities: the vehicles are there, the collector strip
says Running, and the last successful scan is moments ago.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `401` / `Unauthorized` in the logs | The key was rotated. Generate a new one and update `INGEST_KEY`. |
| `Idle: no source is enabled in the dashboard` | `collector_sources` is empty. Turn a source on. Not an error. |
| `Idle: collection is switched off in the dashboard` | `collector_enabled` is false. Turn it on. Not an error. |
| Collector shows *Not responding* | The host is down, or its clock/network is failing. Check the container status. |
| Listings arrive, no photographs | The source published no image URLs, or its CDN refused the download. The listing is kept; the photograph is not invented. |
| Facebook reports *unavailable* | Expected. See `docs/FACEBOOK_MARKETPLACE_ACCESS.md`. |
