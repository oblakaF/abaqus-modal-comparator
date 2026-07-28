from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

import universal_reader
from modal_core import ModeShape, modal_assurance_criterion


_INSTALLED = False
_ALGORITHM_VERSION = "local-svd-v1"


@dataclass
class _FrfBlock:
    frequency: np.ndarray
    matrix: np.ndarray
    row_keys: List[Tuple[int, int]]
    node_numbers: np.ndarray
    coordinates: np.ndarray
    measured_mask: np.ndarray
    mean_coherence: np.ndarray
    coherence_status: str
    reference_count: int


def _close_target_clusters(
    target_frequencies: Optional[Sequence[float]],
    absolute_gap_hz: float = 3.5,
    relative_gap: float = 0.035,
) -> List[List[float]]:
    values = sorted(
        {
            float(value)
            for value in (target_frequencies or [])
            if np.isfinite(value) and float(value) > 0.0
        }
    )
    if len(values) < 2:
        return []

    clusters: List[List[float]] = [[values[0]]]
    for value in values[1:]:
        previous = clusters[-1][-1]
        threshold = max(absolute_gap_hz, relative_gap * 0.5 * (previous + value))
        if value - previous <= threshold:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [cluster for cluster in clusters if len(cluster) > 1]


def _build_frf_block(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
) -> _FrfBlock:
    frf_group = universal_reader._select_frf_group(datasets, geometry)
    if not frf_group:
        raise ValueError("No usable transfer-function group is available for close-mode separation.")

    frequency = universal_reader._as_array(frf_group[0].get("x"), dtype=float)
    if len(frequency) < 5:
        raise ValueError("The selected FRF group contains too few frequency lines.")

    dof_data: Dict[Tuple[int, int], np.ndarray] = {}
    references = set()
    for dataset in frf_group:
        x = universal_reader._as_array(dataset.get("x"), dtype=float)
        data = universal_reader._as_array(dataset.get("data"), dtype=complex)
        if len(x) != len(frequency) or len(data) != len(frequency):
            continue
        if not np.allclose(x, frequency, rtol=1.0e-8, atol=1.0e-10):
            continue
        try:
            node = int(np.asarray(dataset.get("rsp_node")).reshape(-1)[0])
            direction = int(np.asarray(dataset.get("rsp_dir")).reshape(-1)[0])
            reference_node = int(np.asarray(dataset.get("ref_node", 0)).reshape(-1)[0])
            reference_direction = int(np.asarray(dataset.get("ref_dir", 0)).reshape(-1)[0])
        except (TypeError, ValueError, IndexError):
            continue
        if node not in geometry or abs(direction) not in (1, 2, 3):
            continue
        dof_data[(node, direction)] = data
        references.add((reference_node, reference_direction))

    if not dof_data:
        raise ValueError("No compatible complex FRF channels are available for SVD.")

    row_keys = sorted(dof_data)
    matrix = np.vstack([dof_data[key] for key in row_keys])
    node_numbers = np.asarray(sorted({node for node, _ in row_keys}), dtype=int)
    node_index = {int(node): index for index, node in enumerate(node_numbers)}
    coordinates = universal_reader._coordinates_for_nodes(node_numbers, geometry)
    measured_mask = np.zeros((len(node_numbers), 3), dtype=bool)
    for node, signed_direction in row_keys:
        measured_mask[node_index[int(node)], abs(int(signed_direction)) - 1] = True

    reference_node, reference_direction = next(iter(references))
    try:
        coherence_lookup = universal_reader._coherence_by_dof(
            datasets, frequency, reference_node, reference_direction
        )
        coherence_rows = [coherence_lookup[key] for key in row_keys if key in coherence_lookup]
        if coherence_rows:
            mean_coherence = np.mean(np.vstack(coherence_rows), axis=0)
            coherence_status = "computed"
        else:
            # No dataset-58 coherence channel was exported for this reference: there is
            # no basis to distrust the FRF data, so it is weighted at full confidence.
            mean_coherence = np.ones_like(frequency, dtype=float)
            coherence_status = "unavailable"
    except (TypeError, ValueError, IndexError, KeyError) as error:
        # The coherence channel exists but could not be parsed (malformed pyuff scalar
        # data). Unlike the "unavailable" case above, real data was withheld here, so
        # default to the least-trusting weight rather than silently assuming perfect
        # coherence, and surface the failure to the user via close_mode_separation.
        mean_coherence = np.zeros_like(frequency, dtype=float)
        coherence_status = f"error: {error}"

    return _FrfBlock(
        frequency=frequency,
        matrix=matrix,
        row_keys=row_keys,
        node_numbers=node_numbers,
        coordinates=coordinates,
        measured_mask=measured_mask,
        mean_coherence=mean_coherence,
        coherence_status=coherence_status,
        reference_count=max(1, len(references)),
    )


def _vectors_from_spatial_component(block: _FrfBlock, component: np.ndarray) -> np.ndarray:
    vectors = np.zeros((len(block.node_numbers), 3), dtype=complex)
    node_index = {int(node): index for index, node in enumerate(block.node_numbers)}
    for value, (node, signed_direction) in zip(component, block.row_keys):
        direction = abs(int(signed_direction))
        sign = -1.0 if int(signed_direction) < 0 else 1.0
        vectors[node_index[int(node)], direction - 1] = sign * value
    return vectors


def _local_svd_components(
    block: _FrfBlock,
    cluster: Sequence[float],
) -> Tuple[List[Tuple[np.ndarray, float, float, np.ndarray]], Dict[str, Any]]:
    center = float(np.mean(cluster))
    frequency_step = float(np.median(np.diff(block.frequency)))
    padding = max(2.5, 0.04 * center, 8.0 * frequency_step)
    lower = max(float(block.frequency[0]), float(min(cluster)) - padding)
    upper = min(float(block.frequency[-1]), float(max(cluster)) + padding)
    band_mask = (block.frequency >= lower) & (block.frequency <= upper)
    band_indices = np.flatnonzero(band_mask)
    if len(band_indices) < max(8, 2 * len(cluster) + 2):
        return [], {
            "cluster": list(cluster),
            "band_hz": [lower, upper],
            "reason": "too few frequency lines",
        }

    raw = np.asarray(block.matrix[:, band_mask], dtype=complex)
    t = np.linspace(0.0, 1.0, raw.shape[1])
    baseline = raw[:, [0]] * (1.0 - t)[None, :] + raw[:, [-1]] * t[None, :]
    residual = raw - baseline
    residual *= np.sqrt(np.clip(block.mean_coherence[band_mask], 0.05, 1.0))[None, :]

    column_norm = np.linalg.norm(residual, axis=0)
    floor = max(float(np.max(column_norm)) * 1.0e-12, 1.0e-30)
    # Square-root normalization prevents one strong line from hiding a nearby weaker mode
    # while retaining more physical amplitude information than unit-column normalization.
    snapshots = residual / np.sqrt(np.maximum(column_norm, floor))[None, :]
    u, singular_values, vh = np.linalg.svd(snapshots, full_matrices=False)
    if not len(singular_values) or singular_values[0] <= 1.0e-30:
        return [], {
            "cluster": list(cluster),
            "band_hz": [lower, upper],
            "reason": "zero local SVD energy",
        }

    maximum_components = min(len(cluster), len(singular_values), u.shape[1])
    components: List[Tuple[np.ndarray, float, float, np.ndarray]] = []
    local_frequency = block.frequency[band_mask]
    for component_index in range(maximum_components):
        singular_ratio = float(singular_values[component_index] / singular_values[0])
        if component_index > 0 and singular_ratio < 0.015:
            continue
        spectral_energy = np.abs(singular_values[component_index] * vh[component_index]) ** 2
        if float(np.sum(spectral_energy)) <= 1.0e-30:
            continue
        peak_frequency = float(local_frequency[int(np.argmax(spectral_energy))])
        centroid_frequency = float(
            np.sum(local_frequency * spectral_energy) / np.sum(spectral_energy)
        )
        # The peak is more stable for well-separated components; the centroid is less noisy
        # when a component spans two adjacent frequency lines.
        component_frequency = 0.7 * peak_frequency + 0.3 * centroid_frequency
        components.append(
            (
                _vectors_from_spatial_component(block, u[:, component_index]),
                component_frequency,
                singular_ratio,
                spectral_energy / max(float(np.max(spectral_energy)), 1.0e-30),
            )
        )

    metadata = {
        "cluster": [float(value) for value in cluster],
        "band_hz": [lower, upper],
        "frequency_hz": local_frequency.tolist(),
        "singular_values": singular_values[:maximum_components].tolist(),
        "singular_value_ratios": (
            singular_values[:maximum_components] / singular_values[0]
        ).tolist(),
        "component_energy_profiles": [item[3].tolist() for item in components],
        "component_frequencies_hz": [item[1] for item in components],
    }
    return components, metadata


def _max_mac_against_existing(candidate: np.ndarray, existing: Sequence[ModeShape]) -> float:
    values = []
    for mode in existing:
        try:
            value = modal_assurance_criterion(candidate, mode.vectors)
        except Exception:
            value = None
        if value is not None:
            values.append(float(value))
    return max(values, default=0.0)


def _reviewed_modes_from_frf(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
    target_frequencies: Optional[Sequence[float]],
    target_count: int,
):
    base_modes, metadata = _ORIGINAL_MODES_FROM_FRF(
        datasets, geometry, target_frequencies, target_count
    )
    clusters = _close_target_clusters(target_frequencies)
    if not clusters:
        metadata["close_mode_separation"] = {
            "algorithm_version": _ALGORITHM_VERSION,
            "method": "not required",
            "clusters": [],
        }
        return base_modes, metadata

    try:
        block = _build_frf_block(datasets, geometry)
    except Exception as error:
        metadata["close_mode_separation"] = {
            "algorithm_version": _ALGORITHM_VERSION,
            "method": "unavailable",
            "error": str(error),
            "clusters": [list(cluster) for cluster in clusters],
        }
        return base_modes, metadata

    added_modes: List[ModeShape] = []
    cluster_diagnostics: List[Dict[str, Any]] = []
    for cluster in clusters:
        center = float(np.mean(cluster))
        association_window = max(2.0, 0.025 * center)
        nearby_existing = [
            mode
            for mode in base_modes + added_modes
            if min(cluster) - association_window
            <= mode.frequency_hz
            <= max(cluster) + association_window
        ]
        missing_count = max(0, len(cluster) - len(nearby_existing))
        components, diagnostic = _local_svd_components(block, cluster)
        diagnostic["existing_peak_frequencies_hz"] = [
            mode.frequency_hz for mode in nearby_existing
        ]
        diagnostic["requested_additional_shapes"] = missing_count

        if missing_count > 0 and components:
            ranked = sorted(
                components,
                key=lambda item: (
                    _max_mac_against_existing(item[0], nearby_existing + added_modes),
                    -item[2],
                ),
            )
            for vectors, frequency_hz, singular_ratio, _ in ranked[:missing_count]:
                mode = ModeShape(
                    number=0,
                    frequency_hz=float(frequency_hz),
                    node_ids=block.node_numbers.astype(object),
                    coordinates=block.coordinates,
                    vectors=vectors,
                    metadata={
                        "dataset_type": 58,
                        "mode_source": "local response-matrix SVD close-mode candidate",
                        "close_mode_cluster_hz": [float(value) for value in cluster],
                        "singular_value_ratio": float(singular_ratio),
                        "reference_count": block.reference_count,
                        "separation_method": (
                            "multi-reference CMIF-compatible SVD"
                            if block.reference_count > 1
                            else "single-reference local snapshot SVD"
                        ),
                        "frequency_uncertainty_hz": max(
                            float(np.median(np.diff(block.frequency))),
                            0.5 * (max(cluster) - min(cluster)),
                        ),
                    },
                )
                mode.measured_dofs = block.measured_mask.copy()
                added_modes.append(mode)
        diagnostic["added_candidate_frequencies_hz"] = [
            mode.frequency_hz
            for mode in added_modes
            if mode.metadata.get("close_mode_cluster_hz") == [float(value) for value in cluster]
        ]
        cluster_diagnostics.append(diagnostic)

    all_modes = sorted(base_modes + added_modes, key=lambda mode: mode.frequency_hz)
    for new_number, mode in enumerate(all_modes, start=1):
        mode.metadata.setdefault("original_experimental_mode_number", mode.number)
        mode.number = new_number

    scientific_warning = (
        "With one excitation reference, local SVD identifies additional spatial "
        "components inside an overlapping resonance band, but it is not a fully "
        "independent multi-reference modal curve fit. Confirm split modes by MAC, "
        "AutoMAC, coherence, and visual inspection."
    )
    if block.coherence_status.startswith("error"):
        scientific_warning += (
            " Coherence-based weighting could not be computed for this dataset "
            f"({block.coherence_status}); the local SVD residual was weighted as if "
            "coherence were poor across the band, so split components may be "
            "under-detected rather than falsely confirmed."
        )

    metadata.update(
        {
            "mode_count": len(all_modes),
            "detected_peak_frequencies_hz": [mode.frequency_hz for mode in all_modes],
            "close_mode_separation": {
                "algorithm_version": _ALGORITHM_VERSION,
                "method": (
                    "multi-reference CMIF-compatible SVD"
                    if block.reference_count > 1
                    else "single-reference local response-matrix SVD"
                ),
                "reference_count": block.reference_count,
                "added_mode_count": len(added_modes),
                "coherence_status": block.coherence_status,
                "clusters": cluster_diagnostics,
                "scientific_warning": scientific_warning,
            },
        }
    )
    return all_modes, metadata


def render_cmif_svd_diagnostics(experimental_dataset, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    information = experimental_dataset.metadata.get("close_mode_separation", {})
    clusters = information.get("clusters", [])

    figure = Figure(figsize=(11.0, 6.8), constrained_layout=True)
    FigureCanvasAgg(figure)
    axis = figure.add_subplot(111)

    plotted = 0
    for cluster_index, cluster in enumerate(clusters, start=1):
        frequency = np.asarray(cluster.get("frequency_hz", []), dtype=float)
        profiles = cluster.get("component_energy_profiles", [])
        for component_index, profile in enumerate(profiles, start=1):
            values = np.asarray(profile, dtype=float)
            if len(values) != len(frequency) or not len(values):
                continue
            axis.plot(
                frequency,
                values,
                linewidth=1.6,
                label=f"cluster {cluster_index}, SVD component {component_index}",
            )
            plotted += 1
        for target in cluster.get("cluster", []):
            axis.axvline(float(target), linestyle="--", linewidth=0.9, alpha=0.6)
        for candidate in cluster.get("added_candidate_frequencies_hz", []):
            axis.axvline(float(candidate), linestyle="-", linewidth=1.4, alpha=0.8)

    if plotted:
        axis.set_xlabel("Frequency, Hz")
        axis.set_ylabel("Normalized local SVD component energy")
        axis.set_title(
            "Close-mode separation diagnostics\n"
            + str(information.get("method", "local SVD"))
        )
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best", fontsize=8)
    else:
        axis.text(
            0.5,
            0.5,
            "No additional close-mode SVD component was required or available.",
            ha="center",
            va="center",
            transform=axis.transAxes,
        )
        axis.set_axis_off()

    figure.savefig(output_path, dpi=190)
    return output_path


def install_cmif_separation() -> None:
    global _INSTALLED, _ORIGINAL_MODES_FROM_FRF
    if _INSTALLED:
        return
    _ORIGINAL_MODES_FROM_FRF = universal_reader._modes_from_frf_datasets
    universal_reader._modes_from_frf_datasets = _reviewed_modes_from_frf
    _INSTALLED = True
