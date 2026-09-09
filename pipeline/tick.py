"""
Cron entry point (SPEC.md Section 3.1): invoked directly as a CLI process by
a single Canspace cron entry, frequently. Each pass checks every Active show
for anything due. Phase 3 added script generation; Phase 4 adds detecting an
elapsed finalization countdown (Section 8.1) - the visible countdown in the
UI reflects this state, it is not the source of truth for it, so it must
resolve correctly even if no browser tab is open. Later phases extend the
same loop further, per CLAUDE.md's architecture note that manual and
scheduled triggers must share one code path.

Each show is processed in complete isolation (Section 3.1: "each show's
processing must run as a fully independent, isolated process with no shared
lock or queue across shows") - one show's failure is logged and alerted on,
never allowed to stop the loop for the rest.
"""

import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import anthropic

from anthropic_client import generate as anthropic_generate
from config import ConfigError, load_config
from notify import notify_failure
from script_generation import generate_script_for_show
from wp_client import WPClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("net_gain.tick")

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def script_generation_due(show, today_str, now_local):
    pending = [
        action
        for action in show.get("pending_actions", []) or []
        if action.get("action") == "generate_script" and action.get("status") == "pending"
    ]
    if pending:
        return pending[0].get("episode_date") or today_str, pending

    recording_days = show.get("recording_days") or []
    target_time = show.get("target_time") or ""
    if WEEKDAY_KEYS[now_local.weekday()] in recording_days and target_time:
        if now_local.strftime("%H:%M") >= target_time:
            return today_str, []

    return None, []


def finalization_elapsed(finalization):
    """
    True if a counting_down finalization's countdown has run out.
    countdown_started_at is stored in GMT (WordPress's current_time('mysql', true))
    specifically so this comparison is unambiguous regardless of the WP site's
    configured timezone (Section 1: "never assume a host's timezone").
    """
    if finalization.get("state") != "counting_down":
        return False
    started_raw = finalization.get("countdown_started_at")
    if not started_raw:
        return False
    started = datetime.fromisoformat(started_raw).replace(tzinfo=timezone.utc)
    total_seconds = int(finalization.get("countdown_seconds") or 90)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return elapsed >= total_seconds


def check_finalizations(wp, show):
    for episode in show.get("in_flight_episodes", []) or []:
        finalization = episode.get("finalization") or {}
        if not finalization_elapsed(finalization):
            continue
        finalization["state"] = "finalized"
        wp.update_episode_meta(episode["id"], {"ng_finalization": finalization})
        logger.info("Finalization countdown elapsed for episode %s (%s) - marked finalized.", episode["id"], show["name"])


def process_show(wp, client, config, show):
    try:
        check_finalizations(wp, show)
    except Exception:
        logger.exception("Error checking finalizations for %s", show["name"])

    tz_name = show.get("recording_timezone") or "UTC"
    now_local = datetime.now(ZoneInfo(tz_name))
    today_str = now_local.date().isoformat()

    episode_date, pending_actions = script_generation_due(show, today_str, now_local)
    if episode_date is None:
        return

    episode = wp.find_or_create_episode(
        show["id"], episode_date, show["name"], show.get("effective_talent_today") or 0
    )
    step_status = episode.get("meta", {}).get("ng_step_status", {}) or {}
    current_status = step_status.get("script_generated", {}).get("status", "pending")

    # A pending action's force=True (set only by an explicit "Regenerate" click on
    # an already-completed step, Section 8.2) is the one thing allowed to bypass
    # the ordinary idempotent skip - see Phase 4's plan for why this is needed.
    forced = any(action.get("force") for action in pending_actions)

    if current_status in ("done", "degraded") and not forced:
        for action in pending_actions:
            wp.update_action(show["id"], action["id"], "done")
        logger.info("Script already generated for %s on %s - skipping.", show["name"], episode_date)
        return

    wp.update_step(episode["id"], "script_generated", "in_progress")

    try:
        show_details = wp.get_show(show["id"])
        show_for_generation = dict(show, guidelines_page_id=show_details.get("meta", {}).get("ng_guidelines_page_id", 0))

        recent_episodes = wp.list_episodes_for_show(show["id"])
        draft = generate_script_for_show(
            wp,
            lambda **kwargs: anthropic_generate(client, **kwargs),
            show_for_generation,
            episode_date,
            recent_episodes,
        )
        wp.update_episode_meta(episode["id"], {"ng_script_draft": draft})
        wp.update_step(episode["id"], "script_generated", "done")
        for action in pending_actions:
            wp.update_action(show["id"], action["id"], "done")
        logger.info("Generated script for %s (%s).", show["name"], episode_date)
    except Exception as exc:
        logger.exception("Script generation failed for %s (%s)", show["name"], episode_date)
        wp.update_step(episode["id"], "script_generated", "failed", note=str(exc)[:500])
        for action in pending_actions:
            wp.update_action(show["id"], action["id"], "failed")
        notify_failure(config, show["name"], "script_generated", str(exc))


def main():
    try:
        config = load_config()
    except ConfigError as exc:
        logger.error(str(exc))
        sys.exit(1)

    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    client = anthropic.Anthropic(api_key=config["ANTHROPIC_API_KEY"])

    shows = wp.get_tick_context()
    logger.info("Tick: %d active show(s).", len(shows))

    for show in shows:
        try:
            process_show(wp, client, config, show)
        except Exception:
            # A failure in due-checking/episode lookup itself (before we even reach
            # process_show's own try/except) must still not stop the other shows.
            logger.exception("Unhandled error processing show %s", show.get("name", show.get("id")))


if __name__ == "__main__":
    main()
