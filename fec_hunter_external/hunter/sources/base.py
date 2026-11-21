"""Marketplace source contracts and normalised listing records.

A source turns a marketplace's listings into Listing objects. Everything else, the
scheduling, deduplication, retries and ingest, is shared and source-agnostic.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import SourceBlocked, SourceUnavailable  # re-exported: sources import both from here
from ..normalise import match_area


@dataclass
class Listing:
    source: str
    source_listing_id: str
    price: int
    title: str = ''
    url: str = ''
    make: str = ''
    model: str = ''
    derivative: str = ''
    year: Optional[int] = None
    mileage: Optional[int] = None
    location: str = ''
    area: str = ''
    description: str = ''
    image_urls: List[str] = field(default_factory=list)
    posted_at: str = ''
    seller_type: str = 'unknown'
    seller_phone: str = ''
    sample: bool = False

    def payload(self) -> Dict[str, Any]:
        """The ingestion API's shape. Empty values are omitted, never faked."""
        data = {
            'source_listing_id': self.source_listing_id,
            'price': self.price,
            'title': self.title,
            'url': self.url,
            'make': self.make,
            'model': self.model,
            'derivative': self.derivative,
            'year': self.year,
            'mileage': self.mileage,
            'location': self.location,
            'area': self.area,
            'description': self.description,
            'image_urls': self.image_urls[:12],
            'posted_at': self.posted_at,
            'seller_type': self.seller_type,
            'seller_phone': self.seller_phone,
            'is_sample': self.sample,
        }
        return {key: value for key, value in data.items() if value not in (None, '', [])}


class Source:
    key = ''
    label = ''
    min_interval_minutes = 5
    available = True

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        raise NotImplementedError


def listing_from_record(source_key: str, record: Dict[str, Any],
                        areas: Optional[List[Dict[str, Any]]] = None,
                        sample: bool = False) -> Listing:
    """Build a Listing from an extracted record, filling only what was actually found."""
    location = str(record.get('location') or '')
    area = str(record.get('area') or '') or (match_area(location or str(record.get('title') or ''), areas or []) or '')
    return Listing(
        source=source_key,
        source_listing_id=str(record['source_listing_id']),
        price=int(record['price']),
        title=str(record.get('title') or '')[:300],
        url=str(record.get('url') or ''),
        make=str(record.get('make') or ''),
        model=str(record.get('model') or ''),
        derivative=str(record.get('derivative') or ''),
        year=record.get('year'),
        mileage=record.get('mileage'),
        location=location[:200],
        area=area[:120],
        description=str(record.get('description') or '')[:4000],
        image_urls=[url for url in (record.get('image_urls') or []) if isinstance(url, str)][:12],
        posted_at=str(record.get('posted_at') or ''),
        seller_type=str(record.get('seller_type') or 'unknown'),
        seller_phone=str(record.get('seller_phone') or ''),
        sample=sample,
    )
