"""ABM-SOLID-2: element-level checks of the offline orthotropic C3D8I reference kernel.

Synthetic fixtures only. These are numerical checks of published element theory
(Wilson et al. 1973; Taylor, Beresford, Wilson 1976; MacNeal and Harder 1985
patch geometry). They are not evidence of Abaqus equivalence or physical validity.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("OMP_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from services import solid_c3d8i_forward as sf  # noqa: E402

ORTHO = sf.OrthotropicEngineeringConstants(
    e1=50000.0, e2=30000.0, e3=9000.0, nu12=0.08, nu13=0.28, nu23=0.32,
    g12=5000.0, g13=3200.0, g23=2800.0)
STEEL = sf.OrthotropicEngineeringConstants.isotropic(210000.0, 0.3)
RHO = 1.5e-9  # t/mm^3


def box(lx=1.0, ly=1.0, lz=1.0, centre=(0.0, 0.0, 0.0)):
    return np.asarray(centre) + sf.NODE_NATURAL_COORDINATES * np.array([lx, ly, lz]) / 2.0


DISTORTED = np.array([
    [0.0, 0.0, 0.0], [2.2, 0.1, -0.2], [2.5, 1.7, 0.1], [-0.3, 1.4, 0.2],
    [0.2, -0.1, 1.1], [2.0, 0.2, 0.9], [2.4, 1.9, 1.3], [0.1, 1.5, 1.0],
])


def rotation(axis, angle):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k


def linear_field(coords, grad):
    return (coords @ np.asarray(grad).T).reshape(-1)


def strain_of(grad):
    g = np.asarray(grad)
    return np.array([g[0, 0], g[1, 1], g[2, 2], g[0, 1] + g[1, 0], g[0, 2] + g[2, 0], g[1, 2] + g[2, 1]])


class ConstitutiveTests(unittest.TestCase):
    def test_elasticity_is_symmetric_positive_definite_and_inverts_compliance(self):
        c, s = ORTHO.stiffness_matrix(), ORTHO.compliance_matrix()
        np.testing.assert_allclose(c, c.T, rtol=0, atol=1e-9 * np.abs(c).max())
        self.assertGreater(np.linalg.eigvalsh(c)[0], 0.0)
        np.testing.assert_allclose(c @ s, np.eye(6), atol=1e-12)

    def test_abaqus_order_and_reciprocal_poisson_convention(self):
        m = sf.OrthotropicEngineeringConstants.from_abaqus(
            [50000, 30000, 9000, 0.08, 0.28, 0.32, 5000, 3200, 2800])
        self.assertEqual(m, ORTHO)
        strain = ORTHO.compliance_matrix() @ np.array([1.0, 0, 0, 0, 0, 0])
        self.assertAlmostEqual(strain[0], 1 / 50000)
        self.assertAlmostEqual(strain[1], -0.08 / 50000)  # e2 = -nu12 s1 / E1
        self.assertAlmostEqual(strain[2], -0.28 / 50000)
        strain = ORTHO.compliance_matrix() @ np.array([0, 1.0, 0, 0, 0, 0])
        self.assertAlmostEqual(strain[0], -(0.08 * 30000 / 50000) / 30000)  # nu21 = nu12 E2/E1
        self.assertEqual(sf.VOIGT_ORDER, ("11", "22", "33", "12", "13", "23"))

    def test_shear_moduli_act_on_engineering_shear_strains(self):
        c = ORTHO.stiffness_matrix()
        self.assertAlmostEqual(c[3, 3], 5000.0)
        self.assertAlmostEqual(c[4, 4], 3200.0)
        self.assertAlmostEqual(c[5, 5], 2800.0)
        self.assertTrue(np.allclose(c[:3, 3:], 0.0) and np.allclose(c[3:, 3:], np.diag([5000, 3200, 2800])))

    def test_isotropic_limit_matches_lame_constants(self):
        e, nu = 210000.0, 0.3
        lam, mu = e * nu / ((1 + nu) * (1 - 2 * nu)), e / (2 * (1 + nu))
        expected = np.zeros((6, 6))
        expected[:3, :3] = lam
        expected[np.arange(3), np.arange(3)] = lam + 2 * mu
        expected[3:, 3:] = mu * np.eye(3)
        np.testing.assert_allclose(STEEL.stiffness_matrix(), expected, rtol=1e-12)

    def test_stability_determinant_agrees_with_eigen_check(self):
        self.assertGreater(ORTHO.stability_determinant(), 0.0)
        kwargs = dict(e1=1000.0, e2=1000.0, e3=1000.0, nu13=0.3, nu23=0.3, g12=400.0, g13=400.0, g23=400.0)
        self.assertGreater(sf.OrthotropicEngineeringConstants(nu12=0.3, **kwargs).stability_determinant(), 0)
        with self.assertRaises(sf.InadmissibleMaterialError):
            sf.OrthotropicEngineeringConstants(nu12=0.9, **kwargs)

    def test_inadmissible_constants_are_rejected(self):
        good = dict(e1=50000.0, e2=30000.0, e3=9000.0, nu12=0.08, nu13=0.28, nu23=0.32,
                    g12=5000.0, g13=3200.0, g23=2800.0)
        bad_cases = [dict(e1=-1.0), dict(e3=0.0), dict(g12=0.0), dict(g23=-5.0), dict(nu12=float("nan")),
                     dict(e2=float("inf")), dict(nu12=True), dict(nu12=1.4),  # |nu12| >= sqrt(E1/E2)
                     dict(nu13=2.5),  # |nu13| >= sqrt(E1/E3)
                     # each |nu_ij| < sqrt(E_i/E_j) holds, but 1 - 3 nu^2 - 2 nu^3 < 0
                     dict(e1=1000.0, e2=1000.0, e3=1000.0, nu12=0.6, nu13=0.6, nu23=0.6)]
        for change in bad_cases:
            with self.subTest(change=change), self.assertRaises(sf.InadmissibleMaterialError):
                sf.OrthotropicEngineeringConstants(**{**good, **change})
        with self.assertRaises(sf.InadmissibleMaterialError):
            sf.OrthotropicEngineeringConstants.from_abaqus([1, 2, 3])
        with self.assertRaises(sf.InadmissibleMaterialError):
            sf.consistent_mass(box(), 0.0)
        with self.assertRaises(sf.InadmissibleMaterialError):
            sf.c3d8i_reference_stiffness(box(), -ORTHO.stiffness_matrix())


class MaterialAxisTests(unittest.TestCase):
    def test_identity_axes_change_nothing(self):
        np.testing.assert_allclose(sf.global_elasticity(ORTHO, np.eye(3)), ORTHO.stiffness_matrix())
        np.testing.assert_allclose(sf.material_axes_from_points((1, 0, 0), (0, 1, 0)), np.eye(3))

    def test_quarter_turn_about_3_swaps_the_in_plane_constants(self):
        # material axis 1 along global y, axis 2 along global -x
        r = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        swapped = sf.OrthotropicEngineeringConstants(
            e1=ORTHO.e2, e2=ORTHO.e1, e3=ORTHO.e3, nu12=ORTHO.nu12 * ORTHO.e2 / ORTHO.e1,
            nu13=ORTHO.nu23, nu23=ORTHO.nu13, g12=ORTHO.g12, g13=ORTHO.g23, g23=ORTHO.g13)
        np.testing.assert_allclose(sf.global_elasticity(ORTHO, r), swapped.stiffness_matrix(),
                                   rtol=1e-12, atol=1e-8)

    def test_strain_transformation_matches_tensor_rotation(self):
        r = rotation((1, 2, 3), 0.7)
        eps = np.array([[1.0, 0.3, -0.2], [0.3, -0.5, 0.4], [-0.2, 0.4, 0.8]])
        local = r @ eps @ r.T
        voigt = lambda e: np.array([e[0, 0], e[1, 1], e[2, 2], 2 * e[0, 1], 2 * e[0, 2], 2 * e[1, 2]])
        np.testing.assert_allclose(sf.strain_transformation(r) @ voigt(eps), voigt(local), atol=1e-13)

    def test_rotating_geometry_axes_and_field_together_preserves_energy(self):
        r = rotation((0.3, -1.0, 0.6), 1.1)
        grad = np.array([[1e-3, 2e-4, 0], [0, -3e-4, 1e-4], [5e-4, 0, 2e-4]])
        u = linear_field(DISTORTED, grad) + 1e-4 * np.sin(np.arange(24))
        k0 = sf.element_stiffness(sf.FORMULATION_C3D8I_REFERENCE, DISTORTED, ORTHO).stiffness
        x1 = DISTORTED @ r.T
        u1 = (u.reshape(8, 3) @ r.T).reshape(-1)
        # body axes after rotation are r e_i; as rows of the axes matrix that is r^T
        k1 = sf.element_stiffness(sf.FORMULATION_C3D8I_REFERENCE, x1, ORTHO, rotation=r.T).stiffness
        self.assertAlmostEqual(u1 @ k1 @ u1 / (u @ k0 @ u), 1.0, places=12)

    def test_invalid_axes_are_rejected(self):
        for bad in ([[1, 0, 0], [0, 1, 0], [0, 0, -1]], [[1, 0, 0], [0, 2, 0], [0, 0, 1]], np.eye(2)):
            with self.subTest(bad=bad), self.assertRaises(sf.SolidElementError):
                sf.material_axes(bad)
        with self.assertRaises(sf.SolidElementError):
            sf.material_axes_from_points((1, 0, 0), (2, 0, 0))


class ElementMatrixTests(unittest.TestCase):
    def matrices(self, formulation, coords=DISTORTED, material=ORTHO):
        return sf.element_stiffness(formulation, coords, material)

    def test_stiffness_and_mass_are_symmetric(self):
        for f in sf.FORMULATIONS:
            k = self.matrices(f).stiffness
            self.assertEqual(k.shape, (24, 24))
            np.testing.assert_allclose(k, k.T, atol=1e-12 * np.abs(k).max())
        m = sf.consistent_mass(DISTORTED, RHO)
        np.testing.assert_allclose(m, m.T, atol=0)
        self.assertGreater(np.linalg.eigvalsh(m)[0], 0.0)

    def test_six_rigid_body_modes_and_eighteen_deformation_modes(self):
        modes = sf.rigid_body_modes(DISTORTED)
        for f in sf.FORMULATIONS:
            with self.subTest(formulation=f):
                k = self.matrices(f).stiffness
                self.assertLess(np.abs(k @ modes).max(), 1e-10 * np.abs(k).max())
                eig = np.linalg.eigvalsh(k)
                self.assertTrue(np.all(np.abs(eig[:6]) < 1e-10 * eig[-1]))
                self.assertGreater(eig[6], 1e-6 * eig[-1])

    def test_free_element_vibration_through_the_project_eigensolver(self):
        result = sf.element_free_vibration(sf.FORMULATION_C3D8I_REFERENCE, DISTORTED, ORTHO, RHO)
        self.assertEqual(len(result.frequencies_hz), 18)
        self.assertEqual(len(result.rigid_body_eigenvalues), 6)
        self.assertNotEqual(result.rigid_spectrum_health.status, "FAIL")
        self.assertTrue(np.all(np.diff(result.frequencies_hz) >= 0))

    def test_constant_strain_is_reproduced_with_zero_internal_modes(self):
        grad = np.array([[1e-3, 2e-4, -1e-4], [3e-4, -5e-4, 2e-4], [0.0, 4e-4, 6e-4]])
        u = linear_field(DISTORTED, grad)
        eps = strain_of(grad)
        c = ORTHO.stiffness_matrix()
        stiffness = self.matrices(sf.FORMULATION_C3D8I_REFERENCE)
        exact = 0.5 * eps @ c @ eps * sf.element_volume(DISTORTED)
        self.assertAlmostEqual(0.5 * u @ stiffness.stiffness @ u / exact, 1.0, places=11)
        self.assertLess(np.abs(stiffness.internal_amplitudes(u)).max(), 1e-12)
        uncorrected = sf.c3d8i_reference_stiffness(DISTORTED, c, centre_jacobian_correction=False)
        self.assertGreater(np.abs(uncorrected.internal_amplitudes(u)).max(), 1e-7)

    def test_pure_bending_is_exact_for_c3d8i_and_locks_for_plain_hex8(self):
        lx, ly, lz, kappa = 10.0, 2.0, 1.0, 1e-4
        x = box(lx, ly, lz)
        nu12, nu13 = ORTHO.nu12, ORTHO.nu13
        u = np.column_stack([
            kappa * x[:, 0] * x[:, 2],
            -nu12 * kappa * x[:, 1] * x[:, 2],
            -0.5 * kappa * (x[:, 0] ** 2 - nu12 * x[:, 1] ** 2 + nu13 * x[:, 2] ** 2),
        ]).reshape(-1)
        exact = 0.5 * ORTHO.e1 * kappa ** 2 * ly * lx * lz ** 3 / 12.0
        ratio_i = 0.5 * u @ self.matrices(sf.FORMULATION_C3D8I_REFERENCE, x).stiffness @ u / exact
        ratio_h = 0.5 * u @ self.matrices(sf.FORMULATION_HEX8_FULL, x).stiffness @ u / exact
        self.assertAlmostEqual(ratio_i, 1.0, places=10)
        self.assertGreater(ratio_h, 5.0)  # shear locking of the plain brick

    def test_bending_stays_exact_for_an_affinely_skewed_element(self):
        shear = np.array([[1.0, 0.0, 0.0], [0.4, 1.0, 0.0], [0.0, 0.0, 1.0]])
        x = box(6.0, 2.0, 1.0) @ shear.T
        kappa, nu12, nu13 = 1e-4, ORTHO.nu12, ORTHO.nu13
        u = np.column_stack([kappa * x[:, 0] * x[:, 2], -nu12 * kappa * x[:, 1] * x[:, 2],
                             -0.5 * kappa * (x[:, 0] ** 2 - nu12 * x[:, 1] ** 2 + nu13 * x[:, 2] ** 2)]).reshape(-1)
        exact = 0.5 * ORTHO.e1 * kappa ** 2 * 6.0 * 2.0 * 1.0 / 12.0
        k = self.matrices(sf.FORMULATION_C3D8I_REFERENCE, x).stiffness
        self.assertAlmostEqual(0.5 * u @ k @ u / exact, 1.0, places=10)

    def test_condensation_is_stable_for_thin_and_stiff_elements(self):
        thin = box(3.0, 3.0, 0.003)
        for scale in (1e-3, 1.0, 1e5):
            c = ORTHO.stiffness_matrix() * scale
            with self.subTest(scale=scale):
                result = sf.c3d8i_reference_stiffness(thin, c)
                k = result.stiffness
                self.assertTrue(np.all(np.isfinite(k)))
                self.assertLess(result.internal_condition_number, 1e8)
                np.testing.assert_allclose(k, k.T, atol=1e-12 * np.abs(k).max())
                self.assertLess(np.abs(k @ sf.rigid_body_modes(thin)).max(), 1e-8 * np.abs(k).max())
        k1 = sf.c3d8i_reference_stiffness(DISTORTED, ORTHO.stiffness_matrix()).stiffness
        k2 = sf.c3d8i_reference_stiffness(DISTORTED, 7.0 * ORTHO.stiffness_matrix()).stiffness
        np.testing.assert_allclose(k2, 7.0 * k1, rtol=1e-11, atol=1e-11 * np.abs(k2).max())

    def test_consistent_mass_totals_and_rectangular_closed_form(self):
        m = sf.consistent_mass(DISTORTED, RHO)
        volume = sf.element_volume(DISTORTED)
        ones = np.zeros(24)
        ones[0::3] = 1.0
        self.assertAlmostEqual(ones @ m @ ones / (RHO * volume), 1.0, places=12)
        x = box(2.0, 3.0, 0.5)
        mr = sf.consistent_mass(x, RHO)
        v = 3.0
        n = sf.NODE_NATURAL_COORDINATES
        for i in range(8):
            for j in range(8):
                expected = RHO * v / 8.0 * np.prod((1 + n[i] * n[j] / 3.0) / 2.0)
                self.assertAlmostEqual(mr[3 * i, 3 * j] / (RHO * v), expected / (RHO * v), places=13)
        self.assertAlmostEqual(mr[0, 0], RHO * v / 27.0, delta=1e-12 * RHO * v)
        self.assertEqual(mr[0, 1], 0.0)

    def test_units_are_consistent_between_si_and_mm_t_s(self):
        lx = 0.02  # m
        si = sf.OrthotropicEngineeringConstants.isotropic(210e9, 0.3)  # Pa
        mm = sf.OrthotropicEngineeringConstants.isotropic(210e3, 0.3)  # MPa
        f_si = sf.element_free_vibration(sf.FORMULATION_C3D8I_REFERENCE, box(lx, lx, lx), si, 7850.0)
        f_mm = sf.element_free_vibration(sf.FORMULATION_C3D8I_REFERENCE, box(1e3 * lx, 1e3 * lx, 1e3 * lx),
                                         mm, 7.85e-9)
        np.testing.assert_allclose(f_si.frequencies_hz, f_mm.frequencies_hz, rtol=1e-8)
        grad = np.diag([1e-3, 0.0, 0.0])
        x = box(10.0, 2.0, 1.0)
        u = linear_field(x, grad)
        energy = 0.5 * u @ sf.element_stiffness(sf.FORMULATION_C3D8I_REFERENCE, x, mm).stiffness @ u
        eps = strain_of(grad)
        self.assertAlmostEqual(energy / (0.5 * eps @ mm.stiffness_matrix() @ eps * 20.0), 1.0, places=12)  # N mm

    def test_frequency_scaling_with_modulus_and_size(self):
        base = sf.element_free_vibration(sf.FORMULATION_C3D8I_REFERENCE, DISTORTED, ORTHO, RHO).frequencies_hz
        stiff = sf.OrthotropicEngineeringConstants(**{k: (v * 4 if k[0] in "eg" else v)
                                                      for k, v in ORTHO.__dict__.items()})
        f4 = sf.element_free_vibration(sf.FORMULATION_C3D8I_REFERENCE, DISTORTED, stiff, RHO).frequencies_hz
        f2 = sf.element_free_vibration(sf.FORMULATION_C3D8I_REFERENCE, 2 * DISTORTED, ORTHO, RHO).frequencies_hz
        np.testing.assert_allclose(f4, 2 * base, rtol=1e-8)
        np.testing.assert_allclose(f2, base / 2, rtol=1e-8)


class NodeOrderAndFormulationTests(unittest.TestCase):
    def test_dof_order_is_node_major_xyz(self):
        self.assertEqual(sf.DOF_ORDER[:4], ((1, "x"), (1, "y"), (1, "z"), (2, "x")))
        self.assertEqual(len(sf.DOF_ORDER), 24)
        np.testing.assert_allclose(sf.shape_functions(sf.NODE_NATURAL_COORDINATES[2]), np.eye(8)[2])
        self.assertAlmostEqual(sf.shape_functions((0.3, -0.2, 0.7)).sum(), 1.0)

    def test_consistent_renumbering_permutes_the_matrix(self):
        order = [1, 2, 3, 0, 5, 6, 7, 4]  # same element, start one corner further round
        dofs = np.array([3 * n + a for n in order for a in range(3)])
        k0 = sf.element_stiffness(sf.FORMULATION_C3D8I_REFERENCE, DISTORTED, ORTHO).stiffness
        k1 = sf.element_stiffness(sf.FORMULATION_C3D8I_REFERENCE, DISTORTED[order], ORTHO).stiffness
        np.testing.assert_allclose(k1, k0[np.ix_(dofs, dofs)], rtol=1e-10, atol=1e-10 * np.abs(k0).max())

    def test_inverted_or_degenerate_node_order_is_refused(self):
        inverted = DISTORTED[[4, 5, 6, 7, 0, 1, 2, 3]]
        collapsed = DISTORTED.copy()
        collapsed[4:] = collapsed[:4]
        for x in (inverted, collapsed):
            for f in sf.FORMULATIONS:
                with self.subTest(formulation=f), self.assertRaises(sf.SolidElementError):
                    sf.element_stiffness(f, x, ORTHO)
            with self.assertRaises(sf.SolidElementError):
                sf.consistent_mass(x, RHO)
        with self.assertRaises(sf.SolidElementError):
            sf.element_stiffness(sf.FORMULATION_HEX8_FULL, DISTORTED[:7], ORTHO)

    def test_c3d8i_is_never_silently_replaced(self):
        self.assertEqual(sf.formulation_for_abaqus_element("c3d8i"),
                         (sf.FORMULATION_C3D8I_REFERENCE, "NOT_VERIFIED"))
        for label in ("C3D8", "C3D8R", "C3D20", "S4R", "SC8R"):
            with self.subTest(label=label), self.assertRaises(sf.SolidElementError):
                sf.formulation_for_abaqus_element(label)
        for name in ("C3D8I", "C3D8", ""):
            with self.subTest(name=name), self.assertRaises(sf.SolidElementError):
                sf.element_stiffness(name, DISTORTED, ORTHO)
        ki = sf.element_stiffness(sf.FORMULATION_C3D8I_REFERENCE, DISTORTED, ORTHO)
        kh = sf.element_stiffness(sf.FORMULATION_HEX8_FULL, DISTORTED, ORTHO)
        self.assertEqual((ki.internal_mode_count, kh.internal_mode_count), (9, 0))
        self.assertGreater(np.abs(ki.stiffness - kh.stiffness).max(), 1e-3 * np.abs(kh.stiffness).max())
        self.assertEqual(ki.abaqus_equivalence, "NOT_VERIFIED")

    def test_module_runs_no_solver_and_reads_no_files(self):
        text = Path(sf.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "open(", "os.system", "abaqus job", "Popen"):
            self.assertNotIn(forbidden, text)


class PatchTest(unittest.TestCase):
    """MacNeal-Harder 3-D patch: unit cube, seven distorted bricks, linear boundary field."""

    OUTER = sf.NODE_NATURAL_COORDINATES * 0.5 + 0.5
    INNER = np.array([[0.249, 0.342, 0.192], [0.826, 0.288, 0.288], [0.850, 0.649, 0.263],
                      [0.273, 0.750, 0.230], [0.320, 0.186, 0.643], [0.677, 0.305, 0.683],
                      [0.788, 0.693, 0.644], [0.165, 0.745, 0.702]])
    # nodes 0-7 outer, 8-15 inner, both in C3D8 corner order
    ELEMENTS = [
        [8, 9, 10, 11, 12, 13, 14, 15],
        [0, 1, 2, 3, 8, 9, 10, 11], [12, 13, 14, 15, 4, 5, 6, 7],
        [0, 1, 9, 8, 4, 5, 13, 12], [11, 10, 2, 3, 15, 14, 6, 7],
        [0, 8, 11, 3, 4, 12, 15, 7], [9, 1, 2, 10, 13, 5, 6, 14],
    ]
    GRAD = 1e-3 * np.array([[1.0, 0.5, 0.5], [0.5, 1.0, 0.5], [0.5, 0.5, 1.0]])

    def solve(self, element):
        nodes = np.vstack([self.OUTER, self.INNER])
        k = np.zeros((48, 48))
        for conn in self.ELEMENTS:
            dofs = np.array([3 * n + a for n in conn for a in range(3)])
            k[np.ix_(dofs, dofs)] += element(nodes[conn])
        exact = linear_field(nodes, self.GRAD)
        fixed, free = np.arange(24), np.arange(24, 48)
        inner = np.linalg.solve(k[np.ix_(free, free)], -k[np.ix_(free, fixed)] @ exact[fixed])
        return np.abs(inner - exact[free]).max() / np.abs(exact).max()

    def test_patch_passes_for_c3d8i_reference_with_rotated_orthotropy(self):
        c = sf.global_elasticity(ORTHO, rotation((1, 1, 0), 0.6))
        error = self.solve(lambda x: sf.c3d8i_reference_stiffness(x, c).stiffness)
        self.assertLess(error, 1e-10)
        self.assertLess(self.solve(lambda x: sf.hex8_full_stiffness(x, c).stiffness), 1e-10)

    def test_patch_fails_without_the_centre_jacobian_correction(self):
        c = STEEL.stiffness_matrix()
        error = self.solve(lambda x: sf.c3d8i_reference_stiffness(
            x, c, centre_jacobian_correction=False).stiffness)
        self.assertGreater(error, 1e-4)


if __name__ == "__main__":
    unittest.main()
