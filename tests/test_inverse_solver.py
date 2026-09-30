import math
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.modal_observation import (
    InclusionStatus,
    ModalCluster,
    ModalObservation,
)
from domain.parameter_model import ParameterPrior
from services.identifiability_service import (
    analyze_identifiability,
    whiten_sensitivity,
)
from services.inverse_solver import (
    InverseSolverConfiguration,
    InverseSolverValidationError,
    ModeAssignment,
    ModeTrackingMode,
    PairingResult,
    StageAParameterBounds,
    solve_stage_a_inverse,
)
from services.matrix_model_service import (
    AbaqusDof,
    StageAAffineBasis,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from services.sensitivity_service import compute_stage_a_sensitivity
from services import inverse_solver as inverse_solver_module


class StageAInverseSolverTests(unittest.TestCase):
    def setUp(self):
        self.truth = StageAMatrixParameters(12.0, 2.4, 5.0)
        self.constant = np.array([20.0, 40.0, 65.0, 95.0, 130.0, 170.0, 215.0, 265.0])
        self.contributions = (
            np.array([1.2, 0.2, 0.9, 0.4, 1.5, 0.3, 1.1, 0.6]),
            np.array([0.1, 1.0, -0.3, 0.7, 0.2, -0.4, 0.8, -0.1]),
            np.array([0.2, 1.4, 0.3, 1.0, 0.5, 1.6, 0.4, 1.2]),
        )
        self.mass = sparse.diags([1.0, 1.2, 0.9, 1.4, 1.1, 1.5, 1.3, 1.6], format="csr")
        self.dofs = tuple(AbaqusDof(index + 1, 1) for index in range(8))
        reference_stiffness = self._stiffness(self.truth)
        self.basis = StageAAffineBasis(
            reference_parameters=self.truth,
            reference_stiffness=reference_stiffness,
            basis_matrices=tuple(sparse.diags(item, format="csr") for item in self.contributions),
            mass=self.mass,
            dofs=self.dofs,
        )
        truth_result = solve_generalized_eigenproblem(
            reference_stiffness,
            self.mass,
            8,
            expected_rigid_body_modes=0,
            dofs=self.dofs,
        )
        self.truth_frequencies = truth_result.frequencies_hz
        self.bounds = StageAParameterBounds(
            D11=(6.0, 18.0),
            D66=(2.0, 10.0),
            coupling_ratio=(-0.4, 0.5),
        )

    def _stiffness(self, parameters):
        diagonal = self.constant.copy()
        for value, contribution in zip(parameters.values, self.contributions):
            diagonal += value * contribution
        return sparse.diags(diagonal, format="csr")

    def observations(self, frequency_multipliers=None):
        multipliers = (
            np.ones(6)
            if frequency_multipliers is None
            else np.asarray(frequency_multipliers, dtype=float)
        )
        return tuple(
            ModalObservation(
                observation_id=f"obs_{index + 1}",
                physical_specimen_id="SP_SYNTHETIC",
                test_run_id="run_1",
                fe_mode_id=index + 1,
                experimental_mode_id=index + 1,
                fe_frequency_hz=self.truth_frequencies[index],
                experimental_frequency_hz=self.truth_frequencies[index] * multipliers[index],
                mac=1.0,
            )
            for index in range(6)
        )

    def configuration(self, **changes):
        values = dict(
            mode_count=8,
            expected_rigid_body_modes=0,
            random_seed=7123,
            global_max_iterations=100,
            global_population_size=8,
            global_tolerance=1.0e-7,
            global_absolute_tolerance=1.0e-8,
            local_max_evaluations=200,
        )
        values.update(changes)
        return InverseSolverConfiguration(**values)

    def identifiability(self):
        sensitivity = compute_stage_a_sensitivity(
            self.basis,
            self.truth,
            8,
            expected_rigid_body_modes=0,
            finite_difference_relative_steps=(),
        )
        whitened = whiten_sensitivity(
            sensitivity,
            standard_deviations=np.full(8, 0.003),
        )
        return analyze_identifiability(whitened)

    def solve(self, initial, subset, observations=None, **kwargs):
        return solve_stage_a_inverse(
            self.basis,
            self.observations() if observations is None else observations,
            subset,
            initial,
            self.bounds,
            self.configuration(),
            observation_standard_deviations=np.full(6, 0.003),
            identifiability=self.identifiability(),
            identifiability_metadata_reference="synthetic-svd",
            **kwargs,
        )

    def test_noiseless_identifiable_D11_D66_subset_recovers_truth_from_two_guesses(self):
        results = tuple(
            self.solve(initial, ("D11", "D66"))
            for initial in (
                StageAMatrixParameters(7.0, self.truth.D12, 9.0),
                StageAMatrixParameters(17.0, self.truth.D12, 2.5),
            )
        )
        for result in results:
            self.assertLess(result.objective_final, result.objective_initial * 1.0e-10)
            self.assertLess(abs(result.fitted_parameters["D11"] / self.truth.D11 - 1.0), 1.0e-8)
            self.assertLess(abs(result.fitted_parameters["D66"] / self.truth.D66 - 1.0), 1.0e-8)
            self.assertEqual(result.fixed_parameters["D12"], self.truth.D12)
            self.assertFalse(result.pairing_changed_at_optimum)
            self.assertTrue(result.success)
            self.assertEqual(result.identifiability_metadata_reference, "synthetic-svd")
        self.assertEqual(
            results[1].initial_pairing.signature[:2],
            (("obs_1", 2), ("obs_2", 1)),
        )
        self.assertIn("reordering", results[1].initial_pairing.warnings[0])

    def test_noiseless_full_rank_three_parameter_case_recovers_truth(self):
        diagnostic = self.identifiability()
        self.assertEqual(diagnostic.rank, 3)
        self.assertTrue(diagnostic.structurally_identifiable)
        self.assertIsNone(diagnostic.practically_precise_enough)
        result = self.solve(
            StageAMatrixParameters(8.0, -0.8, 8.5),
            ("D11", "D12", "D66"),
        )
        for name, truth in zip(("D11", "D12", "D66"), self.truth.values):
            self.assertLess(abs(result.fitted_parameters[name] / truth - 1.0), 2.0e-8)
        self.assertLess(np.max(np.abs(result.residuals_final)), 1.0e-10)
        self.assertLess(result.objective_final, result.objective_initial * 1.0e-12)
        self.assertTrue(result.success)

    def test_small_deterministic_noise_converges_near_truth_and_keeps_physics(self):
        noisy = self.observations((1.0020, 0.9975, 1.0030, 0.9980, 1.0015, 0.9965))
        result = self.solve(
            StageAMatrixParameters(8.0, -0.8, 8.5),
            ("D11", "D12", "D66"),
            observations=noisy,
        )
        errors = {
            name: abs(result.fitted_parameters[name] / truth - 1.0)
            for name, truth in zip(("D11", "D12", "D66"), self.truth.values)
        }
        self.assertLess(max(errors.values()), 0.12)
        self.assertLess(result.objective_final, result.objective_initial)
        self.assertTrue(result.success)
        self.assertTrue(np.isfinite(result.residuals_final).all())
        for entry in result.convergence_history:
            if not entry.success:
                continue
            values = entry.physical_parameters
            self.assertGreater(values["D11"], 0.0)
            self.assertGreater(values["D66"], 0.0)
            self.assertLess(abs(values["D12"]), values["D11"])

    def test_selection_and_uncertainty_failures_are_explicit(self):
        excluded = tuple(
            ModalObservation(
                observation_id=f"excluded_{index}",
                physical_specimen_id="SP_SYNTHETIC",
                test_run_id="run_1",
                fe_mode_id=index,
                experimental_mode_id=index,
                fe_frequency_hz=self.truth_frequencies[index - 1],
                experimental_frequency_hz=self.truth_frequencies[index - 1],
                mac=1.0,
                inclusion_status=InclusionStatus.EXCLUDED,
                reason="campaign exclusion",
            )
            for index in range(1, 3)
        )
        with self.assertRaisesRegex(InverseSolverValidationError, "No included"):
            solve_stage_a_inverse(
                self.basis,
                excluded,
                ("D11",),
                self.truth,
                self.bounds,
                self.configuration(),
                observation_standard_deviations=(0.003, 0.003),
            )
        with self.assertRaisesRegex(InverseSolverValidationError, "positive definite"):
            solve_stage_a_inverse(
                self.basis,
                self.observations(),
                ("D11", "D66"),
                StageAMatrixParameters(8.0, self.truth.D12, 8.0),
                self.bounds,
                self.configuration(),
                observation_covariance=np.ones((6, 6)),
            )
        with self.assertRaisesRegex(InverseSolverValidationError, "uncertainty is missing"):
            solve_stage_a_inverse(
                self.basis,
                self.observations(),
                ("D11", "D66"),
                StageAMatrixParameters(8.0, self.truth.D12, 8.0),
                self.bounds,
                self.configuration(),
            )

    def test_invalid_initial_nonidentifiable_subset_and_cluster_members_fail(self):
        with self.assertRaisesRegex(InverseSolverValidationError, "outside"):
            solve_stage_a_inverse(
                self.basis,
                self.observations(),
                ("D11", "D66"),
                StageAMatrixParameters(20.0, self.truth.D12, 8.0),
                self.bounds,
                self.configuration(),
                observation_standard_deviations=np.full(6, 0.003),
            )

        deficient = analyze_identifiability(
            np.array([[1.0, 1.0], [2.0, 2.0]]),
            ("D11", "D12"),
            dimensionless=True,
        )
        with self.assertRaisesRegex(InverseSolverValidationError, "not marked"):
            solve_stage_a_inverse(
                self.basis,
                self.observations(),
                ("D11", "D12"),
                StageAMatrixParameters(8.0, -0.8, self.truth.D66),
                self.bounds,
                self.configuration(),
                observation_standard_deviations=np.full(6, 0.003),
                identifiability=deficient,
            )

        observations = self.observations()[:2]
        cluster = ModalCluster(
            cluster_id="cluster_1_2",
            physical_specimen_id="SP_SYNTHETIC",
            test_run_id="run_1",
            observation_ids=("obs_1", "obs_2"),
        )
        with self.assertRaisesRegex(InverseSolverValidationError, "No included"):
            solve_stage_a_inverse(
                self.basis,
                observations + (cluster,),
                ("D11",),
                self.truth,
                self.bounds,
                self.configuration(),
                observation_standard_deviations=(0.003, 0.003),
            )

    def test_optimizer_failure_is_returned_as_structured_status(self):
        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            side_effect=RuntimeError("synthetic optimizer failure"),
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )
        self.assertFalse(result.global_success)
        self.assertFalse(result.global_stage_acceptable)
        self.assertFalse(result.success)
        self.assertIn("synthetic optimizer failure", result.global_message)
        self.assertTrue(any("synthetic optimizer failure" in item for item in result.warnings))

    def test_de_maxiter_with_valid_candidate_is_acceptable_initializer(self):
        candidate = np.log([self.truth.D11, self.truth.D66])

        def exhausted_de(objective, bounds, **kwargs):
            del bounds, kwargs
            value = objective(candidate)
            return mock.Mock(
                x=candidate.copy(),
                fun=value,
                nfev=1,
                success=False,
                message="Maximum number of iterations has been exceeded.",
            )

        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            side_effect=exhausted_de,
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )

        self.assertFalse(result.global_success)
        self.assertTrue(result.global_stage_acceptable)
        self.assertTrue(result.local_success)
        self.assertTrue(result.success)
        self.assertTrue(
            any(
                "convergence criterion was not reached" in item
                and "Maximum number of iterations" in item
                for item in result.warnings
            )
        )

    def test_exact_acceptable_de_candidate_is_passed_to_trf(self):
        candidate = np.log([self.truth.D11, self.truth.D66])
        captured = {}

        def converged_de(objective, bounds, **kwargs):
            del bounds, kwargs
            return mock.Mock(
                x=candidate.copy(),
                fun=objective(candidate),
                nfev=1,
                success=True,
                message="Optimization terminated successfully.",
            )

        def successful_local(residual, x0, **kwargs):
            captured["x0"] = np.asarray(x0).copy()
            residual(x0)
            return mock.Mock(
                x=np.asarray(x0).copy(),
                nfev=1,
                status=3,
                success=True,
                message="`xtol` termination condition is satisfied.",
            )

        with (
            mock.patch(
                "services.inverse_solver.optimize.differential_evolution",
                side_effect=converged_de,
            ),
            mock.patch(
                "services.inverse_solver.optimize.least_squares",
                side_effect=successful_local,
            ),
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )

        np.testing.assert_allclose(captured["x0"], candidate)
        self.assertTrue(result.global_success)
        self.assertTrue(result.global_stage_acceptable)
        self.assertTrue(result.success)

    def test_no_successful_de_objective_evaluation_is_unacceptable(self):
        candidate = np.log([self.truth.D11, self.truth.D66])
        result_without_evaluations = mock.Mock(
            x=candidate,
            fun=0.0,
            nfev=0,
            success=True,
            message="synthetic result without evaluations",
        )
        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            return_value=result_without_evaluations,
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )
        self.assertTrue(result.global_success)
        self.assertFalse(result.global_stage_acceptable)
        self.assertFalse(result.success)

    def test_penalty_only_de_result_is_unacceptable(self):
        candidate = np.log([self.truth.D11, self.truth.D66])
        real_eigensolve = inverse_solver_module.solve_generalized_eigenproblem
        eigensolve_calls = 0

        def fail_only_global_candidate(*args, **kwargs):
            nonlocal eigensolve_calls
            eigensolve_calls += 1
            if eigensolve_calls == 3:
                raise inverse_solver_module.MatrixModelError(
                    "synthetic global candidate failure"
                )
            return real_eigensolve(*args, **kwargs)

        def penalty_de(objective, bounds, **kwargs):
            del bounds, kwargs
            penalty = objective(candidate)
            self.assertEqual(penalty, inverse_solver_module._FAILED_OBJECTIVE)
            return mock.Mock(
                x=candidate,
                fun=penalty,
                nfev=1,
                success=False,
                message="Maximum number of iterations has been exceeded.",
            )

        with (
            mock.patch.object(
                inverse_solver_module,
                "solve_generalized_eigenproblem",
                side_effect=fail_only_global_candidate,
            ),
            mock.patch(
                "services.inverse_solver.optimize.differential_evolution",
                side_effect=penalty_de,
            ),
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )
        self.assertFalse(result.global_stage_acceptable)
        self.assertFalse(result.success)
        self.assertTrue(
            any(not item.success and item.stage == "global" for item in result.convergence_history)
        )

    def test_nonfinite_de_result_is_unacceptable(self):
        valid = np.log([self.truth.D11, self.truth.D66])
        invalid = np.array([np.nan, valid[1]])

        def nonfinite_de(objective, bounds, **kwargs):
            del bounds, kwargs
            objective(valid)
            return mock.Mock(
                x=invalid,
                fun=0.0,
                nfev=1,
                success=True,
                message="synthetic malformed convergence",
            )

        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            side_effect=nonfinite_de,
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )
        self.assertFalse(result.global_stage_acceptable)
        self.assertFalse(result.success)

    def test_out_of_bounds_de_result_is_unacceptable(self):
        valid = np.log([self.truth.D11, self.truth.D66])
        out_of_bounds = np.array([math.log(self.bounds.D11[1]) + 0.1, valid[1]])

        def invalid_de(objective, bounds, **kwargs):
            del bounds, kwargs
            objective(valid)
            return mock.Mock(
                x=out_of_bounds,
                fun=0.0,
                nfev=1,
                success=True,
                message="synthetic malformed convergence",
            )

        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            side_effect=invalid_de,
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )
        self.assertFalse(result.global_stage_acceptable)
        self.assertFalse(result.success)

    def test_failed_trf_remains_fatal_with_acceptable_global_initializer(self):
        candidate = np.log([self.truth.D11, self.truth.D66])

        def converged_de(objective, bounds, **kwargs):
            del bounds, kwargs
            return mock.Mock(
                x=candidate,
                fun=objective(candidate),
                nfev=1,
                success=True,
                message="Optimization terminated successfully.",
            )

        failed_local = mock.Mock(
            x=candidate,
            nfev=1,
            status=0,
            success=False,
            message="The maximum number of function evaluations is exceeded.",
        )
        with (
            mock.patch(
                "services.inverse_solver.optimize.differential_evolution",
                side_effect=converged_de,
            ),
            mock.patch(
                "services.inverse_solver.optimize.least_squares",
                return_value=failed_local,
            ),
        ):
            result = self.solve(
                StageAMatrixParameters(8.0, self.truth.D12, 8.5),
                ("D11", "D66"),
            )
        self.assertTrue(result.global_stage_acceptable)
        self.assertFalse(result.local_success)
        self.assertFalse(result.success)

    def test_comparison_backed_pairing_is_explicit_and_mac_is_not_an_objective_term(self):
        calls = []

        def provider(observations, eigenpairs):
            calls.append(eigenpairs.frequencies_hz.copy())
            return PairingResult(
                assignments=tuple(
                    ModeAssignment(item.observation_id, item.fe_mode_id, mac=0.91)
                    for item in observations
                ),
                method="test comparison adapter",
            )

        initial = self.truth
        result = solve_stage_a_inverse(
            self.basis,
            self.observations(),
            ("D11", "D66"),
            initial,
            self.bounds,
            self.configuration(
                tracking_mode=ModeTrackingMode.COMPARISON_BACKED,
                global_max_iterations=1,
                global_population_size=5,
            ),
            observation_standard_deviations=np.full(6, 0.003),
            comparison_pairing_provider=provider,
        )
        self.assertGreater(len(calls), 1)
        self.assertEqual(result.objective_initial, 0.0)
        self.assertEqual(result.initial_pairing.method, "test comparison adapter")

    def test_objective_is_exact_weighted_log_frequency_least_squares_plus_explicit_prior(self):
        observations = self.observations((1.01, 0.995, 1.002, 1.0, 0.998, 1.004))
        sigmas = np.array([0.004, 0.006, 0.005, 0.004, 0.007, 0.005])
        covariance = np.diag(sigmas**2)
        expected_residuals = np.log(1.0 / np.array([1.01, 0.995, 1.002, 1.0, 0.998, 1.004]))
        expected_modal_objective = float(expected_residuals @ np.linalg.solve(covariance, expected_residuals))
        result = solve_stage_a_inverse(
            self.basis,
            observations,
            ("D11", "D66"),
            self.truth,
            self.bounds,
            self.configuration(global_max_iterations=1, global_population_size=5),
            observation_covariance=covariance,
            priors={"D11": ParameterPrior(mean=10.0, standard_uncertainty=2.0)},
        )
        self.assertAlmostEqual(result.objective_initial, expected_modal_objective + 1.0)

    def test_final_comparison_pairing_change_is_flagged(self):
        calls = 0

        def provider(observations, eigenpairs):
            nonlocal calls
            del eigenpairs
            calls += 1
            mode_ids = list(range(1, len(observations) + 1))
            if calls >= 3:
                mode_ids[0], mode_ids[1] = mode_ids[1], mode_ids[0]
            return PairingResult(
                assignments=tuple(
                    ModeAssignment(item.observation_id, mode_id, mac=0.95)
                    for item, mode_id in zip(observations, mode_ids)
                ),
                method="stateful final-check adapter",
            )

        global_vector = np.log([self.truth.D11, self.truth.D66])

        def fake_global(objective, bounds, **kwargs):
            del bounds, kwargs
            return mock.Mock(
                success=True,
                message="synthetic global convergence",
                nfev=1,
                x=global_vector,
                fun=objective(global_vector),
            )

        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            side_effect=fake_global,
        ):
            result = solve_stage_a_inverse(
                self.basis,
                self.observations(),
                ("D11", "D66"),
                self.truth,
                self.bounds,
                self.configuration(tracking_mode=ModeTrackingMode.COMPARISON_BACKED),
                observation_standard_deviations=np.full(6, 0.003),
                comparison_pairing_provider=provider,
            )
        self.assertTrue(result.pairing_changed_at_optimum)
        self.assertTrue(result.global_stage_acceptable)
        self.assertFalse(result.success)
        self.assertTrue(any("Pairing changed" in item for item in result.warnings))

    def test_downweighted_observation_needs_explicit_numerical_weight(self):
        observations = list(self.observations())
        source = observations[0]
        observations[0] = ModalObservation(
            observation_id=source.observation_id,
            physical_specimen_id=source.physical_specimen_id,
            test_run_id=source.test_run_id,
            fe_mode_id=source.fe_mode_id,
            experimental_mode_id=source.experimental_mode_id,
            fe_frequency_hz=source.fe_frequency_hz,
            experimental_frequency_hz=source.experimental_frequency_hz,
            mac=source.mac,
            inclusion_status=InclusionStatus.DOWNWEIGHTED,
            reason="reviewed low quality",
        )
        result = solve_stage_a_inverse(
            self.basis,
            observations,
            ("D11", "D66"),
            self.truth,
            self.bounds,
            self.configuration(global_max_iterations=1, global_population_size=5),
            observation_standard_deviations=np.full(5, 0.003),
        )
        self.assertNotIn(source.observation_id, result.observation_ids)
        self.assertEqual(
            result.excluded_observations[0].status,
            "downweighted_without_numerical_weight",
        )


class StageAInverseSolverMassDependentTests(unittest.TestCase):
    """Every optimizer evaluation must reconstruct K(x) and M(x) together.

    The basis reference point is deliberately NOT the truth point, so a
    fixed-mass regression (using ``basis.mass`` instead of
    ``basis.reconstruct_mass(parameters)``) would evaluate the truth
    candidate with the wrong mass and leave a non-zero residual floor.
    """

    def setUp(self):
        self.reference = StageAMatrixParameters(9.0, 1.8, 4.5)
        self.truth = StageAMatrixParameters(12.0, 2.4, 5.0)
        self.constant = np.array([20.0, 40.0, 65.0, 95.0, 130.0, 170.0, 215.0, 265.0])
        self.contributions = (
            np.array([1.2, 0.2, 0.9, 0.4, 1.5, 0.3, 1.1, 0.6]),
            np.array([0.1, 1.0, -0.3, 0.7, 0.2, -0.4, 0.8, -0.1]),
            np.array([0.2, 1.4, 0.3, 1.0, 0.5, 1.6, 0.4, 1.2]),
        )
        self.mass_constant = np.array([1.0, 1.2, 0.9, 1.4, 1.1, 1.5, 1.3, 1.6])
        self.mass_slope = np.array(
            [0.02, 0.03, -0.015, 0.025, 0.01, -0.03, 0.015, 0.005]
        )
        self.dofs = tuple(AbaqusDof(index + 1, 1) for index in range(8))
        self.basis = StageAAffineBasis(
            reference_parameters=self.reference,
            reference_stiffness=self._stiffness(self.reference),
            basis_matrices=tuple(
                sparse.diags(item, format="csr") for item in self.contributions
            ),
            mass=sparse.diags(self.mass_constant, format="csr"),
            dofs=self.dofs,
            mass_derivative_D11=sparse.diags(self.mass_slope, format="csr"),
        )
        truth_result = solve_generalized_eigenproblem(
            self._stiffness(self.truth),
            self.basis.reconstruct_mass(self.truth),
            8,
            expected_rigid_body_modes=0,
            dofs=self.dofs,
        )
        self.truth_frequencies = truth_result.frequencies_hz
        self.bounds = StageAParameterBounds(
            D11=(6.0, 18.0), D66=(2.0, 10.0), coupling_ratio=(-0.4, 0.5)
        )

    def _stiffness(self, parameters):
        diagonal = self.constant.copy()
        for value, contribution in zip(parameters.values, self.contributions):
            diagonal += value * contribution
        return sparse.diags(diagonal, format="csr")

    def observations(self):
        return tuple(
            ModalObservation(
                observation_id=f"obs_{index + 1}",
                physical_specimen_id="SP_SYNTHETIC",
                test_run_id="run_1",
                fe_mode_id=index + 1,
                experimental_mode_id=index + 1,
                fe_frequency_hz=self.truth_frequencies[index],
                experimental_frequency_hz=self.truth_frequencies[index],
                mac=1.0,
            )
            for index in range(6)
        )

    def configuration(self):
        return InverseSolverConfiguration(
            mode_count=8,
            expected_rigid_body_modes=0,
            random_seed=7123,
            global_max_iterations=100,
            global_population_size=8,
            global_tolerance=1.0e-7,
            global_absolute_tolerance=1.0e-8,
            local_max_evaluations=200,
        )

    def identifiability(self):
        sensitivity = compute_stage_a_sensitivity(
            self.basis,
            self.truth,
            8,
            expected_rigid_body_modes=0,
            finite_difference_relative_steps=(),
        )
        whitened = whiten_sensitivity(sensitivity, standard_deviations=np.full(8, 0.003))
        return analyze_identifiability(whitened)

    def test_recovery_uses_the_reconstructed_mass_at_every_candidate(self):
        diagnostic = self.identifiability()
        self.assertEqual(diagnostic.rank, 3)
        result = solve_stage_a_inverse(
            self.basis,
            self.observations(),
            ("D11", "D12", "D66"),
            StageAMatrixParameters(8.0, -0.8, 8.5),
            self.bounds,
            self.configuration(),
            observation_standard_deviations=np.full(6, 0.003),
            identifiability=diagnostic,
        )
        for name, truth in zip(("D11", "D12", "D66"), self.truth.values):
            self.assertLess(abs(result.fitted_parameters[name] / truth - 1.0), 1.0e-6)
        self.assertLess(np.max(np.abs(result.residuals_final)), 1.0e-6)
        self.assertLess(result.objective_final, result.objective_initial * 1.0e-8)
        self.assertTrue(result.success)

    def test_fixed_reference_mass_would_not_reach_the_same_truth_residual(self):
        # Regression guard proving the fixture's mass slope is large enough
        # to matter: evaluating the truth candidate with the OLD constant
        # basis.mass (instead of the correct reconstructed mass) leaves a
        # non-zero residual, so the recovery test above is not vacuous.
        stale_mass_result = solve_generalized_eigenproblem(
            self._stiffness(self.truth),
            self.basis.mass,
            8,
            expected_rigid_body_modes=0,
            dofs=self.dofs,
        )
        self.assertFalse(
            np.allclose(stale_mass_result.frequencies_hz, self.truth_frequencies)
        )


class LocalBranchTrackingTests(unittest.TestCase):
    """Local refinement follows global-best FE branches, not frozen eigen-indices.

    Diagonal fixture with M = I: branch P (lambda = 20 D11) crosses the fixed
    branch Q (lambda = 100) exactly at D11 = 5; A, R and H are spectators.
    """

    SIGMA = 0.003
    BRANCH_DOF = {"A": 0, "P": 1, "Q": 2, "R": 3}

    def build(self, truth_d11, observed=("A", "P", "Q")):
        truth = StageAMatrixParameters(truth_d11, 0.5, 5.0)
        diagonal = np.array([45.0, 20.0 * truth_d11, 100.0, 300.0 + 10.0 * truth_d11, 800.0])
        self.basis = StageAAffineBasis(
            reference_parameters=truth,
            reference_stiffness=sparse.diags(diagonal, format="csr"),
            basis_matrices=(
                sparse.diags([0.0, 20.0, 0.0, 10.0, 0.0], format="csr"),
                sparse.diags([0.3, 0.0, 0.0, 0.0, 0.0], format="csr"),
                sparse.diags([1.0, 0.0, 0.0, 0.0, 0.0], format="csr"),
            ),
            mass=sparse.identity(5, format="csr"),
            dofs=tuple(AbaqusDof(index + 1, 1) for index in range(5)),
        )
        reference_order = list(np.argsort(diagonal, kind="stable"))
        frequencies = np.sqrt(diagonal) / (2.0 * math.pi)
        self.observed = tuple(
            ModalObservation(
                observation_id=f"obs_{name}",
                physical_specimen_id="SP_SYNTHETIC",
                test_run_id="run_1",
                fe_mode_id=reference_order.index(self.BRANCH_DOF[name]) + 1,
                experimental_mode_id=index + 1,
                fe_frequency_hz=frequencies[self.BRANCH_DOF[name]],
                experimental_frequency_hz=frequencies[self.BRANCH_DOF[name]],
                mac=1.0,
            )
            for index, name in enumerate(observed)
        )
        self.provider_calls = 0

    def provider(self, observations, eigenpairs):
        """Memoryless shape pairing against the experimental unit-vector shapes."""

        self.provider_calls += 1
        vectors = np.asarray(eigenpairs.eigenvectors, dtype=float)
        rows = [self.BRANCH_DOF[item.observation_id[4:]] for item in observations]
        mac = vectors[rows, :] ** 2 / np.sum(vectors**2, axis=0)[np.newaxis, :]
        observation_indexes, mode_indexes = inverse_solver_module.optimize.linear_sum_assignment(-mac)
        return PairingResult(
            assignments=tuple(
                ModeAssignment(
                    observations[row].observation_id,
                    int(column) + 1,
                    mac=float(mac[row, column]),
                )
                for row, column in zip(observation_indexes, mode_indexes)
            ),
            method="test shape adapter",
        )

    def solve(self, global_d11, tracking_mode=ModeTrackingMode.COMPARISON_BACKED):
        global_vector = np.array([math.log(global_d11)])

        def fixed_global(objective, bounds, **kwargs):
            del bounds, kwargs
            return mock.Mock(
                success=True,
                message="fixed global best",
                nfev=1,
                x=global_vector,
                fun=objective(global_vector),
            )

        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            side_effect=fixed_global,
        ):
            return solve_stage_a_inverse(
                self.basis,
                self.observed,
                ("D11",),
                StageAMatrixParameters(global_d11, 0.5, 5.0),
                StageAParameterBounds(D11=(3.0, 9.0), D66=(3.0, 8.0), coupling_ratio=(0.01, 0.35)),
                InverseSolverConfiguration(
                    mode_count=5,
                    expected_rigid_body_modes=0,
                    random_seed=5,
                    tracking_mode=tracking_mode,
                    local_max_evaluations=100,
                ),
                observation_standard_deviations=np.full(len(self.observed), self.SIGMA),
                comparison_pairing_provider=(
                    self.provider
                    if tracking_mode == ModeTrackingMode.COMPARISON_BACKED
                    else None
                ),
            )

    @staticmethod
    def local_signatures(result):
        return [
            dict(item.pairing_signature)
            for item in result.convergence_history
            if item.stage == "local" and item.success
        ]

    def test_pre_crossing_start_follows_the_branch_to_the_true_optimum(self):
        for tracking_mode in ModeTrackingMode:
            with self.subTest(tracking_mode=tracking_mode.value):
                self.build(6.0)
                result = self.solve(4.5, tracking_mode)
                self.assertEqual(dict(result.global_pairing.signature)["obs_P"], 2)
                self.assertAlmostEqual(result.fitted_parameters["D11"], 6.0, delta=1.0e-7)
                self.assertLess(result.objective_final, 1.0e-10)
                self.assertTrue(result.local_success)
                self.assertFalse(result.pairing_changed_at_optimum)
                self.assertTrue(result.success)
                self.assertEqual(
                    dict(result.final_pairing.signature),
                    {"obs_A": 1, "obs_P": 3, "obs_Q": 2},
                )
                tracked_indexes = {item["obs_P"] for item in self.local_signatures(result)}
                self.assertEqual(tracked_indexes, {2, 3})

    def test_local_stop_on_a_numerically_degenerate_crossing_is_not_silent(self):
        self.build(6.0)

        def crossing_landing(fun, x0, **kwargs):
            del x0, kwargs
            # exp(log 5) lands within one ulp of the exact P/Q eigenvalue tie.
            landing = np.array([math.log(5.0)])
            return optimize_result(landing, fun(landing))

        with mock.patch(
            "services.inverse_solver.optimize.least_squares",
            side_effect=crossing_landing,
        ):
            result = self.solve(4.5)
        self.assertFalse(result.success)
        self.assertFalse(result.local_success)
        self.assertTrue(any("numerically degenerate" in item for item in result.warnings))
        self.assertEqual(result.fitted_parameters["D11"], 4.5)

    def test_local_jacobian_is_the_tracked_branch_derivative_on_both_sides(self):
        self.build(6.0)
        captured = {}
        real_least_squares = inverse_solver_module.optimize.least_squares

        def capturing(fun, x0, **kwargs):
            captured["fun"], captured["jac"] = fun, kwargs["jac"]
            return real_least_squares(fun, x0, **kwargs)

        with mock.patch(
            "services.inverse_solver.optimize.least_squares",
            side_effect=capturing,
        ):
            result = self.solve(4.5)
        rows = {item: index for index, item in enumerate(result.observation_ids)}
        step = 1.0e-7
        for d11 in (4.9, 5.1):
            with self.subTest(D11=d11):
                point = np.array([math.log(d11)])
                analytic = captured["jac"](point)
                finite_difference = (
                    captured["fun"](point + step) - captured["fun"](point - step)
                ) / (2.0 * step)
                np.testing.assert_allclose(
                    analytic[:, 0], finite_difference, rtol=1.0e-6, atol=1.0e-6
                )
                self.assertAlmostEqual(analytic[rows["obs_P"], 0], 0.5 / self.SIGMA, places=6)
                self.assertAlmostEqual(analytic[rows["obs_Q"], 0], 0.0, places=9)

    def test_close_non_crossing_branches_keep_the_global_pairing(self):
        self.build(4.9)
        result = self.solve(4.5)
        global_signature = dict(result.global_pairing.signature)
        self.assertEqual(global_signature, {"obs_A": 1, "obs_P": 2, "obs_Q": 3})
        self.assertAlmostEqual(result.fitted_parameters["D11"], 4.9, delta=1.0e-7)
        self.assertTrue(result.success)
        self.assertFalse(result.pairing_changed_at_optimum)
        self.assertEqual(dict(result.final_pairing.signature), global_signature)
        self.assertTrue(
            all(item == global_signature for item in self.local_signatures(result))
        )

    def eigenpairs(self, d11):
        parameters = StageAMatrixParameters(d11, 0.5, 5.0)
        return solve_generalized_eigenproblem(
            self.basis.reconstruct_stiffness(parameters),
            self.basis.mass,
            5,
            expected_rigid_body_modes=0,
            dofs=self.basis.dofs,
        )

    def test_tracker_changes_index_but_keeps_branch_and_refuses_only_numerical_ties(self):
        self.build(6.0)
        reference = self.eigenpairs(4.5)
        tracker = inverse_solver_module._LocalBranchTracker(
            reference, self.provider(self.observed, reference), self.basis
        )
        cases = (
            (4.8, 2, 3),
            (5.0 * (1.0 - 1.0e-9), 2, 3),  # close but numerically resolved
            (5.0 * (1.0 + 1.0e-9), 3, 2),
            (6.0, 3, 2),
        )
        for d11, p_mode, q_mode in cases:
            with self.subTest(D11=d11):
                pairing = tracker.pairing(self.eigenpairs(d11))
                by_id = {item.observation_id: item for item in pairing.assignments}
                self.assertEqual(by_id["obs_P"].fe_mode_id, p_mode)
                self.assertEqual(by_id["obs_Q"].fe_mode_id, q_mode)
                self.assertEqual(by_id["obs_A"].fe_mode_id, 1)
                for item in pairing.assignments:
                    self.assertAlmostEqual(item.tracking_mac, 1.0, places=12)
                    self.assertIsNone(item.mac)
        self.assertEqual(self.provider_calls, 1)
        with self.assertRaisesRegex(
            inverse_solver_module._UnresolvedLocalBranch, "numerically degenerate"
        ):
            tracker.pairing(self.eigenpairs(5.0))
        with self.assertRaisesRegex(
            inverse_solver_module._UnresolvedLocalBranch, "global-best reference"
        ):
            degenerate = self.eigenpairs(5.0)
            inverse_solver_module._LocalBranchTracker(
                degenerate, self.provider(self.observed, degenerate), self.basis
            )

    def test_degenerate_global_best_refuses_local_refinement(self):
        self.build(6.0)
        with mock.patch(
            "services.inverse_solver.optimize.least_squares",
            side_effect=AssertionError("local refinement started"),
        ) as local:
            result = self.solve(5.0)
        local.assert_not_called()
        self.assertTrue(result.global_stage_acceptable)
        self.assertFalse(result.local_success)
        self.assertFalse(result.success)
        self.assertEqual(result.local_iterations, 0)
        self.assertIn("numerically degenerate", result.local_message)
        self.assertTrue(any("global-stage solution is retained" in item for item in result.warnings))
        self.assertEqual(result.fitted_parameters["D11"], math.exp(math.log(5.0)))

    def test_degenerate_local_candidate_stops_refinement_and_keeps_global_solution(self):
        self.build(6.0)
        visited = []

        def local_through_tie(fun, x0, **kwargs):
            del kwargs
            for d11 in (4.8, 5.0):
                point = np.array([math.log(d11)])
                visited.append(d11)
                fun(point)
            return optimize_result(x0, fun(x0))

        with mock.patch(
            "services.inverse_solver.optimize.least_squares",
            side_effect=local_through_tie,
        ):
            result = self.solve(4.5)
        self.assertEqual(visited, [4.8, 5.0])
        self.assertFalse(result.local_success)
        self.assertFalse(result.success)
        self.assertFalse(result.pairing_changed_at_optimum)
        self.assertEqual(result.fitted_parameters["D11"], 4.5)
        self.assertEqual(result.local_iterations, 2)
        self.assertIn("local candidate", result.local_message)

    def test_local_residual_and_jacobian_never_call_the_pairing_provider(self):
        self.build(6.0)
        real_least_squares = inverse_solver_module.optimize.least_squares
        calls = {}

        def counting(fun, x0, **kwargs):
            calls["before"] = self.provider_calls
            outcome = real_least_squares(fun, x0, **kwargs)
            calls["after"] = self.provider_calls
            return outcome

        with mock.patch(
            "services.inverse_solver.optimize.least_squares",
            side_effect=counting,
        ):
            result = self.solve(4.5)
        self.assertTrue(result.success)
        self.assertGreater(len(self.local_signatures(result)), 1)
        self.assertEqual(calls["after"], calls["before"])
        self.assertEqual(self.provider_calls, calls["after"] + 1)  # final re-pair guard only


def optimize_result(x, values):
    return inverse_solver_module.optimize.OptimizeResult(
        x=x,
        fun=values,
        success=True,
        status=1,
        message="synthetic local stop",
        nfev=1,
    )


class ModeWindowGuardTests(unittest.TestCase):
    """The highest returned elastic mode is a computational guard, never a scalar fitted mode."""

    DOFS = tuple(AbaqusDof(index + 1, 1) for index in range(8))

    def setUp(self):
        self.fixture = StageAInverseSolverTests()
        self.fixture.setUp()

    def window(self, diagonal, mode_count):
        return solve_generalized_eigenproblem(
            sparse.diags(np.asarray(diagonal, dtype=float), format="csr"),
            sparse.identity(len(diagonal), format="csr"),
            mode_count,
            expected_rigid_body_modes=0,
            dofs=self.DOFS[: len(diagonal)],
        )

    def test_exact_pair_split_by_the_upper_edge_is_numerically_degenerate(self):
        split = self.window([10.0, 20.0, 30.0, 30.0, 50.0, 60.0, 70.0, 80.0], 3)
        self.assertEqual(
            inverse_solver_module._numerically_degenerate_modes(split, (1, 2, 3)), (3,)
        )

    def test_close_but_resolved_pair_split_by_the_edge_is_not_degenerate(self):
        resolved = self.window([10.0, 20.0, 30.0, 30.3, 50.0, 60.0, 70.0, 80.0], 3)
        self.assertEqual(
            inverse_solver_module._numerically_degenerate_modes(resolved, (1, 2, 3)), ()
        )

    def solve_fixture(self, observations, mode_count, provider=None, fake_global=None):
        fixture = self.fixture
        kwargs = {}
        configuration_changes = {"mode_count": mode_count}
        if provider is not None:
            kwargs["comparison_pairing_provider"] = provider
            configuration_changes["tracking_mode"] = ModeTrackingMode.COMPARISON_BACKED
        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            side_effect=fake_global or AssertionError("fitting started"),
        ):
            return solve_stage_a_inverse(
                fixture.basis,
                observations,
                ("D11", "D66"),
                fixture.truth,
                fixture.bounds,
                fixture.configuration(**configuration_changes),
                observation_standard_deviations=np.full(len(observations), 0.003),
                **kwargs,
            )

    def truth_global(self):
        vector = np.log([self.fixture.truth.D11, self.fixture.truth.D66])

        def fake_global(objective, bounds, **kwargs):
            del bounds, kwargs
            return mock.Mock(
                success=True, message="fixed", nfev=1, x=vector, fun=objective(vector)
            )

        return fake_global

    def test_observation_on_the_guard_mode_is_refused_before_fitting(self):
        observations = self.fixture.observations()
        fitted = observations[:4] + observations[5:]  # FE modes 1-4 and 6
        with self.assertRaisesRegex(
            InverseSolverValidationError, "guard mode.*fe_mode_id < mode_count.*obs_6"
        ), mock.patch(
            "services.inverse_solver.solve_generalized_eigenproblem",
            side_effect=AssertionError("eigen-solve started"),
        ):
            self.solve_fixture(fitted, 6)

    def test_observations_below_the_guard_mode_remain_valid(self):
        fitted = self.fixture.observations()[:5]  # FE modes 1-5, guard mode 6
        result = self.solve_fixture(fitted, 6, fake_global=self.truth_global())
        self.assertTrue(result.success)
        self.assertEqual(max(item.fe_mode_id for item in result.final_pairing.assignments), 5)

    def guard_provider(self, guard_calls):
        calls = 0

        def provider(observations, eigenpairs):
            nonlocal calls
            calls += 1
            mode_ids = [item.fe_mode_id for item in observations]
            if guard_calls(calls):
                mode_ids[0] = eigenpairs.eigenvalues.size
            return PairingResult(
                assignments=tuple(
                    ModeAssignment(item.observation_id, mode_id, mac=0.95)
                    for item, mode_id in zip(observations, mode_ids)
                ),
                method="guard-mode adapter",
            )

        return provider

    def test_global_candidate_paired_to_the_guard_mode_is_an_invalid_candidate(self):
        recorded = []
        vector = np.log([self.fixture.truth.D11, self.fixture.truth.D66])

        def fake_global(objective, bounds, **kwargs):
            del bounds, kwargs
            recorded.append(objective(vector))
            return mock.Mock(success=True, message="fixed", nfev=1, x=vector, fun=recorded[-1])

        result = self.solve_fixture(
            self.fixture.observations(),
            8,
            provider=self.guard_provider(lambda call: call == 2),
            fake_global=fake_global,
        )
        self.assertEqual(recorded, [inverse_solver_module._FAILED_OBJECTIVE])
        failed = [item for item in result.convergence_history if item.stage == "global" and not item.success]
        self.assertTrue(failed and "guard mode" in failed[0].message)
        self.assertFalse(result.success)

    def test_final_pairing_on_the_guard_mode_is_never_success(self):
        result = self.solve_fixture(
            self.fixture.observations(),
            8,
            provider=self.guard_provider(lambda call: call >= 4),
            fake_global=self.truth_global(),
        )
        self.assertTrue(result.global_stage_acceptable)
        self.assertTrue(result.pairing_changed_at_optimum)
        self.assertFalse(result.success)
        self.assertTrue(any("guard mode" in item for item in result.warnings))

    def tracker_fixture(self):
        # Branch P = 10 D11 moves through fixed entries 20 and 30; mode_count 3.
        reference = StageAMatrixParameters(1.5, 0.5, 5.0)
        basis = StageAAffineBasis(
            reference_parameters=reference,
            reference_stiffness=sparse.diags([10.0, 20.0, 15.0, 30.0, 80.0], format="csr"),
            basis_matrices=(
                sparse.diags([0.0, 0.0, 10.0, 0.0, 0.0], format="csr"),
                sparse.diags([0.0, 0.0, 0.0, 0.0, 0.001], format="csr"),
                sparse.diags([0.0, 0.0, 0.0, 0.0, 0.002], format="csr"),
            ),
            mass=sparse.identity(5, format="csr"),
            dofs=self.DOFS[:5],
        )

        def eigenpairs(d11):
            parameters = StageAMatrixParameters(d11, 0.5, 5.0)
            return solve_generalized_eigenproblem(
                basis.reconstruct_stiffness(parameters),
                basis.mass,
                3,
                expected_rigid_body_modes=0,
                dofs=basis.dofs,
            )

        start = eigenpairs(1.5)  # [10, 15 (P), 20]
        tracker = inverse_solver_module._LocalBranchTracker(
            start,
            PairingResult((ModeAssignment("obs_P", 2),), method="test"),
            basis,
        )
        return tracker, eigenpairs

    def test_tracker_follows_interior_branch_away_from_the_window_edge(self):
        tracker, eigenpairs = self.tracker_fixture()
        assignment = tracker.pairing(eigenpairs(1.8)).assignments[0]
        self.assertEqual(assignment.fe_mode_id, 2)
        self.assertAlmostEqual(assignment.tracking_mac, 1.0, places=12)

    def test_tracker_refuses_when_the_branch_reaches_the_guard_mode(self):
        tracker, eigenpairs = self.tracker_fixture()
        with self.assertRaisesRegex(
            inverse_solver_module._UnresolvedLocalBranch, "mode-window boundary"
        ):
            tracker.pairing(eigenpairs(2.5))  # [10, 20, 25 (P)], next 30

    def test_tracker_refuses_a_tie_with_the_hidden_boundary_eigenvalue(self):
        tracker, eigenpairs = self.tracker_fixture()
        with self.assertRaisesRegex(
            inverse_solver_module._UnresolvedLocalBranch, "numerically degenerate"
        ):
            tracker.pairing(eigenpairs(3.0))  # [10, 20, 30], hidden next 30


class SolverIdentifiabilityGateTests(unittest.TestCase):
    """Rank deficiency is a hard block; the override covers full-rank conditioning only."""

    def setUp(self):
        self.fixture = StageAInverseSolverTests()
        self.fixture.setUp()

    def solve(self, subset, identifiability, *, allow_override):
        fixture = self.fixture
        return solve_stage_a_inverse(
            fixture.basis,
            fixture.observations(),
            subset,
            StageAMatrixParameters(8.0, -0.8, 8.5),
            fixture.bounds,
            fixture.configuration(
                global_max_iterations=5,
                local_max_evaluations=20,
                allow_non_identifiable_subset=allow_override,
            ),
            observation_standard_deviations=np.full(6, 0.003),
            identifiability=identifiability,
        )

    # A / B
    def test_rank_deficient_subset_is_refused_with_or_without_override(self):
        full_set_deficient = analyze_identifiability(
            np.array([[1.0, 1.0], [2.0, 2.0]]), ("D11", "D12"), dimensionless=True
        )
        # Full model rank 2 of 3; the (D11, D12) subset alone has rank 1.
        subset_deficient = analyze_identifiability(
            np.array([[1.0, 2.0, 0.0], [2.0, 4.0, 0.0], [0.0, 0.0, 1.0]]),
            ("D11", "D12", "D66"),
            dimensionless=True,
        )
        cases = (
            ("full set", ("D11", "D12"), full_set_deficient, "rank 1 for 2"),
            ("proper subset", ("D11", "D12"), subset_deficient, "rank 1 for 2"),
            ("deficient full model", ("D11", "D12", "D66"), subset_deficient, "rank 2 for 3"),
        )
        for name, subset, identifiability, rank_text in cases:
            for allow_override in (False, True):
                with self.subTest(name, allow_override=allow_override), mock.patch(
                    "services.inverse_solver.optimize.differential_evolution",
                    side_effect=AssertionError("fitting started"),
                ) as optimizer:
                    with self.assertRaisesRegex(
                        InverseSolverValidationError,
                        f"not marked structurally identifiable.*{rank_text}.*hard block",
                    ):
                        self.solve(subset, identifiability, allow_override=allow_override)
                optimizer.assert_not_called()

    # C / D
    def test_full_rank_poor_conditioning_keeps_the_explicit_override(self):
        ill_conditioned = analyze_identifiability(
            np.array([[1.0, 0.0], [0.0, 1.0e-3]]), ("D11", "D66"), dimensionless=True
        )
        self.assertTrue(ill_conditioned.structurally_identifiable)
        self.assertFalse(ill_conditioned.collinearity.warning)
        self.assertGreater(ill_conditioned.condition_number, 100.0)
        with self.assertRaisesRegex(InverseSolverValidationError, "Use an explicit override"):
            self.solve(("D11", "D66"), ill_conditioned, allow_override=False)
        result = self.solve(("D11", "D66"), ill_conditioned, allow_override=True)
        self.assertTrue(any("Explicit override accepted" in item for item in result.warnings))
        self.assertEqual(set(result.fitted_parameters), {"D11", "D66"})

    # E
    def test_full_rank_gamma_violation_keeps_the_explicit_override(self):
        collinear = analyze_identifiability(
            np.array([[1.0, 1.0], [0.0, 0.01]]),
            ("D11", "D66"),
            dimensionless=True,
            condition_warning_threshold=1.0e12,
        )
        self.assertTrue(collinear.structurally_identifiable)
        self.assertTrue(collinear.collinearity.warning)
        self.assertLessEqual(collinear.condition_number, 1.0e12)
        with self.assertRaisesRegex(InverseSolverValidationError, "Use an explicit override"):
            self.solve(("D11", "D66"), collinear, allow_override=False)
        result = self.solve(("D11", "D66"), collinear, allow_override=True)
        self.assertTrue(any("Explicit override accepted" in item for item in result.warnings))


if __name__ == "__main__":
    unittest.main()
