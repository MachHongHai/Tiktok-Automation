import os
from pathlib import Path

from dotenv import load_dotenv

from autodub.core.paths import app_data_dir, bin_dir, cache_dir, logs_dir, package_root, project_root, runtime_data_dir, storage_dir

BASE_DIR = str(package_root())
PROJECT_ROOT = str(project_root())

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=True)
APP_DATA_DIR = str(app_data_dir())
load_dotenv(dotenv_path=os.path.join(APP_DATA_DIR, ".env"), override=True)
APP_DATA_DIR = str(app_data_dir())

RUNTIME_DATA_DIR = str(runtime_data_dir())
STORAGE_DIR = str(storage_dir())
CACHE_DIR = str(cache_dir())
LOGS_DIR = str(logs_dir())
MODELS_DIR = os.path.join(RUNTIME_DATA_DIR, "models")

PORT = int(os.getenv("PORT", 8000))
BIN_DIR = str(bin_dir())
if os.path.exists(BIN_DIR):
    os.environ["PATH"] = BIN_DIR + os.path.pathsep + os.environ["PATH"]

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
HYMT2_MODEL = os.getenv("HYMT2_MODEL", "tencent/Hy-MT2-1.8B")
HYMT2_CPU_MODEL_REPO = os.getenv("HYMT2_CPU_MODEL_REPO", "tencent/Hy-MT2-1.8B-GGUF")
HYMT2_CPU_MODEL_FILE = os.getenv("HYMT2_CPU_MODEL_FILE", "Hy-MT2-1.8B-Q4_K_M.gguf")
# Edge's consumer speech endpoint is substantially more reliable with one
# WebSocket at a time. Advanced users can still override this, but production
# defaults preserve the sequential behavior of the stable pipeline.
TTS_MAX_CONCURRENCY = max(1, min(4, int(os.getenv("TTS_MAX_CONCURRENCY", "1"))))


def _resolve_runtime_path(value: str | None, default: str) -> str:
    if not value:
        return default
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    parts = path.parts
    if parts and parts[0].lower() == "data":
        path = Path(*parts[1:])
    return str((Path(RUNTIME_DATA_DIR) / path).resolve())


HF_HOME = _resolve_runtime_path(os.getenv("HF_HOME"), os.path.join(CACHE_DIR, "huggingface"))
TORCH_HOME = _resolve_runtime_path(os.getenv("TORCH_HOME"), os.path.join(CACHE_DIR, "torch"))
PIP_CACHE_DIR = _resolve_runtime_path(os.getenv("PIP_CACHE_DIR"), os.path.join(CACHE_DIR, "pip"))
UV_CACHE_DIR = _resolve_runtime_path(os.getenv("UV_CACHE_DIR"), os.path.join(CACHE_DIR, "uv"))
TMP_DIR = _resolve_runtime_path(os.getenv("AUTODUB_TMP_DIR"), os.path.join(CACHE_DIR, "tmp"))
os.environ["HF_HOME"] = HF_HOME
os.environ["TORCH_HOME"] = TORCH_HOME
os.environ["PIP_CACHE_DIR"] = PIP_CACHE_DIR
os.environ["UV_CACHE_DIR"] = UV_CACHE_DIR
# Keep worker extraction/build temporary files out of the system drive.
os.environ["TMP"] = TMP_DIR
os.environ["TEMP"] = TMP_DIR

# Project-owned data is created inside the selected project. JOBS_DIR remains
# only as a read-once migration location for older installations.
for directory in (
    RUNTIME_DATA_DIR,
    CACHE_DIR,
    LOGS_DIR,
    MODELS_DIR,
    HF_HOME,
    TORCH_HOME,
    PIP_CACHE_DIR,
    UV_CACHE_DIR,
    TMP_DIR,
):
    os.makedirs(directory, exist_ok=True)

JOBS_DIR = STORAGE_DIR
