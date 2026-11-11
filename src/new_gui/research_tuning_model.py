"""REAL-FIT.R1: what the Research Tuning page reads, computes and draws, with no Qt.

The page tunes the ASSUMED CFRP inputs of an Abaqus plate INP against measured PolyMAX frequencies with the research service
``services.research_frequency_tuning`` (a Kirchhoff-Ritz surrogate; no Abaqus, no FE solve). The experimental file is read by
the program's own importer (``preview_model``); only curve-fitted records are used, never FRF peak records. Nothing here is
a material property: every result carries the service's label.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import threading
from typing import Optional

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from new_gui import analyze_model as am
from new_gui import preview_model as pm
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import modal_data_viewer as viewer
from services import registered_ritz_estimation as rre
from services import research_frequency_tuning as rft

LABEL = rft.RESULT_LABEL
SURROGATE_NOTE = ("Ritz values are frequencies of the Kirchhoff plate surrogate, not Abaqus FE results. A candidate is a "
                  "proposal for a new Abaqus solve; only that solve can confirm it.")
# ABM-AUD-1: what the optimizer status says, and only that. The spectral fit quality and the physical validity are separate.
STATUS_TEXT = {
    rft.SUPPORTED: ("Optimizer: converged, full practical rank, no bound, the starts agree. A numerical statement only: it "
                    "does not say that the model reproduces the spectrum (see the spectral fit quality)."),
    rft.MIRROR: ("Optimizer: converged to two minima with E1 and E2 exchanged. Numerical estimates E_stiff, E_soft, G12; no "
                 "oriented candidate, because which plate axis is stiff is not identifiable."),
    rft.NOT_IDENTIFIABLE: "Optimizer: no candidate, the selected frequencies cannot separate the parameters.",
    rft.AT_BOUND: "Optimizer: no candidate, a parameter ended at its bound.",
    rft.NOT_CONVERGED: "Optimizer: no candidate, the fit did not converge.",
    rft.STARTS_DISAGREE: "Optimizer: no candidate, different starts end at different minima.",
    rft.CANCELLED: "Cancelled. No result.",
}
OPTIMIZER_SHORT = {
    rft.SUPPORTED: "converged (full rank, no bound, starts agree)", rft.MIRROR: "converged, E1 / E2 axis not identifiable",
    rft.NOT_IDENTIFIABLE: "parameters not separable", rft.AT_BOUND: "parameter at a bound",
    rft.NOT_CONVERGED: "not converged", rft.STARTS_DISAGREE: "competing minima", rft.CANCELLED: "cancelled",
}
CORRESPONDENCE_HINT = ("Surrogate rank: the rank each record is compared with. By default it is the record's place in the "
                       "frequency order of the whole measured set, so HOLDOUT or EXCLUDED never renumbers another record. "
                       "To state a different correspondence, declare it (record:rank); nothing is re-matched automatically.")
STALE_TEXT = "The settings changed: the previous result was cleared. Run the tuning again to see a result for these settings."
EXPORT_FILTER = "Research tuning proposal (*.json)"
DPI = 100


ANALYZE_NOTE = ("Still available: the Analyze page shows the FE and EXP shapes and runs registration and comparison from "
                "this model's ODB and the EXP file; none of that needs this INP.")


class ReadFailed(ValueError):
    def __init__(self, message: str, compatibility: Optional[rft.InpCompatibility] = None):
        super().__init__(message)
        self.compatibility = compatibility


def check_model(inp_path) -> rft.InpCompatibility:
    """ABM-REAL-INPUT-1: what the INP is and whether Research Tuning reads it, from its text alone. A model it does not read
    is a ReadFailed carrying the report; nothing is converted."""
    try:
        report = rft.inspect_inp(inp_path)
    except (OSError, ValueError) as error:
        raise ReadFailed(f"The INP could not be used: {error}") from error
    if not report.supported:
        raise ReadFailed(f"The INP could not be used: {report.reason}", report)
    return report


def compatibility_rows(report: rft.InpCompatibility) -> tuple:
    return tuple((what, value) for what, value in report.facts)


def compatibility_notes(report: rft.InpCompatibility) -> str:
    """What the owner can still do with a model this page does not read. Files beside the INP are only looked up by name;
    an extracted package is used by Analyze only when it matches the ODB."""
    if report.supported:
        return ""
    inp = Path(report.inp_path)
    lines = [ANALYZE_NOTE]
    odb = inp.with_suffix(".odb")
    if odb.is_file():
        folder = am.package_folder(odb)
        lines.append(f"{odb.name} is beside the INP" + (f", with extracted modes in {folder.name}; Analyze uses them "
                                                        "without Abaqus when they match that ODB" if folder.is_dir() else "")
                     + ". This does not enable Research Tuning.")
    return "\n".join(lines)


@dataclass(frozen=True)
class Sources:
    inputs: rft.AbaqusPlateInputs
    dat_path: Optional[str]
    dat_rows: tuple  # (mode, Hz) of the .dat beside the INP, unclassified
    fe_elastic: tuple  # (mode, Hz) of the elastic FE modes classified by shape, or () when no classification exists
    fe_classification: str
    unv_path: str
    unv_sha256: str
    set_title: str
    records: tuple  # (record number, Hz) of the curve-fitted records
    compatibility: Optional[rft.InpCompatibility] = None  # ABM-REAL-INPUT-1: what the INP is


def _classify(odb, cancel) -> tuple:
    """(elastic (mode, Hz), text), by the comparator's shape-based rigid-body criterion on an already extracted package of
    this ODB's content. Abaqus is never started: without such a package the classification is unavailable."""
    if not odb:
        return (), "unavailable: no ODB chosen, so no FE mode shapes"
    try:
        plan = am.make_plan(odb, discover=lambda: ())
        manifest = am.find_package(plan, cancel)
    except (am.StepFailed, am.StepCancelled) as error:
        return (), f"unavailable: {error}"
    if manifest is None:
        return (), "unavailable: no extracted modes of this ODB's content (Abaqus is not started here)"
    outcome = pm.run_read(FE, manifest, 0, cancel)
    if outcome.error or outcome.cancelled:
        return (), f"unavailable: {outcome.error or 'cancelled'}"
    dataset = outcome.preview.dataset
    residuals = viewer.classify_rigid_body_fe_modes(dataset)
    threshold = viewer.rigid_body_threshold()
    modes = [(int(m.number), float(m.frequency_hz)) for m in dataset.sorted_modes()]
    rigid = [n for n, _f in modes if residuals.get(n, 1.0) <= threshold]
    elastic = tuple((n, f) for n, f in modes if residuals.get(n, 1.0) > threshold)
    return elastic, (f"shape-based (rigid-body shape projection residual <= {threshold:g}, the comparator's criterion): "
                     f"rigid {', '.join(map(str, rigid)) or 'none'}; elastic from mode {elastic[0][0] if elastic else '-'}; "
                     f"package {Path(manifest).parent.name}")


def read_sources(inp_path, unv_path, cancel: threading.Event, odb_path=None) -> Sources:
    """The INP (and its .dat, when present beside it), an optional ODB for the shape-based FE classification, and the
    fitted modes of the experimental file. Read only."""
    report = check_model(inp_path)
    try:
        inputs = rft.read_inp(inp_path)
    except rft.InpNotSupported as error:
        raise ReadFailed(f"The INP could not be used: {error}", error.report) from error
    except (OSError, rft.TuningRefused) as error:
        raise ReadFailed(f"The INP could not be used: {error}") from error
    dat = Path(inp_path).with_suffix(".dat")
    rows = ()
    if dat.is_file():
        try:
            rows = rft.read_dat_frequencies(dat)
        except rft.TuningRefused:
            rows = ()
    elastic, classification = _classify(odb_path, cancel)
    outcome = pm.run_read(EXPERIMENTAL, unv_path, 0, cancel)
    if outcome.cancelled:
        raise ReadFailed("Cancelled.")
    if outcome.error:
        raise ReadFailed(outcome.error)
    fitted = [item for item in outcome.preview.sets if item.records and not any(r.provisional for r in item.records)]
    if not fitted:
        raise ReadFailed("The experimental file holds no curve-fitted modal set; FRF peak records are never used as modes.")
    chosen = fitted[0]
    records = tuple((int(r.number), float(r.frequency_hz)) for r in chosen.records)
    identity = outcome.identity or {}
    return Sources(inputs, str(dat) if rows else None, rows, elastic, classification, str(unv_path),
                   str(identity.get("sha256", "")), chosen.title, records, report)


def default_holdout(records) -> tuple:
    """The two highest records: a prediction check above the fitted range."""
    ordered = sorted(records, key=lambda item: item[1])
    return tuple(record for record, _hz in ordered[-2:]) if len(ordered) > 5 else ()


def parse_declared(text: str) -> dict:
    """"3:4, 4:3" -> {3: 4, 4: 3}: experimental record -> surrogate elastic rank. Raises ValueError."""
    mapping = {}
    for part in (p.strip() for p in str(text).split(",")):
        if not part:
            continue
        pieces = [piece.strip() for piece in part.split(":")]
        if len(pieces) != 2 or not all(piece.lstrip("-").isdigit() for piece in pieces):
            raise ValueError(f"Declared ranks: '{part}' is not record:rank with two whole numbers.")
        record, rank = int(pieces[0]), int(pieces[1])
        if record in mapping:
            raise ValueError(f"Declared ranks: record {record} is given more than once.")
        if rank < 1:
            raise ValueError(f"Declared ranks: record {record} has rank {rank}; a rank starts at 1.")
        mapping[record] = rank
    return mapping


def correspondence_preview(records, roles, declared_text: str) -> tuple:
    """({record: rank text}, problem) of the correspondence the page would fit now, by the service's own rules. ``problem``
    is "" when it is valid, otherwise the service's refusal; with a problem the ranks are the default ones, for reading."""
    roles = dict(roles)
    holdout = [r for r, role in roles.items() if role == rft.HOLDOUT]
    excluded = [r for r, role in roles.items() if role == rft.EXCLUDED]
    problem = ""
    try:
        observations = rft.observations_by_rank(records, holdout=holdout, excluded=excluded,
                                                declared=parse_declared(declared_text))
        try:
            rft.validate_correspondence(observations)
        except rft.TuningRefused as error:
            problem = str(error)
    except (ValueError, KeyError) as error:  # TuningRefused is a ValueError
        problem = str(error)
        observations = rft.observations_by_rank(records, holdout=holdout, excluded=excluded)
    default = rft.default_ranks(records)
    texts = {}
    for o in observations:
        if o.role == rft.EXCLUDED:
            texts[o.record] = "— (excluded; no other record takes rank " + str(default[o.record]) + ")"
        elif o.surrogate_rank != default[o.record]:
            texts[o.record] = f"{o.surrogate_rank} (declared; default {default[o.record]})"
        else:
            texts[o.record] = str(o.surrogate_rank)
    return texts, problem


def quality_of(result: rft.TuningResult) -> dict:
    return result.fit_quality or rft.assess_fit_quality(result.rows)


def _rms(value) -> str:
    return "—" if value is None else f"{value:.2%}"


def headline(result: rft.TuningResult) -> dict:
    """ABM-AUD-1: the three separate statements of a result, short enough to read at once, and the badge states.
    ``state``: "blocked" (the warning colour) unless there is an oriented candidate that may be shown as a proposal."""
    quality = quality_of(result)
    verdict = quality.get("verdict", rft.FIT_NOT_ASSESSED)
    high, off = verdict == rft.HIGH_MISFIT, quality.get("holdout_verdict") == rft.HOLDOUT_DISAGREES
    fit = {rft.HIGH_MISFIT: (f"SPECTRAL FIT: HIGH MISFIT — FIT RMS {_rms(quality.get('fit_rms_ln'))} is above the "
                             f"{rft.MISFIT_RMS:.0%} diagnostic threshold. The model and correspondence do not reproduce "
                             "the measured spectrum."),
           rft.FIT_WITHIN: (f"SPECTRAL FIT: FIT RMS {_rms(quality.get('fit_rms_ln'))}, within the {rft.MISFIT_RMS:.0%} "
                            "diagnostic threshold."),
           rft.FIT_NOT_ASSESSED: "SPECTRAL FIT: not assessed."}[verdict]
    if quality.get("holdout_count"):
        fit += (f" HOLDOUT RMS {_rms(quality.get('holdout_rms_ln'))}"
                + (" — HOLDOUT DISAGREES (record " + ", ".join(map(str, quality.get("holdout_records_off", [])))
                   + " more than 5 % off)." if off else "."))
    else:
        fit += " No HOLDOUT record."
    proposal = result.candidate_presentation == rft.PROPOSAL
    return {
        "optimizer": f"OPTIMIZER: {result.status} — {OPTIMIZER_SHORT.get(result.status, result.status)}.",
        "fit": fit, "fit_state": "blocked" if high or off or verdict == rft.FIT_NOT_ASSESSED else "chosen",
        "validity": ("PHYSICAL VALIDITY: NOT ESTABLISHED — research only. No mode identity, no material property, no "
                     "Abaqus check; convergence and a small residual are not a validation."),
        "state": "chosen" if proposal and not off else "blocked",
        "high_misfit": high, "holdout_disagrees": off, "proposal": proposal,
    }


def fit_quality_rows(result: rft.TuningResult) -> tuple:
    q = quality_of(result)

    def largest(item):
        return "—" if not item else f"record {item['record']}: {_pct(item['ln'])}"

    rows = [("Spectral fit quality", q.get("verdict", rft.FIT_NOT_ASSESSED)),
            ("FIT residual RMS (ln f)", f"{_rms(q.get('fit_rms_ln'))} over {q.get('fit_count', 0)} FIT record(s)"),
            ("Diagnostic threshold (unchanged)", f"{rft.MISFIT_RMS:.0%}"),
            ("Largest FIT residual", largest(q.get("largest_fit_residual"))),
            ("HOLDOUT (not fitted)", q.get("holdout_verdict", rft.NO_HOLDOUT)),
            ("HOLDOUT residual RMS (ln f)", f"{_rms(q.get('holdout_rms_ln'))} over {q.get('holdout_count', 0)} HOLDOUT record(s)"),
            ("Largest HOLDOUT residual", largest(q.get("largest_holdout_residual"))),
            ("Meaning", q.get("statement", ""))]
    if q.get("derived_when_opened"):
        rows.append(("Origin", "Derived from the saved residuals when the file was opened (saved before this assessment "
                               "existed); nothing was re-fitted."))
    return tuple(rows)


def correspondence_rows(result: rft.TuningResult) -> tuple:
    c = result.correspondence or {}
    if not c:
        return ()
    rows = [("Kind", c.get("identity", "")), ("Method", {rft.RANK_ORDER: "default rank order of the full measured set",
                                                         rft.DECLARED: "default rank order with ranks declared by the user"}
                                              .get(c.get("method"), str(c.get("method")))),
            ("Record -> surrogate rank", ", ".join(f"{record} -> {rank}" for record, rank in sorted(c.get("ranks", {}).items()))
             or "none"),
            ("EXCLUDED records (no rank)", ", ".join(map(str, c.get("excluded_records", []))) or "none"),
            ("Surrogate ranks without a measured record", ", ".join(map(str, c.get("unmatched_ranks", []))) or "none")]
    rows += [("Note", note) for note in c.get("notes", [])]
    rows.append(("Not established", c.get("identity_note", "")))
    return tuple(rows)


def input_rows(sources: Sources) -> tuple:
    i = sources.inputs

    def text(value, unit=""):
        return "not in this definition" if value is None else f"{value:g}{unit}"

    rows = [("Material", i.material), ("Elastic type", i.elastic_type), ("E1", text(i.E1, " MPa")), ("E2", text(i.E2, " MPa")),
            ("E3", text(i.E3, " MPa")), ("nu12", text(i.nu12)), ("nu13", text(i.nu13)), ("nu23", text(i.nu23)),
            ("G12", text(i.G12, " MPa")), ("G13", text(i.G13, " MPa")), ("G23", text(i.G23, " MPa")),
            ("Density", f"{i.density_t_mm3:g} t/mm³"), ("Shell thickness", f"{i.thickness_mm:g} mm"),
            ("Plan (from the nodes)", f"{i.a_mm:g} × {i.b_mm:g} mm"), ("Model mass", f"{i.mass_g:.2f} g"),
            ("Material orientation", "*Orientation present" if i.has_orientation else "none: global axes")]
    rows.append(("Stored FE frequencies (.dat)", f"{len(sources.dat_rows)} modes, unclassified" if sources.dat_rows
                 else "no .dat beside the INP"))
    rows.append(("FE classification", sources.fe_classification))
    if sources.fe_elastic:
        rows.append(("Elastic FE modes (by shape)", f"{len(sources.fe_elastic)}, first mode {sources.fe_elastic[0][0]} at "
                                                     f"{sources.fe_elastic[0][1]:g} Hz"))
    return tuple(rows)


def _pct(value) -> str:
    return "—" if value is None else f"{100.0 * (np.exp(value) - 1.0):+.2f} %"


def frequency_rows(result: rft.TuningResult) -> tuple:
    return tuple((str(r["record"]), r["role"], "—" if r["rank"] is None else str(r["rank"]), f"{r['exp_hz']:.4f}",
                  "—" if r["ritz_before_hz"] is None else f"{r['ritz_before_hz']:.3f}", _pct(r["ln_before"]),
                  "—" if r["ritz_after_hz"] is None else f"{r['ritz_after_hz']:.3f}", _pct(r["ln_after"]))
                 for r in result.rows)


FREQUENCY_HEADERS = ("EXP record", "Role", "Surrogate rank", "EXP (Hz)", "Ritz at INP values (Hz)", "Error before",
                     "Ritz at fitted values (Hz)", "Error after")
REGISTERED_FREQUENCY_HEADERS = ("EXP record", "Role", "Fixed Ritz rank (at the reference)", "EXP (Hz)",
                                "Ritz at reference values (Hz)", "Error before", "Ritz at fitted values (Hz)", "Error after")


def candidate_rows(result: rft.TuningResult) -> tuple:
    if not result.candidate:
        return ()
    return tuple((name, f"{result.baseline[name]:g}", f"{result.candidate[name]:.0f}",
                  f"{100.0 * (result.candidate[name] / result.baseline[name] - 1.0):+.1f} %") for name in ("E1", "E2", "G12"))


CANDIDATE_HEADERS = ("Input", "INP value (MPa)", "Candidate (MPa)", "Change")
DIAGNOSTIC_CANDIDATE_HEADERS = ("Input", "INP value (MPa)", "DIAGNOSTIC ONLY, HIGH MISFIT (MPa)", "Change")
CANDIDATE_TITLE = "Oriented Abaqus input candidate (only when the axes are resolved)"
DIAGNOSTIC_CANDIDATE_NOTE = ("DIAGNOSTIC ONLY — NOT A PROPOSAL. The optimizer converged, but the spectral fit is a HIGH "
                             "MISFIT, so these numbers absorb model-form or correspondence error. They are shown for "
                             "investigation; no Abaqus *Elastic block is exported for them.")
DIAGNOSTIC_ESTIMATE_NOTE = ("DIAGNOSTIC ONLY: the spectral fit is a HIGH MISFIT. These numbers are the optimizer's raw "
                            "result, kept for investigation; they are not usable estimates.")


def candidate_headers(result: rft.TuningResult) -> tuple:
    return CANDIDATE_HEADERS if result.candidate_presentation != rft.DIAGNOSTIC_ONLY else DIAGNOSTIC_CANDIDATE_HEADERS


def candidate_note(result: rft.TuningResult) -> str:
    """What stands above (or instead of) the candidate table."""
    if result.candidate:
        return DIAGNOSTIC_CANDIDATE_NOTE if result.candidate_presentation == rft.DIAGNOSTIC_ONLY else (
            "A proposal for a new Abaqus solve only; not validated in Abaqus and not a material property.")
    return "None: " + ("the E1 / E2 axis assignment is unresolved, so no oriented *Elastic block is given."
                       if result.status == rft.MIRROR else "the optimizer status gives no candidate.")


def estimate_rows(result: rft.TuningResult) -> tuple:
    if not result.estimates:
        return ()
    sd = {}
    if result.log_sd and "E1" in result.parameter_names:  # E_stiff / E_soft take the SD of the axis that carries them
        stiff, soft = ("E1", "E2") if result.fitted["E1"] >= result.fitted["E2"] else ("E2", "E1")
        sd = {"E_stiff": result.log_sd[stiff], "E_soft": result.log_sd[soft], "G12": result.log_sd["G12"]}
    elif result.log_sd:
        sd = {"E (E1 = E2)": result.log_sd["E"], "G12": result.log_sd["G12"]}
    return tuple((name, f"{value:.0f}", "—" if name not in sd else f"±{np.exp(sd[name]) - 1:.1%}")
                 for name, value in result.estimates.items())


ESTIMATE_HEADERS = ("Research estimate", "Value (MPa)", "Statistical SD (model-conditional; not a certified accuracy)")
DIAGNOSTIC_ESTIMATE_HEADERS = ("Optimizer result (diagnostic only)", "Value (MPa), HIGH MISFIT",
                               "Statistical SD (model-conditional; not a certified accuracy)")


def estimate_headers(result: rft.TuningResult) -> tuple:
    return DIAGNOSTIC_ESTIMATE_HEADERS if quality_of(result).get("verdict") == rft.HIGH_MISFIT else ESTIMATE_HEADERS


def axis_rows(result: rft.TuningResult) -> tuple:
    return tuple((a["assignment"], f"{a['E1 (FE X)']:.0f}", f"{a['E2 (FE Y)']:.0f}", f"{a['G12']:.0f}", f"{a['cost']:.6g}")
                 for a in result.axis_assignments)


AXIS_HEADERS = ("Possible axis assignment (none chosen)", "E1 along FE X (MPa)", "E2 along FE Y (MPa)", "G12 (MPa)", "Cost")


def quantity_rows(result: rft.TuningResult) -> tuple:
    return tuple((q["quantity"], q["category"], q["source"]) for q in result.quantities)


QUANTITY_HEADERS = ("Quantity", "Category", "Source")


def first_mode_rows(result: rft.TuningResult) -> tuple:
    check = result.first_mode_check
    origin = ()
    if check and check.get("lowest_measured_role") == rft.EXCLUDED:
        origin = (("Lowest measured record", f"record {check['lowest_measured_record']} is EXCLUDED by the user; this check "
                                             "concerns the lowest record that is kept, at its own unchanged rank"),)
    if not check or not check.get("done"):
        return origin + (("Lowest record left out", (check or {}).get("reason", "not run")),)
    rows = list(origin) + [("Left out for this check only", f"record {check['left_out_record']} at "
                                                            f"{check['left_out_hz']:.4f} Hz (surrogate rank "
                                                            f"{check.get('left_out_rank', '—')}); every other record keeps "
                                                            "its rank")]
    rows += [(f"{('E1 = E2' if name == 'E' else name)} without it", f"{value:.0f} MPa ({check['change'][name]:+.1%})")
             for name, value in check["values"].items()]
    rows.append(("Condition number without it", f"{check['condition_number']:.4g}"))
    return tuple(rows)


def assumption_rows(result: rft.TuningResult) -> tuple:
    return tuple((row["assumption"], f"× {row['moduli_factor']:.3f}") for row in result.assumption_sensitivity)


def minima_rows(result: rft.TuningResult) -> tuple:
    return tuple((str(index + 1), ", ".join(f"{k} {v:.0f}" for k, v in m["values"].items()), f"{m['cost']:.6g}")
                 for index, m in enumerate(result.minima))


def diagnostic_rows(result: rft.TuningResult) -> tuple:
    quality = quality_of(result)
    rows = [("Optimizer status", result.status), ("Spectral fit quality", quality.get("verdict", rft.FIT_NOT_ASSESSED)),
            ("Physical validity", rft.NOT_ESTABLISHED), ("Candidate presentation", result.candidate_presentation),
            ("Label", result.label), ("Parameters fitted", ", ".join(result.parameter_names)),
            ("Correspondence", "Rank order of the full measured set (a frequency hypothesis), with any declared ranks; an "
             "EXCLUDED record leaves its rank unmatched. It is not a mode identity: a missing or extra measured mode "
             "cannot be ruled out from the frequencies"
             if not (result.correspondence or {}).get("legacy_renumbered_ranks") else
             "As saved by an earlier version: rank order of the kept frequencies, renumbered after EXCLUDED records"),
            ("Initialization", f"{result.initialization.get('method', '—')}; INP values not used"),
            ("Data-scaled start", ", ".join(f"{k} {v:.0f}" for k, v in result.initialization.get("start", {}).items())),
            ("Search bounds", "; ".join(f"{k} {lo:.0f} to {hi:.0f}" for k, (lo, hi) in result.initialization.get("bounds", {}).items())),
            ("Forward solves", str(result.evaluations)),
            ("Singular values (d ln f / d ln p)", ", ".join(f"{v:.4g}" for v in result.singular_values)),
            ("Practical rank", f"{result.practical_rank} of {len(result.parameter_names)}"),
            ("Condition number", "—" if result.condition_number is None else f"{result.condition_number:.4g}"),
            ("Active bounds", ", ".join(result.active_bounds) or "none"),
            ("FIT RMS before / after (ln f)", f"{result.rms_fit_before:.4f} / " + ("—" if result.rms_fit_after is None
                                                                               else f"{result.rms_fit_after:.4f}")),
            ("HOLDOUT RMS before / after (ln f)", "—" if result.rms_holdout_before is None else
             f"{result.rms_holdout_before:.4f} / {result.rms_holdout_after:.4f}")]
    if result.log_sd:
        rows.append(("Statistical SD of ln p (conditional on the model)", ", ".join(f"{k} {v:.3g}" for k, v in result.log_sd.items())))
    if result.correlation:
        rows.append(("Parameter correlation", "; ".join(", ".join(f"{v:+.3f}" for v in row) for row in result.correlation)))
    for index, start in enumerate(result.starts):
        rows.append((f"Start {index + 1} from " + ", ".join(f"{k} {v:.0f}" for k, v in start["start"].items()),
                     ", ".join(f"{k} {v:.0f}" for k, v in start["values"].items()) + f"; cost {start['cost']:.6g}"))
    return tuple(rows)


def sensitivity_rows(result: rft.TuningResult) -> tuple:
    return tuple((str(row["record"]),) + tuple(f"{row[name]:+.4f}" for name in result.parameter_names) for row in result.sensitivity)


def surrogate_rows(result: rft.TuningResult) -> tuple:
    return tuple((str(r["rank"]), str(r["fe_mode"]), f"{r['fe_hz']:g}", f"{r['ritz_hz']:.3f}", f"{100 * r['ritz_over_fe_minus_1']:+.2f} %")
                 for r in result.surrogate)


SURROGATE_HEADERS = ("Elastic rank (by shape)", "Abaqus mode", "Abaqus (Hz)", "Ritz at INP values (Hz)", "Ritz / Abaqus − 1")


STABILITY_NOTE = ("Each FIT record is left out once; every other record keeps its role and its declared rank (nothing is "
                  "renumbered or rematched). Estimates are compared without an axis: E (E1 = E2) and G12, or E_stiff, "
                  "E_soft and G12. Research only: stability is not accuracy.")


def _signed(value) -> str:
    return "—" if value is None else f"{value:+.2%}"


def stability_headers(stability: dict) -> tuple:
    names = tuple(stability["baseline"]["estimates"])
    return (("Left out", "Rank", "EXP (Hz)") + tuple(f"{n} change" for n in names)
            + ("FIT RMS (ln f)", "Left-out error", "Holdout RMS", "Rank / cond.", "Converged", "Bounds", "Minima"))


def stability_rows(stability: dict) -> tuple:
    names = tuple(stability["baseline"]["estimates"])
    rows = []
    for item in stability["leave_one_out"]:
        if not item.get("done"):
            rows.append((str(item["record"]), str(item["rank"]), f"{item['hz']:.4f}") + ("—",) * len(names)
                        + (item.get("reason", "not done"), "—", "—", "—", "—", "—", "—"))
            continue
        notes = []
        if item["mirror"]:
            notes.append("mirror pair" + (", lowest cost exchanged (" + ", ".join(
                f"{n} {item['lowest_cost_change'][n]:+.2%}" for n in names) + ")" if item["lowest_cost_in_other_assignment"] else ""))
        for m in item["competing_minima"]:
            notes.append(f"further minimum, cost × {m['cost_ratio_to_lowest']:.2f}")
        rows.append((str(item["record"]), str(item["rank"]), f"{item['hz']:.4f}")
                    + tuple(_signed(item["change"][n]) for n in names)
                    + (f"{item['fit_rms_ln']:.4f}", _signed(item["left_out_residual_ln"]),
                       "—" if item["holdout_rms_ln"] is None else f"{item['holdout_rms_ln']:.4f}",
                       f"{item['practical_rank']} / {item['condition_number']:.3g}", "yes" if item["converged"] else "NO",
                       ", ".join(item["active_bounds"]) or "none", "; ".join(notes) or "one"))
    return tuple(rows)


CONTROL_HEADERS = ("Estimate", "Full-data value (MPa)", "Largest leave-out change", "Record", "Share of squared changes",
                   "Controlled by one record", "Strongest local influence (records)")


def control_rows(stability: dict) -> tuple:
    rows = []
    for item in stability["control"]:
        shares = stability["influence"]["squared_coefficient_shares"][item["parameter"]]
        local = ", ".join(f"{r} ({shares[r]:.0%})" for r in item["local_order"][:3])
        rows.append((item["parameter"], f"{stability['baseline']['estimates'][item['parameter']]:.0f}",
                     _signed(item["largest_change"]), str(item["record"]), f"{item['share_of_squared_changes']:.0%}",
                     "YES" if item["disproportionate"] else "no", local + (" — not determined" if item["locally_undetermined"] else "")))
    return tuple(rows)


def influence_headers(stability: dict) -> tuple:
    return ("EXP record", "Leverage") + tuple(f"d ln {n} / d ln f" for n in stability["baseline"]["estimates"])


def influence_rows(stability: dict) -> tuple:
    names = tuple(stability["baseline"]["estimates"])
    return tuple((str(c["record"]), f"{c['leverage']:.3f}") + tuple(f"{c[n]:+.3f}" for n in names)
                 for c in stability["influence"]["coefficients"])


def fixed_input_rows(stability: dict) -> tuple:
    fixed = stability["fixed_inputs"]
    rows = [("Relation", fixed["relation"])]
    rows += [(key, f"{value:+g}") for key, value in fixed["exponents"].items()]
    rows += [(f"{key}: factor for a 10 % change of the moduli", f"{lo:.4f} to {hi:.4f}")
             for key, (lo, hi) in fixed["input_factor_for_a_10_percent_modulus_change"].items()]
    rows.append(("Meaning of that factor", fixed["factor_note"]))
    rows += [(key, f"{value:.4g} (independent of thickness and density)") for key, value in fixed["ratios"].items()]
    rows += [(f"Surrogate check: {c['case']}", f"moduli × {c['moduli_factor']:.4f}; largest frequency difference "
                                                f"{c['largest_relative_frequency_difference']:.1e}") for c in fixed["verification"]]
    return tuple(rows)


def assessment_rows(stability: dict) -> tuple:
    a = stability["assessment"]
    numerical = a["numerical_stability"]
    rows = [("Numerical stability", numerical["verdict"], numerical["meaning"])]
    rows += [(f"  {p['parameter']}", p["numerical_stability"],
              f"largest change {p['largest_change_including_the_lowest_cost_minimum']:.2%} (target {a['target']:.0%})")
             for p in numerical["parameters"]]
    rows += [("  Caveat", "", c) for c in numerical["caveats"]]
    fit = a["frequency_fit"]
    rows.append(("Frequency fit", "WARNING: misfit" if fit["misfit_warning"] else "reported",
                 f"FIT RMS {fit['fit_rms_ln']:.4f}, HOLDOUT RMS " + ("—" if fit["holdout_rms_ln"] is None else
                                                                     f"{fit['holdout_rms_ln']:.4f}") + f" (ln f). {fit['meaning']}"))
    accuracy = a["parameter_accuracy"]
    rows.append(("Parameter accuracy (10 % target)", accuracy["verdict"], accuracy["reasons"][0]))
    rows += [("", "", reason) for reason in accuracy["reasons"][1:]]
    return tuple(rows)


def error_plot(result: rft.TuningResult, width: int = 900, height: int = 420, scale: float = 1.0,
               before: str = "Ritz at INP values") -> Optional[bytes]:
    rows = [r for r in result.rows if r["role"] != rft.EXCLUDED and r["ln_after"] is not None]
    if not rows:
        return None
    figure = Figure(figsize=(width / DPI, height / DPI), dpi=DPI * scale, layout="constrained", facecolor="#ffffff")
    axis = figure.add_subplot(111)
    places = np.arange(len(rows))
    before = [100 * (np.exp(r["ln_before"]) - 1) for r in rows]
    after = [100 * (np.exp(r["ln_after"]) - 1) for r in rows]
    for index, r in enumerate(rows):
        if r["role"] == rft.HOLDOUT:
            axis.axvspan(index - 0.5, index + 0.5, color="#fdf3e7", zorder=0, linewidth=0)
    axis.bar(places - 0.2, before, 0.38, color="#9aa5b1", label=before)
    axis.bar(places + 0.2, after, 0.38, color="#2563eb", label="Ritz at fitted values")
    axis.axhline(0.0, color="#3e4c59", linewidth=1.0)
    axis.set_xticks(places, [f"{r['record']}" + ("\nHOLDOUT" if r["role"] == rft.HOLDOUT else "") for r in rows], fontsize=9)
    axis.set_xlabel("Experimental record (shaded: HOLDOUT, not fitted)", fontsize=10, color="#52606d")
    axis.set_ylabel("Error, %", fontsize=10, color="#52606d")
    axis.set_title("Frequency error against PolyMAX (surrogate, not Abaqus)", fontsize=11, loc="left", color="#3e4c59")
    axis.grid(True, axis="y", color="#e4e7eb")
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    axis.legend(fontsize=9, frameon=False)
    FigureCanvasAgg(figure)
    out = io.BytesIO()
    figure.savefig(out, format="png", dpi=figure.dpi)
    return out.getvalue()


SAVED_NOTE = ("SAVED RESULT, shown as exported from {name}. Its source files were not re-read or revalidated and nothing was "
              "recalculated. The stability check and export need live inputs: choose the files and run the tuning.")


def open_saved(path) -> tuple:
    """(result, stability) of an exported proposal, validated and test-rendered; nothing named in the file is opened and
    nothing is recomputed. Any defect is a rft.TuningRefused, so the page keeps what it shows."""
    document = rft.read_export(path)
    result = rft.result_from_export(document)
    stability = rft.restore_record_keys(document.get("stability"))
    if stability is not None and not isinstance(stability, dict):
        raise rft.TuningRefused("The export is damaged: unexpected content in stability.")
    try:
        for rows in (estimate_rows, axis_rows, candidate_rows, quantity_rows, first_mode_rows, assumption_rows, frequency_rows,
                     minima_rows, diagnostic_rows, sensitivity_rows, fit_quality_rows, correspondence_rows, headline,
                     candidate_note, candidate_headers, estimate_headers):
            rows(result)
        if result.surrogate:
            surrogate_rows(result)
        if stability:
            for rows in (stability_rows, control_rows, influence_rows, fixed_input_rows, assessment_rows):
                rows(stability)
            stability_headers(stability), influence_headers(stability)
            stability["assessment"]["statement"], stability["influence"]["rank_note"], stability["solves"]
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
        raise rft.TuningRefused(f"The export is damaged and cannot be shown ({type(error).__name__}: {error}).") from None
    return result, stability


# ================================================================================================ ABM-AUD-5: registered route

REGISTERED_TITLE = "1b. Registered modal set (from the comparison on Analyze), instead of an INP"
REGISTERED_INTRO = ("Estimates the bending stiffness of a flat rectangular plate from the modal set that the Analyze page "
                    "compared with a verified or confirmed physical registration. The measured shapes are compared with "
                    "Kirchhoff-Ritz shapes at the registered points; the fit itself uses frequencies only. Research only: "
                    "conditional estimates, not material properties and not a production identification.")
REGISTERED_NONE = ("No registered set. Finish a mode-shape comparison on the Analyze page (with a verified or confirmed "
                   "registration), then take it here.")
PLATE_FIELDS = (("length", "Length a (mm)"), ("width", "Width b (mm)"), ("thickness", "Thickness (mm)"), ("mass", "Mass (g)"),
                ("nu12", "nu12 (held fixed)"))
CATEGORY_CHOICES = ((rre.MEASURED, "Measured"), (rre.DECLARED, "Declared"), (rre.IMPORTED_FE, "From FE"))  # short: a narrow window
CATEGORY_NOTE = ("For each value say what it is: Measured (on the plate itself), Declared (an engineering assumption) or "
                 "From FE (taken from the FE model). The category is shown with every result.")
AXIS_CHOICES = tuple((axis, axis) for axis in rre.AXES)
MATERIAL_AXIS_CHOICES = (("", "Not stated"), (rre.AXIS_LENGTH, "Along the length"), (rre.AXIS_WIDTH, "Along the width"))
LINK_CHECK = "The entered plate is the registered FE body"
LINK_TEXT = ("By ticking this you state that the plate entered here is the body of the registered FE model, with its length "
             "and width along the FE axes chosen above and its centre at the centre of the FE model. The program does not "
             "verify it; without it no Ritz shape is compared with a measured shape.")
FIX_CHECK = "I fix this correspondence for the fit"
FIX_TEXT = ("By ticking this you fix the record -> Ritz rank correspondence shown in section 2 for the next fit. It is your "
            "decision: the program pairs nothing by frequency or by fit, and any later change of a role or rank withdraws "
            "the fixing.")
REFERENCE_NOTE = ("Reference constants (MPa): a declared starting picture of the plate for the shape review and for the "
                  "comparison column. They set neither the start nor the bounds of the fit. With a stated material axis 1, "
                  "E1 is along that axis; otherwise E1 is along the length.")
REVIEW_NOTE = ("MAC of every record (row) against every Ritz mode (column) at the reference constants, on the registered "
               "measured DOFs. A diagnostic for review: no pair is made from it. Change the roles or declare ranks in "
               "section 2, then fix the correspondence.")
RANK_ONLY_NOTE = ("No shape review is in force. A fit started now uses frequency ranks only: an UNVERIFIED CORRESPONDENCE "
                  "HYPOTHESIS, shown as diagnostic only.")
PRESENTATION_TEXT = {
    rre.SUPPORTED_ESTIMATE: "NUMERICALLY SUPPORTED RESEARCH ESTIMATE — conditional on the declared inputs; not a material property.",
    rre.DIAGNOSTIC_ONLY: "DIAGNOSTIC ONLY — not a supported estimate.",
    rre.NO_ESTIMATE: "NO ESTIMATE — the optimizer status gives none.",
}
REGISTERED_SAVED_NOTE = (" The registration, the comparison and the source files of this saved result were not revalidated: "
                         "nothing of it is carried into a new calculation.")
_SET_KEYS = ("modes", "transform", "fe_low", "fe_high", "source", "registration", "pairs")


def load_registered(source: dict) -> rre.RegisteredSet:
    """The registered set of a comparison (``analyze_model.registered_source``); a refusal says what is missing."""
    return rre.registered_set(**{key: source[key] for key in _SET_KEYS})


def registered_identity_rows(rset: rre.RegisteredSet) -> tuple:
    s, r = rset.source, rset.registration
    pairs = ", ".join(f"record {record} - FE {mode}" + ("" if mac is None else f" (MAC {mac:.3f})")
                      for record, mode, mac in rset.pairs) or "none"
    return (("Experimental file", f"{s.get('experimental_file', '')} ({s.get('experimental_size', 0)} bytes)"),
            ("SHA-256", str(s.get("experimental_sha256", ""))), ("Modal set", str(s.get("modal_set_title", ""))),
            ("Records (as read)", ", ".join(f"{record}: {hz:.4f} Hz" for record, hz in rset.records)),
            ("Measured DOFs", f"{len(rset.labels)} at {rset.point_count} points"),
            ("Registration", f"{r.get('kind', '')}, hash {str(r.get('registration_hash', ''))[:16]}…"
                             + (f"; confirmed by {r['confirmed_by']} on {r.get('confirmed_at', '')}; evidence: "
                                f"{r.get('evidence_location', '')}" if r.get("confirmed_by") else "")),
            ("Units and measured side", f"FE {r.get('fe_unit') or 'not stated'}, experimental "
                                        f"{r.get('experimental_unit') or 'not stated'}, measured side "
                                        f"{r.get('measured_side') or 'not stated'}"),
            ("FE source", f"package {str(s.get('fe_package_sha256', ''))[:16]}…, geometry "
                          f"{str(s.get('fe_geometry_sha256', ''))[:16]}…"),
            ("FE / EXP pairs of the comparison (kept, not used by the fit)", pairs))


def fe_extent_mm(rset: rre.RegisteredSet, axis: str) -> Optional[float]:
    """The FE model's extent along one FE axis in mm, for an explicit import by the user; None when the unit is unknown."""
    unit = {"mm": 1.0, "m": 1000.0}.get(str(rset.registration.get("fe_unit", "")))
    if unit is None or axis not in rre.AXES:
        return None
    index = rre.AXES.index(axis)
    return (rset.fe_high[index] - rset.fe_low[index]) * unit


def _number(text: str, name: str, problems: list) -> float:
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        problems.append(f"{name}: '{str(text).strip()}' is not a number." if str(text).strip() else f"{name} is not entered.")
        return float("nan")


def parse_plate(texts: dict, categories: dict, choices: dict) -> tuple:
    """(plate or None, problems). ``texts``: the entered fields; ``categories``: the category of each quantity ("" when
    not stated); ``choices``: length_axis, width_axis, linked, material_axis. Nothing is completed or defaulted."""
    problems = []
    values = {key: _number(texts.get(key, ""), caption, problems) for key, caption in PLATE_FIELDS}
    reference = tuple(_number(texts.get(key, ""), f"Reference {key}", problems) for key in ("E1", "E2", "G12"))
    if problems:
        return None, problems
    plate = rre.Plate(values["length"], values["width"], values["thickness"], values["mass"], values["nu12"],
                      tuple(categories.get(name, "") for name in rre.INPUT_NAMES), str(texts.get("source", "")).strip(),
                      choices.get("length_axis", ""), choices.get("width_axis", ""), bool(choices.get("linked")),
                      choices.get("material_axis", ""), str(texts.get("axis_evidence", "")).strip(),
                      str(texts.get("suspension", "")).strip(), reference)
    problems = rre.plate_problems(plate)
    return (None if problems else plate), problems


def review_headers(review: dict) -> tuple:
    return ("EXP record", "EXP (Hz)") + tuple(f"Ritz {rank}\n{hz:.2f} Hz" for rank, hz in zip(review["ranks"], review["ritz_hz"]))


def review_rows(review: dict) -> tuple:
    return tuple((str(record), f"{hz:.4f}") + tuple(f"{value:.3f}" for value in row)
                 for (record, hz), row in zip(review["records"], review["mac"]))


CORRESPONDENCE_HEADERS = ("EXP record", "EXP (Hz)", "Role", "Fixed Ritz rank", "Ritz (Hz)", "MAC with it",
                          "Most alike Ritz mode", "Shape verdict", "FE pair of the comparison")
VERDICT_TEXT = {rre.AGREES: "agrees", rre.UNCERTAIN: "UNCERTAIN: close Ritz modes", rre.CONTRADICTS: "CONTRADICTS",
                rre.NOT_COMPARED: "—"}


def correspondence_table_rows(table: dict) -> tuple:
    rows = []
    for r in table["rows"]:
        compared = r.get("compared_rank")
        fixed = "—" if r["rank"] is None else str(r["rank"]) + (
            f" (rank {compared} at these values)" if compared not in (None, r["rank"]) else "")
        pair = "—" if not r.get("fe_pair") else f"FE {r['fe_pair'][0]}" + (
            "" if r["fe_pair"][1] is None else f" (MAC {r['fe_pair'][1]:.3f})")
        rows.append((str(r["record"]), f"{r['hz']:.4f}", r["role"], fixed,
                     "—" if r["ritz_hz"] is None else f"{r['ritz_hz']:.3f}", "—" if r["mac"] is None else f"{r['mac']:.3f}",
                     "—" if r["best_rank"] is None else f"rank {r['best_rank']} (MAC {r['best_mac']:.3f})",
                     VERDICT_TEXT.get(r["verdict"], r["verdict"]), pair))
    return tuple(rows)


GROUP_HEADERS = ("Close Ritz modes", "Records fixed into the group: individual MAC", "Subspace MAC (group, not an identity)")


def group_rows(table: dict) -> tuple:
    rows = []
    for g in table["groups"]:
        name = ", ".join(f"rank {rank} ({hz:.2f} Hz)" for rank, hz in zip(g["ranks"], g["ritz_hz"]))
        if g.get("exactly_degenerate"):
            name += " — exactly degenerate: the individual shapes are not defined"
        individual = "; ".join(f"record {record} with rank {rank}: {mac:.3f}" for record, rank, mac in g["individual"]) or "none"
        subspace = (f"{g['subspace_mac']:.3f} — " if g.get("subspace_mac") is not None else "") + g.get("subspace_note", "")
        rows.append((name, individual, subspace))
    return tuple(rows)


def correspondence_summary_text(table: dict) -> str:
    parts = []
    if table["contradicting"]:
        parts.append("FIT record(s) " + ", ".join(map(str, table["contradicting"])) + " CONTRADICT their fixed Ritz mode by "
                     "shape.")
    if table["uncertain"]:
        parts.append("FIT record(s) " + ", ".join(map(str, table["uncertain"])) + " lie among close Ritz modes: their "
                     "individual identity is not established.")
    if table["holdout_not_agreeing"]:
        parts.append("HOLDOUT record(s) " + ", ".join(map(str, table["holdout_not_agreeing"])) + " do not agree by shape "
                     "(they are predicted, not fitted).")
    if not table["contradicting"] and not table["uncertain"]:
        parts.insert(0, "Every FIT record agrees by shape with the Ritz mode it is fixed to.")
    return " ".join(parts)


BRANCH_HEADERS = ("EXP record", "Role", "Ritz rank at the reference", "Rank at the fitted values", "Fitted Ritz (Hz)",
                  "MAC to the reference mode", "Lowest step MAC on the path", "Branch", "Note")


def branch_rows(block: dict) -> tuple:
    return tuple((str(r["record"]), r["role"], str(r["reference_rank"]), str(r["fitted_rank"]), f"{r['fitted_hz']:.3f}",
                  f"{r['mac_to_reference']:.3f}", f"{r['lowest_step_mac']:.3f}", r["status"],
                  r["note"] + (f" Close Ritz modes at the fitted values: ranks {', '.join(map(str, r['close_group']))}."
                               if r.get("close_group") else ""))
                 for r in block["branch"]["rows"])


STIFFNESS_HEADERS = ("Bending stiffness", "Value (N m)", "Category")


def stiffness_rows(block: dict) -> tuple:
    s, verdict = block["stiffness"], block["presentation"]["verdict"]
    if verdict == rre.NO_ESTIMATE:
        return ()
    category = rre.ESTIMATE if verdict == rre.SUPPORTED_ESTIMATE else "DIAGNOSTIC ONLY"
    if s["alternatives"]:
        rows = []
        for a in s["alternatives"]:
            rows += [(f"{a['alternative']}: D11 (x = {s['frame']['x']})", f"{a['D11']:.4f}", category + ", ALTERNATIVE"),
                     (f"{a['alternative']}: D22 (y = {s['frame']['y']})", f"{a['D22']:.4f}", category + ", ALTERNATIVE"),
                     (f"{a['alternative']}: D66", f"{a['D66']:.4f}", category + ", ALTERNATIVE")]
        return tuple(rows)
    v = s["values"]
    return ((f"D11 (bending, x = {s['frame']['x']})", f"{v['D11']:.4f}", category),
            (f"D22 (bending, y = {s['frame']['y']})", f"{v['D22']:.4f}", category),
            ("D66 (twisting)", f"{v['D66']:.4f}", category),
            ("D12 (coupling)", f"{v['D12']:.4f}", "FIXED RELATION: " + s["D12_note"]))


CONSTANT_HEADERS = ("Quantity", "Value", "Category")
CONSTANT_KIND_TEXT = {"CONDITIONAL_ENGINEERING_CONSTANTS": "CONDITIONAL RESEARCH ESTIMATE",
                      "AXIS_FREE_VALUES": "RESEARCH ESTIMATE WITHOUT A MATERIAL AXIS", "DIAGNOSTIC_ONLY_VALUES": "DIAGNOSTIC ONLY"}


def constant_rows(block: dict) -> tuple:
    c = block["constants"]
    category = CONSTANT_KIND_TEXT.get(c["kind"], c["kind"])
    return tuple((name, f"{value:.0f} MPa ({value / 1000.0:.3f} GPa)" if isinstance(value, (int, float)) else str(value),
                  category if isinstance(value, (int, float)) else "NOTE") for name, value in c["rows"])


def constants_note(block: dict) -> str:
    c = block["constants"]
    if c["kind"] == "CONDITIONAL_ENGINEERING_CONSTANTS":
        return (f"Conditional on: {c['conditions']}. Material axis 1 as declared (evidence: {c.get('axis_evidence', '')}). "
                "Research estimates of the Ritz model, not verified material constants.")
    lead = {"WITHHELD": "No engineering constant is given.",
            "AXIS_FREE_VALUES": "E1 and E2 are not named.",
            "DIAGNOSTIC_ONLY_VALUES": "DIAGNOSTIC ONLY: these numbers are not usable estimates, and E1 / E2 are not named."}
    return lead.get(c["kind"], "") + " " + " ".join(c["reasons"]) + f" Conditional on: {c['conditions']}."


def statement_rows(block: dict) -> tuple:
    return tuple(tuple(row) for row in block.get("statements", ()))


def presentation_text(block: dict) -> str:
    p = block["presentation"]
    return PRESENTATION_TEXT.get(p["verdict"], p["verdict"]) + ((" Reasons: " + " ".join(p["reasons"])) if p["reasons"] else "")


def frame_rows(block_or_review: dict) -> tuple:
    return tuple(tuple(line) for line in block_or_review.get("frame") or ())


def confirmation_text(rset: rre.RegisteredSet, plate: rre.Plate, request: rft.TuningRequest, reviewed: bool,
                      table: Optional[dict]) -> str:
    """What the user confirms before a fit starts: every input and assumption of this one calculation."""
    categories = dict(zip(rre.INPUT_NAMES, plate.categories))
    lines = ["Run ONE bounded research fit of the Ritz model?", "",
             f"Registered modal set: {rset.source.get('experimental_file', '')}, SHA-256 "
             f"{str(rset.source.get('experimental_sha256', ''))[:16]}…, {rset.source.get('modal_set_title', '')}",
             f"Registration: {rset.registration.get('kind', '')}, hash {str(rset.registration.get('registration_hash', ''))[:16]}…",
             "", "Fixed correspondence (" + ("reviewed by shape" if reviewed else "UNVERIFIED frequency-rank hypothesis") + "):"]
    verdicts = {r["record"]: r["verdict"] for r in (table or {}).get("rows", ())}
    for o in sorted(request.observations, key=lambda item: item.record):
        lines.append(f"  record {o.record} ({o.hz:.4f} Hz): {o.role}"
                     + ("" if o.role == rft.EXCLUDED else f", Ritz rank {o.surrogate_rank}"
                        + (f", shape {VERDICT_TEXT.get(verdicts[o.record], '')}" if o.record in verdicts else "")))
    lines += ["", f"Fixed inputs: length {plate.length_mm:g} mm ({categories['length']}), width {plate.width_mm:g} mm "
                  f"({categories['width']}), thickness {plate.thickness_mm:g} mm ({categories['thickness']}), mass "
                  f"{plate.mass_g:g} g ({categories['mass']}), nu12 {plate.nu12:g} ({categories['nu12']}).",
              f"Source of these values: {plate.inputs_source}",
              "Material axis 1: " + ("not stated (no E1 / E2 will be named)" if not plate.material_axis else
                                     f"along the {'length' if plate.material_axis == rre.AXIS_LENGTH else 'width'}; "
                                     f"evidence: {plate.material_axis_evidence}"),
              f"Fitted: {request.parameterization}. Search bounds: the start scaled from the measured frequencies, divided "
              f"and multiplied by {request.search_factor:g}. Ritz basis degree {request.degree}.",
              "", "Model assumptions:"] + [f"  - {text}" for text in rre.ASSUMPTIONS]
    lines += ["", "Research only: the result is a conditional estimate of this model. It is not a material property, it "
                  "changes no production status, and this confirmation is not a scientific approval of any value."]
    return "\n".join(lines)


def run_registered(source: dict, rset: rre.RegisteredSet, plate: rre.Plate, request: rft.TuningRequest,
                   review: Optional[dict], cancel: threading.Event, progress) -> tuple:
    """(result, block) of ``registered_ritz_estimation.run_estimation``, once both source files are confirmed to be the
    files that were read and compared. A changed file is a refusal: nothing is fitted on other data."""
    try:
        am.confirm_sources(source["inputs"], cancel)
    except am.StepCancelled:
        return rft._cancelled(rre.plate_inputs(plate), request, rft.PARAMETERIZATIONS[request.parameterization]), None
    except am.StepFailed as error:
        raise ReadFailed(f"Not started: a source file changed after the comparison. {error}") from error
    return rre.run_estimation(rset, plate, request, review, cancel, progress)


def sources_unchanged(source: dict) -> str:
    """"" when both source files are still the files that were read, otherwise the reason."""
    try:
        am.confirm_sources(source["inputs"], threading.Event())
    except (am.StepFailed, am.StepCancelled) as error:
        return str(error) or "the source files could not be confirmed"
    return ""


def open_saved_registered(path) -> tuple:
    """(result, stability, block): ``open_saved`` and, when the export holds one, its registered-estimation part with the
    presentation computed again from the saved facts. ``block`` is None for an export of the INP route."""
    result, stability = open_saved(path)
    block = rre.block_from_export(rft.read_export(path), result)
    if block is not None:
        try:
            for rows in (stiffness_rows, constant_rows, statement_rows, branch_rows, frame_rows):
                rows(block)
            constants_note(block), presentation_text(block)
            for key in ("reference", "fitted"):
                table = block["correspondence"].get(key)
                if table:
                    correspondence_table_rows(table), group_rows(table), correspondence_summary_text(table)
            if block.get("review"):
                review_headers(block["review"]), review_rows(block["review"])
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
            raise rft.TuningRefused(f"The export is damaged and cannot be shown ({type(error).__name__}: {error}).") from None
    return result, stability, block


# ================================================================================================ ABM-SOLID-5: solid mode

SOLID_TITLE = "Solid offline FE — research"
SOLID_INTRO = ("This INP is a solid C3D8I model, which the Kirchhoff-Ritz tuning above does not read. Here its modal "
               "frequencies can be calculated offline, ONCE per confirmed request, at the INP's own material values, with "
               "the program's reference C3D8I element in a supervised background process. No Abaqus, no fitting, no "
               "parameter change.")
SOLID_LIMITS = ("Limits: the reference element follows published incompatible-mode theory (9 Wilson-Taylor modes); its "
                "equivalence to Abaqus C3D8I is NOT VERIFIED. One part, one instance, one material, one orientation, no "
                "boundary conditions (free-free). The result is a numerical forward result, not material properties and "
                "not a comparison with the experiment.")
SOLID_FE_FE_NOTE = ("FE-to-FE only, PROVISIONAL: offline FE against the Abaqus .dat beside the INP, paired by index after "
                    "the six lowest (rigid-body) modes. The .dat's provenance is UNVERIFIED: equal element and node counts "
                    "and total mass are consistency checks only and do not prove that the .dat was computed with this "
                    "INP's material constants or FE model. This says nothing about the experiment; experimental mode "
                    "shapes are compared on the Analyze and MAC / Points pages.")
SOLID_FREQUENCY_HEADERS = ("Elastic mode", "Offline FE (Hz)", "Abaqus .dat (Hz, PROVISIONAL)",
                           "Difference (Hz, PROVISIONAL)", "Difference (%, PROVISIONAL)")
SOLID_REFERENCE_PROVENANCE = "UNVERIFIED"  # nothing in the .dat ties it to this INP's material constants


@dataclass(frozen=True)
class SolidReference:
    dat_path: str
    consistent: bool         # mesh counts, mass and eigen table pass: a consistency diagnostic, never proof of identity
    checks: tuple            # (check, value, PASS/FAIL)
    elastic_hz: tuple        # .dat rows above the six lowest, as written
    rigid_marked: tuple      # modes Abaqus itself marked with '*'
    note: str
    provenance: str = SOLID_REFERENCE_PROVENANCE


@dataclass(frozen=True)
class SolidSummary:
    inp_path: str
    sha256: str
    element_count: int
    node_count: int
    dof_count: int
    instance: Optional[str]
    material_name: str
    material: dict
    density: float
    axes: tuple
    orientation: Optional[str]
    requested_eigenvalues: Optional[int]
    volume_mm3: float
    formulation: str
    abaqus_equivalence: str
    preflight: dict
    reference: Optional[SolidReference]


def _printed_resolution(text: str) -> float:
    """Half a unit in the last printed digit of an Abaqus number such as 1.1836072E-04."""
    mantissa, _, exponent = text.upper().partition("E")
    decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
    return 0.5 * 10.0 ** (int(exponent or 0) - decimals)


def read_solid_reference(dat_path, element_count: int, node_count: int, mass_t: float) -> SolidReference:
    """The .dat eigenvalue table, shown (as PROVISIONAL) only when its problem size and total mass match this INP's mesh
    and density. These are consistency diagnostics, not proof of model identity: the .dat does not echo the material
    constants, so its provenance stays UNVERIFIED."""
    import re

    text = Path(dat_path).read_text(encoding="latin-1", errors="replace")
    checks = []

    def number(pattern):
        found = re.search(pattern, text)
        return found.group(1) if found else None

    elements = number(r"NUMBER OF ELEMENTS IS\s+(\d+)")
    nodes = number(r"NUMBER OF NODES DEFINED BY THE USER\s+(\d+)")
    mass = number(r"TOTAL MASS OF MODEL\s+(\S+)")
    checks.append(("Elements in the .dat", elements or "not found", "PASS" if elements and int(elements) == element_count else "FAIL"))
    checks.append(("User nodes in the .dat", nodes or "not found", "PASS" if nodes and int(nodes) == node_count else "FAIL"))
    if mass:
        tolerance = _printed_resolution(mass) + 1e-12 * abs(mass_t)
        same = abs(float(mass) - mass_t) <= tolerance
        checks.append(("Total mass in the .dat", f"{mass} t (INP density × volume {mass_t:.7E} t, printed precision)",
                       "PASS" if same else "FAIL"))
    else:
        checks.append(("Total mass in the .dat", "not found", "FAIL"))
    start = text.find("E I G E N V A L U E    O U T P U T")
    rows = []
    if start >= 0:
        for line in text[start:].splitlines()[1:]:
            found = re.match(r"\s+(\d+)(\*?)\s+(\S+)\s+(\S+)\s+(\S+)", line)
            if found:
                rows.append((int(found.group(1)), found.group(2) == "*", float(found.group(5))))
            elif rows and not line.strip():
                break
    checks.append(("Eigenvalue rows in the .dat", str(len(rows)), "PASS" if len(rows) > 6 else "FAIL"))
    consistent = all(c[2] == "PASS" for c in checks)
    note = ("PROVISIONAL: mesh size and total mass are consistent with this INP, but that does not prove the same "
            "material or FE model; the .dat does not echo the material constants. Differences are shown as PROVISIONAL."
            if consistent else "Not used: the .dat is not consistent with this INP's mesh or mass.")
    return SolidReference(str(dat_path), consistent, tuple(checks), tuple(r[2] for r in rows[6:]),
                          tuple(r[0] for r in rows if r[1]), note)


def check_solid(inp_path) -> SolidSummary:
    """Read-only: import with the solid importer, its preflight and memory decision, and a matching .dat if any."""
    from services import solid_c3d8i_forward as sf
    from services import solid_c3d8i_model as sm
    from services import solid_forward_runner as sfr

    try:
        model = sm.load_solid_inp(inp_path)
    except (OSError, sf.SolidElementError) as error:
        raise ReadFailed(f"Solid offline FE is not available for this INP: {error}") from error
    x = model.coordinates[model.connectivity]
    geometries, inverse = np.unique((x - x[:, :1, :]).reshape(len(x), 24), axis=0, return_inverse=True)
    volumes = np.array([sf.element_volume(g.reshape(8, 3)) for g in geometries])
    volume = float(np.sum(volumes[np.asarray(inverse).reshape(-1)]))
    try:
        info = sfr.preflight(sfr.ForwardRequest(str(inp_path), model.source_sha256))
    except sfr.RunnerRefused as error:
        raise ReadFailed(f"Solid offline FE is not available: {error}") from error
    dat = Path(inp_path).with_suffix(".dat")
    reference = (read_solid_reference(dat, len(model.element_labels), len(model.node_labels), model.density * volume)
                 if dat.is_file() else None)
    m = model.material
    return SolidSummary(str(inp_path), model.source_sha256, len(model.element_labels), len(model.node_labels),
                        model.dof_count, model.instance_name, model.material_name,
                        {k: getattr(m, k) for k in ("e1", "e2", "e3", "nu12", "nu13", "nu23", "g12", "g13", "g23")},
                        model.density, tuple(map(tuple, model.material_axes.tolist())), model.orientation_name,
                        model.requested_eigenvalues, volume, model.formulation, model.abaqus_equivalence, info, reference)


def _gib(value) -> str:
    return "—" if value is None else f"{value / 1024 ** 3:.2f} GiB"


def solid_identity_rows(s: SolidSummary) -> tuple:
    return (("INP", s.inp_path), ("SHA-256", s.sha256), ("Instance", s.instance or "none (flat input)"),
            ("Elements", f"{s.element_count} C3D8I"), ("Nodes", str(s.node_count)), ("Degrees of freedom", str(s.dof_count)),
            ("Volume", f"{s.volume_mm3:.6g} mm³"), ("Mass (INP density × volume)", f"{s.density * s.volume_mm3 * 1e6:.3f} g"),
            ("Element formulation", s.formulation), ("Abaqus element equivalence", s.abaqus_equivalence))


def solid_material_rows(s: SolidSummary) -> tuple:
    m = s.material
    axes = "global axes" if np.allclose(s.axes, np.eye(3)) else "; ".join(
        f"{n} = ({', '.join(f'{v:.4g}' for v in row)})" for n, row in zip(("1", "2", "3"), s.axes))
    return ((f"E1 (original, used)", f"{m['e1']:g} MPa"), ("E2 (original, used)", f"{m['e2']:g} MPa"),
            ("G12 (original, used)", f"{m['g12']:g} MPa"), ("E3 (fixed)", f"{m['e3']:g} MPa"), ("nu12 (fixed)", f"{m['nu12']:g}"),
            ("nu13 (fixed)", f"{m['nu13']:g}"), ("nu23 (fixed)", f"{m['nu23']:g}"), ("G13 (fixed)", f"{m['g13']:g} MPa"),
            ("G23 (fixed)", f"{m['g23']:g} MPa"), ("Density (fixed)", f"{s.density:g} t/mm³"),
            ("Material axes", f"{s.orientation or 'no orientation'}: {axes}"))


def solid_resource_text(s: SolidSummary) -> str:
    p = s.preflight
    text = (f"Estimated peak {_gib(p['peak_bytes_estimate'])} (factor estimate {_gib(p['factor_bytes_estimate'])}); "
            f"available now {_gib(p['available_memory_bytes'])}; supervised limit {_gib(p['job_memory_limit_bytes'])} for "
            f"all worker processes; {_gib(p['reserve_free_memory_bytes'])} kept free for the system.")
    if p["decision"] != "ALLOW":
        text += " NOT ALLOWED: " + " ".join(p["decision_reasons"])
    return text


def solid_reference_rows(s: SolidSummary) -> tuple:
    if s.reference is None:
        return (("Abaqus .dat beside the INP", "none: no FE-to-FE comparison"),)
    r = s.reference
    rows = [("Abaqus .dat", r.dat_path)] + [(f"{name} (consistency)", f"{value}  [{state}]")
                                            for name, value, state in r.checks]
    rows.append(("Modes Abaqus marked rigid (*)", ", ".join(map(str, r.rigid_marked)) or "none marked"))
    rows.append(("Provenance (same material and FE model)",
                 f"{r.provenance}: the .dat does not echo the material constants; consistency checks are not proof"))
    rows.append(("Use", r.note))
    return tuple(rows)


def solid_confirmation_text(s: SolidSummary) -> str:
    m = s.material
    return (f"Run ONE offline FE calculation of this model?\n\n{s.inp_path}\nSHA-256 {s.sha256}\n"
            f"{s.element_count} C3D8I elements, {s.dof_count} degrees of freedom.\n\n"
            f"Material exactly as in the INP, unchanged: E1 {m['e1']:g}, E2 {m['e2']:g}, G12 {m['g12']:g} MPa; "
            f"E3 {m['e3']:g}, G13 {m['g13']:g}, G23 {m['g23']:g} MPa; nu12 {m['nu12']:g}, nu13 {m['nu13']:g}, "
            f"nu23 {m['nu23']:g}; density {s.density:g} t/mm³.\n\n"
            f"Scope: 6 rigid-body + 14 elastic + 4 guard modes, once. No fitting, no repetition, no Abaqus. "
            f"{solid_resource_text(s)}")


def solid_frequency_rows(result: dict, s: Optional[SolidSummary]) -> tuple:
    # differences against a consistent .dat are PROVISIONAL (headers and note say so); an inconsistent .dat is not used
    ref = s.reference.elastic_hz if s is not None and s.reference is not None and s.reference.consistent else ()
    rows = []
    for index, hz in enumerate(result["frequencies_hz"]):
        if index < len(ref):
            diff = hz - ref[index]
            rows.append((str(index + 1), f"{hz:.4f}", f"{ref[index]:g}", f"{diff:+.4f}", f"{100 * diff / ref[index]:+.3f}"))
        else:
            rows.append((str(index + 1), f"{hz:.4f}", "—", "—", "—"))
    return tuple(rows)


def _supervision_rows(outcome) -> list:
    return [("Status", outcome.status), ("Message", outcome.message),
            ("Worker process", f"PID {outcome.worker_pid}, verified inside the supervision job" if outcome.worker_in_job
             else f"PID {outcome.worker_pid}: NOT verified"),
            ("Launcher process", f"PID {outcome.launcher_pid}"),
            ("Peak memory, all worker processes (measured by Windows)", _gib(outcome.peak_job_memory_bytes) + (
                " — LIMIT REACHED: this figure includes the allocation Windows refused" if outcome.memory_limit_reached
                else "")),
            ("Peak memory of the solver process (its own report)", _gib(outcome.peak_worker_commit_bytes)),
            ("Available memory before / lowest during the run", f"{_gib(outcome.available_memory_before_bytes)} / "
                                                                f"{_gib(outcome.min_available_memory_bytes)}"),
            ("Worker processes still running after the run", "—" if outcome.active_processes_after is None
             else str(outcome.active_processes_after)),
            ("Runtime", f"{outcome.runtime_seconds:.1f} s")]


def solid_diagnostic_rows(outcome) -> tuple:
    rows = _supervision_rows(outcome)
    r = outcome.result
    if r and "frequencies_hz" in r:
        rigid = r["rigid"]
        seconds = r["seconds"]
        rows += [("Stages", ", ".join(f"{k} {v:.1f} s" for k, v in seconds.items())),
                 ("Factorisation", f"{r['factor_nonzeros']:,} nonzeros"),
                 ("Shift", f"{r['shift']:.6g} ({r['shift_source']}); {r['operator_applications']} operator applications"),
                 ("Largest backward error", f"{r['max_backward_error']:.2e}"),
                 ("Mass orthogonality error", f"{r['mass_orthogonality_error']:.2e}"),
                 ("Rigid-body modes", f"{'passed' if rigid['passed'] else 'FAILED'}: C2E0 {rigid['c2e0']}, "
                                      f"f_rigid,max / f_elastic,1 = {rigid['ratio']:.3g}, smallest span cosine "
                                      f"{rigid['min_span_cosine']:.12f}, largest rigid content of an elastic mode "
                                      f"{rigid['max_rigid_content_of_elastic']:.2e}"),
                 ("First elastic mode", f"{r['frequencies_hz'][0]:.4f} Hz (kept: the six lowest are the verified rigid-body modes)"),
                 ("Guard modes above the window", ", ".join(f"{v:.3f}" for v in r["guard_frequencies_hz"]) + " Hz"),
                 ("Closest neighbouring pair", f"{100 * min(r['relative_spacing']):.2f} % relative spacing"),
                 ("Material used", ", ".join(f"{k} {v:g}" for k, v in r["material"].items()) + f", density {r['density']:g}"),
                 ("Element", f"{r['formulation']}; Abaqus equivalence {r['abaqus_equivalence']}")]
    elif r:
        rows.append(("Failure diagnostics", "; ".join(f"{k}: {v}" for k, v in r.items() if k != "all_eigenvalues")))
    return tuple(rows)


# ================================================================================================ ABM-SOLID-6: What-If

WHATIF_TITLE = "Manual What-If: E1, E2, G12 (research)"
WHATIF_INTRO = ("Optional: enter up to three combinations of E1, E2 and G12 (MPa) to calculate their frequencies with this "
                "model. Every other engineering constant, the density, geometry, orientation and the free-free condition "
                "stay as in the INP. Each point is solved once, in the order entered, in one supervised worker. No search, "
                "no fitting, no automatic E1/E2 orientation, no pairing with measured modes.")
WHATIF_NOTE = ("Frequencies are listed in ascending order for each point and compared by that order, not by mode shape: "
               "if two modes change places between points, the comparison of that row compares different modes. A "
               "smaller difference from measured frequencies does not prove a material property.")
WHATIF_FIELDS = ("E1", "E2", "G12")


def solid_material_constants(s: SolidSummary):
    """The INP's engineering constants rebuilt from the checked summary (validated again; nothing is re-read)."""
    from services import solid_c3d8i_forward as sf

    return sf.OrthotropicEngineeringConstants(**s.material)


def parse_whatif(material, texts) -> tuple:
    """(points, problems): ``texts`` holds one (E1, E2, G12) text triple per row. A blank row is skipped; any other row
    must be complete and admissible. ``problems`` maps the row number (1-based) to its messages."""
    from services import solid_forward_runner as sfr

    points, problems = [], {}
    for row, triple in enumerate(texts, 1):
        cells = [str(t).strip() for t in triple]
        if not any(cells):
            continue
        if not all(cells):
            problems[row] = ["Enter all of E1, E2 and G12, or leave the row empty."]
            continue
        found = sfr.point_problems(material, cells)
        if found:
            problems[row] = found
        else:
            points.append(tuple(float(c) for c in cells))
    if not problems and len(set(points)) != len(points):
        problems[0] = ["Two rows are identical; each point is solved once, so enter distinct points."]
    return tuple(points), problems


def _change(value: float, original: float) -> str:
    return "unchanged" if value == original else f"{100 * (value - original) / original:+.2f} %"


def whatif_parameter_rows(s: SolidSummary, points) -> tuple:
    rows = []
    for name, key in zip(WHATIF_FIELDS, ("e1", "e2", "g12")):
        original = s.material[key]
        rows.append((f"{name} (MPa)", f"{original:g}",
                     *(f"{p[WHATIF_FIELDS.index(name)]:g} ({_change(p[WHATIF_FIELDS.index(name)], original)})"
                       for p in points)))
    m = s.material
    fixed = (f"E3 {m['e3']:g}, G13 {m['g13']:g}, G23 {m['g23']:g} MPa; nu12 {m['nu12']:g}, nu13 {m['nu13']:g}, "
             f"nu23 {m['nu23']:g}; density {s.density:g} t/mm³")
    rows.append(("Other constants, density", fixed, *("same as the INP" for _ in points)))
    rows.append(("Geometry, orientation, boundary", f"{s.element_count} C3D8I, {s.orientation or 'no orientation'}, "
                                                    "free-free", *("same as the INP" for _ in points)))
    return tuple(rows)


def whatif_parameter_headers(points) -> tuple:
    return ("Parameter", "Original INP", *(f"Point {i}" for i in range(1, len(points) + 1)))


def whatif_confirmation_text(s: SolidSummary, points) -> str:
    lines = [f"Point {i}: E1 {p[0]:g}, E2 {p[1]:g}, G12 {p[2]:g} MPa" for i, p in enumerate(points, 1)]
    m = s.material
    return (f"Run {len(points)} offline FE calculation{'s' if len(points) != 1 else ''} (one per What-If point, in this "
            f"order) of this model?\n\n{s.inp_path}\nSHA-256 {s.sha256}\n{s.element_count} C3D8I elements, "
            f"{s.dof_count} degrees of freedom.\n\nOriginal INP: E1 {m['e1']:g}, E2 {m['e2']:g}, G12 {m['g12']:g} MPa.\n"
            + "\n".join(lines) +
            f"\n\nUnchanged: E3 {m['e3']:g}, G13 {m['g13']:g}, G23 {m['g23']:g} MPa; nu12 {m['nu12']:g}, nu13 "
            f"{m['nu13']:g}, nu23 {m['nu23']:g}; density {s.density:g} t/mm³; geometry, orientation, free-free.\n\n"
            f"Total FE solves: {len(points)}, sequential, in one supervised worker. No search, no fitting, no repetition "
            f"of failed points, no Abaqus. {solid_resource_text(s)}")


def whatif_frequency_headers(outcome) -> tuple:
    points = outcome.points
    base = next((p["index"] for p in points if p["status"] == "SOLVED"), None)
    headers = ["Elastic mode"]
    for p in points:
        headers.append(f"Point {p['index']} (Hz)")
        if base is not None and p["index"] != base:
            headers.append(f"Point {p['index']} vs Point {base} (%)")
    return tuple(headers)


def whatif_frequency_rows(outcome) -> tuple:
    points = outcome.points
    solved = [p for p in points if p["status"] == "SOLVED"]
    if not solved:
        return ()
    base = solved[0]
    count = max(len(p["result"]["frequencies_hz"]) for p in solved)
    rows = []
    for mode in range(count):
        row = [str(mode + 1)]
        reference = base["result"]["frequencies_hz"][mode] if mode < len(base["result"]["frequencies_hz"]) else None
        for p in points:
            values = p["result"]["frequencies_hz"] if p["status"] == "SOLVED" else ()
            hz = values[mode] if mode < len(values) else None
            row.append(f"{hz:.4f}" if hz is not None else p["status"])
            if p is not base:
                row.append(f"{100 * (hz - reference) / reference:+.3f}" if hz is not None and reference else "—")
        rows.append(tuple(row))
    return tuple(rows)


def whatif_diagnostic_rows(outcome) -> tuple:
    rows = _supervision_rows(outcome)
    reuse = (outcome.result or {}).get("reuse")
    if reuse:
        rows.append(("Model reuse", f"one import, one forward model (unique-geometry cache); mass matrix reused for every "
                                    f"point: {'yes' if reuse['mass_matrix_reused_for_every_point'] else 'NO'}; "
                                    f"{reuse['points_attempted']} point(s) attempted"))
    for p in outcome.points:
        q = p["parameters"]
        head = f"Point {p['index']} (E1 {q['e1']:g}, E2 {q['e2']:g}, G12 {q['g12']:g})"
        if p["status"] != "SOLVED":
            error = p.get("error") or {}
            rows.append((head, f"{p['status']}" + (f": {error.get('kind')}: {error.get('message')}" if error else
                                                    ": not run") + " — not retried"))
            continue
        r = p["result"]
        rigid = r["rigid"]
        rows.append((head, f"SOLVED in {r['seconds'].get('total', 0.0):.1f} s; largest backward error "
                           f"{r['max_backward_error']:.2e}; mass orthogonality {r['mass_orthogonality_error']:.2e}; "
                           f"rigid-body modes {'passed' if rigid['passed'] else 'FAILED'} (C2E0 {rigid['c2e0']}); shift "
                           f"{r['shift']:.6g}; factor {r['factor_nonzeros']:,} nonzeros; closest pair "
                           f"{100 * min(r['relative_spacing']):.2f} %; guard modes up to {max(r['guard_frequencies_hz']):.3f} Hz; "
                           f"mass matrix reused: {'yes' if p.get('mass_matrix_reused') else 'NO'}"))
        used = r["material"]
        rows.append((f"Point {p['index']} material used", ", ".join(f"{k} {v:g}" for k, v in used.items())
                     + f", density {r['density']:g}"))
    if outcome.points and outcome.points[0].get("result"):
        r = outcome.points[0]["result"]
        rows.append(("Element", f"{r['formulation']}; Abaqus equivalence {r['abaqus_equivalence']}"))
    return tuple(rows)


__all__ = ["BRANCH_HEADERS", "CATEGORY_CHOICES", "CONSTANT_HEADERS", "CORRESPONDENCE_HEADERS", "FIX_CHECK", "FIX_TEXT", "GROUP_HEADERS",
           "LINK_CHECK", "LINK_TEXT", "PLATE_FIELDS", "REGISTERED_FREQUENCY_HEADERS", "REGISTERED_INTRO", "REGISTERED_NONE",
           "REGISTERED_TITLE", "STIFFNESS_HEADERS", "branch_rows", "confirmation_text", "constant_rows", "constants_note",
           "correspondence_summary_text", "correspondence_table_rows", "fe_extent_mm", "frame_rows", "group_rows",
           "load_registered", "open_saved_registered", "parse_plate", "presentation_text", "registered_identity_rows",
           "review_headers", "review_rows", "run_registered", "sources_unchanged", "statement_rows", "stiffness_rows",
           "CORRESPONDENCE_HINT", "STALE_TEXT", "candidate_headers", "candidate_note", "correspondence_preview",
           "correspondence_rows", "estimate_headers", "fit_quality_rows", "headline", "quality_of",
           "ANALYZE_NOTE", "check_model", "compatibility_notes", "compatibility_rows", "LABEL", "ReadFailed", "SAVED_NOTE", "Sources", "candidate_rows", "open_saved", "default_holdout", "diagnostic_rows", "error_plot",
           "frequency_rows", "input_rows", "minima_rows", "parse_declared", "read_sources", "sensitivity_rows",
           "surrogate_rows", "SOLID_FE_FE_NOTE", "SOLID_FREQUENCY_HEADERS", "SOLID_INTRO", "SOLID_LIMITS",
           "SOLID_REFERENCE_PROVENANCE", "SOLID_TITLE",
           "SolidReference", "SolidSummary", "check_solid", "read_solid_reference", "solid_confirmation_text",
           "solid_diagnostic_rows", "solid_frequency_rows", "solid_identity_rows", "solid_material_rows",
           "solid_reference_rows", "solid_resource_text", "WHATIF_FIELDS", "WHATIF_INTRO", "WHATIF_NOTE", "WHATIF_TITLE",
           "parse_whatif", "solid_material_constants", "whatif_confirmation_text", "whatif_diagnostic_rows", "whatif_frequency_headers",
           "whatif_frequency_rows", "whatif_parameter_headers", "whatif_parameter_rows"]
