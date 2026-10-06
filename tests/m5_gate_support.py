"""Explicit synthetic M5 stage-gate cases and the M4.9 twin records-based control (no Abaqus).

Every synthetic case defines its sensitivities, Σ, priors, residuals, families, holdouts and guard
evidence explicitly, including `registration_limited = false`. The constants here are synthetic case
definitions and test tolerances, not physical policy (M5_DECISION_RECORD §1, §19).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from services.identification_uncertainty import ResidualTerm, residual_terms
from services.identification_verdict import (
    EvidenceState,
    GuardEvidence,
    NuisanceConstraint,
    SandwichG12Evidence,
    VerdictContext,
    VerdictInputs,
    compute_evidence_chain,
    fitting_pair_mac_evidence,
)
from services.practical_identifiability import (
    G12_PARAMETER,
    NuisancePrior,
    ObservationCovariance,
    ParameterDefinition,
    ParameterRole,
    assemble_system,
    build_sensitivity_matrix,
    diagonal_component,
    reconstruct_lm_jacobian,
)


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = "explicit synthetic M5 gate case definition"
E = ParameterDefinition("E_in_plane_mpa", ParameterRole.GLOBAL)
G = ParameterDefinition(G12_PARAMETER, ParameterRole.GLOBAL)
K = ParameterDefinition("k_core", ParameterRole.NUISANCE, "SYN")
P_HAT = {"E_in_plane_mpa": 45000.0, G12_PARAMETER: 4000.0, "k_core": 1.0}

# Twelve explicit synthetic fit rows: (S_E, S_G12, S_k) and whitened residuals at p̂ (small, mixed signs).
ROWS = {f"R{k}": v for k, v in enumerate([
    (0.48, 0.02, 0.010), (0.32, 0.18, 0.012), (0.42, 0.08, 0.009), (0.36, 0.14, 0.015), (0.50, 0.00, 0.011),
    (0.30, 0.20, 0.014), (0.44, 0.05, 0.010), (0.38, 0.12, 0.013), (0.46, 0.04, 0.012), (0.34, 0.16, 0.011),
    (0.40, 0.10, 0.010), (0.31, 0.19, 0.014)], start=1)}
RESIDUALS = dict(zip(ROWS, [0.6, -0.4, 0.9, -1.1, 0.2, 0.5, -0.7, 0.3, -0.2, 1.0, -0.8, 0.1]))
FAMILIES = {row: f"F{i}" for i, row in enumerate(ROWS, start=1)}
HOLDOUTS = {"H1": ("TORSION", 0.4), "H2": ("VALIDATION", -0.9)}


def synthetic_guards(**changes):
    guards = {
        "fitting_pair_mac": fitting_pair_mac_evidence({row: 0.99 for row in ROWS}, SYNTHETIC),
        "registration": GuardEvidence("registration", EvidenceState.PASS, SYNTHETIC, "registration_limited = false"),
        "peak_derived_input": GuardEvidence("peak_derived_input", EvidenceState.PASS, SYNTHETIC, "no peak-derived modes"),
        "tracking": GuardEvidence("tracking", EvidenceState.PASS, SYNTHETIC, "no branch or pairing loss"),
        "family_consistency": GuardEvidence("family_consistency", EvidenceState.NOT_AVAILABLE, SYNTHETIC,
                                            "single-specimen synthetic case (D-044)"),
    }
    guards.update(changes)
    return guards


def sandwich(independent=True, synthetic_definition=True, provisional=False, bare_plate=EvidenceState.NOT_AVAILABLE,
             applies=True):
    return SandwichG12Evidence(applies, bare_plate, ("k_core",), {"k_core": NuisanceConstraint(
        "k_core", independent, provisional, synthetic_definition, SYNTHETIC)}, SYNTHETIC)


def build(parameters=(E, G, K), rows=ROWS, residuals=RESIDUALS, families=FAMILIES, holdouts=HOLDOUTS,
          priors=(NuisancePrior("k_core", 0.0, 0.05, SYNTHETIC, False),), sigma=0.003, p_hat=P_HAT,
          context=VerdictContext.SYNTHETIC_GATE, sandwich_evidence=None, label="synthetic", clusters=(),
          upstream=(), **guard_changes):
    ids = [p.parameter_id for p in parameters]
    data = {r: dict(zip(ids, values[:len(ids)] if len(values) >= len(ids) else values)) for r, values in rows.items()}
    clustered = {m for c in clusters for m in c}
    singles = [r for r in rows if r not in clustered]
    m = build_sensitivity_matrix(data, singles, clusters, parameters, {p: SYNTHETIC for p in ids})
    covariance = ObservationCovariance(m.term_ids, (diagonal_component("synthetic_measurement", m.term_ids,
                                                                       {t: sigma for t in m.term_ids}, False,
                                                                       SYNTHETIC),))
    system = assemble_system(m, covariance, priors)
    fit = residual_terms(singles, clusters, [residuals[r] for r in singles] +
                         [residuals[c[0]] for c in clusters], families)
    held = [ResidualTerm(k, (k,), f, v) for k, (f, v) in holdouts.items()]
    p_hat = {k: p_hat[k] for k in ids}
    chain = compute_evidence_chain(system, fit, held, p_hat, f"{label}: {SYNTHETIC}")
    guards = synthetic_guards(**guard_changes)
    inputs = VerdictInputs(context, label, chain.analysis, chain.statistical, chain.pattern, chain.birge,
                           chain.robustness, guards["fitting_pair_mac"], guards["registration"],
                           guards["peak_derived_input"], guards["tracking"], guards["family_consistency"],
                           sandwich_evidence or sandwich(), p_hat, {p.parameter_id: p.role for p in parameters},
                           tuple(upstream))
    return inputs, chain


def case_positive(**changes):
    return build(label="CASE A positive control", **changes)


def case_absorption():
    rows = {r: (v[0], s_k, s_k) for (r, v), s_k in zip(ROWS.items(), [0.10, 0.12, 0.09, 0.15, 0.11, 0.14, 0.10,
                                                                     0.13, 0.12, 0.11, 0.10, 0.14])}
    return build(rows=rows, priors=(NuisancePrior("k_core", 0.0, 0.5, SYNTHETIC, True),),
                 label="CASE B G12 absorbed by k_core")


def case_rank_deficient():
    rows = {r: (v[0], 2.0 * v[0]) for r, v in ROWS.items()}
    return build(parameters=(E, G), rows=rows, priors=(), sandwich_evidence=sandwich(),
                 label="CASE C rank-deficient")


def case_model_error(holdout=False):
    if holdout:
        return build(holdouts={"H1": ("TORSION", 0.4), "H2": ("VALIDATION", 3.4)}, label="CASE D holdout failure")
    residuals = dict(RESIDUALS, R2=2.6, R4=3.1)
    families = dict(FAMILIES, R4="F2")  # R2 and R4 form one family with two same-sign residuals > 2
    return build(residuals=residuals, families=families, label="CASE D systematic pattern")


def case_wide():
    rows = {f"W{k}": (0.5,) for k in range(1, 11)}
    residuals = dict(zip(rows, [0.8, -0.8, 0.5, -0.5, 0.3, -0.3, 0.6, -0.6, 0.2, -0.2]))
    families = {r: f"F{r}" for r in rows}
    return build(parameters=(E,), rows=rows, residuals=residuals, families=families, priors=(), sigma=0.1,
                 sandwich_evidence=sandwich(applies=False), label="CASE E WIDE band",
                 fitting_pair_mac=fitting_pair_mac_evidence({r: 0.99 for r in rows}, SYNTHETIC))


def case_missing_physical_evidence():
    return build(sandwich_evidence=sandwich(independent=False), label="CASE F missing independent nuisance evidence")


def twin_control(context=VerdictContext.SYNTHETIC_GATE):
    """The accepted M4.9 twin, read-only from committed records (synthetic records-based control)."""
    loop = ROOT / "docs" / "auto_id" / "twins" / "SP13_identification_loop"
    gate = ROOT / "docs" / "auto_id" / "twins" / "SP13_truth_gate"
    journal = json.loads((loop / "journal.json").read_text(encoding="utf-8"))
    result = json.loads((loop / "loop_result.json").read_text(encoding="utf-8"))
    identity = json.loads((loop / "run_identity.json").read_text(encoding="utf-8"))
    readiness = json.loads((gate / "readiness_report_a1.json").read_text(encoding="utf-8"))
    evaluations = [e["record"] for e in journal["entries"] if e["kind"] == "evaluation"]
    names = identity["bounds"]["names"]
    jac = reconstruct_lm_jacobian(evaluations, result["history"], identity["start"], names,
                                  identity["lm_settings"]["finite_difference_step"])
    design, sigma = identity["objective_design"], 0.003
    whitened = np.array(jac.whitened)
    data = {row: {n: whitened[i, j] * sigma for j, n in enumerate(names)} for i, row in enumerate(design["fit_rows"])}
    parameters = tuple(ParameterDefinition(n, ParameterRole.GLOBAL) for n in names)
    m = build_sensitivity_matrix(data, design["fit_rows"], design["fit_clusters"], parameters,
                                 {n: jac.provenance for n in names})
    system = assemble_system(m, ObservationCovariance(m.term_ids, (diagonal_component(
        "twin_noise", m.term_ids, {t: sigma for t in m.term_ids}, False,
        "M4.9 twin synthetic experiment noise (sigma 0.003, D-036); not real-data uncertainty"),)), ())
    final = next(e for e in evaluations if e["parameters"] == result["parameters"])
    rows = {row["row_id"]: row for row in readiness["rows"]}
    families = {k: v["family"] for k, v in rows.items()}
    fit = residual_terms(design["fit_rows"], design["fit_clusters"], final["residuals"], families)
    held = [ResidualTerm(k, (k,), families[k], v) for k, v in sorted(final["holdout_residuals"].items())]
    label = "M4.9 SP13 twin synthetic records-based control; not real-specimen identification"
    chain = compute_evidence_chain(system, fit, held, result["parameters"], label)
    refusals = [e for e in evaluations if e["refusal"] is not None]
    source = "committed M4.9 records (D-036 twin definition)"
    inputs = VerdictInputs(
        context, label, chain.analysis, chain.statistical, chain.pattern, chain.birge, chain.robustness,
        fitting_pair_mac_evidence({r: rows[r]["mac"] for r in design["fit_rows"]}, source),
        GuardEvidence("registration", EvidenceState.PASS, source,
                      "registration_limited = false: synthetic experiment built through the frozen registration"),
        GuardEvidence("peak_derived_input", EvidenceState.PASS, source, "synthetic modes from the truth solve"),
        GuardEvidence("tracking", EvidenceState.FAIL if refusals else EvidenceState.PASS, source,
                      f"{len(refusals)} refused evaluations in the accepted journal"),
        GuardEvidence("family_consistency", EvidenceState.NOT_AVAILABLE, source, "single-specimen twin (D-044)"),
        SandwichG12Evidence(True, EvidenceState.NOT_AVAILABLE, ("k_core",), {"k_core": NuisanceConstraint(
            "k_core", True, False, True, "twin definition: core constants identical in truth and model (D-036)")},
            source),
        dict(result["parameters"]), {n: ParameterRole.GLOBAL for n in names})
    return inputs, chain
