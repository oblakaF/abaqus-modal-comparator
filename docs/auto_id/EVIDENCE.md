# Auto-ID Evidence Index

Index of scientific evidence relevant to Auto-ID. This file holds compact summaries
and identities only.

**Never commit** large ODBs, UNVs, solver scratch, caches or user data. Evidence files
live in the local research archive. Here they are referenced by identity (hash, file
name, modal set) where known.

Entry fields: stage · status · purpose · input/provenance identity · compact result ·
external/archive location · normative vs diagnostic.

Only entries marked `ACCEPTED` (including "accepted as diagnostic") may be cited as
evidence (precedence item 5 in [README.md](README.md)). An entry changes status only
after explicit SUPERVISOR acceptance.

---

## CARBON-4C — Forward/replay chain control validation

- **Status:** ACCEPTED
- **Kind:** normative for the forward/replay chain; **not** a material fit.
- **Purpose:** control validation of the direct shared-carbon forward path.
- **Chain:** candidate Engineering Constants → deterministic INP → Abaqus → ODB →
  extraction → geometry identity → FrozenRegistration replay → modal comparison.
- **Provenance identity:**
  - forward builder `src/services/shared_carbon_forward.py` at
    `121ba1d06b7c268b3051f1407a3ea26a9027dca3`;
  - registrations
    [SP02_frozen_registration.json](../registrations/SP02_frozen_registration.json)
    (hash `9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164`, PolyMAX
    `SP02_polymax_retry_260803.unv`, modal set `bravo-1`) and
    [SP13_frozen_registration.json](../registrations/SP13_frozen_registration.json)
    (hash `a8970e525d10173af3d3b030b1150ca24432b616e1b52f6e8cfeefe2946f58a4`, PolyMAX
    `SP13_a_polymax.unv`, modal set `best`, 289 points).
- **Compact result:** the SP02 and SP13 control runs reproduced the accepted
  baselines. Same-index shape MAC = 1.0.
- **Archive location:** local research archive (ODBs not in Git). Exact path not
  recorded in this freeze.

## CARBON-5A — ±5 % full-Abaqus sensitivity of E_in_plane and G12

- **Status:** ACCEPTED
- **Kind:** diagnostic.
- **Purpose:** ±5 % full-Abaqus sensitivity of E_in_plane and G12.
- **Method:** fixed baseline observation branches. Branches tracked by FE shape
  continuity.
- **Compact result:** the joint matrix has numerical rank 2. The weak direction is
  mainly G12. SP02 and SP13 sensitivity directions are similar.
- **Important:** numerical rank 2 is **not** a production identifiability verdict under
  Auto-ID v1.1 (SPEC §10, AUDIT K2).
- **Provenance:** same registrations as CARBON-4C (PolyMAX). Not affected by K1.
- **Archive location:** local research archive; not in Git.

## CARBON-5B — Fixed-row local objective preview

- **Status:** ACCEPTED
- **Kind:** diagnostic.
- **Purpose:** fixed-row local objective preview for a shared carbon correction.
- **Compact result:** a shared carbon correction that improves SP13 degrades the
  already-good SP02.
- **Archive location:** local research archive; not in Git.

## CARBON-5C — Targeted SP13 diagnostic

- **Status:** ACCEPTED
- **Kind:** diagnostic.
- **Purpose:** targeted diagnosis of the SP13 discrepancy.
- **Compact result:** the SP13 discrepancy cannot safely be assigned to E/G12 alone.
  E1 ≠ E2 was not reopened without physical orientation traceability (D-005).
- **Archive location:** local research archive; not in Git.

## CARBON-5D — CAD→FE core lineage

- **Status:** ACCEPTED AS DIAGNOSTIC / HISTORICAL
- **Kind:** diagnostic / historical.
- **Purpose:** verify CAD→FE core lineage.
- **Compact result:** CAD→FE core lineage verified. Later direct measurements and the
  user's 4-piece vs 1-piece FE comparison make core segmentation/footprint a
  **secondary** suspect, not the primary explanation.
- **Archive location:** local research archive; not in Git.

## CARBON-5F — Shared PLA/core-stiffness sensitivity (SP02/SP13)

- **Status:** ACCEPTED
- **Kind:** diagnostic sensitivity evidence.
- **Supervisor acceptance:** ACCEPTED (2026-10-03), with the scope stated below.
- **Purpose:** shared PLA/core-stiffness sensitivity for SP02/SP13.

### Authorized solves

Exactly 4 full Abaqus modal solves:

- SP02 CORE_MINUS
- SP13 CORE_MINUS
- SP02 CORE_PLUS
- SP13 CORE_PLUS

No retries. No extra Abaqus solves.

### Perturbation

- **k_core:** 0.90 / 1.10.
- **Definition:** all six current core stiffness constants (E1, E2, E3, G12, G13, G23)
  are scaled proportionally by k_core:
  - CORE_MINUS: E1 = E2 = 2322, E3 = 1854, G12 = 873, G13 = G23 = 765 MPa.
  - CORE_PLUS: E1 = E2 = 2838, E3 = 2266, G12 = 1067, G13 = G23 = 935 MPa.
- **Unchanged:** Poisson ratios, density, mass, geometry, mesh, ties, face properties,
  adhesive/NSM and FrozenRegistration.
- **Baseline:** CARBON-4C states. Same registrations as CARBON-4C.

### Provenance identity

- **Source INPs:**
  - SP02 `SP02_Modal_V02.inp`, SHA-256
    `574ae78a897f5a666989716c54549969f13ca2919ad3af1f3ca658580a4ba8a5`.
  - SP13 `SP13_mesh_local_v1_modal.inp`, SHA-256
    `9d4105840e527354dbd0bb4d0d0012f7708125aa94619b0dcc486fd76dc70571`.
- **Job provenance hash:**
  `e3a026a7c47bdd11af7ef838428c2e2139f80be4eccb8432ce9b945ede8b4c09`.
- **Generated INP SHA-256:**
  - SP02 CORE_MINUS `267d66a2987f72766fe7893fd1c1d49980564f880402055d1b81b893f205d4af`
  - SP13 CORE_MINUS `b7a025a0e1b25fd4452c3b67d29a9af9c1d6e89506a52f2e07aa34929360841f`
  - SP02 CORE_PLUS `cedbec8d5c8ca2973157e3431e6671c3d5b18d15b01882848599f2476f2232d5`
  - SP13 CORE_PLUS `cdbfe3732dd3fef882c5b0af46a80abfa4df6f9246c30bc1e439f9edcf381b59`
- **Change check:** relative to the source INP, each generated INP differs only in the
  PLA `*Elastic` record. SP02 additionally changes its eigenvalue request from 15 to 30.

### Verification

- All 4 solves completed normally (Abaqus 2024).
- 30 eigenvalues each.
- Zero solver errors.
- All 19 post-run checks passed in every state.
- FE geometry identity exact.
- FrozenRegistration replay exact.
- Mass unchanged.
- All tracked branches preserved.
- Minimum tracking MAC approximately 0.99998 (registered U3 and full face).
- No mode-order change.
- Production pairing unchanged (diagnostic only): SP02 6 pairs and SP13 10 pairs, none
  added or removed, no gate crossings.

### Core sensitivity summary

The table below is the per-branch s_k column:
S_core = [ln f(k = 1.10) − ln f(k = 0.90)] / [ln 1.10 − ln 0.90].

| Branch | SP02 S_core | SP13 S_core |
|---|---|---|
| FE7 (holdout) | 0.0152 | 0.0183 |
| FE8 | 0.0064 | 0.0066 |
| FE9 | 0.0073 | 0.0081 |
| FE10 | 0.0106 | 0.0115 |
| FE11 | 0.0107 | 0.0125 |
| FE12 | 0.0153 | 0.0171 |
| FE13 | 0.0152 | 0.0135 |
| FE14–FE17 | — | approximately 0.0159–0.0200 |
| **Mean over fit rows** | **0.0109** | **0.0139** |

- **SP13/SP02 mean sensitivity ratio:** approximately 1.28.
- **Observed frequency changes:** the ±10 % frequency changes stayed small,
  approximately 0.06–0.21 % in magnitude.
- **s_E and s_G:** these columns come from CARBON-5A, not from CARBON-5F.

### Interpretation

1. SP13 is not substantially more core-stiffness-sensitive than SP02.
2. The tested scalar core stiffness uncertainty is far too weak to explain the ~6 %
   SP13 common frequency deficit.
3. FE7 is only moderately more core-sensitive than the fitted-mode mean, and it
   behaves similarly in SP02 and SP13.
4. SP13 FE8/FE9 ordering, shape type and mixing remain essentially unchanged.
5. The existing SP13 FE8/FE9 coupling conflict is therefore not explained by this
   scalar core-stiffness parameter.

### Order-of-magnitude diagnostic (extrapolation, NOT Abaqus-verified)

- **Compensating SP13's deficit:** compensating ln(c) ≈ 0.0606 with the local mean
  sensitivity would require k_core of roughly 77. This is a first-order
  (linear-in-ln k) illustration far outside the tested ±10 % interval. It is **not** an
  Abaqus-verified state.
- **k_core = 0.5 or 1.5:** any statement about these values is likewise a first-order
  extrapolation, not a directly solved state.

### Accepted conclusion and scope

The tested common scalar k_core is ruled out as a realistic cause of the SP13 common
~6 % deficit and of the FE7 deficit. Here k_core is the proportional scaling of all six
current explicit-core elastic stiffness constants.

CARBON-5F does **not** rule out:

- core model-form effects in general;
- core geometry / as-built footprint;
- anisotropic changes of individual core constants;
- interface/contact effects.

Possible remaining causes remain outside CARBON-5F scope:

- face-sheet properties/thickness;
- core geometry / as-built footprint;
- interface/contact;
- test/setup/model-form effects.

### q_G

- **q_G:** NOT YET PRODUCTION-VALID / DEFERRED TO M5.
- CARBON-5F provides the s_k column only.
- A production-valid q_G under SPEC v1.1 §10 requires the whitened full
  global + nuisance matrix, the observation covariance Σ and the prior rows (M5.1–M5.4).
- No q_G value is recorded here.

### k_core prior (D-006)

- CARBON-5F provides sensitivity only.
- It does **not** establish a numerical k_core prior.
- Independent core-tile evidence (ROADMAP M6.3) remains required.

### Archive location

- Local research scratch.
- ODBs and solver files are not in Git.


## M3 — Universal forward builder byte-for-byte regression

- **Status:** ACCEPTED (SUPERVISOR, M3 review; PR #29)
- **Kind:** software regression; **not** a material result. No Abaqus.
- **Purpose:** show that the manifest-driven builder (`src/services/forward_builder.py`)
  generates exactly the accepted shared-carbon forward INPs.
- **Inputs:**
  - reference INPs `SP02_Modal_V02.inp` `574ae78a…` and
    `SP13_mesh_local_v1_modal.inp` `9d410584…` (store `snadwich`);
  - forward-model manifests `docs/auto_id/forward_models/{SP02,SP13}.forward.json`;
  - archived job identities
    [forward_models/accepted_forward_jobs.json](forward_models/accepted_forward_jobs.json),
    from `carbon-project-archive:carbon4c/step1_prepare.json` and
    `carbon5a/prepare.json`, pinned by SHA-256.
- **Compact result:**
  - **Archived candidates:** CARBON-4C baseline and CARBON-5A E± / G± × SP02/SP13
    (10 jobs).
    - The bytes are identical to the live accepted builder.
    - The generated SHA-256 equals the archive. For example, SP02 baseline
      `f3e59228…` and SP13 baseline `a46d08b5…` are the names of the archived CARBON-4C
      ODBs.
    - Changed lines, the accepted provenance hashes and the evaluation hashes all
      reproduce.
  - **Extended matrix:** 24 / 24 further candidate files are identical.
- **Normative vs diagnostic:** normative for the M3 gate (forward-builder regression);
  not a material result.

## M4 — ODB shape-extraction gate and M4.2 complete-MAC baseline freeze

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-05)
- **Kind:** data preparation and observation freeze; **not** a material result.
- **Gate:**
  - HUMAN-authorised 2026-10-04; supervisor review of the extraction: PASS.
  - Abaqus 2024 Python on SHA-verified copies of 6 archived ODBs: SP02 and SP13
    CARBON-4C baselines, and SP13 CARBON-5A E± / G±.
  - Pinned `extract_odb.py` `039aa067…`.
  - The archived originals are unchanged.
- **Validation (all PASS):**
  - V1 ODB integrity;
  - V2 completeness;
  - V3 FE geometry identity;
  - V4 frequencies exactly equal to the archive;
  - V5 node set equal to the registration subset;
  - V6 MAC reproduction (direct, and the comparator read-only; max |ΔMAC| ≤ 6.7e-16);
  - V7 lossless float32;
  - V8 deterministic content hash.
- **Artifacts:** `carbon-project-archive:fe_shapes/<job>.npz` and
  `.provenance.json`, pinned by [fe_shapes/](fe_shapes/README.md).
- **M4.2 result** (strict pairing, complete MAC matrices):
  - **SP13 FROZEN** with 2 rows: exp 4 ↔ FE 10 (MAC 0.888) and exp 5 ↔ FE 11
    (MAC 0.889).
  - **SP02 NOT_FROZEN:** 1 strict pair < 2.
- **Normative vs diagnostic:** normative for M4.2 only after SUPERVISOR acceptance.

## M4.3 — Modal-family classifier on real SP13 FE shapes

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-05)
- **Kind:** diagnostic validation of the PROVISIONAL classifier policy
  `auto-id/modal-family/v1-provisional`, with thresholds unchanged.
- **Input:** validated shape pack `SP13_a46d08b52995e078` (content `7941545b…`).
- **Result:**
  - mirror coverage 100 %;
  - 24/24 modes classified, with parity and nodal-line counts consistent;
  - lowest odd-odd family: FE 7;
  - frozen rows: R1 (FE 10) odd-even, R2 (FE 11) even-odd;
  - holdout rule: no torsion holdout among the frozen rows; validation holdout R2.

  Record: [fe_shapes/SP13_a46d08b52995e078.families.json](fe_shapes/SP13_a46d08b52995e078.families.json).
- **Normative vs diagnostic:** diagnostic; thresholds stay PROVISIONAL until a separate
  decision.

## M4.4 — Cluster confirmation of SP13 R1/R2 on real FE shapes

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-05)
- **Kind:** observation-design diagnostic. **Not** a material result.
- **Input:** validated SP13 baseline and CARBON-5A ±5 % E/G12 shape packs; M4.2 rows
  R1/R2; M4.3 families.
- **Result:**
  - the 2.2 % trigger fired;
  - the decision is **INDEPENDENT**: individual FE-to-FE MAC is 0.999998 with unique
    counterparts in all four directions, and the cross-MAC is ≈ 0;
  - R1 and R2 remain two observations.

  Record: [fe_shapes/SP13.R1-R2.cluster.json](fe_shapes/SP13.R1-R2.cluster.json).
- **Normative vs diagnostic:** diagnostic; normative for the SP13 observation design
  only after SUPERVISOR acceptance.

## M4.6 — SP13 p0 smoke gate (real Abaqus through the M4.6 path)

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-05). Verdict REPRODUCED.
- **Kind:** software and solver reproducibility check. **Not** a material result.
- **Authorisation:** HUMAN gate. 1 Abaqus 2024 solve plus 1 pinned `extract_odb.py`
  extraction of `SP13_a46d08b52995e078` (p0); no LM loop, no M4.9.
- **Inputs:**
  - generated INP `a46d08b52995e078…` (the M3 rendering);
  - solver profile `SP13/abaqus-2024/v1` (`79aebbfe…`);
  - pinned extraction script `039aa067…`.
- **Result: REPRODUCED.**
  - **30/30** eigenfrequencies (EIGFREQ, modes 1–30) are exactly equal to the
    CARBON-4C archive.
  - The shape-pack content SHA `7941545b59390a65…` is identical to the validated
    baseline pack (minimum MAC 1.0).
  - The ODB differs only in run metadata (same size 715 614 536 bytes; SHA
    `56da620e…`).
  - Wall-clock 620 s; memory peak 18 GB.
- **Artifacts:** `D:\abaqus_m4_smoke` (journal, comparison, extraction manifest,
  logs; ODB kept until review). Archive proposal: provenance only, under
  `carbon-project-archive/m4_smoke/`, referencing the existing pack.
- **Normative vs diagnostic:** after acceptance, establishes that the M4.6 solve and
  extraction path reproduces the accepted CARBON-4C SP13 baseline.

## M4.9 — SP13 truth gate and observation readiness (synthetic twin)

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-05)
- **Kind:** software and pipeline readiness. **Not** a material identification result.
- **Authorisation:** HUMAN gate. 1 Abaqus 2024 truth solve (SP13, E 45000 / G12 4000
  MPa) plus 1 pinned `extract_odb.py` extraction. No LM, no identification solves.
- **Truth:**
  - job `SP13_bb3e5d7d131bed4f`;
  - generated INP `bb3e5d7d…`;
  - ODB `57282e50…` (715 614 536 bytes);
  - pack content `758add0c…`;
  - wall-clock 621 s.
- **Twin:**
  - definition `c200b293…` (seed 20261005, modes 7–30, σ = noise = 0.003);
  - synthetic experiment `5b0450d8…`.
- **Result: REFUSED_BEFORE_IDENTIFICATION.**
  - Strict freeze FROZEN, 23 rows; exp 24 / FE 30 excluded by the policy.
  - Trigger groups FE 13–15 and FE 20–23 are UNSUPPORTED (> 2 modes; SPEC §12.4).
  - The other five groups are INDEPENDENT; none is CONFIRMED.
  - The design is REFUSED under M4_DECISION_RECORD §8.2.
- **Records:**
  - `docs/auto_id/twins/SP13_truth_gate/`: readiness report, twin provenance, truth
    journal, truth pack record, extraction manifest;
  - `D:\abaqus_m4_truth`.

## M4.9 — SP13 observation readiness after A1 (zero-Abaqus re-run)

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-05)
- **Kind:** pipeline readiness. **Not** a material identification result.
- **Inputs:**
  - the journalled truth stage of the M4.9 truth gate (no new solve or extraction);
  - the twin definition `c200b293…` (seed 20261005);
  - the validated p0/±5 % packs;
  - D-032 (A1).
- **Result: READY_FOR_IDENTIFICATION.**
  - Strict freeze FROZEN, 23 rows; observation hash `05a5443a…`, unchanged.
  - FE 13–15 and FE 20–23 are INDEPENDENT (member MAC ≥ 0.9998, subspace cos² ≥ 0.9999).
    All seven trigger groups are INDEPENDENT.
  - Holdouts: R1 (torsion) and R23 (validation). 21 fit terms for 2 parameters; the M4.7
    design is valid.
- **Abaqus runs:** 0.
- **Records:** `docs/auto_id/twins/SP13_truth_gate/readiness_report_a1.json` and
  `twin_provenance_a1.json`.

## M4.9 — SP13 synthetic-twin identification loop (real Abaqus)

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-05)
- **Kind:** M4 software / pipeline acceptance on a synthetic digital twin.
  - **Not** a material identification of a real specimen.
  - **Not** an M5 identifiability result.
  - The bounds are development-only.
- **Authorisation:** HUMAN gate 2026-10-05 (M4_DECISION_RECORD §11.1).
- **Result: CONVERGED.**
  - Estimate: E_in_plane = 45005.45 MPa, G12 = 4012.20 MPa (truth 45000 / 4000).
  - |ln error| / local sd: E 0.000121 / 0.002064; G12 0.003046 / 0.009951. Both are within 1σ.
- **Effort:** 6 identification evaluations (5 reused archived, 1 new Abaqus solve, 1 pinned
  extraction); 2 iterations (Φ 5260.09 → 9.97).
- **Run quality:**
  - no refusal and no active bound;
  - minimum tracking MAC 0.9861;
  - holdout residuals at p̂: R1 +0.031, R23 −0.311 (whitened).
- **Determinism:** journal replay gives an identical result with 0 solves.
- **M3:** unchanged.
- **Records:**
  - run `3503c7d4…` in `D:\abaqus_m4_twin_loop`;
  - archive `m4_twin/SP13_identification_loop/` (manifest `11eb6493…`);
  - repository copies in `docs/auto_id/twins/SP13_identification_loop/`.
