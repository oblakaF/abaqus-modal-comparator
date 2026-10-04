# Auto-ID v1.1 Roadmap

Governing specification:
[docs/auto_id/SPEC_V1_1.md](SPEC_V1_1.md)

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
| M3.1 | Manifest-driven material location | `REVIEW_READY` |
| M3.2 | Generic candidate rewrite | `REVIEW_READY` |
| M3.3 | Generic provenance / job hash | `REVIEW_READY` |
| M3.4 | Remove production hard-coding of SP02, SP13, `D:\Snadwich` and specific machine paths from the generic Auto-ID path | `TODO` |
| M3.5 | Regression against the current accepted shared-carbon builder | `TODO` |

**M3 GATE:** the generic builder reproduces the accepted SP02/SP13 reference INPs
byte-for-byte, except any explicitly versioned metadata difference proven irrelevant.
No physics change.

Stage status: `IN_PROGRESS` (branch `auto-id/m3`, based on `main` `7af9038`).
M3.1–M3.5 run as one SUPERVISOR-authorised stage batch. No Abaqus. The accepted
shared-carbon builder stays unchanged as the regression oracle.

---

## M4 — Auto-ID orchestrator + mode identity

| Id | Mini-step | Status |
|---|---|---|
| M4.1 | `IdentificationPairingPolicy` | `TODO` |
| M4.2 | Baseline observation / pair freeze | `TODO` |
| M4.3 | Physical modal-family classifier: P_x/P_y, nodal structure, diagonal symmetry when relevant | `TODO` |
| M4.4 | Cluster trigger + principal-angle / subspace confirmation | `TODO` |
| M4.5 | FE-to-FE branch tracker | `TODO` |
| M4.6 | Resumable pipeline: candidate → INP → Abaqus → ODB → extraction → registration → fixed observations → residual | `TODO` |
| M4.7 | Log-frequency objective | `TODO` |
| M4.8 | Bounded LM / trust step with the correct minus sign | `TODO` |
| M4.9 | Synthetic digital-twin recovery | `TODO` |

M4.9 synthetic truth: E = 45000 MPa, G12 = 4000 MPa, controlled frequency noise
≈ 0.3 %; start E = 52000 MPa, G12 = 4500 MPa.

**M4 GATE:** recover the truth within 1σ in ≤ 20 authorised Abaqus solves. An
artificial branch exchange must trigger refusal, not silent re-pairing.

---

## M5 — Practical identifiability + uncertainty

| Id | Mini-step | Status |
|---|---|---|
| M5.1 | Full global + nuisance sensitivity matrix | `TODO` |
| M5.2 | Prior rows | `TODO` |
| M5.3 | Practical rank and posterior uncertainty | `TODO` |
| M5.4 | q_G nuisance-space projection | `TODO` |
| M5.5 | `statistical_sd` | `TODO` |
| M5.6 | Conditional Birge adjustment | `TODO` |
| M5.7 | Leave-one-family-out `model_form_robustness` | `TODO` |
| M5.8 | Residual family pattern test | `TODO` |
| M5.9 | IDENTIFIED / WIDE / NOT_IDENTIFIABLE verdict engine | `TODO` |

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
| M6.1 | Bare carbon plate Stage A: identify D11, D66; derive E, G12 with propagated thickness uncertainty | `TODO` |
| M6.2 | Repeat the same bare-plate experiment; measure true setup/retest uncertainty | `TODO` |
| M6.3 | Printed core-tile free-free experiment; obtain an independent effective k_core prior for the defined topology/process | `TODO` |
| M6.4 | Sensitivity budget for fixed transverse carbon constants E3, ν13, ν23, G13, G23; include them if their uncertainty is not negligible | `TODO` |

**M6 GATE:** critical priors and uncertainties are physically supported, not guessed.

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
| STEEL | Independent steel validation | `TODO` |

---

## M7 — Multi-specimen carbon campaign

| Id | Mini-step | Status |
|---|---|---|
| M7.1 | `family.json` campaign | `TODO` |
| M7.2 | Old plain 0.45 family where scientifically compatible: SP1, SP2, SP10, SP13 | `TODO` |
| M7.3 | Shared vs separate fits | `TODO` |
| M7.4 | Δχ² or bootstrap consistency test | `TODO` |
| M7.5 | Global E_in | `TODO` |
| M7.6 | Conditional secondary G12 evidence | `TODO` |
| M7.7 | Specimen-specific nuisance results | `TODO` |
| M7.8 | Holdout / model-form diagnostics | `TODO` |

**M7 GATE:** if one shared carbon vector cannot explain the family, NO global material
number is reported.

---

## M8 — GUI Auto-ID

| Id | Mini-step | Status |
|---|---|---|
| M8.1 | Specimen / family wizard | `TODO` |
| M8.2 | Readiness screen | `TODO` |
| M8.3 | One Auto-ID button calling the same backend as the CLI | `TODO` |
| M8.4 | Progress / resume | `TODO` |
| M8.5 | Verdict presentation | `TODO` |
| M8.6 | Abaqus Engineering Constants block | `TODO` |
| M8.7 | Uncertainty / source breakdown | `TODO` |
| M8.8 | Evidence / provenance export | `TODO` |

**M8 GATE:** the user goes from a specimen/family folder to a scientifically guarded
result without manually entering optimisation numbers other than specimen/passport
measurements. No separate GUI scientific implementation. No new `install_*` layers.
