import json
import subprocess
import sys
import unittest
from pathlib import Path


class DependencyLockTests(unittest.TestCase):
    def test_release_lock_and_manifest_are_current(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, str(root / "scripts" / "verify-dependency-lock.py"), "--no-installed-check"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertGreaterEqual(payload["locked_packages"], 100)
        self.assertEqual(payload["target"], "windows-x86_64-python-3.13")


if __name__ == "__main__":
    unittest.main()
