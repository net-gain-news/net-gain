"""
One background-job pass per show at a time. Cron starts the job every minute, so a pass that is still working (a long
script, a slow upload) must make the next one step aside instead of racing it: two passes both seeing an episode as
unpublished would create it twice on Captivate. The lock is a kernel `flock` on a file, which the system releases the
moment the holding process ends, however it ends - there is no stale lock to clear by hand.
"""
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path

LOCK_DIR = Path(__file__).resolve().parent / ".locks"


class ShowBusy(Exception):
    """Another pass holds this show's lock. `held_seconds` is how long it has held it, if known."""

    def __init__(self, show_id, held_seconds=None):
        super().__init__(f"Show {show_id} is being processed by another run.")
        self.show_id = show_id
        self.held_seconds = held_seconds


def _held_seconds(fd):
    try:
        started = float(os.pread(fd, 64, 0).decode().strip() or 0)
    except (OSError, ValueError):
        return None
    return max(0.0, time.time() - started) if started else None


@contextmanager
def show_lock(show_id, wait_seconds=0, directory=None):
    """Hold the show's lock for the block; raise ShowBusy if it can't be had within `wait_seconds`."""
    directory = Path(directory) if directory else LOCK_DIR
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(directory / f"show-{int(show_id)}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + max(0, wait_seconds)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                held = _held_seconds(fd)
                os.close(fd)
                raise ShowBusy(show_id, held)
            time.sleep(1)
    try:
        os.ftruncate(fd, 0)
        os.pwrite(fd, str(time.time()).encode(), 0)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock
