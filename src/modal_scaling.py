from __future__ import annotations

from typing import Tuple

import numpy as np

from modal_core import ModePairResult


def measured_pair_values(pair: ModePairResult) -> Tuple[np.ndarray, np.ndarray]:
    """Return finite measured Abaqus and experimental DOFs as flat complex vectors."""
    abaqus = np.asarray(pair.abaqus_vector, dtype=complex)
    experiment = np.asarray(pair.experimental_vector, dtype=complex)
    mask = getattr(pair, "measured_dof_mask", None)
    if mask is None:
        mask = np.ones(abaqus.shape, dtype=bool)
    else:
        mask = np.asarray(mask, dtype=bool)
    if mask.shape != abaqus.shape or experiment.shape != abaqus.shape:
        raise ValueError("Pair vectors and measured-DOF mask must have identical shapes.")

    finite = (
        np.isfinite(abaqus.real)
        & np.isfinite(abaqus.imag)
        & np.isfinite(experiment.real)
        & np.isfinite(experiment.imag)
    )
    mask &= finite
    return abaqus[mask], experiment[mask]


def least_squares_complex_scale(
    source: np.ndarray,
    target: np.ndarray,
) -> Tuple[np.ndarray, complex]:
    """Scale and phase-align source to target in a complex least-squares sense."""
    source = np.asarray(source, dtype=complex).reshape(-1)
    target = np.asarray(target, dtype=complex).reshape(-1)
    if source.shape != target.shape:
        raise ValueError("Source and target modal vectors must have equal lengths.")
    denominator = np.vdot(source, source)
    if abs(denominator) <= 1.0e-30:
        return source.copy(), complex(1.0)
    coefficient = np.vdot(source, target) / denominator
    return source * coefficient, complex(coefficient)


def optimal_real_phase(vector: np.ndarray) -> complex:
    """Return a unit phase that makes a complex mode as real as possible."""
    values = np.asarray(vector, dtype=complex).reshape(-1)
    if not len(values):
        return complex(1.0)
    second_moment = np.sum(values * values)
    if abs(second_moment) > 1.0e-30:
        return complex(np.exp(-0.5j * np.angle(second_moment)))
    reference = values[int(np.argmax(np.abs(values)))]
    if abs(reference) <= 1.0e-30:
        return complex(1.0)
    return complex(np.exp(-1j * np.angle(reference)))


def correlation_plot_values(pair: ModePairResult) -> Tuple[np.ndarray, np.ndarray, complex]:
    """Return comparably scaled real amplitudes for the modal correlation plot.

    Eigenvectors and FRF-derived shapes have arbitrary independent amplitudes. Abaqus is
    therefore fitted to the experimental vector by one complex least-squares coefficient
    before both vectors are rotated to their most-real representation and normalized.
    """
    abaqus, experiment = measured_pair_values(pair)
    fitted_abaqus, coefficient = least_squares_complex_scale(abaqus, experiment)
    phase = optimal_real_phase(experiment)
    fitted_real = np.real(fitted_abaqus * phase)
    experiment_real = np.real(experiment * phase)
    scale = max(
        float(np.max(np.abs(fitted_real))) if len(fitted_real) else 0.0,
        float(np.max(np.abs(experiment_real))) if len(experiment_real) else 0.0,
        1.0e-30,
    )
    return fitted_real / scale, experiment_real / scale, coefficient


def unit_norm_aligned_columns(
    abaqus: np.ndarray,
    experiment: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Normalize a modal pair and phase-align Abaqus to experiment for COMAC."""
    abaqus = np.asarray(abaqus, dtype=complex).reshape(-1)
    experiment = np.asarray(experiment, dtype=complex).reshape(-1)
    if abaqus.shape != experiment.shape:
        raise ValueError("Abaqus and experimental modal columns must have equal lengths.")
    norm_a = float(np.sqrt(np.vdot(abaqus, abaqus).real))
    norm_e = float(np.sqrt(np.vdot(experiment, experiment).real))
    if norm_a <= 1.0e-30 or norm_e <= 1.0e-30:
        return abaqus, experiment
    abaqus = abaqus / norm_a
    experiment = experiment / norm_e
    correlation = np.vdot(abaqus, experiment)
    if abs(correlation) > 1.0e-30:
        abaqus = abaqus * (correlation / abs(correlation))
    return abaqus, experiment
