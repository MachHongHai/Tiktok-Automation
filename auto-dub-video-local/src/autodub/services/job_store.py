import json
import os
import stat
import time
from datetime import datetime, timezone
from typing import List, Optional

from autodub.config import JOBS_DIR
from autodub.core.events import emit_log
from autodub.schemas.job import JobConfig, JobInfo


def get_job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id)


def get_job_json_path(job_id: str) -> str:
    return os.path.join(get_job_dir(job_id), "job.json")


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
    path = get_job_json_path(job_info.job_id)
    with open(path, "w", encoding="utf-8") as file:
        data = job_info.model_dump() if hasattr(job_info, "model_dump") else job_info.dict()
        json.dump(data, file, ensure_ascii=False, indent=2)


def get_job(job_id: str) -> Optional[JobInfo]:
    path = get_job_json_path(job_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
        return JobInfo(**data)


def update_job(job_id: str, **kwargs) -> Optional[JobInfo]:
    job_info = get_job(job_id)
    if not job_info:
        return None

    for key, value in kwargs.items():
        if hasattr(job_info, key):
            setattr(job_info, key, value)

    job_info.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    save_job(job_info)
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
