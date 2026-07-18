import json
import sys
import tempfile
import unittest
from pathlib import Path
import stat
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.models import ProjectListModel
from haizflow.schemas.job import JobConfig
from haizflow.services import job_store
from haizflow.services import project_store
from haizflow.services.desktop_jobs import create_desktop_job, migrate_legacy_single_export


def _job(job_id, filename, project_name, project_type, status, progress, updated_at):
    return SimpleNamespace(
        job_id=job_id,
        original_filename=filename,
        project_name=project_name,
        project_directory="D:/HaizFlowData/projects",
        project_type=project_type,
        status=status,
        progress=progress,
        updated_at=updated_at,
        files={},
    )


class ProjectGroupingTests(unittest.TestCase):
    def test_same_name_single_and_batch_projects_have_distinct_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_project_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                single = project_store.ensure_project("Campaign", str(root / "projects"), "single")
                batch = project_store.ensure_project("Campaign", str(root / "projects"), "batch")
            finally:
                project_store.PROJECT_INDEX_PATH = original_project_index

        self.assertNotEqual(single["key"], batch["key"])
        self.assertNotEqual(single["project_root"], batch["project_root"])
        self.assertTrue(single["key"].startswith("project:"))
        self.assertTrue(batch["key"].startswith("project:"))

    def test_new_projects_with_the_same_name_have_distinct_uuid_identities(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                first = project_store.create_project("Daily clips", str(root / "projects"), "single")
                second = project_store.create_project("Daily clips", str(root / "projects"), "single")
                persisted = project_store.list_projects()
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertNotEqual(first["project_id"], second["project_id"])
        self.assertNotEqual(first["key"], second["key"])
        self.assertNotEqual(first["project_root"], second["project_root"])
        self.assertEqual({item["key"] for item in persisted}, {first["key"], second["key"]})

    def test_jobs_with_duplicate_project_names_use_the_selected_project_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            original_jobs_dir = job_store.JOBS_DIR
            original_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "legacy-jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                first = project_store.create_project("Episode", str(root / "projects"), "single")
                second = project_store.create_project("Episode", str(root / "projects"), "single")
                first_job = create_desktop_job(
                    str(source),
                    JobConfig(project_type="single", project_key=first["key"]),
                    project_name="Episode",
                    project_directory=str(root / "projects"),
                    project_key_value=first["key"],
                )
                second_job = create_desktop_job(
                    str(source),
                    JobConfig(project_type="single", project_key=second["key"]),
                    project_name="Episode",
                    project_directory=str(root / "projects"),
                    project_key_value=second["key"],
                )
                first_workspace = Path(job_store.get_job_dir(first_job.job_id))
                second_workspace = Path(job_store.get_job_dir(second_job.job_id))
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_index
                job_store._JOB_DIR_CACHE.clear()

        self.assertEqual(first_job.project_key, first["key"])
        self.assertEqual(second_job.project_key, second["key"])
        self.assertTrue(first_workspace.is_relative_to(Path(first["project_root"])))
        self.assertTrue(second_workspace.is_relative_to(Path(second["project_root"])))

    def test_batch_jobs_share_one_project_card(self):
        summaries = HaizFlowController._build_project_summaries(
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

    def test_project_library_models_keep_single_and_batch_projects_separate(self):
        summaries = HaizFlowController._build_project_summaries(
            [
                _job("one", "one.mp4", "Campaign", "batch", "pending", 0, "2026-07-14T10:00:00Z"),
                _job("two", "two.mp4", "Interview", "single", "done", 100, "2026-07-14T11:00:00Z"),
            ]
        )
        single_model = ProjectListModel()
        batch_model = ProjectListModel()
        single_model.set_projects([item for item in summaries if item["project_type"] == "single"])
        batch_model.set_projects([item for item in summaries if item["project_type"] == "batch"])

        self.assertEqual(single_model.rowCount(), 1)
        self.assertEqual(batch_model.rowCount(), 1)
        self.assertEqual(single_model.project_at(0)["project_name"], "Interview")
        self.assertEqual(batch_model.project_at(0)["project_name"], "Campaign")

    def test_batch_output_uses_a_unique_folder_for_each_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                job = create_desktop_job(
                    str(source),
                    JobConfig(project_type="batch"),
                    project_name="Launch",
                    project_directory=str(root / "projects"),
                )
                project_root = Path(project_store.project_root("Launch", str(root / "projects"), "batch"))
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        output_path = Path(job.files["final_video"])
        self.assertEqual(job.project_type, "batch")
        self.assertEqual(output_path.name, "dubbed_video.mp4")
        self.assertEqual(output_path.parent.parent.name, "exports")
        self.assertEqual(output_path.parent.parent.parent, project_root)
        self.assertTrue(project_root.name.startswith("Launch--"))
        self.assertIn(job.job_id[:8], output_path.parent.name)

    def test_single_project_export_is_separate_from_the_project_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                job = create_desktop_job(
                    str(source),
                    JobConfig(project_type="single"),
                    project_name="Interview",
                    project_directory=str(root / "projects"),
                )
                workspace = Path(job_store.get_job_dir(job.job_id))
                project_root = Path(project_store.project_root("Interview", str(root / "projects"), "single"))
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        output_path = Path(job.files["final_video"])
        self.assertEqual(output_path.parent.name, "exports")
        self.assertEqual(output_path.parent.parent, project_root)
        self.assertTrue(project_root.name.startswith("Interview--"))
        self.assertEqual(workspace.parent.name, "videos")
        self.assertEqual(workspace.parent.parent, project_root)
        self.assertFalse((workspace / "output").exists())

    def test_imported_single_video_is_saved_before_processing_starts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "clip.mp4"
            source.write_bytes(b"video")
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "legacy-jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                job = create_desktop_job(
                    str(source),
                    JobConfig(project_type="single"),
                    project_name="Imported",
                    project_directory=str(root / "projects"),
                )
                persisted = job_store.get_job(job.job_id)
                copied_input = Path(persisted.files["video_input"])
                project_root = project_store.project_root("Imported", str(root / "projects"))
                copied_bytes = copied_input.read_bytes()
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index
                job_store._JOB_DIR_CACHE.clear()

        self.assertEqual(persisted.status, "pending")
        self.assertEqual(copied_bytes, b"video")
        self.assertTrue(copied_input.is_relative_to(Path(project_root)))

    def test_channel_import_can_move_downloaded_video_into_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "downloaded.mp4"
            source.write_bytes(b"downloaded-video")
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "legacy-jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                job = create_desktop_job(
                    str(source),
                    JobConfig(project_type="batch"),
                    project_name="Channel",
                    project_directory=str(root / "projects"),
                    media_source={"type": "channel", "platform": "YouTube", "remote_video_id": "abc"},
                    move_input=True,
                )
                imported_path = Path(job.files["video_input"])
                imported_bytes = imported_path.read_bytes()
                source_exists = source.exists()
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index
                job_store._JOB_DIR_CACHE.clear()

        self.assertFalse(source_exists)
        self.assertEqual(imported_bytes, b"downloaded-video")
        self.assertEqual(job.media_source.type, "channel")
        self.assertEqual(job.media_source.remote_video_id, "abc")

    def test_legacy_single_export_moves_into_exports_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project = project_store.ensure_project("Legacy", str(root / "projects"), "single")
                config = JobConfig(project_name="Legacy", project_directory=str(root / "projects"))
                job = job_store.create_job("legacy-job", "clip.mp4", config)
                legacy_export = Path(project["project_root"]) / "dubbed_video.mp4"
                legacy_export.write_bytes(b"video")
                job.files["final_video"] = str(legacy_export)
                job_store.save_job(job)

                migrated = migrate_legacy_single_export(job)
                saved_job = job_store.get_job(job.job_id)
                expected_export = Path(project["project_root"]) / "exports" / "dubbed_video.mp4"
                legacy_export_exists = legacy_export.exists()
                expected_export_exists = expected_export.is_file()
                saved_export_path = Path(saved_job.files["final_video"])
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        self.assertTrue(migrated)
        self.assertFalse(legacy_export_exists)
        self.assertTrue(expected_export_exists)
        self.assertEqual(saved_export_path, expected_export)

    def test_legacy_video_workspace_moves_into_its_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project_store.ensure_project("Migrated", str(root / "projects"), "single")
                job = job_store.create_job("legacy-workspace", "clip.mp4", JobConfig())
                legacy_workspace = Path(job_store.get_job_dir(job.job_id))
                job.project_name = "Migrated"
                job.project_directory = str(root / "projects")
                job.project_type = "single"
                job_store.save_job(job)

                migrated = job_store.migrate_legacy_project_data()
                workspace = Path(job_store.get_job_dir(job.job_id))
                saved_job = job_store.get_job(job.job_id)
                legacy_workspace_exists = legacy_workspace.exists()
                workspace_has_metadata = (workspace / "job.json").is_file()
                workspace_parent_name = workspace.parent.name
                saved_input_parent = Path(saved_job.files["video_input"]).parent.parent
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        self.assertEqual(migrated, ["legacy-workspace"])
        self.assertFalse(legacy_workspace_exists)
        self.assertEqual(workspace_parent_name, "videos")
        self.assertTrue(workspace_has_metadata)
        self.assertEqual(saved_input_parent, workspace)

    def test_legacy_thumbnail_moves_into_its_video_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "legacy-jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project_store.ensure_project("Thumbnail", str(root / "projects"), "single")
                config = JobConfig(project_name="Thumbnail", project_directory=str(root / "projects"))
                job = job_store.create_job("thumbnail-workspace", "clip.mp4", config)
                legacy_thumbnail = root / "cache" / "thumbnails" / "legacy.jpg"
                legacy_thumbnail.parent.mkdir(parents=True)
                legacy_thumbnail.write_bytes(b"thumbnail")
                job.files["thumbnail"] = str(legacy_thumbnail)
                job_store.save_job(job)

                migrated = job_store.migrate_legacy_thumbnails(str(legacy_thumbnail.parent))
                saved_job = job_store.get_job(job.job_id)
                expected_thumbnail = Path(job_store.get_job_dir(job.job_id)) / "thumbnail.jpg"
                expected_exists = expected_thumbnail.is_file()
                legacy_exists = legacy_thumbnail.exists()
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        self.assertEqual(migrated, ["thumbnail-workspace"])
        self.assertTrue(expected_exists)
        self.assertFalse(legacy_exists)
        self.assertEqual(Path(saved_job.files["thumbnail"]), expected_thumbnail)

    def test_empty_project_is_included_in_project_summaries(self):
        persisted = {
            "key": "single:d:/haizflowdata/projects:draft",
            "project_name": "Draft",
            "project_directory": "D:/HaizFlowData/projects",
            "project_type": "single",
            "updated_at": "2026-07-15T10:00:00Z",
        }
        summaries = HaizFlowController._build_project_summaries([], [persisted])

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["status"], "empty")
        self.assertEqual(summaries[0]["job_count"], 0)

    def test_ensure_project_persists_an_empty_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project = project_store.ensure_project("Empty batch", str(root / "exports"), "batch")
                projects = project_store.list_projects()
                self.assertTrue(Path(project["project_root"]).is_dir())
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertEqual(projects[0]["key"], project["key"])
        self.assertEqual(projects[0]["project_type"], "batch")
        self.assertEqual(projects[0]["schema_version"], project_store.PROJECT_SCHEMA_VERSION)
        self.assertEqual(projects[0]["storage_layout"], "uuid")

    def test_single_and_batch_projects_with_the_same_name_use_distinct_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                single = project_store.ensure_project("Shared name", str(root / "projects"), "single")
                batch = project_store.ensure_project("Shared name", str(root / "projects"), "batch")
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertNotEqual(single["project_id"], batch["project_id"])
        self.assertNotEqual(single["project_root"], batch["project_root"])
        self.assertTrue(Path(single["project_root"]).name.startswith("Shared name--"))
        self.assertTrue(Path(batch["project_root"]).name.startswith("Shared name--"))

    def test_deleting_one_project_type_keeps_the_same_named_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                single = project_store.ensure_project("Shared name", str(root / "projects"), "single")
                batch = project_store.ensure_project("Shared name", str(root / "projects"), "batch")
                Path(single["project_root"], "single.txt").write_text("single", encoding="utf-8")
                Path(batch["project_root"], "batch.txt").write_text("batch", encoding="utf-8")
                deleted = project_store.delete_project("Shared name", str(root / "projects"), "single")
                remaining = project_store.list_projects()
                batch_still_exists = Path(batch["project_root"], "batch.txt").is_file()
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertTrue(deleted)
        self.assertTrue(batch_still_exists)
        self.assertEqual([record["key"] for record in remaining], [batch["key"]])

    def test_new_project_rejects_invalid_and_windows_reserved_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                for name in ("a:b", "a?b", "CON", "LPT1.txt", "trailing."):
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        project_store.ensure_project(name, str(root / "projects"), "single")
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

    def test_legacy_project_keeps_its_existing_root_when_metadata_is_upgraded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            projects_dir = root / "projects"
            legacy_root = projects_dir / "Legacy"
            legacy_root.mkdir(parents=True)
            key = project_store.project_key("Legacy", str(projects_dir), "single")
            legacy_record = {
                "key": key,
                "project_name": "Legacy",
                "project_directory": str(projects_dir),
                "project_root": str(legacy_root),
                "project_type": "single",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            index_path = root / "runtime" / "projects.json"
            index_path.parent.mkdir(parents=True)
            index_path.write_text(json.dumps([legacy_record]), encoding="utf-8")
            (legacy_root / project_store.PROJECT_MANIFEST_NAME).write_text(
                json.dumps(legacy_record),
                encoding="utf-8",
            )
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(index_path)
            try:
                upgraded = project_store.ensure_project("Legacy", str(projects_dir), "single")
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertEqual(Path(upgraded["project_root"]), legacy_root)
        self.assertEqual(upgraded["storage_layout"], "legacy")
        self.assertTrue(upgraded["project_id"])

    def test_delete_is_blocked_when_two_records_reference_the_same_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            projects_dir = root / "projects"
            shared_root = projects_dir / "shared"
            shared_root.mkdir(parents=True)
            records = []
            for project_type in ("single", "batch"):
                records.append(
                    {
                        "key": project_store.project_key("Shared", str(projects_dir), project_type),
                        "project_name": "Shared",
                        "project_directory": str(projects_dir),
                        "project_root": str(shared_root),
                        "project_type": project_type,
                    }
                )
            index_path = root / "runtime" / "projects.json"
            index_path.parent.mkdir(parents=True)
            index_path.write_text(json.dumps(records), encoding="utf-8")
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(index_path)
            try:
                with self.assertRaises(RuntimeError):
                    project_store.validate_project_deletion("Shared", str(projects_dir), "single")
                with self.assertRaises(RuntimeError):
                    project_store.delete_project("Shared", str(projects_dir), "single")
                still_exists = shared_root.is_dir()
                remaining = project_store.list_projects()
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertTrue(still_exists)
        self.assertEqual(len(remaining), 2)

    def test_delete_empty_project_removes_only_its_project_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project = project_store.ensure_project("Disposable", str(root / "exports"), "single")
                sibling = project_store.ensure_project("Keep", str(root / "exports"), "single")
                deleted = project_store.delete_project("Disposable", str(root / "exports"), "single")
                remaining = project_store.list_projects()
                removed_project_root_exists = Path(project["project_root"]).exists()
                sibling_project_root_exists = Path(sibling["project_root"]).is_dir()
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertTrue(deleted)
        self.assertFalse(removed_project_root_exists)
        self.assertTrue(sibling_project_root_exists)
        self.assertEqual([item["key"] for item in remaining], [sibling["key"]])

    def test_delete_project_removes_all_project_owned_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_index = project_store.PROJECT_INDEX_PATH
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project = project_store.ensure_project("Disposable", str(root / "exports"), "single")
                exported_video = Path(project["project_root"]) / "dubbed_video.mp4"
                nested_log = Path(project["project_root"]) / "processing" / "logs.txt"
                exported_video.write_bytes(b"video")
                nested_log.parent.mkdir(parents=True)
                nested_log.write_text("log", encoding="utf-8")
                exported_video.chmod(stat.S_IREAD)

                deleted = project_store.delete_project("Disposable", str(root / "exports"), "single")
                project_root_exists = Path(project["project_root"]).exists()
                records = project_store.list_projects()
            finally:
                project_store.PROJECT_INDEX_PATH = original_index

        self.assertTrue(deleted)
        self.assertFalse(project_root_exists)
        self.assertEqual(records, [])

    def test_replacing_a_video_clears_its_previous_processing_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "legacy-jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project = project_store.ensure_project("Replace", str(root / "projects"), "single")
                config = JobConfig(project_name="Replace", project_directory=str(root / "projects"))
                job = job_store.create_job("replace-video", "old.mp4", config)
                old_input = Path(job.files["video_input"])
                old_input.write_bytes(b"old-video")
                old_export = Path(project["project_root"]) / "exports" / "dubbed_video.mp4"
                old_export.write_bytes(b"old-export")
                old_transcript = Path(job.files["transcript_json"])
                old_voice = Path(job.files["voice_output"])
                old_thumbnail = Path(job_store.get_job_dir(job.job_id)) / "thumbnail.jpg"
                old_transcript.write_text('[{"text": "old"}]', encoding="utf-8")
                old_voice.write_bytes(b"old-voice")
                old_thumbnail.write_bytes(b"old-thumbnail")
                job.files["final_video"] = str(old_export)
                job.files["thumbnail"] = str(old_thumbnail)
                job.checkpoints = {"translation": "old-checkpoint"}
                job.status = "paused"
                job.progress = 100
                job.review_approved = True
                job_store.save_job(job)
                Path(job_store.get_job_logs_path(job.job_id)).write_text("old log", encoding="utf-8")

                replacement = root / "new.mov"
                replacement.write_bytes(b"new-video")
                updated = job_store.replace_job_input(job.job_id, str(replacement))
                logs = Path(job_store.get_job_logs_path(job.job_id)).read_text(encoding="utf-8")
                backup_exists = Path(job_store.get_job_json_path(job.job_id) + ".bak").exists()
                replacement_name = Path(updated.files["video_input"]).name
                replacement_bytes = Path(updated.files["video_input"]).read_bytes()
                old_input_exists = old_input.exists()
                old_export_exists = old_export.exists()
                old_transcript_exists = old_transcript.exists()
                old_voice_exists = old_voice.exists()
                old_thumbnail_exists = old_thumbnail.exists()
                legacy_output_exists = (Path(job_store.get_job_dir(job.job_id)) / "output").exists()
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        self.assertEqual(updated.original_filename, "new.mov")
        self.assertEqual(replacement_name, "video.mov")
        self.assertEqual(replacement_bytes, b"new-video")
        self.assertFalse(old_input_exists)
        self.assertFalse(old_export_exists)
        self.assertFalse(old_transcript_exists)
        self.assertFalse(old_voice_exists)
        self.assertFalse(old_thumbnail_exists)
        self.assertFalse(legacy_output_exists)
        self.assertEqual(updated.status, "pending")
        self.assertEqual(updated.progress, 0)
        self.assertEqual(updated.checkpoints, {})
        self.assertFalse(updated.review_approved)
        self.assertFalse(backup_exists)
        self.assertIn("Previous processing data was removed", logs)
        self.assertNotIn("old log", logs)

    def test_replacing_a_video_removes_an_untracked_legacy_thumbnail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "legacy-jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project_store.ensure_project("Replace thumbnail", str(root / "projects"), "single")
                config = JobConfig(project_name="Replace thumbnail", project_directory=str(root / "projects"))
                job = job_store.create_job("replace-thumbnail", "old.mp4", config)
                Path(job.files["video_input"]).write_bytes(b"old-video")
                legacy_thumbnail = Path(job_store.get_job_dir(job.job_id)) / "thumbnail.jpg"
                legacy_thumbnail.write_bytes(b"old-thumbnail")
                replacement = root / "new.mp4"
                replacement.write_bytes(b"new-video")

                updated = job_store.replace_job_input(job.job_id, str(replacement))
                legacy_thumbnail_exists = legacy_thumbnail.exists()
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        self.assertIsNotNone(updated)
        self.assertFalse(legacy_thumbnail_exists)

    def test_restart_discards_artifacts_and_checkpoints_but_keeps_source_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_jobs_dir = job_store.JOBS_DIR
            original_project_index = project_store.PROJECT_INDEX_PATH
            job_store.JOBS_DIR = str(root / "legacy-jobs")
            project_store.PROJECT_INDEX_PATH = str(root / "runtime" / "projects.json")
            try:
                project = project_store.ensure_project("Restart", str(root / "projects"), "single")
                config = JobConfig(project_name="Restart", project_directory=str(root / "projects"))
                job = job_store.create_job("restart-video", "source.mp4", config)
                input_path = Path(job.files["video_input"])
                input_path.write_bytes(b"source-video")
                transcript_path = Path(job.files["transcript_json"])
                voice_path = Path(job.files["voice_output"])
                srt_path = Path(job.files["srt_output"])
                final_video_path = Path(job.files["final_video"])
                thumbnail_path = Path(job_store.get_job_dir(job.job_id)) / "thumbnail.jpg"
                transcript_path.write_text('[{"text": "old"}]', encoding="utf-8")
                voice_path.write_bytes(b"voice")
                srt_path.write_text("old subtitles", encoding="utf-8")
                final_video_path.write_bytes(b"old-export")
                thumbnail_path.write_bytes(b"thumbnail")
                job.files["thumbnail"] = str(thumbnail_path)
                job.checkpoints = {"translation": "checkpoint", "render": "checkpoint"}
                job.status = "done"
                job.progress = 100
                job.resume_step = "rendering"
                job.review_approved = True
                job_store.save_job(job)

                restarted = job_store.prepare_job_restart(job.job_id)
                saved = job_store.get_job(job.job_id)
                source_bytes = input_path.read_bytes()
                source_exists = input_path.is_file()
                thumbnail_exists = thumbnail_path.is_file()
                transcript_exists = transcript_path.exists()
                voice_exists = voice_path.exists()
                srt_exists = srt_path.exists()
                final_video_exists = final_video_path.exists()
                voice_parts_exists = (Path(job_store.get_job_dir(job.job_id)) / "temp" / "voice_parts").is_dir()
            finally:
                job_store.JOBS_DIR = original_jobs_dir
                project_store.PROJECT_INDEX_PATH = original_project_index

        self.assertIsNotNone(restarted)
        self.assertTrue(source_exists)
        self.assertEqual(source_bytes, b"source-video")
        self.assertTrue(thumbnail_exists)
        self.assertFalse(transcript_exists)
        self.assertFalse(voice_exists)
        self.assertFalse(srt_exists)
        self.assertFalse(final_video_exists)
        self.assertTrue(voice_parts_exists)
        self.assertEqual(saved.status, "pending")
        self.assertEqual(saved.progress, 0)
        self.assertEqual(saved.step, "queued")
        self.assertEqual(saved.resume_step, "")
        self.assertEqual(saved.checkpoints, {})
        self.assertFalse(saved.review_approved)


if __name__ == "__main__":
    unittest.main()
