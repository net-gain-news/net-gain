"""
Operator tool: re-run an episode's metadata with the current rules and push the result to everywhere the episode is
already published (Captivate, the website page, the existing YouTube video, the email signature's newscast line).

    python republish_metadata.py <show_id> <episode_id>              preview: generates and prints, changes nothing
    python republish_metadata.py <show_id> <episode_id> --apply      generate, store and push everywhere
        --keep-slug                                                   leave the website address as it is
        --skip captivate website youtube signature                    leave a destination alone

Written 2026-10-19 after a follow-up story was headlined as if it were new. The YouTube video is edited in place
(same URL, no re-upload); the website address is renamed to match the new headline, with no redirect left behind (fresh pages only).
"""
import argparse
import logging
import re
import sys
import time

import anthropic

import youtube_client as yt
from captivate_client import CaptivateClient, episode_update_payload
from config import load_config
from metadata_generation import generate_metadata_for_episode
from signature_strip import refresh_signature_strip
from tick import (
    anthropic_generate,
    append_notes_footer,
    build_final_youtube_description,
    evaluate_youtube_checklist,
    generate_metadata,
    recent_headlines,
    verify_website_publish,
)
from wp_client import WPClient

logger = logging.getLogger("net_gain.republish")


def slugify(title):
    """'ETS Breach Traced to a Single Stolen Login' -> 'ets-breach-traced-to-a-single-stolen-login' (as WordPress does)."""
    text = (title or "").lower().replace("‑", "-")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _unwrap(response):
    episode = response.get("episode", response)
    return episode[0] if isinstance(episode, list) else episode


def push_to_captivate(captivate, show, meta):
    """Updates the title and show notes of the existing Captivate episode; every other field is resent unchanged."""
    cap_id = (meta.get("ng_url_captivate") or "").rsplit("/", 1)[-1]
    if not cap_id:
        return "skipped (not on Captivate)"
    captivate.ensure_authenticated()
    before = _unwrap(captivate.get_episode(cap_id))
    payload = episode_update_payload(before, show["captivate_show_id"], before["media_id"])
    payload["title"] = meta["ng_meta_captivate_title"]
    payload["shownotes"] = append_notes_footer(meta["ng_meta_captivate_notes"], show.get("captivate_notes_footer"))
    captivate.update_episode(cap_id, payload)
    after = _unwrap(captivate.get_episode(cap_id))
    problems = [
        f"{key} changed ({before.get(key)!r} -> {after.get(key)!r})"
        for key in ("media_id", "status", "episode_number")
        if before.get(key) != after.get(key)
    ]
    if after.get("title") != payload["title"]:
        problems.append(f"title is {after.get('title')!r}, expected {payload['title']!r}")
    if problems:
        raise RuntimeError("Captivate update did not come back as expected: " + "; ".join(problems))
    return f"title now {after['title']!r}"


def push_to_website(wp, episode_id, aioseo_title, rename=True):
    """Re-publishes the page (title, excerpt, SEO row) and, unless told not to, renames its address to match with no
    redirect left behind (the plugin only allows that for a page that is still fresh)."""
    result = wp.publish_website(episode_id)
    if rename:
        result = wp.rename_public_page(episode_id, slugify(aioseo_title))
    verify_website_publish(result["permalink"], wp.get_episode(episode_id).get("meta", {}))
    return result["permalink"]


READ_BACK_ATTEMPTS = 6
READ_BACK_WAIT_SECONDS = 10


def push_to_youtube(wp, show, episode_id, meta, sleep=time.sleep):
    video_id = meta.get("ng_youtube_video_id")
    if not video_id:
        return "skipped (no YouTube video yet)"
    title = meta["ng_meta_youtube_title"]
    description = build_final_youtube_description(
        meta.get("ng_meta_youtube_description", ""), meta.get("ng_url_website", ""), show.get("youtube_description_boilerplate", "")
    )
    tags = meta.get("ng_meta_youtube_tags", []) or []
    thumbnail = wp.download_binary(wp.get_attachment_url(meta["ng_image_16x9_id"]))
    failures = evaluate_youtube_checklist(title, description, tags, thumbnail, show["name"])
    if failures:
        raise RuntimeError("YouTube checklist failed: " + "; ".join(failures))
    service = yt.build_service(wp.get_youtube_access_token(show["id"])["access_token"])
    if yt.get_own_channel_id(service) != show.get("youtube_channel_id"):
        raise RuntimeError("The YouTube connection's channel does not match this show's stored channel; refusing to edit.")
    current = yt.get_video_snippet(service, video_id)
    if current is None:
        raise RuntimeError(f"YouTube video {video_id} was not found.")
    snippet = {
        "title": title, "description": description, "tags": tags, "categoryId": current.get("categoryId", "25"),
        "defaultLanguage": current.get("defaultLanguage", "en"), "defaultAudioLanguage": current.get("defaultAudioLanguage", "en"),
    }
    yt.update_video_snippet(service, video_id, snippet)
    for attempt in range(READ_BACK_ATTEMPTS):      # YouTube's own reads can lag a write by several seconds
        after = yt.get_video_snippet(service, video_id)
        if (after or {}).get("title") == title:
            break
        if attempt < READ_BACK_ATTEMPTS - 1:
            sleep(READ_BACK_WAIT_SECONDS)
    else:
        raise RuntimeError(f"YouTube title is still {(after or {}).get('title')!r} after {READ_BACK_ATTEMPTS} reads, expected {title!r}")
    return f"https://www.youtube.com/watch?v={video_id}"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("show_id", type=int)
    ap.add_argument("episode_id", type=int)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--keep-slug", action="store_true")
    ap.add_argument("--skip", nargs="*", default=[], choices=["captivate", "website", "youtube", "signature"])
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    config = load_config()
    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    client = anthropic.Anthropic(api_key=config["ANTHROPIC_API_KEY"], timeout=600.0)
    show = next(s for s in wp.get_tick_context() if s["id"] == args.show_id)
    meta = wp.get_episode(args.episode_id).get("meta", {})

    if not args.apply:
        result = generate_metadata_for_episode(
            lambda **kw: anthropic_generate(client, **kw), show["name"], meta.get("ng_episode_date", ""),
            meta.get("ng_script_final", ""), recent_titles=recent_headlines(wp, show["id"], meta.get("ng_episode_date", "")),
        )
        print("PREVIEW (nothing stored or pushed):")
        for key in ("captivate_title", "aioseo_title", "youtube_title", "aioseo_description", "website_excerpt"):
            print(f"  {key}: {result[key]}")
        return 0

    generate_metadata(wp, client, show, args.episode_id, force=True)
    meta = wp.get_episode(args.episode_id).get("meta", {})
    print("stored titles:", meta["ng_meta_captivate_title"], "|", meta["ng_meta_aioseo_title"], "|", meta["ng_meta_youtube_title"])
    steps = [
        ("captivate", lambda: push_to_captivate(CaptivateClient(config["CAPTIVATE_USER_ID"], config["CAPTIVATE_API_TOKEN"]), show, meta)),
        ("website", lambda: push_to_website(wp, args.episode_id, meta["ng_meta_aioseo_title"], rename=not args.keep_slug)),
    ]
    results = {}
    for name, fn in steps:
        if name not in args.skip:
            results[name] = fn()
            print(name, "->", results[name])
    if "youtube" not in args.skip:
        meta = wp.get_episode(args.episode_id).get("meta", {})      # the page address may have changed
        print("youtube ->", push_to_youtube(wp, show, args.episode_id, meta))
    if "signature" not in args.skip:
        print("signature ->", "stored" if refresh_signature_strip(wp, show, args.episode_id) else "NOT stored")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
