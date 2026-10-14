# Phase B — proposed scientific extension contract (NOT ACCEPTED)

**Status: PROPOSAL.** SPEC v1.2 remains the governing contract. Every item marked `REQUIRES_SUPERVISOR_DECISION` or
`REQUIRES_SPEC_AMENDMENT` is unresolved. The research code implements the proposal only behind
`RESEARCH_DIAGNOSTIC_ONLY` and cannot produce a governed verdict.

## Classification of a nine-constant material-identification mode

**REQUIRES_SPEC_AMENDMENT.** It conflicts with SPEC v1.2:

- §5 and §5.2 (E1 = E2 = E_in_plane; E3, ν13, ν23, G13 and G23 fixed; ν12 fixed);
- §16 (E1 ≠ E2 prohibited without traceable fabric orientation).

It stays disabled in production (`BLOCKED_PENDING_SUPERVISOR_DECISION`). A nine-constant **specimen calibration**
(question B) would also need a new parameterisation identity, but no SPEC v1.2 rule forbids declaring one.

## The contract (18 items)

1. **Parameter vector:** p = (E1, E2, E3, ν12, ν13, ν23, G12, G13, G23), in Abaqus `*Elastic, type=ENGINEERING
   CONSTANTS` record order. ν_ij (i < j) are the input ratios. The reciprocal ratios ν21 = ν12·E2/E1,
   ν31 = ν13·E3/E1 and ν32 = ν23·E3/E2 are derived and never input.
2. **Units and conventions:**
   - moduli in the INP's stress unit (MPa for the project models), Poisson ratios dimensionless;
   - Voigt order (11, 22, 33, 12, 13, 23) with engineering shear strain;
   - material axes 1, 2, 3 as declared by the model's `*Orientation` or default axes, stated in the report.
3. **Admissible domain:** E_i > 0, G_ij > 0, |ν_ij| < sqrt(E_i/E_j), and 1 − ν12ν21 − ν23ν32 − ν31ν13 − 2ν21ν32ν13 > 0.
4. **Stability:** the compliance (equivalently the stiffness) must be positive definite. Every candidate is checked
   **before** any FE job is prepared (`require_admissible`, `EvaluationCounter`).
5. **Forward-model identity:** INP SHA-256, material name, section and element formulation, orientation, solver
   identity and extraction identity. A content-addressed job per constant set reuses the P1b provenance, and
   `verify_job_cache` is mandatory before any reuse.
6. **Observation identity:**
   - the experimental file SHA-256, modal set, physical registration hash and frozen strict pairs;
   - fit and holdout rows by physical family;
   - no dynamic addition or removal of rows.
7. **Sensitivity definition:** S_ij = ∂ln f_i/∂x_j by central differences. x = ln p for moduli (step ±0.05, SPEC S4)
   and x = ν for Poisson ratios with an absolute step.
   - **The ν step (0.02) is a PROPOSAL** (`REQUIRES_SUPERVISOR_DECISION`).
   - ln ν is never used: ν may be zero or negative.
8. **Numerical noise:**
   - a half-step repeat must agree within 5 % (SPEC S4 for ln p);
   - the same criterion for ν columns is a PROPOSAL;
   - a column failing it is `NOT_IDENTIFIABLE` (not resolved above noise);
   - the FE discretisation and convergence noise of the real model must be measured before acceptance
     (`REQUIRES_SUPERVISOR_DECISION`: mesh-convergence evidence).
9. **Rank and identifiability:** the M5 engine is reused unchanged:
   - whitened rows plus nuisance prior rows;
   - rcond 1e-3;
   - rank deficiency as a hard block;
   - C = (AᵀA)⁻¹, q_j projections, correlations and condition number as diagnostics.
10. **Nuisance parameters:** every nuisance column needs an explicit, evidence-backed prior (M5.2). No default
    priors. **No prior may be strengthened to create rank.**
11. **Correlation and confounding:**
    - pairwise cosines and correlations are diagnostics;
    - the verdict uses the full-system sd and q;
    - a strongly correlated pair is reported as an unresolved combination (singular directions), never as two values.
12. **Uncertainty reporting:**
    - Moduli: SPEC §9 quantities in ln p (statistical_sd; birge_adjusted_sd only after a passed pattern test;
      model_form_robustness as a leave-one-family-out range; the conservative envelope).
    - Poisson ratios: absolute sd. **The ν precision rule is missing** (`REQUIRES_SUPERVISOR_DECISION`; the research
      code only accepts a caller-declared limit, recorded as UNACCEPTED).
13. **Mode correspondence:** the unchanged rules:
    - strict baseline pairing;
    - FE-to-FE tracking (MAC ≥ 0.90, unique) from the last accepted state;
    - clusters as one observation;
    - branch loss as refusal;
    - MAC never in Φ;
    - orientation never by MAC.
14. **Numerical refusal:**
    - inadmissible state;
    - rank deficiency;
    - sd above limit;
    - unresolved or unevaluated column;
    - branch loss;
    - non-convergence in the SPEC §8 limits;
    - exhausted evaluation budget.

    A refusal publishes no optimiser point.
15. **Effective-model result:** may claim at most "these constants make THIS model reproduce THIS specimen's rows at
    this statistical precision" (`NOT_A_MATERIAL_PROPERTY`, `NOT_TRANSFERABLE_WITHOUT_VALIDATION`). Any nine-constant
    calibration INP would need a distinct material name and SPEC v1.2 §9 fragment rules.
16. **Material-property result:** requires, at minimum:
    - the SPEC amendment above;
    - traceable material axes;
    - Σ_meas and Σ_setup;
    - the pattern test and model-form robustness;
    - family consistency over specimens (§13);
    - independent nuisance constraints;
    - an independent validation experiment (in the spirit of D-015, the steel gate).
17. **Partial identifiability:** reported per constant. A narrower question (some constants declared fixed) must be
    declared **before** execution and is labelled `FIXED_INPUT_NOT_IDENTIFIED`. The engine never narrows a question
    automatically, and a refused question publishes no partial optimisation.
18. **Multiple specimens:** shared material columns plus per-specimen nuisance columns in one system (SPEC §13
    hierarchy). Specimens with different geometry, thickness or orientation are the way to separate the transverse
    constants (see IDENTIFIABILITY_REQUIREMENTS.md).

## Thresholds and choices that need SUPERVISOR acceptance

| Item | Research value | Status |
|---|---|---|
| ν finite-difference step | 0.02 absolute | PROPOSAL |
| ν noise criterion | half-step repeat within 5 % of max \|S\| (column) | PROPOSAL (SPEC S4 analogue) |
| ν precision limit | none by default; caller-declared (demo 0.05) | REQUIRES_SUPERVISOR_DECISION |
| Minimum families for k = 9 | 10 FIT + 1 HOLDOUT (SPEC v1.2 §8 formula) | accepted formula; its use for nine is a PROPOSAL |
| LM limits | SPEC §8 (5 iterations, 0.2·sd stop) | reused unchanged |
| Synthetic cluster exclusion | same-class neighbour < 3 % (SPEC §12.4 trigger) | test-design rule only |
| Column scaling for ν in the condition number | none (absolute ν) | PROPOSAL; affects only the diagnostic |
| E1 ≠ E2, E3 / ν13 / ν23 / G13 / G23 variable | — | REQUIRES_SPEC_AMENDMENT |
