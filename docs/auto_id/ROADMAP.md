# Auto-ID — Roadmap (SPEC v1.2 governing)

Governing specification (D-078):
[docs/auto_id/SPEC_V1_2.md](SPEC_V1_2.md) — SPEC v1.1 as amended by v1.2;
normative predecessor [docs/auto_id/SPEC_V1_1.md](SPEC_V1_1.md) (archived, immutable)

Scientific audit:
[docs/auto_id/AUDIT_121ba1d_V1_1.md](AUDIT_121ba1d_V1_1.md)

Original audited snapshot:
`121ba1d06b7c268b3051f1407a3ea26a9027dca3`

Machine-readable state: [STATUS.json](STATUS.json). Decisions: [DECISIONS.md](DECISIONS.md).
History: [CHANGELOG.md](CHANGELOG.md). Evidence: [EVIDENCE.md](EVIDENCE.md).

## Execution rule

**ONE MINI-STEP AT A TIME.**

Exception: a SUPERVISOR-authorised batch of named mini-steps within one stage
runs without stopping between mini-steps (see `CLAUDE.md` / `AGENTS.md`). Each
mini-step still ends `REVIEW_READY` with its own commit; the worker STOPs after the
whole batch.

Every mini-step:

```
IMPLEMENT
→ VERIFY
→ UPDATE ROADMAP / STATUS / CHANGELOG
→ COMMIT
→ PUSH
→ REPORT
→ STOP
→ SUPERVISOR REVIEW  (ACCEPT / REWORK / ESCALATE)
```

Only after ACCEPT may the next mini-step begin.

### Allowed statuses

`TODO` · `IN_PROGRESS` · `REVIEW_READY` · `ACCEPTED` · `BLOCKED` · `REWORK`

`BLOCKED_<REASON>` (for example `BLOCKED_WAITING_FOR_CARBON_5F`) is the `BLOCKED`
status with its reason attached.

A worker may move `TODO → IN_PROGRESS → REVIEW_READY`. Only an explicit SUPERVISOR or
HUMAN acceptance may move `REVIEW_READY → ACCEPTED`. A requested correction moves
`REVIEW_READY → REWORK`.

## Mini-step git protocol (permanent)

**Before each mini-step**

- Inspect [STATUS.json](STATUS.json).
- Require the prior mini-step to be `ACCEPTED`.
- Create or use the correct `auto-id/*` branch.
- Set the current mini-step to `IN_PROGRESS`.

**Implement**

- ONLY the named mini-step.
- No unrelated refactor. No opportunistic cleanup.

**Verify**

- Targeted tests.
- Relevant regressions.
- Full suite only where a stage gate requires it.
- Abaqus only under explicit human authorisation.

**Document**

- This ROADMAP (status of the mini-step).
- [STATUS.json](STATUS.json).
- [CHANGELOG.md](CHANGELOG.md) (append-only entry).
- [DECISIONS.md](DECISIONS.md) only for new accepted design decisions.
- [EVIDENCE.md](EVIDENCE.md) for scientific evidence.

**Commit**: one coherent mini-step commit. Examples:

```
auto-id(M0.1): fix cross-platform evidence path
auto-id(M2.1): add specimen manifest schema
auto-id(M4.5): add fixed-branch FE tracker
docs(auto-id): freeze v1.1 roadmap
```

**Push** the current `auto-id/*` branch. Never push directly to `main`. Never force
push.

**STOP.** Report to the supervisor. Do not continue automatically.

## Stage branch / merge policy

- Current freeze branch: `auto-id/v1.1-roadmap`.
- Recommended stage branches: `auto-id/m0`, `auto-id/m1`, `auto-id/m2`,
  `auto-id/m3`, `auto-id/m4`, `auto-id/m5`, `auto-id/m6`, `auto-id/m7`, `auto-id/m8`.
- Mini-step commits are pushed to the stage branch.
- At stage end: all mini-steps `ACCEPTED`, gate tests pass, stage status
  `REVIEW_READY`, PR to `main` prepared, then STOP.
- **Never merge a stage PR without explicit HUMAN authorisation.**
- After merge: record the `main` merge SHA in STATUS.json and CHANGELOG.md. Only then
  begin the next stage.

---

## PRE-M0 — Freeze and governance

| Id | Mini-step | Status |
|---|---|---|
| P0.1 | Freeze SPEC v1.1, AUDIT v1.1, roadmap and governance documents | `ACCEPTED` (commit `3362076`) |
| P0.2 | Record final accepted CARBON-5F evidence appendix | `ACCEPTED` (commit `ec86a77`) |
| P0.3 | Establish permanent branch / mini-step / GitHub reporting protocol | `ACCEPTED` (commit `3362076`) |

PRE-M0 is **complete**. M0 may begin only after this freeze branch is merged to `main`
under explicit HUMAN authorization.

**P0.2 scope (only after a final CARBON-5F report is SUPERVISOR-ACCEPTED and an
explicit prompt provides it):** update [EVIDENCE.md](EVIDENCE.md); add [s_E, s_G, s_k];
add S_core; add q_G if validly calculated; describe the FE7 holdout; describe FE8/FE9
behaviour; state explicitly what CARBON-5F does **not** establish about the k_core
prior; update STATUS/ROADMAP/CHANGELOG; commit and push.

**PRE-M0 GATE:** P0.1, P0.2 and P0.3 must all be `ACCEPTED` before M0 begins.
Gate status: `ACCEPTED`.

---

## M0 — Trusted development baseline

Purpose: make every later Auto-ID change testable against stable real evidence.

| Id | Mini-step | Acceptance | Status |
|---|---|---|---|
| M0.1 | Fix V7 cross-platform path failure | Linux V7 failure gone; no scientific behaviour change; targeted regression passes | `ACCEPTED` (commit `15d6c53`) |
| M0.2 | Real experimental fixture manifest | SP02/SP13 real fixture identities pinned; SHA-256 recorded; large/private data need not be committed blindly; deterministic local/external fixture retrieval contract documented | `ACCEPTED` (commit `66dfe45`) |
| M0.3 | Real PolyMAX / FrozenRegistration regressions | SP02 `bravo-1` identity reproduced; SP13 `best` identity reproduced; accepted FrozenRegistration identities reproduced; a peak-derived source cannot silently substitute | `ACCEPTED` (commit `b3e080f`) |
| M0.4 | Windows + Linux CI baseline | Factual test summaries; zero unexplained failures; skips documented; platform behaviour explicit | `ACCEPTED` (commits `afa2181`, `ad62328`) |

**M0 GATE:** trusted green baseline before M1.
Stage status: `ACCEPTED` (M0.1–M0.4 `ACCEPTED`; M0 GATE `ACCEPTED`, CI reference `afa2181`).

**M0 merge completed into `main`** (PR #26). Main merge commit:
`4ec80abd3110b41aea586387faf42d4ad90fa9d0`. M1 may begin only after explicit SUPERVISOR
authorization.

---

## M1 — Production experimental modal input

| Id | Mini-step | Content | Status |
|---|---|---|---|
| M1.1 | Identification input-source policy | Curve-fitted modes allowed. Peak-derived modes refused for production Auto-ID. | `ACCEPTED` (commit `2fa48c2`) |
| M1.2 | Production PolyMAX dataset 55/2414 path | Preserve frequency, shape, provenance, measurement DOFs. | `ACCEPTED` (commit `bc2ffce`) |
| M1.3 | Raw-FRF multi-mode fitting path | Dataset 58 may be used for identification only through an accepted multi-mode fit. Peak-only stays QC/screening. | `ACCEPTED` (commit `4b8d73e`) |
| M1.4 | Experimental QC | Suspension threshold; resolution; unresolved resonance (2ζf < 3Δf); coherence at resonance (< 0.9); phase complexity. | `ACCEPTED` (commits `c411bb9`, `ef95cbe`: suspension-aware QC) |

Stage status: `ACCEPTED` (M1.1–M1.4 `ACCEPTED`; Gate A `PASS`; Gate B `FUTURE_INTERNAL_PROVIDER`).
**M1 merged into `main`** (PR #27, merge commit `d00120514bdd75bc4421891486218c3cf87d3438`).
M1.3 design: `DESIGN_ACCEPTED` ([M1_3_DESIGN_REVIEW.md](M1_3_DESIGN_REVIEW.md);
D-019, D-021, D-023, D-024, D-026 to D-029). M1.3 implementation is `ACCEPTED`.

| Id | Sub-step | Status |
|---|---|---|
| M1.3.1 | `ModalFittingProvider` interface boundary (no fitting algorithm) | `ACCEPTED` (commit `f77045d`) |
| M1.3 provider | `ExternalPolyMAXProvider`: external PolyMAX modal preparation provider (D-026, D-027) | `ACCEPTED` (commit `4b8d73e`) |

**Final architecture:** Dataset-58 FRF → FRF preparation / external
PolyMAX-compatible provider (D-027) → validated curve-fitted modal dataset (frozen
external selection, D-026) → M1.1 source policy → M1.2 production loader → Auto-ID.
Internal FRF fitting is a future provider (D-029). The first provider
(`services.external_polymax_provider`) is ACCEPTED. Accepted limitations: coherence
evaluation deferred to M1.4; internal fitting remains a future provider;
registration source path/timestamp reconciliation remains future work.

**M1 GATE (stage closure; SPEC §19 items 4–5)**

**Reference values are fixture-specific (D-028, SPEC §19 item 4).**
- **`SP13/best` (repeat-a, 2026-09-10):** the frozen PolyMAX values are about 205.65 /
  212.66 / 228.61 Hz.
- **Historical:** 206.15 / 212.61 / 228.75 Hz belong to the 2026-09-09 acquisition.
  They stay historical until that acquisition is pinned as a separate fixture.

**M1 Gate A — initial production modal-input layer: `PASS`.**
Evidence: `tests/test_m1_stage_gate.py` plus the per-milestone real-data tests, on
`SP02/bravo-1` and `SP13/best`. Gate A requires all of the following:
- the curve-fitted source policy is enforced (M1.1);
- fixture identity and provenance are pinned (M0.2 manifest, M1.2 loader);
- the `ExternalPolyMAXProvider` is accepted (M1.3);
- the frozen `SP02/bravo-1` and `SP13/best` datasets are reproduced;
- fixture-specific reference frequencies are used;
- damping is recovered from the stored PolyMAX poles;
- peak-derived substitution is refused, including real peak-derived modes from the
  same export;
- the M1.4 hard QC checks pass;
- the suspension threshold is represented honestly: evaluated when a trusted value
  exists, otherwise `NOT_AVAILABLE` pending M2. Both historical fixtures are
  `NOT_AVAILABLE`;
- QC does not mutate the modal dataset.

**M1 Gate B — first internal `ModalFittingProvider`: `FUTURE_INTERNAL_PROVIDER`.**
It is not part of the initial M1 closure (SPEC §19 item 4, D-029). Its future gate
keeps the original scientific requirement:
raw FRF → independent internal fitting → recovery against the acquisition-specific
PolyMAX reference → damping agreement → no false peak-derived modes.
Gate B has **not** been passed. The external provider reproduces the frozen PolyMAX
result and does not re-fit raw FRF.
---

## M2 — Specimen manifest + physical registration

| Id | Mini-step | Status |
|---|---|---|
| M2.1 | `specimen_manifest` schema / domain / hash | `ACCEPTED` |
| M2.2 | Family / design / specimen / test-run identities with distinct keys `design_id`, `physical_specimen_id`, `test_run_id` | `ACCEPTED` |
| M2.3 | FrozenRegistration generated from physical calibration / passport | `ACCEPTED` |
| M2.4 | Registration uncertainty diagnostic (never optimisation) | `ACCEPTED` |
| M2.5 | Acquisition / remount linkage for Σ_setup | `ACCEPTED` |

**M2 GATE:** SP02/SP13 reproduce the accepted FrozenRegistration identities. The
registration perturbation diagnostic never changes the chosen geometry by optimising
MAC.

Stage status: `ACCEPTED` (M2.1–M2.5 `ACCEPTED` by the SUPERVISOR; software / regression gate `PASS`;
current SP02/SP13 production physical readiness `NOT_READY`).
**M2 merged into `main`** (PR #28, merge commit `7af9038c5486560c5d2d0b6d571a354766e29d77`).

**M2 gate evidence:**

| Gate | Result |
|---|---|
| Software / regression gate | **PASS** |
| Current SP02/SP13 production physical readiness | **NOT_READY** |

- **Historical accepted-registration replay (regression compatibility):** SP02 and
  SP13 reproduce their accepted identities through the passport path with full
  content equality (`9bf736d3…`, `a8970e52…`; `tests/test_m2_stage_gate.py`).
  - The build runs with the MAC/frequency functions disabled.
  - `source_identity_basis` stays `legacy_accepted_registration`.
- **Two separate statuses:**
  - **Registration basis** (`PHYSICAL` / `LEGACY_REPLAY` / `INCOMPLETE`) describes the
    nominal registration.
  - **Uncertainty availability** (`AVAILABLE` / `PARTIAL` / `NOT_AVAILABLE`) is
    reported separately. A physical registration without measured uncertainty is
    still `PHYSICAL`.
  - SP02/SP13 are `LEGACY_REPLAY`, which is not SPEC §11 evidence, with uncertainty
    `NOT_AVAILABLE`.
- **Production guard:** `require_production_ready()` refuses `LEGACY_REPLAY`, a missing
  physical reference, a non-traceable orientation, a legacy source identity or a
  missing `physical_specimen_id`. It never refuses for missing uncertainty alone, and
  never upgrades a replay. It refuses SP02/SP13 and names the missing evidence
  ([specimens/README.md](specimens/README.md)).
- **Units:** passport lengths (mm) are converted to the Abaqus model unit (mm/cm/m/µm).
- **Diagnostic:**
  - Perturbations stay within measured uncertainty; the diagnostic never selects or
    returns a perturbation.
  - A non-finite MAC is recorded as an invalid perturbation and is excluded from the
    range.
  - "Not registration-limited" needs complete evidence.
  - The 0.8 MAC crossing is executable; the pairing-change trigger is `DEFERRED_M4`.

---

## M3 — Universal forward builder

| Id | Mini-step | Status |
|---|---|---|
| M3.1 | Manifest-driven material location | `ACCEPTED` |
| M3.2 | Generic candidate rewrite | `ACCEPTED` |
| M3.3 | Generic provenance / job hash | `ACCEPTED` |
| M3.4 | Remove production hard-coding of SP02, SP13, `D:\Snadwich` and specific machine paths from the generic Auto-ID path | `ACCEPTED` |
| M3.5 | Regression against the current accepted shared-carbon builder | `ACCEPTED` |

**M3 GATE:** the generic builder reproduces the accepted SP02/SP13 reference INPs
byte-for-byte, except any explicitly versioned metadata difference proven irrelevant.
No physics change.

Stage status: `ACCEPTED` (M3.1–M3.5 `ACCEPTED` by the SUPERVISOR; byte-for-byte regression `PASS`).
**M3 merged into `main`** (PR #29, merge commit `0fd63d69a78f251bd51721880bae9b425b98951e`).
M3.1–M3.5 run as one SUPERVISOR-authorised stage batch. No Abaqus. The accepted
shared-carbon builder stays unchanged as the regression oracle.

**M3 gate evidence:**

| Gate | Result |
|---|---|
| Byte-for-byte regression against the accepted shared-carbon builder | **PASS** |
| Physics change | none |

- **Archived jobs:** for the 5 accepted CARBON-4C / CARBON-5A candidates × SP02/SP13
  (10 jobs that were solved in Abaqus), the universal builder's INP bytes are
  identical to the live accepted builder (`shared_carbon_forward`, unchanged since
  `121ba1d`) on the same pinned reference INPs (`tests/test_m3_stage_gate.py`).
- **Archived identities reproduced:** generated INP SHA-256, changed-line numbers,
  the accepted provenance and evaluation hashes, and the job names (= archived ODB
  names) ([forward_models/accepted_forward_jobs.json](forward_models/accepted_forward_jobs.json)).
- **Extended check:** a one-off matrix of 12 further candidates × 2 specimens (awkward
  floats, the M4 twin start 45000/4000, extremes) gave 24 / 24 identical files.
- **Synthetic:** 8 INP variants × 7 candidates are identical to the accepted builder.
- **Only E1/E2/G12 change:** the carbon record and, for SP02, the eigenvalue request
  15 → 30 are the only changed lines. Mesh, geometry, core, density, adhesive and
  ties are unchanged; a post-check enforces this on every job.
- **Metadata:** none differs in the INP. The generic provenance schema
  (`auto-id/forward-job/v1`) is new and versioned. It is a separate document, not
  INP content, and it reproduces the accepted provenance hashes.

---

## M4 — Auto-ID orchestrator + mode identity

| Id | Mini-step | Status |
|---|---|---|
| M4.1 | `IdentificationPairingPolicy` | `ACCEPTED` |
| M4.2 | Baseline observation / pair freeze | `ACCEPTED` |
| M4.3 | Physical modal-family classifier: P_x/P_y, nodal structure, diagonal symmetry when relevant | `ACCEPTED` (thresholds PROVISIONAL) |
| M4.4 | Cluster trigger + principal-angle / subspace confirmation | `ACCEPTED` |
| M4.5 | FE-to-FE branch tracker | `ACCEPTED` |
| M4.6 | Resumable pipeline: candidate → INP → Abaqus → ODB → extraction → registration → fixed observations → residual | `ACCEPTED` |
| M4.7 | Log-frequency objective | `ACCEPTED` |
| M4.8 | Bounded LM / trust step with the correct minus sign | `ACCEPTED` |
| M4.9 | Synthetic digital-twin recovery | `ACCEPTED` |

M4.9 synthetic truth: E = 45000 MPa, G12 = 4000 MPa, controlled frequency noise
≈ 0.3 %; start E = 52000 MPa, G12 = 4500 MPa.

**M4 GATE:** recover the truth within 1σ in ≤ 20 authorised Abaqus solves. An
artificial branch exchange must trigger refusal, not silent re-pairing.

Stage status: `ACCEPTED` (M4.1–M4.9 `ACCEPTED` by the SUPERVISOR, 2026-10-05; **M4 GATE: `PASS`**;
merged to `main` by PR #31, merge commit `ee22e33`, with HUMAN authorisation).

**M4 GATE: `PASS`** (SUPERVISOR, 2026-10-05; `tests/test_m4_stage_gate.py`, records only, no Abaqus):
- **Recovery:** the synthetic twin was recovered within 1σ: E 45005.45 / G12 4012.20 MPa against the truth
  45000 / 4000. |ln error| / sd: E 0.000121 / 0.002064; G12 0.003046 / 0.009951.
- **Budget:** 6 of 20 identification evaluations (5 reused archived evaluations, 1 new Abaqus
  solve plus 1 pinned extraction). No bound was active.
- **Branch exchange:** an artificial exchange is refused (the real-pack negative control gives
  `BRANCH_LOSS`; no re-pairing).
- **Determinism and M3:** deterministic journal replay; M3 contracts unchanged.
- **Abaqus work:** all of it ran under HUMAN gates: 3 solves (smoke, truth, loop) and 9 Abaqus Python
  runs (6 in the extraction gate, 3 pinned extractions).
- **Qualifications:**
  - the M4.3 classifier thresholds stay PROVISIONAL;
  - real SP13 identification stays refused (its strict real observation set is insufficient and
    near-collinear; option C), so M4.9 is the synthetic-twin gate, not a real-specimen
    identification;
  - SP02 stays NOT_FROZEN and excluded;
  - the M4.9 bounds are development-only twin bounds.
- **Evidence:** EVIDENCE.md M4 entries (all `ACCEPTED`); M4_DECISION_RECORD.md §1–§12; DECISIONS.md
  D-032–D-038.

Stage history (for the record):
First development batch (SUPERVISOR-authorised): M4.1–M4.5, M4.7, M4.8. Rules for the batch:
- no Abaqus execution; Abaqus Python on archived ODBs counts as an Abaqus run;
- no real solve pipeline; M4.6 and M4.9 need new authorisation;
- the archived CARBON-4C baseline replay is the M4.2 reference observation source;
- SP02/SP13 are development and test only (M2 production readiness `NOT_READY`);
- the M3 contracts are unchanged.

First batch reviewed by the SUPERVISOR:
- M4.1, M4.3, M4.4, M4.5, M4.7 and M4.8 are acknowledged as `REVIEW_READY`.
- M4.2 is `BLOCKED_WAITING_FOR_ODB_SHAPE_EXTRACTION`: the archived baseline lacks FE mode shapes,
  and Abaqus Python extraction needs a separate HUMAN gate.
- M4.6 and M4.9 had not started at that point (both were later completed; see below).
- ODB shape-extraction gate (HUMAN-authorised; review PASS): 6 validated shape packs
  ([fe_shapes/](fe_shapes/README.md)). M4.2 integrated with complete MAC matrices: back to
  `REVIEW_READY`. SP13 is FROZEN (2 rows); SP02 is NOT_FROZEN (1 strict pair < 2).
- SUPERVISOR review of M4.2:
  - M4.2 is unblocked and `REVIEW_READY` (not `ACCEPTED`).
  - SP13 is the candidate frozen observation set.
  - SP02 remains excluded from identification.
  - Criteria and thresholds are unchanged.
- M4.3 real validation on the SP13 baseline shape pack: `REVIEW_READY`.
  - 24/24 modes classified; mirror coverage 100 %.
  - Frozen rows: R1 (FE 10) is odd-even, R2 (FE 11) is even-odd.
  - Holdouts: no torsion holdout; the validation holdout is R2; one fit row remains.
  - Thresholds unchanged and PROVISIONAL.
- M4.4 real cluster confirmation of SP13 R1/R2: `REVIEW_READY`.
  - The trigger fired, but the decision is **INDEPENDENT**: individual identity is stable
    (MAC 0.999998) in all ±5 % E/G12 directions.
  - R1 and R2 remain two observations. Criteria unchanged.
- M4.6 resumable pipeline (architecture plus fake-solver tests; no real Abaqus):
  `REVIEW_READY`.
- M4.6 SP13 smoke gate (HUMAN-authorised: 1 Abaqus 2024 solve plus 1 pinned extraction):
  **REPRODUCED**.
  - 30/30 eigenfrequencies exact.
  - Shape-pack content SHA identical to the validated baseline pack.
  - M3 contracts unchanged.
  - **SUPERVISOR ACCEPTED** (2026-10-05). The archive of the smoke provenance remains a
    proposal.
- SUPERVISOR review of M4.4:
  - `REVIEW_READY`: R1/R2 are independent branches; no cluster merging.
  - The M4.3 holdout selection leaves one real fit row for two parameters. This was resolved by option C
    (real SP13 identification refused, M4_DECISION_RECORD §5.1).
- M4.9 preparation (fake solver only; no Abaqus): `REVIEW_READY`.
  - Twin builder, observation pipeline and M4.6 integration in
    `services/synthetic_twin.py`; tests A–E pass.
  - SUPERVISOR decisions recorded in M4_DECISION_RECORD.md §8; dependency boundary
    restored (the twin reaches M3 only through the M4.6 pipeline layer).
  - The real M4.9 gate was not started at that point (it later ran under its own HUMAN gates).
- M4.9 truth / observation-readiness gate (HUMAN-authorised: 1 truth solve + 1
  pinned extraction): **REFUSED_BEFORE_IDENTIFICATION**.
  - Strict freeze: 23 rows.
  - Trigger groups FE 13–15 and FE 20–23 are UNSUPPORTED (> 2 modes), so the
    design is REFUSED under §8.2.
  - The identification loop was not started; the SUPERVISOR then decided option A1 (D-032).
- M4.4 option A1 (N > 2 groups INDEPENDENT only; D-032): implemented.
  - The zero-Abaqus readiness re-run gives **READY_FOR_IDENTIFICATION**:
    FE 13–15 and FE 20–23 are INDEPENDENT; 21 fit terms; holdouts R1 and R23.
  - Identification loop: run later under its own HUMAN gate (see the next item).
- M4.9 real identification loop (HUMAN-authorised): **CONVERGED**.
  - Result: E 45005 MPa, G12 4012 MPa (truth 45000 / 4000); both within 1σ.
  - Effort: 6 evaluations (5 reused, 1 new solve).
  - **ACCEPTED** by the SUPERVISOR (2026-10-05).
- Decisions: [M4_DECISION_RECORD.md](M4_DECISION_RECORD.md) (accepted). Durable items are promoted to
  DECISIONS.md D-033–D-038; D-032 records A1.

---

## M5 — Practical identifiability + uncertainty

| Id | Mini-step | Status |
|---|---|---|
| M5.1 | Full global + nuisance sensitivity matrix | `ACCEPTED` |
| M5.2 | Prior rows | `ACCEPTED` |
| M5.3 | Practical rank and posterior uncertainty | `ACCEPTED` |
| M5.4 | q_G nuisance-space projection | `ACCEPTED` |
| M5.5 | `statistical_sd` | `ACCEPTED` |
| M5.6 | Conditional Birge adjustment | `ACCEPTED` |
| M5.7 | Leave-one-family-out `model_form_robustness` | `ACCEPTED` |
| M5.8 | Residual family pattern test | `ACCEPTED` |
| M5.9 | IDENTIFIED / WIDE / NOT_IDENTIFIABLE verdict engine | `ACCEPTED` |

Stage status: `ACCEPTED` (M5.1–M5.9 `ACCEPTED` by the SUPERVISOR, 2026-10-06; **M5 GATE: `PASS`**,
synthetic and records only, 0 Abaqus; merged to `main` by PR #33, merge commit `ab75315`,
with HUMAN authorisation; SUPERVISOR decisions in [M5_DECISION_RECORD.md](M5_DECISION_RECORD.md),
D-039–D-048).
- Checkpoint M5-A (M5.1–M5.4) `REVIEW_READY`: `services/practical_identifiability.py` with
  synthetic tests. No Abaqus.
- Checkpoint M5-B (M5.5, M5.8, M5.6) `REVIEW_READY`: `services/identification_uncertainty.py`
  with synthetic tests and the M4.9 twin records-based control. No Abaqus.
- Checkpoint M5-C (M5.7) `REVIEW_READY`: `services/model_form_robustness.py` (linearised
  leave-one-family-out, D-042). No Abaqus.
- Checkpoint M5-D (M5.9) `REVIEW_READY`: `services/identification_verdict.py` plus
  `tests/test_m5_stage_gate.py` (synthetic gate cases A–G; M4.9 twin records-based control).
  D-045–D-047.
- **M5 GATE `PASS`:**
  - k_core absorption gives q_G ≈ 0 and G12 NOT_IDENTIFIABLE;
  - rank deficiency is a hard block with no override;
  - systematic model error gives no green verdict;
  - the uncertainty labels stay separate.

**M5 GATE:**

- synthetic case where G12 is absorbed by k_core gives q_G near zero and
  NOT_IDENTIFIABLE;
- rank-deficient cases cannot be overridden;
- systematic model error cannot receive IDENTIFIED;
- the uncertainty quantities stay separately labelled.

**M5 MILESTONE:** a scientifically guarded Auto-ID backend exists before final GUI
work.

---

## M6 — Independent physical calibration

| Id | Mini-step | Status |
|---|---|---|
| M6.1 | Bare carbon plate Stage A: identify D11, D66; derive E, G12 with propagated thickness uncertainty | `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059) |
| M6.2 | Repeat the same bare-plate experiment; measure true setup/retest uncertainty | `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059) |
| M6.3 | Printed core-tile free-free experiment; obtain an independent effective k_core prior for the defined topology/process | `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059) |
| M6.4 | Sensitivity budget for fixed transverse carbon constants E3, ν13, ν23, G13, G23; include them if their uncertainty is not negligible | `ACCEPTED` (CLOSED; D-066–D-068): all five `NEGLIGIBLE_FOR_BUDGET`, kept fixed |

Stage status: **`ACCEPTED`** (SUPERVISOR 2026-10-08; M6 gate PASS; merged to `main` by PR #35, merge commit
`f1274cae80a6b3972cef04fd9c1bee0505920311`, with HUMAN authorisation). History: `IN_PROGRESS` (SUPERVISOR entry decisions 2026-10-06; branch `auto-id/m6` from `main` `ab1dc60`;
decisions in [M6_DECISION_RECORD.md](M6_DECISION_RECORD.md), D-049–D-061; rescoped by SPEC §19 item 6; M6 gate
`NOT_EVALUATED`; M7 `NOT_STARTED`).
- Checkpoint M6-A `REVIEW_READY`: entry decisions recorded; HUMAN SP-11 experiment checklist
  [M6_SP11_EXPERIMENT_CHECKLIST.md](M6_SP11_EXPERIMENT_CHECKLIST.md). No Abaqus.
- Checkpoint M6-B `REVIEW_READY`: `domain/stage_a_experiment.py` + `services/stage_a_validation.py`
  (Stage-A → M5 adapter, `STAGE_A_VALIDATION` context) with synthetic tests. No Abaqus.
- Corrective governance 2026-10-06 (§15; D-057, D-058): M6.1 and M6.2 are `BLOCKED_ON_EXPERIMENT`.
  - Reasons: no governed fitted SP-11 modal set, inconsistent sessions, incomplete physical support
    data, and no new SP-11 experiment available.
  - The checklist is now a reference record; the real-specimen inventory is in
    [SNADWICH_INVENTORY.md](SNADWICH_INVENTORY.md).
  - This ROADMAP and SPEC §17 were unchanged at that point.
- **M6 rescope 2026-10-06 (SPEC §19 item 6; D-059, D-060, D-061; §16):**
  - M6.1, M6.2 and M6.3 are `NOT_AVAILABLE_WITH_CURRENT_SETUP`. Their consequences are kept: G12 follows
    §5/§5.1 (D-046), there is no real-data Stage-A validation, k_core is only a later PROVISIONAL
    nuisance, and Σ_setup stays at the flagged provisional 0.3 %.
  - M6.4 is the remaining executable step (FE-only); it needs an approved range source.
  - The STEEL gate is removed (D-060): results are labelled not externally validated.
- **SP-13 physical registration gate 2026-10-06 (zero Abaqus; D-062, D-063; §17):**
  - A production-ready physical registration was rebuilt from the stored PSV records. The legacy
    centred registration is historical only (point error median 26 mm, max 47 mm).
  - Strict pairs 4↔10 and 7↔13 are well conditioned (condition number 252 → 6.3), but after the
    unchanged M4.3 holdout SP-13 alone still has one fit row.
  - SUPERVISOR-ACCEPTED (D-064).
- **SP-13 HUMAN update and SP-02 physical registration gate 2026-10-06 (zero Abaqus; D-064; §18),
  `REVIEW_READY`:**
  - SP-13 (H7, H8): in-plane signs physically established; `scale_rel` 0.002 (readout only).
    M2.4 is EVALUATED and `registration_limited` is False. Σ_setup stays provisional (H9).
  - SP-02 has the same Polytec anisotropy, and the legacy registration is wrong by median 29 mm.
    The physical registration (same method) freezes 3 strict pairs, leaving 2 fit rows after the
    unchanged M4.3 holdout (condition number 6.1).
  - SP-02 identity needs one HUMAN confirmation.
  - Combined with SP-13: 3 fit rows, rank 2. The SP2/SP10 reference scatter test stays
    NOT_AVAILABLE (§18.2).
- **Specimen catalog 2026-10-06 (documentation/governance checkpoint, zero Abaqus), `REVIEW_READY`:**
  - `SPECIMEN_CATALOG.md` (canonical) + `specimen_catalog.json` (machine index, not a runtime
    dependency).
  - 14 physical specimens with records: SP-01 … SP-13 and SP-15. SP-14 has no physical record.
  - SP-02 identity: SP02_IDENTITY_RESOLVED_FROM_RECORDS (DERIVED), pending SUPERVISOR.
  - REAL_CONFLICT C1: a PolyMAX fit of SP-13 260909 exists, against H9. Σ_setup stays provisional.
  - SUPERVISOR-ACCEPTED 2026-10-07 (D-065).
- **D-065 governed updates 2026-10-07 (zero Abaqus), `REVIEW_READY`:**
  - SP-02 is active on the accepted physical registration (fixture `SP02/bravo-1-physical`). The
    legacy chain is historical.
  - The SP-13 260909 PolyMAX set "Bravo (1)" is frozen as the FREQUENCY_ONLY fixture
    `SP13/260909-bravo-1` (provenance confirmed).
  - Σ_setup stays provisional 0.3 %. M6.4 remains the M6 blocker.
  - SUPERVISOR-ACCEPTED 2026-10-07 as the M6.4 basis (D-066).
- **M6.4 screening (D-066):**
  - Envelope `LITERATURE_INTERIM_SCREENING_ENVELOPE` (not material-specific): E3 5–10 GPa, ν13/ν23
    0.2–0.4, G13/G23 2.2–5 GPa.
  - Rule: the SPEC §5 0.3 % on the frozen observation rows, one constant at a time, both endpoints,
    FE-to-FE tracking. The criterion is bookkeeping, not a fit target.
  - **M6.4a (zero Abaqus), `REVIEW_READY`:**
    - the envelope record `screening/M6_4_transverse_envelope.json`;
    - the guarded screening path: `forward_builder.prepare_screening_job`,
      `services/transverse_screening.py`, `tools/m6_4_transverse_screening.py`;
    - tests;
    - HUMAN Abaqus manifest `6d34179c…`: 16 solves, 16 extractions; the baselines are reused.
  - **M6.4b, `TODO`:** the 16 solves and extractions under a HUMAN Abaqus gate, then the result record.
  - M6.4a SUPERVISOR-ACCEPTED 2026-10-07 (D-067). The HUMAN Abaqus gate was authorised for manifest
    `6d34179c…`.
  - **M6.4b (16 solves, 16 extractions, 0 failures), `REVIEW_READY`:**
    - E3, ν13, ν23, G13 and G23 are all `NEGLIGIBLE_FOR_BUDGET`. The global max |Δf/f| is
      0.0353 % (G23, SP-13 R2).
    - Every frozen row was tracked, with no refusal.
    - Result `screening/M6_4_transverse_screening_result.json`.
  - **M6 gate (rescoped): worker evaluation PASS**, pending SUPERVISOR (M6_DECISION_RECORD §20).
  - M6.4b SUPERVISOR-ACCEPTED 2026-10-08 (D-068). M6.4 is CLOSED.
- **M7-entry wiring and M6 closure record (D-068, zero Abaqus), `REVIEW_READY`:**
  - The active inputs are on the physical registrations:
    - SP-02: `SP02/bravo-1-physical` + `SP02.physical.forward.json`;
    - SP-13: `SP13/best-physical` (new) + `SP13.physical.forward.json`.
  - The historical M0–M5 chains are unchanged.
  - M6 gate: **PASS candidate**, pending final SUPERVISOR acceptance.
  - The remaining M7 prerequisites are listed in M6_DECISION_RECORD §21. M7 NOT_STARTED.

**M6 GATE (rescoped, SPEC §19 item 6, D-061): PASS (SUPERVISOR 2026-10-08; M6_DECISION_RECORD §22)**

- all unavailable physical evidence is explicitly recorded;
- every missing prior has its conservative verdict consequence encoded;
- provisional inputs are explicitly flagged;
- the M6.4 transverse-constant sensitivity budget is closed.

(Former gate: "critical priors and uncertainties are physically supported, not guessed";
superseded 2026-10-06.)

> **Decided ([D-017](DECISIONS.md#d-017--bare-plate-g12-is-material-family-specific)), bare-plate G12 is material-family specific:**
>
> - the **twill 350×350** bare plate is the Stage-A real-carbon validation specimen and
>   the twill-family specimen;
> - it does **not** provide primary G12 for **old plain 0.45**;
> - old plain 0.45 requires its own bare-plate evidence for primary G12, unless the
>   sandwich-only conditional path satisfies SPEC §5.1.

---

## STEEL INDEPENDENT VALIDATION GATE

Immediately after M6: perform an independent steel beam or plate experiment. The known
material stiffness is the external truth. Auto-ID must recover steel stiffness within
its declared uncertainty.

**If this fails: STOP before accepting final carbon material conclusions.** (D-015)

| Id | Gate | Status |
|---|---|---|
| STEEL | Independent steel validation | `SUPERSEDED` (D-060) |

> **Superseded 2026-10-06 (D-060, SPEC §19 item 6):** no steel or external known-stiffness
> validation is part of the selected release path. Real carbon results are reported as
> model-calibrated effective constants, labelled **not externally validated**.

---

## M7 — Multi-specimen carbon campaign

| Id | Mini-step | Status |
|---|---|---|
| M7.1 | `family.json` campaign | `ACCEPTED` (D-070): RUN_A + RUN_B campaigns; RUN_A release candidate, RUN_B diagnostic (D-075) |
| M7.2 | Old plain 0.45 family where scientifically compatible: SP1, SP2, SP10, SP13 | `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance; not DONE |
| M7.3 | Shared vs separate fits | `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance; not DONE |
| M7.4 | Δχ² or bootstrap consistency test | `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance; not DONE |
| M7.5 | Global E_in | `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance; not DONE |
| M7.6 | Conditional secondary G12 evidence | `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance; not DONE |
| M7.7 | Specimen-specific nuisance results | `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance; not DONE |
| M7.8 | Holdout / model-form diagnostics | `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance; not DONE |

**M7 GATE:** if one shared carbon vector cannot explain the family, NO global material
number is reported.

Stage status: **`ACCEPTED`** (D-077, 2026-10-09; **M7 GATE: `PASS` — `PASS_BY_REFUSAL`**). SPEC §13 family consistency
**FAIL** for the SP-02 / SP-13 shared model → formal output **NO_GLOBAL_PARAMETER_VALUE**; the program withholds the
global value as the M7 GATE requires — a successful scientific refusal, not a green material identification. M7b
corrective merged by PR #39 (merge commit `b9db2c1`). The D-075 acceptance and its release rationale were
superseded by D-076. Historical:
merged to `main` by PR #37, merge commit `0f15db9`, with HUMAN authorisation; opened D-069 on branch `auto-id/m7`
from `main` `9f5f63a`; decisions in [M7_DECISION_RECORD.md](M7_DECISION_RECORD.md).
- **M7.1 (zero Abaqus), `REVIEW_READY`:** the RUN_A campaign architecture.
  - Specimens `SP02/bravo-1-physical` + `SP13/best-physical`. Only E_in is fitted; G12 is fixed at 4 500 MPa.
  - FIT rows `SP02:R1`, `SP02:R2`, `SP13:R1`; HOLDOUT rows `SP02:R3`, `SP13:R2`.
  - Σ_setup 0.3 % PROVISIONAL; Σ_meas NOT_AVAILABLE.
  - Hard budget of 16 new solves.
  - Proposed manifest `e4ba607f…` (not executed). RUN_B is diagnostic only and needs its own later gate.
  - M7.1 ACCEPTED (D-070). Gate 1 (archived SP-02 extraction) was accepted at `0837921`.
- **RUN_A (HUMAN gate 2, D-071), `REVIEW_READY`:**
  - CONVERGED, 2 new solves; Ê_in = 55593 MPa; max |error| 6.79 %
    (all rows within 10 %).
  - `EFFECTIVE_MODEL_PARAMETER_ESTIMATE`; M5 NOT_IDENTIFIABLE; not externally validated.
  - RUN_B not started.
  - RUN_A ACCEPTED and CLOSED (D-072).
- **RUN_B preparation (D-072, zero Abaqus), `REVIEW_READY`:**
  - The diagnostic `EFFECTIVE_MODEL_COMPENSATION_TEST`: E_in + G12 from the governed start.
  - Proposed manifest `5fd0946a…`: 2 SP-02 G12± archive extractions, then at most 24 new solves.
  - Not executed.
- **RUN_B HUMAN gate 1 (D-073), `REVIEW_READY`:** the 2 SP-02 G12± archive extractions (0 solves) validate;
  manifest unchanged; RUN_B run identity `fb5234116c6e9413…`; budget 24 / 24. The RUN_B LM is not started.
- **RUN_B result (HUMAN solve gate, D-074), `REVIEW_READY`:** CONVERGED with 6 solves; E_in 50.89 GPa
  (-8.5 % vs RUN_A), G12 6.87 GPa (+52.7 %), diagnostic only;
  max |error| 4.17 %; M5 NOT_IDENTIFIABLE. Conclusion C (compensation / model-form dependence).
- **M7 closure (D-075), stage `REVIEW_READY`:** RUN_B ACCEPTED (diagnostic only); RUN_A E_in,eff = 55.593 GPa
  remains the release candidate (`EFFECTIVE_MODEL_PARAMETER_ESTIMATE`, not externally validated, M5
  NOT_IDENTIFIABLE). Campaign report gains `model_form_robustness.status` (an incomplete leave-one-family-out set
  is never zero model-form uncertainty). Unused budgets abandoned; no further M7 FE work. M7.2–M7.8 not pursued
  as separate mini-steps. Stage PR #37 prepared.
- **M7 ACCEPTED, M7 GATE `PASS`** (SUPERVISOR 2026-10-08). Merged to `main` by PR #37 (`auto-id/m7` → `main`),
  merge commit `0f15db9acf29b7d3a7b20350982440015e177e94`; reviewed head `87c05da`, merged tree identical.
  - M7.2–M7.8 stay `NOT_PURSUED_IN_M7` (D-075): superseded by the D-075 M7 stage conclusion and not required for M7 acceptance. They were deliberately not pursued as separate
    tasks and are **not** DONE.
  - Scientific results unchanged: RUN_A E_in,eff = 55.593 GPa (`EFFECTIVE_MODEL_PARAMETER_ESTIMATE`, not externally
    validated, M5 NOT_IDENTIFIABLE; 50.8–60.3 GPa only as `MODEL_DEPENDENCE_DIAGNOSTIC`); RUN_B diagnostic only.
  - No Abaqus after RUN_B. M8 `NOT_STARTED`.
- **M7b-DIAG corrective diagnostics (D-076, zero Abaqus), `ACCEPTED` (D-077; PR #39):** external audit iteration 2 (K1–K3
  CONFIRMED). Branch `auto-id/m7b-diag` from `main` `7a34ee6`.
  - K1: 55.593 GPa is HISTORICAL_RUN_A_OPTIMIZER_CANDIDATE only; **no global E_in for SP-02 / SP-13 under SPEC v1.1**.
  - K2: SPEC §13 implemented and wired into the M5 guard; RUN_A family consistency FAIL (Δχ² 746.27, Δdof 1, p_χ² 2.6e-164, bootstrap p 0.00025 (4000 samples, seed 20261009)); RUN_B NOT_EVALUABLE_RANK_DEFICIENT.
  - K3: CARBON-5G INP audit; additive physical-measurement records (passports unchanged).
  - Campaign report v2: optimizer candidate vs formal output; excluded-mode and per-specimen diagnostics.
  - SPEC v1.2 / SPECIMEN_ENGINEERING_CALIBRATION / τ_mf: not implemented (HUMAN decisions).
  - Full audit disposition (K1–K3, V1–V8, J1–J5); `uncertainty_basis` reporting (J5).

- **M7 closure merged:** PR #40 (`auto-id/m7b-closure` → `main`), merge commit `9bff6c7`.

### Policy track — SPEC v1.2 (ACCEPTED as normative, D-078)

**Current governing state (D-078, accepted 2026-10-09):** [SPEC_V1_2.md](SPEC_V1_2.md) is normative,
with unamended SPEC v1.1 clauses remaining in force. The two scientific questions and τ_mf rules were
accepted **before** further FE work; historical RUN_A/RUN_B records remain immutable and do not become
v1.2 calibrations. Policy-development documents `SPEC_V1_2_DRAFT.md`,
`SPEC_V1_2_POLICY_REVIEW.md`, and `SPEC_V1_2_POLICY_OPTIONS.json` are superseded historical records.
The policy was developed on `auto-id/spec-v1.2-policy` from `9bff6c7` and accepted via PRs #41/#42.
No SP10, t_face or additional FE solves are authorised by policy acceptance.

- **Policy PR merged:** PR #41 (`auto-id/spec-v1.2-policy` → `main`), reviewed head `62903ef`, merge commit
  `edb3070` (tree identical). The final review added the calibration precision gate
  (conservative_uncertainty ≤ 0.08).
- **Normative acceptance (D-078):** `SPEC_V1_2.md` is the governing scientific contract; SPEC v1.1 is archived and
  immutable. Implementation is tracked below: V12-I1–I6 ACCEPTED and merged (scientific / readiness implementation track ACCEPTED). Production calibration execution remains blocked / not authorised.

### Implementation track — SPEC v1.2 (before any SP10 / new FE work)

**Scientific / readiness implementation track: ACCEPTED** — V12-I1–I6 ACCEPTED and merged (final step PR #49).
This does **not** authorise real calibration execution. Separate states:

| State | Value |
|---|---|
| Scientific / readiness implementation | `ACCEPTED` |
| Production calibration execution | `BLOCKED / NOT_AUTHORISED` |
| HUMAN-authorised real calibration run | `NOT YET AVAILABLE` |
| M8 | `IN_PROGRESS` — accepted scope `READ_ONLY_EXISTING_JOURNALLED_RUNS` (M8.1–M8.8 `ACCEPTED`); original M8 GATE `NOT_MET` (D-079); historical prototype branch `auto-id/m8` `PARKED` |

A synthetic (fake-solver) RELEASED record proves the adapter only; it is never an accepted physical calibration.
No new FE work is authorised. Each step requires explicit SUPERVISOR authorisation, one at a time,
tests and review. No `install_*` layer: CLI and GUI must use the same scientific backend services.

| Id | Step | Status |
|---|---|---|
| V12-I1 | Campaign / run question (MATERIAL_IDENTIFICATION or SPECIMEN_ENGINEERING_CALIBRATION) and τ_mf schema, both declared before execution and bound into the campaign / run identity | `ACCEPTED` |
| V12-I2 | Holdout and residual-family magnitude bounds max(3σ, τ_mf) / max(2σ, τ_mf); τ_mf kept out of Σ, Φ, whitening, every uncertainty and §13 | `ACCEPTED` |
| V12-I3 | Specimen calibration gate: observability, non-degradation (max + RMS + 8 % row ceiling), precision conservative_uncertainty ≤ 0.08, refusal without fallback | `ACCEPTED` |
| V12-I4 | Calibration reporting / output record: released/refused labels, bound identities, diagnostics and uncertainty; optional CAL_* material cloned from pinned source INP with Density and other supported options retained | `ACCEPTED` |
| V12-I5 | Negative/regression closure: no fallback; τ_mf cannot rescue §13 FAIL; historical records immutable; calibration material cloning must fail closed on unknown/ambiguous Abaqus options | `ACCEPTED` |
| V12-I6 | SPEC v1.2 backend/GUI readiness with the same scientific services (no `install_*`); the M8 GUI track was later built on the same backend (see M8, D-079) | `ACCEPTED` |

- **Normative acceptance merged:** PR #42 (`auto-id/spec-v1.2-acceptance` → `main`), merge commit `61b5016`.

**Historical checkpoint note:** the `REVIEW_READY` descriptions below reflect the stage when each PR was prepared,
not today's acceptance status. The table above and `STATUS.json` define the current states.
- **V12-I1 (historical REVIEW_READY checkpoint, branch `auto-id/v12-i1` from `61b5016`):** campaign schema
  `auto-id/identification-campaign/v1.2` with mandatory `scientific_question` and `tau_mf` (0 < τ_mf ≤ 0.02), both in
  the campaign identity; specimen cardinality by question (v1 and v1.2 MATERIAL_IDENTIFICATION ≥ 2, v1.2
  SPECIMEN_ENGINEERING_CALIBRATION exactly 1); v1 definitions and the M7 identities unchanged; calibration
  execution refused with
  `SPECIMEN_ENGINEERING_CALIBRATION_NOT_IMPLEMENTED` until V12-I3; τ_mf has no numerical effect until V12-I2.
  Production v1.2 implementation remains incomplete.

- **V12-I1 accepted and merged:** PR #43 (`auto-id/v12-i1` → `main`), merge commit `4e3a1eb`.
- **V12-I2 (historical REVIEW_READY checkpoint, branch `auto-id/v12-i2` from `4e3a1eb`):** for a v1.2 campaign with declared τ_mf, each
  governed term is judged with its own σ_term in ln f: a family is systematic when it has ≥ 2 FIT terms of one sign and
  every |Δ ln f| > max(2σ_term, τ_mf); a holdout fails when |Δ ln f| > max(3σ_term, τ_mf); equality passes. Clusters
  use the objective's σ_C. v1.1 rules, records and hashes unchanged; τ_mf stays out of Σ, Φ, whitening, every
  uncertainty and §13. Production v1.2 implementation remains incomplete.

- **V12-I2 accepted and merged:** PR #44 (`auto-id/v12-i2` → `main`), merge commit `e702959`.
- **V12-I3 (historical REVIEW_READY checkpoint, branch `auto-id/v12-i3` from `e702959`):** pure specimen-calibration scientific gate
  `services/specimen_calibration_gate.py` (`evaluate_calibration_gate`): question / τ_mf / one specimen, observability
  (k + 1 FIT family keys, full rank, complete leave-one-FIT-family-out, disjoint HOLDOUT family), pairing / tracking,
  no active bound, registration / peak, the V12-I2 pattern record, non-degradation (max, RMS, 8 % rows), precision
  (conservative_uncertainty ≤ 0.08 per parameter) and reporting completeness. PASS / REFUSED with reasons; no value is
  released; production calibration execution stays refused until V12-I4.

- **V12-I3 accepted and merged:** PR #45 (`auto-id/v12-i3` → `main`), merge commit `3218663`.
- **V12-I4 (historical REVIEW_READY checkpoint, branch `auto-id/v12-i4` from `3218663`):** `services/specimen_calibration_output.py` —
  `build_calibration_output` evaluates the I3 gate on the same evidence bundle and builds the deterministic
  calibration record (RELEASED: exactly the judged p̂ as MODEL_CALIBRATION_PARAMETER with SPECIMEN_ENGINEERING_CALIBRATION,
  NOT_A_MATERIAL_PROPERTY, NOT_TRANSFERABLE_WITHOUT_VALIDATION; REFUSED: diagnostic optimiser candidate only), bound to
  specimen, test run, forward model, INP, registration, campaign, run, τ_mf and the gate; full physical-row table,
  excluded diagnostics, I3 precision / uncertainty basis / non-degradation. `render_calibration_inp_fragment` renders a
  distinct CAL_* material only from a RELEASED record, governed Engineering Constants, and the **exact pinned
  source INP bytes** (model-input SHA-256 verified). It clones the complete **supported** production material block,
  preserving `*Density` and other source material options; only its name and governed elastic constants change.
  It reuses pure forward-builder parsing/rewrite helpers, writes no files and calls no solver.
  Production calibration orchestration stays blocked pending V12-I5 / V12-I6.

- **V12-I4 accepted and merged:** PR #46 (`auto-id/v12-i4` → `main`), final reviewed head
  `1fcabc47d32560816dc67dfb4c1a6d6b2d2d2f6c`, merge commit `90e237849f72e55c58359245ddb9d3b2956bc3bc`
  (tree `508aaf8704a4d7496ef22d59ec08b01bd12f6937`, identical to reviewed head).
  Post-merge main Linux CI **success** (run `37904375035`). Historical records and I3 science unchanged.
- **V12-I5 (historical REVIEW_READY checkpoint after REWORK, PR #47, branch `auto-id/v12-i5` from `90e2378`, synchronised with `main` `c96e385`):**
  `tests/test_v12_i5_contract_closure.py` — end-to-end negative / regression matrix (no fallback, τ_mf boundaries and
  exclusion from Σ / uncertainty / §13, §13 FAIL not rescued by τ_mf, refusals without released values, anti-mixing,
  cluster member rows, historical records pinned, production calibration refused). The calibration material clone is
  **fail-closed**: the governed block must end at `*Material`, `*Step` or end of input; any other keyword (e.g.
  `*Mohr Coulomb`) refuses the fragment. SUPERVISOR review (head `00e210c`): matrix and fragment fix accepted in
  principle; REWORK to close the evidence-binding findings F1 (authoritative candidate evaluation binding p̂, residuals,
  robustness and FE identity) and F2 (baseline Δ ln f = ln(f_FE / f_EXP) of the frozen baseline pairing, SPEC v1.1 §6
  S3).
- **V12-I5 binding closure:** F2 — the §7 baseline is the frozen FE reference state at p0: per governed physical
  row Δ ln f = ln(f_FE / f_EXP) of the frozen observation set (`governed_baseline_rows`), any other baseline is an
  input inconsistency. F1 — `services/candidate_evaluation_evidence.py`: the calibration bundle must be the verified
  evaluation of one candidate in the specimen's M4 pipeline journal; p̂, residuals, tracking, pattern, M5 records and
  the FE / job / pack identity are re-derived from the journal, the pinned INP and the content-addressed packs and
  compared. Confirmed clusters are refused as unverified (no per-member evidence in M4).
- **V12-I5 accepted and merged:** PR #47 (`auto-id/v12-i5` → `main`), reviewed head `c897b478cc0039aa39460409c06f069b2bb36da8`, merge commit
  `248d7eb5c66fa5568e70d34c0550fddf4dbad4cb` (tree `b14750cf7e5e8736dacd2b83d85a99fa31481db0`, identical to reviewed head). Post-merge main Linux CI **success** (run `37919318508`).
  Accepted with documented limitations.
- **Confirmed-cluster policy (SUPERVISOR decision, 2026-10-09):** a confirmed cluster keeps
  `CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE`; such a calibration cannot be RELEASED. M4's confirmed-cluster mean does not
  prove per-member frequency errors or tracking MACs; no per-member pairing rule is invented and there is no fallback
  (cluster-average 8 % comparison, average tracking MAC, arbitrary or highest-MAC member mapping, reassigned
  experimental modes, dropped members). Valid cluster mathematics for objective terms, pattern and observability is
  preserved. Implementation limitation only: SPEC and M4 unchanged.
- **V12-I6 (`ACCEPTED`; prepared as REVIEW_READY on PR #49, branch `auto-id/v12-i6` from `248d7eb`):** one read-only backend scientific path for a
  journalled run. `services/campaign_lm_provenance.py` proves the M5 Jacobian from the journals (governed run
  identity; one CONVERGED result of this run; every evaluation its candidate's and the identical record of the
  specimen's hash-chained pipeline journal, whose run identity is exactly the governed pipeline (`run_identity` of
  `specimen_pipeline_config`); the LM history's objectives, every step's strict acceptance decision and its
  successor, and the stop step at p̂ replayed; the accepted `reconstruct_lm_jacobian` reproduces the journalled local
  sd and stop step; LM-provenance corrections `b4b5baf`, `6da9fd1`). `services/campaign_scientific_backend.py`
  dispatches on the declared question: MATERIAL_IDENTIFICATION = the accepted campaign report unchanged;
  SPECIMEN_ENGINEERING_CALIBRATION = one specimen, declared τ_mf, every Jacobian evaluation re-derived from its
  content-addressed FE pack, the accepted M5 system on the specimen's FIT rows, I3 gate inputs from verified evidence
  only, and the I4 output (I3 gate + I5 verifier) on the same system and evaluation; clusters a readiness refusal; the
  INP fragment only for RELEASED. Typed readiness states with reasons; the existing Data Readiness Check page shows the
  stored record read-only. The calibration execution gate is unchanged: readiness only, no HUMAN-authorised production
  calibration run.

- **V12-I6 accepted and merged:** PR #49 (`auto-id/v12-i6` → `main`), reviewed head `23516fd781a266d13bd80151daba8cea8d3a8c8b`, merge commit
  `29e010e778d718a5cafa501fb925b6e9d437db85` (tree `15c7922f98acd4bd5021541a182f976dd1f68612`, identical to reviewed head). Post-merge main Linux CI **success** (run `37930220912`).
  Both final provenance findings closed (governed M4 pipeline run identity; strict LM acceptance decisions and step
  transitions).
- **Retained limitations:** a confirmed-cluster calibration cannot be released without per-member evidence
  (`CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE`, no fallback); the production execution gate remains in place; no governed
  production calibration campaign has been authorised; real Abaqus execution needs separate HUMAN approval; the M8 GUI track
  followed separately (read-only scope `ACCEPTED`, original M8 GATE `NOT_MET`; D-079). No scientific gate is relaxed.

**Companion material verdict (D-080, architecture decision `ACCEPTED`):** SPEC v1.2 §1 requires the material verdict of a calibration run to be
computed and shown first. Current state: `MATERIAL_VERDICT_NOT_COMPUTED` (temporary non-conformance by omission). Target:
a read-only companion material verdict from the run's existing journals (no Abaqus, FE, LM or new optimisation), with its
own record hash, shown first, never an input to the calibration gate or release; it is not a second scientific question
and not a fallback. Implementation step **V12-I7 `IN_PROGRESS`**: **V12-I7.1 core `REVIEW_READY`** (PR #63,
branch `auto-id/v12-i7-companion`) — `ScientificReadiness.companion_material_verdict` (calibration records only; own
schema and record hash; provenance = the run's existing journalled evidence), judged read-only by the accepted M7 report
body after the calibration verdict and never an input to it; the public `build_campaign_report` guard is unchanged. The PR #61 V1 gap
(material verdict of a calibration run shown as not computed) stays open until V12-I7 is accepted.
Production calibration execution stays `BLOCKED / NOT_AUTHORISED`.

**External audit corrections V1 / V2 (`REVIEW_READY`, branch `auto-id/v12-audit-v1-v2`, reporting only):** V1 — the
material verdict (question, formal output, status / refusal) is shown first, read from the stored record, then the
calibration verdict; for a calibration run it shows `MATERIAL_VERDICT_NOT_COMPUTED` — a known temporary SPEC v1.2 §1
non-conformance, decided by D-080; the companion material verdict is implementation V12-I7 `TODO`. V2 — the calibration
output record (schema v2) carries the recorded `statistical_sd` and leave-one-FIT-family-out status; missing values stay
`NOT_AVAILABLE`; schema v2 changes the calibration `record_hash` and the derived `CAL_*` names (acceptable: no production
calibration records exist). No SPEC, threshold, M5 / M7 or RUN_A / RUN_B change; no Abaqus.

**V12 PRODUCTION GATE — EXECUTION NOT AUTHORISED:** the scientific / readiness implementation is accepted, but calibration
execution stays refused by the unchanged execution gate. A production calibration run, SP10, t_face or other FE work
requires a separate explicit HUMAN authorisation. Abaqus requires separate HUMAN authorisation.

---

## M8 — GUI Auto-ID

| Id | Mini-step | Status |
|---|---|---|
| M8.1 | Specimen / family wizard | `ACCEPTED` |
| M8.2 | Readiness screen | `ACCEPTED` |
| M8.3 | One Auto-ID button calling the same backend as the CLI | `ACCEPTED` |
| M8.4 | Progress / resume | `ACCEPTED` |
| M8.5 | Verdict presentation | `ACCEPTED` |
| M8.6 | Abaqus Engineering Constants block | `ACCEPTED` |
| M8.7 | Uncertainty / source breakdown | `ACCEPTED` |
| M8.8 | Evidence / provenance export | `ACCEPTED` |

**M8 GATE:** the user goes from a specimen/family folder to a scientifically guarded
result without manually entering optimisation numbers other than specimen/passport
measurements. No separate GUI scientific implementation. No new `install_*` layers.

Stage status: `IN_PROGRESS` — original M8 GATE still open (`NOT_MET`); accepted scope `READ_ONLY_EXISTING_JOURNALLED_RUNS` (D-079). SUPERVISOR final scope decision 2026-10-10: M8.1–M8.8 and the final integration review `ACCEPTED` for the read-only scope `READ_ONLY_EXISTING_JOURNALLED_RUNS`; the original gate is not waived and not marked PASS. The historical prototype branch `auto-id/m8` (`193db8d`) stays `PARKED` and untouched. **M8.1 `ACCEPTED`** (PR #51, branch
`auto-id/m8-1` from `196503e`): page "0. Auto-ID Setup" in the existing Effective Material Identification tab loads one
specimen folder or a family / campaign definition through the governed parsers and lists identity, physical
measurements, passport / fixture, modal-data source, forward model, INP / ODB references, physical registration, the
declared scientific question and τ_mf (NOT_DECLARED when not declared; never inferred), FIT / HOLDOUT rows, gaps and
provenance. Size-only file checks are `PRESENT_SHA256_NOT_VERIFIED`; nothing is shown as scientifically READY. Factual
loading only (no mode / family / registration choice, no LM, Abaqus, MAC, freezing or writes); scientific readiness
stays with the V12-I6 backend on the Data Readiness Check page. M8.1 merged: merge commit `27a587f` (tree
identical to reviewed head `7f91dfd`), post-merge main CI success (run `37943295401`).
**M8.2 `ACCEPTED`** (PR #52, branch `auto-id/m8-2` from `27a587f`): selection-aware Data Readiness Check. The
stored V12-I6 readiness record is shown only under its own governed selection — exact campaign hash, run type,
specimen labels, declared question and τ_mf, and run hash when a run is selected; never by names, folders, labels or
files. Otherwise `NOT_EVALUATED_FOR_SELECTION` (a presentation state, not a backend verdict); a specimen folder
without a governed campaign is never given a campaign result or an inferred question; an invalid selection clears the
shown result. Matching records are presented through `readiness_presentation`, unchanged; a match is not proof of
authenticity. M8.2 merged: merge commit `3bf5067` (tree identical to reviewed head `1208562`), post-merge main CI
success (run `37948118759`).
**M8.3 `ACCEPTED`** (PR #53, branch `auto-id/m8-3` from `3bf5067`): one read-only Auto-ID action,
"Auto-ID — Evaluate Stored Run". It requires a governed campaign (M8.1) and an explicitly selected journal of an existing
run; `services/stored_run_evidence.py` reads that run in the accepted journal layout (campaign hash must be the selected
campaign's; pipeline journals located by governed pipeline identity; FE packs and pinned INP loaded with verification;
missing parts left missing), calls `judge_campaign_run` and stores the backend record unchanged, shown selection- and
run-bound on the Data Readiness Check. No run, LM, planning, extraction, solver process or write. UI freshness
correction: a result is presented as current only for the exact journal and run of its latest successful evaluation;
any new selection or evaluation attempt invalidates it first, and a failed attempt shows
`NOT_EVALUATED_FOR_SELECTION` (a genuine backend NOT_READY / REFUSED is shown as returned). M8.3 merged: merge
commit `6db9a15` (tree identical to reviewed head `3b2693c`), post-merge main CI success (run `37964686863`).
**M8.4 `ACCEPTED`** (PR #54, branch `auto-id/m8-4` from `6db9a15`): read-only progress / resume *inspection*
of the explicitly selected stored run. `services/run_progress.py` verifies the campaign journal (format, directory = run
hash, hash chain, governed run identity) and each governed pipeline journal, then reports only journalled facts:
evaluations and refusals, LM result status / iterations / evaluations, Abaqus solves recorded and the run identity's
budgets, recorded refusal / stop, missing evidence. No percentage, remaining time, live state or completion; unverified
evidence shows no counts; a CONVERGED LM result is not a release. GUI: Refresh run progress (fresh from disk; a changed
journal makes an earlier evaluation non-current) and Reopen selected run (re-verified; evaluation not current); a new
selection clears progress. Journal freshness covers the campaign journal and every governed pipeline journal; a
missing or unverified journal never compares equal, so an earlier evaluation is not kept current. Computational resume is
not enabled (HUMAN execution gate). M8.4 merged: merge commit `43ffb89` (tree identical to reviewed head
`79cf8ab`), post-merge main CI success (run `37974175785`).
**M8.5 `ACCEPTED`** (PR #55, branch `auto-id/m8-5` from `43ffb89`): a concise read-only verdict summary on the
Data Readiness Check, read only from the backend record shown under the current selection (`verdict_summary`): evaluated
campaign / run, declared question and τ_mf (not declared for v1), exact backend status, released values only from the
record's released fields (specimen calibration with its own labels; material values only for MATERIAL_VALUES_RELEASED),
refusal / not-ready reasons, diagnostic-only candidates, result type, solver profiles and production status.
NOT_EVALUATED_FOR_SELECTION is a GUI presentation state with no value or candidate. M8.5 merged (by HUMAN): merge
commit `3b77c19` (tree identical to reviewed head `95a1ae8`), post-merge main CI success (run `38033800330`).
**M8.6 `ACCEPTED`** (PR #56, branch `auto-id/m8-6` from `3b77c19`): read-only Engineering Constants and
calibration material preview on the Data Readiness Check, only for a RELEASED specimen calibration of the current
evaluation. The nine constants (E1, E2, E3, ν12, ν13, ν23, G12, G13, G23) are the accepted governed constants with exact
values, units and provenance (released calibration parameter / fixed campaign parameter / parameterisation-fixed
constant); the material block is the accepted I4/I5 fragment from the exact SHA-256-verified pinned source INP (distinct
CAL_* material, production material never overwritten, in memory only, no INP written, never attached). The GUI keeps
the exact typed backend evaluation and its verified source INP bytes bound to the active evaluation; a display-only
record, REFUSED / NOT_READY / MATERIAL_VALUES_RELEASED, a cluster, a selection or journal change and Reopen give
NOT_AVAILABLE_FOR_SELECTION. A synthetic RELEASED preview is labelled SYNTHETIC / TEST EVIDENCE and NOT AUTHORISED FOR
PRODUCTION. M8.6 merged: merge commit `4eb241d` (tree identical to reviewed head `8bbee80`), post-merge
main CI success (run `38037350167`).
**M8.7 `ACCEPTED`** (PR #57, branch `auto-id/m8-7` from `4eb241d`): one read-only uncertainty and
evidence-source section on the Data Readiness Check (`uncertainty_breakdown`), read from the record shown under the
current selection and, for material identification only, from the backend's formal campaign report of the current typed
evaluation. It shows the covariance basis (Σ_setup / Σ_meas status, complete vs conditional, provisional and missing
components), statistical_sd, the Birge adjustment, model-form robustness / leave-one-family-out, the conservative
calibration uncertainty against the recorded 0.08 ln p ceiling with the recorded decision, τ_mf separately as an
acceptance tolerance, question-specific evidence and the evidence sources (hashes, specimens, solver profiles, FE
sources, LM provenance, production status). Nothing is computed; a missing quantity is NOT_AVAILABLE with its recorded
reason. M8.7 merged: merge commit `f523c38` (tree identical to reviewed head `0d9a03f`), post-merge main
CI success (run `38040194804`).
**M8.8 `ACCEPTED`** (PR #58, branch `auto-id/m8-8` from `f523c38`): "Export Auto-ID Evidence..." on the Data
Readiness Check writes a deterministic, report-only JSON export snapshot (`auto-id/evidence-export-snapshot/v1`, kind
EXPORT_SNAPSHOT — not a scientific verdict and not an accepted evidence record) of the current typed evaluation: the
exact backend record with its hash, the backend material report (material identification), the M8.6 constants and
fragment as a non-production preview (RELEASED calibration), verified campaign / run / specimen / governed pipeline
identities, the evidence fingerprint and the M8.5 / M8.7 presentation. The campaign journal and every governed pipeline
journal are re-verified from disk immediately before export; a change since the evaluation refuses and invalidates the
active presentation, an unverifiable fingerprint refuses, and the run is never evaluated again. Written only after Save
As, atomically, outside the repository, the data stores and the selected run, never over a non-export file; no INP file. Final export-safety
correction (part of the accepted M8.8): the journals are re-verified again after the Save As dialog, immediately before
writing; temporary-file creation failures are a typed WRITE_FAILED refusal; undeterminable data-store roots refuse.
M8.8 merged: merge commit `1e88e9b` (tree identical to reviewed head `7f7408f`), post-merge main CI success (run
`38044596355`).
**Final M8 integration review** (governance PR #59, from `1e88e9b`): the complete M8.1–M8.8 workflow passes in the
real Tk application for the implemented read-only scope (governed definition → preparation → stored run → verified
progress → Evaluate Stored Run → verdict → breakdown → constants only under the release gate → verified deterministic JSON
export; Reopen / switch / Refresh / Save As freshness; RUN_A, RUN_B, synthetic calibration, NOT_READY, cluster, incomplete
LOO). **The original M8 GATE is not met in full:** no optimisation number is entered in the GUI, there is no separate GUI
scientific implementation and no new `install_*` layer, but a NEW specimen folder alone cannot reach a new scientific
result — a governed campaign definition (authored outside the GUI) and a previously journalled campaign run (produced
behind the HUMAN execution gate; production calibration execution BLOCKED) are prerequisites. No new scientific execution was enabled.
**SUPERVISOR final M8 scope decision (2026-10-10):** the M8.1–M8.8 read-only implementation and the final integration
review are `ACCEPTED`; accepted scope `READ_ONLY_EXISTING_JOURNALLED_RUNS` — campaign preparation, explicit stored-run selection, verified
progress, backend evaluation, scientific verdict, uncertainty, governed constants preview and safe export. **Original M8
GATE: `NOT_MET`.** Remaining gap: NEW specimen folder → governed campaign → new journalled scientific run → new result;
the GUI cannot currently complete this path. The limitation is acknowledged, not silently waived and not marked PASS.
Overall M8 stage: `IN_PROGRESS` — original gate still open. No authorisation for real Abaqus execution, new FE solves,
LM execution, computational resume, production calibration, SP10 or t_face; further work toward the original gate
requires separate explicit authorisation.
**M8 read-only closeout merged (D-079):** PR #59 (`auto-id/m8-integration-review` → `main`), reviewed head
`f31510d`, merge commit `149debc3172cb4adb3ba6fcc48635b770340783e` (tree `f5aca52`, identical to the reviewed head), post-merge main CI success
(run `38047072811`). Separate states: M8 stage `IN_PROGRESS`; accepted scope `READ_ONLY_EXISTING_JOURNALLED_RUNS`; original M8 GATE `NOT_MET`;
production calibration execution `BLOCKED / NOT_AUTHORISED`. Release test checkpoint on `149debc`: 2022 OK without
data stores (84 skipped), 2036 OK with all data stores (5 skipped), 0 failures. The parked prototype branch
`auto-id/m8` (`193db8d`) is untouched; selected code was reused. Production calibration execution remains
`BLOCKED / NOT_AUTHORISED`.
