import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.desktop.qml_controller import AutoDubController
from autodub.schemas.job import JobConfig
from autodub.services import job_store
from autodub.services.desktop_jobs import create_desktop_job


def _job(job_id, filename, project_name, project_type, status, progress, updated_at):
    return SimpleNamespace(
        job_id=job_id,
        original_filename=filename,
        project_name=project_name,
        project_directory="D:/AutoDubData/projects",
        project_type=project_type,
        status=status,
        progress=progress,
        updated_at=updated_at,
        files={},
    )


class ProjectGroupingTests(unittest.TestCase):
    def test_batch_jobs_share_one_project_card(self):
        summaries = AutoDubController._build_project_summaries(
            [
                _job("one", "one.mp4", "Summer launch", "batch", "done", 100, "2026-07-14T10:00:00Z"),
                _job("two", "two.mp4", "Summer launch", "batch", "processing", 50, "2026-07-14T11:00:00Z"),
                _job("three", "three.mp4", "Interview", "single", "pending", 0, "2026-07-14T09:00:00Z"),
            ]
        )

        self.assertEqual(len(summaries), 2)
        batch = summaries[0]
        self.assertEqual(batch["project_name"], "Summer launch")
        self.assertEqual(batch["project_type"], "batch")
        self.assertEqual(batch["job_count"], 2)
        self.assertEqual(batch["status"], "processing")
        self.assertEqual(batch["progress"], 75)
        self.assertEqual([job.job_id for job in batch["jobs"]], ["one", "two"])

    def test_batch_output_uses_a_unique_folder_for_each_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            original_jobs_dir = job_store.JOBS_DIR
            job_store.JOBS_DIR = str(root / "jobs")
            try:
                job = create_desktop_job(
                    str(source),
                    JobConfig(project_type="batch"),
                    project_name="Launch",
                    project_directory=str(root / "projects"),
                )
            finally:
                job_store.JOBS_DIR = original_jobs_dir

        output_path = Path(job.files["final_video"])
        self.assertEqual(job.project_type, "batch")
        self.assertEqual(output_path.name, "dubbed_video.mp4")
        self.assertEqual(output_path.parent.parent.name, "outputs")
        self.assertIn(job.job_id[:8], output_path.parent.name)


if __name__ == "__main__":
    unittest.main()
