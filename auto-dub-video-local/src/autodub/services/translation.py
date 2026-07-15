import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from autodub.core.paths import is_frozen, project_root
from autodub.core.hardware import runtime_profile
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
_WORKER_WARM = False
_WORKER_IDLE_TIMER = None
_WORKER_DIAGNOSTIC_PATH = None


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
    global _WORKER_PROCESS, _WORKER_OUTPUT, _WORKER_READER, _WORKER_WARM, _WORKER_DIAGNOSTIC_PATH
    if process is not None and process is not _WORKER_PROCESS:
        return
    _WORKER_PROCESS = None
    _WORKER_OUTPUT = None
    _WORKER_READER = None
    _WORKER_WARM = False
    _WORKER_DIAGNOSTIC_PATH = None


def _worker_diagnostic_path(process=None) -> str:
    if process is not None and process is not _WORKER_PROCESS:
        return ""
    return str(_WORKER_DIAGNOSTIC_PATH or "")


def _prune_worker_diagnostics(directory: Path, keep: int = 25) -> None:
    """Retain recent crash evidence without allowing worker logs to grow forever."""
    try:
        diagnostics = sorted(
            directory.glob("hymt2-worker-*.log"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
    except OSError:
        return
    for stale_path in diagnostics[keep:]:
        try:
            stale_path.unlink()
        except OSError:
            pass


def _last_worker_stage(worker_output: list[str]) -> str:
    for line in reversed(worker_output):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "diagnostic" and isinstance(event.get("detail"), dict):
            stage = event["detail"].get("stage")
            if stage:
                return str(stage)
        if event.get("event") == "status" and event.get("detail"):
            return str(event["detail"])
    return "worker startup"


def _format_worker_exit(
    return_code: int | None,
    phase: str,
    worker_output: list[str],
    diagnostic_path: str,
) -> str:
    code = int(return_code or 0)
    unsigned_code = code & 0xFFFFFFFF
    hex_code = f"0x{unsigned_code:08X}"
    classifications = {
        0xC0000005: "Windows access violation in native code (Torch, CUDA, driver, or a native dependency)",
        0xC0000017: "Windows could not reserve enough virtual memory",
        0xC000009A: "Windows reported insufficient system resources",
        0xC000012D: "Windows commit limit was reached",
        0xC0000409: "Windows terminated the process after a native stack or security check failure",
    }
    classification = classifications.get(unsigned_code, "unexpected worker process termination")
    last_stage = _last_worker_stage(worker_output)
    non_json_tail = [line.strip() for line in worker_output[-30:] if line.strip() and not line.lstrip().startswith("{")]
    tail = " | ".join(non_json_tail)[-1500:] or "no native stderr was emitted"
    return (
        f"HY-MT2 worker stopped unexpectedly during {phase}. Exit code: {code} ({hex_code}); "
        f"classification: {classification}; last stage: {last_stage}. "
        f"Diagnostic log: {diagnostic_path or 'unavailable'}. Native output: {tail}"
    )


def _terminate_hymt2_worker(process) -> None:
    """Stop a failed worker so partial native model allocations are released."""
    if process is not None and process.poll() is None:
        try:
            process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
    _discard_hymt2_worker(process)


def _collect_remaining_worker_output(process, output_queue, worker_output: list[str]) -> None:
    """Wait briefly for the reader to persist native stderr after worker exit."""
    reader = _WORKER_READER if process is _WORKER_PROCESS else None
    if reader is not None and reader.is_alive():
        reader.join(timeout=2)
    while True:
        try:
            worker_output.append(output_queue.get_nowait())
        except queue.Empty:
            return


def _cancel_worker_idle_timer() -> None:
    global _WORKER_IDLE_TIMER
    timer = _WORKER_IDLE_TIMER
    _WORKER_IDLE_TIMER = None
    if timer is not None:
        timer.cancel()


def _schedule_worker_idle_shutdown() -> None:
    global _WORKER_IDLE_TIMER
    profile = runtime_profile()
    _cancel_worker_idle_timer()
    if not profile.is_cpu_only or profile.translation_idle_seconds <= 0:
        return
    timer = threading.Timer(profile.translation_idle_seconds, shutdown_hymt2_worker)
    timer.name = "hymt2-idle-shutdown"
    timer.daemon = True
    _WORKER_IDLE_TIMER = timer
    timer.start()


def is_hymt2_worker_warm() -> bool:
    """Return whether the persistent worker has a live, loaded model."""
    with _WORKER_LOCK:
        return bool(
            _WORKER_WARM
            and _WORKER_PROCESS is not None
            and _WORKER_PROCESS.poll() is None
        )


def _ensure_hymt2_worker():
    global _WORKER_PROCESS, _WORKER_OUTPUT, _WORKER_READER, _WORKER_WARM, _WORKER_DIAGNOSTIC_PATH
    _cancel_worker_idle_timer()
    if _WORKER_PROCESS is not None and _WORKER_PROCESS.poll() is None and _WORKER_OUTPUT is not None:
        return _WORKER_PROCESS, _WORKER_OUTPUT

    _discard_hymt2_worker()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root() / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    environment["OMP_NUM_THREADS"] = "1"
    environment["MKL_NUM_THREADS"] = "1"
    environment["PYTHONFAULTHANDLER"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    startupinfo = None
    if os.name == "nt":
        # Hide the console window while retaining normal process semantics for
        # CUDA and native Torch libraries.
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    process = subprocess.Popen(
        _worker_command(),
        cwd=str(project_root()),
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        startupinfo=startupinfo,
    )
    from autodub.config import HYMT2_MODEL, LOGS_DIR

    diagnostic_directory = Path(LOGS_DIR) / "hymt2-workers"
    diagnostic_directory.mkdir(parents=True, exist_ok=True)
    _prune_worker_diagnostics(diagnostic_directory)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    diagnostic_path = diagnostic_directory / f"hymt2-worker-{timestamp}-{process.pid}.log"
    profile = runtime_profile()
    diagnostic_path.write_text(
        json.dumps(
            {
                "event": "worker_started",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "launcher_pid": process.pid,
                "command": _worker_command(),
                "python": sys.version,
                "model": HYMT2_MODEL,
                "profile": profile.key,
                "backend": profile.hymt2_backend,
                "requested_device": profile.requested_device,
                "cuda_name": profile.cuda_name,
                "vram_gib": profile.total_vram_gib,
                "ram_gib": profile.total_ram_gib,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output_queue = queue.Queue()

    def read_output():
        with diagnostic_path.open("a", encoding="utf-8") as diagnostic_file:
            for line in process.stdout or []:
                diagnostic_file.write(line)
                diagnostic_file.flush()
                output_queue.put(line)
            try:
                return_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                return_code = process.poll()
            diagnostic_file.write(
                json.dumps(
                    {
                        "event": "worker_output_closed",
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "return_code": return_code,
                        "return_code_hex": f"0x{(int(return_code or 0) & 0xFFFFFFFF):08X}",
                    }
                )
                + "\n"
            )
            diagnostic_file.flush()

    _WORKER_PROCESS = process
    _WORKER_OUTPUT = output_queue
    _WORKER_DIAGNOSTIC_PATH = diagnostic_path
    reader = threading.Thread(target=read_output, name="hymt2-worker-output", daemon=True)
    _WORKER_READER = reader
    _WORKER_WARM = False
    reader.start()
    return process, output_queue


def shutdown_hymt2_worker() -> None:
    """Release the persistent translation model when the desktop session closes."""
    with _WORKER_LOCK:
        _cancel_worker_idle_timer()
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
    global _WORKER_WARM
    with _WORKER_LOCK:
        process, output_queue = _ensure_hymt2_worker()
        request_id = uuid.uuid4().hex
        worker_output = []
        try:
            if process.stdin is None:
                raise RuntimeError("HY-MT2 worker input channel is unavailable.")
            process.stdin.write(json.dumps({"request_id": request_id, "command": "warm"}) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + 300
            while True:
                if time.monotonic() >= deadline:
                    diagnostic_path = _worker_diagnostic_path(process)
                    process.kill()
                    _discard_hymt2_worker(process)
                    raise RuntimeError(
                        f"HY-MT2 warm-up timed out after 5 minutes. Diagnostic log: {diagnostic_path or 'unavailable'}"
                    )
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
                if event.get("event") == "status" and status_callback:
                    status_callback(str(event.get("detail", "Preparing HY-MT2 translation model")))
                if event.get("event") != "response" or event.get("request_id") != request_id:
                    continue
                if event.get("error"):
                    error = str(event["error"])
                    diagnostic_path = _worker_diagnostic_path(process)
                    _terminate_hymt2_worker(process)
                    raise RuntimeError(f"{error} Diagnostic log: {diagnostic_path or 'unavailable'}")
                if event.get("warmed"):
                    _WORKER_WARM = True
                    return
                raise RuntimeError("HY-MT2 worker returned an invalid warm-up response.")
        except Exception:
            if process.poll() is not None:
                _discard_hymt2_worker(process)
            raise

        _collect_remaining_worker_output(process, output_queue, worker_output)
        diagnostic_path = _worker_diagnostic_path(process)
        error = _format_worker_exit(
            process.returncode,
            "model warm-up",
            worker_output,
            diagnostic_path,
        )
        _discard_hymt2_worker(process)
        raise RuntimeError(error)


def _translate_with_hymt2_worker(
    texts: list[str],
    job_id: str,
    source_languages: list[str],
    target_language_name: str,
    progress_callback=None,
) -> list[str]:
    global _WORKER_WARM
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
        diagnostic_path = _worker_diagnostic_path(process)
        log_to_job(job_id, f"HY-MT2 diagnostic log: {diagnostic_path or 'unavailable'}")
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
                    error = str(event["error"])
                    diagnostic_path = _worker_diagnostic_path(process)
                    _terminate_hymt2_worker(process)
                    raise RuntimeError(f"{error} Diagnostic log: {diagnostic_path or 'unavailable'}")
                translations = event.get("translations")
                if not isinstance(translations, list) or len(translations) != len(texts) or not all(isinstance(text, str) for text in translations):
                    raise RuntimeError("HY-MT2 worker returned an invalid translation result.")
                _WORKER_WARM = True
                _schedule_worker_idle_shutdown()
                if runtime_profile().is_cpu_only:
                    log_to_job(
                        job_id,
                        f"HY-MT2 CPU model stays warm for {runtime_profile().translation_idle_seconds} seconds.",
                    )
                else:
                    log_to_job(job_id, "HY-MT2 translation completed; model stays warm for the next job.")
                return translations
        finally:
            unregister_process(job_id, process)

        _collect_remaining_worker_output(process, output_queue, worker_output)
        return_code = process.returncode
        diagnostic_path = _worker_diagnostic_path(process)
        error = _format_worker_exit(
            return_code,
            "translation",
            worker_output,
            diagnostic_path,
        )
        _discard_hymt2_worker(process)
        raise RuntimeError(error)


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
