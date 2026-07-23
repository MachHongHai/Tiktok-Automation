"""Project media import and channel-download commands behind the QML facade."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from queue import Empty

from haizflow.desktop.localization import QFileDialog, QMessageBox
from haizflow.desktop.media import collect_batch_video_paths, create_video_thumbnail_path, normalize_video_path
from haizflow.schemas.video import VideoConfig
from haizflow.services import project_store, video_store
from haizflow.services.channel_import import normalize_remote_url
from haizflow.services.desktop_videos import create_desktop_video


class ProjectImportController:
    """Owns media acquisition without exposing another QML API surface."""

    _VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}

    def __init__(self, host, *, create_video=None):
        self._host = host
        self._create_video = create_video or create_desktop_video
        self._storage_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._tasks: dict[int, dict] = {}
        self._task_threads: dict[int, threading.Thread] = {}
        self._next_task_id = 0

    def _can_import_in_background(self) -> bool:
        """Keep the small controller doubles used by unit tests synchronous."""
        return hasattr(self._host, "_media_import_events")

    def _queue_import(self, jobs: list[dict], context: dict) -> bool:
        """Run disk/FFmpeg work outside the QML thread and marshal results back."""
        host = self._host
        if not self._can_import_in_background():
            return False
        self._next_task_id += 1
        task_id = self._next_task_id
        self._tasks[task_id] = context
        host._media_import_busy = True
        host._media_import_total += len(jobs)
        host._media_import_status = "Adding video files in the background…"
        host.mediaImportChanged.emit()
        worker = threading.Thread(
            target=self._run_import_task,
            args=(task_id, jobs),
            name=f"haizflow-media-import-{task_id}",
            daemon=True,
        )
        self._task_threads[task_id] = worker
        worker.start()
        return True

    def _run_import_task(self, task_id: int, jobs: list[dict]) -> None:
        created_ids: list[str] = []
        errors: list[str] = []
        for job in jobs:
            if self._shutdown_event.is_set():
                errors.append(f"{os.path.basename(job['path'])}: import cancelled")
                break
            try:
                with self._storage_lock:
                    if job["operation"] == "replace":
                        video = video_store.replace_video_input(
                            job["video_id"], job["path"], media_source=job.get("media_source")
                        )
                        video.video_width, video.video_height = 0, 0
                    else:
                        kwargs = dict(job.get("create_kwargs") or {})
                        video = self._create_video(job["path"], job["config"], **kwargs)
                    self._assign_thumbnail_in_worker(video)
                created_ids.append(video.video_id)
            except Exception as exc:  # The GUI reports the individual file after the batch finishes.
                errors.append(f"{os.path.basename(job['path'])}: {exc}")
            finally:
                self._host._media_import_events.put({
                    "type": "progress", "task_id": task_id, "completed": 1,
                })
        self._host._media_import_events.put({
            "type": "finished", "task_id": task_id, "created_ids": created_ids, "errors": errors,
        })

    def _assign_thumbnail_in_worker(self, video) -> None:
        thumbnail = create_video_thumbnail_path(
            video.files["video_input"], os.path.join(video_store.get_video_dir(video.video_id), "thumbnail.jpg")
        )
        if thumbnail:
            video.files["thumbnail"] = thumbnail
            video_store.save_video(video)

    def drain_background_events(self) -> None:
        """Apply import results on the QObject's owning (GUI) thread."""
        host = self._host
        if not self._can_import_in_background():
            return
        changed = False
        while True:
            try:
                event = host._media_import_events.get_nowait()
            except Empty:
                break
            if event.get("type") == "progress":
                host._media_import_completed += int(event.get("completed", 0))
                changed = True
                continue
            context = self._tasks.pop(int(event["task_id"]), None)
            self._task_threads.pop(int(event["task_id"]), None)
            if context:
                self._apply_finished_import(
                    context, list(event.get("created_ids") or []), list(event.get("errors") or [])
                )
            changed = True
        if not self._tasks:
            host._media_import_busy = False
            host._media_import_total = 0
            host._media_import_completed = 0
            host._media_import_status = ""
            changed = True
        if changed:
            host.mediaImportChanged.emit()

    def _apply_finished_import(self, context: dict, created_ids: list[str], errors: list[str]) -> None:
        host = self._host
        errors = list(context.get("invalid_names") or []) + errors
        operation = context["operation"]
        project_key = context.get("project_key", "")
        if operation == "batch":
            if project_key == host._selected_project_key and host._project_type == "batch":
                host._batch_video_ids.extend(
                    video_id for video_id in created_ids if video_id not in host._batch_video_ids
                )
                host._refresh_batch_model()
                host.batchChanged.emit()
        elif operation == "create" and created_ids:
            video = video_store.get_video(created_ids[0])
            if video and project_key == host._selected_project_key:
                if context.get("as_batch"):
                    if video.video_id not in host._batch_video_ids:
                        host._batch_video_ids.append(video.video_id)
                    host._refresh_batch_model()
                    host.batchChanged.emit()
                else:
                    host._select_video(video)
        elif operation == "replace" and created_ids:
            video = video_store.get_video(created_ids[0])
            if video:
                destination = video.files["video_input"]
                update_open_view = host._selected_video_id == video.video_id
                if update_open_view:
                    host._set_video_path(destination, refresh_thumbnail=True)
                video_store.log_to_video(video.video_id, f"Input video replaced with: {video.original_filename}")
                if update_open_view:
                    host._replace_logs(host._read_video_logs(video.video_id))
                    host.videoThumbnailChanged.emit()
                    host.selectedVideoChanged.emit()
                    host.logsChanged.emit()
                host._log_queue.put("__QUEUE_CHANGED__")
        if created_ids:
            host.refreshVideos()
        if context.get("url_import"):
            message = "" if created_ids else "The video was downloaded but could not be added to the project."
            host._url_importer.complete_import(bool(created_ids), message)
        if context.get("channel_import"):
            host._channel_importer.complete_video(
                context["session_id"], context["remote_id"], bool(created_ids),
                "" if created_ids else (errors[0] if errors else "The video could not be added to the project."),
            )
        if errors and not context.get("channel_import") and not context.get("url_import"):
            QMessageBox.warning(None, "Some videos were skipped", self.batch_rejection_message(errors))

    def shutdown(self) -> None:
        self._shutdown_event.set()

    def download_inspected_video(self) -> None:
        host = self._host
        if not host.hasOpenProject:
            host._url_importer.complete_import(False, "Open or create a project before downloading a video.")
            return
        if host._project_type == "single" and host.isSelectedVideoProcessing:
            host._url_importer.complete_import(False, "Pause or finish the current video before replacing it.")
            return
        host._url_import_target = {
            "project_key": host._selected_project_key,
            "project_name": host._project_name,
            "project_directory": host._project_directory,
            "project_type": host._project_type,
            "selected_video_id": host._selected_video_id,
            "config": host._build_config(),
            "media_source": {
                "type": "video_url",
                "platform": host._url_importer.platform,
                "source_url": host._url_importer.url,
                "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        }
        if not host._url_importer.start_download(host._selected_project_root()):
            host._url_import_target = None

    def handle_url_download_ready(self, path, _workspace, mode) -> None:
        host = self._host
        target = host._url_import_target
        host._url_import_target = None
        if self._can_import_in_background():
            if self._queue_downloaded_video(path, mode, target):
                return
            host._url_importer.complete_import(False, "The video was downloaded but could not be added to the project.")
            return
        imported = self.import_downloaded_video(path, mode, target)
        message = "" if imported else "The video was downloaded but could not be added to the project."
        host._url_importer.complete_import(imported, message)

    def _queue_downloaded_video(self, path: str, mode: str, target) -> bool:
        host = self._host
        if not target:
            if mode == "batch":
                return self._queue_batch_paths([path], url_import=True)
            if host._selected_video_id:
                return self._queue_replace(host._selected_video_id, path, None, url_import=True)
            return self._queue_project_video(path, url_import=True)
        target_video_id = target.get("selected_video_id")
        if mode != "batch" and target_video_id:
            return self._queue_replace(target_video_id, path, target.get("media_source"), url_import=True)
        config = target.get("config")
        known_project_keys = {project.get("key") for project in project_store.list_projects()}
        if not isinstance(config, VideoConfig) or target.get("project_key") not in known_project_keys:
            return False
        return self._queue_import([{
            "operation": "create", "path": path, "config": config.model_copy(deep=True),
            "create_kwargs": {
                "project_name": str(target.get("project_name") or ""),
                "project_directory": str(target.get("project_directory") or ""),
                "project_key_value": str(target.get("project_key") or ""),
                "media_source": target.get("media_source"),
            },
        }], {"operation": "create", "project_key": str(target.get("project_key") or ""),
             "as_batch": mode == "batch", "url_import": True})

    def import_downloaded_video(self, path: str, mode: str, target) -> bool:
        host = self._host
        if not target:
            if mode == "batch":
                previous_count = host.batchCount
                self.import_batch_videos([path])
                return host.batchCount > previous_count
            if host._selected_video_id:
                return self.replace_video(host._selected_video_id, path)
            return self.import_video(path)

        target_video_id = target.get("selected_video_id")
        if mode != "batch" and target_video_id:
            return self.replace_video(target_video_id, path, target.get("media_source"))
        config = target.get("config")
        if not isinstance(config, VideoConfig):
            return False
        if target.get("project_key") not in {project.get("key") for project in project_store.list_projects()}:
            QMessageBox.warning(None, "Import video", "The destination project no longer exists.")
            return False
        try:
            kwargs = {
                "project_name": str(target.get("project_name") or ""),
                "project_directory": str(target.get("project_directory") or ""),
                "project_key_value": str(target.get("project_key") or ""),
            }
            if target.get("media_source"):
                kwargs["media_source"] = target["media_source"]
            video = self._create_video(path, config, **kwargs)
            self._assign_thumbnail(video)
        except Exception as exc:
            QMessageBox.warning(None, "Import video", str(exc))
            return False

        if target.get("project_key") == host._selected_project_key:
            if mode == "batch":
                host._batch_video_ids.append(video.video_id)
                host._refresh_batch_model()
                host.batchChanged.emit()
            else:
                host._select_video(video)
        host.refreshVideos()
        return True

    def current_project_media_keys(self) -> set[str]:
        host = self._host
        keys: set[str] = set()
        for video in video_store.list_videos():
            if not video.project_directory or host._video_project_key(video) != host._selected_project_key:
                continue
            source = getattr(video, "media_source", None)
            platform = str(getattr(source, "platform", "") or "").strip().lower()
            remote_id = str(getattr(source, "remote_video_id", "") or "").strip().lower()
            source_url = str(getattr(source, "source_url", "") or "").strip().lower()
            if platform and remote_id:
                keys.add(f"{platform}:{remote_id}")
            if source_url:
                keys.update((source_url, normalize_remote_url(source_url)))
        return keys

    def prepare_channel_import(self) -> bool:
        host = self._host
        if not host.hasOpenProject or host._project_type != "batch":
            QMessageBox.information(None, "Channel import", "Open or create a batch project before importing a channel.")
            return False
        host._channel_importer.attach_project(
            host._selected_project_key, host._selected_project_root(), self.current_project_media_keys()
        )
        return True

    def start_channel_downloads(self) -> bool:
        host = self._host
        if not self.prepare_channel_import() or host._channel_importer.selectedCount <= 0:
            return False
        session_id = host._channel_importer.sessionId
        if not session_id:
            return False
        self.remember_channel_import_target(session_id)
        if not host._channel_importer.start_downloads(2):
            host._channel_import_targets.pop(session_id, None)
            return False
        return True

    def remember_channel_import_target(self, session_id: str) -> None:
        host = self._host
        host._channel_import_targets[session_id] = {
            "project_key": host._selected_project_key,
            "project_name": host._project_name,
            "project_directory": host._project_directory,
            "project_type": "batch",
            "config": host._build_config().model_copy(deep=True),
            "channel_url": host._channel_importer.channelUrl,
            "channel_name": host._channel_importer.channelName,
        }

    def retry_channel_video(self, row: int) -> bool:
        host = self._host
        if not self.prepare_channel_import():
            return False
        session_id = host._channel_importer.sessionId
        if not session_id:
            return False
        self.remember_channel_import_target(session_id)
        if not host._channel_importer.retry(int(row)):
            host._channel_import_targets.pop(session_id, None)
            return False
        return True

    def handle_channel_video_ready(self, path, _workspace, candidate_payload, project_key, session_id) -> None:
        host = self._host
        target = host._channel_import_targets.get(session_id)
        candidate = dict(candidate_payload or {})
        remote_id = str(candidate.get("remote_video_id") or "")
        if not target or target.get("project_key") != project_key:
            host._channel_importer.complete_video(session_id, remote_id, False, "The destination project is no longer available.")
            return
        if project_key not in {project.get("key") for project in project_store.list_projects()}:
            host._channel_importer.complete_video(session_id, remote_id, False, "The destination project was deleted.")
            return
        source = {
            "type": "channel", "platform": str(candidate.get("platform") or ""),
            "remote_video_id": remote_id, "source_url": str(candidate.get("source_url") or ""),
            "channel_url": str(target.get("channel_url") or ""),
            "channel_name": str(target.get("channel_name") or candidate.get("uploader") or ""),
            "import_session_id": session_id,
            "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if self._can_import_in_background():
            queued = self._queue_import([{
                "operation": "create", "path": path, "config": target["config"].model_copy(deep=True),
                "create_kwargs": {
                    "project_name": str(target.get("project_name") or ""),
                    "project_directory": str(target.get("project_directory") or ""),
                    "media_source": source, "move_input": True, "project_key_value": project_key,
                },
            }], {"operation": "create", "project_key": project_key, "as_batch": True,
                 "channel_import": True, "session_id": session_id, "remote_id": remote_id})
            if queued:
                return
            host._channel_importer.complete_video(session_id, remote_id, False, "Unable to queue the imported video.")
            return
        try:
            video = self._create_video(
                path, target["config"].model_copy(deep=True),
                project_name=str(target.get("project_name") or ""),
                project_directory=str(target.get("project_directory") or ""),
                media_source=source, move_input=True, project_key_value=project_key,
            )
            self._assign_thumbnail(video)
        except Exception as exc:
            host._channel_importer.complete_video(session_id, remote_id, False, str(exc))
            return
        if project_key == host._selected_project_key and host._project_type == "batch":
            if video.video_id not in host._batch_video_ids:
                host._batch_video_ids.append(video.video_id)
            host._refresh_batch_model()
            host.batchChanged.emit()
        host.refreshVideos()
        host._channel_importer.complete_video(session_id, remote_id, True)

    def finish_channel_import_target(self, session_id: str) -> None:
        self._host._channel_import_targets.pop(str(session_id), None)

    def browse_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(None, "Choose input video", "", "Video files (*.mp4 *.mov *.mkv);;All files (*.*)")
        if path:
            self.import_video(path, replace_selected=True)

    def browse_project_directory(self) -> None:
        host = self._host
        os.makedirs(host._project_directory, exist_ok=True)
        path = QFileDialog.getExistingDirectory(None, "Choose project storage location", host._project_directory)
        if path:
            host._project_directory = os.path.abspath(path)
            host.projectSetupChanged.emit()

    def prepare_project(self, project_name: str, project_directory: str, project_type: str) -> bool:
        host = self._host
        project_name, project_directory = project_name.strip(), project_directory.strip()
        if not project_name:
            QMessageBox.warning(None, "Project name", "Enter a project name.")
            return False
        if not project_directory:
            QMessageBox.warning(None, "Project storage location", "Choose a location for this project.")
            return False
        host._project_name, host._project_directory = project_name, os.path.abspath(project_directory)
        host._project_type = "batch" if project_type == "batch" else "single"
        try:
            project = project_store.create_project(host._project_name, host._project_directory, host._project_type)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(None, "Project storage location", f"Cannot create the project at this location: {exc}")
            return False
        host._selected_project_key = project["key"]
        host.videoPath = ""
        host._selected_video_id, host._batch_video_ids = None, []
        host._refresh_batch_model()
        host._clear_logs()
        host.projectSetupChanged.emit()
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host.projectPrepared.emit()
        return True

    def import_video(self, path: str, *, replace_selected: bool = False) -> bool:
        host = self._host
        if replace_selected and host._selected_video_id:
            return self.replace_video(host._selected_video_id, path)
        normalized = normalize_video_path(path)
        if not os.path.isfile(normalized):
            QMessageBox.warning(None, "Invalid video", "The dropped file is unavailable.")
            return False
        if os.path.splitext(normalized)[1].lower() not in self._VIDEO_EXTENSIONS:
            QMessageBox.warning(None, "Unsupported file", "Choose an MP4, MOV, or MKV video file.")
            return False
        if not host.hasOpenProject:
            host._selected_video_id = None
            host.videoPath = normalized
            host.selectedVideoChanged.emit()
            return True
        if self._can_import_in_background():
            return self._queue_project_video(normalized)
        try:
            video = self._create_video(
                normalized, host._build_config(), project_name=host._project_name,
                project_directory=host._project_directory, project_key_value=host._selected_project_key,
            )
            host._assign_project_thumbnail(video)
        except Exception as exc:
            QMessageBox.critical(None, "Cannot import video", str(exc))
            return False
        host._select_video(video)
        host.refreshVideos()
        return True

    def replace_video(self, video_id: str | None, path: str, media_source=None) -> bool:
        host = self._host
        video = video_store.get_video(video_id) if video_id else None
        normalized = normalize_video_path(path)
        if not video:
            return False
        if video.status == "processing" or host._processing_queue.active_video_id == video.video_id:
            QMessageBox.information(None, "Replace video", "Pause or finish this video before replacing it.")
            return False
        if not os.path.isfile(normalized) or os.path.splitext(normalized)[1].lower() not in self._VIDEO_EXTENSIONS:
            QMessageBox.warning(None, "Invalid video", "Choose an MP4, MOV, or MKV video file.")
            return False
        if host._processing_queue.discard(video.video_id):
            host._update_queue_positions()
        if self._can_import_in_background():
            return self._queue_replace(video.video_id, normalized, media_source)
        try:
            video = video_store.replace_video_input(video.video_id, normalized, media_source=media_source)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(None, "Replace video", str(exc))
            return False
        destination = video.files["video_input"]
        video.video_width, video.video_height = 0, 0
        thumbnail = host._create_video_thumbnail_path(destination, host._video_thumbnail_path(video.video_id))
        if thumbnail:
            video.files["thumbnail"] = thumbnail
        video_store.save_video(video)
        update_open_view = host._selected_video_id == video.video_id
        if update_open_view:
            host._set_video_path(destination, refresh_thumbnail=True)
        video_store.log_to_video(video.video_id, f"Input video replaced with: {video.original_filename}")
        if update_open_view:
            host._replace_logs(host._read_video_logs(video.video_id))
            host.videoThumbnailChanged.emit()
            host.selectedVideoChanged.emit()
            host.logsChanged.emit()
        host.refreshVideos()
        host._log_queue.put("__QUEUE_CHANGED__")
        return True

    def browse_batch_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(None, "Choose videos for batch processing", "", "Video files (*.mp4 *.mov *.mkv);;All files (*.*)")
        if paths:
            self.import_batch_videos(paths)

    def browse_batch_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(None, "Choose a folder of videos for batch processing", "", QFileDialog.Option.ShowDirsOnly)
        if folder:
            self.import_batch_videos([folder])

    def import_batch_videos(self, paths) -> None:
        host = self._host
        valid_paths, invalid_names = collect_batch_video_paths(paths)
        if not valid_paths:
            if invalid_names:
                QMessageBox.warning(None, "Some videos were skipped", self.batch_rejection_message(invalid_names))
            else:
                QMessageBox.warning(None, "No supported videos", "Choose MP4, MOV, or MKV video files.")
            return
        if self._can_import_in_background():
            self._queue_batch_paths(valid_paths, invalid_names=invalid_names)
            return
        created_ids, errors = [], []
        for path in valid_paths:
            try:
                video = self._create_video(
                    path, host._build_config(), project_name=host._project_name,
                    project_directory=host._project_directory, project_key_value=host._selected_project_key,
                )
                self._assign_thumbnail(video)
                created_ids.append(video.video_id)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
        host._batch_video_ids.extend(created_ids)
        host._refresh_batch_model()
        host.refreshVideos()
        host.batchChanged.emit()
        rejected = invalid_names + errors
        if rejected:
            QMessageBox.warning(None, "Some videos were skipped", self.batch_rejection_message(rejected))

    def _queue_project_video(self, path: str, *, url_import: bool = False) -> bool:
        host = self._host
        return self._queue_import([{
            "operation": "create", "path": path, "config": host._build_config().model_copy(deep=True),
            "create_kwargs": {
                "project_name": host._project_name, "project_directory": host._project_directory,
                "project_key_value": host._selected_project_key,
            },
        }], {"operation": "create", "project_key": host._selected_project_key, "url_import": url_import})

    def _queue_batch_paths(self, paths, *, invalid_names=None, url_import: bool = False) -> bool:
        host = self._host
        valid_paths = list(paths)
        if not valid_paths:
            return False
        jobs = [{
            "operation": "create", "path": path, "config": host._build_config().model_copy(deep=True),
            "create_kwargs": {
                "project_name": host._project_name, "project_directory": host._project_directory,
                "project_key_value": host._selected_project_key,
            },
        } for path in valid_paths]
        context = {
            "operation": "batch", "project_key": host._selected_project_key,
            "url_import": url_import, "invalid_names": list(invalid_names or []),
        }
        return self._queue_import(jobs, context)

    def _queue_replace(self, video_id: str, path: str, media_source, *, url_import: bool = False) -> bool:
        host = self._host
        video = video_store.get_video(video_id)
        if not video:
            return False
        return self._queue_import([{
            "operation": "replace", "video_id": video_id, "path": path, "media_source": media_source,
        }], {"operation": "replace", "project_key": host._selected_project_key, "url_import": url_import})

    def batch_rejection_message(self, rejected) -> str:
        host = self._host
        shown = [str(item) for item in rejected][:12]
        remaining = len(rejected) - len(shown)
        if remaining:
            shown.append(f"... và {remaining} mục khác" if host._settings_language == "vi" else f"... and {remaining} more")
        heading = (
            f"{len(rejected)} mục không được hỗ trợ hoặc không thể đọc:"
            if host._settings_language == "vi"
            else f"{len(rejected)} unsupported or unreadable item(s):"
        )
        return f"{heading}\n\n" + "\n".join(shown)

    def _assign_thumbnail(self, video) -> None:
        host = self._host
        thumbnail = host._create_video_thumbnail_path(video.files["video_input"], host._video_thumbnail_path(video.video_id))
        if thumbnail:
            video.files["thumbnail"] = thumbnail
            video_store.save_video(video)
