"""ABM-SOLID-3: INP -> mesh/material -> sparse K, M -> free-free eigenproblem (synthetic fixtures only).

Reference cases are exact properties of the discrete model or classical beam theory for small
synthetic bars and cubes. They are code checks, not Abaqus equivalence or physical validation.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("OMP_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402
from scipy import linalg, sparse  # noqa: E402

from services import solid_c3d8i_forward as sf  # noqa: E402
from services import solid_c3d8i_model as sm  # noqa: E402
from services import solid_c3d8i_solver as ss  # noqa: E402
from services.modal_cluster_service import subspace_mac  # noqa: E402
from test_solid_c3d8i_model import box_inp  # noqa: E402

E1, E2, RHO = 70000.0, 20000.0, 2.7e-9
L, N = 100.0, 20


def discrete_axial_hz(modulus, length=L, elements=N, density=RHO, order=1):
    """Exact first axial frequency of a uniform consistent-mass linear-element bar (free-free)."""
    h, theta = length / elements, order * math.pi / elements
    return math.sqrt(6 * modulus / (density * h * h) * (1 - math.cos(theta)) / (2 + math.cos(theta))) / (2 * math.pi)


class SolverCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def model(self, **kwargs):
        path = Path(self._dir.name) / "m.inp"
        path.write_text(box_inp(**kwargs), encoding="latin-1")
        return sm.load_solid_inp(path)

    def bar(self, **kwargs):
        return self.model(nx=N, ny=1, nz=1, lx=L, ly=5.0, lz=5.0, **kwargs)

    @staticmethod
    def axial(forward, result):
        """Pick the axial mode by mass-weighted shape correlation with cos(pi x / L), not by frequency."""
        x = forward.model.coordinates
        field = np.zeros_like(x)
        field[:, 0] = np.cos(math.pi * (x[:, 0] - x[:, 0].min()) / L)
        field = field.reshape(-1)
        mass = forward.mass_matrix()
        mac = (result.shapes.T @ (mass @ field)) ** 2 / (field @ mass @ field)
        j = int(np.argmax(mac))
        return result.frequencies_hz[j], float(mac[j])


class AssemblyTests(SolverCase):
    def test_sparse_symmetric_assembly_mass_and_rigid_null_space(self):
        m = self.model(nx=4, ny=3, nz=2, lx=40.0, ly=12.0, lz=6.0)
        fm = ss.SolidForwardModel(m)
        k, mass = fm.stiffness_matrix(), fm.mass_matrix()
        self.assertTrue(sparse.issparse(k) and sparse.issparse(mass))
        self.assertEqual(k.shape, (m.dof_count, m.dof_count))
        self.assertLess(abs(k - k.T).max(), 1e-12 * abs(k).max())
        self.assertLess(abs(mass - mass.T).max(), 1e-14 * abs(mass).max())  # summation-order roundoff only
        ux = np.zeros(m.dof_count)
        ux[0::3] = 1.0
        self.assertAlmostEqual(ux @ (mass @ ux) / (RHO * 40.0 * 12.0 * 6.0), 1.0, places=12)
        rigid = ss.rigid_body_fields(m.coordinates)
        self.assertLess(abs(k @ rigid).max(), 1e-9 * abs(k).max())
        pre = fm.preflight(5)
        self.assertLessEqual(k.nnz, pre.matrix_nonzeros)  # structural pattern bounds the stored entries
        self.assertLessEqual(mass.nnz, pre.matrix_nonzeros)
        self.assertEqual(pre.distinct_element_geometries, 1)
        self.assertEqual(pre.dof_count, m.dof_count)

    def test_global_matrix_equals_element_kernel_on_one_element(self):
        m = self.model(nx=1, ny=1, nz=1, lx=3.0, ly=2.0, lz=1.0,
                       orientation="1., 1., 0., -1., 1., 0.\n3, 0.")
        fm = ss.SolidForwardModel(m)
        x = m.coordinates[m.connectivity[0]]
        ke = sf.element_stiffness(sf.FORMULATION_C3D8I_REFERENCE, x, m.material, m.material_axes).stiffness
        dofs = (3 * m.connectivity[0][:, None] + np.arange(3)).reshape(-1)
        np.testing.assert_allclose(fm.stiffness_matrix().toarray()[np.ix_(dofs, dofs)], ke, rtol=1e-12, atol=1e-9)
        np.testing.assert_allclose(fm.mass_matrix().toarray()[np.ix_(dofs, dofs)], sf.consistent_mass(x, RHO))


class ModalTests(SolverCase):
    def test_axial_mode_reproduces_the_exact_discrete_bar_frequency(self):
        fm = ss.SolidForwardModel(self.bar())
        result = fm.solve(14)
        f, mac = self.axial(fm, result)
        self.assertGreater(mac, 1 - 1e-10)
        self.assertAlmostEqual(f / discrete_axial_hz(E1), 1.0, places=10)

    def test_sparse_solution_matches_dense_reference_with_small_residuals(self):
        fm = ss.SolidForwardModel(self.bar())
        result = fm.solve(14)
        w = linalg.eigh(fm.stiffness_matrix().toarray(), fm.mass_matrix().toarray(), eigvals_only=True)
        dense = np.sqrt(w[6:20]) / (2 * math.pi)
        np.testing.assert_allclose(result.frequencies_hz, dense, rtol=1e-9)
        self.assertLess(result.backward_errors.max(), 1e-10)
        self.assertLess(result.mass_orthogonality_error, 1e-10)
        self.assertEqual(result.shapes.shape, (fm.model.dof_count, 14))
        self.assertEqual(len(result.guard_frequencies_hz), 4)

    def test_rigid_modes_are_checked_by_spectrum_and_by_shape(self):
        result = ss.SolidForwardModel(self.bar()).solve(6)
        rigid = result.rigid
        self.assertEqual(rigid.count, 6)
        self.assertEqual(rigid.c2e0_status, "PASS")
        self.assertGreater(rigid.span_cosines.min(), 1 - 1e-10)
        self.assertLess(rigid.max_rigid_content_of_elastic_modes, 1e-10)
        self.assertGreater(result.frequencies_hz[0], 0.0)

    def test_first_bending_pair_against_euler_bernoulli(self):
        lx, h = 200.0, 5.0
        result = ss.SolidForwardModel(self.model(nx=40, ny=1, nz=1, lx=lx, ly=h, lz=h)).solve(2)
        euler = 4.730040745 ** 2 / (2 * math.pi * lx ** 2) * math.sqrt(E1 * h * h / 12 / RHO)
        ratio = result.frequencies_hz / euler
        # shear deformation and rotary inertia make the 3-D beam slightly softer than Euler-Bernoulli
        self.assertTrue(np.all((ratio < 1.0) & (ratio > 0.99)), ratio)

    def test_close_modes_of_a_cube_are_resolved_as_a_subspace(self):
        iso = (1000.0, 1000.0, 1000.0, 0.3, 0.3, 0.3, 384.6153846, 384.6153846, 384.6153846)
        fm = ss.SolidForwardModel(self.model(nx=2, ny=2, nz=2, lx=10.0, ly=10.0, lz=10.0, constants=iso,
                                             orientation=None))
        result = fm.solve(9, guard_modes=3)
        w, v = linalg.eigh(fm.stiffness_matrix().toarray(), fm.mass_matrix().toarray())
        dense = np.sqrt(np.clip(w[6:15], 0, None)) / (2 * math.pi)
        np.testing.assert_allclose(result.frequencies_hz, dense, rtol=1e-8)
        self.assertLess(result.relative_spacing.min(), 1e-8)  # cubic symmetry: repeated frequencies
        # compare the first repeated group as a subspace, never mode by mode
        group = np.flatnonzero(np.abs(dense / dense[0] - 1) < 1e-8)
        self.assertGreater(len(group), 1)
        self.assertGreater(subspace_mac(result.shapes[:, group], v[:, 6 + group]), 1 - 1e-8)
        self.assertLess(result.backward_errors.max(), 1e-10)

    def test_material_axes_change_the_axial_modulus(self):
        fm = ss.SolidForwardModel(self.bar(orientation="0., 1., 0., -1., 0., 0.\n3, 0."))  # axis 2 along -x
        f, mac = self.axial(fm, fm.solve(14))
        self.assertGreater(mac, 1 - 1e-10)
        self.assertAlmostEqual(f / discrete_axial_hz(E2), 1.0, places=10)

    def test_instance_translation_and_rotation_do_not_change_frequencies(self):
        base = ss.SolidForwardModel(self.bar()).solve(8).frequencies_hz
        moved = ss.SolidForwardModel(self.bar(
            translation=(251.0, 270.0, 3.0), rotation=(1.0, 2.0, 0.0, 2.0, 3.0, 1.0, 37.0))).solve(8)
        np.testing.assert_allclose(moved.frequencies_hz, base, rtol=1e-9)


class ParameterTests(SolverCase):
    def test_independent_e1_e2_g12_variation(self):
        fm = ss.SolidForwardModel(self.bar())
        f0, _ = self.axial(fm, fm.solve(14))
        f_e1, mac = self.axial(fm, fm.solve(30, e1=4 * E1))  # the axial mode moves up the spectrum
        self.assertGreater(mac, 1 - 1e-10)
        self.assertAlmostEqual(f_e1 / f0, 2.0, places=9)  # axial depends on E1 only (all nu = 0)
        f_g, mac = self.axial(fm, fm.solve(14, g12=2000.0))
        self.assertGreater(mac, 1 - 1e-10)
        self.assertAlmostEqual(f_g / f0, 1.0, places=9)
        r_e2 = fm.solve(6, e2=5000.0)
        self.assertEqual((r_e2.material.e1, r_e2.material.e2, r_e2.material.g12), (E1, 5000.0, 9000.0))
        self.assertEqual(r_e2.material.e3, fm.model.material.e3)

    def test_inadmissible_parameter_points_are_refused_before_assembly(self):
        poisson = (1000.0, 1000.0, 1000.0, 0.45, 0.45, 0.45, 300.0, 300.0, 300.0)
        fm = ss.SolidForwardModel(self.model(constants=poisson))
        for kwargs in (dict(g12=-1.0), dict(e2=200.0), dict(e1=float("nan"))):
            with self.subTest(kwargs=kwargs), self.assertRaises(sf.InadmissibleMaterialError):
                fm.solve(3, **kwargs)
        with self.assertRaises(ValueError):
            fm.solve(3, material=fm.model.material, e1=1.0)


class ControlTests(SolverCase):
    def test_progress_is_reported_and_cancellation_stops_the_run(self):
        fm = ss.SolidForwardModel(self.bar())
        stages = []
        fm.solve(6, progress=lambda stage, done, total: stages.append(stage))
        self.assertTrue({"assemble mass", "assemble stiffness", "factorise", "eigensolve"} <= set(stages))
        with self.assertRaises(ss.SolverCancelled):
            ss.SolidForwardModel(self.bar()).solve(6, cancel=lambda: True)
        calls = [0]

        def later():
            calls[0] += 1
            return calls[0] > 12

        with self.assertRaises(ss.SolverCancelled):
            ss.SolidForwardModel(self.bar()).solve(6, cancel=later)

    def test_resource_limits(self):
        m = self.bar()
        with self.assertRaisesRegex(ss.ResourceLimitExceeded, "DOFs"):
            ss.SolidForwardModel(m, ss.ResourceLimits(max_dofs=100)).solve(4)
        with self.assertRaisesRegex(ss.ResourceLimitExceeded, "GiB"):
            ss.SolidForwardModel(m, ss.ResourceLimits(max_memory_bytes=10_000)).solve(4)
        self.assertEqual(ss.SolidForwardModel(m, ss.ResourceLimits(max_memory_bytes=10_000)).preflight(4).verdict,
                         "EXCEEDS_LIMITS")
        with self.assertRaisesRegex(ss.ResourceLimitExceeded, "application"):
            ss.SolidForwardModel(m, ss.ResourceLimits(max_operator_applications=3)).solve(4)
        with self.assertRaisesRegex(ss.ResourceLimitExceeded, "Time"):
            ss.SolidForwardModel(m, ss.ResourceLimits(max_seconds=0.0)).solve(4)

    def test_shift_rules(self):
        fm = ss.SolidForwardModel(self.bar())
        with self.assertRaises(ValueError):
            fm.solve(4, shift=10.0)
        result = fm.solve(4)
        self.assertEqual(result.shift_source, "ritz_bound")
        self.assertGreaterEqual(-2.0 * result.shift, result.eigenvalues[0])  # Ritz value bounds lambda_7
        caller = fm.solve(4, shift=-1.0e6)
        np.testing.assert_allclose(caller.frequencies_hz, result.frequencies_hz, rtol=1e-9)

    def test_no_solver_process_or_file_writes(self):
        for module in (ss, sm):
            text = Path(module.__file__).read_text(encoding="utf-8")
            for forbidden in ("subprocess", "write_text", "write_bytes", "os.system", "Popen", "open("):
                self.assertNotIn(forbidden, text, (module.__name__, forbidden))


class ComparisonHelperTests(SolverCase):
    def test_shape_mac_uses_identical_node_identities(self):
        fm = ss.SolidForwardModel(self.bar())
        result = fm.solve(5)
        ids = [f"PART-1-1:{label}" for label in fm.model.node_labels]
        vectors = [result.shape_vectors(j) for j in range(5)]
        order = np.random.default_rng(1).permutation(len(ids))  # reference in another node order
        mac = ss.shape_mac_matrix(result, [ids[i] for i in order], [v[order] for v in vectors])
        np.testing.assert_allclose(np.diag(mac), 1.0, rtol=1e-12)
        with self.assertRaises(ValueError):
            ss.shape_mac_matrix(result, ids[:-1], [v[:-1] for v in vectors])
        with self.assertRaises(ValueError):
            ss.shape_mac_matrix(result, [i.replace("PART-1-1", "OTHER") for i in ids], vectors)

    def test_signed_frequency_residuals(self):
        np.testing.assert_allclose(ss.signed_frequency_residuals([101.0, 99.0, 5.0], [100.0, 100.0]),
                                   [0.01, -0.01])


if __name__ == "__main__":
    unittest.main()
