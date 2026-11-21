"""
Operator tools for the LinkedIn posting step (2026-11-20). Run from the pipeline folder on the server:

  python3 linkedin_tools.py auth-url              prints the address a page administrator opens to sign in
  python3 linkedin_tools.py exchange "<address>"  saves the sign-in from the address LinkedIn sent the browser to afterwards
  python3 linkedin_tools.py status                says whether a sign-in is saved and when it expires
  python3 linkedin_tools.py check PAGE_ID         reads the page's recent posts with the saved sign-in (proves it can reach the page)
  python3 linkedin_tools.py preview EPISODE_ID    prints exactly what would be posted for an episode, posts nothing

The sign-in lasts about 60 days; repeat auth-url and exchange before it runs out (the daily job emails a warning two weeks ahead).
"""

import os
import secrets
import sys
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import linkedin_post
import linkedin_token
from config import load_config
from linkedin_client import LinkedInClient, LinkedInError

STATE_FILE = os.path.join(os.path.dirname(linkedin_token.STATE_PATH), "linkedin-state")


def _need(config, *names):
    missing = [n for n in names if not config.get(n)]
    if missing:
        sys.exit("Missing in the environment: " + ", ".join(missing))


def parse_redirect(value):
    """(code, state) from the address LinkedIn redirected to, or (value, None) when only a bare code was pasted."""
    value = value.strip()
    if "code=" not in value:
        return value, None
    query = parse_qs(urlparse(value).query)
    if "error" in query:
        sys.exit("LinkedIn reported: " + query["error"][0] + " - " + (query.get("error_description", [""])[0]))
    return (query.get("code", [""])[0], query.get("state", [None])[0])


def cmd_auth_url(config):
    _need(config, "LINKEDIN_CLIENT_ID", "LINKEDIN_REDIRECT_URI")
    state = secrets.token_urlsafe(16)
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as handle:
        handle.write(state)
    print("Open this address while signed in to LinkedIn as an administrator of the page, then allow access:\n")
    print(linkedin_token.authorization_url(config["LINKEDIN_CLIENT_ID"], config["LINKEDIN_REDIRECT_URI"], state))
    print("\nLinkedIn then sends the browser to your redirect address (the page may show an error; that is fine).")
    print('Copy the whole address from the browser bar and run:  python3 linkedin_tools.py exchange "<that address>"')


def cmd_exchange(config, value):
    _need(config, "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_REDIRECT_URI")
    code, state = parse_redirect(value)
    if not code:
        sys.exit("No code found in what was pasted.")
    if state is not None:
        try:
            expected = open(STATE_FILE).read().strip()
        except OSError:
            sys.exit("No sign-in was started from here (run auth-url first).")
        if state != expected:
            sys.exit("That address does not belong to the sign-in started here. Run auth-url again.")
    record = linkedin_token.exchange_code(config["LINKEDIN_CLIENT_ID"], config["LINKEDIN_CLIENT_SECRET"], config["LINKEDIN_REDIRECT_URI"], code)
    linkedin_token.save_token(record)
    print("Saved. Expires", datetime.fromtimestamp(record["expires_at"], timezone.utc).strftime("%Y-%m-%d"), "UTC. Scopes:", record.get("scope") or "(not reported)")


def cmd_status(config):
    record = linkedin_token.load_token()
    if record is None:
        print("No LinkedIn sign-in is saved.")
        return
    left = linkedin_token.seconds_left(record)
    when = datetime.fromtimestamp(record["expires_at"], timezone.utc).strftime("%Y-%m-%d")
    print(f"Signed in; expires {when} UTC ({int(left // 86400)} days left)." if left > 0 else f"The saved sign-in expired on {when} UTC.")


def cmd_check(config, page_id):
    record = linkedin_token.load_token()
    if record is None:
        sys.exit("No LinkedIn sign-in is saved.")
    client = LinkedInClient(record["access_token"], record["expires_at"], config["LINKEDIN_API_VERSION"])
    try:
        found = []
        client.find_post(linkedin_post.author_urn(page_id), lambda post: found.append(post) and False)
    except LinkedInError as exc:
        sys.exit(f"Could not read the page's posts: {exc}")
    print(f"Reached the page: {len(found)} recent post(s) listed.")


def cmd_preview(config, episode_id):
    from wp_client import WPClient
    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    meta = wp.get_episode(int(episode_id)).get("meta", {})
    paragraphs = linkedin_post.notes_paragraphs(meta.get("ng_meta_captivate_notes", ""))
    text = linkedin_post.build_commentary(paragraphs, meta.get("ng_url_website", ""))
    print(text)
    print(f"\n--- {len(text)} of {linkedin_post.COMMENTARY_LIMIT} characters; card: {meta.get('ng_meta_captivate_title')!r}")


def main(argv):
    if len(argv) < 2 or argv[1] not in ("auth-url", "exchange", "status", "check", "preview"):
        sys.exit(__doc__)
    config = load_config()
    command, args = argv[1], argv[2:]
    if command == "auth-url":
        cmd_auth_url(config)
    elif command == "exchange":
        cmd_exchange(config, " ".join(args)) if args else sys.exit("Give the address (or code) after exchange.")
    elif command == "status":
        cmd_status(config)
    elif command == "check":
        cmd_check(config, args[0]) if args else sys.exit("Give the page id after check.")
    elif command == "preview":
        cmd_preview(config, args[0]) if args else sys.exit("Give the episode id after preview.")


if __name__ == "__main__":
    main(sys.argv)
