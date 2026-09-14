import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.errors import HttpError

import youtube_client as yt


def _http_error(status, body=b"raw error body"):
    resp = Mock()
    resp.status = status
    return HttpError(resp, body)


class NormalizeVideoItemTests(unittest.TestCase):
    def test_no_item_means_does_not_exist(self):
        result = yt._normalize_video_item(None)
        self.assertFalse(result["exists"])
        self.assertIsNone(result["upload_status"])

    def test_processed_video_normalizes_every_field(self):
        item = {
            "status": {
                "uploadStatus": "processed",
                "privacyStatus": "public",
                "failureReason": None,
                "rejectionReason": None,
            },
            "snippet": {"title": "Today's Newscast"},
            "processingDetails": {"processingStatus": "succeeded"},
        }
        result = yt._normalize_video_item(item)
        self.assertEqual(
            result,
            {
                "exists": True,
                "upload_status": "processed",
                "processing_status": "succeeded",
                "privacy_status": "public",
                "title": "Today's Newscast",
                "failure_reason": None,
                "rejection_reason": None,
            },
        )

    def test_rejected_video_carries_rejection_reason_through(self):
        item = {
            "status": {"uploadStatus": "rejected", "rejectionReason": "duplicate"},
            "snippet": {"title": "X"},
        }
        result = yt._normalize_video_item(item)
        self.assertEqual(result["upload_status"], "rejected")
        self.assertEqual(result["rejection_reason"], "duplicate")

    def test_missing_processing_details_does_not_raise(self):
        item = {"status": {"uploadStatus": "uploaded"}, "snippet": {"title": "X"}}
        result = yt._normalize_video_item(item)
        self.assertIsNone(result["processing_status"])


class ExecuteWithRetryTests(unittest.TestCase):
    @patch("retry.time.sleep")  # avoid a real multi-second sleep in the test suite
    def test_retryable_status_retries_then_succeeds(self, _mock_sleep):
        request = Mock()
        request.execute.side_effect = [_http_error(503), {"items": []}]

        result = yt._execute_with_retry(request)
        self.assertEqual(result, {"items": []})
        self.assertEqual(request.execute.call_count, 2)

    def test_non_retryable_status_raises_immediately(self):
        request = Mock()
        request.execute.side_effect = _http_error(404, b'{"error": "not found"}')

        with self.assertRaises(yt.YouTubeError):
            yt._execute_with_retry(request)
        self.assertEqual(request.execute.call_count, 1)

    def test_non_retryable_error_message_includes_raw_body(self):
        request = Mock()
        request.execute.side_effect = _http_error(403, b"quota exceeded detail")

        with self.assertRaises(yt.YouTubeError) as ctx:
            yt._execute_with_retry(request)
        self.assertIn("quota exceeded detail", str(ctx.exception))


class WatchUrlTests(unittest.TestCase):
    def test_constructs_expected_url(self):
        self.assertEqual(yt.watch_url("abc123"), "https://www.youtube.com/watch?v=abc123")


if __name__ == "__main__":
    unittest.main()
