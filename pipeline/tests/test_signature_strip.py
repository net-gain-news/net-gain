import base64
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

import signature_strip as ss


class Labels(unittest.TestCase):
    def test_date_label_has_the_year_and_no_leading_zero(self):
        self.assertEqual(ss.date_label("2026-10-06"), "OCT 6, 2026")
        self.assertEqual(ss.date_label("2026-10-16T14:16:10"), "OCT 16, 2026")

    def test_length_label(self):
        self.assertEqual(ss.length_label(306), "5:06")
        self.assertEqual(ss.length_label(3725), "1:02:05")
        self.assertEqual(ss.length_label(0), "")
        self.assertEqual(ss.length_label(None), "")

    def test_caption_names_the_newscast_date_and_length(self):
        self.assertEqual(ss.caption("2026-10-16", 306), "NEWSCAST · OCT 16, 2026 · 5:06")
        self.assertEqual(ss.caption("2026-10-16", 0), "NEWSCAST · OCT 16, 2026")


class Rendering(unittest.TestCase):
    TITLE = "Arbor School Breach in UK as Frontline Data Leak Hits Methuen"

    def _img(self, theme, title=None, seconds=306):
        return Image.open(io.BytesIO(ss.render_strip(title or self.TITLE, "2026-10-16", seconds, theme)))

    def test_size_is_three_times_the_display_size_with_transparency(self):
        im = self._img("light")
        self.assertEqual(im.size, (ss.WIDTH * 3, ss.HEIGHT * 3))
        self.assertEqual(im.mode, "RGBA")
        self.assertEqual(im.getpixel((ss.WIDTH * 3 - 2, ss.HEIGHT * 3 - 2))[3], 0)   # empty corner is transparent

    def test_the_red_flash_is_drawn_in_both_colourways(self):
        for theme in ("light", "dark"):
            im = self._img(theme)
            self.assertEqual(im.getpixel((4, 4)), ss.RED + (255,), theme)

    def test_text_colour_follows_the_theme(self):
        def ink_pixels(theme):
            im = self._img(theme)
            region = im.crop((0, 70, 600, 110))                      # the headline row
            return [p for p in region.getdata() if p[3] == 255]
        light, dark = ink_pixels("light"), ink_pixels("dark")
        self.assertTrue(light and dark)
        self.assertEqual(light[0][:3], ss.THEMES["light"]["ink"])
        self.assertEqual(dark[0][:3], ss.THEMES["dark"]["ink"])

    def test_a_very_long_headline_is_shrunk_then_ellipsised_to_stay_inside_the_image(self):
        long_title = "Districts Urged to Disable YouTube and Gemini AI as Vermont District Refuses Ransom Demand After Cyberattack"
        im = self._img("light", long_title)
        box = im.getchannel("A").crop((0, 70, im.width, im.height)).getbbox()
        self.assertIsNotNone(box)
        self.assertLessEqual(box[2], im.width)

    def test_non_breaking_hyphen_is_drawn_as_an_ordinary_hyphen(self):
        a = ss.render_strip("K‑12 breach", "2026-10-16", 306, "light")
        b = ss.render_strip("K-12 breach", "2026-10-16", 306, "light")
        self.assertEqual(a, b)

    def test_both_colourways_are_returned_and_differ(self):
        both = ss.render_both(self.TITLE, "2026-10-16", 306)
        self.assertEqual(set(both), {"light", "dark"})
        self.assertNotEqual(both["light"], both["dark"])


class FakeWP:
    def __init__(self, episode, fail=False):
        self.episode, self.fail, self.stored = episode, fail, None

    def get_episode(self, episode_id):
        return self.episode

    def store_signature_strip(self, show_id, payload):
        if self.fail:
            raise RuntimeError("boom")
        self.stored = (show_id, payload)
        return {"status": "stored"}


class Refresh(unittest.TestCase):
    EP = {"title": {"rendered": "T"}, "meta": {"ng_meta_aioseo_title": "Arbor School Breach in UK", "ng_episode_date": "2026-10-16", "ng_audio_seconds": 306}}

    def test_stores_both_images_for_the_show(self):
        wp = FakeWP(self.EP)
        self.assertTrue(ss.refresh_signature_strip(wp, {"id": 16}, 590))
        show_id, payload = wp.stored
        self.assertEqual(show_id, 16)
        self.assertEqual(payload["episode_date"], "2026-10-16")
        for key in ("light_png", "dark_png"):
            self.assertTrue(base64.b64decode(payload[key]).startswith(b"\x89PNG"))

    def test_a_failure_is_swallowed_and_reported_as_false(self):
        self.assertFalse(ss.refresh_signature_strip(FakeWP(self.EP, fail=True), {"id": 16}, 590))

    def test_missing_title_or_date_is_skipped(self):
        self.assertFalse(ss.refresh_signature_strip(FakeWP({"meta": {}}), {"id": 16}, 590))


if __name__ == "__main__":
    unittest.main()
