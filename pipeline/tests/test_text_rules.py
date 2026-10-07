import json
import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cards
from anthropic_client import generate
from metadata_generation import generate_metadata_for_episode
from text_rules import K12_PROMPT_RULE, NB_HYPHEN, apply_text_rules, machine_safe

NB = NB_HYPHEN


class ApplyTextRulesTests(unittest.TestCase):
    def test_every_dash_variant_between_k_and_12_becomes_the_non_breaking_hyphen(self):
        for dash in ["-", "‐", "‑", "‒", "–", "—", "−"]:
            self.assertEqual(apply_text_rules(f"K{dash}12 districts"), f"K{NB}12 districts", repr(dash))

    def test_prek_and_lowercase_forms_and_punctuation(self):
        self.assertEqual(apply_text_rules("PreK-12, and k-12."), f"PreK{NB}12, and k{NB}12.")
        self.assertEqual(apply_text_rules("(K-12)"), f"(K{NB}12)")

    def test_other_hyphens_and_numbers_are_untouched(self):
        for text in ["state-of-the-art", "K-120 bus routes", "R-12 refrigerant", "BK-12", "A-K-12 grid"[0:4], "K 12"]:
            self.assertEqual(apply_text_rules(text), text, text)

    def test_urls_are_never_rewritten(self):
        text = 'See <a href="https://example.com/news/k-12-budget-2026">K-12 budget</a> or https://x.test/K-12'
        self.assertEqual(
            apply_text_rules(text),
            f'See <a href="https://example.com/news/k-12-budget-2026">K{NB}12 budget</a> or https://x.test/K-12',
        )

    def test_works_inside_json_text_and_is_idempotent(self):
        raw = json.dumps({"title": "Big K-12 news", "tags": ["K-12"]})
        once = apply_text_rules(raw)
        self.assertEqual(apply_text_rules(once), once)
        self.assertEqual(json.loads(once)["title"], f"Big K{NB}12 news")

    def test_machine_safe_restores_ordinary_hyphens_and_handles_empty(self):
        self.assertEqual(machine_safe(f"K{NB}12 trends"), "K-12 trends")
        self.assertEqual(machine_safe(""), "")
        self.assertEqual(apply_text_rules(""), "")
        self.assertIsNone(apply_text_rules(None))


class PromptAndClientTests(unittest.TestCase):
    def test_the_rule_is_in_every_generators_prompt(self):
        import card_text
        import metadata_generation
        import script_generation

        for prompt in (script_generation.build_system_prompt("guidelines", "Show"),
                       metadata_generation.build_system_prompt("Show"),
                       card_text.build_system_prompt("Show")):
            self.assertIn("K-12 SPELLING", prompt)
            self.assertIn(NB, prompt)
        self.assertIn("U+2011", K12_PROMPT_RULE)

    def test_generate_applies_the_rule_whatever_the_model_wrote(self):
        response = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Today in K-12 news.")])
        client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))
        self.assertEqual(generate(client, system="s", user_content="go", tools=[]), f"Today in K{NB}12 news.")

    def test_metadata_gets_the_rule_but_youtube_tags_keep_ordinary_hyphens(self):
        fields = {"captivate_title": "K-12 hacked", "captivate_notes": "<p>K-12 story</p>", "aioseo_title": "K-12 hacked",
                  "aioseo_description": "About K-12", "website_excerpt": "K-12", "youtube_title": "K-12 hacked",
                  "youtube_description": "K-12", "youtube_tags": ["K-12", "ransomware"]}
        from anthropic_client import generate as real_generate  # noqa: F401  (the real wrapper normalizes; simulate it here)
        def fake(system, user_content, tools, response_schema):
            if "stories" in (response_schema.get("properties") or {}):
                order = {f: [1] for f in ["captivate_title", "captivate_notes", "aioseo_title", "aioseo_description", "website_excerpt", "youtube_title", "youtube_description"]}
                return json.dumps({"stories": ["only story"], "order": order})
            return apply_text_rules(json.dumps(fields))
        result = generate_metadata_for_episode(fake, "Show", "2026-10-07", "script")
        self.assertEqual(result["captivate_title"], f"K{NB}12 hacked")
        self.assertEqual(result["youtube_title"], f"K{NB}12 hacked")
        self.assertEqual(result["youtube_tags"], ["K-12", "ransomware"])


class CardGlyphTests(unittest.TestCase):
    def test_cards_draw_the_non_breaking_hyphen_like_a_hyphen_never_as_a_missing_glyph_box(self):
        plain = cards.CardContent(date(2026, 10, 7), headline="Districts brace for K-12 budget cuts", keywords=["K-12 budgets", "AI", "Deals"])
        nb = cards.CardContent(date(2026, 10, 7), headline=f"Districts brace for K{NB}12 budget cuts", keywords=[f"K{NB}12 budgets", "AI", "Deals"])
        for template in ("A", "E", "B1", "D3"):
            for kind, window in (("wide", (8, 584)), ("square", (0, 2600))):
                a = cards.render_card(template, plain, kind, window)
                b = cards.render_card(template, nb, kind, window)
                self.assertEqual(a.tobytes(), b.tobytes(), f"{template} {kind}")

    def test_the_mono_face_really_lacks_the_glyph_which_is_why_the_mapping_exists(self):
        mono = cards.mono(100)
        self.assertEqual(mono.getbbox(NB), mono.getbbox(""))        # same as a missing-glyph box
        self.assertNotEqual(mono.getbbox(NB), mono.getbbox("-"))
        self.assertEqual(cards.tlen(f"K{NB}12", mono), cards.tlen("K-12", mono))


if __name__ == "__main__":
    unittest.main()
