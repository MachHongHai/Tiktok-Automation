import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline.process_job import _checkpoint_valid


class RestartCheckpointTests(unittest.TestCase):
    def test_checkpoint_is_only_valid_for_a_paused_job_being_resumed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "translation.json"
            artifact.write_text("[]", encoding="utf-8")
            job = SimpleNamespace(checkpoints={"translation": "signature"}, resume_step="")

            self.assertFalse(_checkpoint_valid(job, "translation", "signature", [str(artifact)]))

            job.resume_step = "translating"
            self.assertTrue(_checkpoint_valid(job, "translation", "signature", [str(artifact)]))


if __name__ == "__main__":
    unittest.main()
