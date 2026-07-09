import os
import subprocess
import time

import requests

from app.config import BIN_DIR, OLLAMA_BASE_URL, OLLAMA_MODELS_DIR, TRANSLATOR_PROVIDER
from app.services.job_store import log_to_job


def ensure_ollama_running(job_id: str):
    """Start the bundled Ollama server when the selected translator needs it."""
    if TRANSLATOR_PROVIDER != "ollama":
        return

    try:
        response = requests.get(OLLAMA_BASE_URL, timeout=1.5)
        if response.status_code == 200:
            log_to_job(job_id, "Ollama server is already running.")
            return
    except Exception:
        log_to_job(job_id, "Ollama server is not running. Attempting to start it automatically...")

    ollama_exe = os.path.join(BIN_DIR, "ollama", "ollama.exe")
    if not os.path.exists(ollama_exe):
        log_to_job(job_id, f"WARNING: Local Ollama binary not found at {ollama_exe}. Cannot auto-start.")
        return

    ollama_env = os.environ.copy()
    models_dir = os.path.abspath(OLLAMA_MODELS_DIR)
    os.makedirs(models_dir, exist_ok=True)
    ollama_env["OLLAMA_MODELS"] = models_dir

    try:
        creation_flags = 0
        if os.name == "nt":
            creation_flags = 0x00000008 | 0x00000200

        subprocess.Popen(
            [ollama_exe, "serve"],
            creationflags=creation_flags,
            env=ollama_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        log_to_job(job_id, "Ollama server process spawned. Waiting for initialization...")

        for _ in range(10):
            time.sleep(1)
            try:
                response = requests.get(OLLAMA_BASE_URL, timeout=1.0)
                if response.status_code == 200:
                    log_to_job(job_id, "Ollama server initialized and running successfully.")
                    return
            except Exception:
                pass
        log_to_job(job_id, "WARNING: Spawned Ollama server but it did not respond in 10 seconds.")
    except Exception as exc:
        log_to_job(job_id, f"ERROR: Failed to automatically start Ollama server: {exc}")
