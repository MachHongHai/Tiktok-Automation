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


def install_root() -> Path:
    """Directory selected for the application installation.

    Source builds use the repository application root. Frozen builds use the
    directory containing the executable. An installer may set the override
    explicitly before launching HaizFlow.
    """
    override = os.getenv("HAIZFLOW_INSTALL_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return project_root()


def app_data_dir() -> Path:
    override = os.getenv("HAIZFLOW_HOME") or os.getenv("APP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    # Portable-by-default layout: installer location determines where every
    # HaizFlow-owned mutable file is written. This also prevents silent writes
    # to the Windows system drive when the user installs on another drive.
    return install_root() / "runtime"


def runtime_data_dir() -> Path:
    """All mutable app-level data: settings, diagnostics, model caches, and project index."""
    override = os.getenv("RUNTIME_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        candidate = path.resolve() if path.is_absolute() else (app_data_dir() / path).resolve()
        home_override = os.getenv("HAIZFLOW_HOME")
        if (
            home_override
            and os.getenv("HAIZFLOW_SMOKE_TEST") != "1"
            and not candidate.is_relative_to(Path(home_override).expanduser().resolve())
        ):
            return app_data_dir() / "data"
        return candidate
    return app_data_dir() / "data"


def legacy_runtime_data_dir() -> Path:
    """Source-mode data directory used by versions before offline storage separation."""
    return project_root() / "data"


def models_dir() -> Path:
    override = os.getenv("MODELS_DIR")
    if override:
        path = Path(override).expanduser()
        candidate = path.resolve() if path.is_absolute() else (app_data_dir() / path).resolve()
        home_override = os.getenv("HAIZFLOW_HOME")
        if home_override and not candidate.is_relative_to(Path(home_override).expanduser().resolve()):
            return app_data_dir() / "models"
        return candidate
    return app_data_dir() / "models"


def storage_dir() -> Path:
    """Legacy pre-project-first video workspace location, retained for migration."""
    # Historical releases called processing records "jobs" and stored them in
    # this directory. The literal path must remain readable until migration.
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
