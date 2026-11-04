"""GUI-UX-R1: the Review page's frequency-based candidate comparison and its plots, with no Qt.

The automatic columns are the frequency diagnostic's own, as shown or saved. A person may select another elastic FE mode for
a row to inspect it; the choice lives only here, is marked USER_REVIEW_HYPOTHESIS and reaches nothing else: the analysis,
its pairs, its MAC and a saved project do not change, and no registration or scientific gate reads it. Every plot draws
values that exist; an FRF curve is drawn only from FRF data the importer read.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
from typing import Mapping, Optional

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from new_gui import shape_model as sm

USER_HYPOTHESIS = "USER_REVIEW_HYPOTHESIS"
HEADERS = ("Row", "EXP mode", "EXP frequency (Hz)", "Selected FE mode", "Selected FE frequency (Hz)", "Δf (%)",
           "Nearest FE mode (automatic)")
TITLE = "Frequency-based candidate comparison"
LIMIT_TEXT = ("These are candidates chosen by frequency, not validated mode pairs. Δf (%) = 100 × (f_FE − f_EXP) / f_EXP. "
              "Mode identity needs a registration and MAC: see the MAC / Points page.")
PROVISIONAL_EXPLANATION = ("This experimental set holds FRF peak records, not fitted modes: each is a response snapshot at "
                           "an FRF peak. Its frequencies can be reviewed here, but MAC is not computed on them. The full "
                           "wording is in the details.")
FRF_NEEDS_SOURCE = "FRF curves are not kept in a saved project file. Check source files and Analyze again to show them."
FRF_NOT_IN_FILE = "This experimental file holds no FRF curves (dataset 58), so no spectrum is drawn: none is made up."
SAVED_PLOTS_TEXT = ("Shown from the saved file: frequencies and the saved magnitude pictures. Other components and FRF curves "
                    "need the source files: Check source files on the Analyze page, then Analyze.")
SESSION_ONLY_TEXT = "Manual choices are kept for this session only: they are not saved and change no saved or computed result."
_DASH = "—"
_INK, _MUTED, _GRID = "#3e4c59", "#52606d", "#e4e7eb"
_AUTOMATIC, _MANUAL = "#2563eb", "#b45309"


class DuplicateSelection(ValueError):
    """The FE mode is already selected for another row, and the caller did not accept a duplicate."""

    def __init__(self, rows: tuple):
        super().__init__(f"already selected for row {', '.join(str(row + 1) for row in rows)}")
        self.rows = rows


@dataclass(frozen=True)
class ReviewRow:
    row: int
    record: str
    exp_mode: str
    exp_text: str
    selected_mode: str
    selected_text: str
    difference_text: str
    nearest_mode: str
    manual: bool

    def cells(self) -> tuple:
        return (str(self.row + 1), self.exp_mode, self.exp_text, self.selected_mode, self.selected_text,
                self.difference_text, self.nearest_mode)

    @property
    def origin(self) -> str:
        return USER_HYPOTHESIS if self.manual else "automatic nearest frequency"


def _number(text) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class ReviewState:
    """``fe_hz`` and ``exp_hz`` (by record name) are full-precision frequencies when known; the shown text is the fallback."""

    def __init__(self, analysis, fe_hz: Optional[Mapping] = None, exp_hz: Optional[Mapping] = None):
        self.nearest = tuple(analysis.nearest_rows)
        self.options = tuple((row[0], row[1]) for row in analysis.fe_rows if row[2] == "elastic")
        self.fe_hz = {number: float((fe_hz or {}).get(number, _number(text))) for number, text in self.options}
        self.exp_hz = {row[0]: (exp_hz or {}).get(row[0], _number(row[2])) for row in self.nearest}
        self.manual: dict = {}
        self.provisional = any(sm.PROVISIONAL_TEXT in str(row[-1]) for row in analysis.experimental_rows)

    def __len__(self) -> int:
        return len(self.nearest)

    def row(self, index: int) -> ReviewRow:
        source = self.nearest[index]
        selected = self.manual.get(index)
        if selected is None:  # the service's own cells, untouched
            return ReviewRow(index, source[0], source[1], source[2], source[3], source[4], source[5], source[3], False)
        return ReviewRow(index, source[0], source[1], source[2], selected, dict(self.options)[selected],
                         self._difference(selected, self.exp_hz[source[0]]), source[3], True)

    def rows(self) -> tuple:
        return tuple(self.row(index) for index in range(len(self)))

    def _difference(self, mode: str, experimental: Optional[float]) -> str:
        if not experimental:
            return _DASH
        return f"{100.0 * (self.fe_hz[mode] - experimental) / experimental:+.2f}"

    def selected(self, index: int) -> str:
        return self.manual.get(index, self.nearest[index][3])

    def holders(self, mode: str, excluding: int = -1) -> tuple:
        return tuple(i for i in range(len(self)) if i != excluding and self.selected(i) == mode)

    def assign(self, index: int, mode: str, allow_duplicate: bool = False) -> None:
        """Select an elastic FE mode for one row; selecting the automatic mode again removes the manual mark."""
        if mode not in self.fe_hz:
            raise ValueError(f"FE mode {mode} is not an elastic mode of these results.")
        others = self.holders(mode, index)
        if others and not allow_duplicate:
            raise DuplicateSelection(others)
        self._set(index, mode)

    def _set(self, index: int, mode: str) -> None:
        if mode == self.nearest[index][3]:
            self.manual.pop(index, None)
        else:
            self.manual[index] = mode

    def swap(self, first: int, second: int) -> bool:
        one, other = self.selected(first), self.selected(second)
        if one not in self.fe_hz or other not in self.fe_hz:
            return False
        self._set(first, other)
        self._set(second, one)
        return True

    def reset(self, index: Optional[int] = None) -> None:
        if index is None:
            self.manual.clear()
        else:
            self.manual.pop(index, None)

    def duplicate_warning(self) -> str:
        groups = {}
        for index in range(len(self)):
            mode = self.selected(index)
            if mode in self.fe_hz:
                groups.setdefault(mode, []).append(index + 1)
        lines = [f"FE mode {mode} is selected for rows {', '.join(str(row) for row in rows)}."
                 for mode, rows in groups.items() if len(rows) > 1]
        return "Diagnostic: not one-to-one. " + " ".join(lines) if lines else ""

    def hypothesis_text(self) -> str:
        if not self.manual:
            return ""
        items = "; ".join(f"row {row.row + 1}: EXP {row.exp_mode} with FE {row.selected_mode}"
                          for row in self.rows() if row.manual)
        return f"{USER_HYPOTHESIS} (not a validated identity): {items}."


# ---------------------------------------------------------------------------------------------- plots


def _figure(size=(6.0, 3.6)) -> Figure:
    figure = Figure(figsize=size, constrained_layout=True)
    FigureCanvasAgg(figure)
    return figure


def _style(axis, xlabel: str, ylabel: str, title: str) -> None:
    axis.set_title(title, fontsize=10, color=_INK, loc="left")
    axis.set_xlabel(xlabel, fontsize=9, color=_MUTED)
    axis.set_ylabel(ylabel, fontsize=9, color=_MUTED)
    axis.tick_params(labelsize=8, colors=_MUTED)
    axis.grid(True, color=_GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(_GRID)


def _png(figure: Figure) -> bytes:
    out = io.BytesIO()
    with sm._RENDER:
        figure.savefig(out, format="png", dpi=130)
    return out.getvalue()


def _plotted(state: ReviewState) -> list:
    """(row, EXP Hz, selected FE Hz, difference %) of each row that has a selected FE mode with a frequency."""
    points = []
    for row in state.rows():
        experimental, fe, difference = _number(row.exp_text), _number(row.selected_text), _number(row.difference_text)
        if experimental is not None and fe is not None and difference is not None:
            points.append((row, experimental, fe, difference))
    return points


def frequency_plot(state: ReviewState, current: Optional[int] = None) -> bytes:
    figure = _figure()
    axis = figure.add_subplot(111)
    points = _plotted(state)
    for manual, colour, marker, label in ((False, _AUTOMATIC, "o", "Automatic nearest"), (True, _MANUAL, "D", USER_HYPOTHESIS)):
        chosen = [p for p in points if p[0].manual == manual]
        if chosen:
            axis.scatter([p[1] for p in chosen], [p[2] for p in chosen], s=36, c=colour, marker=marker, label=label, zorder=3,
                         edgecolors="white", linewidths=1.0)
    if points:
        low = min(min(p[1], p[2]) for p in points)
        high = max(max(p[1], p[2]) for p in points)
        axis.plot((low, high), (low, high), color=_MUTED, linewidth=1.0, linestyle="--", label="f_FE = f_EXP", zorder=1)
    for p in points:
        if p[0].row == current:
            axis.scatter([p[1]], [p[2]], s=130, facecolors="none", edgecolors=_INK, linewidths=1.5, zorder=4)
    _style(axis, "EXP frequency (Hz)", "Selected FE frequency (Hz)", "FE versus experimental frequency (candidates)")
    if points:
        axis.legend(fontsize=8, frameon=False, loc="upper left")
    return _png(figure)


def difference_plot(state: ReviewState, current: Optional[int] = None) -> bytes:
    figure = _figure()
    axis = figure.add_subplot(111)
    points = _plotted(state)
    for manual, colour, label in ((False, _AUTOMATIC, "Automatic nearest"), (True, _MANUAL, USER_HYPOTHESIS)):
        chosen = [p for p in points if p[0].manual == manual]
        if chosen:
            axis.bar([p[0].row + 1 for p in chosen], [p[3] for p in chosen], width=0.6, color=colour, label=label, zorder=3)
    axis.axhline(0.0, color=_MUTED, linewidth=1.0, zorder=2)
    for p in points:
        if p[0].row == current:
            axis.bar([p[0].row + 1], [p[3]], width=0.72, fill=False, edgecolor=_INK, linewidth=1.5, zorder=4)
    axis.set_xticks([p[0].row + 1 for p in points])
    _style(axis, "Row", "Δf (%)", "Signed frequency difference (candidates)")
    if points:
        axis.legend(fontsize=8, frameon=False)
    return _png(figure)


def frf_series(dataset) -> Optional[tuple]:
    """(frequency, indicator, coherence or None) the importer read from FRF data, or None: nothing is ever synthesized."""
    metadata = getattr(dataset, "metadata", None) or {}
    frequency = np.asarray(metadata.get("_frf_frequency_hz", ()), dtype=float)
    indicator = np.asarray(metadata.get("_frf_indicator", ()), dtype=float)
    if not len(frequency) or len(indicator) != len(frequency):
        return None
    coherence = np.asarray(metadata.get("_frf_mean_coherence", ()), dtype=float)
    return frequency, indicator, coherence if len(coherence) == len(frequency) else None


def frf_plot(series: tuple, marks=(), current: Optional[float] = None) -> bytes:
    """The combined FRF indicator with the set's record frequencies; coherence, when read, on its own axes below."""
    frequency, indicator, coherence = series
    figure = _figure((6.0, 4.4) if coherence is not None else (6.0, 3.2))
    if coherence is not None:
        axis, lower = figure.subplots(2, 1, sharex=True, height_ratios=(3, 1))
    else:
        axis, lower = figure.add_subplot(111), None
    axis.semilogy(frequency, np.maximum(indicator / max(float(np.max(indicator)), 1.0e-30), 1.0e-12), color=_AUTOMATIC,
                  linewidth=1.2)
    for value in marks:
        axis.axvline(value, color=_MUTED, linewidth=0.8, linestyle=":")
    if current is not None:
        axis.axvline(current, color=_INK, linewidth=1.5)
    _style(axis, "" if lower is not None else "Frequency (Hz)", "Normalized indicator",
           "Experimental FRF indicator; dotted: records of this set; solid: selected row")
    if lower is not None:
        lower.plot(frequency, coherence, color=_AUTOMATIC, linewidth=1.0)
        lower.set_ylim(0.0, 1.05)
        _style(lower, "Frequency (Hz)", "Mean coherence", "")
    return _png(figure)


def mac_plot(view) -> bytes:
    """The comparator's MAC matrix as computed or saved; a value not computed stays blank, assigned pairs are outlined."""
    fe, experimental = view.mac_fe_modes, view.mac_experimental_modes
    values = np.array([[np.nan if value is None else float(value) for value in row] for row in view.mac_values], dtype=float)
    figure = _figure((max(4.2, 1.8 + 0.34 * len(experimental)), max(3.2, 1.2 + 0.26 * len(fe))))
    axis = figure.add_subplot(111)
    image = axis.imshow(values, cmap="Blues", vmin=0.0, vmax=1.0, aspect="auto", interpolation="nearest")
    axis.set_xticks(range(len(experimental)), [str(mode) for mode in experimental], fontsize=8)
    axis.set_yticks(range(len(fe)), [str(mode) for mode in fe], fontsize=8)
    axis.set_xlabel("EXP mode", fontsize=9, color=_MUTED)
    axis.set_ylabel("FE mode", fontsize=9, color=_MUTED)
    axis.set_title("MAC over the mapped measured DOFs; outlined: assigned pairs", fontsize=10, color=_INK, loc="left")
    for row, column in view.assigned_cells:
        axis.add_patch(Rectangle((column - 0.5, row - 0.5), 1, 1, fill=False, edgecolor=_MANUAL, linewidth=1.6))
    figure.colorbar(image, ax=axis, label="MAC")
    return _png(figure)


__all__ = ["DuplicateSelection", "FRF_NEEDS_SOURCE", "FRF_NOT_IN_FILE", "HEADERS", "LIMIT_TEXT", "PROVISIONAL_EXPLANATION",
           "ReviewRow", "ReviewState", "SAVED_PLOTS_TEXT", "SESSION_ONLY_TEXT", "TITLE", "USER_HYPOTHESIS", "difference_plot",
           "frequency_plot", "frf_plot", "frf_series", "mac_plot"]
