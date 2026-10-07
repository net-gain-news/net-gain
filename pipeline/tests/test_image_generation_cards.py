import json
import os
import sys
import unittest
from io import BytesIO

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import image_generation
from image_generation import card_index_from_snapshot, render_images_for_episode

GOOD = {"headline": "South Carolina school-choice payments hit by another cyberattack",
        "words": [{"story": 1, "word": "Cyberattack"}, {"story": 2, "word": "AI detectors"}, {"story": 3, "word": "Acquisition"}]}
STORIES = ["a", "b", "c"]


def frame_png(size, top, bottom):
    frame = Image.new("RGBA", size, (30, 38, 32, 255))
    frame.paste(Image.new("RGBA", (size[0], bottom - top), (0, 0, 0, 0)), (0, top))
    buf = BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()


FRAMES = {11: frame_png((3000, 3000), 0, 2600), 12: frame_png((1280, 720), 8, 584), 13: frame_png((1200, 630), 8, 510)}
SNAPSHOT = {
    "daily_change_percent": 0.23, "ytd_change_percent": -8.1,
    "constituents": [{"ticker": f"T{i}", "company": f"Co {i}", "day_change_percent": (i - 25) / 5} for i in range(50)],
}


class FakeWP:
    def __init__(self, episode_meta, show_meta):
        self.episode = {"meta": episode_meta}
        self.show = {"meta": show_meta}
        self.uploads, self.episode_updates, self.show_updates = [], [], []

    def get_episode(self, episode_id): return self.episode
    def get_show(self, show_id): return self.show
    def get_attachment_url(self, attachment_id): return f"url/{attachment_id}"
    def download_binary(self, url): return FRAMES[int(url.split("/")[1])]

    def upload_media(self, data, filename, mime):
        self.uploads.append((filename, mime, len(data)))
        return 100 + len(self.uploads)

    def update_episode_meta(self, episode_id, meta): self.episode_updates.append(meta)
    def update_show_meta(self, show_id, meta): self.show_updates.append(meta)


def show_meta(**extra):
    base = {"ng_image_mode": "cards", "ng_frame_square_id": 11, "ng_frame_16x9_id": 12, "ng_frame_1200x630_id": 13,
            "ng_index_snapshot": SNAPSHOT, "ng_index_last_refresh_date": "2026-10-06"}
    base.update(extra)
    return base


def generate(system, user_content, tools, response_schema):
    if response_schema is image_generation.generate_card_text.__globals__["AUDIT_SCHEMA"]:
        return json.dumps({"stories": STORIES, "headline_story": 1, "word_stories": [1, 2, 3]})
    return json.dumps(GOOD)


SHOW = {"id": 16, "name": "Net Gain Edtech", "slug": "edtech"}


class IndexTests(unittest.TestCase):
    def test_only_a_snapshot_refreshed_on_the_episode_date_counts(self):
        meta = {"ng_index_snapshot": SNAPSHOT, "ng_index_last_refresh_date": "2026-10-05"}
        self.assertIsNone(card_index_from_snapshot(meta, "2026-10-06"))
        meta["ng_index_last_refresh_date"] = "2026-10-06"
        ix = card_index_from_snapshot(meta, "2026-10-06")
        self.assertEqual(ix["pct"], 0.23)
        self.assertEqual(len(ix["moves"]), 50)
        self.assertEqual(ix["moves"][0], {"t": "T0", "co": "Co 0", "mv": -5.0})

    def test_no_snapshot_means_no_index(self):
        self.assertIsNone(card_index_from_snapshot({}, "2026-10-06"))
        self.assertIsNone(card_index_from_snapshot({"ng_index_snapshot": {"daily_change_percent": None}, "ng_index_last_refresh_date": "2026-10-06"}, "2026-10-06"))


class CardPathTests(unittest.TestCase):
    def render(self, wp):
        render_images_for_episode(wp, None, generate, SHOW, 7)

    def test_a_new_episode_gets_the_template_after_the_last_one_and_records_it(self):
        wp = FakeWP({"ng_episode_date": "2026-10-07", "ng_script_final": "s"}, show_meta(ng_card_last_template="D5", ng_index_last_refresh_date="2026-10-07"))
        self.render(wp)
        self.assertEqual(len(wp.uploads), 3)
        self.assertEqual(wp.episode_updates[-1]["ng_card_template"], "A")          # D5 wraps to A
        self.assertEqual(wp.show_updates, [{"ng_card_last_template": "A"}])
        self.assertEqual(sorted(m for _, m, _ in wp.uploads), ["image/jpeg", "image/jpeg", "image/webp"])
        self.assertEqual({f for f, _, _ in wp.uploads}, {"edtech-2026-10-07-square.jpg", "edtech-2026-10-07-16x9.jpg", "edtech-2026-10-07-1200x630.webp"})

    def test_a_re_render_keeps_the_episodes_own_card_and_does_not_advance_the_rotation(self):
        wp = FakeWP({"ng_episode_date": "2026-10-07", "ng_script_final": "s", "ng_card_template": "D8"},
                    show_meta(ng_card_last_template="D5", ng_index_last_refresh_date="2026-10-07"))
        self.render(wp)
        self.assertEqual(wp.episode_updates[-1]["ng_card_template"], "D8")
        self.assertEqual(wp.show_updates, [])

    def test_index_cards_are_skipped_when_the_index_is_not_from_that_day(self):
        wp = FakeWP({"ng_episode_date": "2026-10-07", "ng_script_final": "s"}, show_meta(ng_card_last_template="D6", ng_index_last_refresh_date="2026-10-06"))
        self.render(wp)
        self.assertEqual(wp.episode_updates[-1]["ng_card_template"], "E")          # C is unavailable; E is next

    def test_failed_card_text_falls_back_to_a_card_that_needs_no_text(self):
        def failing(system, user_content, tools, response_schema):
            raise RuntimeError("API down")
        wp = FakeWP({"ng_episode_date": "2026-10-07", "ng_script_final": "s"}, show_meta(ng_card_last_template="D5", ng_index_last_refresh_date="2026-10-07"))
        render_images_for_episode(wp, None, failing, SHOW, 7)
        self.assertIn(wp.episode_updates[-1]["ng_card_template"], {"D6", "C", "D8", "F", "D5"})

    def test_missing_frame_is_a_clear_error(self):
        wp = FakeWP({"ng_episode_date": "2026-10-07", "ng_script_final": "s"}, show_meta(ng_frame_square_id=0))
        with self.assertRaisesRegex(RuntimeError, "no square frame"):
            self.render(wp)

    def test_ai_mode_still_takes_the_original_path(self):
        wp = FakeWP({"ng_episode_date": "2026-10-07", "ng_script_final": "s"}, show_meta(ng_image_mode="ai"))
        calls = []
        original = image_generation.generate_image_prompt_for_episode
        image_generation.generate_image_prompt_for_episode = lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(RuntimeError("stop"))
        try:
            with self.assertRaises(RuntimeError):
                self.render(wp)
        finally:
            image_generation.generate_image_prompt_for_episode = original
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
