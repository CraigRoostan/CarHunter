"""Photographs for a listing: download, validate, re-encode, and prepare for upload.

Only permitted sources reach here, and only the addresses that source published. Every
image is decoded before it is sent, so an error page or a challenge page can never be
stored as a vehicle photograph. Nothing is invented: a listing with no usable photograph
simply arrives without one.
"""

import base64
import hashlib
import io
import logging
from typing import Any, Dict, List

log = logging.getLogger('hunter.photos')

MAX_IMAGES = 8
MAX_DOWNLOAD_BYTES = 6 * 1024 * 1024
MAX_EDGE = 1600
MIN_EDGE = 180
JPEG_QUALITY = 82
TIMEOUT_SECONDS = 25

# A transparent identity rather than a browser's: the collector says who it is.
USER_AGENT = 'FastEasyCarHunter/1.1 (+https://fasteasycar.co.uk)'


def signature(urls: List[str]) -> str:
    """A short signature of the photographs a listing offers, so unchanged ones are skipped."""
    joined = '|'.join(url for url in urls if isinstance(url, str))
    return hashlib.sha1(joined.encode('utf-8')).hexdigest()[:16]


def _prepare(image_bytes: bytes):
    """Decode, bound and re-encode one picture. Returns None when it is not usable."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is in requirements.txt
        log.error('Pillow is not installed, so photographs cannot be processed.')
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            probe.verify()

        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert('RGB')
            width, height = image.size
            if min(width, height) < MIN_EDGE:
                return None

            scale = min(1.0, MAX_EDGE / max(width, height))
            if scale < 1.0:
                image = image.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))),
                    Image.LANCZOS,
                )

            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)
            return buffer.getvalue()
    except Exception as error:
        log.debug('Image could not be prepared: %s', error)
        return None


def collect(listing: Any) -> List[Dict[str, str]]:
    """Download and prepare this listing's photographs, main image first."""
    # Imported here so the package loads without the HTTP client installed.
    import requests

    urls = [url for url in (listing.image_urls or []) if isinstance(url, str) and url.startswith('http')]
    if not urls:
        return []

    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})

    images: List[Dict[str, str]] = []
    seen = set()

    for url in urls[:MAX_IMAGES]:
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS, stream=True)
            if response.status_code != 200:
                continue

            content_type = (response.headers.get('content-type') or '').lower()
            if content_type and not content_type.startswith('image/'):
                continue

            chunks = []
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    chunks = []
                    break
                chunks.append(chunk)
            if not chunks:
                continue

            prepared = _prepare(b''.join(chunks))
            if not prepared:
                continue

            digest = hashlib.sha1(prepared).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)

            images.append({
                'content_base64': base64.b64encode(prepared).decode('ascii'),
                'content_type': 'image/jpeg',
            })
        except requests.RequestException as error:
            log.warning('Photograph could not be downloaded (%s): %s', listing.source_listing_id, error)
        except Exception as error:  # one bad picture must not cost the listing
            log.warning('Photograph could not be prepared (%s): %s', listing.source_listing_id, error)

    return images