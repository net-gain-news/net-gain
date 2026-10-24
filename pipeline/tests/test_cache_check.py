import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cache_check as cc


class Evaluate(unittest.TestCase):
    def test_a_shared_cache_is_healthy(self):
        self.assertEqual(cc.evaluate("Accept-Encoding", 0.22), [])

    def test_vary_user_agent_coming_back_is_a_problem_whatever_the_timing(self):
        problems = cc.evaluate("Accept-Encoding, User-Agent", 0.2)
        self.assertEqual(len(problems), 1)
        self.assertIn("split per browser", problems[0])

    def test_a_slow_second_browser_is_a_problem(self):
        problems = cc.evaluate("Accept-Encoding", 3.4)
        self.assertEqual(len(problems), 1)
        self.assertIn("3.4s", problems[0])

    def test_both_problems_are_reported_together(self):
        self.assertEqual(len(cc.evaluate("user-agent", 2.0)), 2)

    def test_a_missing_header_and_timing_are_not_a_problem(self):
        self.assertEqual(cc.evaluate("", None), [])


if __name__ == "__main__":
    unittest.main()
