import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_publisher_logo as logos


class PublisherLogoTests(unittest.TestCase):
    def test_wide_logo_fits_googles_60_by_600_limit(self):
        for palette in logos.PALETTES:
            img = logos.wide_logo(palette)
            self.assertEqual(img.height, 60)
            self.assertLessEqual(img.width, 600)
            self.assertGreater(img.width, 60)

    def test_square_logo_is_square_and_at_least_512(self):
        img = logos.square_logo("denim")
        self.assertEqual(img.width, img.height)
        self.assertGreaterEqual(img.width, 512)

    def test_logos_are_opaque_on_the_dark_footer_colour(self):
        img = logos.wide_logo("denim")
        self.assertEqual(img.mode, "RGB")
        self.assertEqual(img.getpixel((1, 1)), logos.PALETTES["denim"]["bar"])


if __name__ == "__main__":
    unittest.main()
