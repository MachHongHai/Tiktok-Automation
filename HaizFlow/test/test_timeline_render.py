import tempfile
import unittest
from pathlib import Path
from unittest import mock

from haizflow.pipeline.audio_timeline import _segment_slot_end_ms
from haizflow.pipeline import render
from haizflow.schemas.video import CropSettings, SubtitleStyle


class TimelineRenderTests(unittest.TestCase):
    def test_only_last_voice_slot_keeps_a_small_tail_margin(self):
        self.assertEqual(
            _segment_slot_end_ms(1000, 3000, 5000, is_last=False),
            3000,
        )
        self.assertEqual(
            _segment_slot_end_ms(3000, 5000, 5000, is_last=True),
            4880,
        )

    def test_very_short_final_slot_is_not_overcompressed_for_margin(self):
        self.assertEqual(
            _segment_slot_end_ms(4800, 5000, 5000, is_last=True),
            5000,
        )

    def test_render_is_limited_by_source_duration_instead_of_shortest_stream(self):
        captured = {}

        class FakeProcess:
            returncode = 0

            def __init__(self, command, **_kwargs):
                captured["command"] = command

            def communicate(self):
                return "", ""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subtitle_path = root / "subtitles.srt"
            subtitle_path.write_text("", encoding="utf-8")
            with (
                mock.patch.object(render, "get_video_dimensions", return_value=(1920, 1080)),
                mock.patch.object(render, "get_video_duration", return_value=5.0),
                mock.patch.object(render, "preferred_video_encoder", return_value=("libx264", ["-preset", "fast"])),
                mock.patch.object(render.subprocess, "Popen", FakeProcess),
                mock.patch.object(render, "register_process"),
                mock.patch.object(render, "unregister_process"),
                mock.patch.object(render, "check_cancellation"),
                mock.patch.object(render, "log_to_video"),
            ):
                render.render_video(
                    str(root / "input.mp4"),
                    str(root / "voice.wav"),
                    str(subtitle_path),
                    str(root / "output.mp4"),
                    "keep_ratio",
                    SubtitleStyle(),
                    CropSettings(),
                    "video-id",
                )

        command = captured["command"]
        self.assertNotIn("-shortest", command)
        self.assertEqual(command[command.index("-t") + 1], "5.000000")


if __name__ == "__main__":
    unittest.main()
