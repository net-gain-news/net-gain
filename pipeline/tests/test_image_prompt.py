import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_prompt import RESPONSE_SCHEMA, build_system_prompt, generate_image_prompt_for_episode


class BuildSystemPromptTests(unittest.TestCase):
    def test_includes_show_name(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Net Gain Edtech", prompt)

    def test_requires_a_concrete_detail_not_just_a_category(self):
        """Rewritten 2026-09-16 after three live episodes all produced generic
        conceptual imagery (anonymous people, vague screens) instead of
        anything tied to the lead story's actual specifics."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("concrete", prompt.lower())

    def test_bans_the_observed_stock_photo_cliches_by_name(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("shaking hands", prompt)
        self.assertIn("conference table", prompt)

    def test_disallows_logos_outright_with_no_exception(self):
        """Human-operator decision (2026-09-16): logos disallowed outright -
        AI-drawn logos render inaccurately, and a real-logo-asset pipeline
        wasn't worth the time investment."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Do not include any company logo", prompt)
        self.assertNotIn("logo is acceptable", prompt)

    def test_allows_financial_iconography_without_hardcoding_dollar_sign(self):
        """Human-operator decision (2026-09-16): money symbols are fine for
        financial stories, but must not default to the US dollar sign - not
        every show's stories are US-market-specific."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("currency", prompt.lower())
        self.assertIn("do not default to the us dollar sign", prompt.lower())

    def test_financial_iconography_may_not_spell_out_the_amount(self):
        """Live incident (2026-09-17): the first real episode under the
        rewritten prompt showed a genuine, on-topic tablet/AI-tutoring scene
        (the concrete-detail fix working) but also rendered the word
        "BILLION" as garbled background text for a $400M-pledge story - the
        financial-iconography rule permitted graphical money symbols but
        never explicitly excluded spelling the amount out, so it won out
        over the general no-readable-text rule on this exact overlap."""
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("never spell out the actual amount", prompt.lower())


class GenerateImagePromptForEpisodeTests(unittest.TestCase):
    def test_wires_schema_and_no_web_search_into_the_generate_call(self):
        captured = {}

        def fake_generate(system, user_content, tools, response_schema):
            captured["system"] = system
            captured["user_content"] = user_content
            captured["tools"] = tools
            captured["response_schema"] = response_schema
            return json.dumps({"image_prompt": "A concrete scene."})

        result = generate_image_prompt_for_episode(
            fake_generate, "Net Gain Edtech", "2026-09-16", "Today's script text."
        )

        self.assertEqual(result, "A concrete scene.")
        self.assertEqual(captured["tools"], [])
        self.assertIs(captured["response_schema"], RESPONSE_SCHEMA)
        self.assertIn("Today's script text.", captured["user_content"])
        self.assertIn("2026-09-16", captured["user_content"])


if __name__ == "__main__":
    unittest.main()
