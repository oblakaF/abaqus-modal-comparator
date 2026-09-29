from __future__ import annotations

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
    evidence_content_hash,
    evidence_record_hash,
)
from domain.identification_model import STAGE_A_BENDING_MODEL
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
    IdentificationExecutionOutput,
    MaterialIdentificationEvidenceBindingError,
    MaterialIdentificationEvidenceResults,
    MaterialIdentificationIdentificationExecutionError,
    MaterialIdentificationMissingIdentifiabilityError,
    MaterialIdentificationMissingSensitivityError,
    MaterialIdentificationRunner,
    MaterialIdentificationRunStatus,
    MaterialIdentificationSourceMismatchError,
)
from services.inverse_solver import (
    InverseIdentificationResult,
    ModeAssignment,
    OptimizationHistoryEntry,
    PairingResult,
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


class _MockIdentificationExecutor:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def __call__(self, session, sensitivity, identifiability):
        self.calls.append((session, sensitivity, identifiability))
        if self.error is not None:
            raise self.error
        return self.output


class MaterialIdentificationIdentificationRunnerTests(unittest.TestCase):
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
        self.identification_source = self.source(
            "SP13-identification", "identification-output", "6"
        )
        self.provenance = EvidenceProvenance(
            producer="injected mock identification executor",
            producer_version="test-1",
            method="supplied inverse result",
            artifacts=(
                self.experimental_artifact,
                self.identification_source,
            ),
            details={"mathematics_changed": False},
        )
        # InverseIdentificationResult is produced only by the Stage-A inverse
        # solver, so the session identifies the Stage-A bending model.
        task = MaterialIdentificationTaskDefinition(
            model=STAGE_A_BENDING_MODEL,
            selected_parameter_ids=("D11", "D12", "D66"),
            parameter_bounds={
                "D11": ParameterBounds(5.0, 50.0, "N·m"),
                "D12": ParameterBounds(-10.0, 10.0, "N·m"),
                "D66": ParameterBounds(1.0, 20.0, "N·m"),
            },
            weighting_selection="U",
            provenance=self.provenance,
        )
        self.session = MaterialIdentificationSession.create(
            session_id="identification-session",
            created_at=datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc),
            task_definition=task,
            source_identities=self.sources,
            registration=REGISTRATION,
        )
        # Inputs are session-bound, as the C5-R2 runner produces them.
        self.sensitivity = self.sensitivity_input()
        self.identifiability = self.identifiability_input(self.sensitivity)
        self.sensitivity_reference = self.reference(self.sensitivity)
        self.identifiability_reference = self.reference(self.identifiability)
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

    def reference(self, evidence):
        return MaterialIdentificationEvidenceReference.from_evidence(
            evidence, self.sources
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

    def inverse_result(self):
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
                    transformed_parameters=(
                        math.log(12.0),
                        math.log(5.0),
                        math.atanh(0.2),
                    ),
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
            identifiability_metadata_reference=self.identifiability.evidence_id,
            weighting_mode="mock_U",
            global_success=True,
            global_stage_acceptable=True,
            global_message="supplied",
            local_success=True,
            local_message="supplied",
            success=True,
        )

    def output(self, *, sources=None):
        return IdentificationExecutionOutput(
            result=self.inverse_result(),
            model_id="U",
            source_identities=sources or self.sources,
            source_identity=self.identification_source,
            provenance=self.provenance,
            timestamp=self.evidence_timestamp,
            status="COMPLETED",
            parameter_unit="N·m",
            uncertainty={
                "D11": {"standard_deviation": 0.1, "unit": "N·m"},
                "D12": {"standard_deviation": 0.2, "unit": "N·m"},
                "D66": {"standard_deviation": 0.03, "unit": "N·m"},
            },
        )

    def runner(self, executor):
        return MaterialIdentificationRunner(
            self.session,
            run_id="identification-run",
            clock=self.clock(),
            identification_executor=executor,
        )

    def execute(self, runner):
        return runner.run_identification(
            self.sensitivity,
            self.sensitivity_reference,
            self.identifiability,
            self.identifiability_reference,
        )

    def test_mock_executor_creates_typed_identification_evidence(self):
        executor = _MockIdentificationExecutor(self.output())

        completed = self.execute(self.runner(executor))

        self.assertEqual(
            executor.calls,
            [(self.session, self.sensitivity, self.identifiability)],
        )
        self.assertEqual(completed.run.status, MaterialIdentificationRunStatus.COMPLETED)
        evidence = completed.evidence.identification
        self.assertIsInstance(evidence, IdentificationEvidence)
        self.assertEqual(
            evidence.parent_ids,
            (self.sensitivity.evidence_id, self.identifiability.evidence_id),
        )
        self.assertEqual(evidence.timestamp, self.evidence_timestamp)
        self.assertEqual(evidence.source_identity, self.identification_source)
        self.assertEqual(evidence.provenance, self.provenance)
        self.assertEqual(evidence.status, "COMPLETED")
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
        model = evidence.content["identified_properties"]["models"]["U"]
        # The adapter's content key is still named properties_MPa (C5-R1);
        # the values and the declared unit are Stage-A N·m.
        self.assertEqual(model["properties_MPa"]["D12"], 2.4)
        self.assertEqual(model["parameter_unit"], "N·m")
        self.assertEqual(
            tuple(model["properties_MPa"]),
            self.session.task_definition.model.parameter_ids,
        )
        self.assertEqual(
            model["uncertainty"]["D12"]["standard_deviation"], 0.2
        )
        self.assertEqual(
            evidence.content["inverse_result"]["warnings"],
            ("Mock warning preserved.",),
        )
        self.assertEqual(
            completed.run.evidence_references[0].source_identities,
            self.sources,
        )

    def test_missing_prerequisites_are_rejected_before_executor_call(self):
        executor = _MockIdentificationExecutor(self.output())
        with self.assertRaises(MaterialIdentificationMissingSensitivityError):
            self.runner(executor).run_identification(
                None, None, self.identifiability, self.identifiability_reference
            )

        runner = self.runner(executor)
        with self.assertRaises(MaterialIdentificationMissingIdentifiabilityError):
            runner.run_identification(
                self.sensitivity, self.sensitivity_reference, None, None
            )

        self.assertEqual(executor.calls, [])
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.READY)

    def test_executor_failure_records_failed_lifecycle(self):
        runner = self.runner(
            _MockIdentificationExecutor(error=RuntimeError("mock inverse failed"))
        )

        with self.assertRaisesRegex(
            MaterialIdentificationIdentificationExecutionError,
            "mock inverse failed",
        ):
            self.execute(runner)

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)
        self.assertEqual(runner.record.errors, ("mock inverse failed",))

    def sensitivity_input(self, binding="session", evidence_id="sensitivity-input", content=None):
        return SensitivityEvidence.create(
            evidence_id=evidence_id,
            timestamp=datetime(2026, 9, 27, 8, 15, tzinfo=timezone.utc),
            source_identity=self.sensitivity_source,
            provenance=self.provenance,
            status="COMPLETED",
            content=content or {"raw_sensitivity_matrix": ()},
            scientific_binding=self.session_binding() if binding == "session" else binding,
        )

    def identifiability_input(self, sensitivity, binding="session", evidence_id="identifiability-input"):
        return IdentifiabilityEvidence.create(
            evidence_id=evidence_id,
            timestamp=datetime(2026, 9, 27, 8, 30, tzinfo=timezone.utc),
            source_identity=self.identifiability_source,
            provenance=self.provenance,
            status="COMPLETED",
            parent_ids=(sensitivity.evidence_id,),
            content={"models": {"U": {"numerical_rank": 3}}},
            scientific_binding=self.session_binding() if binding == "session" else binding,
        )

    def session_binding(self, **changes):
        registration = self.session.registration_reference
        fields = {
            "identification_model_id": self.session.task_definition.identification_model_id,
            "identification_model_hash": self.session.task_definition.identification_model_hash,
            "registration_hash": registration.registration_hash,
            "experimental_content_sha256": registration.experimental_content_sha256,
        }
        fields.update(changes)
        return EvidenceScientificBinding.create(**fields)

    def prebuilt(self, binding, parent_ids=None, evidence_id="prebuilt-identification"):
        if parent_ids is None:
            parent_ids = (self.sensitivity.evidence_id, self.identifiability.evidence_id)
        return IdentificationEvidence.create(
            evidence_id=evidence_id,
            timestamp=self.evidence_timestamp,
            source_identity=EvidenceSourceIdentity(
                source_id="external-identification", source_type="external-executor"
            ),
            provenance=EvidenceProvenance(producer="external identification producer"),
            status="COMPLETED",
            parent_ids=parent_ids,
            content={"identified_properties": {"models": {}}},
            scientific_binding=binding,
        )

    # G / N / P
    def test_prebuilt_evidence_with_exact_binding_is_accepted_unchanged(self):
        prebuilt = self.prebuilt(self.session_binding())
        before = prebuilt.to_dict()
        completed = self.execute(self.runner(_MockIdentificationExecutor(prebuilt)))

        accepted = completed.evidence.identification
        self.assertIs(accepted, prebuilt)
        self.assertEqual(accepted.to_dict(), before)
        self.assertEqual(accepted.evidence_id, "prebuilt-identification")
        self.assertEqual(accepted.source_identity.source_id, "external-identification")
        self.assertEqual(accepted.provenance.producer, "external identification producer")
        reference = completed.run.evidence_references[0]
        self.assertEqual(reference.evidence_id, prebuilt.evidence_id)
        self.assertEqual(reference.content_hash, prebuilt.content_hash)
        self.assertEqual(completed.run.status, MaterialIdentificationRunStatus.COMPLETED)

    # H / I / J / K / O
    def test_prebuilt_evidence_without_exact_binding_is_refused(self):
        cases = {
            "unbound": None,
            "model": self.session_binding(identification_model_hash="d" * 64),
            "registration": self.session_binding(registration_hash="e" * 64),
            "experimental_content": self.session_binding(experimental_content_sha256="f" * 64),
        }
        for reason, binding in cases.items():
            with self.subTest(reason):
                prebuilt = self.prebuilt(binding)
                before = prebuilt.to_dict()
                runner = self.runner(_MockIdentificationExecutor(prebuilt))
                with self.assertRaises(MaterialIdentificationEvidenceBindingError) as context:
                    self.execute(runner)
                self.assertEqual(context.exception.reason, reason)
                self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)
                self.assertEqual(runner.record.evidence_references, ())
                # No relabelling: the refused record is untouched and still carries
                # whatever binding (or none) it arrived with.
                self.assertEqual(prebuilt.to_dict(), before)
                self.assertEqual(prebuilt.scientific_binding, binding)

    # L
    def test_matching_source_labels_cannot_rescue_wrong_registration(self):
        record = self.prebuilt(self.session_binding(registration_hash="e" * 64))
        reference = MaterialIdentificationEvidenceReference.from_evidence(record, self.sources)
        self.assertEqual(reference.source_identities, self.session.source_identities)
        runner = self.runner(_MockIdentificationExecutor())
        runner.prepare()
        runner.start()
        with self.assertRaises(MaterialIdentificationEvidenceBindingError) as context:
            runner.complete(
                evidence=MaterialIdentificationEvidenceResults(identification=record),
                evidence_references=(reference,),
            )
        self.assertEqual(context.exception.reason, "registration")
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.RUNNING)
        self.assertEqual(runner.record.evidence_references, ())

    # M
    def test_exact_binding_does_not_override_the_descriptive_source_policy(self):
        # Existing policy is kept: an execution output labelled for other sources
        # is refused even though the evidence the runner would build is bound to
        # this session.  (A prebuilt record carries no session labels, so for it
        # the scientific binding is the only check.)
        other_sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP14", source_label="SP14-experimental"
        )
        runner = self.runner(_MockIdentificationExecutor(self.output(sources=other_sources)))
        with self.assertRaises(MaterialIdentificationSourceMismatchError):
            self.execute(runner)
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)

    def test_complete_refuses_unbound_evidence_supplied_directly(self):
        unbound = self.prebuilt(None)
        runner = self.runner(_MockIdentificationExecutor())
        runner.prepare()
        runner.start()
        with self.assertRaises(MaterialIdentificationEvidenceBindingError) as context:
            runner.complete(
                evidence=MaterialIdentificationEvidenceResults(identification=unbound),
                evidence_references=(
                    MaterialIdentificationEvidenceReference.from_evidence(unbound, self.sources),
                ),
            )
        self.assertEqual(context.exception.reason, "unbound")

    def run_with_inputs(self, sensitivity, identifiability, executor):
        runner = self.runner(executor)
        result = runner.run_identification(
            sensitivity,
            self.reference(sensitivity),
            identifiability,
            self.reference(identifiability),
        )
        return runner, result

    # A / I
    def test_bound_inputs_reach_the_executor_and_become_parents(self):
        executor = _MockIdentificationExecutor(self.output())
        runner, completed = self.run_with_inputs(self.sensitivity, self.identifiability, executor)
        self.assertEqual(len(executor.calls), 1)
        evidence = completed.evidence.identification
        self.assertEqual(
            evidence.parent_ids,
            (self.sensitivity.evidence_id, self.identifiability.evidence_id),
        )
        self.assertEqual(evidence.scientific_binding, self.sensitivity.scientific_binding)
        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.COMPLETED)

    # B / C / D / E / F / G / H / Q / R / S
    def test_invalid_input_chains_are_refused_before_execution(self):
        other_registration = self.session_binding(registration_hash="e" * 64)
        cases = (
            ("sensitivity UNBOUND", None, "session", "sensitivity_unbound"),
            ("identifiability UNBOUND", "session", None, "identifiability_unbound"),
            ("sensitivity wrong model", self.session_binding(identification_model_hash="d" * 64),
             "session", "input_binding_mismatch"),
            ("sensitivity wrong registration", other_registration, "session", "input_binding_mismatch"),
            ("sensitivity wrong experiment", self.session_binding(experimental_content_sha256="f" * 64),
             "session", "input_binding_mismatch"),
            ("identifiability wrong model", "session",
             self.session_binding(identification_model_id="effective_face_sheet"), "input_binding_mismatch"),
            ("identifiability wrong registration", "session", other_registration, "input_binding_mismatch"),
            ("inputs bound to two other bindings", other_registration,
             self.session_binding(registration_hash="9" * 64), "input_binding_mismatch"),
            ("both inputs bound to another registration", other_registration, other_registration,
             "sensitivity_binding"),
        )
        for name, sensitivity_binding, identifiability_binding, reason in cases:
            with self.subTest(name):
                sensitivity = self.sensitivity_input(binding=sensitivity_binding)
                identifiability = self.identifiability_input(sensitivity, binding=identifiability_binding)
                executor = _MockIdentificationExecutor(self.output())
                runner = self.runner(executor)
                with self.assertRaises(MaterialIdentificationEvidenceBindingError) as context:
                    runner.run_identification(
                        sensitivity,
                        self.reference(sensitivity),
                        identifiability,
                        self.reference(identifiability),
                    )
                self.assertEqual(context.exception.reason, reason)
                self.assertEqual(executor.calls, [])
                self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)
                self.assertEqual(runner.record.evidence_references, ())
                self.assertEqual(runner.record.errors, (str(context.exception),))

    # J
    def test_prebuilt_output_with_exact_binding_and_parents_is_accepted(self):
        prebuilt = self.prebuilt(self.session_binding())
        completed = self.execute(self.runner(_MockIdentificationExecutor(prebuilt)))
        self.assertIs(completed.evidence.identification, prebuilt)
        self.assertEqual(
            prebuilt.parent_ids, (self.sensitivity.evidence_id, self.identifiability.evidence_id)
        )

    # K / L / M / N / P
    def test_prebuilt_output_must_derive_from_exactly_the_supplied_inputs(self):
        # Same scientific binding, different record: compatibility is not ancestry.
        sibling = self.sensitivity_input(
            evidence_id="sensitivity-sibling", content={"raw_sensitivity_matrix": ({"row": 1},)}
        )
        self.assertEqual(sibling.scientific_binding, self.sensitivity.scientific_binding)
        self.assertNotEqual(sibling.content_hash, self.sensitivity.content_hash)
        sensitivity_id = self.sensitivity.evidence_id
        identifiability_id = self.identifiability.evidence_id
        cases = {
            "empty": (),
            "only sensitivity": (sensitivity_id,),
            "wrong sensitivity id": ("sensitivity-from-another-run", identifiability_id),
            "wrong identifiability id": (sensitivity_id, "identifiability-from-another-run"),
            "extra parent": (sensitivity_id, identifiability_id, "unrelated-evidence"),
            "reversed order": (identifiability_id, sensitivity_id),
            "sibling sensitivity": (sibling.evidence_id, identifiability_id),
        }
        for name, parents in cases.items():
            with self.subTest(name):
                prebuilt = self.prebuilt(self.session_binding(), parent_ids=parents)
                before = prebuilt.to_dict()
                runner = self.runner(_MockIdentificationExecutor(prebuilt))
                with self.assertRaises(MaterialIdentificationEvidenceBindingError) as context:
                    self.execute(runner)
                self.assertEqual(context.exception.reason, "parent_ids")
                self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)
                self.assertEqual(runner.record.evidence_references, ())
                self.assertEqual(prebuilt.to_dict(), before)

    # O
    def test_duplicate_parent_ids_cannot_even_be_constructed(self):
        with self.assertRaisesRegex(ValueError, "parent_ids must be unique"):
            self.prebuilt(
                self.session_binding(),
                parent_ids=(self.sensitivity.evidence_id, self.sensitivity.evidence_id),
            )

    def test_source_mismatch_fails_after_executor_output(self):
        # Descriptive source-label mismatch only.  It does not prove scientific
        # registration/model compatibility (C5 EVIDENCE BINDING GAP).
        other_sources = MaterialIdentificationSourceIdentities(
            specimen_label="SP14",
            source_label="SP14-experimental",
            source_uri="project://SP14/SP14-experimental",
        )
        runner = self.runner(
            _MockIdentificationExecutor(self.output(sources=other_sources))
        )

        with self.assertRaisesRegex(
            MaterialIdentificationSourceMismatchError,
            "does not match session sources",
        ):
            self.execute(runner)

        self.assertEqual(runner.record.status, MaterialIdentificationRunStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
