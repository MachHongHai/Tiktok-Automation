"""Runtime, model warm-up, shutdown, and hardware-device orchestration."""

from __future__ import annotations

import threading

from haizflow.desktop.localization import QMessageBox
from haizflow.core.events import unsubscribe_log
from haizflow.core.hardware import (
    configure_processing_device, detect_hardware_capabilities, processing_device_preference,
    recommended_processing_device, runtime_profile, validate_processing_device,
)
from haizflow.core.runtime_probe import probe_runtime
from haizflow.pipeline.process_registry import pause_video
from haizflow.services import desktop_settings, video_store
from haizflow.services.translation import shutdown_hymt2_worker, warm_hymt2_worker


class RuntimeDeviceController:
    """Owns runtime transitions; the QML singleton remains the stable facade."""

    def __init__(self, host, *, unsubscribe=None, pause=None, shutdown_translation=None, detect_hardware=None):
        self._host = host
        self._unsubscribe = unsubscribe or unsubscribe_log
        self._pause = pause or pause_video
        self._shutdown_translation = shutdown_translation or shutdown_hymt2_worker
        self._detect_hardware = detect_hardware or detect_hardware_capabilities

    def _confirm_application_close(self) -> bool:
        host = self._host
        background_work = (
            host._processing_queue.has_work
            or host._url_importer.busy
            or host._channel_importer.busy
            or getattr(host, "_media_import_busy", False)
        )
        if not background_work:
            host._close_confirmed = True
            return True
        answer = QMessageBox.question(
            None,
            "Exit HaizFlow",
            "HaizFlow is still processing or downloading media.\n\n"
            "Exit now? The active video will be paused, active downloads will be cancelled, "
            "and queued videos will remain available for later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        host._close_confirmed = answer == QMessageBox.StandardButton.Yes
        return host._close_confirmed
    def shutdown(self):
        host = self._host
        if host._shutdown_started:
            return
        host._shutdown_started = True
        host._initial_model_warmup_done.set()
        self._unsubscribe(host._on_video_log)

        active_video_id = host._processing_queue.active_video_id
        active_video = video_store.get_video(active_video_id) if active_video_id else None
        if active_video and active_video.status in {"pending", "processing"}:
            resume_step = active_video.resume_step or active_video.step or "processing"
            if resume_step in {"pending", "queued", "paused"}:
                resume_step = "starting"
            self._pause(active_video_id)
            video_store.update_video(
                active_video_id,
                status="paused",
                error=None,
                step="paused",
                resume_step=resume_step,
                step_detail=f"Paused during application exit ({resume_step})",
                estimated_remaining_seconds=None,
            )
            video_store.log_to_video(
                active_video_id,
                "Application exit requested. Active subprocesses were stopped and the video was paused.",
            )

        for video_id in host._processing_queue.pending_ids():
            queued_video = video_store.get_video(video_id)
            if queued_video and queued_video.status == "pending":
                video_store.update_video(
                    video_id,
                    step="queued",
                    step_detail="Waiting to be started after the application exited",
                )

        host._url_importer.shutdown()
        host._channel_importer.shutdown()
        project_import = getattr(host, "_project_import", None)
        if project_import:
            project_import.shutdown()
        dimension_probe = getattr(self, "_dimension_probe", None)
        if dimension_probe:
            dimension_probe.shutdown()
        queue_stopped = host._processing_queue.shutdown(timeout_seconds=10.0)
        self._shutdown_translation(permanent=True)
        if not queue_stopped:
            queue_stopped = host._processing_queue.shutdown(timeout_seconds=2.0)

        warmup_thread = host._warmup_thread
        if warmup_thread and warmup_thread.is_alive():
            warmup_thread.join(timeout=1.0)
        if queue_stopped and not (warmup_thread and warmup_thread.is_alive()):
            from haizflow.pipeline.transcribe import release_warm_whisperx_model

            release_warm_whisperx_model()
        if getattr(type(host), "_qml_instance", None) is host:
            type(host)._qml_instance = None
    def _warm_models(self):
        host = self._host
        with host._model_runtime_lock:
            host._warm_models_unlocked()
    def _warm_models_at_startup(self):
        host = self._host
        try:
            requested_device = processing_device_preference()
            probe = probe_runtime(requested_device)
            if not probe.ok and requested_device == "gpu":
                cpu_probe = probe_runtime("cpu")
                if cpu_probe.ok:
                    configure_processing_device("cpu")
                    host._active_processing_device = "cpu"
                    host._settings_processing_device = "cpu"
                    host._processing_device_origin = "detected"
                    try:
                        desktop_settings.save_settings(
                            {
                                "theme": host._settings_theme,
                                "language": host._settings_language,
                                "processing_device": "cpu",
                                "processing_device_origin": "detected",
                            }
                        )
                    except OSError:
                        pass
                    host._status_message = f"GPU runtime unavailable; using CPU. {probe.message}"
                    host.settingsChanged.emit()
                    host.hardwareChanged.emit()
                else:
                    host._runtime_probe_error = (
                        f"GPU runtime: {probe.message} CPU runtime: {cpu_probe.message}"
                    )
            elif not probe.ok:
                host._runtime_probe_error = probe.message
            if host._runtime_probe_error:
                host._status_message = f"Model runtime unavailable: {host._runtime_probe_error}"
                host.statusMessageChanged.emit()
                return
            host._warm_models()
        finally:
            host._initial_model_warmup_done.set()
    def _warm_models_unlocked(self):
        host = self._host
        profile = runtime_profile()
        try:
            warmed = []
            if profile.warm_hymt2_on_startup:
                warm_hymt2_worker(host._set_warmup_status)
                warmed.append("HY-MT2")
            if profile.warm_whisper_on_startup:
                from haizflow.pipeline.transcribe import warm_whisperx_model

                warm_whisperx_model()
                warmed.append("WhisperX")
            host._status_message = (
                f"{', '.join(warmed)} ready - {profile.summary}"
                if warmed
                else f"Ready - {profile.summary}"
            )
        except Exception as exc:
            host._status_message = f"Model warm-up unavailable: {exc}"
        host.statusMessageChanged.emit()
    def _switch_processing_device(self, preference: str):
        host = self._host
        host._device_switching = True
        host._status_message = "Switching processing device"
        host.processingChanged.emit()
        host.statusMessageChanged.emit()

        def switch_models():
            try:
                from haizflow.pipeline.transcribe import release_warm_whisperx_model

                probe = probe_runtime(preference)
                if not probe.ok:
                    active_device = host._active_processing_device
                    host._settings_processing_device = active_device
                    host._pending_processing_device = ""
                    try:
                        desktop_settings.save_settings(
                            {
                                "theme": host._settings_theme,
                                "language": host._settings_language,
                                "processing_device": active_device,
                                "processing_device_origin": host._processing_device_origin,
                            }
                        )
                    except OSError:
                        pass
                    host._status_message = f"Cannot switch to {preference.upper()}: {probe.message}"
                    host.settingsChanged.emit()
                    host.statusMessageChanged.emit()
                    return
                with host._model_runtime_lock:
                    self._shutdown_translation()
                    release_warm_whisperx_model()
                    configure_processing_device(preference)
                    host._active_processing_device = preference
                    host._runtime_probe_error = ""
                    if host._pending_processing_device == preference:
                        host._pending_processing_device = ""
                    host._warm_models_unlocked()
                host.settingsChanged.emit()
                host.hardwareChanged.emit()
            except Exception as exc:
                host._status_message = f"Processing device switch failed: {exc}"
                host.statusMessageChanged.emit()
            finally:
                host._device_switching = False
                host.processingChanged.emit()

        threading.Thread(target=switch_models, name="processing-device-switch", daemon=True).start()
    def _pipeline_is_active(self) -> bool:
        host = self._host
        """Return whether a video is currently inside the serial worker."""
        return bool(host._processing_queue.active_video_id)
    def _activate_pending_device_for_next_video(self, video_id: str) -> None:
        host = self._host
        """Switch only between two queued videos, never during a pipeline."""
        preference = host._pending_processing_device
        if preference not in {"cpu", "gpu"}:
            return

        if preference == processing_device_preference():
            host._pending_processing_device = ""
            return

        compatible, message = validate_processing_device(preference)
        if not compatible:
            preference = "cpu"
            host._settings_processing_device = "cpu"
            host._processing_device_origin = "detected"
            try:
                desktop_settings.save_settings(
                    {
                        "theme": host._settings_theme,
                        "language": host._settings_language,
                        "processing_device": "cpu",
                        "processing_device_origin": "detected",
                    }
                )
            except OSError:
                pass
            video_store.log_to_video(video_id, f"Requested GPU runtime is no longer safe: {message} Falling back to CPU.")

        probe = probe_runtime(preference)
        if not probe.ok and preference == "gpu":
            video_store.log_to_video(video_id, f"GPU runtime validation failed: {probe.message} Falling back to CPU.")
            preference = "cpu"
            probe = probe_runtime("cpu")
            host._settings_processing_device = "cpu"
            host._processing_device_origin = "detected"
            try:
                desktop_settings.save_settings(
                    {
                        "theme": host._settings_theme,
                        "language": host._settings_language,
                        "processing_device": "cpu",
                        "processing_device_origin": "detected",
                    }
                )
            except OSError:
                pass
        if not probe.ok:
            host._runtime_probe_error = probe.message
            video_store.log_to_video(video_id, f"Processing runtime validation failed: {probe.message}")
            return

        try:
            from haizflow.pipeline.transcribe import release_warm_whisperx_model

            with host._model_runtime_lock:
                if preference != processing_device_preference():
                    self._shutdown_translation()
                    release_warm_whisperx_model()
                    configure_processing_device(preference)
            host._active_processing_device = preference
            host._runtime_probe_error = ""
            host._pending_processing_device = ""
            video_store.log_to_video(video_id, f"Using the updated {preference.upper()} runtime for this video.")
        except Exception as exc:
            video_store.log_to_video(video_id, f"Could not apply the updated processing device: {exc}")
    def _refresh_live_hardware(self):
        host = self._host
        """Keep Settings telemetry live without changing a pipeline mid-video."""
        if not host._hardware_telemetry_active:
            return
        capabilities = self._detect_hardware()
        recommended_device = recommended_processing_device(capabilities)
        # The pipeline can force a single video onto CPU after a GPU fault. Once
        # the queue is idle, persist that runtime choice so Settings never
        # claims that GPU is active while the app is actually using CPU.
        runtime_fallback_device = processing_device_preference()
        runtime_fallback_pending = (
            not host._pending_processing_device
            and runtime_fallback_device != host._settings_processing_device
        )
        should_fallback_to_cpu = host._settings_processing_device == "gpu" and recommended_device == "cpu"
        should_follow_recommendation = (
            host._processing_device_origin == "detected"
            and recommended_device != host._settings_processing_device
        )
        runtime_needs_switch = runtime_fallback_pending or should_fallback_to_cpu or should_follow_recommendation
        if capabilities != host._hardware_capabilities:
            host._hardware_capabilities = capabilities
            host.hardwareChanged.emit()
        if host._pipeline_is_active():
            return
        if host._pending_processing_device:
            if not host._device_switching:
                host._switch_processing_device(host._pending_processing_device)
            return
        if not runtime_needs_switch or host._device_switching:
            return
        host._apply_detected_processing_device(
            runtime_fallback_device if runtime_fallback_pending else recommended_device
        )
    def setHardwareTelemetryActive(self, active: bool):
        host = self._host
        """Only refresh dynamic telemetry while the Settings dialog needs it."""
        host._hardware_telemetry_active = bool(active)
        if host._hardware_telemetry_active:
            host._refresh_live_hardware()
    def _apply_detected_processing_device(self, device: str):
        host = self._host
        """Persist a safe device chosen from live hardware telemetry."""
        if device not in {"cpu", "gpu"}:
            device = "cpu"
        host._settings_processing_device = device
        host._processing_device_origin = "detected"
        try:
            desktop_settings.save_settings(
                {
                    "theme": host._settings_theme,
                    "language": host._settings_language,
                    "processing_device": device,
                    "processing_device_origin": "detected",
                }
            )
        except OSError:
            pass
        host.settingsChanged.emit()
        host._switch_processing_device(device)
    def _set_warmup_status(self, detail: str):
        host = self._host
        host._status_message = detail
        host.statusMessageChanged.emit()
