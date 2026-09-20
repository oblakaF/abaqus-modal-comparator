"""Structured, deterministic scientific reporting for Stage-A identification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import json
import math
from typing import Any, Mapping, Sequence, Tuple

import numpy as np

from domain.specimen import PhysicalSpecimen

from .stage_a_identification_service import StageAIdentificationResult
from .uncertainty_service import (
    APPARENT_FLEXURAL_LABEL,
    CoverageValidationResult,
    LocalCovarianceDiagnostic,
    MonteCarloResult,
    QuantityStatistics,
    apparent_flexural_properties,
)


APPARENT_FLEXURAL_NOTE = (
    "These are apparent flexural properties derived from bending stiffness. "
    "They are not automatically equal to membrane properties."
)


def _primitive(value: Any) -> Any:
    if is_dataclass(value):
        return _primitive(asdict(value))
    if isinstance(value, np.ndarray):
        return _primitive(value.tolist())
    if isinstance(value, np.generic):
        return _primitive(value.item())
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0 else "-Infinity" if value < 0 else "NaN"
    return value


def _statistics_dict(statistics: QuantityStatistics) -> Mapping[str, Any]:
    return _primitive(statistics)


@dataclass(frozen=True)
class StageAReport:
    specimen_identity: Mapping[str, Any]
    observation_budget: Mapping[str, Any]
    fitted_subset: Tuple[str, ...]
    identified_section_properties: Mapping[str, Any]
    identifiability_summary: Mapping[str, Any]
    inverse_fit_summary: Mapping[str, Any]
    uncertainty_summary: Mapping[str, Any]
    derived_apparent_flexural_properties: Mapping[str, Any]
    excluded_modes: Tuple[Mapping[str, Any], ...]
    clusters: Tuple[Mapping[str, Any], ...]
    pairing_warnings: Tuple[str, ...]
    coverage_validation: Mapping[str, Any] | None
    assumptions: Tuple[str, ...]
    warnings: Tuple[str, ...]
    local_covariance_comparison: Mapping[str, Any] | None = None
    schema_version: str = "stage-a-report/1.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Mapping[str, Any]:
        return _primitive(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, indent=indent, ensure_ascii=False, allow_nan=False
        ) + "\n"

    @classmethod
    def from_json(cls, payload: str) -> "StageAReport":
        data = json.loads(payload)
        data["fitted_subset"] = tuple(data["fitted_subset"])
        data["excluded_modes"] = tuple(data["excluded_modes"])
        data["clusters"] = tuple(data["clusters"])
        data["pairing_warnings"] = tuple(data["pairing_warnings"])
        data["assumptions"] = tuple(data["assumptions"])
        data["warnings"] = tuple(data["warnings"])
        return cls(**data)

    def to_markdown(self) -> str:
        return render_stage_a_report(self)


def _format_value(value: Any, precision: int = 6) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, (int, float)):
        return f"{float(value):.{precision}g}"
    return str(value)


def _thickness_metres(specimen: PhysicalSpecimen) -> float:
    measurement = next(
        (item for item in specimen.primary_measurements if item.name == "h"), None
    )
    if measurement is None:
        raise ValueError("Stage-A report requires primary thickness measurement 'h'.")
    factors = {"": 1.0, "m": 1.0, "mm": 1.0e-3, "um": 1.0e-6, "µm": 1.0e-6}
    unit = measurement.unit.strip().lower()
    if unit not in factors:
        raise ValueError(f"Unsupported thickness unit {measurement.unit!r}.")
    return float(measurement.value) * factors[unit]


def build_stage_a_report(
    identification: StageAIdentificationResult,
    specimen: PhysicalSpecimen,
    monte_carlo: MonteCarloResult,
    *,
    coverage_validation: CoverageValidationResult | None = None,
    local_covariance: LocalCovarianceDiagnostic | None = None,
) -> StageAReport:
    """Assemble one audit-ready report without performing PDF/Excel rendering."""

    inverse = identification.inverse_result
    fitted = dict(inverse.fixed_parameters)
    fitted.update(inverse.fitted_parameters)
    h_m = _thickness_metres(specimen)
    point_apparent = apparent_flexural_properties(
        fitted["D11"], fitted["D12"], fitted["D66"], h_m
    )
    identified = {
        name: {
            "point_estimate": float(fitted[name]),
            "monte_carlo": (
                _statistics_dict(monte_carlo.identified_statistics[name])
                if name in monte_carlo.identified_statistics
                else None
            ),
            "unit": "N·m",
        }
        for name in ("D11", "D12", "D66")
    }
    derived = {
        "label": APPARENT_FLEXURAL_LABEL,
        "note": APPARENT_FLEXURAL_NOTE,
        "E_flex": {
            "point_estimate": point_apparent.E_flex,
            "monte_carlo": _statistics_dict(monte_carlo.derived_statistics["E_flex"])
            if "E_flex" in monte_carlo.derived_statistics else None,
            "unit": "Pa",
        },
        "G12_flex": {
            "point_estimate": point_apparent.G12_flex,
            "monte_carlo": _statistics_dict(monte_carlo.derived_statistics["G12_flex"])
            if "G12_flex" in monte_carlo.derived_statistics else None,
            "unit": "Pa",
        },
        "nu12_flex": {
            "point_estimate": point_apparent.nu12_flex,
            "monte_carlo": _statistics_dict(monte_carlo.derived_statistics["nu12_flex"])
            if "nu12_flex" in monte_carlo.derived_statistics else None,
            "unit": "dimensionless",
        },
        "thickness_m": h_m,
        "thickness_variance_diagnostics": _primitive(monte_carlo.thickness_diagnostics),
    }
    correlation = None
    parameter_ids = identification.identifiability.parameter_ids
    if "D12" in parameter_ids and "D66" in parameter_ids:
        i = parameter_ids.index("D12")
        j = parameter_ids.index("D66")
        correlation = float(identification.identifiability.correlation_matrix[i, j])
    weak_directions = tuple(
        {
            "singular_value": float(item.singular_value),
            "dominant_parameter": item.dominant_parameter,
            "parameter_loadings": _primitive(item.parameter_loadings),
            "numerical_null_direction": item.numerical_null_direction,
        }
        for item in identification.identifiability.deficient_directions
    )
    identifiability = {
        "rank": identification.identifiability.rank,
        "parameter_count": len(parameter_ids),
        "condition_number": identification.identifiability.condition_number,
        "gamma": identification.identifiability.collinearity.gamma,
        "practically_identifiable": identification.identifiability.practically_identifiable,
        "D12_D66_correlation": correlation,
        "weak_directions": weak_directions,
        "recommended_subset": identification.recommended_parameter_subset,
        "weighting_mode": identification.identifiability.weighting_mode,
    }
    excluded_modes = tuple(
        {
            "observation_id": item.observation_id,
            "status": item.status,
            "reason": item.reason,
        }
        for item in identification.excluded_observations
    )
    clusters = tuple(
        {
            "cluster_id": item.cluster_id,
            "observation_ids": item.observation_ids,
            "status": item.inclusion_status.value,
            "reason": item.reason,
        }
        for item in identification.clusters
    )
    uncertainty_by_mode = {
        item.observation_id: {
            "sigma_measurement": item.uncertainty.measurement,
            "sigma_setup": item.uncertainty.setup,
            "sigma_manufacturing": item.uncertainty.manufacturing,
        }
        for item in identification.observations
    }
    local_comparison = None
    if local_covariance is not None:
        local_comparison = {
            "diagnostic_only": True,
            "method": local_covariance.method,
            "local_intervals_95": _primitive(local_covariance.intervals_95),
            "monte_carlo_intervals_95": {
                name: list(stats.interval_95)
                for name, stats in monte_carlo.identified_statistics.items()
            },
        }
    assumptions = tuple(
        dict.fromkeys(
            monte_carlo.assumptions
            + (APPARENT_FLEXURAL_NOTE,)
            + tuple(str(item) for item in identification.metadata.get("assumptions", ()))
        )
    )
    warnings = tuple(
        dict.fromkeys(identification.warnings + monte_carlo.warnings)
    )
    pairing_warnings = tuple(
        item for item in warnings if "pair" in item.lower() or "comparator" in item.lower()
    )
    return StageAReport(
        specimen_identity={
            "physical_specimen_id": specimen.physical_specimen_id,
            "design_id": specimen.design_id,
            "test_run_ids": sorted({item.test_run_id for item in identification.observations}),
        },
        observation_budget={
            "raw": len(identification.observations),
            "excluded": len(identification.excluded_observations),
            "clusters": len(identification.clusters),
            "cluster_members": sum(item.cluster_size for item in identification.clusters),
            "effective": identification.effective_observation_count,
        },
        fitted_subset=identification.fitted_parameter_subset,
        identified_section_properties=identified,
        identifiability_summary=identifiability,
        inverse_fit_summary={
            "objective_initial": inverse.objective_initial,
            "objective_final": inverse.objective_final,
            "success": inverse.success,
            "global_success": inverse.global_success,
            "global_stage_acceptable": inverse.global_stage_acceptable,
            "local_success": inverse.local_success,
            "pairing_changed_at_optimum": inverse.pairing_changed_at_optimum,
            "residuals_final": inverse.residuals_final,
            "observation_ids": inverse.observation_ids,
        },
        uncertainty_summary={
            "per_mode_components": uncertainty_by_mode,
            "monte_carlo_samples": len(monte_carlo.samples),
            "successful_samples": monte_carlo.successful_sample_count,
            "failed_samples": monte_carlo.failed_sample_count,
            "convergence_fraction": monte_carlo.convergence_fraction,
            "final_intervals": "Monte Carlo percentile intervals",
        },
        derived_apparent_flexural_properties=derived,
        excluded_modes=excluded_modes,
        clusters=clusters,
        pairing_warnings=pairing_warnings,
        coverage_validation=_primitive(coverage_validation) if coverage_validation else None,
        assumptions=assumptions,
        warnings=warnings,
        local_covariance_comparison=local_comparison,
        metadata={
            "stage": "A",
            "report_format": "structured scientific result",
            "pdf_exported": False,
            "excel_exported": False,
        },
    )


def render_stage_a_report(report: StageAReport) -> str:
    """Render stable human-readable Markdown from the structured report."""

    lines = ["# STAGE-A SCIENTIFIC REPORT", "", "## IDENTIFIED SECTION PROPERTIES"]
    for name in ("D11", "D12", "D66"):
        item = report.identified_section_properties[name]
        interval = None if item["monte_carlo"] is None else item["monte_carlo"]["interval_95"]
        suffix = "" if interval is None else f"; 95% CI [{_format_value(interval[0])}, {_format_value(interval[1])}]"
        lines.append(f"- {name} = {_format_value(item['point_estimate'])} N·m{suffix}")
    ident = report.identifiability_summary
    lines.extend(
        [
            "",
            "## IDENTIFIABILITY",
            f"- Rank: {ident['rank']} / {ident['parameter_count']}",
            f"- Condition number: {_format_value(ident['condition_number'])}",
            f"- Collinearity gamma: {_format_value(ident['gamma'])}",
            f"- Fitted subset: {', '.join(report.fitted_subset)}",
            "",
            f"## DERIVED {APPARENT_FLEXURAL_LABEL}",
        ]
    )
    derived = report.derived_apparent_flexural_properties
    for name in ("E_flex", "G12_flex"):
        item = derived[name]
        value_gpa = float(item["point_estimate"]) / 1.0e9
        interval = None if item["monte_carlo"] is None else item["monte_carlo"]["interval_95"]
        suffix = "" if interval is None else f"; 95% CI [{interval[0] / 1.0e9:.6g}, {interval[1] / 1.0e9:.6g}] GPa"
        lines.append(f"- {name} = {value_gpa:.6g} GPa{suffix}")
    lines.append(f"- nu12_flex = {_format_value(derived['nu12_flex']['point_estimate'])}")
    lines.extend(["", f"> NOTE: {APPARENT_FLEXURAL_NOTE}", "", "## OBSERVATION BUDGET"])
    budget = report.observation_budget
    lines.append(
        "- Raw {raw}; excluded {excluded}; clusters {clusters}; effective {effective}.".format(**budget)
    )
    uncertainty = report.uncertainty_summary
    lines.extend(
        [
            "",
            "## UNCERTAINTY",
            f"- Monte Carlo samples: {uncertainty['monte_carlo_samples']}",
            f"- Successful: {uncertainty['successful_samples']}; failed: {uncertainty['failed_samples']}",
            f"- Convergence: {uncertainty['convergence_fraction']:.1%}",
            "- Reported intervals: Monte Carlo percentile intervals.",
            "",
            "## DIAGNOSTICS",
            f"- Pairing changed at optimum: {report.inverse_fit_summary['pairing_changed_at_optimum']}",
        ]
    )
    if report.coverage_validation is not None:
        lines.append(
            f"- Level-1 coverage validation passed: {report.coverage_validation['passed']}"
        )
    for warning in report.warnings:
        lines.append(f"- Warning: {warning}")
    lines.extend(["", "## ASSUMPTIONS"])
    lines.extend(f"- {item}" for item in report.assumptions)
    return "\n".join(lines) + "\n"


def report_to_json(report: StageAReport, *, indent: int = 2) -> str:
    return report.to_json(indent=indent)


def report_from_json(payload: str) -> StageAReport:
    return StageAReport.from_json(payload)


__all__ = [
    "APPARENT_FLEXURAL_NOTE",
    "StageAReport",
    "build_stage_a_report",
    "render_stage_a_report",
    "report_from_json",
    "report_to_json",
]
