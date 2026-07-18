import json
import os
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR


SETTINGS_PATH = Path(RUNTIME_DATA_DIR) / "desktop-settings.json"
DEFAULT_SETTINGS = {
    "theme": "dark",
    "language": "en",
    "processing_device": "cpu",
    "processing_device_origin": "detected",
}


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    migrate_legacy_device = False
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
            saved = json.load(file)
        if isinstance(saved, dict):
            settings.update({key: saved[key] for key in DEFAULT_SETTINGS if key in saved})
            if saved.get("processing_device") == "auto":
                settings["processing_device"] = "cpu"
                settings["processing_device_origin"] = "detected"
                migrate_legacy_device = True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if migrate_legacy_device:
        try:
            save_settings(settings)
        except OSError:
            pass
    return settings


def save_settings(settings: dict) -> dict:
    normalized = {
        "theme": settings.get("theme") if settings.get("theme") in {"dark", "light"} else "dark",
        "language": settings.get("language") if settings.get("language") in {"en", "vi"} else "en",
        "processing_device": (
            settings.get("processing_device")
            if settings.get("processing_device") in {"cpu", "gpu"}
            else "cpu"
        ),
        "processing_device_origin": (
            settings.get("processing_device_origin")
            if settings.get("processing_device_origin") in {"detected", "manual"}
            else "detected"
        ),
    }
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = SETTINGS_PATH.with_suffix(".tmp")
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
    os.replace(temporary_path, SETTINGS_PATH)
    return normalized


def reset_settings() -> dict:
    return save_settings(DEFAULT_SETTINGS)
