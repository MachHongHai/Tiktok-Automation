import os
import json
import shutil
import queue
import threading
from collections import Counter
from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtQml import QmlNamedElement, QmlSingleton

from haizflow.desktop.catalog import POPULAR_TARGET_LANGUAGES
from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.desktop.localization import QFileDialog, QMessageBox, _set_ui_language, _ui_text
from haizflow.desktop.media import (
    collect_batch_video_paths,
    create_video_thumbnail_path,
    normalize_video_path,
    open_path,
    resolve_video_file,
    thumbnail_source,
)
from haizflow.desktop.models import VideoListModel, ProjectListModel, TaskListModel
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
from haizflow.pipeline.process_registry import cancel_video, pause_video
from haizflow.schemas.video import CropSettings, VideoConfig, SubtitleStyle
from haizflow.services import desktop_settings, video_store, project_store
from haizflow.services.channel_import import normalize_remote_url
from haizflow.services.desktop_videos import create_desktop_video, migrate_legacy_single_export
from haizflow.services.processing_queue import SerialProcessingQueue
from haizflow.services.translation import shutdown_hymt2_worker, warm_hymt2_worker
from haizflow.utils.ffmpeg import get_video_dimensions

QML_IMPORT_NAME = "HaizFlow"
QML_IMPORT_MAJOR_VERSION = 1


@QmlNamedElement("AppController")
@QmlSingleton
class HaizFlowController(QObject):
    _qml_instance = None

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

    def __init__(self):
        super().__init__()
        type(self)._qml_instance = self
        self.videos = VideoListModel()
        self.projects = ProjectListModel()
        self.single_projects = ProjectListModel()
        self.batch_projects = ProjectListModel()
        self.batch_videos = VideoListModel()
        self.tasks = TaskListModel()
        self._video_path = ""
        self._video_thumbnail_source = ""
        self._target_language = "vi"
        self._tts_voice = "vi-VN-HoaiMyNeural"
        self._enable_audio_separation = False
        self._original_volume = 60
        self._workflow_mode = "A"
        self._selected_video_id = None
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
        self._processing_queue = SerialProcessingQueue(
            self._execute_pipeline,
            on_started=self._on_queue_video_started,
            on_finished=self._on_queue_video_finished,
            on_idle=self._on_processing_queue_idle,
            on_error=self._on_processing_queue_error,
        )
        self._batch_video_ids = []
        self._batch_running = False
        self._batch_stop_requested = False
        self._logs = ""
        self._status_message = "Ready"
        self._subtitle_position_x = 50
        self._subtitle_position_y = 88
        self._caption_font_size = 72
        self._subtitle_box_width = 72
        self._subtitle_box_height = 12
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
        settings = desktop_settings.load_settings()
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        self._settings_processing_device = settings["processing_device"]
        self._processing_device_origin = settings["processing_device_origin"]
        _set_ui_language(self._settings_language)
        # Re-check power and free VRAM at every launch before any model warm-up.
        clear_runtime_profile_cache()
        capabilities = detect_hardware_capabilities()
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
        self._thumbnail_refresh_running = False
        self._url_importer = VideoUrlImportCoordinator(self)
        self._url_import_target = None
        self._url_importer.downloadReady.connect(self._handle_url_download_ready)
        self._url_importer.importFinished.connect(self.urlImportFinished.emit)
        self._channel_importer = ChannelImportCoordinator(self)
        self._channel_importer.set_worker_limit_provider(
            lambda: 1 if self._processing_queue.active_video_id else 2
        )
        self._channel_import_targets = {}
        self._channel_importer.videoReady.connect(self._handle_channel_video_ready)
        self._channel_importer.downloadsFinished.connect(self._finish_channel_import_target)

        migrated_video_data = video_store.migrate_legacy_project_data()
        if migrated_video_data:
            self._status_message = f"Organized {len(migrated_video_data)} video workspace(s) into their projects."
        recovered_videos = video_store.recover_interrupted_videos()
        if recovered_videos:
            self._status_message = (
                f"Recovered {len(recovered_videos)} interrupted video(s). "
                "They are paused and ready to resume."
            )
        self._migrate_legacy_project_thumbnails()

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
        self._log_timer.start(250)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.poll_videos)
        self._status_timer.start(1000)

        self._hardware_timer = QTimer(self)
        self._hardware_timer.timeout.connect(self._refresh_live_hardware)
        self._hardware_timer.start(3000)

        self.refreshVideos()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and not self._close_confirmed:
            if not self._confirm_application_close():
                event.ignore()
                return True
        return super().eventFilter(watched, event)

    def _confirm_application_close(self) -> bool:
        background_work = (
            self._processing_queue.has_work
            or self._url_importer.busy
            or self._channel_importer.busy
        )
        if not background_work:
            self._close_confirmed = True
            return True
        answer = QMessageBox.question(
            None,
            "Exit HaizFlow",
            "HaizFlow is still processing or downloading media.\n\n"
            "Exit now? The active video will be paused, active downloads will be cancelled, "
            "and queued videos will remain available for later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        self._close_confirmed = answer == QMessageBox.StandardButton.Yes
        return self._close_confirmed

    def shutdown(self):
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._initial_model_warmup_done.set()
        unsubscribe_log(self._on_video_log)

        active_video_id = self._processing_queue.active_video_id
        active_video = video_store.get_video(active_video_id) if active_video_id else None
        if active_video and active_video.status in {"pending", "processing"}:
            resume_step = active_video.resume_step or active_video.step or "processing"
            if resume_step in {"pending", "queued", "paused"}:
                resume_step = "starting"
            pause_video(active_video_id)
            video_store.update_video(
                active_video_id,
                status="paused",
                error=None,
                step="paused",
                resume_step=resume_step,
                step_detail=f"Paused during application exit ({resume_step})",
                estimated_remaining_seconds=None,
            )
            video_store.log_to_video(
                active_video_id,
                "Application exit requested. Active subprocesses were stopped and the video was paused.",
            )

        for video_id in self._processing_queue.pending_ids():
            queued_video = video_store.get_video(video_id)
            if queued_video and queued_video.status == "pending":
                video_store.update_video(
                    video_id,
                    step="queued",
                    step_detail="Waiting to be started after the application exited",
                )

        self._url_importer.shutdown()
        self._channel_importer.shutdown()
        queue_stopped = self._processing_queue.shutdown(timeout_seconds=10.0)
        shutdown_hymt2_worker()
        if not queue_stopped:
            queue_stopped = self._processing_queue.shutdown(timeout_seconds=2.0)

        warmup_thread = self._warmup_thread
        if warmup_thread and warmup_thread.is_alive():
            warmup_thread.join(timeout=1.0)
        if queue_stopped and not (warmup_thread and warmup_thread.is_alive()):
            from haizflow.pipeline.transcribe import release_warm_whisperx_model

            release_warm_whisperx_model()
        if HaizFlowController._qml_instance is self:
            HaizFlowController._qml_instance = None

    def _warm_models(self):
        with self._model_runtime_lock:
            self._warm_models_unlocked()

    def _warm_models_at_startup(self):
        try:
            requested_device = processing_device_preference()
            probe = probe_runtime(requested_device)
            if not probe.ok and requested_device == "gpu":
                cpu_probe = probe_runtime("cpu")
                if cpu_probe.ok:
                    configure_processing_device("cpu")
                    self._active_processing_device = "cpu"
                    self._settings_processing_device = "cpu"
                    self._processing_device_origin = "detected"
                    try:
                        desktop_settings.save_settings(
                            {
                                "theme": self._settings_theme,
                                "language": self._settings_language,
                                "processing_device": "cpu",
                                "processing_device_origin": "detected",
                            }
                        )
                    except OSError:
                        pass
                    self._status_message = f"GPU runtime unavailable; using CPU. {probe.message}"
                    self.settingsChanged.emit()
                    self.hardwareChanged.emit()
                else:
                    self._runtime_probe_error = (
                        f"GPU runtime: {probe.message} CPU runtime: {cpu_probe.message}"
                    )
            elif not probe.ok:
                self._runtime_probe_error = probe.message
            if self._runtime_probe_error:
                self._status_message = f"Model runtime unavailable: {self._runtime_probe_error}"
                self.statusMessageChanged.emit()
                return
            self._warm_models()
        finally:
            self._initial_model_warmup_done.set()

    def _warm_models_unlocked(self):
        profile = runtime_profile()
        try:
            warmed = []
            if profile.warm_hymt2_on_startup:
                warm_hymt2_worker(self._set_warmup_status)
                warmed.append("HY-MT2")
            if profile.warm_whisper_on_startup:
                from haizflow.pipeline.transcribe import warm_whisperx_model

                warm_whisperx_model()
                warmed.append("WhisperX")
            self._status_message = (
                f"{', '.join(warmed)} ready - {profile.summary}"
                if warmed
                else f"Ready - {profile.summary}"
            )
        except Exception as exc:
            self._status_message = f"Model warm-up unavailable: {exc}"
        self.statusMessageChanged.emit()

    def _switch_processing_device(self, preference: str):
        self._device_switching = True
        self._status_message = "Switching processing device"
        self.processingChanged.emit()
        self.statusMessageChanged.emit()

        def switch_models():
            try:
                from haizflow.pipeline.transcribe import release_warm_whisperx_model

                probe = probe_runtime(preference)
                if not probe.ok:
                    active_device = self._active_processing_device
                    self._settings_processing_device = active_device
                    self._pending_processing_device = ""
                    try:
                        desktop_settings.save_settings(
                            {
                                "theme": self._settings_theme,
                                "language": self._settings_language,
                                "processing_device": active_device,
                                "processing_device_origin": self._processing_device_origin,
                            }
                        )
                    except OSError:
                        pass
                    self._status_message = f"Cannot switch to {preference.upper()}: {probe.message}"
                    self.settingsChanged.emit()
                    self.statusMessageChanged.emit()
                    return
                with self._model_runtime_lock:
                    shutdown_hymt2_worker()
                    release_warm_whisperx_model()
                    configure_processing_device(preference)
                    self._active_processing_device = preference
                    self._runtime_probe_error = ""
                    if self._pending_processing_device == preference:
                        self._pending_processing_device = ""
                    self._warm_models_unlocked()
                self.settingsChanged.emit()
                self.hardwareChanged.emit()
            except Exception as exc:
                self._status_message = f"Processing device switch failed: {exc}"
                self.statusMessageChanged.emit()
            finally:
                self._device_switching = False
                self.processingChanged.emit()

        threading.Thread(target=switch_models, name="processing-device-switch", daemon=True).start()

    def _pipeline_is_active(self) -> bool:
        """Return whether a video is currently inside the serial worker."""
        return bool(self._processing_queue.active_video_id)

    def _activate_pending_device_for_next_video(self, video_id: str) -> None:
        """Switch only between two queued videos, never during a pipeline."""
        preference = self._pending_processing_device
        if preference not in {"cpu", "gpu"}:
            return

        if preference == processing_device_preference():
            self._pending_processing_device = ""
            return

        compatible, message = validate_processing_device(preference)
        if not compatible:
            preference = "cpu"
            self._settings_processing_device = "cpu"
            self._processing_device_origin = "detected"
            try:
                desktop_settings.save_settings(
                    {
                        "theme": self._settings_theme,
                        "language": self._settings_language,
                        "processing_device": "cpu",
                        "processing_device_origin": "detected",
                    }
                )
            except OSError:
                pass
            video_store.log_to_video(video_id, f"Requested GPU runtime is no longer safe: {message} Falling back to CPU.")

        probe = probe_runtime(preference)
        if not probe.ok and preference == "gpu":
            video_store.log_to_video(video_id, f"GPU runtime validation failed: {probe.message} Falling back to CPU.")
            preference = "cpu"
            probe = probe_runtime("cpu")
            self._settings_processing_device = "cpu"
            self._processing_device_origin = "detected"
            try:
                desktop_settings.save_settings(
                    {
                        "theme": self._settings_theme,
                        "language": self._settings_language,
                        "processing_device": "cpu",
                        "processing_device_origin": "detected",
                    }
                )
            except OSError:
                pass
        if not probe.ok:
            self._runtime_probe_error = probe.message
            video_store.log_to_video(video_id, f"Processing runtime validation failed: {probe.message}")
            return

        try:
            from haizflow.pipeline.transcribe import release_warm_whisperx_model

            with self._model_runtime_lock:
                if preference != processing_device_preference():
                    shutdown_hymt2_worker()
                    release_warm_whisperx_model()
                    configure_processing_device(preference)
            self._active_processing_device = preference
            self._runtime_probe_error = ""
            self._pending_processing_device = ""
            video_store.log_to_video(video_id, f"Using the updated {preference.upper()} runtime for this video.")
        except Exception as exc:
            video_store.log_to_video(video_id, f"Could not apply the updated processing device: {exc}")

    def _refresh_live_hardware(self):
        """Keep Settings telemetry live without changing a pipeline mid-video."""
        capabilities = detect_hardware_capabilities()
        recommended_device = recommended_processing_device(capabilities)
        # The pipeline can force a single video onto CPU after a GPU fault. Once
        # the queue is idle, persist that runtime choice so Settings never
        # claims that GPU is active while the app is actually using CPU.
        runtime_fallback_device = processing_device_preference()
        runtime_fallback_pending = (
            not self._pending_processing_device
            and runtime_fallback_device != self._settings_processing_device
        )
        should_fallback_to_cpu = self._settings_processing_device == "gpu" and recommended_device == "cpu"
        should_follow_recommendation = (
            self._processing_device_origin == "detected"
            and recommended_device != self._settings_processing_device
        )
        runtime_needs_switch = runtime_fallback_pending or should_fallback_to_cpu or should_follow_recommendation
        self.hardwareChanged.emit()
        if self._pipeline_is_active():
            return
        if self._pending_processing_device:
            if not self._device_switching:
                self._switch_processing_device(self._pending_processing_device)
            return
        if not runtime_needs_switch or self._device_switching:
            return
        self._apply_detected_processing_device(
            runtime_fallback_device if runtime_fallback_pending else recommended_device
        )

    def _apply_detected_processing_device(self, device: str):
        """Persist a safe device chosen from live hardware telemetry."""
        if device not in {"cpu", "gpu"}:
            device = "cpu"
        self._settings_processing_device = device
        self._processing_device_origin = "detected"
        try:
            desktop_settings.save_settings(
                {
                    "theme": self._settings_theme,
                    "language": self._settings_language,
                    "processing_device": device,
                    "processing_device_origin": "detected",
                }
            )
        except OSError:
            pass
        self.settingsChanged.emit()
        self._switch_processing_device(device)

    def _set_warmup_status(self, detail: str):
        self._status_message = detail
        self.statusMessageChanged.emit()

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

    @Property(QObject, constant=True)
    def batchVideoModel(self):
        return self.batch_videos

    @Property(bool, notify=batchChanged)
    def isBatchRunning(self):
        return any(self._processing_queue.contains(video_id) for video_id in self._batch_video_ids)

    @Property(int, notify=batchChanged)
    def batchCount(self):
        return len(self._batch_video_ids)

    @Property(int, notify=batchChanged)
    def batchCompletedCount(self):
        completed_states = {"done", "failed", "cancelled"}
        videos = [video_store.get_video(video_id) for video_id in self._batch_video_ids]
        return sum(1 for video in videos if video and video.status in completed_states)

    @Property(int, notify=batchChanged)
    def batchPendingCount(self):
        videos = [video_store.get_video(video_id) for video_id in self._batch_video_ids]
        return sum(
            1
            for video in videos
            if video and video.status == "pending" and not self._processing_queue.contains(video.video_id)
        )

    @Property(int, notify=batchChanged)
    def batchProgress(self):
        videos = [video_store.get_video(video_id) for video_id in self._batch_video_ids]
        videos = [video for video in videos if video]
        return round(sum(video.progress for video in videos) / len(videos)) if videos else 0

    @Property(str, notify=batchChanged)
    def batchTargetLanguageLabel(self):
        if not self._batch_video_ids:
            return self._language_label(self._target_language)
        videos = [video_store.get_video(video_id) for video_id in self._batch_video_ids]
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

    @Property(QObject, constant=True)
    def taskModel(self):
        return self.tasks

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

    @Property(str, notify=selectedVideoChanged)
    def selectedTitle(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return f"{video.original_filename} | {video.status}" if video else "No video selected"

    @Property(bool, notify=selectedVideoChanged)
    def hasSelectedVideo(self):
        return self._selected_video_id is not None and video_store.get_video(self._selected_video_id) is not None

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
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return bool(video and video.project_type == "batch" and video.video_id in self._batch_video_ids)

    @Property("QVariantList", notify=selectedVideoChanged)
    def reviewSegments(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video or video.status != "awaiting_review":
            return []
        try:
            with open(video.files["transcript_json"], "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return []

    @Property(str, notify=selectedVideoChanged)
    def selectedFileName(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return video.original_filename if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedStatus(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return video.status if video else "none"

    @Property(str, notify=selectedVideoChanged)
    def selectedStep(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return video.step_detail or video.step if video else "pending"

    @Property(int, notify=selectedVideoChanged)
    def selectedProgress(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return video.progress if video else 0

    @Property(str, notify=selectedVideoChanged)
    def selectedStageLabel(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
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
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video:
            return ""
        item_detail = f"{video.current_item}/{video.total_items}" if video.total_items else ""
        return " | ".join(part for part in (video.step_detail, item_detail) if part)

    @Property(str, notify=selectedVideoChanged)
    def selectedElapsed(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
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
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return video.updated_at if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedOutputFormat(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return video.output_format if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedTargetLanguageLabel(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return self._language_label(video.target_language) if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedTranslatorProvider(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return video.translator_provider if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedInputPath(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))

    @Property(str, notify=selectedVideoChanged)
    def selectedOutputPath(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))

    @Property(bool, notify=selectedVideoChanged)
    def hasSelectedOutput(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video or video.status != "done":
            return False
        output_path = self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))
        return bool(output_path and os.path.isfile(output_path) and os.path.getsize(output_path) > 0)

    @Property(str, notify=selectedVideoChanged)
    def selectedSrtPath(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        return self._resolve_video_file(video, ("srt_output", "subtitle_output"), ("temp", "vi.srt"))

    @Property(str, notify=selectedVideoChanged)
    def selectedVoicePath(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
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
        capabilities = detect_hardware_capabilities()
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
        compatible, _message = validate_processing_device(str(preference))
        return compatible

    @Slot(str, result=str)
    def processingDeviceStatus(self, preference):
        preference = str(preference)
        compatible, message = validate_processing_device(preference)
        if self._settings_language != "vi":
            return message
        capabilities = detect_hardware_capabilities()
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
        if not self.hasOpenProject:
            self._url_importer.complete_import(False, "Open or create a project before downloading a video.")
            return
        if self._project_type == "single" and self.isSelectedVideoProcessing:
            self._url_importer.complete_import(
                False,
                "Pause or finish the current video before replacing it.",
            )
            return
        project_root = self._selected_project_root()
        self._url_import_target = {
            "project_key": self._selected_project_key,
            "project_name": self._project_name,
            "project_directory": self._project_directory,
            "project_type": self._project_type,
            "selected_video_id": self._selected_video_id,
            "config": self._build_config(),
            "media_source": {
                "type": "video_url",
                "platform": self._url_importer.platform,
                "source_url": self._url_importer.url,
                "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        }
        if not self._url_importer.start_download(project_root):
            self._url_import_target = None

    def _handle_url_download_ready(self, path, _workspace, mode):
        target = self._url_import_target
        self._url_import_target = None
        imported = self._import_downloaded_video(path, mode, target)

        message = "" if imported else "The video was downloaded but could not be added to the project."
        self._url_importer.complete_import(imported, message)

    def _import_downloaded_video(self, path: str, mode: str, target) -> bool:
        """Commit an async URL download to the project that requested it."""
        if not target:
            if mode == "batch":
                previous_count = self.batchCount
                self.importBatchVideos([path])
                return self.batchCount > previous_count
            if self._selected_video_id:
                return self.replaceSelectedVideoVideo(path)
            return self.importVideo(path)

        target_video_id = target.get("selected_video_id")
        if mode != "batch" and target_video_id:
            return self._replace_video_video(target_video_id, path, target.get("media_source"))

        config = target.get("config")
        if not isinstance(config, VideoConfig):
            return False
        registered_keys = {project.get("key") for project in project_store.list_projects()}
        if target.get("project_key") not in registered_keys:
            QMessageBox.warning(None, "Import video", "The destination project no longer exists.")
            return False
        try:
            import_kwargs = {
                "project_name": str(target.get("project_name") or ""),
                "project_directory": str(target.get("project_directory") or ""),
            }
            if target.get("media_source"):
                import_kwargs["media_source"] = target["media_source"]
            video = create_desktop_video(
                path,
                config,
                **import_kwargs,
                project_key_value=str(target.get("project_key") or ""),
            )
            thumbnail_path = self._create_video_thumbnail_path(
                video.files["video_input"],
                self._video_thumbnail_path(video.video_id),
            )
            if thumbnail_path:
                video.files["thumbnail"] = thumbnail_path
                video_store.save_video(video)
        except Exception as exc:
            QMessageBox.warning(None, "Import video", str(exc))
            return False

        target_is_open = target.get("project_key") == self._selected_project_key
        if target_is_open and mode == "batch":
            self._batch_video_ids.append(video.video_id)
            self._refresh_batch_model()
            self.batchChanged.emit()
        elif target_is_open:
            self._select_video(video)
        self.refreshVideos()
        return True

    def _current_project_media_keys(self) -> set[str]:
        keys = set()
        for video in video_store.list_videos():
            if not video.project_directory:
                continue
            key = self._video_project_key(video)
            if key != self._selected_project_key:
                continue
            source = getattr(video, "media_source", None)
            platform = str(getattr(source, "platform", "") or "").strip().lower()
            remote_video_id = str(getattr(source, "remote_video_id", "") or "").strip().lower()
            source_url = str(getattr(source, "source_url", "") or "").strip().lower()
            if platform and remote_video_id:
                keys.add(f"{platform}:{remote_video_id}")
            if source_url:
                keys.add(source_url)
                keys.add(normalize_remote_url(source_url))
        return keys

    @Slot(result=bool)
    def prepareChannelImport(self):
        if not self.hasOpenProject or self._project_type != "batch":
            QMessageBox.information(
                None,
                "Channel import",
                "Open or create a batch project before importing a channel.",
            )
            return False
        project_root = self._selected_project_root()
        self._channel_importer.attach_project(
            self._selected_project_key,
            project_root,
            self._current_project_media_keys(),
        )
        return True

    @Slot(result=bool)
    def startChannelDownloads(self):
        if not self.prepareChannelImport() or self._channel_importer.selectedCount <= 0:
            return False
        session_id = self._channel_importer.sessionId
        if not session_id:
            return False
        self._remember_channel_import_target(session_id)
        # The coordinator continuously throttles to one worker while the model
        # pipeline is active and can return to two when the device is idle.
        started_session_id = self._channel_importer.start_downloads(2)
        if not started_session_id:
            self._channel_import_targets.pop(session_id, None)
            return False
        return True

    def _remember_channel_import_target(self, session_id: str) -> None:
        self._channel_import_targets[session_id] = {
            "project_key": self._selected_project_key,
            "project_name": self._project_name,
            "project_directory": self._project_directory,
            "project_type": "batch",
            "config": self._build_config().model_copy(deep=True),
            "channel_url": self._channel_importer.channelUrl,
            "channel_name": self._channel_importer.channelName,
        }

    @Slot(int, result=bool)
    def retryChannelVideo(self, row):
        if not self.prepareChannelImport():
            return False
        session_id = self._channel_importer.sessionId
        if not session_id:
            return False
        self._remember_channel_import_target(session_id)
        if not self._channel_importer.retry(int(row)):
            self._channel_import_targets.pop(session_id, None)
            return False
        return True

    def _handle_channel_video_ready(self, path, _workspace, candidate_payload, project_key, session_id):
        target = self._channel_import_targets.get(session_id)
        candidate = dict(candidate_payload or {})
        remote_video_id = str(candidate.get("remote_video_id") or "")
        if not target or target.get("project_key") != project_key:
            self._channel_importer.complete_video(
                session_id,
                remote_video_id,
                False,
                "The destination project is no longer available.",
            )
            return
        registered_keys = {project.get("key") for project in project_store.list_projects()}
        if project_key not in registered_keys:
            self._channel_importer.complete_video(
                session_id,
                remote_video_id,
                False,
                "The destination project was deleted.",
            )
            return

        media_source = {
            "type": "channel",
            "platform": str(candidate.get("platform") or ""),
            "remote_video_id": remote_video_id,
            "source_url": str(candidate.get("source_url") or ""),
            "channel_url": str(target.get("channel_url") or ""),
            "channel_name": str(target.get("channel_name") or candidate.get("uploader") or ""),
            "import_session_id": session_id,
            "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        try:
            video = create_desktop_video(
                path,
                target["config"].model_copy(deep=True),
                project_name=str(target.get("project_name") or ""),
                project_directory=str(target.get("project_directory") or ""),
                media_source=media_source,
                move_input=True,
                project_key_value=project_key,
            )
            thumbnail_path = self._create_video_thumbnail_path(
                video.files["video_input"],
                self._video_thumbnail_path(video.video_id),
            )
            if thumbnail_path:
                video.files["thumbnail"] = thumbnail_path
                video_store.save_video(video)
        except Exception as exc:
            self._channel_importer.complete_video(session_id, remote_video_id, False, str(exc))
            return

        if project_key == self._selected_project_key and self._project_type == "batch":
            if video.video_id not in self._batch_video_ids:
                self._batch_video_ids.append(video.video_id)
            self._refresh_batch_model()
            self.batchChanged.emit()
        self.refreshVideos()
        self._channel_importer.complete_video(session_id, remote_video_id, True)

    @Slot(str)
    def _finish_channel_import_target(self, session_id):
        self._channel_import_targets.pop(str(session_id), None)

    @Slot()
    def browseVideo(self):
        path, _ = QFileDialog.getOpenFileName(None, "Choose input video", "", "Video files (*.mp4 *.mov *.mkv);;All files (*.*)")
        if path:
            if self._selected_video_id:
                self.replaceSelectedVideoVideo(path)
            else:
                self.importVideo(path)

    @Slot(str, result=bool)
    def replaceSelectedVideoVideo(self, path):
        return self._replace_video_video(self._selected_video_id, path)

    def _replace_video_video(self, video_id, path, media_source=None):
        video = video_store.get_video(video_id) if video_id else None
        normalized_path = self._normalize_video_path(path)
        if not video:
            return False
        if video.status == "processing" or self._processing_queue.active_video_id == video.video_id:
            QMessageBox.information(None, "Replace video", "Pause or finish this video before replacing it.")
            return False
        if not os.path.isfile(normalized_path) or os.path.splitext(normalized_path)[1].lower() not in {".mp4", ".mov", ".mkv"}:
            QMessageBox.warning(None, "Invalid video", "Choose an MP4, MOV, or MKV video file.")
            return False
        if self._processing_queue.discard(video.video_id):
            self._update_queue_positions()
        try:
            video = video_store.replace_video_input(video.video_id, normalized_path, media_source=media_source)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(None, "Replace video", str(exc))
            return False
        if not video:
            return False
        destination = video.files["video_input"]
        try:
            video.video_width, video.video_height = get_video_dimensions(destination)
        except RuntimeError:
            video.video_width, video.video_height = 0, 0
        thumbnail_path = self._create_video_thumbnail_path(destination, self._video_thumbnail_path(video.video_id))
        if thumbnail_path:
            video.files["thumbnail"] = thumbnail_path
        video_store.save_video(video)
        # The managed input path remains stable (input/video.ext) after a
        # replacement, so explicitly refresh the image source as well.
        update_open_view = self._selected_video_id == video.video_id
        if update_open_view:
            self._set_video_path(destination, refresh_thumbnail=True)
        video_store.log_to_video(video.video_id, f"Input video replaced with: {video.original_filename}")
        if update_open_view:
            self._logs = self._read_video_logs(video.video_id)
            self.videoThumbnailChanged.emit()
            self.selectedVideoChanged.emit()
            self.logsChanged.emit()
        self.refreshVideos()
        self._log_queue.put("__QUEUE_CHANGED__")
        return True

    @Slot()
    def browseProjectDirectory(self):
        os.makedirs(self._project_directory, exist_ok=True)
        path = QFileDialog.getExistingDirectory(None, "Choose project storage location", self._project_directory)
        if path:
            self._project_directory = os.path.abspath(path)
            self.projectSetupChanged.emit()

    @Slot(str, str, str, result=bool)
    def prepareProject(self, project_name, project_directory, project_type):
        project_name = project_name.strip()
        project_directory = project_directory.strip()
        if not project_name:
            QMessageBox.warning(None, "Project name", "Enter a project name.")
            return False
        if not project_directory:
            QMessageBox.warning(None, "Project storage location", "Choose a location for this project.")
            return False
        self._project_name = project_name
        self._project_directory = os.path.abspath(project_directory)
        self._project_type = "batch" if project_type == "batch" else "single"
        try:
            project = project_store.create_project(
                self._project_name,
                self._project_directory,
                self._project_type,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(None, "Project storage location", f"Cannot create the project at this location: {exc}")
            return False
        self._selected_project_key = project["key"]
        self.videoPath = ""
        self._selected_video_id = None
        self._batch_video_ids = []
        self._refresh_batch_model()
        self._logs = ""
        self.tasks.set_video(None)
        self.projectSetupChanged.emit()
        self.selectedVideoChanged.emit()
        self.logsChanged.emit()
        self.refreshVideos()
        self.projectPrepared.emit()
        return True

    @Slot(str, str, str, result=bool)
    def applySettings(self, theme, language, processing_device):
        processing_device = str(processing_device).lower()
        pipeline_active = self._pipeline_is_active()
        if processing_device != self._settings_processing_device and not (pipeline_active or self._device_switching):
            clear_runtime_profile_cache()
        compatible, compatibility_message = validate_processing_device(processing_device)
        if not compatible:
            QMessageBox.warning(None, "Processing device", compatibility_message)
            return False
        device_changed = processing_device != self._settings_processing_device
        try:
            settings = desktop_settings.save_settings(
                {
                    "theme": theme,
                    "language": language,
                    "processing_device": processing_device,
                    "processing_device_origin": "manual",
                }
            )
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot save settings: {exc}")
            return False
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        self._settings_processing_device = settings["processing_device"]
        self._processing_device_origin = settings["processing_device_origin"]
        _set_ui_language(self._settings_language)
        if device_changed and (pipeline_active or self._device_switching):
            self._pending_processing_device = self._settings_processing_device
            self._status_message = "Settings applied. The current video keeps its processing device."
        else:
            self._status_message = "Settings applied"
        self.settingsChanged.emit()
        self.languageOptionsChanged.emit()
        self.statusMessageChanged.emit()
        if device_changed and not (pipeline_active or self._device_switching):
            self._switch_processing_device(self._settings_processing_device)
        return True

    @Slot()
    def resetSettings(self):
        pipeline_active = self._pipeline_is_active()
        try:
            settings = desktop_settings.reset_settings()
            settings["processing_device"] = recommended_processing_device(detect_hardware_capabilities())
            settings["processing_device_origin"] = "detected"
            settings = desktop_settings.save_settings(settings)
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot restore defaults: {exc}")
            return
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        _set_ui_language(self._settings_language)
        device_changed = settings["processing_device"] != self._settings_processing_device
        self._settings_processing_device = settings["processing_device"]
        self._processing_device_origin = settings["processing_device_origin"]
        if device_changed and (pipeline_active or self._device_switching):
            self._pending_processing_device = self._settings_processing_device
            self._status_message = "Settings reset. The processing device changes after the current video."
        else:
            self._status_message = "Settings reset to defaults"
        self.settingsChanged.emit()
        self.languageOptionsChanged.emit()
        self.statusMessageChanged.emit()
        if device_changed and not (pipeline_active or self._device_switching):
            self._switch_processing_device(self._settings_processing_device)

    @Slot(str, result=bool)
    def importVideo(self, path):
        normalized_path = self._normalize_video_path(path)
        if not os.path.isfile(normalized_path):
            QMessageBox.warning(None, "Invalid video", "The dropped file is unavailable.")
            return False
        if os.path.splitext(normalized_path)[1].lower() not in {".mp4", ".mov", ".mkv"}:
            QMessageBox.warning(None, "Unsupported file", "Choose an MP4, MOV, or MKV video file.")
            return False
        if self.hasOpenProject:
            try:
                video = create_desktop_video(
                    normalized_path,
                    self._build_config(),
                    project_name=self._project_name,
                    project_directory=self._project_directory,
                    project_key_value=self._selected_project_key,
                )
            except Exception as exc:
                QMessageBox.critical(None, "Cannot import video", str(exc))
                return False
            self._assign_project_thumbnail(video)
            self._select_video(video)
            self.refreshVideos()
            return True

        self._selected_video_id = None
        self.tasks.set_video(None)
        self.videoPath = normalized_path
        self.selectedVideoChanged.emit()
        return True

    @Slot()
    def browseBatchVideos(self):
        paths, _ = QFileDialog.getOpenFileNames(
            None,
            "Choose videos for batch processing",
            "",
            "Video files (*.mp4 *.mov *.mkv);;All files (*.*)",
        )
        if paths:
            self.importBatchVideos(paths)

    @Slot()
    def browseBatchFolder(self):
        folder = QFileDialog.getExistingDirectory(
            None,
            "Choose a folder of videos for batch processing",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self.importBatchVideos([folder])

    @Slot("QVariantList")
    def importBatchVideos(self, paths):
        valid_paths, invalid_names = self._collect_batch_video_paths(paths)

        if not valid_paths:
            if invalid_names:
                QMessageBox.warning(
                    None,
                    "Some videos were skipped",
                    self._batch_rejection_message(invalid_names),
                )
            else:
                QMessageBox.warning(None, "No supported videos", "Choose MP4, MOV, or MKV video files.")
            return

        created_ids = []
        errors = []
        for path in valid_paths:
            try:
                video = create_desktop_video(
                    path,
                    self._build_config(),
                    project_name=self._project_name,
                    project_directory=self._project_directory,
                    project_key_value=self._selected_project_key,
                )
                thumbnail_path = self._create_video_thumbnail_path(
                    video.files["video_input"],
                    self._video_thumbnail_path(video.video_id),
                )
                if thumbnail_path:
                    video.files["thumbnail"] = thumbnail_path
                    video_store.save_video(video)
                created_ids.append(video.video_id)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")

        self._batch_video_ids.extend(created_ids)
        self._refresh_batch_model()
        self.refreshVideos()
        self.batchChanged.emit()

        rejected = invalid_names + errors
        if rejected:
            QMessageBox.warning(
                None,
                "Some videos were skipped",
                self._batch_rejection_message(rejected),
            )

    def _batch_rejection_message(self, rejected) -> str:
        rejected = [str(item) for item in rejected]
        shown = rejected[:12]
        remaining = len(rejected) - len(shown)
        if remaining:
            suffix = f"... và {remaining} mục khác" if self._settings_language == "vi" else f"... and {remaining} more"
            shown.append(suffix)
        if self._settings_language == "vi":
            heading = f"{len(rejected)} mục không được hỗ trợ hoặc không thể đọc:"
        else:
            heading = f"{len(rejected)} unsupported or unreadable item(s):"
        return f"{heading}\n\n" + "\n".join(shown)

    @Slot()
    def startBatch(self):
        pending_ids = []
        for video_id in self._batch_video_ids:
            video = video_store.get_video(video_id)
            if video and video.status == "pending":
                pending_ids.append(video_id)
        if not pending_ids:
            QMessageBox.information(None, "Batch queue", "Add at least one video to the queue.")
            return

        self._batch_running = True
        self._batch_stop_requested = False
        added = self._enqueue_videos(pending_ids)
        if not added:
            self._batch_running = False
            QMessageBox.information(None, "Batch queue", "These videos are already waiting or processing.")
            return
        self.batchChanged.emit()

    @Slot(result=bool)
    def applyBatchSettings(self):
        updated = 0
        for video_id in self._batch_video_ids:
            video = video_store.get_video(video_id)
            if not video or self._processing_queue.contains(video_id):
                continue
            video_store.update_video(
                video_id,
                mode=self._workflow_mode,
                source_language="auto",
                target_language=self._target_language,
                tts_voice=self._tts_voice,
                enable_audio_separation=self._enable_audio_separation,
                original_video_volume=self._original_volume,
            )
            updated += 1
        if not updated:
            QMessageBox.information(None, "Batch settings", "Add at least one video before applying settings.")
            return False
        self.refreshVideos()
        self.batchChanged.emit()
        return True

    @Slot()
    def loadBatchSettings(self):
        videos = [video_store.get_video(video_id) for video_id in self._batch_video_ids]
        videos = [video for video in videos if video]
        if not videos:
            return
        common, _count = Counter(
            (
                video.mode,
                video.target_language,
                video.tts_voice,
                video.enable_audio_separation,
                video.original_video_volume,
            )
            for video in videos
        ).most_common(1)[0]
        workflow_mode, target_language, tts_voice, audio_separation, original_volume = common
        self._workflow_mode = workflow_mode
        self._target_language = str(target_language or "vi")
        self._tts_voice = self._normalized_voice_for_language(self._target_language, tts_voice)
        self._enable_audio_separation = audio_separation
        self._original_volume = original_volume
        self.workflowModeChanged.emit()
        self.targetLanguageChanged.emit()
        self.ttsVoiceChanged.emit()
        self.ttsVoiceOptionsChanged.emit()
        self.enableAudioSeparationChanged.emit()
        self.originalVolumeChanged.emit()

    @Slot(result=bool)
    def saveSelectedVideoSettings(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video or video.project_type != "batch" or self._processing_queue.contains(video.video_id):
            return False
        self._apply_setup_to_video(video)
        video_store.log_to_video(video.video_id, "Per-video dubbing settings saved.")
        self.refreshVideos()
        self.selectedVideoChanged.emit()
        self.batchChanged.emit()
        return True

    @Slot()
    def stopBatch(self):
        if not self.isBatchRunning:
            return
        if QMessageBox.question(None, "Stop batch", "Stop the active video and cancel the remaining queue?") != QMessageBox.StandardButton.Yes:
            return

        self._batch_stop_requested = True
        active_video_id = self._processing_queue.active_video_id
        if active_video_id in self._batch_video_ids:
            cancel_video(active_video_id)
            video_store.update_video(active_video_id, status="cancelled", error=None, step="cancelled")
            video_store.log_to_video(active_video_id, "Batch stop requested. Active subprocesses were force-stopped.")
        for video_id in self._batch_video_ids:
            video = video_store.get_video(video_id)
            if video and self._processing_queue.discard(video_id):
                video_store.update_video(video_id, status="cancelled", error=None, step="cancelled")
                video_store.log_to_video(video_id, "Cancelled while waiting in the processing queue.")
        self._refresh_batch_model()
        self.batchChanged.emit()

    @Slot()
    def clearBatch(self):
        if self.isBatchRunning:
            return
        self._batch_video_ids = []
        self._refresh_batch_model()
        self.batchChanged.emit()

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
        batch_ids = list(self._batch_video_ids)
        if not self.hasOpenProject:
            return
        if not batch_ids:
            self.deleteCurrentProject()
            return
        project_name = self._project_name or "this batch"
        message = (
            "Delete this batch project and all of its videos?\n\n"
            f"{project_name}\n{len(batch_ids)} video(s)\n\n"
            "This removes processing logs, temporary data, copied inputs, and generated videos. "
            "If processing is active, it will be stopped first."
        )
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        if QMessageBox.question(
            None,
            "Delete project",
            message,
            buttons,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        current_key = self._selected_project_key
        try:
            project_store.validate_project_deletion_by_key(current_key)
        except Exception as exc:
            QMessageBox.warning(None, "Delete project", str(exc))
            return
        if not self._channel_importer.cancel_project(current_key):
            QMessageBox.information(
                None,
                "Channel import",
                "Channel import is still stopping. Try deleting the project again in a moment.",
            )
            return
        for session_id, target in tuple(self._channel_import_targets.items()):
            if target.get("project_key") == current_key:
                self._channel_import_targets.pop(session_id, None)

        self._batch_stop_requested = True
        active_video_id = self._processing_queue.active_video_id
        if active_video_id in batch_ids:
            cancel_video(active_video_id)

        failures = []
        remaining_ids = []
        for video_id in batch_ids:
            video = video_store.get_video(video_id)
            if not video:
                continue
            self._deleted_video_ids.add(video_id)
            self._processing_queue.discard(video_id)
            if video.status == "processing":
                cancel_video(video_id)
            output_directory = self._batch_output_directory(video)
            try:
                if output_directory and os.path.isdir(output_directory):
                    shutil.rmtree(output_directory)
                video_store.delete_video(video_id)
                self._remove_empty_batch_output_parents(video)
            except Exception as exc:
                failures.append(f"{video.original_filename}: {exc}")
                remaining_ids.append(video_id)

        self._batch_video_ids = remaining_ids
        self._refresh_batch_model()
        self.batchChanged.emit()
        self._selected_video_id = None
        self._logs = ""
        self.tasks.set_video(None)
        self.selectedVideoChanged.emit()
        self.logsChanged.emit()
        self.refreshVideos()

        if failures:
            QMessageBox.warning(
                None,
                "Batch delete incomplete",
                "Some videos could not be deleted. You can retry after closing any program using them.\n\n"
                + "\n".join(failures[:5]),
            )
            return
        try:
            project_store.delete_project_by_key(current_key)
        except Exception as exc:
            QMessageBox.warning(None, "Delete project", str(exc))
            return
        self._selected_project_key = ""
        self._project_name = ""
        self.projectSetupChanged.emit()
        self.batchDeleted.emit()

    @Slot()
    def startVideo(self):
        if not self._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return
        try:
            video = create_desktop_video(self._video_path, self._build_config())
        except Exception as exc:
            QMessageBox.critical(None, "Cannot start project", str(exc))
            return

        self._assign_project_thumbnail(video)

        self._selected_video_id = video.video_id
        self._logs = self._read_video_logs(video.video_id)
        self.tasks.set_video(video)
        self.selectedVideoChanged.emit()
        self.logsChanged.emit()
        self.refreshVideos()
        self._enqueue_video(video.video_id)

    @Slot(result=bool)
    def startProjectVideo(self):
        if not self._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return False
        if not self._project_name.strip():
            QMessageBox.warning(None, "Project name", "Enter a project name.")
            return False
        if not self._project_directory.strip():
            QMessageBox.warning(None, "Project storage location", "Choose a location for this project.")
            return False
        selected_video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if selected_video and self._processing_queue.contains(selected_video.video_id):
            self._status_message = "This video is already waiting or processing."
            self.statusMessageChanged.emit()
            return False
        if selected_video and selected_video.status == "pending" and not self._processing_queue.contains(selected_video.video_id):
            self._apply_setup_to_video(selected_video, review_approved=False)
            video_store.log_to_video(selected_video.video_id, "Processing requested for the imported video.")
            self._enqueue_video(selected_video.video_id)
            self.selectedVideoChanged.emit()
            self.refreshVideos()
            return True
        if selected_video:
            return False
        try:
            video = create_desktop_video(
                self._video_path,
                self._build_config(),
                project_name=self._project_name,
                project_directory=self._project_directory,
                project_key_value=self._selected_project_key,
            )
        except Exception as exc:
            QMessageBox.critical(None, "Cannot create project", str(exc))
            return False

        self._assign_project_thumbnail(video)

        self._selected_video_id = video.video_id
        self._logs = self._read_video_logs(video.video_id)
        self.tasks.set_video(video)
        self.selectedVideoChanged.emit()
        self.logsChanged.emit()
        self.refreshVideos()
        self._enqueue_video(video.video_id)
        return True

    @Slot()
    def stopVideo(self):
        selected_video_id = self._selected_video_id
        if not selected_video_id or selected_video_id != self._processing_queue.active_video_id:
            return
        selected_video = video_store.get_video(selected_video_id)
        if not selected_video:
            return
        if self.isSelectedBatchVideo:
            self.stopBatch()
            return
        if QMessageBox.question(None, "Pause video", "Pause this video? You can resume it later from Projects.") != QMessageBox.StandardButton.Yes:
            return
        resume_step = selected_video.step
        pause_video(selected_video_id)
        video_store.update_video(selected_video_id, status="paused", error=None, step="paused", resume_step=resume_step, step_detail=f"Paused during {resume_step or 'startup'}")
        video_store.log_to_video(selected_video_id, "Pause requested. Active subprocesses were stopped.")
        self.selectedVideoChanged.emit()
        self.refreshVideos()

    @Slot()
    def resumeSelectedVideo(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video or video.status != "paused":
            return
        video_store.update_video(video.video_id, status="pending", step="queued", step_detail="Queued to resume")
        self._enqueue_video(video.video_id)
        self.selectedVideoChanged.emit()

    @Slot()
    def restartSelectedVideo(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video or self._processing_queue.contains(video.video_id):
            return
        if self._device_switching:
            QMessageBox.information(None, "Processing device", "Wait for the processing device to finish switching before restarting.")
            return
        if QMessageBox.question(None, "Restart video", "Apply the current dubbing setup and restart this project?") != QMessageBox.StandardButton.Yes:
            return
        self._apply_setup_to_video(video, review_approved=False)
        restarted = video_store.prepare_video_restart(video.video_id)
        if not restarted:
            return
        profile = runtime_profile()
        video_store.log_to_video(
            restarted.video_id,
            f"Restart requested with the latest dubbing setup and runtime: {profile.summary}.",
        )
        self._enqueue_video(restarted.video_id)
        self.selectedVideoChanged.emit()

    @Slot(str)
    def approveTranslationReview(self, payload):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
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
        video_store.update_video(video.video_id, review_approved=True, status="pending", step="queued", step_detail="Queued to create dub")
        video_store.log_to_video(video.video_id, f"Translation review approved with {len(segments)} edited segments. Added to the processing queue.")
        self._enqueue_video(video.video_id)
        self.selectedVideoChanged.emit()

    @Slot(int)
    def selectVideo(self, row: int):
        video = self.videos.video_at(row)
        if not video:
            return
        self._select_video(video)

    def _select_video(self, video):
        self._selected_video_id = video.video_id
        self._project_name = video.project_name or os.path.splitext(video.original_filename)[0]
        self._project_directory = video.project_directory or self._project_directory
        self._project_type = "batch" if getattr(video, "project_type", "single") == "batch" else "single"
        self._selected_project_key = self._video_project_key(video)
        if (
            self._processing_queue.active_video_id != video.video_id
            and video.status != "processing"
            and (video.source_language != "auto" or video.output_format != "keep_ratio")
        ):
            video = video_store.update_video(video.video_id, source_language="auto", output_format="keep_ratio") or video
        if migrate_legacy_single_export(video):
            video = video_store.get_video(video.video_id) or video
        self._workflow_mode = video.mode
        self._target_language = str(video.target_language or "vi")
        self._tts_voice = self._normalized_voice_for_language(self._target_language, video.tts_voice)
        if self._tts_voice != video.tts_voice and video.status != "processing":
            video = video_store.update_video(video.video_id, tts_voice=self._tts_voice) or video
            video_store.log_to_video(video.video_id, "Updated an incompatible saved TTS voice to match the target language.")
        self._enable_audio_separation = video.enable_audio_separation
        self._original_volume = video.original_video_volume
        input_path = self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
        thumbnail_path = video.files.get("thumbnail") or ""
        self._video_path = input_path
        self._video_thumbnail_source = thumbnail_source(thumbnail_path)
        self._load_video_preview(video)
        self._logs = self._read_video_logs(video.video_id)
        self.tasks.set_video(video)
        self.videoPathChanged.emit()
        self.videoThumbnailChanged.emit()
        self.targetLanguageChanged.emit()
        self.ttsVoiceChanged.emit()
        self.ttsVoiceOptionsChanged.emit()
        self.enableAudioSeparationChanged.emit()
        self.originalVolumeChanged.emit()
        self.workflowModeChanged.emit()
        self.projectSetupChanged.emit()
        self.selectedVideoChanged.emit()
        self.processingChanged.emit()
        self.logsChanged.emit()

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
        videos = project["videos"]
        self._project_name = project["project_name"]
        self._project_directory = project["project_directory"] or self._project_directory
        self._project_type = project["project_type"]
        self._selected_project_key = project["key"]
        self._batch_video_ids = [video.video_id for video in videos] if self._project_type == "batch" else []
        self._refresh_batch_model()
        if videos:
            self._select_video(videos[0])
        else:
            self.videoPath = ""
            self._selected_video_id = None
            self._logs = ""
            self.tasks.set_video(None)
            self.selectedVideoChanged.emit()
            self.logsChanged.emit()
        self._project_type = project["project_type"]
        self.projectSetupChanged.emit()
        self.batchChanged.emit()
        if self._project_type == "batch":
            self.prepareChannelImport()

    @Slot()
    def deleteSelectedVideo(self):
        if not self._selected_video_id:
            QMessageBox.information(None, "No video selected", "Select a video in this batch first.")
            return
        video_id = self._selected_video_id
        video = video_store.get_video(video_id)
        label = video.original_filename if video else video_id
        message = f"Remove this video from the batch project and delete its generated files?\n\n{label}\n\nIf it is running, it will be stopped first."
        if QMessageBox.question(None, "Remove video", message) != QMessageBox.StandardButton.Yes:
            return
        if video and (video.status == "processing" or self._processing_queue.active_video_id == video_id):
            cancel_video(video_id)
            video_store.update_video(video_id, status="cancelled", error=None, step="cancelled")
        self._deleted_video_ids.add(video_id)
        self._processing_queue.discard(video_id)
        try:
            deleted = video_store.delete_video(video_id)
        except Exception as exc:
            QMessageBox.critical(None, "Delete failed", str(exc))
            return
        if not deleted:
            QMessageBox.information(None, "Already removed", "Video data was already removed.")
        if video_id in self._batch_video_ids:
            self._batch_video_ids.remove(video_id)
            self._refresh_batch_model()
            self.batchChanged.emit()
        self._selected_video_id = None
        self._logs = ""
        self.tasks.set_video(None)
        self.selectedVideoChanged.emit()
        self.logsChanged.emit()
        self.refreshVideos()
        self.videoDeleted.emit()

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
        if not self.hasOpenProject:
            QMessageBox.information(None, "Delete project", "Select a project first.")
            return

        current_key = self._selected_project_key
        project_videos = [
            video
            for video in video_store.list_videos()
            if video.project_directory
            and self._video_project_key(video) == current_key
        ]
        video_label = "" if not project_videos else f"\n\nThis also removes {len(project_videos)} video(s) and their generated files."
        message = f"Delete project '{self._project_name}' and all files inside its project folder?{video_label}"
        if QMessageBox.question(None, "Delete project", message) != QMessageBox.StandardButton.Yes:
            return

        try:
            project_store.validate_project_deletion_by_key(current_key)
        except Exception as exc:
            QMessageBox.critical(None, "Delete project", str(exc))
            return
        if not self._channel_importer.cancel_project(current_key):
            QMessageBox.information(
                None,
                "Channel import",
                "Channel import is still stopping. Try deleting the project again in a moment.",
            )
            return
        for session_id, target in tuple(self._channel_import_targets.items()):
            if target.get("project_key") == current_key:
                self._channel_import_targets.pop(session_id, None)

        try:
            for video in project_videos:
                self._processing_queue.discard(video.video_id)
                if video.status == "processing" or self._processing_queue.active_video_id == video.video_id:
                    cancel_video(video.video_id)
                    video_store.update_video(video.video_id, status="cancelled", error=None, step="cancelled")
                self._deleted_video_ids.add(video.video_id)
                video_store.delete_video(video.video_id)
            project_store.delete_project_by_key(current_key)
        except Exception as exc:
            QMessageBox.critical(None, "Delete project", str(exc))
            return

        self._selected_video_id = None
        self._selected_project_key = ""
        self._batch_video_ids = []
        self._logs = ""
        self.tasks.set_video(None)
        self.videoPath = ""
        self._refresh_batch_model()
        self.selectedVideoChanged.emit()
        self.projectSetupChanged.emit()
        self.logsChanged.emit()
        self.batchChanged.emit()
        self.refreshVideos()
        self.videoDeleted.emit()

    @Slot()
    def refreshVideos(self):
        all_videos = video_store.list_videos()
        self.videos.set_videos(all_videos[:40])
        summaries = self._build_project_summaries(all_videos, project_store.list_projects())
        self.projects.set_projects(summaries)
        self.single_projects.set_projects(
            [project for project in summaries if project["project_type"] == "single"]
        )
        self.batch_projects.set_projects(
            [project for project in summaries if project["project_type"] == "batch"]
        )
        self._refresh_batch_model()
        selected = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        self.tasks.set_video(selected)
        self.selectedVideoChanged.emit()
        missing_thumbnails = [video.video_id for video in all_videos if not video.files.get("thumbnail")]
        if missing_thumbnails and not self._thumbnail_refresh_running:
            self._thumbnail_refresh_running = True
            threading.Thread(target=self._create_missing_thumbnails, args=(missing_thumbnails,), daemon=True).start()

    def _create_missing_thumbnails(self, video_ids):
        try:
            for video_id in video_ids:
                video = video_store.get_video(video_id)
                if not video or video.files.get("thumbnail"):
                    continue
                video_path = self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
                thumbnail_path = self._create_video_thumbnail_path(video_path, self._video_thumbnail_path(video.video_id))
                if thumbnail_path:
                    video.files["thumbnail"] = thumbnail_path
                    video_store.save_video(video)
        finally:
            self._log_queue.put("__THUMBNAILS_READY__")

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

    @Slot()
    def openBatchSubtitleEditor(self):
        groups = self._batch_dimension_groups()
        if not groups:
            QMessageBox.information(None, "Subtitle presets", "Add at least one video before editing subtitles.")
            return
        self._preview_group_keys = [group["size_key"] for group in groups]
        self._preview_group_index = 0
        self._open_batch_group_preview(self._preview_group_keys[0])

    @Slot(str)
    def openBatchSizeEditor(self, size_key):
        group = self._batch_dimension_group(size_key)
        if not group:
            return
        self._preview_group_keys = [size_key]
        self._preview_group_index = 0
        self._open_batch_group_preview(size_key)

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
            for video_id in self._preview_target_video_ids:
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
        if self._selected_video_id:
            video = video_store.get_video(self._selected_video_id)
            if video:
                self.tasks.set_video(video)
                self.selectedVideoChanged.emit()
        self.refreshVideos()
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

    def _enqueue_video(self, video_id: str) -> bool:
        video = video_store.get_video(video_id)
        if not video or video.status == "processing" or self._processing_queue.contains(video_id):
            return False
        video_store.update_video(video_id, status="pending", step="queued", step_detail="Queued for processing")
        added = self._processing_queue.enqueue(video_id)
        if not added:
            return False
        video_store.log_to_video(video_id, "Added to the processing queue.")
        self._update_queue_positions()
        self.processingChanged.emit()
        self.selectedVideoChanged.emit()
        self._log_queue.put("__QUEUE_CHANGED__")
        return True

    def _enqueue_videos(self, video_ids) -> int:
        added = 0
        for video_id in video_ids:
            if self._enqueue_video(video_id):
                added += 1
        return added

    def _update_queue_positions(self) -> None:
        for position, video_id in enumerate(self._processing_queue.pending_ids(), start=1):
            video = video_store.get_video(video_id)
            if video and video.status == "pending":
                video_store.update_video(video_id, step="queued", step_detail=f"Queued: position {position}")

    def _on_queue_video_started(self, video_id: str) -> None:
        if video_id in self._deleted_video_ids:
            return
        video = video_store.get_video(video_id)
        if not video or video.status == "cancelled":
            return
        self._activate_pending_device_for_next_video(video_id)
        video_store.update_video(video_id, status="processing", step="starting", step_detail="Processing started")
        video_store.log_to_video(video_id, "Processing started from the shared queue.")
        self._update_queue_positions()
        self._log_queue.put(f"__QUEUE_STARTED__:{video_id}")

    def _on_queue_video_finished(self, video_id: str) -> None:
        self._update_queue_positions()
        self._log_queue.put(f"__QUEUE_FINISHED__:{video_id}")

    def _on_processing_queue_idle(self) -> None:
        self._log_queue.put("__QUEUE_IDLE__")

    def _on_processing_queue_error(self, video_id: str, exc: Exception) -> None:
        if not video_id or video_id in self._deleted_video_ids:
            return
        video = video_store.get_video(video_id)
        if not video:
            return
        message = f"Processing queue recovered from an internal error: {exc}"
        video_store.log_to_video(video_id, message)
        video_store.update_video(video_id, status="failed", error=str(exc), step="failed", step_detail=message)

    def _execute_pipeline(self, video_id):
        video = video_store.get_video(video_id)
        if not video or video.status == "cancelled" or video_id in self._deleted_video_ids:
            return
        try:
            if not self._initial_model_warmup_done.is_set():
                video_store.log_to_video(video_id, "Waiting for startup model warm-up to finish.")
                self._initial_model_warmup_done.wait()
            if getattr(self, "_shutdown_started", False):
                return
            runtime_probe_error = getattr(self, "_runtime_probe_error", "")
            if runtime_probe_error:
                raise RuntimeError(f"Model runtime validation failed: {runtime_probe_error}")
            # A device switch owns this lock. Crossing the barrier guarantees
            # that model processes are stable before the pipeline uses them.
            with self._model_runtime_lock:
                pass
            from haizflow.pipeline.process_video import process_video_sync

            process_video_sync(video_id)
        except Exception as exc:
            if video_id not in self._deleted_video_ids:
                message = f"Desktop worker failed before pipeline could start: {exc}"
                video_store.log_to_video(video_id, message)
                video_store.update_video(video_id, status="failed", error=str(exc), step="failed")

    @staticmethod
    def _prepare_batch_models(video_id):
        profile = runtime_profile()
        video_store.log_to_video(video_id, f"Preparing shared models for batch profile: {profile.summary}.")
        try:
            if profile.warm_hymt2_on_startup:
                warm_hymt2_worker(lambda detail: video_store.log_to_video(video_id, detail))
            if profile.warm_whisper_on_startup:
                from haizflow.pipeline.transcribe import warm_whisperx_model

                warm_whisperx_model()
            video_store.log_to_video(
                video_id,
                "Shared models are ready for the batch.",
            )
        except Exception as exc:
            # The video pipeline can retry initialization at the point of use.
            video_store.log_to_video(video_id, f"Batch model preparation deferred: {exc}")

    def _on_video_log(self, video_id, line):
        if video_id == self._selected_video_id:
            self._log_queue.put(("video_log", video_id, line))

    def _drain_log_queue(self):
        changed = False
        while True:
            try:
                item = self._log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and len(item) == 3 and item[0] == "video_log":
                _kind, video_id, line = item
                if video_id == self._selected_video_id:
                    self._logs = f"{self._logs}\n{line}".strip()
                    changed = True
            elif item.startswith("__QUEUE_STARTED__:"):
                self.refreshVideos()
                self.selectedVideoChanged.emit()
                self.processingChanged.emit()
                self._refresh_batch_model()
                self.batchChanged.emit()
            elif item.startswith("__QUEUE_FINISHED__:"):
                self.refreshVideos()
                self.selectedVideoChanged.emit()
                self._refresh_batch_model()
                self.batchChanged.emit()
            elif item == "__QUEUE_IDLE__":
                if self._processing_queue.has_work:
                    continue
                self._batch_running = False
                self._batch_stop_requested = False
                self.refreshVideos()
                self.processingChanged.emit()
                self.batchChanged.emit()
            elif item == "__QUEUE_CHANGED__":
                self.refreshVideos()
                self.selectedVideoChanged.emit()
                self.batchChanged.emit()
            elif item == "__THUMBNAILS_READY__":
                self._thumbnail_refresh_running = False
                self.refreshVideos()
        if changed:
            self.logsChanged.emit()

    def _read_video_logs(self, video_id):
        path = video_store.get_video_logs_path(video_id)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as file:
            return file.read()

    def _refresh_batch_model(self):
        videos = []
        valid_ids = []
        for video_id in self._batch_video_ids:
            video = video_store.get_video(video_id)
            if video:
                video = self._ensure_video_dimensions(video)
                valid_ids.append(video_id)
                videos.append(video)
        self._batch_video_ids = valid_ids
        self.batch_videos.set_videos(videos)

    def _ensure_video_dimensions(self, video):
        if video.video_width > 0 and video.video_height > 0:
            return video
        video_path = self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
        try:
            width, height = get_video_dimensions(video_path)
        except RuntimeError:
            return video
        return video_store.update_video(video.video_id, video_width=width, video_height=height) or video

    def _batch_dimension_groups(self):
        grouped = {}
        for video_id in self._batch_video_ids:
            video = video_store.get_video(video_id)
            if not video:
                continue
            video = self._ensure_video_dimensions(video)
            if video.video_width > 0 and video.video_height > 0:
                size_key = f"{video.video_width}x{video.video_height}"
                label = f"{video.video_width} x {video.video_height}"
            else:
                size_key = f"unknown:{video.video_id}"
                label = "Unknown size"
            group = grouped.setdefault(size_key, {"size_key": size_key, "label": label, "videos": []})
            group["videos"].append(video)
        return sorted(
            grouped.values(),
            key=lambda group: (
                -(group["videos"][0].video_width * group["videos"][0].video_height),
                group["label"],
            ),
        )

    def _batch_dimension_group(self, size_key):
        return next((group for group in self._batch_dimension_groups() if group["size_key"] == size_key), None)

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
        self._subtitle_position_x = video.subtitle_style.position_x_percent
        self._subtitle_position_y = video.subtitle_style.position_y_percent
        self._caption_font_size = video.subtitle_style.font_size
        self._subtitle_box_width = video.subtitle_style.box_width_percent
        self._subtitle_box_height = video.subtitle_style.box_height_percent
        self.previewChanged.emit()

    @staticmethod
    def _copy_subtitle_style(style):
        data = style.model_dump() if hasattr(style, "model_dump") else style.dict()
        return SubtitleStyle(**data)

    def _current_subtitle_style(self, base=None):
        base = base or SubtitleStyle()
        return SubtitleStyle(
            font_size=self._caption_font_size,
            margin_bottom=base.margin_bottom,
            outline=base.outline,
            max_chars_per_line=base.max_chars_per_line,
            position_x_percent=self._subtitle_position_x,
            position_y_percent=self._subtitle_position_y,
            box_width_percent=self._subtitle_box_width,
            box_height_percent=self._subtitle_box_height,
        )

    def _set_preview_style(self, style):
        self._subtitle_position_x = style.position_x_percent
        self._subtitle_position_y = style.position_y_percent
        self._caption_font_size = style.font_size
        self._subtitle_box_width = style.box_width_percent
        self._subtitle_box_height = style.box_height_percent

    def _open_batch_group_preview(self, size_key):
        group = self._batch_dimension_group(size_key)
        if not group:
            self._clear_preview_edit_session()
            return
        representative = group["videos"][0]
        video_path = self._resolve_video_file(representative, ("video_input", "input_video"), ("input", "video.mp4"))
        self._preview_edit_scope = "size_group"
        self._preview_target_video_ids = [video.video_id for video in group["videos"]]
        self._preview_original_style = self._copy_subtitle_style(representative.subtitle_style)
        self._set_preview_style(representative.subtitle_style)
        index_label = f"{self._preview_group_index + 1}/{len(self._preview_group_keys)}"
        title = f"{group['label']} | {index_label}"
        self._open_preview(video_path, title, True)

    def _clear_preview_edit_session(self):
        self._preview_edit_scope = "draft"
        self._preview_target_video_ids = []
        self._preview_group_keys = []
        self._preview_group_index = -1
        self._preview_original_style = None

    def _apply_preview_edits(self, subtitle_x, subtitle_y, box_width, box_height, font_size):
        self._subtitle_position_x = max(0, min(100, int(subtitle_x)))
        self._subtitle_position_y = max(0, min(100, int(subtitle_y)))
        self._subtitle_box_width = max(20, min(95, int(box_width)))
        self._subtitle_box_height = max(6, min(35, int(box_height)))
        self._caption_font_size = max(10, min(160, int(font_size)))

    def _open_preview(self, path: str, title: str, interactive: bool):
        self._preview_title = title
        self._preview_interactive = interactive
        self._preview_source = QUrl.fromLocalFile(path).toString()
        selected_video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        thumbnail_path = (selected_video.files or {}).get("thumbnail", "") if selected_video else ""
        if not os.path.exists(thumbnail_path):
            thumbnail_path = self._video_thumbnail_path(selected_video.video_id) if selected_video else self._draft_thumbnail_path()
            thumbnail_path = self._create_video_thumbnail_path(path, thumbnail_path)
            if selected_video and thumbnail_path:
                selected_video.files["thumbnail"] = thumbnail_path
                video_store.save_video(selected_video)
        poster_source = thumbnail_source(thumbnail_path)
        self._preview_poster_source = poster_source or self._video_thumbnail_source
        self._preview_aspect_ratio = 16 / 9
        try:
            width, height = get_video_dimensions(path)
            if width > 0 and height > 0:
                self._preview_aspect_ratio = width / height
        except RuntimeError:
            pass
        self.previewChanged.emit()
        self.previewOpenRequested.emit()

    def _draft_thumbnail_path(self) -> str:
        if not self.hasOpenProject:
            return ""
        return os.path.join(
            self._selected_project_root(),
            ".input-thumbnail.jpg",
        )

    @staticmethod
    def _video_thumbnail_path(video_id: str) -> str:
        return os.path.join(video_store.get_video_dir(video_id), "thumbnail.jpg")

    def _assign_project_thumbnail(self, video) -> None:
        thumbnail_path = self._create_video_thumbnail_path(
            video.files["video_input"],
            self._video_thumbnail_path(video.video_id),
        )
        if thumbnail_path:
            video.files["thumbnail"] = thumbnail_path
            video_store.save_video(video)
        draft_thumbnail = self._draft_thumbnail_path()
        if draft_thumbnail and os.path.isfile(draft_thumbnail):
            try:
                os.remove(draft_thumbnail)
            except OSError:
                pass

    @staticmethod
    def _create_video_thumbnail(path: str, output_path: str = "") -> str:
        output_path = HaizFlowController._create_video_thumbnail_path(path, output_path)
        return thumbnail_source(output_path)

    _create_video_thumbnail_path = staticmethod(create_video_thumbnail_path)

    def _migrate_legacy_project_thumbnails(self) -> None:
        legacy_directory = os.path.join(RUNTIME_DATA_DIR, "cache", "thumbnails")
        video_store.migrate_legacy_thumbnails(legacy_directory)
        for video in video_store.list_videos():
            expected_path = self._video_thumbnail_path(video.video_id)
            changed = False
            if not os.path.exists(expected_path):
                source_path = self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
                created_path = self._create_video_thumbnail_path(source_path, expected_path)
                if created_path:
                    video.files["thumbnail"] = created_path
                    changed = True
            if changed:
                video_store.save_video(video)
        if os.path.isdir(legacy_directory):
            try:
                shutil.rmtree(legacy_directory)
            except OSError:
                pass

    _open_path = staticmethod(open_path)
