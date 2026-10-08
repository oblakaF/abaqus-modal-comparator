# SPEC v1.2 policy review — PROPOSED, not accepted

| | |
|---|---|
| **Status** | PROPOSED — NOT NORMATIVE — awaiting SUPERVISOR decision |
| **Draft** | `SPEC_V1_2_DRAFT.md`; machine-readable options `SPEC_V1_2_POLICY_OPTIONS.json` |
| **Base** | `main` `9bff6c79ee149e9309c3e3697cb96fff4e937c68` (M7 closed, D-077) |
| **Freeze** | Declared before any new FE result (SP10, t_face, M7 re-run). No candidate was chosen from or evaluated on RUN_A / RUN_B |

## 1. Decision table

| Topic | v1.1 | Audit problem | v1.2 proposed rule | Scientific rationale | Risk | Code change? |
|---|---|---|---|---|---|---|
| **τ_mf** | none; model form only via pattern test, Birge, leave-one-family-out | V4: Σ-only bounds (0.6 % / 0.9 %) mix repeatability scale with model-form acceptance | Declared acceptance tolerance on \|Δ ln f\|, **τ_mf = 0.02 fixed by the specification**; campaign declares it before execution (identity-bound), may only declare smaller; never in Σ, Φ, whitening, uncertainty or §13 | Separates "how repeatable is the measurement" from "how wrong may the model be"; 2 % keeps the implied parameter scale (≥ 4 % in ln E, since d ln f / d ln E ≤ 0.5) inside the 5 % IDENTIFIED target | A tolerance always widens what passes; mitigated by a single fixed value, no per-family freedom, declaration before execution | Yes (campaign schema, M5 bounds) |
| **Holdout** | fail if \|r\| > 3 (\|Δ ln f\| > 3σ = 0.9 %) | V4: 0.9 % is a repeatability bound, unrealistic for sandwich model form | pass if \|Δ ln f\| ≤ max(3σ, τ_mf) | Holdout tests model transfer to unfitted families; the right scale is the declared model-form tolerance, not repeatability | Torsion holdouts (default selection) will often still fail — intended: weak torsion modelling stays visible | Yes (M5 pattern evaluation, when τ_mf declared) |
| **Pattern test** | systematic if same sign and every \|r\| > 2 (0.6 %) | V4 (scale); V5 (misses cross-specimen splits) | systematic if ≥ 2 members, same sign, every \|Δ ln f\| > max(2σ, τ_mf); cross-specimen splits stay with §13 | Same-sign families beyond the declared model-form tolerance still mean model error; splits between specimens are a family question | A 1.5 % same-sign family no longer blocks Birge — acceptable only because τ_mf is fixed in advance | Yes (same place) |
| **Family consistency** | §13, p < 0.01, χ² or bootstrap; mandatory for global parameters | K2 (now implemented, D-076) | Unchanged; **τ_mf never enters §13 and can never convert FAIL into PASS**; not evaluable → no family value | Shared material vector must explain every specimen within the statistical observation model; model-form tolerance is not a licence for specimen inconsistency | None new; the separation must be guarded by tests when implemented | No (guard tests only) |
| **Specimen calibration class** | none; only IDENTIFIED / WIDE / NOT_IDENTIFIABLE | K1 showed the pressure to release a number anyway | New optional class `SPECIMEN_ENGINEERING_CALIBRATION` (+ NOT_A_MATERIAL_PROPERTY, NOT_TRANSFERABLE_WITHOUT_VALIDATION), one specimen, separate output, all refusal conditions except §13 and the σ-only bounds | Engineering users need a governed, honest per-specimen model calibration; making it explicit and labelled is safer than informal reuse of an optimiser value | **Main risk:** re-creating K1 through the back door. Mitigation: material verdict shown first and unchanged; never in material fields; SUPERVISOR must decide whether §1 admits this narrower question at all | Yes (new class, record writer) |
| **Per-specimen non-degradation** | campaign-global "improved_or_consistent" | V6: global flag hid SP-02 worsening | Rule A: per specimen, max \|Δ ln f\| over FIT + HOLDOUT at the candidate ≤ at the governed baseline; every row ≤ 10 % | Simple, deterministic, cannot hide one specimen's worsening behind another's improvement | Strict: a calibration that improves RMS but raises the worst row slightly is refused (accepted conservatism) | Yes (calibration class only) |
| **Minimum observability** | M5 rank; strict pairs ≥ 2 | V1: 5 of 21 modes strict, 3 FIT; SP-13 one FIT row | Calibration needs ≥ k + 1 FIT families, leave-one-family-out complete, ≥ 1 holdout family; for k = 1: 2 FIT families + 1 holdout | No single mode or family may decide the value; a holdout must check transfer | Many current specimens will not qualify until scans improve — intended | Yes (calibration gate) |
| **S8 output** | Engineering Constants block for IDENTIFIED / WIDE (not implemented, J1) | J1 | IDENTIFIED / WIDE: block per existing rules; NOT_IDENTIFIABLE / NO_GLOBAL_PARAMETER_VALUE: none; calibration: never an ordinary material block — separate record, distinct material name, warning header | A material block is read as a transferable property by every downstream user | A user can still copy numbers by hand; the warnings make that a deliberate act | Yes (M8.6 writer) |
| **Uncertainty wording** | three quantities kept separate | J5: statistical_sd looks more certain than the evidence | Mandatory basis: CONDITIONAL_ON_AVAILABLE_COVARIANCE while any Σ component is NOT_AVAILABLE or PROVISIONAL (already in campaign reports, D-076) | States what the number is conditional on, without inventing Σ_meas | None | Already in campaign reports; extend to every result output |
| **Scan / excluded-mode diagnostics** | scan coverage not recorded; excluded modes invisible | V2, V3, J3 | Scan coverage is data quality (recorded, fixed by experiment, never by τ_mf); high-MAC excluded modes stay as diagnostic rows (never fitted); cluster discovery should later inspect the full neighbourhood under frozen rules | Experimental limitations must be visible and fixed experimentally, not absorbed numerically | None | Diagnostics exist (D-076); J3 later |

## 2. τ_mf options (no historical data used)

Reference Σ for the arithmetic: Σ_setup 0.3 % (PROVISIONAL), Σ_meas NOT_AVAILABLE. Implied parameter scale uses only
the generic bound d ln f / d ln E ≤ 0.5 (f ∝ √stiffness).

| Option | τ_mf | Holdout bound max(3σ, τ) | Pattern bound max(2σ, τ) | Implied min. scale in ln E | Assessment |
|---|---|---|---|---|---|
| v1.1 | — | 0.9 % | 0.6 % | 1.8 % | repeatability scale; unrealistic for sandwich model form (V4) |
| **A** | **2 %** | **2 %** | **2 %** | **≥ 4 %** | **Recommended.** Below half of the preferred engineering target (~5 %, D-066 / D-069); implied parameter scale stays inside the 5 % IDENTIFIED threshold; one fixed value |
| B | 3 % | 3 % | 3 % | ≥ 6 % | Not recommended: implied parameter scale exceeds the IDENTIFIED threshold, so a green verdict could sit on model form as large as the claimed uncertainty |
| C | per family / parameter | varies | varies | varies | Rejected for v1.2: multiplies tuning freedom and invites post-hoc selection |

**Recommendation:** Option A, τ_mf = 0.02 as a specification maximum, declared per campaign before execution and
identity-bound; smaller declared values allowed, larger ones only by a specification change.

## 3. Non-degradation rule options

| Rule | Definition (per specimen, governed FIT + HOLDOUT rows) | Pros | Cons |
|---|---|---|---|
| **A (proposed)** | max \|Δ ln f\|(candidate) ≤ max \|Δ ln f\|(baseline); every row ≤ 10 % | One comparison, deterministic, no averaging; a worse worst row is always visible | Refuses a calibration that improves most rows but slightly worsens the worst one |
| B | RMS(candidate) ≤ RMS(baseline) and max \|Δ ln f\|(candidate) ≤ 10 % | Rewards overall improvement | A single row may worsen substantially while RMS improves — the kind of hidden degradation the audit found (V6) |

## 4. Decisions requested from the SUPERVISOR

1. Accept or reject τ_mf as a concept, and the value (Option A, 0.02, specification maximum).
2. Accept or reject the holdout and pattern amendments (max(kσ, τ_mf)).
3. Confirm that §13 stays τ_mf-free (no rescue of a family by τ_mf).
4. **Decide whether SPEC §1 admits the narrower specimen-calibration question at all**, and if so accept the class
   with its conditions, observability minimum (2 FIT families + 1 holdout for k = 1) and non-degradation rule A.
5. Accept the S8 output separation and the mandatory uncertainty-basis wording.
6. Decide separately whether historical RUN_A / RUN_B data may ever be re-analysed under v1.2 (not proposed here).

Nothing in this review changes production behaviour, SPEC v1.1, M5, the M7 records or the family-consistency
implementation.
