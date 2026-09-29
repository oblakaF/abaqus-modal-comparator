"""Lossless serialization adapter from service output to evidence content.

No SVD, Fisher, covariance, precision, or threshold calculation is performed
here.  Every value is copied from an existing ``IdentifiabilityResult``.
"""

from __future__ import annotations

from collections.abc import Mapping

from services.identifiability_service import IdentifiabilityResult


def _finite_json_value(value: object) -> object:
    if hasattr(value, "tolist"):
        return _finite_json_value(value.tolist())
    if isinstance(value, Mapping):
        return {str(key): _finite_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_finite_json_value(item) for item in value)
    if isinstance(value, float):
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
        if value != value:
            return "NaN"
    if hasattr(value, "item"):
        return _finite_json_value(value.item())
    return value


def _subset_content(value: object) -> object:
    if value is None:
        return None
    return {
        "parameter_ids": tuple(value.parameter_ids),
        "singular_values": _finite_json_value(value.singular_values),
        "rank": value.rank,
        "condition_number": _finite_json_value(value.condition_number),
        "collinearity": {
            "parameter_ids": tuple(value.collinearity.parameter_ids),
            "gamma": _finite_json_value(value.collinearity.gamma),
            "minimum_eigenvalue": _finite_json_value(
                value.collinearity.minimum_eigenvalue
            ),
            "warning": value.collinearity.warning,
            "normalization": value.collinearity.normalization,
        },
        "minimum_singular_value": _finite_json_value(
            value.minimum_singular_value
        ),
        "normalized_minimum_singular_value": _finite_json_value(
            value.normalized_minimum_singular_value
        ),
        "admissible": value.admissible,
    }


def identifiability_evidence_content(
    result: IdentifiabilityResult,
    model_id: str,
) -> dict[str, object]:
    """Copy an identifiability result into deterministic evidence content."""

    if not isinstance(result, IdentifiabilityResult):
        raise TypeError("result must be an IdentifiabilityResult.")
    return {
        "uncertainty_model": model_id,
        "parameter_order": tuple(result.parameter_ids),
        "singular_values": _finite_json_value(result.singular_values),
        "numerical_rank": result.rank,
        "rank_tolerance": _finite_json_value(result.numerical_rank_tolerance),
        "condition_number": _finite_json_value(result.condition_number),
        "right_singular_vectors": _finite_json_value(
            result.right_singular_vectors
        ),
        "fisher_information": _finite_json_value(result.fisher_information),
        "covariance_proxy": _finite_json_value(result.covariance_proxy),
        "correlation_matrix": _finite_json_value(result.correlation_matrix),
        "collinearity": {
            "parameter_ids": tuple(result.collinearity.parameter_ids),
            "gamma": _finite_json_value(result.collinearity.gamma),
            "minimum_eigenvalue": _finite_json_value(
                result.collinearity.minimum_eigenvalue
            ),
            "warning": result.collinearity.warning,
            "normalization": result.collinearity.normalization,
        },
        "deficient_directions": tuple(
            {
                "singular_value": _finite_json_value(item.singular_value),
                "coefficients": _finite_json_value(item.coefficients),
                "parameter_loadings": _finite_json_value(item.parameter_loadings),
                "dominant_parameter": item.dominant_parameter,
                "dominant_loading": _finite_json_value(item.dominant_loading),
                "numerical_null_direction": item.numerical_null_direction,
            }
            for item in result.deficient_directions
        ),
        "best_identifiable_subset": _subset_content(
            result.best_identifiable_subset
        ),
        "subset_ranking": tuple(
            _subset_content(item) for item in result.subset_ranking
        ),
        "structurally_identifiable": result.structurally_identifiable,
        "directionally_separable": result.directionally_separable,
        "practically_precise_enough": result.practically_precise_enough,
        "overall_practical_identifiability": (
            result.overall_practical_identifiability
        ),
        "practically_identifiable": result.practically_identifiable,
        "precision_status": result.precision_status,
        "precision_assessments": tuple(
            {
                "parameter_id": item.parameter_id,
                "observability_status": item.observability_status,
                "observable_fraction": _finite_json_value(item.observable_fraction),
                "scaled_standard_deviation": _finite_json_value(
                    item.scaled_standard_deviation
                ),
                "transformed_coordinate": item.transformed_coordinate,
                "transformed_standard_deviation": _finite_json_value(
                    item.transformed_standard_deviation
                ),
                "physical_standard_deviation": _finite_json_value(
                    item.physical_standard_deviation
                ),
                "requirement_coordinate": item.requirement_coordinate,
                "maximum_standard_deviation": _finite_json_value(
                    item.maximum_standard_deviation
                ),
                "reference_scale": _finite_json_value(item.reference_scale),
                "achieved_fraction_of_reference": _finite_json_value(
                    item.achieved_fraction_of_reference
                ),
                "status": item.status,
                "reason": item.reason,
            }
            for item in result.precision_assessments
        ),
        "scaled_standard_deviations": _finite_json_value(
            result.scaled_standard_deviations
        ),
        "transformed_coordinate_ids": tuple(result.transformed_coordinate_ids),
        "transformed_standard_deviations": _finite_json_value(
            result.transformed_standard_deviations
        ),
        "physical_standard_deviations": _finite_json_value(
            result.physical_standard_deviations
        ),
        "observable_projector": _finite_json_value(result.observable_projector),
        "nullspace_basis": _finite_json_value(result.nullspace_basis),
        "parameter_observability": dict(result.parameter_observability),
        "warnings": tuple(result.warnings),
        "weighting_mode": result.weighting_mode,
    }


__all__ = ["identifiability_evidence_content"]
