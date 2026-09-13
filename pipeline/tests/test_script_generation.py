import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from script_generation import (
    build_system_prompt,
    build_user_message,
    filter_recent_episodes_for_context,
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


class FilterRecentEpisodesForContextTests(unittest.TestCase):
    def _episode(self, date, final="", draft="", reviewed_status=None):
        meta = {"ng_episode_date": date, "ng_script_final": final, "ng_script_draft": draft}
        if reviewed_status is not None:
            meta["ng_step_status"] = {"script_reviewed": {"status": reviewed_status}}
        return {"meta": meta}

    def test_excludes_empty_scripts(self):
        episodes = [self._episode("2026-09-05", final=""), self._episode("2026-09-06", final="final text")]
        result = filter_recent_episodes_for_context(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-06", "final text", None)])

    def test_excludes_outside_lookback_window(self):
        episodes = [self._episode("2026-01-01", final="too old"), self._episode("2026-09-06", final="recent")]
        result = filter_recent_episodes_for_context(episodes, lookback_days=7, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-06", "recent", None)])

    def test_excludes_the_target_date_itself(self):
        episodes = [self._episode("2026-09-07", final="today - should not appear as its own context")]
        result = filter_recent_episodes_for_context(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [])

    def test_returns_oldest_first(self):
        episodes = [self._episode("2026-09-06", final="b"), self._episode("2026-09-04", final="a")]
        result = filter_recent_episodes_for_context(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-04", "a", None), ("2026-09-06", "b", None)])

    def test_includes_draft_when_edit_was_substantial(self):
        episodes = [
            self._episode("2026-09-06", final="the real final", draft="the ai draft", reviewed_status="done")
        ]
        result = filter_recent_episodes_for_context(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-06", "the real final", "the ai draft")])

    def test_excludes_draft_when_flagged_degraded(self):
        """A near-identical draft/final pair (Section 5.2's own similarity check
        already flagged it) has no editorial-preference signal to teach."""
        episodes = [
            self._episode("2026-09-06", final="barely edited", draft="barely edited draft", reviewed_status="degraded")
        ]
        result = filter_recent_episodes_for_context(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-06", "barely edited", None)])

    def test_excludes_draft_when_missing_entirely(self):
        episodes = [self._episode("2026-09-06", final="final only", draft="", reviewed_status="done")]
        result = filter_recent_episodes_for_context(episodes, lookback_days=30, before_date="2026-09-07")
        self.assertEqual(result, [("2026-09-06", "final only", None)])


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
        message = build_user_message(
            "2026-09-07", [("2026-09-05", "story A", None), ("2026-09-06", "story B", None)]
        )
        self.assertIn("story A", message)
        self.assertIn("story B", message)
        self.assertIn("[2026-09-05]", message)

    def test_user_message_shows_draft_alongside_final_when_present(self):
        message = build_user_message(
            "2026-09-07", [("2026-09-06", "the host's final version", "the original draft")]
        )
        self.assertIn("the original draft", message)
        self.assertIn("the host's final version", message)
        self.assertIn("Your original draft", message)
        self.assertIn("actual final", message)

    def test_user_message_omits_draft_labels_when_no_draft(self):
        message = build_user_message("2026-09-07", [("2026-09-06", "final only", None)])
        self.assertNotIn("Your original draft", message)


class GenerateScriptForShowTests(unittest.TestCase):
    def test_wires_guidelines_and_context_into_the_generate_call(self):
        class FakeWP:
            def get_page_content(self, page_id):
                self.requested_page_id = page_id
                return "<p>Be concise.</p>"

        captured = {}

        def fake_generate(system, user_content, **kwargs):
            captured["system"] = system
            captured["user_content"] = user_content
            captured["kwargs"] = kwargs
            return "the generated script"

        wp = FakeWP()
        show = {"name": "Net Gain Edtech", "guidelines_page_id": 42, "lookback_days": 30}
        recent_episodes = [{"meta": {"ng_episode_date": "2026-09-06", "ng_script_final": "yesterday's script"}}]

        result = generate_script_for_show(wp, fake_generate, show, "2026-09-07", recent_episodes)

        self.assertEqual(result, "the generated script")
        self.assertEqual(wp.requested_page_id, 42)
        self.assertIn("Be concise.", captured["system"])
        self.assertIn("yesterday's script", captured["user_content"])
        self.assertEqual(captured["kwargs"].get("effort"), "high")

    def test_falls_back_when_no_guidelines_page(self):
        class FakeWP:
            def get_page_content(self, page_id):
                raise AssertionError("should not be called when guidelines_page_id is falsy")

        def fake_generate(system, user_content, **kwargs):
            return system  # just echo so the test can inspect it

        show = {"name": "Net Gain Edtech", "guidelines_page_id": 0, "lookback_days": 30}
        result = generate_script_for_show(FakeWP(), fake_generate, show, "2026-09-07", [])

        self.assertIn("general good editorial judgment", result)


if __name__ == "__main__":
    unittest.main()
