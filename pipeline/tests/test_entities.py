import json
import unittest

import entities

SCRIPT = (
    "Good afternoon. Frontline Education confirmed more breach notices today.\n\n"
    "In Texas, the state board met.\n\n"
    "Show notes - story names and links:\n\n"
    "1. Texas board opens final session of outgoing majority — https://www.example.org/a\n"
    "2. Caption that names a person — https://www.example.org/b\n"
)


class SlugTests(unittest.TestCase):
    def test_slug_folds_case_accents_and_nonbreaking_hyphen(self):
        self.assertEqual(entities.slugify("K‑12 AI policy"), "k-12-ai-policy")
        self.assertEqual(entities.slugify("Montréal Schools & Boards"), "montreal-schools-and-boards")
        self.assertEqual(entities.slugify("  "), "")


class SpokenScriptTests(unittest.TestCase):
    def test_link_lines_and_their_heading_are_removed(self):
        body = entities.spoken_script(SCRIPT)
        self.assertIn("Frontline Education", body)
        self.assertIn("the state board met", body)
        self.assertNotIn("Caption that names a person", body)
        self.assertNotIn("Show notes", body)
        self.assertNotIn("example.org", body)

    def test_script_without_links_is_kept_whole(self):
        self.assertEqual(entities.spoken_script("Just narration."), "Just narration.")


class CleanTests(unittest.TestCase):
    def test_known_spelling_wins_and_bad_items_are_dropped(self):
        raw = {"entities": [
            {"name": "frontline education", "kind": "company", "note": "Sent notices."},
            {"name": "Frontline Education", "kind": "company", "note": "duplicate"},
            {"name": "Texas", "kind": "person", "note": "bad kind"},
            {"name": "", "kind": "place", "note": "no name"},
            {"name": "Ransomware attacks on schools", "kind": "topic", "note": "See https://x.example/a"},
        ]}
        out = entities.clean_entities(raw, ["Frontline Education"])
        self.assertEqual([e["name"] for e in out], ["Frontline Education", "Ransomware attacks on schools"])
        self.assertEqual(out[0]["slug"], "frontline-education")
        self.assertEqual(out[1]["note"], "")       # a note with an address is discarded

    def test_long_note_is_shortened_and_list_capped(self):
        raw = {"entities": [{"name": f"Org {i}", "kind": "organization", "note": "word " * 100} for i in range(9)]}
        out = entities.clean_entities(raw)
        self.assertEqual(len(out), entities.MAX_ENTITIES)
        self.assertLessEqual(len(out[0]["note"]), entities.MAX_NOTE_CHARS)


class ExtractTests(unittest.TestCase):
    def test_model_sees_only_the_spoken_script_and_known_names(self):
        seen = {}

        def fake(**kw):
            seen.update(kw)
            return json.dumps({"entities": [{"name": "Frontline Education", "kind": "company", "note": "Sent notices."}]})

        out = entities.extract_entities(fake, "Net Gain Edtech", "2026-11-18", SCRIPT, ["Frontline Education"])
        self.assertEqual(out[0]["slug"], "frontline-education")
        self.assertNotIn("Caption that names a person", seen["user_content"])
        self.assertIn("- Frontline Education", seen["user_content"])
        self.assertEqual(seen["tools"], [])

    def test_empty_result_is_an_error(self):
        with self.assertRaises(ValueError):
            entities.extract_entities(lambda **kw: json.dumps({"entities": []}), "S", "d", SCRIPT)


class FakeWP:
    def __init__(self, meta, fail=False):
        self.meta, self.fail, self.updates = meta, fail, []

    def get_episode(self, _id):
        return {"id": _id, "meta": self.meta}

    def list_episodes_for_show(self, _show):
        return [{"id": 1, "meta": {"ng_entities": [{"name": "PowerSchool"}]}}]

    def update_episode_meta(self, _id, fields):
        if self.fail:
            raise RuntimeError("boom")
        self.updates.append(fields)


class EnsureTests(unittest.TestCase):
    GOOD = staticmethod(lambda **kw: json.dumps({"entities": [{"name": "PowerSchool", "kind": "company", "note": "n"}]}))

    def test_stores_tags_once(self):
        wp = FakeWP({"ng_script_final": SCRIPT, "ng_episode_date": "2026-11-18"})
        entities.ensure_entities(wp, self.GOOD, {"id": 9, "name": "S"}, 5)
        self.assertEqual(wp.updates[0]["ng_entities"][0]["name"], "PowerSchool")

    def test_existing_tags_are_kept_unless_forced(self):
        wp = FakeWP({"ng_script_final": SCRIPT, "ng_entities": [{"name": "X"}]})
        self.assertEqual(entities.ensure_entities(wp, self.GOOD, {"id": 9, "name": "S"}, 5), [{"name": "X"}])
        self.assertEqual(wp.updates, [])

    def test_failure_never_raises(self):
        wp = FakeWP({"ng_script_final": SCRIPT}, fail=True)
        self.assertIsNone(entities.ensure_entities(wp, self.GOOD, {"id": 9, "name": "S"}, 5))
        self.assertIsNone(entities.ensure_entities(FakeWP({"ng_script_final": SCRIPT}), lambda **kw: "not json", {"id": 9, "name": "S"}, 5))


if __name__ == "__main__":
    unittest.main()
