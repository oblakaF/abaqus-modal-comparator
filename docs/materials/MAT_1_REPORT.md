# MAT-1 report: offline forward backends

Status: **REVIEW_READY**. Not self-accepted. MAT-2 has not started.

For the reviewer of MAT-1. Code baseline `0a7b8f7da62b189c4c90f3c3ffbb4436da276d1c`; documentation base
`1ad75e8de65f3a027c0610b49167b753f9b18245`; branch `feature/materials-offline-v1`; `origin/main` at start
`0bea1de68dc346d20958e6f53a9e1d634a870f5d`.

A forward result is a model prediction, not a material identification. M8 GATE NOT_MET, D-077
NO_GLOBAL_PARAMETER_VALUE and the production Auto-ID block are unchanged. No SPEC, DECISIONS, ROADMAP or STATUS
file was edited.

## Files

| File | Content |
|---|---|
| `src/domain/plate_material_problem.py` | Typed contracts: geometry and units, parameters, mixed coordinates, observations, resource limits, capabilities, provenance, results, refusal codes, exact identity hash |
| `src/services/plate_ritz_forward.py` | Standalone solver, rigid-subspace separation, observation evaluation, sensitivities, central-difference and order checks |
| `src/services/plate_forward_adapter.py` | The two backends behind one result contract, and the Stage-A package reader and writer |
| `tests/test_plate_ritz_forward.py`, `tests/test_plate_forward_adapter.py`, `tests/plate_forward_support.py` | Focused tests, declared test caps, Abaqus guard |

No existing file changed. The GUI, launcher, project schema, comparator, optimizer and material-release logic are untouched.

Reused without change: `StageAAffineBasis`, `StageAMatrixParameters`, `StageAMatrixNodeMap` and
`solve_generalized_eigenproblem` (`matrix_model_service.py`), `compute_stage_a_sensitivity` (`sensitivity_service.py`),
`stage_a_basis_identity` (`stage_a_identification_service.py`), and through them `stage_a_parameterization.py`.

## KIRCHHOFF_RITZ_4D

**Computes:** frequencies and mass-orthonormal shapes of a free-free rectangular plate with independent D11, D22, D12
and D66, using NumPy and SciPy only. The basis is a hierarchical tensor-product Legendre basis. The matrices use
Gauss-Legendre quadrature with `degree+1` points per axis, exact for the polynomial degree involved, and are cached by
exact a, b and degree.

- **Rigid forms:** `span{1,x,y}` is separated by an M-orthogonal split and verified on each solve (`K R`, `R^T M Z` and the
  field values at check points). No frequency cutoff and no six-mode rule is used. The FE classifier is untouched.
- **Solve:** the elastic block is solved as `M v = mu K v` with K scaled to a unit diagonal. A first version using
  `eigh(K, M)` lost about 1e-7 on the first mode at a high stiffness contrast and fell below the exact value, which
  Rayleigh-Ritz forbids. A non-positive-definite K is refused; no `abs()` or clipping exists.
- **Observations:** w, its gradient, and the measured value `d_z*w - z*(d_x*w_x + d_y*w_y)` at registered points. A set
  needs a registration identity. An off-normal direction without a declared surface offset is refused.
- **Sensitivities:** physical derivatives, S1 to S4 in `(ln D11, ln D22, ln D66, u)`, and J11, J22, J12, J66 with the
  corrected chain rule. `u` is not logged.
- **Degeneracy:** a mode in a cluster, or at a window boundary that cuts a cluster, gets no single-branch derivative: its
  row is NaN and `simple_mode_row` refuses. A basis-invariant cluster derivative is provided instead.
- **Order check:** `ritz_order_convergence` runs a fixed schedule and reports observed changes. It assumes no rate and
  issues no verdict, because no convergence tolerance has been approved.

**Limits:** constant D, negligible B, D16 and D26, thin plate. Thickness alone does not prove applicability, and nothing
here checks shear, rotary inertia, prestress or supports. The degeneracy gap (1e-7, relative) is an unapproved numerical
policy. Complex modal values and FIT/HOLDOUT belong to MAT-2.

## STAGE_A_MATRIX_3D

**Computes:** frequencies and DOF shapes from a stored Stage-A basis, through the existing reconstruction and solver, with
the existing rigid-spectrum classifier. It keeps three parameters, D22 = D11 (a different D22 is refused, not averaged),
exact DOF and node identities, the stored validity domain (outside it is refused, not extrapolated) and the stored mass
behaviour. A slope is used only if stored, and a mismatch between manifest and archive is refused. The sum-of-J rule is not
applied. Sensitivities come from the existing service, which treats its top solved mode as a guard, so one extra mode is
solved.

**Package format, a new decision for review:** the repository had no stored form of `StageAAffineBasis`: it only exists in
memory after `.mtx` import. MAT-1 therefore defines `abm/stage-a-matrix-package/v1`: a JSON manifest plus an `.npz`
without pickle. `write_stage_a_package` stores an existing in-memory basis, computes no matrix and overwrites nothing.

**Reading order:** manifest size and identity, domain, file size, SHA-256, then zip and npy headers (shapes, types, DOF and
nonzero caps) before any array is loaded. After loading: finiteness, sparse format, the basis's own checks, and the
`basis_km_hash` and `dof_mapping_hash` identities.

**Limits:**
- **No real package was opened.** No disk was scanned for one, so availability for any real plate is UNKNOWN.
- Existing `.mtx` exports cannot be opened directly. They need the existing `read_abaqus_matrix_pair` and
  `build_stage_a_affine_basis`, then the writer; that conversion was not built or run.
- Coordinate observations are refused: the package holds no node coordinates.
- A package's `validation_evidence` is passed through as text and not assessed.

## Test caps, declared before testing

Development resource limits, not scientific tolerances: 225 Ritz coefficients (degree 14), 64 MiB allocation, 2 MiB
package file, 8 MiB expanded archive, 64 matrix DOFs, 10 000 stored values. The defaults in `ResourceLimits` are larger;
they have not been exercised at scale.

## Verification

One process at a time. OpenBLAS reported **1 thread** when queried directly in the numerics run (Windows, NumPy 2.5.1,
SciPy 1.18.0, Python 3.14.6).

**Final-code targeted run:** `test_plate_ritz_forward` 55 tests OK; `test_plate_forward_adapter` 44 tests OK; 99 in total,
no failures, no skips. Wall time 2 s.

**Budget:** about 9 s of 300 s across all runs: first run 3 s (4 failures), second 2 s, numerics 1 s, final 2 s, plus about
1 s for an import check. The first failures were a tolerance tighter than the basis could reach, the eigensolve accuracy
problem above, and a missing guard mode in the Stage-A sensitivity call. All three were corrected.

| Check | Result |
|---|---|
| Curvature, coupling, mixed-curvature and mass integrals, against polynomials integrated by hand | Pass |
| Free-free beam family (D12 = 0, both axes): closed form from `cos(z)cosh(z) = 1`, computed without plate code | Pass: first mode within 1e-9, three modes within 1e-5, upper bounds hold, shape MAC above 1-1e-10 |
| Three rigid forms, first elastic mode kept, residuals | Pass |
| `sqrt(c)` stiffness scaling, size and mass scaling, axis swap | Pass |
| Central differences at two steps, u positive, zero and negative | Pass: absolute difference at most 1e-5 |
| Chain rule and sum(J) = 1 (Ritz only) | Pass |
| Square plate: repeated pair refused, cluster derivative against central difference | Pass |
| Stage-A frequencies and stored mass slope, against the fixture's closed form | Pass |
| Stage-A refusals: missing, corrupt, wrong model or specimen, oversized before load | Pass |
| Attempted process launch or Abaqus service call fails the test | Pass: guard is itself tested |

**Observed order changes**, rectangular case, modes 1 to 6:

| Degrees | Max relative frequency change | Min MAC | Max S change |
|---|---|---|---|
| 6 to 8 | 2.99e-2 | 0.99598 | 2.67e-3 |
| 8 to 10 | 2.52e-4 | 0.99998 | 2.34e-5 |
| 10 to 12 | 2.42e-6 | 0.99999997 | 5.61e-6 |
| 12 to 14 | 7.00e-7 | 0.9999999998 | 1.85e-6 |

The reduction slows at the last step, so no fixed rate should be assumed. The cause was not investigated.

**Same-solver and fixture tests establish software behaviour, not physical validity.** The beam family is independent of
the assembly but covers only D12 = 0.

## NOT_RUN

- **Published free-free benchmark:** NOT_RUN. The one article retrieved covers simply supported plates and holds no
  free-free table. Leissa and Gorman were not read.
- For the reviewer only, not a test and not evidence: a square isotropic plate at nu = 0.3 gives
  `omega*a^2*sqrt(mu/D)` = 13.4682, 19.5961, 24.2702, 34.8009, 34.8009, 61.0932 at degree 14. These agree with values I
  recall as 13.468, 19.596, 24.270, 34.801, 34.801, 61.09, but that recollection has **no verified source**.
- Independent numerical reference with D12 != 0, any real matrix package, real data: NOT_RUN.
- Full suite, GUI, Abaqus, optimizer: not run, as instructed.
- Python 3.11 (the CI version): not run locally.

## Artifacts

All numbers come from synthetic inputs. Local logs, outside the repository:
`D:\git\abaqus-modal-comparator-work\research\MAT_1\final_targeted.log` and `final_code.sha256`.
