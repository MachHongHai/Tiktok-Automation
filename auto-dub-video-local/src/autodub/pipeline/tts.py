import asyncio
import os
import json
import edge_tts
from autodub.services.job_store import log_to_job

def preprocess_text_for_tts(text: str) -> str:
    """Normalize whitespace and punctuation without changing translated words."""
    if not text:
        return ""
    text = " ".join(text.split())

    # A terminal pause helps Edge TTS pronounce short fragments naturally.
    if text and text[-1] not in ('.', '!', '?', ',', ';', ':', '...'):
        text += "."
        
    return text

async def tts_segment_with_retry(text: str, voice: str, output_path: str, retries: int = 3):
    """Invokes edge-tts to speak text, retrying if a network error occurs."""
    processed_text = preprocess_text_for_tts(text)
    for attempt in range(retries):
        try:
            communicate = edge_tts.Communicate(processed_text, voice)
            await communicate.save(output_path)
            return
        except Exception as e:
            if attempt == retries - 1:
                raise e
            # Exponential backoff
            await asyncio.sleep(1.5 * (attempt + 1))

def generate_voice_parts(segments_json_path: str, voice_parts_dir: str, voice: str, job_id: str, progress_callback=None):
    """Translates a JSON segments file into individual voice MP3 files."""
    log_to_job(job_id, f"Starting voice parts generation with voice '{voice}'...")
    
    with open(segments_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
        
    async def run_all():
        total = len(segments)
        for idx, seg in enumerate(segments, 1):
            text = seg["text"]
            part_path = os.path.join(voice_parts_dir, f"voice_{idx:04d}.mp3")
            
            if not text.strip():
                # Write an empty file to represent silence
                open(part_path, "wb").close()
                if progress_callback:
                    progress_callback(idx, total)
                continue
                
            try:
                log_to_job(job_id, f"[{idx}/{total}] TTS synthesis: '{text}' -> {os.path.basename(part_path)}")
                await tts_segment_with_retry(text, voice, part_path)
            except Exception as tts_err:
                log_to_job(job_id, f"[{idx}/{total}] WARNING: TTS synthesis failed for '{text}': {str(tts_err)}. Using silence fallback.")
                open(part_path, "wb").close()
            finally:
                if progress_callback:
                    progress_callback(idx, total)
            
    # Run async function using a dedicated event loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_all())
        loop.close()
    except Exception as e:
        log_to_job(job_id, f"Primary event loop failed: {str(e)}. Attempting asyncio.run fallback...")
        asyncio.run(run_all())
        
    log_to_job(job_id, "All segment voices generated successfully.")

def generate_single_voice(text: str, output_path: str, voice: str, job_id: str):
    """Speaks a complete text script into a single output file."""
    log_to_job(job_id, f"Generating single narration voice file (voice '{voice}')...")
    
    async def run_single():
        await tts_segment_with_retry(text, voice, output_path)
        
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_single())
        loop.close()
    except Exception as e:
        log_to_job(job_id, f"Primary event loop failed: {str(e)}. Attempting asyncio.run fallback...")
        asyncio.run(run_single())
        
    log_to_job(job_id, f"Successfully created narration file: {output_path}")

