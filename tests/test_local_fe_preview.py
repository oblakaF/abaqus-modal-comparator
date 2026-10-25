"""APP-DATA.2: read-only view of the FE modes in an extracted package (File > Input file registry... > Inspect FE modes).

The view uses the existing loader ``abaqus_bridge.load_extracted_odb`` unchanged: the modes, frequencies and refusals it
shows are the loader's. A plain .odb is never extracted (Abaqus is not started), the package files are only read, the
reading runs off the Tk thread and a window closed while reading discards the outcome. Synthetic temporary packages.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import abaqus_bridge  # noqa: E402
from services import local_fe_preview as fe_preview  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from test_app_p1_stale_results import _App  # noqa: E402

NODES = [("PART-1", 1, 0.0, 0.0, 0.0), ("PART-1", 2, 0.3, 0.0, 0.0), ("PART-1", 3, 0.0, 0.3, 0.0)]


def described(frequency: float, digits: int = 4) -> str:
    return (f"Mode: Value = {(2 * 3.141592653589793 * frequency) ** 2:.5E} Freq = {frequency:.{digits}f} "
            "(cycles/time)")


RIGID = [0.0011, 0.0012, 0.0013, 0.0014, 0.0015, 0.0016]  # rigid-body frames: near-zero positive frequencies


def write_package(folder: Path, modes, *, history=None, geometry=True, start=None, end=None) -> Path:
    """An extracted package in the pinned extractor's format 2: manifest.json, geometry.csv, one CSV per mode.
    ``modes`` holds (mode number, manifest frequency, description or None)."""
    folder.mkdir(parents=True, exist_ok=True)
    if geometry:
        rows = ["instance,node_label,x,y,z"] + [f"{i},{n},{x},{y},{z}" for i, n, x, y, z in NODES]
        (folder / "geometry.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    entries = []
    for number, frequency, description in modes:
        name = f"mode_{number:04d}.csv"
        rows = ["instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag"]
        rows += [f"{i},{n},0,0,{(n + number) % 3 - 1},0,0,0" for i, n, *_ in NODES]
        (folder / name).write_text("\n".join(rows) + "\n", encoding="utf-8")
        entry = {"mode": number, "frequency_hz": frequency, "file": name, "frame_index": number}
        if description is not None:
            entry["description"] = description
        entries.append(entry)
    numbers = [m[0] for m in modes] or [1]
    manifest = {"format_version": 2, "geometry_file": "geometry.csv", "step_name": "Frequency",
                "odb_path": "D:/synthetic/plate_model.odb", "start_mode": start or min(numbers),
                "end_mode": end or max(numbers), "modes": entries}
    if history is not None:
        manifest["history"] = history
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return path


def fingerprint(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="app_data2_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        for target in ("subprocess.Popen", "abaqus_bridge.run_abaqus_extraction"):
            patcher = mock.patch(target, side_effect=AssertionError(f"{target} must not run for a preview"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def plate(self, name="plate") -> Path:
        """Six rigid-body frames (near 0 Hz) and three elastic modes, every record consistent."""
        modes = [(n, f, described(f)) for n, f in enumerate(RIGID, 1)]
        modes += [(7, 19.07, described(19.07)), (8, 33.52, described(33.52)), (9, 60.11, described(60.11))]
        return write_package(self.folder / name, modes)

    def assert_matches_loader(self, preview, manifest: Path) -> None:
        dataset = abaqus_bridge.load_extracted_odb(manifest)
        self.assertEqual([(m.number, m.frequency_hz) for m in preview.modes],
                         [(int(m.number), float(m.frequency_hz)) for m in dataset.modes])
        self.assertEqual([m.frequency_source for m in preview.modes],
                         [m.metadata["frequency_source"] for m in dataset.modes])


class ServiceTests(_Folder):
    def test_a_valid_package_shows_every_loaded_mode_and_frequency(self):
        manifest = self.plate()
        before = fingerprint(manifest.parent)
        preview = fe_preview.preview_fe_package(manifest)
        self.assertEqual(preview.mode_numbers, list(range(1, 10)))  # rigid frames and the first elastic mode kept
        self.assertEqual([m.frequency_hz for m in preview.modes][6:], [19.07, 33.52, 60.11])
        self.assertEqual({m.node_count for m in preview.modes}, {3})
        self.assertEqual(preview.fe_source, "D:/synthetic/plate_model.odb")
        self.assertEqual(preview.step_name, "Frequency")
        self.assertEqual(preview.warnings, ())
        self.assertEqual(fe_preview.summary(preview), "9 modes loaded (1–9); no diagnostic messages")
        self.assert_matches_loader(preview, manifest)
        self.assertEqual(fingerprint(manifest.parent), before)  # nothing written

    def test_eigfreq_history_values_are_the_loaders(self):
        history = [{"name": "EIGFREQ", "data": [[7, 19.0703], [8, 33.5198], [9, 60.1104]]}]
        history[0]["data"] = [[7, 19.07032], [8, 33.51981], [9, 60.11042]]  # within the 3-decimal frame precision
        manifest = write_package(self.folder / "eig", [(7, 19.07, described(19.07, 3)), (8, 33.52, described(33.52, 3)),
                                                       (9, 60.11, described(60.11, 3))], history=history)
        preview = fe_preview.preview_fe_package(manifest)
        self.assertEqual([m.frequency_hz for m in preview.modes], [19.07032, 33.51981, 60.11042])
        self.assertEqual({m.frequency_source for m in preview.modes}, {abaqus_bridge.FREQUENCY_SOURCE_HISTORY})
        self.assertEqual(fe_preview.source_text(preview.modes[0]), "EIGFREQ history")
        self.assert_matches_loader(preview, manifest)

    def test_contradictory_frequency_records_follow_the_loader(self):
        # mode 2: the extractor's frameValue fallback ("2 Hz") against a 0 Hz frame description (R7)
        # mode 8: the manifest value contradicts its own frame description
        modes = [(1, 0.0011, described(0.0011)), (2, 2.0, described(0.0)), (7, 19.07, described(19.07)),
                 (8, 40.0, described(33.52))]
        manifest = write_package(self.folder / "contradict", modes)
        preview = fe_preview.preview_fe_package(manifest)
        self.assertEqual(preview.mode_numbers, [1, 7])
        self.assert_matches_loader(preview, manifest)
        metadata = abaqus_bridge.load_extracted_odb(manifest).metadata
        refused = metadata["rejected_frequency_modes"]
        self.assertEqual(sorted(refused), ["2", "8"])
        # the loader's own messages, in order: the two refused modes, then its note on the non-contiguous range
        self.assertEqual(len(preview.warnings), 3)
        self.assertTrue(preview.warnings[0].startswith("Mode 2 not loaded: "))
        self.assertIn("frameValue fallback", preview.warnings[0])
        self.assertIn(refused["8"]["reason"], preview.warnings[1])
        self.assertEqual(preview.warnings[2], metadata["extraction_range_notice"])

    def test_a_clipped_extraction_range_is_reported(self):
        manifest = write_package(self.folder / "range", [(7, 19.07, described(19.07))], start=7, end=12)
        preview = fe_preview.preview_fe_package(manifest)
        self.assertEqual(preview.warnings, (abaqus_bridge.extraction_range_notice(json.loads(manifest.read_text())),))

    def test_missing_mode_csv_or_geometry_is_a_clear_error(self):
        manifest = self.plate("no_csv")
        (manifest.parent / "mode_0008.csv").unlink()
        with self.assertRaisesRegex(fe_preview.FePreviewError, "incomplete: .*mode_0008.csv"):
            fe_preview.preview_fe_package(manifest)
        manifest = self.plate("no_geometry")
        (manifest.parent / "geometry.csv").unlink()
        with self.assertRaisesRegex(fe_preview.FePreviewError, "incomplete: .*geometry"):
            fe_preview.preview_fe_package(manifest)

    def test_a_damaged_manifest_is_a_clear_error_and_is_not_changed(self):
        manifest = self.plate("damaged")
        forms = {
            "invalid JSON": "{not json",
            "a list": "[1, 2]",
            "an entry without its mode": json.dumps({"format_version": 2, "geometry_file": "geometry.csv",
                                                     "modes": [{"frequency_hz": 1.0, "file": "mode_0007.csv"}]}),
            "a frequency that is not a number": json.dumps({"format_version": 2, "geometry_file": "geometry.csv",
                                                            "modes": [{"mode": 7, "frequency_hz": "abc",
                                                                       "file": "mode_0007.csv"}]}),
            "no modes": json.dumps({"format_version": 2, "geometry_file": "geometry.csv", "modes": []}),
            "format 2 without geometry_file": json.dumps({"format_version": 2, "modes": []}),
        }
        for name, text in forms.items():
            with self.subTest(form=name):
                manifest.write_text(text, encoding="utf-8")
                before = fingerprint(manifest.parent)
                with self.assertRaisesRegex(fe_preview.FePreviewError, "cannot be read"):
                    fe_preview.preview_fe_package(manifest)
                self.assertEqual(fingerprint(manifest.parent), before)

    def test_an_odb_is_never_extracted(self):
        odb = self.folder / "model.odb"
        odb.write_bytes(b"synthetic ODB stand-in; never opened")
        with mock.patch.object(fe_preview, "load_extracted_odb", side_effect=AssertionError("not loaded")):
            with self.assertRaises(fe_preview.FePreviewError) as raised:
                fe_preview.preview_fe_package(odb)
        self.assertEqual(str(raised.exception), fe_preview.ODB_NEEDS_PACKAGE)
        self.assertIn("Abaqus is not started", fe_preview.ODB_NEEDS_PACKAGE)
        self.assertEqual(odb.read_bytes(), b"synthetic ODB stand-in; never opened")
        with self.assertRaisesRegex(fe_preview.FePreviewError, "does not exist"):
            fe_preview.preview_fe_package(self.folder / "absent" / "manifest.json")

    def test_a_set_cancel_event_stops_the_reading(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(fe_preview.AnalysisCancelled):
            fe_preview.preview_fe_package(self.plate("cancel"), cancel_event=cancel)


class PreviewWindowTests(_App):
    """The real main window: Inspect FE modes in the registry dialog (synthetic data, no process)."""

    def dialog(self, application):
        import menu_ui

        self.store = self.folder / "profile" / registry.STORE_NAME
        application.local_input_registry_store = self.store
        dialog = menu_ui.InputRegistryDialog(application)
        self.addCleanup(lambda: dialog.window.destroy() if dialog.window.winfo_exists() else None)
        return dialog

    def inspect(self, dialog, kind, path, label="entry"):
        entry, _ = registry.add_entry(self.store, kind, path, label)
        dialog.refresh(select=entry["id"])
        preview = dialog.inspect_selected()
        if preview is not None:
            self.addCleanup(preview.close)
        return preview

    def wait(self, preview, timeout=30.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and preview.preview is None and preview.error is None:
            self.root.update()
            time.sleep(0.02)

    def package(self, name="plate"):
        modes = [(n, f, described(f)) for n, f in enumerate(RIGID, 1)] + [(7, 19.07, described(19.07)),
                                                                   (8, 33.52, described(33.52))]
        return write_package(self.folder / name, modes)

    def test_inspect_shows_the_loaders_modes_and_changes_nothing(self):
        application = self.application()
        dialog = self.dialog(application)
        manifest = self.package()
        before = fingerprint(manifest.parent)
        fields = (application.abaqus_path.get(), application.experimental_path.get())
        with mock.patch.object(application, "_start", side_effect=AssertionError("nothing is run")):
            preview = self.inspect(dialog, registry.FE, manifest, "Synthetic plate")
            self.assertIn("Reading the extracted package", preview.status.get())
            self.wait(preview)
        self.assertIsNone(preview.error)
        rows = [preview.tree.item(i)["values"] for i in preview.tree.get_children()]
        dataset = abaqus_bridge.load_extracted_odb(manifest)
        self.assertEqual([int(row[0]) for row in rows], [int(m.number) for m in dataset.modes])
        self.assertEqual([str(row[1]) for row in rows], [f"{m.frequency_hz:.6g}" for m in dataset.modes])
        self.assertEqual(preview.status.get(), "8 modes loaded (1–8); no diagnostic messages.")
        self.assertIn("D:/synthetic/plate_model.odb", preview.source.get())
        self.assertEqual(preview.window.title(), "FE modes — Synthetic plate")
        self.assertEqual((application.abaqus_path.get(), application.experimental_path.get()), fields)
        self.assertFalse(application.running)
        self.assertEqual(fingerprint(manifest.parent), before)

    def test_an_odb_entry_asks_for_the_extracted_package(self):
        application = self.application()
        dialog = self.dialog(application)
        with mock.patch("tkinter.messagebox.showinfo") as shown:
            preview = self.inspect(dialog, registry.FE, self.other_odb)
        self.assertIsNone(preview)
        self.assertEqual(shown.call_args.args[1], fe_preview.ODB_NEEDS_PACKAGE)
        self.assertEqual(dialog.previews, [])

    def test_an_experimental_entry_or_a_missing_file_opens_nothing(self):
        application = self.application()
        dialog = self.dialog(application)
        self.assertIsNone(self.inspect(dialog, registry.EXPERIMENTAL, self.other_unv))
        self.assertIn("works on an FE entry", dialog.message.get())
        manifest = self.package("gone")
        entry, _ = registry.add_entry(self.store, registry.FE, manifest, "Gone")
        manifest.unlink()
        dialog.refresh(select=entry["id"])
        with mock.patch("tkinter.messagebox.showwarning") as warned:
            self.assertIsNone(dialog.inspect_selected())
        self.assertIn("'Gone' cannot be used", warned.call_args.args[1])

    def test_a_damaged_package_is_stated_in_the_window(self):
        application = self.application()
        dialog = self.dialog(application)
        manifest = self.package("damaged")
        (manifest.parent / "mode_0007.csv").unlink()
        preview = self.inspect(dialog, registry.FE, manifest)
        self.wait(preview)
        self.assertIn("incomplete", preview.error)
        self.assertEqual(preview.status.get(), "No FE modes can be shown.")
        self.assertIn("mode_0007.csv", preview.warnings.get("1.0", "end"))
        self.assertEqual(preview.tree.get_children(), ())

    def test_closing_the_window_while_reading_cancels_and_discards_the_outcome(self):
        application = self.application()
        dialog = self.dialog(application)
        manifest = self.package("slow")
        gate, entered = threading.Event(), threading.Event()
        real_loader = fe_preview.load_extracted_odb
        cancel_seen = []

        def slow_loader(path, cancel_event=None):
            entered.set()
            gate.wait(30)
            cancel_seen.append(cancel_event.is_set())
            return real_loader(path, cancel_event=cancel_event)  # the real loader stops on the set event

        errors = []
        self.root.report_callback_exception = lambda *exc: errors.append(exc[1])
        with mock.patch.object(fe_preview, "load_extracted_odb", side_effect=slow_loader):
            preview = self.inspect(dialog, registry.FE, manifest)
            self.assertTrue(entered.wait(10))
            for _ in range(5):  # the main window keeps processing events while the package is read
                self.root.update()
            self.assertIn("Reading", preview.status.get())
            preview.close()
            self.assertFalse(preview.window.winfo_exists())
            gate.set()
            preview.thread.join(10)
        self.assertFalse(preview.thread.is_alive())
        self.assertEqual(cancel_seen, [True])
        self.assertEqual(preview.results.get_nowait(), ("cancelled", None))
        for _ in range(int(3 * fe_preview_poll_seconds() / 0.02)):  # a poll after closing never touches the window
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(preview.preview)
        self.assertEqual(errors, [])


def fe_preview_poll_seconds() -> float:
    import menu_ui

    return menu_ui.FePreviewWindow.POLL_MS / 1000.0


if __name__ == "__main__":
    unittest.main()
