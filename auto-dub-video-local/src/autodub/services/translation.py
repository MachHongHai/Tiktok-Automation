import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid

from autodub.core.paths import is_frozen, project_root
from autodub.pipeline.job_manager import register_process, unregister_process
from autodub.services.job_store import log_to_job

try:
    from transformers.models.whisper.tokenization_whisper import LANGUAGES as WHISPER_LANGUAGE_NAMES
except ImportError:  # pragma: no cover - transformers is a runtime dependency.
    WHISPER_LANGUAGE_NAMES = {}


LANGUAGE_NAMES = {
    "vi": "Vietnamese",
    "en": "English",
    "zh": "Chinese",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "ar": "Arabic",
    "pt": "Portuguese",
    "ru": "Russian",
    "id": "Indonesian",
    "de": "German",
    "ja": "Japanese",
    "ko": "Korean",
    "it": "Italian",
    "th": "Thai",
    "fil": "Filipino",
}

_WORKER_LOCK = threading.RLock()
_WORKER_PROCESS = None
_WORKER_OUTPUT = None
_WORKER_READER = None


def language_name(language_code: str) -> str:
    normalized = (language_code or "").lower()
    return LANGUAGE_NAMES.get(normalized, WHISPER_LANGUAGE_NAMES.get(normalized, normalized or "English").title())


def translate_segments(
    input_json_path: str,
    output_json_path: str,
    job_id: str,
    target_language: str = "vi",
    source_language: str = "auto",
    provider: str = "hymt2",
    progress_callback=None,
):
    if provider != "hymt2":
        raise ValueError("HY-MT2 is the only supported translation provider.")

    target_language_name = language_name(target_language)
    log_to_job(job_id, f"Initializing HY-MT2 translation | target: {target_language_name}.")
    with open(input_json_path, "r", encoding="utf-8") as file:
        segments = json.load(file)

    source_texts = [segment["text"] for segment in segments]
    source_codes = [str(segment.get("language") or source_language or "en").lower() for segment in segments]
    translations = _translate_with_hymt2_worker(
        source_texts,
        job_id=job_id,
        source_languages=[language_name(code) for code in source_codes],
        target_language_name=target_language_name,
        progress_callback=progress_callback,
    )
    translated_segments = []
    total = len(segments)
    for index, (segment, source_text, translated_text) in enumerate(
        zip(segments, source_texts, translations),
        start=1,
    ):
        translated_text = clean_translation(translated_text)
        if is_suspicious_translation(source_text, translated_text, target_language_name):
            log_to_job(job_id, f"[{index}/{total}] HY-MT2 output failed validation. Keeping the source subtitle.")
            translated_text = source_text
        log_to_job(job_id, f"[{index}/{total}] Segment translation: '{source_text}' -> '{translated_text}'")
        translated_segments.append(
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": translated_text or source_text,
                "source_language": source_codes[index - 1],
            }
        )

    with open(output_json_path, "w", encoding="utf-8") as file:
        json.dump(translated_segments, file, ensure_ascii=False, indent=2)
    log_to_job(job_id, f"Saved translated segments to: {output_json_path}")
    return translated_segments


def _worker_command() -> list[str]:
    if is_frozen():
        return [sys.executable, "--hymt2-worker", "--server"]
    return [sys.executable, "-m", "autodub.services.hymt2_worker", "--server"]


def _discard_hymt2_worker(process=None) -> None:
    global _WORKER_PROCESS, _WORKER_OUTPUT, _WORKER_READER
    if process is not None and process is not _WORKER_PROCESS:
        return
    _WORKER_PROCESS = None
    _WORKER_OUTPUT = None
    _WORKER_READER = None


def _ensure_hymt2_worker():
    global _WORKER_PROCESS, _WORKER_OUTPUT, _WORKER_READER
    if _WORKER_PROCESS is not None and _WORKER_PROCESS.poll() is None and _WORKER_OUTPUT is not None:
        return _WORKER_PROCESS, _WORKER_OUTPUT

    _discard_hymt2_worker()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root() / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    environment["OMP_NUM_THREADS"] = "1"
    environment["MKL_NUM_THREADS"] = "1"
    environment["PYTHONFAULTHANDLER"] = "1"
    process = subprocess.Popen(
        _worker_command(),
        cwd=str(project_root()),
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output_queue = queue.Queue()

    def read_output():
        for line in process.stdout or []:
            output_queue.put(line)

    reader = threading.Thread(target=read_output, name="hymt2-worker-output", daemon=True)
    reader.start()
    _WORKER_PROCESS = process
    _WORKER_OUTPUT = output_queue
    _WORKER_READER = reader
    return process, output_queue


def shutdown_hymt2_worker() -> None:
    """Release the persistent translation model when the desktop session closes."""
    with _WORKER_LOCK:
        process = _WORKER_PROCESS
        if process is None:
            return
        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write(json.dumps({"request_id": uuid.uuid4().hex, "command": "shutdown"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=5)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.kill()
        finally:
            _discard_hymt2_worker(process)


def warm_hymt2_worker(status_callback=None) -> None:
    """Load HY-MT2 once in the persistent worker before the first job arrives."""
    with _WORKER_LOCK:
        process, output_queue = _ensure_hymt2_worker()
        request_id = uuid.uuid4().hex
        try:
            if process.stdin is None:
                raise RuntimeError("HY-MT2 worker input channel is unavailable.")
            process.stdin.write(json.dumps({"request_id": request_id, "command": "warm"}) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + 300
            while True:
                if time.monotonic() >= deadline:
                    process.kill()
                    _discard_hymt2_worker(process)
                    raise RuntimeError("HY-MT2 warm-up timed out after 5 minutes.")
                try:
                    line = output_queue.get(timeout=0.25)
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "status" and status_callback:
                    status_callback(str(event.get("detail", "Preparing HY-MT2 translation model")))
                if event.get("event") != "response" or event.get("request_id") != request_id:
                    continue
                if event.get("error"):
                    raise RuntimeError(event["error"])
                if event.get("warmed"):
                    return
                raise RuntimeError("HY-MT2 worker returned an invalid warm-up response.")
        except Exception:
            if process.poll() is not None:
                _discard_hymt2_worker(process)
            raise

        _discard_hymt2_worker(process)
        raise RuntimeError(f"HY-MT2 worker stopped during warm-up with exit code {process.returncode}.")


def _translate_with_hymt2_worker(
    texts: list[str],
    job_id: str,
    source_languages: list[str],
    target_language_name: str,
    progress_callback=None,
) -> list[str]:
    if not texts:
        return []
    if len(source_languages) != len(texts):
        raise ValueError("Each translation segment must have a source language.")
    with _WORKER_LOCK:
        process, output_queue = _ensure_hymt2_worker()
        request_id = uuid.uuid4().hex
        payload = {
            "request_id": request_id,
            "payload": {
                "texts": texts,
                "source_languages": source_languages,
                "target_language_name": target_language_name,
            },
        }
        worker_output = []
        log_to_job(job_id, "Sending translation request to persistent HY-MT2 worker.")
        register_process(job_id, process)
        try:
            if process.stdin is None:
                raise RuntimeError("HY-MT2 worker input channel is unavailable.")
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + 1800
            while True:
                if time.monotonic() >= deadline:
                    process.kill()
                    _discard_hymt2_worker(process)
                    raise RuntimeError("HY-MT2 translation timed out after 30 minutes.")
                try:
                    line = output_queue.get(timeout=0.25)
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                worker_output.append(line)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "status":
                    detail = str(event.get("detail", "Preparing HY-MT2 translation"))
                    log_to_job(job_id, detail)
                    if progress_callback:
                        progress_callback(0, 0, detail)
                    continue
                if event.get("event") == "batch_started":
                    total = int(event.get("total", len(texts)))
                    completed = int(event.get("completed", 0))
                    detail = f"Translating subtitles {event.get('start', completed + 1)}-{event.get('end', completed)} of {total}"
                    log_to_job(job_id, detail)
                    if progress_callback:
                        progress_callback(completed, total, detail)
                    continue
                if event.get("event") == "progress":
                    current = int(event.get("current", 0))
                    total = int(event.get("total", len(texts)))
                    detail = f"Translated {current} of {total} subtitles"
                    log_to_job(job_id, detail)
                    if progress_callback:
                        progress_callback(current, total, detail)
                    continue
                if event.get("event") != "response" or event.get("request_id") != request_id:
                    continue
                if event.get("error"):
                    raise RuntimeError(event["error"])
                translations = event.get("translations")
                if not isinstance(translations, list) or len(translations) != len(texts) or not all(isinstance(text, str) for text in translations):
                    raise RuntimeError("HY-MT2 worker returned an invalid translation result.")
                log_to_job(job_id, "HY-MT2 translation completed; model stays warm for the next job.")
                return translations
        finally:
            unregister_process(job_id, process)

        details = "".join(worker_output).strip() or "no worker output"
        return_code = process.returncode
        _discard_hymt2_worker(process)
        if return_code == 3221225477:
            details = (
                "Native Torch crash (0xC0000005) while loading or running HY-MT2. "
                f"Worker output: {details}"
            )
        raise RuntimeError(f"HY-MT2 worker stopped with exit code {return_code}: {details[-1000:]}")


def clean_translation(text: str) -> str:
    return " ".join(text.strip().strip('"').split())


def is_suspicious_translation(source_text: str, translated_text: str, target_language_name: str) -> bool:
    source_content = "".join(character for character in source_text if character.isalnum())
    translated_content = "".join(character for character in translated_text if character.isalnum())
    if source_content and not translated_content:
        return True
    if len(source_content) >= 35 and len(translated_content) < max(6, len(source_content) // 10):
        return True
    required_script = {
        "Hindi": r"[\u0900-\u097f]",
        "Arabic": r"[\u0600-\u06ff]",
        "Russian": r"[\u0400-\u04ff]",
        "Korean": r"[\uac00-\ud7af]",
        "Thai": r"[\u0e00-\u0e7f]",
    }.get(target_language_name)
    if required_script and len(source_content) >= 12:
        import re

        return re.search(required_script, translated_text) is None
    return False
