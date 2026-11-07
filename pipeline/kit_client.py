"""
Kit (kit.com) v4 API client: creates and sends the daily and weekly email broadcasts.

Confirmed against Kit's own v4 docs and a live account on 2026-11-06 (a real draft created through this API rendered
correctly in the show's HTML layout template):
  - POST /v4/broadcasts takes the email BODY as `content` when the template is a "Classic"/HTML layout template; the
    template wraps it. `send_at` null saves a draft; an ISO 8601 time schedules the send.
  - `subscriber_filter` is [{"all": [{"type": "tag", "ids": [...]}], "any": null, "none": null}].
  - GET /v4/broadcasts lists the account's broadcasts newest first (cursor paginated) with their `description`,
    `status` (draft / scheduled / completed) and `send_at`; that listing is how a retry finds an email it already made.
  - Authentication is an API key in the X-Kit-Api-Key header, limited to 120 requests per rolling minute.

A creating POST is never retried here: if it times out, Kit may still have made the broadcast, and a blind repeat would
email subscribers twice. The caller looks the broadcast up by its description before every attempt (find_broadcast), so a
retry on a later pass adopts the one that exists instead of making another.
"""

import logging

import requests

from retry import call_with_retries

logger = logging.getLogger("net_gain.kit_client")

BASE_URL = "https://api.kit.com/v4"

# Kit's own page-size cap for the broadcast list is generous; this many recent broadcasts is a month of daily emails and
# far more than any retry window needs to look back through.
LOOKUP_PAGES = 4
LOOKUP_PAGE_SIZE = 50

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class KitError(RuntimeError):
    """A Kit API failure. `transient` is True when waiting and trying again can succeed (network trouble, 429, 5xx)."""

    def __init__(self, message, status=None, transient=False):
        super().__init__(message)
        self.status = status
        self.transient = transient


class KitClient:
    def __init__(self, api_key, timeout=60):
        if not api_key:
            raise KitError("KIT_API_KEY is not set.")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Kit-Api-Key": api_key,
                "Accept": "application/json",
                # The account's own WAF blocks requests' default User-Agent; every client here uses the same honest custom one.
                "User-Agent": "NetGainStudio-Pipeline/1.0 (+https://netgain.news)",
            }
        )

    # --- plumbing -------------------------------------------------------------------

    def _request(self, method, path, retry=True, **kwargs):
        """One API call. `retry` (default) retries network errors with backoff; pass False for a call that creates something."""
        def do_request():
            return self.session.request(method, BASE_URL + path, timeout=self.timeout, **kwargs)

        try:
            response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS) if retry else do_request()
        except RETRYABLE_EXCEPTIONS as exc:
            raise KitError(f"Could not reach Kit ({type(exc).__name__}).", transient=True) from exc

        if response.status_code >= 400:
            # The raw body, truncated, never the request (which carries the key in a header, not here, but keeps logs tidy).
            body = (response.text or "")[:500]
            transient = response.status_code == 429 or response.status_code >= 500
            raise KitError(f"Kit {method} {path} returned {response.status_code}: {body}", status=response.status_code, transient=transient)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise KitError(f"Kit {method} {path} returned a body that is not JSON.", status=response.status_code) from exc

    # --- reading --------------------------------------------------------------------

    def get_account(self):
        return self._request("GET", "/account")

    def list_templates(self):
        return self._request("GET", "/email_templates", params={"per_page": 100}).get("email_templates", [])

    def list_tags(self):
        return self._request("GET", "/tags", params={"per_page": 100}).get("tags", [])

    def get_broadcast(self, broadcast_id):
        return self._request("GET", f"/broadcasts/{broadcast_id}").get("broadcast", {})

    def find_broadcast(self, marker):
        """
        The newest broadcast whose description contains `marker`, or None. Scans the most recent broadcasts only.
        This is the guard against a duplicate send: every broadcast the pipeline makes carries a unique marker in its
        description, so a retry (after a timeout, a crash between creating and recording, a manual re-run) finds the
        existing one instead of creating a second.
        """
        cursor = None
        for _ in range(LOOKUP_PAGES):
            params = {"per_page": LOOKUP_PAGE_SIZE}
            if cursor:
                params["after"] = cursor
            page = self._request("GET", "/broadcasts", params=params)
            for broadcast in page.get("broadcasts", []):
                if marker in (broadcast.get("description") or ""):
                    return broadcast
            pagination = page.get("pagination") or {}
            if not pagination.get("has_next_page"):
                return None
            cursor = pagination.get("end_cursor")
        return None

    # --- writing --------------------------------------------------------------------

    def create_broadcast(self, *, subject, preview_text, description, content, template_id, tag_id, send_at,
                         published_at, email_address=""):
        """
        Creates a broadcast to everyone carrying Kit tag `tag_id`, in the HTML layout template `template_id`.
        `send_at` is an ISO 8601 UTC string (the email is scheduled for then) or None for an unsent draft.
        Returns Kit's broadcast record. Never retried (see the module note).
        """
        payload = {
            "subject": subject,
            "preview_text": preview_text,
            "description": description,
            "content": content,
            "email_template_id": template_id,
            "public": False,
            "published_at": published_at,
            "send_at": send_at,
            "subscriber_filter": [{"all": [{"type": "tag", "ids": [tag_id]}], "any": None, "none": None}],
        }
        if email_address:
            payload["email_address"] = email_address
        return self._request("POST", "/broadcasts", retry=False, json=payload).get("broadcast", {})

    def delete_broadcast(self, broadcast_id):
        return self._request("DELETE", f"/broadcasts/{broadcast_id}")
