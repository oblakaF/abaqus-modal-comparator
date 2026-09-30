from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.evidence import (
    EvidenceProvenance,
    EvidenceSourceIdentity,
    SensitivityEvidence,
    evidence_content_hash,
    evidence_record_hash,
)
from domain.identification_model import STAGE_A_BENDING_MODEL, IdentificationModelDefinition
from domain.registration import FrozenRegistration
from scientific_state import calibration_fingerprint
from domain.material_identification_session import (
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    MaterialIdentificationTaskDefinition,
    ParameterBounds,
    SessionReadiness,
)
from material_identification_runner import (
    MaterialIdentificationNotReadyError,
    MaterialIdentificationRunner,
    MaterialIdentificationRunStatus,
    MaterialIdentificationSensitivityExecutionError,
    MaterialIdentificationSourceMismatchError,
    SensitivityExecutionOutput,
)
from services.sensitivity_service import (
    ParameterSensitivityCoordinate,
    SensitivityResult,
    StageASensitivityCoordinate,
)


def _test_registration(experiment_digit="1", geometry_digit="2"):
    """Deterministic synthetic FrozenRegistration for the SP13 test specimen."""
    calibration = {"mode": "manual", "manual_scale": 1.0}
    return FrozenRegistration.create(
        experimental_source_identity={
            "path": "project/sp13/experiment.unv",
            "size": 4096,
            "mtime_ns": 1,
            "sha256": experiment_digit * 64,
        },
        experimental_modal_set_identity=None,
        fe_geometry_identity={
            "schema_version": "fe-geometry-identity/2",
            "node_count": 2,
            "instances": ["PLATE-1"],
            "dof_components": ["U1", "U2", "U3"],
            "sha256": geometry_digit * 64,
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


REGISTRATION = _test_registration()


class _NotReadySession(MaterialIdentificationSession):
    def readiness(self) -> SessionReadiness:
        return SessionReadiness(False, ("Calibration identity is not ready.",))


class _MockSensitivityExecutor:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def __call__(self, session):
        self.calls.append(session)
        if self.error is not None:
            raise self.error
        return self.output


class MaterialIdentificationSensitivityRunnerTests(unittest.TestCase):
    def setUp(self):
        # Descriptive labels only; the experiment content, FE geometry and
        # calibration identities are owned by the bound FrozenRegistration.
        self.sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP13",
            source_label="SP13-experimental",
            source_uri="project://SP13/SP13-experimental",
        )
        self.experimental_artifact = self.source("SP13-experimental", "experimental", "1")
        self.output_source = self.source(
            "SP13-sensitivity-output", "sensitivity-service-output", "4"
        )
        self.provenance = EvidenceProvenance(
            producer="injected mock sensitivity executor",
            producer_version="test-1",
            method="precomputed mock result",
            artifacts=(
                self.experimental_artifact,
                self.output_source,
            ),
            details={"mathematics_changed": False},
        )
        # SensitivityResult is the Stage-A sensitivity service type, so the
        # session identifies the Stage-A bending model (D11/D12/D66).
        bounds = {
            "D11": ParameterBounds(5.0, 50.0, "N·m"),
            "D12": ParameterBounds(-10.0, 10.0, "N·m"),
            "D66": ParameterBounds(1.0, 20.0, "N·m"),
        }
        task = MaterialIdentificationTaskDefinition(
            model=STAGE_A_BENDING_MODEL,
            selected_parameter_ids=("D11", "D12", "D66"),
            parameter_bounds=bounds,
            weighting_selection="UNIFORM",
            provenance=self.provenance,
        )
        self.session = MaterialIdentificationSession.create(
            session_id="sensitivity-session",
            created_at=datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc),
            task_definition=task,
            source_identities=self.sources,
            registration=REGISTRATION,
        )
        self.evidence_timestamp = datetime(
            2026, 9, 27, 9, 1, 30, tzinfo=timezone.utc
        )

    @staticmethod
    def source(source_id: str, source_type: str, digit: str):
        return EvidenceSourceIdentity(
            source_id=source_id,
            source_type=source_type,
            uri=f"project://SP13/{source_id}",
            content_hash=digit * 64,
        )

    @staticmethod
    def clock():
        values = iter(
            (
                datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 27, 9, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 27, 9, 2, tzinfo=timezone.utc),
            )
        )
        return lambda: next(values)

    @staticmethod
    def sensitivity_result():
        return SensitivityResult(
            observation_ids=("EXP1_A7", "EXP2_A9"),
            parameter_ids=("D11", "D12", "D66"),
            raw_derivatives=np.array(
                ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)), dtype=float
            ),
            scaled_sensitivity=np.array(
                ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6)), dtype=float
            ),
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

    def output(self, *, sources=None):
        return SensitivityExecutionOutput(
            result=self.sensitivity_result(),
            source_identities=sources or self.sources,
            source_identity=self.output_source,
            provenance=self.provenance,
            timestamp=self.evidence_timestamp,
            status="COMPLETED",
        )

    def runner(self, executor, *, session=None):
        return MaterialIdentificationRunner(
            session or self.session,
            run_id="sensitivity-run",
            clock=self.clock(),
            sensitivity_executor=executor,
        )

    def test_mock_service_executes_and_creates_typed_sensitivity_evidence(self):
        executor = _MockSensitivityExecutor(self.output())
        runner = self.runner(executor)

        completed = runner.run_sensitivity()

        self.assertEqual(executor.calls, [self.session])
        self.assertEqual(completed.run.status, MaterialIdentificationRunStatus.COMPLETED)
        evidence = completed.evidence.sensitivity
        self.assertIsInstance(evidence, SensitivityEvidence)
        self.assertEqual(evidence.timestamp, self.evidence_timestamp)
        self.assertEqual(evidence.source_identity, self.output_source)
        self.assertEqual(evidence.provenance, self.provenance)
        # Runner evidence is BOUND to the session; its hash seals content + binding.
        self.assertEqual(evidence.binding_status, "BOUND")
        registration = self.session.registration_reference
        self.assertEqual(
            evidence.scientific_binding.to_dict(),
            {
                "schema_version": "evidence-scientific-binding/2",
                "identification_model_id": self.session.task_definition.identification_model_id,
                "identification_model_hash": self.session.task_definition.identification_model_hash,
                "identification_task_hash": self.session.task_definition.scientific_task_hash,
                "registration_hash": registration.registration_hash,
                "experimental_content_sha256": registration.experimental_content_sha256,
            },
        )
        self.assertEqual(
            evidence.content_hash,
            evidence_record_hash(evidence.content, evidence.scientific_binding),
        )
        self.assertNotEqual(evidence.content_hash, evidence_content_hash(evidence.content))
        self.assertEqual(evidence.content["scaled_sensitivity"][0], (0.1, 0.2, 0.3))
        self.assertEqual(
            evidence.content["parameter_ids"],
            self.session.task_definition.model.parameter_ids,
        )
        self.assertEqual(evidence.content["coordinate_system"], "affine_D11_D12_D66")
        self.assertEqual(
            completed.run.evidence_references[0].source_identities,
            self.sources,
        )

    def test_service_failure_records_failed_lifecycle(self):
        executor = _MockSensitivityExecutor(error=RuntimeError("mock service failed"))
        runner = self.runner(executor)

        with self.assertRaisesRegex(
            MaterialIdentificationSensitivityExecutionError,
            "mock service failed",
        ):
            runner.run_sensitivity()

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)
        self.assertEqual(runner.record.errors, ("mock service failed",))

    def test_not_ready_session_does_not_call_service(self):
        session = _NotReadySession(**self.session.__dict__)
        executor = _MockSensitivityExecutor(self.output())
        runner = self.runner(executor, session=session)

        with self.assertRaisesRegex(
            MaterialIdentificationNotReadyError,
            "Calibration identity is not ready",
        ):
            runner.run_sensitivity()

        self.assertEqual(executor.calls, [])
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.NOT_READY)

    def session_variant(self, *, registration=None, model=None):
        task = self.session.task_definition
        if model is not None:
            task = MaterialIdentificationTaskDefinition(
                model=model,
                selected_parameter_ids=task.selected_parameter_ids,
                parameter_bounds=task.parameter_bounds,
                weighting_selection=task.weighting_selection,
                provenance=task.provenance,
            )
        return MaterialIdentificationSession.create(
            session_id=self.session.session_id,
            created_at=self.session.created_at,
            task_definition=task,
            source_identities=self.sources,
            registration=registration or REGISTRATION,
        )

    def produced(self, session):
        return self.runner(
            _MockSensitivityExecutor(self.output()), session=session
        ).run_sensitivity().evidence.sensitivity

    # E / F
    def test_bound_hash_follows_registration_and_model(self):
        base = self.produced(self.session)
        other_registration = self.produced(
            self.session_variant(registration=_test_registration(experiment_digit="9"))
        )
        other_model = IdentificationModelDefinition.create(
            **{
                **{
                    name: getattr(STAGE_A_BENDING_MODEL, name)
                    for name in IdentificationModelDefinition.FIELD_NAMES[:-2]
                },
                "limitations": STAGE_A_BENDING_MODEL.limitations + ("Variant.",),
            }
        )
        other_definition = self.produced(self.session_variant(model=other_model))
        for name, variant in (
            ("registration", other_registration),
            ("model definition", other_definition),
        ):
            with self.subTest(name):
                self.assertEqual(variant.content, base.content)
                self.assertEqual(variant.evidence_id, base.evidence_id)
                self.assertNotEqual(variant.content_hash, base.content_hash)
                self.assertNotEqual(variant.scientific_binding, base.scientific_binding)
        self.assertEqual(
            other_registration.scientific_binding.experimental_content_sha256, "9" * 64
        )

    def test_source_mismatch_fails_run(self):
        # Descriptive source-label mismatch only.  It does not prove scientific
        # registration/model compatibility (C5 EVIDENCE BINDING GAP).
        other_sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP14",
            source_label="SP14-experimental",
            source_uri="project://SP14/SP14-experimental",
        )
        runner = self.runner(_MockSensitivityExecutor(self.output(sources=other_sources)))

        with self.assertRaisesRegex(
            MaterialIdentificationSourceMismatchError,
            "does not match session sources",
        ):
            runner.run_sensitivity()

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
