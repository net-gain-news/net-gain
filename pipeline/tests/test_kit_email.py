"""The pure rules behind the Kit emails (kit_email.py): feed parsing, payloads, and the weekly schedule."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kit_email

NB = "‑"

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:ng="https://netgain.news/ns/email">
<channel><title>Net Gain Edtech</title>
<item>
<title>Australia Curbs School AI</title>
<link>https://netgain.news/edtech/australia-curbs-school-ai/</link>
<pubDate>Fri, 06 Nov 2026 21:44:06 +0000</pubDate>
<ng:summary><![CDATA[Australia will limit AI and screen time in schools.]]></ng:summary>
<description><![CDATA[<table>COMPACT-FRIDAY</table>]]></description>
<content:encoded><![CDATA[<table>DAILY-FRIDAY</table>]]></content:encoded>
</item>
<item>
<title>Bristol Schools Leak</title>
<link>https://netgain.news/edtech/bristol/</link>
<pubDate>Thu, 05 Nov 2026 22:00:43 +0000</pubDate>
<description><![CDATA[<table>COMPACT-THURSDAY</table>]]></description>
<content:encoded><![CDATA[<table>DAILY-THURSDAY</table>]]></content:encoded>
</item>
<item>
<title>No readable date</title>
<link>https://netgain.news/edtech/bad/</link>
<pubDate>sometime</pubDate>
</item>
</channel></rss>"""

KIT = {"enabled": True, "daily_tag_id": 23806689, "daily_template_id": 5595805, "from_email": "news@netgain.news",
       "weekly_day": "mon", "weekly_time": "08:00", "weekly_timezone": "America/New_York", "weekly_tag_id": 23806691,
       "weekly_template_id": 5595806, "weekly_last_slot": "2026-11-02T08:00:00-05:00",
       "feed_url": "https://netgain.news/series/edtech/feed/ng-email/"}


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class ParseFeedTests(unittest.TestCase):
    def setUp(self):
        self.items = kit_email.parse_feed(FEED)

    def test_items_carry_title_link_time_summary_and_both_cards(self):
        first = self.items[0]
        self.assertEqual(first["title"], "Australia Curbs School AI")
        self.assertEqual(first["published"], utc(2026, 11, 6, 21, 44, 6))
        self.assertEqual(first["summary"], "Australia will limit AI and screen time in schools.")
        self.assertIn("DAILY-FRIDAY", first["daily_card"])
        self.assertIn("COMPACT-FRIDAY", first["compact_card"])

    def test_an_item_without_a_readable_time_is_left_out(self):
        self.assertEqual([i["title"] for i in self.items], ["Australia Curbs School AI", "Bristol Schools Leak"])

    def test_a_feed_without_the_summary_element_still_parses(self):
        self.assertEqual(self.items[1]["summary"], "")

    def test_finds_the_item_for_a_page_with_or_without_a_trailing_slash(self):
        self.assertEqual(kit_email.item_for_page(self.items, "https://netgain.news/edtech/bristol")["title"], "Bristol Schools Leak")
        self.assertEqual(kit_email.item_for_page(self.items, "https://netgain.news/edtech/bristol/")["title"], "Bristol Schools Leak")
        self.assertIsNone(kit_email.item_for_page(self.items, "https://netgain.news/edtech/other/"))
        self.assertIsNone(kit_email.item_for_page(self.items, ""))

    def test_fetch_bypasses_the_cache_and_rejects_errors(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, content=FEED.encode())
        items = kit_email.fetch_feed(KIT["feed_url"], now=utc(2026, 11, 6, 21, 45), session=session)
        self.assertEqual(len(items), 2)
        self.assertIn("cb", session.get.call_args.kwargs["params"])
        session.get.return_value = Mock(status_code=503, content=b"")
        with self.assertRaises(kit_email.KitEmailError):
            kit_email.fetch_feed(KIT["feed_url"], session=session)
        with self.assertRaises(kit_email.KitEmailError):
            kit_email.fetch_feed("")


class PreviewTextTests(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(kit_email.preview_text("Short summary."), "Short summary.")

    def test_long_text_is_cut_at_a_word_with_an_ellipsis_within_the_limit(self):
        text = "word " * 60
        result = kit_email.preview_text(text)
        self.assertLessEqual(len(result), kit_email.PREVIEW_LIMIT)
        self.assertTrue(result.endswith("…"))
        self.assertNotIn("wor…", result)

    def test_whitespace_is_collapsed(self):
        self.assertEqual(kit_email.preview_text("a\n\n  b\t c"), "a b c")

    def test_k12_gets_the_non_breaking_hyphen(self):
        self.assertEqual(kit_email.preview_text("New K-12 rules"), f"New K{NB}12 rules")

    def test_empty_stays_empty(self):
        self.assertEqual(kit_email.preview_text(""), "")
        self.assertEqual(kit_email.preview_text(None), "")


class DailyPayloadTests(unittest.TestCase):
    def setUp(self):
        self.item = kit_email.parse_feed(FEED)[0]
        self.now = utc(2026, 11, 6, 21, 50, 0)

    def test_payload_fields(self):
        payload = kit_email.daily_payload(KIT, "Net Gain Edtech", {"id": 696, "meta": {"ng_episode_date": "2026-11-06"}}, self.item, self.now)
        self.assertEqual(payload["subject"], "Australia Curbs School AI")
        self.assertEqual(payload["content"], "<table>DAILY-FRIDAY</table>")
        self.assertEqual(payload["template_id"], 5595805)
        self.assertEqual(payload["tag_id"], 23806689)
        self.assertEqual(payload["email_address"], "news@netgain.news")
        self.assertEqual(payload["published_at"], "2026-11-06T21:44:06Z")
        self.assertEqual(payload["preview_text"], "Australia will limit AI and screen time in schools.")

    def test_it_is_scheduled_a_moment_ahead_not_thirty_minutes(self):
        payload = kit_email.daily_payload(KIT, "Net Gain Edtech", {"id": 696, "meta": {}}, self.item, self.now)
        self.assertEqual(payload["send_at"], "2026-11-06T21:51:30Z")

    def test_the_description_carries_the_unique_marker(self):
        payload = kit_email.daily_payload(KIT, "Net Gain Edtech", {"id": 696, "meta": {"ng_episode_date": "2026-11-06"}}, self.item, self.now)
        self.assertEqual(payload["description"], "Net Gain Edtech daily 2026-11-06 [ng-ep-696]")
        self.assertIn(kit_email.episode_marker(696), payload["description"])
        self.assertNotIn(kit_email.episode_marker(69), payload["description"])


class SettingsCheckTests(unittest.TestCase):
    def test_complete_daily_settings_have_no_problem(self):
        self.assertIsNone(kit_email.check_daily_settings(KIT))

    def test_missing_pieces_are_named(self):
        message = kit_email.check_daily_settings({"daily_tag_id": 0, "daily_template_id": 5, "feed_url": ""})
        self.assertIn("daily Kit tag ID", message)
        self.assertIn("email feed address", message)
        self.assertNotIn("template", message)

    def test_weekly_off_is_an_empty_string_and_incomplete_is_a_message(self):
        self.assertEqual(kit_email.check_weekly_settings(dict(KIT, weekly_day="")), "")
        self.assertIn("weekly Kit tag ID", kit_email.check_weekly_settings(dict(KIT, weekly_tag_id=0)))
        self.assertIsNone(kit_email.check_weekly_settings(KIT))


class WeeklySlotTests(unittest.TestCase):
    def test_after_the_slot_on_the_day_it_is_this_morning(self):
        slot, previous = kit_email.weekly_slots(KIT, utc(2026, 11, 9, 13, 5))          # Mon 08:05 EST
        self.assertEqual(kit_email.slot_key(slot), "2026-11-09T08:00:00-05:00")
        self.assertEqual(kit_email.slot_key(previous), "2026-11-02T08:00:00-05:00")

    def test_before_the_slot_on_the_day_it_is_last_weeks(self):
        slot, previous = kit_email.weekly_slots(KIT, utc(2026, 11, 9, 12, 59))         # Mon 07:59 EST
        self.assertEqual(kit_email.slot_key(slot), "2026-11-02T08:00:00-05:00")
        # Oct 26 was still daylight time: the clocks went back on Nov 1, and 08:00 stays 08:00 on the wall.
        self.assertEqual(kit_email.slot_key(previous), "2026-10-26T08:00:00-04:00")

    def test_midweek_still_points_at_the_last_monday(self):
        slot, _ = kit_email.weekly_slots(KIT, utc(2026, 11, 12, 20, 0))
        self.assertEqual(kit_email.slot_key(slot), "2026-11-09T08:00:00-05:00")

    def test_the_local_hour_is_kept_across_the_spring_daylight_change(self):
        slot, previous = kit_email.weekly_slots(KIT, utc(2027, 3, 15, 12, 5))          # Mon 08:05 EDT (clocks went forward Mar 14)
        self.assertEqual(kit_email.slot_key(slot), "2027-03-15T08:00:00-04:00")
        self.assertEqual(kit_email.slot_key(previous), "2027-03-08T08:00:00-05:00")
        self.assertEqual(slot.astimezone(timezone.utc), utc(2027, 3, 15, 12, 0))

    def test_the_local_hour_is_kept_across_the_autumn_change_too(self):
        slot, _ = kit_email.weekly_slots(KIT, utc(2026, 11, 2, 13, 5))                 # Mon Nov 2, the day after clocks went back
        self.assertEqual(kit_email.slot_key(slot), "2026-11-02T08:00:00-05:00")

    def test_another_day_and_zone(self):
        kit = dict(KIT, weekly_day="fri", weekly_time="17:30", weekly_timezone="America/Vancouver")
        slot, previous = kit_email.weekly_slots(kit, utc(2026, 11, 7, 2, 0))           # Fri Nov 6 18:00 Vancouver
        self.assertEqual(slot.strftime("%a %H:%M"), "Fri 17:30")
        self.assertEqual((slot - previous), timedelta(days=7))


class WeeklyStateTests(unittest.TestCase):
    def test_due_in_the_minutes_after_the_slot(self):
        state, slot, _ = kit_email.weekly_state(KIT, utc(2026, 11, 9, 13, 1))
        self.assertEqual(state, "due")

    def test_not_due_again_once_handled(self):
        kit = dict(KIT, weekly_last_slot="2026-11-09T08:00:00-05:00")
        self.assertEqual(kit_email.weekly_state(kit, utc(2026, 11, 9, 13, 30))[0], "handled")
        self.assertEqual(kit_email.weekly_state(kit, utc(2026, 11, 12, 13, 30))[0], "handled")

    def test_late_start_within_the_limit_still_sends(self):
        self.assertEqual(kit_email.weekly_state(KIT, utc(2026, 11, 9, 18, 59))[0], "due")

    def test_beyond_the_limit_it_is_missed(self):
        self.assertEqual(kit_email.weekly_state(KIT, utc(2026, 11, 9, 19, 1))[0], "missed")

    def test_the_first_ever_slot_is_a_silent_baseline(self):
        self.assertEqual(kit_email.weekly_state(dict(KIT, weekly_last_slot=""), utc(2026, 11, 9, 13, 1))[0], "baseline")

    def test_unconfigured_or_off_is_off(self):
        self.assertEqual(kit_email.weekly_state(dict(KIT, weekly_day=""), utc(2026, 11, 9, 13, 1))[0], "off")
        self.assertEqual(kit_email.weekly_state(dict(KIT, weekly_tag_id=0), utc(2026, 11, 9, 13, 1))[0], "off")


class WeeklyContentTests(unittest.TestCase):
    def setUp(self):
        self.items = []
        for day, name in ((6, "FRI"), (5, "THU"), (4, "WED"), (3, "TUE"), (2, "MON"), (30, "OLD")):
            published = utc(2026, 11, day, 21, 45) if day < 10 else utc(2026, 10, day, 21, 45)
            self.items.append({"title": name, "link": f"https://x/{name}", "published": published, "summary": f"{name} summary",
                               "daily_card": "", "compact_card": f"<table>{name}</table>"})

    def test_only_the_weeks_episodes_are_included(self):
        slot, previous = kit_email.weekly_slots(KIT, utc(2026, 11, 9, 13, 1))
        week = kit_email.episodes_in_window(self.items, previous, slot)
        self.assertEqual([i["title"] for i in week], ["FRI", "THU", "WED", "TUE", "MON"])

    def test_the_window_includes_its_end_and_excludes_its_start(self):
        slot, previous = kit_email.weekly_slots(KIT, utc(2026, 11, 9, 13, 1))
        edge = [dict(self.items[0], published=slot.astimezone(timezone.utc)), dict(self.items[1], published=previous.astimezone(timezone.utc))]
        self.assertEqual(len(kit_email.episodes_in_window(edge, previous, slot)), 1)

    def test_the_body_stacks_the_cards_in_order_inside_one_table(self):
        body = kit_email.weekly_body(self.items[:3])
        self.assertTrue(body.startswith('<table cellpadding="0" cellspacing="0" style="width:100%;margin:0 auto">'))
        self.assertLess(body.index("FRI"), body.index("THU"))
        self.assertLess(body.index("THU"), body.index("WED"))
        self.assertEqual(body.count("<div>"), 3)

    def test_payload(self):
        slot, previous = kit_email.weekly_slots(KIT, utc(2026, 11, 9, 13, 1))
        week = kit_email.episodes_in_window(self.items, previous, slot)
        payload = kit_email.weekly_payload(KIT, {"id": 16, "name": "Net Gain Edtech"}, week, slot, utc(2026, 11, 9, 13, 1))
        self.assertEqual(payload["subject"], "Net Gain Edtech")
        self.assertEqual(payload["tag_id"], 23806691)
        self.assertEqual(payload["template_id"], 5595806)
        self.assertEqual(payload["preview_text"], "FRI summary")
        self.assertEqual(payload["description"], "Net Gain Edtech weekly 2026-11-09 [ng-week-16-2026-11-09T08:00:00-05:00]")
        self.assertEqual(payload["send_at"], "2026-11-09T13:02:30Z")


class SettingsProblemsTests(unittest.TestCase):
    TAGS = [{"id": 23806689}, {"id": 23806691}]
    TEMPLATES = [{"id": 5595805}, {"id": 5595806}]

    def test_real_settings_have_no_problems(self):
        self.assertEqual(kit_email.settings_problems(KIT, self.TAGS, self.TEMPLATES), [])

    def test_an_unknown_tag_or_template_is_named(self):
        problems = kit_email.settings_problems(dict(KIT, daily_tag_id=1, weekly_template_id=2), self.TAGS, self.TEMPLATES)
        self.assertEqual(len(problems), 2)
        self.assertIn("daily tag ID 1", problems[0])
        self.assertIn("weekly layout template ID 2", problems[1])

    def test_unset_daily_ids_are_reported_once_not_also_as_unknown(self):
        problems = kit_email.settings_problems(dict(KIT, daily_tag_id=0), self.TAGS, self.TEMPLATES)
        self.assertEqual(len(problems), 1)
        self.assertIn("not set", problems[0])

    def test_a_switched_off_weekly_is_not_a_problem(self):
        self.assertEqual(kit_email.settings_problems(dict(KIT, weekly_day="", weekly_tag_id=0), self.TAGS, self.TEMPLATES), [])


if __name__ == "__main__":
    unittest.main()
