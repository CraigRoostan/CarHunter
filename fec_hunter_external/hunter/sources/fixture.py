"""Synthetic listings, for proving the whole pipeline without a live source.

Every listing is flagged `is_sample`, so it is badged as a fixture in the dashboard and
can be deleted in one go. This source is off unless it is explicitly enabled.
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from .base import Listing, Source

# title, make, model, year, mileage, price
CATALOGUE = [
    ('2012 Ford Fiesta 1.25 Zetec 5dr', 'Ford', 'Fiesta', 2012, 96000, 1450),
    ('2009 Vauxhall Corsa 1.2i Club', 'Vauxhall', 'Corsa', 2009, 112000, 895),
    ('2011 Volkswagen Golf 1.6 TDI SE', 'Volkswagen', 'Golf', 2011, 128000, 2100),
    ('2008 BMW 320d SE', 'BMW', '320d', 2008, 141000, 1850),
    ('2013 Ford Focus 1.6 Zetec', 'Ford', 'Focus', 2013, 88000, 1900),
    ('2010 Toyota Yaris 1.33 TR', 'Toyota', 'Yaris', 2010, 79000, 1650),
    ('2007 Audi A3 1.9 TDI Sport', 'Audi', 'A3', 2007, 156000, 1250),
    ('2014 Nissan Qashqai 1.5 dCi Visia', 'Nissan', 'Qashqai', 2014, 102000, 3400),
    ('2006 Honda Civic 1.8 i-VTEC SE', 'Honda', 'Civic', 2006, 133000, 850),
    ('2012 Peugeot 208 1.2 VTi Access', 'Peugeot', '208', 2012, 84000, 1550),
]


def _slug(value: str) -> str:
    return ''.join(char if char.isalnum() else '-' for char in value.lower()).strip('-')


class FixtureSource(Source):
    key = 'fixture'
    label = 'Test fixtures (not real listings)'
    min_interval_minutes = 1
    available = True

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        slot = int(time.time() // 300)
        areas = config.get('areas') or []
        listings: List[Listing] = []

        # Two areas only: enough to prove per-area collection and cross-area
        # deduplication without filling the dashboard with test data.
        for area in areas[:2]:
            entry = CATALOGUE[(slot + areas.index(area)) % len(CATALOGUE)]
            title, make, model, year, mileage, price = entry
            listing_id = f'fixture-{_slug(area["name"])}-{slot}'
            if store.is_known(self.key, listing_id):
                continue
            listings.append(Listing(
                source=self.key,
                source_listing_id=listing_id,
                price=price,
                title=title,
                url=f'https://example.com/fixture/{listing_id}',
                make=make,
                model=model,
                year=year,
                mileage=mileage,
                location=f'{area["name"]}, Kent',
                area=area['name'],
                description='Synthetic test listing created by the collector. Not a real vehicle.',
                posted_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                seller_type='private',
                sample=True,
            ))
        return listings