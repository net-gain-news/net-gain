"""
The LinkedIn authorization the pipeline posts with (2026-11-20).

LinkedIn issues one access token per authorizing member, good for about 60 days, and (for an app like ours) no refresh
token: a page admin signs in again when it runs out. The token is saved in pipeline/.state/linkedin-token.json (not in
git, readable only by the account), and the daily pass warns the operator well before it expires.

The one-time and every-two-months sign-in is done with linkedin_tools.py: it prints the address to open, then exchanges the
code LinkedIn puts in the address bar afterwards. No web page of ours has to listen for it.
"""

import json
import os
import tempfile
import time
from urllib.parse import urlencode

import requests

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state", "linkedin-token.json")
AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
SCOPES = "w_organization_social r_organization_social"
WARN_DAYS = 14
UA = {"User-Agent": "NetGainStudio-Pipeline/1.0 (+https://netgain.news)"}


class LinkedInAuthError(RuntimeError):
    pass


def load_token(path=None):
    """The saved token record, or None when there is none (or it cannot be read)."""
    try:
        with open(path or STATE_PATH) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("access_token") or not data.get("expires_at"):
        return None
    return data


def save_token(record, path=None):
    path = path or STATE_PATH
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as out:
            json.dump(record, out)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def seconds_left(record, now=None):
    return float(record["expires_at"]) - (now if now is not None else time.time())


def authorization_url(client_id, redirect_uri, state):
    return AUTHORIZE_URL + "?" + urlencode(
        {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state, "scope": SCOPES}
    )


def exchange_code(client_id, client_secret, redirect_uri, code, now=None):
    """Trades the one-time code for an access token and returns the record to save."""
    response = requests.post(
        TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri},
        headers=UA,
        timeout=30,
    )
    if response.status_code != 200:
        raise LinkedInAuthError(f"LinkedIn returned {response.status_code}: {(response.text or '')[:300]}")
    body = response.json()
    if not body.get("access_token") or not body.get("expires_in"):
        raise LinkedInAuthError("LinkedIn's reply had no access token.")
    obtained = now if now is not None else time.time()
    return {
        "access_token": body["access_token"],
        "expires_at": obtained + float(body["expires_in"]),
        "obtained_at": obtained,
        "scope": body.get("scope", ""),
    }
