# ABM Materials - offline implementation plan, v1.0

Date: 2026-11-04. Status: proposed implementation contract, not a material-property release or permission for physical-data optimization.
Repository: oblakaF/abaqus-modal-comparator.
Verified working baseline: fix/gui-ux-r1-final, 0a7b8f7da62b189c4c90f3c3ffbb4436da276d1c.
Verified origin/main: 0bea1de68dc346d20958e6f53a9e1d634a870f5d.
Canonical Windows folder: D:\git\abaqus-modal-comparator. Launcher: RUN_NEW_GUI.cmd.

## 1. Product decision and scope

Build one Materials workspace INSIDE ABM, not another application or repository. The first delivery supports one flat, rectangular, thin, homogeneous-equivalent orthotropic plate with independently known material axes and justified free-free conditions. The existing comparison workflow continues to support compatible plates, beams and sandwich structures; this does not extend the new inverse plate model to sandwiches.

Implement two interchangeable forward backends under one scientific inverse workflow:

- KIRCHHOFF_RITZ_4D: a proposed new standalone mathematical plate solver, with independent D11, D22, D12 and D66. Assemble matrices in Python; solve frequencies AND shapes using NumPy/SciPy. No Abaqus installation, ODB or historical Abaqus matrices required.
- STAGE_A_MATRIX_3D: an adapter to the existing matrix_model_service.py. It evaluates a previously prepared, identified and compatible StageAAffineBasis offline. Preserve D22 = D11, the stored approximation domain, the real DOF map and the stored mass behavior. This is NOT a four-independent-parameter backend. Missing compatible matrices means this backend is unavailable for that specimen, not that the first backend must stop.

Both use the same Materials input/output contracts, observation policy, resource control and new invocation of the shared inverse workflow. Two forward models are not two independent physical experiments; agreement is a numerical/model check, not validation of the measured material.

The existing generic_plate_offline_study.py is a THIRD pre-existing facility: a log-linear sensitivity-table predictor for E_in_plane and G12, restricted to E1 = E2. Preserve it and reuse suitable contracts/LM primitives. Do not silently present its fixed-sensitivity predictions as fresh eigen-solves, or use it as an automatic fallback for missing Stage-A matrices. It is not an additional new delivery stream.

Strip tests in the source document are an optional external validation proposal. They are OUTSIDE this software roadmap. No cutting specimens, new laboratory campaign or waiting for strips is required to develop the module. Omitting strips does not waive independent validation or create a holdout from previously fitted data.

### Precise meaning of no Abaqus

No new Abaqus jobs, no matrix generation, no abaqus-python extraction and no subprocess fallback to Abaqus in either offline backend. A raw ODB may still require the existing separately authorized importer to obtain data; offline identification must accept the already imported package or run the standalone backend without ODB. An ODB containing a few modes is not a parameter-dependent stiffness/mass basis. CAE is not an ordinary text file and will not be parsed in this stage.

## 2. What exists and what changes

Verified at the baseline:

| Existing owner | Reuse or boundary |
|---|---|
| matrix_model_service.py / stage_a_parameterization.py | Three-parameter Stage A, D22=D11; affine K approximation and an explicitly represented M(D11) slope when supplied. Preserve old behavior. |
| inverse_solver.py / stage_a_identification_service.py | Existing Stage-A orchestration. Do not wire historical comparison-backed re-pairing into the new frozen-observation workflow. Reuse mathematical components only after checking their contracts. |
| identification_step.py | Existing bounded LM primitives and callback loop. Current ParameterBounds accepts only positive physical parameters and uses log coordinates. A linear signed u cannot be passed as a positive parameter. |
| identification_pairing.py / branch_tracker.py / identification_clusters.py | Reuse admissibility, frozen identities, branch and cluster checks. Add only the adapters needed for a mathematical model geometry. |
| practical_identifiability.py / uncertainty_service.py / model_form_robustness.py | Reuse governed rank, nuisance, uncertainty and family checks where their parameter contracts apply. |
| generic_plate_offline_study.py | Existing research-only sensitivity predictor and run declaration; no numerical material release. |
| materials_workspace.py / materials_workspace_model.py | Existing GUI entry points; extend rather than create a new window/application. |
| analysis_project.py / project_model.py | Existing offline project opening. Extend through an explicit v2 schema, retaining v1 reading. |

Proposed small additions, names finalized by the agent after locating ownership: domain/plate_material_problem.py; services/plate_ritz_forward.py; services/plate_forward_adapter.py; services/plate_material_workflow.py. Prefer existing parsers/readers and process controls. No new Auto-ID install_* layer, copied comparator or independent optimizer implementation.

## 3. Input and result contracts

A PlateMaterialProblem binds specimen_id, test_run_id, modal_set_id, geometry, units, independently measured a/b/m/h, their uncertainty/source status, material axes, actual measurement directions, registration evidence, model/backend identity, parameter policy, observations, numerical configuration and execution authorization.

Ritz minimum physical inputs: a, b, measured mass or justified surface mass, h for conversion to effective engineering constants, a fitted modal dataset with geometry/DOFs and provenance, independently established coordinate registration, declared uncertainty and FIT/HOLDOUT plan. Without h it may evaluate/report D at a declared surface mass, but must not report E/G. Missing uncertainty remains missing; do not insert zero or a guessed percentage.

Use Analyze's loaded data without copying or rereading multi-GB files. Offer independent selection as well. ODB is optional for Ritz and may provide a read-only comparison baseline. INP is an optional source of FE INPUT values, never proof of measured thickness, density or material constants. If an INP reader is needed, support only an explicitly documented subset, resolve INCLUDE dependencies read-only with path/size limits and user-selected scope, and refuse unsupported definitions instead of guessing. Require stated units and material/section/instance identity. No CAE extraction or new ODB extraction is part of this roadmap.

The result stores three independent dimensions: execution status (completed/cancelled/budget/refused), evidence kind (synthetic/research/physical), and scientific verdict. Convergence never changes a research candidate into a released property. Preserve RESEARCH_ONLY, DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE and existing production restrictions. Research results must be useful: D, conditional engineering conversions, residuals, sensitivities, pairs, uncertainties when defined, convergence history and exact reasons for missing scientific acceptance.

## 4. New mathematical forward solver (proposed design)

Scope: Kirchhoff-Love plate bending, constant orthotropic D, negligible B, D16 and D26, independently known material axes, small linear motion. Do not accept thickness/slenderness alone as proof that shear, rotary inertia, supports, prestress or curvature are negligible. Unsupported models fail applicability checks without disabling ordinary ABM viewing.

Use normalized coordinates xi=2x/a, eta=2y/b and a hierarchical tensor-product Legendre basis B_pq(x,y)=P_p(xi)P_q(eta), with w=sum(q_pq B_pq). This is a proposed implementation of the document's plate model, not code already present in the repository. Free edges are natural conditions of the variational problem; do not accidentally impose simply-supported sine functions or clamps.

With mu=m/(a*b), assemble geometry-dependent matrices once:

    K11[r,s] = integral B_r,xx * B_s,xx dA
    K22[r,s] = integral B_r,yy * B_s,yy dA
    K12[r,s] = integral (B_r,xx*B_s,yy + B_r,yy*B_s,xx) dA
    K66[r,s] = 4 * integral B_r,xy * B_s,xy dA
    K(D) = D11*K11 + D22*K22 + D12*K12 + D66*K66
    M[r,s] = integral mu * B_r * B_s dA
    K q_i = lambda_i M q_i; f_i = sqrt(lambda_i)/(2*pi)

Use analytic polynomial integrals or a declared quadrature exact for the relevant polynomial degree; test both scaling and mixed-curvature factors. Validate symmetry, finite values and positive-definite mass before using scipy.linalg.eigh. Use a consistent unit system (proposed internal SI) and explicit conversions in adapters.

The transverse model has the analytic rigid subspace span{1,x,y}. Remove it by a mass-orthogonal projection and verify the shapes; do not discard six modes or use an arbitrary frequency cutoff. This is a new scalar-model adapter, not a change to the established FE rigid-body classifier. Keep the first elastic mode available. Evaluate w and needed spatial derivatives at the registered experimental points. For off-normal observation of a plate surface, implement the justified Kirchhoff surface kinematics (not just U3) or declare that measurement geometry unsupported.

Increase basis order on a fixed, predeclared small convergence schedule. Check frequencies, mode/subspace identity and sensitivities across orders. Select an order adequate over the intended parameter domain before fitting; changing order silently during a fit would change the objective. Cache integration matrices and observation-basis evaluations by exact geometry, order, quadrature, units and code identity. A convergence tolerance is a documented numerical policy to approve, not the historical 0.9999 assertion or a new scientific threshold.

For a simple tracked eigenvalue:

    d(ln f)/dt = q^H (K_t - lambda*M_t) q / (2*lambda*q^H*M*q)

For Ritz, M does not depend on D. Check analytic sensitivities against central differences with two step sizes. At repeated/confirmed clustered modes, use the approved cluster residual and basis-invariant subspace handling, not derivatives of arbitrary individual eigenvectors.

## 5. Existing matrix backend

Load only an explicit compatible StageAAffineBasis package with manifest, source/model identity, matrices, DOF/node maps, parameter definitions, bounds and validation-domain evidence. Use existing reconstruct_stiffness, reconstruct_mass and generalized solver; no generation commands.

Keep its parameter constraint D22=D11 explicit in the GUI and report. Never split the D11 matrix into two invented independent contributions. Preserve a verified mass slope if present; its existence is not a claim that physical mass generally depends on elastic stiffness. Check package compatibility, finite/symmetric matrices, active DOFs, rigid classification and approximation domain.

Cross-backend comparison is allowed only on their common parameter domain with matched geometry, mass, BCs, units, observation directions and compatible physics. Different numbers outside that scope are not evidence that one implementation is broken. No automatic averaging or selection of the backend producing the highest MAC.

A small synthetic Stage-A fixture verifies the adapter, not physical applicability to the owner's plate. If the actual matching archived basis is unavailable, report that fact; do not launch Abaqus or hold up the standalone solver.

## 6. One inverse workflow

1. Validate sources, units and the selected model scope. Select task intent and active parameters before the run. Distinguish viewing, synthetic testing, authorized research and production release.
2. Establish independent plate-to-experiment registration and Hobs. Preserve complex modal values, phase conventions and measured-DOF masks. No coordinate rotation from frequencies, MAC, nodal lines or GUI Rotate/Mirror. Symmetry is a post-registration model-consistency diagnostic only.
3. Compute the baseline and perform the existing strict admissible assignment. Freeze observation IDs, FIT/HOLDOUT families, clusters and registration. A manual Review swap remains a hypothesis and does not become a governed pair automatically.
4. Calculate sensitivities and full practical identifiability. Use the full nuisance/measurement system, not a single column norm. Fix a poorly observed u only with independent value and uncertainty; otherwise do not manufacture a four-constant result.
5. Optionally initialize from local direct stiffness estimates using FIT only and tracked model branches. These estimates are not a third identification algorithm or a material output.
6. Run the shared bounded LM scheme on the same frequency residuals and allowed independent priors. Track every perturbed/trial/final model state to frozen branch IDs. Accepted updates are atomic; rejected updates leave current parameters, modes and mapping unchanged. Branch loss follows the existing refusal contract; no hidden re-pairing or retry policy.
7. Recompute final derivatives, then evaluate held-out families, complete leave-one-FIT-family-out robustness, residual patterns, uncertainty, active bounds and the selected result-class rules.
8. Save the full reproducible result and numerical/scientific status. Report what was learned even when release is refused. Never convert refusal into an approved calibration by renaming it.

Coordinates for the new model:

    theta=(ln(D11/D11ref), ln(D22/D22ref), ln(D66/D66ref), u)
    D12=u*D22
    D11>0; D22>0; D66>0; D12^2<D11*D22
    J11=2*S1; J12=2*u*S4; J22=2*S2-2*u*S4; J66=2*S3

Adapt the existing LM coordinate interface deliberately: preserve the default positive-log API and its historical results, add an opt-in mixed-coordinate contract using the same step kernel/loop ownership. Do not pass signed/zero u through log(), clamp it to an invented epsilon, or introduce a second unrelated optimizer. Generalize the loop only as much as required; prior-row construction, whitening and final covariance use the same coordinates/scales.

    r_i = ln(f_model,i/f_exp,i)
    Phi = 0.5 * r^T Sigma^-1 r + permitted independent-prior terms

MAC remains out of Phi and the weights. Numerical discretization error and tau_mf are not inserted into Sigma to weaken residuals. Missing Sigma components retain their status. Preserve strict baseline MAC 0.80, frequency admissibility 15%, tracking MAC 0.90 and the governed cluster/family policies; consume existing policy objects rather than new hard-coded GUI values.

Exact effective conversion (not ply properties):

    nu12=D12/D22; nu21=D12/D11
    E1_flex=12/h^3*(D11-D12^2/D22)
    E2_flex=12/h^3*(D22-D12^2/D11)
    G12_flex=12/h^3*D66

Carry the full covariance through these formulas. Include mass exactly once and distinguish uncertainty of mean thickness from spatial thickness variation. Birge adjustment is allowed only when the residual-pattern checks support it; LOFO range is not a standard deviation. Four-parameter/signed-u acceptance policy, including an absolute precision criterion near u=0, requires explicit approval before physical release; do not reinterpret the existing log-positive precision gates.

## 7. GUI and persistence

Materials: Reuse Analyze inputs / Choose experiment / Choose existing FE package (optional) / Import INP input properties (optional) / Specimen passport / Backend selector. Show each backend's availability and reason, not two permanently empty tabs. Display input FE values separately from measured inputs and computed results.

Actions: Validate inputs, Preview numerical model, Run authorized study, Cancel, Save result, Copy plot, Export report. Start is enabled only for the declared execution kind and available requirements. Synthetic demo must run without the user's files and must be prominently labelled SYNTHETIC; it is never a substitute for actual identification.

Result view: baseline/current D; effective conversions when supported; frequency and signed-residual table; convergence curve; sensitivities and identifiability; registered shape/MAC evidence; FIT/HOLDOUT roles; uncertainty and explicit scientific verdict. Manual display transforms never change any computational input.

Extend .mcproj with an explicit v2 Materials member: problem/configuration, backend and model identities, provenance, registration reference, selected observations, initial/final parameters, iteration history, numerical evidence, residuals, uncertainties/status and original rendered plots. Include a compact basis/shape representation where bounded; do not embed raw multi-GB ODB/FE stores. Read v1 unchanged; Save As when migrating; no silent overwrite. Offline opening reads only the selected project, never referenced local/network paths. New computation requires explicit source/model revalidation. Use bounded safe serialization, no pickle and atomic saves. Restore results without recomputation; unavailable interactive functions must be explained rather than trigger hidden source reads.

## 8. Four delivery stages (one agent, sequential)

| Stage | Delivery | Completion evidence |
|---|---|---|
| MAT-1: forward foundation | Typed problem/backend contracts; independent 4-D Ritz solver; existing 3-D Stage-A adapter; fixed-geometry cache and observation evaluation; explicit capability flags. | Small deterministic algebra, nullspace, eigen-residual, scaling, derivative and order-convergence tests; no external Abaqus call; both backends evaluated on clearly labelled small fixtures. Actual Stage-A asset availability reported separately. |
| MAT-2: inverse research workflow | Shared mixed-coordinate LM integration, frozen observations/tracking, uncertainty/identifiability, safe candidate reports and bounded execution. | Synthetic parameter recovery for identifiable cases; explicit rejection of constructed rank loss, invalid provenance, incompatible modes and unsupported release; finite-stop and cancellation tests; final Jacobian identity. |
| MAT-3: usable Materials page and save/open | Reuse existing imports/passport; narrow INP input reader if necessary; backend choice; progress/results/plots; .mcproj v2 compatibility and offline replay. | Bounded end-to-end synthetic run on each backend; save/close/open identical results; cancel leaves prior saved result intact; old projects still open without external access. |
| MAT-4: integrated preview handoff | One reviewed small verification matrix and final application integration, not EXE packaging. | Quantified numerical comparison against independent published/archived references where available, GUI acceptance by the owner, artifact versions and clear real-data readiness. No evidence invented for a missing archive or experiment. |

Each stage: verify actual branch/base and clean tracked tree; preserve untracked files; implement only the named stage; complete bounded focused tests; commit/push the authorized feature branch; report exact SHA and limitations; STOP. Next stage begins only after owner review. No automatic PR/merge. Proposed branch for this whole sequential delivery: feature/materials-offline-v1. Base the next stage on its accepted predecessor, not on an unrelated newer branch. Do not modify normative SPEC/DECISIONS without a separate owner decision.

## 9. Verification and resource policy

Two acceptance tracks: (A) software/numerics operational on synthetic/archived references; (B) scientific release for a particular physical specimen. Track A must not wait for a new laboratory campaign, and must not be called track B.

Use a small positive synthetic case with a declared nonsingular sensitivity system and a starting point inside pairing admissibility. Use explicitly constructed unidentifiability rather than missing modes named saddle/ring. Include u=0, u<0, D11 != D22, a truly degenerate/subspace case and FE-number permutation. Do not assume D11=D22 alone makes every chosen pair exactly degenerate. Test absent/corrupted basis, wrong model identity, double coordinate correction, FRF-only input, altered source hash and refused export.

An independent forward benchmark must not be the same assembly with renamed variables. Compare a documented published case or already existing content-addressed trusted calculation; record BCs, units, parameter point and numerical tolerance before testing. A simple simply-supported analytic fixture may test the assembly only; it does NOT validate the free-free boundary implementation by itself. Same-backend twin recovery tests the inverse plumbing, not independent physics.

Do not require 95% of 50 noisy runs to fall in +/-2 standard deviations as a deterministic gate. Statistical coverage work, if needed, uses a separately budgeted predeclared binomial interval/test and recorded seeds; never hundreds of unapproved solves on the owner's workstation.

Proposed development limits: one process at a time, one BLAS thread, no parallel suites; at most 300 s total local focused testing per stage, no automatic budget extension/repetition. If the estimate exceeds that budget, reduce the test selection or report NOT_RUN. No full suite or stress testing in this roadmap without separate approval. Larger numerical qualification belongs to explicitly authorized controlled runs, not hidden background activity.

For executable research runs, require configured caps on elapsed time, evaluations, basis/DOF count and process memory before Start. Enforce termination on the owned worker only; cancel stops at a safe boundary with a hard timeout fallback. Scope Windows process-tree handling to this application. Memory checks are not a guarantee against system-wide resource issues. No Desktop SendKeys or coordinate-based external UI automation; use Qt-scoped synthetic/offscreen tests and the owner's manual final check. No clipboard modification during testing without explicit consent.

No Abaqus execution, new matrix export, real-data identification, material-card release, EXE build, new worktree, original-file changes, force push, reset --hard or git clean is authorized by this plan.

## 10. Disposition of all review corrections

- Carry forward the corrected four-D chain rule and exact D-to-effective-constant conversion.
- Apply sum(J)=1 only to homogeneous K with constant M; remove an assumed value 0.9999.
- Retain independent geometry/measurement registration; torsional nodal symmetry is a conditional diagnostic, never a coordinate-fitting rule.
- Preserve complex/LOS quantities and one-time angle correction; mode 1 is not auto-excluded.
- Use fixed pairs, branch identities, family holdouts and governed clusters; no MAC-weighted objective.
- Remove default nu prior and unsupported E3/shear values. No four-independent-D output from the existing three-parameter Stage A.
- Separate numerical error, measurement covariance, model residuals and tau_mf. No forced mesh order p=2, no two-grid difference declared random sigma.
- Correct synthetic start/case/coverage criteria and retain negative tests.
- No holdout-to-calibration loophole. Previously inspected/fitted modes do not become independent by renaming.
- Historical 56700/41600/0.17/4770 values remain diagnostic examples, never regression targets.
- Strips and their 45-degree inversion are outside this delivery. No unsupported 5% air correction enters the software.
- Include transitive dependencies, backend version, units, model, observations and policies in the appropriate identities; safe replay is not proof of physical truth.
- Positive completion criteria are in MAT-1 through MAT-4; production blockers do not prohibit independent synthetic software development.

## 11. First task to the single VS Code agent (send only this stage)

TASK: MAT-1 - Offline forward foundation for Materials

Read this plan and root AGENTS.md/CLAUDE.md. Verify the baseline 0a7b8f7da62b189c4c90f3c3ffbb4436da276d1c, origin/main and the actual clean tracked tree in D:\git\abaqus-modal-comparator; preserve every untracked file. Use feature/materials-offline-v1, no new worktree. If the base has moved, report the difference before modifying code; do not reset or overwrite owner changes.

Implement MAT-1 only: typed backend/problem/results contracts, the standalone rectangular free-free Kirchhoff-Ritz four-D forward solver, and a read-only adapter to existing Stage-A matrices. Reuse existing imports/domain owners; do not add a second optimizer or call Abaqus. Preserve the three-parameter Stage-A contract and all existing scientific restrictions. Add explicit capabilities, exact provenance/cache identities, observation evaluation, numerical checks, analytical rigid-subspace handling and bounded resource preflight.

Suggested scope: new src/domain/plate_material_problem.py, src/services/plate_ritz_forward.py and src/services/plate_forward_adapter.py; narrowly required exports/adapters; focused tests/test_plate_ritz_forward.py and tests/test_plate_forward_adapter.py; docs/gui/MATERIALS_OFFLINE_PLAN.md and a short MAT-1 report. Other edits require a concrete technical reason in the report. No broad refactor, main.py monkeypatch layer, new GUI pages or normative file changes.

Allowed numerical work for MAT-1: small deterministic synthetic unit tests only, one process/one BLAS thread, aggregate local budget 300 s; declare and enforce small DOF and memory caps before the tests. Do not run an inverse optimizer, physical-data study, multi-GB model or full suite. Verify that an attempted Abaqus call causes the test to fail. Test units, SPD/finite checks, three analytic transverse rigid shapes, first elastic mode, eigensystem residuals, sqrt(c) uniform-D scaling, exact matrix assembly and corrected sensitivities at nonzero/zero/negative u. Add a bounded convergence check, and test Stage-A adapter capability and missing/wrong-package refusal. Do not claim physical validation or final numerical-domain qualification from these tests.

Commit and push the feature branch only. Report SHA, files, complete test summary and budget, mathematical scope, actual/synthetic matrix provenance and remaining limitations. Do not self-accept. No PR/merge, GUI desktop automation or next stage. STOP.

## Sources and evidence boundary

User source: "Algorithm for identifying elastic constants of a CFRP plate from a modal test", v2.2 (uploaded DOCX), with the subsequent review corrections. Its strip validation and Abaqus forward implementation are not silently treated as a finished pure-code solver. The Ritz design above is the present implementation proposal.

Repository evidence, read 2026-11-04 at 0a7b8f7da62b189c4c90f3c3ffbb4436da276d1c:
- docs/auto_id/SPEC_V1_2.md, with unchanged SPEC_V1_1.md clauses.
- src/services/matrix_model_service.py: StageAMatrixParameters / StageAAffineBasis.
- src/services/identification_step.py: bounded LM and positive-log ParameterBounds.
- src/services/inverse_solver.py and stage_a_identification_service.py: legacy Stage-A integration.
- src/services/generic_plate_offline_study.py: research-only log-linear predictor.
- src/services/forward_solver.py: separately gated Abaqus execution path, excluded from offline work.

Primary technical references:
- Dickinson, S. M.; Di Blasio, A. (1986). On the use of orthogonal polynomials in the Rayleigh-Ritz method for the study of the flexural vibration and buckling of isotropic and orthotropic rectangular plates. Journal of Sound and Vibration 108(1), 51-62. DOI: 10.1016/S0022-460X(86)80310-8. Bibliographic record/abstract checked; this does not verify the proposed implementation.
- SciPy official scipy.linalg.eigh documentation: https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.eigh.html
- Repository pinned source: https://github.com/oblakaF/abaqus-modal-comparator/tree/0a7b8f7da62b189c4c90f3c3ffbb4436da276d1c

No FE jobs, matrix solves, optimization, repository edits or desktop actions were performed while preparing this plan. Actual Windows worktree state and presence of the owner's compatible Stage-A matrix package remain to be checked by the agent.
