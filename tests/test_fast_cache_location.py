"""RC6-F2: a large read cache is written only to a folder the user chose; the import works without it.

The sizes are synthetic: the limit is lowered, or read-only broadcast arrays report a large ``nbytes`` without
allocating it. No large file is written.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import abaqus_bridge  # noqa: E402
import fast_cache  # noqa: E402
from modal_core import ModalDataset, ModeShape  # noqa: E402


def _dataset(source, nodes=4, modes=2) -> ModalDataset:
    return ModalDataset("Abaqus", source, [
        ModeShape(number=index + 1, frequency_hz=10.0 * (index + 1),
                  node_ids=np.array([f"P:{n}" for n in range(nodes)], dtype=object),
                  coordinates=np.zeros((nodes, 3)), vectors=np.ones((nodes, 3)))
        for index in range(modes)])


def _virtual_dataset(nodes, modes) -> ModalDataset:
    """Arrays of the full reported size that share one element of memory."""
    shapes = []
    for index in range(modes):
        mode = ModeShape.__new__(ModeShape)
        mode.node_ids = range(nodes)
        mode.coordinates = np.broadcast_to(np.float64(0.0), (nodes, 3))
        mode.vectors = np.broadcast_to(np.complex128(0.0), (nodes, 3))
        mode.number = index + 1
        shapes.append(mode)
    return collections.namedtuple("Virtual", "modes")(shapes)


class _Case(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        self.default = self.root / "user cache"
        self.chosen = self.root / "my cache folder" / "with spaces"
        self.package = self.root / "fe package"
        self.package.mkdir()
        (self.package / "mode_0001.csv").write_text("mode\n", encoding="utf-8")
        self.manifest = self.package / "manifest.json"
        self.manifest.write_text(json.dumps({"modes": [{"file": "mode_0001.csv"}]}), encoding="utf-8")
        self.unv = self.root / "exp folder" / "test.unv"
        self.unv.parent.mkdir()
        self.unv.write_text("-1\n", encoding="utf-8")
        self.parses = 0

        def parse(path, **_kwargs):
            self.parses += 1
            return _dataset(path)

        fast_cache.set_cache_folder(None)
        fast_cache._MEMORY_UNV.clear()
        self.addCleanup(fast_cache.set_cache_folder, None)
        self.addCleanup(fast_cache._MEMORY_UNV.clear)
        for patcher in (mock.patch.object(fast_cache, "_user_cache_root", lambda: self.default),
                        mock.patch.object(fast_cache, "_ORIGINAL_EXTRACTED_ODB_LOADER", parse, create=True),
                        mock.patch.object(fast_cache, "_ORIGINAL_UNIVERSAL_LOADER", parse, create=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def read(self, **kwargs):
        return fast_cache._cached_extracted_odb_loader(self.manifest, **kwargs)

    def entries(self, folder):
        return sorted(p.name for p in folder.glob("*")) if folder.exists() else []

    def limit(self, value=1):
        patcher = mock.patch.object(fast_cache, "IMPLICIT_CACHE_LIMIT_BYTES", value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def free_space(self, free):
        usage = collections.namedtuple("usage", "total used free")(free, 0, free)
        patcher = mock.patch.object(fast_cache.shutil, "disk_usage", return_value=usage)
        patcher.start()
        self.addCleanup(patcher.stop)


class SizePolicyTests(_Case):
    def test_a_small_entry_still_goes_to_the_user_cache_and_is_reused(self):
        first = self.read()
        self.assertEqual(len(self.entries(self.default)), 1)
        self.assertNotIn("binary_odb_cache_write_skipped", first.metadata)
        self.assertIs(self.read().metadata["binary_odb_cache_reused"], True)
        self.assertEqual(self.parses, 1)

    def test_a_large_entry_without_a_chosen_folder_stays_in_memory(self):
        self.limit()
        dataset = self.read()
        self.assertEqual(dataset.metadata["binary_odb_cache_write_skipped"], fast_cache.SKIPPED_LARGE)
        self.assertEqual(self.entries(self.default), [])
        self.assertEqual(len(dataset.modes), 2)
        self.assertEqual(dataset.modes[1].frequency_hz, 20.0)

    def test_a_large_unv_without_a_chosen_folder_stays_in_memory_and_is_reused_there(self):
        self.limit()
        dataset = fast_cache._cached_universal_loader(self.unv)
        self.assertEqual(dataset.metadata["unv_cache_write_skipped"], fast_cache.SKIPPED_LARGE)
        self.assertEqual(self.entries(self.default), [])
        self.assertEqual(fast_cache._cached_universal_loader(self.unv).metadata["unv_cache_reused"], "memory")
        self.assertEqual(self.parses, 1)

    def test_a_chosen_folder_takes_a_large_entry_and_reuses_it(self):
        self.limit()
        fast_cache.set_cache_folder(self.chosen)
        self.assertNotIn("binary_odb_cache_write_skipped", self.read().metadata)
        self.assertEqual(len(self.entries(self.chosen)), 1)
        self.assertEqual(self.entries(self.default), [])
        self.assertIs(self.read().metadata["binary_odb_cache_reused"], True)
        self.assertEqual(self.parses, 1)

    def test_a_chosen_folder_takes_a_large_unv_and_reuses_it(self):
        self.limit()
        fast_cache.set_cache_folder(self.chosen)
        fast_cache._cached_universal_loader(self.unv)
        fast_cache._MEMORY_UNV.clear()
        self.assertEqual(fast_cache._cached_universal_loader(self.unv).metadata["unv_cache_reused"], "disk")
        self.assertEqual(self.parses, 1)

    def test_the_real_limit_keeps_m11_small_and_a_large_model_out(self):
        self.assertLess(fast_cache._estimated_cache_bytes(_virtual_dataset(10201, 20)),
                        fast_cache.IMPLICIT_CACHE_LIMIT_BYTES)
        self.assertGreater(fast_cache._estimated_cache_bytes(_virtual_dataset(100000, 300)),
                           fast_cache.IMPLICIT_CACHE_LIMIT_BYTES)

    def test_an_existing_entry_is_reused_from_the_user_cache_after_a_folder_is_chosen(self):
        self.read()
        fast_cache.set_cache_folder(self.chosen)
        self.assertIs(self.read().metadata["binary_odb_cache_reused"], True)
        self.assertEqual(self.parses, 1)
        self.assertEqual(self.entries(self.chosen), [])

    def test_a_large_existing_entry_is_reused_without_a_folder(self):
        self.read()
        self.limit()
        self.assertIs(self.read().metadata["binary_odb_cache_reused"], True)
        self.assertEqual(self.parses, 1)

    def test_a_changed_source_is_read_again(self):
        fast_cache.set_cache_folder(self.chosen)
        self.read()
        self.manifest.write_text(json.dumps({"modes": [{"file": "mode_0001.csv"}], "changed": 1}), encoding="utf-8")
        self.assertIs(self.read().metadata["binary_odb_cache_reused"], False)
        self.assertEqual(self.parses, 2)


class LowDiskTests(_Case):
    def test_no_room_in_the_chosen_folder_skips_the_write(self):
        fast_cache.set_cache_folder(self.chosen)
        self.free_space(fast_cache.CACHE_FREE_SPACE_RESERVE_BYTES)
        dataset = self.read()
        self.assertEqual(dataset.metadata["binary_odb_cache_write_skipped"], fast_cache.SKIPPED_LOW_SPACE)
        self.assertFalse(self.chosen.exists())
        self.assertEqual(len(dataset.modes), 2)

    def test_no_room_in_the_user_cache_skips_a_small_write_too(self):
        self.free_space(0)
        self.assertEqual(self.read().metadata["binary_odb_cache_write_skipped"], fast_cache.SKIPPED_LOW_SPACE)
        self.assertEqual(self.entries(self.default), [])

    def test_enough_room_writes(self):
        fast_cache.set_cache_folder(self.chosen)
        self.free_space(fast_cache.CACHE_FREE_SPACE_RESERVE_BYTES + 10 ** 6)
        self.assertNotIn("binary_odb_cache_write_skipped", self.read().metadata)
        self.assertEqual(len(self.entries(self.chosen)), 1)

    def test_a_disk_that_fills_during_the_write_leaves_no_partial_file(self):
        fast_cache.set_cache_folder(self.chosen)
        with mock.patch.object(fast_cache.pickle, "dump", side_effect=OSError(28, "No space left on device")):
            dataset = self.read()
        self.assertIs(dataset.metadata["binary_odb_cache_write_failed"], True)
        self.assertEqual(self.entries(self.chosen), [])
        self.assertEqual(len(dataset.modes), 2)

    def test_a_folder_that_cannot_be_measured_is_not_written(self):
        fast_cache.set_cache_folder(self.chosen)
        with mock.patch.object(fast_cache.shutil, "disk_usage", side_effect=OSError("unavailable")):
            self.assertEqual(self.read().metadata["binary_odb_cache_write_skipped"], fast_cache.SKIPPED_LOW_SPACE)


class NothingDeletedTests(_Case):
    def digests(self, folder):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}

    def test_older_entries_stay(self):
        self.default.mkdir()
        older = {"odb_older.pkl.gz": b"older entry", "unv_older.pkl.gz": b"older entry 2"}
        for name, content in older.items():
            (self.default / name).write_bytes(content)
        self.read()
        fast_cache._cached_universal_loader(self.unv)
        for name, content in older.items():
            self.assertEqual((self.default / name).read_bytes(), content)

    def test_an_unreadable_entry_is_not_deleted_when_the_write_is_skipped(self):
        self.read()
        entry = next(self.default.glob("odb_*.pkl.gz"))
        entry.write_bytes(b"broken")
        self.limit()
        dataset = self.read()
        self.assertEqual(entry.read_bytes(), b"broken")
        self.assertEqual(dataset.metadata["binary_odb_cache_write_skipped"], fast_cache.SKIPPED_LARGE)

    def test_the_original_files_are_not_changed(self):
        before = {**self.digests(self.package), **self.digests(self.unv.parent)}
        fast_cache.set_cache_folder(self.package)  # even when the user chooses the package's own folder
        self.read()
        fast_cache.set_cache_folder(self.chosen)
        fast_cache._cached_universal_loader(self.unv)
        after = {**self.digests(self.package), **self.digests(self.unv.parent)}
        for name, digest in before.items():
            self.assertEqual(after[name], digest)


class CancellationTests(_Case):
    def test_cancelled_before_the_read(self):
        cancel = threading.Event()
        cancel.set()
        fast_cache.set_cache_folder(self.chosen)
        with self.assertRaises(abaqus_bridge.AnalysisCancelled):
            self.read(cancel_event=cancel)
        self.assertEqual(self.parses, 0)

    def test_cancelled_during_the_read_of_a_large_package(self):
        cancel = threading.Event()

        def parse_then_cancel(path, **_kwargs):
            cancel.set()
            return _dataset(path)

        self.limit()
        with mock.patch.object(fast_cache, "_ORIGINAL_EXTRACTED_ODB_LOADER", parse_then_cancel, create=True), \
                self.assertRaises(abaqus_bridge.AnalysisCancelled):
            self.read(cancel_event=cancel)
        self.assertEqual(self.entries(self.default), [])


class SetFolderTests(_Case):
    def test_the_choice_and_its_refusals(self):
        self.assertIsNone(fast_cache.set_cache_folder("  "))
        self.assertIsNone(fast_cache.cache_folder())
        self.assertEqual(fast_cache.set_cache_folder(self.chosen), self.chosen)
        self.assertFalse(self.chosen.exists())  # created only when an entry is written
        with self.assertRaises(ValueError):
            fast_cache.set_cache_folder("relative folder")
        with self.assertRaises(ValueError):
            fast_cache.set_cache_folder(self.manifest)
        self.assertEqual(fast_cache.cache_folder(), self.chosen)  # a refused value changes nothing


sys.path.insert(0, str(ROOT / "tests"))
try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - depends on the environment
    QApplication = None
else:
    from new_gui import window as window_module
    from new_gui.odb_import_dialog import OdbImportDialog
    from test_odb_import_service import FOUND, fake_runner


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class DialogTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or window_module.create_application([])
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        self.odb = self.root / "plate.odb"
        self.odb.write_bytes(b"synthetic; never opened")
        fast_cache.set_cache_folder(None)
        self.addCleanup(fast_cache.set_cache_folder, None)

    def dialog(self, **kwargs):
        dialog = OdbImportDialog(self.odb, results_folder=self.root / "results", runner=fake_runner(),
                                 confirm=lambda: True, discover=FOUND, **kwargs)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_no_folder_is_chosen_by_default_and_nothing_is_created(self):
        dialog = self.dialog()
        self.assertEqual(dialog.cache.text(), "")
        self.assertTrue(dialog.apply_cache_folder())
        self.assertIsNone(fast_cache.cache_folder())

    def test_choosing_a_folder_with_spaces_sets_the_destination(self):
        folder = self.root / "read cache folder"
        dialog = self.dialog(ask_cache_folder=lambda _start: str(folder))
        self.assertTrue(dialog.choose_cache_folder())
        self.assertEqual(fast_cache.cache_folder(), folder)
        self.assertFalse(folder.exists())
        self.assertEqual(self.dialog().cache.text(), str(folder))  # offered again in this session

    def test_cancelling_the_folder_dialog_changes_nothing(self):
        dialog = self.dialog(ask_cache_folder=lambda _start: "")
        self.assertFalse(dialog.choose_cache_folder())
        self.assertIsNone(fast_cache.cache_folder())

    def test_a_file_is_refused_with_a_message_and_the_dialog_stays_open(self):
        dialog = self.dialog()
        dialog.cache.setText(str(self.odb))
        self.assertFalse(dialog.apply_cache_folder())
        self.assertIn("is a file", dialog.cache_error.text())
        self.assertIsNone(fast_cache.cache_folder())
        dialog.show()
        self.addCleanup(dialog.close)
        dialog.accept()
        self.assertTrue(dialog.isVisible())
        dialog.cache.setText("")
        self.assertTrue(dialog.apply_cache_folder())
        self.assertEqual(dialog.cache_error.text(), "")

    def test_clearing_the_field_returns_to_no_folder(self):
        fast_cache.set_cache_folder(self.root / "was chosen")
        dialog = self.dialog()
        dialog.cache.setText("")
        self.assertTrue(dialog.apply_cache_folder())
        self.assertIsNone(fast_cache.cache_folder())

    def test_the_cache_controls_are_locked_during_a_run(self):
        import time

        dialog = self.dialog()
        self.assertTrue(dialog.extract())
        self.assertFalse(dialog.cache.isEnabled())
        self.assertFalse(dialog.cache_button.isEnabled())
        end = time.monotonic() + 30
        while dialog.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()
        self.assertTrue(dialog.cache.isEnabled())


if __name__ == "__main__":
    unittest.main()
