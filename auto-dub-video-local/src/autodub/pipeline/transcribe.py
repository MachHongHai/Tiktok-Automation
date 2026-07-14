import gc
import json
import threading

import torch
import whisperx

from autodub.config import WHISPER_MODEL
from autodub.services.job_store import log_to_job


_MODEL_LOCK = threading.Lock()
_WARM_ASR_MODEL = None
_WARM_DEVICE = None
_AUDIO_SAMPLE_RATE = 16000
_SEGMENT_LANGUAGE_CONFIDENCE = 0.55


def warm_whisperx_model():
    """Load the ASR model once in the background so the first job starts promptly."""
    global _WARM_ASR_MODEL, _WARM_DEVICE
    with _MODEL_LOCK:
        if _WARM_ASR_MODEL is not None:
            return True
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _WARM_ASR_MODEL = whisperx.load_model(WHISPER_MODEL, device, compute_type=compute_type)
        _WARM_DEVICE = device
        return True


def release_warm_whisperx_model():
    global _WARM_ASR_MODEL, _WARM_DEVICE
    with _MODEL_LOCK:
        if _WARM_ASR_MODEL is not None:
            del _WARM_ASR_MODEL
        _WARM_ASR_MODEL = None
        _WARM_DEVICE = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _release_cuda(job_id: str, stage: str) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log_to_job(job_id, f"Released WhisperX VRAM after {stage}.")


def _detect_segment_languages(asr_model, audio, segments, fallback_language: str, job_id: str):
    """Detect a language for every sentence-level subtitle segment."""
    fallback_language = fallback_language or "en"
    detected_segments = []
    counts = {}
    audio_duration = len(audio) / _AUDIO_SAMPLE_RATE

    for index, segment in enumerate(segments, start=1):
        start = max(0.0, float(segment.get("start", 0.0)))
        end = min(audio_duration, float(segment.get("end", start)))
        language = fallback_language
        confidence = 0.0

        if end > start:
            # Do not include adjacent subtitle sentences: language ID is based on
            # the exact sentence audio rather than a wider VAD region.
            clip = audio[int(start * _AUDIO_SAMPLE_RATE): int(end * _AUDIO_SAMPLE_RATE)]
            try:
                detected, confidence, _all_probabilities = asr_model.model.detect_language(
                    audio=clip,
                    language_detection_threshold=0.0,
                )
                if detected and confidence >= _SEGMENT_LANGUAGE_CONFIDENCE:
                    language = detected
                else:
                    log_to_job(
                        job_id,
                        f"Subtitle segment {index} language confidence {confidence:.2f} is low; using '{fallback_language}'.",
                    )
            except Exception as exc:
                log_to_job(job_id, f"Subtitle segment {index} language detection failed; using '{fallback_language}': {exc}")

        segment_with_language = dict(segment)
        segment_with_language["language"] = language
        segment_with_language["language_confidence"] = round(float(confidence), 3)
        detected_segments.append(segment_with_language)
        counts[language] = counts.get(language, 0) + 1

    if counts:
        summary = ", ".join(f"{language}={count}" for language, count in sorted(counts.items()))
        log_to_job(job_id, f"Detected languages per subtitle segment: {summary}.")
    return detected_segments


def _language_for_aligned_segment(segment, source_segments, fallback_language: str) -> tuple[str, float]:
    """Carry language ID from Whisper segments into their aligned subtitle segments."""
    start = float(segment.get("start", 0.0))
    end = float(segment.get("end", start))
    midpoint = (start + end) / 2
    best_source = None
    best_overlap = -1.0

    for source in source_segments:
        source_start = float(source.get("start", 0.0))
        source_end = float(source.get("end", source_start))
        overlap = max(0.0, min(end, source_end) - max(start, source_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_source = source
        elif overlap == best_overlap and best_source is not None:
            source_midpoint = (source_start + source_end) / 2
            best_midpoint = (float(best_source.get("start", 0.0)) + float(best_source.get("end", 0.0))) / 2
            if abs(midpoint - source_midpoint) < abs(midpoint - best_midpoint):
                best_source = source

    if not best_source:
        return fallback_language, 0.0
    return best_source.get("language") or fallback_language, float(best_source.get("language_confidence", 0.0))


def _retranscribe_mixed_language_segments(asr_model, audio, segments, primary_language: str, job_id: str):
    """Re-transcribe only detected language switches with the appropriate Whisper tokenizer."""
    primary_language = primary_language or "en"
    retranscribed_segments = []

    for index, segment in enumerate(segments, start=1):
        language = segment.get("language") or primary_language
        confidence = float(segment.get("language_confidence", 0.0))
        start = max(0.0, float(segment.get("start", 0.0)))
        end = min(len(audio) / _AUDIO_SAMPLE_RATE, float(segment.get("end", start)))
        if language == primary_language or confidence < _SEGMENT_LANGUAGE_CONFIDENCE or end <= start:
            retranscribed_segments.append(segment)
            continue

        try:
            log_to_job(job_id, f"Re-transcribing segment {index} with detected language '{language}'.")
            clip = audio[int(start * _AUDIO_SAMPLE_RATE): int(end * _AUDIO_SAMPLE_RATE)]
            local_result = asr_model.transcribe(clip, batch_size=1, language=language)
            local_segments = local_result.get("segments", [])
            if not local_segments:
                retranscribed_segments.append(segment)
                continue
            for local_segment in local_segments:
                retranscribed_segments.append(
                    {
                        **local_segment,
                        "start": round(start + float(local_segment.get("start", 0.0)), 3),
                        "end": round(start + float(local_segment.get("end", 0.0)), 3),
                        "language": language,
                        "language_confidence": confidence,
                    }
                )
        except Exception as exc:
            log_to_job(job_id, f"Could not re-transcribe segment {index} in '{language}'; keeping its original transcript: {exc}")
            retranscribed_segments.append(segment)

    return retranscribed_segments


def _align_segments_by_language(audio, segments, device: str, job_id: str, progress_callback=None):
    """Align each language group with its matching WhisperX alignment model."""
    grouped_segments = {}
    ordered_languages = []
    for segment in segments:
        language = segment.get("language") or "en"
        if language not in grouped_segments:
            grouped_segments[language] = []
            ordered_languages.append(language)
        grouped_segments[language].append(segment)

    aligned_segments = []
    for language in ordered_languages:
        language_segments = grouped_segments[language]
        align_model = None
        try:
            log_to_job(job_id, f"Loading alignment model for language '{language}'.")
            if progress_callback:
                progress_callback("loading_alignment", f"Loading subtitle alignment for {language}")
            align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
            log_to_job(job_id, f"Running forced alignment for {len(language_segments)} {language} segment(s).")
            if progress_callback:
                progress_callback("aligning", f"Aligning {language} subtitles")
            aligned_result = whisperx.align(
                language_segments,
                align_model,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            aligned_segments.extend(aligned_result["segments"])
        except Exception as exc:
            log_to_job(job_id, f"WARNING: Alignment failed or is unsupported for '{language}'. Using raw segments: {exc}")
            aligned_segments.extend(language_segments)
        finally:
            if align_model is not None:
                del align_model
            _release_cuda(job_id, f"{language} alignment")

    aligned_segments.sort(key=lambda segment: float(segment.get("start", 0.0)))
    return aligned_segments


def transcribe(audio_path: str, output_json_path: str, source_language: str, job_id: str, progress_callback=None):
    """Transcribe and align audio while releasing each GPU model as soon as it is no longer needed."""
    log_to_job(job_id, f"Initializing WhisperX with model '{WHISPER_MODEL}'.")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    log_to_job(job_id, f"WhisperX device: {device}, compute type: {compute_type}.")

    asr_model = None
    using_warm_model = False
    audio = None
    try:
        log_to_job(job_id, "Loading WhisperX transcription model.")
        if progress_callback:
            progress_callback("loading_model", "Loading WhisperX speech model")
        with _MODEL_LOCK:
            if _WARM_ASR_MODEL is not None and _WARM_DEVICE == device:
                asr_model = _WARM_ASR_MODEL
                using_warm_model = True
                log_to_job(job_id, "Reusing warmed WhisperX speech model.")
            else:
                asr_model = whisperx.load_model(WHISPER_MODEL, device, compute_type=compute_type)
        audio = whisperx.load_audio(audio_path)
        # Source language is always automatic. Per-segment detection runs after
        # transcription so mixed-language videos are not constrained by the first 30 seconds.
        language = None
        if source_language != "auto":
            log_to_job(job_id, f"Ignoring legacy source language '{source_language}'; using automatic per-segment detection.")
        log_to_job(job_id, "Running transcription with automatic language detection.")
        if progress_callback:
            progress_callback("transcribing", "Transcribing speech")
        result = asr_model.transcribe(audio, batch_size=16, language=language)
        detected_language = result.get("language")
        log_to_job(job_id, f"Transcription completed. Detected language: '{detected_language}'.")
        if progress_callback:
            progress_callback("transcribed", f"Detected {detected_language or 'unknown'} speech")

        # WhisperX alignment emits sentence-level segments. Run this initial pass
        # only to obtain exact sentence boundaries before language identification.
        initial_segments = [
            {
                **segment,
                "language": detected_language or "en",
                "language_confidence": 1.0,
            }
            for segment in result["segments"]
        ]
        sentence_segments = _align_segments_by_language(
            audio,
            initial_segments,
            device,
            job_id,
            progress_callback=progress_callback,
        )
        log_to_job(job_id, f"Prepared {len(sentence_segments)} sentence-level subtitle segments for language identification.")

        source_segments = _detect_segment_languages(
            asr_model,
            audio,
            sentence_segments,
            detected_language or "en",
            job_id,
        )
        source_segments = _retranscribe_mixed_language_segments(
            asr_model,
            audio,
            source_segments,
            detected_language or "en",
            job_id,
        )

        if not using_warm_model:
            del asr_model
            asr_model = None
            _release_cuda(job_id, "transcription")

        aligned_segments = _align_segments_by_language(
            audio,
            source_segments,
            device,
            job_id,
            progress_callback=progress_callback,
        )
        log_to_job(job_id, "Forced alignment completed successfully.")
        if progress_callback:
            progress_callback("aligned", f"Aligned {len(aligned_segments)} segments")

        output_segments = []
        for segment in aligned_segments:
            segment_language, confidence = _language_for_aligned_segment(
                segment,
                source_segments,
                detected_language or "en",
            )
            output_segments.append(
                {
                    "start": round(segment.get("start", 0.0), 3),
                    "end": round(segment.get("end", 0.0), 3),
                    "text": segment.get("text", "").strip(),
                    "language": segment_language,
                    "language_confidence": round(confidence, 3),
                }
            )
        with open(output_json_path, "w", encoding="utf-8") as file:
            json.dump(output_segments, file, ensure_ascii=False, indent=2)

        log_to_job(job_id, f"Saved {len(output_segments)} transcribed segments to: {output_json_path}")
        if progress_callback:
            progress_callback("saved", f"Prepared {len(output_segments)} subtitle segments")
        return output_segments, detected_language
    finally:
        if asr_model is not None and not using_warm_model:
            del asr_model
        if audio is not None:
            del audio
        _release_cuda(job_id, "WhisperX cleanup")
