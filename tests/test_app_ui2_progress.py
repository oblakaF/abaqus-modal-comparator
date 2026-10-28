"""APP-UI.2-O1: the window stopped repainting at "6/6 Report data generation" (real main window, synthetic data).

Measured on the SHA-verified SP-02 copies (extracted manifest + UNV, Bravo (1); docs/gui/APP_UI2_PROGRESS.md):

- the worker's stage 6 takes milliseconds;
- the completion then ran on the GUI thread for 28.8 s, and the root.after heartbeat stopped for 28.9 s;
- 24.2 s of it was the rigid-body classification of the FE modes. ``project_review.refresh_review_table`` called
  ``_all_elastic_abaqus_modes`` -> ``quality_control._detect_rigid_modes`` (an ``lstsq`` per mode on the full FE
  mesh), twice per completion.

The comparison's quality control has already classified every FE mode on the worker and recorded it in
``result.abaqus.metadata["quality_control"]``. ``_all_elastic_abaqus_modes`` now reuses that record when it is complete
and agrees with the current criterion and with this exact FE set; otherwise it classifies again exactly as before.
"""

from __future__ import annotations

import copy
import functools
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from modal_core import ModalDataset, ModeShape  # noqa: E402
from test_app_p1_stale_results import DISCARDED, STALE, _App  # noqa: E402

import project_review  # noqa: E402
import quality_control  # noqa: E402


def _rigid_shapes(coordinates):
    """The six rigid-body shapes (3 translations, 3 small rotations about the centroid) on *coordinates*."""
    centered = coordinates - coordinates.mean(axis=0)
    x, y, z = centered[:, 0], centered[:, 1], centered[:, 2]
    shapes = [np.tile(axis, (len(coordinates), 1)) for axis in np.eye(3)]
    shapes.append(np.stack([np.zeros_like(x), -z, y], axis=1))
    shapes.append(np.stack([z, np.zeros_like(x), -x], axis=1))
    shapes.append(np.stack([-y, x, np.zeros_like(x)], axis=1))
    return shapes


def _elastic_part(vectors, coordinates):
    """*vectors* without its rigid-body part, scaled to unit norm."""
    basis = np.stack([shape.reshape(-1) for shape in _rigid_shapes(coordinates)], axis=1)
    flat = vectors.reshape(-1).astype(float)
    coefficients, _, _, _ = np.linalg.lstsq(basis, flat, rcond=None)
    rest = flat - basis @ coefficients
    return (rest / np.linalg.norm(rest)).reshape(vectors.shape)


class _World:
    """The synthetic SP-02 world of the P-1 tests: an FE set, its experiment and the accepted registration."""

    def __init__(self, folder: Path):
        from test_g2c_archived_sensitivity_evidence import World
        from test_g2d1_governed_registration import experimental_dataset, fe_dataset
        from test_new_odb_comparison import new_odb_dataset
        from services import new_odb_comparison as new

        self.world = World(str(folder))
        odb, unv = self.world.files["SP02"]
        baseline = fe_dataset(odb)
        self.experimental = experimental_dataset(unv, baseline)
        target = folder / "data" / "SP02_new_model.odb"
        target.write_bytes(b"another FE result with the accepted mesh " * 4000)
        self.fe = new_odb_dataset(target, baseline)
        with self.world.pins():
            self.registration = functools.partial(new.bind_registration_by_fe_geometry, repo_root=self.world.root)(
                unv, self.fe, self.experimental).registration

    def compare(self, fe):
        import main

        return main.app.compare_modal_datasets(fe, self.experimental, frozen_registration=self.registration)

    def with_rigid_and_close_modes(self):
        """The FE set plus six rigid-body modes, a nearly rigid mode on each side of the threshold and a degenerate
        pair (the same frequency twice), all on the same mesh, listed out of frequency order."""
        elastic = self.fe.sorted_modes()
        first = elastic[0]
        coordinates, node_ids = first.coordinates, first.node_ids
        bending = _elastic_part(first.vectors, coordinates)
        modes = list(reversed(elastic))
        for k, shape in enumerate(_rigid_shapes(coordinates)):
            modes.append(ModeShape(1 + k, 1.0e-3 * (k + 1), node_ids, coordinates, shape / np.linalg.norm(shape)))
        rigid = _rigid_shapes(coordinates)[2]
        rigid = rigid / np.linalg.norm(rigid)
        modes.append(ModeShape(20, 0.5, node_ids, coordinates, rigid + 0.01 * bending))  # residual ~0.01: rigid
        modes.append(ModeShape(21, 2.0, node_ids, coordinates, rigid + 0.05 * bending))  # residual ~0.05: elastic
        twin = elastic[2]
        modes.append(ModeShape(22, twin.frequency_hz, node_ids, coordinates, _elastic_part(twin.vectors[::-1].copy(),
                                                                                       coordinates)))
        return ModalDataset("FE", self.fe.source_path, modes)


class QualityControlRecordTests(unittest.TestCase):
    """_all_elastic_abaqus_modes gives exactly the modes of the previous classification, without re-projecting."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._folder = tempfile.mkdtemp(prefix="ui2_o1_")
        cls.world = _World(Path(cls._folder))
        cls.raw = cls.world.with_rigid_and_close_modes()
        cls._result = cls.world.compare(cls.raw)
        cls._plain = cls.world.compare(cls.world.fe)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._folder, ignore_errors=True)

    def result(self):
        return copy.deepcopy(self._result)

    @staticmethod
    def previous(result):
        """The previous implementation of _all_elastic_abaqus_modes, unchanged."""
        _, retained, _, _ = quality_control._detect_rigid_modes(result.abaqus)
        return retained

    def classified_without_projection(self, result):
        with mock.patch.object(quality_control, "_rigid_body_residual_fraction",
                               side_effect=AssertionError("re-projected")):
            return project_review._all_elastic_abaqus_modes(result)

    def classified_again(self, result):
        """The fallback: the previous classification runs (and is counted)."""
        with mock.patch.object(project_review, "_detect_rigid_modes",
                               side_effect=quality_control._detect_rigid_modes) as detect:
            modes = project_review._all_elastic_abaqus_modes(result)
        self.assertEqual(detect.call_count, 1)
        self.assertEqual(modes, self.previous(result))
        return modes

    def test_the_synthetic_set_exercises_rigid_nearly_rigid_close_and_first_elastic_modes(self):
        residuals = quality_control._rigid_residuals(self.raw)
        self.assertTrue(all(residuals[number] < 1.0e-9 for number in range(1, 7)))
        self.assertLess(residuals[20], quality_control.RIGID_SHAPE_RESIDUAL_THRESHOLD)
        self.assertGreater(residuals[21], quality_control.RIGID_SHAPE_RESIDUAL_THRESHOLD)
        record = self._result.abaqus.metadata["quality_control"]
        self.assertEqual(sorted(record["excluded_abaqus_modes"]), [1, 2, 3, 4, 5, 6, 20])
        twins = [mode for mode in self.raw.modes if mode.frequency_hz == self.raw.modes[-1].frequency_hz]
        self.assertEqual(len(twins), 2)

    def test_the_recorded_classification_equals_the_previous_one_without_projection(self):
        for source in (self._result, self._plain):
            result = copy.deepcopy(source)
            expected = self.previous(result)
            modes = self.classified_without_projection(result)
            self.assertEqual([id(mode) for mode in modes], [id(mode) for mode in expected])  # the same objects, order
            self.assertEqual([mode.frequency_hz for mode in modes], sorted(mode.frequency_hz for mode in modes))

    def test_the_rigid_modes_stay_excluded_and_the_first_elastic_mode_stays_available(self):
        modes = self.classified_without_projection(self.result())
        numbers = [mode.number for mode in modes]
        self.assertFalse({1, 2, 3, 4, 5, 6, 20} & set(numbers))
        self.assertEqual(numbers[0], 21)  # the lowest elastic mode (residual just above the threshold) is first
        _, retained, _, first_elastic = quality_control._detect_rigid_modes(self.raw)
        self.assertEqual(numbers, [mode.number for mode in retained])  # the classification of the unfiltered set
        self.assertEqual(modes[0].frequency_hz, first_elastic)
        twin_frequency = self.raw.modes[-1].frequency_hz
        by_number = {mode.number: mode for mode in self.raw.modes}
        self.assertEqual([n for n in numbers if by_number[n].frequency_hz == twin_frequency],
                         [9, 22])  # both degenerate modes are kept, in their input order

    def assert_falls_back(self, change):
        result = self.result()
        change(result)
        self.assertIsNone(project_review._quality_controlled_elastic_modes(result))
        self.classified_again(result)

    def quality(self, result):
        return result.abaqus.metadata["quality_control"]

    def test_a_result_without_metadata_or_record_is_classified_as_before(self):
        self.assert_falls_back(lambda result: setattr(result.abaqus, "metadata", {}))
        self.assert_falls_back(lambda result: result.abaqus.metadata.pop("quality_control"))
        self.assert_falls_back(lambda result: result.abaqus.metadata.update(quality_control="damaged"))

    def test_another_method_or_threshold_is_not_reused(self):
        self.assert_falls_back(lambda result: self.quality(result).update(rigid_mode_method="frequency below 1 Hz"))
        self.assert_falls_back(lambda result: self.quality(result).pop("rigid_mode_method"))
        self.assert_falls_back(lambda result: self.quality(result).update(rigid_shape_residual_threshold=0.05))
        self.assert_falls_back(lambda result: self.quality(result).update(rigid_shape_residual_threshold="0.02"))
        self.assert_falls_back(lambda result: self.quality(result).pop("rigid_shape_residual_threshold"))

    def test_an_incomplete_or_damaged_record_is_not_reused(self):
        residuals = "rigid_body_residual_fraction_by_mode"
        self.assert_falls_back(lambda result: self.quality(result).pop(residuals))
        self.assert_falls_back(lambda result: self.quality(result).pop("excluded_abaqus_modes"))
        self.assert_falls_back(lambda result: self.quality(result)[residuals].pop(21))  # a retained mode is missing
        self.assert_falls_back(lambda result: self.quality(result)[residuals].pop(3))  # an excluded mode is missing
        self.assert_falls_back(lambda result: self.quality(result).update(  # keys as a JSON round trip leaves them
            **{residuals: {str(k): v for k, v in self.quality(result)[residuals].items()}}))
        self.assert_falls_back(lambda result: self.quality(result)[residuals].update({21: "0.05"}))
        self.assert_falls_back(lambda result: self.quality(result)[residuals].update({21: True}))
        self.assert_falls_back(lambda result: self.quality(result)["excluded_abaqus_modes"].append(20))  # duplicate

    def test_a_record_that_contradicts_the_current_set_is_not_reused(self):
        residuals = "rigid_body_residual_fraction_by_mode"
        self.assert_falls_back(lambda result: self.quality(result)[residuals].update({21: 0.001}))  # says rigid
        self.assert_falls_back(lambda result: self.quality(result)[residuals].update({20: 0.5}))  # excluded elastic
        self.assert_falls_back(lambda result: self.quality(result)["excluded_abaqus_modes"].append(21))
        self.assert_falls_back(lambda result: self.quality(result).update(first_elastic_frequency_hz=1.0))

    def test_a_changed_fe_set_is_not_reused(self):
        def add_mode(result):
            mode = result.abaqus.modes[0]
            result.abaqus.modes.append(ModeShape(99, 500.0, mode.node_ids, mode.coordinates, mode.vectors))

        def change_frequency(result):
            lowest = min(result.abaqus.modes, key=lambda mode: mode.frequency_hz)
            lowest.frequency_hz *= 1.01

        self.assert_falls_back(add_mode)
        self.assert_falls_back(lambda result: result.abaqus.modes.pop())  # a mode removed
        self.assert_falls_back(lambda result: result.abaqus.modes.append(  # an excluded rigid mode back in the set
            next(mode for mode in self.raw.modes if mode.number == 3)))
        self.assert_falls_back(lambda result: result.abaqus.modes.append(result.abaqus.modes[0]))  # duplicated
        self.assert_falls_back(change_frequency)

    def test_the_record_of_another_analysis_is_never_used(self):
        def graft(result):  # this result's FE set carrying the record of another analysis
            other = copy.deepcopy(self._plain)
            result.abaqus.metadata["quality_control"] = other.abaqus.metadata["quality_control"]

        def other_comparison(result):  # this FE set and record attached to another comparison's mode list
            result.abaqus_mode_numbers = list(self._plain.abaqus_mode_numbers)

        self.assert_falls_back(graft)
        self.assert_falls_back(other_comparison)
        plain = copy.deepcopy(self._plain)  # each result answers with its own modes
        result = self.result()
        self.assertEqual([m.number for m in self.classified_without_projection(plain)],
                         [m.number for m in self.previous(plain)])
        self.assertNotEqual([m.number for m in self.classified_without_projection(plain)],
                            [m.number for m in self.classified_without_projection(result)])


class CompletionThreadTests(_App):
    """The completion on the GUI thread reads the recorded classification; it never projects the FE modes."""

    def counted(self, run):
        """Run *run* while every FE rigid-body classification and projection is recorded with its thread name."""
        projections, classifications = [], []
        project = quality_control._rigid_body_residual_fraction
        classify = project_review._detect_rigid_modes

        def projection(mode):
            projections.append(threading.current_thread().name)
            return project(mode)

        def classification(dataset):
            classifications.append(threading.current_thread().name)
            return classify(dataset)

        with mock.patch.object(quality_control, "_rigid_body_residual_fraction", side_effect=projection), \
                mock.patch.object(project_review, "_detect_rigid_modes", side_effect=classification):
            value = run()
        return value, projections, classifications

    def review_rows(self, application):
        return [tuple(application.review_table.item(item, "values")) for item in application.review_table.get_children()]

    def test_the_completion_does_no_rigid_mode_classification_on_the_gui_thread(self):
        self.comparison_result()  # the analysis itself (worker side) is done before the completion is measured
        application = self.application()
        _, projections, classifications = self.counted(lambda: self.established(application))
        self.assertEqual((projections, classifications), ([], []))
        self.assert_active_comparison(application)
        rows = self.review_rows(application)
        expected = [mode.number for mode in quality_control._detect_rigid_modes(application.result.abaqus)[1]]
        self.assertEqual([int(row[0]) for row in rows], expected)

    def test_a_result_without_its_record_is_classified_as_before_with_the_same_table(self):
        application = self.application()
        self.established(application)
        rows = self.review_rows(application)
        result = self.comparison_result()
        result.abaqus.metadata.pop("quality_control")
        self.start(application)
        _, _, classifications = self.counted(lambda: application._complete(result))
        self.assertEqual(classifications, ["MainThread", "MainThread"])  # the previous path, unchanged
        self.assert_active_comparison(application)
        self.assertEqual(self.review_rows(application), rows)

    def test_a_new_analysis_shows_the_modes_of_its_own_result(self):
        application = self.application()
        self.established(application)
        first = application.result
        result = self.comparison_result()
        dropped = max(result.abaqus.modes, key=lambda mode: mode.frequency_hz)
        result.abaqus.modes.remove(dropped)  # another FE set: its stale record cannot be reused
        self.start(application)
        _, _, classifications = self.counted(lambda: application._complete(result))
        self.assertIsNot(application.result, first)
        self.assertEqual(classifications, ["MainThread", "MainThread"])
        self.assertNotIn(str(dropped.number), [row[0] for row in self.review_rows(application)])
        self.start(application)  # and a further analysis with a valid record reads it again
        _, projections, classifications = self.counted(lambda: application._complete(self.comparison_result()))
        self.assertEqual((projections, classifications), ([], []))
        self.assert_active_comparison(application)

    def test_stop_error_and_changed_inputs_end_the_run_without_classification(self):
        result = self.comparison_result()
        application = self.application()
        self.start(application)
        application._analysis_cancel_event.set()  # Stop
        _, projections, classifications = self.counted(lambda: application._complete(copy.deepcopy(result)))
        self.assertIsNone(application.result)
        self.assertFalse(application.running)
        self.assertEqual((projections, classifications), ([], []))

        self.start(application)
        with mock.patch("tkinter.messagebox.showerror"):
            _, projections, classifications = self.counted(
                lambda: application._failed(RuntimeError("synthetic analysis error")))
        self.assertIsNone(application.result)
        self.assertFalse(application.running)
        self.assertEqual((projections, classifications), ([], []))

        self.start(application)
        application.end_mode.set(application.end_mode.get() + 3)  # inputs changed while running (P-1)
        _, projections, classifications = self.counted(lambda: application._complete(copy.deepcopy(result)))
        self.assert_inactive(application, DISCARDED)
        self.assertEqual((projections, classifications), ([], []))

    def test_a_result_made_stale_after_completion_is_cleared(self):
        application = self.application()
        self.established(application)
        application.end_mode.set(8)
        self.assert_inactive(application, STALE)

    def test_a_completion_posted_after_the_window_closed_does_nothing(self):
        result = self.comparison_result()
        application = self.application()
        self.start(application)
        application._ui_closing = True  # the close path sets this before the window is destroyed
        _, projections, classifications = self.counted(
            lambda: application._post_to_ui(lambda: application._complete(result)))
        self.root.update()
        self.assertEqual((projections, classifications), ([], []))
        self.assertIsNone(application.result)


if __name__ == "__main__":
    unittest.main()
