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


if __name__ == "__main__":
    unittest.main()
