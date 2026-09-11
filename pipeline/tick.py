"""
Cron entry point (SPEC.md Section 3.1): invoked directly as a CLI process by
a single Canspace cron entry, frequently. Each pass checks every Active show
for anything due. Phase 3 added script generation; Phase 4 added detecting
an elapsed finalization countdown (Section 8.1); Phase 5 added metadata
generation and Captivate publishing (Section 6.1); Phase 6 adds website
publishing (Section 6.2). Metadata generation, Captivate, and website
publishing are all deliberately triggered at the same moment - the closest
point to actual publication, per the Phase 4 amendment deferring generation
work to avoid wasting it on episodes later aborted and replaced. Later
phases extend the same loop further, per CLAUDE.md's architecture note that
manual and scheduled triggers must share one code path.

Each show is processed in complete isolation (Section 3.1: "each show's
processing must run as a fully independent, isolated process with no shared
lock or queue across shows") - one show's failure is logged and alerted on,
never allowed to stop the loop for the rest. Within one show, Captivate and
website publishing are likewise isolated from each other and from script
generation (Section 9: publish-target independence) - a failure in one must
never prevent attempts at the other two.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import anthropic
import requests

from anthropic_client import generate as anthropic_generate
from captivate_client import CaptivateClient
from config import ConfigError, load_config
from image_generation import FALLBACK_META_KEYS, IMAGE_META_KEYS, build_vertex_client, render_images_for_episode
from metadata_generation import generate_metadata_for_episode
from notify import notify_failure
from script_generation import generate_script_for_show
from wp_client import WPClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("net_gain.tick")

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Deliberately not per-show-configured and set well below any plausible real
# script (a spoken daily newscast segment, even a short one, runs well past
# this) rather than tuned to any one show's target length - a general floor
# that a garbage non-script response (an apology, a truncation) would fail,
# not a substitute for the human review script_reviewed already provides.
# Raised from 150 (2026-09-10): a live failure - Claude narrating an extended
# web_search server-tool-limit troubleshooting attempt before giving up - was
# verbose enough to clear 150 words and was wrongly marked done, not degraded.
# 250 is still far below an actual newscast script's length, so this remains
# a floor against non-scripts, not a proxy for real editorial quality.
MIN_SCRIPT_WORDS = 250


def _gmt_mysql(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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
        finalization["finalized_at"] = _gmt_mysql(datetime.now(timezone.utc))
        wp.update_episode_meta(episode["id"], {"ng_finalization": finalization})
        logger.info("Finalization countdown elapsed for episode %s (%s) - marked finalized.", episode["id"], show["name"])


def compute_target_publish_moment(show, finalization):
    """
    The earliest moment (UTC) an episode is allowed to publish. Immediate
    mode: as soon as finalized. Scheduled mode: the next occurrence of
    publish_time (in publish_timezone) at or after the moment it was
    finalized (Section 8.2's "records Pacific afternoon, publishes 7am
    Eastern the next day" example - always the next upcoming occurrence,
    never one that's already passed).
    """
    finalized_raw = finalization.get("finalized_at")
    finalized_at = (
        datetime.fromisoformat(finalized_raw).replace(tzinfo=timezone.utc)
        if finalized_raw
        else datetime.now(timezone.utc)
    )

    if (show.get("publish_mode") or "immediate") != "scheduled":
        return finalized_at

    publish_tz = ZoneInfo(show.get("publish_timezone") or "UTC")
    hour, minute = (int(part) for part in (show.get("publish_time") or "00:00").split(":"))

    finalized_local = finalized_at.astimezone(publish_tz)
    target_local = finalized_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_local <= finalized_local:
        target_local += timedelta(days=1)

    return target_local.astimezone(timezone.utc)


def images_due(show, episode):
    """
    Unlike metadata_generated/Captivate/website publishing, images have no
    publish-timing gate - Section 8.3's amendment requires image generation
    to remain triggerable as soon as audio is received, not deferred to
    publish time. Returns (due, pending_actions).
    """
    step_status = episode.get("step_status") or {}
    if step_status.get("audio_received", {}).get("status", "pending") not in ("done", "degraded"):
        return False, []

    current = step_status.get("images_rendered", {}).get("status", "pending")
    pending = [
        a for a in show.get("pending_actions", []) or []
        if a.get("action") == "generate_images" and a.get("status") == "pending"
    ]
    if current in ("done", "degraded") and not any(a.get("force") for a in pending):
        return False, pending
    return True, pending


def process_image_rendering(wp, client, vertex_client, config, show):
    for episode in show.get("in_flight_episodes", []) or []:
        due, pending = images_due(show, episode)
        if not due:
            continue

        episode_id = episode["id"]
        try:
            wp.update_step(episode_id, "images_rendered", "in_progress")
            render_images_for_episode(
                wp, vertex_client, lambda **kwargs: anthropic_generate(client, **kwargs), show, episode_id
            )
            wp.update_step(episode_id, "images_rendered", "done")
            for action in pending:
                wp.update_action(show["id"], action["id"], "done")
            logger.info("Rendered images for episode %s (%s).", episode_id, show["name"])
        except Exception as exc:
            logger.exception("Image rendering failed for episode %s (%s)", episode_id, show["name"])
            show_details = wp.get_show(show["id"])
            show_meta = show_details.get("meta", {})
            fallback_ids = {spec: show_meta.get(key, 0) for spec, key in FALLBACK_META_KEYS.items()}
            if all(fallback_ids.values()):
                wp.update_episode_meta(
                    episode_id, {IMAGE_META_KEYS[spec]: fid for spec, fid in fallback_ids.items()}
                )
                wp.update_step(episode_id, "images_rendered", "degraded", note=str(exc)[:500])
                for action in pending:
                    wp.update_action(show["id"], action["id"], "done")
            else:
                wp.update_step(episode_id, "images_rendered", "failed", note=str(exc)[:500])
                for action in pending:
                    wp.update_action(show["id"], action["id"], "failed")
                notify_failure(config, show["name"], "images_rendered", str(exc))


def captivate_publish_due(show, episode):
    finalization = episode.get("finalization") or {}
    if finalization.get("state") != "finalized":
        return False

    step_status = episode.get("step_status") or {}
    current = step_status.get("captivate_published", {}).get("status", "pending")
    pending = [
        a
        for a in show.get("pending_actions", []) or []
        if a.get("action") == "publish_captivate" and a.get("status") == "pending"
    ]
    if current in ("done", "degraded") and not any(a.get("force") for a in pending):
        return False

    return datetime.now(timezone.utc) >= compute_target_publish_moment(show, finalization)


def generate_metadata(wp, client, show, episode_id):
    episode = wp.get_episode(episode_id)
    meta = episode.get("meta", {})

    metadata = generate_metadata_for_episode(
        lambda **kwargs: anthropic_generate(client, **kwargs),
        show["name"],
        meta.get("ng_episode_date", ""),
        meta.get("ng_script_final", ""),
    )

    wp.update_episode_meta(
        episode_id,
        {
            "ng_meta_captivate_title": metadata["captivate_title"],
            "ng_meta_captivate_notes": metadata["captivate_notes"],
            "ng_meta_aioseo_title": metadata["aioseo_title"],
            "ng_meta_aioseo_description": metadata["aioseo_description"],
            "ng_meta_youtube_title": metadata["youtube_title"],
            "ng_meta_youtube_description": metadata["youtube_description"],
            "ng_meta_youtube_tags": metadata["youtube_tags"],
        },
    )
    wp.update_step(episode_id, "metadata_generated", "done")


def publish_to_captivate(wp, captivate, show, episode_id, finalization):
    captivate_show_id = show.get("captivate_show_id")
    if not captivate_show_id:
        raise RuntimeError(f"Show '{show['name']}' has no Captivate show connected yet.")

    captivate.ensure_authenticated()
    captivate_show = captivate.get_show(captivate_show_id)
    captivate_timezone = captivate_show.get("time_zone") or "UTC"

    episode = wp.get_episode(episode_id)
    meta = episode.get("meta", {})

    audio_id = meta.get("ng_audio_attachment_id")
    if not audio_id:
        raise RuntimeError("No audio attached to this episode yet.")
    audio_url = wp.get_attachment_url(audio_id)
    audio_bytes = wp.download_binary(audio_url)
    filename = audio_url.rsplit("/", 1)[-1] or "episode.mp3"
    media_id = captivate.upload_media(captivate_show_id, audio_bytes, filename)

    target_moment = compute_target_publish_moment(show, finalization)
    if (show.get("publish_mode") or "immediate") != "scheduled":
        # A small buffer in the past, not "now" exactly, so this is unambiguously
        # in the past relative to Captivate's own clock (SPEC Section 6.1: "a past
        # value publishes immediately").
        target_moment = datetime.now(timezone.utc) - timedelta(minutes=1)
    date_field = target_moment.astimezone(ZoneInfo(captivate_timezone)).strftime("%Y-%m-%d %H:%M:%S")

    title = meta.get("ng_meta_captivate_title") or episode.get("title", {}).get("rendered", "")
    payload = {
        "shows_id": captivate_show_id,
        "title": title,
        "shownotes": meta.get("ng_meta_captivate_notes", ""),
        "media_id": media_id,
        "date": date_field,
        "status": "Published",
    }
    image_id = meta.get("ng_image_square_id")
    if image_id:
        payload["episode_art"] = wp.get_attachment_url(image_id)

    created = captivate.create_episode(payload)
    new_episode_id = created.get("id") or (created.get("episode") or {}).get("id")
    if not new_episode_id:
        raise RuntimeError(f"Captivate did not return an episode id from creation: {created}")

    # Full end-to-end verification (Section 6.1 & 9): re-fetch and confirm, rather
    # than trusting the create call's own success response alone.
    verification = captivate.get_episode(new_episode_id)
    verified_title = verification.get("title") or (verification.get("episode") or {}).get("title")
    if verified_title != title:
        raise RuntimeError(
            f"Verification failed: re-fetched Captivate episode title {verified_title!r} "
            f"does not match what was sent {title!r}."
        )

    public_url = verification.get("link") or (verification.get("episode") or {}).get("link") or ""
    wp.update_episode_meta(episode_id, {"ng_url_captivate": public_url})


def process_captivate_publishes(wp, client, captivate, config, show):
    for episode in show.get("in_flight_episodes", []) or []:
        if not captivate_publish_due(show, episode):
            continue

        episode_id = episode["id"]
        step_status = episode.get("step_status") or {}
        metadata_status = step_status.get("metadata_generated", {}).get("status", "pending")

        try:
            if metadata_status not in ("done", "degraded"):
                generate_metadata(wp, client, show, episode_id)

            wp.update_step(episode_id, "captivate_published", "in_progress")
            publish_to_captivate(wp, captivate, show, episode_id, episode.get("finalization") or {})
            wp.update_step(episode_id, "captivate_published", "done")

            for action in show.get("pending_actions", []) or []:
                if action.get("action") == "publish_captivate" and action.get("status") == "pending":
                    wp.update_action(show["id"], action["id"], "done")
            logger.info("Published episode %s to Captivate for %s.", episode_id, show["name"])
        except Exception as exc:
            logger.exception("Captivate publish failed for episode %s (%s)", episode_id, show["name"])
            wp.update_step(episode_id, "captivate_published", "failed", note=str(exc)[:500])
            for action in show.get("pending_actions", []) or []:
                if action.get("action") == "publish_captivate" and action.get("status") == "pending":
                    wp.update_action(show["id"], action["id"], "failed")
            notify_failure(config, show["name"], "captivate_published", str(exc))


def website_publish_due(show, episode):
    # No pending-action/force handling here, unlike Captivate - Section 8.3 only
    # names script generation, image generation, and Captivate publish as needing
    # a manual trigger; website publishing isn't in that list.
    finalization = episode.get("finalization") or {}
    if finalization.get("state") != "finalized":
        return False

    step_status = episode.get("step_status") or {}
    current = step_status.get("website_published", {}).get("status", "pending")
    if current in ("done", "degraded"):
        return False

    return datetime.now(timezone.utc) >= compute_target_publish_moment(show, finalization)


def verify_website_publish(permalink, episode_meta):
    """Full end-to-end verification (Section 6.2): re-fetch the live page and confirm
    it both returns and actually contains the expected content - never trust the
    creation call's own response alone."""
    if not permalink:
        raise RuntimeError("publish-website did not return a permalink.")

    response = requests.get(permalink, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Re-fetching the published page returned {response.status_code}: {permalink}")

    title = episode_meta.get("ng_meta_aioseo_title") or ""
    if title and title not in response.text:
        raise RuntimeError(f"Published page did not contain the expected title {title!r}: {permalink}")


def process_website_publishes(wp, client, config, show):
    for episode in show.get("in_flight_episodes", []) or []:
        if not website_publish_due(show, episode):
            continue

        episode_id = episode["id"]
        step_status = episode.get("step_status") or {}
        metadata_status = step_status.get("metadata_generated", {}).get("status", "pending")

        try:
            if metadata_status not in ("done", "degraded"):
                generate_metadata(wp, client, show, episode_id)

            wp.update_step(episode_id, "website_published", "in_progress")
            result = wp.publish_website(episode_id)
            verify_website_publish(result.get("permalink"), wp.get_episode(episode_id).get("meta", {}))
            wp.update_step(episode_id, "website_published", "done")
            logger.info("Published episode %s to the website for %s.", episode_id, show["name"])
        except Exception as exc:
            logger.exception("Website publish failed for episode %s (%s)", episode_id, show["name"])
            wp.update_step(episode_id, "website_published", "failed", note=str(exc)[:500])
            notify_failure(config, show["name"], "website_published", str(exc))


def process_show(wp, client, captivate, vertex_client, config, show):
    try:
        check_finalizations(wp, show)
    except Exception:
        logger.exception("Error checking finalizations for %s", show["name"])

    try:
        process_image_rendering(wp, client, vertex_client, config, show)
    except Exception:
        logger.exception("Error processing image rendering for %s", show["name"])

    try:
        process_captivate_publishes(wp, client, captivate, config, show)
    except Exception:
        logger.exception("Error processing Captivate publishes for %s", show["name"])

    try:
        process_website_publishes(wp, client, config, show)
    except Exception:
        logger.exception("Error processing website publishes for %s", show["name"])

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
        word_count = len(draft.split())
        if word_count < MIN_SCRIPT_WORDS:
            # A live incident (2026-09-10) produced non-empty text that wasn't a
            # script at all - Claude explaining it had exhausted its web-search
            # budget and asking to be re-prompted. That's now fixed at the
            # source (anthropic_client.py), but this is a cheap, general
            # backstop against the *shape* of that failure recurring in some
            # other form: no real spoken newscast segment is this short,
            # regardless of show, so flag rather than silently trust it.
            wp.update_step(
                episode["id"],
                "script_generated",
                "degraded",
                note=f"Draft is only {word_count} words - suspiciously short for a real script.",
            )
            logger.warning(
                "Script for %s (%s) is only %d words - flagged degraded, not done.",
                show["name"], episode_date, word_count,
            )
        else:
            wp.update_step(episode["id"], "script_generated", "done")
            logger.info("Generated script for %s (%s).", show["name"], episode_date)
        for action in pending_actions:
            wp.update_action(show["id"], action["id"], "done")
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
    # Explicit bound, not left to the SDK's own default - live incident
    # (2026-09-11) caught a request truly stalled in a raw socket read with no
    # data arriving, for 20+ minutes with no error and no way to tell it apart
    # from a legitimate long search-heavy call from the outside. 600s is
    # generous enough to not cut off a real call (the longest observed
    # successful single call ran ~7 minutes) while still being a real bound
    # rather than an indefinite hang.
    client = anthropic.Anthropic(api_key=config["ANTHROPIC_API_KEY"], timeout=600.0)
    captivate = CaptivateClient(config["CAPTIVATE_USER_ID"], config["CAPTIVATE_API_TOKEN"])
    vertex_client = build_vertex_client(config)

    shows = wp.get_tick_context()
    logger.info("Tick: %d active show(s).", len(shows))

    for show in shows:
        try:
            process_show(wp, client, captivate, vertex_client, config, show)
        except Exception:
            # A failure in due-checking/episode lookup itself (before we even reach
            # process_show's own try/except) must still not stop the other shows.
            logger.exception("Unhandled error processing show %s", show.get("name", show.get("id")))


if __name__ == "__main__":
    main()
