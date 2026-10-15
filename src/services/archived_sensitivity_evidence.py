"""Archived CARBON-5A modal sensitivities for an ODB + PolyMAX comparison (G2c; display only).

For the two accepted baselines (SP-02 and SP-13, CARBON-4C template E_in 52 000 / G12 4 500 MPa) the accepted
strict-freeze records hold S(i, p) = d ln f_i / d ln p for E_in and G12. They are central differences over the
archived CARBON-5A ±5 % states, taken on resolved FE-to-FE branches. This module shows those recorded values for
the current two-file comparison only when the comparison is bound to exactly that evidence:

- the comparison's ODB and resolved experimental file are hashed afresh (SHA-256 and size; never a cached
  path/size/mtime identity) and must be the accepted baseline ODB and PolyMAX source of one fixture;
- the imported PolyMAX modal set, its measurement points and measured-DOF contract replay the fixture's frozen
  physical registration (``experiment_fixture_regression``);
- the registration is hash-sealed, pinned and content-compatible with the loaded files
  (``FrozenRegistration.check_content_compatible``), and every mapped FE node exists in the loaded FE model;
- the archived baseline record, the strict-freeze record and the accepted forward jobs are pinned and mutually
  consistent (baseline and ±5 % parameter values, policy, registration, pack identities);
- each displayed row is an accepted strict pair whose FE / experimental frequencies are the recorded ones, whose
  sensitivity branch was resolved in all four states, and which the current comparison pairs identically with a
  MAC-supported match (the G1 classification of the accepted strict pairing policy).

Anything else is ``SENSITIVITY_EVIDENCE_NOT_APPLICABLE`` with the precise reason. Specimen name, file name, similar
frequencies, geometry or material family never establish compatibility.

Two statuses show the recorded values, and they are kept apart:

- ``ARCHIVED_SENSITIVITY_REFERENCE_ONLY``: the exact files and every accepted record match, so the values are valid
  archived sensitivities of that FE model and its pinned physical reference. The live comparison's own registration
  is not demonstrably the governed one, so this is NOT a governed verification of the current comparison (file
  hashes, mode numbers and MAC do not establish it).
- ``ARCHIVED_SENSITIVITY_EVIDENCE_VERIFIED``: additionally, the comparison maps every measurement point to the same
  FE node as the frozen physical registration, with the same rotation. The GUI comparator places points by centring,
  not by the panel edges of the physical registration, so it does not currently reach this status.

Nothing is estimated: no E, G or ν, no sensitivity-based correction, no calibration or identification verdict. The
recorded values are local sensitivities of those exact FE models; they do not transfer to any other model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import stat as stat_module
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from domain.experiment_fixture import ExperimentFixture, load_experiment_fixture_manifest
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.registration import RegistrationMismatchError
from frequency_scaling import MAC_SUPPORTED, scaling_row
from scientific_state import modal_dataset_geometry_identity
from services.archived_baseline import ArchivedBaselineError, load_archived_baseline, record_hash
from services.experiment_fixture_regression import (
    FixtureRegressionError,
    load_fixture_registration,
    verify_fixture_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

VERIFIED = "ARCHIVED_SENSITIVITY_EVIDENCE_VERIFIED"
REFERENCE_ONLY = "ARCHIVED_SENSITIVITY_REFERENCE_ONLY"
NOT_APPLICABLE = "SENSITIVITY_EVIDENCE_NOT_APPLICABLE"
REFERENCE_ONLY_STATEMENT = (
    "These are valid archived FE-model sensitivities of the exact ODB / UNV and the pinned physical reference; they "
    "are NOT a governed verification of the current GUI comparison.")
LABELS = ("ARCHIVED_SENSITIVITY_EVIDENCE_DISPLAY_ONLY", "NOT_A_MATERIAL_PROPERTY", "NOT_A_SPECIMEN_CALIBRATION",
          "NOT_TRANSFERABLE_TO_OTHER_MODELS")
LABEL_TEXT = " · ".join(LABELS)
CAVEAT = ("Recorded local sensitivities S = d ln f / d ln p of the exact accepted SP-02 / SP-13 FE models (CARBON-5A "
          "central differences over ±5 % about the template E_in 52 000 / G12 4 500 MPa). They are not material "
          "properties and no correction is derived from them. A frequency mismatch is not a parameter change: "
          "outliers stay as recorded.")

FIXTURE_MANIFEST = "docs/auto_id/fixtures/real_experiment_fixtures.json"
ACCEPTED_FORWARD_JOBS = "docs/auto_id/forward_models/accepted_forward_jobs.json"
# Canonical content hashes (key order and line endings ignored), as pinned for the historical evidence by V12-I5.
ACCEPTED_FORWARD_JOBS_HASH = "40914b07a4034eda7eddcbd50662cfc28f1b896394386f644eae3db4fd4e8f71"
BASELINE_CANDIDATE = "CARBON-4C BASELINE"
# Recorded direction key -> accepted CARBON-5A candidate, parameter and factor (the archived ±5 %; unchanged).
PERTURBATIONS = {
    "E_in_plane_mpa+": ("CARBON-5A E_PLUS", "E_in_plane_mpa", 1.05),
    "E_in_plane_mpa-": ("CARBON-5A E_MINUS", "E_in_plane_mpa", 0.95),
    "G12_mpa+": ("CARBON-5A G_PLUS", "G12_mpa", 1.05),
    "G12_mpa-": ("CARBON-5A G_MINUS", "G12_mpa", 0.95),
}
CANDIDATE_FIELDS = {"E_in_plane_mpa": "e_in_plane_mpa", "G12_mpa": "g12_mpa"}
# Mode identity only: FE frequencies are archived in single precision (as in the re-evaluation tools).
FREQUENCY_IDENTITY_RELATIVE = 1.0e-6
# Registration equivalence: rotations are signed-axis matrices; the same tolerance as domain.registration.
ROTATION_IDENTITY_TOLERANCE = 1.0e-6
CARBON5A_ARCHIVE_ROWS = "carbon5a-archive-rows"  # SP-02: per-row status / tracked modes from carbon5a CSVs
BRANCH_TRACKED_PACKS = "branch-tracked-shape-packs"  # SP-13: track_branches over the ±5 % shape packs
_CHUNK_BYTES = 1 << 22


@dataclass(frozen=True)
class SpecimenEvidence:
    """The accepted records of one specimen whose archived sensitivities may be shown."""

    specimen: str
    fixture_id: str
    baseline_path: str
    reevaluation_path: str
    reevaluation_hash: str
    sensitivity_structure: str


SPECIMENS = (
    SpecimenEvidence("SP02", "SP02/bravo-1-physical", "docs/auto_id/baselines/SP02.carbon4c-baseline.json",
                     "docs/auto_id/registration_evidence/SP02_registration_reevaluation.json",
                     "a488f1ebe01b15d7fce50f5219554011404a8ea24f6208938387c32a5678d553", CARBON5A_ARCHIVE_ROWS),
    SpecimenEvidence("SP13", "SP13/best-physical", "docs/auto_id/baselines/SP13.carbon4c-baseline.json",
                     "docs/auto_id/registration_evidence/SP13_registration_reevaluation.json",
                     "5c2e897c813107323c768316d8b38463988b59371cab6968f590420ca437d27b", BRANCH_TRACKED_PACKS),
)

SCIENTIFIC_LIMITATIONS = (
    "Local central differences over the archived ±5 % only; values far outside that range are not described.",
    "Valid only for this exact FE model (mesh, geometry, thicknesses, core, ties, mass, boundary conditions); "
    "never for another ODB.",
    "FE vs experiment frequency differences (hand-made panels; up to about 10 % can be informative) are not "
    "parameter changes. Outliers are preserved; changing E_in or G12 to remove them would hide a possible model-form "
    "origin (core, adhesive / ties, boundary conditions, mass distribution).",
    "D-074 / D-075: G12 adjusted on these modes compensates model form "
    "(COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY, BARE_PLATE_REQUIRED).",
    "D-077: RUN_A family consistency FAIL, RUN_B NOT_EVALUABLE_RANK_DEFICIENT, NO_GLOBAL_PARAMETER_VALUE; the "
    "historical RUN_A / RUN_B optimiser values are not material properties or accepted calibration values.",
    "SPEC v1.2 §6: a specimen calibration is issued only through the governed gate; none is issued here.",
)


class SensitivityCheckCancelled(Exception):
    """The check was cancelled (inputs or comparison changed); its partial state is discarded."""


class AcceptedReferenceRefusal(ValueError):
    """The files, datasets or records are not exactly an accepted SP-02 / SP-13 reference; the message says why."""

    def __init__(self, message: str, specimen: Optional[str] = None) -> None:
        super().__init__(message)
        self.specimen = specimen


_Refusal = AcceptedReferenceRefusal


@dataclass(frozen=True)
class AcceptedReference:
    """An accepted specimen reference bound to the exact compared files and loaded datasets."""

    spec: "SpecimenEvidence"
    fixture: ExperimentFixture
    registration: Any  # the sealed, content-compatible FrozenRegistration
    checks: tuple[str, ...]


@dataclass(frozen=True)
class SensitivityRow:
    row_id: str
    role: str  # FIT | HOLDOUT | NO_STRICT_ROW
    experimental_mode: int
    fe_mode: Optional[int]
    experimental_hz: Optional[float]
    fe_hz: Optional[float]
    relative_frequency_error: Optional[float]  # recorded (f_FE - f_exp) / f_exp; not a parameter change
    governed_mac: Optional[float]
    comparison_mac: Optional[float]
    s_e: Optional[float]
    s_g12: Optional[float]
    branch: str
    applicable: bool
    reason: str


@dataclass(frozen=True)
class SensitivityEvidence:
    status: str
    specimen: Optional[str]
    reasons: tuple[str, ...]
    rows: tuple[SensitivityRow, ...] = ()
    checks: tuple[str, ...] = ()  # the identity / record checks that passed (never a verification of the comparison)
    limitations: tuple[str, ...] = ()
    baseline: Mapping[str, float] = field(default_factory=dict)
    perturbations: Mapping[str, float] = field(default_factory=dict)
    source: str = ""
    labels: tuple[str, ...] = LABELS

    @property
    def shows_sensitivities(self) -> bool:
        return self.status in (VERIFIED, REFERENCE_ONLY)


def not_applicable(reason: str, *, specimen: Optional[str] = None, checks: Sequence[str] = ()) -> SensitivityEvidence:
    return SensitivityEvidence(NOT_APPLICABLE, specimen, (reason,), checks=tuple(checks))


# ----------------------------------------------------------------------------- comparison inputs

def comparison_input_record(abaqus: Path, experimental: Path, modal_set: Optional[str]) -> dict[str, Any]:
    """The files a comparison actually read, with their size and mtime at that time (change detection only)."""

    record = {"requested_modal_set": modal_set}
    for key, path in (("abaqus", abaqus), ("experimental", experimental)):
        resolved = Path(path).resolve()
        status = resolved.stat()
        record[key] = {"path": str(resolved), "size": int(status.st_size), "mtime_ns": int(status.st_mtime_ns)}
    return record


def _check_cancelled(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise SensitivityCheckCancelled()


def fresh_content_identity(path: Path, cancel=None) -> dict[str, Any]:
    """SHA-256 and size read from the file now (no cache); a file that changes while it is read is refused."""

    try:
        before = path.stat()
    except OSError as error:
        raise _Refusal(f"{path} cannot be read: {error}") from error
    if not stat_module.S_ISREG(before.st_mode):
        raise _Refusal(f"{path} is not a regular file.")
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(_CHUNK_BYTES), b""):
                _check_cancelled(cancel)
                digest.update(chunk)
        after = path.stat()
    except OSError as error:
        raise _Refusal(f"{path} cannot be read: {error}") from error
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise _Refusal(f"{path} changed while it was being hashed.")
    return {"path": os.path.normcase(str(path)), "size": int(before.st_size), "mtime_ns": int(before.st_mtime_ns),
            "sha256": digest.hexdigest()}


def _recorded_inputs(result) -> tuple[Path, Path]:
    record = (getattr(result, "metadata", None) or {}).get("comparison_inputs")
    if not isinstance(record, Mapping):
        raise _Refusal("the comparison did not record the files it read; run the comparison again.")
    paths = []
    for key, name in (("abaqus", "ODB"), ("experimental", "experimental file")):
        item = record.get(key)
        if not isinstance(item, Mapping) or not item.get("path"):
            raise _Refusal(f"the comparison did not record its {name}; run the comparison again.")
        path = Path(str(item["path"]))
        try:
            status = path.stat()
        except OSError as error:
            raise _Refusal(f"the compared {name} {path} is no longer readable: {error}") from error
        if (int(status.st_size), int(status.st_mtime_ns)) != (item.get("size"), item.get("mtime_ns")):
            raise _Refusal(f"the compared {name} {path} changed after the comparison; run the comparison again.")
        paths.append(path)
    return paths[0], paths[1]


# ----------------------------------------------------------------------------- accepted records

def _load_json(repo_root: Path, relative: str) -> Any:
    try:
        with open(Path(repo_root) / relative, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        raise _Refusal(f"accepted record {relative} is unavailable: {error}") from error


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise _Refusal(reason)


def _short(digest: object) -> str:
    return f"{str(digest)[:12]}…"


def _select_specimen(fixtures, odb: Mapping[str, Any], experimental: Mapping[str, Any]):
    known = []
    for spec in SPECIMENS:
        try:
            fixture = fixtures.fixture(spec.fixture_id)
        except KeyError as error:
            raise _Refusal(f"accepted fixture {spec.fixture_id} is missing from {FIXTURE_MANIFEST}.") from error
        reference = fixture.fe.odb_reference
        known.append(f"{spec.specimen} {_short(reference.sha256)}")
        if reference.sha256 == odb["sha256"]:
            _require(odb["size"] == reference.size_bytes,
                     f"the ODB has {odb['size']} bytes; the accepted {spec.specimen} baseline ODB has "
                     f"{reference.size_bytes}.")
            source = fixture.experimental_source
            _require(experimental["sha256"] == source.sha256 and experimental["size"] == source.size_bytes,
                     f"the experimental file SHA-256 {_short(experimental['sha256'])} ({experimental['size']} bytes) "
                     f"is not the accepted {spec.specimen} PolyMAX source {source.file_name} "
                     f"({_short(source.sha256)}, {source.size_bytes} bytes).")
            return spec, fixture
    raise _Refusal(f"the ODB SHA-256 {_short(odb['sha256'])} is not an accepted baseline ODB "
                   f"({', '.join(known)}); archived sensitivities belong only to those exact FE models.")


def _candidate(jobs: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    matches = [item for item in jobs.get("candidates", ()) if item.get("name") == name]
    _require(len(matches) == 1, f"accepted forward jobs: candidate {name!r} is missing or ambiguous.")
    return matches[0]


def _perturbations(spec: SpecimenEvidence, baseline, jobs: Mapping[str, Any]) -> dict[str, tuple[float, str]]:
    """The accepted ±5 % parameter values of this specimen (value, generated INP SHA-256) per direction."""

    _require(record_hash(jobs) == ACCEPTED_FORWARD_JOBS_HASH,
             f"{ACCEPTED_FORWARD_JOBS} differs from its pinned content.")
    base_job = _candidate(jobs, BASELINE_CANDIDATE).get("jobs", {}).get(spec.specimen, {})
    _require(base_job.get("generated_inp_sha256") == baseline.generated_inp_sha256,
             f"the archived {spec.specimen} baseline job is not the accepted CARBON-4C baseline job.")
    values = {}
    for direction, (name, parameter, factor) in PERTURBATIONS.items():
        candidate = _candidate(jobs, name)
        for other, key in CANDIDATE_FIELDS.items():
            expected = baseline.candidate[other] * (factor if other == parameter else 1.0)
            _require(math.isclose(float(candidate.get(key, math.nan)), expected, rel_tol=1e-12),
                     f"accepted candidate {name!r} {key} is not the archived ±5 % value {expected:g}.")
        job = candidate.get("jobs", {}).get(spec.specimen, {})
        _require(isinstance(job.get("generated_inp_sha256"), str),
                 f"accepted candidate {name!r} has no {spec.specimen} job.")
        values[direction] = (baseline.candidate[parameter] * factor, job["generated_inp_sha256"])
    return values


def _physical_freeze(spec: SpecimenEvidence, document: Mapping[str, Any], baseline, fixture: ExperimentFixture,
                     registration) -> Mapping[str, Any]:
    _require(record_hash(document) == spec.reevaluation_hash, f"{spec.reevaluation_path} differs from its pinned content.")
    _require(document.get("baseline_record_sha256") == baseline.record_sha256,
             f"{spec.reevaluation_path} was not evaluated on the archived {spec.specimen} baseline record.")
    _require(document.get("policy_id") == STRICT_IDENTIFICATION_PAIRING.policy_id
             and document.get("policy_hash") == STRICT_IDENTIFICATION_PAIRING.policy_hash,
             f"{spec.reevaluation_path} was not frozen under the accepted strict pairing policy.")
    _require(document.get("physical_registration_file") == fixture.registration.path,
             f"{spec.reevaluation_path} is not bound to {fixture.registration.path}.")
    physical = (document.get("results") or {}).get("PHYSICAL")
    _require(isinstance(physical, Mapping) and physical.get("status") == "FROZEN",
             f"{spec.reevaluation_path} holds no frozen PHYSICAL strict freeze.")
    _require(physical.get("registration_hash") == registration.registration_hash,
             f"the strict freeze was made on registration {_short(physical.get('registration_hash'))}, not on the "
             f"accepted physical registration {_short(registration.registration_hash)}.")
    return physical


def _bound_baseline(spec: SpecimenEvidence, fixture: ExperimentFixture, repo_root: Path):
    try:
        baseline = load_archived_baseline(Path(repo_root) / spec.baseline_path)
    except (OSError, ValueError, ArchivedBaselineError) as error:
        raise _Refusal(f"archived baseline {spec.baseline_path} unavailable: {error}") from error
    _require(baseline.odb.sha256 == fixture.fe.odb_reference.sha256
             and baseline.fe_geometry_sha256 == fixture.fe.geometry_identity.sha256
             and baseline.experimental_source_sha256 == fixture.experimental_source.sha256
             and baseline.modal_set == fixture.modal_set.name,
             f"archived baseline {spec.baseline_path} is not bound to fixture {fixture.fixture_id}.")
    return baseline


@dataclass(frozen=True)
class AcceptedPhysicalFreeze:
    """The accepted strict physical freeze of one specimen, with the records it was verified against."""

    specimen: str
    fixture: ExperimentFixture
    registration: Any  # the fixture's sealed FrozenRegistration
    reevaluation_path: str
    reevaluation_hash: str  # canonical content hash, equal to the pinned one
    baseline_path: str
    baseline_record_sha256: str
    freeze: Mapping[str, Any]  # a copy of the record's results.PHYSICAL (status FROZEN)


def accepted_physical_freeze(fixture_id: str, *, repo_root: Path = REPO_ROOT) -> AcceptedPhysicalFreeze:
    """The accepted strict physical freeze of ``fixture_id`` from the repository records only, or refuse.

    The same checks as the sensitivity display: the fixture's sealed registration, the archived baseline bound to the
    fixture, the pinned strict-freeze record under the accepted strict pairing policy on that registration. No data
    store is read and no observation is created. Raises ``AcceptedReferenceRefusal`` with the reason.
    """
    spec = next((item for item in SPECIMENS if item.fixture_id == fixture_id), None)
    _require(spec is not None, f"no accepted strict freeze is recorded for fixture {fixture_id!r}.")
    try:
        fixture = load_experiment_fixture_manifest(Path(repo_root) / FIXTURE_MANIFEST).fixture(fixture_id)
        registration = load_fixture_registration(fixture, Path(repo_root))
    except (OSError, ValueError, KeyError) as error:
        raise _Refusal(f"fixture {fixture_id}: {error}", spec.specimen) from error
    try:
        baseline = _bound_baseline(spec, fixture, repo_root)
        document = _load_json(repo_root, spec.reevaluation_path)
        physical = _physical_freeze(spec, document, baseline, fixture, registration)
    except AcceptedReferenceRefusal as refusal:
        raise AcceptedReferenceRefusal(str(refusal), spec.specimen) from refusal
    return AcceptedPhysicalFreeze(spec.specimen, fixture, registration, spec.reevaluation_path, spec.reevaluation_hash,
                                  spec.baseline_path, baseline.record_sha256, json.loads(json.dumps(physical)))


def _branch(spec: SpecimenEvidence, document: Mapping[str, Any], physical: Mapping[str, Any], row_id: str,
            perturbations: Mapping[str, tuple[float, str]]) -> tuple[Optional[float], Optional[float], str, str]:
    """(S_E, S_G12, branch text, refusal reason or '') of one strict row, from the record's own structure."""

    if spec.sensitivity_structure == CARBON5A_ARCHIVE_ROWS:
        item = (physical.get("sensitivities_carbon5a") or {}).get(row_id)
        if not isinstance(item, Mapping):
            return None, None, "no archived sensitivity", f"no archived CARBON-5A sensitivity is recorded for {row_id}."
        tracked = item.get("tracked") or {}
        if item.get("status") != "RESOLVED" or set(tracked) != set(PERTURBATIONS):
            return None, None, f"branch {item.get('status', 'NOT_AVAILABLE')}", (
                f"the FE-to-FE branch of {row_id} is not resolved in all four CARBON-5A states.")
        modes = "/".join(str(tracked[key]) for key in PERTURBATIONS)
        branch = (f"RESOLVED in E+/E-/G+/G-: FE {modes}; min tracked MAC(U3) "
                  f"{float(item.get('min_tracked_mac_u3', math.nan)):.7f} (carbon5a/branch_tracking.csv)")
    else:
        refusals = physical.get("tracking_refusals")
        item = (physical.get("sensitivities") or {}).get(row_id)
        packs = document.get("packs") or {}
        expected = {key: f"{spec.specimen}_{perturbations[key][1][:16]}" for key in PERTURBATIONS}
        if any(packs.get(key) != name for key, name in expected.items()):
            return None, None, "pack provenance differs", (
                f"the ±5 % shape packs of {row_id} are not the accepted CARBON-5A jobs.")
        if refusals != [] or not isinstance(item, Mapping):
            return None, None, "branch not resolved", (
                f"the FE-to-FE branch of {row_id} was refused by the strict branch tracker.")
        branch = ("RESOLVED by the strict branch tracker (tracking MAC "
                  f"{STRICT_IDENTIFICATION_PAIRING.tracking_minimum_mac:.2f}) over packs "
                  + ", ".join(expected[key] for key in PERTURBATIONS))
    values = (item.get("S_E"), item.get("S_G12"))
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        return None, None, "no archived sensitivity", f"the archived sensitivity of {row_id} is not finite."
    return float(values[0]), float(values[1]), branch, ""


# ----------------------------------------------------------------------------- comparison binding

def _frequencies(dataset) -> dict[int, float]:
    return {int(mode.number): float(mode.frequency_hz) for mode in dataset.sorted_modes()}


def _same_frequency(value: Optional[float], recorded: float) -> bool:
    return value is not None and math.isclose(value, recorded, rel_tol=FREQUENCY_IDENTITY_RELATIVE)


def registration_equivalence(result, registration) -> tuple[bool, str]:
    """Whether the live comparison demonstrably uses the frozen physical registration, and why (or why not).

    Equivalent only if every measurement point (in the frozen point order, already replayed) maps to the same FE
    node and the rotation is the frozen one. Anything that cannot be read is not equivalent.
    """
    frozen = registration.mapped_fe_node_ids
    try:
        reference = result.abaqus.sorted_modes()[0]
        mapped = [str(value) for value in np.asarray(reference.node_ids, dtype=object)[
            np.asarray(result.geometry.experimental_to_abaqus, dtype=int).reshape(-1)]]
        rotation = np.asarray(result.geometry.rotation, dtype=float)
    except Exception:  # noqa: BLE001 - an unreadable registration is never equivalent
        return False, (f"The comparison's own registration cannot be compared with the physical registration "
                       f"{_short(registration.registration_hash)}; it is not demonstrably equivalent.")
    same = sum(left == right for left, right in zip(mapped, frozen))
    same_rotation = rotation.shape == (3, 3) and bool(np.allclose(rotation, np.asarray(registration.rotation),
                                                                  rtol=0.0, atol=ROTATION_IDENTITY_TOLERANCE))
    equivalent = len(mapped) == len(frozen) and same == len(frozen) and same_rotation
    source = (getattr(result, "metadata", None) or {}).get("orientation_source", "unknown")
    text = (f"The comparison's registration ({source}) maps {same} of {len(frozen)} measurement points to the same FE "
            f"node as the accepted physical registration {_short(registration.registration_hash)}; rotation "
            f"{'identical' if same_rotation else 'different'}.")
    if equivalent:
        return True, text + " It is the governed physical mapping."
    return False, (text + " It is not demonstrably equivalent: governed MAC values come from the strict freeze on "
                   "the physical registration, comparison MAC values from the current comparison.")


def _rows(spec, document, physical, perturbations, result, equivalent: bool) -> list[SensitivityRow]:
    shown = ("accepted strict pair; the comparison uses the governed physical mapping; recorded values shown"
             if equivalent else "accepted strict pair; archived FE-model values shown as REFERENCE ONLY (the "
             "comparison's registration is not the governed physical registration)")
    fe_hz = _frequencies(result.abaqus)
    experimental_hz = _frequencies(result.experimental)
    pairs = list(getattr(result, "pairs", None) or ())
    holdouts = set((physical.get("holdouts") or {}).get("holdout_row_ids") or ())
    rows = []
    for pair_record in physical.get("strict_pairs") or ():
        row_id = str(pair_record["row_id"])
        exp_mode, fe_mode = int(pair_record["experimental_mode"]), int(pair_record["fe_mode"])
        s_e, s_g12, branch, reason = _branch(spec, document, physical, row_id, perturbations)
        match = next((p for p in pairs if p.abaqus_mode == fe_mode and p.experimental_mode == exp_mode), None)
        comparison_mac = None if match is None else match.mac
        if not reason and not _same_frequency(fe_hz.get(fe_mode), float(pair_record["fe_hz"])):
            reason = (f"FE mode {fe_mode} of the comparison is missing or not the recorded mode "
                      f"({pair_record['fe_hz']:.4f} Hz).")
        if not reason and not _same_frequency(experimental_hz.get(exp_mode), float(pair_record["experimental_hz"])):
            reason = (f"experimental mode {exp_mode} of the comparison is missing or not the recorded mode "
                      f"({pair_record['experimental_hz']:.4f} Hz).")
        if not reason and match is None:
            other = next((p.abaqus_mode for p in pairs if p.experimental_mode == exp_mode), None)
            reason = (f"the comparison does not pair experimental mode {exp_mode} with FE mode {fe_mode} "
                      + ("(it is unpaired)." if other is None else f"(it pairs it with FE mode {other})."))
        if not reason:
            classified = scaling_row(match)
            if classified.category != MAC_SUPPORTED:
                reason = (f"the comparison pair is {classified.category}: " + "; ".join(classified.warnings) + ".")
        rows.append(SensitivityRow(
            row_id, "HOLDOUT" if row_id in holdouts else "FIT", exp_mode, fe_mode,
            float(pair_record["experimental_hz"]), float(pair_record["fe_hz"]),
            float(pair_record["relative_frequency_error"]), float(pair_record["mac"]), comparison_mac,
            None if reason else s_e, None if reason else s_g12, branch, not reason,
            reason or shown))
    best = {int(item["experimental_mode"]): item for item in physical.get("best_match_per_experimental_mode") or ()}
    for excluded in physical.get("excluded") or ():  # preserved outliers: no strict row, no sensitivity shown
        exp_mode = int(excluded["experimental_mode"])
        match = best.get(exp_mode, {})
        fe_mode = match.get("best_fe_mode")
        note = "" if fe_mode is None else (
            f"; recorded best match FE {fe_mode} (MAC {match['best_mac']:.3f}, FE vs exp. "
            f"{match['relative_frequency_error']:+.1%})")
        rows.append(SensitivityRow(
            "—", "NO_STRICT_ROW", exp_mode, fe_mode, experimental_hz.get(exp_mode),
            None if fe_mode is None else fe_hz.get(int(fe_mode)), match.get("relative_frequency_error"),
            match.get("best_mac"), None, None, None, "not applicable", False,
            f"no accepted strict pair: {excluded['reason']}{note}. Outlier preserved; no sensitivity shown."))
    return rows


# ----------------------------------------------------------------------------- binding to an accepted reference

def match_accepted_files(odb_path: Path, experimental_path: Path, *, repo_root: Path = REPO_ROOT, cancel=None):
    """(spec, fixture, ODB identity, experimental identity) when both files are, by fresh SHA-256 and size, the
    accepted baseline ODB and PolyMAX source of one fixture; otherwise AcceptedReferenceRefusal."""

    _check_cancelled(cancel)
    odb = fresh_content_identity(Path(odb_path), cancel)
    experimental = fresh_content_identity(Path(experimental_path), cancel)
    _check_cancelled(cancel)
    try:
        fixtures = load_experiment_fixture_manifest(Path(repo_root) / FIXTURE_MANIFEST)
    except (OSError, ValueError, KeyError) as error:
        raise _Refusal(f"accepted fixture manifest unavailable: {error}") from error
    spec, fixture = _select_specimen(fixtures, odb, experimental)
    return spec, fixture, odb, experimental


def bind_accepted_reference(odb_path: Path, experimental_path: Path, abaqus, experimental_dataset, *,
                            repo_root: Path = REPO_ROOT, cancel=None, checks: Optional[list] = None) -> AcceptedReference:
    """Bind the exact files and their loaded datasets to an accepted specimen reference, or refuse with the reason.

    Fresh SHA-256 of both files; the PolyMAX modal set, points and measured-DOF contract replay the frozen physical
    registration; the sealed registration is content-compatible with the loaded files and every mapped FE node is
    present. ``checks`` collects the passed checks (also on refusal).
    """

    checks = [] if checks is None else checks
    spec, fixture, odb, experimental = match_accepted_files(odb_path, experimental_path, repo_root=repo_root,
                                                            cancel=cancel)
    try:
        checks.append(f"ODB SHA-256 {_short(odb['sha256'])} = accepted {spec.specimen} CARBON-4C baseline ODB "
                      f"{fixture.fe.odb_reference.file_name}")
        checks.append(f"experimental SHA-256 {_short(experimental['sha256'])} = {fixture.experimental_source.file_name}")
        try:
            registration = load_fixture_registration(fixture, Path(repo_root))
            report = verify_fixture_dataset(fixture, registration, experimental_dataset)
        except FixtureRegressionError as error:
            raise _Refusal(f"fixture {fixture.fixture_id}: {error}") from error
        checks.append(f"PolyMAX modal set {report.modal_set_key!r} ({report.mode_source}; {report.mode_count} modes, "
                      f"{report.point_count} points, measured {'/'.join(report.measured_dofs)}) replays the frozen "
                      "registration's points and measured-DOF contract")
        _check_cancelled(cancel)
        try:
            fe_identity = modal_dataset_geometry_identity(abaqus)
            registration.check_content_compatible(experimental, fe_identity)
        except (RegistrationMismatchError, ValueError) as error:
            raise _Refusal(f"physical registration {_short(registration.registration_hash)}: {error}") from error
        loaded_nodes = {str(value) for value in np.asarray(abaqus.sorted_modes()[0].node_ids, dtype=object)}
        missing = [node for node in registration.mapped_fe_node_ids if node not in loaded_nodes]
        _require(not missing, f"{len(missing)} FE nodes of the frozen measured-node mapping are absent from the ODB.")
        checks.append(f"physical registration {_short(registration.registration_hash)} (sealed; calibration "
                      f"{_short(registration.calibration_fingerprint)}, orientation {registration.orientation_candidate_id}"
                      f") is content-compatible: FE geometry {_short(fe_identity['sha256'])} "
                      f"({fe_identity['node_count']} nodes); all {len(registration.mapped_fe_node_ids)} mapped FE nodes present")
        _check_cancelled(cancel)
    except AcceptedReferenceRefusal as refusal:
        raise AcceptedReferenceRefusal(str(refusal), spec.specimen) from refusal
    return AcceptedReference(spec, fixture, registration, tuple(checks))


# ----------------------------------------------------------------------------- the check

def check_archived_sensitivity_evidence(result, *, repo_root: Path = REPO_ROOT, cancel=None) -> SensitivityEvidence:
    """Check the comparison against the accepted SP-02 / SP-13 evidence and return the recorded rows, or refuse.

    The status is VERIFIED only for a demonstrably equivalent registration; with matching files and records but
    another registration it is REFERENCE_ONLY; anything incompatible or unavailable is NOT_APPLICABLE.

    Raises ``SensitivityCheckCancelled`` when ``cancel`` is set; the caller discards the check.
    """

    checks: list[str] = []
    specimen = None
    try:
        _require(result is not None, "there is no comparison result.")
        odb_path, experimental_path = _recorded_inputs(result)
        reference = bind_accepted_reference(odb_path, experimental_path, result.abaqus, result.experimental,
                                            repo_root=repo_root, cancel=cancel, checks=checks)
        spec, fixture, registration = reference.spec, reference.fixture, reference.registration
        specimen = spec.specimen

        baseline = _bound_baseline(spec, fixture, repo_root)
        perturbations = _perturbations(spec, baseline, _load_json(repo_root, ACCEPTED_FORWARD_JOBS))
        document = _load_json(repo_root, spec.reevaluation_path)
        physical = _physical_freeze(spec, document, baseline, fixture, registration)
        checks.append(f"accepted records pinned and consistent: baseline {_short(baseline.record_sha256)}, strict freeze "
                      f"{_short(spec.reevaluation_hash)} ({STRICT_IDENTIFICATION_PAIRING.policy_id}), forward jobs "
                      f"{_short(ACCEPTED_FORWARD_JOBS_HASH)}")

        equivalent, mapping_note = registration_equivalence(result, registration)
        rows = _rows(spec, document, physical, perturbations, result, equivalent)
    except _Refusal as refusal:
        return not_applicable(str(refusal), specimen=specimen or refusal.specimen, checks=checks)

    applicable = [row for row in rows if row.applicable]
    fit_rows = sum(row.role == "FIT" for row in rows)
    limitations = (
        mapping_note,
        f"Recorded strict freeze: {fit_rows} FIT row(s); observation_sufficient = "
        f"{physical.get('observation_sufficient')}.",
        *SCIENTIFIC_LIMITATIONS,
    )
    common = dict(specimen=specimen, rows=tuple(rows), checks=tuple(checks), limitations=limitations,
                  baseline=dict(baseline.candidate),
                  perturbations={key: value for key, (value, _) in perturbations.items()},
                  source=f"{spec.reevaluation_path} (results.PHYSICAL); CARBON-5A ±5 %")
    if not applicable:
        reasons = tuple(f"{row.row_id}: {row.reason}" for row in rows if row.role != "NO_STRICT_ROW")
        return SensitivityEvidence(NOT_APPLICABLE, reasons=("no accepted strict pair is supported by this "
                                                             "comparison.",) + reasons, **common)
    if not equivalent:
        return SensitivityEvidence(REFERENCE_ONLY, reasons=(REFERENCE_ONLY_STATEMENT, mapping_note), **common)
    return SensitivityEvidence(VERIFIED, reasons=(), **common)


# ----------------------------------------------------------------------------- presentation

TABLE_COLUMNS = ("row", "role", "em", "fe", "ef", "ff", "df", "gmac", "cmac", "se", "sg", "branch", "reason")
TABLE_TITLES = ("Row", "Role", "Exp. mode", "FE mode", "Exp., Hz", "FE, Hz", "FE vs exp. (recorded)",
                "Governed MAC", "Comparison MAC", "S_E (archived)", "S_G12 (archived)", "Sensitivity branch",
                "Applicability")
TABLE_WIDTHS = (50, 110, 75, 65, 90, 90, 140, 105, 120, 110, 120, 520, 520)


def _number(value: Optional[float], text: str) -> str:
    return "—" if value is None else format(value, text)


def table_rows(evidence: SensitivityEvidence) -> tuple[tuple[str, ...], ...]:
    return tuple((row.row_id, row.role, str(row.experimental_mode), _number(row.fe_mode, "d"),
                  _number(row.experimental_hz, ".4f"), _number(row.fe_hz, ".4f"),
                  _number(row.relative_frequency_error, "+.2%"), _number(row.governed_mac, ".3f"),
                  _number(row.comparison_mac, ".3f"), _number(row.s_e, ".4f"), _number(row.s_g12, ".4f"),
                  row.branch, row.reason) for row in evidence.rows)


def summary_text(evidence: SensitivityEvidence) -> str:
    lines = [f"{evidence.status}" + (f" — {evidence.specimen}" if evidence.specimen else "")]
    lines += [f"Reason: {reason}" for reason in evidence.reasons]
    if evidence.baseline:
        base = evidence.baseline
        perturbed = evidence.perturbations
        lines.append(f"Baseline (CARBON-4C template): E_in {base['E_in_plane_mpa']:.0f} MPa, G12 {base['G12_mpa']:.0f} MPa. "
                     f"Archived ±5 %: E_in {perturbed['E_in_plane_mpa-']:.0f} / {perturbed['E_in_plane_mpa+']:.0f} MPa, "
                     f"G12 {perturbed['G12_mpa-']:.0f} / {perturbed['G12_mpa+']:.0f} MPa. Source: {evidence.source}.")
    lines += [f"Checked: {item}" for item in evidence.checks]
    lines += [f"Limitation: {item}" for item in evidence.limitations]
    return "\n".join(lines)
