import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_step
from run_step import StepRefused, run_step as run

ALL_DONE = {k: {"status": "done"} for k in (
    "script_generated", "script_reviewed", "audio_received", "metadata_generated", "images_rendered",
    "captivate_published", "website_published", "youtube_published")}


def _wp(meta=None, steps=None):
    wp = Mock()
    base = {"ng_episode_date": "2026-11-02", "ng_step_status": steps or ALL_DONE, "ng_finalization": {"state": "finalized"}}
    base.update(meta or {})
    wp.get_episode.return_value = {"meta": base}
    return wp


SHOW = {"id": 16, "name": "Edtech", "youtube_channel_id": "UC123"}


def _go(step, wp, **kw):
    return run(step, wp, Mock(), {}, SHOW, 671, make_captivate=Mock(), make_vertex=Mock(), **kw)


class RunStepTests(unittest.TestCase):
    def test_unknown_step_is_refused(self):
        with self.assertRaises(StepRefused):
            _go("nope", _wp())

    def test_nothing_runs_before_audio(self):
        steps = dict(ALL_DONE, audio_received={"status": "pending"})
        with self.assertRaises(StepRefused):
            _go("captivate", _wp(steps=steps))

    def test_captivate_on_an_episode_already_there_updates_it_and_never_creates_another(self):
        wp = _wp({"ng_url_captivate": "https://player.captivate.fm/episode/abc"})
        with patch.object(run_step, "push_to_captivate", return_value="title now 'T'") as push, \
             patch.object(run_step.tick, "publish_episode_to_captivate") as publish:
            outcome = _go("captivate", wp)
        push.assert_called_once()
        publish.assert_not_called()
        self.assertIn("updated in place", outcome)

    def test_captivate_on_a_new_episode_publishes(self):
        with patch.object(run_step.tick, "publish_episode_to_captivate") as publish:
            _go("captivate", _wp())
        publish.assert_called_once()

    def test_website_refuses_over_hand_edits_unless_told(self):
        wp = _wp({"ng_seo_hand_edited": True})
        with patch.object(run_step.tick, "publish_episode_to_website") as publish:
            with self.assertRaises(StepRefused):
                _go("website", wp)
            publish.assert_not_called()
            _go("website", wp, override_hand_edits=True)
            publish.assert_called_once()

    def test_youtube_checks_an_existing_video_and_never_uploads_a_second(self):
        with patch.object(run_step.tick, "publish_episode_to_youtube") as publish:
            _go("youtube", _wp({"ng_youtube_video_id": "abc"}))
        self.assertEqual(publish.call_args.args[5], "verify")

    def test_youtube_refuses_a_possible_orphan_upload(self):
        with patch.object(run_step.tick, "publish_episode_to_youtube") as publish:
            with self.assertRaises(StepRefused):
                _go("youtube", _wp({"ng_youtube_upload_started_at": "2026-11-02T21:50:00+00:00"}))
            publish.assert_not_called()
            _go("youtube", _wp({"ng_youtube_upload_started_at": "2026-11-02T21:50:00+00:00"}), allow_orphan_check_done=True)
            self.assertEqual(publish.call_args.args[5], "upload")

    def test_youtube_waits_for_captivate_and_website(self):
        steps = dict(ALL_DONE, website_published={"status": "pending"})
        with self.assertRaises(StepRefused):
            _go("youtube", _wp(steps=steps))

    def test_strip_reports_whether_it_was_stored(self):
        with patch.object(run_step, "refresh_signature_strip", return_value=True):
            self.assertEqual(_go("strip", _wp()), "strip stored")
        with patch.object(run_step, "refresh_signature_strip", return_value=False):
            self.assertIn("NOT stored", _go("strip", _wp()))

    def test_reports_the_step_status_it_ended_in(self):
        steps = dict(ALL_DONE, images_rendered={"status": "failed", "note": "Imagen quota"})
        with patch.object(run_step.tick, "render_episode_images"):
            outcome = _go("images", _wp(steps=steps))
        self.assertEqual(outcome, "images: failed - Imagen quota")


if __name__ == "__main__":
    unittest.main()
