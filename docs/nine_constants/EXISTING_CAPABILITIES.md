# Phase A — scientific and software capability audit

Audited at `aa76de3` (Quick Calibration P6.2) plus the governed Auto-ID records on that commit. Read-only; no Abaqus.

## A1. Parameterisation, per constant

Code facts used by the table:

- **Reading:** `forward_builder.locate_engineering_constants` reads exactly one temperature-independent nine-value
  `*Elastic, type=ENGINEERING CONSTANTS` record of one unique material and refuses everything else.
- **Writing:** `forward_builder.rewrite_engineering_constants(lines, record, constants, variable)` rewrites any
  subset of the nine values and keeps every other byte. A constant outside `variable` must equal its source value.
- **Domain:** `domain.forward_model_manifest.EngineeringConstants` holds the nine values in record order.
  `Parameterisation` maps parameters to constants.
- **Governed parameterisation:** `CARBON_PROPERTY_SET_V1` varies `E_in_plane_mpa` (E1 and E2 together) and `G12_mpa`.
  It fixes E3 6700, ν12 0.05, ν13 0.30, ν23 0.30, G13 2200 and G23 2200.
- **Quick Calibration:** `QuickCalibrationConfig.parameters` varies one multiplier k of a listed constant group
  (default E1, E2), with an optional G12 multiplier.
- **Optimiser:** `identification_step.run_bounded_lm` optimises in x = ln p with positive bounds. It cannot carry a
  signed Poisson ratio.
- **Sensitivities:** `practical_identifiability` (M5) analyses any typed set of columns: SVD rank at rcond 1e-3,
  C = (AᵀA)⁻¹, q projections, nuisance priors. Its sd rule (`SD_FIT_LIMIT_LN` 0.08) is defined in ln p.
- **Screening:** M6.4 (`transverse_screening`) is the only accepted FE evidence on E3, ν13, ν23, G13 and G23.

| Constant | Parsed from INP | Safe rewrite | Current optimiser can vary | Sensitivity layer | Realistic modal constraint (SP-13-type sandwich) | Main confounders | Policy restriction (SPEC v1.2) |
|---|---|---|---|---|---|---|---|
| E1 | yes | yes | only jointly with E2 (E_in_plane; QC multiplier) | yes (ln p) | yes, bending-dominated modes | E2 (fabric symmetry), t_face, core, adhesive | E1 ≠ E2 **MUST NOT** be enabled without traceable warp/fill (§5, §5.2, §16) |
| E2 | yes | yes | only jointly with E1 | yes | yes | E1, t_face, core | same |
| E3 | yes | yes | no (fixed) | not in any accepted path | **no**: M6.4 max \|Δf/f\| 5.1·10⁻⁶ for 5000→10000 MPa | — (no signal) | fixed (§5); M6.4 NEGLIGIBLE_FOR_BUDGET |
| ν12 | yes | yes | no (fixed 0.05) | not in any accepted path; ln ν undefined for ν ≤ 0 | weak | E1, E2, G12 | fixed by campaign definition (§5.2) |
| ν13 | yes | yes | no | no | **no**: M6.4 1.3·10⁻⁶ for 0.2→0.4 | — | fixed (§5) |
| ν23 | yes | yes | no | no | **no**: M6.4 7.3·10⁻⁶ | — | fixed (§5) |
| G12 | yes | yes | yes (G12_mpa; QC optional) | yes | partly (torsion families) | k_core, k_int, adhesive | sandwich-only G12 IDENTIFIED only under §5.1; primary source is a bare plate |
| G13 | yes | yes | no | no | **very weak**: M6.4 1.4·10⁻⁴ for 2200→5000 MPa | core shear, adhesive | fixed (§5) |
| G23 | yes | yes | no | no | **very weak**: M6.4 3.5·10⁻⁴ | core shear, adhesive | fixed (§5) |

The M6.4 figures are the accepted maxima over every frozen row, both specimens and both envelope endpoints
(`docs/auto_id/screening/M6_4_transverse_screening_result.json`). Per unit ln p they correspond to sensitivities of
about 10⁻⁵ (E3), 1.7·10⁻⁴ (G13) and 4·10⁻⁴ (G23). With σ = 0.3 % per mode, one row carries an sd(ln G23) of about
0.003 / 4·10⁻⁴ ≈ 7 — two to three orders of magnitude above the 8 % limit.

## A2. Physical model

- **3D orthotropic elasticity** (solid elements) uses all nine constants through the 6×6 compliance.
- **Conventional and continuum shells** work in plane stress: E1, E2, ν12, G12 and the transverse shear moduli G13,
  G23. E3, ν13 and ν23 cannot influence such a model at all. `nine_constants_inp.formulation_use` reports this from
  the section keyword. Its source is Abaqus behaviour; the solver version must still be confirmed.
- **Single-layer CFRP plate in bending:** thin-plate frequencies follow the bending stiffnesses D11, D22, D12 and D66,
  that is E1, E2, ν12 (weakly) and G12, with a transverse-shear correction from G13 and G23 that grows as (h/λ)². E3,
  ν13 and ν23 enter only through through-thickness normal stress, which is negligible in thin bending.
- **Sandwich panels:** thin faces carry membrane stiffness. Core shear, the adhesive and the interfaces dominate the
  transverse shear. G13 and G23 of the faces are then confounded with the core and adhesive parameters (SPEC §5.1
  discusses the same problem for G12).
- **SP-13:**
  - faces `CFRP_Face`: `C3D8I` solids, `*Solid Section` with `Ori-2` (axes 1 and 2 = global X and Y, axis 3 = Z,
    EVIDENCE M6.4a, re-read by `nine_constants_inp`);
  - core `PLA_Basic_Core`: `C3D20R` with its own Engineering Constants;
  - all nine face constants therefore *enter* the stiffness, yet five of them change the observed spectrum by less than
    4·10⁻⁴ (A1).
- **Element type and thickness:** solid `C3D8I` faces of 0.45 mm in bending behave like thin plates (low E3, ν13, ν23
  observability).
- **Material axes:** must be explicit (an `*Orientation` or global axes), never inferred from MAC (SPEC §11).
- **Free-free boundary conditions:** fix the rigid-body modes. Any suspension mass is a nuisance parameter.
- **Synthetic confirmation** (same physics, independent model, `orthotropic_block_model`):
  - a thin 80 × 54 × 1.6 mm plate gives max |S|: E1 0.49, E2 0.50, G12 0.47, ν12 0.05, G13 0.044, G23 0.020,
    ν23 0.0023, ν13 0.0006, E3 0.000006, and a rank of 6 for 9 at rcond 1e-3;
  - a thick 26 × 12.6 × 8.8 mm block makes all nine observable.

## A3. Existing SP-13 evidence (unchanged, read only)

- **P5 Quick Calibration** (accepted): two strict pairs, EXP 4 ↔ FE 10 and EXP 7 ↔ FE 13. It returns one common
  multiplier k = 1.14012, E1 = E2 ≈ 59 286 MPa, grade APPROXIMATE (band ±10.3 %). This is an **effective FE-model
  diagnostic, not a material property**.
- **Rank bound:** two independent scalar frequency observations give a nine-column sensitivity system of rank ≤ 2.
  SP-13's accepted rows therefore **cannot establish nine independent constants**, whatever FE evaluations are added.
  This is shown without any FE evaluation by `assess_identifiability` and in the research view
  (`offline_preview` with the P5 `result.json`).
- **Not done:** no new observation rows, no lowered MAC gates and no weaker pairs.
- **Archived sensitivities** (`SP13_registration_reevaluation.json`) exist only for `E_in_plane_mpa` (S_E 0.365 and
  0.483) and `G12_mpa`. No per-constant column exists for E1 alone, E2 alone or the transverse constants beyond the
  M6.4 screening.

## Modules reused by the research track

- **INP:**
  - `forward_builder` (strict reading and rewriting);
  - `EngineeringConstants`.
- **Identifiability:**
  - `practical_identifiability` (M5 rank, posterior, q, nuisance priors);
  - `branch_tracker.track_branches` (STRICT FE-to-FE tracking, refusals);
  - `identification_step.lm_step` / `objective` (the SPEC §8 step with the minus sign).
- **Quick Calibration:**
  - `quick_calibration.discover_modal_sets`;
  - Quick Calibration `result.json` (frozen rows; effective-model reference);
  - the main application layer `quick_calibration_ui` (Workflow menu).
