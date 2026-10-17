import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from title_width import (
    AIOSEO_TITLE_PX_MAX,
    AIOSEO_TITLE_PX_MIN,
    description_problem,
    search_field_distance,
    search_field_problems,
    title_width_px,
    title_width_problem,
)


class TitleWidthTests(unittest.TestCase):
    def test_widths_match_what_a_real_browser_measured_at_20px_arial(self):
        # Measured with canvas.measureText in a browser, 2026-10-16; the table has no kerning, so it may read a few px high.
        measured = {
            "Bett Asia Opens in KL as UK Launches National AI Lab": 490,
            "Burnaby School Cyberattack, Frederick County Rethinks Gemini": 569,
            "Districts Urged to Disable YouTube, Gemini; Vermont Ransomware": 593,
            "ChatGPT Teen Mode Called Unsafe, Easthampton Schools Go Dark": 605,
            "OpenAI Sued by 8 States, Burnaby Breach Confirmed": 478,
        }
        for text, browser in measured.items():
            self.assertAlmostEqual(title_width_px(text), browser, delta=6, msg=text)

    def test_wide_letters_cost_more_than_narrow_ones(self):
        self.assertGreater(title_width_px("WWWWWWWWWW"), title_width_px("iiiiiiiiii") * 4)

    def test_an_unknown_character_is_priced_wide_so_the_check_can_only_get_stricter(self):
        self.assertGreaterEqual(title_width_px("☃"), title_width_px("n"))

    def test_the_target_window_sits_inside_aioseos_edges(self):
        inside = "Frederick County Bans Student AI as Spokane Breach Widens"
        self.assertIsNone(title_width_problem(inside))
        self.assertTrue(AIOSEO_TITLE_PX_MIN < title_width_px(inside) < AIOSEO_TITLE_PX_MAX)

    def test_titles_near_the_edges_are_rejected_before_aioseo_would_mind(self):
        self.assertIn("at most 580", title_width_problem("ChatGPT Teen Mode Called Unsafe, Easthampton Schools Go Dark"))
        self.assertIn("at least 430", title_width_problem("Burnaby Breach Confirmed"))

    def test_description_window(self):
        self.assertIsNone(description_problem("x" * 130))
        self.assertIsNone(description_problem("x" * 156))
        self.assertIn("at most 156", description_problem("x" * 157))
        self.assertIn("at least 130", description_problem("x" * 129))
        self.assertIn("at least 130", description_problem(""))

    def test_problems_and_distance(self):
        good = {"aioseo_title": "Frederick County Bans Student AI as Spokane Breach Widens", "aioseo_description": "x" * 145}
        self.assertEqual(search_field_problems(good), {})
        self.assertEqual(search_field_distance(good), 0)
        bad = {"aioseo_title": "Short", "aioseo_description": "x" * 200}
        self.assertEqual(set(search_field_problems(bad)), {"aioseo_title", "aioseo_description"})
        self.assertGreater(search_field_distance(bad), search_field_distance({"aioseo_title": good["aioseo_title"], "aioseo_description": "x" * 170}))


if __name__ == "__main__":
    unittest.main()
