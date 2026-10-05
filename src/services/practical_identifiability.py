"""Practical identifiability — Auto-ID M5.1–M5.4 (SPEC §7, §10; D-003, D-011; M5_DECISION_RECORD.md).

The full parameter system of SPEC §10, in ln p:

    S~  = Σ^(−1/2) · S                      # whitened FIT sensitivities (confirmed cluster = one term)
    A   = [ S~ ; C_prior^(−1/2) · E_nuis ]  # prior rows for nuisance parameters only
    C   = (AᵀA)⁻¹ ;  sd_j = sqrt(C_jj)      # ln p
    q_j = ‖(I − P_N) a_j‖ / ‖a_j‖           # a_j column of A, N the other columns (q_G for G12)

- **M5.1 (sensitivities):** typed global / nuisance columns, each with explicit provenance. Only
  fit terms appear; a confirmed cluster is one term (the mean of its member rows, matching the
  cluster residual of M4.7).
- **M5.2 (prior rows):** every nuisance parameter needs an explicit prior (centre and sd in ln p,
  provenance, PROVISIONAL flag). There are no default priors; a missing prior is a refusal.
  Global parameters have no prior rows.
- **M5.3 (rank):**
  - the numerical rank rule is rcond = 1e-3 (SPEC §10 default, a module constant, not an
    argument);
  - **rank deficiency is a hard block**: no covariance, no sd, no pseudo-inverse, no override;
  - condition number, correlations and pairwise cosines are diagnostics only.
- **M5.4 (q):** the nuisance-space projection for every parameter (q_G for G12). It is
  diagnostic evidence with **no verdict threshold**.

The SPEC §10 rule "sd_j > 8 % → not fitted" is reported per parameter as evidence for the M5.9
verdict engine, which is not implemented here. Σ is explicit; model discrepancy never enters it
(D-003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Mapping, Optional, Sequence

import numpy as np

from domain.identification_run import canonical_hash

from .identification_step import broyden_update


SCHEMA = "auto-id/practical-identifiability/v1"
RCOND = 1.0e-3  # SPEC §10: numerical rank tolerance (default for v1.1); not overridable
SD_FIT_LIMIT_LN = 0.08  # SPEC §10: sd_j > 8 % (sd in ln p) -> the parameter is not fitted (evidence for M5.9)
G12_PARAMETER = "G12_mpa"
_HASH_DIGITS = 12  # float rounding inside result hashes only (platform-independent records)


class PracticalIdentifiabilityInputError(ValueError):
    """Inputs are malformed (shapes, identities, non-finite values, non-SPD Σ)."""


class NuisancePriorRefusal(Exception):
    """A nuisance parameter lacks its required explicit prior (or a prior is not allowed). Never defaulted."""


class RankDeficiencyRefusal(Exception):
    """SPEC §10: the full system is rank-deficient. A hard scientific block; there is no override."""

    def __init__(self, reasons: Sequence[str]) -> None:
        super().__init__("rank-deficient full system: " + "; ".join(reasons))
        self.reasons = tuple(reasons)


def _finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)) or not math.isfinite(float(value)):
        raise PracticalIdentifiabilityInputError(f"{field_name} must be a finite number.")
    return float(value)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PracticalIdentifiabilityInputError(f"{field_name} must be a non-empty string.")
    return value


def _rounded(values) -> list:
    return [float(f"{float(v):.{_HASH_DIGITS}g}") for v in np.asarray(values, dtype=float).ravel()]


# ----------------------------------------------------------------------------- M5.1 parameters and sensitivities

class ParameterRole(str, Enum):
    GLOBAL = "GLOBAL"
    NUISANCE = "NUISANCE"


@dataclass(frozen=True)
class ParameterDefinition:
    parameter_id: str
    role: ParameterRole
    specimen: Optional[str] = None  # nuisance parameters are specimen parameters (for example k_core of SP13)

    def __post_init__(self) -> None:
        _text(self.parameter_id, "parameter_id")
        if not isinstance(self.role, ParameterRole):
            raise PracticalIdentifiabilityInputError("role must be a ParameterRole.")
        if self.role is ParameterRole.NUISANCE and not self.specimen:
            raise PracticalIdentifiabilityInputError(f"{self.parameter_id}: a nuisance parameter needs its specimen.")

    def to_dict(self) -> dict:
        return {"parameter_id": self.parameter_id, "role": self.role.value, "specimen": self.specimen}


@dataclass(frozen=True)
class ObservationTerm:
    """One FIT term: a single frozen row, or a confirmed cluster (≥ 2 rows) counted as one observation."""

    term_id: str
    row_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.term_id, "term_id")
        if not self.row_ids or len(set(self.row_ids)) != len(self.row_ids):
            raise PracticalIdentifiabilityInputError(f"{self.term_id}: row ids must be non-empty and unique.")

    @property
    def is_cluster(self) -> bool:
        return len(self.row_ids) > 1

    def to_dict(self) -> dict:
        return {"term_id": self.term_id, "row_ids": list(self.row_ids)}


@dataclass(frozen=True)
class SensitivityMatrix:
    """S_ij = ∂ ln f_i / ∂ ln p_j for FIT terms only, with the provenance of every column."""

    terms: tuple[ObservationTerm, ...]
    parameters: tuple[ParameterDefinition, ...]
    values: tuple[tuple[float, ...], ...]  # len(terms) × len(parameters)
    column_provenance: Mapping[str, str]

    def __post_init__(self) -> None:
        term_ids = [t.term_id for t in self.terms]
        parameter_ids = [p.parameter_id for p in self.parameters]
        if not self.terms or not self.parameters:
            raise PracticalIdentifiabilityInputError("a sensitivity matrix needs terms and parameters.")
        if len(set(term_ids)) != len(term_ids) or len(set(parameter_ids)) != len(parameter_ids):
            raise PracticalIdentifiabilityInputError("term and parameter ids must be unique.")
        rows = [row for term in self.terms for row in term.row_ids]
        if len(set(rows)) != len(rows):
            raise PracticalIdentifiabilityInputError("a frozen row may belong to one fit term only.")
        if len(self.values) != len(self.terms) or any(len(r) != len(self.parameters) for r in self.values):
            raise PracticalIdentifiabilityInputError("values must be terms × parameters.")
        object.__setattr__(self, "values", tuple(tuple(_finite(v, "sensitivity") for v in row) for row in self.values))
        if set(self.column_provenance) != set(parameter_ids):
            raise PracticalIdentifiabilityInputError("every column needs provenance (and only the matrix columns).")
        for key, value in self.column_provenance.items():
            _text(value, f"provenance of {key}")
        object.__setattr__(self, "column_provenance", dict(sorted(self.column_provenance.items())))

    @property
    def term_ids(self) -> tuple[str, ...]:
        return tuple(t.term_id for t in self.terms)

    @property
    def parameter_ids(self) -> tuple[str, ...]:
        return tuple(p.parameter_id for p in self.parameters)

    def array(self) -> np.ndarray:
        return np.array(self.values, dtype=float)

    def to_dict(self) -> dict:
        return {"terms": [t.to_dict() for t in self.terms], "parameters": [p.to_dict() for p in self.parameters],
                "values": [list(row) for row in self.values], "column_provenance": dict(self.column_provenance)}


def build_sensitivity_matrix(row_sensitivities: Mapping[str, Mapping[str, float]], single_rows: Sequence[str],
                             clusters: Sequence[Sequence[str]], parameters: Sequence[ParameterDefinition],
                             column_provenance: Mapping[str, str]) -> SensitivityMatrix:
    """Fit terms from per-row sensitivities: one term per single row, one term per confirmed cluster.

    A cluster term is the mean of its members' rows, the sensitivity of r_C = (1/n_C)·Σ ln(f_FE/f_EXP).
    Holdout rows must not be passed.
    """
    parameter_ids = [p.parameter_id for p in parameters]
    terms, values = [], []

    def row(row_id: str) -> list[float]:
        if row_id not in row_sensitivities:
            raise PracticalIdentifiabilityInputError(f"no sensitivities for row {row_id}.")
        data = row_sensitivities[row_id]
        missing = sorted(set(parameter_ids) - set(data))
        if missing:
            raise PracticalIdentifiabilityInputError(f"row {row_id}: missing columns {missing}.")
        return [_finite(data[p], f"{row_id}.{p}") for p in parameter_ids]

    for row_id in single_rows:
        terms.append(ObservationTerm(str(row_id), (str(row_id),)))
        values.append(row(row_id))
    for members in clusters:
        members = tuple(str(m) for m in members)
        if len(members) < 2:
            raise PracticalIdentifiabilityInputError("a confirmed cluster has at least two rows.")
        terms.append(ObservationTerm("C(" + "+".join(members) + ")", members))
        values.append(list(np.mean([row(m) for m in members], axis=0)))
    return SensitivityMatrix(tuple(terms), tuple(parameters), tuple(tuple(v) for v in values), dict(column_provenance))


# ----------------------------------------------------------------------------- Σ (explicit)

@dataclass(frozen=True)
class CovarianceComponent:
    """One explicit additive part of Σ over the fit terms, in (ln f)² units (for example Σ_meas, Σ_setup)."""

    name: str
    matrix: tuple[tuple[float, ...], ...]
    provisional: bool
    provenance: str

    def __post_init__(self) -> None:
        _text(self.name, "component name")
        _text(self.provenance, f"{self.name} provenance")
        if not isinstance(self.provisional, bool):
            raise PracticalIdentifiabilityInputError("provisional must be a boolean.")
        object.__setattr__(self, "matrix", tuple(tuple(_finite(v, self.name) for v in row) for row in self.matrix))

    def to_dict(self) -> dict:
        return {"name": self.name, "matrix": [list(r) for r in self.matrix], "provisional": self.provisional,
                "provenance": self.provenance}


def diagonal_component(name: str, term_ids: Sequence[str], term_sd_ln: Mapping[str, float], provisional: bool,
                       provenance: str) -> CovarianceComponent:
    """A diagonal component from per-term standard deviations in ln f (sd > 0 required)."""
    if set(term_sd_ln) != set(term_ids):
        raise PracticalIdentifiabilityInputError(f"{name}: an sd is needed for exactly the fit terms.")
    sds = []
    for term in term_ids:
        sd = _finite(term_sd_ln[term], f"{name}.{term}")
        if sd <= 0.0:
            raise PracticalIdentifiabilityInputError(f"{name}.{term}: sd must be positive.")
        sds.append(sd)
    return CovarianceComponent(name, tuple(tuple(float(v) for v in row) for row in np.diag(np.square(sds))),
                               provisional, provenance)


@dataclass(frozen=True)
class ObservationCovariance:
    """Σ = Σ components (SPEC §7: Σ_meas + Σ_setup); explicit, symmetric positive definite."""

    term_ids: tuple[str, ...]
    components: tuple[CovarianceComponent, ...]

    def __post_init__(self) -> None:
        if not self.components:
            raise PracticalIdentifiabilityInputError("Σ needs at least one explicit component.")
        n = len(self.term_ids)
        for component in self.components:
            if len(component.matrix) != n or any(len(row) != n for row in component.matrix):
                raise PracticalIdentifiabilityInputError(f"{component.name}: must be {n} × {n} over the fit terms.")
        total = self.matrix()
        if not np.allclose(total, total.T, rtol=0.0, atol=1e-15 * max(1.0, float(np.abs(total).max()))):
            raise PracticalIdentifiabilityInputError("Σ must be symmetric.")
        try:
            np.linalg.cholesky(total)
        except np.linalg.LinAlgError as error:
            raise PracticalIdentifiabilityInputError("Σ must be positive definite.") from error

    def matrix(self) -> np.ndarray:
        return np.sum([np.array(c.matrix, dtype=float) for c in self.components], axis=0)

    @property
    def provisional(self) -> bool:
        return any(c.provisional for c in self.components)

    def to_dict(self) -> dict:
        return {"term_ids": list(self.term_ids), "components": [c.to_dict() for c in self.components]}


# ----------------------------------------------------------------------------- M5.2 nuisance priors

@dataclass(frozen=True)
class NuisancePrior:
    """Gaussian prior on one nuisance parameter in ln p: centre x_0 and sd (explicit, never defaulted)."""

    parameter_id: str
    center_ln: float
    sd_ln: float
    provenance: str
    provisional: bool

    def __post_init__(self) -> None:
        _text(self.parameter_id, "prior parameter_id")
        _finite(self.center_ln, f"{self.parameter_id} prior centre")
        sd = _finite(self.sd_ln, f"{self.parameter_id} prior sd")
        if sd <= 0.0:
            raise NuisancePriorRefusal(f"{self.parameter_id}: prior sd must be positive (got {sd}).")
        _text(self.provenance, f"{self.parameter_id} prior provenance")
        if not isinstance(self.provisional, bool):
            raise PracticalIdentifiabilityInputError("provisional must be a boolean.")

    def to_dict(self) -> dict:
        return {"parameter_id": self.parameter_id, "center_ln": self.center_ln, "sd_ln": self.sd_ln,
                "provenance": self.provenance, "provisional": self.provisional}


# ----------------------------------------------------------------------------- the full system A

@dataclass(frozen=True)
class PracticalSystem:
    matrix: SensitivityMatrix
    covariance: ObservationCovariance
    priors: tuple[NuisancePrior, ...]

    def whitened_sensitivities(self) -> np.ndarray:
        """S~ = Σ^(−1/2)·S, using the Cholesky factor (Σ = L Lᵀ, S~ = L⁻¹ S); AᵀA is independent of the root."""
        lower = np.linalg.cholesky(self.covariance.matrix())
        return np.linalg.solve(lower, self.matrix.array())

    def prior_rows(self) -> np.ndarray:
        index = {p: j for j, p in enumerate(self.matrix.parameter_ids)}
        rows = np.zeros((len(self.priors), len(index)))
        for k, prior in enumerate(self.priors):
            rows[k, index[prior.parameter_id]] = 1.0 / prior.sd_ln
        return rows

    def design(self) -> np.ndarray:
        return np.vstack([self.whitened_sensitivities(), self.prior_rows()])

    @property
    def row_labels(self) -> tuple[str, ...]:
        return self.matrix.term_ids + tuple(f"prior:{p.parameter_id}" for p in self.priors)

    @property
    def provisional_inputs(self) -> tuple[str, ...]:
        flagged = [f"Σ:{c.name}" for c in self.covariance.components if c.provisional]
        flagged += [f"prior:{p.parameter_id}" for p in self.priors if p.provisional]
        return tuple(flagged)

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "matrix": self.matrix.to_dict(), "covariance": self.covariance.to_dict(),
                "priors": [p.to_dict() for p in self.priors]}

    @property
    def system_hash(self) -> str:
        return canonical_hash(self.to_dict())


def assemble_system(matrix: SensitivityMatrix, covariance: ObservationCovariance,
                    priors: Sequence[NuisancePrior]) -> PracticalSystem:
    """Bind Σ and the nuisance priors to the sensitivity matrix; refuse missing or misplaced priors."""
    if tuple(covariance.term_ids) != matrix.term_ids:
        raise PracticalIdentifiabilityInputError("Σ must be defined over exactly the fit terms, in matrix order.")
    roles = {p.parameter_id: p.role for p in matrix.parameters}
    by_id = {}
    for prior in priors:
        if prior.parameter_id not in roles:
            raise NuisancePriorRefusal(f"prior for unknown parameter {prior.parameter_id}.")
        if roles[prior.parameter_id] is not ParameterRole.NUISANCE:
            raise NuisancePriorRefusal(f"{prior.parameter_id} is global: SPEC §10 has prior rows only for nuisance "
                                       "parameters.")
        if prior.parameter_id in by_id:
            raise NuisancePriorRefusal(f"duplicate prior for {prior.parameter_id}.")
        by_id[prior.parameter_id] = prior
    missing = [p for p, role in roles.items() if role is ParameterRole.NUISANCE and p not in by_id]
    if missing:
        raise NuisancePriorRefusal(f"nuisance parameters {missing} have no explicit prior (no default is allowed).")
    ordered = tuple(by_id[p] for p in matrix.parameter_ids if p in by_id)
    return PracticalSystem(matrix, covariance, ordered)


# ----------------------------------------------------------------------------- M5.3 / M5.4 analysis

class RankStatus(str, Enum):
    FULL_RANK = "FULL_RANK"
    RANK_DEFICIENT = "RANK_DEFICIENT"  # hard block (SPEC §10)


@dataclass(frozen=True)
class ProjectionDiagnostic:
    """q_j = ‖(I − P_N) a_j‖ / ‖a_j‖ (diagnostic; no threshold). For G12 this is q_G."""

    parameter_id: str
    q: float
    residual_norm: float  # ‖(I − P_N) a_j‖
    projected_sd_ln: Optional[float]  # 1 / ‖(I − P_N) a_j‖ when the parameter has no prior row (SPEC §10)


@dataclass(frozen=True)
class PracticalIdentifiabilityResult:
    system_hash: str
    status: RankStatus
    rcond: float
    singular_values: tuple[float, ...]
    rank: int
    parameter_ids: tuple[str, ...]
    covariance_ln: Optional[tuple[tuple[float, ...], ...]]  # C = (AᵀA)⁻¹, only when FULL_RANK
    sd_ln: Optional[Mapping[str, float]]  # posterior sd foundation (M5.5 builds statistical_sd on it)
    exceeds_sd_fit_limit: Optional[Mapping[str, bool]]  # SPEC §10 sd_j > 8 % -> not fitted (evidence for M5.9)
    correlation: Optional[tuple[tuple[float, ...], ...]]  # diagnostic
    condition_number: float  # diagnostic only (inf when the smallest singular value is 0)
    pairwise_cosines: Mapping[str, float]  # cos(s~_i, s~_j) of the whitened data block S~ (SPEC §10 warning), diagnostic only
    projections: Mapping[str, ProjectionDiagnostic]  # q for every parameter (q_G for G12)
    provisional_inputs: tuple[str, ...]
    refusal_reasons: tuple[str, ...]

    @property
    def q_g(self) -> Optional[float]:
        diagnostic = self.projections.get(G12_PARAMETER)
        return None if diagnostic is None else diagnostic.q

    @property
    def full_rank(self) -> bool:
        return self.status is RankStatus.FULL_RANK

    def require_full_rank(self) -> "PracticalIdentifiabilityResult":
        if not self.full_rank:
            raise RankDeficiencyRefusal(self.refusal_reasons)
        return self

    def to_dict(self) -> dict:
        def rounded_map(values):
            return None if values is None else {k: _rounded([v])[0] for k, v in sorted(values.items())}

        return {
            "schema": SCHEMA, "system_hash": self.system_hash, "status": self.status.value, "rcond": self.rcond,
            "rank": self.rank, "parameter_ids": list(self.parameter_ids),
            "singular_values": _rounded(self.singular_values),
            "covariance_ln": None if self.covariance_ln is None else _rounded(self.covariance_ln),
            "sd_ln": rounded_map(self.sd_ln),
            "exceeds_sd_fit_limit": None if self.exceeds_sd_fit_limit is None else dict(sorted(self.exceeds_sd_fit_limit.items())),
            "correlation": None if self.correlation is None else _rounded(self.correlation),
            "condition_number": None if math.isinf(self.condition_number) else _rounded([self.condition_number])[0],
            "pairwise_cosines": rounded_map(self.pairwise_cosines),
            "projections": {k: {"q": _rounded([d.q])[0], "residual_norm": _rounded([d.residual_norm])[0],
                                "projected_sd_ln": None if d.projected_sd_ln is None else _rounded([d.projected_sd_ln])[0]}
                            for k, d in sorted(self.projections.items())},
            "provisional_inputs": list(self.provisional_inputs), "refusal_reasons": list(self.refusal_reasons),
        }

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _projection(design: np.ndarray, j: int, has_prior: bool, parameter_id: str) -> ProjectionDiagnostic:
    a = design[:, j]
    others = np.delete(design, j, axis=1)
    norm = float(np.linalg.norm(a))
    if norm == 0.0:
        return ProjectionDiagnostic(parameter_id, 0.0, 0.0, None)
    if others.shape[1]:
        coefficients, *_ = np.linalg.lstsq(others, a, rcond=None)
        residual = a - others @ coefficients
    else:
        residual = a
    residual_norm = float(np.linalg.norm(residual))
    projected = None if has_prior or residual_norm == 0.0 else 1.0 / residual_norm
    return ProjectionDiagnostic(parameter_id, residual_norm / norm, residual_norm, projected)


def analyse_practical_identifiability(system: PracticalSystem) -> PracticalIdentifiabilityResult:
    """SVD rank (rcond = 1e-3), posterior covariance in ln p, q projections and diagnostics. No override."""

    design = system.design()
    parameter_ids = system.matrix.parameter_ids
    n = len(parameter_ids)
    singular = np.linalg.svd(design, compute_uv=False)
    smax = float(singular[0]) if singular.size else 0.0
    rank = int(np.sum(singular > RCOND * smax)) if smax > 0.0 else 0
    smin = float(singular[-1]) if singular.size == n else 0.0
    condition = math.inf if smin == 0.0 else smax / smin
    whitened = system.whitened_sensitivities()  # SPEC §10: the pairwise warning uses cos(s~_i, s~_j) of S~
    norms = np.linalg.norm(whitened, axis=0)
    cosines = {}
    for i in range(n):
        for j in range(i + 1, n):
            denominator = norms[i] * norms[j]
            cosines[f"{parameter_ids[i]}|{parameter_ids[j]}"] = (
                float(whitened[:, i] @ whitened[:, j] / denominator) if denominator > 0.0 else 0.0)
    prior_ids = {p.parameter_id for p in system.priors}
    projections = {pid: _projection(design, j, pid in prior_ids, pid) for j, pid in enumerate(parameter_ids)}
    if rank < n:
        reasons = (f"rank {rank} < {n} parameters at rcond {RCOND:g} (smallest/largest singular value "
                   f"{(smin / smax) if smax else 0.0:.3g}); SPEC §10 hard block, no override",)
        return PracticalIdentifiabilityResult(system.system_hash, RankStatus.RANK_DEFICIENT, RCOND,
                                              tuple(float(s) for s in singular), rank, parameter_ids, None, None, None,
                                              None, condition, cosines, projections, system.provisional_inputs, reasons)
    _, s, vt = np.linalg.svd(design, full_matrices=False)
    covariance = (vt.T * (1.0 / s ** 2)) @ vt  # (AᵀA)⁻¹ of a full-rank A
    sd = np.sqrt(np.diag(covariance))
    correlation = covariance / np.outer(sd, sd)
    sd_map = {pid: float(v) for pid, v in zip(parameter_ids, sd)}
    return PracticalIdentifiabilityResult(
        system.system_hash, RankStatus.FULL_RANK, RCOND, tuple(float(x) for x in singular), rank, parameter_ids,
        tuple(tuple(float(v) for v in row) for row in covariance), sd_map,
        {pid: value > SD_FIT_LIMIT_LN for pid, value in sd_map.items()},
        tuple(tuple(float(v) for v in row) for row in correlation), condition, cosines, projections,
        system.provisional_inputs, ())


# ----------------------------------------------------------------------------- Jacobian at p̂ from an accepted LM journal

@dataclass(frozen=True)
class ReconstructedJacobian:
    """The LM's final Jacobian (whitened residuals per ln p), rebuilt from journalled evaluations."""

    parameter_ids: tuple[str, ...]
    point: Mapping[str, float]
    whitened: tuple[tuple[float, ...], ...]
    provenance: str
    updates: int


def reconstruct_lm_jacobian(evaluations: Sequence[Mapping], history: Sequence[Mapping], start: Mapping[str, float],
                            parameter_ids: Sequence[str], finite_difference_step: float) -> ReconstructedJacobian:
    """Replay the M4.8 Jacobian bookkeeping on journalled residuals (no solve).

    Central differences at the start (p·(1 ± h)), a Broyden update after every accepted step, and a
    fresh central difference after a rejected step following an update, exactly as
    ``identification_step.run_bounded_lm`` does.  Every point must be found in ``evaluations``
    (``{"parameters", "residuals"}``), or the reconstruction is refused.
    """

    names = tuple(parameter_ids)

    def residuals_at(point: np.ndarray) -> np.ndarray:
        for record in evaluations:
            values = record["parameters"]
            if all(math.isclose(values[n], float(p), rel_tol=1e-12, abs_tol=0.0) for n, p in zip(names, point)):
                if record.get("residuals") is None:
                    raise PracticalIdentifiabilityInputError("a required evaluation was refused (no residuals).")
                return np.asarray(record["residuals"], dtype=float)
        raise PracticalIdentifiabilityInputError(f"no journalled evaluation at {dict(zip(names, point))}.")

    def central(point: np.ndarray) -> np.ndarray:
        columns = []
        for j in range(len(names)):
            up, down = point.copy(), point.copy()
            up[j], down[j] = point[j] * (1.0 + finite_difference_step), point[j] * (1.0 - finite_difference_step)
            columns.append((residuals_at(up) - residuals_at(down)) / (math.log(up[j]) - math.log(down[j])))
        return np.column_stack(columns)

    p = np.array([float(start[n]) for n in names])
    jacobian, fresh, updates = central(p), True, 0
    for entry in history:
        if entry["accepted"]:
            x, trial_x = np.array(entry["x"], dtype=float), np.array(entry["trial_x"], dtype=float)
            if not np.allclose(np.exp(x), p, rtol=1e-12, atol=0.0):
                raise PracticalIdentifiabilityInputError("history does not follow the accepted points.")
            trial_p = np.exp(trial_x)
            jacobian = broyden_update(jacobian, trial_x - x, residuals_at(trial_p) - residuals_at(p))
            p, fresh, updates = trial_p, False, updates + 1
        elif entry["note"] == "rejected" and not fresh:
            jacobian, fresh = central(p), True
    return ReconstructedJacobian(names, {n: float(v) for n, v in zip(names, p)},
                                 tuple(tuple(float(v) for v in row) for row in jacobian),
                                 f"Broyden-updated LM Jacobian reconstructed from the journal ({updates} update(s) "
                                 f"after central differences at ±{finite_difference_step:g}); not a fresh "
                                 "finite-difference Jacobian at p̂", updates)
