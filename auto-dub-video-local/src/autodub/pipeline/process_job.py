import os
import traceback

from autodub.pipeline.audio_separation import separate_audio
from autodub.pipeline.audio_timeline import build_audio_timeline
from autodub.pipeline.extract_audio import extract_audio
from autodub.pipeline.job_manager import check_cancellation, clean_job, is_cancelled, start_job
from autodub.pipeline.render import render_video
from autodub.pipeline.subtitle import generate_srt
from autodub.pipeline.transcribe import transcribe
from autodub.pipeline.tts import generate_voice_parts
from autodub.services.job_store import get_job, log_to_job, update_job
from autodub.services.translation import translate_segments


def process_job_sync(job_id: str):
    """Run the full-auto desktop dubbing pipeline."""
    try:
        start_job(job_id)
        job = get_job(job_id)
        if not job:
            return
        if job.mode != "A":
            raise ValueError("Only full-auto jobs are supported by the desktop app.")

        if job.translator_provider != "hymt2":
            log_to_job(job_id, "Migrated legacy translation setting to HY-MT2.")
            job = update_job(job_id, translator_provider="hymt2") or job
        update_job(job_id, status="processing", progress=5, step="starting")
        log_to_job(job_id, "Processing started | Mode: Full Auto | Translator: HY-MT2")

        video_input = job.files["video_input"]
        final_video = job.files["final_video"]
        srt_output = job.files["srt_output"]
        voice_output = job.files["voice_output"]
        transcript_json = job.files["transcript_json"]

        job_dir = os.path.dirname(os.path.dirname(video_input))
        voice_parts_dir = os.path.join(job_dir, "temp", "voice_parts")
        temp_audio_wav = os.path.join(job_dir, "temp", "audio.wav")
        source_segments_json = os.path.join(job_dir, "temp", "source_segments.json")

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

        check_cancellation(job_id)
        update_job(job_id, progress=30, step="transcribing")
        _segments, detected_language = transcribe(
            transcribe_audio_target,
            source_segments_json,
            job.source_language,
            job_id,
        )

        check_cancellation(job_id)
        update_job(job_id, progress=50, step="translating")
        translate_segments(
            source_segments_json,
            transcript_json,
            job_id,
            job.target_language,
            source_language=detected_language or job.source_language,
            provider="hymt2",
        )

        check_cancellation(job_id)
        update_job(job_id, progress=60, step="creating_subtitle")
        generate_srt(transcript_json, srt_output, job.subtitle_style.max_chars_per_line, job_id)

        check_cancellation(job_id)
        update_job(job_id, progress=75, step="creating_voice")
        generate_voice_parts(transcript_json, voice_parts_dir, job.tts_voice, job_id)

        check_cancellation(job_id)
        update_job(job_id, progress=85, step="building_audio_timeline")
        build_audio_timeline(
            transcript_json,
            voice_parts_dir,
            video_input,
            voice_output,
            job_id,
            background_audio_path=original_audio_target,
            original_video_volume=job.original_video_volume,
        )

        check_cancellation(job_id)
        update_job(job_id, progress=95, step="rendering")
        render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job.crop, job_id)

        update_job(job_id, status="done", progress=100, step="done")
        log_to_job(job_id, "Pipeline run finished successfully.")

    except Exception as exc:
        error_msg = str(exc)
        if is_cancelled(job_id) or error_msg == "Job cancelled by user.":
            update_job(job_id, status="cancelled", error=None, step="cancelled")
            log_to_job(job_id, "Job cancelled by user.")
            return
        stack_trace = traceback.format_exc()
        log_to_job(job_id, f"Execution failed: {error_msg}\n{stack_trace}")
        update_job(job_id, status="failed", error=error_msg, step="failed")
    finally:
        clean_job(job_id)
