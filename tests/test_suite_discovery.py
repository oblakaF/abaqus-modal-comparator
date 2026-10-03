from pathlib import Path
import re
import unittest


TESTS = Path(__file__).resolve().parent
_TEST_CASE = re.compile(r"^class \w+\([^)]*TestCase\)", re.MULTILINE)


class SuiteDiscoveryTests(unittest.TestCase):
    def test_every_test_case_module_matches_the_discovery_pattern(self):
        # `python -m unittest discover -s tests` (local and CI) only collects test*.py;
        # a TestCase in any other file never runs, which silently hides its tests.
        hidden = sorted(
            path.name
            for path in TESTS.glob("*.py")
            if not path.name.startswith("test")
            and _TEST_CASE.search(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(hidden, [], "rename these files to test_*.py so discovery collects them")


if __name__ == "__main__":
    unittest.main()
