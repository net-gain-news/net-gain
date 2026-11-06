import base64
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

import signature_strip as ss


class Labels(unittest.TestCase):
    def test_short_date_has_no_year_and_no_leading_zero(self):
        self.assertEqual(ss.short_date("2026-11-05"), "NOV 5")
        self.assertEqual(ss.short_date("2026-10-16T14:16:10"), "OCT 16")

    def test_the_label_names_the_show_and_the_date(self):
        wide = 296 * ss.SCALE
        self.assertEqual(ss.fit_label("Net Gain Edtech", "2026-11-05", wide), "LATEST FROM NET GAIN EDTECH · NOV 5")
        self.assertEqual(ss.fit_label("Net Gain Cleantech", "2026-11-05", wide), "LATEST FROM NET GAIN CLEANTECH · NOV 5")

    def test_a_label_that_is_too_wide_drops_the_date_first_and_then_shortens_the_show_name(self):
        narrow = 250 * ss.SCALE
        self.assertEqual(ss.fit_label("Net Gain Real Estate", "2026-11-05", 290 * ss.SCALE), "LATEST FROM NET GAIN REAL ESTATE · NOV 5")
        self.assertEqual(ss.fit_label("Net Gain Real Estate Development", "2026-11-05", 290 * ss.SCALE), "LATEST FROM NET GAIN REAL ESTATE DEVELOPMENT")
        shortest = ss.fit_label("Net Gain " + "Extraordinarily Long Vertical Name " * 3, "2026-11-05", narrow)
        self.assertTrue(shortest.startswith("LATEST FROM NET GAIN EXTRA"))
        self.assertTrue(shortest.endswith("…"))
        self.assertLessEqual(ss._tracked_width(ss.label_font(), shortest, ss.label_track()), narrow)

    def test_a_non_breaking_hyphen_in_a_show_name_is_drawn_as_a_hyphen(self):
        self.assertEqual(ss.fit_label("K\u201112 News", "2026-11-05", 296 * ss.SCALE), "LATEST FROM K-12 NEWS · NOV 5")


class Rendering(unittest.TestCase):
    TITLE = "Bristol Schools' Leak Hits 320,000 Files as Google AI Draws Scrutiny"
    SHOW = "Net Gain Edtech"

    def _img(self, theme, title=None, show=None):
        return Image.open(io.BytesIO(ss.render_strip(title or self.TITLE, show or self.SHOW, "2026-11-05", theme)))

    def test_size_is_three_times_the_display_size_with_transparency(self):
        im = self._img("light")
        self.assertEqual(im.size, (340 * 3, 52 * 3))
        self.assertEqual((ss.WIDTH, ss.HEIGHT), (340, 52))
        self.assertEqual(im.mode, "RGBA")
        self.assertEqual(im.getpixel((ss.WIDTH * 3 - 2, ss.HEIGHT * 3 - 2))[3], 0)   # empty corner is transparent

    def test_there_is_no_red_in_the_module(self):
        for theme in ("light", "dark"):
            reds = [p for p in self._img(theme).getdata() if p[3] > 200 and p[0] > 180 and p[1] < 80 and p[2] < 90]
            self.assertEqual(reds, [], theme)

    def test_the_play_button_sits_in_the_left_column_and_the_text_to_its_right(self):
        alpha = self._img("light").getchannel("A")
        button = alpha.crop((0, 0, ss.TEXT_X * 3 - 6, alpha.height)).getbbox()
        text = alpha.crop((ss.TEXT_X * 3 - 6, 0, alpha.width, alpha.height)).getbbox()
        self.assertIsNotNone(button)
        self.assertIsNotNone(text)
        self.assertLessEqual(button[2], 30 * 3 + 6)

    def test_text_colour_follows_the_theme(self):
        def ink_pixels(theme):
            im = self._img(theme)
            region = im.crop((ss.TEXT_X * 3, 70, im.width, 150))             # the headline rows
            return [p for p in region.getdata() if p[3] == 255]
        light, dark = ink_pixels("light"), ink_pixels("dark")
        self.assertTrue(light and dark)
        self.assertEqual(light[0][:3], ss.THEMES["light"]["ink"])
        self.assertEqual(dark[0][:3], ss.THEMES["dark"]["ink"])

    def test_a_long_headline_wraps_to_two_lines_inside_the_text_column(self):
        im = self._img("light")
        alpha = im.getchannel("A")
        line1 = alpha.crop((ss.TEXT_X * 3, 70, im.width, 96)).getbbox()
        line2 = alpha.crop((ss.TEXT_X * 3, 100, im.width, 150)).getbbox()
        self.assertIsNotNone(line1)
        self.assertIsNotNone(line2)
        self.assertLessEqual(line2[2] + ss.TEXT_X * 3, im.width)

    def test_a_two_line_headline_is_balanced_not_left_with_a_stranded_word(self):
        words = "Report: Education Ransomware Attacks Jump 54% in Q3".split()
        lines, font = ss._fit_headline(" ".join(words), (ss.WIDTH - ss.TEXT_X) * ss.SCALE)
        self.assertEqual(len(lines), 2)
        self.assertGreater(len(lines[1].split()), 1)

    def test_a_short_headline_stays_on_one_line_and_is_centred_beside_the_button(self):
        im = self._img("light", "Skillsoft jumps 10%")
        alpha = im.getchannel("A")
        text = alpha.crop((ss.TEXT_X * 3, 0, im.width, im.height)).getbbox()
        self.assertIsNotNone(text)
        top, bottom = text[1], text[3]
        self.assertAlmostEqual((top + bottom) / 2, im.height / 2, delta=12)       # centred within ~4 display px

    def test_a_very_long_headline_is_shrunk_then_ellipsised_to_stay_inside_the_image(self):
        long_title = ("Districts Urged to Disable YouTube and Gemini AI as Vermont District Refuses Ransom Demand "
                      "After Cyberattack and Regulators Open an Inquiry Into the Vendor Responsible for the Breach")
        im = self._img("light", long_title)
        box = im.getchannel("A").getbbox()
        self.assertIsNotNone(box)
        self.assertLessEqual(box[2], im.width)
        self.assertLessEqual(box[3], im.height)
        lines, _ = ss._fit_headline(long_title, (ss.WIDTH - ss.TEXT_X) * ss.SCALE)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"))

    def test_the_height_does_not_change_with_the_headline(self):
        sizes = {self._img("light", t).size for t in ("Short", self.TITLE, "x " * 80)}
        self.assertEqual(sizes, {(1020, 156)})

    def test_non_breaking_hyphen_is_drawn_as_an_ordinary_hyphen(self):
        a = ss.render_strip("K\u201112 breach", self.SHOW, "2026-10-16", "light")
        b = ss.render_strip("K-12 breach", self.SHOW, "2026-10-16", "light")
        self.assertEqual(a, b)

    def test_both_colourways_are_returned_and_differ(self):
        both = ss.render_both(self.TITLE, self.SHOW, "2026-11-05")
        self.assertEqual(set(both), {"light", "dark"})
        self.assertNotEqual(both["light"], both["dark"])

    def test_a_different_show_name_changes_the_image(self):
        self.assertNotEqual(ss.render_strip(self.TITLE, "Net Gain Edtech", "2026-11-05", "light"),
                            ss.render_strip(self.TITLE, "Net Gain Cleantech", "2026-11-05", "light"))


class FakeWP:
    def __init__(self, episode, fail=False):
        self.episode, self.fail, self.stored = episode, fail, None

    def get_show(self, show_id):
        return {"title": {"rendered": "Net Gain Edtech"}}

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
        self.assertTrue(ss.refresh_signature_strip(wp, {"id": 16, "name": "Net Gain Edtech"}, 590))
        show_id, payload = wp.stored
        self.assertEqual(show_id, 16)
        self.assertEqual(payload["episode_date"], "2026-10-16")
        self.assertEqual(set(payload), {"episode_date", "light_png", "dark_png"})
        for key in ("light_png", "dark_png"):
            self.assertTrue(base64.b64decode(payload[key]).startswith(b"\x89PNG"))

    def test_the_show_name_is_read_from_the_show_when_the_context_has_none(self):
        wp = FakeWP(self.EP)
        self.assertTrue(ss.refresh_signature_strip(wp, {"id": 16}, 590))
        self.assertIsNotNone(wp.stored)

    def test_a_show_with_no_name_is_skipped_not_published_unlabelled(self):
        wp = FakeWP(self.EP)
        wp.get_show = lambda show_id: {"title": {"rendered": ""}}
        self.assertFalse(ss.refresh_signature_strip(wp, {"id": 16}, 590))
        self.assertIsNone(wp.stored)

    def test_a_failure_is_swallowed_and_reported_as_false(self):
        self.assertFalse(ss.refresh_signature_strip(FakeWP(self.EP, fail=True), {"id": 16, "name": "X"}, 590))

    def test_missing_title_or_date_is_skipped(self):
        self.assertFalse(ss.refresh_signature_strip(FakeWP({"meta": {}}), {"id": 16, "name": "X"}, 590))


if __name__ == "__main__":
    unittest.main()
