from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

import universal_reader
from modal_core import ModeShape, modal_assurance_criterion
from universal_hardening import _scalar_int


_INSTALLED = False
_ALGORITHM_VERSION = "local-svd-v2-multi-reference"


@dataclass
class _MultiReferenceFrfBlock:
    """A genuine response x reference x frequency FRF matrix, built from every
    compatible reference present in the file (ROADMAP Stage 2 #2), instead of
    universal_hardening._safe_select_frf_group's single best-scoring group.

    matrix has shape (len(row_keys), len(reference_keys), len(frequency)).
    """

    frequency: np.ndarray
    matrix: np.ndarray
    row_keys: List[Tuple[int, int]]
    reference_keys: List[Tuple[int, int]]
    node_numbers: np.ndarray
    coordinates: np.ndarray
    measured_mask: np.ndarray
    mean_coherence: np.ndarray
    coherence_status: str
    reference_count: int
    duplicate_channels: List[Dict[str, Any]]
    excluded_response_dofs: List[Dict[str, Any]]
    dropped_references: List[Dict[str, Any]]
    initial_response_dof_count: int
    response_dof_coverage_fraction: float


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


def _channel_quantity_priority(dataset: Dict[str, Any]) -> int:
    label = universal_reader._frf_label(dataset)
    if "displacement" in label:
        return 3
    if "velocity" in label:
        return 2
    if "acceleration" in label or "accelerance" in label:
        return 1
    return 0


def _build_multi_reference_frf_block(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
) -> _MultiReferenceFrfBlock:
    """Build a genuine response x reference x frequency FRF matrix from every
    compatible reference in the file (ROADMAP Stage 2 #2).

    Each channel is identified by its full (response node, response direction,
    reference node, reference direction) key. References sharing a common
    frequency-axis signature and physical quantity are pooled into one
    candidate group; a reference on an incompatible axis/quantity is excluded
    rather than misaligned against the rest. Within the winning group, every
    channel's actual frequency samples are further compared against the
    canonical axis with np.allclose -- two axes can share the same length,
    first value, last value, and median step while differing in between, so
    the coarse signature alone is not sufficient proof of alignment. A
    response DOF not covered by every included reference is excluded from the
    matrix rather than fabricated (for example zero-filled). A duplicate
    channel (the same response and reference key appearing more than once) is
    kept once if the two occurrences are numerically equivalent (np.allclose),
    recorded with status "equivalent"; if they disagree, both are dropped and
    recorded with status "conflicting" rather than silently keeping either one.
    """
    # group[(signature, quantity_priority)][(ref_node, ref_dir)] -> [dataset, ...]
    groups: Dict[Tuple[Any, int], Dict[Tuple[int, int], List[Dict[str, Any]]]] = {}
    canonical_dataset_by_group: Dict[Tuple[Any, int], Dict[str, Any]] = {}

    for dataset in datasets:
        if universal_reader._dataset_type(dataset) != 58:
            continue
        if _scalar_int(dataset.get("func_type"), -1) != 4:
            continue
        response_node = _scalar_int(dataset.get("rsp_node"), -1)
        if response_node not in geometry:
            continue
        response_direction = _scalar_int(dataset.get("rsp_dir"), 0)
        if abs(response_direction) not in (1, 2, 3):
            continue
        signature = universal_reader._axis_signature(dataset)
        if signature is None:
            continue
        data = universal_reader._as_array(dataset.get("data"), dtype=complex)
        if len(data) != signature[0]:
            continue
        reference_node = _scalar_int(dataset.get("ref_node"), 0)
        reference_direction = _scalar_int(dataset.get("ref_dir"), 0)

        group_key = (signature, _channel_quantity_priority(dataset))
        reference_key = (reference_node, reference_direction)
        canonical_dataset_by_group.setdefault(group_key, dataset)
        groups.setdefault(group_key, {}).setdefault(reference_key, []).append(dataset)

    if not groups:
        raise ValueError("No usable transfer-function group is available for close-mode separation.")

    def group_score(item) -> Tuple[int, int, int]:
        (_, quantity_priority), references_in_group = item
        unique_channels = sum(
            len({(_scalar_int(d.get("rsp_node"), -1), _scalar_int(d.get("rsp_dir"), 0)) for d in datasets_for_reference})
            for datasets_for_reference in references_in_group.values()
        )
        return quantity_priority, len(references_in_group), unique_channels

    winning_group_key, winning_group = max(groups.items(), key=group_score)
    canonical_frequency = universal_reader._as_array(
        canonical_dataset_by_group[winning_group_key].get("x"), dtype=float
    )

    dropped_references: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for group_key, references_in_group in groups.items():
        if group_key == winning_group_key:
            continue
        for reference_key in references_in_group:
            if reference_key in winning_group:
                continue
            reason = (
                "incompatible frequency axis"
                if group_key[0] != winning_group_key[0]
                else "incompatible physical quantity"
            )
            dropped_references.setdefault(reference_key, {"reference": reference_key, "reason": reason})

    # Within the winning (signature, quantity) group, verify every channel's
    # actual samples against the canonical axis and resolve duplicate channels.
    reference_channels: Dict[Tuple[int, int], Dict[Tuple[int, int], Dict[str, Any]]] = {}
    axis_mismatch_references: Dict[Tuple[int, int], set] = {}
    duplicate_channels: List[Dict[str, Any]] = []
    excluded_channel_keys: set = set()

    for reference_key, datasets_for_reference in winning_group.items():
        for dataset in datasets_for_reference:
            response_key = (
                _scalar_int(dataset.get("rsp_node"), -1),
                _scalar_int(dataset.get("rsp_dir"), 0),
            )
            x = universal_reader._as_array(dataset.get("x"), dtype=float)
            if len(x) != len(canonical_frequency) or not np.allclose(
                x, canonical_frequency, rtol=1.0e-8, atol=1.0e-10
            ):
                axis_mismatch_references.setdefault(reference_key, set()).add(response_key)
                continue

            channel_key = (reference_key, response_key)
            if channel_key in excluded_channel_keys:
                continue
            data = universal_reader._as_array(dataset.get("data"), dtype=complex)
            channels_for_reference = reference_channels.setdefault(reference_key, {})
            if response_key in channels_for_reference:
                previous_data = universal_reader._as_array(
                    channels_for_reference[response_key].get("data"), dtype=complex
                )
                if np.allclose(previous_data, data, rtol=1.0e-6, atol=1.0e-9):
                    duplicate_channels.append(
                        {"response": response_key, "reference": reference_key, "status": "equivalent"}
                    )
                else:
                    duplicate_channels.append(
                        {"response": response_key, "reference": reference_key, "status": "conflicting"}
                    )
                    del channels_for_reference[response_key]
                    excluded_channel_keys.add(channel_key)
                continue
            channels_for_reference[response_key] = dataset

    # A reference can end up with zero usable channels either because every
    # channel's axis failed the sample-for-sample check, or because every
    # channel was excluded as a conflicting duplicate; report whichever
    # applies rather than letting the reference silently disappear.
    for reference_key in winning_group:
        if reference_key in reference_channels and reference_channels[reference_key]:
            continue
        if reference_key in axis_mismatch_references:
            reason = (
                "individual channel frequency axis does not match the reference axis "
                "sample-for-sample, despite matching length/start/end/median-step"
            )
        else:
            reason = "every channel for this reference was excluded as a conflicting duplicate"
        dropped_references.setdefault(reference_key, {"reference": reference_key, "reason": reason})

    reference_keys = sorted(key for key, channels in reference_channels.items() if channels)
    if not reference_keys:
        raise ValueError("No reference has any channel whose frequency axis matches sample-for-sample.")

    response_key_sets = [set(reference_channels[reference_key]) for reference_key in reference_keys]
    common_response_keys = set.intersection(*response_key_sets) if response_key_sets else set()
    all_response_keys = set.union(*response_key_sets) if response_key_sets else set()
    initial_response_dof_count = len(all_response_keys)

    excluded_response_dofs = [
        {
            "node": response_key[0],
            "direction": response_key[1],
            "present_for_references": sorted(
                reference_key
                for reference_key in reference_keys
                if response_key in reference_channels[reference_key]
            ),
        }
        for response_key in sorted(all_response_keys - common_response_keys)
    ]

    if not common_response_keys:
        raise ValueError(
            "No response DOF is covered by every compatible reference for close-mode separation."
        )

    row_keys = sorted(common_response_keys)
    frequency = canonical_frequency
    response_dof_coverage_fraction = (
        len(row_keys) / initial_response_dof_count if initial_response_dof_count else 0.0
    )

    matrix = np.zeros((len(row_keys), len(reference_keys), len(frequency)), dtype=complex)
    for reference_index, reference_key in enumerate(reference_keys):
        channels = reference_channels[reference_key]
        for response_index, response_key in enumerate(row_keys):
            matrix[response_index, reference_index, :] = universal_reader._as_array(
                channels[response_key].get("data"), dtype=complex
            )

    node_numbers = np.asarray(sorted({node for node, _ in row_keys}), dtype=int)
    node_index = {int(node): index for index, node in enumerate(node_numbers)}
    coordinates = universal_reader._coordinates_for_nodes(node_numbers, geometry)
    measured_mask = np.zeros((len(node_numbers), 3), dtype=bool)
    for node, signed_direction in row_keys:
        measured_mask[node_index[int(node)], abs(int(signed_direction)) - 1] = True

    primary_reference_node, primary_reference_direction = reference_keys[0]
    try:
        coherence_lookup = universal_reader._coherence_by_dof(
            datasets, frequency, primary_reference_node, primary_reference_direction
        )
        coherence_rows = [coherence_lookup[key] for key in row_keys if key in coherence_lookup]
        if coherence_rows:
            mean_coherence = np.mean(np.vstack(coherence_rows), axis=0)
            coherence_status = "computed"
        else:
            mean_coherence = np.ones_like(frequency, dtype=float)
            coherence_status = "unavailable"
    except (TypeError, ValueError, IndexError, KeyError) as error:
        mean_coherence = np.zeros_like(frequency, dtype=float)
        coherence_status = f"error: {error}"

    return _MultiReferenceFrfBlock(
        frequency=frequency,
        matrix=matrix,
        row_keys=row_keys,
        reference_keys=reference_keys,
        node_numbers=node_numbers,
        coordinates=coordinates,
        measured_mask=measured_mask,
        mean_coherence=mean_coherence,
        coherence_status=coherence_status,
        reference_count=len(reference_keys),
        duplicate_channels=duplicate_channels,
        excluded_response_dofs=excluded_response_dofs,
        dropped_references=sorted(dropped_references.values(), key=lambda item: item["reference"]),
        initial_response_dof_count=initial_response_dof_count,
        response_dof_coverage_fraction=response_dof_coverage_fraction,
    )


def _cmif_singular_values(block: _MultiReferenceFrfBlock) -> np.ndarray:
    """Conventional multi-reference CMIF: the singular values of the complex
    response x reference matrix H(f), computed independently at every
    frequency line. Returns an array of shape
    (len(block.frequency), min(len(block.row_keys), block.reference_count)),
    descending within each row. A peak in the second column near an existing
    peak in the first indicates a mode that a single reference cannot resolve
    on its own.
    """
    # np.linalg.svd batches over leading dimensions, so move frequency first.
    stacked = np.moveaxis(block.matrix, 2, 0)
    return np.linalg.svd(stacked, compute_uv=False)


def _vectors_from_spatial_component(block: _MultiReferenceFrfBlock, component: np.ndarray) -> np.ndarray:
    vectors = np.zeros((len(block.node_numbers), 3), dtype=complex)
    node_index = {int(node): index for index, node in enumerate(block.node_numbers)}
    for value, (node, signed_direction) in zip(component, block.row_keys):
        direction = abs(int(signed_direction))
        sign = -1.0 if int(signed_direction) < 0 else 1.0
        vectors[node_index[int(node)], direction - 1] = sign * value
    return vectors


def _local_svd_components(
    block: _MultiReferenceFrfBlock,
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

    # block.matrix is (Nresponse, Nreference, Nfrequency). Each reference's band is
    # detrended against its own band edges, then references are concatenated as
    # additional snapshot columns: extra independent references give the SVD more
    # independent excitation patterns to separate close modes with, exactly the
    # benefit multi-reference testing provides over a single reference (ROADMAP
    # Stage 2 #2). With one reference this reduces exactly to the prior single-
    # reference snapshot-POD computation.
    raw = np.asarray(block.matrix[:, :, band_mask], dtype=complex)
    band_size = raw.shape[2]
    t = np.linspace(0.0, 1.0, band_size)
    baseline = raw[:, :, [0]] * (1.0 - t)[None, None, :] + raw[:, :, [-1]] * t[None, None, :]
    residual = raw - baseline
    coherence_weight = np.sqrt(np.clip(block.mean_coherence[band_mask], 0.05, 1.0))
    residual *= coherence_weight[None, None, :]
    snapshots_raw = residual.reshape(residual.shape[0], -1)

    column_norm = np.linalg.norm(snapshots_raw, axis=0)
    floor = max(float(np.max(column_norm)) * 1.0e-12, 1.0e-30)
    # Square-root normalization prevents one strong line from hiding a nearby weaker mode
    # while retaining more physical amplitude information than unit-column normalization.
    snapshots = snapshots_raw / np.sqrt(np.maximum(column_norm, floor))[None, :]
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
        # Sum energy across references at each frequency line: multiple references
        # share the same band frequency samples, so this collapses the
        # (Nreference, Nband) snapshot energy back to one per-frequency profile.
        spectral_energy = (
            (np.abs(singular_values[component_index] * vh[component_index]) ** 2)
            .reshape(raw.shape[1], band_size)
            .sum(axis=0)
        )
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
        block = _build_multi_reference_frf_block(datasets, geometry)
    except Exception as error:
        metadata["close_mode_separation"] = {
            "algorithm_version": _ALGORITHM_VERSION,
            "method": "unavailable",
            "error": str(error),
            "clusters": [list(cluster) for cluster in clusters],
        }
        return base_modes, metadata

    # Conventional CMIF: singular values of H(f) at every frequency line, computed
    # once and sliced per cluster band below (ROADMAP Stage 2 #2 "report ... matrix
    # rank, singular-value ratios").
    cmif_singular_values = _cmif_singular_values(block)
    matrix_rank_capacity = int(cmif_singular_values.shape[1])

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
        diagnostic["cmif_matrix_rank_capacity"] = matrix_rank_capacity
        band_hz = diagnostic.get("band_hz")
        if band_hz is not None:
            band_mask = (block.frequency >= band_hz[0]) & (block.frequency <= band_hz[1])
            if matrix_rank_capacity > 1 and np.any(band_mask):
                ratios = cmif_singular_values[band_mask, 1] / np.maximum(
                    cmif_singular_values[band_mask, 0], 1.0e-30
                )
                diagnostic["cmif_max_second_to_first_singular_ratio"] = float(np.max(ratios))
            else:
                diagnostic["cmif_max_second_to_first_singular_ratio"] = None

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
                            "local snapshot-SVD candidate shape (multi-reference bands stacked)"
                            if block.reference_count > 1
                            else "local snapshot-SVD candidate shape (single-reference)"
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

    if block.reference_count > 1:
        scientific_warning = (
            f"Candidate shapes were extracted by a local snapshot-SVD candidate shape "
            f"method: {block.reference_count} independent excitation references' band "
            "snapshots were stacked and locally decomposed by SVD. The per-frequency "
            "multi-reference CMIF singular values (reported per cluster below) provide "
            "genuine evidence of an independent second mode, but shape extraction itself "
            "is not yet a full per-frequency-line CMIF modal curve fit -- that remains a "
            "separate future task. Confirm split modes by MAC, AutoMAC, coherence, and "
            "visual inspection."
        )
    else:
        scientific_warning = (
            "With one excitation reference, the local snapshot-SVD candidate shape method "
            "identifies additional spatial components inside an overlapping resonance "
            "band, but it is not a fully independent multi-reference modal curve fit. "
            "Confirm split modes by MAC, AutoMAC, coherence, and visual inspection."
        )
    if block.coherence_status.startswith("error"):
        scientific_warning += (
            " Coherence-based weighting could not be computed for this dataset "
            f"({block.coherence_status}); the local SVD residual was weighted as if "
            "coherence were poor across the band, so split components may be "
            "under-detected rather than falsely confirmed."
        )
    conflicting_duplicates = [
        entry for entry in block.duplicate_channels if entry.get("status") == "conflicting"
    ]
    if conflicting_duplicates:
        scientific_warning += (
            f" {len(conflicting_duplicates)} channel(s) were exported more than once with "
            "conflicting data for the same response/reference key; every occurrence was "
            "excluded rather than silently choosing one (see duplicate_channels)."
        )

    metadata.update(
        {
            "mode_count": len(all_modes),
            "detected_peak_frequencies_hz": [mode.frequency_hz for mode in all_modes],
            "close_mode_separation": {
                "algorithm_version": _ALGORITHM_VERSION,
                "method": (
                    "local snapshot-SVD candidate shape (multi-reference bands stacked)"
                    if block.reference_count > 1
                    else "local snapshot-SVD candidate shape (single-reference)"
                ),
                "reference_count": block.reference_count,
                "reference_keys": [list(key) for key in block.reference_keys],
                "matrix_rank_capacity": matrix_rank_capacity,
                "added_mode_count": len(added_modes),
                "coherence_status": block.coherence_status,
                "initial_response_dof_count": block.initial_response_dof_count,
                "common_response_dof_count": len(block.row_keys),
                "response_dof_coverage_fraction": block.response_dof_coverage_fraction,
                "duplicate_channels": block.duplicate_channels,
                "excluded_response_dofs": block.excluded_response_dofs,
                "rejected_references": block.dropped_references,
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
