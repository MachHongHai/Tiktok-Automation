import json
import requests
import re
from app.config import (
    TRANSLATOR_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL
)
from app.job_store import log_to_job

class BaseTranslator:
    def translate_batch(self, texts: list[str], job_id: str) -> list[str]:
        raise NotImplementedError()
        
    def translate_single(self, text: str, job_id: str) -> str:
        raise NotImplementedError()

class MockTranslator(BaseTranslator):
    def translate_batch(self, texts: list[str], job_id: str) -> list[str]:
        return texts
        
    def translate_single(self, text: str, job_id: str) -> str:
        return text

class OllamaTranslator(BaseTranslator):
    def translate_single(self, text: str, job_id: str) -> str:
        if not text.strip():
            return ""
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional subtitle translator. Translate the given text to natural Vietnamese. Output ONLY the translation. Never include explanations, notes, or any other languages."
                },
                {
                    "role": "user",
                    "content": f"Dịch và viết lại câu sau sang tiếng Việt tự nhiên, ngắn gọn, phù hợp phụ đề video TikTok. Chỉ trả về câu tiếng Việt:\n\n'{text}'"
                }
            ],
            "options": {
                "temperature": 0.2
            },
            "stream": False
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            translated = result.get("message", {}).get("content", "").strip()
            return clean_translation(translated)
        except Exception as e:
            log_to_job(job_id, f"Ollama single translation error: {str(e)}")
            return text

    def translate_batch(self, texts: list[str], job_id: str) -> list[str]:
        if not texts:
            return []
            
        formatted_input = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(texts))
        system_prompt = (
            "You are a professional subtitle translator. Translate the given numbered list of English subtitle segments into natural, concise Vietnamese.\n"
            "Follow these rules strictly:\n"
            "1. Translate into natural Vietnamese. Never output Chinese or any other language.\n"
            "2. Translate contextually, preserving the flow and pronouns across segments.\n"
            "3. Keep the translations concise, suitable for video subtitles.\n"
            "4. Maintain the exact format '[index] Translated text' for each line.\n"
            "5. Do NOT include any explanations, introduction, notes, or other languages. Output ONLY the translated list."
        )
        user_prompt = (
            "Dịch danh sách phụ đề tiếng Anh sau sang tiếng Việt tự nhiên (Tuyệt đối KHÔNG dịch sang tiếng Trung) và giữ nguyên định dạng '[chỉ_số] câu_dịch':\n\n"
            f"{formatted_input}"
        )
        
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "options": {
                "temperature": 0.2
            },
            "stream": False
        }
        
        try:
            log_to_job(job_id, f"Sending batch of {len(texts)} segments to Ollama...")
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
            
            # Parse output
            results = parse_batch_output(content, len(texts), job_id)
            if results is not None:
                return results
                
            log_to_job(job_id, "Ollama batch parse failed or length mismatched. Falling back to individual translation...")
        except Exception as e:
            log_to_job(job_id, f"Ollama batch translation request failed: {str(e)}. Falling back to individual translation...")
            
        # Fallback to individual
        fallback_results = []
        for text in texts:
            fallback_results.append(self.translate_single(text, job_id))
        return fallback_results

class OpenAICompatibleTranslator(BaseTranslator):
    def translate_single(self, text: str, job_id: str) -> str:
        if not text.strip():
            return ""
        prompt = f"Dịch và viết lại câu sau sang tiếng Việt tự nhiên, ngắn gọn, hợp video TikTok. Không giải thích, chỉ trả về câu tiếng Việt. Giữ ý chính, tránh câu quá dài. Câu gốc: {text}"
        url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
            
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            translated = result["choices"][0]["message"]["content"].strip()
            return clean_translation(translated)
        except Exception as e:
            log_to_job(job_id, f"OpenAI Compatible single translation error: {str(e)}")
            return text

    def translate_batch(self, texts: list[str], job_id: str) -> list[str]:
        if not texts:
            return []
            
        formatted_input = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(texts))
        system_prompt = (
            "You are a professional subtitle translator. Translate the given numbered list of subtitle segments into natural, concise Vietnamese.\n"
            "Follow these rules strictly:\n"
            "1. Translate contextually, preserving the flow and pronouns across segments.\n"
            "2. Keep the translations concise, suitable for video subtitles.\n"
            "3. Maintain the exact format '[index] Translated text' for each line.\n"
            "4. Return exactly the same number of lines as the input.\n"
            "5. Do NOT include any explanations, introduction, notes, or other languages. Output ONLY the translated list."
        )
        user_prompt = (
            "Dịch danh sách phụ đề sau sang tiếng Việt tự nhiên và giữ nguyên định dạng '[chỉ_số] câu_dịch':\n\n"
            f"{formatted_input}"
        )
        
        url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
            
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3
        }
        
        try:
            log_to_job(job_id, f"Sending batch of {len(texts)} segments to OpenAI-Compatible API...")
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            
            # Parse output
            results = parse_batch_output(content, len(texts), job_id)
            if results is not None:
                return results
                
            log_to_job(job_id, "OpenAI Compatible batch parse failed or length mismatched. Falling back to individual translation...")
        except Exception as e:
            log_to_job(job_id, f"OpenAI Compatible batch translation request failed: {str(e)}. Falling back to individual translation...")
            
        # Fallback to individual
        fallback_results = []
        for text in texts:
            fallback_results.append(self.translate_single(text, job_id))
        return fallback_results

def clean_translation(text: str) -> str:
    """Removes double quotes, single quotes, or model-generated prefixes from translation output."""
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1].strip()
    
    # Remove common prefix headings returned by some models
    prefixes = ["Dịch:", "Tiếng Việt:", "Dịch lại:", "Bản dịch:", "Tiếng Việt dịch:", "Dịch sang tiếng Việt:"]
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
            
    # Clean quotes again if they were inside the prefix
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
        
    return text

def parse_batch_output(content: str, expected_count: int, job_id: str) -> list[str] | None:
    """
    Parses LLM batch output formatted like '[1] text' or '1. text'.
    Returns list of cleaned translations of length `expected_count`, or None if parsing fails.
    """
    lines = content.strip().split("\n")
    translated_map = {}
    
    # Regex to match prefix index like [1], (1), 1., 1- followed by content
    pattern = re.compile(r"^\s*[\(\[\{]?\s*(\d+)\s*[\)\]\}]?\s*[\.:\-]?\s*(.*)$")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            try:
                idx = int(match.group(1))
                text = match.group(2).strip()
                translated_map[idx] = text
            except Exception:
                pass
                
    # Reconstruct in order
    results = []
    for i in range(expected_count):
        expected_idx = i + 1
        if expected_idx in translated_map:
            results.append(clean_translation(translated_map[expected_idx]))
        else:
            results.append(None)
            
    # Verify success: no None elements and correct count
    if len(results) == expected_count and all(r is not None for r in results):
        return results
        
    log_to_job(job_id, f"Batch parse warning: Expected {expected_count} lines, parsed {len(translated_map)} valid lines.")
    log_to_job(job_id, f"Raw LLM output:\n{content}")
    return None

def get_translator() -> BaseTranslator:
    if TRANSLATOR_PROVIDER == "ollama":
        return OllamaTranslator()
    elif TRANSLATOR_PROVIDER == "openai_compatible":
        return OpenAICompatibleTranslator()
    else:
        return MockTranslator()

def translate_segments(input_json_path: str, output_json_path: str, job_id: str):
    """Loads source segments, translates them in context-aware batches, and writes results back."""
    log_to_job(job_id, f"Initializing translation using provider: {TRANSLATOR_PROVIDER}...")
    
    with open(input_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
        
    translator = get_translator()
    
    BATCH_SIZE = 30
    total = len(segments)
    
    all_texts = [seg["text"] for seg in segments]
    all_translated_texts = []
    
    for start_idx in range(0, total, BATCH_SIZE):
        end_idx = min(start_idx + BATCH_SIZE, total)
        batch_texts = all_texts[start_idx:end_idx]
        
        log_to_job(job_id, f"Translating batch [{start_idx + 1}-{end_idx}/{total}]...")
        batch_translations = translator.translate_batch(batch_texts, job_id)
        
        for idx, (orig, trans) in enumerate(zip(batch_texts, batch_translations), start_idx + 1):
            if not trans or not trans.strip():
                trans = orig
            log_to_job(job_id, f"[{idx}/{total}] Segment translation: '{orig}' -> '{trans}'")
            
        all_translated_texts.extend(batch_translations)
        
    # Reassemble translated segments
    translated_segments = []
    for seg, trans_text in zip(segments, all_translated_texts):
        if not trans_text or not trans_text.strip():
            trans_text = seg["text"]
        translated_segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": trans_text
        })
        
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(translated_segments, f, ensure_ascii=False, indent=2)
        
    log_to_job(job_id, f"Saved translated segments to: {output_json_path}")
    return translated_segments
