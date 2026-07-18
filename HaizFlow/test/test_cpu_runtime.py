import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.core import hardware
from haizflow.desktop import qml_controller
from haizflow.pipeline import audio_separation
from haizflow.services import hymt2_worker
from haizflow.services import desktop_settings
from haizflow.utils import ffmpeg


class CpuRuntimeTests(unittest.TestCase):
    def tearDown(self):
        hardware.clear_runtime_profile_cache()
        ffmpeg.available_video_encoders.cache_clear()
        ffmpeg._encoder_works.cache_clear()

    def _profile(
        self,
        *,
        cuda=False,
        vram_gib=8,
        ram_gib=16,
        cpu_count=12,
        preference="gpu",
        bf16=True,
    ):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.dict(
                hardware.os.environ,
                {"HAIZFLOW_PROCESSING_DEVICE": preference, "HAIZFLOW_FORCE_CPU": ""},
                clear=False,
            ),
            mock.patch.object(hardware, "_cuda_details", return_value=(cuda, "Test GPU" if cuda else "")),
            mock.patch.object(
                hardware,
                "_cuda_precision_details",
                return_value=((8, 9), bf16) if cuda else ((0, 0), False),
            ),
            mock.patch.object(hardware, "_cuda_memory_bytes", return_value=vram_gib * 1024**3),
            mock.patch.object(hardware, "_cuda_free_memory_bytes", return_value=vram_gib * 1024**3),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=ram_gib * 1024**3),
            mock.patch.object(hardware.os, "cpu_count", return_value=cpu_count),
        ):
            return hardware.runtime_profile()

    def test_hardware_profiles_are_conservative_on_cpu(self):
        balanced = self._profile(ram_gib=32, cpu_count=16)
        self.assertEqual(balanced.key, "cpu_balanced")
        self.assertEqual(balanced.whisper_batch_size, 4)
        self.assertEqual(balanced.cpu_threads, 8)
        self.assertTrue(balanced.warm_whisper_on_startup)
        self.assertFalse(balanced.warm_hymt2_on_startup)

        low_memory = self._profile(ram_gib=10, cpu_count=8)
        self.assertEqual(low_memory.key, "cpu_low_memory")
        self.assertEqual(low_memory.whisper_batch_size, 2)
        self.assertEqual(low_memory.cpu_threads, 4)

        minimum = self._profile(ram_gib=6, cpu_count=8)
        self.assertEqual(minimum.key, "cpu_minimum")
        self.assertEqual(minimum.whisper_batch_size, 1)
        self.assertFalse(minimum.warm_whisper_on_startup)

    def test_cuda_profile_keeps_existing_fast_path(self):
        profile = self._profile(cuda=True, vram_gib=12, ram_gib=16, cpu_count=12)
        self.assertEqual(profile.key, "cuda")
        self.assertEqual(profile.hymt2_backend, "transformers")
        self.assertEqual(profile.whisper_batch_size, 16)
        self.assertTrue(profile.warm_hymt2_on_startup)
        self.assertEqual(profile.hymt2_dtype, "bfloat16")

        marketed_eight_gib = self._profile(cuda=True, vram_gib=8, ram_gib=16, cpu_count=12)
        self.assertEqual(marketed_eight_gib.key, "cuda_low_memory")
        self.assertEqual(marketed_eight_gib.hymt2_backend, "transformers")
        self.assertTrue(marketed_eight_gib.warm_hymt2_on_startup)

        older_gpu = self._profile(cuda=True, vram_gib=8, ram_gib=16, cpu_count=12, bf16=False)
        self.assertEqual(older_gpu.hymt2_dtype, "float16")

    def test_device_preference_and_vram_select_the_expected_backend(self):
        forced_cpu = self._profile(cuda=True, vram_gib=8, preference="cpu")
        self.assertFalse(forced_cpu.cuda_available)
        self.assertEqual(forced_cpu.hymt2_backend, "llama_cpp")

        low_vram_gpu = self._profile(cuda=True, vram_gib=6, preference="gpu")
        self.assertFalse(low_vram_gpu.cuda_available)
        self.assertEqual(low_vram_gpu.key, "cpu_balanced")

        unsupported_gpu = self._profile(cuda=True, vram_gib=4, preference="gpu")
        self.assertFalse(unsupported_gpu.cuda_available)

    def test_gpu_requires_safe_total_and_free_memory_before_auto_selecting_it(self):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.object(hardware, "_cuda_details", return_value=(True, "Test GPU")),
            mock.patch.object(hardware, "_cuda_precision_details", return_value=((8, 9), True)),
            mock.patch.object(hardware, "_cuda_memory_bytes", return_value=8 * 1024**3),
            mock.patch.object(hardware, "_cuda_free_memory_bytes", return_value=4 * 1024**3),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware.os, "cpu_count", return_value=8),
        ):
            compatible, message = hardware.validate_processing_device("gpu")
            profile = hardware.runtime_profile()

        self.assertFalse(compatible)
        self.assertIn("free VRAM", message)
        self.assertTrue(profile.is_cpu_only)

    def test_device_validation_reports_missing_gpu(self):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.object(hardware, "_cuda_details", return_value=(False, "")),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware.os, "cpu_count", return_value=8),
        ):
            compatible, message = hardware.validate_processing_device("gpu")
        self.assertFalse(compatible)
        self.assertIn("not detected", message)

    def test_invalid_gpu_setting_warns_and_is_rejected_without_saving(self):
        controller = SimpleNamespace(
            _settings_processing_device="cpu",
            _is_processing=False,
            _device_switching=False,
            _pipeline_is_active=lambda: False,
        )
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.object(hardware, "_cuda_details", return_value=(True, "Low VRAM GPU")),
            mock.patch.object(hardware, "_cuda_memory_bytes", return_value=4 * 1024**3),
            mock.patch.object(hardware, "_cuda_free_memory_bytes", return_value=4 * 1024**3),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware.os, "cpu_count", return_value=8),
            mock.patch.object(qml_controller.QMessageBox, "warning") as warning,
        ):
            applied = qml_controller.HaizFlowController.applySettings(controller, "dark", "en", "gpu")

        self.assertFalse(applied)
        warning.assert_called_once()

    def test_device_change_is_deferred_while_a_video_is_processing(self):
        signal = mock.Mock()
        switch_runtime = mock.Mock()
        controller = SimpleNamespace(
            _settings_processing_device="gpu",
            _settings_theme="dark",
            _settings_language="en",
            _processing_device_origin="manual",
            _pending_processing_device="",
            _device_switching=False,
            _pipeline_is_active=lambda: True,
            settingsChanged=signal,
            languageOptionsChanged=signal,
            statusMessageChanged=signal,
            _switch_processing_device=switch_runtime,
        )
        saved = {
            "theme": "dark",
            "language": "en",
            "processing_device": "cpu",
            "processing_device_origin": "manual",
        }
        with (
            mock.patch.object(qml_controller, "validate_processing_device", return_value=(True, "CPU ready")),
            mock.patch.object(qml_controller.desktop_settings, "save_settings", return_value=saved),
        ):
            applied = qml_controller.HaizFlowController.applySettings(controller, "dark", "en", "cpu")

        self.assertTrue(applied)
        self.assertEqual(controller._settings_processing_device, "cpu")
        self.assertEqual(controller._pending_processing_device, "cpu")
        self.assertIn("current video", controller._status_message)
        switch_runtime.assert_not_called()

    def test_desktop_settings_persist_processing_device(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = desktop_settings.SETTINGS_PATH
            desktop_settings.SETTINGS_PATH = Path(temp_dir) / "desktop-settings.json"
            try:
                saved = desktop_settings.save_settings(
                    {"theme": "dark", "language": "en", "processing_device": "cpu"}
                )
                loaded = desktop_settings.load_settings()
            finally:
                desktop_settings.SETTINGS_PATH = original_path
        self.assertEqual(saved["processing_device"], "cpu")
        self.assertEqual(loaded["processing_device"], "cpu")

    def test_legacy_auto_device_setting_migrates_to_detected_cpu_or_gpu(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "desktop-settings.json"
            settings_path.write_text(
                '{"theme": "dark", "language": "en", "processing_device": "auto"}',
                encoding="utf-8",
            )
            original_path = desktop_settings.SETTINGS_PATH
            desktop_settings.SETTINGS_PATH = settings_path
            try:
                loaded = desktop_settings.load_settings()
                persisted = settings_path.read_text(encoding="utf-8")
            finally:
                desktop_settings.SETTINGS_PATH = original_path

        self.assertEqual(loaded["processing_device"], "cpu")
        self.assertEqual(loaded["processing_device_origin"], "detected")
        self.assertNotIn('"auto"', persisted)

    def test_battery_power_rejects_gpu_and_recommends_cpu(self):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.object(hardware, "_cuda_details", return_value=(True, "Laptop GPU")),
            mock.patch.object(hardware, "_cuda_precision_details", return_value=((8, 9), True)),
            mock.patch.object(hardware, "_cuda_memory_bytes", return_value=8 * 1024**3),
            mock.patch.object(hardware, "_cuda_free_memory_bytes", return_value=7 * 1024**3),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware, "_power_status", return_value=(False, 72)),
            mock.patch.object(hardware.os, "cpu_count", return_value=8),
        ):
            capabilities = hardware.detect_hardware_capabilities()
            compatible, message = hardware.validate_processing_device("gpu", capabilities)
            recommended = hardware.recommended_processing_device(capabilities)

        self.assertFalse(compatible)
        self.assertIn("AC power", message)
        self.assertEqual(recommended, "cpu")

    def test_hymt2_gguf_uses_chat_completion_and_plain_translation(self):
        class FakeLlama:
            def __init__(self):
                self.requests = []

            def create_chat_completion(self, **kwargs):
                self.requests.append(kwargs)
                return {"choices": [{"message": {"content": "Xin chao"}}]}

        model = FakeLlama()
        result = hymt2_worker._translate_prompt_batch(
            model,
            None,
            None,
            "cpu-gguf",
            ["Translate this"],
            ["Hello"],
        )
        self.assertEqual(result, ["Xin chao"])
        self.assertEqual(model.requests[0]["messages"][0]["content"], "Translate this")
        self.assertLessEqual(model.requests[0]["max_tokens"], 24)
        self.assertEqual(model.requests[0]["temperature"], 0.0)

    def test_hymt2_resolves_an_installed_transformers_snapshot_without_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "snapshot"
            snapshot.mkdir()
            for filename in ("config.json", "tokenizer_config.json", "tokenizer.json", "model.safetensors"):
                (snapshot / filename).write_bytes(b"installed")

            with (
                mock.patch("huggingface_hub.snapshot_download", return_value=str(snapshot)) as resolve_snapshot,
                mock.patch("haizflow.core.model_integrity.verify_gpu_model", return_value=snapshot),
            ):
                model_source, local_files_only = hymt2_worker._local_transformers_model_source(
                    "tencent/Hy-MT2-1.8B"
                )

        self.assertEqual(model_source, str(snapshot.resolve()))
        self.assertTrue(local_files_only)
        from haizflow.config import HF_HOME

        resolve_snapshot.assert_called_once_with(
            repo_id="tencent/Hy-MT2-1.8B",
            revision="9a341cd1b679d3efd23b46e847b01745a71ed792",
            cache_dir=str(Path(HF_HOME) / "hub"),
            local_files_only=True,
        )

    def test_hymt2_rejects_an_incomplete_sharded_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "snapshot"
            snapshot.mkdir()
            for filename in ("config.json", "tokenizer_config.json", "tokenizer.json"):
                (snapshot / filename).write_text("{}", encoding="utf-8")
            (snapshot / "model.safetensors.index.json").write_text(
                '{"weight_map":{"layer":"missing-00001-of-00002.safetensors"}}',
                encoding="utf-8",
            )
            self.assertFalse(hymt2_worker._transformers_snapshot_complete(snapshot))

            (snapshot / "missing-00001-of-00002.safetensors").write_bytes(b"weights")
            self.assertTrue(hymt2_worker._transformers_snapshot_complete(snapshot))

    def test_hymt2_torch_threading_is_configured_only_once(self):
        fake_torch = SimpleNamespace(
            set_num_threads=mock.Mock(),
            set_num_interop_threads=mock.Mock(),
        )
        original_configured = hymt2_worker._TORCH_THREADING_CONFIGURED
        hymt2_worker._TORCH_THREADING_CONFIGURED = False
        try:
            hymt2_worker._configure_torch_threading(fake_torch)
            hymt2_worker._configure_torch_threading(fake_torch)
        finally:
            hymt2_worker._TORCH_THREADING_CONFIGURED = original_configured

        fake_torch.set_num_threads.assert_called_once_with(1)
        fake_torch.set_num_interop_threads.assert_called_once_with(1)

    def test_hymt2_keeps_existing_interop_pool_when_torch_already_started(self):
        fake_torch = SimpleNamespace(
            set_num_threads=mock.Mock(),
            set_num_interop_threads=mock.Mock(
                side_effect=RuntimeError(
                    "Error: cannot set number of interop threads after parallel work has started"
                )
            ),
        )
        original_configured = hymt2_worker._TORCH_THREADING_CONFIGURED
        hymt2_worker._TORCH_THREADING_CONFIGURED = False
        try:
            hymt2_worker._configure_torch_threading(fake_torch)
            self.assertTrue(hymt2_worker._TORCH_THREADING_CONFIGURED)
        finally:
            hymt2_worker._TORCH_THREADING_CONFIGURED = original_configured

    def test_encoder_selection_probes_hardware_then_falls_back(self):
        cuda_profile = SimpleNamespace(cuda_available=True)
        with (
            mock.patch.object(ffmpeg, "runtime_profile", return_value=cuda_profile),
            mock.patch.object(ffmpeg, "_encoder_works", side_effect=lambda name: name == "h264_nvenc"),
        ):
            encoder, _args = ffmpeg.preferred_video_encoder()
        self.assertEqual(encoder, "h264_nvenc")

        cpu_profile = SimpleNamespace(cuda_available=False)
        with (
            mock.patch.object(ffmpeg, "runtime_profile", return_value=cpu_profile),
            mock.patch.object(ffmpeg, "_encoder_works", return_value=False),
        ):
            encoder, args = ffmpeg.preferred_video_encoder()
        self.assertEqual(encoder, "libx264")
        self.assertIn("veryfast", args)

    def test_demucs_cpu_profile_limits_parallel_work(self):
        captured = {}

        class FakeProcess:
            returncode = 0

            def __init__(self, command, **_kwargs):
                captured["command"] = command

            def communicate(self):
                return "", ""

        profile = SimpleNamespace(cuda_available=False, key="cpu_low_memory", cpu_threads=4)
        fake_walk = [("out", [], ["vocals.wav", "no_vocals.wav"])]
        with (
            mock.patch.object(audio_separation, "runtime_profile", return_value=profile),
            mock.patch.object(audio_separation.subprocess, "Popen", FakeProcess),
            mock.patch.object(audio_separation.os, "walk", return_value=fake_walk),
            mock.patch.object(audio_separation.os.path, "exists", return_value=True),
            mock.patch.object(audio_separation, "register_process"),
            mock.patch.object(audio_separation, "unregister_process"),
            mock.patch.object(audio_separation, "check_cancellation"),
            mock.patch.object(audio_separation, "log_to_job"),
        ):
            audio_separation.separate_audio("audio.wav", "out", "job")

        command = captured["command"]
        self.assertEqual(command[command.index("-j") + 1], "1")
        self.assertEqual(command[command.index("-d") + 1], "cpu")
        self.assertIn("--segment", command)


if __name__ == "__main__":
    unittest.main()
