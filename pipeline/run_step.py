"""
Operator tool: run ONE step of one episode on request, through the same code the background job uses.

    python run_step.py <show_id> <episode_id> <step> [--override-hand-edits] [--allow-orphan-check-done]

    images     render the episode's three graphics again (replaces the stored ones)
    metadata   generate the titles, notes and descriptions again (leaves SEO fields an editor wrote by hand alone)
    captivate  publish to Captivate; if the episode is already on Captivate, update its title and notes there instead,
               never create a second episode (to swap the audio, use "Replace audio")
    website    publish or refresh the episode's page, then the signature strip once Captivate is live too. Refuses when an
               editor has hand-edited the page's SEO fields, since a re-publish would put the generated ones back
               (--override-hand-edits accepts that)
    strip      rebuild the email-signature strip from the latest stored title and length
    youtube    check on a video already uploaded, or upload one if none was ever started. Never uploads a second video:
               it refuses when an upload was started but never recorded a video id (look for an orphan on the channel
               first, then pass --allow-orphan-check-done)

Takes the show's lock, waiting up to three minutes for a pass that is already running, so it never races the background
job. Exits non-zero when the step ends anywhere other than done or degraded.
"""
import argparse
import logging
import sys

import anthropic

import tick
from captivate_client import CaptivateClient
from captivate_mode import is_manual
from config import load_config
from image_generation import build_vertex_client
from republish_metadata import push_to_captivate
from run_lock import ShowBusy, show_lock
from signature_strip import refresh_signature_strip
from wp_client import WPClient

logger = logging.getLogger("net_gain.run_step")

STEPS = ("images", "metadata", "captivate", "website", "strip", "youtube")
STEP_KEYS = {
    "images": "images_rendered",
    "metadata": "metadata_generated",
    "captivate": "captivate_published",
    "website": "website_published",
    "strip": None,
    "youtube": "youtube_published",
}
LOCK_WAIT_SECONDS = 180


class StepRefused(Exception):
    """The step was not run, and why."""


def _episode_view(wp, episode_id):
    meta = wp.get_episode(episode_id).get("meta", {})
    return {
        "id": episode_id,
        "episode_date": meta.get("ng_episode_date", ""),
        "step_status": meta.get("ng_step_status") or {},
        "finalization": meta.get("ng_finalization") or {},
    }, meta


def run_step(step, wp, client, config, show, episode_id, make_captivate, make_vertex, override_hand_edits=False, allow_orphan_check_done=False):
    """Runs the step; returns a one-line outcome. Raises StepRefused for a guarded case, never for a step's own failure
    (that is recorded on the episode and alerted, exactly as in the background job)."""
    if step not in STEPS:
        raise StepRefused(f"Unknown step {step!r}; choose one of {', '.join(STEPS)}.")
    episode, meta = _episode_view(wp, episode_id)
    audio_done = (episode["step_status"].get("audio_received") or {}).get("status") in ("done", "degraded")
    if step != "strip" and not audio_done:
        raise StepRefused("No audio has been uploaded for this episode yet.")

    if step == "images":
        tick.render_episode_images(wp, client, make_vertex(), config, show, episode, [])

    elif step == "metadata":
        tick.generate_metadata(wp, client, show, episode_id, force=True)

    elif step == "captivate":
        if meta.get("ng_url_captivate") and is_manual(config, show):
            raise StepRefused(
                "Captivate episodes for this show are posted by hand, and an update through the API adds a second ad slot. "
                "Change the title or notes in the Captivate dashboard."
            )
        if meta.get("ng_url_captivate"):
            captivate = make_captivate()
            outcome = push_to_captivate(captivate, show, meta)
            return f"already on Captivate - updated in place: {outcome}"
        tick.publish_episode_to_captivate(wp, client, make_captivate(), config, show, episode)

    elif step == "website":
        if meta.get("ng_seo_hand_edited") and not override_hand_edits:
            raise StepRefused(
                "An editor hand-edited this page's SEO title/description. Re-publishing would put the generated ones "
                "back. Pass --override-hand-edits if that is what you want."
            )
        if override_hand_edits and meta.get("ng_seo_hand_edited"):
            wp.update_episode_meta(episode_id, {"ng_seo_hand_edited": ""})
        tick.publish_episode_to_website(wp, client, config, show, episode, make_captivate())

    elif step == "strip":
        if not refresh_signature_strip(wp, show, episode_id):
            return "strip NOT stored (see the log)"
        return "strip stored"

    elif step == "youtube":
        steps = episode["step_status"]
        if not show.get("youtube_channel_id"):
            raise StepRefused("This show has no YouTube channel connected.")
        for key in ("captivate_published", "website_published"):
            if (steps.get(key) or {}).get("status") not in ("done", "degraded"):
                raise StepRefused("YouTube goes after Captivate and the website; one of them is not live yet.")
        if meta.get("ng_youtube_video_id"):
            mode = "verify"
        else:
            if meta.get("ng_youtube_upload_started_at") and not allow_orphan_check_done:
                raise StepRefused(
                    "An upload was started for this episode but no video id was recorded. Check the channel's Content "
                    "page for an orphaned upload first; if there is none, pass --allow-orphan-check-done."
                )
            mode = "upload"
        tick.publish_episode_to_youtube(wp, client, config, show, episode, mode, [])

    key = STEP_KEYS[step]
    status = ((wp.get_episode(episode_id).get("meta", {}).get("ng_step_status") or {}).get(key) or {})
    return f"{step}: {status.get('status', 'unknown')}" + (f" - {status['note']}" if status.get("note") else "")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("show_id", type=int)
    ap.add_argument("episode_id", type=int)
    ap.add_argument("step", choices=STEPS)
    ap.add_argument("--override-hand-edits", action="store_true")
    ap.add_argument("--allow-orphan-check-done", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()
    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    client = anthropic.Anthropic(api_key=config["ANTHROPIC_API_KEY"], timeout=600.0)
    show = next((s for s in wp.get_tick_context() if s["id"] == args.show_id), None)
    if show is None:
        print(f"Show {args.show_id} is not an active show.")
        return 2

    try:
        with show_lock(args.show_id, wait_seconds=LOCK_WAIT_SECONDS):
            outcome = run_step(
                args.step, wp, client, config, show, args.episode_id,
                make_captivate=lambda: CaptivateClient(config["CAPTIVATE_USER_ID"], config["CAPTIVATE_API_TOKEN"]),
                make_vertex=lambda: build_vertex_client(config),
                override_hand_edits=args.override_hand_edits,
                allow_orphan_check_done=args.allow_orphan_check_done,
            )
    except ShowBusy:
        print("The background job has held this show for over three minutes; try again shortly.")
        return 3
    except StepRefused as refused:
        print(f"NOT RUN: {refused}")
        return 2

    print(outcome)
    return 0 if ("failed" not in outcome and "NOT stored" not in outcome) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
