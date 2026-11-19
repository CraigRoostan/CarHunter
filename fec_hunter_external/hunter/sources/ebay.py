"""eBay UK, through the official Browse API.

This is a permitted source: eBay publishes the API for exactly this purpose. It needs an
eBay developer account and the app's client id and secret, set on the collector host.

Incremental behaviour: results come back newest-first, and paging stops as soon as a
whole page is already known. Every `full_sweep_every` cycles the stop is skipped, so an
older listing that drops its price is still noticed.
"""

import base64
import os
import time
from typing import Any, Dict, List, Optional

from ..normalise import clean, match_area, parse_title, redact_contact
from .base import Listing, Source, SourceUnavailable

TOKEN_URL = 'https://api.ebay.com/identity/v1/oauth2/token'
SEARCH_URL = 'https://api.ebay.com/buy/browse/v1/item_summary/search'
SCOPE = 'https://api.ebay.com/oauth/api_scope'
PAGE_SIZE = 200


class EbaySource(Source):
    key = 'ebay'
    label = 'eBay UK (official Browse API)'
    min_interval_minutes = 5
    available = True

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.client_id = (os.environ.get('EBAY_CLIENT_ID') or '').strip()
        self.client_secret = (os.environ.get('EBAY_CLIENT_SECRET') or '').strip()
        self._token = ''
        self._token_expires = 0.0

    def _access_token(self) -> str:
        import requests  # imported here so the package loads without the HTTP client

        if self._token and time.time() < self._token_expires - 60:
            return self._token

        if not (self.client_id and self.client_secret):
            raise SourceUnavailable(
                'eBay is enabled but this host has no EBAY_CLIENT_ID and EBAY_CLIENT_SECRET. '
                'Create an app in the eBay developer programme and add both to .env.'
            )

        credentials = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode()
        response = requests.post(
            TOKEN_URL,
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            data={'grant_type': 'client_credentials', 'scope': SCOPE},
            timeout=30,
        )
        if response.status_code != 200:
            raise SourceUnavailable(f'eBay rejected the app credentials (HTTP {response.status_code}).')

        data = response.json()
        self._token = data.get('access_token', '')
        self._token_expires = time.time() + int(data.get('expires_in', 7200))
        if not self._token:
            raise SourceUnavailable('eBay returned no access token.')
        return self._token

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        import requests

        token = self._access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_GB',
        }
        filters = ','.join([
            f"price:[{config['price_min']}..{config['price_max']}]",
            'priceCurrency:GBP',
            'itemLocationCountry:GB',
            'buyingOptions:{FIXED_PRICE}',
        ])

        full_sweep = config['full_sweep_every'] > 0 and cycle % config['full_sweep_every'] == 0
        listings: List[Listing] = []
        seen_ids = set()

        for page in range(config['max_pages']):
            params = {
                'q': 'car',
                'filter': filters,
                'sort': 'newlyListed',
                'limit': PAGE_SIZE,
                'offset': page * PAGE_SIZE,
            }
            response = requests.get(SEARCH_URL, headers=headers, params=params, timeout=30)

            if response.status_code == 429:
                raise SourceUnavailable('eBay rate limit reached. The collector will back off and retry.')
            if response.status_code != 200:
                raise SourceUnavailable(f'eBay search failed (HTTP {response.status_code}).')

            items = response.json().get('itemSummaries') or []
            if not items:
                break

            fresh = 0
            for item in items:
                listing = self._to_listing(item, config)
                if listing is None or listing.source_listing_id in seen_ids:
                    continue
                seen_ids.add(listing.source_listing_id)
                listings.append(listing)
                if store.known_price(self.key, listing.source_listing_id) != listing.price:
                    fresh += 1

            if len(items) < PAGE_SIZE:
                break
            if fresh == 0 and not full_sweep:
                break

        return listings

    def _to_listing(self, item: Dict[str, Any], config: Dict[str, Any]) -> Optional[Listing]:
        item_id = str(item.get('itemId') or '').strip()
        price_block = item.get('price') or {}
        try:
            price = int(round(float(price_block.get('value'))))
        except (TypeError, ValueError):
            return None
        if not item_id or price <= 0:
            return None
        if not (config['price_min'] <= price <= config['price_max']):
            return None

        title = clean(item.get('title'), 300)
        parsed = parse_title(title)

        location_block = item.get('itemLocation') or {}
        location_parts = [
            clean(location_block.get('city'), 80),
            clean(location_block.get('postalCode'), 16),
        ]
        location = ', '.join([part for part in location_parts if part])

        area = match_area(location, config['areas'])
        if area is None and config.get('require_area', True):
            return None

        images = []
        main_image = (item.get('image') or {}).get('imageUrl')
        if isinstance(main_image, str):
            images.append(main_image)
        for extra in item.get('additionalImages') or []:
            url = (extra or {}).get('imageUrl')
            if isinstance(url, str):
                images.append(url)
        images = [url for url in images if url.startswith('http')][:12]

        return Listing(
            source=self.key,
            source_listing_id=item_id,
            price=price,
            title=title,
            url=clean(item.get('itemWebUrl'), 1200),
            make=parsed.get('make', ''),
            model=parsed.get('model', ''),
            year=parsed.get('year'),
            mileage=parsed.get('mileage'),
            location=location,
            area=area or '',
            description=redact_contact(item.get('shortDescription') or '', 4000),
            image_urls=images,
            posted_at=clean(item.get('itemCreationDate'), 40),
            seller_type='unknown',
        )