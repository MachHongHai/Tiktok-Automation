import gc
import json

import torch
import whisperx

from autodub.config import WHISPER_MODEL
from autodub.services.job_store import log_to_job


def _release_cuda(job_id: str, stage: str) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log_to_job(job_id, f"Released WhisperX VRAM after {stage}.")


def transcribe(audio_path: str, output_json_path: str, source_language: str, job_id: str, progress_callback=None):
    """Transcribe and align audio while releasing each GPU model as soon as it is no longer needed."""
    log_to_job(job_id, f"Initializing WhisperX with model '{WHISPER_MODEL}'.")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    log_to_job(job_id, f"WhisperX device: {device}, compute type: {compute_type}.")

    asr_model = None
    align_model = None
    audio = None
    try:
        log_to_job(job_id, "Loading WhisperX transcription model.")
        if progress_callback:
            progress_callback("loading_model", "Loading WhisperX speech model")
        asr_model = whisperx.load_model(WHISPER_MODEL, device, compute_type=compute_type)
        audio = whisperx.load_audio(audio_path)
        language = None if source_language == "auto" else source_language
        log_to_job(job_id, f"Running transcription (source language: {source_language}).")
        if progress_callback:
            progress_callback("transcribing", "Transcribing speech")
        result = asr_model.transcribe(audio, batch_size=16, language=language)
        detected_language = result.get("language")
        log_to_job(job_id, f"Transcription completed. Detected language: '{detected_language}'.")
        if progress_callback:
            progress_callback("transcribed", f"Detected {detected_language or 'unknown'} speech")

        del asr_model
        asr_model = None
        _release_cuda(job_id, "transcription")

        aligned_segments = result["segments"]
        try:
            log_to_job(job_id, f"Loading alignment model for language '{detected_language}'.")
            if progress_callback:
                progress_callback("loading_alignment", "Loading subtitle alignment model")
            align_model, metadata = whisperx.load_align_model(language_code=detected_language, device=device)
            log_to_job(job_id, "Running forced alignment.")
            if progress_callback:
                progress_callback("aligning", "Aligning subtitle timestamps")
            aligned_result = whisperx.align(
                result["segments"],
                align_model,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            aligned_segments = aligned_result["segments"]
            log_to_job(job_id, "Forced alignment completed successfully.")
            if progress_callback:
                progress_callback("aligned", f"Aligned {len(aligned_segments)} segments")
        except Exception as exc:
            log_to_job(job_id, f"WARNING: Alignment failed or is unsupported for '{detected_language}'. Using raw segments: {exc}")
        finally:
            if align_model is not None:
                del align_model
                align_model = None
            _release_cuda(job_id, "alignment")

        output_segments = [
            {
                "start": round(segment.get("start", 0.0), 3),
                "end": round(segment.get("end", 0.0), 3),
                "text": segment.get("text", "").strip(),
            }
            for segment in aligned_segments
        ]
        with open(output_json_path, "w", encoding="utf-8") as file:
            json.dump(output_segments, file, ensure_ascii=False, indent=2)

        log_to_job(job_id, f"Saved {len(output_segments)} transcribed segments to: {output_json_path}")
        if progress_callback:
            progress_callback("saved", f"Prepared {len(output_segments)} subtitle segments")
        return output_segments, detected_language
    finally:
        if asr_model is not None:
            del asr_model
        if align_model is not None:
            del align_model
        if audio is not None:
            del audio
        _release_cuda(job_id, "WhisperX cleanup")
