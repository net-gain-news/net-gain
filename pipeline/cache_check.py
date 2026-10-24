"""
Daily check that netgain.news's page cache is still shared between browsers (2026-10-24).

The host's cache used to keep a separate copy of every page per User-Agent string, because the account .htaccess adds
"Vary: User-Agent"; a site-only SetEnv line in netgain.news/.htaccess switched that off. If it comes back (a migration,
a rewritten .htaccess, a change on the host's side) first visits go back to taking seconds on a busy server.

Two quiet fetches of one page as never-seen browsers: the first may rebuild the page, the second must come back from the
shared cache. Emails the usual failure alert when the Vary header names User-Agent again, or when the second browser
still waited a long time on two tries. Otherwise it appends one "ok" line, so a missing line means the check did not run.
"""

import logging
import random
import sys
import time
from datetime import datetime

import requests

from config import load_config
from notify import notify_failure

PAGE = "https://netgain.news/edtech/episodes/"
SLOW_SECONDS = 1.5


def evaluate(vary_header, second_browser_seconds):
    """Returns a list of problems (empty = healthy). second_browser_seconds: the slowest of the retries."""
    problems = []
    if "user-agent" in (vary_header or "").lower():
        problems.append(f'the server sends "Vary: {vary_header}" again, so the page cache is split per browser')
    if second_browser_seconds is not None and second_browser_seconds >= SLOW_SECONDS:
        problems.append(
            f"a second, different browser still waited {second_browser_seconds:.1f}s for a page another browser had just "
            f"loaded (a cached page should take about 0.2s)"
        )
    return problems


def _fetch(agent):
    started = time.monotonic()
    response = requests.get(PAGE, headers={"User-Agent": agent}, timeout=60)
    return response, time.monotonic() - started


def run():
    nonce = random.randint(10**6, 10**7)
    first, _ = _fetch(f"Mozilla/5.0 (X11; Linux x86_64) CacheCheckWarm/{nonce}")
    vary = ", ".join(v for k, v in first.headers.items() if k.lower() == "vary")
    seconds = []
    for attempt in range(2):
        _, took = _fetch(f"Mozilla/5.0 (Windows NT 10.0) CacheCheckProbe/{nonce}-{attempt}")
        seconds.append(took)
        if took < SLOW_SECONDS:
            break
        time.sleep(5)
    return first.status_code, vary, min(seconds) if seconds[-1] >= SLOW_SECONDS else seconds[-1]


def main():
    stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
    try:
        status, vary, seconds = run()
        problems = [] if status == 200 else [f"the page answered HTTP {status}"]
        problems += evaluate(vary, seconds)
    except requests.RequestException as exc:
        problems, vary, seconds = [f"could not fetch the page ({exc.__class__.__name__})"], "", None
    if problems:
        message = "; ".join(problems)
        print(f"{stamp} PROBLEM {message}")
        try:
            notify_failure(load_config(), "netgain.news", "page_cache_check", message)
        except Exception:
            logging.getLogger("net_gain.cache_check").exception("Could not send the alert")
        return 1
    print(f"{stamp} ok (second browser {seconds:.2f}s, Vary: {vary or '-'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
