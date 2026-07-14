import os
import shutil
import uuid

from autodub.schemas.job import JobConfig
from autodub.services import job_store
from autodub.utils.ffmpeg import get_video_dimensions


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def create_desktop_job(video_path: str, config: JobConfig, project_name: str = "", project_directory: str = ""):
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
    job_info = job_store.create_job(job_id, os.path.basename(video_path), config, video_ext=ext)

    if project_directory:
        safe_project = "".join(character if character.isalnum() or character in {"-", "_", " "} else "_" for character in project_name).strip()
        project_output_dir = os.path.join(os.path.abspath(project_directory), safe_project or "project")
        os.makedirs(project_output_dir, exist_ok=True)
        if config.project_type == "batch":
            safe_stem = "".join(
                character if character.isalnum() or character in {"-", "_", " "} else "_"
                for character in os.path.splitext(os.path.basename(video_path))[0]
            ).strip()
            video_output_dir = os.path.join(project_output_dir, "outputs", f"{safe_stem or 'video'}-{job_id[:8]}")
            os.makedirs(video_output_dir, exist_ok=True)
            job_info.files["final_video"] = os.path.join(video_output_dir, "dubbed_video.mp4")
        else:
            job_info.files["final_video"] = os.path.join(project_output_dir, "dubbed_video.mp4")

    shutil.copyfile(video_path, job_info.files["video_input"])

    try:
        job_info.video_width, job_info.video_height = get_video_dimensions(job_info.files["video_input"])
    except RuntimeError:
        # The UI can retry probing legacy or unusual files when the batch is opened.
        job_info.video_width = 0
        job_info.video_height = 0

    job_store.save_job(job_info)
    job_store.log_to_job(job_id, f"Imported input video: {video_path}")
    return job_info
