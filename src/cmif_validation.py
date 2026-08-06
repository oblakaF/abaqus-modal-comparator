from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

import universal_reader
from modal_core import ModeShape, modal_assurance_criterion


_INSTALLED = False
_ALGORITHM_VERSION = "conservative-svd-validation-v2"
_DUPLICATE_MAC_LIMIT = 0.90
_MIN_MULTI_REFERENCE_SECOND_RATIO = 0.05


def _is_svd_mode(mode: ModeShape) -> bool:
    source = str(mode.metadata.get("mode_source", "")).lower()
    return "svd" in source and "close-mode" in source


def _measured_mac(first: ModeShape, second: ModeShape) -> Optional[float]:
    if first.vectors.shape != second.vectors.shape:
        return None
    mask = np.ones(first.vectors.shape, dtype=bool)
    first_mask = getattr(first, "measured_dofs", None)
    second_mask = getattr(second, "measured_dofs", None)
    if first_mask is not None and np.asarray(first_mask).shape == mask.shape:
        mask &= np.asarray(first_mask, dtype=bool)
    if second_mask is not None and np.asarray(second_mask).shape == mask.shape:
        mask &= np.asarray(second_mask, dtype=bool)
    finite = (
        np.isfinite(first.vectors.real)
        & np.isfinite(first.vectors.imag)
        & np.isfinite(second.vectors.real)
        & np.isfinite(second.vectors.imag)
    )
    mask &= finite
    if not np.any(mask):
        return None
    return modal_assurance_criterion(first.vectors[mask], second.vectors[mask])


def _max_mac(candidate: ModeShape, modes: Sequence[ModeShape]) -> float:
    values = [
        value
        for value in (_measured_mac(candidate, mode) for mode in modes)
        if value is not None
    ]
    return max((float(value) for value in values), default=0.0)


def _cluster_diagnostic(
    information: Dict[str, Any], cluster: Sequence[float]
) -> Dict[str, Any]:
    wanted = np.asarray(cluster, dtype=float)
    for diagnostic in information.get("clusters", []):
        current = np.asarray(diagnostic.get("cluster", []), dtype=float)
        if current.shape == wanted.shape and np.allclose(current, wanted, rtol=0.0, atol=1.0e-6):
            return diagnostic
    diagnostic = {"cluster": [float(value) for value in cluster]}
    information.setdefault("clusters", []).append(diagnostic)
    return diagnostic


def _annotate_standard_mode(mode: ModeShape) -> None:
    metadata = mode.metadata
    source = str(metadata.get("mode_source", ""))
    dataset_type = metadata.get("dataset_type")
    if dataset_type in (55, 2414) or "curve-fitted" in source.lower():
        metadata["source_label"] = "Curve-fitted modal set"
        metadata["confidence_label"] = "High"
        metadata["confidence_score"] = 1.0
        return

    if dataset_type == 58 or "frf" in source.lower() or "peak" in source.lower():
        # Only a genuinely computed coherence value may raise confidence above the
        # peak-derived baseline (ROADMAP Stage 2 #1). A missing or unparsable
        # coherence channel must not be able to score as "High peak confidence".
        # Legacy modes (cache/project data saved before this field existed) have
        # no coherence_status at all and are normalized to "unavailable" rather
        # than trusting whatever mean_coherence they happened to store.
        coherence_status = str(metadata.get("coherence_status") or "unavailable")
        coherence_value: Optional[float] = None
        if coherence_status == "computed":
            try:
                coherence_value = float(metadata.get("mean_coherence"))
            except (TypeError, ValueError):
                coherence_value = None

        if coherence_value is None:
            reason = "parse error" if coherence_status == "parse_error" else "unavailable"
            confidence = f"Peak-derived (coherence {reason})"
            confidence_score = 0.0
        elif coherence_value >= 0.90:
            confidence = "High peak confidence"
            confidence_score = coherence_value
        elif coherence_value >= 0.70:
            confidence = "Medium peak confidence"
            confidence_score = coherence_value
        else:
            confidence = "Peak-derived"
            confidence_score = coherence_value
        metadata["source_label"] = "FRF resonance peak"
        metadata["confidence_label"] = confidence
        metadata["confidence_score"] = float(np.clip(confidence_score, 0.0, 1.0))
        return

    metadata.setdefault("source_label", "Imported modal vector")
    metadata.setdefault("confidence_label", "Imported")
    metadata.setdefault("confidence_score", 1.0)


def _candidate_confidence(
    reference_count: int,
    second_ratio: float,
    duplicate_mac: float,
) -> float:
    reference_factor = 1.0 if reference_count > 1 else 0.20
    rank_factor = float(np.clip(second_ratio / 0.20, 0.0, 1.0))
    distinctness = float(np.clip((1.0 - duplicate_mac) / 0.50, 0.0, 1.0))
    return reference_factor * rank_factor * distinctness


def validate_close_mode_candidates(
    modes: Sequence[ModeShape],
    metadata: Dict[str, Any],
) -> Tuple[List[ModeShape], Dict[str, Any]]:
    """Remove unsupported or duplicate local-SVD candidates before modal matching.

    A single-reference FRF scan has one response column per frequency line. Local snapshot
    SVD can be useful diagnostically, but it does not provide the independent reference
    information required to promote an additional component to an automatically accepted
    experimental mode. Such candidates therefore remain in diagnostics only.
    """
    information = metadata.setdefault("close_mode_separation", {})
    reference_count = int(information.get("reference_count", 1) or 1)
    base_modes = [mode for mode in modes if not _is_svd_mode(mode)]
    candidates = [mode for mode in modes if _is_svd_mode(mode)]

    for mode in base_modes:
        _annotate_standard_mode(mode)

    accepted: List[ModeShape] = []
    rejected_records: List[Dict[str, Any]] = []
    accepted_records: List[Dict[str, Any]] = []

    for candidate in candidates:
        cluster = [
            float(value)
            for value in candidate.metadata.get("close_mode_cluster_hz", [])
        ]
        if not cluster:
            cluster = [float(candidate.frequency_hz)]
        diagnostic = _cluster_diagnostic(information, cluster)
        center = float(np.mean(cluster))
        span = float(max(cluster) - min(cluster)) if len(cluster) > 1 else 0.0
        association_window = max(3.0, 0.04 * center, span)
        nearby_base = [
            mode
            for mode in base_modes
            if min(cluster) - association_window
            <= mode.frequency_hz
            <= max(cluster) + association_window
        ]
        target_shape_count = max(1, len(cluster))
        # Acceptance is driven by the actual per-frequency multi-reference CMIF
        # singular-value ratio (evidence that a second reference resolves an
        # independent mode), not by the local snapshot-SVD candidate shape's own
        # component energy ratios, which reflect the extraction method rather than
        # independent-reference evidence.
        cmif_ratio = diagnostic.get("cmif_max_second_to_first_singular_ratio")
        second_ratio = (
            float(cmif_ratio) if cmif_ratio is not None and np.isfinite(cmif_ratio) else 0.0
        )
        duplicate_mac = _max_mac(candidate, base_modes + accepted)
        confidence_score = _candidate_confidence(
            reference_count, second_ratio, duplicate_mac
        )

        reasons: List[str] = []
        if len(nearby_base) >= target_shape_count:
            reasons.append(
                "the local band already contains the required number of independent FRF peaks"
            )
        if duplicate_mac >= _DUPLICATE_MAC_LIMIT:
            reasons.append(
                f"duplicate spatial shape (maximum MAC to an existing mode = {duplicate_mac:.3f})"
            )
        if reference_count < 2:
            reasons.append(
                "single-reference local SVD is diagnostic only and cannot establish an independent extra mode"
            )
        elif second_ratio < _MIN_MULTI_REFERENCE_SECOND_RATIO:
            reasons.append(
                f"insufficient independent SVD rank (second/first ratio = {second_ratio:.4f})"
            )

        accepted_candidate = not reasons
        record = {
            "frequency_hz": float(candidate.frequency_hz),
            "cluster_hz": cluster,
            "reference_count": reference_count,
            "second_to_first_singular_ratio": float(second_ratio),
            "maximum_mac_to_existing": float(duplicate_mac),
            "confidence_score": float(confidence_score),
            "confidence_label": (
                "High" if confidence_score >= 0.75 else
                "Medium" if confidence_score >= 0.45 else
                "Low"
            ),
            "accepted_for_pairing": accepted_candidate,
            "reason": "accepted" if accepted_candidate else "; ".join(reasons),
        }

        if accepted_candidate:
            candidate.metadata.update(
                {
                    "source_label": "Multi-reference SVD/CMIF component",
                    "confidence_label": record["confidence_label"],
                    "confidence_score": record["confidence_score"],
                    "candidate_validation": record,
                }
            )
            accepted.append(candidate)
            accepted_records.append(record)
        else:
            rejected_records.append(record)

        diagnostic["existing_peak_frequencies_hz"] = [
            float(mode.frequency_hz) for mode in nearby_base
        ]
        diagnostic["existing_peak_count"] = len(nearby_base)
        diagnostic["requested_additional_shapes"] = max(
            0, target_shape_count - len(nearby_base)
        )
        diagnostic.setdefault("pre_validation_candidate_frequencies_hz", []).append(
            float(candidate.frequency_hz)
        )
        if accepted_candidate:
            diagnostic.setdefault("accepted_candidates", []).append(record)
        else:
            diagnostic.setdefault("rejected_candidates", []).append(record)

    final_modes = sorted(base_modes + accepted, key=lambda mode: mode.frequency_hz)
    for new_number, mode in enumerate(final_modes, start=1):
        mode.metadata.setdefault("pre_validation_experimental_mode_number", mode.number)
        mode.number = new_number

    for diagnostic in information.get("clusters", []):
        diagnostic["added_candidate_frequencies_hz"] = [
            item["frequency_hz"]
            for item in diagnostic.get("accepted_candidates", [])
        ]
        diagnostic["rejected_candidate_frequencies_hz"] = [
            item["frequency_hz"]
            for item in diagnostic.get("rejected_candidates", [])
        ]

    information.update(
        {
            "validation_algorithm_version": _ALGORITHM_VERSION,
            "automatic_pairing_policy": (
                "Single-reference local-SVD components are diagnostics only. Automatic "
                "promotion requires multiple independent references, sufficient second "
                "singular-value energy, and no duplicate high-MAC shape."
            ),
            "pre_validation_candidate_count": len(candidates),
            "added_mode_count": len(accepted),
            "rejected_mode_count": len(rejected_records),
            "accepted_candidates": accepted_records,
            "rejected_candidates": rejected_records,
            "scientific_warning": (
                "Local SVD of a single-reference scan cannot by itself prove a second "
                "independent experimental mode. Rejected candidates remain visible in the "
                "Close modes diagnostics but are excluded from MAC pairing. Use a curve-fitted "
                "Testlab modal set (UNV 55/2414) or multi-reference FRFs for confirmation."
            ),
        }
    )

    metadata["mode_count"] = len(final_modes)
    metadata["detected_peak_frequencies_hz"] = [
        float(mode.frequency_hz) for mode in final_modes
    ]
    metadata["close_mode_candidate_rejections"] = rejected_records
    metadata["mode_source_counts"] = dict(
        Counter(mode.metadata.get("source_label", "Unknown") for mode in final_modes)
    )
    return final_modes, metadata


def _validated_modes_from_frf(
    datasets,
    geometry,
    target_frequencies,
    target_count,
):
    modes, metadata = _ORIGINAL_MODES_FROM_FRF(
        datasets, geometry, target_frequencies, target_count
    )
    return validate_close_mode_candidates(modes, metadata)


def install_cmif_validation() -> None:
    global _INSTALLED, _ORIGINAL_MODES_FROM_FRF
    if _INSTALLED:
        return
    _ORIGINAL_MODES_FROM_FRF = universal_reader._modes_from_frf_datasets
    universal_reader._modes_from_frf_datasets = _validated_modes_from_frf
    _INSTALLED = True
