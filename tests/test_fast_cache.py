from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import fast_cache
import universal_hardening
from modal_core import ModalDataset, ModeShape
from test_universal_hardening import write_2414_unv


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


def pre_app_import_2414_unv_cache_key(source, modal_set=None):
    """The UNV cache key exactly as fast_cache built it before APP-IMPORT-2414 (no importer marker)."""
    payload = {
        "version": fast_cache._CACHE_VERSION,
        "source": fast_cache._file_signature(source),
        "modal_set": None if modal_set is None else str(modal_set),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class UnvImporterVersionCacheTests(unittest.TestCase):
    """APP-IMPORT-2414: UNV results cached before the dataset-2414 fix are not served again."""

    @classmethod
    def setUpClass(cls):
        universal_hardening.install_universal_hardening()  # the importer the cache wraps in the application

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="unv_importer_cache_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.cache = self.root / "cache"
        fast_cache._MEMORY_UNV.clear()
        self.addCleanup(fast_cache._MEMORY_UNV.clear)
        self.source = write_2414_unv(
            self.root / "records_2414.unv",
            [{"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
             {"analysis_type": 2, "mode": 9, "frequency": 47.25, "label": 2}],
        )
        self.parses = 0

        def counted(*args, **kwargs):
            self.parses += 1
            return universal_hardening.load_universal_modal_file(*args, **kwargs)

        for patcher in (patch.object(fast_cache, "_ORIGINAL_UNIVERSAL_LOADER", counted, create=True),
                        patch.object(fast_cache, "_user_cache_root", lambda: self.cache)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_pre_fix_frf_entry(self):
        """A cache file in the pre-fix format: the earlier FRF-only reading of this same file, at its old key."""
        frf_mode = ModeShape(
            number=1,
            frequency_hz=24.9,
            node_ids=np.array([11, 12, 13], dtype=object),
            coordinates=np.zeros((3, 3)),
            vectors=np.array([[0.0, 0.0, 1.0]] * 3, dtype=complex),
            metadata={"frf_indicator": 1.0},
        )
        frf_result = ModalDataset("FRF estimate", self.source, [frf_mode],
                                  metadata={"frf_channel_count": 3, "import_warnings": []})
        path = self.cache / f"unv_{pre_app_import_2414_unv_cache_key(self.source)}.pkl.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        fast_cache._atomic_pickle_dump({"version": fast_cache._CACHE_VERSION, "dataset": frf_result},
                                       path, compressed=True)
        return path

    def test_the_pre_fix_entry_is_valid_for_the_pre_fix_key(self):
        # Control: under the old key recipe this entry is served as is, without a parse.
        stale = self.write_pre_fix_frf_entry()
        with patch.object(fast_cache, "_unv_cache_key",
                          lambda source, *_args: pre_app_import_2414_unv_cache_key(source, _args[-1])):
            served = fast_cache._cached_universal_loader(self.source)
        self.assertEqual(self.parses, 0)
        self.assertEqual(served.metadata["unv_cache_reused"], "disk")
        self.assertEqual([(m.number, m.frequency_hz) for m in served.modes], [(1, 24.9)])
        self.assertTrue(stale.exists())

    def test_a_pre_fix_entry_is_ignored_and_the_file_is_parsed_again(self):
        stale = self.write_pre_fix_frf_entry()
        stale_bytes = stale.read_bytes()
        self.assertNotEqual(fast_cache._unv_cache_key(self.source, None, None, None),
                            pre_app_import_2414_unv_cache_key(self.source))
        dataset = fast_cache._cached_universal_loader(self.source)
        self.assertEqual(self.parses, 1)
        self.assertIs(dataset.metadata["unv_cache_reused"], False)
        self.assertEqual([(m.number, m.frequency_hz) for m in dataset.modes], [(7, 23.5), (9, 47.25)])
        self.assertNotIn("frf_channel_count", dataset.metadata)
        self.assertEqual(stale.read_bytes(), stale_bytes)  # the old entry is left on disk, only no longer used

    def test_an_entry_written_by_the_new_importer_is_reused(self):
        self.write_pre_fix_frf_entry()
        first = fast_cache._cached_universal_loader(self.source)
        fast_cache._MEMORY_UNV.clear()
        again = fast_cache._cached_universal_loader(self.source)
        self.assertEqual(self.parses, 1)
        self.assertEqual(again.metadata["unv_cache_reused"], "disk")
        self.assertEqual([(m.number, m.frequency_hz) for m in again.modes],
                         [(m.number, m.frequency_hz) for m in first.modes])
        new_key = fast_cache._unv_cache_key(self.source, None, None, None)
        self.assertEqual(sorted(p.name for p in self.cache.glob("unv_*.pkl.gz")),
                         sorted([f"unv_{new_key}.pkl.gz",
                                 f"unv_{pre_app_import_2414_unv_cache_key(self.source)}.pkl.gz"]))


class ExtractedOdbCacheIdentityTests(unittest.TestCase):
    """The UNV importer marker leaves the FE/ODB cache identity as it was."""

    def test_odb_cache_key_and_reuse_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mode_001.npz").write_bytes(b"synthetic")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"modes": [{"file": "mode_001.npz"}]}), encoding="utf-8")
            signature = {
                "version": fast_cache._CACHE_VERSION,
                "manifest": fast_cache._file_signature(manifest),
                "mode_files": [fast_cache._file_signature(root / "mode_001.npz")],
                "geometry_file": None,
            }
            self.assertEqual(fast_cache._manifest_signature(manifest), signature)
            self.assertNotIn(fast_cache._UNV_IMPORTER_VERSION, json.dumps(signature))
            key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode("utf-8")).hexdigest()
            cached_mode = ModeShape(
                number=1,
                frequency_hz=31.0,
                node_ids=np.array([1], dtype=object),
                coordinates=np.zeros((1, 3)),
                vectors=np.array([[0.0, 0.0, 1.0]]),
            )
            cache = root / "cache"
            cache.mkdir()
            fast_cache._atomic_pickle_dump(
                {"signature": signature, "dataset": ModalDataset("Abaqus", manifest, [cached_mode])},
                cache / f"odb_{key}.pkl.gz",
                compressed=True,
            )

            def must_not_parse(*_args, **_kwargs):
                raise AssertionError("an existing extracted-ODB cache entry was not reused")

            with patch.object(fast_cache, "_ORIGINAL_EXTRACTED_ODB_LOADER", must_not_parse, create=True), \
                    patch.object(fast_cache, "_user_cache_root", lambda: cache):
                dataset = fast_cache._cached_extracted_odb_loader(manifest)
            self.assertIs(dataset.metadata["binary_odb_cache_reused"], True)
            self.assertEqual(dataset.modes[0].frequency_hz, 31.0)


if __name__ == "__main__":
    unittest.main()
