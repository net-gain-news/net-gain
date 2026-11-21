"""
LinkedIn Community Management API client: posts to a company or showcase page (2026-11-20).

Built from LinkedIn's published docs (Posts API, Images API); the first live post is the real test of three points the docs
leave open - whether a showcase page posts as urn:li:organization:{id}, the image upload's HTTP verb, and the exact
finder for a page's recent posts. Each is isolated in one small method below so a correction is a one-line change.

A creating call (the post) is never retried here: if it times out LinkedIn may still have made it, and a blind repeat
would post twice. The caller looks for the post by the episode page's address before every attempt (find_post).
"""

import logging
from urllib.parse import quote

import requests

from retry import call_with_retries

logger = logging.getLogger("net_gain.linkedin_client")

BASE_URL = "https://api.linkedin.com/rest"
DEFAULT_VERSION = "202605"
LOOKUP_COUNT = 20

RETRYABLE_EXCEPTIONS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)


class LinkedInError(RuntimeError):
    """A LinkedIn failure. `transient` is True when waiting and trying again can succeed (network trouble, 429, 5xx)."""

    def __init__(self, message, status=None, transient=False):
        super().__init__(message)
        self.status = status
        self.transient = transient


class LinkedInClient:
    def __init__(self, access_token, expires_at=None, version=DEFAULT_VERSION, timeout=60):
        if not access_token:
            raise LinkedInError("There is no LinkedIn access token.")
        self.expires_at = expires_at
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "Linkedin-Version": version,
                "Accept": "application/json",
                "User-Agent": "NetGainStudio-Pipeline/1.0 (+https://netgain.news)",
            }
        )

    def _request(self, method, url, retry=True, **kwargs):
        def do_request():
            return self.session.request(method, url, timeout=self.timeout, **kwargs)

        try:
            response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS) if retry else do_request()
        except RETRYABLE_EXCEPTIONS as exc:
            raise LinkedInError(f"Could not reach LinkedIn ({type(exc).__name__}).", transient=True) from exc
        if response.status_code >= 400:
            body = (response.text or "")[:500]
            transient = response.status_code == 429 or response.status_code >= 500
            raise LinkedInError(f"LinkedIn {method} {url.replace(BASE_URL, '')} returned {response.status_code}: {body}", status=response.status_code, transient=transient)
        return response

    def find_post(self, author_urn, matches):
        """The first of the page's most recent posts for which matches(post) is true, or None."""
        response = self._request("GET", f"{BASE_URL}/posts?author={quote(author_urn, safe='')}&q=author&count={LOOKUP_COUNT}&sortBy=LAST_MODIFIED")
        try:
            elements = response.json().get("elements", [])
        except ValueError as exc:
            raise LinkedInError("LinkedIn's list of posts was not JSON.", status=response.status_code) from exc
        for post in elements:
            if matches(post):
                return post
        return None

    def upload_image(self, owner_urn, data):
        """Uploads picture bytes for the owner and returns the image's urn:li:image id."""
        init = self._request("POST", f"{BASE_URL}/images?action=initializeUpload", json={"initializeUploadRequest": {"owner": owner_urn}})
        try:
            value = init.json()["value"]
            upload_url, image_urn = value["uploadUrl"], value["image"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LinkedInError("LinkedIn's image upload reply was not what the docs describe.", status=init.status_code) from exc
        self._request("PUT", upload_url, data=data, headers={"Content-Type": "application/octet-stream"})
        return image_urn

    def create_post(self, payload):
        """Makes the post and returns its id (urn). Never retried (see the module note)."""
        response = self._request("POST", f"{BASE_URL}/posts", retry=False, json=payload)
        post_id = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")
        if not post_id:
            raise LinkedInError("LinkedIn accepted the post but did not return its id.", status=response.status_code)
        return post_id
