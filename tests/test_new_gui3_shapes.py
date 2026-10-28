"""NEW-GUI.3: one FE mode or experimental record of an inspected file drawn by the existing services (no Qt).

``new_gui.shape_model`` lists the loaded FE modes (rigid-body and elastic), the experimental sets and the records of
one set (record 1 included), and draws the one chosen by its position with
``local_fe_preview.render_fe_mode_shape`` / ``local_experimental_preview.render_record_shape``. The image and its
caption are the service's; refusals (a component that was not measured, points on one line) are the service's
reasons and leave no image; FRF peak records stay PROVISIONAL and ambiguous records keep the importer's warning.
Every request draws into its own temporary folder, which is removed afterwards. Nothing is read again, compared,
paired or written next to the inputs, and no process is started. Synthetic files and an isolated LOCALAPPDATA.
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

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from new_gui import preview_model as pm  # noqa: E402
from new_gui import shape_model as sm  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
import test_local_fe_preview as fe_support  # noqa: E402
from test_local_fe_preview import RIGID, described, write_package  # noqa: E402
from test_polymax_modal_sets import _geometry, _mode  # noqa: E402
from test_universal_hardening import write_2414_unv  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n"
PLANE = [("PART-1", n, 0.1 * (n % 3), 0.1 * (n // 3), 0.0) for n in range(1, 10)]  # nine nodes in a plane


def fingerprint(folder: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


def geometry_4():
    return {"type": 2411, "node_nums": np.array([1, 2, 3, 4]), "x": np.array([0.0, 1.0, 0.0, 1.0]),
            "y": np.array([0.0, 0.0, 1.0, 1.0]), "z": np.zeros(4)}


def mode_55_4(number, frequency, ambiguous=False):
    """A dataset-55 record on four points (Z only); without its analysis type the importer keeps it ambiguous."""
    record = _mode("Processing", number, frequency)
    record.update(node_nums=np.array([1, 2, 3, 4]), r1=np.zeros(4), r2=np.zeros(4),
                  r3=np.array([1.0, -0.5, 0.25, -1.0]) * number)
    if ambiguous:
        record.pop("analysis_type")
    return record


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="new_gui3_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.inputs = self.folder / "inputs"
        self.inputs.mkdir()
        cache = self.folder / "cache"
        cache.mkdir()
        for patcher in (mock.patch.dict(os.environ, {"LOCALAPPDATA": str(cache)}),
                        mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a shape"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.folders: list[Path] = []
        real_mkdtemp = tempfile.mkdtemp

        def recorded(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            if kwargs.get("prefix") == "new_gui_shape_":
                self.folders.append(Path(path))
            return path

        patcher = mock.patch.object(sm.tempfile, "mkdtemp", side_effect=recorded)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, kind, path):
        outcome = pm.run_read(kind, path, 1, threading.Event())
        self.assertEqual(outcome.error, "")
        return outcome.preview

    def draw(self, kind, source, index, component):
        outcome = sm.run_render(kind, source, index, component, 7, threading.Event())
        self.assertEqual(outcome.token, 7)
        self.assertFalse(any(folder.exists() for folder in self.folders))  # the request's folder is removed
        return outcome

    def service_lines(self, kind, source, index, component):
        target = self.folder / f"service_{len(list(self.folder.iterdir()))}"
        view = sm.render(kind, source, index, component, target)
        return tuple(view.lines), Path(view.image_path).read_bytes()


class FeShapeTests(_Folder):
    def package(self, nodes=PLANE):
        with mock.patch.object(fe_support, "NODES", nodes):
            return write_package(self.inputs / "package", [(n, f, None) for n, f in enumerate(RIGID, 1)]
                                 + [(7, 101.25, described(101.25)), (8, 133.5, described(133.5))])

    def test_every_loaded_mode_is_offered_rigid_and_first_elastic_included(self):
        preview = self.read(ws.FE, self.package())
        self.assertEqual(sm.fe_mode_options(preview),
                         [(i, f"Mode {m.number} — {m.frequency_hz:.6g} Hz") for i, m in enumerate(preview.modes)])
        self.assertEqual([m.number for m in preview.modes], list(range(1, 9)))
        from services import local_fe_preview as fp

        self.assertEqual(sm.fe_mode_facts(preview, 6),
                         ("FE mode 7", "Frequency: 101.25 Hz",
                          f"Frequency source: {fp.source_text(preview.modes[6])}", "FE nodes: 9"))

    def test_rigid_and_first_elastic_modes_are_drawn_by_the_service(self):
        manifest = self.package()
        before = fingerprint(self.inputs)
        preview = self.read(ws.FE, manifest)
        for index in (0, 5, 6):  # rigid-body modes 1 and 6, first elastic mode 7
            for component in sm.COMPONENTS:
                with self.subTest(mode=preview.modes[index].number, component=component):
                    outcome = self.draw(ws.FE, preview, index, component)
                    self.assertEqual(outcome.error, "")
                    self.assertTrue(outcome.image.startswith(PNG))
                    lines, image = self.service_lines(ws.FE, preview, index, component)
                    self.assertEqual(outcome.lines, lines)  # the service's caption, unchanged
                    self.assertEqual(outcome.lines[0].split(" — ")[0], f"FE mode {preview.modes[index].number}")
        self.assertEqual(fingerprint(self.inputs), before)

    def test_fe_nodes_on_one_line_have_no_normal_view(self):
        line = [("PART-1", n, 0.1 * n, 0.0, 0.0) for n in range(1, 6)]
        preview = self.read(ws.FE, self.package(nodes=line))
        refused = self.draw(ws.FE, preview, 6, "normal")
        self.assertEqual(refused.image, b"")
        self.assertTrue(refused.error.startswith("The FE nodes lie on one line: no best-fit plane"))
        self.assertEqual(self.draw(ws.FE, preview, 6, "z").error, "")  # the other components are drawn


class ExperimentalShapeTests(_Folder):
    def test_sets_are_chosen_explicitly_and_drawn_independently(self):
        path = S.write_experiment(self.inputs / "two.unv", S.E0, S.G0, sets=(("bravo", 4), ("processing", 6)))
        before = fingerprint(self.inputs)
        preview = self.read(ws.EXPERIMENTAL, path)
        self.assertEqual(sm.set_options(preview), [(0, preview.sets[0].title), (1, preview.sets[1].title)])
        first, second = preview.sets
        self.assertEqual(sm.record_options(first)[0], (0, f"Record 1: mode 1 — {first.records[0].frequency_hz:.6g} Hz"))
        self.assertEqual(len(sm.record_options(second)), 6)
        for chosen, set_title in ((first, first.title), (second, second.title)):
            outcome = self.draw(ws.EXPERIMENTAL, chosen, 0, "normal")  # record 1 of each set, not excluded
            self.assertEqual(outcome.error, "")
            self.assertTrue(outcome.image.startswith(PNG))
            self.assertIn(f"Record 1 of {set_title}", outcome.lines[1])
            self.assertEqual(outcome.lines, self.service_lines(ws.EXPERIMENTAL, chosen, 0, "normal")[0])
        self.assertEqual(sm.record_facts(first, 0)[2], f"Classification: {first.records[0].label}")
        self.assertIn(f"measured DOFs: {first.records[0].measured_dof_count}", sm.record_facts(first, 0)[3])
        self.assertEqual(fingerprint(self.inputs), before)

    def test_an_unmeasured_component_is_refused_and_no_value_is_created(self):
        chosen = self.read(ws.EXPERIMENTAL, S.write_experiment(self.inputs / "z.unv", S.E0, S.G0)).sets[0]
        for component in ("x", "y"):
            refused = self.draw(ws.EXPERIMENTAL, chosen, 0, component)
            self.assertEqual(refused.image, b"")
            self.assertIn("is not a measured component of this record", refused.error)
        drawn = self.draw(ws.EXPERIMENTAL, chosen, 0, "z")
        self.assertIn("Not measured: X, Y", drawn.lines[3])

    def test_dataset_2414_records(self):
        path = write_2414_unv(self.inputs / "real_2414.unv", [
            {"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
            {"analysis_type": 2, "mode": 9, "frequency": 47.25, "label": 2}])
        chosen = self.read(ws.EXPERIMENTAL, path).sets[0]
        outcome = self.draw(ws.EXPERIMENTAL, chosen, 1, "magnitude")
        self.assertEqual(outcome.error, "")
        self.assertIn("dataset 2414 record 2 (physical, importer)", outcome.lines[0])

    def test_ambiguous_records_keep_the_importer_warning(self):
        import universal_reader

        path = self.inputs / "ambiguous.unv"
        path.write_text("synthetic records", encoding="utf-8")
        datasets = [geometry_4(), mode_55_4(1, 10.0), mode_55_4(2, 20.0, ambiguous=True)]
        pm.read_preview(ws.EXPERIMENTAL, F.write_frf_only(self.inputs / "warm.uff"))  # the chain is installed
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            preview = self.read(ws.EXPERIMENTAL, path)
        chosen = preview.sets[0]
        warnings = sm.record_warnings(chosen, 1)
        self.assertTrue(warnings)
        self.assertTrue(all(w.lower().startswith("dataset 55 record 2") for w in warnings))
        self.assertEqual(sm.record_warnings(chosen, 0), ())
        outcome = self.draw(ws.EXPERIMENTAL, chosen, 1, "normal")
        self.assertTrue(outcome.lines[0].startswith("AMBIGUOUS (importer) — dataset 55 record 2"))
        self.assertIn("AMBIGUOUS (importer)", sm.record_facts(chosen, 1)[2])

    def test_frf_peak_records_are_provisional(self):
        chosen = self.read(ws.EXPERIMENTAL, F.write_frf_only(self.inputs / "frf.uff")).sets[0]
        self.assertTrue(all(sm.is_provisional(chosen, i) for i in range(len(chosen.records))))
        outcome = self.draw(ws.EXPERIMENTAL, chosen, 0, "normal")
        self.assertEqual(outcome.lines[0], sm.PROVISIONAL_TEXT)
        self.assertEqual(sm.record_facts(chosen, 0)[2], f"Classification: {sm.PROVISIONAL_TEXT}")

    def test_too_few_points_is_the_services_refusal(self):
        chosen = self.read(ws.EXPERIMENTAL, F.write_frf_only(self.inputs / "two.uff", points=2)).sets[0]
        refused = self.draw(ws.EXPERIMENTAL, chosen, 0, "normal")
        self.assertEqual(refused.image, b"")
        self.assertIn("needs at least 3 measured points", refused.error)


class RequestTests(_Folder):
    def test_a_set_cancel_event_gives_a_cancelled_outcome_and_no_folder_is_left(self):
        chosen = self.read(ws.EXPERIMENTAL, S.write_experiment(self.inputs / "c.unv", S.E0, S.G0)).sets[0]
        event = threading.Event()
        event.set()
        outcome = sm.run_render(ws.EXPERIMENTAL, chosen, 0, "normal", 3, event)
        self.assertEqual((outcome.cancelled, outcome.image, outcome.error), (True, b"", ""))
        self.assertFalse(any(folder.exists() for folder in self.folders))

    def test_a_cancel_during_the_drawing_discards_the_image(self):
        chosen = self.read(ws.EXPERIMENTAL, S.write_experiment(self.inputs / "c.unv", S.E0, S.G0)).sets[0]
        event = threading.Event()
        real = sm.render

        def cancelled_while_drawing(*args, **kwargs):
            view = real(*args, **kwargs)
            event.set()  # the choice changed while the service was drawing
            return view

        with mock.patch.object(sm, "render", cancelled_while_drawing):
            outcome = sm.run_render(ws.EXPERIMENTAL, chosen, 0, "normal", 3, event)
        self.assertTrue(outcome.cancelled)
        self.assertEqual(outcome.image, b"")
        self.assertFalse(any(folder.exists() for folder in self.folders))

    def test_only_the_current_request_is_shown(self):
        slot = sm.ShapeSlot()
        token, event = slot.start((None, 0, "normal"))
        stale = sm.ShapeOutcome(ws.FE, token, image=PNG)
        slot.reset()  # the choice changed
        self.assertTrue(event.is_set())
        self.assertFalse(slot.finish(stale))
        self.assertEqual((slot.state, slot.outcome), (sm.IDLE, None))
        token, _ = slot.start((None, 1, "z"))
        self.assertFalse(slot.finish(stale))
        self.assertTrue(slot.finish(sm.ShapeOutcome(ws.FE, token, image=PNG, lines=("FE mode 2",))))
        self.assertEqual(slot.state, sm.SHOWN)
        self.assertFalse(slot.finish(sm.ShapeOutcome(ws.FE, token, image=b"twice")))
        token, _ = slot.start((None, 1, "x"))
        self.assertTrue(slot.finish(sm.ShapeOutcome(ws.FE, token, error="refused")))
        self.assertEqual((slot.state, slot.outcome.error), (sm.REFUSED, "refused"))
        token, _ = slot.start((None, 1, "x"))
        self.assertTrue(slot.finish(sm.ShapeOutcome(ws.FE, token, cancelled=True)))
        self.assertEqual(slot.state, sm.IDLE)

    def test_unknown_kind_or_component_is_an_error(self):
        with self.assertRaises(ValueError):
            sm.render("model", None, 0, "normal", self.folder)
        with self.assertRaises(ValueError):
            sm.render(ws.FE, None, 0, "rx", self.folder)

    def test_no_mac_no_pairing_and_nothing_read_again(self):
        with mock.patch.object(fe_support, "NODES", PLANE):
            manifest = write_package(self.inputs / "package", [(7, 101.25, described(101.25))])
        preview = self.read(ws.FE, manifest)
        chosen = self.read(ws.EXPERIMENTAL, S.write_experiment(self.inputs / "c.unv", S.E0, S.G0)).sets[0]
        import abaqus_bridge
        import modal_core
        import universal_reader

        guards = [mock.patch.object(modal_core, "modal_assurance_criterion", side_effect=AssertionError("MAC")),
                  mock.patch.object(abaqus_bridge, "load_extracted_odb", side_effect=AssertionError("read again")),
                  mock.patch.object(universal_reader, "load_universal_modal_file",
                                    side_effect=AssertionError("read again"))]
        for guard in guards:
            guard.start()
            self.addCleanup(guard.stop)
        self.assertEqual(self.draw(ws.FE, preview, 0, "normal").error, "")
        self.assertEqual(self.draw(ws.EXPERIMENTAL, chosen, 0, "normal").error, "")


class StartTests(unittest.TestCase):
    def test_importing_the_shape_model_loads_no_service_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import new_gui.shape_model; "
                    "bad = sorted(m for m in sys.modules if m in ('main', 'tkinter', 'matplotlib', "
                    "'services.local_fe_preview', 'services.local_experimental_preview', 'fast_cache')); "
                    "print(','.join(bad))")
            done = subprocess.run([sys.executable, "-c", code, str(ROOT / "src")], capture_output=True, text=True,
                                  timeout=120, env={**os.environ, "LOCALAPPDATA": folder})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), "")
            self.assertEqual(list(Path(folder).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
