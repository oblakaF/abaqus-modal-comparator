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

from new_gui import preview_model as pm
from new_gui.workspace_state import EXPERIMENTAL
from services import research_frequency_tuning as rft

LABEL = rft.RESULT_LABEL
SURROGATE_NOTE = ("Ritz values are frequencies of the Kirchhoff plate surrogate, not Abaqus FE results. A candidate is a "
                  "proposal for a new Abaqus solve; only that solve can confirm it.")
STATUS_TEXT = {
    rft.SUPPORTED: "Candidate issued: the fit is numerically supported.",
    rft.MIRROR: "No candidate: E1 and E2 fit equally well exchanged; which plate axis is stiff is not identifiable.",
    rft.NOT_IDENTIFIABLE: "No candidate: the selected frequencies cannot separate the parameters.",
    rft.AT_BOUND: "No candidate: a parameter ended at its bound.",
    rft.NOT_CONVERGED: "No candidate: the fit did not converge.",
    rft.STARTS_DISAGREE: "No candidate: different starts end at different minima.",
    rft.CANCELLED: "Cancelled. No result.",
}
EXPORT_FILTER = "Research tuning proposal (*.json)"
DPI = 100


class ReadFailed(ValueError):
    pass


@dataclass(frozen=True)
class Sources:
    inputs: rft.AbaqusPlateInputs
    dat_path: Optional[str]
    fe_elastic: tuple  # (mode, Hz) from the model's own .dat, or ()
    unv_path: str
    unv_sha256: str
    set_title: str
    records: tuple  # (record number, Hz) of the curve-fitted records


def read_sources(inp_path, unv_path, cancel: threading.Event) -> Sources:
    """The INP (and its .dat, when present beside it) and the fitted modes of the experimental file. Read only."""
    try:
        inputs = rft.read_inp(inp_path)
    except (OSError, rft.TuningRefused) as error:
        raise ReadFailed(f"The INP could not be used: {error}") from error
    dat = Path(inp_path).with_suffix(".dat")
    fe = ()
    if dat.is_file():
        try:
            fe = rft.elastic_fe_frequencies(rft.read_dat_frequencies(dat))
        except rft.TuningRefused:
            fe = ()
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
    return Sources(inputs, str(dat) if fe else None, fe, str(unv_path), str(identity.get("sha256", "")), chosen.title, records)


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
        record, rank = part.split(":")
        mapping[int(record)] = int(rank)
        if mapping[int(record)] < 1:
            raise ValueError("A rank starts at 1.")
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
    rows.append(("Stored FE elastic modes (.dat)", f"{len(sources.fe_elastic)}, first {sources.fe_elastic[0][1]:g} Hz"
                 if sources.fe_elastic else "no .dat beside the INP"))
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


def minima_rows(result: rft.TuningResult) -> tuple:
    return tuple((str(index + 1), ", ".join(f"{k} {v:.0f}" for k, v in m["values"].items()), f"{m['cost']:.6g}")
                 for index, m in enumerate(result.minima))


def diagnostic_rows(result: rft.TuningResult) -> tuple:
    rows = [("Status", result.status), ("Label", result.label), ("Parameters fitted", ", ".join(result.parameter_names)),
            ("Correspondence", "Rank order of the kept frequencies (exploratory spectrum fit), with any declared ranks"),
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
        rows.append((f"Start {index + 1} (factors {start['start_factor']})",
                     ", ".join(f"{k} {v:.0f}" for k, v in start["values"].items()) + f"; cost {start['cost']:.6g}"))
    return tuple(rows)


def sensitivity_rows(result: rft.TuningResult) -> tuple:
    return tuple((str(row["record"]),) + tuple(f"{row[name]:+.4f}" for name in result.parameter_names) for row in result.sensitivity)


def surrogate_rows(result: rft.TuningResult) -> tuple:
    return tuple((str(r["rank"]), str(r["fe_mode"]), f"{r['fe_hz']:g}", f"{r['ritz_hz']:.3f}", f"{100 * r['ritz_over_fe_minus_1']:+.2f} %")
                 for r in result.surrogate)


SURROGATE_HEADERS = ("Elastic rank", "Abaqus mode (.dat)", "Abaqus (Hz)", "Ritz at INP values (Hz)", "Ritz / Abaqus − 1")


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


__all__ = ["LABEL", "ReadFailed", "Sources", "candidate_rows", "default_holdout", "diagnostic_rows", "error_plot",
           "frequency_rows", "input_rows", "minima_rows", "parse_declared", "read_sources", "sensitivity_rows",
           "surrogate_rows"]
