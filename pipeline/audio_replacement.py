"""
Audio replacement for an already-recorded episode (SPEC.md Section 8.4).

An administrator or the show's designated host can swap an episode's audio at
any point after the first upload. WordPress swaps the master attachment and
the website's player immediately and queues a replacement record; this module
(run from the tick loop, like every other manual trigger) carries it through
to the destinations that already have the episode:

- Captivate: the episode's media is replaced and NOTHING ELSE about the
  Captivate episode changes (every field is resent as read; the result is
  re-read and any drift is a failure). Captivate has no replace-in-place for
  media, so a new media file is uploaded and the episode re-pointed at it; the
  old media is left untouched, which is what makes it reversible.
- YouTube: the existing video is deleted and the episode's youtube_published
  step reset to pending, so the ordinary publish path re-creates it from the
  new audio (a different video at a different URL - accepted by the operator).
  No second creation path is built here.
- Website: handled synchronously inside WordPress, not here.

Graphics and metadata are deliberately never regenerated - they are assumed
fine. Destinations that have not published yet need nothing: they read the
episode's audio attachment when their own publish step eventually runs.
"""

import logging
from pathlib import Path

import captivate_client
import youtube_client as yt
from audio_conversion import convert_to_captivate_bitrate

logger = logging.getLogger("net_gain.audio_replacement")

# Fields that must read back exactly as before the Captivate swap.
CAPTIVATE_UNCHANGED_FIELDS = (
    "title", "itunes_title", "episode_number", "status", "shownotes", "summary",
    "itunes_subtitle", "episode_art", "explicit", "episode_type",
)


def captivate_episode_id(meta):
    """ng_url_captivate is https://player.captivate.fm/episode/{id} (see tick.py)."""
    url = (meta.get("ng_url_captivate") or "").strip()
    return url.rstrip("/").rsplit("/", 1)[-1] if url else ""


def _unwrap_episode(response):
    episode = response.get("episode", response)
    if isinstance(episode, list):
        episode = episode[0]
    return episode


def verify_captivate_swap(before, after, new_media_id):
    """Returns a list of problems (empty = the swap changed only the media)."""
    problems = []
    if str(after.get("media_id")) != str(new_media_id):
        problems.append(f"media_id is {after.get('media_id')!r}, expected {new_media_id!r}")
    if after.get("media_url") == before.get("media_url"):
        problems.append("media_url did not change")
    for field in CAPTIVATE_UNCHANGED_FIELDS:
        if (before.get(field) or "") != (after.get(field) or ""):
            problems.append(f"{field} changed: was {before.get(field)!r}, now {after.get(field)!r}")
    if captivate_client.parse_captivate_timestamp(before.get("published_date")) != \
            captivate_client.parse_captivate_timestamp(after.get("published_date")):
        problems.append(
            f"published_date changed: was {before.get('published_date')!r}, now {after.get('published_date')!r}"
        )
    return problems


def swap_captivate_audio(wp, captivate, show, episode_id, meta, record):
    """Returns ("done"|"skipped", note, data). Raises on any failure."""
    cap_id = captivate_episode_id(meta)
    if not cap_id:
        return "skipped", "Not on Captivate yet - it will use the new audio when it publishes.", {}

    # The client signs in lazily, once per process (publish_to_captivate does
    # the same). Without this the first call below is an unauthenticated 401 -
    # found live on the first real replacement (2026-10-02).
    captivate.ensure_authenticated()

    destination = (record.get("destinations") or {}).get("captivate") or {}
    new_attachment_id = record["new_attachment_id"]
    media_id = destination.get("media_id")

    if not media_id:
        audio_url = wp.get_attachment_url(new_attachment_id)
        audio_bytes = convert_to_captivate_bitrate(wp.download_binary(audio_url))
        filename = Path(audio_url.rsplit("/", 1)[-1] or "episode.mp3").stem + ".mp3"
        media_id = captivate.upload_media(show["captivate_show_id"], audio_bytes, filename)
        # Recorded before the PUT: a retry after a failure past this point
        # must re-point the episode, never upload a second copy.
        wp.update_audio_replacement(episode_id, "captivate", "pending", data={"media_id": media_id})

    before = _unwrap_episode(captivate.get_episode(cap_id))
    previous_media_id = before.get("media_id")
    payload = captivate_client.episode_update_payload(before, show["captivate_show_id"], media_id)
    captivate.update_episode(cap_id, payload)

    after = _unwrap_episode(captivate.get_episode(cap_id))
    problems = verify_captivate_swap(before, after, media_id)
    if problems:
        raise RuntimeError(
            "Captivate verification failed after the media swap: " + "; ".join(problems)
            + f". To point the episode back at its previous audio, set its media_id to {previous_media_id}."
        )
    return "done", f"Captivate audio replaced (previous media {previous_media_id} left in place).", {
        "media_id": media_id, "previous_media_id": previous_media_id,
    }


def replace_youtube_video(wp, show, episode_id, meta):
    """Deletes the existing video and resets the step so the normal publish
    path re-creates it. Returns ("done"|"skipped"|"waiting", note, data)."""
    video_id = (meta.get("ng_youtube_video_id") or "").strip()
    step = ((meta.get("ng_step_status") or {}).get("youtube_published") or {}).get("status", "pending")

    if not video_id:
        if step == "in_progress":
            return "waiting", "A YouTube upload is mid-flight with no video id yet - checking again next pass.", {}
        return "skipped", "No YouTube video yet - it will use the new audio when it publishes.", {}

    service = yt.build_service(wp.get_youtube_access_token(show["id"])["access_token"])
    if show.get("youtube_channel_id"):
        # Never delete through a token for the wrong channel.
        if yt.get_own_channel_id(service) != show["youtube_channel_id"]:
            raise RuntimeError("YouTube token's channel does not match this show's connected channel - refusing to delete.")

    deleted_now = yt.delete_video(service, video_id)

    wp.update_episode_meta(episode_id, {
        "ng_youtube_video_id": "",
        "ng_url_youtube": "",
        "ng_youtube_upload_started_at": "",
        "ng_youtube_thumbnail_error": "",
    })
    wp.update_step(
        episode_id, "youtube_published", "pending",
        note=f"Audio replaced: old video {video_id} deleted; re-creating from the new audio.",
    )
    verb = "deleted" if deleted_now else "was already gone"
    return "done", f"Old video {video_id} {verb}; the normal YouTube publish step is re-creating it.", {
        "deleted_video_id": video_id,
    }


def process_audio_replacements(wp, captivate, config, show, notify_failure):
    for record in show.get("audio_replacements") or []:
        episode_id = record["episode_id"]
        destinations = record.get("destinations") or {}

        for name in ("captivate", "youtube"):
            if (destinations.get(name) or {}).get("status", "pending") != "pending":
                continue
            try:
                meta = wp.get_episode(episode_id).get("meta", {})
                if name == "captivate":
                    status, note, data = swap_captivate_audio(wp, captivate, show, episode_id, meta, record)
                else:
                    status, note, data = replace_youtube_video(wp, show, episode_id, meta)
                if status == "waiting":
                    logger.info("Audio replacement %s/%s waiting: %s", episode_id, name, note)
                    continue
                wp.update_audio_replacement(episode_id, name, status, note=note, data=data)
                logger.info("Audio replacement for episode %s - %s: %s (%s)", episode_id, name, status, note)
            except Exception as exc:
                logger.exception("Audio replacement failed for episode %s (%s)", episode_id, name)
                try:
                    wp.update_audio_replacement(episode_id, name, "failed", note=str(exc)[:500])
                except Exception:
                    logger.exception("Could not record the %s failure for episode %s", name, episode_id)
                notify_failure(config, show["name"], f"audio_replacement:{name}", str(exc))
