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

import requests

from retry import call_with_retries

logger = logging.getLogger("net_gain.captivate_client")

BASE_URL = "https://api.captivate.fm"

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class CaptivateError(RuntimeError):
    pass


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
        response = self._request("GET", f"/shows/{captivate_show_id}/episodes")

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
        return self._request("POST", "/episodes", data=payload)

    def get_episode(self, episode_id):
        return self._request("GET", f"/episodes/{episode_id}")

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
            raise CaptivateError(f"{method} {path} failed ({response.status_code}): {response.text[:1000]}")

        if not response.text:
            return {}
        try:
            return response.json()
        except ValueError:
            raise CaptivateError(f"{method} {path} returned a non-JSON response: {response.text[:1000]}")
