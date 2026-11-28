"""PLATE-DIRECT-ESTIMATION-01: bending stiffness of a standalone rectangular plate from measured frequencies (no Qt).

A small adapter. There is no Abaqus, no INP, no ODB and no registration in this route: the user gives a curve-fitted
experimental modal set and enters the plate (length, width, thickness, mass and a fixed Poisson ratio, each with its
provenance). Everything numerical is an existing service:

* the forward model is the Kirchhoff-Ritz free plate of ``plate_ritz_forward``;
* the fit is ``research_frequency_tuning.run_tuning`` on frequencies only, under ONE explicit record -> Ritz rank
  hypothesis with FIT / HOLDOUT / EXCLUDED roles that the user fixes before the fit;
* the stiffness conversion and the declared plate are those of ``registered_ritz_estimation``;
* the input sensitivities and ranges are ``registered_ritz_uncertainty.run_uncertainty`` with this route's fit.

What this route cannot have is a mode identity. No measured shape is compared with a Ritz shape, because nothing here
establishes where the measurement points lie on the plate. Every result is therefore a FREQUENCY-ONLY DIAGNOSTIC
HYPOTHESIS: it is never presented as a verified or numerically supported estimate, whatever the residuals are.

A frequency-only fit often has several minima (the rank order of the Ritz modes changes during the search). The tuning
service then reports ``STARTS_DISAGREE`` and issues no candidate; that rule is unchanged. This route lists EVERY minimum
that was reached, with its FIT and HOLDOUT residuals and its stiffnesses, as competing hypotheses. None is chosen, and
the input assessment (which needs one estimate) stays unavailable for such a result.

D11, D22 and D66 are the primary numbers (the frequencies fix D / surface mass; the thickness is not needed for them).
Ex, Ey and Gxy follow from D only through the declared thickness (E ~ h^-3 with the measured mass held) and are named by
the plate's EDGE axes: x along the length, y along the width. No material axis 1 is named.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Optional, Sequence

import numpy as np

from domain.plate_material_problem import PlateForwardRefusal
from services import registered_ritz_estimation as rre
from services import registered_ritz_uncertainty as rru
from services import research_frequency_tuning as rft

SCHEMA = "standalone-plate-estimation/1"
EXPORT_KEY = "standalone_plate_estimation"
LABEL = ("STANDALONE_PLATE_FREQUENCY_ONLY_DIAGNOSTIC_HYPOTHESIS — NO_PHYSICAL_POINT_MAPPING — NOT_A_VERIFIED_ESTIMATE — "
         "NOT_A_MATERIAL_PROPERTY — NOT_PRODUCTION_AUTO_ID")
FREQUENCY_ONLY, NO_ESTIMATE = "FREQUENCY_ONLY_DIAGNOSTIC_HYPOTHESIS", rre.NO_ESTIMATE
COMPETING = "COMPETING_FREQUENCY_ONLY_HYPOTHESES"  # several minima: every one is listed, none is chosen
SHOWN_STATUSES = (rft.SUPPORTED, rft.MIRROR, rft.STARTS_DISAGREE)  # the optimizer statuses with numbers to show
PLATE_AXIS_VALUES, WITHHELD = "CONDITIONAL_PLATE_AXIS_VALUES", "WITHHELD"
UNRESOLVED = "UNRESOLVED_FREQUENCY_RANK_ONLY"
INPUT_CATEGORIES = (rre.MEASURED, rre.DECLARED)  # there is no FE model to import a value from
NEUTRAL_REFERENCE = (rft.REFERENCE_MPA, rft.REFERENCE_MPA, rft.REFERENCE_MPA)  # for the "before" column only
NO_MAPPING = ("No independently established physical point mapping: no measured shape was compared with a Ritz shape, "
              "so every record -> Ritz mode correspondence is a hypothesis and no mode identity is established.")
ASSUMPTIONS = rre.ASSUMPTIONS[:4] + (
    "Each measured record is compared with the Ritz rank fixed by the user before the fit, by frequency only. No "
    "shape is compared: a missing, extra or exchanged mode cannot be seen by this route.",
    "Ex, Ey and Gxy are values along the plate's edges (x = length a, y = width b) of one homogeneous layer of the "
    "declared thickness. Whether an edge is a material axis is not known here.",
)
VALIDITY_TEXT = ("NOT ESTABLISHED. This is a frequency-only diagnostic hypothesis: a converged optimizer and small FIT and "
                 "HOLDOUT residuals do not verify the correspondence, the model or any material property. The values are "
                 "conditional on the entered plate, the fixed rank hypothesis and the Kirchhoff-Ritz model.")
CORRESPONDENCE_STATEMENT = ("UNVERIFIED CORRESPONDENCE HYPOTHESIS, fixed by the user before the fit: records are matched "
                            "to Ritz modes by frequency rank only. " + NO_MAPPING)


@dataclass(frozen=True)
class PlateModalSet:
    """The curve-fitted records of one experimental file: numbers and frequencies only. It carries no registration."""

    source: dict  # experimental_file, experimental_path, experimental_sha256, experimental_size, modal_set_title, ...
    records: tuple  # (record number as read, Hz)
    identity: str

    registration = {}  # no physical registration exists in this route
    pairs = ()
    labels = ()


def modal_set(*, experimental_file: str, experimental_path: str = "", experimental_sha256: str, experimental_size: int = 0,
              modal_set_title: str = "", records: Sequence, other_fitted_sets: Sequence[str] = ()) -> PlateModalSet:
    """The records as read. Refused: no record, a repeated record number, a frequency that is not positive and finite,
    a file without a content identity."""
    if not str(experimental_sha256).strip():
        raise rre.EstimationRefused(rre.INVALID_INPUT, "The experimental file has no content identity (it changed while "
                                                       "it was read, or could not be read again). Choose it again.")
    try:
        rows = tuple((int(record), float(hz)) for record, hz in records)
    except (TypeError, ValueError):
        raise rre.EstimationRefused(rre.INVALID_INPUT, "The modal set holds a record without a number or a frequency.") from None
    if not rows:
        raise rre.EstimationRefused(rre.INVALID_INPUT, "The modal set holds no curve-fitted record.")
    numbers = [record for record, _hz in rows]
    if len(set(numbers)) != len(numbers):
        raise rre.EstimationRefused(rre.INVALID_INPUT, "The modal set holds a record number more than once.")
    bad = [record for record, hz in rows if not math.isfinite(hz) or hz <= 0.0]
    if bad:
        raise rre.EstimationRefused(rre.INVALID_INPUT, "Record(s) " + ", ".join(map(str, bad)) + " have no positive, "
                                                       "finite frequency.")
    source = {"experimental_file": str(experimental_file), "experimental_path": str(experimental_path),
              "experimental_sha256": str(experimental_sha256), "experimental_size": int(experimental_size),
              "modal_set_title": str(modal_set_title), "other_fitted_sets": [str(title) for title in other_fitted_sets]}
    return PlateModalSet(source, rows, rre._digest(source, rows))


def plate_problems(plate: rre.Plate) -> list:
    """The declared plate's problems for this route: those of the registered route, and no value 'from the FE model'."""
    problems = rre.plate_problems(plate)
    if any(category == rre.IMPORTED_FE for category in plate.categories):
        problems.append("There is no FE model in the standalone route: state each value as measured or as a declared "
                        "assumption.")
    if plate.material_axis:
        problems.append("The standalone route names no material axis: the constants are given along the plate edges.")
    return problems


def check_request(pset: PlateModalSet, plate: rre.Plate, request: rft.TuningRequest) -> rft.AbaqusPlateInputs:
    """Every refusal, before anything is solved. Returns the plate in the tuning service's form."""
    problems = plate_problems(plate)
    if problems:
        raise rre.EstimationRefused(rre.INVALID_INPUT, " ".join(problems))
    inputs = rre.plate_inputs(plate)
    if {o.record for o in request.observations} != {record for record, _hz in pset.records}:
        raise rre.EstimationRefused(rre.INVALID_INPUT, "The correspondence does not name exactly the records of the modal set.")
    rft.validate_correspondence(request.observations)
    names = rft.PARAMETERIZATIONS[request.parameterization]
    if len(request.fit_rows()) <= len(names):
        raise rre.EstimationRefused(rre.INVALID_INPUT, f"{len(request.fit_rows())} FIT frequencies cannot determine "
                                                       f"{len(names)} parameters; keep more than {len(names)} in the fit.")
    if request.parameterization == rft.TIED and inputs.E1 != inputs.E2:
        raise rre.EstimationRefused(rre.INVALID_INPUT, "The form E1 = E2 needs equal reference E1 and E2; enter equal "
                                                       "values, leave the reference empty or choose the three-parameter form.")
    if not request.search_factor > 1.0:
        raise rre.EstimationRefused(rre.INVALID_INPUT, "The search range factor must exceed 1.")
    return inputs


def _surrogate(inputs: rft.AbaqusPlateInputs, request: rft.TuningRequest) -> rft.Surrogate:
    included = [o for o in request.observations if o.role in (rft.FIT, rft.HOLDOUT)]
    return rft.Surrogate(inputs, request.degree, max(max(o.surrogate_rank for o in included) + 4, 12))


# ---------------------------------------------------------------------------------------------- what stays unresolved


def identities_report(inputs: rft.AbaqusPlateInputs, result: rft.TuningResult, request: rft.TuningRequest) -> dict:
    """Every included record against the Ritz spectrum at the fitted values (the lowest minimum), by frequency alone:
    the rank it was fixed to, the Ritz rank nearest to it in frequency, and the close or degenerate Ritz modes around
    its rank. It resolves nothing; it says where the frequency-only hypothesis is weakest. One Ritz solve."""
    fitted = result.fitted
    try:
        solution = _surrogate(inputs, request).solution(fitted["E1"], fitted["E2"], fitted["G12"])
    except PlateForwardRefusal as refusal:
        raise rre.EstimationRefused(rre.MODEL_REFUSED, f"The Ritz model refuses the fitted values: {refusal.reason}") from refusal
    hz = [float(v) for v in solution.frequencies_hz]
    close = rre._close_groups(hz)
    degenerate = [[int(i) + 1 for i in cluster] for cluster in solution.clusters]
    rows = []
    for o in sorted(request.observations, key=lambda item: item.record):
        if o.role == rft.EXCLUDED:
            rows.append({"record": o.record, "hz": o.hz, "role": o.role, "rank": None, "ritz_hz": None, "nearest_rank": None,
                         "nearest_hz": None, "close_group": None, "status": "EXCLUDED_BY_THE_USER",
                         "note": "not used; no other record takes its place"})
            continue
        rank = o.surrogate_rank
        nearest = int(np.argmin([abs(math.log(value / o.hz)) for value in hz])) + 1
        group = next((g for g in close if rank in g), None)
        notes = []
        if nearest != rank:
            notes.append(f"Ritz rank {nearest} ({hz[nearest - 1]:.3f} Hz) is nearer in frequency than the fixed rank {rank}")
        if any(rank in g for g in degenerate):
            notes.append("the fixed rank is exactly degenerate at the fitted values: its own shape is not defined")
        elif group:
            notes.append("the fixed rank lies among close Ritz modes (ranks " + ", ".join(map(str, group)) + "): their "
                         "order cannot be told by frequency")
        rows.append({"record": o.record, "hz": o.hz, "role": o.role, "rank": rank, "ritz_hz": hz[rank - 1],
                     "nearest_rank": nearest, "nearest_hz": hz[nearest - 1], "close_group": group, "status": UNRESOLVED,
                     "note": "; ".join(notes) or "no shape was compared"})
    correspondence = result.correspondence or {}
    lowest = min(request.observations, key=lambda o: (o.hz, o.record))
    ambiguity = []
    if result.status == rft.MIRROR:
        ambiguity.append("Two minima with the moduli along x and y exchanged fit the frequencies almost equally: which "
                         "plate edge is the stiff one is not identifiable. Both are shown; neither is chosen.")
    others = len(result.minima) - (2 if result.status == rft.MIRROR else 1)
    if others > 0:
        ambiguity.append(f"{others} further minimum/minima were reached from the starts: the fit is not unique in the "
                         "search range. The rows here describe the lowest minimum only; it is not chosen as the answer.")
    nearer = [r["record"] for r in rows if r["status"] == UNRESOLVED and r["nearest_rank"] != r["rank"]]
    if nearer:
        ambiguity.append("Record(s) " + ", ".join(map(str, nearer)) + " are nearer in frequency to another Ritz rank than "
                         "to the fixed one: another correspondence hypothesis may fit as well or better.")
    grouped = [r["record"] for r in rows if r["status"] == UNRESOLVED and r["close_group"]]
    if grouped:
        ambiguity.append("Record(s) " + ", ".join(map(str, grouped)) + " are fixed to close Ritz modes, whose order "
                         "frequencies cannot decide.")
    if correspondence.get("unmatched_ranks"):
        ambiguity.append("Ritz rank(s) " + ", ".join(map(str, correspondence["unmatched_ranks"])) + " below the highest "
                         "used rank have no measured record: a mode missing from the measurement, or a wrong hypothesis.")
    if lowest.role == rft.EXCLUDED:
        ambiguity.append(f"The lowest measured record {lowest.record} ({lowest.hz:.4f} Hz) is EXCLUDED by the user; it "
                         "was not discarded by the program.")
    return {"rows": rows, "ritz_hz": hz, "close_groups": close, "degenerate_groups": degenerate, "ambiguity": ambiguity,
            "lowest_measured_record": lowest.record, "lowest_measured_role": lowest.role,
            "unresolved_records": [r["record"] for r in rows if r["status"] == UNRESOLVED],
            "statement": ("The identity of every included record is UNRESOLVED: " + NO_MAPPING
                          + (" Further ambiguity: " + " ".join(ambiguity) if ambiguity else
                             " No further ambiguity was found by frequency; that does not verify the correspondence."))}


def _fit_rms(cost: float, fit_count: int) -> Optional[float]:
    """The FIT residual RMS (ln f) of a minimum from the optimizer's cost, which is half the sum of squares."""
    return math.sqrt(2.0 * float(cost) / fit_count) if fit_count else None


def _minimum_moduli(result: rft.TuningResult, minimum: Mapping) -> dict:
    return rft._moduli(result.parameter_names, [minimum["values"][n] for n in result.parameter_names], None)


def minima_report(inputs: rft.AbaqusPlateInputs, result: rft.TuningResult, request: rft.TuningRequest) -> list:
    """Every minimum the starts reached, lowest cost first: its values, its FIT RMS and the RMS of its HOLDOUT
    predictions (one Ritz solve each). A list for the reader; nothing is chosen from it."""
    fit_count = len(request.fit_rows())
    holdout = [o for o in request.observations if o.role == rft.HOLDOUT]
    surrogate = _surrogate(inputs, request)
    rows = []
    for number, minimum in enumerate(result.minima, start=1):
        moduli = _minimum_moduli(result, minimum)
        holdout_rms = None
        if holdout:
            try:
                hz = surrogate.frequencies(moduli["E1"], moduli["E2"], moduli["G12"])
                holdout_rms = float(np.sqrt(np.mean(np.square(rft._residuals(hz, holdout)))))
            except (PlateForwardRefusal, rft.TuningRefused):
                holdout_rms = None
        rows.append({"minimum": number, "E1": moduli["E1"], "E2": moduli["E2"], "G12": moduli["G12"],
                     "cost": float(minimum["cost"]), "fit_rms_ln": _fit_rms(minimum["cost"], fit_count),
                     "holdout_rms_ln": holdout_rms})
    return rows


# ---------------------------------------------------------------------------------------------- the estimate


def stiffness_report(result: rft.TuningResult, plate: rre.Plate, minima: Sequence[Mapping]) -> dict:
    """The registered route's stiffness report; for competing minima every minimum is an alternative (none chosen)."""
    report = rre.stiffness_report(result.fitted, plate, result.status, result.minima, result.parameter_names)
    if result.status == rft.STARTS_DISAGREE:
        report["alternatives"] = []
        for row in minima:
            d = rft.bending_stiffness(row["E1"], row["E2"], plate.nu12, row["G12"], plate.thickness_mm)
            rms = row.get("fit_rms_ln")
            report["alternatives"].append({
                "alternative": f"minimum {row['minimum']}" + ("" if rms is None else f" (FIT RMS {rms:.2%})"),
                "D11": d.D11, "D22": d.D22, "D66": d.D66, "D12": d.D12, "E1": row["E1"], "E2": row["E2"], "G12": row["G12"],
                "cost": row["cost"]})
    return report


def presentation_of(status: str, quality: Mapping, minima_count: int = 1) -> dict:
    """Never a supported or verified estimate. ``numerically_consistent``: one estimate (the optimizer converged to it
    from every start, or to it and its exchanged twin), the FIT residuals within the diagnostic threshold and no
    HOLDOUT record disagreeing (the existing levels; none is added)."""
    if status not in SHOWN_STATUSES:
        return {"verdict": NO_ESTIMATE, "reasons": [f"The optimizer status {status} gives no estimate."],
                "numerically_consistent": False}
    reasons = [NO_MAPPING]
    if status == rft.STARTS_DISAGREE:
        reasons.append(f"The starts ended at {minima_count} different minima: there is no single estimate. Every minimum "
                       "is listed as a competing hypothesis with its residuals; none is chosen.")
    if quality.get("verdict") != rft.FIT_WITHIN:
        reasons.append(f"Spectral fit quality {quality.get('verdict')} at the lowest minimum: the model and the rank "
                       "hypothesis do not reproduce the FIT frequencies.")
    if quality.get("holdout_verdict") == rft.HOLDOUT_DISAGREES:
        reasons.append("HOLDOUT record(s) " + ", ".join(map(str, quality.get("holdout_records_off", []))) + " are not "
                       "predicted: the fit does not predict the frequencies it did not use.")
    if quality.get("holdout_verdict") == rft.NO_HOLDOUT:
        reasons.append("There is no HOLDOUT record: nothing outside the fit was predicted.")
    return {"verdict": COMPETING if status == rft.STARTS_DISAGREE else FREQUENCY_ONLY, "reasons": reasons,
            "numerically_consistent": len(reasons) == 1}


def constants_report(result: rft.TuningResult, plate: rre.Plate, presentation: Mapping,
                     thickness_range: Optional[Sequence[float]] = None, minima: Sequence[Mapping] = ()) -> dict:
    """Ex, Ey and Gxy along the plate edges, conditional on the declared thickness, and their values over a stated
    thickness range (exact: with the measured mass held, D does not depend on the thickness and E goes as h^-3)."""
    conditions = (f"thickness {plate.thickness_mm:g} mm, mass {plate.mass_g:g} g, {plate.length_mm:g} x {plate.width_mm:g} "
                  f"mm, nu12 {plate.nu12:g}, the fixed frequency-rank hypothesis and the Kirchhoff-Ritz model")
    reasons = ["Plate-edge axes only: no material axis 1 is named, because this route holds no independent evidence of "
               "the material axes.", "Frequency-only diagnostic hypothesis: no mode identity is established."]
    if presentation["verdict"] == NO_ESTIMATE:
        return {"kind": WITHHELD, "rows": [], "thickness_rows": [], "thickness_range_mm": None, "thickness_note": "",
                "reasons": list(presentation["reasons"]), "conditions": conditions, "axis_evidence": ""}
    tied = "E" in result.parameter_names

    def named(values: Mapping[str, float], prefix: str = "") -> list:
        if tied:
            return [[prefix + "Ex = Ey (tied by the chosen form)", values["E1"]], [prefix + "Gxy", values["G12"]]]
        return [[prefix + "Ex (along x = length a)", values["E1"]], [prefix + "Ey (along y = width b)", values["E2"]],
                [prefix + "Gxy (in the plate's edge axes)", values["G12"]]]

    if result.status == rft.STARTS_DISAGREE:
        reasons.append("The starts ended at different minima: every minimum is listed and none is chosen.")
        rows = []
        for row in minima:
            rows += named(row, f"minimum {row['minimum']}: ")
    elif result.status == rft.MIRROR:
        reasons.append("Two minima with Ex and Ey exchanged fit almost equally: both alternatives are listed and neither "
                       "is chosen.")
        rows = []
        for label, minimum in zip(("alternative A: ", "alternative B: "), result.minima[:2]):
            rows += named(_minimum_moduli(result, minimum), label)
    else:
        rows = named(result.fitted)
    thickness_rows = []
    if thickness_range is not None:
        low, high = (float(v) for v in thickness_range)
        for name, value in rows:
            ends = sorted(value * (end / plate.thickness_mm) ** -3 for end in (low, high))
            thickness_rows.append([name, ends[0], ends[1]])
    return {"kind": PLATE_AXIS_VALUES, "rows": rows, "thickness_rows": thickness_rows,
            "thickness_range_mm": None if thickness_range is None else [float(v) for v in thickness_range],
            "thickness_note": ("Exact scaling of the homogeneous plate with the measured mass held: D11, D22 and D66 do not "
                               "depend on the thickness, and every modulus goes as thickness^-3."
                               + ("" if thickness_range is not None else " No thickness range was stated: the moduli are "
                                  "given at the entered thickness only.")),
            "reasons": reasons, "conditions": conditions, "axis_evidence": ""}


def quantity_table(pset: PlateModalSet, plate: rre.Plate, parameter_names: Sequence[str]) -> list:
    source = pset.source
    categories = dict(zip(rre.INPUT_NAMES, plate.categories))
    where = str(plate.inputs_source).strip()
    surface = plate.mass_g * 1.0e-3 / (plate.length_mm * plate.width_mm * 1.0e-6)
    fitted = ", ".join("Ex = Ey" if n == "E" else {"E1": "Ex", "E2": "Ey", "G12": "Gxy"}[n] for n in parameter_names)
    neutral = tuple(plate.reference) == NEUTRAL_REFERENCE
    return [
        {"quantity": f"Natural frequencies ({len(pset.records)} curve-fitted records)", "category": rre.MEASURED,
         "source": f"{source.get('experimental_file', '')}, SHA-256 {str(source.get('experimental_sha256', ''))[:12]}…, "
                   f"modal set {source.get('modal_set_title', '')}"},
        {"quantity": "Measured mode shapes and point positions", "category": "NOT USED",
         "source": "no physical point mapping is established in this route; no shape is compared"},
        {"quantity": f"Length a {plate.length_mm:g} mm", "category": categories["length"], "source": where},
        {"quantity": f"Width b {plate.width_mm:g} mm", "category": categories["width"], "source": where},
        {"quantity": f"Thickness {plate.thickness_mm:g} mm", "category": categories["thickness"], "source": where},
        {"quantity": f"Mass {plate.mass_g:g} g", "category": categories["mass"], "source": where},
        {"quantity": f"nu12 = {plate.nu12:g}", "category": categories["nu12"] + ", FIXED, NOT IDENTIFIED", "source": where},
        {"quantity": f"Surface mass {surface:.5g} kg/m²", "category": rre.COMPUTED, "source": "mass / (length x width)"},
        {"quantity": "Comparison reference " + ", ".join(f"{n} {v:g}" for n, v in zip(("Ex", "Ey", "Gxy"), plate.reference))
                     + " MPa", "category": "NEUTRAL, NOT A STATEMENT" if neutral else rre.DECLARED,
         "source": "for the 'before' column only; it sets neither the start nor the bounds of the fit"},
        {"quantity": "Record -> Ritz rank correspondence", "category": "HYPOTHESIS FIXED BY THE USER BEFORE THE FIT",
         "source": "frequency rank only: unverified"},
        {"quantity": "Support", "category": rre.DECLARED, "source": "free on all edges; "
                                                                   + (str(plate.suspension).strip() or "no suspension note")},
        {"quantity": f"D11, D22, D66; {fitted}", "category": "FREQUENCY-ONLY DIAGNOSTIC HYPOTHESIS",
         "source": "this fit (Kirchhoff-Ritz model)"},
    ]


def statements(result: rft.TuningResult, block: Mapping) -> list:
    """Seven separate statements: [title, verdict, text]. None of them implies another."""
    quality = result.fit_quality or rft.assess_fit_quality(result.rows)
    identities = block.get("identities") or {}

    def rms(value) -> str:
        return "—" if value is None else f"{value:.2%}"

    return [
        ["1. Optimizer convergence", result.status, "; ".join(result.reasons) or "converged from every start"],
        ["2. Parameter identifiability (rank)", f"practical rank {result.practical_rank} of {len(result.parameter_names)}",
         f"condition number {result.condition_number:.4g}; {len(result.minima)} minimum/minima reached"
         if result.condition_number is not None else "not assessed"],
        ["3. FIT spectral residuals", quality.get("verdict", rft.FIT_NOT_ASSESSED),
         f"RMS {rms(quality.get('fit_rms_ln'))} (ln f) over {quality.get('fit_count', 0)} FIT record(s)"],
        ["4. HOLDOUT predictive residuals", quality.get("holdout_verdict", rft.NO_HOLDOUT),
         f"RMS {rms(quality.get('holdout_rms_ln'))} (ln f) over {quality.get('holdout_count', 0)} HOLDOUT record(s); they "
         "took no part in the fit"],
        ["5. Modal correspondence and ambiguity", rre.RANK_HYPOTHESIS,
         identities.get("statement") or block["correspondence"]["statement"]],
        ["6. Model assumptions", "DECLARED, NOT VERIFIED", " ".join(block.get("assumptions") or ASSUMPTIONS)],
        ["7. Physical validity", rft.NOT_ESTABLISHED, VALIDITY_TEXT],
    ]


def complete(block: dict, result: rft.TuningResult) -> dict:
    """The parts that follow from the saved facts and the result: how it may be presented, the stiffnesses, the
    constants and the statements. Computed here every time, also when a file is opened; never read from a file."""
    plate = rre.plate_from_document(block["plate"])
    quality = result.fit_quality or rft.assess_fit_quality(result.rows)
    minima = block.get("minima") or []
    if len(minima) != len(result.minima):
        raise rft.TuningRefused("The standalone-plate part does not list the minima of its own result.")
    for number, (row, minimum) in enumerate(zip(minima, result.minima), start=1):
        row.update(_minimum_moduli(result, minimum))  # the result's own values; only the HOLDOUT RMS is a saved fact
        row.update(minimum=number, cost=float(minimum["cost"]),
                   fit_rms_ln=_fit_rms(minimum["cost"], quality.get("fit_count", 0)))
    block["presentation"] = presentation_of(result.status, quality, len(minima))
    block["stiffness"] = rre._plain(stiffness_report(result, plate, minima))
    block["constants"] = rre._plain(constants_report(result, plate, block["presentation"], block.get("thickness_range_mm"),
                                                     minima))
    block["statements"] = rre._plain(statements(result, block))
    return block


def thickness_range_of(plate: rre.Plate, ranges: Optional[Mapping[str, Sequence[float]]]) -> Optional[list]:
    """The stated thickness range, checked by the uncertainty service's own rule; None when none is stated."""
    if not ranges or "thickness" not in ranges:
        return None
    problems = rru.range_problems(plate, {"thickness": ranges["thickness"]})
    if problems:
        raise rre.EstimationRefused(rre.INVALID_INPUT, " ".join(problems))
    return [float(v) for v in ranges["thickness"]]


def run_estimation(pset: PlateModalSet, plate: rre.Plate, request: rft.TuningRequest, cancel=None, progress=None,
                   ranges: Optional[Mapping[str, Sequence[float]]] = None) -> tuple:
    """(result, block). ``request`` holds the FIXED rank hypothesis and roles; ``ranges``: the stated input ranges, of
    which only the thickness is used here (for the conditional moduli). Refused before anything is solved: an
    inadmissible plate, an invalid correspondence, too few FIT records, an invalid thickness range."""
    inputs = check_request(pset, plate, request)
    thickness_range = thickness_range_of(plate, ranges)
    names = rft.PARAMETERIZATIONS[request.parameterization]
    request = replace(request, tracked_spectrum=None)
    try:
        result = rft.run_tuning(inputs, request, (), cancel, progress,
                                "not used: there is no FE model; measured frequencies are compared with the Ritz model only")
    except PlateForwardRefusal as refusal:
        raise rre.EstimationRefused(rre.MODEL_REFUSED, f"The Ritz model refused a value during the fit: {refusal.reason}") from refusal
    except rft.TuningRefused as refusal:
        if "nu12*nu21" not in str(refusal):
            raise
        limit = f"below about {1.0 / abs(plate.nu12):.3g}" if plate.nu12 else "smaller"
        raise rre.EstimationRefused(rre.MODEL_REFUSED, (
            "The search reached values that are not admissible with the fixed nu12 (1 - nu12^2 Ey / Ex must stay "
            f"positive). Nothing was estimated. Use a smaller search range factor (for nu12 = {plate.nu12:g}: {limit}) "
            "or the form with one in-plane modulus.")) from refusal
    if result.status == rft.CANCELLED:
        return result, None
    statistical = {n: math.exp(v) - 1.0 for n, v in (result.log_sd or {}).items()}
    result = replace(
        result, quantities=quantity_table(pset, plate, names), assumptions=ASSUMPTIONS,
        warnings=[w for w in result.warnings if not w.startswith("FE classification unavailable")],
        accuracy_statement=("Frequency errors are not parameter errors. The statistical SD is conditional on the model, the "
                            "fixed rank hypothesis and the entered inputs; it leaves out the thickness, mass and dimension "
                            "uncertainty, the support and any wrong correspondence."
                            + (" Statistical SD: " + ", ".join(f"{n} ±{v:.1%}" for n, v in statistical.items())
                               if statistical else "")))
    block = {"schema": SCHEMA, "label": LABEL, "source": pset.source, "registration": {}, "set_identity": pset.identity,
             "plate": rre.plate_document(plate), "records": [[record, hz] for record, hz in pset.records], "fe_pairs": [],
             "frame": [], "review": None, "thickness_range_mm": thickness_range,
             "correspondence": {"kind": rre.RANK_HYPOTHESIS, "reference": None, "fitted": None,
                                "statement": CORRESPONDENCE_STATEMENT},
             "branch": {"verdict": rre.BRANCHES_NOT_FOLLOWED, "rows": [],
                        "statement": "No shape is compared in this route: the fixed ranks are plain frequency ranks."},
             "identities": identities_report(inputs, result, request),
             "minima": minima_report(inputs, result, request),
             "assumptions": list(ASSUMPTIONS), "validity": VALIDITY_TEXT}
    block = rre._plain(block)
    return result, complete(block, result)


def run_uncertainty(pset: PlateModalSet, plate: rre.Plate, request: rft.TuningRequest, result: rft.TuningResult,
                    ranges: Mapping[str, Sequence[float]], cancel=None, progress=None) -> Optional[dict]:
    """The uncertainty service's sensitivities and one-input ranges, every refit by this route's own fit. Like that
    service it needs ONE estimate: a result with competing minima is refused there."""
    return rru.run_uncertainty(pset, plate, request, None, result, ranges, cancel, progress,
                               estimate=lambda changed, same, c, p: run_estimation(pset, changed, same, c, p))


def export_document(result: rft.TuningResult, block: Mapping, stability: Optional[Mapping] = None) -> dict:
    """The tuning service's export of the result with the standalone part; no Abaqus block is written (there is no INP)."""
    plate = rre.plate_from_document(block["plate"])
    source = block["source"]
    sources = {"inp": "", "inp_sha256": "", "dat": "", "unv": source.get("experimental_path") or source.get("experimental_file", ""),
               "unv_sha256": source.get("experimental_sha256", ""), "modal_set": source.get("modal_set_title", "")}
    document = rft.export_document(result, rre.plate_inputs(plate), sources, stability)
    document[EXPORT_KEY] = dict(block)
    document["statement"] = ("Frequency-only diagnostic hypothesis of a standalone Kirchhoff-Ritz plate: no FE model, no "
                             "physical point mapping, no mode identity. Not a verified estimate, not a material property, "
                             "not a production identification. " + LABEL)
    return document


_BLOCK_KEYS = ("schema", "label", "source", "set_identity", "plate", "records", "correspondence", "branch", "identities",
               "minima", "assumptions", "validity")


def block_from_export(document: Mapping, result: rft.TuningResult) -> Optional[dict]:
    """The standalone part of an export, or None when the export has none. The presentation, the stiffnesses, the
    constants and the statements are computed again from the saved facts; a file cannot raise its own status."""
    block = document.get(EXPORT_KEY)
    if block is None:
        return None
    if not isinstance(block, dict) or block.get("schema") != SCHEMA or block.get("label") != LABEL:
        raise rft.TuningRefused("The export holds a standalone-plate part of another version; it is not opened.")
    missing = [key for key in _BLOCK_KEYS if key not in block]
    if missing:
        raise rft.TuningRefused(f"The standalone-plate part is incomplete: {', '.join(missing)} missing.")
    block = rft.restore_record_keys(dict(block))
    try:
        if block["correspondence"]["kind"] != rre.RANK_HYPOTHESIS:
            raise rft.TuningRefused("The standalone-plate part names a correspondence this route cannot have.")
        block["correspondence"]["statement"] = CORRESPONDENCE_STATEMENT
        plate = rre.plate_from_document(block["plate"])
        problems = plate_problems(plate)
        if problems:
            raise rft.TuningRefused("The saved plate is not admissible: " + " ".join(problems))
        saved_range = block.get("thickness_range_mm")
        block["thickness_range_mm"] = thickness_range_of(plate, {"thickness": saved_range} if saved_range else None)
        for row in block["identities"]["rows"]:
            row["record"], row["status"], row["note"], row["role"]
        block["identities"]["ambiguity"], block["identities"]["statement"]
        complete(block, result)
    except rft.TuningRefused:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        raise rft.TuningRefused(f"The standalone-plate part is damaged ({type(error).__name__}: {error}).") from None
    return block


__all__ = ["ASSUMPTIONS", "COMPETING", "EXPORT_KEY", "FREQUENCY_ONLY", "INPUT_CATEGORIES", "LABEL", "NEUTRAL_REFERENCE",
           "NO_ESTIMATE", "NO_MAPPING", "PLATE_AXIS_VALUES", "PlateModalSet", "SCHEMA", "SHOWN_STATUSES", "UNRESOLVED",
           "WITHHELD", "block_from_export", "check_request", "complete", "constants_report", "export_document",
           "identities_report", "minima_report", "modal_set", "plate_problems", "presentation_of", "quantity_table",
           "run_estimation", "run_uncertainty", "statements", "stiffness_report", "thickness_range_of"]
