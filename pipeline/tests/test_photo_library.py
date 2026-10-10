import json
import os
import random
import sys
import unittest
from datetime import date
from io import BytesIO

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import photo_library as pl


def photo(id_, **kw):
    base = {"id": id_, "status": "ready", "eligible": True, "tags": [], "topics": ["general"], "people": "none",
            "flags": [], "use_count": 0, "last_used": ""}
    base.update(kw)
    return base


class SelectionTests(unittest.TestCase):
    BRIEF = {"topics": ["security"], "settings": ["laptop", "lock"], "sensitive": False}

    def test_prefers_a_photo_that_suits_the_story(self):
        photos = [photo(1, topics=["k12"], tags=["classroom"]), photo(2, topics=["security"], tags=["laptop", "lock"])]
        chosen, relaxed = pl.select_photo(photos, self.BRIEF, "2026-10-09")
        self.assertEqual((chosen["id"], relaxed), (2, False))

    def test_resting_photos_are_skipped_while_any_eligible_photo_exists(self):
        photos = [photo(1, eligible=False, topics=["security"], tags=["laptop", "lock"]), photo(2, topics=["k12"])]
        self.assertEqual(pl.select_photo(photos, self.BRIEF, "2026-10-09")[0]["id"], 2)

    def test_when_everything_is_resting_the_least_recently_used_is_reused_and_flagged(self):
        photos = [photo(1, eligible=False, last_used="2026-09-20"), photo(2, eligible=False, last_used="2026-08-01"),
                  photo(3, eligible=False, last_used="2026-09-01")]
        chosen, relaxed = pl.select_photo(photos, {"topics": ["general"], "settings": [], "sensitive": False}, "2026-10-09")
        self.assertTrue(relaxed)
        self.assertEqual(chosen["id"], 2)

    def test_sensitive_stories_never_get_identifiable_people(self):
        brief = dict(self.BRIEF, sensitive=True)
        photos = [photo(1, people="identifiable", topics=["security"], tags=["laptop", "lock"]), photo(2, people="anonymous")]
        self.assertEqual(pl.select_photo(photos, brief, "2026-10-09")[0]["id"], 2)
        only_faces = [photo(1, people="identifiable")]
        self.assertEqual(pl.select_photo(only_faces, brief, "2026-10-09"), (None, False))

    def test_sensitive_rule_applies_even_when_relaxing_the_cooldown(self):
        brief = dict(self.BRIEF, sensitive=True)
        photos = [photo(1, eligible=False, people="identifiable", last_used="2026-01-01"), photo(2, eligible=False, people="none", last_used="2026-09-30")]
        chosen, relaxed = pl.select_photo(photos, brief, "2026-10-09")
        self.assertEqual((chosen["id"], relaxed), (2, True))

    def test_retired_and_untagged_photos_are_never_chosen(self):
        photos = [photo(1, status="retired"), photo(2, status="pending_tags")]
        self.assertEqual(pl.select_photo(photos, self.BRIEF, "2026-10-09"), (None, False))

    def test_the_choice_is_repeatable_for_the_same_day_and_varies_across_days(self):
        photos = [photo(i) for i in range(1, 30)]
        brief = {"topics": ["general"], "settings": [], "sensitive": False}
        a = pl.select_photo(photos, brief, "2026-10-09")[0]["id"]
        self.assertEqual(a, pl.select_photo(photos, brief, "2026-10-09")[0]["id"])
        days = {pl.select_photo(photos, brief, f"2026-10-{d:02d}")[0]["id"] for d in range(1, 29)}
        self.assertGreater(len(days), 5)

    def test_low_resolution_and_logo_photos_rank_lower(self):
        photos = [photo(1, flags=["low_res", "logo_text"]), photo(2)]
        self.assertEqual(pl.select_photo(photos, {"topics": ["general"], "settings": [], "sensitive": False}, "2026-10-09")[0]["id"], 2)


class CropTests(unittest.TestCase):
    WINDOWS = [(1280, 576), (1200, 502), (3000, 2600)]
    IMAGES = [(4000, 2667), (2667, 4000), (3000, 3000), (6000, 2000), (1500, 1000)]

    def test_variants_are_repeatable_and_change_with_each_use(self):
        self.assertEqual(pl.choose_variant(7, 0), pl.choose_variant(7, 0))
        seen = {json.dumps(pl.choose_variant(7, n), sort_keys=True) for n in range(40)}
        self.assertGreater(len(seen), 5)

    def test_the_crop_always_fits_the_image_matches_the_window_shape_and_keeps_the_focal_point(self):
        rng = random.Random(1)
        for img_w, img_h in self.IMAGES:
            for win_w, win_h in self.WINDOWS:
                for _ in range(120):
                    focal = (rng.random(), rng.random())
                    variant = {"zoom": rng.choice(pl.ZOOMS), "strategy": rng.choice(pl.STRATEGIES)}
                    left, top, right, bottom = pl.crop_box(img_w, img_h, focal, variant, win_w, win_h)
                    self.assertGreaterEqual(left, -1e-6)
                    self.assertGreaterEqual(top, -1e-6)
                    self.assertLessEqual(right, img_w + 1e-6)
                    self.assertLessEqual(bottom, img_h + 1e-6)
                    self.assertAlmostEqual((right - left) / (bottom - top), win_w / win_h, places=3)
                    self.assertTrue(left - 1e-6 <= focal[0] * img_w <= right + 1e-6, (img_w, img_h, win_w, focal, variant))
                    self.assertTrue(top - 1e-6 <= focal[1] * img_h <= bottom + 1e-6, (img_h, win_h, focal, variant))

    def test_higher_zoom_is_a_tighter_crop(self):
        wide = pl.crop_box(4000, 2667, (0.5, 0.5), {"zoom": 1.0, "strategy": "center"}, 1280, 576)
        tight = pl.crop_box(4000, 2667, (0.5, 0.5), {"zoom": 1.8, "strategy": "center"}, 1280, 576)
        self.assertLess(tight[2] - tight[0], (wide[2] - wide[0]) * 0.6)

    def test_strategies_put_the_subject_in_different_places(self):
        crops = {s: pl.crop_box(4000, 2667, (0.5, 0.5), {"zoom": 1.5, "strategy": s}, 1280, 576) for s in pl.STRATEGIES}
        self.assertEqual(len({round(c[0]) for c in crops.values()}), 3)


class FakeGenerate:
    def __init__(self, response):
        self.response, self.calls = response, []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(self.response) if not isinstance(self.response, str) else self.response


def jpeg_bytes(size=(1600, 1000), color=(120, 140, 160)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


class TaggingTests(unittest.TestCase):
    GOOD = {"is_photograph": True, "tags": ["Classroom", "laptop"], "topics": ["k12"], "people": "anonymous", "focal_x": 0.4,
            "focal_y": 0.6, "description": "A classroom.", "logo_or_text_visible": False}

    def test_sends_the_image_and_returns_ready_to_store_fields(self):
        gen = FakeGenerate(self.GOOD)
        fields = pl.tag_photo(gen, jpeg_bytes((3200, 2400)))
        content = gen.calls[0]["user_content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["media_type"], "image/jpeg")
        self.assertEqual(fields["tags"], ["classroom", "laptop"])
        self.assertEqual((fields["people"], fields["status"], fields["width"], fields["height"]), ("anonymous", "ready", 3200, 2400))
        self.assertNotIn("low_res", fields["flags"])    # short side 2400 is above the 2200 threshold
        self.assertEqual(fields["focal_x"], 0.4)

    def test_flags_low_resolution_portrait_and_logos(self):
        fields = pl.tag_photo(FakeGenerate(dict(self.GOOD, logo_or_text_visible=True)), jpeg_bytes((1200, 1800)))
        self.assertEqual(set(fields["flags"]), {"low_res", "portrait", "logo_text"})

    def test_a_non_photograph_is_retired_for_review(self):
        fields = pl.tag_photo(FakeGenerate(dict(self.GOOD, is_photograph=False)), jpeg_bytes())
        self.assertEqual(fields["status"], "retired")
        self.assertIn("needs_review", fields["flags"])

    def test_an_unknown_people_value_is_treated_cautiously(self):
        fields = pl.tag_photo(FakeGenerate(dict(self.GOOD, people="unsure")), jpeg_bytes())
        self.assertEqual(fields["people"], "identifiable")

    def test_focal_point_is_clamped_and_unreadable_files_raise(self):
        fields = pl.tag_photo(FakeGenerate(dict(self.GOOD, focal_x=3, focal_y=-1)), jpeg_bytes())
        self.assertEqual((fields["focal_x"], fields["focal_y"]), (1.0, 0.0))
        with self.assertRaises(OSError):
            pl.tag_photo(FakeGenerate(self.GOOD), b"not an image")

    def test_exif_orientation_is_applied_to_the_reported_size(self):
        img = Image.new("RGB", (3000, 2000), (10, 20, 30))
        exif = img.getexif(); exif[0x0112] = 6        # rotated 90 degrees
        buf = BytesIO(); img.save(buf, format="JPEG", exif=exif)
        fields = pl.tag_photo(FakeGenerate(self.GOOD), buf.getvalue())
        self.assertEqual((fields["width"], fields["height"]), (2000, 3000))


class BriefAndEmailTests(unittest.TestCase):
    def test_brief_is_normalised_and_prompt_is_about_story_one(self):
        gen = FakeGenerate({"topics": ["security", "bogus"], "settings": ["laptop", "nonsense"], "sensitive": True})
        brief = pl.describe_story(gen, "Show", "2026-10-09", "script")
        self.assertEqual(brief, {"topics": ["security"], "settings": ["laptop"], "sensitive": True})
        self.assertIn("ONLY at story 1", gen.calls[0]["system"])

    def test_empty_topics_default_to_general(self):
        brief = pl.describe_story(FakeGenerate({"topics": [], "settings": [], "sensitive": False}), "S", "d", "x")
        self.assertEqual(brief["topics"], ["general"])

    def test_the_library_email_states_the_level_and_the_advice(self):
        stats = {"level": "low", "eligible_now": 14, "cooling_down": 30, "cooldown_days": 90, "never_used": 5, "eligible_no_faces": 2,
                 "retired": 1, "messages": ["Only 2 eligible photos without identifiable people."]}
        subject, body = pl.library_email("Net Gain Edtech", stats)
        self.assertIn("running low", subject)
        self.assertIn("14 ready to use now", body)
        self.assertIn("Only 2 eligible", body)
        self.assertIn("Photos", body)


if __name__ == "__main__":
    unittest.main()
