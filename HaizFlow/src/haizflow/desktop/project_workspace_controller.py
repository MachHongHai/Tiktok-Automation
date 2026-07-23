"""Project selection, catalog refresh, and incremental model updates."""

from __future__ import annotations

import os

from haizflow.desktop.media import thumbnail_source
from haizflow.services import project_store, video_store
from haizflow.services.desktop_videos import migrate_legacy_single_export


class ProjectWorkspaceController:
    def __init__(self, host):
        self._host = host

    def select_video(self, video) -> None:
        host = self._host
        host._selected_video_id = video.video_id
        host._project_name = video.project_name or os.path.splitext(video.original_filename)[0]
        host._project_directory = video.project_directory or host._project_directory
        host._project_type = "batch" if getattr(video, "project_type", "single") == "batch" else "single"
        host._selected_project_key = host._video_project_key(video)
        if (
            host._processing_queue.active_video_id != video.video_id
            and video.status != "processing"
            and (video.source_language != "auto" or video.output_format != "keep_ratio")
        ):
            video = video_store.update_video(video.video_id, source_language="auto", output_format="keep_ratio") or video
        if migrate_legacy_single_export(video):
            video = video_store.get_video(video.video_id) or video
        host._workflow_mode = video.mode
        host._target_language = str(video.target_language or "vi")
        host._tts_voice = host._normalized_voice_for_language(host._target_language, video.tts_voice)
        if host._tts_voice != video.tts_voice and video.status != "processing":
            video = video_store.update_video(video.video_id, tts_voice=host._tts_voice) or video
            video_store.log_to_video(video.video_id, "Updated an incompatible saved TTS voice to match the target language.")
        host._enable_audio_separation = video.enable_audio_separation
        host._original_volume = video.original_video_volume
        input_path = host._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
        host._video_path = input_path
        host._video_thumbnail_source = thumbnail_source(video.files.get("thumbnail") or "")
        host._load_video_preview(video)
        host._replace_logs(host._read_video_logs(video.video_id))
        host.videoPathChanged.emit()
        host.videoThumbnailChanged.emit()
        host.targetLanguageChanged.emit()
        host.ttsVoiceChanged.emit()
        host.ttsVoiceOptionsChanged.emit()
        host.enableAudioSeparationChanged.emit()
        host.originalVolumeChanged.emit()
        host.workflowModeChanged.emit()
        host.projectSetupChanged.emit()
        host.selectedVideoChanged.emit()
        host.processingChanged.emit()
        host.logsChanged.emit()

    def open_project_summary(self, project) -> None:
        host = self._host
        videos = project["videos"]
        host._project_name = project["project_name"]
        host._project_directory = project["project_directory"] or host._project_directory
        host._project_type = project["project_type"]
        host._selected_project_key = project["key"]
        host._batch_video_ids = [video.video_id for video in videos] if host._project_type == "batch" else []
        host._refresh_batch_model()
        if videos:
            self.select_video(videos[0])
        else:
            host.videoPath = ""
            host._selected_video_id = None
            host._clear_logs()
            host.selectedVideoChanged.emit()
            host.logsChanged.emit()
        host._project_type = project["project_type"]
        host.projectSetupChanged.emit()
        host.batchChanged.emit()
        if host._project_type == "batch":
            host.prepareChannelImport()

    def refresh_videos(self) -> None:
        host = self._host
        all_videos = video_store.list_videos()
        host._catalog_videos = {video.video_id: video for video in all_videos}
        host.videos.set_videos(all_videos[:40])
        summaries = host._build_project_summaries(all_videos, project_store.list_projects())
        host._project_summaries_by_key = {project["key"]: project for project in summaries}
        host.projects.set_projects(summaries)
        host.single_projects.set_projects([project for project in summaries if project["project_type"] == "single"])
        host.batch_projects.set_projects([project for project in summaries if project["project_type"] == "batch"])
        host._refresh_batch_model()
        host._selected_video_snapshot = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        host.selectedVideoChanged.emit()
        missing_thumbnails = host._missing_thumbnail_ids(all_videos)
        if missing_thumbnails and not host._thumbnail_refresh_running:
            host._thumbnail_refresh_running = True
            import threading

            threading.Thread(target=host._create_missing_thumbnails, args=(missing_thumbnails,), daemon=True).start()
        host._last_video_metadata_revision = video_store.metadata_revision()

    def apply_video_metadata_changes(self, video_ids: set[str]) -> bool:
        host = self._host
        changed = []
        affected_project_keys = set()
        for video_id in video_ids:
            previous = host._catalog_videos.get(video_id)
            current = video_store.get_video(video_id)
            if previous is None or current is None:
                return False
            host._catalog_videos[video_id] = current
            changed.append(current)
            affected_project_keys.add(host._video_project_key(previous))
            affected_project_keys.add(host._video_project_key(current))

        for video in changed:
            host.videos.update_video(video)
            host.batch_videos.update_video(video)

        for project_key in affected_project_keys:
            previous_summary = host._project_summaries_by_key.get(project_key)
            if previous_summary is None:
                return False
            project_videos = [
                video for video in host._catalog_videos.values()
                if host._video_project_key(video) == project_key
            ]
            summaries = host._build_project_summaries(project_videos, [previous_summary])
            if len(summaries) != 1:
                return False
            summary = summaries[0]
            host._project_summaries_by_key[project_key] = summary
            if not (
                host.projects.update_project(summary)
                and (
                    host.batch_projects.update_project(summary)
                    if summary["project_type"] == "batch"
                    else host.single_projects.update_project(summary)
                )
            ):
                return False

        if host._selected_video_id in video_ids:
            host._selected_video_snapshot = None
            host.selectedVideoChanged.emit()
        return True
