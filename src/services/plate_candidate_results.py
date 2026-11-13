"""PLATE-CANDIDATES: FE-model parameter candidates of the M11 CFRP plate, calculated from the measured frequencies
(no Qt; RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY / LINEAR_APPROXIMATION).

The calculation is the PRIORITY-3 research fit, moved here unchanged so that the interface and
``research/plate_inverse/run_inverse.py`` run one implementation:

- the optimiser is the project's ``services.identification_step.run_bounded_lm`` (no second optimiser);
- the forward model is the log-linear approximation built from the PRIORITY-2 central sensitivities of the M11 S4R
  model (six real Abaqus ±5 % solves; ``CENTRAL_SENSITIVITIES.csv``, read only with its recorded SHA-256):

      ln f_t(p) = ln f_t0 + Σ_j s_tj · ln(p_j / p_j0),   p0 = (E1, E2, G12) = (56 000, 56 000, 5 000) MPa

- the scenarios S0, H1 and H2 are declared before any fit. Each names its correspondences EXP ↔ FE as HYPOTHESES;
  every scenario keeps EXP1 ↔ FE7. No record is paired by its nearest frequency, MAC is not an input, and no
  orientation, scenario or value is chosen;
- bounds: every fitted parameter in [0.5, 2] × its baseline value. The run is deterministic and offline: an
  evaluation is an evaluation of the approximation, never an Abaqus solve.

``calculate`` takes the measured frequencies of the modal set the user read (``{record number: Hz}``). Nothing in the
answer comes from an archive. The archived PRIORITY-3 / PRIORITY-4 records are read apart (``load_archive``) and only
compared with the calculation (``compare_with_archive``): a regression check, and the archived Abaqus solves of the
archived parameter sets, shown as such.

A parameter that the rows do not constrain is reported as a limitation, with the range of candidates the model
supports where one exists; it is never given a unique value. A rank-deficient or ambiguous scenario is refused with
its reason and gives no number.

``verify_sources`` ties the calculation to the files read: the experimental file by its SHA-256, the modal set by its
name and its records, the FE package by the SHA-256 of its manifest and by the baseline frequency of every FE term of
the sensitivity table. ``export`` writes each calculated candidate as CSV and TXT for a manual Abaqus check.

M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
import io
import math
import os
from pathlib import Path
import tempfile
from typing import Optional

import numpy as np

from services import identification_step as st
from services import plate_study as ps
from services import research_results_reader as rr

# ------------------------------------------------------------------------------------ the research fit (PRIORITY-3)

P0 = {"E1": 56000.0, "E2": 56000.0, "G12": 5000.0}
SIGMA_LN = 0.003  # the provisional scale of the design studies; not a measured uncertainty
BOUND_FACTOR = (0.5, 2.0)
LINEAR_RANGE = 0.05  # the ±5 % of the central differences: outside it the approximation is an extrapolation
RCOND = 1e-3
SETTINGS = st.LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=8, solve_budget=200,
                         max_iterations=50)  # evaluations of the approximation, not solves
LABELS = ["RESEARCH_ONLY", "HYPOTHETICAL_PAIRING", "NOT_A_MATERIAL_PROPERTY", "LINEAR_APPROXIMATION"]
PARAMETERS = ("E1", "E2", "G12")
KEPT_PAIR = (1, "FE7")  # EXP1 ↔ FE7: kept by every scenario
WINDOW_PERCENT = 15.0  # the frequency window of the PRIORITY-1 matching
CLOSE_PERCENT = 3.0  # the project's close-group trigger
BASELINE_MEMBER = "S4R_0875_BASELINE"
FE_TOLERANCE_HZ = 1.0e-4  # the sensitivity table holds the baseline frequencies to 5 decimals
ARCHIVE_TOLERANCE_MPA = 0.051  # the archive holds the parameters to 0.1 MPa
CONVERGED = "CONVERGED"
REFUSED_RANK = "REFUSED_RANK_DEFICIENT"
REFUSED_PAIRING = "REFUSED_PAIRING"


@dataclass(frozen=True)
class Scenario:
    key: str
    pairs: tuple  # (EXP number, FE term)
    parameters: tuple  # fitted parameters: "G12", or "E" (E1 = E2 = E) and "G12"
    note: str


SCENARIOS = (
    Scenario("S0", ((1, "FE7"),), ("G12",), "one-mode research problem; E1, E2 fixed at 56 000 MPa"),
    Scenario("H1", ((1, "FE7"), (8, "FE15+FE16")), ("E", "G12"),
             "EXP8 lies in the FE15/FE16 span (two-mode subspace 0.92, single MAC 0.43): a hypothesis, not a pair"),
    Scenario("H2", ((1, "FE7"), (7, "FE14")), ("E", "G12"),
             "stress test: EXP7 ↔ FE14 research MAC 0.79 < 0.80 and |Δf| 15.5 % > the 15 % window"),
)


class Refused(RuntimeError):
    """The sensitivity table is missing or changed; nothing is calculated."""


class ArchiveRefused(ValueError):
    """An archived record is missing, changed or inconsistent; it is not compared."""


class SourceMismatch(ValueError):
    """The files read are not the sources of this calculation; ``reasons`` lists every difference."""

    def __init__(self, reasons):
        self.reasons = tuple(reasons)
        super().__init__("; ".join(self.reasons))


def _committed(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")  # the committed (LF) form, whatever the checkout wrote


def load_sensitivities(root: Path = rr.REPO) -> dict:
    """{FE term: f0, s_E1, s_E2, s_G12} of the PRIORITY-2 table; ``Refused`` on another content."""
    relative, expected, _commit = rr.SNAPSHOT_FILES["SENSITIVITIES"]
    path = Path(root) / relative
    if not path.is_file():
        raise Refused(f"{relative} is missing")
    data = _committed(path)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise Refused(f"{relative}: SHA-256 {digest[:12]}… is not the PRIORITY-2 table {expected[:12]}…")
    out = {}
    for row in csv.DictReader(io.StringIO(data.decode("utf-8"))):
        if row["s_E1"] in ("", None) or row["s_G12"] in ("", None):
            continue  # a branch that lost identity has no central value; nothing is guessed
        out[row["term"]] = {"f0": float(row["f_baseline_hz"]), "E1": float(row["s_E1"]), "E2": float(row["s_E2"]),
                            "G12": float(row["s_G12"])}
    return out


def full_parameters(fitted: dict) -> dict:
    """E1, E2, G12 from the fitted set ('E' means E1 = E2 = E)."""
    p = dict(P0)
    if "E" in fitted:
        p["E1"] = p["E2"] = fitted["E"]
    for key in PARAMETERS:
        if key in fitted:
            p[key] = fitted[key]
    return p


def predict(sens: dict, term: str, p: dict) -> float:
    s = sens[term]
    return s["f0"] * math.exp(sum(s[j] * math.log(p[j] / P0[j]) for j in PARAMETERS))


def jacobian_rows(sens: dict, terms, parameters) -> np.ndarray:
    rows = []
    for t in terms:
        s = sens[t]
        rows.append([s["E1"] + s["E2"] if name == "E" else s[name] for name in parameters])
    return np.array(rows)


def rank_report(S: np.ndarray) -> dict:  # noqa: N803
    sv = np.linalg.svd(S, compute_uv=False)
    rank = int(np.sum(sv > RCOND * sv[0])) if sv.size and sv[0] > 0 else 0
    return {"singular_values": [float(v) for v in sv], "rank": rank,
            "condition": float(sv[0] / sv[-1]) if sv[-1] > 0 else math.inf}


def fit(scenario: Scenario, sens: dict, f_exp: dict) -> dict:
    terms = [t for _e, t in scenario.pairs]
    S_fit = jacobian_rows(sens, terms, scenario.parameters)  # noqa: N806
    S_3 = jacobian_rows(sens, terms, PARAMETERS)  # noqa: N806
    out = {"scenario": scenario.key, "pairs": [f"EXP{e} ↔ {t}" for e, t in scenario.pairs],
           "fitted_parameters": list(scenario.parameters), "note": scenario.note, "labels": LABELS,
           "rank_fitted": rank_report(S_fit), "rank_E1_E2_G12": rank_report(S_3)}
    if out["rank_fitted"]["rank"] < len(scenario.parameters):
        out.update(status=REFUSED_RANK, reason=f"rank {out['rank_fitted']['rank']} < "
                   f"{len(scenario.parameters)} fitted parameters: no number is given")
        return out

    def residuals(q):
        p = full_parameters(q)
        return np.array([(math.log(predict(sens, t, p)) - math.log(f_exp[e])) / SIGMA_LN for e, t in scenario.pairs])

    start = {n: (P0["E1"] if n == "E" else P0[n]) for n in scenario.parameters}
    bounds = st.parameter_bounds([(n, v * BOUND_FACTOR[0], v * BOUND_FACTOR[1]) for n, v in start.items()])
    try:
        result = st.run_bounded_lm(residuals, start, bounds, SETTINGS)
    except st.StepError as error:
        out.update(status="REFUSED_STEP_ERROR", reason=str(error))
        return out
    p = full_parameters(result.parameters)
    at_bound = [n for n, low, high in zip(bounds.names, bounds.lower, bounds.upper)
                if math.isclose(result.parameters[n], low, rel_tol=1e-9)
                or math.isclose(result.parameters[n], high, rel_tol=1e-9)]
    # the same equations solved directly (an independent check of the LM; exact for a square full-rank system)
    b = np.array([math.log(f_exp[e] / sens[t]["f0"]) for e, t in scenario.pairs])
    direct = np.linalg.lstsq(S_fit, b, rcond=None)[0]
    ratios = {n: result.parameters[n] / start[n] for n in scenario.parameters}
    beyond = {n: r for n, r in ratios.items() if abs(math.log(r)) > math.log(1 + LINEAR_RANGE)}
    out.update(status=result.status.value, refusal=result.refusal, evaluations=result.solves,
               iterations=result.iterations, objective=result.objective, parameters=p, ratios=ratios,
               at_bound=at_bound, direct_solution_ratios={n: float(math.exp(v))
                                                         for n, v in zip(scenario.parameters, direct)},
               local_sd_ln=list(result.local_sd) if result.local_sd else None,
               extrapolation_beyond_5_percent=beyond,
               residuals=[{"exp": e, "term": t, "f_exp": f_exp[e], "f0": sens[t]["f0"],
                           "f_fit": predict(sens, t, p),
                           "error_before_percent": 100 * (sens[t]["f0"] / f_exp[e] - 1),
                           "error_after_percent": 100 * (predict(sens, t, p) / f_exp[e] - 1)}
                          for e, t in scenario.pairs])
    return out


# ------------------------------------------------------------------------------------ the candidates of one set

@dataclass(frozen=True)
class Residual:
    """One declared, HYPOTHETICAL correspondence with its frequencies (never a verified pair)."""

    exp: int
    term: str
    f_exp_hz: float
    f_baseline_hz: float
    f_predicted_hz: float
    before_percent: float  # 100 × (f_FE baseline / f_EXP − 1)
    after_percent: float  # 100 × (f_FE predicted / f_EXP − 1)


@dataclass(frozen=True)
class ArchiveComparison:
    """The archived record of the same scenario, beside the calculation (never its source)."""

    E1: float  # noqa: N815
    E2: float  # noqa: N815
    G12: float  # noqa: N815
    largest_difference_mpa: Optional[float]  # calculated − archived; None when nothing was calculated
    reproduced: bool  # the calculation equals the archived set to the archive's 0.1 MPa
    abaqus_rows: tuple  # (hypothesis, measured Hz, archived Abaqus Hz, archived residual %)
    tracking: str
    solve: str


@dataclass(frozen=True)
class Candidate:
    key: str
    pairs: tuple  # (EXP number, FE term): hypotheses
    fitted: tuple
    note: str
    status: str
    reason: str = ""
    E1: Optional[float] = None  # noqa: N815  (MPa)
    E2: Optional[float] = None  # noqa: N815
    G12: Optional[float] = None  # noqa: N815
    ratios: dict = field(default_factory=dict)
    at_bound: tuple = ()
    beyond: dict = field(default_factory=dict)
    rank_fitted: int = 0
    condition: float = math.inf
    rank_full: int = 0
    objective: Optional[float] = None
    evaluations: Optional[int] = None
    direct_ratios: dict = field(default_factory=dict)
    residuals: tuple = ()
    predictions: tuple = ()  # (FE term, baseline Hz, predicted Hz) of every tracked term: FE values only
    warnings: tuple = ()
    limitations: tuple = ()
    g12_range_mpa: Optional[tuple] = None  # the supported range of G12 when E is not constrained
    archive: Optional[ArchiveComparison] = None

    @property
    def calculated(self) -> bool:
        return self.E1 is not None

    @property
    def pairs_text(self) -> str:
        return "; ".join(f"EXP{e} ↔ {t}" for e, t in self.pairs)


@dataclass(frozen=True)
class CandidateSet:
    candidates: tuple
    experiment: tuple  # (record number, measured Hz) of the modal set read
    fixed: dict  # the FE model's constants that are not fitted
    fe_member: str
    across: tuple  # what the scenarios say together (no choice)
    archive_note: str = ""
    checks: tuple = ()

    def candidate(self, key: str) -> Candidate:
        return next(c for c in self.candidates if c.key == key)


def _members(term: str) -> set:
    return set(term.split("+"))


def pairing_problems(scenario: Scenario, sens: dict, f_exp: dict) -> tuple:
    """Why the declared hypotheses cannot be used as they are (empty when they can). Nothing is re-paired."""
    problems = []
    exps = [e for e, _t in scenario.pairs]
    terms = [t for _e, t in scenario.pairs]
    if KEPT_PAIR not in scenario.pairs:
        problems.append(f"the scenario does not keep EXP{KEPT_PAIR[0]} ↔ {KEPT_PAIR[1]}")
    for e in sorted(set(exps)):
        if exps.count(e) > 1:
            problems.append(f"EXP{e} is assigned to {exps.count(e)} FE terms: an ambiguous pairing")
        if e not in f_exp:
            problems.append(f"EXP{e} is not a record of the modal set read")
        elif not (math.isfinite(f_exp[e]) and f_exp[e] > 0):
            problems.append(f"EXP{e} has no positive finite frequency")
    for index, t in enumerate(terms):
        if t not in sens:
            problems.append(f"{t} has no central sensitivity (its branch identity was lost or it is not an FE term "
                            "of the table): nothing is guessed")
        if any(_members(t) & _members(other) for other in terms[index + 1:]):
            problems.append(f"{t} shares an FE mode with another term of the scenario: an ambiguous pairing")
    return tuple(problems)


def _g12_range(sens: dict, pair, f_exp: dict) -> Optional[tuple]:
    """G12 that fits the one row for E1 = E2 at the two declared bounds of E (the model's null direction)."""
    e, t = pair
    s = sens[t]
    if abs(s["G12"]) < 1e-12:
        return None
    b = math.log(f_exp[e] / s["f0"])
    values = [P0["G12"] * math.exp((b - (s["E1"] + s["E2"]) * math.log(factor)) / s["G12"]) for factor in BOUND_FACTOR]
    low, high = P0["G12"] * BOUND_FACTOR[0], P0["G12"] * BOUND_FACTOR[1]
    return tuple(sorted(min(max(v, low), high) for v in values))


def _candidate(scenario: Scenario, sens: dict, f_exp: dict) -> Candidate:
    problems = pairing_problems(scenario, sens, f_exp)
    if problems:
        return Candidate(scenario.key, scenario.pairs, scenario.parameters, scenario.note, REFUSED_PAIRING,
                         "; ".join(problems) + ": no number is given")
    r = fit(scenario, sens, f_exp)
    rank, full = r["rank_fitted"], r["rank_E1_E2_G12"]
    if "parameters" not in r:
        return Candidate(scenario.key, scenario.pairs, scenario.parameters, scenario.note, r["status"],
                         r.get("reason", ""), rank_fitted=rank["rank"], condition=rank["condition"],
                         rank_full=full["rank"],
                         limitations=(f"The {len(scenario.pairs)} declared row(s) give rank {rank['rank']} for the "
                                      f"{len(scenario.parameters)} fitted parameter(s): they do not determine a "
                                      "unique value, so none is given.",))
    p = r["parameters"]
    residuals = tuple(Residual(x["exp"], x["term"], x["f_exp"], x["f0"], x["f_fit"], x["error_before_percent"],
                               x["error_after_percent"]) for x in r["residuals"])
    predictions = tuple((term, sens[term]["f0"], predict(sens, term, p)) for term in sens)
    warnings = [f"Every correspondence is a hypothesis: {scenario.note}."]
    if r["status"] != CONVERGED:
        warnings.append(f"The optimiser ended with {r['status']}" + (f" ({r['refusal']})" if r.get("refusal") else "")
                        + ": the values are its last accepted point, not a converged fit.")
    for name, ratio in r["extrapolation_beyond_5_percent"].items():
        warnings.append(f"EXTRAPOLATION: {name} ×{ratio:.4f} lies outside the ±5 % that the sensitivities were "
                        "solved for; the predicted frequencies are an extrapolation of the log-linear model.")
    for name in r["at_bound"]:
        warnings.append(f"AT A BOUND: {name} stopped at a declared bound ({BOUND_FACTOR[0]:g}–{BOUND_FACTOR[1]:g} × "
                        "the baseline); the value is the bound, not a fit.")
    if len(scenario.pairs) == len(scenario.parameters):
        warnings.append(f"As many frequencies as fitted parameters ({len(scenario.pairs)}): the residuals are zero "
                        "by construction and do not test the hypothesis.")
    for x in residuals:
        if abs(x.before_percent) > WINDOW_PERCENT:
            warnings.append(f"EXP{x.exp} ↔ {x.term}: the baseline FE frequency is {x.before_percent:+.2f} % from the "
                            f"record, outside the {WINDOW_PERCENT:g} % window of the mode matching.")
        for term, _f0, predicted in predictions:
            if _members(term) & _members(x.term):
                continue
            distance = 100 * (predicted / x.f_exp_hz - 1)
            if abs(distance) <= CLOSE_PERCENT:
                warnings.append(f"AMBIGUITY: at this solution {term} is predicted at {predicted:.3f} Hz, "
                                f"{distance:+.2f} % from EXP{x.exp}; the frequency alone cannot tell it from "
                                f"{x.term}.")
    limitations, g12_range = [], None
    if "E" not in scenario.parameters and "E1" not in scenario.parameters:
        g12_range = _g12_range(sens, scenario.pairs[0], f_exp) if len(scenario.pairs) == 1 else None
        text = (f"E1 and E2 are NOT determined: they are kept at the FE model's {P0['E1']:.0f} MPa by assumption, "
                f"and the row(s) give rank {full['rank']} of 3 for E1 / E2 / G12.")
        if g12_range is not None:
            text += (f" Were E1 = E2 anywhere in the declared bounds {P0['E1'] * BOUND_FACTOR[0]:.0f}–"
                     f"{P0['E1'] * BOUND_FACTOR[1]:.0f} MPa, the same record would be fitted by G12 from "
                     f"{g12_range[0]:.1f} to {g12_range[1]:.1f} MPa (log-linear model, an extrapolation outside "
                     "±5 %). This is the supported range of candidates, not an uncertainty interval.")
        limitations.append(text)
    if "E" in scenario.parameters:
        limitations.append(f"E1 = E2 is imposed: the rows give rank {full['rank']} of 3 for E1 / E2 / G12, so E1 and "
                           "E2 are not separable and no separate values are given.")
    limitations.append("The other constants of the FE model (E3, ν, G13, G23, density, thickness) are fixed inputs, "
                       "not results.")
    return Candidate(scenario.key, scenario.pairs, scenario.parameters, scenario.note, r["status"], "",
                     p["E1"], p["E2"], p["G12"], dict(r["ratios"]), tuple(r["at_bound"]),
                     dict(r["extrapolation_beyond_5_percent"]), rank["rank"], rank["condition"], full["rank"],
                     r["objective"], r["evaluations"], dict(r["direct_solution_ratios"]), residuals, predictions,
                     tuple(warnings), tuple(limitations), g12_range)


def baseline_member():
    return next((m for m in ps.PLATE_FE_FAMILY if m.member_id == BASELINE_MEMBER), None)


def calculate(f_exp: dict, sens: Optional[dict] = None, scenarios=SCENARIOS, checks=()) -> CandidateSet:
    """The candidates of every declared scenario from the measured frequencies ``{record number: Hz}``."""
    sens = load_sensitivities() if sens is None else sens
    f_exp = {int(k): float(v) for k, v in f_exp.items()}
    member = baseline_member()
    parameters = dict(member.parameters) if member is not None else {}
    different = [n for n in PARAMETERS if n in parameters and parameters[n] != P0[n]]
    if different:
        raise Refused(f"the baseline FE model's {', '.join(different)} are not the base point of the sensitivities")
    candidates = tuple(_candidate(s, sens, f_exp) for s in scenarios)
    done = [c for c in candidates if c.calculated]
    across = []
    if len(done) > 1:
        for name in PARAMETERS:
            values = [getattr(c, name) for c in done]
            across.append(f"{name}: {min(values):.1f}–{max(values):.1f} MPa over {', '.join(c.key for c in done)} — "
                          "the spread of different hypotheses and assumptions, not an uncertainty interval")
        across.append("No scenario is preferred: a small residual of a square system is not evidence for its "
                      "hypothesis.")
    return CandidateSet(candidates, tuple(sorted(f_exp.items())),
                        {k: v for k, v in parameters.items() if k not in PARAMETERS},
                        member.member_id if member is not None else "", tuple(across), checks=tuple(checks))


def verify_sources(sens: dict, experimental_sha256, set_names, record_numbers, fe_manifest_sha256,
                   fe_frequencies_hz, scenarios=SCENARIOS) -> tuple:
    """(identity, detail) of every check that ties the calculation to the files read; ``SourceMismatch`` otherwise.

    ``set_names``: the names the chosen modal set carries; ``record_numbers``: its records' numbers in order;
    ``fe_frequencies_hz``: {FE mode number: Hz} of the FE package read.
    """
    reasons, checks = [], []
    experimental_sha256 = str(experimental_sha256 or "").lower()
    if experimental_sha256 != ps.WORKING_SOURCE_SHA256:
        reasons.append(f"the experimental file has SHA-256 {experimental_sha256[:12] or 'none'}… "
                       f"({ps.classify_source(experimental_sha256)}), not {ps.WORKING_SOURCE_SHA256[:12]}… of the "
                       f"plate's working source ({ps.SERIES}); the scenarios' hypotheses are declared for that test "
                       "only")
    else:
        checks.append(("Experimental file", f"SHA-256 {experimental_sha256} — the working source of {ps.SERIES}"))
    names = [str(n) for n in set_names if n]
    wanted = ps.WORKING_SET.lower()
    numbers = [int(n) for n in record_numbers]
    needed = sorted({e for s in scenarios for e, _t in s.pairs})
    set_reasons = []
    if not any(wanted == n.lower() or wanted in n.lower().replace("(", " ").replace(")", " ").split()
               for n in names):
        set_reasons.append(f"the chosen modal set is {' / '.join(names) or 'unnamed'}, not {ps.WORKING_SET}")
    if numbers != list(range(1, len(numbers) + 1)):
        set_reasons.append(f"the records of the chosen modal set are numbered {numbers}, not 1–{len(numbers)}")
    elif needed and needed[-1] > len(numbers):
        set_reasons.append(f"the chosen modal set has {len(numbers)} records; the scenarios use EXP{needed[-1]}")
    if set_reasons:
        reasons += set_reasons
    else:
        checks.append(("Modal set", f"{ps.WORKING_SET}: {len(numbers)} records, numbered 1–{len(numbers)}; their "
                                    "frequencies are read from the file"))
    member = baseline_member()
    wanted_fe = member.manifest.sha256 if member is not None and member.manifest else ""
    fe_manifest_sha256 = str(fe_manifest_sha256 or "").lower()
    if fe_manifest_sha256 != wanted_fe:
        other = next((m.member_id for m in ps.PLATE_FE_FAMILY if m.manifest
                      and m.manifest.sha256 == fe_manifest_sha256), "not a member of the plate's FE family")
        reasons.append(f"the FE package's manifest has SHA-256 {fe_manifest_sha256[:12] or 'none'}… ({other}), not "
                       f"{wanted_fe[:12]}… of {BASELINE_MEMBER}, the model the sensitivities were solved for")
    else:
        read = {int(k): float(v) for k, v in dict(fe_frequencies_hz or {}).items()}
        different = []
        for term, s in sens.items():
            modes = [int(m[2:]) for m in term.split("+")]
            if any(m not in read for m in modes):
                different.append(f"{term} missing")
                continue
            value = math.exp(sum(math.log(read[m]) for m in modes) / len(modes))  # a cluster: the geometric mean
            if abs(value - s["f0"]) > FE_TOLERANCE_HZ:
                different.append(f"{term} {value:.5f} Hz (table {s['f0']:.5f} Hz)")
        if different:
            reasons.append("the FE package's frequencies are not the base point of the sensitivity table: "
                           + ", ".join(different))
        else:
            checks.append(("FE package", f"{BASELINE_MEMBER}: manifest SHA-256 {wanted_fe}; the baseline frequency "
                                         f"of all {len(sens)} FE terms equals the sensitivity table"))
    if reasons:
        raise SourceMismatch(reasons)
    relative, sha, commit = rr.SNAPSHOT_FILES["SENSITIVITIES"]
    checks.append(("Sensitivities", f"{relative}: SHA-256 {sha} (research commit {commit}; six real Abaqus ±5 % "
                                    "solves of PRIORITY-2)"))
    return tuple(checks)


# ------------------------------------------------------------------------------------ the archive (comparison only)

SOLVER_RUNS = ("docs/research/plate_inverse_fe_r1/REAL_FE_SOLVER_RUNS.csv",
               "22ffe74ceebde9db3f778c5b0148854cbd7d7fed3a92df331d286f405a7f02d4", "f19fc93")


def load_archive(root: Path = rr.REPO) -> dict:
    """{scenario: archived record} of PRIORITY-3 / PRIORITY-4; ``ArchiveRefused`` when a file is missing or changed."""
    root = Path(root)
    try:
        snapshot = rr.load_snapshot(root)
    except rr.SnapshotRefused as refusal:
        raise ArchiveRefused(str(refusal)) from refusal
    relative, expected, _commit = SOLVER_RUNS
    path = root / relative
    if not path.is_file():
        raise ArchiveRefused(f"{relative} is missing")
    data = _committed(path)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ArchiveRefused(f"{relative}: the file changed, so the archived solves are not compared")
    runs = {row["job"]: row for row in csv.DictReader(io.StringIO(data.decode("utf-8")))}
    out = {}
    for scenario in snapshot.scenarios:
        key = scenario.key
        declared = tuple((f"{r['exp']} ↔ {r['fe_branch']}", r["f_exp_hz"], r["f_abaqus_hz"], r["error_percent"])
                         for r in snapshot.fe_vs_experiment if r["state"] == key and r["kind"] == "DECLARED_HYPOTHESIS")
        tracking = [r for r in snapshot.tracking if r["state"] == key]
        tracked = sum(1 for r in tracking if r["status"] == "TRACKED")
        lowest = min((float(r["fe_fe_mac_or_cos2"]) for r in tracking), default=float("nan"))
        run = runs.get(key)
        out[key] = {"E1": scenario.E1, "E2": scenario.E2, "G12": scenario.G12, "pairs": scenario.pairs,
                    "abaqus_rows": declared,
                    "tracking": f"{tracked} of {len(tracking)} FE branches tracked to the baseline FE model, lowest "
                                f"FE-to-FE MAC {lowest:.4f}",
                    "solve": "" if run is None else
                    f"Abaqus solve {run['attempt']} of 3 ({run['started']}, exit {run['exit_code']}): INP SHA-256 "
                    f"{run['inp_sha256']} · ODB SHA-256 {run['odb_sha256']}"}
    return out


def compare_with_archive(result: CandidateSet, archive: Optional[dict], note: str = "") -> CandidateSet:
    """``result`` with the archived record beside each candidate. The calculated values are not changed."""
    if archive is None:
        return CandidateSet(result.candidates, result.experiment, result.fixed, result.fe_member, result.across,
                            note or "No archived record was compared.", result.checks)
    candidates = []
    for c in result.candidates:
        a = archive.get(c.key)
        if a is None or a["pairs"] != c.pairs_text:
            candidates.append(c)
            continue
        difference = max(abs(getattr(c, n) - a[n]) for n in PARAMETERS) if c.calculated else None
        comparison = ArchiveComparison(a["E1"], a["E2"], a["G12"], difference,
                                       difference is not None and difference <= ARCHIVE_TOLERANCE_MPA,
                                       a["abaqus_rows"], a["tracking"], a["solve"])
        candidates.append(Candidate(**{**c.__dict__, "archive": comparison}))
    return CandidateSet(tuple(candidates), result.experiment, result.fixed, result.fe_member, result.across,
                        note, result.checks)


# ------------------------------------------------------------------------------------ export for a manual Abaqus check

ELASTIC_ORDER = ("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23")
UNITS = {"E1": "MPa", "E2": "MPa", "E3": "MPa", "G12": "MPa", "G13": "MPa", "G23": "MPa", "nu12": "-", "nu13": "-",
         "nu23": "-", "h": "mm", "rho": "t/mm3"}
ASSUMPTIONS = (
    "FE model: the M11 S4R plate model (CFRP_S4R_0875_FreeFree), free-free; only E1, E2 and G12 are changed.",
    "Forward model of this calculation: the log-linear approximation of the PRIORITY-2 central sensitivities (six "
    "real Abaqus ±5 % solves). The predicted frequencies are NOT Abaqus results.",
    "Every EXP ↔ FE correspondence is a hypothesis: the 261027 scan has no physical registration.",
    "Optimiser: services.identification_step.run_bounded_lm, bounds 0.5–2 × the baseline, deterministic.",
)


def _values(c: Candidate, fixed: dict) -> dict:
    return {**fixed, "E1": round(c.E1, 1), "E2": round(c.E2, 1), "G12": round(c.G12, 1)}


def candidate_text(result: CandidateSet, c: Candidate, sources=()) -> str:
    v = _values(c, result.fixed)
    fitted = {"E1", "E2"} if "E" in c.fitted else set()
    fitted |= set(c.fitted) & set(PARAMETERS)
    lines = [f"{ps.SPECIMEN} — research candidate {c.key}: CALCULATED offline from the measured frequencies",
             " / ".join(LABELS), "NOT verified by Abaqus and NOT a material property. Use it for a manual Abaqus "
             "check only.", "", "Parameters for manual entry"]
    for name in ELASTIC_ORDER:
        if name in v:
            lines.append(f"  {name:<5}= {v[name]:g} {UNITS[name]:<4} "
                         + ("CALCULATED" if name in fitted else "fixed input (the FE model's value)"))
    lines += [f"  {name:<5}= {v[name]:g} {UNITS[name]:<6} fixed input (the FE model's value)"
              for name in ("h", "rho") if name in v]
    if all(name in v for name in ELASTIC_ORDER):
        lines += ["", "Abaqus *Elastic data lines, in the order of the baseline INP (E1, E2, E3, nu12, nu13, nu23, "
                  "G12, G13 / G23):",
                  "  " + ", ".join(f"{v[n]:g}" for n in ELASTIC_ORDER[:8]) + ",", f"  {v['G23']:g}"]
    lines += ["", f"Scenario {c.key}: fitted {' + '.join(c.fitted)}"
              + (" (E means E1 = E2)" if "E" in c.fitted else "") + f"; status {c.status}; rank of the fitted "
              f"parameters {c.rank_fitted} of {len(c.fitted)} (condition {c.condition:.3f}); rank of E1 / E2 / G12 "
              f"on these rows {c.rank_full} of 3.",
              "Ratios to the baseline: " + ", ".join(f"{k} ×{r:.4f}" for k, r in c.ratios.items()) + ".", "",
              "Hypothetical correspondences (measured against predicted)",
              "  hypothesis\tmeasured Hz\tbaseline FE Hz\tpredicted FE Hz\tresidual %"]
    lines += [f"  EXP{x.exp} <-> {x.term}\t{x.f_exp_hz:.4f}\t{x.f_baseline_hz:.5f}\t{x.f_predicted_hz:.5f}\t"
              f"{x.after_percent:+.4f}" for x in c.residuals]
    lines += ["", "Predicted FE frequencies of every tracked FE term (compare each with the same FE mode of your "
              "Abaqus run; FE15+FE16 is the geometric mean of modes 15 and 16)",
              "  FE term\tbaseline Hz\tpredicted Hz"]
    lines += [f"  {term}\t{f0:.5f}\t{predicted:.5f}" for term, f0, predicted in c.predictions]
    lines += ["", "Measured frequencies of the modal set read (Hz): "
              + ", ".join(f"EXP{n} {hz:.4f}" for n, hz in result.experiment), "", "Warnings"]
    lines += [f"  - {w}" for w in c.warnings] + ["", "Limits of what the rows determine"]
    lines += [f"  - {w}" for w in c.limitations] + ["", "Modelling assumptions"]
    lines += [f"  - {w}" for w in ASSUMPTIONS] + ["", "Sources"]
    lines += [f"  - {name}: {detail}" for name, detail in tuple(result.checks) + tuple(sources)]
    return "\n".join(lines) + "\n"


def candidate_csv(result: CandidateSet, c: Candidate) -> str:
    v = _values(c, result.fixed)
    fitted = {"E1", "E2"} if "E" in c.fitted else set()
    fitted |= set(c.fitted) & set(PARAMETERS)
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["section", "item", "value", "unit", "note"])
    writer.writerow(["scenario", c.key, c.status, "", " / ".join(LABELS)])
    for name in ELASTIC_ORDER + ("h", "rho"):
        if name in v:
            writer.writerow(["parameter", name, f"{v[name]:g}", UNITS[name],
                             "CALCULATED (research candidate; not a material property)" if name in fitted
                             else "fixed input (the FE model's value)"])
    writer.writerow(["rank", "fitted parameters", c.rank_fitted, "", f"of {len(c.fitted)}"])
    writer.writerow(["rank", "E1 / E2 / G12", c.rank_full, "", "of 3"])
    for x in c.residuals:
        writer.writerow(["hypothesis", f"EXP{x.exp} <-> {x.term}", f"{x.f_exp_hz:.4f}", "Hz", "measured"])
        writer.writerow(["hypothesis", f"EXP{x.exp} <-> {x.term}", f"{x.f_predicted_hz:.5f}", "Hz",
                         "predicted (log-linear model; not an Abaqus result)"])
        writer.writerow(["hypothesis", f"EXP{x.exp} <-> {x.term}", f"{x.after_percent:+.4f}", "%", "residual"])
    for term, f0, predicted in c.predictions:
        writer.writerow(["predicted frequency", term, f"{predicted:.5f}", "Hz", f"baseline {f0:.5f} Hz"])
    for n, hz in result.experiment:
        writer.writerow(["measured frequency", f"EXP{n}", f"{hz:.4f}", "Hz", "the modal set read; not paired"])
    for w in c.warnings:
        writer.writerow(["warning", "", "", "", w])
    for w in c.limitations:
        writer.writerow(["limitation", "", "", "", w])
    for w in ASSUMPTIONS:
        writer.writerow(["assumption", "", "", "", w])
    return stream.getvalue()


def export(result: CandidateSet, folder, stamp: str, sources=()) -> tuple:
    """Write every calculated candidate as ``plate_candidate_<key>_<stamp>.csv`` and ``.txt`` into ``folder``
    (atomic; an existing file is never replaced). A refused scenario has no file: it has no number."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"{folder} is not an existing folder.")
    written = []
    for c in result.candidates:
        if not c.calculated:
            continue
        for suffix, text in ((".csv", candidate_csv(result, c)), (".txt", candidate_text(result, c, sources))):
            target = folder / f"plate_candidate_{c.key}_{stamp}{suffix}"
            index = 2
            while target.exists():
                target = folder / f"plate_candidate_{c.key}_{stamp}_{index}{suffix}"
                index += 1
            handle, temporary = tempfile.mkstemp(prefix=".~candidate_", suffix=suffix, dir=folder)
            os.close(handle)
            try:
                Path(temporary).write_text(text, encoding="utf-8", newline="\n")
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
            written.append(target)
    return tuple(written)


__all__ = ["ArchiveComparison", "ArchiveRefused", "BOUND_FACTOR", "Candidate", "CandidateSet", "LABELS",
           "LINEAR_RANGE", "P0", "RCOND", "Refused", "Residual", "SCENARIOS", "SETTINGS", "SIGMA_LN", "Scenario",
           "SourceMismatch", "calculate", "candidate_csv", "candidate_text", "compare_with_archive", "export", "fit",
           "full_parameters", "jacobian_rows", "load_archive", "load_sensitivities", "pairing_problems", "predict",
           "rank_report", "verify_sources"]
