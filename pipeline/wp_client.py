"""
Thin REST client over the net-gain-studio plugin's routes (Phase 1/2).
Authenticates via a WordPress Application Password (HTTP Basic Auth) - see
CLAUDE.md: "Python authenticates with a WordPress Application Password, not
a shared database connection - keep the two systems loosely coupled."

Deliberately does not add any new server-side filtering: lookback context
and find-or-create-by-date are done client-side against the existing
Phase 1 REST surface, so this phase needs no PHP changes.
"""

import logging

import requests

from retry import call_with_retries

logger = logging.getLogger("net_gain.wp_client")

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class WPClientError(RuntimeError):
    pass


class WPClient:
    def __init__(self, base_url, username, app_password, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (username, app_password)
        # Confirmed on the real Canspace account (2026-09-09): requests' default
        # "python-requests/x.y.z" User-Agent gets its connection reset outright by
        # the account's own WAF (Imunify360), before WordPress ever sees the
        # request - even identical requests succeed with any other User-Agent.
        self.session.headers["User-Agent"] = "NetGainStudio-Pipeline/1.0 (+https://netgain.news)"

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"

        def do_request():
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            if response.status_code >= 500 or response.status_code == 429:
                # Raised so call_with_retries can catch it - a 4xx (other than 429)
                # is a real client error and should propagate immediately instead.
                raise requests.exceptions.ConnectionError(
                    f"{method} {path} returned {response.status_code}: {response.text[:300]}"
                )
            return response

        response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS)

        if not response.ok:
            raise WPClientError(
                f"{method} {path} failed ({response.status_code}): {response.text[:500]}"
            )
        return response.json() if response.text else None

    # --- tick loop context -------------------------------------------------

    def get_tick_context(self):
        return self._request("GET", "/wp-json/net-gain/v1/tick-context")

    def get_show(self, show_id):
        # /tick-context is a summary for the loop's own due-checking and doesn't
        # carry every Show field (e.g. guidelines_page_id) - the default CPT
        # REST route already exposes all registered meta, so fetch it here
        # rather than adding a PHP route/field for one extra value.
        return self._request("GET", f"/wp-json/wp/v2/ng_show/{show_id}")

    # --- guidelines ----------------------------------------------------------

    def get_page_content(self, page_id):
        page = self._request("GET", f"/wp-json/wp/v2/pages/{page_id}")
        return page.get("content", {}).get("rendered", "")

    # --- media ---------------------------------------------------------------

    def get_attachment_url(self, attachment_id):
        media = self._request("GET", f"/wp-json/wp/v2/media/{attachment_id}")
        return media.get("source_url", "")

    def download_binary(self, url):
        """
        Fetches raw bytes from a URL (e.g. a WP media attachment) for handing
        to a third-party API (Captivate) - a plain GET, not routed through
        _request() since that assumes a JSON response body.
        """

        def do_request():
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code >= 500 or response.status_code == 429:
                raise requests.exceptions.ConnectionError(
                    f"GET {url} returned {response.status_code}"
                )
            return response

        response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS)
        if not response.ok:
            raise WPClientError(f"GET {url} failed ({response.status_code})")
        return response.content

    # --- episodes ------------------------------------------------------------

    def list_episodes_for_show(self, show_id, per_page=100):
        return self._request(
            "GET",
            "/wp-json/wp/v2/ng_episode",
            params={
                "parent": show_id,
                "orderby": "date",
                "order": "desc",
                "per_page": per_page,
            },
        )

    def get_episode(self, episode_id):
        return self._request("GET", f"/wp-json/wp/v2/ng_episode/{episode_id}")

    def find_episode_by_date(self, show_id, episode_date):
        for episode in self.list_episodes_for_show(show_id):
            if episode.get("meta", {}).get("ng_episode_date") == episode_date:
                return episode
        return None

    def create_episode(self, show_id, episode_date, title, talent_user_id=0):
        # WP REST's `date` field needs a full ISO8601 datetime, not a bare
        # YYYY-MM-DD - ng_episode_date (below) is the unambiguous business-logic
        # field; post_date is set purely so the dashboard (Phase 7) can use
        # native after/before/orderby=date REST params, per Phase 1's design.
        payload = {
            "parent": show_id,
            "status": "publish",
            "title": title,
            "date": f"{episode_date}T00:00:00",
            "meta": {"ng_episode_date": episode_date},
        }
        if talent_user_id:
            payload["author"] = talent_user_id
            payload["meta"]["ng_talent_user_id"] = talent_user_id
        return self._request("POST", "/wp-json/wp/v2/ng_episode", json=payload)

    def find_or_create_episode(self, show_id, episode_date, show_title, talent_user_id=0):
        existing = self.find_episode_by_date(show_id, episode_date)
        if existing:
            return existing
        title = f"{show_title} — {episode_date}"
        return self.create_episode(show_id, episode_date, title, talent_user_id)

    def update_episode_meta(self, episode_id, meta):
        return self._request(
            "POST", f"/wp-json/wp/v2/ng_episode/{episode_id}", json={"meta": meta}
        )

    def update_step(self, episode_id, step_key, status, note=""):
        return self._request(
            "PATCH",
            f"/wp-json/net-gain/v1/episodes/{episode_id}/steps/{step_key}",
            json={"status": status, "note": note},
        )

    def publish_website(self, episode_id):
        return self._request("POST", f"/wp-json/net-gain/v1/episodes/{episode_id}/publish-website")

    # --- manual-trigger actions ------------------------------------------------

    def update_action(self, show_id, action_id, status):
        return self._request(
            "PATCH",
            f"/wp-json/net-gain/v1/shows/{show_id}/actions/{action_id}",
            json={"status": status},
        )
