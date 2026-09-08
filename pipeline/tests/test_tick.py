import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tick import script_generation_due


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


if __name__ == "__main__":
    unittest.main()
