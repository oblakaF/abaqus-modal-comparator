"""Accepted FIT / HOLDOUT observations of a campaign draft and its preparation review — Auto-ID M8 existing data.

"Bind Accepted FIT / HOLDOUT Observations" (``bind_specimen_observations``) attaches to one selected, record-bound
specimen the strict rows of its accepted strict freeze, exactly as recorded: row id, experimental and FE mode numbers,
role (the freeze's own holdout split), M4.3 family, MAC and frequency error.  Nothing is paired, ranked or chosen here:
no role is assigned by MAC, frequency proximity or mode number, no weak or provisional pair is added, no family is
renamed and no threshold is touched.  The rows are bound only when the P11 observation-readiness record counts them
(every input GOVERNED: curve-fitted fixture modes, PHYSICAL registration, its M2.4 evidence with
``registration_limited`` false, the accepted strict freeze on that registration) and when the freeze, the M2.4
evidence and the other governed records are the ones already bound to the draft.  Anything else is refused with its
reasons and the draft is unchanged.  The modes the freeze excluded are shown with the freeze's own reasons.

``draft_preparation_review`` is a preliminary preparation review of one exact draft, not a scientific gate: it reports
the SPEC v1.2 §8 counting conditions (``observation_count.count_observations`` through the P11 records, per specimen
and pooled), the k = 9 counting diagnostic, the availability of numerical sensitivity, practical rank, full
leave-one-FIT-family-out and experimental covariance (never turned into PASS), the historical result of earlier
campaigns on the same specimens, the missing required inputs and the governed parser's finalisation state.  Its
verdict says only whether the definition can be passed on for further review or is incomplete, with the reasons.

Records only: no data store, ODB, UNV or INP is read, nothing is written, and no Abaqus, FE, LM or solve runs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Optional

from domain.campaign_definition import (
    CALIBRATION_NOT_IMPLEMENTED,
    MATERIAL_IDENTIFICATION,
    NOT_AVAILABLE,
    RUN_A,
    RUN_B,
)
from domain.experiment_fixture import ExperimentFixtureManifest
from domain.forward_model_manifest import PARAMETERISATIONS

from .archived_sensitivity_evidence import AcceptedReferenceRefusal, accepted_physical_freeze
from .governed_specimen_records import FIELDS as RECORD_FIELDS, SpecimenRecords
from .observation_readiness import NOT_ASSESSED, pooled_observation_count, specimen_observation_readiness

BOUND = "BOUND"
REFUSED = "REFUSED"
OBSERVATION_NOTE = ("accepted strict-freeze rows as recorded (role, family and MAC from the freeze; nothing paired or "
                    "chosen here); bound observations are not a readiness verdict")
# The governed parser's run-type rule (D-069): RUN_A fits E_in_plane_mpa only, RUN_B E_in_plane_mpa and G12_mpa.
K_BY_RUN_TYPE = {RUN_A: 1, RUN_B: 2}
NINE_CONSTANTS_K = 9  # the orthotropic nine-constant question: a counting diagnostic only, never fitted here
HISTORICAL_CAMPAIGN = "docs/auto_id/campaigns/M7_RUN_A.campaign.json"
HISTORICAL_RESULT = ("D-077: M7 RUN_A family consistency FAIL, RUN_B NOT_EVALUABLE_RANK_DEFICIENT, formal output "
                     "NO_GLOBAL_PARAMETER_VALUE; the historical optimiser values are not material properties or accepted "
                     "calibration values. Unchanged: this draft re-evaluates nothing")
REVIEW_NOTE = ("preliminary preparation review of this exact draft: a met counting condition, a high MAC or a complete "
               "definition is not identifiability, not a calibration and not an execution authorisation")
READY_FOR_REVIEW = "DEFINITION_COMPLETE_FOR_FURTHER_REVIEW"
INCOMPLETE = "INCOMPLETE"


class ObservationBindingError(ValueError):
    """The observations of a specimen cannot be bound; nothing is substituted."""


@dataclass(frozen=True)
class ObservationRow:
    """One accepted strict pair as the strict freeze records it."""

    row_id: str
    role: str  # FIT | HOLDOUT (the freeze's holdout split)
    experimental_mode: int
    fe_mode: int
    family: str
    mac: float
    relative_frequency_error: float
    experimental_hz: float
    fe_hz: float

    def campaign_row(self) -> dict:
        return {"row_id": self.row_id, "experimental_mode": self.experimental_mode, "fe_mode": self.fe_mode,
                "role": self.role}

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class SpecimenObservations:
    """The bound observations of one specimen with the identities they rest on."""

    forward_model: str
    label: str
    fixture_id: str
    registration_hash: str
    registration_label: str
    strict_freeze: tuple[str, str]  # repository path, canonical SHA-256
    registration_evidence: tuple[str, str]
    rows: tuple[ObservationRow, ...]
    excluded: tuple[tuple[int, str], ...]  # experimental mode, the freeze's reason
    holdout_notes: tuple[str, ...]

    def campaign_rows(self) -> list[dict]:
        return [row.campaign_row() for row in self.rows]

    def frozen_pair_id(self, row: ObservationRow) -> str:
        return f"{self.label}:{row.row_id}"

    def to_dict(self) -> dict:
        return {"forward_model": self.forward_model, "label": self.label, "fixture_id": self.fixture_id,
                "registration_hash": self.registration_hash, "registration_label": self.registration_label,
                "strict_freeze": {"path": self.strict_freeze[0], "canonical_sha256": self.strict_freeze[1]},
                "registration_evidence": {"path": self.registration_evidence[0],
                                          "canonical_sha256": self.registration_evidence[1]},
                "rows": [row.to_dict() for row in self.rows],
                "excluded": [{"experimental_mode": mode, "reason": reason} for mode, reason in self.excluded],
                "holdout_notes": list(self.holdout_notes)}


@dataclass(frozen=True)
class ObservationBinding:
    forward_model: str
    status: str  # BOUND | REFUSED
    observations: Optional[SpecimenObservations]
    reasons: tuple[str, ...]

    def summary(self) -> str:
        if self.status == BOUND:
            rows = self.observations.rows
            return (f"{self.forward_model}: {sum(r.role == 'FIT' for r in rows)} FIT + "
                    f"{sum(r.role == 'HOLDOUT' for r in rows)} HOLDOUT accepted rows bound")
        return f"{self.forward_model}: " + "; ".join(self.reasons)


def _refused(forward_model: str, *reasons: str) -> ObservationBinding:
    return ObservationBinding(forward_model, REFUSED, None, tuple(reasons))


def bind_specimen_observations(forward_model: str, repo_root: Path, fixtures: ExperimentFixtureManifest,
                               records: Optional[SpecimenRecords]) -> ObservationBinding:
    """The accepted strict-freeze rows of one specimen, bound only on the governed chain already bound to the draft."""

    root = Path(repo_root).resolve()
    try:
        readiness = specimen_observation_readiness(forward_model, 1, repo_root=root, fixtures=fixtures)
    except Exception as error:  # the governed binder or a loader refused the specimen
        return _refused(forward_model, f"the observation-readiness record cannot be built: {error}")
    record = readiness.record
    if not readiness.counted:
        return _refused(forward_model, *(f"{r['code']}: {r['detail']}" for r in record["insufficiency_reasons"]
                                         if r["code"] in ("PREREQUISITE_NOT_GOVERNED", "REGISTRATION_LIMITED")),
                        "no observation is bound (only governed, curve-fitted rows on a PHYSICAL registration count)")
    unconfirmed = [r["detail"] for r in record["insufficiency_reasons"] if r["code"] == "CLUSTER_GROUP_NOT_COUNTED"]
    if unconfirmed:
        return _refused(forward_model, *(f"CLUSTER_GROUP_NOT_COUNTED: {d}" for d in unconfirmed))
    if not isinstance(records, SpecimenRecords):
        return _refused(forward_model, "the governed specimen records are not bound: use Bind Governed Specimen "
                                       "Records first (the observations must rest on the same registration evidence)")
    sources, bound = record["sources"], records.to_dict()
    differing = [name for name in RECORD_FIELDS if sources.get(name) != bound[name]]
    if differing:
        return _refused(forward_model, f"the observation record rests on other {', '.join(differing)} than the "
                                       "records bound to the draft (never substituted)")
    fixture_id = record["specimen"]["fixture_id"]
    try:
        freeze = accepted_physical_freeze(fixture_id, repo_root=root)
    except AcceptedReferenceRefusal as refusal:
        return _refused(forward_model, f"strict freeze: {refusal}")
    if sources.get("strict_freeze") != {"path": freeze.reevaluation_path,
                                        "canonical_sha256": freeze.reevaluation_hash}:
        return _refused(forward_model, "the strict freeze differs from the one the observation record counted")
    physical = freeze.freeze
    holdouts = set(physical["holdouts"]["holdout_row_ids"])
    rows = tuple(ObservationRow(p["row_id"], "HOLDOUT" if p["row_id"] in holdouts else "FIT",
                                int(p["experimental_mode"]), int(p["fe_mode"]), p["family"], float(p["mac"]),
                                float(p["relative_frequency_error"]), float(p["experimental_hz"]), float(p["fe_hz"]))
                 for p in physical["strict_pairs"])
    counted = [(r["row_id"], r["role"], r["experimental_mode"], r["fe_mode"], r["family"])
               for r in record["observation_count"]["strict_rows"]["rows"]]
    if counted != [(r.row_id, r.role, r.experimental_mode, r.fe_mode, r.family) for r in rows]:
        return _refused(forward_model, "the strict-freeze rows differ from the counted observation rows")
    observations = SpecimenObservations(
        forward_model=forward_model, label=record["specimen"]["label"], fixture_id=fixture_id,
        registration_hash=freeze.registration.registration_hash, registration_label=str(physical.get("label", "")),
        strict_freeze=(freeze.reevaluation_path, freeze.reevaluation_hash),
        registration_evidence=(bound["registration_evidence"]["path"],
                               bound["registration_evidence"]["canonical_sha256"]),
        rows=rows, excluded=tuple((int(e["experimental_mode"]), str(e["reason"])) for e in physical["excluded"]),
        holdout_notes=tuple(str(n) for n in physical["holdouts"].get("notes", ())))
    return ObservationBinding(forward_model, BOUND, observations, ())


def observation_rows(label: str, observations: SpecimenObservations) -> list[tuple[str, str, str, str]]:
    """Table rows (section, item, value, status) of one specimen's bound observations."""

    rows = [("Observations", f"{label} registration",
             f"{observations.registration_label} {observations.registration_hash[:12]}; M2.4 evidence "
             f"{observations.registration_evidence[0]}; strict freeze {observations.strict_freeze[0]} "
             f"(canonical SHA-256 {observations.strict_freeze[1][:12]})", BOUND)]
    for row in observations.rows:
        rows.append(("Observations", f"{label} {row.row_id}",
                     f"{row.role}; frozen pair {observations.frozen_pair_id(row)}; exp. mode {row.experimental_mode} "
                     f"({row.experimental_hz:.3f} Hz) ↔ FE mode {row.fe_mode} ({row.fe_hz:.3f} Hz); family "
                     f"{row.family}; MAC {row.mac:.3f}; Δf/f {row.relative_frequency_error:+.4f} (as frozen)",
                     row.role))
    for mode, reason in observations.excluded:
        rows.append(("Observations", f"{label} exp. mode {mode}", f"excluded by the strict freeze: {reason}",
                     "EXCLUDED"))
    for note in observations.holdout_notes:
        rows.append(("Observations", f"{label} holdout note", note, "NOTE"))
    return rows


# ----------------------------------------------------------------------------- preparation review


@dataclass(frozen=True)
class PreparationReview:
    """The preliminary preparation review of one exact draft (rows, verdict, reasons)."""

    rows: tuple[tuple[str, str, str, str], ...]
    verdict: str
    reasons: tuple[str, ...]

    def summary(self) -> str:
        head = f"Preparation review: {self.verdict}"
        if self.reasons:
            head += " — " + "; ".join(self.reasons)
        return f"{head}. ({REVIEW_NOTE}.)"


def _sensitivity_item(repo_root: Path, observations: Optional[SpecimenObservations]) -> tuple[str, str]:
    if observations is None:
        return NOT_AVAILABLE, "no bound observations"
    try:
        freeze = accepted_physical_freeze(observations.fixture_id, repo_root=repo_root).freeze
    except AcceptedReferenceRefusal as refusal:
        return NOT_AVAILABLE, str(refusal)
    recorded = freeze.get("sensitivities") or freeze.get("sensitivities_carbon5a") or {}
    missing = [row.row_id for row in observations.rows if row.row_id not in recorded]
    if missing:
        return NOT_AVAILABLE, f"no recorded sensitivity for rows {missing}"
    return ("RECORDED_DIAGNOSTIC_ONLY", "local archived d ln f / d ln p of every bound row at the reference FE state "
                                        "(recorded in the strict freeze); never a rank result or an identifiability "
                                        "claim")


def _historical(repo_root: Path, forward_models: set[str]) -> Optional[str]:
    try:
        campaign = json.loads(repo_root.joinpath(*PurePosixPath(HISTORICAL_CAMPAIGN).parts).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    historical = {s["forward_model"] for s in campaign.get("specimens", [])}
    shared = sorted(historical & forward_models)
    if not shared:
        return None
    return f"{campaign.get('campaign_id')} used {', '.join(shared)}: {HISTORICAL_RESULT}"


def draft_preparation_review(draft, repo_root: Path, fixtures: ExperimentFixtureManifest) -> PreparationReview:
    """Counting conditions, numerical availability, history, missing inputs and finalisation of one draft."""

    from .campaign_draft import DraftIncomplete  # the draft module imports this one lazily

    root = Path(repo_root).resolve()
    rows: list[tuple[str, str, str, str]] = []
    reasons: list[str] = []
    k = K_BY_RUN_TYPE.get(draft.run_type)
    rows.append(("Question", "Scientific question", draft.scientific_question or "not declared",
                 "PRESENT" if draft.scientific_question else "NOT_DECLARED"))
    if draft.scientific_question not in (None, MATERIAL_IDENTIFICATION):  # the specimen-calibration question
        rows.append(("Question", "Consequence", "exactly one physical specimen; the calibration gate is the governed "
                     "SPEC v1.2 §6 gate; production calibration execution BLOCKED / NOT_AUTHORISED "
                     f"({CALIBRATION_NOT_IMPLEMENTED}); never rerouted to material identification",
                     "BLOCKED"))
    elif draft.scientific_question == MATERIAL_IDENTIFICATION:
        rows.append(("Question", "Consequence", "at least two physical specimens sharing one material; a met count is "
                     "not identifiability; a material value needs every SPEC criterion (family consistency, rank, "
                     "leave-one-FIT-family-out, covariance)", "NOTE"))
    rows.append(("Question", "Fitted parameters k", "not determined (declare the run type)" if k is None
                 else f"k = {k} ({draft.run_type}: the parser's run-type rule)", "PRESENT" if k else "NOT_DECLARED"))
    if k is None:
        reasons.append("run type not declared: k is not determined")

    readiness = []
    for item in draft.specimens:
        observations = draft.specimen_observations(item.forward_model)
        if observations is None:
            rows.append(("Observations", item.label, "not bound (Bind Accepted FIT / HOLDOUT Observations)",
                         "NOT_BOUND"))
            reasons.append(f"{item.label}: FIT / HOLDOUT observations not bound")
        for count_k, label in ((k, "§8 count"), (NINE_CONSTANTS_K, "§8 count k = 9 (diagnostic)")):
            if count_k is None:
                continue
            try:
                record = specimen_observation_readiness(item.forward_model, count_k, repo_root=root,
                                                        fixtures=fixtures)
            except Exception as error:
                rows.append((label, item.label, f"refused: {error}", "REFUSED"))
                reasons.append(f"{item.label}: observation record refused")
                continue
            count = record.record["observation_count"]
            refusals = [r["code"] for r in count["section_8_count"]["refusal_reasons"]]
            value = (f"{count['families']['FIT']} FIT / {count['families']['HOLDOUT']} HOLDOUT families; needs "
                     f"{count_k + 1} FIT families" + (f"; {', '.join(refusals)}" if refusals else ""))
            if not count["governed_observations_counted"]:
                value = "no governed observation counted (" + ", ".join(
                    r["code"] for r in record.record["insufficiency_reasons"]
                    if r["code"] in ("PREREQUISITE_NOT_GOVERNED", "REGISTRATION_LIMITED")) + ")"
            rows.append((label, f"{item.label} (k = {count_k})", value, count["status"]))
            if count_k == k:
                readiness.append(record)
                if count["status"] != "COUNT_CONDITIONS_MET" and draft.scientific_question != MATERIAL_IDENTIFICATION:
                    reasons.append(f"{item.label}: §8 counting conditions not met for k = {k}")
        status, detail = _sensitivity_item(root, observations)
        rows.append(("Numerical identifiability", f"{item.label} numerical sensitivity", detail, status))
    if len(draft.specimens) > 1 and k is not None and readiness:
        pooled = pooled_observation_count(readiness, k)
        refusals = [r["code"] for r in pooled["section_8_count"]["refusal_reasons"]]
        rows.append(("§8 count", f"pooled ({len(readiness)} specimens, k = {k})",
                     f"FIT families {pooled['section_8_count']['fit_family_keys']}, HOLDOUT families "
                     f"{pooled['section_8_count']['holdout_family_keys']} (family identity shared by key, D-070)"
                     + (f"; {', '.join(refusals)}" if refusals else ""), pooled["status"]))
        if pooled["status"] != "COUNT_CONDITIONS_MET":
            reasons.append(f"pooled §8 counting conditions not met for k = {k}")
    elif len(draft.specimens) == 1 and readiness and draft.scientific_question == MATERIAL_IDENTIFICATION:
        status = readiness[0].record["observation_count"]["status"]
        if status != "COUNT_CONDITIONS_MET":
            reasons.append(f"{draft.specimens[0].label}: §8 counting conditions not met for k = {k}")
    nine = [p for p in PARAMETERISATIONS.values() if len(p.parameters) >= NINE_CONSTANTS_K]
    rows.append(("§8 count k = 9 (diagnostic)", "Nine-constant identification",
                 "counting diagnostic only: no governed parameterisation has nine constants (available: "
                 + ", ".join(f"{name} {list(p.parameters)}" for name, p in sorted(PARAMETERISATIONS.items()))
                 + "); nothing is fitted", "PARAMETERISATION_AVAILABLE" if nine else "NOT_SUPPORTED"))
    for item, detail in (("Practical rank (M5 RCOND)", "needs the FE Jacobian of a campaign run; not computed here"),
                         ("Full leave-one-FIT-family-out", "needs campaign fits; not computed here"),
                         ("Family consistency (SPEC §13)", "needs a campaign run; not computed here")):
        rows.append(("Numerical identifiability", item, detail, NOT_ASSESSED))
    rows.append(("Numerical identifiability", "Experimental covariance Σ_meas",
                 "real PolyMAX data give no modal uncertainty; the parser supports Σ_meas NOT_AVAILABLE only (D-069), "
                 "never a zero value", NOT_AVAILABLE))
    history = _historical(root, {s.forward_model for s in draft.specimens})
    if history:
        rows.append(("History", "Earlier campaign on these specimens", history, "UNCHANGED"))
    from .campaign_configuration import configuration_problems, configuration_rows  # M8-D2f

    rows.extend(configuration_rows(draft, root))
    reasons.extend(f"configuration: {problem}" for problem in configuration_problems(draft, root))
    gaps = draft.gaps()
    for gap in gaps:
        rows.append(("Missing required inputs", gap.field, gap.reason, "MISSING"))
    definition = None
    try:
        definition = draft.finalise()
    except DraftIncomplete as refusal:
        finalisation = f"refused: {len(refusal.gaps)} required campaign input(s) missing"
        reasons.insert(0, f"{len(gaps)} required campaign input(s) missing")
    except Exception as error:  # the governed parser refuses the complete definition
        finalisation = f"refused by the campaign-definition parser: {error}"
        reasons.insert(0, finalisation)
    else:
        finalisation = "accepted by the campaign-definition parser (no definition is written here)"
    rows.append(("Definition", "Finalisation (parse_campaign_definition)", finalisation,
                 "ACCEPTED_BY_PARSER" if definition is not None else "REFUSED"))
    if definition is not None:
        rows.append(("Definition", "New campaign identity", f"{definition.campaign_id}: campaign hash "
                     f"{definition.campaign_hash} (schema {definition.schema}); a new identity — no earlier (M7) "
                     "result is carried over", "NOT_EXECUTED"))
        rows.append(("Definition", "Execution", "not authorised: a complete definition is not identifiability and "
                     "not an execution authorisation; execution needs its own HUMAN gate, production calibration "
                     "stays BLOCKED / NOT_AUTHORISED", "NOT_AUTHORISED"))
    verdict = INCOMPLETE if reasons else READY_FOR_REVIEW
    rows.append(("Verdict", "Preparation", verdict, verdict))
    return PreparationReview(tuple(rows), verdict, tuple(reasons))
