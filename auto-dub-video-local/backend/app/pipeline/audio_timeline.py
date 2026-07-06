import os
import json
from pydub import AudioSegment
from pydub.effects import speedup
from app.job_store import log_to_job
from app.utils.ffmpeg import get_video_duration

# Maximum allowed speed factor for time-stretching (2.0x = 100% faster)
MAX_SPEED_FACTOR = 2.0
# Maximum allowed overrun (ms) after time-stretching before hard truncation
MAX_OVERRUN_AFTER_STRETCH_MS = 300

def build_audio_timeline(segments_json_path: str, voice_parts_dir: str, video_path: str, output_wav_path: str, job_id: str, no_vocals_path: str = None, original_video_volume: int = 60):
    """Overlays generated voice MP3 parts on top of a silent or accompaniment audio track based on timestamps."""
    log_to_job(job_id, "Starting build of the audio timeline...")
    
    # Retrieve duration to build the baseline silence track
    video_dur = get_video_duration(video_path)
    log_to_job(job_id, f"Base video duration: {video_dur:.2f} seconds")
    
    video_dur_ms = int(video_dur * 1000)
    if video_dur_ms <= 0:
        video_dur_ms = 1000  # Fallback duration
        
    # Create silent background audio or load separation accompaniment
    if no_vocals_path and os.path.exists(no_vocals_path):
        log_to_job(job_id, f"Loading background accompaniment track: {no_vocals_path}")
        try:
            bg_audio = AudioSegment.from_file(no_vocals_path)
            # Lower accompaniment by custom percentage so speech stands out
            import math
            if original_video_volume <= 0:
                db_change = -100
                log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Muting accompaniment.")
            else:
                db_change = 20 * math.log10(original_video_volume / 100.0)
                log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Adjusting accompaniment by {db_change:.2f} dB.")
            bg_audio = bg_audio + db_change
            # Convert background audio to mono and 16000Hz (the format whisperX/edge-tts uses)
            base_audio = bg_audio.set_frame_rate(16000).set_channels(1)
            log_to_job(job_id, f"Accompaniment loaded and pre-processed. Duration: {len(base_audio)}ms")
        except Exception as e:
            log_to_job(job_id, f"WARNING: Failed to load accompaniment track ({str(e)}). Falling back to silence.")
            base_audio = AudioSegment.silent(duration=video_dur_ms, frame_rate=16000)
    else:
        base_audio = AudioSegment.silent(duration=video_dur_ms, frame_rate=16000)
    
    with open(segments_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
        
    last_end_ms = 0
    total = len(segments)
    for idx, seg in enumerate(segments, 1):
        part_filename = f"voice_{idx:04d}.mp3"
        part_path = os.path.join(voice_parts_dir, part_filename)
        
        if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
            continue
            
        start_ms = int(seg["start"] * 1000)
        end_ms = int(seg["end"] * 1000)
        seg_dur = end_ms - start_ms
        
        try:
            tts_segment = AudioSegment.from_file(part_path)
            tts_dur = len(tts_segment)
            
            # Dynamic Time-Stretching: speed up TTS if it overruns the segment duration
            if tts_dur > seg_dur:
                if seg_dur <= 0:
                    speed_factor = MAX_SPEED_FACTOR
                else:
                    speed_factor = tts_dur / seg_dur
                
                if speed_factor <= MAX_SPEED_FACTOR:
                    # Speed up entirely within the safe range
                    log_to_job(job_id, f"[{idx}/{total}] TTS overran by {tts_dur - seg_dur}ms. Applying time-stretch at {speed_factor:.2f}x speed.")
                    try:
                        tts_segment = speedup(tts_segment, playback_speed=speed_factor)
                    except Exception as stretch_err:
                        log_to_job(job_id, f"[{idx}/{total}] Time-stretch failed ({str(stretch_err)}). Using original audio.")
                else:
                    # Speed factor exceeds max: apply max stretch
                    log_to_job(job_id, f"[{idx}/{total}] TTS overran by {tts_dur - seg_dur}ms (speed factor {speed_factor:.2f}x exceeds max {MAX_SPEED_FACTOR}x). Stretching to {MAX_SPEED_FACTOR}x.")
                    try:
                        tts_segment = speedup(tts_segment, playback_speed=MAX_SPEED_FACTOR)
                    except Exception as stretch_err:
                        log_to_job(job_id, f"[{idx}/{total}] Time-stretch failed ({str(stretch_err)}). Using original audio.")
                
            # Record the end time of the current segment to prevent overlap for the next segment
            last_end_ms = start_ms + len(tts_segment)
            
            # If the voice overlay exceeds current track length, expand it
            if start_ms + len(tts_segment) > len(base_audio):
                extra_ms = (start_ms + len(tts_segment)) - len(base_audio)
                base_audio = base_audio + AudioSegment.silent(duration=extra_ms, frame_rate=16000)
                
            base_audio = base_audio.overlay(tts_segment, position=start_ms)
        except Exception as e:
            log_to_job(job_id, f"Failed to overlay segment {idx} ({part_filename}): {str(e)}")
            
    # Export mono 16kHz WAV file
    base_audio.export(output_wav_path, format="wav", parameters=["-ac", "1", "-ar", "16000"])
    log_to_job(job_id, f"Successfully exported dubbed audio to: {output_wav_path}")

def convert_to_wav(input_path: str, output_path: str, job_id: str):
    """Converts a general audio file format into a mono 16kHz WAV file."""
    log_to_job(job_id, f"Converting voice file '{input_path}' to WAV '{output_path}'...")
    try:
        audio = AudioSegment.from_file(input_path)
        audio.export(output_path, format="wav", parameters=["-ac", "1", "-ar", "16000"])
        log_to_job(job_id, "Voice conversion successful.")
    except Exception as e:
        log_to_job(job_id, f"Failed to convert voice file: {str(e)}")
        raise e

def mix_accompaniment_and_voice(voice_path: str, no_vocals_path: str, output_wav_path: str, original_video_volume: int, job_id: str):
    """Mixes a full voice track and background accompaniment track together into output_wav_path (for Mode C)."""
    log_to_job(job_id, f"Mixing full narration voice '{voice_path}' with accompaniment '{no_vocals_path}'...")
    try:
        voice_audio = AudioSegment.from_file(voice_path).set_frame_rate(16000).set_channels(1)
        bg_audio = AudioSegment.from_file(no_vocals_path).set_frame_rate(16000).set_channels(1)
        # Lower accompaniment by custom percentage
        import math
        if original_video_volume <= 0:
            db_change = -100
            log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Muting accompaniment.")
        else:
            db_change = 20 * math.log10(original_video_volume / 100.0)
            log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Adjusting accompaniment by {db_change:.2f} dB.")
        bg_audio = bg_audio + db_change
        
        # Overlay voice onto bg_audio. Expand if voice is longer than bg_audio.
        if len(voice_audio) > len(bg_audio):
            extra_ms = len(voice_audio) - len(bg_audio)
            bg_audio = bg_audio + AudioSegment.silent(duration=extra_ms, frame_rate=16000)
            
        mixed = bg_audio.overlay(voice_audio, position=0)
        mixed.export(output_wav_path, format="wav", parameters=["-ac", "1", "-ar", "16000"])
        log_to_job(job_id, f"Successfully mixed narration and accompaniment into: {output_wav_path}")
    except Exception as e:
        log_to_job(job_id, f"Failed to mix narration and accompaniment: {str(e)}")
        raise e
