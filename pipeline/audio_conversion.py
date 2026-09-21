"""
Captivate-specific audio bitrate conversion (real-world requirement,
2026-09-21): Captivate.fm requires 192kbps CBR MP3 uploads, and this show's
audio production software outputs 320kbps CBR - too high a bitrate for
Captivate to accept as-is.

Converts a working copy of the audio just for the Captivate upload. The
original file stored in WordPress's media library - the same file used for
website playback and as the YouTube video's audio track - is left untouched
at its original, higher bitrate: neither of those destinations has this
constraint, and there's no reason to downgrade audio quality somewhere it
isn't required just because one specific destination needs it.

No dashboard step/LED for this (explicit instruction, 2026-09-21) - it's an
internal detail of the existing captivate_published step, not a phase of
its own. A conversion failure surfaces as a normal captivate_published
"failed" status with this error as the note, via the same try/except
publish_to_captivate() is already wrapped in - nothing new to plug in.

Reuses ffmpeg_path() from video_composition.py - the same imageio-ffmpeg-
bundled static binary, already proven working on the actual production host
during Phase 9, rather than introducing a second way to locate ffmpeg.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

from video_composition import ffmpeg_path

logger = logging.getLogger("net_gain.audio_conversion")

CAPTIVATE_BITRATE_KBPS = 192


class AudioConversionError(RuntimeError):
    pass


def convert_to_captivate_bitrate(audio_bytes, bitrate_kbps=CAPTIVATE_BITRATE_KBPS):
    """
    Transcodes audio_bytes to a true CBR MP3 at bitrate_kbps and returns the
    result as bytes. Input format is not assumed - ffmpeg auto-detects it -
    but the output is always MP3, regardless of what came in.

    CONFIRMED (not just assumed) 2026-09-21: -b:a alone, with no -q:a/
    -compression_level alongside it, produces genuine CBR with libmp3lame,
    not VBR/ABR - verified directly against a real converted file's raw
    bytes (an "Info" header, LAME's CBR marker, with no "Xing" header, the
    VBR/ABR one) and its measured output size (~192kbps for a 192k target).
    Sample rate is deliberately left untouched (no -ar flag) - only
    bitrate/CBR was the actual requirement, nothing else about the audio
    should change.
    """
    with tempfile.TemporaryDirectory() as workdir:
        input_path = Path(workdir) / "input.audio"
        output_path = Path(workdir) / "output.mp3"
        input_path.write_bytes(audio_bytes)

        command = [
            ffmpeg_path(),
            "-nostdin",
            "-y",
            "-loglevel", "error",
            "-i", str(input_path),
            "-c:a", "libmp3lame",
            "-b:a", f"{bitrate_kbps}k",
            str(output_path),
        ]

        result = subprocess.run(command, capture_output=True, timeout=300)
        if result.returncode != 0:
            stderr_tail = result.stderr.decode("utf-8", errors="replace")[-1000:]
            raise AudioConversionError(f"ffmpeg audio conversion exited {result.returncode}: {stderr_tail}")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise AudioConversionError("ffmpeg reported success but produced no output file.")

        return output_path.read_bytes()
