import os
import sys
from pathlib import Path

APP_NAME = "AutoDubVideoLocal"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return project_root()


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def source_root() -> Path:
    return package_root().parent


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return source_root().parent


def app_data_dir() -> Path:
    override = os.getenv("APP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if is_frozen():
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME

    return project_root()


def runtime_data_dir() -> Path:
    """All mutable runtime data: jobs, logs, model caches, and downloaded models."""
    override = os.getenv("RUNTIME_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        return path.resolve() if path.is_absolute() else (project_root() / path).resolve()
    return app_data_dir() / "data"


def storage_dir() -> Path:
    """Compatibility name for the job data directory."""
    return runtime_data_dir() / "jobs"


def cache_dir() -> Path:
    return runtime_data_dir() / "cache"


def logs_dir() -> Path:
    return runtime_data_dir() / "logs"


def bin_dir() -> Path:
    override = os.getenv("BIN_DIR")
    if override:
        return Path(override).expanduser().resolve()

    candidates = [
        project_root() / "runtime" / "bin",
        project_root() / "bin",
        bundle_root() / "bin",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()

