# Facebook Marketplace: what can and cannot be collected

Written for Phase 2 of the acquisition hunter. This is the finding that decides the
collector's design, so it is recorded here rather than in chat.

## Summary

There is no permitted, commercial way to search Facebook Marketplace for vehicle
listings automatically. The collector therefore does not scrape it, and no source in
this repository pretends to.

## What Meta actually offers

1. **Meta Content Library and API** does expose Marketplace listings
   (`facebook/marketplace-listings/preview`), including keyword, category, price and
   country filters. Access is limited to **approved academic and non-profit
   researchers**, granted per institution, for research use. It is not offered to
   commercial dealers or to agencies acting for them, and the data may not be used to
   run a commercial acquisition pipeline.

2. **Meta Platform Terms and the Automated Data Collection Terms** require Meta's
   **express written permission** before any automated collection of Meta products.
   Marketplace is a Meta product. Permission is not granted to dealers, and the terms
   explicitly cover "Using Collected Data" as well as collecting it.

3. **Third-party Marketplace scrapers** (Apify actors, Bright Data datasets,
   socialapis.io and similar) exist. They are unauthorised automated collection with
   the vendor standing in the middle. Buying one does not create permission, and it
   moves the account-ban and legal exposure onto whoever consumes the data. We have
   not wired one.

4. **Graph API** has no Marketplace listing search endpoint. Vehicle offers under a
   Product Catalog are the dealer's own inventory feed, not a search of other sellers'
   listings.

## Consequence for the hunter

- A Playwright collector pointed at facebook.com/marketplace would have to hold a
  logged-in session, defeat the login wall and rate limits, and rotate identities to
  survive. Each of those is access-control circumvention, which the brief rules out and
  which we will not build.
- Everything else in Phase 2 (incremental polling, deduplication, price history,
  CAP valuation, scoring, ranking, retry with backoff, configurable intervals and
  areas) is independent of the source. It is built and works today.

## Permitted sources that can feed the same pipeline

| Source | Access route | What it needs | Coverage |
| --- | --- | --- | --- |
| eBay UK | Official Browse API | eBay developer account, app client id + secret (free) | National, private and trade, newest-first, price filters |
| AutoTrader | Partner Connect API | Commercial agreement with AutoTrader | Strongest UK retail coverage |
| Motors.co.uk / Car & Classic | Partner feed | Commercial agreement | Retail and classic/older stock |
| Dealer part-exchange feeds | Supplier feed | Agreement with each supplier | Trade stock, not private sellers |
| Manual capture | Human browsing, pasted into the API | Nothing | Whatever your team is looking at |

The collector is written against a source interface, so any of these is an adapter,
not a rebuild. eBay is implemented and works as soon as credentials are added.

## What to do next

1. Add eBay credentials to the collector host (`EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`)
   and enable the eBay source in the dashboard.
2. Run the collector with `RUN_ONCE=1` to confirm listings arrive and score.
3. Decide whether AutoTrader or a licensed feed is worth the commercial agreement. If
   it is, that becomes a second adapter and the dashboard does not change.
4. If someone offers a "Facebook Marketplace API", ask for Meta's written permission
   covering your use. Without it, the answer is no.
