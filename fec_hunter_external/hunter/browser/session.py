"""Playwright lifecycle and block detection, in one place.

Chromium is launched once per scan and reused, because starting it is the slow part.
There are no stealth patches, no fingerprint spoofing and no proxy rotation: if a site
refuses automated access, that is a signal to stop, not to disguise the request.
"""

import logging
from typing import Optional

from ..errors import SourceBlocked

log = logging.getLogger('hunter.browser')

# Phrases that mean "you are not welcome here without a human". Deliberately blunt:
# a false positive costs one skipped scan, a false negative means retrying against a wall.
BLOCK_MARKERS = (
    'log in to continue',
    'you must log in',
    'enter your password',
    'captcha',
    'are you a robot',
    'verify you are human',
    'security check',
    'unusual traffic',
    'access denied',
    'temporarily blocked',
    'you have been blocked',
)


def detect_block(html: str) -> Optional[str]:
    """The marker that shows the page is an access wall, or None."""
    lowered = (html or '').lower()
    for marker in BLOCK_MARKERS:
        if marker in lowered:
            return marker
    return None


class BrowserSession:
    """A short-lived Chromium session.

    `fetch` returns the rendered HTML of one page, or raises `SourceBlocked` when the
    site refuses access. Playwright is imported on entry, so the rest of the collector
    runs on a host where the browser is not installed.
    """

    def __init__(self, headless: bool = True, timeout_ms: int = 30000, settle_ms: int = 1200) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> 'BrowserSession':
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:  # pragma: no cover - host configuration
            raise RuntimeError(
                'Playwright is not installed. Run: pip install -r requirements.txt && playwright install chromium'
            ) from error

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(locale='en-GB')
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:  # a failed close must not mask the real error
                log.debug('Ignoring error while closing the browser', exc_info=True)
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                log.debug('Ignoring error while stopping Playwright', exc_info=True)

    def fetch(self, url: str) -> str:
        if not self._page:
            raise RuntimeError('BrowserSession used outside a with block')

        response = self._page.goto(url, wait_until='domcontentloaded')
        status = response.status if response else 0

        if status in (401, 403, 429):
            raise SourceBlocked(f'{url} returned HTTP {status}')

        self._page.wait_for_timeout(self.settle_ms)
        html = self._page.content()

        marker = detect_block(html)
        if marker:
            raise SourceBlocked(f'{url} is showing an access wall ("{marker}")')

        return html