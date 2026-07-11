import os
import json
from pydub import AudioSegment
from pydub.effects import speedup
from autodub.services.job_store import log_to_job
from autodub.utils.ffmpeg import get_video_duration

# Keep dubbing intelligible while giving languages such as Japanese enough room.
MAX_SPEED_FACTOR = 1.45

def trim_silence(audio: AudioSegment, silence_threshold_db: float = -50.0) -> AudioSegment:
    """Trims leading and trailing silence from an AudioSegment to remove delay and trailing padding."""
    start_trim = 0
    chunk_size = 10
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i+chunk_size]
        if chunk.dBFS > silence_threshold_db:
            # Keep a small 30ms buffer to avoid abrupt cut-off
            start_trim = max(0, i - 30)
            break
            
    end_trim = len(audio)
    for i in range(len(audio), 0, -chunk_size):
        chunk = audio[i - chunk_size : i]
        if chunk.dBFS > silence_threshold_db:
            # Keep a small 50ms buffer at the end
            end_trim = min(len(audio), i + 50)
            break
            
    if start_trim < end_trim:
        return audio[start_trim:end_trim]
    return audio

def build_audio_timeline(
    segments_json_path: str,
    voice_parts_dir: str,
    video_path: str,
    output_wav_path: str,
    job_id: str,
    background_audio_path: str = None,
    original_video_volume: int = 60,
):
    """Overlays generated voice MP3 parts on top of the original/background audio track based on timestamps."""
    log_to_job(job_id, "Starting build of the audio timeline...")
    
    # Retrieve duration to build the baseline silence track
    video_dur = get_video_duration(video_path)
    log_to_job(job_id, f"Base video duration: {video_dur:.2f} seconds")
    
    video_dur_ms = int(video_dur * 1000)
    if video_dur_ms <= 0:
        video_dur_ms = 1000  # Fallback duration
        
    # Create silent background audio or load original/background audio.
    if background_audio_path and os.path.exists(background_audio_path):
        log_to_job(job_id, f"Loading background/original audio track: {background_audio_path}")
        try:
            bg_audio = AudioSegment.from_file(background_audio_path)
            # Lower background/original audio by custom percentage so dubbed speech stands out.
            import math
            if original_video_volume <= 0:
                db_change = -100
                log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Muting original/background audio.")
            else:
                db_change = 20 * math.log10(original_video_volume / 100.0)
                log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Adjusting original/background audio by {db_change:.2f} dB.")
            bg_audio = bg_audio + db_change
            # Convert background audio to mono and 16000Hz (the format whisperX/edge-tts uses)
            base_audio = bg_audio.set_frame_rate(16000).set_channels(1)
            log_to_job(job_id, f"Original/background audio loaded and pre-processed. Duration: {len(base_audio)}ms")
        except Exception as e:
            log_to_job(job_id, f"WARNING: Failed to load original/background audio track ({str(e)}). Falling back to silence.")
            base_audio = AudioSegment.silent(duration=video_dur_ms, frame_rate=16000)
    else:
        base_audio = AudioSegment.silent(duration=video_dur_ms, frame_rate=16000)

    # The final audio must always match the video. Source tracks can occasionally
    # be a few milliseconds longer than the video container reports.
    base_audio = base_audio[:video_dur_ms]
    if len(base_audio) < video_dur_ms:
        base_audio += AudioSegment.silent(
            duration=video_dur_ms - len(base_audio),
            frame_rate=16000,
        )
    
    with open(segments_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
        
    last_end_ms = 0
    total = len(segments)
    for idx, seg in enumerate(segments, 1):
        part_filename = f"voice_{idx:04d}.mp3"
        part_path = os.path.join(voice_parts_dir, part_filename)
        
        if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
            continue
            
        start_ms = max(0, int(seg["start"] * 1000))
        
        # Place the speech start position: it must not overlap with the previous segment's end
        placed_start_ms = max(start_ms, last_end_ms)
        if placed_start_ms >= video_dur_ms:
            log_to_job(job_id, f"[{idx}/{total}] Skipping TTS: its slot starts after the video ends.")
            continue
        
        # Determine target end time: start of the next segment (original) or end of video
        if idx < total:
            next_start_ms = int(segments[idx]["start"] * 1000)
        else:
            next_start_ms = video_dur_ms
            
        # The available duration before overlapping with the next speech segment
        slot_end_ms = min(video_dur_ms, max(placed_start_ms, next_start_ms))
        available_dur = slot_end_ms - placed_start_ms
        if available_dur <= 0:
            log_to_job(job_id, f"[{idx}/{total}] Skipping TTS: no available timeline slot.")
            continue
        
        try:
            tts_segment = AudioSegment.from_file(part_path)
            # Trim leading/trailing silence from the generated TTS audio to remove delay/gaps
            tts_segment = trim_silence(tts_segment)
            tts_dur = len(tts_segment)
            
            # Fit every spoken part into its own subtitle slot so delays never
            # cascade and extend the final video.
            if tts_dur > available_dur:
                speed_factor = min(tts_dur / available_dur, MAX_SPEED_FACTOR)
                    
                log_to_job(job_id, f"[{idx}/{total}] TTS overran available gap ({available_dur}ms). Applying time-stretch at {speed_factor:.2f}x speed.")
                try:
                    tts_segment = speedup(tts_segment, playback_speed=speed_factor)
                except Exception as stretch_err:
                    log_to_job(job_id, f"[{idx}/{total}] Time-stretch failed ({str(stretch_err)}). Using original audio.")

            if len(tts_segment) > available_dur:
                clipped_ms = len(tts_segment) - available_dur
                tts_segment = tts_segment[:available_dur]
                log_to_job(job_id, f"[{idx}/{total}] TTS still exceeded its slot after time-stretch. Trimmed {clipped_ms}ms to preserve video duration.")
            
            # Record the actual end time of the current segment
            last_end_ms = placed_start_ms + len(tts_segment)
            
            base_audio = base_audio.overlay(tts_segment, position=placed_start_ms)
        except Exception as e:
            log_to_job(job_id, f"Failed to overlay segment {idx} ({part_filename}): {str(e)}")
            
    # Export mono 16kHz WAV file
    base_audio[:video_dur_ms].export(output_wav_path, format="wav", parameters=["-ac", "1", "-ar", "16000"])
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

def mix_accompaniment_and_voice(voice_path: str, background_audio_path: str, output_wav_path: str, original_video_volume: int, job_id: str):
    """Mixes a full voice track and original/background audio track together into output_wav_path."""
    log_to_job(job_id, f"Mixing full narration voice '{voice_path}' with original/background audio '{background_audio_path}'...")
    try:
        voice_audio = AudioSegment.from_file(voice_path).set_frame_rate(16000).set_channels(1)
        bg_audio = AudioSegment.from_file(background_audio_path).set_frame_rate(16000).set_channels(1)
        # Lower original/background audio by custom percentage.
        import math
        if original_video_volume <= 0:
            db_change = -100
            log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Muting original/background audio.")
        else:
            db_change = 20 * math.log10(original_video_volume / 100.0)
            log_to_job(job_id, f"Original video volume set to {original_video_volume}%. Adjusting original/background audio by {db_change:.2f} dB.")
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

