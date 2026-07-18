import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from haizflow.schemas.job import VIDEO_METADATA_SCHEMA_VERSION, JobConfig, MediaSource
from haizflow.services import job_store, project_store


class ProjectIndexRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_index = project_store.PROJECT_INDEX_PATH
        project_store.PROJECT_INDEX_PATH = str(self.root / "runtime" / "projects.json")

    def tearDown(self):
        project_store.PROJECT_INDEX_PATH = self.original_index
        self.temp.cleanup()

    def test_corrupt_index_recovers_backup_and_newer_manifests(self):
        projects_dir = self.root / "projects"
        first = project_store.ensure_project("First", str(projects_dir), "single")
        second = project_store.ensure_project("Second", str(projects_dir), "batch")
        index_path = Path(project_store.PROJECT_INDEX_PATH)
        self.assertTrue(Path(f"{index_path}.bak").is_file())

        index_path.write_text("{broken", encoding="utf-8")
        recovered = project_store.list_projects()

        self.assertEqual({item["key"] for item in recovered}, {first["key"], second["key"]})
        self.assertIsInstance(json.loads(index_path.read_text(encoding="utf-8")), list)
        self.assertEqual(len(tuple(index_path.parent.glob("projects.json.corrupt-*"))), 1)

    def test_corrupt_first_index_rebuilds_from_project_manifest(self):
        project = project_store.ensure_project("Manifest only", str(self.root / "projects"), "single")
        index_path = Path(project_store.PROJECT_INDEX_PATH)
        Path(f"{index_path}.bak").unlink(missing_ok=True)
        index_path.write_text("not-json", encoding="utf-8")

        recovered = project_store.list_projects()

        self.assertEqual([item["key"] for item in recovered], [project["key"]])

    def test_unrecoverable_index_is_not_replaced_with_an_empty_list(self):
        index_path = Path(project_store.PROJECT_INDEX_PATH)
        index_path.parent.mkdir(parents=True)
        index_path.write_text("not-json", encoding="utf-8")

        with self.assertRaises(project_store.ProjectMetadataError):
            project_store.list_projects()

        self.assertEqual(index_path.read_text(encoding="utf-8"), "not-json")

    def test_concurrent_processes_do_not_lose_project_records(self):
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")
        projects_dir = self.root / "projects"
        processes = []
        for number in range(4):
            code = "\n".join(
                (
                    "from haizflow.services import project_store",
                    f"project_store.PROJECT_INDEX_PATH = {project_store.PROJECT_INDEX_PATH!r}",
                    f"project_store.ensure_project('Concurrent {number}', {str(projects_dir)!r}, 'single')",
                )
            )
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", code],
                    cwd=root,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            )
        for process in processes:
            output, errors = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, output + errors)

        self.assertEqual(len(project_store.list_projects()), 4)

    def test_project_v1_migrates_sequentially_with_backups(self):
        projects_dir = self.root / "projects"
        project_root = projects_dir / "Legacy"
        project_root.mkdir(parents=True)
        record = {
            "project_name": "Legacy",
            "project_directory": str(projects_dir),
            "project_root": str(project_root),
            "project_type": "single",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        index_path = Path(project_store.PROJECT_INDEX_PATH)
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps([record]), encoding="utf-8")
        manifest_path = project_root / project_store.PROJECT_MANIFEST_NAME
        manifest_path.write_text(json.dumps(record), encoding="utf-8")

        migrated = project_store.list_projects()[0]

        self.assertEqual(migrated["schema_version"], project_store.PROJECT_SCHEMA_VERSION)
        self.assertEqual(migrated["metadata_type"], project_store.PROJECT_METADATA_TYPE)
        self.assertTrue(Path(f"{index_path}.schema-migration.bak").is_file())
        self.assertTrue(Path(f"{manifest_path}.schema-migration.bak").is_file())
        self.assertEqual(
            json.loads(manifest_path.read_text(encoding="utf-8"))["schema_version"],
            project_store.PROJECT_SCHEMA_VERSION,
        )

    def test_future_project_schema_is_rejected_without_rewrite(self):
        index_path = Path(project_store.PROJECT_INDEX_PATH)
        index_path.parent.mkdir(parents=True)
        future = [{"schema_version": project_store.PROJECT_SCHEMA_VERSION + 1}]
        index_path.write_text(json.dumps(future), encoding="utf-8")

        with self.assertRaises(project_store.UnsupportedProjectSchemaError):
            project_store.list_projects()

        self.assertEqual(json.loads(index_path.read_text(encoding="utf-8")), future)


class VideoMetadataMigrationTests(unittest.TestCase):
    def test_media_source_rejects_unknown_provenance_type(self):
        with self.assertRaises(ValueError):
            MediaSource(type="untrusted")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_index = project_store.PROJECT_INDEX_PATH
        self.original_jobs = job_store.JOBS_DIR
        project_store.PROJECT_INDEX_PATH = str(self.root / "runtime" / "projects.json")
        job_store.JOBS_DIR = str(self.root / "legacy-jobs")

    def tearDown(self):
        project_store.PROJECT_INDEX_PATH = self.original_index
        job_store.JOBS_DIR = self.original_jobs
        self.temp.cleanup()

    def _create_video(self):
        name = f"Migration-{uuid.uuid4().hex}"
        project_store.ensure_project(name, str(self.root / "projects"), "single")
        return job_store.create_job(
            uuid.uuid4().hex,
            "source.mp4",
            JobConfig(project_name=name, project_directory=str(self.root / "projects")),
        )

    def test_unversioned_video_metadata_migrates_and_preserves_original(self):
        video = self._create_video()
        path = Path(job_store.get_job_json_path(video.job_id))
        legacy = json.loads(path.read_text(encoding="utf-8"))
        legacy.pop("schema_version")
        legacy.pop("metadata_type")
        legacy["mode"] = "B"
        legacy["source_language"] = "en"
        legacy["translator_provider"] = "ollama"
        path.write_text(json.dumps(legacy), encoding="utf-8")

        migrated = job_store.get_job(video.job_id)
        saved = json.loads(path.read_text(encoding="utf-8"))
        backup = json.loads(Path(f"{path}.schema-migration.bak").read_text(encoding="utf-8"))

        self.assertEqual(migrated.schema_version, VIDEO_METADATA_SCHEMA_VERSION)
        self.assertEqual(migrated.mode, "A")
        self.assertEqual(migrated.source_language, "auto")
        self.assertEqual(migrated.translator_provider, "hymt2")
        self.assertEqual(migrated.media_source.type, "local_file")
        self.assertEqual(saved["metadata_type"], "haizflow.video")
        self.assertEqual(saved["media_source"]["type"], "local_file")
        self.assertNotIn("schema_version", backup)

    def test_future_video_schema_is_rejected_without_falling_back(self):
        video = self._create_video()
        path = Path(job_store.get_job_json_path(video.job_id))
        future = json.loads(path.read_text(encoding="utf-8"))
        future["schema_version"] = VIDEO_METADATA_SCHEMA_VERSION + 1
        path.write_text(json.dumps(future), encoding="utf-8")

        with self.assertRaises(RuntimeError):
            job_store.get_job(video.job_id)

        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["schema_version"],
            VIDEO_METADATA_SCHEMA_VERSION + 1,
        )


if __name__ == "__main__":
    unittest.main()
