import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.schemas.job import JobConfig
from app.services.desktop_jobs import create_desktop_job
from app.services import job_store
from app.pipeline.process_job import process_job_sync

VIDEO_PATH = Path(__file__).resolve().parent.parent / "test" / "english_sample.mp4"


def test_pipeline():
    if not VIDEO_PATH.exists():
        print(f"Error: Test video not found at {VIDEO_PATH}")
        return

    config = JobConfig(
        mode="A",
        source_language="auto",
        target_language="vi",
        tts_voice="vi-VN-NamMinhNeural",
        output_format="keep_ratio",
    )

    print("Step 1: Creating desktop job...")
    job = create_desktop_job(str(VIDEO_PATH), config)
    print(f"Job created successfully. ID: {job.job_id}")

    print("Step 2: Processing job synchronously...")
    process_job_sync(job.job_id)

    final_job = job_store.get_job(job.job_id)
    if not final_job:
        print("Job disappeared from storage.")
        return

    print(f"Job ended with status: {final_job.status}")
    print(f"Step: {final_job.step} | Progress: {final_job.progress}%")
    if final_job.error:
        print(f"Error: {final_job.error}")

    print("Generated files:")
    for key, value in final_job.files.items():
        exists = os.path.exists(value) if value else False
        print(f" - {key}: {value} | exists={exists}")

    print(f"Logs: {job_store.get_job_logs_path(job.job_id)}")
    time.sleep(0.1)


if __name__ == "__main__":
    test_pipeline()
