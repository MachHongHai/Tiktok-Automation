import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from haizflow.schemas.video import VideoConfig
from haizflow.services.desktop_videos import create_desktop_video
from haizflow.services import video_store
from haizflow.pipeline.process_video import process_video_sync

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

    config = VideoConfig(
        mode="A",
        source_language="auto",
        target_language=target_language,
        tts_voice=voice,
        output_format="keep_ratio",
    )

    print("Step 1: Importing project video...")
    video = create_desktop_video(str(video_path), config)
    print(f"Video imported successfully. ID: {video.video_id}")

    print("Step 2: Processing video synchronously...")
    process_video_sync(video.video_id)

    final_video = video_store.get_video(video.video_id)
    if not final_video:
        print("Video disappeared from storage.")
        return 1

    print(f"Video ended with status: {final_video.status}")
    print(f"Step: {final_video.step} | Progress: {final_video.progress}%")
    if final_video.error:
        print(f"Error: {final_video.error}")

    print("Generated files:")
    for key, value in final_video.files.items():
        exists = os.path.exists(value) if value else False
        print(f" - {key}: {value} | exists={exists}")

    print(f"Logs: {video_store.get_video_logs_path(video.video_id)}")
    return 0 if final_video.status == "done" else 1


if __name__ == "__main__":
    arguments = parse_args()
    raise SystemExit(run_pipeline_test(arguments.input, arguments.target_language, arguments.voice))
