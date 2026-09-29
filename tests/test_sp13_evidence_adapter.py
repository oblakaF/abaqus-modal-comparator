from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
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
    evidence_from_dict,
    evidence_from_json,
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
import sp13_evidence_adapter
from material_identification_runner import (
    MaterialIdentificationEvidenceBindingError,
    MaterialIdentificationEvidenceResults,
    MaterialIdentificationRunner,
    MaterialIdentificationRunStatus,
)
from sp13_evidence_adapter import load_frozen_sp13_evidence


SENSITIVITY_DIR = "sp13_sensitivity_real2"
INVERSE_DIR = "sp13_effective_cfrp_inverse"
VALIDATION_DIR = "sp13_final_effective_property_validation"
SYNTHETIC_COMMIT = "a" * 40
SYNTHETIC_MTIME = 1577836800  # 2020-01-01 UTC, not a real artifact timestamp.


def _synthetic_artifacts():
    """Small invented payloads in the exact file layout accepted by the loader."""
    artifacts = {
        f"{SENSITIVITY_DIR}/raw_sensitivity_matrix.csv": (
            "observable,face_Ex,face_Ey,face_Gxy\nSYNTHETIC_MODE,0.1,0.2,0.3\n"
        ),
        f"{SENSITIVITY_DIR}/cluster_sensitivity.csv": "observable\nSYNTHETIC_FAMILY\n",
        f"{SENSITIVITY_DIR}/parameter_baseline.csv": "parameter,value\nface_Ex,100000\n",
        f"{SENSITIVITY_DIR}/execution_note.json": {
            "final_state": "SYNTHETIC_SENSITIVITY_STORED",
            "completed_utc": "2020-01-02T03:04:05Z",
            "baseline_hashes_verified_unchanged": {"odb": "1" * 64},
        },
        f"{SENSITIVITY_DIR}/protocol.json": {},
        f"{SENSITIVITY_DIR}/svd_uniform.json": {
            "numerical_rank": 3,
            "condition_number": 2.0,
            "weakest_right_singular_vector": [0.0, 0.0, 1.0],
            "practical_precision_status": "NOT_ASSESSED",
        },
        f"{SENSITIVITY_DIR}/svd_per_mode.json": {
            "numerical_rank": 3,
            "condition_number": 4.0,
            "practical_precision_status": "NOT_ASSESSED",
        },
        f"{INVERSE_DIR}/inverse_results_U.json": {"fitted_parameters": {"Ex": 100000}},
        f"{INVERSE_DIR}/inverse_results_P.json": {"fitted_parameters": {"Ex": 110000}},
        f"{INVERSE_DIR}/parameter_comparison.csv": "parameter,U,P\nEx,100000,110000\n",
        f"{INVERSE_DIR}/execution_note.json": {"final_state": "SYNTHETIC_INVERSE_STORED"},
        f"{VALIDATION_DIR}/identified_properties.json": {
            "models": {
                "U": {"properties_MPa": {"Ex": 100000, "Ey": 80000, "Gxy": 5000}},
                "P": {"properties_MPa": {"Ex": 110000, "Ey": 90000, "Gxy": 6000}},
            },
            "recommendation": "SYNTHETIC_RECOMMENDATION",
            "record_status": "FROZEN",
            "starting_head": SYNTHETIC_COMMIT,
            "interpretation": "Synthetic test data, not material measurements.",
        },
        f"{VALIDATION_DIR}/validation_summary.csv": (
            "model,observable,category,equivalent_error_percent\n"
            "U,SYNTHETIC_HOLDOUT,HOLDOUT,-1.25\n"
        ),
        f"{VALIDATION_DIR}/limitations.md": "Synthetic limitations only.\n",
        f"{VALIDATION_DIR}/FINAL_REPORT.md": "Synthetic historical report only.\n",
    }
    return {
        name: json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
        for name, value in artifacts.items()
    }


def _write_synthetic_artifacts(root, artifacts=None):
    artifacts = _synthetic_artifacts() if artifacts is None else artifacts
    for relative, text in artifacts.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        os.utime(path, (SYNTHETIC_MTIME, SYNTHETIC_MTIME))


class SyntheticArtifactTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.analysis_root = Path(directory.name)
        _write_synthetic_artifacts(self.analysis_root)


def _test_registration(translation_x=0.0):
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
        translation=[translation_x, 0.0, 0.0],
        coordinate_scales=[1.0, 1.0, 1.0],
        experimental_node_ids=[1, 2],
        mapped_fe_node_ids=["PLATE-1:1", "PLATE-1:2"],
        measured_dof_contract=[[False, False, True], [False, False, True]],
        registration_metrics={},
    )


REGISTRATION = _test_registration()


class FrozenSP13EvidenceAdapterTests(SyntheticArtifactTestCase):
    def test_converts_frozen_sp13_values_without_recalculation(self):
        bundle = load_frozen_sp13_evidence(self.analysis_root)

        self.assertIsInstance(bundle.sensitivity, SensitivityEvidence)
        self.assertIsInstance(bundle.identifiability, IdentifiabilityEvidence)
        self.assertIsInstance(bundle.identification, IdentificationEvidence)
        self.assertIsInstance(bundle.validation, ValidationEvidence)

        sensitivity_rows = bundle.sensitivity.content["raw_sensitivity_matrix"]
        self.assertEqual(sensitivity_rows[0]["observable"], "SYNTHETIC_MODE")
        self.assertEqual(
            sensitivity_rows[0]["face_Gxy"], "0.3"
        )
        self.assertEqual(bundle.sensitivity.status, "SYNTHETIC_SENSITIVITY_STORED")

        models = bundle.identifiability.content["models"]
        self.assertEqual(models["U"]["numerical_rank"], 3)
        self.assertEqual(models["P"]["condition_number"], 4.0)
        self.assertEqual(
            models["U"]["weakest_right_singular_vector"],
            (0.0, 0.0, 1.0),
        )

        identified = bundle.identification.content["identified_properties"]
        self.assertEqual(
            identified["models"]["U"]["properties_MPa"]["Ex"],
            100000,
        )
        self.assertEqual(
            identified["models"]["P"]["properties_MPa"]["Gxy"],
            6000,
        )
        self.assertEqual(
            bundle.identification.status,
            "SYNTHETIC_RECOMMENDATION",
        )

        rows = bundle.validation.content["validation_rows"]
        holdout = next(
            row
            for row in rows
            if row["model"] == "U" and row["observable"] == "SYNTHETIC_HOLDOUT"
        )
        self.assertEqual(holdout["category"], "HOLDOUT")
        self.assertEqual(holdout["equivalent_error_percent"], "-1.25")
        self.assertIn(
            "Synthetic test data",
            identified["interpretation"],
        )

    def test_preserves_source_hashes_and_round_trips(self):
        bundle = load_frozen_sp13_evidence(self.analysis_root)
        records = (
            bundle.sensitivity,
            bundle.identifiability,
            bundle.identification,
            bundle.validation,
        )
        for record in records:
            with self.subTest(record_type=type(record).__name__):
                restored = evidence_from_json(record.to_json())
                self.assertEqual(restored, record)
                self.assertEqual(evidence_from_dict(record.to_dict()), record)
                self.assertEqual(
                    restored.source_identity.content_hash,
                    record.source_identity.content_hash,
                )
                self.assertGreaterEqual(len(restored.provenance.artifacts), 1)
                for artifact in restored.provenance.artifacts:
                    path = self.analysis_root / artifact.source_id
                    self.assertEqual(artifact.content_hash, hashlib.sha256(path.read_bytes()).hexdigest())
                    self.assertEqual(artifact.uri, path.resolve().as_uri())
                    self.assertEqual(artifact.source_type, "frozen-sp13-artifact")
                self.assertIn(restored.source_identity, restored.provenance.artifacts)
                self.assertEqual(
                    tuple(restored.provenance.details["source_paths"]),
                    tuple(item.source_id for item in restored.provenance.artifacts),
                )

        historical_hashes = bundle.sensitivity.content["execution"][
            "baseline_hashes_verified_unchanged"
        ]
        self.assertEqual(
            historical_hashes["odb"],
            "1" * 64,
        )
        self.assertEqual(
            bundle.identification.provenance.commit,
            SYNTHETIC_COMMIT,
        )

    def test_missing_evidence_remains_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            analysis_root = Path(directory)
            relative = f"{SENSITIVITY_DIR}/svd_uniform.json"
            _write_synthetic_artifacts(analysis_root, {relative: _synthetic_artifacts()[relative]})

            bundle = load_frozen_sp13_evidence(analysis_root)

            self.assertIsNone(bundle.sensitivity)
            self.assertIsInstance(bundle.identifiability, IdentifiabilityEvidence)
            self.assertEqual(tuple(bundle.identifiability.content["models"]), ("U",))
            self.assertNotIn("P", bundle.identifiability.content["models"])
            self.assertNotIn("execution", bundle.identifiability.content)
            self.assertEqual(bundle.identifiability.status, "NOT_ASSESSED")
            self.assertIsNone(bundle.identification)
            self.assertIsNone(bundle.validation)

    def test_optional_payloads_and_timestamp_provenance_are_preserved(self):
        bundle = load_frozen_sp13_evidence(self.analysis_root)
        artifacts = _synthetic_artifacts()
        self.assertEqual(bundle.sensitivity.content["protocol"], {})
        self.assertEqual(
            bundle.sensitivity.content["family_observables"],
            ({"observable": "SYNTHETIC_FAMILY"},),
        )
        self.assertEqual(
            bundle.sensitivity.content["parameter_baseline"],
            ({"parameter": "face_Ex", "value": "100000"},),
        )
        self.assertEqual(
            bundle.identification.to_dict()["content"]["identified_properties"],
            json.loads(artifacts[f"{VALIDATION_DIR}/identified_properties.json"]),
        )
        for model in ("U", "P"):
            self.assertEqual(
                bundle.identification.content["inverse_models"][model],
                json.loads(artifacts[f"{INVERSE_DIR}/inverse_results_{model}.json"]),
            )
        self.assertEqual(
            bundle.identification.content["parameter_comparison"],
            ({"parameter": "Ex", "U": "100000", "P": "110000"},),
        )
        self.assertEqual(
            bundle.identification.content["execution"],
            json.loads(artifacts[f"{INVERSE_DIR}/execution_note.json"]),
        )
        self.assertEqual(bundle.validation.content["limitations_markdown"], "Synthetic limitations only.\n")
        self.assertEqual(bundle.validation.content["report_markdown"], "Synthetic historical report only.\n")
        for record in (bundle.sensitivity, bundle.identifiability):
            self.assertEqual(record.timestamp, datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
            self.assertEqual(record.provenance.details["record_timestamp_basis"], "stored completed_utc")
        for record in (bundle.identification, bundle.validation):
            self.assertEqual(record.timestamp, datetime(2020, 1, 1, tzinfo=timezone.utc))
            self.assertEqual(
                record.provenance.details["record_timestamp_basis"],
                "latest source-file modification time in UTC",
            )
            self.assertEqual(record.provenance.commit, SYNTHETIC_COMMIT)

    def test_missing_required_artifacts_do_not_synthesize_records(self):
        artifacts = _synthetic_artifacts()
        for selected in (
            (),
            (f"{SENSITIVITY_DIR}/raw_sensitivity_matrix.csv",),
            (f"{SENSITIVITY_DIR}/execution_note.json",),
            (f"{VALIDATION_DIR}/validation_summary.csv",),
        ):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _write_synthetic_artifacts(root, {name: artifacts[name] for name in selected})
                bundle = load_frozen_sp13_evidence(root)
                self.assertEqual(
                    (bundle.sensitivity, bundle.identifiability, bundle.identification, bundle.validation),
                    (None, None, None, None),
                )

    def test_record_status_fallback_does_not_invent_validation(self):
        identified_name = f"{VALIDATION_DIR}/identified_properties.json"
        identified = json.loads(_synthetic_artifacts()[identified_name])
        del identified["recommendation"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_synthetic_artifacts(root, {
                identified_name: json.dumps(identified),
                f"{VALIDATION_DIR}/validation_summary.csv": _synthetic_artifacts()[
                    f"{VALIDATION_DIR}/validation_summary.csv"
                ],
            })
            bundle = load_frozen_sp13_evidence(root)
            self.assertEqual(bundle.identification.status, "FROZEN")
            self.assertEqual(set(bundle.identification.content), {"identified_properties"})
            self.assertIsNone(bundle.validation)
            self.assertIsNone(bundle.sensitivity)
            self.assertIsNone(bundle.identifiability)

    def test_input_artifacts_are_not_modified(self):
        def snapshot():
            return {
                path.relative_to(self.analysis_root): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.analysis_root.rglob("*") if path.is_file()
            }

        before = snapshot()
        load_frozen_sp13_evidence(self.analysis_root)
        self.assertEqual(snapshot(), before)


class HistoricalSP13ImportTests(SyntheticArtifactTestCase):
    """Exercise historical import with synthetic files, never local research data."""

    def setUp(self):
        super().setUp()
        self.bundle = load_frozen_sp13_evidence(self.analysis_root)

    def records(self, bundle=None):
        bundle = bundle or self.bundle
        return tuple(
            record
            for record in (
                bundle.sensitivity,
                bundle.identifiability,
                bundle.identification,
                bundle.validation,
            )
            if record is not None
        )

    def production_session(self, registration=REGISTRATION):
        task = MaterialIdentificationTaskDefinition(
            model=EFFECTIVE_FACE_SHEET_MODEL,
            selected_parameter_ids=("Ex", "Ey", "Gxy"),
            parameter_bounds={
                "Ex": ParameterBounds(30000.0, 70000.0, "MPa"),
                "Ey": ParameterBounds(30000.0, 70000.0, "MPa"),
                "Gxy": ParameterBounds(2000.0, 12000.0, "MPa"),
            },
            weighting_selection="U_AND_P_BRACKETING",
            provenance=EvidenceProvenance(producer="SP13 production-firewall test"),
        )
        return MaterialIdentificationSession.create(
            session_id="sp13-production-session",
            created_at=datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc),
            task_definition=task,
            source_identities=MaterialIdentificationSourceIdentities(
                specimen_label="SP13", source_label="SP13-experimental"
            ),
            registration=registration,
        )

    def runner(self, session, executor=None):
        times = iter(
            datetime(2026, 9, 29, hour, 0, tzinfo=timezone.utc) for hour in (9, 10, 11)
        )
        return MaterialIdentificationRunner(
            session,
            run_id="sp13-firewall-run",
            clock=lambda: next(times),
            identification_executor=executor,
        )

    # A / B / C
    def test_imported_records_are_unbound_historical_artifacts(self):
        self.assertEqual(self.bundle.historical_status, "HISTORICAL_NOT_REVALIDATED")
        self.assertEqual(self.bundle.binding_status, "UNBOUND")
        records = self.records()
        self.assertTrue(records)
        for record in records:
            with self.subTest(record.RECORD_TYPE):
                self.assertIsNone(record.scientific_binding)
                self.assertEqual(record.binding_status, "UNBOUND")
                self.assertEqual(record.source_identity.source_type, "frozen-sp13-artifact")
                self.assertEqual(
                    record.provenance.details["historical_status"], "HISTORICAL_NOT_REVALIDATED"
                )
                self.assertNotEqual(record.status, "VALIDATED")
                text = json.dumps(record.to_dict())
                self.assertNotIn(REGISTRATION.registration_hash, text)
                self.assertNotIn(EFFECTIVE_FACE_SHEET_MODEL.definition_hash, text)
                self.assertNotIn("registration_hash", text)
                self.assertNotIn("identification_model_hash", text)

    def test_synthetic_values_and_original_status_are_preserved(self):
        identified = self.bundle.identification.content["identified_properties"]
        models = identified["models"]
        self.assertEqual(
            models["U"]["properties_MPa"],
            {"Ex": 100000, "Ey": 80000, "Gxy": 5000},
        )
        self.assertEqual(
            models["P"]["properties_MPa"],
            {"Ex": 110000, "Ey": 90000, "Gxy": 6000},
        )
        self.assertEqual(identified["record_status"], "FROZEN")
        self.assertEqual(self.bundle.identification.status, "SYNTHETIC_RECOMMENDATION")
        self.assertEqual(self.bundle.validation.status, "SYNTHETIC_RECOMMENDATION")
        self.assertNotEqual(self.bundle.identification.status, self.bundle.historical_status)
        self.assertEqual(
            self.bundle.identification.provenance.commit,
            SYNTHETIC_COMMIT,
        )

    # D
    def test_no_replay_executor_exists(self):
        self.assertFalse(hasattr(sp13_evidence_adapter, "FrozenSP13IdentificationExecutor"))
        self.assertNotIn("FrozenSP13IdentificationExecutor", sp13_evidence_adapter.__all__)
        executor_like = [
            name
            for name, value in vars(sp13_evidence_adapter).items()
            if isinstance(value, type) and "__call__" in vars(value)
        ]
        self.assertEqual(executor_like, [])

    # E / F
    def test_production_runner_refuses_historical_evidence(self):
        historical = self.bundle.identification
        before = historical.to_dict()
        session = self.production_session()

        # Through complete(): the application attaching imported evidence.
        runner = self.runner(session)
        runner.prepare()
        runner.start()
        with self.assertRaises(MaterialIdentificationEvidenceBindingError) as context:
            runner.complete(
                evidence=MaterialIdentificationEvidenceResults(identification=historical),
                evidence_references=(
                    MaterialIdentificationEvidenceReference.from_evidence(
                        historical, session.source_identities
                    ),
                ),
            )
        self.assertEqual(context.exception.reason, "unbound")
        self.assertEqual(runner.record.evidence_references, ())

        # Through an executor that simply returns the imported record (the old replay).
        runner = self.runner(session, executor=lambda *arguments: historical)
        sensitivity = self.bundle.sensitivity
        identifiability = replace(
            self.bundle.identifiability, parent_ids=(sensitivity.evidence_id,)
        )
        with self.assertRaises(MaterialIdentificationEvidenceBindingError):
            runner.run_identification(
                sensitivity,
                MaterialIdentificationEvidenceReference.from_evidence(
                    sensitivity, session.source_identities
                ),
                identifiability,
                MaterialIdentificationEvidenceReference.from_evidence(
                    identifiability, session.source_identities
                ),
            )
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)
        self.assertEqual(runner.record.evidence_references, ())

        # Neither path rebinds or alters the historical record.
        self.assertEqual(historical.to_dict(), before)
        self.assertIsNone(historical.scientific_binding)

    def test_bundle_cannot_hold_bound_evidence(self):
        registration = REGISTRATION
        bound = replace(
            self.bundle.identification,
            scientific_binding=EvidenceScientificBinding.create(
                identification_model_id=EFFECTIVE_FACE_SHEET_MODEL.model_id,
                identification_model_hash=EFFECTIVE_FACE_SHEET_MODEL.definition_hash,
                registration_hash=registration.registration_hash,
                experimental_content_sha256="1" * 64,
            ),
            content_hash=evidence_record_hash(
                self.bundle.identification.content,
                EvidenceScientificBinding.create(
                    identification_model_id=EFFECTIVE_FACE_SHEET_MODEL.model_id,
                    identification_model_hash=EFFECTIVE_FACE_SHEET_MODEL.definition_hash,
                    registration_hash=registration.registration_hash,
                    experimental_content_sha256="1" * 64,
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "only UNBOUND evidence"):
            replace(self.bundle, identification=bound)

    # J / K
    def test_import_is_independent_of_any_session(self):
        self.assertEqual(
            list(inspect.signature(load_frozen_sp13_evidence).parameters), ["analysis_root"]
        )
        first = load_frozen_sp13_evidence(self.analysis_root)
        # Sessions with different registrations exist, but the import never sees them.
        other_registration = _test_registration(translation_x=1.0)
        self.assertNotEqual(other_registration.registration_hash, REGISTRATION.registration_hash)
        self.production_session(registration=other_registration)
        second = load_frozen_sp13_evidence(self.analysis_root)
        for left, right in zip(self.records(first), self.records(second)):
            with self.subTest(left.RECORD_TYPE):
                self.assertEqual(left.content_hash, right.content_hash)
                self.assertEqual(left.evidence_id, right.evidence_id)
                self.assertIsNone(right.scientific_binding)

if __name__ == "__main__":
    unittest.main()
