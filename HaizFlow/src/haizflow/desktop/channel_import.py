"""Qt coordinator for persistent, non-blocking channel imports."""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from PySide6.QtCore import QObject, Property, Signal, Slot

from haizflow.desktop.localization import QFileDialog
from haizflow.desktop.models import ChannelCandidateListModel
from haizflow.schemas.channel_import import (
    ChannelImportRequest,
    ChannelImportSession,
    ChannelVideoCandidate,
)
from haizflow.services.channel_import import (
    cleanup_channel_workspace,
    download_candidate,
    download_workspace,
    load_latest_session,
    new_session,
    normalize_remote_url,
    save_session,
    scan_channel,
)
from haizflow.services.video_download import DownloadCancelled


class ChannelImportCoordinator(QObject):
    changed = Signal()
    videoReady = Signal(str, str, object, str, str)
    downloadsFinished = Signal(str)
    _scanResolved = Signal(str, object)
    _scanRejected = Signal(str, str, bool)
    _progressResolved = Signal(str, str, int, str)
    _downloadResolved = Signal(str, object, str)
    _downloadRejected = Signal(str, str, str, bool)
    _batchResolved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.candidates = ChannelCandidateListModel()
        self._active_session_id = ""
        self._active_project_key = ""
        self._active_project_root = ""
        self._sessions: dict[str, ChannelImportSession] = {}
        self._project_sessions: dict[str, str] = {}
        self._existing_remote_keys: dict[str, set[str]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._runner_threads: dict[str, threading.Thread] = {}
        self._workspaces: dict[tuple[str, str], str] = {}
        self._cookie_browser = ""
        self._cookie_file = ""
        self._scan_progress = 0
        self._worker_limit_provider = lambda: 2
        self._scanResolved.connect(self._handle_scan_resolved)
        self._scanRejected.connect(self._handle_scan_rejected)
        self._progressResolved.connect(self._handle_download_progress)
        self._downloadResolved.connect(self._handle_download_resolved)
        self._downloadRejected.connect(self._handle_download_rejected)
        self._batchResolved.connect(self._handle_batch_resolved)

    def set_worker_limit_provider(self, provider) -> None:
        self._worker_limit_provider = provider if callable(provider) else (lambda: 2)

    def _prune_finished_runners(self) -> None:
        finished = [
            session_id
            for session_id, thread in self._runner_threads.items()
            if not thread.is_alive()
        ]
        for session_id in finished:
            self._runner_threads.pop(session_id, None)
            self._cancel_events.pop(session_id, None)

    @Property(QObject, constant=True)
    def candidateModel(self):
        return self.candidates

    def _active_session(self) -> ChannelImportSession | None:
        return self._sessions.get(self._active_session_id)

    @Property(str, notify=changed)
    def state(self):
        session = self._active_session()
        return session.state if session else "idle"

    @Property(str, notify=changed)
    def status(self):
        session = self._active_session()
        return session.status if session else ""

    @Property(bool, notify=changed)
    def busy(self):
        return self.state in {"inspecting", "downloading", "importing", "cancelling"}

    @Property(int, notify=changed)
    def progress(self):
        session = self._active_session()
        if not session:
            return 0
        if session.state == "inspecting":
            return self._scan_progress
        downloadable = [
            candidate
            for candidate in session.candidates
            if candidate.selected and not candidate.duplicate
        ]
        if not downloadable:
            return 0
        return round(sum(candidate.progress for candidate in downloadable) / len(downloadable))

    @Property(int, notify=changed)
    def candidateCount(self):
        session = self._active_session()
        return len(session.candidates) if session else 0

    @Property(int, notify=changed)
    def selectedCount(self):
        session = self._active_session()
        if not session:
            return 0
        return sum(
            1
            for candidate in session.candidates
            if candidate.selected and not candidate.duplicate and candidate.status not in {"imported", "downloading", "importing"}
        )

    @Property(int, notify=changed)
    def selectableCount(self):
        session = self._active_session()
        if not session:
            return 0
        return sum(
            1
            for candidate in session.candidates
            if not candidate.duplicate and candidate.status not in {"imported", "downloading", "importing"}
        )

    @Property(int, notify=changed)
    def importedCount(self):
        session = self._active_session()
        return sum(candidate.status == "imported" for candidate in session.candidates) if session else 0

    @Property(int, notify=changed)
    def failedCount(self):
        session = self._active_session()
        return sum(candidate.status == "failed" for candidate in session.candidates) if session else 0

    @Property(str, notify=changed)
    def channelName(self):
        session = self._active_session()
        return session.channel_name if session else ""

    @Property(str, notify=changed)
    def channelUrl(self):
        session = self._active_session()
        return session.channel_url if session else ""

    @Property(str, notify=changed)
    def platform(self):
        session = self._active_session()
        return session.platform if session else ""

    @Property(str, notify=changed)
    def requestedPlatform(self):
        session = self._active_session()
        if not session:
            return ""
        return str(session.request.get("platform") or "")

    @Property(str, notify=changed)
    def sessionId(self):
        return self._active_session_id

    @Property(str, notify=changed)
    def cookieBrowser(self):
        return self._cookie_browser

    @Property(str, notify=changed)
    def cookieFile(self):
        return self._cookie_file

    def attach_project(self, project_key: str, project_root: str, existing_remote_keys: set[str]) -> None:
        self._active_project_key = str(project_key or "")
        self._active_project_root = os.path.abspath(project_root) if project_root else ""
        self._existing_remote_keys[self._active_project_key] = set(existing_remote_keys)
        session_id = self._project_sessions.get(self._active_project_key, "")
        session = self._sessions.get(session_id) if session_id else None
        if not session and self._active_project_root:
            session = load_latest_session(self._active_project_root)
            if session:
                for candidate in session.candidates:
                    if candidate.status in {"downloading", "importing"}:
                        candidate.status = "failed"
                        candidate.error = "Import was interrupted. Retry this video."
                if session.state in {"inspecting", "downloading", "importing", "cancelling"}:
                    session.state = "ready" if session.candidates else "idle"
                    session.status = "Previous import can be resumed"
                self._sessions[session.session_id] = session
                self._project_sessions[session.project_key] = session.session_id
                try:
                    save_session(session)
                except OSError:
                    pass
        self._active_session_id = session.session_id if session else ""
        self._scan_progress = 0
        self._refresh_active_model()

    def _refresh_active_model(self) -> None:
        session = self._active_session()
        self.candidates.set_candidates(session.candidates if session else [])
        self.changed.emit()

    def _safe_message(self, message) -> str:
        text = str(message or "")
        if self._cookie_file:
            text = text.replace(self._cookie_file, "cookies.txt")
            text = text.replace(os.path.normpath(self._cookie_file), "cookies.txt")
        if "cookie" in text.lower() and (self._cookie_file or self._cookie_browser):
            return "Browser session or cookies could not be read. Close the browser or choose cookies.txt and try again."
        return text

    @Slot(str)
    def setCookieBrowser(self, value):
        normalized = str(value or "").strip().lower()
        self._cookie_browser = normalized if normalized in {"chrome", "edge"} else ""
        if self._cookie_browser:
            self._cookie_file = ""
        self.changed.emit()

    @Slot()
    def browseCookieFile(self):
        path, _selected_filter = QFileDialog.getOpenFileName(
            None,
            "Choose cookies.txt",
            "",
            "Netscape cookie files (*.txt);;All files (*.*)",
        )
        if path:
            self._cookie_file = os.path.abspath(path)
            self._cookie_browser = ""
        # Also refresh the selector after a cancelled native dialog so it does
        # not remain visually stuck on an authentication mode that was not set.
        self.changed.emit()

    @Slot()
    def clearAuthentication(self):
        self._cookie_browser = ""
        self._cookie_file = ""
        self.changed.emit()

    @Slot(str, str, str, int, str, int)
    def inspect(self, url, platform, ranking, limit, duration_filter, scan_scope):
        self._prune_finished_runners()
        if not self._active_project_key or not self._active_project_root or self.busy:
            return
        try:
            request = ChannelImportRequest(
                url=str(url or ""),
                platform=str(platform or "").strip().lower(),
                ranking="popular" if str(ranking) == "popular" else "newest",
                limit=int(limit),
                duration_filter=str(duration_filter),
                scan_scope=int(scan_scope),
                cookie_browser=self._cookie_browser,
                cookie_file=self._cookie_file,
            )
        except ValueError as exc:
            session = ChannelImportSession(
                session_id=str(uuid.uuid4()),
                project_key=self._active_project_key,
                project_root=self._active_project_root,
                channel_url=str(url or "").strip(),
                request={
                    "url": str(url or "").strip(),
                    "platform": str(platform or "").strip().lower(),
                    "ranking": str(ranking or "newest"),
                    "limit": int(limit),
                    "duration_filter": str(duration_filter or "short"),
                    "scan_scope": int(scan_scope),
                },
                state="error",
                status=str(exc),
            )
            self._sessions[session.session_id] = session
            self._project_sessions[session.project_key] = session.session_id
            self._active_session_id = session.session_id
            self._refresh_active_model()
            return

        session = new_session(self._active_project_key, self._active_project_root, request)
        self._sessions[session.session_id] = session
        self._project_sessions[session.project_key] = session.session_id
        self._active_session_id = session.session_id
        cancel_event = threading.Event()
        self._cancel_events[session.session_id] = cancel_event
        self._scan_progress = 0
        save_session(session)
        self._refresh_active_model()

        def report(progress: int, detail: str) -> None:
            self._progressResolved.emit(session.session_id, "", progress, detail)

        def inspect_channel() -> None:
            try:
                platform, channel_name, candidates = scan_channel(
                    request,
                    self._existing_remote_keys.get(session.project_key, set()),
                    report,
                    cancel_event,
                )
                self._scanResolved.emit(
                    session.session_id,
                    {
                        "session_id": session.session_id,
                        "platform": platform,
                        "channel_name": channel_name,
                        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
                    },
                )
            except DownloadCancelled as exc:
                self._scanRejected.emit(session.session_id, str(exc), True)
            except Exception as exc:
                self._scanRejected.emit(session.session_id, str(exc), False)

        thread = threading.Thread(target=inspect_channel, name="channel-inspection", daemon=True)
        self._runner_threads[session.session_id] = thread
        thread.start()

    @Slot(int, bool)
    def setSelected(self, row, selected):
        candidate = self.candidates.candidate_at(int(row))
        if not candidate or candidate.duplicate or candidate.status in {"imported", "downloading", "importing"}:
            return
        candidate.selected = bool(selected)
        self.candidates.update_candidate(candidate.remote_video_id)
        self._save_active_session()
        self.changed.emit()

    @Slot(bool)
    def selectAll(self, selected):
        session = self._active_session()
        if not session:
            return
        for candidate in session.candidates:
            if not candidate.duplicate and candidate.status not in {"imported", "downloading", "importing"}:
                candidate.selected = bool(selected)
        self.candidates.set_candidates(session.candidates)
        self._save_active_session()
        self.changed.emit()

    def start_downloads(self, requested_workers: int = 2, only_candidate_id: str = "") -> str:
        self._prune_finished_runners()
        session = self._active_session()
        if not session or self.busy:
            return ""
        selected = [
            candidate
            for candidate in session.candidates
            if candidate.selected and not candidate.duplicate and candidate.status in {"ready", "failed"}
            and (not only_candidate_id or candidate.remote_video_id == only_candidate_id)
        ]
        if not selected:
            return ""
        request = ChannelImportRequest.model_validate(session.request)
        request.cookie_browser = self._cookie_browser
        request.cookie_file = self._cookie_file
        cancel_event = threading.Event()
        self._cancel_events[session.session_id] = cancel_event
        session.state = "downloading"
        session.status = f"Downloading {len(selected)} videos"
        for candidate in selected:
            candidate.status = "downloading"
            candidate.progress = 0
            candidate.error = ""
        self.candidates.set_candidates(session.candidates)
        self._save_active_session()
        self.changed.emit()
        max_workers = max(1, min(2, int(requested_workers)))

        def download_one(candidate: ChannelVideoCandidate):
            workspace = download_workspace(session.project_root, session.session_id, candidate.remote_video_id)
            self._workspaces[(session.session_id, candidate.remote_video_id)] = workspace
            path = download_candidate(
                candidate.model_copy(deep=True),
                request,
                workspace,
                lambda progress, detail: self._progressResolved.emit(
                    session.session_id,
                    candidate.remote_video_id,
                    progress,
                    detail,
                ),
                cancel_event,
            )
            return candidate, path, workspace

        def run_downloads() -> None:
            pending = list(selected)
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="channel-download") as executor:
                futures = {}
                while pending or futures:
                    if cancel_event.is_set() and pending:
                        for candidate in pending:
                            self._downloadRejected.emit(
                                session.session_id,
                                candidate.remote_video_id,
                                "Channel import cancelled.",
                                True,
                            )
                        pending.clear()

                    try:
                        live_limit = int(self._worker_limit_provider())
                    except (TypeError, ValueError, RuntimeError):
                        live_limit = 1
                    live_limit = max(1, min(max_workers, live_limit))
                    while pending and len(futures) < live_limit:
                        restricted_active = any(
                            candidate.platform in {"TikTok", "Douyin"}
                            for candidate in futures.values()
                        )
                        candidate_index = next(
                            (
                                index
                                for index, candidate in enumerate(pending)
                                if candidate.platform not in {"TikTok", "Douyin"}
                                or not restricted_active
                            ),
                            None,
                        )
                        if candidate_index is None:
                            break
                        candidate = pending.pop(candidate_index)
                        futures[executor.submit(download_one, candidate)] = candidate

                    if not futures:
                        cancel_event.wait(0.15)
                        continue
                    completed, _pending_futures = wait(
                        tuple(futures),
                        timeout=0.25,
                        return_when=FIRST_COMPLETED,
                    )
                    for future in completed:
                        candidate = futures.pop(future)
                        try:
                            resolved_candidate, path, workspace = future.result()
                            self._downloadResolved.emit(
                                session.session_id,
                                resolved_candidate.model_dump(mode="json"),
                                path,
                            )
                        except DownloadCancelled as exc:
                            self._downloadRejected.emit(
                                session.session_id,
                                candidate.remote_video_id,
                                str(exc),
                                True,
                            )
                        except Exception as exc:
                            self._downloadRejected.emit(
                                session.session_id,
                                candidate.remote_video_id,
                                str(exc),
                                False,
                            )
            self._batchResolved.emit(session.session_id)

        thread = threading.Thread(target=run_downloads, name="channel-download-manager", daemon=True)
        self._runner_threads[session.session_id] = thread
        thread.start()
        return session.session_id

    @Slot(int, result=bool)
    def retry(self, row):
        candidate = self.candidates.candidate_at(int(row))
        if not candidate or candidate.duplicate or candidate.status != "failed":
            return False
        candidate.selected = True
        return bool(self.start_downloads(1, candidate.remote_video_id))

    @Slot()
    def cancel(self):
        session = self._active_session()
        if not session or not self.busy:
            return
        event = self._cancel_events.get(session.session_id)
        if event:
            event.set()
        session.state = "cancelling"
        session.status = "Cancelling channel import"
        self._save_active_session()
        self.changed.emit()

    def complete_video(self, session_id: str, remote_video_id: str, success: bool, message: str = "") -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        candidate = next(
            (item for item in session.candidates if item.remote_video_id == remote_video_id),
            None,
        )
        if not candidate:
            return
        candidate.status = "imported" if success else "failed"
        candidate.progress = 100 if success else 0
        candidate.error = "" if success else str(message)
        if success:
            project_keys = self._existing_remote_keys.setdefault(session.project_key, set())
            project_keys.add(f"{candidate.platform.lower()}:{candidate.remote_video_id.lower()}")
            project_keys.add(normalize_remote_url(candidate.source_url))
        workspace = self._workspaces.pop((session_id, remote_video_id), "")
        if success:
            cleanup_channel_workspace(workspace)
        self._finalize_session_if_idle(session)
        self._save_session(session)
        if session_id == self._active_session_id:
            self.candidates.update_candidate(remote_video_id)
            self.changed.emit()

    def cancel_project(self, project_key: str) -> bool:
        self._prune_finished_runners()
        session_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if session.project_key == project_key
        ]
        for session_id in session_ids:
            event = self._cancel_events.get(session_id)
            if event:
                event.set()
        project_threads = [self._runner_threads.get(session_id) for session_id in session_ids]
        for thread in project_threads:
            if thread and thread.is_alive():
                thread.join(timeout=10)
        if any(thread and thread.is_alive() for thread in project_threads):
            return False
        for session_id in session_ids:
            self._sessions.pop(session_id, None)
            self._cancel_events.pop(session_id, None)
            self._runner_threads.pop(session_id, None)
        self._project_sessions.pop(project_key, None)
        if self._active_project_key == project_key:
            self._active_session_id = ""
            self._refresh_active_model()
        return True

    def shutdown(self, timeout_seconds: float = 5.0) -> bool:
        self._prune_finished_runners()
        for event in self._cancel_events.values():
            event.set()
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        for thread in tuple(self._runner_threads.values()):
            if thread.is_alive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                thread.join(timeout=remaining)
        return not any(thread.is_alive() for thread in self._runner_threads.values())

    def _handle_scan_resolved(self, session_id, payload):
        session = self._sessions.get(session_id)
        if not session:
            return
        session.platform = str(payload.get("platform") or "")
        session.channel_name = str(payload.get("channel_name") or "")
        session.candidates = [
            ChannelVideoCandidate.model_validate(candidate)
            for candidate in payload.get("candidates") or []
        ]
        session.state = "ready"
        session.status = f"{len(session.candidates)} videos ready to review"
        self._save_session(session)
        self._scan_progress = 100
        if session.session_id == self._active_session_id:
            self._refresh_active_model()

    def _handle_scan_rejected(self, session_id, message, cancelled):
        session = self._sessions.get(session_id)
        if not session:
            return
        session.state = "idle" if cancelled else "error"
        session.status = "Channel inspection cancelled" if cancelled else self._safe_message(message)
        self._save_session(session)
        if session_id == self._active_session_id:
            self.changed.emit()

    def _handle_download_progress(self, session_id, remote_video_id, progress, detail):
        session = self._sessions.get(session_id)
        if not session:
            return
        if not remote_video_id:
            if session_id == self._active_session_id:
                self._scan_progress = int(progress)
                session.status = str(detail)
                self.changed.emit()
            return
        candidate = next(
            (item for item in session.candidates if item.remote_video_id == remote_video_id),
            None,
        )
        if not candidate:
            return
        candidate.progress = int(progress)
        session.status = str(detail)
        if session_id == self._active_session_id:
            self.candidates.update_candidate(remote_video_id)
            self.changed.emit()

    def _handle_download_resolved(self, session_id, candidate_payload, path):
        session = self._sessions.get(session_id)
        candidate = ChannelVideoCandidate.model_validate(candidate_payload)
        if not session:
            cleanup_channel_workspace(self._workspaces.pop((session_id, candidate.remote_video_id), ""))
            return
        stored = next(
            (item for item in session.candidates if item.remote_video_id == candidate.remote_video_id),
            None,
        )
        if stored:
            stored.status = "importing"
            stored.progress = 100
        session.state = "importing"
        session.status = "Adding downloaded videos to the project"
        self._save_session(session)
        workspace = self._workspaces.get((session_id, candidate.remote_video_id), "")
        self.videoReady.emit(path, workspace, candidate_payload, session.project_key, session_id)
        if session_id == self._active_session_id:
            self.candidates.update_candidate(candidate.remote_video_id)
            self.changed.emit()

    def _handle_download_rejected(self, session_id, remote_video_id, message, cancelled):
        session = self._sessions.get(session_id)
        if not session:
            return
        candidate = next(
            (item for item in session.candidates if item.remote_video_id == remote_video_id),
            None,
        )
        if candidate:
            candidate.status = "failed"
            candidate.progress = 0
            candidate.error = "Download cancelled" if cancelled else self._safe_message(message)
        self._finalize_session_if_idle(session)
        self._save_session(session)
        if session_id == self._active_session_id:
            self.candidates.update_candidate(remote_video_id)
            self.changed.emit()

    def _handle_batch_resolved(self, session_id):
        session = self._sessions.get(session_id)
        if not session:
            return
        self._finalize_session_if_idle(session)
        self._save_session(session)
        self.downloadsFinished.emit(session_id)
        if session_id == self._active_session_id:
            self.changed.emit()

    def _finalize_session_if_idle(self, session: ChannelImportSession) -> None:
        if any(candidate.status in {"downloading", "importing"} for candidate in session.candidates):
            return
        failed = sum(candidate.status == "failed" for candidate in session.candidates)
        imported = sum(candidate.status == "imported" for candidate in session.candidates)
        session.state = "partial" if failed else "success"
        if failed:
            session.status = f"Imported {imported} videos; {failed} need attention"
        else:
            session.status = f"Imported {imported} videos"

    def _save_active_session(self) -> None:
        session = self._active_session()
        if session:
            self._save_session(session)

    @staticmethod
    def _save_session(session: ChannelImportSession) -> None:
        try:
            save_session(session)
        except OSError:
            pass
