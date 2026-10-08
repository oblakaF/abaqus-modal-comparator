"""Additive governed physical-measurement record of a specimen (D-076; audit iteration 2, finding K3).

The specimen passport (``specimen.json``) is pinned by its canonical hash in forward-model manifests and run
identities, so documentary physical facts are not written into it.  This record sits beside it, bound to the
passport's path and manifest hash, and records each known physical value with its traceable source.

Rules:
- strict, versioned schema; unknown fields are refused;
- every value cites a pinned source file (store + relative path + SHA-256) and the verbatim source text;
- a unit that the source does not write is recorded as such (``unit_stated_in_source`` false), never implied;
- instrument resolution is not an uncertainty: a numeric ``sd`` exists only with status ``MEASURED_SD`` and an
  explicit basis; otherwise the status is ``NOT_AVAILABLE`` or ``PROVISIONAL_WITHOUT_NUMERIC_SD`` with no number;
- the record never changes the passport, a registration, a fixture, a freeze or a mode pair.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from .experiment_fixture import ExternalFileReference, _file as _external_file
from .specimen_manifest import canonical_hash


PHYSICAL_MEASUREMENTS_SCHEMA = "auto-id/specimen-physical-measurements/v1"
QUANTITIES = ("plan_mm", "masses_g", "face_thickness_mm", "core_height_mm", "total_thickness_mm")
UNCERTAINTY_STATUSES = ("NOT_AVAILABLE", "PROVISIONAL_WITHOUT_NUMERIC_SD", "MEASURED_SD")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_TOP = {"schema", "specimen_passport", "physical_specimen_id", "sources", "measurements", "not_available", "note"}
_ENTRY = {"quantity", "component", "values", "unit", "unit_stated_in_source", "source", "source_text", "method",
          "uncertainty", "spec_requirement", "remarks"}


class PhysicalMeasurementsError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


def _fail(field: str, message: str):
    raise PhysicalMeasurementsError(field, message)


def _keys(value: object, field: str, required: set[str], optional: frozenset = frozenset()) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(field, "must be an object.")
    missing, unknown = sorted(required - set(value)), sorted(set(value) - required - optional)
    if missing or unknown:
        _fail(field, f"missing {missing}, unknown {unknown}.")
    return value


def _text(value: object, field: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail(field, "must be a non-empty string.")
    return value


@dataclass(frozen=True)
class MeasurementUncertainty:
    status: str
    sd: Optional[float]
    basis: str


@dataclass(frozen=True)
class PhysicalMeasurement:
    quantity: str
    component: str
    values: tuple[float, ...]
    unit: str
    unit_stated_in_source: bool
    source: str
    source_text: str
    method: Optional[str]
    uncertainty: MeasurementUncertainty
    spec_requirement: Optional[str]
    remarks: Optional[str]


@dataclass(frozen=True)
class PhysicalMeasurementsRecord:
    passport_path: str
    passport_manifest_hash: str
    physical_specimen_id: str
    sources: Mapping[str, ExternalFileReference]
    measurements: tuple[PhysicalMeasurement, ...]
    not_available: Mapping[str, str]
    canonical: Mapping[str, Any]

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.canonical)

    def values(self, quantity: str) -> dict[str, tuple[float, ...]]:
        return {m.component: m.values for m in self.measurements if m.quantity == quantity}


def _uncertainty(value: object, field: str) -> MeasurementUncertainty:
    value = _keys(value, field, {"status", "sd", "basis"})
    status = value["status"]
    if status not in UNCERTAINTY_STATUSES:
        _fail(f"{field}.status", f"must be one of {UNCERTAINTY_STATUSES}.")
    sd = value["sd"]
    if status == "MEASURED_SD":
        if isinstance(sd, bool) or not isinstance(sd, (int, float)) or not math.isfinite(sd) or sd <= 0:
            _fail(f"{field}.sd", "MEASURED_SD needs a positive finite sd.")
    elif sd is not None:
        _fail(f"{field}.sd", f"{status} has no numeric sd (instrument resolution is not an uncertainty).")
    return MeasurementUncertainty(status, None if sd is None else float(sd), _text(value["basis"], f"{field}.basis"))


def parse_physical_measurements(data: object) -> PhysicalMeasurementsRecord:
    data = _keys(data, "record", _TOP)
    if data["schema"] != PHYSICAL_MEASUREMENTS_SCHEMA:
        _fail("schema", f"must be {PHYSICAL_MEASUREMENTS_SCHEMA!r}.")
    passport = _keys(data["specimen_passport"], "specimen_passport", {"path", "manifest_hash"})
    if not isinstance(passport["manifest_hash"], str) or not _HASH.match(passport["manifest_hash"]):
        _fail("specimen_passport.manifest_hash", "must be a SHA-256.")
    sources_data = data["sources"]
    if not isinstance(sources_data, Mapping) or not sources_data:
        _fail("sources", "must name at least one pinned source file.")
    sources = {name: _external_file(value, f"sources.{name}") for name, value in sources_data.items()}
    entries = data["measurements"]
    if not isinstance(entries, list) or not entries:
        _fail("measurements", "must be a non-empty list.")
    measurements = []
    seen = set()
    for index, entry in enumerate(entries):
        field = f"measurements[{index}]"
        entry = _keys(entry, field, _ENTRY)
        if entry["quantity"] not in QUANTITIES:
            _fail(f"{field}.quantity", f"must be one of {QUANTITIES}.")
        component = _text(entry["component"], f"{field}.component")
        if (entry["quantity"], component) in seen:
            _fail(field, "duplicate quantity / component.")
        seen.add((entry["quantity"], component))
        values = entry["values"]
        if not isinstance(values, list) or not values or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
            _fail(f"{field}.values", "must be a non-empty list of positive finite numbers.")
        if entry["source"] not in sources:
            _fail(f"{field}.source", "must name one of the pinned sources.")
        if not isinstance(entry["unit_stated_in_source"], bool):
            _fail(f"{field}.unit_stated_in_source", "must be true or false.")
        measurements.append(PhysicalMeasurement(
            entry["quantity"], component, tuple(float(v) for v in values), _text(entry["unit"], f"{field}.unit"),
            entry["unit_stated_in_source"], entry["source"], _text(entry["source_text"], f"{field}.source_text"),
            _text(entry["method"], f"{field}.method", nullable=True), _uncertainty(entry["uncertainty"], f"{field}.uncertainty"),
            _text(entry["spec_requirement"], f"{field}.spec_requirement", nullable=True),
            _text(entry["remarks"], f"{field}.remarks", nullable=True)))
    not_available = data["not_available"]
    if not isinstance(not_available, Mapping) or any(not isinstance(v, str) or not v.strip()
                                                      for v in not_available.values()):
        _fail("not_available", "must map each missing fact to its reason.")
    canonical = json.loads(json.dumps(data, sort_keys=True))
    return PhysicalMeasurementsRecord(_text(passport["path"], "specimen_passport.path"), passport["manifest_hash"],
                                      _text(data["physical_specimen_id"], "physical_specimen_id"), sources,
                                      tuple(measurements), dict(not_available), canonical)


def load_physical_measurements(path: Path) -> PhysicalMeasurementsRecord:
    with open(path, encoding="utf-8") as handle:
        return parse_physical_measurements(json.load(handle))
