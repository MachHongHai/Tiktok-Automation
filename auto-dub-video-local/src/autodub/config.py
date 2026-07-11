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
os.environ["HF_HOME"] = HF_HOME
os.environ["TORCH_HOME"] = TORCH_HOME

for directory in (RUNTIME_DATA_DIR, STORAGE_DIR, CACHE_DIR, LOGS_DIR, MODELS_DIR, HF_HOME, TORCH_HOME):
    os.makedirs(directory, exist_ok=True)

JOBS_DIR = STORAGE_DIR
