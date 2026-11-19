"""One-shot public-access diagnostic. No login, cookies, retries, or bypasses.

Run on Railway with: python tools/check_marketplace_access.py
Only use for a URL you are authorised to access automatically.
"""
import os
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse

URL = os.environ.get('MARKETPLACE_TEST_URL', '').strip()
if not URL:
    sys.exit('Set MARKETPLACE_TEST_URL to an authorised publicly accessible page.')
parsed = urlparse(URL)
if parsed.scheme != 'https' or parsed.hostname not in {'www.facebook.com', 'facebook.com'}:
    sys.exit('Diagnostic only accepts HTTPS Facebook URLs.')
request = urllib.request.Request(URL, headers={'User-Agent': 'CarHunter-AccessDiagnostic/1.0'})
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        status = response.status
        final_url = response.url
        body = response.read(2_000_000).decode('utf-8', 'replace')
except urllib.error.HTTPError as exc:
    sys.exit(f'HTTP {exc.code}: page not accessible; no retry attempted')
except Exception as exc:
    sys.exit(f'Access failed: {type(exc).__name__}: {exc}')
from hunter.browser.extract import extract_cards
from hunter.browser.profiles import profile_for
records = extract_cards(body, 'https://www.facebook.com', profile_for('facebook_marketplace'))
print(f'HTTP status: {status}')
print(f'Final host: {urlparse(final_url).hostname}')
print(f'HTML characters: {len(body)}')
print(f'Vehicle cards found: {len(records)}')
if not records:
    print('No usable cards. Login wall, blocking, or dynamic rendering may be involved. Do not bypass access controls.')
