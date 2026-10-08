"""Multi-specimen identification campaign definition — Auto-ID M7 (SPEC §5, §7, §8, §12.3, §13; D-069).

A campaign fits one shared carbon in-plane vector to several specimens.  Each specimen keeps its own
active physical chain (fixture, registration, forward model), its own frozen observation rows and its
own holdouts; only the FIT residuals are stacked into the campaign vector, after branch tracking.

The definition is data (schema ``auto-id/identification-campaign/v1``), parsed strictly:

- ``run_type`` ``RUN_A`` (the executable campaign) or ``RUN_B`` (diagnostic
  ``EFFECTIVE_MODEL_COMPENSATION_TEST``; never executable without its own later SUPERVISOR gate);
- the fitted parameters are a subset of the parameterisation; every other parameter is fixed explicitly;
- Σ is explicit: Σ_setup with its status, and Σ_meas as ``NOT_AVAILABLE`` (never a zero value);
- numerical search bounds (solver only) and an engineering plausibility window (reporting only);
- an LM evaluation budget and a hard Abaqus solve budget.

Nothing here runs a solve.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Mapping, Optional

from .forward_model_manifest import PARAMETERISATIONS, canonical_hash


CAMPAIGN_SCHEMA = "auto-id/identification-campaign/v1"
ARCHIVE_REUSE_SCHEMA = "auto-id/campaign-archive-reuse/v1"
RUN_A = "RUN_A"
RUN_B = "RUN_B"
RUN_TYPES = (RUN_A, RUN_B)
RUN_B_LABEL = "EFFECTIVE_MODEL_COMPENSATION_TEST"
ROW_ROLES = ("FIT", "HOLDOUT")
SIGMA_STATUSES = ("PROVISIONAL", "MEASURED")
NOT_AVAILABLE = "NOT_AVAILABLE"
EFFECTIVE_ESTIMATE = "EFFECTIVE_MODEL_PARAMETER_ESTIMATE"
NO_EFFECTIVE_ESTIMATE = "NO_EFFECTIVE_ESTIMATE"
IDENTIFIED_MATERIAL_PROPERTY = "IDENTIFIED_MATERIAL_PROPERTY"
NO_MATERIAL_CLAIM = "NO_MATERIAL_PROPERTY_CLAIM"
NOT_EXTERNALLY_VALIDATED = "not externally validated"  # D-060: on every real carbon result

_TOP_KEYS = {"schema", "campaign_id", "run_type", "decision", "parameterisation", "fitted_parameters",
             "fixed_parameters", "start", "bounds", "engineering_plausibility", "practical_target", "sigma", "lm",
             "abaqus_solve_budget", "not_fitted", "specimens", "archive_reuse", "run_b_gate", "provenance"}
_SPECIMEN_KEYS = {"label", "fixture_id", "forward_model", "solver_profile", "baseline_shape_pack",
                  "archived_baseline", "registration_evidence", "rows"}
_LM_KEYS = {"mu_initial", "mu_decrease", "max_step_attempts", "evaluation_budget", "max_iterations",
            "stop_fraction", "mu_increase", "finite_difference_step"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+-]*$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class CampaignDefinitionError(ValueError):
    """A campaign definition is malformed or not authorised; nothing is guessed."""


class RunGateRefusal(Exception):
    """The run type is not authorised for execution (RUN_B without its own SUPERVISOR gate).

    Not a ValueError, so generic fallback handlers never swallow it.
    """


def _fail(field: str, message: str):
    raise CampaignDefinitionError(f"{field}: {message}")


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


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(field, "must be a positive integer.")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH.match(value):
        _fail(field, "must be a 64-character lowercase hex SHA-256.")
    return value


@dataclass(frozen=True)
class SigmaState:
    """Σ = Σ_meas + Σ_setup (SPEC §7), explicit.  Σ_meas NOT_AVAILABLE has no numeric value at all."""

    setup_sd_ln: float
    setup_status: str  # PROVISIONAL | MEASURED
    setup_source: str
    measurement_status: str  # NOT_AVAILABLE (real PolyMAX data give no modal uncertainty)
    measurement_source: str

    @property
    def setup_provisional(self) -> bool:
        return self.setup_status == "PROVISIONAL"

    @property
    def measurement_available(self) -> bool:
        return self.measurement_status != NOT_AVAILABLE

    def measurement_sd_ln(self) -> float:
        raise CampaignDefinitionError("Σ_meas is NOT_AVAILABLE: it has no value and is never taken as zero.")

    def to_dict(self) -> dict:
        return {"setup": {"sd_ln": self.setup_sd_ln, "status": self.setup_status, "source": self.setup_source},
                "measurement": {"status": self.measurement_status, "source": self.measurement_source}}


@dataclass(frozen=True)
class CampaignRow:
    row_id: str
    experimental_mode: int
    fe_mode: int
    role: str  # FIT | HOLDOUT


@dataclass(frozen=True)
class CampaignSpecimen:
    label: str
    fixture_id: str
    forward_model: str
    solver_profile: str
    baseline_shape_pack: str
    archived_baseline: str
    registration_evidence: str  # M2.4 record carrying registration_limited
    rows: tuple[CampaignRow, ...]

    @property
    def fit_rows(self) -> tuple[str, ...]:
        return tuple(r.row_id for r in self.rows if r.role == "FIT")

    @property
    def holdout_rows(self) -> tuple[str, ...]:
        return tuple(r.row_id for r in self.rows if r.role == "HOLDOUT")

    def term_id(self, row_id: str) -> str:
        return f"{self.label}:{row_id}"


@dataclass(frozen=True)
class LMConfiguration:
    mu_initial: float
    mu_decrease: float
    max_step_attempts: int
    evaluation_budget: int  # LM evaluations (reused and new); each new evaluation solves every specimen once
    max_iterations: int
    stop_fraction: float
    mu_increase: float
    finite_difference_step: float


@dataclass(frozen=True)
class CampaignDefinition:
    campaign_id: str
    run_type: str
    decision: str
    parameterisation_id: str
    fitted_parameters: tuple[str, ...]
    fixed_parameters: Mapping[str, float]
    start: Mapping[str, float]
    bounds: Mapping[str, tuple[float, float]]  # numerical search bounds (solver only)
    engineering_plausibility: Mapping[str, tuple[float, float]]  # reporting context only; never a prior
    preferred_max_abs_relative_error: float
    acceptable_max_abs_relative_error: float
    sigma: SigmaState
    lm: LMConfiguration
    abaqus_solve_budget: int
    not_fitted: Mapping[str, str]
    specimens: tuple[CampaignSpecimen, ...]
    archive_reuse: str
    run_b_gate: Optional[str]
    provenance: tuple[str, ...]
    canonical: Mapping[str, Any]

    @property
    def campaign_hash(self) -> str:
        return canonical_hash(self.canonical)

    def full_parameters(self, fitted: Mapping[str, float]) -> dict[str, float]:
        """The parameterisation's candidate: the fitted values plus the explicit fixed values."""
        if set(fitted) != set(self.fitted_parameters):
            raise CampaignDefinitionError(f"a campaign candidate sets exactly {self.fitted_parameters}.")
        values = {**{k: float(v) for k, v in fitted.items()}, **dict(self.fixed_parameters)}
        return {name: values[name] for name in PARAMETERISATIONS[self.parameterisation_id].parameters}

    def fit_term_ids(self) -> tuple[str, ...]:
        """Campaign FIT vector order: specimens in definition order, rows in frozen order."""
        return tuple(s.term_id(r) for s in self.specimens for r in s.fit_rows)

    def holdout_term_ids(self) -> tuple[str, ...]:
        return tuple(s.term_id(r) for s in self.specimens for r in s.holdout_rows)

    def require_executable(self) -> "CampaignDefinition":
        if self.run_type == RUN_B and not self.run_b_gate:
            raise RunGateRefusal(f"{RUN_B} ({RUN_B_LABEL}) is diagnostic only and needs its own later SUPERVISOR "
                                 "gate after RUN_A; it is not executable.")
        return self

    def specimen(self, label: str) -> CampaignSpecimen:
        for item in self.specimens:
            if item.label == label:
                return item
        raise CampaignDefinitionError(f"no campaign specimen {label!r}.")


def _pair(value: object, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        _fail(field, "must be [lower, upper].")
    low, high = _positive(value[0], f"{field}[0]"), _positive(value[1], f"{field}[1]")
    if not low < high:
        _fail(field, "needs lower < upper.")
    return low, high


def _rows(value: object, field: str) -> tuple[CampaignRow, ...]:
    if not isinstance(value, list) or not value:
        _fail(field, "must be a non-empty list.")
    rows = []
    for index, item in enumerate(value):
        data = _mapping(item, f"{field}[{index}]", {"row_id", "experimental_mode", "fe_mode", "role"})
        if data["role"] not in ROW_ROLES:
            _fail(f"{field}[{index}].role", f"must be one of {ROW_ROLES}.")
        rows.append(CampaignRow(_text(data["row_id"], f"{field}[{index}].row_id"),
                                _count(data["experimental_mode"], f"{field}[{index}].experimental_mode"),
                                _count(data["fe_mode"], f"{field}[{index}].fe_mode"), data["role"]))
    for name in ("row_id", "experimental_mode", "fe_mode"):
        if len({getattr(r, name) for r in rows}) != len(rows):
            _fail(field, f"{name} values must be unique within a specimen.")
    if not any(r.role == "FIT" for r in rows):
        _fail(field, "a specimen needs at least one FIT row.")
    return tuple(rows)


def parse_campaign_definition(data: object) -> CampaignDefinition:
    data = _mapping(data, "campaign", _TOP_KEYS)
    if data["schema"] != CAMPAIGN_SCHEMA:
        _fail("schema", f"must be {CAMPAIGN_SCHEMA!r}.")
    campaign_id = _text(data["campaign_id"], "campaign_id")
    if not _IDENTIFIER.match(campaign_id):
        _fail("campaign_id", "must use letters, digits, '.', '_', '-', '+' or '/'.")
    run_type = data["run_type"]
    if run_type not in RUN_TYPES:
        _fail("run_type", f"must be one of {RUN_TYPES}.")
    decision = _text(data["decision"], "decision")

    parameterisation_id = data["parameterisation"]
    if parameterisation_id not in PARAMETERISATIONS:
        _fail("parameterisation", f"unknown parameterisation {parameterisation_id!r}.")
    parameters = PARAMETERISATIONS[parameterisation_id].parameters
    fitted = data["fitted_parameters"]
    if not isinstance(fitted, list) or not fitted or len(set(fitted)) != len(fitted) or not set(fitted) <= set(parameters):
        _fail("fitted_parameters", f"must be a non-empty list of distinct parameters of {parameterisation_id}.")
    fitted = tuple(name for name in parameters if name in fitted)  # parameterisation order
    fixed = data["fixed_parameters"]
    if not isinstance(fixed, Mapping) or set(fixed) != set(parameters) - set(fitted):
        _fail("fixed_parameters", f"must fix exactly {sorted(set(parameters) - set(fitted))}.")
    fixed = {name: _positive(fixed[name], f"fixed_parameters.{name}") for name in parameters if name in fixed}
    if run_type == RUN_A and fitted != ("E_in_plane_mpa",):
        _fail("fitted_parameters", "RUN_A fits E_in_plane_mpa only (G12 fixed; D-069).")
    if run_type == RUN_B and fitted != ("E_in_plane_mpa", "G12_mpa"):
        _fail("fitted_parameters", f"RUN_B ({RUN_B_LABEL}) fits E_in_plane_mpa and G12_mpa.")

    start = data["start"]
    if not isinstance(start, Mapping) or set(start) != set(fitted):
        _fail("start", f"must give exactly {fitted}.")
    start = {name: _positive(start[name], f"start.{name}") for name in fitted}
    bounds_data = data["bounds"]
    if not isinstance(bounds_data, Mapping) or set(bounds_data) != set(fitted):
        _fail("bounds", f"must bound exactly {fitted}.")
    bounds = {name: _pair(bounds_data[name], f"bounds.{name}") for name in fitted}
    for name in fitted:
        if not bounds[name][0] <= start[name] <= bounds[name][1]:
            _fail(f"start.{name}", "lies outside the search bounds.")
    plausibility = data["engineering_plausibility"]
    if not isinstance(plausibility, Mapping) or not set(plausibility) <= set(fitted):
        _fail("engineering_plausibility", "may only describe fitted parameters.")
    plausibility = {name: _pair(plausibility[name], f"engineering_plausibility.{name}") for name in plausibility}

    target = _mapping(data["practical_target"], "practical_target", {"preferred_max_abs_relative_error",
                                                                     "acceptable_max_abs_relative_error", "note"})
    preferred = _positive(target["preferred_max_abs_relative_error"], "practical_target.preferred")
    acceptable = _positive(target["acceptable_max_abs_relative_error"], "practical_target.acceptable")
    if not preferred <= acceptable < 1.0:
        _fail("practical_target", "needs preferred ≤ acceptable < 1.")
    _text(target["note"], "practical_target.note")

    sigma = _mapping(data["sigma"], "sigma", {"setup", "measurement"})
    setup = _mapping(sigma["setup"], "sigma.setup", {"sd_ln", "status", "source"})
    measurement = _mapping(sigma["measurement"], "sigma.measurement", {"status", "source"})
    if setup["status"] not in SIGMA_STATUSES:
        _fail("sigma.setup.status", f"must be one of {SIGMA_STATUSES}.")
    if measurement["status"] != NOT_AVAILABLE:
        _fail("sigma.measurement.status", "only NOT_AVAILABLE is supported: no real Σ_meas exists (D-069).")
    sigma_state = SigmaState(_positive(setup["sd_ln"], "sigma.setup.sd_ln"), setup["status"],
                             _text(setup["source"], "sigma.setup.source"), NOT_AVAILABLE,
                             _text(measurement["source"], "sigma.measurement.source"))

    lm = _mapping(data["lm"], "lm", _LM_KEYS)
    lm_config = LMConfiguration(_positive(lm["mu_initial"], "lm.mu_initial"),
                                _positive(lm["mu_decrease"], "lm.mu_decrease"),
                                _count(lm["max_step_attempts"], "lm.max_step_attempts"),
                                _count(lm["evaluation_budget"], "lm.evaluation_budget"),
                                _count(lm["max_iterations"], "lm.max_iterations"),
                                _positive(lm["stop_fraction"], "lm.stop_fraction"),
                                _positive(lm["mu_increase"], "lm.mu_increase"),
                                _positive(lm["finite_difference_step"], "lm.finite_difference_step"))
    solve_budget = _count(data["abaqus_solve_budget"], "abaqus_solve_budget")

    not_fitted = data["not_fitted"]
    if not isinstance(not_fitted, Mapping) or set(not_fitted) != {"t_face", "k_core", "k_int"}:
        _fail("not_fitted", "must state t_face, k_core and k_int explicitly.")
    not_fitted = {k: _text(v, f"not_fitted.{k}") for k, v in sorted(not_fitted.items())}

    if not isinstance(data["specimens"], list) or len(data["specimens"]) < 2:
        _fail("specimens", "a campaign needs at least two specimens.")
    specimens = []
    for index, item in enumerate(data["specimens"]):
        field = f"specimens[{index}]"
        entry = _mapping(item, field, _SPECIMEN_KEYS)
        specimens.append(CampaignSpecimen(
            _text(entry["label"], f"{field}.label"), _text(entry["fixture_id"], f"{field}.fixture_id"),
            *(_repo_path(entry[k], f"{field}.{k}") for k in ("forward_model", "solver_profile", "baseline_shape_pack",
                                                             "archived_baseline", "registration_evidence")),
            _rows(entry["rows"], f"{field}.rows")))
    if len({s.label for s in specimens}) != len(specimens) or len({s.fixture_id for s in specimens}) != len(specimens):
        _fail("specimens", "labels and fixtures must be unique.")
    fit_terms = sum(len(s.fit_rows) for s in specimens)
    if fit_terms < len(fitted):
        _fail("specimens", f"{fit_terms} campaign FIT rows < {len(fitted)} fitted parameters.")

    run_b_gate = data["run_b_gate"]
    if run_b_gate is not None:
        run_b_gate = _text(run_b_gate, "run_b_gate")
    if run_type == RUN_A and run_b_gate is not None:
        _fail("run_b_gate", "a RUN_A definition carries no RUN_B gate.")
    archive_reuse = _repo_path(data["archive_reuse"], "archive_reuse")
    provenance = data["provenance"]
    if not isinstance(provenance, list) or not provenance:
        _fail("provenance", "must be a non-empty list.")
    provenance = tuple(_text(p, "provenance[]") for p in provenance)

    canonical = {
        "schema": CAMPAIGN_SCHEMA, "campaign_id": campaign_id, "run_type": run_type, "decision": decision,
        "parameterisation": parameterisation_id, "fitted_parameters": list(fitted), "fixed_parameters": fixed,
        "start": start, "bounds": {k: list(v) for k, v in bounds.items()},
        "engineering_plausibility": {k: list(v) for k, v in plausibility.items()},
        "practical_target": {"preferred_max_abs_relative_error": preferred,
                             "acceptable_max_abs_relative_error": acceptable, "note": target["note"]},
        "sigma": sigma_state.to_dict(),
        "lm": {k: getattr(lm_config, k) for k in sorted(_LM_KEYS)}, "abaqus_solve_budget": solve_budget,
        "not_fitted": not_fitted,
        "specimens": [{"label": s.label, "fixture_id": s.fixture_id, "forward_model": s.forward_model,
                       "solver_profile": s.solver_profile, "baseline_shape_pack": s.baseline_shape_pack,
                       "archived_baseline": s.archived_baseline, "registration_evidence": s.registration_evidence,
                       "rows": [{"row_id": r.row_id, "experimental_mode": r.experimental_mode, "fe_mode": r.fe_mode,
                                 "role": r.role} for r in s.rows]} for s in specimens],
        "archive_reuse": archive_reuse, "run_b_gate": run_b_gate, "provenance": list(provenance),
    }
    return CampaignDefinition(campaign_id, run_type, decision, parameterisation_id, fitted, fixed, start, bounds,
                              plausibility, preferred, acceptable, sigma_state, lm_config, solve_budget, not_fitted,
                              tuple(specimens), archive_reuse, run_b_gate, provenance, canonical)


def load_campaign_definition(path) -> CampaignDefinition:
    with open(path, encoding="utf-8") as handle:
        return parse_campaign_definition(json.load(handle))


# ----------------------------------------------------------------------------- archived-result reuse

@dataclass(frozen=True)
class ArchivedPackReuse:
    """A validated, governed shape pack reused for one planned job (no solve, no extraction)."""

    specimen: str
    point: Mapping[str, float]  # the full parameterisation candidate
    job_name: str
    generated_inp_sha256: str
    shape_pack_record: str  # repository path


@dataclass(frozen=True)
class ArchivedOdbReuse:
    """An archived accepted ODB reused through an extraction-only job (Abaqus Python, HUMAN gate)."""

    specimen: str
    point: Mapping[str, float]
    job_name: str
    generated_inp_sha256: str
    odb_store: str
    odb_relative_path: str
    odb_sha256: str
    odb_size_bytes: int
    odb_pin_source: str
    status_files: Mapping[str, str]  # store-relative path → sha256 (.sta completion, .dat release, .msg)
    expected_mode_numbers: tuple[int, ...]
    expected_frequencies_hz: tuple[float, ...]  # the accepted archived frequencies; the pack must equal them
    frequency_source: str
    excluded_attempts: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class ArchiveReusePlan:
    packs: tuple[ArchivedPackReuse, ...]
    odbs: tuple[ArchivedOdbReuse, ...]
    canonical: Mapping[str, Any]

    @property
    def reuse_hash(self) -> str:
        return canonical_hash(self.canonical)


def _point(value: object, field: str, parameterisation_id: str) -> dict[str, float]:
    parameters = PARAMETERISATIONS[parameterisation_id].parameters
    if not isinstance(value, Mapping) or set(value) != set(parameters):
        _fail(field, f"must set exactly {parameters}.")
    return {name: _positive(value[name], f"{field}.{name}") for name in parameters}


def _job(entry: Mapping[str, Any], field: str) -> tuple[str, str]:
    sha = _sha(entry["generated_inp_sha256"], f"{field}.generated_inp_sha256")
    name = _text(entry["job_name"], f"{field}.job_name")
    if not name.endswith("_" + sha[:16]):
        _fail(f"{field}.job_name", "must be the content-addressed job name.")
    return name, sha


def parse_archive_reuse(data: object, parameterisation_id: str) -> ArchiveReusePlan:
    data = _mapping(data, "archive_reuse", {"schema", "packs", "odbs", "provenance"})
    if data["schema"] != ARCHIVE_REUSE_SCHEMA:
        _fail("schema", f"must be {ARCHIVE_REUSE_SCHEMA!r}.")
    packs = []
    for index, item in enumerate(data["packs"]):
        field = f"packs[{index}]"
        entry = _mapping(item, field, {"specimen", "point", "job_name", "generated_inp_sha256", "shape_pack_record"})
        name, sha = _job(entry, field)
        packs.append(ArchivedPackReuse(_text(entry["specimen"], f"{field}.specimen"),
                                       _point(entry["point"], f"{field}.point", parameterisation_id), name, sha,
                                       _repo_path(entry["shape_pack_record"], f"{field}.shape_pack_record")))
    odbs = []
    keys = {"specimen", "point", "job_name", "generated_inp_sha256", "odb", "status_files", "expected_frequencies",
            "excluded_attempts"}
    for index, item in enumerate(data["odbs"]):
        field = f"odbs[{index}]"
        entry = _mapping(item, field, keys)
        name, sha = _job(entry, field)
        odb = _mapping(entry["odb"], f"{field}.odb", {"store", "relative_path", "sha256", "size_bytes", "pin_source"})
        relative = _repo_path(odb["relative_path"], f"{field}.odb.relative_path")
        if not relative.endswith(f"/{name}.odb"):
            _fail(f"{field}.odb.relative_path", "must end with the job's ODB name.")
        status_files = entry["status_files"]
        if not isinstance(status_files, Mapping) or not status_files:
            _fail(f"{field}.status_files", "must pin the archived .sta / .dat / .msg files.")
        status_files = {_repo_path(k, f"{field}.status_files"): _sha(v, f"{field}.status_files[{k}]")
                        for k, v in sorted(status_files.items())}
        frequencies = _mapping(entry["expected_frequencies"], f"{field}.expected_frequencies",
                               {"mode_numbers", "frequencies_hz", "source"})
        modes = tuple(_count(m, f"{field}.mode_numbers[]") for m in frequencies["mode_numbers"])
        hz = tuple(_positive(f, f"{field}.frequencies_hz[]") for f in frequencies["frequencies_hz"])
        if len(modes) != len(hz) or not modes:
            _fail(f"{field}.expected_frequencies", "mode numbers and frequencies must match.")
        excluded = entry["excluded_attempts"]
        if not isinstance(excluded, list):
            _fail(f"{field}.excluded_attempts", "must be a list (possibly empty).")
        excluded = tuple({k: _text(v, f"{field}.excluded_attempts[].{k}") for k, v in
                          _mapping(e, f"{field}.excluded_attempts[]", {"relative_path", "reason"}).items()}
                         for e in excluded)
        odbs.append(ArchivedOdbReuse(_text(entry["specimen"], f"{field}.specimen"),
                                     _point(entry["point"], f"{field}.point", parameterisation_id), name, sha,
                                     _text(odb["store"], f"{field}.odb.store"), relative,
                                     _sha(odb["sha256"], f"{field}.odb.sha256"),
                                     _count(odb["size_bytes"], f"{field}.odb.size_bytes"),
                                     _text(odb["pin_source"], f"{field}.odb.pin_source"), status_files, modes, hz,
                                     _text(frequencies["source"], f"{field}.expected_frequencies.source"), excluded))
    names = [p.job_name for p in packs] + [o.job_name for o in odbs]
    if len(set(names)) != len(names):
        _fail("archive_reuse", "each job is reused at most once.")
    provenance = data["provenance"]
    if not isinstance(provenance, list) or not provenance:
        _fail("provenance", "must be a non-empty list.")
    canonical = json.loads(json.dumps(data, sort_keys=True))
    return ArchiveReusePlan(tuple(packs), tuple(odbs), canonical)


def load_archive_reuse(path, parameterisation_id: str) -> ArchiveReusePlan:
    with open(path, encoding="utf-8") as handle:
        return parse_archive_reuse(json.load(handle), parameterisation_id)
