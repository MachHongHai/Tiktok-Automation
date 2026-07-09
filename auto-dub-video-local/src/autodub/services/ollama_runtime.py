import os
import subprocess
import time
from urllib.parse import urlparse

import requests

from autodub.config import BIN_DIR, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_MODELS_DIR, TRANSLATOR_PROVIDER
from autodub.services.job_store import log_to_job


def ensure_ollama_running(job_id: str | None = None, warm_model: bool = False):
    """Start the bundled Ollama server when the selected translator needs it."""
    if TRANSLATOR_PROVIDER != "ollama":
        return

    try:
        response = requests.get(OLLAMA_BASE_URL, timeout=1.5)
        if response.status_code == 200:
            _log(job_id, "Ollama server is already running.")
            if warm_model:
                _warm_ollama_model(job_id)
            return
    except Exception:
        _log(job_id, "Ollama server is not running. Attempting to start it automatically...")

    ollama_exe = os.path.join(BIN_DIR, "ollama", "ollama.exe")
    if not os.path.exists(ollama_exe):
        _log(job_id, f"WARNING: Local Ollama binary not found at {ollama_exe}. Cannot auto-start.")
        return

    ollama_env = os.environ.copy()
    models_dir = os.path.abspath(OLLAMA_MODELS_DIR)
    os.makedirs(models_dir, exist_ok=True)
    ollama_env["OLLAMA_MODELS"] = models_dir
    ollama_env["OLLAMA_HOST"] = _ollama_host()

    try:
        creation_flags = 0
        startupinfo = None
        if os.name == "nt":
            # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
            creation_flags = 0x08000000 | 0x00000200
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        subprocess.Popen(
            [ollama_exe, "serve"],
            creationflags=creation_flags,
            env=ollama_env,
            cwd=os.path.dirname(ollama_exe),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            close_fds=True,
        )
        _log(job_id, "Ollama server process spawned in background. Waiting for initialization...")

        for _ in range(10):
            time.sleep(1)
            try:
                response = requests.get(OLLAMA_BASE_URL, timeout=1.0)
                if response.status_code == 200:
                    _log(job_id, "Ollama server initialized and running successfully.")
                    if warm_model:
                        _warm_ollama_model(job_id)
                    return
            except Exception:
                pass
        _log(job_id, "WARNING: Spawned Ollama server but it did not respond in 10 seconds.")
    except Exception as exc:
        _log(job_id, f"ERROR: Failed to automatically start Ollama server: {exc}")


def _warm_ollama_model(job_id: str | None):
    try:
        _log(job_id, f"Warming Ollama model '{OLLAMA_MODEL}' in background...")
        response = requests.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": "OK",
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 1, "temperature": 0},
            },
            timeout=180,
        )
        response.raise_for_status()
        _log(job_id, f"Ollama model '{OLLAMA_MODEL}' is warm.")
    except Exception as exc:
        _log(job_id, f"WARNING: Failed to warm Ollama model '{OLLAMA_MODEL}': {exc}")


def _log(job_id: str | None, message: str):
    if job_id:
        log_to_job(job_id, message)
    else:
        print(message)


def _ollama_host() -> str:
    parsed = urlparse(OLLAMA_BASE_URL)
    if parsed.hostname and parsed.port:
        return f"{parsed.hostname}:{parsed.port}"
    if parsed.netloc:
        return parsed.netloc
    return "127.0.0.1:11434"

