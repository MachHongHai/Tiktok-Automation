import os
import json
import traceback
import subprocess
import requests
import time
from app.job_store import update_job, log_to_job, get_job
from app.pipeline.extract_audio import extract_audio
from app.pipeline.transcribe import transcribe
from app.pipeline.translate import translate_segments
from app.pipeline.subtitle import generate_srt, parse_srt_to_segments
from app.pipeline.tts import generate_voice_parts, generate_single_voice
from app.pipeline.audio_timeline import build_audio_timeline, convert_to_wav, mix_accompaniment_and_voice
from app.pipeline.audio_separation import separate_audio
from app.pipeline.render import render_video
from app.pipeline.job_manager import start_job, check_cancellation, clean_job

def ensure_ollama_running(job_id: str):
    """Checks if Ollama server is running. If not, automatically starts it in the background using the project binary."""
    from app.config import OLLAMA_BASE_URL, BASE_DIR, TRANSLATOR_PROVIDER
    
    if TRANSLATOR_PROVIDER != "ollama":
        return
        
    try:
        response = requests.get(OLLAMA_BASE_URL, timeout=1.5)
        if response.status_code == 200:
            log_to_job(job_id, "Ollama server is already running.")
            return
    except Exception:
        log_to_job(job_id, "Ollama server is not running. Attempting to start it automatically...")
        
    ollama_exe = os.path.join(BASE_DIR, "bin", "ollama", "ollama.exe")
    if not os.path.exists(ollama_exe):
        log_to_job(job_id, f"WARNING: Local Ollama binary not found at {ollama_exe}. Cannot auto-start.")
        return
        
    # Configure env to save models in the D drive cache
    ollama_env = os.environ.copy()
    models_dir = os.path.abspath(os.path.join(BASE_DIR, ".cache", "ollama", "models"))
    os.makedirs(models_dir, exist_ok=True)
    ollama_env["OLLAMA_MODELS"] = models_dir
    
    try:
        creation_flags = 0
        if os.name == 'nt':
            # DETACHED_PROCESS = 0x00000008, CREATE_NEW_PROCESS_GROUP = 0x00000200
            creation_flags = 0x00000008 | 0x00000200
            
        subprocess.Popen(
            [ollama_exe, "serve"],
            creationflags=creation_flags,
            env=ollama_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True
        )
        log_to_job(job_id, "Ollama server process spawned. Waiting for initialization...")
        
        # Wait up to 10 seconds for the port to open
        for _ in range(10):
            time.sleep(1)
            try:
                response = requests.get(OLLAMA_BASE_URL, timeout=1.0)
                if response.status_code == 200:
                    log_to_job(job_id, "Ollama server initialized and running successfully.")
                    return
            except Exception:
                pass
        log_to_job(job_id, "WARNING: Spawned Ollama server but it did not respond in 10 seconds.")
    except Exception as e:
        log_to_job(job_id, f"ERROR: Failed to automatically start Ollama server: {str(e)}")

def process_job_sync(job_id: str):
    """Processes a video dubbing job from start to finish depending on its mode."""
    try:
        start_job(job_id)
        job = get_job(job_id)
        if not job:
            return
            
        update_job(job_id, status="processing", progress=5, step="starting")
        log_to_job(job_id, f"Processing started | Mode: {job.mode}")
        
        # Ensure Ollama is running if we are using it
        ensure_ollama_running(job_id)
        
        # Files mapping
        video_input = job.files["video_input"]
        final_video = job.files["final_video"]
        srt_output = job.files["srt_output"]
        voice_output = job.files["voice_output"]
        transcript_json = job.files["transcript_json"]
        
        # Set up working paths
        job_dir = os.path.dirname(os.path.dirname(video_input))
        voice_parts_dir = os.path.join(job_dir, "temp", "voice_parts")
        temp_audio_wav = os.path.join(job_dir, "temp", "audio.wav")
        source_segments_json = os.path.join(job_dir, "temp", "source_segments.json")
        
        if job.mode == "A":
            # Mode A: Full Auto
            # 1. Extract audio
            check_cancellation(job_id)
            update_job(job_id, progress=10, step="extracting_audio")
            extract_audio(video_input, temp_audio_wav, job_id)
            
            # Audio Separation (Mandatory)
            check_cancellation(job_id)
            update_job(job_id, progress=15, step="separating_audio")
            separation_dir = os.path.join(job_dir, "temp", "separation")
            vocals_path, no_vocals_path = separate_audio(temp_audio_wav, separation_dir, job_id)
            transcribe_audio_target = vocals_path
            no_vocals_audio_target = no_vocals_path
            
            # 2. Transcribe using WhisperX
            check_cancellation(job_id)
            update_job(job_id, progress=30, step="transcribing")
            transcribe(transcribe_audio_target, source_segments_json, job.source_language, job_id)
            
            # 3. Translate segments to Vietnamese
            check_cancellation(job_id)
            update_job(job_id, progress=50, step="translating")
            translate_segments(source_segments_json, transcript_json, job_id)
            
            # 4. Generate Vietnamese Subtitles SRT
            check_cancellation(job_id)
            update_job(job_id, progress=60, step="creating_subtitle")
            generate_srt(transcript_json, srt_output, job.subtitle_style.max_chars_per_line, job_id)
            
            # 5. Generate Speech parts using edge-tts
            check_cancellation(job_id)
            update_job(job_id, progress=75, step="creating_voice")
            generate_voice_parts(transcript_json, voice_parts_dir, job.tts_voice, job_id)
            
            # 6. Build the audio timeline WAV
            check_cancellation(job_id)
            update_job(job_id, progress=85, step="building_audio_timeline")
            build_audio_timeline(
                transcript_json, 
                voice_parts_dir, 
                video_input, 
                voice_output, 
                job_id, 
                no_vocals_path=no_vocals_audio_target,
                original_video_volume=job.original_video_volume
            )
            
            # 7. Render final video (burn subtitles + overlay voice)
            check_cancellation(job_id)
            update_job(job_id, progress=95, step="rendering")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job_id)
            
        elif job.mode == "B":
            # Mode B: Use Vietnamese Subtitle
            srt_input = job.files.get("srt_input")
            if not srt_input or not os.path.exists(srt_input):
                raise FileNotFoundError("Required subtitle input (.srt) is missing for Mode B.")
                
            # Extract and Separate Audio for background music (Mandatory)
            check_cancellation(job_id)
            update_job(job_id, progress=10, step="extracting_audio")
            extract_audio(video_input, temp_audio_wav, job_id)
            
            check_cancellation(job_id)
            update_job(job_id, progress=15, step="separating_audio")
            separation_dir = os.path.join(job_dir, "temp", "separation")
            vocals_path, no_vocals_path = separate_audio(temp_audio_wav, separation_dir, job_id)
            no_vocals_audio_target = no_vocals_path
                
            # 1. Parse SRT to segments JSON
            check_cancellation(job_id)
            update_job(job_id, progress=20, step="creating_subtitle")
            log_to_job(job_id, f"Parsing input subtitle file: {srt_input}")
            segments = parse_srt_to_segments(srt_input)
            with open(transcript_json, "w", encoding="utf-8") as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
                
            # Compile subtitle file to final target location (applies length limits if any)
            check_cancellation(job_id)
            generate_srt(transcript_json, srt_output, job.subtitle_style.max_chars_per_line, job_id)
            
            # 2. Generate Speech parts using edge-tts
            check_cancellation(job_id)
            update_job(job_id, progress=50, step="creating_voice")
            generate_voice_parts(transcript_json, voice_parts_dir, job.tts_voice, job_id)
            
            # 3. Build the audio timeline WAV
            check_cancellation(job_id)
            update_job(job_id, progress=75, step="building_audio_timeline")
            build_audio_timeline(
                transcript_json, 
                voice_parts_dir, 
                video_input, 
                voice_output, 
                job_id, 
                no_vocals_path=no_vocals_audio_target,
                original_video_volume=job.original_video_volume
            )
            
            # 4. Render final video
            check_cancellation(job_id)
            update_job(job_id, progress=90, step="rendering")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job_id)
            
        elif job.mode == "C":
            # Mode C: Use Vietnamese Script
            script_input = job.files.get("script_input")
            if not script_input or not os.path.exists(script_input):
                raise FileNotFoundError("Required script input (.txt) is missing for Mode C.")
                
            with open(script_input, "r", encoding="utf-8") as f:
                script_text = f.read().strip()
                
            if not script_text:
                raise ValueError("Script script_vi.txt is empty.")
                
            # Extract and Separate Audio for background music (Mandatory)
            check_cancellation(job_id)
            update_job(job_id, progress=5, step="extracting_audio")
            extract_audio(video_input, temp_audio_wav, job_id)
            
            check_cancellation(job_id)
            update_job(job_id, progress=10, step="separating_audio")
            separation_dir = os.path.join(job_dir, "temp", "separation")
            vocals_path, no_vocals_path = separate_audio(temp_audio_wav, separation_dir, job_id)
            no_vocals_audio_target = no_vocals_path
                
            # 1. Generate full narration voice file
            check_cancellation(job_id)
            update_job(job_id, progress=25, step="creating_voice")
            voice_raw_mp3 = os.path.join(job_dir, "temp", "voice_raw.mp3")
            generate_single_voice(script_text, voice_raw_mp3, job.tts_voice, job_id)
            
            # 2. Transcribe voice_raw.mp3 to get segments/timestamps (Vietnamese speech-to-text)
            check_cancellation(job_id)
            update_job(job_id, progress=50, step="transcribing")
            transcribe(voice_raw_mp3, transcript_json, "vi", job_id)
            
            # 3. Create subtitles from transcribed segments
            check_cancellation(job_id)
            update_job(job_id, progress=70, step="creating_subtitle")
            generate_srt(transcript_json, srt_output, job.subtitle_style.max_chars_per_line, job_id)
            
            # 4. Convert narration MP3 to WAV timeline format or mix with background
            check_cancellation(job_id)
            update_job(job_id, progress=80, step="building_audio_timeline")
            if no_vocals_audio_target:
                mix_accompaniment_and_voice(voice_raw_mp3, no_vocals_audio_target, voice_output, job.original_video_volume, job_id)
            else:
                convert_to_wav(voice_raw_mp3, voice_output, job_id)
            
            # 5. Render final video
            check_cancellation(job_id)
            update_job(job_id, progress=90, step="rendering")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job_id)
            
        else:
            raise ValueError(f"Invalid execution mode: {job.mode}")
            
        # Completion state
        update_job(job_id, status="done", progress=100, step="done")
        log_to_job(job_id, "Pipeline run finished successfully.")
        
    except Exception as e:
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        log_to_job(job_id, f"Execution failed: {error_msg}\n{stack_trace}")
        update_job(job_id, status="failed", error=error_msg, step="failed")
    finally:
        clean_job(job_id)
