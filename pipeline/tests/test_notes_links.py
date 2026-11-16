"""The show notes' "Stories & links" block is rebuilt from the script's link lines, not trusted to the model
(2026-11-16: the model's last attempt stopped at `<p>1. ` and the episode's notes had no links)."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import metadata_generation as mg

DASH = "—"
SCRIPT = (
    "Spoken text.\n\n"
    f'1. "Cyber Incident Shuts Down Ohio\'s Perry Local Schools" {DASH} https://www.cleveland19.com/a/\n'
    f'2. "UK Conservatives Pledge Cuts" {DASH} https://schoolsweek.co.uk/b/\n'
    f'3. "Lawmaker Warns FCC" {DASH} https://www.law360.com/c\n'
)
HEADER = "<p><strong>Stories &amp; links:</strong></p>"


class ScriptLinks(unittest.TestCase):
    def test_numbered_lines_are_read_in_order(self):
        self.assertEqual([u for _, u in mg.script_links(SCRIPT)], ["https://www.cleveland19.com/a/", "https://schoolsweek.co.uk/b/", "https://www.law360.com/c"])
        self.assertEqual(mg.script_links(SCRIPT)[0][0], "Cyber Incident Shuts Down Ohio's Perry Local Schools")

    def test_a_line_with_two_addresses_gives_each_its_own_entry(self):
        links = mg.script_links(f'1. "Title, with comma" {DASH} https://a.test/1 and https://b.test/2')
        self.assertEqual(links, [("Title, with comma", "https://a.test/1"), ("Title, with comma", "https://b.test/2")])

    def test_prose_after_the_address_and_spoken_lines_are_not_links(self):
        self.assertEqual(mg.script_links(f"1. Title {DASH} https://a.test/1 is a great read\n2. Make sure to follow the show."), [])

    def test_curly_quotes_are_stripped_from_captions(self):
        self.assertEqual(mg.script_links(f"1. “Curly” {DASH} https://a.test/1")[0][0], "Curly")


class EnsureNotesLinks(unittest.TestCase):
    def test_a_block_cut_off_after_the_header_is_completed(self):
        notes, changed = mg.ensure_notes_links("<p>Story.</p>" + HEADER + "<p>1. ", SCRIPT)
        self.assertTrue(changed)
        self.assertTrue(notes.startswith("<p>Story.</p>" + HEADER))
        self.assertEqual(notes.count("<a href="), 3)
        self.assertIn('<a href="https://www.law360.com/c" rel="nofollow">https://www.law360.com/c</a>', notes)

    def test_a_block_listed_twice_becomes_one(self):
        doubled = "<p>Story.</p>" + HEADER + "<p>1. x</p><p>2. y</p>" + HEADER + "<p>1. x</p>"
        notes, _ = mg.ensure_notes_links(doubled, SCRIPT)
        self.assertEqual(notes.count("Stories &amp; links"), 1)
        self.assertEqual(notes.count("<a href="), 3)

    def test_notes_with_no_block_get_one(self):
        notes, changed = mg.ensure_notes_links("<p>Story.</p>", SCRIPT)
        self.assertTrue(changed)
        self.assertIn(HEADER + '<p>1. "Cyber Incident', notes)

    def test_a_correct_block_is_left_as_it_is(self):
        notes, _ = mg.ensure_notes_links("<p>Story.</p>", SCRIPT)
        again, changed = mg.ensure_notes_links(notes, SCRIPT)
        self.assertFalse(changed)
        self.assertEqual(again, notes)

    def test_a_script_without_links_changes_nothing(self):
        self.assertEqual(mg.ensure_notes_links("<p>Story.</p>", "Only spoken text."), ("<p>Story.</p>", False))
        self.assertEqual(mg.ensure_notes_links(None, SCRIPT), (None, False))

    def test_special_characters_are_escaped(self):
        script = f'1. "A & B <i>" {DASH} https://a.test/?x=1&y=2'
        notes, _ = mg.ensure_notes_links("<p>S.</p>", script)
        self.assertIn("A &amp; B &lt;i&gt;", notes)
        self.assertIn('href="https://a.test/?x=1&amp;y=2"', notes)


class GenerationUsesIt(unittest.TestCase):
    def test_the_model_s_truncated_block_never_reaches_the_stored_notes(self):
        fields = {
            "captivate_title": "C", "captivate_notes": "<p>Story.</p>" + HEADER + "<p>1. ", "aioseo_title": "A",
            "aioseo_description": "D", "website_excerpt": "E", "youtube_title": "Y", "youtube_description": "YD", "youtube_tags": ["t"],
        }
        with mock.patch.object(mg, "audit_story_order", return_value={}), mock.patch.object(mg, "find_order_violations", return_value=[]), \
                mock.patch.object(mg, "find_development_problems", return_value=[]), mock.patch.object(mg, "overlong_titles", return_value={}), \
                mock.patch.object(mg, "search_field_problems", return_value={}):
            result = mg.generate_metadata_for_episode(lambda **kw: json.dumps(fields), "Show", "2026-11-16", SCRIPT)
        self.assertEqual(result["captivate_notes"].count("<a href="), 3)


if __name__ == "__main__":
    unittest.main()
