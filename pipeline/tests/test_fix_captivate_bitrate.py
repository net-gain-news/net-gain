import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fix_captivate_bitrate import build_update_payload, find_episode_by_number, to_captivate_date_field


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


if __name__ == "__main__":
    unittest.main()
