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
FRF_NOT_USABLE = ("This file holds dataset 58 records, but the importer formed no usable FRF curve from them, so no spectrum is "
                  "drawn: none is made up.")
FRF_PEAK_NOTE = ("Triangles: FRF peak records, response snapshots at detected peaks, not fitted modal shapes. Orange: the record "
                 "of the selected table row.")
FITTED_NOTE = ("Dashed lines: fitted modes of the chosen set at their frequencies. They are not peaks of this curve. Orange: the "
               "record of the selected table row.")
PLOTS_EXPLANATION = ("Each dot or bar is one table row: a frequency-based candidate, not a validated mode pair. Click a dot or "
                     "a bar to select its row and show its shapes. On the dashed line FE = EXP; above it FE is higher.")
CONFLICT_TEXT = ("Pink FE frequency: that FE mode is selected for more than one EXP record (not one-to-one). It is not a "
                 "frequency-error limit.")
MANUAL_TINT_TEXT = "Pale yellow row: your manual FE choice."
DETAIL_LIMIT = 10.0  # percent: the detailed view of the signed error; larger values stay drawn in full above it
LABEL_AUTOMATIC, LABEL_EQUAL = "Automatic nearest-frequency candidate", "Equal frequency line (FE = EXP)"
LABEL_MANUAL = f"Manual candidate ({USER_HYPOTHESIS})"
LABEL_SELECTED, LABEL_SELECTED_RECORD = "Selected table row", "Record of the selected row"
LABEL_FRF_PEAK, LABEL_FITTED = "FRF peak record, not fitted", "Fitted mode frequency"
SAVED_PLOTS_TEXT = ("Shown from the saved file: frequencies and the saved magnitude pictures. Other components and FRF curves "
                    "need the source files: Check source files on the Analyze page, then Analyze.")
SESSION_ONLY_TEXT = "Manual choices are kept for this session only: they are not saved and change no saved or computed result."
UNVERIFIED_TITLE = "Unverified frequency-based candidates"
PAIRED_TITLE = "Frequency-based candidates (the MAC pairs are on the MAC / Points page)"
STATUS_UNREGISTERED = ("No physical registration: the FE modes below are matched by frequency only and are unverified; "
                       "no mode pairs and no MAC.")
STATUS_FRF_PEAKS = ("FRF peak records, not fitted modes: the FE modes below are matched by frequency only and are "
                    "unverified; no mode pairs and no MAC.")
STATUS_FAILED = ("The registration check failed: the FE modes below are matched by frequency only and are unverified; "
                 "no mode pairs and no MAC.")
STATUS_CONFIRMED = ("Mode pairs and MAC use the registration you confirmed (see MAC / Points); this table is matched by "
                    "frequency only.")
STATUS_VERIFIED = ("Mode pairs and MAC use a verified physical registration (see MAC / Points); this table is matched by "
                   "frequency only.")
_DASH = "—"
_INK, _MUTED, _GRID = "#1f2933", "#52606d", "#e4e7eb"
_AUTOMATIC, _MANUAL = "#2563eb", "#b45309"
LABEL_SPACING_POINTS = 11.0  # the width of one vertical FRF label, its bold form included


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

    def conflicts(self) -> dict:
        """FE mode -> table rows (from 1) of every FE mode selected more than once."""
        groups: dict = {}
        for index in range(len(self)):
            mode = self.selected(index)
            if mode in self.fe_hz:
                groups.setdefault(mode, []).append(index + 1)
        return {mode: rows for mode, rows in groups.items() if len(rows) > 1}

    def duplicate_warning(self) -> str:
        groups = self.conflicts()
        if not groups:
            return ""
        return "Not one-to-one: " + "; ".join(f"FE {mode} (rows {', '.join(str(r) for r in rows)})"
                                               for mode, rows in groups.items()) + "."

    def hypothesis_text(self) -> str:
        if not self.manual:
            return ""
        items = "; ".join(f"row {row.row + 1}: EXP {row.exp_mode} with FE {row.selected_mode}"
                          for row in self.rows() if row.manual)
        return f"{USER_HYPOTHESIS} (not a validated identity): {items}."


def status_sentence(analysis, confirmed: bool) -> str:
    """The result's status in one sentence. Without a comparison every row is an unverified frequency candidate."""
    if analysis is None:
        return ""
    if analysis.comparison is not None:
        return STATUS_CONFIRMED if confirmed else STATUS_VERIFIED
    if any(sm.PROVISIONAL_TEXT in str(row[-1]) for row in analysis.experimental_rows):
        return STATUS_FRF_PEAKS
    return STATUS_FAILED if analysis.registration_outcome == "failed" else STATUS_UNREGISTERED


def table_title(analysis) -> str:
    return PAIRED_TITLE if analysis is not None and analysis.comparison is not None else UNVERIFIED_TITLE


# ---------------------------------------------------------------------------------------------- plots


def _figure(size=(6.0, 3.6), dpi: float = 100.0) -> Figure:
    figure = Figure(figsize=size, dpi=dpi, constrained_layout=True)
    FigureCanvasAgg(figure)
    return figure


def _style(axis, xlabel: str, ylabel: str, title: str) -> None:
    axis.set_title(title, fontsize=10, color=_INK, loc="left")
    axis.set_xlabel(xlabel, fontsize=9, color=_MUTED, labelpad=4)
    axis.set_ylabel(ylabel, fontsize=9, color=_MUTED, labelpad=4)
    axis.tick_params(labelsize=8.5, colors=_MUTED, pad=3)
    axis.grid(True, color=_GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(_GRID)


def _png(figure: Figure, dpi: Optional[float] = 130) -> bytes:
    out = io.BytesIO()
    with sm._RENDER:
        figure.savefig(out, format="png", dpi=dpi or figure.dpi)
    return out.getvalue()


def _canvas(width: Optional[int], height: Optional[int], ratio: float, default=(6.0, 3.6)) -> Figure:
    """A figure of exactly ``width`` x ``height`` logical pixels at the screen's pixel ratio, so the PNG is shown without
    stretching. Without a size: the default size at 130 dpi, as before."""
    if width and height:
        return _figure((width / 100.0, height / 100.0), 100.0 * max(1.0, float(ratio)))
    return _figure(default, 130.0)


@dataclass(frozen=True)
class Chart:
    """A chart PNG and where its rows are drawn, in PNG pixels (origin top left): dots (row, x, y), or bar spans
    (row, x0, x1, y0, y1). ``pixel_ratio`` is PNG pixels per logical pixel."""

    png: bytes
    points: tuple = ()
    spans: tuple = ()
    pixel_ratio: float = 1.0
    note: str = ""


def _to_png_pixels(figure: Figure, axis, x: float, y: float) -> tuple:
    px, py = axis.transData.transform((x, y))
    return float(px), float(figure.bbox.height - py)


def _plotted(state: ReviewState) -> list:
    """(row, EXP Hz, selected FE Hz, difference %) of each row that has a selected FE mode with a frequency."""
    points = []
    for row in state.rows():
        experimental, fe, difference = _number(row.exp_text), _number(row.selected_text), _number(row.difference_text)
        if experimental is not None and fe is not None and difference is not None:
            points.append((row, experimental, fe, difference))
    return points


def _not_drawn(state: ReviewState, points) -> str:
    missing = len(state) - len(points)
    if not missing:
        return ""
    return (f"{missing} EXP record{'' if missing == 1 else 's'} without a selected FE frequency "
            f"{'is' if missing == 1 else 'are'} not drawn.")


def selected_point(state: ReviewState, current: Optional[int]):
    """The plotted point of the selected table row, or None."""
    return next((p for p in _plotted(state) if p[0].row == current), None)


def frequency_chart(state: ReviewState, current: Optional[int] = None, width: Optional[int] = None,
                    height: Optional[int] = None, ratio: float = 1.0) -> Chart:
    """FE against EXP frequency of every row with both, as stored; the dot of the selected row is ringed."""
    figure = _canvas(width, height, ratio)
    axis = figure.add_subplot(111)
    points = _plotted(state)
    for manual, colour, marker, label in ((False, _AUTOMATIC, "o", LABEL_AUTOMATIC), (True, _MANUAL, "D", LABEL_MANUAL)):
        chosen = [p for p in points if p[0].manual == manual]
        if chosen:
            axis.scatter([p[1] for p in chosen], [p[2] for p in chosen], s=46, c=colour, marker=marker, label=label, zorder=3,
                         edgecolors="white", linewidths=1.0)
    if points:
        low = min(min(p[1], p[2]) for p in points)
        high = max(max(p[1], p[2]) for p in points)
        axis.plot((low, high), (low, high), color=_MUTED, linewidth=1.0, linestyle="--", label=LABEL_EQUAL, zorder=1)
        pad = 0.04 * ((high - low) or 1.0)
        axis.set_xlim(low - pad, high + pad)
        axis.set_ylim(low - pad, high + pad)
    chosen = selected_point(state, current)
    if chosen is not None:
        axis.scatter([chosen[1]], [chosen[2]], s=190, facecolors="none", edgecolors=_INK, linewidths=2.0, zorder=4,
                     label=LABEL_SELECTED)
        low_x, high_x = axis.get_xlim()
        right = chosen[1] > (low_x + high_x) / 2
        axis.annotate(f"EXP {chosen[0].exp_mode} / FE {chosen[0].selected_mode}", (chosen[1], chosen[2]),
                      xytext=(-10 if right else 10, -14), textcoords="offset points", fontsize=8.5, color=_INK,
                      weight="bold", ha="right" if right else "left")
    _style(axis, "EXP frequency (Hz)", "Selected FE frequency (Hz)", "FE vs EXP frequency: candidates, not validated pairs")
    if points:
        axis.legend(fontsize=7.5, frameon=True, framealpha=0.92, edgecolor=_GRID, loc="upper left")
    figure.canvas.draw()
    hits = tuple((p[0].row, *_to_png_pixels(figure, axis, p[1], p[2])) for p in points)
    return Chart(_png(figure, figure.dpi if width else None), points=hits if width else (),
                 pixel_ratio=figure.dpi / 100.0, note=_not_drawn(state, points))


def frequency_plot(state: ReviewState, current: Optional[int] = None) -> bytes:
    return frequency_chart(state, current).png


def _bars(axis, points, current, limit: Optional[float] = None) -> None:
    for manual, colour, label in ((False, _AUTOMATIC, LABEL_AUTOMATIC), (True, _MANUAL, LABEL_MANUAL)):
        chosen = [p for p in points if p[0].manual == manual]
        if chosen:
            axis.bar([p[0].row + 1 for p in chosen], [p[3] for p in chosen], width=0.62, color=colour, label=label, zorder=3)
    axis.axhline(0.0, color=_MUTED, linewidth=1.0, zorder=2)
    chosen = next((p for p in points if p[0].row == current), None)
    if chosen is not None:
        axis.bar([chosen[0].row + 1], [chosen[3]], width=0.8, fill=False, edgecolor=_INK, linewidth=2.0, zorder=4,
                 label=LABEL_SELECTED)
    if limit is not None:
        edge = limit * 1.2
        axis.set_ylim(-edge, edge)
        for p in points:
            if abs(p[3]) > limit:  # cut at the view's edge, whole in the full-range view; its true value is written here
                sign = 1.0 if p[3] > 0 else -1.0
                axis.plot([p[0].row + 1], [sign * edge * 0.94], marker="^" if sign > 0 else "v", color=_INK, markersize=6,
                          zorder=5)
                axis.annotate(f"{p[3]:+.1f}", (p[0].row + 1, sign * edge * 0.94), xytext=(0, -13 if sign > 0 else 6),
                              textcoords="offset points", ha="center", fontsize=7.5, color=_INK, zorder=6)
    axis.set_xticks([p[0].row + 1 for p in points], [p[0].exp_mode for p in points])
    if len(points) > 14:
        axis.tick_params(axis="x", labelsize=7.5)


def difference_chart(state: ReviewState, current: Optional[int] = None, width: Optional[int] = None,
                     height: Optional[int] = None, ratio: float = 1.0) -> Chart:
    """The signed error 100 (f_FE - f_EXP) / f_EXP of every row, as stored. When some rows exceed DETAIL_LIMIT and others do
    not, a second view shows ±DETAIL_LIMIT %: the larger bars are cut at its edge, marked and labelled with their value, and
    stay whole in the full-range view above. No value is changed or left out."""
    points = _plotted(state)
    values = [abs(p[3]) for p in points]
    detail = bool(values) and max(values) > DETAIL_LIMIT and min(values) <= DETAIL_LIMIT
    figure = _canvas(width, height, ratio, (6.0, 5.2) if detail else (6.0, 3.6))
    if detail:
        full, close = figure.subplots(2, 1, sharex=True, height_ratios=(2, 3))
    else:
        full, close = figure.add_subplot(111), None
    _bars(full, points, current)
    _style(full, "" if close is not None else "EXP mode", "FE − EXP (%)",
           "Signed frequency error, full range" if close is not None else "Signed frequency error")
    if points:
        full.legend(fontsize=7.5, frameon=True, framealpha=0.92, edgecolor=_GRID)
    if close is not None:
        _bars(close, points, current, DETAIL_LIMIT)
        _style(close, "EXP mode", "FE − EXP (%)", f"Detail ±{DETAIL_LIMIT:g} %: larger bars are cut, value written")
    figure.canvas.draw()
    spans = []
    for axis in (full, close):
        if axis is None:
            continue
        y0, y1 = axis.get_ylim()
        for p in points:
            x0, top = _to_png_pixels(figure, axis, p[0].row + 1 - 0.45, y1)
            x1, bottom = _to_png_pixels(figure, axis, p[0].row + 1 + 0.45, y0)
            spans.append((p[0].row, x0, x1, top, bottom))
    return Chart(_png(figure, figure.dpi if width else None), spans=tuple(spans) if width else (),
                 pixel_ratio=figure.dpi / 100.0, note=_not_drawn(state, points))


def difference_plot(state: ReviewState, current: Optional[int] = None) -> bytes:
    return difference_chart(state, current).png


def rows_at(chart: Chart, x: float, y: float, reach: float = 9.0) -> tuple:
    """The rows under a click at (x, y) PNG pixels, nearest first: every dot within ``reach`` logical pixels (overlapping
    dots all count, so none is chosen for the person), then the bar span holding the click."""
    reach *= chart.pixel_ratio
    found = sorted((((px - x) ** 2 + (py - y) ** 2) ** 0.5, row) for row, px, py in chart.points)
    rows = [row for distance, row in found if distance <= reach]
    for row, x0, x1, top, bottom in chart.spans:
        if x0 <= x <= x1 and top <= y <= bottom and row not in rows:
            rows.append(row)
    return tuple(rows)


def frf_series(dataset) -> Optional[tuple]:
    """(frequency, indicator, coherence or None) the importer read from FRF data, or None: nothing is ever synthesized."""
    metadata = getattr(dataset, "metadata", None) or {}
    frequency = np.asarray(metadata.get("_frf_frequency_hz", ()), dtype=float)
    indicator = np.asarray(metadata.get("_frf_indicator", ()), dtype=float)
    if not len(frequency) or len(indicator) != len(frequency):
        return None
    coherence = np.asarray(metadata.get("_frf_mean_coherence", ()), dtype=float)
    return frequency, indicator, coherence if len(coherence) == len(frequency) else None


def spread_labels(positions, gap: float, low: float, high: float) -> list:
    """Label places in the order of ``positions``, at least ``gap`` apart and as near their positions as that allows.

    Only where a label is written: a marker stays at its own frequency, and a leader joins the two."""
    count = len(positions)
    if not count:
        return []
    order = sorted(range(count), key=lambda i: positions[i])
    gap = min(gap, (high - low) / max(1, count - 1))
    # with s = place - rank * gap, keeping the gaps is keeping s in order: the closest such s is a pooled running mean
    pools: list = []
    for rank, index in enumerate(order):
        pools.append([positions[index] - rank * gap, 1])
        while len(pools) > 1 and pools[-2][0] > pools[-1][0]:
            value, size = pools.pop()
            pools[-1] = [(pools[-1][0] * pools[-1][1] + value * size) / (pools[-1][1] + size), pools[-1][1] + size]
    shifted = [value for value, size in pools for _ in range(size)]
    shifted = [min(max(value, low), high - (count - 1) * gap) for value in shifted]
    places = [0.0] * count
    for rank, index in enumerate(order):
        places[index] = shifted[rank] + rank * gap
    return places


def _record_number(name: str) -> str:
    return name.split()[-1] if name.split() else name


def frf_figure(series: tuple, records=(), current: Optional[int] = None, provisional: bool = False,
               width: Optional[int] = None, height: Optional[int] = None, ratio: float = 1.0) -> Figure:
    """The imported FRF indicator, as read, with the set's records marked at their frequencies; coherence, when read, below.

    ``records`` are (name, Hz). FRF peak records are triangles on the curve; fitted modes are dashed lines, never peaks. Each
    record carries only its number above the curve (spread apart when close; a leader joins it to its frequency); the
    selected record carries its full name and frequency. Every record stays listed in the Review table."""
    frequency, indicator, coherence = series
    default = (9.0, 4.8) if coherence is not None else (9.0, 3.6)
    figure = _canvas(width, height, ratio, default)
    if coherence is not None:
        axis, lower = figure.subplots(2, 1, sharex=True, height_ratios=(3, 1))
    else:
        axis, lower = figure.add_subplot(111), None
    curve = np.maximum(indicator / max(float(np.max(indicator)), 1.0e-30), 1.0e-12)
    axis.semilogy(frequency, curve, color=_AUTOMATIC, linewidth=1.1, label="Imported FRF indicator")
    kind = LABEL_FRF_PEAK if provisional else LABEL_FITTED
    for index, (name, hz) in enumerate(records):
        selected = index == current
        colour, width_line = (_MANUAL, 1.8) if selected else (_MUTED, 0.7)
        label = kind if index == 0 else None
        if provisional:
            y = curve[int(np.argmin(np.abs(frequency - hz)))]
            axis.scatter([hz], [y], marker="v", s=70 if selected else 26, c=colour, zorder=4, label=label)
        else:
            axis.axvline(hz, color=colour, linewidth=width_line, linestyle="--", zorder=2, label=label, alpha=1.0 if selected else 0.7)
    if current is not None and 0 <= current < len(records):
        axis.axvline(records[current][1], color=_MANUAL, linewidth=1.8, zorder=3, label=LABEL_SELECTED_RECORD)
    _style(axis, "" if lower is not None else "Frequency (Hz)", "Normalized indicator", "")
    axis.legend(fontsize=7.5, frameon=True, framealpha=0.92, edgecolor=_GRID, loc="lower right")
    low, high = axis.get_xlim()
    axis.set_xlim(low, high)  # the labels are placed for this range
    room = axis.get_position().width * figure.get_figwidth() * 72.0
    places = spread_labels([hz for _name, hz in records], LABEL_SPACING_POINTS / room * (high - low), low, high)
    transform = axis.get_xaxis_transform()
    for index, ((name, hz), place) in enumerate(zip(records, places)):
        if index == current:
            continue
        axis.annotate(_record_number(name), xy=(hz, 1.0), xycoords=transform, xytext=(place, 1.025), textcoords=transform,
                      ha="center", va="bottom", fontsize=7, color=_MUTED, annotation_clip=False,
                      arrowprops={"arrowstyle": "-", "color": _GRID, "linewidth": 0.6, "shrinkA": 0, "shrinkB": 0})
    if current is not None and 0 <= current < len(records):
        name, hz = records[current]
        middle = min(max(hz, low + 0.12 * (high - low)), high - 0.12 * (high - low))
        axis.annotate(f"{name}: {hz:.2f} Hz", xy=(hz, 1.0), xycoords=transform, xytext=(middle, 1.11), textcoords=transform,
                      ha="center", va="bottom", fontsize=8.5, color=_INK, weight="bold", annotation_clip=False,
                      bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": _MANUAL, "linewidth": 1.0},
                      arrowprops={"arrowstyle": "-", "color": _MANUAL, "linewidth": 0.9, "shrinkA": 0, "shrinkB": 0})
    if lower is not None:
        lower.plot(frequency, coherence, color=_AUTOMATIC, linewidth=1.0)
        lower.set_ylim(0.0, 1.05)
        _style(lower, "Frequency (Hz)", "Mean coherence", "")
    return figure


def frf_chart(series: tuple, records=(), current: Optional[int] = None, provisional: bool = False,
              width: Optional[int] = None, height: Optional[int] = None, ratio: float = 1.0) -> Chart:
    """``frf_figure`` as a PNG with, per record, a narrow clickable column at its frequency over the indicator axis."""
    figure = frf_figure(series, records, current, provisional, width, height, ratio)
    figure.canvas.draw()
    axis = figure.axes[0]
    spans = []
    if width:
        y0, y1 = axis.get_ylim()
        reach = 5.0 * figure.dpi / 100.0
        for index, (_name, hz) in enumerate(records):
            x, top = _to_png_pixels(figure, axis, hz, y1)
            _x, bottom = _to_png_pixels(figure, axis, hz, y0)
            spans.append((index, x - reach, x + reach, top, bottom))
    return Chart(_png(figure, figure.dpi if width else None), spans=tuple(spans), pixel_ratio=figure.dpi / 100.0)


def frf_plot(series: tuple, records=(), current: Optional[int] = None, provisional: bool = False) -> bytes:
    return _png(frf_figure(series, records, current, provisional))


def frf_missing(dataset, saved: bool) -> str:
    """Why no curve can be drawn, in the file's own terms."""
    if saved:
        return FRF_NEEDS_SOURCE
    metadata = getattr(dataset, "metadata", None) or {}
    if 58 in tuple(metadata.get("dataset_types") or ()):
        return FRF_NOT_USABLE
    return FRF_NOT_IN_FILE


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
           "frequency_plot", "frf_plot", "frf_series", "mac_plot", "Chart", "frequency_chart", "difference_chart",
           "frf_chart", "rows_at", "CONFLICT_TEXT", "MANUAL_TINT_TEXT", "DETAIL_LIMIT"]
