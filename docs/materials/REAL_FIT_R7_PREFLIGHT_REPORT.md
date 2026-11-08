# REAL-FIT.R7.0: FE sensitivity convergence preflight

Status: **REAL-FIT.R7.0 PREFLIGHT_REVIEW_READY**.
- **Abaqus:** NOT_AUTHORIZED, NOT_RUN. No solve, datacheck, fitting or optimisation took place.
- **Unchanged:** the R4/R5/R6 files, gates, thresholds and registrations.
- **Status flags unchanged:** M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED.

## 1. Baseline

- **Git:** branch `feature/materials-offline-v1`; HEAD `10e0ce5722c5c203baeb49559a79596d74018b1c`, equal to origin.
  `origin/main` is `0bea1de68dc346d20958e6f53a9e1d634a870f5d`. The tracked tree is clean; 25 untracked items are
  preserved.
- **Governing references:**
  - [ABM_Materials_Implementation_EN.md](ABM_Materials_Implementation_EN.md) §9–10 and the roadmap. They require
    governed sensitivities and identifiability, keep numerical error separate from measurement uncertainty, and allow
    no invented uncertainty.
  - The accepted R5, R6.0, R6.1, R6.D1 and R6.V1 reports.
- **Plan v2.2:** the DOCX is not in the repository. Its sensitivity rule is applied as stated in the task: central
  differences, δ = ln 1.05, a repeat at δ/2, and no silent substitution of the earlier 1 % forward-difference proposal
  from R6.0 §10.
- **Work folder:** `D:\git\abaqus-modal-comparator-work\runs\real_fit_r7_preflight\`. The output manifest is
  `hash_manifest.json`, SHA `a110a1d4…`, covering 93 files.

## 2. Inventory of existing calculations

**Reusable unperturbed base states.** All of them are S4R with 20 modes, 6 rigid by shape and 14 elastic, extracted
by the pinned extractor with ODBs unchanged.

| Variant | 50×50 | 100×100 | 200×200 | 400×400 |
|---|---|---|---|---|
| A | R6_A_M050 (R6.1) | R5_A (R5) | R6_A_M200 (R6.1) | R6_A_M400 (R6.V1) |
| B | R6_B_M050 (R6.1) | R5_B (R5) | R6_B_M200 (R6.1) | none (not authorised) |

**How they are used:**
- A central difference does not use the base frequency.
- The base states are the tracking references for every perturbation, and they provide the curvature (second
  difference) diagnostic.
- **None of them is re-run.**

**Existing sensitivity data:**
- **Ritz (Kirchhoff surrogate) derivatives only:** R1 and R2 (J = d ln f/d ln p at the fitted points) and R6.D1
  (`diagnostic_r6_d1.json`, central h = 1e-4 at the A and B minima). They are recomputed here at the δ and δ/2 steps
  (§6).
- **Abaqus derivatives: none exist.** Stage A matrices are NOT_AVAILABLE (R3).
  - The earlier M11 inverse runs in `m11_carbon_plate\inverse_fe_r1` (S0, H1, H2) are single solves at other
    parameter points (E1 = E2). They are not central-difference pairs and are not at A or B, so they are **not
    reusable** as A/B sensitivities.
  - Ritz and Abaqus derivatives are kept strictly apart. Ritz values are expectations and pipeline test data only.

## 3. Sensitivity definition

For an elastic branch k (identified by shape) and p ∈ {E1, E2, G12}:

S_k,p(δ) = [ln f_k(p⁺) − ln f_k(p⁻)] / [ln p⁺ − ln p⁻].

- **Steps:** p± = p0·1.05^(±1) for **δ = ln 1.05**, and p0·1.05^(±1/2) for **δ/2**.
- **Values:** written as exact `repr` doubles; the denominator uses the written values. Every written step equals the
  intended ±δ or ±δ/2 to within 1e-14.
- **Fixed:** every other constant (E3, ν12, ν13, ν23, G13, G23), the density, the thickness and the mesh keep the
  base-deck values.
- **Frequencies:** full-precision ODB EIGFREQ, cross-checked with √EIGVAL/2π. The `.dat` table is never used.
- **Variants:** A and B are both kept as separate parameter points. Nothing chooses between them, and the axis
  ambiguity is not addressed by frequency agreement.

## 4. FE-to-FE tracking for every perturbation

- **Reference:** each perturbed job is compared on its **full mesh** with the base state of the same variant and mesh.
- **Rigid modes:** classified by shape (residual ≤ 0.02).
- **Singles:** `r5_common.track` (STRICT, MAC ≥ 0.90, unique), applied identically to every rank 1–14, including
  rank 1, the first elastic twist mode.
- **Pairs:** the frozen pair {13, 14} plus any pair triggered by the 3 % rule on the (base, perturbed) spectra. Each
  is followed as a subspace, with both principal-angle cos² > 0.95.
- **Plus/minus consistency:** the + and − partners must be the same base branch, with MAC(+, −) ≥ 0.90.
- **Unresolved pair:** if only the subspace is unique, the status is **SUBSPACE_ONLY** and S is given for the mean
  eigenvalue of the pair, not per member.
- **Never** by frequency or by mode number.

**Predicted risk**, from the Ritz expectation applied to the FE base spectra (an expectation, not a result):
- no rank order change is predicted for any ±δ perturbation;
- ranks 3/4 come within 2.4 % for E1⁺ (A) and for E2⁺ (B);
- ranks 13/14 come within 0.14–3 % in most cases (down to 0.14 % for B E1⁻ and 0.4 % for A E2⁻). SUBSPACE_ONLY is
  therefore plausible for ranks 13/14; these are not EXP rows.

## 5. Diagnostics and failure statuses (declared before any calculation)

| Diagnostic | Definition |
|---|---|
| Step stability | STEP_STABLE if \|S(δ) − S(δ/2)\| ≤ max(0.005, 0.02·\|S(δ/2)\|) **[PROPOSED limit]**. Step-extrapolated S = S(δ/2) + (S(δ/2) − S(δ))/3, because the central-difference error is O(δ²) |
| Curvature | second difference from (+, base, −) at δ, reported |
| Resolution | \|S\| < 1e-5 at both steps → RESOLUTION_LIMITED. The float32 EIGFREQ floor is about 2.5e-6 at δ/2 |
| Mesh convergence of S | three meshes 50/100/200: MONOTONE gives observed p and S_ext. MESH_STABLE if \|S200 − S_ext\| ≤ max(0.005, 0.02·\|S_ext\|) **[PROPOSED]**. OSCILLATORY within the limit counts as stable; DIVERGENT means MESH_UNSTABLE. Optional A400 gives a second triplet |
| Sum rule | Ritz (Kirchhoff): S_E1 + S_E2 + S_G12 = 0.5 exactly (verified to 1.6e-10). For FE, the deficit 0.5 − ΣS is the share of E3, G13 and G23, reported as a diagnostic, not a gate |
| Ritz comparison | FE S against Ritz S per rank and parameter, diagnostic only |
| Jacobian | singular values and condition number of the FE Jacobian on FIT rows 1–9, against Ritz, diagnostic only |

**Failure statuses:**

| Status | Meaning |
|---|---|
| JOB_FAILED | STOP the batch; no retry |
| TRACKING_LOSS | no unique shape partner for the + or − state |
| TRACKING_INCONSISTENT | the + and − partners differ, or MAC(+, −) < 0.90 |
| SUBSPACE_ONLY | only the pair subspace is unique |
| RESOLUTION_LIMITED | \|S\| below the resolution floor |
| STEP_UNSTABLE | the step-stability limit is exceeded |
| MESH_UNSTABLE | the mesh limit is exceeded, or the sequence diverges |
| NOT_EVALUABLE | a required state is missing |

The PROPOSED limits are diagnostics awaiting owner approval. They are not scientific gates, and no decision uses them
until they are approved.

## 6. Prepared inputs and offline checks

**Decks:** 84 decks were built with the existing `research_fe_trial_preflight.build_variant` from the seven
hash-verified base decks: 3 parameters × 2 steps × 2 signs × (A on 4 meshes + B on 3 meshes). Together they are
276 MB.
- **Naming:** `R7_<L>_M<n>_<P>_<P|M><1|2>`, with 1 = δ and 2 = δ/2.
- **Location:** `decks\<L>_M<n>\`.
- **Checks:** every deck passed all 49 of its checks (`static_verification_log.json` `03cdca0e…`):
  - the existing `verify_variant`: line count unchanged; only the first `*Elastic` data line changed; line endings
    unchanged; the target written exactly; every non-target constant unchanged; all structure and mesh hashes equal
    to the base;
  - plus: the step equals ±δ or ±δ/2 within 1e-14, and the other two targets equal the base exactly.
- **Inputs unchanged:** the R4/R5/R6 inputs (base decks, base packages and result files) were hashed before and after,
  and are unchanged.

**Exact values at 100×100, δ** (δ/2 values and all meshes are in the log):

| Parameter | p0 (A) | p⁺ / p⁻ (A) | p0 (B) | p⁺ / p⁻ (B) |
|---|---|---|---|---|
| E1 | 59643.140320162354 | 62625.29733617047 / 56802.990781107 | 44170.77433673189 | 46379.31305356849 / 42067.40413022085 |
| E2 | 43592.56647783119 | 45772.194801722755 / 41516.72997888685 | 58724.14887983508 | 61660.35632382683 / 55927.76083793816 |
| G12 | 4824.07010224442 | 5065.273607356641 / 4594.352478328019 | 4817.417308245888 | 5058.288173658183 / 4588.016484043703 |

**Pilot decks (stage 1), SHA-256:**

| Job | p written | SHA-256 |
|---|---|---|
| R7_A_M100_G12_P1 | 5065.273607356641 | `760a234073209137eed6f9a81f655dff79f0fdbca534a0b4d6bde9868dcdac04` |
| R7_A_M100_G12_M1 | 4594.352478328019 | `04f03f9e51d815ccd29febfc9c6b3aece5372dd8a0b84831f0b89e6d5167cce8` |
| R7_A_M100_G12_P2 | 4943.2008829236265 | `f871e9b09594b4f0572209fe5c04f2ce9b39f1ff92d35bbb8447367cb745342f` |
| R7_A_M100_G12_M2 | 4707.810364689167 | `0f5a4586a9a44894fa44e5457dbfdf94a5d6d648dff087cb1b0501039441301e` |

**Ritz expectation at the same steps** (Kirchhoff surrogate; this is not an FE result):
- the largest frequency shift at δ is 2.5 %;
- every step check is STEP_STABLE. The largest \|S(δ) − S(δ/2)\| is 1.2e-4 for A, and 1.5e-3 for B E1 (a near-crossing
  of rank-sorted ranks 13/14, which shape tracking avoids). The largest \|S(δ/2) − S(h → 0)\| is 3.9e-5;
- rank 1: S_G12 = 0.483 (A and B). Ranks 2, 3, 7, 9 and 14 depend almost only on E1 or E2 (S ≈ 0.49–0.50).

**Pipeline dry run** (`r7_dryrun.py`, `dry_run_r7.json`), in 2.8 s with no solver:
- **Synthetic states:** perturbed states were built from the real R5 A100 base package shapes, with Ritz-shifted
  frequencies and re-sorted mode order. The analysis returned exactly the injected S (largest error 1.8e-14).
- **Statuses:** all 84 rank/parameter/step entries TRACKED, and all 42 step checks STEP_STABLE.
- **Degenerate pair:** a forced 45° mixing of the rank-13/14 shapes in one state gave SUBSPACE_ONLY for 13 and 14 and
  TRACKED for 12.
- **Mesh classifier:** the cases monotone p = 2, zero, small oscillation and divergent were classified as declared.

The code under test is `r7_sensitivity.py` and the byte-identical `r5_common.py` (`9f26da4f…`). The proposed protocol
is `proposed_protocol_r7.json`, SHA `a41bb5c79c3b27ded294716acded5d7fc74a5e34df6a36349d25d13043628d3f`, with every job,
deck hash and parameter value.

## 7. Exact FE job budget (proposed; each stage needs separate authorisation)

| Scope | Abaqus jobs | Read-only extractions |
|---|---|---|
| One parameter point, one mesh (3 parameters × 2 steps × 2 signs) | **12** | 12 |
| Variant A on 50/100/200 | **36** | 36 |
| A and B on 50/100/200 | **72** | 72 |
| Optional extension: A400 | **+12** (A on four meshes: 48; everything: 84) | +12 |

There are no base re-runs, no datacheck and no retries.

**Proposed stages:**

| Stage | Content | Jobs |
|---|---|---|
| 1 | pilot: A100 G12 at ±δ and ±δ/2 | 4 |
| 2 | rest of A100: E1 and E2 | 8 |
| 3 | A50 and A200 | 24 |
| 4 | B50, B100 and B200 | 36 |
| 5 | optional A400 | 12 |

**Resource estimates**, scaled from the measured R5/R6 runs; these are estimates, not measurements:

| Mesh | Solver time per job | Disk per job | Note |
|---|---|---|---|
| 50 | about 18 s | about 9 MB | |
| 100 | about 17 s | about 28 MB | |
| 200 | about 20 s | about 104 MB | |
| 400 | about 57 s | about 408 MB | 9.4 GB memory to minimise I/O |

- Extraction adds roughly 20–90 s per job.
- Stage 1 takes about 3 min and 0.12 GB.
- Variant A on three meshes takes about 30–45 min and 1.7 GB; A and B together about 1–1.5 h and 3.4 GB.
- Adding A400 brings the total to about 8.3 GB.
- The runs are sequential, use one CPU, have an 1800 s cap per job, and STOP on the first failure.

## 8. Recommended first batch

**Stage 1, 4 jobs: A100 G12 at ±δ and ±δ/2.** It is the smallest batch that genuinely exercises the whole pipeline:
- perturbed deck, solve, extraction;
- full-mesh shape tracking against the existing R5_A base, including rank 1 (S_G12 ≈ 0.48 expected) and the predicted
  13/14 near-degeneracy (1.3 % for G12⁺);
- central difference at both steps and the step-stability check;
- curvature, using the R5 base;
- comparison with the Ritz S.

It reuses the R5 base, so it needs no base re-run. Stage 2 (8 jobs) completes the first full parameter point. Only
then should stages 3–5 be considered.

## 9. Scientific limitations

- **What S is:** local derivatives of S4R frequencies at two research points (A and B), on one element family, with
  E3, ν and the transverse constants fixed. The deficit from the sum rule only indicates the share of those fixed
  constants.
- **What S is not:** FE sensitivities are not a fit, not an identification and not a measurement uncertainty. They
  do not choose A or B, and they do not resolve the axis ambiguity.
- **Twisting modes:** they were pre-asymptotic below h = 0.75 mm (R6.V1). Their sensitivities may converge more slowly
  with mesh than those of non-twisting modes; the mesh diagnostic is designed to show this, not to hide it.
- **Proposed limits:** the step and mesh limits are proposals, not accepted gates.
- **Mesh gate:** u(ln f_exp) is NOT_AVAILABLE, so the uncertainty-relative mesh gate stays NOT_EVALUABLE.
- **Not demonstrated:** the 10 % target, material identification and FE↔EXP mode identity.

REAL-FIT.R7.0 PREFLIGHT_REVIEW_READY. STOP: awaiting owner review and separate Abaqus authorisation.
