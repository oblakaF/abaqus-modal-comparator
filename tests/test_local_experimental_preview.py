"""APP-DATA.3: read-only view of the experimental data of a UNV / UFF / LMS file (Input file registry).

The view uses the comparator's importer unchanged (resolve_testlab_file, discover_experimental_modal_sets, the installed
load_universal_modal_file per set) and the classification of services.modal_data_viewer. Several dataset-55 sets are
shown separately and none is chosen; dataset 2414 keeps the importer's record classification; FRF peak-derived records
are PROVISIONAL. Nothing in the main window changes, nothing is paired or run, the files are only read, and a window
closed while reading discards the outcome. Synthetic temporary files only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import main  # noqa: E402,F401  (the installed importer chain, as in the application)
import universal_reader  # noqa: E402
from modal_core import ModalDataset, ModeShape  # noqa: E402
from services import local_experimental_preview as preview_service  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from services import modal_data_viewer as viewer  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from test_app_p1_stale_results import _App  # noqa: E402
from test_polymax_modal_sets import _geometry, _mode, _mode_2414, _residual  # noqa: E402


def fingerprint(*paths: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="app_data3_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        patcher = mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a preview"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def records(self, preview_set):
        return [(r.number, r.frequency_hz) for r in preview_set.records]

    def loader_modes(self, path, **kwargs):
        return [(int(m.number), float(m.frequency_hz))
                for m in universal_reader.load_universal_modal_file(path, **kwargs).modes]

    def fake_file(self, name: str) -> Path:
        path = self.folder / name
        path.write_text(f"synthetic records of {name}", encoding="utf-8")
        return path


class ServiceTests(_Folder):
    def test_one_fitted_dataset_55_set(self):
        unv = S.write_experiment(self.folder / "one.unv", S.E0, S.G0)
        before = fingerprint(unv)
        preview = preview_service.preview_experimental_file(unv)
        self.assertEqual(preview.kind, preview_service.DATASET_55)
        self.assertEqual(len(preview.sets), 1)
        chosen = preview.sets[0]
        self.assertEqual(self.records(chosen), self.loader_modes(unv, modal_set=chosen.key))
        self.assertEqual(chosen.records[0].number, 1)  # experimental mode 1 is shown, never excluded
        self.assertEqual({r.classification for r in chosen.records}, {viewer.FITTED_MODE})
        self.assertFalse(any(r.provisional for r in chosen.records))
        self.assertEqual({r.point_count for r in chosen.records}, {63})
        self.assertEqual({r.measured_dof_count for r in chosen.records}, {63})  # U3 only
        self.assertEqual(preview.source_path, unv)
        self.assertIn(55, preview.dataset_types)
        self.assertEqual(preview.geometry_node_count, 63)
        self.assertEqual(fingerprint(unv), before)

    def test_several_dataset_55_sets_are_shown_separately_and_none_is_chosen(self):
        unv = S.write_experiment(self.folder / "two.unv", S.E0, S.G0, sets=(("PolyMAX bravo", 4), ("PolyMAX alpha", 6)))
        with self.assertRaisesRegex(ValueError, "select one explicitly"):  # the importer itself never picks one
            universal_reader.load_universal_modal_file(unv)
        preview = preview_service.preview_experimental_file(unv)
        self.assertEqual([s.display_name for s in preview.sets], ["PolyMAX bravo", "PolyMAX alpha"])
        self.assertEqual([len(s.records) for s in preview.sets], [4, 6])
        for chosen in preview.sets:
            self.assertEqual(self.records(chosen), self.loader_modes(unv, modal_set=chosen.key))
        self.assertIn("2 fitted modal sets (dataset 55), shown separately", preview_service.summary(preview))

    def test_residual_and_non_modal_records_are_the_importers_exclusions(self):
        non_modal = _residual("Processing", "below", 30.0)
        non_modal["id1"] = "Processing"
        datasets = [_geometry(), _mode("Processing", 1, 30.0), _mode("Processing", 2, 45.0),
                    _residual("Processing", "below", 5.0), _residual("Processing", "above", 500.0), non_modal]
        path = self.fake_file("residuals.unv")
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            preview = preview_service.preview_experimental_file(path)
            expected = universal_reader.load_universal_modal_file(path, modal_set="processing").metadata
        chosen = preview.sets[0]
        self.assertEqual(self.records(chosen), [(1, 30.0), (2, 45.0)])
        self.assertEqual(list(chosen.excluded_residual), expected["excluded_residual_labels"])
        self.assertEqual(len(chosen.excluded_residual), 2)
        self.assertEqual(list(chosen.excluded_non_modal), expected["excluded_non_modal_labels"])
        self.assertEqual(len(chosen.excluded_non_modal), 1)

    def assert_importer_classification(self, records, loaded, dataset_type):
        """Each row carries the importer's own record classification; nothing else changes."""
        self.assertEqual([(r.number, r.frequency_hz) for r in records],
                         [(int(m.number), float(m.frequency_hz)) for m in loaded.modes])
        for record, mode in zip(records, loaded.modes):
            self.assertEqual(record.record_classification, mode.metadata["record_classification"])
            self.assertEqual(record.record_classification_reason, mode.metadata["record_classification_reason"])
            index = mode.metadata[f"dataset_{dataset_type}_record_index"]
            self.assertEqual(record.record_reference, f"dataset {dataset_type} record {index}")
            self.assertEqual(record.classification, viewer.experimental_classification(mode, loaded.metadata)[0])

    def test_unambiguous_and_ambiguous_dataset_55_records(self):
        ambiguous = _mode("Processing", 2, 20.0)
        ambiguous.pop("analysis_type")  # the importer preserves it as ambiguous
        datasets = [_geometry(), _mode("Processing", 1, 10.0), ambiguous]
        path = self.fake_file("ambiguous55.unv")
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            preview = preview_service.preview_experimental_file(path)
            loaded = universal_reader.load_universal_modal_file(path, modal_set="processing")
        physical, unclear = preview.sets[0].records
        self.assert_importer_classification(preview.sets[0].records, loaded, 55)
        self.assertEqual((physical.record_classification, physical.ambiguous), ("physical", False))
        self.assertEqual(physical.label, f"{physical.source_text} — dataset 55 record 1 (physical, importer)")
        self.assertTrue(unclear.ambiguous)
        self.assertTrue(unclear.label.startswith(f"{preview_service.AMBIGUOUS} — dataset 55 record 2, not a "
                                                 "confirmed fitted mode: "))
        self.assertIn(unclear.record_classification_reason, unclear.label)
        self.assertNotIn("curve-fitted", unclear.label)  # never shown as a confirmed fitted mode
        warning = next(w for w in preview.sets[0].warnings if "preserved as ambiguous" in w)
        self.assertTrue(warning.lower().startswith(unclear.record_reference))  # the row names the warning's record
        self.assertIn(f"1 record {preview_service.AMBIGUOUS}", preview_service.summary(preview))

    def test_dataset_2414_without_dataset_55(self):
        datasets = [_geometry(), _mode_2414(1, 25.0, analysis_type=3),
                    _mode_2414(2, 25.0, analysis_type=5, name="Frequency response"),
                    _mode_2414(3, 35.0, analysis_type=None, name="Legacy modal result")]
        path = self.fake_file("records.unv")
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            preview = preview_service.preview_experimental_file(path)
            loaded = universal_reader.load_universal_modal_file(path)
        self.assertEqual(preview.kind, preview_service.DATASET_2414)
        self.assertEqual(self.records(preview.sets[0]), [(1, 25.0), (3, 35.0)])
        self.assert_importer_classification(preview.sets[0].records, loaded, 2414)
        physical, unclear = preview.sets[0].records
        self.assertEqual(physical.label, f"{physical.source_text} — dataset 2414 record 1 (physical, importer)")
        self.assertTrue(unclear.label.startswith(f"{preview_service.AMBIGUOUS} — dataset 2414 record 3, not a "
                                                 "confirmed fitted mode: "))
        warning = next(w for w in preview.sets[0].warnings if "preserved as ambiguous" in w)
        self.assertTrue(warning.lower().startswith(unclear.record_reference))
        self.assertEqual([(i, c, inc) for i, c, inc, _ in preview.record_classifications],
                         [(1, "physical", True), (2, "non_modal", False), (3, "ambiguous", True)])
        self.assertTrue(any("preserved as ambiguous" in w for w in preview.sets[0].warnings))
        self.assertEqual({r.classification for r in preview.sets[0].records}, {viewer.FITTED_MODE})
        self.assertIn("used dataset 2414", preview_service.KIND_TEXT[preview.kind])  # not "no fitted modes"

    def test_a_real_pyuff_dataset_2414_file(self):
        from test_universal_hardening import write_2414_unv

        path = write_2414_unv(self.folder / "real_2414.unv", [
            {"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
            {"analysis_type": 3, "mode": 8, "frequency": 41.25, "label": 2},
            {"analysis_type": 5, "mode": 9, "frequency": 25.0, "label": 3, "name": "Frequency response"}])
        before = fingerprint(path)
        preview = preview_service.preview_experimental_file(path)
        self.assertEqual(preview.kind, preview_service.DATASET_2414)
        record, = preview.sets[0].records
        self.assertEqual((record.number, record.frequency_hz, record.point_count, record.measured_dof_count),
                         (7, 23.5, 3, 9))
        self.assertEqual(record.label, f"{record.source_text} — dataset 2414 record 1 (physical, importer)")
        self.assertTrue(any("(analysis type 3): complex eigenvalue data define no frequency" in w
                            for w in preview.sets[0].warnings))
        self.assertEqual([(i, c, inc) for i, c, inc, _ in preview.record_classifications],
                         [(1, "physical", True), (2, "physical", True), (3, "non_modal", False)])
        self.assertEqual(fingerprint(path), before)

    def test_frf_only_dataset_58_records_are_provisional(self):
        uff = F.write_frf_only(self.folder / "frf_only.uff")
        before = fingerprint(uff)
        preview = preview_service.preview_experimental_file(uff)
        self.assertEqual(preview.kind, preview_service.FRF_58)
        records = preview.sets[0].records
        self.assertTrue(records)
        self.assertTrue(all(r.provisional and r.label == preview_service.PROVISIONAL for r in records))
        self.assertEqual({r.classification for r in records}, {viewer.FRF_PEAK_SNAPSHOT})
        self.assertEqual(self.records(preview.sets[0]), self.loader_modes(uff))
        self.assertIn("NOT validated fitted modes", preview_service.KIND_TEXT[preview.kind])
        self.assertTrue(any(d.startswith("FRF channels:") for d in preview.details))
        self.assertEqual(fingerprint(uff), before)

    def test_lms_with_and_without_its_companion(self):
        companion = S.write_experiment(self.folder / "project.unv", S.E0, S.G0)
        lms = self.folder / "project.lms"
        lms.write_bytes(b"synthetic Testlab project stand-in")
        preview = preview_service.preview_experimental_file(lms)
        self.assertEqual(preview.selected_path, lms)
        self.assertEqual(preview.source_path, companion)
        lone = self.folder / "lone" / "alone.lms"
        lone.parent.mkdir()
        lone.write_bytes(b"synthetic Testlab project stand-in")
        with self.assertRaisesRegex(preview_service.ExperimentalPreviewError, "no companion .unv/.uff"):
            preview_service.preview_experimental_file(lone)

    def test_damaged_or_missing_files_are_clear_errors(self):
        damaged = self.fake_file("damaged.unv")
        before = fingerprint(damaged)
        with self.assertRaisesRegex(preview_service.ExperimentalPreviewError, "cannot be read"):
            preview_service.preview_experimental_file(damaged)
        self.assertEqual(fingerprint(damaged), before)
        with self.assertRaisesRegex(preview_service.ExperimentalPreviewError, "does not exist"):
            preview_service.preview_experimental_file(self.folder / "absent.unv")

    def test_a_set_cancel_event_stops_between_reads(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(preview_service.PreviewCancelled):
            preview_service.preview_experimental_file(S.write_experiment(self.folder / "c.unv", S.E0, S.G0),
                                                      cancel_event=cancel)


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


class ShapeViewServiceTests(_Folder):
    """APP-DATA.4: one record of one set drawn on its own measured points by services.modal_data_viewer."""

    def drawn(self, preview_set, index, component):
        """The view, and the one-mode dataset handed to the main window's viewer (render_viewer_mode)."""
        with mock.patch.object(viewer, "render_viewer_mode", wraps=viewer.render_viewer_mode) as render:
            view = preview_service.render_record_shape(preview_set, index, component, self.folder / "views")
        (dataset, role, number, drawn_component, _directory), _ = render.call_args
        self.assertEqual((role, drawn_component), (viewer.EXPERIMENTAL, component))
        mode, = dataset.modes
        self.assertEqual(number, mode.number)
        self.assertTrue(view.image_path.is_file())
        self.assertEqual(view.image_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        return view, mode

    def assert_same_record(self, drawn, loaded, keep=None):
        keep = np.ones(len(loaded.node_ids), bool) if keep is None else np.asarray(keep)
        self.assertEqual((drawn.number, drawn.frequency_hz), (loaded.number, loaded.frequency_hz))
        np.testing.assert_array_equal(drawn.vectors, np.asarray(loaded.vectors)[keep])  # as imported, a subset only
        np.testing.assert_array_equal(drawn.coordinates, np.asarray(loaded.coordinates)[keep])
        self.assertEqual(list(drawn.node_ids), list(np.asarray(loaded.node_ids)[keep]))

    def images(self):
        return sorted(p.name for p in (self.folder / "views").rglob("*.png")) if (self.folder / "views").exists() \
            else []

    def test_the_selected_record_of_the_selected_set_is_drawn(self):
        unv = S.write_experiment(self.folder / "two.unv", S.E0, S.G0, sets=(("PolyMAX bravo", 4), ("PolyMAX alpha", 6)))
        before = fingerprint(unv)
        preview = preview_service.preview_experimental_file(unv)
        for set_index, record_index in ((1, 2), (0, 3), (1, 0)):
            chosen = preview.sets[set_index]
            view, drawn = self.drawn(chosen, record_index, "normal")
            loaded = universal_reader.load_universal_modal_file(unv, modal_set=chosen.key).modes[record_index]
            self.assert_same_record(drawn, loaded)
            self.assertEqual((view.set_title, view.index, view.record), (chosen.title, record_index,
                                                                        chosen.records[record_index]))
            self.assertIn(f"Record {record_index + 1} of {chosen.title}", view.lines[1])
            self.assertIn(chosen.display_name, view.lines[0])  # the set's own name, never another set's
        self.assertEqual(fingerprint(unv), before)

    def test_components_that_are_not_measured_are_refused_and_never_created(self):
        preview = preview_service.preview_experimental_file(S.write_experiment(self.folder / "z.unv", S.E0, S.G0))
        chosen = preview.sets[0]
        for component in ("x", "y"):
            with self.assertRaisesRegex(preview_service.ShapeViewUnavailable, "not a measured component"):
                preview_service.render_record_shape(chosen, 0, component, self.folder / "views")
        self.assertEqual(self.images(), [])
        for component in ("normal", "magnitude", "z"):
            view, drawn = self.drawn(chosen, 0, component)
            self.assertEqual(view.points_shown, 63)
            self.assertIn("Measured components (importer): Z. Not measured: X, Y — not drawn as measured", view.lines[3])
        with self.assertRaisesRegex(ValueError, "unknown component"):
            preview_service.render_record_shape(chosen, 0, "rx", self.folder / "views")

    def test_only_the_points_where_a_component_is_measured_are_drawn(self):
        coordinates = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [2.0, 0.0, 0.0],
                                [2.0, 1.0, 0.0]])
        vectors = np.array([[0.5, 0.0, 1.0], [0.25, 0.0, -1.0], [0.0, 0.0, 0.5], [-0.5, 0.0, 0.25], [0.75, 0.0, 0.0],
                            [0.0, 0.0, 0.0]], dtype=complex)
        mode = ModeShape(1, 12.0, np.arange(1, 7), coordinates, vectors, metadata={"dataset_type": 55})
        mode.measured_dofs = np.array([[1, 0, 1], [1, 0, 1], [0, 0, 1], [1, 0, 1], [1, 0, 0], [0, 0, 0]], dtype=bool)
        chosen = preview_service._set_from(ModalDataset("synthetic", self.folder / "s.unv", [mode]), "s", "Set S")
        x_view, x_drawn = self.drawn(chosen, 0, "x")
        self.assert_same_record(x_drawn, mode, mode.measured_dofs[:, 0])
        self.assertEqual(x_view.points_shown, 4)
        self.assertIn("on 4 of 6 points", x_view.lines[2])
        normal_view, normal_drawn = self.drawn(chosen, 0, "normal")
        self.assert_same_record(normal_drawn, mode, mode.measured_dofs.any(axis=1))  # point 6 measured nothing
        self.assertIn("Not measured: Y", normal_view.lines[3])
        with self.assertRaisesRegex(preview_service.ShapeViewUnavailable, "Y \\(measurement axes\\) is not a measured"):
            preview_service.render_record_shape(chosen, 0, "y", self.folder / "views")

    def test_imported_dataset_2414_normal_modes(self):
        from test_universal_hardening import write_2414_unv

        path = write_2414_unv(self.folder / "real_2414.unv", [
            {"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
            {"analysis_type": 2, "mode": 9, "frequency": 47.25, "label": 2},
            {"analysis_type": 2, "mode": 11, "frequency": 60.0, "label": 3, "values": [
                np.array([0.0, 0.0, 0.0, 0.0, 0.5 * k, -0.0625 * k]) for k in (1, 2, 3)]}])
        preview = preview_service.preview_experimental_file(path)
        chosen = preview.sets[0]
        loaded = universal_reader.load_universal_modal_file(path).modes
        view, drawn = self.drawn(chosen, 1, "magnitude")
        self.assert_same_record(drawn, loaded[1])
        self.assertIn("dataset 2414 record 2 (physical, importer)", view.lines[0])
        self.assertIn("Measured components (importer): X, Y, Z.", view.lines[3])
        with self.assertRaisesRegex(preview_service.ShapeViewUnavailable, "X \\(measurement axes\\) is not a measured"):
            preview_service.render_record_shape(chosen, 2, "x", self.folder / "views")  # Z only, written as zeros
        self.assert_same_record(self.drawn(chosen, 2, "z")[1], loaded[2])

    def test_frf_records_are_drawn_provisional(self):
        preview = preview_service.preview_experimental_file(F.write_frf_only(self.folder / "frf.uff"))
        chosen = preview.sets[0]
        view, drawn = self.drawn(chosen, 1, "normal")
        self.assert_same_record(drawn, universal_reader.load_universal_modal_file(self.folder / "frf.uff").modes[1])
        self.assertEqual(view.lines[0], preview_service.PROVISIONAL)
        self.assertTrue(view.record.provisional)

    def test_ambiguous_records_keep_their_warning(self):
        datasets = [geometry_4(), mode_55_4(1, 10.0), mode_55_4(2, 20.0, ambiguous=True)]
        path = self.fake_file("ambiguous.unv")
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            preview = preview_service.preview_experimental_file(path)
        view, _ = self.drawn(preview.sets[0], 1, "normal")
        self.assertTrue(view.lines[0].startswith(f"{preview_service.AMBIGUOUS} — dataset 55 record 2, not a "
                                                 "confirmed fitted mode"))
        self.assertTrue(view.record.ambiguous)
        clear, _ = self.drawn(preview.sets[0], 0, "normal")
        self.assertIn("dataset 55 record 1 (physical, importer)", clear.lines[0])

    def test_points_on_one_line_have_no_out_of_plane_view(self):
        line = np.column_stack([np.linspace(0.0, 0.3, 6), np.zeros(6), np.zeros(6)])
        vectors = np.column_stack([np.zeros(6), np.zeros(6), np.sin(np.linspace(0.0, np.pi, 6)) + 0.1]).astype(complex)
        mode = ModeShape(1, 31.5, np.arange(1, 7), line, vectors, metadata={"dataset_type": 55})
        mode.measured_dofs = np.column_stack([np.zeros(6, bool), np.zeros(6, bool), np.ones(6, bool)])
        chosen = preview_service._set_from(ModalDataset("synthetic", self.folder / "l.unv", [mode]), "l", "Line")
        with self.assertRaisesRegex(preview_service.ShapeViewUnavailable, "lie on one line: no best-fit plane"):
            preview_service.render_record_shape(chosen, 0, "normal", self.folder / "views")
        self.assertEqual(self.images(), [])
        for component in ("z", "magnitude"):  # the measured values along the line are still drawn
            self.assert_same_record(self.drawn(chosen, 0, component)[1], mode)

    def test_no_spatial_view_is_stated_and_nothing_is_drawn(self):
        two_points = preview_service.preview_experimental_file(F.write_frf_only(self.folder / "two.uff", points=2))
        with self.assertRaisesRegex(preview_service.ShapeViewUnavailable, "needs at least 3 measured points"):
            preview_service.render_record_shape(two_points.sets[0], 0, "normal", self.folder / "views")
        chosen = preview_service.preview_experimental_file(S.write_experiment(self.folder / "c.unv", S.E0, S.G0)).sets[0]
        with self.assertRaisesRegex(preview_service.ShapeViewUnavailable, "not in the loaded data"):
            preview_service.render_record_shape(chosen, len(chosen.records), "normal", self.folder / "views")
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(preview_service.PreviewCancelled):
            preview_service.render_record_shape(chosen, 0, "normal", self.folder / "views", cancel_event=cancel)
        self.assertEqual(self.images(), [])


class PreviewWindowTests(_App):
    """The real main window: Inspect experimental data in the registry dialog (synthetic data, no process)."""

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
        window = dialog.inspect_experimental_selected()
        if window is not None:
            self.addCleanup(window.close)
        return window

    def wait(self, window, timeout=60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and window.preview is None and window.error is None:
            self.root.update()
            time.sleep(0.02)

    def main_state(self, application):
        return (application.abaqus_path.get(), application.experimental_path.get(),
                application.experimental_modal_set_key.get(), application.result is None, application.running)

    def test_several_sets_are_viewed_one_at_a_time_and_the_main_window_is_untouched(self):
        application = self.application()
        dialog = self.dialog(application)
        unv = S.write_experiment(self.folder / "two_sets.unv", S.E0, S.G0, sets=(("PolyMAX bravo", 4),
                                                                                  ("PolyMAX alpha", 6)))
        before_file, before_main = fingerprint(unv), self.main_state(application)
        with mock.patch.object(application, "_start", side_effect=AssertionError("nothing is run")):
            window = self.inspect(dialog, registry.EXPERIMENTAL, unv, "Two sets")
            before_store = self.store.read_bytes()
            self.wait(window)
            self.assertIsNone(window.error)
            self.assertEqual(window.window.title(), "Experimental data — Two sets")
            self.assertEqual(list(window.set_box.cget("values")),
                             [s.title for s in window.preview.sets])
            self.assertEqual(len(window.tree.get_children()), 4)  # the first set only
            window.set_box.current(1)
            window.set_box.event_generate("<<ComboboxSelected>>")
            self.root.update()
            self.assertEqual(len(window.tree.get_children()), 6)  # the second set only, never merged
            self.assertIn("PolyMAX alpha", window.set_note.get())
        self.assertEqual(self.main_state(application), before_main)  # fields, modal set, no result, not running
        self.assertEqual(fingerprint(unv), before_file)
        self.assertEqual(self.store.read_bytes(), before_store)

    def test_frf_only_records_are_shown_provisional(self):
        application = self.application()
        dialog = self.dialog(application)
        window = self.inspect(dialog, registry.EXPERIMENTAL, F.write_frf_only(self.folder / "frf.uff"))
        self.wait(window)
        rows = [window.tree.item(i)["values"] for i in window.tree.get_children()]
        self.assertTrue(rows)
        self.assertEqual({row[2] for row in rows}, {preview_service.PROVISIONAL})
        self.assertIn("FRF data (dataset 58)", window.details.get("1.0", "end"))

    def test_ambiguous_records_are_shown_as_ambiguous_in_the_table(self):
        application = self.application()
        dialog = self.dialog(application)
        ambiguous55 = _mode("Processing", 2, 20.0)
        ambiguous55.pop("analysis_type")
        cases = {
            "dataset 55": ([_geometry(), _mode("Processing", 1, 10.0), ambiguous55], 55, (1, 2)),
            "dataset 2414": ([_geometry(), _mode_2414(1, 25.0, analysis_type=3),
                              _mode_2414(2, 25.0, analysis_type=5, name="Frequency response"),
                              _mode_2414(3, 35.0, analysis_type=None, name="Legacy modal result")], 2414, (1, 3)),
        }
        for name, (datasets, dataset_type, (clear_index, unclear_index)) in cases.items():
            with self.subTest(case=name):
                path = self.folder / f"ambiguous_{dataset_type}.unv"
                path.write_text(f"synthetic records {dataset_type}", encoding="utf-8")
                with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
                    window = self.inspect(dialog, registry.EXPERIMENTAL, path, name)
                    self.wait(window)
                self.assertIsNone(window.error)
                labels = [str(window.tree.item(i)["values"][2]) for i in window.tree.get_children()]
                self.assertEqual(len(labels), 2)
                self.assertIn(f"dataset {dataset_type} record {clear_index} (physical, importer)", labels[0])
                self.assertFalse(labels[0].startswith(preview_service.AMBIGUOUS))
                self.assertTrue(labels[1].startswith(f"{preview_service.AMBIGUOUS} — dataset {dataset_type} record "
                                                     f"{unclear_index}, not a confirmed fitted mode"))
                details = window.details.get("1.0", "end")
                self.assertIn(f"Dataset {dataset_type} record {unclear_index} was preserved as ambiguous", details)
                self.assertIn(f"1 record {preview_service.AMBIGUOUS}", window.status.get())

    def test_entries_that_cannot_be_inspected(self):
        application = self.application()
        dialog = self.dialog(application)
        self.assertIsNone(self.inspect(dialog, registry.FE, self.other_odb))
        self.assertIn("works on an experimental entry", dialog.message.get())
        unv = S.write_experiment(self.folder / "gone.unv", S.E0, S.G0)
        entry, _ = registry.add_entry(self.store, registry.EXPERIMENTAL, unv, "Gone")
        unv.unlink()
        dialog.refresh(select=entry["id"])
        with mock.patch("tkinter.messagebox.showwarning") as warned:
            self.assertIsNone(dialog.inspect_experimental_selected())
        self.assertIn("'Gone' cannot be used", warned.call_args.args[1])

    def test_a_damaged_file_is_stated_in_the_window(self):
        application = self.application()
        dialog = self.dialog(application)
        damaged = self.folder / "damaged.unv"
        damaged.write_text("not a universal file", encoding="utf-8")
        window = self.inspect(dialog, registry.EXPERIMENTAL, damaged)
        self.wait(window)
        self.assertIn("cannot be read", window.error)
        self.assertEqual(window.status.get(), "No experimental data can be shown.")
        self.assertEqual(window.tree.get_children(), ())

    def test_closing_the_window_while_reading_discards_the_outcome(self):
        application = self.application()
        dialog = self.dialog(application)
        unv = S.write_experiment(self.folder / "slow.unv", S.E0, S.G0)
        gate, entered = threading.Event(), threading.Event()
        real_discover = universal_reader.discover_experimental_modal_sets

        def slow_discover(path):
            entered.set()
            gate.wait(30)
            return real_discover(path)  # the importer itself cannot be interrupted inside a read

        errors = []
        self.root.report_callback_exception = lambda *exc: errors.append(exc[1])
        with mock.patch.object(universal_reader, "discover_experimental_modal_sets", side_effect=slow_discover):
            window = self.inspect(dialog, registry.EXPERIMENTAL, unv)
            self.assertTrue(entered.wait(10))
            for _ in range(5):  # the main window keeps processing events while the file is read
                self.root.update()
            self.assertIn("Reading", window.status.get())
            window.close()
            self.assertFalse(window.window.winfo_exists())
            gate.set()
            window.thread.join(30)
        self.assertFalse(window.thread.is_alive())
        self.assertEqual(window.results.get_nowait(), ("cancelled", None))  # stopped at the next step, discarded
        for _ in range(15):
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(window.preview)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
