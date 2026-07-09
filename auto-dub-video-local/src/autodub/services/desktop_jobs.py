import os
import shutil
import uuid
from typing import Optional

from autodub.schemas.job import JobConfig
from autodub.services import job_store

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def create_desktop_job(
    video_path: str,
    config: JobConfig,
    srt_path: Optional[str] = None,
    script_path: Optional[str] = None,
):
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise ValueError(f"Unsupported video extension '{ext}'. Supported: {supported}.")

    if config.mode == "B" and not srt_path:
        raise ValueError("Mode B requires a Vietnamese .srt subtitle file.")
    if config.mode == "C" and not script_path:
        raise ValueError("Mode C requires a Vietnamese .txt script file.")

    job_id = str(uuid.uuid4())
    job_info = job_store.create_job(job_id, os.path.basename(video_path), config, video_ext=ext)
    job_dir = job_store.get_job_dir(job_id)

    shutil.copyfile(video_path, job_info.files["video_input"])

    if srt_path:
        srt_dest = os.path.join(job_dir, "input", "vi.srt")
        shutil.copyfile(srt_path, srt_dest)
        job_info.files["srt_input"] = srt_dest

    if script_path:
        script_dest = os.path.join(job_dir, "input", "script_vi.txt")
        shutil.copyfile(script_path, script_dest)
        job_info.files["script_input"] = script_dest

    job_store.save_job(job_info)
    job_store.log_to_job(job_id, f"Imported input video: {video_path}")
    if srt_path:
        job_store.log_to_job(job_id, f"Imported subtitle file: {srt_path}")
    if script_path:
        job_store.log_to_job(job_id, f"Imported script file: {script_path}")

    return job_info

