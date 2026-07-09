import subprocess
import shutil

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


