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
    IdentifiabilityEvidence,
    SensitivityEvidence,
    evidence_content_hash,
    evidence_record_hash,
)
from domain.identification_model import EFFECTIVE_FACE_SHEET_MODEL
from domain.registration import FrozenRegistration
from scientific_state import calibration_fingerprint
from domain.material_identification_session import (
    MaterialIdentificationEvidenceReference,
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    MaterialIdentificationTaskDefinition,
    ParameterBounds,
)
from material_identification_runner import (
    IdentifiabilityExecutionOutput,
    MaterialIdentificationIdentifiabilityExecutionError,
    MaterialIdentificationMissingSensitivityError,
    MaterialIdentificationRunner,
    MaterialIdentificationRunStatus,
    MaterialIdentificationSourceMismatchError,
)
from services.identifiability_service import (
    CollinearityResult,
    DeficientDirection,
    IdentifiabilityResult,
)


def _test_registration():
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


REGISTRATION = _test_registration()


class _MockIdentifiabilityExecutor:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def __call__(self, session, sensitivity):
        self.calls.append((session, sensitivity))
        if self.error is not None:
            raise self.error
        return self.output


class MaterialIdentificationIdentifiabilityRunnerTests(unittest.TestCase):
    def setUp(self):
        # Descriptive labels only; the experiment content, FE geometry and
        # calibration identities are owned by the bound FrozenRegistration.
        self.sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP13",
            source_label="SP13-experimental",
            source_uri="project://SP13/SP13-experimental",
        )
        self.experimental_artifact = self.source("SP13-experimental", "experimental", "1")
        self.sensitivity_source = self.source(
            "SP13-sensitivity", "sensitivity-output", "4"
        )
        self.identifiability_source = self.source(
            "SP13-identifiability", "identifiability-output", "5"
        )
        self.provenance = EvidenceProvenance(
            producer="injected mock identifiability executor",
            producer_version="test-1",
            method="precomputed mock result",
            artifacts=(
                self.experimental_artifact,
                self.identifiability_source,
            ),
            details={"mathematics_changed": False},
        )
        bounds = {
            "Ex": ParameterBounds(30000.0, 70000.0, "MPa"),
            "Ey": ParameterBounds(30000.0, 70000.0, "MPa"),
            "Gxy": ParameterBounds(2000.0, 12000.0, "MPa"),
        }
        task = MaterialIdentificationTaskDefinition(
            model=EFFECTIVE_FACE_SHEET_MODEL,
            selected_parameter_ids=("Ex", "Ey", "Gxy"),
            parameter_bounds=bounds,
            weighting_selection="U",
            provenance=self.provenance,
        )
        self.session = MaterialIdentificationSession.create(
            session_id="identifiability-session",
            created_at=datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc),
            task_definition=task,
            source_identities=self.sources,
            registration=REGISTRATION,
        )
        self.sensitivity = SensitivityEvidence.create(
            evidence_id="sensitivity-input",
            timestamp=datetime(2026, 9, 27, 8, 30, tzinfo=timezone.utc),
            source_identity=self.sensitivity_source,
            provenance=self.provenance,
            status="COMPLETED",
            content={
                "raw_sensitivity_matrix": (
                    {
                        "observable": "EXP1_A7",
                        "face_Ex": 0.1,
                        "face_Ey": 0.2,
                        "face_Gxy": 0.3,
                    },
                )
            },
        )
        self.sensitivity_reference = (
            MaterialIdentificationEvidenceReference.from_evidence(
                self.sensitivity, self.sources
            )
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
    def identifiability_result():
        return IdentifiabilityResult(
            parameter_ids=("Ex", "Ey", "Gxy"),
            singular_values=np.array((3.0, 2.0, 1.0)),
            rank=3,
            numerical_rank_tolerance=1.0e-12,
            condition_number=3.0,
            right_singular_vectors=np.eye(3),
            fisher_information=np.diag((9.0, 4.0, 1.0)),
            covariance_proxy=np.diag((1.0 / 9.0, 0.25, 1.0)),
            correlation_matrix=np.eye(3),
            collinearity=CollinearityResult(
                parameter_ids=("Ex", "Ey", "Gxy"),
                gamma=1.2,
                minimum_eigenvalue=0.8,
                warning=False,
            ),
            deficient_directions=(
                DeficientDirection(
                    singular_value=1.0,
                    coefficients=np.array((0.1, 0.2, 0.97)),
                    parameter_loadings={"Ex": 0.1, "Ey": 0.2, "Gxy": 0.97},
                    dominant_parameter="Gxy",
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
            transformed_coordinate_ids=("Ex", "Ey", "Gxy"),
            transformed_standard_deviations=np.array((0.1, 0.2, 0.3)),
            physical_standard_deviations=np.array((100.0, 200.0, 30.0)),
            observable_projector=np.eye(3),
            nullspace_basis=np.empty((3, 0)),
            parameter_observability={
                "Ex": "OBSERVABLE",
                "Ey": "PARTIALLY_OBSERVABLE",
                "Gxy": "UNOBSERVABLE",
            },
            warnings=("Mock warning preserved.",),
            weighting_mode="mock_U",
        )

    def output(self, *, sources=None):
        return IdentifiabilityExecutionOutput(
            result=self.identifiability_result(),
            model_id="U",
            source_identities=sources or self.sources,
            source_identity=self.identifiability_source,
            provenance=self.provenance,
            timestamp=self.evidence_timestamp,
            status="NOT_ASSESSED",
        )

    def runner(self, executor):
        return MaterialIdentificationRunner(
            self.session,
            run_id="identifiability-run",
            clock=self.clock(),
            identifiability_executor=executor,
        )

    def test_mock_service_creates_typed_identifiability_evidence(self):
        executor = _MockIdentifiabilityExecutor(self.output())
        runner = self.runner(executor)

        completed = runner.run_identifiability(
            self.sensitivity, self.sensitivity_reference
        )

        self.assertEqual(executor.calls, [(self.session, self.sensitivity)])
        self.assertEqual(completed.run.status, MaterialIdentificationRunStatus.COMPLETED)
        evidence = completed.evidence.identifiability
        self.assertIsInstance(evidence, IdentifiabilityEvidence)
        self.assertEqual(evidence.parent_ids, (self.sensitivity.evidence_id,))
        self.assertEqual(evidence.timestamp, self.evidence_timestamp)
        self.assertEqual(evidence.source_identity, self.identifiability_source)
        self.assertEqual(evidence.provenance, self.provenance)
        self.assertEqual(evidence.status, "NOT_ASSESSED")
        # Runner evidence is BOUND to the session; its hash seals content + binding.
        self.assertEqual(evidence.binding_status, "BOUND")
        registration = self.session.registration_reference
        self.assertEqual(
            evidence.scientific_binding.to_dict(),
            {
                "identification_model_id": self.session.task_definition.identification_model_id,
                "identification_model_hash": self.session.task_definition.identification_model_hash,
                "registration_hash": registration.registration_hash,
                "experimental_content_sha256": registration.experimental_content_sha256,
            },
        )
        self.assertEqual(
            evidence.content_hash,
            evidence_record_hash(evidence.content, evidence.scientific_binding),
        )
        self.assertNotEqual(evidence.content_hash, evidence_content_hash(evidence.content))
        self.assertEqual(evidence.content["models"]["U"]["numerical_rank"], 3)
        self.assertEqual(
            evidence.content["models"]["U"]["parameter_order"],
            self.session.task_definition.model.parameter_ids,
        )
        self.assertEqual(
            evidence.content["models"]["U"]["parameter_observability"]["Ey"],
            "PARTIALLY_OBSERVABLE",
        )

    def test_missing_sensitivity_is_rejected_before_service_call(self):
        executor = _MockIdentifiabilityExecutor(self.output())
        runner = self.runner(executor)

        with self.assertRaisesRegex(
            MaterialIdentificationMissingSensitivityError,
            "Sensitivity evidence",
        ):
            runner.run_identifiability(None, None)

        self.assertEqual(executor.calls, [])
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.READY)

    def test_service_exception_records_failed_lifecycle(self):
        executor = _MockIdentifiabilityExecutor(
            error=RuntimeError("mock identifiability failed")
        )
        runner = self.runner(executor)

        with self.assertRaisesRegex(
            MaterialIdentificationIdentifiabilityExecutionError,
            "mock identifiability failed",
        ):
            runner.run_identifiability(
                self.sensitivity, self.sensitivity_reference
            )

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)
        self.assertEqual(runner.record.errors, ("mock identifiability failed",))

    def test_source_mismatch_fails_after_service_output(self):
        # Descriptive source-label mismatch only.  It does not prove scientific
        # registration/model compatibility (C5 EVIDENCE BINDING GAP).
        other_sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP14",
            source_label="SP14-experimental",
            source_uri="project://SP14/SP14-experimental",
        )
        runner = self.runner(
            _MockIdentifiabilityExecutor(self.output(sources=other_sources))
        )

        with self.assertRaisesRegex(
            MaterialIdentificationSourceMismatchError,
            "does not match session sources",
        ):
            runner.run_identifiability(
                self.sensitivity, self.sensitivity_reference
            )

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
