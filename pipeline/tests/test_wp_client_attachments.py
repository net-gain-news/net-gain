import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wp_client import WPClient

SCALED = {
    "source_url": "https://x.test/uploads/edtech-square-2-scaled.jpg",
    "media_details": {"original_image": "edtech-square-2.jpg"},
}


def client():
    return WPClient("https://x.test", "svc", "pw")


class AttachmentUrlTests(unittest.TestCase):
    def test_default_is_the_url_wordpress_reports(self):
        with patch.object(WPClient, "_request", return_value=SCALED):
            self.assertEqual(client().get_attachment_url(1), "https://x.test/uploads/edtech-square-2-scaled.jpg")

    def test_original_returns_the_file_as_uploaded(self):
        with patch.object(WPClient, "_request", return_value=SCALED):
            self.assertEqual(client().get_attachment_url(1, original=True), "https://x.test/uploads/edtech-square-2.jpg")

    def test_original_falls_back_when_wordpress_did_not_scale_the_image(self):
        plain = {"source_url": "https://x.test/uploads/a.jpg", "media_details": {}}
        with patch.object(WPClient, "_request", return_value=plain):
            self.assertEqual(client().get_attachment_url(1, original=True), "https://x.test/uploads/a.jpg")


if __name__ == "__main__":
    unittest.main()
