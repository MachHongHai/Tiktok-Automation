import os
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from haizflow.desktop.single_instance import SingleInstanceCoordinator, default_server_name


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_default_lock_name_is_stable_and_user_scoped(self):
        self.assertEqual(default_server_name(), default_server_name())
        self.assertRegex(default_server_name(), r"^HaizFlow-[0-9a-f]{16}$")

    def test_second_instance_notifies_the_primary_instance(self):
        server_name = f"HaizFlow-test-{uuid.uuid4().hex}"
        primary = SingleInstanceCoordinator(server_name)
        secondary = SingleInstanceCoordinator(server_name)
        activations = []
        primary.activationRequested.connect(lambda: activations.append(True))
        try:
            self.assertTrue(primary.acquire())
            self.assertFalse(secondary.acquire())
            deadline = time.monotonic() + 2
            while not activations and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertEqual(activations, [True])
        finally:
            secondary.close()
            primary.close()

    def test_lock_and_activation_work_across_processes(self):
        server_name = f"HaizFlow-process-test-{uuid.uuid4().hex}"
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        primary_code = "\n".join(
            (
                "import sys",
                "from PySide6.QtCore import QCoreApplication, QTimer",
                "from haizflow.desktop.single_instance import SingleInstanceCoordinator",
                "app = QCoreApplication([])",
                f"coordinator = SingleInstanceCoordinator({server_name!r})",
                "assert coordinator.acquire()",
                "def activated():",
                "    print('ACTIVATED', flush=True)",
                "    coordinator.close()",
                "    app.quit()",
                "coordinator.activationRequested.connect(activated)",
                "QTimer.singleShot(5000, app.quit)",
                "print('READY', flush=True)",
                "raise SystemExit(app.exec())",
            )
        )
        secondary_code = "\n".join(
            (
                "from PySide6.QtCore import QCoreApplication",
                "from haizflow.desktop.single_instance import SingleInstanceCoordinator",
                "app = QCoreApplication([])",
                f"coordinator = SingleInstanceCoordinator({server_name!r})",
                "assert not coordinator.acquire()",
                "coordinator.close()",
                "print('SECONDARY_EXITED')",
            )
        )
        primary = subprocess.Popen(
            [sys.executable, "-c", primary_code],
            cwd=root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=creationflags,
        )
        try:
            self.assertEqual(primary.stdout.readline().strip(), "READY")
            secondary = subprocess.run(
                [sys.executable, "-c", secondary_code],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
                check=False,
                creationflags=creationflags,
            )
            self.assertEqual(secondary.returncode, 0, secondary.stderr)
            self.assertIn("SECONDARY_EXITED", secondary.stdout)
            output, errors = primary.communicate(timeout=5)
            self.assertEqual(primary.returncode, 0, errors)
            self.assertIn("ACTIVATED", output)
        finally:
            if primary.poll() is None:
                primary.kill()
                primary.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
