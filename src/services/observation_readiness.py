"""Observation readiness of one governed specimen — P11 (records only; SPEC v1.2 §8; P10 data-readiness audit).

``specimen_observation_readiness`` assembles, for one governed forward-model manifest, a deterministic, hash-sealed
record of three separate things, never mixed:

1. **data governance** — the status of each input as its governed records state it: GOVERNED, AVAILABLE,
   DIAGNOSTIC_ONLY, NOT_AVAILABLE or NOT_VERIFIED (the experiment fixture, the modal input source, the physical
   registration and its M2.4 evidence, the forward model, the bound campaign records, the accepted strict freeze, the
   physical-measurement record, the suspension threshold);
2. **observation count** — the strict FIT / HOLDOUT rows of the accepted strict freeze, their terms (a cluster-trigger
   group is one term) and families, and the SPEC v1.2 §8 counting conditions for a declared k
   (``observation_count.count_observations``, the calibration gate's own rule). Rows are counted only when every input
   they rest on is GOVERNED, the modes are curve-fitted and the registration is not limited;
3. **numerical identifiability** — always NOT_ASSESSED here: practical rank, precision, leave-one-FIT-family-out and
   sensitivities need FE evidence that this record never computes.

A met counting condition is not scientific readiness, a rank result or a calibration: the record says so
(``scientific_readiness`` NOT_DECLARED). The M6.4 transverse screening is attached as DIAGNOSTIC_ONLY context.

Everything is read from committed repository records through the existing loaders (governed binder, fixture
catalogue, ``accepted_physical_freeze``, governed specimen records, physical measurements). No data store, ODB, UNV or
INP is read, nothing is written, and no Abaqus, FE, LM or solve runs. No threshold is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional, Sequence

from domain.experiment_fixture import ExperimentFixtureManifest, load_experiment_fixture_manifest
from domain.identification_run import canonical_hash
from domain.modal_input_source import ModalInputSource, classify_mode_source
from domain.physical_measurements import load_physical_measurements
from domain.specimen_manifest import RegistrationBasisStatus, load_specimen_manifest

from .archived_sensitivity_evidence import (
    FIXTURE_MANIFEST,
    REPO_ROOT,
    AcceptedReferenceRefusal,
    accepted_physical_freeze,
)
from .campaign_draft import governed_specimen_input
from .experiment_fixture_regression import SOURCE_TYPE_MODE_SOURCES
from .governed_specimen_records import BOUND, bind_governed_specimen_records
from .observation_count import count_observations

SCHEMA = "auto-id/observation-readiness/v1"
POOLED_SCHEMA = "auto-id/pooled-observation-count/v1"
QUANTITY = "observation_readiness"
NOT_ASSESSED = "NOT_ASSESSED"
SCIENTIFIC_READINESS = "NOT_DECLARED"
NOTE = ("records-only observation readiness: data governance, observation count and numerical identifiability are "
        "separate; a met SPEC v1.2 §8 counting condition is not a rank result, not scientific readiness and not a "
        "calibration")
MEASUREMENTS_DIRECTORY = PurePosixPath("docs/auto_id/specimens")
SCREENING_RESULT = "docs/auto_id/screening/M6_4_transverse_screening_result.json"
# Inputs every counted observation rests on (all must be GOVERNED).
PREREQUISITES = ("experimental_modal_set", "modal_input_source", "physical_registration", "registration_evidence",
                 "strict_freeze")


class DataStatus(str, Enum):
    GOVERNED = "GOVERNED"
    AVAILABLE = "AVAILABLE"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_VERIFIED = "NOT_VERIFIED"


@dataclass(frozen=True)
class GovernanceItem:
    status: DataStatus
    detail: str

    def to_dict(self) -> dict:
        return {"status": self.status.value, "detail": self.detail}


@dataclass(frozen=True)
class StrictRow:
    """One accepted strict pair as the strict freeze records it (never re-paired here)."""

    row_id: str
    role: str  # FIT | HOLDOUT
    experimental_mode: int
    fe_mode: int
    family: str
    mac: float
    relative_frequency_error: float

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ReadinessEvidence:
    """What the governed records state for one specimen; ``build_observation_readiness`` judges nothing else."""

    specimen: Mapping[str, Optional[str]]
    sources: Mapping[str, Mapping[str, str]]  # record name → repository path and canonical SHA-256
    items: Mapping[str, GovernanceItem]
    registration_limited: Optional[bool]  # the M2.4 record's value; None when no record is bound
    strict_rows: tuple[StrictRow, ...] = ()
    cluster_groups: tuple[tuple[str, ...], ...] = ()  # the freeze's cluster-trigger row groups
    diagnostics: Mapping[str, Any] = None


@dataclass(frozen=True)
class ObservationReadiness:
    record: Mapping[str, Any]

    @property
    def record_hash(self) -> str:
        return self.record["record_hash"]

    @property
    def counted(self) -> bool:
        return self.record["observation_count"]["governed_observations_counted"]

    def to_dict(self) -> dict:
        return json.loads(json.dumps(self.record))


def modal_input_item(source: ModalInputSource, governed_fixture: bool, basis: str) -> GovernanceItem:
    """The governance status of the experimental modes from their source class (SPEC §16, §19 item 3)."""
    if source is ModalInputSource.PEAK_DERIVED:
        return GovernanceItem(DataStatus.DIAGNOSTIC_ONLY, f"peak-derived modes ({basis}): viewing and QC only, never "
                                                          "an identification observation")
    if source is ModalInputSource.UNKNOWN:
        return GovernanceItem(DataStatus.NOT_VERIFIED, f"mode source not classifiable ({basis}); refused like "
                                                       "peak-derived")
    if governed_fixture:
        return GovernanceItem(DataStatus.GOVERNED, f"curve-fitted ({basis})")
    return GovernanceItem(DataStatus.AVAILABLE, f"curve-fitted but not a governed fixture ({basis})")


def _terms(rows: Sequence[StrictRow], groups: Sequence[tuple[str, ...]]):
    """Terms of the counted rows: a cluster-trigger group is one term, never several (SPEC §12.4)."""
    by_id = {row.row_id: row for row in rows}
    grouped = {member for group in groups for member in group}
    reasons, terms = [], []
    for group in groups:
        members = [by_id[m] for m in group if m in by_id]
        roles, families = {m.role for m in members}, {m.family for m in members}
        if len(members) != len(group) or len(roles) != 1 or len(families) != 1:
            reasons.append({"code": "CLUSTER_GROUP_NOT_COUNTED",
                            "detail": f"rows {list(group)}: a cluster group needs one role and one family to be one "
                                      f"term; it is not counted"})
            continue
        reasons.append({"code": "CLUSTER_COUNTED_ONCE",
                        "detail": f"rows {list(group)} form one cluster term; its M4.4 confirmation is NOT_ASSESSED"})
        terms.append(("+".join(group), roles.pop(), families.pop(), tuple(group)))
    for row in rows:
        if row.row_id not in grouped:
            terms.append((row.row_id, row.role, row.family, (row.row_id,)))
    return sorted(terms), reasons


def build_observation_readiness(evidence: ReadinessEvidence, k: int) -> ObservationReadiness:
    """The deterministic, hash-sealed readiness record of one specimen for k declared parameters."""
    if not isinstance(evidence, ReadinessEvidence):
        raise TypeError("observation readiness is built from a ReadinessEvidence record.")
    items = dict(evidence.items)
    missing = [name for name in PREREQUISITES if name not in items]
    if missing:
        raise ValueError(f"the evidence lacks the governance items {missing}.")
    blocking = [{"code": "PREREQUISITE_NOT_GOVERNED", "detail": f"{name}: {items[name].status.value} — "
                                                                f"{items[name].detail}"}
                for name in PREREQUISITES if items[name].status is not DataStatus.GOVERNED]
    if items["registration_evidence"].status is DataStatus.GOVERNED and evidence.registration_limited is not False:
        blocking.append({"code": "REGISTRATION_LIMITED", "detail": "the M2.4 registration evidence states "
                                                                   f"registration_limited = {evidence.registration_limited}"})
    counted = not blocking
    rows = tuple(evidence.strict_rows) if counted else ()
    terms, cluster_reasons = _terms(rows, evidence.cluster_groups if counted else ())
    fit = {term: family for term, role, family, _ in terms if role == "FIT"}
    holdout = {term: family for term, role, family, _ in terms if role == "HOLDOUT"}
    count = count_observations(fit, holdout, k)
    reasons = blocking + cluster_reasons + [{"code": code, "detail": detail} for code, detail in count.refusals]
    observation_count = {
        "governed_observations_counted": counted,
        "rule": "SPEC v1.2 §8 counting conditions (observation_count.count_observations)",
        "strict_rows": {"FIT": sum(r.role == "FIT" for r in rows), "HOLDOUT": sum(r.role == "HOLDOUT" for r in rows),
                        "rows": [r.to_dict() for r in rows]},
        "terms": {"FIT": len(fit), "HOLDOUT": len(holdout),
                  "members": {term: list(members) for term, _, _, members in terms}},
        "families": {"FIT": len(count.fit_family_keys), "HOLDOUT": len(count.holdout_family_keys)},
        "section_8_count": count.to_dict(),
        "status": "COUNT_CONDITIONS_MET" if count.met else "COUNT_CONDITIONS_NOT_MET",
    }
    numerical = {
        "rank_status": NOT_ASSESSED, "precision_status": NOT_ASSESSED,
        "leave_one_fit_family_out_status": NOT_ASSESSED, "sensitivity_status": NOT_ASSESSED,
        "detail": "needs FE sensitivity evidence and the M5 system; not computed from records (no Abaqus, no FE)",
    }
    record = {
        "schema": SCHEMA, "quantity": QUANTITY, "note": NOTE,
        "specimen": dict(evidence.specimen), "declared_k": k,
        "sources": {name: dict(value) for name, value in sorted(evidence.sources.items())},
        "data_governance": {name: item.to_dict() for name, item in sorted(items.items())},
        "registration_limited": evidence.registration_limited,
        "observation_count": observation_count,
        "numerical_identifiability": numerical,
        "insufficiency_reasons": reasons,
        "diagnostics": evidence.diagnostics or {},
        "scientific_readiness": SCIENTIFIC_READINESS,
    }
    record = json.loads(json.dumps(record))
    record["record_hash"] = canonical_hash(record)
    return ObservationReadiness(record)


def pooled_observation_count(readiness: Sequence[ObservationReadiness], k: int) -> dict:
    """The §8 counting conditions over several specimens' counted terms (family identity shared by key, D-070)."""
    fit, holdout, specimens = {}, {}, []
    for item in readiness:
        record = item.record
        label = record["specimen"]["label"]
        specimens.append({"label": label, "record_hash": item.record_hash,
                          "governed_observations_counted": item.counted})
        if not item.counted:
            continue
        families = {row["row_id"]: row["family"] for row in record["observation_count"]["strict_rows"]["rows"]}
        roles = {row["row_id"]: row["role"] for row in record["observation_count"]["strict_rows"]["rows"]}
        for term, members in record["observation_count"]["terms"]["members"].items():
            target = fit if roles[members[0]] == "FIT" else holdout
            target[f"{label}:{term}"] = families[members[0]]
    count = count_observations(fit, holdout, k)
    result = {"schema": POOLED_SCHEMA, "declared_k": k, "specimens": specimens,
              "terms": {"FIT": sorted(fit), "HOLDOUT": sorted(holdout)},
              "section_8_count": count.to_dict(),
              "status": "COUNT_CONDITIONS_MET" if count.met else "COUNT_CONDITIONS_NOT_MET",
              "numerical_identifiability": {"rank_status": NOT_ASSESSED, "precision_status": NOT_ASSESSED,
                                            "leave_one_fit_family_out_status": NOT_ASSESSED},
              "scientific_readiness": SCIENTIFIC_READINESS, "note": NOTE}
    result["record_hash"] = canonical_hash(result)
    return result


# ----------------------------------------------------------------------------- the governed-record loader

def _measurements(root: Path, passport_path: str, passport_hash: str):
    matches = []
    for path in sorted(root.joinpath(*MEASUREMENTS_DIRECTORY.parts).glob("*.physical-measurements.json")):
        record = load_physical_measurements(path)
        if record.passport_path == passport_path and record.passport_manifest_hash == passport_hash:
            matches.append((path, record))
    if not matches:
        return GovernanceItem(DataStatus.NOT_AVAILABLE, "no physical-measurement record is bound to this passport"), None
    if len(matches) > 1:
        return GovernanceItem(DataStatus.NOT_VERIFIED, "several physical-measurement records name this passport: "
                                                       f"{[p.name for p, _ in matches]}"), None
    path, record = matches[0]
    entries = [f"{m.quantity} {m.component}: {len(m.values)} value(s), uncertainty {m.uncertainty.status}"
               + (f" ({m.spec_requirement})" if m.spec_requirement else "") for m in record.measurements]
    gaps = [f"{name}: {reason}" for name, reason in sorted(record.not_available.items())]
    detail = "; ".join(entries + ([f"not available — {'; '.join(gaps)}"] if gaps else []))
    return GovernanceItem(DataStatus.GOVERNED, detail), (path, record)


def _screening(root: Path, label: str, rows: Sequence[StrictRow]) -> dict:
    """The accepted M6.4 screening for this specimen's rows, as DIAGNOSTIC_ONLY context (never a sensitivity column)."""
    if not rows:
        return {"status": DataStatus.NOT_AVAILABLE.value, "detail": "no accepted strict rows to relate it to"}
    try:
        result = json.loads(root.joinpath(*PurePosixPath(SCREENING_RESULT).parts).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"status": DataStatus.NOT_AVAILABLE.value, "detail": f"{SCREENING_RESULT}: {error}"}
    sealed = {key: value for key, value in result.items() if key != "result_hash"}
    if canonical_hash(sealed) != result.get("result_hash"):
        return {"status": DataStatus.NOT_VERIFIED.value, "detail": f"{SCREENING_RESULT} differs from its seal"}
    states = [state for state in result.get("states", []) if state.get("specimen") == label]
    if not states:
        return {"status": DataStatus.NOT_AVAILABLE.value, "detail": f"no M6.4 screening state for {label}"}
    frozen = {(row.row_id, row.role, row.fe_mode) for row in rows}
    screened = {(row["row_id"], row["role"], row["baseline_fe_mode"]) for state in states for row in state["rows"]}
    if screened != frozen:
        return {"status": DataStatus.NOT_VERIFIED.value,
                "detail": "the M6.4 rows are not the counted strict rows of this specimen"}
    effects = {}
    for name, item in sorted(result["constants"].items()):
        changes = [abs(row["relative_change"]) for state in states if state["constant"] == name
                   for row in state["rows"]]
        effects[name] = {"max_abs_relative_change_this_specimen": max(changes, default=0.0),
                         "classification": item["classification"]}
    return {"status": DataStatus.DIAGNOSTIC_ONLY.value, "source": SCREENING_RESULT,
            "result_hash": result["result_hash"], "envelope_basis": result["envelope"]["basis"],
            "detail": "local to the CARBON-4C reference state; fixed-constant budget screening only, never a "
                      "sensitivity column, a rank result or an identifiability claim",
            "constants": effects}


def specimen_observation_readiness(forward_model: str, k: int, *, repo_root: Path = REPO_ROOT,
                                   fixtures: Optional[ExperimentFixtureManifest] = None) -> ObservationReadiness:
    """The observation-readiness record of the governed forward-model manifest ``forward_model`` (read-only).

    ``forward_model`` is a repository-relative ``docs/auto_id/forward_models/*.forward.json``; anything else is refused
    by the governed binder (``CampaignDraftError``).
    """
    root = Path(repo_root).resolve()
    if fixtures is None:
        fixtures = load_experiment_fixture_manifest(root.joinpath(*PurePosixPath(FIXTURE_MANIFEST).parts))
    specimen = governed_specimen_input(root.joinpath(*PurePosixPath(forward_model).parts), root, fixtures)
    passport = load_specimen_manifest(root.joinpath(*PurePosixPath(specimen.passport).parts))
    items: dict[str, GovernanceItem] = {}
    sources = {"forward_model": {"path": specimen.forward_model, "canonical_sha256": specimen.forward_manifest_hash},
               "specimen_passport": {"path": specimen.passport, "canonical_sha256": specimen.passport_manifest_hash}}
    items["forward_model"] = GovernanceItem(DataStatus.GOVERNED, f"{specimen.forward_model_id} (governed binder)")

    fixture = fixtures.fixture(specimen.fixture_id)
    modal_set = fixture.modal_set
    items["experimental_modal_set"] = GovernanceItem(
        DataStatus.GOVERNED, f"fixture {fixture.fixture_id}: set {modal_set.name!r}, {modal_set.mode_count} modes, "
                             f"{modal_set.measurement_point_count} points, {'/'.join(modal_set.measured_dofs)}")
    label = SOURCE_TYPE_MODE_SOURCES.get(modal_set.source_type)
    items["modal_input_source"] = modal_input_item(
        classify_mode_source({"mode_source": label}), True,
        f"fixture source type {modal_set.source_type!r}; the source file is not read here")

    basis = specimen.registration_basis
    if basis == RegistrationBasisStatus.PHYSICAL.value:
        items["physical_registration"] = GovernanceItem(DataStatus.GOVERNED,
                                                        f"PHYSICAL registration {specimen.registration_hash}")
    elif basis == RegistrationBasisStatus.LEGACY_REPLAY.value:
        items["physical_registration"] = GovernanceItem(
            DataStatus.DIAGNOSTIC_ONLY, f"LEGACY_REPLAY registration {specimen.registration_hash}: historical, not "
                                        "SPEC §11 physical evidence")
    else:
        items["physical_registration"] = GovernanceItem(DataStatus.NOT_VERIFIED, f"registration basis {basis}")

    binding = bind_governed_specimen_records(specimen.forward_model, root, fixtures)
    registration_limited = None
    if binding.status == BOUND:
        records = binding.records
        items["governed_records"] = GovernanceItem(DataStatus.GOVERNED, "solver profile, archived baseline, baseline "
                                                                        "shape pack and registration evidence bound")
        for name, record in sorted(records.to_dict().items()):
            sources[name] = {"path": record["path"], "canonical_sha256": record["canonical_sha256"]}
        evidence_path = root.joinpath(*PurePosixPath(records.registration_evidence.path).parts)
        registration_limited = json.loads(evidence_path.read_text(encoding="utf-8")).get("registration_limited")
        items["registration_evidence"] = GovernanceItem(
            DataStatus.GOVERNED, f"{records.registration_evidence.path}: registration_limited = {registration_limited}")
    else:
        reasons = "; ".join(binding.reasons)
        items["governed_records"] = GovernanceItem(DataStatus.NOT_AVAILABLE, reasons)
        items["registration_evidence"] = GovernanceItem(DataStatus.NOT_AVAILABLE, reasons)

    rows: tuple[StrictRow, ...] = ()
    groups: tuple[tuple[str, ...], ...] = ()
    try:
        freeze = accepted_physical_freeze(fixture.fixture_id, repo_root=root)
    except AcceptedReferenceRefusal as refusal:
        items["strict_freeze"] = GovernanceItem(DataStatus.NOT_AVAILABLE, str(refusal))
    else:
        if freeze.registration.registration_hash != specimen.registration_hash:
            items["strict_freeze"] = GovernanceItem(
                DataStatus.NOT_VERIFIED, f"the strict freeze is on registration {freeze.registration.registration_hash}, "
                                         f"not on the forward model's {specimen.registration_hash}")
        else:
            physical = freeze.freeze
            holdouts = set(physical["holdouts"]["holdout_row_ids"])
            rows = tuple(StrictRow(p["row_id"], "HOLDOUT" if p["row_id"] in holdouts else "FIT",
                                   int(p["experimental_mode"]), int(p["fe_mode"]), p["family"], float(p["mac"]),
                                   float(p["relative_frequency_error"])) for p in physical["strict_pairs"])
            groups = tuple(tuple(trigger["row_ids"]) if isinstance(trigger, Mapping) else tuple(trigger)
                           for trigger in physical.get("cluster_triggers", []))
            items["strict_freeze"] = GovernanceItem(
                DataStatus.GOVERNED, f"{freeze.reevaluation_path} results.PHYSICAL FROZEN (pinned "
                                     f"{freeze.reevaluation_hash}); {len(rows)} strict rows")
            sources["strict_freeze"] = {"path": freeze.reevaluation_path, "canonical_sha256": freeze.reevaluation_hash}

    measurement_item, measurement = _measurements(root, specimen.passport, specimen.passport_manifest_hash)
    items["physical_measurements"] = measurement_item
    if measurement is not None:
        path, record = measurement
        sources["physical_measurements"] = {"path": path.relative_to(root).as_posix(),
                                            "canonical_sha256": record.record_hash}
    limit = passport.suspension_max_hz
    items["suspension_threshold"] = (
        GovernanceItem(DataStatus.NOT_AVAILABLE, "suspension_max_hz not recorded; suspension QC NOT_AVAILABLE")
        if limit is None else GovernanceItem(DataStatus.GOVERNED, f"{limit.value_hz} Hz ({limit.source})"))

    evidence = ReadinessEvidence(
        specimen={"label": specimen.label, "physical_specimen_id": specimen.physical_specimen_id,
                  "fixture_id": specimen.fixture_id, "forward_model": specimen.forward_model,
                  "test_run_id": specimen.test_run_id},
        sources=sources, items=items, registration_limited=registration_limited, strict_rows=rows,
        cluster_groups=groups, diagnostics={"m6_4_transverse_screening": _screening(root, specimen.label, rows)})
    return build_observation_readiness(evidence, k)
