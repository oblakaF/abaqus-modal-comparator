from __future__ import annotations

import warnings
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from modal_core import ComparisonResult


def _new_figure(figsize) -> Figure:
    figure = Figure(figsize=figsize, constrained_layout=True)
    FigureCanvasAgg(figure)
    return figure


_GRID_MISMATCH_MESSAGE = (
    "AutoMAC/COMAC unavailable: verified pairs use different measurement grids."
)


def _verified_pairs_share_one_measurement_grid(result: ComparisonResult) -> None:
    """Raise if any two accepted pairs cannot be combined by row position.

    advanced_metrics.py combines every accepted pair's already row-filtered
    abaqus_vector/experimental_vector/measured_dof_mask into one AutoMAC/COMAC
    Gram-matrix computation purely by array position. That is only valid when
    every pair kept the exact same node IDs in the exact same order -- which
    is not guaranteed now that each pair uses its own experimental mode's own
    measured-DOF mask (ROADMAP Stage 2 #3) and can therefore keep a different
    subset of rows. Positionally combining mismatched grids would silently
    correlate the wrong physical points, so this refuses instead of guessing;
    genuinely realigning differently ordered/subsetted grids is left as a
    documented future task rather than attempted here.
    """
    reference_pair = result.pairs[0]
    reference_node_ids = getattr(reference_pair, "node_ids", None)
    shape = reference_pair.abaqus_vector.shape
    if reference_node_ids is None or np.asarray(reference_node_ids).shape[:1] != shape[:1]:
        raise ValueError(_GRID_MISMATCH_MESSAGE)
    reference_node_ids = np.asarray(reference_node_ids)

    for pair in result.pairs:
        pair_node_ids = getattr(pair, "node_ids", None)
        pair_mask = getattr(pair, "measured_dof_mask", None)
        if (
            pair.abaqus_vector.shape != shape
            or pair.experimental_vector.shape != shape
            or pair_mask is None
            or np.asarray(pair_mask, dtype=bool).shape != shape
            or pair_node_ids is None
            or np.asarray(pair_node_ids).shape != reference_node_ids.shape
            or not np.array_equal(np.asarray(pair_node_ids), reference_node_ids)
        ):
            raise ValueError(_GRID_MISMATCH_MESSAGE)


def _common_pair_data(result: ComparisonResult):
    if not result.pairs:
        raise ValueError("No verified pairs are available for AutoMAC or COMAC.")
    _verified_pairs_share_one_measurement_grid(result)

    shape = result.pairs[0].abaqus_vector.shape
    common_mask = np.ones(shape, dtype=bool)
    for pair in result.pairs:
        finite = (
            np.isfinite(pair.abaqus_vector.real)
            & np.isfinite(pair.abaqus_vector.imag)
            & np.isfinite(pair.experimental_vector.real)
            & np.isfinite(pair.experimental_vector.imag)
        )
        common_mask &= np.asarray(pair.measured_dof_mask, dtype=bool) & finite
    if not np.any(common_mask):
        raise ValueError("No common measured degrees of freedom exist across verified pairs.")
    abaqus = np.column_stack(
        [np.asarray(pair.abaqus_vector, dtype=complex)[common_mask] for pair in result.pairs]
    )
    experiment = np.column_stack(
        [np.asarray(pair.experimental_vector, dtype=complex)[common_mask] for pair in result.pairs]
    )
    return abaqus, experiment, common_mask


def mac_matrix_from_columns(matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=complex)
    gram = values.conj().T @ values
    diagonal = np.real(np.diag(gram))
    denominator = np.outer(diagonal, diagonal)
    output = np.zeros_like(denominator, dtype=float)
    valid = denominator > 1.0e-30
    output[valid] = (np.abs(gram[valid]) ** 2 / denominator[valid]).real
    return np.clip(output, 0.0, 1.0)


def automac_matrices(result: ComparisonResult) -> Tuple[np.ndarray, np.ndarray]:
    abaqus, experiment, _ = _common_pair_data(result)
    return mac_matrix_from_columns(abaqus), mac_matrix_from_columns(experiment)


def comac_by_node(result: ComparisonResult) -> Tuple[np.ndarray, np.ndarray]:
    abaqus, experiment, common_mask = _common_pair_data(result)
    shape = result.pairs[0].abaqus_vector.shape
    dof_scores = np.full(shape, np.nan, dtype=float)

    row = 0
    for node in range(shape[0]):
        for component in range(shape[1]):
            if not common_mask[node, component]:
                continue
            a = abaqus[row, :]
            e = experiment[row, :]
            numerator = abs(np.vdot(a, e)) ** 2
            denominator = float(np.vdot(a, a).real * np.vdot(e, e).real)
            dof_scores[node, component] = (
                float(numerator / denominator) if denominator > 1.0e-30 else np.nan
            )
            row += 1

    with warnings.catch_warnings():
        # A node with no measured DOF at all yields an all-NaN row here; the
        # resulting NaN node score is correct, only numpy's warning is unwanted.
        warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
        node_scores = np.nanmean(dof_scores, axis=1)
    coordinates = np.asarray(result.pairs[0].coordinates, dtype=float)
    return coordinates, np.clip(node_scores, 0.0, 1.0)


def _project_coordinates(coordinates: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    centered = coordinates - np.mean(coordinates, axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    projected = centered @ vt[:2].T
    return projected[:, 0], projected[:, 1]


def _draw_matrix(axis, figure, matrix, labels, title: str) -> None:
    image = axis.imshow(matrix, vmin=0.0, vmax=1.0, aspect="equal")
    axis.set_xticks(range(len(labels)))
    axis.set_xticklabels(labels, rotation=45, ha="right")
    axis.set_yticks(range(len(labels)))
    axis.set_yticklabels(labels)
    axis.set_title(title)
    axis.set_xlabel("Mode")
    axis.set_ylabel("Mode")
    if matrix.size <= 400:
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                value = matrix[row, column]
                text_color = "black" if value >= 0.55 else "white"
                axis.text(
                    column,
                    row,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color=text_color,
                )
    figure.colorbar(image, ax=axis, fraction=0.046, label="MAC")


def render_abaqus_automac(result: ComparisonResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    abaqus_automac, _ = automac_matrices(result)
    labels = [f"A{pair.abaqus_mode}" for pair in result.pairs]
    figure = _new_figure((8.4, 7.2))
    axis = figure.add_subplot(111)
    _draw_matrix(axis, figure, abaqus_automac, labels, "Abaqus AutoMAC")
    figure.savefig(output_path, dpi=190)
    return output_path


def render_experimental_automac(result: ComparisonResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _, experimental_automac = automac_matrices(result)
    labels = [f"E{pair.experimental_mode}" for pair in result.pairs]
    figure = _new_figure((8.4, 7.2))
    axis = figure.add_subplot(111)
    _draw_matrix(axis, figure, experimental_automac, labels, "Experimental AutoMAC")
    figure.savefig(output_path, dpi=190)
    return output_path


def render_comac_map(result: ComparisonResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coordinates, comac = comac_by_node(result)
    x, y = _project_coordinates(coordinates)
    figure = _new_figure((8.8, 7.0))
    axis = figure.add_subplot(111)
    scatter = axis.scatter(
        x,
        y,
        c=comac,
        vmin=0.0,
        vmax=1.0,
        s=105,
        edgecolors="black",
        linewidths=0.25,
    )
    axis.set_title("COMAC by measurement point")
    axis.set_xlabel("Principal coordinate 1")
    axis.set_ylabel("Principal coordinate 2")
    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, alpha=0.2)
    figure.colorbar(scatter, ax=axis, fraction=0.046, label="COMAC")
    figure.savefig(output_path, dpi=190)
    return output_path


def render_automac_comac(result: ComparisonResult, output_path: Path) -> Path:
    """Keep the combined figure for reports while the GUI uses separate large panels."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    abaqus_automac, experimental_automac = automac_matrices(result)
    coordinates, comac = comac_by_node(result)
    labels = [f"A{pair.abaqus_mode}" for pair in result.pairs]
    experimental_labels = [f"E{pair.experimental_mode}" for pair in result.pairs]

    figure = _new_figure((13.5, 4.8))
    axes = [figure.add_subplot(1, 3, index) for index in (1, 2, 3)]
    for axis, matrix, xlabels, title in (
        (axes[0], abaqus_automac, labels, "Abaqus AutoMAC"),
        (axes[1], experimental_automac, experimental_labels, "Experimental AutoMAC"),
    ):
        image = axis.imshow(matrix, vmin=0.0, vmax=1.0, aspect="equal")
        axis.set_xticks(range(len(xlabels)))
        axis.set_xticklabels(xlabels, rotation=45, ha="right")
        axis.set_yticks(range(len(xlabels)))
        axis.set_yticklabels(xlabels)
        axis.set_title(title)
        if matrix.size <= 225:
            for row in range(matrix.shape[0]):
                for column in range(matrix.shape[1]):
                    axis.text(column, row, f"{matrix[row, column]:.2f}", ha="center", va="center", fontsize=7)
        figure.colorbar(image, ax=axis, fraction=0.046)

    x, y = _project_coordinates(coordinates)
    scatter = axes[2].scatter(x, y, c=comac, vmin=0.0, vmax=1.0, s=52)
    axes[2].set_title("COMAC by measurement point")
    axes[2].set_xlabel("Principal coordinate 1")
    axes[2].set_ylabel("Principal coordinate 2")
    axes[2].set_aspect("equal", adjustable="box")
    axes[2].grid(True, alpha=0.2)
    figure.colorbar(scatter, ax=axes[2], fraction=0.046, label="COMAC")
    figure.savefig(output_path, dpi=180)
    return output_path


def advanced_metric_summary(result: ComparisonResult) -> Dict[str, float]:
    abaqus_automac, experimental_automac = automac_matrices(result)
    _, comac = comac_by_node(result)

    def maximum_off_diagonal(matrix: np.ndarray) -> float:
        if matrix.shape[0] <= 1:
            return 0.0
        copy = matrix.copy()
        np.fill_diagonal(copy, np.nan)
        return float(np.nanmax(copy))

    return {
        "abaqus_automac_max_off_diagonal": maximum_off_diagonal(abaqus_automac),
        "experimental_automac_max_off_diagonal": maximum_off_diagonal(experimental_automac),
        "mean_comac": float(np.nanmean(comac)),
        "minimum_comac": float(np.nanmin(comac)),
    }
