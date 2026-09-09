import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadata_generation import RESPONSE_SCHEMA, build_system_prompt, generate_metadata_for_episode


class BuildSystemPromptTests(unittest.TestCase):
    def test_includes_show_name_and_field_rules(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Net Gain Edtech", prompt)
        self.assertIn("youtube_tags", prompt)
        self.assertIn("125 characters", prompt)


class GenerateMetadataForEpisodeTests(unittest.TestCase):
    def _fake_metadata(self):
        return {
            "captivate_title": "Title",
            "captivate_notes": "Notes",
            "aioseo_title": "SEO Title",
            "aioseo_description": "SEO description",
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


if __name__ == "__main__":
    unittest.main()
