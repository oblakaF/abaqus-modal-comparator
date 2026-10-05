# M5 decision record

**Status:** SUPERVISOR decisions recorded (2026-10-05, M5 entry). Durable items are promoted to
DECISIONS.md D-039–D-044.

**Branch:** `auto-id/m5`, from `main` `8f405c3`.

**Scope of M5:** practical identifiability and uncertainty (SPEC §7, §9, §10, §14, S7; ROADMAP M5).
- No Abaqus or Abaqus Python.
- No real-specimen identification.
- No change to M4 scientific results.

| Mini-step | Status |
|---|---|
| M5.1–M5.4 | `REVIEW_READY` (checkpoint M5-A) |
| M5.5–M5.9 | `TODO` |

---

## 1. Data scope

- **Synthetic gate:** the M5 stage-gate nuisance and identifiability cases are synthetic.
- **Each synthetic case defines explicitly:**
  - its sensitivity matrix;
  - Σ;
  - its nuisance priors;
  - `registration_limited = false`.
- **Not needed to close M5:** real t_face or k_core FE columns. Real nuisance sensitivities and
  priors are future real-application work.
- **Test tolerances** (for example "q ≈ 0") belong to the tests only. They are not scientific
  thresholds.

## 2. Jacobian at p̂ (M4.9 twin positive control)

- **Source:** the final accepted **Broyden-updated** LM Jacobian, reconstructed
  deterministically from the committed M4.9 journal (`reconstruct_lm_jacobian`). It is labelled
  as such.
- **Not used:** a fresh finite-difference Abaqus Jacobian.
- **Not evidence:** the twin is a records-based positive control, not evidence of
  real-specimen identifiability.
- **Not interchangeable:** M4 `local_sd` is never substituted for M5 `statistical_sd`.
- **Synthetic gate cases:** use their explicitly defined matrices.

## 3. Nuisance priors (M5.2)

- **Machinery:** prior rows C_prior^(−1/2)·E_nuis, for nuisance parameters only.
- **No defaults:** no default prior values exist.
- **Refusals:** a nuisance parameter without its required prior refuses (`NuisancePriorRefusal`);
  so does a non-positive prior sd.
- **Synthetic priors:** part of the synthetic case definition and provenance.
- **Flagging:** any provisional prior carries `provisional = True`, which is reported in
  `provisional_inputs`.

## 4. Practical rank (M5.3)

- **Rule:** rank uses rcond = 1e-3 (SPEC §10). It is a module constant, not an argument.
- **Rank deficiency is a hard block:** no covariance, no sd, no pseudo-inverse path, no user
  override.
- **Diagnostics only:** condition number, correlations and pairwise cosines.

## 5. q_G (M5.4)

- **Definition:** q_j = ‖(I − P_N) a_j‖ / ‖a_j‖ on the columns of A, for every parameter; q_G is
  the G12 value.
- **No verdict threshold:** q_G is diagnostic evidence. The verdict is decided by the full
  uncertainty and rank calculation.
- **Required synthetic absorption case:**
  - G12 sensitivity is absorbed by a data-relevant, weakly constrained k_core;
  - q_G ≈ 0;
  - the posterior sd of G12 exceeds the SPEC §10 fit limit;
  - the evidence is NOT_IDENTIFIABLE-compatible.

## 6. Σ and `statistical_sd`

- **Σ:** explicit for every synthetic case. Model discrepancy never enters Σ (D-003).
- **M4.9 twin positive control:** Σ = the accepted synthetic noise definition (σ = 0.003; D-036).
  The provisional real-data σ_setup is not reinterpreted as validated uncertainty.
- **Real data:** a missing Σ_meas remains NOT_AVAILABLE; it is never invented.
- **`statistical_sd` (M5.5):** must come from the full M5 system, including nuisance columns and
  prior rows where present.

## 7. Birge definition (M5.6)

- χ² = Σ of squared whitened **fit** residual terms only. Prior rows and holdouts are excluded; a
  confirmed cluster is one term.
- dof = n_fit_terms − n_fitted_parameters, counting all estimated parameters, including fitted
  nuisance parameters.
- **dof ≤ 0** → the Birge calculation (and a green verdict) is refused.
- s_B = √max(1, χ²/dof); `birge_adjusted_sd` = `statistical_sd`·s_B.
- `birge_adjusted_sd` is populated only when the residual-pattern test passes (SPEC §9).

## 8. `model_form_robustness` (M5.7)

- **Method:** linearised leave-one-family-out at p̂. No nonlinear or Abaqus refits.
- **For each fitted modal family:**
  - remove all its fit terms;
  - keep the same parameter, nuisance and prior contract;
  - solve the reduced local linearised system around p̂.
- **Refusal:** if a reduced system is rank-deficient (same rcond rule), that case is REFUSED, and
  the robustness result cannot support a green verdict.
- **Reporting:** the range of the resulting estimates, in % of p̂. It is not `statistical_sd`,
  not 1σ, and not part of Σ.
- **Holdouts:** remain holdouts; they are never promoted into the fit.

## 9. Residual-pattern test: clarification for singleton families (M5.8)

**The SPEC text is ambiguous for single-member families. This clarifies it; the thresholds are
unchanged.**

- **Fit-family rule:** a family can trigger the same-sign, > 2σ systematic pattern only when it
  contains **at least two** fit residual terms, all of the same sign and each with |r| > 2
  (whitened).
- **Singletons:** a single fit residual cannot establish a family-wide pattern. Unrelated
  singleton families are never merged to manufacture a pattern.
- **Holdout rule (unchanged):** any |r_holdout| > 3 (whitened) fails the check, and no green
  verdict is allowed.

## 10. Family consistency (M5.9)

- **Synthetic gate:** in the synthetic single-specimen gate, `family_consistency = NOT_AVAILABLE`
  wherever the later cross-family / cross-specimen check cannot be evaluated.
- **NOT_AVAILABLE is not PASS.** In the explicitly synthetic M5 gate it does not by itself stop
  the M5 machinery being exercised or passed.
- **Real data:** for production verdicts the SPEC requirement stands. If the required family
  consistency is unavailable, a green IDENTIFIED verdict is blocked.

## 11. registration-limited

- **Authoritative source:** the existing M2 registration diagnostic. No second metric or threshold
  is created.
- **Synthetic cases** without a physical registration problem set
  `registration_limited = false` explicitly.

## 12. S4 noise control

- **Not run in M5:** the ±2.5 % noise-control solves. The synthetic gate uses exact matrices.
- **Still mandatory later:** for real FE sensitivity columns the requirement remains mandatory and
  needs a separate HUMAN Abaqus gate.

## 13. Retained M4 artifacts

- **No deletion** in M5-A.
- The M4 ODBs and INPs are not required for M5.
- Clean-up follows separately, after the smoke-provenance archival question is resolved.

## 14–15. Checkpoint M5-A (implemented)

**Module:** `src/services/practical_identifiability.py` (new; SPEC-conformant). The legacy Stage-A
`identifiability_service` is not modified.

**Typed records:**
- `ParameterDefinition` (GLOBAL / NUISANCE plus specimen);
- `ObservationTerm` (a confirmed cluster is one term, the mean of its member rows, matching r_C);
- `SensitivityMatrix` (fit terms only, per-column provenance);
- `CovarianceComponent` / `ObservationCovariance` (explicit Σ, symmetric positive definite, with a
  provisional flag);
- `NuisancePrior`;
- `PracticalSystem` (A = [S~; prior rows], with a system hash);
- `PracticalIdentifiabilityResult`: rank status, singular values, C in ln p, sd foundation, the
  §10 sd > 8 % evidence, diagnostics, q projections, provisional inputs, refusal reasons;
- `ReconstructedJacobian`.

**Hashing:**
- canonical SHA-256, as elsewhere in Auto-ID;
- the system hash covers the inputs only;
- result hashes round floats to 12 significant digits, so they are platform-independent.

**Implementation notes for SUPERVISOR confirmation:**
- **Whitening:** S~ = L⁻¹·S with Σ = L·Lᵀ (Cholesky). AᵀA is independent of the chosen square root.
- **Pairwise cosines:** computed on the whitened data block S~, as SPEC §10 defines
  cos(s~_G, s~_core). q is computed on the columns of A, including the prior rows.
- **SPEC §10 "sd_j > 8 %":** compared on sd in ln p, `sd_ln > 0.08` (first-order relative sd). It
  is reported as evidence for M5.9; no verdict is issued here.

**Tests:** `tests/test_practical_identifiability.py`, synthetic, no Abaqus:
- A–N as specified;
- a weak-nuisance contrast;
- a module-boundary guard;
- the M4.9 twin positive control, from committed records only.

## 16. Governance

- **DECISIONS.md:** D-039 to D-044.
- **STATUS and ROADMAP:** M5 `IN_PROGRESS`; M5.1–M5.4 `REVIEW_READY`; M5.5–M5.9 `TODO`.
- **Abaqus runs:** 0.

---

## 17. M5-A review and checkpoint M5-B (2026-10-05)

### 17.1 SUPERVISOR confirmations of M5-A

- **8 % rule:** the SPEC §10 evidence uses `sd_ln > 0.08`, with no internal conversion to a
  physical-space threshold.
- **Cosines:** pairwise sensitivity cosines on the whitened block S~, diagnostics only.
- **q:** projections on the full augmented system, including the prior rows. There is no q_G
  threshold.
- **Whitening:** Cholesky whitening approved. Posterior covariance and conclusions are invariant
  to the Σ square-root representation.
- **Linux flake:** the `test_registration_factory` failure does not block M5-A: the path is
  untouched and the identical commit passed on rerun. It is not fixed inside M5. See the
  technical-debt note in §17.3.

### 17.2 Checkpoint M5-B implemented (M5.5, M5.8, M5.6)

**Module:** `src/services/identification_uncertainty.py` (new; no Abaqus, no legacy imports).

**M5.5 `statistical_sd()`:**
- Computed only from a `PracticalSystem`. Anything else, including an M4 `local_sd`, raises a
  TypeError.
- Reports `statistical_sd_ln` = √C_jj of the full augmented system, plus
  `statistical_sd_percent_first_order` = 100·sd_ln (a label, not a policy conversion).
- Carries the Σ components (name, provenance, provisional), the priors, the provisional inputs, a
  required `context` label and the system and analysis hashes.
- Rank deficiency → `REFUSED_RANK_DEFICIENT`, with no numbers (inherited from M5.3).

**M5.8 `residual_pattern_test()` (D-043, exactly):**
- **Fit families:** grouped by M4.3 family identity. A family with at least two fit terms triggers
  only if all its terms have the same sign and each has |r| > 2. Singleton families never trigger
  and are never merged.
- **Holdouts:** any |r| > 3 fails.
- **Inequalities:** strict, so |r| = 2 and |r| = 3 do not trigger.
- **Clusters:** `residual_terms()` binds the M4.7 order (fit rows, then confirmed clusters) to
  families, and a cluster is one term.
- **Implementation note for confirmation:** a confirmed cluster whose members share one M4.3
  family belongs to that family. If its members' families differ, it gets the composite key
  `F_a+F_b`. It is never merged into an unrelated family and acts as its own group.

**M5.6 `birge_adjustment()` (D-041):**
- χ² = Σ r² over fit terms only.
- dof = n_fit_terms − n_fitted_parameters (all system parameters, including nuisance).
- s_B = √max(1, χ²/dof).
- **Statuses:**
  - `AVAILABLE` only when the pattern test passed;
  - `BLOCKED_PATTERN`: `birge_adjusted_sd` is NOT_AVAILABLE, with the reasons;
  - `REFUSED_DOF` when dof ≤ 0;
  - `REFUSED_STATISTICAL` when `statistical_sd` is unavailable.
- `statistical_sd` is always kept separately; the quantities are never merged (D-012).
- The fit terms must equal the system's terms, in order.

**Tests:** `tests/test_identification_uncertainty.py` (19; cases A–P plus mixed-sign / one member
≤ 2 / strict inequalities, rank refusal of Birge, and term binding). The module-boundary guard of
`tests/test_practical_identifiability.py` covers both M5 modules.

**M4.9 twin synthetic records-based control (P; not real-specimen uncertainty):**

| Quantity | E | G12 |
|---|---|---|
| `statistical_sd_ln` | 0.002064 | 0.009951 |
| `birge_adjusted_sd_ln` | 0.002115 | 0.010195 |

- Pattern test PASS: 21 singleton fit families; holdout |r| at most 0.31.
- χ² = 19.946 over dof 19, so s_B = 1.0246.
- Not refused.

### 17.3 Technical debt (unrelated to M5; not fixed in M5)

`tests/test_registration_factory.py::test_no_full_model_contamination` is flaky. It scans the
serialised registration for the substring `d11`, while the registration hash depends on a
temporary path and mtime, so it fails by chance (about 1.5 % per run). It is to be fixed
separately, for example by excluding hash fields from the token scan.
