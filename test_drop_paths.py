"""Tests sans PySide6 : python -m unittest test_drop_paths.py -v"""
import tempfile
import unittest
from pathlib import Path

from drop_paths import classify_paths


class DropPathsTests(unittest.TestCase):
    def test_mixed_and_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            v1 = root / "video.MP4"
            v2 = root / "film.mkv"
            other = root / "notes.txt"
            sub = root / "saison"
            v1.write_bytes(b"test")
            v2.write_bytes(b"test")
            other.write_text("test")
            sub.mkdir()
            videos, folders = classify_paths(
                [str(v1), str(v1), str(v2), str(other), str(sub), str(root / "404.mp4")]
            )
            self.assertEqual(set(videos), {str(v1), str(v2)})
            self.assertEqual(folders, [str(sub)])

    def test_folder_not_scanned_in_classification(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "film.mp4").write_bytes(b"x")
            videos, folders = classify_paths([str(root)])
            self.assertEqual(videos, [])
            self.assertEqual(folders, [str(root)])


if __name__ == "__main__":
    unittest.main()
