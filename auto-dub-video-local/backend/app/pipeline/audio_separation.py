import os
import subprocess
import sys
import torch
from app.job_store import log_to_job
from app.pipeline.job_manager import register_process, unregister_process, check_cancellation

def separate_audio(audio_path: str, output_dir: str, job_id: str) -> tuple[str, str]:
    """
    Separates vocals and accompaniment from the given audio file using Demucs.
    Returns a tuple: (vocals_path, no_vocals_path)
    """
    log_to_job(job_id, f"Starting audio source separation using Demucs on: {audio_path}")
    
    # Auto-detect device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log_to_job(job_id, f"Demucs device selected: {device}")
    
    python_exe = sys.executable
    
    # We use --two-stems=vocals to output vocals and accompaniment (no_vocals)
    cmd = [
        python_exe, "-m", "demucs.separate",
        "--two-stems", "vocals",
        "-o", output_dir,
        "-d", device,
        audio_path
    ]
    
    log_to_job(job_id, f"Running Demucs command: {' '.join(cmd)}")
    
    check_cancellation(job_id)
    
    # Run Demucs separate as a subprocess
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    register_process(job_id, p)
    
    # Wait for completion and capture outputs
    stdout, stderr = p.communicate()
    unregister_process(job_id, p)
    
    check_cancellation(job_id)
    
    if p.returncode != 0:
        log_to_job(job_id, f"Demucs separation failed with exit code {p.returncode}")
        log_to_job(job_id, f"Error details:\n{stderr}")
        raise RuntimeError(f"Demucs audio separation failed with exit code {p.returncode}: {stderr}")
        
    track_name = os.path.splitext(os.path.basename(audio_path))[0]
    
    # Search output_dir for vocals.wav and no_vocals.wav
    vocals_path = None
    no_vocals_path = None
    
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file == "vocals.wav":
                vocals_path = os.path.join(root, file)
            elif file == "no_vocals.wav":
                no_vocals_path = os.path.join(root, file)
                
    if not vocals_path or not no_vocals_path:
        # Fallback check for exact default path
        model_name = "htdemucs"
        vocals_path = os.path.join(output_dir, model_name, track_name, "vocals.wav")
        no_vocals_path = os.path.join(output_dir, model_name, track_name, "no_vocals.wav")
        
    if not os.path.exists(vocals_path) or not os.path.exists(no_vocals_path):
        raise FileNotFoundError(
            f"Could not locate separated audio files in {output_dir}. "
            f"Expected vocals at {vocals_path} and no_vocals at {no_vocals_path}"
        )
        
    log_to_job(job_id, "Audio source separation completed successfully.")
    log_to_job(job_id, f"Vocals path: {vocals_path}")
    log_to_job(job_id, f"No-vocals path: {no_vocals_path}")
    
    return vocals_path, no_vocals_path
