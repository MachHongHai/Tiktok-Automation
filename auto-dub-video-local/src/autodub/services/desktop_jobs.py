import os
import shutil
import uuid

from autodub.schemas.job import JobConfig
from autodub.services import job_store


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def create_desktop_job(video_path: str, config: JobConfig):
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise ValueError(f"Unsupported video extension '{ext}'. Supported: {supported}.")
    if config.mode != "A":
        raise ValueError("Only full-auto jobs are supported.")

    job_id = str(uuid.uuid4())
    job_info = job_store.create_job(job_id, os.path.basename(video_path), config, video_ext=ext)

    shutil.copyfile(video_path, job_info.files["video_input"])

    job_store.save_job(job_info)
    job_store.log_to_job(job_id, f"Imported input video: {video_path}")
    return job_info
