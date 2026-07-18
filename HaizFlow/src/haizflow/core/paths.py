import os
import sys
from pathlib import Path

APP_NAME = "HaizFlow"


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

    base = Path(os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"))
    return base / APP_NAME


def runtime_data_dir() -> Path:
    """All mutable app-level data: settings, diagnostics, model caches, and project index."""
    override = os.getenv("RUNTIME_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        return path.resolve() if path.is_absolute() else (app_data_dir() / path).resolve()
    return app_data_dir() / "data"


def legacy_runtime_data_dir() -> Path:
    """Source-mode data directory used by versions before offline storage separation."""
    return project_root() / "data"


def storage_dir() -> Path:
    """Legacy pre-project-first video workspace location, retained for migration."""
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
