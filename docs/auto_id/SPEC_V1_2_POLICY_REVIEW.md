> **SUPERSEDED_BY_NORMATIVE_SPEC_V1_2** — historical policy-development evidence. Superseded by the normative [SPEC_V1_2.md](SPEC_V1_2.md) (D-078, SUPERVISOR, 2026-10-09; PR #41 merged as `edb3070`). The content below is the reviewed final state (PR #41 head `62903ef`) and is kept unchanged, including its status line at review time.

# SPEC v1.2 policy review — revised after SUPERVISOR policy decision

| | |
|---|---|
| **Status** | PROPOSED — NOT NORMATIVE — awaiting final SUPERVISOR acceptance (no decision number yet) |
| **Policy direction** | Accepted 2026-10-09, subject to the corrections incorporated here |
| **Draft** | `SPEC_V1_2_DRAFT.md`; machine-readable policy `SPEC_V1_2_POLICY_OPTIONS.json` |
| **Base** | `main` `9bff6c79ee149e9309c3e3697cb96fff4e937c68` (M7 closed, D-077) |
| **Freeze** | Declared before any new FE result. No value chosen from or evaluated on RUN_A / RUN_B |

## 1. Decision table

| Topic | v1.1 | Audit problem | v1.2 rule (revised) | Scientific rationale | Risk | Code change? |
|---|---|---|---|---|---|---|
| **Upper rule (§1)** | no mode may turn a refusal into a number | K1: refusal turned into a released number | **Amended:** two questions declared before execution — A material identification, B specimen / FE-model calibration; **no automatic fallback** from a material refusal to a calibration; material verdict always computed and shown separately | Separates "is this a material property?" from "which constant calibrates this model of this specimen?" without letting either answer replace the other | Back-door release (K1 again); mitigated by pre-declaration, identity binding, no fallback, separate fields | Yes (run / campaign question field) |
| **τ_mf** | none | V4: Σ-only bounds (0.6 % / 0.9 %) mix repeatability with model-form acceptance | **τ_mf ≤ 0.02** in \|Δ ln f\| (accepted, Option A); one campaign-level value, declared before execution, identity-bound; never per mode / family / parameter; never selected after a fit | Model-form acceptance tolerance in frequency space only; deliberately conservative versus the desired few-percent agreement; stricter than 3 %; no tuning freedom. **No conversion to parameter uncertainty is made** | A tolerance widens what passes; mitigated by one fixed maximum declared in advance | Yes (campaign schema, M5 bounds) |
| **Holdout** | fail if \|Δ ln f\| > 3σ (0.9 %) | V4 | pass if \|Δ ln f\| ≤ max(3σ, τ_mf) | Transfer to unfitted families is a model-form question | Passing does not establish parameter precision — stated explicitly; M5 still decides precision | Yes |
| **Pattern test** | systematic if same sign and every \|Δ ln f\| > 2σ (0.6 %) | V4; V5 | systematic if ≥ 2 members, same sign, every \|Δ ln f\| > max(2σ, τ_mf); cross-specimen splits stay with §13 | Same-sign families beyond the declared tolerance still indicate model error | Same as holdout | Yes |
| **Family consistency** | §13, Σ only, p < 0.01 | K2 (implemented, D-076) | **Unchanged; τ_mf never enters Σ, Δχ², bootstrap, p or the shared / separate comparison; FAIL → NO_GLOBAL_PARAMETER_VALUE; τ_mf cannot rescue it** | A shared material vector must explain every specimen within the statistical observation model | None new; guard tests required at implementation | No (guard tests) |
| **Specimen calibration class** | none | K1 pressure to release anyway | **Accepted in concept.** `SPECIMEN_ENGINEERING_CALIBRATION` + `NOT_A_MATERIAL_PROPERTY` + `NOT_TRANSFERABLE_WITHOUT_VALIDATION`; intent pre-declared and identity-bound; identities (specimen, test run, forward model, INP SHA-256, registration, campaign / run, τ_mf); never in a material-property field; gates without override | Honest, governed per-specimen model calibration where a material claim is refused | Misuse as a material constant; mitigated by labels, separate output, no fallback | Yes (gate, record writer) |
| **Calibration precision gate** | M5 envelope for material verdicts only | Final review: the calibration gates had no explicit precision requirement | **conservative_uncertainty = max(birge_adjusted_sd, 0.5 · width(model_form_robustness)) ≤ 0.08** (ln p, as M5); birge_adjusted_sd required; model_form_robustness must be AVAILABLE_COMPLETE_LOO; missing component or > 0.08 → REFUSED, no calibration value released; an optimiser candidate only as `DIAGNOSTIC_OPTIMIZER_CANDIDATE` / `NOT_A_RELEASE_VALUE`; never labelled IDENTIFIED / WIDE; τ_mf not in the envelope; with incomplete Σ the ≤ 0.08 result stays `UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE` | A calibration is a numerical scientific output (§1 B); the evidence must support it at a declared precision | Many candidates will be refused — intended; the gate does not make incomplete covariance complete | Yes (calibration gate) |
| **Per-specimen non-degradation** | campaign-global "improved" flag | V6 | Same governed FIT + HOLDOUT rows of one specimen: **max \|Δ ln f\| not worse AND RMS not worse than the baseline, AND every row ≤ 8 %** | Max protects the worst mode; RMS protects the rest; 8 % is the hard practical ceiling of this class, separate from τ_mf; no per-row improvement requirement (avoids brittle optimum) | Stricter than either condition alone — intended | Yes (calibration gate) |
| **Minimum observability** | M5 rank; strict pairs ≥ 2 | V1 | ≥ k + 1 FIT families, full rank, complete leave-one-FIT-family-out, ≥ 1 HOLDOUT family; **k = 1: 2 FIT + 1 HOLDOUT**; one torsion-sensitive mixed mode never sufficient; a cluster counts once | No single mode or family decides the value; transfer is checked | Many current specimens will not qualify until scans improve — intended | Yes (calibration gate) |
| **S8 output** | block for IDENTIFIED / WIDE (J1, not implemented) | J1 | IDENTIFIED / WIDE: existing rules; NOT_IDENTIFIABLE / NO_GLOBAL_PARAMETER_VALUE: none; calibration: never via the material writer, optional separate fragment with distinct name and warnings | A material block is read as transferable by every downstream user | Hand-copying remains possible; warnings make it deliberate | Yes (M8.6) |
| **Uncertainty wording** | three separate quantities | J5 | mandatory basis; `UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE` while any Σ component is missing or provisional; calibration reports statistical (with basis), Birge only when valid, robustness, missing components, and τ_mf **as an acceptance tolerance, not uncertainty** | States what the numbers are conditional on; never complete experimental uncertainty without Σ_meas | None | Campaign reports already; extend to calibration records |
| **Scan / excluded-mode diagnostics** | not recorded / invisible | V2, V3, J3 | scan coverage is data quality fixed by experiment; high-MAC excluded modes stay diagnostic rows; cluster discovery later inspects the full neighbourhood under frozen rules | Experimental limits are fixed experimentally, not numerically | None | Diagnostics exist; J3 later |
| **Historical data** | — | — | v1.1 records unchanged (RUN_A NO_GLOBAL_PARAMETER_VALUE; RUN_B diagnostic); after v1.2 only `RETROSPECTIVE_DIAGNOSTIC_ONLY`; an accepted v1.2 calibration needs a new v1.2 campaign / run identity declared before the run or re-analysis (archived FE states reusable where valid) | No retroactive upgrade of a refused result | None | No |

## 2. τ_mf options (decided: A)

Reference Σ for the arithmetic only: Σ_setup 0.3 % (PROVISIONAL), Σ_meas NOT_AVAILABLE.

| Option | τ_mf | Holdout bound max(3σ, τ) | Pattern bound max(2σ, τ) | Outcome |
|---|---|---|---|---|
| v1.1 | — | 0.9 % | 0.6 % | repeatability scale (V4) |
| **A** | **2 %** | **2 %** | **2 %** | **accepted as the v1.2 specification maximum** |
| B | 3 % | 3 % | 3 % | not accepted (less strict) |
| C | per family / parameter | varies | varies | rejected (tuning freedom) |

The earlier argument "2 % implies about 4 % in E, inside the 5 % IDENTIFIED threshold" is **withdrawn**: since
|d ln f / d ln E| ≤ 0.5, a 2 % frequency discrepancy corresponds to *at least* about 4 % in E and possibly much more, so
it cannot justify a parameter-uncertainty bound. τ_mf is justified only as a frequency-space model-form tolerance;
parameter uncertainty stays with M5.

## 3. Non-degradation (decided: combined rule)

| Condition | Purpose |
|---|---|
| max \|Δ ln f\| (candidate) ≤ max \|Δ ln f\| (baseline) | the worst mode is not sacrificed |
| RMS Δ ln f (candidate) ≤ RMS Δ ln f (baseline) | many modes are not worsened to improve the worst one |
| every row \|relative error\| ≤ 8 % | hard practical ceiling of the calibration class |

Individual rows need not improve. This 8 % per-row frequency ceiling is a different quantity from the 0.08
conservative_uncertainty precision gate (§1 table, "Calibration precision gate").

## 4. Remaining for final acceptance

1. Final acceptance of this revised draft (decision number to be assigned then).
2. Implementation is a separate, later step: no production code is changed by this policy work.
