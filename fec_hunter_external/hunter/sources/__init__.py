"""The registry of available sources.

Adding a source is one module plus one line here. Nothing in the scheduler changes.
"""

from typing import Any, Dict, List

from .base import Listing, Source, SourceBlocked, SourceUnavailable
from .ebay import EbaySource
from .facebook import FacebookMarketplaceSource
from .fixture import FixtureSource
from .saved_pages import SavedPagesSource

REGISTRY = {
    source.key: source
    for source in (EbaySource, FacebookMarketplaceSource, FixtureSource, SavedPagesSource)
}


def build_source(key: str, config: Dict[str, Any]) -> Source:
    source_class = REGISTRY.get(key)
    if source_class is None:
        raise SourceUnavailable(f"Unknown source '{key}'. Known sources: {', '.join(sorted(REGISTRY))}.")
    return source_class(config)


def describe_sources() -> List[Dict[str, Any]]:
    return [
        {
            'key': source.key,
            'label': source.label,
            'available': source.available,
            'min_interval_minutes': source.min_interval_minutes,
        }
        for source in REGISTRY.values()
    ]


__all__ = ['Listing', 'Source', 'SourceUnavailable', 'build_source', 'describe_sources']