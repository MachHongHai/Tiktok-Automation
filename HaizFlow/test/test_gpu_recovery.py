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

from haizflow.pipeline import process_job
from haizflow.services import translation


class GpuRecoveryTests(unittest.TestCase):
    def test_recovery_checkpoint_is_not_a_pause_resume_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "timeline.wav"
            artifact.write_bytes(b"audio")
            job = SimpleNamespace(
                checkpoints={"timeline": "signature"},
                resume_step="",
                runtime_recovery_step="rendering",
            )

            self.assertFalse(process_job._checkpoint_valid(job, "timeline", "signature", [str(artifact)]))
            self.assertTrue(process_job._recovery_checkpoint_valid(job, "timeline", "signature", [str(artifact)]))

    def test_gpu_preflight_stops_before_a_new_stage_when_power_is_lost(self):
        profile = SimpleNamespace(cuda_available=True)
        unavailable = SimpleNamespace(cuda_available=True, ac_powered=False)
        with (
            mock.patch.object(process_job, "runtime_profile", return_value=profile),
            mock.patch.object(process_job, "detect_hardware_capabilities", return_value=unavailable),
        ):
            with self.assertRaises(process_job.GpuRuntimeUnavailable):
                process_job._ensure_gpu_available("translation")

    def test_gpu_failure_switches_one_job_to_cpu_once(self):
        job = SimpleNamespace(gpu_recovery_attempted=False)
        profile = SimpleNamespace(cuda_available=True)
        with (
            mock.patch.object(process_job, "get_job", return_value=job),
            mock.patch.object(process_job, "runtime_profile", return_value=profile),
            mock.patch.object(process_job, "update_job") as update_job,
            mock.patch.object(process_job, "log_to_job"),
            mock.patch("haizflow.pipeline.transcribe.release_warm_whisperx_model"),
            mock.patch.object(process_job, "shutdown_hymt2_worker"),
            mock.patch.object(process_job, "configure_processing_device") as configure,
        ):
            recovered = process_job._recover_gpu_to_cpu(
                "video-1",
                "translating",
                RuntimeError("CUDA driver lost"),
            )

        self.assertTrue(recovered)
        configure.assert_called_once_with("cpu")
        self.assertTrue(update_job.call_args.kwargs["gpu_recovery_attempted"])
        self.assertEqual(update_job.call_args.kwargs["runtime_recovery_step"], "translating")

    def test_second_gpu_failure_is_not_retried_automatically(self):
        job = SimpleNamespace(gpu_recovery_attempted=True)
        with mock.patch.object(process_job, "get_job", return_value=job):
            self.assertFalse(
                process_job._recover_gpu_to_cpu("video-1", "translating", RuntimeError("CUDA device lost"))
            )

    def test_windows_commit_limit_is_reported_without_hiding_it_behind_cpu_recovery(self):
        profile = SimpleNamespace(cuda_available=True)
        with mock.patch.object(process_job, "runtime_profile", return_value=profile):
            self.assertFalse(
                process_job._is_gpu_runtime_failure(
                    OSError("The paging file is too small for this operation to complete. (os error 1455)")
                )
            )

    def test_native_torch_crash_is_reported_without_automatic_fallback(self):
        profile = SimpleNamespace(cuda_available=True)
        with mock.patch.object(process_job, "runtime_profile", return_value=profile):
            self.assertFalse(
                process_job._is_gpu_runtime_failure(
                    RuntimeError("Native Torch crash (0xC0000005) while loading HY-MT2")
                )
            )

    def test_native_worker_exit_reports_hex_stage_and_diagnostic_file(self):
        worker_output = [
            '{"event":"diagnostic","detail":{"stage":"weights_load_start"}}\n',
            "Windows fatal exception: access violation\n",
        ]
        message = translation._format_worker_exit(
            3221225477,
            "model warm-up",
            worker_output,
            r"D:\\HaizFlowData\\logs\\hymt2-workers\\worker.log",
        )

        self.assertIn("0xC0000005", message)
        self.assertIn("weights_load_start", message)
        self.assertIn("worker.log", message)
        self.assertIn("access violation", message)


if __name__ == "__main__":
    unittest.main()
