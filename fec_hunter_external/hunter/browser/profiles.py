"""Site profiles: where to look and how to read a page.

A profile is data, not logic, so adding a site or repairing a site's markup never
touches the scheduler, the ingest client or the store.

`permitted` is the gate. A profile only runs when someone has confirmed that automated
access is allowed. Facebook Marketplace is present so the blocker is explicit and
reported, and it stays switched off.
"""

from typing import Any, Dict

FACEBOOK_REASON = (
    'Facebook Marketplace has no public search API, and Meta permits automated collection '
    'only with its express written permission, which we do not have. Automated access would '
    'mean holding a logged-in session and defeating the login wall and rate limits, which is '
    'access-control circumvention. Collection stays disabled. Manual capture of pages you '
    'save yourself is available instead.'
)

PROFILES: Dict[str, Dict[str, Any]] = {
    'facebook_marketplace': {
        'key': 'facebook_marketplace',
        'label': 'Facebook Marketplace',
        'permitted': False,
        'reason': FACEBOOK_REASON,
        # Kept for reference only: nothing in the collector will load it.
        'search_url': (
            'https://www.facebook.com/marketplace/{area}/search'
            '?query=car&minPrice={price_min}&maxPrice={price_max}&sortBy=creation_time_descend'
        ),
        'id_regex': r'/marketplace/item/(\d+)',
        'title_pattern': None,
        'price_pattern': None,
    },
}


def profile_for(key: str) -> Dict[str, Any]:
    profile = PROFILES.get(key)
    if not profile:
        raise KeyError(f"No browser profile named '{key}'")
    return profile


def permitted_profiles() -> Dict[str, Dict[str, Any]]:
    return {key: profile for key, profile in PROFILES.items() if profile.get('permitted')}