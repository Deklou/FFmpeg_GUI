"""Tests sans Qt : python -m unittest test_rename_tracking -v"""
import tempfile
import unittest
from pathlib import Path

from rename_tracking import file_signature, renamed_candidate


class RenameTrackingTests(unittest.TestCase):
    def test_rename_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'clip.mp4'
            old.write_bytes(b'video content')
            signature = file_signature(old)
            new = old.rename(Path(directory) / 'nouveau_nom.mp4')
            if signature is None:
                self.skipTest('Filesystem without a usable file ID')
            self.assertEqual(renamed_candidate(old, signature), str(new))

    def test_replacement_with_same_size_is_not_a_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'clip.mp4'
            old.write_bytes(b'123456')
            signature = file_signature(old)
            old.unlink()
            (Path(directory) / 'new.mp4').write_bytes(b'abcdef')
            self.assertIsNone(renamed_candidate(old, signature))

    def test_non_video_rename_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'clip.mp4'
            old.write_bytes(b'video content')
            signature = file_signature(old)
            old.rename(Path(directory) / 'clip.txt')
            self.assertIsNone(renamed_candidate(old, signature))

    def test_occupied_candidate_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'clip.mp4'
            old.write_bytes(b'video content')
            signature = file_signature(old)
            new = old.rename(Path(directory) / 'new.mp4')
            self.assertIsNone(renamed_candidate(old, signature, [str(new)]))


if __name__ == '__main__':
    unittest.main()
