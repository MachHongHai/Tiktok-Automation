from autodub.config import WHISPER_MODEL  # Import config first to load .env variables before importing torch/whisperx
import json
import torch
import whisperx
from autodub.services.job_store import log_to_job

def transcribe(audio_path: str, output_json_path: str, source_language: str, job_id: str):
    """Transcribes and aligns audio using WhisperX."""
    log_to_job(job_id, f"Initializing whisperX with model '{WHISPER_MODEL}'...")
    
    # Auto-detect CUDA availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # whisperX loads models with float16 on cuda, int8 on cpu
    compute_type = "float16" if device == "cuda" else "int8"
    log_to_job(job_id, f"Model device: {device}, compute type: {compute_type}")
    
    # 1. Transcribe with WhisperX
    log_to_job(job_id, "Loading WhisperX transcription model...")
    model = whisperx.load_model(WHISPER_MODEL, device, compute_type=compute_type)
    
    log_to_job(job_id, "Loading audio file...")
    audio = whisperx.load_audio(audio_path)
    
    lang_param = None if source_language == "auto" else source_language
    log_to_job(job_id, f"Running WhisperX transcription (source lang: {source_language})...")
    
    # Run transcription (batch_size=16 is recommended by whisperx for fast performance)
    result = model.transcribe(audio, batch_size=16, language=lang_param)
    
    detected_lang = result.get("language")
    log_to_job(job_id, f"Transcription completed. Detected language: '{detected_lang}'")
    
    # 2. Align whisper output
    aligned_segments = result["segments"]
    log_to_job(job_id, f"Loading alignment model for language '{detected_lang}'...")
    try:
        model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=device)
        log_to_job(job_id, "Running forced alignment...")
        aligned_result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
        aligned_segments = aligned_result["segments"]
        log_to_job(job_id, "Forced alignment completed successfully.")
    except Exception as ae:
        log_to_job(job_id, f"WARNING: Alignment failed or not supported for language '{detected_lang}'. Using raw segments. Error: {ae}")
        
    output_segments = []
    for segment in aligned_segments:
        segment_data = {
            "start": round(segment.get("start", 0.0), 3),
            "end": round(segment.get("end", 0.0), 3),
            "text": segment.get("text", "").strip()
        }
        output_segments.append(segment_data)
        log_to_job(job_id, f"Segment: {segment_data['start']}s - {segment_data['end']}s | {segment_data['text']}")
        
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output_segments, f, ensure_ascii=False, indent=2)
        
    log_to_job(job_id, f"Saved {len(output_segments)} transcribed segments to: {output_json_path}")
    return output_segments

