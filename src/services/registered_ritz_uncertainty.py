"""ABM-AUD-6: how a registered Ritz research estimate moves with its declared inputs (no Qt, no Abaqus).

Nothing here is a new identification: every number comes from repeating the SAME fit of
``registered_ritz_estimation.run_estimation`` (the same records, roles, fixed correspondence and reference constants)
with ONE declared input changed, or from the exact scaling of the homogeneous Kirchhoff plate.

Two things are reported, and kept apart:

* SENSITIVITY: the local exponent d ln q / d ln x of every estimate q to every input x. For the length, the width and
  nu12 it is a central difference of two refits at x (1 -/+ STEP). For the mass and the thickness it is exact: the
  frequencies fix D / (surface mass), so with the MEASURED MASS held every D is proportional to the mass and does not
  depend on the thickness, and E = 12 D (1 - nu12 nu21) / h^3 goes as h^-3; if instead the VOLUME DENSITY were held, the
  mass would grow with h, D would go as h and E as h^-2. The two thickness assumptions are different statements and are
  shown as such.
* RANGES: for an input whose range the user stated, the estimates at its two ends, the other inputs at their nominal
  values. A range is a deterministic interval of one input. It is not a confidence interval, the inputs are not
  combined, and no accuracy of the estimate is derived from it. An input without a stated range is NOT_ASSESSED.

Not quantified here, and said so in every result: the suspension, the difference between the Ritz plate and an FE or
real plate (model form), a wrong correspondence or registration, and the errors of the measured frequencies.
"""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Mapping, Optional, Sequence

from services import registered_ritz_estimation as rre
from services import research_frequency_tuning as rft

SCHEMA = "registered-ritz-uncertainty/1"
ASSESSED, NOT_ASSESSED = "ASSESSED", "NOT_ASSESSED"
STEP = 0.01  # the relative step of the central differences (a numerical step, not a tolerance of any input)
INPUTS = (("length", "length_mm", "mm"), ("width", "width_mm", "mm"), ("thickness", "thickness_mm", "mm"),
          ("mass", "mass_g", "g"), ("nu12", "nu12", ""))
QUANTITIES = ("D11", "D22", "D66", "E_x", "E_y", "G12")
EXACT, REFIT = "exact scaling of the homogeneous plate", "the same fit repeated with this one input changed"
MASS_HELD = "the measured mass is held (this route: the mass is an input)"
DENSITY_HELD = "the volume density is held instead (the mass then changes with the thickness)"
NOT_QUANTIFIED = (
    "The suspension: the model is free on all edges; no support stiffness or added mass is estimated, and none is "
    "inferred from the frequencies.",
    "Model form: the difference between this Kirchhoff-Ritz plate and an FE model (Abaqus) or the real plate - "
    "transverse shear, rotary inertia, thickness and density variation, layup coupling - is not quantified.",
    "The correspondence and the registration: a wrong mode pairing or a wrong placement of the measurement is not "
    "covered by any range below.",
    "The measured frequencies and shapes: their own errors are not propagated.",
)
STATEMENT = ("Deterministic one-input-at-a-time ranges and local sensitivities of a research estimate. They are not "
             "statistical confidence intervals, they are not combined into one accuracy, and they do not establish any "
             "material property.")


class _Cancelled(Exception):
    pass


def range_problems(plate: rre.Plate, ranges: Mapping[str, Sequence[float]]) -> list:
    """Why the stated ranges cannot be used. A range is (low, high) in the input's own unit and must hold its nominal
    value; the dimensions, thickness and mass stay positive and nu12 stays admissible with the reference constants."""
    problems = []
    known = {name: (attribute, unit) for name, attribute, unit in INPUTS}
    for name, pair in ranges.items():
        if name not in known:
            problems.append(f"There is no input '{name}'.")
            continue
        attribute, unit = known[name]
        nominal = getattr(plate, attribute)
        try:
            low, high = (float(v) for v in pair)
        except (TypeError, ValueError):
            problems.append(f"The range of the {name} needs two numbers.")
            continue
        text = f"The range of the {name} ({low:g} to {high:g}{' ' + unit if unit else ''})"
        if not (math.isfinite(low) and math.isfinite(high)):
            problems.append(f"{text} is not finite.")
        elif not low < high:
            problems.append(f"{text} must run from a lower to a higher value.")
        elif not low <= nominal <= high:
            problems.append(f"{text} does not hold the entered value {nominal:g}.")
        elif name != "nu12" and low <= 0.0:
            problems.append(f"{text} must be positive.")
        elif name == "nu12" and len(plate.reference) == 3 and any(
                not 1.0 - value ** 2 * plate.reference[1] / plate.reference[0] > 0.0 for value in (low, high)):
            problems.append(f"{text} is not admissible: 1 - nu12^2 E2 / E1 must stay positive.")
    return problems


def quantities(result: rft.TuningResult, plate: rre.Plate) -> dict:
    """D11, D22, D66 (N m) and the moduli along the fit frame's x and y and G12 (MPa) of a result."""
    fitted = result.fitted
    d = rft.bending_stiffness(fitted["E1"], fitted["E2"], plate.nu12, fitted["G12"], plate.thickness_mm)
    return {"D11": d.D11, "D22": d.D22, "D66": d.D66, "E_x": fitted["E1"], "E_y": fitted["E2"], "G12": fitted["G12"]}


def _refit(rset, plate: rre.Plate, request: rft.TuningRequest, reviewed: bool, cancel, progress) -> dict:
    """The same fit with the changed plate: its quantities, or the reason there are none."""
    if cancel is not None and cancel.is_set():
        raise _Cancelled()
    try:
        review = rre.shape_review(rset, plate, request.degree) if reviewed else None
        result, block = rre.run_estimation(rset, plate, request, review, cancel, progress)
    except rft.TuningRefused as refusal:
        return {"done": False, "reason": str(refusal)}
    if result.status == rft.CANCELLED or block is None:
        raise _Cancelled()
    verdict = block["presentation"]["verdict"]
    if result.status not in (rft.SUPPORTED, rft.MIRROR):
        return {"done": False, "reason": f"the refit gives no estimate (optimizer status {result.status})"}
    return {"done": True, "values": quantities(result, plate), "status": result.status, "presentation": verdict,
            "fit_rms_ln": result.rms_fit_after, "branch": block["branch"]["verdict"]}


def _changes(values: Mapping[str, float], nominal: Mapping[str, float]) -> dict:
    return {name: values[name] / nominal[name] - 1.0 for name in QUANTITIES}


def _scaled(nominal: Mapping[str, float], stiffness: float, moduli: float) -> dict:
    return {name: nominal[name] * (stiffness if name.startswith("D") else moduli) for name in QUANTITIES}


def exact_rows(nominal: Mapping[str, float]) -> list:
    """The exact exponents of the homogeneous plate at fixed measured frequencies, plan and nu12."""
    def row(name, assumption, stiffness, moduli):
        return {"input": name, "assumption": assumption, "method": EXACT, "status": ASSESSED,
                "exponents": {q: (stiffness if q.startswith("D") else moduli) for q in QUANTITIES}, "reason": ""}

    return [row("mass", "the plan dimensions and the thickness are held", 1.0, 1.0),
            row("thickness", MASS_HELD, 0.0, -3.0),
            row("thickness", DENSITY_HELD, 1.0, -2.0)]


def run_uncertainty(rset: rre.RegisteredSet, plate: rre.Plate, request: rft.TuningRequest, review: Optional[Mapping],
                    result: rft.TuningResult, ranges: Mapping[str, Sequence[float]], cancel=None, progress=None) -> dict:
    """The sensitivities and the stated ranges of ``result``, which ``run_estimation(rset, plate, request, review)``
    returned. ``ranges``: {input: (low, high)} for the inputs whose range the user stated; the others are
    NOT_ASSESSED. Returns None when it is cancelled. Refused when the result holds no estimate or a range is invalid."""
    if result.status not in (rft.SUPPORTED, rft.MIRROR):
        raise rre.EstimationRefused(rre.INVALID_INPUT, f"There is no estimate to assess: the optimizer status is "
                                                       f"{result.status}.")
    problems = range_problems(plate, ranges)
    if problems:
        raise rre.EstimationRefused(rre.INVALID_INPUT, " ".join(problems))
    reviewed = review is not None
    nominal = quantities(result, plate)
    categories = dict(zip(rre.INPUT_NAMES, plate.categories))
    refits = 0

    def at(name: str, value: float) -> dict:
        nonlocal refits
        refits += 1
        attribute = next(a for n, a, _u in INPUTS if n == name)
        return _refit(rset, replace(plate, **{attribute: value}), request, reviewed, cancel, progress)

    try:
        sensitivity = exact_rows(nominal)
        for name, attribute, _unit in INPUTS:
            if name in ("mass", "thickness"):
                continue
            value = getattr(plate, attribute)
            low, high = at(name, value * (1.0 - STEP)), at(name, value * (1.0 + STEP))
            row = {"input": name, "assumption": "every other input is held", "method": REFIT + f" by -/+ {STEP:.0%}",
                   "status": NOT_ASSESSED, "exponents": {}, "reason": ""}
            if low["done"] and high["done"]:
                span = math.log((1.0 + STEP) / (1.0 - STEP))
                row["exponents"] = {q: math.log(high["values"][q] / low["values"][q]) / span for q in QUANTITIES}
                row["status"] = ASSESSED
            else:
                row["reason"] = next(item["reason"] for item in (low, high) if not item["done"])
            sensitivity.append(row)
        inputs, rows = [], []
        for name, attribute, unit in INPUTS:
            value = getattr(plate, attribute)
            stated = name in ranges
            inputs.append({"input": name, "nominal": value, "unit": unit, "category": categories[name],
                           "low": float(ranges[name][0]) if stated else None,
                           "high": float(ranges[name][1]) if stated else None,
                           "status": ASSESSED if stated else NOT_ASSESSED})
            if not stated:
                continue
            for bound, end in zip(("low", "high"), (float(v) for v in ranges[name])):
                factor = end / value
                def exact(stiffness: float, moduli: float) -> dict:
                    return {"done": True, "values": _scaled(nominal, stiffness, moduli)}

                if name == "mass":
                    cases = [(EXACT, "the plan dimensions and the thickness are held", exact(factor, factor))]
                elif name == "thickness":
                    cases = [(EXACT, MASS_HELD, exact(1.0, factor ** -3)), (EXACT, DENSITY_HELD, exact(factor, factor ** -2))]
                else:
                    cases = [(REFIT, "every other input is held",
                              at(name, end) if end != value else {"done": True, "values": dict(nominal)})]
                for method, assumption, outcome in cases:
                    values = outcome["values"] if outcome["done"] else None
                    row = {"input": name, "bound": bound, "value": end, "unit": unit, "method": method,
                           "assumption": assumption, "status": ASSESSED if values else NOT_ASSESSED,
                           "values": values, "change": _changes(values, nominal) if values else None,
                           "reason": "" if values else outcome.get("reason", ""),
                           "presentation": outcome.get("presentation")}
                    rows.append(row)
    except _Cancelled:
        return None
    envelope = []
    for name, _attribute, _unit in INPUTS:
        for assumption in sorted({r["assumption"] for r in rows if r["input"] == name}):
            found = [r for r in rows if r["input"] == name and r["assumption"] == assumption and r["values"]]
            if len(found) == 2:
                envelope.append({"input": name, "assumption": assumption,
                                 "low": {q: min(r["values"][q] for r in found) for q in QUANTITIES},
                                 "high": {q: max(r["values"][q] for r in found) for q in QUANTITIES},
                                 "largest_change": max(abs(v) for r in found for v in r["change"].values())})
    return rre._plain({
        "schema": SCHEMA, "set_identity": rset.identity, "plate_identity": plate.identity(),
        "nominal": nominal, "frame": dict(zip(("x", "y"), plate.direction_names())), "status": result.status,
        "inputs": inputs, "sensitivity": sensitivity, "ranges": rows, "envelope": envelope, "refits": refits,
        "step": STEP, "not_quantified": list(NOT_QUANTIFIED), "statement": STATEMENT,
        "axis_note": ("Two minima with the in-plane moduli exchanged fit equally: every value here belongs to the lowest "
                      "minimum, and the exchanged alternative is as likely by these frequencies."
                      if result.status == rft.MIRROR else ""),
    })


def check(uncertainty) -> Optional[dict]:
    """A saved uncertainty part, or None when there is none. Refused when it is of another version or incomplete."""
    if uncertainty is None:
        return None
    if not isinstance(uncertainty, dict) or uncertainty.get("schema") != SCHEMA:
        raise rft.TuningRefused("The export holds an uncertainty part of another version; it is not opened.")
    missing = [key for key in ("nominal", "inputs", "sensitivity", "ranges", "envelope", "not_quantified", "statement")
               if key not in uncertainty]
    if missing:
        raise rft.TuningRefused(f"The uncertainty part is incomplete: {', '.join(missing)} missing.")
    return uncertainty


__all__ = ["ASSESSED", "DENSITY_HELD", "EXACT", "INPUTS", "MASS_HELD", "NOT_ASSESSED", "NOT_QUANTIFIED", "QUANTITIES",
           "REFIT", "SCHEMA", "STATEMENT", "STEP", "check", "exact_rows", "quantities", "range_problems",
           "run_uncertainty"]
