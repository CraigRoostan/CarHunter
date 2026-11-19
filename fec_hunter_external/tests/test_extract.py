"""Extraction and block detection, against saved pages rather than a live site.

These fixtures are synthetic. They prove the parser reads structured data correctly and
refuses to invent anything; they are not, and must not be reported as, real Facebook
Marketplace records.
"""

import os
import unittest

from hunter.browser.extract import extract_cards, extract_detail, price_from_text
from hunter.browser.session import detect_block

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
AREAS = [
    {'name': 'Maidstone', 'radius_miles': 15},
    {'name': 'Medway', 'radius_miles': 15},
]


def load(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as handle:
        return handle.read()


class DetailExtractionTests(unittest.TestCase):
    def test_reads_a_structured_listing(self):
        record = extract_detail(load('listing_jsonld.html'), 'https://example.com/vehicles/1234567')

        self.assertIsNotNone(record)
        self.assertEqual(record['source_listing_id'], '1234567')
        self.assertEqual(record['price'], 1450)
        self.assertEqual(record['title'], '2012 Ford Fiesta 1.25 Zetec 5dr')
        self.assertEqual(record['make'], 'Ford')
        self.assertEqual(record['model'], 'Fiesta')
        self.assertEqual(record['year'], 2012)
        self.assertEqual(record['mileage'], 96000)
        self.assertIn('Maidstone', record['location'])
        self.assertEqual(len(record['image_urls']), 2)
        self.assertEqual(record['posted_at'][:10], '2026-11-18')

    def test_leaves_missing_fields_empty(self):
        record = extract_detail(load('listing_minimal.html'), 'https://example.com/vehicles/7654321')

        self.assertEqual(record['price'], 2400)
        self.assertEqual(record['make'], 'Vauxhall')
        self.assertEqual(record['model'], 'Corsa')
        self.assertIsNone(record['year'])
        self.assertIsNone(record['mileage'])
        self.assertEqual(record['location'], '')
        self.assertEqual(record['image_urls'], [])

    def test_rejects_a_page_without_a_price(self):
        html = '<html><head><meta property="og:title" content="Ford Focus"></head><body>Call for price</body></html>'
        self.assertIsNone(extract_detail(html, 'https://example.com/vehicles/9999999'))


class CardExtractionTests(unittest.TestCase):
    def test_reads_cards_and_skips_the_unpriced(self):
        cards = extract_cards(load('results_page.html'), 'https://www.facebook.com', None, AREAS)

        self.assertEqual([card['source_listing_id'] for card in cards], ['111111111', '222222222'])

        first = cards[0]
        self.assertEqual(first['price'], 1450)
        self.assertEqual(first['area'], 'Maidstone')
        self.assertEqual(first['url'], 'https://www.facebook.com/marketplace/item/111111111/')
        self.assertEqual(first['image_urls'], ['https://www.facebook.com/img/fiesta.jpg'])
        self.assertNotIn('£', first['title'])

        # Gillingham belongs to the Medway area through the alias map.
        self.assertEqual(cards[1]['area'], 'Medway')


class PriceParsingTests(unittest.TestCase):
    def test_reads_a_currency_amount(self):
        self.assertEqual(price_from_text('£1,450'), 1450)
        self.assertEqual(price_from_text('asking £895 ono'), 895)

    def test_never_reads_a_year_as_a_price(self):
        self.assertIsNone(price_from_text('2012 Ford Fiesta 1.25 Zetec'))


class BlockDetectionTests(unittest.TestCase):
    def test_detects_a_login_wall(self):
        self.assertEqual(detect_block(load('login_wall.html')), 'log in to continue')

    def test_a_normal_page_is_not_blocked(self):
        self.assertIsNone(detect_block(load('results_page.html')))


if __name__ == '__main__':
    unittest.main()