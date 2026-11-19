import os
import unittest
from hunter.browser.extract import extract_cards
from hunter.browser.profiles import profile_for

class RealPageTest(unittest.TestCase):
    def test_saved_page_links_and_images(self):
        path = os.environ.get('CARHUNTER_REAL_HTML')
        if not path or not os.path.exists(path):
            self.skipTest('Set CARHUNTER_REAL_HTML to supplied page')
        with open(path, encoding='utf-8', errors='replace') as f:
            records = extract_cards(f.read(), 'https://www.facebook.com', profile_for('facebook_marketplace'))
        self.assertEqual(len(records), 24)
        self.assertTrue(all('&amp;' not in r['url'] for r in records))
        self.assertTrue(all(not u.startswith('https://www.facebook.com/(6)') for r in records for u in r['image_urls']))
        self.assertEqual(records[0]['price'], 995)

if __name__ == '__main__':
    unittest.main()
