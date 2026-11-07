"""Kit API client (kit_client.py): request shape, error classification, duplicate-send safety."""
import os
import sys
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kit_client
from kit_client import KitClient, KitError


def _response(status=200, body=None, text=None):
    response = Mock()
    response.status_code = status
    response.json.return_value = body if body is not None else {}
    response.text = text if text is not None else ("{}" if body is None else "x")
    response.content = b"{}" if body is not None or text is None else text.encode()
    return response


def _client(responses):
    client = KitClient("secret-key")
    client.session = Mock()
    client.session.request.side_effect = responses
    return client


CREATE = dict(subject="S", preview_text="P", description="D [ng-ep-1]", content="<p>x</p>", template_id=5595805,
              tag_id=23806689, send_at="2026-11-09T21:45:00Z", published_at="2026-11-09T21:44:06Z", email_address="news@netgain.news")


class ConstructionTests(unittest.TestCase):
    def test_a_missing_key_fails_loudly(self):
        with self.assertRaises(KitError):
            KitClient("")

    def test_the_key_goes_in_a_header_not_a_url(self):
        client = KitClient("secret-key")
        self.assertEqual(client.session.headers["X-Kit-Api-Key"], "secret-key")
        self.assertIn("NetGainStudio", client.session.headers["User-Agent"])


class CreateBroadcastTests(unittest.TestCase):
    def test_the_payload_targets_the_tag_template_and_time(self):
        client = _client([_response(201, {"broadcast": {"id": 77}})])
        result = client.create_broadcast(**CREATE)
        self.assertEqual(result["id"], 77)
        method, url = client.session.request.call_args.args[:2]
        self.assertEqual((method, url), ("POST", "https://api.kit.com/v4/broadcasts"))
        payload = client.session.request.call_args.kwargs["json"]
        self.assertEqual(payload["email_template_id"], 5595805)
        self.assertEqual(payload["subscriber_filter"], [{"all": [{"type": "tag", "ids": [23806689]}], "any": None, "none": None}])
        self.assertEqual(payload["send_at"], "2026-11-09T21:45:00Z")
        self.assertIs(payload["public"], False)
        self.assertEqual(payload["email_address"], "news@netgain.news")

    def test_no_sender_means_the_accounts_default(self):
        client = _client([_response(201, {"broadcast": {"id": 1}})])
        client.create_broadcast(**dict(CREATE, email_address=""))
        self.assertNotIn("email_address", client.session.request.call_args.kwargs["json"])

    def test_a_draft_has_no_send_time(self):
        client = _client([_response(201, {"broadcast": {"id": 1}})])
        client.create_broadcast(**dict(CREATE, send_at=None))
        self.assertIsNone(client.session.request.call_args.kwargs["json"]["send_at"])

    def test_a_timeout_is_never_retried_because_kit_may_have_made_the_email(self):
        client = _client([requests.exceptions.Timeout("slow")] * 5)
        with self.assertRaises(KitError) as caught:
            client.create_broadcast(**CREATE)
        self.assertTrue(caught.exception.transient)
        self.assertEqual(client.session.request.call_count, 1)


class ErrorClassificationTests(unittest.TestCase):
    def test_a_rejected_request_is_permanent_and_carries_the_body(self):
        client = _client([_response(422, text='{"errors":["Email template not found"]}')])
        with self.assertRaises(KitError) as caught:
            client.get_account()
        self.assertFalse(caught.exception.transient)
        self.assertEqual(caught.exception.status, 422)
        self.assertIn("Email template not found", str(caught.exception))

    def test_rate_limits_and_server_errors_are_transient(self):
        for status in (429, 500, 503):
            client = _client([_response(status, text="busy")])
            with self.assertRaises(KitError) as caught:
                client.get_account()
            self.assertTrue(caught.exception.transient, status)

    def test_the_key_never_appears_in_an_error(self):
        client = _client([_response(403, text="forbidden")])
        with self.assertRaises(KitError) as caught:
            client.get_account()
        self.assertNotIn("secret-key", str(caught.exception))

    def test_reads_retry_network_errors_then_succeed(self):
        client = _client([requests.exceptions.ConnectionError("reset"), _response(200, {"account": {"id": 1}})])
        with patch("retry.time.sleep"):
            self.assertEqual(client.get_account(), {"account": {"id": 1}})
        self.assertEqual(client.session.request.call_count, 2)

    def test_a_body_that_is_not_json_is_an_error(self):
        response = _response(200, text="<html>")
        response.json.side_effect = ValueError("no json")
        client = _client([response])
        with self.assertRaises(KitError):
            client.get_account()


class FindBroadcastTests(unittest.TestCase):
    def test_finds_by_marker_on_the_first_page(self):
        page = {"broadcasts": [{"id": 1, "description": "other"}, {"id": 2, "description": "Net Gain daily [ng-ep-696]"}],
                "pagination": {"has_next_page": True, "end_cursor": "c1"}}
        client = _client([_response(200, page)])
        self.assertEqual(client.find_broadcast("[ng-ep-696]")["id"], 2)
        self.assertEqual(client.session.request.call_count, 1)

    def test_follows_the_cursor_to_a_later_page(self):
        first = {"broadcasts": [{"id": 1, "description": None}], "pagination": {"has_next_page": True, "end_cursor": "c1"}}
        second = {"broadcasts": [{"id": 9, "description": "x [ng-ep-5] y"}], "pagination": {"has_next_page": False}}
        client = _client([_response(200, first), _response(200, second)])
        self.assertEqual(client.find_broadcast("[ng-ep-5]")["id"], 9)
        self.assertEqual(client.session.request.call_args.kwargs["params"]["after"], "c1")

    def test_returns_none_when_there_is_no_match_and_no_more_pages(self):
        client = _client([_response(200, {"broadcasts": [{"id": 1, "description": "a"}], "pagination": {"has_next_page": False}})])
        self.assertIsNone(client.find_broadcast("[ng-ep-1]"))

    def test_a_marker_for_episode_1_does_not_match_episode_10(self):
        client = _client([_response(200, {"broadcasts": [{"id": 1, "description": "d [ng-ep-10]"}], "pagination": {"has_next_page": False}})])
        self.assertIsNone(client.find_broadcast("[ng-ep-1]"))

    def test_gives_up_after_a_bounded_number_of_pages(self):
        endless = {"broadcasts": [{"id": 1, "description": "a"}], "pagination": {"has_next_page": True, "end_cursor": "c"}}
        client = _client([_response(200, endless)] * 20)
        self.assertIsNone(client.find_broadcast("[nope]"))
        self.assertEqual(client.session.request.call_count, kit_client.LOOKUP_PAGES)


if __name__ == "__main__":
    unittest.main()
