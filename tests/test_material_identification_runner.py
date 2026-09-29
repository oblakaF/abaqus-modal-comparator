from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.evidence import EvidenceProvenance, EvidenceSourceIdentity
from domain.identification_model import EFFECTIVE_FACE_SHEET_MODEL
from domain.registration import FrozenRegistration
from scientific_state import calibration_fingerprint
from domain.material_identification_session import (
    MaterialIdentificationEvidenceReference,
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    MaterialIdentificationTaskDefinition,
    ParameterBounds,
    SessionReadiness,
)
from material_identification_runner import (
    MaterialIdentificationNotReadyError,
    MaterialIdentificationRunRecord,
    MaterialIdentificationRunner,
    MaterialIdentificationRunStatus,
    MaterialIdentificationSourceMismatchError,
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


class _NotReadySession(MaterialIdentificationSession):
    def readiness(self) -> SessionReadiness:
        return SessionReadiness(
            ready=False,
            reasons=("Experimental source is not validated.",),
        )


class MaterialIdentificationRunnerTests(unittest.TestCase):
    def setUp(self):
        # Descriptive labels only; the experiment content, FE geometry and
        # calibration identities are owned by the bound FrozenRegistration.
        self.sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP13", source_label="experimental-sp13"
        )
        self.experimental = self.source("experimental-sp13", "experimental", "1")
        provenance = EvidenceProvenance(
            producer="runner contract test",
            method="configuration only",
            artifacts=(self.experimental,),
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
            weighting_selection="U_AND_P_BRACKETING",
            provenance=provenance,
        )
        self.session = MaterialIdentificationSession.create(
            session_id="session-sp13",
            created_at=datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc),
            task_definition=task,
            source_identities=self.sources,
            registration=REGISTRATION,
        )

    @staticmethod
    def source(source_id: str, source_type: str, digit: str):
        return EvidenceSourceIdentity(
            source_id=source_id,
            source_type=source_type,
            content_hash=digit * 64,
        )

    @staticmethod
    def clock(*values):
        iterator = iter(values)
        return lambda: next(iterator)

    def test_session_without_registration_is_not_prepared(self):
        session = MaterialIdentificationSession.create(
            session_id="session-unregistered",
            created_at=datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc),
            task_definition=self.session.task_definition,
            source_identities=self.sources,
        )
        runner = MaterialIdentificationRunner(
            session,
            run_id="run-unregistered",
            clock=lambda: datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(
            MaterialIdentificationNotReadyError, "No FrozenRegistration is bound"
        ):
            runner.prepare()

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.NOT_READY)

    def test_readiness_rejection_remains_not_ready_and_records_errors(self):
        session = _NotReadySession(**self.session.__dict__)
        runner = MaterialIdentificationRunner(
            session,
            run_id="run-not-ready",
            clock=lambda: datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(
            MaterialIdentificationNotReadyError,
            "Experimental source is not validated",
        ):
            runner.prepare()

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.NOT_READY)
        self.assertEqual(
            runner.record.errors,
            ("Experimental source is not validated.",),
        )
        self.assertIsNone(runner.record.started_at)

    def test_successful_lifecycle_records_state_without_execution(self):
        created = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
        started = datetime(2026, 9, 27, 9, 1, tzinfo=timezone.utc)
        finished = datetime(2026, 9, 27, 9, 2, tzinfo=timezone.utc)
        runner = MaterialIdentificationRunner(
            self.session,
            run_id="run-lifecycle",
            clock=self.clock(created, started, finished),
        )

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.NOT_READY)
        reference = runner.session.registration_reference
        self.assertEqual(reference.registration_hash, REGISTRATION.registration_hash)
        self.assertEqual(reference.experimental_content_sha256, "1" * 64)
        self.assertEqual(reference.fe_geometry_identity["schema_version"], "fe-geometry-identity/2")
        self.assertEqual(runner.prepare().status, MaterialIdentificationRunStatus.READY)
        self.assertEqual(runner.start().status, MaterialIdentificationRunStatus.RUNNING)
        result = runner.complete()

        self.assertEqual(result.run.status, MaterialIdentificationRunStatus.COMPLETED)
        self.assertEqual(result.run.session_id, "session-sp13")
        self.assertEqual(result.run.run_id, "run-lifecycle")
        self.assertEqual(result.run.created_at, created)
        self.assertEqual(result.run.started_at, started)
        self.assertEqual(result.run.finished_at, finished)
        self.assertEqual(result.evidence.records(), ())
        self.assertEqual(result.run.evidence_references, ())

    def test_completion_rejects_evidence_from_different_sources(self):
        created = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
        started = datetime(2026, 9, 27, 9, 1, tzinfo=timezone.utc)
        runner = MaterialIdentificationRunner(
            self.session,
            clock=self.clock(created, started),
        )
        runner.prepare()
        runner.start()
        # Descriptive source-label mismatch only.  It does not prove scientific
        # registration/model compatibility (C5 EVIDENCE BINDING GAP).
        mismatched_sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP14", source_label="experimental-sp14"
        )
        reference = MaterialIdentificationEvidenceReference(
            evidence_id="sensitivity-sp14",
            record_type="sensitivity",
            content_hash="a" * 64,
            source_identities=mismatched_sources,
        )

        with self.assertRaisesRegex(
            MaterialIdentificationSourceMismatchError,
            "does not match session sources",
        ):
            runner.complete(evidence_references=(reference,))

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.RUNNING)

    def test_completed_run_record_serializes_deterministically(self):
        runner = MaterialIdentificationRunner(
            self.session,
            run_id="run-serialized",
            clock=self.clock(
                datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 27, 9, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 27, 9, 2, tzinfo=timezone.utc),
            ),
        )
        runner.prepare()
        runner.start()
        record = runner.complete().run

        restored = MaterialIdentificationRunRecord.from_json(record.to_json())

        self.assertEqual(restored, record)
        self.assertEqual(restored.to_json(), record.to_json())


if __name__ == "__main__":
    unittest.main()
