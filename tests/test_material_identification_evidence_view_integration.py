"""C6 integration: runner-produced evidence rendered by the evidence view.

These render checks were moved out of the runner test modules so the runner
checkpoint does not depend on the (C6) evidence view.  Evidence is produced by
the real runner from a FrozenRegistration-bound session, then rendered.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.evidence import (
    EvidenceProvenance,
    EvidenceScientificBinding,
    EvidenceSourceIdentity,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
)
from domain.identification_model import EFFECTIVE_FACE_SHEET_MODEL, STAGE_A_BENDING_MODEL
from domain.material_identification_session import (
    MaterialIdentificationEvidenceReference,
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    MaterialIdentificationTaskDefinition,
    ParameterBounds,
)
from domain.registration import FrozenRegistration
from material_identification_evidence_view import (
    EvidenceModelBindingError,
    MaterialIdentificationEvidenceViewModel,
)
from material_identification_runner import (
    IdentifiabilityExecutionOutput,
    IdentificationExecutionOutput,
    MaterialIdentificationRunner,
    SensitivityExecutionOutput,
)
from scientific_state import calibration_fingerprint
from sp13_evidence_adapter import HISTORICAL_STATUS, SP13EvidenceBundle
from services.identifiability_service import (
    CollinearityResult,
    DeficientDirection,
    IdentifiabilityResult,
)
from services.inverse_solver import (
    InverseIdentificationResult,
    ModeAssignment,
    OptimizationHistoryEntry,
    PairingResult,
)
from services.sensitivity_service import (
    ParameterSensitivityCoordinate,
    SensitivityResult,
    StageASensitivityCoordinate,
)


def _registration():
    """Deterministic synthetic FrozenRegistration for the SP13 test specimen."""
    calibration = {"mode": "manual", "manual_scale": 1.0}
    return FrozenRegistration.create(
        experimental_source_identity={
            "path": "project/sp13/experiment.unv",
            "size": 4096,
            "mtime_ns": 1,
            "sha256": "1" * 64,
        },
        experimental_modal_set_identity=None,
        fe_geometry_identity={
            "schema_version": "fe-geometry-identity/2",
            "node_count": 2,
            "instances": ["PLATE-1"],
            "dof_components": ["U1", "U2", "U3"],
            "sha256": "2" * 64,
        },
        calibration=calibration,
        calibration_fingerprint=calibration_fingerprint(calibration),
        orientation_candidate_id="geometry-0123456789abcdef",
        rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[0.0, 0.0, 0.0],
        coordinate_scales=[1.0, 1.0, 1.0],
        experimental_node_ids=[1, 2],
        mapped_fe_node_ids=["PLATE-1:1", "PLATE-1:2"],
        measured_dof_contract=[[False, False, True], [False, False, True]],
        registration_metrics={},
    )


REGISTRATION = _registration()
SOURCES = MaterialIdentificationSourceIdentities(
    specimen_label="SP13",
    source_label="SP13-experimental",
    source_uri="project://SP13/SP13-experimental",
)
PROVENANCE = EvidenceProvenance(producer="evidence-view integration test")
EVIDENCE_TIMESTAMP = datetime(2026, 9, 27, 9, 1, 30, tzinfo=timezone.utc)
STAGE_A_BOUNDS = {
    "D11": ParameterBounds(5.0, 50.0, "N·m"),
    "D12": ParameterBounds(-10.0, 10.0, "N·m"),
    "D66": ParameterBounds(1.0, 20.0, "N·m"),
}
FACE_BOUNDS = {
    "Ex": ParameterBounds(30000.0, 70000.0, "MPa"),
    "Ey": ParameterBounds(30000.0, 70000.0, "MPa"),
    "Gxy": ParameterBounds(2000.0, 12000.0, "MPa"),
}


def _source(source_id: str, digit: str) -> EvidenceSourceIdentity:
    return EvidenceSourceIdentity(
        source_id=source_id,
        source_type="service-output",
        uri=f"project://SP13/{source_id}",
        content_hash=digit * 64,
    )


def _session(model, bounds) -> MaterialIdentificationSession:
    task = MaterialIdentificationTaskDefinition(
        model=model,
        selected_parameter_ids=model.parameter_ids,
        parameter_bounds=bounds,
        weighting_selection="U",
        provenance=PROVENANCE,
    )
    return MaterialIdentificationSession.create(
        session_id=f"{model.model_id}-view-session",
        created_at=datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc),
        task_definition=task,
        source_identities=SOURCES,
        registration=REGISTRATION,
    )


def _binding(session) -> EvidenceScientificBinding:
    registration = session.registration_reference
    return EvidenceScientificBinding.create(
        identification_model_id=session.task_definition.identification_model_id,
        identification_model_hash=session.task_definition.identification_model_hash,
        identification_task_hash=session.task_definition.scientific_task_hash,
        registration_hash=registration.registration_hash,
        experimental_content_sha256=registration.experimental_content_sha256,
    )


def _runner(session, **executors) -> MaterialIdentificationRunner:
    times = iter(
        datetime(2026, 9, 27, 9, minute, tzinfo=timezone.utc) for minute in (0, 1, 2)
    )
    return MaterialIdentificationRunner(
        session, run_id="view-run", clock=lambda: next(times), **executors
    )


def _sensitivity_input(session) -> SensitivityEvidence:
    return SensitivityEvidence.create(
        evidence_id="sensitivity-input",
        timestamp=datetime(2026, 9, 27, 8, 15, tzinfo=timezone.utc),
        source_identity=_source("SP13-sensitivity", "4"),
        provenance=PROVENANCE,
        status="COMPLETED",
        content={
            "raw_sensitivity_matrix": (
                {"observable": "EXP1_A7", "face_Ex": 0.1, "face_Ey": 0.2, "face_Gxy": 0.3},
            )
        },
        scientific_binding=_binding(session),
    )


def _stage_a_sensitivity_result() -> SensitivityResult:
    return SensitivityResult(
        observation_ids=("EXP1_A7", "EXP2_A9"),
        parameter_ids=("D11", "D12", "D66"),
        raw_derivatives=np.array(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)), dtype=float),
        scaled_sensitivity=np.array(((0.1, 0.2, 0.3), (0.4, 0.5, 0.6)), dtype=float),
        frequencies_hz=np.array((31.4, 75.9), dtype=float),
        # The coordinates compute_stage_a_sensitivity emits for AFFINE.
        parameter_coordinates=(
            ParameterSensitivityCoordinate(
                "D11", "physical balanced D11=D22 at fixed D12,D66", 12.0, "relative"
            ),
            ParameterSensitivityCoordinate(
                "D12", "physical signed D12 at fixed D11,D66", 12.0, "characteristic_D11"
            ),
            ParameterSensitivityCoordinate(
                "D66", "physical D66 at fixed D11,D12", 5.0, "relative"
            ),
        ),
        excluded_cluster_observations=(),
        derivative_validation=None,
        coordinate_system=StageASensitivityCoordinate.AFFINE,
    )


def _identifiability_result(parameter_ids: tuple[str, str, str]) -> IdentifiabilityResult:
    first, second, third = parameter_ids
    return IdentifiabilityResult(
        parameter_ids=parameter_ids,
        singular_values=np.array((3.0, 2.0, 1.0)),
        rank=3,
        numerical_rank_tolerance=1.0e-12,
        condition_number=3.0,
        right_singular_vectors=np.eye(3),
        fisher_information=np.diag((9.0, 4.0, 1.0)),
        covariance_proxy=np.diag((1.0 / 9.0, 0.25, 1.0)),
        correlation_matrix=np.eye(3),
        collinearity=CollinearityResult(
            parameter_ids=parameter_ids,
            gamma=1.2,
            minimum_eigenvalue=0.8,
            warning=False,
        ),
        deficient_directions=(
            DeficientDirection(
                singular_value=1.0,
                coefficients=np.array((0.1, 0.2, 0.97)),
                parameter_loadings={first: 0.1, second: 0.2, third: 0.97},
                dominant_parameter=third,
                dominant_loading=0.97,
                numerical_null_direction=False,
            ),
        ),
        best_identifiable_subset=None,
        subset_ranking=(),
        structurally_identifiable=True,
        directionally_separable=True,
        practically_precise_enough=None,
        overall_practical_identifiability=False,
        practically_identifiable=False,
        precision_status="NOT_ASSESSED_MISSING_PARAMETER_REQUIREMENTS",
        precision_assessments=(),
        scaled_standard_deviations=np.array((0.1, 0.2, 0.3)),
        transformed_coordinate_ids=parameter_ids,
        transformed_standard_deviations=np.array((0.1, 0.2, 0.3)),
        physical_standard_deviations=np.array((100.0, 200.0, 30.0)),
        observable_projector=np.eye(3),
        nullspace_basis=np.empty((3, 0)),
        parameter_observability={
            first: "OBSERVABLE",
            second: "PARTIALLY_OBSERVABLE",
            third: "UNOBSERVABLE",
        },
        warnings=("Mock warning preserved.",),
        weighting_mode="mock_U",
    )


def _face_identifiability_result() -> IdentifiabilityResult:
    return _identifiability_result(("Ex", "Ey", "Gxy"))


def _stage_a_identifiability_result() -> IdentifiabilityResult:
    return _identifiability_result(("D11", "D12", "D66"))


def _stage_a_inverse_result(identifiability_evidence_id: str) -> InverseIdentificationResult:
    pairing = PairingResult(
        assignments=(ModeAssignment("EXP1_A7", 7, mac=0.99),),
        method="supplied pairing",
    )
    # Keys follow solve_stage_a_inverse: physical D11/D12/D66 and the
    # (log D11, log D66, atanh(D12/D11)) transformed coordinates.
    return InverseIdentificationResult(
        fitted_parameters={"D11": 12.0, "D12": 2.4, "D66": 5.0},
        fixed_parameters={},
        transformed_parameters={
            "x1_log_D11": math.log(12.0),
            "x2_log_D66": math.log(5.0),
            "x3_atanh_D12_over_D11": math.atanh(0.2),
        },
        initial_parameters={"D11": 9.0, "D12": 0.9, "D66": 7.0},
        objective_initial=2.5,
        objective_global=0.25,
        objective_final=0.1,
        residuals_initial=np.array((1.0,)),
        residuals_final=np.array((0.1,)),
        predicted_frequencies_initial=np.array((30.0,)),
        predicted_frequencies_final=np.array((31.3,)),
        experimental_frequencies=np.array((31.4,)),
        observation_ids=("EXP1_A7",),
        global_evaluations=20,
        global_optimizer_evaluations=18,
        local_iterations=4,
        convergence_history=(
            OptimizationHistoryEntry(
                stage="supplied",
                evaluation=1,
                transformed_parameters=(math.log(12.0), math.log(5.0), math.atanh(0.2)),
                physical_parameters={"D11": 12.0, "D12": 2.4, "D66": 5.0},
                objective=0.1,
                success=True,
            ),
        ),
        pairing_changed_at_optimum=False,
        initial_pairing=pairing,
        global_pairing=pairing,
        final_pairing=pairing,
        excluded_observations=(),
        warnings=("Mock warning preserved.",),
        identifiability_metadata_reference=identifiability_evidence_id,
        weighting_mode="mock_U",
        global_success=True,
        global_stage_acceptable=True,
        global_message="supplied",
        local_success=True,
        local_message="supplied",
        success=True,
    )


class RunnerEvidenceViewIntegrationTests(unittest.TestCase):
    # A (moved from test_material_identification_sensitivity_runner)
    def test_stage_a_sensitivity_evidence_renders_in_gui_view_model(self):
        session = _session(STAGE_A_BENDING_MODEL, STAGE_A_BOUNDS)
        output = SensitivityExecutionOutput(
            result=_stage_a_sensitivity_result(),
            source_identities=SOURCES,
            source_identity=_source("SP13-sensitivity-output", "4"),
            provenance=PROVENANCE,
            timestamp=EVIDENCE_TIMESTAMP,
            status="COMPLETED",
        )
        runner = _runner(session, sensitivity_executor=lambda current: output)
        evidence = runner.run_sensitivity().evidence.sensitivity

        view = MaterialIdentificationEvidenceViewModel(
            sensitivity=evidence, model=session.task_definition.model
        ).sensitivity_view()

        self.assertTrue(view["available"])
        self.assertEqual(
            view["matrix"],
            (
                ("EXP1_A7", "Scalar mode", 0.1, 0.2, 0.3),
                ("EXP2_A9", "Scalar mode", 0.4, 0.5, 0.6),
            ),
        )

    # B (moved from test_material_identification_identifiability_runner; active)
    def test_effective_face_identifiability_evidence_renders_in_gui_view_model(self):
        session = _session(EFFECTIVE_FACE_SHEET_MODEL, FACE_BOUNDS)
        sensitivity = _sensitivity_input(session)
        output = IdentifiabilityExecutionOutput(
            result=_face_identifiability_result(),
            model_id="U",
            source_identities=SOURCES,
            source_identity=_source("SP13-identifiability", "5"),
            provenance=PROVENANCE,
            timestamp=EVIDENCE_TIMESTAMP,
            status="NOT_ASSESSED",
        )
        runner = _runner(session, identifiability_executor=lambda current, prior: output)
        evidence = runner.run_identifiability(
            sensitivity,
            MaterialIdentificationEvidenceReference.from_evidence(sensitivity, SOURCES),
        ).evidence.identifiability
        self.assertEqual(evidence.binding_status, "BOUND")

        view = MaterialIdentificationEvidenceViewModel(
            identifiability=evidence, model=session.task_definition.model
        ).sensitivity_view()

        self.assertTrue(view["available"])
        self.assertEqual(
            view["observability"],
            (("Ex", "strong"), ("Ey", "weak"), ("Gxy", "unavailable")),
        )
        self.assertEqual(view["identifiability"][0], ("Rank", "U: 3"))
        self.assertEqual(
            view["identifiability"][1], ("Condition number", "U: 3")
        )
        self.assertIn("Gxy +0.970", view["identifiability"][3][1])

    # Previously untested: Stage-A identifiability silently rendered Ex/Ey/Gxy.
    def test_stage_a_identifiability_evidence_renders_in_gui_view_model(self):
        session = _session(STAGE_A_BENDING_MODEL, STAGE_A_BOUNDS)
        sensitivity = _sensitivity_input(session)
        output = IdentifiabilityExecutionOutput(
            result=_stage_a_identifiability_result(),
            model_id="U",
            source_identities=SOURCES,
            source_identity=_source("SP13-identifiability", "5"),
            provenance=PROVENANCE,
            timestamp=EVIDENCE_TIMESTAMP,
            status="NOT_ASSESSED",
        )
        runner = _runner(session, identifiability_executor=lambda current, prior: output)
        evidence = runner.run_identifiability(
            sensitivity,
            MaterialIdentificationEvidenceReference.from_evidence(sensitivity, SOURCES),
        ).evidence.identifiability
        self.assertEqual(evidence.binding_status, "BOUND")

        view = MaterialIdentificationEvidenceViewModel(
            identifiability=evidence, model=session.task_definition.model
        ).sensitivity_view()

        self.assertTrue(view["available"])
        self.assertEqual(
            view["observability"],
            (("D11", "strong"), ("D12", "weak"), ("D66", "unavailable")),
        )
        self.assertEqual(view["identifiability"][0], ("Rank", "U: 3"))
        self.assertEqual(view["identifiability"][1], ("Condition number", "U: 3"))
        self.assertIn("D66 +0.970", view["identifiability"][3][1])

    # C (moved from test_material_identification_identification_runner)
    def test_stage_a_identification_evidence_renders_in_gui_view_model(self):
        session = _session(STAGE_A_BENDING_MODEL, STAGE_A_BOUNDS)
        sensitivity = _sensitivity_input(session)
        identifiability = IdentifiabilityEvidence.create(
            evidence_id="identifiability-input",
            timestamp=datetime(2026, 9, 27, 8, 30, tzinfo=timezone.utc),
            source_identity=_source("SP13-identifiability", "5"),
            provenance=PROVENANCE,
            status="COMPLETED",
            parent_ids=(sensitivity.evidence_id,),
            content={"models": {"U": {"numerical_rank": 3}}},
            scientific_binding=_binding(session),
        )
        output = IdentificationExecutionOutput(
            result=_stage_a_inverse_result(identifiability.evidence_id),
            model_id="U",
            source_identities=SOURCES,
            source_identity=_source("SP13-identification", "6"),
            provenance=PROVENANCE,
            timestamp=EVIDENCE_TIMESTAMP,
            status="COMPLETED",
            parameter_unit="N·m",
            uncertainty={
                "D11": {"standard_deviation": 0.1, "unit": "N·m"},
                "D12": {"standard_deviation": 0.2, "unit": "N·m"},
                "D66": {"standard_deviation": 0.03, "unit": "N·m"},
            },
        )
        runner = _runner(
            session, identification_executor=lambda current, prior, identifiability_: output
        )
        evidence = runner.run_identification(
            sensitivity,
            MaterialIdentificationEvidenceReference.from_evidence(sensitivity, SOURCES),
            identifiability,
            MaterialIdentificationEvidenceReference.from_evidence(identifiability, SOURCES),
        ).evidence.identification

        view = MaterialIdentificationEvidenceViewModel(
            identification=evidence, model=session.task_definition.model
        ).identification_view()

        self.assertTrue(view["available"])
        self.assertEqual(
            view["model_u"],
            (
                ("D11", 12.0, "N·m"),
                ("D12", 2.4, "N·m"),
                ("D66", 5.0, "N·m"),
            ),
        )
        self.assertEqual(
            view["model_p"],
            (("D11", None, "N·m"), ("D12", None, "N·m"), ("D66", None, "N·m")),
        )
        self.assertEqual(view["status"], "COMPLETED")


def _synthetic_historical_bundle() -> SP13EvidenceBundle:
    """Small synthetic UNBOUND bundle in the legacy historical SP13 layout.

    Presentation fixture only: the frozen-artifact loader is tested by
    test_sp13_evidence_adapter.  Values are synthetic, not REAL-4 results.
    """

    source = EvidenceSourceIdentity(
        source_id="synthetic/sp13_historical",
        source_type="frozen-sp13-artifact",
        uri="synthetic://sp13/historical",
        content_hash="5" * 64,
    )
    provenance = EvidenceProvenance(
        producer="synthetic historical SP13 view fixture",
        method="synthetic stand-in for read-only serialization of frozen artifacts",
        details={"specimen": "SP13", "historical_status": HISTORICAL_STATUS},
    )

    def record(record_type, name, status, content):
        return record_type.create(
            evidence_id=f"sp13-{name}-synthetic",
            timestamp=EVIDENCE_TIMESTAMP,
            source_identity=source,
            provenance=provenance,
            status=status,
            content=content,
            scientific_binding=None,
        )

    svd = {
        "parameter_order": ("face_Ex", "face_Ey", "face_Gxy", "core_scale"),
        "singular_values": (4.0, 3.0, 2.0, 1.0),
        "numerical_rank": 4,
        "condition_number": 4.0,
        "weakest_right_singular_vector": (0.1, 0.2, 0.3, -0.9),
    }
    return SP13EvidenceBundle(
        sensitivity=record(
            SensitivityEvidence,
            "sensitivity",
            "SYNTHETIC_FROZEN",
            {
                # CSV cells are stored as text in the historical layout.
                "raw_sensitivity_matrix": (
                    {"observable": "SYN_A1", "baseline_frequency_hz": "10.0",
                     "face_Ex": "0.125", "face_Ey": "0.25", "face_Gxy": "0.5",
                     "core_scale": "0.0625"},
                ),
            },
        ),
        identifiability=record(
            IdentifiabilityEvidence,
            "identifiability",
            "SYNTHETIC_FROZEN",
            {"models": {"U": dict(svd), "P": dict(svd)}},
        ),
        identification=record(
            IdentificationEvidence,
            "identification",
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            {
                "identified_properties": {
                    "models": {
                        "U": {"properties_MPa": {"Ex": 41000.0, "Ey": 52000.0, "Gxy": 6100.0}},
                        "P": {"properties_MPa": {"Ex": 43000.0, "Ey": 51000.0, "Gxy": 7300.0}},
                    },
                    "stability": {
                        "Ex": "RELATIVELY_STABLE",
                        "Ey": "RELATIVELY_STABLE",
                        "Gxy": "WEIGHTING_SENSITIVE",
                        "U_P_symmetric_difference_percent": {"Ex": 5.0, "Ey": 2.0, "Gxy": 18.0},
                    },
                }
            },
        ),
        validation=record(
            ValidationEvidence,
            "validation",
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            {
                "validation_rows": (
                    {"model": "U", "observable": "SYN_A1", "category": "PRIMARY",
                     "experimental_value": "10.0", "FE_value": "10.5",
                     "equivalent_error_percent": "5.0", "identity_status": "PASS"},
                ),
            },
        ),
    )


class HistoricalSP13EvidenceViewIntegrationTests(unittest.TestCase):
    """Presentation assertions for imported (UNBOUND) historical SP13 evidence."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = _synthetic_historical_bundle()

    def test_historical_bundle_renders_without_the_runner(self):
        view = MaterialIdentificationEvidenceViewModel.from_bundle(self.bundle)
        identification = view.identification_view()
        self.assertTrue(identification["available"])
        self.assertEqual(identification["model_u"][2], ("Gxy", 6100.0, "MPa"))
        self.assertEqual(identification["model_p"][0], ("Ex", 43000.0, "MPa"))
        self.assertEqual(identification["status"], "SYNTHETIC_HISTORICAL_RECOMMENDATION")
        self.assertTrue(view.sensitivity_view()["available"])

    # I
    def test_historical_bundle_renders_without_a_model_definition(self):
        self.assertEqual(
            {
                record.binding_status
                for record in (
                    self.bundle.sensitivity,
                    self.bundle.identifiability,
                    self.bundle.identification,
                    self.bundle.validation,
                )
            },
            {"UNBOUND"},
        )
        self.assertEqual(self.bundle.binding_status, "UNBOUND")
        self.assertEqual(self.bundle.historical_status, HISTORICAL_STATUS)
        view = MaterialIdentificationEvidenceViewModel.from_bundle(self.bundle)
        self.assertIsNone(view.model)

        sensitivity = view.sensitivity_view()
        self.assertEqual(
            sensitivity["matrix"][0],
            ("SYN_A1", "Scalar mode", 0.125, 0.25, 0.5),
        )
        self.assertEqual(
            sensitivity["observability"],
            (("Ex", "unavailable"), ("Ey", "unavailable"), ("Gxy", "unavailable")),
        )
        self.assertIn("core_scale -0.900", sensitivity["identifiability"][3][1])
        identification = view.identification_view()
        self.assertEqual(
            identification["model_u"],
            (
                ("Ex", 41000.0, "MPa"),
                ("Ey", 52000.0, "MPa"),
                ("Gxy", 6100.0, "MPa"),
            ),
        )
        self.assertEqual(
            identification["comparison"],
            (
                ("Ex", 5.0, "relatively stable"),
                ("Ey", 2.0, "relatively stable"),
                ("Gxy", 18.0, "weighting-sensitive"),
            ),
        )

    def test_historical_evidence_is_never_presented_as_bound_production_evidence(self):
        for model in (EFFECTIVE_FACE_SHEET_MODEL, STAGE_A_BENDING_MODEL):
            with self.subTest(model.model_id):
                with self.assertRaises(EvidenceModelBindingError) as context:
                    MaterialIdentificationEvidenceViewModel(
                        sensitivity=self.bundle.sensitivity,
                        identification=self.bundle.identification,
                        model=model,
                    )
                self.assertEqual(context.exception.reason, "unbound_with_model")

    def test_missing_historical_evidence_stays_missing_at_the_view(self):
        partial = replace(self.bundle, identification=None, validation=None)
        view = MaterialIdentificationEvidenceViewModel.from_bundle(partial)
        self.assertFalse(view.identification_view()["available"])
        self.assertEqual(view.validation_view()["status"], "NO_VALIDATION_EVIDENCE")
        self.assertTrue(view.sensitivity_view()["available"])


if __name__ == "__main__":
    unittest.main()
