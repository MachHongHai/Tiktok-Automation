import json
import os
import shutil
import stat
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

from haizflow.config import JOBS_DIR
from haizflow.core.events import emit_log
from haizflow.schemas.job import (
    VIDEO_METADATA_SCHEMA_VERSION,
    VIDEO_METADATA_TYPE,
    JobConfig,
    JobInfo,
    MediaSource,
)
from haizflow.services import project_store


_JOB_LOCKS: dict[str, threading.RLock] = {}
_JOB_LOCKS_GUARD = threading.Lock()
_JOB_DIR_CACHE: dict[str, str] = {}


def _job_lock(job_id: str) -> threading.RLock:
    with _JOB_LOCKS_GUARD:
        lock = _JOB_LOCKS.get(job_id)
        if lock is None:
            lock = threading.RLock()
            _JOB_LOCKS[job_id] = lock
        return lock


def _legacy_job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id)


def _project_job_dir(job_id: str, config: JobConfig) -> str:
    if config.project_name.strip() and config.project_directory.strip():
        videos_dir = (
            project_store.project_videos_dir_for_key(config.project_key)
            if config.project_key
            else project_store.project_videos_dir(config.project_name, config.project_directory, config.project_type)
        )
        return os.path.join(
            videos_dir,
            job_id,
        )
    return _legacy_job_dir(job_id)


def _find_job_dir(job_id: str) -> str:
    cached = _JOB_DIR_CACHE.get(job_id)
    if cached and os.path.isdir(cached):
        return cached
    _JOB_DIR_CACHE.pop(job_id, None)

    legacy = _legacy_job_dir(job_id)
    if os.path.isdir(legacy):
        _JOB_DIR_CACHE[job_id] = legacy
        return legacy

    for project in project_store.list_projects():
        candidate = os.path.join(
            project_store.project_videos_dir_for_key(project["key"]),
            job_id,
        )
        if os.path.isdir(candidate):
            _JOB_DIR_CACHE[job_id] = candidate
            return candidate
    return legacy


def get_job_dir(job_id: str) -> str:
    return _find_job_dir(job_id)


def get_job_json_path(job_id: str) -> str:
    return os.path.join(get_job_dir(job_id), "job.json")


def _get_job_backup_path(job_id: str) -> str:
    return get_job_json_path(job_id) + ".bak"


def get_job_logs_path(job_id: str) -> str:
    return os.path.join(get_job_dir(job_id), "logs.txt")


def create_job(job_id: str, original_filename: str, config: JobConfig, video_ext: str = ".mp4") -> JobInfo:
    job_dir = _project_job_dir(job_id, config)
    _JOB_DIR_CACHE[job_id] = job_dir
    os.makedirs(job_dir, exist_ok=True)
    os.makedirs(os.path.join(job_dir, "input"), exist_ok=True)
    os.makedirs(os.path.join(job_dir, "temp"), exist_ok=True)
    os.makedirs(os.path.join(job_dir, "temp", "voice_parts"), exist_ok=True)
    project_owned = bool(config.project_name and config.project_directory)
    # Modern desktop projects export through <project>/exports. Preserve the
    # per-video output folder only for legacy jobs without a project owner.
    if not project_owned:
        os.makedirs(os.path.join(job_dir, "output"), exist_ok=True)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if project_owned:
        export_dir = (
            project_store.project_exports_dir_for_key(config.project_key)
            if config.project_key
            else project_store.project_exports_dir(config.project_name, config.project_directory, config.project_type)
        )
        if config.project_type == "batch":
            safe_stem = "".join(
                character if character.isalnum() or character in {"-", "_", " "} else "_"
                for character in os.path.splitext(original_filename)[0]
            ).strip()
            export_dir = os.path.join(export_dir, f"{safe_stem or 'video'}-{job_id[:8]}")
        os.makedirs(export_dir, exist_ok=True)
        final_video = os.path.join(export_dir, "dubbed_video.mp4")
    else:
        final_video = os.path.join(job_dir, "output", "final.mp4")
    files = {
        "video_input": os.path.join(job_dir, "input", f"video{video_ext}"),
        "final_video": final_video,
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
        project_id=config.project_id,
        project_key=config.project_key,
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


def _job_data(job_info: JobInfo) -> dict:
    data = job_info.model_dump() if hasattr(job_info, "model_dump") else job_info.dict()
    data["schema_version"] = VIDEO_METADATA_SCHEMA_VERSION
    data["metadata_type"] = VIDEO_METADATA_TYPE
    return data


def _write_json_atomic(path: str, data: dict) -> None:
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


class VideoMetadataError(RuntimeError):
    pass


class UnsupportedVideoSchemaError(VideoMetadataError):
    pass


def _video_schema_version(data: dict) -> int:
    raw_version = data.get("schema_version", 1)
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise VideoMetadataError(f"Video metadata has an invalid schema version: {raw_version!r}") from exc
    if version < 1:
        raise VideoMetadataError(f"Video metadata has an invalid schema version: {version}")
    if version > VIDEO_METADATA_SCHEMA_VERSION:
        raise UnsupportedVideoSchemaError(
            f"Video metadata uses schema v{version}, newer than supported v{VIDEO_METADATA_SCHEMA_VERSION}."
        )
    return version


def _migrate_video_metadata(raw_data: dict) -> tuple[dict, bool]:
    if not isinstance(raw_data, dict):
        raise VideoMetadataError("Video metadata must contain a JSON object.")
    original = dict(raw_data)
    data = dict(raw_data)
    version = _video_schema_version(data)
    while version < VIDEO_METADATA_SCHEMA_VERSION:
        if version == 1:
            data["schema_version"] = 2
            data["metadata_type"] = VIDEO_METADATA_TYPE
            data["mode"] = data.get("mode") if data.get("mode") in {"A", "review"} else "A"
            data["source_language"] = "auto"
            data["translator_provider"] = "hymt2"
            data["output_format"] = "keep_ratio"
            data["project_type"] = "batch" if data.get("project_type") == "batch" else "single"
            version = 2
            continue
        if version == 2:
            data["schema_version"] = 3
            data["media_source"] = {"type": "local_file"}
            version = 3
            continue
        if version == 3:
            project_name = str(data.get("project_name") or "").strip()
            project_directory = str(data.get("project_directory") or "").strip()
            project_type = "batch" if data.get("project_type") == "batch" else "single"
            key = project_store.resolve_project_key(project_name, project_directory, project_type)
            record = project_store.get_project(key) if key else None
            data["schema_version"] = 4
            data["project_key"] = key
            data["project_id"] = str((record or {}).get("project_id") or "")
            version = 4
            continue
        raise VideoMetadataError(f"No video metadata migration is available from schema v{version}.")
    data["schema_version"] = VIDEO_METADATA_SCHEMA_VERSION
    data["metadata_type"] = VIDEO_METADATA_TYPE
    return data, data != original


def _write_video_migration_backup(path: str, raw_data: dict) -> None:
    backup_path = f"{path}.schema-migration.bak"
    if not os.path.exists(backup_path):
        _write_json_atomic(backup_path, raw_data)


def _load_video_metadata(path: str, *, persist_migration: bool = True) -> JobInfo:
    with open(path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)
    migrated_data, migrated = _migrate_video_metadata(raw_data)
    job = JobInfo(**migrated_data)
    if migrated and persist_migration:
        _write_video_migration_backup(path, raw_data)
        _write_json_atomic(path, _job_data(job))
    return job


def _save_job_unlocked(job_info: JobInfo) -> None:
    path = get_job_json_path(job_info.job_id)
    backup_path = _get_job_backup_path(job_info.job_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                previous_data = json.load(file)
            _write_json_atomic(backup_path, previous_data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    _write_json_atomic(path, _job_data(job_info))


def save_job(job_info: JobInfo):
    with _job_lock(job_info.job_id):
        _save_job_unlocked(job_info)


def _get_job_unlocked(job_id: str) -> Optional[JobInfo]:
    path = get_job_json_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        return _load_video_metadata(path)
    except UnsupportedVideoSchemaError as exc:
        raise RuntimeError(f"Job metadata was created by a newer application version: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError) as original_error:
        backup_path = _get_job_backup_path(job_id)
        if not os.path.exists(backup_path):
            raise RuntimeError(f"Job metadata is unreadable: {path}") from original_error
        try:
            recovered = _load_video_metadata(backup_path, persist_migration=False)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError) as backup_error:
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


def _is_inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


def replace_job_input(
    job_id: str,
    source_path: str,
    media_source: MediaSource | dict | None = None,
) -> Optional[JobInfo]:
    """Replace a completed/pending video's source and discard its old artifacts."""
    source_path = os.path.abspath(source_path)
    with _job_lock(job_id):
        job = _get_job_unlocked(job_id)
        if not job:
            return None
        if job.status == "processing":
            raise RuntimeError("Cannot replace a video while it is processing.")

        job_dir = get_job_dir(job_id)
        extension = os.path.splitext(source_path)[1].lower() or ".mp4"
        input_path = os.path.join(job_dir, "input", f"video{extension}")
        if os.path.normcase(source_path) == os.path.normcase(os.path.abspath(input_path)):
            return job

        staged_source = source_path
        staging_directory = ""
        if _is_inside(source_path, job_dir):
            staging_directory = tempfile.mkdtemp(prefix=".replace-source-", dir=os.path.dirname(job_dir))
            staged_source = os.path.join(staging_directory, os.path.basename(source_path))
            shutil.copy2(source_path, staged_source)

        final_video = (job.files or {}).get("final_video") or ""
        previous_thumbnail = (job.files or {}).get("thumbnail") or ""
        project_root = (
            project_store.project_root_for_key(job.project_key)
            if job.project_key
            else project_store.project_root(job.project_name, job.project_directory, job.project_type)
            if job.project_name and job.project_directory
            else job_dir
        )
        try:
            for directory in ("input", "temp"):
                path = os.path.join(job_dir, directory)
                if os.path.isdir(path):
                    shutil.rmtree(path, onerror=_force_remove_readonly)
                os.makedirs(path, exist_ok=True)

            legacy_output_dir = os.path.join(job_dir, "output")
            if os.path.isdir(legacy_output_dir):
                shutil.rmtree(legacy_output_dir, onerror=_force_remove_readonly)

            if final_video and _is_inside(final_video, project_root) and os.path.isfile(final_video):
                os.remove(final_video)
            thumbnail_candidates = {
                previous_thumbnail,
                os.path.join(job_dir, "thumbnail.jpg"),
            }
            for thumbnail_path in thumbnail_candidates:
                if thumbnail_path and _is_inside(thumbnail_path, job_dir) and os.path.isfile(thumbnail_path):
                    os.remove(thumbnail_path)

            shutil.copy2(staged_source, input_path)
        finally:
            if staging_directory:
                shutil.rmtree(staging_directory, ignore_errors=True)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        job.files["video_input"] = input_path
        job.files["srt_output"] = os.path.join(job_dir, "temp", "vi.srt")
        job.files["voice_output"] = os.path.join(job_dir, "temp", "voice_final.wav")
        job.files["transcript_json"] = os.path.join(job_dir, "temp", "vi_segments.json")
        job.files["thumbnail"] = os.path.join(job_dir, "thumbnail.jpg")
        job.original_filename = os.path.basename(source_path)
        job.media_source = MediaSource.model_validate(media_source or {"type": "local_file"})
        job.video_width = 0
        job.video_height = 0
        job.review_approved = False
        job.status = "pending"
        job.progress = 0
        job.step = "pending"
        job.resume_step = ""
        job.runtime_recovery_step = ""
        job.gpu_recovery_attempted = False
        job.checkpoints = {}
        job.started_at = None
        job.estimated_remaining_seconds = None
        job.step_detail = "New source video imported"
        job.current_item = 0
        job.total_items = 0
        job.error = None
        job.created_at = now
        job.updated_at = now
        _save_job_unlocked(job)
        try:
            os.remove(_get_job_backup_path(job_id))
        except FileNotFoundError:
            pass
        with open(get_job_logs_path(job_id), "w", encoding="utf-8") as file:
            file.write(f"[{now}] Input video replaced. Previous processing data was removed.\n")
        return job


def remove_empty_legacy_output_dir(job_id: str) -> bool:
    """Remove an obsolete per-video output folder only when it is empty."""
    output_dir = os.path.join(get_job_dir(job_id), "output")
    try:
        if not os.path.isdir(output_dir) or any(os.scandir(output_dir)):
            return False
        os.rmdir(output_dir)
        return True
    except OSError:
        return False


def prepare_job_restart(job_id: str) -> Optional[JobInfo]:
    """Discard generated artifacts so a restart always runs from the source video."""
    with _job_lock(job_id):
        job = _get_job_unlocked(job_id)
        if not job:
            return None
        if job.status == "processing":
            raise RuntimeError("Cannot restart a video while it is processing.")

        job_dir = get_job_dir(job_id)
        temp_dir = os.path.join(job_dir, "temp")
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, onerror=_force_remove_readonly)
        os.makedirs(os.path.join(temp_dir, "voice_parts"), exist_ok=True)

        final_video = (job.files or {}).get("final_video") or ""
        project_root = (
            project_store.project_root_for_key(job.project_key)
            if job.project_key
            else project_store.project_root(job.project_name, job.project_directory, job.project_type)
            if job.project_name and job.project_directory
            else job_dir
        )
        if final_video and (_is_inside(final_video, project_root) or _is_inside(final_video, job_dir)):
            try:
                os.remove(final_video)
            except FileNotFoundError:
                pass

        legacy_output_dir = os.path.join(job_dir, "output")
        if _is_inside(final_video, legacy_output_dir):
            os.makedirs(legacy_output_dir, exist_ok=True)

        job.files["srt_output"] = os.path.join(temp_dir, "vi.srt")
        job.files["voice_output"] = os.path.join(temp_dir, "voice_final.wav")
        job.files["transcript_json"] = os.path.join(temp_dir, "vi_segments.json")
        job.review_approved = False
        job.status = "pending"
        job.progress = 0
        job.step = "queued"
        job.resume_step = ""
        job.runtime_recovery_step = ""
        job.gpu_recovery_attempted = False
        job.checkpoints = {}
        job.started_at = None
        job.estimated_remaining_seconds = None
        job.step_detail = "Queued to restart"
        job.current_item = 0
        job.total_items = 0
        job.error = None
        job.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _save_job_unlocked(job)
        log_to_job(job_id, "Restart prepared. Generated files and checkpoints were cleared.")
        return job


def _project_job_ids() -> list[str]:
    job_ids: list[str] = []
    for project in project_store.list_projects():
        videos_dir = project_store.project_videos_dir_for_key(project["key"])
        if not os.path.isdir(videos_dir):
            continue
        for name in os.listdir(videos_dir):
            if os.path.isdir(os.path.join(videos_dir, name)):
                job_ids.append(name)
    return job_ids


def list_jobs() -> List[JobInfo]:
    jobs = []
    seen = set()
    for job_id in _project_job_ids():
        job_info = get_job(job_id)
        if job_info:
            jobs.append(job_info)
            seen.add(job_id)
    if os.path.isdir(JOBS_DIR):
        for job_id in os.listdir(JOBS_DIR):
            if job_id in seen or not os.path.isdir(_legacy_job_dir(job_id)):
                continue
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
    with _job_lock(job_id):
        job_dir = get_job_dir(job_id)
        if not os.path.exists(job_dir):
            _JOB_DIR_CACHE.pop(job_id, None)
            return False
        last_error = None
        for attempt in range(attempts):
            try:
                shutil.rmtree(job_dir, onerror=_force_remove_readonly)
                _JOB_DIR_CACHE.pop(job_id, None)
                return True
            except Exception as exc:
                last_error = exc
                time.sleep(delay_seconds * (attempt + 1))
        if os.path.exists(job_dir):
            raise RuntimeError(f"Could not delete video data after {attempts} attempts: {last_error}")
        _JOB_DIR_CACHE.pop(job_id, None)
        return True


def migrate_legacy_project_data() -> list[str]:
    """Move old global video workspaces into their registered project folders."""
    if not os.path.isdir(JOBS_DIR):
        return []
    registered = {record["key"]: record for record in project_store.list_projects()}
    migrated = []
    for job_id in os.listdir(JOBS_DIR):
        source = _legacy_job_dir(job_id)
        metadata_path = os.path.join(source, "job.json")
        if not os.path.isdir(source) or not os.path.isfile(metadata_path):
            continue
        try:
            job = _load_video_metadata(metadata_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError):
            continue
        if not job.project_name or not job.project_directory:
            continue
        key = job.project_key or project_store.resolve_project_key(
            job.project_name,
            job.project_directory,
            job.project_type,
        )
        record = registered.get(key)
        if not record:
            continue
        destination = os.path.join(
            project_store.project_videos_dir_for_key(key),
            job_id,
        )
        if os.path.exists(destination):
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        _JOB_DIR_CACHE[job_id] = destination
        job.project_key = key
        job.project_id = str(record.get("project_id") or "")
        for file_key, file_path in (job.files or {}).items():
            if not file_path:
                continue
            try:
                if os.path.commonpath([os.path.abspath(source), os.path.abspath(file_path)]) == os.path.abspath(source):
                    job.files[file_key] = os.path.join(destination, os.path.relpath(file_path, source))
            except ValueError:
                continue
        for checkpoint_key, checkpoint_path in (job.checkpoints or {}).items():
            try:
                if os.path.commonpath([os.path.abspath(source), os.path.abspath(checkpoint_path)]) == os.path.abspath(source):
                    job.checkpoints[checkpoint_key] = os.path.join(destination, os.path.relpath(checkpoint_path, source))
            except (TypeError, ValueError):
                continue
        save_job(job)
        migrated.append(job_id)
    try:
        os.rmdir(JOBS_DIR)
    except OSError:
        pass
    return migrated


def migrate_legacy_thumbnails(legacy_directory: str) -> list[str]:
    """Move referenced legacy thumbnail-cache files into their video workspaces."""
    if not os.path.isdir(legacy_directory):
        return []
    legacy_root = os.path.abspath(legacy_directory)
    migrated = []
    for job in list_jobs():
        current_path = (job.files or {}).get("thumbnail") or ""
        if not current_path or not os.path.isfile(current_path):
            continue
        try:
            if os.path.commonpath([legacy_root, os.path.abspath(current_path)]) != legacy_root:
                continue
        except ValueError:
            continue
        destination = os.path.join(get_job_dir(job.job_id), "thumbnail.jpg")
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if not os.path.exists(destination):
                shutil.move(current_path, destination)
            job.files["thumbnail"] = destination
            save_job(job)
            migrated.append(job.job_id)
        except OSError:
            continue
    return migrated
