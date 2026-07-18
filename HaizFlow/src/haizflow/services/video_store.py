import json
import os
import shutil
import stat
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

from haizflow.config import LEGACY_VIDEO_WORKSPACES_DIR
from haizflow.core.events import emit_log
from haizflow.schemas.video import (
    VIDEO_METADATA_SCHEMA_VERSION,
    VIDEO_METADATA_TYPE,
    VideoConfig,
    VideoInfo,
    MediaSource,
)
from haizflow.services import project_store


_VIDEO_LOCKS: dict[str, threading.RLock] = {}
_VIDEO_LOCKS_GUARD = threading.Lock()
_VIDEO_DIR_CACHE: dict[str, str] = {}
_LEGACY_METADATA_NAME = "job.json"


def _video_lock(video_id: str) -> threading.RLock:
    with _VIDEO_LOCKS_GUARD:
        lock = _VIDEO_LOCKS.get(video_id)
        if lock is None:
            lock = threading.RLock()
            _VIDEO_LOCKS[video_id] = lock
        return lock


def _legacy_video_dir(video_id: str) -> str:
    return os.path.join(LEGACY_VIDEO_WORKSPACES_DIR, video_id)


def _project_video_dir(video_id: str, config: VideoConfig) -> str:
    if config.project_name.strip() and config.project_directory.strip():
        videos_dir = (
            project_store.project_videos_dir_for_key(config.project_key)
            if config.project_key
            else project_store.project_videos_dir(config.project_name, config.project_directory, config.project_type)
        )
        return os.path.join(
            videos_dir,
            video_id,
        )
    return _legacy_video_dir(video_id)


def _find_video_dir(video_id: str) -> str:
    cached = _VIDEO_DIR_CACHE.get(video_id)
    if cached and os.path.isdir(cached):
        return cached
    _VIDEO_DIR_CACHE.pop(video_id, None)

    legacy = _legacy_video_dir(video_id)
    if os.path.isdir(legacy):
        _VIDEO_DIR_CACHE[video_id] = legacy
        return legacy

    for project in project_store.list_projects():
        candidate = os.path.join(
            project_store.project_videos_dir_for_key(project["key"]),
            video_id,
        )
        if os.path.isdir(candidate):
            _VIDEO_DIR_CACHE[video_id] = candidate
            return candidate
    return legacy


def get_video_dir(video_id: str) -> str:
    return _find_video_dir(video_id)


def get_video_json_path(video_id: str) -> str:
    return os.path.join(get_video_dir(video_id), "video.json")


def _legacy_video_json_path(video_id: str) -> str:
    return os.path.join(get_video_dir(video_id), _LEGACY_METADATA_NAME)


def _existing_video_json_path(video_id: str) -> str:
    canonical = get_video_json_path(video_id)
    if os.path.isfile(canonical):
        return canonical
    legacy = _legacy_video_json_path(video_id)
    return legacy if os.path.isfile(legacy) else canonical


def _get_video_backup_path(video_id: str) -> str:
    return get_video_json_path(video_id) + ".bak"


def get_video_logs_path(video_id: str) -> str:
    return os.path.join(get_video_dir(video_id), "logs.txt")


def create_video(video_id: str, original_filename: str, config: VideoConfig, video_ext: str = ".mp4") -> VideoInfo:
    video_dir = _project_video_dir(video_id, config)
    _VIDEO_DIR_CACHE[video_id] = video_dir
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(os.path.join(video_dir, "input"), exist_ok=True)
    os.makedirs(os.path.join(video_dir, "temp"), exist_ok=True)
    os.makedirs(os.path.join(video_dir, "temp", "voice_parts"), exist_ok=True)
    project_owned = bool(config.project_name and config.project_directory)
    # Modern desktop projects export through <project>/exports. Preserve the
    # per-video output folder only for legacy videos without a project owner.
    if not project_owned:
        os.makedirs(os.path.join(video_dir, "output"), exist_ok=True)

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
            export_dir = os.path.join(export_dir, f"{safe_stem or 'video'}-{video_id[:8]}")
        os.makedirs(export_dir, exist_ok=True)
        final_video = os.path.join(export_dir, "dubbed_video.mp4")
    else:
        final_video = os.path.join(video_dir, "output", "final.mp4")
    files = {
        "video_input": os.path.join(video_dir, "input", f"video{video_ext}"),
        "final_video": final_video,
        "srt_output": os.path.join(video_dir, "temp", "vi.srt"),
        "voice_output": os.path.join(video_dir, "temp", "voice_final.wav"),
        "transcript_json": os.path.join(video_dir, "temp", "vi_segments.json"),
    }
    video_info = VideoInfo(
        video_id=video_id,
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
    save_video(video_info)
    with open(get_video_logs_path(video_id), "w", encoding="utf-8") as file:
        file.write(f"[{now}] Video created.\n")
    return video_info


def _video_data(video_info: VideoInfo) -> dict:
    data = video_info.model_dump() if hasattr(video_info, "model_dump") else video_info.dict()
    data["schema_version"] = VIDEO_METADATA_SCHEMA_VERSION
    data["metadata_type"] = VIDEO_METADATA_TYPE
    return data


def _write_json_atomic(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(prefix=".video-", suffix=".json.tmp", dir=directory)
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
        if version == 4:
            legacy_id = str(data.pop("job_id", "") or "").strip()
            if not str(data.get("video_id") or "").strip():
                data["video_id"] = legacy_id
            data["schema_version"] = 5
            version = 5
            continue
        raise VideoMetadataError(f"No video metadata migration is available from schema v{version}.")
    data["schema_version"] = VIDEO_METADATA_SCHEMA_VERSION
    data["metadata_type"] = VIDEO_METADATA_TYPE
    return data, data != original


def _write_video_migration_backup(path: str, raw_data: dict) -> None:
    backup_path = f"{path}.schema-migration.bak"
    if not os.path.exists(backup_path):
        _write_json_atomic(backup_path, raw_data)


def _load_video_metadata(path: str, *, persist_migration: bool = True) -> VideoInfo:
    with open(path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)
    migrated_data, migrated = _migrate_video_metadata(raw_data)
    video = VideoInfo(**migrated_data)
    if migrated and persist_migration:
        _write_video_migration_backup(path, raw_data)
        _write_json_atomic(path, _video_data(video))
    return video


def _save_video_unlocked(video_info: VideoInfo) -> None:
    path = get_video_json_path(video_info.video_id)
    backup_path = _get_video_backup_path(video_info.video_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                previous_data = json.load(file)
            _write_json_atomic(backup_path, previous_data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    _write_json_atomic(path, _video_data(video_info))


def save_video(video_info: VideoInfo):
    with _video_lock(video_info.video_id):
        _save_video_unlocked(video_info)


def _get_video_unlocked(video_id: str) -> Optional[VideoInfo]:
    path = _existing_video_json_path(video_id)
    if not os.path.exists(path):
        return None
    try:
        legacy_path = os.path.basename(path).lower() == _LEGACY_METADATA_NAME
        video = _load_video_metadata(path, persist_migration=not legacy_path)
        if legacy_path:
            canonical = get_video_json_path(video_id)
            _write_json_atomic(canonical, _video_data(video))
            legacy_backup = f"{path}.legacy.bak"
            if not os.path.exists(legacy_backup):
                shutil.copy2(path, legacy_backup)
        return video
    except UnsupportedVideoSchemaError as exc:
        raise RuntimeError(f"Video metadata was created by a newer application version: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError) as original_error:
        backup_path = _get_video_backup_path(video_id)
        if not os.path.exists(backup_path) and path != get_video_json_path(video_id):
            backup_path = f"{path}.bak"
        if not os.path.exists(backup_path):
            raise RuntimeError(f"Video metadata is unreadable: {path}") from original_error
        try:
            recovered = _load_video_metadata(backup_path, persist_migration=False)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError) as backup_error:
            raise RuntimeError(f"Video metadata and backup are unreadable: {path}") from backup_error
        _write_json_atomic(path, _video_data(recovered))
        log_to_video(video_id, "Recovered video metadata from the last atomic backup.")
        return recovered


def get_video(video_id: str) -> Optional[VideoInfo]:
    with _video_lock(video_id):
        return _get_video_unlocked(video_id)


def update_video(video_id: str, **kwargs) -> Optional[VideoInfo]:
    with _video_lock(video_id):
        video_info = _get_video_unlocked(video_id)
        if not video_info:
            return None
        for key, value in kwargs.items():
            if hasattr(video_info, key):
                setattr(video_info, key, value)
        video_info.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _save_video_unlocked(video_info)
        return video_info


def _is_inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


def replace_video_input(
    video_id: str,
    source_path: str,
    media_source: MediaSource | dict | None = None,
) -> Optional[VideoInfo]:
    """Replace a completed/pending video's source and discard its old artifacts."""
    source_path = os.path.abspath(source_path)
    with _video_lock(video_id):
        video = _get_video_unlocked(video_id)
        if not video:
            return None
        if video.status == "processing":
            raise RuntimeError("Cannot replace a video while it is processing.")

        video_dir = get_video_dir(video_id)
        extension = os.path.splitext(source_path)[1].lower() or ".mp4"
        input_path = os.path.join(video_dir, "input", f"video{extension}")
        if os.path.normcase(source_path) == os.path.normcase(os.path.abspath(input_path)):
            return video

        staged_source = source_path
        staging_directory = ""
        if _is_inside(source_path, video_dir):
            staging_directory = tempfile.mkdtemp(prefix=".replace-source-", dir=os.path.dirname(video_dir))
            staged_source = os.path.join(staging_directory, os.path.basename(source_path))
            shutil.copy2(source_path, staged_source)

        final_video = (video.files or {}).get("final_video") or ""
        previous_thumbnail = (video.files or {}).get("thumbnail") or ""
        project_root = (
            project_store.project_root_for_key(video.project_key)
            if video.project_key
            else project_store.project_root(video.project_name, video.project_directory, video.project_type)
            if video.project_name and video.project_directory
            else video_dir
        )
        try:
            for directory in ("input", "temp"):
                path = os.path.join(video_dir, directory)
                if os.path.isdir(path):
                    shutil.rmtree(path, onerror=_force_remove_readonly)
                os.makedirs(path, exist_ok=True)

            legacy_output_dir = os.path.join(video_dir, "output")
            if os.path.isdir(legacy_output_dir):
                shutil.rmtree(legacy_output_dir, onerror=_force_remove_readonly)

            if final_video and _is_inside(final_video, project_root) and os.path.isfile(final_video):
                os.remove(final_video)
            thumbnail_candidates = {
                previous_thumbnail,
                os.path.join(video_dir, "thumbnail.jpg"),
            }
            for thumbnail_path in thumbnail_candidates:
                if thumbnail_path and _is_inside(thumbnail_path, video_dir) and os.path.isfile(thumbnail_path):
                    os.remove(thumbnail_path)

            shutil.copy2(staged_source, input_path)
        finally:
            if staging_directory:
                shutil.rmtree(staging_directory, ignore_errors=True)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        video.files["video_input"] = input_path
        video.files["srt_output"] = os.path.join(video_dir, "temp", "vi.srt")
        video.files["voice_output"] = os.path.join(video_dir, "temp", "voice_final.wav")
        video.files["transcript_json"] = os.path.join(video_dir, "temp", "vi_segments.json")
        video.files["thumbnail"] = os.path.join(video_dir, "thumbnail.jpg")
        video.original_filename = os.path.basename(source_path)
        video.media_source = MediaSource.model_validate(media_source or {"type": "local_file"})
        video.video_width = 0
        video.video_height = 0
        video.review_approved = False
        video.status = "pending"
        video.progress = 0
        video.step = "pending"
        video.resume_step = ""
        video.runtime_recovery_step = ""
        video.gpu_recovery_attempted = False
        video.checkpoints = {}
        video.started_at = None
        video.estimated_remaining_seconds = None
        video.step_detail = "New source video imported"
        video.current_item = 0
        video.total_items = 0
        video.error = None
        video.created_at = now
        video.updated_at = now
        _save_video_unlocked(video)
        try:
            os.remove(_get_video_backup_path(video_id))
        except FileNotFoundError:
            pass
        with open(get_video_logs_path(video_id), "w", encoding="utf-8") as file:
            file.write(f"[{now}] Input video replaced. Previous processing data was removed.\n")
        return video


def remove_empty_legacy_output_dir(video_id: str) -> bool:
    """Remove an obsolete per-video output folder only when it is empty."""
    output_dir = os.path.join(get_video_dir(video_id), "output")
    try:
        if not os.path.isdir(output_dir) or any(os.scandir(output_dir)):
            return False
        os.rmdir(output_dir)
        return True
    except OSError:
        return False


def prepare_video_restart(video_id: str) -> Optional[VideoInfo]:
    """Discard generated artifacts so a restart always runs from the source video."""
    with _video_lock(video_id):
        video = _get_video_unlocked(video_id)
        if not video:
            return None
        if video.status == "processing":
            raise RuntimeError("Cannot restart a video while it is processing.")

        video_dir = get_video_dir(video_id)
        temp_dir = os.path.join(video_dir, "temp")
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, onerror=_force_remove_readonly)
        os.makedirs(os.path.join(temp_dir, "voice_parts"), exist_ok=True)

        final_video = (video.files or {}).get("final_video") or ""
        project_root = (
            project_store.project_root_for_key(video.project_key)
            if video.project_key
            else project_store.project_root(video.project_name, video.project_directory, video.project_type)
            if video.project_name and video.project_directory
            else video_dir
        )
        if final_video and (_is_inside(final_video, project_root) or _is_inside(final_video, video_dir)):
            try:
                os.remove(final_video)
            except FileNotFoundError:
                pass

        legacy_output_dir = os.path.join(video_dir, "output")
        if _is_inside(final_video, legacy_output_dir):
            os.makedirs(legacy_output_dir, exist_ok=True)

        video.files["srt_output"] = os.path.join(temp_dir, "vi.srt")
        video.files["voice_output"] = os.path.join(temp_dir, "voice_final.wav")
        video.files["transcript_json"] = os.path.join(temp_dir, "vi_segments.json")
        video.review_approved = False
        video.status = "pending"
        video.progress = 0
        video.step = "queued"
        video.resume_step = ""
        video.runtime_recovery_step = ""
        video.gpu_recovery_attempted = False
        video.checkpoints = {}
        video.started_at = None
        video.estimated_remaining_seconds = None
        video.step_detail = "Queued to restart"
        video.current_item = 0
        video.total_items = 0
        video.error = None
        video.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _save_video_unlocked(video)
        log_to_video(video_id, "Restart prepared. Generated files and checkpoints were cleared.")
        return video


def _project_video_ids() -> list[str]:
    video_ids: list[str] = []
    for project in project_store.list_projects():
        videos_dir = project_store.project_videos_dir_for_key(project["key"])
        if not os.path.isdir(videos_dir):
            continue
        for name in os.listdir(videos_dir):
            if os.path.isdir(os.path.join(videos_dir, name)):
                video_ids.append(name)
    return video_ids


def list_videos() -> List[VideoInfo]:
    videos = []
    seen = set()
    for video_id in _project_video_ids():
        video_info = get_video(video_id)
        if video_info:
            videos.append(video_info)
            seen.add(video_id)
    if os.path.isdir(LEGACY_VIDEO_WORKSPACES_DIR):
        for video_id in os.listdir(LEGACY_VIDEO_WORKSPACES_DIR):
            if video_id in seen or not os.path.isdir(_legacy_video_dir(video_id)):
                continue
            video_info = get_video(video_id)
            if video_info:
                videos.append(video_info)
    videos.sort(key=lambda item: item.created_at, reverse=True)
    return videos


def recover_interrupted_videos() -> list[str]:
    """Turn stale in-progress metadata into resumable paused videos at startup."""
    recovered: list[str] = []
    for video in list_videos():
        if video.status != "processing":
            continue
        interrupted_step = video.resume_step or video.step or "processing"
        if interrupted_step == "paused":
            interrupted_step = "processing"
        updated = update_video(
            video.video_id,
            status="paused",
            error=None,
            step="paused",
            resume_step=interrupted_step,
            step_detail=f"Recovered after an interrupted exit during {interrupted_step}",
            estimated_remaining_seconds=None,
        )
        if not updated:
            continue
        recovered.append(video.video_id)
        log_to_video(
            video.video_id,
            f"Recovered an interrupted application exit. Resume will continue from {interrupted_step}.",
        )
    return recovered


def log_to_video(video_id: str, message: str):
    log_path = get_video_logs_path(video_id)
    if not os.path.exists(_existing_video_json_path(video_id)) and not os.path.exists(log_path):
        return
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    line = f"[{now}] {message}"
    with open(log_path, "a", encoding="utf-8") as file:
        file.write(f"{line}\n")
    emit_log(video_id, line)


def _force_remove_readonly(func, path, _exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def delete_video(video_id: str, attempts: int = 8, delay_seconds: float = 0.35) -> bool:
    with _video_lock(video_id):
        video_dir = get_video_dir(video_id)
        if not os.path.exists(video_dir):
            _VIDEO_DIR_CACHE.pop(video_id, None)
            return False
        last_error = None
        for attempt in range(attempts):
            try:
                shutil.rmtree(video_dir, onerror=_force_remove_readonly)
                _VIDEO_DIR_CACHE.pop(video_id, None)
                return True
            except Exception as exc:
                last_error = exc
                time.sleep(delay_seconds * (attempt + 1))
        if os.path.exists(video_dir):
            raise RuntimeError(f"Could not delete video data after {attempts} attempts: {last_error}")
        _VIDEO_DIR_CACHE.pop(video_id, None)
        return True


def migrate_legacy_project_data() -> list[str]:
    """Move old global video workspaces into their registered project folders."""
    if not os.path.isdir(LEGACY_VIDEO_WORKSPACES_DIR):
        return []
    registered = {record["key"]: record for record in project_store.list_projects()}
    migrated = []
    for video_id in os.listdir(LEGACY_VIDEO_WORKSPACES_DIR):
        source = _legacy_video_dir(video_id)
        metadata_path = os.path.join(source, "video.json")
        if not os.path.isfile(metadata_path):
            metadata_path = os.path.join(source, _LEGACY_METADATA_NAME)
        if not os.path.isdir(source) or not os.path.isfile(metadata_path):
            continue
        try:
            video = _load_video_metadata(metadata_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError):
            continue
        if not video.project_name or not video.project_directory:
            continue
        key = video.project_key or project_store.resolve_project_key(
            video.project_name,
            video.project_directory,
            video.project_type,
        )
        record = registered.get(key)
        if not record:
            continue
        destination = os.path.join(
            project_store.project_videos_dir_for_key(key),
            video_id,
        )
        if os.path.exists(destination):
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        _VIDEO_DIR_CACHE[video_id] = destination
        video.project_key = key
        video.project_id = str(record.get("project_id") or "")
        for file_key, file_path in (video.files or {}).items():
            if not file_path:
                continue
            try:
                if os.path.commonpath([os.path.abspath(source), os.path.abspath(file_path)]) == os.path.abspath(source):
                    video.files[file_key] = os.path.join(destination, os.path.relpath(file_path, source))
            except ValueError:
                continue
        for checkpoint_key, checkpoint_path in (video.checkpoints or {}).items():
            try:
                if os.path.commonpath([os.path.abspath(source), os.path.abspath(checkpoint_path)]) == os.path.abspath(source):
                    video.checkpoints[checkpoint_key] = os.path.join(destination, os.path.relpath(checkpoint_path, source))
            except (TypeError, ValueError):
                continue
        save_video(video)
        migrated.append(video_id)
    try:
        os.rmdir(LEGACY_VIDEO_WORKSPACES_DIR)
    except OSError:
        pass
    return migrated


def migrate_legacy_thumbnails(legacy_directory: str) -> list[str]:
    """Move referenced legacy thumbnail-cache files into their video workspaces."""
    if not os.path.isdir(legacy_directory):
        return []
    legacy_root = os.path.abspath(legacy_directory)
    migrated = []
    for video in list_videos():
        current_path = (video.files or {}).get("thumbnail") or ""
        if not current_path or not os.path.isfile(current_path):
            continue
        try:
            if os.path.commonpath([legacy_root, os.path.abspath(current_path)]) != legacy_root:
                continue
        except ValueError:
            continue
        destination = os.path.join(get_video_dir(video.video_id), "thumbnail.jpg")
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if not os.path.exists(destination):
                shutil.move(current_path, destination)
            video.files["thumbnail"] = destination
            save_video(video)
            migrated.append(video.video_id)
        except OSError:
            continue
    return migrated
