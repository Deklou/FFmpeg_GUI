"""Régressions V0.12 : préservation des sorties et changement des exclusions."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from config import ConversionSettings, build_command
from file_utils import (
    discover_videos, output_change_requires_rescan,
    path_identity, plan_destinations, publish_without_overwrite,
)


class StabilityTests(unittest.TestCase):
    def test_output_outside_monitored_roots_does_not_rescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'input'; root.mkdir()
            self.assertFalse(output_change_requires_rescan('', str(Path(tmp) / 'out'), [root]))
            self.assertFalse(output_change_requires_rescan(str(Path(tmp) / 'out'), str(Path(tmp) / 'out2'), [root]))
            self.assertFalse(output_change_requires_rescan('', '', [root]))

    def test_output_inside_source_requires_rescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'input'; root.mkdir()
            sub = root / 'out'
            self.assertTrue(output_change_requires_rescan('', str(sub), [root]))
            self.assertTrue(output_change_requires_rescan(str(sub), '', [root]))
            self.assertTrue(output_change_requires_rescan(str(sub), str(root / 'other'), [root]))
            self.assertFalse(output_change_requires_rescan(str(root), '', [root]))
            self.assertFalse(output_change_requires_rescan(str(sub), str(sub), [root]))

    def test_output_excludes_nested_dir_but_not_siblings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'in'; root.mkdir()
            output = root / 'out'; output.mkdir()
            (root / 'a.mp4').write_bytes(b'a')
            (output / 'b.mp4').write_bytes(b'b')
            self.assertEqual(discover_videos(root, recursive=True, exclude_folder=output), [str(root / 'a.mp4')])
            self.assertEqual(len(discover_videos(root, recursive=True, exclude_folder=root)), 2)

    def test_publish_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.mp4'; target.write_bytes(b'original')
            partial = Path(tmp) / 'in.part.mp4'; partial.write_bytes(b'new')
            self.assertFalse(publish_without_overwrite(partial, target))
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(partial.read_bytes(), b'new')

    def test_publish_creates_output_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.mp4'
            partial = Path(tmp) / 'in.part.mp4'; partial.write_bytes(b'new')
            self.assertTrue(publish_without_overwrite(partial, target))
            self.assertEqual(target.read_bytes(), b'new')
            self.assertFalse(partial.exists())

    def test_collision_safe_output_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a'; b = Path(tmp) / 'b'; a.mkdir(); b.mkdir()
            left = a / 'same.mkv'; right = b / 'same.mkv'
            for p in [left, right]: p.write_bytes(b'0')
            sources = [str(left), str(right)]
            targets = plan_destinations(sources, {}, str(Path(tmp) / 'out'), 'mkv', False)
            self.assertEqual(len(set(path_identity(t) for t in targets)), 2)

    def test_command_has_no_shell_and_preserves_source(self):
        settings = ConversionSettings(codec='libx264', audio='none', subtitles='none', container='mp4')
        command = build_command('ffmpeg', 'source with spaces.mkv', 'dest with spaces.mp4', settings)
        self.assertIsInstance(command, list)
        self.assertIn('source with spaces.mkv', command)
        self.assertIn('dest with spaces.mp4', command)


if __name__ == '__main__':
    unittest.main()
