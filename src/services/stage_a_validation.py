"""Stage-A → M5 validation adapter — Auto-ID M6.1, checkpoint M6-B (SPEC §2, §5, §5.2, §6 S4, §7–§10,
§12.1, §15, §17; D-008, D-033, D-034, D-040–D-048, D-049–D-056; M6_DECISION_RECORD.md).

A real bare plate is identified through the accepted Stage-A affine matrix model and judged by the
accepted M5 machinery only:

1. **Inputs:** every experimental input must be present and admissible
   (``domain.stage_a_experiment``). FRF-only input, a missing frozen modal set, fewer than nine
   thickness points, a missing attachment / non-contact record, a missing suspension threshold or a
   legacy pairing shortcut are refused, all gaps listed together.
2. **Forward:** the verified ``StageAAffineBasis`` (no Abaqus, no M3). Observation rows are followed
   from the baseline pairing state by FE-to-FE tracking only (``track_branches``, strict policy,
   D-008); there is no re-pairing and no fixed-pair fallback.
3. **D12 (D-051):** D11, D12 and D66 are fitted only when the full Stage-A system is practically full
   rank at the M5 rule (rcond = 1e-3). Otherwise D12 is *not identified* and the governed fixed-ν12
   formulation (D12 = ν12·D11, ν12 = 0.05, SPEC §5/§5.2) is used and recorded. No pseudo-inverse, no
   conditioning override, no legacy threshold.
4. **Estimate:** the accepted M4.8 bounded LM in ln p (explicit settings and bounds, no defaults).
5. **Evidence:** at p̂ the sensitivities are central differences ±5 % in ln p (SPEC §6 S4); the
   M5 chain gives practical rank, ``statistical_sd``, the pattern test, conditional Birge and
   ``model_form_robustness``.
6. **Derived E, G12 (D-052):** E = 12·D11·(1 − ν²)/t³ and G12 = 12·D66/t³. The thickness enters
   analytically in ln p with its cubic weight kept explicit; the spatial scatter is the sample sd of
   the measured points (never divided by √N) and a known gauge uncertainty stays a separate component.
7. **Context (D-050):** the result is a ``STAGE_A_VALIDATION`` record: estimate, separately labelled
   uncertainties and the open validation conditions. The M5.9 verdict is computed in the PRODUCTION
   context with family consistency NOT_AVAILABLE (M7 work), so it can never be IDENTIFIED here, and
   it is never relabelled.

M6.2 (D-053): ``stage_a_repeat_comparison_inputs`` prepares the ln-space comparison of two runs of the
same plate (shared thickness never double-counted); the estimator and agreement rule are a later
M6.2 decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
from typing import Mapping, Optional, Protocol, Sequence

import numpy as np
from scipy import sparse

from domain.acquisition_linkage import SetupRepeatClassification
from domain.experimental_qc import (
    ExperimentalModeEligibility,
    ExperimentalModeEligibilityRefusal,
    ExperimentalQCStatus,
)
from domain.forward_model_manifest import CARBON_PROPERTY_SET_V1
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import canonical_hash
from domain.stage_a_experiment import (
    ExcitationRoute,
    RefusalCode,
    StageAExperimentalEvidence,
    StageAInputRefusal,
    StageAPairingEvidence,
)

from .branch_tracker import BranchTrackingRefusal, FEModalState, track_branches
from .identification_step import LMSettings, LMStatus, ParameterBounds, run_bounded_lm
from .identification_uncertainty import BirgeStatus, ResidualTerm, residual_terms
from .identification_verdict import (
    EvidenceState,
    GuardEvidence,
    SandwichG12Evidence,
    Verdict,
    VerdictContext,
    VerdictInputs,
    compute_evidence_chain,
    decide_verdicts,
    fitting_pair_mac_evidence,
)
from .matrix_model_service import (
    MatrixModelError,
    StageAAffineBasis,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from .practical_identifiability import (
    CovarianceComponent,
    ObservationCovariance,
    ObservationTerm,
    ParameterDefinition,
    ParameterRole,
    PracticalSystem,
    SensitivityMatrix,
    analyse_practical_identifiability,
    assemble_system,
)


SCHEMA = "auto-id/stage-a-validation/v1"
D11, D12, D66 = "D11", "D12", "D66"
FULL_PARAMETERS = (D11, D12, D66)
FIXED_NU12_PARAMETERS = (D11, D66)
GOVERNED_NU12 = CARBON_PROPERTY_SET_V1.fixed_constants["nu12"]  # SPEC §5 / §5.2: ν12 = 0.05 (campaign definition)
GOVERNED_NU12_SOURCE = "SPEC §5 / §5.2 accepted campaign definition (carbon-property-set/v1 fixed nu12)"
THICKNESS_EXPONENT = -3  # E, G12 ∝ t⁻³ (D-052): kept explicit in every derived record
SPEC_PROVISIONAL_SETUP_SD_LN = 0.003  # SPEC §7: provisional Σ_setup 0.3 % until measured (sd in ln f, first order)
_DIGITS = 12


def _r(value):
    return None if value is None else float(f"{float(value):.{_DIGITS}g}")


class StageAValidationError(ValueError):
    """Malformed adapter inputs (types, shapes, inconsistent identities)."""


class ResultContext(str, Enum):
    STAGE_A_VALIDATION = "STAGE_A_VALIDATION"  # D-050: real Stage-A validation / calibration; never production


class ValidationStatus(str, Enum):
    ESTIMATE_REPORTED = "ESTIMATE_REPORTED"  # estimate + separately labelled uncertainties + open conditions
    REFUSED = "REFUSED"  # scientific refusal (rank, tracking, LM); no estimate


class D12Status(str, Enum):
    FITTED = "FITTED"  # full Stage-A system practically full rank at rcond 1e-3
    NOT_IDENTIFIED = "NOT_IDENTIFIED"  # rank-deficient: governed fixed-ν12 formulation used instead


# ----------------------------------------------------------------------------- Σ

class SigmaKind(str, Enum):
    MEASUREMENT = "Sigma_meas"  # modal-fit uncertainty (never invented, never relabelled setup scatter)
    SETUP = "Sigma_setup"  # same-panel setup / retest scatter (SPEC §7)


@dataclass(frozen=True)
class StageASigmaTerm:
    """One explicit Σ component over all observation terms (fit terms, then holdout rows)."""

    kind: SigmaKind
    component: CovarianceComponent

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SigmaKind) or not isinstance(self.component, CovarianceComponent):
            raise StageAValidationError("a Σ term needs a SigmaKind and a CovarianceComponent.")
        if self.component.name != self.kind.value:
            raise StageAValidationError(f"a {self.kind.name} component must be named {self.kind.value!r}; "
                                        f"got {self.component.name!r} (no relabelling).")


def observation_term_ids(pairing: StageAPairingEvidence) -> tuple[str, ...]:
    """The Σ ordering: M5 fit terms (single rows, then confirmed clusters), then holdout rows."""
    return pairing.fit_term_ids + tuple(r.row_id for r in pairing.holdout_rows)


def spec_provisional_setup_term(term_ids: Sequence[str]) -> StageASigmaTerm:
    """SPEC §7 provisional Σ_setup (0.3 %), explicitly PROVISIONAL until the M6.2 same-panel repeat (D-053)."""
    matrix = np.diag(np.full(len(term_ids), SPEC_PROVISIONAL_SETUP_SD_LN ** 2))
    return StageASigmaTerm(SigmaKind.SETUP, CovarianceComponent(
        SigmaKind.SETUP.value, tuple(tuple(float(v) for v in row) for row in matrix), True,
        "SPEC §7 provisional Σ_setup 0.3 % (sd 0.003 in ln f, first order) until measured by the M6.2 "
        "same-panel repeat; PROVISIONAL (D-053)"))


# ----------------------------------------------------------------------------- forward (affine Stage-A model)

def _sparse_digest(hasher, label: str, matrix) -> None:
    matrix = sparse.csr_matrix(matrix, dtype=np.float64)
    matrix.sort_indices()
    hasher.update(f"{label}:{matrix.shape[0]}x{matrix.shape[1]}".encode())
    for array, dtype in ((matrix.indptr, np.int64), (matrix.indices, np.int64), (matrix.data, np.float64)):
        hasher.update(np.ascontiguousarray(array, dtype=dtype).tobytes())


@dataclass(frozen=True)
class StageAForwardModel:
    """The verified affine Stage-A model of one specimen (SI units: D in N·m)."""

    model_id: str
    basis: StageAAffineBasis
    mode_count: int
    expected_rigid_body_modes: Optional[int]  # 6 for a free-free plate model; explicit
    modelled_attachment_mass_g: Optional[float]  # the attachment mass included in the model (SPEC §15)
    provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise StageAValidationError("model_id must be a non-empty string.")
        if not isinstance(self.basis, StageAAffineBasis):
            raise StageAValidationError("basis must be a verified StageAAffineBasis.")
        if isinstance(self.mode_count, bool) or not isinstance(self.mode_count, int) or self.mode_count < 1:
            raise StageAValidationError("mode_count must be a positive integer.")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise StageAValidationError("forward provenance required.")

    @property
    def dof_hash(self) -> str:
        return canonical_hash([[d.node_label, d.dof] for d in self.basis.dofs])

    @property
    def identity_hash(self) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.model_id.encode("utf-8"))
        hasher.update(self.dof_hash.encode())
        hasher.update(np.asarray(self.basis.reference_parameters.values, dtype=np.float64).tobytes())
        _sparse_digest(hasher, "K_ref", self.basis.reference_stiffness)
        for name, matrix in zip(FULL_PARAMETERS, self.basis.basis_matrices):
            _sparse_digest(hasher, f"K_{name}", matrix)
        _sparse_digest(hasher, "M_ref", self.basis.mass)
        if self.basis.mass_derivative_D11 is not None:
            _sparse_digest(hasher, "dM/dD11", self.basis.mass_derivative_D11)
        hasher.update(canonical_hash([self.mode_count, self.expected_rigid_body_modes,
                                      self.modelled_attachment_mass_g]).encode())
        return hasher.hexdigest()

    def state(self, d11: float, d12: float, d66: float) -> FEModalState:
        parameters = StageAMatrixParameters(float(d11), float(d12), float(d66))
        result = solve_generalized_eigenproblem(
            self.basis.reconstruct_stiffness(parameters), self.basis.reconstruct_mass(parameters), self.mode_count,
            expected_rigid_body_modes=self.expected_rigid_body_modes, dofs=self.basis.dofs)
        state_id = f"{self.model_id}:" + canonical_hash([_r(d11), _r(d12), _r(d66)])[:16]
        return FEModalState(state_id, self.identity_hash, self.dof_hash, tuple(range(1, self.mode_count + 1)),
                            tuple(float(f) for f in result.frequencies_hz), np.asarray(result.eigenvectors).T)


# ----------------------------------------------------------------------------- the observation problem

class _StageAProblem:
    """ln-misfit terms e = ln f_FE − ln f_EXP over fit terms (cluster = mean of members) and holdout rows."""

    def __init__(self, forward: StageAForwardModel, pairing: StageAPairingEvidence, frequencies: Mapping[int, float],
                 covariance: np.ndarray, start: Mapping[str, float]) -> None:
        self.forward, self.pairing = forward, pairing
        self.rows = {r.row_id: r for r in pairing.rows}
        self.log_exp = {r.row_id: math.log(frequencies[r.experimental_mode_id]) for r in pairing.rows}
        n_fit = len(pairing.fit_term_ids)
        self.fit_lower = np.linalg.cholesky(covariance[:n_fit, :n_fit])
        self.holdout_sd = np.sqrt(np.diag(covariance)[n_fit:])
        d11, d66 = float(start[D11]), float(start[D66])
        self.baseline = forward.state(d11, GOVERNED_NU12 * d11, d66)

    @staticmethod
    def physical(values: Mapping[str, float], fitted: Sequence[str]) -> tuple[float, float, float]:
        d11, d66 = float(values[D11]), float(values[D66])
        d12 = float(values[D12]) if D12 in fitted else GOVERNED_NU12 * d11
        return d11, d12, d66

    def misfit(self, values: Mapping[str, float], fitted: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
        candidate = self.forward.state(*self.physical(values, fitted))
        tracking = track_branches(STRICT_IDENTIFICATION_PAIRING, self.baseline, candidate,
                                  {row_id: row.fe_mode for row_id, row in self.rows.items()}, self.pairing.clusters)
        log_fe = {b.row_id: math.log(b.candidate_hz) for b in tracking.branches}
        fit = [log_fe[row] - self.log_exp[row] for row in self.pairing.single_fit_rows]
        by_group = {tuple(c.row_ids): c for c in tracking.clusters}
        for group in self.pairing.clusters:
            tracked = by_group[tuple(group)]
            fit.append(float(np.mean([math.log(f) for f in tracked.candidate_hz]))
                       - float(np.mean([self.log_exp[m] for m in group])))
        holdout = [log_fe[r.row_id] - self.log_exp[r.row_id] for r in self.pairing.holdout_rows]
        return np.array(fit, dtype=float), np.array(holdout, dtype=float)

    def whitened_fit(self, values: Mapping[str, float], fitted: Sequence[str]) -> np.ndarray:
        fit, _ = self.misfit(values, fitted)
        return np.linalg.solve(self.fit_lower, fit)

    def sensitivities(self, point: Mapping[str, float], fitted: Sequence[str], step: float) -> np.ndarray:
        """∂(ln f_FE)/∂(ln p) by central differences p·(1 ± step) (SPEC §6 S4); fit terms only."""
        columns = []
        for name in fitted:
            up, down = dict(point), dict(point)
            up[name], down[name] = point[name] * (1.0 + step), point[name] * (1.0 - step)
            columns.append((self.misfit(up, fitted)[0] - self.misfit(down, fitted)[0])
                           / (math.log(1.0 + step) - math.log(1.0 - step)))
        return np.column_stack(columns)


def _system(problem: _StageAProblem, point: Mapping[str, float], fitted: Sequence[str], fit_sigma: Sequence[
        CovarianceComponent], step: float) -> PracticalSystem:
    pairing = problem.pairing
    terms = tuple(ObservationTerm(r, (r,)) for r in pairing.single_fit_rows) + tuple(
        ObservationTerm("C(" + "+".join(g) + ")", tuple(g)) for g in pairing.clusters)
    values = problem.sensitivities(point, fitted, step)
    provenance = (f"central differences ±{step:g} in ln p on the Stage-A affine model {problem.forward.model_id} "
                  f"({problem.forward.identity_hash[:16]}) at " + canonical_hash({k: _r(v) for k, v in point.items()})
                  [:16] + " (SPEC §6 S4)")
    matrix = SensitivityMatrix(terms, tuple(ParameterDefinition(p, ParameterRole.GLOBAL) for p in fitted),
                               tuple(tuple(float(v) for v in row) for row in values), {p: provenance for p in fitted})
    return assemble_system(matrix, ObservationCovariance(matrix.term_ids, tuple(fit_sigma)), ())


# ----------------------------------------------------------------------------- the report

@dataclass(frozen=True)
class DerivedQuantity:
    """E or G12 from D at p̂ and the mean thickness, with its uncertainty components in ln p (all labelled)."""

    name: str
    value_mpa: float
    thickness_exponent: int
    frequency_statistical_sd_ln: float  # from statistical_sd of the D parameters (C of the M5 system)
    frequency_birge_adjusted_sd_ln: Optional[float]  # only when Birge is AVAILABLE
    thickness_spatial_sd_ln: float  # |exponent|·s_t/t̄, s_t the sample sd of the points (not /√N)
    thickness_gauge_sd_ln: Optional[float]  # |exponent|·u_gauge/t̄, only when a gauge uncertainty is supplied
    statistical_sd_ln_with_thickness: float  # √(frequency² + spatial² + gauge²), independent components
    model_form_robustness_half_range_ln: Optional[float]  # linearised leave-one-family-out; not 1σ

    def to_dict(self) -> dict:
        return {"name": self.name, "value_mpa": _r(self.value_mpa), "thickness_exponent": self.thickness_exponent,
                "frequency_statistical_sd_ln": _r(self.frequency_statistical_sd_ln),
                "frequency_birge_adjusted_sd_ln": _r(self.frequency_birge_adjusted_sd_ln),
                "thickness_spatial_sd_ln": _r(self.thickness_spatial_sd_ln),
                "thickness_gauge_sd_ln": _r(self.thickness_gauge_sd_ln),
                "statistical_sd_ln_with_thickness": _r(self.statistical_sd_ln_with_thickness),
                "model_form_robustness_half_range_ln": _r(self.model_form_robustness_half_range_ln)}


@dataclass(frozen=True)
class StageAValidationReport:
    context: ResultContext
    status: ValidationStatus
    case_label: str
    physical_specimen_id: str
    test_run_id: str
    input_hashes: Mapping[str, str]
    refusal_reasons: tuple[str, ...]
    d12: Mapping[str, object]
    lm: Mapping[str, object]
    fitted_parameters: tuple[str, ...]
    estimates: Optional[Mapping[str, float]]  # D values (N·m)
    statistical_sd_ln: Optional[Mapping[str, float]]
    covariance_ln: Optional[tuple[tuple[float, ...], ...]]
    birge: Optional[Mapping[str, object]]
    model_form_robustness: Optional[Mapping[str, object]]
    rank_diagnostics: Optional[Mapping[str, object]]
    derived: Optional[Mapping[str, DerivedQuantity]]
    nu12_used: Optional[float]
    thickness_mean_mm: Optional[float]
    production_verdict: Optional[Mapping[str, object]]  # M5.9 PRODUCTION context, embedded unchanged
    open_conditions: tuple[str, ...]
    provisional_inputs: tuple[str, ...]
    note: str = ("STAGE_A_VALIDATION (D-050): estimate and separately labelled uncertainties of a real Stage-A run; "
                 "not a production material-property verdict; production family consistency is M7 work")

    @property
    def production_identified(self) -> bool:
        """Always False: this context never grants production IDENTIFIED (D-050)."""
        return False

    def to_dict(self) -> dict:
        def rounded(values):
            return None if values is None else {k: _r(v) for k, v in sorted(values.items())}

        return {"schema": SCHEMA, "context": self.context.value, "status": self.status.value, "note": self.note,
                "case_label": self.case_label, "physical_specimen_id": self.physical_specimen_id,
                "test_run_id": self.test_run_id, "input_hashes": dict(sorted(self.input_hashes.items())),
                "refusal_reasons": list(self.refusal_reasons), "d12": self.d12, "lm": self.lm,
                "fitted_parameters": list(self.fitted_parameters), "estimates": rounded(self.estimates),
                "statistical_sd_ln": rounded(self.statistical_sd_ln),
                "covariance_ln": None if self.covariance_ln is None else
                [[_r(v) for v in row] for row in self.covariance_ln],
                "birge": self.birge, "model_form_robustness": self.model_form_robustness,
                "rank_diagnostics": self.rank_diagnostics,
                "derived": None if self.derived is None else {k: v.to_dict() for k, v in sorted(self.derived.items())},
                "nu12_used": _r(self.nu12_used), "thickness_mean_mm": _r(self.thickness_mean_mm),
                "production_verdict": self.production_verdict, "production_identified": self.production_identified,
                "open_conditions": list(self.open_conditions), "provisional_inputs": list(self.provisional_inputs)}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


# ----------------------------------------------------------------------------- admission

def _admit(evidence: StageAExperimentalEvidence, pairing: StageAPairingEvidence,
           forward: StageAForwardModel) -> None:
    reasons = list(evidence.refusals())
    reasons += pairing.refusals(evidence.modal_input)
    excitation = evidence.excitation
    if excitation is not None:
        if excitation.route is ExcitationRoute.CONTACT_ATTACHMENT and excitation.attachment_mass_g is not None \
                and forward.modelled_attachment_mass_g != excitation.attachment_mass_g:
            reasons.append((RefusalCode.ATTACHMENT_MASS_NOT_MODELLED, f"recorded attachment mass "
                            f"{excitation.attachment_mass_g:g} g is not the mass modelled in {forward.model_id} "
                            f"({forward.modelled_attachment_mass_g})"))
        if excitation.route is ExcitationRoute.NON_CONTACT and forward.modelled_attachment_mass_g is not None:
            reasons.append((RefusalCode.ATTACHMENT_MASS_NOT_MODELLED, "non-contact excitation but the model "
                            "carries an attachment mass"))
    if evidence.suspension is not None and evidence.modal_input is not None:
        frequencies = {m.mode_id: m.frequency_hz for m in evidence.modal_input.modes}
        threshold = evidence.suspension
        excluded = tuple(sorted(i for i, f in frequencies.items() if f < threshold.suspension_max_hz))
        eligibility = ExperimentalModeEligibility(ExperimentalQCStatus.PASS, threshold,
                                                  tuple(sorted(set(frequencies) - set(excluded))), excluded)
        try:
            eligibility.require_eligible(sorted({r.experimental_mode_id for r in pairing.rows
                                                 if r.experimental_mode_id in frequencies}))
        except ExperimentalModeEligibilityRefusal as refusal:
            reasons.append((RefusalCode.MODE_BELOW_SUSPENSION, str(refusal)))
    if reasons:
        raise StageAInputRefusal(tuple(reasons))


def _sigma(terms: Sequence[StageASigmaTerm], term_ids: tuple[str, ...]) -> tuple[ObservationCovariance, list]:
    if not terms or any(not isinstance(t, StageASigmaTerm) for t in terms):
        raise StageAValidationError("Σ needs at least one explicit StageASigmaTerm (no default Σ).")
    kinds = [t.kind for t in terms]
    if len(set(kinds)) != len(kinds):
        raise StageAValidationError("each Σ kind may appear once.")
    total = ObservationCovariance(term_ids, tuple(t.component for t in terms))  # validates shape and SPD
    return total, [t.component for t in terms]


def _fit_block(component: CovarianceComponent, n_fit: int) -> CovarianceComponent:
    return CovarianceComponent(component.name, tuple(tuple(row[:n_fit]) for row in component.matrix[:n_fit]),
                               component.provisional, component.provenance)


# ----------------------------------------------------------------------------- the adapter

def run_stage_a_validation(*, evidence: StageAExperimentalEvidence, pairing: StageAPairingEvidence,
                           forward: StageAForwardModel, sigma: Sequence[StageASigmaTerm], start: Mapping[str, float],
                           bounds: ParameterBounds, lm_settings: LMSettings, case_label: str) -> StageAValidationReport:
    """One real Stage-A validation run through the M5 machinery (no Abaqus, no M3, no override).

    ``start`` gives D11 and D66 (D12 starts on the governed ν12 line). ``bounds`` must bound D11, D12
    and D66. Raises ``StageAInputRefusal`` for incomplete or inadmissible inputs.
    """

    for name, value, kind in (("evidence", evidence, StageAExperimentalEvidence),
                              ("pairing", pairing, StageAPairingEvidence), ("forward", forward, StageAForwardModel),
                              ("bounds", bounds, ParameterBounds), ("lm_settings", lm_settings, LMSettings)):
        if not isinstance(value, kind):
            raise StageAValidationError(f"{name} must be a {kind.__name__}.")
    if not isinstance(case_label, str) or not case_label.strip():
        raise StageAValidationError("case_label required.")
    if set(start) != {D11, D66}:
        raise StageAValidationError("start gives exactly D11 and D66 (D12 starts at ν12·D11).")
    if set(bounds.names) != set(FULL_PARAMETERS):
        raise StageAValidationError("bounds must bound exactly D11, D12 and D66.")
    _admit(evidence, pairing, forward)

    term_ids = observation_term_ids(pairing)
    total, components = _sigma(sigma, term_ids)
    n_fit = len(pairing.fit_term_ids)
    fit_sigma = [_fit_block(c, n_fit) for c in components]
    frequencies = {m.mode_id: m.frequency_hz for m in evidence.modal_input.modes}
    step = lm_settings.finite_difference_step
    input_hashes = {"evidence": evidence.record_hash, "pairing": pairing.record_hash,
                    "forward": forward.identity_hash, "sigma": canonical_hash(total.to_dict()),
                    "lm_settings": canonical_hash({k: getattr(lm_settings, k)
                                                   for k in lm_settings.__dataclass_fields__}),
                    "bounds": canonical_hash({"names": list(bounds.names), "lower": list(bounds.lower),
                                              "upper": list(bounds.upper)}),
                    "start": canonical_hash({k: float(v) for k, v in sorted(start.items())})}
    base = dict(context=ResultContext.STAGE_A_VALIDATION, case_label=case_label,
                physical_specimen_id=evidence.physical_specimen_id, test_run_id=evidence.test_run_id,
                input_hashes=input_hashes)

    def refused(reasons, d12, lm, fitted=()):
        return StageAValidationReport(status=ValidationStatus.REFUSED, refusal_reasons=tuple(reasons), d12=d12, lm=lm,
                                      fitted_parameters=tuple(fitted), estimates=None, statistical_sd_ln=None,
                                      covariance_ln=None, birge=None, model_form_robustness=None,
                                      rank_diagnostics=None, derived=None, nu12_used=None, thickness_mean_mm=None,
                                      production_verdict=None, open_conditions=(), provisional_inputs=(), **base)

    try:
        problem = _StageAProblem(forward, pairing, frequencies, total.matrix(), start)
    except (MatrixModelError, BranchTrackingRefusal) as error:
        return refused((f"baseline FE state: {error}",), {}, {})

    def sub_bounds(fitted):
        index = {n: i for i, n in enumerate(bounds.names)}
        return ParameterBounds(tuple(fitted), tuple(bounds.lower[index[n]] for n in fitted),
                               tuple(bounds.upper[index[n]] for n in fitted))

    def fit(fitted, origin):
        lm = run_bounded_lm(lambda values: problem.whitened_fit(values, fitted), origin, sub_bounds(fitted),
                            lm_settings)
        return lm, {"status": lm.status.value, "parameters": list(fitted), "iterations": lm.iterations,
                    "evaluations": lm.solves, "objective": _r(lm.objective), "refusal": lm.refusal}

    start_full = {D11: float(start[D11]), D12: GOVERNED_NU12 * float(start[D11]), D66: float(start[D66])}
    d12_record: dict = {"policy": "fit D12 only when the full Stage-A system is practically full rank at rcond "
                                  "1e-3 (D-051)", "governed_nu12": GOVERNED_NU12,
                        "governed_nu12_source": GOVERNED_NU12_SOURCE}
    trace: dict = {"lm": {}}

    def estimate():
        lm_record = {}
        full_start = analyse_practical_identifiability(_system(problem, start_full, FULL_PARAMETERS, fit_sigma, step))
        d12_record["full_system_at_start"] = {"status": full_start.status.value, "rank": full_start.rank,
                                              "analysis_hash": full_start.record_hash,
                                              "refusal_reasons": list(full_start.refusal_reasons)}
        fitted, p_hat = FIXED_NU12_PARAMETERS, None
        if full_start.full_rank:
            lm, lm_record = fit(FULL_PARAMETERS, start_full)
            trace["lm"] = lm_record
            if lm.status is not LMStatus.CONVERGED:
                return refused((f"bounded LM (D11, D12, D66) ended {lm.status.value}"
                                + (f": {lm.refusal}" if lm.refusal else ""),), d12_record, lm_record, FULL_PARAMETERS)
            full_hat = analyse_practical_identifiability(_system(problem, lm.parameters, FULL_PARAMETERS, fit_sigma,
                                                                 step))
            d12_record["full_system_at_p_hat"] = {"status": full_hat.status.value, "rank": full_hat.rank,
                                                  "analysis_hash": full_hat.record_hash,
                                                  "refusal_reasons": list(full_hat.refusal_reasons)}
            if full_hat.full_rank:
                fitted, p_hat = FULL_PARAMETERS, dict(lm.parameters)
        if p_hat is None:
            d12_record["status"] = D12Status.NOT_IDENTIFIED.value
            d12_record["reason"] = ("the full Stage-A system is practically rank-deficient at rcond 1e-3: D12 is "
                                    "not identified; governed fixed-ν12 formulation D12 = ν12·D11 used (no "
                                    "pseudo-inverse, no override, no fallback pairing)")
            reduced_start = {D11: float(start[D11]), D66: float(start[D66])}
            reduced = analyse_practical_identifiability(_system(problem, reduced_start, FIXED_NU12_PARAMETERS,
                                                                fit_sigma, step))
            d12_record["fixed_nu12_system_at_start"] = {"status": reduced.status.value, "rank": reduced.rank,
                                                        "analysis_hash": reduced.record_hash,
                                                        "refusal_reasons": list(reduced.refusal_reasons)}
            if not reduced.full_rank:
                return refused(("practical rank deficiency of the governed (D11, D66) Stage-A system (SPEC §10 hard "
                                "block, no override): " + "; ".join(reduced.refusal_reasons),), d12_record, lm_record,
                               FIXED_NU12_PARAMETERS)
            lm, reduced_record = fit(FIXED_NU12_PARAMETERS, reduced_start)
            lm_record = {"full": lm_record, "fixed_nu12": reduced_record} if lm_record else reduced_record
            trace["lm"] = lm_record
            if lm.status is not LMStatus.CONVERGED:
                return refused((f"bounded LM (D11, D66; fixed ν12) ended {lm.status.value}"
                                + (f": {lm.refusal}" if lm.refusal else ""),), d12_record, lm_record,
                               FIXED_NU12_PARAMETERS)
            p_hat = dict(lm.parameters)
        else:
            d12_record["status"] = D12Status.FITTED.value

        # M5 evidence at p̂.
        system = _system(problem, p_hat, fitted, fit_sigma, step)
        fit_misfit, holdout_misfit = problem.misfit(p_hat, fitted)
        whitened = np.linalg.solve(problem.fit_lower, fit_misfit)
        families = {r.row_id: r.family for r in pairing.rows}
        fit_terms = residual_terms(pairing.single_fit_rows, pairing.clusters, list(whitened), families)
        holdout_terms = tuple(ResidualTerm(r.row_id, (r.row_id,), r.family, float(v / sd))
                              for r, v, sd in zip(pairing.holdout_rows, holdout_misfit, problem.holdout_sd))
        chain = compute_evidence_chain(system, fit_terms, holdout_terms, p_hat, f"{SCHEMA}:{case_label}")
        if not chain.analysis.full_rank:
            return refused(("practical rank deficiency of the Stage-A system at p̂ (SPEC §10 hard block): "
                            + "; ".join(chain.analysis.refusal_reasons),), d12_record, lm_record, fitted)
        return fitted, p_hat, chain, lm_record

    try:
        outcome = estimate()
    except BranchTrackingRefusal as error:
        return refused((f"FE-to-FE tracking refusal (D-008; no re-pairing): {error}",), d12_record, trace["lm"])
    if isinstance(outcome, StageAValidationReport):
        return outcome
    fitted, p_hat, chain, lm_record = outcome

    roles = {p: ParameterRole.GLOBAL for p in fitted}
    fit_macs = {r.row_id: float(r.mac) for r in pairing.fit_rows}
    verdict = decide_verdicts(VerdictInputs(
        context=VerdictContext.PRODUCTION, case_label=case_label, analysis=chain.analysis,
        statistical=chain.statistical, pattern=chain.pattern, birge=chain.birge, robustness=chain.robustness,
        fitting_pair_mac=fitting_pair_mac_evidence(fit_macs, f"pairing {pairing.record_hash[:16]}"),
        registration=GuardEvidence("registration", EvidenceState.FAIL if pairing.registration_limited
                                   else EvidenceState.PASS,
                                   f"M2 registration diagnostic ({pairing.registration_hash})"),
        peak_derived_input=GuardEvidence("peak_derived_input", EvidenceState.PASS,
                                         "M1.1 curve-fitted classification; frozen modal set "
                                         f"{evidence.modal_input.frozen_modal_set.modal_set_key}"),
        tracking=GuardEvidence("tracking", EvidenceState.PASS, "FE-to-FE tracking from the baseline pairing state "
                               "without refusal (D-008)"),
        family_consistency=GuardEvidence("family_consistency", EvidenceState.NOT_AVAILABLE,
                                         "production family consistency is M7 work (D-050)"),
        sandwich_g12=SandwichG12Evidence(False, EvidenceState.NOT_AVAILABLE, (), {},
                                         "not applicable: Stage-A bending stiffnesses of a bare plate"),
        p_hat=p_hat, parameter_roles=roles))
    if any(v.verdict is not Verdict.NOT_IDENTIFIABLE for v in verdict.verdicts.values()):
        raise AssertionError("STAGE_A_VALIDATION must never carry a production IDENTIFIED / WIDE verdict (D-050).")

    covariance = np.array(chain.analysis.covariance_ln, dtype=float)
    d11, d12, d66 = problem.physical(p_hat, fitted)
    nu = d12 / d11 if D12 in fitted else GOVERNED_NU12
    thickness = evidence.thickness
    t_mean = thickness.mean_mm
    t_m = t_mean / 1000.0
    spatial_ln = abs(THICKNESS_EXPONENT) * thickness.spatial_sd_mm / t_mean
    gauge_ln = None if thickness.gauge_uncertainty is None else \
        abs(THICKNESS_EXPONENT) * thickness.gauge_uncertainty.sd_mm / t_mean
    birge_factor = chain.birge.birge_factor if chain.birge.status is BirgeStatus.AVAILABLE else None
    coupling = 2.0 * nu * nu / (1.0 - nu * nu)  # ∂ln(1 − ν²)/∂ln D11 (= −∂/∂ln D12) when D12 is fitted
    gradients = {"E_flex_mpa": {D11: 1.0 + (coupling if D12 in fitted else 0.0), D12: -coupling, D66: 0.0},
                 "G12_flex_mpa": {D11: 0.0, D12: 0.0, D66: 1.0}}
    values = {"E_flex_mpa": 12.0 * d11 * (1.0 - nu * nu) / t_m ** 3 / 1.0e6,  # E = 12·D11·(1 − ν²)/t³
              "G12_flex_mpa": 12.0 * d66 / t_m ** 3 / 1.0e6}  # G12 = 12·D66/t³
    valid_cases = [] if chain.robustness is None else [c for c in chain.robustness.cases if c.shift_ln is not None]
    derived = {}
    for name, gradient in gradients.items():
        g = np.array([gradient[p] for p in fitted])
        frequency_sd = float(math.sqrt(g @ covariance @ g))
        shifts = [float(sum(gradient[p] * case.shift_ln[p] for p in fitted)) for case in valid_cases]
        half_range = 0.5 * (max(shifts) - min(shifts)) if shifts else None
        combined = math.sqrt(frequency_sd ** 2 + spatial_ln ** 2 + (gauge_ln or 0.0) ** 2)
        derived[name] = DerivedQuantity(name, values[name], THICKNESS_EXPONENT, frequency_sd,
                                        None if birge_factor is None else frequency_sd * birge_factor, spatial_ln,
                                        gauge_ln, combined, half_range)

    open_conditions = ["family consistency NOT_AVAILABLE: production verdict blocked until M7 (D-044, D-050)",
                       "M6.2 same-panel repeat agreement not yet evaluated (D-053)",
                       "specimen mass / plan-dimension uncertainties recorded but not propagated (M6 open item)"]
    if not any(t.kind is SigmaKind.MEASUREMENT for t in sigma):
        open_conditions.append("Sigma_meas NOT_AVAILABLE (not invented; D-053)")
    for item in chain.analysis.provisional_inputs:
        open_conditions.append(f"PROVISIONAL input {item}: final M6 acceptance requires measured M6.2 evidence")
    if thickness.gauge_uncertainty is None:
        open_conditions.append("gauge uncertainty not supplied: no gauge component (not invented; D-052)")
    if not chain.pattern.passed:
        open_conditions.append("residual-pattern test FAIL: " + "; ".join(chain.pattern.reasons))
    if chain.birge.status is not BirgeStatus.AVAILABLE:
        open_conditions.append(f"birge_adjusted_sd NOT_AVAILABLE ({chain.birge.status.value})")
    if chain.robustness is None or not chain.robustness.supports_green:
        open_conditions.append("model_form_robustness refused or unavailable")
    over = sorted(p for p, flag in chain.analysis.exceeds_sd_fit_limit.items() if flag)
    if over:
        open_conditions.append(f"statistical sd_ln above the SPEC §10 limit for {over}")
    mac = fitting_pair_mac_evidence(fit_macs, "pairing")
    if mac.state is not EvidenceState.PASS:
        open_conditions.append(f"fitting-pair MAC {mac.state.value}: {mac.detail}")
    if pairing.registration_limited:
        open_conditions.append("registration_limited (M2 diagnostic)")
    if d12_record["status"] == D12Status.NOT_IDENTIFIED.value:
        open_conditions.append("D12 not identified: governed fixed ν12 = 0.05 used (D-051)")

    analysis = chain.analysis
    robustness = None if chain.robustness is None else {
        "supports_green": chain.robustness.supports_green, "refused_families": list(chain.robustness.refused_families),
        "record_hash": chain.robustness.record_hash,
        "half_range_ln": {p: _r(0.5 * (v.max_shift_ln - v.min_shift_ln))
                          for p, v in sorted(chain.robustness.parameters.items())},
        "note": "linearised leave-one-family-out range (D-042); not statistical_sd, not 1 sigma"}
    return StageAValidationReport(
        status=ValidationStatus.ESTIMATE_REPORTED, refusal_reasons=(), d12=d12_record, lm=lm_record,
        fitted_parameters=tuple(fitted), estimates={p: float(p_hat[p]) for p in fitted},
        statistical_sd_ln=dict(chain.statistical.statistical_sd_ln),
        covariance_ln=analysis.covariance_ln,
        birge={"status": chain.birge.status.value, "birge_factor": _r(chain.birge.birge_factor),
               "chi2_per_dof": _r(chain.birge.chi2_per_dof), "dof": chain.birge.dof,
               "birge_adjusted_sd_ln": None if chain.birge.birge_adjusted_sd_ln is None else
               {k: _r(v) for k, v in sorted(chain.birge.birge_adjusted_sd_ln.items())},
               "record_hash": chain.birge.record_hash},
        model_form_robustness=robustness,
        rank_diagnostics={"status": analysis.status.value, "rank": analysis.rank, "rcond": analysis.rcond,
                          "singular_values": [_r(s) for s in analysis.singular_values],
                          "condition_number_diagnostic": _r(analysis.condition_number),
                          "correlation": [[_r(v) for v in row] for row in analysis.correlation],
                          "analysis_hash": analysis.record_hash, "statistical_hash": chain.statistical.record_hash,
                          "pattern_hash": chain.pattern.record_hash},
        derived=derived, nu12_used=nu, thickness_mean_mm=t_mean, production_verdict=verdict.to_dict(),
        open_conditions=tuple(open_conditions), provisional_inputs=tuple(analysis.provisional_inputs), **base)


# ----------------------------------------------------------------------------- M6.2 interface (estimator pending)

@dataclass(frozen=True)
class StageARepeatComparisonInputs:
    """ln-space inputs for the M6.2 same-plate comparison; the agreement rule is a later M6.2 decision (D-053)."""

    original_report_hash: str
    repeat_report_hash: str
    repeat_eligibility: str
    parameters: tuple[str, ...]
    ln_original: Mapping[str, float]
    ln_repeat: Mapping[str, float]
    ln_difference: Mapping[str, float]
    frequency_statistical_sd_ln_original: Mapping[str, float]
    frequency_statistical_sd_ln_repeat: Mapping[str, float]
    shared_thickness_record: Optional[str]  # common-mode quantity of the same plate: never counted as setup scatter
    status: str = "AGREEMENT_RULE_PENDING_M6_2_DECISION"


class SetupScatterEstimator(Protocol):
    """The M6.2 Σ_setup estimator, to be defined once real repeat data exist (D-053). Not implemented here."""

    def estimate(self, comparisons: Sequence[StageARepeatComparisonInputs]) -> Mapping[str, object]:
        ...


def stage_a_repeat_comparison_inputs(original: StageAValidationReport, repeat: StageAValidationReport,
                                     classification: SetupRepeatClassification,
                                     thickness_record_hashes: tuple[str, str]) -> StageARepeatComparisonInputs:
    """Pair two validation runs of the same plate in D (thickness-free) ln space; no pass/fail rule here."""
    for report in (original, repeat):
        if report.status is not ValidationStatus.ESTIMATE_REPORTED:
            raise StageAValidationError("both runs need a reported estimate.")
    if not classification.frequency_eligible:
        raise StageAValidationError("the runs are not an eligible same-panel repeat: "
                                    f"{classification.eligibility.value} "
                                    f"({'; '.join(classification.reasons)})")
    if (classification.original_run, classification.repeat_run) != (original.test_run_id, repeat.test_run_id):
        raise StageAValidationError("the repeat classification belongs to other runs.")
    if original.physical_specimen_id != repeat.physical_specimen_id:
        raise StageAValidationError("a setup repeat is the same physical specimen (SPEC §7).")
    if original.fitted_parameters != repeat.fitted_parameters:
        raise StageAValidationError("both runs must fit the same Stage-A parameters.")
    parameters = original.fitted_parameters
    ln_a = {p: math.log(original.estimates[p]) for p in parameters}
    ln_b = {p: math.log(repeat.estimates[p]) for p in parameters}
    shared = thickness_record_hashes[0] if thickness_record_hashes[0] == thickness_record_hashes[1] else None
    return StageARepeatComparisonInputs(original.record_hash, repeat.record_hash, classification.eligibility.value,
                                        parameters, ln_a, ln_b, {p: ln_b[p] - ln_a[p] for p in parameters},
                                        dict(original.statistical_sd_ln), dict(repeat.statistical_sd_ln), shared)
