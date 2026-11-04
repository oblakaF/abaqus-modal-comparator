# MAT-1 - Implement both offline forward backends inside ABM

This is an implementation task, not another global audit or a documentation-only stage. Deliver working forward-calculation services and bounded tests. Execute MAT-1 ONLY, then STOP for owner review.

## Repository, documents and safe start

Repository: `oblakaF/abaqus-modal-comparator`
Canonical application folder: `D:\git\abaqus-modal-comparator`
Launcher to preserve: `RUN_NEW_GUI.cmd`
Code baseline: `0a7b8f7da62b189c4c90f3c3ffbb4436da276d1c`
Documentation branch: `docs/materials-offline-v1`
Implementation branch: `feature/materials-offline-v1`

1. Work in the canonical folder. Inspect the current branch, HEAD and tracked/untracked status before changing anything. Fetch origin and record current origin/main. Preserve every untracked file, including START_HERE.txt and user projects; the previous report listed 25 untracked files, not a deletion allowlist.
2. Pin the fetched `origin/docs/materials-offline-v1` commit. Verify that it descends from the code baseline and that its delta from that baseline contains only the three handoff documents under `docs/materials/`. Do not merge an unrelated branch or overwrite owner changes.
3. With a clean tracked tree, create `feature/materials-offline-v1` from that pinned documentation commit. If this implementation branch already exists, inspect it and reuse it only if it is a compatible continuation; never reset, replace, force-checkout or silently discard work.
4. Read these repository files directly; do not ask the owner to download or locate them:
   - `docs/materials/ABM_Materials_Implementation_EN.md`
   - `docs/materials/ABM_Materials_Roadmap_RU.md`
   - `docs/materials/MAT_1_AGENT_PROMPT_EN.md`
5. Read root AGENTS.md and CLAUDE.md, governing SPEC_V1_2.md including unchanged SPEC_V1_1.md clauses, relevant DECISIONS/ROADMAP/STATUS and accepted evidence. Locate the actual code owners before editing. This prompt refines the operational bootstrap and scope of section 11 of the English plan; it does not override scientific norms.

The Russian Markdown is a readable text mirror of the Word roadmap. The English implementation plan is the technical work contract. The original Word document is not needed to execute this task.

## Product requirements carried through all four stages

One application, one Materials workspace, one canonical folder. No second application, repository, agent or worktree.

Two interchangeable FORWARD backends will feed one shared inverse workflow:

- `KIRCHHOFF_RITZ_4D`: a new standalone mathematical model of a single rectangular free-free plate, with independent D11, D22, D12 and D66. Python/NumPy/SciPy compute both frequencies and shapes. No Abaqus installation, ODB or previously exported Abaqus matrices are required.
- `STAGE_A_MATRIX_3D`: a read-only adapter to the existing Stage-A matrix model. It needs an identified compatible matrix package prepared previously. Preserve D22 = D11 and all stored approximation/mass behavior. No new Abaqus invocation is allowed.

The existing log-linear sensitivity predictor is preserved; it is not a third development stream, a fresh eigensolve or an automatic fallback for missing matrices.

The delivery roadmap remains exactly four stages:
MAT-1 forward backends; MAT-2 shared inverse workflow; MAT-3 Materials GUI and project persistence; MAT-4 bounded integration and handoff. Do not execute MAT-2/3/4 now.

Later GUI requirements remain binding but are NOT this stage's scope: reuse Analyze inputs, allow standalone experimental input without ODB for Ritz, explicit units/provenance, useful numerical results and plots, one cancellable bounded worker, and versioned .mcproj persistence with offline opening and v1 compatibility. Manual Review Swap/Rotate/Mirror must never modify scientific registration or frozen observations.

Strip tests, specimen cutting and new laboratory campaigns are outside this software task. Software progress must not wait for them. This does not waive the independent evidence needed for a physical material result.

## MAT-1 deliverables

### A. Shared typed contracts

Implement or adapt small domain contracts for plate geometry/units, positive physical quantities, parameter coordinates, backend capabilities, model identity, observation evaluation, numerical configuration, resource limits and forward results.

A result must carry frequencies, shape representation, DOF/component and coordinate meaning, backend/model identity, numerical diagnostics and synthetic/research provenance. Missing information remains missing; do not substitute default material values or uncertainties. Forward computation is not material identification.

Keep execution status, data provenance and scientific status separate. No automatic ACCEPTED or material-card export.

### B. Standalone free-free Kirchhoff-Ritz solver

Implement the mathematical formulation in section 4 of the English plan:

- Domain: x in [-a/2,a/2], y in [-b/2,b/2]; surface mass mu = m/(a*b).
- Hierarchical tensor-product Legendre basis with xi = 2*x/a and eta = 2*y/b.
- Natural free-edge conditions from the variational formulation. Do not substitute simply-supported sine functions or artificial clamps.
- Assemble geometry matrices once using analytic integration or quadrature exact for the declared polynomial degree:

  K11_rs = integral(B_r,xx * B_s,xx)
  K22_rs = integral(B_r,yy * B_s,yy)
  K12_rs = integral(B_r,xx*B_s,yy + B_r,yy*B_s,xx)
  K66_rs = 4 * integral(B_r,xy * B_s,xy)
  M_rs   = integral(mu * B_r * B_s)
  K      = D11*K11 + D22*K22 + D12*K12 + D66*K66
  K*q    = lambda*M*q; f = sqrt(lambda)/(2*pi)

- Require D11,D22,D66 > 0 and D12^2 < D11*D22. Validate finite values, symmetry, units and SPD mass. Do not hide invalid eigenvalues with abs() or unjustified clipping.
- Separate the scalar transverse rigid subspace span{1,x,y} by a verified mass-orthogonal projection. Do not drop six modes or introduce an arbitrary frequency cutoff. Preserve the first elastic mode and the existing FE rigid-body classifier.
- Evaluate shapes and derivatives at explicitly registered observation coordinates. Support justified measurement projection or report unsupported kinematics; do not guess measured U3 or derive registration from shapes.
- Expose a bounded order-convergence check for frequencies, shapes/subspaces and sensitivities. A fixed order is part of model/run identity. Do not assume convergence order p=2.

Provide derivatives for simple tracked eigenbranches and check them against central differences:

  d ln(f)/dt = q^H*(K_t - lambda*M_t)*q / (2*lambda*q^H*M*q)

Ritz M is independent of D. Prepare mixed coordinates
(theta1,theta2,theta3,u) = (ln(D11/D11ref), ln(D22/D22ref), ln(D66/D66ref), D12/D22).
Do not log u: zero and negative values are admissible within physical constraints.
Check J11=2*S1, J12=2*u*S4, J22=2*S2-2*u*S4, J66=2*S3.
Apply sum(J)=1 only where homogeneous K and constant M justify it. For unresolved degeneracy, use the supported subspace contract or a clear diagnostic refusal; never differentiate an arbitrary eigenvector as a unique branch.

### C. Existing Stage-A adapter

Reuse `matrix_model_service.py` and `stage_a_parameterization.py`; do not rewrite their mathematics.

Preserve the three independent parameters, D22=D11, exact DOF/node identities, declared validity domain, stored affine stiffness approximation and supplied mass derivative. Do not invent a missing mass slope or apply Ritz homogeneity assumptions to this backend.

Identify compatible package inputs using existing code/evidence and bounded reads only. Missing, corrupt, wrong-specimen or wrong-model packages must give a precise refusal for this backend, without disabling Ritz. Never generate matrices or infer a parameter basis from an ODB containing a few modes.

A small synthetic matrix fixture is permitted and must be labelled SYNTHETIC. It tests adapter operation, not applicability to the owner's real plate. A Ritz-generated fixture cannot be called independent validation of Stage A.

### D. Provenance and resource preflight

Include backend version, parameters, units, geometry, mass, basis/order or matrix-package identity, DOF ordering and numerical configuration in cache/run identities. Preserve the applicable source and observation identities; no rounded-parameter cache collisions.

Bound matrix size and memory before allocation. Reject oversized inputs before large loading. Keep scientific services free of Qt and desktop actions.

## Reuse and allowed code scope

Suggested additions:
- `src/domain/plate_material_problem.py`
- `src/services/plate_ritz_forward.py`
- `src/services/plate_forward_adapter.py`
- `tests/test_plate_ritz_forward.py`
- `tests/test_plate_forward_adapter.py`
- `docs/materials/MAT_1_REPORT.md`

Names may follow the existing architecture after inspection. Other edits require a concrete dependency and a narrowly scoped explanation. No broad refactor or new install_* layer.

Do not change the GUI, launcher, project-file schema, comparator algorithms, inverse optimizer or material release logic in MAT-1. Record progress in the dedicated report; do not change global Auto-ID status or normative SPEC/DECISIONS. The future mixed-coordinate LM belongs to MAT-2 and must reuse existing ownership rather than duplicate an optimizer.

## Verification and strict resource limits

Allowed computations: small deterministic SYNTHETIC forward unit tests only. No physical-data identification, inverse optimization or new FE jobs.

- One test/calculation process at a time; one BLAS thread configured before importing NumPy/SciPy. Verify the effective setting where available.
- Aggregate local test budget: 300 seconds INCLUDING repetitions. Reserve time for one completed final-code targeted run. Budget exhaustion is INTERRUPTED/NOT_RUN, never PASS; do not silently restart the budget.
- Declare conservative coefficient/DOF, allocation and input-file caps before testing. These are development resource limits, not scientific tolerances. No multi-GB reads, full suites, parallel tests, stress tests, Monte Carlo campaign or crash reproduction.
- No visible GUI run in this stage. No SendKeys, global mouse/keyboard actions, screen-coordinate automation or clipboard modification. Do not inspect or affect other projects/processes.
- Make an attempted Abaqus launch fail in tests. Both offline backends must have no extraction, matrix-generation or external-solver fallback.

Focused coverage: units and D conversions; matrix symmetry/finite/SPD checks; exact rigid subspace and first elastic mode; eigensystem residuals; sqrt(c) scaling for uniform D scaling in Ritz; mixed-curvature factor; derivatives/chain rule for u positive, zero and negative; bounded order refinement; observation evaluation; Stage-A capability limits, wrong/missing package refusal and preservation of supplied mass behavior.

Use a published or existing content-addressed independent reference only when available within the budget. State NOT_RUN when absent. Same-solver recovery and a simply-supported analytical case do not establish free-free physical validity. Do not invent benchmark numbers or claim numerical-domain qualification from a few unit tests.

## Scientific and operational boundaries

Preserve M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and the production Auto-ID block. No threshold changes, fabricated registration, FRF-peak promotion, material values from one frequency, or automatic material-to-calibration fallback. Keep source modes and archived evidence unchanged.

No Abaqus/abaqus-python, new matrix export, real-data optimization, material cards, EXE build, new worktrees, PR, merge, direct main push, force push, reset --hard, git clean or source-data modification. Do not scan disks for unrelated material. This prompt authorizes implementation and bounded synthetic forward tests, not scientific release.

## Completion and report

Deliver executable forward services for BOTH backends, not only stubs or another plan. Missing real matrix artifacts do not prevent a clearly synthetic adapter test or the standalone implementation.

Commit and push ONLY `feature/materials-offline-v1`. Report:
1. Documentation base, code baseline, actual branch and final SHA.
2. Changed files and code owners reused.
3. What each backend actually computes and its limitations.
4. Complete final targeted-test summary, elapsed budget and NOT_RUN/INTERRUPTED checks.
5. Numerical checks and synthetic versus real artifact provenance.
6. Confirmation of unchanged source files/untracked data, no Abaqus or desktop automation, and no production-status change.
7. CI link/status for the exact final SHA when accessible; otherwise UNKNOWN. Do not wait by running more tests.

Use REVIEW_READY, not self-ACCEPTED. STOP after the report. Do not begin MAT-2 until the owner accepts MAT-1 and explicitly authorizes the next stage.
