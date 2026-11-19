"""Deduplication, price history and block cooldowns, against a temporary database."""

import os
import tempfile
import unittest

from hunter.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = Store(os.path.join(self.folder, 'hunter.sqlite3'))

    def tearDown(self):
        self.store.close()

    def test_a_listing_is_only_new_once(self):
        self.assertIsNone(self.store.known_price('saved_pages', '111111111'))

        self.store.remember('saved_pages', '111111111', 1450)
        self.assertEqual(self.store.known_price('saved_pages', '111111111'), 1450)
        self.assertEqual(self.store.counts()['seen'], 1)

    def test_a_price_change_is_visible(self):
        self.store.remember('saved_pages', '222222222', 895)
        self.store.remember('saved_pages', '222222222', 795)

        self.assertEqual(self.store.known_price('saved_pages', '222222222'), 795)
        self.assertEqual(self.store.counts()['seen'], 1)

    def test_a_block_is_remembered_then_cleared(self):
        self.assertIsNone(self.store.blocked_reason('facebook_marketplace'))

        self.store.record_block('facebook_marketplace', 'access wall', 360)
        self.assertIsNotNone(self.store.blocked_reason('facebook_marketplace'))
        self.assertEqual(self.store.block_hits('facebook_marketplace'), 1)

        self.store.record_block('facebook_marketplace', 'access wall', 360)
        self.assertEqual(self.store.block_hits('facebook_marketplace'), 2)

        self.store.clear_block('facebook_marketplace')
        self.assertIsNone(self.store.blocked_reason('facebook_marketplace'))
        self.assertEqual(self.store.block_hits('facebook_marketplace'), 0)


if __name__ == '__main__':
    unittest.main()