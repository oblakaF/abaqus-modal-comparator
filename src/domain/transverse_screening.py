"""Transverse-constant screening envelope — Auto-ID M6.4 (SPEC §5, §5.2; D-055, D-061, D-066).

E3, ν13, ν23, G13 and G23 of the carbon face are fixed in ``carbon-property-set/v1``.  M6.4
checks, by FE only, whether varying each one over a SUPERVISOR-approved screening envelope
changes the frozen observation frequencies by less than the SPEC criterion (0.3 %):

- ``NEGLIGIBLE_FOR_BUDGET``: max |Δf/f| < 0.3 % on every frozen row, specimen and endpoint;
- ``INCLUDE_IN_UNCERTAINTY_BUDGET``: otherwise.  This is bookkeeping only: it is not a failure,
  not a model-fit target and never a reason to re-tune the model (D-066).

The envelope is data (schema ``auto-id/transverse-screening-envelope/v1``), never code.  A
screening perturbation sets exactly one screened constant to one envelope endpoint while the
in-plane candidate stays at the recorded reference point.  Perturbations are not
parameterisations: they are never fitted.  Parsing is strict; nothing is guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Mapping

import numpy as np

from .forward_model_manifest import PARAMETERISATIONS, EngineeringConstants, canonical_hash


ENVELOPE_SCHEMA = "auto-id/transverse-screening-envelope/v1"
SCREENED_CONSTANTS = ("E3", "nu13", "nu23", "G13", "G23")
ENDPOINTS = ("low", "high")
ENVELOPE_BASES = ("LITERATURE_INTERIM_SCREENING_ENVELOPE",)
SPEC_FREQUENCY_CRITERION = 0.003  # SPEC §5: "changes frequencies by < 0.3 %" (D-055: unchanged)
NEGLIGIBLE = "NEGLIGIBLE_FOR_BUDGET"
INCLUDE = "INCLUDE_IN_UNCERTAINTY_BUDGET"
ROW_ROLES = ("FIT", "HOLDOUT")

_TOP_KEYS = {"schema", "envelope_id", "basis", "basis_statement", "decision", "parameterisation",
             "reference_candidate", "criterion", "constants", "extraction_modes", "specimens", "provenance"}
_SPECIMEN_KEYS = {"label", "forward_model", "solver_profile", "baseline_shape_pack", "observation_source", "rows"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_UNITS = {"E3": "MPa", "nu13": "1", "nu23": "1", "G13": "MPa", "G23": "MPa"}


class ScreeningEnvelopeError(ValueError):
    """A screening envelope or perturbation is malformed or not authorised; nothing is guessed."""


def _fail(field: str, message: str):
    raise ScreeningEnvelopeError(f"{field}: {message}")


def _mapping(value: object, field: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(field, "must be an object.")
    missing, unknown = sorted(keys - set(value)), sorted(set(value) - keys)
    if missing or unknown:
        _fail(field, f"missing {missing}, unknown {unknown}.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _fail(field, "must be a non-empty string without surrounding whitespace.")
    return value


def _repo_path(value: object, field: str) -> str:
    text = _text(value, field)
    if "\\" in text or re.match(r"^[A-Za-z]:", text) or text.startswith("/") or ".." in text.split("/"):
        _fail(field, "must be a repository-relative POSIX path.")
    return text


def _positive(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) \
            or float(value) <= 0.0:
        _fail(field, "must be a finite positive number.")
    return float(value)


@dataclass(frozen=True)
class ScreeningRange:
    constant: str
    unit: str
    baseline: float
    low: float
    high: float

    def endpoint(self, name: str) -> float:
        if name not in ENDPOINTS:
            raise ScreeningEnvelopeError(f"endpoint must be one of {ENDPOINTS}.")
        return self.low if name == "low" else self.high


@dataclass(frozen=True)
class ObservationRow:
    row_id: str
    fe_mode: int  # baseline FE mode number of the frozen row
    role: str  # FIT | HOLDOUT


@dataclass(frozen=True)
class ScreeningSpecimen:
    label: str
    forward_model: str
    solver_profile: str
    baseline_shape_pack: str
    observation_source: str
    rows: tuple[ObservationRow, ...]

    @property
    def row_modes(self) -> dict[str, int]:
        return {row.row_id: row.fe_mode for row in self.rows}


@dataclass(frozen=True)
class ScreeningPerturbation:
    """One screened constant at one envelope endpoint (every other constant stays at its baseline)."""

    envelope_id: str
    envelope_hash: str
    constant: str
    endpoint: str
    value: float
    baseline: float

    def __post_init__(self) -> None:
        if self.constant not in SCREENED_CONSTANTS:
            raise ScreeningEnvelopeError(f"{self.constant!r} is not a screened constant {SCREENED_CONSTANTS}.")
        if self.endpoint not in ENDPOINTS:
            raise ScreeningEnvelopeError(f"endpoint must be one of {ENDPOINTS}.")
        for name in ("value", "baseline"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ScreeningEnvelopeError(f"{name} must be a finite positive number.")
        if self.value == self.baseline:
            raise ScreeningEnvelopeError(f"{self.perturbation_id}: an endpoint equal to the baseline is no perturbation.")

    @property
    def perturbation_id(self) -> str:
        return f"{self.constant}-{self.endpoint}"

    def to_dict(self) -> dict:
        return {"envelope_id": self.envelope_id, "envelope_hash": self.envelope_hash, "constant": self.constant,
                "endpoint": self.endpoint, "value": self.value, "baseline": self.baseline}


@dataclass(frozen=True)
class ScreeningEnvelope:
    envelope_id: str
    basis: str
    basis_statement: str
    decision: str
    parameterisation_id: str
    reference_candidate: Mapping[str, float]
    criterion: float
    ranges: Mapping[str, ScreeningRange]
    extraction_modes: tuple[int, ...]
    specimens: tuple[ScreeningSpecimen, ...]
    provenance: tuple[str, ...]
    canonical: Mapping[str, Any]

    @property
    def envelope_hash(self) -> str:
        return canonical_hash(self.canonical)

    def perturbations(self) -> tuple[ScreeningPerturbation, ...]:
        """The one-at-a-time endpoint perturbations; an endpoint equal to the baseline needs no solve."""
        return tuple(ScreeningPerturbation(self.envelope_id, self.envelope_hash, name, endpoint,
                                           self.ranges[name].endpoint(endpoint), self.ranges[name].baseline)
                     for name in SCREENED_CONSTANTS for endpoint in ENDPOINTS
                     if self.ranges[name].endpoint(endpoint) != self.ranges[name].baseline)

    def baseline_endpoints(self) -> tuple[tuple[str, str], ...]:
        """(constant, endpoint) pairs whose endpoint is the baseline: Δf ≡ 0 by definition, no solve."""
        return tuple((name, endpoint) for name in SCREENED_CONSTANTS for endpoint in ENDPOINTS
                     if self.ranges[name].endpoint(endpoint) == self.ranges[name].baseline)

    def require_perturbation(self, perturbation: ScreeningPerturbation) -> ScreeningPerturbation:
        if not isinstance(perturbation, ScreeningPerturbation) or perturbation not in self.perturbations():
            raise ScreeningEnvelopeError("the perturbation is not one of this envelope's endpoint perturbations.")
        return perturbation

    def specimen(self, label: str) -> ScreeningSpecimen:
        for item in self.specimens:
            if item.label == label:
                return item
        raise ScreeningEnvelopeError(f"no screening specimen {label!r}.")


def classify(max_abs_relative_change: float) -> str:
    """The SPEC §5 bookkeeping rule: strictly below 0.3 % is negligible, otherwise budgeted."""
    value = float(max_abs_relative_change)
    if not math.isfinite(value) or value < 0.0:
        raise ScreeningEnvelopeError("the relative frequency change must be finite and non-negative.")
    return NEGLIGIBLE if value < SPEC_FREQUENCY_CRITERION else INCLUDE


def orthotropic_compliance(constants: EngineeringConstants) -> np.ndarray:
    """6×6 compliance of Abaqus ENGINEERING CONSTANTS (ν_ij: strain j from stress i; ν_ij/E_i = ν_ji/E_j)."""
    c = constants
    compliance = np.zeros((6, 6))
    compliance[:3, :3] = [[1.0 / c.E1, -c.nu12 / c.E1, -c.nu13 / c.E1],
                          [-c.nu12 / c.E1, 1.0 / c.E2, -c.nu23 / c.E2],
                          [-c.nu13 / c.E1, -c.nu23 / c.E2, 1.0 / c.E3]]
    compliance[3, 3], compliance[4, 4], compliance[5, 5] = 1.0 / c.G12, 1.0 / c.G13, 1.0 / c.G23
    return compliance


def require_material_stability(constants: EngineeringConstants) -> EngineeringConstants:
    """Refuse constants whose compliance is not positive definite (Abaqus would reject them)."""
    if min(constants.E1, constants.E2, constants.E3, constants.G12, constants.G13, constants.G23) <= 0.0:
        raise ScreeningEnvelopeError("moduli must be positive.")
    if float(np.linalg.eigvalsh(orthotropic_compliance(constants)).min()) <= 0.0:
        raise ScreeningEnvelopeError(f"constants {constants.to_dict()} are not positive definite.")
    return constants


def screened_constants(base: EngineeringConstants, perturbation: ScreeningPerturbation) -> EngineeringConstants:
    """``base`` with exactly the perturbed constant replaced; the baseline must be the base value."""
    if getattr(base, perturbation.constant) != perturbation.baseline:
        raise ScreeningEnvelopeError(f"{perturbation.perturbation_id}: the base value of {perturbation.constant} is "
                                     f"{getattr(base, perturbation.constant)}, not the envelope baseline "
                                     f"{perturbation.baseline}.")
    values = base.to_dict()
    values[perturbation.constant] = perturbation.value
    return require_material_stability(EngineeringConstants(**values))


def _rows(value: object, field: str) -> tuple[ObservationRow, ...]:
    if not isinstance(value, list) or not value:
        _fail(field, "must be a non-empty list.")
    rows = []
    for index, item in enumerate(value):
        data = _mapping(item, f"{field}[{index}]", {"row_id", "fe_mode", "role"})
        mode = data["fe_mode"]
        if isinstance(mode, bool) or not isinstance(mode, int) or mode < 1:
            _fail(f"{field}[{index}].fe_mode", "must be a positive integer.")
        if data["role"] not in ROW_ROLES:
            _fail(f"{field}[{index}].role", f"must be one of {ROW_ROLES}.")
        rows.append(ObservationRow(_text(data["row_id"], f"{field}[{index}].row_id"), mode, data["role"]))
    if len({row.row_id for row in rows}) != len(rows) or len({row.fe_mode for row in rows}) != len(rows):
        _fail(field, "row ids and FE modes must be unique.")
    return tuple(rows)


def parse_screening_envelope(data: object) -> ScreeningEnvelope:
    data = _mapping(data, "envelope", _TOP_KEYS)
    if data["schema"] != ENVELOPE_SCHEMA:
        _fail("schema", f"must be {ENVELOPE_SCHEMA!r}.")
    envelope_id = _text(data["envelope_id"], "envelope_id")
    if not _IDENTIFIER.match(envelope_id):
        _fail("envelope_id", "must use letters, digits, '.', '_', '-' or '/'.")
    if data["basis"] not in ENVELOPE_BASES:
        _fail("basis", f"must be one of {ENVELOPE_BASES} (the envelope is not a material-specific prior).")
    statement = _text(data["basis_statement"], "basis_statement")
    decision = _text(data["decision"], "decision")

    parameterisation_id = data["parameterisation"]
    if parameterisation_id not in PARAMETERISATIONS:
        _fail("parameterisation", f"unknown parameterisation {parameterisation_id!r}.")
    parameterisation = PARAMETERISATIONS[parameterisation_id]
    if not set(SCREENED_CONSTANTS) <= set(parameterisation.fixed_constants):
        _fail("parameterisation", "every screened constant must be a fixed constant of the parameterisation.")

    reference = data["reference_candidate"]
    if not isinstance(reference, Mapping) or set(reference) != set(parameterisation.parameters):
        _fail("reference_candidate", f"must set exactly {parameterisation.parameters}.")
    reference = {name: _positive(reference[name], f"reference_candidate.{name}") for name in parameterisation.parameters}

    criterion = _mapping(data["criterion"], "criterion", {"metric", "value", "comparison", "purpose"})
    if criterion["metric"] != "max_abs_relative_frequency_change" or criterion["comparison"] != "strictly_below":
        _fail("criterion", "must be max_abs_relative_frequency_change, strictly_below.")
    if criterion["value"] != SPEC_FREQUENCY_CRITERION:
        _fail("criterion.value", f"the SPEC §5 criterion is {SPEC_FREQUENCY_CRITERION}; it is not configurable.")
    purpose = _text(criterion["purpose"], "criterion.purpose")

    constants = data["constants"]
    if not isinstance(constants, Mapping) or set(constants) != set(SCREENED_CONSTANTS):
        _fail("constants", f"must give exactly {SCREENED_CONSTANTS}.")
    ranges = {}
    for name in SCREENED_CONSTANTS:
        item = _mapping(constants[name], f"constants.{name}", {"unit", "baseline", "low", "high"})
        if item["unit"] != _UNITS[name]:
            _fail(f"constants.{name}.unit", f"must be {_UNITS[name]!r}.")
        baseline, low, high = (_positive(item[key], f"constants.{name}.{key}") for key in ("baseline", "low", "high"))
        if baseline != parameterisation.fixed_constants[name]:
            _fail(f"constants.{name}.baseline", f"must be the governed fixed value {parameterisation.fixed_constants[name]}.")
        if not low <= baseline <= high or low == high:
            _fail(f"constants.{name}", "needs low ≤ baseline ≤ high and low < high.")
        ranges[name] = ScreeningRange(name, item["unit"], baseline, low, high)

    modes = _mapping(data["extraction_modes"], "extraction_modes", {"start", "end"})
    start, end = modes["start"], modes["end"]
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end)) or not 1 <= start <= end:
        _fail("extraction_modes", "needs integers 1 ≤ start ≤ end.")
    extraction_modes = tuple(range(start, end + 1))

    if not isinstance(data["specimens"], list) or not data["specimens"]:
        _fail("specimens", "must be a non-empty list.")
    specimens = []
    for index, item in enumerate(data["specimens"]):
        field = f"specimens[{index}]"
        entry = _mapping(item, field, _SPECIMEN_KEYS)
        rows = _rows(entry["rows"], f"{field}.rows")
        if any(row.fe_mode not in extraction_modes for row in rows):
            _fail(f"{field}.rows", "every frozen FE mode must be among the extraction modes.")
        specimens.append(ScreeningSpecimen(
            _text(entry["label"], f"{field}.label"), _repo_path(entry["forward_model"], f"{field}.forward_model"),
            _repo_path(entry["solver_profile"], f"{field}.solver_profile"),
            _repo_path(entry["baseline_shape_pack"], f"{field}.baseline_shape_pack"),
            _text(entry["observation_source"], f"{field}.observation_source"), rows))
    if len({item.label for item in specimens}) != len(specimens):
        _fail("specimens", "labels must be unique.")

    provenance = data["provenance"]
    if not isinstance(provenance, list) or not provenance:
        _fail("provenance", "must be a non-empty list.")
    provenance = tuple(_text(item, "provenance[]") for item in provenance)

    # Every perturbed state must be a stable material at the reference candidate.
    base = parameterisation.engineering_constants(reference)
    for name in SCREENED_CONSTANTS:
        for endpoint in ENDPOINTS:
            values = base.to_dict()
            values[name] = ranges[name].endpoint(endpoint)
            try:
                require_material_stability(EngineeringConstants(**values))
            except ScreeningEnvelopeError as exc:
                _fail(f"constants.{name}.{endpoint}", str(exc))

    canonical = {
        "schema": ENVELOPE_SCHEMA, "envelope_id": envelope_id, "basis": data["basis"], "basis_statement": statement,
        "decision": decision, "parameterisation": parameterisation_id, "reference_candidate": reference,
        "criterion": {"metric": "max_abs_relative_frequency_change", "value": SPEC_FREQUENCY_CRITERION,
                      "comparison": "strictly_below", "purpose": purpose},
        "constants": {name: {"unit": r.unit, "baseline": r.baseline, "low": r.low, "high": r.high}
                      for name, r in ranges.items()},
        "extraction_modes": {"start": start, "end": end},
        "specimens": [{"label": s.label, "forward_model": s.forward_model, "solver_profile": s.solver_profile,
                       "baseline_shape_pack": s.baseline_shape_pack, "observation_source": s.observation_source,
                       "rows": [{"row_id": r.row_id, "fe_mode": r.fe_mode, "role": r.role} for r in s.rows]}
                      for s in specimens],
        "provenance": list(provenance),
    }
    return ScreeningEnvelope(envelope_id, data["basis"], statement, decision, parameterisation_id, reference,
                             SPEC_FREQUENCY_CRITERION, ranges, extraction_modes, tuple(specimens), provenance, canonical)


def load_screening_envelope(path) -> ScreeningEnvelope:
    with open(path, encoding="utf-8") as handle:
        return parse_screening_envelope(json.load(handle))
