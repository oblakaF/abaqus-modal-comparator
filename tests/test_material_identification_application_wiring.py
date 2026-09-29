from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


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
from material_identification_evidence_view import (
    MaterialIdentificationEvidenceViewModel,
)
from material_identification_runner import (
    MaterialIdentificationEvidenceBindingError,
    MaterialIdentificationEvidenceResults,
    MaterialIdentificationLifecycleError,
    MaterialIdentificationRunner,
    MaterialIdentificationRunStatus,
    MaterialIdentificationSourceMismatchError,
)
from material_identification_ui import identification_result_view, session_evidence_view_model
from sp13_evidence_adapter import HISTORICAL_STATUS, SP13EvidenceBundle


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


def _synthetic_historical_bundle() -> SP13EvidenceBundle:
    """Small synthetic UNBOUND bundle in the legacy historical SP13 layout.

    Wiring fixture only: the frozen-artifact loader is tested by
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
    timestamp = datetime(2026, 9, 27, 8, 30, tzinfo=timezone.utc)

    def record(record_type, name, status, content):
        return record_type.create(
            evidence_id=f"sp13-{name}-synthetic",
            timestamp=timestamp,
            source_identity=source,
            provenance=provenance,
            status=status,
            content=content,
            scientific_binding=None,
        )

    return SP13EvidenceBundle(
        sensitivity=record(
            SensitivityEvidence,
            "sensitivity",
            "SYNTHETIC_FROZEN",
            {
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
            {
                "models": {
                    "U": {
                        "parameter_order": ("face_Ex", "face_Ey", "face_Gxy", "core_scale"),
                        "singular_values": (4.0, 3.0, 2.0, 1.0),
                        "numerical_rank": 4,
                        "condition_number": 4.0,
                        "weakest_right_singular_vector": (0.1, 0.2, 0.3, -0.9),
                    }
                }
            },
        ),
        identification=record(
            IdentificationEvidence,
            "identification",
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            {
                "identified_properties": {
                    "models": {
                        "U": {"properties_MPa": {"Ex": 41000.0, "Ey": 52000.0, "Gxy": 6100.0}},
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
                     "experimental_value": "10.25", "FE_value": "10.5",
                     "equivalent_error_percent": "2.4", "identity_status": "PASS"},
                ),
            },
        ),
    )


class MaterialIdentificationApplicationWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = _synthetic_historical_bundle()

    def setUp(self):
        # Descriptive labels only; the experiment content, FE geometry and
        # calibration identities are owned by the bound FrozenRegistration.
        self.sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP13",
            source_label="SP13-experimental",
            source_uri="project://SP13/SP13-experimental",
        )
        self.experimental_artifact = self.source("SP13-experimental", "experimental-modal-data", "1")
        provenance = EvidenceProvenance(
            producer="material-identification application wiring test",
            method="frozen evidence integration only",
            artifacts=(
                self.experimental_artifact,
            ),
            details={"scientific_execution": False},
        )
        bounds = {
            "Ex": ParameterBounds(30000.0, 70000.0, "MPa"),
            "Ey": ParameterBounds(30000.0, 70000.0, "MPa"),
            "Gxy": ParameterBounds(2000.0, 12000.0, "MPa"),
        }
        # A production session of the effective face-sheet model; SP13 is only the
        # specimen label.  The historical SP13 records are UNBOUND and belong to no
        # current model definition.
        task = MaterialIdentificationTaskDefinition(
            model=EFFECTIVE_FACE_SHEET_MODEL,
            selected_parameter_ids=("Ex", "Ey", "Gxy"),
            parameter_bounds=bounds,
            weighting_selection="U_AND_P_BRACKETING",
            provenance=provenance,
        )
        self.session = MaterialIdentificationSession.create(
            session_id="sp13-application-session",
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

    def references(self, results: MaterialIdentificationEvidenceResults):
        return tuple(
            MaterialIdentificationEvidenceReference.from_evidence(
                record, self.sources
            )
            for record in results.records()
        )

    def runner(self):
        return MaterialIdentificationRunner(
            self.session,
            run_id="sp13-frozen-evidence-run",
            clock=self.clock(),
        )

    def test_production_runner_refuses_historical_sp13_evidence(self):
        # Production safety: imported historical SP13 evidence is UNBOUND and must
        # never enter a production session through the runner.
        results = MaterialIdentificationEvidenceResults(
            sensitivity=self.bundle.sensitivity,
            identifiability=self.bundle.identifiability,
            identification=self.bundle.identification,
            validation=self.bundle.validation,
        )
        before = {record.evidence_id: record.to_dict() for record in results.records()}
        runner = self.runner()

        task = self.session.task_definition
        self.assertEqual(task.identification_model_id, "effective_face_sheet")
        self.assertEqual(
            task.identification_model_hash, EFFECTIVE_FACE_SHEET_MODEL.definition_hash
        )
        self.assertEqual(task.selected_parameter_ids, task.model.parameter_ids)
        registration = self.session.registration_reference
        self.assertEqual(registration.registration_hash, REGISTRATION.registration_hash)
        self.assertEqual(registration.experimental_content_sha256, "1" * 64)
        self.assertEqual(
            registration.fe_geometry_identity["schema_version"], "fe-geometry-identity/2"
        )
        self.assertEqual(self.session.source_identities.specimen_label, "SP13")
        self.assertTrue(self.session.readiness().ready)
        self.assertEqual(runner.prepare().status, MaterialIdentificationRunStatus.READY)
        self.assertEqual(runner.start().status, MaterialIdentificationRunStatus.RUNNING)
        # Matching descriptive labels do not help: the records are UNBOUND.
        with self.assertRaises(MaterialIdentificationEvidenceBindingError) as context:
            runner.complete(
                evidence=results,
                evidence_references=self.references(results),
            )
        self.assertEqual(context.exception.reason, "unbound")
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.RUNNING)
        self.assertEqual(runner.record.evidence_references, ())
        for record in results.records():
            self.assertIsNone(record.scientific_binding)
            self.assertEqual(record.to_dict(), before[record.evidence_id])

    def test_historical_sp13_bundle_reaches_the_view_without_the_runner(self):
        # Historical display: import -> UNBOUND bundle -> evidence view.
        self.assertEqual(self.bundle.historical_status, "HISTORICAL_NOT_REVALIDATED")
        view_model = MaterialIdentificationEvidenceViewModel.from_bundle(self.bundle)

        sensitivity = view_model.sensitivity_view()
        identification = view_model.identification_view()
        validation = view_model.validation_view()
        self.assertIsNone(view_model.model)
        self.assertEqual(
            sensitivity["matrix"][0],
            ("SYN_A1", "Scalar mode", 0.125, 0.25, 0.5),
        )
        self.assertEqual(identification["model_u"][0], ("Ex", 41000.0, "MPa"))
        self.assertEqual(
            identification["status"],
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
        )
        primary_a1 = next(
            row
            for row in validation["primary"]
            if row[0] == "U" and row[1] == "SYN_A1"
        )
        self.assertEqual(primary_a1[2], "10.25")
        self.assertEqual(primary_a1[3], "10.5")

    def test_runner_evidence_reaches_the_ui_through_its_session_model(self):
        # Production display: session -> runner-accepted BOUND evidence -> UI view
        # rendered against the session's own model definition.
        registration = self.session.registration_reference
        identification = IdentificationEvidence.create(
            evidence_id="bound-identification",
            timestamp=datetime(2026, 9, 27, 8, 45, tzinfo=timezone.utc),
            source_identity=self.source("bound-identification", "identification-output", "6"),
            provenance=EvidenceProvenance(producer="application wiring test"),
            status="COMPLETED",
            content={
                "identified_properties": {
                    "models": {
                        "U": {
                            "properties_MPa": {"Ex": 45000.0, "Ey": 60000.0, "Gxy": 8000.0},
                            "parameter_unit": "MPa",
                            "uncertainty": {},
                        }
                    }
                }
            },
            scientific_binding=EvidenceScientificBinding.create(
                identification_model_id=self.session.task_definition.identification_model_id,
                identification_model_hash=self.session.task_definition.identification_model_hash,
                registration_hash=registration.registration_hash,
                experimental_content_sha256=registration.experimental_content_sha256,
            ),
        )
        results = MaterialIdentificationEvidenceResults(identification=identification)
        runner = self.runner()
        runner.prepare()
        runner.start()
        completed = runner.complete(evidence=results, evidence_references=self.references(results))
        self.assertEqual(completed.run.status, MaterialIdentificationRunStatus.COMPLETED)

        view_model = session_evidence_view_model(
            self.session, identification=completed.evidence.identification
        )
        self.assertIs(view_model.model, self.session.task_definition.model)
        application = type(
            "Application",
            (),
            {
                "material_identification_evidence_view_model": view_model,
                "material_identification_session": self.session,
            },
        )()
        self.assertEqual(
            identification_result_view(application)["model_u"],
            (("Ex", 45000.0, "MPa"), ("Ey", 60000.0, "MPa"), ("Gxy", 8000.0, "MPa")),
        )
        # Historical records can never be shown under the production session.
        with self.assertRaises(ValueError):
            session_evidence_view_model(self.session, identification=self.bundle.identification)

    def test_runner_rejects_frozen_evidence_bound_to_other_sources(self):
        results = MaterialIdentificationEvidenceResults(
            sensitivity=self.bundle.sensitivity
        )
        runner = self.runner()
        runner.prepare()
        runner.start()
        # The descriptive source-label check runs first and still refuses.  It
        # proves nothing scientific: the binding check (see the production
        # firewall test above) is what keeps historical evidence out.
        other_sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP14",
            source_label="SP14-experimental",
            source_uri="project://SP14/SP14-experimental",
        )
        reference = MaterialIdentificationEvidenceReference.from_evidence(
            self.bundle.sensitivity, other_sources
        )

        with self.assertRaisesRegex(
            MaterialIdentificationSourceMismatchError,
            "does not match session sources",
        ):
            runner.complete(
                evidence=results,
                evidence_references=(reference,),
            )

    def test_missing_evidence_remains_missing_at_gui_boundary(self):
        # Absent historical records stay absent; nothing is synthesized and the
        # production runner is not used to fill them.
        view_model = MaterialIdentificationEvidenceViewModel.from_bundle(
            SP13EvidenceBundle(
                sensitivity=self.bundle.sensitivity,
                identifiability=None,
                identification=None,
                validation=None,
            )
        )

        self.assertTrue(view_model.sensitivity_view()["available"])
        self.assertFalse(view_model.identification_view()["available"])
        self.assertEqual(
            view_model.validation_view()["status"],
            "NO_VALIDATION_EVIDENCE",
        )

    def test_invalid_lifecycle_transition_is_rejected(self):
        runner = self.runner()

        with self.assertRaisesRegex(
            MaterialIdentificationLifecycleError,
            "Expected run state READY, got NOT_READY",
        ):
            runner.start()

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.NOT_READY)


if __name__ == "__main__":
    unittest.main()
