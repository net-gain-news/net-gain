import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warm_cache as wc


class Warm(unittest.TestCase):
    def test_urls_include_the_main_pages_and_the_newest_episode(self):
        urls = wc.urls_to_warm("/edtech/some-episode/")
        self.assertIn("https://netgain.news/", urls)
        self.assertIn("https://netgain.news/edtech/", urls)
        self.assertEqual(urls[-1], "https://netgain.news/edtech/some-episode/")

    def test_without_a_latest_episode_the_fixed_pages_still_warm(self):
        urls = wc.urls_to_warm("")
        self.assertEqual(len(urls), len(wc.PATHS))

    def test_quick_successes_log_nothing(self):
        self.assertEqual(wc.problems([("u", 0, 200, 0.3), ("u", 1, 200, 1.9)]), [])

    def test_slow_pages_and_errors_are_reported(self):
        lines = wc.problems([("https://netgain.news/", 0, 200, 4.4), ("https://netgain.news/x/", 1, 502, 0.2)])
        self.assertEqual(len(lines), 2)
        self.assertIn("slow 4.4s", lines[0])
        self.assertIn("HTTP 502", lines[1])


if __name__ == "__main__":
    unittest.main()
