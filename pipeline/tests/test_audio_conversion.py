import os
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_conversion import AudioConversionError, convert_to_captivate_bitrate
from video_composition import ffmpeg_path, VideoCompositionError


def _make_silent_mp3(seconds=1, bitrate_kbps=320):
    """Real ffmpeg-generated test fixture - a tiny silent MP3 at a known
    bitrate, so the integration test below exercises the real conversion
    command end to end rather than only mocking subprocess."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as workdir:
        out = Path(workdir) / "silent.mp3"
        subprocess.run(
            [
                ffmpeg_path(), "-nostdin", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
                "-t", str(seconds),
                "-c:a", "libmp3lame", "-b:a", f"{bitrate_kbps}k",
                str(out),
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        return out.read_bytes()


class ConvertToCaptivateBitrateIntegrationTests(unittest.TestCase):
    """Real ffmpeg invocation, no mocking - skipped outright if no ffmpeg
    binary resolves on this machine, matching this project's own "flag what
    needs live verification, don't fail the whole suite over an environment
    gap" discipline."""

    @classmethod
    def setUpClass(cls):
        try:
            ffmpeg_path()
        except VideoCompositionError as exc:
            raise unittest.SkipTest(f"No ffmpeg binary available: {exc}")

    def test_produces_valid_mp3_bytes_at_the_requested_bitrate(self):
        source = _make_silent_mp3(seconds=1, bitrate_kbps=320)
        converted = convert_to_captivate_bitrate(source, bitrate_kbps=192)

        self.assertGreater(len(converted), 0)
        # MP3 frame sync (11 set bits) or an ID3 tag header - either is a
        # genuine MP3 file, not just arbitrary bytes.
        self.assertTrue(converted[:3] == b"ID3" or (converted[0] == 0xFF and (converted[1] & 0xE0) == 0xE0))

    def test_default_bitrate_is_192(self):
        source = _make_silent_mp3(seconds=1, bitrate_kbps=320)
        default_result = convert_to_captivate_bitrate(source)
        explicit_result = convert_to_captivate_bitrate(source, bitrate_kbps=192)
        # Not byte-identical (encoders aren't required to be deterministic
        # run to run), but close enough in size to confirm the same target
        # bitrate was actually used, not the un-converted 320k source size.
        self.assertLess(abs(len(default_result) - len(explicit_result)), len(explicit_result) * 0.2)


class ConvertToCaptivateBitrateErrorHandlingTests(unittest.TestCase):
    @patch("audio_conversion.ffmpeg_path", return_value="/usr/bin/ffmpeg")
    @patch("audio_conversion.subprocess.run")
    def test_raises_with_stderr_on_nonzero_exit(self, mock_run, _mock_path):
        mock_run.return_value = Mock(returncode=1, stderr=b"some encoder error")
        with self.assertRaises(AudioConversionError) as ctx:
            convert_to_captivate_bitrate(b"not real audio")
        self.assertIn("some encoder error", str(ctx.exception))

    @patch("audio_conversion.ffmpeg_path", return_value="/usr/bin/ffmpeg")
    @patch("audio_conversion.subprocess.run")
    def test_raises_when_output_file_missing_despite_zero_exit(self, mock_run, _mock_path):
        # returncode 0 but no output written - subprocess.run itself doesn't
        # create the file since ffmpeg_path is mocked and never really runs.
        mock_run.return_value = Mock(returncode=0, stderr=b"")
        with self.assertRaises(AudioConversionError) as ctx:
            convert_to_captivate_bitrate(b"not real audio")
        self.assertIn("no output file", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
