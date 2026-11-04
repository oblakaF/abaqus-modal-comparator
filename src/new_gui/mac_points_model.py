"""GUI-UX-R1: what the MAC / Points page states, with no Qt.

Everything comes from the comparator's result or the saved comparison view. Nothing here computes a MAC, maps a point or
chooses a registration. MAC belongs to a pair of mode shapes over the mapped measured DOFs, so no value per point exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
from typing import Optional

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import review_model as rv
from new_gui import shape_model as sm
from services import analysis_project as ap

EVIDENCE_HEADERS = ("Evidence level", "State for this result", "What it means")
UNAVAILABLE_BADGE = "MAC NOT AVAILABLE"
REASONS = {
    am.PROVISIONAL: ("MAC is not available: the chosen set holds FRF peak records, not fitted modes. Choose a fitted modal set "
                     "if the file holds one."),
    am.REFUSED: ("MAC is not available: no registration is confirmed for these two files, and no accepted registration "
                 "matches their geometry. A registration for other geometry is never imported. Set one up below."),
    am.FAILED: "MAC is not available: the registration check could not be completed, so nothing about these files is verified.",
    am.NOT_CONFIRMED: "MAC is not available: the confirmed registration does not hold for the current data. See the details on Review.",
}
SAVED_NO_REGISTRATION = "MAC is not available: the saved result has no registration. Its files must be checked and analyzed again."
NO_RESULT = "No result yet. Run Analyze, or open a saved result."
NEEDS_SOURCE = ("Point correspondence, the pair pictures and line profiles are not kept in a saved file. Check source files on "
                "the Analyze page, Analyze again and repeat the comparison to show them.")
NO_DETAIL = "The point-by-point detail is not available for this result."
NO_LINE = "No line of at least three mapped points runs along a coordinate axis, so no profile is drawn."
NOT_MEASURED = "This component is not measured on the chosen line: no profile is drawn and no value is created."
PAIR_TEXT = ("Both shapes on the same registered measured points, from the comparator's pair data; the third view is its "
             "amplitude correlation. Click a pair to draw it.")
POINT_NOTE = "MAC applies to each mode pair over all mapped measured DOFs. There is no MAC per point."
POINT_HEADERS = ("EXP point", "X", "Y", "Z", "FE node", "Residual (FE units)", "Measured DOFs")
COVERAGE_COLUMNS = (0, 3, 8, 9, 10)  # of comparison_model.PAIR_HEADERS: FE, EXP, measured DOFs, coverage, mapped points
COVERAGE_HEADERS = tuple(cm.PAIR_HEADERS[i] for i in COVERAGE_COLUMNS)
PROVENANCE_HEADERS = ("Fact", "Value")
MAPPING_FACTS = ("FE geometry identity", "Orientation source", "Geometry candidates evaluated",
                 "Mapping RMS / max residual (FE units)", "Matched point fraction", "Comparator state")  # of the view's provenance
PROFILE_NOTE = ("In the registered common coordinate system. One complex scale is fitted to the experiment over all mapped "
                "DOFs of the pair; the profile does not change the MAC or the pair.")
AXES = "XYZ"


def evidence_levels(analysis, review_state, kind: str) -> tuple:
    """The four kinds of evidence, never merged; ``kind`` is the registration of the result shown."""
    view = analysis.comparison
    manual = len(review_state.manual) if review_state is not None else 0
    rows = len(review_state) if review_state is not None else 0
    frequency = f"{rows} rows, {manual} {rv.USER_HYPOTHESIS}" if manual else f"{rows} rows, all automatic"
    if view is None:
        mac = "Not available"
    else:
        mac = f"{len(view.pair_rows)} admissible pair{'' if len(view.pair_rows) == 1 else 's'}"
    confirmed = "Applied to this result" if kind == ap.KIND_CONFIRMED else "None applied"
    reference = "Applied: accepted registration matched by FE geometry" if kind == ap.KIND_ARCHIVED else "None applied"
    return (("Frequency-based candidate selection", frequency, "Frequency proximity only, on the Review page. Never a mode identity."),
            ("MAC-based modal identity diagnostics", mac, "The comparator's result, only with a registration."),
            ("User-confirmed registration", confirmed, "Records a person's statement. It is not independent proof."),
            ("Physically validated archived evidence", reference, "Reused only for the same geometry. A manual choice never changes it."))


def unavailable_reason(analysis, saved: bool) -> str:
    if analysis is None:
        return NO_RESULT
    if analysis.comparison is not None:
        return ""
    return REASONS.get(analysis.registration_outcome) or (SAVED_NO_REGISTRATION if saved else REASONS[am.REFUSED])


def coverage_rows(view) -> tuple:
    return tuple(tuple(row.cells[i] for i in COVERAGE_COLUMNS) for row in view.pair_rows)


def point_rows(result) -> tuple:
    """Each experimental point with its mapped FE node and residual, as the comparator's geometry match holds them."""
    try:
        experimental, fe = result.experimental.modes[0], result.abaqus.modes[0]
        mapping = np.asarray(result.geometry.experimental_to_abaqus)
        physical = result.geometry.physical_distances
        residuals = np.asarray(result.geometry.distances if physical is None else physical, dtype=float)
        nodes, coordinates = np.asarray(experimental.node_ids), np.asarray(experimental.coordinates, dtype=float)
        if not len(mapping) == len(nodes) == len(residuals) == len(coordinates):
            return ()
        measured = getattr(experimental, "measured_dofs", None)
        mask = None if measured is None else np.asarray(measured, dtype=bool)
        rows = []
        for index, node in enumerate(nodes):
            dofs = "not recorded" if mask is None else " ".join(a for a, used in zip(AXES, mask[index]) if used) or "none"
            rows.append((str(node), *(f"{value:.5g}" for value in coordinates[index]),
                         str(np.asarray(fe.node_ids)[int(mapping[index])]), f"{residuals[index]:.4g}", dofs))
        return tuple(rows)
    except (AttributeError, IndexError, TypeError, ValueError):
        return ()


@dataclass(frozen=True)
class ProfileLine:
    """Mapped points sharing the two other coordinates, in order along ``axis``."""

    axis: int
    label: str
    indices: tuple


def profile_lines(pair) -> tuple:
    try:
        coordinates = np.asarray(pair.coordinates, dtype=float)
        if coordinates.ndim != 2 or coordinates.shape[1] != 3 or np.asarray(pair.abaqus_vector).shape != coordinates.shape:
            return ()
    except (AttributeError, TypeError, ValueError):
        return ()
    spans = np.ptp(coordinates, axis=0)
    tolerance = max(float(spans.max()) * 1.0e-3, 1.0e-30)
    lines = []
    for axis in range(3):
        if spans[axis] <= tolerance:
            continue
        others = [other for other in range(3) if other != axis]
        groups: dict = {}
        for index, point in enumerate(coordinates):
            groups.setdefault(tuple(np.round(point[others] / tolerance).astype(np.int64)), []).append(index)
        for members in groups.values():
            if len(members) >= 3:
                members = sorted(members, key=lambda i: coordinates[i, axis])
                where = ", ".join(f"{AXES[o]} = {coordinates[members[0], o]:.4g}" for o in others if spans[o] > tolerance)
                lines.append(ProfileLine(axis, f"Along {AXES[axis]}" + (f" at {where}" if where else ""), tuple(members)))
    return tuple(lines)


def _scaled(pair) -> tuple:
    from modal_scaling import least_squares_complex_scale, measured_pair_values, optimal_real_phase

    source, target = measured_pair_values(pair)
    _fitted, coefficient = least_squares_complex_scale(source, target)
    return coefficient, optimal_real_phase(target)


def profile_plot(pair, line: ProfileLine, component: int) -> Optional[bytes]:
    """FE and experimental displacement along one line, or None when the component is not measured on all of it."""
    indices = np.asarray(line.indices)
    fe = np.asarray(pair.abaqus_vector, dtype=complex)
    experimental = np.asarray(pair.experimental_vector, dtype=complex)
    mask = getattr(pair, "measured_dof_mask", None)
    measured = np.ones(fe.shape, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if not measured[indices, component].all():
        return None
    coefficient, phase = _scaled(pair)
    fe_line = np.real(fe[indices, component] * coefficient * phase)
    experimental_line = np.real(experimental[indices, component] * phase)
    position = np.asarray(pair.coordinates, dtype=float)[indices, line.axis]
    figure = Figure(figsize=(6.2, 3.4), constrained_layout=True)
    FigureCanvasAgg(figure)
    axis = figure.add_subplot(111)
    axis.plot(position, fe_line, color="#2563eb", linewidth=2, marker="o", markersize=5, label=f"FE mode {pair.abaqus_mode}")
    axis.plot(position, experimental_line, color="#b45309", linewidth=2, linestyle="--", marker="D", markersize=5,
              label=f"EXP mode {pair.experimental_mode}")
    axis.axhline(0.0, color="#52606d", linewidth=0.8)
    axis.set_title(f"{line.label}: {AXES[component]} displacement", fontsize=10, color="#3e4c59", loc="left")
    axis.set_xlabel(f"{AXES[line.axis]} (registered coordinates, FE units)", fontsize=9, color="#52606d")
    axis.set_ylabel("Fitted amplitude", fontsize=9, color="#52606d")
    axis.tick_params(labelsize=8, colors="#52606d")
    axis.grid(True, color="#e4e7eb", linewidth=0.8)
    axis.legend(fontsize=8, frameon=False)
    out = io.BytesIO()
    with sm._RENDER:
        figure.savefig(out, format="png", dpi=130)
    return out.getvalue()


__all__ = ["evidence_levels", "point_rows", "profile_lines", "profile_plot", "unavailable_reason"]
