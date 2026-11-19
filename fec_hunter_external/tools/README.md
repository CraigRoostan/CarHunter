# Live access diagnostic

From the repository application directory, set `MARKETPLACE_TEST_URL` to a Facebook Marketplace page for which automated access is authorised, then run `python tools/check_marketplace_access.py`. The script makes a single unauthenticated request, prints status and extracted card count, and does not bypass blocks. It does **not** enable live Facebook collection.

The saved-page parser now unescapes HTML-encoded listing links and skips relative image paths instead of inventing unusable Facebook URLs. Local image-file ingestion requires a separate file-to-photo upload adapter.
