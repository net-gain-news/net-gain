"""
Links an episode to a Captivate episode that was posted by hand under a different title than the hand-off asked for (the pipeline
normally finds it by title). Reads Captivate, writes nothing to it.

    venv/bin/python adopt_captivate_episode.py <show id> <episode id> <captivate episode id>

The Captivate episode must be Published. Afterwards the website, YouTube and the email carry on as usual.
"""
import logging
import sys

import tick
from captivate_client import CaptivateClient
from config import load_config
from run_lock import ShowBusy, show_lock
from wp_client import WPClient


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    show_id, episode_id, cap_id = int(argv[0]), int(argv[1]), argv[2].strip()
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    captivate = CaptivateClient(config["CAPTIVATE_USER_ID"], config["CAPTIVATE_API_TOKEN"])
    show = next(s for s in wp.get_tick_context() if s["id"] == show_id)

    captivate.ensure_authenticated()
    record = captivate.get_episode(cap_id)
    record = record.get("episode", record) if isinstance(record, dict) else {}
    if record.get("id") != cap_id:
        print(f"Captivate has no episode {cap_id}.")
        return 1
    if record.get("shows_id") and record["shows_id"] != show.get("captivate_show_id"):
        print("That Captivate episode belongs to a different show.")
        return 1
    if record.get("status") != "Published":
        print(f"That Captivate episode is {record.get('status')}, not Published; publish it first.")
        return 1
    try:
        with show_lock(show_id):
            tick.adopt_captivate_episode(wp, captivate, config, show, episode_id, cap_id, note="Linked by hand to the episode posted in Captivate.")
    except ShowBusy:
        print("A background pass is working on this show; try again in a minute.")
        return 1
    print(f"Episode {episode_id} is now linked to Captivate episode {cap_id} ({record.get('title')!r}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
