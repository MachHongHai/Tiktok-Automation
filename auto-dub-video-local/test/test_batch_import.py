import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.desktop.qml_controller import AutoDubController


class BatchImportTests(unittest.TestCase):
    def test_folder_import_keeps_only_supported_top_level_videos(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "a.mp4").touch()
            (folder / "b.MOV").touch()
            (folder / "c.mkv").touch()
            (folder / "notes.txt").touch()
            (folder / "audio.wav").touch()
            nested = folder / "nested"
            nested.mkdir()
            (nested / "nested.mp4").touch()

            valid_paths, invalid_names = AutoDubController._collect_batch_video_paths(
                [str(folder), str(folder / "a.mp4"), str(folder / "missing.mp4")]
            )

            self.assertEqual(
                [os.path.basename(path) for path in valid_paths],
                ["a.mp4", "b.MOV", "c.mkv"],
            )
            self.assertEqual(invalid_names, ["missing.mp4"])


if __name__ == "__main__":
    unittest.main()
