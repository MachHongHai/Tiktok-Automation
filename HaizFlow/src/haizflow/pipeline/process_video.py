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
from haizflow.pipeline.process_registry import check_cancellation, clean_video, is_cancelled, is_paused, start_video
from haizflow.pipeline.render import render_video
from haizflow.pipeline.subtitle import generate_srt
from haizflow.pipeline.transcribe import TIMING_SOURCE, transcribe
from haizflow.pipeline.tts import generate_voice_parts
from haizflow.services.video_store import get_video, log_to_video, update_video
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


def _checkpoint_valid(video, name, signature, outputs):
    # Checkpoints are exclusively a pause/resume optimization. A normal start
    # or explicit restart must run every stage again, even if old files remain.
    return (
        bool(video.resume_step)
        and video.checkpoints.get(name) == signature
        and all(os.path.exists(path) and os.path.getsize(path) > 0 for path in outputs)
    )


def _recovery_checkpoint_valid(video, name, signature, outputs):
    """Reuse durable artifacts only while recovering from a lost GPU.

    This is deliberately independent from pause/resume: Restart must still
    discard every generated artifact and run from the input video.
    """
    return (
        bool(getattr(video, "runtime_recovery_step", ""))
        and video.checkpoints.get(name) == signature
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


def _recover_gpu_to_cpu(video_id: str, stage: str, error: Exception) -> bool:
    """Move one interrupted video to CPU at a durable stage boundary.

    The interrupted stage is restarted, while completed checkpoints remain
    available only to this recovery run. A second automatic retry is refused
    so an unstable driver cannot leave a project in an endless loop.
    """
    video = get_video(video_id)
    if not video or video.gpu_recovery_attempted or not _is_gpu_runtime_failure(error):
        return False

    detail = f"GPU unavailable during {stage}. Switching this project to CPU and retrying that stage."
    update_video(
        video_id,
        status="processing",
        step="recovering_device",
        step_detail=detail,
        runtime_recovery_step=stage,
        gpu_recovery_attempted=True,
        error=None,
    )
    log_to_video(video_id, detail)
    log_to_video(video_id, f"GPU recovery reason: {error}")
    try:
        from haizflow.pipeline.transcribe import release_warm_whisperx_model

        cpu_probe = probe_runtime("cpu")
        if not cpu_probe.ok:
            log_to_video(video_id, f"CPU fallback runtime is unavailable: {cpu_probe.message}")
            return False
        shutdown_hymt2_worker()
        release_warm_whisperx_model()
        configure_processing_device("cpu")
        log_to_video(video_id, "Released GPU models. CPU runtime is ready to resume from the last completed stage.")
        return True
    except Exception as recovery_error:
        log_to_video(video_id, f"Could not prepare CPU fallback: {recovery_error}")
        return False


def _mark_checkpoint(video, name, signature):
    video.checkpoints[name] = signature
    update_video(video.video_id, checkpoints=video.checkpoints)


def _resolve_audio_mix(video, fallback_audio_path: str) -> tuple[str, int]:
    """Return the mutually exclusive background source and its effective volume."""
    if not video.enable_audio_separation:
        return fallback_audio_path, video.original_video_volume
    separated_background = video.files.get("background_audio") or ""
    if separated_background and os.path.exists(separated_background) and os.path.getsize(separated_background) > 0:
        return separated_background, 100
    return "", 100


def _prepare_audio_mix(video, reporter, video_dir: str, fallback_audio_path: str) -> tuple[str, int]:
    background_audio_path, background_volume = _resolve_audio_mix(video, fallback_audio_path)
    if background_audio_path:
        return background_audio_path, background_volume

    check_cancellation(video.video_id)
    _ensure_gpu_available("audio separation")
    if not os.path.exists(fallback_audio_path):
        reporter.update(12, "extracting_audio", "Restoring source audio")
        extract_audio(video.files["video_input"], fallback_audio_path, video.video_id)
    reporter.update(14, "separating_audio", "Restoring separated background audio")
    separation_dir = os.path.join(video_dir, "temp", "separation")
    vocals_path, background_audio_path = separate_audio(
        fallback_audio_path,
        separation_dir,
        video.video_id,
    )
    files = dict(video.files)
    files["speech_audio"] = vocals_path
    files["background_audio"] = background_audio_path
    video.files = files
    update_video(video.video_id, files=files)
    log_to_video(video.video_id, "Separated background audio restored for the final mix.")
    return background_audio_path, 100


class ProgressReporter:
    """Persist real stage details and item progress for the desktop UI."""

    def __init__(self, video_id: str):
        self.video_id = video_id
        self.started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.started_monotonic = time.monotonic()

    def update(self, progress: int, step: str, detail: str, current: int = 0, total: int = 0):
        progress = max(0, min(99, int(progress)))
        elapsed = time.monotonic() - self.started_monotonic
        eta = None
        if progress >= 5:
            eta = max(0, round(elapsed * (100 - progress) / progress))
        update_video(
            self.video_id,
            status="processing",
            progress=progress,
            step=step,
            step_detail=detail,
            current_item=max(0, current),
            total_items=max(0, total),
            started_at=self.started_at,
            estimated_remaining_seconds=eta,
        )


def _finish_recovered_translation(video, reporter, video_dir, temp_audio_wav, source_segments_json, transcript_json, translation_signature):
    """Continue from a durable translation or post-translation artifact."""
    recovery_step = getattr(video, "runtime_recovery_step", "")
    late_stages = {"creating_subtitle", "creating_voice", "building_audio_timeline", "rendering"}
    if recovery_step in late_stages and os.path.exists(transcript_json):
        log_to_video(video.video_id, f"CPU recovery: keeping translated subtitles and retrying from {recovery_step}.")
        _finish_after_translation(video, reporter, video_dir, temp_audio_wav)
        return True
    if recovery_step != "translating" or not os.path.exists(source_segments_json):
        return False
    if not _timing_file_is_current(source_segments_json):
        log_to_video(video.video_id, "CPU recovery discarded legacy source timestamps and will transcribe again.")
        return False

    log_to_video(video.video_id, "CPU recovery: keeping the transcript and retrying HY-MT2 translation.")
    reporter.update(50, "translating", "Retrying translation on CPU")

    def report_translation_progress(current, total, detail):
        progress = 50 + round(12 * current / total) if total else 50
        reporter.update(progress, "translating", detail, current, total)

    translate_segments(
        source_segments_json,
        transcript_json,
        video.video_id,
        video.target_language,
        source_language="en",
        provider="hymt2",
        progress_callback=report_translation_progress,
    )
    _mark_checkpoint(video, "translation", translation_signature)
    if video.mode == "review" and not video.review_approved:
        update_video(
            video.video_id,
            status="awaiting_review",
            progress=62,
            step="review_translation",
            step_detail="Translation ready for review",
            runtime_recovery_step="",
        )
        return True
    _finish_after_translation(video, reporter, video_dir, temp_audio_wav)
    return True


def process_video_sync(video_id: str, _reporter: ProgressReporter | None = None):
    """Run the full-auto desktop dubbing pipeline."""
    try:
        start_video(video_id)
        # A recovery re-enters this function with the existing reporter so
        # elapsed processing time remains the total time for the video.
        reporter = _reporter or ProgressReporter(video_id)
        video = get_video(video_id)
        if not video:
            return
        if video.mode not in {"A", "review"}:
            raise ValueError(f"Unsupported workflow: {video.mode}")

        if video.translator_provider != "hymt2":
            log_to_video(video_id, "Migrated legacy translation setting to HY-MT2.")
            video = update_video(video_id, translator_provider="hymt2") or video
        reporter.update(3, "starting", "Preparing video")
        log_to_video(video_id, "Processing started | Mode: Full Auto | Translator: HY-MT2")

        video_input = video.files["video_input"]
        final_video = video.files["final_video"]
        srt_output = video.files["srt_output"]
        voice_output = video.files["voice_output"]
        transcript_json = video.files["transcript_json"]

        video_dir = os.path.dirname(os.path.dirname(video_input))
        voice_parts_dir = os.path.join(video_dir, "temp", "voice_parts")
        temp_audio_wav = os.path.join(video_dir, "temp", "audio.wav")
        source_segments_json = os.path.join(video_dir, "temp", "source_segments.json")
        translation_signature = _signature(
            _file_state(video_input), TIMING_SOURCE, "hymt2-tencent-structured-context-v17",
            video.target_language, video.enable_audio_separation, "hymt2", HYMT2_MODEL_REVISION
        )

        if _checkpoint_valid(video, "translation", translation_signature, [transcript_json]):
            log_to_video(video_id, "Checkpoint hit: reusing translated segments; skipping audio extraction, transcription and translation.")
            if video.mode == "review" and not video.review_approved:
                update_video(video_id, status="awaiting_review", progress=62, step="review_translation", step_detail="Translation ready for review")
                return
            _finish_after_translation(video, reporter, video_dir, temp_audio_wav)
            return

        if video.mode == "review" and video.review_approved:
            _finish_after_translation(video, reporter, video_dir, temp_audio_wav)
            return

        if video.resume_step and os.path.exists(transcript_json):
            if _timing_file_is_current(transcript_json):
                log_to_video(video_id, f"Resuming from translated segments after paused step '{video.resume_step}'.")
                _finish_after_translation(video, reporter, video_dir, temp_audio_wav)
                return
            log_to_video(video_id, "Resume discarded legacy translated timestamps and will transcribe again.")

        if _finish_recovered_translation(
            video,
            reporter,
            video_dir,
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
            log_to_video(video_id, "Preparing HY-MT2 before WhisperX to avoid peak memory usage.")

            def report_model_warmup(detail):
                log_to_video(video_id, detail)
                reporter.update(4, "loading_models", detail)

            warm_hymt2_worker(report_model_warmup)

        check_cancellation(video_id)
        reporter.update(5, "extracting_audio", "Extracting source audio")
        extract_audio(video_input, temp_audio_wav, video_id)
        reporter.update(12, "extracting_audio", "Source audio ready")

        transcribe_audio_target = temp_audio_wav
        original_audio_target = temp_audio_wav
        if video.enable_audio_separation:
            check_cancellation(video_id)
            _ensure_gpu_available("audio separation")
            reporter.update(14, "separating_audio", "Separating speech from background audio")
            separation_dir = os.path.join(video_dir, "temp", "separation")
            vocals_path, no_vocals_path = separate_audio(temp_audio_wav, separation_dir, video_id)
            transcribe_audio_target = vocals_path
            original_audio_target = no_vocals_path
            files = dict(video.files)
            files["speech_audio"] = vocals_path
            files["background_audio"] = no_vocals_path
            video.files = files
            update_video(video_id, files=files)
            log_to_video(video_id, "Separated mode selected. The no-vocals track will be used as the final background audio.")
            reporter.update(22, "separating_audio", "Speech track ready")
        else:
            log_to_video(video_id, "Audio separation disabled. Transcribing from original audio.")

        check_cancellation(video_id)
        _ensure_gpu_available("speech recognition")
        reporter.update(24, "transcribing", "Preparing speech recognition")
        _segments, detected_language = transcribe(
            transcribe_audio_target,
            source_segments_json,
            video.source_language,
            video_id,
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
            log_to_video(video_id, "Released the warmed WhisperX model before translation to conserve processing memory.")

        check_cancellation(video_id)
        _ensure_gpu_available("translation")
        reporter.update(50, "translating", "Starting HY-MT2 translation")
        def report_translation_progress(current, total, detail):
            progress = 50 + round(12 * current / total) if total else 50
            reporter.update(progress, "translating", detail, current, total)

        translate_segments(
            source_segments_json,
            transcript_json,
            video_id,
            video.target_language,
            source_language=detected_language or "en",
            provider="hymt2",
            progress_callback=report_translation_progress,
        )
        _mark_checkpoint(video, "translation", translation_signature)

        if video.mode == "review" and not video.review_approved:
            update_video(video_id, status="awaiting_review", progress=62, step="review_translation", step_detail="Translation ready for review")
            log_to_video(video_id, "Translation review is ready. Edit the translated segments, then continue the video.")
            return

        _finish_after_translation(video, reporter, video_dir, original_audio_target)

    except Exception as exc:
        error_msg = str(exc)
        if is_cancelled(video_id) or error_msg == "Video cancelled by user.":
            if is_paused(video_id):
                paused_video = get_video(video_id)
                update_video(
                    video_id,
                    status="paused",
                    error=None,
                    step="paused",
                    resume_step=(paused_video.resume_step if paused_video else ""),
                    step_detail=f"Paused during {(paused_video.resume_step if paused_video else '') or 'processing'}",
                )
                log_to_video(video_id, "Video paused by user. Resume from Projects to run it again.")
                return
            update_video(video_id, status="cancelled", error=None, step="cancelled")
            log_to_video(video_id, "Video cancelled by user.")
            return
        failed_video = get_video(video_id)
        failed_stage = (failed_video.step if failed_video else "processing") or "processing"
        if _recover_gpu_to_cpu(video_id, failed_stage, exc):
            log_to_video(video_id, "Restarting the interrupted pipeline stage on CPU.")
            return process_video_sync(video_id, _reporter=reporter)
        stack_trace = traceback.format_exc()
        log_to_video(video_id, f"Execution failed: {error_msg}\n{stack_trace}")
        update_video(video_id, status="failed", error=error_msg, step="failed")
    finally:
        clean_video(video_id)


def _finish_after_translation(video, reporter, video_dir, original_audio_target):
        video_id = video.video_id
        video_input = video.files["video_input"]
        final_video = video.files["final_video"]
        srt_output = video.files["srt_output"]
        voice_output = video.files["voice_output"]
        transcript_json = video.files["transcript_json"]
        voice_parts_dir = os.path.join(video_dir, "temp", "voice_parts")
        transcript_state = _file_state(transcript_json)
        subtitle_signature = _signature(transcript_state, video.subtitle_style.max_chars_per_line)
        check_cancellation(video_id)
        if _checkpoint_valid(video, "subtitles", subtitle_signature, [srt_output]) or _recovery_checkpoint_valid(video, "subtitles", subtitle_signature, [srt_output]):
            reporter.update(64, "creating_subtitle", "Reusing subtitles checkpoint")
        else:
            reporter.update(63, "creating_subtitle", "Formatting timed subtitles")
            generate_srt(transcript_json, srt_output, video.subtitle_style.max_chars_per_line, video_id)
            _mark_checkpoint(video, "subtitles", subtitle_signature)

        check_cancellation(video_id)
        voice_signature = _signature(transcript_state, video.tts_voice)
        with open(transcript_json, "r", encoding="utf-8") as transcript_file:
            expected_parts = len(json.load(transcript_file))
        voice_outputs = [os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3") for index in range(1, expected_parts + 1)]
        if _checkpoint_valid(video, "voice", voice_signature, voice_outputs) or _recovery_checkpoint_valid(video, "voice", voice_signature, voice_outputs):
            reporter.update(82, "creating_voice", "Reusing generated voices", expected_parts, expected_parts)
        else:
            reporter.update(65, "creating_voice", "Starting voice synthesis")
            def report_voice_progress(current, total):
                detail = f"Verified voice audio {current} of {total}"
                reporter.update(65 + round(17 * current / max(1, total)), "creating_voice", detail, current, total)

            generate_voice_parts(
                transcript_json, voice_parts_dir, video.tts_voice, video_id,
                progress_callback=report_voice_progress,
            )
            _mark_checkpoint(video, "voice", voice_signature)

        check_cancellation(video_id)
        mix_audio_path, mix_audio_volume = _prepare_audio_mix(
            video,
            reporter,
            video_dir,
            original_audio_target,
        )
        timeline_signature = _signature(
            voice_signature,
            _file_state(video_input),
            _file_state(mix_audio_path),
            video.enable_audio_separation,
            mix_audio_volume,
            "exclusive-audio-source-v3-final-tail-margin",
        )
        if _checkpoint_valid(video, "timeline", timeline_signature, [voice_output]) or _recovery_checkpoint_valid(video, "timeline", timeline_signature, [voice_output]):
            reporter.update(87, "building_audio_timeline", "Reusing mixed audio checkpoint")
        else:
            reporter.update(83, "building_audio_timeline", "Fitting voices to the video timeline")
            build_audio_timeline(
                transcript_json,
                voice_parts_dir,
                video_input,
                voice_output,
                video_id,
                background_audio_path=mix_audio_path,
                original_video_volume=mix_audio_volume,
            )
            _mark_checkpoint(video, "timeline", timeline_signature)

        check_cancellation(video_id)
        style_data = video.subtitle_style.model_dump() if hasattr(video.subtitle_style, "model_dump") else video.subtitle_style.dict()
        crop_data = video.crop.model_dump() if hasattr(video.crop, "model_dump") else video.crop.dict()
        render_signature = _signature(timeline_signature, subtitle_signature, video.output_format, style_data, crop_data)
        if _checkpoint_valid(video, "render", render_signature, [final_video]) or _recovery_checkpoint_valid(video, "render", render_signature, [final_video]):
            reporter.update(99, "rendering", "Reusing rendered video checkpoint")
        else:
            _ensure_gpu_available("final video render")
            reporter.update(88, "rendering", "Rendering final video")
            render_video(video_input, voice_output, srt_output, final_video, video.output_format, video.subtitle_style, video.crop, video_id)
            _mark_checkpoint(video, "render", render_signature)

        update_video(
            video_id,
            status="done",
            progress=100,
            step="done",
            step_detail="Final video ready",
            estimated_remaining_seconds=0,
            runtime_recovery_step="",
        )
        log_to_video(video_id, "Pipeline run finished successfully.")
