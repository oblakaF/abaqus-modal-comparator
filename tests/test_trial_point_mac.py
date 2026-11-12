"""ABM-PLATE-POINT-MAC-GUI-1: the exploratory trial service. Synthetic plates only; no file, no Qt, no Abaqus."""

from __future__ import annotations

from pathlib import Path
import sys
import threading
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModeShape  # noqa: E402
from services import trial_point_mac as tp  # noqa: E402

LX, LY, THICK, MESH = 60.0, 48.0, 1.0, 3.0  # FE plate, millimetres; no measured point falls midway between two nodes
GRID, PITCH, THETA = 5, 0.008, 30.0  # measured grid: 5 x 5, metres, turned in the scan plane
ORDERS = ((2, 0), (0, 2), (1, 1), (2, 1), (1, 2), (3, 0), (0, 3), (2, 2), (3, 1), (1, 3), (4, 0), (0, 4), (3, 2), (2, 3),
          (4, 1), (1, 4), (3, 3), (4, 2), (2, 4))
FACTOR = 0.8 + 0.6j


def fe_nodes():
    """(label, x, y, z): a structured mesh on the faces z = 0 and z = THICK."""
    nodes, label = [], 1
    for z in (0.0, THICK):
        for i in range(int(LX / MESH) + 1):
            for j in range(int(LY / MESH) + 1):
                nodes.append((label, MESH * i, MESH * j, z))
                label += 1
    return nodes


def field(k: int, x, y, parity: bool = True):
    """Out-of-plane shape k at FE (x, y): of definite parity about the plate centre, or of none."""
    p, q = ORDERS[k]
    value = np.cos(p * np.pi * np.asarray(x) / LX) * np.cos(q * np.pi * np.asarray(y) / LY)
    return value if parity else value + 0.5 * np.sin(0.7 * np.asarray(x) / LX + 0.3 * k) * np.cos(1.3 * np.asarray(y) / LY)


def grid_ab():
    """The grid's own coordinates (a, b) in millimetres, centred, in the order of the points."""
    half = (GRID - 1) / 2.0
    return np.array([((i - half) * PITCH * 1000.0, (j - half) * PITCH * 1000.0) for i in range(GRID) for j in range(GRID)])


def experimental_nodes():
    """(label, x, y, z) in metres: the grid turned by THETA and moved anywhere in the scan frame."""
    c, s = np.cos(np.radians(THETA)), np.sin(np.radians(THETA))
    ab = grid_ab() / 1000.0
    return [(100 + n, 0.4 + c * a - s * b, -0.2 + s * a + c * b, -1.15) for n, (a, b) in enumerate(ab)]


def truth_xy(name: str = "T1"):
    """Where the points are on the plate under one centred placement, written out by hand."""
    a, b = grid_ab().T
    x, y = {"T0": (a, b), "T1": (-b, a), "T2": (-a, -b), "T3": (b, -a),
            "B0": (a, -b), "B1": (b, a), "B2": (-a, b), "B3": (-b, -a)}[name]
    return LX / 2.0 + x, LY / 2.0 + y


def fe_modes(count: int = 14, parity: bool = True):
    nodes = fe_nodes()
    ids = [n[0] for n in nodes]
    xyz = np.array([n[1:] for n in nodes])
    modes = []
    for k in range(count):
        vectors = np.zeros((len(nodes), 3))
        vectors[:, 2] = field(k, xyz[:, 0], xyz[:, 1], parity)
        modes.append(ModeShape(7 + k, 20.0 * (k + 1), ids, xyz, vectors))
    return modes


def experimental_shapes(count: int = 4, truth: str = "T1", parity: bool = True):
    x, y = truth_xy(truth)
    return [FACTOR * field(k, x, y, parity) for k in range(count)]


def experimental_modes(count: int = 4, truth: str = "T1", parity: bool = True, nodes=None):
    nodes = nodes or experimental_nodes()
    ids = [n[0] for n in nodes]
    xyz = np.array([n[1:] for n in nodes])
    modes = []
    for k, shape in enumerate(experimental_shapes(count, truth, parity)):
        vectors = np.zeros((len(nodes), 3), dtype=complex)
        vectors[:, 2] = shape[:len(nodes)]
        modes.append(ModeShape(k + 1, 21.0 * (k + 1), ids, xyz, vectors))
    return modes


class HypothesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fe, cls.experimental = fe_modes(), experimental_modes()
        cls.run_ = tp.run_trials(cls.fe, cls.experimental)

    def test_the_forty_fixed_hypotheses_in_their_fixed_order(self):
        names = [f"{face}{turn}_{shift}" for face in "TB" for turn in range(4) for shift in ("C", "X+5", "X-5", "Y+5", "Y-5")]
        self.assertEqual([t.name for t in self.run_.trials], names)
        self.assertEqual(self.run_.label, "EXPLORATORY MAC — UNCONFIRMED GEOMETRIC MAPPING")

    def test_every_transform_is_a_proper_rotation_and_no_point_is_dropped(self):
        for trial in self.run_.trials:
            self.assertAlmostEqual(trial.determinant, 1.0, places=12)
            self.assertTrue(trial.usable, trial.rejected_because)
            self.assertEqual((trial.points, trial.valid_points, trial.unique_nodes, len(trial.node_ids)), (25, 25, 25, 25))
            self.assertEqual(trial.mac.shape, (4, 14))
            self.assertLessEqual(trial.max_distance, self.run_.half_mesh_diagonal * (1 + 1e-6))
        self.assertEqual(self.run_.point_ids, tuple(str(n[0]) for n in experimental_nodes()))

    def test_each_centred_placement_is_where_it_is_said_to_be(self):
        for name in ("T0", "T1", "T2", "T3", "B0", "B1", "B2", "B3"):
            x, y = truth_xy(name)
            placed = self.run_.trial(f"{name}_C").placed
            np.testing.assert_allclose(placed, np.column_stack([x, y]), atol=1e-9, err_msg=name)

    def test_a_shift_moves_the_centred_placement_by_five_fe_units(self):
        centred = self.run_.trial("B3_C").placed
        for shift, move in (("X+5", (5, 0)), ("X-5", (-5, 0)), ("Y+5", (0, 5)), ("Y-5", (0, -5))):
            np.testing.assert_allclose(self.run_.trial(f"B3_{shift}").placed, centred + np.array(move), atol=1e-12)

    def test_each_point_takes_the_nearest_node_of_the_assumed_face(self):
        nodes = np.array([n[1:] for n in fe_nodes()])
        labels = [str(n[0]) for n in fe_nodes()]
        for name, z in (("T1_C", THICK), ("B2_X+5", 0.0)):
            trial = self.run_.trial(name)
            face = np.where(nodes[:, 2] == z)[0]
            for point, node in zip(trial.placed, trial.node_ids):
                nearest = face[np.argmin(np.hypot(*(nodes[face, :2] - point).T))]
                self.assertEqual(node, labels[nearest])

    def test_the_mac_is_the_complex_mac_of_measured_z_against_fe_u3_at_the_mapped_nodes(self):
        trial = self.run_.trial("T1_C")
        labels = [str(n[0]) for n in fe_nodes()]
        rows = [labels.index(node) for node in trial.node_ids]
        for i, measured in enumerate(self.experimental):
            e = np.asarray(measured.vectors)[:, 2]
            for j, mode in enumerate(self.fe):
                f = np.asarray(mode.vectors)[rows, 2]
                direct = abs(np.vdot(f, e)) ** 2 / (np.vdot(f, f).real * np.vdot(e, e).real)
                self.assertAlmostEqual(trial.mac[i, j], direct, places=12)
        self.assertTrue(np.iscomplexobj(self.run_.experimental_z))
        for k in range(4):  # the shapes were made at this placement: nearest-node error only
            self.assertGreater(trial.mac[k, k], 0.9)

    def test_the_lower_face_takes_fe_displacement_along_scan_z(self):
        labels = [str(n[0]) for n in fe_nodes()]
        trial = self.run_.trial("B0_C")
        rows = [labels.index(node) for node in trial.node_ids]
        np.testing.assert_array_equal(trial.fe_at[:, 0], -np.asarray(self.fe[0].vectors)[rows, 2])

    def test_equal_matrices_are_grouped_in_the_fixed_order_and_nothing_is_ranked(self):
        self.assertEqual(self.run_.families, (("T0_C", "T2_C", "B0_C", "B2_C"), ("T1_C", "T3_C", "B1_C", "B3_C")))
        first, second = (self.run_.trial(f[0]).mac for f in self.run_.families)
        self.assertGreater(float(np.abs(first - second).max()), 0.1)
        for name in ("best", "preferred", "selected", "rank", "score", "recommended"):
            self.assertFalse(hasattr(self.run_, name), name)
            self.assertFalse(hasattr(self.run_.trials[0], name), name)

    def test_shapes_of_no_symmetry_give_no_merged_family(self):
        run = tp.run_trials(fe_modes(parity=False), experimental_modes(parity=False))
        self.assertEqual(run.families, tuple((f"{face}{turn}_C",) for face in "TB" for turn in range(4)))

    def test_the_data_are_not_changed_and_read_only_arrays_are_accepted(self):
        fe, experimental = fe_modes(), experimental_modes()
        before = [(m.coordinates.copy(), m.vectors.copy()) for m in fe + experimental]
        for mode in fe + experimental:
            mode.coordinates.flags.writeable = False
            mode.vectors.flags.writeable = False
        run = tp.run_trials(fe, experimental)
        for mode, (coordinates, vectors) in zip(fe + experimental, before):
            np.testing.assert_array_equal(mode.coordinates, coordinates)
            np.testing.assert_array_equal(mode.vectors, vectors)
        np.testing.assert_array_equal(run.trial("T1_C").mac, self.run_.trial("T1_C").mac)


class RejectionTests(unittest.TestCase):
    def test_a_placement_that_cannot_map_every_point_is_rejected_whole_with_its_reason(self):
        run = tp.run_trials(fe_modes(), experimental_modes(), scale=1600.0)  # the grid is 51.2 units: wider than the 48 side
        rejected = [t for t in run.trials if not t.usable]
        self.assertTrue(rejected)
        for trial in rejected:
            self.assertIsNone(trial.mac)
            self.assertIn("outside the FE outline", trial.rejected_because)
            self.assertEqual(trial.points, 25)
        self.assertTrue(all(t.rejected_because == "" for t in run.usable))

    def test_points_on_a_shared_node_reject_the_placement(self):
        run = tp.run_trials(fe_modes(), experimental_modes(), scale=250.0)  # pitch 2: finer than the mesh
        self.assertEqual(len(run.usable), 0)
        self.assertIn("share an FE node", run.trials[0].rejected_because)
        self.assertEqual(run.families, ())

    def test_another_measured_component_is_refused(self):
        experimental = experimental_modes()
        experimental[1].vectors[:, 0] = 1.0
        with self.assertRaisesRegex(tp.TrialUnavailable, "Z component alone"):
            tp.run_trials(fe_modes(), experimental)

    def test_points_that_are_not_a_full_grid_are_refused(self):
        with self.assertRaisesRegex(tp.TrialUnavailable, "regular rectangular grid"):
            tp.run_trials(fe_modes(), experimental_modes(nodes=experimental_nodes()[:-1]))

    def test_modes_on_different_points_are_refused(self):
        experimental = experimental_modes()
        experimental[2].coordinates = experimental[2].coordinates + 1.0e-3
        with self.assertRaisesRegex(tp.TrialUnavailable, "same points"):
            tp.run_trials(fe_modes(), experimental)

    def test_no_modes_are_refused(self):
        with self.assertRaises(tp.TrialUnavailable):
            tp.run_trials([], experimental_modes())


class CancellationTests(unittest.TestCase):
    def test_a_set_event_stops_before_any_value(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(tp.TrialCancelled):
            tp.run_trials(fe_modes(), experimental_modes(), event)

    def test_cancelling_between_hypotheses_returns_nothing(self):
        event, seen = threading.Event(), []

        def progress(text):
            seen.append(text)
            if len(seen) == 7:
                event.set()

        with self.assertRaises(tp.TrialCancelled):
            tp.run_trials(fe_modes(), experimental_modes(), event, progress)
        self.assertEqual(len(seen), 7)


class SourceGuards(unittest.TestCase):
    def test_the_service_starts_nothing_writes_nothing_and_chooses_nothing(self):
        text = (ROOT / "src" / "services" / "trial_point_mac.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "abaqus", "install_", "open(", "write_", "argmax", "argsort", "sorted(", "research/",
                          "ABM_PLATE_POINT_MAC_1", "registration_", "confirmed_registration"):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertIn("modal_assurance_criterion", text)


if __name__ == "__main__":
    unittest.main()
