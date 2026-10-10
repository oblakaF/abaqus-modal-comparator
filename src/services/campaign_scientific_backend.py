"""One backend scientific path for a journalled campaign run — Auto-ID V12-I6 (SPEC v1.2 §1, §6–§9; D-078).

``judge_campaign_run`` reads the campaign definition's explicitly declared scientific question and judges an already
journalled run.  It never executes, solves or extracts anything, and it never converts one question into the other:

* MATERIAL_IDENTIFICATION — the accepted M7 path, unchanged: ``build_campaign_report`` (M5 verdicts, SPEC §13 family
  consistency, the D-076 formal output) after the LM / Jacobian provenance of the journals is verified.  A §13 FAIL
  releases no global value; a calibration is never produced.
* SPECIMEN_ENGINEERING_CALIBRATION — exactly one physical specimen and a declared τ_mf.  The evidence is derived from
  the journals only, never taken from the caller:
  1. the LM history (``campaign_lm_provenance.verify_lm_history``) proves the reconstructed Jacobian at p̂;
  2. every journalled evaluation the Jacobian uses is re-derived from its content-addressed FE pack (job re-rendered
     from the pinned source INP, pack content hash, branch tracking and the objective recomputed against the frozen
     baseline pack): the M5 system is built from genuine evaluations only;
  3. the M5 system is the accepted campaign system (``campaign_m5_system``) on the specimen's FIT rows, and the M5
     evidence chain (rank, statistical_sd, pattern with τ_mf, Birge, leave-one-family-out) is computed on it;
  4. the I3 gate inputs are assembled from that verified evidence; ``build_calibration_output`` (V12-I4) evaluates the
     I3 gate and verifies the candidate evaluation (V12-I5, F1 / F2) on the same system and evaluation.
  A confirmed cluster is a readiness refusal (CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE): no member is paired, ordered,
  averaged or dropped.

Every refusal is a typed readiness state, never a crash and never a silent downgrade.  The readiness record states the
solver profiles and FE sources exactly as journalled and that no HUMAN-authorised production calibration run exists:
the calibration execution gate (``CampaignDefinition.require_executable``) is unchanged, so a judged calibration
journal is evidence for readiness only, never an accepted physical calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping, Optional, Sequence

from domain.campaign_definition import (
    MATERIAL_IDENTIFICATION,
    SPECIMEN_ENGINEERING_CALIBRATION,
    TAU_MF_MAXIMUM,
)
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import canonical_hash

from .branch_tracker import BranchTrackingRefusal, TrackingInputError, track_branches
from .campaign_lm_provenance import LMProvenanceRefusal, VerifiedLMHistory, journal_document, verify_lm_history
from .candidate_evaluation_evidence import (
    CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE,
    CandidateEvaluationEvidence,
    CandidateEvaluationUnverified,
)
from .fe_shape_pack import FEShapePack, shape_pack_content_sha256
from .forward_builder import ForwardBuildError, forward_job_provenance, render_forward_input
from .identification_campaign_run import (
    CampaignError,
    CampaignSpecimenInput,
    build_campaign_report,
    campaign_guards,
    campaign_m5_system,
    row_sigma,
)
from .identification_objective import ObjectiveDesign, ObjectiveInputError, RowSigma, evaluate_objective
from .identification_pipeline import fe_state_from_pack, forward_candidate
from .identification_uncertainty import ResidualTerm, residual_terms
from .identification_verdict import compute_evidence_chain
from .practical_identifiability import PracticalIdentifiabilityInputError
from .specimen_calibration_gate import CalibrationGateInputs, GovernedRow, GovernedTerm, ReportingCompleteness
from .specimen_calibration_output import (
    CalibrationFragmentRefusal,
    CalibrationInpFragment,
    CalibrationOutputRecord,
    ExcludedDiagnosticsEvidence,
    GovernedConstant,
    build_calibration_output,
    governed_baseline_rows,
    governed_engineering_constants,
    render_calibration_inp_fragment,
)

import numpy as np


SCHEMA = "auto-id/v12-scientific-readiness/v1"
PRODUCTION_EXECUTION = ("NOT_AUTHORISED: readiness only; a new production run needs a separate explicit HUMAN "
                        "authorisation (the calibration execution gate is unchanged)")
NO_PRODUCTION_CALIBRATION = ("NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN: calibration execution is refused by "
                             "the execution gate, so this journal is not an accepted physical calibration")


class ReadinessStatus(str, Enum):
    RELEASED = "RELEASED"  # the full calibration chain passed on verified evidence (I4 RELEASED record)
    REFUSED = "REFUSED"  # a scientific judgement was made: no value (calibration gate REFUSED / no global value)
    NOT_READY = "NOT_READY"  # the evidence or the question does not allow a judgement at all
    MATERIAL_VALUES_RELEASED = "MATERIAL_VALUES_RELEASED"  # D-076 formal output VALUES_RELEASED (material question)


class ReadinessRefusal(str, Enum):
    WRONG_SCIENTIFIC_QUESTION = "WRONG_SCIENTIFIC_QUESTION"
    SPECIMEN_COUNT = "SPECIMEN_COUNT"
    TAU_MF_NOT_DECLARED = "TAU_MF_NOT_DECLARED"
    RUN_IDENTITY = "RUN_IDENTITY"
    LM_HISTORY_MISSING = "LM_HISTORY_MISSING"
    LM_HISTORY_UNRELATED = "LM_HISTORY_UNRELATED"
    LM_NOT_CONVERGED = "LM_NOT_CONVERGED"
    LM_EVALUATION_UNVERIFIED = "LM_EVALUATION_UNVERIFIED"
    JACOBIAN_INCONSISTENT = "JACOBIAN_INCONSISTENT"
    FE_EVIDENCE_UNVERIFIED = "FE_EVIDENCE_UNVERIFIED"
    CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE = CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE
    CANDIDATE_EVALUATION_UNVERIFIED = "CANDIDATE_EVALUATION_UNVERIFIED"
    COVARIANCE_NOT_SUPPORTED = "COVARIANCE_NOT_SUPPORTED"
    CALIBRATION_GATE_REFUSED = "CALIBRATION_GATE_REFUSED"
    NO_GLOBAL_PARAMETER_VALUE = "NO_GLOBAL_PARAMETER_VALUE"


@dataclass(frozen=True)
class CampaignRunEvidence:
    """The journalled run as stored: the campaign journal, each specimen's pipeline journal, the content-addressed FE
    packs (content SHA-256 → pack) the evaluations reference, and each specimen's pinned source INP bytes."""

    campaign_journal: Mapping[str, Any]
    pipeline_journals: Mapping[str, Mapping[str, Any]]
    packs: Mapping[str, FEShapePack]
    source_inps: Mapping[str, bytes]


@dataclass(frozen=True)
class ScientificReadiness:
    status: ReadinessStatus
    scientific_question: Optional[str]
    tau_mf: Optional[float]
    campaign: Mapping[str, Any]
    refusal_reasons: tuple[Mapping[str, str], ...]
    evidence: Mapping[str, Any]  # solver profiles and FE sources as journalled; LM provenance when verified
    uncertainty_basis: Optional[Mapping[str, Any]]
    diagnostic_candidate: Optional[Mapping[str, Any]]
    calibration_record: Optional[CalibrationOutputRecord] = None
    material_report: Optional[Mapping[str, Any]] = None

    @property
    def refusal_codes(self) -> tuple[str, ...]:
        return tuple(r["code"] for r in self.refusal_reasons)

    @property
    def released(self) -> bool:
        return self.status is ReadinessStatus.RELEASED and self.calibration_record is not None \
            and self.calibration_record.released

    def to_dict(self) -> dict:
        released = self.released
        return {"schema": SCHEMA, "status": self.status.value, "scientific_question": self.scientific_question,
                "tau_mf": self.tau_mf, "campaign": dict(self.campaign),
                "refusal_reasons": [dict(r) for r in self.refusal_reasons], "evidence": dict(self.evidence),
                "uncertainty_basis": self.uncertainty_basis, "diagnostic_candidate": self.diagnostic_candidate,
                "calibration": None if self.calibration_record is None else self.calibration_record.to_dict(),
                "released_calibration_parameters": (dict(self.calibration_record.calibration_parameters)
                                                    if released else None),
                "material_formal_output": None if self.material_report is None
                else self.material_report.get("formal_output"),
                "material_family_consistency": None if self.material_report is None or not self.material_report.get(
                    "family_consistency") else self.material_report["family_consistency"].get("status"),
                "material_claim": None if self.material_report is None else self.material_report.get("material_claim"),
                "inp_fragment_available": released,
                "production_execution": PRODUCTION_EXECUTION,
                "production_calibration": None if self.scientific_question != SPECIMEN_ENGINEERING_CALIBRATION
                else NO_PRODUCTION_CALIBRATION}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


class _NotReady(Exception):
    def __init__(self, code: ReadinessRefusal, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


def _campaign(definition, run_hash: Optional[str] = None) -> dict:
    return {"campaign_id": definition.campaign_id, "campaign_hash": definition.campaign_hash,
            "run_type": definition.run_type, "specimens": [s.label for s in definition.specimens],
            "run_hash": run_hash}


def _evidence(specimens: Sequence[CampaignSpecimenInput], lm: Optional[VerifiedLMHistory]) -> dict:
    fe_sources = {}
    if lm is not None:
        for item in specimens:
            fe_sources[item.label] = sorted({str((e.get("specimens") or {}).get(item.label, {}).get("fe_source"))
                                             for e in lm.evaluations})
    return {"solver_profiles": {item.label: {"profile_id": item.profile.profile_id,
                                             "profile_hash": item.profile.profile_hash,
                                             "abaqus_release": item.profile.abaqus_release} for item in specimens},
            "fe_sources": fe_sources, "lm_provenance": None if lm is None else lm.to_dict()}


def _not_ready(definition, specimens, code: ReadinessRefusal, detail: str, lm=None) -> ScientificReadiness:
    return ScientificReadiness(ReadinessStatus.NOT_READY, getattr(definition, "scientific_question", None),
                               getattr(definition, "tau_mf", None),
                               _campaign(definition, None if lm is None else lm.run_hash),
                               ({"code": code.value, "detail": detail},), _evidence(specimens, lm), None, None)


def _lm(definition, specimens, evidence: CampaignRunEvidence) -> VerifiedLMHistory:
    if not isinstance(evidence, CampaignRunEvidence):
        raise _NotReady(ReadinessRefusal.LM_HISTORY_MISSING, "no journalled campaign run evidence.")
    try:
        return verify_lm_history(definition, specimens, evidence.campaign_journal, evidence.pipeline_journals)
    except LMProvenanceRefusal as refusal:
        raise _NotReady(ReadinessRefusal(refusal.code), str(refusal)) from refusal


# ----------------------------------------------------------------------------- MATERIAL_IDENTIFICATION (unchanged)

def _material(definition, specimens, evidence: CampaignRunEvidence) -> ScientificReadiness:
    lm = _lm(definition, specimens, evidence)
    _, _, entries = journal_document(evidence.campaign_journal, "campaign")
    evaluations = [dict(e["record"]) for e in entries if e.get("kind") == "evaluation"]
    report = build_campaign_report(definition, specimens, evaluations, dict(lm.result))
    formal = report["formal_output"]
    if formal["status"] == "VALUES_RELEASED":
        status, reasons = ReadinessStatus.MATERIAL_VALUES_RELEASED, ()
    else:
        status = ReadinessStatus.REFUSED
        reasons = tuple({"code": ReadinessRefusal.NO_GLOBAL_PARAMETER_VALUE.value, "detail": str(blocker)}
                        for blocker in formal["blockers"]) or (
            {"code": ReadinessRefusal.NO_GLOBAL_PARAMETER_VALUE.value, "detail": formal["status"]},)
    candidate = {"labels": ["DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"],
                 "parameters": report["optimizer_candidate"]["values"]} if status is ReadinessStatus.REFUSED else None
    return ScientificReadiness(status, definition.scientific_question, definition.tau_mf,
                               _campaign(definition, lm.run_hash), reasons, _evidence(specimens, lm),
                               report["uncertainty_basis"], candidate, material_report=report)


# ----------------------------------------------------------------------------- SPECIMEN_ENGINEERING_CALIBRATION

def _pack(evidence: CampaignRunEvidence, content: object, what: str) -> FEShapePack:
    pack = evidence.packs.get(content) if isinstance(evidence.packs, Mapping) else None
    if not isinstance(pack, FEShapePack):
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, f"the content-addressed FE pack of {what} is missing.")
    recomputed = shape_pack_content_sha256({
        "node_ids": np.array(list(pack.node_ids)), "coordinates": np.asarray(pack.coordinates, dtype=np.float64),
        "mode_numbers": np.array(pack.mode_numbers, dtype=np.int32),
        "frequencies_hz": np.array(pack.frequencies_hz, dtype=np.float64), "displacements": pack.displacements})
    if recomputed != content or pack.record.content_sha256 != content:
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, f"the FE pack of {what} is not its content hash.")
    return pack


def _design(identity: Mapping, specimen: CampaignSpecimenInput) -> ObjectiveDesign:
    design = identity.get("objective_design")
    if not isinstance(design, Mapping):
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, "the pipeline run has no objective design.")
    if design.get("fit_clusters") or design.get("holdout_clusters"):
        raise _NotReady(ReadinessRefusal.CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE,
                        "a confirmed cluster is tracked as a subspace and judged by its pairing-independent mean; "
                        "per-member candidate frequencies and tracking MACs are not evaluated, so no calibration can "
                        "be released (no member pairing, ordering, averaging or dropping)")
    if list(design.get("fit_rows", ())) != list(specimen.spec.fit_rows) \
            or list(design.get("holdout_rows", ())) != list(specimen.spec.holdout_rows):
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, "the pipeline design has other FIT / HOLDOUT rows.")
    try:
        sigmas = {row: RowSigma(**value) for row, value in dict(design["sigmas"]).items()}
    except (KeyError, TypeError, ObjectiveInputError) as exc:
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, f"the pipeline design has no valid σ ({exc}).")
    return ObjectiveDesign(tuple(design["fit_rows"]), (), tuple(design["holdout_rows"]), (), sigmas,
                           specimen.frozen.observation_hash)


def _genuine_evaluations(definition, specimen: CampaignSpecimenInput, lm: VerifiedLMHistory,
                         evidence: CampaignRunEvidence) -> tuple[dict, FEShapePack, FEShapePack, dict, dict]:
    """Re-derive every journalled evaluation the Jacobian uses from its FE pack (step 2 of the module docstring)."""

    document = evidence.pipeline_journals[specimen.label]
    identity, _, entries = journal_document(document, f"{specimen.label} pipeline")
    design = _design(identity, specimen)
    records = {e["record"]["evaluation_hash"]: dict(e["record"]) for e in entries if e.get("kind") == "evaluation"}
    extracted = {e["record"].get("pack_content_sha256") for e in entries if e.get("kind") == "extraction"}
    archived = dict(identity.get("archived_packs") or {})
    source = evidence.source_inps.get(specimen.label) if isinstance(evidence.source_inps, Mapping) else None
    if not isinstance(source, bytes):
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, "the pinned source INP bytes are missing.")
    frozen, expectation = specimen.frozen, specimen.expectation
    baseline_job = frozen.identity.job_name
    baseline_contents = {e["record"].get("pack_content_sha256") for e in entries if e.get("kind") == "extraction"
                         and e["record"].get("job_name") == baseline_job} | (
        {archived[baseline_job]} if baseline_job in archived else set())
    if len(baseline_contents) != 1:
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, "the frozen baseline FE pack is not one journalled "
                                                                 "pack of this pipeline run.")
    baseline_content = next(iter(baseline_contents))
    if frozen.identity.shape_pack_content_sha256 not in (None, baseline_content):
        raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, "the baseline pack is not the frozen set's pack.")
    baseline = _pack(evidence, baseline_content, "the frozen baseline")
    baseline_state = fe_state_from_pack(baseline)
    rows = {row.row_id: row.fe_mode for row in frozen.rows}
    final_hash = lm.final_evaluation["specimens"][specimen.label]["evaluation_hash"]
    final_pack, final_branches = None, None
    for campaign_record in lm.evaluations:
        record = records[campaign_record["specimens"][specimen.label]["evaluation_hash"]]
        what = f"the evaluation at {campaign_record['parameters']}"
        candidate = forward_candidate(specimen.model, definition.full_parameters(campaign_record["parameters"]))
        try:
            rendered = render_forward_input(specimen.model, candidate, source)
        except (ForwardBuildError, TypeError) as exc:
            raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, f"{what}: no forward job ({exc}).")
        provenance = forward_job_provenance(specimen.model, candidate, rendered)
        job_name = provenance["generated_inp"]["job_name"]
        if (record.get("job_name"), record.get("generated_inp_sha256"), record.get("job_hash")) != (
                job_name, rendered.sha256, canonical_hash(provenance)):
            raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED,
                            f"{what}: the journalled job is not the forward job rendered from the pinned source INP.")
        content = record.get("pack_content_sha256")
        if content not in extracted and archived.get(job_name) != content:
            raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, f"{what}: the FE pack is not journalled.")
        pack = _pack(evidence, content, what)
        problems = [label for label, ok in (
            ("job", pack.record.job_name == job_name), ("generated INP", pack.record.generated_inp_sha256
                                                        == rendered.sha256),
            ("FE geometry", pack.record.fe_geometry_sha256 == expectation.fe_geometry_sha256),
            ("node set", pack.record.node_set_sha256 == expectation.node_set_sha256),
            ("modes", tuple(pack.mode_numbers) == tuple(expectation.mode_numbers))) if not ok]
        if problems:
            raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, f"{what}: the FE pack does not match its "
                                                                     f"{', '.join(problems)}.")
        try:
            tracking = track_branches(STRICT_IDENTIFICATION_PAIRING, baseline_state, fe_state_from_pack(pack), rows,
                                      [])
            result = evaluate_objective(design, frozen, tracking)
        except (BranchTrackingRefusal, TrackingInputError, ObjectiveInputError) as exc:
            raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED, f"{what}: not recomputable ({exc}).")
        branches = {b.row_id: b for b in tracking.branches}
        if [t.residual for t in result.fit_terms] != record.get("residuals") \
                or {t.term_id: t.residual for t in result.holdout_terms} != record.get("holdout_residuals") \
                or {r: [b.candidate_mode, b.mac] for r, b in branches.items()} != record.get("tracking"):
            raise _NotReady(ReadinessRefusal.FE_EVIDENCE_UNVERIFIED,
                            f"{what}: the journalled residuals / tracking are not those of its FE pack.")
        if record["evaluation_hash"] == final_hash:
            final_pack, final_branches = pack, branches
    return records[final_hash], final_pack, baseline, final_branches, identity


def _gate_inputs(definition, specimen: CampaignSpecimenInput, lm: VerifiedLMHistory, record: Mapping,
                 branches: Mapping, excluded: ExcludedDiagnosticsEvidence):
    try:
        sigma = row_sigma(definition).sigma
    except CampaignError as exc:
        raise _NotReady(ReadinessRefusal.COVARIANCE_NOT_SUPPORTED, str(exc))
    fit_rows, holdout_rows = specimen.spec.fit_rows, specimen.spec.holdout_rows
    system = campaign_m5_system(definition, lm.jacobian, fit_rows)  # the accepted M5 system on the specimen's rows
    families = specimen.families
    fit = residual_terms(list(fit_rows), [], record["residuals"], families, {r: sigma for r in fit_rows})
    held = [ResidualTerm(r, (r,), families[r], record["holdout_residuals"][r], sigma) for r in holdout_rows]
    label = f"{definition.campaign_id} ({definition.run_type}): specimen engineering calibration"
    chain = compute_evidence_chain(system, fit, held, lm.p_hat, label, definition.tau_mf)
    registration, peak, tracking = campaign_guards(definition, [specimen], lm.journalled_evaluations)
    roles = {**{r: "FIT" for r in fit_rows}, **{r: "HOLDOUT" for r in holdout_rows}}
    terms = [GovernedTerm(t.term_id, "FIT", t.value * t.sigma) for t in fit]
    terms += [GovernedTerm(t.term_id, "HOLDOUT", t.value * t.sigma) for t in held]
    rows = [GovernedRow(r, roles[r], math.log(branches[r].candidate_hz) - math.log(specimen.frozen.row(r).experimental_hz))
            for r in (*fit_rows, *holdout_rows)]
    inputs = CalibrationGateInputs(
        definition=definition, p_hat=dict(lm.p_hat), fit_families={r: families[r] for r in fit_rows},
        holdout_families={r: families[r] for r in holdout_rows}, term_rows={r: (r,) for r in (*fit_rows, *holdout_rows)},
        analysis=chain.analysis, robustness=chain.robustness, pattern=chain.pattern, statistical=chain.statistical,
        birge=chain.birge, baseline_pair_macs={row.row_id: row.mac for row in specimen.frozen.rows
                                               if row.row_id in fit_rows},
        tracking_macs={r: branches[r].mac for r in roles}, branch_pairing=tracking, registration=registration,
        peak_derived_input=peak, candidate_terms=terms, baseline_rows=list(governed_baseline_rows(specimen)),
        candidate_rows=rows, reporting=ReportingCompleteness(True, bool(holdout_rows), bool(excluded.complete), True))
    return inputs, system


def _judged_output(definition, specimen: CampaignSpecimenInput, lm: VerifiedLMHistory,
                   evidence: CampaignRunEvidence) -> CalibrationOutputRecord:
    record, final_pack, baseline, branches, _ = _genuine_evaluations(definition, specimen, lm, evidence)
    excluded = ExcludedDiagnosticsEvidence.from_campaign_rows(
        specimen.excluded_diagnostics, f"campaign_diagnostics.excluded_mode_diagnostics ({specimen.label}, D-076)")
    inputs, system = _gate_inputs(definition, specimen, lm, record, branches, excluded)
    candidate = CandidateEvaluationEvidence(evidence.pipeline_journals[specimen.label], record["evaluation_hash"],
                                            final_pack, baseline, evidence.source_inps[specimen.label], system)
    try:  # V12-I4 evaluates the I3 gate and verifies the candidate evaluation (V12-I5) on this same evidence
        return build_calibration_output(inputs, specimen, lm.run_identity, excluded, candidate)
    except CandidateEvaluationUnverified as exc:
        raise _NotReady(ReadinessRefusal.CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE
                        if CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE in str(exc)
                        else ReadinessRefusal.CANDIDATE_EVALUATION_UNVERIFIED, str(exc)) from exc
    except PracticalIdentifiabilityInputError as exc:
        raise _NotReady(ReadinessRefusal.RUN_IDENTITY, str(exc)) from exc


def _calibration(definition, specimens, evidence: CampaignRunEvidence) -> ScientificReadiness:
    if len(definition.specimens) != 1 or len(specimens) != 1:
        raise _NotReady(ReadinessRefusal.SPECIMEN_COUNT, f"{SPECIMEN_ENGINEERING_CALIBRATION} requires exactly one "
                                                         "physical specimen (SPEC v1.2 §6).")
    tau = definition.tau_mf
    if isinstance(tau, bool) or not isinstance(tau, (int, float)) or not math.isfinite(tau) \
            or not 0.0 < tau <= TAU_MF_MAXIMUM:
        raise _NotReady(ReadinessRefusal.TAU_MF_NOT_DECLARED, f"τ_mf must be declared with 0 < τ_mf ≤ "
                                                              f"{TAU_MF_MAXIMUM} (SPEC v1.2 §3).")
    lm = _lm(definition, specimens, evidence)
    try:
        output = _judged_output(definition, specimens[0], lm, evidence)
    except _NotReady as refusal:
        return _not_ready(definition, specimens, refusal.code, refusal.detail, lm)
    if output.released:
        status, reasons, diagnostic = ReadinessStatus.RELEASED, (), None
    else:
        status = ReadinessStatus.REFUSED
        reasons = tuple({"code": ReadinessRefusal.CALIBRATION_GATE_REFUSED.value,
                         "detail": f"{r['code']}: {r['detail']}"} for r in output.refusal_reasons)
        diagnostic = dict(output.diagnostic_optimizer_candidate)
    return ScientificReadiness(status, definition.scientific_question, tau, _campaign(definition, lm.run_hash),
                               reasons, _evidence(specimens, lm), dict(output.uncertainty_basis), diagnostic,
                               calibration_record=output)


def judge_campaign_run(definition, specimens: Sequence[CampaignSpecimenInput],
                       evidence: CampaignRunEvidence) -> ScientificReadiness:
    """The one backend path: dispatch on the declared question; never a fallback from one question to the other."""

    specimens = tuple(specimens)
    question = getattr(definition, "scientific_question", None)
    try:
        if question == SPECIMEN_ENGINEERING_CALIBRATION:
            return _calibration(definition, specimens, evidence)
        if question in (MATERIAL_IDENTIFICATION, None):  # None: a v1 (historical) material-identification campaign
            return _material(definition, specimens, evidence)
        raise _NotReady(ReadinessRefusal.WRONG_SCIENTIFIC_QUESTION, f"undeclared scientific question {question!r}.")
    except _NotReady as refusal:
        return _not_ready(definition, specimens, refusal.code, refusal.detail)


def judge_specimen_calibration(definition, specimens: Sequence[CampaignSpecimenInput],
                               evidence: CampaignRunEvidence) -> ScientificReadiness:
    """The calibration question only: any other declared question is a refusal, never converted into calibration."""

    if getattr(definition, "scientific_question", None) != SPECIMEN_ENGINEERING_CALIBRATION:
        return _not_ready(definition, tuple(specimens), ReadinessRefusal.WRONG_SCIENTIFIC_QUESTION,
                          f"the campaign declares {getattr(definition, 'scientific_question', None)!r}, not "
                          f"{SPECIMEN_ENGINEERING_CALIBRATION}; a material campaign is never turned into a "
                          "calibration (no fallback)")
    return judge_campaign_run(definition, specimens, evidence)


def released_engineering_constants(readiness: ScientificReadiness) -> dict[str, GovernedConstant]:
    """The nine governed Engineering Constants (V12-I4) — only for a RELEASED readiness record; nothing is computed
    here beyond the accepted ``governed_engineering_constants`` (M8.6 read-only preview)."""

    if not isinstance(readiness, ScientificReadiness) or not readiness.released:
        raise CalibrationFragmentRefusal("Engineering Constants are available only for a RELEASED specimen calibration.")
    return governed_engineering_constants(readiness.calibration_record)


def released_inp_fragment(readiness: ScientificReadiness, source_inp_bytes: bytes) -> CalibrationInpFragment:
    """The optional calibration INP fragment (V12-I4, fail-closed) — only for a RELEASED readiness record."""

    if not isinstance(readiness, ScientificReadiness) or not readiness.released:
        raise CalibrationFragmentRefusal("an INP fragment is available only for a RELEASED specimen calibration.")
    record = readiness.calibration_record
    return render_calibration_inp_fragment(record, governed_engineering_constants(record), source_inp_bytes)


def _values(parameters: Optional[Mapping], suffix: str) -> str:
    if not parameters:
        return ""
    items = []
    for name, item in sorted(parameters.items()):
        value = item.get("value") if isinstance(item, Mapping) else item
        unit = item.get("unit") if isinstance(item, Mapping) else None
        items.append(f"{name} = {float(value):.6g}{'' if not unit else ' ' + unit}")
    return f"{', '.join(items)} ({suffix})"


def readiness_presentation(record: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Display rows of a stored readiness record (``ScientificReadiness.to_dict``) for any interface (GUI, CLI).

    Presentation only: every value is read from the record; nothing is judged, recomputed, rounded into a decision or
    inferred.  A calibration value is shown only when the record is RELEASED with released parameters.
    """

    if not isinstance(record, Mapping) or record.get("schema") != SCHEMA:
        return ()
    question = record.get("scientific_question")
    calibration = question == SPECIMEN_ENGINEERING_CALIBRATION
    tau = record.get("tau_mf")
    campaign = record.get("campaign") or {}
    codes = [r.get("code") for r in record.get("refusal_reasons") or ()]
    basis = record.get("uncertainty_basis") or {}
    components = basis.get("covariance_components") or {}
    candidate = record.get("diagnostic_candidate") or {}
    evidence = record.get("evidence") or {}
    released = record.get("status") == ReadinessStatus.RELEASED.value and record.get("released_calibration_parameters")
    formal = record.get("material_formal_output") or {}
    if calibration:
        material = "not applicable: a specimen engineering calibration is not a material property"
    elif formal:
        material = formal.get("status", "")
        if record.get("material_family_consistency") == "FAIL":
            material += " (SPEC §13 family consistency FAIL: no global material property)"
        if formal.get("released_values"):
            material += f"; released {_values(formal['released_values'], 'effective model parameters')}"
    else:
        material = "not judged"
    profiles = "; ".join(f"{label}: {item.get('profile_id')}" for label, item in
                         sorted((evidence.get("solver_profiles") or {}).items()))
    sources = "; ".join(f"{label}: {', '.join(values)}" for label, values in
                        sorted((evidence.get("fe_sources") or {}).items()))
    from .auto_id_wizard import material_verdict  # presentation only (the wizard imports no backend)

    return material_verdict(record) + (  # audit V1: the material verdict first, then the calibration verdict
        ("Scientific question", question or "not declared (v1 material identification)"),
        ("Readiness", str(record.get("status", ""))),
        ("τ_mf", "not declared" if tau is None else f"{tau:g} in |Δ ln f| (acceptance tolerance only; never an "
                                                    "uncertainty)"),
        ("Campaign identity", f"{campaign.get('campaign_id')}; campaign {str(campaign.get('campaign_hash'))[:12]}; "
                              f"run {str(campaign.get('run_hash') or 'not verified')[:12]}"),
        ("Refusal reasons", "; ".join(f"{r.get('code')}: {r.get('detail')}" for r in record.get("refusal_reasons") or ())
         or "none"),
        ("Uncertainty", "not evaluated" if not basis else
         f"{basis.get('basis') or basis.get('statistical_sd_status')} (Σ_setup {components.get('sigma_setup')}; "
         f"Σ_meas {components.get('sigma_meas')})"),
        ("Released calibration", _values(released, "SPECIMEN_ENGINEERING_CALIBRATION; not a material property")
         if released else "none released"),
        ("Diagnostic-only candidate", _values(candidate.get("parameters"), ", ".join(candidate.get("labels") or ()))
         or "none"),
        ("Cluster member evidence", "NOT AVAILABLE: a confirmed cluster cannot be released"
         if CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE in codes else "no cluster refusal recorded"),
        ("Global material value", material),
        ("Evidence", f"solver profiles {profiles or 'none'}; FE sources {sources or 'none'}"),
        ("Production execution", str(record.get("production_execution", ""))),
        ("Production calibration", str(record.get("production_calibration") or "not applicable")),
    )


__all__ = ["CampaignRunEvidence", "ReadinessRefusal", "ReadinessStatus", "ScientificReadiness", "judge_campaign_run",
           "judge_specimen_calibration", "readiness_presentation", "released_inp_fragment"]
