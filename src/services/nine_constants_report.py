"""Nine-constant report contract — research track NINE-EC (Phase H). RESEARCH_DIAGNOSTIC_ONLY.

One machine-readable record (``research/nine-constants-report/v1``) with nine rows, plus CSV and text renderings.
Value classes are never mixed:

1. INPUT_CONSTANT — the value read from the INP (the "Input value" column, always);
2. ASSUMED_FIXED — a constant declared fixed for the question (input value kept, NOT identified);
3. DIAGNOSTIC_CANDIDATE — not used: an optimiser point that failed a gate is never published;
4. EVIDENCE_SUPPORTED_RESEARCH_ESTIMATE — an estimated value with uncertainty, only for status
   SUPPORTED_RESEARCH_ESTIMATE of a completed research estimation (still RESEARCH_DIAGNOSTIC_ONLY);
5. GOVERNED_MATERIAL_PROPERTY — never produced by this track (requires the governed Auto-ID path).

A fixed or input constant never appears in the estimated-value field; a refusal has no estimated values; no INP is
written by this module (no calibrated nine-constant INP exists in this research track).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Mapping, Optional, Sequence

from domain.orthotropic_elasticity import COORDINATE_UNITS, COORDINATES, NAMES, CoordinateKind

from .nine_constants_engine import (
    CLAIM_LABELS,
    ConstantStatus,
    EstimationResult,
    FECostPlan,
    IdentifiabilityAssessment,
    ObservationRow,
)

REPORT_SCHEMA = "research/nine-constants-report/v1"
GOVERNED_STATUS = "NOT_EVALUATED (no governed nine-constant material-identification path exists; SPEC v1.2 §5, §5.2)"
STATUS_TEXT = {
    "SUPPORTED_RESEARCH_ESTIMATE": "supported research estimate",
    "NOT_IDENTIFIABLE": "not identifiable",
    "NOT_EVALUATED": "not evaluated",
    "FIXED_INPUT_NOT_IDENTIFIED": "fixed input value, NOT identified",
    "POLICY_OR_EVIDENCE_BLOCKER": "scientific policy / evidence blocker",
    "INVALID_OR_UNSUPPORTED_MODEL": "invalid or unsupported model",
}
UNSPECIFIED_STRESS_UNITS = "INP stress units (unspecified)"  # an INP declares no stress unit; never inferred
POISSON_UNITS = "dimensionless"


def stress_units_record(stress_units: Optional[str] = None, source: str = "USER_SUPPLIED") -> dict:
    """The unit of E and G: an explicit declaration (with its source) or the unspecified INP stress unit."""
    if stress_units is None:
        return {"label": UNSPECIFIED_STRESS_UNITS, "source": "NOT_DECLARED",
                "statement": "the INP does not declare a stress unit; moduli are in the INP's own consistent units"}
    if not isinstance(stress_units, str) or not stress_units.strip():
        raise ValueError("a declared stress unit must be a non-empty text.")
    return {"label": stress_units.strip(), "source": source}


def units(stress_units: Mapping) -> dict[str, str]:
    return {name: (POISSON_UNITS if name[0] == "n" else stress_units["label"]) for name in NAMES}


def _uncertainty(name: str, sd: Optional[float], value: Optional[float]) -> Optional[dict]:
    if sd is None or value is None:
        return None
    if COORDINATES[name] is CoordinateKind.LOG:
        return {"sd": sd, "units": "ln p", "relative_percent": (math.exp(sd) - 1.0) * 100.0,
                "basis": "statistical_sd at the estimate (M5 posterior, explicit Σ); no Birge / model-form envelope"}
    return {"sd": sd, "units": "absolute ν", "basis": "statistical_sd at the estimate (M5 posterior, explicit Σ)"}


def nine_rows(input_constants: Optional[Mapping[str, float]], assessment: Optional[IdentifiabilityAssessment],
              estimation: Optional[EstimationResult], blanket_status: Optional[str] = None,
              blanket_reason: Optional[str] = None, stress_units: Optional[Mapping] = None) -> list[dict]:
    """Exactly nine rows, in record order. Estimated values only from a completed research estimation."""
    unit_of = units(stress_units or stress_units_record())
    final = None
    if estimation is not None and estimation.status == "ESTIMATED_RESEARCH":
        final = estimation.final_assessment
    source = final or (estimation.final_assessment if estimation is not None and estimation.final_assessment
                       else None) or (estimation.gate if estimation is not None else None) or assessment
    rows = []
    for name in NAMES:
        item = None if source is None else source.constants.get(name)
        status = blanket_status or (item.status.value if item is not None else ConstantStatus.NOT_EVALUATED.value)
        reasons = [blanket_reason] if blanket_reason else (list(item.reasons) if item is not None else
                                                           ["no assessment"])
        estimated = None
        if final is not None and item is not None and status == ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE.value:
            estimated = item.estimate
        if status == ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE.value and estimated is None:
            status = ConstantStatus.NOT_EVALUATED.value  # identifiable alone, but no estimate exists: never shown as one
            why = "; ".join(estimation.reasons) if estimation is not None and estimation.reasons else (
                "no estimation was run")
            reasons = reasons + [f"identifiable at the start point, but no value was estimated ({why}); a narrower "
                                 "question must be declared explicitly to estimate it"]
        fixed = status == ConstantStatus.FIXED_INPUT_NOT_IDENTIFIED.value
        rows.append({
            "constant": name, "units": unit_of[name], "coordinate": COORDINATE_UNITS[name],
            "input_value": None if input_constants is None else input_constants.get(name),
            "input_value_class": "ASSUMED_FIXED" if fixed else "INPUT_CONSTANT",
            "estimated_value": estimated,
            "estimated_value_class": "EVIDENCE_SUPPORTED_RESEARCH_ESTIMATE" if estimated is not None else None,
            "uncertainty": _uncertainty(name, None if item is None else item.sd, estimated),
            "status": status, "status_text": STATUS_TEXT[status], "reasons": reasons,
            "q_residual_information": None if item is None else item.q,
            "null_space_weight": None if item is None else item.null_space_weight,
            "governed_material_property": GOVERNED_STATUS,
        })
    return rows


def headline(rows: Sequence[Mapping], refusals: Sequence[str]) -> str:
    supported = [r["constant"] for r in rows if r["estimated_value"] is not None]
    if len(supported) == 9:
        return "Research estimate for all nine constants (RESEARCH_DIAGNOSTIC_ONLY; NOT a validated material property)."
    if supported:
        return (f"Research estimate for {', '.join(supported)} only; the other constants are not determined by this "
                "evidence (RESEARCH_DIAGNOSTIC_ONLY).")
    reason = refusals[0] if refusals else "the evidence does not determine the constants"
    return f"No constant can be determined from this evidence: {reason}."


def build_report(*, question: str, inputs: Mapping, model: Optional[Mapping], experiment: Optional[Mapping],
                 registration: Optional[Mapping], observations: Sequence[ObservationRow],
                 assessment: Optional[IdentifiabilityAssessment], estimation: Optional[EstimationResult],
                 fe_plan: Optional[FECostPlan], fe_provenance: Optional[Mapping],
                 effective_model_reference: Optional[Mapping], refusals: Sequence[str],
                 synthetic: Optional[Mapping] = None, blanket_status: Optional[str] = None,
                 blanket_reason: Optional[str] = None, nuisance_assumptions: Sequence[str] = (),
                 stress_units: Optional[Mapping] = None) -> dict:
    """``stress_units``: a ``stress_units_record`` of an explicit declaration; default: unspecified INP units."""
    stress_units = dict(stress_units or stress_units_record())
    input_constants = None if model is None else model.get("constants")
    rows = nine_rows(input_constants, assessment, estimation, blanket_status, blanket_reason, stress_units)
    source = (estimation.final_assessment if estimation is not None and estimation.final_assessment is not None
              else estimation.gate if estimation is not None else assessment)
    fit = [r for r in observations if r.role.value == "FIT"]
    holdout = [r for r in observations if r.role.value == "HOLDOUT"]
    all_refusals = list(refusals) + ([] if source is None else list(source.refusal_reasons)) + (
        [] if estimation is None else list(estimation.reasons))
    record = {
        "schema": REPORT_SCHEMA,
        "claim": list(CLAIM_LABELS),
        "claim_classification": {
            "material_property_identification": GOVERNED_STATUS,
            "effective_fe_model_calibration": ("separate (see effective_model_reference); never converted from a "
                                               "refusal of this analysis"),
            "this_record": "C. diagnostic sensitivity / identifiability analysis (research)",
        },
        "question": question,
        "headline": headline(rows, all_refusals),
        "inputs": dict(inputs),
        "model": None if model is None else dict(model),
        "experiment": None if experiment is None else dict(experiment),
        "registration": dict(registration) if registration else {"status": "NOT_AVAILABLE"},
        "observations": {"accepted_fit": len(fit), "holdout": len(holdout),
                         "fit_families": len({r.family_key for r in fit}),
                         "holdout_families": len({r.family_key for r in holdout} - {r.family_key for r in fit}),
                         "rows": [r.to_dict() for r in observations],
                         "rank_upper_bound": len(fit)},
        "units": {"moduli": stress_units, "poisson_ratios": POISSON_UNITS},
        "constants": rows,
        "identifiability": None if source is None else source.to_dict(),
        "estimation": None if estimation is None else {k: v for k, v in estimation.to_dict().items()
                                                       if k not in ("gate", "final_assessment")},
        "uncertainty_basis": {"available": "statistical_sd from the M5 posterior with the explicit Σ",
                              "unavailable": ["Σ_meas / Σ_setup of a real experiment (synthetic or not provided)",
                                              "birge_adjusted_sd and pattern test", "model_form_robustness (LOO)",
                                              "conservative envelope (SPEC §9)"]},
        "nuisance_assumptions": list(nuisance_assumptions) or [
            "no nuisance parameters in the system: core, adhesive, thickness and interface are assumed exactly known "
            "(synthetic) or not assessed (real data) — a real specimen needs explicit evidence-backed priors"],
        "fe_cost_plan": None if fe_plan is None else fe_plan.to_dict(),
        "fe_provenance": None if fe_provenance is None else dict(fe_provenance),
        "effective_model_reference": None if effective_model_reference is None else dict(effective_model_reference),
        "refusal_reasons": all_refusals,
        "synthetic": None if synthetic is None else dict(synthetic),
        "calibrated_inp": "NOT_PRODUCED (no calibrated nine-constant INP writer exists in this research track)",
    }
    record["report_hash"] = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
    return record


def report_csv(report: Mapping) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["constant", "units", "input_value", "estimated_value", "uncertainty_sd", "uncertainty_units",
                     "status", "reasons"])
    for row in report["constants"]:
        u = row["uncertainty"] or {}
        writer.writerow([row["constant"], row["units"], row["input_value"], row["estimated_value"], u.get("sd"),
                         u.get("units"), row["status"], " | ".join(row["reasons"])])
    return out.getvalue()


def _value(value) -> str:
    if value is None:
        return "-"
    return f"{value:,.6g}" if abs(value) >= 1 else f"{value:.4g}"


def report_text(report: Mapping) -> str:
    lines = ["NINE ORTHOTROPIC ENGINEERING CONSTANTS - " + " / ".join(report["claim"]),
             "=" * 96, report["headline"], ""]
    if report.get("synthetic"):
        lines += [f"SYNTHETIC: {report['synthetic'].get('label', 'synthetic test evidence')}", ""]
    model = report.get("model") or {}
    if model:
        lines.append(f"Material: {model.get('material')} ({model.get('model_kind')}); INP SHA-256 "
                     f"{str(model.get('source_sha256', ''))[:16]}")
    obs = report["observations"]
    lines.append(f"Accepted observations: {obs['accepted_fit']} FIT ({obs['fit_families']} families), "
                 f"{obs['holdout']} HOLDOUT; the sensitivity system has rank <= {obs['rank_upper_bound']}.")
    moduli = report["units"]["moduli"]
    lines.append(f"Units: E and G in {moduli['label']} (source: {moduli['source']}); Poisson ratios "
                 f"{report['units']['poisson_ratios']}.")
    lines += ["", f"{'Constant':<8} {'Input':>12} {'Estimated':>12} {'Uncertainty':>14}  {'Units':<32} Status",
              "-" * 96]
    for row in report["constants"]:
        u = row["uncertainty"]
        if u is None:
            unc = "-"
        elif u["units"] == "ln p":
            unc = f"±{u['relative_percent']:.2f} %"
        else:
            unc = f"±{u['sd']:.3g}"
        lines.append(f"{row['constant']:<8} {_value(row['input_value']):>12} {_value(row['estimated_value']):>12} "
                     f"{unc:>14}  {row['units']:<32} {row['status_text']}")
    lines += ["", "Why:"]
    for row in report["constants"]:
        lines.append(f"  {row['constant']}: " + "; ".join(row["reasons"]))
    if report.get("effective_model_reference"):
        ref = report["effective_model_reference"]
        lines += ["", "Separate effective FE-model calibration (question B, NOT a material property, not a per-constant "
                  "result):", "  " + json.dumps(ref, ensure_ascii=False)]
    plan = report.get("fe_cost_plan")
    if plan:
        lines += ["", f"FE evaluations for {plan['estimated_constants']} constants: identifiability gate "
                  f"{plan['required_new_minimum']}, a complete research estimation {plan['required_new_typical_range'][0]}"
                  f"-{plan['required_new_typical_range'][1]} (verified cached: {plan['verified_cached_evaluations']})."]
        if plan.get("resources"):
            r = plan["resources"]
            lines.append(f"  {r['statement']}: {r['hours_range'][0]}-{r['hours_range'][1]} h, "
                         f"{r['disk_gb_range_without_cleanup'][0]}-{r['disk_gb_range_without_cleanup'][1]} GB without "
                         f"cleanup ({r['basis']}).")
    if report["refusal_reasons"]:
        lines += ["", "Refusal / blocker reasons:"] + [f"  - {r}" for r in report["refusal_reasons"]]
    lines += ["", f"Governed material property: {GOVERNED_STATUS}", f"Calibrated INP: {report['calibrated_inp']}"]
    return "\n".join(lines) + "\n"


def write_report(report: Mapping, folder: Path) -> dict[str, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {"json": folder / "nine_constants_report.json", "csv": folder / "nine_constants_report.csv",
             "text": folder / "nine_constants_report.txt"}
    paths["json"].write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    paths["csv"].write_text(report_csv(report), encoding="utf-8")
    paths["text"].write_text(report_text(report), encoding="utf-8")
    return paths
