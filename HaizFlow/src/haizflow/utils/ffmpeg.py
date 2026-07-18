import subprocess
import os
import shutil
from functools import lru_cache
from pathlib import Path

from haizflow.config import BIN_DIR
from haizflow.core.hardware import runtime_profile


def _binary(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    return str(Path(BIN_DIR) / f"{name}.exe")


@lru_cache(maxsize=1)
def available_video_encoders() -> set[str]:
    try:
        result = subprocess.run(
            [_binary("ffmpeg"), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    encoders = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.add(parts[1])
    return encoders


@lru_cache(maxsize=None)
def _encoder_works(encoder: str) -> bool:
    if encoder not in available_video_encoders():
        return False
    try:
        result = subprocess.run(
            [
                _binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                "-frames:v", "1", "-c:v", encoder, "-f", "null", "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def preferred_video_encoder() -> tuple[str, list[str]]:
    """Return a verified hardware encoder, with a universal CPU fallback."""
    profile = runtime_profile()
    candidates = []
    if profile.cuda_available:
        candidates = ["h264_nvenc", "h264_qsv", "h264_amf"]
    for encoder in candidates:
        if not _encoder_works(encoder):
            continue
        if encoder == "h264_nvenc":
            return encoder, ["-preset", "p4", "-cq", "23"]
        if encoder == "h264_qsv":
            return encoder, ["-preset", "faster", "-global_quality", "23"]
        return encoder, ["-quality", "speed", "-qp_i", "23", "-qp_p", "23"]
    return "libx264", ["-preset", "veryfast", "-crf", "23"]

def is_ffmpeg_available() -> bool:
    """Checks if both ffmpeg and ffprobe are available in the PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def get_ffmpeg_version() -> str:
    """Retrieves the first line of ffmpeg's version details."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        if result.stdout:
            return result.stdout.splitlines()[0]
        return "Unknown version"
    except Exception as e:
        return f"Unknown (Error: {str(e)})"

def get_video_duration(video_path: str) -> float:
    """Calculates the duration of a video file using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def get_video_dimensions(video_path: str) -> tuple[int, int]:
    """Return the first video stream dimensions for subtitle positioning and crop math."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        width, height = result.stdout.strip().split(",")
        return int(width), int(height)
    except Exception as exc:
        raise RuntimeError(f"Cannot read video dimensions: {exc}") from exc


