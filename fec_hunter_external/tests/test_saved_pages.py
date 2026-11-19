"""The manual capture path end to end: saved files in, Listing records out.

Proves the parts that matter for a first live test: cards are read from a saved search
page, a saved listing page is read as one record, an access wall is ignored rather than
parsed, and nothing is treated as seen until Base44 has accepted it.
"""

import os
import shutil
import tempfile
import unittest

from hunter.sources.saved_pages import SavedPagesSource
from hunter.store import Store

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
CONFIG = {
    'areas': [{'name': 'Maidstone', 'radius_miles': 15}, {'name': 'Medway', 'radius_miles': 15}],
    'price_min': 500,
    'price_max': 5000,
}


class SavedPagesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        for name in ('results_page.html', 'listing_jsonld.html', 'login_wall.html'):
            shutil.copy(os.path.join(FIXTURES, name), self.folder)

        self.store = Store(os.path.join(self.folder, 'hunter.sqlite3'))
        self.previous = os.environ.get('SAVED_PAGES_DIR')
        os.environ['SAVED_PAGES_DIR'] = self.folder
        self.source = SavedPagesSource(CONFIG)

    def tearDown(self):
        if self.previous is None:
            os.environ.pop('SAVED_PAGES_DIR', None)
        else:
            os.environ['SAVED_PAGES_DIR'] = self.previous
        self.store.close()

    def test_reads_both_page_types_and_ignores_the_wall(self):
        listings = self.source.collect(CONFIG, self.store)
        ids = sorted(listing.source_listing_id for listing in listings)

        self.assertEqual(ids, ['111111111', '1234567', '222222222'])
        self.assertTrue(all(listing.price > 0 for listing in listings))
        self.assertTrue(all(listing.source == 'saved_pages' for listing in listings))
        # These are real listings read from saved pages, not synthetic fixtures.
        self.assertFalse(any(listing.sample for listing in listings))

        by_id = {listing.source_listing_id: listing for listing in listings}
        self.assertEqual(by_id['111111111'].area, 'Maidstone')
        self.assertEqual(by_id['222222222'].area, 'Medway')
        self.assertEqual(by_id['1234567'].make, 'Ford')
        self.assertEqual(by_id['1234567'].mileage, 96000)

    def test_nothing_is_remembered_until_it_is_sent(self):
        listings = self.source.collect(CONFIG, self.store)

        # The scan itself records nothing: a failed send must be retried next cycle.
        self.assertIsNone(self.store.known_price('saved_pages', '111111111'))

        for listing in listings:
            self.store.remember(listing.source, listing.source_listing_id, listing.price)

        self.assertEqual(self.source.collect(CONFIG, self.store), [])


if __name__ == '__main__':
    unittest.main()