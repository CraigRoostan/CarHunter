# CarHunter Facebook Marketplace — authorised Railway collector

This source is enabled in code but **does not collect** unless all three gates are met:
1. `FACEBOOK_COLLECTION_AUTHORISED=yes` is set on Railway, reflecting your documented permission.
2. A manually authenticated Playwright storage state has been securely provisioned.
3. Base44 Collector is enabled and its `sources` configuration includes `facebook_marketplace`.

## Local session export

On your Mac, close other Playwright test browsers, activate your virtual environment, and run:

```sh
python tools/export_facebook_state.py
```

Log into Facebook yourself if prompted. Once vehicle cards are visible, press Enter. The script writes `~/.carhunter/facebook-state.b64` with mode 0600. **This is an authentication secret, equivalent to a password.** Never commit, upload to ChatGPT, send by email or put it in logs. It may expire or be invalidated when used on another host; Facebook may require verification again. If that happens, collection pauses; no login bypass is attempted.

To provision, open Railway **development** service → Variables → add `FACEBOOK_STORAGE_STATE_B64` with the **entire contents** of the local `.b64` file, using a private variable/secret entry. Do not paste it into chat. Remove it from Railway after the first successful run if the persistent `/app/data/facebook-state.json` file has been created, and do not remove the volume. Protect Railway project access and rotate the Facebook session if it is exposed. Session transfer is a sensitive operation; only use it where your permission and Facebook's security requirements allow.

## Railway variables

- `INGEST_KEY`: existing Base44 ingest key
- `BASE44_URL=https://fasteasycar.base44.app`
- `HUNTER_DB=/app/data/hunter.sqlite3` (or `DB_PATH=/app/data/collector.sqlite` when `HUNTER_DB` is unset)
- `FACEBOOK_COLLECTION_AUTHORISED=yes`
- `FACEBOOK_STORAGE_STATE_B64`: session secret from local export, for first bootstrap
- `FACEBOOK_STATE_PATH=/app/data/facebook-state.json`
- `FACEBOOK_VEHICLES_URL=https://www.facebook.com/marketplace/category/vehicles/`
- `FACEBOOK_MAX_CARDS=20`
- `FACEBOOK_MAX_DETAILS=8`

Volume must be mounted at `/app/data`. Keep **one Railway replica** and the collector disabled in Base44 until ready. No need to set `SCAN_INTERVAL_SECONDS`: this code reads `interval_minutes` from Base44 configuration. Set **5 minutes** in the Base44 Collector dashboard. If Base44 does not offer `facebook_marketplace` as a source, its source configuration/UI must be updated separately; this ZIP cannot change Base44's backend.

## First deployment test

1. Deploy `dev` to Railway **development**; leave Base44 collector disabled.
2. Configure Railway variables above and the volume.
3. Enable only `facebook_marketplace` in Base44 and set a conservative price range. Enable the collector.
4. Watch Railway logs for `Cycle ...` and Base44 dashboard for ingested listings.
5. Confirm duplicates are not created on the next cycle. Turn off collector if login/verification or access errors appear.

**Known limitations:** Facebook may not accept transferred sessions; this does not provide interactive login on Railway. The category page uses your account's Marketplace location and may include motorcycles, dealers and vehicles outside Kent. Location and seller-type filters are not yet enforced by this source. The first visible image URL is sent but may expire. Only the first 8 eligible new/repriced listings have details fetched per cycle. Listings without mileage may not match CAP precisely. Detail extraction is based on visible text and can include irrelevant UI text. Do not treat seller claims as verified. The code does not attempt to evade challenges, rotate proxies, spoof fingerprints or bypass login restrictions.
