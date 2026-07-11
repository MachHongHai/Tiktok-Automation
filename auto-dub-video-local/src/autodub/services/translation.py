import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

from autodub.core.paths import project_root
from autodub.pipeline.job_manager import register_process, unregister_process
from autodub.services.job_store import get_job_dir, log_to_job


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


def language_name(language_code: str) -> str:
    return LANGUAGE_NAMES.get(language_code, language_code or "Vietnamese")


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
    translations = _translate_with_hymt2_worker(
        source_texts,
        job_id=job_id,
        source_language=language_name(source_language),
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
            }
        )

    with open(output_json_path, "w", encoding="utf-8") as file:
        json.dump(translated_segments, file, ensure_ascii=False, indent=2)
    log_to_job(job_id, f"Saved translated segments to: {output_json_path}")
    return translated_segments


def _translate_with_hymt2_worker(
    texts: list[str],
    job_id: str,
    source_language: str,
    target_language_name: str,
    progress_callback=None,
) -> list[str]:
    if not texts:
        return []

    temp_dir = os.path.join(get_job_dir(job_id), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    request_handle, request_path = tempfile.mkstemp(prefix="hymt2-request-", suffix=".json", dir=temp_dir)
    os.close(request_handle)
    response_path = request_path.replace("-request-", "-response-")
    try:
        with open(request_path, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "texts": texts,
                    "source_language": source_language,
                    "target_language_name": target_language_name,
                },
                file,
                ensure_ascii=False,
            )

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(project_root() / "src") + os.pathsep + environment.get("PYTHONPATH", "")
        command = [
            sys.executable,
            "-m",
            "autodub.services.hymt2_worker",
            "--request",
            request_path,
            "--response",
            response_path,
        ]
        log_to_job(job_id, "Starting isolated HY-MT2 translation worker.")
        process = subprocess.Popen(
            command,
            cwd=str(project_root()),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        register_process(job_id, process)
        worker_output = []
        output_queue = queue.Queue()

        def read_output():
            for line in process.stdout or []:
                output_queue.put(line)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        deadline = time.monotonic() + 1800
        try:
            while process.poll() is None or not output_queue.empty():
                if time.monotonic() >= deadline:
                    process.kill()
                    raise subprocess.TimeoutExpired(command, 1800)
                try:
                    line = output_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                worker_output.append(line)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "progress" and progress_callback:
                    progress_callback(int(event.get("current", 0)), int(event.get("total", 0)))
        finally:
            reader.join(timeout=1)
            unregister_process(job_id, process)
        if not os.path.exists(response_path):
            details = "".join(worker_output).strip() or "no worker output"
            raise RuntimeError(f"HY-MT2 worker stopped with exit code {process.returncode}: {details[-1000:]}")

        with open(response_path, "r", encoding="utf-8") as file:
            response = json.load(file)
        if response.get("error"):
            raise RuntimeError(response["error"])
        translations = response.get("translations")
        if not isinstance(translations, list) or len(translations) != len(texts) or not all(isinstance(text, str) for text in translations):
            raise RuntimeError("HY-MT2 worker returned an invalid translation result.")
        log_to_job(job_id, "HY-MT2 worker completed and released its model memory.")
        return translations
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("HY-MT2 translation timed out after 30 minutes.") from exc
    finally:
        for path in (request_path, response_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


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
