from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fast_cache
from modal_core import ModalDataset, ModeShape


class FastCacheTests(unittest.TestCase):
    def test_unv_result_is_reused_from_memory_and_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scan.unv"
            source.write_text("synthetic", encoding="utf-8")
            calls = {"count": 0}

            def fake_loader(file_path, target_frequencies=None, target_count=None, modal_set=None):
                calls["count"] += 1
                mode = ModeShape(
                    number=1,
                    frequency_hz=10.0,
                    node_ids=np.array([1, 2], dtype=object),
                    coordinates=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
                    vectors=np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]], dtype=complex),
                )
                return ModalDataset("Testlab", Path(file_path), [mode])

            fast_cache._MEMORY_UNV.clear()
            with patch.object(fast_cache, "_ORIGINAL_UNIVERSAL_LOADER", fake_loader, create=True), patch.object(
                fast_cache, "_user_cache_root", lambda: root / "cache"
            ):
                first = fast_cache._cached_universal_loader(
                    source, target_frequencies=[10.0], target_count=1
                )
                second = fast_cache._cached_universal_loader(
                    source, target_frequencies=[10.0], target_count=1
                )
                self.assertEqual(calls["count"], 1)
                self.assertEqual(second.metadata["unv_cache_reused"], "memory")

                fast_cache._MEMORY_UNV.clear()
                third = fast_cache._cached_universal_loader(
                    source, target_frequencies=[10.0], target_count=1
                )
                self.assertEqual(calls["count"], 1)
                self.assertEqual(third.metadata["unv_cache_reused"], "disk")
                self.assertEqual(first.modes[0].frequency_hz, third.modes[0].frequency_hz)

    def test_fe_targets_do_not_fragment_experimental_import_cache_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scan.unv"
            source.write_text("synthetic", encoding="utf-8")
            calls = {"count": 0}

            def fake_loader(file_path, target_frequencies=None, target_count=None, modal_set=None):
                calls["count"] += 1
                self.assertIsNone(target_frequencies)
                self.assertIsNone(target_count)
                mode = ModeShape(
                    number=1,
                    frequency_hz=10.0,
                    node_ids=np.array([1], dtype=object),
                    coordinates=np.zeros((1, 3)),
                    vectors=np.array([[0.0, 0.0, 1.0]], dtype=complex),
                )
                return ModalDataset("Testlab", Path(file_path), [mode])

            fast_cache._MEMORY_UNV.clear()
            with patch.object(
                fast_cache, "_ORIGINAL_UNIVERSAL_LOADER", fake_loader, create=True
            ), patch.object(fast_cache, "_user_cache_root", lambda: root / "cache"):
                first = fast_cache._cached_universal_loader(
                    source, target_frequencies=[10.0], target_count=1
                )
                second = fast_cache._cached_universal_loader(
                    source, target_frequencies=[1000.0, 2000.0], target_count=999
                )

            self.assertEqual(calls["count"], 1)
            self.assertEqual(first.modes[0].frequency_hz, second.modes[0].frequency_hz)
            self.assertEqual(second.metadata["unv_cache_reused"], "memory")

    def test_old_fe_guided_cache_version_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scan.unv"
            source.write_text("synthetic", encoding="utf-8")
            calls = {"count": 0}

            stale_mode = ModeShape(
                number=1,
                frequency_hz=999.0,
                node_ids=np.array([1], dtype=object),
                coordinates=np.zeros((1, 3)),
                vectors=np.array([[0.0, 0.0, 1.0]], dtype=complex),
            )
            stale_dataset = ModalDataset("stale", source, [stale_mode])
            key = fast_cache._unv_cache_key(source, [999.0], 1, None)
            cache_path = root / "cache" / f"unv_{key}.pkl.gz"
            cache_path.parent.mkdir(parents=True)
            fast_cache._atomic_pickle_dump(
                {"version": "pre-p1-2-fe-guided-cache", "dataset": stale_dataset},
                cache_path,
                compressed=True,
            )

            def fake_loader(file_path, target_frequencies=None, target_count=None, modal_set=None):
                calls["count"] += 1
                fresh_mode = ModeShape(
                    number=1,
                    frequency_hz=10.0,
                    node_ids=np.array([1], dtype=object),
                    coordinates=np.zeros((1, 3)),
                    vectors=np.array([[0.0, 0.0, 1.0]], dtype=complex),
                )
                return ModalDataset("fresh", Path(file_path), [fresh_mode])

            fast_cache._MEMORY_UNV.clear()
            with patch.object(
                fast_cache, "_ORIGINAL_UNIVERSAL_LOADER", fake_loader, create=True
            ), patch.object(fast_cache, "_user_cache_root", lambda: root / "cache"):
                result = fast_cache._cached_universal_loader(
                    source, target_frequencies=[999.0], target_count=1
                )

            self.assertEqual(calls["count"], 1)
            self.assertEqual(result.modes[0].frequency_hz, 10.0)

    def test_modal_set_selection_is_forwarded_and_part_of_cache_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scan.unv"
            source.write_text("synthetic", encoding="utf-8")
            selections = []

            def fake_loader(file_path, target_frequencies=None, target_count=None, modal_set=None):
                selections.append(modal_set)
                frequency = 10.0 if modal_set == "first" else 20.0
                mode = ModeShape(
                    number=1,
                    frequency_hz=frequency,
                    node_ids=np.array([1], dtype=object),
                    coordinates=np.array([[0.0, 0.0, 0.0]]),
                    vectors=np.array([[0.0, 0.0, 1.0]], dtype=complex),
                )
                return ModalDataset("Testlab", Path(file_path), [mode])

            fast_cache._MEMORY_UNV.clear()
            with patch.object(
                fast_cache, "_ORIGINAL_UNIVERSAL_LOADER", fake_loader, create=True
            ), patch.object(fast_cache, "_user_cache_root", lambda: root / "cache"):
                first = fast_cache._cached_universal_loader(source, modal_set="first")
                second = fast_cache._cached_universal_loader(source, modal_set="second")
                first_again = fast_cache._cached_universal_loader(source, modal_set="first")

            self.assertEqual(selections, ["first", "second"])
            self.assertEqual(first.modes[0].frequency_hz, 10.0)
            self.assertEqual(second.modes[0].frequency_hz, 20.0)
            self.assertEqual(first_again.metadata["unv_cache_reused"], "memory")


if __name__ == "__main__":
    unittest.main()
