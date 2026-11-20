"""Authorised Facebook Marketplace browser collector.

Requires the operator's explicit permission and a manually established session.
No password automation, CAPTCHA solving, stealth or access-control workarounds.
"""
import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin

from ..normalise import parse_title, redact_contact
from .base import Listing, Source, SourceBlocked, SourceUnavailable

log = logging.getLogger('hunter.facebook')
ITEM_RE = re.compile(r'/marketplace/item/(\d+)')
PRICE_RE = re.compile(r'£\s*([\d,]+)')
MILEAGE_RE = re.compile(r'\b(?:Driven\s+)?([\d,]+)\s*(km|miles|mi)\b', re.I)
LOGIN_MARKERS = ('/login/', '/checkpoint/', '/recover/')


def parse_card(text: str, href: str, image_url: str = '') -> Dict[str, Any]:
    """Parse visible card text; preserve source identity without tracking params."""
    match = ITEM_RE.search(href or '')
    price = PRICE_RE.search(text or '')
    if not match or not price:
        return {}
    lines = [s.strip() for s in (text or '').splitlines() if s.strip()]
    price_index = next((i for i, line in enumerate(lines) if PRICE_RE.search(line)), -1)
    title = next((line for line in lines[price_index + 1:] if re.search(r'\b(?:19|20)\d{2}\b', line)), '')
    if not title:
        return {}
    title_index = lines.index(title)
    location = lines[title_index + 1] if title_index + 1 < len(lines) else ''
    parsed = parse_title(title)
    return {
        'source_listing_id': match.group(1),
        'price': int(price.group(1).replace(',', '')),
        'title': title,
        'url': f'https://www.facebook.com/marketplace/item/{match.group(1)}/',
        'location': location,
        'image_urls': [image_url] if image_url and image_url.startswith('https://') else [],
        **parsed,
    }


def parse_detail(text: str) -> Dict[str, Any]:
    """Extract only visible fields. UK valuation mileage is expressed in miles."""
    match = MILEAGE_RE.search(text or '')
    data: Dict[str, Any] = {'description': redact_contact(text or '', 4000)}
    if match:
        amount = int(match.group(1).replace(',', ''))
        unit = match.group(2).lower()
        data['mileage'] = round(amount / 1.609344) if unit == 'km' else amount
        data['description'] = (f'[Displayed mileage: {amount:,} {unit}; converted to miles for valuation]\n' + data['description'])[:4000]
    return data


class FacebookMarketplaceSource(Source):
    key = 'facebook_marketplace'
    label = 'Facebook Marketplace (authorised browser)'
    min_interval_minutes = 5
    available = True

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        if os.environ.get('FACEBOOK_COLLECTION_AUTHORISED') != 'yes':
            raise SourceUnavailable('Set FACEBOOK_COLLECTION_AUTHORISED=yes only when collection is expressly authorised.')

        state_path = Path(os.environ.get('FACEBOOK_STATE_PATH', '/app/data/facebook-state.json'))
        state_b64 = os.environ.get('FACEBOOK_STORAGE_STATE_B64', '')
        if not state_path.exists() and not state_b64:
            raise SourceUnavailable('No authenticated Facebook browser state. Perform manual login and provision state securely.')
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if not state_path.exists() and state_b64:
            try:
                state = json.loads(base64.b64decode(state_b64, validate=True))
                if not isinstance(state, dict) or 'cookies' not in state:
                    raise ValueError('Invalid Playwright storage state')
                state_path.write_text(json.dumps(state), encoding='utf-8')
                state_path.chmod(0o600)
            except (ValueError, json.JSONDecodeError) as error:
                raise SourceUnavailable('Invalid FACEBOOK_STORAGE_STATE_B64; export a valid Playwright storage state.') from error

        from playwright.sync_api import sync_playwright
        url = os.environ.get('FACEBOOK_VEHICLES_URL', 'https://www.facebook.com/marketplace/category/vehicles/')
        if not url.startswith('https://www.facebook.com/marketplace/'):
            raise SourceUnavailable('FACEBOOK_VEHICLES_URL must be a facebook.com Marketplace page.')
        max_cards = min(max(int(os.environ.get('FACEBOOK_MAX_CARDS', '20')), 1), 50)
        max_details = min(max(int(os.environ.get('FACEBOOK_MAX_DETAILS', '8')), 0), 20)
        found: List[Listing] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(storage_state=str(state_path), locale='en-GB')
                context.set_default_timeout(15000)
                page = context.new_page()
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                if response and response.status in (401, 403, 429):
                    raise SourceBlocked(f'Facebook returned HTTP {response.status}; collection paused.')
                try:
                    page.locator('a[href*="/marketplace/item/"]').first.wait_for(timeout=15000)
                except Exception:
                    pass
                if any(marker in page.url.lower() for marker in LOGIN_MARKERS):
                    raise SourceBlocked('Facebook session expired or verification required. Manual login needed.')
                cards = page.locator('a[href*="/marketplace/item/"]')
                count = min(cards.count(), max_cards)
                if count == 0:
                    raise SourceUnavailable('No vehicle cards visible; check login, category and page rendering manually.')
                records: List[Dict[str, Any]] = []
                seen = set()
                for index in range(count):
                    card = cards.nth(index)
                    try:
                        href = card.get_attribute('href') or ''
                        text = card.inner_text(timeout=3000)
                        image = card.locator('img').first
                        image_url = image.get_attribute('src', timeout=2000) if image.count() else ''
                        record = parse_card(text, href, image_url or '')
                    except Exception as error:
                        log.debug('Skipping unreadable card: %s', error)
                        continue
                    if not record or record['source_listing_id'] in seen:
                        continue
                    seen.add(record['source_listing_id'])
                    if not (config['price_min'] <= record['price'] <= config['price_max']):
                        continue
                    records.append(record)

                for record_index, record in enumerate(records):
                    if len(found) >= max_cards:
                        break
                    known = store.known_price(self.key, record['source_listing_id'])
                    if known is not None and known == record['price']:
                        continue
                    if record_index < max_details:
                        detail_page = context.new_page()
                        try:
                            response = detail_page.goto(record['url'], wait_until='domcontentloaded', timeout=30000)
                            if response and response.status in (401, 403, 429):
                                raise SourceBlocked(f'Facebook returned HTTP {response.status} on detail page.')
                            if any(marker in detail_page.url.lower() for marker in LOGIN_MARKERS):
                                raise SourceBlocked('Facebook login required on detail page.')
                            detail_text = detail_page.locator('[role="dialog"]').last.inner_text(timeout=5000) if detail_page.locator('[role="dialog"]').count() else detail_page.locator('body').inner_text(timeout=5000)
                            record.update(parse_detail(detail_text))
                        except SourceBlocked:
                            raise
                        except Exception as error:
                            log.info('Detail unavailable for %s: %s', record['source_listing_id'], type(error).__name__)
                        finally:
                            detail_page.close()
                    found.append(Listing(source=self.key, **record))
                context.storage_state(path=str(state_path))
                state_path.chmod(0o600)
            finally:
                browser.close()
        return found
