import os
import time
import traceback
from datetime import datetime, timezone

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


class ProgressReporter:
    """Persist real stage details and item progress for the desktop UI."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.started_monotonic = time.monotonic()

    def update(self, progress: int, step: str, detail: str, current: int = 0, total: int = 0):
        progress = max(0, min(99, int(progress)))
        elapsed = time.monotonic() - self.started_monotonic
        eta = None
        if progress >= 5:
            eta = max(0, round(elapsed * (100 - progress) / progress))
        update_job(
            self.job_id,
            status="processing",
            progress=progress,
            step=step,
            step_detail=detail,
            current_item=max(0, current),
            total_items=max(0, total),
            started_at=self.started_at,
            estimated_remaining_seconds=eta,
        )


def process_job_sync(job_id: str):
    """Run the full-auto desktop dubbing pipeline."""
    try:
        start_job(job_id)
        reporter = ProgressReporter(job_id)
        job = get_job(job_id)
        if not job:
            return
        if job.mode != "A":
            raise ValueError("Only full-auto jobs are supported by the desktop app.")

        if job.translator_provider != "hymt2":
            log_to_job(job_id, "Migrated legacy translation setting to HY-MT2.")
            job = update_job(job_id, translator_provider="hymt2") or job
        reporter.update(3, "starting", "Preparing job")
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
        reporter.update(5, "extracting_audio", "Extracting source audio")
        extract_audio(video_input, temp_audio_wav, job_id)
        reporter.update(12, "extracting_audio", "Source audio ready")

        transcribe_audio_target = temp_audio_wav
        original_audio_target = temp_audio_wav
        if job.enable_audio_separation:
            check_cancellation(job_id)
            reporter.update(14, "separating_audio", "Separating speech from background audio")
            separation_dir = os.path.join(job_dir, "temp", "separation")
            vocals_path, _no_vocals_path = separate_audio(temp_audio_wav, separation_dir, job_id)
            transcribe_audio_target = vocals_path
            reporter.update(22, "separating_audio", "Speech track ready")
        else:
            log_to_job(job_id, "Audio separation disabled. Transcribing from original audio.")

        check_cancellation(job_id)
        reporter.update(24, "transcribing", "Preparing speech recognition")
        _segments, detected_language = transcribe(
            transcribe_audio_target,
            source_segments_json,
            job.source_language,
            job_id,
            progress_callback=lambda event, detail: reporter.update(
                {"loading_model": 25, "transcribing": 29, "transcribed": 39,
                 "loading_alignment": 40, "aligning": 42, "aligned": 46, "saved": 48}.get(event, 24),
                "transcribing",
                detail,
            ),
        )

        check_cancellation(job_id)
        reporter.update(50, "translating", "Starting HY-MT2 translation")
        translate_segments(
            source_segments_json,
            transcript_json,
            job_id,
            job.target_language,
            source_language=detected_language or job.source_language,
            provider="hymt2",
            progress_callback=lambda current, total: reporter.update(
                50 + round(12 * current / max(1, total)),
                "translating",
                f"Translating segment {current} of {total}",
                current,
                total,
            ),
        )

        check_cancellation(job_id)
        reporter.update(63, "creating_subtitle", "Formatting timed subtitles")
        generate_srt(transcript_json, srt_output, job.subtitle_style.max_chars_per_line, job_id)

        check_cancellation(job_id)
        reporter.update(65, "creating_voice", "Starting voice synthesis")
        generate_voice_parts(
            transcript_json,
            voice_parts_dir,
            job.tts_voice,
            job_id,
            progress_callback=lambda current, total: reporter.update(
                65 + round(17 * current / max(1, total)),
                "creating_voice",
                f"Creating voice {current} of {total}",
                current,
                total,
            ),
        )

        check_cancellation(job_id)
        reporter.update(83, "building_audio_timeline", "Fitting voices to the video timeline")
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
        reporter.update(88, "rendering", "Rendering final video")
        render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job.crop, job_id)

        update_job(job_id, status="done", progress=100, step="done", step_detail="Final video ready", estimated_remaining_seconds=0)
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
