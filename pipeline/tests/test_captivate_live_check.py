"""The alert for an episode Captivate does not show as Published a few minutes after it was handed over (tick.process_captivate_live_check)."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alert_memory
import tick

CAPTIVATE_ID = "fbe1d28d-08ea-4669-a8a4-c199fe796ac2"
HANDED_OVER = "2026-11-05 21:58:35"                       # the step's 'at': site-local, and the test show's site zone is UTC


def _show(episodes, **extra):
    return dict({"id": 16, "name": "Net Gain Edtech", "publish_mode": "immediate", "site_timezone": "UTC",
                 "in_flight_episodes": episodes}, **extra)


def _episode(step_status="done", at=HANDED_OVER, finalized_at="2026-11-05 21:55:00", state="finalized"):
    return {"id": 690, "step_status": {"captivate_published": {"status": step_status, "at": at}},
            "finalization": {"state": state, "finalized_at": finalized_at}}


def _wp(url=f"https://player.captivate.fm/episode/{CAPTIVATE_ID}"):
    wp = Mock()
    wp.get_episode.return_value = {"meta": {"ng_url_captivate": url} if url else {}}
    return wp


def _captivate(status="Scheduled", date="2026/11/05 14:56:33"):
    captivate = Mock()
    captivate.get_episode.return_value = {"episode": {"id": CAPTIVATE_ID, "status": status, "published_date": date}}
    return captivate


class LiveCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.path = os.path.join(self.directory, "alerts.json")

        class Memory:
            already_sent = staticmethod(lambda key: alert_memory.already_sent(key, self.path))
            mark_sent = staticmethod(lambda key: alert_memory.mark_sent(key, self.path))

        self.memory = Memory
        self.notify = Mock()
        self._real_notify = tick.notify_failure
        tick.notify_failure = self.notify

    def tearDown(self):
        tick.notify_failure = self._real_notify

    def _check(self, show, wp, captivate, minutes_after):
        now = datetime(2026, 11, 5, 21, 58, 35, tzinfo=timezone.utc)
        return tick.process_captivate_live_check(wp, captivate, {}, show, now=now + timedelta(minutes=minutes_after), memory=self.memory)

    def test_nothing_is_read_from_captivate_before_the_grace_period_ends(self):
        captivate = _captivate()
        self._check(_show([_episode()]), _wp(), captivate, minutes_after=2)
        captivate.get_episode.assert_not_called()
        self.notify.assert_not_called()

    def test_an_episode_still_scheduled_after_the_grace_period_is_reported_once(self):
        captivate, show, wp = _captivate("Scheduled"), _show([_episode()]), _wp()
        self._check(show, wp, captivate, minutes_after=4)
        self.notify.assert_called_once()
        message = self.notify.call_args.args[3]
        self.assertEqual(self.notify.call_args.args[1:3], ("Net Gain Edtech", "captivate_live"))
        self.assertIn("Scheduled", message)
        self.assertIn(CAPTIVATE_ID, message)
        self.assertIn("not in the podcast feed", message)
        self._check(show, wp, captivate, minutes_after=5)
        self._check(show, wp, captivate, minutes_after=30)
        self.notify.assert_called_once()

    def test_an_episode_that_is_published_raises_no_alert_and_is_not_read_again(self):
        captivate, show, wp = _captivate("Published"), _show([_episode()]), _wp()
        self._check(show, wp, captivate, minutes_after=4)
        self._check(show, wp, captivate, minutes_after=5)
        self.notify.assert_not_called()
        self.assertEqual(captivate.get_episode.call_count, 1)

    def test_a_scheduled_release_is_not_checked_until_its_own_publish_time_has_passed(self):
        # Handed to Captivate long ago for a 07:00 Eastern release tomorrow: a Scheduled status is exactly right until then.
        show = _show([_episode(finalized_at="2026-11-05 21:00:00")], publish_mode="scheduled", publish_time="07:00",
                     publish_timezone="America/New_York")
        captivate = _captivate("Scheduled")
        self._check(show, _wp(), captivate, minutes_after=40)
        captivate.get_episode.assert_not_called()
        self.notify.assert_not_called()

    def test_a_scheduled_release_that_does_not_go_live_after_its_time_is_reported(self):
        show = _show([_episode(finalized_at="2026-11-05 21:00:00")], publish_mode="scheduled", publish_time="07:00",
                     publish_timezone="America/New_York")
        captivate, wp = _captivate("Scheduled"), _wp()
        now = datetime(2026, 11, 6, 12, 5, 0, tzinfo=timezone.utc)       # 07:05 Eastern, five minutes after the release time
        tick.process_captivate_live_check(wp, captivate, {}, show, now=now, memory=self.memory)
        self.notify.assert_called_once()

    def test_episodes_whose_captivate_step_is_not_done_are_ignored(self):
        captivate = _captivate()
        for step_status in ("pending", "in_progress", "failed"):
            self._check(_show([_episode(step_status=step_status)]), _wp(), captivate, minutes_after=10)
        captivate.get_episode.assert_not_called()
        self.notify.assert_not_called()

    def test_no_recorded_captivate_id_is_skipped_quietly(self):
        captivate = _captivate()
        self._check(_show([_episode()]), _wp(url=""), captivate, minutes_after=10)
        captivate.get_episode.assert_not_called()
        self.notify.assert_not_called()

    def test_a_failing_read_never_raises_and_does_not_alert(self):
        captivate = _captivate()
        captivate.get_episode.side_effect = RuntimeError("Captivate down")
        self.assertFalse(self._check(_show([_episode()]), _wp(), captivate, minutes_after=10))
        self.notify.assert_not_called()

    def test_a_failure_to_sign_in_never_raises(self):
        captivate = _captivate()
        captivate.ensure_authenticated.side_effect = RuntimeError("401")
        self.assertFalse(self._check(_show([_episode()]), _wp(), captivate, minutes_after=10))

    def test_a_malformed_timestamp_on_one_episode_does_not_stop_the_others(self):
        good = dict(_episode(), id=691)
        bad = dict(_episode(at="not a time"), id=690)
        wp = Mock()
        wp.get_episode.return_value = {"meta": {"ng_url_captivate": f"https://player.captivate.fm/episode/{CAPTIVATE_ID}"}}
        self._check(_show([bad, good]), wp, _captivate("Scheduled"), minutes_after=10)
        self.notify.assert_called_once()

    def test_the_operator_is_still_told_when_the_alert_cannot_be_remembered(self):
        class Unwritable:
            already_sent = staticmethod(lambda key: False)

            @staticmethod
            def mark_sent(key):
                raise OSError("read-only file system")

        now = datetime(2026, 11, 5, 22, 5, 0, tzinfo=timezone.utc)
        tick.process_captivate_live_check(_wp(), _captivate("Scheduled"), {}, _show([_episode()]), now=now, memory=Unwritable)
        self.notify.assert_called_once()


class AlertMemoryTests(unittest.TestCase):
    def test_remembers_a_key_and_drops_old_ones(self):
        path = os.path.join(tempfile.mkdtemp(), "state", "alerts.json")
        self.assertFalse(alert_memory.already_sent("a", path))
        alert_memory.mark_sent("a", path, now=1000)
        self.assertTrue(alert_memory.already_sent("a", path))
        alert_memory.mark_sent("b", path, now=1000 + alert_memory.RETAIN_SECONDS + 5)
        self.assertFalse(alert_memory.already_sent("a", path))
        self.assertTrue(alert_memory.already_sent("b", path))

    def test_an_unreadable_file_reads_as_nothing_sent(self):
        path = os.path.join(tempfile.mkdtemp(), "alerts.json")
        with open(path, "w") as handle:
            handle.write("{not json")
        self.assertFalse(alert_memory.already_sent("a", path))
        alert_memory.mark_sent("a", path)
        self.assertTrue(alert_memory.already_sent("a", path))


if __name__ == "__main__":
    unittest.main()
