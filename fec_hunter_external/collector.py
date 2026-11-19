"""Fast Easy Car Hunter external collector.

Consumes a permitted JSON listing feed or user-provided JSON snapshot, then posts
records to Base44. Does not scrape Facebook or bypass access controls.
"""
import argparse
import hashlib
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

LOG = logging.getLogger('fec_hunter')
DB_PATH = Path(os.getenv('DB_PATH', '/app/data/collector.sqlite'))
ENDPOINT = os.getenv('BASE44_INGEST_URL', 'https://fasteasycar.base44.app/functions/marketplaceIngest')
KEY = os.getenv('BASE44_INGEST_KEY', '')
FEED_URL = os.getenv('PERMITTED_FEED_URL', '')
FEED_TOKEN = os.getenv('PERMITTED_FEED_TOKEN', '')
SOURCE = os.getenv('FEED_SOURCE', 'licensed_feed')
INTERVAL = max(60, int(os.getenv('SCAN_INTERVAL_SECONDS', '300')))


def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute('CREATE TABLE IF NOT EXISTS seen (source TEXT NOT NULL, listing_id TEXT NOT NULL, fingerprint TEXT NOT NULL, last_seen TEXT NOT NULL, PRIMARY KEY(source, listing_id))')
    db.commit()
    return db


def normalize(raw):
    listing_id = str(raw.get('source_listing_id') or raw.get('id') or '').strip()
    price = raw.get('price', raw.get('asking_price'))
    if not listing_id or price is None:
        return None
    try:
        price = float(str(price).replace('£', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return None
    if price <= 0:
        return None
    result = {'source_listing_id': listing_id, 'price': price}
    for key in ('url', 'title', 'make', 'model', 'derivative', 'year', 'mileage', 'location', 'description', 'posted_at', 'area', 'seller_type', 'currency', 'mileage_unit'):
        if raw.get(key) is not None:
            result[key] = raw[key]
    if 'url' not in result and raw.get('listing_url'):
        result['url'] = raw['listing_url']
    images = raw.get('image_urls') or ([raw['image_url']] if raw.get('image_url') else [])
    if isinstance(images, list):
        result['image_urls'] = [u for u in images if isinstance(u, str) and u.startswith('https://')][:12]
    return result


def fingerprint(record):
    important = {k: record.get(k) for k in ('price', 'title', 'year', 'mileage', 'image_urls', 'description')}
    return hashlib.sha256(json.dumps(important, sort_keys=True, default=str).encode()).hexdigest()


def read_feed():
    if not FEED_URL:
        raise RuntimeError('PERMITTED_FEED_URL is unset. Live collection is disabled.')
    parsed = urlparse(FEED_URL)
    if parsed.scheme != 'https':
        raise RuntimeError('Feed URL must use HTTPS')
    headers = {'Authorization': f'Bearer {FEED_TOKEN}'} if FEED_TOKEN else {}
    response = requests.get(FEED_URL, headers=headers, timeout=35)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data = data.get('listings', [])
    if not isinstance(data, list):
        raise ValueError('Feed must return a JSON array or {"listings": [...]}')
    return data


def send_batch(records, dry_run=False):
    if not records:
        return {'created': 0, 'updated': 0, 'received': 0}
    if dry_run:
        LOG.info('DRY RUN: would send %d listings', len(records))
        return {'dry_run': True, 'received': len(records)}
    if not KEY:
        raise RuntimeError('BASE44_INGEST_KEY is unset')
    response = requests.post(ENDPOINT, headers={'x-ingest-key': KEY}, json={'source': SOURCE, 'listings': records}, timeout=60)
    response.raise_for_status()
    data = response.json()
    if not data.get('ok'):
        raise RuntimeError(f'Base44 rejected batch: {data}')
    return data


def run_once(raw_records=None, dry_run=False):
    records = read_feed() if raw_records is None else raw_records
    db = database()
    try:
        unique = {}
        for raw in records:
            normalized = normalize(raw)
            if normalized:
                unique[normalized['source_listing_id']] = normalized
        changed = []
        for listing_id, record in unique.items():
            fp = fingerprint(record)
            prior = db.execute('SELECT fingerprint FROM seen WHERE source=? AND listing_id=?', (SOURCE, listing_id)).fetchone()
            if not prior or prior[0] != fp:
                changed.append((record, fp))
        LOG.info('Read %d records, %d valid unique, %d new/changed', len(records), len(unique), len(changed))
        for offset in range(0, len(changed), 40):
            batch = changed[offset:offset + 40]
            outcome = send_batch([r for r, _ in batch], dry_run=dry_run)
            LOG.info('Ingest response: %s', outcome)
            if not dry_run:
                now = datetime.now(timezone.utc).isoformat()
                db.executemany('INSERT INTO seen(source, listing_id, fingerprint, last_seen) VALUES (?, ?, ?, ?) ON CONFLICT(source, listing_id) DO UPDATE SET fingerprint=excluded.fingerprint, last_seen=excluded.last_seen', [(SOURCE, r['source_listing_id'], fp, now) for r, fp in batch])
                db.commit()
        return len(changed)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--file', type=Path, help='Read an authorised JSON snapshot instead of a live feed')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.file:
        raw = json.loads(args.file.read_text(encoding='utf-8'))
        if isinstance(raw, dict):
            raw = raw.get('listings', [])
        run_once(raw, dry_run=args.dry_run)
        return
    while True:
        try:
            run_once(dry_run=args.dry_run)
        except Exception:
            LOG.exception('Collector cycle failed')
        if args.once:
            break
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
