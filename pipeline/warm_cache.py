"""
Keeps netgain.news's server-side page cache (60 minutes) warm, so a real visitor rarely pays for rebuilding a page
(0.5 s normally, 3-7 s when the shared server is busy; 2026-10-24).

Run from cron every 5 minutes: cached pages answer in ~0.2 s and cost the server nothing, and a page whose cache has
just expired is rebuilt here, within five minutes, instead of by the next visitor.

Until 2026-10-24 the host's cache kept a separate copy per User-Agent string (the account .htaccess adds "Vary: User-Agent"),
so a warm-up only covered the browsers it imitated. A site-only line in netgain.news/.htaccess now switches that header off,
so one User-Agent warms the copy every visitor gets; cache_check.py verifies daily that this still holds.

Silent when everything is quick and fine; writes one line when a page is slow or fails.
"""

import sys
import time
from datetime import datetime

import requests

BASE = "https://netgain.news"
PATHS = ["/", "/edtech/", "/edtech/episodes/", "/edtech/index/", "/about/"]
LATEST = "/edtech/latest/"          # redirects to the newest episode page, which is the page most visitors want
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.5 Safari/605.1.15",
]
TIMEOUT = 60
SLOW_SECONDS = 2.0


def latest_episode_path(session):
    """The newest episode's path, from the redirect (never followed, so the redirect itself is not cached anywhere)."""
    response = session.get(BASE + LATEST, allow_redirects=False, timeout=TIMEOUT)
    location = response.headers.get("Location", "")
    return location[len(BASE):] if location.startswith(BASE) else ""


def urls_to_warm(latest_path):
    paths = list(PATHS) + ([latest_path] if latest_path else [])
    return [BASE + p for p in paths]


def problems(results):
    """results: list of (url, user_agent_index, status, seconds). Returns the lines worth logging."""
    lines = []
    for url, ua_index, status, seconds in results:
        if status != 200:
            lines.append(f"HTTP {status} {url} (UA {ua_index})")
        elif seconds >= SLOW_SECONDS:
            lines.append(f"slow {seconds:.1f}s {url} (UA {ua_index})")
    return lines


def main():
    results = []
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENTS[0]
    try:
        latest = latest_episode_path(session)
    except requests.RequestException as exc:
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} could not find the latest episode: {exc.__class__.__name__}")
        latest = ""
    for url in urls_to_warm(latest):
        for index, agent in enumerate(USER_AGENTS):
            started = time.monotonic()
            try:
                status = session.get(url, headers={"User-Agent": agent}, timeout=TIMEOUT).status_code
            except requests.RequestException as exc:
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S} failed {url} (UA {index}): {exc.__class__.__name__}")
                continue
            results.append((url, index, status, time.monotonic() - started))
    for line in problems(results):
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
