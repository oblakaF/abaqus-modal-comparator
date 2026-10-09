"""SPECIMEN_ENGINEERING_CALIBRATION output record and separate calibration INP fragment — Auto-ID V12-I4
(SPEC v1.2 §1 B, §6, §9, §10; D-078).

``build_calibration_output`` evaluates the V12-I3 gate itself, on the same ``CalibrationGateInputs``, and
builds one deterministic record:

- **RELEASED** (gate PASS): class SPECIMEN_ENGINEERING_CALIBRATION with the labels
  SPECIMEN_ENGINEERING_CALIBRATION, NOT_A_MATERIAL_PROPERTY, NOT_TRANSFERABLE_WITHOUT_VALIDATION; the
  calibration parameters are exactly the judged ``p_hat`` (role MODEL_CALIBRATION_PARAMETER), never a
  material property, never IDENTIFIED / WIDE;
- **REFUSED** (gate REFUSED): no calibration parameter at all; the judged candidate appears only as
  ``diagnostic_optimizer_candidate`` labelled DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE.

Both carry the bound identity (specimen, test run, forward model, INP SHA-256, registration, campaign, run,
τ_mf, gate record hash), the I3 precision and uncertainty basis unchanged, τ_mf only as an
ACCEPTANCE_TOLERANCE, the full governed physical-row table (cluster members row by row) and the excluded
high-MAC diagnostic records (DIAGNOSTIC_ONLY). An inconsistent identity or evidence bundle is an input
error, never a record.

``render_calibration_inp_fragment`` is a separate pure renderer: it accepts only a RELEASED record, the
complete nine governed Engineering Constants (checked against the forward model's parameterisation) and the
exact pinned source INP bytes (SHA-256 checked against the record). It clones the complete governed production
material block (density, damping and every other supported option unchanged, with the forward builder's
parsing semantics) under a distinct CAL_* name and changes only the Engineering Constants. It never builds or
renders a forward job; nothing is read from or written to disk; nothing is executed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import math
import re
from typing import Mapping, Optional, Sequence

from domain.campaign_definition import SPECIMEN_ENGINEERING_CALIBRATION
from domain.forward_model_manifest import (
    PARAMETERISATIONS,
    EngineeringConstants,
)
from domain.identification_run import canonical_hash

from .forward_builder import (
    ForwardBuildError,
    inp_keyword,
    locate_engineering_constants,
    material_block_bounds,
    rewrite_engineering_constants,
    split_inp_lines,
)
from .identification_campaign_run import CampaignSpecimenInput
from .practical_identifiability import PracticalIdentifiabilityInputError
from .specimen_calibration_gate import CalibrationGateInputs, evaluate_calibration_gate


SCHEMA = "auto-id/specimen-engineering-calibration/v1"
QUANTITY = "specimen_engineering_calibration"
LABELS = ("SPECIMEN_ENGINEERING_CALIBRATION", "NOT_A_MATERIAL_PROPERTY", "NOT_TRANSFERABLE_WITHOUT_VALIDATION")
CANDIDATE_LABELS = ("DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE")
PARAMETER_ROLE = "MODEL_CALIBRATION_PARAMETER"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
TAU_MF_ROLE = "ACCEPTANCE_TOLERANCE"
PARAMETER_UNITS = {"E_in_plane_mpa": "MPa", "G12_mpa": "MPa"}
_MATERIAL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")


class CalibrationOutputStatus(str, Enum):
    RELEASED = "RELEASED"
    REFUSED = "REFUSED"


class CalibrationFragmentRefusal(Exception):
    """No calibration INP fragment can be rendered. Not a ValueError: generic handlers never swallow it."""


@dataclass(frozen=True)
class ExcludedModeDiagnostic:
    """An experimental mode excluded by the strict pairing although its best FE MAC reaches 0.80 (D-076)."""

    experimental_mode: int
    experimental_hz: float
    best_fe_mode: int
    fe_hz: Optional[float]
    mac: float
    signed_relative_difference: float  # f_FE / f_EXP − 1
    family: Optional[str]
    exclusion_reason: str

    def to_dict(self) -> dict:
        return {"experimental_mode": self.experimental_mode, "experimental_hz": self.experimental_hz,
                "best_fe_mode": self.best_fe_mode, "fe_hz": self.fe_hz, "mac": self.mac,
                "signed_relative_difference": self.signed_relative_difference, "family": self.family,
                "exclusion_reason": self.exclusion_reason, "role": DIAGNOSTIC_ONLY,
                "enters": "nothing: never fitted, never in the objective, Birge, LOO or the calibration value"}


@dataclass(frozen=True)
class ExcludedDiagnosticsEvidence:
    """The complete excluded high-MAC diagnostics of the specimen (possibly an explicit empty list)."""

    records: tuple[ExcludedModeDiagnostic, ...]
    provenance: str
    complete: bool  # True only when the governed diagnostic evaluation ran (an empty list is then a result)

    @classmethod
    def from_campaign_rows(cls, rows: Sequence[Mapping], provenance: str) -> "ExcludedDiagnosticsEvidence":
        """From ``campaign_diagnostics.excluded_mode_diagnostics`` rows (the governed D-076 evaluation)."""
        return cls(tuple(ExcludedModeDiagnostic(
            int(r["experimental_mode"]), float(r["experimental_hz"]), int(r["best_fe_mode"]),
            None if r.get("fe_hz") is None else float(r["fe_hz"]), float(r["mac"]),
            float(r["signed_frequency_error"]), r.get("fe_family"), str(r["exclusion_reason"])) for r in rows),
            provenance, True)


@dataclass(frozen=True)
class CalibrationOutputRecord:
    status: CalibrationOutputStatus
    identity: Mapping[str, object]
    tau_mf: float
    gate_record_hash: str
    parameterisation_id: str
    calibration_parameters: Optional[Mapping[str, Mapping[str, object]]]  # RELEASED only
    fixed_parameters: Mapping[str, Mapping[str, object]]
    diagnostic_optimizer_candidate: Optional[Mapping[str, object]]  # REFUSED only
    precision: Mapping[str, object]
    uncertainty_basis: Mapping[str, object]
    governed_rows: tuple[Mapping[str, object], ...]
    governed_terms: tuple[Mapping[str, object], ...]
    non_degradation: Mapping[str, object]
    excluded_diagnostics: Mapping[str, object]
    refusal_reasons: tuple[Mapping[str, str], ...]

    @property
    def released(self) -> bool:
        return self.status is CalibrationOutputStatus.RELEASED

    def to_dict(self) -> dict:
        record = {"schema": SCHEMA, "quantity": QUANTITY, "status": self.status.value,
                  "scientific_question": SPECIMEN_ENGINEERING_CALIBRATION, "identity": dict(self.identity),
                  "tau_mf": {"value": self.tau_mf, "role": TAU_MF_ROLE,
                             "note": "acceptance tolerance on |Δ ln f| only; never an uncertainty"},
                  "gate_record_hash": self.gate_record_hash, "parameterisation": self.parameterisation_id,
                  "fixed_parameters": {k: dict(v) for k, v in sorted(self.fixed_parameters.items())},
                  "precision": self.precision, "uncertainty_basis": self.uncertainty_basis,
                  "governed_rows": [dict(r) for r in self.governed_rows],
                  "governed_terms": [dict(t) for t in self.governed_terms],
                  "non_degradation": self.non_degradation, "excluded_diagnostics": self.excluded_diagnostics,
                  "refusal_reasons": [dict(r) for r in self.refusal_reasons]}
        if self.released:
            record["output_class"] = SPECIMEN_ENGINEERING_CALIBRATION
            record["labels"] = list(LABELS)
            record["calibration_parameters"] = {k: dict(v) for k, v in sorted(self.calibration_parameters.items())}
            record["notes"] = ["model-specific calibration of one physical specimen and one governed FE model "
                               "(SPEC v1.2 §1 B); not a material property; not transferable without validation",
                               "the material verdict is a separate question and is not changed by this record"]
        else:
            record["output_class"] = None
            record["labels"] = []
            record["diagnostic_optimizer_candidate"] = dict(self.diagnostic_optimizer_candidate)
            record["notes"] = ["no calibration value is released (SPEC v1.2 §6); the judged candidate is diagnostic "
                               "evidence only", "no automatic fallback to material identification (§1)"]
        return record

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


# ----------------------------------------------------------------------------- binding

def _fail(message: str):
    raise PracticalIdentifiabilityInputError(message)


def _identity(inputs: CalibrationGateInputs, specimen: CampaignSpecimenInput, run_identity: Mapping) -> dict:
    definition = inputs.definition
    if len(definition.specimens) != 1 or specimen.spec != definition.specimens[0]:
        _fail("the specimen input is not the calibration campaign's specimen.")
    manifest, frozen = specimen.model.manifest, specimen.frozen
    if manifest.model_input.sha256 != manifest.canonical["model_input"]["sha256"]:
        _fail("the INP SHA-256 differs from the forward-model manifest's pinned model input.")
    if manifest.registration_hash != manifest.canonical["registration"]["registration_hash"]:
        _fail("the registration identity differs from the forward-model manifest.")
    if manifest.registration_hash != frozen.identity.registration_hash:
        _fail("the forward model and the frozen observations use different registrations.")
    if manifest.forward_model_id != frozen.identity.forward_model_id:
        _fail("the frozen observations belong to another forward model.")
    if manifest.parameterisation.parameterisation_id != definition.parameterisation_id:
        _fail("the forward model's parameterisation differs from the campaign's.")
    if not isinstance(run_identity, Mapping) or run_identity.get("campaign_hash") != definition.campaign_hash:
        _fail("the run identity belongs to another campaign.")
    entries = run_identity.get("specimens")
    if not isinstance(entries, list) or len(entries) != 1:
        _fail("the run identity must describe exactly the one calibration specimen.")
    entry = entries[0]
    expected = {"label": specimen.label, "fixture_id": specimen.spec.fixture_id,
                "registration_hash": frozen.identity.registration_hash,
                "forward_model": {"forward_model_id": manifest.forward_model_id,
                                  "manifest_hash": manifest.manifest_hash},
                "passport_manifest_hash": specimen.model.passport.manifest_hash,
                "observation_hash": frozen.observation_hash}
    for key, value in expected.items():
        if entry.get(key) != value:
            _fail(f"the run identity's specimen {key} does not match the evidence.")
    passport = specimen.model.passport
    return {"specimen": {"label": specimen.label, "fixture_id": specimen.spec.fixture_id,
                         "physical_specimen_id": None if passport.physical_specimen_id is None
                         else str(passport.physical_specimen_id),
                         "design_id": str(passport.design_id), "family_id": str(passport.family_id)},
            "test_run_id": str(passport.test_run_id),
            "forward_model": {"forward_model_id": manifest.forward_model_id, "manifest_hash": manifest.manifest_hash,
                              "parameterisation": manifest.parameterisation.parameterisation_id,
                              "material_role": manifest.material_role,
                              "production_material_name": specimen.model.material_name},
            "inp_sha256": manifest.model_input.sha256, "registration_hash": manifest.registration_hash,
            "passport_manifest_hash": passport.manifest_hash, "observation_hash": frozen.observation_hash,
            "campaign_id": definition.campaign_id, "campaign_hash": definition.campaign_hash,
            "run_hash": canonical_hash(dict(run_identity))}


def _family_of(rows: Sequence[str], families: Mapping[str, str]) -> str:
    keys = sorted({families[r] for r in rows})
    return keys[0] if len(keys) == 1 else "+".join(keys)  # the M5.8 rule of residual_terms


def _rows(inputs: CalibrationGateInputs, specimen: CampaignSpecimenInput) -> tuple[list[dict], list[dict]]:
    """The governed physical-row table and the term table, bound to the specimen's frozen rows and roles."""
    frozen = {row.row_id: row for row in specimen.frozen.rows}
    roles = {row.row_id: row.role for row in specimen.spec.rows}
    term_of = {row: term for term, members in inputs.term_rows.items() for row in members}
    term_family = {**inputs.fit_families, **inputs.holdout_families}
    if set(term_of) != set(frozen):
        _fail(f"the governed rows {sorted(term_of)} are not the specimen's frozen rows {sorted(frozen)}.")
    for term, members in inputs.term_rows.items():
        role = "FIT" if term in inputs.fit_families else "HOLDOUT"
        if any(roles[m] != role for m in members):
            _fail(f"term {term}: its rows have another role in the campaign definition.")
        if term_family[term] != _family_of(members, specimen.families):
            _fail(f"term {term}: family {term_family[term]} is not the specimen's M4.3 family of its rows.")
    for row, mac in inputs.baseline_pair_macs.items():
        if mac != frozen[row].mac:
            _fail(f"row {row}: the baseline pair MAC differs from the frozen pairing.")
    candidate = {r.row_id: float(r.delta_ln_f) for r in inputs.candidate_rows}
    baseline = {r.row_id: float(r.delta_ln_f) for r in inputs.baseline_rows}
    table = []
    for row_id in [r.row_id for r in specimen.frozen.rows]:
        term = term_of[row_id]
        members = inputs.term_rows[term]
        observed = frozen[row_id]
        delta = candidate.get(row_id)
        table.append({
            "row_id": row_id, "role": roles[row_id], "family": specimen.families[row_id], "term_id": term,
            "cluster_members": list(members) if len(members) > 1 else None,
            "experimental_mode": observed.experimental_mode, "experimental_hz": observed.experimental_hz,
            "baseline_fe_mode": observed.fe_mode, "baseline_fe_hz": observed.fe_hz,
            "candidate_delta_ln_f": delta,
            "candidate_relative_frequency_error": None if delta is None else math.expm1(delta),
            "baseline_delta_ln_f": baseline.get(row_id),
            "baseline_pair_mac": inputs.baseline_pair_macs.get(row_id) if roles[row_id] == "FIT" else None,
            "tracking_mac": inputs.tracking_macs.get(row_id)})
    terms = [{"term_id": t.term_id, "role": t.role, "family": term_family[t.term_id],
              "rows": list(inputs.term_rows[t.term_id]), "candidate_delta_ln_f": float(t.delta_ln_f),
              "evidence_level": "objective term (diagnostic; non-degradation is judged per row)"}
             for t in sorted(inputs.candidate_terms, key=lambda t: (t.role, t.term_id))]
    return table, terms


def _excluded(evidence: ExcludedDiagnosticsEvidence, specimen: CampaignSpecimenInput) -> dict:
    if not isinstance(evidence, ExcludedDiagnosticsEvidence) or not evidence.provenance.strip():
        _fail("excluded high-MAC diagnostics need an explicit evidence record with provenance.")
    governed_modes = {row.experimental_mode for row in specimen.frozen.rows}
    fitted = sorted(r.experimental_mode for r in evidence.records if r.experimental_mode in governed_modes)
    if fitted:
        _fail(f"excluded diagnostic modes {fitted} are governed rows: diagnostics never enter the fit.")
    return {"complete": evidence.complete, "provenance": evidence.provenance, "role": DIAGNOSTIC_ONLY,
            "records": [r.to_dict() for r in sorted(evidence.records, key=lambda r: r.experimental_mode)]}


def _reporting(gate, table: Sequence[Mapping], excluded: Mapping) -> None:
    """The gate's reporting-completeness claims must be backed by the evidence actually carried here."""
    claims = gate.reporting_completeness or {}
    actual = {"fit_residuals": any(r["role"] == "FIT" and r["candidate_delta_ln_f"] is not None for r in table),
              "holdout_residuals": any(r["role"] == "HOLDOUT" and r["candidate_delta_ln_f"] is not None
                                       for r in table),
              "excluded_high_mac_modes": bool(excluded["complete"]),
              "uncertainty_basis": gate.uncertainty_basis is not None}
    for key, present in actual.items():
        if claims.get(key) is True and not present:
            _fail(f"reporting completeness claims {key}, but the output carries no such evidence.")
    if gate.passed and not all(actual.values()):
        absent = sorted(k for k, v in actual.items() if not v)
        _fail(f"a calibration cannot be released with incomplete reporting {absent}.")


def build_calibration_output(inputs: CalibrationGateInputs, specimen: CampaignSpecimenInput, run_identity: Mapping,
                             excluded: ExcludedDiagnosticsEvidence,
                             expected_gate_record_hash: Optional[str] = None) -> CalibrationOutputRecord:
    """V12-I4: evaluate the I3 gate on ``inputs`` and build the calibration output record. Pure; writes nothing."""

    if not isinstance(inputs, CalibrationGateInputs) or not isinstance(specimen, CampaignSpecimenInput):
        raise TypeError("the output builder consumes CalibrationGateInputs and the CampaignSpecimenInput it describes.")
    definition = inputs.definition
    if definition.scientific_question != SPECIMEN_ENGINEERING_CALIBRATION or definition.tau_mf is None:
        _fail("only a v1.2 SPECIMEN_ENGINEERING_CALIBRATION campaign with a declared τ_mf has a calibration output.")
    gate = evaluate_calibration_gate(inputs)  # the same evidence bundle; never a gate record from elsewhere
    if expected_gate_record_hash is not None and expected_gate_record_hash != gate.record_hash:
        _fail("the gate record under review is not the gate of this evidence bundle.")
    identity = _identity(inputs, specimen, run_identity)
    identity["tau_mf"] = definition.tau_mf
    identity["gate_record_hash"] = gate.record_hash
    # The gate record carries no value by design; the judged candidate and evidence are bound here by hash.
    identity["evidence_binding"] = {
        "p_hat_hash": canonical_hash({k: float(v) for k, v in sorted(inputs.p_hat.items())}),
        **{f"{name}_record_hash": None if record is None else record.record_hash
           for name, record in (("analysis", inputs.analysis), ("statistical_sd", inputs.statistical),
                                ("pattern", inputs.pattern), ("birge", inputs.birge),
                                ("model_form_robustness", inputs.robustness))}}
    table, terms = _rows(inputs, specimen)
    excluded_record = _excluded(excluded, specimen)
    _reporting(gate, table, excluded_record)
    fixed = {name: {"value": float(value), "unit": PARAMETER_UNITS.get(name), "role": "FIXED_BY_CAMPAIGN_DEFINITION",
                    "provenance": f"campaign definition {definition.campaign_id} (identity-bound)"}
             for name, value in definition.fixed_parameters.items()}
    candidate = {name: float(inputs.p_hat[name]) for name in definition.fitted_parameters}
    for name in candidate:
        if name not in PARAMETER_UNITS:
            _fail(f"no governed unit for calibration parameter {name}.")
    common = dict(identity=identity, tau_mf=definition.tau_mf, gate_record_hash=gate.record_hash,
                  parameterisation_id=definition.parameterisation_id, fixed_parameters=fixed,
                  precision=gate.precision, uncertainty_basis=gate.uncertainty_basis, governed_rows=tuple(table),
                  governed_terms=tuple(terms), non_degradation=gate.non_degradation,
                  excluded_diagnostics=excluded_record, refusal_reasons=gate.refusal_reasons)
    if gate.passed:
        parameters = {name: {"value": value, "unit": PARAMETER_UNITS[name], "role": PARAMETER_ROLE}
                      for name, value in candidate.items()}
        return CalibrationOutputRecord(CalibrationOutputStatus.RELEASED, calibration_parameters=parameters,
                                       diagnostic_optimizer_candidate=None, **common)
    diagnostic = {"labels": list(CANDIDATE_LABELS),
                  "parameters": {name: {"value": value, "unit": PARAMETER_UNITS[name]}
                                 for name, value in candidate.items()}}
    return CalibrationOutputRecord(CalibrationOutputStatus.REFUSED, calibration_parameters=None,
                                   diagnostic_optimizer_candidate=diagnostic, **common)


# ----------------------------------------------------------------------------- separate calibration INP fragment

@dataclass(frozen=True)
class GovernedConstant:
    value: float
    provenance: str


@dataclass(frozen=True)
class CalibrationInpFragment:
    """A complete calibration material cloned from the pinned source INP; text only (nothing is written)."""

    material_name: str
    source_calibration_record_hash: str
    gate_record_hash: str
    source_inp_sha256: str
    source_material_name: str
    source_material_block_sha256: str
    content: str

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("latin-1")).hexdigest()


# Abaqus material options outside the supported set: a material block that ends on one of them would be cloned
# incompletely, so no fragment is produced (the supported set is the forward builder's).
_UNSUPPORTED_MATERIAL_OPTIONS = frozenset({
    "plastic", "hyperelastic", "hyperfoam", "viscoelastic", "user material", "depvar", "creep", "damage initiation",
    "damage evolution", "permeability", "piezoelectric", "dielectric", "electrical conductivity", "latent heat",
    "joule heat fraction", "swelling", "moisture swelling", "hysteresis", "mullins effect", "viscous",
    "anisotropic hyperelastic", "concrete damaged plasticity", "brittle cracking", "porous bulk moduli",
    "user defined field", "regularize", "low density foam"})
_NAME = re.compile(r"(?i)(\bname\s*=\s*)(\"?)([^,\"\r\n]+)(\"?)")


def governed_engineering_constants(record: CalibrationOutputRecord) -> dict[str, GovernedConstant]:
    """The nine constants of a RELEASED record from the governed parameterisation (no constant is invented)."""
    if not isinstance(record, CalibrationOutputRecord) or not record.released:
        raise CalibrationFragmentRefusal("only a RELEASED specimen-engineering-calibration record has constants.")
    parameterisation = PARAMETERISATIONS.get(record.parameterisation_id)
    if parameterisation is None:
        raise CalibrationFragmentRefusal(f"unknown parameterisation {record.parameterisation_id}.")
    values = {name: item["value"] for name, item in record.calibration_parameters.items()}
    values.update({name: item["value"] for name, item in record.fixed_parameters.items()})
    unsupported = sorted(set(record.calibration_parameters) - set(parameterisation.parameters))
    if unsupported or set(values) != set(parameterisation.parameters):
        raise CalibrationFragmentRefusal(f"calibration parameters {unsupported or sorted(values)} do not match "
                                         f"{parameterisation.parameterisation_id}.")
    constants = parameterisation.engineering_constants(values).to_dict()
    source = {}
    for parameter, targets in parameterisation.parameter_targets.items():
        origin = ("released calibration parameter" if parameter in record.calibration_parameters
                  else "campaign definition fixed parameter")
        for name in targets:
            source[name] = f"{origin} {parameter}"
    for name in parameterisation.fixed_constants:
        source[name] = f"{parameterisation.parameterisation_id} fixed constant (SPEC §5.2)"
    return {name: GovernedConstant(constants[name], source[name]) for name in EngineeringConstants.names()}


def calibration_material_name(record: CalibrationOutputRecord) -> str:
    label = re.sub(r"[^A-Za-z0-9_]", "_", str(record.identity["specimen"]["label"]))
    name = f"CAL_{label}_{record.record_hash[:12]}"[:80]
    if not _MATERIAL_NAME.match(name):
        raise CalibrationFragmentRefusal(f"cannot form a valid Abaqus material name from {label!r}.")
    if name.lower() == str(record.identity["forward_model"]["production_material_name"]).lower():
        raise CalibrationFragmentRefusal("the calibration material name equals the production material name.")
    return name


def _comment(text: object) -> str:
    return re.sub(r"[^\x20-\x7e]", "?", str(text))  # ASCII comment text only


def _clone_material(record: CalibrationOutputRecord, source_inp_bytes: bytes, material: str,
                    calibrated: EngineeringConstants) -> tuple[list[str], str]:
    """The complete governed production material block of the pinned source INP, renamed, with only its Engineering
    Constants set to the calibration constants (the forward builder's parsing and record-writing semantics)."""
    if not isinstance(source_inp_bytes, (bytes, bytearray)):
        raise CalibrationFragmentRefusal("the exact pinned source INP bytes are required.")
    source = bytes(source_inp_bytes)
    if hashlib.sha256(source).hexdigest() != record.identity["inp_sha256"]:
        raise CalibrationFragmentRefusal("the source INP is not the pinned INP of the calibration (SHA-256 differs).")
    production = str(record.identity["forward_model"]["production_material_name"])
    lines = split_inp_lines(source)
    try:
        start, end = material_block_bounds(lines, production)
        located = locate_engineering_constants(lines, production)
    except ForwardBuildError as exc:
        raise CalibrationFragmentRefusal(f"the governed source material cannot be cloned: {exc}") from exc
    if end < len(lines) and inp_keyword(lines[end]) in _UNSUPPORTED_MATERIAL_OPTIONS:
        raise CalibrationFragmentRefusal(f"material {production!r} carries the unsupported option "
                                         f"*{inp_keyword(lines[end])}; a complete clone is not possible.")
    while end > start + 1 and (lines[end - 1].startswith("**") or not lines[end - 1].strip()):
        end -= 1  # trailing comments belong to what follows, not to the material
    block_sha256 = hashlib.sha256("".join(lines[start:end]).encode("latin-1")).hexdigest()
    block = list(lines[start:end])
    names = list(_NAME.finditer(block[0]))
    if len(names) != 1 or names[0].group(3).strip().lower() != production.lower():
        raise CalibrationFragmentRefusal(f"the *Material line of {production!r} cannot be renamed unambiguously.")
    match = names[0]
    block[0] = block[0][:match.start(3)] + material + block[0][match.end(3):]
    relocated = replace(located, material_line=0, elastic_line=located.elastic_line - start,
                        data_lines=tuple(i - start for i in located.data_lines))
    try:  # fixed constants must equal the source; only the parameterisation's variable constants are written
        rewrite_engineering_constants(block, relocated, calibrated,
                                      PARAMETERISATIONS[record.parameterisation_id].variable_constants)
    except ForwardBuildError as exc:
        raise CalibrationFragmentRefusal(f"the source Engineering Constants are not the governed set: {exc}") from exc
    return [line.rstrip("\r\n") for line in block], block_sha256


def render_calibration_inp_fragment(record: CalibrationOutputRecord, constants: Mapping[str, GovernedConstant],
                                    source_inp_bytes: bytes) -> CalibrationInpFragment:
    """A distinct calibration material for a RELEASED record: the complete governed production material block of the
    pinned source INP (density, damping and every other supported option unchanged) under a CAL_* name, with only
    the nine Engineering Constants set to the governed calibration constants.

    Abaqus Keywords Reference, *ELASTIC, TYPE=ENGINEERING CONSTANTS: E1, E2, E3, ν12, ν13, ν23, G12, G13 on the first
    data line, G23 on the second; the source record layout is kept. Pure: the caller supplies the exact source INP
    bytes (verified against the record's INP SHA-256); nothing is read, written or executed.
    """
    if not isinstance(record, CalibrationOutputRecord) or not record.released:
        raise CalibrationFragmentRefusal("a calibration INP fragment needs a RELEASED calibration record.")
    governed = governed_engineering_constants(record)
    names = EngineeringConstants.names()
    missing, extra = sorted(set(names) - set(constants)), sorted(set(constants) - set(names))
    if missing or extra:
        raise CalibrationFragmentRefusal(f"incomplete Engineering Constants: missing {missing}, unexpected {extra}.")
    for name in names:
        item = constants[name]
        if not isinstance(item, GovernedConstant) or not item.provenance.strip():
            raise CalibrationFragmentRefusal(f"{name}: a governed constant with provenance is required.")
        if isinstance(item.value, bool) or not isinstance(item.value, (int, float)) or not math.isfinite(item.value) \
                or float(item.value) != governed[name].value:
            raise CalibrationFragmentRefusal(
                f"{name} = {item.value!r} is not the governed value {governed[name].value!r}.")
    material = calibration_material_name(record)
    identity = record.identity
    calibrated = EngineeringConstants(**{name: float(constants[name].value) for name in names})
    block, block_sha256 = _clone_material(record, source_inp_bytes, material, calibrated)
    production = _comment(identity["forward_model"]["production_material_name"])
    lines = [
        "** " + "-" * 76,
        "** SPECIMEN_ENGINEERING_CALIBRATION",
        "** NOT_A_MATERIAL_PROPERTY",
        "** NOT_TRANSFERABLE_WITHOUT_VALIDATION",
        "** Model-specific calibration of one physical specimen and one governed FE model (SPEC v1.2 1B, 9).",
        f"** specimen: {_comment(identity['specimen']['label'])}",
        f"** fixture: {_comment(identity['specimen']['fixture_id'])}",
        f"** test run: {_comment(identity['test_run_id'])}",
        f"** forward model: {_comment(identity['forward_model']['forward_model_id'])}",
        f"** forward-model manifest sha256: {identity['forward_model']['manifest_hash']}",
        f"** inp sha256: {identity['inp_sha256']}",
        f"** campaign hash: {identity['campaign_hash']}",
        f"** run hash: {identity['run_hash']}",
        f"** gate record hash: {record.gate_record_hash}",
        f"** calibration record hash: {record.record_hash}",
        f"** calibration material: {material}",
        f"** Complete governed source material block of {production} cloned from the pinned source INP",
        f"** (source material block sha256: {block_sha256}).",
        "** Only the material name and the governed Engineering Constants were changed; the production",
        f"** material {production} is not changed (this is a separate material).",
        "** " + "-" * 76,
        *block,
    ]
    return CalibrationInpFragment(material, record.record_hash, record.gate_record_hash, identity["inp_sha256"],
                                  str(identity["forward_model"]["production_material_name"]), block_sha256,
                                  "\n".join(lines) + "\n")
