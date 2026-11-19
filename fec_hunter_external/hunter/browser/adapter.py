"""The browser engine: a permitted site, a profile, and Chromium.

Kept apart from the scheduler and the ingest client so a site's markup can be repaired
in `extract.py` and `profiles.py` alone. The engine refuses any profile that is not
marked permitted, before it ever opens a browser.
"""

import logging
import os
import time
from typing import Any, Dict, List

from ..errors import SourceBlocked, SourceUnavailable
from ..sources.base import Listing, Source, listing_from_record
from .extract import extract_cards, extract_detail
from .profiles import profile_for
from .session import BrowserSession

log = logging.getLogger('hunter.browser')


class BrowserSource(Source):
    """Collects from one site through a profile.

    Not registered as a source on its own: it becomes live the moment a permitted
    profile exists for a site whose terms allow automated access.
    """

    key = 'browser'
    label = 'Browser collector'
    min_interval_minutes = 5
    available = True

    def __init__(self, config: Dict[str, Any], profile_key: str, source_key: str = '') -> None:
        super().__init__(config)
        self.profile = profile_for(profile_key)
        self.key = source_key or profile_key

    def _search_urls(self, profile: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
        template = profile.get('search_url')
        if not template:
            return []
        urls = []
        for area in config.get('areas') or []:
            urls.append(template.format(
                area=str(area.get('name') or '').replace(' ', '-').lower(),
                price_min=config['price_min'],
                price_max=config['price_max'],
            ))
        return urls

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        profile = self.profile
        if not profile.get('permitted'):
            raise SourceUnavailable(profile.get('reason') or 'This site does not permit automated collection.')

        urls = self._search_urls(profile, config)
        if not urls:
            raise SourceUnavailable('No search areas are configured.')

        page_delay = float(os.environ.get('PAGE_DELAY_SECONDS') or 2.5)
        headless = (os.environ.get('BROWSER_HEADLESS') or 'true').lower() not in ('0', 'false', 'no')
        found: List[Listing] = []

        with BrowserSession(headless=headless) as session:
            for url in urls:
                html = session.fetch(url)
                cards = extract_cards(html, url, profile, config.get('areas'))

                for card in cards[:int(config.get('max_per_area') or 20)]:
                    known = store.known_price(self.key, card['source_listing_id'])
                    if known is not None and known == card['price']:
                        continue

                    record = card
                    try:
                        detail = extract_detail(session.fetch(card['url']), card['url'], profile)
                    except SourceBlocked:
                        raise  # a wall on a detail page stops the whole source
                    except Exception as error:  # one bad page must not lose the batch
                        log.warning('Detail page failed for %s: %s', card['url'], error)
                        detail = None

                    if detail:
                        record = {**card, **{key: value for key, value in detail.items() if value not in ('', None, [])}}

                    try:
                        found.append(listing_from_record(self.key, record, config.get('areas')))
                    except Exception as error:  # one unreadable listing must not cost the batch
                        log.warning('Listing %s could not be read: %s', card.get('source_listing_id'), error)

                    time.sleep(page_delay)

        return found