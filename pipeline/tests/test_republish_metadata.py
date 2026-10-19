import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import republish_metadata as rm

EPISODE = {
    "title": "Old title", "itunes_title": "", "media_id": "media-1", "published_date": "2026/10/19 14:03:35",
    "status": "Published", "shownotes": "<p>old</p>", "summary": "s", "itunes_subtitle": "", "episode_art": "art.jpg",
    "explicit": "clean", "episode_type": "full", "episode_number": 19, "itunes_block": "false",
}


class FakeCaptivate:
    def __init__(self, drift=None, ignore_title=False):
        self.episode = dict(EPISODE)
        self.puts = []
        self.drift, self.ignore_title = drift or {}, ignore_title
        self.authenticated = False

    def ensure_authenticated(self):
        self.authenticated = True

    def get_episode(self, episode_id):
        return {"episode": dict(self.episode)}

    def update_episode(self, episode_id, payload):
        self.puts.append(payload)
        if not self.ignore_title:
            self.episode["title"] = payload["title"]
        self.episode["shownotes"] = payload["shownotes"]
        self.episode.update(self.drift)


META = {
    "ng_url_captivate": "https://player.captivate.fm/episode/abc-123", "ng_meta_captivate_title": "New headline",
    "ng_meta_captivate_notes": "<p>new notes</p>", "ng_meta_aioseo_title": "Wisconsin Joins 38 States Fighting Character.AI Sale",
}
SHOW = {"captivate_show_id": "show-1", "captivate_notes_footer": "<p>Sponsor footer</p>"}


class Slug(unittest.TestCase):
    def test_slugify_matches_wordpress_style(self):
        self.assertEqual(rm.slugify("ETS Breach Traced to a Single Stolen Login"), "ets-breach-traced-to-a-single-stolen-login")
        self.assertEqual(rm.slugify("Character.AI Faces 39 States; K‑12 Schools"), "character-ai-faces-39-states-k-12-schools")
        self.assertEqual(rm.slugify("  Hello, World!  "), "hello-world")


class Captivate(unittest.TestCase):
    def test_title_and_notes_change_and_every_other_field_is_resent_unchanged(self):
        cap = FakeCaptivate()
        rm.push_to_captivate(cap, SHOW, META)
        self.assertTrue(cap.authenticated)
        payload = cap.puts[0]
        self.assertEqual(payload["title"], "New headline")
        self.assertEqual(payload["shownotes"], "<p>new notes</p>\n<p>Sponsor footer</p>")
        for key in ("media_id", "status", "episode_number", "episode_art", "explicit", "episode_type"):
            self.assertEqual(payload[key], EPISODE[key], key)

    def test_missing_captivate_episode_is_skipped(self):
        self.assertTrue(rm.push_to_captivate(FakeCaptivate(), SHOW, {"ng_url_captivate": ""}).startswith("skipped"))

    def test_an_update_that_did_not_take_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "title is"):
            rm.push_to_captivate(FakeCaptivate(ignore_title=True), SHOW, META)

    def test_drift_in_other_fields_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "media_id changed"):
            rm.push_to_captivate(FakeCaptivate(drift={"media_id": "media-2"}), SHOW, META)


class FakeWP:
    def __init__(self):
        self.calls = []

    def publish_website(self, episode_id):
        self.calls.append("publish")
        return {"post_id": 605, "permalink": "https://netgain.news/edtech/old/"}

    def rename_public_page(self, episode_id, slug):
        self.calls.append("rename")
        self.slug = slug
        return {"post_id": 605, "permalink": f"https://netgain.news/edtech/{slug}/"}

    def get_episode(self, episode_id):
        return {"meta": {}}


class Website(unittest.TestCase):
    def test_publish_then_rename_with_no_redirect_and_verify_the_new_address(self):
        wp = FakeWP()
        with mock.patch.object(rm, "verify_website_publish") as verify:
            url = rm.push_to_website(wp, 600, "Wisconsin Joins 38 States", rename=True)
        self.assertEqual(wp.calls, ["publish", "rename"])
        self.assertEqual(wp.slug, "wisconsin-joins-38-states")
        self.assertEqual(url, "https://netgain.news/edtech/wisconsin-joins-38-states/")
        self.assertEqual(verify.call_args.args[0], url)

    def test_keep_slug_publishes_once_and_never_renames(self):
        wp = FakeWP()
        with mock.patch.object(rm, "verify_website_publish"):
            rm.push_to_website(wp, 600, "Anything", rename=False)
        self.assertEqual(wp.calls, ["publish"])


class YouTube(unittest.TestCase):
    META = {"ng_youtube_video_id": "VID", "ng_meta_youtube_title": "New YT title", "ng_meta_youtube_description": "desc",
            "ng_url_website": "https://netgain.news/edtech/new/", "ng_meta_youtube_tags": ["a"], "ng_image_16x9_id": 9}
    SHOW = {"id": 16, "name": "Net Gain Edtech", "youtube_channel_id": "CH", "youtube_description_boilerplate": "Follow"}

    class WP:
        def get_attachment_url(self, i): return "u"
        def download_binary(self, u): return b"jpg"
        def get_youtube_access_token(self, sid): return {"access_token": "t"}

    def _patches(self, snippets):
        return mock.patch.multiple(
            rm,
            evaluate_youtube_checklist=mock.Mock(return_value=[]),
            yt=mock.Mock(
                build_service=mock.Mock(return_value="svc"),
                get_own_channel_id=mock.Mock(return_value="CH"),
                get_video_snippet=mock.Mock(side_effect=snippets),
                update_video_snippet=mock.Mock(),
            ),
        )

    def test_edits_the_existing_video_in_place_keeping_its_category_and_language(self):
        with self._patches([{"categoryId": "25", "defaultLanguage": "en", "title": "Old"}, {"title": "New YT title"}]):
            result = rm.push_to_youtube(self.WP(), self.SHOW, 600, self.META)
            snippet = rm.yt.update_video_snippet.call_args.args[2]
        self.assertEqual(result, "https://www.youtube.com/watch?v=VID")
        self.assertEqual(snippet["title"], "New YT title")
        self.assertEqual(snippet["categoryId"], "25")
        self.assertIn("https://netgain.news/edtech/new/", snippet["description"])      # the new page address
        self.assertIn("Follow", snippet["description"])

    def test_no_video_yet_is_skipped(self):
        self.assertTrue(rm.push_to_youtube(self.WP(), self.SHOW, 600, {}).startswith("skipped"))

    def test_a_channel_mismatch_refuses(self):
        with self._patches([{}]):
            rm.yt.get_own_channel_id.return_value = "OTHER"
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                rm.push_to_youtube(self.WP(), self.SHOW, 600, self.META)

    def test_a_title_that_never_changes_is_reported_after_several_reads(self):
        waits = []
        with self._patches([{"categoryId": "25"}] + [{"title": "Still old"}] * 6):
            with self.assertRaisesRegex(RuntimeError, "still 'Still old'"):
                rm.push_to_youtube(self.WP(), self.SHOW, 600, self.META, sleep=waits.append)
        self.assertEqual(len(waits), rm.READ_BACK_ATTEMPTS - 1)

    def test_a_read_that_lags_the_write_is_waited_out(self):
        waits = []
        with self._patches([{"categoryId": "25"}, {"title": "Old"}, {"title": "Old"}, {"title": "New YT title"}]):
            result = rm.push_to_youtube(self.WP(), self.SHOW, 600, self.META, sleep=waits.append)
        self.assertTrue(result.startswith("https://www.youtube.com/watch?v="))
        self.assertEqual(len(waits), 2)


if __name__ == "__main__":
    unittest.main()
