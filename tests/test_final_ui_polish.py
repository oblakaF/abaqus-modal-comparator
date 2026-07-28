from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from final_ui_polish import TABLE_COLUMN_SPECS, restore_table_headings


class FakeTree:
    def __init__(self):
        self.columns = tuple(item[0] for item in TABLE_COLUMN_SPECS)
        self.headings = {}
        self.widths = {}

    def __getitem__(self, key):
        if key == "columns":
            return self.columns
        raise KeyError(key)

    def heading(self, key, **options):
        self.headings[key] = options

    def column(self, key, **options):
        self.widths[key] = options


class FinalUiPolishTests(unittest.TestCase):
    def test_all_extended_treeview_headings_are_restored(self):
        tree = FakeTree()
        restore_table_headings(tree)

        expected_titles = {key: title for key, title, _ in TABLE_COLUMN_SPECS}
        self.assertEqual(
            {key: options["text"] for key, options in tree.headings.items()},
            expected_titles,
        )
        self.assertEqual(tree.headings["err"]["text"], "Signed error, %")
        self.assertEqual(tree.headings["source"]["text"], "Experimental source")
        self.assertEqual(tree.headings["confidence"]["text"], "Confidence")


if __name__ == "__main__":
    unittest.main()
