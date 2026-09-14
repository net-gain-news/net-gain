"""
YouTube Data API v3 client (SPEC.md Section 6.3).

Uses google-api-python-client + google-auth, a deliberate, scoped exception
to this project's usual lean-hand-rolled-requests-client pattern
(captivate_client.py, wp_client.py) - resumable video upload is a genuine
multi-step protocol (session init, chunked PUT, resume-on-interruption)
where a hand-rolled bug risks a corrupted or duplicated *public* video, and
this project already made the identical exception for google-genai in the
image pipeline rather than hand-rolling Vertex AI's own call shape. No
custom User-Agent is needed here (unlike every other client in this
pipeline) - Canspace's own WAF only gates *inbound* requests to netgain.news,
not outbound calls to Google.

This module never refreshes or stores credentials itself - it's handed a
short-lived access token per call (minted by WordPress, see
wp_client.get_youtube_access_token) and builds a token-only, non-refreshing
Credentials object. The refresh token and OAuth client secret never reach
this process (SPEC Section 3.3).

Deliberately asymmetric retry policy: thumbnails.set/videos.list/
channels.list are idempotent and wrapped in call_with_retries via
_execute_with_retry(). videos.insert is NOT wrapped - re-running a whole
upload that may have already landed is exactly how a duplicate public video
gets published. Its own resilience comes from the resumable session's
internal chunk-level retry (next_chunk(num_retries=...)); a hard failure
becomes a failed step a human looks at, not an automatic full retry.

FLAG: field names below (snippet.categoryId, status.selfDeclaredMadeForKids,
videos.list's status/processingDetails enums, channels.list's
longUploadsStatus) are this build's best understanding of the YouTube Data
API v3, not verified against a live response - confirm against current
documentation before the first real upload, per SPEC.md Section 1.
"""

import logging

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from retry import call_with_retries

logger = logging.getLogger("net_gain.youtube_client")

# Must be a multiple of 256 KiB (Google's resumable-upload requirement).
# Chunked (rather than chunksize=-1's single request) so an interrupted
# upload of this pipeline's relatively small newscast videos can actually
# resume mid-file via next_chunk(), not just retry the whole thing.
DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024

RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


class YouTubeError(RuntimeError):
    pass


class YouTubeTransientError(YouTubeError):
    pass


def build_service(access_token):
    """
    Token-only credentials, deliberately with no refresh capability - this
    process never holds the client secret needed to refresh anyway (decision
    B: WordPress mints a fresh access token per tick instead).
    """
    credentials = Credentials(token=access_token)
    # cache_discovery=False avoids googleapiclient writing a discovery-doc
    # cache file to disk - untested whether that's even writable on this
    # shared host, and unnecessary for a process that runs one tick and exits.
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def get_own_channel_id(service):
    response = _execute_with_retry(service.channels().list(part="id", mine=True))
    items = response.get("items") or []
    if not items:
        raise YouTubeError(f"channels.list(mine=True) returned no channel: {response}")
    return items[0]["id"]


def upload_video(service, video_path, snippet, status, progress_logger=None):
    """
    Resumable upload (SPEC Section 6.3's full native upload, not RSS-import).
    Returns the new video's id. Deliberately not wrapped in call_with_retries
    - see module docstring.
    """
    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=DEFAULT_CHUNK_SIZE, resumable=True)
    request = service.videos().insert(
        part="snippet,status",
        body={"snippet": snippet, "status": status},
        media_body=media,
    )

    response = None
    while response is None:
        try:
            progress, response = request.next_chunk(num_retries=3)
        except HttpError as exc:
            raise YouTubeError(f"videos.insert failed: {_http_error_body(exc)}") from exc
        if progress_logger and progress:
            progress_logger(progress.resumable_progress, progress.total_size)

    video_id = response.get("id")
    if not video_id:
        raise YouTubeError(f"videos.insert did not return a video id: {response}")
    return video_id


def set_thumbnail(service, video_id, image_path):
    media = MediaFileUpload(image_path, mimetype="image/jpeg")
    _execute_with_retry(service.thumbnails().set(videoId=video_id, media_body=media))


def get_video_state(service, video_id):
    """
    Normalized snapshot of a video's processing/publish state. An empty
    `items` array (video deleted, or never existed) is treated as a
    meaningful terminal result (exists=False), not a parse error.

    status.uploadStatus is treated as the primary done-signal;
    processingDetails is corroborating only - it's owner-only and has a
    reputation for being less reliable than status.uploadStatus itself.
    """
    response = _execute_with_retry(
        service.videos().list(part="status,snippet,processingDetails", id=video_id)
    )
    items = response.get("items") or []
    return _normalize_video_item(items[0] if items else None)


def _normalize_video_item(item):
    """Split out from get_video_state() purely so this normalization logic is
    unit-testable without a live (or mocked) googleapiclient service object."""
    if item is None:
        return {
            "exists": False,
            "upload_status": None,
            "processing_status": None,
            "privacy_status": None,
            "title": None,
            "failure_reason": None,
            "rejection_reason": None,
        }

    status = item.get("status", {})
    processing = item.get("processingDetails", {})
    return {
        "exists": True,
        "upload_status": status.get("uploadStatus"),
        "processing_status": processing.get("processingStatus"),
        "privacy_status": status.get("privacyStatus"),
        "title": item.get("snippet", {}).get("title"),
        "failure_reason": status.get("failureReason"),
        "rejection_reason": status.get("rejectionReason"),
    }


def watch_url(video_id):
    """Constructed, not API-sourced - document as such wherever it's displayed."""
    return f"https://www.youtube.com/watch?v={video_id}"


def _execute_with_retry(request):
    def do_request():
        try:
            return request.execute()
        except HttpError as exc:
            status_code = exc.resp.status if getattr(exc, "resp", None) else None
            if status_code in RETRYABLE_HTTP_STATUSES:
                raise YouTubeTransientError(f"returned {status_code}: {_http_error_body(exc)}") from exc
            raise YouTubeError(_http_error_body(exc)) from exc

    return call_with_retries(do_request, (YouTubeTransientError,))


def _http_error_body(exc):
    try:
        if exc.content:
            return exc.content.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - fall through to the generic str() below
        pass
    return str(exc)
