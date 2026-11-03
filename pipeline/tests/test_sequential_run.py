"""
One pass chains the whole publish sequence: images, then Captivate, then the website (and the signature strip), with each
step seeing what the one before it just did, instead of one step per five-minute tick.
"""
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tick
from tick import housekeeping_due, note_busy_show, process_show, refresh_in_flight, refresh_strip_when_live, run_phase


class FakeWP:
    """A tiny in-memory WordPress: one episode whose step status changes as the pass works through it."""

    def __init__(self, steps, finalization=None, meta=None):
        self.steps = {k: {"status": v} for k, v in steps.items()}
        self.finalization = finalization or {"state": "finalized", "finalized_at": "2026-11-02 21:40:00"}
        self.meta = dict(meta or {})
        self.calls = []

    def get_episode(self, episode_id):
        meta = dict(self.meta, ng_step_status=self.steps, ng_finalization=self.finalization)
        return {"id": episode_id, "meta": meta, "title": {"rendered": "T"}}

    def update_step(self, episode_id, step, status, note=""):
        self.steps[step] = {"status": status}
        self.calls.append(("step", step, status))

    def update_episode_meta(self, episode_id, meta):
        self.meta.update(meta)

    def update_action(self, *args):
        pass

    def publish_website(self, episode_id):
        self.calls.append(("publish_website",))
        return {"permalink": "https://netgain.news/edtech/x/"}

    def get_show(self, show_id):
        return {"meta": {}}


def _show(wp, **extra):
    episode = {
        "id": 671,
        "episode_date": "2026-11-02",
        "step_status": {k: dict(v) for k, v in wp.steps.items()},
        "finalization": dict(wp.finalization),
    }
    show = {
        "id": 16,
        "name": "Net Gain Edtech",
        "publish_mode": "immediate",
        "pending_actions": [],
        "youtube_channel_id": "",
        "captivate_show_id": "abc",
        "in_flight_episodes": [episode],
    }
    show.update(extra)
    return show


UPLOADED = {
    "script_generated": "done",
    "script_reviewed": "done",
    "audio_received": "done",
    "metadata_generated": "pending",
    "images_rendered": "pending",
    "captivate_published": "pending",
    "website_published": "pending",
    "youtube_published": "pending",
}


class OnePassChainTests(unittest.TestCase):
    def _run(self, wp, show, captivate_side_effect=None):
        order = []

        def render(*args, **kwargs):
            order.append("images")
            return {}

        def captivate(*args, **kwargs):
            order.append("captivate")
            if captivate_side_effect:
                raise captivate_side_effect
            return 29

        def strip(*args, **kwargs):
            order.append("strip")
            return True

        def website_verified(*args, **kwargs):
            order.append("website")

        with patch.object(tick, "render_images_for_episode", side_effect=render), \
             patch.object(tick, "generate_metadata"), \
             patch.object(tick, "publish_to_captivate", side_effect=captivate), \
             patch.object(tick, "record_audio_seconds"), \
             patch.object(tick, "verify_website_publish", side_effect=website_verified), \
             patch.object(tick, "refresh_signature_strip", side_effect=strip), \
             patch.object(tick, "notify_failure"), \
             patch.object(tick, "process_index_refresh"), \
             patch.object(tick, "process_script_generation"), \
             patch.object(tick, "process_photo_tagging"), \
             patch.object(tick, "process_photo_digest"):
            process_show(wp, Mock(), Mock(), Mock(), {}, show)
        return order

    def test_an_uploaded_episode_goes_from_images_to_a_live_site_in_a_single_pass(self):
        wp = FakeWP(UPLOADED)
        order = self._run(wp, _show(wp))

        self.assertEqual(order, ["images", "captivate", "website", "strip"])
        self.assertEqual(wp.steps["images_rendered"]["status"], "done")
        self.assertEqual(wp.steps["captivate_published"]["status"], "done")
        self.assertEqual(wp.steps["website_published"]["status"], "done")

    def test_the_strip_waits_when_captivate_fails_and_the_website_still_publishes(self):
        wp = FakeWP(UPLOADED)
        order = self._run(wp, _show(wp), captivate_side_effect=RuntimeError("Captivate down"))

        self.assertEqual(order, ["images", "captivate", "website"])
        self.assertEqual(wp.steps["captivate_published"]["status"], "failed")
        self.assertEqual(wp.steps["website_published"]["status"], "done")

    def test_nothing_publishes_without_an_upload(self):
        wp = FakeWP(dict(UPLOADED, audio_received="pending"), finalization={"state": "pending"})
        order = self._run(wp, _show(wp))
        self.assertEqual(order, [])

    def test_a_scheduled_show_renders_images_but_holds_the_publish(self):
        wp = FakeWP(UPLOADED, finalization={"state": "finalized", "finalized_at": "2099-01-01 00:00:00"})
        show = _show(wp, publish_mode="scheduled", publish_time="07:00", publish_timezone="America/New_York")
        # finalized "in the future" stands in for a target moment that has not arrived
        with patch.object(tick, "compute_target_publish_moment", return_value=tick.datetime(2099, 1, 1, tzinfo=tick.timezone.utc)):
            order = self._run(wp, show)
        self.assertEqual(order, ["images"])


class RunPhaseTests(unittest.TestCase):
    def test_a_stage_that_acted_triggers_a_reread_of_the_episodes(self):
        wp = FakeWP(dict(UPLOADED, images_rendered="done"))
        show = _show(wp)
        show["in_flight_episodes"][0]["step_status"]["images_rendered"]["status"] = "pending"

        run_phase(wp, show, "x", lambda: True)

        self.assertEqual(show["in_flight_episodes"][0]["step_status"]["images_rendered"]["status"], "done")

    def test_a_quiet_stage_costs_no_requests(self):
        wp = Mock()
        run_phase(wp, _show(FakeWP(UPLOADED)), "x", lambda: False)
        wp.get_episode.assert_not_called()

    def test_a_failing_stage_is_contained_and_does_not_reread(self):
        wp = Mock()

        def boom():
            raise RuntimeError("boom")

        run_phase(wp, _show(FakeWP(UPLOADED)), "x", boom)  # must not raise
        wp.get_episode.assert_not_called()

    def test_refresh_can_be_forced_for_a_stage_that_changes_episodes_without_saying_so(self):
        wp = FakeWP(UPLOADED)
        show = _show(wp)
        wp.steps["youtube_published"] = {"status": "pending"}
        run_phase(wp, show, "x", lambda: None, refresh=True)
        self.assertEqual(show["in_flight_episodes"][0]["finalization"]["state"], "finalized")

    def test_an_unreadable_episode_keeps_its_old_state(self):
        wp = Mock()
        wp.get_episode.side_effect = RuntimeError("timeout")
        show = _show(FakeWP(UPLOADED))
        before = dict(show["in_flight_episodes"][0]["step_status"])
        refresh_in_flight(wp, show)
        self.assertEqual(show["in_flight_episodes"][0]["step_status"], before)


class StripGateTests(unittest.TestCase):
    def test_refreshes_only_when_captivate_and_website_are_both_live(self):
        for captivate, website, expected in (
            ("done", "done", True),
            ("degraded", "done", True),
            ("done", "pending", False),
            ("failed", "done", False),
            ("pending", "pending", False),
        ):
            wp = FakeWP(dict(UPLOADED, captivate_published=captivate, website_published=website))
            with patch.object(tick, "refresh_signature_strip") as strip:
                refresh_strip_when_live(wp, {"id": 16}, 671)
            self.assertEqual(strip.called, expected, (captivate, website))

    def test_never_raises(self):
        wp = Mock()
        wp.get_episode.side_effect = RuntimeError("timeout")
        refresh_strip_when_live(wp, {"id": 16}, 671)


class HousekeepingTests(unittest.TestCase):
    def test_runs_on_the_five_minute_marks_only(self):
        from datetime import datetime
        self.assertTrue(housekeeping_due(datetime(2026, 11, 2, 17, 0)))
        self.assertTrue(housekeeping_due(datetime(2026, 11, 2, 17, 35)))
        self.assertFalse(housekeeping_due(datetime(2026, 11, 2, 17, 1)))
        self.assertFalse(housekeeping_due(datetime(2026, 11, 2, 17, 44)))

    def test_a_pass_off_the_mark_skips_tagging(self):
        wp = FakeWP(UPLOADED)
        with patch.object(tick, "housekeeping_due", return_value=False), \
             patch.object(tick, "process_photo_tagging") as tagging, \
             patch.object(tick, "process_photo_digest") as digest, \
             patch.object(tick, "process_index_refresh"), \
             patch.object(tick, "process_script_generation"):
            process_show(wp, Mock(), Mock(), Mock(), {}, _show(wp, in_flight_episodes=[]))
        tagging.assert_not_called()
        digest.assert_not_called()


class BusyShowTests(unittest.TestCase):
    def _busy(self, minutes):
        from run_lock import ShowBusy
        return ShowBusy(16, minutes * 60)

    def test_a_normal_overlap_is_only_logged(self):
        with patch.object(tick, "notify_failure") as notify:
            note_busy_show({}, {"id": 16, "name": "Edtech"}, self._busy(3))
        notify.assert_not_called()

    def test_a_hung_pass_is_reported_once(self):
        with patch.object(tick, "notify_failure") as notify:
            note_busy_show({}, {"id": 16, "name": "Edtech"}, self._busy(45.3))
            note_busy_show({}, {"id": 16, "name": "Edtech"}, self._busy(46.5))
            note_busy_show({}, {"id": 16, "name": "Edtech"}, self._busy(120))
        self.assertEqual(notify.call_count, 1)


if __name__ == "__main__":
    unittest.main()
