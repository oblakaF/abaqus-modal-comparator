from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmif_ui import (
    COMPACT_SUMMARY_LINES,
    EXPANDED_SUMMARY_LINES,
    summary_height,
)


class CmifUiLayoutTests(unittest.TestCase):
    def test_compact_summary_is_shorter_than_expanded_summary(self):
        self.assertLess(COMPACT_SUMMARY_LINES, EXPANDED_SUMMARY_LINES)
        self.assertEqual(summary_height(False), COMPACT_SUMMARY_LINES)
        self.assertEqual(summary_height(True), EXPANDED_SUMMARY_LINES)

    def test_compact_summary_reserves_most_vertical_space_for_plot(self):
        self.assertLessEqual(COMPACT_SUMMARY_LINES, 8)
        self.assertGreaterEqual(EXPANDED_SUMMARY_LINES, 14)


if __name__ == "__main__":
    unittest.main()
