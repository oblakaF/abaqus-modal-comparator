"""Individual FE and experimental modes, viewed separately and independently of any physical registration.

The normal comparator correlates FE and experimental shapes only after a physical registration (an orientation and a
measured-point-to-FE-node mapping). When that registration is ambiguous or unavailable, the loaded data stay useful:

- every extracted Abaqus mode can be inspected on its own FE nodes and coordinates (out-of-plane component,
  magnitude or one displacement component);
- every imported experimental record can be inspected on its own measured points, with its source classification:
  a curve-fitted mode (dataset 55 / 2414), or an FRF peak-derived response snapshot (dataset 58), which is NOT a
  validated fitted mode shape;
- nothing here maps one dataset onto the other, chooses an orientation, overlays the two fields or computes a MAC.
  Frequency proximity rows (``services.new_odb_comparison``) are never mode pairs.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import io
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

FE = "FE"
EXPERIMENTAL = "EXPERIMENTAL"

FE_MODE = "FE_MODE"
FE_RIGID_BODY_MODE = "FE_RIGID_BODY_MODE"
FITTED_MODE = "FITTED_EXPERIMENTAL_MODE"
FRF_PEAK_SNAPSHOT = "FRF_PEAK_RESPONSE_SNAPSHOT"
UNCLASSIFIED = "UNCLASSIFIED_EXPERIMENTAL_RECORD"

FE_SOURCE_TEXT = "Abaqus ODB extraction (FE mode shape on its own FE nodes)"
FRF_SNAPSHOT_TEXT = "FRF peak-derived response snapshot — NOT a validated fitted mode shape"
FRF_PEAK_FREQUENCY_TEXT = "FRF resonance-peak candidate (dataset 58) — PROVISIONAL, not a validated fitted mode"
NOT_CORRELATED = ("FE and experimental views are separate: no physical registration is applied, no field is mapped "
                  "or overlaid and no MAC is computed.")

COMPONENTS = ("normal", "magnitude", "x", "y", "z")
COMPONENT_TEXT = {
    FE: {"normal": "Out-of-plane (normal to the best-fit plane)", "magnitude": "Magnitude |U|",
         "x": "U1", "y": "U2", "z": "U3"},
    EXPERIMENTAL: {"normal": "Out-of-plane (normal to the best-fit plane)", "magnitude": "Magnitude",
                   "x": "X (measurement axes)", "y": "Y (measurement axes)", "z": "Z (measurement axes)"},
}
# P-2: the comparator's own rigid-body criterion (quality_control: six-vector rigid-body subspace projection of the
# mode shape, residual fraction <= RIGID_SHAPE_RESIDUAL_THRESHOLD). No frequency threshold is used.
RIGID_RESIDUALS_KEY = "rigid_body_residual_fraction_by_mode"
RIGID_BODY_METHOD = "six-vector rigid-body subspace projection of the mode shape"
MINIMUM_SPATIAL_POINTS = 3
DISPLAY_GRID_THRESHOLD = 5000  # above this many nodes the field is averaged on a display grid
DISPLAY_GRID_CELLS = 220
# APP-DATA.6: points span no plane when the second singular value of the centred points is at most this fraction of
# the first (the rule of the APP-DATA.4/5 previews); their out-of-plane direction would be arbitrary.
COLLINEAR_TOLERANCE = 1.0e-6
NO_PLANE_REASON = ("the points lie on one line: no best-fit plane and no normal to it are defined, so no out-of-plane "
                   "view is drawn; magnitude and the X / Y / Z (U1 / U2 / U3) components can still be viewed")


def _new_figure(figsize) -> Figure:
    figure = Figure(figsize=figsize, constrained_layout=True)
    FigureCanvasAgg(figure)
    return figure


def experimental_classification(mode, dataset_metadata: Optional[Mapping[str, Any]] = None) -> tuple[str, str]:
    """(classification, source text) of one imported experimental record, from its import metadata."""

    metadata = dict(getattr(mode, "metadata", {}) or {})
    dataset_metadata = dict(dataset_metadata or {})
    dataset_type = metadata.get("dataset_type")
    source = str(metadata.get("mode_source") or "")
    if dataset_type == 58 or "FRF peak" in source:
        return FRF_PEAK_SNAPSHOT, FRF_SNAPSHOT_TEXT
    if dataset_type in (55, 2414) or "curve-fitted" in source:
        set_name = dataset_metadata.get("modal_set_name")
        record = f"dataset {dataset_type}" if dataset_type in (55, 2414) else "curve-fitted dataset"
        text = f"curve-fitted experimental mode ({record}" + (f", modal set {set_name})" if set_name else ")")
        return FITTED_MODE, text
    return UNCLASSIFIED, f"experimental record of unknown origin ({source or 'no source metadata'})"


def experimental_frequency_source(dataset) -> str:
    """How the experimental frequency list was obtained (for frequency-only views)."""

    metadata = dict(getattr(dataset, "metadata", {}) or {})
    source = str(metadata.get("mode_source") or "")
    if "dataset 58" in source or "FRF" in source:
        return FRF_PEAK_FREQUENCY_TEXT
    if metadata.get("modal_set_name"):
        return f"curve-fitted modal set (dataset 55: {metadata['modal_set_name']})"
    if source:
        return f"curve-fitted modes ({source})"
    return "experimental modes (source not recorded)"


def _finite_points(mode) -> np.ndarray:
    coordinates = np.asarray(mode.coordinates, dtype=float)
    vectors = np.asarray(mode.vectors)
    finite = np.all(np.isfinite(coordinates), axis=1)
    finite &= np.all(np.isfinite(vectors.real) & np.isfinite(np.imag(vectors)), axis=1)
    return finite


def measured_axes(mode) -> tuple[str, ...]:
    vectors = np.asarray(mode.vectors)
    present = np.any(np.abs(vectors[_finite_points(mode)]) > 0.0, axis=0) if len(vectors) else np.zeros(3, bool)
    return tuple(axis for axis, used in zip("xyz", present) if used)


def spatial_status(mode) -> tuple[bool, str]:
    """Whether a spatial view of this record can be drawn, and why not."""

    finite = _finite_points(mode)
    vectors = np.asarray(mode.vectors)[finite]
    responding = int(np.count_nonzero(np.any(np.abs(vectors) > 0.0, axis=1))) if len(vectors) else 0
    if responding < MINIMUM_SPATIAL_POINTS:
        return False, (f"only {responding} point(s) with coordinates and a non-zero response; a spatial view needs at "
                       f"least {MINIMUM_SPATIAL_POINTS} measured points (insufficient nodal channels).")
    return True, f"{responding} points with coordinates and a response"


@dataclass(frozen=True)
class ViewerMode:
    role: str
    number: int
    frequency_hz: float
    classification: str
    source_text: str
    point_count: int
    axes: tuple[str, ...]
    spatial_available: bool
    spatial_reason: str
    quality: Mapping[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        prefix = "FE mode" if self.role == FE else (
            "FRF peak" if self.classification == FRF_PEAK_SNAPSHOT else "Experimental mode")
        suffix = " — rigid-body (diagnostic)" if self.classification == FE_RIGID_BODY_MODE else ""
        return f"{prefix} {self.number} — {self.frequency_hz:.3f} Hz{suffix}"

    def to_dict(self) -> dict:
        return {"role": self.role, "number": self.number, "frequency_hz": self.frequency_hz,
                "classification": self.classification, "source": self.source_text, "points": self.point_count,
                "axes_with_data": list(self.axes), "spatial_view": "AVAILABLE" if self.spatial_available else
                "UNAVAILABLE", "spatial_reason": self.spatial_reason, "quality": dict(self.quality)}


def _quality(mode) -> dict:
    metadata = dict(getattr(mode, "metadata", {}) or {})
    out = {}
    if mode.damping_ratio is not None:
        out["damping_ratio"] = float(mode.damping_ratio)
    for key in ("mean_coherence", "phase_complexity_ratio", "frf_indicator", "reference_node", "reference_direction",
                "response_quantity", "record_classification"):
        if metadata.get(key) not in (None, ""):
            value = metadata[key]
            out[key] = float(value) if isinstance(value, (float, np.floating)) else value
    return out


def rigid_body_threshold() -> float:
    from quality_control import RIGID_SHAPE_RESIDUAL_THRESHOLD

    return float(RIGID_SHAPE_RESIDUAL_THRESHOLD)


def classify_rigid_body_fe_modes(dataset) -> dict[int, float]:
    """P-2: the rigid-body residual fraction of every FE mode, by the comparator's own quality-control criterion.

    Computed once (off the GUI thread, by the analysis worker) and recorded in the dataset metadata under the key the
    comparison's quality control uses; a recorded value is reused. Nothing is removed from the dataset."""
    from quality_control import _rigid_body_residual_fraction

    recorded = recorded_rigid_residuals(dataset)
    if recorded is not None and all(int(mode.number) in recorded for mode in dataset.modes):
        return recorded
    residuals = {int(mode.number): float(_rigid_body_residual_fraction(mode)) for mode in dataset.modes}
    dataset.metadata[RIGID_RESIDUALS_KEY] = residuals
    return residuals


def recorded_rigid_residuals(dataset) -> Optional[dict[int, float]]:
    """The recorded rigid-body residuals (never computed here, so the GUI thread never projects large models)."""
    recorded = (getattr(dataset, "metadata", None) or {}).get(RIGID_RESIDUALS_KEY)
    if not isinstance(recorded, Mapping):
        return None
    return {int(number): float(value) for number, value in recorded.items()}


def rigid_body_text(residual: float) -> str:
    return (f"rigid-body mode by {RIGID_BODY_METHOD} (residual {residual:.2g} <= {rigid_body_threshold():g}, the "
            "comparator's criterion); a diagnostic record, not an elastic mode")


def viewer_modes(dataset, role: str) -> list[ViewerMode]:
    if dataset is None:
        return []
    modes = []
    residuals = recorded_rigid_residuals(dataset) if role == FE else None
    threshold = rigid_body_threshold() if residuals else None
    for mode in dataset.sorted_modes():
        if role == FE:
            residual = None if residuals is None else residuals.get(int(mode.number))
            if residual is not None and residual <= threshold:
                classification, text = FE_RIGID_BODY_MODE, rigid_body_text(residual)
            else:
                classification, text = FE_MODE, FE_SOURCE_TEXT
        else:
            classification, text = experimental_classification(mode, dataset.metadata)
        available, reason = spatial_status(mode)
        modes.append(ViewerMode(role, int(mode.number), float(mode.frequency_hz), classification, text,
                                len(mode.node_ids), measured_axes(mode), available, reason,
                                _quality(mode) if role == EXPERIMENTAL else {}))
    return modes


def _phase_aligned(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=complex)
    flat = vectors.reshape(-1)
    finite = np.isfinite(flat.real) & np.isfinite(flat.imag)
    if np.any(finite):
        reference = flat[np.flatnonzero(finite)[np.argmax(np.abs(flat[finite]))]]
        if abs(reference) > 1.0e-30:
            vectors = vectors * np.exp(-1j * np.angle(reference))
    return vectors


def collinear_points(coordinates) -> bool:
    """Whether the points span no plane (fewer than three, or all on one line within COLLINEAR_TOLERANCE)."""
    points = np.asarray(coordinates, dtype=float)
    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) < 3:
        return True
    spread = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
    return bool(spread[0] <= 0.0 or spread[1] <= COLLINEAR_TOLERANCE * spread[0])


def out_of_plane_available(mode) -> bool:
    """Whether the points the out-of-plane component is computed on (finite coordinates and values) span a plane."""
    return not collinear_points(np.asarray(mode.coordinates, dtype=float)[_finite_points(mode)])


def _plane_basis(coordinates: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = coordinates.mean(axis=0)
    _, _, vt = np.linalg.svd(coordinates - center, full_matrices=False)
    if vt.shape[0] < 3:
        vt = np.vstack([vt, np.eye(3)[: 3 - vt.shape[0]]])
    return center, vt[:2], vt[-1]


def component_values(mode, component: str) -> np.ndarray:
    """A real field per point: the phase-aligned real part of the chosen component (magnitude: |v|)."""

    if component not in COMPONENTS:
        raise ValueError(f"unknown component {component!r}; choose one of {', '.join(COMPONENTS)}.")
    coordinates = np.asarray(mode.coordinates, dtype=float)
    vectors = np.asarray(mode.vectors)
    if component == "magnitude":
        return np.linalg.norm(np.abs(vectors), axis=1)
    aligned = _phase_aligned(vectors)
    if component == "normal":
        finite = _finite_points(mode)
        if collinear_points(coordinates[finite]):  # never an arbitrary normal
            raise ValueError(f"No out-of-plane component: {NO_PLANE_REASON}.")
        _, _, normal = _plane_basis(coordinates[finite])
        return np.real(aligned @ normal)
    return np.real(aligned[:, "xyz".index(component)])


def _binned(x: np.ndarray, y: np.ndarray, values: np.ndarray, cells: int):
    """Mean of the field per display cell (large FE models; every node contributes)."""

    span = max(float(np.ptp(x)), float(np.ptp(y)), 1.0e-30)
    nx = max(2, int(round(cells * float(np.ptp(x)) / span)))
    ny = max(2, int(round(cells * float(np.ptp(y)) / span)))
    total, xe, ye = np.histogram2d(x, y, bins=(nx, ny), weights=values)
    count, _, _ = np.histogram2d(x, y, bins=(xe, ye))
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(count > 0, total / count, np.nan)
    return mean.T, (xe[0], xe[-1], ye[0], ye[-1])


def render_mode(mode, role: str, component: str, output_path: Path, title: str, note: str = "") -> Path:
    """One mode on its own points only (no mapping, no overlay)."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    finite = _finite_points(mode)
    coordinates = np.asarray(mode.coordinates, dtype=float)[finite]
    values = component_values(mode, component)[finite]
    scale = float(np.nanmax(np.abs(values))) if len(values) else 0.0
    if scale > 0.0:
        values = values / scale
    center, plane, _ = _plane_basis(coordinates)
    projected = (coordinates - center) @ plane.T
    x, y = projected[:, 0], projected[:, 1]
    signed = component != "magnitude"
    limits = (-1.0, 1.0) if signed else (0.0, 1.0)
    colour_map = "coolwarm" if signed else "viridis"

    figure = _new_figure((6.2, 4.8))
    axis = figure.add_subplot(111)
    if len(values) > DISPLAY_GRID_THRESHOLD:
        image, extent = _binned(x, y, values, DISPLAY_GRID_CELLS)
        artist = axis.imshow(image, origin="lower", extent=extent, cmap=colour_map, vmin=limits[0], vmax=limits[1],
                             interpolation="nearest", aspect="equal")
        method = f"{len(values)} FE nodes, averaged per display cell"
    else:
        artist = None
        planar_points = len(np.unique(np.round(projected, 9), axis=0)) >= 3
        if planar_points and len(values) >= 3:
            try:
                artist = axis.tricontourf(x, y, values, levels=21, cmap=colour_map, vmin=limits[0], vmax=limits[1])
            except Exception:  # noqa: BLE001 - degenerate triangulation: fall back to points
                artist = None
        points = axis.scatter(x, y, c=values, cmap=colour_map, vmin=limits[0], vmax=limits[1], s=30,
                              edgecolors="black", linewidths=0.3, zorder=3)
        artist = artist or points
        method = f"{len(values)} points"
    figure.colorbar(artist, ax=axis, label="Normalised " + ("amplitude" if signed else "magnitude"))
    axis.set_title(title + (f"\n{note}" if note else ""), fontsize=9)
    axis.set_xlabel(f"In-plane principal coordinate 1\n{COMPONENT_TEXT[role][component]} · {method}", fontsize=8)
    axis.set_ylabel("In-plane principal coordinate 2", fontsize=8)
    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, alpha=0.25)
    figure.savefig(output_path, dpi=150)
    return output_path


def mode_by_number(dataset, number: int):
    for mode in dataset.sorted_modes():
        if int(mode.number) == int(number):
            return mode
    raise KeyError(f"mode {number} is not in {getattr(dataset, 'source_path', 'the dataset')}")


def render_viewer_mode(dataset, role: str, number: int, component: str, directory: Path) -> tuple[Path, ViewerMode]:
    mode = mode_by_number(dataset, number)
    entry = next(item for item in viewer_modes(dataset, role) if item.number == int(number))
    if not entry.spatial_available:
        raise ValueError(f"{entry.label()}: no spatial view — {entry.spatial_reason}")
    if component == "normal" and not out_of_plane_available(mode):
        raise ValueError(f"{entry.label()}: no out-of-plane view — {NO_PLANE_REASON}.")
    if role == FE:
        title, note = f"Abaqus FE mode {entry.number} — {entry.frequency_hz:.3f} Hz", ""
    elif entry.classification == FRF_PEAK_SNAPSHOT:
        title = f"FRF peak {entry.number} — {entry.frequency_hz:.3f} Hz (complex FRF, phase-aligned real part)"
        note = FRF_SNAPSHOT_TEXT
    else:
        title, note = f"Experimental mode {entry.number} — {entry.frequency_hz:.3f} Hz", entry.source_text
    stem = f"{'fe' if role == FE else 'exp'}_{entry.number:04d}_{component}"
    return render_mode(mode, role, component, Path(directory) / f"{stem}.png", title, note), entry


# ----------------------------------------------------------------------------- loaded data kept for viewing

ESTABLISHED = "ESTABLISHED"
AMBIGUOUS = "AMBIGUOUS"
NOT_ESTABLISHED = "NOT_ESTABLISHED"


class ExperimentalDataUnavailable(RuntimeError):
    """The experimental file gave no usable modal or FRF data; the FE data stay available for viewing."""


@dataclass
class LoadedModalData:
    """The datasets one analysis run actually loaded, kept for separate viewing whatever the comparison outcome."""

    abaqus: Any
    experimental: Any = None
    experimental_error: Optional[str] = None
    directory: Optional[Path] = None  # where views and the diagnostic output of this run are written
    registration: str = NOT_ESTABLISHED
    reason: str = ""
    frequency_diagnostic: Any = None
    abaqus_path: Optional[Path] = None  # the files this run read (a guided registration is bound to them)
    experimental_path: Optional[Path] = None

    def inventory(self) -> dict:
        return modal_inventory(self.abaqus, self.experimental, registration=self.registration, reason=self.reason,
                               experimental_error=self.experimental_error)


def attach_loaded_data(error: BaseException, loaded: Optional[LoadedModalData]) -> BaseException:
    """Keep the loaded datasets on a failure so the user can still inspect them (never a comparison result)."""

    if loaded is not None and getattr(error, "loaded_modal_data", None) is None:
        try:
            error.loaded_modal_data = loaded
        except AttributeError:
            pass
    return error


# ----------------------------------------------------------------------------- diagnostic output

def modal_inventory(abaqus, experimental, *, registration: str, reason: str = "",
                    experimental_error: Optional[str] = None) -> dict:
    """What each file contains, separately; registration state stated, never inferred from frequency or MAC."""

    fe_modes = [item.to_dict() for item in viewer_modes(abaqus, FE)]
    exp_modes = [item.to_dict() for item in viewer_modes(experimental, EXPERIMENTAL)]
    return {
        "schema": "modal-data-viewer/inventory/v1",
        "physical_registration": registration,
        "reason": reason,
        "correlation": NOT_CORRELATED if registration != ESTABLISHED else "see the gated comparison results",
        "mac": "NOT_COMPUTED" if registration != ESTABLISHED else "see the gated comparison results",
        "fe": {"source": None if abaqus is None else str(abaqus.source_path), "mode_count": len(fe_modes),
               "modes": fe_modes},
        "experimental": {
            "source": None if experimental is None else str(experimental.source_path),
            "frequency_source": None if experimental is None else experimental_frequency_source(experimental),
            "mode_count": len(exp_modes), "modes": exp_modes, "import_error": experimental_error,
            "frf": None if experimental is None else {
                key: experimental.metadata.get(key) for key in (
                    "frf_channel_count", "frf_response_node_count", "frf_frequency_start_hz", "frf_frequency_end_hz",
                    "frf_frequency_lines", "frf_quantity", "coherence_channel_count", "coherence_status",
                    "dataset_58_role") if experimental.metadata.get(key) is not None},
        },
    }


def inventory_csv(inventory: Mapping) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["dataset", "number", "frequency_hz", "classification", "source", "points", "spatial_view",
                     "mean_coherence", "phase_complexity_ratio"])
    for key in ("fe", "experimental"):
        for mode in inventory[key]["modes"]:
            quality = mode.get("quality") or {}
            writer.writerow([mode["role"], mode["number"], f"{mode['frequency_hz']:.6f}", mode["classification"],
                             mode["source"], mode["points"], mode["spatial_view"], quality.get("mean_coherence", ""),
                             quality.get("phase_complexity_ratio", "")])
    return out.getvalue()


def write_diagnostic_package(folder: Path, inventory: Mapping, frequency_diagnostic=None,
                             images: Sequence[Path] = ()) -> dict[str, Path]:
    """inventory JSON + CSV, the frequency-only diagnostic (when present) and the rendered views. Never an INP."""

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {"inventory": folder / "modal_data_inventory.json", "csv": folder / "modal_data_frequencies.csv"}
    paths["inventory"].write_text(json.dumps(inventory, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    paths["csv"].write_text(inventory_csv(inventory), encoding="utf-8")
    if frequency_diagnostic is not None:
        paths["frequency_only"] = folder / "frequency_only_diagnostic.json"
        paths["frequency_only"].write_text(json.dumps(frequency_diagnostic.to_dict(), indent=2, ensure_ascii=False),
                                           encoding="utf-8")
        paths["frequency_only_text"] = folder / "frequency_only_diagnostic.txt"
        paths["frequency_only_text"].write_text("\n".join(frequency_diagnostic.text_lines()) + "\n",
                                                encoding="utf-8")
    for image in images:
        image = Path(image)
        if image.exists():
            target = folder / image.name
            target.write_bytes(image.read_bytes())
            paths[image.stem] = target
    return paths
