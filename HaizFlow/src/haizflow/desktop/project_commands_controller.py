"""Mutating project, batch, and video commands behind the QML facade."""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter

from haizflow.desktop.localization import QMessageBox
from haizflow.core.hardware import runtime_profile
from haizflow.pipeline.process_registry import cancel_video, pause_video
from haizflow.services import project_store, video_store
from haizflow.services.desktop_videos import create_desktop_video


class ProjectCommandsController:
    def __init__(self, host, *, create_video=None):
        self._host = host
        self._create_video = create_video or create_desktop_video

    def start_batch(self) -> None:
        host = self._host
        pending_ids = [
            video_id for video_id in host._batch_video_ids
            if (video := video_store.get_video(video_id)) and video.status == "pending"
        ]
        if not pending_ids:
            QMessageBox.information(None, "Batch queue", "Add at least one video to the queue.")
            return
        host._batch_running = True
        host._batch_stop_requested = False
        if not host._enqueue_videos(pending_ids):
            host._batch_running = False
            QMessageBox.information(None, "Batch queue", "These videos are already waiting or processing.")
            return
        host.batchChanged.emit()

    def batch_settings_values(self) -> dict[str, object]:
        host = self._host
        videos = [video for video_id in host._batch_video_ids if (video := video_store.get_video(video_id))]
        if not videos:
            return {
                "workflowMode": host._workflow_mode,
                "targetLanguage": host._target_language,
                "ttsVoice": host._tts_voice,
                "enableAudioSeparation": host._enable_audio_separation,
                "originalVolume": host._original_volume,
            }
        common, _count = Counter(
            (video.mode, video.target_language, video.tts_voice, video.enable_audio_separation, video.original_video_volume)
            for video in videos
        ).most_common(1)[0]
        workflow_mode, target_language, tts_voice, audio_separation, original_volume = common
        target_language = str(target_language or "vi")
        return {
            "workflowMode": "review" if workflow_mode == "review" else "A",
            "targetLanguage": target_language,
            "ttsVoice": host._normalized_voice_for_language(target_language, tts_voice),
            "enableAudioSeparation": bool(audio_separation),
            "originalVolume": int(original_volume),
        }

    def apply_batch_settings(self, workflow_mode, target_language, tts_voice, enable_audio_separation, original_volume) -> bool:
        host = self._host
        mode = "review" if workflow_mode == "review" else "A"
        language = str(target_language or "vi")
        voice = host._normalized_voice_for_language(language, tts_voice)
        updated = 0
        for video_id in host._batch_video_ids:
            if not (video := video_store.get_video(video_id)) or host._processing_queue.contains(video_id):
                continue
            video_store.update_video(
                video_id, mode=mode, source_language="auto", target_language=language, tts_voice=voice,
                enable_audio_separation=bool(enable_audio_separation), original_video_volume=int(original_volume),
            )
            updated += 1
        if not updated:
            QMessageBox.information(None, "Batch settings", "Add at least one video before applying settings.")
            return False
        host.refreshVideos()
        host.batchChanged.emit()
        return True

    def load_batch_settings(self) -> None:
        host = self._host
        values = self.batch_settings_values()
        host._workflow_mode = values["workflowMode"]
        host._target_language = values["targetLanguage"]
        host._tts_voice = values["ttsVoice"]
        host._enable_audio_separation = values["enableAudioSeparation"]
        host._original_volume = values["originalVolume"]
        host.workflowModeChanged.emit()
        host.targetLanguageChanged.emit()
        host.ttsVoiceChanged.emit()
        host.ttsVoiceOptionsChanged.emit()
        host.enableAudioSeparationChanged.emit()
        host.originalVolumeChanged.emit()

    def save_selected_video_settings(self) -> bool:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or video.project_type != "batch" or host._processing_queue.contains(video.video_id):
            return False
        host._apply_setup_to_video(video)
        video_store.log_to_video(video.video_id, "Per-video dubbing settings saved.")
        host.refreshVideos()
        host.selectedVideoChanged.emit()
        host.batchChanged.emit()
        return True

    def stop_batch(self) -> None:
        host = self._host
        if not host.isBatchRunning:
            return
        if QMessageBox.question(None, "Stop batch", "Stop the active video and cancel the remaining queue?") != QMessageBox.StandardButton.Yes:
            return
        host._batch_stop_requested = True
        active_video_id = host._processing_queue.active_video_id
        if active_video_id in host._batch_video_ids:
            cancel_video(active_video_id)
            video_store.update_video(active_video_id, status="cancelled", error=None, step="cancelled")
            video_store.log_to_video(active_video_id, "Batch stop requested. Active subprocesses were force-stopped.")
        for video_id in host._batch_video_ids:
            video = video_store.get_video(video_id)
            if video and host._processing_queue.discard(video_id):
                video_store.update_video(video_id, status="cancelled", error=None, step="cancelled")
                video_store.log_to_video(video_id, "Cancelled while waiting in the processing queue.")
        host._refresh_batch_model()
        host.batchChanged.emit()

    def clear_batch(self) -> None:
        host = self._host
        if host.isBatchRunning:
            return
        host._batch_video_ids = []
        host._refresh_batch_model()
        host.batchChanged.emit()

    def delete_current_batch(self) -> None:
        host = self._host
        batch_ids = list(host._batch_video_ids)
        if not host.hasOpenProject:
            return
        if not batch_ids:
            host.deleteCurrentProject()
            return
        message = (
            "Delete this batch project and all of its videos?\n\n"
            f"{host._project_name or 'this batch'}\n{len(batch_ids)} video(s)\n\n"
            "This removes processing logs, temporary data, copied inputs, and generated videos. "
            "If processing is active, it will be stopped first."
        )
        if QMessageBox.question(None, "Delete project", message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        current_key = host._selected_project_key
        try:
            project_store.validate_project_deletion_by_key(current_key)
        except Exception as exc:
            QMessageBox.warning(None, "Delete project", str(exc))
            return
        if not host._channel_importer.cancel_project(current_key):
            QMessageBox.information(None, "Channel import", "Channel import is still stopping. Try deleting the project again in a moment.")
            return
        for session_id, target in tuple(host._channel_import_targets.items()):
            if target.get("project_key") == current_key:
                host._channel_import_targets.pop(session_id, None)
        host._batch_stop_requested = True
        if host._processing_queue.active_video_id in batch_ids:
            cancel_video(host._processing_queue.active_video_id)
        failures, remaining_ids = [], []
        for video_id in batch_ids:
            video = video_store.get_video(video_id)
            if not video:
                continue
            host._deleted_video_ids.add(video_id)
            host._processing_queue.discard(video_id)
            if video.status == "processing":
                cancel_video(video_id)
            try:
                output_directory = host._batch_output_directory(video)
                if output_directory and os.path.isdir(output_directory):
                    shutil.rmtree(output_directory)
                video_store.delete_video(video_id)
                host._remove_empty_batch_output_parents(video)
            except Exception as exc:
                failures.append(f"{video.original_filename}: {exc}")
                remaining_ids.append(video_id)
        host._batch_video_ids = remaining_ids
        host._refresh_batch_model()
        host.batchChanged.emit()
        host._selected_video_id = None
        host._clear_logs()
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        if failures:
            QMessageBox.warning(None, "Batch delete incomplete",
                                "Some videos could not be deleted. You can retry after closing any program using them.\n\n"
                                + "\n".join(failures[:5]))
            return
        try:
            project_store.delete_project_by_key(current_key)
        except Exception as exc:
            QMessageBox.warning(None, "Delete project", str(exc))
            return
        host._selected_project_key = ""
        host._project_name = ""
        host.projectSetupChanged.emit()
        host.batchDeleted.emit()

    def start_video(self) -> None:
        host = self._host
        if not host._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return
        try:
            video = self._create_video(host._video_path, host._build_config())
        except Exception as exc:
            QMessageBox.critical(None, "Cannot start project", str(exc))
            return
        host._assign_project_thumbnail(video)
        host._selected_video_id = video.video_id
        host._replace_logs(host._read_video_logs(video.video_id))
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host._enqueue_video(video.video_id)

    def start_project_video(self) -> bool:
        host = self._host
        if not host._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return False
        if not host._project_name.strip():
            QMessageBox.warning(None, "Project name", "Enter a project name.")
            return False
        if not host._project_directory.strip():
            QMessageBox.warning(None, "Project storage location", "Choose a location for this project.")
            return False
        selected_video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if selected_video and host._processing_queue.contains(selected_video.video_id):
            host._status_message = "This video is already waiting or processing."
            host.statusMessageChanged.emit()
            return False
        if selected_video and selected_video.status == "pending":
            host._apply_setup_to_video(selected_video, review_approved=False)
            video_store.log_to_video(selected_video.video_id, "Processing requested for the imported video.")
            host._enqueue_video(selected_video.video_id)
            host.selectedVideoChanged.emit()
            host.refreshVideos()
            return True
        if selected_video:
            return False
        try:
            video = self._create_video(
                host._video_path, host._build_config(), project_name=host._project_name,
                project_directory=host._project_directory, project_key_value=host._selected_project_key,
            )
        except Exception as exc:
            QMessageBox.critical(None, "Cannot create project", str(exc))
            return False
        host._assign_project_thumbnail(video)
        host._selected_video_id = video.video_id
        host._replace_logs(host._read_video_logs(video.video_id))
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host._enqueue_video(video.video_id)
        return True

    def stop_video(self) -> None:
        host = self._host
        selected_video_id = host._selected_video_id
        if not selected_video_id or selected_video_id != host._processing_queue.active_video_id:
            return
        selected_video = video_store.get_video(selected_video_id)
        if not selected_video:
            return
        if host.isSelectedBatchVideo:
            self.stop_batch()
            return
        if QMessageBox.question(None, "Pause video", "Pause this video? You can resume it later from Projects.") != QMessageBox.StandardButton.Yes:
            return
        resume_step = selected_video.step
        pause_video(selected_video_id)
        video_store.update_video(selected_video_id, status="paused", error=None, step="paused",
                                 resume_step=resume_step, step_detail=f"Paused during {resume_step or 'startup'}")
        video_store.log_to_video(selected_video_id, "Pause requested. Active subprocesses were stopped.")
        host.selectedVideoChanged.emit()
        host.refreshVideos()

    def resume_selected_video(self) -> None:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or video.status != "paused":
            return
        video_store.update_video(video.video_id, status="pending", step="queued", step_detail="Queued to resume")
        host._enqueue_video(video.video_id)
        host.selectedVideoChanged.emit()

    def restart_selected_video(self) -> None:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or host._processing_queue.contains(video.video_id):
            return
        if host._device_switching:
            QMessageBox.information(None, "Processing device", "Wait for the processing device to finish switching before restarting.")
            return
        if QMessageBox.question(None, "Restart video", "Apply the current dubbing setup and restart this project?") != QMessageBox.StandardButton.Yes:
            return
        host._apply_setup_to_video(video, review_approved=False)
        restarted = video_store.prepare_video_restart(video.video_id)
        if not restarted:
            return
        video_store.log_to_video(restarted.video_id, f"Restart requested with the latest dubbing setup and runtime: {runtime_profile().summary}.")
        host._enqueue_video(restarted.video_id)
        host.selectedVideoChanged.emit()

    def approve_translation_review(self, payload: str) -> None:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or video.status != "awaiting_review":
            return
        try:
            segments = json.loads(payload)
            if not isinstance(segments, list) or any(not str(item.get("text", "")).strip() for item in segments):
                raise ValueError("Every translation must contain text.")
            with open(video.files["transcript_json"], "w", encoding="utf-8") as file:
                json.dump(segments, file, ensure_ascii=False, indent=2)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(None, "Translation review", str(exc))
            return
        video_store.update_video(video.video_id, review_approved=True, status="pending", step="queued",
                                 step_detail="Queued to create dub")
        video_store.log_to_video(video.video_id, f"Translation review approved with {len(segments)} edited segments. Added to the processing queue.")
        host._enqueue_video(video.video_id)
        host.selectedVideoChanged.emit()

    def delete_selected_video(self) -> None:
        host = self._host
        if not host._selected_video_id:
            QMessageBox.information(None, "No video selected", "Select a video in this batch first.")
            return
        video_id = host._selected_video_id
        video = video_store.get_video(video_id)
        label = video.original_filename if video else video_id
        if QMessageBox.question(
            None, "Remove video",
            f"Remove this video from the batch project and delete its generated files?\n\n{label}\n\n"
            "If it is running, it will be stopped first.",
        ) != QMessageBox.StandardButton.Yes:
            return
        if video and (video.status == "processing" or host._processing_queue.active_video_id == video_id):
            cancel_video(video_id)
            video_store.update_video(video_id, status="cancelled", error=None, step="cancelled")
        host._deleted_video_ids.add(video_id)
        host._processing_queue.discard(video_id)
        try:
            deleted = video_store.delete_video(video_id)
        except Exception as exc:
            QMessageBox.critical(None, "Delete failed", str(exc))
            return
        if not deleted:
            QMessageBox.information(None, "Already removed", "Video data was already removed.")
        if video_id in host._batch_video_ids:
            host._batch_video_ids.remove(video_id)
            host._refresh_batch_model()
            host.batchChanged.emit()
        host._selected_video_id = None
        host._clear_logs()
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host.videoDeleted.emit()

    def delete_current_project(self) -> None:
        host = self._host
        if not host.hasOpenProject:
            QMessageBox.information(None, "Delete project", "Select a project first.")
            return
        current_key = host._selected_project_key
        project_videos = [
            video for video in video_store.list_videos()
            if video.project_directory and host._video_project_key(video) == current_key
        ]
        suffix = "" if not project_videos else f"\n\nThis also removes {len(project_videos)} video(s) and their generated files."
        if QMessageBox.question(
            None, "Delete project",
            f"Delete project '{host._project_name}' and all files inside its project folder?{suffix}",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            project_store.validate_project_deletion_by_key(current_key)
        except Exception as exc:
            QMessageBox.critical(None, "Delete project", str(exc))
            return
        if not host._channel_importer.cancel_project(current_key):
            QMessageBox.information(None, "Channel import", "Channel import is still stopping. Try deleting the project again in a moment.")
            return
        for session_id, target in tuple(host._channel_import_targets.items()):
            if target.get("project_key") == current_key:
                host._channel_import_targets.pop(session_id, None)
        try:
            for video in project_videos:
                host._processing_queue.discard(video.video_id)
                if video.status == "processing" or host._processing_queue.active_video_id == video.video_id:
                    cancel_video(video.video_id)
                    video_store.update_video(video.video_id, status="cancelled", error=None, step="cancelled")
                host._deleted_video_ids.add(video.video_id)
                video_store.delete_video(video.video_id)
            project_store.delete_project_by_key(current_key)
        except Exception as exc:
            QMessageBox.critical(None, "Delete project", str(exc))
            return
        host._selected_video_id = None
        host._selected_project_key = ""
        host._batch_video_ids = []
        host._clear_logs()
        host.videoPath = ""
        host._refresh_batch_model()
        host.selectedVideoChanged.emit()
        host.projectSetupChanged.emit()
        host.logsChanged.emit()
        host.batchChanged.emit()
        host.refreshVideos()
        host.videoDeleted.emit()
