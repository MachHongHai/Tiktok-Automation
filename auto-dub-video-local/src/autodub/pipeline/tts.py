import asyncio
import os
import json
import re
import edge_tts
from autodub.services.job_store import log_to_job

def preprocess_text_for_tts(text: str) -> str:
    """Preprocesses translation text to ensure compatibility with Edge-TTS.
    It replaces English words that crash the vi-VN normalizer with Vietnamese equivalents or phonetics,
    and ensures the text ends with punctuation to prevent crashes on very short phrases.
    This is ONLY used for TTS voice synthesis (subtitles still show the original text).
    """
    if not text:
        return ""
        
    text = text.strip()
    # Replaces common English terms with Vietnamese phonetic equivalents or translations
    replacements = {
        r"\bunderrated\b": "đánh giá thấp",
        r"\boverrated\b": "đánh giá quá cao",
        r"\bbasically\b": "cơ bản",
        r"\bdensity\b": "mật độ",
        r"\bđensity\b": "mật độ",
        r"\bpocket\b": "bỏ túi",
        r"\bsugar\b": "đường",
        r"\bcalories\b": "calo",
        r"\bcalorie\b": "calo",
        r"\bdeficit\b": "thâm hụt",
        r"\bcarb\b": "carb",
        r"\bcarbs\b": "carb",
        r"\bprotein\b": "prô-tê-in",
        r"\bfit\b": "phù hợp",
        r"\bfits\b": "phù hợp",
        r"\bdetox\b": "thải độc",
        r"\bdiet\b": "ăn kiêng",
        r"\bcommencement\b": "lễ tốt nghiệp",
        r"\buniversities\b": "trường đại học",
        r"\buniversity\b": "trường đại học",
        r"\bcollege\b": "đại học",
        r"\bgraduated\b": "tốt nghiệp",
        r"\bhonored\b": "vinh dự",
        r"\btruth\b": "sự thật",
        r"\btold\b": "nói",
        r"\bblueberries\b": "việt quất",
        r"\bwatermelon\b": "dưa hấu",
        r"\bpineapple\b": "dứa",
        r"\bmelon\b": "dưa",
        r"\bgrapes\b": "nho",
        r"\bvitamin c\b": "vitamin xê",
        r"\bvitamin C\b": "vitamin xê",
        r"\bS tier\b": "hạng S",
        r"\bA tier\b": "hạng A",
        r"\bB tier\b": "hạng B",
        r"\bC tier\b": "hạng C",
        r"\bF tier\b": "hạng F",
        r"\bs-tier\b": "hạng S",
        r"\ba-tier\b": "hạng A",
        r"\bb-tier\b": "hạng B",
        r"\bc-tier\b": "hạng C",
        r"\bf-tier\b": "hạng F",
    }
    
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        
    # Ensure it ends with a punctuation (., !, ?) to prevent Edge-TTS failure on very short texts
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

def generate_voice_parts(segments_json_path: str, voice_parts_dir: str, voice: str, job_id: str):
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
                continue
                
            try:
                log_to_job(job_id, f"[{idx}/{total}] TTS synthesis: '{text}' -> {os.path.basename(part_path)}")
                await tts_segment_with_retry(text, voice, part_path)
            except Exception as tts_err:
                log_to_job(job_id, f"[{idx}/{total}] WARNING: TTS synthesis failed for '{text}': {str(tts_err)}. Using silence fallback.")
                open(part_path, "wb").close()
            
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

