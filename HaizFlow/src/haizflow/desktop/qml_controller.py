import os
import json
import queue
import threading
import time
from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QObject, Property, QTimer, Signal, Slot
from PySide6.QtQml import QmlNamedElement, QmlSingleton

from haizflow.desktop.activity_log import ActivityLogBuffer
from haizflow.desktop.catalog import POPULAR_TARGET_LANGUAGES
from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.desktop.localization import QMessageBox, _set_ui_language, _ui_text
from haizflow.desktop.media import (
    collect_batch_video_paths,
    create_video_thumbnail_path,
    normalize_video_path,
    open_path,
    resolve_video_file,
    thumbnail_source,
)
from haizflow.desktop.media_probe import VideoDimensionProbe
from haizflow.desktop.models import VideoListModel, ProjectGridModel, ProjectListModel
from haizflow.desktop.preview_media_controller import PreviewMediaController
from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.catalog_media_controller import CatalogMediaController
from haizflow.desktop.runtime_device_controller import RuntimeDeviceController
from haizflow.desktop.settings_controller import SettingsController
from haizflow.desktop.presenters import (
    build_project_summaries,
    format_duration,
    format_memory_size,
    language_label,
    voice_options_for_language,
)
from haizflow.desktop.url_import import VideoUrlImportCoordinator

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.core.events import subscribe_log, unsubscribe_log
from haizflow.core.hardware import (
    configure_processing_device,
    clear_runtime_profile_cache,
    detect_hardware_capabilities,
    processing_device_preference,
    recommended_processing_device,
    runtime_profile,
    validate_processing_device,
)
from haizflow.core.runtime_probe import probe_runtime
from haizflow.pipeline.process_registry import pause_video
from haizflow.schemas.video import CropSettings, VideoConfig, SubtitleStyle
from haizflow.services import desktop_settings, video_store, project_store
from haizflow.services.desktop_videos import create_desktop_video, migrate_legacy_single_export
from haizflow.services.processing_queue import SerialProcessingQueue
from haizflow.services.translation import shutdown_hymt2_worker, warm_hymt2_worker

QML_IMPORT_NAME = "HaizFlow"
QML_IMPORT_MAJOR_VERSION = 1


@QmlNamedElement("AppController")
@QmlSingleton
class HaizFlowController(QObject):
    _qml_instance = None
    _THUMBNAIL_RETRY_MAX_ATTEMPTS = 3
    _THUMBNAIL_RETRY_INITIAL_DELAY_SECONDS = 15.0

    videoPathChanged = Signal()
    videoThumbnailChanged = Signal()
    targetLanguageChanged = Signal()
    ttsVoiceChanged = Signal()
    ttsVoiceOptionsChanged = Signal()
    enableAudioSeparationChanged = Signal()
    originalVolumeChanged = Signal()
    workflowModeChanged = Signal()
    selectedVideoChanged = Signal()
    processingChanged = Signal()
    logsChanged = Signal()
    statusMessageChanged = Signal()
    previewChanged = Signal()
    previewOpenRequested = Signal()
    videoDeleted = Signal()
    batchDeleted = Signal()
    batchChanged = Signal()
    settingsChanged = Signal()
    hardwareChanged = Signal()
    languageOptionsChanged = Signal()
    projectSetupChanged = Signal()
    projectPrepared = Signal()
    urlImportFinished = Signal()
    channelImportChanged = Signal()
    mediaImportChanged = Signal()

    def __init__(self):
        super().__init__()
        type(self)._qml_instance = self
        self.videos = VideoListModel()
        self.projects = ProjectListModel()
        self.single_projects = ProjectGridModel()
        self.batch_projects = ProjectGridModel()
        self.batch_videos = VideoListModel()
        self._video_path = ""
        self._video_thumbnail_source = ""
        self._target_language = "vi"
        self._tts_voice = "vi-VN-HoaiMyNeural"
        self._enable_audio_separation = False
        self._original_volume = 60
        self._workflow_mode = "A"
        self._selected_video_id = None
        self._selected_video_snapshot = None
        self.selectedVideoChanged.connect(self._refresh_selected_video_snapshot)
        self._selected_project_key = ""
        self._device_switching = False
        self._pending_processing_device = ""
        self._model_runtime_lock = threading.Lock()
        self._initial_model_warmup_done = threading.Event()
        self._runtime_probe_error = ""
        self._deleted_video_ids = set()
        self._shutdown_started = False
        self._close_confirmed = False
        self._warmup_thread: threading.Thread | None = None
        self._startup_maintenance_thread: threading.Thread | None = None
        self._startup_maintenance_events = queue.Queue()
        self._processing_lifecycle = ProcessingLifecycleController(self)
        self._processing_queue = SerialProcessingQueue(
            self._execute_pipeline,
            on_started=self._on_queue_video_started,
            on_finished=self._on_queue_video_finished,
            on_idle=self._on_processing_queue_idle,
            on_error=self._on_processing_queue_error,
        )
        self._batch_video_ids = []
        self._catalog_videos = {}
        self._project_summaries_by_key = {}
        self._batch_running = False
        self._batch_stop_requested = False
        self._log_buffer = ActivityLogBuffer()
        self._logs = ""
        self._status_message = "Ready"
        self._subtitle_position_x = 51
        self._subtitle_position_y = 96
        self._caption_font_size = 36
        self._subtitle_box_width = 72
        self._subtitle_box_height = 6
        self._preview_source = ""
        self._preview_poster_source = ""
        self._preview_title = "Preview"
        self._preview_interactive = False
        self._preview_aspect_ratio = 16 / 9
        self._preview_edit_scope = "draft"
        self._preview_target_video_ids = []
        self._preview_group_keys = []
        self._preview_group_index = -1
        self._preview_original_style = None
        self._preview_media = PreviewMediaController(self)
        self._settings_controller = SettingsController(self)
        self._project_workspace = ProjectWorkspaceController(self)
        self._project_commands = ProjectCommandsController(self)
        self._project_import = ProjectImportController(self)
        self._catalog_media = CatalogMediaController(self)
        self._runtime_device = RuntimeDeviceController(self)
        settings = desktop_settings.load_settings()
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        self._settings_processing_device = settings["processing_device"]
        self._processing_device_origin = settings["processing_device_origin"]
        _set_ui_language(self._settings_language)
        # Re-check power and free VRAM at every launch before any model warm-up.
        clear_runtime_profile_cache()
        capabilities = detect_hardware_capabilities()
        self._hardware_capabilities = capabilities
        self._hardware_telemetry_active = False
        device_valid, device_message = validate_processing_device(self._settings_processing_device, capabilities)
        if self._processing_device_origin == "detected":
            selected_device = recommended_processing_device(capabilities)
        elif device_valid:
            selected_device = self._settings_processing_device
        else:
            selected_device = "cpu"
            self._processing_device_origin = "detected"
        if selected_device != self._settings_processing_device or settings.get("processing_device_origin") != self._processing_device_origin:
            self._settings_processing_device = selected_device
            settings["processing_device"] = selected_device
            settings["processing_device_origin"] = self._processing_device_origin
            try:
                desktop_settings.save_settings(settings)
            except OSError:
                pass
        if not device_valid and selected_device == "cpu":
            self._status_message = f"Saved GPU setting is unavailable: {device_message} Switched to CPU."
        configure_processing_device(self._settings_processing_device)
        self._active_processing_device = self._settings_processing_device
        self._project_directory = os.path.join(RUNTIME_DATA_DIR, "projects")
        self._project_name = ""
        self._project_type = "single"
        self._log_queue = queue.Queue()
        self._media_import_events = queue.Queue()
        self._media_import_busy = False
        self._media_import_total = 0
        self._media_import_completed = 0
        self._media_import_status = ""
        self._thumbnail_refresh_running = False
        self._thumbnail_retry_failures: dict[str, tuple[str, int, float]] = {}
        self._thumbnail_retry_lock = threading.Lock()
        self._dimension_probe = VideoDimensionProbe(self._on_video_dimensions_ready)
        self._url_importer = VideoUrlImportCoordinator(self)
        self._url_import_target = None
        self._url_importer.downloadReady.connect(self._handle_url_download_ready)
        self._url_importer.importFinished.connect(self.urlImportFinished.emit)
        self._channel_importer = ChannelImportCoordinator(self)
        self._channel_importer.set_worker_limit_provider(
            lambda: 1 if self._processing_queue.active_video_id else 2
        )
        self._channel_import_targets = {}
        self._channel_importer.changed.connect(self.channelImportChanged.emit)
        self._channel_importer.videoReady.connect(self._handle_channel_video_ready)
        self._channel_importer.downloadsFinished.connect(self._finish_channel_import_target)

        if os.getenv("HAIZFLOW_SMOKE_TEST") == "1":
            self._initial_model_warmup_done.set()
        else:
            self._warmup_thread = threading.Thread(
                target=self._warm_models_at_startup,
                name="haizflow-model-warmup",
                daemon=True,
            )
            self._warmup_thread.start()

        subscribe_log(self._on_video_log)
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._drain_log_queue)
        self._log_timer.start(500)

        self._media_import_timer = QTimer(self)
        self._media_import_timer.timeout.connect(self._drain_media_import_events)
        self._media_import_timer.start(100)

        self._startup_maintenance_timer = QTimer(self)
        self._startup_maintenance_timer.timeout.connect(self._drain_startup_maintenance_events)
        self._startup_maintenance_timer.start(100)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.poll_videos)
        self._status_timer.start(1000)

        self._hardware_timer = QTimer(self)
        self._hardware_timer.timeout.connect(self._refresh_live_hardware)
        self._hardware_timer.start(5000)

        self.refreshVideos()
        self._last_video_metadata_revision = video_store.metadata_revision()
        # Let Qt render the first frame before migrations touch large workspaces or invoke FFmpeg.
        QTimer.singleShot(0, self._start_startup_maintenance)

    def _drain_media_import_events(self) -> None:
        self._project_import.drain_background_events()

    def _start_startup_maintenance(self) -> None:
        if self._shutdown_started or self._startup_maintenance_thread:
            return
        self._startup_maintenance_thread = threading.Thread(
            target=self._run_startup_maintenance,
            name="haizflow-startup-maintenance",
            daemon=True,
        )
        self._startup_maintenance_thread.start()

    def _run_startup_maintenance(self) -> None:
        try:
            migrated = video_store.migrate_legacy_project_data()
            recovered = video_store.recover_interrupted_videos()
            self._migrate_legacy_project_thumbnails()
            self._startup_maintenance_events.put({"migrated": migrated, "recovered": recovered})
        except Exception as exc:
            self._startup_maintenance_events.put({"error": str(exc)})

    def _drain_startup_maintenance_events(self) -> None:
        try:
            result = self._startup_maintenance_events.get_nowait()
        except queue.Empty:
            return
        if result.get("error"):
            self._status_message = f"Startup maintenance could not finish: {result['error']}"
        else:
            migrated = result.get("migrated") or []
            recovered = result.get("recovered") or []
            if recovered:
                self._status_message = (
                    f"Recovered {len(recovered)} interrupted video(s). They are paused and ready to resume."
                )
            elif migrated:
                self._status_message = f"Organized {len(migrated)} video workspace(s) into their projects."
            self.refreshVideos()
        self.statusMessageChanged.emit()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and not self._close_confirmed:
            if not self._confirm_application_close():
                event.ignore()
                return True
        return super().eventFilter(watched, event)

    def _confirm_application_close(self) -> bool:
        return HaizFlowController._runtime_device_for(self)._confirm_application_close()

    def shutdown(self):
        return HaizFlowController._runtime_device_for(self).shutdown()

    def _warm_models(self):
        return HaizFlowController._runtime_device_for(self)._warm_models()

    def _warm_models_at_startup(self):
        return HaizFlowController._runtime_device_for(self)._warm_models_at_startup()

    def _warm_models_unlocked(self):
        return HaizFlowController._runtime_device_for(self)._warm_models_unlocked()

    def _switch_processing_device(self, preference: str):
        return HaizFlowController._runtime_device_for(self)._switch_processing_device(preference)

    def _pipeline_is_active(self) -> bool:
        return HaizFlowController._runtime_device_for(self)._pipeline_is_active()

    def _activate_pending_device_for_next_video(self, video_id: str) -> None:
        return HaizFlowController._runtime_device_for(self)._activate_pending_device_for_next_video(video_id)

    def _refresh_live_hardware(self):
        return HaizFlowController._runtime_device_for(self)._refresh_live_hardware()

    @Slot(bool)
    def setHardwareTelemetryActive(self, active: bool):
        return HaizFlowController._runtime_device_for(self).setHardwareTelemetryActive(active)

    def _apply_detected_processing_device(self, device: str):
        return HaizFlowController._runtime_device_for(self)._apply_detected_processing_device(device)

    def _set_warmup_status(self, detail: str):
        return HaizFlowController._runtime_device_for(self)._set_warmup_status(detail)

    @Property(QObject, constant=True)
    def videoModel(self):
        return self.videos

    @Property(QObject, constant=True)
    def projectModel(self):
        return self.projects

    @Property(QObject, constant=True)
    def singleProjectModel(self):
        return self.single_projects

    @Property(QObject, constant=True)
    def batchProjectModel(self):
        return self.batch_projects

    @Property(QObject, constant=True)
    def channelImporter(self):
        return self._channel_importer

    @Property(bool, notify=mediaImportChanged)
    def mediaImportBusy(self):
        return self._media_import_busy

    @Property(int, notify=mediaImportChanged)
    def mediaImportTotal(self):
        return self._media_import_total

    @Property(int, notify=mediaImportChanged)
    def mediaImportCompleted(self):
        return self._media_import_completed

    @Property(str, notify=mediaImportChanged)
    def mediaImportStatus(self):
        return self._media_import_status

    @Property(bool, notify=channelImportChanged)
    def hasChannelImportSession(self):
        return bool(self._channel_importer.sessionId)

    @Property(bool, notify=channelImportChanged)
    def channelImportBusy(self):
        return self._channel_importer.busy

    @Property(int, notify=channelImportChanged)
    def channelImportProgress(self):
        return self._channel_importer.progress

    @Property(str, notify=channelImportChanged)
    def channelImportStatus(self):
        return self._channel_importer.status

    @Property(str, notify=channelImportChanged)
    def channelImportName(self):
        return self._channel_importer.channelName

    @Property(int, notify=channelImportChanged)
    def channelImportCandidateCount(self):
        return self._channel_importer.candidateCount

    @Property(int, notify=channelImportChanged)
    def channelImportImportedCount(self):
        return self._channel_importer.importedCount

    @Property(int, notify=channelImportChanged)
    def channelImportFailedCount(self):
        return self._channel_importer.failedCount

    @Property(QObject, constant=True)
    def batchVideoModel(self):
        return self.batch_videos

    @Property(bool, notify=batchChanged)
    def isBatchRunning(self):
        return any(self._processing_queue.contains(video_id) for video_id in self._batch_video_ids)

    @Property(int, notify=batchChanged)
    def batchCount(self):
        return len(self._batch_video_ids)

    def _batch_catalog_videos(self):
        catalog = getattr(self, "_catalog_videos", {})
        videos = []
        for video_id in self._batch_video_ids:
            video = catalog.get(video_id)
            if video is None:
                video = video_store.get_video(video_id)
            if video is not None:
                videos.append(video)
        return videos

    @Property(int, notify=batchChanged)
    def batchCompletedCount(self):
        completed_states = {"done", "failed", "cancelled"}
        videos = self._batch_catalog_videos()
        return sum(1 for video in videos if video and video.status in completed_states)

    @Property(int, notify=batchChanged)
    def batchPendingCount(self):
        videos = self._batch_catalog_videos()
        return sum(
            1
            for video in videos
            if video and video.status == "pending" and not self._processing_queue.contains(video.video_id)
        )

    @Property(int, notify=batchChanged)
    def batchProgress(self):
        videos = self._batch_catalog_videos()
        return round(sum(video.progress for video in videos) / len(videos)) if videos else 0

    @Property(str, notify=batchChanged)
    def batchTargetLanguageLabel(self):
        if not self._batch_video_ids:
            return self._language_label(self._target_language)
        videos = self._batch_catalog_videos()
        languages = {video.target_language for video in videos if video}
        if len(languages) > 1:
            return "Mixed settings"
        return self._language_label(next(iter(languages))) if languages else self._language_label(self._target_language)

    @Property("QVariantList", notify=batchChanged)
    def batchVideoSizeGroups(self):
        return [
            {
                "sizeKey": group["size_key"],
                "label": group["label"],
                "count": len(group["videos"]),
                "customizedCount": sum(1 for video in group["videos"] if video.subtitle_override),
                "thumbnailSource": VideoListModel._thumbnail_source(group["videos"][0]),
            }
            for group in self._batch_dimension_groups()
        ]

    @Property(str, notify=videoPathChanged)
    def videoPath(self):
        return self._video_path

    @videoPath.setter
    def videoPath(self, value):
        self._set_video_path(value)

    def _set_video_path(self, value: str, *, refresh_thumbnail: bool = False) -> None:
        path_changed = self._video_path != value
        if not path_changed and not refresh_thumbnail:
            return
        self._video_path = value
        thumbnail_path = (
            self._video_thumbnail_path(self._selected_video_id)
            if self._selected_video_id
            else self._draft_thumbnail_path()
        )
        self._video_thumbnail_source = self._create_video_thumbnail(value, thumbnail_path)
        self.videoPathChanged.emit()
        self.videoThumbnailChanged.emit()

    @Property(str, notify=videoThumbnailChanged)
    def videoThumbnailSource(self):
        return self._video_thumbnail_source

    @Property("QVariantList", notify=languageOptionsChanged)
    def targetLanguageOptions(self):
        return [
            {
                "code": code,
                "englishName": english_name,
                "nativeName": native_name,
                "label": self._language_label(code),
                "search": f"{code} {english_name} {native_name}".lower(),
            }
            for code, english_name, native_name in POPULAR_TARGET_LANGUAGES
        ]

    @Property(str, notify=targetLanguageChanged)
    def targetLanguage(self):
        return self._target_language

    @targetLanguage.setter
    def targetLanguage(self, value):
        language = str(value or "vi")
        language_changed = self._target_language != language
        normalized_voice = self._normalized_voice_for_language(language, self._tts_voice)
        voice_changed = self._tts_voice != normalized_voice
        if not language_changed and not voice_changed:
            return

        self._target_language = language
        self._tts_voice = normalized_voice
        if language_changed:
            self.targetLanguageChanged.emit()
            self.languageOptionsChanged.emit()
        if voice_changed:
            self.ttsVoiceChanged.emit()
        # The option model and selected index depend on both language and voice.
        self.ttsVoiceOptionsChanged.emit()

    @Property(str, notify=languageOptionsChanged)
    def targetLanguageLabel(self):
        return self._language_label(self._target_language)

    @Property(str, notify=ttsVoiceChanged)
    def ttsVoice(self):
        return self._tts_voice

    @ttsVoice.setter
    def ttsVoice(self, value):
        normalized_voice = self._normalized_voice_for_language(self._target_language, value)
        if self._tts_voice != normalized_voice:
            self._tts_voice = normalized_voice
            self.ttsVoiceChanged.emit()
            self.ttsVoiceOptionsChanged.emit()

    @Property("QVariantList", notify=ttsVoiceOptionsChanged)
    def ttsVoiceOptions(self):
        return self._voice_options_for_language(self._target_language)

    @Slot(str, result="QVariantList")
    def voiceOptionsForLanguage(self, language_code: str):
        return self._voice_options_for_language(str(language_code or "vi"))

    @Property(int, notify=ttsVoiceOptionsChanged)
    def ttsVoiceIndex(self):
        voices = self._voice_options_for_language(self._target_language)
        for index, item in enumerate(voices):
            if item["voice"] == self._tts_voice:
                return index
        return 0

    @Property(bool, notify=enableAudioSeparationChanged)
    def enableAudioSeparation(self):
        return self._enable_audio_separation

    @enableAudioSeparation.setter
    def enableAudioSeparation(self, value):
        if self._enable_audio_separation != value:
            self._enable_audio_separation = value
            self.enableAudioSeparationChanged.emit()

    @Property(int, notify=originalVolumeChanged)
    def originalVolume(self):
        return self._original_volume

    @originalVolume.setter
    def originalVolume(self, value):
        value = int(value)
        if self._original_volume != value:
            self._original_volume = value
            self.originalVolumeChanged.emit()

    @Property(str, notify=workflowModeChanged)
    def workflowMode(self): return self._workflow_mode

    @workflowMode.setter
    def workflowMode(self, value):
        value = "review" if value == "review" else "A"
        if self._workflow_mode != value:
            self._workflow_mode = value
            self.workflowModeChanged.emit()

    @Property(bool, notify=processingChanged)
    def isProcessing(self):
        return self._processing_queue.has_work or self._device_switching

    @Property(bool, notify=processingChanged)
    def isSelectedVideoProcessing(self):
        return bool(
            self._selected_video_id
            and self._selected_video_id == self._processing_queue.active_video_id
        )

    @Property(bool, notify=selectedVideoChanged)
    def isSelectedVideoQueued(self):
        return bool(self._selected_video_id and self._processing_queue.contains(self._selected_video_id))

    @Property(bool, notify=selectedVideoChanged)
    def canEditSelectedVideo(self):
        """Only freeze the video whose immutable pipeline snapshot is queued."""
        return not (
            self._selected_video_id
            and self._processing_queue.contains(self._selected_video_id)
        )

    @Property(str, notify=processingChanged)
    def processingText(self):
        active_video_id = self._processing_queue.active_video_id
        video = video_store.get_video(active_video_id) if active_video_id else None
        return f"{video.original_filename} | {video.step_detail or video.status}" if video else "No active video"

    def _refresh_selected_video_snapshot(self) -> None:
        self._selected_video_snapshot = (
            video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        )

    def _selected_video(self):
        if not self._selected_video_id:
            return None
        if (
            self._selected_video_snapshot is not None
            and self._selected_video_snapshot.video_id == self._selected_video_id
        ):
            return self._selected_video_snapshot
        self._refresh_selected_video_snapshot()
        return self._selected_video_snapshot

    @Property(str, notify=selectedVideoChanged)
    def selectedTitle(self):
        video = self._selected_video()
        return f"{video.original_filename} | {video.status}" if video else "No video selected"

    @Property(bool, notify=selectedVideoChanged)
    def hasSelectedVideo(self):
        return self._selected_video() is not None

    @Property(bool, notify=projectSetupChanged)
    def hasOpenProject(self):
        if not self._selected_project_key:
            return False
        try:
            return os.path.isdir(project_store.project_root_for_key(self._selected_project_key))
        except (RuntimeError, ValueError):
            return False

    @staticmethod
    def _video_project_key(video) -> str:
        key = str(getattr(video, "project_key", "") or "")
        if key:
            return key
        return project_store.resolve_project_key(
            str(getattr(video, "project_name", "") or ""),
            str(getattr(video, "project_directory", "") or ""),
            "batch" if getattr(video, "project_type", "single") == "batch" else "single",
        )

    def _selected_project_root(self) -> str:
        return project_store.project_root_for_key(self._selected_project_key)

    @Property(bool, notify=selectedVideoChanged)
    def isSelectedBatchVideo(self):
        video = self._selected_video()
        return bool(video and video.project_type == "batch" and video.video_id in self._batch_video_ids)

    @Property("QVariantList", notify=selectedVideoChanged)
    def reviewSegments(self):
        video = self._selected_video()
        if not video or video.status != "awaiting_review":
            return []
        try:
            with open(video.files["transcript_json"], "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return []

    @Property(str, notify=selectedVideoChanged)
    def selectedFileName(self):
        video = self._selected_video()
        return video.original_filename if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedStatus(self):
        video = self._selected_video()
        return video.status if video else "none"

    @Property(str, notify=selectedVideoChanged)
    def selectedStep(self):
        video = self._selected_video()
        return video.step_detail or video.step if video else "pending"

    @Property(int, notify=selectedVideoChanged)
    def selectedProgress(self):
        video = self._selected_video()
        return video.progress if video else 0

    @Property(str, notify=selectedVideoChanged)
    def selectedStageLabel(self):
        video = self._selected_video()
        if not video:
            return "Ready"
        labels = {
            "starting": "Preparing project",
            "extracting_audio": "Extracting audio",
            "separating_audio": "Separating vocals",
            "transcribing": "Transcribing speech",
            "translating": "Translating",
            "review_translation": "Waiting for translation review",
            "creating_subtitle": "Creating subtitles",
            "creating_voice": "Generating voice",
            "building_audio_timeline": "Mixing audio",
            "rendering": "Rendering video",
            "paused": "Paused",
            "done": "Export complete",
        }
        return labels.get(video.step, video.step_detail or video.status)

    @Property(str, notify=selectedVideoChanged)
    def selectedProgressDetail(self):
        video = self._selected_video()
        if not video:
            return ""
        item_detail = f"{video.current_item}/{video.total_items}" if video.total_items else ""
        return " | ".join(part for part in (video.step_detail, item_detail) if part)

    @Property(str, notify=selectedVideoChanged)
    def selectedElapsed(self):
        video = self._selected_video()
        if not video or not video.started_at:
            return ""
        try:
            started_at = datetime.fromisoformat(video.started_at.replace("Z", "+00:00"))
            if video.status == "processing":
                seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            else:
                finished_at = datetime.fromisoformat(video.updated_at.replace("Z", "+00:00"))
                seconds = (finished_at - started_at).total_seconds()
            return self._format_duration(max(0, seconds))
        except ValueError:
            return ""

    @Property(str, notify=selectedVideoChanged)
    def selectedUpdatedAt(self):
        video = self._selected_video()
        return video.updated_at if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedOutputFormat(self):
        video = self._selected_video()
        return video.output_format if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedTargetLanguageLabel(self):
        video = self._selected_video()
        return self._language_label(video.target_language) if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedTranslatorProvider(self):
        video = self._selected_video()
        return video.translator_provider if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedInputPath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))

    @Property(str, notify=selectedVideoChanged)
    def selectedOutputPath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))

    @Property(bool, notify=selectedVideoChanged)
    def hasSelectedOutput(self):
        video = self._selected_video()
        if not video or video.status != "done":
            return False
        output_path = self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))
        return bool(output_path and os.path.isfile(output_path) and os.path.getsize(output_path) > 0)

    @Property(str, notify=selectedVideoChanged)
    def selectedSrtPath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("srt_output", "subtitle_output"), ("temp", "vi.srt"))

    @Property(str, notify=selectedVideoChanged)
    def selectedVoicePath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("voice_output", "dubbed_audio"), ("temp", "voice_final.wav"))

    @Property(str, notify=selectedVideoChanged)
    def selectedLogsPath(self):
        return video_store.get_video_logs_path(self._selected_video_id) if self._selected_video_id else ""

    @Property(str, notify=logsChanged)
    def logs(self):
        return self._logs

    @Property(str, notify=statusMessageChanged)
    def statusMessage(self):
        return self._status_message

    @Property(QObject, constant=True)
    def urlImporter(self):
        return self._url_importer

    @Property(str, notify=previewChanged)
    def previewSource(self):
        return self._preview_source

    @Property(str, notify=previewChanged)
    def previewPosterSource(self):
        return self._preview_poster_source

    @Property(str, notify=settingsChanged)
    def settingsTheme(self):
        return self._settings_theme

    @Property(str, notify=settingsChanged)
    def settingsLanguage(self):
        return self._settings_language

    @Property(str, notify=settingsChanged)
    def processingDevice(self):
        return self._settings_processing_device

    @Property(bool, notify=settingsChanged)
    def cpuOnly(self):
        return runtime_profile().is_cpu_only

    @Property(str, notify=settingsChanged)
    def performanceProfileLabel(self):
        return runtime_profile().label

    @Property(str, notify=settingsChanged)
    def performanceProfileDetail(self):
        profile = runtime_profile()
        if self._settings_language == "vi":
            if profile.cuda_available:
                return f"Tăng tốc GPU - {profile.cuda_name or 'CUDA'}"
            ram = f"{profile.total_ram_gib:.0f} GB RAM" if profile.total_ram_bytes else "không rõ RAM"
            return f"Chế độ CPU - {ram}, {profile.cpu_threads} luồng"
        return profile.summary

    @Property("QVariantMap", notify=hardwareChanged)
    def hardwareInfo(self):
        """Expose the active graphics adapter and detailed CPU telemetry."""
        capabilities = self._hardware_capabilities
        profile = runtime_profile()
        active_gpu_name = capabilities.cuda_name if profile.cuda_available else capabilities.active_display_gpu_name
        return {
            "activeGpuName": active_gpu_name,
            "activeGpuRole": "GPU compute" if profile.cuda_available else "Windows display adapter",
            "activeGpuResolution": capabilities.active_display_gpu_resolution,
            "usingGpu": profile.cuda_available,
            "gpuSafe": capabilities.gpu_supported,
            "availableGpuName": capabilities.cuda_name if capabilities.gpu_supported else "",
            "totalVram": self._format_memory_size(capabilities.total_vram_bytes) if profile.cuda_available else "--",
            "freeVram": self._format_memory_size(capabilities.free_vram_bytes) if profile.cuda_available else "--",
            "systemRam": self._format_memory_size(capabilities.total_ram_bytes),
            "logicalCpuCount": capabilities.logical_cpu_count,
            "cpuName": capabilities.cpu_name or "CPU information loading...",
            "cpuPhysicalCores": capabilities.cpu_physical_cores or 0,
            "cpuMaxMhz": capabilities.cpu_max_mhz or 0,
            "acPowered": capabilities.ac_powered,
            "batteryPercent": capabilities.battery_percent if capabilities.battery_percent is not None else -1,
            "recommendedDevice": recommended_processing_device(capabilities),
            "profileLabel": profile.label,
        }

    @Slot(str, result=bool)
    def processingDeviceCompatible(self, preference):
        compatible, _message = validate_processing_device(str(preference), self._hardware_capabilities)
        return compatible

    @Slot(str, result=str)
    def processingDeviceStatus(self, preference):
        preference = str(preference)
        capabilities = self._hardware_capabilities
        compatible, message = validate_processing_device(preference, capabilities)
        if self._settings_language != "vi":
            return message
        if preference == "gpu":
            if not capabilities.cuda_available:
                return "Không phát hiện GPU NVIDIA tương thích CUDA."
            if capabilities.total_vram_bytes < 7 * 1024 ** 3:
                return f"GPU cần ít nhất 7 GB VRAM; hiện có {capabilities.total_vram_bytes / (1024 ** 3):.1f} GB."
            if capabilities.free_vram_bytes and capabilities.free_vram_bytes < 5 * 1024 ** 3:
                return f"GPU cần ít nhất 5 GB VRAM trống; hiện có {capabilities.free_vram_bytes / (1024 ** 3):.1f} GB trống."
            if capabilities.total_ram_bytes and capabilities.total_ram_bytes < 8 * 1024 ** 3:
                return f"GPU cần ít nhất 8 GB RAM hệ thống; hiện có {capabilities.total_ram_bytes / (1024 ** 3):.1f} GB."
            return f"GPU sẵn sàng: {capabilities.cuda_name}, {capabilities.total_vram_bytes / (1024 ** 3):.0f} GB VRAM."
        if preference == "cpu":
            if not compatible:
                return f"Chế độ CPU cần khoảng 6 GB RAM; hiện có {capabilities.total_ram_bytes / (1024 ** 3):.1f} GB."
            return f"CPU sẵn sàng: {capabilities.total_ram_bytes / (1024 ** 3):.0f} GB RAM, {capabilities.logical_cpu_count} luồng logic."
        if capabilities.gpu_supported:
            return f"Chế độ tự động sẽ dùng {capabilities.cuda_name}."
        if capabilities.cpu_supported:
            return "Chế độ tự động sẽ dùng CPU vì GPU hiện không đủ an toàn."
        return "Máy không đáp ứng yêu cầu bộ nhớ tối thiểu của CPU hoặc GPU."

    @Property(str, notify=projectSetupChanged)
    def projectDirectory(self):
        return self._project_directory

    @Property(str, notify=projectSetupChanged)
    def projectName(self):
        return self._project_name

    @Property(str, notify=projectSetupChanged)
    def projectType(self):
        return self._project_type

    @Property(str, notify=previewChanged)
    def previewTitle(self):
        return self._preview_title

    @Property(bool, notify=previewChanged)
    def previewInteractive(self):
        return self._preview_interactive

    @Property(float, notify=previewChanged)
    def previewAspectRatio(self):
        return self._preview_aspect_ratio

    @Property(int, notify=previewChanged)
    def subtitleX(self):
        return self._subtitle_position_x

    @Property(int, notify=previewChanged)
    def subtitleY(self):
        return self._subtitle_position_y

    @Property(int, notify=previewChanged)
    def subtitleBoxWidth(self):
        return self._subtitle_box_width

    @Property(int, notify=previewChanged)
    def subtitleBoxHeight(self):
        return self._subtitle_box_height

    @Property(int, notify=previewChanged)
    def subtitleFontSize(self):
        return self._caption_font_size

    @Property(str, notify=previewChanged)
    def previewSaveLabel(self):
        return "Apply to this size" if self._preview_edit_scope == "size_group" else "Save subtitle frame"

    @Slot()
    def downloadInspectedVideo(self):
        HaizFlowController._project_import_for(self).download_inspected_video()

    def _handle_url_download_ready(self, path, _workspace, mode):
        HaizFlowController._project_import_for(self).handle_url_download_ready(path, _workspace, mode)

    def _import_downloaded_video(self, path: str, mode: str, target) -> bool:
        return HaizFlowController._project_import_for(self).import_downloaded_video(path, mode, target)

    def _current_project_media_keys(self) -> set[str]:
        return HaizFlowController._project_import_for(self).current_project_media_keys()

    @Slot(result=bool)
    def prepareChannelImport(self):
        return HaizFlowController._project_import_for(self).prepare_channel_import()

    @Slot(result=bool)
    def startChannelDownloads(self):
        return HaizFlowController._project_import_for(self).start_channel_downloads()

    def _remember_channel_import_target(self, session_id: str) -> None:
        HaizFlowController._project_import_for(self).remember_channel_import_target(session_id)

    @Slot(int, result=bool)
    def retryChannelVideo(self, row):
        return HaizFlowController._project_import_for(self).retry_channel_video(row)

    def _handle_channel_video_ready(self, path, _workspace, candidate_payload, project_key, session_id):
        HaizFlowController._project_import_for(self).handle_channel_video_ready(path, _workspace, candidate_payload, project_key, session_id)

    @Slot(str)
    def _finish_channel_import_target(self, session_id):
        HaizFlowController._project_import_for(self).finish_channel_import_target(session_id)

    @Slot()
    def browseVideo(self):
        HaizFlowController._project_import_for(self).browse_video()

    @Slot(str, result=bool)
    def replaceSelectedVideoVideo(self, path):
        return HaizFlowController._project_import_for(self).replace_video(self._selected_video_id, path)

    def _replace_video_video(self, video_id, path, media_source=None):
        return HaizFlowController._project_import_for(self).replace_video(video_id, path, media_source)

    @Slot()
    def browseProjectDirectory(self):
        HaizFlowController._project_import_for(self).browse_project_directory()

    @Slot(str, str, str, result=bool)
    def prepareProject(self, project_name, project_directory, project_type):
        return HaizFlowController._project_import_for(self).prepare_project(project_name, project_directory, project_type)

    @Slot(str, str, str, result=bool)
    def applySettings(self, theme, language, processing_device):
        return HaizFlowController._settings_delegate_for(self).apply(theme, language, processing_device)

    @staticmethod
    def _settings_delegate_for(host):
        return getattr(host, "_settings_controller", None) or SettingsController(host)

    @Slot()
    def resetSettings(self):
        HaizFlowController._settings_delegate_for(self).reset()

    @Slot(str, result=bool)
    def importVideo(self, path):
        return HaizFlowController._project_import_for(self).import_video(path)

    @Slot()
    def browseBatchVideos(self):
        HaizFlowController._project_import_for(self).browse_batch_videos()

    @Slot()
    def browseBatchFolder(self):
        HaizFlowController._project_import_for(self).browse_batch_folder()

    @Slot("QVariantList")
    def importBatchVideos(self, paths):
        HaizFlowController._project_import_for(self).import_batch_videos(paths)

    def _batch_rejection_message(self, rejected) -> str:
        return HaizFlowController._project_import_for(self).batch_rejection_message(rejected)

    @staticmethod
    def _project_commands_for(host):
        return getattr(host, "_project_commands", None) or ProjectCommandsController(
            host, create_video=create_desktop_video
        )

    @staticmethod
    def _project_import_for(host):
        return getattr(host, "_project_import", None) or ProjectImportController(
            host, create_video=create_desktop_video
        )

    @staticmethod
    def _catalog_media_for(host):
        return getattr(host, "_catalog_media", None) or CatalogMediaController(host)

    @staticmethod
    def _runtime_device_for(host):
        return getattr(host, "_runtime_device", None) or RuntimeDeviceController(
            host,
            unsubscribe=unsubscribe_log,
            pause=pause_video,
            shutdown_translation=shutdown_hymt2_worker,
            detect_hardware=detect_hardware_capabilities,
        )

    @Slot()
    def startBatch(self):
        HaizFlowController._project_commands_for(self).start_batch()

    def _batch_settings_values(self) -> dict[str, object]:
        return HaizFlowController._project_commands_for(self).batch_settings_values()

    @Slot(result="QVariantMap")
    def batchSettings(self):
        """Return a batch draft without mutating shared editor state."""
        return self._batch_settings_values()

    def _apply_batch_settings(
        self,
        workflow_mode: str,
        target_language: str,
        tts_voice: str,
        enable_audio_separation: bool,
        original_volume: int,
    ) -> bool:
        return HaizFlowController._project_commands_for(self).apply_batch_settings(
            workflow_mode, target_language, tts_voice, enable_audio_separation, original_volume
        )

    @Slot(result=bool)
    def applyBatchSettings(self):
        return self._apply_batch_settings(
            self._workflow_mode,
            self._target_language,
            self._tts_voice,
            self._enable_audio_separation,
            self._original_volume,
        )

    @Slot(str, str, str, bool, int, result=bool)
    def applyBatchSettingsDraft(
        self,
        workflow_mode: str,
        target_language: str,
        tts_voice: str,
        enable_audio_separation: bool,
        original_volume: int,
    ):
        return self._apply_batch_settings(
            workflow_mode,
            target_language,
            tts_voice,
            enable_audio_separation,
            original_volume,
        )

    @Slot()
    def loadBatchSettings(self):
        HaizFlowController._project_commands_for(self).load_batch_settings()

    @Slot(result=bool)
    def saveSelectedVideoSettings(self):
        return HaizFlowController._project_commands_for(self).save_selected_video_settings()

    @Slot()
    def stopBatch(self):
        HaizFlowController._project_commands_for(self).stop_batch()

    @Slot()
    def clearBatch(self):
        HaizFlowController._project_commands_for(self).clear_batch()

    @staticmethod
    def _batch_output_directory(video):
        """Return only the app-owned per-video output directory, if it is safe to remove."""
        project_directory = (video.project_directory or "").strip()
        output_path = (video.files or {}).get("final_video", "")
        if not project_directory or not output_path:
            return ""
        project_root = (
            project_store.project_root_for_key(video.project_key)
            if getattr(video, "project_key", "")
            else project_store.project_root(video.project_name, project_directory, video.project_type)
        )
        export_roots = (
            os.path.abspath(
                project_store.project_exports_dir_for_key(video.project_key)
                if getattr(video, "project_key", "")
                else project_store.project_exports_dir(video.project_name, project_directory, video.project_type)
            ),
            os.path.abspath(os.path.join(project_root, "outputs")),
        )
        output_directory = os.path.abspath(os.path.dirname(output_path))
        try:
            if not any(os.path.commonpath([exports_root, output_directory]) == exports_root for exports_root in export_roots):
                return ""
        except ValueError:
            return ""
        return output_directory

    @staticmethod
    def _remove_empty_batch_output_parents(video):
        output_directory = HaizFlowController._batch_output_directory(video)
        if not output_directory:
            return
        outputs_root = os.path.dirname(output_directory)
        project_root = os.path.dirname(outputs_root)
        for directory in (outputs_root, project_root):
            try:
                os.rmdir(directory)
            except OSError:
                # Keep non-empty folders and any folder currently in use.
                pass

    @Slot()
    def deleteCurrentBatch(self):
        HaizFlowController._project_commands_for(self).delete_current_batch()

    @Slot()
    def startVideo(self):
        HaizFlowController._project_commands_for(self).start_video()

    @Slot(result=bool)
    def startProjectVideo(self):
        return HaizFlowController._project_commands_for(self).start_project_video()

    @Slot()
    def stopVideo(self):
        HaizFlowController._project_commands_for(self).stop_video()

    @Slot()
    def resumeSelectedVideo(self):
        HaizFlowController._project_commands_for(self).resume_selected_video()

    @Slot()
    def restartSelectedVideo(self):
        HaizFlowController._project_commands_for(self).restart_selected_video()

    @Slot(str)
    def approveTranslationReview(self, payload):
        HaizFlowController._project_commands_for(self).approve_translation_review(payload)

    @Slot(int)
    def selectVideo(self, row: int):
        video = self.videos.video_at(row)
        if not video:
            return
        self._select_video(video)

    def _select_video(self, video):
        HaizFlowController._project_workspace_for(self).select_video(video)

    @Slot(int)
    def selectBatchVideo(self, row: int):
        video = self.batch_videos.video_at(row)
        if not video:
            return
        self._select_video(video)

    @Slot(int)
    def selectProject(self, row: int):
        project = self.projects.project_at(row)
        if not project:
            return
        self._open_project_summary(project)

    @Slot(int, str)
    def selectProjectInMode(self, row: int, project_type: str):
        model = self.batch_projects if project_type == "batch" else self.single_projects
        project = model.project_at(row)
        if not project:
            return
        self._open_project_summary(project)

    def _open_project_summary(self, project):
        HaizFlowController._project_workspace_for(self).open_project_summary(project)

    @staticmethod
    def _project_workspace_for(host):
        return getattr(host, "_project_workspace", None) or ProjectWorkspaceController(host)

    @Slot()
    def deleteSelectedVideo(self):
        HaizFlowController._project_commands_for(self).delete_selected_video()

    @Slot()
    def openProjectFolder(self):
        if not self.hasOpenProject:
            QMessageBox.information(None, "Project folder", "This project's folder is not available yet.")
            return
        self._open_path(
            self._selected_project_root()
        )

    @Slot()
    def deleteCurrentProject(self):
        HaizFlowController._project_commands_for(self).delete_current_project()

    @Slot()
    def refreshVideos(self):
        HaizFlowController._project_workspace_for(self).refresh_videos()

    def _apply_video_metadata_changes(self, video_ids: set[str]) -> bool:
        return HaizFlowController._project_workspace_for(self).apply_video_metadata_changes(video_ids)

    @staticmethod
    def _thumbnail_retry_signature(source_path: str) -> str:
        return CatalogMediaController.thumbnail_retry_signature(source_path)

    def _missing_thumbnail_ids(self, videos) -> list[str]:
        return HaizFlowController._catalog_media_for(self).missing_thumbnail_ids(videos)

    def _record_thumbnail_failure(self, video_id: str, signature: str) -> None:
        HaizFlowController._catalog_media_for(self).record_thumbnail_failure(video_id, signature)

    def _clear_thumbnail_failure(self, video_id: str) -> None:
        HaizFlowController._catalog_media_for(self).clear_thumbnail_failure(video_id)

    def _create_missing_thumbnails(self, video_ids):
        HaizFlowController._catalog_media_for(self).create_missing_thumbnails(video_ids)

    @Slot()
    def openInputPreview(self):
        selected_video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        video_path = self._resolve_video_file(selected_video, ("video_input", "input_video"), ("input", "video.mp4")) if selected_video else self._video_path.strip()
        if not video_path or not os.path.exists(video_path):
            QMessageBox.information(None, "Input preview", "Choose an input video before opening the preview editor.")
            return
        self._preview_edit_scope = "single_video" if selected_video else "draft"
        self._preview_target_video_ids = [selected_video.video_id] if selected_video else []
        self._preview_group_keys = []
        self._preview_group_index = -1
        self._preview_original_style = self._copy_subtitle_style(selected_video.subtitle_style) if selected_video else self._current_subtitle_style()
        self._open_preview(video_path, "Input Preview Editor", True)

    @Slot(result=bool)
    def openBatchSubtitleEditor(self):
        groups = self._batch_dimension_groups()
        if not groups:
            QMessageBox.information(None, "Subtitle presets", "Add at least one video before editing subtitles.")
            return False
        self._preview_group_keys = [group["size_key"] for group in groups]
        self._preview_group_index = 0
        self._open_batch_group_preview(self._preview_group_keys[0])
        return True

    @Slot(str, result=bool)
    def openBatchSizeEditor(self, size_key):
        group = self._batch_dimension_group(size_key)
        if not group:
            return False
        self._preview_group_keys = [size_key]
        self._preview_group_index = 0
        self._open_batch_group_preview(size_key)
        return True

    @Slot()
    def openInputFile(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        input_path = self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
        if not input_path or not os.path.exists(input_path):
            QMessageBox.information(None, "Open input video", "Input video is not available yet.")
            return
        self._open_path(input_path)

    @Slot()
    def openOutputFile(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video or video.status != "done":
            QMessageBox.information(None, "Open output", "Final video is not available yet.")
            return
        output_path = self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))
        if not output_path or not os.path.exists(output_path):
            QMessageBox.information(None, "Open output", "Final video is not available yet.")
            return
        self._open_path(output_path)

    @Slot()
    def openOutputFolder(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if video and migrate_legacy_single_export(video):
            video = video_store.get_video(video.video_id) or video
        output_path = self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))
        folder = os.path.dirname(output_path) if output_path else ""
        fallback_folder = os.path.join(video_store.get_video_dir(video.video_id), "output") if video else ""
        if folder and os.path.isdir(folder):
            self._open_path(folder)
            return
        if fallback_folder and os.path.isdir(fallback_folder):
            self._open_path(fallback_folder)
            return
        if self.hasOpenProject:
            export_folder = project_store.project_exports_dir_for_key(self._selected_project_key)
            os.makedirs(export_folder, exist_ok=True)
            self._open_path(export_folder)
            return
        QMessageBox.information(None, "Open export folder", "The export folder is not available yet.")

    @Slot(int, int, int, int, int)
    def updatePreviewEdits(self, subtitle_x, subtitle_y, box_width, box_height, font_size):
        self._apply_preview_edits(subtitle_x, subtitle_y, box_width, box_height, font_size)
        self.previewChanged.emit()

    @Slot(result=bool)
    def commitPreviewEdits(self):
        style = self._current_subtitle_style(self._preview_original_style)
        if self._preview_edit_scope == "size_group":
            target_ids = [video_id for video_id in self._preview_target_video_ids if video_store.get_video(video_id)]
            if not target_ids:
                self._clear_preview_edit_session()
                return False
            for video_id in target_ids:
                video_store.update_video(video_id, subtitle_style=style, subtitle_override=False)
            self._refresh_batch_model()
            self.batchChanged.emit()
            next_index = self._preview_group_index + 1
            if next_index < len(self._preview_group_keys):
                self._preview_group_index = next_index
                self._open_batch_group_preview(self._preview_group_keys[next_index])
                return False
        elif self._preview_edit_scope == "single_video" and self._preview_target_video_ids:
            video_id = self._preview_target_video_ids[0]
            video = video_store.get_video(video_id)
            if video:
                video_store.update_video(
                    video_id,
                    subtitle_style=style,
                    subtitle_override=video.project_type == "batch",
                )
                video_store.log_to_video(video_id, "Custom subtitle frame saved for this video.")
                self.refreshVideos()
                self.selectedVideoChanged.emit()
                self.batchChanged.emit()
            else:
                self._clear_preview_edit_session()
                return False
        elif self._preview_edit_scope != "draft" or self._preview_original_style is None:
            # A terminal save clears the target.  Never acknowledge a later save that
            # has nowhere to persist its subtitle style.
            return False
        self._clear_preview_edit_session()
        return True

    @Slot()
    def cancelPreviewEdits(self):
        if self._preview_original_style:
            self._set_preview_style(self._preview_original_style)
        self._clear_preview_edit_session()
        self.previewChanged.emit()

    @Slot()
    def openVideoFolder(self):
        if self._selected_video_id:
            self._open_path(video_store.get_video_dir(self._selected_video_id))

    def poll_videos(self):
        revision = video_store.metadata_revision()
        if revision == self._last_video_metadata_revision:
            return
        if not hasattr(self, "_apply_video_metadata_changes"):
            self.refreshVideos()
            self._last_video_metadata_revision = revision
            self.batchChanged.emit()
            return
        changes = video_store.metadata_changes_since(self._last_video_metadata_revision)
        if changes is None:
            self.refreshVideos()
        else:
            revision, video_ids = changes
            if not self._apply_video_metadata_changes(video_ids):
                self.refreshVideos()
            else:
                self._last_video_metadata_revision = revision
        self.batchChanged.emit()

    def _build_config(self):
        return VideoConfig(
            mode=self._workflow_mode,
            source_language="auto",
            target_language=self._target_language,
            translator_provider="hymt2",
            tts_voice=self._tts_voice,
            subtitle_style=SubtitleStyle(
                font_size=self._caption_font_size,
                margin_bottom=40,
                outline=2,
                max_chars_per_line=32,
                position_x_percent=self._subtitle_position_x,
                position_y_percent=self._subtitle_position_y,
                box_width_percent=self._subtitle_box_width,
                box_height_percent=self._subtitle_box_height,
            ),
            output_format="keep_ratio",
            crop=CropSettings(),
            enable_audio_separation=self._enable_audio_separation,
            original_video_volume=self._original_volume,
            project_name=self._project_name,
            project_directory=self._project_directory,
            project_type=self._project_type,
            project_key=self._selected_project_key,
            project_id=str((project_store.get_project(self._selected_project_key) or {}).get("project_id") or ""),
        )

    def _apply_setup_to_video(self, video, review_approved=None):
        config = self._build_config()
        changes = {
            "mode": config.mode,
            "source_language": config.source_language,
            "target_language": config.target_language,
            "tts_voice": config.tts_voice,
            "subtitle_style": config.subtitle_style,
            "output_format": config.output_format,
            "crop": config.crop,
            "enable_audio_separation": config.enable_audio_separation,
            "original_video_volume": config.original_video_volume,
            "project_type": config.project_type,
        }
        if review_approved is not None:
            changes["review_approved"] = review_approved
        video_store.update_video(video.video_id, **changes)

    @staticmethod
    def _processing_delegate_for(host):
        return getattr(host, "_processing_lifecycle", None) or ProcessingLifecycleController(host)

    def _enqueue_video(self, video_id: str) -> bool:
        return HaizFlowController._processing_delegate_for(self).enqueue_video(video_id)

    def _enqueue_videos(self, video_ids) -> int:
        return HaizFlowController._processing_delegate_for(self).enqueue_videos(video_ids)

    def _update_queue_positions(self) -> None:
        HaizFlowController._processing_delegate_for(self).update_queue_positions()

    def _on_queue_video_started(self, video_id: str) -> None:
        HaizFlowController._processing_delegate_for(self).on_queue_video_started(video_id)

    def _on_queue_video_finished(self, video_id: str) -> None:
        HaizFlowController._processing_delegate_for(self).on_queue_video_finished(video_id)

    def _on_processing_queue_idle(self) -> None:
        HaizFlowController._processing_delegate_for(self).on_processing_queue_idle()

    def _on_processing_queue_error(self, video_id: str, exc: Exception) -> None:
        HaizFlowController._processing_delegate_for(self).on_processing_queue_error(video_id, exc)

    def _execute_pipeline(self, video_id):
        HaizFlowController._processing_delegate_for(self).execute_pipeline(video_id)

    def _prepare_batch_models(self, video_id):
        HaizFlowController._processing_delegate_for(self).prepare_batch_models(video_id)

    def _on_video_log(self, video_id, line):
        HaizFlowController._processing_delegate_for(self).on_video_log(video_id, line)

    def _drain_log_queue(self):
        HaizFlowController._processing_delegate_for(self).drain_log_queue()

    def _read_video_logs(self, video_id):
        return HaizFlowController._processing_delegate_for(self).read_video_logs(video_id)

    def _replace_logs(self, text: str) -> None:
        HaizFlowController._processing_delegate_for(self).replace_logs(text)

    def _clear_logs(self) -> None:
        HaizFlowController._processing_delegate_for(self).clear_logs()

    def _append_logs(self, lines) -> bool:
        return HaizFlowController._processing_delegate_for(self).append_logs(lines)

    def _refresh_batch_model(self):
        HaizFlowController._catalog_media_for(self).refresh_batch_model()

    def _ensure_video_dimensions(self, video):
        return HaizFlowController._catalog_media_for(self).ensure_video_dimensions(video)

    def _on_video_dimensions_ready(self, video_id: str, width: int, height: int) -> None:
        HaizFlowController._catalog_media_for(self).on_video_dimensions_ready(video_id, width, height)

    def _batch_dimension_groups(self):
        return HaizFlowController._catalog_media_for(self).batch_dimension_groups()

    def _batch_dimension_group(self, size_key):
        return HaizFlowController._catalog_media_for(self).batch_dimension_group(size_key)

    _build_project_summaries = staticmethod(build_project_summaries)
    _normalize_video_path = staticmethod(normalize_video_path)
    _collect_batch_video_paths = staticmethod(collect_batch_video_paths)
    _resolve_video_file = staticmethod(resolve_video_file)

    def _language_label(self, code):
        return language_label(code, self._settings_language)

    _format_duration = staticmethod(format_duration)
    _format_memory_size = staticmethod(format_memory_size)

    def _voice_options_for_language(self, language_code):
        return voice_options_for_language(language_code, self._settings_language)

    def _voice_codes_for_language(self, language_code):
        return [item["voice"] for item in self._voice_options_for_language(language_code)]

    def _normalized_voice_for_language(self, language_code, voice):
        """Return a valid Edge voice for the selected output language."""
        options = self._voice_options_for_language(language_code)
        supported_voices = [item["voice"] for item in options]
        if voice in supported_voices:
            return voice
        return supported_voices[0] if supported_voices else ""

    def _load_video_preview(self, video):
        self._preview_media.load_video_preview(video)

    def _copy_subtitle_style(self, style):
        return self._preview_media.copy_subtitle_style(style)

    def _current_subtitle_style(self, base=None):
        return self._preview_media.current_subtitle_style(base)

    def _set_preview_style(self, style):
        self._preview_media.set_preview_style(style)

    def _open_batch_group_preview(self, size_key):
        self._preview_media.open_batch_group_preview(size_key)

    def _clear_preview_edit_session(self):
        self._preview_media.clear_preview_edit_session()

    def _apply_preview_edits(self, subtitle_x, subtitle_y, box_width, box_height, font_size):
        self._preview_media.apply_preview_edits(subtitle_x, subtitle_y, box_width, box_height, font_size)

    def _open_preview(self, path: str, title: str, interactive: bool):
        self._preview_media.open_preview(path, title, interactive)

    def _draft_thumbnail_path(self) -> str:
        return self._preview_media.draft_thumbnail_path()

    @staticmethod
    def _video_thumbnail_path(video_id: str) -> str:
        return os.path.join(video_store.get_video_dir(video_id), "thumbnail.jpg")

    def _assign_project_thumbnail(self, video) -> None:
        self._preview_media.assign_project_thumbnail(video)

    @staticmethod
    def _create_video_thumbnail(path: str, output_path: str = "") -> str:
        output_path = HaizFlowController._create_video_thumbnail_path(path, output_path)
        return thumbnail_source(output_path)

    _create_video_thumbnail_path = staticmethod(create_video_thumbnail_path)

    def _migrate_legacy_project_thumbnails(self) -> None:
        self._preview_media.migrate_legacy_project_thumbnails()

    _open_path = staticmethod(open_path)
