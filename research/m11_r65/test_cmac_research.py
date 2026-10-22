"""Synthetic tests of the M11 R6.5 research code (no real data).

Run: python -m unittest discover -s research/m11_r65 -v
"""
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmac_research as R  # noqa: E402


def grid(nx, ny, w=R.PLATE_MM[0], h=R.PLATE_MM[1]):
    xs, ys = np.linspace(0, w, nx), np.linspace(0, h, ny)
    xy = np.array([(x, y) for y in ys for x in xs])
    el = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            n1 = j * nx + i
            el.append([n1, n1 + 1, n1 + nx + 1, n1 + nx])  # counter-clockwise, as S4R 1-2-103-102
    return xy, np.array(el)


class CMAC(unittest.TestCase):
    def test_identical_and_orthogonal(self):
        e = np.array([1 + 1j, 2 - 1j, 0.5j])
        self.assertAlmostEqual(R.cmac(e, e), 1.0, places=14)
        self.assertAlmostEqual(R.cmac(np.array([1.0, 0, 0]), np.array([0, 1.0, 0])), 0.0, places=14)

    def test_global_phase_and_scale_invariance(self):
        rng = np.random.default_rng(1)
        e = rng.normal(size=50) + 1j * rng.normal(size=50)
        f = rng.normal(size=50)
        base = R.cmac(e, f)
        self.assertAlmostEqual(R.cmac(e * 7.3 * np.exp(1j * 1.234), f), base, places=13)
        self.assertAlmostEqual(R.cmac(e, -0.01 * f), base, places=13)

    def test_complex_part_is_kept(self):
        e = np.array([1.0, 1j])  # a travelling-wave-like complex shape
        self.assertAlmostEqual(R.cmac(e, np.array([1.0, 0.0])), 0.5, places=14)
        self.assertAlmostEqual(R.cmac(e, np.array([1.0, 1.0])), 0.5, places=14)
        self.assertAlmostEqual(R.cmac(e.real, np.array([1.0, 0.0])), 1.0, places=14)  # real part alone differs

    def test_first_order_sensitivity_to_fe_perturbation(self):
        # R6.5 §1 counterexample: MAC between a fixed experimental vector and a perturbed FE vector is first order.
        e = np.array([1.0, 1.0]) / math.sqrt(2)
        u = np.array([1.0, 0.0])
        theta = 0.14
        u2 = np.array([math.cos(theta), math.sin(theta)])
        self.assertAlmostEqual(R.cmac(e, u), 0.5, places=14)
        self.assertAlmostEqual(R.cmac(e, u2), (1 + math.sin(2 * theta)) / 2, places=14)
        delta = R.cmac(e, u2) - R.cmac(e, u)
        eps = np.linalg.norm(u2 - u) / np.linalg.norm(u)
        self.assertGreater(delta, 0.13)            # ~0.138: first order, not ~eps^2 = 0.02
        self.assertGreater(delta, 5 * eps ** 2)
        self.assertLessEqual(delta, eps / (1 - eps))  # the first-order bound |dMAC| <= eps / (1 - eps)

    def test_refuses_zero_and_non_finite(self):
        with self.assertRaises(R.ResearchRefusal):
            R.cmac(np.zeros(3), np.ones(3))
        with self.assertRaises(R.ResearchRefusal):
            R.cmac(np.array([1.0, np.nan]), np.ones(2))
        with self.assertRaises(R.ResearchRefusal):
            R.cmac(np.ones(3), np.ones(4))

    def test_real_normalised_is_phase_independent(self):
        rng = np.random.default_rng(2)
        e = rng.normal(size=20) + 0.1j * rng.normal(size=20)
        a, b = R.real_normalised(e), R.real_normalised(e * np.exp(1j * 2.1))
        self.assertTrue(np.allclose(np.abs(a), np.abs(b)))


class Subspace(unittest.TestCase):
    def test_basis_rotation_invariance(self):
        rng = np.random.default_rng(3)
        e = rng.normal(size=40) + 1j * rng.normal(size=40)
        f = rng.normal(size=(40, 2))
        t = 0.7
        rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
        self.assertAlmostEqual(R.subspace_projection(e, f), R.subspace_projection(e, f @ rot * 3.0), places=13)

    def test_projection_equals_sum_of_macs_for_orthogonal_basis(self):
        e = np.array([1.0, 2.0, 3.0, 4.0]) + 0.5j
        f1, f2 = np.array([1.0, 1, 0, 0]), np.array([0.0, 0, 1, -1])
        self.assertAlmostEqual(R.subspace_projection(e, np.column_stack([f1, f2])),
                               R.cmac(e, f1) + R.cmac(e, f2), places=13)

    def test_rank_deficient_basis_refused(self):
        f = np.array([1.0, 2.0, 3.0])
        with self.assertRaises(R.ResearchRefusal):
            R.subspace_projection(np.ones(3), np.column_stack([f, 2 * f]))


class Bilinear(unittest.TestCase):
    def test_bilinear_field_reproduced_exactly(self):
        xy, el = grid(6, 5)
        mesh = R.BilinearQuadMesh(xy, el)
        field = 1.5 + 0.2 * xy[:, 0] - 0.3 * xy[:, 1] + 0.001 * xy[:, 0] * xy[:, 1]
        rng = np.random.default_rng(4)
        pts = rng.uniform([0, 0], [301, 300], size=(200, 2))
        got = mesh.sample(field, mesh.locate(pts))
        exact = 1.5 + 0.2 * pts[:, 0] - 0.3 * pts[:, 1] + 0.001 * pts[:, 0] * pts[:, 1]
        self.assertLess(np.max(np.abs(got - exact)), 1e-10)
        self.assertLess(np.max(np.abs(mesh.sample(field, mesh.locate(xy)) - field)), 1e-10)  # nodes exact

    def test_linear_field_on_distorted_quad(self):
        xy = np.array([[0.0, 0.0], [2.0, 0.2], [2.4, 2.1], [-0.1, 1.8]])
        mesh = R.BilinearQuadMesh(xy, np.array([[0, 1, 2, 3]]))
        field = 3.0 + 2.0 * xy[:, 0] - xy[:, 1]
        pts = np.array([[1.0, 1.0], [0.5, 0.4], [1.9, 1.5]])
        got = mesh.sample(field, mesh.locate(pts))
        self.assertLess(np.max(np.abs(got - (3.0 + 2.0 * pts[:, 0] - pts[:, 1]))), 1e-10)

    def test_point_outside_refused(self):
        xy, el = grid(4, 4)
        mesh = R.BilinearQuadMesh(xy, el)
        with self.assertRaises(R.ResearchRefusal):
            mesh.locate(np.array([[150.0, 150.0], [302.0, 10.0]]))


class PointsAndIdentity(unittest.TestCase):
    def test_order_and_count_preserved(self):
        ref = [10, 11, 12, 13]
        vals = np.array([1.0, 2.0, 3.0, 4.0])
        perm = [12, 10, 13, 11]
        got = R.order_by_reference(perm, vals[[2, 0, 3, 1]], ref)
        self.assertTrue(np.array_equal(got, vals))

    def test_missing_extra_duplicate_points_refused(self):
        with self.assertRaises(R.ResearchRefusal):
            R.order_by_reference([10, 11, 12], np.ones(3), [10, 11, 12, 13])
        with self.assertRaises(R.ResearchRefusal):
            R.order_by_reference([10, 11, 12, 14], np.ones(4), [10, 11, 12, 13])
        with self.assertRaises(R.ResearchRefusal):
            R.order_by_reference([10, 10, 12, 13], np.ones(4), [10, 11, 12, 13])

    def test_identity_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.bin"
            p.write_bytes(b"verified")
            good = R.sha256_file(p)
            self.assertEqual(R.verify_identity({"a": p}, {"a": good}), {"a": good})
            with self.assertRaises(R.ResearchRefusal):
                R.verify_identity({"a": p}, {"a": "0" * 64})
            with self.assertRaises(R.ResearchRefusal):
                R.verify_identity({}, {"a": good})
            with self.assertRaises(R.ResearchRefusal):
                R.verify_identity({"a": p, "b": p}, {"a": good})
            with self.assertRaises(R.ResearchRefusal):
                R.verify_identity({"a": Path(d) / "missing"}, {"a": good})

    def test_protocol_is_fixed(self):
        self.assertEqual(len(R.PROTOCOL["scenarios"]), 59)
        self.assertEqual(R.PROTOCOL["fe_modes"], list(range(7, 21)))
        self.assertEqual(len(R.protocol_sha256()), 64)


class CandidateEquivalence(unittest.TestCase):
    def test_a_to_d_give_identical_cmac_on_a_symmetric_model(self):
        xy, el = grid(21, 21)
        w, h = R.PLATE_MM
        x, y = xy[:, 0] - w / 2, xy[:, 1] - h / 2
        # fields with definite parity under the three 180-degree rotations (out-of-plane component)
        fields = [np.cos(np.pi * x / w) * np.cos(np.pi * y / h), x * y, np.sin(np.pi * x / w) * np.cos(np.pi * y / h),
                  np.cos(np.pi * x / w) * np.sin(2 * np.pi * y / h)]
        rng = np.random.default_rng(5)
        pts = rng.uniform([20, 10], [280, 290], size=(60, 2))
        e = rng.normal(size=60) + 1j * rng.normal(size=60)
        mesh, nn = R.BilinearQuadMesh(xy, el), R.NearestNode(xy)
        results = {}
        for k, axes in R.CANDIDATES.items():
            q = R.candidate_to_fe(pts, axes)
            for name, m in (("bilinear", mesh), ("nearest", nn)):
                loc = m.locate(q)
                results[(k, name)] = [R.cmac(e, R.z_sign(axes) * m.sample(f, loc)) for f in fields]
        for name in ("bilinear", "nearest"):
            for k in "BCD":
                self.assertTrue(np.allclose(results[(k, name)], results[("A", name)], atol=1e-12))

    def test_scenario_zero_is_identity_and_rotation_keeps_centroid(self):
        rng = np.random.default_rng(6)
        p = rng.uniform(0, 300, size=(30, 2))
        self.assertTrue(np.allclose(R.scenario_points(p, 0, 0, 0), p))
        q = R.scenario_points(p, 0, 0, 0.874)
        self.assertTrue(np.allclose(q.mean(axis=0), p.mean(axis=0)))


if __name__ == "__main__":
    unittest.main()
