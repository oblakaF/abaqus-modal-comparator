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


def fe_modes(count=3, other_order_at=None):
    """FE modes the way the loader built them before it shared geometry: every mode has arrays of its own."""
    modes = []
    for number in range(1, count + 1):
        labels = [2, 1, 3] if number == other_order_at else [1, 2, 3]
        mode = ModeShape(
            number=number,
            frequency_hz=10.0 * number,
            node_ids=np.array([f"PART-1:{label}" for label in labels], dtype=object),
            coordinates=np.array([[float(label), 0.5 * label, 0.0] for label in labels]),
            vectors=np.array([[number + 0.1 * label, 0.0, 1.0 / label] for label in labels], dtype=complex),
        )
        mode.measured_dofs = np.ones(mode.vectors.shape, dtype=bool)
        modes.append(mode)
    return modes


class ExtractedOdbCacheSharedGeometryTests(unittest.TestCase):
    """SP13-SHARED-FE-GEOMETRY-01: a dataset read from the FE cache shares equal geometry as a parsed one does. The
    cache key, the entry on disk and the values are what they were."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "mode_001.csv").write_bytes(b"synthetic")
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"modes": [{"file": "mode_001.csv"}]}), encoding="utf-8")
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.signature = fast_cache._manifest_signature(self.manifest)
        key = hashlib.sha256(json.dumps(self.signature, sort_keys=True).encode("utf-8")).hexdigest()
        self.entry = self.cache / f"odb_{key}.pkl.gz"

    def read(self, loader):
        with patch.object(fast_cache, "_ORIGINAL_EXTRACTED_ODB_LOADER", loader, create=True), \
                patch.object(fast_cache, "_user_cache_root", lambda: self.cache), \
                patch.object(fast_cache, "_CACHE_FOLDER", None):
            return fast_cache._cached_extracted_odb_loader(self.manifest)

    @staticmethod
    def must_not_parse(*_args, **_kwargs):
        raise AssertionError("an existing extracted-ODB cache entry was not reused")

    def write_entry_of_the_previous_program(self, modes):
        for mode in modes:  # as parsed before this change: nothing shared
            self.assertTrue(mode.node_ids.flags.writeable)
        self.assertEqual(len({id(mode.coordinates) for mode in modes}), len(modes))
        fast_cache._atomic_pickle_dump(
            {"signature": self.signature, "dataset": ModalDataset("Abaqus ODB", self.manifest, modes)},
            self.entry, compressed=True)
        return hashlib.sha256(self.entry.read_bytes()).hexdigest()

    def assert_values(self, dataset, expected):
        self.assertEqual(len(dataset.modes), len(expected))
        for mode, reference in zip(dataset.modes, expected):
            self.assertEqual((mode.number, mode.frequency_hz), (reference.number, reference.frequency_hz))
            self.assertEqual(mode.node_ids.tolist(), reference.node_ids.tolist())
            self.assertEqual(mode.coordinates.tobytes(), reference.coordinates.tobytes())
            self.assertEqual(mode.vectors.tobytes(), reference.vectors.tobytes())
            self.assertEqual(mode.measured_dofs.tolist(), reference.measured_dofs.tolist())

    def assert_shared_and_read_only(self, dataset):
        first = dataset.modes[0]
        for mode in dataset.modes[1:]:
            self.assertIs(mode.node_ids, first.node_ids)
            self.assertIs(mode.coordinates, first.coordinates)
        with self.assertRaises(ValueError):
            first.node_ids[0] = "OTHER:1"
        with self.assertRaises(ValueError):
            dataset.modes[-1].coordinates[0, 0] = 9.0
        self.assertEqual(len({id(mode.vectors) for mode in dataset.modes}), len(dataset.modes))
        self.assertEqual(len({id(mode.measured_dofs) for mode in dataset.modes}), len(dataset.modes))
        self.assertTrue(all(mode.vectors.flags.writeable for mode in dataset.modes))

    def test_an_entry_written_before_the_change_is_reused_and_shares_its_geometry(self):
        digest = self.write_entry_of_the_previous_program(fe_modes())
        dataset = self.read(self.must_not_parse)
        self.assertIs(dataset.metadata["binary_odb_cache_reused"], True)
        self.assert_shared_and_read_only(dataset)
        self.assert_values(dataset, fe_modes())
        self.assertEqual(hashlib.sha256(self.entry.read_bytes()).hexdigest(), digest)  # the entry is not rewritten
        self.assertEqual(sorted(path.name for path in self.cache.iterdir()), [self.entry.name])

    def test_a_cached_mode_with_another_node_order_keeps_its_own_arrays(self):
        self.write_entry_of_the_previous_program(fe_modes(other_order_at=2))
        one, two, three = self.read(self.must_not_parse).modes
        self.assertIsNot(two.node_ids, one.node_ids)
        self.assertIsNot(two.coordinates, one.coordinates)
        self.assertEqual(two.node_ids.tolist(), ["PART-1:2", "PART-1:1", "PART-1:3"])
        self.assertTrue(two.coordinates.flags.writeable)
        self.assertIs(three.node_ids, one.node_ids)
        self.assertIs(three.coordinates, one.coordinates)

    def test_a_new_entry_keeps_the_key_and_gives_shared_read_only_geometry_when_read_back(self):
        parsed = []

        def loader(manifest_path, cancel_event=None):
            modes = fe_modes()
            abaqus_bridge_share(modes)
            parsed.append(1)
            return ModalDataset("Abaqus ODB", Path(manifest_path), modes)

        written = self.read(loader)
        self.assertIs(written.metadata["binary_odb_cache_reused"], False)
        self.assertEqual(sorted(path.name for path in self.cache.iterdir()), [self.entry.name])  # the same key
        self.assert_shared_and_read_only(written)
        stored = fast_cache._pickle_load(self.entry, compressed=True)
        self.assertEqual(stored["signature"], self.signature)
        self.assertIs(stored["dataset"].modes[1].coordinates, stored["dataset"].modes[0].coordinates)  # stored once
        ids, xyz = stored["dataset"].modes[0].node_ids.copy(), stored["dataset"].modes[0].coordinates.copy()
        for mode in stored["dataset"].modes:  # whether a pickle keeps the flag depends on NumPy: drop it here ...
            mode.node_ids, mode.coordinates = ids, xyz
        self.assertTrue(ids.flags.writeable and xyz.flags.writeable)
        fast_cache._atomic_pickle_dump(stored, self.entry, compressed=True)
        again = self.read(self.must_not_parse)
        self.assertEqual(parsed, [1])
        self.assertIs(again.metadata["binary_odb_cache_reused"], True)
        self.assert_shared_and_read_only(again)  # ... and the reader restores it
        self.assert_values(again, fe_modes())

    def test_a_changed_package_file_still_invalidates_the_entry(self):
        self.write_entry_of_the_previous_program(fe_modes())
        (self.root / "mode_001.csv").write_bytes(b"synthetic, changed")
        parsed = []

        def loader(manifest_path, cancel_event=None):
            parsed.append(1)
            return ModalDataset("Abaqus ODB", Path(manifest_path), fe_modes(count=1))

        dataset = self.read(loader)
        self.assertEqual(parsed, [1])
        self.assertIs(dataset.metadata["binary_odb_cache_reused"], False)
        self.assertEqual(len(dataset.modes), 1)


def abaqus_bridge_share(modes):
    import abaqus_bridge
    return abaqus_bridge.share_equal_geometry(modes)


if __name__ == "__main__":
    unittest.main()
