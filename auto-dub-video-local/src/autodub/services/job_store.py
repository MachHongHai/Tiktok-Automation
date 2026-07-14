import json
import os
import stat
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

from autodub.config import JOBS_DIR
from autodub.core.events import emit_log
from autodub.schemas.job import JobConfig, JobInfo


_JOB_LOCKS: dict[str, threading.RLock] = {}
_JOB_LOCKS_GUARD = threading.Lock()


def _job_lock(job_id: str) -> threading.RLock:
    with _JOB_LOCKS_GUARD:
        lock = _JOB_LOCKS.get(job_id)
        if lock is None:
            lock = threading.RLock()
            _JOB_LOCKS[job_id] = lock
        return lock


def get_job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id)


def get_job_json_path(job_id: str) -> str:
    return os.path.join(get_job_dir(job_id), "job.json")


def _get_job_backup_path(job_id: str) -> str:
    return get_job_json_path(job_id) + ".bak"


def get_job_logs_path(job_id: str) -> str:
    return os.path.join(get_job_dir(job_id), "logs.txt")


def create_job(job_id: str, original_filename: str, config: JobConfig, video_ext: str = ".mp4") -> JobInfo:
    job_dir = get_job_dir(job_id)
    os.makedirs(job_dir, exist_ok=True)
    os.makedirs(os.path.join(job_dir, "input"), exist_ok=True)
    os.makedirs(os.path.join(job_dir, "temp"), exist_ok=True)
    os.makedirs(os.path.join(job_dir, "temp", "voice_parts"), exist_ok=True)
    os.makedirs(os.path.join(job_dir, "output"), exist_ok=True)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    files = {
        "video_input": os.path.join(job_dir, "input", f"video{video_ext}"),
        "final_video": os.path.join(job_dir, "output", "final.mp4"),
        "srt_output": os.path.join(job_dir, "temp", "vi.srt"),
        "voice_output": os.path.join(job_dir, "temp", "voice_final.wav"),
        "transcript_json": os.path.join(job_dir, "temp", "vi_segments.json"),
    }

    job_info = JobInfo(
        job_id=job_id,
        original_filename=original_filename,
        mode=config.mode,
        source_language=config.source_language,
        target_language=config.target_language,
        translator_provider=config.translator_provider,
        tts_voice=config.tts_voice,
        subtitle_style=config.subtitle_style,
        output_format=config.output_format,
        crop=config.crop,
        enable_audio_separation=config.enable_audio_separation,
        original_video_volume=config.original_video_volume,
        project_name=config.project_name,
        project_directory=config.project_directory,
        project_type=config.project_type,
        review_approved=config.review_approved,
        status="pending",
        progress=0,
        step="pending",
        created_at=now,
        updated_at=now,
        error=None,
        files=files,
    )

    save_job(job_info)
    with open(get_job_logs_path(job_id), "w", encoding="utf-8") as file:
        file.write(f"[{now}] Job created.\n")

    return job_info


def save_job(job_info: JobInfo):
    with _job_lock(job_info.job_id):
        _save_job_unlocked(job_info)


def _job_data(job_info: JobInfo) -> dict:
    return job_info.model_dump() if hasattr(job_info, "model_dump") else job_info.dict()


def _write_json_atomic(path: str, data: dict) -> None:
    """Write a complete JSON document before replacing the previous file."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(prefix=".job-", suffix=".json.tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass
        raise


def _save_job_unlocked(job_info: JobInfo) -> None:
    path = get_job_json_path(job_info.job_id)
    backup_path = _get_job_backup_path(job_info.job_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                previous_data = json.load(file)
            _write_json_atomic(backup_path, previous_data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # Preserve the last known-good backup if an older app version left a corrupt file.
            pass
    _write_json_atomic(path, _job_data(job_info))


def _get_job_unlocked(job_id: str) -> Optional[JobInfo]:
    path = get_job_json_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            return JobInfo(**json.load(file))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as original_error:
        backup_path = _get_job_backup_path(job_id)
        if not os.path.exists(backup_path):
            raise RuntimeError(f"Job metadata is unreadable: {path}") from original_error
        try:
            with open(backup_path, "r", encoding="utf-8") as file:
                recovered = JobInfo(**json.load(file))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as backup_error:
            raise RuntimeError(f"Job metadata and backup are unreadable: {path}") from backup_error
        _write_json_atomic(path, _job_data(recovered))
        log_to_job(job_id, "Recovered job metadata from the last atomic backup.")
        return recovered


def get_job(job_id: str) -> Optional[JobInfo]:
    with _job_lock(job_id):
        return _get_job_unlocked(job_id)


def update_job(job_id: str, **kwargs) -> Optional[JobInfo]:
    with _job_lock(job_id):
        job_info = _get_job_unlocked(job_id)
        if not job_info:
            return None

        for key, value in kwargs.items():
            if hasattr(job_info, key):
                setattr(job_info, key, value)

        job_info.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _save_job_unlocked(job_info)
        return job_info


def list_jobs() -> List[JobInfo]:
    if not os.path.exists(JOBS_DIR):
        return []
    jobs = []
    for job_id in os.listdir(JOBS_DIR):
        job_info = get_job(job_id)
        if job_info:
            jobs.append(job_info)
    jobs.sort(key=lambda item: item.created_at, reverse=True)
    return jobs


def log_to_job(job_id: str, message: str):
    log_path = get_job_logs_path(job_id)
    if not os.path.exists(get_job_json_path(job_id)) and not os.path.exists(log_path):
        return
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    line = f"[{now}] {message}"
    with open(log_path, "a", encoding="utf-8") as file:
        file.write(f"{line}\n")
    emit_log(job_id, line)


def _force_remove_readonly(func, path, _exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def delete_job(job_id: str, attempts: int = 8, delay_seconds: float = 0.35) -> bool:
    import shutil

    with _job_lock(job_id):
        job_dir = get_job_dir(job_id)
        if not os.path.exists(job_dir):
            return False

        last_error = None
        for attempt in range(attempts):
            try:
                shutil.rmtree(job_dir, onerror=_force_remove_readonly)
                return True
            except Exception as exc:
                last_error = exc
                time.sleep(delay_seconds * (attempt + 1))

        if os.path.exists(job_dir):
            raise RuntimeError(f"Could not delete job folder after {attempts} attempts: {last_error}")
        return True
