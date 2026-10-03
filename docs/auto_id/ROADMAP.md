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
| M0.4 | Windows + Linux CI baseline | Factual test summaries; zero unexplained failures; skips documented; platform behaviour explicit | `REVIEW_READY` |

**M0 GATE:** trusted green baseline before M1.
Stage status: `IN_PROGRESS` (M0.1 `ACCEPTED`; M0.2 `ACCEPTED`; M0.3 `ACCEPTED`; M0.4 `REVIEW_READY`).

---

## M1 — Production experimental modal input

| Id | Mini-step | Content | Status |
|---|---|---|---|
| M1.1 | Identification input-source policy | Curve-fitted modes allowed. Peak-derived modes refused for production Auto-ID. | `TODO` |
| M1.2 | Production PolyMAX dataset 55/2414 path | Preserve frequency, shape, provenance, measurement DOFs. | `TODO` |
| M1.3 | Raw-FRF multi-mode fitting path | Dataset 58 may be used for identification only through an accepted multi-mode fit. Peak-only stays QC/screening. | `TODO` |
| M1.4 | Experimental QC | Suspension threshold; resolution; unresolved resonance (2ζf < 3Δf); coherence at resonance (< 0.9); phase complexity. | `TODO` |

**M1 GATE (SP13 raw FRF):** recover ≈ 206.15 Hz and ≈ 212.61 Hz within ±0.05 Hz of
PolyMAX; no false identification mode around 217.5 Hz; damping within 30 % of PolyMAX
(SPEC §17).

---

## M2 — Specimen manifest + physical registration

| Id | Mini-step | Status |
|---|---|---|
| M2.1 | `specimen_manifest` schema / domain / hash | `TODO` |
| M2.2 | Family / design / specimen / test-run identities with distinct keys `design_id`, `physical_specimen_id`, `test_run_id` | `TODO` |
| M2.3 | FrozenRegistration generated from physical calibration / passport | `TODO` |
| M2.4 | Registration uncertainty diagnostic (never optimisation) | `TODO` |
| M2.5 | Acquisition / remount linkage for Σ_setup | `TODO` |

**M2 GATE:** SP02/SP13 reproduce the accepted FrozenRegistration identities. The
registration perturbation diagnostic never changes the chosen geometry by optimising
MAC.

---

## M3 — Universal forward builder

| Id | Mini-step | Status |
|---|---|---|
| M3.1 | Manifest-driven material location | `TODO` |
| M3.2 | Generic candidate rewrite | `TODO` |
| M3.3 | Generic provenance / job hash | `TODO` |
| M3.4 | Remove production hard-coding of SP02, SP13, `D:\Snadwich` and specific machine paths from the generic Auto-ID path | `TODO` |
| M3.5 | Regression against the current accepted shared-carbon builder | `TODO` |

**M3 GATE:** the generic builder reproduces the accepted SP02/SP13 reference INPs
byte-for-byte, except any explicitly versioned metadata difference proven irrelevant.
No physics change.

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
