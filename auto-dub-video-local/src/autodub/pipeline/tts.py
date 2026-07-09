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
        r"\bunderrated\b": "Ä‘Ã¡nh giÃ¡ tháº¥p",
        r"\boverrated\b": "Ä‘Ã¡nh giÃ¡ quÃ¡ cao",
        r"\bbasically\b": "cÆ¡ báº£n",
        r"\bdensity\b": "máº­t Ä‘á»™",
        r"\bÄ‘ensity\b": "máº­t Ä‘á»™",
        r"\bpocket\b": "bá» tÃºi",
        r"\bsugar\b": "Ä‘Æ°á»ng",
        r"\bcalories\b": "calo",
        r"\bcalorie\b": "calo",
        r"\bdeficit\b": "thÃ¢m há»¥t",
        r"\bcarb\b": "cÃ¡c",
        r"\bcarbs\b": "cÃ¡c",
        r"\bprotein\b": "prÃ´-tÃª-in",
        r"\bfit\b": "phÃ¹ há»£p",
        r"\bfits\b": "phÃ¹ há»£p",
        r"\bdetox\b": "tháº£i Ä‘á»™c",
        r"\bdiet\b": "Äƒn kiÃªng",
        r"\bcommencement\b": "lá»… tá»‘t nghiá»‡p",
        r"\buniversities\b": "trÆ°á»ng Ä‘áº¡i há»c",
        r"\buniversity\b": "trÆ°á»ng Ä‘áº¡i há»c",
        r"\bcollege\b": "Ä‘áº¡i há»c",
        r"\bgraduated\b": "tá»‘t nghiá»‡p",
        r"\bhonored\b": "vinh dá»±",
        r"\btruth\b": "sá»± tháº­t",
        r"\btold\b": "nÃ³i",
        r"\bblueberries\b": "viá»‡t quáº¥t",
        r"\bwatermelon\b": "dÆ°a háº¥u",
        r"\bpineapple\b": "dá»©a",
        r"\bmelon\b": "dÆ°a",
        r"\bgrapes\b": "nho",
        r"\bvitamin c\b": "vitamin xÃª",
        r"\bvitamin C\b": "vitamin xÃª",
        r"\bS tier\b": "háº¡ng S",
        r"\bA tier\b": "háº¡ng A",
        r"\bB tier\b": "háº¡ng B",
        r"\bC tier\b": "háº¡ng C",
        r"\bF tier\b": "háº¡ng F",
        r"\bs-tier\b": "háº¡ng S",
        r"\ba-tier\b": "háº¡ng A",
        r"\bb-tier\b": "háº¡ng B",
        r"\bc-tier\b": "háº¡ng C",
        r"\bf-tier\b": "háº¡ng F",
        r"\bS\b": "háº¡ng Ã©t",
        r"\bA\b": "háº¡ng a",
        r"\bB\b": "háº¡ng bÃª",
        r"\bC\b": "háº¡ng xÃª",
        r"\bD\b": "háº¡ng Ä‘Ãª",
        r"\bF\b": "háº¡ng Ã©p",
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
    """Speaks a complete text script into a single output file (used in Mode C)."""
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

