"""Manual capture: read pages a person saved while browsing normally.

Nothing here contacts a website. The operator saves a listing or search page from their
own browser into SAVED_PAGES_DIR and this source parses the file. That keeps it inside
what a person is already allowed to look at: no login automation, no scrolling, no
rate-limit dodging. It is a bridge until a licensed source is connected, not a bulk
scraper, and the volume is whatever someone chose to save.
"""

import logging
import os
from typing import Any, Dict, List

from ..browser.extract import extract_cards, extract_detail
from ..browser.profiles import profile_for
from ..errors import SourceUnavailable
from .base import Listing, Source, listing_from_record

log = logging.getLogger('hunter.saved_pages')

# Saved pages keep their original absolute URLs in the markup, so relative hrefs are
# resolved against the site they came from.
BASE_URL = 'https://www.facebook.com'


class SavedPagesSource(Source):
    key = 'saved_pages'
    label = 'Manual capture (saved pages)'
    min_interval_minutes = 1
    available = True

    def _files(self, folder: str) -> List[str]:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return []
        return [os.path.join(folder, name) for name in names if name.lower().endswith(('.html', '.htm'))]

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        folder = (os.environ.get('SAVED_PAGES_DIR') or '').strip()
        if not folder or not os.path.isdir(folder):
            raise SourceUnavailable('SAVED_PAGES_DIR is not set, or is not a folder on this host.')

        paths = self._files(folder)
        if not paths:
            raise SourceUnavailable(f'No saved pages in {folder}. Save a listing or search page there to import it.')

        profile = profile_for('facebook_marketplace')
        listings: List[Listing] = []

        for path in paths:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as handle:
                    html = handle.read()
            except OSError as error:
                log.warning('Could not read %s: %s', path, error)
                continue

            # A saved search page yields many cards; a saved listing page yields one.
            records = extract_cards(html, BASE_URL, profile, config.get('areas'))
            if not records:
                detail = extract_detail(html, BASE_URL, profile)
                records = [detail] if detail else []

            for record in records:
                if not record.get('source_listing_id') or not record.get('price'):
                    continue
                known = store.known_price(self.key, record['source_listing_id'])
                if known is not None and known == record['price']:
                    continue
                try:
                    listings.append(listing_from_record(self.key, record, config.get('areas')))
                except Exception as error:  # one unreadable record must not cost the rest
                    log.warning('Record %s could not be read: %s', record.get('source_listing_id'), error)

        return listings