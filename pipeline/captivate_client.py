"""
Captivate.fm API client (SPEC.md Section 6.1).

Field names and endpoints below come from Captivate's own published OpenAPI
specs, cross-checked against an independent open-source SDK - not guessed
(Section 1's own documented lesson is explicit that this API's field names
were previously discovered the hard way and must not be re-guessed). Two
things neither source fully documents are handled defensively rather than
assumed - see AUTH and MEDIA UPLOAD below - and every error raised here
includes the raw response body, per Section 10's own guidance that a
Captivate-failure tooltip should point at the logged raw response first.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from retry import call_with_retries

logger = logging.getLogger("net_gain.captivate_client")

BASE_URL = "https://api.captivate.fm"

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class CaptivateError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code      # the HTTP status when Captivate answered with one, else None


class CaptivateClient:
    def __init__(self, user_id, api_token, timeout=60):
        self.user_id = user_id
        self.api_token = api_token
        self.timeout = timeout
        self.session = requests.Session()
        # See wp_client.py - the account's own WAF blocks requests' default
        # User-Agent outright; using the same honest custom one everywhere calls
        # go out from this pipeline, not just where it was first discovered.
        self.session.headers["User-Agent"] = "NetGainStudio-Pipeline/1.0 (+https://netgain.news)"

    def ensure_authenticated(self):
        """Authenticates once per process (per tick pass), reused across every show that needs it."""
        if "Authorization" not in self.session.headers:
            self.authenticate()

    def authenticate(self):
        response = self._request(
            "POST", "/authenticate/token", data={"username": self.user_id, "token": self.api_token}
        )
        # AUTH: the two sources documenting this consulted for this build disagree on
        # whether the bearer token is top-level or nested under "user" - check both
        # rather than assume either, and fail loudly with the raw body if neither matches.
        token = response.get("token") or (response.get("user") or {}).get("token")
        if not token:
            raise CaptivateError(f"Could not find a bearer token in the auth response: {response}")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def get_show(self, captivate_show_id):
        return self._request("GET", f"/shows/{captivate_show_id}")

    def verify_account_timezone(self, captivate_show_id):
        """Raises unless Captivate still reports the show's zone as CAPTIVATE_REPORTED_ZONE (see the note on CAPTIVATE_ACCOUNT_TIMEZONE)."""
        show = self.get_show(captivate_show_id)
        if isinstance(show, dict):
            show = show.get("show", show)
        reported = show.get("time_zone") if isinstance(show, dict) else None
        if reported != CAPTIVATE_REPORTED_ZONE:
            raise CaptivateError(
                f"Captivate reports the show's time zone as {reported!r}, but episode dates are formatted for a show Captivate "
                f"reports as {CAPTIVATE_REPORTED_ZONE!r}. Nothing was published; the zone in captivate_client.py needs checking."
            )

    def upload_media(self, captivate_show_id, file_bytes, filename, content_type="audio/mpeg"):
        response = self._request(
            "POST",
            f"/shows/{captivate_show_id}/media",
            files={"file": (filename, file_bytes, content_type)},
        )
        # MEDIA UPLOAD: response shape is undocumented in both sources consulted -
        # check the plausible spots, fail loudly with the raw body if neither matches.
        media_id = response.get("id") or (response.get("media") or {}).get("id")
        if not media_id:
            raise CaptivateError(f"Could not find a media id in the upload response: {response}")
        return media_id

    def get_next_episode_number(self, captivate_show_id):
        """
        Live-polled at publish time, not tracked separately - Captivate's own
        current episode list is always the source of truth, so deleting all of
        a show's episodes there and republishing naturally restarts numbering
        at 1 with no separate reset step needed anywhere. Ported from the
        prior single-show prototype's publish_episode.py, with one deliberate
        change: that version defaulted to 1 on ANY lookup problem, including
        an unrecognized response shape. Here, only a genuinely empty episode
        list returns 1 - if episodes exist but none expose a recognized number
        field, this raises rather than silently mislabeling every future
        episode "1" (Section 1's "fail loudly, don't guess quietly" applies
        directly to numbering a live public feed).
        """
        response = self.list_episodes(captivate_show_id)

        episodes = None
        for path in (("episodes",), ("data",)):
            value = response
            try:
                for key in path:
                    value = value[key]
                episodes = value
                break
            except (KeyError, TypeError):
                continue
        if episodes is None and isinstance(response, list):
            episodes = response

        if not episodes:
            return 1

        numbers = []
        for ep in episodes:
            if not isinstance(ep, dict):
                continue
            for field in ("episode_number", "number", "episode"):
                if field in ep:
                    try:
                        numbers.append(int(ep[field]))
                    except (TypeError, ValueError):
                        pass
                    break

        if not numbers:
            raise CaptivateError(
                f"Show has {len(episodes)} existing episode(s) but none exposed a "
                "recognized episode-number field (tried episode_number/number/episode) "
                f"- refusing to guess 1 and risk mislabeling every future episode. "
                f"Raw response: {response}"
            )
        return max(numbers) + 1

    def create_episode(self, payload):
        # Sent form-encoded, not JSON - Captivate's confirmed auth endpoint uses
        # FormData, and the one documented episode-create example found uses the
        # same key=value shape rather than a JSON body. Worth confirming against
        # a live response on first real use (see PHASE_5_HANDOFF.md).
        #
        # Exception (2026-11-10): a payload that carries `slots` is sent as JSON, the way Captivate's own dashboard
        # creates an episode (nested slot objects cannot ride in a form body). See dashboard_post_roll_slots().
        if "slots" in payload:
            return self._request("POST", "/episodes", json=payload)
        return self._request("POST", "/episodes", data=payload)

    def get_media_slots(self, media_id):
        """The ad slots on one episode's audio (GET /media/{id}/slots/), a list of slot objects. Read-only."""
        response = self._request("GET", f"/media/{media_id}/slots/")
        return response if isinstance(response, list) else (response.get("slots") or [])

    def get_episode(self, episode_id):
        return self._request("GET", f"/episodes/{episode_id}")

    def update_episode(self, episode_id, payload):
        # PUT /episodes/{id} - confirmed against Captivate's live docs
        # (docs.captivate.fm, 2026-09-21) to accept the SAME full field set as
        # create_episode(), not a partial patch: the docs describe it as using
        # "the similar principle" to Update Show, whose own example resends
        # every field, not just the changed one. Callers must always send back
        # every current field value they want preserved, not just what's
        # actually changing - there is no confirmed guarantee that an omitted
        # field is left alone rather than reset.
        return self._request("PUT", f"/episodes/{episode_id}", data=payload)

    def list_episodes(self, captivate_show_id):
        return self._request("GET", f"/shows/{captivate_show_id}/episodes")

    def _request(self, method, path, **kwargs):
        url = f"{BASE_URL}{path}"

        def do_request():
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            if response.status_code >= 500 or response.status_code == 429:
                raise requests.exceptions.ConnectionError(
                    f"{method} {path} returned {response.status_code}: {response.text[:300]}"
                )
            return response

        response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS)

        if not response.ok:
            raise CaptivateError(f"{method} {path} failed ({response.status_code}): {response.text[:1000]}", response.status_code)

        if not response.text:
            return {}
        try:
            return response.json()
        except ValueError:
            raise CaptivateError(f"{method} {path} returned a non-JSON response: {response.text[:1000]}")


# --- shared by the audio-replacement facility (audio_replacement.py) -----------
# (fix_captivate_bitrate.py, a one-off from before this existed, carries its
# own older copies of the first two - left alone deliberately.)

# Captivate reads the `date` field of a create/update (and prints published_date back) as wall-clock time in the show's zone.
# The show reports that zone as America/Vancouver, but Captivate applies it with its OWN time-zone rules, and in November those
# are Pacific STANDARD time (UTC-8): its RSS feed prints every pubDate with "-0800" (confirmed 2026-11-05). The server's own
# tz database (2026c) says British Columbia is on permanent UTC-7, and formatting dates with it (2026-11-03 .. 2026-11-05,
# CAPTIVATE_ACCOUNT_TIMEZONE = America/Vancouver) made Captivate read every date an hour too late: episodes 31 and 32 sat as
# "Scheduled" for 59 minutes and reached the podcast feed (and Apple) an hour after the pipeline published them. The flip to
# Published happened exactly when Captivate's reading of the date came due (episode 32: digits 14:56:33, flip at 22:57:00 UTC).
#
# So dates are written the way Captivate reads them: Pacific time with the US rules, which is America/Los_Angeles. If Captivate
# ever adopts BC's change its dates would start reading an hour EARLIER than sent, which only moves the printed publish time
# back an hour; the failure that matters (an episode left Scheduled) is caught by tick.process_captivate_live_check.
# verify_account_timezone() still checks the name Captivate reports, so a changed account zone stops a publish instead of
# mis-dating it. (History: a 2026-09-12 version read the zone from the API without ever checking the response and silently
# fell back to UTC, which scheduled an episode for the next day.)
CAPTIVATE_REPORTED_ZONE = "America/Vancouver"
CAPTIVATE_ACCOUNT_TIMEZONE = ZoneInfo("America/Los_Angeles")


def parse_captivate_timestamp(value):
    """Captivate returns published_date in two shapes depending on how the
    record was last written: "2026-09-18T15:18:00.000Z" (UTC, POST-created) or
    "2026/09/18 08:18:00" (account-local wall clock, PUT-updated) - confirmed
    live. Parses either into a timezone-aware datetime."""
    if not value:
        return None
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    naive = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
    return naive.replace(tzinfo=CAPTIVATE_ACCOUNT_TIMEZONE)


def episode_update_payload(episode, captivate_show_id, media_id):
    """
    Full-field PUT /episodes/{id} body: every documented field resent from the
    episode's CURRENT values, with only media_id taking a new value. The
    endpoint accepts the same full field set as create and has no confirmed
    partial-update guarantee, so never send a partial body. Fields the read
    response has no value for are omitted rather than guessed.
    """
    published = parse_captivate_timestamp(episode["published_date"])
    return {
        "shows_id": captivate_show_id,
        "title": episode["title"],
        "itunes_title": episode.get("itunes_title") or "",
        "media_id": media_id,
        "date": published.astimezone(CAPTIVATE_ACCOUNT_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "status": episode["status"],
        "shownotes": episode.get("shownotes") or "",
        "summary": episode.get("summary") or "",
        "itunes_subtitle": episode.get("itunes_subtitle") or "",
        "episode_art": episode.get("episode_art") or "",
        "explicit": episode.get("explicit") or "",
        "episode_type": episode.get("episode_type") or "",
        "episode_number": episode["episode_number"],
        "itunes_block": episode.get("itunes_block") or "false",
    }


# --- ad slots on a new episode (2026-11-10) ------------------------------------------------------------------------
# Captivate's campaign system fills DYNAMIC slots. A show on Captivate's v2 ad system (amie_version 2) should have each
# episode carry ONE dynamic post-roll slot whose total_ad_slots equals the show's default (3 for Net Gain Edtech): that is
# what Captivate's own conversion left on episodes 1-29. An episode created through the API without any slot data came out
# (episodes 30-35) with a STATIC post-roll holding a copy of the show's legacy default house ad, which the campaign does not
# fill and the dashboard's bulk editors refuse to touch ("cannot be used on episodes which have AMIE").
#
# The dashboard itself creates v2 episodes by sending `slots` (dynamic, with `adMediaAssignments`, not `subSlots`) and
# `dashboard: true` in a JSON body, so that is what dashboard_post_roll_slots() builds. Whether the API honours it on create
# is being tested on a live episode; tick.check_new_episode_ad_slots() reads the result back and alerts the operator
# whenever the episode did not come out as expected, so the experiment can never fail silently.

def v2_post_roll_count(show):
    """The number of ad positions a new episode should get after its audio: the show's default post-roll count when the show
    is on Captivate's v2 ad system, else 0 (meaning: leave slot creation to Captivate, as before)."""
    if isinstance(show, dict):
        show = show.get("show", show)
    if not isinstance(show, dict) or show.get("amie_version") != 2:
        return 0
    try:
        return max(0, int(show.get("default_post_roll_slots") or 0))
    except (TypeError, ValueError):
        return 0


def dashboard_post_roll_slots(captivate_show_id, media_id, count, slot_id):
    """The slot list the dashboard sends for a new episode on a v2 show: one dynamic post-roll with `count` positions."""
    return [{
        "id": slot_id,
        "parent_media_id": media_id,
        "show_id": captivate_show_id,
        "start": -1,
        "end": -1,
        "type": "post",
        "label": "post-roll",
        "slot_type": "dynamic",
        "total_ad_slots": count,
        "adMediaAssignments": [],
    }]


def slot_problems(slots, expected_count):
    """Plain-English problems with an episode's slots, [] when it is exactly what the campaign needs: one post-roll slot,
    dynamic, with `expected_count` positions and no ad attached to it, and no other slot."""
    slots = slots or []
    if not slots:
        return ["it has no ad slots at all"]
    problems = []
    others = [s for s in slots if s.get("type") != "post"]
    posts = [s for s in slots if s.get("type") == "post"]
    if others:
        problems.append("it also has " + ", ".join(f"a {s.get('type')}-roll slot ({s.get('slot_type')})" for s in others))
    if not posts:
        problems.append("it has no post-roll slot")
        return problems
    if len(posts) > 1:
        problems.append(f"it has {len(posts)} post-roll slots (one expected)")
    for slot in posts:
        if slot.get("slot_type") != "dynamic":
            problems.append(f"its post-roll slot is {slot.get('slot_type')}, not dynamic")
        elif slot.get("total_ad_slots") != expected_count:
            problems.append(f"its dynamic post-roll slot has {slot.get('total_ad_slots')} ad positions, expected {expected_count}")
        if slot.get("subSlots"):
            names = ", ".join(str(sub.get("media_name") or sub.get("media_id")) for sub in slot["subSlots"])
            problems.append(f"an ad is permanently attached to its post-roll slot ({names})")
    return problems
