"""Tests sans PySide6 pour le noyau de FFmpeg GUI."""
import tempfile
import unittest
from pathlib import Path

from config import ConversionSettings, PresetStore, build_command
from file_utils import (discover_videos, plan_destinations, path_identity,
                        renamed_candidate, file_signature, classify_paths)
from metrics import calculate_summary, format_reduction


class RefactorTests(unittest.TestCase):
    def test_settings_command(self):
        opts = ConversionSettings(codec='libx264', audio='aac',
                                  subtitles='none', container='mp4')
        command = build_command('ffmpeg', 'a.mkv', 'b.mp4', opts)
        self.assertIn('libx264', command)
        self.assertIn('192k', command)

    def test_presets_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'presets.json'
            store = PresetStore(path)
            store.set('Test', ConversionSettings().to_dict())
            self.assertIn('Test', PresetStore(path).custom)

    def test_discovery_and_collisions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'sub').mkdir()
            (root / 'x.mkv').write_bytes(b'a')
            (root / 'sub' / 'x.mkv').write_bytes(b'b')
            self.assertEqual(len(discover_videos(root)), 1)
            files = discover_videos(root, recursive=True)
            self.assertEqual(len(files), 2)
            roots = {path_identity(p): str(root) for p in files}
            targets = plan_destinations(files, roots, root / 'out', 'mkv', False)
            self.assertEqual(len(set(map(str, targets))), 2)

    def test_rename_and_sizes(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / 'a.mp4'
            old.write_bytes(b'abc')
            signature = file_signature(old)
            renamed = old.with_name('b.mp4')
            old.rename(renamed)
            if signature is not None:
                self.assertEqual(renamed_candidate(old, signature), str(renamed))
            self.assertEqual(classify_paths([str(renamed)])[0], [str(renamed)])
            self.assertEqual(format_reduction(25), '25.0 %')
            summary = calculate_summary([100], {0: 75})
            self.assertEqual(summary['known_reduction'], 25)


if __name__ == '__main__':
    unittest.main()
