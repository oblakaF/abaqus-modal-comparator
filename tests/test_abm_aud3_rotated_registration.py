"""ABM-AUD-3: a flat scan turned by any angle is registered from stated physical evidence, through the real page.

The scenario of the audit, with synthetic data only: an FE model 301 mm square in millimetres, and a 17 x 17 measurement
grid 277 mm wide inside it, written in metres in a frame turned 45 degrees about the normal with its own origin. The
rotation comes from three landmarks (experimental point = the FE place where it physically lies) and the stated
out-of-plane axis; no frequency, shape or MAC takes part. Everything refused stays REGISTRATION_REQUIRED.
"""

from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

import numpy as np

import test_universal_two_file_analysis as base
import test_universal_reg1_registration as reg1
import test_universal_reg3_confirmed as reg3
import test_working_draft_r2_project as r2
from test_universal_ui2_clean import FORBIDDEN

from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea

from domain.specimen_manifest import canonical_hash
import modal_core
from new_gui import analyze_model as am
from new_gui import analyze_panel
from new_gui import comparison_model as cm
from new_gui import confirmation_dialog
from new_gui import registration_dialog as rd
from new_gui.analyze_panel import DONE, UNUSABLE_TEXT
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from new_gui import project_model as pj
from services import generic_registration as gr

SIDE_MM, MESH, GRID, MARGIN = 301.0, 44, 17, 12.0  # FE 301 mm on a 7 mm mesh; the scan is 277 mm wide inside it
ORIGIN = np.array([150.5, -80.0, 0.0])  # the measuring system's origin in FE millimetres
CORNERS = (0, GRID - 1, GRID * (GRID - 1))  # three grid corners: not on one line
RECORDS = reg3.RECORDS


def turn(degrees: float) -> np.ndarray:
    """R of x_FE = R (s x_EXP) + t: a rotation about the FE normal."""
    angle = np.radians(degrees)
    return np.array([[np.cos(angle), -np.sin(angle), 0.0], [np.sin(angle), np.cos(angle), 0.0], [0.0, 0.0, 1.0]])


def fe_points(mesh=MESH) -> np.ndarray:
    line = np.linspace(0.0, SIDE_MM, mesh)
    return np.array([[x, y, 0.0] for y in line for x in line])


def grid_points(low=MARGIN, high=SIDE_MM - MARGIN, count=GRID) -> np.ndarray:
    """Where the measured points physically lie, in FE millimetres."""
    line = np.linspace(low, high, count)
    return np.array([[x, y, 0.0] for y in line for x in line])


def in_scan_frame(points, degrees=45.0, origin=ORIGIN, unit=1000.0) -> np.ndarray:
    """The same places as the measuring system writes them: x_EXP = R^T (x_FE - t) / s."""
    return ((np.asarray(points) - origin) @ turn(degrees)) / unit


def shape(k: int, points) -> np.ndarray:
    """A smooth out-of-plane shape, the same function on the FE nodes and on the measured places."""
    a, b = ((1, 1), (2, 1), (1, 2), (2, 2), (3, 1))[k]
    points = np.asarray(points)
    return np.cos(a * np.pi * points[:, 0] / SIDE_MM + 0.3 * k) * np.cos(b * np.pi * points[:, 1] / SIDE_MM + 0.2)


def placed(points, rows=CORNERS, offset=100) -> tuple:
    """Landmarks stated as FE positions: (experimental label, "(x, y, z)")."""
    return tuple((str(offset + row), gr.position_text(*points[row])) for row in rows)


def evidence(**changes) -> gr.Evidence:
    values = dict(fe_unit="mm", experimental_unit="m", axes=("", "", "+Z"), measured_side="+Z", measured_dofs=("z",),
                  landmarks=placed(grid_points()), source="measurement drawing with the grid corners dimensioned")
    values.update(changes)
    return gr.Evidence(**values)


def propose(scan=None, fe=None, **changes) -> gr.Proposal:
    scan = in_scan_frame(grid_points()) if scan is None else scan
    return gr.propose(reg1.fe_dataset(fe_points() if fe is None else fe), reg1.experimental_dataset(scan),
                      evidence(**changes))


def codes(proposal) -> list:
    return [problem.code for problem in proposal.problems]


def text_of(proposal) -> str:
    return " ".join(problem.text for problem in proposal.problems)


class TurnedScanTests(unittest.TestCase):
    def test_45_degrees_is_recovered_with_translation_and_unit_factor(self):
        proposal = propose()
        self.assertEqual(proposal.status, gr.REGISTRATION_PROPOSED, proposal.problems)
        np.testing.assert_allclose(np.asarray(proposal.rotation), turn(45.0), atol=1.0e-9)
        np.testing.assert_allclose(np.asarray(proposal.translation), ORIGIN, atol=1.0e-6)
        self.assertEqual(proposal.scale, 1000.0)
        self.assertAlmostEqual(float(np.linalg.det(np.asarray(proposal.rotation))), 1.0)
        self.assertEqual(proposal.axes_in_fe[2], "+Z")
        self.assertEqual(proposal.axes_in_fe[0], "(+0.707, +0.707, +0.000)")

    def test_every_point_keeps_its_identity_and_gets_the_fe_node_at_its_place(self):
        proposal = propose()
        places, nodes = grid_points(), fe_points()
        self.assertEqual([point.experimental_point for point in proposal.mapping], [str(100 + k) for k in range(GRID * GRID)])
        for point, place in zip(proposal.mapping, places):
            row = int(point.fe_node.split(":")[1]) - 1
            nearest = float(np.linalg.norm(nodes - place, axis=1).min())
            self.assertAlmostEqual(float(np.linalg.norm(nodes[row] - place)), nearest, places=6)
            self.assertAlmostEqual(point.distance, nearest, places=6)
        self.assertEqual(len({point.fe_node for point in proposal.mapping}), GRID * GRID)
        self.assertEqual([point.landmark for point in proposal.mapping].count(True), 3)
        self.assertLess(max(point.distance for point in proposal.mapping), SIDE_MM / (MESH - 1))  # within one mesh cell

    def test_a_scan_on_the_mesh_nodes_maps_to_exactly_those_nodes_with_node_landmarks(self):
        nodes = fe_points(87)  # 3.5 mm: a 280 mm grid at 17.5 mm starts on node 3 and takes every fifth node
        places = grid_points(10.5, 290.5)
        rows = [reg1.row_of(nodes, place) for place in places]
        landmarks = tuple((str(100 + k), f"PART-1:{rows[k] + 1}") for k in CORNERS)
        proposal = propose(in_scan_frame(places), nodes, landmarks=landmarks)
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertEqual([point.fe_node for point in proposal.mapping], [f"PART-1:{row + 1}" for row in rows])
        self.assertLess(max(point.distance for point in proposal.mapping), 1.0e-6)
        self.assertFalse(any("FE positions" in line for line in proposal.checks))

    def test_another_angle_origin_and_unit_are_not_special_cases(self):
        places = grid_points(60.0, 180.0, 9) @ turn(-27.5).T + np.array([40.0, 110.0, 0.0])  # tilted on the part itself
        origin = np.array([-512.0, 77.0, 3.0])
        scan = in_scan_frame(places, 112.0, origin, unit=10.0)  # the file is in centimetres
        proposal = propose(scan, experimental_unit="cm", landmarks=placed(places, (0, 8, 72)))
        self.assertTrue(proposal.proposed, proposal.problems)
        np.testing.assert_allclose(np.asarray(proposal.rotation), turn(112.0), atol=1.0e-9)
        np.testing.assert_allclose(np.asarray(proposal.translation), origin, atol=1.0e-6)
        self.assertEqual(proposal.scale, 10.0)
        self.assertIn("112.000 degrees about FE +Z", " ".join(proposal.details))
        nodes = fe_points()
        for point, place in zip(proposal.mapping, places):
            self.assertAlmostEqual(point.distance, float(np.linalg.norm(nodes - place, axis=1).min()), places=6)

    def test_a_clockwise_turn_is_named_with_its_sign(self):
        proposal = propose(in_scan_frame(grid_points(), -45.0))
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertIn("-45.000 degrees about FE +Z", " ".join(proposal.details))

    def test_the_details_state_the_transform_and_that_the_grid_is_not_the_part(self):
        details = " ".join(propose().details)
        for word in ("Rule: x_FE = R (1000 x_EXP) + t", "nothing is stretched, nothing is mirrored",
                     "Rotation R: 45.000 degrees about FE +Z", "Translation t: (150.5, -80, 0) mm",
                     "experimental m to FE mm, factor 1000", "Mapped points: 289 of 289", "3 are landmarks",
                     "FE outer dimensions (all FE nodes): X 0 to 301 (301), Y 0 to 301 (301)",
                     "Measurement grid in FE coordinates (289 points): X 12 to 289 (277), Y 12 to 289 (277)",
                     "92.0% along X, 92.0% along Y", "not the size of the part", "not stretched to the FE outline",
                     "Landmark consistency: 3 landmark(s)", "1.0000 times the experimental ones"):
            self.assertIn(word, details)

    def test_the_result_and_its_hashes_are_reproducible(self):
        first, second = propose(), propose()
        self.assertEqual(first, second)
        self.assertEqual(first.evidence_hash, evidence().evidence_hash)
        scan = reg1.experimental_dataset(in_scan_frame(grid_points()))
        kwargs = dict(modal_set={"key": "k"}, sources={"fe": {}, "experimental": {"sha256": "s", "size": 1}})
        one = gr.draft_bytes(gr.draft_document(first, evidence(), scan, **kwargs))
        two = gr.draft_bytes(gr.draft_document(second, evidence(), scan, **kwargs))
        self.assertEqual(one, two)
        self.assertNotIn("details", json.loads(one)["result"])  # described again each time, never stored

    def test_no_frequency_and_no_shape_takes_part(self):
        scan = in_scan_frame(grid_points())
        first = gr.propose(reg1.fe_dataset(fe_points()), reg1.experimental_dataset(scan), evidence())
        other = gr.propose(reg1.fe_dataset(fe_points(), frequency=777.0, seed=9),
                           reg1.experimental_dataset(scan, frequency=3.0, seed=11), evidence())
        self.assertEqual(first, other)

    def test_evidence_without_fe_positions_gives_the_checks_it_always_gave(self):
        """A draft stores its checks and is refused when they differ: the wording of old evidence must not move."""
        points = reg1.plate()
        proposal = gr.propose(reg1.fe_dataset(points), reg1.experimental_dataset(reg1.in_metres(points)), reg1.evidence(
            landmarks=(("100", "PART-1:1"), ("162", "PART-1:63"))))
        self.assertEqual(proposal.checks, (
            "Evidence stated by the user: marker photograph.", "Units: experimental m, FE mm (factor 1000).",
            "Measured DOFs z agree with the experimental records.",
            "Orientation from the stated axes ['+X', '+Y', '+Z'] (right-handed).",
            "2 landmarks agree: worst distance 0 mm.",
            "Mapping: 100.0% within 15 mm, RMS 0, largest distance 0."))


class RefusalTests(unittest.TestCase):
    def refused(self, code, word="", **arguments):
        proposal = propose(**arguments)
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED, proposal.checks)
        self.assertIn(code, codes(proposal), text_of(proposal))
        self.assertIn(word, text_of(proposal))
        self.assertFalse(proposal.proposed)
        return proposal

    def test_a_289_point_grid_with_no_landmark_is_registration_required(self):
        """What real turned data without independent evidence must give: a refusal that says what is missing."""
        proposal = self.refused(gr.MISSING, "at least one landmark", landmarks=())
        self.assertEqual(proposal.mapping, ())
        self.assertEqual(self.refused(gr.MISSING, "how the evidence was established", source="").mapping, ())

    def test_landmarks_on_one_line_leave_the_rotation_free(self):
        self.refused(gr.AMBIGUOUS, "not on one line", landmarks=placed(grid_points(), (0, 8, 16)))
        self.refused(gr.AMBIGUOUS, "not on one line", landmarks=placed(grid_points(), (0,)))

    def test_without_the_out_of_plane_axis_the_facing_is_unknown(self):
        self.refused(gr.AMBIGUOUS, "out of that plane", axes=("", "", ""))

    def test_a_wrong_unit_is_named_with_the_factor(self):
        proposal = self.refused(gr.LANDMARK, "check the units", experimental_unit="mm")
        self.assertIn("A factor of 1000 is m against mm", text_of(proposal))
        self.refused(gr.LANDMARK, "check the units", fe_unit="m")

    def test_an_in_plane_axis_stated_against_the_landmarks_is_a_contradiction(self):
        proposal = self.refused(gr.LANDMARK, "45.0 degrees from the stated +X", axes=("+X", "", "+Z"))
        self.assertIn("leave its in-plane axes not stated", text_of(proposal))

    def test_a_mirrored_scan_is_refused(self):
        mirrored = in_scan_frame(grid_points()) * np.array([-1.0, 1.0, 1.0])
        proposal = self.refused(gr.MIRRORED, "mirror image", scan=mirrored)
        self.assertEqual(proposal.mapping, ())

    def test_the_opposite_facing_stated_is_refused(self):
        self.refused(gr.MIRRORED, "opposite face", axes=("", "", "-Z"))

    def test_the_scan_extent_taken_for_the_fe_outline_is_refused_and_explained(self):
        corners = ((0.0, 0.0, 0.0), (SIDE_MM, 0.0, 0.0), (0.0, SIDE_MM, 0.0))
        landmarks = tuple((str(100 + row), gr.position_text(*corner)) for row, corner in zip(CORNERS, corners))
        proposal = self.refused(gr.LANDMARK, "never stretched", landmarks=landmarks)
        self.assertIn("1.087 times", text_of(proposal))  # 301 / 277
        self.assertEqual(proposal.mapping, ())

    def test_measured_dofs_must_be_those_of_the_file(self):
        self.refused(gr.DOF, "Experimental x is stated as measured", measured_dofs=("x", "z"))
        self.refused(gr.MISSING, "the measured DOFs", measured_dofs=())

    def test_a_landmark_position_must_be_a_place_on_the_measured_part(self):
        far = ((str(100 + CORNERS[0]), gr.position_text(12.0, 12.0, 250.0)),) + placed(grid_points(), CORNERS[1:])
        self.refused(gr.AMBIGUOUS, "", landmarks=far[:1])  # one landmark alone never fixes a turned scan
        proposal = propose(landmarks=((far[0][0], "(12, 12)"),) + far[1:])
        self.assertIn("is not an FE position", text_of(proposal))
        proposal = propose(landmarks=((far[0][0], "(nan, 12, 0)"),) + far[1:])
        self.assertIn("is not an FE position", text_of(proposal))
        lifted = tuple((label, gr.position_text(*(np.array(gr.landmark_position(place)) + [0.0, 0.0, 250.0])))
                       for label, place in placed(grid_points()))
        proposal = propose(landmarks=lifted)
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn(gr.SIDE, codes(proposal))
        self.assertIn("not on the stated measured face or part", text_of(proposal))

    def test_a_repeated_place_is_refused(self):
        marks = placed(grid_points())
        self.refused(gr.LANDMARK, "repeats", landmarks=(marks[0], (marks[1][0], marks[0][1]), marks[2]))

    def test_the_other_side_of_a_solid_is_refused(self):
        """The measured side is checkable where the mesh has depth: the landmarks lie on the top, the bottom is stated."""
        line = np.linspace(0.0, SIDE_MM, 44)
        solid = np.array([[x, y, z] for z in (0.0, 20.0, 40.0) for y in line for x in line])
        top = grid_points() + np.array([0.0, 0.0, 40.0])
        good = propose(in_scan_frame(top), solid, landmarks=placed(top))
        self.assertTrue(good.proposed, good.problems)
        self.assertTrue(all(solid[int(point.fe_node.split(":")[1]) - 1][2] == 40.0 for point in good.mapping))
        proposal = propose(in_scan_frame(top), solid, landmarks=placed(top), measured_side="-Z")
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn(gr.SIDE, codes(proposal))

    def test_with_two_fe_parts_the_measured_one_must_be_stated_and_hold_the_landmarks(self):
        nodes = fe_points()
        both = np.vstack((nodes, nodes + np.array([0.0, 0.0, 400.0])))
        labels = [f"SKIN:{k + 1}" for k in range(len(nodes))] + [f"OTHER:{k + 1}" for k in range(len(nodes))]
        fe = reg1.fe_dataset(both, labels)
        scan = reg1.experimental_dataset(in_scan_frame(grid_points()))
        missing = gr.propose(fe, scan, evidence())
        self.assertIn("which FE part was measured", text_of(missing))
        self.assertTrue(gr.propose(fe, scan, evidence(measured_instance="SKIN")).proposed)
        wrong = gr.propose(fe, scan, evidence(measured_instance="OTHER"))
        self.assertEqual(wrong.status, gr.REGISTRATION_REQUIRED)
        self.assertIn(gr.SIDE, codes(wrong))

    def test_a_symmetric_grid_is_decided_only_by_the_evidence_and_says_so(self):
        proposal = propose()
        self.assertTrue(proposal.proposed)
        self.assertGreater(proposal.metrics["other_orientations"], 0)
        self.assertTrue(any("only your evidence separates them" in text for text in proposal.warnings))
        self.assertTrue(any("the mesh cannot confirm it" in text for text in proposal.warnings))  # a flat mesh has no side

    def test_no_orientation_is_tried_or_scored(self):
        """One rigid fit of the stated landmarks; the service imports no comparator and reads no shape."""
        source = (reg1.ROOT / "src" / "services" / "generic_registration.py").read_text(encoding="utf-8")
        for word in ("import modal_core", "from modal_core", "compare_modal_datasets", "frequency_hz", ".vectors",
                     "mac("):
            self.assertNotIn(word, source)


class LandmarkTextTests(unittest.TestCase):
    def test_a_position_is_read_in_both_spellings_and_written_back_the_same(self):
        pairs, bad = rd.parse_landmarks("1, 12, 12, 0\n17,(289, 12.0, 0)\n273 12 289 0\n5, PART-1:9\n7, 1, 2\n8, a, b, c\n")
        self.assertEqual(pairs, (("1", "(12.0, 12.0, 0.0)"), ("17", "(289.0, 12.0, 0.0)"), ("273", "(12.0, 289.0, 0.0)"),
                                 ("5", "PART-1:9")))
        self.assertEqual(bad, ("7, 1, 2", "8, a, b, c"))
        again, _bad = rd.parse_landmarks("\n".join(f"{point}, {place}" for point, place in pairs))
        self.assertEqual(again, pairs)
        self.assertEqual(gr.landmark_position("(12.0, 12.0, 0.0)"), (12.0, 12.0, 0.0))
        self.assertIsNone(gr.landmark_position("PART-1:9"))


# ------------------------------------------------------------------------------------------- through the real page

def fe_nodes():
    return [(k + 1, float(x), float(y), float(z)) for k, (x, y, z) in enumerate(fe_points())]


def fe_modes(nodes):
    """Rigid modes 1-6, then elastic modes whose U3 is the smooth shape of record k, 2.4 % below its frequency."""
    points = np.array([n[1:4] for n in nodes])
    rigid = base.rigid_shapes(nodes)
    modes = [(i + 1, 0.0011 + 0.0001 * i, vectors) for i, vectors in enumerate(rigid)]
    for number in range(len(rigid) + 1, 26):
        k = number - len(rigid) - 1
        vectors = np.zeros_like(points)
        vectors[:, 2] = shape(k, points) if k < RECORDS else np.random.default_rng(number).standard_normal(len(points))
        modes.append((number, reg3.record_hz(k) * 0.976 if k < RECORDS else 5000.0 + 50.0 * number, vectors))
    return modes


class _Turned(r2._Project):
    nodes = staticmethod(fe_nodes)

    def modes(self):
        return fe_modes(self.nodes())

    def scan_file(self, name="turned scan.unv", degrees=45.0, sets=None):
        places = grid_points()
        scan = in_scan_frame(places, degrees)
        nodes = [(k + 1, float(x), float(y), float(z)) for k, (x, y, z) in enumerate(scan)]
        return base.write_unv(self.inputs / name, nodes, reg3.freqs(), sets, [shape(k, places) for k in range(RECORDS)])

    def analysed(self, frequencies=None, unv=None):
        return super().analysed(frequencies, unv or self.scan_file())

    def state_evidence(self, dialog, panel, axes=("", "", "+Z")):
        for combo, value in ((dialog.fe_unit, "mm"), (dialog.experimental_unit, "m"), (dialog.side, "+Z")):
            combo.setCurrentIndex(combo.findData(value))
        for combo, value in zip(dialog.axes, axes):
            combo.setCurrentIndex(combo.findData(value))
        dialog.dofs["z"].setChecked(True)
        places = grid_points()
        dialog.landmarks.setPlainText("\n".join(
            f"{row + 1}, {places[row][0]:g}, {places[row][1]:g}, {places[row][2]:g}" for row in CORNERS))
        dialog.source.setText("measurement drawing with the grid corners dimensioned")

    def checked(self, panel, **changes):
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel, **changes)
        self.assertTrue(dialog.check())
        self.wait(panel)
        return dialog

    def assert_pairs(self, analysis):
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        rows = analysis.comparison.pair_rows
        self.assertEqual([(row.abaqus_mode, row.experimental_mode) for row in rows],
                         [(reg3.FIRST_ELASTIC + k, k + 1) for k in range(RECORDS)])
        for row in rows:
            self.assertGreater(row.mac, 0.99)  # the FE shape is read at the nearest node of a 7 mm mesh
            self.assertAlmostEqual(row.frequency_error_percent, -2.4, places=2)


class PageWorkflowTests(_Turned):
    def test_the_form_says_what_is_needed_and_where_it_comes_from(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        shown = " ".join(label.text() for label in dialog.findChildren(QLabel))
        for word in (rd.NEEDED, rd.TURNED, rd.LANDMARK_NOTE, *rd.SECTIONS, "Measured side", "Measured DOFs",
                     "FE: 1936 points (x 0 to 301, y 0 to 301", "Experimental: 289 points"):
            self.assertIn(word, shown)
        self.assertEqual(dialog.evidence()[0], gr.Evidence())  # nothing is prefilled
        self.assertEqual([text for text in [label.text() for label in dialog.findChildren(QLabel)]
                          + [button.text() for button in dialog.findChildren(QPushButton)] if FORBIDDEN.search(text)], [])
        available = dialog.screen().availableGeometry()
        self.assertLessEqual(dialog.height(), available.height())
        self.assertLessEqual(dialog.width(), available.width())
        area = dialog.findChild(QScrollArea)  # the form wraps inside the dialog: nothing is cut off at the right
        self.app.processEvents()
        self.assertLessEqual(area.widget().minimumSizeHint().width(), area.viewport().width())
        self.assertFalse(area.horizontalScrollBar().isVisible())

    def test_the_check_shows_the_rotation_the_translation_and_the_coverage(self):
        _window, panel = self.analysed()
        with mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")), \
                mock.patch.object(cm, "run_compare_confirmed", side_effect=AssertionError("no comparison")):
            dialog = self.checked(panel)
        proposal = dialog.proposal
        self.assertEqual(proposal.status, gr.REGISTRATION_PROPOSED, proposal.problems)
        np.testing.assert_allclose(np.asarray(proposal.rotation), turn(45.0), atol=1.0e-5)  # the file keeps 6 digits
        np.testing.assert_allclose(np.asarray(proposal.translation), ORIGIN, atol=1.0e-2)
        details = dialog.details_label.text()
        for word in ("Rotation R: 45.000 degrees about FE +Z", "factor 1000", "Mapped points: 289 of 289",
                     "X 0 to 301 (301)", "(277)", "not stretched to the FE outline", "Landmark consistency: 3 landmark(s)"):
            self.assertIn(word, details)
        self.assertEqual(dialog.table.rowCount(), GRID * GRID)
        self.assertLessEqual(dialog.table.height(), 260)  # 289 rows scroll inside the table, not the whole dialog
        self.assertEqual(dialog.status_label.text(), gr.REGISTRATION_PROPOSED)
        self.assertFalse(dialog.save_button.isEnabled())  # not before the review
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)  # the page's result has not moved
        self.assertNotIn("pairs", panel.tables)
        self.assertNotIn("mac", panel.tables)
        self.assertTrue(panel.compare_button is None or panel.compare_button.isHidden())

    def test_draft_confirmation_comparison_and_reopening_each_revalidate(self):
        window, panel = self.analysed()
        dialog = self.checked(panel)
        dialog.review_box.setChecked(True)
        self.draft_path = self.root / "turned draft.json"
        self.assertTrue(dialog.save_draft(str(self.draft_path)))
        self.wait(panel)
        draft = json.loads(self.draft_path.read_text(encoding="utf-8"))
        self.assertEqual(draft["status"], gr.DRAFT_STATUS)
        self.assertFalse(draft["accepted_physical_registration"])
        self.assertEqual(draft["evidence"]["axes"], ["", "", "+Z"])
        self.assertEqual(draft["evidence"]["landmarks"][0], ["1", "(12.0, 12.0, 0.0)"])
        self.assertEqual(draft["sources"]["experimental"]["sha256"], base.sha(self.exp_path))
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)  # a draft is not a registration
        window.close()

        # the program is started again: the draft is reopened and reproduced on the files as they are now
        _second, again = self.analysed(unv=self.exp_path)
        reopened = again.open_registration()
        self.assertTrue(reopened.open_draft(str(self.draft_path)))
        self.wait(again)
        self.assertTrue(reopened.proposal.proposed, reopened.proposal.problems)
        self.assertEqual(reopened.draft_note.text(), rd.REPRODUCED)
        self.assertEqual(reopened.evidence()[0].landmarks[0], ("1", "(12.0, 12.0, 0.0)"))
        self.assertFalse(reopened.review_box.isChecked())  # an opened draft is shown unreviewed
        self.assertFalse(reopened.confirm_button.isEnabled())
        reopened.review_box.setChecked(True)
        confirming = self.confirmation_dialog(reopened, again)
        shown = " ".join(label.text() for label in confirming.findChildren(QLabel))
        for word in ("Rotation R: 45.000 degrees about FE +Z", "Experimental point 1 = FE position (12.0, 12.0, 0.0) mm",
                     "Stated axes: +x → not stated, +y → not stated, +z → +Z", "X 0 to 301 (301)", "(277)",
                     "not proof of physical correctness"):
            self.assertIn(word, shown)
        self.assertEqual(confirming.table.rowCount(), GRID * GRID)
        self.sign(confirming, "turned confirmation.json")
        self.wait(again)
        self.assertTrue(self.confirmation_path.is_file(), confirming.message.text())
        self.assertEqual(again.analysis.status, am.REGISTRATION_REQUIRED)  # saved, not applied
        _second.close()

        # started once more: the confirmation is reopened, revalidated, and used only on command
        _third, panel3 = self.analysed(unv=self.exp_path)
        self.assertTrue(panel3.open_confirmation(str(self.confirmation_path)))
        self.wait(panel3)
        self.assertIsNotNone(panel3.confirmation_view, panel3.proposal_label.text())
        self.assertIsNone(panel3.confirmation)
        self.assertEqual(panel3.analysis.status, am.REGISTRATION_REQUIRED)
        panel3.confirmation_view.use_existing()
        real = modal_core.compare_modal_datasets
        with mock.patch.object(modal_core, "compare_modal_datasets", side_effect=real) as comparator:
            analysis = self.compare(panel3)
        self.assert_pairs(analysis)
        registration = comparator.call_args.kwargs["frozen_registration"]
        np.testing.assert_allclose(np.asarray(registration.rotation), turn(45.0), atol=1.0e-5)
        self.assertEqual(list(registration.experimental_node_ids), list(range(1, GRID * GRID + 1)))
        self.assertEqual(analysis.rigid_modes, tuple(range(1, reg3.FIRST_ELASTIC)))
        self.assertEqual(analysis.first_elastic, str(reg3.FIRST_ELASTIC))
        self.assertEqual(panel3.status_label.text(), am.CONFIRMED_COMPARISON)
        self.assertNotEqual(panel3.status_label.property("state"), "read")  # a statement, never shown as verified

        # saved with the page's own command, closed, opened: a snapshot, not a result verified now
        self.saved(panel3)
        _fourth, snapshot = self.reopened()
        self.assertIsNotNone(snapshot.snapshot)
        self.assertIsNone(snapshot.inputs)
        self.assertIsNone(snapshot.confirmation)
        self.assertEqual(snapshot.status_label.text(), am.CONFIRMED_COMPARISON)
        self.assertEqual(snapshot.status_label.property("state"), "chosen")
        self.assertEqual(snapshot.analysis.comparison.pair_rows, analysis.comparison.pair_rows)
        self.assertIsNone(snapshot.compare_button)
        self.assertFalse(snapshot.compare_confirmed())
        self.assertFalse(snapshot.analyze())  # blocked until the sources are checked
        check = self.check(snapshot)
        self.assertTrue(check.can_analyze)
        self.assertEqual(self.row(snapshot, pj.ROLE_REGISTRATION).state, pj.NOT_REVALIDATED)
        self.assertTrue(snapshot.analyze())
        self.wait(snapshot)
        self.assertEqual(snapshot.state, DONE, snapshot.message.text())
        self.assertEqual(snapshot.analysis.status, am.REGISTRATION_REQUIRED)  # nothing is carried over from the file
        self.assertIsNone(snapshot.confirmation)
        self.assertTrue(snapshot.open_confirmation(str(self.confirmation_path)))
        self.wait(snapshot)
        snapshot.confirmation_view.use_existing()
        self.assert_pairs(self.compare(snapshot))

    def test_the_saved_project_records_a_statement_not_a_verification(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.saved(panel)
        document, _images = ap.read_project(self.project)
        registration = document["registration"]
        self.assertEqual(registration["kind"], ap.KIND_CONFIRMED)
        self.assertEqual(registration["confirmed_by"], "A. Tester")
        self.assertTrue(registration["limits"])
        self.assertEqual(document["sources"]["experimental"]["sha256"], base.sha(self.exp_path))


class PageRefusalTests(_Turned):
    def assert_nothing_compared(self, panel):
        self.assert_frequency_only(panel)
        self.assertIsNone(panel.confirmation)
        self.assertTrue(panel.compare_button is None or panel.compare_button.isHidden())

    def test_missing_evidence_is_explained_and_nothing_can_be_saved(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertEqual(dialog.status_label.text(), gr.REGISTRATION_REQUIRED)
        for word in ("coordinate units", "measured side", "measured DOFs", "landmark", "how the evidence was established"):
            self.assertIn(word, dialog.problem_label.text())
        self.assertIsNone(dialog.review_box)
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertFalse(dialog.confirm_button.isEnabled())
        self.assertFalse(dialog.save_draft(str(self.root / "no.json")))
        self.assertFalse((self.root / "no.json").exists())
        self.assert_nothing_compared(panel)

    def test_each_insufficient_statement_is_refused_in_words(self):
        _window, panel = self.analysed()
        places = grid_points()
        collinear = "\n".join(f"{row + 1}, {places[row][0]:g}, {places[row][1]:g}, 0" for row in (0, 8, 16))
        outline = "1, 0, 0, 0\n17, 301, 0, 0\n273, 0, 301, 0"
        cases = (("no facing", dict(axes=("", "", "")), None, None, "out of that plane"),
                 ("in-plane axis", dict(axes=("+X", "", "+Z")), None, None, "leave its in-plane axes not stated"),
                 ("opposite facing", dict(axes=("", "", "-Z")), None, None, "mirror image"),
                 ("collinear", {}, collinear, None, "not on one line"),
                 ("outline", {}, outline, None, "never stretched"),
                 ("units", {}, None, "mm", "check the units"),
                 ("bad line", {}, "1, 12, 12", None, "not a pair"))
        dialog = panel.open_registration()
        for name, changes, landmarks, unit, word in cases:
            with self.subTest(name):
                self.state_evidence(dialog, panel, **changes)
                if landmarks is not None:
                    dialog.landmarks.setPlainText(landmarks)
                if unit is not None:
                    dialog.experimental_unit.setCurrentIndex(dialog.experimental_unit.findData(unit))
                if dialog.check():
                    self.wait(panel)
                self.assertEqual(dialog.status_label.text(), gr.REGISTRATION_REQUIRED)
                self.assertIn(word, dialog.problem_label.text())
                self.assertFalse(dialog.save_button.isEnabled())
                self.assertEqual(panel.proposal_label.text(), analyze_panel.REFUSED_TEXT)
                self.assert_nothing_compared(panel)

    def test_an_unstated_measured_dof_is_refused(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel)
        dialog.dofs["z"].setChecked(False)
        dialog.dofs["x"].setChecked(True)
        dialog.check()
        self.wait(panel)
        self.assertIn("Experimental x is stated as measured", dialog.problem_label.text())
        self.assertIn("Experimental z is measured in the file, but it is not stated", dialog.problem_label.text())
        self.assert_nothing_compared(panel)

    def drafted(self, panel):
        dialog = self.checked(panel)
        self.assertTrue(dialog.proposal.proposed, dialog.proposal.problems)
        dialog.review_box.setChecked(True)
        self.draft_path = self.root / "draft.json"
        self.assertTrue(dialog.save_draft(str(self.draft_path)))
        self.wait(panel)
        return dialog

    def open_draft(self, dialog, panel, path=None):
        self.assertTrue(dialog.open_draft(str(path or self.draft_path)))
        self.wait(panel)
        return dialog.proposal

    def test_a_changed_experimental_file_stops_the_draft_and_the_confirmation(self):
        _window, panel = self.analysed()
        dialog = self.drafted(panel)
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        proposal = self.open_draft(dialog, panel)
        self.assertEqual(proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(codes(proposal), [gr.DRAFT_CHANGED])
        self.assertFalse(dialog.confirm_button.isEnabled())
        self.assert_nothing_compared(panel)

    def test_a_changed_fe_package_stops_the_draft(self):
        _window, panel = self.analysed()
        dialog = self.drafted(panel)
        mode_file = next(panel.inputs.full_fe.manifest_path.parent.glob("mode_*.csv"))
        mode_file.write_bytes(mode_file.read_bytes() + b"\n")
        self.assertEqual(codes(self.open_draft(dialog, panel)), [gr.DRAFT_CHANGED])
        self.assert_nothing_compared(panel)

    def test_another_fe_model_refuses_the_draft(self):
        """The same scan against an FE model shifted by 3 mm: other content, other geometry, no silent reuse."""
        _window, panel = self.analysed()
        self.drafted(panel)
        document = gr.read_draft(self.draft_path)
        scan = panel.inputs.full_experimental.sets[0].dataset
        other = copy.copy(panel.inputs.full_fe.dataset)
        other.modes = [copy.copy(mode) for mode in other.modes]
        for mode in other.modes:
            mode.coordinates = np.asarray(mode.coordinates) + np.array([3.0, 0.0, 0.0])
        result = gr.revalidate_draft(document, other, scan, modal_set=document["modal_set"], sources=document["sources"])
        self.assertEqual(codes(result.proposal), [gr.DRAFT_CHANGED])
        self.assertIn("another FE geometry", text_of(result.proposal))

    def test_another_modal_set_refuses_the_draft_and_the_confirmation(self):
        sets = (("Fitted A", reg3.freqs()), ("Fitted B", reg3.freqs()))
        unv = self.scan_file("two sets.unv", sets=sets)
        panel = self.window().analyze
        self.exp_path = unv
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(unv))
        self.run_analysis(panel)
        self.assertEqual(len(panel.inputs.full_experimental.sets), 2)
        self.assertTrue(panel.choose_set(0))
        self.wait(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        dialog = self.drafted(panel)
        confirming = self.confirmation_dialog(dialog, panel)
        self.sign(confirming)
        self.wait(panel)
        self.assertTrue(self.confirmation_path.is_file(), confirming.message.text())
        self.assertTrue(panel.choose_set(1))
        self.wait(panel)
        self.assertEqual(panel.analysis.set_index, 1)
        self.assertIsNone(panel.confirmation)  # the choice of another set drops it
        other = panel.open_registration()
        proposal = self.open_draft(other, panel)
        self.assertEqual(codes(proposal), [gr.DRAFT_CHANGED])
        self.assertIn("another modal set", text_of(proposal))
        self.assertTrue(panel.open_confirmation(str(self.confirmation_path)))
        self.wait(panel)
        self.assertTrue(panel.proposal_label.text().startswith(UNUSABLE_TEXT))
        self.assertIn("another modal set", panel.proposal_label.text())
        self.assert_nothing_compared(panel)

    def test_a_tampered_draft_is_refused_even_with_its_hash_recomputed(self):
        _window, panel = self.analysed()
        dialog = self.drafted(panel)
        document = json.loads(self.draft_path.read_text(encoding="utf-8"))
        plain = copy.deepcopy(document)
        plain["result"]["rotation"][0][0] = 1.0
        (self.root / "plain.json").write_text(json.dumps(plain), encoding="utf-8")
        self.assertEqual(codes(self.open_draft(dialog, panel, self.root / "plain.json")), [gr.DRAFT_TAMPERED])
        turned = copy.deepcopy(document)
        turned["result"]["rotation"] = turn(40.0).tolist()  # another angle, with a matching content hash
        body = {key: value for key, value in turned.items() if key != "draft_sha256"}
        turned["draft_sha256"] = canonical_hash(body)
        (self.root / "turned.json").write_text(json.dumps(turned), encoding="utf-8")
        proposal = self.open_draft(dialog, panel, self.root / "turned.json")
        self.assertEqual(codes(proposal), [gr.DRAFT_NOT_REPRODUCED])
        self.assertIn("rotation", text_of(proposal))
        self.assertFalse(dialog.confirm_button.isEnabled())
        self.assert_nothing_compared(panel)

    def test_a_tampered_confirmation_is_not_usable(self):
        _window, panel = self.analysed()
        dialog = self.drafted(panel)
        confirming = self.confirmation_dialog(dialog, panel)
        self.sign(confirming)
        self.wait(panel)
        document = json.loads(self.confirmation_path.read_text(encoding="utf-8"))
        document["draft"]["result"]["rotation"] = turn(40.0).tolist()
        (self.root / "edited.json").write_text(json.dumps(document), encoding="utf-8")
        panel.confirmation = None
        self.assertTrue(panel.open_confirmation(str(self.root / "edited.json")))
        self.wait(panel)
        self.assertTrue(panel.proposal_label.text().startswith(UNUSABLE_TEXT))
        self.assertIsNone(panel.confirmation)
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)

    def test_a_confirmation_made_stale_by_a_changed_file_gives_no_comparison(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        self.assertTrue(panel.compare_confirmed())
        self.wait(panel)
        self.assertNotEqual(getattr(panel.analysis, "status", ""), am.CONFIRMED_COMPARISON)
        self.assertNotIn("pairs", panel.tables)
        self.assertNotIn("mac", panel.tables)


class DisplayTests(unittest.TestCase):
    def test_the_confirmation_names_a_position_landmark_as_a_position(self):
        proposal = propose()
        scan = reg1.experimental_dataset(in_scan_frame(grid_points()))
        draft = gr.draft_document(proposal, evidence(), scan, modal_set={"key": "k", "display_name": "d", "record_count": 2},
                                  sources={"fe": {"package_sha256": "p"}, "experimental": {"sha256": "s", "size": 1}})
        facts = dict(confirmation_dialog.facts_of(draft, ("coverage line",)))
        self.assertIn("Experimental point 100 = FE position (12.0, 12.0, 0.0) mm", facts["Landmarks"])
        self.assertIn("Rotation R: 45.000 degrees about FE +Z (right-hand rule).", facts["Transform and coverage"])
        self.assertEqual(facts["Transform and coverage"][-1], "coverage line")
        self.assertEqual(gr.rotation_text(np.eye(3)), "none: the experimental axes are parallel to the FE axes")
        self.assertEqual(gr.rotation_text(np.diag([-1.0, -1.0, 1.0])), "180.000 degrees about FE +Z (right-hand rule)")
        self.assertEqual(gr.rotation_text(np.diag([1.0, -1.0, -1.0])), "180.000 degrees about FE +X (right-hand rule)")


if __name__ == "__main__":
    unittest.main()
