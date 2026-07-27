from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from modal_core import ComparisonResult


def _new_figure(figsize) -> Figure:
    figure = Figure(figsize=figsize, constrained_layout=True)
    FigureCanvasAgg(figure)
    return figure


def _common_pair_data(result: ComparisonResult):
    if not result.pairs:
        raise ValueError("No verified pairs are available for AutoMAC or COMAC.")
    shape = result.pairs[0].abaqus_vector.shape
    common_mask = np.ones(shape, dtype=bool)
    for pair in result.pairs:
        if pair.abaqus_vector.shape != shape or pair.experimental_vector.shape != shape:
            raise ValueError("Verified pair vectors do not share a common measurement grid.")
        pair_mask = getattr(pair, "measured_dof_mask", np.ones(shape, dtype=bool))
        finite = (
            np.isfinite(pair.abaqus_vector.real)
            & np.isfinite(pair.abaqus_vector.imag)
            & np.isfinite(pair.experimental_vector.real)
            & np.isfinite(pair.experimental_vector.imag)
        )
        common_mask &= np.asarray(pair_mask, dtype=bool) & finite
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

    node_scores = np.nanmean(dof_scores, axis=1)
    coordinates = np.asarray(result.pairs[0].coordinates, dtype=float)
    return coordinates, np.clip(node_scores, 0.0, 1.0)


def _project_coordinates(coordinates: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    centered = coordinates - np.mean(coordinates, axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    projected = centered @ vt[:2].T
    return projected[:, 0], projected[:, 1]


def render_automac_comac(result: ComparisonResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    abaqus_automac, experimental_automac = automac_matrices(result)
    coordinates, comac = comac_by_node(result)
    labels = [f"A{pair.abaqus_mode}" for pair in result.pairs]
    experimental_labels = [f"E{pair.experimental_mode}" for pair in result.pairs]

    figure = _new_figure((12.0, 4.3))
    axes = [figure.add_subplot(1, 3, index) for index in (1, 2, 3)]
    for axis, matrix, xlabels, title in (
        (axes[0], abaqus_automac, labels, "Abaqus AutoMAC"),
        (axes[1], experimental_automac, experimental_labels, "Experimental AutoMAC"),
    ):
        image = axis.imshow(matrix, vmin=0.0, vmax=1.0, aspect="auto")
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
    scatter = axes[2].scatter(x, y, c=comac, vmin=0.0, vmax=1.0, s=42)
    axes[2].set_title("COMAC by measurement point")
    axes[2].set_xlabel("Principal coordinate 1")
    axes[2].set_ylabel("Principal coordinate 2")
    axes[2].set_aspect("equal", adjustable="box")
    axes[2].grid(True, alpha=0.2)
    figure.colorbar(scatter, ax=axes[2], fraction=0.046, label="COMAC")
    figure.savefig(output_path, dpi=170)
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
