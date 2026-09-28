"""Build a FrozenRegistration from a finished, confirmed comparison.

Application-level glue between the reviewed comparator and the model-neutral
domain contract.  Every value is read from the geometry/orientation state the
comparator already selected: orientation is never re-selected, no transform is
recomputed, and no MAC, frequency, or other modal evidence is consulted.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import numpy as np

from coordinate_calibration import CoordinateCalibration
from domain.registration import FrozenRegistration
from modal_core import ComparisonResult
from reviewed_core import (
    _candidate_summary,
    _explicit_measurement_mask,
    experimental_measurement_masks,
)
from scientific_state import (
    calibration_fingerprint,
    experimental_source_content_identity,
    modal_dataset_geometry_identity,
    orientation_registration_valid,
)


ORIENTATION_SOURCES = ("geometry_unique", "user_confirmed")

# Geometry-quality values the comparator already records in result.metadata.
_RESULT_METRIC_KEYS = (
    "mapping_rms",
    "mapping_max_residual",
    "mapping_rms_in_abaqus_units",
    "mapping_max_residual_in_abaqus_units",
    "raw_experimental_bbox",
    "mapped_fe_bbox",
    "transformed_full_fe_bbox_in_experimental_coordinates",
    "evaluated_geometry_candidate_count",
    "geometry_calibration",
)
_TRANSFORM_METRIC_KEYS = (
    "determinant",
    "mirrored",
    "axis_permutation",
    "planar_axes_swapped",
    "unique_mapped_abaqus_nodes",
    "experimental_point_count",
)


class RegistrationRefusedError(ValueError):
    """The comparison state is not sufficient to freeze a registration."""


def _plain(value: Any) -> Any:
    """Convert numpy containers/scalars to plain Python values (no stringifying)."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _require_comparison_calibration(
    result: ComparisonResult, calibration_state: Mapping[str, Any]
) -> None:
    details = result.geometry.calibration_details
    differing = sorted(
        key
        for key, value in calibration_state.items()
        if key not in details or details[key] != value
    )
    if differing:
        raise RegistrationRefusedError(
            "The comparison was not run with the supplied calibration "
            f"(differing calibration fields: {differing})."
        )


def _source_identity(
    result: ComparisonResult, injected: Optional[Mapping[str, Any]]
) -> dict[str, Any]:
    if injected is not None:
        if not isinstance(injected, Mapping) or "sha256" not in injected:
            raise RegistrationRefusedError(
                "An injected experimental source identity must be a content identity "
                "with a sha256 entry."
            )
        return dict(injected)
    identity = experimental_source_content_identity(result.experimental.source_path)
    if identity is None:
        raise RegistrationRefusedError(
            "The experimental source file is not readable, so no content identity "
            "can be computed; the legacy path/size/mtime identity is not used as a "
            "fallback."
        )
    return identity


def _confirmed_candidate_id(
    result: ComparisonResult,
    orientation_binding: Optional[Mapping[str, Any]],
    source_identity: Mapping[str, Any],
    calibration_state: Mapping[str, Any],
) -> str:
    orientation_source = result.metadata.get("orientation_source")
    if orientation_source not in ORIENTATION_SOURCES:
        raise RegistrationRefusedError(
            f"The comparison records no valid orientation_source ({orientation_source!r})."
        )
    candidate_id = str(_candidate_summary(result.geometry)["candidate_id"])
    if orientation_binding is None:
        if orientation_source == "user_confirmed":
            raise RegistrationRefusedError(
                "The comparison used a user-confirmed orientation, but no orientation "
                "confirmation binding was supplied."
            )
        return candidate_id
    if not orientation_registration_valid(
        orientation_binding, source_identity, calibration_state
    ):
        raise RegistrationRefusedError(
            "The orientation confirmation is not valid for this experimental source "
            "and calibration."
        )
    confirmed_ids = {
        orientation_binding["candidate"].get("candidate_id"),
        orientation_binding.get("candidate_identity", candidate_id),
    }
    if confirmed_ids != {candidate_id}:
        raise RegistrationRefusedError(
            "The orientation confirmation is for a different candidate than the one "
            "the comparison used."
        )
    return candidate_id


def _measured_dof_contract(experimental_modes, experimental_node_ids) -> list:
    for mode in experimental_modes:
        if _explicit_measurement_mask(mode) is None:
            raise RegistrationRefusedError(
                f"Experimental mode {mode.number} has no explicit measured-DOF mask; "
                "a registration never stores an inferred measurement contract."
            )
    masks = experimental_measurement_masks(experimental_modes, experimental_node_ids)
    reference = masks[0]
    if any(not np.array_equal(mask, reference) for mask in masks[1:]):
        raise RegistrationRefusedError(
            "The measured-DOF mask differs between experimental modes; "
            "frozen-registration/1 stores one measurement contract per node."
        )
    return np.asarray(reference, dtype=bool).tolist()


def _registration_metrics(result: ComparisonResult) -> dict[str, Any]:
    geometry = result.geometry
    metrics: dict[str, Any] = {
        "orientation_source": result.metadata["orientation_source"],
        "normalized_rms_distance": geometry.normalized_rms_distance,
        "matched_fraction": geometry.matched_fraction,
        "coordinate_scale": geometry.coordinate_scale,
    }
    for key in _RESULT_METRIC_KEYS:
        if key in result.metadata:
            metrics[key] = result.metadata[key]
    transform = result.metadata.get("selected_geometry_transform", {})
    for key in _TRANSFORM_METRIC_KEYS:
        if key in transform:
            metrics[key] = transform[key]
    return _plain(metrics)


def build_frozen_registration(
    result: ComparisonResult,
    *,
    calibration: CoordinateCalibration,
    orientation_binding: Optional[Mapping[str, Any]] = None,
    experimental_source_identity: Optional[Mapping[str, Any]] = None,
) -> FrozenRegistration:
    """Freeze the registration a completed comparison actually used.

    ``calibration`` must be the calibration the comparison ran with.  A
    comparison whose orientation was user-confirmed requires the confirmation
    binding (as stored by the GUI); a supplied binding must be valid for the
    current source and calibration and name the comparison's own candidate.
    ``experimental_source_identity`` may inject a content identity when no
    real source file exists (tests, synthetic data).
    """
    calibration_state = calibration.to_dict()
    _require_comparison_calibration(result, calibration_state)
    source_identity = _source_identity(result, experimental_source_identity)
    candidate_id = _confirmed_candidate_id(
        result, orientation_binding, source_identity, calibration_state
    )

    experimental_modes = result.experimental.sorted_modes()
    fe_modes = result.abaqus.sorted_modes()
    if not experimental_modes or not fe_modes:
        raise RegistrationRefusedError("The comparison has no experimental or FE modes.")
    experimental_node_ids = experimental_modes[0].node_ids
    mapping = np.asarray(result.geometry.experimental_to_abaqus, dtype=int)
    if mapping.shape != (len(experimental_node_ids),):
        raise RegistrationRefusedError(
            "The geometry mapping does not cover the experimental reference nodes."
        )
    try:
        fe_geometry_identity = modal_dataset_geometry_identity(result.abaqus)
    except ValueError as error:
        raise RegistrationRefusedError(f"FE geometry identity unavailable: {error}") from error

    return FrozenRegistration.create(
        experimental_source_identity=source_identity,
        experimental_modal_set_identity=result.experimental.metadata.get("modal_set_key"),
        fe_geometry_identity=fe_geometry_identity,
        calibration=calibration_state,
        calibration_fingerprint=calibration_fingerprint(calibration_state),
        orientation_candidate_id=candidate_id,
        rotation=result.geometry.rotation,
        translation=result.geometry.translation,
        coordinate_scales=result.geometry.coordinate_scales,
        experimental_node_ids=experimental_node_ids,
        mapped_fe_node_ids=fe_modes[0].node_ids[mapping],
        measured_dof_contract=_measured_dof_contract(
            experimental_modes, experimental_node_ids
        ),
        registration_metrics=_registration_metrics(result),
    )
