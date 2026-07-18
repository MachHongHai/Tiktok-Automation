import gc
import json
import os
import re
import statistics
import threading
from pathlib import Path

import torch
import whisperx

from haizflow.config import HF_HOME, MODELS_DIR, WHISPER_MODEL
from haizflow.core.hardware import runtime_profile
from haizflow.core.model_integrity import ModelIntegrityError, verify_whisper_model
from haizflow.core.paths import bundle_root
from haizflow.services.video_store import log_to_video


_MODEL_LOCK = threading.Lock()
_WARM_ASR_MODEL = None
_WARM_DEVICE = None
_AUDIO_SAMPLE_RATE = 16000
_SEGMENT_LANGUAGE_CONFIDENCE = 0.55
_ALIGNMENT_MIN_COVERAGE_RATIO = 0.55
_ALIGNMENT_MIN_MEDIAN_WORD_SCORE = 0.03
TIMING_SOURCE = "whisperx-validated-sentences-v3"
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_SENTENCE_END_CHARS = frozenset(".!?\u2026\u3002\uff01\uff1f")
_SENTENCE_CLOSERS = frozenset("\"'\u2019\u201d)]}\u3009\u300b\u300d\u300f\u3011")


def _whisper_model_source() -> tuple[str, bool]:
    """Prefer the installer-owned pinned model and otherwise cache on the selected drive."""
    if os.path.isdir(WHISPER_MODEL):
        return os.path.abspath(WHISPER_MODEL), True
    if WHISPER_MODEL != "small":
        return WHISPER_MODEL, False
    candidates = (
        os.path.join(MODELS_DIR, "whisper", "small"),
        str(bundle_root() / "models" / "whisper" / "small"),
    )
    for candidate in candidates:
        if not os.path.isdir(candidate):
            continue
        try:
            return str(verify_whisper_model(Path(candidate))), True
        except ModelIntegrityError as exc:
            raise RuntimeError(f"Installed Whisper model failed integrity verification: {exc}") from exc
    return WHISPER_MODEL, False


def _load_whisper_model(device: str, compute_type: str, threads: int):
    source, local_only = _whisper_model_source()
    return whisperx.load_model(
        source,
        device,
        compute_type=compute_type,
        threads=threads,
        download_root=os.path.join(HF_HOME, "hub"),
        local_files_only=local_only,
    )


def warm_whisperx_model():
    """Load the ASR model once in the background so the first video starts promptly."""
    global _WARM_ASR_MODEL, _WARM_DEVICE
    with _MODEL_LOCK:
        if _WARM_ASR_MODEL is not None:
            return True
        profile = runtime_profile()
        device = "cuda" if profile.cuda_available else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        try:
            model = _load_whisper_model(device, compute_type, profile.cpu_threads)
        except Exception:
            _WARM_ASR_MODEL = None
            _WARM_DEVICE = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise
        _WARM_ASR_MODEL = model
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


def _release_cuda(video_id: str, stage: str) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log_to_video(video_id, f"Released WhisperX VRAM after {stage}.")


def _value(item, name: str, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _merge_transcript_text(left: str, right: str) -> str:
    """Join adjacent model fragments without inserting spaces into CJK text."""
    left = (left or "").strip()
    raw_right = right or ""
    right = raw_right.strip()
    if not left:
        return right
    if not right:
        return left
    if raw_right[:1].isspace():
        return f"{left} {right}"
    if _CJK_RE.search(left[-1:]) and _CJK_RE.match(right[:1]):
        return left + right
    if right[:1] in ",.;:!?%)]}\u3001\u3002\uff0c\uff01\uff1f":
        return left + right
    return f"{left} {right}"


def _detect_segment_languages(asr_model, audio, segments, fallback_language: str, video_id: str):
    """Detect one source language for each immutable sentence timestamp."""
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
            clip = audio[int(start * _AUDIO_SAMPLE_RATE): int(end * _AUDIO_SAMPLE_RATE)]
            try:
                detected, confidence, _all_probabilities = asr_model.model.detect_language(
                    audio=clip,
                    language_detection_threshold=0.0,
                )
                if detected and confidence >= _SEGMENT_LANGUAGE_CONFIDENCE:
                    language = detected
                else:
                    log_to_video(
                        video_id,
                        f"Sentence {index} language confidence {confidence:.2f} is low; using '{fallback_language}'.",
                    )
            except Exception as exc:
                log_to_video(video_id, f"Sentence {index} language detection failed; using '{fallback_language}': {exc}")

        segment_with_language = dict(segment)
        segment_with_language["language"] = language
        segment_with_language["language_confidence"] = round(float(confidence), 3)
        detected_segments.append(segment_with_language)
        counts[language] = counts.get(language, 0) + 1

    if counts:
        summary = ", ".join(f"{language}={count}" for language, count in sorted(counts.items()))
        log_to_video(video_id, f"Detected languages per sentence: {summary}.")
    return detected_segments


def _retranscribe_mixed_language_segments(asr_model, audio, segments, primary_language: str, video_id: str):
    """Correct switched-language text while preserving every original timestamp."""
    primary_language = primary_language or "en"
    corrected_segments = []

    for index, segment in enumerate(segments, start=1):
        language = segment.get("language") or primary_language
        confidence = float(segment.get("language_confidence", 0.0))
        start = max(0.0, float(segment.get("start", 0.0)))
        end = min(len(audio) / _AUDIO_SAMPLE_RATE, float(segment.get("end", start)))
        corrected_segment = dict(segment)
        if language == primary_language or confidence < _SEGMENT_LANGUAGE_CONFIDENCE or end <= start:
            corrected_segments.append(corrected_segment)
            continue

        try:
            log_to_video(video_id, f"Re-transcribing sentence {index} with detected language '{language}'.")
            clip = audio[int(start * _AUDIO_SAMPLE_RATE): int(end * _AUDIO_SAMPLE_RATE)]
            local_result = asr_model.transcribe(clip, batch_size=1, language=language)
            corrected_text = ""
            for local_segment in local_result.get("segments", []):
                corrected_text = _merge_transcript_text(
                    corrected_text,
                    str(_value(local_segment, "text", "") or ""),
                )
            if corrected_text.strip():
                corrected_segment["text"] = corrected_text.strip()
        except Exception as exc:
            log_to_video(video_id, f"Could not re-transcribe sentence {index} in '{language}'; keeping its text: {exc}")
        corrected_segments.append(corrected_segment)

    return corrected_segments


def _language_for_aligned_segment(segment, source_segments, fallback_language: str) -> tuple[str, float]:
    """Carry language metadata to the aligned sentence with the greatest overlap."""
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
            best_midpoint = (
                float(best_source.get("start", 0.0)) + float(best_source.get("end", 0.0))
            ) / 2
            if abs(midpoint - source_midpoint) < abs(midpoint - best_midpoint):
                best_source = source

    if not best_source:
        return fallback_language, 0.0
    return (
        best_source.get("language") or fallback_language,
        float(best_source.get("language_confidence", 0.0)),
    )


def _split_sentence_text(text: str) -> list[str]:
    """Split complete sentences without assuming that the language uses spaces."""
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return []

    sentences = []
    sentence_start = 0
    index = 0
    while index < len(normalized):
        character = normalized[index]
        if character not in _SENTENCE_END_CHARS:
            index += 1
            continue
        if (
            character == "."
            and index > 0
            and index + 1 < len(normalized)
            and normalized[index - 1].isdigit()
            and normalized[index + 1].isdigit()
        ):
            index += 1
            continue

        sentence_end = index + 1
        while sentence_end < len(normalized) and (
            normalized[sentence_end] in _SENTENCE_END_CHARS
            or normalized[sentence_end] in _SENTENCE_CLOSERS
        ):
            sentence_end += 1

        has_boundary = sentence_end >= len(normalized)
        if not has_boundary:
            has_boundary = normalized[sentence_end].isspace() or character in "\u2026\u3002\uff01\uff1f"
        if has_boundary:
            sentence = normalized[sentence_start:sentence_end].strip()
            if sentence:
                sentences.append(sentence)
            while sentence_end < len(normalized) and normalized[sentence_end].isspace():
                sentence_end += 1
            sentence_start = sentence_end
            index = sentence_end
            continue
        index += 1

    remainder = normalized[sentence_start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def _speech_weight(text: str) -> int:
    """Estimate spoken length consistently for spaced and unspaced languages."""
    return max(1, sum(character.isalnum() for character in str(text or "")))


def _split_segment_proportionally(segment: dict) -> list[dict]:
    """Keep Whisper's trusted span while deriving sentence-level fallback timing."""
    sentences = _split_sentence_text(segment.get("text", ""))
    if len(sentences) <= 1:
        return [dict(segment)]

    start = float(segment.get("start", 0.0))
    end = float(segment.get("end", start))
    duration = max(0.0, end - start)
    weights = [_speech_weight(sentence) for sentence in sentences]
    total_weight = sum(weights)
    elapsed_weight = 0
    fallback_segments = []
    for index, (sentence, weight) in enumerate(zip(sentences, weights)):
        sentence_start = start + duration * elapsed_weight / total_weight
        elapsed_weight += weight
        sentence_end = end if index == len(sentences) - 1 else start + duration * elapsed_weight / total_weight
        fallback_segment = dict(segment)
        fallback_segment.update(
            {
                "start": round(sentence_start, 3),
                "end": round(max(sentence_start + 0.001, sentence_end), 3),
                "text": sentence,
            }
        )
        fallback_segment.pop("words", None)
        fallback_segments.append(fallback_segment)
    return fallback_segments


def _alignment_quality(source_segment: dict, aligned_segments: list[dict]) -> tuple[bool, str]:
    """Reject aligners that return legal-looking but physically impossible timing."""
    if not aligned_segments:
        return False, "no aligned sentences"

    source_start = float(source_segment.get("start", 0.0))
    source_end = float(source_segment.get("end", source_start))
    source_duration = source_end - source_start
    aligned_start = min(float(segment.get("start", source_start)) for segment in aligned_segments)
    aligned_end = max(float(segment.get("end", aligned_start)) for segment in aligned_segments)
    aligned_duration = aligned_end - aligned_start
    if source_duration <= 0 or aligned_duration <= 0:
        return False, "non-positive duration"
    if aligned_start < source_start - 0.25 or aligned_end > source_end + 0.25:
        return False, "timestamps escaped the Whisper source span"

    coverage_ratio = aligned_duration / source_duration
    if coverage_ratio < _ALIGNMENT_MIN_COVERAGE_RATIO:
        return False, f"coverage {coverage_ratio:.2f} is below {_ALIGNMENT_MIN_COVERAGE_RATIO:.2f}"

    word_scores = [
        float(word["score"])
        for segment in aligned_segments
        for word in segment.get("words", [])
        if word.get("score") is not None
    ]
    if word_scores:
        median_score = statistics.median(word_scores)
        if median_score < _ALIGNMENT_MIN_MEDIAN_WORD_SCORE:
            return False, (
                f"median word score {median_score:.3f} is below "
                f"{_ALIGNMENT_MIN_MEDIAN_WORD_SCORE:.3f}"
            )
    return True, f"coverage={coverage_ratio:.2f}"


def _align_segments_by_language(audio, segments, device: str, video_id: str, progress_callback=None):
    """Align each source span and preserve it whenever the aligner is unreliable."""
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
            log_to_video(video_id, f"Loading alignment model for language '{language}'.")
            if progress_callback:
                progress_callback("loading_alignment", f"Loading subtitle alignment for {language}")
            align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
            if progress_callback:
                progress_callback("aligning", f"Aligning {language} subtitles")
            for source_index, source_segment in enumerate(language_segments, start=1):
                try:
                    aligned_result = whisperx.align(
                        [source_segment],
                        align_model,
                        metadata,
                        audio,
                        device,
                        return_char_alignments=False,
                    )
                    candidate_segments = aligned_result.get("segments", [])
                    is_valid, quality_detail = _alignment_quality(source_segment, candidate_segments)
                    if is_valid:
                        aligned_segments.extend(candidate_segments)
                        continue
                    log_to_video(
                        video_id,
                        f"WARNING: Rejected '{language}' alignment for source span {source_index} "
                        f"({quality_detail}). Preserving Whisper timing with proportional sentence boundaries.",
                    )
                except Exception as exc:
                    log_to_video(
                        video_id,
                        f"WARNING: Alignment failed for '{language}' source span {source_index}. "
                        f"Preserving Whisper timing: {exc}",
                    )
                aligned_segments.extend(_split_segment_proportionally(source_segment))
        except Exception as exc:
            log_to_video(
                video_id,
                f"WARNING: Alignment model failed or is unsupported for '{language}'. "
                f"Preserving Whisper spans with proportional sentence boundaries: {exc}",
            )
            for source_segment in language_segments:
                aligned_segments.extend(_split_segment_proportionally(source_segment))
        finally:
            if align_model is not None:
                del align_model
            _release_cuda(video_id, f"{language} alignment")

    aligned_segments.sort(key=lambda segment: float(segment.get("start", 0.0)))
    return aligned_segments


def _validate_timestamp_invariants(segments: list[dict], audio_duration: float) -> None:
    """Reject timestamp corruption before translation, subtitles or TTS can use it."""
    previous_start = -1.0
    previous_end = -1.0
    for index, segment in enumerate(segments, start=1):
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        if not segment.get("text", "").strip():
            raise RuntimeError(f"Whisper sentence {index} has no text.")
        if start < previous_start or end <= start:
            raise RuntimeError(f"Whisper sentence {index} has invalid or non-monotonic timestamps.")
        if start < previous_end - 0.05:
            raise RuntimeError(f"Whisper sentence {index} overlaps the previous sentence timestamp.")
        if end > audio_duration + 0.5:
            raise RuntimeError(f"Whisper sentence {index} ends outside the source audio.")
        previous_start = start
        previous_end = end


def transcribe(audio_path: str, output_json_path: str, source_language: str, video_id: str, progress_callback=None):
    """Transcribe through WhisperX and align sentence timestamps per language."""
    log_to_video(video_id, f"Initializing WhisperX with model '{WHISPER_MODEL}'.")
    profile = runtime_profile()
    device = "cuda" if profile.cuda_available else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    log_to_video(
        video_id,
        f"WhisperX device: {device}, compute type: {compute_type}, "
        f"batch size: {profile.whisper_batch_size}, threads: {profile.cpu_threads}.",
    )

    asr_model = None
    using_warm_model = False
    audio = None
    try:
        log_to_video(video_id, "Loading WhisperX transcription model.")
        if progress_callback:
            progress_callback("loading_model", "Loading WhisperX speech model")
        with _MODEL_LOCK:
            if _WARM_ASR_MODEL is not None and _WARM_DEVICE == device:
                asr_model = _WARM_ASR_MODEL
                using_warm_model = True
                log_to_video(video_id, "Reusing warmed WhisperX speech model.")
            else:
                asr_model = _load_whisper_model(device, compute_type, profile.cpu_threads)
        audio = whisperx.load_audio(audio_path)
        if source_language != "auto":
            log_to_video(video_id, f"Ignoring legacy source language '{source_language}'; using automatic detection.")

        log_to_video(video_id, "Running WhisperX batched transcription with automatic language detection.")
        if progress_callback:
            progress_callback("transcribing", "Transcribing speech")
        result = asr_model.transcribe(
            audio,
            batch_size=profile.whisper_batch_size,
            language=None,
        )
        detected_language = result.get("language")
        initial_segments = [
            {
                **segment,
                "language": detected_language or "en",
                "language_confidence": 1.0,
            }
            for segment in result.get("segments", [])
            if segment.get("text", "").strip()
        ]
        if not initial_segments:
            raise RuntimeError("WhisperX did not return any speech segments.")
        log_to_video(video_id, f"Transcription completed. Primary detected language: '{detected_language}'.")
        if progress_callback:
            progress_callback("transcribed", f"Detected {detected_language or 'unknown'} speech")

        sentence_segments = _align_segments_by_language(
            audio,
            initial_segments,
            device,
            video_id,
            progress_callback=progress_callback,
        )
        if progress_callback:
            progress_callback("segmenting", f"Prepared {len(sentence_segments)} complete sentences")

        source_segments = _detect_segment_languages(
            asr_model,
            audio,
            sentence_segments,
            detected_language or "en",
            video_id,
        )
        source_segments = _retranscribe_mixed_language_segments(
            asr_model,
            audio,
            source_segments,
            detected_language or "en",
            video_id,
        )
        has_language_switch = any(
            (segment.get("language") or detected_language or "en") != (detected_language or "en")
            for segment in source_segments
        )
        if has_language_switch:
            aligned_segments = _align_segments_by_language(
                audio,
                source_segments,
                device,
                video_id,
                progress_callback=None,
            )
        else:
            aligned_segments = source_segments
            log_to_video(video_id, "Keeping validated sentence timestamps; no language-switch realignment is needed.")

        output_segments = []
        for segment in aligned_segments:
            language, confidence = _language_for_aligned_segment(
                segment,
                source_segments,
                detected_language or "en",
            )
            output_segments.append(
                {
                    "start": round(float(segment["start"]), 3),
                    "end": round(float(segment["end"]), 3),
                    "text": segment["text"].strip(),
                    "language": language,
                    "language_confidence": round(confidence, 3),
                    "timing_source": TIMING_SOURCE,
                }
            )

        _validate_timestamp_invariants(output_segments, len(audio) / _AUDIO_SAMPLE_RATE)
        if progress_callback:
            progress_callback("detecting_languages", f"Validated {len(output_segments)} timed sentences")
        with open(output_json_path, "w", encoding="utf-8") as file:
            json.dump(output_segments, file, ensure_ascii=False, indent=2)

        log_to_video(video_id, f"Saved {len(output_segments)} timestamp-locked source sentences to: {output_json_path}")
        if progress_callback:
            progress_callback("saved", f"Prepared {len(output_segments)} timestamp-locked sentences")
        return output_segments, detected_language
    finally:
        if asr_model is not None and not using_warm_model:
            del asr_model
        if audio is not None:
            del audio
        _release_cuda(video_id, "WhisperX cleanup")
