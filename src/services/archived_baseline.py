"""Archived baseline replay — Auto-ID M4.2 (SUPERVISOR decision: archived CARBON-4C replay).

An archived-baseline record (schema ``auto-id/archived-baseline/v1``) carries, by content
identity, what an accepted baseline solve left behind: the FE frequencies, the identity of
the generated INP / ODB / FE geometry / registration, the experimental modes, and the MAC
values that were computed and recorded.  No Abaqus or Abaqus Python is run here.

MAC entries that were not recorded stay unknown (NaN).  The strict freeze then reports
incomplete evidence instead of guessing them.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

import numpy as np

from domain.experiment_fixture import ExternalFileReference, FixtureManifestError
from domain.experiment_fixture import _file as _external_file
from domain.experimental_qc import ExperimentalModeEligibility
from domain.frozen_observations import BaselineIdentity

from .baseline_freeze import BaselineEvidence, build_baseline_evidence
from .fe_shape_pack import FEShapePack
from .identification_pairing import ModeFrequency


ARCHIVED_BASELINE_SCHEMA = "auto-id/archived-baseline/v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_KEYS = {"schema", "baseline_id", "forward_model", "candidate", "job", "odb", "source_record", "fe_geometry_sha256",
         "registration_hash", "experimental", "fe_modes", "mac_entries", "provenance"}


class ArchivedBaselineError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


@dataclass(frozen=True)
class MacEntry:
    experimental_mode: int
    fe_mode: int
    mac: float
    origin: str


@dataclass(frozen=True)
class ArchivedBaseline:
    baseline_id: str
    forward_model_path: str
    forward_model_hash: str
    candidate: Mapping[str, float]
    job_name: str
    generated_inp_sha256: str
    odb: ExternalFileReference
    source_record: ExternalFileReference
    fe_geometry_sha256: str
    registration_hash: str
    fixture_id: str
    experimental_source_sha256: str
    modal_set: str
    measured_dofs: tuple[str, ...]
    experimental_modes: tuple[ModeFrequency, ...]
    fe_modes: tuple[ModeFrequency, ...]
    mac_entries: tuple[MacEntry, ...]
    record_sha256: str

    def identity(self, forward_model_id: str) -> BaselineIdentity:
        return BaselineIdentity(forward_model_id, self.job_name, self.generated_inp_sha256, self.fe_geometry_sha256,
                                self.registration_hash, self.experimental_source_sha256, self.modal_set,
                                self.measured_dofs, "archived-carbon4c-replay", self.record_sha256)

    def mac_matrix(self) -> np.ndarray:
        rows = {mode.number: i for i, mode in enumerate(self.experimental_modes)}
        columns = {mode.number: j for j, mode in enumerate(self.fe_modes)}
        matrix = np.full((len(rows), len(columns)), np.nan)
        for entry in self.mac_entries:
            matrix[rows[entry.experimental_mode], columns[entry.fe_mode]] = entry.mac
        return matrix

    def evidence(self, forward_model_id: str, eligibility: ExperimentalModeEligibility) -> BaselineEvidence:
        return build_baseline_evidence(self.identity(forward_model_id), self.experimental_modes, eligibility,
                                       self.fe_modes, self.mac_matrix())


def _mapping(value: object, field: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArchivedBaselineError(field, "must be an object.")
    missing, unknown = sorted(keys - set(value)), sorted(set(value) - keys)
    if missing or unknown:
        raise ArchivedBaselineError(field, f"missing {missing}, unknown {unknown}.")
    return value


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH.match(value):
        raise ArchivedBaselineError(field, "must be a 64-character lowercase hex SHA-256.")
    return value


def _modes(values: object, field: str) -> tuple[ModeFrequency, ...]:
    if not isinstance(values, list) or not values:
        raise ArchivedBaselineError(field, "must be a non-empty list.")
    modes = []
    for item in values:
        data = _mapping(item, f"{field}[]", {"number", "frequency_hz"})
        number, frequency = data["number"], data["frequency_hz"]
        if isinstance(number, bool) or not isinstance(number, int) or not isinstance(frequency, (int, float)) \
                or not math.isfinite(frequency) or frequency <= 0:
            raise ArchivedBaselineError(field, f"invalid mode {item}.")
        modes.append(ModeFrequency(number, float(frequency)))
    if len({mode.number for mode in modes}) != len(modes):
        raise ArchivedBaselineError(field, "mode numbers must be unique.")
    return tuple(modes)


def parse_archived_baseline(data: object, record_sha256: str) -> ArchivedBaseline:
    data = _mapping(data, "record", _KEYS)
    if data["schema"] != ARCHIVED_BASELINE_SCHEMA:
        raise ArchivedBaselineError("schema", f"must be {ARCHIVED_BASELINE_SCHEMA!r}.")
    forward = _mapping(data["forward_model"], "forward_model", {"path", "manifest_hash"})
    job = _mapping(data["job"], "job", {"job_name", "generated_inp_sha256"})
    experimental = _mapping(data["experimental"], "experimental",
                            {"fixture_id", "source_sha256", "modal_set", "measured_dofs", "modes"})
    try:
        odb = _external_file(data["odb"], "odb")
        source = _external_file(data["source_record"], "source_record")
    except FixtureManifestError as exc:
        raise ArchivedBaselineError(exc.field, str(exc)) from exc
    generated = _hash(job["generated_inp_sha256"], "job.generated_inp_sha256")
    if not str(job["job_name"]).endswith("_" + generated[:16]):
        raise ArchivedBaselineError("job.job_name", "must be the content-addressed name of the generated INP.")
    experimental_modes = _modes(experimental["modes"], "experimental.modes")
    fe_modes = _modes(data["fe_modes"], "fe_modes")
    exp_numbers, fe_numbers = {m.number for m in experimental_modes}, {m.number for m in fe_modes}
    entries, seen = [], set()
    for item in data["mac_entries"]:
        entry = _mapping(item, "mac_entries[]", {"experimental_mode", "fe_mode", "mac", "origin"})
        key = (entry["experimental_mode"], entry["fe_mode"])
        if key in seen or key[0] not in exp_numbers or key[1] not in fe_numbers:
            raise ArchivedBaselineError("mac_entries", f"duplicate or unknown mode pair {key}.")
        if not isinstance(entry["mac"], (int, float)) or not 0.0 <= entry["mac"] <= 1.0:
            raise ArchivedBaselineError("mac_entries", f"MAC out of range for {key}.")
        seen.add(key)
        entries.append(MacEntry(key[0], key[1], float(entry["mac"]), str(entry["origin"])))
    candidate = {str(k): float(v) for k, v in dict(data["candidate"]).items()}
    return ArchivedBaseline(
        baseline_id=str(data["baseline_id"]), forward_model_path=str(forward["path"]),
        forward_model_hash=_hash(forward["manifest_hash"], "forward_model.manifest_hash"), candidate=candidate,
        job_name=str(job["job_name"]), generated_inp_sha256=generated, odb=odb, source_record=source,
        fe_geometry_sha256=_hash(data["fe_geometry_sha256"], "fe_geometry_sha256"),
        registration_hash=_hash(data["registration_hash"], "registration_hash"),
        fixture_id=str(experimental["fixture_id"]),
        experimental_source_sha256=_hash(experimental["source_sha256"], "experimental.source_sha256"),
        modal_set=str(experimental["modal_set"]), measured_dofs=tuple(experimental["measured_dofs"]),
        experimental_modes=experimental_modes, fe_modes=fe_modes, mac_entries=tuple(entries),
        record_sha256=record_sha256)


def record_hash(data: object) -> str:
    """Canonical content hash of a record (independent of key order and line endings)."""
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_archived_baseline(path: Path) -> ArchivedBaseline:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return parse_archived_baseline(data, record_hash(data))


# ----------------------------------------------------------------------------- complete MAC matrix from a shape pack

SHAPE_PACK_EVIDENCE_SOURCE = "archived-carbon4c-replay+fe-shape-pack"
RECORDED_MAC_TOLERANCE = 1.0e-9


def _mac(left: np.ndarray, right: np.ndarray) -> float:
    """|a^H b|^2 / (a^H a * b^H b): the comparator's modal assurance criterion (modal_core), on given DOFs."""
    norm_left = float(np.vdot(left, left).real)
    norm_right = float(np.vdot(right, right).real)
    if norm_left <= 1e-30 or norm_right <= 1e-30:
        raise ArchivedBaselineError("mac", "a shape vector is zero on the measured DOFs.")
    return float(np.clip(abs(np.vdot(left, right)) ** 2 / (norm_left * norm_right), 0.0, 1.0))


def _bind_pack(baseline: ArchivedBaseline, pack: FEShapePack, registration, *,
               same_registration: bool = True) -> None:
    record = pack.record
    subset = dict(registration.registration_metrics).get("fe_mapping_node_subset") or {}
    checks = {
        "job_name": record.job_name == baseline.job_name,
        "generated_inp_sha256": record.generated_inp_sha256 == baseline.generated_inp_sha256,
        "odb_sha256": record.odb.sha256 == baseline.odb.sha256,
        "fe_geometry_sha256": record.fe_geometry_sha256 == baseline.fe_geometry_sha256,
        "state": record.state == "BASELINE",
        "registration_fe_geometry": dict(registration.fe_geometry_identity).get("sha256") == baseline.fe_geometry_sha256,
        "node_set": subset.get("sha256") == record.node_set_sha256,
        "fe_modes": tuple(mode.number for mode in baseline.fe_modes) == pack.mode_numbers,
        "fe_frequencies_exact": tuple(mode.frequency_hz for mode in baseline.fe_modes) == pack.frequencies_hz,
    }
    if same_registration:
        checks["registration_hash"] = registration.registration_hash == baseline.registration_hash
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise ArchivedBaselineError("shape_pack", f"the pack does not belong to this baseline: {failed}.")


def complete_mac_matrix(baseline: ArchivedBaseline, pack: FEShapePack, registration,
                        experimental_modes) -> np.ndarray:
    """Experimental x FE MAC on the registration's measured DOFs, from the validated pack.

    FE shapes at the registration-mapped nodes are rotated into the experimental frame (R of the
    FrozenRegistration) and compared on the measured-DOF contract.  Every MAC value recorded in the
    archived baseline must be reproduced (<= 1e-9), or the matrix is refused.
    """

    _bind_pack(baseline, pack, registration)
    matrix = _mac_matrix(baseline, pack, registration, experimental_modes)
    rows = {mode.number: i for i, mode in enumerate(baseline.experimental_modes)}
    columns = {mode.number: j for j, mode in enumerate(baseline.fe_modes)}
    worst = max(abs(matrix[rows[e.experimental_mode], columns[e.fe_mode]] - e.mac) for e in baseline.mac_entries)
    if worst > RECORDED_MAC_TOLERANCE:
        raise ArchivedBaselineError("mac_entries", f"recorded MAC values not reproduced (max difference {worst:.3g}).")
    return matrix


def reregistered_mac_matrix(baseline: ArchivedBaseline, pack: FEShapePack, registration,
                            experimental_modes) -> np.ndarray:
    """The same MAC matrix for a *different*, independently frozen registration (M6 registration gate).

    Every binding of the pack to the baseline is kept (job, INP, ODB, FE geometry, BASELINE state,
    measured node set, FE modes and frequencies) except the registration hash; the archived MAC values
    belong to the archived registration and are therefore not reproduced. The registration must be
    fixed before this is called; nothing here selects or adjusts it.
    """

    _bind_pack(baseline, pack, registration, same_registration=False)
    return _mac_matrix(baseline, pack, registration, experimental_modes)


def _mac_matrix(baseline: ArchivedBaseline, pack: FEShapePack, registration, experimental_modes) -> np.ndarray:
    modes = {mode.number: mode for mode in experimental_modes}
    expected = [(mode.number, mode.frequency_hz) for mode in baseline.experimental_modes]
    if sorted(modes) != [number for number, _ in expected] or any(
            float(modes[number].frequency_hz) != frequency for number, frequency in expected):
        raise ArchivedBaselineError("experimental", "experimental modes differ from the archived baseline record.")
    rotation = np.asarray(registration.rotation, dtype=float)
    mask = np.asarray(registration.measured_dof_contract, dtype=bool)
    experimental_ids = [str(value) for value in registration.experimental_node_ids]
    if mask.shape != (len(experimental_ids), 3) or not mask.any():
        raise ArchivedBaselineError("registration", "measured-DOF contract must be (points, 3) with measured DOFs.")
    fe_rows = pack.rows(registration.mapped_fe_node_ids)
    fe_vectors = {mode.number: pack.displacements[pack.mode_index(mode.number)][fe_rows].astype(np.float64) @ rotation
                  for mode in baseline.fe_modes}
    matrix = np.empty((len(baseline.experimental_modes), len(baseline.fe_modes)))
    for i, (number, _) in enumerate(expected):
        mode = modes[number]
        index = {str(value): k for k, value in enumerate(np.asarray(mode.node_ids, dtype=object).tolist())}
        missing = [node for node in experimental_ids if node not in index]
        if missing:
            raise ArchivedBaselineError("experimental", f"mode {number} lacks registered points {missing[:3]}.")
        experimental = np.asarray(mode.vectors)[[index[node] for node in experimental_ids]]
        for j, fe_mode in enumerate(baseline.fe_modes):
            matrix[i, j] = _mac(fe_vectors[fe_mode.number][mask], experimental[mask])
    return matrix


def shape_pack_evidence(baseline: ArchivedBaseline, pack: FEShapePack, registration, experimental_modes,
                        forward_model_id: str, eligibility: ExperimentalModeEligibility) -> BaselineEvidence:
    """Baseline evidence with the complete MAC matrix from the validated shape pack."""

    matrix = complete_mac_matrix(baseline, pack, registration, experimental_modes)
    identity = BaselineIdentity(forward_model_id, baseline.job_name, baseline.generated_inp_sha256,
                                baseline.fe_geometry_sha256, baseline.registration_hash,
                                baseline.experimental_source_sha256, baseline.modal_set, baseline.measured_dofs,
                                SHAPE_PACK_EVIDENCE_SOURCE, baseline.record_sha256, pack.record.content_sha256)
    return build_baseline_evidence(identity, baseline.experimental_modes, eligibility, baseline.fe_modes, matrix)


REREGISTERED_EVIDENCE_SOURCE = "archived-carbon4c-replay+fe-shape-pack+reregistered"


def reregistered_shape_pack_evidence(baseline: ArchivedBaseline, pack: FEShapePack, registration, experimental_modes,
                                     forward_model_id: str,
                                     eligibility: ExperimentalModeEligibility) -> BaselineEvidence:
    """Baseline evidence on the archived pack under another frozen registration (identity carries its hash)."""

    matrix = reregistered_mac_matrix(baseline, pack, registration, experimental_modes)
    identity = BaselineIdentity(forward_model_id, baseline.job_name, baseline.generated_inp_sha256,
                                baseline.fe_geometry_sha256, registration.registration_hash,
                                baseline.experimental_source_sha256, baseline.modal_set, baseline.measured_dofs,
                                REREGISTERED_EVIDENCE_SOURCE, baseline.record_sha256, pack.record.content_sha256)
    return build_baseline_evidence(identity, baseline.experimental_modes, eligibility, baseline.fe_modes, matrix)
