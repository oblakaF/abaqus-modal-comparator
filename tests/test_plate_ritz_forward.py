"""Standalone Kirchhoff-Ritz forward model: deterministic SYNTHETIC checks only.

Same-solver checks establish software behaviour, not physical validity. The free-free beam family
is a closed-form solution of this variational problem, computed without the Ritz assembly.
"""

import ast
import dataclasses
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np
from scipy import optimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.plate_material_problem import (
    CoordinateObservationSet,
    DofObservation,
    DofObservationSet,
    ExecutionStatus,
    ForwardBackendId,
    MixedCoordinateReference,
    ObservationPoint,
    PlateBendingParameters,
    PlateForwardRefusal,
    PlateForwardResult,
    PlateGeometry,
    QuantityEvidence,
    QuantitySource,
    RefusalCode,
    ResourceLimits,
    ScientificStatus,
    effective_engineering_constants,
)
from plate_forward_support import SYNTHETIC, TEST_LIMITS, AbaqusForbiddenMixin
from services import plate_ritz_forward as ritz
from services.plate_forward_adapter import RitzForwardBackend
from services.plate_ritz_forward import (
    RitzNumericalConfig,
    assemble_ritz_matrices,
    evaluate_ritz_field,
    evaluate_ritz_observations,
    log_frequency_derivative,
    rigid_coefficients,
    ritz_central_difference_check,
    ritz_model_identity,
    ritz_order_convergence,
    ritz_sensitivities,
    solve_ritz,
)


GEOMETRY = PlateGeometry.from_units(300.0, 200.0, "mm", mass=120.0, mass_unit="g", thickness=2.0)
PARAMETERS = PlateBendingParameters(12.0, 7.0, 1.1, 2.3)
CONFIG = RitzNumericalConfig(8, 8, 6)


def solve(parameters=PARAMETERS, geometry=GEOMETRY, config=CONFIG):
    return solve_ritz(geometry, parameters, config, TEST_LIMITS)


def coefficient_vector(matrices, terms):
    index = {label: position for position, label in enumerate(matrices.labels)}
    vector = np.zeros(len(matrices.labels))
    for label, value in terms.items():
        vector[index[label]] = value
    return vector


class UnitsAndConversions(unittest.TestCase):
    def test_geometry_units_become_si(self):
        self.assertAlmostEqual(GEOMETRY.a_m, 0.3, places=15)
        self.assertAlmostEqual(GEOMETRY.mass_kg, 0.12, places=15)
        self.assertEqual(GEOMETRY.surface_mass_kg_m2, 0.12 / (GEOMETRY.a_m * GEOMETRY.b_m))
        self.assertAlmostEqual(GEOMETRY.thickness_m, 0.002, places=15)

    def test_mass_or_surface_mass_exactly_one(self):
        for arguments in ({}, {"mass": 1.0, "surface_mass_kg_m2": 1.0}):
            with self.assertRaises(PlateForwardRefusal):
                PlateGeometry.from_units(1.0, 1.0, "m", **arguments)
        with self.assertRaises(PlateForwardRefusal):
            PlateGeometry.from_units(1.0, 1.0, "inch", mass=1.0)

    def test_bending_units(self):
        converted = PlateBendingParameters.from_units(12000.0, 7000.0, 1100.0, 2300.0, "N*mm")
        self.assertAlmostEqual(converted.D11, 12.0, places=12)
        self.assertAlmostEqual(converted.D12, 1.1, places=12)

    def test_engineering_conversion_round_trip(self):
        h = 0.002
        parameters = PlateBendingParameters.from_engineering_constants(56.0e9, 42.0e9, 0.17, 4.8e9, h)
        constants = effective_engineering_constants(parameters, h)
        self.assertAlmostEqual(constants.nu12, 0.17, places=12)
        self.assertAlmostEqual(constants.E1_flex_pa / 56.0e9, 1.0, places=12)
        self.assertAlmostEqual(constants.E2_flex_pa / 42.0e9, 1.0, places=12)
        self.assertAlmostEqual(constants.G12_flex_pa / 4.8e9, 1.0, places=12)
        self.assertAlmostEqual(constants.nu12 / constants.E1_flex_pa, constants.nu21 / constants.E2_flex_pa, places=20)

    def test_no_thickness_reports_no_e_or_g(self):
        constants = effective_engineering_constants(PARAMETERS, None)
        self.assertIsNone(constants.E1_flex_pa)
        self.assertIsNone(constants.G12_flex_pa)
        self.assertTrue(constants.missing_reason)

    def test_missing_uncertainty_stays_missing(self):
        evidence = QuantityEvidence("a", QuantitySource.SYNTHETIC)
        self.assertIsNone(evidence.standard_uncertainty_si)
        with self.assertRaises(PlateForwardRefusal):
            QuantityEvidence("a", QuantitySource.MEASURED, 0.0)

    def test_inadmissible_parameters(self):
        for values in ((0.0, 1.0, 0.0, 1.0), (1.0, -1.0, 0.0, 1.0), (1.0, 1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 1.0),
                       (1.0, 4.0, -2.0, 1.0), (math.nan, 1.0, 0.0, 1.0)):
            with self.subTest(values=values), self.assertRaises(PlateForwardRefusal) as caught:
                PlateBendingParameters(*values)
            self.assertIs(caught.exception.code, RefusalCode.INADMISSIBLE_PARAMETERS)


class Assembly(unittest.TestCase):
    def setUp(self):
        self.matrices = assemble_ritz_matrices(GEOMETRY, CONFIG, TEST_LIMITS)
        self.a = GEOMETRY.a_m
        self.b = GEOMETRY.b_m

    def energy(self, matrix, terms):
        vector = coefficient_vector(self.matrices, terms)
        return float(vector @ matrix @ vector)

    def test_exact_curvature_integrals(self):
        a, b = self.a, self.b
        x_squared = {(2, 0): a * a / 6.0, (0, 0): a * a / 12.0}
        y_squared = {(0, 2): b * b / 6.0, (0, 0): b * b / 12.0}
        self.assertAlmostEqual(self.energy(self.matrices.K11, x_squared) / (4.0 * a * b), 1.0, places=12)
        self.assertAlmostEqual(self.energy(self.matrices.K22, y_squared) / (4.0 * a * b), 1.0, places=12)
        self.assertAlmostEqual(self.energy(self.matrices.K22, x_squared), 0.0, places=8)

    def test_mixed_curvature_factor_is_four(self):
        xy = {(1, 1): self.a * self.b / 4.0}
        self.assertAlmostEqual(self.energy(self.matrices.K66, xy) / (4.0 * self.a * self.b), 1.0, places=12)
        self.assertAlmostEqual(self.energy(self.matrices.K11, xy), 0.0, places=8)

    def test_coupling_integral(self):
        # w = x^2*y^2 gives 2*integral(w_xx*w_yy) = 8*(a^3/12)*(b^3/12).
        a, b = self.a, self.b
        terms = {
            (2, 2): (a * a / 6.0) * (b * b / 6.0),
            (2, 0): (a * a / 6.0) * (b * b / 12.0),
            (0, 2): (a * a / 12.0) * (b * b / 6.0),
            (0, 0): (a * a / 12.0) * (b * b / 12.0),
        }
        expected = a**3 * b**3 / 18.0
        self.assertAlmostEqual(self.energy(self.matrices.K12, terms) / expected, 1.0, places=11)

    def test_mass_integral(self):
        mass = solve().mass
        one = coefficient_vector(self.matrices, {(0, 0): 1.0})
        self.assertAlmostEqual(float(one @ mass @ one) / GEOMETRY.mass_kg, 1.0, places=12)

    def test_symmetric_finite_and_mass_positive_definite(self):
        solution = solve()
        for matrix in (self.matrices.K11, self.matrices.K22, self.matrices.K12, self.matrices.K66, solution.mass):
            self.assertTrue(np.isfinite(matrix).all())
            self.assertLessEqual(np.max(np.abs(matrix - matrix.T)), 1.0e-9 * np.max(np.abs(matrix)))
        self.assertGreater(float(np.min(np.linalg.eigvalsh(solution.mass))), 0.0)

    def test_matrix_checks_refuse(self):
        bad = np.eye(3)
        bad[0, 1] = 1.0
        with self.assertRaises(PlateForwardRefusal) as caught:
            ritz._check_matrix(bad, "K", 1.0e-9)
        self.assertIs(caught.exception.code, RefusalCode.ASYMMETRIC_MATRIX)
        bad = np.eye(3)
        bad[0, 0] = math.inf
        with self.assertRaises(PlateForwardRefusal) as caught:
            ritz._check_matrix(bad, "K", 1.0e-9)
        self.assertIs(caught.exception.code, RefusalCode.NON_FINITE_MATRIX)

    def test_mass_not_positive_definite_is_refused(self):
        changed = dataclasses.replace(self.matrices, M_area=-self.matrices.M_area)
        with mock.patch.object(ritz, "assemble_ritz_matrices", return_value=changed):
            with self.assertRaises(PlateForwardRefusal) as caught:
                solve()
        self.assertIs(caught.exception.code, RefusalCode.MASS_NOT_POSITIVE_DEFINITE)

    def test_negative_eigenvalues_are_refused_not_hidden(self):
        changed = dataclasses.replace(
            self.matrices, K11=-self.matrices.K11, K22=-self.matrices.K22, K66=-self.matrices.K66
        )
        with mock.patch.object(ritz, "assemble_ritz_matrices", return_value=changed):
            with self.assertRaises(PlateForwardRefusal) as caught:
                solve(PlateBendingParameters(1.0, 1.0, 0.0, 1.0))
        self.assertIs(caught.exception.code, RefusalCode.NON_POSITIVE_ELASTIC_EIGENVALUE)

    def test_matrices_are_cached_and_read_only(self):
        again = assemble_ritz_matrices(GEOMETRY, CONFIG, TEST_LIMITS)
        self.assertIs(again, self.matrices)
        self.assertFalse(self.matrices.K11.flags.writeable)
        other = PlateGeometry.from_units(301.0, 200.0, "mm", mass=120.0, mass_unit="g")
        self.assertIsNot(assemble_ritz_matrices(other, CONFIG, TEST_LIMITS), self.matrices)


class RigidSubspace(unittest.TestCase):
    def test_three_transverse_rigid_forms(self):
        solution = solve()
        rigid = rigid_coefficients(solution.matrices)
        self.assertEqual(rigid.shape[1], 3)
        self.assertLessEqual(float(np.max(np.abs(solution.stiffness @ rigid))), 1.0e-9 * np.max(np.abs(solution.stiffness)))
        x = np.array([-0.15, 0.15, 0.04, -0.1])
        y = np.array([0.1, -0.1, 0.02, 0.09])
        values = ritz.basis_at_points(solution.matrices, x, y) @ rigid
        np.testing.assert_allclose(values, np.column_stack((np.ones(4), x, y)), atol=1.0e-12)
        self.assertTrue(solution.rigid_diagnostics.verified)

    def test_elastic_modes_are_mass_orthogonal_to_rigid_forms(self):
        solution = solve()
        coupling = rigid_coefficients(solution.matrices).T @ solution.mass @ solution.coefficients
        self.assertLessEqual(float(np.max(np.abs(coupling))), 1.0e-12)

    def test_exactly_three_forms_removed_and_first_elastic_kept(self):
        config = RitzNumericalConfig(8, 8, 81 - 3)
        solution = solve(config=config)
        self.assertEqual(solution.eigenvalues.size, 78)
        self.assertIsNone(solution.next_elastic_eigenvalue)
        self.assertGreater(float(solution.eigenvalues[0]), 0.0)
        all_eigen = np.linalg.eigvals(np.linalg.solve(solution.mass, solution.stiffness)).real
        ordered = np.sort(all_eigen)
        np.testing.assert_allclose(ordered[3] / solution.eigenvalues[0], 1.0, rtol=1.0e-5)
        self.assertLess(abs(ordered[2]), 1.0e-6 * solution.eigenvalues[0])

    def test_broken_rigid_subspace_is_refused(self):
        matrices = assemble_ritz_matrices(GEOMETRY, CONFIG, TEST_LIMITS)
        stiffness = np.array(matrices.K11)
        stiffness[0, 0] = stiffness[1, 1] + 1.0
        changed = dataclasses.replace(matrices, K11=stiffness)
        with mock.patch.object(ritz, "assemble_ritz_matrices", return_value=changed):
            with self.assertRaises(PlateForwardRefusal) as caught:
                solve()
        self.assertIs(caught.exception.code, RefusalCode.RIGID_SUBSPACE_NOT_VERIFIED)


class EigenSystem(unittest.TestCase):
    def test_residuals_and_orthonormality(self):
        solution = solve()
        self.assertLessEqual(solution.max_residual, 1.0e-8)
        self.assertLessEqual(solution.max_orthonormality_error, 1.0e-10)
        np.testing.assert_allclose(solution.frequencies_hz, np.sqrt(solution.eigenvalues) / (2.0 * math.pi))
        self.assertTrue(np.all(np.diff(solution.frequencies_hz) > 0.0))

    def test_uniform_stiffness_scaling(self):
        for factor in (0.25, 3.7):
            scaled = PlateBendingParameters(
                factor * PARAMETERS.D11, factor * PARAMETERS.D22, factor * PARAMETERS.D12, factor * PARAMETERS.D66
            )
            np.testing.assert_allclose(
                solve(scaled).frequencies_hz / solve().frequencies_hz, math.sqrt(factor), rtol=1.0e-8
            )

    def test_size_and_mass_scaling(self):
        base = solve()
        larger = PlateGeometry.from_units(600.0, 400.0, "mm", surface_mass_kg_m2=GEOMETRY.surface_mass_kg_m2)
        np.testing.assert_allclose(solve(geometry=larger).frequencies_hz / base.frequencies_hz, 0.25, rtol=1.0e-7)
        heavier = PlateGeometry.from_units(300.0, 200.0, "mm", mass=480.0, mass_unit="g")
        np.testing.assert_allclose(solve(geometry=heavier).frequencies_hz / base.frequencies_hz, 0.5, rtol=1.0e-8)

    def test_swapping_axes_swaps_the_plate(self):
        swapped_geometry = PlateGeometry.from_units(200.0, 300.0, "mm", mass=120.0, mass_unit="g")
        swapped = PlateBendingParameters(PARAMETERS.D22, PARAMETERS.D11, PARAMETERS.D12, PARAMETERS.D66)
        np.testing.assert_allclose(
            solve(swapped, swapped_geometry).frequencies_hz, solve().frequencies_hz, rtol=1.0e-8
        )


def free_free_beam_roots(count):
    """Roots of cos(z)*cosh(z) = 1, found without any plate code."""

    equation = lambda z: math.cos(z) * math.cosh(z) - 1.0  # noqa: E731
    return [optimize.brentq(equation, (k + 0.5) * math.pi - 0.3, (k + 0.5) * math.pi + 0.3, xtol=1.0e-13)
            for k in range(1, count + 1)]


def free_free_beam_shape(root, length, x):
    s = root * (np.asarray(x) / length + 0.5)
    sigma = (math.cosh(root) - math.cos(root)) / (math.sinh(root) - math.sin(root))
    return np.cosh(s) + np.cos(s) - sigma * (np.sinh(s) + np.sin(s))


class FreeEdgeClosedForm(unittest.TestCase):
    """With D12 = 0, w = phi(x) is an exact free-free beam mode at any D22 and D66.

    The variational problem reduces to the Euler-Bernoulli free-free beam, with lambda =
    D11*(z/a)^4/mu and cos(z)*cosh(z) = 1. Simply-supported or clamped functions cannot reproduce
    these values, so this exercises the natural free-edge conditions. It does not cover D12 != 0.
    """

    def setUp(self):
        self.geometry = PlateGeometry.from_units(400.0, 150.0, "mm", surface_mass_kg_m2=2.5)
        self.config = RitzNumericalConfig(12, 12, 4)

    def check_axis(self, parameters, stiffness, length, x_axis):
        solution = solve(parameters, self.geometry, self.config)
        roots = free_free_beam_roots(3)
        expected = [
            stiffness * (root / length) ** 4 / self.geometry.surface_mass_kg_m2 for root in roots
        ]
        # Rayleigh-Ritz gives upper bounds; the allowance covers rounding only.
        self.assertTrue(np.all(solution.eigenvalues[:3] >= np.array(expected) * (1.0 - 1.0e-10)))
        np.testing.assert_allclose(solution.eigenvalues[:3], expected, rtol=1.0e-5)
        self.assertAlmostEqual(solution.eigenvalues[0] / expected[0], 1.0, delta=1.0e-9)
        along = np.linspace(-length / 2.0, length / 2.0, 41)
        across = np.full(41, 0.031)
        x, y = (along, across) if x_axis else (across, along)
        computed = evaluate_ritz_field(solution, x, y)[:, 0]
        analytic = free_free_beam_shape(roots[0], length, along)
        mac = float(computed @ analytic) ** 2 / float((computed @ computed) * (analytic @ analytic))
        self.assertGreater(mac, 1.0 - 1.0e-10)

    def test_beam_family_along_x(self):
        self.check_axis(PlateBendingParameters(1.5, 500.0, 0.0, 300.0), 1.5, self.geometry.a_m, True)

    def test_beam_family_along_y(self):
        self.check_axis(PlateBendingParameters(5000.0, 0.2, 0.0, 300.0), 0.2, self.geometry.b_m, False)


class Sensitivities(unittest.TestCase):
    CASES = {"positive": 0.2, "zero": 0.0, "negative": -0.3}

    def parameters(self, u):
        return PlateBendingParameters(12.0, 7.0, u * 7.0, 2.3)

    def test_central_differences_match_at_two_steps(self):
        for name, u in self.CASES.items():
            with self.subTest(case=name):
                check = ritz_central_difference_check(
                    solve(self.parameters(u)), step_sizes=(1.0e-3, 2.0e-3), limits=TEST_LIMITS
                )
                self.assertEqual(check.central_differences.shape[0], 2)
                for index in range(2):
                    self.assertLessEqual(
                        float(np.max(np.abs(check.central_differences[index] - check.analytic))), 1.0e-5
                    )

    def test_chain_rule_energy_fractions(self):
        for name, u in self.CASES.items():
            with self.subTest(case=name):
                result = ritz_sensitivities(solve(self.parameters(u)))
                s1, s2, s3, s4 = result.mixed.T
                j11, j22, j12, j66 = result.energy_fractions.T
                np.testing.assert_allclose(j11, 2.0 * s1, atol=1.0e-12)
                np.testing.assert_allclose(j12, 2.0 * u * s4, atol=1.0e-12)
                np.testing.assert_allclose(j22, 2.0 * s2 - 2.0 * u * s4, atol=1.0e-12)
                np.testing.assert_allclose(j66, 2.0 * s3, atol=1.0e-12)
                self.assertLessEqual(result.max_energy_fraction_sum_error, 1.0e-8)

    def test_zero_u_keeps_a_real_u_sensitivity(self):
        result = ritz_sensitivities(solve(self.parameters(0.0)))
        self.assertEqual(float(np.max(np.abs(result.energy_fractions[:, 2]))), 0.0)
        self.assertGreater(float(np.max(np.abs(result.mixed[:, 3]))), 1.0e-3)

    def test_mixed_coordinates_do_not_log_u(self):
        reference = MixedCoordinateReference(10.0, 8.0, 2.0)
        for u in self.CASES.values():
            parameters = self.parameters(u)
            theta = parameters.mixed_coordinates(reference)
            self.assertEqual(theta[3], u)
            restored = PlateBendingParameters.from_mixed_coordinates(theta, reference)
            self.assertAlmostEqual(restored.D22, parameters.D22, places=12)
            self.assertAlmostEqual(restored.D12, parameters.D12, places=12)
        with self.assertRaises(PlateForwardRefusal):
            PlateBendingParameters.from_mixed_coordinates((0.0, 0.0, 0.0, 3.0), MixedCoordinateReference(1.0, 1.0, 1.0))

    def test_formula_includes_a_supplied_mass_derivative(self):
        mass = np.diag([2.0, 3.0])
        vector = np.array([1.0 / math.sqrt(2.0), 0.0])
        stiffness_t = np.diag([4.0, 0.0])
        mass_t = np.diag([0.5, 0.0])
        eigenvalue = 5.0
        expected = (2.0 - 5.0 * 0.25) / (2.0 * 5.0 * 1.0)
        self.assertAlmostEqual(log_frequency_derivative(vector, eigenvalue, stiffness_t, mass, mass_t), expected)


class Degeneracy(unittest.TestCase):
    def setUp(self):
        self.geometry = PlateGeometry.from_units(300.0, 300.0, "mm", mass=100.0, mass_unit="g")
        self.parameters = PlateBendingParameters(5.0, 5.0, 1.5, 1.75)
        self.config = RitzNumericalConfig(10, 10, 6)
        self.solution = solve(self.parameters, self.geometry, self.config)

    def test_symmetric_pair_is_refused_as_single_branches(self):
        self.assertTrue(self.solution.clusters)
        result = ritz_sensitivities(self.solution)
        mode = self.solution.clusters[0][0]
        self.assertIn(mode, result.refused_mode_indexes)
        self.assertTrue(np.isnan(result.mixed[mode]).all())
        with self.assertRaises(PlateForwardRefusal) as caught:
            result.simple_mode_row(mode)
        self.assertIs(caught.exception.code, RefusalCode.DEGENERATE_BRANCH)
        with self.assertRaises(PlateForwardRefusal):
            ritz_central_difference_check(self.solution, limits=TEST_LIMITS)

    def test_cluster_derivative_matches_central_difference_of_the_subspace(self):
        cluster = ritz_sensitivities(self.solution).clusters[0]
        members = list(cluster.mode_indexes)
        step = 1.0e-4

        def rms(parameters):
            values = solve(parameters, self.geometry, self.config).eigenvalues[members]
            return 0.5 * math.log(float(np.mean(values)))

        p = self.parameters
        central = (
            rms(PlateBendingParameters(p.D11 + step, p.D22, p.D12, p.D66))
            - rms(PlateBendingParameters(p.D11 - step, p.D22, p.D12, p.D66))
        ) / (2.0 * step)
        self.assertAlmostEqual(cluster.d_ln_rms_frequency_d_D[0], central, places=6)


class OrderConvergence(unittest.TestCase):
    def setUp(self):
        self.report = ritz_order_convergence(
            GEOMETRY, PARAMETERS, ((6, 6), (8, 8), (10, 10)), 5, limits=TEST_LIMITS
        )

    def test_nested_bases_never_raise_a_frequency(self):
        for step in self.report.steps:
            self.assertTrue(step.frequencies_not_increased)
            self.assertTrue(np.all(step.relative_frequency_change >= -1.0e-10))

    def test_changes_shrink_on_refinement(self):
        first, second = self.report.steps
        self.assertLess(float(np.max(second.relative_frequency_change)), float(np.max(first.relative_frequency_change)))
        self.assertGreater(float(np.min(second.subspace_cosine_squared)), 0.999)
        self.assertLess(second.max_mixed_sensitivity_change, first.max_mixed_sensitivity_change)

    def test_report_carries_no_verdict_or_assumed_rate(self):
        names = {field.name for field in dataclasses.fields(self.report)}
        self.assertEqual(names, {"schedule", "frequencies_by_order", "steps"})

    def test_oversized_schedule_is_refused_before_any_solve(self):
        with mock.patch.object(ritz, "solve_ritz") as solver:
            with self.assertRaises(PlateForwardRefusal) as caught:
                ritz_order_convergence(GEOMETRY, PARAMETERS, ((8, 8), (20, 20)), 5, limits=TEST_LIMITS)
        self.assertIs(caught.exception.code, RefusalCode.RESOURCE_LIMIT)
        solver.assert_not_called()


class Observations(unittest.TestCase):
    def setUp(self):
        self.solution = solve()

    def observe(self, *points):
        return evaluate_ritz_observations(self.solution, CoordinateObservationSet("SYNTHETIC-REG-1", tuple(points)), TEST_LIMITS)

    def test_normal_measurement_equals_the_field(self):
        result = self.observe(ObservationPoint("p1", 0.05, 0.02), ObservationPoint("p2", -0.15, 0.1))
        np.testing.assert_allclose(result.values, evaluate_ritz_field(self.solution, [0.05, -0.15], [0.02, 0.1]))
        self.assertEqual(result.registration_id, "SYNTHETIC-REG-1")
        self.assertEqual(result.values.shape, (2, 6))

    def test_gradient_matches_central_difference(self):
        result = self.observe(ObservationPoint("p", 0.03, -0.04))
        h = 1.0e-5
        wx = (evaluate_ritz_field(self.solution, [0.03 + h], [-0.04]) - evaluate_ritz_field(self.solution, [0.03 - h], [-0.04])) / (2.0 * h)
        wy = (evaluate_ritz_field(self.solution, [0.03], [-0.04 + h]) - evaluate_ritz_field(self.solution, [0.03], [-0.04 - h])) / (2.0 * h)
        np.testing.assert_allclose(result.w_x, wx, rtol=1.0e-6, atol=1.0e-6)
        np.testing.assert_allclose(result.w_y, wy, rtol=1.0e-6, atol=1.0e-6)

    def test_off_normal_uses_kirchhoff_surface_kinematics(self):
        c = math.cos(0.3)
        s = math.sin(0.3)
        z = 0.001
        result = self.observe(ObservationPoint("p", 0.03, -0.04, (s, 0.0, c), z, "line of sight"))
        np.testing.assert_allclose(result.values, c * result.w - z * s * result.w_x)

    def test_off_normal_without_surface_offset_is_refused(self):
        with self.assertRaises(PlateForwardRefusal) as caught:
            self.observe(ObservationPoint("p", 0.03, -0.04, (0.6, 0.0, 0.8)))
        self.assertIs(caught.exception.code, RefusalCode.UNSUPPORTED_KINEMATICS)

    def test_outside_point_is_refused(self):
        with self.assertRaises(PlateForwardRefusal) as caught:
            self.observe(ObservationPoint("p", 0.2, 0.0))
        self.assertIs(caught.exception.code, RefusalCode.OBSERVATION_OUTSIDE_MODEL)

    def test_registration_identity_is_required(self):
        with self.assertRaises(PlateForwardRefusal):
            CoordinateObservationSet(" ", (ObservationPoint("p", 0.0, 0.0),))
        with self.assertRaises(PlateForwardRefusal):
            CoordinateObservationSet("r", (ObservationPoint("p", 0.0, 0.0),), "FE_GLOBAL")

    def test_direction_must_be_a_unit_vector(self):
        with self.assertRaises(PlateForwardRefusal):
            ObservationPoint("p", 0.0, 0.0, (0.0, 0.0, 2.0))


class Preflight(unittest.TestCase):
    def test_refused_before_assembly(self):
        with mock.patch.object(ritz, "_assemble_cached") as assembly:
            with self.assertRaises(PlateForwardRefusal) as caught:
                solve(config=RitzNumericalConfig(20, 20, 6))
        self.assertIs(caught.exception.code, RefusalCode.RESOURCE_LIMIT)
        assembly.assert_not_called()

    def test_allocation_cap(self):
        limits = ResourceLimits(max_allocation_bytes=1024)
        with self.assertRaises(PlateForwardRefusal) as caught:
            solve_ritz(GEOMETRY, PARAMETERS, CONFIG, limits)
        self.assertIs(caught.exception.code, RefusalCode.RESOURCE_LIMIT)

    def test_too_many_modes(self):
        with self.assertRaises(PlateForwardRefusal):
            solve(config=RitzNumericalConfig(2, 2, 7))


class BackendContract(AbaqusForbiddenMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.backend = RitzForwardBackend(GEOMETRY, CONFIG, SYNTHETIC, limits=TEST_LIMITS)

    def test_guard_makes_an_abaqus_attempt_fail(self):
        with self.assertRaises(AssertionError):
            subprocess.run(["abaqus", "information=version"])

    def test_capabilities(self):
        capabilities = self.backend.capabilities
        self.assertEqual(capabilities.independent_parameters, ("D11", "D22", "D12", "D66"))
        self.assertFalse(capabilities.requires_abaqus_installation)
        self.assertFalse(capabilities.requires_odb)
        self.assertFalse(capabilities.requires_matrix_package)
        self.assertFalse(capabilities.performs_material_identification)
        self.assertTrue(self.backend.availability().available)

    def test_completed_result_separates_three_statuses(self):
        result = self.backend.evaluate(PARAMETERS)
        self.assertIs(result.execution_status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.provenance.evidence_kind.value, "SYNTHETIC")
        self.assertIs(result.scientific_status, ScientificStatus.FORWARD_ONLY_NOT_AN_IDENTIFICATION)
        self.assertIs(result.backend_id, ForwardBackendId.KIRCHHOFF_RITZ_4D)
        self.assertEqual(len(result.frequencies_hz), 6)
        self.assertEqual(result.shape.values.shape, (81, 6))
        self.assertEqual(result.diagnostics["rigid_subspace"], "span{1,x,y} separated by mass-orthogonal projection")

    def test_refusal_is_a_result_without_numbers(self):
        points = DofObservationSet("r", (DofObservation("p", 1, 3),))
        result = self.backend.evaluate(PARAMETERS, points)
        self.assertIs(result.execution_status, ExecutionStatus.REFUSED)
        self.assertIs(result.refusal_code, RefusalCode.UNSUPPORTED_OBSERVATION_KIND)
        self.assertEqual(result.frequencies_hz, ())
        self.assertIsNone(result.shape)
        with self.assertRaises(ValueError):
            PlateForwardResult(ExecutionStatus.REFUSED, SYNTHETIC, ForwardBackendId.KIRCHHOFF_RITZ_4D, "x", frequencies_hz=(1.0,))

    def test_run_identity_is_exact(self):
        identity = self.backend.run_identity(PARAMETERS)
        self.assertEqual(identity, self.backend.run_identity(PlateBendingParameters(12.0, 7.0, 1.1, 2.3)))
        nudged = PlateBendingParameters(float(np.nextafter(12.0, 13.0)), 7.0, 1.1, 2.3)
        self.assertNotEqual(identity, self.backend.run_identity(nudged))
        points = CoordinateObservationSet("r", (ObservationPoint("p", 0.0, 0.0),))
        self.assertNotEqual(identity, self.backend.run_identity(PARAMETERS, points))

    def test_model_identity_tracks_geometry_mass_and_order(self):
        base = ritz_model_identity(GEOMETRY, CONFIG)
        self.assertNotEqual(base, ritz_model_identity(GEOMETRY, RitzNumericalConfig(9, 8, 6)))
        heavier = PlateGeometry.from_units(300.0, 200.0, "mm", mass=121.0, mass_unit="g", thickness=2.0)
        self.assertNotEqual(base, ritz_model_identity(heavier, CONFIG))

    def test_repeated_solves_are_identical(self):
        first = self.backend.evaluate(PARAMETERS)
        second = self.backend.evaluate(PARAMETERS)
        self.assertEqual(first.frequencies_hz, second.frequencies_hz)
        np.testing.assert_array_equal(first.shape.values, second.shape.values)


class ModuleBoundaries(unittest.TestCase):
    def test_scientific_modules_import_no_process_or_qt(self):
        forbidden = {"subprocess", "PySide6", "PySide2", "PyQt5", "PyQt6", "matplotlib", "pyautogui"}
        for relative in (
            "src/domain/plate_material_problem.py",
            "src/services/plate_ritz_forward.py",
            "src/services/plate_forward_adapter.py",
        ):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    imported.add(node.module.split(".")[0])
            with self.subTest(module=relative):
                self.assertFalse(imported & forbidden)


if __name__ == "__main__":
    unittest.main()
