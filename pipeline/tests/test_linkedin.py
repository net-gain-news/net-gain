"""LinkedIn posting: the post text, the token file, the client's guards, and the tick step (due check, one post, no duplicates)."""
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import linkedin_post as lp
import linkedin_token
import tick
from linkedin_client import LinkedInClient, LinkedInError

PAGE = "https://netgain.news/edtech/australia-curbs-school-ai/"
NOTES = ("<p>Australia moves to curb AI in classrooms (pilot) by term two.</p><p>Ontario boards weigh a $5M cyber fund, @CoSN says.</p>"
         "<p><strong>Stories &amp; links:</strong></p><p>1. Australia - <a href=\"https://example.com/a\">link</a></p>")
WEBSITE_AT = "2026-11-20 21:44:06"
NOW = datetime(2026, 11, 20, 21, 50, 0, tzinfo=timezone.utc)
LI = {"enabled": True, "since": "2026-11-20 00:00:00", "page_id": 146769492}


class PostText(unittest.TestCase):
    def test_paragraphs_stop_at_stories_and_links(self):
        self.assertEqual(lp.notes_paragraphs(NOTES), [
            "Australia moves to curb AI in classrooms (pilot) by term two.",
            "Ontario boards weigh a $5M cyber fund, @CoSN says."])

    def test_entities_and_tags_become_plain_text(self):
        self.assertEqual(lp.notes_paragraphs("<p>Tom &amp; Jerry <em>win</em></p>"), ["Tom & Jerry win"])

    def test_notes_without_paragraph_tags_still_cut_at_the_header(self):
        self.assertEqual(lp.notes_paragraphs("One.<br><br>Two.<br><br>Stories & links:<br>1. x"), ["One.", "Two."])

    def test_commentary_shape(self):
        text = lp.build_commentary(["First story.", "Second story."], PAGE)
        self.assertEqual(text, "Today in edtech:\n\nFirst story.\n\nSecond story.\n\nListen to today's episode:\n" + PAGE)

    def test_reserved_characters_are_escaped(self):
        text = lp.build_commentary(["Pilot (term two) #1 @CoSN"], "https://x.test/a_b/")
        self.assertIn("Pilot \\(term two\\) \\#1 \\@CoSN", text)
        self.assertIn("a\\_b", text)

    def test_long_notes_drop_whole_paragraphs_from_the_end(self):
        paragraphs = ["A" * 1200, "B" * 1200, "C" * 1200]
        text = lp.build_commentary(paragraphs, PAGE)
        self.assertLessEqual(len(text), lp.COMMENTARY_LIMIT)
        self.assertIn("A" * 1200, text)
        self.assertNotIn("C", text.replace("Listen to today's episode:", ""))
        self.assertTrue(text.endswith(PAGE))

    def test_a_single_overlong_paragraph_fails_loudly(self):
        with self.assertRaises(lp.LinkedInPostError):
            lp.build_commentary(["A" * 3500], PAGE)

    def test_no_link_or_no_stories_fails_loudly(self):
        with self.assertRaises(lp.LinkedInPostError):
            lp.build_commentary(["x"], "")
        with self.assertRaises(lp.LinkedInPostError):
            lp.build_commentary([], PAGE)

    def test_payload_attaches_the_page_as_an_article_card(self):
        payload = lp.post_payload(lp.author_urn(146769492), "text", PAGE, "Title", "Summary", "urn:li:image:1")
        self.assertEqual(payload["author"], "urn:li:organization:146769492")
        self.assertEqual(payload["content"]["article"], {"source": PAGE, "title": "Title", "description": "Summary", "thumbnail": "urn:li:image:1"})
        self.assertEqual(payload["visibility"], "PUBLIC")
        self.assertNotIn("thumbnail", lp.post_payload("a", "t", PAGE, "T", "D")["content"]["article"])

    def test_finding_a_post_made_for_the_page(self):
        self.assertTrue(lp.post_mentions_episode({"content": {"article": {"source": PAGE}}}, PAGE))
        self.assertTrue(lp.post_mentions_episode({"commentary": "x https\\://netgain.news/edtech/australia-curbs-school-ai/".replace("\\:", ":")}, PAGE))
        self.assertFalse(lp.post_mentions_episode({"commentary": "other", "content": {"article": {"source": PAGE + "x"}}}, PAGE))


class TokenFile(unittest.TestCase):
    def test_round_trip_and_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.json")
            self.assertIsNone(linkedin_token.load_token(path))
            linkedin_token.save_token({"access_token": "tok", "expires_at": 1000.0}, path)
            record = linkedin_token.load_token(path)
            self.assertEqual(record["access_token"], "tok")
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
            self.assertEqual(linkedin_token.seconds_left(record, now=400.0), 600.0)

    def test_unreadable_or_incomplete_file_reads_as_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.json")
            open(path, "w").write("not json")
            self.assertIsNone(linkedin_token.load_token(path))
            open(path, "w").write('{"access_token": "x"}')
            self.assertIsNone(linkedin_token.load_token(path))

    def test_authorization_url_asks_for_posting_and_reading(self):
        url = linkedin_token.authorization_url("cid", "https://netgain.news/cb", "st")
        self.assertIn("w_organization_social", url)
        self.assertIn("client_id=cid", url)


class Client(unittest.TestCase):
    def _client(self):
        return LinkedInClient("tok", version="202605")

    def test_headers(self):
        h = self._client().session.headers
        self.assertEqual(h["Authorization"], "Bearer tok")
        self.assertEqual(h["Linkedin-Version"], "202605")
        self.assertEqual(h["X-Restli-Protocol-Version"], "2.0.0")

    def _response(self, status=200, body=None, headers=None):
        r = Mock(status_code=status, text=str(body), headers=headers or {})
        r.json.return_value = body
        return r

    def test_create_post_returns_the_id_header_and_is_not_retried(self):
        c = self._client()
        c.session.request = Mock(return_value=self._response(201, {}, {"x-restli-id": "urn:li:share:9"}))
        self.assertEqual(c.create_post({"a": 1}), "urn:li:share:9")
        c.session.request = Mock(side_effect=__import__("requests").exceptions.Timeout())
        with self.assertRaises(LinkedInError) as ctx:
            c.create_post({"a": 1})
        self.assertEqual(c.session.request.call_count, 1)
        self.assertTrue(ctx.exception.transient)

    def test_error_classification(self):
        c = self._client()
        for status, transient in ((401, False), (403, False), (422, False), (429, True), (503, True)):
            c.session.request = Mock(return_value=self._response(status, {}))
            with self.assertRaises(LinkedInError) as ctx:
                c.create_post({})
            self.assertEqual((ctx.exception.status, ctx.exception.transient), (status, transient))

    def test_find_post_scans_recent_posts(self):
        c = self._client()
        c.session.request = Mock(return_value=self._response(200, {"elements": [{"id": "1"}, {"id": "2", "k": "yes"}]}))
        self.assertEqual(c.find_post("urn:li:organization:5", lambda p: p.get("k") == "yes")["id"], "2")
        self.assertIn("author=urn%3Ali%3Aorganization%3A5", c.session.request.call_args[0][1])
        self.assertIsNone(c.find_post("urn:li:organization:5", lambda p: False))

    def test_upload_image_returns_the_urn(self):
        c = self._client()
        c.session.request = Mock(side_effect=[self._response(200, {"value": {"uploadUrl": "https://up.test/x", "image": "urn:li:image:7"}}), self._response(201, {})])
        self.assertEqual(c.upload_image("urn:li:organization:5", b"png"), "urn:li:image:7")
        self.assertEqual(c.session.request.call_args_list[1][0][:2], ("PUT", "https://up.test/x"))


def _show(**over):
    show = {"id": 16, "name": "Net Gain Edtech", "site_timezone": "UTC", "linkedin": dict(LI), "pending_actions": []}
    show.update(over)
    return show


def _episode(linkedin="pending", website="done", website_at=WEBSITE_AT, state="finalized"):
    steps = {"website_published": {"status": website, "at": website_at}, "linkedin_posted": {"status": linkedin}}
    return {"id": 700, "episode_date": "2026-11-20", "step_status": steps, "finalization": {"state": state}}


class Due(unittest.TestCase):
    def test_due_once_the_page_is_live_after_switch_on(self):
        self.assertTrue(tick.linkedin_post_due(_show(), _episode()))

    def test_not_when_off_or_page_not_live_or_not_finalized(self):
        self.assertFalse(tick.linkedin_post_due(_show(linkedin={**LI, "enabled": False}), _episode()))
        self.assertFalse(tick.linkedin_post_due(_show(), _episode(website="pending")))
        self.assertFalse(tick.linkedin_post_due(_show(), _episode(state="draft")))

    def test_not_for_episodes_older_than_switch_on(self):
        self.assertFalse(tick.linkedin_post_due(_show(linkedin={**LI, "since": "2026-11-21 00:00:00"}), _episode()))
        self.assertFalse(tick.linkedin_post_due(_show(linkedin={**LI, "since": ""}), _episode()))

    def test_finished_or_failed_steps_wait_for_a_manual_request(self):
        for status in ("done", "degraded", "failed"):
            self.assertFalse(tick.linkedin_post_due(_show(), _episode(linkedin=status)))
        forced = _show(pending_actions=[{"id": "a", "action": "post_linkedin", "status": "pending", "episode_date": "2026-11-20"}],
                       linkedin={**LI, "since": "2026-12-01 00:00:00"})
        self.assertTrue(tick.linkedin_post_due(forced, _episode(linkedin="failed")))


def _meta(**over):
    meta = {"ng_url_website": PAGE, "ng_meta_captivate_notes": NOTES, "ng_meta_captivate_title": "Australia Curbs School AI",
            "ng_meta_website_excerpt": "Summary.", "ng_image_16x9_id": 12}
    meta.update(over)
    return meta


def _wp(meta=None):
    wp = Mock()
    wp.get_episode.return_value = {"meta": meta if meta is not None else _meta(), "title": {"rendered": "T"}}
    wp.get_attachment_url.return_value = "https://netgain.news/img.png"
    wp.download_binary.return_value = b"png"
    return wp


def _client(expires=None):
    c = Mock()
    c.expires_at = expires
    c.find_post.return_value = None
    c.upload_image.return_value = "urn:li:image:1"
    c.create_post.return_value = "urn:li:share:99"
    return c


def _steps(wp):
    return [(c.args[1], c.args[2]) for c in wp.update_step.call_args_list]


class Posting(unittest.TestCase):
    def run_post(self, wp=None, client=None, show=None, pending=(), now=NOW, episode=None):
        wp = wp or _wp()
        client = client if client is not None else _client()
        with patch.object(tick, "notify_failure") as notify:
            tick.post_episode_to_linkedin(wp, client, {}, show or _show(), episode or _episode(), list(pending), now=now)
        return wp, client, notify

    def test_posts_the_notes_once_and_records_it(self):
        wp, client, notify = self.run_post()
        payload = client.create_post.call_args[0][0]
        self.assertEqual(payload["author"], "urn:li:organization:146769492")
        self.assertTrue(payload["commentary"].startswith("Today in edtech:\n\nAustralia moves"))
        self.assertTrue(payload["commentary"].endswith(PAGE))
        self.assertNotIn("Stories", payload["commentary"])
        self.assertEqual(payload["content"]["article"]["thumbnail"], "urn:li:image:1")
        self.assertEqual(_steps(wp), [("linkedin_posted", "in_progress"), ("linkedin_posted", "done")])
        wp.update_episode_meta.assert_any_call(700, {"ng_linkedin_post_urn": "urn:li:share:99", "ng_linkedin_attempt": ""})
        notify.assert_not_called()

    def test_a_post_that_already_exists_is_adopted_not_repeated(self):
        client = _client()
        client.find_post.return_value = {"id": "urn:li:share:5"}
        wp, client, _ = self.run_post(client=client)
        client.create_post.assert_not_called()
        self.assertEqual(_steps(wp), [("linkedin_posted", "done")])

    def test_a_recorded_post_is_adopted_without_any_call(self):
        wp, client, _ = self.run_post(wp=_wp(_meta(ng_linkedin_post_urn="urn:li:share:5")))
        client.find_post.assert_not_called()
        client.create_post.assert_not_called()

    def test_search_failure_after_an_earlier_attempt_fails_loudly_and_does_not_post(self):
        client = _client()
        client.find_post.side_effect = LinkedInError("boom", status=403)
        wp, client, notify = self.run_post(wp=_wp(_meta(ng_linkedin_attempt="2026-11-20T21:40:00+00:00")), client=client)
        client.create_post.assert_not_called()
        self.assertEqual(_steps(wp)[-1][1], "failed")
        notify.assert_called_once()

    def test_search_failure_with_no_earlier_attempt_still_posts(self):
        client = _client()
        client.find_post.side_effect = LinkedInError("no read permission", status=403)
        wp, client, _ = self.run_post(client=client)
        client.create_post.assert_called_once()
        self.assertEqual(_steps(wp)[-1][1], "done")

    def test_the_picture_failing_never_blocks_the_post(self):
        client = _client()
        client.upload_image.side_effect = LinkedInError("bad image", status=400)
        wp, client, _ = self.run_post(client=client)
        self.assertNotIn("thumbnail", client.create_post.call_args[0][0]["content"]["article"])
        self.assertEqual(_steps(wp)[-1][1], "done")

    def test_a_refusal_fails_with_a_plain_note_and_clears_the_attempt(self):
        client = _client()
        client.create_post.side_effect = LinkedInError("LinkedIn POST /posts returned 403: nope", status=403)
        wp, client, notify = self.run_post(client=client)
        self.assertEqual(_steps(wp)[-1][1], "failed")
        self.assertIn("administrator of the page", wp.update_step.call_args[1]["note"])
        wp.update_episode_meta.assert_any_call(700, {"ng_linkedin_attempt": ""})
        notify.assert_called_once()

    def test_an_unconfirmed_post_is_never_retried_automatically(self):
        client = _client()
        client.create_post.side_effect = LinkedInError("Could not reach LinkedIn (Timeout).", transient=True)
        wp, client, _ = self.run_post(client=client)
        client.create_post.assert_called_once()
        self.assertEqual(_steps(wp)[-1][1], "failed")
        self.assertIn("did not confirm", wp.update_step.call_args[1]["note"])

    def test_a_transient_lookup_failure_inside_the_window_retries_later(self):
        client = _client()
        client.find_post.side_effect = LinkedInError("busy", status=503, transient=True)
        wp, client, notify = self.run_post(client=client)
        client.create_post.assert_not_called()
        self.assertEqual(_steps(wp)[-1], ("linkedin_posted", "pending"))
        notify.assert_not_called()

    def test_a_transient_failure_after_the_window_fails(self):
        client = _client()
        client.find_post.side_effect = LinkedInError("busy", status=503, transient=True)
        wp, client, notify = self.run_post(client=client, now=NOW + timedelta(minutes=30))
        self.assertEqual(_steps(wp)[-1][1], "failed")

    def test_missing_page_missing_sign_in_and_expired_sign_in_fail_plainly(self):
        wp, client, _ = self.run_post(show=_show(linkedin={**LI, "page_id": 0}))
        self.assertIn("no LinkedIn page", wp.update_step.call_args[1]["note"])
        with patch.object(tick, "notify_failure"):
            wp = _wp()
            tick.post_episode_to_linkedin(wp, None, {}, _show(), _episode(), [], now=NOW)
            self.assertIn("no LinkedIn sign-in", wp.update_step.call_args[1]["note"])
        wp, client, _ = self.run_post(client=_client(expires=NOW.timestamp() - 5))
        self.assertIn("expired", wp.update_step.call_args[1]["note"])
        client.create_post.assert_not_called()

    def test_an_old_episode_is_not_posted_without_a_manual_request(self):
        wp, client, _ = self.run_post(now=NOW + timedelta(hours=14))
        client.create_post.assert_not_called()
        self.assertIn("too late", wp.update_step.call_args[1]["note"])
        wp, client, _ = self.run_post(now=NOW + timedelta(hours=14), pending=[{"id": "a"}])
        client.create_post.assert_called_once()
        wp.update_action.assert_called_with(16, "a", "done")

    def test_no_show_notes_fails_loudly(self):
        wp, client, _ = self.run_post(wp=_wp(_meta(ng_meta_captivate_notes="")))
        client.create_post.assert_not_called()
        self.assertEqual(_steps(wp)[-1][1], "failed")


class SignInWarning(unittest.TestCase):
    def test_warns_once_a_day_inside_the_window(self):
        memory = Mock()
        memory.already_sent.return_value = False
        now = 1_800_000_000.0
        with patch.object(tick, "send_notice", return_value=True) as notice:
            tick.warn_linkedin_sign_in({}, Mock(expires_at=now + 5 * 86400), memory=memory, now=now)
            self.assertIn("5 day", notice.call_args[0][2])
        memory.mark_sent.assert_called_once()

    def test_quiet_when_far_from_expiry_or_already_sent(self):
        memory = Mock()
        memory.already_sent.return_value = False
        with patch.object(tick, "send_notice") as notice:
            tick.warn_linkedin_sign_in({}, Mock(expires_at=2_000_000_000.0), memory=memory, now=1_800_000_000.0)
            notice.assert_not_called()
        memory.already_sent.return_value = True
        with patch.object(tick, "send_notice") as notice:
            tick.warn_linkedin_sign_in({}, None, memory=memory, now=1_800_000_000.0)
            notice.assert_not_called()

    def test_reports_a_missing_sign_in(self):
        memory = Mock()
        memory.already_sent.return_value = False
        with patch.object(tick, "send_notice", return_value=True) as notice:
            tick.warn_linkedin_sign_in({}, None, memory=memory, now=1_800_000_000.0)
            self.assertIn("No LinkedIn sign-in", notice.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
