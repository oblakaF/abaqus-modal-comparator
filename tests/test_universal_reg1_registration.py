"""UNIVERSAL-REG-1: a diagnostic geometry mapping from stated physical evidence, for any geometry, with no archived record."""

from __future__ import annotations

import ast
from pathlib import Path
import threading
import unittest
from unittest import mock

import numpy as np

import test_universal_two_file_analysis as base
from test_universal_ui2_clean import FORBIDDEN

from PySide6.QtWidgets import QPushButton

from modal_core import ModalDataset, ModeShape
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import production_window as pw
from new_gui.analyze_panel import DONE, PROPOSED_TEXT, REFUSED_TEXT, SET_UP_REGISTRATION
from new_gui.registration_dialog import parse_landmarks
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import generic_registration as gr

ROOT = Path(__file__).resolve().parents[1]
RIGHT = ("+X", "+Y", "+Z")


def fe_dataset(points, labels=None, frequency=10.0, seed=1) -> ModalDataset:
    points = np.asarray(points, dtype=float)
    labels = labels or [f"PART-1:{k + 1}" for k in range(len(points))]
    vectors = np.random.default_rng(seed).standard_normal((len(points), 3))
    return ModalDataset("FE", Path("fe"), [ModeShape(n, frequency * n, labels, points, vectors) for n in (1, 2)])


def experimental_dataset(points, components="z", frequency=11.0, seed=2, metadata=None) -> ModalDataset:
    points = np.asarray(points, dtype=float)
    labels = [str(100 + k) for k in range(len(points))]
    modes = []
    for number in (1, 2):
        vectors = np.zeros((len(points), 3), dtype=complex)
        random = np.random.default_rng(seed + number)
        for component in components:
            vectors[:, "xyz".index(component)] = random.standard_normal(len(points)) + 0.1
        modes.append(ModeShape(number, frequency * number, labels, points, vectors))
    return ModalDataset("EXP", Path("exp"), modes, metadata=metadata or {})


def plate(nx=9, ny=7, lx=400.0, ly=300.0) -> np.ndarray:
    return np.array([[x, y, 0.0] for y in np.linspace(0, ly, ny) for x in np.linspace(0, lx, nx)])


def beam(n=21, length=1000.0) -> np.ndarray:
    return np.column_stack((np.linspace(0, length, n), np.zeros(n), np.zeros(n)))


def l_bracket() -> np.ndarray:
    """A plate with one corner cut away: no symmetry."""
    return np.array([p for p in plate(13, 9, 480.0, 320.0) if not (p[0] > 240.0 and p[1] > 160.0)])


def block() -> np.ndarray:
    """A solid with a different extent per axis, whose top and bottom faces carry nodes."""
    return np.array([[x, y, z] for z in (0.0, 20.0, 40.0) for y in np.linspace(0, 200, 11) for x in np.linspace(0, 300, 16)])


def evidence(**changes) -> gr.Evidence:
    values = dict(fe_unit="mm", experimental_unit="m", axes=RIGHT, measured_side="+Z", measured_dofs=("z",),
                  landmarks=(("100", "PART-1:1"),), source="marker photograph")
    values.update(changes)
    return gr.Evidence(**values)


def in_metres(points) -> np.ndarray:
    return np.asarray(points) / 1000.0


def row_of(points, target) -> int:
    return int(np.argmin(np.linalg.norm(np.asarray(points) - np.asarray(target), axis=1)))


class WorkingCaseTests(unittest.TestCase):
    def test_a_plate_with_axes_and_a_landmark(self):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence())
        self.assertEqual(proposal.status, gr.REGISTRATION_PROPOSED, proposal.problems)
        self.assertEqual(len(proposal.mapping), len(points))
        self.assertEqual([m.fe_node for m in proposal.mapping], [f"PART-1:{k + 1}" for k in range(len(points))])
        self.assertLess(max(m.distance for m in proposal.mapping), 1.0e-6)
        self.assertEqual(proposal.axes_in_fe, RIGHT)
        self.assertEqual(proposal.scale, 1000.0)

    def test_a_partial_scan_shifted_in_its_own_frame(self):
        points = plate()
        window = points[(points[:, 0] <= 200.0) & (points[:, 1] <= 150.0)]
        origin = np.array([7.0, -3.0, 2.0])  # metres of the measuring system
        first = row_of(points, window[0])
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(window) + origin),
                              evidence(landmarks=(("100", f"PART-1:{first + 1}"),)))
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertLess(max(m.distance for m in proposal.mapping), 1.0e-6)

    def test_a_scan_rotated_about_the_normal_with_coplanar_landmarks_and_one_axis(self):
        points = plate()
        turn = np.array([[0.8, -0.6, 0.0], [0.6, 0.8, 0.0], [0.0, 0.0, 1.0]])  # experimental -> FE
        scan = (points - points.mean(axis=0)) @ turn  # (turn.T @ p): the same points in the turned frame
        picks = [0, 8, 62]
        landmarks = tuple((str(100 + k), f"PART-1:{k + 1}") for k in picks)
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(scan)),
                              evidence(axes=("", "", "+Z"), landmarks=landmarks))
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertEqual([m.fe_node for m in proposal.mapping], [f"PART-1:{k + 1}" for k in range(len(points))])
        self.assertLess(max(m.distance for m in proposal.mapping), 1.0e-6)

    def test_a_beam_with_axes_and_two_landmarks(self):
        points = beam()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)),
                              evidence(landmarks=(("100", "PART-1:1"), ("120", "PART-1:21"))))
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertEqual(proposal.mapping[-1].fe_node, "PART-1:21")

    def test_a_beam_scanned_in_the_opposite_direction(self):
        """The axes and the landmarks state it, so it is the physical mapping."""
        points = beam()
        reversed_points = np.column_stack((1000.0 - points[:, 0], np.zeros(21), np.zeros(21)))
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(reversed_points)),
                              evidence(axes=("-X", "+Y", "-Z"), landmarks=(("100", "PART-1:1"), ("120", "PART-1:21"))))
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertEqual(proposal.mapping[0].fe_node, "PART-1:1")
        self.assertEqual(proposal.mapping[20].fe_node, "PART-1:21")

    def test_an_asymmetric_part(self):
        points = l_bracket()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence())
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertEqual(proposal.metrics["other_orientations"], 0)

    def test_non_coplanar_landmarks_alone_on_a_stepped_surface_in_a_turned_frame(self):
        points = np.array([[x, y, 200.0 if x > 150.0 else (100.0 if y > 100.0 else 0.0)]
                           for y in np.linspace(0, 200, 11) for x in np.linspace(0, 300, 16)])
        turn = np.array([[0.0, -1.0, 0.0], [0.6, 0.0, -0.8], [0.8, 0.0, 0.6]])
        self.assertAlmostEqual(float(np.linalg.det(turn)), 1.0)
        scan = (points - points.mean(axis=0)) @ turn  # the same points in the turned frame
        picks = [row_of(points, t) for t in ([0, 0, 0], [300, 0, 200], [0, 200, 100], [300, 200, 200], [150, 200, 100])]
        landmarks = tuple((str(100 + k), f"PART-1:{k + 1}") for k in picks)
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(scan), "xyz"),
                              evidence(axes=("", "", ""), landmarks=landmarks, measured_dofs=("x", "y", "z")))
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertEqual([m.fe_node for m in proposal.mapping], [f"PART-1:{k + 1}" for k in range(len(points))])

    def test_coplanar_landmarks_and_a_stated_normal_on_the_top_of_a_solid(self):
        points = block()
        top = points[points[:, 2] == 40.0]
        rows = [row_of(top, t) for t in ([0, 0, 40], [300, 0, 40], [0, 200, 40])]
        landmarks = [(str(100 + r), f"PART-1:{row_of(points, top[r]) + 1}") for r in rows]
        scan = top.copy()
        fe = fe_dataset(points)
        no_axes = evidence(axes=("", "", "+Z"), landmarks=tuple(landmarks))
        proposal = gr.propose(fe, experimental_dataset(in_metres(scan)), no_axes)
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertTrue(all(points[int(m.fe_node.split(":")[1]) - 1][2] == 40.0 for m in proposal.mapping))

    def test_a_bare_node_number_is_accepted_when_it_is_unique(self):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)),
                              evidence(landmarks=(("100", "1"),)))
        self.assertTrue(proposal.proposed, proposal.problems)


class MissingEvidenceTests(unittest.TestCase):
    def check_missing(self, word, **changes):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence(**changes))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(proposal.mapping, ())
        self.assertEqual(proposal.problems[0].code, gr.MISSING)
        self.assertIn(word, proposal.problems[0].text)

    def test_each_statement_is_required(self):
        self.check_missing("units", fe_unit="")
        self.check_missing("units", experimental_unit="")
        self.check_missing("measured side", measured_side="")
        self.check_missing("measured DOFs", measured_dofs=())
        self.check_missing("landmark", landmarks=())
        self.check_missing("established", source=" ")

    def test_nothing_stated_is_required_with_every_reason(self):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), gr.Evidence())
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        for word in ("units", "side", "DOFs", "landmark", "established"):
            self.assertIn(word, proposal.problems[0].text)


class AmbiguityTests(unittest.TestCase):
    def check(self, code, points, scan=None, **changes):
        scan = points if scan is None else scan
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(scan)), evidence(**changes))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED, proposal.checks)
        self.assertEqual(proposal.mapping, ())
        self.assertIn(code, [problem.code for problem in proposal.problems])
        return proposal

    def test_no_axes_and_one_landmark(self):
        self.check(gr.AMBIGUOUS, plate(), axes=("", "", ""))

    def test_collinear_landmarks_on_a_beam_without_axes(self):
        self.check(gr.AMBIGUOUS, beam(), axes=("", "", ""), landmarks=(("100", "PART-1:1"), ("120", "PART-1:21")))

    def test_coplanar_landmarks_cannot_tell_which_way_the_plane_faces(self):
        landmarks = (("100", "PART-1:1"), ("108", "PART-1:9"), ("162", "PART-1:63"))
        self.check(gr.AMBIGUOUS, plate(), axes=("", "", ""), landmarks=landmarks)
        self.check(gr.AMBIGUOUS, plate(), axes=("+X", "", ""), landmarks=landmarks)

    def test_two_axes_along_one_direction(self):
        self.check(gr.AMBIGUOUS, plate(), axes=("+X", "+X", "+Z"))

    def test_a_symmetric_plate_is_named_as_decided_only_by_the_evidence(self):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence())
        self.assertTrue(proposal.proposed)
        self.assertGreater(proposal.metrics["other_orientations"], 0)
        self.assertTrue(any("only your evidence separates them" in text for text in proposal.warnings))

    def test_a_turned_symmetric_plate_is_not_silently_corrected(self):
        """A scan turned 180 degrees with the axes stated unturned: the landmark shows the contradiction."""
        points = plate()
        turned = np.array([[400.0, 300.0, 0.0]]) - points * np.array([1.0, 1.0, -1.0])
        landmarks = (("100", "PART-1:1"), ("162", "PART-1:63"))
        self.check(gr.LANDMARK, points, turned, landmarks=landmarks)


class MirroredOrientationTests(unittest.TestCase):
    def test_left_handed_axes_are_refused(self):
        points = plate()
        mirrored = points * np.array([-1.0, 1.0, 1.0])
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(mirrored)),
                              evidence(axes=("-X", "+Y", "+Z")))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(proposal.problems[0].code, gr.MIRRORED)
        self.assertEqual(proposal.mapping, ())

    def test_a_mirrored_landmark_set_is_refused(self):
        points = block()
        scan = points * np.array([-1.0, 1.0, 1.0])
        picks = [row_of(points, t) for t in ([0, 0, 0], [300, 0, 0], [0, 200, 0], [0, 0, 40], [300, 200, 40])]
        landmarks = tuple((str(100 + k), f"PART-1:{k + 1}") for k in picks)
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(scan)),
                              evidence(axes=("", "", ""), landmarks=landmarks))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(proposal.problems[-1].code, gr.MIRRORED)

    def test_a_mirrored_plate_under_right_handed_axes_fails_on_its_landmarks(self):
        points = l_bracket()
        scan = points * np.array([-1.0, 1.0, 1.0])
        far = row_of(points, [480, 0, 0])
        landmarks = (("100", "PART-1:1"), (str(100 + far), f"PART-1:{far + 1}"))
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(scan)), evidence(landmarks=landmarks))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(proposal.problems[-1].code, gr.LANDMARK)


class DofTests(unittest.TestCase):
    def propose(self, components="z", **changes):
        points = plate()
        return gr.propose(fe_dataset(points), experimental_dataset(in_metres(points), components), evidence(**changes))

    def test_a_stated_dof_the_file_does_not_hold_is_refused(self):
        proposal = self.propose("z", measured_dofs=("x", "z"))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(proposal.problems[0].code, gr.DOF)
        self.assertIn("Experimental x is stated as measured", proposal.problems[0].text)

    def test_a_measured_dof_that_is_not_stated_is_refused(self):
        proposal = self.propose("xz", measured_dofs=("z",))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn("Experimental x is measured in the file", proposal.problems[0].text)

    def test_a_dof_absent_from_one_record_is_refused(self):
        points = plate()
        experimental = experimental_dataset(in_metres(points), "xz")
        experimental.modes[1].vectors[:, 0] = 0.0
        proposal = gr.propose(fe_dataset(points), experimental, evidence(measured_dofs=("x", "z")))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn("1 of 2 records", proposal.problems[0].text)

    def test_several_dofs_pass_when_they_agree(self):
        self.assertTrue(self.propose("xyz", measured_dofs=("x", "y", "z")).proposed)


class MappingTests(unittest.TestCase):
    def test_wrong_units_are_named(self):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)),
                              evidence(experimental_unit="mm", landmarks=(("100", "PART-1:1"), ("108", "PART-1:9"))))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(proposal.problems[-1].code, gr.LANDMARK)
        self.assertIn("check the units", proposal.problems[-1].text)

    def test_a_scan_far_from_the_mesh_fails_on_distance(self):
        points = plate(5, 4)
        scan = plate(21, 16)  # four times finer than the FE mesh: most points have no FE node of their own
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(scan)), evidence())
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertTrue(proposal.mapping)  # the failing mapping is displayed
        self.assertTrue({gr.MAPPING, gr.SHARED} & {problem.code for problem in proposal.problems})

    def test_points_sharing_an_fe_node_are_refused(self):
        points = plate(41, 31)
        scan = points[:2] * np.array([1.0, 1.0, 1.0])
        scan[1] = scan[0] + np.array([0.01, 0.0, 0.0])
        extra = np.array([[400.0, 300.0, 0.0]])
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(np.vstack((scan, extra)))), evidence())
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn(gr.SHARED, [problem.code for problem in proposal.problems])

    def test_unknown_or_repeated_landmarks_are_refused(self):
        points = plate()
        experimental = experimental_dataset(in_metres(points))
        cases = (((("999", "PART-1:1"),), "Experimental point 999"),
                 ((("100", "PART-1:9999"),), "9999"),
                 ((("100", "PART-1:1"), ("100", "PART-1:2")), "repeats"))
        for landmarks, word in cases:
            proposal = gr.propose(fe_dataset(points), experimental, evidence(landmarks=landmarks))
            self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED, landmarks)
            self.assertIn(word, proposal.problems[0].text)

    def test_a_bare_number_in_two_instances_is_refused(self):
        points = plate(3, 2)
        labels = [f"{name}:{k}" for name in ("A", "B") for k in (1, 2, 3)]
        proposal = gr.propose(fe_dataset(points, labels), experimental_dataset(in_metres(points)),
                              evidence(landmarks=(("100", "1"),)))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn("2 instances", proposal.problems[0].text)

    def test_local_coordinate_systems_stop_the_check(self):
        points = plate()
        metadata = {"local_coordinate_system_diagnostics": {"coordinate_system_dataset_2420_present": True}}
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points), metadata=metadata), evidence())
        self.assertEqual(proposal.problems[0].code, gr.LOCAL_AXES)

    def test_records_of_different_geometry_are_refused(self):
        points = plate()
        experimental = experimental_dataset(in_metres(points))
        experimental.modes[1].coordinates = experimental.modes[1].coordinates + 1.0
        proposal = gr.propose(fe_dataset(points), experimental, evidence())
        self.assertEqual(proposal.problems[0].code, gr.GEOMETRY)


class MeasuredSideTests(unittest.TestCase):
    def test_the_top_is_found_on_a_solid(self):
        points = block()
        top = points[points[:, 2] == 40.0]
        landmark = row_of(points, top[0])
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(top)),
                              evidence(landmarks=(("100", f"PART-1:{landmark + 1}"),)))
        self.assertTrue(proposal.proposed, proposal.problems)

    def test_a_scan_of_the_bottom_stated_as_the_top_is_refused(self):
        points = block()
        bottom = points[points[:, 2] == 0.0]
        landmark = row_of(points, bottom[0])
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(bottom)),
                              evidence(landmarks=(("100", f"PART-1:{landmark + 1}"),)))
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn(gr.SIDE, [problem.code for problem in proposal.problems])

    def test_a_flat_mesh_says_the_side_is_only_stated(self):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence())
        self.assertTrue(any("no depth" in text for text in proposal.warnings))


class NoModalDataTests(unittest.TestCase):
    """Orientation is never chosen by MAC, frequency or modal pairing."""

    def test_frequencies_and_shapes_change_nothing(self):
        points = l_bracket()
        first = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence())
        other = gr.propose(fe_dataset(points, frequency=777.0, seed=50),
                           experimental_dataset(in_metres(points), frequency=3.0, seed=90), evidence())
        self.assertEqual(first, other)

    def test_the_service_reads_no_frequency_or_fe_shape_and_imports_no_comparator(self):
        path = ROOT / "src" / "services" / "generic_registration.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse({"frequency_hz", "vectors", "mac", "mac_matrix", "sorted_modes"} & attributes)
        imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertFalse({"modal_core", "quality_control", "amplitude_correlation"} & imported)
        names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
        self.assertEqual({"experimental_measurement_masks"}, names & {"experimental_measurement_masks",
                                                                      "compare_modal_datasets",
                                                                      "FrozenRegistration"})

    def test_a_proposal_is_no_frozen_registration(self):
        points = plate()
        proposal = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence())
        for name in ("registration", "registration_hash", "to_dict"):
            self.assertFalse(hasattr(proposal, name))

    def test_the_same_evidence_always_gives_the_same_result(self):
        points = plate()
        first = gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence())
        self.assertEqual(first, gr.propose(fe_dataset(points), experimental_dataset(in_metres(points)), evidence()))
        self.assertNotEqual(first.evidence_hash, evidence(source="another").evidence_hash)


class LandmarkTextTests(unittest.TestCase):
    def test_pairs_and_bad_lines(self):
        pairs, bad = parse_landmarks("100, PART-1:1\n\n101;PART-1:2\n102 7\nonly\na,b,c\n")
        self.assertEqual(pairs, (("100", "PART-1:1"), ("101", "PART-1:2"), ("102", "7")))
        self.assertEqual(bad, ("only", "a,b,c"))


class _Gui(base._Case):
    def analysed(self, nodes=None):
        nodes = nodes or base.plate_nodes()
        window = pw.ProductionWindow(analyze_options={"runner": base.Runner(nodes), "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.show()
        panel = window.analyze
        panel.choose_file(FE, str(self.odb))
        self.exp_path = self.unv(nodes)
        panel.choose_file(EXPERIMENTAL, str(self.exp_path))
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        return window, panel

    def fill(self, dialog, panel):
        fe = panel.inputs.full_fe.dataset.modes[0]
        exp = panel.inputs.full_experimental.sets[0].dataset.modes[0]
        ratio = np.ptp(fe.coordinates, axis=0).max() / np.ptp(exp.coordinates, axis=0).max()
        self.assertAlmostEqual(ratio, 1.0)
        for combo, value in ((dialog.fe_unit, "m"), (dialog.experimental_unit, "m"), (dialog.side, "+Z")):
            combo.setCurrentIndex(combo.findData(value))
        for combo, value in zip(dialog.axes, RIGHT):
            combo.setCurrentIndex(combo.findData(value))
        dialog.dofs["z"].setChecked(True)
        dialog.landmarks.setPlainText(f"{exp.node_ids[0]}, {fe.node_ids[0]}\n{exp.node_ids[-1]}, {fe.node_ids[-1]}")
        dialog.source.setText("marker photograph")

    def run_check(self, dialog, panel):
        self.assertTrue(dialog.check())
        self.wait(panel)
        return dialog.proposal


class GuiTests(_Gui):
    def test_the_action_is_compact_and_opens_an_empty_form(self):
        _window, panel = self.analysed()
        self.assertEqual(panel.registration_button.text(), SET_UP_REGISTRATION)
        self.assertTrue(panel.registration_button.isVisible())
        panel.registration_button.click()
        dialog = panel.registration_dialog
        self.assertTrue(dialog.isVisible())
        stated = dialog.evidence()[0]
        self.assertEqual(stated, gr.Evidence(fe_unit="", experimental_unit="", axes=("", "", ""), measured_side="",
                                             measured_dofs=(), landmarks=(), source=""))

    def test_empty_evidence_shows_what_is_needed_and_the_page_is_unchanged(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        proposal = self.run_check(dialog, panel)
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(dialog.status_label.text(), gr.REGISTRATION_REQUIRED)
        self.assertIn("Still needed", dialog.problem_label.text())
        self.assertEqual(panel.proposal_label.text(), REFUSED_TEXT)
        self.assertEqual(panel.status_label.text(), am.REGISTRATION_REQUIRED)

    def test_a_good_statement_shows_the_mapping_and_stays_diagnostic(self):
        window, panel = self.analysed()
        dialog = panel.open_registration()
        self.fill(dialog, panel)
        with mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")):
            proposal = self.run_check(dialog, panel)
        self.assertEqual(proposal.status, gr.REGISTRATION_PROPOSED, proposal.problems)
        self.assertEqual(dialog.table.rowCount(), len(proposal.mapping))
        self.assertEqual(dialog.status_label.text(), gr.REGISTRATION_PROPOSED)
        self.assertEqual(panel.proposal_label.text(), PROPOSED_TEXT)
        self.assertTrue(panel.proposal_label.isVisible())
        # the result itself: still required, with no pair and no MAC
        self.assertEqual(panel.status_label.text(), am.REGISTRATION_REQUIRED)
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.analysis.comparison)
        self.assertNotIn("pairs", panel.tables)
        self.assertNotIn("mac", panel.tables)
        self.assertEqual(len(panel.analysis.fe_rows), 20)
        headers = [dialog.table.horizontalHeaderItem(c).text() for c in range(dialog.table.columnCount())]
        self.assertNotIn("MAC", headers)

    def test_a_changed_file_gives_required_and_a_stale_reason(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.fill(dialog, panel)
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        proposal = self.run_check(dialog, panel)
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(proposal.problems[0].code, gr.STALE)
        self.assertEqual(proposal.mapping, ())

    def test_a_changed_fe_package_gives_required(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.fill(dialog, panel)
        folder = panel.inputs.full_fe.manifest_path.parent
        mode_file = next(folder.glob("mode_*.csv"))
        mode_file.write_bytes(mode_file.read_bytes() + b"\n")
        self.assertEqual(self.run_check(dialog, panel).problems[0].code, gr.STALE)

    def test_replacing_a_file_removes_the_dialog_and_the_proposal(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.fill(dialog, panel)
        self.run_check(dialog, panel)
        self.assertIsNotNone(panel.proposal)
        panel.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes(), name="another.unv")))
        self.assertIsNone(panel.proposal)
        self.assertIsNone(panel.registration_dialog)
        self.assertIsNone(panel.registration_button)

    def test_a_new_analysis_removes_the_proposal(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.fill(dialog, panel)
        self.run_check(dialog, panel)
        self.run_analysis(panel)
        self.assertIsNone(panel.proposal)
        self.assertFalse(panel.proposal_label.isVisible())

    def test_a_bad_landmark_line_is_shown(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        dialog.landmarks.setPlainText("only one value")
        self.assertFalse(dialog.check())
        self.assertIn("only one value", dialog.problem_label.text())

    def test_closing_the_dialog_keeps_the_first_twenty_result(self):
        _window, panel = self.analysed()
        rows = panel.analysis.fe_rows
        dialog = panel.open_registration()
        dialog.close()
        self.assertEqual(panel.analysis.fe_rows, rows)
        self.assertEqual(panel.state, DONE)

    def test_no_action_without_a_result(self):
        window = pw.ProductionWindow(analyze_options={"discover": base.FOUND})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        self.assertIsNone(window.analyze.open_registration())
        self.assertIsNone(window.analyze.registration_button)

    def test_a_verified_result_offers_no_setup(self):
        verified = am.rm.RegistrationOutcome(0, view=mock.Mock(registration="hash-1"))
        cells = ("7", "20.0", "EXP1", "1", "20.5", "-2.44", "0.981", "paired", "")
        view = mock.Mock(status=cm.PAIRS_FOUND, pair_rows=(mock.Mock(cells=cells),), mac_cells=(("0.981",),),
                         mac_fe_modes=(7,), mac_experimental_modes=(1,), warnings=())
        with mock.patch.object(am.rm, "run_check", return_value=verified), \
                mock.patch.object(cm, "run_compare", return_value=cm.ComparisonOutcome(0, view=view)):
            _window, panel = self.analysed()
        self.assertEqual(panel.status_label.text(), cm.PAIRS_FOUND)
        self.assertIsNone(panel.registration_button)
        self.assertIsNone(panel.open_registration())

    def test_the_dialog_text_is_clean(self):
        window, panel = self.analysed()
        dialog = panel.open_registration()
        self.fill(dialog, panel)
        self.run_check(dialog, panel)
        texts = [button.text() for button in dialog.findChildren(QPushButton)]
        texts += [label.text() for label in dialog.findChildren(type(dialog.busy_label))]
        self.assertEqual([t for t in texts if FORBIDDEN.search(t)], [])


if __name__ == "__main__":
    unittest.main()
