import os
import json
import shutil
import queue
import threading
import hashlib
from collections import Counter
from datetime import datetime, timezone

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Property, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

from autodub.config import (
    CACHE_DIR,
    RUNTIME_DATA_DIR,
)
from autodub.core.events import subscribe_log, unsubscribe_log
from autodub.pipeline.job_manager import cancel_job, pause_job
from autodub.schemas.job import CropSettings, JobConfig, SubtitleStyle
from autodub.services import job_store
from autodub.services.desktop_jobs import SUPPORTED_VIDEO_EXTENSIONS, create_desktop_job
from autodub.services.translation import shutdown_hymt2_worker, warm_hymt2_worker
from autodub.services import desktop_settings
from autodub.utils.ffmpeg import get_video_dimensions
from autodub.pipeline.transcribe import release_warm_whisperx_model, warm_whisperx_model


POPULAR_TARGET_LANGUAGES = [
    ("vi", "Vietnamese", "Tiếng Việt"),
    ("en", "English", "English"),
    ("zh", "Chinese", "中文"),
    ("hi", "Hindi", "हिन्दी"),
    ("es", "Spanish", "Español"),
    ("fr", "French", "Français"),
    ("ar", "Arabic", "العربية"),
    ("pt", "Portuguese", "Português"),
    ("ru", "Russian", "Русский"),
    ("id", "Indonesian", "Bahasa Indonesia"),
    ("de", "German", "Deutsch"),
    ("ja", "Japanese", "日本語"),
    ("ko", "Korean", "한국어"),
    ("it", "Italian", "Italiano"),
    ("th", "Thai", "ไทย"),
    ("fil", "Filipino", "Filipino"),
]


EDGE_TTS_VOICES_BY_LANGUAGE = {
    "vi": [("vi-VN-HoaiMyNeural", "Hoai My - Female"), ("vi-VN-NamMinhNeural", "Nam Minh - Male")],
    "en": [("en-US-JennyNeural", "Jenny - Female"), ("en-US-GuyNeural", "Guy - Male")],
    "zh": [("zh-CN-XiaoxiaoNeural", "Xiaoxiao - Female"), ("zh-CN-YunxiNeural", "Yunxi - Male")],
    "hi": [("hi-IN-SwaraNeural", "Swara - Female"), ("hi-IN-MadhurNeural", "Madhur - Male")],
    "es": [("es-ES-ElviraNeural", "Elvira - Female"), ("es-ES-AlvaroNeural", "Alvaro - Male")],
    "fr": [("fr-FR-DeniseNeural", "Denise - Female"), ("fr-FR-HenriNeural", "Henri - Male")],
    "ar": [("ar-SA-ZariyahNeural", "Zariyah - Female"), ("ar-SA-HamedNeural", "Hamed - Male")],
    "bn": [("bn-BD-NabanitaNeural", "Nabanita - Female"), ("bn-BD-PradeepNeural", "Pradeep - Male")],
    "pt": [("pt-BR-FranciscaNeural", "Francisca - Female"), ("pt-BR-AntonioNeural", "Antonio - Male")],
    "ru": [("ru-RU-SvetlanaNeural", "Svetlana - Female"), ("ru-RU-DmitryNeural", "Dmitry - Male")],
    "ur": [("ur-PK-UzmaNeural", "Uzma - Female"), ("ur-PK-AsadNeural", "Asad - Male")],
    "id": [("id-ID-GadisNeural", "Gadis - Female"), ("id-ID-ArdiNeural", "Ardi - Male")],
    "de": [("de-DE-KatjaNeural", "Katja - Female"), ("de-DE-ConradNeural", "Conrad - Male")],
    "ja": [("ja-JP-NanamiNeural", "Nanami - Female"), ("ja-JP-KeitaNeural", "Keita - Male")],
    "sw": [("sw-KE-ZuriNeural", "Zuri - Female"), ("sw-KE-RafikiNeural", "Rafiki - Male")],
    "mr": [("mr-IN-AarohiNeural", "Aarohi - Female"), ("mr-IN-ManoharNeural", "Manohar - Male")],
    "te": [("te-IN-ShrutiNeural", "Shruti - Female"), ("te-IN-MohanNeural", "Mohan - Male")],
    "tr": [("tr-TR-EmelNeural", "Emel - Female"), ("tr-TR-AhmetNeural", "Ahmet - Male")],
    "ta": [("ta-IN-PallaviNeural", "Pallavi - Female"), ("ta-IN-ValluvarNeural", "Valluvar - Male")],
    "ko": [("ko-KR-SunHiNeural", "SunHi - Female"), ("ko-KR-InJoonNeural", "InJoon - Male")],
    "it": [("it-IT-ElsaNeural", "Elsa - Female"), ("it-IT-DiegoNeural", "Diego - Male")],
    "th": [("th-TH-PremwadeeNeural", "Premwadee - Female"), ("th-TH-NiwatNeural", "Niwat - Male")],
    "gu": [("gu-IN-DhwaniNeural", "Dhwani - Female"), ("gu-IN-NiranjanNeural", "Niranjan - Male")],
    "pl": [("pl-PL-ZofiaNeural", "Zofia - Female"), ("pl-PL-MarekNeural", "Marek - Male")],
    "uk": [("uk-UA-PolinaNeural", "Polina - Female"), ("uk-UA-OstapNeural", "Ostap - Male")],
    "fa": [("fa-IR-DilaraNeural", "Dilara - Female"), ("fa-IR-FaridNeural", "Farid - Male")],
    "ms": [("ms-MY-YasminNeural", "Yasmin - Female"), ("ms-MY-OsmanNeural", "Osman - Male")],
    "nl": [("nl-NL-FennaNeural", "Fenna - Female"), ("nl-NL-MaartenNeural", "Maarten - Male")],
    "ro": [("ro-RO-AlinaNeural", "Alina - Female"), ("ro-RO-EmilNeural", "Emil - Male")],
    "el": [("el-GR-AthinaNeural", "Athina - Female"), ("el-GR-NestorasNeural", "Nestoras - Male")],
    "cs": [("cs-CZ-VlastaNeural", "Vlasta - Female"), ("cs-CZ-AntoninNeural", "Antonin - Male")],
    "hu": [("hu-HU-NoemiNeural", "Noemi - Female"), ("hu-HU-TamasNeural", "Tamas - Male")],
    "sv": [("sv-SE-SofieNeural", "Sofie - Female"), ("sv-SE-MattiasNeural", "Mattias - Male")],
    "he": [("he-IL-HilaNeural", "Hila - Female"), ("he-IL-AvriNeural", "Avri - Male")],
    "fil": [("fil-PH-BlessicaNeural", "Blessica - Female"), ("fil-PH-AngeloNeural", "Angelo - Male")],
    "my": [("my-MM-NilarNeural", "Nilar - Female"), ("my-MM-ThihaNeural", "Thiha - Male")],
    "km": [("km-KH-SreymomNeural", "Sreymom - Female"), ("km-KH-PisethNeural", "Piseth - Male")],
    "lo": [("lo-LA-KeomanyNeural", "Keomany - Female"), ("lo-LA-ChanthavongNeural", "Chanthavong - Male")],
}

class JobListModel(QAbstractListModel):
    JobIdRole = Qt.ItemDataRole.UserRole + 1
    FileRole = Qt.ItemDataRole.UserRole + 2
    ModeRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    StepRole = Qt.ItemDataRole.UserRole + 5
    UpdatedRole = Qt.ItemDataRole.UserRole + 6
    ProgressRole = Qt.ItemDataRole.UserRole + 7
    ThumbnailRole = Qt.ItemDataRole.UserRole + 8
    ProjectNameRole = Qt.ItemDataRole.UserRole + 9
    VideoSizeRole = Qt.ItemDataRole.UserRole + 10
    SubtitleOverrideRole = Qt.ItemDataRole.UserRole + 11

    def __init__(self):
        super().__init__()
        self._jobs = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._jobs)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._jobs):
            return None
        job = self._jobs[index.row()]
        return {
            self.JobIdRole: job.job_id,
            self.FileRole: job.original_filename,
            self.ModeRole: "Full Auto",
            self.StatusRole: job.status,
            self.StepRole: job.step,
            self.UpdatedRole: job.updated_at,
            self.ProgressRole: job.progress,
            self.ThumbnailRole: self._thumbnail_source(job),
            self.ProjectNameRole: job.project_name or job.original_filename,
            self.VideoSizeRole: self._video_size(job),
            self.SubtitleOverrideRole: bool(getattr(job, "subtitle_override", False)),
        }.get(role)

    def roleNames(self):
        return {
            self.JobIdRole: b"jobId",
            self.FileRole: b"fileName",
            self.ModeRole: b"mode",
            self.StatusRole: b"status",
            self.StepRole: b"step",
            self.UpdatedRole: b"updatedAt",
            self.ProgressRole: b"progress",
            self.ThumbnailRole: b"thumbnailSource",
            self.ProjectNameRole: b"projectName",
            self.VideoSizeRole: b"videoSize",
            self.SubtitleOverrideRole: b"subtitleOverride",
        }

    def set_jobs(self, jobs):
        current_ids = [job.job_id for job in self._jobs]
        next_ids = [job.job_id for job in jobs]
        if current_ids == next_ids:
            self._jobs = jobs
            if jobs:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(jobs) - 1, 0),
                    list(self.roleNames().keys()),
                )
            return
        self.beginResetModel()
        self._jobs = jobs
        self.endResetModel()

    def job_at(self, row: int):
        if row < 0 or row >= len(self._jobs):
            return None
        return self._jobs[row]

    @staticmethod
    def _thumbnail_source(job):
        path = job.files.get("thumbnail") if job else ""
        return QUrl.fromLocalFile(path).toString() if path and os.path.exists(path) else ""

    @staticmethod
    def _video_size(job):
        width = int(getattr(job, "video_width", 0) or 0)
        height = int(getattr(job, "video_height", 0) or 0)
        return f"{width} x {height}" if width and height else "Unknown size"


class ProjectListModel(QAbstractListModel):
    ProjectNameRole = Qt.ItemDataRole.UserRole + 1
    ProjectTypeRole = Qt.ItemDataRole.UserRole + 2
    JobCountRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    ThumbnailRole = Qt.ItemDataRole.UserRole + 6

    def __init__(self):
        super().__init__()
        self._projects = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._projects)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._projects):
            return None
        project = self._projects[index.row()]
        return {
            self.ProjectNameRole: project["project_name"],
            self.ProjectTypeRole: project["project_type"],
            self.JobCountRole: project["job_count"],
            self.StatusRole: project["status"],
            self.ProgressRole: project["progress"],
            self.ThumbnailRole: project["thumbnail_source"],
        }.get(role)

    def roleNames(self):
        return {
            self.ProjectNameRole: b"projectName",
            self.ProjectTypeRole: b"projectType",
            self.JobCountRole: b"jobCount",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.ThumbnailRole: b"thumbnailSource",
        }

    def set_projects(self, projects):
        next_keys = [project["key"] for project in projects]
        current_keys = [project["key"] for project in self._projects]
        if current_keys == next_keys:
            self._projects = projects
            if projects:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(projects) - 1, 0),
                    list(self.roleNames().keys()),
                )
            return
        self.beginResetModel()
        self._projects = projects
        self.endResetModel()

    def project_at(self, row: int):
        if row < 0 or row >= len(self._projects):
            return None
        return self._projects[row]


class TaskListModel(QAbstractListModel):
    NameRole = Qt.ItemDataRole.UserRole + 1
    KeyRole = Qt.ItemDataRole.UserRole + 2
    StateRole = Qt.ItemDataRole.UserRole + 3
    DetailRole = Qt.ItemDataRole.UserRole + 4

    STEPS = [
        ("starting", "Prepare job"),
        ("extracting_audio", "Extract audio"),
        ("separating_audio", "Separate vocals"),
        ("transcribing", "Transcribe speech"),
        ("translating", "Translate segments"),
        ("creating_subtitle", "Build subtitles"),
        ("creating_voice", "Generate voice"),
        ("building_audio_timeline", "Mix audio timeline"),
        ("rendering", "Render final video"),
        ("done", "Finish"),
    ]

    def __init__(self):
        super().__init__()
        self._tasks = self._build_tasks(None)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._tasks)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._tasks):
            return None
        task = self._tasks[index.row()]
        return {
            self.NameRole: task["name"],
            self.KeyRole: task["key"],
            self.StateRole: task["state"],
            self.DetailRole: task["detail"],
        }.get(role)

    def roleNames(self):
        return {
            self.NameRole: b"name",
            self.KeyRole: b"key",
            self.StateRole: b"taskState",
            self.DetailRole: b"detail",
        }

    def set_job(self, job):
        self.beginResetModel()
        self._tasks = self._build_tasks(job)
        self.endResetModel()

    def _build_tasks(self, job):
        current_step = job.step if job else "pending"
        status = job.status if job else "pending"
        step_keys = [key for key, _name in self.STEPS]
        current_index = step_keys.index(current_step) if current_step in step_keys else -1
        tasks = []
        for index, (key, name) in enumerate(self.STEPS):
            if not job:
                state = "pending"
            elif status == "done":
                state = "done"
            elif status in {"failed", "cancelled"} and (key == current_step or index == max(current_index, 0)):
                state = status
            elif index < current_index:
                state = "done"
            elif index == current_index and status == "processing":
                state = "active"
            else:
                state = "pending"
            tasks.append({"key": key, "name": name, "state": state, "detail": key.replace("_", " ")})
        return tasks


class AutoDubController(QObject):
    videoPathChanged = Signal()
    videoThumbnailChanged = Signal()
    targetLanguageChanged = Signal()
    ttsVoiceChanged = Signal()
    enableAudioSeparationChanged = Signal()
    originalVolumeChanged = Signal()
    workflowModeChanged = Signal()
    selectedJobChanged = Signal()
    processingChanged = Signal()
    logsChanged = Signal()
    statusMessageChanged = Signal()
    previewChanged = Signal()
    previewOpenRequested = Signal()
    jobDeleted = Signal()
    batchDeleted = Signal()
    batchChanged = Signal()
    settingsChanged = Signal()
    projectSetupChanged = Signal()
    projectPrepared = Signal()

    def __init__(self):
        super().__init__()
        self.jobs = JobListModel()
        self.projects = ProjectListModel()
        self.batch_jobs = JobListModel()
        self.tasks = TaskListModel()
        self._video_path = ""
        self._video_thumbnail_source = ""
        self._target_language = "vi"
        self._tts_voice = "vi-VN-HoaiMyNeural"
        self._enable_audio_separation = False
        self._original_volume = 60
        self._workflow_mode = "A"
        self._selected_job_id = None
        self._processing_job_id = None
        self._is_processing = False
        self._deleted_job_ids = set()
        self._batch_job_ids = []
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
        self._preview_target_job_ids = []
        self._preview_group_keys = []
        self._preview_group_index = -1
        self._preview_original_style = None
        settings = desktop_settings.load_settings()
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        self._project_directory = os.path.join(RUNTIME_DATA_DIR, "projects")
        self._project_name = ""
        self._project_type = "single"
        self._log_queue = queue.Queue()
        self._thumbnail_refresh_running = False

        threading.Thread(target=self._warm_models, daemon=True).start()

        subscribe_log(self._on_job_log)
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._drain_log_queue)
        self._log_timer.start(250)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.poll_jobs)
        self._status_timer.start(1000)

        self.refreshJobs()

    def shutdown(self):
        unsubscribe_log(self._on_job_log)
        shutdown_hymt2_worker()
        release_warm_whisperx_model()

    def _warm_models(self):
        try:
            warm_whisperx_model()
            self._status_message = "WhisperX model ready"
            self.statusMessageChanged.emit()
            warm_hymt2_worker(self._set_warmup_status)
            self._status_message = "WhisperX and HY-MT2 models ready"
        except Exception as exc:
            self._status_message = f"Model warm-up unavailable: {exc}"
        self.statusMessageChanged.emit()

    def _set_warmup_status(self, detail: str):
        self._status_message = detail
        self.statusMessageChanged.emit()

    @Property(QObject, constant=True)
    def jobModel(self):
        return self.jobs

    @Property(QObject, constant=True)
    def projectModel(self):
        return self.projects

    @Property(QObject, constant=True)
    def batchJobModel(self):
        return self.batch_jobs

    @Property(bool, notify=batchChanged)
    def isBatchRunning(self):
        return self._batch_running

    @Property(int, notify=batchChanged)
    def batchCount(self):
        return len(self._batch_job_ids)

    @Property(int, notify=batchChanged)
    def batchCompletedCount(self):
        completed_states = {"done", "failed", "cancelled"}
        jobs = [job_store.get_job(job_id) for job_id in self._batch_job_ids]
        return sum(1 for job in jobs if job and job.status in completed_states)

    @Property(int, notify=batchChanged)
    def batchPendingCount(self):
        jobs = [job_store.get_job(job_id) for job_id in self._batch_job_ids]
        return sum(1 for job in jobs if job and job.status == "pending")

    @Property(int, notify=batchChanged)
    def batchProgress(self):
        jobs = [job_store.get_job(job_id) for job_id in self._batch_job_ids]
        jobs = [job for job in jobs if job]
        return round(sum(job.progress for job in jobs) / len(jobs)) if jobs else 0

    @Property(str, notify=batchChanged)
    def batchTargetLanguageLabel(self):
        if not self._batch_job_ids:
            return self._language_label(self._target_language)
        jobs = [job_store.get_job(job_id) for job_id in self._batch_job_ids]
        languages = {job.target_language for job in jobs if job}
        if len(languages) > 1:
            return "Mixed settings"
        return self._language_label(next(iter(languages))) if languages else self._language_label(self._target_language)

    @Property("QVariantList", notify=batchChanged)
    def batchVideoSizeGroups(self):
        return [
            {
                "sizeKey": group["size_key"],
                "label": group["label"],
                "count": len(group["jobs"]),
                "customizedCount": sum(1 for job in group["jobs"] if job.subtitle_override),
                "thumbnailSource": JobListModel._thumbnail_source(group["jobs"][0]),
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
        if self._video_path != value:
            self._video_path = value
            self._video_thumbnail_source = self._create_video_thumbnail(value)
            self.videoPathChanged.emit()
            self.videoThumbnailChanged.emit()

    @Property(str, notify=videoThumbnailChanged)
    def videoThumbnailSource(self):
        return self._video_thumbnail_source

    @Property("QVariantList", constant=True)
    def targetLanguageOptions(self):
        return [
            {
                "code": code,
                "englishName": english_name,
                "nativeName": native_name,
                "label": f"{native_name} - {english_name} ({code})",
                "search": f"{code} {english_name} {native_name}".lower(),
            }
            for code, english_name, native_name in POPULAR_TARGET_LANGUAGES
        ]

    @Property(str, notify=targetLanguageChanged)
    def targetLanguage(self):
        return self._target_language

    @targetLanguage.setter
    def targetLanguage(self, value):
        if self._target_language != value:
            self._target_language = value
            if self._tts_voice not in self._voice_codes_for_language(value):
                self._tts_voice = self._voice_options_for_language(value)[0]["voice"]
                self.ttsVoiceChanged.emit()
            self.targetLanguageChanged.emit()

    @Property(str, notify=targetLanguageChanged)
    def targetLanguageLabel(self):
        return self._language_label(self._target_language)

    @Property(str, notify=ttsVoiceChanged)
    def ttsVoice(self):
        return self._tts_voice

    @ttsVoice.setter
    def ttsVoice(self, value):
        if self._tts_voice != value:
            self._tts_voice = value
            self.ttsVoiceChanged.emit()

    @Property("QVariantList", notify=targetLanguageChanged)
    def ttsVoiceOptions(self):
        return self._voice_options_for_language(self._target_language)

    @Property(int, notify=ttsVoiceChanged)
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
        return self._is_processing

    @Property(bool, notify=processingChanged)
    def isSelectedJobProcessing(self):
        if not self._selected_job_id or self._selected_job_id != self._processing_job_id:
            return False
        job = job_store.get_job(self._selected_job_id)
        return bool(job and job.status == "processing")

    @Property(str, notify=processingChanged)
    def processingText(self):
        job = job_store.get_job(self._processing_job_id) if self._processing_job_id else None
        return f"{job.original_filename} | {job.step_detail or job.status}" if job else "No active job"

    @Property(str, notify=selectedJobChanged)
    def selectedTitle(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return f"{job.original_filename} | {job.status}" if job else "No job selected"

    @Property(bool, notify=selectedJobChanged)
    def hasSelectedJob(self):
        return self._selected_job_id is not None and job_store.get_job(self._selected_job_id) is not None

    @Property(bool, notify=selectedJobChanged)
    def isSelectedBatchJob(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return bool(job and job.project_type == "batch" and job.job_id in self._batch_job_ids)

    @Property("QVariantList", notify=selectedJobChanged)
    def reviewSegments(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job or job.status != "awaiting_review":
            return []
        try:
            with open(job.files["transcript_json"], "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return []

    @Property(str, notify=selectedJobChanged)
    def selectedFileName(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.original_filename if job else ""

    @Property(str, notify=selectedJobChanged)
    def selectedStatus(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.status if job else "none"

    @Property(str, notify=selectedJobChanged)
    def selectedStep(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.step_detail or job.step if job else "pending"

    @Property(int, notify=selectedJobChanged)
    def selectedProgress(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.progress if job else 0

    @Property(str, notify=selectedJobChanged)
    def selectedStageLabel(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job:
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
        return labels.get(job.step, job.step_detail or job.status)

    @Property(str, notify=selectedJobChanged)
    def selectedProgressDetail(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job:
            return ""
        item_detail = f"{job.current_item}/{job.total_items}" if job.total_items else ""
        return " | ".join(part for part in (job.step_detail, item_detail) if part)

    @Property(str, notify=selectedJobChanged)
    def selectedElapsed(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job or not job.started_at:
            return ""
        try:
            started_at = datetime.fromisoformat(job.started_at.replace("Z", "+00:00"))
            if job.status == "processing":
                seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            else:
                finished_at = datetime.fromisoformat(job.updated_at.replace("Z", "+00:00"))
                seconds = (finished_at - started_at).total_seconds()
            return self._format_duration(max(0, seconds))
        except ValueError:
            return ""

    @Property(str, notify=selectedJobChanged)
    def selectedUpdatedAt(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.updated_at if job else ""

    @Property(str, notify=selectedJobChanged)
    def selectedOutputFormat(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.output_format if job else ""

    @Property(str, notify=selectedJobChanged)
    def selectedTargetLanguageLabel(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return self._language_label(job.target_language) if job else ""

    @Property(str, notify=selectedJobChanged)
    def selectedTranslatorProvider(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.translator_provider if job else ""

    @Property(str, notify=selectedJobChanged)
    def selectedInputPath(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return self._resolve_job_file(job, ("video_input", "input_video"), ("input", "video.mp4"))

    @Property(str, notify=selectedJobChanged)
    def selectedOutputPath(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return self._resolve_job_file(job, ("final_video", "output_video"), ("output", "final.mp4"))

    @Property(str, notify=selectedJobChanged)
    def selectedSrtPath(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return self._resolve_job_file(job, ("srt_output", "subtitle_output"), ("temp", "vi.srt"))

    @Property(str, notify=selectedJobChanged)
    def selectedVoicePath(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return self._resolve_job_file(job, ("voice_output", "dubbed_audio"), ("temp", "voice_final.wav"))

    @Property(str, notify=selectedJobChanged)
    def selectedLogsPath(self):
        return job_store.get_job_logs_path(self._selected_job_id) if self._selected_job_id else ""

    @Property(str, notify=logsChanged)
    def logs(self):
        return self._logs

    @Property(str, notify=statusMessageChanged)
    def statusMessage(self):
        return self._status_message

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
    def browseVideo(self):
        path, _ = QFileDialog.getOpenFileName(None, "Choose input video", "", "Video files (*.mp4 *.mov *.mkv);;All files (*.*)")
        if path:
            if self._selected_job_id:
                self.replaceSelectedJobVideo(path)
            else:
                self.importVideo(path)

    @Slot(str)
    def replaceSelectedJobVideo(self, path):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        normalized_path = self._normalize_video_path(path)
        if not job or self._is_processing:
            return
        if not os.path.isfile(normalized_path) or os.path.splitext(normalized_path)[1].lower() not in {".mp4", ".mov", ".mkv"}:
            QMessageBox.warning(None, "Invalid video", "Choose an MP4, MOV, or MKV video file.")
            return
        destination = job.files["video_input"]
        shutil.copy2(normalized_path, destination)
        job.original_filename = os.path.basename(normalized_path)
        try:
            job.video_width, job.video_height = get_video_dimensions(destination)
        except RuntimeError:
            job.video_width, job.video_height = 0, 0
        job.subtitle_override = True
        thumbnail_path = self._create_video_thumbnail_path(destination)
        if thumbnail_path:
            job.files["thumbnail"] = thumbnail_path
        job_store.save_job(job)
        self.videoPath = destination
        self._logs = self._read_job_logs(job.job_id)
        job_store.log_to_job(job.job_id, f"Input video replaced with: {job.original_filename}")
        self.videoThumbnailChanged.emit()
        self.selectedJobChanged.emit()
        self.logsChanged.emit()

    @Slot()
    def browseProjectDirectory(self):
        os.makedirs(self._project_directory, exist_ok=True)
        path = QFileDialog.getExistingDirectory(None, "Choose project folder", self._project_directory)
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
            QMessageBox.warning(None, "Project folder", "Choose a project folder.")
            return False
        self._project_name = project_name
        self._project_directory = os.path.abspath(project_directory)
        self._project_type = "batch" if project_type == "batch" else "single"
        self.videoPath = ""
        self._selected_job_id = None
        self._batch_job_ids = []
        self._refresh_batch_model()
        self._logs = ""
        self.tasks.set_job(None)
        self.projectSetupChanged.emit()
        self.selectedJobChanged.emit()
        self.logsChanged.emit()
        self.projectPrepared.emit()
        return True

    @Slot(str, str)
    def applySettings(self, theme, language):
        try:
            settings = desktop_settings.save_settings(
                {
                    "theme": theme,
                    "language": language,
                }
            )
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot use this output folder: {exc}")
            return
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        self._status_message = "Settings applied"
        self.settingsChanged.emit()
        self.statusMessageChanged.emit()

    @Slot()
    def resetSettings(self):
        try:
            settings = desktop_settings.reset_settings()
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot restore defaults: {exc}")
            return
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        self._status_message = "Settings reset to defaults"
        self.settingsChanged.emit()
        self.statusMessageChanged.emit()

    @Slot(str)
    def importVideo(self, path):
        normalized_path = self._normalize_video_path(path)
        if not os.path.isfile(normalized_path):
            QMessageBox.warning(None, "Invalid video", "The dropped file is unavailable.")
            return
        if os.path.splitext(normalized_path)[1].lower() not in {".mp4", ".mov", ".mkv"}:
            QMessageBox.warning(None, "Unsupported file", "Choose an MP4, MOV, or MKV video file.")
            return
        self.videoPath = normalized_path
        self._selected_job_id = None
        self.tasks.set_job(None)
        self.selectedJobChanged.emit()

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
        if self._batch_running:
            QMessageBox.information(None, "Batch running", "Stop the current batch before adding more videos.")
            return

        valid_paths, invalid_names = self._collect_batch_video_paths(paths)

        if not valid_paths:
            QMessageBox.warning(None, "No supported videos", "Choose MP4, MOV, or MKV video files.")
            return

        created_ids = []
        errors = []
        for path in valid_paths:
            try:
                job = create_desktop_job(
                    path,
                    self._build_config(),
                    project_name=self._project_name,
                    project_directory=self._project_directory,
                )
                thumbnail_path = self._create_video_thumbnail_path(job.files["video_input"])
                if thumbnail_path:
                    job.files["thumbnail"] = thumbnail_path
                    job_store.save_job(job)
                created_ids.append(job.job_id)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")

        self._batch_job_ids.extend(created_ids)
        self._refresh_batch_model()
        self.refreshJobs()
        self.batchChanged.emit()

        rejected = invalid_names + errors
        if rejected:
            QMessageBox.warning(
                None,
                "Some videos were skipped",
                "\n".join(str(item) for item in rejected[:12]),
            )

    @Slot()
    def startBatch(self):
        if self._is_processing:
            QMessageBox.warning(None, "Processing active", "Another job is already processing.")
            return
        pending_ids = []
        for job_id in self._batch_job_ids:
            job = job_store.get_job(job_id)
            if job and job.status == "pending":
                pending_ids.append(job_id)
        if not pending_ids:
            QMessageBox.information(None, "Batch queue", "Add at least one video to the queue.")
            return

        self._batch_running = True
        self._batch_stop_requested = False
        self._is_processing = True
        self.batchChanged.emit()
        self.processingChanged.emit()
        threading.Thread(target=self._run_batch_queue, args=(pending_ids,), daemon=True).start()

    @Slot(result=bool)
    def applyBatchSettings(self):
        if self._batch_running or self._is_processing:
            QMessageBox.information(None, "Batch settings", "Stop processing before changing batch settings.")
            return False
        updated = 0
        for job_id in self._batch_job_ids:
            job = job_store.get_job(job_id)
            if not job:
                continue
            job_store.update_job(
                job_id,
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
        self.refreshJobs()
        self.batchChanged.emit()
        return True

    @Slot()
    def loadBatchSettings(self):
        jobs = [job_store.get_job(job_id) for job_id in self._batch_job_ids]
        jobs = [job for job in jobs if job]
        if not jobs:
            return
        common, _count = Counter(
            (
                job.mode,
                job.target_language,
                job.tts_voice,
                job.enable_audio_separation,
                job.original_video_volume,
            )
            for job in jobs
        ).most_common(1)[0]
        self._workflow_mode, self._target_language, self._tts_voice, self._enable_audio_separation, self._original_volume = common
        self.workflowModeChanged.emit()
        self.targetLanguageChanged.emit()
        self.ttsVoiceChanged.emit()
        self.enableAudioSeparationChanged.emit()
        self.originalVolumeChanged.emit()

    @Slot(result=bool)
    def saveSelectedJobSettings(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job or job.project_type != "batch" or job.status == "processing":
            return False
        self._apply_setup_to_job(job)
        job_store.log_to_job(job.job_id, "Per-video dubbing settings saved.")
        self.refreshJobs()
        self.selectedJobChanged.emit()
        self.batchChanged.emit()
        return True

    @Slot()
    def stopBatch(self):
        if not self._batch_running:
            return
        if QMessageBox.question(None, "Stop batch", "Stop the active video and cancel the remaining queue?") != QMessageBox.StandardButton.Yes:
            return

        self._batch_stop_requested = True
        active_job_id = self._processing_job_id
        if active_job_id:
            cancel_job(active_job_id)
            job_store.update_job(active_job_id, status="cancelled", error=None, step="cancelled")
            job_store.log_to_job(active_job_id, "Batch stop requested. Active subprocesses were force-stopped.")
        for job_id in self._batch_job_ids:
            job = job_store.get_job(job_id)
            if job and job.status == "pending":
                job_store.update_job(job_id, status="cancelled", error=None, step="cancelled")
                job_store.log_to_job(job_id, "Cancelled before batch processing started.")
        self._refresh_batch_model()
        self.batchChanged.emit()

    @Slot()
    def clearBatch(self):
        if self._batch_running:
            return
        self._batch_job_ids = []
        self._refresh_batch_model()
        self.batchChanged.emit()

    @staticmethod
    def _batch_output_directory(job):
        """Return only the app-owned per-video output directory, if it is safe to remove."""
        project_directory = (job.project_directory or "").strip()
        output_path = (job.files or {}).get("final_video", "")
        if not project_directory or not output_path:
            return ""
        safe_project = "".join(
            character if character.isalnum() or character in {"-", "_", " "} else "_"
            for character in (job.project_name or "").strip()
        ).strip() or "project"
        project_root = os.path.abspath(os.path.join(project_directory, safe_project))
        outputs_root = os.path.abspath(os.path.join(project_root, "outputs"))
        output_directory = os.path.abspath(os.path.dirname(output_path))
        try:
            if os.path.commonpath([outputs_root, output_directory]) != outputs_root:
                return ""
        except ValueError:
            return ""
        return output_directory

    @staticmethod
    def _remove_empty_batch_output_parents(job):
        output_directory = AutoDubController._batch_output_directory(job)
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
        batch_ids = list(self._batch_job_ids)
        if not batch_ids:
            return
        project_name = self._project_name or "this batch"
        message = (
            "Delete this batch and all of its jobs?\n\n"
            f"{project_name}\n{len(batch_ids)} video(s)\n\n"
            "This removes job logs, temporary data, copied inputs, and generated batch outputs. "
            "If processing is active, it will be stopped first."
        )
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        if QMessageBox.question(
            None,
            "Delete batch",
            message,
            buttons,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self._batch_stop_requested = True
        active_job_id = self._processing_job_id
        if active_job_id in batch_ids:
            cancel_job(active_job_id)

        failures = []
        remaining_ids = []
        for job_id in batch_ids:
            job = job_store.get_job(job_id)
            if not job:
                continue
            self._deleted_job_ids.add(job_id)
            if job.status == "processing":
                cancel_job(job_id)
            output_directory = self._batch_output_directory(job)
            try:
                if output_directory and os.path.isdir(output_directory):
                    shutil.rmtree(output_directory)
                job_store.delete_job(job_id)
                self._remove_empty_batch_output_parents(job)
            except Exception as exc:
                failures.append(f"{job.original_filename}: {exc}")
                remaining_ids.append(job_id)

        self._batch_job_ids = remaining_ids
        self._refresh_batch_model()
        self.batchChanged.emit()
        self._selected_job_id = None
        self._logs = ""
        self.tasks.set_job(None)
        self.selectedJobChanged.emit()
        self.logsChanged.emit()
        self.refreshJobs()

        if failures:
            QMessageBox.warning(
                None,
                "Batch delete incomplete",
                "Some videos could not be deleted. You can retry after closing any program using them.\n\n"
                + "\n".join(failures[:5]),
            )
            return
        self.batchDeleted.emit()

    @Slot()
    def startJob(self):
        if self._is_processing:
            QMessageBox.warning(None, "Job running", "A job is already processing.")
            return
        if not self._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return
        try:
            job = create_desktop_job(self._video_path, self._build_config())
        except Exception as exc:
            QMessageBox.critical(None, "Cannot create job", str(exc))
            return

        self._processing_job_id = job.job_id
        self._selected_job_id = job.job_id
        self._is_processing = True
        self._logs = self._read_job_logs(job.job_id)
        self.tasks.set_job(job)
        self.processingChanged.emit()
        self.selectedJobChanged.emit()
        self.logsChanged.emit()
        self.refreshJobs()
        threading.Thread(target=self._run_pipeline, args=(job.job_id,), daemon=True).start()

    @Slot(result=bool)
    def startProjectJob(self):
        if self._is_processing:
            QMessageBox.warning(None, "Job running", "A job is already processing.")
            return False
        if not self._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return False
        if not self._project_name.strip():
            QMessageBox.warning(None, "Project name", "Enter a project name.")
            return False
        if not self._project_directory.strip():
            QMessageBox.warning(None, "Project folder", "Choose a project folder.")
            return False
        try:
            job = create_desktop_job(
                self._video_path,
                self._build_config(),
                project_name=self._project_name,
                project_directory=self._project_directory,
            )
        except Exception as exc:
            QMessageBox.critical(None, "Cannot create project", str(exc))
            return False

        self._processing_job_id = job.job_id
        self._selected_job_id = job.job_id
        self._is_processing = True
        self._logs = self._read_job_logs(job.job_id)
        self.tasks.set_job(job)
        self.processingChanged.emit()
        self.selectedJobChanged.emit()
        self.logsChanged.emit()
        self.refreshJobs()
        threading.Thread(target=self._run_pipeline, args=(job.job_id,), daemon=True).start()
        return True

    @Slot()
    def stopJob(self):
        selected_job_id = self._selected_job_id
        if not selected_job_id or selected_job_id != self._processing_job_id:
            return
        selected_job = job_store.get_job(selected_job_id)
        if not selected_job or selected_job.status != "processing":
            return
        if self._batch_running:
            if selected_job_id in self._batch_job_ids:
                self.stopBatch()
            return
        if QMessageBox.question(None, "Pause job", "Pause this job? You can resume it later from Projects.") != QMessageBox.StandardButton.Yes:
            return
        resume_step = selected_job.step
        pause_job(selected_job_id)
        job_store.update_job(selected_job_id, status="paused", error=None, step="paused", resume_step=resume_step, step_detail=f"Paused during {resume_step or 'startup'}")
        job_store.log_to_job(selected_job_id, "Pause requested. Active subprocesses were stopped.")
        self._processing_job_id = None
        self._is_processing = False
        self.processingChanged.emit()
        self.selectedJobChanged.emit()
        self.refreshJobs()

    @Slot()
    def resumeSelectedJob(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job or job.status != "paused" or self._is_processing:
            return
        self._apply_setup_to_job(job)
        job_store.update_job(job.job_id, status="processing", step=job.resume_step or "starting", step_detail="Resuming job")
        self._processing_job_id = job.job_id
        self._is_processing = True
        self.processingChanged.emit()
        self.selectedJobChanged.emit()
        threading.Thread(target=self._run_pipeline, args=(job.job_id,), daemon=True).start()

    @Slot()
    def restartSelectedJob(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job or self._is_processing:
            return
        if QMessageBox.question(None, "Restart job", "Apply the current dubbing setup and restart this project?") != QMessageBox.StandardButton.Yes:
            return
        self._apply_setup_to_job(job, review_approved=False)
        job_store.update_job(job.job_id, status="processing", progress=0, step="starting", resume_step="", step_detail="Restarting job", error=None)
        job_store.log_to_job(job.job_id, "Restart requested with the updated dubbing setup.")
        self._processing_job_id = job.job_id
        self._is_processing = True
        self.processingChanged.emit()
        self.selectedJobChanged.emit()
        threading.Thread(target=self._run_pipeline, args=(job.job_id,), daemon=True).start()

    @Slot(str)
    def approveTranslationReview(self, payload):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        if not job or job.status != "awaiting_review":
            return
        try:
            segments = json.loads(payload)
            if not isinstance(segments, list) or any(not str(item.get("text", "")).strip() for item in segments):
                raise ValueError("Every translation must contain text.")
            with open(job.files["transcript_json"], "w", encoding="utf-8") as file:
                json.dump(segments, file, ensure_ascii=False, indent=2)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(None, "Translation review", str(exc))
            return
        job_store.update_job(job.job_id, review_approved=True, status="processing", step="creating_subtitle", step_detail="Review approved; creating dub")
        job_store.log_to_job(job.job_id, f"Translation review approved with {len(segments)} edited segments. Continuing with TTS and render.")
        self._processing_job_id = job.job_id
        self._is_processing = True
        self.processingChanged.emit()
        self.selectedJobChanged.emit()
        threading.Thread(target=self._run_pipeline, args=(job.job_id,), daemon=True).start()

    @Slot(int)
    def selectJob(self, row: int):
        job = self.jobs.job_at(row)
        if not job:
            return
        self._select_job(job)

    def _select_job(self, job):
        self._selected_job_id = job.job_id
        self._project_name = job.project_name or os.path.splitext(job.original_filename)[0]
        self._project_directory = job.project_directory or self._project_directory
        self._project_type = "batch" if getattr(job, "project_type", "single") == "batch" else "single"
        if job.status != "processing" and (job.source_language != "auto" or job.output_format != "keep_ratio"):
            job = job_store.update_job(job.job_id, source_language="auto", output_format="keep_ratio") or job
        self._workflow_mode = job.mode
        self._target_language = job.target_language
        self._tts_voice = job.tts_voice
        self._enable_audio_separation = job.enable_audio_separation
        self._original_volume = job.original_video_volume
        input_path = self._resolve_job_file(job, ("video_input", "input_video"), ("input", "video.mp4"))
        thumbnail_path = job.files.get("thumbnail") or ""
        self._video_path = input_path
        self._video_thumbnail_source = QUrl.fromLocalFile(thumbnail_path).toString() if os.path.exists(thumbnail_path) else ""
        self._load_job_preview(job)
        self._logs = self._read_job_logs(job.job_id)
        self.tasks.set_job(job)
        self.videoPathChanged.emit()
        self.videoThumbnailChanged.emit()
        self.targetLanguageChanged.emit()
        self.ttsVoiceChanged.emit()
        self.enableAudioSeparationChanged.emit()
        self.originalVolumeChanged.emit()
        self.workflowModeChanged.emit()
        self.projectSetupChanged.emit()
        self.selectedJobChanged.emit()
        self.processingChanged.emit()
        self.logsChanged.emit()

    @Slot(int)
    def selectBatchJob(self, row: int):
        job = self.batch_jobs.job_at(row)
        if not job:
            return
        self._select_job(job)

    @Slot(int)
    def selectProject(self, row: int):
        project = self.projects.project_at(row)
        if not project:
            return
        jobs = project["jobs"]
        if not jobs:
            return
        self._project_name = project["project_name"]
        self._project_directory = project["project_directory"] or self._project_directory
        self._project_type = project["project_type"]
        self._batch_job_ids = [job.job_id for job in jobs] if self._project_type == "batch" else []
        self._refresh_batch_model()
        self._select_job(jobs[0])
        self._project_type = project["project_type"]
        self.projectSetupChanged.emit()
        self.batchChanged.emit()

    @Slot()
    def deleteSelectedJob(self):
        if not self._selected_job_id:
            QMessageBox.information(None, "No job selected", "Select a job in Recent Jobs first.")
            return
        job_id = self._selected_job_id
        job = job_store.get_job(job_id)
        label = job.original_filename if job else job_id
        message = f"Delete this job and all generated files?\n\n{label}\n\nIf it is running, it will be stopped first."
        if QMessageBox.question(None, "Delete job", message) != QMessageBox.StandardButton.Yes:
            return
        if job and job.status == "processing":
            cancel_job(job_id)
            job_store.update_job(job_id, status="cancelled", error=None, step="cancelled")
        self._deleted_job_ids.add(job_id)
        try:
            deleted = job_store.delete_job(job_id)
        except Exception as exc:
            QMessageBox.critical(None, "Delete failed", str(exc))
            return
        if not deleted:
            QMessageBox.information(None, "Already removed", "Job folder is already gone.")
        if self._processing_job_id == job_id:
            self._processing_job_id = None
            self._is_processing = False
            self.processingChanged.emit()
        if job_id in self._batch_job_ids:
            self._batch_job_ids.remove(job_id)
            self._refresh_batch_model()
            self.batchChanged.emit()
        self._selected_job_id = None
        self._logs = ""
        self.tasks.set_job(None)
        self.selectedJobChanged.emit()
        self.logsChanged.emit()
        self.refreshJobs()
        self.jobDeleted.emit()

    @Slot()
    def refreshJobs(self):
        all_jobs = job_store.list_jobs()
        self.jobs.set_jobs(all_jobs[:40])
        self.projects.set_projects(self._build_project_summaries(all_jobs))
        self._refresh_batch_model()
        selected = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        self.tasks.set_job(selected)
        self.selectedJobChanged.emit()
        missing_thumbnails = [job.job_id for job in all_jobs if not job.files.get("thumbnail")]
        if missing_thumbnails and not self._thumbnail_refresh_running:
            self._thumbnail_refresh_running = True
            threading.Thread(target=self._create_missing_thumbnails, args=(missing_thumbnails,), daemon=True).start()

    def _create_missing_thumbnails(self, job_ids):
        try:
            for job_id in job_ids:
                job = job_store.get_job(job_id)
                if not job or job.files.get("thumbnail"):
                    continue
                video_path = self._resolve_job_file(job, ("video_input", "input_video"), ("input", "video.mp4"))
                thumbnail_path = self._create_video_thumbnail_path(video_path)
                if thumbnail_path:
                    job.files["thumbnail"] = thumbnail_path
                    job_store.save_job(job)
        finally:
            self._log_queue.put("__THUMBNAILS_READY__")

    @Slot()
    def openInputPreview(self):
        selected_job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        video_path = self._resolve_job_file(selected_job, ("video_input", "input_video"), ("input", "video.mp4")) if selected_job else self._video_path.strip()
        if not video_path or not os.path.exists(video_path):
            QMessageBox.information(None, "Input preview", "Choose an input video before opening the preview editor.")
            return
        self._preview_edit_scope = "single_job" if selected_job else "draft"
        self._preview_target_job_ids = [selected_job.job_id] if selected_job else []
        self._preview_group_keys = []
        self._preview_group_index = -1
        self._preview_original_style = self._copy_subtitle_style(selected_job.subtitle_style) if selected_job else self._current_subtitle_style()
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
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        input_path = self._resolve_job_file(job, ("video_input", "input_video"), ("input", "video.mp4"))
        if not input_path or not os.path.exists(input_path):
            QMessageBox.information(None, "Open input video", "Input video is not available yet.")
            return
        self._open_path(input_path)

    @Slot()
    def openOutputFile(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        output_path = self._resolve_job_file(job, ("final_video", "output_video"), ("output", "final.mp4"))
        if not output_path or not os.path.exists(output_path):
            QMessageBox.information(None, "Open output", "Final video is not available yet.")
            return
        self._open_path(output_path)

    @Slot()
    def openOutputFolder(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        output_path = self._resolve_job_file(job, ("final_video", "output_video"), ("output", "final.mp4"))
        folder = os.path.dirname(output_path) if output_path else ""
        fallback_folder = os.path.join(job_store.get_job_dir(job.job_id), "output") if job else ""
        if folder and os.path.isdir(folder):
            self._open_path(folder)
            return
        if fallback_folder and os.path.isdir(fallback_folder):
            self._open_path(fallback_folder)
            return
        QMessageBox.information(None, "Open output folder", "Output folder is not available yet.")

    @Slot(int, int, int, int, int)
    def updatePreviewEdits(self, subtitle_x, subtitle_y, box_width, box_height, font_size):
        self._apply_preview_edits(subtitle_x, subtitle_y, box_width, box_height, font_size)
        self.previewChanged.emit()

    @Slot(result=bool)
    def commitPreviewEdits(self):
        style = self._current_subtitle_style(self._preview_original_style)
        if self._preview_edit_scope == "size_group":
            for job_id in self._preview_target_job_ids:
                job_store.update_job(job_id, subtitle_style=style, subtitle_override=False)
            self._refresh_batch_model()
            self.batchChanged.emit()
            next_index = self._preview_group_index + 1
            if next_index < len(self._preview_group_keys):
                self._preview_group_index = next_index
                self._open_batch_group_preview(self._preview_group_keys[next_index])
                return False
        elif self._preview_edit_scope == "single_job" and self._preview_target_job_ids:
            job_id = self._preview_target_job_ids[0]
            job = job_store.get_job(job_id)
            if job:
                job_store.update_job(
                    job_id,
                    subtitle_style=style,
                    subtitle_override=job.project_type == "batch",
                )
                job_store.log_to_job(job_id, "Custom subtitle frame saved for this video.")
                self.refreshJobs()
                self.selectedJobChanged.emit()
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
    def openJobFolder(self):
        if self._selected_job_id:
            self._open_path(job_store.get_job_dir(self._selected_job_id))

    def poll_jobs(self):
        processing = job_store.get_job(self._processing_job_id) if self._processing_job_id else None
        if not self._batch_running and processing and processing.status in {"done", "failed", "cancelled"}:
            self._processing_job_id = None
            self._is_processing = False
            self.processingChanged.emit()
        if self._selected_job_id:
            job = job_store.get_job(self._selected_job_id)
            if job:
                self.tasks.set_job(job)
                self.selectedJobChanged.emit()
        self.refreshJobs()
        self.batchChanged.emit()

    def _build_config(self):
        return JobConfig(
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
        )

    def _apply_setup_to_job(self, job, review_approved=None):
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
        job_store.update_job(job.job_id, **changes)

    def _run_pipeline(self, job_id):
        self._execute_pipeline(job_id)
        self._log_queue.put(f"__REFRESH__:{job_id}")

    def _execute_pipeline(self, job_id):
        try:
            from autodub.pipeline.process_job import process_job_sync

            process_job_sync(job_id)
        except Exception as exc:
            if job_id not in self._deleted_job_ids:
                message = f"Desktop worker failed before pipeline could start: {exc}"
                job_store.log_to_job(job_id, message)
                job_store.update_job(job_id, status="failed", error=str(exc), step="failed")

    def _run_batch_queue(self, pending_ids):
        try:
            if pending_ids:
                first_job_id = pending_ids[0]
                # Do not hold up audio extraction while checking the shared
                # runtimes. Locks in each model service prevent duplicate loads.
                threading.Thread(
                    target=self._prepare_batch_models,
                    args=(first_job_id,),
                    daemon=True,
                ).start()
            for job_id in pending_ids:
                if self._batch_stop_requested:
                    break
                job = job_store.get_job(job_id)
                if not job or job.status != "pending":
                    continue
                self._processing_job_id = job_id
                self._log_queue.put(f"__BATCH_START__:{job_id}")
                self._execute_pipeline(job_id)
                self._log_queue.put(f"__BATCH_JOB_FINISHED__:{job_id}")
        finally:
            self._log_queue.put("__BATCH_FINISHED__")

    @staticmethod
    def _prepare_batch_models(job_id):
        job_store.log_to_job(job_id, "Preparing shared WhisperX and HY-MT2 models for the batch.")
        try:
            warm_whisperx_model()
            warm_hymt2_worker(lambda detail: job_store.log_to_job(job_id, detail))
            job_store.log_to_job(
                job_id,
                "Shared models are ready and will be reused for every video in this batch.",
            )
        except Exception as exc:
            # The job pipeline can retry initialization at the point of use.
            job_store.log_to_job(job_id, f"Batch model preparation deferred: {exc}")

    def _on_job_log(self, job_id, line):
        if job_id == self._selected_job_id:
            self._log_queue.put(line)

    def _drain_log_queue(self):
        changed = False
        while True:
            try:
                item = self._log_queue.get_nowait()
            except queue.Empty:
                break
            if item.startswith("__REFRESH__:"):
                completed_job_id = item.split(":", 1)[1]
                if completed_job_id == self._processing_job_id:
                    self._processing_job_id = None
                    self._is_processing = False
                    self.processingChanged.emit()
                self.refreshJobs()
                self.selectedJobChanged.emit()
            elif item.startswith("__BATCH_START__:"):
                self._processing_job_id = item.split(":", 1)[1]
                self.processingChanged.emit()
                self._refresh_batch_model()
                self.batchChanged.emit()
            elif item.startswith("__BATCH_JOB_FINISHED__:"):
                self.refreshJobs()
                self.processingChanged.emit()
                self.batchChanged.emit()
            elif item == "__BATCH_FINISHED__":
                self._processing_job_id = None
                self._batch_running = False
                self._batch_stop_requested = False
                self._is_processing = False
                self.refreshJobs()
                self.processingChanged.emit()
                self.batchChanged.emit()
            elif item == "__THUMBNAILS_READY__":
                self._thumbnail_refresh_running = False
                self.refreshJobs()
            else:
                self._logs = f"{self._logs}\n{item}".strip()
                changed = True
        if changed:
            self.logsChanged.emit()

    def _read_job_logs(self, job_id):
        path = job_store.get_job_logs_path(job_id)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as file:
            return file.read()

    def _refresh_batch_model(self):
        jobs = []
        valid_ids = []
        for job_id in self._batch_job_ids:
            job = job_store.get_job(job_id)
            if job:
                job = self._ensure_job_dimensions(job)
                valid_ids.append(job_id)
                jobs.append(job)
        self._batch_job_ids = valid_ids
        self.batch_jobs.set_jobs(jobs)

    def _ensure_job_dimensions(self, job):
        if job.video_width > 0 and job.video_height > 0:
            return job
        video_path = self._resolve_job_file(job, ("video_input", "input_video"), ("input", "video.mp4"))
        try:
            width, height = get_video_dimensions(video_path)
        except RuntimeError:
            return job
        return job_store.update_job(job.job_id, video_width=width, video_height=height) or job

    def _batch_dimension_groups(self):
        grouped = {}
        for job_id in self._batch_job_ids:
            job = job_store.get_job(job_id)
            if not job:
                continue
            job = self._ensure_job_dimensions(job)
            if job.video_width > 0 and job.video_height > 0:
                size_key = f"{job.video_width}x{job.video_height}"
                label = f"{job.video_width} x {job.video_height}"
            else:
                size_key = f"unknown:{job.job_id}"
                label = "Unknown size"
            group = grouped.setdefault(size_key, {"size_key": size_key, "label": label, "jobs": []})
            group["jobs"].append(job)
        return sorted(
            grouped.values(),
            key=lambda group: (
                -(group["jobs"][0].video_width * group["jobs"][0].video_height),
                group["label"],
            ),
        )

    def _batch_dimension_group(self, size_key):
        return next((group for group in self._batch_dimension_groups() if group["size_key"] == size_key), None)

    @staticmethod
    def _build_project_summaries(jobs):
        grouped = {}
        for job in jobs:
            project_type = "batch" if getattr(job, "project_type", "single") == "batch" else "single"
            project_name = job.project_name or os.path.splitext(job.original_filename)[0]
            project_directory = job.project_directory or ""
            key = (
                f"batch:{project_directory.lower()}:{project_name.lower()}"
                if project_type == "batch"
                else f"single:{job.job_id}"
            )
            project = grouped.setdefault(
                key,
                {
                    "key": key,
                    "project_name": project_name,
                    "project_directory": project_directory,
                    "project_type": project_type,
                    "jobs": [],
                },
            )
            project["jobs"].append(job)

        summaries = []
        for project in grouped.values():
            project_jobs = project["jobs"]
            statuses = {job.status for job in project_jobs}
            if "processing" in statuses:
                status = "processing"
            elif "awaiting_review" in statuses:
                status = "awaiting_review"
            elif "paused" in statuses:
                status = "paused"
            elif "pending" in statuses:
                status = "pending"
            elif all(job.status == "done" for job in project_jobs):
                status = "done"
            elif "failed" in statuses:
                status = "failed"
            elif "cancelled" in statuses:
                status = "cancelled"
            else:
                status = project_jobs[0].status
            thumbnail_source = ""
            for job in project_jobs:
                thumbnail_source = JobListModel._thumbnail_source(job)
                if thumbnail_source:
                    break
            summaries.append(
                {
                    **project,
                    "job_count": len(project_jobs),
                    "status": status,
                    "progress": round(sum(job.progress for job in project_jobs) / len(project_jobs)),
                    "thumbnail_source": thumbnail_source,
                    "updated_at": max(job.updated_at for job in project_jobs),
                }
            )
        return sorted(summaries, key=lambda project: project["updated_at"], reverse=True)

    @staticmethod
    def _normalize_video_path(value) -> str:
        raw_path = str(value).strip() if value else ""
        if not raw_path:
            return ""
        url = QUrl(raw_path)
        if url.isLocalFile():
            return os.path.abspath(url.toLocalFile())
        return os.path.abspath(raw_path)

    @classmethod
    def _collect_batch_video_paths(cls, paths):
        valid_paths = []
        invalid_names = []
        seen_paths = set()

        def add_if_supported(path):
            normalized_path = os.path.abspath(path)
            extension = os.path.splitext(normalized_path)[1].lower()
            if extension in SUPPORTED_VIDEO_EXTENSIONS and normalized_path not in seen_paths:
                seen_paths.add(normalized_path)
                valid_paths.append(normalized_path)

        for value in paths:
            path = cls._normalize_video_path(value)
            if os.path.isdir(path):
                try:
                    with os.scandir(path) as entries:
                        for entry in sorted(entries, key=lambda item: item.name.lower()):
                            if entry.is_file():
                                add_if_supported(entry.path)
                except OSError as exc:
                    invalid_names.append(f"{os.path.basename(path) or path}: {exc}")
            elif os.path.isfile(path):
                if os.path.splitext(path)[1].lower() in SUPPORTED_VIDEO_EXTENSIONS:
                    add_if_supported(path)
                else:
                    invalid_names.append(os.path.basename(path) or path)
            elif path:
                invalid_names.append(os.path.basename(path) or path)

        return valid_paths, invalid_names

    @staticmethod
    def _resolve_job_file(job, keys, fallback_parts):
        if not job:
            return ""
        for key in keys:
            path = job.files.get(key)
            if path and os.path.exists(path):
                return path
        fallback = os.path.join(job_store.get_job_dir(job.job_id), *fallback_parts)
        if os.path.exists(fallback):
            return fallback
        if fallback_parts == ("input", "video.mp4"):
            input_dir = os.path.join(job_store.get_job_dir(job.job_id), "input")
            if os.path.isdir(input_dir):
                for name in os.listdir(input_dir):
                    path = os.path.join(input_dir, name)
                    if os.path.isfile(path) and os.path.splitext(name)[1].lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                        return path
        return job.files.get(keys[0]) or fallback

    @staticmethod
    def _language_label(code):
        for language_code, english_name, native_name in POPULAR_TARGET_LANGUAGES:
            if language_code == code:
                return f"{native_name} - {english_name} ({language_code})"
        return code

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, round(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02}:{seconds:02}"
        return f"{minutes}:{seconds:02}"

    @staticmethod
    def _voice_options_for_language(language_code):
        voices = EDGE_TTS_VOICES_BY_LANGUAGE.get(language_code) or EDGE_TTS_VOICES_BY_LANGUAGE["en"]
        return [{"voice": voice, "label": f"{label} ({voice})"} for voice, label in voices]

    @staticmethod
    def _voice_codes_for_language(language_code):
        return [item["voice"] for item in AutoDubController._voice_options_for_language(language_code)]

    def _load_job_preview(self, job):
        self._subtitle_position_x = job.subtitle_style.position_x_percent
        self._subtitle_position_y = job.subtitle_style.position_y_percent
        self._caption_font_size = job.subtitle_style.font_size
        self._subtitle_box_width = job.subtitle_style.box_width_percent
        self._subtitle_box_height = job.subtitle_style.box_height_percent
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
        representative = group["jobs"][0]
        video_path = self._resolve_job_file(representative, ("video_input", "input_video"), ("input", "video.mp4"))
        self._preview_edit_scope = "size_group"
        self._preview_target_job_ids = [job.job_id for job in group["jobs"]]
        self._preview_original_style = self._copy_subtitle_style(representative.subtitle_style)
        self._set_preview_style(representative.subtitle_style)
        index_label = f"{self._preview_group_index + 1}/{len(self._preview_group_keys)}"
        title = f"{group['label']} | {index_label}"
        self._open_preview(video_path, title, True)

    def _clear_preview_edit_session(self):
        self._preview_edit_scope = "draft"
        self._preview_target_job_ids = []
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
        self._preview_poster_source = self._create_video_thumbnail(path)
        self._preview_aspect_ratio = 16 / 9
        try:
            width, height = get_video_dimensions(path)
            if width > 0 and height > 0:
                self._preview_aspect_ratio = width / height
        except RuntimeError:
            pass
        self.previewChanged.emit()
        self.previewOpenRequested.emit()

    @staticmethod
    def _create_video_thumbnail(path: str) -> str:
        output_path = AutoDubController._create_video_thumbnail_path(path)
        return QUrl.fromLocalFile(output_path).toString() if output_path else ""

    @staticmethod
    def _create_video_thumbnail_path(path: str) -> str:
        if not path or not os.path.exists(path):
            return ""
        try:
            import subprocess

            thumbnail_dir = os.path.join(CACHE_DIR, "thumbnails")
            os.makedirs(thumbnail_dir, exist_ok=True)
            digest = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:16]
            output_path = os.path.join(thumbnail_dir, f"{digest}.jpg")
            if not os.path.exists(output_path):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        "00:00:01",
                        "-i",
                        path,
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=320:-1",
                        output_path,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            return output_path if os.path.exists(output_path) else ""
        except Exception:
            return ""

    @staticmethod
    def _open_path(path):
        if not path:
            return
        if os.name == "nt":
            os.startfile(path)
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(path)])
