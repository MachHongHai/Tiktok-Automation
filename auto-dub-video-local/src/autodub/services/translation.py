import json
import re
from typing import Optional

import requests

from autodub.config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    TRANSLATOR_PROVIDER,
)
from autodub.services.job_store import log_to_job

BATCH_SIZE = 30

SYSTEM_PROMPT = (
    "Bạn là dịch giả phụ đề chuyên nghiệp cho video ngắn. Dịch từ tiếng Anh sang tiếng Việt tự nhiên, "
    "đúng ngữ cảnh hội thoại, ngắn gọn và dễ đọc khi lồng tiếng.\n"
    "Quy tắc bắt buộc:\n"
    "1. Chỉ trả tiếng Việt, không giải thích, không ghi chú, không thêm tiếng Trung/chữ Hán.\n"
    "2. Giữ đúng nghĩa và đúng vai nói. Ví dụ: 'Excuse me, can I ask you for some directions?' = "
    "'Xin lỗi, cho tôi hỏi đường được không?' hoặc 'Xin lỗi, bạn chỉ đường giúp tôi được không?'. "
    "Không được đảo nghĩa thành 'bạn muốn hỏi tôi'.\n"
    "3. Với batch, mỗi dòng phải bắt đầu bằng số thật trong ngoặc vuông: [1], [2], [3]... "
    "Không được viết placeholder như [số_thứ_tự].\n"
    "4. Số dòng đầu ra phải bằng đúng số dòng đầu vào."
)


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

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Dịch câu sau sang tiếng Việt. Chỉ trả về bản dịch:\n\n{text}"},
            ],
            "options": {"temperature": 0.1},
            "stream": False,
        }
        try:
            response = requests.post(_ollama_chat_url(), json=payload, timeout=30)
            response.raise_for_status()
            translated = response.json().get("message", {}).get("content", "").strip()
            return clean_translation(translated)
        except Exception as exc:
            log_to_job(job_id, f"Ollama single translation error: {exc}")
            return text

    def translate_batch(self, texts: list[str], job_id: str) -> list[str]:
        if not texts:
            return []

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_batch_prompt(texts)},
            ],
            "options": {"temperature": 0.1},
            "stream": False,
        }
        try:
            log_to_job(job_id, f"Sending batch of {len(texts)} segments to Ollama...")
            response = requests.post(_ollama_chat_url(), json=payload, timeout=90)
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
            results = parse_batch_output(content, len(texts), job_id)
            if results is not None:
                return results
            log_to_job(job_id, "Ollama batch parse failed or length mismatched. Falling back to individual translation...")
        except Exception as exc:
            log_to_job(job_id, f"Ollama batch translation request failed: {exc}. Falling back to individual translation...")

        return [self.translate_single(text, job_id) for text in texts]


class OpenAICompatibleTranslator(BaseTranslator):
    def translate_single(self, text: str, job_id: str) -> str:
        if not text.strip():
            return ""

        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Dịch câu sau sang tiếng Việt. Chỉ trả về bản dịch:\n\n{text}"},
            ],
            "temperature": 0.2,
        }
        try:
            response = requests.post(_openai_chat_url(), json=payload, headers=_openai_headers(), timeout=30)
            response.raise_for_status()
            translated = response.json()["choices"][0]["message"]["content"].strip()
            return clean_translation(translated)
        except Exception as exc:
            log_to_job(job_id, f"OpenAI-compatible single translation error: {exc}")
            return text

    def translate_batch(self, texts: list[str], job_id: str) -> list[str]:
        if not texts:
            return []

        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_batch_prompt(texts)},
            ],
            "temperature": 0.2,
        }
        try:
            log_to_job(job_id, f"Sending batch of {len(texts)} segments to OpenAI-compatible API...")
            response = requests.post(_openai_chat_url(), json=payload, headers=_openai_headers(), timeout=90)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            results = parse_batch_output(content, len(texts), job_id)
            if results is not None:
                return results
            log_to_job(job_id, "OpenAI-compatible batch parse failed or length mismatched. Falling back to individual translation...")
        except Exception as exc:
            log_to_job(job_id, f"OpenAI-compatible batch translation request failed: {exc}. Falling back to individual translation...")

        return [self.translate_single(text, job_id) for text in texts]


def clean_translation(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"[\u4e00-\u9fff]", "", text)

    prefixes = [
        "Dịch:",
        "Tiếng Việt:",
        "Dịch lại:",
        "Bản dịch:",
        "Dịch sang tiếng Việt:",
    ]
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    text = re.sub(
        r"(?i)\b(note|translation|trans|explain|explanation|annotation|chú thích|dịch|nghĩa)\b.*?:",
        "",
        text,
    )
    text = text.replace('"', "").replace("'", "").replace("“", "").replace("”", "")
    text = re.sub(r"^\s*[\[\(]?\s*số[_\s-]*thứ[_\s-]*tự\s*[\]\)]?\s*[:.\-]?\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text if re.search(r"\w", text) else ""


def parse_batch_output(content: str, expected_count: int, job_id: str) -> Optional[list[str]]:
    translated_map = {}
    indexed_pattern = re.compile(r"^\s*\**\s*[\(\[\{]?\s*(\d+)\s*[\)\]\}]?\s*[\.:\-]?\s*\**\s*(.*)$")

    fallback_lines = []
    for raw_line in content.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = indexed_pattern.match(line)
        if match:
            translated_map[int(match.group(1))] = match.group(2).strip()
        else:
            cleaned = clean_translation(line)
            if cleaned:
                fallback_lines.append(cleaned)

    results = []
    for index in range(1, expected_count + 1):
        value = translated_map.get(index)
        results.append(clean_translation(value) if value is not None else None)

    if len(results) == expected_count and all(item is not None for item in results):
        return results

    # Some small local models copy the placeholder label for every line. If line count still matches,
    # keep batch context by accepting sequential lines instead of falling back to isolated translation.
    if not translated_map and len(fallback_lines) == expected_count:
        log_to_job(job_id, "Batch output used non-numeric labels; accepted lines sequentially.")
        return fallback_lines

    log_to_job(job_id, f"Batch parse warning: Expected {expected_count} lines, parsed {len(translated_map)} valid lines.")
    log_to_job(job_id, f"Raw LLM output:\n{content}")
    return None


def get_translator() -> BaseTranslator:
    if TRANSLATOR_PROVIDER == "ollama":
        return OllamaTranslator()
    if TRANSLATOR_PROVIDER == "openai_compatible":
        return OpenAICompatibleTranslator()
    return MockTranslator()


def translate_segments(input_json_path: str, output_json_path: str, job_id: str):
    log_to_job(job_id, f"Initializing translation using provider: {TRANSLATOR_PROVIDER}...")

    with open(input_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    translator = get_translator()
    all_texts = [seg["text"] for seg in segments]
    all_translated_texts = []
    total = len(segments)

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

    translated_segments = []
    for seg, trans_text in zip(segments, all_translated_texts):
        translated_segments.append(
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": trans_text if trans_text and trans_text.strip() else seg["text"],
            }
        )

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(translated_segments, f, ensure_ascii=False, indent=2)

    log_to_job(job_id, f"Saved translated segments to: {output_json_path}")
    return translated_segments


def _build_batch_prompt(texts: list[str]) -> str:
    formatted_input = "\n".join(f"[{index + 1}] {text}" for index, text in enumerate(texts))
    return (
        "Dịch từng dòng dưới đây sang tiếng Việt.\n"
        "BẮT BUỘC trả về đúng dạng: [1] bản dịch, [2] bản dịch, [3] bản dịch...\n"
        "Không dùng chữ 'số_thứ_tự'. Không bỏ số. Không thêm dòng ngoài danh sách.\n\n"
        f"{formatted_input}"
    )


def _ollama_chat_url() -> str:
    return f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"


def _openai_chat_url() -> str:
    return f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"


def _openai_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    return headers
