import os
import json
import traceback
from autodub.services.job_store import update_job, log_to_job, get_job
from autodub.pipeline.extract_audio import extract_audio
from autodub.pipeline.transcribe import transcribe
from autodub.services.translation import translate_segments
from autodub.pipeline.subtitle import generate_srt, parse_srt_to_segments
from autodub.pipeline.tts import generate_voice_parts, generate_single_voice
from autodub.pipeline.audio_timeline import build_audio_timeline, convert_to_wav, mix_accompaniment_and_voice
from autodub.pipeline.audio_separation import separate_audio
from autodub.pipeline.render import render_video
from autodub.pipeline.job_manager import start_job, check_cancellation, clean_job, is_cancelled
from autodub.services.ollama_runtime import ensure_ollama_running

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
            
            transcribe_audio_target = temp_audio_wav
            original_audio_target = temp_audio_wav
            if job.enable_audio_separation:
                check_cancellation(job_id)
                update_job(job_id, progress=15, step="separating_audio")
                separation_dir = os.path.join(job_dir, "temp", "separation")
                vocals_path, _no_vocals_path = separate_audio(temp_audio_wav, separation_dir, job_id)
                transcribe_audio_target = vocals_path
            else:
                log_to_job(job_id, "Audio separation disabled. Transcribing from original audio.")
            
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
                background_audio_path=original_audio_target,
                original_video_volume=job.original_video_volume
            )
            
            # 7. Render final video (burn subtitles + overlay voice)
            check_cancellation(job_id)
            update_job(job_id, progress=95, step="rendering")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job.crop, job_id)
            
        elif job.mode == "B":
            # Mode B: Use Vietnamese Subtitle
            srt_input = job.files.get("srt_input")
            if not srt_input or not os.path.exists(srt_input):
                raise FileNotFoundError("Required subtitle input (.srt) is missing for Mode B.")
                
            # Extract original audio for background mix.
            check_cancellation(job_id)
            update_job(job_id, progress=10, step="extracting_audio")
            extract_audio(video_input, temp_audio_wav, job_id)
            
            original_audio_target = temp_audio_wav
                
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
                background_audio_path=original_audio_target,
                original_video_volume=job.original_video_volume
            )
            
            # 4. Render final video
            check_cancellation(job_id)
            update_job(job_id, progress=90, step="rendering")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job.crop, job_id)
            
        elif job.mode == "C":
            # Mode C: Use Vietnamese Script
            script_input = job.files.get("script_input")
            if not script_input or not os.path.exists(script_input):
                raise FileNotFoundError("Required script input (.txt) is missing for Mode C.")
                
            with open(script_input, "r", encoding="utf-8") as f:
                script_text = f.read().strip()
                
            if not script_text:
                raise ValueError("Script script_vi.txt is empty.")
                
            # Extract original audio for background mix.
            check_cancellation(job_id)
            update_job(job_id, progress=5, step="extracting_audio")
            extract_audio(video_input, temp_audio_wav, job_id)
            
            original_audio_target = temp_audio_wav
                
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
            if original_audio_target:
                mix_accompaniment_and_voice(voice_raw_mp3, original_audio_target, voice_output, job.original_video_volume, job_id)
            else:
                convert_to_wav(voice_raw_mp3, voice_output, job_id)
            
            # 5. Render final video
            check_cancellation(job_id)
            update_job(job_id, progress=90, step="rendering")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job.crop, job_id)
            
        else:
            raise ValueError(f"Invalid execution mode: {job.mode}")
            
        # Completion state
        update_job(job_id, status="done", progress=100, step="done")
        log_to_job(job_id, "Pipeline run finished successfully.")
        
    except Exception as e:
        error_msg = str(e)
        if is_cancelled(job_id) or error_msg == "Job cancelled by user.":
            update_job(job_id, status="cancelled", error=None, step="cancelled")
            log_to_job(job_id, "Job cancelled by user.")
            return
        stack_trace = traceback.format_exc()
        log_to_job(job_id, f"Execution failed: {error_msg}\n{stack_trace}")
        update_job(job_id, status="failed", error=error_msg, step="failed")
    finally:
        clean_job(job_id)

