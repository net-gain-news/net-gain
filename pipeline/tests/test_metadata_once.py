"""generate_metadata runs once per episode, and reads recent headlines for context (2026-10-19)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tick


class FakeWP:
    def __init__(self, meta, episodes=None, list_error=False):
        self.meta = meta
        self.episodes = episodes or []
        self.list_error = list_error
        self.updates = []
        self.steps = []

    def get_episode(self, episode_id):
        return {"meta": self.meta}

    def list_episodes_for_show(self, show_id):
        if self.list_error:
            raise RuntimeError("down")
        return self.episodes

    def update_episode_meta(self, episode_id, values):
        self.updates.append(values)

    def update_step(self, episode_id, step, status, **kwargs):
        self.steps.append((step, status))


GENERATED = {
    "captivate_title": "C", "captivate_notes": "N", "aioseo_title": "A", "aioseo_description": "D",
    "website_excerpt": "E", "youtube_title": "Y", "youtube_description": "YD", "youtube_tags": ["t"],
}
DONE = {"ng_episode_date": "2026-10-19", "ng_script_final": "script", "ng_meta_captivate_title": "Existing",
        "ng_meta_aioseo_title": "Existing too", "ng_step_status": {"metadata_generated": {"status": "done"}}}


class GenerateOnce(unittest.TestCase):
    def test_a_finished_set_is_not_regenerated(self):
        wp = FakeWP(dict(DONE))
        with mock.patch.object(tick, "generate_metadata_for_episode") as gen:
            tick.generate_metadata(wp, object(), {"id": 16, "name": "Show"}, 600)
        gen.assert_not_called()
        self.assertEqual(wp.updates, [])

    def test_force_regenerates_and_stores(self):
        wp = FakeWP(dict(DONE))
        with mock.patch.object(tick, "generate_metadata_for_episode", return_value=GENERATED) as gen:
            tick.generate_metadata(wp, object(), {"id": 16, "name": "Show"}, 600, force=True)
        gen.assert_called_once()
        self.assertEqual(wp.updates[0]["ng_meta_captivate_title"], "C")
        self.assertIn(("metadata_generated", "done"), wp.steps)

    def test_hand_edited_seo_text_and_excerpt_survive_a_forced_regeneration(self):
        # 2026-10-21: an editor's AIOSEO title/description on the Arbor episode kept being replaced by generated text.
        wp = FakeWP(dict(DONE, ng_seo_hand_edited="2026-10-21 14:19:15"))
        with mock.patch.object(tick, "generate_metadata_for_episode", return_value=GENERATED):
            tick.generate_metadata(wp, object(), {"id": 16, "name": "Show"}, 600, force=True)
        stored = wp.updates[0]
        for key in ("ng_meta_aioseo_title", "ng_meta_aioseo_description", "ng_meta_website_excerpt"):
            self.assertNotIn(key, stored)
        self.assertEqual(stored["ng_meta_captivate_title"], "C")      # the other destinations still regenerate
        self.assertEqual(stored["ng_meta_youtube_title"], "Y")

    def test_without_the_flag_everything_regenerates(self):
        wp = FakeWP(dict(DONE))
        with mock.patch.object(tick, "generate_metadata_for_episode", return_value=GENERATED):
            tick.generate_metadata(wp, object(), {"id": 16, "name": "Show"}, 600, force=True)
        self.assertEqual(wp.updates[0]["ng_meta_aioseo_title"], "A")
        self.assertEqual(wp.updates[0]["ng_meta_website_excerpt"], "E")

    def test_a_pending_episode_generates(self):
        meta = {"ng_episode_date": "2026-10-19", "ng_script_final": "script", "ng_step_status": {"metadata_generated": {"status": "pending"}}}
        wp = FakeWP(meta)
        with mock.patch.object(tick, "generate_metadata_for_episode", return_value=GENERATED) as gen:
            tick.generate_metadata(wp, object(), {"id": 16, "name": "Show"}, 600)
        gen.assert_called_once()

    def test_a_done_status_without_stored_titles_still_generates(self):
        meta = {"ng_episode_date": "2026-10-19", "ng_script_final": "script", "ng_step_status": {"metadata_generated": {"status": "done"}}}
        with mock.patch.object(tick, "generate_metadata_for_episode", return_value=GENERATED) as gen:
            tick.generate_metadata(FakeWP(meta), object(), {"id": 16, "name": "Show"}, 600)
        gen.assert_called_once()

    def test_recent_headlines_are_passed_to_the_generator(self):
        episodes = [{"meta": {"ng_episode_date": "2026-10-16", "ng_meta_aioseo_title": "Arbor Education Breach"}}]
        meta = {"ng_episode_date": "2026-10-19", "ng_script_final": "script", "ng_step_status": {}}
        with mock.patch.object(tick, "generate_metadata_for_episode", return_value=GENERATED) as gen:
            tick.generate_metadata(FakeWP(meta, episodes), object(), {"id": 16, "name": "Show"}, 600)
        self.assertEqual(gen.call_args.kwargs["recent_titles"], ["Arbor Education Breach"])


class RecentHeadlines(unittest.TestCase):
    def test_newest_first_only_earlier_days_and_html_decoded(self):
        episodes = [
            {"meta": {"ng_episode_date": "2026-10-15", "ng_meta_aioseo_title": "Older"}},
            {"meta": {"ng_episode_date": "2026-10-19", "ng_meta_aioseo_title": "Today itself"}},
            {"meta": {"ng_episode_date": "2026-10-16"}, "title": {"rendered": "Arbor &amp; Friends"}},
        ]
        self.assertEqual(tick.recent_headlines(FakeWP({}, episodes), 16, "2026-10-19"), ["Arbor & Friends", "Older"])

    def test_limited(self):
        episodes = [{"meta": {"ng_episode_date": f"2026-09-{d:02d}", "ng_meta_aioseo_title": f"T{d}"}} for d in range(1, 21)]
        self.assertEqual(len(tick.recent_headlines(FakeWP({}, episodes), 16, "2026-10-19")), tick.RECENT_HEADLINES_LIMIT)

    def test_a_failure_means_no_context_not_an_error(self):
        self.assertEqual(tick.recent_headlines(FakeWP({}, list_error=True), 16, "2026-10-19"), [])


if __name__ == "__main__":
    unittest.main()
