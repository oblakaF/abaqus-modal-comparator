# Implementation, FE architecture, resources and promotion path (research track NINE-EC)

## Implemented in this batch (research only; no Abaqus)

| Phase | Module | Purpose |
|---|---|---|
| C | `src/domain/orthotropic_elasticity.py` | compliance and stiffness (Abaqus Voigt order); reciprocal ν; admissibility with every violated condition; research coordinates (ln p for moduli, signed absolute ν) |
| C | `src/services/nine_constants_inp.py` | materials with record type and readability; explicit choice when several qualify; sections, element types (elset or part), orientation as written; formulation use (solid: all nine; shells: E3, ν13, ν23 unused); rendering through the accepted `rewrite_engineering_constants`, refused for inadmissible sets |
| D | `src/services/nine_constants_engine.py` | tracked central sensitivities with admissibility and SPEC S4 noise check; per-constant assessment on the unchanged M5 engine; gated research LM (SPEC §8 step, Φ decrease, 0.2·sd stop, 5 iterations, branch identity from the last accepted state); hard evaluation budget; FE cost plan |
| F | `src/services/orthotropic_block_model.py` | independent synthetic forward model: Rayleigh–Ritz orthotropic block (normalised Legendre basis, exact quadrature, symmetry-class family keys, analytic eigenvalue derivatives) |
| F | `src/services/nine_constants_synthetic.py` | synthetic experiments from declared true constants, frozen by shape identity; design-time same-class cluster exclusion |
| H | `src/services/nine_constants_report.py` | `research/nine-constants-report/v1`: nine rows with separate value classes; JSON, CSV and text; no INP writer |
| G | `src/services/nine_constants_offline.py` | the one service of the view: real files without FE (materials, modal sets, optional frozen rows of the same files, rank bound, FE plan, separate effective-model reference) and synthetic demonstrations |
| G | `src/nine_constants_window.py`, `src/quick_calibration_ui.py` | research view as Workflow menu item 3, a Toplevel of the main root, never starts Abaqus |

Tests:

- `tests/test_nine_constants_model.py`: elasticity and INP (F5, F7);
- `tests/test_nine_constants_engine.py`: F1–F6, F8, FE plan, report contract;
- `tests/test_nine_constants_gui.py`: the view in the main application.

## Phase E — FE evaluation architecture (designed, not connected)

```
nine-constant candidate p (admissible)                                    [orthotropic_elasticity]
  → render_constants(source INP, material, p)  (one material record changed)      [nine_constants_inp]
  → content-addressed job qc_<sha12> in the run's work/ folder                     [as Quick Calibration P1b]
  → verify_job_cache(job, requirements)  → VERIFIED_REUSE | NEW_SOLVE                [quick_calibration]
  → NEW_SOLVE only through the hard budget (_claim_new_solve), HUMAN-approved run,
    AbaqusRunner with owned-process tree, Stop / close safeguards, workflow exclusion   [P1a, P1b, P6.2]
  → extraction (pinned extract_odb.py) → provenance.json → fe_modes.npz (tracking subset)
  → FEModalState → track_branches(STRICT) from the last accepted state                [branch_tracker]
  → ln f per frozen row → engine (sensitivities, gate, LM, final sensitivities)        [nine_constants_engine]
```

- The adapter is an object with `evaluate(constants) -> FEModalState` and `identity()`. The engine already counts
  every evaluation against a hard limit.
- **MAC** is used only for identity. There is no automatic re-pairing after the baseline and no orientation
  optimisation.
- **Preflight contract:** `plan_fe_evaluations` keeps three counts apart — verified cached (named by the caller after
  `verify_job_cache`), potentially reusable (recorded, never subtracted) and required new. It also records the
  authorised limit, which is never raised. Disk, scratch, memory and licence figures come from a profile labelled
  MEASURED or ESTIMATE.
- **Not implemented:**
  - the Abaqus adapter itself;
  - a nine-constant run folder and campaign identity;
  - candidate CSV cleanup.

  They need a SUPERVISOR decision and HUMAN-approved validation.

## Resource estimate for a real nine-constant campaign (ESTIMATE, not measured)

Basis: the measured SP-13 profile (P4/P5) per evaluation:

- 31–33 min (solve on C: NVMe scratch, 30-mode extraction, post-processing);
- 4.65 GB output (≈ 0.9 GB without the extraction CSVs);
- ≤ 10.1 GB scratch;
- ≈ 41.5 GB commit peak;
- 3 licence tokens per solve.

| Item | Evaluations | Time | Disk (no cleanup) |
|---|---|---|---|
| Identifiability gate (baseline + 18 central + 18 half-step) | 37 | ≈ 20 h | ≈ 172 GB |
| Complete research estimation (gate + 2–15 LM trials + fresh central and noise at p̂) | 75–88 | ≈ 39–48 h | ≈ 349–409 GB |

- **Memory:** one solve at a time on the 31.7 GB machine. The 41.5 GB commit peak rules out parallel solves there.
- **Cleanup:** removing candidate CSVs after provenance would cut disk to ≈ 70–80 GB.
- **SP-13:** the accepted SP-13 rows bound the rank at 2, so **no amount of FE work identifies nine constants from
  them**. A real campaign needs new evidence first (IDENTIFIABILITY_REQUIREMENTS.md).

## Release path (minimum steps to an approved Windows capability)

1. SUPERVISOR scientific review of SCIENTIFIC_CONTRACT_PROPOSAL.md. The decisions needed:
   - the ν coordinate, step and precision rule;
   - the use of the §8 family rule for nine;
   - the nuisance priors;
   - mesh-convergence noise evidence.
2. A SPEC amendment for any nine-constant material-identification question (E1 ≠ E2 with traceable axes; variable
   transverse constants). Without it only diagnostic (C) and, separately declared, calibration (B) questions exist.
3. Experimental evidence that can carry the transverse constants:
   - thick specimens or blocks (RUS-type);
   - bare plates with traceable axes;
   - core-tile tests;
   - repeat tests for Σ_setup.
4. The Abaqus adapter on the P1b cache, budget and safeguards, with HUMAN-approved validation runs:
   - first a synthetic-twin campaign on an FE model with known constants;
   - then one real specimen with sufficient families.
5. Model-form robustness (leave-one-family-out), the pattern test and Birge for every estimated constant;
   family consistency for shared constants.
6. Promotion from the research view to a production Run button only after 1–5 are ACCEPTED. The GUI still shows
   per-constant statuses and never a value without evidence.

## Integration and promotion plan (Phase I)

- **Status now:** research diagnostic. It may run synthetic estimations and real-file previews; it cannot run
  Abaqus or produce a governed verdict.
- **Mandatory before promotion:**
  - SPEC amendment (REQUIRES_SPEC_AMENDMENT);
  - accepted ν rules;
  - nuisance priors with provenance;
  - mesh-convergence evidence;
  - real FE validation (synthetic twin with a real Abaqus model; then a physical specimen with ≥ 10 FIT families and
    1 HOLDOUT);
  - an independent material validation experiment;
  - Linux CI with a virtual display for the GUI tests.
- **Production enablement:** BLOCKED_PENDING_SUPERVISOR_DECISION.
