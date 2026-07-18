import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from haizflow.schemas.job import JobConfig
from haizflow.services.desktop_jobs import create_desktop_job
from haizflow.services import job_store
from haizflow.pipeline.process_job import process_job_sync

def parse_args():
    parser = argparse.ArgumentParser(description="Run one local HaizFlow pipeline smoke test.")
    parser.add_argument("--input", required=True, type=Path, help="Path to an MP4, MOV, or MKV input video.")
    parser.add_argument("--target-language", default="vi", help="Target language code, for example vi or ja.")
    parser.add_argument("--voice", default="vi-VN-NamMinhNeural", help="Edge TTS voice identifier.")
    return parser.parse_args()


def run_pipeline_test(video_path: Path, target_language: str, voice: str) -> int:
    video_path = video_path.expanduser().resolve()
    if not video_path.is_file():
        print(f"Input video was not found: {video_path}")
        return 2

    config = JobConfig(
        mode="A",
        source_language="auto",
        target_language=target_language,
        tts_voice=voice,
        output_format="keep_ratio",
    )

    print("Step 1: Creating desktop job...")
    job = create_desktop_job(str(video_path), config)
    print(f"Job created successfully. ID: {job.job_id}")

    print("Step 2: Processing job synchronously...")
    process_job_sync(job.job_id)

    final_job = job_store.get_job(job.job_id)
    if not final_job:
        print("Job disappeared from storage.")
        return 1

    print(f"Job ended with status: {final_job.status}")
    print(f"Step: {final_job.step} | Progress: {final_job.progress}%")
    if final_job.error:
        print(f"Error: {final_job.error}")

    print("Generated files:")
    for key, value in final_job.files.items():
        exists = os.path.exists(value) if value else False
        print(f" - {key}: {value} | exists={exists}")

    print(f"Logs: {job_store.get_job_logs_path(job.job_id)}")
    return 0 if final_job.status == "done" else 1


if __name__ == "__main__":
    arguments = parse_args()
    raise SystemExit(run_pipeline_test(arguments.input, arguments.target_language, arguments.voice))
