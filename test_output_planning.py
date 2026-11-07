"""Exécution : python -m unittest test_output_planning.py -v"""
import tempfile
import unittest
from pathlib import Path

from output_planning import discover_videos, path_identity, plan_destinations


class OutputPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'videos'
        (self.source / 'Serie A').mkdir(parents=True)
        (self.source / 'Serie B').mkdir(parents=True)
        self.files = [
            self.source / 'Film.mp4',
            self.source / 'Serie A' / 'Episode 1.mkv',
            self.source / 'Serie B' / 'Episode 1.mkv',
        ]
        for path in self.files:
            path.write_bytes(b'fake')

    def plan(self, preserve=True):
        return plan_destinations(
            [str(p) for p in self.files],
            {path_identity(p): str(self.source) for p in self.files},
            self.root / 'sortie', 'mkv', preserve_tree=preserve
        )

    def test_nonrecursive(self):
        self.assertEqual(discover_videos(self.source), [str(self.files[0])])

    def test_recursive(self):
        self.assertEqual(set(discover_videos(self.source, True)), set(map(str, self.files)))

    def test_preserve_tree(self):
        outputs = self.plan(True)
        self.assertEqual(outputs[0], self.root / 'sortie' / 'Film.mkv')
        self.assertEqual(outputs[1], self.root / 'sortie' / 'Serie A' / 'Episode 1.mkv')
        self.assertEqual(outputs[2], self.root / 'sortie' / 'Serie B' / 'Episode 1.mkv')

    def test_flat_collision_safe_and_stable(self):
        outputs = self.plan(False)
        self.assertEqual(outputs[0].name, 'Film.mkv')
        self.assertNotEqual(outputs[1], outputs[2])
        self.assertTrue(all(p.parent == self.root / 'sortie' for p in outputs))
        self.assertEqual(outputs, self.plan(False))

    def test_manual_file_uses_output_root(self):
        outputs = plan_destinations([str(self.files[1])], {}, self.root / 'sortie', 'mp4', True)
        self.assertEqual(outputs, [self.root / 'sortie' / 'Episode 1.mp4'])

    def test_same_stem_other_extensions(self):
        twin = self.files[0].with_suffix('.mkv')
        twin.write_bytes(b'fake')
        outputs = plan_destinations([str(self.files[0]), str(twin)], {}, self.root / 'out', 'mkv')
        self.assertEqual(len(set(outputs)), 2)

    def test_output_subtree_is_excluded(self):
        nested = self.source / 'sortie'
        nested.mkdir()
        (nested / 'old.mkv').write_bytes(b'fake')
        result = discover_videos(self.source, recursive=True, exclude_folder=nested)
        self.assertEqual(set(result), set(map(str, self.files)))

    def test_output_is_parent_of_source(self):
        # Régression V0.6 : sortie sur le Bureau, source dans Bureau/test.
        result = discover_videos(self.source, recursive=False, exclude_folder=self.root)
        self.assertEqual(result, [str(self.files[0])])
        recursive = discover_videos(self.source, recursive=True, exclude_folder=self.root)
        self.assertEqual(set(recursive), set(map(str, self.files)))

    def test_output_equal_source_does_not_hide_all(self):
        result = discover_videos(self.source, exclude_folder=self.source)
        self.assertEqual(result, [str(self.files[0])])

    def test_same_name_from_separate_roots(self):
        first, second = self.files[1:]
        outputs = plan_destinations(
            [str(first), str(second)],
            {path_identity(first): str(first.parent), path_identity(second): str(second.parent)},
            self.root / 'sortie', 'mkv', True
        )
        self.assertNotEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()
