import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from captivate_client import (
    CAPTIVATE_ACCOUNT_TIMEZONE,
    CaptivateClient,
    CaptivateError,
    episode_update_payload,
    parse_captivate_timestamp,
)


class AuthenticateTests(unittest.TestCase):
    def _client_with_response(self, response):
        client = CaptivateClient("user-id", "api-token")
        client._request = lambda method, path, **kwargs: response
        return client

    def test_top_level_token(self):
        client = self._client_with_response({"success": True, "token": "abc123", "user": {}})
        client.authenticate()
        self.assertEqual(client.session.headers["Authorization"], "Bearer abc123")

    def test_nested_user_token(self):
        client = self._client_with_response({"user": {"id": "1", "token": "xyz789"}})
        client.authenticate()
        self.assertEqual(client.session.headers["Authorization"], "Bearer xyz789")

    def test_neither_shape_raises_with_raw_body_visible(self):
        client = self._client_with_response({"success": True, "user": {"id": "1"}})
        with self.assertRaises(CaptivateError) as ctx:
            client.authenticate()
        self.assertIn("user", str(ctx.exception))  # raw response echoed, not a generic message

    def test_ensure_authenticated_only_calls_once(self):
        client = self._client_with_response({"token": "abc123"})
        calls = []
        original_authenticate = client.authenticate

        def counting_authenticate():
            calls.append(1)
            original_authenticate()

        client.authenticate = counting_authenticate
        client.ensure_authenticated()
        client.ensure_authenticated()
        self.assertEqual(len(calls), 1)


class UploadMediaTests(unittest.TestCase):
    def _client_with_response(self, response):
        client = CaptivateClient("user-id", "api-token")
        client._request = lambda method, path, **kwargs: response
        return client

    def test_top_level_id(self):
        client = self._client_with_response({"id": "media-1", "name": "episode.mp3"})
        media_id = client.upload_media("show-1", b"fake-audio-bytes", "episode.mp3")
        self.assertEqual(media_id, "media-1")

    def test_nested_media_id(self):
        client = self._client_with_response({"media": {"id": "media-2"}})
        media_id = client.upload_media("show-1", b"fake-audio-bytes", "episode.mp3")
        self.assertEqual(media_id, "media-2")

    def test_neither_shape_raises_with_raw_body_visible(self):
        client = self._client_with_response({"success": True})
        with self.assertRaises(CaptivateError) as ctx:
            client.upload_media("show-1", b"fake-audio-bytes", "episode.mp3")
        self.assertIn("success", str(ctx.exception))


class UpdateEpisodeTests(unittest.TestCase):
    def test_sends_a_put_with_the_full_payload(self):
        client = CaptivateClient("user-id", "api-token")
        captured = {}

        def fake_request(method, path, **kwargs):
            captured["method"] = method
            captured["path"] = path
            captured["data"] = kwargs.get("data")
            return {"success": True, "errors": [], "episode": [{"id": "ep-1"}]}

        client._request = fake_request
        payload = {"shows_id": "show-1", "title": "T", "media_id": "media-2", "episode_number": 5}
        client.update_episode("ep-1", payload)

        self.assertEqual(captured["method"], "PUT")
        self.assertEqual(captured["path"], "/episodes/ep-1")
        self.assertEqual(captured["data"], payload)


class ListEpisodesTests(unittest.TestCase):
    def test_get_next_episode_number_uses_list_episodes(self):
        """list_episodes() and get_next_episode_number() must stay wired
        together - a regression here would silently make numbering ignore
        whatever list_episodes() actually returns."""
        client = CaptivateClient("user-id", "api-token")
        client._request = lambda method, path, **kwargs: {
            "episodes": [{"episode_number": 3}, {"episode_number": 7}]
        }
        self.assertEqual(client.get_next_episode_number("show-1"), 8)


class AccountTimezoneTests(unittest.TestCase):
    """Captivate reads episode dates as wall-clock time in the show's zone, applied with ITS rules: in November that is Pacific
    standard time (UTC-8; its feed prints -0800). The server's tz database says British Columbia is on permanent UTC-7, and
    formatting with it made episodes 31 and 32 (2026-11-04, 2026-11-05) read an hour late and sit as Scheduled for 59 minutes."""

    def _client_reporting(self, response):
        client = CaptivateClient("user-id", "api-token")
        client._request = lambda method, path, **kwargs: response
        return client

    def test_dates_are_written_in_pacific_time_with_the_us_rules(self):
        from datetime import datetime, timezone
        self.assertEqual(CAPTIVATE_ACCOUNT_TIMEZONE.key, "America/Los_Angeles")
        # Episode 32: created 21:58 UTC on 2026-11-05. Captivate flipped it to Published at exactly 22:57:00 UTC, which is when
        # it read the digits "14:56:33" as UTC-8; "13:56:33" is the digits that mean two minutes ago.
        due = datetime(2026, 11, 5, 21, 56, 33, tzinfo=timezone.utc)
        self.assertEqual(due.astimezone(CAPTIVATE_ACCOUNT_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"), "2026-11-05 13:56:33")

    def test_accepts_the_zone_captivate_reports_for_the_show(self):
        self._client_reporting({"name": "Net Gain News", "time_zone": "America/Vancouver"}).verify_account_timezone("show")
        self._client_reporting({"show": {"time_zone": "America/Vancouver"}}).verify_account_timezone("show")

    def test_refuses_any_other_zone_before_anything_is_published(self):
        for reported in ("America/Los_Angeles", "America/Toronto", "UTC", "", None):
            with self.assertRaises(CaptivateError, msg=reported):
                self._client_reporting({"time_zone": reported}).verify_account_timezone("show")

    def test_refuses_when_captivate_reports_no_zone_at_all(self):
        with self.assertRaises(CaptivateError):
            self._client_reporting({"name": "Net Gain News"}).verify_account_timezone("show")

    def test_a_utc_timestamp_is_written_back_as_pacific_wall_clock(self):
        episode = {"published_date": "2026-11-03T21:38:16.000Z", "title": "T", "status": "Published", "episode_number": 30}
        payload = episode_update_payload(episode, "show", "media")
        self.assertEqual(payload["date"], "2026-11-03 13:38:16")

    def test_a_wall_clock_timestamp_is_read_as_pacific(self):
        parsed = parse_captivate_timestamp("2026/11/03 13:38:16")
        self.assertEqual(parsed.astimezone(timezone.utc), datetime(2026, 11, 3, 21, 38, 16, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
