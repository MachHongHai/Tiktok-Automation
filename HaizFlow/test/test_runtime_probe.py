import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.core import runtime_probe


class RuntimeProbeTests(unittest.TestCase):
    def test_smoke_runtime_override_cannot_be_replaced_by_dotenv(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(SRC)
            environment["HAIZFLOW_SMOKE_TEST"] = "1"
            environment["RUNTIME_DATA_DIR"] = temporary
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from haizflow.config import RUNTIME_DATA_DIR; print(RUNTIME_DATA_DIR)",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(Path(completed.stdout.strip()).resolve(), Path(temporary).resolve())

    def test_native_windows_exit_codes_are_classified(self):
        self.assertIn("CPU instruction", runtime_probe._native_exit_message(0xC000001D))
        self.assertIn("DLL", runtime_probe._native_exit_message(0xC0000135))
        self.assertIn("commit", runtime_probe._native_exit_message(0xC000012D))

    def test_parent_parses_probe_payload_from_noisy_output(self):
        payload = {
            "event": "runtime_probe",
            "device": "cpu",
            "ok": True,
            "details": {"torch": "2.8.0"},
            "errors": [],
            "warnings": ["optional decoder"],
        }
        completed = subprocess.CompletedProcess(
            args=["probe"],
            returncode=0,
            stdout="native warning\n" + json.dumps(payload) + "\n",
            stderr="",
        )
        with mock.patch.object(runtime_probe.subprocess, "run", return_value=completed):
            result = runtime_probe.probe_runtime("cpu")

        self.assertTrue(result.ok)
        self.assertEqual(result.details["torch"], "2.8.0")
        self.assertEqual(result.warnings, ("optional decoder",))

    def test_parent_preserves_native_crash_diagnostics(self):
        completed = subprocess.CompletedProcess(
            args=["probe"],
            returncode=-1073741819,
            stdout="",
            stderr="native loader stopped",
        )
        with mock.patch.object(runtime_probe.subprocess, "run", return_value=completed):
            result = runtime_probe.probe_runtime("gpu")

        self.assertFalse(result.ok)
        self.assertIn("access violation", result.message)
        self.assertIn("native loader stopped", result.message)


if __name__ == "__main__":
    unittest.main()
