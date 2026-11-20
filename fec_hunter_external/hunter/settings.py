"""Configuration: environment for the host, dashboard settings for each scan.

The dashboard is the source of truth for the interval, search areas, price band and
which sources are enabled, so the operator can change them without touching the host.
Everything here is defensive: a malformed value falls back to a safe default rather
than stopping the collector.
"""

import os
from typing import Any, Dict, List

# The areas the business asked to monitor. Used until the dashboard has its own list.
DEFAULT_AREAS = [
    {'name': 'Maidstone', 'radius_miles': 15},
    {'name': 'Dartford', 'radius_miles': 15},
    {'name': 'Orpington', 'radius_miles': 15},
    {'name': 'Sevenoaks', 'radius_miles': 15},
    {'name': 'Ashford', 'radius_miles': 15},
    {'name': 'Canterbury', 'radius_miles': 15},
    {'name': 'Tunbridge Wells', 'radius_miles': 15},
    {'name': 'Bromley', 'radius_miles': 15},
    {'name': 'Medway', 'radius_miles': 15},
    {'name': 'Gravesend', 'radius_miles': 15},
]

ALLOWED_INTERVALS = (1, 5, 10, 15, 30, 60)

# A source cannot be polled faster than this. eBay's Browse API quota is generous at
# five minutes but not at one, so the interval is raised to the source's floor.
SOURCE_MIN_INTERVALS = {'ebay': 5, 'fixture': 1, 'facebook_marketplace': 5, 'saved_pages': 1}


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def normalise_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Turn whatever the dashboard returned into a config the scan can trust."""
    data = raw if isinstance(raw, dict) else {}

    sources = [item for item in (data.get('sources') or []) if isinstance(item, str) and item]

    interval = _int(data.get('interval_minutes'), 5)
    if interval not in ALLOWED_INTERVALS:
        interval = min(ALLOWED_INTERVALS, key=lambda value: abs(value - interval))
    for source in sources:
        minimum = SOURCE_MIN_INTERVALS.get(source)
        if minimum and interval < minimum:
            interval = minimum

    areas: List[Dict[str, Any]] = []
    for area in data.get('areas') or []:
        if isinstance(area, dict) and str(area.get('name') or '').strip():
            areas.append({
                'name': str(area['name']).strip()[:60],
                'radius_miles': max(1, _int(area.get('radius_miles'), 15)),
            })
    if not areas:
        areas = [dict(area) for area in DEFAULT_AREAS]

    price_min = max(0, _int(data.get('price_min'), 500))
    price_max = max(price_min + 1, _int(data.get('price_max'), 5000))

    return {
        'enabled': data.get('enabled') is True,
        'interval_minutes': interval,
        'areas': areas,
        'price_min': price_min,
        'price_max': price_max,
        'seller_type': 'any' if data.get('seller_type') == 'any' else 'private',
        'sources': sources,
        'max_pages': max(1, min(10, _int(data.get('max_pages'), 3))),
        'full_sweep_every': max(1, _int(data.get('full_sweep_every'), 12)),
        'require_area': data.get('require_area') is not False,
    }


class Env:
    """Values that belong to the host, read once at startup."""

    def __init__(self) -> None:
        self.base44_url = (os.environ.get('BASE44_URL') or 'https://fasteasycar.base44.app').rstrip('/')
        self.ingest_key = (os.environ.get('INGEST_KEY') or '').strip()
        self.db_path = os.environ.get('HUNTER_DB') or os.environ.get('DB_PATH') or os.path.join('data', 'hunter.sqlite3')
        self.log_level = (os.environ.get('LOG_LEVEL') or 'INFO').upper()
        self.run_once = (os.environ.get('RUN_ONCE') or '').lower() in ('1', 'true', 'yes')
        # How often an idle collector re-reads the dashboard while it has nothing to scan.
        # Waiting quietly is the point: an idle collector must not fill the logs.
        self.idle_poll_seconds = max(15, _int(os.environ.get('IDLE_POLL_SECONDS'), 60))

    def validate(self) -> List[str]:
        problems: List[str] = []
        if not self.ingest_key:
            problems.append('INGEST_KEY is empty. Generate a key on Marketplace Opportunities -> Collector.')
        return problems