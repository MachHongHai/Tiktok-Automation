import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class PortablePathTests(unittest.TestCase):
    def test_runtime_environment_stays_under_the_selected_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONPATH": str(SRC),
                    "HAIZFLOW_SMOKE_TEST": "1",
                    "HAIZFLOW_HOME": temporary,
                    "RUNTIME_DATA_DIR": temporary,
                    "MODELS_DIR": "C:\\HaizFlow-escape-test\\models",
                    "HF_HOME": "C:\\HaizFlow-escape-test\\huggingface",
                    "TORCH_HOME": "C:\\HaizFlow-escape-test\\torch",
                    "HAIZFLOW_TMP_DIR": "C:\\HaizFlow-escape-test\\tmp",
                }
            )
            script = (
                "import json, os; import haizflow.config as c; "
                "values = {name: os.environ[name] for name in "
                "('HF_HOME','TORCH_HOME','XDG_CACHE_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR',"
                "'CUDA_CACHE_PATH','QML_DISK_CACHE_PATH','LOCALAPPDATA','APPDATA','TMP','TEMP')}; "
                "values['MODELS_DIR'] = c.MODELS_DIR; print(json.dumps(values))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        values = json.loads(completed.stdout.strip())
        selected_home = os.path.normcase(os.path.abspath(temporary))
        for name, value in values.items():
            with self.subTest(name=name):
                self.assertEqual(os.path.commonpath([selected_home, os.path.abspath(value)]), selected_home)


if __name__ == "__main__":
    unittest.main()
