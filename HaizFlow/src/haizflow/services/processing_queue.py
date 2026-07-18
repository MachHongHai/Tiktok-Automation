"""A single-worker FIFO queue for resource-intensive video pipelines."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import threading


class SerialProcessingQueue:
    """Run one pipeline at a time while allowing the UI to keep accepting work."""

    def __init__(
        self,
        runner: Callable[[str], None],
        on_started: Callable[[str], None] | None = None,
        on_finished: Callable[[str], None] | None = None,
        on_idle: Callable[[], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ):
        self._runner = runner
        self._on_started = on_started
        self._on_finished = on_finished
        self._on_idle = on_idle
        self._on_error = on_error
        self._pending: deque[str] = deque()
        self._active_video_id: str | None = None
        self._worker: threading.Thread | None = None
        self._shutdown_requested = False
        self._lock = threading.RLock()

    @property
    def active_video_id(self) -> str | None:
        with self._lock:
            return self._active_video_id

    @property
    def has_work(self) -> bool:
        """Return whether a video is active or waiting without exposing internals."""
        with self._lock:
            return self._active_video_id is not None or bool(self._pending)

    def pending_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending)

    def contains(self, video_id: str) -> bool:
        with self._lock:
            return video_id == self._active_video_id or video_id in self._pending

    def enqueue(self, video_id: str) -> bool:
        """Add a video once. Returns False when it is already queued or active."""
        with self._lock:
            if self._shutdown_requested or video_id == self._active_video_id or video_id in self._pending:
                return False
            self._pending.append(video_id)
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="haizflow-processing-queue", daemon=True)
                self._worker.start()
            return True

    def discard(self, video_id: str) -> bool:
        """Remove a waiting video. The active video must be cancelled by its pipeline manager."""
        with self._lock:
            try:
                self._pending.remove(video_id)
            except ValueError:
                return False
            return True

    def shutdown(self, *, timeout_seconds: float = 10.0) -> bool:
        """Stop accepting work, discard waiting items, and wait for the active runner.

        The owner must first signal cancellation to the active runner. Returning
        ``False`` means that runner did not finish before the timeout; the queue
        still remains closed and will not start any waiting work.
        """
        with self._lock:
            self._shutdown_requested = True
            self._pending.clear()
            worker = self._worker
        if worker is None or worker is threading.current_thread():
            return worker is None
        worker.join(timeout=max(0.0, timeout_seconds))
        return not worker.is_alive()

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._shutdown_requested or not self._pending:
                    self._pending.clear()
                    self._active_video_id = None
                    self._worker = None
                    break
                video_id = self._pending.popleft()
                self._active_video_id = video_id

            can_run = True
            if self._on_started:
                try:
                    self._on_started(video_id)
                except Exception as exc:
                    can_run = False
                    self._report_error(video_id, exc)
            try:
                if can_run:
                    self._runner(video_id)
            except Exception as exc:
                self._report_error(video_id, exc)
            finally:
                if self._on_finished:
                    try:
                        self._on_finished(video_id)
                    except Exception as exc:
                        self._report_error(video_id, exc)
                with self._lock:
                    if self._active_video_id == video_id:
                        self._active_video_id = None
        if self._on_idle:
            try:
                self._on_idle()
            except Exception as exc:
                self._report_error("", exc)

    def _report_error(self, video_id: str, exc: Exception) -> None:
        """Keep the worker alive even when a runner or lifecycle callback fails."""
        if not self._on_error:
            return
        try:
            self._on_error(video_id, exc)
        except Exception:
            # Error reporting must never strand the remaining queue.
            pass
