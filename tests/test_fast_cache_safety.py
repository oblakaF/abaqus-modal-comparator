from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fast_cache import (
    _CACHE_VERSION,
    _clone_dataset,
    _user_cache_path,
)
from modal_core import ModalDataset, ModeShape


class FastCacheSafetyTests(unittest.TestCase):
    def test_cache_version_contains_schema_fingerprint(self):
        self.assertTrue(_CACHE_VERSION.startswith("modal-cache-v5-"))
        self.assertGreater(len(_CACHE_VERSION.split("-")[-1]), 8)

    def test_clone_does_not_share_mutable_metadata(self):
        coordinates = np.array(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        vectors = np.zeros((3, 3))
        vectors[:, 2] = [1.0, -1.0, 0.5]
        source = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [
                ModeShape(
                    1,
                    10.0,
                    np.arange(3),
                    coordinates,
                    vectors,
                    metadata={"nested": {"value": 1}},
                )
            ],
            metadata={"run": {"value": 1}},
        )
        clone = _clone_dataset(source)
        clone.metadata["run"]["value"] = 2
        clone.modes[0].metadata["nested"]["value"] = 2
        self.assertEqual(source.metadata["run"]["value"], 1)
        self.assertEqual(source.modes[0].metadata["nested"]["value"], 1)
        self.assertIs(clone.modes[0].vectors, source.modes[0].vectors)

    def test_user_cache_path_rejects_escape(self):
        with self.assertRaises(ValueError):
            _user_cache_path("../outside.pkl")


if __name__ == "__main__":
    unittest.main()
