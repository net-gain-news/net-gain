import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from script_generation import (
    build_system_prompt,
    build_user_message,
    filter_recent_final_scripts,
    generate_script_for_show,
    strip_html,
)


class StripHtmlTests(unittest.TestCase):
    def test_strips_tags(self):
        self.assertEqual(strip_html("<p>Hello <b>world</b></p>"), "Hello world")

    def test_strips_script_and_style_blocks_entirely(self):
        html = "<style>.x{color:red}</style><p>Keep this</p><script>alert(1)</script>"
        self.assertEqual(strip_html(html), "Keep this")

    def test_collapses_whitespace_and_nbsp(self):
        self.assertEqual(strip_html("Hello&nbsp;&nbsp;world\n\n  there"), "Hello world there")

    def test_empty_input(self):
        self.assertEqual(strip_html(""), "")


class FilterRecentFinalScriptsTests(unittest.TestCase):
    def _episode(self, date, script=""):
        return {"meta": {"ng_episode_date": date, "ng_script_final": script}}

    def test_excludes_empty_scripts(self):
        episodes = [self._episode("2026-09-05", ""), self._episode("2026-09-06", "final text")]
        result = filter_recent_final_scripts(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-06", "final text")])

    def test_excludes_outside_lookback_window(self):
        episodes = [self._episode("2026-01-01", "too old"), self._episode("2026-09-06", "recent")]
        result = filter_recent_final_scripts(episodes, lookback_days=7, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-06", "recent")])

    def test_excludes_the_target_date_itself(self):
        episodes = [self._episode("2026-09-07", "today - should not appear as its own context")]
        result = filter_recent_final_scripts(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [])

    def test_returns_oldest_first(self):
        episodes = [self._episode("2026-09-06", "b"), self._episode("2026-09-04", "a")]
        result = filter_recent_final_scripts(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-04", "a"), ("2026-09-06", "b")])


class PromptBuildingTests(unittest.TestCase):
    def test_system_prompt_includes_guidelines_and_show_name(self):
        prompt = build_system_prompt("Always be upbeat.", "Net Gain Edtech")
        self.assertIn("Net Gain Edtech", prompt)
        self.assertIn("Always be upbeat.", prompt)
        self.assertIn("web_search", prompt)

    def test_user_message_with_no_history(self):
        message = build_user_message("2026-09-07", [])
        self.assertIn("2026-09-07", message)
        self.assertIn("first episode", message)

    def test_user_message_includes_recap(self):
        message = build_user_message("2026-09-07", [("2026-09-05", "story A"), ("2026-09-06", "story B")])
        self.assertIn("story A", message)
        self.assertIn("story B", message)
        self.assertIn("[2026-09-05]", message)


class GenerateScriptForShowTests(unittest.TestCase):
    def test_wires_guidelines_and_context_into_the_generate_call(self):
        class FakeWP:
            def get_page_content(self, page_id):
                self.requested_page_id = page_id
                return "<p>Be concise.</p>"

        captured = {}

        def fake_generate(system, user_content):
            captured["system"] = system
            captured["user_content"] = user_content
            return "the generated script"

        wp = FakeWP()
        show = {"name": "Net Gain Edtech", "guidelines_page_id": 42, "lookback_days": 30}
        recent_episodes = [{"meta": {"ng_episode_date": "2026-09-06", "ng_script_final": "yesterday's script"}}]

        result = generate_script_for_show(wp, fake_generate, show, "2026-09-07", recent_episodes)

        self.assertEqual(result, "the generated script")
        self.assertEqual(wp.requested_page_id, 42)
        self.assertIn("Be concise.", captured["system"])
        self.assertIn("yesterday's script", captured["user_content"])

    def test_falls_back_when_no_guidelines_page(self):
        class FakeWP:
            def get_page_content(self, page_id):
                raise AssertionError("should not be called when guidelines_page_id is falsy")

        def fake_generate(system, user_content):
            return system  # just echo so the test can inspect it

        show = {"name": "Net Gain Edtech", "guidelines_page_id": 0, "lookback_days": 30}
        result = generate_script_for_show(FakeWP(), fake_generate, show, "2026-09-07", [])

        self.assertIn("general good editorial judgment", result)


if __name__ == "__main__":
    unittest.main()
