from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ensure_dependencies import dependencies_are_current, requirements_fingerprint


class DependencyFingerprintTests(unittest.TestCase):
    def test_marker_is_reused_until_requirements_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            requirements = root / "requirements.txt"
            marker = root / "marker.sha256"
            requirements.write_text("numpy>=1.24\n", encoding="utf-8")

            self.assertFalse(dependencies_are_current(requirements, marker))
            marker.write_text(requirements_fingerprint(requirements), encoding="utf-8")
            self.assertTrue(dependencies_are_current(requirements, marker))

            requirements.write_text("numpy>=1.24\nscipy>=1.10\n", encoding="utf-8")
            self.assertFalse(dependencies_are_current(requirements, marker))


if __name__ == "__main__":
    unittest.main()
