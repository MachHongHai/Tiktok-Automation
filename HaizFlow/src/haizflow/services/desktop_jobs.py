import os
import shutil
import uuid

from haizflow.schemas.job import JobConfig, MediaSource
from haizflow.services import job_store, project_store
from haizflow.utils.ffmpeg import get_video_dimensions


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def _same_path(first: str, second: str) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def migrate_legacy_single_export(job_info) -> bool:
    """Move a legacy single-project export out of the project root once."""
    if (
        not job_info
        or job_info.project_type == "batch"
        or not job_info.project_name
        or not job_info.project_directory
    ):
        return False

    project_root = (
        project_store.project_root_for_key(job_info.project_key)
        if job_info.project_key
        else project_store.project_root(job_info.project_name, job_info.project_directory, job_info.project_type)
    )
    legacy_export = os.path.join(project_root, "dubbed_video.mp4")
    current_export = (job_info.files or {}).get("final_video") or ""
    if not current_export or not _same_path(current_export, legacy_export):
        return False

    export_directory = (
        project_store.project_exports_dir_for_key(job_info.project_key)
        if job_info.project_key
        else project_store.project_exports_dir(job_info.project_name, job_info.project_directory, job_info.project_type)
    )
    migrated_export = os.path.join(export_directory, "dubbed_video.mp4")
    os.makedirs(export_directory, exist_ok=True)
    if os.path.isfile(legacy_export) and not os.path.exists(migrated_export):
        os.replace(legacy_export, migrated_export)

    if os.path.exists(migrated_export):
        job_info.files["final_video"] = migrated_export
        job_store.save_job(job_info)
        return True
    return False


def create_desktop_job(
    video_path: str,
    config: JobConfig,
    project_name: str = "",
    project_directory: str = "",
    media_source: MediaSource | dict | None = None,
    *,
    move_input: bool = False,
    project_key_value: str = "",
):
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise ValueError(f"Unsupported video extension '{ext}'. Supported: {supported}.")
    if config.mode not in {"A", "review"}:
        raise ValueError(f"Unsupported workflow: {config.mode}")

    project_name = project_name.strip()
    project_directory = project_directory.strip()
    if project_directory and not project_name:
        raise ValueError("Enter a project name before choosing an output folder.")

    job_id = str(uuid.uuid4())
    if project_directory:
        config.project_name = project_name
        config.project_directory = os.path.abspath(project_directory)
        project = project_store.ensure_project(
            project_name,
            config.project_directory,
            config.project_type,
            project_key_value=project_key_value or config.project_key,
        )
        config.project_id = str(project["project_id"])
        config.project_key = str(project["key"])
    job_info = job_store.create_job(job_id, os.path.basename(video_path), config, video_ext=ext)
    try:
        job_info.media_source = MediaSource.model_validate(media_source or {"type": "local_file"})
        input_path = job_info.files["video_input"]
        if move_input:
            os.replace(video_path, input_path)
        else:
            shutil.copyfile(video_path, input_path)

        try:
            job_info.video_width, job_info.video_height = get_video_dimensions(input_path)
        except RuntimeError:
            # The UI can retry probing legacy or unusual files when the batch is opened.
            job_info.video_width = 0
            job_info.video_height = 0

        job_store.save_job(job_info)
        job_store.log_to_job(job_id, f"Imported input video: {video_path}")
        return job_info
    except Exception:
        try:
            job_store.delete_job(job_id, attempts=2, delay_seconds=0.05)
        except Exception:
            pass
        export_directory = os.path.dirname(str(job_info.files.get("final_video") or ""))
        if export_directory:
            try:
                os.rmdir(export_directory)
            except OSError:
                pass
        raise
