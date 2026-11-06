"""REAL-FIT.R1: research-only frequency tuning of the CFRP input properties of an Abaqus plate model (no Qt, no Abaqus).

The owner asked to refine the ASSUMED orthotropic constants of the M11 plate model (``CFRP_S4R_0875_FreeFree.inp``) against
the measured PolyMAX frequencies. This module is a separate research tool. It does not use, change or bypass the governed
inverse workflow (``plate_material_workflow``), whose refusal of real data stays as it is, and it issues no material
property. Every result carries ``RESULT_LABEL``.

What it does, in order:

1. Reads the model's own inputs from the INP text: the material (``*Elastic, type=ENGINEERING CONSTANTS`` or ``LAMINA``),
   ``*Density``, the ``*Shell Section`` thickness and the plan extents of the part nodes. Nothing is assumed in code.
2. Converts them to homogeneous Kirchhoff bending stiffnesses: one orthotropic layer on the global axes (the INP has no
   ``*Orientation`` and no layup), plane stress, ``Q11 = E1/(1 - nu12 nu21)``, ``Q22 = E2/(1 - nu12 nu21)``,
   ``Q12 = nu12 E2/(1 - nu12 nu21)``, ``Q66 = G12``, ``nu21 = nu12 E2/E1`` and ``Dij = Qij t^3/12``. Transverse shear
   (G13, G23) and E3 are not in this plate theory: they stay as the INP has them.
3. Solves the free plate with the existing Kirchhoff-Ritz forward model (``plate_ritz_forward.solve_ritz``).
4. Compares that surrogate spectrum, by rank, with the elastic frequencies stored in the model's own ``.dat``.
5. Fits the selected experimental frequencies by bounded least squares on signed residuals ln(f_model / f_exp), under ONE
   declared correspondence hypothesis: the k-th fitted experimental frequency against a stated elastic rank of the
   surrogate (by default the same rank). This is a frequency hypothesis, never a mode pair.
6. Keeps HOLDOUT records out of the fit and reports their prediction, and reports the sensitivities d ln f / d ln p, the
   singular values, the condition number, the parameter correlation, active bounds and a check from several starts.

A candidate is issued only when the fit is numerically supported (converged, full practical rank, no active bound, the
starts agree). The candidate values are surrogate (Ritz) results: they are proposals for a new Abaqus solve, not FE results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Callable, Mapping, Optional, Sequence

import numpy as np
from scipy.optimize import least_squares

from domain.plate_material_problem import PlateBendingParameters, PlateGeometry
from services.plate_ritz_forward import RitzNumericalConfig, solve_ritz

RESULT_LABEL = "EXPLORATORY_FE_INPUT_CANDIDATE — NOT_A_MATERIAL_PROPERTY — NOT_VALIDATED_IN_ABAQUS"
SCHEMA = "research-frequency-tuning/1"
TIED, FREE = "E1=E2, G12", "E1, E2, G12"
PARAMETERIZATIONS = {TIED: ("E", "G12"), FREE: ("E1", "E2", "G12")}
RANK_ORDER, DECLARED = "RANK_ORDER_SPECTRUM", "DECLARED_CORRESPONDENCE"
SUPPORTED, NOT_IDENTIFIABLE, AT_BOUND, NOT_CONVERGED, STARTS_DISAGREE, CANCELLED = (
    "NUMERICALLY_SUPPORTED", "NOT_IDENTIFIABLE", "PARAMETER_AT_BOUND", "NOT_CONVERGED", "STARTS_DISAGREE", "CANCELLED")
MIRROR = "E1_E2_AXIS_ASSIGNMENT_NOT_IDENTIFIABLE"  # two minima with E1 and E2 exchanged: which plate axis is stiff is open
MIRROR_TOLERANCE = 0.05  # relative difference for "exchanged" (numerical policy)
MISFIT_RMS = 0.02  # FIT residual RMS (ln f) above which the parameterization does not reproduce the spectrum (diagnostic)
FIT, HOLDOUT, EXCLUDED = "FIT", "HOLDOUT", "EXCLUDED"
DEFAULT_STARTS = {TIED: ((1.0, 1.0), (0.5, 2.0), (2.0, 0.5)),
                  FREE: ((1.0, 1.0, 1.0), (0.6, 1.6, 1.0), (1.6, 0.6, 1.0), (0.8, 0.8, 2.0))}  # asymmetric: a mirror minimum shows
PRACTICAL_RANK_RATIO = 1.0e-3  # a singular value below this share of the largest does not count (numerical policy)
CONDITION_LIMIT = 1.0e3  # above it the parameters are reported as poorly distinguished (numerical policy)
START_AGREEMENT = 1.0e-3  # relative spread of the fitted parameters over the starts (numerical policy)
ASSUMPTIONS = (
    "The Kirchhoff-Ritz plate is a surrogate of the S4R shell model: no transverse shear, no rotary inertia.",
    "One homogeneous orthotropic layer on the global axes, as the INP defines it (no *Orientation, no layup).",
    "Thickness, density and nu12 are held at the INP values; E3, nu13, nu23, G13 and G23 are not part of the fit.",
    "The plate is free-free, as in the model. The test hung the plate on two strings at about 45 degrees with a shaker "
    "behind it; that suspension angle is not a fibre direction, and support stiffness is not in the model.",
    "That the 27 October test plate is the M11 model's specimen is an ASSUMPTION; it is not verified.",
    "Experimental frequencies are matched to the surrogate by a declared rank hypothesis, not by mode identity.",
)


class TuningRefused(ValueError):
    """The inputs cannot support the requested tuning; the message says why."""


# ---------------------------------------------------------------------------------------------- the model's own inputs


@dataclass(frozen=True)
class AbaqusPlateInputs:
    inp_path: str
    inp_sha256: str
    material: str
    elastic_type: str
    E1: float  # MPa (N/mm^2), as written
    E2: float
    E3: Optional[float]
    nu12: float
    nu13: Optional[float]
    nu23: Optional[float]
    G12: float
    G13: Optional[float]
    G23: Optional[float]
    density_t_mm3: float
    thickness_mm: float
    a_mm: float
    b_mm: float
    has_orientation: bool

    @property
    def mass_g(self) -> float:
        return self.density_t_mm3 * self.thickness_mm * self.a_mm * self.b_mm * 1.0e6

    def geometry(self) -> PlateGeometry:
        return PlateGeometry.from_units(self.a_mm, self.b_mm, "mm", surface_mass_kg_m2=self.density_t_mm3 * 1.0e12 * self.thickness_mm * 1.0e-3,
                                        thickness=self.thickness_mm)


def _numbers(lines: Sequence[str]) -> list:
    out = []
    for line in lines:
        out += [float(item) for item in line.replace(" ", "").split(",") if item.strip()]
    return out


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_inp(path) -> AbaqusPlateInputs:
    """The material, density, shell thickness and plan of a single-part, single-material shell plate INP. Read only."""
    path = Path(path)
    text = path.read_text(encoding="latin-1")
    lines = text.splitlines()
    keyword = [(i, line.strip()) for i, line in enumerate(lines) if line.startswith("*") and not line.startswith("**")]

    def data_after(index: int) -> list:
        out = []
        for line in lines[index + 1:]:
            if line.startswith("*"):
                break
            out.append(line)
        return out

    materials = [(i, k) for i, k in keyword if k.lower().startswith("*material")]
    if len(materials) != 1:
        raise TuningRefused(f"The INP holds {len(materials)} materials; this tool reads exactly one homogeneous material.")
    name = re.search(r"name\s*=\s*([^,]+)", materials[0][1], re.I).group(1).strip()
    elastic = density = section = None
    for i, k in keyword:
        low = k.lower()
        if low.startswith("*elastic") and i > materials[0][0]:
            elastic = (k, _numbers(data_after(i)))
        elif low.startswith("*density") and i > materials[0][0]:
            density = _numbers(data_after(i))
        elif low.startswith("*shell section"):
            if section is not None:
                raise TuningRefused("The INP holds more than one shell section.")
            section = (k, _numbers(data_after(i)[:1]))
    if elastic is None or density is None or section is None:
        raise TuningRefused("The INP has no *Elastic, *Density or *Shell Section to read.")
    kind = (re.search(r"type\s*=\s*([^,]+)", elastic[0], re.I) or [None, "ISOTROPIC"])[1].strip().upper()
    values = elastic[1]
    if kind == "ENGINEERING CONSTANTS" and len(values) >= 9:
        E1, E2, E3, nu12, nu13, nu23, G12, G13, G23 = values[:9]
    elif kind == "LAMINA" and len(values) >= 6:
        (E1, E2, nu12, G12, G13, G23), E3, nu13, nu23 = values[:6], None, None, None
    else:
        raise TuningRefused(f"*Elastic type {kind} with {len(values)} values is not an orthotropic definition this tool reads.")
    if "composite" in section[0].lower():
        raise TuningRefused("The shell section is a composite layup; this tool converts one homogeneous layer only.")
    nodes = []
    for i, k in keyword:
        if k.lower() == "*node":
            for line in data_after(i):
                parts = [p for p in line.split(",") if p.strip()]
                if len(parts) >= 3:
                    nodes.append((float(parts[1]), float(parts[2])))
            break
    if not nodes:
        raise TuningRefused("The INP has no *Node block for the plate plan.")
    xs, ys = [n[0] for n in nodes], [n[1] for n in nodes]
    return AbaqusPlateInputs(str(path), _sha(path), name, kind, E1, E2, E3, nu12, nu13, nu23, G12, G13, G23, density[0],
                             section[1][0], max(xs) - min(xs), max(ys) - min(ys),
                             any(k.lower().startswith("*orientation") for _i, k in keyword))


def read_dat_frequencies(path) -> tuple:
    """(mode, Hz) of the eigenvalue output table of an Abaqus .dat, as written. Read only."""
    rows = []
    text = Path(path).read_text(encoding="latin-1")
    start = text.find("E I G E N V A L U E    O U T P U T")
    if start < 0:
        raise TuningRefused("The .dat holds no eigenvalue output.")
    for line in text[start:].splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            try:
                rows.append((int(parts[0]), float(parts[3])))
            except ValueError:
                continue
        elif rows and ("P A R T I C I P A T I O N" in line or "E F F E C T I V E" in line):
            break
    if not rows:
        raise TuningRefused("No eigenvalue rows were found in the .dat.")
    return tuple(rows)


def elastic_fe_frequencies(rows, rigid_limit_hz: float = 1.0) -> tuple:
    """The elastic modes of a free model: the rigid-body ones are those near 0 Hz (the .dat's own values)."""
    return tuple((mode, hz) for mode, hz in rows if hz > rigid_limit_hz)


# ---------------------------------------------------------------------------------------------- constitutive conversion


def bending_stiffness(E1: float, E2: float, nu12: float, G12: float, thickness_mm: float) -> PlateBendingParameters:
    """Homogeneous orthotropic Kirchhoff plate, MPa and mm in, N*m out (1 N*mm = 1e-3 N*m)."""
    nu21 = nu12 * E2 / E1
    factor = 1.0 - nu12 * nu21
    if factor <= 0.0:
        raise TuningRefused("1 - nu12*nu21 must be positive.")
    t3 = thickness_mm ** 3 / 12.0 * 1.0e-3
    return PlateBendingParameters(D11=E1 / factor * t3, D22=E2 / factor * t3, D12=nu12 * E2 / factor * t3, D66=G12 * t3)


def _moduli(names: Sequence[str], values: Sequence[float], base: AbaqusPlateInputs) -> dict:
    found = dict(zip(names, values))
    if "E" in found:
        return {"E1": found["E"], "E2": found["E"], "G12": found["G12"]}
    return {"E1": found["E1"], "E2": found["E2"], "G12": found["G12"]}


# ---------------------------------------------------------------------------------------------- the surrogate


@dataclass(frozen=True)
class Surrogate:
    inputs: AbaqusPlateInputs
    degree: int = 14
    mode_count: int = 24

    def frequencies(self, E1: float, E2: float, G12: float) -> np.ndarray:
        config = RitzNumericalConfig(self.degree, self.degree, self.mode_count)
        stiffness = bending_stiffness(E1, E2, self.inputs.nu12, G12, self.inputs.thickness_mm)
        return np.asarray(solve_ritz(self.inputs.geometry(), stiffness, config).frequencies_hz, dtype=float)


def surrogate_discrepancy(surrogate: Surrogate, fe_elastic) -> tuple:
    """(rank, FE mode, FE Hz, Ritz Hz, Ritz/FE - 1) at the INP's own constants, by rank of the elastic spectra."""
    base = surrogate.inputs
    ritz = surrogate.frequencies(base.E1, base.E2, base.G12)
    return tuple((rank + 1, mode, hz, float(ritz[rank]), float(ritz[rank] / hz - 1.0))
                 for rank, (mode, hz) in enumerate(fe_elastic) if rank < ritz.size)


# ---------------------------------------------------------------------------------------------- the tuning


@dataclass(frozen=True)
class Observation:
    record: int  # the experimental record number, as read
    hz: float
    role: str  # FIT, HOLDOUT or EXCLUDED
    surrogate_rank: int  # 1-based elastic rank of the surrogate this frequency is compared with (the declared hypothesis)


@dataclass(frozen=True)
class TuningRequest:
    observations: tuple
    parameterization: str = TIED
    correspondence: str = RANK_ORDER
    lower_factor: float = 0.2  # bounds as factors of the INP values
    upper_factor: float = 5.0
    starts: tuple = ()  # start points as factors of the INP values, one per parameter; empty: DEFAULT_STARTS
    degree: int = 14

    def fit_rows(self) -> tuple:
        return tuple(o for o in self.observations if o.role == FIT)


def observations_by_rank(records: Sequence[tuple], holdout: Sequence[int] = (), excluded: Sequence[int] = (),
                         declared: Optional[Mapping[int, int]] = None) -> tuple:
    """Experimental (record, Hz) as observations. Rank hypothesis: the k-th lowest kept record against surrogate rank k;
    a declared mapping {record: rank} replaces it for the records it names."""
    kept = sorted((r for r in records if r[0] not in set(excluded)), key=lambda item: item[1])
    rows = []
    for rank, (record, hz) in enumerate(kept, start=1):
        target = (declared or {}).get(record, rank)
        rows.append(Observation(record, float(hz), HOLDOUT if record in set(holdout) else FIT, int(target)))
    rows += [Observation(record, float(hz), EXCLUDED, 0) for record, hz in records if record in set(excluded)]
    return tuple(sorted(rows, key=lambda o: o.record))


@dataclass
class TuningResult:
    status: str
    reasons: list
    label: str
    warnings: list
    request: dict
    inputs: dict
    parameter_names: tuple
    baseline: dict
    fitted: Optional[dict]  # the optimizer's point (all starts' best), always reported for diagnosis
    candidate: Optional[dict]  # only when numerically supported
    rows: list  # per observation: record, role, rank, exp, Ritz baseline, Ritz fitted, residual before/after (ln)
    sensitivity: list  # d ln f / d ln p, FIT rows, at the fitted point
    singular_values: list
    condition_number: Optional[float]
    practical_rank: int
    correlation: Optional[list]
    log_sd: Optional[dict]
    active_bounds: list
    starts: list
    rms_fit_before: float
    rms_fit_after: Optional[float]
    rms_holdout_before: Optional[float]
    rms_holdout_after: Optional[float]
    surrogate: list
    minima: list = field(default_factory=list)  # the distinct minima the starts reached, best first
    assumptions: tuple = ASSUMPTIONS
    evaluations: int = 0

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, **asdict(self)}


def _residuals(frequencies: np.ndarray, rows: Sequence[Observation]) -> np.ndarray:
    return np.array([math.log(frequencies[o.surrogate_rank - 1] / o.hz) for o in rows])


def run_tuning(inputs: AbaqusPlateInputs, request: TuningRequest, fe_elastic=(), cancel: Optional[threading.Event] = None,
               progress: Optional[Callable[[int], None]] = None) -> TuningResult:
    names = PARAMETERIZATIONS[request.parameterization]
    fit_rows = request.fit_rows()
    holdout_rows = tuple(o for o in request.observations if o.role == HOLDOUT)
    if len(fit_rows) <= len(names):
        raise TuningRefused(f"{len(fit_rows)} FIT frequencies cannot determine {len(names)} parameters; keep more than "
                            f"{len(names)} in the fit.")
    top = max(o.surrogate_rank for o in request.observations if o.role != EXCLUDED)
    surrogate = Surrogate(inputs, request.degree, max(top + 4, 12))
    base_values = {"E": inputs.E1, "E1": inputs.E1, "E2": inputs.E2, "G12": inputs.G12}
    if request.parameterization == TIED and inputs.E1 != inputs.E2:
        raise TuningRefused("E1 = E2 tying needs equal E1 and E2 in the INP; choose the three-parameter form.")
    base = np.array([math.log(base_values[n]) for n in names])
    lower = base + math.log(request.lower_factor)
    upper = base + math.log(request.upper_factor)
    count = [0]

    def spectrum(x: np.ndarray) -> np.ndarray:
        if cancel is not None and cancel.is_set():
            raise _Cancelled()
        count[0] += 1
        if progress is not None:
            progress(count[0])
        moduli = _moduli(names, np.exp(x), inputs)
        return surrogate.frequencies(moduli["E1"], moduli["E2"], moduli["G12"])

    def residual(x):
        return _residuals(spectrum(x), fit_rows)

    def jacobian(x, rows=fit_rows, step=1.0e-5):
        columns = []
        for j in range(x.size):
            up, down = x.copy(), x.copy()
            up[j] += step
            down[j] -= step
            columns.append((_residuals(spectrum(up), rows) - _residuals(spectrum(down), rows)) / (2 * step))
        return np.column_stack(columns)

    try:
        baseline_spectrum = spectrum(base)
        starts = []
        for factor in (request.starts or DEFAULT_STARTS[request.parameterization]):
            x0 = np.clip(base + np.log(np.asarray(factor, dtype=float)), lower + 1e-9, upper - 1e-9)
            solution = least_squares(residual, x0, jac=jacobian, bounds=(lower, upper), method="trf", x_scale=1.0,
                                     ftol=1e-14, xtol=1e-12, gtol=1e-12, max_nfev=200)
            starts.append({"start_factor": list(factor), "values": dict(zip(names, np.exp(solution.x).tolist())),
                           "cost": float(solution.cost), "status": int(solution.status), "message": solution.message,
                           "success": bool(solution.success), "x": solution.x})
        best = min(starts, key=lambda s: s["cost"])
        x = best["x"]
        fitted_spectrum = spectrum(x)
        J = jacobian(x)
    except _Cancelled:
        return _cancelled(inputs, request, names)
    singular = np.linalg.svd(J, compute_uv=False)
    rank = int(np.sum(singular > PRACTICAL_RANK_RATIO * singular[0])) if singular.size else 0
    condition = float(singular[0] / singular[-1]) if singular.size and singular[-1] > 0 else math.inf
    r_after = _residuals(fitted_spectrum, fit_rows)
    dof = len(fit_rows) - len(names)
    correlation = log_sd = None
    if rank == len(names):
        covariance = np.linalg.inv(J.T @ J) * float(r_after @ r_after) / dof
        sd = np.sqrt(np.diag(covariance))
        correlation = (covariance / np.outer(sd, sd)).round(6).tolist()
        log_sd = dict(zip(names, sd.tolist()))
    active = [n for n, v, lo, hi in zip(names, x, lower, upper) if v - lo < 1e-6 or hi - v < 1e-6]
    spread = max(float(np.max(np.abs(np.exp(s["x"] - x) - 1.0))) for s in starts)
    reasons = []
    if not all(s["success"] for s in starts):
        reasons.append("A start did not converge: " + "; ".join(s["message"] for s in starts if not s["success"]))
    if rank < len(names):
        reasons.append(f"Practical rank {rank} of {len(names)}: the FIT frequencies cannot separate the parameters.")
    if condition > CONDITION_LIMIT:
        reasons.append(f"Condition number {condition:.3g} exceeds {CONDITION_LIMIT:g}: the parameters are poorly distinguished.")
    if active:
        reasons.append("At a bound: " + ", ".join(active) + ". The minimum lies outside the allowed range.")
    if spread > START_AGREEMENT:
        reasons.append(f"The starts end {spread:.2%} apart: the minimum is not unique within the bounds.")
    minima = []
    for item in sorted(starts, key=lambda s: s["cost"]):
        if not any(float(np.max(np.abs(np.exp(item["x"] - m["x"]) - 1.0))) <= START_AGREEMENT for m in minima):
            minima.append(item)
    mirror = (len(minima) == 2 and "E1" in names and all(
        abs(minima[0]["values"][a] / minima[1]["values"][b] - 1.0) <= MIRROR_TOLERANCE
        for a, b in (("E1", "E2"), ("E2", "E1"), ("G12", "G12"))))
    if mirror:
        reasons = [r for r in reasons if not r.startswith("The starts end")]
        reasons.append("Two minima with E1 and E2 exchanged fit almost equally (costs " + ", ".join(
            f"{m['cost']:.6g}" for m in minima) + "): the frequencies support a stiff and a soft in-plane direction but not "
            "which plate axis (FE X or Y) is which. That needs the physical orientation of the test plate.")
    status = (MIRROR if mirror else NOT_CONVERGED if reasons and reasons[0].startswith("A start") else NOT_IDENTIFIABLE if rank < len(names)
              or condition > CONDITION_LIMIT else AT_BOUND if active else STARTS_DISAGREE if spread > START_AGREEMENT else SUPPORTED)
    fitted = {k: float(v) for k, v in _moduli(names, np.exp(x), inputs).items()}
    rows = []
    for o in request.observations:  # (built before the warnings above use them)
        if o.role == EXCLUDED:
            rows.append({"record": o.record, "role": o.role, "rank": None, "exp_hz": o.hz, "ritz_before_hz": None,
                         "ritz_after_hz": None, "ln_before": None, "ln_after": None})
            continue
        before, after = float(baseline_spectrum[o.surrogate_rank - 1]), float(fitted_spectrum[o.surrogate_rank - 1])
        rows.append({"record": o.record, "role": o.role, "rank": o.surrogate_rank, "exp_hz": o.hz, "ritz_before_hz": before,
                     "ritz_after_hz": after, "ln_before": math.log(before / o.hz), "ln_after": math.log(after / o.hz)})

    def rms(role, key):
        values = [r[key] for r in rows if r["role"] == role]
        return float(np.sqrt(np.mean(np.square(values)))) if values else None

    warnings = []
    fit_rms = float(np.sqrt(np.mean(np.square(r_after))))
    if fit_rms > MISFIT_RMS:
        warnings.append(f"FIT residual RMS {fit_rms:.2%} in ln f exceeds {MISFIT_RMS:.0%}: this parameterization does not "
                        "reproduce the measured spectrum, and its values absorb model-form error.")
    if any(abs(r["ln_after"]) > 0.05 for r in rows if r["role"] == HOLDOUT):
        warnings.append("A HOLDOUT frequency is predicted more than 5 % off after the fit.")
    return TuningResult(
        status=status, reasons=reasons, label=RESULT_LABEL, warnings=warnings,
        request={"parameterization": request.parameterization, "correspondence": request.correspondence,
                 "bounds_factor": [request.lower_factor, request.upper_factor], "starts": [list(f) for f in (request.starts or DEFAULT_STARTS[request.parameterization])],
                 "ritz_degree": request.degree, "observations": [asdict(o) for o in request.observations]},
        inputs=asdict(inputs), parameter_names=names,
        baseline={"E1": inputs.E1, "E2": inputs.E2, "G12": inputs.G12, "nu12": inputs.nu12},
        fitted={**fitted, "nu12": inputs.nu12}, candidate=({**fitted, "nu12": inputs.nu12} if status == SUPPORTED else None),
        rows=rows, sensitivity=[dict(zip(names, row)) | {"record": o.record} for o, row in zip(fit_rows, J.tolist())],
        singular_values=singular.tolist(), condition_number=condition, practical_rank=rank, correlation=correlation,
        log_sd=log_sd, active_bounds=active,
        starts=[{k: v for k, v in s.items() if k != "x"} for s in starts],
        rms_fit_before=rms(FIT, "ln_before"), rms_fit_after=rms(FIT, "ln_after"),
        rms_holdout_before=rms(HOLDOUT, "ln_before"), rms_holdout_after=rms(HOLDOUT, "ln_after"),
        surrogate=[{"rank": r[0], "fe_mode": r[1], "fe_hz": r[2], "ritz_hz": r[3], "ritz_over_fe_minus_1": r[4]}
                   for r in surrogate_discrepancy(surrogate, fe_elastic)] if fe_elastic else [],
        minima=[{"values": dict(m["values"]), "cost": m["cost"]} for m in minima], evaluations=count[0])


class _Cancelled(Exception):
    pass


def _cancelled(inputs, request, names) -> TuningResult:
    return TuningResult(CANCELLED, ["Cancelled before the fit finished."], RESULT_LABEL, [], {}, asdict(inputs), names,
                        {"E1": inputs.E1, "E2": inputs.E2, "G12": inputs.G12, "nu12": inputs.nu12}, None, None, [], [], [],
                        None, 0, None, None, [], [], 0.0, None, None, None, [])


def abaqus_elastic_line(inputs: AbaqusPlateInputs, candidate: Mapping[str, float]) -> str:
    """The *Elastic data a new Abaqus solve would use: the candidate E1, E2, G12; every other constant as in the INP."""
    if inputs.elastic_type == "ENGINEERING CONSTANTS":
        return (f"*Elastic, type=ENGINEERING CONSTANTS\n{candidate['E1']:.6g}, {candidate['E2']:.6g}, {inputs.E3:.6g}, "
                f"{inputs.nu12:.6g}, {inputs.nu13:.6g}, {inputs.nu23:.6g}, {candidate['G12']:.6g}, {inputs.G13:.6g}\n"
                f"{inputs.G23:.6g},")
    return (f"*Elastic, type=LAMINA\n{candidate['E1']:.6g}, {candidate['E2']:.6g}, {inputs.nu12:.6g}, {candidate['G12']:.6g}, "
            f"{inputs.G13:.6g}, {inputs.G23:.6g}")


def export_document(result: TuningResult, inputs: AbaqusPlateInputs, sources: Mapping[str, str]) -> dict:
    """Everything needed to reproduce and review the proposal; the Abaqus lines only when a candidate exists."""
    document = result.to_dict()
    document["sources"] = dict(sources)
    document["abaqus_elastic_candidate"] = abaqus_elastic_line(inputs, result.candidate) if result.candidate else None
    document["statement"] = ("Surrogate (Kirchhoff-Ritz) result. The candidate is a proposal for a new Abaqus solve, not an FE "
                             "result, not a material property and not a calibration. " + RESULT_LABEL)
    return document


def write_export(document: dict, path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(document, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    return path


__all__ = ["ASSUMPTIONS", "AbaqusPlateInputs", "DECLARED", "FIT", "FREE", "HOLDOUT", "EXCLUDED", "Observation",
           "PARAMETERIZATIONS", "RANK_ORDER", "RESULT_LABEL", "SUPPORTED", "Surrogate", "TIED", "TuningRefused",
           "TuningRequest", "TuningResult", "abaqus_elastic_line", "bending_stiffness", "elastic_fe_frequencies",
           "export_document", "observations_by_rank", "read_dat_frequencies", "read_inp", "run_tuning",
           "surrogate_discrepancy", "write_export"]
