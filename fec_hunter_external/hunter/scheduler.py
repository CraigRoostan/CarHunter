"""The scan loop.

One pass polls every enabled source, deduplicates across search areas, sends only what
is new or repriced, then waits. Cycles never overlap: the loop is sequential and a lock
file stops a second process using the same database.
"""

import logging
import os
import random
import socket
import time
from typing import Any, Dict, Iterable, List

from . import VERSION
from . import photos as photo_library
from .api import ApiError
from .settings import normalise_config
from .sources import build_source
from .sources.base import Listing, SourceBlocked, SourceUnavailable

log = logging.getLogger('hunter')

BATCH_SIZE = 200
MAX_BACKOFF_SECONDS = 1800


def heartbeat_path(db_path: str) -> str:
    """A file the host's health check can watch to prove the loop is still alive."""
    return os.path.join(os.path.dirname(os.path.abspath(db_path)) or '.', 'collector.heartbeat')


def touch_heartbeat(db_path: str) -> None:
    try:
        with open(heartbeat_path(db_path), 'w', encoding='utf-8') as handle:
            handle.write(str(int(time.time())))
    except OSError:
        pass


def _group_by_source(listings: Iterable[Listing]) -> Dict[str, List[Listing]]:
    groups: Dict[str, List[Listing]] = {}
    for listing in listings:
        groups.setdefault(listing.source, []).append(listing)
    return groups


def _chunks(items: List[Listing], size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _send_photos(api: Any, store: Any, source_key: str, listings: List[Listing], notes: List[str]) -> None:
    """Store photographs for the listings just sent.

    Only listings whose photographs changed are downloaded, and a signature is remembered
    only after Base44 accepted the files, so a failure retries and a repeat scan uploads
    nothing. A photograph that cannot be fetched costs that picture, never the cycle.
    """
    pending = []
    for listing in listings:
        urls = [url for url in (listing.image_urls or []) if isinstance(url, str)]
        if not urls:
            continue
        key = photo_library.signature(urls)
        if store.photo_key(listing.source, listing.source_listing_id) == key:
            continue
        pending.append((listing, key))

    if not pending:
        return

    prepared = []
    for listing, key in pending:
        try:
            images = photo_library.collect(listing)
        except Exception as error:  # a broken picture must not stop the batch
            log.warning('Photographs failed for %s: %s', listing.source_listing_id, error)
            continue
        if images:
            prepared.append({
                'source_listing_id': listing.source_listing_id,
                'source_key': key,
                'images': images,
            })

    if not prepared:
        return

    try:
        response = api.send_photos(source_key, prepared)
        for entry in prepared:
            store.remember_photos(source_key, entry['source_listing_id'], entry['source_key'])
        notes.append(f"{source_key}: {response.get('stored', 0)} photographs stored")
    except ApiError as error:
        notes.append(f'{source_key}: photographs not stored ({error})')
        log.error('Photographs not stored: %s', error)


def run_cycle(api: Any, store: Any, config: Dict[str, Any], cycle: int = 0) -> Dict[str, Any]:
    """One pass over every enabled source."""
    scan_id = store.start_scan()
    notes: List[str] = []
    scanned = 0
    sent = 0

    try:
        # Keyed on source + listing id, so a car found in three search areas goes once.
        collected: Dict[tuple, Listing] = {}

        for key in config['sources']:
            blocked = store.blocked_reason(key)
            if blocked:
                notes.append(f'{key}: {blocked}')
                continue

            try:
                source = build_source(key, config)
                found = source.collect(config, store, cycle)
            except SourceBlocked as error:
                # Six hours, then a week: knocking again is not going to help.
                cooldown = 6 * 60 if store.block_hits(key) < 2 else 7 * 24 * 60
                until = store.record_block(key, str(error), cooldown)
                notes.append(f'{key}: access refused ({error}). Paused until {until[:16].replace("T", " ")}.')
                log.warning('%s refused access: %s', key, error)
                continue
            except SourceUnavailable as error:
                notes.append(f'{key}: {error}')
                log.warning('%s unavailable: %s', key, error)
                continue
            except Exception as error:  # one broken source must not stop the others
                notes.append(f'{key}: unexpected error: {error}')
                log.exception('%s failed', key)
                continue

            store.clear_block(key)

            scanned += len(found)
            for listing in found:
                identity = (listing.source, listing.source_listing_id)
                if identity in collected:
                    continue
                known_price = store.known_price(listing.source, listing.source_listing_id)
                if known_price is not None and known_price == listing.price:
                    continue
                collected[identity] = listing

        if not collected:
            message = '; '.join(notes) if notes else 'No new or repriced listings.'
            store.finish_scan(scan_id, 'ok', message, scanned, 0)
            return {'ok': True, 'message': message, 'scanned': scanned, 'sent': 0}

        for source_key, group in _group_by_source(collected.values()).items():
            for chunk in _chunks(group, BATCH_SIZE):
                response = api.send_listings(source_key, [listing.payload() for listing in chunk])
                # Remembered only after Base44 accepted them, so a failed batch retries.
                for listing in chunk:
                    store.remember(listing.source, listing.source_listing_id, listing.price)
                sent += len(chunk)
                notes.append(
                    f"{source_key}: {response.get('created', 0)} new, "
                    f"{response.get('updated', 0)} updated, "
                    f"{response.get('price_changes', 0)} repriced"
                )
                # The listings exist now, so their photographs can be attached to them.
                _send_photos(api, store, source_key, chunk, notes)

        message = '; '.join(notes)
        store.finish_scan(scan_id, 'ok', message, scanned, sent)
        return {'ok': True, 'message': message, 'scanned': scanned, 'sent': sent}

    except Exception as error:
        message = str(error)[:500]
        store.finish_scan(scan_id, 'error', message, scanned, sent)
        log.error('Cycle failed: %s', error)
        return {'ok': False, 'message': message, 'scanned': scanned, 'sent': sent}


def _report(api: Any, status: str, message: str, scanned: int, sent: int,
            config: Dict[str, Any]) -> None:
    """Tell the dashboard what happened, including when nothing is being scanned."""
    try:
        api.heartbeat(
            status=status,
            scanned=scanned,
            sent=sent,
            message=message,
            interval_minutes=config['interval_minutes'],
            host=socket.gethostname(),
            version=VERSION,
        )
    except ApiError as error:
        log.error('Heartbeat failed: %s', error)


def main_loop(api: Any, store: Any, env: Any) -> int:
    backoff = 0
    cycle = 0
    last_state = ''

    def note_state(state: str, message: str) -> None:
        """Say it once when the state changes, never once per cycle.

        An idle collector is not a problem to report over and over: it is waiting for
        the dashboard to give it something to scan.
        """
        nonlocal last_state
        if state == last_state:
            return
        last_state = state
        if state == 'idle':
            log.info('Idle: %s.', message)
        else:
            log.info('Collecting again: %s.', message)

    while True:
        cycle += 1
        touch_heartbeat(env.db_path)
        config: Dict[str, Any] = {}
        loaded = False

        try:
            response = api.fetch_config()
            config = normalise_config(response.get('config') or {})
            loaded = True
        except ApiError as error:
            log.error('Could not read configuration: %s', error)
            if not error.retryable:
                return 2
            backoff = min((backoff * 2) or 60, MAX_BACKOFF_SECONDS)

        if loaded and not config['enabled']:
            # Switched off in the dashboard: report that once, then wait quietly. The
            # heartbeat still goes out so the dashboard knows the host is alive.
            note_state('idle', 'collection is switched off in the dashboard')
            _report(api, 'idle', 'Idle: collection is switched off in the dashboard.', 0, 0, config)
            if env.run_once:
                return 0
            time.sleep(env.idle_poll_seconds)
            continue

        if loaded:
            if not config['sources']:
                # Nothing to scan. This is a configuration choice, not a failure.
                note_state('idle', 'no source is enabled in the dashboard')
                result = {'ok': True, 'message': 'Idle: no source is enabled in the dashboard.',
                          'scanned': 0, 'sent': 0}
                _report(api, 'idle', result['message'], 0, 0, config)
            else:
                note_state('running', f"scanning every {config['interval_minutes']} minutes")
                result = run_cycle(api, store, config, cycle)
                log.info('Cycle %s: %s (%s sent)', cycle, result['message'], result['sent'])
                _report(api, 'ok' if result['ok'] else 'error', result['message'],
                        result['scanned'], result['sent'], config)

            backoff = 0 if result['ok'] else min((backoff * 2) or 60, MAX_BACKOFF_SECONDS)

        if env.run_once:
            return 0

        interval_seconds = config['interval_minutes'] * 60 if loaded else 300
        delay = max(interval_seconds, backoff)
        log.info('Next scan in about %s seconds.', int(delay))
        time.sleep(delay + random.uniform(0, 5))