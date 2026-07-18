import os
from pathlib import Path

from dotenv import load_dotenv

from haizflow.core.model_integrity import (
    HYMT2_CPU_FILE,
    HYMT2_CPU_REPO,
    HYMT2_CPU_REVISION,
    HYMT2_GPU_REPO,
    HYMT2_GPU_REVISION,
    WHISPER_REPO,
    WHISPER_REVISION,
)
from haizflow.core.paths import (
    app_data_dir,
    bin_dir,
    cache_dir,
    install_root,
    logs_dir,
    models_dir,
    package_root,
    project_root,
    runtime_data_dir,
    storage_dir,
)

BASE_DIR = str(package_root())
PROJECT_ROOT = str(project_root())
_SMOKE_TEST = os.getenv("HAIZFLOW_SMOKE_TEST") == "1"

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=not _SMOKE_TEST)
APP_DATA_DIR = str(app_data_dir())
load_dotenv(dotenv_path=os.path.join(APP_DATA_DIR, ".env"), override=not _SMOKE_TEST)
APP_DATA_DIR = str(app_data_dir())

INSTALL_ROOT = str(install_root())
RUNTIME_DATA_DIR = str(runtime_data_dir())
STORAGE_DIR = str(storage_dir())
CACHE_DIR = str(cache_dir())
LOGS_DIR = str(logs_dir())
MODELS_DIR = str(models_dir())

PORT = int(os.getenv("PORT", 8000))
BIN_DIR = str(bin_dir())
if os.path.exists(BIN_DIR):
    os.environ["PATH"] = BIN_DIR + os.path.pathsep + os.environ["PATH"]

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_MODEL_REPO = WHISPER_REPO
WHISPER_MODEL_REVISION = WHISPER_REVISION
WHISPER_MODELS_DIR = os.path.join(MODELS_DIR, "whisper")
HYMT2_MODEL = HYMT2_GPU_REPO
HYMT2_MODEL_REVISION = HYMT2_GPU_REVISION
HYMT2_CPU_MODEL_REPO = HYMT2_CPU_REPO
HYMT2_CPU_MODEL_REVISION = HYMT2_CPU_REVISION
HYMT2_CPU_MODEL_FILE = HYMT2_CPU_FILE
# Edge's consumer speech endpoint is substantially more reliable with one
# WebSocket at a time. Advanced users can still override this, but production
# defaults preserve the sequential behavior of the stable pipeline.
TTS_MAX_CONCURRENCY = max(1, min(4, int(os.getenv("TTS_MAX_CONCURRENCY", "1"))))


def _bounded_seconds(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


# These are inactivity limits. Long CPU inference remains valid while the
# worker continues to emit progress or model-loading status events.
HYMT2_WARM_TIMEOUT_SECONDS = _bounded_seconds("HYMT2_WARM_TIMEOUT_SECONDS", 1800, 300, 7200)
HYMT2_REQUEST_TIMEOUT_SECONDS = _bounded_seconds("HYMT2_REQUEST_TIMEOUT_SECONDS", 3600, 600, 14400)


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


_PORTABLE_HOME_SELECTED = bool(os.getenv("HAIZFLOW_HOME"))


def _cache_override(name: str) -> str | None:
    # A selected application home is a hard containment boundary. Ignore
    # machine-wide cache variables that may point back to the system drive.
    return None if _PORTABLE_HOME_SELECTED else os.getenv(name)


HF_HOME = _resolve_runtime_path(_cache_override("HF_HOME"), os.path.join(CACHE_DIR, "huggingface"))
TORCH_HOME = _resolve_runtime_path(_cache_override("TORCH_HOME"), os.path.join(CACHE_DIR, "torch"))
PIP_CACHE_DIR = _resolve_runtime_path(_cache_override("PIP_CACHE_DIR"), os.path.join(CACHE_DIR, "pip"))
UV_CACHE_DIR = _resolve_runtime_path(_cache_override("UV_CACHE_DIR"), os.path.join(CACHE_DIR, "uv"))
TMP_DIR = _resolve_runtime_path(_cache_override("HAIZFLOW_TMP_DIR"), os.path.join(APP_DATA_DIR, "tmp"))

# Third-party libraries otherwise scatter caches under %LOCALAPPDATA%,
# %APPDATA%, %USERPROFILE%\.cache, and the system temporary directory. Set
# these before Qt/Torch/WhisperX are imported so one installer-selected root
# owns every HaizFlow runtime artifact.
_RUNTIME_ENVIRONMENT = {
    "HF_HOME": HF_HOME,
    "HF_HUB_CACHE": os.path.join(HF_HOME, "hub"),
    "HF_ASSETS_CACHE": os.path.join(HF_HOME, "assets"),
    "HF_DATASETS_CACHE": os.path.join(HF_HOME, "datasets"),
    "TORCH_HOME": TORCH_HOME,
    "TORCH_EXTENSIONS_DIR": os.path.join(TORCH_HOME, "extensions"),
    "PIP_CACHE_DIR": PIP_CACHE_DIR,
    "UV_CACHE_DIR": UV_CACHE_DIR,
    "XDG_CACHE_HOME": CACHE_DIR,
    "NUMBA_CACHE_DIR": os.path.join(CACHE_DIR, "numba"),
    "MPLCONFIGDIR": os.path.join(CACHE_DIR, "matplotlib"),
    "CUDA_CACHE_PATH": os.path.join(CACHE_DIR, "nvidia", "compute-cache"),
    "TRITON_CACHE_DIR": os.path.join(CACHE_DIR, "triton"),
    "QML_DISK_CACHE_PATH": os.path.join(CACHE_DIR, "qt", "qmlcache"),
    "LOCALAPPDATA": os.path.join(CACHE_DIR, "windows", "local"),
    "APPDATA": os.path.join(APP_DATA_DIR, "config", "roaming"),
    "TMP": TMP_DIR,
    "TEMP": TMP_DIR,
}
os.environ.update(_RUNTIME_ENVIRONMENT)

# Project-owned data is created inside the selected project. This global path
# remains only as a read-once migration location for older installations.
for directory in (
    RUNTIME_DATA_DIR,
    CACHE_DIR,
    LOGS_DIR,
    MODELS_DIR,
    WHISPER_MODELS_DIR,
    HF_HOME,
    TORCH_HOME,
    PIP_CACHE_DIR,
    UV_CACHE_DIR,
    TMP_DIR,
    *_RUNTIME_ENVIRONMENT.values(),
):
    os.makedirs(directory, exist_ok=True)

LEGACY_VIDEO_WORKSPACES_DIR = STORAGE_DIR
