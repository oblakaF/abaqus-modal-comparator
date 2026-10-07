# M6 decision record

**Status:** M6 `IN_PROGRESS` (entry decisions; corrective governance §15; rescope §16). Durable items
are promoted to DECISIONS.md D-049–D-061. D-057–D-059 correct parts of D-049, D-053 and D-054, and
D-060 supersedes D-015.

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
| M6.1 | `NOT_AVAILABLE_WITH_CURRENT_SETUP` | D-059, §16 |
| M6.2 | `NOT_AVAILABLE_WITH_CURRENT_SETUP` | D-059, §16 |
| M6.3 | `NOT_AVAILABLE_WITH_CURRENT_SETUP` | D-059, §16 |
| M6.4 | `ACCEPTED` (CLOSED) | M6.4a ACCEPTED (D-067); M6.4b ACCEPTED (D-068): all five constants NEGLIGIBLE_FOR_BUDGET (§20) |
| M6 gate | `PASS_CANDIDATE` (pending final SUPERVISOR acceptance) | rescoped (SPEC §19 item 6, D-061); §20, §21 |
| STEEL gate | `SUPERSEDED` | D-060 |
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

> **Superseded by §15 / D-057 (2026-10-06):** a new SP-11 experiment is not physically available. The
> requirement below is no longer actionable; frequency resolution alone is no longer a reason.

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

> **Corrected by §15 / D-058:** the repeat wording follows SPEC §7. The same grid supports
> frequencies, shapes and MAC; a same-panel remount on a different grid supports frequency-only.
> SP-11 M6.2 is `BLOCKED_ON_EXPERIMENT`.

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

> **Corrected by §15 (2026-10-06):** nominal SP-11 values exist in `D:\Snadwich\SP-11\spec.txt`
> (AVAILABLE_NOT_YET_GOVERNED). The checklist is now a reference record, not a HUMAN to-do list.

Every HUMAN item of [M6_SP11_EXPERIMENT_CHECKLIST.md](M6_SP11_EXPERIMENT_CHECKLIST.md),
sections A–E (A7 is a SUPERVISOR confirmation). None is available in the repository records or in
the data stores today.

---

## 15. Corrective governance after the real-specimen source audit (SUPERVISOR, 2026-10-06)

**Basis:** the `D:\Snadwich` source audit, accepted as the factual basis
([SNADWICH_INVENTORY.md](SNADWICH_INVENTORY.md)), and the HUMAN constraint that a new SP-11
experiment is not physically available.

**D-057 (corrects D-049):**
- **Kept:** SP-11 is the M6 twill bare plate, and its existing data are reconnaissance-only for the
  current M6.1 contract.
- **Removed as reasons:**
  - "resolution insufficient" as a standalone bar (the accepted SP02/SP13 lineages also started
    from coarser raw FRFs);
  - "new acquisition required" as an actionable requirement.
- **M6.1 is `BLOCKED_ON_EXPERIMENT` because:**
  - there is no governed fitted / frozen modal set;
  - the sessions are inconsistent;
  - the physical support data are incomplete: no thickness map, no mass or dimension uncertainty,
    no attachment mass, no suspension threshold;
  - no new valid SP-11 experiment is available.
- **The old FRFs** stay reconnaissance and modal-preparation source data.

**D-058 (corrects D-053):**
- **Wording:** the repeat wording now matches SPEC §7. The same grid supports frequencies, shapes
  and MAC; a same-panel independent remount on a different grid supports frequency-only. No new
  criterion.
- **M6.2:** `BLOCKED_ON_EXPERIMENT`. The definition is not weakened.

**Checklist:** [M6_SP11_EXPERIMENT_CHECKLIST.md](M6_SP11_EXPERIMENT_CHECKLIST.md) is re-labelled
"Reference requirements for a valid future SP-11 / bare-plate test", with three groups:
AVAILABLE_NOT_YET_GOVERNED, MISSING and UNAVAILABLE_FOR_THIS_PROJECT.

**Unchanged:**
- **SPEC and ROADMAP:** M6.1 and M6.2 stay in the contract. There is no stage rescope (option C2)
  yet: one deliberate rescope decision follows only once the feasibility of M6.3 and of the STEEL
  gate is known.
- **M6-B code and tests:** unchanged, and remain valid. The generic Stage-A adapter is kept for any
  future valid bare-plate evidence.

**Status:**

| Item | Status |
|---|---|
| M6 | `IN_PROGRESS` |
| M6-A | `REVIEW_READY` (corrected) |
| M6-B | `REVIEW_READY` |
| M6.1 | `BLOCKED_ON_EXPERIMENT` |
| M6.2 | `BLOCKED_ON_EXPERIMENT` |
| M6.3 | `TODO`, NEEDS_DATA, feasibility unresolved |
| M6.4 | `TODO`, NEEDS_DECISION |
| M6 gate | `NOT_EVALUATED` (cannot currently close) |
| M7 | `NOT_STARTED` |

M6 is neither failed nor accepted.

---

## 16. M6 / STEEL normative rescope (SUPERVISOR, 2026-10-06)

**Basis:**
- the accepted rescope review (sections F–K);
- the HUMAN constraints: no new SP-11 test, no SP-11 repeat, no core-tile test; STEEL is not part of
  the plan.

**Governance route:** SPEC §19 item 6 (the established normative amendment mechanism), with
DECISIONS D-059–D-061. SPEC §5, §5.1, §5.3 and §7 are unchanged.

| Item | New status | Consequence kept |
|---|---|---|
| M6.1 | `NOT_AVAILABLE_WITH_CURRENT_SETUP` | No primary twill G12; no real-data Stage-A validation; the M6-B adapter stays (synthetic validation). Not a release failure by itself. |
| M6.2 | `NOT_AVAILABLE_WITH_CURRENT_SETUP` | SPEC §7 provisional Σ_setup 0.3 % allowed and flagged. A measured sandwich-remount estimate only with proven remount provenance from existing records. |
| M6.3 | `NOT_AVAILABLE_WITH_CURRENT_SETUP` | No measured k_core prior; the §5.1 G12 route stays closed (D-046); k_core later only as a PROVISIONAL nuisance with a SUPERVISOR-approved width (not chosen). D-054's tile plan is superseded in part. |
| M6.4 | `TODO`, NEEDS_SOURCE | FE-only screening, after an approved range source and a HUMAN Abaqus gate |
| STEEL | `SUPERSEDED` (D-060) | Results labelled **not externally validated** |

**Rescoped M6 gate (D-061):**
- all unavailable physical evidence is explicitly recorded;
- every missing prior has its conservative verdict consequence encoded;
- provisional inputs are explicitly flagged;
- the M6.4 budget is closed.

**Not done in this checkpoint:**
- M6 is not accepted;
- M7 is `NOT_STARTED`;
- no Abaqus, no M6-C, no code change.

---

## 17. SP-13 physical registration gate (SUPERVISOR, 2026-10-06)

**Scope:** zero Abaqus. SP-13 only. No M7 fitting. The anti-tuning rule is mandatory.

**Delivered:**
- `services/psv_video_registration.py`: read-only `.svd` reconstruction; no modal imports.
- `tools/reconstruct_psv_registration.py`: writes the evidence record.
- `tools/build_sp13_physical_registration.py`: builds the registration through the unchanged M2 builder.
- `tools/sp13_registration_reevaluation.py`: the before/after strict freeze.
- `services/archived_baseline.reregistered_mac_matrix`: every pack binding except the registration
  hash; the existing archived path is unchanged.
- Governed files:
  - the reconstruction record (sha256 `6b45fbfbacad0df939b0b12f8496edddff0525855e0de0312ff5f558c71bb0ae`);
  - the physical passport (manifest `943bb3d1946863c61abd39ccac8fa1da625067b9dffdcd6be2c82c3e125d5000`);
  - the physical registration (`2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823`, production-ready);
  - the re-evaluation record.
- Decisions D-062 and D-063.

**Result:**
- **Strict pairs:**
  - legacy: (4↔10, 5↔11), nearly collinear (condition number 252);
  - physical: (4↔10 MAC 0.958; 7↔13 MAC 0.947), condition number 6.3.
- **Sufficiency:** the M4.3 validation holdout takes R2, leaving one fit row, so SP-13 alone stays
  insufficient.

**Remaining ambiguities:**
- FE axis signs: four admissible mappings, geometrically identical; 180° gives the same pairs;
  the bottom face is not evaluable.
- Face binding is a convention.
- `scale_rel` is NOT_AVAILABLE, so `registration_limited` is NOT_AVAILABLE.

## 18. SP-13 HUMAN evidence update and SP-02 physical registration gate (SUPERVISOR, 2026-10-06)

**Scope:** zero Abaqus. No M7 fitting, no M6-C, no SP-10 FE model. The STRICT policy, thresholds,
classifier, M4.3 holdout rule and M4.4 cluster rule are unchanged. MAC is never used for
orientation. The SP-13 gate (`173af43`) is SUPERVISOR-ACCEPTED (D-064). Status of this
checkpoint: `REVIEW_READY`.

**Delivered:**
- **Parser fix (behaviour change, tested):** `psv_video_registration.alignment_points` reads the
  stored point count (SP-02: 27 points). SP-13 is rebuilt bit-identically.
- **Tools:**
  - `tools/reconstruct_psv_registration.py`: optional `--dimension-uncertainty`; the default text
    is unchanged.
  - `tools/build_physical_registration.py`: the generic passport builder plus the four sign
    alternatives. The SP-13 tool is unchanged.
  - `tools/registration_uncertainty_evaluation.py`: M2.4 on the shape-pack surface. It also
    evaluates the pairing-change trigger with the unchanged STRICT freeze.
  - `tools/sp02_registration_reevaluation.py`: legacy vs physical freeze, CARBON-5A tracked
    sensitivities and the combined picture.
- **Governed files:**
  - SP-13 passport: `scale_rel` 0.002 and the H7 orientation source. Registration hash unchanged.
  - SP-13 and SP-02 M2.4 records.
  - SP-02 reconstruction record, physical passport, physical registration and re-evaluation record.
  - New SP-02 files only. The legacy SP-02 registration, passport and fixture are unchanged.
- **Tests:** `tests/test_sp02_physical_registration.py` (new); `tests/test_sp13_physical_registration.py`
  updated for H7/H8.

**Results:** EVIDENCE, the entry "SP-13 HUMAN evidence update (H7–H10) and SP-02 physical
registration".
- **SP-13 M2.4:** EVALUATED; `registration_limited` False.
- **SP-02:** same Polytec anisotropy (x 1.092, y 0.818). The legacy registration is wrong by median
  29 mm, max 54 mm.
- **SP-02 physical strict freeze:** FROZEN, 3 pairs (2↔8, 4↔10, 7↔13). Validation holdout R3.
  2 fit rows: rank 2, condition number 6.1. `registration_limited` False.
- **SP-02 identity:** NEEDS_ONE_HUMAN_CONFIRMATION (one question). It does not block the
  reconstruction.

### 18.1 M4.3 holdout semantics (read-only; rule unchanged)

- **Sources:**
  - SPEC §12.3: holdouts by physical modal family. Default sandwich holdouts: the lowest
    torsion-dominated family when k_int is disabled, and the highest accepted family as a
    validation holdout.
  - SPEC §5 (k_int row): "the lowest torsional family goes to holdout".
  - D-010 (family, not mode index).
  - D-035: only the classifier **thresholds** are provisional.
  - M4_DECISION_RECORD §5.1: "the holdout policy is not overridden for real data".
  - M5: holdouts are never promoted into the fit; |r| > 3 fails.
- **Implementation:** `select_holdouts(rows, k_int_enabled)` acts on the rows of **one frozen
  observation set**. M4/M5 freeze one specimen at a time, so in practice the rule is applied per
  specimen.
- **Classification:**
  - **Mandatory, not provisional.** The torsion holdout is a model-form safeguard for k_int off.
    The validation holdout is part of the SPEC default and is applied to real data without override.
  - **Unit:** defined per frozen set, which is per specimen as built and validated (M4.3 real
    validation and the M4.9 twin were single-specimen).
  - **Campaign level:** SPEC §12.3 does not say whether a multi-specimen campaign (§13, M7) applies
    it per specimen or once to the pooled family set. That choice is an M7 decision, not made here.
- **Why SP-13 loses a row:**
  - SP-13 has two strict rows of different families, (1,2) and (0,3), and no torsion family among
    them.
  - The highest accepted family (0,3) is held out for validation, which leaves one fit row.
  - This is the SPEC default working as designed on a two-row set, not a defect.
- **Effect of the reading on SP-02 + SP-13:**
  - Per specimen: 3 fit rows.
  - Pooled by family type: the highest accepted family is (0,3), which holds out both SP-13 R2 and
    SP-02 R3, so the same 3 fit rows.
  - Only a specimen-keyed pooled reading would return SP-02 R3 to the fit (4 rows). It is not
    adopted.

### 18.2 Is SP-10 still needed?

- **Observations:**
  - SP-02 alone now has 2 fit rows after its unchanged holdout: rank 2, condition number 6.1.
  - SP-13 adds a third fit row.
  - Stacked: 5 strict rows, 3 fit rows over 2 specimens and 2 family types. Rank 2, condition
    number 6.0. sd(ln E) 0.6 % (σ provisional 0.3 %, carbon-only).
  - E_in remains supported when any one family is left out. G12 rests on the (1,2) family, and G12
    already follows §5 / §5.1 (`BARE_PLATE_REQUIRED`, D-046).
- **SPEC route:** SPEC §5 (order step 3) identifies E_in from "sandwiches of the family jointly".
  SP-02 and SP-13 are two sandwiches of the old-plain-0.45 family (`CFRP-T300-plain-0.45-oldstock`).
  The §13 consistency test needs N ≥ 2 specimens, so it is evaluable with Δdof = k.
- **What SP-10 would add:** SPEC §7 and §13 name the SP2/SP10 pair (same design) as the
  **reference specimen-to-specimen scatter** test.
  - Without SP-10, an SP-02 vs SP-13 consistency test mixes specimen scatter with core-topology
    model form (honeycomb vs auxetic).
  - A failure would therefore not be attributable. A pass remains meaningful.
  - This reference scatter test must be reported as NOT_AVAILABLE. It is not a gate condition in
    SPEC §13, ROADMAP M7 ("where scientifically compatible") or §19.
- **Conditions that remain, unrelated to SP-10:**
  - the single SP-02 identity confirmation;
  - SUPERVISOR acceptance of the SP-02 registration;
  - Σ_setup provisional 0.3 % flagged;
  - M6 must still pass its rescoped gate (M6.4 NEEDS_SOURCE) before M7 starts.
- **Worker answer:** SP-02 + SP-13 give a plausible path to E_in without SP-10 (**YES**), with no
  rule weakened.

## 19. M6.4 transverse-constant screening (SUPERVISOR, 2026-10-07; D-066)

**Normative reading:**
- SPEC §5: E3, ν13, ν23, G13 and G23 stay fixed if "reasonable variation changes frequencies by < 0.3 %";
  otherwise they enter the uncertainty budget. D-055 keeps the criterion.
- The SUPERVISOR accepted (D-066) the reading of the points the SPEC leaves open:
  - the output is the frozen observation rows (fit and holdout), followed by FE-to-FE MAC tracking;
  - both specimens of the M7 path are screened, at both endpoints;
  - a non-negligible constant is recorded and budgeted, never re-tuned. Its M7 propagation is decided at
    M7 entry.

**Envelope** (`screening/M6_4_transverse_envelope.json`, envelope hash `d29e8485…`):
- E3 5000–10000 MPa;
- ν13 and ν23 0.2–0.4;
- G13 and G23 2200–5000 MPa;
- basis `LITERATURE_INTERIM_SCREENING_ENVELOPE`.

**Minimum FE design:**

| Constant | Baseline | Low | High | Solves per specimen |
|---|---|---|---|---|
| E3 | 6700 | 5000 | 10000 | 2 |
| ν13 | 0.30 | 0.20 | 0.40 | 2 |
| ν23 | 0.30 | 0.20 | 0.40 | 2 |
| G13 | 2200 | 2200 = baseline (no solve) | 5000 | 1 |
| G23 | 2200 | 2200 = baseline (no solve) | 5000 | 1 |

- **Specimens:**
  - SP-02: rows R1 FE 8, R2 FE 10, R3 FE 13 (holdout);
  - SP-13: R1 FE 10, R2 FE 13 (holdout).
- **Stiffness:** both faces are C3D8I solids with material axis 3 along global Z (read from the INPs).
  All five constants therefore enter the stiffness, and none can be excluded without a solve.
- **Baselines:** the archived CARBON-4C packs `SP02_f3e592281bebce66` and `SP13_a46d08b52995e078` are
  reused. The reference candidate regenerates their INPs byte-identically (checked in code and tests).
- **Totals:** 16 Abaqus solves, 16 extractions (pinned `extract_odb.py`, modes 7–30), 0 baseline solves.

**M6.4a implementation (zero Abaqus), `REVIEW_READY`:**
- `src/domain/transverse_screening.py`:
  - the envelope schema, parsed strictly;
  - the criterion is fixed at the SPEC 0.3 % and is not configurable;
  - each baseline must equal the governed fixed constant;
  - every endpoint state must be positive definite.
- `forward_builder.render_screening_input` / `prepare_screening_job`:
  - the candidate is the envelope's reference point;
  - exactly one screened constant is set to one of the envelope's endpoints;
  - the fitting post-check applies unchanged;
  - the job schema is `auto-id/screening-forward-job/v1`.
  - The fitting parameterisations are unchanged; a screening perturbation is not a parameterisation.
- `src/services/transverse_screening.py`:
  - the plan: the baseline regeneration check, then the HUMAN manifest;
  - the HUMAN-gated run:
    - the authorised manifest hash;
    - a hash-chained journal;
    - no automatic retry and no duplicate solve;
  - the evaluation: M4.5 tracking of the frozen rows, then the per-constant classification;
  - an informational all-mode diagnostic, never used for classification.
- `tools/m6_4_transverse_screening.py`: `plan` / `run` / `evaluate`.

**HUMAN Abaqus manifest:** hash `6d34179c787c8b0e1619864709290f2824e0435b98fb1ff2689e61d892da3922`. The job list is in EVIDENCE.

**Not done:** no Abaqus, no Abaqus Python, no result, no M6 acceptance, no M7.

## 20. M6.4b screening result and the rescoped M6 gate (worker evaluation, 2026-10-08)

**Execution:** HUMAN Abaqus gate D-067, manifest `6d34179c787c8b0e…`.
- 16 of 16 solves and 16 of 16 extractions succeeded.
- 0 failures, 0 retries, 0 baseline solves.
- The details are in EVIDENCE, "M6.4b".

**Result** (`screening/M6_4_transverse_screening_result.json`, `0fb87ea753217e15…`):

| Parameter | Max effect SP02 | Max effect SP13 | Global max | Classification |
|---|---|---|---|---|
| E3 | 0.0003 % | 0.0005 % | 0.0005 % | `NEGLIGIBLE_FOR_BUDGET` |
| ν13 | 0.0001 % | 0.0001 % | 0.0001 % | `NEGLIGIBLE_FOR_BUDGET` |
| ν23 | 0.0007 % | 0.0007 % | 0.0007 % | `NEGLIGIBLE_FOR_BUDGET` |
| G13 | 0.0125 % | 0.0138 % | 0.0138 % | `NEGLIGIBLE_FOR_BUDGET` |
| G23 | 0.0271 % | 0.0353 % | 0.0353 % | `NEGLIGIBLE_FOR_BUDGET` |

- **Tracking:** every frozen row was tracked (MAC ≥ 0.999999), with no refusal and no order change.
- **INCLUDE parameters:** none. The M7 propagation policy for a budgeted constant is therefore not needed
  for these five constants. It was not decided.

**Rescoped M6 gate (D-061):**

| Condition | Evidence | State |
|---|---|---|
| All unavailable physical evidence is recorded | M6.1–M6.3 `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059, §16); SP-11 records (§15); specimen catalog (D-065) | met |
| Every missing prior has its conservative verdict consequence encoded | G12: `BARE_PLATE_REQUIRED` / `NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED` in `services/identification_verdict.py` (D-046, M5.9). k_core: no measured prior; later only a PROVISIONAL nuisance, and a PROVISIONAL prior keeps the verdict provisional (`identification_verdict.py`). No real-data Stage-A validation (recorded) | met |
| Provisional inputs are explicitly flagged | Σ_setup 0.3 % provisional (SPEC §7, D-065; carried as `provisional` in `identification_uncertainty`); M4.3 classifier thresholds PROVISIONAL; the M6.4 envelope labelled interim | met |
| The M6.4 transverse-constant budget is closed | M6.4b: all five constants classified `NEGLIGIBLE_FOR_BUDGET`; complete evidence; no tracking refusal | met (pending SUPERVISOR acceptance of M6.4b) |

**Worker gate evaluation:** **PASS**, pending SUPERVISOR acceptance. M6 is not self-accepted.

**Open items, not M6 gate conditions:**
- the "not externally validated" label (D-060) must appear in real-result reports; it is not yet wired in
  code (M7/M8 reporting);
- the forward binding of the SP-02 physical passport; `SP13/best` still uses the legacy registration;
- the campaign-level reading of the M4.3 holdout (§18.1);
- the k_core PROVISIONAL width; the M7 mapping of the practical 5–10 % target (D-066).

M7 is NOT_STARTED.

## 21. M6 closure record and M7-entry wiring (SUPERVISOR, 2026-10-08; D-068)

**M6 closure record:**

| Item | State |
|---|---|
| M6.1 bare-plate Stage A | `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059). No primary twill G12; G12 follows §5 / §5.1 (D-046) |
| M6.2 same-plate repeat | `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059). Σ_setup provisional 0.3 %, flagged |
| M6.3 core tile | `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059). No measured k_core prior |
| M6.4 transverse constants | **CLOSED** (D-067, D-068). E3, ν13, ν23, G13, G23 `NEGLIGIBLE_FOR_BUDGET` (max 0.0353 %); fixed |
| New experiments | none |
| STEEL gate | `SUPERSEDED` (D-060). Results are labelled not externally validated |
| M6 gate (rescoped, D-061) | **PASS candidate.** All four conditions are met (§20); final SUPERVISOR acceptance is pending |

**M7-entry wiring (active inputs only):**
- SP-02: `SP02.physical.specimen.json` → `SP02/bravo-1-physical` (`9b63f6c8…`) → `SP02.physical.forward.json`.
- SP-13: `SP13.physical.specimen.json` → `SP13/best-physical` (new; `2eeeaa86…`) → `SP13.physical.forward.json`.
- Historical M0–M5 chains are unchanged and still bind: `SP02/bravo-1` / `SP13/best`, the legacy passports,
  `SP02.forward.json` / `SP13.forward.json`, and the CARBON-4C baselines.
- Both chains render the same FE jobs, so the archived baseline packs are reusable.

**Exact remaining M7 prerequisites:**
- **Process (CLAUDE.md, ROADMAP stage policy):**
  1. SUPERVISOR final acceptance of M6 (gate PASS candidate → ACCEPTED) and of this D-068 checkpoint;
  2. the M6 stage PR to `main`, merged only with explicit HUMAN authorisation;
  3. the `main` merge SHA recorded in STATUS.json and CHANGELOG.md before M7 starts.
- **SUPERVISOR M7 entry decisions (not decided here):**
  4. the M7 specimen scope. ROADMAP M7.2 names SP-01, SP-02, SP-10 and SP-13, but only SP-02 and SP-13 have
     governed fixtures, FE models and physical registrations (catalog);
  5. the campaign-level reading of the mandatory M4.3 holdout (M6_DECISION_RECORD §18.1): per specimen
     (3 fit rows, rank 2) or pooled;
  6. the mapping of the practical target (D-066: correct mode identity / MAC, frequency preferably within
     ~5 %, up to ~10 %) onto the M5 verdict (Σ, pattern test, Birge);
  7. the nuisance set and priors:
     - t_face: SPEC §5 needs a prior from 9+ thickness points per specimen; D-066 gives the local scatter;
     - k_core: only a PROVISIONAL nuisance with a SUPERVISOR-approved width (D-059), or kept fixed;
     - k_int: off by default, with the torsion holdout.
- **Implementation before real-result reporting:**
  8. the "not externally validated" label (D-060) must be emitted by the real-result report path. It is not
     yet wired in code.
- **Execution:**
  9. every M7 Abaqus solve and extraction needs its own HUMAN gate.
- **Already closed and not M7 blockers:**
  - Σ_setup provisional 0.3 %, flagged (a measured value is deferred);
  - the transverse constants are fixed (M6.4: all NEGLIGIBLE_FOR_BUDGET), so no propagation policy is needed;
  - the active inputs are wired to the physical registrations (D-068).

M7 is NOT_STARTED. No Abaqus, no identification run.
