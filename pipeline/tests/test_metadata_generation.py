import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadata_generation import (
    AUDIT_SCHEMA,
    MAX_METADATA_ATTEMPTS,
    RESPONSE_SCHEMA,
    StoryOrderError,
    TITLE_MAX_CHARS,
    build_system_prompt,
    find_order_violations,
    generate_metadata_for_episode,
    overlong_titles,
)



def good_audit(n=3):
    """An audit saying every field follows the script's order (all fields lead with story 1)."""
    return {"stories": [f"story {i}" for i in range(1, n + 1)],
            "order": {"captivate_title": [1, 2], "captivate_notes": list(range(1, n + 1)), "aioseo_title": [1, 2],
                      "aioseo_description": [1, 2], "website_excerpt": list(range(1, n + 1)),
                      "youtube_title": [1], "youtube_description": [1, 2]}}


def route(metas, audits=None):
    """A fake generate(): metadata calls get the next meta, audit calls get the next audit (last repeats)."""
    audits = audits or [good_audit()]
    log = {"meta": [], "audit": []}

    def fake(system, user_content, tools, response_schema):
        if response_schema is AUDIT_SCHEMA:
            log["audit"].append(user_content)
            return json.dumps(audits[min(len(log["audit"]), len(audits)) - 1])
        log["meta"].append(user_content)
        return json.dumps(metas[min(len(log["meta"]), len(metas)) - 1])

    return fake, log


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
            if response_schema is AUDIT_SCHEMA:
                return json.dumps(good_audit())
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
        fake, log = route(metas)
        result = generate_metadata_for_episode(fake, "Net Gain Edtech", "2026-10-02", "script")
        return log["meta"], result

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


class StoryOrderRuleTests(unittest.TestCase):
    def test_the_prompt_makes_script_order_absolute_and_bars_promoting_a_ticker_story(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("STORY ORDER - NO EXCEPTIONS", prompt)
        self.assertIn("Never promote or reorder a story", prompt)
        self.assertIn("ticker symbol", prompt)
        self.assertIn("A ticker symbol or company never changes the story order", prompt)
        self.assertIn("story 1 first", prompt)
        self.assertIn("ONE later story after it (in script order)", prompt)
        self.assertNotIn("single most search- and recommendation-relevant keyword", prompt)  # the instruction that caused it


def audit_with(**overrides):
    audit = good_audit()
    audit["order"].update(overrides)
    return audit


class FindOrderViolationsTests(unittest.TestCase):
    def test_a_correctly_ordered_set_has_no_violations(self):
        self.assertEqual(find_order_violations(good_audit()), [])

    def test_the_real_2026_10_06_failure_is_caught(self):
        """All three titles led with story 3 (Nelnet/Entab) then story 1, and two descriptions began with story 3."""
        audit = audit_with(captivate_title=[3, 1], aioseo_title=[3, 1], youtube_title=[3, 1],
                           aioseo_description=[3, 1, 2], youtube_description=[3, 1, 2])
        problems = find_order_violations(audit)
        for field in ("captivate_title", "aioseo_title", "youtube_title", "aioseo_description", "youtube_description"):
            self.assertTrue(any(p.startswith(field) for p in problems), field)
        self.assertFalse(any(p.startswith("website_excerpt") or p.startswith("captivate_notes") for p in problems))

    def test_a_title_must_lead_with_story_one(self):
        self.assertTrue(find_order_violations(audit_with(captivate_title=[2])))
        self.assertTrue(find_order_violations(audit_with(youtube_title=[])))

    def test_a_title_names_story_one_plus_at_most_one_later_story_in_order(self):
        self.assertEqual(find_order_violations(audit_with(captivate_title=[1])), [])
        self.assertEqual(find_order_violations(audit_with(captivate_title=[1, 3])), [])   # 10/1's title: 1 then 3, in order
        self.assertTrue(find_order_violations(audit_with(captivate_title=[1, 2, 3])))     # three stories: over the two-story rule
        self.assertTrue(find_order_violations(audit_with(aioseo_title=[3, 1])))           # later story ahead of an earlier one

    def test_abstracts_and_notes_may_not_skip_the_lead_or_repeat_or_regress(self):
        self.assertTrue(find_order_violations(audit_with(aioseo_description=[2, 3])))
        self.assertTrue(find_order_violations(audit_with(website_excerpt=[1, 3, 2])))
        self.assertTrue(find_order_violations(audit_with(captivate_notes=[1, 2, 2])))

    def test_an_abstract_that_names_no_story_is_not_a_violation_but_an_empty_title_is(self):
        self.assertEqual(find_order_violations(audit_with(website_excerpt=[])), [])
        self.assertTrue(find_order_violations(audit_with(aioseo_title=[])))

    def test_story_numbers_outside_the_script_are_rejected(self):
        self.assertTrue(find_order_violations(audit_with(captivate_notes=[1, 2, 7])))


class StoryOrderGuardTests(unittest.TestCase):
    META = {"captivate_title": "T", "captivate_notes": "N", "aioseo_title": "A", "aioseo_description": "D",
            "website_excerpt": "E", "youtube_title": "Y", "youtube_description": "YD", "youtube_tags": ["t"]}

    def test_a_wrongly_ordered_attempt_is_regenerated_with_the_script_order_spelled_out(self):
        bad = audit_with(captivate_title=[3, 1])
        bad["stories"] = ["South Carolina cyberattack", "Oklahoma AI detectors", "Nelnet buys Entab"]
        fake, log = route([self.META, self.META], [bad, good_audit()])
        result = generate_metadata_for_episode(fake, "Net Gain Edtech", "2026-10-06", "script text")
        self.assertEqual(result["captivate_title"], "T")
        self.assertEqual(len(log["meta"]), 2)
        self.assertNotIn("PREVIOUS ATTEMPT", log["meta"][0])
        self.assertIn("PREVIOUS ATTEMPT BROKE THE STORY-ORDER RULE", log["meta"][1])
        self.assertIn("1. South Carolina cyberattack; 2. Oklahoma AI detectors; 3. Nelnet buys Entab", log["meta"][1])
        self.assertIn("captivate_title", log["meta"][1])

    def test_it_fails_loudly_when_no_attempt_keeps_the_order(self):
        fake, log = route([self.META], [audit_with(youtube_title=[3, 1])])
        with self.assertRaises(StoryOrderError) as ctx:
            generate_metadata_for_episode(fake, "Net Gain Edtech", "2026-10-06", "script")
        self.assertEqual(len(log["meta"]), MAX_METADATA_ATTEMPTS)
        self.assertIn("youtube_title", str(ctx.exception))

    def test_an_unreadable_audit_counts_as_a_failure_not_a_pass(self):
        calls = {"meta": 0}

        def fake(system, user_content, tools, response_schema):
            if response_schema is AUDIT_SCHEMA:
                return "not json"
            calls["meta"] += 1
            return json.dumps(self.META)

        with self.assertRaises(StoryOrderError):
            generate_metadata_for_episode(fake, "Net Gain Edtech", "2026-10-06", "script")
        self.assertEqual(calls["meta"], MAX_METADATA_ATTEMPTS)

    def test_the_shortest_title_fallback_never_borrows_from_a_wrongly_ordered_attempt(self):
        wrong_but_short = dict(self.META, captivate_title="x" * 10, aioseo_title="y" * 10)
        right_but_long = dict(self.META, captivate_title="c" * 80, aioseo_title="a" * 80)
        fake, log = route([wrong_but_short, right_but_long], [audit_with(captivate_title=[3, 1]), good_audit()])
        result = generate_metadata_for_episode(fake, "Net Gain Edtech", "2026-10-06", "script")
        self.assertEqual(len(result["captivate_title"]), 80)   # NOT the 10-character one from the mis-ordered attempt
        self.assertEqual(len(result["aioseo_title"]), 80)


if __name__ == "__main__":
    unittest.main()
