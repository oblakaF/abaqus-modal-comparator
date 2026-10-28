"""NEW-GUI.2: reading a chosen file for the new interface's preview (``new_gui.preview_model``), with no Qt.

The preview is the existing services' output, read with the application's importer chain: FE modes of an extracted
package; dataset-55 modal sets one table each, none chosen and nothing merged; dataset-2414 records with the
importer's classification; FRF peak-derived records PROVISIONAL. A plain .odb is not read. A read of a replaced or
cleared file is cancelled and its outcome discarded. Importing the model reads nothing, installs nothing and creates
no cache; the cache is created in an isolated folder only when a file is read. Synthetic temporary files only.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from new_gui import preview_model as pm  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import importer_runtime  # noqa: E402
from services import local_experimental_preview as xp  # noqa: E402
from services import local_fe_preview as fp  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from test_local_fe_preview import RIGID, described, write_package  # noqa: E402
from test_universal_hardening import write_2414_unv  # noqa: E402


def fingerprint(folder: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="new_gui2_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.inputs = self.folder / "inputs"
        self.inputs.mkdir()
        self.cache = self.folder / "cache"
        self.cache.mkdir()
        environment = mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.cache)})
        environment.start()
        self.addCleanup(environment.stop)
        no_process = mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a preview"))
        no_process.start()
        self.addCleanup(no_process.stop)

    def read(self, kind, path, cancel_event=None):
        return pm.run_read(kind, path, 1, cancel_event or threading.Event())

    def package(self, name="package"):
        return write_package(self.inputs / name, [(n, f, None) for n, f in enumerate(RIGID, 1)]
                             + [(7, 101.25, described(101.25)), (8, 133.5, described(133.5))])


class FeReadTests(_Folder):
    def test_the_fe_modes_are_the_services_unchanged(self):
        manifest = self.package()
        before = fingerprint(self.inputs)
        outcome = self.read(ws.FE, manifest)
        self.assertEqual((outcome.error, outcome.cancelled), ("", False))
        service = fp.preview_fe_package(manifest)
        self.assertEqual(outcome.preview.modes, service.modes)
        self.assertEqual(outcome.preview.warnings, service.warnings)
        view = pm.view_of(ws.FE, outcome.preview)
        section, = view.sections
        self.assertEqual(section.headers, pm.FE_HEADERS)
        self.assertEqual([row[0] for row in section.rows], [str(n) for n in range(1, 9)])  # rigid modes kept
        self.assertEqual([row[1] for row in section.rows], [fp.frequency_text(m) for m in service.modes])
        self.assertEqual(view.summary, fp.summary(service))
        self.assertEqual(view.paths, (("Package", str(manifest)), ("FE source", "D:/synthetic/plate_model.odb")))
        self.assertEqual(view.facts, ("Step: Frequency",))
        self.assertEqual(fingerprint(self.inputs), before)

    def test_loader_warnings_are_shown(self):
        manifest = write_package(self.inputs / "package", [(7, 101.25, described(101.25)),
                                                           (8, 140.0, described(133.5))])  # contradicting records
        outcome = self.read(ws.FE, manifest)
        service = fp.preview_fe_package(manifest)
        self.assertTrue(service.warnings)
        self.assertEqual(pm.view_of(ws.FE, outcome.preview).warnings, service.warnings)

    def test_a_plain_odb_is_not_read_and_abaqus_is_not_started(self):
        odb = self.inputs / "plate.odb"
        odb.write_bytes(b"synthetic odb; never opened")
        with mock.patch.object(fp, "preview_fe_package", side_effect=AssertionError("not read")):
            outcome = self.read(ws.FE, odb)
        self.assertEqual(outcome.error, pm.ODB_NOT_READ)
        self.assertIn("manifest.json", outcome.error)
        self.assertIn("Abaqus is not started", outcome.error)
        self.assertEqual(list(self.cache.rglob("*")), [])

    def test_a_damaged_package_is_a_message_not_an_exception(self):
        manifest = self.inputs / "manifest.json"
        manifest.write_text("{not json", encoding="utf-8")
        outcome = self.read(ws.FE, manifest)
        self.assertTrue(outcome.error.startswith("The extracted package cannot be read"))
        self.assertIsNone(outcome.preview)


class ExperimentalReadTests(_Folder):
    def test_several_dataset_55_sets_are_separate_and_none_is_chosen(self):
        path = S.write_experiment(self.inputs / "two_sets.unv", S.E0, S.G0, sets=(("bravo", 4), ("processing", 6)))
        outcome = self.read(ws.EXPERIMENTAL, path)
        service = xp.preview_experimental_file(path)
        self.assertEqual(outcome.preview, service)
        view = pm.view_of(ws.EXPERIMENTAL, outcome.preview)
        self.assertEqual([s.title for s in view.sections],
                         ["Modal set 1 of 2: bravo (bravo) — 4 records",
                          "Modal set 2 of 2: processing (processing) — 6 records"])
        for section, item in zip(view.sections, service.sets):
            self.assertEqual([(row[0], row[1]) for row in section.rows],
                             [(str(r.number), f"{r.frequency_hz:.6g}") for r in item.records])
            self.assertEqual([row[2] for row in section.rows], [r.label for r in item.records])
        self.assertEqual(view.sections[0].rows[0][0], "1")  # experimental mode 1 is shown, not excluded
        self.assertEqual(view.summary, xp.summary(service))

    def test_dataset_2414_records_keep_the_importer_classification(self):
        path = write_2414_unv(self.inputs / "records_2414.unv", [
            {"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
            {"analysis_type": 3, "mode": 8, "frequency": 41.25, "label": 2},
            {"analysis_type": 5, "mode": 9, "frequency": 25.0, "label": 3, "name": "Frequency response"}])
        outcome = self.read(ws.EXPERIMENTAL, path)
        view = pm.view_of(ws.EXPERIMENTAL, outcome.preview)
        section, = view.sections
        self.assertEqual([(row[0], row[1]) for row in section.rows], [("7", "23.5")])
        self.assertEqual([w.split(" (")[0] for w in view.warnings],
                         ["Dataset 2414 record 1: physical", "Dataset 2414 record 2: physical",
                          "Dataset 2414 record 3: non_modal, not loaded"])
        self.assertEqual(view.warnings[2], "Dataset 2414 record 3: non_modal, not loaded ("
                         + outcome.preview.record_classifications[2][3] + ")")  # the importer's reason
        self.assertTrue(any("complex eigenvalue data define no frequency" in n for n in section.notes))
        self.assertIn("Content: " + xp.KIND_TEXT[xp.DATASET_2414], view.facts)

    def test_frf_peak_records_are_provisional(self):
        path = F.write_frf_only(self.inputs / "frf_only.uff")
        outcome = self.read(ws.EXPERIMENTAL, path)
        view = pm.view_of(ws.EXPERIMENTAL, outcome.preview)
        section, = view.sections
        self.assertTrue(section.rows)
        self.assertEqual({row[2] for row in section.rows}, {"PROVISIONAL — NOT A VALIDATED FITTED MODE"})
        self.assertEqual(section.notes[0], pm.PROVISIONAL_NOTE)
        self.assertIn("NOT validated fitted modes", " ".join(view.facts))
        self.assertTrue(all(r.provisional for r in outcome.preview.sets[0].records))

    def test_lms_reads_its_companion_and_without_it_is_a_message(self):
        unv = S.write_experiment(self.inputs / "project.unv", S.E0, S.G0)
        lms = self.inputs / "project.lms"
        lms.write_bytes(b"synthetic LMS project")
        view = pm.view_of(ws.EXPERIMENTAL, self.read(ws.EXPERIMENTAL, lms).preview)
        self.assertEqual(view.paths, (("File", str(lms)), ("Data read from the companion", str(unv))))
        (self.inputs / "alone").mkdir()
        lonely = self.inputs / "alone" / "lonely.lms"
        lonely.write_bytes(b"synthetic LMS project")
        outcome = self.read(ws.EXPERIMENTAL, lonely)
        self.assertTrue(outcome.error)
        self.assertIsNone(outcome.preview)

    def test_a_damaged_file_is_a_message_not_an_exception(self):
        path = self.inputs / "damaged.unv"
        path.write_text("    -1\n  9999\nnot a dataset\n    -1\n", encoding="utf-8")
        outcome = self.read(ws.EXPERIMENTAL, path)
        self.assertTrue(outcome.error)
        self.assertFalse(outcome.cancelled)

    def test_a_set_cancel_event_gives_a_cancelled_outcome(self):
        path = S.write_experiment(self.inputs / "two_sets.unv", S.E0, S.G0, sets=(("bravo", 4), ("processing", 6)))
        event = threading.Event()
        event.set()
        outcome = self.read(ws.EXPERIMENTAL, path, event)
        self.assertEqual((outcome.cancelled, outcome.preview, outcome.error), (True, None, ""))

    def test_the_read_installs_the_application_importer_chain(self):
        self.read(ws.EXPERIMENTAL, F.write_frf_only(self.inputs / "frf_only.uff"))
        self.assertEqual(importer_runtime.installed_layers(), importer_runtime.LAYER_NAMES)


class SlotTests(unittest.TestCase):
    def outcome(self, slot, path, **kwargs):
        return pm.Outcome(ws.FE, Path(path), slot.token, **kwargs)

    def test_only_the_current_read_of_the_current_file_is_shown(self):
        slot = pm.InspectSlot()
        token, event = slot.start("a/manifest.json")
        stale = pm.Outcome(ws.FE, Path("a/manifest.json"), token, preview="old")
        slot.reset()  # the file was replaced or cleared
        self.assertTrue(event.is_set())
        self.assertFalse(slot.finish(stale))
        self.assertEqual((slot.state, slot.preview), (pm.IDLE, None))
        slot.start("b/manifest.json")
        self.assertFalse(slot.finish(stale))  # an earlier token
        self.assertFalse(slot.finish(self.outcome(slot, "a/manifest.json", preview="other file")))
        self.assertEqual(slot.state, pm.READING)
        self.assertTrue(slot.finish(self.outcome(slot, "b/manifest.json", preview="new")))
        self.assertEqual((slot.state, slot.preview), (pm.READ, "new"))
        self.assertFalse(slot.finish(self.outcome(slot, "b/manifest.json", preview="twice")))  # not reading
        self.assertEqual(slot.preview, "new")

    def test_failed_and_cancelled_reads(self):
        slot = pm.InspectSlot()
        slot.start("x.unv")
        self.assertTrue(slot.finish(self.outcome(slot, "x.unv", error="cannot be read")))
        self.assertEqual((slot.state, slot.message, slot.preview), (pm.FAILED, "cannot be read", None))
        slot.start("x.unv")
        self.assertEqual(slot.message, "")
        self.assertTrue(slot.finish(self.outcome(slot, "x.unv", cancelled=True)))
        self.assertEqual(slot.state, pm.IDLE)

    def test_a_new_read_cancels_the_running_one(self):
        slot = pm.InspectSlot()
        _, first = slot.start("x.unv")
        _, second = slot.start("x.unv")
        self.assertTrue(first.is_set())
        self.assertFalse(second.is_set())

    def test_an_unknown_kind_is_an_error(self):
        with self.assertRaises(ValueError):
            pm.read_preview("model", "x.unv")


class StartTests(unittest.TestCase):
    def test_importing_the_model_reads_installs_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import new_gui.preview_model, new_gui.workspace_state; "
                    "import universal_reader; "
                    "bad = sorted(m for m in sys.modules if m in ('main', 'tkinter', 'fast_cache', "
                    "'services.importer_runtime', 'services.local_fe_preview', 'services.local_experimental_preview', "
                    "'cmif_separation')); "
                    "print(','.join(bad) + '|' + universal_reader.load_universal_modal_file.__module__)")
            done = subprocess.run([sys.executable, "-c", code, str(ROOT / "src")], capture_output=True, text=True,
                                  timeout=120, env={**os.environ, "LOCALAPPDATA": folder})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), "|universal_reader")
            self.assertEqual(list(Path(folder).rglob("*")), [])

    def test_a_read_in_a_fresh_process_creates_the_cache_only_then_and_loads_no_old_program(self):
        with tempfile.TemporaryDirectory() as folder:
            uff = F.write_frf_only(Path(folder) / "frf_only.uff")
            cache = Path(folder) / "cache"
            cache.mkdir()
            code = ("import sys, threading; sys.path.insert(0, sys.argv[1]); import new_gui.preview_model as pm; "
                    "o = pm.run_read('EXPERIMENTAL', sys.argv[2], 1, threading.Event()); "
                    "bad = sorted(m for m in sys.modules if m in ('main', 'tkinter', 'app', 'home_dashboard')); "
                    "print(len(o.preview.sets[0].records), ','.join(bad))")
            done = subprocess.run([sys.executable, "-c", code, str(ROOT / "src"), str(uff)], capture_output=True,
                                  text=True, timeout=300, env={**os.environ, "LOCALAPPDATA": str(cache),
                                                               "MPLBACKEND": "Agg"})
            self.assertEqual(done.returncode, 0, done.stderr)
            count, bad = done.stdout.strip().split(" ", 1) if " " in done.stdout.strip() else (done.stdout.strip(), "")
            self.assertGreater(int(count), 0)
            self.assertEqual(bad, "")
            written = [p.name for p in cache.rglob("*") if p.is_file()]
            self.assertEqual(len(written), 1)
            self.assertTrue(written[0].startswith("unv_"))


if __name__ == "__main__":
    unittest.main()
