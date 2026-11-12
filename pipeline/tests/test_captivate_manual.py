"""Manual posting to Captivate: the switch, the hand-off email, finding the operator's episode, taking it over, and the guards that
keep API updates (which add a second ad slot) away from episodes posted by hand."""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio_replacement
import captivate_handoff as ch
import captivate_mode as cm
import run_step
import tick

CAP_SHOW = "f40bbab2-a721-4bec-9de7-aa82b5488060"
TITLE = "Microsoft Unveils Classroom as UK Proposes Edtech AI Rules"
WAIT_AT = "2026-11-12 13:00:00"


class Memory:
    def __init__(self):
        self.sent = set()

    def already_sent(self, key):
        return key in self.sent

    def mark_sent(self, key):
        self.sent.add(key)


def show(**extra):
    base = {"id": 16, "name": "Net Gain Edtech", "captivate_show_id": CAP_SHOW, "site_timezone": "UTC", "pending_actions": []}
    base.update(extra)
    return base


def episode(step_status=None):
    return {"id": 716, "step_status": step_status or {}, "finalization": {"state": "finalized"}}


def waiting_step():
    return {"captivate_published": {"status": "in_progress", "at": WAIT_AT, "note": f"{cm.MANUAL_WAIT_NOTE} (the details were emailed to you)."}}


def fakes(captivate_episodes, title=TITLE):
    wp = Mock()
    wp.get_episode.return_value = {"meta": {"ng_meta_captivate_title": title, "ng_episode_date": "2026-11-12"}}
    captivate = Mock()
    captivate.list_episodes.return_value = {"episodes": captivate_episodes}
    return wp, captivate


class SwitchTests(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(cm.is_manual({}, show()))
        self.assertFalse(cm.is_manual({"CAPTIVATE_MANUAL_SHOWS": ""}, show()))
        self.assertFalse(cm.is_manual({"CAPTIVATE_MANUAL_SHOWS": "  "}, show()))

    def test_all_covers_every_show(self):
        self.assertTrue(cm.is_manual({"CAPTIVATE_MANUAL_SHOWS": "ALL"}, show()))

    def test_a_list_matches_the_captivate_id_or_the_wordpress_id(self):
        self.assertTrue(cm.is_manual({"CAPTIVATE_MANUAL_SHOWS": f"abc, {CAP_SHOW.upper()}"}, show()))
        self.assertTrue(cm.is_manual({"CAPTIVATE_MANUAL_SHOWS": "16"}, show()))
        self.assertFalse(cm.is_manual({"CAPTIVATE_MANUAL_SHOWS": "17,other"}, show()))

    def test_waiting_needs_both_the_status_and_the_note(self):
        self.assertTrue(cm.waiting_for_operator(waiting_step()["captivate_published"]))
        self.assertFalse(cm.waiting_for_operator({"status": "in_progress", "note": ""}))
        self.assertFalse(cm.waiting_for_operator({"status": "done", "note": cm.MANUAL_WAIT_NOTE}))
        self.assertFalse(cm.waiting_for_operator(None))


class MatchingTests(unittest.TestCase):
    def test_case_spacing_quotes_and_entities_do_not_matter(self):
        episodes = [{"id": "a", "title": "microsoft  unveils “Classroom” as UK proposes Edtech AI rules"}]
        self.assertEqual(ch.find_posted_episode(episodes, 'Microsoft Unveils "Classroom" as UK Proposes Edtech AI Rules'), episodes)
        self.assertEqual(ch.find_posted_episode([{"id": "b", "title": "AT&amp;T news"}], "AT&T news")[0]["id"], "b")

    def test_a_different_title_does_not_match(self):
        self.assertEqual(ch.find_posted_episode([{"id": "a", "title": "Something else"}], TITLE), [])

    def test_an_empty_title_matches_nothing(self):
        self.assertEqual(ch.find_posted_episode([{"id": "a", "title": ""}], ""), [])

    def test_the_list_comes_out_of_either_response_shape(self):
        self.assertEqual(ch.extract_episodes({"episodes": [{"id": 1}]}), [{"id": 1}])
        self.assertEqual(ch.extract_episodes([{"id": 2}, "junk"]), [{"id": 2}])
        self.assertEqual(ch.extract_episodes({"nothing": 1}), [])


HANDOFF = {
    "show_name": "Net Gain Edtech", "date": "2026-11-12", "title": TITLE, "notes_html": '<p>Notes <a href="https://x.test/a">story</a></p>',
    "audio_url": "https://netgain.news/wp-content/uploads/ep-192k.mp3", "art_url": "https://netgain.news/wp-content/uploads/art.png",
    "episode_number": 37, "publish_now": True, "publish_at": "2026-11-12 12:55:00", "account_zone": "America/Los_Angeles", "check_slots": True,
}


class MessageTests(unittest.TestCase):
    def test_the_hand_off_carries_every_ingredient(self):
        subject, text, page = ch.build_handoff_message(HANDOFF)
        for needle in (TITLE, HANDOFF["audio_url"], HANDOFF["art_url"], "37"):
            self.assertIn(needle, text)
            self.assertIn(needle, page)
        self.assertIn('href="https://x.test/a"', page)          # the notes keep their links in the rendered email
        self.assertIn("story (https://x.test/a)", text)         # and spell them out in the plain version
        self.assertIn("2026-11-12", subject)
        self.assertIn("Publish it now", text)

    def test_a_scheduled_show_gets_the_date_and_zone(self):
        _, text, _ = ch.build_handoff_message(dict(HANDOFF, publish_now=False))
        self.assertIn("2026-11-12 12:55:00 (America/Los_Angeles)", text)

    def test_notes_are_not_escaped_but_the_title_is(self):
        _, _, page = ch.build_handoff_message(dict(HANDOFF, title="A <b> & B"))
        self.assertIn("A &lt;b&gt; &amp; B", page)

    def test_reminders_say_what_is_wrong(self):
        self.assertIn("No episode titled", ch.build_reminder_message("S", "d", TITLE, 20)[1])
        self.assertIn("status is Scheduled", ch.build_reminder_message("S", "d", TITLE, 20, "Scheduled")[1])


class StoreAudioTests(unittest.TestCase):
    def test_the_copy_is_written_and_addressed_and_old_ones_are_removed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            old = os.path.join(folder, "old-192k-aaaa.mp3")
            open(old, "wb").write(b"x")
            os.utime(old, (1, 1))
            keep = os.path.join(folder, "notes.txt")
            open(keep, "w").write("x")
            os.utime(keep, (1, 1))
            config = {"CAPTIVATE_HANDOFF_DIR": folder, "WP_BASE_URL": "https://netgain.news/"}
            url = ch.store_handoff_audio(config, b"mp3-bytes", "ep-2026-11-12")
            name = url.rsplit("/", 1)[-1]
            self.assertTrue(url.startswith("https://netgain.news/wp-content/uploads/captivate-handoff/ep-2026-11-12-192k-"))
            self.assertEqual(open(os.path.join(folder, name), "rb").read(), b"mp3-bytes")
            self.assertFalse(os.path.exists(old))
            self.assertTrue(os.path.exists(keep))

    def test_a_missing_setting_fails_loudly(self):
        with self.assertRaises(RuntimeError):
            ch.store_handoff_audio({"WP_BASE_URL": "https://x"}, b"x", "ep")


class HandoffStartTests(unittest.TestCase):
    def run_start(self, mail_ok=True, meta_done=True):
        wp, captivate = fakes([])
        config = {"CAPTIVATE_MANUAL_SHOWS": "all"}
        ep = episode({"metadata_generated": {"status": "done" if meta_done else "pending"}})
        with patch.object(tick, "prepare_captivate_handoff", return_value=HANDOFF) as prep, \
                patch.object(tick, "send_notice", return_value=mail_ok) as mail, \
                patch.object(tick, "generate_metadata") as gen, \
                patch.object(tick, "notify_failure") as alert:
            tick.publish_episode_to_captivate(wp, Mock(), captivate, config, show(), ep)
        return wp, captivate, prep, mail, gen, alert

    def test_a_ready_episode_is_handed_over_and_nothing_is_created_on_captivate(self):
        wp, captivate, prep, mail, gen, alert = self.run_start()
        mail.assert_called_once()
        wp.update_step.assert_called_once()
        args = wp.update_step.call_args
        self.assertEqual(args.args[:3], (716, "captivate_published", "in_progress"))
        self.assertTrue(args.kwargs["note"].startswith(cm.MANUAL_WAIT_NOTE))
        for method in ("create_episode", "upload_media", "update_episode"):
            getattr(captivate, method).assert_not_called()
        gen.assert_not_called()
        alert.assert_not_called()

    def test_metadata_is_generated_first_when_it_is_missing(self):
        _, _, _, _, gen, _ = self.run_start(meta_done=False)
        gen.assert_called_once()

    def test_an_email_that_cannot_be_sent_fails_the_step_loudly(self):
        wp, _, _, _, _, alert = self.run_start(mail_ok=False)
        self.assertEqual(wp.update_step.call_args.args[:3], (716, "captivate_published", "failed"))
        self.assertTrue(wp.update_step.call_args.kwargs["note"].startswith(tick.HANDOFF_FAILED_NOTE))
        alert.assert_called_once()

    def test_a_failed_hand_off_is_not_retried_every_minute(self):
        wp, captivate = fakes([])
        failed = {"captivate_published": {"status": "failed", "note": f"{tick.HANDOFF_FAILED_NOTE} x"}}
        with patch.object(tick, "prepare_captivate_handoff") as prep:
            tick.publish_episode_to_captivate(wp, Mock(), captivate, {"CAPTIVATE_MANUAL_SHOWS": "all"}, show(), episode(failed))
        prep.assert_not_called()

    def test_a_failure_from_before_manual_mode_still_starts_the_hand_off(self):
        wp, captivate = fakes([])
        failed = {"captivate_published": {"status": "failed", "note": "Captivate rejected the upload"}, "metadata_generated": {"status": "done"}}
        with patch.object(tick, "prepare_captivate_handoff", return_value=HANDOFF) as prep, patch.object(tick, "send_notice", return_value=True):
            tick.publish_episode_to_captivate(wp, Mock(), captivate, {"CAPTIVATE_MANUAL_SHOWS": "all"}, show(), episode(failed))
        prep.assert_called_once()


class OperatorPostTests(unittest.TestCase):
    CONFIG = {"CAPTIVATE_MANUAL_SHOWS": "all"}

    def run_check(self, captivate_episodes, now, memory=None, pending=None):
        wp, captivate = fakes(captivate_episodes)
        memory = memory or Memory()
        with patch.object(tick, "record_audio_seconds") as seconds, patch.object(tick, "check_new_episode_ad_slots") as slots, \
                patch.object(tick, "refresh_strip_when_live") as strip, patch.object(tick, "send_notice", return_value=True) as mail, \
                patch.object(tick, "notify_failure") as alert, patch.object(tick, "alert_memory", memory):
            sh = show(pending_actions=pending or [])
            tick.check_operator_captivate_post(wp, captivate, self.CONFIG, sh, episode(waiting_step()), memory=memory, now=now)
        return wp, captivate, seconds, slots, strip, mail, alert, memory

    def at(self, minute):
        return datetime(2026, 11, 12, 13, minute, tzinfo=timezone.utc)

    def test_a_published_episode_with_the_title_is_taken_over(self):
        pending = [{"id": "act1", "action": "publish_captivate", "status": "pending"}]
        wp, captivate, seconds, slots, strip, mail, alert, _ = self.run_check([{"id": "cap-1", "title": TITLE, "status": "Published"}], self.at(5), pending=pending)
        wp.update_episode_meta.assert_called_once_with(716, {"ng_url_captivate": "https://player.captivate.fm/episode/cap-1"})
        self.assertEqual(wp.update_step.call_args.args[:3], (716, "captivate_published", "done"))
        wp.update_action.assert_called_once_with(16, "act1", "done")
        seconds.assert_called_once()
        slots.assert_called_once()
        self.assertTrue(slots.call_args.kwargs["by_hand"])
        strip.assert_called_once()
        for method in ("create_episode", "update_episode", "upload_media"):
            getattr(captivate, method).assert_not_called()

    def test_an_unpublished_match_is_not_taken_over_and_the_nudge_names_the_status(self):
        wp, _, _, slots, _, mail, _, memory = self.run_check([{"id": "cap-1", "title": TITLE, "status": "Scheduled"}], self.at(20))
        wp.update_step.assert_not_called()
        slots.assert_not_called()
        self.assertIn("Scheduled", mail.call_args.args[2])
        self.assertIn("captivate-handoff-late:716", memory.sent)

    def test_nothing_yet_is_quiet_before_fifteen_minutes(self):
        wp, _, _, _, _, mail, _, _ = self.run_check([], self.at(10))
        wp.update_step.assert_not_called()
        mail.assert_not_called()

    def test_the_operator_is_nudged_once_at_fifteen_and_again_at_sixty_minutes(self):
        memory = Memory()
        _, _, _, _, _, mail, _, _ = self.run_check([], self.at(20), memory=memory)
        self.assertEqual(mail.call_count, 1)
        _, _, _, _, _, mail, _, _ = self.run_check([], self.at(25), memory=memory)
        mail.assert_not_called()
        later = datetime(2026, 11, 12, 14, 5, tzinfo=timezone.utc)
        _, _, _, _, _, mail, _, memory = self.run_check([], later, memory=memory)
        self.assertEqual(mail.call_count, 1)
        self.assertEqual(memory.sent, {"captivate-handoff-late:716", "captivate-handoff-late2:716"})

    def test_two_episodes_with_the_title_are_reported_and_nothing_is_taken_over(self):
        twin = [{"id": "a", "title": TITLE, "status": "Published"}, {"id": "b", "title": TITLE, "status": "Published"}]
        wp, _, _, _, _, _, alert, memory = self.run_check(twin, self.at(5))
        wp.update_step.assert_not_called()
        alert.assert_called_once()
        self.run_check(twin, self.at(6), memory=memory)       # a later pass does not repeat the alert

    def test_a_captivate_error_is_survived(self):
        wp, captivate = fakes([])
        captivate.list_episodes.side_effect = RuntimeError("boom")
        tick.check_operator_captivate_post(wp, captivate, self.CONFIG, show(), episode(waiting_step()), memory=Memory())
        wp.update_step.assert_not_called()


class ForcedPublishTests(unittest.TestCase):
    def test_a_forced_publish_on_an_episode_already_on_captivate_changes_nothing(self):
        wp, captivate = fakes([])
        pending = [{"id": "act1", "action": "publish_captivate", "status": "pending", "force": True}]
        done = {"captivate_published": {"status": "done"}}
        tick.publish_episode_to_captivate(wp, Mock(), captivate, {"CAPTIVATE_MANUAL_SHOWS": "all"}, show(pending_actions=pending), episode(done))
        wp.update_action.assert_called_once_with(16, "act1", "done")
        for method in ("create_episode", "upload_media", "update_episode"):
            getattr(captivate, method).assert_not_called()


class RevertTests(unittest.TestCase):
    def test_switching_back_while_an_episode_waits_adopts_the_operators_episode(self):
        wp, captivate = fakes([{"id": "cap-9", "title": TITLE, "status": "Published"}])
        with patch.object(tick, "record_audio_seconds"), patch.object(tick, "check_new_episode_ad_slots"), patch.object(tick, "refresh_strip_when_live"):
            tick.publish_episode_to_captivate(wp, Mock(), captivate, {}, show(), episode(waiting_step()))
        wp.update_episode_meta.assert_called_once_with(716, {"ng_url_captivate": "https://player.captivate.fm/episode/cap-9"})
        captivate.create_episode.assert_not_called()
        captivate.upload_media.assert_not_called()

    def test_switching_back_with_nothing_posted_publishes_through_the_api_as_before(self):
        wp, captivate = fakes([])
        with patch.object(tick, "publish_to_captivate", return_value=37) as publish, patch.object(tick, "check_new_episode_ad_slots"), \
                patch.object(tick, "refresh_strip_when_live"):
            tick.publish_episode_to_captivate(wp, Mock(), captivate, {}, show(), episode(dict(waiting_step(), metadata_generated={"status": "done"})))
        publish.assert_called_once()
        self.assertEqual(wp.update_step.call_args_list[-1].args[:3], (716, "captivate_published", "done"))

    def test_an_ordinary_automatic_publish_never_looks_for_a_posted_episode(self):
        wp, captivate = fakes([{"id": "cap-9", "title": TITLE, "status": "Published"}])
        with patch.object(tick, "publish_to_captivate", return_value=37), patch.object(tick, "check_new_episode_ad_slots"), \
                patch.object(tick, "refresh_strip_when_live"):
            tick.publish_episode_to_captivate(wp, Mock(), captivate, {}, show(), episode({"metadata_generated": {"status": "done"}}))
        captivate.list_episodes.assert_not_called()


class GuardTests(unittest.TestCase):
    def test_audio_replacement_does_not_touch_captivate_on_a_manual_show(self):
        wp = Mock()
        wp.get_episode.return_value = {"meta": {}}
        sh = show(audio_replacements=[{"episode_id": 716, "destinations": {"captivate": {"status": "pending"}, "youtube": {"status": "done"}}}])
        with patch.object(audio_replacement, "swap_captivate_audio") as swap:
            audio_replacement.process_audio_replacements(wp, Mock(), {"CAPTIVATE_MANUAL_SHOWS": "all"}, sh, Mock())
        swap.assert_not_called()
        self.assertEqual(wp.update_audio_replacement.call_args.args[:3], (716, "captivate", "skipped"))

    def test_run_step_refuses_to_update_a_manually_posted_episode(self):
        wp = Mock()
        wp.get_episode.return_value = {
            "meta": {"ng_url_captivate": "https://player.captivate.fm/episode/x", "ng_step_status": {"audio_received": {"status": "done"}}},
        }
        with patch.object(run_step, "_episode_view", return_value=({"step_status": {"audio_received": {"status": "done"}}}, {"ng_url_captivate": "u"})):
            with self.assertRaises(run_step.StepRefused):
                run_step.run_step("captivate", wp, Mock(), {"CAPTIVATE_MANUAL_SHOWS": "all"}, show(), 716, Mock(), Mock())


if __name__ == "__main__":
    unittest.main()
