import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio_replacement as ar
import captivate_client


def captivate_episode(**overrides):
    ep = {
        "id": "cap-1", "title": "Ep title", "itunes_title": "", "episode_number": 4, "status": "Published",
        "shownotes": "<p>notes</p>", "summary": "", "itunes_subtitle": "", "episode_art": "https://x/art.jpg",
        "explicit": "clean", "episode_type": "full", "itunes_block": "false",
        "published_date": "2026/09/28 15:38:00", "media_id": "old-media", "media_url": "https://x/old.mp3",
    }
    ep.update(overrides)
    return ep


class CaptivateIdTests(unittest.TestCase):
    def test_parses_the_id_from_the_player_url(self):
        self.assertEqual(ar.captivate_episode_id({"ng_url_captivate": "https://player.captivate.fm/episode/abc-123"}), "abc-123")

    def test_empty_when_not_published(self):
        self.assertEqual(ar.captivate_episode_id({}), "")


class EpisodeUpdatePayloadTests(unittest.TestCase):
    def test_resends_every_field_and_changes_only_the_media_id(self):
        before = captivate_episode()
        payload = captivate_client.episode_update_payload(before, "show-1", "new-media")
        self.assertEqual(payload["media_id"], "new-media")
        for field in ("title", "shownotes", "status", "episode_number", "episode_art", "explicit"):
            self.assertEqual(payload[field], before[field])
        self.assertEqual(payload["shows_id"], "show-1")

    def test_accepts_both_published_date_shapes_and_round_trips_the_instant(self):
        """Live finding: Captivate returns the account-local 'YYYY/MM/DD HH:MM:SS' form on PUT-updated
        episodes, which the older one-off helper (ISO only) crashed on."""
        local = captivate_client.episode_update_payload(captivate_episode(published_date="2026/09/28 15:38:00"), "s", "m")
        self.assertEqual(local["date"], "2026-09-28 15:38:00")
        utc = captivate_client.episode_update_payload(captivate_episode(published_date="2026-09-28T22:38:00.000Z"), "s", "m")
        self.assertEqual(utc["date"], "2026-09-28 15:38:00")


class VerifyCaptivateSwapTests(unittest.TestCase):
    def test_clean_swap_has_no_problems(self):
        before = captivate_episode()
        after = captivate_episode(media_id="new-media", media_url="https://x/new.mp3")
        self.assertEqual(ar.verify_captivate_swap(before, after, "new-media"), [])

    def test_flags_any_other_field_drifting(self):
        before = captivate_episode()
        after = captivate_episode(media_id="new-media", media_url="https://x/new.mp3", shownotes="changed")
        problems = ar.verify_captivate_swap(before, after, "new-media")
        self.assertTrue(any("shownotes" in p for p in problems))

    def test_flags_a_swap_that_did_not_take(self):
        before = captivate_episode()
        problems = ar.verify_captivate_swap(before, captivate_episode(), "new-media")
        self.assertTrue(any("media_id" in p for p in problems))
        self.assertTrue(any("media_url" in p for p in problems))

    def test_flags_the_publish_date_moving(self):
        before = captivate_episode()
        after = captivate_episode(media_id="n", media_url="u2", published_date="2026/09/29 15:38:00")
        self.assertTrue(any("published_date" in p for p in ar.verify_captivate_swap(before, after, "n")))


class SwapCaptivateAudioTests(unittest.TestCase):
    def setUp(self):
        self.wp = mock.Mock()
        self.wp.get_attachment_url.return_value = "https://netgain.news/uploads/new-audio.m4a"
        self.wp.download_binary.return_value = b"raw"
        self.captivate = mock.Mock()
        self.captivate.upload_media.return_value = "new-media"
        self.before = captivate_episode()
        self.after = captivate_episode(media_id="new-media", media_url="https://x/new.mp3")
        self.captivate.get_episode.side_effect = [{"episode": self.before}, {"episode": self.after}]
        self.show = {"id": 16, "captivate_show_id": "show-1"}
        self.meta = {"ng_url_captivate": "https://player.captivate.fm/episode/cap-1"}

    def run_swap(self, record):
        with mock.patch.object(ar, "convert_to_captivate_bitrate", return_value=b"converted"):
            return ar.swap_captivate_audio(self.wp, self.captivate, self.show, 180, self.meta, record)

    def test_skips_when_not_on_captivate(self):
        status, _, _ = ar.swap_captivate_audio(self.wp, self.captivate, self.show, 180, {}, {"new_attachment_id": 9})
        self.assertEqual(status, "skipped")
        self.captivate.upload_media.assert_not_called()

    def test_signs_in_to_captivate_before_any_call(self):
        """Live bug (2026-10-02): the client authenticates lazily, and this path skipped it, so the
        very first upload was a 401 Unauthorized."""
        self.run_swap({"new_attachment_id": 9, "destinations": {"captivate": {"status": "pending"}}})
        names = [c[0] for c in self.captivate.method_calls]
        self.assertEqual(names[0], "ensure_authenticated")
        self.assertLess(names.index("ensure_authenticated"), names.index("upload_media"))

    def test_uploads_converted_audio_then_updates_and_verifies(self):
        status, note, data = self.run_swap({"new_attachment_id": 9, "destinations": {"captivate": {"status": "pending"}}})
        self.assertEqual(status, "done")
        self.captivate.upload_media.assert_called_once_with("show-1", b"converted", "new-audio.mp3")
        payload = self.captivate.update_episode.call_args[0][1]
        self.assertEqual(payload["media_id"], "new-media")
        self.assertEqual(data["previous_media_id"], "old-media")

    def test_records_the_media_id_before_the_put(self):
        self.run_swap({"new_attachment_id": 9, "destinations": {"captivate": {"status": "pending"}}})
        self.wp.update_audio_replacement.assert_called_once_with(180, "captivate", "pending", data={"media_id": "new-media"})

    def test_a_retry_reuses_the_recorded_media_and_never_uploads_again(self):
        record = {"new_attachment_id": 9, "destinations": {"captivate": {"status": "pending", "media_id": "new-media"}}}
        self.run_swap(record)
        self.captivate.upload_media.assert_not_called()

    def test_drift_after_the_swap_is_a_failure_that_names_the_rollback_media(self):
        self.captivate.get_episode.side_effect = [
            {"episode": self.before},
            {"episode": captivate_episode(media_id="new-media", media_url="https://x/new.mp3", title="Different")},
        ]
        with self.assertRaises(RuntimeError) as ctx:
            self.run_swap({"new_attachment_id": 9, "destinations": {"captivate": {"status": "pending"}}})
        self.assertIn("title changed", str(ctx.exception))
        self.assertIn("old-media", str(ctx.exception))


class ReplaceYouTubeVideoTests(unittest.TestCase):
    def setUp(self):
        self.wp = mock.Mock()
        self.wp.get_youtube_access_token.return_value = {"access_token": "t"}
        self.show = {"id": 16, "youtube_channel_id": "chan"}

    def run_replace(self, meta, deleted=True, channel="chan"):
        with mock.patch.object(ar.yt, "build_service", return_value="svc"), \
             mock.patch.object(ar.yt, "get_own_channel_id", return_value=channel), \
             mock.patch.object(ar.yt, "delete_video", return_value=deleted) as delete:
            result = ar.replace_youtube_video(self.wp, self.show, 180, meta)
        return result, delete

    def test_deletes_clears_the_episode_and_resets_the_step(self):
        (status, note, data), delete = self.run_replace({"ng_youtube_video_id": "vid1", "ng_step_status": {}})
        delete.assert_called_once_with("svc", "vid1")
        self.assertEqual(status, "done")
        self.assertEqual(data["deleted_video_id"], "vid1")
        cleared = self.wp.update_episode_meta.call_args[0][1]
        self.assertEqual(cleared["ng_youtube_video_id"], "")
        self.assertEqual(cleared["ng_url_youtube"], "")
        self.assertEqual(self.wp.update_step.call_args[0][:3], (180, "youtube_published", "pending"))

    def test_an_already_deleted_video_is_not_an_error(self):
        (status, note, _), _ = self.run_replace({"ng_youtube_video_id": "vid1"}, deleted=False)
        self.assertEqual(status, "done")
        self.assertIn("already gone", note)
        self.wp.update_step.assert_called_once()

    def test_skips_when_there_is_no_video(self):
        (status, _, _), delete = self.run_replace({"ng_step_status": {"youtube_published": {"status": "pending"}}})
        self.assertEqual(status, "skipped")
        delete.assert_not_called()

    def test_waits_while_an_upload_is_mid_flight_with_no_id_yet(self):
        (status, _, _), delete = self.run_replace({"ng_step_status": {"youtube_published": {"status": "in_progress"}}})
        self.assertEqual(status, "waiting")
        delete.assert_not_called()

    def test_refuses_to_delete_through_a_token_for_the_wrong_channel(self):
        with self.assertRaises(RuntimeError):
            self.run_replace({"ng_youtube_video_id": "vid1"}, channel="someone-else")
        self.wp.update_step.assert_not_called()


class ProcessAudioReplacementsTests(unittest.TestCase):
    def test_failure_is_recorded_notified_and_does_not_stop_the_other_destination(self):
        wp = mock.Mock()
        wp.get_episode.return_value = {"meta": {}}
        notify = mock.Mock()
        show = {"id": 16, "name": "Net Gain Edtech", "audio_replacements": [{
            "episode_id": 180, "new_attachment_id": 9,
            "destinations": {"captivate": {"status": "pending"}, "youtube": {"status": "pending"}},
        }]}
        with mock.patch.object(ar, "swap_captivate_audio", side_effect=RuntimeError("boom")), \
             mock.patch.object(ar, "replace_youtube_video", return_value=("skipped", "n/a", {})):
            ar.process_audio_replacements(wp, mock.Mock(), {}, show, notify)
        calls = {c[0][1]: c[0][2] for c in wp.update_audio_replacement.call_args_list}
        self.assertEqual(calls["captivate"], "failed")
        self.assertEqual(calls["youtube"], "skipped")
        notify.assert_called_once()

    def test_already_settled_destinations_are_left_alone(self):
        wp = mock.Mock()
        show = {"id": 16, "name": "x", "audio_replacements": [{
            "episode_id": 1, "new_attachment_id": 2,
            "destinations": {"captivate": {"status": "done"}, "youtube": {"status": "failed"}},
        }]}
        with mock.patch.object(ar, "swap_captivate_audio") as swap, mock.patch.object(ar, "replace_youtube_video") as yt:
            ar.process_audio_replacements(wp, mock.Mock(), {}, show, mock.Mock())
        swap.assert_not_called()
        yt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
