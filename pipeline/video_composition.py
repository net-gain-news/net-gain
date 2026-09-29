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

`-loop 1` on the still image ends the video at the audio's own duration -
via an explicit `-t <duration>` measured by decoding the audio first (see
`_probe_audio_duration_seconds()`), not via `-shortest` alone. That was the
original design (avoiding needing ffprobe, which imageio-ffmpeg doesn't
bundle, just to measure duration first) - confirmed live 2026-09-29 that
`-shortest` alone isn't reliable for every source file, so this now decodes
the audio with plain ffmpeg instead, which is bundled either way.

Verified live 2026-09-29 against a real production render on the actual
target host: 1280x720 h264/AAC, correct 16:9 DAR, real audio track - the
pipeline's actual output, not a synthetic test. `-r 1` (1fps) specifically
has not caused any observed YouTube-side problem in the one real upload
tested so far, but that's one data point, not a guarantee across all
content.
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

    Returns (video_path, duration_seconds).

    Confirmed live (2026-09-29): -shortest alone is not reliable here - a
    real published episode came out ~45 seconds longer than its own source
    audio (confirmed by fully decoding that audio file: no trailing silence,
    true duration exactly matched its own header). The mechanism wasn't
    pinned down (something in how -shortest interacts with an infinitely-
    looped still-image input, not a bad source file), so rather than
    continuing to depend on -shortest's heuristic at all, this now measures
    the audio's real decoded duration up front and passes ffmpeg a hard
    `-t <duration>` - an unambiguous, independent cap that produces a
    correctly-timed video even if -shortest's own cutoff misbehaves again.
    -shortest is left in place too, as a harmless second bound.
    """
    workdir = Path(workdir)
    image_path = workdir / "image.jpg"
    audio_path = workdir / f"audio.{audio_extension}"
    video_path = workdir / "out.mp4"

    image_path.write_bytes(image_bytes)
    audio_path.write_bytes(audio_bytes)

    ffmpeg_bin = ffmpeg_path()
    duration_seconds = _probe_audio_duration_seconds(ffmpeg_bin, audio_path)

    command = [
        ffmpeg_bin,
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
        "-t", f"{duration_seconds:.3f}",
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

    return str(video_path), duration_seconds


def _probe_audio_duration_seconds(ffmpeg_bin, audio_path):
    """
    Fully decodes the audio (not just reading its self-reported header) to
    get its real duration, via ffmpeg's own periodic "time=" progress
    output - the same mechanism confirmed by hand during the 2026-09-29
    incident investigation. Deliberately does not trust a quick `-i` probe
    alone; a full decode is the only way to be sure the header and the real
    content agree, which is exactly what was suspect about this bug.
    """
    command = [ffmpeg_bin, "-nostdin", "-stats", "-i", str(audio_path), "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, timeout=300)
    stderr_text = result.stderr.decode("utf-8", errors="replace")

    matches = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", stderr_text)
    if not matches:
        raise VideoCompositionError(
            f"Could not determine the audio's real duration by decoding it: {stderr_text[-500:]}"
        )

    hours, minutes, seconds = matches[-1]
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
