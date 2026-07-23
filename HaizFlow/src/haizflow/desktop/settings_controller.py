"""Persistent desktop settings operations kept outside the QML facade."""

from __future__ import annotations

from haizflow.desktop.localization import QMessageBox, _set_ui_language
from haizflow.core.hardware import (
    clear_runtime_profile_cache,
    detect_hardware_capabilities,
    recommended_processing_device,
    validate_processing_device,
)
from haizflow.services import desktop_settings


class SettingsController:
    def __init__(self, host):
        self._host = host

    def apply(self, theme, language, processing_device) -> bool:
        host = self._host
        processing_device = str(processing_device).lower()
        pipeline_active = host._pipeline_is_active()
        if processing_device != host._settings_processing_device and not (pipeline_active or host._device_switching):
            clear_runtime_profile_cache()
        compatible, compatibility_message = validate_processing_device(processing_device)
        if not compatible:
            QMessageBox.warning(None, "Processing device", compatibility_message)
            return False
        device_changed = processing_device != host._settings_processing_device
        try:
            settings = desktop_settings.save_settings(
                {
                    "theme": theme,
                    "language": language,
                    "processing_device": processing_device,
                    "processing_device_origin": "manual",
                }
            )
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot save settings: {exc}")
            return False
        host._settings_theme = settings["theme"]
        host._settings_language = settings["language"]
        host._settings_processing_device = settings["processing_device"]
        host._processing_device_origin = settings["processing_device_origin"]
        _set_ui_language(host._settings_language)
        if device_changed and (pipeline_active or host._device_switching):
            host._pending_processing_device = host._settings_processing_device
            host._status_message = "Settings applied. The current video keeps its processing device."
        else:
            host._status_message = "Settings applied"
        host.settingsChanged.emit()
        host.languageOptionsChanged.emit()
        host.statusMessageChanged.emit()
        if device_changed and not (pipeline_active or host._device_switching):
            host._switch_processing_device(host._settings_processing_device)
        return True

    def reset(self) -> None:
        host = self._host
        pipeline_active = host._pipeline_is_active()
        try:
            settings = desktop_settings.reset_settings()
            settings["processing_device"] = recommended_processing_device(detect_hardware_capabilities())
            settings["processing_device_origin"] = "detected"
            settings = desktop_settings.save_settings(settings)
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot restore defaults: {exc}")
            return
        host._settings_theme = settings["theme"]
        host._settings_language = settings["language"]
        _set_ui_language(host._settings_language)
        device_changed = settings["processing_device"] != host._settings_processing_device
        host._settings_processing_device = settings["processing_device"]
        host._processing_device_origin = settings["processing_device_origin"]
        if device_changed and (pipeline_active or host._device_switching):
            host._pending_processing_device = host._settings_processing_device
            host._status_message = "Settings reset. The processing device changes after the current video."
        else:
            host._status_message = "Settings reset to defaults"
        host.settingsChanged.emit()
        host.languageOptionsChanged.emit()
        host.statusMessageChanged.emit()
        if device_changed and not (pipeline_active or host._device_switching):
            host._switch_processing_device(host._settings_processing_device)
