from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import reporting
from modal_core import ComparisonResult, ModePairResult


_INSTALLED = False


def _new_figure(figsize) -> Figure:
    figure = Figure(figsize=figsize, constrained_layout=True)
    FigureCanvasAgg(figure)
    return figure


def _plane_projection(coordinates: np.ndarray) -> Tuple[np.ndarray, np.ndarray, bool]:
    coordinates = np.asarray(coordinates, dtype=float)
    center = np.mean(coordinates, axis=0)
    centered = coordinates - center
    _, singular_values, vt = np.linalg.svd(centered, full_matrices=False)
    projected = centered @ vt[:2].T
    planarity_ratio = (
        float(singular_values[2] / singular_values[0])
        if len(singular_values) >= 3 and singular_values[0] > 1.0e-30
        else 0.0
    )
    return projected[:, 0], projected[:, 1], planarity_ratio <= 0.05


def _modal_scalar(coordinates: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=complex)
    flattened = vectors.reshape(-1)
    finite = np.isfinite(flattened.real) & np.isfinite(flattened.imag)
    if not np.any(finite):
        return np.zeros(len(vectors), dtype=float)
    reference = flattened[np.flatnonzero(finite)[np.argmax(np.abs(flattened[finite]))]]
    if abs(reference) > 1.0e-30:
        vectors = vectors * np.exp(-1j * np.angle(reference))

    _, _, vt = np.linalg.svd(
        np.asarray(coordinates, dtype=float) - np.mean(coordinates, axis=0),
        full_matrices=False,
    )
    normal = vt[-1]
    component = np.real(vectors @ normal)
    if np.nanmax(np.abs(component)) <= 1.0e-12:
        component = np.real(vectors[:, int(np.argmax(np.linalg.norm(vectors, axis=0)))])
    maximum = float(np.nanmax(np.abs(component))) if len(component) else 0.0
    return component / maximum if maximum > 0.0 else component


def render_mode_shape(
    coordinates: np.ndarray,
    vectors: np.ndarray,
    title: str,
    output_path: Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coordinates = np.asarray(coordinates, dtype=float)
    scalar = _modal_scalar(coordinates, vectors)
    x, y, planar = _plane_projection(coordinates)

    figure = _new_figure((6.0, 4.6))
    axis = figure.add_subplot(111)
    plotted = False
    if planar and len(x) >= 3 and len(np.unique(np.column_stack((x, y)), axis=0)) >= 3:
        try:
            contour = axis.tricontourf(x, y, scalar, levels=21)
            axis.tricontour(x, y, scalar, levels=[0.0], linewidths=1.2)
            figure.colorbar(contour, ax=axis, label="Normalized modal amplitude")
            plotted = True
        except Exception:
            plotted = False
    if not plotted:
        scatter = axis.scatter(x, y, c=scalar, s=26)
        figure.colorbar(scatter, ax=axis, label="Normalized modal amplitude")
        if not planar:
            axis.text(
                0.02,
                0.02,
                "Non-planar geometry: scatter projection used",
                transform=axis.transAxes,
                fontsize=8,
            )
    axis.set_title(title)
    axis.set_xlabel("Principal coordinate 1")
    axis.set_ylabel("Principal coordinate 2")
    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, alpha=0.25)
    figure.savefig(output_path, dpi=170)
    return output_path


def _pair_measured_values(pair: ModePairResult) -> Tuple[np.ndarray, np.ndarray]:
    abaqus = np.asarray(pair.abaqus_vector, dtype=complex)
    experiment = np.asarray(pair.experimental_vector, dtype=complex)
    mask = getattr(pair, "measured_dof_mask", None)
    if mask is None:
        mask = (
            np.isfinite(abaqus.real)
            & np.isfinite(abaqus.imag)
            & np.isfinite(experiment.real)
            & np.isfinite(experiment.imag)
        )
    else:
        mask = np.asarray(mask, dtype=bool)
    a = abaqus[mask]
    e = experiment[mask]
    finite = np.isfinite(a.real) & np.isfinite(a.imag) & np.isfinite(e.real) & np.isfinite(e.imag)
    a, e = a[finite], e[finite]
    if len(a):
        reference = e[int(np.argmax(np.abs(e)))]
        if abs(reference) > 1.0e-30:
            phase = np.exp(-1j * np.angle(reference))
            a, e = a * phase, e * phase
    return np.real(a), np.real(e)


def render_overlay(pair: ModePairResult, output_path: Path) -> Path:
    """Correlation plot using one shared normalized amplitude scale."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    abaqus, experiment = _pair_measured_values(pair)
    scale = max(
        float(np.max(np.abs(abaqus))) if len(abaqus) else 0.0,
        float(np.max(np.abs(experiment))) if len(experiment) else 0.0,
        1.0e-30,
    )
    abaqus = abaqus / scale
    experiment = experiment / scale

    figure = _new_figure((6.0, 4.6))
    axis = figure.add_subplot(111)
    axis.scatter(experiment, abaqus, s=25, alpha=0.75)
    limits = (-1.05, 1.05)
    axis.plot(limits, limits, linestyle="--", linewidth=1.1, label="45° agreement")
    axis.set_xlim(limits)
    axis.set_ylim(limits)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Experimental normalized amplitude")
    axis.set_ylabel("Abaqus normalized amplitude")
    mac_text = "unavailable" if pair.mac is None else f"{pair.mac:.3f}"
    axis.set_title(
        f"Mode A{pair.abaqus_mode} / E{pair.experimental_mode} correlation\nMAC={mac_text}"
    )
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure.savefig(output_path, dpi=170)
    return output_path


def render_pair_images(pair: ModePairResult, output_directory: Path) -> Dict[str, Path]:
    output_directory = Path(output_directory)
    stem = f"abaqus_{pair.abaqus_mode}_experiment_{pair.experimental_mode}"
    return {
        "abaqus": render_mode_shape(
            pair.coordinates,
            pair.abaqus_vector,
            f"Abaqus mode {pair.abaqus_mode} — {pair.abaqus_frequency_hz:.3f} Hz",
            output_directory / f"{stem}_abaqus.png",
        ),
        "experimental": render_mode_shape(
            pair.coordinates,
            pair.experimental_vector,
            f"Experimental mode {pair.experimental_mode} — {pair.experimental_frequency_hz:.3f} Hz",
            output_directory / f"{stem}_experimental.png",
        ),
        "overlay": render_overlay(pair, output_directory / f"{stem}_overlay.png"),
    }


def render_mac_matrix(result: ComparisonResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    matrix = np.asarray(result.mac_matrix, dtype=float)
    figure = _new_figure((8.0, 6.2))
    axis = figure.add_subplot(111)
    image = axis.imshow(matrix, vmin=0.0, vmax=1.0, aspect="auto")
    figure.colorbar(image, ax=axis, label="MAC")
    axis.set_xticks(range(len(result.experimental_mode_numbers)))
    axis.set_xticklabels(result.experimental_mode_numbers)
    axis.set_yticks(range(len(result.abaqus_mode_numbers)))
    axis.set_yticklabels(result.abaqus_mode_numbers)
    axis.set_xlabel("Experimental mode")
    axis.set_ylabel("Abaqus mode")
    axis.set_title("Modal Assurance Criterion matrix (measured DOFs only)")
    if matrix.size <= 400:
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                value = matrix[row, column]
                if np.isfinite(value):
                    axis.text(column, row, f"{value:.2f}", ha="center", va="center", fontsize=8)
    figure.savefig(output_path, dpi=170)
    return output_path


def render_frequency_comparison(result: ComparisonResult, output_path: Path) -> Path:
    """Frequency regression with 45-degree line and stiffness-direction diagnostic."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    experimental = np.asarray([pair.experimental_frequency_hz for pair in result.pairs], dtype=float)
    abaqus = np.asarray([pair.abaqus_frequency_hz for pair in result.pairs], dtype=float)

    figure = _new_figure((8.0, 5.6))
    axis = figure.add_subplot(111)
    if len(experimental):
        axis.scatter(experimental, abaqus, s=48, label="Matched modes")
        maximum = max(float(np.max(experimental)), float(np.max(abaqus))) * 1.05
        axis.plot([0.0, maximum], [0.0, maximum], linestyle="--", label="Perfect agreement")
        denominator = float(np.dot(experimental, experimental))
        slope = float(np.dot(experimental, abaqus) / denominator) if denominator > 0.0 else float("nan")
        predicted = slope * experimental
        residual = float(np.sum((abaqus - predicted) ** 2))
        total = float(np.sum((abaqus - np.mean(abaqus)) ** 2))
        r_squared = 1.0 - residual / total if total > 1.0e-30 else 1.0
        axis.plot([0.0, maximum], [0.0, slope * maximum], label=f"Fit: Abaqus={slope:.4f}·Experiment")
        for pair in result.pairs:
            axis.annotate(
                f"A{pair.abaqus_mode}/E{pair.experimental_mode}",
                (pair.experimental_frequency_hz, pair.abaqus_frequency_hz),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
            )
        axis.text(
            0.02,
            0.96,
            f"R²={r_squared:.4f}\nSlope {slope:.4f}: "
            + ("model generally higher/stiffer" if slope > 1.0 else "model generally lower/softer"),
            transform=axis.transAxes,
            va="top",
        )
        axis.set_xlim(0.0, maximum)
        axis.set_ylim(0.0, maximum)
    else:
        axis.text(0.5, 0.5, "No accepted mode pairs", ha="center", va="center", transform=axis.transAxes)
    axis.set_xlabel("Experimental frequency, Hz")
    axis.set_ylabel("Abaqus frequency, Hz")
    axis.set_title("Natural-frequency regression")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best")
    figure.savefig(output_path, dpi=170)
    return output_path


def install_reporting_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    reporting.render_mode_shape = render_mode_shape
    reporting.render_overlay = render_overlay
    reporting.render_pair_images = render_pair_images
    reporting.render_mac_matrix = render_mac_matrix
    reporting.render_frequency_comparison = render_frequency_comparison
    # The signed-frequency-error summary rows and "Mode Comparison" column widths
    # are written once, last, by final_reporting_review.install_final_reporting_review
    # after every other report extension has run.
    _INSTALLED = True
