"""REAL-FIT.R2: stability of the research frequency-tuning estimates, from the measured frequencies alone (no Qt, no Abaqus).

This module checks a finished ``research_frequency_tuning.run_tuning`` result. It changes neither that result nor the
workflow that made it, and it issues no material property: everything carries ``RESULT_LABEL``.

What it does:

1. **Leave one FIT record out**, once for every FIT record. Only that record leaves the fit. Every other observation keeps
   its declared surrogate rank and its role, so the correspondence is never renumbered, rematched or optimized. Each refit
   uses the full fit's bounds and parameterization and starts from the full-data minimum (plus the same start pattern).
2. **Comparison with the full-data result**, on axis-independent quantities: ``E (E1 = E2)`` and ``G12`` for the tied model,
   ``E_stiff``, ``E_soft`` and ``G12`` for the orthotropic one. For every refit it reports the parameter changes, the
   frequency residuals, the practical rank, the convergence, the active bounds and the competing minima.
3. **Control by one record**: a record controls a parameter disproportionately when its own leave-out change carries more
   than ``DOMINANCE_SHARE`` of the summed squared changes of that parameter and is at least ``DOMINANCE_FLOOR``.
4. **Local influence coefficients** d ln p / d ln f_exp from the full fit's own sensitivity matrix J (d ln f / d ln p):
   the truncated pseudo-inverse of J at its practical rank. Directions below the practical rank are not determined, and a
   parameter with a share of them is marked so; its coefficients are then the minimum-norm convention, not a result.
5. **Thickness and density**: the exact surrogate scaling of the absolute moduli, with a numerical verification on the
   surrogate. No distribution or interval is given for either input.
6. **The 10 % engineering objective**, separated into numerical stability, frequency fit and parameter accuracy. Parameter
   accuracy is never inferred from a small residual or a stable refit.
"""

from __future__ import annotations

from dataclasses import replace
import math
import threading
from typing import Callable, Mapping, Optional, Sequence

import numpy as np

from services import research_frequency_tuning as rft

SCHEMA = "research-frequency-stability/1"
TARGET = 0.10  # the owner's engineering objective for the parameters: a target to assess, never a demonstrated property
DOMINANCE_SHARE = 0.5  # numerical reporting policy: one record's share of the summed squared leave-out changes
DOMINANCE_FLOOR = 0.01  # numerical reporting policy: a leave-out change below 1 % is not called control by one record
UNDETERMINED_SHARE = 0.01  # numerical reporting policy: a parameter's share of the undetermined directions
VERIFICATION_FACTOR = 1.03  # the point where the exact scaling is checked on the surrogate; not an uncertainty
STABLE, UNSTABLE, NOT_ASSESSED = "STABLE_WITHIN_TARGET", "CHANGE_EXCEEDS_TARGET", "NOT_ASSESSED"
NOT_DEMONSTRATED = "NOT_DEMONSTRATED"


class _Counter:
    def __init__(self, progress):
        self.count, self.progress = 0, progress

    def __call__(self, _count):
        self.count += 1
        if self.progress is not None:
            self.progress(self.count)


def axis_free_names(names: Sequence[str]) -> tuple:
    return ("E (E1 = E2)", "G12") if "E" in names else ("E_stiff", "E_soft", "G12")


def _axis_free(names, values: Mapping[str, float]) -> dict:
    return rft._estimates(names, values)


def _relabel(names, full: Mapping[str, float]) -> dict:
    """Parameter name -> axis-independent name at the full-data minimum (E1 and E2 become E_stiff and E_soft)."""
    if "E" in names:
        return {"E": "E (E1 = E2)", "G12": "G12"}
    stiff, soft = ("E1", "E2") if full["E1"] >= full["E2"] else ("E2", "E1")
    return {stiff: "E_stiff", soft: "E_soft", "G12": "G12"}


def _is_mirror(names, minima) -> bool:
    return (len(minima) >= 2 and "E1" in names and all(
        abs(minima[0]["values"][a] / minima[1]["values"][b] - 1.0) <= rft.MIRROR_TOLERANCE
        for a, b in (("E1", "E2"), ("E2", "E1"), ("G12", "G12"))))


def _same(a, b) -> bool:
    return float(np.max(np.abs(np.exp(a["x"] - b["x"]) - 1.0))) <= rft.START_AGREEMENT


# ---------------------------------------------------------------------------------------------- local influence


def influence(baseline: rft.TuningResult) -> dict:
    """d ln p / d ln f_exp of every FIT record, from the full fit's sensitivity matrix, with the leverage and the linearized
    leave-one-out change. Rank deficiency: the pseudo-inverse is truncated at the practical rank of the full fit."""
    names = tuple(baseline.parameter_names)
    records = [row["record"] for row in baseline.sensitivity]
    J = np.array([[row[n] for n in names] for row in baseline.sensitivity], dtype=float)
    residual = {r["record"]: r["ln_after"] for r in baseline.rows if r["role"] == rft.FIT}
    r = np.array([residual[k] for k in records], dtype=float)
    U, s, Vt = np.linalg.svd(J, full_matrices=False)
    k = int(np.sum(s > rft.PRACTICAL_RANK_RATIO * s[0])) if s.size else 0
    pinv = (Vt[:k].T / s[:k]) @ U[:, :k].T  # p x n: d ln p / d ln f_exp
    leverage = np.sum(U[:, :k] ** 2, axis=1)
    A = (Vt[:k].T / s[:k] ** 2) @ Vt[:k]  # (J^T J)^+ at the practical rank
    full = baseline.minima[0]["values"]
    label = _relabel(names, full)
    undetermined = {label[n]: float(np.sum(Vt[k:, j] ** 2)) for j, n in enumerate(names)}
    linear = []
    for i, record in enumerate(records):
        if leverage[i] >= 1.0 - 1e-9:
            linear.append({"record": record, "change": None})
            continue
        step = A @ J[i] * r[i] / (1.0 - leverage[i])  # removing record i: x_(i) - x, linearized
        values = {n: full[n] * math.exp(step[j]) for j, n in enumerate(names)}
        free = _axis_free(names, values)
        base = _axis_free(names, full)
        linear.append({"record": record, "change": {q: free[q] / base[q] - 1.0 for q in base}})
    coefficients = []
    for i, record in enumerate(records):
        coefficients.append({"record": record, "leverage": float(leverage[i]),
                             **{label[n]: float(pinv[j, i]) for j, n in enumerate(names)}})
    shares = {}
    for j, n in enumerate(names):
        total = float(np.sum(pinv[j] ** 2))
        shares[label[n]] = {record: (float(pinv[j, i] ** 2) / total if total > 0 else None) for i, record in enumerate(records)}
    return {
        "method": ("truncated pseudo-inverse of the full fit's sensitivity matrix J = d ln f / d ln p (FIT rows, at the "
                   "full-data minimum); coefficient = d ln p / d ln f_exp, so a 1 % shift of that measured frequency "
                   "alone moves the parameter by about that many per cent"),
        "practical_rank": k, "parameters": len(names), "singular_values": s.tolist(),
        "rank_deficient": k < len(names),
        "undetermined_share": undetermined,
        "undetermined": [q for q, v in undetermined.items() if v > UNDETERMINED_SHARE],
        "rank_note": ("full practical rank: every parameter is determined locally" if k == len(names) else
                      f"practical rank {k} of {len(names)}: the directions below the rank are not determined by these "
                      "frequencies; coefficients of a parameter with a share of them are a minimum-norm convention, "
                      "not a result"),
        "coefficients": coefficients,
        "coefficient_sums": {label[n]: float(np.sum(pinv[j])) for j, n in enumerate(names)},
        "squared_coefficient_shares": shares,
        "share_note": ("share of the squared coefficients of a parameter; it is the share of variance only if every "
                       "frequency had the same independent error, which is not assumed here"),
        "linearized_leave_one_out": linear,
    }


# ---------------------------------------------------------------------------------------------- leave one out


def _refit(inputs, request, names, x_full, bounds, left_out, counter, cancel) -> dict:
    observations = tuple(o if o.record != left_out.record else rft.Observation(o.record, o.hz, rft.EXCLUDED, 0)
                         for o in request.observations)
    fit_rows = tuple(o for o in observations if o.role == rft.FIT)
    if len(fit_rows) <= len(names):
        return {"record": left_out.record, "hz": left_out.hz, "rank": left_out.surrogate_rank, "done": False,
                "reason": f"{len(fit_rows)} FIT records remain for {len(names)} parameters"}
    problem = rft._Problem(inputs, names, fit_rows, request.degree, cancel, counter)
    fit = rft._solve(problem, x_full, request.search_factor, bounds=bounds)
    if "E1" in names and len(fit["minima"]) == 1:  # the exchanged minimum is looked for, never assumed absent
        mirror = rft._solve(problem, rft._swap(names, fit["minima"][0]["x"]), request.search_factor, bounds=bounds)
        for item in mirror["minima"]:
            if not any(_same(item, m) for m in fit["minima"]):
                fit["minima"].append(item)
        fit["starts"] += mirror["starts"]
    minima = sorted(fit["minima"], key=lambda m: m["cost"])
    best = minima[0]
    # the refit's minimum with the full fit's axis assignment: the change it shows is the record's own influence; the
    # lowest-cost minimum may lie in the exchanged assignment, whose small asymmetry is reported separately
    same = min(minima, key=lambda m: float(np.max(np.abs(m["x"] - x_full))))
    x = same["x"]
    J = problem.jacobian(x)
    singular = np.linalg.svd(J, compute_uv=False)
    rank = int(np.sum(singular > rft.PRACTICAL_RANK_RATIO * singular[0])) if singular.size else 0
    condition = float(singular[0] / singular[-1]) if singular.size and singular[-1] > 0 else math.inf
    lower, upper = bounds
    active = [n for n, v, lo, hi in zip(names, x, lower, upper) if v - lo < 1e-6 or hi - v < 1e-6]
    mirror = _is_mirror(names, minima)
    competing = [m for m in minima[1:] if not (mirror and m is minima[1])]
    switched = same is not best
    kept = tuple(o for o in observations if o.role != rft.EXCLUDED) + (left_out,)
    spectrum = rft._Problem(inputs, names, kept, request.degree, cancel, counter).spectrum(x)

    def ln(o):
        return math.log(float(spectrum[o.surrogate_rank - 1]) / o.hz)

    fit_ln = [ln(o) for o in fit_rows]
    holdout_ln = [ln(o) for o in observations if o.role == rft.HOLDOUT]
    values = dict(zip(names, np.exp(x).tolist()))
    return {
        "record": left_out.record, "hz": left_out.hz, "rank": left_out.surrogate_rank, "done": True,
        "ranks_kept": {o.record: o.surrogate_rank for o in fit_rows},
        "values": values, "estimates": _axis_free(names, values),
        "lowest_cost_in_other_assignment": switched,
        "lowest_cost_estimates": _axis_free(names, best["values"]),
        "cost": same["cost"], "lowest_cost": best["cost"],
        "fit_rms_ln": float(np.sqrt(np.mean(np.square(fit_ln)))),
        "fit_residuals_ln": {o.record: v for o, v in zip(fit_rows, fit_ln)},
        "left_out_residual_ln": ln(left_out),
        "holdout_rms_ln": float(np.sqrt(np.mean(np.square(holdout_ln)))) if holdout_ln else None,
        "practical_rank": rank, "condition_number": condition,
        "converged": all(s["success"] for s in fit["starts"]),
        "active_bounds": active, "mirror": mirror,
        "competing_minima": [{"estimates": _axis_free(names, m["values"]), "cost": m["cost"],
                              "cost_ratio_to_lowest": m["cost"] / best["cost"] if best["cost"] > 0 else None}
                             for m in competing],
        "minima": [{"values": dict(m["values"]), "cost": m["cost"]} for m in minima],
    }


def _clean(item, names) -> bool:
    """Converged, full practical rank, no active bound. Competing minima are reported beside it, not hidden by it."""
    return bool(item.get("done") and item["converged"] and item["practical_rank"] == len(names) and not item["active_bounds"])


# ---------------------------------------------------------------------------------------------- fixed inputs


def fixed_input_dependence(inputs: rft.AbaqusPlateInputs, baseline: rft.TuningResult, degree: int) -> dict:
    """The exact surrogate dependence of the absolute moduli on the assumed thickness t and density rho at fixed measured
    frequencies, plan and nu12: every D_ij ~ E t^3 and the mass per area is rho t, so f^2 ~ E t^2 / rho. Verified on the
    surrogate at one point (VERIFICATION_FACTOR); no distribution or interval is assumed for either input."""
    names = tuple(baseline.parameter_names)
    full = baseline.minima[0]["values"]
    moduli = rft._moduli(names, [full[n] for n in names], inputs)
    surrogate = rft.Surrogate(inputs, degree, 12)
    reference = surrogate.frequencies(moduli["E1"], moduli["E2"], moduli["G12"])
    factor = VERIFICATION_FACTOR
    checks = []
    for case, changed, scale in (("thickness × 1.03, density held", replace(inputs, thickness_mm=inputs.thickness_mm * factor),
                                  factor ** -2),
                                 ("thickness × 1.03, surface mass held",
                                  replace(inputs, thickness_mm=inputs.thickness_mm * factor,
                                          density_t_mm3=inputs.density_t_mm3 / factor), factor ** -3),
                                 ("density × 1.03", replace(inputs, density_t_mm3=inputs.density_t_mm3 * factor), factor)):
        scaled = rft.Surrogate(changed, degree, 12).frequencies(moduli["E1"] * scale, moduli["E2"] * scale, moduli["G12"] * scale)
        checks.append({"case": case, "moduli_factor": scale,
                       "largest_relative_frequency_difference": float(np.max(np.abs(scaled / reference - 1.0)))})

    def band(exponent):  # the input factor that alone moves every modulus by -10 % or +10 %
        return sorted(((1.0 - TARGET) ** (1.0 / exponent), (1.0 + TARGET) ** (1.0 / exponent)))

    return {
        "relation": ("E_i(t, rho) = E_i,fit × (rho / rho_INP) × (t / t_INP)^-2 with the density held, and "
                     "× (t / t_INP)^-3 with the surface mass rho·t held (a weighed plate); the same factor for E1, E2 "
                     "and G12, so E_stiff / E_soft and E / G12 do not depend on t or rho"),
        "exponents": {"d ln E / d ln t (density held)": -2.0, "d ln E / d ln t (surface mass held)": -3.0,
                      "d ln E / d ln rho": 1.0},
        "inp_values": {"thickness_mm": inputs.thickness_mm, "density_t_mm3": inputs.density_t_mm3},
        "estimates_at_inp_values": _axis_free(names, full),
        "ratios": ({"E_stiff / E_soft": full_ratio(full, names), "E_stiff / G12": max(full["E1"], full["E2"]) / full["G12"]}
                   if "E1" in names else {"E / G12": full["E"] / full["G12"]}),
        "input_factor_for_a_10_percent_modulus_change": {
            "thickness, density held": band(-2.0), "thickness, surface mass held": band(-3.0), "density": band(1.0)},
        "factor_note": ("the change of one input that alone moves the absolute moduli by 10 %; it is not an uncertainty of "
                        "that input, which this evidence does not give"),
        "verification": checks,
        "verification_note": "surrogate solved with the scaled input and the scaled moduli; 1.03 is a check point only",
    }


def full_ratio(full, names) -> float:
    return max(full["E1"], full["E2"]) / min(full["E1"], full["E2"])


# ---------------------------------------------------------------------------------------------- the check


def run_stability(inputs: rft.AbaqusPlateInputs, request: rft.TuningRequest, baseline: rft.TuningResult,
                  cancel: Optional[threading.Event] = None, progress: Optional[Callable[[int], None]] = None) -> dict:
    """The stability check of ``baseline``, which ``run_tuning(inputs, request)`` returned. Read only; no file is written."""
    if baseline.status == rft.CANCELLED or not baseline.minima or not baseline.sensitivity:
        raise rft.TuningRefused("The stability check needs a finished tuning result.")
    if request.parameterization not in rft.PARAMETERIZATIONS or tuple(baseline.parameter_names) != rft.PARAMETERIZATIONS[
            request.parameterization]:
        raise rft.TuningRefused("The stability check needs the request that produced this result.")
    rft.validate_correspondence(request.observations)
    names = tuple(baseline.parameter_names)
    recorded = {(o["record"], o["role"], o["surrogate_rank"]) for o in baseline.request.get("observations", [])}
    if recorded != {(o.record, o.role, o.surrogate_rank) for o in request.observations}:
        raise rft.TuningRefused("The stability check needs the request that produced this result.")
    full = baseline.minima[0]["values"]
    x_full = np.array([math.log(full[n]) for n in names])
    bounds = (np.array([math.log(baseline.initialization["bounds"][n][0]) for n in names]),
              np.array([math.log(baseline.initialization["bounds"][n][1]) for n in names]))
    reference = _axis_free(names, full)
    counter = _Counter(progress)
    refits = []
    try:
        for left_out in request.fit_rows():
            item = _refit(inputs, request, names, x_full, bounds, left_out, counter, cancel)
            if item.get("done"):
                item["change"] = {q: item["estimates"][q] / reference[q] - 1.0 for q in reference}
                item["lowest_cost_change"] = {q: item["lowest_cost_estimates"][q] / reference[q] - 1.0 for q in reference}
            refits.append(item)
        dependence = fixed_input_dependence(inputs, baseline, request.degree)
    except rft._Cancelled:
        return {"schema": SCHEMA, "status": rft.CANCELLED, "label": rft.RESULT_LABEL, "solves": counter.count}
    local = influence(baseline)
    done = [item for item in refits if item.get("done")]
    control = []
    for q in reference:
        changes = {item["record"]: item["change"][q] for item in done}
        total = sum(v * v for v in changes.values())
        record, largest = max(changes.items(), key=lambda kv: abs(kv[1])) if changes else (None, 0.0)
        share = (largest * largest / total) if total > 0 else 0.0
        local_shares = local["squared_coefficient_shares"].get(q, {})
        local_top = max(local_shares.items(), key=lambda kv: kv[1] or 0.0) if local_shares else (None, None)
        order = sorted(local_shares, key=lambda k: -(local_shares[k] or 0.0))
        control.append({
            "parameter": q, "largest_change": largest, "record": record, "share_of_squared_changes": share,
            "disproportionate": bool(share > DOMINANCE_SHARE and abs(largest) >= DOMINANCE_FLOOR),
            "local_top_record": local_top[0], "local_top_share": local_top[1],
            "local_order": order,
            "locally_undetermined": q in local["undetermined"],
            "exceeds_target": abs(largest) > TARGET,
        })
    assessment = assess(baseline, names, done, refits, control, dependence)
    return {
        "schema": SCHEMA, "status": "DONE", "label": rft.RESULT_LABEL,
        "baseline": {"status": baseline.status, "parameterization": request.parameterization, "estimates": reference,
                     "values": dict(full), "fit_rms_ln": baseline.rms_fit_after, "holdout_rms_ln": baseline.rms_holdout_after,
                     "bounds": dict(baseline.initialization["bounds"]),
                     "ranks": {o.record: o.surrogate_rank for o in request.observations if o.role != rft.EXCLUDED}},
        "correspondence": ("held as declared in every refit: only the left-out record leaves; no rank is renumbered, "
                           "rematched or optimized"),
        "policy": {"dominance_share": DOMINANCE_SHARE, "dominance_floor": DOMINANCE_FLOOR,
                   "undetermined_share": UNDETERMINED_SHARE, "target": TARGET,
                   "note": "numerical reporting policy of this research check; no accepted scientific threshold"},
        "leave_one_out": refits, "control": control, "influence": local, "fixed_inputs": dependence,
        "assessment": assessment, "solves": counter.count,
    }


def assess(baseline, names, done, refits, control, dependence) -> dict:
    """The owner's 10 % objective, three separate questions. Only the first two are answered by these data."""
    clean = bool(done) and len(done) == len(refits) and all(_clean(item, names) for item in done)
    competing = [item["record"] for item in done if item["competing_minima"]]
    per = []
    for item in control:
        q = item["parameter"]
        either = max((abs(r["change"][q]) for r in done), default=0.0)
        either = max([either] + [abs(r["lowest_cost_change"][q]) for r in done])  # also the lowest-cost minimum
        verdict = NOT_ASSESSED if not clean else (UNSTABLE if either > TARGET else STABLE)
        per.append({"parameter": q, "largest_leave_one_out_change": item["largest_change"], "record": item["record"],
                    "largest_change_including_the_lowest_cost_minimum": either, "numerical_stability": verdict})
    misfit = baseline.rms_fit_after is not None and baseline.rms_fit_after > rft.MISFIT_RMS
    numerical = (NOT_ASSESSED if not clean else UNSTABLE if any(p["numerical_stability"] == UNSTABLE for p in per)
                 else STABLE)
    thickness = dependence["input_factor_for_a_10_percent_modulus_change"]
    reasons = [
        "No independent reference value of these moduli exists in the evidence, so no estimate is compared with a truth.",
        "Thickness and density are fixed at the INP values and not measured here; alone, the moduli move by 10 % for a "
        f"thickness factor of {thickness['thickness, density held'][0]:.4f} to {thickness['thickness, density held'][1]:.4f} "
        f"(density held), or {thickness['thickness, surface mass held'][0]:.4f} to "
        f"{thickness['thickness, surface mass held'][1]:.4f} (surface mass held), or a density factor of 0.9 to 1.1.",
        "The Kirchhoff-Ritz surrogate, the free-free support, nu12 and the specimen identity are assumptions.",
        "The rank correspondence is a declared hypothesis, not a verified mode pairing.",
    ]
    if misfit:
        reasons.append(f"The FIT residual RMS ({baseline.rms_fit_after:.2%} in ln f) exceeds {rft.MISFIT_RMS:.0%}: the "
                       "parameterization does not reproduce the spectrum, so its values absorb model-form error.")
    if baseline.status == rft.MIRROR:
        reasons.append("The E1 / E2 axis assignment is unresolved: only E_stiff, E_soft and G12 are assessed.")
    if baseline.status not in (rft.SUPPORTED, rft.MIRROR):
        reasons.append(f"The full-data fit is {baseline.status}: it gives no research estimate.")
    switched = [item["record"] for item in done if item["lowest_cost_in_other_assignment"]]
    caveats = []
    if competing:
        caveats.append("Refits without record(s) " + ", ".join(map(str, competing)) + " also reach a further, non-mirror "
                       "minimum (see the cost ratios): the minimum is not unique within the search range there.")
    if switched:
        caveats.append("Without record(s) " + ", ".join(map(str, switched)) + " the lowest cost lies in the exchanged "
                       "E1 / E2 assignment; that minimum is included in the largest change.")
    return {
        "target": TARGET,
        "numerical_stability": {"verdict": numerical, "refits_clean": clean, "parameters": per,
                                "refits_with_competing_minima": competing, "refits_lowest_cost_in_other_assignment": switched,
                                "caveats": caveats,
                                "meaning": ("how much one FIT record moves the estimate; a stable refit says the "
                                            "estimate does not hang on one frequency, not that it is accurate")},
        "frequency_fit": {"fit_rms_ln": baseline.rms_fit_after, "holdout_rms_ln": baseline.rms_holdout_after,
                          "misfit_warning": misfit,
                          "meaning": "how well the surrogate reproduces the measured frequencies; not a parameter error"},
        "parameter_accuracy": {"verdict": NOT_DEMONSTRATED, "reasons": reasons},
        "statement": ("10 % TARGET: NOT DEMONSTRATED. "
                      + {STABLE: "Numerically, no single FIT record moves an estimate by more than 10 %. ",
                         UNSTABLE: "Numerically, leaving out one FIT record moves an estimate by more than 10 %. ",
                         NOT_ASSESSED: "Numerical stability is not assessed: a refit did not converge, lost rank or "
                                       "ended at a bound. "}[numerical]
                      + "Largest leave-one-out changes: " + ", ".join(
                          f"{p['parameter']} {p['largest_change_including_the_lowest_cost_minimum']:.1%}"
                          + (f" (record {p['record']})" if p["record"] is not None else "") for p in per) + ". "
                      + "".join(c + " " for c in caveats)
                      + "A small frequency residual or a stable refit is not a parameter accuracy; the accuracy also "
                        "depends on the assumed thickness, density, model form and correspondence, which these data do "
                        "not test."),
    }


__all__ = ["DOMINANCE_FLOOR", "DOMINANCE_SHARE", "NOT_ASSESSED", "NOT_DEMONSTRATED", "SCHEMA", "STABLE", "TARGET",
           "UNSTABLE", "assess", "axis_free_names", "fixed_input_dependence", "influence", "run_stability"]
