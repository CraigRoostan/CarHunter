"""Facebook Marketplace collector for an authorised, authenticated browser session."""

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..normalise import parse_title, redact_contact
from .base import Listing, Source, SourceBlocked, SourceUnavailable

log = logging.getLogger('hunter.facebook')
ITEM_RE = re.compile(r'/marketplace/item/(\d+)')
PRICE_RE = re.compile(r'£\s*([\d,]+)')
LOGIN_MARKERS = ('/login/', '/checkpoint/', '/recover/', '/marketplace/ineligible/')
DESCRIPTION_START = re.compile(r"Seller[’']s description\s*", re.I)
DESCRIPTION_END = re.compile(
    r'\n\s*(?:See more|See less|Location is approximate|Learn more about purchasing|'
    r'Today[’\']s picks|Message seller|Seller information|Seller details)\b', re.I
)
MILEAGE_WITH_UNIT = re.compile(
    r'\b(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{1,3}(?:\.\d+)?)\s*'
    r'(k)?\s*(miles?|mi|km)\b', re.I
)
MILEAGE_LABEL = re.compile(
    r'\b(?:mileage|odometer)\s*[:\-]\s*(\d{1,3}(?:,\d{3})+|\d{4,6})\b', re.I
)


def parse_card(text: str, href: str, image_url: str = '') -> Dict[str, Any]:
    match = ITEM_RE.search(href or '')
    price = PRICE_RE.search(text or '')
    if not match or not price:
        return {}
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    price_index = next((i for i, line in enumerate(lines) if PRICE_RE.search(line)), -1)
    title = next((line for line in lines[price_index + 1:]
                  if re.search(r'\b(?:19|20)\d{2}\b', line)), '')
    if not title:
        return {}
    title_index = lines.index(title)
    location = lines[title_index + 1] if title_index + 1 < len(lines) else ''
    parsed = parse_title(title)
    if not parsed.get('model') and parsed.get('make'):
        numeric_model = re.search(
            r'\b' + re.escape(str(parsed['make'])) + r'\s+(\d{1,4}(?:[A-Za-z-]+)?)\b',
            title, re.I,
        )
        if numeric_model:
            parsed['model'] = numeric_model.group(1)
    listing_id = match.group(1)
    return {
        'source_listing_id': listing_id,
        'price': int(price.group(1).replace(',', '')),
        'title': title,
        'url': f'https://www.facebook.com/marketplace/item/{listing_id}/',
        'location': location,
        'image_urls': [image_url] if image_url.startswith('https://') else [],
        **parsed,
    }


def extract_description(page_text: str) -> Optional[str]:
    """Only use the seller-description section, never navigation or recommendations."""
    match = DESCRIPTION_START.search(page_text or '')
    if not match:
        return None
    tail = page_text[match.end():]
    end = DESCRIPTION_END.search(tail)
    description = (tail[:end.start()] if end else tail).strip()
    # If the section boundary is not identifiable, do not ingest unrelated page text.
    if end is None or not description:
        return None
    return description


def extract_mileage(description: str) -> Optional[int]:
    """Read explicitly stated mileage from a verified seller description."""
    if not description:
        return None
    labelled = MILEAGE_LABEL.search(description)
    if labelled:
        value = int(labelled.group(1).replace(',', ''))
        return value if 100 <= value <= 1000000 else None
    match = MILEAGE_WITH_UNIT.search(description)
    if not match:
        return None
    value = float(match.group(1).replace(',', ''))
    if match.group(2):
        value *= 1000
    if match.group(3).lower() == 'km':
        value /= 1.609344
    result = round(value)
    return result if 100 <= result <= 1000000 else None


def extract_seller_phone(description: str) -> str:
    """Return a UK mobile number explicitly included in the seller description.

    Do not inspect Marketplace navigation, recommendations, or other listings.
    Numbers are normalised to their UK domestic form (07xxxxxxxxx).
    """
    if not description:
        return ''
    phone_pattern = re.compile(
        r'(?<![\w\d])(?:\+44[\s.-]*(?:\(0\)[\s.-]*)?7|07)'
        r'(?:[\s().-]*\d){9}(?!\d)',
        re.I,
    )
    for match in phone_pattern.finditer(description):
        raw = match.group(0)
        digits = re.sub(r'\D', '', raw)
        if digits.startswith('44'):
            digits = '0' + digits[2:]
        if len(digits) == 11 and digits.startswith('07'):
            return digits
    return ''


def parse_detail(page_text: str) -> Dict[str, Any]:
    description = extract_description(page_text)
    if not description:
        return {}
    result: Dict[str, Any] = {}
    phone = extract_seller_phone(description)
    if phone:
        result['seller_phone'] = phone
    mileage = extract_mileage(description)
    if mileage is not None:
        result['mileage'] = mileage
    cleaned = redact_contact(description, 4000)
    if cleaned:
        result['description'] = cleaned
    return result


def extract_vehicle_images(page, title: str) -> List[str]:
    """Collect listing-specific product photos, excluding Marketplace recommendations.

    Facebook currently labels gallery images "Product photo of <vehicle title>".
    If that markup changes, keep the card image rather than guessing.
    """
    expected = re.sub(r"\s+", " ", title or "").strip().casefold()
    if not expected:
        return []
    result: List[str] = []
    seen = set()
    images = page.locator('img[alt]')
    for index in range(min(images.count(), 100)):
        img = images.nth(index)
        try:
            alt = re.sub(r"\s+", " ", img.get_attribute('alt') or '').strip()
            prefix = 'product photo of '
            if not alt.casefold().startswith(prefix):
                continue
            photo_title = alt[len(prefix):].strip().casefold()
            if photo_title != expected:
                continue
            url = img.get_attribute('src') or ''
            if not url.startswith('https://') or 'fbcdn.net/' not in url:
                continue
            if url not in seen:
                result.append(url)
                seen.add(url)
        except Exception as error:
            log.debug('Skipping gallery image: %s', error)
    return result


class FacebookMarketplaceSource(Source):
    key = 'facebook_marketplace'
    label = 'Facebook Marketplace (authorised browser)'
    min_interval_minutes = 5
    available = True

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        if os.environ.get('FACEBOOK_COLLECTION_AUTHORISED') != 'yes':
            raise SourceUnavailable('Set FACEBOOK_COLLECTION_AUTHORISED=yes only when expressly authorised.')

        state_path = Path(os.environ.get('FACEBOOK_STATE_PATH', '/app/data/facebook-state.json'))
        state_b64 = os.environ.get('FACEBOOK_STORAGE_STATE_B64', '')
        if not state_path.exists() and not state_b64:
            raise SourceUnavailable('No authenticated Facebook browser state.')
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if not state_path.exists() and state_b64:
            try:
                state = json.loads(base64.b64decode(state_b64, validate=True))
                if not isinstance(state, dict) or 'cookies' not in state:
                    raise ValueError('Invalid Playwright storage state')
                state_path.write_text(json.dumps(state), encoding='utf-8')
                state_path.chmod(0o600)
            except (ValueError, json.JSONDecodeError) as error:
                raise SourceUnavailable('Invalid FACEBOOK_STORAGE_STATE_B64.') from error

        from playwright.sync_api import sync_playwright
        url = os.environ.get('FACEBOOK_VEHICLES_URL',
                             'https://www.facebook.com/marketplace/category/vehicles/')
        if not url.startswith('https://www.facebook.com/marketplace/'):
            raise SourceUnavailable('Invalid Facebook Marketplace URL.')
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
                    raise SourceBlocked(f'Facebook returned HTTP {response.status}')
                try:
                    page.locator('a[href*="/marketplace/item/"]').first.wait_for(timeout=15000)
                except Exception:
                    pass
                if any(marker in page.url.lower() for marker in LOGIN_MARKERS):
                    raise SourceBlocked('Facebook login or verification required.')
                cards = page.locator('a[href*="/marketplace/item/"]')
                count = min(cards.count(), max_cards)
                if count == 0:
                    raise SourceUnavailable('No Marketplace vehicle cards visible.')
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
                    if not record:
                        continue
                    listing_id = record['source_listing_id']
                    if listing_id in seen:
                        continue
                    seen.add(listing_id)
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
                            response = detail_page.goto(record['url'],
                                                        wait_until='domcontentloaded', timeout=30000)
                            if response and response.status in (401, 403, 429):
                                raise SourceBlocked('Facebook denied detail-page access.')
                            if any(marker in detail_page.url.lower() for marker in LOGIN_MARKERS):
                                raise SourceBlocked('Facebook login required.')
                            try:
                                detail_page.get_by_text("Seller's description", exact=True).first.wait_for(timeout=8000)
                            except Exception:
                                try:
                                    detail_page.get_by_text('Seller’s description', exact=True).first.wait_for(timeout=3000)
                                except Exception:
                                    log.warning('Seller description missing for %s', record['source_listing_id'])
                            page_text = detail_page.locator('body').inner_text(timeout=5000)
                            record.update(parse_detail(page_text))
                            gallery = extract_vehicle_images(detail_page, record['title'])
                            if gallery:
                                record['image_urls'] = gallery
                        except SourceBlocked:
                            raise
                        except Exception as error:
                            log.info('Detail unavailable for %s: %s',
                                     record['source_listing_id'], type(error).__name__)
                        finally:
                            detail_page.close()
                    found.append(Listing(source=self.key, **record))
                context.storage_state(path=str(state_path))
                state_path.chmod(0o600)
            finally:
                browser.close()
        return found
