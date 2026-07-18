import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline.process_video import _checkpoint_valid
from haizflow.schemas.video import VideoConfig
from haizflow.services import video_store, project_store


class RestartCheckpointTests(unittest.TestCase):
    def test_checkpoint_is_only_valid_for_a_paused_video_being_resumed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "translation.json"
            artifact.write_text("[]", encoding="utf-8")
            video = SimpleNamespace(checkpoints={"translation": "signature"}, resume_step="")

            self.assertFalse(_checkpoint_valid(video, "translation", "signature", [str(artifact)]))

            video.resume_step = "translating"
            self.assertTrue(_checkpoint_valid(video, "translation", "signature", [str(artifact)]))


class InterruptedVideoRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_index = project_store.PROJECT_INDEX_PATH
        self.original_videos = video_store.LEGACY_VIDEO_WORKSPACES_DIR
        project_store.PROJECT_INDEX_PATH = str(self.root / "runtime" / "projects.json")
        video_store.LEGACY_VIDEO_WORKSPACES_DIR = str(self.root / "legacy-videos")

    def tearDown(self):
        project_store.PROJECT_INDEX_PATH = self.original_index
        video_store.LEGACY_VIDEO_WORKSPACES_DIR = self.original_videos
        self.temp.cleanup()

    def _create_video(self, status: str, step: str):
        project_name = f"Recovery-{uuid.uuid4().hex}"
        project_directory = self.root / "projects"
        project_store.ensure_project(project_name, str(project_directory), "single")
        video = video_store.create_video(
            uuid.uuid4().hex,
            "source.mp4",
            VideoConfig(project_name=project_name, project_directory=str(project_directory)),
        )
        return video_store.update_video(video.video_id, status=status, step=step, error="stale error")

    def test_stale_processing_video_becomes_resumable_after_restart(self):
        interrupted = self._create_video("processing", "rendering")
        completed = self._create_video("done", "done")

        recovered = video_store.recover_interrupted_videos()

        self.assertEqual(recovered, [interrupted.video_id])
        restored = video_store.get_video(interrupted.video_id)
        self.assertEqual(restored.status, "paused")
        self.assertEqual(restored.step, "paused")
        self.assertEqual(restored.resume_step, "rendering")
        self.assertIsNone(restored.error)
        self.assertIn("interrupted exit", restored.step_detail)
        self.assertEqual(video_store.get_video(completed.video_id).status, "done")
        self.assertEqual(video_store.recover_interrupted_videos(), [])


if __name__ == "__main__":
    unittest.main()
