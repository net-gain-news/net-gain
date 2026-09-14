"""
Renders the "video" YouTube actually gets (SPEC.md Section 6.3): the
episode's 16:9 art held static for the audio's full duration, muxed together
via ffmpeg into one MP4 - not three independently generated assets, and not
a real video in any other sense.

ffmpeg itself comes from imageio-ffmpeg's bundled static binary, not a
system install - Canspace is a shared cPanel host, and assuming a system
ffmpeg exists (or that arbitrary binaries can be installed) is exactly the
kind of unverified infrastructure assumption this project has been burned by
before (SPEC.md Section 1). A system ffmpeg on PATH is still preferred if
present, so this also works unmodified on a host that does have one.

`-loop 1` on the still image plus `-shortest` lets the audio's own duration
end the video - deliberately avoids needing ffprobe (which imageio-ffmpeg
does not bundle) just to measure it first.

FLAG: every ffmpeg flag below is this build's best understanding, not
verified against a real render on the actual target host - in particular
`-r 1` (1fps) is the most likely one to need raising toward YouTube's
documented 24fps recommendation if a 1fps upload causes problems. Verify
with one real render before trusting this in production.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("net_gain.video_composition")


class VideoCompositionError(RuntimeError):
    pass


def ffmpeg_path():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001 - any failure here means "no usable binary"
        logger.warning("imageio-ffmpeg unavailable or failed to resolve a binary: %s", exc)

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    raise VideoCompositionError(
        "No ffmpeg binary available: imageio-ffmpeg is not installed (or its "
        "bundled binary is not executable on this host) and no system ffmpeg "
        "is on PATH. YouTube publishing cannot render a video without one - "
        "this needs a human operator to resolve (confirm imageio-ffmpeg "
        "installed correctly via requirements.txt, or that a system ffmpeg is "
        "reachable), it is not retryable by the pipeline itself."
    )


def render_still_video(image_bytes, audio_bytes, workdir, audio_extension="mp3"):
    """
    Writes image_bytes/audio_bytes into workdir (a caller-owned directory -
    e.g. a tempfile.TemporaryDirectory() kept open across the subsequent
    upload, since ffmpeg needs real file paths) and renders out.mp4 there.

    Returns (video_path, duration_seconds_or_None) - duration is parsed
    best-effort from ffmpeg's own stderr purely for logging/a sanity floor;
    parse failure is non-fatal and logged only, since stderr's exact format
    is not a stable contract.
    """
    workdir = Path(workdir)
    image_path = workdir / "image.jpg"
    audio_path = workdir / f"audio.{audio_extension}"
    video_path = workdir / "out.mp4"

    image_path.write_bytes(image_bytes)
    audio_path.write_bytes(audio_bytes)

    command = [
        ffmpeg_path(),
        "-nostdin",
        "-y",
        "-loglevel", "error",
        "-stats",
        "-loop", "1",
        "-framerate", "1",
        "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", "scale=1280:720",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-r", "1",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-shortest",
        "-movflags", "+faststart",
        str(video_path),
    ]

    result = subprocess.run(command, capture_output=True, timeout=900)
    if result.returncode != 0:
        stderr_tail = result.stderr.decode("utf-8", errors="replace")[-1000:]
        raise VideoCompositionError(f"ffmpeg exited {result.returncode}: {stderr_tail}")

    if not video_path.exists() or video_path.stat().st_size == 0:
        raise VideoCompositionError("ffmpeg reported success but produced no output file.")

    duration = _parse_duration(result.stderr.decode("utf-8", errors="replace"))
    return str(video_path), duration


def _parse_duration(stderr_text):
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr_text)
    if not match:
        return None
    try:
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return None
