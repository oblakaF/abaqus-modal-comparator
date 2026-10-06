# M6 decision record

**Status:** M6 `IN_PROGRESS` (SUPERVISOR entry decisions 2026-10-06). Durable items are promoted
to DECISIONS.md D-049–D-056.

**Branch:** `auto-id/m6`, from `main` `ab1dc60`.

**Scope of M6:** independent physical calibration (SPEC §5, §5.1, §5.3, §7, §15, §17; ROADMAP M6).

**Authorised so far:**
- checkpoint M6-A: governance, design, and the HUMAN SP-11 experiment checklist;
- checkpoint M6-B: the Stage-A → M5 software adapter with synthetic tests.

**Not authorised:**
- no Abaqus or Abaqus Python, and no FE runs;
- no M6-C (real-data admission);
- no deletion of retained M4 artifacts.

| Item | Status | Readiness |
|---|---|---|
| M6.1 | `IN_PROGRESS` | NEEDS_DATA: real SP-11 data missing; not `REVIEW_READY` |
| M6.2 | `TODO` | NEEDS_DATA |
| M6.3 | `TODO` | NEEDS_DATA |
| M6.4 | `TODO` | NEEDS_DECISION |
| M6 gate | not evaluated | — |
| M7 | `NOT_STARTED` | — |

Checkpoints:
- **M6-A:** governance and the experiment checklist.
- **M6-B:** the adapter.
- **M6-C (not started):** real SP-11 data admission.
- **STOP:** a HUMAN Abaqus gate comes before the first SP-11 Stage-A matrix job.

---

## 1. Entry authorisation (SUPERVISOR, 2026-10-06)

- **Review:** the M6 entry review is accepted.
- **Start:** M6 starts on `auto-id/m6`, branched from `origin/main` `ab1dc60`.
- **Scope:** this task covers M6-A and M6-B only.
- **STOP:** after the M6-A/M6-B report, wait for:
  1. the SUPERVISOR review;
  2. the real SP-11 experimental data.

## 2. SP-11 identity (D-049)

- **Specimen:** `D:\Snadwich\SP-11` is the M6 twill 350×350 bare plate (SPEC §13, §17). Its
  governed identity is:

  | Field | Value |
  |---|---|
  | Name | Old CFRP Twill Plate 350x350 |
  | Nominal geometry | approximately 350 × 347 × 0.45 mm |
  | Mass record | approximately 79.59 g |
  | Family | old T300 twill |

  This is the intended M6 specimen identity.
- **D-017 still applies:** a twill result is not primary G12 for old plain 0.45.
- **Old recordings:** they may be used for planning and modal reconnaissance only. They MUST NOT be
  admitted as identification input.

  | Session | Content | Points | Band | Δf |
  |---|---|---|---|---|
  | 260824 | dataset 58 only: FRF, coherence, cross-spectrum; one reference | 121 | 0–250 Hz | 0.3125 Hz |
  | 260826 a | same | 120 | 0–100 Hz | 0.25 Hz |
  | 260826 b_center | same | 121 | 0–100 Hz | 0.25 Hz |

  Reasons:
  - FRF-only input is refused (D-030);
  - the frequency resolution is insufficient: SPEC §15 requires Δf ≤ 0.05 Hz below 100 Hz;
  - no governed frozen modal set exists (D-026).
- **No synthetic substitute:** no modal data are manufactured from these FRFs.

## 3. New SP-11 acquisition (D-049)

- **Requirement:** M6.1 must use a new experiment. The 260824 and 260826 FRFs are not sufficient
  for M6.1 acceptance.
- **Contract:** the new experiment must satisfy the current SPEC, M1 and M2 contracts. The exact
  HUMAN checklist is [M6_SP11_EXPERIMENT_CHECKLIST.md](M6_SP11_EXPERIMENT_CHECKLIST.md).

## 4. M6.1 verdict context (D-050)

- **Kind of result:** M6.1 is a real Stage-A validation and calibration result, in the typed
  context `STAGE_A_VALIDATION`.
- **It may report:**
  - D11 and D66;
  - D12, if practically identifiable (§5);
  - derived E and G12;
  - separately labelled uncertainties;
  - rank and identifiability diagnostics;
  - repeat agreement, after M6.2.
- **What M6 acceptance does not grant:** a production IDENTIFIED material-property verdict under
  the M5.9 PRODUCTION context while the required family consistency is NOT_AVAILABLE.
  - NOT_AVAILABLE is never mapped to PASS.
  - The result is never relabelled as production IDENTIFIED.
- **Stage boundary:**
  - M6 proves the real Stage-A estimate and its physical uncertainty support.
  - M7 remains responsible for production family consistency and the sandwich verdicts.
  - This resolves the hidden M6/M7 dependency found in the entry review.

## 5. D12 policy (D-051)

- **When D12 is fitted:** only when the full Stage-A system (D11, D12, D66) is practically full
  rank at the M5 rule, rcond = 1e-3. No new rank threshold is introduced.
- **When it cannot be independently supported:**
  - no pseudo-inverse;
  - no conditioning override;
  - no legacy fixed-pair fallback.
- **Instead:** the governed fixed-ν12 formulation of the current Stage-A parameterisation is used
  (D12 = ν12·D11, ν12 = 0.05, SPEC §5/§5.2), and the record states explicitly that D12 was not
  identified.

## 6. Thickness uncertainty (D-052)

- **Not an FE nuisance column:** for the bare plate, thickness is propagated analytically from D to
  E and G12 in ln-parameter space:
  - E = 12·D11·(1 − ν²)/t³;
  - G12 = 12·D66/t³.
- **Data:** the ≥ 9 physical thickness measurements.
- **Spatial contribution:** the measured spatial scatter, not the standard error of the mean. The
  physical plate non-uniformity is never divided by √N.
- **Gauge uncertainty:** if a gauge or instrument uncertainty is known, it stays a separately
  identified measurement component and is combined under the uncertainty model. It is never
  invented.
- **Cubic dependence:** E, G12 ∝ t⁻³ stays explicit, so the thickness uncertainty remains visible.

## 7. M6.2 repeat principle and Σ before M6.2 (D-053)

- **What counts as a repeat:** a valid M6.2 repeat is a genuine remount, re-suspension and
  excitation reinstallation of the SAME SP-11 specimen, under the same governed grid and protocol.
  The `remount_of` provenance is recorded.
- **Old sessions:** on current documentation they do not satisfy this.
- **Estimator:** the final Σ_setup estimator is not defined beyond what SPEC requires.
  - The software interface allows it to be added once the repeat dataset exists.
  - The exact formula is a dedicated M6.2 decision, taken after real repeat data exist.
- **Eventual 1σ agreement:** compares the inferred Stage-A mechanical quantities in ln space.
  Shared systematic quantities of the same plate, above all the same thickness characterisation,
  are not double-counted as independent setup scatter.
- **Before M6.2:**
  - development and testing may use the SPEC-authorised provisional setup term (0.3 %, SPEC §7),
    always flagged PROVISIONAL;
  - final M6 acceptance requires the physically measured M6.2 setup/retest evidence;
  - Σ_meas is not invented;
  - setup scatter is never relabelled as measurement uncertainty.

## 8. Core-tile policy (D-054)

- **Evidence required:** M6.3 requires physical core-tile evidence.
- **CARBON-5F:** sensitivity and context evidence only. It is NOT:
  - a k_core prior;
  - a current M5 sensitivity column;
  - a substitute for the core-tile experiment.
- **Plan:** one governed tile experiment for each lattice topology that will need an independent
  k_core prior in M7. Currently expected: auxetic and honeycomb.
- **Not in this checkpoint:** no manufacturing and no model execution.

## 9. M6.4 ranges; t_face and interface (D-055)

- **M6.4 ranges:**
  - no variation ranges are invented for E3, ν13, ν23, G13 or G23;
  - M6.4 stays NEEDS_DECISION until defensible ranges are supported by an approved source or
    decision;
  - the SPEC 0.3 % frequency-effect criterion is unchanged;
  - no M6.4 FE jobs yet.
- **Sandwich t_face:** no morphing in M6; it is M7 work.
- **Interface:**
  - no interface nuisance experiment in M6 unless a later governing decision requires one;
  - k_int stays off by default, with the holdout semantics preserved.

## 10. Legacy Stage-A rules (D-056)

The governed M6 Stage-A path does not inherit legacy rules that conflict with accepted Auto-ID
policy. It rejects:
- automatic mode-1 exclusion based on presumed suspension influence (D-031);
- the legacy condition-number and collinearity thresholds (D-040);
- the conditioning override (D-040);
- the fixed-pair fallback;
- any route that bypasses the M5 rank and refusal logic.

Unrelated legacy code is not rewritten. The governed path is a new adapter around the accepted
Stage-A machinery (§12).

## 11. Status representation

- **Schema:** STATUS keeps the existing mini-step status values. Readiness is recorded alongside:
  - M6 `IN_PROGRESS`;
  - M6.1 `IN_PROGRESS` / NEEDS_DATA;
  - M6.2 `TODO` / NEEDS_DATA;
  - M6.3 `TODO` / NEEDS_DATA;
  - M6.4 `TODO` / NEEDS_DECISION.
- **Not claimed:**
  - M6.1 is not `REVIEW_READY`, because the real SP-11 data are missing;
  - the M6 gate is not evaluated and is not PASS;
  - M7 is `NOT_STARTED`.

---

## 12. Checkpoint M6-B: Stage-A → M5 adapter (worker design, for SUPERVISOR review)

**Modules (new; no change to M1–M5 or legacy modules):**
- `src/domain/stage_a_experiment.py`: typed experimental evidence records for one Stage-A run.
  - Contents: the modal input (dataset types, M1.1 classification, frozen modal set), the thickness
    points (with an optional gauge), excitation, the trusted suspension threshold (M1.4 type), mass
    and plan dimensions with uncertainties, and the strict-policy pairing.
  - Every gap is reported together as `StageAInputRefusal`, with a typed code per gap.
- `src/services/stage_a_validation.py`: the adapter `run_stage_a_validation`, the
  `STAGE_A_VALIDATION` report, and the M6.2 comparison interface.

**Reused, unchanged:**
- `StageAAffineBasis` and `solve_generalized_eigenproblem`. Only these two (plus the error type and
  the parameter record) are imported from `matrix_model_service`; there is no Abaqus job path.
- M4: `track_branches` (strict policy) and `run_bounded_lm`.
- M5: `assemble_system`, `analyse_practical_identifiability` and `compute_evidence_chain` (rank,
  `statistical_sd`, pattern test, Birge, leave-one-family-out), plus `decide_verdicts`.
- The legacy Stage-A identification, uncertainty and inverse-solver services are not imported.

**Worker choices that need SUPERVISOR review:**

1. **Sensitivities:** central differences ±5 % in ln p on the affine model (SPEC §6 S4,
   `LMSettings.finite_difference_step`). The same rule handles single rows and confirmed clusters.
2. **Estimation:** the accepted M4.8 bounded LM.
   - The settings and parameter bounds are explicit run inputs with no defaults. The tests use the
     D-034 values.
   - D12 starts on the governed line ν12·D11.
   - A non-converged LM is a REFUSED report; it never falls back to another parameter set.
3. **D12 (D-051):** practical rank of the full (D11, D12, D66) system is checked at the start point
   and again at p̂. If it is rank-deficient at either point, the governed fixed-ν12 path runs.
   - That path first checks the rank of its own (D11, D66) system.
   - If that is rank-deficient too, the run is REFUSED (hard block).
4. **Tracking:** every evaluation is tracked FE-to-FE from the baseline pairing state (D-008). A
   tracking refusal anywhere gives a REFUSED report; nothing is re-paired.
5. **Σ:**
   - **Typed components:** each component is typed `Sigma_meas` or `Sigma_setup`, and its name must
     match its kind, so nothing can be relabelled.
   - **Ordering:** Σ is given over the fit terms, then the holdout rows.
   - **Holdout whitening:** holdout residuals are whitened by the diagonal of Σ over the holdout
     rows.
   - **Provisional term:** `spec_provisional_setup_term` gives the SPEC §7 0.3 % term (sd 0.003 in
     ln f, first order), flagged PROVISIONAL.
6. **Thickness (D-052):**
   - spatial scatter = sample sd (n − 1) of the points;
   - sd(ln t) ≈ s_t/t̄, first order;
   - component in E or G12 = 3·s_t/t̄;
   - gauge component = 3·u_gauge/t̄, only if supplied;
   - combined `statistical_sd_ln_with_thickness` = the root-sum-square of the independent
     components, with every component kept and labelled.
   - E = 12·D11·(1 − ν²)/t³ and G12 = 12·D66/t³ (equal to the existing Stage-A formula). ν is
     D12/D11 when D12 is fitted; otherwise ν = 0.05.
   - The Birge factor scales the frequency part only.
   - The model-form half-range of E and G12 is the linear image of the leave-one-family-out shifts.
7. **Excitation (SPEC §15):**
   - at least 2 excitation locations;
   - a contact route needs a recorded attachment mass, equal to the mass modelled in the forward
     model;
   - a route without an attached mass needs an approval reference.
8. **Production verdict (D-050):**
   - computed by `decide_verdicts` in the PRODUCTION context, with family consistency NOT_AVAILABLE
     and the provenance "M7 work";
   - embedded unchanged in the report;
   - an internal invariant refuses any IDENTIFIED or WIDE result;
   - the M5 `VerdictContext` enum is unchanged.
9. **Units:** SI, with D in N·m and the thickness converted from mm.
10. **M6.2 interface (D-053):** `stage_a_repeat_comparison_inputs` gives ln estimates,
    differences and frequency-only `statistical_sd` for two runs.
    - It requires an eligible M2 `classify_setup_repeat`, the same physical specimen, and the same
      fitted parameters.
    - It records a shared thickness characterisation as common-mode.
    - It has no agreement rule: its status is `AGREEMENT_RULE_PENDING_M6_2_DECISION`.
    - `SetupScatterEstimator` is an interface only.

**Open items, not decided by the worker:**
- **N2:** the affine-basis validation tolerance against direct Abaqus solves. It must not be
  invented and is needed before M6-D.
- **Real-run LM settings and D bounds** for SP-11.
- **Mass and plan uncertainties:** propagation of the mass and plan-dimension uncertainties into D.
  They are recorded, not propagated, and listed as an open condition in every report.
- **Bare-plate fit/holdout policy:** SPEC §12 holdouts are defined for sandwiches (k_int); the
  adapter supports holdout rows but does not choose them.
- **Family-id string for the twill passport** (checklist A7).

## 13. M6-B tests (`tests/test_stage_a_validation.py`, synthetic, no Abaqus)

| SUPERVISOR item | Test |
|---|---|
| 1 D11/D66 recovery | `test_01_synthetic_d11_d66_recovery` (fitted-D12 and fixed-ν12 cases) |
| 2 D12 full rank | `test_02_d12_full_rank_case_is_fitted` |
| 3 D12 rank-deficient | `test_03_d12_rank_deficient_uses_governed_fixed_path_only` |
| 4 no pseudo-inverse | `test_04_no_pseudo_inverse` |
| 5 no override | `test_05_no_scientific_override_and_required_rank_is_a_hard_refusal` |
| 6 t⁻³ scaling | `test_06_e_and_g12_scale_as_t_to_the_minus_three` (+ `test_06b` formula cross-check) |
| 7 not /√N | `test_07_spatial_scatter_is_the_sample_sd_not_divided_by_sqrt_n` |
| 8 gauge separate | `test_08_gauge_uncertainty_is_a_separate_component` |
| 9 FRF-only refused | `test_09_frf_only_input_is_refused` (through the M1.1 classifier) |
| 10 frozen set missing | `test_10_missing_frozen_modal_set_is_refused` |
| 11 < 9 thickness points | `test_11_fewer_than_nine_thickness_points_are_refused` |
| 12 attachment / non-contact | `test_12_missing_attachment_or_non_contact_evidence_is_refused` |
| 13 suspension | `test_13_missing_suspension_evidence_is_refused` |
| 14 no mode-1 exclusion | `test_14_mode_one_is_not_excluded` |
| 15 no legacy condition thresholds | `test_15_legacy_condition_number_thresholds_are_not_applied` (condition number 342, still fitted) |
| 16 no fixed-pair fallback | `test_16_legacy_fixed_pair_fallback_is_not_used` |
| 17 estimate + uncertainty | `test_17_stage_a_validation_reports_estimate_and_labelled_uncertainty` |
| 18 no production IDENTIFIED | `test_18_no_production_identified_while_family_consistency_is_not_available` |
| 19 deterministic hashes | `test_19_deterministic_provenance_and_hashes` |
| 20 no Abaqus / M3 dependency | `test_20_no_abaqus_or_m3_execution_dependency` |

Additional tests:
- all gaps are listed together;
- a confirmed cluster is one fit term and holdouts stay out of the fit;
- a systematic family error is reported, not hidden;
- a tracking refusal gives a REFUSED report;
- Σ kinds cannot be relabelled;
- the M6.2 comparison inputs.

## 14. Data still needed for M6-C

Every HUMAN item of [M6_SP11_EXPERIMENT_CHECKLIST.md](M6_SP11_EXPERIMENT_CHECKLIST.md),
sections A–E (A7 is a SUPERVISOR confirmation). None is available in the repository records or in
the data stores today.
