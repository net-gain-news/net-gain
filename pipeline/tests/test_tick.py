import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from tick import (
    captivate_publish_due,
    check_finalizations,
    compute_target_publish_moment,
    finalization_elapsed,
    script_generation_due,
    verify_website_publish,
    website_publish_due,
)


class ScriptGenerationDueTests(unittest.TestCase):
    def test_pending_manual_action_wins_regardless_of_schedule(self):
        show = {
            "recording_days": [],
            "target_time": "",
            "pending_actions": [
                {"action": "generate_script", "status": "pending", "episode_date": "2026-09-05"}
            ],
        }
        now_local = datetime(2026, 9, 7, 3, 0, tzinfo=ZoneInfo("UTC"))  # a day not in recording_days
        episode_date, pending = script_generation_due(show, "2026-09-07", now_local)
        self.assertEqual(episode_date, "2026-09-05")
        self.assertEqual(len(pending), 1)

    def test_ignores_non_pending_actions(self):
        show = {
            "recording_days": [],
            "target_time": "",
            "pending_actions": [{"action": "generate_script", "status": "done", "episode_date": "2026-09-05"}],
        }
        now_local = datetime(2026, 9, 7, 3, 0, tzinfo=ZoneInfo("UTC"))
        episode_date, pending = script_generation_due(show, "2026-09-07", now_local)
        self.assertIsNone(episode_date)

    def test_due_on_recording_day_after_target_time(self):
        # 2026-09-07 is a Monday.
        show = {"recording_days": ["mon"], "target_time": "08:00", "pending_actions": []}
        now_local = datetime(2026, 9, 7, 9, 0, tzinfo=ZoneInfo("UTC"))
        episode_date, pending = script_generation_due(show, "2026-09-07", now_local)
        self.assertEqual(episode_date, "2026-09-07")
        self.assertEqual(pending, [])

    def test_not_due_before_target_time(self):
        show = {"recording_days": ["mon"], "target_time": "08:00", "pending_actions": []}
        now_local = datetime(2026, 9, 7, 7, 0, tzinfo=ZoneInfo("UTC"))
        episode_date, _ = script_generation_due(show, "2026-09-07", now_local)
        self.assertIsNone(episode_date)

    def test_not_due_on_a_non_recording_day(self):
        # 2026-09-08 is a Tuesday.
        show = {"recording_days": ["mon"], "target_time": "08:00", "pending_actions": []}
        now_local = datetime(2026, 9, 8, 9, 0, tzinfo=ZoneInfo("UTC"))
        episode_date, _ = script_generation_due(show, "2026-09-08", now_local)
        self.assertIsNone(episode_date)


def _gmt_mysql(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class FinalizationElapsedTests(unittest.TestCase):
    def test_not_elapsed_when_not_counting_down(self):
        self.assertFalse(finalization_elapsed({"state": "finalized"}))
        self.assertFalse(finalization_elapsed({"state": "pending"}))
        self.assertFalse(finalization_elapsed({}))

    def test_not_elapsed_within_window(self):
        started = _gmt_mysql(datetime.now(timezone.utc) - timedelta(seconds=30))
        finalization = {"state": "counting_down", "countdown_started_at": started, "countdown_seconds": 90}
        self.assertFalse(finalization_elapsed(finalization))

    def test_elapsed_after_window(self):
        started = _gmt_mysql(datetime.now(timezone.utc) - timedelta(seconds=120))
        finalization = {"state": "counting_down", "countdown_started_at": started, "countdown_seconds": 90}
        self.assertTrue(finalization_elapsed(finalization))

    def test_missing_started_at_is_not_elapsed(self):
        self.assertFalse(finalization_elapsed({"state": "counting_down"}))


class CheckFinalizationsTests(unittest.TestCase):
    def test_transitions_elapsed_episode_to_finalized(self):
        started = _gmt_mysql(datetime.now(timezone.utc) - timedelta(seconds=200))

        class FakeWP:
            def __init__(self):
                self.updates = []

            def update_episode_meta(self, episode_id, meta):
                self.updates.append((episode_id, meta))

        wp = FakeWP()
        show = {
            "name": "Net Gain Edtech",
            "in_flight_episodes": [
                {
                    "id": 42,
                    "finalization": {
                        "state": "counting_down",
                        "countdown_started_at": started,
                        "countdown_seconds": 90,
                    },
                }
            ],
        }

        check_finalizations(wp, show)

        self.assertEqual(len(wp.updates), 1)
        episode_id, meta = wp.updates[0]
        self.assertEqual(episode_id, 42)
        self.assertEqual(meta["ng_finalization"]["state"], "finalized")

    def test_leaves_non_elapsed_episode_alone(self):
        started = _gmt_mysql(datetime.now(timezone.utc) - timedelta(seconds=10))

        class FakeWP:
            def update_episode_meta(self, episode_id, meta):
                raise AssertionError("should not be called")

        show = {
            "name": "Net Gain Edtech",
            "in_flight_episodes": [
                {"id": 42, "finalization": {"state": "counting_down", "countdown_started_at": started, "countdown_seconds": 90}}
            ],
        }

        check_finalizations(FakeWP(), show)  # must not raise


class ComputeTargetPublishMomentTests(unittest.TestCase):
    def test_immediate_mode_returns_finalized_at(self):
        finalized_at = datetime(2026, 9, 7, 20, 0, tzinfo=timezone.utc)
        show = {"publish_mode": "immediate"}
        finalization = {"finalized_at": _gmt_mysql(finalized_at)}
        self.assertEqual(compute_target_publish_moment(show, finalization), finalized_at)

    def test_scheduled_same_day_when_finalized_before_publish_time(self):
        # 09:00 UTC = 05:00 Eastern (EDT, UTC-4) - before 07:00 Eastern, so the
        # target should be that same Eastern calendar day, not roll to the next.
        finalized_at = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
        show = {"publish_mode": "scheduled", "publish_timezone": "America/New_York", "publish_time": "07:00"}
        finalization = {"finalized_at": _gmt_mysql(finalized_at)}

        target = compute_target_publish_moment(show, finalization)

        expected = datetime(2026, 9, 7, 7, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(target.astimezone(timezone.utc), expected.astimezone(timezone.utc))

    def test_scheduled_next_day_when_finalized_after_publish_time(self):
        # Spec Section 8.2's own example: records Pacific afternoon, publishes
        # 7am Eastern the NEXT day. 20:00 UTC = 16:00 Eastern (EDT), already past 07:00.
        finalized_at = datetime(2026, 9, 7, 20, 0, tzinfo=timezone.utc)
        show = {"publish_mode": "scheduled", "publish_timezone": "America/New_York", "publish_time": "07:00"}
        finalization = {"finalized_at": _gmt_mysql(finalized_at)}

        target = compute_target_publish_moment(show, finalization)

        expected = datetime(2026, 9, 8, 7, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(target.astimezone(timezone.utc), expected.astimezone(timezone.utc))


class CaptivatePublishDueTests(unittest.TestCase):
    def _episode(self, state="finalized", captivate_status="pending", finalized_seconds_ago=3600):
        finalized_at = _gmt_mysql(datetime.now(timezone.utc) - timedelta(seconds=finalized_seconds_ago))
        return {
            "id": 42,
            "finalization": {"state": state, "finalized_at": finalized_at},
            "step_status": {"captivate_published": {"status": captivate_status}},
        }

    def test_not_due_when_not_finalized(self):
        show = {"publish_mode": "immediate", "pending_actions": []}
        episode = self._episode(state="counting_down")
        self.assertFalse(captivate_publish_due(show, episode))

    def test_due_when_finalized_and_immediate_mode(self):
        show = {"publish_mode": "immediate", "pending_actions": []}
        episode = self._episode()
        self.assertTrue(captivate_publish_due(show, episode))

    def test_not_due_again_once_already_published(self):
        show = {"publish_mode": "immediate", "pending_actions": []}
        episode = self._episode(captivate_status="done")
        self.assertFalse(captivate_publish_due(show, episode))

    def test_forced_action_bypasses_already_published_skip(self):
        show = {
            "publish_mode": "immediate",
            "pending_actions": [{"action": "publish_captivate", "status": "pending", "force": True}],
        }
        episode = self._episode(captivate_status="done")
        self.assertTrue(captivate_publish_due(show, episode))

    def test_not_due_when_scheduled_target_is_in_the_future(self):
        # publish_time set 2 hours ahead of right now, so the target is always in
        # the future regardless of what time this test happens to run.
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        show = {
            "publish_mode": "scheduled",
            "publish_timezone": "UTC",
            "publish_time": future.strftime("%H:%M"),
            "pending_actions": [],
        }
        episode = self._episode(finalized_seconds_ago=1)
        self.assertFalse(captivate_publish_due(show, episode))


class WebsitePublishDueTests(unittest.TestCase):
    def _episode(self, state="finalized", website_status="pending", finalized_seconds_ago=3600):
        finalized_at = _gmt_mysql(datetime.now(timezone.utc) - timedelta(seconds=finalized_seconds_ago))
        return {
            "id": 42,
            "finalization": {"state": state, "finalized_at": finalized_at},
            "step_status": {"website_published": {"status": website_status}},
        }

    def test_not_due_when_not_finalized(self):
        show = {"publish_mode": "immediate"}
        episode = self._episode(state="counting_down")
        self.assertFalse(website_publish_due(show, episode))

    def test_due_when_finalized_and_immediate_mode(self):
        show = {"publish_mode": "immediate"}
        episode = self._episode()
        self.assertTrue(website_publish_due(show, episode))

    def test_not_due_again_once_already_published(self):
        show = {"publish_mode": "immediate"}
        episode = self._episode(website_status="done")
        self.assertFalse(website_publish_due(show, episode))

    def test_not_due_when_scheduled_target_is_in_the_future(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        show = {"publish_mode": "scheduled", "publish_timezone": "UTC", "publish_time": future.strftime("%H:%M")}
        episode = self._episode(finalized_seconds_ago=1)
        self.assertFalse(website_publish_due(show, episode))


class VerifyWebsitePublishTests(unittest.TestCase):
    def test_raises_when_no_permalink_returned(self):
        with self.assertRaises(RuntimeError):
            verify_website_publish(None, {})

    @patch("tick.requests.get")
    def test_raises_on_non_200(self, mock_get):
        mock_get.return_value.status_code = 404
        with self.assertRaises(RuntimeError):
            verify_website_publish("https://example.com/shows/x/y/", {})

    @patch("tick.requests.get")
    def test_raises_when_title_missing_from_page(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html><body>something else</body></html>"
        with self.assertRaises(RuntimeError):
            verify_website_publish("https://example.com/shows/x/y/", {"ng_meta_aioseo_title": "Expected Title"})

    @patch("tick.requests.get")
    def test_passes_when_title_present(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html><body>Expected Title</body></html>"
        verify_website_publish("https://example.com/shows/x/y/", {"ng_meta_aioseo_title": "Expected Title"})  # no raise


if __name__ == "__main__":
    unittest.main()
