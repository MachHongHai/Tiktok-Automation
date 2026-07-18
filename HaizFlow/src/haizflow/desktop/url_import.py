"""QML-facing state coordinator for background video URL imports."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Property, Signal, Slot

from haizflow.desktop.presenters import format_duration
from haizflow.services.video_download import (
    DownloadCancelled,
    VideoMetadata,
    cleanup_download_workspace,
    create_download_workspace,
    download_video,
    inspect_video_url,
    validate_video_url,
)


class VideoUrlImportCoordinator(QObject):
    changed = Signal()
    downloadReady = Signal(str, str, str)
    importFinished = Signal()
    _metadataResolved = Signal(int, object)
    _progressResolved = Signal(int, int, str)
    _downloadResolved = Signal(int, str, str)
    _operationRejected = Signal(int, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = 0
        self._mode = "single"
        self._state = "idle"
        self._url = ""
        self._metadata = {}
        self._progress = 0
        self._status = ""
        self._workspace = ""
        self._cancel_event = threading.Event()
        self._threads: set[threading.Thread] = set()
        self._threads_lock = threading.Lock()
        self._metadataResolved.connect(self._handle_metadata)
        self._progressResolved.connect(self._handle_progress)
        self._downloadResolved.connect(self._handle_download)
        self._operationRejected.connect(self._handle_rejection)

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(str, notify=changed)
    def url(self):
        return self._url

    @Property(bool, notify=changed)
    def busy(self):
        return self._state in {"inspecting", "downloading", "importing", "cancelling"}

    @Property(int, notify=changed)
    def progress(self):
        return self._progress

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def title(self):
        return str(self._metadata.get("title") or "")

    @Property(str, notify=changed)
    def platform(self):
        return str(self._metadata.get("platform") or "")

    @Property(str, notify=changed)
    def uploader(self):
        return str(self._metadata.get("uploader") or "")

    @Property(int, notify=changed)
    def durationSeconds(self):
        return int(self._metadata.get("duration_seconds") or 0)

    @Property(str, notify=changed)
    def duration(self):
        seconds = self.durationSeconds
        return format_duration(seconds) if seconds else ""

    @Property(str, notify=changed)
    def thumbnailSource(self):
        return str(self._metadata.get("thumbnail_url") or "")

    @Slot(str)
    def begin(self, mode):
        if self.busy:
            return
        self._generation += 1
        self._mode = "batch" if str(mode) == "batch" else "single"
        self._state = "idle"
        self._url = ""
        self._metadata = {}
        self._progress = 0
        self._status = ""
        self._workspace = ""
        self._cancel_event = threading.Event()
        self.changed.emit()

    @Slot(str)
    def inspect(self, value):
        if self.busy:
            return
        try:
            normalized_url, _platform = validate_video_url(value)
        except ValueError as exc:
            self._state = "error"
            self._status = str(exc)
            self.changed.emit()
            return

        self._generation += 1
        generation = self._generation
        self._url = normalized_url
        self._metadata = {}
        self._progress = 0
        self._state = "inspecting"
        self._status = "Checking video link"
        self._cancel_event = threading.Event()
        cancel_event = self._cancel_event
        self.changed.emit()

        def inspect_link():
            try:
                metadata = inspect_video_url(normalized_url, cancel_event)
                self._metadataResolved.emit(generation, metadata.to_dict())
            except DownloadCancelled as exc:
                self._operationRejected.emit(generation, str(exc), True)
            except Exception as exc:
                self._operationRejected.emit(generation, str(exc), False)

        self._start_worker(inspect_link, "video-link-inspection")

    def start_download(self, project_root: str) -> bool:
        if self._state != "ready" or not self._metadata:
            return False
        try:
            workspace = create_download_workspace(project_root)
        except OSError as exc:
            self._state = "error"
            self._status = f"Cannot prepare the project download folder: {exc}"
            self.changed.emit()
            return False

        generation = self._generation
        cancel_event = threading.Event()
        self._cancel_event = cancel_event
        self._workspace = workspace
        self._state = "downloading"
        self._progress = 0
        self._status = "Starting download"
        metadata = VideoMetadata(**self._metadata)
        self.changed.emit()

        def download_link():
            try:
                path = download_video(
                    metadata,
                    workspace,
                    lambda progress, detail: self._progressResolved.emit(generation, progress, detail),
                    cancel_event,
                )
                self._downloadResolved.emit(generation, path, workspace)
            except DownloadCancelled as exc:
                cleanup_download_workspace(workspace)
                self._operationRejected.emit(generation, str(exc), True)
            except Exception as exc:
                cleanup_download_workspace(workspace)
                self._operationRejected.emit(generation, str(exc), False)

        self._start_worker(download_link, "video-link-download")
        return True

    @Slot()
    def cancel(self):
        if not self.busy:
            return
        self._cancel_event.set()
        self._state = "cancelling"
        self._status = "Cancelling download"
        self.changed.emit()

    def complete_import(self, success: bool, message: str = "") -> None:
        cleanup_download_workspace(self._workspace)
        self._workspace = ""
        self._state = "success" if success else "error"
        self._status = "Video added to project" if success else message
        self.changed.emit()
        if success:
            self.importFinished.emit()

    def shutdown(self, timeout_seconds: float = 5.0) -> bool:
        self._cancel_event.set()
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        with self._threads_lock:
            threads = tuple(self._threads)
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)
        with self._threads_lock:
            stopped = not any(thread.is_alive() for thread in self._threads)
        if stopped:
            cleanup_download_workspace(self._workspace)
            self._workspace = ""
        return stopped

    def _start_worker(self, target, name: str) -> None:
        def run() -> None:
            try:
                target()
            finally:
                with self._threads_lock:
                    self._threads.discard(threading.current_thread())

        thread = threading.Thread(target=run, name=name, daemon=True)
        with self._threads_lock:
            self._threads.add(thread)
        thread.start()

    def _handle_metadata(self, generation, metadata):
        if generation != self._generation:
            return
        self._metadata = dict(metadata)
        self._url = str(metadata.get("url") or self._url)
        self._state = "ready"
        self._status = "Video ready to download"
        self.changed.emit()

    def _handle_progress(self, generation, progress, detail):
        if generation != self._generation or self._state != "downloading":
            return
        self._progress = int(progress)
        self._status = str(detail)
        self.changed.emit()

    def _handle_download(self, generation, path, workspace):
        if generation != self._generation:
            cleanup_download_workspace(workspace)
            return
        self._state = "importing"
        self._progress = 100
        self._status = "Adding video to project"
        self.changed.emit()
        self.downloadReady.emit(str(path), str(workspace), self._mode)

    def _handle_rejection(self, generation, message, cancelled):
        if generation != self._generation:
            return
        self._workspace = ""
        self._state = "idle" if cancelled else "error"
        self._status = "Import cancelled" if cancelled else str(message)
        self.changed.emit()
