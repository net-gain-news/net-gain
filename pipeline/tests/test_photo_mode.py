import json
import os
import sys
import unittest
from datetime import date, datetime
from io import BytesIO
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import image_generation
import photo_library as pl
import photo_render
import tick
from image_compositing import visible_window

BAR = (30, 38, 32)
DENIM = ("#22293a", "#7193b8")


def frame_png(size, top, bottom):
    frame = Image.new("RGBA", size, BAR + (255,))
    frame.paste(Image.new("RGBA", (size[0], bottom - top), (0, 0, 0, 0)), (0, top))
    buf = BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()


FRAMES = {"16x9": frame_png((1280, 720), 8, 584), "1200x630": frame_png((1200, 630), 8, 510), "square": frame_png((3000, 3000), 0, 2600)}


def sample_photo(size=(4000, 2667)):
    """A busy synthetic 'photo': horizontal gradient plus shapes, so crops and duotone have something to act on."""
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for x in range(0, size[0], 8):
        v = int(255 * x / size[0])
        d.rectangle((x, 0, x + 8, size[1]), fill=(v, 255 - v, 128))
    d.ellipse((size[0] * 0.3, size[1] * 0.3, size[0] * 0.5, size[1] * 0.6), fill=(240, 240, 240))
    d.rectangle((size[0] * 0.6, size[1] * 0.5, size[0] * 0.9, size[1] * 0.95), fill=(20, 20, 20))
    return img


class RenderTests(unittest.TestCase):
    VARIANT = {"zoom": 1.25, "strategy": "center"}

    def test_three_finished_sizes_with_the_footer_painted_by_the_frame(self):
        out = photo_render.render_formats(sample_photo(), (0.4, 0.45), self.VARIANT, FRAMES, DENIM, None)
        self.assertEqual({k: v.size for k, v in out.items()}, {"16x9": (1280, 720), "1200x630": (1200, 630), "square": (3000, 3000)})
        self.assertEqual(out["16x9"].getpixel((10, 700)), BAR)
        self.assertEqual(out["square"].getpixel((10, 2990)), BAR)

    def test_the_duotone_maps_the_photo_between_the_shadow_and_highlight_colors(self):
        out = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, FRAMES, DENIM, None)["16x9"]
        region = out.crop((0, 8, 1280, 584)).resize((64, 28))
        lo = [min(p[c] for p in region.getdata()) for c in range(3)]
        hi = [max(p[c] for p in region.getdata()) for c in range(3)]
        shadow, highlight = (0x22, 0x29, 0x3a), (0x71, 0x93, 0xb8)
        for c in range(3):
            # a few levels of slack: Lanczos resampling overshoots slightly at hard edges
            self.assertGreaterEqual(lo[c], min(shadow[c], highlight[c]) - 8)
            self.assertLessEqual(hi[c], max(shadow[c], highlight[c]) + 8)

    def test_without_a_duotone_the_photo_keeps_its_own_colour(self):
        out = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, FRAMES, None, None)["16x9"]
        reds = {p[0] for p in out.crop((0, 8, 1280, 584)).resize((32, 14)).getdata()}
        greens = {p[1] for p in out.crop((0, 8, 1280, 584)).resize((32, 14)).getdata()}
        self.assertGreater(len(reds | greens), 20)

    def test_different_variants_give_visibly_different_crops_of_the_same_photo(self):
        photo = sample_photo()
        a = photo_render.render_formats(photo, (0.4, 0.45), {"zoom": 1.0, "strategy": "center"}, FRAMES, DENIM, None)["16x9"]
        b = photo_render.render_formats(photo, (0.4, 0.45), {"zoom": 1.8, "strategy": "right_third"}, FRAMES, DENIM, None)["16x9"]
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_a_caption_plate_is_drawn_inside_the_window_above_the_footer(self):
        plain = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, FRAMES, DENIM, None)["16x9"]
        capt = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, FRAMES, DENIM, {"topic": "Cyberattack", "date": date(2026, 10, 9)})["16x9"]
        self.assertNotEqual(plain.crop((0, 500, 1280, 584)).tobytes(), capt.crop((0, 500, 1280, 584)).tobytes())
        self.assertEqual(plain.crop((0, 8, 1280, 480)).tobytes(), capt.crop((0, 8, 1280, 480)).tobytes())   # above the plate: untouched
        self.assertEqual(capt.getpixel((10, 700)), BAR)

    def test_a_topic_word_that_cannot_fit_falls_back_to_the_date_alone(self):
        out = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, FRAMES, DENIM,
                                          {"topic": "Internationalization of everything under the sun", "date": date(2026, 10, 9)})
        self.assertEqual(out["16x9"].size, (1280, 720))

    def test_k12_in_a_caption_draws_like_a_plain_hyphen(self):
        a = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, FRAMES, DENIM, {"topic": "K-12 budgets", "date": date(2026, 10, 9)})
        b = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, FRAMES, DENIM, {"topic": "K‑12 budgets", "date": date(2026, 10, 9)})
        self.assertEqual(a["16x9"].tobytes(), b["16x9"].tobytes())

    def test_portrait_and_small_photos_still_fill_every_window(self):
        for size in ((2667, 4000), (1500, 1000)):
            out = photo_render.render_formats(sample_photo(size), (0.5, 0.5), {"zoom": 1.8, "strategy": "left_third"}, FRAMES, DENIM, None)
            self.assertEqual(out["square"].size, (3000, 3000))

    def test_the_square_window_follows_the_frame_not_a_hardcoded_size(self):
        old_frame = dict(FRAMES, square=frame_png((3000, 3000), 25, 2615))
        out = photo_render.render_formats(sample_photo(), (0.5, 0.5), self.VARIANT, old_frame, DENIM, None)["square"]
        self.assertEqual(out.getpixel((10, 2990)), BAR)
        self.assertNotEqual(out.getpixel((1500, 2610)), BAR)


# --- the image step -------------------------------------------------------------------------------

STORY_BRIEF = {"topics": ["k12"], "settings": ["classroom"], "sensitive": False}


def jpeg(size=(3000, 2000)):
    buf = BytesIO()
    sample_photo(size).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class FakeWP:
    def __init__(self, photos, episode_meta=None, show_meta=None):
        self.photos = photos
        self.episode = {"meta": dict({"ng_episode_date": "2026-10-09", "ng_script_final": "script"}, **(episode_meta or {}))}
        self.show = {"meta": dict({"ng_frame_square_id": 1, "ng_frame_16x9_id": 2, "ng_frame_1200x630_id": 3, "ng_image_mode": "photos",
                                   "ng_image_style": "duotone", "ng_duotone_shadow_color": DENIM[0], "ng_duotone_highlight_color": DENIM[1],
                                   "ng_photo_caption": "topic"}, **(show_meta or {}))}
        self.uploads, self.episode_updates, self.used = [], [], []

    def get_episode(self, episode_id): return self.episode
    def get_show(self, show_id): return self.show
    def get_attachment_url(self, attachment_id): return f"url/{attachment_id}"
    def download_binary(self, url): return {"url/1": FRAMES["square"], "url/2": FRAMES["16x9"], "url/3": FRAMES["1200x630"]}[url]
    def list_photos(self, show_id, for_date=None): return {"photos": self.photos, "cooldown_days": 90}
    def get_photo_file(self, photo_id): return jpeg()
    def upload_media(self, data, filename, mime):
        self.uploads.append((filename, mime, len(data))); return 500 + len(self.uploads)
    def update_episode_meta(self, episode_id, meta): self.episode_updates.append(meta)
    def mark_photo_used(self, photo_id, episode_id, episode_date): self.used.append((photo_id, episode_id, episode_date))


def fake_generate(brief=STORY_BRIEF, keywords=("Cyberattack", "AI detectors", "Acquisition")):
    def generate(system, user_content, tools, response_schema):
        props = response_schema.get("properties", {})
        if "settings" in props:
            return json.dumps(brief)
        if "headline_story" in props:
            return json.dumps({"stories": ["a", "b", "c"], "headline_story": 1, "word_stories": [1, 2, 3][:len(keywords)]})
        return json.dumps({"headline": "A perfectly fine headline here", "words": [{"story": i + 1, "word": w} for i, w in enumerate(keywords)]})
    return generate


SHOW = {"id": 16, "name": "Net Gain Edtech", "slug": "edtech"}


def ready(id_, **kw):
    base = {"id": id_, "status": "ready", "eligible": True, "tags": ["classroom"], "topics": ["k12"], "people": "none", "flags": [],
            "use_count": 0, "last_used": "", "focal_x": 0.5, "focal_y": 0.5}
    base.update(kw)
    return base


class PhotoPathTests(unittest.TestCase):
    def render(self, wp, generate=None):
        return image_generation.render_images_for_episode(wp, None, generate or fake_generate(), SHOW, 7)

    def test_draws_three_graphics_records_the_photo_and_marks_it_used(self):
        wp = FakeWP([ready(11), ready(12, topics=["security"])])
        result = self.render(wp)
        self.assertEqual(len(wp.uploads), 3)
        self.assertEqual({f for f, _, _ in wp.uploads}, {"edtech-2026-10-09-square.jpg", "edtech-2026-10-09-16x9.jpg", "edtech-2026-10-09-1200x630.webp"})
        meta = wp.episode_updates[-1]
        self.assertEqual(meta["ng_photo_id"], 11)                       # topic k12 matches photo 11
        self.assertEqual(set(json.loads(meta["ng_photo_variant"])), {"zoom", "strategy"})
        self.assertEqual(wp.used, [(11, 7, "2026-10-09")])
        self.assertEqual(result, {"relaxed": False, "photo_id": 11})

    def test_a_re_render_keeps_the_episodes_photo_and_crop(self):
        variant = {"zoom": 1.5, "strategy": "left_third"}
        wp = FakeWP([ready(11), ready(12)], episode_meta={"ng_photo_id": 12, "ng_photo_variant": json.dumps(variant)})
        self.render(wp)
        self.assertEqual(wp.episode_updates[-1]["ng_photo_id"], 12)
        self.assertEqual(json.loads(wp.episode_updates[-1]["ng_photo_variant"]), variant)

    def test_a_sensitive_story_avoids_photos_with_identifiable_people(self):
        wp = FakeWP([ready(11, people="identifiable"), ready(12, people="none", topics=["general"])])
        self.render(wp, fake_generate(dict(STORY_BRIEF, sensitive=True)))
        self.assertEqual(wp.episode_updates[-1]["ng_photo_id"], 12)

    def test_an_empty_library_fails_loudly_instead_of_falling_back_to_cards(self):
        wp = FakeWP([])
        with self.assertRaisesRegex(RuntimeError, "nothing usable.*Photos"):
            self.render(wp)
        self.assertEqual(wp.uploads, [])
        self.assertEqual(wp.used, [])

    def test_only_identifiable_photos_for_a_sensitive_story_is_explained(self):
        wp = FakeWP([ready(11, people="identifiable")])
        with self.assertRaisesRegex(RuntimeError, "identifiable people"):
            self.render(wp, fake_generate(dict(STORY_BRIEF, sensitive=True)))

    def test_resting_photos_are_reused_only_when_nothing_else_is_left_and_the_caller_is_told(self):
        wp = FakeWP([ready(11, eligible=False, last_used="2026-09-01", use_count=1)])
        self.assertEqual(self.render(wp)["relaxed"], True)
        self.assertEqual(wp.episode_updates[-1]["ng_photo_id"], 11)

    def test_a_story_order_failure_in_the_caption_text_falls_back_to_the_date(self):
        def broken(system, user_content, tools, response_schema):
            if "settings" in response_schema.get("properties", {}):
                return json.dumps(STORY_BRIEF)
            raise RuntimeError("API down")
        wp = FakeWP([ready(11)])
        self.render(wp, broken)
        self.assertEqual(len(wp.uploads), 3)

    def test_caption_none_skips_the_caption_text_call(self):
        calls = []
        base = fake_generate()
        def spy(system, user_content, tools, response_schema):
            calls.append(list(response_schema.get("properties", {})))
            return base(system, user_content, tools, response_schema)
        wp = FakeWP([ready(11)], show_meta={"ng_photo_caption": "none"})
        self.render(wp, spy)
        self.assertTrue(all("headline" not in c for c in calls))


# --- tick: tagging, weekly note, low-stock warning ------------------------------------------------

CONFIG = {"SMTP_HOST": "x", "ALERT_TO_EMAIL": "me@example.com"}


class TaggingStepTests(unittest.TestCase):
    def wp(self, photos):
        wp = Mock()
        wp.list_photos.return_value = {"photos": photos}
        wp.get_photo_file.return_value = jpeg((3200, 2400))
        return wp

    def good_generate(self, **kwargs):
        return json.dumps({"is_photograph": True, "tags": ["laptop"], "topics": ["security"], "people": "none", "focal_x": 0.5,
                           "focal_y": 0.5, "description": "A laptop.", "logo_or_text_visible": False})

    @patch("tick.anthropic_generate")
    def test_pending_photos_get_tagged_and_become_ready(self, gen):
        gen.side_effect = lambda client, **kw: self.good_generate()
        wp = self.wp([{"id": 5, "status": "pending_tags"}, {"id": 6, "status": "ready"}])
        tick.process_photo_tagging(wp, object(), CONFIG, {"id": 16, "name": "Show"})
        wp.update_photo.assert_called_once()
        pid, fields = wp.update_photo.call_args[0]
        self.assertEqual((pid, fields["status"], fields["people"]), (5, "ready", "none"))

    @patch("tick.anthropic_generate")
    def test_an_unreadable_file_is_retired_for_review(self, gen):
        wp = self.wp([{"id": 5, "status": "pending_tags"}])
        wp.get_photo_file.return_value = b"garbage"
        tick.process_photo_tagging(wp, object(), CONFIG, {"id": 16, "name": "Show"})
        pid, fields = wp.update_photo.call_args[0]
        self.assertEqual((pid, fields["status"]), (5, "retired"))
        self.assertIn("needs_review", fields["flags"])

    @patch("tick.anthropic_generate")
    def test_an_api_failure_leaves_the_photo_pending_for_the_next_tick(self, gen):
        gen.side_effect = RuntimeError("API down")
        wp = self.wp([{"id": 5, "status": "pending_tags"}])
        tick.process_photo_tagging(wp, object(), CONFIG, {"id": 16, "name": "Show"})
        wp.update_photo.assert_not_called()

    @patch("tick.anthropic_generate")
    def test_only_a_few_photos_are_tagged_per_tick(self, gen):
        gen.side_effect = lambda client, **kw: self.good_generate()
        wp = self.wp([{"id": i, "status": "pending_tags"} for i in range(10)])
        tick.process_photo_tagging(wp, object(), CONFIG, {"id": 16, "name": "Show"}, limit=4)
        self.assertEqual(wp.update_photo.call_count, 4)


class DigestTests(unittest.TestCase):
    STATS = {"level": "low", "eligible_now": 14, "cooling_down": 3, "cooldown_days": 90, "never_used": 2, "eligible_no_faces": 4, "retired": 0, "messages": []}
    SHOW = {"id": 16, "name": "Net Gain Edtech", "recording_timezone": "America/New_York"}

    def wp(self, meta):
        wp = Mock()
        wp.get_show.return_value = {"meta": meta}
        wp.get_photo_stats.return_value = self.STATS
        return wp

    def run_at(self, wp, moment, sent=True):
        with patch("tick.datetime") as dt, patch("tick.send_notice", return_value=sent) as notice:
            dt.now.return_value = moment
            tick.process_photo_digest(wp, CONFIG, self.SHOW)
            return notice

    def test_sent_on_monday_morning_and_recorded(self):
        wp = self.wp({"ng_image_mode": "photos"})
        notice = self.run_at(wp, datetime(2026, 10, 12, 9, 0, tzinfo=ZoneInfo("America/New_York")))
        notice.assert_called_once()
        wp.update_show_meta.assert_called_once_with(16, {"ng_photo_digest_last_sent": "2026-10-12"})

    def test_not_before_eight_not_on_other_days_not_twice_and_not_for_other_modes(self):
        et = ZoneInfo("America/New_York")
        for moment, meta in [(datetime(2026, 10, 12, 7, 0, tzinfo=et), {"ng_image_mode": "photos"}),
                             (datetime(2026, 10, 13, 9, 0, tzinfo=et), {"ng_image_mode": "photos"}),
                             (datetime(2026, 10, 12, 9, 0, tzinfo=et), {"ng_image_mode": "photos", "ng_photo_digest_last_sent": "2026-10-12"}),
                             (datetime(2026, 10, 12, 9, 0, tzinfo=et), {"ng_image_mode": "cards"})]:
            self.assertFalse(self.run_at(self.wp(meta), moment).called, (moment, meta))

    def test_not_recorded_as_sent_if_the_email_failed(self):
        wp = self.wp({"ng_image_mode": "photos"})
        self.run_at(wp, datetime(2026, 10, 12, 9, 0, tzinfo=ZoneInfo("America/New_York")), sent=False)
        wp.update_show_meta.assert_not_called()


class LowStockWarningTests(unittest.TestCase):
    def test_warns_once_then_stays_quiet_for_three_days(self):
        wp = Mock()
        wp.get_show.return_value = {"meta": {}}
        wp.get_photo_stats.return_value = DigestTests.STATS
        with patch("tick.send_notice", return_value=True) as notice:
            tick.warn_photo_library_low(wp, CONFIG, {"id": 16, "name": "Show"}, "2026-10-09")
            notice.assert_called_once()
            self.assertIn("PHOTOS NEEDED", notice.call_args[0][1])
            today = datetime.now().date().isoformat()
            wp.update_show_meta.assert_called_once()
        wp2 = Mock()
        wp2.get_show.return_value = {"meta": {"ng_photo_low_alert_last": datetime.utcnow().date().isoformat()}}
        with patch("tick.send_notice") as notice2:
            tick.warn_photo_library_low(wp2, CONFIG, {"id": 16, "name": "Show"}, "2026-10-09")
            notice2.assert_not_called()


if __name__ == "__main__":
    unittest.main()
