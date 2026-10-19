"""Headlines must report the news (story 1's new development), not just name the topic. Operator rule 2026-10-19:
a follow-up story ("new reporting on the ETS breach") was headlined "ETS Student Data Breach", which read as old news."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadata_generation import (
    AUDIT_SCHEMA,
    MAX_METADATA_ATTEMPTS,
    build_audit_system_prompt,
    build_system_prompt,
    build_user_message,
    find_development_problems,
    generate_metadata_for_episode,
)

TITLE = "Wisconsin Joins 38 States Fighting Character.AI Sale"          # 53 chars, ~500 px
DESC = ("A stolen login exposed years of California student records at ETS, while Wisconsin joins 38 states "
        "fighting the Character.AI bankruptcy sale.")


def good_audit(dev_fields=(True, True, True)):
    return {
        "stories": ["ETS breach new details", "Character.AI states", "School networks down"],
        "order": {"captivate_title": [1], "captivate_notes": [1, 2, 3], "aioseo_title": [1], "aioseo_description": [1, 2],
                  "website_excerpt": [1, 2], "youtube_title": [1], "youtube_description": [1, 2]},
        "lead_development": "one stolen login let intruders copy years of California student records",
        "states_development": dict(zip(("captivate_title", "aioseo_title", "youtube_title"), dev_fields)),
    }


def meta(title="ETS Breach Traced to One Stolen Login"):
    return {
        "captivate_title": title, "captivate_notes": "n", "aioseo_title": "ETS Breach Traced to a Single Stolen Login; 38 States Sue",
        "aioseo_description": DESC, "website_excerpt": "e", "youtube_title": title,
        "youtube_description": "yd", "youtube_tags": ["t"],
    }


def route(metas, audits):
    log = {"meta": [], "audit": []}

    def fake(system, user_content, tools, response_schema):
        if response_schema is AUDIT_SCHEMA:
            log["audit"].append(user_content)
            return json.dumps(audits[min(len(log["audit"]), len(audits)) - 1])
        log["meta"].append(user_content)
        return json.dumps(metas[min(len(log["meta"]), len(metas)) - 1])

    return fake, log


class PromptTests(unittest.TestCase):
    def test_the_prompt_demands_the_new_development_and_rejects_bare_topic_labels(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("HEADLINES REPORT THE NEWS, NOT THE TOPIC", prompt)
        self.assertIn("is NOT a headline", prompt)
        self.assertIn("could have run unchanged weeks ago", prompt)
        self.assertIn("ONE story well", prompt)                           # the full length may tell one complex story

    def test_descriptions_and_excerpts_open_with_what_is_new(self):
        prompt = build_system_prompt("Net Gain Edtech")
        self.assertIn("Open with what happened in story 1 today", prompt)
        self.assertIn("Open with what is new in story 1 today", prompt)

    def test_the_audit_is_asked_what_is_new_and_whether_each_title_says_it(self):
        audit_prompt = build_audit_system_prompt()
        self.assertIn("lead_development", audit_prompt)
        self.assertIn("states_development", audit_prompt)
        self.assertIn("could have run unchanged weeks ago", audit_prompt)

    def test_recent_headlines_reach_the_model_as_context_only_when_given(self):
        with_recent = build_user_message("2026-10-19", "script", ["OpenAI Sued by 8 States", "ETS Hacked"])
        self.assertIn("Headlines already published in the last two weeks", with_recent)
        self.assertIn("- OpenAI Sued by 8 States", with_recent)
        self.assertLess(with_recent.index("Headlines already published"), with_recent.index("Final script:"))
        self.assertNotIn("Headlines already published", build_user_message("2026-10-19", "script"))
        self.assertNotIn("Headlines already published", build_user_message("2026-10-19", "script", []))


class DevelopmentCheckTests(unittest.TestCase):
    def test_only_an_explicit_false_counts_as_a_topic_only_title(self):
        self.assertEqual(find_development_problems(good_audit((True, False, True))), ["aioseo_title"])
        self.assertEqual(find_development_problems(good_audit((False, False, False))),
                         ["captivate_title", "aioseo_title", "youtube_title"])
        self.assertEqual(find_development_problems(good_audit()), [])

    def test_an_audit_with_no_answer_never_blocks_a_publish(self):
        self.assertEqual(find_development_problems({"stories": [], "order": {}}), [])


class LoopTests(unittest.TestCase):
    def _run(self, metas, audits, recent=None):
        fake, log = route(metas, audits)
        result = generate_metadata_for_episode(fake, "Net Gain Edtech", "2026-10-19", "script", recent_titles=recent)
        return log, result

    def test_a_topic_only_headline_is_regenerated_with_the_new_development_spelled_out(self):
        bad, good = meta("ETS Student Data Breach"), meta()
        log, result = self._run([bad, good], [good_audit((False, True, True)), good_audit()])
        self.assertEqual(len(log["meta"]), 2)
        self.assertNotIn("NAMED THE TOPIC BUT NOT THE NEWS", log["meta"][0])
        feedback = log["meta"][1]
        self.assertIn("NAMED THE TOPIC BUT NOT THE NEWS", feedback)
        self.assertIn("captivate_title", feedback)
        self.assertIn("one stolen login let intruders copy years of California student records", feedback)
        self.assertEqual(result["captivate_title"], "ETS Breach Traced to One Stolen Login")

    def test_recent_headlines_are_sent_with_every_attempt(self):
        log, _ = self._run([meta("ETS Student Data Breach"), meta()], [good_audit((False, False, False)), good_audit()],
                           recent=["Tribal Group Bidding War"])
        self.assertTrue(all("Tribal Group Bidding War" in m for m in log["meta"]))

    def test_when_every_attempt_is_topic_only_the_best_one_is_used_and_nothing_raises(self):
        worse = meta("A Label")
        better = meta("Another Label")
        audits = [good_audit((False, False, False)), good_audit((False, True, True))]
        log, result = self._run([worse, better], audits)
        self.assertEqual(len(log["meta"]), MAX_METADATA_ATTEMPTS)
        self.assertEqual(result["captivate_title"], "Another Label")      # the attempt with fewer topic-only titles

    def test_a_clean_first_attempt_costs_exactly_one_generation_and_one_audit(self):
        log, result = self._run([meta()], [good_audit()])
        self.assertEqual((len(log["meta"]), len(log["audit"])), (1, 1))
        self.assertEqual(result["youtube_title"], "ETS Breach Traced to One Stolen Login")


if __name__ == "__main__":
    unittest.main()
