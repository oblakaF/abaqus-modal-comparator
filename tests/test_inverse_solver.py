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
        self.assertTrue(diagnostic.practically_identifiable)
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
        self.assertIn("synthetic optimizer failure", result.global_message)
        self.assertTrue(any("synthetic optimizer failure" in item for item in result.warnings))

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

        fake_global_result = mock.Mock(
            success=True,
            message="synthetic global convergence",
            nfev=0,
            x=np.log([self.truth.D11, self.truth.D66]),
        )
        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            return_value=fake_global_result,
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


if __name__ == "__main__":
    unittest.main()
