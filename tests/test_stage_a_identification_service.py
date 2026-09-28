import copy
import dataclasses
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.registration import FrozenRegistration
from modal_core import ModalDataset, ModeShape, compare_modal_datasets
from scientific_state import calibration_fingerprint
from services.identifiability_service import ParameterPrecisionRequirement
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
    StageAMatrixNodeMap,
    StageAMatrixNodeMapError,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from services.specimen_comparison_service import comparison_to_observations
from services.stage_a_identification_service import (
    ComparatorPairingError,
    MatrixEigenmodeDatasetAdapter,
    PairingProviderMode,
    ProductionComparisonPairingProvider,
    StageACampaignPolicy,
    StageAFeAvailability,
    StageAFeAvailabilityError,
    StageAIdentificationError,
    build_stage_a_fe_availability,
    check_required_fe_availability,
    create_production_pairing_provider,
    identify_stage_a,
    precheck_required_fe_export,
    required_fe_components,
    stage_a_basis_identity,
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
        self.assertEqual(
            result.metadata["model_validation_evidence"]["status"],
            "NOT_VALIDATED_FOR_THIS_MODEL",
        )
        statuses = result.metadata["scientific_statuses"]
        self.assertEqual(statuses["optimizer_solver"]["status"], "PASS")
        self.assertEqual(
            statuses["fit_quality"]["status"],
            "NOT_ASSESSED_NO_DECLARED_ACCEPTANCE_THRESHOLD",
        )
        self.assertEqual(statuses["direct_fe_validation"]["status"], "NOT_RUN")
        self.assertEqual(statuses["hold_out_validation"]["status"], "NOT_RUN")
        self.assertEqual(
            statuses["material_identification_validation"]["status"],
            "NOT_VALIDATED",
        )
        caveat = result.metadata["mode_identity_caveat"]
        self.assertEqual(caveat["minimum_individual_mac"]["NB6"], 5.32e-4)
        self.assertEqual(caveat["minimum_individual_mac"]["NB8"], 0.01495)
        self.assertFalse(caveat["mac_thresholds_changed"])
        self.assertFalse(caveat["cluster_subspace_residual_implemented"])

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

    def test_precision_is_re_evaluated_at_fitted_optimum_when_declared(self):
        fixture = SyntheticProductionFixture()
        result = fixture.identify(
            campaign_policy=StageACampaignPolicy(
                precision_requirements={
                    name: ParameterPrecisionRequirement(
                        1.0e12, coordinate="physical"
                    )
                    for name in ("D11", "D12", "D66")
                }
            )
        )
        self.assertEqual(result.metadata["identifiability_evaluated_at"], "fitted_optimum")
        self.assertEqual(result.identifiability.precision_status, "PASS")
        self.assertTrue(result.identifiability.practically_precise_enough)
        self.assertEqual(
            result.metadata["scientific_statuses"]["identifiability_at_optimum"]["status"],
            "PASS",
        )

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
        with self.assertRaisesRegex(StageAIdentificationError, "not structurally identifiable"):
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

        global_vector = np.log([fixture.truth.D11, fixture.truth.D66])

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
            result = fixture.identify(
                pairing_provider=provider,
                requested_parameter_subset=("D11", "D66"),
                initial_parameters=fixture.truth,
            )
        self.assertTrue(result.inverse_result.pairing_changed_at_optimum)
        self.assertFalse(result.inverse_result.success)
        self.assertTrue(any("Pairing changed" in item for item in result.warnings))


class MappedAdapterFixture:
    """Two instances with overlapping labels, mapped explicitly from matrix nodes."""

    REFERENCE_IDS = ("PART-B:1", "PART-A:1", "PART-A:2")
    REFERENCE_COORDINATES = ((10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 5.0, 0.0))
    # Matrix node 101 carries U1+U3, 102 only U3, 103 only a rotation.
    DOFS = (
        AbaqusDof(101, 1),
        AbaqusDof(101, 3),
        AbaqusDof(102, 3),
        AbaqusDof(103, 4),
    )
    MAPPING = {101: "PART-A:1", 102: "PART-B:1", 103: "PART-A:2"}

    def reference(self, node_ids=REFERENCE_IDS):
        mode = ModeShape(
            number=1,
            frequency_hz=10.0,
            node_ids=np.asarray(node_ids, dtype=object),
            coordinates=np.asarray(self.REFERENCE_COORDINATES),
            vectors=np.zeros((len(node_ids), 3)),
        )
        mode.measured_dofs = np.ones((len(node_ids), 3), dtype=bool)
        return ModalDataset("Abaqus ODB", Path("reference.odb"), [mode])

    def eigenpairs(self, dofs=DOFS):
        vectors = np.arange(1.0, 1.0 + 2 * len(dofs)).reshape(len(dofs), 2)
        return GeneralizedEigenResult(
            eigenvalues=np.array([1.0, 4.0]),
            frequencies_hz=np.array([11.0, 22.0]),
            eigenvectors=vectors,
            dofs=tuple(dofs),
            rigid_body_eigenvalues=np.array([]),
        )

    def adapter(self, mapping=MAPPING, reference=None):
        return MatrixEigenmodeDatasetAdapter(
            reference or self.reference(),
            self.DOFS,
            node_map=StageAMatrixNodeMap.from_mapping(mapping),
        )


class MappedMatrixEigenmodeAdapterTests(MappedAdapterFixture, unittest.TestCase):
    """Explicit matrix-node -> INSTANCE:label mapping (multi-instance safe)."""

    # A / B
    def test_overlapping_labels_map_to_distinct_instance_nodes(self):
        candidate = self.adapter()(self.eigenpairs())
        mode = candidate.sorted_modes()[0]
        self.assertEqual(tuple(mode.node_ids.tolist()), self.REFERENCE_IDS)
        np.testing.assert_array_equal(mode.coordinates, self.REFERENCE_COORDINATES)
        by_id = dict(zip(mode.node_ids.tolist(), mode.vectors))
        # eigenvector rows: (101,1)=1, (101,3)=3, (102,3)=5 for the first mode
        np.testing.assert_array_equal(by_id["PART-A:1"], [1.0, 0.0, 3.0])
        np.testing.assert_array_equal(by_id["PART-B:1"], [0.0, 0.0, 5.0])
        np.testing.assert_array_equal(by_id["PART-A:2"], [0.0, 0.0, 0.0])
        self.assertEqual(
            candidate.metadata["stage_a_node_map_hash"],
            StageAMatrixNodeMap.from_mapping(self.MAPPING).content_hash,
        )

    # C
    def test_missing_map_entry_is_refused(self):
        with self.assertRaisesRegex(ComparatorPairingError, "no FE target"):
            MatrixEigenmodeDatasetAdapter(
                self.reference(),
                self.DOFS,
                node_map=StageAMatrixNodeMap.from_mapping({101: "PART-A:1", 102: "PART-B:1"}),
            )
        adapter = self.adapter()
        with self.assertRaisesRegex(ComparatorPairingError, "no FE target"):
            adapter(self.eigenpairs(self.DOFS + (AbaqusDof(104, 3),)))

    # D
    def test_duplicate_fe_target_is_refused(self):
        with self.assertRaises(StageAMatrixNodeMapError):
            self.adapter({101: "PART-A:1", 102: "PART-A:1", 103: "PART-A:2"})

    # E
    def test_unknown_target_fe_node_is_refused(self):
        with self.assertRaisesRegex(ComparatorPairingError, "not in the reference FE grid"):
            self.adapter({101: "PART-A:1", 102: "PART-C:1", 103: "PART-A:2"})

    def test_reference_grid_must_use_instance_qualified_ids(self):
        with self.assertRaisesRegex(ComparatorPairingError, "INSTANCE:label"):
            self.adapter(reference=self.reference(node_ids=(1, 2, 3)))

    # I
    def test_fe_availability_comes_from_matrix_active_dofs_only(self):
        candidate = self.adapter()(self.eigenpairs())
        for mode in candidate.modes:
            self.assertFalse(hasattr(mode, "measured_dofs"))
            self.assertNotIn("measured_dofs", mode.metadata)
            availability = dict(zip(mode.node_ids.tolist(), mode.metadata["fe_available_dofs"].tolist()))
            self.assertEqual(availability["PART-A:1"], [True, False, True])
            self.assertEqual(availability["PART-B:1"], [False, False, True])
            self.assertEqual(availability["PART-A:2"], [False, False, False])
            self.assertEqual(
                mode.metadata["fe_dof_availability_source"], "stage_a_matrix_active_dofs"
            )
        reduced = self.adapter()(self.eigenpairs(self.DOFS[1:]))
        first = dict(zip(reduced.modes[0].node_ids.tolist(), reduced.modes[0].metadata["fe_available_dofs"].tolist()))
        self.assertEqual(first["PART-A:1"], [False, False, True])

    # J
    def test_mapped_path_never_compares_labels_with_fe_ids(self):
        with mock.patch(
            "services.stage_a_identification_service._node_key",
            side_effect=AssertionError("label matching must not be used"),
        ):
            candidate = self.adapter()(self.eigenpairs())
        self.assertEqual(len(candidate.modes), 2)

    # K
    def test_legacy_unmapped_adapter_still_matches_exact_labels(self):
        reference = self.reference(node_ids=(1, 2, 3))
        dofs = (AbaqusDof(1, 3), AbaqusDof(2, 3))
        eigenpairs = GeneralizedEigenResult(
            eigenvalues=np.array([1.0]),
            frequencies_hz=np.array([5.0]),
            eigenvectors=np.array([[2.0], [3.0]]),
            dofs=dofs,
            rigid_body_eigenvalues=np.array([]),
        )
        candidate = MatrixEigenmodeDatasetAdapter(reference, dofs)(eigenpairs)
        np.testing.assert_array_equal(candidate.modes[0].vectors[:, 2], [2.0, 3.0, 0.0])
        self.assertNotIn("stage_a_node_map_hash", candidate.metadata)

    def test_production_provider_factory_forwards_the_basis_node_map(self):
        fixture = SyntheticProductionFixture()
        mapping = {int(node): f"PLATE-1:{int(node)}" for node in fixture.node_ids}
        node_map = StageAMatrixNodeMap.from_mapping(mapping)
        basis = replace(fixture.basis, node_map=node_map)
        comparison = copy.copy(fixture.comparison)
        comparison.abaqus = self._qualified(fixture.comparison.abaqus)
        provider = create_production_pairing_provider(comparison, basis, coordinate_scale_override=1.0)
        self.assertIs(provider.candidate_dataset_adapter.node_map, node_map)

    @staticmethod
    def _qualified(dataset):
        modes = []
        for mode in dataset.sorted_modes():
            modes.append(
                ModeShape(
                    number=mode.number,
                    frequency_hz=mode.frequency_hz,
                    node_ids=np.asarray([f"PLATE-1:{int(item)}" for item in mode.node_ids], dtype=object),
                    coordinates=mode.coordinates,
                    vectors=mode.vectors,
                )
            )
        return ModalDataset(dataset.source_name, dataset.source_path, modes)


def _registration(
    rotation,
    measured,
    *,
    experimental_node_ids=(1,),
    mapped_fe_node_ids=("PART-A:1",),
):
    calibration = {"mode": "manual", "manual_scale": 1.0}
    return FrozenRegistration.create(
        experimental_source_identity={"path": "exp.unv", "size": 1, "mtime_ns": 1, "sha256": "a" * 64},
        experimental_modal_set_identity=None,
        fe_geometry_identity={"schema_version": "fe-geometry-identity/2", "sha256": "b" * 64},
        calibration=calibration,
        calibration_fingerprint=calibration_fingerprint(calibration),
        orientation_candidate_id="geometry-0000000000000000",
        rotation=rotation,
        translation=[0.0, 0.0, 0.0],
        coordinate_scales=[1.0, 1.0, 1.0],
        experimental_node_ids=list(experimental_node_ids),
        mapped_fe_node_ids=list(mapped_fe_node_ids),
        measured_dof_contract=measured,
        registration_metrics={},
    )


ONLY_U3 = [[False, False, True]]
# exp = fe @ R ; this signed permutation sends FE U1 -> experimental U3.
FE_U1_TO_EXP_U3 = [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]


class StageAFeAvailabilityContractTests(unittest.TestCase):
    IDS = ("PART-B:1", "PART-A:1", "PART-A:2")
    MASK = [[False, False, True], [True, False, True], [False, False, False]]

    def contract(self, ids=IDS, mask=MASK, node_map_hash="c" * 64):
        return StageAFeAvailability(
            fe_node_ids=ids, available=mask, node_map_hash=node_map_hash
        )

    # A
    def test_contract_is_immutable_detached_and_hashed(self):
        mask = np.asarray(self.MASK, dtype=bool)
        ids = list(self.IDS)
        contract = self.contract(ids=ids, mask=mask)
        before = contract.content_hash
        mask[0, 0] = True
        ids[0] = "PART-Z:9"
        self.assertEqual(contract.content_hash, before)
        self.assertEqual(contract.fe_node_ids, self.IDS)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            contract.node_map_hash = "d" * 64
        self.assertEqual(contract.source, "stage_a_matrix_active_dofs")
        self.assertRegex(before, r"^[0-9a-f]{64}$")
        array = contract.mask_array()
        array[:] = True
        self.assertEqual(contract.content_hash, before)

    def test_hash_is_stable_and_sensitive(self):
        base = self.contract()
        order = [2, 0, 1]
        reordered = self.contract(
            ids=tuple(self.IDS[i] for i in order), mask=[self.MASK[i] for i in order]
        )
        self.assertEqual(base.content_hash, reordered.content_hash)
        changed_mask = [list(row) for row in self.MASK]
        changed_mask[2][0] = True
        self.assertNotEqual(base.content_hash, self.contract(mask=changed_mask).content_hash)
        changed_ids = ("PART-B:1", "PART-A:1", "PART-A:3")
        self.assertNotEqual(base.content_hash, self.contract(ids=changed_ids).content_hash)
        self.assertNotEqual(
            base.content_hash, self.contract(node_map_hash="d" * 64).content_hash
        )

    def test_malformed_contracts_are_refused(self):
        invalid = {
            "duplicate id": dict(ids=("PART-A:1", "PART-A:1", "PART-A:2")),
            "unqualified id": dict(ids=(1, "PART-A:1", "PART-A:2")),
            "no instance": dict(ids=("1", "PART-A:1", "PART-A:2")),
            "mask shape": dict(mask=[[True, True]] * 3),
            "mask rows": dict(mask=self.MASK[:2]),
            "mask type": dict(mask=np.ones((3, 3), dtype=int)),
            "node map hash": dict(node_map_hash="short"),
        }
        for name, change in invalid.items():
            with self.subTest(name):
                with self.assertRaises(StageAFeAvailabilityError):
                    self.contract(**change)
        with self.assertRaises(StageAFeAvailabilityError):
            StageAFeAvailability(
                fe_node_ids=self.IDS, available=self.MASK, node_map_hash="c" * 64, source="odb_all_true"
            )


class StageAFeAvailabilityDerivationTests(MappedAdapterFixture, unittest.TestCase):
    # B
    def test_availability_comes_from_active_dofs_not_values(self):
        node_map = StageAMatrixNodeMap.from_mapping(self.MAPPING)
        availability = build_stage_a_fe_availability(self.REFERENCE_IDS, node_map, self.DOFS)
        self.assertEqual(availability.fe_node_ids, self.REFERENCE_IDS)
        self.assertEqual(availability.available_components("PART-A:1"), (True, False, True))
        self.assertEqual(availability.available_components("PART-B:1"), (False, False, True))
        self.assertEqual(availability.available_components("PART-A:2"), (False, False, False))
        self.assertEqual(availability.node_map_hash, node_map.content_hash)  # M
        zero_valued = GeneralizedEigenResult(
            eigenvalues=np.array([1.0]),
            frequencies_hz=np.array([11.0]),
            eigenvectors=np.zeros((len(self.DOFS), 1)),
            dofs=self.DOFS,
            rigid_body_eigenvalues=np.array([]),
        )
        candidate = self.adapter()(zero_valued)
        self.assertEqual(candidate.metadata["stage_a_fe_availability"], availability)

    def test_adapter_metadata_is_derived_from_the_contract(self):
        candidate = self.adapter()(self.eigenpairs())
        contract = candidate.metadata["stage_a_fe_availability"]
        self.assertIsInstance(contract, StageAFeAvailability)
        self.assertEqual(candidate.metadata["stage_a_fe_availability_hash"], contract.content_hash)
        for mode in candidate.modes:
            np.testing.assert_array_equal(mode.metadata["fe_available_dofs"], contract.mask_array())

    # C
    def test_reference_or_experimental_masks_are_never_copied(self):
        reference = self.reference()
        reference.modes[0].measured_dofs = np.zeros((3, 3), dtype=bool)
        first = self.adapter(reference=reference)(self.eigenpairs())
        reference.modes[0].measured_dofs = np.ones((3, 3), dtype=bool)
        second = self.adapter(reference=reference)(self.eigenpairs())
        self.assertEqual(
            first.metadata["stage_a_fe_availability"], second.metadata["stage_a_fe_availability"]
        )

    def test_unmapped_dof_or_unknown_target_is_refused(self):
        node_map = StageAMatrixNodeMap.from_mapping({101: "PART-A:1", 102: "PART-B:1"})
        with self.assertRaisesRegex(StageAFeAvailabilityError, "no FE target"):
            build_stage_a_fe_availability(self.REFERENCE_IDS, node_map, self.DOFS)
        node_map = StageAMatrixNodeMap.from_mapping({101: "PART-A:1", 102: "PART-C:1", 103: "PART-A:2"})
        with self.assertRaisesRegex(StageAFeAvailabilityError, "not in the reference FE grid"):
            build_stage_a_fe_availability(self.REFERENCE_IDS, node_map, self.DOFS)


class StageARequiredFeComponentsTests(unittest.TestCase):
    # D
    def test_signed_permutation_requires_single_fe_component(self):
        required = required_fe_components(_registration(FE_U1_TO_EXP_U3, ONLY_U3))
        self.assertEqual(required, {"PART-A:1": (True, False, False)})

    def test_identity_rotation_requires_same_component(self):
        required = required_fe_components(_registration(np.eye(3), ONLY_U3))
        self.assertEqual(required, {"PART-A:1": (False, False, True)})

    # E
    def test_tilted_rotation_requires_every_contributing_component(self):
        angle = 0.3
        tilted = [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(angle), -np.sin(angle)],
            [0.0, np.sin(angle), np.cos(angle)],
        ]
        required = required_fe_components(_registration(tilted, ONLY_U3))
        self.assertEqual(required, {"PART-A:1": (False, True, True)})

    # F
    def test_tiny_nonzero_coefficient_is_conservatively_required(self):
        epsilon = 1.0e-9
        nearly_identity = [
            [1.0, 0.0, epsilon],
            [0.0, 1.0, 0.0],
            [-epsilon, 0.0, 1.0],
        ]
        registration = _registration(nearly_identity, ONLY_U3)
        self.assertNotEqual(registration.rotation[0][2], 0.0)
        self.assertEqual(
            required_fe_components(registration), {"PART-A:1": (True, False, True)}
        )

    # J
    def test_requirements_accumulate_over_experimental_nodes(self):
        registration = _registration(
            np.eye(3),
            [[False, False, True], [True, False, False], [False, True, False]],
            experimental_node_ids=(1, 2, 3),
            mapped_fe_node_ids=("PART-A:1", "PART-A:1", "PART-B:1"),
        )
        self.assertEqual(
            required_fe_components(registration),
            {"PART-A:1": (True, False, True), "PART-B:1": (False, True, False)},
        )

    def test_nodes_without_measured_components_require_nothing(self):
        registration = _registration(
            np.eye(3),
            [[False, False, True], [False, False, False]],
            experimental_node_ids=(1, 2),
            mapped_fe_node_ids=("PART-A:1", "PART-B:1"),
        )
        self.assertEqual(required_fe_components(registration), {"PART-A:1": (False, False, True)})


class StageAPolicyBCheckTests(unittest.TestCase):
    IDS = ("PART-A:1", "PART-B:1")

    def availability(self, mask, node_map_hash="c" * 64, ids=IDS):
        return StageAFeAvailability(fe_node_ids=ids, available=mask, node_map_hash=node_map_hash)

    # G
    def test_all_required_components_available_passes(self):
        registration = _registration(FE_U1_TO_EXP_U3, ONLY_U3)
        availability = self.availability([[True, False, False], [False, False, False]])
        self.assertTrue(check_required_fe_availability(registration, availability))

    # H
    def test_unavailable_required_component_is_refused_with_node_and_component(self):
        registration = _registration(np.eye(3), ONLY_U3)
        availability = self.availability([[True, True, False], [True, True, True]])
        with self.assertRaises(StageAFeAvailabilityError) as context:
            check_required_fe_availability(registration, availability)
        message = str(context.exception)
        self.assertIn("PART-A:1", message)
        self.assertIn("U3", message)
        self.assertIn("UNAVAILABLE", message)
        self.assertEqual(
            context.exception.violations,
            (("PART-A:1", "U3", "not active in the matrix eigenvector DOFs"),),
        )

    def test_required_node_absent_from_contract_is_refused(self):
        registration = _registration(
            np.eye(3), ONLY_U3, mapped_fe_node_ids=("PART-C:1",)
        )
        availability = self.availability([[True] * 3, [True] * 3])
        with self.assertRaisesRegex(StageAFeAvailabilityError, "PART-C:1.*absent"):
            check_required_fe_availability(registration, availability)

    # I
    def test_missing_non_required_component_does_not_block(self):
        registration = _registration(np.eye(3), ONLY_U3)
        availability = self.availability([[False, False, True], [False, False, False]])
        self.assertTrue(check_required_fe_availability(registration, availability))

    # K / L
    def test_numeric_zero_in_candidate_vector_cannot_satisfy_availability(self):
        reference = MappedAdapterFixture().reference()
        dofs = (AbaqusDof(101, 1), AbaqusDof(102, 3), AbaqusDof(103, 3))
        node_map = StageAMatrixNodeMap.from_mapping(
            {101: "PART-A:1", 102: "PART-B:1", 103: "PART-A:2"}
        )
        candidate = MatrixEigenmodeDatasetAdapter(reference, dofs, node_map=node_map)(
            GeneralizedEigenResult(
                eigenvalues=np.array([1.0]),
                frequencies_hz=np.array([11.0]),
                eigenvectors=np.array([[1.0], [2.0], [3.0]]),
                dofs=dofs,
                rigid_body_eigenvalues=np.array([]),
            )
        )
        mode = candidate.modes[0]
        row = mode.node_ids.tolist().index("PART-A:1")
        self.assertEqual(mode.vectors[row, 2], 0.0)  # zero-filled, not measured data
        self.assertTrue(np.all(np.isfinite(mode.vectors)))  # no NaN workaround
        registration = _registration(np.eye(3), ONLY_U3)
        with self.assertRaisesRegex(StageAFeAvailabilityError, "PART-A:1.*U3"):
            check_required_fe_availability(
                registration, candidate.metadata["stage_a_fe_availability"], node_map=node_map
            )

    # M
    def test_node_map_provenance_must_match(self):
        registration = _registration(np.eye(3), ONLY_U3)
        availability = self.availability([[True] * 3, [True] * 3], node_map_hash="c" * 64)
        other_map = StageAMatrixNodeMap.from_mapping({1: "PART-A:1"})
        with self.assertRaisesRegex(StageAFeAvailabilityError, "node map"):
            check_required_fe_availability(registration, availability, node_map=other_map)

    def test_malformed_arguments_are_refused(self):
        registration = _registration(np.eye(3), ONLY_U3)
        with self.assertRaises(StageAFeAvailabilityError):
            check_required_fe_availability(registration, {"PART-A:1": (True, True, True)})
        with self.assertRaises(StageAFeAvailabilityError):
            check_required_fe_availability(
                {"measured": True}, self.availability([[True] * 3, [True] * 3])
            )

    def test_measured_contract_is_not_mutated(self):
        registration = _registration(np.eye(3), ONLY_U3)
        before = registration.to_dict()
        with self.assertRaises(StageAFeAvailabilityError):
            check_required_fe_availability(
                registration, self.availability([[False] * 3, [False] * 3])
            )
        self.assertEqual(registration.to_dict(), before)


class StageAExportPrecheckTests(unittest.TestCase):
    def test_export_precheck_refuses_required_dof_that_was_never_exported(self):
        node_map = StageAMatrixNodeMap.from_mapping({101: "PART-A:1"})
        exported = (AbaqusDof(101, 1), AbaqusDof(101, 2))
        registration = _registration(np.eye(3), ONLY_U3)
        with self.assertRaisesRegex(StageAFeAvailabilityError, "PART-A:1.*U3.*not exported"):
            precheck_required_fe_export(registration, node_map, exported)
        self.assertTrue(
            precheck_required_fe_export(
                registration, node_map, exported + (AbaqusDof(101, 3),)
            )
        )


class StageABasisIdentityVersioningTests(unittest.TestCase):
    # G
    def test_unmapped_identity_is_unchanged_and_mapped_identity_is_versioned(self):
        fixture = SyntheticProductionFixture()
        legacy = stage_a_basis_identity(fixture.basis)
        expected_dofs = hashlib.sha256()
        for dof in fixture.basis.dofs:
            expected_dofs.update(f"{dof.node_label!r}:{dof.dof}\n".encode("utf-8"))
        self.assertEqual(set(legacy), {"basis_km_hash", "dof_mapping_hash"})
        self.assertEqual(legacy["dof_mapping_hash"], expected_dofs.hexdigest())

        mapping = {int(node): f"PLATE-1:{int(node)}" for node in fixture.node_ids}
        mapped = stage_a_basis_identity(
            replace(fixture.basis, node_map=StageAMatrixNodeMap.from_mapping(mapping))
        )
        self.assertEqual(mapped["basis_km_hash"], legacy["basis_km_hash"])
        self.assertNotEqual(mapped["dof_mapping_hash"], legacy["dof_mapping_hash"])
        self.assertEqual(mapped["dof_mapping_schema"], "stage-a-dof-mapping/2")
        self.assertEqual(
            mapped["node_map_hash"], StageAMatrixNodeMap.from_mapping(mapping).content_hash
        )

        other = dict(mapping)
        other[1] = "PLATE-2:1"
        changed = stage_a_basis_identity(
            replace(fixture.basis, node_map=StageAMatrixNodeMap.from_mapping(other))
        )
        self.assertNotEqual(changed["dof_mapping_hash"], mapped["dof_mapping_hash"])
        self.assertNotEqual(changed["node_map_hash"], mapped["node_map_hash"])


if __name__ == "__main__":
    unittest.main()
