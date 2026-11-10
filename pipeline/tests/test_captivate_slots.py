"""Ad slots on a new Captivate episode: the dashboard-shaped request on creation, the fallback, and the read-back check
(captivate_client.dashboard_post_roll_slots / slot_problems, tick.publish_to_captivate / check_new_episode_ad_slots)."""
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import captivate_client as cc
import tick

SHOW_ID = "f40bbab2-a721-4bec-9de7-aa82b5488060"
MEDIA = "75f0b334-fc7c-42fd-9748-b11613ddda00"
EPISODE = "acf5ad59-baae-4ce4-bdd9-dd60606e2a8e"

GOOD = [{"id": "a", "type": "post", "slot_type": "dynamic", "total_ad_slots": 3, "subSlots": []}]
STATIC = [{"id": "a", "type": "post", "slot_type": "static", "total_ad_slots": 0,
           "subSlots": [{"media_id": "969c", "media_name": "Edsby 52s Ad Rev A"}]}]


class SlotJudgementTests(unittest.TestCase):
    def test_the_converted_shape_is_accepted(self):
        self.assertEqual(cc.slot_problems(GOOD, 3), [])

    def test_the_static_house_ad_slot_is_reported(self):
        problems = cc.slot_problems(STATIC, 3)
        self.assertTrue(any("static, not dynamic" in p for p in problems))
        self.assertTrue(any("Edsby 52s Ad Rev A" in p for p in problems))

    def test_two_post_roll_slots_are_reported(self):
        self.assertTrue(any("2 post-roll slots" in p for p in cc.slot_problems(GOOD + GOOD, 3)))

    def test_a_wrong_position_count_is_reported(self):
        slots = [dict(GOOD[0], total_ad_slots=1)]
        self.assertTrue(any("1 ad positions, expected 3" in p for p in cc.slot_problems(slots, 3)))

    def test_an_extra_pre_roll_is_reported(self):
        pre = {"type": "pre", "slot_type": "dynamic", "total_ad_slots": 0, "subSlots": []}
        self.assertTrue(any("pre-roll" in p for p in cc.slot_problems(GOOD + [pre], 3)))

    def test_no_slots_at_all_is_reported(self):
        self.assertEqual(cc.slot_problems([], 3), ["it has no ad slots at all"])


class SlotRequestTests(unittest.TestCase):
    def test_a_v2_show_gets_its_default_count(self):
        self.assertEqual(cc.v2_post_roll_count({"show": {"amie_version": 2, "default_post_roll_slots": 3}}), 3)
        self.assertEqual(cc.v2_post_roll_count({"amie_version": 2, "default_post_roll_slots": "3"}), 3)

    def test_other_shows_get_no_slot_request(self):
        self.assertEqual(cc.v2_post_roll_count({"amie_version": 1, "default_post_roll_slots": 3}), 0)
        self.assertEqual(cc.v2_post_roll_count({"amie_version": 2, "default_post_roll_slots": 0}), 0)
        self.assertEqual(cc.v2_post_roll_count(Mock()), 0)
        self.assertEqual(cc.v2_post_roll_count(None), 0)

    def test_the_slot_is_dynamic_with_no_attached_ad(self):
        slot = cc.dashboard_post_roll_slots(SHOW_ID, MEDIA, 3, "new-id")[0]
        self.assertEqual((slot["type"], slot["slot_type"], slot["total_ad_slots"], slot["adMediaAssignments"]), ("post", "dynamic", 3, []))
        self.assertEqual((slot["parent_media_id"], slot["show_id"], slot["start"], slot["end"]), (MEDIA, SHOW_ID, -1, -1))
        self.assertNotIn("subSlots", slot)

    def test_a_payload_with_slots_goes_as_json_and_one_without_as_a_form(self):
        client = cc.CaptivateClient("u", "t")
        client._request = Mock(return_value={})
        client.create_episode({"title": "x", "slots": [], "dashboard": True})
        self.assertIn("json", client._request.call_args.kwargs)
        client.create_episode({"title": "x"})
        self.assertIn("data", client._request.call_args.kwargs)


def _captivate(show, create_side_effect=None):
    captivate = Mock()
    captivate.get_show.return_value = show
    captivate.upload_media.return_value = MEDIA
    captivate.get_next_episode_number.return_value = 36
    captivate.create_episode.side_effect = create_side_effect or [{"id": EPISODE}]
    captivate.get_episode.return_value = {"id": EPISODE, "title": "T", "media_id": MEDIA, "status": "Published", "published_date": "x"}
    return captivate


def _wp():
    wp = Mock()
    wp.get_episode.return_value = {"meta": {"ng_audio_attachment_id": 1, "ng_meta_captivate_title": "T", "ng_meta_captivate_notes": ""},
                                   "title": {"rendered": "T"}}
    wp.get_attachment_url.return_value = "https://x/a.mp3"
    wp.download_binary.return_value = b"audio"
    return wp


def _publish(captivate, wp=None):
    show = {"name": "Net Gain Edtech", "captivate_show_id": SHOW_ID}
    with patch.object(tick, "convert_to_captivate_bitrate", side_effect=lambda b: b), \
         patch.object(tick, "record_audio_seconds"), \
         patch.object(tick, "compute_captivate_date_field", return_value="2026-11-11 04:00:00"):
        return tick.publish_to_captivate(wp or _wp(), captivate, show, 710, {})


V2_SHOW = {"show": {"amie_version": 2, "default_post_roll_slots": 3, "time_zone": "America/Vancouver"}}


class PublishSendsSlotsTests(unittest.TestCase):
    def test_a_v2_show_creates_the_episode_with_a_dynamic_post_roll(self):
        captivate = _captivate(V2_SHOW)
        _publish(captivate)
        payload = captivate.create_episode.call_args.args[0]
        self.assertTrue(payload["dashboard"])
        self.assertEqual(len(payload["slots"]), 1)
        self.assertEqual((payload["slots"][0]["slot_type"], payload["slots"][0]["total_ad_slots"], payload["slots"][0]["parent_media_id"]),
                         ("dynamic", 3, MEDIA))

    def test_a_show_not_on_v2_is_created_exactly_as_before(self):
        captivate = _captivate({"show": {"amie_version": 1, "default_post_roll_slots": 3}})
        _publish(captivate)
        payload = captivate.create_episode.call_args.args[0]
        self.assertNotIn("slots", payload)
        self.assertNotIn("dashboard", payload)

    def test_a_4xx_on_the_slot_data_falls_back_to_the_old_creation(self):
        captivate = _captivate(V2_SHOW, [cc.CaptivateError("POST /episodes failed (400): bad slot", 400), {"id": EPISODE}])
        _publish(captivate)
        self.assertEqual(captivate.create_episode.call_count, 2)
        self.assertNotIn("slots", captivate.create_episode.call_args.args[0])

    def test_a_server_error_is_not_retried_without_slots(self):
        captivate = _captivate(V2_SHOW, [cc.CaptivateError("boom", 500)])
        with self.assertRaises(cc.CaptivateError):
            _publish(captivate)
        self.assertEqual(captivate.create_episode.call_count, 1)

    def test_an_error_with_no_status_is_not_retried_without_slots(self):
        captivate = _captivate(V2_SHOW, [cc.CaptivateError("no answer")])
        with self.assertRaises(cc.CaptivateError):
            _publish(captivate)
        self.assertEqual(captivate.create_episode.call_count, 1)


class ReadBackCheckTests(unittest.TestCase):
    def _run(self, slots, show=V2_SHOW):
        captivate = _captivate(show)
        captivate.get_media_slots.return_value = slots
        wp = Mock()
        wp.get_episode.return_value = {"meta": {"ng_url_captivate": f"https://player.captivate.fm/episode/{EPISODE}"}}
        with patch.object(tick, "notify_failure") as notify:
            ok = tick.check_new_episode_ad_slots(wp, captivate, {}, {"name": "Net Gain Edtech", "captivate_show_id": SHOW_ID}, 710)
        return ok, notify

    def test_correct_slots_raise_no_alert(self):
        ok, notify = self._run(GOOD)
        self.assertTrue(ok)
        notify.assert_not_called()

    def test_static_slots_alert_the_operator_with_the_details(self):
        ok, notify = self._run(STATIC)
        self.assertFalse(ok)
        notify.assert_called_once()
        step, message = notify.call_args.args[2], notify.call_args.args[3]
        self.assertEqual(step, "captivate_ad_slots")
        self.assertIn(EPISODE, message)
        self.assertIn("static", message)
        self.assertIn("3 positions", message)

    def test_a_show_not_on_v2_is_not_checked(self):
        ok, notify = self._run(STATIC, show={"show": {"amie_version": 1}})
        self.assertTrue(ok)
        notify.assert_not_called()

    def test_a_failing_read_alerts_and_never_raises(self):
        captivate = _captivate(V2_SHOW)
        captivate.get_media_slots.side_effect = RuntimeError("down")
        wp = Mock()
        wp.get_episode.return_value = {"meta": {"ng_url_captivate": f"https://player.captivate.fm/episode/{EPISODE}"}}
        with patch.object(tick, "notify_failure") as notify:
            ok = tick.check_new_episode_ad_slots(wp, captivate, {}, {"name": "N", "captivate_show_id": SHOW_ID}, 710)
        self.assertFalse(ok)
        self.assertIn("could not run", notify.call_args.args[3])


if __name__ == "__main__":
    unittest.main()
