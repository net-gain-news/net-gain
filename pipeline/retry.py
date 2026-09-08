"""
Standardized retry-with-backoff wrapper (SPEC.md Section 9): "used
consistently across every third-party API call ... not handled ad hoc per
integration." Generic over which exceptions count as retryable so the same
function serves Anthropic now and Captivate/YouTube in later phases -
real precedent for why this matters: a live cron log during the original
single-show build showed two genuine, transient Captivate 503s in one
morning, both recovered automatically a few minutes later.
"""

import logging
import random
import time

logger = logging.getLogger("net_gain.retry")


def call_with_retries(
    fn,
    retryable_exceptions,
    max_retries=5,
    base_delay=2.0,
    max_delay=60.0,
):
    """
    Calls fn() (a zero-arg callable - use a lambda/closure to bind args) and
    retries with exponential backoff + jitter on any exception matching
    retryable_exceptions. Re-raises immediately on anything else, and
    re-raises the last retryable exception once max_retries is exhausted.
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            return fn()
        except retryable_exceptions as exc:
            last_exception = exc
            delay = min(base_delay * (2**attempt) + random.uniform(0, 1), max_delay)
            logger.warning(
                "Retryable error (attempt %d/%d): %s - retrying in %.1fs",
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)

    raise last_exception
