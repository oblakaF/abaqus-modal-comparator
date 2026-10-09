"""LM / Jacobian provenance of a journalled campaign run — Auto-ID V12-I6 (SPEC v1.1 §6 S4, §8, §10; SPEC v1.2 §6).

The M5 system of a campaign is the LM's final Jacobian, reconstructed from the journal by the accepted
``reconstruct_lm_jacobian`` (central differences at the start, a Broyden update after every accepted step, a fresh
central difference after a rejected step following an update).  A caller-supplied sensitivity matrix is never
evidence.  ``verify_lm_history`` accepts the reconstruction only when the journals prove it:

1. the campaign journal is intact (run hash = hash of its run identity, hash chain) and its run identity is exactly
   the governed campaign's (definition hash, specimens, Σ, bounds, start, LM settings, solve budget);
2. exactly one journalled LM result, of this run, with the accepted status CONVERGED and no refusal;
3. every journalled campaign evaluation is the evaluation of its own candidate (candidate hash, full parameters,
   FIT term order) and, per specimen, the identical record of that specimen's hash-chained pipeline journal, whose run
   identity is exactly the governed pipeline of this campaign run and specimen (``governed_pipeline_identity``: the
   ``run_identity`` of the campaign's ``specimen_pipeline_config``, field by field; the stacked residuals are the
   specimens' FIT residuals);
4. the LM history follows the journalled evaluations: it starts at the start point, every objective it recorded is
   ½‖r‖² of the journalled residuals at that point, and it ends with the stop step at p̂;
5. p̂ is the final journalled evaluation, the reconstructed Jacobian is evaluated at p̂, it has the FIT terms ×
   fitted parameters in definition order, and it is the Jacobian the LM actually stopped with: the journalled
   ``local_sd`` and the journalled final trial step are reproduced from it (``local_sd`` / ``lm_step``).

Otherwise ``LMProvenanceRefusal`` with a typed code; nothing is repaired, guessed or taken from another run.

Pure: reads no file, writes nothing, runs nothing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from domain.identification_run import JOURNAL_SCHEMA, RunIdentityError, canonical_hash, verify_journal_chain

from .identification_campaign_run import (
    CAMPAIGN_RUN_SCHEMA,
    CampaignRun,
    CampaignSpecimenInput,
    ObservationSetMismatch,
    campaign_bounds,
    specimen_pipeline_config,
)
from .identification_pipeline import forward_candidate, run_identity
from .identification_step import LMStatus, StepError, local_sd, lm_step, objective
from .practical_identifiability import (
    PracticalIdentifiabilityInputError,
    ReconstructedJacobian,
    reconstruct_lm_jacobian,
)


SCHEMA = "auto-id/v12-lm-provenance/v1"
VERIFICATION = "VERIFIED_AGAINST_CAMPAIGN_AND_PIPELINE_JOURNALS"
LM_HISTORY_MISSING = "LM_HISTORY_MISSING"
LM_HISTORY_UNRELATED = "LM_HISTORY_UNRELATED"
LM_NOT_CONVERGED = "LM_NOT_CONVERGED"
LM_EVALUATION_UNVERIFIED = "LM_EVALUATION_UNVERIFIED"
JACOBIAN_INCONSISTENT = "JACOBIAN_INCONSISTENT"
STOP_NOTE = "step below stop_fraction·sd"  # identification_step.run_bounded_lm: the CONVERGED history entry
_POINT = {"rel_tol": 1e-12, "abs_tol": 0.0}  # the reconstruction's point identity (reconstruct_lm_jacobian)
_REPLAY = {"rel_tol": 1e-9, "abs_tol": 1e-12}  # replayed LM floating-point quantities


class LMProvenanceRefusal(PracticalIdentifiabilityInputError):
    """The LM history does not prove the M5 Jacobian: an input refusal (never a system, never a record)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class VerifiedLMHistory:
    run_hash: str
    run_identity: Mapping[str, Any]
    status: str
    p_hat: Mapping[str, float]
    result: Mapping[str, Any]  # the one journalled CONVERGED LM result
    final_evaluation: Mapping[str, Any]  # the campaign evaluation at p̂
    evaluations: tuple[Mapping[str, Any], ...]  # every journalled, non-refused campaign evaluation
    journalled_evaluations: tuple[Mapping[str, Any], ...]  # every journalled campaign evaluation (refusals included)
    pipeline_run_hashes: Mapping[str, str]  # specimen label → pipeline run hash
    jacobian: ReconstructedJacobian
    local_sd: tuple[float, ...]

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "verification": VERIFICATION, "run_hash": self.run_hash, "status": self.status,
                "p_hat": dict(sorted(self.p_hat.items())),
                "final_candidate_hash": self.final_evaluation["candidate_hash"],
                "evaluation_candidate_hashes": [e["candidate_hash"] for e in self.evaluations],
                "pipeline_run_hashes": dict(sorted(self.pipeline_run_hashes.items())),
                "jacobian": {"parameter_ids": list(self.jacobian.parameter_ids),
                             "point": dict(sorted(self.jacobian.point.items())), "updates": self.jacobian.updates,
                             "provenance": self.jacobian.provenance,
                             "whitened_hash": canonical_hash([list(row) for row in self.jacobian.whitened])},
                "local_sd": list(self.local_sd)}


def _refuse(code: str, message: str):
    raise LMProvenanceRefusal(code, message)


def journal_document(document: object, name: str) -> tuple[dict, str, list]:
    """An intact journal document: (run identity, run hash, entries), or LM_HISTORY_MISSING / UNRELATED."""
    if not isinstance(document, Mapping) or document.get("schema") != JOURNAL_SCHEMA:
        _refuse(LM_HISTORY_MISSING, f"no {name} journal document.")
    identity, entries = document.get("run_identity"), document.get("entries")
    if not isinstance(identity, Mapping) or not isinstance(entries, list):
        _refuse(LM_HISTORY_MISSING, f"the {name} journal has no run identity or entries.")
    run_hash = canonical_hash(dict(identity))
    if document.get("run_hash") != run_hash:
        _refuse(LM_HISTORY_UNRELATED, f"the {name} journal's run hash is not the hash of its run identity.")
    try:
        verify_journal_chain(run_hash, entries)
    except (RunIdentityError, KeyError, TypeError) as exc:
        _refuse(LM_HISTORY_UNRELATED, f"the {name} journal's hash chain is broken ({exc}).")
    return dict(identity), run_hash, entries


def _records(entries: list, kind: str) -> list[dict]:
    return [dict(e["record"]) for e in entries if e.get("kind") == kind and isinstance(e.get("record"), Mapping)]


def _bind_run_identity(definition, specimens: Sequence[CampaignSpecimenInput], identity: Mapping) -> None:
    # The run identity is the governed one, field by field (campaign_run_identity); archived pack hashes are bound to
    # each specimen's pipeline run below.
    expected = {
        "schema": CAMPAIGN_RUN_SCHEMA, "run_type": definition.run_type, "campaign_hash": definition.campaign_hash,
        "fitted_parameters": list(definition.fitted_parameters), "fixed_parameters": dict(definition.fixed_parameters),
        "sigma": definition.sigma.to_dict(), "bounds": {k: list(v) for k, v in definition.bounds.items()},
        "start": dict(definition.start), "lm": asdict(definition.lm),
        "abaqus_solve_budget": definition.abaqus_solve_budget,
    }
    wrong = sorted(key for key, value in expected.items() if identity.get(key) != value)
    entries = identity.get("specimens")
    if not isinstance(entries, list) or [e.get("label") if isinstance(e, Mapping) else None for e in entries] != [
            item.label for item in specimens]:
        wrong.append("specimens")
    else:
        for entry, item in zip(entries, specimens):
            specimen = {"fixture_id": item.spec.fixture_id, "registration_hash": item.frozen.identity.registration_hash,
                        "forward_model": {"forward_model_id": item.model.manifest.forward_model_id,
                                          "manifest_hash": item.model.manifest.manifest_hash},
                        "passport_manifest_hash": item.model.passport.manifest_hash,
                        "observation_hash": item.frozen.observation_hash, "fit_rows": list(item.fit_rows),
                        "holdout_rows": list(item.holdout_rows), "families": dict(sorted(item.families.items())),
                        "solver_profile_hash": item.profile.profile_hash}
            wrong += [f"{item.label}.{key}" for key, value in specimen.items() if entry.get(key) != value]
    if wrong:
        _refuse(LM_HISTORY_UNRELATED, f"the campaign run belongs to another {', '.join(wrong)}.")


def governed_pipeline_identity(definition, item: CampaignSpecimenInput, campaign_run_hash: str,
                               archived_packs: Mapping[str, str]) -> dict:
    """The run identity of the specimen's governed M4.6 pipeline in this campaign run.

    ``identification_pipeline.run_identity`` of the campaign's own ``specimen_pipeline_config``; the run root, stores,
    Abaqus command and executors are machine-specific and not part of a run identity.  ``archived_packs`` are the
    campaign run identity's pack content hashes of this specimen (job name → content hash).
    """
    config = specimen_pipeline_config(definition, item, Path(), {}, "", None, None, {}, campaign_run_hash)
    return dict(run_identity(config), archived_packs=dict(archived_packs))


def _bind_pipelines(definition, specimens: Sequence[CampaignSpecimenInput], identity: Mapping, run_hash: str,
                    pipeline_journals: Mapping[str, Mapping]) -> tuple[dict, dict]:
    records, run_hashes = {}, {}
    for item, entry in zip(specimens, identity["specimens"]):
        document = pipeline_journals.get(item.label) if isinstance(pipeline_journals, Mapping) else None
        pipeline, pipeline_hash, entries = journal_document(document, f"{item.label} pipeline")
        archived = entry.get("archived_packs")
        if not isinstance(archived, Mapping):
            _refuse(LM_HISTORY_UNRELATED, f"the campaign run identity has no archived packs for {item.label}.")
        try:
            governed = governed_pipeline_identity(definition, item, run_hash, archived)
        except ObservationSetMismatch as exc:
            _refuse(LM_HISTORY_UNRELATED, f"the {item.label} specimen has no governed pipeline ({exc}).")
        wrong = sorted(key for key in set(governed) | set(pipeline)
                       if canonical_hash(pipeline.get(key)) != canonical_hash(governed.get(key)))
        if wrong:
            _refuse(LM_HISTORY_UNRELATED, f"the {item.label} pipeline run is not the governed pipeline of this "
                                          f"campaign run and specimen ({', '.join(wrong)}).")
        records[item.label] = {r.get("evaluation_hash"): r for r in _records(entries, "evaluation")}
        run_hashes[item.label] = pipeline_hash
    return records, run_hashes


def _bind_evaluations(definition, specimens: Sequence[CampaignSpecimenInput], evaluations: list,
                      pipeline_records: Mapping) -> None:
    terms = list(definition.fit_term_ids())
    for record in evaluations:
        parameters = record.get("parameters")
        try:
            full = definition.full_parameters(parameters)
        except (TypeError, ValueError, AttributeError) as exc:
            _refuse(LM_EVALUATION_UNVERIFIED, f"a journalled evaluation has no campaign candidate ({exc}).")
        if record.get("candidate_hash") != CampaignRun.candidate_hash(parameters) \
                or record.get("full_parameters") != full or record.get("fit_term_ids") != terms:
            _refuse(LM_EVALUATION_UNVERIFIED, f"the journalled evaluation at {parameters} is not the evaluation of "
                                              "its own campaign candidate.")
        if record.get("refusal") is not None:
            continue
        per_specimen, stacked = record.get("specimens") or {}, []
        for item in specimens:
            given = per_specimen.get(item.label) if isinstance(per_specimen, Mapping) else None
            source = pipeline_records[item.label].get(given.get("evaluation_hash")) if isinstance(given, Mapping) \
                else None
            if source is None or canonical_hash({k: v for k, v in source.items() if k != "evaluation_hash"}) \
                    != source.get("evaluation_hash") or source.get("refusal") is not None \
                    or any(given.get(k) != source.get(k) for k in given) \
                    or source.get("parameters") != forward_candidate(item.model, full).to_dict():
                _refuse(LM_EVALUATION_UNVERIFIED, f"the {item.label} evaluation at {parameters} is not the record of "
                                                  "its pipeline journal for this candidate.")
            stacked += list(source.get("residuals") or [])
            holdouts = record.get("holdout_residuals") or {}
            if any(holdouts.get(item.spec.term_id(row)) != value
                   for row, value in (source.get("holdout_residuals") or {}).items()):
                _refuse(LM_EVALUATION_UNVERIFIED, f"the campaign holdouts at {parameters} are not {item.label}'s.")
        if record.get("residuals") != stacked or len(stacked) != len(terms):
            _refuse(LM_EVALUATION_UNVERIFIED, f"the campaign residuals at {parameters} are not the specimens' stacked "
                                              "FIT residuals.")


def _close(a: float, b: float, tolerance: Mapping) -> bool:
    return a is not None and b is not None and math.isclose(float(a), float(b), **tolerance)


def verify_lm_history(definition, specimens: Sequence[CampaignSpecimenInput], campaign_journal: Mapping,
                      pipeline_journals: Mapping[str, Mapping]) -> VerifiedLMHistory:
    """Prove that the reconstructed LM Jacobian at p̂ is the one this governed run's LM history produced."""

    specimens = tuple(specimens)
    if [item.label for item in specimens] != [s.label for s in definition.specimens] or any(
            item.spec != spec for item, spec in zip(specimens, definition.specimens)):
        _refuse(LM_HISTORY_UNRELATED, "give exactly the campaign specimens, in definition order.")
    identity, run_hash, entries = journal_document(campaign_journal, "campaign")
    _bind_run_identity(definition, specimens, identity)
    pipeline_records, pipeline_hashes = _bind_pipelines(definition, specimens, identity, run_hash, pipeline_journals)

    results = _records(entries, "result")
    if not results:
        _refuse(LM_HISTORY_MISSING, "the campaign journal has no LM result.")
    converged = [r for r in results if r.get("status") == LMStatus.CONVERGED.value]
    if not converged:
        _refuse(LM_NOT_CONVERGED, f"the LM status is {[r.get('status') for r in results]}, not "
                                  f"{LMStatus.CONVERGED.value}.")
    if len(converged) != 1 or len(results) != 1:
        _refuse(LM_HISTORY_UNRELATED, f"{len(results)} journalled LM results: the converged result is ambiguous.")
    result = converged[0]
    names = definition.fitted_parameters
    if result.get("run_hash") != run_hash or result.get("refusal") is not None \
            or not isinstance(result.get("parameters"), Mapping) or set(result["parameters"]) != set(names):
        _refuse(LM_HISTORY_UNRELATED, "the LM result does not belong to this run or has no p̂.")
    history = result.get("history")
    if not isinstance(history, list) or not history:
        _refuse(LM_HISTORY_MISSING, "the LM result has no iteration history.")

    evaluations = _records(entries, "evaluation")
    _bind_evaluations(definition, specimens, evaluations, pipeline_records)
    usable = [e for e in evaluations if e.get("refusal") is None]
    p_hat = {n: float(result["parameters"][n]) for n in names}
    finals = [e for e in usable if e["candidate_hash"] == CampaignRun.candidate_hash(p_hat)]
    if len(finals) != 1:
        _refuse(LM_EVALUATION_UNVERIFIED, f"{len(finals)} journalled evaluations at p̂ {p_hat}.")
    final = finals[0]

    def residuals_at(x: Sequence[float]) -> np.ndarray:
        point = np.exp(np.asarray(x, dtype=float))
        found = [e for e in usable if all(math.isclose(e["parameters"][n], float(v), **_POINT)
                                          for n, v in zip(names, point))]
        if len(found) != 1:
            _refuse(JACOBIAN_INCONSISTENT, f"the LM history visits {dict(zip(names, point))}, which is not one "
                                           "journalled evaluation.")
        return np.asarray(found[0]["residuals"], dtype=float)

    start = [math.log(float(definition.start[n])) for n in names]
    if not all(_close(a, b, _POINT) for a, b in zip(history[0].get("x", ()), start)):
        _refuse(JACOBIAN_INCONSISTENT, "the LM history does not start at the campaign start point.")
    for entry in history:
        if not _close(entry.get("objective_before"), objective(residuals_at(entry["x"])), _REPLAY) or (
                entry.get("trial_objective") is not None
                and not _close(entry["trial_objective"], objective(residuals_at(entry["trial_x"])), _REPLAY)):
            _refuse(JACOBIAN_INCONSISTENT, f"LM iteration {entry.get('iteration')} recorded an objective that is not "
                                           "½‖r‖² of the journalled residuals.")
    last = history[-1]
    if last.get("note") != STOP_NOTE or last.get("accepted") or last.get("trial_objective") is not None \
            or not all(_close(math.exp(x), p_hat[n], _POINT) for x, n in zip(last["x"], names)):
        _refuse(LM_NOT_CONVERGED, "the LM history does not end with the convergence stop step at p̂.")
    if not _close(result.get("objective"), objective(np.asarray(final["residuals"], dtype=float)), _REPLAY):
        _refuse(JACOBIAN_INCONSISTENT, "the LM result objective is not ½‖r‖² at p̂.")

    try:
        jacobian = reconstruct_lm_jacobian(usable, history, definition.start, names,
                                           definition.lm.finite_difference_step)
    except PracticalIdentifiabilityInputError as exc:
        _refuse(JACOBIAN_INCONSISTENT, f"the journalled evaluations do not support the LM Jacobian ({exc}).")
    whitened = np.array(jacobian.whitened, dtype=float)
    if tuple(jacobian.parameter_ids) != tuple(names) or whitened.shape != (len(definition.fit_term_ids()), len(names)) \
            or not all(_close(jacobian.point[n], p_hat[n], _POINT) for n in names):
        _refuse(JACOBIAN_INCONSISTENT, "the reconstructed Jacobian is not FIT terms × fitted parameters at p̂.")
    try:
        sd = tuple(float(v) for v in local_sd(whitened))
        step = lm_step(np.asarray(final["residuals"], dtype=float), whitened, float(last["mu"]))
    except (StepError, KeyError, TypeError, ValueError) as exc:
        _refuse(JACOBIAN_INCONSISTENT, f"the LM stop step cannot be replayed on the reconstructed Jacobian ({exc}).")
    journalled_sd = result.get("local_sd")
    if not isinstance(journalled_sd, list) or len(journalled_sd) != len(sd) \
            or not all(_close(a, b, _REPLAY) for a, b in zip(journalled_sd, sd)):
        _refuse(JACOBIAN_INCONSISTENT, "the reconstructed Jacobian does not reproduce the LM's journalled local sd.")
    bounds = campaign_bounds(definition)
    x = np.asarray(last["x"], dtype=float)
    trial = np.log(np.clip(np.exp(x + step), np.array(bounds.lower), np.array(bounds.upper)))
    if not all(_close(a, b, _REPLAY) for a, b in zip(trial, last.get("trial_x", ()))) \
            or not np.max(np.abs(trial - x) / np.asarray(sd)) < definition.lm.stop_fraction:
        _refuse(JACOBIAN_INCONSISTENT, "the reconstructed Jacobian does not reproduce the LM's journalled stop step.")
    return VerifiedLMHistory(run_hash, identity, result["status"], p_hat, result, final, tuple(usable),
                             tuple(evaluations), pipeline_hashes, jacobian, sd)
