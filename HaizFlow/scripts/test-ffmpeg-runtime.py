"""Run the media operations required by the production pipeline."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / "runtime" / "bin" / "ffmpeg.exe"
FFPROBE = ROOT / "runtime" / "bin" / "ffprobe.exe"


def _run(*arguments: str) -> str:
    completed = subprocess.run(
        [arguments[0], *arguments[1:]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(arguments)}\n{completed.stderr[-3000:]}")
    return completed.stdout


def main() -> int:
    if not FFMPEG.is_file() or not FFPROBE.is_file():
        raise RuntimeError("Bundled FFmpeg runtime is missing")

    with tempfile.TemporaryDirectory(prefix="haizflow-ffmpeg-") as temporary:
        work = Path(temporary)
        source = work / "source.mp4"
        voice = work / "voice.wav"
        rendered = work / "rendered.mp4"
        subtitle = work / "caption.ass"
        subtitle.write_text(
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 240\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,20,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.20,0:00:01.50,Default,,0,0,0,,HaizFlow FFmpeg test\n",
            encoding="utf-8",
        )

        _run(
            str(FFMPEG), "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
        )
        _run(
            str(FFMPEG), "-y", "-v", "error", "-i", str(source),
            "-vn", "-af", "atempo=1.25", "-c:a", "pcm_s16le", str(voice),
        )
        ass_path = subtitle.as_posix().replace(":", r"\:").replace("'", r"\'")
        _run(
            str(FFMPEG), "-y", "-v", "error", "-i", str(source), "-i", str(voice),
            "-filter_complex", f"[0:a][1:a]amix=inputs=2:duration=first[a];[0:v]ass='{ass_path}'[v]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(rendered),
        )
        payload = json.loads(
            _run(
                str(FFPROBE), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                "-of", "json", str(rendered),
            )
        )
        streams = payload.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        duration = float(payload.get("format", {}).get("duration", 0))
        if not video or (video.get("width"), video.get("height")) != (320, 240):
            raise RuntimeError(f"Unexpected rendered video stream: {video}")
        if not audio or not 1.0 <= duration <= 2.1:
            raise RuntimeError(f"Unexpected rendered audio/duration: audio={audio}, duration={duration}")

    print("FFmpeg production codec regression passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
