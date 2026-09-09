import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from captivate_client import CaptivateClient, CaptivateError


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


if __name__ == "__main__":
    unittest.main()
