import os
import sys
from pathlib import Path

APP_NAME = "AutoDubVideoLocal"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def backend_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return backend_dir().parent


def app_data_dir() -> Path:
    override = os.getenv("APP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if is_frozen():
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME

    return project_root()


def storage_dir() -> Path:
    override = os.getenv("STORAGE_DIR")
    if override:
        path = Path(override).expanduser()
        return path.resolve() if path.is_absolute() else (backend_dir() / path).resolve()

    return app_data_dir() / "storage"


def cache_dir() -> Path:
    return app_data_dir() / ".cache"


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def bin_dir() -> Path:
    override = os.getenv("BIN_DIR")
    if override:
        return Path(override).expanduser().resolve()

    candidates = [
        backend_dir() / "bin",
        project_root() / "runtime" / "bin",
        project_root() / "bin",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()
