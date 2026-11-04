# MAT-2 report: shared offline inverse workflow

Status: **REVIEW_READY**, including the F1 correction below. Not self-accepted. MAT-3 has not started.

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
| `tests/test_plate_material_workflow.py` | New | 72 focused tests after F1 |
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

1. **Declaration checks, no solve:** supported intent, SYNTHETIC-only execution, input source, HOLDOUT independence,
   covariance.
2. **Model identity:** declared identity must equal the opened model; Stage-A specimen, model and evidence kind must match
   the package; bounds must lie inside the stored domain.
3. **Start point:** forward solve with numerical health checks, refusal of frozen rows on a numerically repeated
   eigenvalue, then frequency triggers and the governed +/-5 % cluster review, then the strict baseline check. That check
   verifies the frozen mapping and never changes it.
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

**Unresolved historical-impact question:** whether any historical Auto-ID run stopped this way was not examined. F1 keeps
the default path unchanged, reinterprets no historical result, reruns no campaign and changes no accepted status.

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

The final regression of the F1 code is in the F1 section. **MAT-2 regression at `570c911`**, one process per module, one
BLAS thread, Python 3.14:

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
clusters; frozen rows on a repeated eigenvalue; wrong Stage-A model, specimen, identity and evidence kind; missing package;
bounds and start outside range;
inadmissible point; loss of branch identity; failed residual and orthogonality, at the start and during a fit; incomplete
covariance; FRF peaks and unknown sources; unsupported intent; any non-synthetic study; attempted release; iteration,
solve, time and cancel stops.

## Limitations

- **Real data:** nothing was run on it, and the workflow refuses it. No real matrix package was opened. Its availability is
  UNKNOWN.
- **`SYNTHETIC` is a declared label for the Ritz backend.** The workflow cannot detect measured frequencies declared as
  synthetic. A Stage-A package's stored evidence kind is checked against the declaration.
- **Repeated frozen pairs are refused, not resolved.** The governed cluster review compares individual shapes, so it has no
  basis-independent answer at an exact repeat. A study on a perfectly symmetric model cannot use such a pair until a
  basis-independent review is decided. The refusal limit of 1e-9 in relative spacing is numerical, not scientific.
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
- **`execution_authorization` is recorded text and enables nothing.** There is no real-data authorization mechanism.
- **The default budget and limits** have not been exercised at scale.
- **Full suite, GUI, Abaqus:** not run, as instructed.

## F1 correction

Base `570c911af9c26781b79ec85f1c62ff1f5d45b5ea`. The working two-backend architecture is unchanged. F1 changes no threshold,
SPEC, DECISIONS, ROADMAP, STATUS, registration, accepted evidence or existing policy test. `run_bounded_lm` is untouched.

**CI log access:** raw job logs and the artifact need GitHub authentication (HTTP 403 without it), and no token was read. The
individual failure names come from the owner's review. The rest comes from the public API and from local reproduction.

### Cluster failures

Execution order is forward solve, cluster review, baseline check, rank analysis. The first check that refuses sets the code.

**Root cause.** The fixture started at D11 = D22 on a square plate, where modes 4 and 5 have the same eigenvalue (spacing
9e-16). Any basis of that pair is a valid eigensolver answer, and OpenBLAS on Linux and the Windows build return different
ones. The review and the baseline check compare individual shapes, so the basis decided the outcome. Turning the basis in a
wrapper model, on Windows, with the code at `570c911`:

| Basis angle from the x/y symmetry axes | Cluster not declared | Cluster declared |
|---|---|---|
| 0, 10, 18 degrees | **`DIAGNOSTIC_OPTIMIZER_CANDIDATE`** | `UNRESOLVED_MODAL_CLUSTER`, not confirmed |
| 25, 45 degrees | `UNRESOLVED_MODAL_CLUSTER` | `RANK_DEFICIENT` |
| 90 degrees | `BASELINE_PAIRING_REFUSED` | `UNRESOLVED_MODAL_CLUSTER`, not confirmed |

The 90-degree row gives the same two codes CI reported, and 25 to 45 degrees gives what Windows expected. Python 3.11 on
Windows behaves as Windows does, so the difference is the platform's linear algebra and not the Python version. The Linux basis
itself was not observed.

**Verdict: both the implementation and the fixture.** One declaration could produce a candidate or a refusal depending only on
the eigensolver's basis, which is an implementation defect. The tests also put three separate conditions on one fixture.

**Fix.** A frozen pair within 1e-9 relative spacing at the start point is now refused as `UNRESOLVED_MODAL_CLUSTER` before the
review, with or without a declared cluster. This only adds a refusal. No MAC, frequency, rank or cluster policy changed.

| Condition | Test | Fixture |
|---|---|---|
| Rank-deficient four-parameter system | `test_four_parameters_are_rank_deficient_at_the_symmetric_point` | Same plate, separated modes only. The test first checks the cause: the D22 column equals the D11 column plus u times the u column, within 1e-9 |
| Undeclared modal cluster | `test_undeclared_cluster_is_refused` | Stage-A rotating pair with separated frequencies, so its basis is defined |
| Frozen pairing refused, not changed | `test_wrong_frozen_mapping_is_refused_not_repaired` | Two separated modes swapped; refused before any fit |
| Repeated eigenvalue | `test_frozen_rows_on_a_repeated_eigenvalue_are_refused_in_every_basis` | Three declarations at five angles give one result |

The rank and repeated-eigenvalue tests run across several basis angles, so they do not depend on the platform's choice.

### Governance failures

The reserved engineering-calibration question had been added to `StudyIntent` and to a workflow check. Those two modules are
outside the modules that the three governance tests allow. It is removed from both, without obfuscation and without touching
the scanners. A declaration holding any unsupported intent now gets `UNSUPPORTED_STUDY_INTENT` with no solve and no model
opened. The negative test uses the constant from `domain.campaign_definition`, so it sends the real request. There is no
calibration path, fallback or release path.

### Execution authorization

Only `SYNTHETIC_SOFTWARE_TEST` with `SYNTHETIC` evidence runs. Every other combination gets `NOT_AUTHORIZED` before a model or
package is opened, whatever `execution_authorization` holds. This also refuses `MATERIAL_IDENTIFICATION_RESEARCH` on synthetic
data, which MAT-2 had allowed.

### Frozen provenance

`_frozen_set()` had put the model identity in two file-hash fields, the declaration hash in the experimental-source hash, the
registration identifier in the registration hash, the study name in the job name, and mode-source text in `measured_dofs`.

Those five identity fields now hold `SYNTHETIC_NO_PHYSICAL_SOURCE`, which is not a hash, and `measured_dofs` holds the declared
observation identifiers. The real identities remain in the declaration under their own names. A non-synthetic declaration
reaching this function is refused. `domain/frozen_observations.py` and all accepted frozen records are unchanged.

### Behaviour preserved

Ritz, Ritz with offsets and Stage A were run on the code at `570c911` and on F1 under Python 3.11. Fitted parameters, objective,
statistical sd, robustness ranges, HOLDOUT residuals, leave-one-family-out estimates, statuses and solve counts are **identical
in every bit**. That is expected, since F1 adds refusals and changes only identity fields.

The Stage-A confirmed-pair fit and the published benchmark were not part of that comparison. Their tests pass with unchanged
tolerances.

### Final targeted regression

Python 3.11.17, numpy 2.4.6, scipy 1.17.1, Windows; the CI runs Linux. Run sequentially, one BLAS thread:

| Module | Tests | Result |
|---|---|---|
| `test_plate_material_workflow` | 72 | PASS |
| `test_identification_step` | 13 | PASS |
| `test_spec_v1_2_normative` | 6 | PASS |
| `test_spec_v1_2_policy_draft` | 16 | PASS |
| `test_v12_i1_campaign_question` | 19 | PASS |

126 tests, 0 failures, 0 skipped, 16 s. Budget: about 60 s of 120 s, counting diagnostic probes and one failed run caused by a
wrong solve count in a new assertion. The other MAT-2 modules, the full suite, GUI and Abaqus: NOT_RUN, as instructed.

### Other CI failures

Steps "Run unit tests" and "Qt tests offscreen" (exit code 134) both fail at `570c911`.

| Commit | Content | CI |
|---|---|---|
| `0bea1de` (`origin/main`) | | success |
| `af61c35` | WORKING-DRAFT-R1 | success |
| `00a4c85` | WORKING-DRAFT-R2, the next commit | failure |
| `0a7b8f7` | GUI-UX-R1-F2, no MAT code | failure |
| `1ad75e8` | Documents only, no MAT code; both steps fail | failure |
| `14f36d6` | MAT-1 | failure |
| `570c911` | MAT-2 | failure |

No file under `src/new_gui` or any GUI test changed between `1ad75e8` and F1, and the workspace inventory test lists only
`src/new_gui`. So red CI predates MAT, and the GUI failures named in the review are consistent with GUI work on this branch.
**This is not a test-by-test proof,** because the logs were not readable: a new failure hidden among the old ones cannot be
excluded until the log of the final commit is read. No GUI repair was started.

### Future input requirements

The material workflow is for the single CFRP plate. By the owner's clarification, the "Rotated Plate" UNV files inside the disk
folder named "Sandwich" must not be treated as sandwich-panel material data. A title establishes neither registration nor the
measurement series. Those files were not opened in F1.

Using a real sandwich specimen later would need:

- UNV/UFF with genuinely fitted experimental modes, if available;
- verified specimen geometry, mass, thickness and test conditions;
- independently registered modal shapes and DOFs;
- optional ODB/FE information, for comparison only;
- a verified compatible matrix package for Stage A, not merely an ODB;
- an explicit model-applicability review before using the homogeneous Kirchhoff-Ritz model on a sandwich.

No core, adhesive or skin property may be inferred from fitting one or more frequencies without an appropriate, independently
justified physical model.

## Artifacts

Outside the repository, in `D:\git\abaqus-modal-comparator-work\research\MAT_2\`: `final_targeted.log` and
`final_code.sha256` for `570c911`; `f1_final_targeted.log` and `f1_final_code.sha256` for F1.
