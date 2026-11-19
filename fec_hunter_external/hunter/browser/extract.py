"""Turn a page into listing records.

Standard library only, so it can be tested offline against saved pages and maintained
without touching the browser session, the scheduler or the ingest client. That boundary
is deliberate: when a site changes its markup, only this module and its profile change.

Extraction order is structured first (JSON-LD, then OpenGraph, then a profile pattern),
because structured data is both the most reliable and the least likely to be wrong.

Nothing is invented. A field that is not on the page is left out, and a record without a
listing id and a price is rejected outright, because the ingestion API requires a price.
"""

import json
import re
from datetime import datetime
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from ..normalise import match_area, parse_title, strip_tags

SCRIPT_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
META_RE = re.compile(r'<meta\b[^>]*>', re.IGNORECASE)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*["\']([^"\']*)["\']')
ANCHOR_RE = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.IGNORECASE | re.DOTALL)
IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
PRICE_TEXT_RE = re.compile(r'£\s?([\d,]+(?:\.\d{1,2})?)')
NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')
GENERIC_ID_RE = r'/(?:item|listing|ad|vehicles?)/(\d{4,})'

VEHICLE_TYPES = {'vehicle', 'car', 'motorcycle', 'product', 'offer'}


def _attrs(raw: str) -> Dict[str, str]:
    return {key.lower(): value for key, value in ATTR_RE.findall(raw or '')}


def meta_map(html: str) -> Dict[str, str]:
    """Every meta tag, keyed by property or name. First occurrence wins."""
    result: Dict[str, str] = {}
    for tag in META_RE.findall(html):
        attrs = _attrs(tag)
        key = (attrs.get('property') or attrs.get('name') or '').lower()
        content = attrs.get('content')
        if key and content is not None and key not in result:
            result[key] = unescape(content).strip()
    return result


def _walk_json(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _walk_json(item)
    elif isinstance(node, dict):
        yield node
        for value in node.values():
            if isinstance(value, (dict, list)):
                yield from _walk_json(value)


def json_ld_blocks(html: str) -> List[Any]:
    blocks = []
    for match in SCRIPT_RE.finditer(html):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except ValueError:
            continue
    return blocks


def to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        amount = int(round(value))
        return amount if amount > 0 else None
    if isinstance(value, str):
        match = NUMBER_RE.search(value.replace(',', ''))
        if not match:
            return None
        amount = int(round(float(match.group(0))))
        return amount if 0 < amount <= 10_000_000 else None
    return None


def price_from_text(text: str) -> Optional[int]:
    """Only a currency-marked amount counts, so a year is never read as a price."""
    match = PRICE_TEXT_RE.search(text or '')
    if not match:
        return None
    return to_int(match.group(1))


def _iso(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ''
    text = value.strip().replace('Z', '+00:00')
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return ''
    return value.strip()[:40]


def _offer_price(node: Dict[str, Any]) -> Optional[int]:
    offers = node.get('offers')
    candidates = offers if isinstance(offers, list) else [offers]
    for offer in candidates:
        if not isinstance(offer, dict):
            continue
        for key in ('price', 'lowPrice', 'highPrice'):
            amount = to_int(offer.get(key))
            if amount:
                return amount
        spec = offer.get('priceSpecification')
        if isinstance(spec, dict):
            amount = to_int(spec.get('price'))
            if amount:
                return amount
    return to_int(node.get('price'))


def _image_list(value: Any) -> List[str]:
    items = value if isinstance(value, list) else [value]
    urls: List[str] = []
    for item in items:
        if isinstance(item, str) and item.startswith('http'):
            urls.append(item)
        elif isinstance(item, dict) and isinstance(item.get('url'), str) and item['url'].startswith('http'):
            urls.append(item['url'])
    return urls[:12]


def _location(value: Any) -> str:
    if isinstance(value, str):
        return strip_tags(value)[:200]
    if isinstance(value, dict):
        address = value.get('address') if isinstance(value.get('address'), dict) else value
        parts = [address.get('addressLocality'), address.get('addressRegion'), address.get('postalCode')]
        return ', '.join([str(part) for part in parts if part])[:200]
    return ''


def _json_ld_fields(html: str) -> Dict[str, Any]:
    for block in json_ld_blocks(html):
        for node in _walk_json(block):
            types = node.get('@type')
            types = [types] if isinstance(types, str) else (types or [])
            if not ({str(item).lower() for item in types} & VEHICLE_TYPES):
                continue
            if not isinstance(node.get('name'), str):
                continue
            return {
                'title': strip_tags(node['name']),
                'price': _offer_price(node),
                'description': strip_tags(node.get('description') or '')[:4000],
                'images': _image_list(node.get('image')),
                'location': _location(node.get('areaServed') or node.get('availableAtOrFrom') or node.get('location')),
                'posted_at': _iso(node.get('datePosted') or node.get('datePublished')),
            }
    return {}


def _first_pattern(html: str, pattern: Optional[str]) -> str:
    if not pattern:
        return ''
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    return strip_tags(match.group(1)) if match else ''


def _listing_id(page_url: str, profile: Dict[str, Any], meta: Dict[str, str]) -> str:
    """The source's own id, taken from the page URL or its canonical URL.

    The profile's pattern is tried first, because it knows that site's URL shape. The
    generic pattern is the fallback for a saved page whose canonical URL points at a
    different host, which happens whenever a browser rewrites links on save.
    """
    for pattern in (profile.get('id_regex'), GENERIC_ID_RE):
        if not pattern:
            continue
        for candidate in (page_url or '', meta.get('og:url', '')):
            match = re.search(pattern, candidate)
            if match:
                return match.group(1)
    return ''


def extract_detail(html: str, page_url: str, profile: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """One listing from a detail page. Returns None when it cannot be trusted."""
    profile = profile or {}
    meta = meta_map(html)
    structured = _json_ld_fields(html)

    title = (structured.get('title') or meta.get('og:title') or meta.get('twitter:title')
             or _first_pattern(html, profile.get('title_pattern')))
    title = strip_tags(title)[:300]

    price = structured.get('price')
    if not price:
        price = to_int(meta.get('product:price:amount')) or price_from_text(meta.get('og:description', ''))
    if not price:
        price = price_from_text(_first_pattern(html, profile.get('price_pattern')))
    if not price:
        # A detail page carries one asking price; the first currency amount is it.
        price = price_from_text(strip_tags(html)[:120000])

    listing_id = _listing_id(page_url, profile, meta)
    if not listing_id or not price:
        return None

    description = (structured.get('description') or meta.get('og:description')
                   or _first_pattern(html, profile.get('description_pattern')))

    images = structured.get('images') or []
    if not images:
        og_image = meta.get('og:image', '')
        if og_image.startswith('http'):
            images = [og_image]
        elif og_image.startswith('/'):
            images = [urljoin(page_url, og_image)]

    location = structured.get('location') or _first_pattern(html, profile.get('location_pattern'))
    posted_at = (structured.get('posted_at') or _iso(meta.get('article:published_time'))
                 or _first_pattern(html, profile.get('posted_pattern')))

    parsed = parse_title(title)
    # Mileage is often only in the description. A year is never taken from prose, because
    # "MOT until 2027" is not a registration year.
    if not parsed.get('mileage') and description:
        from_description = parse_title(description)
        if from_description.get('mileage'):
            parsed['mileage'] = from_description['mileage']

    return {
        'source_listing_id': listing_id,
        'url': meta.get('og:url') or page_url,
        'title': title,
        'price': price,
        'make': parsed.get('make', ''),
        'model': parsed.get('model', ''),
        'year': parsed.get('year'),
        'mileage': parsed.get('mileage'),
        'location': location[:200],
        'description': description[:4000],
        'image_urls': images[:12],
        'posted_at': posted_at,
    }


def extract_cards(html: str, base_url: str, profile: Optional[Dict[str, Any]] = None,
                  areas: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Listing cards from a results page.

    Site-agnostic: any anchor whose href carries a listing id is a candidate, and the
    price is read from the card's own text. A card without a price is skipped rather
    than guessed at.
    """
    profile = profile or {}
    pattern = profile.get('id_regex') or GENERIC_ID_RE
    results: List[Dict[str, Any]] = []
    seen = set()

    for match in ANCHOR_RE.finditer(html):
        attrs = _attrs(match.group(1))
        href = attrs.get('href') or ''
        id_match = re.search(pattern, href)
        if not id_match:
            continue

        listing_id = id_match.group(1)
        if listing_id in seen:
            continue

        inner = match.group(2)
        text = strip_tags(inner)

        # The price must be inside the card itself. Reading past the anchor would pick up
        # the next card's price and attribute it to this vehicle.
        price = price_from_text(text)
        if not price:
            continue

        seen.add(listing_id)
        title = PRICE_TEXT_RE.sub('', text).strip(' -·|')[:300]

        image = ''
        img = IMG_RE.search(inner)
        if img:
            image = _attrs(img.group(0)).get('src', '')
        if image and not image.startswith('http'):
            image = urljoin(base_url, image)

        area = match_area(text, areas or [])

        results.append({
            'source_listing_id': listing_id,
            'url': urljoin(base_url, href),
            'title': title,
            'price': price,
            'location': area or '',
            'area': area or '',
            'image_urls': [image] if image else [],
        })

    return results