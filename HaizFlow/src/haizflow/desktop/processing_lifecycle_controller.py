"""Queue, pipeline, and log lifecycle kept outside the QML singleton facade."""

from __future__ import annotations

import queue

from haizflow.desktop.activity_log import ActivityLogBuffer
from haizflow.core.hardware import runtime_profile
from haizflow.services import video_store
from haizflow.services.translation import warm_hymt2_worker


class ProcessingLifecycleController:
    def __init__(self, host):
        self._host = host

    def enqueue_video(self, video_id: str) -> bool:
        host = self._host
        video = video_store.get_video(video_id)
        if not video or video.status == "processing" or host._processing_queue.contains(video_id):
            return False
        video_store.update_video(video_id, status="pending", step="queued", step_detail="Queued for processing")
        if not host._processing_queue.enqueue(video_id):
            return False
        video_store.log_to_video(video_id, "Added to the processing queue.")
        self.update_queue_positions()
        host.processingChanged.emit()
        host.selectedVideoChanged.emit()
        host._log_queue.put("__QUEUE_CHANGED__")
        return True

    def enqueue_videos(self, video_ids) -> int:
        return sum(1 for video_id in video_ids if self.enqueue_video(video_id))

    def update_queue_positions(self) -> None:
        host = self._host
        for position, video_id in enumerate(host._processing_queue.pending_ids(), start=1):
            video = video_store.get_video(video_id)
            if video and video.status == "pending":
                video_store.update_video(video_id, step="queued", step_detail=f"Queued: position {position}")

    def on_queue_video_started(self, video_id: str) -> None:
        host = self._host
        if video_id in host._deleted_video_ids:
            return
        video = video_store.get_video(video_id)
        if not video or video.status == "cancelled":
            return
        host._activate_pending_device_for_next_video(video_id)
        video_store.update_video(video_id, status="processing", step="starting", step_detail="Processing started")
        video_store.log_to_video(video_id, "Processing started from the shared queue.")
        self.update_queue_positions()
        host._log_queue.put(f"__QUEUE_STARTED__:{video_id}")

    def on_queue_video_finished(self, video_id: str) -> None:
        self.update_queue_positions()
        self._host._log_queue.put(f"__QUEUE_FINISHED__:{video_id}")

    def on_processing_queue_idle(self) -> None:
        self._host._log_queue.put("__QUEUE_IDLE__")

    def on_processing_queue_error(self, video_id: str, exc: Exception) -> None:
        host = self._host
        if not video_id or video_id in host._deleted_video_ids:
            return
        video = video_store.get_video(video_id)
        if not video:
            return
        message = f"Processing queue recovered from an internal error: {exc}"
        video_store.log_to_video(video_id, message)
        video_store.update_video(video_id, status="failed", error=str(exc), step="failed", step_detail=message)

    def execute_pipeline(self, video_id: str) -> None:
        host = self._host
        video = video_store.get_video(video_id)
        if not video or video.status == "cancelled" or video_id in host._deleted_video_ids:
            return
        try:
            if not host._initial_model_warmup_done.is_set():
                video_store.log_to_video(video_id, "Waiting for startup model warm-up to finish.")
                host._initial_model_warmup_done.wait()
            if getattr(host, "_shutdown_started", False):
                return
            runtime_probe_error = getattr(host, "_runtime_probe_error", "")
            if runtime_probe_error:
                raise RuntimeError(f"Model runtime validation failed: {runtime_probe_error}")
            with host._model_runtime_lock:
                pass
            from haizflow.pipeline.process_video import process_video_sync

            process_video_sync(video_id)
        except Exception as exc:
            if video_id not in host._deleted_video_ids:
                message = f"Desktop worker failed before pipeline could start: {exc}"
                video_store.log_to_video(video_id, message)
                video_store.update_video(video_id, status="failed", error=str(exc), step="failed")

    @staticmethod
    def prepare_batch_models(video_id: str) -> None:
        profile = runtime_profile()
        video_store.log_to_video(video_id, f"Preparing shared models for batch profile: {profile.summary}.")
        try:
            if profile.warm_hymt2_on_startup:
                warm_hymt2_worker(lambda detail: video_store.log_to_video(video_id, detail))
            if profile.warm_whisper_on_startup:
                from haizflow.pipeline.transcribe import warm_whisperx_model

                warm_whisperx_model()
            video_store.log_to_video(video_id, "Shared models are ready for the batch.")
        except Exception as exc:
            video_store.log_to_video(video_id, f"Batch model preparation deferred: {exc}")

    def on_video_log(self, video_id: str, line: str) -> None:
        host = self._host
        if video_id == host._selected_video_id:
            host._log_queue.put(("video_log", video_id, line))

    def drain_log_queue(self) -> None:
        host = self._host
        pending_lines = []
        while True:
            try:
                item = host._log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and len(item) == 3 and item[0] == "video_log":
                _kind, video_id, line = item
                if video_id == host._selected_video_id:
                    pending_lines.append(line)
            elif item.startswith("__QUEUE_STARTED__:"):
                host.refreshVideos()
                host.selectedVideoChanged.emit()
                host.processingChanged.emit()
                host._refresh_batch_model()
                host.batchChanged.emit()
            elif item.startswith("__QUEUE_FINISHED__:"):
                host.refreshVideos()
                host.selectedVideoChanged.emit()
                host._refresh_batch_model()
                host.batchChanged.emit()
            elif item == "__QUEUE_IDLE__":
                if host._processing_queue.has_work:
                    continue
                host._batch_running = False
                host._batch_stop_requested = False
                host.refreshVideos()
                host.processingChanged.emit()
                host.batchChanged.emit()
            elif item == "__QUEUE_CHANGED__":
                host.refreshVideos()
                host.selectedVideoChanged.emit()
                host.batchChanged.emit()
            elif item == "__THUMBNAILS_READY__":
                host._thumbnail_refresh_running = False
                host.refreshVideos()
            elif item == "__VIDEO_DIMENSIONS_READY__":
                host.poll_videos()
        if pending_lines and self.append_logs(pending_lines):
            host.logsChanged.emit()

    @staticmethod
    def read_video_logs(video_id: str) -> str:
        return ActivityLogBuffer.read_tail(video_store.get_video_logs_path(video_id))

    def replace_logs(self, text: str) -> None:
        host = self._host
        host._log_buffer.replace(text)
        host._logs = host._log_buffer.text

    def clear_logs(self) -> None:
        host = self._host
        host._log_buffer.clear()
        host._logs = ""

    def append_logs(self, lines) -> bool:
        host = self._host
        if not host._log_buffer.append(lines):
            return False
        host._logs = host._log_buffer.text
        return True
