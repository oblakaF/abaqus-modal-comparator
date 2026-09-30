import dataclasses
from dataclasses import replace
import hashlib
import inspect
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coordinate_calibration import CoordinateCalibration
from domain.registration import FrozenRegistration
from modal_core import ModalDataset, ModeShape, compare_modal_datasets
from registration_factory import build_frozen_registration
from reviewed_core import GeometryOrientationAmbiguousError, _candidate_summary
from scientific_state import (
    calibration_fingerprint,
    experimental_source_content_identity,
    modal_dataset_geometry_identity,
    source_identity_matches,
)
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
    MacEvidencePairingError,
    MatrixEigenmodeDatasetAdapter,
    PairingProviderMode,
    ProductionComparisonPairingProvider,
    StageACampaignPolicy,
    StageAFeAvailability,
    StageAFeAvailabilityError,
    StageAIdentificationError,
    StageAProductionPairingRefusal,
    build_stage_a_fe_availability,
    check_required_fe_availability,
    create_production_pairing_provider,
    identify_stage_a,
    precheck_required_fe_export,
    required_fe_components,
    stage_a_basis_identity,
)
from services import stage_a_identification_service as stage_a_service


# Real experimental source files, so content identity (SHA-256) is checked
# exactly as in production.
_SOURCE_DIRECTORY = tempfile.TemporaryDirectory(prefix="stage-a-sources-")


def tearDownModule():
    _SOURCE_DIRECTORY.cleanup()


class SyntheticProductionFixture:
    """Synthetic plate in the frozen production contract.

    FE nodes are ``PLATE-1:<label>``, matrix labels map to them through an
    explicit node map, the experiment measures U3 only, and the registration
    is frozen from the reference comparison by the real registration factory.
    """

    INSTANCE = "PLATE-1"

    def __init__(
        self,
        *,
        rank_deficient=False,
        mass_dependent=False,
        experimental_order=None,
        unmeasured_experimental_rows=(),
    ):
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
        self.fe_node_ids = np.asarray(
            [f"{self.INSTANCE}:{int(item)}" for item in self.node_ids], dtype=object
        )
        self.node_map = StageAMatrixNodeMap.from_mapping(
            dict(zip((int(item) for item in self.node_ids), self.fe_node_ids.tolist()))
        )
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
            node_map=self.node_map,
        )
        truth_modes = solve_generalized_eigenproblem(
            reference,
            self.basis.reconstruct_mass(self.truth),
            8,
            expected_rigid_body_modes=3,
            dofs=self.dofs,
        )
        abaqus_modes = [
            self._mode(
                index + 1,
                truth_modes.frequencies_hz[index],
                truth_modes.eigenvectors[:, index],
                self.fe_node_ids,
            )
            for index in range(8)
        ]
        order = tuple(range(6)) if experimental_order is None else tuple(experimental_order)
        measured = np.zeros((len(self.node_ids), 3), dtype=bool)
        measured[:, 2] = True
        measured[list(unmeasured_experimental_rows), :] = False
        experimental_modes = []
        for number, index in enumerate(order, start=1):
            mode = self._mode(
                number,
                truth_modes.frequencies_hz[index],
                2.5 * truth_modes.eigenvectors[:, index],
                self.node_ids,
            )
            mode.measured_dofs = measured.copy()
            experimental_modes.append(mode)
        handle, name = tempfile.mkstemp(suffix=".unv", dir=_SOURCE_DIRECTORY.name)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(f"synthetic experiment {order} {truth_modes.frequencies_hz.tolist()}\n")
        self.source_path = Path(name)
        self.calibration = CoordinateCalibration(mode="manual", manual_scale=1.0)
        self.comparison = compare_modal_datasets(
            ModalDataset("Abaqus", Path("synthetic.odb"), abaqus_modes),
            ModalDataset("Experiment", self.source_path, experimental_modes),
            geometry_calibration=self.calibration,
        )
        self.registration = build_frozen_registration(
            self.comparison, calibration=self.calibration
        )
        self.bounds = StageAParameterBounds(
            D11=(8.0, 16.0),
            D66=(3.0, 8.0),
            coupling_ratio=(0.05, 0.35),
        )

    def _mode(self, number, frequency, values, node_ids):
        vectors = np.zeros((len(self.node_ids), 3), dtype=float)
        vectors[:, 2] = values
        return ModeShape(
            number=number,
            frequency_hz=float(frequency),
            node_ids=node_ids,
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
        if "pairing_provider" not in changes:
            # Default production pairing runs under the frozen registration.
            values["registration"] = self.registration
        values.update(changes)
        return identify_stage_a(**values)

    def eigenpairs(self, parameters=None):
        parameters = self.truth if parameters is None else parameters
        return solve_generalized_eigenproblem(
            self.basis.reconstruct_stiffness(parameters),
            self.basis.reconstruct_mass(parameters),
            8,
            expected_rigid_body_modes=3,
            dofs=self.dofs,
        )

    def provider(self, **changes):
        values = dict(registration=self.registration)
        values.update(changes)
        return create_production_pairing_provider(self.comparison, self.basis, **values)

    def observations(self):
        return comparison_to_observations(
            self.comparison, "synthetic-design", "SP-SYNTHETIC", "run-1"
        )


class ProductionPairingProviderTests(unittest.TestCase):
    def test_comparator_pairing_and_mac_are_adapted_verbatim(self):
        # Experimental modes 2 and 3 are swapped, so the comparator's
        # assignment is not the identity and must be copied, not assumed.
        fixture = SyntheticProductionFixture(experimental_order=(0, 2, 1, 3, 4, 5))
        observations = fixture.observations()
        provider = fixture.provider()
        pairing = provider(observations, fixture.eigenpairs())
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
        self.assertTrue(
            any(
                pair.abaqus_mode != pair.experimental_mode
                for pair in provider.last_comparison.pairs
            )
        )
        self.assertEqual(pairing.method, "existing reviewed modal comparator")


class StageAIdentificationOrchestrationTests(unittest.TestCase):
    def test_end_to_end_comparison_to_identifiability_to_solver_recovers_truth(self):
        fixture = SyntheticProductionFixture()
        provider = fixture.provider()
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
        provider = fixture.provider()
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

        # Rank deficiency is a hard block: the override no longer reaches it.
        with self.assertRaisesRegex(StageAIdentificationError, "rank deficient.*hard block"):
            fixture.identify(
                solver_configuration=fixture.configuration(
                    global_max_iterations=10,
                    allow_non_identifiable_subset=True,
                )
            )

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
        provider = fixture.provider()
        self.assertIs(provider.candidate_dataset_adapter.node_map, fixture.basis.node_map)
        self.assertEqual(provider.node_map_hash, fixture.node_map.content_hash)


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
        legacy = stage_a_basis_identity(replace(fixture.basis, node_map=None))
        expected_dofs = hashlib.sha256()
        for dof in fixture.basis.dofs:
            expected_dofs.update(f"{dof.node_label!r}:{dof.dof}\n".encode("utf-8"))
        self.assertEqual(set(legacy), {"basis_km_hash", "dof_mapping_hash"})
        self.assertEqual(legacy["dof_mapping_hash"], expected_dofs.hexdigest())

        mapping = {int(node): f"PLATE-1:{int(node)}" for node in fixture.node_ids}
        mapped = stage_a_basis_identity(
            replace(fixture.basis, node_map=StageAMatrixNodeMap.from_mapping(mapping))
        )
        self.assertEqual(stage_a_basis_identity(fixture.basis), mapped)
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



def _rebuilt_registration(registration, **changes):
    """Seal a new registration that differs from ``registration`` only in ``changes``."""
    fields = registration.to_dict()
    del fields["registration_hash"], fields["registration_schema_version"]
    fields.update(changes)
    return FrozenRegistration.create(**fields)


def _without_dof(eigenpairs, node_label, component=3):
    """The same solve with one DOF absent from the active eigenvector DOFs."""
    keep = [
        index
        for index, dof in enumerate(eigenpairs.dofs)
        if (dof.node_label, dof.dof) != (node_label, component)
    ]
    return GeneralizedEigenResult(
        eigenvalues=eigenpairs.eigenvalues,
        frequencies_hz=eigenpairs.frequencies_hz,
        eigenvectors=eigenpairs.eigenvectors[keep, :],
        dofs=tuple(eigenpairs.dofs[index] for index in keep),
        rigid_body_eigenvalues=eigenpairs.rigid_body_eigenvalues,
    )


class ComparatorSpy:
    """Record the keyword arguments and results of the real comparator."""

    def __init__(self, after_call=None):
        self.calls = []
        self.results = []
        self.after_call = after_call

    def __call__(self, *args, **kwargs):
        self.calls.append(kwargs)
        result = compare_modal_datasets(*args, **kwargs)
        self.results.append(result)
        if self.after_call is not None:
            self.after_call(len(self.calls))
        return result


class FrozenProductionPairingTests(unittest.TestCase):
    """Production pairing runs only under the FrozenRegistration."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = SyntheticProductionFixture()
        cls.observations = cls.fixture.observations()
        cls.eigenpairs = cls.fixture.eigenpairs()

    def assertRefused(self, contract, callable_, *args, **kwargs):
        with self.assertRaises(StageAProductionPairingRefusal) as context:
            callable_(*args, **kwargs)
        self.assertEqual(context.exception.contract, contract, str(context.exception))
        return context.exception

    # A
    def test_provider_refuses_missing_frozen_registration(self):
        fixture = self.fixture
        self.assertRefused(
            "registration", create_production_pairing_provider, fixture.comparison, fixture.basis
        )
        adapter = MatrixEigenmodeDatasetAdapter(
            fixture.comparison.abaqus, fixture.dofs, node_map=fixture.node_map
        )
        self.assertRefused(
            "registration", ProductionComparisonPairingProvider, fixture.comparison, adapter
        )
        self.assertRefused(
            "registration", fixture.provider, registration=fixture.registration.to_dict()
        )

    # B
    def test_provider_refuses_missing_explicit_node_map(self):
        fixture = self.fixture
        self.assertRefused(
            "node_map",
            create_production_pairing_provider,
            fixture.comparison,
            replace(fixture.basis, node_map=None),
            registration=fixture.registration,
        )
        legacy_adapter = MatrixEigenmodeDatasetAdapter(fixture.comparison.abaqus, fixture.dofs)

        class OdbDatasetAdapter:
            def __call__(self, eigenpairs):
                return fixture.comparison.abaqus

        for adapter in (legacy_adapter, OdbDatasetAdapter()):
            with self.subTest(type(adapter).__name__):
                self.assertRefused(
                    "node_map",
                    ProductionComparisonPairingProvider,
                    fixture.comparison,
                    adapter,
                    registration=fixture.registration,
                )

    # C
    def test_same_path_size_mtime_with_different_content_is_refused(self):
        fixture = self.fixture
        current = experimental_source_content_identity(fixture.source_path)
        forged = dict(current, sha256="0" * 64)
        self.assertTrue(source_identity_matches(forged, current))  # path-style "match"
        registration = build_frozen_registration(
            fixture.comparison,
            calibration=fixture.calibration,
            experimental_source_identity=forged,
        )
        self.assertRefused(
            "experimental_source_identity", fixture.provider, registration=registration
        )

    def test_unreadable_experimental_source_is_refused(self):
        fixture = SyntheticProductionFixture()
        os.remove(fixture.source_path)
        self.assertRefused("experimental_source_identity", fixture.provider)

    # D
    def test_fe_geometry_mismatch_is_refused(self):
        fixture = self.fixture
        geometry = dict(fixture.registration.fe_geometry_identity)
        geometry["sha256"] = "f" * 64
        registration = _rebuilt_registration(
            fixture.registration, fe_geometry_identity=geometry
        )
        self.assertRefused("fe_geometry_identity", fixture.provider, registration=registration)

    # E
    def test_required_dof_never_exported_is_refused_before_any_comparison(self):
        fixture = self.fixture
        # The experiment's U3 would need FE U1, which the basis never exports.
        registration = _rebuilt_registration(fixture.registration, rotation=FE_U1_TO_EXP_U3)
        spy = ComparatorSpy()
        refusal = self.assertRefused(
            "policy_b", fixture.provider, registration=registration, comparator=spy
        )
        self.assertIn("not exported", str(refusal))
        self.assertEqual(spy.calls, [])
        with mock.patch.object(
            stage_a_service, "solve_stage_a_inverse", side_effect=AssertionError("optimized")
        ) as solver:
            self.assertRefused(
                "policy_b",
                fixture.identify,
                registration=registration,
                campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
            )
        solver.assert_not_called()

    # F
    def test_inactive_required_component_is_refused(self):
        spy = ComparatorSpy()
        provider = self.fixture.provider(comparator=spy)
        refusal = self.assertRefused(
            "policy_b", provider, self.observations, _without_dof(self.eigenpairs, 5)
        )
        self.assertIn("PLATE-1:5", str(refusal))
        self.assertIn("U3", str(refusal))
        self.assertEqual(spy.calls, [])

    # G
    def test_policy_b_is_checked_on_every_call(self):
        provider = self.fixture.provider()
        other = self.fixture.eigenpairs(StageAMatrixParameters(10.0, 2.0, 6.0))
        with mock.patch.object(
            stage_a_service,
            "check_required_fe_availability",
            wraps=stage_a_service.check_required_fe_availability,
        ) as check:
            provider(self.observations, self.eigenpairs)
            provider(self.observations, other)
        self.assertEqual(check.call_count, 2)
        for call in check.call_args_list:
            self.assertIs(call.args[0], self.fixture.registration)
            self.assertIs(call.kwargs["node_map"], self.fixture.node_map)
        # A later candidate is checked afresh, not accepted from an earlier call.
        self.assertRefused(
            "policy_b", provider, self.observations, _without_dof(self.eigenpairs, 7)
        )

    # H
    def test_missing_non_required_component_does_not_block(self):
        provider = self.fixture.provider()
        pairing = provider(self.observations, self.eigenpairs)
        candidate = provider.candidate_dataset_adapter(self.eigenpairs)
        availability = candidate.metadata["stage_a_fe_availability"]
        self.assertFalse(availability.mask_array()[:, :2].any())  # U1/U2 never available
        self.assertEqual(len(pairing.assignments), len(self.observations))

        fixture = SyntheticProductionFixture(unmeasured_experimental_rows=(4,))
        self.assertEqual(fixture.registration.measured_dof_contract[4], (False, False, False))
        label = int(fixture.registration.mapped_fe_node_ids[4].rpartition(":")[2])
        observations = fixture.observations()
        pairing = fixture.provider()(observations, _without_dof(fixture.eigenpairs(), label))
        self.assertEqual(len(pairing.assignments), len(observations))

    # I / J / M
    def test_comparator_receives_frozen_calibration_and_orientation(self):
        spy = ComparatorSpy()
        registration = self.fixture.registration
        provider = self.fixture.provider(comparator=spy)
        pairing = provider(self.observations, self.eigenpairs)
        kwargs = spy.calls[-1]
        self.assertEqual(set(kwargs), {"geometry_calibration", "orientation_selection"})
        self.assertIsInstance(kwargs["geometry_calibration"], CoordinateCalibration)
        self.assertEqual(
            kwargs["geometry_calibration"],
            CoordinateCalibration.from_mapping(registration.calibration),
        )
        self.assertEqual(
            calibration_fingerprint(kwargs["geometry_calibration"].to_dict()),
            registration.calibration_fingerprint,
        )
        self.assertEqual(
            kwargs["orientation_selection"],
            {"candidate_id": registration.orientation_candidate_id},
        )
        result = spy.results[-1]
        self.assertEqual(
            _candidate_summary(result.geometry)["candidate_id"],
            registration.orientation_candidate_id,
        )
        self.assertEqual(result.metadata["orientation_source"], "user_confirmed")
        self.assertIs(provider.last_comparison, result)
        self.assertEqual(len(pairing.assignments), len(self.observations))

    # K
    def test_coordinate_scale_override_is_refused(self):
        spy = ComparatorSpy()
        for scale in (1.0, 2.0):
            with self.subTest(scale=scale):
                self.assertRefused(
                    "calibration",
                    self.fixture.provider,
                    coordinate_scale_override=scale,
                    comparator=spy,
                )
        self.assertEqual(spy.calls, [])

    def test_calibration_that_does_not_round_trip_is_refused(self):
        calibration = dict(self.fixture.registration.calibration, unexpected_field=1)
        registration = _rebuilt_registration(
            self.fixture.registration,
            calibration=calibration,
            calibration_fingerprint=calibration_fingerprint(calibration),
        )
        self.assertRefused("calibration", self.fixture.provider, registration=registration)

    def test_experimental_mask_differing_from_frozen_contract_is_refused(self):
        registration = _rebuilt_registration(
            self.fixture.registration,
            measured_dof_contract=[[True, False, True]] * len(self.fixture.node_ids),
        )
        self.assertRefused(
            "measured_dof_contract", self.fixture.provider, registration=registration
        )

    # L
    def test_comparator_candidate_fallback_is_refused(self):
        registration = _rebuilt_registration(
            self.fixture.registration, orientation_candidate_id="geometry-00000000deadbeef"
        )
        spy = ComparatorSpy()
        provider = self.fixture.provider(registration=registration, comparator=spy)
        refusal = self.assertRefused(
            "orientation_candidate_id", provider, self.observations, self.eigenpairs
        )
        # The real comparator fell back to the unique geometry and returned normally.
        self.assertEqual(len(spy.results), 1)
        self.assertEqual(spy.results[0].metadata["orientation_source"], "geometry_unique")
        self.assertIn("geometry-00000000deadbeef", str(refusal))
        self.assertIsNone(provider.last_comparison)

    def test_orientation_ambiguity_under_frozen_candidate_is_refused(self):
        def ambiguous(*args, **kwargs):
            raise GeometryOrientationAmbiguousError("2 candidates", [])

        provider = self.fixture.provider(comparator=ambiguous)
        self.assertRefused(
            "orientation_candidate_id", provider, self.observations, self.eigenpairs
        )

    def test_no_geometry_candidate_is_refused_and_never_falls_back(self):
        # The real comparator, left with no geometry-alignment candidate for
        # the frozen state, raises its plain RuntimeError.
        spy = ComparatorSpy()
        provider = self.fixture.provider(comparator=spy)
        with mock.patch(
            "reviewed_core.geometry_alignment_candidates", return_value=[]
        ), mock.patch.object(
            stage_a_service, "_fixed_pairing", wraps=stage_a_service._fixed_pairing
        ) as fixed:
            refusal = self.assertRefused(
                "orientation_candidate_id",
                self.fixture.identify,
                pairing_provider=provider,
                campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
            )
        fixed.assert_not_called()
        self.assertEqual(len(spy.calls), 1)
        self.assertIsInstance(refusal.__cause__, RuntimeError)
        self.assertEqual(
            str(refusal.__cause__), "No geometry-alignment candidates were generated."
        )

    # N
    def test_fe_geometry_identity_is_checked_on_every_call(self):
        provider = self.fixture.provider()
        with mock.patch.object(
            stage_a_service,
            "modal_dataset_geometry_identity",
            wraps=modal_dataset_geometry_identity,
        ) as identity:
            provider(self.observations, self.eigenpairs)
            provider(self.observations, self.eigenpairs)
        self.assertEqual(identity.call_count, 2)
        provider.candidate_dataset_adapter._coordinates[0, 0] += 1.0e-9
        self.assertRefused(
            "fe_geometry_identity", provider, self.observations, self.eigenpairs
        )

    # O
    def test_node_map_provenance_mismatch_is_refused(self):
        provider = self.fixture.provider()
        mapping = dict(self.fixture.node_map.entries)
        mapping[1], mapping[2] = mapping[2], mapping[1]
        provider.candidate_dataset_adapter.node_map = StageAMatrixNodeMap.from_mapping(mapping)
        self.assertRefused("node_map", provider, self.observations, self.eigenpairs)

    def test_unmapped_candidate_dof_is_a_node_map_refusal(self):
        provider = self.fixture.provider()
        eigenpairs = self.eigenpairs
        extra = GeneralizedEigenResult(
            eigenvalues=eigenpairs.eigenvalues,
            frequencies_hz=eigenpairs.frequencies_hz,
            eigenvectors=np.vstack((eigenpairs.eigenvectors, eigenpairs.eigenvectors[:1])),
            dofs=eigenpairs.dofs + (AbaqusDof(999, 3),),
            rigid_body_eigenvalues=eigenpairs.rigid_body_eigenvalues,
        )
        self.assertRefused("node_map", provider, self.observations, extra)

    # P
    def test_hard_refusal_never_uses_fixed_pair_fallback(self):
        fixture = self.fixture
        fallback = StageACampaignPolicy(allow_fixed_pair_fallback=True)
        real_solve = stage_a_service.solve_generalized_eigenproblem

        def solve_without_u3_of_node_5(*args, **kwargs):
            return _without_dof(real_solve(*args, **kwargs), 5)

        # Calls 1 and 2 are the initial pairing and the solver's initial
        # evaluation; call 3 is inside the optimizer's objective, which turns
        # ValueErrors into failed evaluations.
        def corrupt_geometry_after_second_call(count):
            if count == 2:
                provider.candidate_dataset_adapter._coordinates[0, 0] += 1.0

        spy = ComparatorSpy(after_call=corrupt_geometry_after_second_call)
        provider = fixture.provider(comparator=spy)
        cases = (
            ("missing registration", "registration", dict(registration=None), None),
            (
                "Policy B at initial pairing",
                "policy_b",
                {},
                solve_without_u3_of_node_5,
            ),
            (
                "FE geometry during optimization",
                "fe_geometry_identity",
                dict(pairing_provider=provider),
                None,
            ),
        )
        for name, contract, changes, solve in cases:
            with self.subTest(name), mock.patch.object(
                stage_a_service, "_fixed_pairing", wraps=stage_a_service._fixed_pairing
            ) as fixed, mock.patch.object(
                stage_a_service,
                "solve_generalized_eigenproblem",
                side_effect=solve or real_solve,
            ):
                self.assertRefused(
                    contract, fixture.identify, campaign_policy=fallback, **changes
                )
                fixed.assert_not_called()
        # The first refused optimizer evaluation stopped the identification.
        self.assertEqual(len(spy.calls), 2)
        self.assertEqual(provider.call_count, 3)

    # Q
    def test_ordinary_comparator_failure_may_still_fall_back(self):
        fixture = self.fixture

        def failing_comparator(*args, **kwargs):
            raise ValueError("ordinary comparator failure")

        provider = fixture.provider(comparator=failing_comparator)
        with self.assertRaisesRegex(StageAIdentificationError, "pairing is unavailable"):
            fixture.identify(pairing_provider=provider)
        result = fixture.identify(
            pairing_provider=provider,
            requested_parameter_subset=("D11", "D66"),
            solver_configuration=fixture.configuration(global_max_iterations=5),
            campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
        )
        self.assertEqual(result.pairing_provider_mode, PairingProviderMode.FIXED_PAIR_FALLBACK)
        self.assertIn("ordinary comparator failure", result.metadata["pairing_fallback_reason"])

    def test_other_runtime_errors_remain_ordinary_pairing_failures(self):
        # Only the comparator's exact no-candidate RuntimeError is a refusal.
        class OtherRuntimeError(RuntimeError):
            pass

        failures = (
            RuntimeError("ordinary comparator runtime failure"),
            OtherRuntimeError("No geometry-alignment candidates were generated."),
        )
        for failure in failures:
            with self.subTest(type(failure).__name__):

                def failing_comparator(*args, **kwargs):
                    raise failure

                provider = self.fixture.provider(comparator=failing_comparator)
                result = self.fixture.identify(
                    pairing_provider=provider,
                    requested_parameter_subset=("D11", "D66"),
                    solver_configuration=self.fixture.configuration(global_max_iterations=5),
                    campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
                )
                self.assertEqual(
                    result.pairing_provider_mode, PairingProviderMode.FIXED_PAIR_FALLBACK
                )
                self.assertIn(str(failure), result.metadata["pairing_fallback_reason"])

    # R
    def test_repeated_inverse_calls_use_the_same_frozen_state(self):
        spy = ComparatorSpy()
        provider = self.fixture.provider(comparator=spy)
        other = self.fixture.eigenpairs(StageAMatrixParameters(10.0, 2.0, 6.0))
        first = provider(self.observations, self.eigenpairs)
        second = provider(self.observations, other)
        self.assertEqual(len(first.assignments), len(second.assignments))
        self.assertEqual(spy.calls[0], spy.calls[1])
        self.assertIsNot(spy.calls[0]["orientation_selection"], provider.orientation_selection)
        self.assertEqual(
            {_candidate_summary(item.geometry)["candidate_id"] for item in spy.results},
            {self.fixture.registration.orientation_candidate_id},
        )
        self.assertEqual({item.geometry.coordinate_scale for item in spy.results}, {1.0})

    def test_default_identification_runs_under_the_frozen_registration(self):
        fixture = self.fixture
        result = fixture.identify(
            requested_parameter_subset=("D11", "D66"),
            solver_configuration=fixture.configuration(global_max_iterations=5),
        )
        self.assertEqual(result.pairing_provider_mode, PairingProviderMode.COMPARATOR)
        self.assertEqual(
            result.metadata["frozen_registration_hash"],
            fixture.registration.registration_hash,
        )
        self.assertGreater(result.metadata["pairing_provider_calls"], 1)

    def test_registration_cannot_be_combined_with_a_different_provider(self):
        def custom(observations, eigenpairs):
            raise AssertionError("not called")

        with self.assertRaisesRegex(StageAIdentificationError, "registration"):
            self.fixture.identify(
                pairing_provider=custom, registration=self.fixture.registration
            )



def _make_mac_less(pair):
    """What the comparator records for a frequency-only match."""
    pair.mac = None
    pair.status = "Frequency match"


class MacEvidencePolicyTests(unittest.TestCase):
    """D-FREQONLY: a pair without MAC never becomes an inverse-fit observation."""

    def quick_identify(self, fixture, **changes):
        values = dict(
            requested_parameter_subset=("D11", "D66"),
            solver_configuration=fixture.configuration(global_max_iterations=5),
        )
        values.update(changes)
        return fixture.identify(**values)

    @staticmethod
    def by_experimental_mode(result, mode):
        return next(item for item in result.observations if item.experimental_mode_id == mode)

    # A
    def test_observation_with_mac_is_fitted_as_before(self):
        fixture = SyntheticProductionFixture()
        result = self.quick_identify(fixture)
        for observation in result.observations:
            if observation.experimental_mode_id == 1:
                continue  # campaign exclusion
            self.assertIsNotNone(observation.mac)
            self.assertEqual(observation.inclusion_status.value, "included")
            self.assertNotIn("pre_mac_policy_inclusion_status", observation.metadata)
            self.assertIn(observation.observation_id, result.inverse_result.observation_ids)
        self.assertEqual(result.effective_observation_count, 5)

    # B / C / G
    def test_frequency_match_without_mac_is_excluded_but_kept_in_diagnostics(self):
        fixture = SyntheticProductionFixture()
        pair = fixture.comparison.pairs[2]
        _make_mac_less(pair)
        result = self.quick_identify(fixture)
        observation = self.by_experimental_mode(result, pair.experimental_mode)
        self.assertIsNone(observation.mac)
        self.assertEqual(observation.inclusion_status.value, "excluded")
        self.assertIn("MAC unavailable", observation.reason)
        self.assertIn("Frequency match", observation.reason)
        self.assertEqual(observation.metadata["pre_mac_policy_inclusion_status"], "included")
        self.assertNotIn(observation.observation_id, result.inverse_result.observation_ids)
        self.assertIn(
            observation.observation_id,
            {item.observation_id for item in result.excluded_observations},
        )
        self.assertEqual(result.effective_observation_count, 4)
        # G: the comparator result and the audit trail still carry the pair.
        self.assertIs(fixture.comparison.pairs[2], pair)
        self.assertIsNone(pair.mac)
        self.assertEqual(pair.status, "Frequency match")
        self.assertIsNone(observation.metadata["source_pair"]["mac"])

    def test_manual_acceptance_cannot_admit_a_mac_less_pair(self):
        fixture = SyntheticProductionFixture()
        pair = fixture.comparison.pairs[2]
        _make_mac_less(pair)
        pair.manual_decision = "accepted"
        result = self.quick_identify(fixture)
        observation = self.by_experimental_mode(result, pair.experimental_mode)
        self.assertEqual(observation.inclusion_status.value, "excluded")
        self.assertNotIn(observation.observation_id, result.inverse_result.observation_ids)

    # D
    def test_mixed_case_fits_exactly_the_mac_valid_observations(self):
        fixture = SyntheticProductionFixture()
        _make_mac_less(fixture.comparison.pairs[2])  # E3
        provider = fixture.provider()
        seen = []
        real_call = provider.__call__

        def recording_provider(observations, eigenpairs):
            seen.append(tuple(item.experimental_mode_id for item in observations))
            return real_call(observations, eigenpairs)

        result = self.quick_identify(
            fixture,
            pairing_provider=recording_provider,
            campaign_policy=StageACampaignPolicy(excluded_experimental_mode_ids=(1, 5, 6)),
        )
        fitted = {
            self.by_experimental_mode(result, mode).observation_id for mode in (2, 4)
        }
        self.assertEqual(set(result.inverse_result.observation_ids), fitted)
        self.assertEqual(result.effective_observation_count, 2)
        self.assertEqual(set(seen), {(2, 4)})

    # E
    def test_all_mac_less_fails_before_any_fit(self):
        fixture = SyntheticProductionFixture()
        for pair in fixture.comparison.pairs:
            _make_mac_less(pair)
        with mock.patch.object(
            stage_a_service, "solve_stage_a_inverse", side_effect=AssertionError("fitted")
        ) as solver, mock.patch.object(
            stage_a_service,
            "solve_generalized_eigenproblem",
            side_effect=AssertionError("solved"),
        ) as eigen, mock.patch.object(
            stage_a_service, "_fixed_pairing", side_effect=AssertionError("fixed pairs")
        ) as fixed:
            with self.assertRaisesRegex(StageAIdentificationError, "No usable scalar.*MAC"):
                self.quick_identify(
                    fixture,
                    campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
                )
        solver.assert_not_called()
        eigen.assert_not_called()
        fixed.assert_not_called()

    # F
    def test_numeric_zero_mac_is_not_treated_as_missing(self):
        fixture = SyntheticProductionFixture()
        observations = fixture.observations()
        zero = replace(observations[2], mac=0.0)
        missing = replace(observations[3], mac=None)
        policed = stage_a_service._apply_mac_evidence_policy((zero, missing))
        self.assertIs(policed[0], zero)
        self.assertEqual(policed[0].inclusion_status.value, "included")
        self.assertEqual(policed[1].inclusion_status.value, "excluded")

        pair = fixture.comparison.pairs[2]
        pair.mac = 0.0
        pair.manual_decision = "accepted"  # the existing upstream gate decides
        result = self.quick_identify(fixture)
        observation = self.by_experimental_mode(result, pair.experimental_mode)
        self.assertEqual(observation.mac, 0.0)
        self.assertEqual(observation.inclusion_status.value, "included")
        self.assertIn(observation.observation_id, result.inverse_result.observation_ids)

    def test_non_finite_mac_is_refused_by_the_existing_convention(self):
        fixture = SyntheticProductionFixture()
        fixture.comparison.pairs[2].mac = float("nan")
        with self.assertRaisesRegex(ValueError, "MAC must be between zero and one"):
            self.quick_identify(fixture)

    # H
    def test_fixed_pair_fallback_does_not_reintroduce_mac_less_observation(self):
        fixture = SyntheticProductionFixture()
        pair = fixture.comparison.pairs[2]
        _make_mac_less(pair)

        def failing_provider(observations, eigenpairs):
            raise ComparatorPairingError("fixture pairing unavailable")

        with mock.patch.object(
            stage_a_service, "_fixed_pairing", wraps=stage_a_service._fixed_pairing
        ) as fixed:
            result = self.quick_identify(
                fixture,
                pairing_provider=failing_provider,
                campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
            )
        self.assertEqual(result.pairing_provider_mode, PairingProviderMode.FIXED_PAIR_FALLBACK)
        fixed_modes = {item.experimental_mode_id for item in fixed.call_args.args[0]}
        self.assertNotIn(pair.experimental_mode, fixed_modes)
        observation = self.by_experimental_mode(result, pair.experimental_mode)
        self.assertNotIn(observation.observation_id, result.inverse_result.observation_ids)

    def test_production_re_pairing_without_mac_is_an_ordinary_pairing_failure(self):
        fixture = SyntheticProductionFixture()

        def mac_less_comparator(*args, **kwargs):
            result = compare_modal_datasets(*args, **kwargs)
            for pair in result.pairs:
                if pair.experimental_mode == 3:
                    _make_mac_less(pair)
            return result

        provider = fixture.provider(comparator=mac_less_comparator)
        with self.assertRaisesRegex(MacEvidencePairingError, "mode\\(s\\) 3 have no MAC"):
            provider(fixture.observations(), fixture.eigenpairs())
        self.assertIsNone(provider.last_comparison)
        self.assertEqual(provider.failure_count, 1)
        # Observations that do not involve the MAC-less pair still pair normally.
        others = tuple(
            item for item in fixture.observations() if item.experimental_mode_id != 3
        )
        pairing = provider(others, fixture.eigenpairs())
        self.assertTrue(all(item.mac is not None for item in pairing.assignments))



class MacLessComparator:
    """Real comparator whose pair for experimental mode 3 loses its MAC on chosen calls."""

    def __init__(self, mac_less_calls):
        self.mac_less_calls = set(mac_less_calls)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        result = compare_modal_datasets(*args, **kwargs)
        if self.calls in self.mac_less_calls:
            for pair in result.pairs:
                if pair.experimental_mode == 3:
                    _make_mac_less(pair)
        return result


class MacEvidencePairingTests(unittest.TestCase):
    """Production re-pairing without MAC: refuse initially, fail only the trial later."""

    def identify(self, fixture, provider, **changes):
        values = dict(
            pairing_provider=provider,
            requested_parameter_subset=("D11", "D66"),
            solver_configuration=fixture.configuration(global_max_iterations=5),
        )
        values.update(changes)
        return fixture.identify(**values)

    # A / B
    def test_initial_mac_less_pairing_is_refused_without_fixed_pairs(self):
        for allow_fallback in (True, False):
            with self.subTest(allow_fixed_pair_fallback=allow_fallback):
                fixture = SyntheticProductionFixture()
                provider = fixture.provider(comparator=MacLessComparator({1}))
                with mock.patch.object(
                    stage_a_service, "_fixed_pairing", wraps=stage_a_service._fixed_pairing
                ) as fixed, mock.patch.object(
                    stage_a_service,
                    "solve_stage_a_inverse",
                    side_effect=AssertionError("fitted"),
                ) as solver:
                    with self.assertRaisesRegex(
                        StageAIdentificationError, "no MAC evidence.*mode\\(s\\) 3"
                    ) as context:
                        self.identify(
                            fixture,
                            provider,
                            campaign_policy=StageACampaignPolicy(
                                allow_fixed_pair_fallback=allow_fallback
                            ),
                        )
                self.assertIsInstance(context.exception.__cause__, MacEvidencePairingError)
                self.assertEqual(fixed.call_count, 0)
                solver.assert_not_called()

    # C
    def test_mac_less_optimizer_trial_fails_only_that_evaluation(self):
        fixture = SyntheticProductionFixture()
        # Call 1 is the initial pairing and call 2 the solver's initial
        # evaluation; calls 3-5 are optimizer trial points.
        comparator = MacLessComparator({3, 4, 5})
        provider = fixture.provider(comparator=comparator)
        result = self.identify(fixture, provider)
        self.assertEqual(result.pairing_provider_mode, PairingProviderMode.COMPARATOR)
        self.assertGreater(comparator.calls, 5)  # optimization continued
        failed = [
            entry
            for entry in result.inverse_result.convergence_history
            if not entry.success and "no MAC" in (entry.message or "")
        ]
        self.assertEqual(len(failed), 3)
        self.assertTrue(all(entry.stage == "global" for entry in failed))
        self.assertEqual(provider.failure_count, 3)
        self.assertTrue(
            all(item.mac is not None for item in result.inverse_result.final_pairing.assignments)
        )
        self.assertIn(
            self.mode_observation_id(result, 3), result.inverse_result.observation_ids
        )

    @staticmethod
    def mode_observation_id(result, mode):
        return next(
            item.observation_id
            for item in result.observations
            if item.experimental_mode_id == mode
        )

    # D
    def test_ordinary_initial_pairing_failure_keeps_fixed_pair_fallback(self):
        fixture = SyntheticProductionFixture()

        def failing_comparator(*args, **kwargs):
            raise ValueError("ordinary comparator failure")

        provider = fixture.provider(comparator=failing_comparator)
        with mock.patch.object(
            stage_a_service, "_fixed_pairing", wraps=stage_a_service._fixed_pairing
        ) as fixed:
            result = self.identify(
                fixture,
                provider,
                campaign_policy=StageACampaignPolicy(allow_fixed_pair_fallback=True),
            )
        self.assertEqual(fixed.call_count, 1)
        self.assertEqual(result.pairing_provider_mode, PairingProviderMode.FIXED_PAIR_FALLBACK)


class IdentifiabilityOverridePolicyTests(unittest.TestCase):
    """Rank deficiency is a hard block; only full-rank conditioning may be overridden."""

    # Test-only thresholds that a full-rank fixture exceeds; defaults stay unchanged.
    TIGHT_CONDITION = dict(condition_warning_threshold=1.0 + 1e-9, collinearity_warning_threshold=1.0e6)
    TIGHT_GAMMA = dict(condition_warning_threshold=1.0e12, collinearity_warning_threshold=1.0 + 1e-9)

    def identify(self, fixture, *, allow_override=False, **changes):
        values = dict(
            solver_configuration=fixture.configuration(
                global_max_iterations=5, allow_non_identifiable_subset=allow_override
            ),
        )
        values.update(changes)
        return fixture.identify(**values)

    # A / B
    def test_rank_deficiency_is_refused_with_or_without_override(self):
        fixture = SyntheticProductionFixture(rank_deficient=True)
        for allow_override in (False, True):
            for policy in (
                StageACampaignPolicy(),
                StageACampaignPolicy(condition_warning_threshold=1.0e12, collinearity_warning_threshold=1.0e12),
            ):
                with self.subTest(allow_override=allow_override, policy=policy.condition_warning_threshold):
                    with mock.patch.object(
                        stage_a_service, "solve_stage_a_inverse", side_effect=AssertionError("fitted")
                    ) as solver:
                        with self.assertRaisesRegex(
                            StageAIdentificationError, "rank deficient \\(numerical rank 2 < 3.*hard block"
                        ):
                            self.identify(fixture, allow_override=allow_override, campaign_policy=policy)
                    solver.assert_not_called()

    # C / K
    def test_approved_recommended_subset_is_full_rank_even_when_request_is_deficient(self):
        fixture = SyntheticProductionFixture(rank_deficient=True)
        result = self.identify(
            fixture,
            allow_override=True,
            campaign_policy=StageACampaignPolicy(approve_recommended_subset=True),
        )
        self.assertEqual(result.metadata["subset_selection"], "explicitly_approved_recommended_subset")
        self.assertEqual(result.fitted_parameter_subset, result.recommended_parameter_subset)
        self.assertFalse(result.metadata["non_identifiable_override"])
        self.assertIsNone(result.metadata["identifiability_override"])
        self.assertEqual(result.identifiability.rank, len(result.fitted_parameter_subset))

    def test_rank_deficient_selected_subset_is_refused_by_the_final_guard(self):
        deficient = SimpleNamespace(parameter_ids=("D11", "D66"), rank=1)
        identifiability = SimpleNamespace(
            parameter_ids=("D11", "D12", "D66"), rank=2, subset_ranking=(deficient,)
        )
        for subset in (("D11", "D12", "D66"), ("D11", "D66"), ("D12",)):
            with self.subTest(subset=subset):
                with self.assertRaisesRegex(StageAIdentificationError, "rank deficient.*hard block"):
                    stage_a_service._require_full_rank_subset(identifiability, subset)

    # D
    def test_full_rank_well_conditioned_subset_passes_without_override(self):
        fixture = SyntheticProductionFixture()
        result = self.identify(fixture)
        self.assertEqual(result.metadata["subset_selection"], "requested_subset_identifiable")
        self.assertIsNone(result.metadata["identifiability_override"])
        self.assertFalse(result.metadata["non_identifiable_override"])

    # E / F / G / H / I
    def test_full_rank_conditioning_limits_refuse_by_default_and_yield_to_override(self):
        cases = (
            ("condition_number", self.TIGHT_CONDITION, "condition_number", "condition_warning_threshold"),
            ("collinearity_gamma", self.TIGHT_GAMMA, None, "collinearity_warning_threshold"),
        )
        for criterion, thresholds, metadata_key, threshold_name in cases:
            with self.subTest(criterion):
                fixture = SyntheticProductionFixture()
                policy = StageACampaignPolicy(**thresholds)
                with self.assertRaisesRegex(
                    StageAIdentificationError, "not structurally identifiable or directionally separable"
                ):
                    self.identify(fixture, campaign_policy=policy)

                result = self.identify(fixture, allow_override=True, campaign_policy=policy)
                self.assertEqual(result.fitted_parameter_subset, ("D11", "D12", "D66"))
                self.assertEqual(result.metadata["subset_selection"], "explicit_non_identifiable_override")
                self.assertTrue(result.metadata["non_identifiable_override"])
                provenance = result.metadata["identifiability_override"]
                self.assertEqual(provenance["override"], "full_rank_conditioning")
                self.assertEqual(provenance["numerical_rank"], 3)
                self.assertEqual(provenance["fitted_parameter_subset"], ("D11", "D12", "D66"))
                by_name = {item["criterion"]: item for item in provenance["overridden_criteria"]}
                self.assertEqual(set(by_name), {criterion})
                self.assertEqual(by_name[criterion]["threshold"], thresholds[threshold_name])
                self.assertGreater(by_name[criterion]["value"], by_name[criterion]["threshold"])
                if metadata_key is not None:
                    self.assertEqual(
                        by_name[criterion]["value"],
                        result.metadata["initial_identifiability"][metadata_key],
                    )

    # J
    def test_numerical_thresholds_are_unchanged(self):
        policy = StageACampaignPolicy()
        self.assertEqual(policy.condition_warning_threshold, 100.0)
        self.assertEqual(policy.collinearity_warning_threshold, 20.0)
        from services import identifiability_service

        parameters = inspect.signature(identifiability_service.analyze_identifiability).parameters
        self.assertEqual(parameters["condition_warning_threshold"].default, 100.0)
        self.assertEqual(parameters["collinearity_warning_threshold"].default, 20.0)
        self.assertIsNone(parameters["rcond"].default)


class _InverseReached(Exception):
    """Sentinel: the initial scientific sensitivity was accepted."""


def _fixed_provider(mode_ids):
    def provider(observations, eigenpairs):
        del eigenpairs
        return PairingResult(
            assignments=tuple(
                ModeAssignment(item.observation_id, mode_id, mac=0.99)
                for item, mode_id in zip(observations, mode_ids)
            ),
            method="fixed integration provider",
        )

    return provider


class ObservedModeSensitivityContractTests(unittest.TestCase):
    """Stage A requests exactly its paired FE modes from the sensitivity service."""

    def tied_fixture(self, parameters):
        """FE elastic modes 3 and 4 form an exact doublet at ``parameters`` only."""

        fixture = SyntheticProductionFixture()
        stiffness = fixture.basis.reconstruct_stiffness(parameters).toarray()
        lower, upper = fixture.elastic_vectors[:, 2], fixture.elastic_vectors[:, 3]
        shift = upper @ stiffness @ upper - lower @ stiffness @ lower
        tied = StageAAffineBasis(
            reference_parameters=fixture.truth,
            reference_stiffness=fixture.basis.reference_stiffness
            + sparse.csr_matrix(shift * np.outer(lower, lower)),
            basis_matrices=fixture.basis.basis_matrices,
            mass=fixture.basis.mass,
            dofs=fixture.dofs,
            node_map=fixture.node_map,
        )
        values = solve_generalized_eigenproblem(
            tied.reconstruct_stiffness(parameters),
            tied.reconstruct_mass(parameters),
            8,
            expected_rigid_body_modes=3,
            dofs=fixture.dofs,
        ).eigenvalues
        self.assertLess(abs(values[3] - values[2]), 1.0e-6)
        self.assertGreater(min(np.diff(values[[0, 1, 3, 4, 5, 6, 7]])), 1.0e3)
        return fixture, tied

    def test_initial_and_optimum_sensitivity_request_their_own_paired_modes(self):
        fixture = SyntheticProductionFixture()
        calls = 0
        first_observations = []

        def provider(observations, eigenpairs):
            nonlocal calls
            del eigenpairs
            calls += 1
            if not first_observations:
                first_observations.extend(observations)
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
        ), mock.patch.object(
            stage_a_service,
            "compute_stage_a_sensitivity",
            wraps=stage_a_service.compute_stage_a_sensitivity,
        ) as spy:
            result = fixture.identify(
                pairing_provider=provider,
                requested_parameter_subset=("D11", "D66"),
                initial_parameters=fixture.truth,
            )
        self.assertEqual(spy.call_count, 2)
        initial_ids = tuple(range(2, len(first_observations) + 2))
        final_by_id = {
            item.observation_id: item.fe_mode_id
            for item in result.inverse_result.final_pairing.assignments
        }
        final_ids = tuple(final_by_id[item.observation_id] for item in first_observations)
        self.assertNotEqual(final_ids, initial_ids)
        self.assertEqual(spy.call_args_list[0].kwargs["observed_mode_ids"], initial_ids)
        self.assertEqual(spy.call_args_list[1].kwargs["observed_mode_ids"], final_ids)
        # Every fitted observation keeps its row; none is silently omitted.
        self.assertEqual(len(final_ids), result.effective_observation_count)

    def test_fitted_degenerate_mode_at_initial_point_is_refused_before_fitting(self):
        initial = StageAMatrixParameters(9.0, 0.9, 7.0)
        fixture, tied = self.tied_fixture(initial)
        with mock.patch.object(
            stage_a_service, "solve_stage_a_inverse", side_effect=AssertionError("fitted")
        ) as solver:
            with self.assertRaisesRegex(
                StageAIdentificationError,
                "initial sensitivity.*FE mode 3 .*numerically degenerate",
            ):
                fixture.identify(
                    affine_model=tied,
                    initial_parameters=initial,
                    pairing_provider=_fixed_provider((2, 3, 4, 5, 6)),
                )
        solver.assert_not_called()

    def test_unrelated_doublet_does_not_block_initial_sensitivity(self):
        initial = StageAMatrixParameters(9.0, 0.9, 7.0)
        fixture, tied = self.tied_fixture(initial)
        with mock.patch.object(
            stage_a_service, "solve_stage_a_inverse", side_effect=_InverseReached
        ) as solver:
            with self.assertRaises(_InverseReached):
                fixture.identify(
                    affine_model=tied,
                    initial_parameters=initial,
                    pairing_provider=_fixed_provider((1, 2, 5, 6, 7)),
                )
        solver.assert_called_once()

    def test_fitted_degenerate_mode_at_optimum_is_refused(self):
        tied_point = StageAMatrixParameters(9.0, 0.9, 7.0)
        fixture, tied = self.tied_fixture(tied_point)
        inverse_result = SimpleNamespace(
            fixed_parameters={},
            fitted_parameters=dict(zip(("D11", "D12", "D66"), tied_point.values)),
            final_pairing=_fixed_provider((2, 3, 4, 5, 6))(
                fixture.observations()[1:], None
            ),
        )
        with mock.patch.object(
            stage_a_service, "solve_stage_a_inverse", return_value=inverse_result
        ):
            with self.assertRaisesRegex(
                StageAIdentificationError,
                "optimum sensitivity.*FE mode 3 .*numerically degenerate",
            ):
                fixture.identify(
                    affine_model=tied,
                    initial_parameters=StageAMatrixParameters(11.0, 2.0, 5.5),
                    pairing_provider=_fixed_provider((1, 2, 5, 6, 7)),
                )


if __name__ == "__main__":
    unittest.main()
