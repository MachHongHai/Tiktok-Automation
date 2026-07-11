import os
import queue
import threading
import hashlib

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Property, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

from autodub.config import (
    CACHE_DIR,
)
from autodub.core.events import subscribe_log, unsubscribe_log
from autodub.pipeline.job_manager import cancel_job
from autodub.schemas.job import CropSettings, JobConfig, SubtitleStyle
from autodub.services import job_store
from autodub.services.desktop_jobs import create_desktop_job
from autodub.utils.ffmpeg import get_video_dimensions


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
            self.StateRole: b"state",
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
    sourceLanguageChanged = Signal()
    targetLanguageChanged = Signal()
    ttsVoiceChanged = Signal()
    outputFormatChanged = Signal()
    enableAudioSeparationChanged = Signal()
    originalVolumeChanged = Signal()
    selectedJobChanged = Signal()
    processingChanged = Signal()
    logsChanged = Signal()
    statusMessageChanged = Signal()
    previewChanged = Signal()
    previewOpenRequested = Signal()
    jobDeleted = Signal()
    batchChanged = Signal()

    def __init__(self):
        super().__init__()
        self.jobs = JobListModel()
        self.batch_jobs = JobListModel()
        self.tasks = TaskListModel()
        self._video_path = ""
        self._video_thumbnail_source = ""
        self._source_language = "auto"
        self._target_language = "vi"
        self._tts_voice = "vi-VN-HoaiMyNeural"
        self._output_format = "keep_ratio"
        self._enable_audio_separation = False
        self._original_volume = 60
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
        self._preview_title = "Preview"
        self._preview_interactive = False
        self._preview_aspect_ratio = 16 / 9
        self._log_queue = queue.Queue()

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

    @Property(QObject, constant=True)
    def jobModel(self):
        return self.jobs

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
        job = job_store.get_job(self._batch_job_ids[0])
        return self._language_label(job.target_language) if job else self._language_label(self._target_language)

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

    @Property(str, notify=sourceLanguageChanged)
    def sourceLanguage(self):
        return self._source_language

    @sourceLanguage.setter
    def sourceLanguage(self, value):
        if self._source_language != value:
            self._source_language = value
            self.sourceLanguageChanged.emit()

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

    @Property(str, notify=outputFormatChanged)
    def outputFormat(self):
        return self._output_format

    @outputFormat.setter
    def outputFormat(self, value):
        if self._output_format != value:
            self._output_format = value
            self.outputFormatChanged.emit()

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

    @Property(bool, notify=processingChanged)
    def isProcessing(self):
        return self._is_processing

    @Property(str, notify=processingChanged)
    def processingText(self):
        job = job_store.get_job(self._processing_job_id) if self._processing_job_id else None
        return f"{job.original_filename} | {job.status}" if job else "No active job"

    @Property(str, notify=selectedJobChanged)
    def selectedTitle(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return f"{job.original_filename} | {job.status}" if job else "No job selected"

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
        return job.step if job else "pending"

    @Property(int, notify=selectedJobChanged)
    def selectedProgress(self):
        job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        return job.progress if job else 0

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

    @Slot()
    def browseVideo(self):
        path, _ = QFileDialog.getOpenFileName(None, "Choose input video", "", "Video files (*.mp4 *.mov *.mkv);;All files (*.*)")
        if path:
            self.importVideo(path)

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

    @Slot("QVariantList")
    def importBatchVideos(self, paths):
        if self._batch_running:
            QMessageBox.information(None, "Batch running", "Stop the current batch before adding more videos.")
            return

        valid_paths = []
        invalid_names = []
        for value in paths:
            path = self._normalize_video_path(value)
            extension = os.path.splitext(path)[1].lower()
            if os.path.isfile(path) and extension in {".mp4", ".mov", ".mkv"}:
                if path not in valid_paths:
                    valid_paths.append(path)
            else:
                invalid_names.append(os.path.basename(path) or path)

        if not valid_paths:
            QMessageBox.warning(None, "No supported videos", "Choose MP4, MOV, or MKV video files.")
            return

        config = self._build_config()
        created_ids = []
        errors = []
        for path in valid_paths:
            try:
                job = create_desktop_job(path, config)
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

    @Slot()
    def stopJob(self):
        if self._batch_running:
            self.stopBatch()
            return
        if not self._processing_job_id:
            return
        if QMessageBox.question(None, "Stop job", "Stop the processing job?") != QMessageBox.StandardButton.Yes:
            return
        job_id = self._processing_job_id
        cancel_job(job_id)
        job_store.update_job(job_id, status="cancelled", error=None, step="cancelled")
        job_store.log_to_job(job_id, "Stop requested. Active subprocesses were force-stopped.")
        self._processing_job_id = None
        self._is_processing = False
        self.processingChanged.emit()
        self.selectedJobChanged.emit()
        self.refreshJobs()

    @Slot(int)
    def selectJob(self, row: int):
        job = self.jobs.job_at(row)
        if not job:
            return
        self._select_job(job)

    def _select_job(self, job):
        self._selected_job_id = job.job_id
        self._load_job_preview(job)
        self._logs = self._read_job_logs(job.job_id)
        self.tasks.set_job(job)
        self.selectedJobChanged.emit()
        self.logsChanged.emit()

    @Slot(int)
    def selectBatchJob(self, row: int):
        job = self.batch_jobs.job_at(row)
        if not job:
            return
        self._select_job(job)

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
        self.jobs.set_jobs(job_store.list_jobs()[:40])
        self._refresh_batch_model()
        selected = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        self.tasks.set_job(selected)
        self.selectedJobChanged.emit()

    @Slot()
    def openInputPreview(self):
        selected_job = job_store.get_job(self._selected_job_id) if self._selected_job_id else None
        video_path = self._resolve_job_file(selected_job, ("video_input", "input_video"), ("input", "video.mp4")) if selected_job else self._video_path.strip()
        if not video_path or not os.path.exists(video_path):
            QMessageBox.information(None, "Input preview", "Choose an input video before opening the preview editor.")
            return
        self._open_preview(video_path, "Input Preview Editor", True)

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
            mode="A",
            source_language=self._source_language,
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
            output_format=self._output_format,
            crop=CropSettings(),
            enable_audio_separation=self._enable_audio_separation,
            original_video_volume=self._original_volume,
        )

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
                self.batchChanged.emit()
            elif item == "__BATCH_FINISHED__":
                self._processing_job_id = None
                self._batch_running = False
                self._batch_stop_requested = False
                self._is_processing = False
                self.refreshJobs()
                self.processingChanged.emit()
                self.batchChanged.emit()
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
                valid_ids.append(job_id)
                jobs.append(job)
        self._batch_job_ids = valid_ids
        self.batch_jobs.set_jobs(jobs)

    @staticmethod
    def _normalize_video_path(value) -> str:
        raw_path = str(value).strip() if value else ""
        if not raw_path:
            return ""
        url = QUrl(raw_path)
        if url.isLocalFile():
            return os.path.abspath(url.toLocalFile())
        return os.path.abspath(raw_path)

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
