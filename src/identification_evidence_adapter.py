"""Lossless serialization of inverse identification output as evidence content.

This adapter copies an already-computed ``InverseIdentificationResult``.  It
does not select an optimizer, evaluate residuals, or perform any scientific
calculation.
"""

from __future__ import annotations

from collections.abc import Mapping

from services.inverse_solver import InverseIdentificationResult, PairingResult


def _json_value(value: object) -> object:
    if hasattr(value, "tolist"):
        return _json_value(value.tolist())
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_json_value(item) for item in value)
    if isinstance(value, float):
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
        if value != value:
            return "NaN"
    if hasattr(value, "item"):
        return _json_value(value.item())
    return value


def _pairing_content(pairing: PairingResult) -> dict[str, object]:
    return {
        "assignments": tuple(
            {
                "observation_id": item.observation_id,
                "fe_mode_id": item.fe_mode_id,
                "mac": _json_value(item.mac),
                "tracking_mac": _json_value(item.tracking_mac),
            }
            for item in pairing.assignments
        ),
        "method": pairing.method,
        "warnings": tuple(pairing.warnings),
    }


def identification_evidence_content(
    result: InverseIdentificationResult,
    *,
    model_id: str,
    parameter_unit: str,
    uncertainty: Mapping[str, object],
) -> dict[str, object]:
    """Copy one externally produced inverse result into deterministic content."""

    if not isinstance(result, InverseIdentificationResult):
        raise TypeError("result must be an InverseIdentificationResult.")
    if not isinstance(uncertainty, Mapping):
        raise TypeError("uncertainty must be a mapping.")

    inverse_result = {
        "fitted_parameters": _json_value(result.fitted_parameters),
        "fixed_parameters": _json_value(result.fixed_parameters),
        "transformed_parameters": _json_value(result.transformed_parameters),
        "initial_parameters": _json_value(result.initial_parameters),
        "objective_initial": _json_value(result.objective_initial),
        "objective_global": _json_value(result.objective_global),
        "objective_final": _json_value(result.objective_final),
        "residuals_initial": _json_value(result.residuals_initial),
        "residuals_final": _json_value(result.residuals_final),
        "predicted_frequencies_initial": _json_value(
            result.predicted_frequencies_initial
        ),
        "predicted_frequencies_final": _json_value(
            result.predicted_frequencies_final
        ),
        "experimental_frequencies": _json_value(result.experimental_frequencies),
        "observation_ids": tuple(result.observation_ids),
        "global_evaluations": result.global_evaluations,
        "global_optimizer_evaluations": result.global_optimizer_evaluations,
        "local_iterations": result.local_iterations,
        "convergence_history": tuple(
            {
                "stage": item.stage,
                "evaluation": item.evaluation,
                "transformed_parameters": _json_value(
                    item.transformed_parameters
                ),
                "physical_parameters": _json_value(item.physical_parameters),
                "objective": _json_value(item.objective),
                "success": item.success,
                "pairing_signature": tuple(item.pairing_signature),
                "message": item.message,
            }
            for item in result.convergence_history
        ),
        "pairing_changed_at_optimum": result.pairing_changed_at_optimum,
        "initial_pairing": _pairing_content(result.initial_pairing),
        "global_pairing": _pairing_content(result.global_pairing),
        "final_pairing": _pairing_content(result.final_pairing),
        "excluded_observations": tuple(
            {
                "observation_id": item.observation_id,
                "status": item.status,
                "reason": item.reason,
            }
            for item in result.excluded_observations
        ),
        "warnings": tuple(result.warnings),
        "identifiability_metadata_reference": (
            result.identifiability_metadata_reference
        ),
        "weighting_mode": result.weighting_mode,
        "global_success": result.global_success,
        "global_stage_acceptable": result.global_stage_acceptable,
        "global_message": result.global_message,
        "local_success": result.local_success,
        "local_message": result.local_message,
        "success": result.success,
    }
    return {
        "identified_properties": {
            "models": {
                model_id: {
                    "properties_MPa": _json_value(result.fitted_parameters),
                    "parameter_unit": parameter_unit,
                    "uncertainty": _json_value(uncertainty),
                }
            }
        },
        "inverse_result": inverse_result,
    }


__all__ = ["identification_evidence_content"]
