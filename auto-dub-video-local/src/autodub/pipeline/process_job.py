import os
import hashlib
import json
import time
import traceback
from datetime import datetime, timezone

from autodub.pipeline.audio_separation import separate_audio
from autodub.pipeline.audio_timeline import build_audio_timeline
from autodub.pipeline.extract_audio import extract_audio
from autodub.pipeline.job_manager import check_cancellation, clean_job, is_cancelled, is_paused, start_job
from autodub.pipeline.render import render_video
from autodub.pipeline.subtitle import generate_srt
from autodub.pipeline.transcribe import transcribe
from autodub.pipeline.tts import generate_voice_parts
from autodub.services.job_store import get_job, log_to_job, update_job
from autodub.services.translation import translate_segments


def _signature(*values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _file_state(path):
    if not os.path.exists(path):
        return None
    stat = os.stat(path)
    return (os.path.abspath(path), stat.st_size, stat.st_mtime_ns)


def _checkpoint_valid(job, name, signature, outputs):
    return job.checkpoints.get(name) == signature and all(os.path.exists(path) and os.path.getsize(path) > 0 for path in outputs)


def _mark_checkpoint(job, name, signature):
    job.checkpoints[name] = signature
    update_job(job.job_id, checkpoints=job.checkpoints)


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
        if job.mode not in {"A", "review"}:
            raise ValueError(f"Unsupported workflow: {job.mode}")

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
        translation_signature = _signature(
            _file_state(video_input), "auto-per-subtitle-v2", "hymt2-multilingual-context-greedy-v6",
            job.target_language, job.enable_audio_separation, "hymt2"
        )

        if _checkpoint_valid(job, "translation", translation_signature, [transcript_json]):
            log_to_job(job_id, "Checkpoint hit: reusing translated segments; skipping audio extraction, transcription and translation.")
            if job.mode == "review" and not job.review_approved:
                update_job(job_id, status="awaiting_review", progress=62, step="review_translation", step_detail="Translation ready for review")
                return
            _finish_after_translation(job, reporter, job_dir, temp_audio_wav)
            return

        if job.mode == "review" and job.review_approved:
            _finish_after_translation(job, reporter, job_dir, temp_audio_wav)
            return

        if job.resume_step and os.path.exists(transcript_json):
            log_to_job(job_id, f"Resuming from translated segments after paused step '{job.resume_step}'.")
            _finish_after_translation(job, reporter, job_dir, temp_audio_wav)
            return

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
        def report_translation_progress(current, total, detail):
            progress = 50 + round(12 * current / total) if total else 50
            reporter.update(progress, "translating", detail, current, total)

        translate_segments(
            source_segments_json,
            transcript_json,
            job_id,
            job.target_language,
            source_language=detected_language or "en",
            provider="hymt2",
            progress_callback=report_translation_progress,
        )
        _mark_checkpoint(job, "translation", translation_signature)

        if job.mode == "review" and not job.review_approved:
            update_job(job_id, status="awaiting_review", progress=62, step="review_translation", step_detail="Translation ready for review")
            log_to_job(job_id, "Translation review is ready. Edit the translated segments, then continue the job.")
            return

        _finish_after_translation(job, reporter, job_dir, temp_audio_wav)

    except Exception as exc:
        error_msg = str(exc)
        if is_cancelled(job_id) or error_msg == "Job cancelled by user.":
            if is_paused(job_id):
                paused_job = get_job(job_id)
                update_job(
                    job_id,
                    status="paused",
                    error=None,
                    step="paused",
                    resume_step=(paused_job.resume_step if paused_job else ""),
                    step_detail=f"Paused during {(paused_job.resume_step if paused_job else '') or 'processing'}",
                )
                log_to_job(job_id, "Job paused by user. Resume from Projects to run it again.")
                return
            update_job(job_id, status="cancelled", error=None, step="cancelled")
            log_to_job(job_id, "Job cancelled by user.")
            return
        stack_trace = traceback.format_exc()
        log_to_job(job_id, f"Execution failed: {error_msg}\n{stack_trace}")
        update_job(job_id, status="failed", error=error_msg, step="failed")
    finally:
        clean_job(job_id)


def _finish_after_translation(job, reporter, job_dir, original_audio_target):
        job_id = job.job_id
        video_input = job.files["video_input"]
        final_video = job.files["final_video"]
        srt_output = job.files["srt_output"]
        voice_output = job.files["voice_output"]
        transcript_json = job.files["transcript_json"]
        voice_parts_dir = os.path.join(job_dir, "temp", "voice_parts")
        transcript_state = _file_state(transcript_json)
        subtitle_signature = _signature(transcript_state, job.subtitle_style.max_chars_per_line)
        check_cancellation(job_id)
        if _checkpoint_valid(job, "subtitles", subtitle_signature, [srt_output]):
            reporter.update(64, "creating_subtitle", "Reusing subtitles checkpoint")
        else:
            reporter.update(63, "creating_subtitle", "Formatting timed subtitles")
            generate_srt(transcript_json, srt_output, job.subtitle_style.max_chars_per_line, job_id)
            _mark_checkpoint(job, "subtitles", subtitle_signature)

        check_cancellation(job_id)
        voice_signature = _signature(transcript_state, job.tts_voice)
        with open(transcript_json, "r", encoding="utf-8") as transcript_file:
            expected_parts = len(json.load(transcript_file))
        voice_outputs = [os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3") for index in range(1, expected_parts + 1)]
        if _checkpoint_valid(job, "voice", voice_signature, voice_outputs):
            reporter.update(82, "creating_voice", "Reusing generated voices", expected_parts, expected_parts)
        else:
            reporter.update(65, "creating_voice", "Starting voice synthesis")
            def report_voice_progress(current, total):
                detail = f"Creating voice {current} of {total}"
                reporter.update(65 + round(17 * current / max(1, total)), "creating_voice", detail, current, total)
                log_to_job(job_id, detail)

            generate_voice_parts(
                transcript_json, voice_parts_dir, job.tts_voice, job_id,
                progress_callback=report_voice_progress,
            )
            _mark_checkpoint(job, "voice", voice_signature)

        check_cancellation(job_id)
        timeline_signature = _signature(voice_signature, _file_state(video_input), job.original_video_volume)
        if _checkpoint_valid(job, "timeline", timeline_signature, [voice_output]):
            reporter.update(87, "building_audio_timeline", "Reusing mixed audio checkpoint")
        else:
            reporter.update(83, "building_audio_timeline", "Fitting voices to the video timeline")
            build_audio_timeline(transcript_json, voice_parts_dir, video_input, voice_output, job_id, background_audio_path=original_audio_target, original_video_volume=job.original_video_volume)
            _mark_checkpoint(job, "timeline", timeline_signature)

        check_cancellation(job_id)
        style_data = job.subtitle_style.model_dump() if hasattr(job.subtitle_style, "model_dump") else job.subtitle_style.dict()
        crop_data = job.crop.model_dump() if hasattr(job.crop, "model_dump") else job.crop.dict()
        render_signature = _signature(timeline_signature, subtitle_signature, job.output_format, style_data, crop_data)
        if _checkpoint_valid(job, "render", render_signature, [final_video]):
            reporter.update(99, "rendering", "Reusing rendered video checkpoint")
        else:
            reporter.update(88, "rendering", "Rendering final video")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job.crop, job_id)
            _mark_checkpoint(job, "render", render_signature)

        update_job(job_id, status="done", progress=100, step="done", step_detail="Final video ready", estimated_remaining_seconds=0)
        log_to_job(job_id, "Pipeline run finished successfully.")
