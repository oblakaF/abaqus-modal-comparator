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
