import json
import os
from pathlib import Path

from autodub.config import RUNTIME_DATA_DIR


SETTINGS_PATH = Path(RUNTIME_DATA_DIR) / "desktop-settings.json"
DEFAULT_SETTINGS = {
    "theme": "dark",
    "language": "en",
}


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
            saved = json.load(file)
        if isinstance(saved, dict):
            settings.update({key: saved[key] for key in DEFAULT_SETTINGS if key in saved})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return settings


def save_settings(settings: dict) -> dict:
    normalized = {
        "theme": settings.get("theme") if settings.get("theme") in {"dark", "light"} else "dark",
        "language": settings.get("language") if settings.get("language") in {"en", "vi"} else "en",
    }
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = SETTINGS_PATH.with_suffix(".tmp")
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
    os.replace(temporary_path, SETTINGS_PATH)
    return normalized


def reset_settings() -> dict:
    return save_settings(DEFAULT_SETTINGS)
