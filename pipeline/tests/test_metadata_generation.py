import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadata_generation import (
    MAX_METADATA_ATTEMPTS,
    RESPONSE_SCHEMA,
    TITLE_MAX_CHARS,
    build_system_prompt,
    generate_metadata_for_episode,
    overlong_titles,
)


class BuildSystemPromptTests(unittest.TestCase):
    def test_includes_show_name_and_field_rules(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Net Gain Edtech", prompt)
        self.assertIn("youtube_tags", prompt)
        self.assertIn("125 characters", prompt)

    def test_caps_the_captivate_and_website_titles_at_two_stories_and_sixty_five_characters(self):
        """Operator decision 2026-10-02: three-story, 65-90 character titles were hard to read and got
        cut off in podcast apps and Google. Limit set at 65 after reviewing real two-story headlines."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertEqual(TITLE_MAX_CHARS, 65)
        self.assertIn("at most 65", prompt)
        self.assertIn("at most TWO", prompt)
        self.assertIn("lead", prompt)

    def test_titles_may_join_two_stories_with_a_comma_a_semicolon_or_as(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("a comma, a semicolon, or \"as\"", prompt)

    def test_youtube_title_rule_is_unchanged(self):
        self.assertIn("youtube_title: under 100 characters", build_system_prompt("Net Gain Edtech"))


class GenerateMetadataForEpisodeTests(unittest.TestCase):
    def _fake_metadata(self):
        return {
            "captivate_title": "Title",
            "captivate_notes": "Notes",
            "aioseo_title": "SEO Title",
            "aioseo_description": "SEO description",
            "website_excerpt": "A short teaser.",
            "youtube_title": "YT Title",
            "youtube_description": "YT description",
            "youtube_tags": ["tag1", "tag2"],
        }

    def test_wires_schema_and_no_web_search_into_the_generate_call(self):
        captured = {}

        def fake_generate(system, user_content, tools, response_schema):
            captured["system"] = system
            captured["user_content"] = user_content
            captured["tools"] = tools
            captured["response_schema"] = response_schema
            return json.dumps(self._fake_metadata())

        result = generate_metadata_for_episode(fake_generate, "Net Gain Edtech", "2026-09-07", "Today's script text.")

        self.assertEqual(result["captivate_title"], "Title")
        self.assertEqual(result["youtube_tags"], ["tag1", "tag2"])
        self.assertEqual(captured["tools"], [])  # no web search - repackaging, not researching
        self.assertIs(captured["response_schema"], RESPONSE_SCHEMA)
        self.assertIn("Today's script text.", captured["user_content"])
        self.assertIn("2026-09-07", captured["user_content"])


class TitleLimitGuardTests(unittest.TestCase):
    def _meta(self, captivate="Short title", aioseo="Short SEO title"):
        return {
            "captivate_title": captivate, "captivate_notes": "n", "aioseo_title": aioseo,
            "aioseo_description": "d", "website_excerpt": "e", "youtube_title": "y" * 95,
            "youtube_description": "yd", "youtube_tags": ["t"],
        }

    def _run(self, metas):
        calls = []

        def fake(system, user_content, tools, response_schema):
            calls.append(1)
            return json.dumps(metas[min(len(calls), len(metas)) - 1])

        return calls, generate_metadata_for_episode(fake, "Net Gain Edtech", "2026-10-02", "script")

    def test_exactly_sixty_five_characters_is_allowed(self):
        self.assertEqual(overlong_titles(self._meta(captivate="x" * 65, aioseo="y" * 65)), {})
        self.assertEqual(overlong_titles(self._meta(captivate="x" * 66)), {"captivate_title": 66})

    def test_the_youtube_title_is_not_subject_to_the_title_limit(self):
        calls, result = self._run([self._meta()])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result["youtube_title"]), 95)

    def test_an_over_limit_title_is_regenerated_and_the_compliant_attempt_returned(self):
        calls, result = self._run([self._meta(captivate="x" * 80), self._meta(captivate="Fits fine")])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["captivate_title"], "Fits fine")

    def test_when_no_attempt_complies_each_title_takes_its_shortest_attempt(self):
        metas = [
            self._meta(captivate="c" * 90, aioseo="a" * 70),
            self._meta(captivate="c" * 70, aioseo="a" * 85),
            self._meta(captivate="c" * 80, aioseo="a" * 75),
        ]
        calls, result = self._run(metas)
        self.assertEqual(len(calls), MAX_METADATA_ATTEMPTS)
        self.assertEqual(len(result["captivate_title"]), 70)
        self.assertEqual(len(result["aioseo_title"]), 70)


if __name__ == "__main__":
    unittest.main()
