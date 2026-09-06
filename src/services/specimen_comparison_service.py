"""Adapt existing comparator pairs without invoking numerical comparison."""

from __future__ import annotations

from copy import deepcopy
from typing import Tuple
from urllib.parse import quote

from domain.modal_observation import InclusionStatus, ModalObservation
from domain.specimen import require_identifier
from modal_core import ComparisonResult, ModePairResult


def _inclusion(pair: ModePairResult) -> Tuple[InclusionStatus, str]:
    decision = str(getattr(pair, "manual_decision", "automatic")).strip().lower()
    status = pair.status.strip().lower()
    # Review is not evidence for a numerical weight. Unknown decisions/statuses
    # remain excluded until reviewed; explicit manual acceptance takes priority.
    source = status if decision == "automatic" else decision
    if source in {"accepted", "included", "excellent match", "good match", "frequency match"}:
        inclusion = InclusionStatus.INCLUDED
    elif source == "downweighted":
        inclusion = InclusionStatus.DOWNWEIGHTED
    else:
        inclusion = InclusionStatus.EXCLUDED
    reason = pair.status or "No comparator status available"
    if decision != "automatic":
        reason = f"Manual decision: {getattr(pair, 'manual_decision')}; {reason}"
    comment = getattr(pair, "manual_comment", "")
    if comment:
        reason += f"; {comment}"
    return inclusion, reason


def comparison_to_observations(
    comparison: ComparisonResult,
    design_id: str,
    physical_specimen_id: str,
    test_run_id: str,
) -> Tuple[ModalObservation, ...]:
    """Return one observation per source pair, preserving its order and values.

    Design identity and signed frequency error live in metadata because the
    domain record has no dedicated fields for them. ``source_pair`` preserves
    all pair diagnostics, including dynamic review/coverage fields, except
    the two mode vectors. Point coordinates, node IDs and measured-DOF masks
    are retained as lists. Metadata is detached from the source.

    Only explicit downweighting is carried through; no weight is inferred.
    Unmatched modes and pairs removed by manual review are not reconstructed.
    Clusters and identification-specific inclusion policies belong to later PRs.
    """
    for name, value in (("design_id", design_id),
                        ("physical_specimen_id", physical_specimen_id),
                        ("test_run_id", test_run_id)):
        require_identifier(value, name)
    identity = "/".join(quote(value, safe="") for value in
                        (design_id, physical_specimen_id, test_run_id))
    observations = []
    for index, pair in enumerate(comparison.pairs):
        source_pair = {}
        for name, value in vars(pair).items():
            if name in {"abaqus_vector", "experimental_vector"}:
                continue
            if name in {"coordinates", "node_ids", "measured_dof_mask"} and value is not None:
                value = value.tolist()
            source_pair[name] = deepcopy(value)
        inclusion, reason = _inclusion(pair)
        observations.append(ModalObservation(
            observation_id=f"{identity}/pair/{index}/A{pair.abaqus_mode}/E{pair.experimental_mode}",
            physical_specimen_id=physical_specimen_id,
            test_run_id=test_run_id,
            fe_mode_id=pair.abaqus_mode,
            experimental_mode_id=pair.experimental_mode,
            fe_frequency_hz=pair.abaqus_frequency_hz,
            experimental_frequency_hz=pair.experimental_frequency_hz,
            mac=pair.mac,
            inclusion_status=inclusion,
            reason=reason,
            metadata={
                "design_id": design_id,
                "frequency_error_percent": pair.frequency_error_percent,
                "source_pair": source_pair,
                "comparison_metadata": deepcopy(comparison.metadata),
                "comparison_warnings": deepcopy(comparison.warnings),
            },
        ))
    return tuple(observations)
