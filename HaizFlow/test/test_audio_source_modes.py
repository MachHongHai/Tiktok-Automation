import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline import process_job


class AudioSourceModeTests(unittest.TestCase):
    def test_original_mode_uses_source_audio_and_selected_volume(self):
        job = SimpleNamespace(
            enable_audio_separation=False,
            original_video_volume=35,
            files={},
        )

        path, volume = process_job._resolve_audio_mix(job, "source.wav")

        self.assertEqual(path, "source.wav")
        self.assertEqual(volume, 35)

    def test_separated_mode_uses_no_vocals_at_full_volume(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            background_path = Path(temporary_directory) / "no_vocals.wav"
            background_path.write_bytes(b"audio")
            job = SimpleNamespace(
                enable_audio_separation=True,
                original_video_volume=20,
                files={"background_audio": str(background_path)},
            )

            path, volume = process_job._resolve_audio_mix(job, "source.wav")

        self.assertEqual(path, str(background_path))
        self.assertEqual(volume, 100)

    def test_missing_separated_track_is_regenerated_and_persisted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "audio.wav"
            vocals_path = root / "vocals.wav"
            background_path = root / "no_vocals.wav"
            source_path.write_bytes(b"source")
            vocals_path.write_bytes(b"voice")
            background_path.write_bytes(b"background")
            job = SimpleNamespace(
                job_id="audio-test",
                enable_audio_separation=True,
                original_video_volume=20,
                files={"video_input": str(root / "video.mp4")},
            )
            reporter = mock.Mock()

            with (
                mock.patch.object(process_job, "separate_audio", return_value=(str(vocals_path), str(background_path))),
                mock.patch.object(process_job, "check_cancellation"),
                mock.patch.object(process_job, "_ensure_gpu_available"),
                mock.patch.object(process_job, "update_job") as update_job,
                mock.patch.object(process_job, "log_to_job"),
            ):
                path, volume = process_job._prepare_audio_mix(
                    job,
                    reporter,
                    str(root),
                    str(source_path),
                )

        self.assertEqual(path, str(background_path))
        self.assertEqual(volume, 100)
        self.assertEqual(job.files["speech_audio"], str(vocals_path))
        self.assertEqual(job.files["background_audio"], str(background_path))
        update_job.assert_called_once_with("audio-test", files=job.files)


if __name__ == "__main__":
    unittest.main()

