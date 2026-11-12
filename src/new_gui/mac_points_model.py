"""GUI-UX-R1: what the MAC / Points page states, with no Qt.

Everything comes from the comparator's result or the saved comparison view. Nothing here computes a MAC, maps a point or
chooses a registration. MAC belongs to a pair of mode shapes over the mapped measured DOFs, so no value per point exists.

ABM-PLATE-POINT-MAC-GUI-1: the exploratory trial is ``services.trial_point_mac``'s. This module only starts it on the data
read in this session, between two checks of the source identities, and words and draws what it returned.
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
from services import trial_point_mac as tp

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
MEASURED_TITLE = "Measured experimental points"
MEASURED_NOTE = ("The measurement geometry as read, in the file's own coordinates. It needs no registration and says nothing about "
                 "mode identity or MAC.")
MEASURED_NEEDS_SOURCE = ("The measured points are not kept in a saved file. Check source files on the Analyze page, then Analyze, to "
                         "inspect them.")
MEASURED_HEADERS = ("EXP point", "X", "Y", "Z", "Measured DOFs")
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
READINESS_TITLE = "Can MAC be computed for this result?"
MAC_PLAIN = ("MAC compares the shapes of two modes over the same measured points and directions: 1 means the same shape, near "
             "0 unrelated shapes. It needs fitted EXP modes and the FE points matched to the measured ones by a registration.")
READY_QUESTIONS = ("Fitted EXP modes", "FE-to-EXP registration", "Measured directions and points", "MAC")
SET_UP = "Use Set up registration... below."


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


def _provisional(analysis) -> bool:
    return analysis.registration_outcome == am.PROVISIONAL or any(sm.PROVISIONAL_TEXT in str(row[-1])
                                                                   for row in analysis.experimental_rows)


def _directions(mode) -> str:
    measured = getattr(mode, "measured_dofs", None)
    points = len(mode.node_ids)
    if measured is None:
        return f"{points} points; the file states no measured-direction list"
    mask = np.asarray(measured, dtype=bool)
    axes = [axis for column, axis in enumerate(AXES) if mask[:, column].any()]
    return f"{', '.join(axes) or 'none'} at {points} points"


def readiness_rows(analysis, saved: bool, measured_mode, kind: str) -> tuple:
    """ABM-UX5: the four prerequisites of MAC, each answered from the result shown; nothing is inferred or set up here."""
    if analysis is None:
        return ((READY_QUESTIONS[3], NO_RESULT),)
    view = analysis.comparison
    provisional = _provisional(analysis)
    if provisional:
        fitted = "No: the chosen set holds FRF peak records (response snapshots), not fitted modes."
    else:
        fitted = f"Yes: {analysis.experimental_total or len(analysis.experimental_rows)} fitted records of {analysis.set_title}."
    if view is not None:
        registration = ("Yes: the registration you confirmed. Your confirmation is your statement, not independent proof."
                        if kind == ap.KIND_CONFIRMED else "Yes: an accepted registration matched by the FE geometry.")
    elif provisional:
        registration = "Not checked: FRF peak records are not compared."
    else:
        registration = {am.REFUSED: "No: none is confirmed for these files, and no accepted registration matches their geometry.",
                        am.FAILED: "No: the registration check could not be completed.",
                        am.NOT_CONFIRMED: "No: the registration you confirmed does not hold for the current data."}.get(
            analysis.registration_outcome, "No: the saved result holds none." if saved else
            "No: none is confirmed for these files, and no accepted registration matches their geometry.")
    if measured_mode is None:
        measured = ("Not in the saved file: check the source files and Analyze again." if saved
                    else "Not available for this result.")
    else:
        measured = f"Measured directions: {_directions(measured_mode)}."
    measured += (" FE nodes are matched to the points by the registration." if view is not None
                 else " Which FE node belongs to which point is unknown until a registration exists.")
    if view is not None:
        mac = f"Yes: computed for {len(view.pair_rows)} pair{'' if len(view.pair_rows) == 1 else 's'} (see below)."
    elif provisional:
        mac = "No: MAC needs fitted mode shapes; choose a fitted modal set if the file holds one."
    else:
        mac = "No: a registration is missing. " + SET_UP
    return tuple(zip(READY_QUESTIONS, (fitted, registration, measured, mac)))


def unavailable_reason(analysis, saved: bool) -> str:
    if analysis is None:
        return NO_RESULT
    if analysis.comparison is not None:
        return ""
    return REASONS.get(analysis.registration_outcome) or (SAVED_NO_REGISTRATION if saved else REASONS[am.REFUSED])


def measured_rows(mode) -> tuple:
    """Each measured point of a record as read: its coordinates and the DOFs the importer recorded."""
    measured = getattr(mode, "measured_dofs", None)
    mask = None if measured is None else np.asarray(measured, dtype=bool)
    coordinates = np.asarray(mode.coordinates, dtype=float)
    rows = []
    for index, node in enumerate(np.asarray(mode.node_ids)):
        dofs = "not recorded" if mask is None else " ".join(a for a, used in zip(AXES, mask[index]) if used) or "none"
        rows.append((str(node), *(f"{value:.5g}" for value in coordinates[index]), dofs))
    return tuple(rows)


def measured_summary(mode) -> str:
    measured = getattr(mode, "measured_dofs", None)
    points = len(mode.node_ids)
    if measured is None:
        return f"{points} points. The importer recorded no measured-DOF list."
    mask = np.asarray(measured, dtype=bool)
    per_axis = ", ".join(f"{axis}: {int(mask[:, column].sum())}" for column, axis in enumerate(AXES))
    return f"{points} points, {int(mask.sum())} measured DOFs ({per_axis})."


def layout_plot(mode) -> bytes:
    """The points in the two source axes of largest extent; no FE model and no value on them."""
    from services.modal_data_viewer import DisplayView, UNIT_TEXT, display_coordinates

    coordinates = np.asarray(mode.coordinates, dtype=float)
    finite = np.all(np.isfinite(coordinates), axis=1)
    x, y, x_label, y_label = display_coordinates(coordinates[finite], DisplayView("source"))
    figure = Figure(figsize=(5.0, 3.8), constrained_layout=True)
    FigureCanvasAgg(figure)
    axis = figure.add_subplot(111)
    axis.scatter(x, y, s=28, c="#2563eb", edgecolors="white", linewidths=0.6)
    axis.set_aspect("equal", adjustable="datalim")
    axis.set_title(f"{MEASURED_TITLE} ({int(finite.sum())})", fontsize=10, color="#3e4c59", loc="left")
    axis.set_xlabel(f"{x_label} ({UNIT_TEXT})", fontsize=8, color="#52606d")
    axis.set_ylabel(f"{y_label} ({UNIT_TEXT})", fontsize=8, color="#52606d")
    axis.tick_params(labelsize=8, colors="#52606d")
    axis.grid(True, color="#e4e7eb", linewidth=0.8)
    out = io.BytesIO()
    with sm._RENDER:
        figure.savefig(out, format="png", dpi=130)
    return out.getvalue()


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


# ------------------------------------------------------------------------------------------------ the exploratory trial

TRIAL_LABEL = tp.LABEL
TRIAL_TITLE = "Trial MAC under unconfirmed placements (research)"
TRIAL_NOTE = ("A research calculation, not a registration. The measured grid is placed on the FE plate in 40 fixed ways: 2 "
              "faces x 4 quarter turns x 5 positions (centred by assumption, and shifts of 5 FE units along X and Y). It "
              "assumes measured coordinates in metres and FE coordinates in millimetres, takes the nearest FE node of each "
              "point and uses the measured Z component at every point. No placement is selected or ranked. The values make "
              "no mode pair, change no status, are not saved with the result and are not used for material estimation.")
TRIAL_RUN, TRIAL_CANCEL = "Run trial MAC", "Cancel"
TRIAL_NEEDS_RESULT = "Analyze both files first."
TRIAL_NEEDS_SOURCE = ("Not available for a saved result: its files were not read in this session. Check source files on the "
                      "Analyze page, then Analyze again.")
TRIAL_NEEDS_FITTED = "Not available: the chosen set holds FRF peak records, not fitted modes."
TRIAL_RUNNING, TRIAL_CANCELLED = "Running the 40 trial placements...", "Cancelled. No trial value is shown."
TRIAL_STALE = "The files or the chosen set changed, so the trial values were removed."
TRIAL_MAPPING_TITLE = "Point mapping of every placement"
TRIAL_MAPPING_HEADERS = ("Placement", "FE face", "Quarter turns", "Shift X", "Shift Y", "Mapped points", "Different FE nodes",
                         "RMS distance", "Max distance", "Edge margin", "State")
TRIAL_FAMILY_TITLE = "Placements with numerically equal matrices, side by side"
TRIAL_FAMILY_NOTE = ("Centred placements whose matrices agree in every entry are drawn once. The letters follow the fixed "
                     "order of the placements; they are not a preference, and MAC does not decide which placement is physical.")
TRIAL_ONE_TITLE = "One placement"
TRIAL_SHAPE_NOTE = ("Measured Z at the points, the FE mode at the nearest nodes of this placement (one complex scale fitted "
                    "to the measurement) and their difference.")
FACE_TEXT = {"T": "largest Z (scan +Z = FE +Z)", "B": "smallest Z (scan +Z = FE -Z)"}


@dataclass(frozen=True)
class TrialOutcome:
    token: int
    run: Optional[tp.TrialRun] = None
    family_image: bytes = b""
    error: str = ""
    cancelled: bool = False


def trial_problem(analysis, inputs, saved: bool) -> str:
    """Why the trial cannot start, or ''. A saved result never qualifies: its data were not read and verified here."""
    if saved:
        return TRIAL_NEEDS_SOURCE
    if analysis is None or inputs is None:
        return TRIAL_NEEDS_RESULT
    if _provisional(analysis):
        return TRIAL_NEEDS_FITTED
    return ""


def trial_modes(inputs, analysis) -> tuple:
    """The elastic FE modes (the analysis' own rigid-body classification) and the chosen set's records, as read."""
    rigid = {int(number) for number in analysis.rigid_modes}
    fe = [mode for mode in inputs.fe.dataset.sorted_modes() if int(mode.number) not in rigid]
    return fe, list(inputs.experimental.sets[analysis.set_index].dataset.sorted_modes())


def run_trial(inputs, analysis, token: int, cancel_event) -> TrialOutcome:
    """The service on the data of this session; both files must be the files that were read, before and after."""
    try:
        am.confirm_sources(inputs, cancel_event)
        fe, experimental = trial_modes(inputs, analysis)
        run = tp.run_trials(fe, experimental, cancel_event)
        am.confirm_sources(inputs, cancel_event)
        image = trial_family_plot(run)
        if cancel_event.is_set():
            return TrialOutcome(token, cancelled=True)
        return TrialOutcome(token, run, image)
    except (am.StepCancelled, tp.TrialCancelled):
        return TrialOutcome(token, cancelled=True)
    except (am.StepFailed, tp.TrialUnavailable) as error:
        return TrialOutcome(token, error=str(error))
    except Exception as error:  # noqa: BLE001
        if cancel_event.is_set():
            return TrialOutcome(token, cancelled=True)
        return TrialOutcome(token, error=f"The trial could not be completed ({type(error).__name__}: {error}).")


def trial_summary(run) -> str:
    grid, usable = run.grid, len(run.usable)
    return (f"{len(run.point_ids)} measured points, grid {grid['counts'][0]} x {grid['counts'][1]}, pitch {grid['pitch']:.2f}, "
            f"turned {grid['theta_deg']:.2f} deg in the scan plane. {len(run.experimental_numbers)} EXP modes against "
            f"{len(run.fe_numbers)} elastic FE modes. {usable} of {len(run.trials)} placements mapped every point; "
            f"{len(run.trials) - usable} rejected. Distances in FE units.")


def trial_mapping_rows(run) -> tuple:
    return tuple((t.name, FACE_TEXT[t.face], str(t.turn), f"{t.shift[0]:+g}", f"{t.shift[1]:+g}", f"{t.valid_points} of {t.points}",
                  str(t.unique_nodes), f"{t.rms_distance:.3f}", f"{t.max_distance:.3f}", f"{t.edge_margin:.2f}",
                  "Mapped" if t.usable else f"Rejected: {t.rejected_because}") for t in run.trials)


def trial_matrix_headers(run) -> tuple:
    return ("EXP \\ FE",) + tuple(f"FE {n} ({f:.1f} Hz)" for n, f in zip(run.fe_numbers, run.fe_frequencies))


def trial_matrix_rows(run, trial) -> tuple:
    if trial.mac is None:
        return ()
    return tuple((f"EXP {n} ({f:.2f} Hz)", *("n/a" if not np.isfinite(v) else f"{v:.4f}" for v in row))
                 for n, f, row in zip(run.experimental_numbers, run.experimental_frequencies, trial.mac))


def trial_family_letter(index: int) -> str:
    return chr(ord("A") + index) if index < 26 else str(index + 1)


def trial_family_text(run) -> str:
    if not run.families:
        return "No centred placement mapped every point, so no matrix is drawn."
    lines = [f"Family {trial_family_letter(i)}: {', '.join(names)}" for i, names in enumerate(run.families)]
    if len(run.families) > 1:
        first = run.trial(run.families[0][0]).mac
        for i, names in enumerate(run.families[1:], 1):
            gap = float(np.nanmax(np.abs(run.trial(names[0]).mac - first)))
            lines.append(f"Largest difference of one entry between family A and family {trial_family_letter(i)}: {gap:.3f}")
    return "\n".join(lines)


def _heatmap(axis, run, mac, title: str) -> None:
    axis.imshow(mac, cmap="Blues", vmin=0.0, vmax=1.0, aspect="auto")
    axis.set_xticks(range(len(run.fe_numbers)), [f"FE {n}" for n in run.fe_numbers], fontsize=7, rotation=90)
    axis.set_yticks(range(len(run.experimental_numbers)), [f"EXP {n}" for n in run.experimental_numbers], fontsize=7)
    axis.tick_params(colors="#52606d", length=0)
    if mac.size <= 400:
        for (i, j), value in np.ndenumerate(mac):
            if np.isfinite(value):
                axis.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=5.5,
                          color="#ffffff" if value > 0.55 else "#1f2933")
    axis.set_title(title, fontsize=8.5, color="#3e4c59", loc="left")


def trial_family_plot(run) -> bytes:
    """One matrix per family, in the fixed order and on one scale; no family is marked."""
    if not run.families:
        return b""
    count = len(run.families)
    figure = Figure(figsize=(6.4 * min(count, 2), 4.6 * ((count + 1) // 2)), constrained_layout=True)
    FigureCanvasAgg(figure)
    for index, names in enumerate(run.families):
        axis = figure.add_subplot((count + 1) // 2, min(count, 2), index + 1)
        _heatmap(axis, run, run.trial(names[0]).mac, f"Family {trial_family_letter(index)}: {' = '.join(names)}")
    figure.suptitle(TRIAL_LABEL, fontsize=9, color="#9b1c1c")
    out = io.BytesIO()
    with sm._RENDER:
        figure.savefig(out, format="png", dpi=130)
    return out.getvalue()


def trial_shape_plot(run, trial, experimental_index: int, fe_index: int) -> bytes:
    """Measured Z, the FE mode at the mapped nodes and their difference for one placement; the MAC shown is the trial's."""
    if trial.mac is None:
        return b""
    measured, fe = run.experimental_z[:, experimental_index], np.asarray(trial.fe_at[:, fe_index], dtype=complex)
    phase = np.exp(-0.5j * np.angle(np.sum(measured ** 2)))  # the turn that makes the measured vector closest to real
    norm = float(np.vdot(fe, fe).real)
    scale = np.vdot(fe, measured) / norm if norm > 0.0 else 0.0
    measured_line, fe_line = np.real(measured * phase), np.real(scale * fe * phase)
    top = float(np.abs(measured_line).max()) or 1.0
    measured_line, fe_line = measured_line / top, fe_line / top
    figure = Figure(figsize=(9.6, 3.5), constrained_layout=True)
    FigureCanvasAgg(figure)
    exp_name = f"EXP {run.experimental_numbers[experimental_index]}"
    fe_name = f"FE {run.fe_numbers[fe_index]}"
    size = max(6.0, min(60.0, 9000.0 / len(measured_line)))
    drawn = None
    for column, (values, title) in enumerate(((measured_line, f"{exp_name}, measured Z"),
                                              (fe_line, f"{fe_name} at the mapped nodes"),
                                              (measured_line - fe_line, "Difference"))):
        axis = figure.add_subplot(1, 3, column + 1)
        drawn = axis.scatter(trial.placed[:, 0], trial.placed[:, 1], c=values, s=size, marker="s", cmap="RdBu_r",
                             vmin=-1.0, vmax=1.0, linewidths=0)
        axis.set_aspect("equal", adjustable="datalim")
        axis.set_title(title, fontsize=9, color="#3e4c59", loc="left")
        axis.set_xlabel("FE X", fontsize=8, color="#52606d")
        if column == 0:
            axis.set_ylabel("FE Y", fontsize=8, color="#52606d")
        axis.tick_params(labelsize=7, colors="#52606d")
    figure.colorbar(drawn, ax=figure.axes, shrink=0.85, label="Amplitude (largest measured = 1)")
    value = trial.mac[experimental_index, fe_index]
    figure.suptitle(f"{TRIAL_LABEL}   |   placement {trial.name}   |   trial MAC {exp_name} / {fe_name} = "
                    f"{'n/a' if not np.isfinite(value) else format(value, '.4f')}", fontsize=9, color="#9b1c1c")
    out = io.BytesIO()
    with sm._RENDER:
        figure.savefig(out, format="png", dpi=130)
    return out.getvalue()


__all__ = ["MAC_PLAIN", "READINESS_TITLE", "READY_QUESTIONS", "readiness_rows", "evidence_levels", "point_rows", "profile_lines", "profile_plot", "unavailable_reason",
           "TRIAL_LABEL", "TrialOutcome", "run_trial", "trial_family_plot", "trial_mapping_rows", "trial_matrix_rows",
           "trial_problem", "trial_shape_plot"]
