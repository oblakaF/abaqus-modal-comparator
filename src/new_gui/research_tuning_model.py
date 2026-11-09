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
from services import research_frequency_tuning as rft

LABEL = rft.RESULT_LABEL
SURROGATE_NOTE = ("Ritz values are frequencies of the Kirchhoff plate surrogate, not Abaqus FE results. A candidate is a "
                  "proposal for a new Abaqus solve; only that solve can confirm it.")
STATUS_TEXT = {
    rft.SUPPORTED: "Estimates and an oriented candidate issued: the fit is numerically supported.",
    rft.MIRROR: ("Numerical estimates issued (E_stiff, E_soft, G12). No oriented candidate: E1 and E2 fit equally well "
                 "exchanged, so which plate axis is stiff is not identifiable."),
    rft.NOT_IDENTIFIABLE: "No candidate: the selected frequencies cannot separate the parameters.",
    rft.AT_BOUND: "No candidate: a parameter ended at its bound.",
    rft.NOT_CONVERGED: "No candidate: the fit did not converge.",
    rft.STARTS_DISAGREE: "No candidate: different starts end at different minima.",
    rft.CANCELLED: "Cancelled. No result.",
}
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


def candidate_rows(result: rft.TuningResult) -> tuple:
    if not result.candidate:
        return ()
    return tuple((name, f"{result.baseline[name]:g}", f"{result.candidate[name]:.0f}",
                  f"{100.0 * (result.candidate[name] / result.baseline[name] - 1.0):+.1f} %") for name in ("E1", "E2", "G12"))


CANDIDATE_HEADERS = ("Input", "INP value (MPa)", "Candidate (MPa)", "Change")


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


def axis_rows(result: rft.TuningResult) -> tuple:
    return tuple((a["assignment"], f"{a['E1 (FE X)']:.0f}", f"{a['E2 (FE Y)']:.0f}", f"{a['G12']:.0f}", f"{a['cost']:.6g}")
                 for a in result.axis_assignments)


AXIS_HEADERS = ("Possible axis assignment (none chosen)", "E1 along FE X (MPa)", "E2 along FE Y (MPa)", "G12 (MPa)", "Cost")


def quantity_rows(result: rft.TuningResult) -> tuple:
    return tuple((q["quantity"], q["category"], q["source"]) for q in result.quantities)


QUANTITY_HEADERS = ("Quantity", "Category", "Source")


def first_mode_rows(result: rft.TuningResult) -> tuple:
    check = result.first_mode_check
    if not check or not check.get("done"):
        return (("Lowest record left out", (check or {}).get("reason", "not run")),)
    rows = [("Left out for this check only", f"record {check['left_out_record']} at {check['left_out_hz']:.4f} Hz")]
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
    rows = [("Status", result.status), ("Label", result.label), ("Parameters fitted", ", ".join(result.parameter_names)),
            ("Correspondence", "Rank order of the kept frequencies (exploratory spectrum fit), with any declared ranks; it "
             "assumes no measured mode is missing or extra below the highest one"),
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


def error_plot(result: rft.TuningResult, width: int = 900, height: int = 420, scale: float = 1.0) -> Optional[bytes]:
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
    axis.bar(places - 0.2, before, 0.38, color="#9aa5b1", label="Ritz at INP values")
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
                     minima_rows, diagnostic_rows, sensitivity_rows):
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


__all__ = ["ANALYZE_NOTE", "check_model", "compatibility_notes", "compatibility_rows", "LABEL", "ReadFailed", "SAVED_NOTE", "Sources", "candidate_rows", "open_saved", "default_holdout", "diagnostic_rows", "error_plot",
           "frequency_rows", "input_rows", "minima_rows", "parse_declared", "read_sources", "sensitivity_rows",
           "surrogate_rows"]
