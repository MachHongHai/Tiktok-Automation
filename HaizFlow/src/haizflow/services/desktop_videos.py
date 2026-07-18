import os
import shutil
import uuid

from haizflow.schemas.video import VideoConfig, MediaSource
from haizflow.services import video_store, project_store
from haizflow.utils.ffmpeg import get_video_dimensions


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def _same_path(first: str, second: str) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def migrate_legacy_single_export(video_info) -> bool:
    """Move a legacy single-project export out of the project root once."""
    if (
        not video_info
        or video_info.project_type == "batch"
        or not video_info.project_name
        or not video_info.project_directory
    ):
        return False

    project_root = (
        project_store.project_root_for_key(video_info.project_key)
        if video_info.project_key
        else project_store.project_root(video_info.project_name, video_info.project_directory, video_info.project_type)
    )
    legacy_export = os.path.join(project_root, "dubbed_video.mp4")
    current_export = (video_info.files or {}).get("final_video") or ""
    if not current_export or not _same_path(current_export, legacy_export):
        return False

    export_directory = (
        project_store.project_exports_dir_for_key(video_info.project_key)
        if video_info.project_key
        else project_store.project_exports_dir(video_info.project_name, video_info.project_directory, video_info.project_type)
    )
    migrated_export = os.path.join(export_directory, "dubbed_video.mp4")
    os.makedirs(export_directory, exist_ok=True)
    if os.path.isfile(legacy_export) and not os.path.exists(migrated_export):
        os.replace(legacy_export, migrated_export)

    if os.path.exists(migrated_export):
        video_info.files["final_video"] = migrated_export
        video_store.save_video(video_info)
        return True
    return False


def create_desktop_video(
    video_path: str,
    config: VideoConfig,
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

    video_id = str(uuid.uuid4())
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
    video_info = video_store.create_video(video_id, os.path.basename(video_path), config, video_ext=ext)
    try:
        video_info.media_source = MediaSource.model_validate(media_source or {"type": "local_file"})
        input_path = video_info.files["video_input"]
        if move_input:
            os.replace(video_path, input_path)
        else:
            shutil.copyfile(video_path, input_path)

        try:
            video_info.video_width, video_info.video_height = get_video_dimensions(input_path)
        except RuntimeError:
            # The UI can retry probing legacy or unusual files when the batch is opened.
            video_info.video_width = 0
            video_info.video_height = 0

        video_store.save_video(video_info)
        video_store.log_to_video(video_id, f"Imported input video: {video_path}")
        return video_info
    except Exception:
        try:
            video_store.delete_video(video_id, attempts=2, delay_seconds=0.05)
        except Exception:
            pass
        export_directory = os.path.dirname(str(video_info.files.get("final_video") or ""))
        if export_directory:
            try:
                os.rmdir(export_directory)
            except OSError:
                pass
        raise
