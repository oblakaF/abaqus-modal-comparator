# MAT-2 report: shared offline inverse workflow

Status: **REVIEW_READY**. Not self-accepted. MAT-3 has not started.

For the reviewer of MAT-2. Base: accepted MAT-1 `14f36d608420bb5324e1b49be7f644340c8c45d9`; branch
`feature/materials-offline-v1`; `origin/main` at start `0bea1de68dc346d20958e6f53a9e1d634a870f5d`.

A result is at most `DIAGNOSTIC_OPTIMIZER_CANDIDATE` with `NOT_A_RELEASE_VALUE`. Recovering known synthetic values tests
the software and says nothing about a real material. M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and the production
Auto-ID block are unchanged. No SPEC, DECISIONS, ROADMAP, STATUS, threshold, registration or historical observation was
edited.

## Files

| File | Change | Why |
|---|---|---|
| `src/domain/plate_inverse_problem.py` | New | Frozen declaration, result contract, separate statuses, refusal codes |
| `src/services/plate_material_workflow.py` | New | The one workflow over both backends |
| `tests/test_plate_material_workflow.py` | New | 67 focused tests |
| `src/services/identification_step.py` | Opt-in additions | Mixed coordinates in the existing loop. Default path unchanged |
| `src/services/plate_forward_adapter.py` | Three small additions | Orthonormality diagnostic for Stage A, the existing (D, D66, r) sensitivity coordinate, the stored domain in N*m |
| `docs/materials/MAT_2_REPORT.md` | New | This report |

No GUI, project-schema or unrelated change.

## What is reused, not rewritten

`run_bounded_lm`, `lm_step`, `broyden_update` (no second optimizer); `pair_baseline`; `FrozenObservationSet`;
`build_objective_design`, `evaluate_objective`, `RowSigma`; `track_branches`; `cluster_triggers`, `confirm_cluster`;
`assemble_system`, `analyse_practical_identifiability` (rcond 1e-3); `statistical_sd`, `residual_pattern_test`,
`birge_adjustment`; `classify_mode_source`; `StageAMatrixForwardBackend`; `compute_stage_a_sensitivity`.

## Workflow

1. **Declaration checks, no solve:** intent, authorization, input source, HOLDOUT independence, covariance.
2. **Model identity:** declared identity must equal the opened model; Stage-A specimen, model and evidence kind must match
   the package; bounds must lie inside the stored domain.
3. **Start point:** forward solve with numerical health checks, then frequency triggers and the governed +/-5 % cluster
   review, then the strict baseline check. That check verifies the frozen mapping and never changes it.
4. **Identifiability before fitting:** rank and the 8 % limit on the complete tracked sensitivity matrix.
5. **Fit:** bounded LM on whitened ln-frequency residuals. MAC is not an input. Every point is tracked from the last accepted
   state only.
6. **Final accepted point:** the objective is replayed, sensitivities are recomputed and cross-checked analytically, then
   rank, correlation, q, statistical_sd, pattern test, Birge, HOLDOUT and leave-one-FIT-family-out re-fits.

**Coordinates:** Ritz `(ln D11, ln D22, ln D66, u)`, with `D12 = u*D22`. Stage A `(ln D, ln D66, r)`, the existing
`StageAParameterization` physical form with its existing BALANCED sensitivities and stored mass term. Neither logs the
signed coordinate. The existing unconstrained `atanh(r)` form is not used for the LM step; the box on `r` stays inside
`|r| < 1`.

**Numerical defaults follow SPEC 8 and 6 S4:** 5 iterations, stop at 0.2 sd, +/-5 % differences. A study can declare more
iterations; the declaration hash binds that choice.

## A defect found in the existing LM path, for an owner decision

**The default `run_bounded_lm` can report `CONVERGED` after rejected steps.** Rejections raise mu, damping shrinks the step,
and the stop rule then sees a small step. It also tests the step after bound projection. I did not change this, because
the plan requires historical results to stay as they are: `test_default_path_keeps_its_historical_stop_after_rejections`
records the behaviour.

The mixed path avoids it. Convergence is judged on the undamped step with a fresh Jacobian, so damping cannot produce it.
Whether historical Auto-ID runs were affected was not examined.

## Numerical outcomes

All inputs are SYNTHETIC. Noise-free cases, except the second row. Statistical sd uses a declared 0.1 % sigma per row.

| Case | Start | Fitted | Known | sd |
|---|---|---|---|---|
| Ritz D11 | 13 | 12.000139 | 12 | 0.00153 (ln) |
| Ritz D22 | 6.5 | 7.000090 | 7 | 0.00175 (ln) |
| Ritz D66 | 2.5 | 2.300063 | 2.3 | 0.00173 (ln) |
| Ritz u | 0.10 | 0.149767 | 0.15 | 0.0104 (absolute) |
| Stage A D, constant M | 0.34 | 0.3599999 | 0.36 | 0.00128 (ln) |
| Stage A D66, constant M | 0.046 | 0.0500000 | 0.05 | 0.00207 (ln) |
| Stage A r, constant M | 0.05 | 0.0900000 | 0.09 | 0.00059 (absolute) |
| Stage A D, stored mass slope | 0.34 | 0.3599999 | 0.36 | 0.00133 (ln) |

Ritz used 119 solves, 4 iterations, objective 4848 to 7.3e-4, rank 4, condition 8.9, largest eigen residual 5e-13, and
analytic against tracked sensitivities within 6.5e-8. Stage A used 86 solves and rank 3.

With deterministic offsets of up to 0.2 % added to the FIT frequencies, the Ritz fit gave D11 = 11.9628, D22 = 6.9829,
D66 = 2.3126, u = 0.1503, and HOLDOUT residuals of -1.22 and -0.65 sigma. Leave-one-family-out ranges were D11 11.946 to
11.972, D22 6.975 to 7.018, D66 2.309 to 2.316, u 0.144 to 0.159. These are ranges, not standard deviations.

### Published benchmark

Liu and Banerjee, *Computers & Structures* 164 (2016) 108-126, Table 1, row FFFF, M = N = 20, square isotropic plate,
nu = 0.3, modes 4 to 11. Read from the accepted manuscript at City Research Online. Degree 14, tolerance declared before
the first run: 1e-4 in the parameter.

| Table 1 | 13.4682 | 19.5961 | 24.2702 | 34.8009 | 34.8009 | 61.0932 | 61.0932 | 63.6861 |
|---|---|---|---|---|---|---|---|---|
| Ritz | 13.46820 | 19.59614 | 24.27020 | 34.80089 | 34.80089 | 61.09323 | 61.09323 | 63.68614 |

Largest difference 4.0e-5: **PASS**.

Text extraction corrupted the symbols of the parameter definition. I used `omega*a^2*sqrt(rho*h/D)`, which the agreement
in all eight values supports, but I did not see the rendered equation. This checks the forward solver for one isotropic
case. It does not validate the orthotropic coupling or any real material.

## Tests

**Final-code focused regression**, one process per module, one BLAS thread:

| Module | Tests | Result |
|---|---|---|
| `test_plate_material_workflow` | 67 | OK |
| `test_plate_ritz_forward` | 55 | OK |
| `test_plate_forward_adapter` | 44 | OK |
| `test_identification_step` | 13 | OK |
| `test_synthetic_twin` | 30 | OK |
| `test_m4_stage_gate` | 19 | OK, 2 skipped: data stores `snadwich` and `carbon-project-archive` not configured |

228 tests, 0 failures, 2 skipped. Wall time 64 s. **Budget: about 206 s of 300 s** across all runs, including failed ones.

**Positive, both backends:** recovery of known values (u positive, zero, negative); correct identity under changed mode
order; same declaration gives the same result hash; stored mass slope used; confirmed rotating pair counted as one term;
HOLDOUT data and experimental shapes do not change the fit.

**Negative, each returning a specific code and no candidate:** rank-deficient (too few terms, collinear columns, symmetric
square plate, unobservable r); weak parameter above 8 %; missing and non-independent HOLDOUT; unresolved and falsely declared
clusters; wrong Stage-A model, specimen, identity and evidence kind; missing package; bounds and start outside range;
inadmissible point; loss of branch identity; failed residual and orthogonality, at the start and during a fit; incomplete
covariance; FRF peaks and unknown sources; calibration intent; unauthorized non-synthetic study; attempted release; iteration,
solve, time and cancel stops.

## Limitations

- **Real data:** nothing was run on it. No real matrix package was opened. Its availability is UNKNOWN.
- **Benchmark coverage:** one isotropic published case. No independent reference with D11 != D22 and D12 != 0: NOT_RUN.
- **Stage-A fixtures are small diagonal or 2-by-2 block matrices,** so they test the adapter and not an FE model.
- **`setup_provisional`, Sigma diagonal:** covariance is diagonal by declaration, and correlated terms are named as missing.
- **Not propagated:** registration, mass and thickness uncertainty, and covariance of the conditional E, G and nu values. These are
  listed in each result. Mass and thickness are fixed inputs during a fit.
- **No fixed-parameter path:** a weak parameter refuses the study. SPEC 10 allows fixing it at its start value with
  NOT_IDENTIFIABLE, and that path is not built. No nuisance priors.
- **Signed coordinate:** the 8 % limit is not applied to u or r, and no absolute precision rule is approved. Every result says so.
- **Cluster review is axis by axis,** as governed. A repeated pair can pass as individually stable and rotate under a combined
  step, which ended in a branch-loss refusal in testing (modes 6 and 7 of the square plate). That is safe but can stop a study.
- **HOLDOUT tracking:** losing a HOLDOUT branch stops the whole fit.
- **FE-to-FE MAC for Stage A is unweighted,** since zero-mass DOFs rule out the tracker's positive weights. Ritz uses mass weights.
- **`execution_authorization` is a stated text gate,** not a verified approval. The default budget and limits have not been
  exercised at scale.
- **Python 3.11 (CI version):** not run locally. Code ran on 3.14.6.
- **Full suite, GUI, Abaqus:** not run, as instructed.

## Artifacts

`D:\git\abaqus-modal-comparator-work\research\MAT_2\final_targeted.log` and `final_code.sha256`, outside the repository.
