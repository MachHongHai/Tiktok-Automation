import os
import subprocess

import srt

from haizflow.pipeline.process_registry import check_cancellation, register_process, unregister_process
from haizflow.schemas.video import CropSettings, SubtitleStyle
from haizflow.services.video_store import log_to_video
from haizflow.utils.ffmpeg import get_video_dimensions, get_video_duration, preferred_video_encoder


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def _ass_timestamp(value) -> str:
    total_centiseconds = round(value.total_seconds() * 100)
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"


def _write_positioned_ass(srt_path: str, ass_path: str, subtitle_style: SubtitleStyle, width: int, height: int):
    """Convert SRT to ASS so a dragged preview position is reproduced exactly in FFmpeg."""
    with open(srt_path, "r", encoding="utf-8") as file:
        subtitles = list(srt.parse(file.read()))
    x = round(width * subtitle_style.position_x_percent / 100)
    y = round(height * subtitle_style.position_y_percent / 100)
    header = "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,Arial,{subtitle_style.font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{subtitle_style.outline},1,2,0,0,{subtitle_style.margin_bottom},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ])
    lines = [header]
    for subtitle in subtitles:
        start = _ass_timestamp(subtitle.start)
        end = _ass_timestamp(subtitle.end)
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\pos({x},{y})}}{_escape_ass_text(subtitle.content)}")
    with open(ass_path, "w", encoding="utf-8-sig") as file:
        file.write("\n".join(lines))


def _crop_filter(crop: CropSettings) -> str | None:
    if any((crop.left_percent, crop.right_percent, crop.top_percent, crop.bottom_percent)):
        left = max(0, min(84, crop.left_percent))
        right = max(0, min(84, crop.right_percent))
        top = max(0, min(84, crop.top_percent))
        bottom = max(0, min(84, crop.bottom_percent))
        width_ratio = max(0.15, (100 - left - right) / 100)
        height_ratio = max(0.15, (100 - top - bottom) / 100)
        return (
            f"crop=trunc(iw*{width_ratio:.4f}/2)*2:trunc(ih*{height_ratio:.4f}/2)*2:"
            f"trunc(iw*{left / 100:.4f}/2)*2:trunc(ih*{top / 100:.4f}/2)*2"
        )
    if crop.zoom_percent <= 100:
        return None
    zoom = crop.zoom_percent / 100
    x_factor = max(0, min(1, (crop.pan_x_percent + 100) / 200))
    y_factor = max(0, min(1, (crop.pan_y_percent + 100) / 200))
    return (
        f"crop=trunc(iw/{zoom}/2)*2:trunc(ih/{zoom}/2)*2:"
        f"(iw-ow)*{x_factor:.4f}:(ih-oh)*{y_factor:.4f}"
    )


def _ffmpeg_path(path: str, working_dir: str) -> str:
    """Prefer relative paths, but keep cross-drive Windows paths valid."""
    try:
        return os.path.relpath(path, start=working_dir).replace("\\", "/")
    except ValueError:
        return os.path.abspath(path).replace("\\", "/")


def render_video(video_path: str, voice_wav_path: str, srt_path: str, output_path: str, output_format: str, subtitle_style: SubtitleStyle, crop: CropSettings, video_id: str):
    """Render cropped video, positioned subtitles, and dubbed audio with FFmpeg."""
    log_to_video(video_id, f"Starting video render. Format selected: '{output_format}'")
    video_temp_dir = os.path.dirname(os.path.abspath(srt_path))
    source_width, source_height = get_video_dimensions(video_path)
    if output_format in {"tiktok_9_16_crop", "blur_background_9_16"}:
        subtitle_width, subtitle_height = 1080, 1920
    else:
        subtitle_width = max(2, int(source_width * 100 / crop.zoom_percent) // 2 * 2)
        subtitle_height = max(2, int(source_height * 100 / crop.zoom_percent) // 2 * 2)

    ass_path = os.path.join(video_temp_dir, "positioned_subtitles.ass")
    _write_positioned_ass(srt_path, ass_path, subtitle_style, subtitle_width, subtitle_height)
    rel_video = _ffmpeg_path(video_path, video_temp_dir)
    rel_voice = _ffmpeg_path(voice_wav_path, video_temp_dir)
    rel_ass = _ffmpeg_path(ass_path, video_temp_dir)
    rel_output = _ffmpeg_path(output_path, video_temp_dir)
    ass_filter_path = rel_ass.replace(":", "\\:").replace("'", "'\\\\''")
    ass_filter = f"ass='{ass_filter_path}'"
    filters = []
    crop_filter = _crop_filter(crop)
    if crop_filter:
        filters.append(crop_filter)
    if output_format == "tiktok_9_16_crop":
        filters.extend(["scale=1080:1920:force_original_aspect_ratio=increase", "crop=1080:1920"])
    elif output_format == "blur_background_9_16":
        prefix = ",".join(filters)
        source = f"[0:v]{prefix + ',' if prefix else ''}split[base][fg]"
        vf_filter = (
            f"{source};[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=15:3[bg];"
            f"[fg]scale=1080:1920:force_original_aspect_ratio=decrease[front];[bg][front]overlay=(W-w)/2:(H-h)/2,{ass_filter}"
        )
    if output_format != "blur_background_9_16":
        filters.append(ass_filter)
        vf_filter = ",".join(filters)

    video_encoder, video_encoder_args = preferred_video_encoder()
    source_duration = get_video_duration(video_path)
    if source_duration <= 0:
        raise RuntimeError("Unable to determine the source video duration before rendering.")
    cmd_prefix = [
        "ffmpeg", "-y", "-i", rel_video, "-i", rel_voice,
        "-map", "0:v:0", "-map", "1:a:0", "-vf", vf_filter,
        "-t", f"{source_duration:.6f}",
    ]
    audio_args = ["-c:a", "aac", "-b:a", "192k", rel_output]

    def run_render(encoder: str, encoder_args: list[str]):
        command = cmd_prefix + ["-c:v", encoder, *encoder_args, *audio_args]
        log_to_video(video_id, f"Running FFmpeg render with {encoder} in Cwd: {video_temp_dir}")
        check_cancellation(video_id)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=video_temp_dir)
        register_process(video_id, process)
        _stdout, process_stderr = process.communicate()
        unregister_process(video_id, process)
        check_cancellation(video_id)
        return process.returncode, process_stderr

    return_code, stderr = run_render(video_encoder, video_encoder_args)
    if return_code != 0 and video_encoder != "libx264":
        log_to_video(video_id, f"Hardware encoder {video_encoder} failed; retrying with libx264.")
        return_code, stderr = run_render("libx264", ["-preset", "veryfast", "-crf", "23"])
    if return_code != 0:
        log_to_video(video_id, f"FFmpeg Render Error output:\n{stderr}")
        raise RuntimeError(f"FFmpeg render failed with exit code {return_code}")
    log_to_video(video_id, f"Successfully rendered final video to: {output_path}")
