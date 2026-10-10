"""Read-only Engineering Constants and calibration material preview — Auto-ID M8.6 (SPEC v1.2 §9, §10; D-078).

The presentation of an already RELEASED specimen engineering calibration, from the exact typed ``ScientificReadiness``
that the shared backend returned for the current evaluation and the SHA-256-verified pinned source INP bytes of that
same evaluation (``stored_run_evidence.StoredRunEvaluation``).  Nothing here computes a constant or renders INP text:

- the nine constants are the accepted governed constants (``campaign_scientific_backend.released_engineering_constants``)
  with their own provenance; each is classified by that provenance as a released calibration parameter, a fixed
  campaign parameter or a parameterisation-fixed constant; an unknown provenance or unit refuses;
- the calibration material is the accepted I4 / I5 fragment (``campaign_scientific_backend.released_inp_fragment``):
  the complete governed source material block under a distinct CAL_* name, fail-closed;
- any status other than RELEASED (REFUSED, NOT_READY, MATERIAL_VALUES_RELEASED) or anything that is not the typed
  backend object gives no constants and no fragment; a material identification is never turned into a calibration.

Every preview is labelled with the record's own labels and as not authorised for production: no HUMAN-authorised
production calibration run exists (the calibration execution gate is unchanged), so a RELEASED record is synthetic /
test evidence for readiness only, never an accepted physical calibration.  The fragment exists in memory only: no
file is written, nothing is attached to a production model, nothing is executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Mapping, Optional

from .campaign_scientific_backend import (
    CalibrationFragmentRefusal,
    CalibrationInpFragment,
    ReadinessStatus,
    ScientificReadiness,
    released_engineering_constants,
    released_inp_fragment,
)


class PreviewState(str, Enum):
    AVAILABLE = "PREVIEW_AVAILABLE"
    NOT_AVAILABLE_FOR_SELECTION = "NOT_AVAILABLE_FOR_SELECTION"
    REFUSED = "PREVIEW_REFUSED"  # a RELEASED record whose constants or fragment fail closed


class ConstantOrigin(str, Enum):
    RELEASED_CALIBRATION_PARAMETER = "RELEASED_CALIBRATION_PARAMETER"
    FIXED_CAMPAIGN_PARAMETER = "FIXED_CAMPAIGN_PARAMETER"
    PARAMETERISATION_FIXED_CONSTANT = "PARAMETERISATION_FIXED_CONSTANT"


# The governed INP unit system of the Engineering Constants (SPEC §5.2: moduli in MPa; Poisson's ratios are pure numbers)
CONSTANT_UNITS = {"E1": "MPa", "E2": "MPa", "E3": "MPa", "nu12": "1", "nu13": "1", "nu23": "1",
                  "G12": "MPa", "G13": "MPa", "G23": "MPa"}
NOT_FOR_PRODUCTION = "NOT AUTHORISED FOR PRODUCTION"
TEST_EVIDENCE = "SYNTHETIC / TEST EVIDENCE"
_ORIGINS = (("released calibration parameter ", ConstantOrigin.RELEASED_CALIBRATION_PARAMETER),
            ("campaign definition fixed parameter ", ConstantOrigin.FIXED_CAMPAIGN_PARAMETER))


@dataclass(frozen=True)
class ConstantRow:
    name: str
    value: float  # exactly the governed value (displayed with repr, never rounded)
    unit: str
    origin: ConstantOrigin
    provenance: str  # verbatim from the governed constants


@dataclass(frozen=True)
class CalibrationMaterialPreview:
    state: PreviewState
    reason: str
    constants: tuple[ConstantRow, ...] = ()
    fragment: Optional[CalibrationInpFragment] = None
    production_material_name: Optional[str] = None
    source_material_keywords: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


def not_available(reason: str) -> CalibrationMaterialPreview:
    return CalibrationMaterialPreview(PreviewState.NOT_AVAILABLE_FOR_SELECTION, reason)


def _refused(reason: str) -> CalibrationMaterialPreview:
    return CalibrationMaterialPreview(PreviewState.REFUSED, f"no constants and no fragment: {reason}")


def _rows(record, constants: Mapping) -> tuple[ConstantRow, ...]:
    parameters = {**{k: dict(v) for k, v in record.fixed_parameters.items()},
                  **{k: dict(v) for k, v in record.calibration_parameters.items()}}
    rows = []
    for name, constant in constants.items():
        provenance = constant.provenance
        origin, parameter = ConstantOrigin.PARAMETERISATION_FIXED_CONSTANT, None
        for prefix, kind in _ORIGINS:
            if provenance.startswith(prefix):
                origin, parameter = kind, provenance[len(prefix):]
        if origin is ConstantOrigin.PARAMETERISATION_FIXED_CONSTANT \
                and not provenance.endswith(" fixed constant (SPEC §5.2)"):
            raise CalibrationFragmentRefusal(f"{name}: unknown provenance {provenance!r}.")
        unit = CONSTANT_UNITS.get(name)
        if unit is None:
            raise CalibrationFragmentRefusal(f"unknown Engineering Constant {name!r}.")
        if parameter is not None:
            declared = (parameters.get(parameter) or {}).get("unit")
            if parameter not in parameters or declared != unit:
                raise CalibrationFragmentRefusal(f"{name}: parameter {parameter} has unit {declared!r}, not {unit}.")
        rows.append(ConstantRow(name, constant.value, unit, origin, provenance))
    if tuple(r.name for r in rows) != tuple(CONSTANT_UNITS):
        raise CalibrationFragmentRefusal(f"incomplete or reordered Engineering Constants {[r.name for r in rows]}.")
    return tuple(rows)


def calibration_material_preview(readiness, source_inps: Mapping[str, bytes]) -> CalibrationMaterialPreview:
    """The read-only constants and material preview of one typed backend evaluation (no file, no execution)."""

    if not isinstance(readiness, ScientificReadiness):
        return not_available("no typed backend evaluation of the current selection (a stored or display-only record "
                             "never produces constants or a fragment).")
    if readiness.status is ReadinessStatus.MATERIAL_VALUES_RELEASED:
        return not_available("MATERIAL_VALUES_RELEASED is a material identification; it is never turned into a "
                             "specimen calibration, so there are no calibration constants and no fragment.")
    if readiness.status is not ReadinessStatus.RELEASED or not readiness.released:
        return not_available(f"backend status {readiness.status.value}: no calibration is released, so there are no "
                             "constants and no fragment.")
    record = readiness.calibration_record
    label = str(record.identity["specimen"]["label"])
    source = (source_inps or {}).get(label)
    if not isinstance(source, (bytes, bytearray)):
        return _refused(f"the pinned source INP of {label} is not available from this evaluation.")
    digest = hashlib.sha256(bytes(source)).hexdigest()
    if digest != record.identity["inp_sha256"]:
        return _refused(f"the source INP SHA-256 {digest} is not the pinned {record.identity['inp_sha256']}.")
    try:
        rows = _rows(record, released_engineering_constants(readiness))
        fragment = released_inp_fragment(readiness, bytes(source))
    except CalibrationFragmentRefusal as refusal:
        return _refused(str(refusal))
    production = str(record.identity["forward_model"]["production_material_name"])
    if fragment.source_inp_sha256 != digest or fragment.source_calibration_record_hash != record.record_hash \
            or fragment.material_name.lower() == production.lower():
        return _refused("the fragment is not bound to this calibration record and source INP.")
    keywords = tuple(line.split(",")[0].strip() for line in fragment.content.splitlines()
                     if line.startswith("*") and not line.startswith("**"))
    document = readiness.to_dict()
    profiles = "; ".join(f"{name}: {item.get('profile_id')}"
                         for name, item in sorted((document["evidence"].get("solver_profiles") or {}).items()))
    labels = tuple(document["calibration"]["labels"]) + (NOT_FOR_PRODUCTION, TEST_EVIDENCE)
    evidence = (
        f"{TEST_EVIDENCE}: no HUMAN-authorised production calibration run exists; this record is readiness evidence "
        "only and never an accepted physical calibration.",
        f"Solver profiles: {profiles or 'none'}.",
        f"Physical calibration status: {document.get('production_calibration')}.",
        f"Production execution: {document.get('production_execution')}.",
    )
    return CalibrationMaterialPreview(
        PreviewState.AVAILABLE,
        "RELEASED specimen calibration of the current evaluation; preview in memory only (no file is written and it is "
        "never attached to a production model).",
        rows, fragment, production, keywords, labels, evidence)


def preview_lines(preview: CalibrationMaterialPreview) -> tuple[str, ...]:
    """Display text of a preview (reads and formats only)."""

    lines = [f"Calibration material preview: {preview.state.value}", preview.reason]
    if preview.state is not PreviewState.AVAILABLE:
        return tuple(lines)
    fragment = preview.fragment
    lines += [
        f"Labels: {', '.join(preview.labels)}",
        f"Calibration material (in memory only): {fragment.material_name}",
        f"Production material: {preview.production_material_name} (unchanged; never overwritten)",
        f"Source INP SHA-256 (verified): {fragment.source_inp_sha256}",
        f"Source material block SHA-256: {fragment.source_material_block_sha256} "
        f"(options kept: {', '.join(preview.source_material_keywords)})",
        f"Calibration record: {fragment.source_calibration_record_hash}; gate record: {fragment.gate_record_hash}",
        *preview.evidence,
    ]
    return tuple(lines)
