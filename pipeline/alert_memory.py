"""
Remembers which alerts have already been sent, so a check that runs on every one-minute pass tells the operator once.

A small JSON file (pipeline/.state/alerts-sent.json, not in git). A missing or unreadable file reads as "nothing sent yet",
and an entry older than two weeks is dropped when a new one is written.
"""
import json
import os
import tempfile
import time

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state", "alerts-sent.json")
RETAIN_SECONDS = 14 * 24 * 3600


def _read(path):
    try:
        with open(path) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def already_sent(key, path=None):
    return key in _read(path or DEFAULT_PATH)


def mark_sent(key, path=None, now=None):
    """Records the alert. Raises OSError if the file cannot be written (the caller decides what that means)."""
    path = path or DEFAULT_PATH
    now = now if now is not None else time.time()
    data = {k: v for k, v in _read(path).items() if isinstance(v, (int, float)) and now - v < RETAIN_SECONDS}
    data[key] = now
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as out:
            json.dump(data, out)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
