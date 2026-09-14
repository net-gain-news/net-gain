import os
import sys
import unittest
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

import youtube_checklist as yc


def _make_thumbnail(width=1280, height=720, fmt="JPEG", color="red"):
    image = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


class TitleTests(unittest.TestCase):
    def setUp(self):
        self.good_description = "A" * 300
        self.good_tags = ["coursera", "chegg", "edtech funding", "edtech", "online learning"]
        self.good_thumbnail = _make_thumbnail()

    def _evaluate_title(self, title, tags=None, show_name="Net Gain Edtech"):
        return yc.evaluate(title, self.good_description, tags or self.good_tags, self.good_thumbnail, show_name)

    def test_empty_title_fails(self):
        failures = self._evaluate_title("")
        self.assertTrue(any("empty" in f.lower() for f in failures))

    def test_title_over_hard_limit_fails(self):
        failures = self._evaluate_title("x" * 101, tags=["x" * 101])
        self.assertTrue(any("100-character" in f for f in failures))

    def test_title_without_any_keyword_fails(self):
        failures = self._evaluate_title("Completely Unrelated Words Here", tags=["coursera", "chegg"])
        self.assertTrue(any("keyword" in f.lower() for f in failures))

    def test_title_matching_a_tag_passes_keyword_check(self):
        failures = self._evaluate_title("Coursera announces a new partnership today")
        self.assertEqual(failures, [])

    def test_title_matching_show_name_word_passes_keyword_check(self):
        failures = self._evaluate_title("Edtech headlines for today", tags=["zzz", "yyy", "www", "vvv", "uuu"])
        self.assertEqual(failures, [])

    def test_stopword_only_match_does_not_count(self):
        failures = self._evaluate_title("The Daily Show Update", tags=["zzz", "yyy", "www", "vvv", "uuu"], show_name="The Daily Show")
        self.assertTrue(any("keyword" in f.lower() for f in failures))


class DescriptionTests(unittest.TestCase):
    def setUp(self):
        self.good_title = "Edtech Funding Roundup"
        self.good_tags = ["edtech", "funding", "coursera", "chegg", "online learning"]
        self.good_thumbnail = _make_thumbnail()

    def test_too_short_fails(self):
        failures = yc.evaluate(self.good_title, "short", self.good_tags, self.good_thumbnail, "Net Gain Edtech")
        self.assertTrue(any("too short" in f.lower() for f in failures))

    def test_too_long_fails(self):
        failures = yc.evaluate(self.good_title, "A" * 5001, self.good_tags, self.good_thumbnail, "Net Gain Edtech")
        self.assertTrue(any("5000-character" in f for f in failures))

    def test_empty_preview_window_fails(self):
        # Non-empty overall, but the first 125 chars are all whitespace.
        description = (" " * 125) + ("A" * 200)
        failures = yc.evaluate(self.good_title, description, self.good_tags, self.good_thumbnail, "Net Gain Edtech")
        self.assertTrue(any("125" in f for f in failures))

    def test_reasonable_description_passes(self):
        failures = yc.evaluate(self.good_title, "A" * 300, self.good_tags, self.good_thumbnail, "Net Gain Edtech")
        self.assertEqual(failures, [])


class TagTests(unittest.TestCase):
    def setUp(self):
        self.good_title = "Edtech Funding Roundup"
        self.good_description = "A" * 300
        self.good_thumbnail = _make_thumbnail()

    def _evaluate_tags(self, tags):
        return yc.evaluate(self.good_title, self.good_description, tags, self.good_thumbnail, "Net Gain Edtech")

    def test_too_few_tags_fails(self):
        failures = self._evaluate_tags(["edtech"])
        self.assertTrue(any("expected between" in f for f in failures))

    def test_too_many_tags_fails(self):
        failures = self._evaluate_tags([f"tag{i}" for i in range(16)])
        self.assertTrue(any("expected between" in f for f in failures))

    def test_hashtag_style_tag_fails(self):
        failures = self._evaluate_tags(["edtech", "funding", "coursera", "chegg", "#hashtag"])
        self.assertTrue(any("#" in f for f in failures))

    def test_combined_tag_length_over_limit_fails(self):
        long_tags = ["x" * 100 for _ in range(6)]
        failures = self._evaluate_tags(long_tags)
        self.assertTrue(any("aggregate limit" in f for f in failures))

    def test_reasonable_tags_pass(self):
        failures = self._evaluate_tags(["edtech", "funding", "coursera", "chegg", "online learning"])
        self.assertEqual(failures, [])


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.good_title = "Edtech Funding Roundup"
        self.good_description = "A" * 300
        self.good_tags = ["edtech", "funding", "coursera", "chegg", "online learning"]

    def _evaluate_thumbnail(self, thumbnail_bytes):
        return yc.evaluate(self.good_title, self.good_description, self.good_tags, thumbnail_bytes, "Net Gain Edtech")

    def test_missing_thumbnail_fails(self):
        failures = self._evaluate_thumbnail(b"")
        self.assertTrue(any("no thumbnail" in f.lower() for f in failures))

    def test_unreadable_bytes_fail(self):
        failures = self._evaluate_thumbnail(b"not an image at all")
        self.assertTrue(any("could not be read" in f.lower() for f in failures))

    def test_too_small_fails(self):
        failures = self._evaluate_thumbnail(_make_thumbnail(width=640, height=360))
        self.assertTrue(any("smaller than" in f for f in failures))

    def test_wrong_aspect_ratio_fails(self):
        failures = self._evaluate_thumbnail(_make_thumbnail(width=1280, height=1280))
        self.assertTrue(any("aspect ratio" in f.lower() for f in failures))

    def test_wrong_format_fails(self):
        failures = self._evaluate_thumbnail(_make_thumbnail(fmt="BMP"))
        self.assertTrue(any("format" in f.lower() for f in failures))

    def test_oversized_bytes_fail(self):
        # A real 1280x720 JPEG well under the cap, padded with a trailing
        # comment-like blob to push it over 2MB without corrupting the
        # leading JPEG data Pillow actually parses.
        base = _make_thumbnail()
        oversized = base + (b"\x00" * (yc.THUMBNAIL_MAX_BYTES + 1 - len(base)))
        failures = self._evaluate_thumbnail(oversized)
        self.assertTrue(any("byte limit" in f for f in failures))

    def test_good_thumbnail_passes(self):
        failures = self._evaluate_thumbnail(_make_thumbnail())
        self.assertEqual(failures, [])


class FullPassTests(unittest.TestCase):
    def test_everything_good_returns_no_failures(self):
        failures = yc.evaluate(
            title="Coursera Announces New AI Tutor Partnership",
            description="A" * 300,
            tags=["coursera", "edtech", "ai tutor", "online learning", "funding"],
            thumbnail_bytes=_make_thumbnail(),
            show_name="Net Gain Edtech",
        )
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
