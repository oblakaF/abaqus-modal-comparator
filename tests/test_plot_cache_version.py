from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from plot_cache_version import (
    PAIR_MARKER_NAME,
    PAIR_RENDER_VERSION,
    ensure_pair_render_cache,
)


class PairPlotCacheVersionTests(unittest.TestCase):
    def test_stale_pair_images_are_removed_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            stale_overlay = directory / "abaqus_7_experiment_1_overlay.png"
            stale_correlation = directory / "abaqus_7_experiment_1_correlation.png"
            unrelated = directory / "mac_matrix.png"
            stale_overlay.write_bytes(b"old")
            stale_correlation.write_bytes(b"old")
            unrelated.write_bytes(b"keep")

            self.assertTrue(ensure_pair_render_cache(directory))
            self.assertFalse(stale_overlay.exists())
            self.assertFalse(stale_correlation.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(
                (directory / PAIR_MARKER_NAME).read_text(encoding="utf-8"),
                PAIR_RENDER_VERSION,
            )

            fresh = directory / "abaqus_7_experiment_1_correlation.png"
            fresh.write_bytes(b"fresh")
            self.assertFalse(ensure_pair_render_cache(directory))
            self.assertTrue(fresh.exists())


if __name__ == "__main__":
    unittest.main()
