"""Cores recentes: ordem, repetição, limite, persistência e arquivo ilegível."""

import json
import tempfile
import unittest
from pathlib import Path

from hidctl.gui.recent_colors import MAX_COLORS, RecentColors


class RecentColorsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "state" / "recent.json"

    def test_most_recent_first_without_repeats_and_with_a_limit(self):
        recent = RecentColors()
        for value in range(MAX_COLORS + 3):
            recent.add((value, 0, 0))
        recent.add((5, 0, 0))
        self.assertEqual(recent.colors[0], (5, 0, 0))
        self.assertEqual(len(recent.colors), MAX_COLORS)
        self.assertEqual(len(set(recent.colors)), MAX_COLORS)
        self.assertNotIn((0, 0, 0), recent.colors)  # a mais antiga saiu

    def test_persists_and_reloads(self):
        RecentColors(self.path).add((1, 2, 3))
        RecentColors(self.path).add((4, 5, 6))
        self.assertEqual(RecentColors(self.path).colors, ((4, 5, 6), (1, 2, 3)))

    def test_invalid_colors_are_rejected_and_not_stored(self):
        recent = RecentColors(self.path)
        for bad in (
            (256, 0, 0),
            (-1, 0, 0),
            (True, 0, 0),
            (1, 2),
            "abc",
            None,
            (1.0, 2, 3),
        ):
            with self.subTest(bad), self.assertRaises(ValueError):
                recent.add(bad)
        self.assertEqual((recent.colors, self.path.exists()), ((), False))

    def test_unreadable_or_foreign_file_is_ignored_and_kept(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("não é json")
        self.assertEqual(RecentColors(self.path).colors, ())
        self.assertEqual(self.path.read_text(), "não é json")
        self.path.write_text(json.dumps([[1, 2, 3], [999, 0, 0], "x", [4, 5, 6]]))
        self.assertEqual(RecentColors(self.path).colors, ((1, 2, 3), (4, 5, 6)))


if __name__ == "__main__":
    unittest.main()
