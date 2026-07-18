"""Desktop media-path helpers with no controller state."""

import os
import subprocess

from PySide6.QtCore import QUrl

from haizflow.services import job_store
from haizflow.services.desktop_jobs import SUPPORTED_VIDEO_EXTENSIONS


def normalize_video_path(value) -> str:
    raw_path = str(value).strip() if value else ""
    if not raw_path:
        return ""
    url = QUrl(raw_path)
    if url.isLocalFile():
        return os.path.abspath(url.toLocalFile())
    return os.path.abspath(raw_path)


def collect_batch_video_paths(paths):
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
        path = normalize_video_path(value)
        if os.path.isdir(path):
            try:
                with os.scandir(path) as entries:
                    for entry in sorted(entries, key=lambda item: item.name.lower()):
                        if entry.is_file():
                            if os.path.splitext(entry.name)[1].lower() in SUPPORTED_VIDEO_EXTENSIONS:
                                add_if_supported(entry.path)
                            else:
                                invalid_names.append(entry.name)
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


def resolve_job_file(job, keys, fallback_parts):
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


def create_video_thumbnail_path(path: str, output_path: str = "") -> str:
    if not path or not output_path or not os.path.exists(path):
        return ""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
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
    except (OSError, subprocess.SubprocessError):
        return ""


def thumbnail_source(path: str) -> str:
    """Return a local thumbnail URL that changes when its file is replaced."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        stat = os.stat(path)
    except OSError:
        return ""
    url = QUrl.fromLocalFile(os.path.abspath(path))
    url.setQuery(f"v={stat.st_mtime_ns}-{stat.st_size}")
    return url.toString()


def open_path(path) -> None:
    if not path:
        return
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", str(path)])
