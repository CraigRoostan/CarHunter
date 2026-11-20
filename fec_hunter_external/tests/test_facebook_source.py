import unittest
from hunter.sources.facebook import parse_card, parse_detail


class FacebookParserTests(unittest.TestCase):
    def test_card(self):
        result = parse_card('Just listed\n£1,350\n2016 Mazda 6\nHarlow, Essex', '/marketplace/item/1841543900613481/?tracking=abc', 'https://example.com/a.jpg')
        self.assertEqual(result['source_listing_id'], '1841543900613481')
        self.assertEqual(result['price'], 1350)
        self.assertEqual(result['year'], 2016)
        self.assertEqual(result['location'], 'Harlow, Essex')
        self.assertEqual(result['url'], 'https://www.facebook.com/marketplace/item/1841543900613481/')

    def test_km_conversion(self):
        detail = parse_detail('Driven 122,000 km\nFull Service History')
        self.assertEqual(detail['mileage'], 75807)
        self.assertIn('Full Service History', detail['description'])

    def test_no_fake_mileage(self):
        self.assertNotIn('mileage', parse_detail('Good condition'))


if __name__ == '__main__':
    unittest.main()
