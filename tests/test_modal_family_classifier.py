"""M4.3 physical modal-family classifier and family holdouts (SPEC §12.2–12.3; D-010), synthetic shapes."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.modal_family_classifier import (
    PROVISIONAL_FAMILY_CLASSIFIER as POLICY,
    ClassifiedRow,
    FamilyClassificationError,
    Parity,
    classify_surface_mode,
    select_holdouts,
)


def plate(lx=500.0, ly=520.0, n=31, jitter=0.0, seed=0):
    xs, ys = np.linspace(0.0, lx, n), np.linspace(0.0, ly, n)
    points = np.array([(x, y) for x in xs for y in ys])
    if jitter:
        points = points + np.random.default_rng(seed).normal(0.0, jitter, points.shape)
    u = (points[:, 0] - lx / 2) / (lx / 2)
    v = (points[:, 1] - ly / 2) / (ly / 2)
    return points, u, v


class ParityTests(unittest.TestCase):
    def test_plate_families(self):
        points, u, v = plate()
        cases = {
            "torsion": (u * v, Parity.ODD, Parity.ODD, 1, 1),
            "bending_x": (u ** 2 - 1 / 3, Parity.EVEN, Parity.EVEN, 2, 0),
            "bending_y": (v ** 2 - 1 / 3, Parity.EVEN, Parity.EVEN, 0, 2),
            "odd_x": (u, Parity.ODD, Parity.EVEN, 1, 0),
            "even_x_odd_y": (v * (u ** 2 - 1 / 3), Parity.EVEN, Parity.ODD, 2, 1),
        }
        for name, (shape, px, py, nx, ny) in cases.items():
            with self.subTest(name=name):
                family = classify_surface_mode(points, shape)
                self.assertEqual((family.parity_x, family.parity_y), (px, py))
                self.assertEqual((family.nodal_lines_x, family.nodal_lines_y), (nx, ny))
        self.assertTrue(classify_surface_mode(points, u * v).torsion_dominated)
        self.assertFalse(classify_surface_mode(points, u).torsion_dominated)

    def test_continuous_scores_and_mixed_shapes(self):
        points, u, v = plate()
        torsion = classify_surface_mode(points, u * v)
        self.assertAlmostEqual(torsion.p_x, -1.0, places=6)
        self.assertAlmostEqual(torsion.p_y, -1.0, places=6)
        mixed = classify_surface_mode(points, u + 1.2 * (v ** 2 - 1 / 3))
        self.assertIs(mixed.parity_x, Parity.MIXED)
        self.assertTrue(-POLICY.parity_threshold < mixed.p_x < POLICY.parity_threshold)

    def test_independent_of_node_order_and_mild_mesh_irregularity(self):
        points, u, v = plate()
        order = np.random.default_rng(1).permutation(len(points))
        first = classify_surface_mode(points, u * v)
        shuffled = classify_surface_mode(points[order], (u * v)[order])
        # The classification is identical; the scores agree to round-off (summation order differs).
        self.assertEqual((first.key, first.parity_x, first.parity_y), (shuffled.key, shuffled.parity_x,
                                                                       shuffled.parity_y))
        for name in ("p_x", "p_y", "p_diagonal", "p_antidiagonal"):
            self.assertAlmostEqual(getattr(first, name), getattr(shuffled, name), places=12)
        jittered, ju, jv = plate(jitter=0.5)
        self.assertEqual(classify_surface_mode(jittered, ju * jv).key, first.key)

    def test_diagonal_parity_only_for_near_square_panels(self):
        points, u, v = plate(lx=500.0, ly=510.0)
        family = classify_surface_mode(points, u ** 2 - v ** 2)
        self.assertAlmostEqual(family.p_diagonal, -1.0, places=6)
        self.assertAlmostEqual(family.p_antidiagonal, -1.0, places=6)
        self.assertAlmostEqual(classify_surface_mode(points, u * v).p_diagonal, 1.0, places=6)
        rectangle, ru, rv = plate(lx=500.0, ly=750.0)
        self.assertIsNone(classify_surface_mode(rectangle, ru * rv).p_diagonal)

    def test_unsymmetric_mesh_is_refused(self):
        points, u, v = plate()
        keep = ~((u > 0.0) & (v > 0.2))  # remove a corner region: many nodes lose their mirror
        with self.assertRaises(FamilyClassificationError):
            classify_surface_mode(points[keep], (u * v)[keep])

    def test_input_validation(self):
        points, u, v = plate(n=5)
        for args in ((points[:, :1], u), (points, u[:-1]), (points, np.zeros_like(u)), (points[:4], u[:4])):
            with self.subTest(shape=args[0].shape), self.assertRaises(FamilyClassificationError):
                classify_surface_mode(*args)

    def test_policy_hash_is_recorded(self):
        points, u, v = plate()
        self.assertEqual(classify_surface_mode(points, u * v).policy_hash, POLICY.policy_hash)


class HoldoutTests(unittest.TestCase):
    def setUp(self):
        points, u, v = plate()
        family = lambda shape: classify_surface_mode(points, shape)  # noqa: E731
        self.torsion = family(u * v)
        self.bending = family(u ** 2 - 1 / 3)
        self.odd_x = family(u)
        self.mixed = family(v * (u ** 2 - 1 / 3))

    def test_default_sandwich_holdouts_by_family(self):
        rows = [ClassifiedRow("R3", 90.0, self.bending), ClassifiedRow("R1", 30.0, self.torsion),
                ClassifiedRow("R2", 75.0, self.odd_x), ClassifiedRow("R4", 140.0, self.mixed),
                ClassifiedRow("R5", 95.0, self.bending)]
        selection = select_holdouts(rows, k_int_enabled=False)
        self.assertEqual(selection.torsion_family, self.torsion.key)
        self.assertEqual(selection.validation_family, self.mixed.key)
        self.assertEqual(set(selection.holdout_row_ids), {"R1", "R4"})
        self.assertEqual(set(selection.fit_row_ids), {"R2", "R3", "R5"})

    def test_whole_family_is_held_out_and_order_is_by_frequency(self):
        rows = [ClassifiedRow("R9", 300.0, self.bending), ClassifiedRow("R1", 30.0, self.torsion),
                ClassifiedRow("R2", 120.0, self.bending), ClassifiedRow("R5", 60.0, self.torsion)]
        selection = select_holdouts(rows, k_int_enabled=False)
        self.assertEqual(set(selection.holdout_row_ids), {"R1", "R5", "R2", "R9"})
        self.assertEqual(selection.fit_row_ids, ())

    def test_k_int_and_missing_torsion_family(self):
        rows = [ClassifiedRow("R1", 30.0, self.torsion), ClassifiedRow("R2", 75.0, self.odd_x),
                ClassifiedRow("R3", 90.0, self.bending)]
        selection = select_holdouts(rows, k_int_enabled=True)
        self.assertIsNone(selection.torsion_family)
        self.assertEqual(selection.holdout_row_ids, ("R3",))
        no_torsion = select_holdouts(rows[1:], k_int_enabled=False)
        self.assertIsNone(no_torsion.torsion_family)
        self.assertIn("no torsion-dominated", no_torsion.notes[0])

    def test_duplicate_rows_are_refused(self):
        with self.assertRaises(ValueError):
            select_holdouts([ClassifiedRow("R1", 30.0, self.torsion), ClassifiedRow("R1", 40.0, self.bending)], False)


if __name__ == "__main__":
    unittest.main()
