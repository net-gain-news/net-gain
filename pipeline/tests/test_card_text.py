import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import card_text
from metadata_generation import StoryOrderError

GOOD = {"headline": "South Carolina school-choice payments hit by another cyberattack",
        "words": [{"story": 1, "word": "Cyberattack"}, {"story": 2, "word": "AI detectors"}, {"story": 3, "word": "Acquisition"}]}
STORIES = ["South Carolina payments cyberattack", "Oklahoma AI detectors", "Nelnet buys Entab"]


def fake_generate(texts, audits):
    """Returns responses in order: generation calls draw from `texts`, audit calls from `audits`."""
    texts, audits, calls = list(texts), list(audits), []

    def generate(system, user_content, tools, response_schema):
        calls.append(response_schema is card_text.AUDIT_SCHEMA)
        return json.dumps(audits.pop(0) if response_schema is card_text.AUDIT_SCHEMA else texts.pop(0))

    generate.calls = calls
    return generate


def audit(headline_story=1, word_stories=(1, 2, 3)):
    return {"stories": STORIES, "headline_story": headline_story, "word_stories": list(word_stories)}


class ShapeTests(unittest.TestCase):
    def test_good_text_has_no_problems(self):
        self.assertEqual(card_text.shape_problems(GOOD), [])

    def test_headline_length_and_period(self):
        self.assertTrue(card_text.shape_problems(dict(GOOD, headline="x" * 71)))
        self.assertTrue(card_text.shape_problems(dict(GOOD, headline="Too short")))
        self.assertTrue(card_text.shape_problems(dict(GOOD, headline="A fine headline that ends in a period.")))

    def test_topic_words_must_be_short_mixed_case_and_in_story_order(self):
        words = lambda *ws: dict(GOOD, words=[{"story": i + 1, "word": w} for i, w in enumerate(ws)])
        self.assertTrue(card_text.shape_problems(words("CYBERATTACK", "AI detectors", "Acquisition")))   # shouty
        self.assertTrue(card_text.shape_problems(words("Cyber attack of the century", "AI", "Deal")))    # too long
        self.assertTrue(card_text.shape_problems(words("A b c", "AI", "Deal")))                         # three words
        self.assertEqual(card_text.shape_problems(words("AI", "NCAA rules", "Deal")), [])                # short acronyms are fine
        self.assertTrue(card_text.shape_problems(dict(GOOD, words=[{"story": 2, "word": "Policy"}])))     # must start at story 1
        self.assertTrue(card_text.shape_problems(dict(GOOD, words=[])))


class GenerateTests(unittest.TestCase):
    def test_returns_headline_and_keywords_when_the_audit_agrees(self):
        gen = fake_generate([GOOD], [audit()])
        result = card_text.generate_card_text(gen, "Net Gain Edtech", "2026-10-06", "script")
        self.assertEqual(result["headline"], GOOD["headline"])
        self.assertEqual(result["keywords"], ["Cyberattack", "AI detectors", "Acquisition"])

    def test_a_headline_about_a_later_story_is_regenerated(self):
        """The 10/6 failure mode: a title led with story 3. Same guard as the metadata step."""
        gen = fake_generate([GOOD, GOOD], [audit(headline_story=3), audit()])
        result = card_text.generate_card_text(gen, "Net Gain Edtech", "2026-10-06", "script")
        self.assertEqual(result["headline"], GOOD["headline"])
        self.assertEqual(gen.calls, [False, True, False, True])

    def test_topic_words_reordered_by_the_model_are_caught(self):
        gen = fake_generate([GOOD, GOOD], [audit(word_stories=(3, 2, 1)), audit()])
        card_text.generate_card_text(gen, "Net Gain Edtech", "2026-10-06", "script")
        self.assertEqual(gen.calls.count(True), 2)

    def test_raises_story_order_error_when_no_attempt_passes(self):
        gen = fake_generate([GOOD] * 3, [audit(headline_story=2)] * 3)
        with self.assertRaises(StoryOrderError):
            card_text.generate_card_text(gen, "Net Gain Edtech", "2026-10-06", "script")

    def test_a_shape_problem_skips_the_audit_call_and_retries(self):
        gen = fake_generate([dict(GOOD, headline="Too short"), GOOD], [audit()])
        card_text.generate_card_text(gen, "Net Gain Edtech", "2026-10-06", "script")
        self.assertEqual(gen.calls, [False, False, True])

    def test_an_unreadable_audit_counts_as_a_failure_not_a_pass(self):
        def generate(system, user_content, tools, response_schema):
            return "not json" if response_schema is card_text.AUDIT_SCHEMA else json.dumps(GOOD)
        with self.assertRaises(StoryOrderError):
            card_text.generate_card_text(generate, "Net Gain Edtech", "2026-10-06", "script")

    def test_the_prompt_forbids_copying_link_captions_and_reordering(self):
        prompt = card_text.build_system_prompt("Net Gain Edtech")
        self.assertIn("STORY ORDER - NO EXCEPTIONS", prompt)
        self.assertIn("do NOT copy a caption", prompt)


if __name__ == "__main__":
    unittest.main()
