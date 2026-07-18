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

from haizflow.desktop import qml_controller
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.schemas.video import VideoConfig


class MultiProjectControllerTests(unittest.TestCase):
    def test_close_confirmation_is_only_required_for_background_work(self):
        idle_controller = SimpleNamespace(
            _processing_queue=SimpleNamespace(has_work=False),
            _url_importer=SimpleNamespace(busy=False),
            _channel_importer=SimpleNamespace(busy=False),
            _close_confirmed=False,
        )
        self.assertTrue(HaizFlowController._confirm_application_close(idle_controller))

        busy_controller = SimpleNamespace(
            _processing_queue=SimpleNamespace(has_work=True),
            _url_importer=SimpleNamespace(busy=False),
            _channel_importer=SimpleNamespace(busy=False),
            _close_confirmed=False,
        )
        with patch.object(
            qml_controller.QMessageBox,
            "question",
            return_value=qml_controller.QMessageBox.StandardButton.Cancel,
        ):
            self.assertFalse(HaizFlowController._confirm_application_close(busy_controller))
        self.assertFalse(busy_controller._close_confirmed)

    def test_shutdown_pauses_active_video_and_closes_the_queue(self):
        active = SimpleNamespace(
            video_id="active-video",
            status="processing",
            step="rendering",
            resume_step="",
        )
        waiting = SimpleNamespace(video_id="waiting-video", status="pending")
        processing_queue = SimpleNamespace(
            active_video_id=active.video_id,
            pending_ids=Mock(return_value=[waiting.video_id]),
            shutdown=Mock(return_value=True),
        )
        controller = SimpleNamespace(
            _shutdown_started=False,
            _initial_model_warmup_done=threading.Event(),
            _processing_queue=processing_queue,
            _url_importer=SimpleNamespace(shutdown=Mock(return_value=True)),
            _channel_importer=SimpleNamespace(shutdown=Mock(return_value=True)),
            _warmup_thread=None,
            _on_video_log=Mock(),
        )

        with (
            patch.object(qml_controller, "unsubscribe_log") as unsubscribe,
            patch.object(qml_controller, "pause_video") as pause,
            patch.object(qml_controller, "shutdown_hymt2_worker") as shutdown_translation,
            patch.object(
                qml_controller.video_store,
                "get_video",
                side_effect=lambda video_id: active if video_id == active.video_id else waiting,
            ),
            patch.object(qml_controller.video_store, "update_video") as update_video,
            patch.object(qml_controller.video_store, "log_to_video"),
            patch("haizflow.pipeline.transcribe.release_warm_whisperx_model") as release_whisper,
        ):
            HaizFlowController.shutdown(controller)
            HaizFlowController.shutdown(controller)

        self.assertTrue(controller._shutdown_started)
        self.assertTrue(controller._initial_model_warmup_done.is_set())
        unsubscribe.assert_called_once_with(controller._on_video_log)
        pause.assert_called_once_with(active.video_id)
        processing_queue.shutdown.assert_called_once_with(timeout_seconds=10.0)
        shutdown_translation.assert_called_once()
        release_whisper.assert_called_once()
        update_video.assert_any_call(
            active.video_id,
            status="paused",
            error=None,
            step="paused",
            resume_step="rendering",
            step_detail="Paused during application exit (rendering)",
            estimated_remaining_seconds=None,
        )
        update_video.assert_any_call(
            waiting.video_id,
            step="queued",
            step_detail="Waiting to be started after the application exited",
        )

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
        controller._normalized_voice_for_language = HaizFlowController._normalized_voice_for_language.__get__(controller)

        HaizFlowController.targetLanguage.fset(controller, "en")

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
        controller._normalized_voice_for_language = HaizFlowController._normalized_voice_for_language.__get__(controller)

        HaizFlowController.ttsVoice.fset(controller, "vi-VN-NamMinhNeural")

        self.assertEqual(controller._tts_voice, "en-US-JennyNeural")
        controller.ttsVoiceChanged.emit.assert_called_once()
        controller.ttsVoiceOptionsChanged.emit.assert_called_once()

    def test_pipeline_waits_for_startup_warmup_without_blocking_the_ui_thread(self):
        warmup_done = threading.Event()
        selected_video = SimpleNamespace(status="pending")
        controller = SimpleNamespace(
            _deleted_video_ids=set(),
            _initial_model_warmup_done=warmup_done,
            _model_runtime_lock=threading.Lock(),
        )

        with (
            patch.object(qml_controller.video_store, "get_video", return_value=selected_video),
            patch.object(qml_controller.video_store, "log_to_video"),
            patch("haizflow.pipeline.process_video.process_video_sync") as process_video,
        ):
            worker = threading.Thread(
                target=HaizFlowController._execute_pipeline,
                args=(controller, "project-a-video"),
            )
            worker.start()
            time.sleep(0.03)
            self.assertTrue(worker.is_alive())
            process_video.assert_not_called()

            warmup_done.set()
            worker.join(1)

        self.assertFalse(worker.is_alive())
        process_video.assert_called_once_with("project-a-video")

    def test_second_process_click_does_not_duplicate_an_already_queued_video(self):
        selected_video = SimpleNamespace(video_id="project-b-video", status="pending")
        controller = SimpleNamespace(
            _video_path="managed.mp4",
            _project_name="Project B",
            _project_directory="D:/Projects",
            _selected_video_id=selected_video.video_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=True)),
            _status_message="",
            statusMessageChanged=SimpleNamespace(emit=Mock()),
        )

        with (
            patch.object(qml_controller.video_store, "get_video", return_value=selected_video),
            patch.object(qml_controller, "create_desktop_video") as create_video,
        ):
            started = HaizFlowController.startProjectVideo(controller)

        self.assertFalse(started)
        create_video.assert_not_called()
        self.assertIn("already", controller._status_message)

    def test_new_project_setup_is_saved_before_it_enters_the_shared_queue(self):
        selected_video = SimpleNamespace(video_id="project-b-video", status="pending")
        calls = []
        controller = SimpleNamespace(
            _video_path="managed.mp4",
            _project_name="Project B",
            _project_directory="D:/Projects",
            _selected_video_id=selected_video.video_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _apply_setup_to_video=lambda video, review_approved: calls.append(("setup", video.video_id, review_approved)),
            _enqueue_video=lambda video_id: calls.append(("enqueue", video_id)),
            selectedVideoChanged=SimpleNamespace(emit=Mock()),
            refreshVideos=Mock(),
        )

        with (
            patch.object(qml_controller.video_store, "get_video", return_value=selected_video),
            patch.object(qml_controller.video_store, "log_to_video"),
        ):
            started = HaizFlowController.startProjectVideo(controller)

        self.assertTrue(started)
        self.assertEqual(
            calls,
            [("setup", "project-b-video", False), ("enqueue", "project-b-video")],
        )

    def test_delayed_log_line_cannot_leak_into_another_selected_project(self):
        controller = SimpleNamespace(
            _selected_video_id="project-b-video",
            _logs="Project B log",
            _log_queue=queue.Queue(),
            logsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._log_queue.put(("video_log", "project-a-video", "Project A line"))

        HaizFlowController._drain_log_queue(controller)

        self.assertEqual(controller._logs, "Project B log")
        controller.logsChanged.emit.assert_not_called()

    def test_async_link_import_keeps_the_project_that_started_the_download(self):
        controller = SimpleNamespace(
            _selected_video_id=None,
            _selected_project_key="single:d:/projects:project-c",
            _batch_video_ids=[],
            _create_video_thumbnail_path=Mock(return_value=""),
            _video_thumbnail_path=Mock(return_value="thumbnail.jpg"),
            _select_video=Mock(),
            _refresh_batch_model=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
            refreshVideos=Mock(),
        )
        target = {
            "project_key": "single:d:/projects:project-b",
            "project_name": "Project B",
            "project_directory": "D:/Projects",
            "project_type": "single",
            "selected_video_id": None,
            "config": VideoConfig(project_name="Project B", project_directory="D:/Projects"),
        }
        created_video = SimpleNamespace(video_id="video-b", files={"video_input": "managed.mp4"})

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[{"key": target["project_key"]}]),
            patch.object(qml_controller, "create_desktop_video", return_value=created_video) as create_video,
        ):
            imported = HaizFlowController._import_downloaded_video(
                controller,
                "downloaded.mp4",
                "single",
                target,
            )

        self.assertTrue(imported)
        create_video.assert_called_once_with(
            "downloaded.mp4",
            target["config"],
            project_name="Project B",
            project_directory="D:/Projects",
            project_key_value=target["project_key"],
        )
        controller._select_video.assert_not_called()
        controller.refreshVideos.assert_called_once()

    def test_async_link_import_does_not_recreate_a_deleted_project(self):
        controller = SimpleNamespace(
            _selected_video_id=None,
            _selected_project_key="",
        )
        target = {
            "project_key": "single:d:/projects:deleted",
            "project_name": "Deleted",
            "project_directory": "D:/Projects",
            "selected_video_id": None,
            "config": VideoConfig(project_name="Deleted", project_directory="D:/Projects"),
        }

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[]),
            patch.object(qml_controller.QMessageBox, "warning"),
            patch.object(qml_controller, "create_desktop_video") as create_video,
        ):
            imported = HaizFlowController._import_downloaded_video(
                controller,
                "downloaded.mp4",
                "single",
                target,
            )

        self.assertFalse(imported)
        create_video.assert_not_called()

    def test_channel_download_is_added_to_its_batch_without_starting_pipeline(self):
        project_key = "batch:d:/projects:campaign"
        target = {
            "project_key": project_key,
            "project_name": "Campaign",
            "project_directory": "D:/Projects",
            "project_type": "batch",
            "config": VideoConfig(
                project_name="Campaign",
                project_directory="D:/Projects",
                project_type="batch",
            ),
            "channel_url": "https://www.youtube.com/@creator/videos",
            "channel_name": "Creator",
        }
        created_video = SimpleNamespace(video_id="channel-video", files={"video_input": "managed.mp4"})
        importer = SimpleNamespace(complete_video=Mock())
        controller = SimpleNamespace(
            _channel_import_targets={"session": target},
            _channel_importer=importer,
            _selected_project_key=project_key,
            _project_type="batch",
            _batch_video_ids=[],
            _create_video_thumbnail_path=Mock(return_value=""),
            _video_thumbnail_path=Mock(return_value="thumbnail.jpg"),
            _refresh_batch_model=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
            refreshVideos=Mock(),
        )
        candidate = {
            "remote_video_id": "abc",
            "source_url": "https://www.youtube.com/watch?v=abc",
            "platform": "YouTube",
            "uploader": "Creator",
        }

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[{"key": project_key}]),
            patch.object(qml_controller, "create_desktop_video", return_value=created_video) as create_video,
        ):
            HaizFlowController._handle_channel_video_ready(
                controller,
                "downloaded.mp4",
                "workspace",
                candidate,
                project_key,
                "session",
            )

        self.assertEqual(controller._batch_video_ids, ["channel-video"])
        self.assertEqual(create_video.call_args.kwargs["project_name"], "Campaign")
        self.assertEqual(create_video.call_args.kwargs["project_directory"], "D:/Projects")
        self.assertTrue(create_video.call_args.kwargs["move_input"])
        media_source = create_video.call_args.kwargs["media_source"]
        self.assertEqual(media_source["type"], "channel")
        self.assertEqual(media_source["remote_video_id"], "abc")
        self.assertEqual(media_source["channel_url"], target["channel_url"])
        importer.complete_video.assert_called_once_with("session", "abc", True)
        controller.refreshVideos.assert_called_once()


if __name__ == "__main__":
    unittest.main()
