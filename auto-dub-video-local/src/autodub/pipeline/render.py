import os
import subprocess
from autodub.services.job_store import log_to_job
from autodub.schemas.job import SubtitleStyle

def render_video(
    video_path: str,
    voice_wav_path: str,
    srt_path: str,
    output_path: str,
    output_format: str,
    subtitle_style: SubtitleStyle,
    job_id: str
):
    """Combines video, dubbed audio, and burned subtitles using FFmpeg with relative pathing."""
    log_to_job(job_id, f"Starting video render. Format selected: '{output_format}'")
    
    # Resolve job temp directory as cwd
    job_temp_dir = os.path.dirname(os.path.abspath(srt_path))
    
    # Calculate relative paths from temp directory to prevent Windows path/drive/space issues in FFmpeg
    rel_video_path = os.path.relpath(video_path, start=job_temp_dir).replace("\\", "/")
    rel_voice_wav_path = os.path.relpath(voice_wav_path, start=job_temp_dir).replace("\\", "/")
    rel_srt_path = os.path.relpath(srt_path, start=job_temp_dir).replace("\\", "/")
    rel_output_path = os.path.relpath(output_path, start=job_temp_dir).replace("\\", "/")
    
    # Extract subtitle styles
    fs = subtitle_style.font_size
    margin = subtitle_style.margin_bottom
    outline = subtitle_style.outline
    
    style_str = f"FontName=Arial,FontSize={fs},Outline={outline},Shadow=1,Alignment=2,MarginV={margin}"
    
    # Escape quotes inside SRT path for filter safety
    safe_srt_path = rel_srt_path.replace("'", "'\\\\''")
    safe_srt_filter = f"subtitles='{safe_srt_path}':force_style='{style_str}'"
    
    # Select filter graph based on requested output format
    if output_format == "tiktok_9_16_crop":
        vf_filter = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"{safe_srt_filter}"
        )
    elif output_format == "blur_background_9_16":
        vf_filter = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=15:3[bg];"
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{safe_srt_filter}"
        )
    else:  # keep_ratio
        vf_filter = safe_srt_filter
        
    cmd = [
        "ffmpeg", "-y",
        "-i", rel_video_path,
        "-i", rel_voice_wav_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        rel_output_path
    ]
    
    log_to_job(job_id, f"Running FFmpeg render command in Cwd: {job_temp_dir}")
    log_to_job(job_id, f"Command: {' '.join(cmd)}")
    
    from autodub.pipeline.job_manager import register_process, unregister_process, check_cancellation
    check_cancellation(job_id)
    
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=job_temp_dir)
    register_process(job_id, p)
    stdout, stderr = p.communicate()
    unregister_process(job_id, p)
    
    check_cancellation(job_id)
    
    if p.returncode != 0:
        log_to_job(job_id, f"FFmpeg Render Error output:\n{stderr}")
        raise RuntimeError(f"FFmpeg render failed with exit code {p.returncode}")
        
    log_to_job(job_id, f"Successfully rendered final video to: {output_path}")


