"""GUI-UX-R1-F1: what the Analyze page says is loaded and what can be done with it, with no Qt.

The rows state what the read data or the saved file hold. Nothing is read or computed here, and no saved path is looked at.
"""

from __future__ import annotations

from pathlib import Path

from new_gui import analyze_model as am
from new_gui import mac_points_model as mp
from new_gui import review_model as rv
from new_gui import shape_model as sm

HEADERS = ("Item", "State")
FITTED, FRF_PEAKS, MIXED = "Fitted modes", f"{sm.FRF_PEAK_SHORT} records", "Fitted modes and FRF peak records"
AVAILABLE = "Available"
NEEDS_SOURCE = "Needs the source files"


def _name(path) -> str:
    return Path(path).name if path else "not chosen"


def _record_type(provisional, total: int) -> str:
    """``provisional`` is how many of the ``total`` records are FRF peaks."""
    if not provisional:
        return FITTED
    return FRF_PEAKS if provisional == total else MIXED


def summary_rows(paths: dict, inputs, analysis, snapshot, fe_key, experimental_key) -> tuple:
    rows = [("FE results", _name(paths.get(fe_key))), ("Experiment", _name(paths.get(experimental_key)))]
    if inputs is not None:
        sets = inputs.full_experimental.sets
        rows.append(("FE modes loaded", f"{len(inputs.fe.modes)} in the requested range {am.FIRST_MODE}-{am.LAST_MODE}"))
        rows.append(("Modal sets in the file", "; ".join(item.title for item in sets)))
    if analysis is None:
        return tuple(rows)
    saved = snapshot is not None
    rigid = ", ".join(str(mode) for mode in analysis.rigid_modes) or "none"
    if saved:
        rows.append(("Modal sets in the file", "; ".join(item["title"] for item in snapshot.document["modal_set"]["all_sets"])))
    rows.append(("FE modes", f"{len(analysis.fe_rows)} of {am.MODE_LIMIT} requested; rigid-body by shape: {rigid}; "
                             f"first elastic: {analysis.first_elastic or 'none'}"))
    rows.append(("Chosen modal set", analysis.set_title))
    provisional = sum(sm.PROVISIONAL_TEXT in str(row[-1]) for row in analysis.experimental_rows)
    rows.append(("Experimental records", f"{len(analysis.experimental_rows)} of {analysis.experimental_total}: "
                                         + _record_type(provisional, len(analysis.experimental_rows))))
    rows.append(("Frequency table and plots", AVAILABLE))
    rows.append(("Mode shapes", "Saved magnitude pictures only" if saved else AVAILABLE))
    if saved:
        rows.append(("FRF spectrum", NEEDS_SOURCE))
        rows.append(("Measured point layout", NEEDS_SOURCE))
    else:
        dataset = inputs.experimental.sets[analysis.set_index].dataset
        rows.append(("FRF spectrum", AVAILABLE if rv.frf_series(dataset) is not None else "Not available: no usable FRF curve"))
        rows.append(("Measured point layout", AVAILABLE))
    if analysis.comparison is not None:
        rows.append(("MAC and mode pairs", f"{AVAILABLE}: {len(analysis.comparison.pair_rows)} admissible pairs"))
    else:
        rows.append(("MAC and mode pairs", mp.unavailable_reason(analysis, saved)))
    return tuple(rows)


__all__ = ["HEADERS", "summary_rows"]
