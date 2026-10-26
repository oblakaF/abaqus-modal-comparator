"""P7: ODB + UNV/UFF data stay inspectable whatever the physical registration (no Abaqus, synthetic data).

- FE modes are viewed on their own nodes, by mode number, component and navigation, without any orientation;
- fitted experimental modes (dataset 55) and FRF peak-derived response snapshots (dataset 58 only) are viewed on their
  own measured points, the snapshots labelled "NOT a validated fitted mode shape";
- an ambiguous orientation gives a usable result (frequencies, separate views) without an automatic dialog, MAC or
  overlay; the orientation can still be confirmed on request;
- an unusable experimental file keeps the FE modes available and says why;
- a verified registration keeps the gated comparison and MAC unchanged;
- a new run never shows the previous run's views, and nothing starts a process.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from modal_core import ModalDataset, ModeShape  # noqa: E402
from reviewed_core import GeometryOrientationAmbiguousError  # noqa: E402
from services import modal_data_viewer as viewer  # noqa: E402
from services import new_odb_comparison as new  # noqa: E402


def _no_process(*_args, **_kwargs):
    raise AssertionError("the viewer and the diagnostic must never start Abaqus or any process")


def load_unv(path: Path, modal_set=None) -> ModalDataset:
    from application_layers import install_application_layers

    install_application_layers()
    from universal_reader import load_universal_modal_file

    return load_universal_modal_file(path, modal_set=modal_set)


def fe_plate() -> ModalDataset:
    """Abaqus-like modes of the synthetic plate (rigid + elastic), as an extraction would give them."""
    fake = S.FakeAbaqus()
    folder = Path(tempfile.mkdtemp(prefix="p7_fe_"))
    odb = folder / "plate.odb"
    odb.write_text(json.dumps({"E1": S.E0, "E2": S.E0, "G12": S.G0}))
    dataset = fake.extract(odb, folder, 9)
    shutil.rmtree(folder, ignore_errors=True)
    return dataset


def ambiguity(count: int = 8) -> GeometryOrientationAmbiguousError:
    return GeometryOrientationAmbiguousError(f"{count} physically distinct orientation/registration candidates",
                                             [{"candidate_id": f"geometry-{k}"} for k in range(count)])


class _Files(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="p7_viewer_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.fe = fe_plate()
        self.fitted_path = S.write_experiment(self.folder / "fitted.unv", S.E0, S.G0)
        self.frf_path = F.write_frf_only(self.folder / "frf_only.uff")
        (self.folder / "plate.odb").write_bytes(b"synthetic ODB stand-in; never opened")
        for target in ("subprocess.Popen",):
            patcher = mock.patch(target, side_effect=_no_process)
            patcher.start()
            self.addCleanup(patcher.stop)


# ----------------------------------------------------------------------------- the service

class FeViewerTests(_Files):
    def test_every_extracted_mode_is_viewable_by_number_and_component(self):
        entries = viewer.viewer_modes(self.fe, viewer.FE)
        self.assertEqual([e.number for e in entries], list(range(1, 10)))
        self.assertTrue(all(e.classification == viewer.FE_MODE and e.spatial_available for e in entries))
        self.assertEqual(entries[3].label(), f"FE mode 4 — {entries[3].frequency_hz:.3f} Hz")
        for component in viewer.COMPONENTS:
            path, entry = viewer.render_viewer_mode(self.fe, viewer.FE, 5, component, self.folder / "views")
            self.assertTrue(path.exists() and path.stat().st_size > 1000, component)
            self.assertEqual(entry.number, 5)
        mode = viewer.mode_by_number(self.fe, 5)
        self.assertTrue(np.allclose(viewer.component_values(mode, "z"), mode.vectors[:, 2]))
        self.assertTrue(np.allclose(viewer.component_values(mode, "magnitude"), np.abs(mode.vectors[:, 2])))
        self.assertTrue(np.allclose(np.abs(viewer.component_values(mode, "normal")), np.abs(mode.vectors[:, 2])))
        with self.assertRaises(KeyError):
            viewer.mode_by_number(self.fe, 99)
        with self.assertRaises(ValueError):
            viewer.component_values(mode, "u4")

    def test_large_fe_models_are_drawn_on_a_display_grid(self):
        count = viewer.DISPLAY_GRID_THRESHOLD + 1000
        rng = np.random.default_rng(3)
        coordinates = np.column_stack([rng.uniform(0, 300, count), rng.uniform(0, 300, count),
                                       rng.uniform(0, 20, count)])
        vectors = np.zeros((count, 3))
        vectors[:, 2] = np.sin(coordinates[:, 0] / 50.0)
        big = ModalDataset("FE", self.folder / "big.odb", [ModeShape(7, 58.1, np.arange(count), coordinates, vectors)])
        path, _ = viewer.render_viewer_mode(big, viewer.FE, 7, "normal", self.folder / "views")
        self.assertTrue(path.exists())


class ExperimentalViewerTests(_Files):
    def test_fitted_modes_are_listed_with_their_source(self):
        experimental = load_unv(self.fitted_path)
        entries = viewer.viewer_modes(experimental, viewer.EXPERIMENTAL)
        self.assertEqual(len(entries), len(S.MODES))
        self.assertTrue(all(e.classification == viewer.FITTED_MODE for e in entries))
        self.assertIn("curve-fitted experimental mode (dataset 55, modal set", entries[0].source_text)
        self.assertTrue(entries[0].label().startswith("Experimental mode 1"))
        path, _ = viewer.render_viewer_mode(experimental, viewer.EXPERIMENTAL, 2, "normal", self.folder / "views")
        self.assertTrue(path.exists())
        self.assertNotIn("PROVISIONAL", viewer.experimental_frequency_source(experimental))

    def test_dataset_58_only_gives_labelled_frf_peak_snapshots(self):
        experimental = load_unv(self.frf_path)
        entries = viewer.viewer_modes(experimental, viewer.EXPERIMENTAL)
        self.assertEqual(len(entries), F.peak_count())
        for entry in entries:
            self.assertEqual(entry.classification, viewer.FRF_PEAK_SNAPSHOT)
            self.assertEqual(entry.source_text, "FRF peak-derived response snapshot — NOT a validated fitted mode shape")
            self.assertTrue(entry.label().startswith("FRF peak "))
            self.assertAlmostEqual(entry.quality["mean_coherence"], 0.97, places=6)  # coherence preserved
            self.assertIn("phase_complexity_ratio", entry.quality)
            self.assertEqual(entry.axes, ("z",))
            self.assertTrue(entry.spatial_available)
        path, _ = viewer.render_viewer_mode(experimental, viewer.EXPERIMENTAL, 1, "normal", self.folder / "views")
        self.assertTrue(path.exists())
        self.assertIn("PROVISIONAL", viewer.experimental_frequency_source(experimental))
        diagnostic = new.frequency_only_diagnostic(self.fe, experimental, "orientation ambiguous")
        text = "\n".join(diagnostic.text_lines())
        self.assertIn("EXPERIMENTAL FRF RESONANCE-PEAK CANDIDATES (dataset 58; PROVISIONAL", text)
        self.assertNotIn("POLYMAX", text)
        self.assertEqual({row[8] for row in new.frequency_only_table_rows(diagnostic)},
                         {"FREQUENCY ONLY — FRF peak (provisional), not a pair"})
        self.assertEqual(diagnostic.to_dict()["mac"], "NOT_COMPUTED")

    def test_too_few_channels_explain_why_there_is_no_spatial_view(self):
        experimental = load_unv(F.write_frf_only(self.folder / "two_points.uff", points=2))
        entry = viewer.viewer_modes(experimental, viewer.EXPERIMENTAL)[0]
        self.assertFalse(entry.spatial_available)
        self.assertIn("insufficient nodal channels", entry.spatial_reason)
        with self.assertRaises(ValueError) as caught:
            viewer.render_viewer_mode(experimental, viewer.EXPERIMENTAL, entry.number, "normal", self.folder)
        self.assertIn("no spatial view", str(caught.exception))

    def test_several_modal_sets_are_never_mixed(self):  # E
        path = S.write_experiment(self.folder / "two_sets.unv", S.E0, S.G0, sets=(("PolyMAX A", 6), ("PolyMAX B", 4)))
        from polymax_ui import validate_modal_set_selection
        from universal_reader import discover_experimental_modal_sets

        sets = discover_experimental_modal_sets(path)
        self.assertEqual(len(sets), 2)
        with self.assertRaises(ValueError):
            validate_modal_set_selection(sets, "")  # an explicit choice is required
        with self.assertRaises(ValueError):
            load_unv(path)
        chosen = load_unv(path, modal_set=sets[1].key)
        entries = viewer.viewer_modes(chosen, viewer.EXPERIMENTAL)
        self.assertEqual(len(entries), len(sets[1].modes))
        self.assertTrue(all(sets[1].display_name in e.source_text for e in entries))


def fe_line(count: int = 8) -> ModalDataset:
    """FE modes of a beam whose nodes lie on one line (U3 bending, U1 axial)."""
    x = np.linspace(0.0, 0.35, count)
    coordinates = np.column_stack([x, np.zeros(count), np.zeros(count)])
    bending = np.column_stack([np.zeros(count), np.zeros(count), np.sin(np.pi * x / 0.35)])
    axial = np.column_stack([np.cos(np.pi * x / 0.35), np.zeros(count), np.zeros(count)])
    return ModalDataset("FE", Path("beam.odb"), [ModeShape(1, 41.0, np.arange(1, count + 1), coordinates, bending),
                                                 ModeShape(2, 97.0, np.arange(1, count + 1), coordinates, axial)])


class CollinearNormalTests(_Files):
    """APP-DATA.6: no arbitrary normal for points on one line; the other components and planar data are unchanged."""

    def test_the_geometric_rule(self):
        line = np.column_stack([np.linspace(0.0, 1.0, 5), np.zeros(5), np.zeros(5)])
        self.assertTrue(viewer.collinear_points(line))
        self.assertTrue(viewer.collinear_points(line @ np.array([[0.6, 0.8, 0.0], [0.8, -0.6, 0.0], [0, 0, 1]])))
        plate = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])
        self.assertFalse(viewer.collinear_points(plate))
        bent = line.copy()
        bent[2, 1] = 1.0e-8  # second singular value ~ 1e-8 of the first: within the 1e-6 rule, still a line
        self.assertTrue(viewer.collinear_points(bent))
        bent[2, 1] = 1.0e-4  # beyond the rule: a (thin) plane
        self.assertFalse(viewer.collinear_points(bent))
        self.assertTrue(viewer.collinear_points(line[:2]))  # fewer than three points span no plane
        self.assertTrue(viewer.collinear_points(np.vstack([line[:2], [[np.nan, 1.0, 0.0]]])))  # finite points only
        self.assertEqual(viewer.COLLINEAR_TOLERANCE, 1.0e-6)

    def test_fe_nodes_on_one_line_have_no_out_of_plane_view(self):
        beam = fe_line()
        self.assertTrue(all(entry.spatial_available for entry in viewer.viewer_modes(beam, viewer.FE)))
        for number in (1, 2):
            with self.assertRaises(ValueError) as caught:
                viewer.render_viewer_mode(beam, viewer.FE, number, "normal", self.folder / "views")
            self.assertIn(f"FE mode {number} — ", str(caught.exception))
            self.assertIn("no out-of-plane view — the points lie on one line", str(caught.exception))
            with self.assertRaisesRegex(ValueError, "No out-of-plane component: the points lie on one line"):
                viewer.component_values(viewer.mode_by_number(beam, number), "normal")
        self.assertFalse((self.folder / "views").exists() and any((self.folder / "views").iterdir()))
        for component in ("magnitude", "x", "y", "z"):  # the other components stay available on the line
            path, entry = viewer.render_viewer_mode(beam, viewer.FE, 1, component, self.folder / "views")
            self.assertTrue(path.exists() and path.stat().st_size > 1000, component)
        np.testing.assert_allclose(viewer.component_values(beam.modes[0], "z"), beam.modes[0].vectors[:, 2])

    def test_experimental_points_on_one_line_keep_their_labels(self):
        experimental = load_unv(F.write_frf_only(self.folder / "line.uff", points=5))  # the first grid row: y = 0
        entry = viewer.viewer_modes(experimental, viewer.EXPERIMENTAL)[0]
        self.assertEqual(entry.classification, viewer.FRF_PEAK_SNAPSHOT)  # PROVISIONAL snapshot, as before
        self.assertTrue(entry.spatial_available)
        self.assertIn("PROVISIONAL", viewer.experimental_frequency_source(experimental))
        with self.assertRaises(ValueError) as caught:
            viewer.render_viewer_mode(experimental, viewer.EXPERIMENTAL, entry.number, "normal", self.folder)
        self.assertIn(f"{entry.label()}: no out-of-plane view — the points lie on one line", str(caught.exception))
        for component in ("magnitude", "z"):
            path, _ = viewer.render_viewer_mode(experimental, viewer.EXPERIMENTAL, entry.number, component,
                                                self.folder / "views")
            self.assertTrue(path.exists())

    def test_planar_and_three_dimensional_geometry_keep_their_normal(self):
        mode = viewer.mode_by_number(self.fe, 5)  # the synthetic plate, as in the tests above
        self.assertTrue(viewer.out_of_plane_available(mode))
        np.testing.assert_allclose(np.abs(viewer.component_values(mode, "normal")), np.abs(mode.vectors[:, 2]))
        tilted = ModeShape(5, mode.frequency_hz, mode.node_ids, mode.coordinates @ np.array(
            [[1.0, 0.0, 0.0], [0.0, 0.8, 0.6], [0.0, -0.6, 0.8]]), mode.vectors @ np.array(
            [[1.0, 0.0, 0.0], [0.0, 0.8, 0.6], [0.0, -0.6, 0.8]]))  # the same plate, rotated in space
        np.testing.assert_allclose(np.abs(viewer.component_values(tilted, "normal")), np.abs(mode.vectors[:, 2]),
                                   atol=1.0e-9)
        rng = np.random.default_rng(5)
        cloud = rng.uniform(0.0, 1.0, (40, 3))  # a three-dimensional point cloud: its best-fit plane, as before
        solid = ModalDataset("FE", Path("solid.odb"), [ModeShape(1, 30.0, np.arange(40), cloud, rng.normal(size=(40, 3)))])
        self.assertTrue(viewer.out_of_plane_available(solid.modes[0]))
        path, _ = viewer.render_viewer_mode(solid, viewer.FE, 1, "normal", self.folder / "views")
        self.assertTrue(path.exists())

    def test_fewer_than_three_points_keep_the_previous_refusal(self):
        experimental = load_unv(F.write_frf_only(self.folder / "two_points.uff", points=2))
        entry = viewer.viewer_modes(experimental, viewer.EXPERIMENTAL)[0]
        with self.assertRaises(ValueError) as caught:
            viewer.render_viewer_mode(experimental, viewer.EXPERIMENTAL, entry.number, "normal", self.folder)
        self.assertIn("no spatial view — only 2 point(s)", str(caught.exception))


class InventoryTests(_Files):
    def test_inventory_and_saved_package_state_what_is_not_correlated(self):
        experimental = load_unv(self.frf_path)
        loaded = viewer.LoadedModalData(self.fe, experimental, registration=viewer.AMBIGUOUS, reason="8 orientations",
                                        frequency_diagnostic=new.frequency_only_diagnostic(self.fe, experimental, "x"))
        inventory = loaded.inventory()
        self.assertEqual((inventory["mac"], inventory["physical_registration"]), ("NOT_COMPUTED", "AMBIGUOUS"))
        self.assertEqual(inventory["correlation"], viewer.NOT_CORRELATED)
        self.assertEqual(inventory["fe"]["mode_count"], 9)
        self.assertEqual(inventory["experimental"]["frf"]["coherence_status"], "computed")
        paths = viewer.write_diagnostic_package(self.folder / "out", inventory, loaded.frequency_diagnostic)
        self.assertEqual(sorted(paths), ["csv", "frequency_only", "frequency_only_text", "inventory"])
        rows = paths["csv"].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 1 + 9 + F.peak_count())
        self.assertFalse(any(p.suffix == ".inp" for p in (self.folder / "out").iterdir()))
        fe_only = viewer.LoadedModalData(self.fe, None, experimental_error="no modal vectors").inventory()
        self.assertEqual((fe_only["experimental"]["mode_count"], fe_only["experimental"]["import_error"]),
                         (0, "no modal vectors"))


# ----------------------------------------------------------------------------- the analysis worker

class WorkerTests(_Files):
    def run_worker(self, experimental=None, *, compare=None, import_error=None):
        import main
        import runtime_hardening

        failures, completed = [], []

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        application = SimpleNamespace(
            root=Root(), _analysis_cancel_event=threading.Event(), _owned_analysis_process=None,
            _set_analysis_stage=lambda *_: None, _failed=failures.append, _complete=completed.append,
            _orientation_ambiguous=failures.append, _governed_registration_requested=False,
            _active_orientation_selection=None, _write_summary=lambda *_: None)
        loader = (mock.patch.object(runtime_hardening, "load_universal_modal_file", side_effect=import_error)
                  if import_error else
                  mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=experimental))
        refusal = new.GeometryReuseRefusal("not an accepted registration")
        with tempfile.TemporaryDirectory() as directory, loader, \
                mock.patch.object(runtime_hardening, "bind_registration_by_fe_geometry", side_effect=refusal), \
                mock.patch.object(main.app, "load_or_extract_odb", return_value=self.fe), \
                mock.patch.object(main.app, "compare_modal_datasets", side_effect=compare), \
                mock.patch.object(main.app, "render_mac_matrix"), \
                mock.patch.object(main.app, "render_frequency_comparison"), \
                mock.patch("enhanced_reporting.render_frf_diagnostics"), \
                mock.patch("enhanced_reporting.render_verified_mac_matrix"), \
                mock.patch.object(main.app, "write_no_pair_diagnostics"):
            workspace = Path(directory)
            main.app.ModalComparatorApp._worker(application, self.folder / "plate.odb", self.frf_path, workspace,
                                                1, 9, "abaqus", 1.0, None)
            written = {path.name: json.loads(path.read_text(encoding="utf-8"))
                       for path in workspace.rglob("*.json")}
        return failures, completed, written

    def test_ambiguity_keeps_both_datasets_for_viewing(self):  # B / C
        experimental = load_unv(self.frf_path)

        def ambiguous(*_args, **_kwargs):
            raise ambiguity()

        failures, completed, written = self.run_worker(experimental, compare=ambiguous)
        (error,) = failures
        loaded = error.loaded_modal_data
        self.assertIs(loaded.abaqus, self.fe)
        self.assertIs(loaded.experimental, experimental)
        self.assertEqual(loaded.registration, viewer.AMBIGUOUS)
        self.assertIs(loaded.frequency_diagnostic, error.frequency_only_diagnostic)
        self.assertTrue(loaded.frequency_diagnostic.provisional_experimental)
        self.assertEqual(written["modal_data_inventory.json"]["mac"], "NOT_COMPUTED")
        self.assertEqual(completed, [])

    def test_unusable_experimental_file_keeps_the_fe_modes(self):  # D
        failures, completed, written = self.run_worker(
            import_error=ValueError("No experimental modal vectors or FRFs were found in the UNV/UFF file."))
        (error,) = failures
        self.assertIsInstance(error, viewer.ExperimentalDataUnavailable)
        loaded = error.loaded_modal_data
        self.assertIs(loaded.abaqus, self.fe)
        self.assertIsNone(loaded.experimental)
        self.assertIn("No experimental modal vectors", loaded.experimental_error)
        self.assertEqual(written["modal_data_inventory.json"]["fe"]["mode_count"], 9)

    def test_an_established_comparison_carries_its_loaded_data(self):  # A
        experimental = load_unv(self.fitted_path)
        result = SimpleNamespace(metadata={}, warnings=[], pairs=[])
        failures, completed, _ = self.run_worker(experimental, compare=lambda *_a, **_k: result)
        self.assertEqual(failures, [])
        (done,) = completed
        self.assertEqual(done.loaded_modal_data.registration, viewer.ESTABLISHED)
        self.assertIs(done.loaded_modal_data.experimental, experimental)


# ----------------------------------------------------------------------------- the main window

class WindowTests(_Files):
    def application(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(lambda: root.destroy() if root.winfo_exists() else None)
        self.addCleanup(lambda: [root.after_cancel(job) for job in root.tk.splitlist(root.tk.call("after", "info"))])
        root.withdraw()
        import main
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            application = main.app.ModalComparatorApp(root)
        application.mode_viewer.threaded = False  # deterministic rendering in tests
        application._post_to_ui = lambda callback: callback() or True
        application.mode_viewer.post = application._post_to_ui
        self.root = root
        return application

    def loaded(self, experimental, registration=viewer.AMBIGUOUS):
        diagnostic = new.frequency_only_diagnostic(self.fe, experimental, "8 orientations") if experimental else None
        return viewer.LoadedModalData(self.fe, experimental, directory=self.folder / "views",
                                      registration=registration, reason="8 orientations",
                                      frequency_diagnostic=diagnostic)

    def toplevels(self):
        import tkinter as tk

        return [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]

    def test_ambiguity_gives_a_usable_result_without_a_dialog(self):  # B
        application = self.application()
        experimental = load_unv(self.fitted_path)
        error = ambiguity()
        error.frequency_only_diagnostic = new.frequency_only_diagnostic(self.fe, experimental, "8 orientations")
        error.loaded_modal_data = self.loaded(experimental)
        with mock.patch("tkinter.messagebox.showerror") as shown, \
                mock.patch.object(application, "_show_orientation_ambiguity_dialog") as dialog:
            application._failed(error)
            self.root.update_idletasks()
            dialog.assert_not_called()
            self.assertEqual(self.toplevels(), [])  # no automatic dialog, no second root
            panel = application.mode_viewer
            self.assertEqual(application.shape_view.get(), "individual")
            self.assertEqual(application.tabs.select(), str(application.shape_tab))
            self.assertEqual(len(panel.fe.entries), 9)
            self.assertEqual(len(panel.experimental.entries), len(S.MODES))
            self.assertIsNotNone(panel.fe.photo)
            self.assertIsNotNone(panel.experimental.photo)
            self.assertIn("no MAC was computed", panel.banner.cget("text"))
            self.assertEqual(application.metric_mac.cget("text"), "not computed")
            self.assertEqual(application.item_to_pair, {})  # frequency rows are never selectable pairs
            panel.fe.step(1)
            self.assertTrue(panel.fe.choice.get().startswith("FE mode 2"))
            self.assertTrue(panel.fe.select_number(7))
            panel.confirm_button.invoke()  # the orientation can still be confirmed, on request only
            dialog.assert_called_once_with(error)
        shown.assert_not_called()

    def test_dataset_58_snapshot_is_labelled_in_the_window(self):  # C
        application = self.application()
        experimental = load_unv(self.frf_path)
        error = ambiguity()
        error.loaded_modal_data = self.loaded(experimental)
        application._failed(error)
        panel = application.mode_viewer.experimental
        self.assertTrue(panel.choice.get().startswith("FRF peak 1"))
        self.assertIn("NOT a validated fitted mode shape", panel.info.cget("text"))
        self.assertIn("mean coherence 0.970", panel.info.cget("text"))
        two = load_unv(F.write_frf_only(self.folder / "two_points.uff", points=2))
        application.mode_viewer.set_data(self.loaded(two), "two points")
        self.assertIn("insufficient nodal channels", panel.image.cget("text"))

    def test_unusable_experimental_file_keeps_fe_modes_in_the_window(self):  # D
        from ui_policy import AnalysisState

        application = self.application()
        error = viewer.ExperimentalDataUnavailable("The experimental file could not be used")
        error.loaded_modal_data = viewer.LoadedModalData(self.fe, None, experimental_error="no modal vectors",
                                                         directory=self.folder / "views")
        application.running = True
        with mock.patch("tkinter.messagebox.showerror") as shown:
            application._failed(error)
        shown.assert_not_called()  # a stated limitation, not an error dead end
        self.assertIs(application.analysis_state, AnalysisState.DIAGNOSTIC)
        self.assertFalse(application.running)
        panel = application.mode_viewer
        self.assertEqual(len(panel.fe.entries), 9)
        self.assertIsNotNone(panel.fe.photo)
        self.assertIn("no modal vectors", panel.experimental.image.cget("text"))
        self.assertIn("no usable modal or FRF data", panel.banner.cget("text"))

    def test_verified_comparison_keeps_pairs_and_mac(self):  # A
        from test_g2c_archived_sensitivity_evidence import World
        from test_g2d1_governed_registration import experimental_dataset, fe_dataset
        from test_new_odb_comparison import new_odb_dataset

        import main

        world = World(str(self.folder))
        odb, unv = world.files["SP02"]
        baseline = fe_dataset(odb)
        experimental = experimental_dataset(unv, baseline)
        target = self.folder / "data" / "SP02_new_model.odb"
        target.write_bytes(b"another FE result with the accepted mesh " * 4000)
        fe = new_odb_dataset(target, baseline)
        with world.pins():
            reuse = functools.partial(new.bind_registration_by_fe_geometry, repo_root=world.root)(unv, fe, experimental)
        result = main.app.compare_modal_datasets(fe, experimental, frozen_registration=reuse.registration)
        self.assertTrue(result.pairs)
        # the accepted SP-02 / SP-13 registrations record their camera-grid scales; the synthetic world does not
        result.geometry.calibration_details.setdefault("scale_x", 1.0)
        result.geometry.calibration_details.setdefault("scale_y", 1.0)
        result.loaded_modal_data = viewer.LoadedModalData(fe, experimental, directory=self.folder / "views",
                                                          registration=viewer.ESTABLISHED)
        application = self.application()
        application.cache = self.folder / "cache"
        application._analysis_cancel_event = threading.Event()
        application._complete(result)
        rows = [application.table.item(k, "values") for k in application.table.get_children()]
        self.assertEqual(len(rows), len(result.pairs))
        self.assertTrue(all(row[5] not in ("not computed", "—", "") for row in rows))  # MAC values shown
        self.assertEqual(application.shape_view.get(), "pair")  # the gated pair view stays the default
        self.assertEqual(application.mode_viewer.loaded.registration, viewer.ESTABLISHED)
        self.assertIn("Gated FE–experiment pairs and MAC", application.mode_viewer.banner.cget("text"))
        application._show_shape_view("individual")
        self.assertEqual(len(application.mode_viewer.fe.entries), len(fe.modes))
        application._show_shape_view("pair")
        self.assertTrue(application.pair_title.winfo_manager())  # the pair widgets are restored

    def test_a_new_run_never_shows_the_previous_views(self):  # F
        application = self.application()
        error = ambiguity()
        error.loaded_modal_data = self.loaded(load_unv(self.fitted_path))
        application._failed(error)
        panel = application.mode_viewer
        stale_generation = panel.fe.generation
        stale_path = panel.fe.image_path
        application._clear_result_presentation("Analysis is running; previous results are no longer active.")
        self.assertIsNone(panel.loaded)
        self.assertEqual((panel.fe.entries, panel.experimental.entries), ([], []))
        self.assertEqual(str(panel.confirm_button.cget("state")), "disabled")
        self.assertEqual(str(panel.save_button.cget("state")), "disabled")
        self.assertEqual(application.shape_view.get(), "pair")
        panel.fe._rendered(stale_generation, stale_path, None)  # a late render of the old run is ignored
        self.assertIsNone(panel.fe.photo)
        self.assertIn("previous results are no longer active", panel.fe.image.cget("text"))
        self.assertIs(panel.frame.winfo_toplevel(), self.root)

    def test_a_resize_while_drawing_never_reshows_the_previous_view(self):  # P8 acceptance finding
        application = self.application()
        error = ambiguity()
        error.loaded_modal_data = self.loaded(load_unv(self.fitted_path))
        application._failed(error)
        pane = application.mode_viewer.fe
        self.assertIsNotNone(pane.image_path)  # mode 1 is shown
        deferred = []
        application.mode_viewer.post = lambda callback: deferred.append(callback) or True  # mode 5 still drawing
        pane.select_number(5)
        pane._fit()  # a <Configure> re-fit arrives while the new view is drawn
        self.assertIsNone(pane.photo)  # the old picture never reappears under the new selection
        self.assertIn("Drawing FE mode 5", pane.image.cget("text"))
        for callback in deferred:
            callback()
        self.assertIsNotNone(pane.photo)
        self.assertTrue(pane.image_path.name.startswith("fe_0005"), pane.image_path)

    def test_points_on_one_line_state_why_and_never_keep_the_previous_picture(self):  # APP-DATA.6
        application = self.application()
        error = ambiguity()
        error.loaded_modal_data = self.loaded(load_unv(self.frf_path))  # a plate: both panes show a picture
        application._failed(error)
        panel = application.mode_viewer
        self.assertIsNotNone(panel.fe.photo)
        self.assertIsNotNone(panel.experimental.photo)
        line = load_unv(F.write_frf_only(self.folder / "line.uff", points=5))
        panel.set_data(viewer.LoadedModalData(fe_line(), line, directory=self.folder / "views",
                                              registration=viewer.AMBIGUOUS), "points on one line")
        self.root.update()
        for pane in (panel.fe, panel.experimental):  # the default component is the out-of-plane one
            self.assertIsNone(pane.photo)
            self.assertIsNone(pane.image_path)
            self.assertIn("no out-of-plane view — the points lie on one line", pane.image.cget("text"))
            self.assertGreater(int(str(pane.image.cget("wraplength"))), 0)  # the reason is wrapped, not cut off
        self.assertIn("NOT a validated fitted mode shape", panel.experimental.info.cget("text"))  # still PROVISIONAL
        for pane, label in ((panel.fe, "U3"), (panel.experimental, "Z (measurement axes)")):
            pane.component.set(label)
            pane.render()
            self.assertIsNotNone(pane.photo)  # the same points, another component
        panel.fe.component.set(viewer.COMPONENT_TEXT[viewer.FE]["normal"])
        panel.fe.render()
        self.assertIsNone(panel.fe.photo)  # the U3 picture does not stay under the refusal
        self.assertIsNone(panel.fe.image_path)

    def test_save_diagnostic_output(self):
        application = self.application()
        experimental = load_unv(self.frf_path)
        error = ambiguity()
        error.loaded_modal_data = self.loaded(experimental)
        application._failed(error)
        paths = application.mode_viewer.save(self.folder / "saved")
        names = sorted(p.name for p in paths.values())
        self.assertIn("modal_data_inventory.json", names)
        self.assertIn("frequency_only_diagnostic.json", names)
        self.assertTrue(any(name.startswith("fe_0001") for name in names))
        self.assertTrue(any(name.startswith("exp_0001") for name in names))


if __name__ == "__main__":
    unittest.main()
