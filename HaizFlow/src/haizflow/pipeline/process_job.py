import os
import hashlib
import json
import time
import traceback
from datetime import datetime, timezone

from haizflow.config import HYMT2_MODEL_REVISION
from haizflow.core.hardware import (
    configure_processing_device,
    detect_hardware_capabilities,
    runtime_profile,
)
from haizflow.core.runtime_probe import probe_runtime
from haizflow.pipeline.audio_separation import separate_audio
from haizflow.pipeline.audio_timeline import build_audio_timeline
from haizflow.pipeline.extract_audio import extract_audio
from haizflow.pipeline.job_manager import check_cancellation, clean_job, is_cancelled, is_paused, start_job
from haizflow.pipeline.render import render_video
from haizflow.pipeline.subtitle import generate_srt
from haizflow.pipeline.transcribe import TIMING_SOURCE, transcribe
from haizflow.pipeline.tts import generate_voice_parts
from haizflow.services.job_store import get_job, log_to_job, update_job
from haizflow.services.translation import (
    is_hymt2_worker_warm,
    shutdown_hymt2_worker,
    translate_segments,
    warm_hymt2_worker,
)


def _signature(*values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _file_state(path):
    if not os.path.exists(path):
        return None
    stat = os.stat(path)
    return (os.path.abspath(path), stat.st_size, stat.st_mtime_ns)


def _timing_file_is_current(path):
    try:
        with open(path, "r", encoding="utf-8") as timing_file:
            segments = json.load(timing_file)
        return bool(segments) and all(
            isinstance(segment, dict) and segment.get("timing_source") == TIMING_SOURCE
            for segment in segments
        )
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _checkpoint_valid(job, name, signature, outputs):
    # Checkpoints are exclusively a pause/resume optimization. A normal start
    # or explicit restart must run every stage again, even if old files remain.
    return (
        bool(job.resume_step)
        and job.checkpoints.get(name) == signature
        and all(os.path.exists(path) and os.path.getsize(path) > 0 for path in outputs)
    )


def _recovery_checkpoint_valid(job, name, signature, outputs):
    """Reuse durable artifacts only while recovering from a lost GPU.

    This is deliberately independent from pause/resume: Restart must still
    discard every generated artifact and run from the input video.
    """
    return (
        bool(getattr(job, "runtime_recovery_step", ""))
        and job.checkpoints.get(name) == signature
        and all(os.path.exists(path) and os.path.getsize(path) > 0 for path in outputs)
    )


class GpuRuntimeUnavailable(RuntimeError):
    """Raised at a safe pipeline boundary when the active GPU disappears."""


_GPU_FAILURE_MARKERS = (
    "cuda", "cudnn", "cublas", "nvidia", "gpu", "device-side", "driver",
)

_NON_RECOVERABLE_RUNTIME_MARKERS = (
    "0xc0000005",
    "3221225477",
    "native torch crash",
    "native windows crash",
    "paging file is too small",
    "os error 1455",
)


def _ensure_gpu_available(stage: str) -> None:
    """Do not start a new GPU stage after power/device availability changed."""
    profile = runtime_profile()
    if not profile.cuda_available:
        return
    capabilities = detect_hardware_capabilities()
    if not capabilities.cuda_available or capabilities.ac_powered is False:
        reason = "the NVIDIA GPU is no longer detected" if not capabilities.cuda_available else "AC power was disconnected"
        raise GpuRuntimeUnavailable(f"GPU became unavailable before {stage}: {reason}.")


def _is_gpu_runtime_failure(error: Exception) -> bool:
    if isinstance(error, GpuRuntimeUnavailable):
        return True
    if not runtime_profile().cuda_available:
        return False
    message = str(error).lower()
    # Memory-commit failures and native access violations need investigation.
    # Treating them as a lost GPU would hide the original defect behind a CPU
    # retry and make the failing runtime impossible to diagnose.
    if any(marker in message for marker in _NON_RECOVERABLE_RUNTIME_MARKERS):
        return False
    return any(marker in message for marker in _GPU_FAILURE_MARKERS)


def _recover_gpu_to_cpu(job_id: str, stage: str, error: Exception) -> bool:
    """Move one interrupted job to CPU at a durable stage boundary.

    The interrupted stage is restarted, while completed checkpoints remain
    available only to this recovery run. A second automatic retry is refused
    so an unstable driver cannot leave a project in an endless loop.
    """
    job = get_job(job_id)
    if not job or job.gpu_recovery_attempted or not _is_gpu_runtime_failure(error):
        return False

    detail = f"GPU unavailable during {stage}. Switching this project to CPU and retrying that stage."
    update_job(
        job_id,
        status="processing",
        step="recovering_device",
        step_detail=detail,
        runtime_recovery_step=stage,
        gpu_recovery_attempted=True,
        error=None,
    )
    log_to_job(job_id, detail)
    log_to_job(job_id, f"GPU recovery reason: {error}")
    try:
        from haizflow.pipeline.transcribe import release_warm_whisperx_model

        cpu_probe = probe_runtime("cpu")
        if not cpu_probe.ok:
            log_to_job(job_id, f"CPU fallback runtime is unavailable: {cpu_probe.message}")
            return False
        shutdown_hymt2_worker()
        release_warm_whisperx_model()
        configure_processing_device("cpu")
        log_to_job(job_id, "Released GPU models. CPU runtime is ready to resume from the last completed stage.")
        return True
    except Exception as recovery_error:
        log_to_job(job_id, f"Could not prepare CPU fallback: {recovery_error}")
        return False


def _mark_checkpoint(job, name, signature):
    job.checkpoints[name] = signature
    update_job(job.job_id, checkpoints=job.checkpoints)


def _resolve_audio_mix(job, fallback_audio_path: str) -> tuple[str, int]:
    """Return the mutually exclusive background source and its effective volume."""
    if not job.enable_audio_separation:
        return fallback_audio_path, job.original_video_volume
    separated_background = job.files.get("background_audio") or ""
    if separated_background and os.path.exists(separated_background) and os.path.getsize(separated_background) > 0:
        return separated_background, 100
    return "", 100


def _prepare_audio_mix(job, reporter, job_dir: str, fallback_audio_path: str) -> tuple[str, int]:
    background_audio_path, background_volume = _resolve_audio_mix(job, fallback_audio_path)
    if background_audio_path:
        return background_audio_path, background_volume

    check_cancellation(job.job_id)
    _ensure_gpu_available("audio separation")
    if not os.path.exists(fallback_audio_path):
        reporter.update(12, "extracting_audio", "Restoring source audio")
        extract_audio(job.files["video_input"], fallback_audio_path, job.job_id)
    reporter.update(14, "separating_audio", "Restoring separated background audio")
    separation_dir = os.path.join(job_dir, "temp", "separation")
    vocals_path, background_audio_path = separate_audio(
        fallback_audio_path,
        separation_dir,
        job.job_id,
    )
    files = dict(job.files)
    files["speech_audio"] = vocals_path
    files["background_audio"] = background_audio_path
    job.files = files
    update_job(job.job_id, files=files)
    log_to_job(job.job_id, "Separated background audio restored for the final mix.")
    return background_audio_path, 100


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


def _finish_recovered_translation(job, reporter, job_dir, temp_audio_wav, source_segments_json, transcript_json, translation_signature):
    """Continue from a durable translation or post-translation artifact."""
    recovery_step = getattr(job, "runtime_recovery_step", "")
    late_stages = {"creating_subtitle", "creating_voice", "building_audio_timeline", "rendering"}
    if recovery_step in late_stages and os.path.exists(transcript_json):
        log_to_job(job.job_id, f"CPU recovery: keeping translated subtitles and retrying from {recovery_step}.")
        _finish_after_translation(job, reporter, job_dir, temp_audio_wav)
        return True
    if recovery_step != "translating" or not os.path.exists(source_segments_json):
        return False
    if not _timing_file_is_current(source_segments_json):
        log_to_job(job.job_id, "CPU recovery discarded legacy source timestamps and will transcribe again.")
        return False

    log_to_job(job.job_id, "CPU recovery: keeping the transcript and retrying HY-MT2 translation.")
    reporter.update(50, "translating", "Retrying translation on CPU")

    def report_translation_progress(current, total, detail):
        progress = 50 + round(12 * current / total) if total else 50
        reporter.update(progress, "translating", detail, current, total)

    translate_segments(
        source_segments_json,
        transcript_json,
        job.job_id,
        job.target_language,
        source_language="en",
        provider="hymt2",
        progress_callback=report_translation_progress,
    )
    _mark_checkpoint(job, "translation", translation_signature)
    if job.mode == "review" and not job.review_approved:
        update_job(
            job.job_id,
            status="awaiting_review",
            progress=62,
            step="review_translation",
            step_detail="Translation ready for review",
            runtime_recovery_step="",
        )
        return True
    _finish_after_translation(job, reporter, job_dir, temp_audio_wav)
    return True


def process_job_sync(job_id: str, _reporter: ProgressReporter | None = None):
    """Run the full-auto desktop dubbing pipeline."""
    try:
        start_job(job_id)
        # A recovery re-enters this function with the existing reporter so
        # elapsed processing time remains the total time for the video.
        reporter = _reporter or ProgressReporter(job_id)
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
            _file_state(video_input), TIMING_SOURCE, "hymt2-tencent-structured-context-v17",
            job.target_language, job.enable_audio_separation, "hymt2", HYMT2_MODEL_REVISION
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
            if _timing_file_is_current(transcript_json):
                log_to_job(job_id, f"Resuming from translated segments after paused step '{job.resume_step}'.")
                _finish_after_translation(job, reporter, job_dir, temp_audio_wav)
                return
            log_to_job(job_id, "Resume discarded legacy translated timestamps and will transcribe again.")

        if _finish_recovered_translation(
            job,
            reporter,
            job_dir,
            temp_audio_wav,
            source_segments_json,
            transcript_json,
            translation_signature,
        ):
            return

        profile = runtime_profile()
        if profile.warm_hymt2_on_startup and not is_hymt2_worker_warm():
            _ensure_gpu_available("translation model warm-up")
            reporter.update(4, "loading_models", "Preparing HY-MT2 translation model")
            log_to_job(job_id, "Preparing HY-MT2 before WhisperX to avoid peak memory usage.")

            def report_model_warmup(detail):
                log_to_job(job_id, detail)
                reporter.update(4, "loading_models", detail)

            warm_hymt2_worker(report_model_warmup)

        check_cancellation(job_id)
        reporter.update(5, "extracting_audio", "Extracting source audio")
        extract_audio(video_input, temp_audio_wav, job_id)
        reporter.update(12, "extracting_audio", "Source audio ready")

        transcribe_audio_target = temp_audio_wav
        original_audio_target = temp_audio_wav
        if job.enable_audio_separation:
            check_cancellation(job_id)
            _ensure_gpu_available("audio separation")
            reporter.update(14, "separating_audio", "Separating speech from background audio")
            separation_dir = os.path.join(job_dir, "temp", "separation")
            vocals_path, no_vocals_path = separate_audio(temp_audio_wav, separation_dir, job_id)
            transcribe_audio_target = vocals_path
            original_audio_target = no_vocals_path
            files = dict(job.files)
            files["speech_audio"] = vocals_path
            files["background_audio"] = no_vocals_path
            job.files = files
            update_job(job_id, files=files)
            log_to_job(job_id, "Separated mode selected. The no-vocals track will be used as the final background audio.")
            reporter.update(22, "separating_audio", "Speech track ready")
        else:
            log_to_job(job_id, "Audio separation disabled. Transcribing from original audio.")

        check_cancellation(job_id)
        _ensure_gpu_available("speech recognition")
        reporter.update(24, "transcribing", "Preparing speech recognition")
        _segments, detected_language = transcribe(
            transcribe_audio_target,
            source_segments_json,
            job.source_language,
            job_id,
            progress_callback=lambda event, detail: reporter.update(
                {"loading_model": 25, "transcribing": 29, "transcribed": 39,
                 "loading_alignment": 40, "aligning": 41, "segmenting": 42,
                 "detecting_languages": 46, "saved": 48}.get(event, 24),
                "transcribing",
                detail,
            ),
        )

        if profile.key in {"cpu_low_memory", "cpu_minimum", "cuda_low_memory"}:
            from haizflow.pipeline.transcribe import release_warm_whisperx_model

            release_warm_whisperx_model()
            log_to_job(job_id, "Released the warmed WhisperX model before translation to conserve processing memory.")

        check_cancellation(job_id)
        _ensure_gpu_available("translation")
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

        _finish_after_translation(job, reporter, job_dir, original_audio_target)

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
        failed_job = get_job(job_id)
        failed_stage = (failed_job.step if failed_job else "processing") or "processing"
        if _recover_gpu_to_cpu(job_id, failed_stage, exc):
            log_to_job(job_id, "Restarting the interrupted pipeline stage on CPU.")
            return process_job_sync(job_id, _reporter=reporter)
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
        if _checkpoint_valid(job, "subtitles", subtitle_signature, [srt_output]) or _recovery_checkpoint_valid(job, "subtitles", subtitle_signature, [srt_output]):
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
        if _checkpoint_valid(job, "voice", voice_signature, voice_outputs) or _recovery_checkpoint_valid(job, "voice", voice_signature, voice_outputs):
            reporter.update(82, "creating_voice", "Reusing generated voices", expected_parts, expected_parts)
        else:
            reporter.update(65, "creating_voice", "Starting voice synthesis")
            def report_voice_progress(current, total):
                detail = f"Verified voice audio {current} of {total}"
                reporter.update(65 + round(17 * current / max(1, total)), "creating_voice", detail, current, total)

            generate_voice_parts(
                transcript_json, voice_parts_dir, job.tts_voice, job_id,
                progress_callback=report_voice_progress,
            )
            _mark_checkpoint(job, "voice", voice_signature)

        check_cancellation(job_id)
        mix_audio_path, mix_audio_volume = _prepare_audio_mix(
            job,
            reporter,
            job_dir,
            original_audio_target,
        )
        timeline_signature = _signature(
            voice_signature,
            _file_state(video_input),
            _file_state(mix_audio_path),
            job.enable_audio_separation,
            mix_audio_volume,
            "exclusive-audio-source-v3-final-tail-margin",
        )
        if _checkpoint_valid(job, "timeline", timeline_signature, [voice_output]) or _recovery_checkpoint_valid(job, "timeline", timeline_signature, [voice_output]):
            reporter.update(87, "building_audio_timeline", "Reusing mixed audio checkpoint")
        else:
            reporter.update(83, "building_audio_timeline", "Fitting voices to the video timeline")
            build_audio_timeline(
                transcript_json,
                voice_parts_dir,
                video_input,
                voice_output,
                job_id,
                background_audio_path=mix_audio_path,
                original_video_volume=mix_audio_volume,
            )
            _mark_checkpoint(job, "timeline", timeline_signature)

        check_cancellation(job_id)
        style_data = job.subtitle_style.model_dump() if hasattr(job.subtitle_style, "model_dump") else job.subtitle_style.dict()
        crop_data = job.crop.model_dump() if hasattr(job.crop, "model_dump") else job.crop.dict()
        render_signature = _signature(timeline_signature, subtitle_signature, job.output_format, style_data, crop_data)
        if _checkpoint_valid(job, "render", render_signature, [final_video]) or _recovery_checkpoint_valid(job, "render", render_signature, [final_video]):
            reporter.update(99, "rendering", "Reusing rendered video checkpoint")
        else:
            _ensure_gpu_available("final video render")
            reporter.update(88, "rendering", "Rendering final video")
            render_video(video_input, voice_output, srt_output, final_video, job.output_format, job.subtitle_style, job.crop, job_id)
            _mark_checkpoint(job, "render", render_signature)

        update_job(
            job_id,
            status="done",
            progress=100,
            step="done",
            step_detail="Final video ready",
            estimated_remaining_seconds=0,
            runtime_recovery_step="",
        )
        log_to_job(job_id, "Pipeline run finished successfully.")
