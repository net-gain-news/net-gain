"""The Kit steps in the tick loop (tick.py): when the daily email is due, making it exactly once, and the weekly roundup."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tick
from kit_client import KitError
import kit_email

PAGE = "https://netgain.news/edtech/australia-curbs-school-ai/"
WEBSITE_AT = "2026-11-06 21:44:06"          # step 'at' values are site-local; the test show's site zone is UTC
NOW = datetime(2026, 11, 6, 21, 50, 0, tzinfo=timezone.utc)

KIT = {"enabled": True, "since": "2026-11-06 00:00:00", "daily_tag_id": 23806689, "daily_template_id": 5595805,
       "from_email": "news@netgain.news", "weekly_day": "mon", "weekly_time": "08:00", "weekly_timezone": "America/New_York",
       "weekly_tag_id": 23806691, "weekly_template_id": 5595806, "weekly_last_slot": "2026-11-02T08:00:00-05:00",
       "feed_url": "https://netgain.news/series/edtech/feed/ng-email/"}


def _show(**over):
    show = {"id": 16, "name": "Net Gain Edtech", "site_timezone": "UTC", "youtube_channel_id": "UC123", "kit": dict(KIT),
            "pending_actions": []}
    show.update(over)
    return show


def _episode(website_at=WEBSITE_AT, youtube="done", kit="pending", website="done", state="finalized"):
    steps = {"website_published": {"status": website, "at": website_at}, "youtube_published": {"status": youtube, "at": website_at},
             "kit_emailed": {"status": kit}}
    return {"id": 696, "episode_date": "2026-11-06", "step_status": steps, "finalization": {"state": state}}


def _item(link=PAGE, title="Australia Curbs School AI", published=datetime(2026, 11, 6, 21, 44, 6, tzinfo=timezone.utc)):
    return {"title": title, "link": link, "published": published, "summary": "Summary.", "daily_card": "<table>DAILY</table>",
            "compact_card": "<table>COMPACT</table>"}


def _force(show):
    show["pending_actions"] = [{"id": "a1", "action": "send_kit_email", "status": "pending", "episode_date": "2026-11-06", "force": True}]
    return show


class KitEmailDueTests(unittest.TestCase):
    def due(self, show=None, episode=None, now=NOW):
        return tick.kit_email_due(show or _show(), episode or _episode(), now=now)

    def test_due_once_the_website_is_live_and_youtube_has_finished(self):
        self.assertTrue(self.due())

    def test_not_due_when_kit_sending_is_off(self):
        self.assertFalse(self.due(show=_show(kit=dict(KIT, enabled=False))))
        self.assertFalse(self.due(show={"id": 1, "name": "x", "site_timezone": "UTC"}))

    def test_finished_and_failed_emails_are_not_made_again_by_themselves(self):
        for status in ("done", "degraded", "failed"):
            self.assertFalse(self.due(episode=_episode(kit=status)), status)

    def test_a_manual_request_retries_a_failed_email(self):
        self.assertTrue(self.due(show=_force(_show()), episode=_episode(kit="failed")))

    def test_a_manual_request_for_another_day_does_not_count(self):
        show = _force(_show())
        show["pending_actions"][0]["episode_date"] = "2026-11-05"
        self.assertFalse(self.due(show=show, episode=_episode(kit="failed")))

    def test_waits_for_the_episode_to_be_finalized_and_the_website_to_be_live(self):
        self.assertFalse(self.due(episode=_episode(state="draft")))
        self.assertFalse(self.due(episode=_episode(website="pending")))
        self.assertFalse(self.due(episode=_episode(website="failed")))
        self.assertTrue(self.due(episode=_episode(website="degraded")))

    def test_an_episode_that_went_live_before_sending_was_switched_on_is_never_emailed(self):
        self.assertFalse(self.due(show=_show(kit=dict(KIT, since="2026-11-06 22:00:00"))))
        self.assertFalse(self.due(show=_show(kit=dict(KIT, since=""))))
        self.assertTrue(self.due(show=_force(_show(kit=dict(KIT, since="2026-11-06 22:00:00")))))

    def test_it_waits_for_youtube_to_finish_or_fail_with_no_timer_of_its_own(self):
        self.assertFalse(self.due(episode=_episode(youtube="in_progress")))
        self.assertFalse(self.due(episode=_episode(youtube="pending")))
        # No fixed wait: hours later it is still waiting for YouTube's own outcome, not sending on a clock.
        self.assertFalse(self.due(episode=_episode(youtube="in_progress"), now=NOW + timedelta(hours=3)))

    def test_a_failed_or_degraded_youtube_does_not_hold_the_email(self):
        self.assertTrue(self.due(episode=_episode(youtube="failed")))
        self.assertTrue(self.due(episode=_episode(youtube="degraded")))

    def test_a_show_with_no_youtube_channel_does_not_wait(self):
        self.assertTrue(self.due(show=_show(youtube_channel_id=""), episode=_episode(youtube="pending")))

    def test_a_manual_request_does_not_wait_for_youtube(self):
        self.assertTrue(self.due(show=_force(_show()), episode=_episode(youtube="in_progress")))


class SendEpisodeEmailTests(unittest.TestCase):
    def setUp(self):
        self.wp = Mock()
        self.wp.get_episode.return_value = {"meta": {"ng_url_website": PAGE, "ng_episode_date": "2026-11-06"}}
        self.kit_client = Mock()
        self.kit_client.find_broadcast.return_value = None
        self.kit_client.create_broadcast.return_value = {"id": 555}
        self.notify = Mock()
        self._real_notify = tick.notify_failure
        tick.notify_failure = self.notify
        patcher = patch("tick.kit_email.fetch_feed", return_value=[_item()])
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        tick.notify_failure = self._real_notify

    def send(self, show=None, episode=None, pending=(), now=NOW, kit_client="default"):
        show = show or _show()
        tick.send_episode_email(self.wp, self.kit_client if kit_client == "default" else kit_client, {}, show,
                                episode or _episode(), list(pending), now=now)

    def steps(self):
        return [c.args[2] for c in self.wp.update_step.call_args_list]

    def test_makes_the_email_once_and_records_it(self):
        self.send()
        self.kit_client.create_broadcast.assert_called_once()
        kwargs = self.kit_client.create_broadcast.call_args.kwargs
        self.assertEqual(kwargs["subject"], "Australia Curbs School AI")
        self.assertEqual(kwargs["tag_id"], 23806689)
        self.assertEqual(kwargs["template_id"], 5595805)
        self.assertEqual(kwargs["content"], "<table>DAILY</table>")
        self.assertEqual(kwargs["send_at"], "2026-11-06T21:51:30Z")
        self.assertEqual(self.steps(), ["in_progress", "done"])
        self.wp.update_episode_meta.assert_called_once_with(696, {"ng_kit_broadcast_id": "555"})
        self.notify.assert_not_called()

    def test_it_looks_for_its_own_earlier_email_by_marker_first(self):
        self.send()
        self.kit_client.find_broadcast.assert_called_once_with("[ng-ep-696]")

    def test_an_email_already_in_kit_is_adopted_and_never_made_twice(self):
        self.kit_client.find_broadcast.return_value = {"id": 9, "status": "scheduled"}
        self.send()
        self.kit_client.create_broadcast.assert_not_called()
        self.fetch.assert_not_called()
        self.assertEqual(self.steps(), ["done"])
        self.assertIn("Already in Kit", self.wp.update_step.call_args.kwargs["note"])
        self.wp.update_episode_meta.assert_called_once_with(696, {"ng_kit_broadcast_id": "9"})

    def test_an_unsent_draft_for_the_episode_is_reported_not_sent_over(self):
        self.kit_client.find_broadcast.return_value = {"id": 9, "status": "draft"}
        self.send()
        self.kit_client.create_broadcast.assert_not_called()
        self.assertEqual(self.steps(), ["failed"])
        self.notify.assert_called_once()

    def test_a_manual_request_is_marked_done_when_handled(self):
        show = _force(_show())
        self.send(show=show, pending=show["pending_actions"])
        self.wp.update_action.assert_called_once_with(16, "a1", "done")

    def test_a_manual_request_for_an_email_already_sent_makes_no_second_one(self):
        self.kit_client.find_broadcast.return_value = {"id": 9, "status": "completed"}
        show = _force(_show())
        self.send(show=show, episode=_episode(kit="done"), pending=show["pending_actions"])
        self.kit_client.create_broadcast.assert_not_called()
        self.wp.update_action.assert_called_once_with(16, "a1", "done")

    def test_feed_not_listing_the_page_yet_is_retried_quietly(self):
        self.fetch.return_value = [_item(link="https://netgain.news/edtech/another/")]
        self.send()
        self.kit_client.create_broadcast.assert_not_called()
        self.wp.update_step.assert_not_called()
        self.notify.assert_not_called()

    def test_feed_still_not_listing_the_page_after_the_window_is_reported(self):
        self.fetch.return_value = []
        self.send(now=NOW + timedelta(minutes=30))
        self.assertEqual(self.steps(), ["failed"])
        self.notify.assert_called_once()
        self.assertIn("does not list", self.notify.call_args.args[3])

    def test_a_kit_outage_is_retried_and_the_step_put_back_to_pending(self):
        self.kit_client.create_broadcast.side_effect = KitError("Could not reach Kit", transient=True)
        self.send()
        self.assertEqual(self.steps(), ["in_progress", "pending"])
        self.notify.assert_not_called()

    def test_the_retry_window_is_ten_minutes_from_when_the_email_became_due(self):
        self.assertEqual(tick.KIT_RETRY_WINDOW_MINUTES, 10)
        self.fetch.return_value = []
        self.send(now=datetime(2026, 11, 6, 21, 53, 0, tzinfo=timezone.utc))     # 9 minutes after the page went live
        self.notify.assert_not_called()
        self.send(now=datetime(2026, 11, 6, 21, 55, 0, tzinfo=timezone.utc))     # 11 minutes after
        self.notify.assert_called_once()

    def test_the_window_counts_from_youtube_finishing_when_that_is_later(self):
        episode = _episode()
        episode["step_status"]["youtube_published"]["at"] = "2026-11-06 22:10:00"      # YouTube settled 26 minutes after the page
        self.fetch.return_value = []
        self.send(episode=episode, now=datetime(2026, 11, 6, 22, 16, 0, tzinfo=timezone.utc))   # 6 minutes after YouTube
        self.notify.assert_not_called()
        self.send(episode=episode, now=datetime(2026, 11, 6, 22, 21, 0, tzinfo=timezone.utc))   # 11 minutes after YouTube
        self.notify.assert_called_once()

    def test_a_failed_youtube_still_lets_the_email_go_out(self):
        episode = _episode(youtube="failed")
        self.assertTrue(tick.kit_email_due(_show(), episode, now=NOW))
        self.send(episode=episode)
        self.kit_client.create_broadcast.assert_called_once()

    def test_a_kit_outage_that_outlasts_the_window_is_reported(self):
        self.kit_client.find_broadcast.side_effect = KitError("Kit GET /broadcasts returned 503", status=503, transient=True)
        self.send(now=NOW + timedelta(minutes=30))
        self.assertEqual(self.steps(), ["failed"])
        self.notify.assert_called_once()

    def test_a_rejected_email_fails_at_once_with_kits_message(self):
        self.kit_client.create_broadcast.side_effect = KitError("Kit POST /broadcasts returned 422: template not found", status=422)
        self.send()
        self.assertEqual(self.steps(), ["in_progress", "failed"])
        self.assertIn("template not found", self.notify.call_args.args[3])

    def test_incomplete_settings_fail_without_calling_kit(self):
        self.send(show=_show(kit=dict(KIT, daily_tag_id=0)))
        self.kit_client.find_broadcast.assert_not_called()
        self.assertEqual(self.steps(), ["failed"])
        self.assertIn("daily Kit tag ID", self.notify.call_args.args[3])

    def test_a_missing_api_key_fails_loudly(self):
        self.send(kit_client=None)
        self.assertEqual(self.steps(), ["failed"])
        self.assertIn("KIT_API_KEY", self.notify.call_args.args[3])

    def test_an_episode_far_too_old_is_not_emailed_automatically(self):
        self.send(now=NOW + timedelta(hours=40))
        self.kit_client.create_broadcast.assert_not_called()
        self.assertEqual(self.steps(), ["failed"])
        self.assertIn("too late", self.notify.call_args.args[3])

    def test_a_manual_request_sends_even_a_stale_episode(self):
        show = _force(_show())
        self.fetch.return_value = [_item()]
        self.send(show=show, pending=show["pending_actions"], now=NOW + timedelta(hours=40))
        self.kit_client.create_broadcast.assert_called_once()

    def test_a_failure_to_record_the_broadcast_id_does_not_undo_a_sent_email(self):
        self.wp.update_episode_meta.side_effect = RuntimeError("WordPress down")
        self.send()
        self.assertEqual(self.steps(), ["in_progress", "done"])
        self.notify.assert_not_called()

    def test_it_never_raises(self):
        self.wp.get_episode.side_effect = RuntimeError("boom")
        self.send()    # no exception
        self.assertEqual(self.steps(), ["failed"])


class ProcessKitEmailsTests(unittest.TestCase):
    def test_only_due_episodes_are_sent(self):
        due, not_due = _episode(), dict(_episode(kit="done"), id=700)
        show = _show(in_flight_episodes=[due, not_due])
        with patch("tick.send_episode_email") as send, patch("tick.kit_email_due", side_effect=lambda s, e, **kw: e["id"] == 696):
            self.assertTrue(tick.process_kit_emails(Mock(), Mock(), {}, show))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[4]["id"], 696)

    def test_a_show_with_sending_off_does_nothing(self):
        show = _show(kit=dict(KIT, enabled=False), in_flight_episodes=[_episode()])
        with patch("tick.send_episode_email") as send:
            self.assertFalse(tick.process_kit_emails(Mock(), Mock(), {}, show))
        send.assert_not_called()


class Memory:
    """In-memory stand-in for alert_memory."""
    def __init__(self):
        self.sent = set()

    def already_sent(self, key):
        return key in self.sent

    def mark_sent(self, key):
        self.sent.add(key)


MONDAY_AFTER = datetime(2026, 11, 9, 13, 1, 0, tzinfo=timezone.utc)          # Mon 08:01 EST
WEEK = [_item(link=f"https://x/{d}/", title=f"Ep {d}", published=datetime(2026, 11, d, 21, 45, tzinfo=timezone.utc)) for d in (6, 5, 4, 3, 2)]
SLOT = "2026-11-09T08:00:00-05:00"


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.wp = Mock()
        self.kit_client = Mock()
        self.kit_client.find_broadcast.return_value = None
        self.kit_client.create_broadcast.return_value = {"id": 888}
        self.memory = Memory()
        self.notify = Mock()
        self._real_notify = tick.notify_failure
        tick.notify_failure = self.notify
        patcher = patch("tick.kit_email.fetch_feed", return_value=list(WEEK))
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        tick.notify_failure = self._real_notify

    def run_weekly(self, show=None, now=MONDAY_AFTER, kit_client="default"):
        return tick.process_kit_weekly(self.wp, self.kit_client if kit_client == "default" else kit_client, {}, show or _show(),
                                       now=now, memory=self.memory)

    def marked(self):
        return [c.args[1] for c in self.wp.update_show_meta.call_args_list]

    def test_sends_the_roundup_at_the_slot_and_remembers_it(self):
        self.assertTrue(self.run_weekly())
        self.kit_client.create_broadcast.assert_called_once()
        kwargs = self.kit_client.create_broadcast.call_args.kwargs
        self.assertEqual(kwargs["tag_id"], 23806691)
        self.assertEqual(kwargs["template_id"], 5595806)
        self.assertEqual(kwargs["subject"], "Net Gain Edtech")
        self.assertEqual(kwargs["content"].count("COMPACT"), 5)
        self.assertEqual(self.marked(), [{"ng_kit_weekly_last_slot": SLOT}])
        self.notify.assert_not_called()

    def test_does_not_send_again_in_the_same_slot(self):
        show = _show(kit=dict(KIT, weekly_last_slot=SLOT))
        self.assertFalse(self.run_weekly(show=show))
        self.kit_client.create_broadcast.assert_not_called()

    def test_does_nothing_before_the_slot(self):
        before = datetime(2026, 11, 9, 12, 59, tzinfo=timezone.utc)
        self.assertFalse(self.run_weekly(now=before))
        self.kit_client.create_broadcast.assert_not_called()

    def test_the_first_ever_slot_is_noted_but_nothing_is_sent(self):
        show = _show(kit=dict(KIT, weekly_last_slot=""))
        self.run_weekly(show=show)
        self.kit_client.create_broadcast.assert_not_called()
        self.assertEqual(self.marked(), [{"ng_kit_weekly_last_slot": SLOT}])
        self.notify.assert_not_called()

    def test_a_week_with_no_episodes_sends_nothing_but_moves_on(self):
        self.fetch.return_value = []
        self.run_weekly()
        self.kit_client.create_broadcast.assert_not_called()
        self.assertEqual(self.marked(), [{"ng_kit_weekly_last_slot": SLOT}])

    def test_only_the_weeks_episodes_are_listed(self):
        old = _item(link="https://x/old/", title="Old", published=datetime(2026, 10, 28, 21, 45, tzinfo=timezone.utc))
        self.fetch.return_value = [old] + list(WEEK)
        self.run_weekly()
        self.assertEqual(self.kit_client.create_broadcast.call_args.kwargs["content"].count("COMPACT"), 5)

    def test_a_roundup_already_in_kit_is_adopted_not_repeated(self):
        self.kit_client.find_broadcast.return_value = {"id": 7}
        self.run_weekly()
        self.kit_client.create_broadcast.assert_not_called()
        self.assertEqual(self.marked(), [{"ng_kit_weekly_last_slot": SLOT}])
        self.kit_client.find_broadcast.assert_called_once_with(f"[ng-week-16-{SLOT}]")

    def test_a_slot_the_job_slept_through_is_skipped_and_reported_once(self):
        late = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)          # 15:00 EST, 7 hours after
        self.run_weekly(now=late)
        self.run_weekly(now=late + timedelta(minutes=1), show=_show())
        self.kit_client.create_broadcast.assert_not_called()
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(self.marked()[0], {"ng_kit_weekly_last_slot": SLOT})

    def test_a_kit_outage_is_retried_on_the_next_pass(self):
        self.kit_client.create_broadcast.side_effect = KitError("Could not reach Kit", transient=True)
        self.assertFalse(self.run_weekly())
        self.assertEqual(self.marked(), [])
        self.notify.assert_not_called()

    def test_trouble_still_there_ten_minutes_after_the_slot_is_reported_once_and_retrying_continues(self):
        self.kit_client.create_broadcast.side_effect = KitError("Could not reach Kit", transient=True)
        later = MONDAY_AFTER + timedelta(minutes=10)                          # 08:11, eleven minutes after the slot
        self.assertFalse(self.run_weekly(now=later))
        self.assertFalse(self.run_weekly(now=later + timedelta(minutes=1)))
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(self.marked(), [])
        self.assertIn("10 minutes", self.notify.call_args.args[3])

    def test_the_subject_is_the_shows_own_setting_else_its_name(self):
        self.run_weekly(show=_show(kit=dict(KIT, weekly_subject="Weekly edtech news roundup")))
        self.assertEqual(self.kit_client.create_broadcast.call_args.kwargs["subject"], "Weekly edtech news roundup")
        self.kit_client.create_broadcast.reset_mock()
        self.run_weekly(show=_show(kit=dict(KIT, weekly_subject="  ", weekly_last_slot="2026-11-02T08:00:00-05:00")))
        self.assertEqual(self.kit_client.create_broadcast.call_args.kwargs["subject"], "Net Gain Edtech")

    def test_a_rejected_roundup_is_reported_once_and_not_retried_every_minute(self):
        self.kit_client.create_broadcast.side_effect = KitError("Kit POST /broadcasts returned 422: bad tag", status=422)
        self.run_weekly()
        self.run_weekly()
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(self.marked()[0], {"ng_kit_weekly_last_slot": SLOT})

    def test_a_missing_api_key_is_reported_once_and_nothing_is_marked(self):
        self.run_weekly(kit_client=None)
        self.run_weekly(kit_client=None)
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(self.marked(), [])

    def test_incomplete_settings_are_reported_once(self):
        show = _show(kit=dict(KIT, weekly_template_id=0))
        self.assertFalse(self.run_weekly(show=show))
        self.run_weekly(show=show)
        self.assertEqual(self.notify.call_count, 1)
        self.assertIn("weekly Kit layout template ID", self.notify.call_args.args[3])

    def test_weekly_turned_off_is_silent(self):
        self.assertFalse(self.run_weekly(show=_show(kit=dict(KIT, weekly_day=""))))
        self.notify.assert_not_called()

    def test_with_kit_sending_off_nothing_happens(self):
        self.assertFalse(self.run_weekly(show=_show(kit=dict(KIT, enabled=False))))
        self.kit_client.find_broadcast.assert_not_called()

    def test_it_never_raises(self):
        self.fetch.side_effect = RuntimeError("boom")
        self.assertFalse(self.run_weekly())


if __name__ == "__main__":
    unittest.main()
