"""HTTP client for the two Base44 endpoints the collector uses.

Both calls carry the ingest key in `x-ingest-key`. Retries are deliberate: transient
failures back off, but a rejected key stops immediately because retrying cannot fix it.
"""

import random
import time
from typing import Any, Dict, List

import requests

CONFIG_PATH = '/functions/marketplaceCollectorConfig'
INGEST_PATH = '/functions/marketplaceIngest'
PHOTO_PATH = '/functions/marketplacePhotoIngest'

# Photographs are base64 in the body, so they need longer than a JSON listing batch.
PHOTO_TIMEOUT_SECONDS = 120


class ApiError(Exception):
    """A Base44 call failed. `retryable` tells the loop whether to back off."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class Base44Client:
    def __init__(self, base_url: str, ingest_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip('/')
        self.ingest_key = ingest_key
        self.timeout = timeout
        self.session = requests.Session()

    @staticmethod
    def _delay(attempt: int) -> float:
        return min(2 ** (attempt + 1), 30) + random.uniform(0, 1)

    def _post(self, path: str, payload: Dict[str, Any], retries: int = 3,
              timeout: int = 0) -> Dict[str, Any]:
        url = f'{self.base_url}{path}'
        headers = {'x-ingest-key': self.ingest_key, 'content-type': 'application/json'}

        for attempt in range(retries + 1):
            try:
                response = self.session.post(
                    url, json=payload, headers=headers, timeout=timeout or self.timeout,
                )
            except requests.RequestException as error:
                if attempt >= retries:
                    raise ApiError(f'Network error calling Base44: {error}') from error
                time.sleep(self._delay(attempt))
                continue

            if response.status_code in (401, 403):
                raise ApiError(
                    'Base44 rejected the ingest key. Generate a new key on the dashboard and update INGEST_KEY.',
                    retryable=False,
                )

            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= retries:
                    raise ApiError(f'Base44 returned {response.status_code}')
                time.sleep(self._delay(attempt))
                continue

            try:
                data = response.json()
            except ValueError:
                data = {}

            if response.status_code >= 400:
                raise ApiError(
                    str(data.get('error') or f'Base44 returned {response.status_code}'),
                    retryable=False,
                )
            return data if isinstance(data, dict) else {}

        raise ApiError('Base44 call failed')

    def fetch_config(self) -> Dict[str, Any]:
        return self._post(CONFIG_PATH, {'action': 'config'})

    def heartbeat(self, **payload: Any) -> Dict[str, Any]:
        return self._post(CONFIG_PATH, dict(payload, action='heartbeat'))

    def send_listings(self, source: str, listings: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._post(INGEST_PATH, {'source': source, 'listings': listings})

    def send_photos(self, source: str, photos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Store photographs permanently. Sent after the listings themselves exist."""
        return self._post(
            PHOTO_PATH,
            {'source': source, 'photos': photos},
            retries=2,
            timeout=PHOTO_TIMEOUT_SECONDS,
        )