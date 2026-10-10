import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_publisher_logo as logos

DARK_BG, DARK_FG = (19, 17, 13), (237, 234, 228)


class PublisherLogoTests(unittest.TestCase):
    def test_wide_logo_fits_googles_60_by_600_limit(self):
        for theme in logos.THEMES:
            img = logos.wide_logo(theme)
            self.assertEqual(img.height, 60)
            self.assertLessEqual(img.width, 600)
            self.assertGreater(img.width, 200)

    def test_square_and_mark_logos_are_square_and_at_least_512(self):
        for make in (logos.square_logo, logos.mark_logo):
            img = make("dark")
            self.assertEqual(img.width, img.height)
            self.assertGreaterEqual(img.width, 512)

    def test_dark_logos_use_the_official_colours_and_nothing_else_as_background(self):
        for make in (logos.wide_logo, logos.square_logo, logos.mark_logo):
            img = make("dark")
            self.assertEqual(img.getpixel((1, 1)), DARK_BG)
            self.assertIn(DARK_FG, img.getdata())                 # solid foreground is reached

    def test_light_logos_are_the_same_artwork_with_the_colours_flipped(self):
        dark, light = logos.wide_logo("dark"), logos.wide_logo("light")
        self.assertEqual(dark.size, light.size)
        self.assertEqual(light.getpixel((1, 1)), (255, 255, 255))
        # the ink coverage is identical: each pixel's share of foreground matches between the two (to rounding)
        worst = 0.0
        for d, l in zip(dark.getdata(), light.getdata()):
            dark_cov = (d[0] - logos.DARK["bg"][0]) / (logos.DARK["fg"][0] - logos.DARK["bg"][0])
            light_cov = (logos.LIGHT["bg"][0] - l[0]) / (logos.LIGHT["bg"][0] - logos.LIGHT["fg"][0])
            worst = max(worst, abs(dark_cov - light_cov))
        self.assertLess(worst, 0.03)

    def test_horizontal_lockup_is_built_from_the_official_artwork_pieces(self):
        mark, net_gain, news, cap, above = logos.stacked_parts()
        self.assertGreater(net_gain.width, news.width)             # "Net Gain" is the longer line
        self.assertGreater(mark.width, 0)
        lockup, lockup_cap, _ = logos.horizontal_lockup()
        self.assertEqual(lockup_cap, cap)
        self.assertGreater(lockup.width, mark.width + net_gain.width + news.width)    # plus the gaps

    def test_official_source_files_are_in_the_repo(self):
        for name in ("net_gain_news_logo_stacked.png", "net_gain_news_mark.png"):
            self.assertTrue(os.path.exists(os.path.join(logos.BRAND, name)), name)
        self.assertEqual(Image.open(os.path.join(logos.BRAND, "net_gain_news_logo_stacked.png")).size, (2000, 2000))


if __name__ == "__main__":
    unittest.main()
