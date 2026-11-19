# Fast Easy Car Hunter — external collector

An independently hosted 5-minute collector feeding the existing Base44 `marketplaceIngest` API. **It does not currently scrape Facebook Marketplace.** It reads an authorised HTTPS JSON feed, or a user-supplied JSON file for testing. Never use this service to access sources without appropriate rights.

## Test locally

```bash
pip install -r requirements.txt
DB_PATH=./collector.sqlite python collector.py --file sample_listings.json --dry-run
```

## Configure and deploy

1. Copy `.env.example` to `.env` and enter the secret from Base44 → Marketplace Opportunities → Collector API.
2. Set `PERMITTED_FEED_URL` to a feed you are authorised to collect. The endpoint must return a JSON array of listings or `{ "listings": [...] }`.
3. Set `FEED_SOURCE` to the correct source name; do not label a non-Facebook feed as Facebook.
4. Run `docker compose up -d --build` on an always-on host.
5. View logs with `docker compose logs -f collector`.

Every cycle reads the feed, deduplicates by source + listing ID, and forwards new or changed records in batches of 40. SQLite state persists in a Docker volume. The collector updates its local fingerprint **only after Base44 acknowledges success**, allowing failed batches to retry. Base44 retains responsibility for valuations, status, notes and price history.

## Photographs

Image URLs from the feed are forwarded as `image_urls`. Permanent image storage requires Base44's existing `marketplacePhotoIngest` function or a separate image-upload integration. **This starter does not yet download or persist photographs**. Confirm the photo endpoint's request schema before adding that step.

## Remaining integration work

- Obtain an authorised, reliable listing feed; Facebook Marketplace is not connected.
- Confirm actual Base44 ingest and photo API schemas; they were described in chat but not directly inspected here.
- Add heartbeat reporting, source rate limits, and integration tests against a staging Base44 endpoint before production.
- Use a server-side secrets manager for production. Never expose keys in frontend code or commit `.env`.
- Add atomic uniqueness to the Base44 side if its database supports it; application-level reconciliation alone can be racy.
