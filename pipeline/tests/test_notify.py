import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notify import notify_failure


def _config(**overrides):
    base = {
        "SMTP_HOST": "mail.example.com",
        "SMTP_PORT": 587,
        "SMTP_USERNAME": "alerts@example.com",
        "SMTP_PASSWORD": "secret",
        "ALERT_FROM_EMAIL": "alerts@example.com",
        "ALERT_TO_EMAIL": "dallas@example.com",
    }
    base.update(overrides)
    return base


class NotifyFailureTests(unittest.TestCase):
    def test_noop_without_smtp_host(self):
        with patch("notify.smtplib") as mock_smtplib:
            notify_failure(_config(SMTP_HOST=""), "Show", "step", "err")
        mock_smtplib.SMTP.assert_not_called()
        mock_smtplib.SMTP_SSL.assert_not_called()

    def test_noop_without_alert_to_email(self):
        with patch("notify.smtplib") as mock_smtplib:
            notify_failure(_config(ALERT_TO_EMAIL=""), "Show", "step", "err")
        mock_smtplib.SMTP.assert_not_called()
        mock_smtplib.SMTP_SSL.assert_not_called()

    @patch("notify.smtplib.SMTP")
    def test_port_587_uses_starttls_not_implicit_ssl(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        notify_failure(_config(SMTP_PORT=587), "Show", "step", "err")

        mock_smtp_cls.assert_called_once_with("mail.example.com", 587, timeout=15)
        mock_smtp.starttls.assert_called_once()
        mock_smtp.send_message.assert_called_once()

    @patch("notify.smtplib.SMTP_SSL")
    @patch("notify.smtplib.SMTP")
    def test_port_465_uses_implicit_ssl_not_starttls(self, mock_smtp_cls, mock_smtp_ssl_cls):
        """Live incident (2026-09-14): port 465 is implicit TLS (SMTPS) - the
        server never speaks plaintext SMTP on that port at all, so opening a
        plain SMTP() connection and calling starttls() (port 587's protocol)
        just hangs waiting for a greeting that structurally cannot arrive."""
        mock_smtp_ssl = MagicMock()
        mock_smtp_ssl_cls.return_value.__enter__.return_value = mock_smtp_ssl

        notify_failure(_config(SMTP_PORT=465), "Show", "step", "err")

        mock_smtp_ssl_cls.assert_called_once_with("mail.example.com", 465, timeout=15)
        mock_smtp_cls.assert_not_called()
        mock_smtp_ssl.starttls.assert_not_called()
        mock_smtp_ssl.send_message.assert_called_once()

    @patch("notify.smtplib.SMTP")
    def test_skips_login_when_no_username(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        notify_failure(_config(SMTP_USERNAME=""), "Show", "step", "err")

        mock_smtp.login.assert_not_called()
        mock_smtp.send_message.assert_called_once()

    @patch("notify.smtplib.SMTP")
    def test_logs_rather_than_raises_on_send_failure(self, mock_smtp_cls):
        mock_smtp_cls.side_effect = TimeoutError("timed out")
        notify_failure(_config(), "Show", "step", "err")  # must not raise

    @patch("notify.smtplib.SMTP")
    def test_message_fields_are_populated(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        notify_failure(_config(), "Net Gain Edtech", "website_published", "boom")

        sent_message = mock_smtp.send_message.call_args[0][0]
        self.assertIn("website_published", sent_message["Subject"])
        self.assertIn("Net Gain Edtech", sent_message["Subject"])
        self.assertEqual(sent_message["To"], "dallas@example.com")


if __name__ == "__main__":
    unittest.main()
