import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tick import check_finalizations, finalization_elapsed, script_generation_due


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


if __name__ == "__main__":
    unittest.main()
