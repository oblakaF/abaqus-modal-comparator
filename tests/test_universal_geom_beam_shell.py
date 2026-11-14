"""UNIVERSAL-GEOM-1: the two-file comparison on a straight beam and on a hollow cylindrical shell. Synthetic data only.

Every shape is a closed-form expression, so each expected MAC is computed here from its definition, independently of the
program. Nothing in this module is a physical validation: the FE "extraction" and the UNV are written by the tests.

Beam: 15 nodes on a line, bending shapes w_k = sin((2k + 1) pi x / 2L), which are neither symmetric nor antisymmetric,
so a scan stated the wrong way round cannot pass.

Shell: a tube of nominal outside diameter 20 mm and length 120 mm. FE nodes on the mid-surface (radius 9.5 mm, 24 around,
13 stations); 40 sensors on the outside surface (radius 10 mm, 8 around, 5 stations), each measuring along its own
radius. Shell shapes w = cos(n theta + phi) g(z) radial with v = -(1/n) sin(n theta + phi) g(z) tangential.
"""

from __future__ import annotations

import math
from pathlib import Path
import threading
import unittest
from unittest import mock

import numpy as np

import test_universal_two_file_analysis as base
import test_universal_reg3_confirmed as reg3

import modal_core
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import registration_dialog as rd
from services import confirmed_registration as cs
from services import generic_registration as gr

# ---------------------------------------------------------------------------------------------------------- the beam

BEAM_LENGTH = 1.4
BEAM_SHAPES = 5


def beam_shape(k: int, x) -> np.ndarray:
    return np.sin((2 * k + 3) * np.pi * np.asarray(x, dtype=float) / (2.0 * BEAM_LENGTH))


def beam_modes(nodes, count=25):
    """Rigid shapes, then elastic modes: U3 of mode k is w_k, 2.4 % below record k."""
    x = np.array([n[1] for n in nodes])
    rigid = base.rigid_shapes(nodes)
    modes = [(i + 1, 0.0011 + 0.0001 * i, shape) for i, shape in enumerate(rigid)]
    for number in range(len(rigid) + 1, count + 1):
        k = number - len(rigid) - 1
        vectors = np.zeros((len(nodes), 3))
        if k < BEAM_SHAPES:
            vectors[:, 2] = beam_shape(k, x)
            modes.append((number, reg3.record_hz(k) * 0.976, vectors))
        else:
            modes.append((number, 5000.0 + 50.0 * number, base.elastic_shape(nodes, number)))
    return modes


def mac(a, b) -> float:
    a, b = np.asarray(a, dtype=float).ravel(), np.asarray(b, dtype=float).ravel()
    return float((a @ b) ** 2 / ((a @ a) * (b @ b)))


def evidence_of(**fields) -> gr.Evidence:
    values = dict(fe_unit="m", experimental_unit="m", axes=("+X", "+Y", "+Z"), measured_side="+Z", measured_dofs=("z",),
                  landmarks=(), source="marker photograph and set-up drawing")
    values.update(fields)
    return gr.Evidence(**values)


class _GeometryFlow(reg3._Flow):
    """The confirmed workflow with the evidence of one case; ``case_evidence`` is what the person states."""

    case_evidence: gr.Evidence = None
    fe_node_list = None
    fe_mode_list = None

    def nodes(self):
        return self.fe_node_list

    def modes(self):
        return self.fe_mode_list

    def state_evidence(self, dialog, panel, axes=None):
        dialog._fill(self.case_evidence)
        self.assertEqual(dialog.evidence()[0], self.case_evidence)

    def checked(self, panel):
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel)
        self.assertTrue(dialog.check())
        self.wait(panel)
        return dialog

    def service_comparison(self, panel, evidence):
        """The same steps without the dialog: propose, draft, confirmation, comparison. Returns the analysis."""
        inputs, cancel = panel.inputs, threading.Event()
        proposal = gr.propose(inputs.full_fe.dataset, inputs.full_experimental.sets[0].dataset, evidence)
        self.assertTrue(proposal.proposed, proposal.problems)
        draft = am.save_registration_draft(inputs, 0, evidence, proposal, self.root / "service draft.json", cancel)
        document = am.confirm_registration(inputs, 0, draft, "A. Tester", "notebook 7", cs.STATEMENT_KEYS,
                                           self.root / "service confirmation.json", cancel)
        return am.analyse(inputs, 0, cancel, confirmation=document)


class BeamTests(_GeometryFlow):
    def setUp(self):
        super().setUp()
        self.fe_node_list = base.beam_nodes()
        self.fe_mode_list = beam_modes(self.fe_node_list)
        self.x = np.array([n[1] for n in self.fe_node_list])

    def forward_unv(self):
        shapes = [beam_shape(k, self.x) for k in range(BEAM_SHAPES)]
        return base.write_unv(self.inputs / "beam.unv", self.fe_node_list, reg3.freqs(BEAM_SHAPES), shapes=shapes)

    def reversed_unv(self):
        """The same beam scanned from the other end, by a sensor that looks the other way: experimental point k lies at
        x_exp = 0.1 (k - 1), which is FE x = L - x_exp, and reads minus the FE U3."""
        count = len(self.fe_node_list)
        points = [(k + 1, 0.1 * k, 0.0, 0.0) for k in range(count)]
        shapes = [-beam_shape(k, BEAM_LENGTH - 0.1 * np.arange(count)) for k in range(BEAM_SHAPES)]
        return base.write_unv(self.inputs / "beam reversed.unv", points, reg3.freqs(BEAM_SHAPES), shapes=shapes)

    def assert_all_pairs(self, analysis):
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        view = analysis.comparison
        first = len(base.rigid_shapes(self.fe_node_list)) + 1
        self.assertEqual([(r.abaqus_mode, r.experimental_mode) for r in view.pair_rows],
                         [(first + k, k + 1) for k in range(BEAM_SHAPES)])
        for row in view.pair_rows:
            self.assertGreater(row.mac, 0.9999)
            self.assertAlmostEqual(row.frequency_error_percent, -2.4, places=2)
            self.assertTrue(row.cells[-1].startswith(cm.CONFIRMED_VERDICT), row.cells[-1])
        return view

    def test_forward_the_mac_matrix_is_the_analytic_one(self):
        self.case_evidence = evidence_of(landmarks=(("1", "1"), ("15", "15")))
        _window, panel = self.analysed(unv=self.forward_unv())
        self.confirmed(panel)
        view = self.assert_all_pairs(self.compare(panel))
        rows = {int(n): i for i, n in enumerate(view.mac_fe_modes)}
        first = len(base.rigid_shapes(self.fe_node_list)) + 1
        for i in range(BEAM_SHAPES):
            for j in range(BEAM_SHAPES):
                expected = mac(beam_shape(i, self.x), beam_shape(j, self.x))
                self.assertAlmostEqual(view.mac_values[rows[first + i]][j], expected, places=4)
        self.assertLess(view.mac_values[rows[first]][1], 0.01)  # the analytic off-diagonal value is 0.004

    def test_reversed_scan_and_reversed_sensor_with_the_right_statement(self):
        self.case_evidence = evidence_of(axes=("-X", "+Y", "-Z"), measured_side="-Z",
                                         landmarks=(("1", "15"), ("15", "1")))
        _window, panel = self.analysed(unv=self.reversed_unv())
        dialog, _confirming = self.confirmed(panel)
        self.assertEqual(dialog.proposal.axes_in_fe, ("-X", "+Y", "-Z"))
        self.assertEqual([p.fe_node.rpartition(":")[2] for p in dialog.proposal.mapping],
                         [str(15 - k) for k in range(15)])
        view = self.assert_all_pairs(self.compare(panel))
        self.assertEqual(view.pair_rows[0].experimental_mode, 1)  # EXP mode 1 stays EXP mode 1

    def test_reversed_scan_stated_forward_with_its_true_landmarks_is_refused(self):
        self.case_evidence = evidence_of(landmarks=(("1", "15"), ("15", "1")))
        _window, panel = self.analysed(unv=self.reversed_unv())
        dialog = self.checked(panel)
        self.assertFalse(dialog.proposal.proposed)
        self.assertIn(gr.LANDMARK, [problem.code for problem in dialog.proposal.problems])
        self.assertFalse(dialog.save_button.isEnabled())
        self.assert_frequency_only(panel)

    def test_a_wrong_orientation_that_fits_the_geometry_gives_no_confirmed_correspondence(self):
        """Negative control: the reversed scan stated forward, with landmarks that agree with that wrong statement. The
        geometry cannot tell, so the comparison runs, and the analytic MAC (at most 0.35) rejects every record."""
        evidence = evidence_of(landmarks=(("1", "1"), ("15", "15")))
        _window, panel = self.analysed(unv=self.reversed_unv())
        analysis = self.service_comparison(panel, evidence)
        self.assertIsNotNone(analysis.comparison, analysis.registration_reason)
        self.assertEqual(analysis.comparison.pair_rows, ())
        expected = max(mac(beam_shape(i, self.x), beam_shape(j, self.x[::-1]))
                       for i in range(BEAM_SHAPES) for j in range(BEAM_SHAPES))
        self.assertLess(expected, 0.5)
        shown = max(value for row in analysis.comparison.mac_values[:BEAM_SHAPES] for value in row)
        self.assertAlmostEqual(shown, expected, places=4)
        verdicts = [row[-1] for row in analysis.nearest_rows]
        self.assertEqual(len(verdicts), BEAM_SHAPES)
        self.assertTrue(all(text.startswith(cm.REJECTED_VERDICT) for text in verdicts), verdicts)

    def test_landmarks_on_the_beam_line_without_axes_leave_the_orientation_open(self):
        self.case_evidence = evidence_of(axes=("", "", "+Z"), landmarks=(("1", "1"), ("8", "8"), ("15", "15")))
        _window, panel = self.analysed(unv=self.forward_unv())
        dialog = self.checked(panel)
        self.assertEqual([problem.code for problem in dialog.proposal.problems], [gr.AMBIGUOUS])


# --------------------------------------------------------------------------------------------------------- the shell

LENGTH, MID_RADIUS, OUTSIDE_RADIUS = 120.0, 9.5, 10.0
AROUND_FE, STATIONS_FE = 24, 13
SENSOR_ANGLES = tuple(math.radians(45.0 * k) for k in range(8))
SENSOR_STATIONS = (10.0, 30.0, 60.0, 90.0, 110.0)


def uniform(z):
    return np.ones_like(np.asarray(z, dtype=float))


def one_wave(z):
    return np.cos(2.0 * np.pi * np.asarray(z, dtype=float) / LENGTH)


def half_wave(z):
    return np.cos(np.pi * np.asarray(z, dtype=float) / LENGTH)


# (circumferential order n, phase, axial function, experimental frequency in Hz); FE mode 7 + k is 2.4 % below record k
SHELL = ((1, 0.0, one_wave, 100.0), (1, -np.pi / 2, one_wave, 100.3), (2, 0.0, uniform, 225.0),
         (2, -np.pi / 2, uniform, 225.6), (3, 0.0, uniform, 500.0), (2, 0.0, half_wave, 760.0))
NO_COUNTERPART = (4, 0.0, uniform, 520.0)  # a measured shape the FE model does not have


def radial(theta) -> np.ndarray:
    theta = np.asarray(theta, dtype=float)
    return np.column_stack([np.cos(theta), np.sin(theta), np.zeros_like(theta)])


def tangent(theta) -> np.ndarray:
    theta = np.asarray(theta, dtype=float)
    return np.column_stack([-np.sin(theta), np.cos(theta), np.zeros_like(theta)])


def radial_part(shape, theta, z) -> np.ndarray:
    n, phase, axial, _hz = shape
    return np.cos(n * np.asarray(theta) + phase) * axial(z)


def shell_motion(shape, theta, z) -> np.ndarray:
    """The whole displacement (N x 3, FE axes): radial w and tangential v of an inextensional shell shape."""
    n, phase, axial, _hz = shape
    v = -np.sin(n * np.asarray(theta) + phase) * axial(z) / n
    return radial_part(shape, theta, z)[:, np.newaxis] * radial(theta) + v[:, np.newaxis] * tangent(theta)


def ring_nodes(radii=(MID_RADIUS,)):
    nodes = []
    for radius in radii:
        for station in range(STATIONS_FE):
            for j in range(AROUND_FE):
                theta = 2.0 * np.pi * j / AROUND_FE
                nodes.append((len(nodes) + 1, radius * math.cos(theta), radius * math.sin(theta), 10.0 * station))
    return nodes


def node_angles(nodes) -> tuple:
    points = np.array([n[1:] for n in nodes])
    return np.arctan2(points[:, 1], points[:, 0]), points[:, 2]


def shell_modes(nodes, count=25):
    theta, z = node_angles(nodes)
    rigid = base.rigid_shapes(nodes)
    modes = [(i + 1, 0.0011 + 0.0001 * i, shape) for i, shape in enumerate(rigid)]
    for number in range(len(rigid) + 1, count + 1):
        k = number - len(rigid) - 1
        if k < len(SHELL):
            modes.append((number, SHELL[k][3] * 0.976, shell_motion(SHELL[k], theta, z)))
        else:
            modes.append((number, 5000.0 + 50.0 * number, base.elastic_shape(nodes, number)))
    return modes


def sensors(radius=OUTSIDE_RADIUS):
    """(label, theta, z) and the points [(label, x, y, z)] in FE axes."""
    places = [(len(SENSOR_ANGLES) * s + a + 1, theta, z)
              for s, z in enumerate(SENSOR_STATIONS) for a, theta in enumerate(SENSOR_ANGLES)]
    return places, [(label, radius * math.cos(theta), radius * math.sin(theta), z) for label, theta, z in places]


def fe_label(theta: float, z: float, layer: int = 0) -> str:
    j = int(round(math.degrees(theta) / (360.0 / AROUND_FE))) % AROUND_FE
    return str(layer * AROUND_FE * STATIONS_FE + int(round(z / 10.0)) * AROUND_FE + j + 1)


def write_vector_unv(path: Path, points, frequencies, vectors) -> Path:
    """Dataset 15 + 55 with three components per point; ``vectors[k]`` is record k (N x 3, experimental axes)."""
    import pyuff

    labels = np.array([p[0] for p in points])
    count = len(labels)
    x, y, z = (np.array([p[i] for p in points]) for i in (1, 2, 3))
    uff = pyuff.UFF(str(path))
    uff.write_sets(pyuff.prepare_15(node_nums=labels, def_cs=np.zeros(count, dtype=int),
                                    disp_cs=np.zeros(count, dtype=int), color=np.ones(count, dtype=int),
                                    x=x, y=y, z=z), "add")
    for k, hz in enumerate(frequencies):
        zeta = 0.003
        w = 2 * math.pi * hz / math.sqrt(1 - zeta ** 2)
        eig = -zeta * w + 1j * w * math.sqrt(1 - zeta ** 2)
        values = np.asarray(vectors[k], dtype=complex)
        uff.write_sets(pyuff.prepare_55(id1="Fitted", id2="synthetic", id3="x", id4="x", id5="x", model_type=1,
                                        analysis_type=3, data_ch=2, spec_data_type=11, data_type=5, n_data_per_node=3,
                                        load_case=1, mode_n=k + 1, eig=eig, modal_a=1 + 0j, modal_b=1 + 0j,
                                        node_nums=labels, r1=values[:, 0], r2=values[:, 1], r3=values[:, 2],
                                        return_full_dict=True), "add")
    path.write_text(path.read_text().replace("        11         5         6", "        11         5         3"))
    return path


def direction_lines(labels, vectors) -> tuple:
    return tuple((str(label), gr.position_text(*vector)) for label, vector in zip(labels, vectors))


class _ShellFlow(_GeometryFlow):
    records = SHELL

    def setUp(self):
        super().setUp()
        self.fe_node_list = ring_nodes()
        self.fe_mode_list = shell_modes(self.fe_node_list)
        self.places, self.points = sensors()
        self.labels = [p[0] for p in self.places]
        self.theta = np.array([p[1] for p in self.places])
        self.z = np.array([p[2] for p in self.places])

    def radial_unv(self, name="tube radial.unv", records=None, points=None, frame_angle=0.0):
        """Each sensor's reading along its own radius, written as a vector in experimental axes. With ``frame_angle``
        the experimental frame is turned about the tube axis: sensor angle theta_exp lies at FE angle theta_exp + it."""
        records = records or self.records
        vectors = [radial_part(shape, self.theta + frame_angle, self.z)[:, np.newaxis] * radial(self.theta)
                   for shape in records]
        return write_vector_unv(self.inputs / name, points or self.points, [shape[3] for shape in records], vectors)

    def landmarks(self, frame_angle=0.0, layer=0):
        chosen = (0, 10, 20, 30)  # angles 0, 90, 180 and 270 degrees at four stations: not in one plane
        return tuple((str(self.labels[i]), fe_label(self.theta[i] + frame_angle, self.z[i], layer)) for i in chosen)

    def tube_evidence(self, **fields):
        values = dict(fe_unit="mm", experimental_unit="mm", measured_side=gr.AROUND, measured_dofs=("x", "y"),
                      landmarks=self.landmarks(), sensor_directions=direction_lines(self.labels, radial(self.theta)))
        values.update(fields)
        return evidence_of(**values)


class ShellWorkflowTests(_ShellFlow):
    def test_radial_sensors_all_around_give_pairs_with_the_analytic_mac(self):
        self.case_evidence = self.tube_evidence()
        _window, panel = self.analysed(unv=self.radial_unv())
        self.assertTrue(all(row[-1] == cm.INSUFFICIENT_TEXT for row in panel.analysis.nearest_rows))
        dialog, _confirming = self.confirmed(panel)
        proposal = dialog.proposal
        self.assertEqual([p.fe_node.rpartition(":")[2] for p in proposal.mapping],
                         [fe_label(t, z) for t, z in zip(self.theta, self.z)])
        self.assertTrue(all(abs(p.distance - 0.5) < 1.0e-4 for p in proposal.mapping))  # outside surface to mid-surface
        checks = " ".join(proposal.checks)
        self.assertIn("the points lie all around the part", checks)
        self.assertIn("Surface offset, measured point minus FE node along its sensor direction: median 0.5, largest 0.5 mm",
                      checks)
        self.assertIn("Sensor directions, stated for all 40 points", checks)
        self.assertTrue(any("other orientations" in text for text in proposal.warnings), proposal.warnings)
        real, seen = modal_core.compare_modal_datasets, []

        def spy(fe, experimental, **kwargs):
            seen.append(real(fe, experimental, **kwargs))
            return seen[-1]

        with mock.patch.object(modal_core, "compare_modal_datasets", side_effect=spy):
            analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        view = analysis.comparison
        self.assertEqual([(r.abaqus_mode, r.experimental_mode) for r in view.pair_rows],
                         [(7 + k, k + 1) for k in range(len(SHELL))])
        for row in view.pair_rows:
            self.assertGreater(row.mac, 0.9999)
            self.assertAlmostEqual(row.frequency_error_percent, -2.4, places=2)
            self.assertTrue(row.cells[-1].startswith(cm.CONFIRMED_VERDICT), row.cells[-1])
        # every cell of the matrix is the MAC of the two radial readings, computed here from the closed forms
        rows = {int(n): i for i, n in enumerate(view.mac_fe_modes)}
        for i, fe_shape in enumerate(SHELL):
            for j, record in enumerate(SHELL):
                expected = mac(radial_part(fe_shape, self.theta, self.z), radial_part(record, self.theta, self.z))
                self.assertAlmostEqual(view.mac_values[rows[7 + i]][j], expected, places=4)
        # the components along the experimental axes, which the comparator sees without the projection, give 0.5 for
        # the bending shape: sum(cos^2) / 8 over eight sensors
        self.assertEqual(len(seen), 2)
        first = np.asarray(seen[0].mac_matrix)[list(seen[0].abaqus_mode_numbers).index(7), 0]
        self.assertAlmostEqual(float(first), 0.5, places=4)
        self.assertIn(cm.PROJECTION_NOTE, view.warnings)
        self.assertIn(("Measured directions", cm.PROJECTION_NOTE), view.provenance)
        self.assertIn(("Orientation source", f"frozen_registration. {cm.PROJECTION_NOTE}"), view.provenance)
        self.assertTrue(any("FE modes 7 / 8" in text or "FE 7 / 8" in text for text in view.close_groups),
                        view.close_groups)  # the bending doublet is a close group and keeps its two pairs
        # the page: every record has its verdict, EXP1 first
        nearest = panel.tables["nearest"]
        self.assertEqual(nearest.horizontalHeaderItem(nearest.columnCount() - 1).text(), "Verdict")
        self.assertEqual(nearest.item(0, 0).text(), "EXP1")
        self.assertTrue(nearest.item(0, nearest.columnCount() - 1).text().startswith(cm.CONFIRMED_VERDICT))
        pairs = panel.tables["pairs"]
        self.assertEqual(pairs.horizontalHeaderItem(pairs.columnCount() - 1).text(), "Verdict")
        self.assertEqual(pairs.rowCount(), len(SHELL))

    def test_the_read_fe_data_are_not_changed_by_the_projection(self):
        self.case_evidence = self.tube_evidence()
        _window, panel = self.analysed(unv=self.radial_unv())
        before = [np.array(mode.vectors) for mode in panel.inputs.full_fe.dataset.modes]
        self.confirmed(panel)
        self.compare(panel)
        for mode, kept in zip(panel.inputs.full_fe.dataset.modes, before):
            self.assertTrue(np.array_equal(np.asarray(mode.vectors), kept))

    def test_a_draft_with_directions_is_reproduced_and_an_altered_one_is_not(self):
        import json

        self.case_evidence = self.tube_evidence()
        _window, panel = self.analysed(unv=self.radial_unv())
        self.draft(panel)
        document = json.loads(self.draft_path.read_text(encoding="utf-8"))
        self.assertEqual(len(document["evidence"]["sensor_directions"]), 40)
        again = am.open_registration_draft(panel.inputs, 0, self.draft_path, threading.Event())
        self.assertTrue(again.proposal.proposed, again.proposal.problems)
        self.assertEqual(again.evidence, self.case_evidence)
        document["evidence"]["sensor_directions"][0][1] = "(0.0, 1.0, 0.0)"
        self.draft_path.write_text(json.dumps(document), encoding="utf-8")
        altered = am.open_registration_draft(panel.inputs, 0, self.draft_path, threading.Event())
        self.assertEqual([problem.code for problem in altered.proposal.problems], [gr.DRAFT_TAMPERED])

    def test_a_frame_turned_about_the_tube_axis_is_resolved_by_the_landmarks(self):
        angle = math.radians(30.0)
        turn = np.array([[math.cos(angle), math.sin(angle), 0.0], [-math.sin(angle), math.cos(angle), 0.0], [0, 0, 1.0]])
        fe_points = np.array([[OUTSIDE_RADIUS * math.cos(t + angle), OUTSIDE_RADIUS * math.sin(t + angle), z]
                              for t, z in zip(self.theta, self.z)])
        moved = fe_points @ turn.T + np.array([3.0, -2.0, 5.0])  # experimental axes: turned by -30 degrees and shifted
        points = [(label, *row) for label, row in zip(self.labels, moved.tolist())]
        # each landmark is the place of the sensor on the outside surface, as an FE position: FE nodes of the
        # mid-surface, 0.5 mm below the sensors, would tilt the fitted rotation by that offset
        places = tuple((str(self.labels[i]), gr.position_text(*fe_points[i])) for i in (0, 10, 20, 30))
        self.case_evidence = self.tube_evidence(axes=("", "", ""), landmarks=places)
        _window, panel = self.analysed(unv=self.radial_unv(points=points, frame_angle=angle))
        dialog, _confirming = self.confirmed(panel)
        self.assertIn("30.000 degrees about FE +Z", " ".join(dialog.proposal.details))
        self.assertEqual([p.fe_node.rpartition(":")[2] for p in dialog.proposal.mapping],
                         [fe_label(t + angle, z) for t, z in zip(self.theta, self.z)])
        analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        self.assertEqual([(r.abaqus_mode, r.experimental_mode) for r in analysis.comparison.pair_rows],
                         [(7 + k, k + 1) for k in range(len(SHELL))])
        self.assertTrue(all(r.mac > 0.9999 for r in analysis.comparison.pair_rows))

    def test_a_measured_shape_without_an_fe_counterpart_is_rejected_and_the_others_stay(self):
        self.records = SHELL[:5] + (NO_COUNTERPART,) + SHELL[5:]
        _window, panel = self.analysed(unv=self.radial_unv())
        analysis = self.service_comparison(panel, self.tube_evidence())
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        verdicts = {row[0]: row[-1] for row in analysis.nearest_rows}
        self.assertTrue(verdicts["EXP6"].startswith(cm.REJECTED_VERDICT), verdicts["EXP6"])
        for name in ("EXP1", "EXP2", "EXP3", "EXP4", "EXP5", "EXP7"):
            self.assertTrue(verdicts[name].startswith(cm.CONFIRMED_VERDICT), verdicts[name])
        self.assertEqual(len(analysis.comparison.pair_rows), len(SHELL))
        self.assertTrue(any(row[0] == "6" for row in analysis.comparison.unmatched_experimental_rows)
                        or any("mode 6" in text for text in analysis.comparison.unpaired_experimental))
        self.assertTrue(analysis.comparison.unmatched_fe_rows)  # the FE modes above the measured band have no pair

    def test_three_component_sensors_all_around_need_no_direction(self):
        """The whole motion measured at each point (three components): components are compared, nothing is projected."""
        measured = SHELL[2:]  # every one of these shapes moves along x and along y
        vectors = [shell_motion(shape, self.theta, self.z) for shape in measured]
        unv = write_vector_unv(self.inputs / "tube triaxial.unv", self.points, [s[3] for s in measured], vectors)
        _window, panel = self.analysed(unv=unv)
        real, seen = modal_core.compare_modal_datasets, []

        def spy(fe, experimental, **kwargs):
            seen.append(real(fe, experimental, **kwargs))
            return seen[-1]

        with mock.patch.object(modal_core, "compare_modal_datasets", side_effect=spy):
            analysis = self.service_comparison(panel, self.tube_evidence(sensor_directions=()))
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        self.assertEqual(len(seen), 1)
        self.assertEqual([(r.abaqus_mode, r.experimental_mode) for r in analysis.comparison.pair_rows],
                         [(9 + k, k + 1) for k in range(len(measured))])
        self.assertTrue(all(r.mac > 0.9999 for r in analysis.comparison.pair_rows))
        self.assertNotIn(cm.PROJECTION_NOTE, analysis.comparison.warnings)


class ShellRefusalTests(_ShellFlow):
    def refused(self, panel, evidence, code):
        analysis = self.service_comparison(panel, evidence)
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(analysis.comparison)
        self.assertIn(code, analysis.registration_reason)
        self.assertTrue(all(row[-1] == cm.INSUFFICIENT_TEXT for row in analysis.nearest_rows))
        return analysis

    def test_radial_data_without_stated_directions_get_no_mac(self):
        _window, panel = self.analysed(unv=self.radial_unv())
        self.refused(panel, self.tube_evidence(sensor_directions=()), cm.DIRECTION_REQUIRED)

    def test_the_dialog_says_so_before_a_draft_can_be_saved(self):
        self.case_evidence = self.tube_evidence(sensor_directions=())
        _window, panel = self.analysed(unv=self.radial_unv())
        dialog = self.checked(panel)
        self.assertFalse(dialog.proposal.proposed)
        self.assertEqual([problem.code for problem in dialog.proposal.problems], [gr.DIRECTION])
        self.assertIn(cm.DIRECTION_REQUIRED, dialog.problem_label.text())
        self.assertIsNone(dialog.review_box)
        self.assertFalse(dialog.save_button.isEnabled())
        self.assert_frequency_only(panel)

    def test_stated_directions_the_file_contradicts_get_no_mac(self):
        _window, panel = self.analysed(unv=self.radial_unv())
        wrong = direction_lines(self.labels, tangent(self.theta))
        analysis = self.refused(panel, self.tube_evidence(sensor_directions=wrong), cm.DIRECTION_CONTRADICTED)
        self.assertIn("90.0 degrees", analysis.registration_reason)

    def test_directions_stated_for_three_component_data_get_no_mac(self):
        vectors = [shell_motion(shape, self.theta, self.z) for shape in SHELL[2:]]
        unv = write_vector_unv(self.inputs / "tube triaxial.unv", self.points, [s[3] for s in SHELL[2:]], vectors)
        _window, panel = self.analysed(unv=unv)
        self.refused(panel, self.tube_evidence(), cm.DIRECTION_CONTRADICTED)

    def propose(self, panel, evidence):
        inputs = panel.inputs
        return gr.propose(inputs.full_fe.dataset, inputs.full_experimental.sets[0].dataset, evidence)

    def test_readings_stored_in_one_column_without_their_direction_are_refused(self):
        vectors = [np.column_stack([np.zeros(40), np.zeros(40), radial_part(s, self.theta, self.z)]) for s in SHELL]
        unv = write_vector_unv(self.inputs / "tube scalar.unv", self.points, [s[3] for s in SHELL], vectors)
        _window, panel = self.analysed(unv=unv)
        proposal = self.propose(panel, self.tube_evidence())
        self.assertFalse(proposal.proposed)
        self.assertIn(gr.DOF, [problem.code for problem in proposal.problems])

    def test_incomplete_or_unreadable_directions_are_refused(self):
        _window, panel = self.analysed(unv=self.radial_unv())
        every = direction_lines(self.labels, radial(self.theta))
        for stated, words in ((every[:-1], "every point or for none"), (every[:-1] + (("40", "(0.0, 0.0, 0.0)"),), "is not a direction"),
                              (every + (every[0],), "stated twice"), (every[:-1] + (("99", every[-1][1]),), "is not in"),
                              (direction_lines(self.labels, np.tile([0.0, 0.6, 0.8], (40, 1))), "not stated as a measured DOF")):
            with self.subTest(words=words):
                proposal = self.propose(panel, self.tube_evidence(sensor_directions=stated))
                self.assertFalse(proposal.proposed)
                self.assertEqual([problem.code for problem in proposal.problems], [gr.DIRECTION])
                self.assertIn(words, proposal.problems[0].text)
                self.assertEqual(proposal.mapping, ())

    def test_a_single_face_cannot_hold_points_all_around(self):
        _window, panel = self.analysed(unv=self.radial_unv())
        proposal = self.propose(panel, self.tube_evidence(measured_side="+X"))
        self.assertFalse(proposal.proposed)
        self.assertTrue({gr.SIDE, gr.MAPPING} & {problem.code for problem in proposal.problems}, proposal.problems)

    def test_landmarks_on_one_generator_leave_the_rotation_about_the_axis_open(self):
        _window, panel = self.analysed(unv=self.radial_unv())
        line = tuple((str(self.labels[i]), fe_label(self.theta[i], self.z[i])) for i in (0, 8, 16, 24, 32))
        proposal = self.propose(panel, self.tube_evidence(axes=("", "", "+Z"), landmarks=line))
        self.assertEqual([problem.code for problem in proposal.problems], [gr.AMBIGUOUS])

    def test_landmarks_turned_against_the_stated_axes_are_refused(self):
        _window, panel = self.analysed(unv=self.radial_unv())
        proposal = self.propose(panel, self.tube_evidence(landmarks=self.landmarks(frame_angle=math.radians(45.0))))
        self.assertEqual([problem.code for problem in proposal.problems], [gr.LANDMARK])

    def test_a_wrong_angular_position_that_fits_the_geometry_confirms_no_bending_record(self):
        """Negative control: every landmark stated 45 degrees round the tube and no axis stated. The tube's geometry
        accepts it, the comparison runs, and the bending records, whose analytic MAC is then 0.5 with both FE bending
        modes, are not a confirmed correspondence."""
        _window, panel = self.analysed(unv=self.radial_unv())
        evidence = self.tube_evidence(axes=("", "", ""), landmarks=self.landmarks(frame_angle=math.radians(45.0)))
        analysis = self.service_comparison(panel, evidence)
        self.assertIsNotNone(analysis.comparison, analysis.registration_reason)
        turned = self.theta + math.radians(45.0)
        stated = radial(turned)  # what the wrong statement compares each sensor with
        for fe_shape in SHELL[:2]:
            value = mac(np.einsum("ij,ij->i", shell_motion(fe_shape, turned, self.z), stated),
                        radial_part(SHELL[0], self.theta, self.z))
            self.assertAlmostEqual(value, 0.5, places=6)
        verdicts = {row[0]: row[-1] for row in analysis.nearest_rows}
        for name in ("EXP1", "EXP2"):
            self.assertFalse(verdicts[name].startswith(cm.CONFIRMED_VERDICT), verdicts[name])


class SurfaceOffsetTests(_ShellFlow):
    """A wall of two FE node layers (radius 9 and 10 mm)."""

    def setUp(self):
        super().setUp()
        self.fe_node_list = ring_nodes((9.0, 10.0))
        self.fe_mode_list = shell_modes(self.fe_node_list)

    def proposal(self, radius):
        _places, points = sensors(radius)
        _window, panel = self.analysed(unv=self.radial_unv(points=points))
        evidence = self.tube_evidence(landmarks=self.landmarks(layer=1))
        return gr.propose(panel.inputs.full_fe.dataset, panel.inputs.full_experimental.sets[0].dataset, evidence)

    def test_points_between_the_two_layers_do_not_say_which_surface_was_measured(self):
        proposal = self.proposal(9.5)
        self.assertFalse(proposal.proposed)
        self.assertEqual([problem.code for problem in proposal.problems], [gr.SURFACE])
        self.assertIn("36 points lie equally near two FE nodes that follow one another along the sensor direction",
                      proposal.problems[0].text)  # the four landmarks keep their stated nodes

    def test_points_on_the_outside_surface_take_the_outside_nodes(self):
        proposal = self.proposal(10.0)
        self.assertTrue(proposal.proposed, proposal.problems)
        self.assertEqual([p.fe_node.rpartition(":")[2] for p in proposal.mapping],
                         [fe_label(t, z, 1) for t, z in zip(self.theta, self.z)])
        self.assertTrue(all(p.distance < 1.0e-4 for p in proposal.mapping))


# ------------------------------------------------------------------------------------------- what must not have moved

class CompatibilityTests(reg3._Flow):
    def test_a_flat_plate_is_compared_once_and_its_draft_holds_no_new_field(self):
        import hashlib
        import json
        from dataclasses import asdict

        _window, panel = self.analysed()
        dialog, _confirming = self.confirmed(panel)
        evidence = dialog.checked_evidence
        self.assertEqual(evidence.sensor_directions, ())
        legacy = asdict(evidence)
        del legacy["sensor_directions"]
        self.assertEqual(evidence.evidence_hash,
                         hashlib.sha256(json.dumps(legacy, sort_keys=True, default=str).encode("utf-8")).hexdigest())
        self.assertNotIn("sensor_directions", json.loads(self.draft_path.read_text(encoding="utf-8"))["evidence"])
        with mock.patch.object(modal_core, "compare_modal_datasets", wraps=modal_core.compare_modal_datasets) as spy:
            analysis = self.compare(panel)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON)
        self.assertNotIn(cm.PROJECTION_NOTE, analysis.comparison.warnings)
        self.assertTrue(all(row.mac > 0.999 for row in analysis.comparison.pair_rows))
        self.assertTrue(all(row[-1].startswith(cm.CONFIRMED_VERDICT) for row in analysis.nearest_rows))


class DialogTextTests(unittest.TestCase):
    def test_direction_lines_are_read_like_landmarks(self):
        pairs, bad = rd.parse_directions("1, 1, 0, 0\n2; 0.6; 0.8; 0\n\n3 0 0 1\nfour\n5, a, b, c")
        self.assertEqual(pairs, (("1", "(1.0, 0.0, 0.0)"), ("2", "(0.6, 0.8, 0.0)"), ("3", "(0.0, 0.0, 1.0)")))
        self.assertEqual(bad, ("four", "5, a, b, c"))


if __name__ == "__main__":
    unittest.main()
