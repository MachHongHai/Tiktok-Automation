"""Channel/profile inspection and project-owned import-session storage."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from haizflow.schemas.channel_import import (
    ChannelImportRequest,
    ChannelImportSession,
    ChannelVideoCandidate,
)
from haizflow.services.video_download import (
    DownloadCancelled,
    VideoMetadata,
    _is_retryable_tiktok_error,
    _load_yt_dlp,
    _wait_for_retry,
    _youtube_dl_options,
    download_video,
)


ProgressCallback = Callable[[int, str], None]
SUPPORTED_CHANNEL_HOSTS = {
    "youtube.com": "YouTube",
    "tiktok.com": "TikTok",
    "douyin.com": "Douyin",
}
SHORT_VIDEO_SECONDS = 180
SESSION_SCHEMA_VERSION = 1
VIDEO_EXTENSIONS = {"mkv", "mov", "mp4", "webm"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _platform_for_host(hostname: str) -> str:
    hostname = str(hostname or "").lower().rstrip(".")
    for domain, platform in SUPPORTED_CHANNEL_HOSTS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return platform
    return ""


def validate_channel_url(value: str, expected_platform: str = "") -> tuple[str, str]:
    url = str(value or "").strip()
    if not url:
        raise ValueError("Paste a channel or profile link first.")
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP or HTTPS channel link.")
    platform = _platform_for_host(parsed.hostname)
    if not platform:
        raise ValueError("Only YouTube, TikTok, and Douyin channels are supported.")
    expected = str(expected_platform or "").strip().lower()
    platform_key = platform.lower()
    if expected and expected != platform_key:
        raise ValueError("The link does not match the selected platform.")

    path = parsed.path.rstrip("/")
    lowered_path = path.lower()
    if platform == "YouTube":
        if parsed.hostname.lower().endswith("youtu.be") or lowered_path.startswith(("/watch", "/shorts/")):
            raise ValueError("Paste a YouTube channel link, not an individual video link.")
        valid_prefixes = ("/@", "/channel/", "/c/", "/user/")
        if not lowered_path.startswith(valid_prefixes):
            raise ValueError("Paste a YouTube channel link.")
    elif platform == "TikTok":
        if "/video/" in lowered_path or not lowered_path.startswith("/@"):
            raise ValueError("Paste a TikTok profile link, not an individual video link.")
    elif platform == "Douyin" and "/video/" in lowered_path:
        raise ValueError("Paste a Douyin profile link, not an individual video link.")
    elif platform == "Douyin" and "/user/" not in lowered_path and not parsed.hostname.lower().startswith("v."):
        raise ValueError("Paste a Douyin profile link.")

    normalized = urlunparse(("https", parsed.netloc.lower(), path or "/", "", "", ""))
    return normalized, platform


def normalize_remote_url(value: str) -> str:
    """Return a stable URL key without tracking parameters or fragments."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = str(parsed.hostname or "").lower().rstrip(".")
    if not host:
        return raw.lower()
    path = parsed.path.rstrip("/") or "/"
    query = ""
    if host == "youtube.com" or host.endswith(".youtube.com"):
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        if video_id:
            query = urlencode({"v": video_id})
    return urlunparse(("https", host, path, "", query, ""))


def _auth_options(request: ChannelImportRequest) -> dict:
    return {
        "cookie_browser": str(request.cookie_browser or "").strip().lower(),
        "cookie_file": str(request.cookie_file or "").strip(),
    }


def _candidate_url(platform: str, entry: dict) -> str:
    value = str(entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or "").strip()
    remote_id = str(entry.get("id") or entry.get("display_id") or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    if platform == "YouTube" and remote_id:
        return f"https://www.youtube.com/watch?v={remote_id}"
    if platform == "TikTok" and remote_id:
        uploader_id = str(entry.get("uploader_id") or entry.get("channel_id") or "_").strip("@") or "_"
        return f"https://www.tiktok.com/@{uploader_id}/video/{remote_id}"
    if platform == "Douyin" and remote_id:
        return f"https://www.douyin.com/video/{remote_id}"
    return ""


def _published_value(entry: dict) -> str:
    upload_date = str(entry.get("upload_date") or "").strip()
    if upload_date:
        return upload_date
    timestamp = entry.get("timestamp") or entry.get("release_timestamp")
    try:
        return datetime.fromtimestamp(float(timestamp), timezone.utc).strftime("%Y%m%d")
    except (TypeError, ValueError, OSError):
        return ""


def _entry_candidate(
    platform: str,
    entry: dict,
    *,
    content_type: str = "",
) -> ChannelVideoCandidate | None:
    if not isinstance(entry, dict):
        return None
    if entry.get("is_live") or entry.get("live_status") in {"is_live", "is_upcoming"}:
        return None
    if str(entry.get("availability") or "").lower() in {"private", "premium_only", "subscriber_only"}:
        return None
    remote_id = str(entry.get("id") or entry.get("display_id") or "").strip()
    source_url = _candidate_url(platform, entry)
    if not remote_id or not source_url:
        return None
    thumbnails = entry.get("thumbnails") or []
    thumbnail = str(entry.get("thumbnail") or "")
    if not thumbnail and thumbnails:
        last_thumbnail = thumbnails[-1] if isinstance(thumbnails[-1], dict) else {}
        thumbnail = str(last_thumbnail.get("url") or "")
    view_count = entry.get("view_count") or entry.get("play_count")
    try:
        view_count = int(view_count) if view_count is not None else None
    except (TypeError, ValueError):
        view_count = None
    return ChannelVideoCandidate(
        remote_video_id=remote_id,
        source_url=source_url,
        title=str(entry.get("title") or entry.get("description") or f"Video {remote_id}").strip(),
        platform=platform,
        content_type=content_type if content_type in {"short", "long"} else "",
        uploader=str(entry.get("uploader") or entry.get("channel") or entry.get("creator") or "").strip(),
        duration_seconds=max(0, int(entry.get("duration") or 0)),
        published_at=_published_value(entry),
        view_count=view_count,
        thumbnail_url=thumbnail,
    )


def _merge_candidate(candidate: ChannelVideoCandidate, info: dict) -> ChannelVideoCandidate:
    refreshed = _entry_candidate(candidate.platform, {**info, "id": candidate.remote_video_id})
    if not refreshed:
        return candidate
    refreshed.source_url = candidate.source_url or refreshed.source_url
    refreshed.title = refreshed.title or candidate.title
    refreshed.uploader = refreshed.uploader or candidate.uploader
    refreshed.thumbnail_url = refreshed.thumbnail_url or candidate.thumbnail_url
    refreshed.published_at = refreshed.published_at or candidate.published_at
    refreshed.duration_seconds = refreshed.duration_seconds or candidate.duration_seconds
    refreshed.view_count = refreshed.view_count if refreshed.view_count is not None else candidate.view_count
    refreshed.content_type = candidate.content_type or refreshed.content_type
    return refreshed


def _is_non_video_metadata(info: dict) -> bool:
    # TikTok photo posts carry an images payload even when the extractor also
    # exposes a music track. They are not valid inputs for the video pipeline.
    if info.get("images"):
        return True
    formats = info.get("formats")
    if isinstance(formats, list) and formats:
        usable_formats = [item for item in formats if isinstance(item, dict)]
        return bool(usable_formats) and all(
            str(item.get("vcodec") or "").lower() == "none"
            for item in usable_formats
        )
    entries = info.get("entries")
    if info.get("_type") == "playlist" and isinstance(entries, list) and entries:
        image_extensions = {"avif", "bmp", "gif", "heic", "jpeg", "jpg", "png", "webp"}
        usable_entries = [item for item in entries if isinstance(item, dict)]
        return bool(usable_entries) and all(
            str(item.get("ext") or "").lower() in image_extensions
            or (
                str(item.get("vcodec") or "").lower() == "none"
                and str(item.get("ext") or "").lower() not in VIDEO_EXTENSIONS
            )
            for item in usable_entries
        )
    return False


def _extract_info_with_platform_retry(
    platform: str,
    options: dict,
    url: str,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Retry TikTok's known transient rehydration error once."""
    yt_dlp = _load_yt_dlp()
    attempts = 2 if platform == "TikTok" else 1
    for attempt in range(attempts):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Channel inspection cancelled.")
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=False)
            return info if isinstance(info, dict) else {}
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Channel inspection cancelled.") from exc
            if attempt + 1 < attempts and _is_retryable_tiktok_error(exc):
                _wait_for_retry(cancel_event, 0.6)
                continue
            raise
    return {}


def _hydrate_candidate(
    candidate: ChannelVideoCandidate,
    auth: dict,
    cancel_event: threading.Event | None = None,
) -> ChannelVideoCandidate | None:
    options = _youtube_dl_options(auth)
    options["noplaylist"] = True
    info = _extract_info_with_platform_retry(candidate.platform, options, candidate.source_url, cancel_event)
    if _is_non_video_metadata(info):
        return None
    return _merge_candidate(candidate, info)


def _needs_hydration(candidate: ChannelVideoCandidate, request: ChannelImportRequest) -> bool:
    return (
        candidate.platform == "TikTok"
        or candidate.duration_seconds <= 0
        or not candidate.published_at
        or (request.ranking == "popular" and candidate.view_count is None)
    )


def _passes_duration(candidate: ChannelVideoCandidate, duration_filter: str) -> bool:
    if duration_filter == "all":
        return True
    # YouTube's /videos and /shorts tabs are the source of truth. Music videos
    # are often under three minutes but are still regular videos, not Shorts.
    if candidate.platform == "YouTube" and candidate.content_type:
        return candidate.content_type == duration_filter
    # TikTok, Douyin, and legacy session candidates do not expose a reliable
    # channel-tab classification, so retain the duration fallback for them.
    if candidate.duration_seconds <= 0:
        return False
    if duration_filter == "short":
        return candidate.duration_seconds <= SHORT_VIDEO_SECONDS
    return candidate.duration_seconds > SHORT_VIDEO_SECONDS


def _youtube_collection_sources(channel_url: str, duration_filter: str) -> list[tuple[str, str]]:
    parsed = urlparse(channel_url)
    path = parsed.path.rstrip("/")
    for suffix in ("/videos", "/shorts", "/streams"):
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)]
            break
    base = urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    if duration_filter == "short":
        return [(f"{base}/shorts", "short")]
    if duration_filter == "long":
        return [(f"{base}/videos", "long")]
    return [(f"{base}/videos", "long"), (f"{base}/shorts", "short")]


def _youtube_collection_urls(channel_url: str, duration_filter: str) -> list[str]:
    """Return collection URLs for compatibility with callers and tests."""
    return [url for url, _content_type in _youtube_collection_sources(channel_url, duration_filter)]


def _scan_with_ytdlp(
    request: ChannelImportRequest,
    platform: str,
    progress_callback: ProgressCallback | None,
    cancel_event: threading.Event,
) -> tuple[str, list[ChannelVideoCandidate]]:
    # For newest-first imports the requested count is the actual scan budget.
    # Do not silently expand a request for 20 posts into 60 metadata requests.
    scan_limit = request.scan_scope if request.ranking == "popular" else request.limit
    collection_sources = (
        _youtube_collection_sources(request.url, request.duration_filter)
        if platform == "YouTube"
        else [(request.url, "")]
    )
    per_collection_limit = scan_limit
    if scan_limit and len(collection_sources) > 1:
        per_collection_limit = max(1, (scan_limit + len(collection_sources) - 1) // len(collection_sources))
    if progress_callback:
        progress_callback(5, "Reading channel videos")
    channel_name = ""
    entries = []
    for collection_url, content_type in collection_sources:
        options = _youtube_dl_options(_auth_options(request))
        options.update(
            {
                "noplaylist": False,
                "extract_flat": "in_playlist",
                "ignoreerrors": True,
                "lazy_playlist": False,
                "playlistend": per_collection_limit or None,
            }
        )
        info = _extract_info_with_platform_retry(platform, options, collection_url, cancel_event)
        if cancel_event.is_set():
            raise DownloadCancelled("Channel inspection cancelled.")
        if not isinstance(info, dict):
            continue
        channel_name = channel_name or str(
            info.get("channel") or info.get("uploader") or info.get("title") or ""
        ).strip()
        entries.extend((entry, content_type) for entry in (info.get("entries") or []))
    if not entries:
        raise RuntimeError("The channel returned no public videos.")

    candidates = []
    seen_ids = set()
    seen_urls = set()
    for entry, content_type in entries:
        if cancel_event.is_set():
            raise DownloadCancelled("Channel inspection cancelled.")
        candidate = _entry_candidate(platform, entry, content_type=content_type)
        if not candidate:
            continue
        normalized_candidate_url = normalize_remote_url(candidate.source_url)
        if candidate.remote_video_id in seen_ids or normalized_candidate_url in seen_urls:
            continue
        seen_ids.add(candidate.remote_video_id)
        seen_urls.add(normalized_candidate_url)
        candidates.append(candidate)

    to_hydrate = [candidate for candidate in candidates if _needs_hydration(candidate, request)]
    if to_hydrate:
        workers = 1 if platform == "TikTok" else min(4, len(to_hydrate))
        hydrated_by_id = {}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="channel-metadata") as executor:
            futures = {
                executor.submit(_hydrate_candidate, candidate, _auth_options(request), cancel_event): candidate
                for candidate in to_hydrate
            }
            completed = 0
            for future in as_completed(futures):
                if cancel_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    raise DownloadCancelled("Channel inspection cancelled.")
                candidate = futures[future]
                try:
                    hydrated_by_id[candidate.remote_video_id] = future.result()
                except DownloadCancelled:
                    raise
                except Exception:
                    # TikTok photo posts and slideshows can look like ordinary
                    # flat-playlist entries. If details cannot prove that the
                    # entry has a video stream, exclude it from a video batch.
                    hydrated_by_id[candidate.remote_video_id] = (
                        None if platform == "TikTok" else candidate
                    )
                completed += 1
                if progress_callback:
                    progress_callback(
                        10 + round(completed * 75 / len(to_hydrate)),
                        f"Reading video details {completed}/{len(to_hydrate)}",
                    )
        hydrated_candidates = []
        for candidate in candidates:
            resolved = hydrated_by_id.get(candidate.remote_video_id, candidate)
            if resolved is not None:
                hydrated_candidates.append(resolved)
        candidates = hydrated_candidates
    return channel_name, candidates


def _douyin_worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--douyin-channel-worker"]
    return [sys.executable, "-m", "haizflow.services.douyin_channel_worker"]


def _scan_douyin(
    request: ChannelImportRequest,
    progress_callback: ProgressCallback | None,
    cancel_event: threading.Event,
) -> tuple[str, list[ChannelVideoCandidate]]:
    if progress_callback:
        progress_callback(5, "Starting isolated Douyin Beta inspector")
    payload = request.model_dump()
    payload.update(_auth_options(request))
    process = subprocess.Popen(
        _douyin_worker_command(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    input_text = json.dumps(payload, ensure_ascii=False)
    while process.poll() is None:
        if cancel_event.wait(0.15):
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
            raise DownloadCancelled("Channel inspection cancelled.")
        if process.stdin:
            process.stdin.write(input_text)
            process.stdin.close()
            process.stdin = None
            input_text = ""
    stdout = process.stdout.read() if process.stdout else ""
    stderr = process.stderr.read() if process.stderr else ""
    if process.returncode != 0:
        raise RuntimeError((stderr or stdout or "Douyin Beta inspector stopped unexpectedly.").strip())
    try:
        response = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Douyin Beta inspector returned invalid data.") from exc
    if response.get("error"):
        raise RuntimeError(str(response["error"]))
    candidates = [ChannelVideoCandidate.model_validate(item) for item in response.get("candidates") or []]
    return str(response.get("channel_name") or ""), candidates


def scan_channel(
    request: ChannelImportRequest,
    existing_remote_keys: Iterable[str] = (),
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[str, str, list[ChannelVideoCandidate]]:
    normalized_url, platform = validate_channel_url(request.url, request.platform)
    request.url = normalized_url
    cancel_event = cancel_event or threading.Event()
    if platform == "Douyin":
        channel_name, candidates = _scan_douyin(request, progress_callback, cancel_event)
    else:
        channel_name, candidates = _scan_with_ytdlp(request, platform, progress_callback, cancel_event)
    existing = {str(value).lower() for value in existing_remote_keys}
    existing.update(normalize_remote_url(value) for value in existing_remote_keys)
    candidates = [candidate for candidate in candidates if _passes_duration(candidate, request.duration_filter)]
    if request.ranking == "popular":
        candidates.sort(
            key=lambda item: (item.view_count is not None, item.view_count or -1, item.published_at),
            reverse=True,
        )
    else:
        # YouTube channel tabs are already newest-first. Flat playlist entries
        # often omit upload_date; preserving their source order is the only
        # reliable fallback because a YouTube video ID is not chronological.
        if platform != "YouTube" or request.duration_filter == "all":
            dated_count = sum(bool(item.published_at) for item in candidates)
            if dated_count == len(candidates):
                candidates.sort(key=lambda item: item.published_at, reverse=True)
            elif dated_count:
                candidates.sort(
                    key=lambda item: (bool(item.published_at), item.published_at),
                    reverse=True,
                )
    candidates = candidates[: request.limit]
    for candidate in candidates:
        key = f"{candidate.platform.lower()}:{candidate.remote_video_id}".lower()
        url_key = normalize_remote_url(candidate.source_url)
        candidate.duplicate = key in existing or url_key in existing
        candidate.selected = not candidate.duplicate
        if candidate.duplicate:
            candidate.status = "duplicate"
    if progress_callback:
        progress_callback(100, f"Found {len(candidates)} videos")
    return platform, channel_name, candidates


def channel_session_root(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), "imports", "channel")


def session_directory(project_root: str, session_id: str) -> str:
    safe_id = "".join(character for character in str(session_id) if character.isalnum() or character in {"-", "_"})
    if not safe_id:
        raise ValueError("Invalid channel import session id.")
    return os.path.join(channel_session_root(project_root), safe_id)


def download_workspace(project_root: str, session_id: str, remote_video_id: str) -> str:
    safe_video_id = "".join(
        character for character in str(remote_video_id) if character.isalnum() or character in {"-", "_"}
    ) or str(uuid.uuid4())
    path = os.path.join(session_directory(project_root, session_id), "downloads", safe_video_id)
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_channel_workspace(workspace: str) -> None:
    if not workspace:
        return
    workspace_path = Path(workspace).resolve()
    if workspace_path.parent.name != "downloads":
        return
    shutil.rmtree(workspace_path, ignore_errors=True)
    try:
        workspace_path.parent.rmdir()
    except OSError:
        pass


def _write_json_atomic(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".channel-session-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        raise


def save_session(session: ChannelImportSession) -> None:
    session.updated_at = _now()
    directory = session_directory(session.project_root, session.session_id)
    _write_json_atomic(os.path.join(directory, "session.json"), session.model_dump(mode="json"))


def load_latest_session(project_root: str) -> ChannelImportSession | None:
    root = Path(channel_session_root(project_root))
    if not root.is_dir():
        return None
    sessions = []
    for path in root.glob("*/session.json"):
        try:
            with path.open("r", encoding="utf-8") as file:
                sessions.append(ChannelImportSession.model_validate(json.load(file)))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return max(sessions, key=lambda item: item.updated_at) if sessions else None


def new_session(project_key: str, project_root: str, request: ChannelImportRequest) -> ChannelImportSession:
    return ChannelImportSession(
        schema_version=SESSION_SCHEMA_VERSION,
        session_id=str(uuid.uuid4()),
        project_key=project_key,
        project_root=os.path.abspath(project_root),
        channel_url=request.url,
        request=request.model_dump(),
        state="inspecting",
        status="Reading channel",
    )


def download_candidate(
    candidate: ChannelVideoCandidate,
    request: ChannelImportRequest,
    workspace: str,
    progress_callback: ProgressCallback | None,
    cancel_event: threading.Event,
) -> str:
    metadata = VideoMetadata(
        url=candidate.source_url,
        title=candidate.title,
        platform=candidate.platform,
        duration_seconds=candidate.duration_seconds,
        thumbnail_url=candidate.thumbnail_url,
        uploader=candidate.uploader,
    )
    return download_video(metadata, workspace, progress_callback, cancel_event, _auth_options(request))
