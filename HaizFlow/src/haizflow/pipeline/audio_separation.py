import os
import subprocess
import sys
from haizflow.core.hardware import runtime_profile
from haizflow.services.video_store import log_to_video
from haizflow.pipeline.process_registry import register_process, unregister_process, check_cancellation

def separate_audio(audio_path: str, output_dir: str, video_id: str) -> tuple[str, str]:
    """
    Separates vocals and accompaniment from the given audio file using Demucs.
    Returns a tuple: (vocals_path, no_vocals_path)
    """
    log_to_video(video_id, f"Starting audio source separation using Demucs on: {audio_path}")
    
    # Auto-detect device
    profile = runtime_profile()
    device = "cuda" if profile.cuda_available else "cpu"
    log_to_video(video_id, f"Demucs device selected: {device}")
    
    python_exe = sys.executable
    
    # We use --two-stems=vocals to output vocals and accompaniment (no_vocals)
    cmd = [
        python_exe, "-m", "demucs.separate",
        "--two-stems", "vocals",
        "-o", output_dir,
        "-d", device,
        audio_path
    ]
    if device == "cpu":
        videos = 1 if profile.key in {"cpu_low_memory", "cpu_minimum"} else max(1, min(4, profile.cpu_threads // 2))
        cmd[7:7] = ["--shifts", "0", "--overlap", "0.1", "--segment", "7", "-j", str(videos)]
        log_to_video(
            video_id,
            f"CPU Demucs profile enabled with {videos} worker(s). Source separation will be slower without CUDA.",
        )
    
    log_to_video(video_id, f"Running Demucs command: {' '.join(cmd)}")
    
    check_cancellation(video_id)
    
    # Run Demucs separate as a subprocess
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    register_process(video_id, p)
    
    # Wait for completion and capture outputs
    stdout, stderr = p.communicate()
    unregister_process(video_id, p)
    
    check_cancellation(video_id)
    
    if p.returncode != 0:
        log_to_video(video_id, f"Demucs separation failed with exit code {p.returncode}")
        log_to_video(video_id, f"Error details:\n{stderr}")
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
        
    log_to_video(video_id, "Audio source separation completed successfully.")
    log_to_video(video_id, f"Vocals path: {vocals_path}")
    log_to_video(video_id, f"No-vocals path: {no_vocals_path}")
    
    return vocals_path, no_vocals_path

