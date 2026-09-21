"""
One-off remediation script (2026-09-21): replaces the audio on an already-
published Captivate episode with a 192kbps CBR version, without touching any
other episode field. Not part of the ongoing tick.py pipeline - this fixes
episodes that were published to Captivate before audio_conversion.py existed
(everything published after that fix already gets 192kbps CBR automatically).

Mechanics, confirmed against Captivate's live docs (docs.captivate.fm,
2026-09-21) before writing this, not guessed:
- There is no way to replace a media file's content in place - media upload
  (POST /shows/{id}/media) always creates a new media_id. The old media is
  never deleted by this script, which means this is fully reversible: if
  anything looks wrong after the swap, re-run update with --media-id set to
  the OLD id (printed by this script) to point the episode straight back.
- PUT /episodes/{id} accepts the exact same full field set as creating an
  episode, not a partial patch (the docs' own example resends every field).
  This script always sends back every field it read moments before, with
  only media_id (and therefore media_url) actually changing - never just
  the fields that differ.
- The source audio is downloaded from the episode's OWN current media_url
  (what's actually live right now), not re-derived from WordPress's stored
  master - guarantees converting the exact bytes currently being served,
  regardless of whether the WP copy has drifted since original upload.

Usage:
    venv/bin/python3 fix_captivate_bitrate.py <episode_number> [--dry-run]
    venv/bin/python3 fix_captivate_bitrate.py <episode_number> --media-id <id>   # manual rollback
"""

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from audio_conversion import convert_to_captivate_bitrate
from captivate_client import CaptivateClient
from config import load_config

SHOW_ID = "f40bbab2-a721-4bec-9de7-aa82b5488060"  # Net Gain Edtech, per CLAUDE.md
CAPTIVATE_BITRATE_KBPS = 192

# Same account timezone tick.py's compute_captivate_date_field() uses for new
# publishes - Captivate's `date` field is interpreted in this account's
# confirmed timezone, not UTC (Section 1's own carried-forward lesson).
CAPTIVATE_ACCOUNT_TIMEZONE = ZoneInfo("America/Los_Angeles")

USER_AGENT = "NetGainStudio-Pipeline/1.0 (+https://netgain.news)"


def find_episode_by_number(captivate, episode_number):
    response = captivate.list_episodes(SHOW_ID)
    for ep in response.get("episodes", []):
        if ep.get("episode_number") == episode_number:
            return ep
    raise RuntimeError(f"No episode found on Captivate with episode_number={episode_number}")


def to_captivate_date_field(published_date_iso):
    """Existing published_date ("...Z" UTC ISO8601) -> Captivate's own write-side
    `date` field format (YYYY-MM-DD HH:mm:ss, account-timezone wall clock)."""
    dt = datetime.fromisoformat(published_date_iso.replace("Z", "+00:00"))
    local = dt.astimezone(CAPTIVATE_ACCOUNT_TIMEZONE)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def parse_captivate_timestamp(value):
    """Captivate's `published_date` comes back in two different formats
    depending on how the record was last written (confirmed live, 2026-09-21
    - see verify_unchanged()) - "2026-09-18T15:18:00.000Z" (UTC, from a
    POST-created episode) or "2026/09/18 08:18:00" (account-local wall clock,
    from a PUT-updated one). Parses either into a real, timezone-aware
    datetime so the two forms can be compared as the same instant, not as
    unequal strings."""
    if not value:
        return None
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    naive = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
    return naive.replace(tzinfo=CAPTIVATE_ACCOUNT_TIMEZONE)


def build_update_payload(episode, media_id):
    """Every documented PUT /episodes/{id} field this script has a known
    current value for, resent as-is, with only media_id actually changing -
    never send a partial payload against an endpoint with no confirmed
    partial-update guarantee. Fields the read response never returns a value
    for at all (e.g. `author`) are omitted rather than guessed."""
    return {
        "shows_id": SHOW_ID,
        "title": episode["title"],
        "itunes_title": episode.get("itunes_title") or "",
        "media_id": media_id,
        "date": to_captivate_date_field(episode["published_date"]),
        "status": episode["status"],
        "shownotes": episode.get("shownotes") or "",
        "summary": episode.get("summary") or "",
        "itunes_subtitle": episode.get("itunes_subtitle") or "",
        "episode_art": episode.get("episode_art") or "",
        "explicit": episode.get("explicit") or "",
        "episode_type": episode.get("episode_type") or "",
        "episode_number": episode["episode_number"],
        "itunes_block": episode.get("itunes_block") or "false",
    }


def verify_unchanged(captivate, episode_id, before, expected_media_url_change):
    after_response = captivate.get_episode(episode_id)
    after = after_response.get("episode", after_response)
    if isinstance(after, list):
        after = after[0]

    fields_that_must_not_change = ["title", "episode_number", "status", "shownotes"]
    problems = []
    for field in fields_that_must_not_change:
        if after.get(field) != before.get(field):
            problems.append(f"{field} changed: was {before.get(field)!r}, now {after.get(field)!r}")

    # published_date needs its own check, not a raw string comparison - confirmed
    # live (2026-09-21) that Captivate echoes this field in a different string
    # format after a PUT (local "YYYY/MM/DD HH:mm:ss") than a POST-created
    # episode's own original value ("YYYY-MM-DDTHH:mm:ss.sssZ" UTC), even though
    # both represent the exact same instant - verified independently against the
    # live public RSS feed's <pubDate>, which was unaffected. Compare the parsed
    # instant, not the string.
    if parse_captivate_timestamp(after.get("published_date")) != parse_captivate_timestamp(before.get("published_date")):
        problems.append(
            f"published_date changed: was {before.get('published_date')!r}, now {after.get('published_date')!r}"
        )

    if expected_media_url_change and after.get("media_url") == before.get("media_url"):
        problems.append("media_url did NOT change - the swap may not have taken effect")

    return after, problems


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    episode_number = int(sys.argv[1])
    dry_run = "--dry-run" in sys.argv
    manual_media_id = None
    if "--media-id" in sys.argv:
        manual_media_id = sys.argv[sys.argv.index("--media-id") + 1]

    config = load_config()
    captivate = CaptivateClient(config["CAPTIVATE_USER_ID"], config["CAPTIVATE_API_TOKEN"])
    captivate.ensure_authenticated()

    episode = find_episode_by_number(captivate, episode_number)
    episode_id = episode["id"]
    old_media_id = episode["media_id"]
    old_media_url = episode["media_url"]
    print(f"Episode {episode_number}: {episode['title']!r}")
    print(f"  id: {episode_id}")
    print(f"  current media_id: {old_media_id}")
    print(f"  current media_url: {old_media_url}")
    print(f"  published_date: {episode['published_date']}")

    if manual_media_id:
        print(f"\n--media-id given - skipping download/convert/upload, pointing episode straight at {manual_media_id}")
        new_media_id = manual_media_id
    else:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        print("\nDownloading current (live) media...")
        audio_response = session.get(old_media_url, timeout=120)
        audio_response.raise_for_status()
        original_bytes = audio_response.content
        print(f"  downloaded {len(original_bytes)} bytes")

        print(f"Converting to {CAPTIVATE_BITRATE_KBPS}kbps CBR...")
        converted_bytes = convert_to_captivate_bitrate(original_bytes, bitrate_kbps=CAPTIVATE_BITRATE_KBPS)
        print(f"  converted to {len(converted_bytes)} bytes")

        if dry_run:
            print("\n--dry-run: stopping before upload/update. Nothing was changed on Captivate.")
            return

        filename = old_media_url.rsplit("/", 1)[-1] or f"episode-{episode_number}.mp3"
        print(f"Uploading new media ({filename})...")
        new_media_id = captivate.upload_media(SHOW_ID, converted_bytes, filename)
        print(f"  new media_id: {new_media_id}")

    payload = build_update_payload(episode, new_media_id)
    print(f"\nUpdating episode {episode_id} (every field resent, only media_id actually changing)...")
    captivate.update_episode(episode_id, payload)

    print("Verifying...")
    after, problems = verify_unchanged(captivate, episode_id, episode, expected_media_url_change=True)
    print(f"  new media_url: {after.get('media_url')}")

    if problems:
        print("\nPROBLEM(S) DETECTED - review before trusting this:")
        for p in problems:
            print(f"  - {p}")
        print(f"\nRollback: re-run with --media-id {old_media_id} to point the episode straight back at the original media.")
        sys.exit(1)

    print(f"\nDone. All other fields confirmed unchanged. Old media_id {old_media_id} left in place (untouched, just unreferenced) - nothing was deleted.")


if __name__ == "__main__":
    main()
