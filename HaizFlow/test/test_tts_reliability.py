import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline import tts


def _write_test_mp3(path: str) -> None:
    Path(path).write_bytes(b"\xff\xf3\x64" + b"\x00" * 700)


class TtsReliabilityTests(unittest.TestCase):
    def test_text_normalization_removes_transport_sensitive_punctuation(self):
        normalized = tts.preprocess_text_for_tts(
            "  Xin\u00a0chao\u200b \u2013 tu nhien\u2026  "
        )
        self.assertEqual(normalized, "Xin chao, tu nhien...")

    def test_segment_retry_uses_a_fresh_connection_and_atomic_valid_file(self):
        class FakeCommunicate:
            calls = 0

            def __init__(self, *_args, **_kwargs):
                type(self).calls += 1
                self.call = type(self).calls

            async def save(self, path):
                if self.call == 1:
                    raise RuntimeError("No audio was received")
                _write_test_mp3(path)

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            output = str(Path(temp_dir) / "voice.mp3")
            with (
                mock.patch.object(tts.edge_tts, "Communicate", FakeCommunicate),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
            ):
                attempts = asyncio.run(
                    tts.tts_segment_with_retry("Xin chao", "voice", output, retries=2)
                )

            self.assertEqual(attempts, 2)
            self.assertTrue(tts._is_valid_mp3(output))
            self.assertEqual(list(Path(temp_dir).glob("*.part-*")), [])

    def test_failed_parallel_segment_is_recovered_sequentially(self):
        calls = []

        async def fake_synthesize(text, _voice, output_path, retries=3, **_kwargs):
            calls.append((text, retries))
            if text == "second" and retries == tts._INITIAL_RETRIES:
                raise RuntimeError("No audio was received")
            _write_test_mp3(output_path)
            return 1

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": "first"}, {"text": "second"}, {"text": "third"}]),
                encoding="utf-8",
            )
            voice_dir = Path(temp_dir) / "voice"
            progress = []
            with (
                mock.patch.object(tts, "tts_segment_with_retry", fake_synthesize),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(
                    str(segments_path),
                    str(voice_dir),
                    "voice",
                    "video",
                    lambda current, total: progress.append((current, total)),
                )

            self.assertIn(("second", tts._RECOVERY_RETRIES), calls)
            self.assertEqual(progress[-1], (3, 3))
            self.assertTrue(all(tts._is_valid_mp3(str(path)) for path in voice_dir.glob("*.mp3")))

    def test_parallel_tts_logs_distinguish_segment_order_from_overall_progress(self):
        async def fake_synthesize(text, _voice, output_path, retries=3, **_kwargs):
            if text == "second":
                await asyncio.sleep(0.01)
            _write_test_mp3(output_path)
            return 1

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": "first"}, {"text": "second"}, {"text": "third"}]),
                encoding="utf-8",
            )
            logs = []
            with (
                mock.patch.object(tts, "tts_segment_with_retry", fake_synthesize),
                mock.patch.object(tts, "log_to_video", lambda _video, line: logs.append(line)),
            ):
                tts.generate_voice_parts(
                    str(segments_path), str(Path(temp_dir) / "voice"), "voice", "video"
                )

        self.assertTrue(any("[TTS][START] segment=1/3" in line for line in logs))
        self.assertTrue(any("[TTS][START] segment=1/3" in line and 'text="first"' in line for line in logs))
        self.assertTrue(any("[TTS][COMPLETE] segment=1/3 overall=1/3" in line for line in logs))
        self.assertTrue(all("Creating voice" not in line for line in logs))

    def test_tts_sentence_preview_is_single_line_and_bounded(self):
        preview = tts._tts_text_preview('  First line\n"second line"  ' + "x" * 300)

        self.assertNotIn("\n", preview)
        self.assertIn("First line 'second line'", preview)
        self.assertTrue(preview.endswith('..."'))
        self.assertLessEqual(len(preview), 222)

    def test_default_tts_execution_never_opens_two_edge_requests_at_once(self):
        active = 0
        maximum_active = 0

        async def measured_synthesize(_text, _voice, output_path, retries=3, **_kwargs):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.01)
            _write_test_mp3(output_path)
            active -= 1
            return 1

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": str(index)} for index in range(6)]),
                encoding="utf-8",
            )
            with (
                mock.patch.object(tts, "TTS_MAX_CONCURRENCY", 1),
                mock.patch.object(tts, "tts_segment_with_retry", measured_synthesize),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(
                    str(segments_path), str(Path(temp_dir) / "voice"), "voice", "video"
                )

        self.assertEqual(maximum_active, 1)

    def test_tts_retry_log_contains_a_stable_error_label(self):
        async def fail_once(*_args, **kwargs):
            retry_callback = kwargs["retry_callback"]
            retry_callback(1, 3, RuntimeError("No audio was received"), 1.5)
            raise RuntimeError("No audio was received")

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(json.dumps([{"text": "failed"}]), encoding="utf-8")
            logs = []
            with (
                mock.patch.object(tts, "tts_segment_with_retry", fail_once),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
                mock.patch.object(tts, "log_to_video", lambda _video, line: logs.append(line)),
            ):
                with self.assertRaisesRegex(RuntimeError, "segment\\(s\\): 1"):
                    tts.generate_voice_parts(
                        str(segments_path), str(Path(temp_dir) / "voice"), "voice", "video"
                    )

        self.assertTrue(any("[TTS][RETRY]" in line and "error=edge_no_audio" in line for line in logs))
        self.assertTrue(any("[TTS][FAILED]" in line and "error=edge_no_audio" in line for line in logs))

    def test_permanent_failure_stops_pipeline_without_silence_file(self):
        async def always_fail(*_args, **_kwargs):
            raise RuntimeError("No audio was received")

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(json.dumps([{"text": "failed"}]), encoding="utf-8")
            voice_dir = Path(temp_dir) / "voice"
            with (
                mock.patch.object(tts, "tts_segment_with_retry", always_fail),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
                mock.patch.object(tts, "log_to_video"),
            ):
                with self.assertRaisesRegex(RuntimeError, "segment\\(s\\): 1"):
                    tts.generate_voice_parts(
                        str(segments_path), str(voice_dir), "voice", "video"
                    )

            output = voice_dir / "voice_0001.mp3"
            self.assertFalse(output.exists())

    def test_resume_reuses_verified_parts_and_regenerates_only_missing_audio(self):
        calls = []

        async def fake_synthesize(text, _voice, output_path, retries=3, **_kwargs):
            calls.append((text, retries))
            _write_test_mp3(output_path)
            return 1

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": "existing"}, {"text": "missing"}]),
                encoding="utf-8",
            )
            voice_dir = Path(temp_dir) / "voice"
            voice_dir.mkdir()
            _write_test_mp3(str(voice_dir / "voice_0001.mp3"))
            (voice_dir / "voice_0002.mp3").write_bytes(b"")

            with (
                mock.patch.object(tts, "tts_segment_with_retry", fake_synthesize),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(
                    str(segments_path), str(voice_dir), "voice", "video"
                )

            self.assertEqual(calls, [("missing", tts._INITIAL_RETRIES)])
            self.assertTrue(tts._is_valid_mp3(str(voice_dir / "voice_0001.mp3")))
            self.assertTrue(tts._is_valid_mp3(str(voice_dir / "voice_0002.mp3")))


if __name__ == "__main__":
    unittest.main()
