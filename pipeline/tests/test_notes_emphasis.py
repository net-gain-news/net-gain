"""Show notes may emphasise only the 'Stories & links:' header (2026-10-23: a district name came back bolded)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import metadata_generation as mg

HEADER = "<p><strong>Stories &amp; links:</strong></p>"


class StripEmphasis(unittest.TestCase):
    def test_a_bolded_name_in_a_story_paragraph_is_unbolded(self):
        notes = "<p><strong>Oneonta City School District</strong> in New York closed schools.</p>" + HEADER
        cleaned, changed = mg.strip_stray_emphasis(notes)
        self.assertTrue(changed)
        self.assertEqual(cleaned, "<p>Oneonta City School District in New York closed schools.</p>" + HEADER)

    def test_the_header_survives_untouched(self):
        notes = "<p>Story.</p>" + HEADER + '<p>"T" — <a href="https://x.example/a" rel="nofollow">https://x.example/a</a></p>'
        self.assertEqual(mg.strip_stray_emphasis(notes), (notes, False))

    def test_every_kind_of_emphasis_goes_but_links_and_text_stay(self):
        notes = '<p><b>A</b> <i>B</i> <em>C</em> <u>D</u> <a href="https://x.example/" rel="nofollow">E</a></p>'
        cleaned, changed = mg.strip_stray_emphasis(notes)
        self.assertTrue(changed)
        self.assertEqual(cleaned, '<p>A B C D <a href="https://x.example/" rel="nofollow">E</a></p>')

    def test_an_unescaped_ampersand_header_variant_is_still_protected(self):
        header = "<p><strong>Stories & links:</strong></p>"
        notes = "<p><strong>X</strong> story.</p>" + header
        cleaned, _ = mg.strip_stray_emphasis(notes)
        self.assertTrue(cleaned.endswith(header))
        self.assertNotIn("<strong>X", cleaned)

    def test_running_it_twice_changes_nothing_more(self):
        once, _ = mg.strip_stray_emphasis("<p><strong>A</strong></p>" + HEADER)
        self.assertEqual(mg.strip_stray_emphasis(once), (once, False))

    def test_empty_and_missing_notes_pass_through(self):
        self.assertEqual(mg.strip_stray_emphasis(""), ("", False))
        self.assertEqual(mg.strip_stray_emphasis(None), (None, False))


class Wiring(unittest.TestCase):
    def test_finalize_cleans_the_notes(self):
        result = mg._finalize({"captivate_notes": "<p><strong>Name</strong> did it.</p>" + HEADER, "youtube_tags": []})
        self.assertEqual(result["captivate_notes"], "<p>Name did it.</p>" + HEADER)

    def test_the_prompt_forbids_emphasis_in_story_paragraphs(self):
        prompt = mg.build_system_prompt("Net Gain Edtech")
        self.assertIn("NO bold, italics", prompt)


if __name__ == "__main__":
    unittest.main()
