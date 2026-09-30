import math
from pathlib import Path
import sys
import unittest

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.modal_observation import ModalCluster
from services.matrix_model_service import (
    AbaqusDof,
    GeneralizedEigenResult,
    StageAAffineBasis,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from services import sensitivity_service
from services.sensitivity_service import (
    ParameterSensitivityCoordinate,
    StageASensitivityCoordinate,
    _stage_a_coordinates_and_derivatives,
    analytic_eigenvalue_derivative,
    compute_stage_a_sensitivity,
    eigenvalue_to_frequency_derivative,
    generalized_eigen_sensitivity,
)


class AnalyticEigenvalueDerivativeTests(unittest.TestCase):
    def test_known_generalized_derivative_and_frequency_conversion(self):
        mass = sparse.diags([2.0, 3.0], format="csr")
        stiffness_derivative = sparse.diags([4.0, 0.0], format="csr")
        mass_derivative = sparse.diags([1.0, 0.0], format="csr")
        derivative = analytic_eigenvalue_derivative(
            2.0,
            np.array([1.0, 0.0]),
            mass,
            stiffness_derivative,
            mass_derivative,
        )
        self.assertAlmostEqual(derivative, 1.0)
        self.assertAlmostEqual(
            eigenvalue_to_frequency_derivative(2.0, derivative),
            1.0 / (4.0 * math.pi * math.sqrt(2.0)),
        )

    def test_arbitrary_complex_eigenvector_scaling_does_not_change_derivative(self):
        mass = sparse.diags([2.0, 3.0], format="csr")
        stiffness_derivative = sparse.diags([4.0, 1.0], format="csr")
        base = np.array([1.0, 0.0])
        scaled = (3.0 + 4.0j) * base
        first = analytic_eigenvalue_derivative(
            2.0, base, mass, stiffness_derivative
        )
        second = analytic_eigenvalue_derivative(
            2.0, scaled, mass, stiffness_derivative
        )
        self.assertAlmostEqual(first, second)


class StageASensitivityTests(unittest.TestCase):
    def setUp(self):
        self.parameters = StageAMatrixParameters(10.0, 0.0, 5.0)
        self.basis_matrices = (
            sparse.diags([1.0, 0.2, 0.1], format="csr"),
            sparse.diags([0.1, 0.3, 0.05], format="csr"),
            sparse.diags([0.2, 0.1, 0.8], format="csr"),
        )
        constant = sparse.diags([5.0, 8.0, 12.0], format="csr")
        stiffness = constant.copy()
        for value, contribution in zip(
            self.parameters.values, self.basis_matrices
        ):
            stiffness = stiffness + value * contribution
        self.mass = sparse.diags([2.0, 1.0, 3.0], format="csr")
        self.dofs = tuple(AbaqusDof(index + 1, 1) for index in range(3))
        self.basis = StageAAffineBasis(
            reference_parameters=self.parameters,
            reference_stiffness=stiffness,
            basis_matrices=self.basis_matrices,
            mass=self.mass,
            dofs=self.dofs,
        )

    def test_stage_a_analytic_derivatives_agree_with_three_central_fd_steps(self):
        result = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            3,
            expected_rigid_body_modes=0,
        )
        self.assertEqual(result.parameter_ids, ("D11", "D12", "D66"))
        self.assertTrue(result.derivative_validation.consistent)
        self.assertLess(result.derivative_validation.worst_relative_error, 1.0e-3)
        self.assertEqual(
            result.derivative_validation.relative_steps, (0.005, 0.01, 0.02)
        )
        self.assertTrue(np.all(result.raw_derivatives > 0.0))

    def test_zero_d12_uses_explicit_D11_characteristic_scale(self):
        result = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            3,
            expected_rigid_body_modes=0,
            finite_difference_relative_steps=(),
        )
        d12_coordinate = result.parameter_coordinates[1]
        self.assertEqual(d12_coordinate.scaling, "characteristic_D11")
        self.assertEqual(d12_coordinate.scale, self.parameters.D11)
        self.assertTrue(np.isfinite(result.scaled_sensitivity).all())

    def test_zero_ratio_balanced_coordinate_is_finite_and_explicit(self):
        result = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            3,
            coordinate_system=StageASensitivityCoordinate.BALANCED,
            expected_rigid_body_modes=0,
            finite_difference_relative_steps=(),
        )
        self.assertEqual(result.parameter_ids, ("D", "D66", "r"))
        ratio_coordinate = result.parameter_coordinates[2]
        self.assertEqual(ratio_coordinate.scaling, "characteristic_ratio")
        self.assertEqual(ratio_coordinate.scale, 1.0)
        self.assertTrue(np.isfinite(result.scaled_sensitivity).all())

    def test_modal_cluster_is_excluded_with_subspace_status(self):
        cluster = ModalCluster(
            cluster_id="cluster_2_3",
            physical_specimen_id="SP01",
            test_run_id="run_1",
            observation_ids=("obs_2", "obs_3"),
        )
        result = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            2,
            observations=("obs_1", cluster),
            expected_rigid_body_modes=0,
            finite_difference_relative_steps=(),
        )
        self.assertEqual(result.observation_ids, ("obs_1",))
        self.assertEqual(result.raw_derivatives.shape, (1, 3))
        self.assertEqual(
            result.excluded_cluster_observations[0].status,
            "cluster_requires_subspace_sensitivity",
        )

    def test_legacy_constant_mass_basis_has_no_mass_derivative_contribution(self):
        self.assertIsNone(self.basis.mass_derivative_D11)
        coordinates, derivatives, mass_derivatives = _stage_a_coordinates_and_derivatives(
            self.basis, self.parameters, StageASensitivityCoordinate.AFFINE, 1.0
        )
        self.assertIsNone(mass_derivatives)

    def test_general_api_keeps_raw_and_scaled_derivatives_separate(self):
        eigenpairs = GeneralizedEigenResult(
            eigenvalues=np.array([4.0]),
            frequencies_hz=np.array([1.0 / math.pi]),
            eigenvectors=np.array([[1.0], [0.0]]),
            dofs=None,
            rigid_body_eigenvalues=np.array([]),
        )
        result = generalized_eigen_sensitivity(
            eigenpairs,
            sparse.eye(2, format="csr"),
            (sparse.diags([2.0, 0.0], format="csr"),),
            (
                ParameterSensitivityCoordinate(
                    "p", "physical p", 10.0, "characteristic"
                ),
            ),
        )
        expected_raw = 2.0 / (4.0 * math.pi * 2.0)
        self.assertAlmostEqual(result.raw_derivatives[0, 0], expected_raw)
        self.assertAlmostEqual(
            result.scaled_sensitivity[0, 0],
            10.0 * expected_raw / result.frequencies_hz[0],
        )


class StageAMassDependentSensitivityTests(unittest.TestCase):
    """Covers dM/dx wiring once a basis carries a recovered D11 mass slope."""

    def setUp(self):
        self.parameters = StageAMatrixParameters(10.0, 0.0, 5.0)
        self.basis_matrices = (
            sparse.diags([1.0, 0.2, 0.1], format="csr"),
            sparse.diags([0.1, 0.3, 0.05], format="csr"),
            sparse.diags([0.2, 0.1, 0.8], format="csr"),
        )
        constant = sparse.diags([5.0, 8.0, 12.0], format="csr")
        stiffness = constant.copy()
        for value, contribution in zip(self.parameters.values, self.basis_matrices):
            stiffness = stiffness + value * contribution
        self.mass = sparse.diags([2.0, 1.0, 3.0], format="csr")
        self.mass_derivative_D11 = sparse.diags([0.03, -0.01, 0.02], format="csr")
        self.dofs = tuple(AbaqusDof(index + 1, 1) for index in range(3))
        self.basis = StageAAffineBasis(
            reference_parameters=self.parameters,
            reference_stiffness=stiffness,
            basis_matrices=self.basis_matrices,
            mass=self.mass,
            dofs=self.dofs,
            mass_derivative_D11=self.mass_derivative_D11,
        )

    def test_mass_derivative_is_wired_only_into_the_D11_D_coordinate(self):
        for coordinate_system in (
            StageASensitivityCoordinate.AFFINE,
            StageASensitivityCoordinate.BALANCED,
        ):
            _, _, mass_derivatives = _stage_a_coordinates_and_derivatives(
                self.basis, self.parameters, coordinate_system, 1.0
            )
            self.assertIsNotNone(mass_derivatives)
            self.assertEqual(len(mass_derivatives), 3)
            np.testing.assert_allclose(
                mass_derivatives[0].toarray(), self.mass_derivative_D11.toarray()
            )
            self.assertIsNone(mass_derivatives[1])
            self.assertIsNone(mass_derivatives[2])

    def test_analytic_sensitivity_including_dM_dx_matches_central_finite_differences(self):
        result = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            3,
            expected_rigid_body_modes=0,
        )
        self.assertTrue(result.derivative_validation.consistent)
        self.assertLess(result.derivative_validation.worst_relative_error, 1.0e-3)

    def test_balanced_coordinate_analytic_sensitivity_matches_finite_differences(self):
        result = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            3,
            coordinate_system=StageASensitivityCoordinate.BALANCED,
            expected_rigid_body_modes=0,
        )
        self.assertTrue(result.derivative_validation.consistent)
        self.assertLess(result.derivative_validation.worst_relative_error, 1.0e-3)

    def test_ignoring_the_mass_derivative_would_disagree_with_finite_differences(self):
        # A regression guard: confirms the fixture's mass slope is large enough
        # that omitting mass_derivatives from the analytic formula would fail
        # finite-difference validation, so test_analytic_sensitivity_including_
        # dM_dx_matches_central_finite_differences above is not passing
        # vacuously.
        eigenpairs = solve_generalized_eigenproblem(
            self.basis.reconstruct_stiffness(self.parameters),
            self.basis.reconstruct_mass(self.parameters),
            3,
            expected_rigid_body_modes=0,
            dofs=self.basis.dofs,
        )
        without_mass_derivative = generalized_eigen_sensitivity(
            eigenpairs,
            self.mass,
            self.basis_matrices,
            (
                ParameterSensitivityCoordinate("D11", "d11", self.parameters.D11, "relative"),
                ParameterSensitivityCoordinate(
                    "D12", "d12", self.parameters.D11, "characteristic_D11"
                ),
                ParameterSensitivityCoordinate("D66", "d66", self.parameters.D66, "relative"),
            ),
        )
        with_mass_derivative = generalized_eigen_sensitivity(
            eigenpairs,
            self.mass,
            self.basis_matrices,
            (
                ParameterSensitivityCoordinate("D11", "d11", self.parameters.D11, "relative"),
                ParameterSensitivityCoordinate(
                    "D12", "d12", self.parameters.D11, "characteristic_D11"
                ),
                ParameterSensitivityCoordinate("D66", "d66", self.parameters.D66, "relative"),
            ),
            mass_derivatives=(self.mass_derivative_D11, None, None),
        )
        self.assertFalse(
            np.allclose(
                without_mass_derivative.raw_derivatives[:, 0],
                with_mass_derivative.raw_derivatives[:, 0],
            )
        )


class ObservedModeSensitivityTests(unittest.TestCase):
    """Explicit observed_mode_ids: only the requested scalar modes are validated."""

    DOFS = tuple(AbaqusDof(index + 1, 1) for index in range(8))
    # Distinct diagonal slopes, so each row reveals which DOF (mode) it came from.
    SLOPES = np.arange(1.0, 9.0)

    def solve(self, diagonal, mode_count):
        return solve_generalized_eigenproblem(
            sparse.diags(diagonal, format="csr"),
            sparse.identity(8, format="csr"),
            mode_count,
            expected_rigid_body_modes=0,
            dofs=self.DOFS,
        )

    def sensitivity(self, eigenpairs, **kwargs):
        return generalized_eigen_sensitivity(
            eigenpairs,
            sparse.identity(8, format="csr"),
            (sparse.diags(self.SLOPES, format="csr"),),
            (ParameterSensitivityCoordinate("p", "physical p", 1.0, "characteristic"),),
            **kwargs,
        )

    def expected_row(self, diagonal, mode_id):
        # Unit eigenvector e_k and M = I give d(lambda)/dp = slope_k.
        index = int(np.argsort(diagonal, kind="stable")[mode_id - 1])
        return self.SLOPES[index] / (4.0 * math.pi * math.sqrt(diagonal[index]))

    def assert_degenerate_refusal(self, context, mode_id):
        message = str(context.exception)
        self.assertIsInstance(
            context.exception, sensitivity_service.ScalarModeSensitivityRefusal
        )
        self.assertIn(f"FE mode {mode_id} ", message)
        self.assertIn("numerically degenerate", message)
        self.assertIn("single-eigenvector Rayleigh", message)
        self.assertIn("not an automatic fallback", message)

    def test_isolated_requested_mode_returns_expected_sensitivity(self):
        diagonal = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
        result = self.sensitivity(self.solve(diagonal, 5), observed_mode_ids=(2,))
        self.assertEqual(result.observation_ids, ("mode_2",))
        self.assertEqual(result.raw_derivatives.shape, (1, 1))
        self.assertAlmostEqual(result.raw_derivatives[0, 0], self.expected_row(diagonal, 2))
        self.assertAlmostEqual(result.frequencies_hz[0], math.sqrt(20.0) / (2.0 * math.pi))

    def test_interior_exact_doublet_member_is_refused(self):
        eigenpairs = self.solve([10.0, 20.0, 20.0, 40.0, 50.0, 60.0, 70.0, 80.0], 5)
        for mode_id in (2, 3):
            with self.subTest(mode_id=mode_id):
                with self.assertRaises(ValueError) as context:
                    self.sensitivity(eigenpairs, observed_mode_ids=(mode_id,))
                self.assert_degenerate_refusal(context, mode_id)

    def test_upper_window_hidden_doublet_is_refused_as_degenerate(self):
        # Mode 4 is tied with the uncomputed mode 5 just above the window.
        eigenpairs = self.solve([10.0, 20.0, 30.0, 40.0, 40.0, 60.0, 70.0, 80.0], 4)
        self.assertEqual(eigenpairs.next_elastic_eigenvalue, 40.0)
        with self.assertRaises(ValueError) as context:
            self.sensitivity(eigenpairs, observed_mode_ids=(4,))
        self.assert_degenerate_refusal(context, 4)
        self.assertIn("above the returned mode window", str(context.exception))

    def test_close_but_resolved_neighbour_passes(self):
        diagonal = [10.0, 20.0, 30.0, 30.3, 50.0, 60.0, 70.0, 80.0]
        result = self.sensitivity(self.solve(diagonal, 5), observed_mode_ids=(3, 4))
        np.testing.assert_allclose(
            result.raw_derivatives[:, 0],
            [self.expected_row(diagonal, 3), self.expected_row(diagonal, 4)],
        )

    def test_unrelated_doublet_does_not_invalidate_the_request(self):
        diagonal = [10.0, 20.0, 30.0, 50.0, 50.0, 60.0, 70.0, 80.0]
        result = self.sensitivity(self.solve(diagonal, 7), observed_mode_ids=(2, 6))
        self.assertEqual(result.observation_ids, ("mode_2", "mode_6"))
        np.testing.assert_allclose(
            result.raw_derivatives[:, 0],
            [self.expected_row(diagonal, 2), self.expected_row(diagonal, 6)],
        )

    def test_one_degenerate_mode_refuses_the_whole_multi_mode_request(self):
        eigenpairs = self.solve([10.0, 20.0, 30.0, 30.0, 50.0, 60.0, 70.0, 80.0], 6)
        with self.assertRaises(ValueError) as context:
            self.sensitivity(eigenpairs, observed_mode_ids=(2, 3))
        self.assert_degenerate_refusal(context, 3)
        self.assertNotIn("FE mode 2 ", str(context.exception))

    def test_requested_guard_mode_is_refused(self):
        eigenpairs = self.solve([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0], 5)
        with self.assertRaisesRegex(
            sensitivity_service.ScalarModeSensitivityRefusal,
            "FE mode 5 is the computational guard mode.*more modal headroom",
        ):
            self.sensitivity(eigenpairs, observed_mode_ids=(2, 5))
        for invalid in ((6,), (0,), (True,), (2, 2), (), (2.5,)):
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, TypeError)):
                self.sensitivity(eigenpairs, observed_mode_ids=invalid)

    def test_rows_follow_the_declared_request_order(self):
        diagonal = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
        eigenpairs = self.solve(diagonal, 5)
        result = self.sensitivity(eigenpairs, observed_mode_ids=(4, 1, 3))
        self.assertEqual(result.observation_ids, ("mode_4", "mode_1", "mode_3"))
        np.testing.assert_allclose(
            result.raw_derivatives[:, 0],
            [self.expected_row(diagonal, mode_id) for mode_id in (4, 1, 3)],
        )
        np.testing.assert_allclose(
            result.frequencies_hz, eigenpairs.frequencies_hz[[3, 0, 2]]
        )
        np.testing.assert_allclose(
            result.scaled_sensitivity[:, 0],
            result.raw_derivatives[:, 0] / result.frequencies_hz,
        )

    def test_explicit_request_cannot_be_combined_with_positional_observations(self):
        eigenpairs = self.solve([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0], 3)
        with self.assertRaisesRegex(ValueError, "observed_mode_ids"):
            self.sensitivity(
                eigenpairs, observations=("a", "b", "c"), observed_mode_ids=(1,)
            )

    def test_legacy_none_path_keeps_full_spectrum_behaviour(self):
        # Without an explicit scientific request, ties and the top returned
        # mode are not refused: low-level algebraic use is unchanged.
        diagonal = [10.0, 20.0, 20.0, 40.0, 50.0, 60.0, 70.0, 80.0]
        result = self.sensitivity(self.solve(diagonal, 4))
        self.assertEqual(
            result.observation_ids, ("mode_1", "mode_2", "mode_3", "mode_4")
        )
        self.assertAlmostEqual(result.raw_derivatives[3, 0], self.expected_row(diagonal, 4))
        tied_top = self.solve([10.0, 20.0, 30.0, 40.0, 40.0, 60.0, 70.0, 80.0], 4)
        self.assertEqual(self.sensitivity(tied_top).raw_derivatives.shape, (4, 1))


class ObservedModeStageASensitivityTests(unittest.TestCase):
    def setUp(self):
        fixture = StageASensitivityTests()
        fixture.setUp()
        self.basis = fixture.basis
        self.parameters = fixture.parameters

    def test_requested_rows_match_full_rows_and_pass_fd_validation_in_order(self):
        full = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            3,
            expected_rigid_body_modes=0,
            finite_difference_relative_steps=(),
        )
        requested = compute_stage_a_sensitivity(
            self.basis,
            self.parameters,
            3,
            expected_rigid_body_modes=0,
            observed_mode_ids=(2, 1),
        )
        self.assertEqual(requested.observation_ids, ("mode_2", "mode_1"))
        np.testing.assert_allclose(requested.raw_derivatives, full.raw_derivatives[[1, 0]])
        np.testing.assert_allclose(requested.frequencies_hz, full.frequencies_hz[[1, 0]])
        self.assertTrue(requested.derivative_validation.consistent)
        self.assertLess(requested.derivative_validation.worst_relative_error, 1.0e-3)

    def test_requested_guard_mode_is_refused(self):
        with self.assertRaisesRegex(
            sensitivity_service.ScalarModeSensitivityRefusal, "guard mode"
        ):
            compute_stage_a_sensitivity(
                self.basis,
                self.parameters,
                3,
                expected_rigid_body_modes=0,
                observed_mode_ids=(1, 3),
            )


if __name__ == "__main__":
    unittest.main()
