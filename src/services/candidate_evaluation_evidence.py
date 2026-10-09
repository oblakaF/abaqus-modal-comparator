"""Candidate-evaluation evidence of a specimen calibration — Auto-ID V12-I5, finding F1 (SPEC v1.2 §6–§9; D-078).

A calibration value may be released only for the candidate that was actually evaluated.  The authoritative source is
the specimen's M4 identification-pipeline journal (hash-chained; its run identity names the forward model, the frozen
observation set, the solver profile and, in ``extra``, the calibration run hash and specimen) together with the
content-addressed FE shape packs it references.  ``verify_candidate_evaluation`` re-derives from that source, and
only from it, what the calibration gate judges, and compares every caller-supplied value with it:

A. p̂ — the journalled evaluation's candidate parameters are exactly the campaign's full parameters at p̂;
B. governed terms and signed residuals — branch tracking and the log-frequency objective are recomputed from the frozen
   baseline FE pack and the candidate FE pack (``track_branches`` / ``evaluate_objective``) and must equal the
   journalled residuals; the gate's candidate terms must be those Δ ln f;
C. physical candidate rows and their tracking MACs — the tracked FE frequency and MAC of each row;
D. the residual-pattern record — recomputed from the verified terms and the declared τ_mf;
E. M5 evidence — the practical-identifiability analysis, statistical_sd, Birge and model_form_robustness are recomputed
   from the M5 system (whose hash the records carry) with the verified FIT terms at p̂;
F. FE identity — the candidate's forward job is re-rendered from the pinned source INP (generated INP SHA-256, job
   name, job hash), both packs' content hashes are recomputed, the packs belong to the specimen's FE geometry, node set
   and modes, the baseline pack to the frozen baseline job, and both are journalled by the same run.

Nothing is computed from caller-supplied p̂ or residual arrays: they are only compared with the re-derived ones.

A confirmed cluster is refused as unverified (CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE): M4 tracks a cluster as a
two-mode subspace and its objective term is the pairing-independent mean (``cluster_log_residual``), so the per-member
candidate frequencies and tracking MACs that the calibration gate judges row by row do not exist in the evaluation.

Pure: reads no file, writes nothing, runs nothing.  It verifies the journal, not the solver: the verified record names
the solver profile and the FE source (``fe_source``) exactly as journalled; synthetic fake-solver runs stay visible as
such through their solver profile.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

import numpy as np

from domain.frozen_observations import FrozenObservationSet
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import JOURNAL_SCHEMA, RunIdentityError, canonical_hash, verify_journal_chain

from .branch_tracker import BranchTrackingRefusal, TrackingInputError, track_branches
from .fe_shape_pack import FEShapePack, shape_pack_content_sha256
from .forward_builder import ForwardBuildError, forward_job_provenance, render_forward_input
from .identification_campaign_run import CampaignSpecimenInput
from .identification_objective import ObjectiveDesign, ObjectiveInputError, RowSigma, evaluate_objective
from .identification_pipeline import fe_state_from_pack, forward_candidate
from .identification_uncertainty import (
    ResidualTerm,
    birge_adjustment,
    residual_pattern_test,
    residual_terms,
    statistical_sd,
)
from .model_form_robustness import linearised_model_form_robustness
from .practical_identifiability import (
    PracticalIdentifiabilityInputError,
    PracticalSystem,
    analyse_practical_identifiability,
)


SCHEMA = "auto-id/v12-candidate-evaluation/v1"
VERIFICATION = "VERIFIED_AGAINST_SPECIMEN_PIPELINE_JOURNAL"
CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE = "CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE"
_TOLERANCE = {"rel_tol": 1e-9, "abs_tol": 1e-12}  # the gate's numerical binding of one candidate


class CandidateEvaluationUnverified(PracticalIdentifiabilityInputError):
    """The calibration evidence is not the verified evaluation of one candidate: an input error, never a record."""


@dataclass(frozen=True)
class CandidateEvaluationEvidence:
    """The authoritative evaluation behind a calibration bundle (V12 companion evidence; no historical record changes).

    ``pipeline_journal`` is the specimen pipeline journal document exactly as stored (schema, run_hash, run_identity,
    entries); ``evaluation_hash`` selects the judged evaluation; the packs are the content-addressed FE results it and
    the frozen baseline reference; ``source_inp`` are the pinned source INP bytes; ``system`` is the M5 system.
    """

    pipeline_journal: Mapping[str, Any]
    evaluation_hash: str
    candidate_pack: FEShapePack
    baseline_pack: FEShapePack
    source_inp: bytes
    system: PracticalSystem


@dataclass(frozen=True)
class VerifiedCandidateEvaluation:
    pipeline_run_hash: str
    evaluation_hash: str
    candidate_hash: str
    candidate_parameters: Mapping[str, float]
    job_name: str
    generated_inp_sha256: str
    job_hash: str
    candidate_pack_content_sha256: str
    baseline_pack_content_sha256: str
    fe_source: str
    solver_profile_id: str
    solver_profile_hash: str
    system_hash: str

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "verification": VERIFICATION, "pipeline_run_hash": self.pipeline_run_hash,
                "evaluation_hash": self.evaluation_hash, "candidate_hash": self.candidate_hash,
                "candidate_parameters": dict(sorted(self.candidate_parameters.items())), "job_name": self.job_name,
                "generated_inp_sha256": self.generated_inp_sha256, "job_hash": self.job_hash,
                "candidate_pack_content_sha256": self.candidate_pack_content_sha256,
                "baseline_pack_content_sha256": self.baseline_pack_content_sha256, "fe_source": self.fe_source,
                "solver_profile_id": self.solver_profile_id, "solver_profile_hash": self.solver_profile_hash, "system_hash": self.system_hash}


def _fail(message: str):
    raise CandidateEvaluationUnverified(f"candidate evaluation not verified: {message}")


def _pack_content_sha256(pack: FEShapePack) -> str:
    """The pack's content hash recomputed from its arrays (the extraction contract's dtypes)."""
    return shape_pack_content_sha256({
        "node_ids": np.array(list(pack.node_ids)), "coordinates": np.asarray(pack.coordinates, dtype=np.float64),
        "mode_numbers": np.array(pack.mode_numbers, dtype=np.int32),
        "frequencies_hz": np.array(pack.frequencies_hz, dtype=np.float64), "displacements": pack.displacements})


def _journal(evidence: CandidateEvaluationEvidence) -> tuple[dict, str, list]:
    document = evidence.pipeline_journal
    if not isinstance(document, Mapping) or document.get("schema") != JOURNAL_SCHEMA:
        _fail("the pipeline journal document is missing or has another schema.")
    identity, entries = document.get("run_identity"), document.get("entries")
    if not isinstance(identity, Mapping) or not isinstance(entries, list):
        _fail("the pipeline journal has no run identity or entries.")
    run_hash = canonical_hash(dict(identity))
    if document.get("run_hash") != run_hash:
        _fail("the pipeline journal's run hash is not the hash of its run identity.")
    try:
        verify_journal_chain(run_hash, entries)
    except (RunIdentityError, KeyError, TypeError) as exc:
        _fail(f"the pipeline journal's hash chain is broken ({exc}).")
    return dict(identity), run_hash, entries


def _bind_run(identity: Mapping, inputs, specimen: CampaignSpecimenInput, run_identity: Mapping) -> ObjectiveDesign:
    definition, model, frozen = inputs.definition, specimen.model, specimen.frozen
    expected = {
        "forward model": {"forward_model_id": model.manifest.forward_model_id,
                          "manifest_hash": model.manifest.manifest_hash,
                          "passport_manifest_hash": model.passport.manifest_hash},
        "solver profile": specimen.profile.profile_hash,
        "frozen observation set": frozen.observation_hash,
        "pairing policy": frozen.policy_hash,
        "calibration run": {"campaign_hash": canonical_hash(dict(run_identity)), "specimen": specimen.label,
                            "run_type": definition.run_type},
        "start (frozen baseline candidate)": {k: float(v) for k, v in
                                              sorted(definition.full_parameters(definition.start).items())},
    }
    found = {"forward model": identity.get("forward_model"), "solver profile": identity.get("solver_profile_hash"),
             "frozen observation set": identity.get("observation_hash"),
             "pairing policy": identity.get("pairing_policy_hash"), "calibration run": identity.get("extra"),
             "start (frozen baseline candidate)": identity.get("start")}
    wrong = [name for name in expected if found[name] != expected[name]]
    if wrong:
        _fail(f"the pipeline run belongs to another {', '.join(wrong)}.")
    if frozen.policy_hash != STRICT_IDENTIFICATION_PAIRING.policy_hash:
        _fail("the frozen set was not paired with the strict identification policy.")
    design = identity.get("objective_design")
    if not isinstance(design, Mapping):
        _fail("the pipeline run has no objective design.")
    if design.get("fit_clusters") or design.get("holdout_clusters") \
            or any(len(rows) != 1 for rows in inputs.term_rows.values()):
        _fail(f"{CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE}: a confirmed cluster is tracked as a subspace and judged by "
              "its pairing-independent mean; per-member candidate frequencies and tracking MACs are not evaluated.")
    if list(design.get("fit_rows", ())) != list(specimen.spec.fit_rows) \
            or list(design.get("holdout_rows", ())) != list(specimen.spec.holdout_rows):
        _fail("the pipeline objective design has other FIT / HOLDOUT rows than the calibration specimen.")
    try:
        sigmas = {row: RowSigma(**value) for row, value in dict(design["sigmas"]).items()}
    except (KeyError, TypeError, ObjectiveInputError) as exc:
        _fail(f"the pipeline objective design has no valid σ per row ({exc}).")
    return ObjectiveDesign(tuple(design["fit_rows"]), (), tuple(design["holdout_rows"]), (), sigmas,
                           frozen.observation_hash)


def _evaluation(entries: list, evaluation_hash: str) -> dict:
    found = [e["record"] for e in entries if e.get("kind") == "evaluation"
             and isinstance(e.get("record"), Mapping) and e["record"].get("evaluation_hash") == evaluation_hash]
    if len(found) != 1:
        _fail(f"{len(found)} journalled evaluations carry evaluation hash {str(evaluation_hash)[:16]}.")
    record = dict(found[0])
    if record.get("refusal") is not None:
        _fail("the selected evaluation was refused by branch tracking.")
    if canonical_hash({k: v for k, v in record.items() if k != "evaluation_hash"}) != evaluation_hash:
        _fail("the evaluation record does not hash to its evaluation hash.")
    return record


def _bind_packs(evidence, record: Mapping, identity: Mapping, entries: list, specimen: CampaignSpecimenInput,
                job_name: str, generated: str) -> tuple[str, str]:
    frozen: FrozenObservationSet = specimen.frozen
    expectation = specimen.expectation
    contents = {}
    for name, pack, job, inp in (("candidate", evidence.candidate_pack, job_name, generated),
                                 ("baseline", evidence.baseline_pack, frozen.identity.job_name,
                                  frozen.identity.generated_inp_sha256)):
        if not isinstance(pack, FEShapePack):
            _fail(f"the {name} FE shape pack is required.")
        content = _pack_content_sha256(pack)
        problems = [label for label, ok in (
            ("content hash", content == pack.record.content_sha256), ("job", pack.record.job_name == job),
            ("generated INP", pack.record.generated_inp_sha256 == inp),
            ("FE geometry", pack.record.fe_geometry_sha256 == expectation.fe_geometry_sha256),
            ("node set", pack.record.node_set_sha256 == expectation.node_set_sha256),
            ("modes", tuple(pack.mode_numbers) == tuple(expectation.mode_numbers))) if not ok]
        if problems:
            _fail(f"the {name} FE pack does not match its {', '.join(problems)}.")
        contents[name] = content
    if contents["candidate"] != record.get("pack_content_sha256"):
        _fail("the candidate FE pack is not the pack of the journalled evaluation.")
    if frozen.identity.shape_pack_content_sha256 not in (None, contents["baseline"]):
        _fail("the baseline FE pack is not the pack the frozen set was built on.")
    journalled = {e["record"].get("pack_content_sha256") for e in entries if e.get("kind") == "extraction"
                  and isinstance(e.get("record"), Mapping) and e["record"].get("job_name") == frozen.identity.job_name}
    archived = dict(identity.get("archived_packs") or {}).get(frozen.identity.job_name)
    if contents["baseline"] not in journalled and contents["baseline"] != archived:
        _fail("the baseline FE pack is not the reference state journalled by this pipeline run.")
    return contents["candidate"], contents["baseline"]


def verify_candidate_evaluation(evidence: CandidateEvaluationEvidence, inputs, specimen: CampaignSpecimenInput,
                                run_identity: Mapping) -> VerifiedCandidateEvaluation:
    """Prove that p̂, the governed residual evidence, M5 robustness and the FE identity belong to one evaluation."""

    if not isinstance(evidence, CandidateEvaluationEvidence):
        _fail("a CandidateEvaluationEvidence record (the authoritative pipeline evaluation) is required.")
    definition, model, frozen = inputs.definition, specimen.model, specimen.frozen
    identity, pipeline_run_hash, entries = _journal(evidence)
    design = _bind_run(identity, inputs, specimen, run_identity)
    record = _evaluation(entries, evidence.evaluation_hash)

    # A — the evaluated parameter vector is p̂ (with the campaign's fixed parameters)
    try:
        p_hat = {name: float(inputs.p_hat[name]) for name in definition.fitted_parameters}
        candidate = forward_candidate(model, definition.full_parameters(p_hat))
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"p̂ does not describe a forward candidate ({exc}).")
    if set(inputs.p_hat) != set(p_hat) or record.get("parameters") != candidate.to_dict():
        _fail(f"the journalled evaluation evaluated {record.get('parameters')}, not p̂ {candidate.to_dict()}.")
    candidate_hash = canonical_hash({"parameterisation": candidate.parameterisation_id,
                                     "parameters": candidate.to_dict()})
    if record.get("candidate_hash") != candidate_hash:
        _fail("the evaluation's candidate hash is not the hash of p̂.")

    # F — the forward job and both FE packs
    try:
        rendered = render_forward_input(model, candidate, evidence.source_inp)
    except (ForwardBuildError, TypeError) as exc:
        _fail(f"the candidate job cannot be re-rendered from the pinned source INP ({exc}).")
    provenance = forward_job_provenance(model, candidate, rendered)
    job_name, job_hash = provenance["generated_inp"]["job_name"], canonical_hash(provenance)
    if (record.get("job_name"), record.get("generated_inp_sha256"), record.get("job_hash")) != (
            job_name, rendered.sha256, job_hash):
        _fail("the journalled job is not the forward job of p̂ rendered from the pinned source INP.")
    candidate_content, baseline_content = _bind_packs(evidence, record, identity, entries, specimen, job_name,
                                                      rendered.sha256)

    # B, C — tracking and the objective recomputed from the FE packs
    rows = {row.row_id: row.fe_mode for row in frozen.rows}
    try:
        tracking = track_branches(STRICT_IDENTIFICATION_PAIRING, fe_state_from_pack(evidence.baseline_pack),
                                  fe_state_from_pack(evidence.candidate_pack), rows, [])
        result = evaluate_objective(design, frozen, tracking)
    except (BranchTrackingRefusal, TrackingInputError, ObjectiveInputError) as exc:
        _fail(f"branch tracking / the objective cannot be recomputed from the FE packs ({exc}).")
    branches = {b.row_id: b for b in tracking.branches}
    if [t.residual for t in result.fit_terms] != record.get("residuals") \
            or {t.term_id: t.residual for t in result.holdout_terms} != record.get("holdout_residuals") \
            or {r: [b.candidate_mode, b.mac] for r, b in branches.items()} != record.get("tracking"):
        _fail("the journalled residuals / tracking are not those of the FE packs.")
    expected_terms = {(t.term_id, "HOLDOUT" if t.holdout else "FIT"): t.log_ratio
                      for t in result.fit_terms + result.holdout_terms}
    supplied_terms = {(t.term_id, t.role): float(t.delta_ln_f) for t in inputs.candidate_terms}
    if set(supplied_terms) != set(expected_terms) or any(
            not math.isclose(v, expected_terms[k], **_TOLERANCE) for k, v in supplied_terms.items()):
        _fail("the candidate terms are not the signed Δ ln f of the verified evaluation.")
    roles = {row_id: role for (row_id, role) in expected_terms}
    for row in inputs.candidate_rows:  # an absent row is the gate's ROW_SET_MISMATCH, never a substitute
        branch = branches.get(row.row_id)
        if branch is None or roles.get(row.row_id) != row.role or not math.isclose(
                float(row.delta_ln_f), math.log(branch.candidate_hz) - math.log(frozen.row(row.row_id).experimental_hz),
                **_TOLERANCE):
            _fail(f"candidate row {row.row_id} is not the tracked FE result of the verified evaluation.")
    for row_id, mac in inputs.tracking_macs.items():  # an absent MAC is the gate's MISSING_EVIDENCE
        if row_id not in branches or not math.isclose(float(mac), branches[row_id].mac, **_TOLERANCE):
            _fail(f"tracking MAC of {row_id} is not the FE-to-FE MAC of the verified evaluation.")

    # D — the pattern record judged exactly these terms
    sigma = {t.term_id: t.sigma for t in result.fit_terms + result.holdout_terms}
    fit_terms = residual_terms(list(design.fit_rows), [], [t.residual for t in result.fit_terms], specimen.families,
                               {k: sigma[k] for k in design.fit_rows})
    held = [ResidualTerm(t.term_id, t.row_ids, specimen.families[t.term_id], t.residual, t.sigma)
            for t in result.holdout_terms]
    pattern = residual_pattern_test(fit_terms, held, definition.tau_mf)
    if inputs.pattern is not None and inputs.pattern.record_hash != pattern.record_hash:
        _fail("the residual-pattern record was not computed from the verified evaluation.")

    # E — M5 evidence recomputed from the system with the verified FIT terms at p̂
    system = evidence.system
    if not isinstance(system, PracticalSystem):
        _fail("the M5 PracticalSystem is required.")
    if system.matrix.term_ids != tuple(t.term_id for t in fit_terms):
        _fail("the M5 system's FIT terms are not the verified evaluation's FIT terms.")
    foreign = sorted(name for name, given in (("analysis", inputs.analysis), ("statistical_sd", inputs.statistical),
                                              ("model_form_robustness", inputs.robustness))
                     if given is not None and given.system_hash != system.system_hash)
    if foreign:
        _fail(f"{', '.join(foreign)} belong(s) to another M5 system than the evidence's system.")
    recomputed = {}
    if inputs.analysis is not None:
        recomputed["analysis"] = (inputs.analysis, analyse_practical_identifiability(system))
    if inputs.statistical is not None:
        recomputed["statistical_sd"] = (inputs.statistical, statistical_sd(system, inputs.statistical.context))
        if inputs.birge is not None:
            recomputed["birge"] = (inputs.birge, birge_adjustment(system, inputs.statistical, pattern, fit_terms))
    if inputs.robustness is not None:
        recomputed["model_form_robustness"] = (inputs.robustness,
                                               linearised_model_form_robustness(system, fit_terms, p_hat))
    differing = sorted(name for name, (given, derived) in recomputed.items() if given.record_hash != derived.record_hash)
    if differing:
        _fail(f"{', '.join(differing)} was not computed from the verified FIT residuals at p̂ on this system.")

    return VerifiedCandidateEvaluation(pipeline_run_hash, evidence.evaluation_hash, candidate_hash, dict(p_hat),
                                       job_name, rendered.sha256, job_hash, candidate_content, baseline_content,
                                       str(record.get("fe_source")), specimen.profile.profile_id,
                                       specimen.profile.profile_hash,
                                       system.system_hash)
