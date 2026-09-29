import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from video_composition import (
    VideoCompositionError,
    _probe_audio_duration_seconds,
    render_still_video,
)


def _completed(returncode=0, stderr=b""):
    result = MagicMock()
    result.returncode = returncode
    result.stderr = stderr
    return result


class ProbeAudioDurationTests(unittest.TestCase):
    def test_parses_the_final_time_progress_line(self):
        stderr = (
            b"size=N/A time=00:01:00.00 bitrate=N/A speed=500x\n"
            b"size=N/A time=00:04:25.09 bitrate=N/A speed=1070x\n"
        )
        with patch("video_composition.subprocess.run", return_value=_completed(0, stderr)):
            duration = _probe_audio_duration_seconds("ffmpeg", "/tmp/audio.mp3")
        self.assertAlmostEqual(duration, 4 * 60 + 25.09, places=2)

    def test_raises_when_no_time_progress_found(self):
        with patch("video_composition.subprocess.run", return_value=_completed(0, b"nothing useful")):
            with self.assertRaises(VideoCompositionError):
                _probe_audio_duration_seconds("ffmpeg", "/tmp/audio.mp3")


class RenderStillVideoTests(unittest.TestCase):
    def test_passes_an_explicit_duration_to_ffmpeg(self):
        # Confirmed live 2026-09-29: -shortest alone produced a video ~45s
        # longer than its own source audio for a real episode. This locks in
        # that render_still_video() now caps duration explicitly via -t
        # rather than relying on -shortest's own cutoff alone.
        probe_stderr = b"size=N/A time=00:04:25.09 bitrate=N/A speed=1070x\n"

        def fake_run(command, **kwargs):
            if "-f" in command and command[command.index("-f") + 1] == "null":
                return _completed(0, probe_stderr)
            # The real render call - create the output file so the
            # size/exists check downstream passes.
            output_path = command[-1]
            with open(output_path, "wb") as f:
                f.write(b"fake mp4 bytes")
            return _completed(0, b"")

        with tempfile.TemporaryDirectory() as workdir:
            with patch("video_composition.subprocess.run", side_effect=fake_run):
                with patch("video_composition.ffmpeg_path", return_value="ffmpeg"):
                    video_path, duration = render_still_video(
                        b"fake image bytes", b"fake audio bytes", workdir
                    )

            self.assertAlmostEqual(duration, 4 * 60 + 25.09, places=2)
            self.assertTrue(os.path.exists(video_path))

    def test_render_command_includes_dash_t_with_probed_duration(self):
        probe_stderr = b"size=N/A time=00:02:30.50 bitrate=N/A speed=1070x\n"
        captured_commands = []

        def fake_run(command, **kwargs):
            captured_commands.append(command)
            if "-f" in command and command[command.index("-f") + 1] == "null":
                return _completed(0, probe_stderr)
            output_path = command[-1]
            with open(output_path, "wb") as f:
                f.write(b"fake mp4 bytes")
            return _completed(0, b"")

        with tempfile.TemporaryDirectory() as workdir:
            with patch("video_composition.subprocess.run", side_effect=fake_run):
                with patch("video_composition.ffmpeg_path", return_value="ffmpeg"):
                    render_still_video(b"fake image bytes", b"fake audio bytes", workdir)

        render_command = captured_commands[-1]
        self.assertIn("-t", render_command)
        t_value = render_command[render_command.index("-t") + 1]
        self.assertAlmostEqual(float(t_value), 150.50, places=2)
        self.assertIn("-shortest", render_command)

    def test_raises_on_nonzero_exit(self):
        def fake_run(command, **kwargs):
            if "-f" in command and command[command.index("-f") + 1] == "null":
                return _completed(0, b"size=N/A time=00:01:00.00 bitrate=N/A\n")
            return _completed(1, b"some ffmpeg error")

        with tempfile.TemporaryDirectory() as workdir:
            with patch("video_composition.subprocess.run", side_effect=fake_run):
                with patch("video_composition.ffmpeg_path", return_value="ffmpeg"):
                    with self.assertRaises(VideoCompositionError):
                        render_still_video(b"img", b"audio", workdir)


if __name__ == "__main__":
    unittest.main()
