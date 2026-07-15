import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.desktop.media import thumbnail_source


class ThumbnailSourceTests(unittest.TestCase):
    def test_thumbnail_url_changes_after_replacing_the_same_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            thumbnail = Path(temp_dir) / "thumbnail.jpg"
            thumbnail.write_bytes(b"old")
            first_source = thumbnail_source(str(thumbnail))
            time.sleep(0.002)
            thumbnail.write_bytes(b"new-thumbnail")
            os.utime(thumbnail, None)
            second_source = thumbnail_source(str(thumbnail))

        self.assertTrue(first_source.startswith("file:"))
        self.assertNotEqual(first_source, second_source)


if __name__ == "__main__":
    unittest.main()
