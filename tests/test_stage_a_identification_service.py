from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape, compare_modal_datasets
from services.inverse_solver import (
    InverseSolverConfiguration,
    ModeAssignment,
    PairingResult,
    StageAParameterBounds,
)
from services.matrix_model_service import (
    AbaqusDof,
    GeneralizedEigenResult,
    StageAAffineBasis,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from services.specimen_comparison_service import comparison_to_observations
from services.stage_a_identification_service import (
    ComparatorPairingError,
    PairingProviderMode,
    ProductionComparisonPairingProvider,
    StageACampaignPolicy,
    StageAIdentificationError,
    create_production_pairing_provider,
    identify_stage_a,
)
from tests import test_core


class SyntheticProductionFixture:
    def __init__(self, *, rank_deficient=False, mass_dependent=False):
        grid_x, grid_y = np.meshgrid(np.arange(4.0), np.arange(3.0))
        self.coordinates = np.column_stack(
            (grid_x.ravel(), 1.3 * grid_y.ravel(), np.zeros(grid_x.size))
        )
        # A complete, evenly-spaced rectangular grid is invariant under a
        # 180-degree rotation and both axis mirrors regardless of aspect
        # ratio; nudge one point off that exact symmetry so the point set
        # has exactly one geometrically admissible registration, for a
        # reason unrelated to what these tests verify.
        self.coordinates[-1] += np.array([0.05, -0.03, 0.0])
        self.node_ids = np.arange(1, len(self.coordinates) + 1)
        centered = self.coordinates - np.mean(self.coordinates, axis=0)
        rigid_z = np.column_stack(
            (np.ones(len(centered)), centered[:, 0], centered[:, 1])
        )
        complete, _ = np.linalg.qr(rigid_z, mode="complete")
        self.elastic_vectors = complete[:, 3:]
        base = np.array(
            [1.0e5, 1.5e5, 2.1e5, 2.8e5, 3.6e5, 4.5e5, 5.5e5, 6.6e5, 8.0e5]
        )
        coefficients = [
            np.array([2500, 300, 1800, 700, 2800, 500, 2100, 900, 0.0]),
            np.array([200, 1800, -600, 1400, 400, -800, 1600, -200, 0.0]),
            np.array([400, 2600, 600, 1800, 900, 3000, 700, 2200, 0.0]),
        ]
        if rank_deficient:
            coefficients[1] = coefficients[0].copy()
        self.truth = StageAMatrixParameters(12.0, 2.4, 5.0)

        def modal_matrix(diagonal):
            return sparse.csr_matrix(
                self.elastic_vectors @ np.diag(diagonal) @ self.elastic_vectors.T
            )

        basis_matrices = tuple(modal_matrix(item) for item in coefficients)
        reference = modal_matrix(base)
        for value, contribution in zip(self.truth.values, basis_matrices):
            reference = reference + value * contribution
        self.dofs = tuple(AbaqusDof(int(node_id), 3) for node_id in self.node_ids)
        mass_derivative_D11 = None
        if mass_dependent:
            # A small, deterministic D11 mass slope: still verified to be
            # invariant to D12/D66 (only StageAMatrixParameters.D11 enters
            # reconstruct_mass), harmless at the reference/truth point since
            # its coefficient there is exactly zero.
            mass_derivative_D11 = sparse.diags(
                0.001 * np.arange(1, len(self.node_ids) + 1, dtype=float), format="csr"
            )
        self.basis = StageAAffineBasis(
            reference_parameters=self.truth,
            reference_stiffness=reference,
            basis_matrices=basis_matrices,
            mass=sparse.eye(len(self.node_ids), format="csr"),
            dofs=self.dofs,
            mass_derivative_D11=mass_derivative_D11,
        )
        truth_modes = solve_generalized_eigenproblem(
            reference,
            self.basis.reconstruct_mass(self.truth),
            8,
            expected_rigid_body_modes=3,
            dofs=self.dofs,
        )
        abaqus_modes = [
            self._mode(index + 1, truth_modes.frequencies_hz[index], truth_modes.eigenvectors[:, index])
            for index in range(8)
        ]
        experimental_modes = [
            self._mode(index + 1, truth_modes.frequencies_hz[index], 2.5 * truth_modes.eigenvectors[:, index])
            for index in range(6)
        ]
        self.comparison = compare_modal_datasets(
            ModalDataset("Abaqus", Path("synthetic.odb"), abaqus_modes),
            ModalDataset("Experiment", Path("synthetic.unv"), experimental_modes),
            coordinate_scale_override=1.0,
        )
        self.bounds = StageAParameterBounds(
            D11=(8.0, 16.0),
            D66=(3.0, 8.0),
            coupling_ratio=(0.05, 0.35),
        )

    def _mode(self, number, frequency, values):
        vectors = np.zeros((len(self.node_ids), 3), dtype=float)
        vectors[:, 2] = values
        return ModeShape(
            number=number,
            frequency_hz=float(frequency),
            node_ids=self.node_ids,
            coordinates=self.coordinates,
            vectors=vectors,
        )

    def configuration(self, **changes):
        values = dict(
            mode_count=8,
            expected_rigid_body_modes=3,
            random_seed=4815,
            global_max_iterations=45,
            global_population_size=6,
            global_tolerance=1.0e-7,
            global_absolute_tolerance=1.0e-5,
            local_max_evaluations=100,
        )
        values.update(changes)
        return InverseSolverConfiguration(**values)

    def identify(self, **changes):
        values = dict(
            comparison=self.comparison,
            affine_model=self.basis,
            initial_parameters=StageAMatrixParameters(9.0, 0.9, 7.0),
            parameter_bounds=self.bounds,
            requested_parameter_subset=("D11", "D12", "D66"),
            solver_configuration=self.configuration(),
            design_id="synthetic-design",
            physical_specimen_id="SP-SYNTHETIC",
            test_run_id="run-1",
            observation_standard_deviations=0.003,
        )
        values.update(changes)
        return identify_stage_a(**values)


class ProductionPairingProviderTests(unittest.TestCase):
    def test_existing_comparator_fixture_pairing_and_mac_are_adapted_verbatim(self):
        fixture = test_core.ModalCoreTests()
        comparison = fixture.synthetic_result()
        observations = comparison_to_observations(
            comparison, "fixture-design", "SP-FIXTURE", "run-1"
        )

        class ExistingDatasetAdapter:
            def __call__(self, eigenpairs):
                del eigenpairs
                return comparison.abaqus

        provider = ProductionComparisonPairingProvider(
            comparison,
            ExistingDatasetAdapter(),
        )
        dummy = GeneralizedEigenResult(
            eigenvalues=np.ones(3),
            frequencies_hz=np.ones(3),
            eigenvectors=np.eye(3),
            dofs=None,
            rigid_body_eigenvalues=np.array([]),
        )
        pairing = provider(observations, dummy)
        by_experimental = {
            pair.experimental_mode: pair for pair in provider.last_comparison.pairs
        }
        self.assertEqual(
            pairing.signature,
            tuple(
                sorted(
                    (
                        observation.observation_id,
                        by_experimental[observation.experimental_mode_id].abaqus_mode,
                    )
                    for observation in observations
                )
            ),
        )
        for assignment in pairing.assignments:
            observation = next(
                item for item in observations if item.observation_id == assignment.observation_id
            )
            self.assertEqual(
                assignment.mac,
                by_experimental[observation.experimental_mode_id].mac,
            )
        self.assertTrue(any(pair.order_changed for pair in provider.last_comparison.pairs))
        self.assertEqual(pairing.method, "existing reviewed modal comparator")


class StageAIdentificationOrchestrationTests(unittest.TestCase):
    def test_end_to_end_comparison_to_identifiability_to_solver_recovers_truth(self):
        fixture = SyntheticProductionFixture()
        provider = create_production_pairing_provider(
            fixture.comparison, fixture.basis, coordinate_scale_override=1.0
        )
        result = fixture.identify(pairing_provider=provider)
        errors = {
            name: abs(result.inverse_result.fitted_parameters[name] / truth - 1.0)
            for name, truth in zip(("D11", "D12", "D66"), fixture.truth.values)
        }
        self.assertLess(max(errors.values()), 2.0e-7)
        self.assertEqual(result.identifiability.rank, 3)
        self.assertEqual(result.requested_parameter_subset, ("D11", "D12", "D66"))
        self.assertEqual(result.fitted_parameter_subset, result.requested_parameter_subset)
        self.assertEqual(result.pairing_provider_mode, PairingProviderMode.COMPARATOR)
        self.assertEqual(result.effective_observation_count, 5)
        self.assertTrue(result.inverse_result.success)
        self.assertGreater(provider.call_count, result.inverse_result.global_optimizer_evaluations)
        mode_one = next(
            item for item in result.observations if item.experimental_mode_id == 1
        )
        self.assertEqual(mode_one.inclusion_status.value, "excluded")
        self.assertEqual(mode_one.reason, "probable suspension influence")
        self.assertFalse(result.metadata["mac_used_in_objective"])
        self.assertEqual(result.metadata["mass_model"], "constant reference mass")

    def test_mass_dependent_basis_recovers_truth_and_reports_affine_mass_provenance(self):
        fixture = SyntheticProductionFixture(mass_dependent=True)
        self.assertIsNotNone(fixture.basis.mass_derivative_D11)
        provider = create_production_pairing_provider(
            fixture.comparison, fixture.basis, coordinate_scale_override=1.0
        )
        result = fixture.identify(pairing_provider=provider)
        errors = {
            name: abs(result.inverse_result.fitted_parameters[name] / truth - 1.0)
            for name, truth in zip(("D11", "D12", "D66"), fixture.truth.values)
        }
        self.assertLess(max(errors.values()), 2.0e-6)
        self.assertEqual(result.identifiability.rank, 3)
        self.assertTrue(result.inverse_result.success)
        self.assertIn("affine in D11", result.metadata["mass_model"])

    def test_manual_rejection_is_preserved_and_not_sent_to_pairing_provider(self):
        fixture = SyntheticProductionFixture()
        rejected_pair = fixture.comparison.pairs[-1]
        rejected_pair.manual_decision = "rejected"
        rejected_pair.manual_comment = "campaign review"
        result = fixture.identify(
            requested_parameter_subset=("D11", "D66"),
            solver_configuration=fixture.configuration(global_max_iterations=20),
        )
        rejected = next(
            item
            for item in result.observations
            if item.experimental_mode_id == rejected_pair.experimental_mode
        )
        self.assertEqual(rejected.inclusion_status.value, "excluded")
        self.assertIn("campaign review", rejected.reason)
        self.assertNotIn(rejected.observation_id, result.inverse_result.observation_ids)

    def test_cluster_members_remain_in_audit_but_never_become_scalar_equations(self):
        fixture = SyntheticProductionFixture()
        first, second = fixture.comparison.pairs[:2]
        second.abaqus_frequency_hz = first.abaqus_frequency_hz * 1.005
        second.experimental_frequency_hz = first.experimental_frequency_hz * 1.005
        with self.assertRaisesRegex(StageAIdentificationError, "No usable scalar"):
            fixture.identify(
                campaign_policy=StageACampaignPolicy(
                    cluster_relative_frequency_gap=0.99,
                    excluded_experimental_mode_ids=(),
                )
            )

        result = fixture.identify(
            requested_parameter_subset=("D11", "D66"),
            solver_configuration=fixture.configuration(global_max_iterations=20),
            campaign_policy=StageACampaignPolicy(
                cluster_relative_frequency_gap=0.01,
                excluded_experimental_mode_ids=(),
            ),
        )
        self.assertEqual(len(result.clusters), 1)
        cluster = result.clusters[0]
        self.assertEqual(cluster.reason, "cluster_requires_subspace_solver")
        self.assertIsNotNone(cluster.subspace_mac)
        self.assertTrue(set(cluster.observation_ids).issubset(
            {item.observation_id for item in result.observations}
        ))
        self.assertTrue(set(cluster.observation_ids).isdisjoint(result.inverse_result.observation_ids))
        self.assertEqual(result.effective_observation_count, 4)

    def test_rank_deficient_full_request_requires_approval_or_override(self):
        fixture = SyntheticProductionFixture(rank_deficient=True)
        with self.assertRaisesRegex(StageAIdentificationError, "not practically identifiable"):
            fixture.identify()

        approved = fixture.identify(
            campaign_policy=StageACampaignPolicy(approve_recommended_subset=True),
            solver_configuration=fixture.configuration(global_max_iterations=20),
        )
        self.assertNotEqual(approved.fitted_parameter_subset, approved.requested_parameter_subset)
        self.assertEqual(
            approved.fitted_parameter_subset, approved.recommended_parameter_subset
        )
        self.assertTrue(approved.metadata["recommended_subset_approved"])

        overridden = fixture.identify(
            solver_configuration=fixture.configuration(
                global_max_iterations=10,
                allow_non_identifiable_subset=True,
            )
        )
        self.assertEqual(overridden.fitted_parameter_subset, overridden.requested_parameter_subset)
        self.assertTrue(overridden.metadata["non_identifiable_override"])

    def test_pairing_failure_requires_explicit_fallback_and_records_it(self):
        fixture = SyntheticProductionFixture()

        def failing_provider(observations, eigenpairs):
            del observations, eigenpairs
            raise ComparatorPairingError("fixture pairing unavailable")

        with self.assertRaisesRegex(StageAIdentificationError, "pairing is unavailable"):
            fixture.identify(pairing_provider=failing_provider)

        fallback = fixture.identify(
            pairing_provider=failing_provider,
            requested_parameter_subset=("D11", "D66"),
            solver_configuration=fixture.configuration(global_max_iterations=20),
            campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
        )
        self.assertEqual(
            fallback.pairing_provider_mode, PairingProviderMode.FIXED_PAIR_FALLBACK
        )
        self.assertIn("fixture pairing unavailable", fallback.metadata["pairing_fallback_reason"])

    def test_all_excluded_and_invalid_policy_do_not_start_fit(self):
        fixture = SyntheticProductionFixture()
        for pair in fixture.comparison.pairs:
            pair.manual_decision = "rejected"
        with self.assertRaisesRegex(StageAIdentificationError, "No usable scalar"):
            fixture.identify(
                campaign_policy=StageACampaignPolicy(excluded_experimental_mode_ids=())
            )
        with self.assertRaisesRegex(ValueError, "explicit reason"):
            StageACampaignPolicy(
                excluded_experimental_mode_ids=(1,), excluded_mode_reason=""
            )

    def test_empty_comparison_and_invalid_parameter_configuration_fail_explicitly(self):
        empty = SyntheticProductionFixture()
        empty.comparison.pairs = []
        with self.assertRaisesRegex(StageAIdentificationError, "No usable scalar"):
            empty.identify()

        fixture = SyntheticProductionFixture()
        with self.assertRaisesRegex(StageAIdentificationError, "inverse solve failed"):
            fixture.identify(
                initial_parameters=StageAMatrixParameters(20.0, 2.4, 5.0),
                requested_parameter_subset=("D11", "D66"),
            )

    def test_changed_final_pairing_is_returned_as_explicit_failed_result(self):
        fixture = SyntheticProductionFixture()
        calls = 0

        def provider(observations, eigenpairs):
            nonlocal calls
            del eigenpairs
            calls += 1
            mode_ids = list(range(2, len(observations) + 2))
            if calls >= 4:
                mode_ids[0], mode_ids[1] = mode_ids[1], mode_ids[0]
            return PairingResult(
                assignments=tuple(
                    ModeAssignment(item.observation_id, mode_id, mac=0.99)
                    for item, mode_id in zip(observations, mode_ids)
                ),
                method="stateful integration provider",
            )

        fake_global_result = mock.Mock(
            success=True,
            message="synthetic global convergence",
            nfev=0,
            x=np.log([fixture.truth.D11, fixture.truth.D66]),
        )
        with mock.patch(
            "services.inverse_solver.optimize.differential_evolution",
            return_value=fake_global_result,
        ):
            result = fixture.identify(
                pairing_provider=provider,
                requested_parameter_subset=("D11", "D66"),
                initial_parameters=fixture.truth,
            )
        self.assertTrue(result.inverse_result.pairing_changed_at_optimum)
        self.assertFalse(result.inverse_result.success)
        self.assertTrue(any("Pairing changed" in item for item in result.warnings))


if __name__ == "__main__":
    unittest.main()
