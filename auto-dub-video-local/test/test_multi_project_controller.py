import sys
import queue
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.desktop import qml_controller
from autodub.desktop.qml_controller import AutoDubController
from autodub.schemas.job import JobConfig


class MultiProjectControllerTests(unittest.TestCase):
    def test_target_language_replaces_an_incompatible_saved_voice(self):
        controller = SimpleNamespace(
            _target_language="vi",
            _tts_voice="vi-VN-NamMinhNeural",
            _voice_options_for_language=lambda language: {
                "vi": [{"voice": "vi-VN-HoaiMyNeural"}],
                "en": [{"voice": "en-US-JennyNeural"}, {"voice": "en-US-GuyNeural"}],
            }[language],
            targetLanguageChanged=SimpleNamespace(emit=Mock()),
            languageOptionsChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceOptionsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._normalized_voice_for_language = AutoDubController._normalized_voice_for_language.__get__(controller)

        AutoDubController.targetLanguage.fset(controller, "en")

        self.assertEqual(controller._target_language, "en")
        self.assertEqual(controller._tts_voice, "en-US-JennyNeural")
        controller.targetLanguageChanged.emit.assert_called_once()
        controller.ttsVoiceChanged.emit.assert_called_once()
        controller.ttsVoiceOptionsChanged.emit.assert_called_once()

    def test_voice_setter_rejects_a_voice_from_another_language(self):
        controller = SimpleNamespace(
            _target_language="en",
            _tts_voice="en-US-GuyNeural",
            _voice_options_for_language=lambda language: [
                {"voice": "en-US-JennyNeural"},
                {"voice": "en-US-GuyNeural"},
            ],
            ttsVoiceChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceOptionsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._normalized_voice_for_language = AutoDubController._normalized_voice_for_language.__get__(controller)

        AutoDubController.ttsVoice.fset(controller, "vi-VN-NamMinhNeural")

        self.assertEqual(controller._tts_voice, "en-US-JennyNeural")
        controller.ttsVoiceChanged.emit.assert_called_once()
        controller.ttsVoiceOptionsChanged.emit.assert_called_once()

    def test_pipeline_waits_for_startup_warmup_without_blocking_the_ui_thread(self):
        warmup_done = threading.Event()
        selected_job = SimpleNamespace(status="pending")
        controller = SimpleNamespace(
            _deleted_job_ids=set(),
            _initial_model_warmup_done=warmup_done,
            _model_runtime_lock=threading.Lock(),
        )

        with (
            patch.object(qml_controller.job_store, "get_job", return_value=selected_job),
            patch.object(qml_controller.job_store, "log_to_job"),
            patch("autodub.pipeline.process_job.process_job_sync") as process_job,
        ):
            worker = threading.Thread(
                target=AutoDubController._execute_pipeline,
                args=(controller, "project-a-video"),
            )
            worker.start()
            time.sleep(0.03)
            self.assertTrue(worker.is_alive())
            process_job.assert_not_called()

            warmup_done.set()
            worker.join(1)

        self.assertFalse(worker.is_alive())
        process_job.assert_called_once_with("project-a-video")

    def test_second_process_click_does_not_duplicate_an_already_queued_video(self):
        selected_job = SimpleNamespace(job_id="project-b-video", status="pending")
        controller = SimpleNamespace(
            _video_path="managed.mp4",
            _project_name="Project B",
            _project_directory="D:/Projects",
            _selected_job_id=selected_job.job_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=True)),
            _status_message="",
            statusMessageChanged=SimpleNamespace(emit=Mock()),
        )

        with (
            patch.object(qml_controller.job_store, "get_job", return_value=selected_job),
            patch.object(qml_controller, "create_desktop_job") as create_job,
        ):
            started = AutoDubController.startProjectJob(controller)

        self.assertFalse(started)
        create_job.assert_not_called()
        self.assertIn("already", controller._status_message)

    def test_new_project_setup_is_saved_before_it_enters_the_shared_queue(self):
        selected_job = SimpleNamespace(job_id="project-b-video", status="pending")
        calls = []
        controller = SimpleNamespace(
            _video_path="managed.mp4",
            _project_name="Project B",
            _project_directory="D:/Projects",
            _selected_job_id=selected_job.job_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _apply_setup_to_job=lambda job, review_approved: calls.append(("setup", job.job_id, review_approved)),
            _enqueue_job=lambda job_id: calls.append(("enqueue", job_id)),
            selectedJobChanged=SimpleNamespace(emit=Mock()),
            refreshJobs=Mock(),
        )

        with (
            patch.object(qml_controller.job_store, "get_job", return_value=selected_job),
            patch.object(qml_controller.job_store, "log_to_job"),
        ):
            started = AutoDubController.startProjectJob(controller)

        self.assertTrue(started)
        self.assertEqual(
            calls,
            [("setup", "project-b-video", False), ("enqueue", "project-b-video")],
        )

    def test_delayed_log_line_cannot_leak_into_another_selected_project(self):
        controller = SimpleNamespace(
            _selected_job_id="project-b-video",
            _logs="Project B log",
            _log_queue=queue.Queue(),
            logsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._log_queue.put(("job_log", "project-a-video", "Project A line"))

        AutoDubController._drain_log_queue(controller)

        self.assertEqual(controller._logs, "Project B log")
        controller.logsChanged.emit.assert_not_called()

    def test_async_link_import_keeps_the_project_that_started_the_download(self):
        controller = SimpleNamespace(
            _selected_job_id=None,
            _selected_project_key="single:d:/projects:project-c",
            _batch_job_ids=[],
            _create_video_thumbnail_path=Mock(return_value=""),
            _job_thumbnail_path=Mock(return_value="thumbnail.jpg"),
            _select_job=Mock(),
            _refresh_batch_model=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
            refreshJobs=Mock(),
        )
        target = {
            "project_key": "single:d:/projects:project-b",
            "project_name": "Project B",
            "project_directory": "D:/Projects",
            "project_type": "single",
            "selected_job_id": None,
            "config": JobConfig(project_name="Project B", project_directory="D:/Projects"),
        }
        created_job = SimpleNamespace(job_id="job-b", files={"video_input": "managed.mp4"})

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[{"key": target["project_key"]}]),
            patch.object(qml_controller, "create_desktop_job", return_value=created_job) as create_job,
        ):
            imported = AutoDubController._import_downloaded_video(
                controller,
                "downloaded.mp4",
                "single",
                target,
            )

        self.assertTrue(imported)
        create_job.assert_called_once_with(
            "downloaded.mp4",
            target["config"],
            project_name="Project B",
            project_directory="D:/Projects",
            project_key_value=target["project_key"],
        )
        controller._select_job.assert_not_called()
        controller.refreshJobs.assert_called_once()

    def test_async_link_import_does_not_recreate_a_deleted_project(self):
        controller = SimpleNamespace(
            _selected_job_id=None,
            _selected_project_key="",
        )
        target = {
            "project_key": "single:d:/projects:deleted",
            "project_name": "Deleted",
            "project_directory": "D:/Projects",
            "selected_job_id": None,
            "config": JobConfig(project_name="Deleted", project_directory="D:/Projects"),
        }

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[]),
            patch.object(qml_controller.QMessageBox, "warning"),
            patch.object(qml_controller, "create_desktop_job") as create_job,
        ):
            imported = AutoDubController._import_downloaded_video(
                controller,
                "downloaded.mp4",
                "single",
                target,
            )

        self.assertFalse(imported)
        create_job.assert_not_called()

    def test_channel_download_is_added_to_its_batch_without_starting_pipeline(self):
        project_key = "batch:d:/projects:campaign"
        target = {
            "project_key": project_key,
            "project_name": "Campaign",
            "project_directory": "D:/Projects",
            "project_type": "batch",
            "config": JobConfig(
                project_name="Campaign",
                project_directory="D:/Projects",
                project_type="batch",
            ),
            "channel_url": "https://www.youtube.com/@creator/videos",
            "channel_name": "Creator",
        }
        created_job = SimpleNamespace(job_id="channel-job", files={"video_input": "managed.mp4"})
        importer = SimpleNamespace(complete_video=Mock())
        controller = SimpleNamespace(
            _channel_import_targets={"session": target},
            _channel_importer=importer,
            _selected_project_key=project_key,
            _project_type="batch",
            _batch_job_ids=[],
            _create_video_thumbnail_path=Mock(return_value=""),
            _job_thumbnail_path=Mock(return_value="thumbnail.jpg"),
            _refresh_batch_model=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
            refreshJobs=Mock(),
        )
        candidate = {
            "remote_video_id": "abc",
            "source_url": "https://www.youtube.com/watch?v=abc",
            "platform": "YouTube",
            "uploader": "Creator",
        }

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[{"key": project_key}]),
            patch.object(qml_controller, "create_desktop_job", return_value=created_job) as create_job,
        ):
            AutoDubController._handle_channel_video_ready(
                controller,
                "downloaded.mp4",
                "workspace",
                candidate,
                project_key,
                "session",
            )

        self.assertEqual(controller._batch_job_ids, ["channel-job"])
        self.assertEqual(create_job.call_args.kwargs["project_name"], "Campaign")
        self.assertEqual(create_job.call_args.kwargs["project_directory"], "D:/Projects")
        self.assertTrue(create_job.call_args.kwargs["move_input"])
        media_source = create_job.call_args.kwargs["media_source"]
        self.assertEqual(media_source["type"], "channel")
        self.assertEqual(media_source["remote_video_id"], "abc")
        self.assertEqual(media_source["channel_url"], target["channel_url"])
        importer.complete_video.assert_called_once_with("session", "abc", True)
        controller.refreshJobs.assert_called_once()


if __name__ == "__main__":
    unittest.main()
