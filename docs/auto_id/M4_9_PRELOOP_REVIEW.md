# M4.9 final pre-loop decision review (analysis only)

**Status:** PROPOSAL for SUPERVISOR / HUMAN decision (2026-10-05).
- Nothing was run or changed: no code change, no Abaqus or Abaqus Python, no status change, no
  DECISIONS entry. Pending EVIDENCE entries stay pending.
- **Starting state:** SP13 twin READY_FOR_IDENTIFICATION (M4_DECISION_RECORD §10.4):
  - 23 frozen rows; holdouts R1 (FE 7) and R23 (FE 29);
  - 21 fit terms (R2–R22) for 2 parameters;
  - no cluster terms.
- **Data used:** only already-validated material: the p0, E±5 %, G12±5 % and truth shape packs,
  and the repository records.

---

## 1. Parameter bounds

### 1.1 Existing bounds and ranges

| Source | What it says | Kind |
|---|---|---|
| SPEC §8 | `x = ln p, with physical bounds`; `x_new = x + Δx  # projected onto bounds` | Scientific **requirement** that bounds exist; **no values** |
| SPEC §13 | The χ² approximation needs "the optimum is interior (no active bounds)" | Scientific validity condition on results; no values |
| DECISIONS.md (D-001…D-032) | No bound for E_in_plane or G12 (only priors for k_core / t_face) | — |
| M4_DECISION_RECORD §2, §4 | LM settings, start p0 = 52000 / 4500, twin truth 45000 / 4000; **no bounds** | — |
| `forward_model_manifest.py` (M3, `carbon-property-set/v1`) | Candidate values must be finite and positive | Numerical validity only |
| `identification_step.ParameterBounds` (M4.8) | `0 < lower < upper`, required argument, no default | Numerical contract; no values |
| SP13 passport / `SP13.forward.json` | Source engineering constants E1 = E2 = 52000, G12 = 4500 (nominal); no ranges | Nominal model values, not bounds |
| CARBON-5A (`carbon5a/prepare.json`) | Candidates E 49400 / 54600, G12 4275 / 4725 | ±5 % finite-difference points, not bounds |
| CARBON-5B `objective_contract_draft.json` | x = (ln E_in_plane, ln G12), baseline 52000 / 4500 | Parameterisation only; no bounds |
| Legacy `parameter_model` / `material_identification_session` / Stage-A | Bound **structures**; Stage-A bounds on D11/D66/coupling | Different parameterisation; no E/G12 values |
| `tests/m4_6_support.py`, `tests/m4_9_twin_support.py`, the truth-gate driver | E 20000–120000, G12 1000–12000 | **Previous test range** (placeholder); not authoritative |

**Conclusion:** no authoritative scientific bounds exist for E_in_plane or G12. The only numbers
are nominal values, finite-difference points and a test placeholder.

### 1.2 Proposed M4.9 bounds: development only

| Parameter | Lower | Upper | ln-margin from p0 | ln-margin from the truth |
|---|---|---|---|---|
| E_in_plane | **26000 MPa** | **104000 MPa** | ±0.693 | −0.548 / +0.838 |
| G12 | **2250 MPa** | **9000 MPa** | ±0.693 | −0.575 / +0.811 |

**Justification:**
- **Basis:** a factor-2 box around the start point p0, symmetric in ln p (the variable the LM
  works in).
- **Chosen without using the twin truth.** Bounds tuned to the known truth would bias the twin
  test.
- **Purpose:** a numerical guard only, against pathological steps. It is not a physical prior and
  carries no material claim.
- **Containment:** p0 is the centre. The truth is inside with ln margins ≥ 0.548, about 50 times
  the expected local sd. The planning preview of §2.4 puts the first trial point near
  (45 005, 4 012), well inside.
- **Interior expected:** the bounds should never be active in a converging twin. SPEC §13
  requires an interior optimum, so the report should state explicitly if any bound is active at
  p̂. This is reporting only, not a criterion change.
- **Why not 20000–120000 / 1000–12000:** that test placeholder is asymmetric in ln p (E −0.96 /
  +0.84; G12 −1.50 / +0.98) and has no rationale. It is acceptable only if the SUPERVISOR
  prefers continuity with the preparation tests.
- **Label:** mark the bounds `development-only (M4.9 twin)`. Real-specimen identification needs
  its own decision.
- **Run identity:** bounds are part of the run identity. They must be fixed before the loop;
  changing them later starts a new run.

---

## 2. Extraction range and the FE 29 risk (R23, validation holdout)

### 2.1 Tracked counterpart of FE 29, mode (1,5) `Px:O|Py:O|nx:1|ny:5`, in every validated state

Data: full-surface FE-to-FE MAC against the p0 shape.

| State | Counterpart | MAC | Next-best MAC | f (Hz) | Modes above it in 7–30 | Gap to mode 30 |
|---|---|---|---|---|---|---|
| p0 | 29 | 1.00000 | 0.0037 | 628.85 | 1 | 0.15 % |
| E+5 % | **30** | 0.99572 | 0.0037 | 642.28 | **0** | 0 |
| E−5 % | 29 | 0.99634 | 0.0037 | 614.96 | 1 | 0.30 % |
| G12+5 % | 29 | 0.99924 | 0.0037 | 629.54 | 1 | 0.27 % |
| G12−5 % | **30** | 0.99895 | 0.0037 | 628.12 | **0** | 0 |
| Truth | 29 | 0.98629 | 0.0060 | 588.82 | 1 | 0.35 % |

- **Margins:** the MAC margin to the 0.90 tracking threshold is ≥ 0.086. The next-best competitor
  is ≤ 0.006, so there is no ambiguity in any state.
- **FE 29 never leaves modes 7–30** in the six validated states. In E+ and G12−, however, it is
  the **top** extracted mode, with no in-range mode above it.

### 2.2 Neighbour FE 30, mode (4,4)

- **Behaviour:**
  - it swaps order with FE 29 in E+ and G12− (a crossing with stable shapes, tracked by M4.5);
  - it **leaves the range** in E−, G12+ and at the truth (best in-range MAC 0.014–0.28).
- **At the truth, mode 30 is a different mode** that entered from above: `Px:M|Py:E|nx:5|ny:0`,
  0.35 % above FE 29, with MAC 0.006 against FE 29.
- **Consequence:**
  - FE 30 leaving cannot make FE 29 ambiguous: the incoming modes have MAC ≈ 0.006 with it;
  - FE 30 is not a frozen row (exp 24 was excluded at the freeze), so it is not tracked;
  - a missing out-of-range competitor can only **reduce** ambiguity, never create it.

### 2.3 Behaviour of the current M4.5 tracker

- **Reference state:** the pipeline tracks every frozen row, holdouts included, from the fixed
  p0 state.
- **What triggers a refusal:** only FE 29's own counterpart leaving the range, if two modes cross
  below it while it is at the top. The result would be `BRANCH_LOSS`, an LM `REFUSED` and a
  stopped loop.
- **What does not:** a missing out-of-range competitor is never a refusal reason.
- **Where the risk is:** the risk grows in the E-up / G12-down directions, where FE 29 is
  already the top mode.
- **Expected LM path:**
  - it runs from p0 toward lower E and lower G12;
  - FE 29 sits at 29 at the truth and in E− and G12+;
  - but at the truth it is only 0.35 % below the incoming (5,0)-like mode.

### 2.4 Planning preview: not a result, not evidence

- **Method:** a linear LM step from p0 on the 21 fit rows, using the validated ±5 % packs as
  central differences (μ = 1e-3).
- **Result:** the first trial point is predicted near **E ≈ 45 005, G12 ≈ 4 012**, practically the
  already-solved truth state, where FE 29 is in range (mode 29).
- **Design conditioning:** sensitivity correlation 0.65, condition number 6.4, compared with
  about 250 for the real SP13 R1/R2 rows.
- **Status:** the loop itself must compute every value. This preview only places the expected
  path inside the bracket of validated states.

### 2.5 Options

| | A) Keep 7–30 and accept a refusal if it occurs | B) Expand the extraction range before the loop | C) Do not abort on an out-of-range validation holdout |
|---|---|---|---|
| Contract | Unchanged | A new M3 forward-model revision (`frequency_request` > 30 eigenvalues) and a new extraction expectation | Changes the M4.5 / M4.6 identity contract |
| Cost | 0 | The ODBs hold only 30 eigenmodes, so modes 31+ need **new solves**. A new INP gives new job hashes, which invalidates the archived p0/±5 % packs and the truth pack for the new model. That means 6 new Abaqus solves plus 6 pinned extractions (p0, E±, G12±, truth) and a new validation gate, before the loop. | Code change in tracking / the pipeline |
| Sufficient range | — | Not determinable from current data: nothing above mode 30 is known. A conservative proposal is 40 eigenvalues (extract 7–40), plus a new check that every tracked row keeps ≥ 3 in-range modes above it in every solved state. That check would be a new rule needing a decision. | — |
| Decisions affected | None | M3 contract change (requires its own authorisation); twin mode set §5.2 (modes 7–30) and the A1 readiness result would have to be redone | Violates "rows are never added or dropped" (M4.5; M4_DECISION_RECORD §4 criterion 3; the frozen-set contract) and weakens the validation-holdout role. Not compatible without a SPEC / DECISIONS change. |
| Risk | A possible `REFUSED` (non-pass) after some budget is spent | Large scope and many reruns; the result is not comparable with the current readiness evidence | Silent loss of validation evidence |
| Recommendation | **Recommended** | Only if A refuses on R23 (a separate gate) | Not recommended |

**Recommendation: A.**
- In all six validated states FE 29 stays in range with a MAC margin ≥ 0.086 and no ambiguity.
- The expected path starts essentially at the validated truth state.
- A refusal would be the contract working as designed, not a false pass.
- If the loop refuses on R23 (`BRANCH_LOSS`), B becomes the documented next step under its own
  gate.

---

## 3. Run location and retention

### 3.1 Run root

- **Proposed:** **`D:\abaqus_m4_twin_loop`** (`PipelineConfig.run_root`).
  - New and dedicated: not in the repository, not in `D:\abaqus_scratch_m4`, separate from
    `D:\abaqus_m4_truth`.
  - No spaces.
- **Run directory:** the pipeline places the run in
  `D:\abaqus_m4_twin_loop\CFRP-T300-plain-0.45-oldstock\SP-13\<run_hash>\`.
- **Stable across resume:** the run hash depends only on the identity (bounds included), not on
  paths or the Abaqus command.
- **Disk:** about 0.86 GB per new evaluation (ODB 0.716 GB, `.sim` 0.018 GB, rendered INP
  0.111 GB, pack 0.014 GB, logs).
  - 15 evaluations need **about 13 GB**; D: has 323 GB free.
  - The SP13 profile has no separate scratch store.

### 3.2 Retention

| Artifact | Before review | After M4.9 ACCEPTED | After M4.9 REFUSED / not passed |
|---|---|---|---|
| Run journal (hash-chained), result record | Run directory | **Permanent**: archive to `carbon-project-archive/m4_twin/SP13_identification_loop/` (SHA-pinned `ARCHIVE_MANIFEST.json`) plus a repository copy in `docs/auto_id/twins/` | Same as ACCEPTED (permanent) |
| New shape packs (one per new solve) | Run directory | **Permanent** (§6.5): archive under `m4_twin/SP13_identification_loop/packs/`, SHA-pinned; no duplication of archived packs | Same as ACCEPTED (permanent) |
| Provenance (logs, extraction manifests, comparison / assessment) | Run directory | **Permanent**, as for the journal | Same as ACCEPTED (permanent) |
| New ODBs | **Kept** in the run directory until the M4.9 review | May be deleted under §6.5 unless a SUPERVISOR decision archives them | Kept until the refusal review / diagnosis is complete, then the same rule |
| Rendered INPs | Kept | Deletable (deterministic M3 renderings) | Same |
| Truth ODB (`D:\abaqus_m4_truth`) | Kept (§8.6) | May be deleted under §8.6 | Kept until the refusal review |

---

## 4. Proposed HUMAN gate for the loop

| Item | Proposed content |
|---|---|
| Scope | The real M4.9 identification loop, SP13 twin. **No M5.** |
| Inputs, fixed by hash | Twin definition `c200b293…` (seed 20261005); frozen set `05a5443a…`; A1 objective design (21 fit rows R2–R22, holdouts R1 / R23, σ = 0.003, no clusters); `STRICT_IDENTIFICATION_PAIRING`; solver profile `SP13/abaqus-2024/v1` (`79aebbfe…`); extraction expectation modes 7–30 (pinned `extract_odb.py` `039aa067…`); archived packs p0 / E± / G12± |
| LM | `LMSettings(mu_initial=1e-3, mu_decrease=10, max_step_attempts=3, solve_budget=20)`; finite-difference step 5 %; start 52000 / 4500; bounds per §1.2 (to be decided) |
| Budget | At most **20 identification evaluations in total**, p0 included. The 5 reused archived evaluations (p0 plus 4 finite-difference points) count. |
| New Abaqus work | At most **15 new Abaqus 2024 solves plus 15 pinned extractions** (20 − 5). The truth solve is already complete and outside the 20. |
| Stop rules | No automatic retry (`retry_failed_solves = False`). A branch loss or other refusal ends the loop (LM `REFUSED`). A failed solve stops the run. Budget exhaustion gives `SOLVE_BUDGET` (a non-result). Stop after the result record. |
| Execution | Sequential solves. Memory pre-flight before the run (≥ about 15.75 GB free, the threshold accepted for SP13). Run root per §3.1. |
| Output | Result record, `assess_recovery` (criteria 1–2), bounds-active flag, counts (evaluations, reused, solves, extractions), EVIDENCE entry PENDING SUPERVISOR REVIEW |

**Expected new Abaqus work from the current state:**
- **Hard maximum:** **15 solves plus 15 extractions**.
- **Planning expectation:**
  - the first trial needs 1 solve;
  - if it is accepted and the next step is below 0.2·sd, the loop ends CONVERGED without
    another solve;
  - a realistic range is **1–3** new solves (about 22 minutes each: about 620 s solve plus about
    12 minutes extraction).
  - Up to 15 only if steps are rejected and the Jacobian is recomputed (4 solves per
    recomputation).

---

## 5. Status

- **Unchanged:** current status, DECISIONS.md and the pending EVIDENCE entries.
- **Decisions needed before the loop gate:**
  1. bounds (§1.2);
  2. extraction-range option (§2.5; A recommended);
  3. run root and retention (§3);
  4. the gate itself (§4).
