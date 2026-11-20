import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import entities
import gazetteer

# Sentences taken from real scripts (2026-10-15, 2026-11-18, 2026-11-19), the three cases the first audit found wrong.
NOV19 = (
    "Good afternoon. Boxlight's stock dilution and sell-off were cited as a factor in broader edtech market declines.\n\n"
    "Hackers have shut down phone lines at the Burnaby School District in British Columbia, Canada. The district of 29-thousand students has had network problems all week.\n\n"
    "And it's the final day of the OASBO ICT Winter Workshop in Richmond Hill, Ontario for Canadian K‑12 IT managers, CIOs, and school technology leaders.\n\n"
    "That's Net Gain Edtech for Thursday, November nineteenth.\n\n"
    "Show notes - story names and links:\n\n"
    "1. Caption that names a person — https://www.example.org/b\n"
)

OASBO_Q = "And it's the final day of the OASBO ICT Winter Workshop in Richmond Hill, Ontario for Canadian K-12 IT managers, CIOs, and school technology leaders."
BURNABY_Q = "Hackers have shut down phone lines at the Burnaby School District in British Columbia, Canada."


def tag(name, kind, quote, note="n", level="", parent=""):
    return {"name": name, "kind": kind, "level": level, "parent": parent, "quote": quote, "note": note}


def story(*tags):
    return {"summary": "s", "tags": list(tags)}


def fake_model(stories, decisions=None, fail_verify=False):
    def generate(**kw):
        if kw["response_schema"] is entities.VERIFY_SCHEMA:
            if fail_verify:
                raise RuntimeError("down")
            wanted = decisions or {}
            ids = [int(line.split(" | ")[0]) for line in kw["user_content"].splitlines()]
            names = {int(line.split(" | ")[0]): line.split(" | ")[1].split(" (")[0] for line in kw["user_content"].splitlines()}
            return json.dumps({"decisions": [{"id": i, "keep": wanted.get(names[i], False), "note": "Scheduled."} for i in ids]})
        return json.dumps({"stories": stories})
    return generate


class SlugAndScriptTests(unittest.TestCase):
    def test_slug_folds_case_accents_and_nonbreaking_hyphen(self):
        self.assertEqual(entities.slugify("K‑12 AI policy"), "k-12-ai-policy")
        self.assertEqual(entities.slugify("Montréal Schools & Boards"), "montreal-schools-and-boards")

    def test_link_lines_and_heading_are_removed(self):
        body = entities.spoken_script(NOV19)
        self.assertIn("OASBO", body)
        self.assertNotIn("Caption that names a person", body)
        self.assertNotIn("Show notes", body)

    def test_topic_names_match_their_slugs(self):
        self.assertEqual(entities.TOPIC_BY_SLUG["k-12-ai-policy"], "K‑12 AI policy")
        self.assertIn("edtech-mergers-and-acquisitions", entities.TOPIC_BY_SLUG)


class QuoteTests(unittest.TestCase):
    def test_exact_quote_even_with_curly_quotes_and_the_nonbreaking_hyphen(self):
        script_n = entities.norm(NOV19)
        self.assertTrue(entities.quote_in_script(OASBO_Q, script_n))
        self.assertTrue(entities.quote_in_script("Hackers have shut down phone lines ... in British Columbia, Canada.", script_n))

    def test_invented_or_short_quote_fails(self):
        script_n = entities.norm(NOV19)
        self.assertFalse(entities.quote_in_script("Acme will acquire Widgets Inc. for two billion dollars.", script_n))
        self.assertFalse(entities.quote_in_script("", script_n))
        self.assertFalse(entities.quote_in_script("Hackers", script_n))

    def test_an_inferred_province_does_not_need_to_be_in_the_quote(self):
        dropped = []
        tags = entities.flatten_and_verify({"stories": [story(tag("British Columbia", "place", "The district of 29-thousand students has had network problems all week.", level="region"),
                                                              tag("Atlantis", "place", "The district of 29-thousand students has had network problems all week.", level="region"))]},
                                           entities.spoken_script(NOV19), {}, dropped)
        self.assertEqual([t["name"] for t in tags], ["British Columbia"])          # a gazetteer place is inferred; an unknown one is checked
        self.assertEqual(dropped[0][0], "Atlantis")

    def test_known_short_forms_and_punctuated_names_are_recognised(self):
        self.assertTrue(entities.name_supported("U.S. Department of Education", "The Education Department said on Tuesday that it will pause the program."))
        self.assertTrue(entities.name_supported("Character.AI", "Character AI filed for bankruptcy protection last week."))

    def test_name_must_be_in_its_quote(self):
        self.assertTrue(entities.name_supported("Burnaby School District", BURNABY_Q))
        self.assertTrue(entities.name_supported("Federal Communications Commission", "The FCC proceeding closes today."))
        self.assertFalse(entities.name_supported("PowerSchool", BURNABY_Q))


class FlattenTests(unittest.TestCase):
    def run_flatten(self, stories, known=None):
        dropped = []
        tags = entities.flatten_and_verify({"stories": stories}, entities.spoken_script(NOV19), known, dropped)
        return tags, dropped

    def test_topic_without_a_supporting_sentence_is_dropped(self):
        tags, dropped = self.run_flatten([story(tag("Edtech mergers and acquisitions", "topic", "Boxlight agreed to be acquired by a private equity firm for ten dollars a share."))])
        self.assertEqual(tags, [])
        self.assertIn("its quote is not in the script", dropped[0][1])

    def test_topic_off_the_list_is_dropped(self):
        tags, dropped = self.run_flatten([story(tag("School bus safety", "topic", BURNABY_Q))])
        self.assertEqual(tags, [])
        self.assertIn("fixed list", dropped[0][1])

    def test_calendar_organization_is_kept(self):
        tags, _ = self.run_flatten([story(tag("OASBO", "organization", OASBO_Q, note="Its ICT Winter Workshop ends today in Richmond Hill, Ontario."))])
        self.assertEqual([t["name"] for t in tags], ["OASBO"])
        self.assertEqual(tags[0]["slug"], "oasbo")
        self.assertEqual(tags[0]["evidence"], OASBO_Q)

    def test_home_country_sponsor_and_the_show_itself_are_never_tags(self):
        tags, _ = self.run_flatten([story(tag("United States", "place", BURNABY_Q, level="country"), tag("Edsby", "company", BURNABY_Q),
                                          tag("Net Gain Edtech Index", "company", "That's Net Gain Edtech for Thursday, November nineteenth."))])
        self.assertEqual(tags, [])

    def test_known_spelling_is_restored_and_duplicates_merge(self):
        tags, _ = self.run_flatten([story(tag("burnaby school district", "place", BURNABY_Q, level="local", note="One.")),
                                    story(tag("Burnaby School District", "place", BURNABY_Q, level="local", note="Two."))],
                                   known={"Burnaby School District": "place"})
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["name"], "Burnaby School District")
        self.assertEqual(tags[0]["note"], "One. Two.")


class ChainTests(unittest.TestCase):
    def test_district_gets_its_province_and_country(self):
        tags = entities.flatten_and_verify({"stories": [story(tag("Burnaby School District", "place", BURNABY_Q, level="local", parent="British Columbia"))]}, entities.spoken_script(NOV19))
        tags = entities.apply_place_chain(tags)
        by = {t["slug"]: t for t in tags}
        self.assertEqual(by["burnaby-school-district"]["parent"], "british-columbia")
        self.assertEqual(by["british-columbia"]["parent"], "canada")
        self.assertEqual(by["british-columbia"]["level"], "region")
        self.assertEqual(by["canada"]["level"], "country")
        self.assertEqual(by["canada"]["parent"], "")

    def test_us_state_has_no_country_parent(self):
        tags = entities.apply_place_chain([entities._tag("Houston Independent School District", "place", "", "texas", "local", "q")])
        by = {t["slug"]: t for t in tags}
        self.assertIn("texas", by)
        self.assertEqual(by["texas"]["parent"], "")
        self.assertNotIn("united-states", by)

    def test_gazetteer_province_is_put_under_canada_even_if_the_model_forgot(self):
        tags = entities.apply_place_chain([entities._tag("Ontario", "place", "", "", "", "q")])
        self.assertEqual({t["slug"]: t["parent"] for t in tags}, {"ontario": "canada", "canada": ""})


class ScanTests(unittest.TestCase):
    def test_candidate_found_when_the_model_missed_it(self):
        script = entities.spoken_script(NOV19)
        cands = entities.gazetteer_candidates(script, [], {})
        names = {c["name"] for c in cands}
        self.assertIn("British Columbia", names)
        self.assertIn("Canada", names)
        self.assertIn("Ontario", names)
        self.assertIn("OASBO", names)

    def test_already_tagged_names_are_not_candidates(self):
        script = entities.spoken_script(NOV19)
        have = [entities._tag("British Columbia", "place")]
        self.assertNotIn("British Columbia", {c["name"] for c in entities.gazetteer_candidates(script, have, {})})

    def test_ambiguous_names_need_the_verifier(self):
        script = "The New York Times reported that Washington lawmakers met in Georgia."
        names = {c["name"] for c in entities.gazetteer_candidates(script, [], {})}
        self.assertTrue({"New York", "Washington", "Georgia"} <= names)


class ExtractTests(unittest.TestCase):
    def test_the_three_reported_misses_are_fixed(self):
        model = [story(
            tag("Edtech mergers and acquisitions", "topic", "Boxlight agreed to be acquired by a private equity firm."),   # invented: dropped
            tag("Burnaby School District", "place", BURNABY_Q, level="local", parent="British Columbia"),
        )]
        out = entities.extract_entities(fake_model(model, {"OASBO": True, "Ontario": True, "British Columbia": True, "Canada": True}),
                                        "Net Gain Edtech", "2026-11-19", NOV19, {})
        names = {t["name"] for t in out}
        self.assertNotIn("Edtech mergers and acquisitions", names)
        self.assertTrue({"Burnaby School District", "British Columbia", "Canada", "OASBO"} <= names)
        self.assertNotIn("United States", names)
        self.assertEqual({t["slug"]: t["parent"] for t in out}["british-columbia"], "canada")

    def test_verifier_can_reject_a_candidate(self):
        out = entities.extract_entities(fake_model([story(tag("Burnaby School District", "place", BURNABY_Q, level="local", parent="British Columbia"))], {}),
                                        "S", "d", NOV19, {})
        self.assertNotIn("OASBO", {t["name"] for t in out})

    def test_scan_failure_keeps_the_models_tags(self):
        out = entities.extract_entities(fake_model([story(tag("Burnaby School District", "place", BURNABY_Q, level="local"))], fail_verify=True), "S", "d", NOV19, {})
        self.assertIn("Burnaby School District", {t["name"] for t in out})

    def test_report_lists_drops_and_scan_additions(self):
        report = {}
        entities.extract_entities(fake_model([story(tag("PowerSchool", "company", "PowerSchool settled the lawsuit with the state attorney general.")),
                                              story(tag("Burnaby School District", "place", BURNABY_Q, level="local"))], {"OASBO": True}),
                                  "S", "d", NOV19, {}, report=report)
        self.assertEqual(report["dropped"][0][0], "PowerSchool")
        self.assertIn("OASBO", report["scanned"])

    def test_cap_keeps_topics_and_companies_first(self):
        many = [tag(f"Place {i}", "place", BURNABY_Q.replace("Burnaby", f"Burnaby"), level="local") for i in range(45)]
        many = [dict(t, name=f"Burnaby Place {i}") for i, t in enumerate(many)]
        many.append(tag("K-12 AI policy", "topic", OASBO_Q))
        out = entities.extract_entities(fake_model([story(*many)]), "S", "d", NOV19, {})
        self.assertEqual(len(out), entities.MAX_ENTITIES)
        self.assertEqual(out[0]["kind"], "topic")

    def test_empty_result_is_an_error(self):
        with self.assertRaises(ValueError):
            entities.extract_entities(fake_model([]), "S", "d", "Just a short script with nothing named in it at all.", {})


class FakeWP:
    def __init__(self, meta, fail=False):
        self.meta, self.fail, self.updates = meta, fail, []

    def get_episode(self, _id):
        return {"id": _id, "meta": self.meta}

    def list_episodes_for_show(self, _show):
        return [{"id": 1, "meta": {"ng_entities": [{"name": "Burnaby School District", "kind": "place"}]}}]

    def update_episode_meta(self, _id, fields):
        if self.fail:
            raise RuntimeError("boom")
        self.updates.append(fields)


class EnsureTests(unittest.TestCase):
    GOOD = staticmethod(fake_model([story(tag("Burnaby School District", "place", BURNABY_Q, level="local"))], {}))

    def test_stores_tags_once(self):
        wp = FakeWP({"ng_script_final": NOV19, "ng_episode_date": "2026-11-19"})
        entities.ensure_entities(wp, self.GOOD, {"id": 9, "name": "S"}, 5)
        self.assertEqual(wp.updates[0]["ng_entities"][0]["kind"], "place")

    def test_existing_tags_are_kept_unless_forced(self):
        wp = FakeWP({"ng_script_final": NOV19, "ng_entities": [{"name": "X"}]})
        self.assertEqual(entities.ensure_entities(wp, self.GOOD, {"id": 9, "name": "S"}, 5), [{"name": "X"}])
        self.assertEqual(wp.updates, [])

    def test_failure_never_raises(self):
        self.assertIsNone(entities.ensure_entities(FakeWP({"ng_script_final": NOV19}, fail=True), self.GOOD, {"id": 9, "name": "S"}, 5))
        self.assertIsNone(entities.ensure_entities(FakeWP({"ng_script_final": NOV19}), lambda **kw: "not json", {"id": 9, "name": "S"}, 5))


if __name__ == "__main__":
    unittest.main()
