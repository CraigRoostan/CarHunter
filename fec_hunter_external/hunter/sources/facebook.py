"""Facebook Marketplace.

This source refuses on purpose, before any browser is opened.

Facebook Marketplace has no public search API. Meta's Content Library API exposes
Marketplace listings only to approved academic and non-profit researchers, and Meta's
Automated Data Collection Terms require express written permission before any automated
collection. Collecting it would mean holding a logged-in session and defeating the login
wall and rate limits, which is access-control circumvention.

The browser engine in `hunter/browser` is deliberately built and tested, but this
profile is marked not permitted, so nothing loads facebook.com. The dashboard reports
the reason on every scan. Manual capture of pages you save yourself is available instead.

See docs/FACEBOOK_MARKETPLACE_ACCESS.md.
"""

from typing import Any, Dict, List

from ..browser.profiles import profile_for
from .base import Listing, Source, SourceUnavailable


class FacebookMarketplaceSource(Source):
    key = 'facebook_marketplace'
    label = 'Facebook Marketplace'
    min_interval_minutes = 5
    available = False

    def collect(self, config: Dict[str, Any], store: Any, cycle: int = 0) -> List[Listing]:
        raise SourceUnavailable(profile_for('facebook_marketplace')['reason'])