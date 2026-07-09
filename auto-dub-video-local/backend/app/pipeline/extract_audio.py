import subprocess
from app.services.job_store import log_to_job
from app.pipeline.job_manager import register_process, unregister_process, check_cancellation

def extract_audio(video_path: str, output_wav_path: str, job_id: str):
    """Extracts audio from video to a 16kHz mono WAV file."""
    log_to_job(job_id, f"Extracting audio from: {video_path}")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        output_wav_path
    ]
    
    check_cancellation(job_id)
    
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    register_process(job_id, p)
    stdout, stderr = p.communicate()
    unregister_process(job_id, p)
    
    check_cancellation(job_id)
    
    if p.returncode != 0:
        log_to_job(job_id, f"FFmpeg Error output:\n{stderr}")
        raise RuntimeError(f"FFmpeg extraction failed with exit code {p.returncode}")
        
    log_to_job(job_id, f"Successfully extracted audio to: {output_wav_path}")
