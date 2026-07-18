"""Download supported social videos into a project-owned staging directory."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from haizflow.config import BIN_DIR


SUPPORTED_VIDEO_HOSTS = {
    "douyin.com": "Douyin",
    "tiktok.com": "TikTok",
    "youtu.be": "YouTube",
    "youtube.com": "YouTube",
}
SUPPORTED_DOWNLOAD_EXTENSIONS = {".mp4", ".mov", ".mkv"}
_TIKTOK_TRANSIENT_ERROR_MARKERS = (
    "unable to extract universal data for rehydration",
    "unable to extract webpage video data",
    "unable to download api page",
    "http error 429",
    "http error 502",
    "http error 503",
    "http error 504",
    "timed out",
    "timeout",
)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class DownloadCancelled(RuntimeError):
    """Raised when the caller cancels metadata extraction or download."""


class _QuietLogger:
    """Keep downloader diagnostics inside the app's own error surface."""

    @staticmethod
    def debug(_message):
        pass

    @staticmethod
    def info(_message):
        pass

    @staticmethod
    def warning(_message):
        pass

    @staticmethod
    def error(_message):
        pass


@dataclass(frozen=True)
class VideoMetadata:
    url: str
    title: str
    platform: str
    duration_seconds: int
    thumbnail_url: str
    uploader: str

    def to_dict(self) -> dict:
        return asdict(self)


def _matching_platform(hostname: str) -> str:
    hostname = hostname.lower().rstrip(".")
    for domain, platform in SUPPORTED_VIDEO_HOSTS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return platform
    return ""


def validate_video_url(value: str) -> tuple[str, str]:
    """Return a normalized supported URL and its platform label."""
    url = str(value or "").strip()
    if not url:
        raise ValueError("Paste a video link first.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = f"https://{url}"

    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP or HTTPS video link.")
    platform = _matching_platform(parsed.hostname)
    if not platform:
        raise ValueError("Only YouTube, TikTok, and Douyin links are supported.")
    return url, platform


def _youtube_dl_options(auth: dict | None = None) -> dict:
    ffmpeg_location = BIN_DIR if os.path.isdir(BIN_DIR) else None
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "windowsfilenames": True,
        "logger": _QuietLogger(),
        # TikTok's webpage markup is intermittently unavailable. Supplying an
        # empty app profile makes yt-dlp try its supported app API first, then
        # fall back to the webpage extractor when that API is unavailable.
        "extractor_args": {"tiktok": {"app_info": [""]}},
    }
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    auth = auth or {}
    cookie_file = str(auth.get("cookie_file") or "").strip()
    cookie_browser = str(auth.get("cookie_browser") or "").strip().lower()
    if cookie_file:
        options["cookiefile"] = cookie_file
    elif cookie_browser in {"chrome", "edge"}:
        options["cookiesfrombrowser"] = (cookie_browser,)
    return options


def _load_yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("The video downloader is not installed in this app environment.") from exc
    return yt_dlp


def _friendly_error(exc: Exception) -> str:
    raw_message = _ANSI_ESCAPE.sub("", str(exc)).strip()
    message = raw_message.splitlines()[-1] if raw_message else exc.__class__.__name__
    message = re.sub(r"^ERROR:\s*", "", message, flags=re.IGNORECASE)
    if len(message) > 320:
        message = f"{message[:317]}..."
    return message


def _is_retryable_tiktok_error(exc: Exception) -> bool:
    message = _ANSI_ESCAPE.sub("", str(exc)).lower()
    return any(marker in message for marker in _TIKTOK_TRANSIENT_ERROR_MARKERS)


def _wait_for_retry(cancel_event: threading.Event | None, seconds: float) -> None:
    if cancel_event:
        if cancel_event.wait(seconds):
            raise DownloadCancelled("Link inspection cancelled.")
        return
    time.sleep(seconds)


def _inspect_video_info(yt_dlp, url: str) -> dict:
    with yt_dlp.YoutubeDL(_youtube_dl_options()) as downloader:
        return downloader.extract_info(url, download=False)


def inspect_video_url(url: str, cancel_event: threading.Event | None = None) -> VideoMetadata:
    normalized_url, platform = validate_video_url(url)
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Link inspection cancelled.")

    yt_dlp = _load_yt_dlp()
    attempts = 2 if platform == "TikTok" else 1
    info = None
    for attempt in range(attempts):
        try:
            info = _inspect_video_info(yt_dlp, normalized_url)
            break
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Link inspection cancelled.") from exc
            if attempt + 1 < attempts and _is_retryable_tiktok_error(exc):
                _wait_for_retry(cancel_event, 0.6)
                continue
            raise RuntimeError(_friendly_error(exc)) from exc

    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Link inspection cancelled.")
    if not isinstance(info, dict):
        raise RuntimeError("The video service returned no usable metadata.")
    if info.get("_type") in {"playlist", "multi_video"} or info.get("entries"):
        raise ValueError("Paste a link to one video, not a playlist or channel.")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
        raise ValueError("Live and upcoming streams are not supported.")

    resolved_platform = str(info.get("extractor_key") or info.get("extractor") or platform).strip()
    if "youtube" in resolved_platform.lower():
        resolved_platform = "YouTube"
    elif "tiktok" in resolved_platform.lower():
        resolved_platform = "TikTok"
    elif "douyin" in resolved_platform.lower():
        resolved_platform = "Douyin"

    title = str(info.get("title") or "Untitled video").strip()
    return VideoMetadata(
        url=str(info.get("webpage_url") or normalized_url),
        title=title,
        platform=resolved_platform or platform,
        duration_seconds=max(0, int(info.get("duration") or 0)),
        thumbnail_url=str(info.get("thumbnail") or ""),
        uploader=str(info.get("uploader") or info.get("channel") or "").strip(),
    )


def create_download_workspace(project_root: str) -> str:
    downloads_directory = os.path.join(os.path.abspath(project_root), ".downloads")
    os.makedirs(downloads_directory, exist_ok=True)
    return tempfile.mkdtemp(prefix="video-", dir=downloads_directory)


def cleanup_download_workspace(workspace: str) -> None:
    if not workspace:
        return
    workspace_path = Path(workspace).resolve()
    parent = workspace_path.parent
    if parent.name != ".downloads":
        return
    shutil.rmtree(workspace_path, ignore_errors=True)
    try:
        parent.rmdir()
    except OSError:
        pass


def _downloaded_video_path(workspace: str, info: dict, downloader) -> str:
    workspace = os.path.abspath(workspace)
    candidates = [info.get("filepath"), info.get("_filename")]
    for item in info.get("requested_downloads") or []:
        if isinstance(item, dict):
            candidates.extend([item.get("filepath"), item.get("filename")])
    try:
        candidates.append(downloader.prepare_filename(info))
    except Exception:
        pass

    expanded = []
    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.abspath(str(candidate))
        expanded.append(candidate)
        stem, _extension = os.path.splitext(candidate)
        expanded.extend(f"{stem}{extension}" for extension in SUPPORTED_DOWNLOAD_EXTENSIONS)
    for candidate in expanded:
        try:
            inside_workspace = os.path.commonpath([workspace, candidate]) == workspace
        except ValueError:
            inside_workspace = False
        if (
            inside_workspace
            and os.path.isfile(candidate)
            and os.path.splitext(candidate)[1].lower() in SUPPORTED_DOWNLOAD_EXTENSIONS
        ):
            return candidate

    discovered = [
        path
        for path in Path(workspace).glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_DOWNLOAD_EXTENSIONS
    ]
    if not discovered:
        raise RuntimeError("The download finished but no supported video file was produced.")
    return str(max(discovered, key=lambda path: path.stat().st_mtime))


def download_video(
    metadata: VideoMetadata,
    workspace: str,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    auth: dict | None = None,
) -> str:
    """Download one video and return its final MP4/MOV/MKV path."""
    os.makedirs(workspace, exist_ok=True)
    yt_dlp = _load_yt_dlp()
    last_update = {"progress": -1, "time": 0.0}

    def report(progress: int, detail: str) -> None:
        progress = max(0, min(100, int(progress)))
        now = time.monotonic()
        if progress == last_update["progress"] and now - last_update["time"] < 0.25:
            return
        last_update.update(progress=progress, time=now)
        if progress_callback:
            progress_callback(progress, detail)

    def progress_hook(event: dict) -> None:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Video download cancelled.")
        status = event.get("status")
        if status == "downloading":
            downloaded = int(event.get("downloaded_bytes") or 0)
            total = int(event.get("total_bytes") or event.get("total_bytes_estimate") or 0)
            progress = round(downloaded * 100 / total) if total else 0
            speed = float(event.get("speed") or 0)
            detail = f"{_format_bytes(downloaded)}"
            if total:
                detail += f" / {_format_bytes(total)}"
            if speed:
                detail += f"  |  {_format_bytes(speed)}/s"
            report(min(progress, 99), detail)
        elif status == "finished":
            report(99, "Finalizing video")

    options = _youtube_dl_options(auth)
    options.update(
        {
            "outtmpl": os.path.join(workspace, "%(title).120B [%(id)s].%(ext)s"),
            "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]",
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
            "progress_hooks": [progress_hook],
            "concurrent_fragment_downloads": 4,
        }
    )

    report(0, "Starting download")
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(metadata.url, download=True)
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Video download cancelled.")
            video_path = _downloaded_video_path(workspace, info, downloader)
    except DownloadCancelled:
        raise
    except Exception as exc:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Video download cancelled.") from exc
        raise RuntimeError(_friendly_error(exc)) from exc

    report(100, "Download complete")
    return video_path


def _format_bytes(value: float) -> str:
    size = max(0.0, float(value))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
