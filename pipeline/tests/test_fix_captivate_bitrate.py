import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fix_captivate_bitrate import (
    build_update_payload,
    find_episode_by_number,
    parse_captivate_timestamp,
    to_captivate_date_field,
    verify_unchanged,
)


class ToCaptivateDateFieldTests(unittest.TestCase):
    def test_converts_utc_to_pacific_daylight_time(self):
        # 2026-09-18T15:18:00Z is during PDT (UTC-7) - matches the real
        # episode 5 data pulled live from Captivate on 2026-09-21.
        self.assertEqual(to_captivate_date_field("2026-09-18T15:18:00.000Z"), "2026-09-18 08:18:00")

    def test_converts_utc_to_pacific_standard_time(self):
        # Same wall-clock UTC time in January - PST (UTC-8), not PDT, so the
        # local hour differs from the summer case above.
        self.assertEqual(to_captivate_date_field("2026-01-18T15:18:00.000Z"), "2026-01-18 07:18:00")

    def test_crosses_a_calendar_day_boundary(self):
        # Early UTC morning is still the previous evening in Pacific.
        self.assertEqual(to_captivate_date_field("2026-09-18T04:00:00.000Z"), "2026-09-17 21:00:00")


class FindEpisodeByNumberTests(unittest.TestCase):
    def test_finds_matching_episode(self):
        class FakeCaptivate:
            def list_episodes(self, show_id):
                return {"episodes": [{"episode_number": 4, "id": "a"}, {"episode_number": 5, "id": "b"}]}

        episode = find_episode_by_number(FakeCaptivate(), 5)
        self.assertEqual(episode["id"], "b")

    def test_raises_when_not_found(self):
        class FakeCaptivate:
            def list_episodes(self, show_id):
                return {"episodes": [{"episode_number": 1, "id": "a"}]}

        with self.assertRaises(RuntimeError):
            find_episode_by_number(FakeCaptivate(), 99)


class BuildUpdatePayloadTests(unittest.TestCase):
    def _episode(self, **overrides):
        base = {
            "title": "Some Episode",
            "itunes_title": None,
            "published_date": "2026-09-18T15:18:00.000Z",
            "status": "Published",
            "shownotes": "<p>Notes</p>",
            "summary": None,
            "itunes_subtitle": None,
            "episode_art": "https://example.com/art.jpg",
            "explicit": "clean",
            "episode_type": "full",
            "episode_number": 5,
            "itunes_block": "false",
        }
        base.update(overrides)
        return base

    def test_preserves_every_current_field_and_swaps_only_media_id(self):
        episode = self._episode()
        payload = build_update_payload(episode, "new-media-id")

        self.assertEqual(payload["media_id"], "new-media-id")
        self.assertEqual(payload["title"], "Some Episode")
        self.assertEqual(payload["episode_number"], 5)
        self.assertEqual(payload["status"], "Published")
        self.assertEqual(payload["shownotes"], "<p>Notes</p>")
        self.assertEqual(payload["date"], "2026-09-18 08:18:00")

    def test_null_fields_become_empty_string_not_the_literal_none(self):
        episode = self._episode(itunes_title=None, summary=None, itunes_subtitle=None)
        payload = build_update_payload(episode, "new-media-id")

        self.assertEqual(payload["itunes_title"], "")
        self.assertEqual(payload["summary"], "")
        self.assertEqual(payload["itunes_subtitle"], "")


class ParseCaptivateTimestampTests(unittest.TestCase):
    """Live incident (2026-09-21): Captivate echoes published_date in two
    different formats depending on how the record was last written - UTC
    ISO8601 from a POST-created episode, local-time slash-separated from a
    PUT-updated one - even though both represent the same real instant
    (independently confirmed against the live RSS feed's own <pubDate>)."""

    def test_parses_utc_iso_format(self):
        dt = parse_captivate_timestamp("2026-09-18T15:18:00.000Z")
        self.assertEqual(dt.utcoffset().total_seconds(), 0)

    def test_parses_local_slash_format(self):
        dt = parse_captivate_timestamp("2026/09/18 08:18:00")
        self.assertIsNotNone(dt.tzinfo)

    def test_both_formats_of_the_same_instant_are_equal(self):
        utc_form = parse_captivate_timestamp("2026-09-18T15:18:00.000Z")
        local_form = parse_captivate_timestamp("2026/09/18 08:18:00")
        self.assertEqual(utc_form, local_form)

    def test_none_is_handled(self):
        self.assertIsNone(parse_captivate_timestamp(None))


class VerifyUnchangedTests(unittest.TestCase):
    def _fake_captivate(self, returned_episode):
        class FakeCaptivate:
            def get_episode(self, episode_id):
                return {"episode": returned_episode}

        return FakeCaptivate()

    def test_the_live_discovered_timestamp_format_change_is_not_flagged(self):
        before = {
            "title": "T", "episode_number": 5, "status": "Published", "shownotes": "<p>N</p>",
            "published_date": "2026-09-18T15:18:00.000Z", "media_url": "https://old",
        }
        after = dict(before, published_date="2026/09/18 08:18:00", media_url="https://new")
        captivate = self._fake_captivate(after)

        _, problems = verify_unchanged(captivate, "ep-1", before, expected_media_url_change=True)
        self.assertEqual(problems, [])

    def test_a_genuinely_different_timestamp_is_flagged(self):
        before = {
            "title": "T", "episode_number": 5, "status": "Published", "shownotes": "<p>N</p>",
            "published_date": "2026-09-18T15:18:00.000Z", "media_url": "https://old",
        }
        after = dict(before, published_date="2026-09-21T00:00:00.000Z", media_url="https://new")
        captivate = self._fake_captivate(after)

        _, problems = verify_unchanged(captivate, "ep-1", before, expected_media_url_change=True)
        self.assertTrue(any("published_date" in p for p in problems))

    def test_an_unchanged_media_url_is_flagged_when_a_change_was_expected(self):
        before = {
            "title": "T", "episode_number": 5, "status": "Published", "shownotes": "<p>N</p>",
            "published_date": "2026-09-18T15:18:00.000Z", "media_url": "https://same",
        }
        after = dict(before)  # media_url did not change
        captivate = self._fake_captivate(after)

        _, problems = verify_unchanged(captivate, "ep-1", before, expected_media_url_change=True)
        self.assertTrue(any("media_url" in p for p in problems))

    def test_a_changed_title_is_flagged(self):
        before = {
            "title": "Original Title", "episode_number": 5, "status": "Published", "shownotes": "<p>N</p>",
            "published_date": "2026-09-18T15:18:00.000Z", "media_url": "https://old",
        }
        after = dict(before, title="Something Else", media_url="https://new")
        captivate = self._fake_captivate(after)

        _, problems = verify_unchanged(captivate, "ep-1", before, expected_media_url_change=True)
        self.assertTrue(any("title" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
