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

## M5 — Practical-identifiability and verdict machinery: synthetic stage gate and M4.9 twin records-based control

- **Status:** ACCEPTED (SUPERVISOR, 2026-10-06)
- **Kind:** software and scientific-pipeline evidence; synthetic stage-gate evidence.
  - **Not** a real-material identification result.
  - **Not** a real-specimen identifiability conclusion.
- **Scope:** the M5.1–M5.9 machinery:
  - typed global + nuisance sensitivity matrix in ln p, with explicit Σ;
  - explicit nuisance prior rows;
  - practical rank at rcond = 1e-3 as a hard block;
  - q_G (diagnostic);
  - `statistical_sd`, conditional Birge and linearised leave-one-family-out
    `model_form_robustness`;
  - the residual-pattern test;
  - the IDENTIFIED / WIDE / NOT_IDENTIFIABLE verdict engine.
- **Gate:** `tests/test_m5_stage_gate.py` (records and synthetic only; deterministic):
  - **positive synthetic control:** E and G12 IDENTIFIED;
  - **G12 absorbed by k_core:** q_G = 0.0145 (diagnostic only). G12 NOT_IDENTIFIABLE from the
    full uncertainty calculation (sd_ln 0.50 > 0.08); no q_G threshold is used;
  - **rank-deficient:** hard refusal. No covariance, Birge or robustness; no pseudo-inverse; no
    override;
  - **systematic residual pattern or holdout |r| > 3:** Birge not available and no green verdict;
    `statistical_sd` preserved;
  - **WIDE:** WIDE (conservative_ln 0.0632) only while every guard passes; any guard failure or
    the production context gives NOT_IDENTIFIABLE;
  - **missing physical evidence:** sandwich G12 NOT_IDENTIFIABLE (`BARE_PLATE_REQUIRED`,
    `NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED`);
  - **labels:** `statistical_sd`, `birge_adjusted_sd` and `model_form_robustness` stay separate;
    there is no merged field.
- **M4.9 twin, records-based synthetic positive control** (committed records only):
  - inputs: the Broyden-updated Jacobian from the journal; σ = 0.003 (the twin's synthetic
    definition);
  - E: `statistical_sd_ln` 0.002064, `birge_adjusted_sd_ln` 0.002115, model-form half-range
    0.001109 (ln);
  - G12: 0.009951 / 0.010195 / 0.005284;
  - pattern PASS; holdouts R1 +0.03 and R23 −0.31; q_G 0.761;
  - IDENTIFIED in the SYNTHETIC_GATE context only; NOT_IDENTIFIABLE in the PRODUCTION context.
- **Abaqus:** 0 solves and 0 Abaqus Python extractions in M5. M3 and M4 accepted contracts
  unchanged.
- **Qualifications (kept):**
  - real t_face / k_core columns and priors, a real Σ_meas, the S4 noise control and production
    family consistency are future real-data work;
  - sandwich G12 needs bare-plate and/or independent nuisance evidence;
  - M4.3 thresholds PROVISIONAL;
  - real SP13 refused; SP02 NOT_FROZEN.

## SP-13 physical registration from stored PSV records and strict-pairing re-evaluation (M6 gate)

- **Status:** RECORDED (SUPERVISOR-authorised zero-Abaqus gate, 2026-10-06), pending SUPERVISOR review.
- **Kind:** registration evidence (geometry only; no modal data) plus a zero-Abaqus re-evaluation on
  archived packs.

### Pinned sources

| Item | Identity |
|---|---|
| `.svd` (snadwich `SP-13/SP13_a_500by500_Glue420_Auxetic_newSP01_260910.svd`) | sha256 `41da4cc1d3a5daa038f558c571128793d44499f09605c7d79f0817b6744b0765` |
| UNV geometry (snadwich `SP-13/SP13_a_polymax.unv`) | sha256 `f268023583972f0a9c1660bc60631587e8f3330e4fb7495e52d8310906af39fe` |
| Streams | MeasPoints `6ec1a016…`, VideoBitmap `12171aec…`, VideoSettings `d9b7a797…`, DefaultSettings `b65755cb…` (full values in the record) |
| Reconstruction record | `registration_evidence/SP13_physical_registration_reconstruction.json`, sha256 `6b45fbfbacad0df939b0b12f8496edddff0525855e0de0312ff5f558c71bb0ae` |
| Physical passport | `specimens/SP13.physical.specimen.json`, manifest `943bb3d1946863c61abd39ccac8fa1da625067b9dffdcd6be2c82c3e125d5000` |
| Physical registration | `docs/registrations/SP13_physical_registration.json`, hash `2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823` |
| Re-evaluation record | `registration_evidence/SP13_registration_reevaluation.json`, sha256 `cda0393579b3498e4a993a22cc6608058fedd0d436fc1099722358e5a7300112` |

### Method

1. **Parser:** a read-only parser of the compound-file `.svd` (`services/psv_video_registration.py`).
   MeasPoints record k matches UNV node k through one plane homography (residual median 2.3e-4,
   max 8.0e-4 normalised units, about 0.25 px).
2. **Pixel normalisation:** taken from the stored default full-frame rectangle (u −0.2222…1.5556,
   v 0…1): x = 1080·u + 240, y = 1080·v. The scanner-angle alignment confirms isotropy (0.966).
3. **Panel edges** fitted in the stored frame (rms 0.18–0.25 px; frame scale about 0.57 mm/px).
   The pixel aspect agrees with the measured 510 × 520 mm to 0.30 %.
4. **Scan points** mapped into the panel frame (origin bottom-left, +y towards the labelled top).

### Physical transform

- **Scan window:** 366.51 × 496.23 mm.
- **Edge gaps:** left 72.15, right 71.33, bottom 9.81, top 13.96 mm.
- **Scan axes vs panel:** −0.26° / +89.51°.
- **UNV vs physical:** x × 1.195, y × 0.889 (anisotropic).
- **M2 model** (per-axis scale and translation) **vs reconstruction:** median 2.68 mm, max 5.72 mm.
- **Legacy centred placement vs physical:** median 26.0 mm, p95 39.4 mm, max 47.4 mm.

### Strict pairing (STRICT policy, MAC ≥ 0.8, |Δf| ≤ 15 %; unchanged data, packs and classifier)

| Registration | Strict pairs (exp ↔ FE, MAC, Δf) | Fit rows after M4.3 holdout |
|---|---|---|
| Legacy | 4 ↔ 10 (0.888, −9.1 %); 5 ↔ 11 (0.889, −9.1 %) | R1 only |
| Physical | 4 ↔ 10 (0.958, −9.1 %); 7 ↔ 13 (0.947, −2.8 %) | R1 only (R2 = validation holdout) |
| Physical, 180° alternative (reported only) | 4 ↔ 10 (0.959); 7 ↔ 13 (0.948) | R1 only |

**Two-row conditioning** (diagnostic; σ = 0.3 %; carbon-only):

| | Condition number | Angle between rows | sd(ln E) | sd(ln G12) |
|---|---|---|---|---|
| Legacy | 252 | 0.45° | 0.44 | 1.32 |
| Physical | 6.3 | 18.4° | 0.006 | 0.031 |

### Conclusion

- The physical registration removes the collinearity: the pair set changed and is well conditioned.
- Under the unchanged M4.3 holdout rule (highest accepted family held out), one fit row remains.
  **SP-13 alone is still observation-insufficient.**
- 0 Abaqus solves, 0 Abaqus Python extractions.

## SP-13 HUMAN evidence update (H7–H10) and SP-02 physical registration from stored PSV records (M6 gate)

- **Status:** RECORDED (SUPERVISOR-authorised zero-Abaqus gate, 2026-10-06), pending SUPERVISOR review.
  The HUMAN facts H7–H10 are recorded in D-064.
- **Kind:**
  - SP-13: uncertainty update only. The transform, registration and strict pairs are unchanged.
  - SP-02: registration evidence (geometry only; no modal data). Then a zero-Abaqus strict
    re-evaluation on the existing pack, and a combined diagnostic picture (no M7 fitting).

### SP-13: updated uncertainty state

| Item | Before (D-062) | Now |
|---|---|---|
| In-plane FE axis signs | four geometrically identical mappings; nominal by convention | **H7**: +x→+X, +y→+Y physically established; 180° alternative excluded (MAC not used) |
| Remaining symmetry | — | through-thickness face convention only: TOP seen from +Z vs BOTTOM seen from −Z (the in-plane mirror together with z → −z). The FE stack is through-thickness symmetric, so this is a mathematical symmetry of the model, bound to TOP by convention. Not evaluable on the TOP-only packs. |
| `translation_mm` | 5.72 | 5.72 (unchanged rule: maximum M2-model residual) |
| `rotation_deg` | 0.49 | 0.49 (unchanged rule: maximum axis misalignment) |
| `scale_rel` | NOT_AVAILABLE | **0.002**: H8 readout contribution only. The 1 mm ruler graduation over the shorter 510 mm side is 0.00196, rounded up. No calibration or operator term. |
| M2.4 status | PARTIAL | **EVALUATED** (no missing component) |
| `registration_limited` | NOT_AVAILABLE | **False**, both SPEC §11 triggers |
| Σ_setup | provisional 0.3 % | provisional 0.3 %, flagged (H9: no PolyMAX of 260909) |
| 260909 → 260910 | FREQUENCY_ONLY | FREQUENCY_ONLY (H10). No 260909 fitted modes exist, so no frequency-only estimate can be computed. |

- **Passport:** `SP13.physical.specimen.json` is now manifest
  `b857724a7e205cc794fc9a25fae7d1c351e3267855f775d9504fa66cce102731` (D-062 recorded `943bb3d1…`).
  - Only `uncertainty.scale_rel` and the orientation source text (H7) changed.
  - The registration hash is unchanged: `2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823`.
- **M2.4 diagnostic** (`registration_evidence/SP13_registration_uncertainty.json`):
  - Tool: `tools/registration_uncertainty_evaluation.py`, on the shape-pack surface. Eight
    deterministic ±σ perturbations.
  - MAC ranges: 4 ↔ 10 0.947–0.962 (nominal 0.958); 7 ↔ 13 0.921–0.948 (nominal 0.947). No pair
    crosses 0.8.
  - Pairing-change trigger: evaluated diagnostically with the unchanged STRICT freeze under every
    perturbation (the M2.4 service itself still reports `DEFERRED_M4`). The strict pair set is
    unchanged under all eight perturbations.
- The dial caliper (0.01 mm) does not enter `scale_rel`; it is the thickness-readout instrument.
- The audit document lists three 2026-09-09 PolyMAX frequencies (D-028). There is no pinned file
  for them, so they are not a fixture and are not used for Σ_setup.

### SP-02: Polytec anisotropy (verified before any MAC)

| Item | Identity / value |
|---|---|
| `.svd` (snadwich `SP-02/SP02_500by500_Glue420_honeycomb_full_scan_retry_260803.svd`) | sha256 `d974608c9dd4aa497edca69b760e917a2a746bcd99c2806f700bf9a4e1462425` |
| UNV geometry (snadwich `SP-02/SP02_polymax_retry_260803.unv`, the fixture source) | sha256 `2671db01b6401a9a9bbec7d8c2aa2191b0b35b5ae791756b91c7ccd381a41785` |
| Reconstruction record | `registration_evidence/SP02_physical_registration_reconstruction.json`, sha256 `b9234f573b6ab98acad4944ff4a2786ac16baab2e29d41c061d55aec5900707e` |
| Physical passport | `specimens/SP02.physical.specimen.json`, manifest `83739ecd2d0803bba682a3540c44e1437178164a731b48f1921e64b248168159` |
| Physical registration | `docs/registrations/SP02_physical_registration.json`, hash `9b63f6c891331ba55a6ee2797f142bf0b75117d9bffbf3ab312ee08a418e882c` |
| Re-evaluation record | `registration_evidence/SP02_registration_reevaluation.json`, sha256 `18ec73f0d96c84fb4a13610124470a3cfefc96dbae87df04361baaf430abf62d` |
| M2.4 record | `registration_evidence/SP02_registration_uncertainty.json`, sha256 `f05b8b7767703fe9877be64662ec8a58ab5324adff1b8689e9defb1852e3f1c5` |

- **Method:** the SP-13 method unchanged (D-062).
  - One parser fix: the video-alignment table is read from its stored point count (byte 40)
    instead of a 19-point marker. SP-02 stores 27 points.
  - With the fixed parser, the SP-13 record is rebuilt bit-identically.
- **Parser validation:** MeasPoints ↔ UNV homography residual median 1.2e-4, max 4.8e-4 normalised
  units. Scanner-angle isotropy 0.973.
- **Dimensions:** spec 515 × 510 × 2.9 mm.
  - Horizontal 510 / vertical 515 is fixed from the frame aspect: px-per-mm consistency 1.0013,
    against 0.9820 for the swapped order.
  - It equals the FE `SP02_Modal_V02` face extents (X 510, Y 515).
  - It was fixed before any pairing.
- **Panel edges:** rms bottom 0.24, left 0.43, right 0.20 px; top 3.70 px.
  - The top edge is bimodal: a bright halo just inside the panel triggers the first-step rule in
    some columns.
  - The frozen method was **not** changed. A worker-only silhouette diagnostic (first saturated
    background row; rms 0.50 px) moves the window height by 0.17 % and the scan points by median
    1.0 mm, max 3.0 mm.
  - Both are within the recorded uncertainty (`scale_rel` 0.002, `translation_mm` 5.93).

| Quantity | SP-02 | SP-13 (D-062) |
|---|---|---|
| Physical scan window | 368.72 × 499.24 mm | 366.51 × 496.23 mm |
| Legacy UNV window | 402.54 × 408.30 mm | — |
| UNV / physical, x and y | 1.0917, 0.8178 | 1.195, 0.889 |
| Anisotropy x / y | 1.335 | 1.345 |
| Edge offsets (left, right, bottom, top) | 80.72, 60.56, 9.66, 6.09 mm | 72.15, 71.33, 9.81, 13.96 mm |
| Scan axes vs panel | +0.68° / +90.68° | −0.26° / +89.51° |
| Affine residual (UNV → physical) | median 0.26, max 1.12 mm | — |
| M2 model vs reconstruction | median 2.83, max 5.93 mm | median 2.68, max 5.72 mm |
| Legacy centred vs physical (reconstruction) | median 30.6, p95 50.0, max 54.6 mm | median 26.0, max 47.4 mm |
| Legacy registration vs physical registration (FE frame) | median 28.9, p95 48.6, max 54.1 mm; 0 of 121 mapped nodes in common | — |

- **Conclusion (geometry only):** SP-02 has the same anisotropic UNV / video-coordinate distortion as
  SP-13. The legacy SP-02 registration is geometrically wrong. It is kept as historical provenance
  only (registration and passport unchanged).
- **Frozen transform:**
  - `scan_to_panel_edges` + `camera_grid`; physical width 368.7217, height 499.2446 mm;
    panel_edges x 80.7213, y 9.6608 mm.
  - Uncertainty (same rules as SP-13): translation 5.93 mm, rotation 0.68°, `scale_rel` 0.002
    (H8 readout).
  - Mapping rms 1.22 mm, max 1.94 mm; 121 unique nodes.
  - The four sign alternatives are geometrically identical (rms 1.2176 mm).
  - There is no SP-02 counterpart of H7. The nominal +x→+X, +y→+Y continues the accepted SP-02
    convention and was fixed before evaluation.
  - Production readiness: one issue only, `physical_specimen_id is not recorded`.

### SP-02 identity audit (provenance only)

- **File names and records:**
  - Store folder `SP-02`; run `SP02_500by500_Glue420_honeycomb_full_scan_retry_260803`.
  - PSV acquisition 03-Aug-26 13:40:35.
  - The PolyMAX set `Bravo (1)` was processed in the Testlab project
    `SP02_500by500_Glue420_honeycomb_full_scan_260715`, an SP-02 project from a 2026-07-15 scan
    that is not in the store.
  - FE `SP02_Modal_V01/V02` dated 2026-07-25, before the test.
  - Fixture `physical_specimen_id` null.
- **Spec chronology:**
  - SP-02 "copy of SP-10": 515 × 510 × 2.9 mm, faces 0.45, 582.71 g.
  - SP-10 "copy of SP-02": 520 × 515 × 2.8 mm, faces 0.40/0.39, 555.23 g.
  - These are two physically different panels.
- **Stored frames:**
  - The 260803 panel label reads "500x500 / Plain fiber / honey comb / DP420", with **no specimen
    number**.
  - The SP-10 frame (260831) shows a panel labelled "SP_10 / 500x500 / Plain fiber / Honey comb /
    DP420", in a different room and installation.
  - A yellow note "Modal" with an unreadable circled mark is on the frame, not on the panel.
- **Frequencies (records only, not used for any registration):**
  - SP-10 260911 PolyMAX: 29.29 / 76.82 / 79.73 / 92.87 / 95.27 / 146.01 Hz.
  - 260803 set: 28.01 / 74.38 / 78.16 / 90.57 / 91.95 / 144.76 Hz.
  - Offsets +0.9 … +4.6 %, consistent with a different panel.
- **Not excluded by the label alone:** SP-09 (new T300 plain, PLA honeycomb, DP420) carries the
  same label text.
- **Verdict: NEEDS_ONE_HUMAN_CONFIRMATION.** Is the unnumbered panel in the 2026-08-03 frame the
  physical SP-02 of `SP-02/spec.txt` (515 × 510 × 2.9 mm, 582.71 g)?
  - The geometric reconstruction is not blocked.
  - The answer does not change the registration hash (`physical_specimen_id` is not hashed).

### SP-02 strict pairing (STRICT policy unchanged; MAC ≥ 0.8, |Δf| ≤ 15 %; pack `SP02_f3e592281bebce66`)

| Registration | Status | Strict pairs (exp ↔ FE: MAC, Δf) | Holdouts (M4.3, unchanged) | Fit rows |
|---|---|---|---|---|
| Legacy | NOT_FROZEN (1 < 2) | 2 ↔ 8: 0.958, +1.2 % | — | — |
| Physical | FROZEN | 2 ↔ 8: 0.918, +1.2 %; 4 ↔ 10: 0.951, −1.4 %; 7 ↔ 13: 0.975, +2.7 % | validation R3 (family `Px:E\|Py:O\|nx:0\|ny:3`); no torsion family | R1, R2 |
| Physical, 180° (reported only) | FROZEN | 2 ↔ 8: 0.917; 4 ↔ 10: 0.950; 7 ↔ 13: 0.977 | R3 | R1, R2 |

- **Best match per mode (physical):** MAC 0.897, 0.918, 0.622, 0.951, 0.635, 0.614, 0.975, 0.527,
  0.244 for modes 1–9.
  - Mode 1: no FE mode inside the frequency gate (−15.8 %).
  - Modes 3, 5, 6, 8, 9: MAC < 0.8.
  - All values are in the record.
- **M2.4 (SP-02):** EVALUATED.
  - MAC ranges 0.913–0.921, 0.943–0.957, 0.960–0.976.
  - No crossing; the strict pair set is unchanged under all eight perturbations.
  - `registration_limited` False.
- **Cluster:** no M4.4 trigger among the rows.
  - FE 10 lies 1.4 % from FE 11.
  - The CARBON-5A FE-to-FE tracking keeps both branches with MAC ≥ 0.999999 in all ±5 % E / G12
    states, so the M4.4 confirmation condition (unstable branch identity) is not met.
- **Sensitivities:** SP-02 has no ±5 % shape packs, so the accepted CARBON-5A frequency and
  branch-tracking tables are used.
  - Only branches resolved in all four states are used.
  - The values equal the archived CARBON-5A `sensitivity.csv`.
  - R1 (FE 8): S_E 0.493, S_G12 0.0002. R2 (FE 10): 0.362, 0.127. R3 (FE 13): 0.484, 0.0005.
- **SP-02 alone, fit rows R1 and R2** (diagnostic; σ = 0.3 %; carbon-only): rank 2, condition
  number 6.08, row angle 19.3°, sd(ln E) 0.006, sd(ln G12) 0.029.

### Combined SP-02 + SP-13 picture (diagnostic stacking; not an M4/M5 contract; no M7 fit)

| Specimen | Row | exp ↔ FE | MAC | Family | Held out (per specimen, unchanged rule) | S_E | S_G12 |
|---|---|---|---|---|---|---|---|
| SP-13 | R1 | 4 ↔ 10 | 0.958 | `Px:O\|Py:E\|nx:1\|ny:2` | no | 0.365 | 0.123 |
| SP-13 | R2 | 7 ↔ 13 | 0.947 | `Px:E\|Py:O\|nx:0\|ny:3` | yes (validation) | 0.483 | 0.002 |
| SP-02 | R1 | 2 ↔ 8 | 0.918 | `Px:E\|Py:E\|nx:0\|ny:2` | no | 0.493 | 0.0002 |
| SP-02 | R2 | 4 ↔ 10 | 0.951 | `Px:O\|Py:E\|nx:1\|ny:2` | no | 0.362 | 0.127 |
| SP-02 | R3 | 7 ↔ 13 | 0.975 | `Px:E\|Py:O\|nx:0\|ny:3` | yes (validation) | 0.484 | 0.0005 |

- **Counts:**
  - 5 strict rows before holdout: 2 specimens; 3 family types (5 specimen-families).
  - 3 fit rows after the per-specimen holdout: 2 family types; 3 specimen-families.
- **Conditioning** (σ = 0.3 %, carbon-only):

  | Row set | Rank | Condition number | Max row angle | sd(ln E) | sd(ln G12) |
  |---|---|---|---|---|---|
  | All 5 strict rows | 2 | 6.6 | 19.3° | 0.0036 | 0.020 |
  | 3 fit rows | 2 | 6.0 | 19.3° | 0.0061 | 0.025 |

  With G12 fixed, sd(ln E) is 0.0042 on the 3 fit rows.
- **Leave-one-family-out on the 3 fit rows:**
  - Without the (0,2) family: the two (1,2) rows remain, 0.62° apart, condition number 184. G12
    is not robust.
  - Without the (1,2) family (pooled over specimens): one row remains, rank 1, sd(ln E | G12
    fixed) 0.006.
  - By specimen-family: every case keeps rank 2 (condition number ≤ 184).
  - E_in alone is supported in every leave-one-family-out case; G12 depends on the (1,2) family.
- 0 Abaqus solves, 0 Abaqus Python extractions.

## Specimen catalog: records-only audit of every real specimen (M6 documentation checkpoint)

- **Status:** RECORDED (SUPERVISOR-authorised documentation/governance checkpoint, 2026-10-06), pending
  SUPERVISOR review.
- **Kind:** provenance audit. No modal fitting, no MAC, no registration change, no Abaqus.
- **Records:**
  - `SPECIMEN_CATALOG.md` (canonical text);
  - `specimen_catalog.json` (sources, sizes and SHA-256 per reference; verified by
    `tests/test_specimen_catalog.py` for every configured store).
- **New evidence beyond the store-only audit:**
  - **SP-02 identity: SP02_IDENTITY_RESOLVED_FROM_RECORDS (DERIVED).**
    - `I:\Sumin\Updated_260911\Experiment_Freq_damping_LMS.xlsx`, sheet "SPname_files 260909", labels its
      columns "SP2 (old)" and "SP10 (new SP2)".
    - "SP2 (old)" is exactly the governed set Bravo (1) of the 260803 acquisition.
    - The SP-10-labelled panel is self-consistent across 260831 and 260911 (first six modes within
      1.5 %) and is 1.3–6.1 % higher than the 260803 panel.
    - Every frame up to 2026-08-03 is unnumbered, and every frame from 2026-08-22 on is numbered.
    - Recording `physical_specimen_id` in the SP-02 passport needs SUPERVISOR acceptance.
  - **SP-13 260909 PolyMAX exists:** `SP13_polymax.unv` in `I:\Sumin\SPname_files_260909_polymax.zip`
    (Testlab project `SP13_…_260909`, set Bravo (1), 9 modes; the D-028 audit frequencies 206.15 /
    212.61 / 228.75 Hz come from it).
    - This conflicts with HUMAN H9.
    - It is not used, and Σ_setup stays provisional 0.3 %, flagged (catalog C1, question Q1).
  - **Outside `D:\Snadwich`:**
    - SP-06 acquisition (260824) and SP-15 acquisition (260901);
    - ungoverned PolyMAX exports for SP-01, SP-03 … SP-10 (260831), SP-11 (session a), SP-13 (260909)
      and SP-15;
    - `C:\temp\SP-01.inp/.odb` (its eigenfrequencies equal the SP-01 spec Abaqus column).
  - **PLA grade (second-hand):** SP-01 PLA Light; SP-02/SP-13 non-Light (CARBON-5D note citing
    CARBON-3A).
  - **No measured material constants exist for any specimen.** The twill report is an FE sensitivity
    study; the June calibration report gives model-calibration values.
- 0 Abaqus solves, 0 Abaqus Python extractions.

## D-065 governed updates: SP-02 active binding and the frozen SP-13 260909 PolyMAX set (zero Abaqus)

- **Status:** RECORDED (SUPERVISOR-authorised, 2026-10-07; D-065), pending SUPERVISOR review.
- **SP-02 active binding:**
  - New fixture `SP02/bravo-1-physical` in `fixtures/real_experiment_fixtures.json`. It has the same
    experimental source, modal set and FE as `SP02/bravo-1`, with registration
    `SP02_physical_registration.json` (`9b63f6c8…`) and `physical_specimen_id` "SP-02".
  - `SP02.physical.specimen.json`: `physical_specimen_id` "SP-02"; `acquisition.fixture_id`
    `SP02/bravo-1-physical`. The registration rebuilt from it has the same hash and no
    production-readiness issue.
  - `load_production_modal_input("SP02/bravo-1-physical")` returns the 9-mode set with the physical
    registration.
  - **Historical chain unchanged:** `SP02/bravo-1` (legacy registration `9bf736d3…`), the legacy
    passport, `SP02.forward.json` and the archived CARBON-4C baseline. Its M0–M4 bindings
    (`test_baseline_freeze`, `bind_forward_model`) still hold. Rebinding them in place would rewrite frozen
    M4.2 evidence, which was not authorised.
  - **Anti-tuning:**
    - `registration_evidence/SP02_registration_uncertainty.json` was regenerated with the same tool and
      inputs. Only `passport_sha256_lf` changed; every M2.4 value is identical.
    - The registration and reconstruction records are unchanged.
- **SP-13 260909 provenance audit** (read-only, before any use): **SP13_260909_POLYMAX_PROVENANCE_CONFIRMED**.
  - **Source:** archive `I:\Sumin\SPname_files_260909_polymax.zip` (sha256 `c7f91f6f84cdb011e2c6ea18b733bd49ae0f62d4b1e251c38c6dab4bb3e1c336`), member
    `SP13_polymax.unv` (sha256 `c036cdf36230c8deab413a5a2b4da8147cea68248c7d82ec3b0297c6705308c9`).
  - **Contents:** datasets 55 (50 records), 82 (12) and 2411 (121 nodes). No dataset 151 (normal for a
    Testlab export).
  - **Embedded metadata:** Testlab project `SP13_500by500_Glue420_Auxetic_newSP01_260909`; export time
    10-09-2026 12:10:58. That is after the 260909 acquisition (09-Sep-26 09:00:10) and before the 260910a
    acquisition (10-Sep-26 17:38:17).
  - **Geometry:** identical to the raw 260909 acquisition (same 121 ids; coordinates within 1e-16 m).
    Every other 121-point acquisition differs by 3–430 mm, so each grid is unique.
  - **Shapes:** each fitted shape reproduces the raw 260909 H1 at its frequency on the same grid. MAC is
    0.95–0.99 for 8 of 9 modes. Calibration: the governed SP-02 fit against its own raw data gives
    0.95–1.00.
  - Mode 7 (206.15 Hz, MAC 0.38) is barely excited: mean |H1| 0.18 against 2.2 at 212.5 Hz (SPEC §15).
  - **Band:** the fitted band 21.25–244.30 Hz lies inside the raw 0.3125–500 Hz (Δf 0.3125 Hz).
  - **Other records:** the LMS summary column "SP13 (new SP1)", AUDIT §4.2 and D-028.
  - **Relation to `SP13/best`:** a different grid (289 points), a re-suspension (H6, D-063). There is no
    cross-grid shape or MAC claim, and the mode correspondence is NOT_ESTABLISHED.
  - **Frequency agreement** was used only as supporting evidence, after provenance.
- **Frozen record:** `fixtures/SP13_260909.frozen-modal-set.json`.
  - Fixture `SP13/260909-bravo-1`, schema `auto-id/frozen-external-modal-set/v1`, FREQUENCY_ONLY.
  - Registration NOT_AVAILABLE and FE NOT_APPLICABLE, both stated.
  - Frozen modes are read with the production reader: 31.64, 74.14, 80.82, 94.43, 96.55, 147.86, 206.15, 212.61, 228.75 Hz.
  - It sits outside the M0.2 fixture manifest because that schema requires a FrozenRegistration and an FE
    model, which the 121-point grid does not have and frequency-only use does not need.
- **Σ_setup:** provisional 0.3 %, flagged, as decided (D-065).
  - SPEC §7 permits a frequency-only estimate from this re-suspension.
  - The estimator is a later decision (D-053, D-058), and no governed cross-grid mode-correspondence rule
    exists. The LMS mode labels of the two sessions also disagree.
- 0 Abaqus solves, 0 Abaqus Python extractions.

## M6.4a: transverse-constant screening path and the HUMAN Abaqus manifest (zero Abaqus; no result yet)

- **Status:** REVIEW_READY (worker, 2026-10-07; D-066). No screening result exists yet.
- **Envelope record:** `screening/M6_4_transverse_envelope.json`, envelope hash `d29e848566afaadc1a73234d531f83383810e7ec2f7ac0471c0965aa6fd2036d`. Basis
  `LITERATURE_INTERIM_SCREENING_ENVELOPE`. Reference candidate E_in 52 000, G12 4 500 MPa.
- **FE model check** (read-only, the INPs in the `snadwich` store):
  - `SP02_Modal_V02.inp` faces: `C3D8I`, `*Solid Section` with `Ori-1` (axes 1 and 2 = global X and Y;
    axis 3 = Z).
  - `SP13_mesh_local_v1_modal.inp` faces: `C3D8I`, `Ori-2` (same axes).
  - All nine engineering constants therefore enter the face stiffness.
- **Plan** (rendered without Abaqus):
  - The reference candidate regenerates the archived baseline jobs byte-identically:
    `SP02_f3e592281bebce66` and `SP13_a46d08b52995e078`. Their packs are reused.
  - Changed lines per job equal the M3.5 anchors:
    - SP02: 2077230 and 2077231 (record), 2077244 (15 → 30 eigenvalues, as in the baseline);
    - SP13: 1957765 and 1957766.
  - Every job differs from its baseline in exactly one constant. The other values keep their source text.
- **HUMAN Abaqus manifest:** schema `auto-id/transverse-screening-manifest/v1`, hash `6d34179c787c8b0e1619864709290f2824e0435b98fb1ff2689e61d892da3922`.
  16 solves, 16 extractions, 0 baseline solves.

| Specimen | Perturbation | Value | Job | Generated INP SHA-256 |
|---|---|---|---|---|
| SP02 | E3-low | 5000 | `SP02_7ecb36decc403fda` | `7ecb36decc403fda…` |
| SP02 | E3-high | 10000 | `SP02_f3eed68a26571fba` | `f3eed68a26571fba…` |
| SP02 | nu13-low | 0.2 | `SP02_4ef95a55171cc3d8` | `4ef95a55171cc3d8…` |
| SP02 | nu13-high | 0.4 | `SP02_fe01394cc4ef1535` | `fe01394cc4ef1535…` |
| SP02 | nu23-low | 0.2 | `SP02_6bf74401677e7e75` | `6bf74401677e7e75…` |
| SP02 | nu23-high | 0.4 | `SP02_47b309d68e48a957` | `47b309d68e48a957…` |
| SP02 | G13-high | 5000 | `SP02_5732bef18649d4bb` | `5732bef18649d4bb…` |
| SP02 | G23-high | 5000 | `SP02_c93b3e3cb8ae511e` | `c93b3e3cb8ae511e…` |
| SP13 | E3-low | 5000 | `SP13_81a5cedfe42b38d3` | `81a5cedfe42b38d3…` |
| SP13 | E3-high | 10000 | `SP13_3fc1cad51076cfd2` | `3fc1cad51076cfd2…` |
| SP13 | nu13-low | 0.2 | `SP13_7ac63eb2905930ec` | `7ac63eb2905930ec…` |
| SP13 | nu13-high | 0.4 | `SP13_9771af6aa8d4373c` | `9771af6aa8d4373c…` |
| SP13 | nu23-low | 0.2 | `SP13_eb9383c49c9e1f2d` | `eb9383c49c9e1f2d…` |
| SP13 | nu23-high | 0.4 | `SP13_8f84df93ab40549c` | `8f84df93ab40549c…` |
| SP13 | G13-high | 5000 | `SP13_b0af3095b6111c09` | `b0af3095b6111c09…` |
| SP13 | G23-high | 5000 | `SP13_0fcc8454363f3fa4` | `0fcc8454363f3fa4…` |

- **Solver profiles** (both unchanged):
  - `SP02/abaqus-2024/v1`: 8 cpus, `abaqus-scratch` store;
  - `SP13/abaqus-2024/v1`: 1 cpu.
- **Extraction:** pinned `abaqus_scripts/extract_odb.py` (`039aa067…`), modes 7–30. The expectation is the
  baseline pack's TOP node set (SP02 29 583 nodes, SP13 29 754).
- **Tests:** `tests/test_m6_4_transverse_screening.py`. They cover:
  - the envelope and the builder guard;
  - a synthetic plan → gated run → evaluation with fake executors;
  - the strict criterion, holdout rows and both endpoints;
  - tracking refusal and frequency-order change;
  - the architecture guards and the pinned real manifest.
- **Mutation check:** 6 of 6 targeted mutants killed.
- **Test results:** Windows with the snadwich and carbon-project-archive stores 1511 OK (5 skipped: 3 need the sumin store and pass with it, 24 OK; 2 are Abaqus-gated); without data stores 1502 OK (48 skipped); test_m6_4_transverse_screening 28 OK (24 OK, 1 class skipped without stores)
- 0 Abaqus solves, 0 Abaqus Python extractions.

## M6.4b: transverse-constant screening result (HUMAN Abaqus gate, manifest 6d34179c…)

- **Status:** REVIEW_READY (worker, 2026-10-08; D-066, D-067). Pending SUPERVISOR review.
- **Authorisation:** HUMAN Abaqus gate for manifest `6d34179c787c8b0e1619864709290f2824e0435b98fb1ff2689e61d892da3922` (D-067).
- **Pre-run verification:**
  - `plan` from the frozen tree `403ff94` gave exactly this hash.
  - The job list equals the 16 authorised jobs.
  - Each generated INP was re-read. It differs from the reference constants only in the authorised constant
    at its authorised value.
  - The extractor `abaqus_scripts/extract_odb.py` has SHA-256 `039aa067…`, unchanged.
- **Execution:** `tools/m6_4_transverse_screening.py run` with the governed profiles `SP02/abaqus-2024/v1`
  (8 cpus) and `SP13/abaqus-2024/v1` (1 cpu), Abaqus 2024.
  - 16 successful solves and 16 successful, validated extractions.
  - 0 failures, 0 retries, 0 baseline solves.
  - Solve wall-clock: SP02 809–2169 s, SP13 581–718 s. The first SP02 solves ran slower because the
    machine was loaded by other work; this changed the timing only.
- **Run evidence:** `screening/M6_4_run_evidence.json` pins every job by content: generated INP, solve hash,
  ODB SHA-256 and size, Abaqus version line, extraction ID, pack file and content hashes, and node set.
  - Journal run hash `6def52361ef8ebed…`, 32 entries.
  - The run-store data (ODBs, packs, journal) is not committed.
- **Result record:** `screening/M6_4_transverse_screening_result.json`, the unchanged output of `evaluate`,
  result hash `0fb87ea753217e15ca0f182aff960f94d022020d32151edaebdbfb62e2f1cd9b`.
  - The result reproduces exactly from the journalled run packs through the frozen tool path (test
    `test_m6_4_screening_result`, store-gated).
- **Branch tracking:** every frozen row of every state was tracked by FE-to-FE MAC with a unique match
  (minimum MAC 0.999999). Every row stayed on its baseline mode number, with no frequency-order
  change. No refusal occurred.

| Parameter | Max effect SP02 | Max effect SP13 | Global max | Classification |
|---|---|---|---|---|
| E3 | 0.0003 % | 0.0005 % | 0.0005 % | `NEGLIGIBLE_FOR_BUDGET` |
| ν13 | 0.0001 % | 0.0001 % | 0.0001 % | `NEGLIGIBLE_FOR_BUDGET` |
| ν23 | 0.0007 % | 0.0007 % | 0.0007 % | `NEGLIGIBLE_FOR_BUDGET` |
| G13 | 0.0125 % | 0.0138 % | 0.0138 % | `NEGLIGIBLE_FOR_BUDGET` |
| G23 | 0.0271 % | 0.0353 % | 0.0353 % | `NEGLIGIBLE_FOR_BUDGET` |

Per row, signed Δf/f = (f_perturbed − f_baseline) / f_baseline at the CARBON-4C reference point:

| Endpoint | Specimen | Row | Tracked mode | f (Hz) | Δf/f | Tracking MAC |
|---|---|---|---|---|---|---|
| E3 low (5000) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.241 | -0.0001 % | 1.000000 |
| E3 low (5000) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.327 | -0.0001 % | 1.000000 |
| E3 low (5000) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.427 | -0.0002 % | 1.000000 |
| E3 high (10000) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.241 | +0.0001 % | 1.000000 |
| E3 high (10000) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.327 | +0.0002 % | 1.000000 |
| E3 high (10000) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.428 | +0.0003 % | 1.000000 |
| E3 low (5000) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.851 | -0.0002 % | 1.000000 |
| E3 low (5000) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 199.976 | -0.0004 % | 1.000000 |
| E3 high (10000) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.852 | +0.0002 % | 1.000000 |
| E3 high (10000) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 199.978 | +0.0005 % | 1.000000 |
| ν13 low (0.2) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.241 | -0.0001 % | 1.000000 |
| ν13 low (0.2) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.327 | -0.0001 % | 1.000000 |
| ν13 low (0.2) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.427 | -0.0000 % | 1.000000 |
| ν13 high (0.4) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.241 | +0.0001 % | 1.000000 |
| ν13 high (0.4) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.327 | +0.0001 % | 1.000000 |
| ν13 high (0.4) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.427 | +0.0000 % | 1.000000 |
| ν13 low (0.2) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.851 | -0.0001 % | 1.000000 |
| ν13 low (0.2) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 199.977 | -0.0001 % | 1.000000 |
| ν13 high (0.4) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.852 | +0.0001 % | 1.000000 |
| ν13 high (0.4) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 199.977 | +0.0001 % | 1.000000 |
| ν23 low (0.2) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.241 | -0.0001 % | 1.000000 |
| ν23 low (0.2) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.327 | -0.0002 % | 1.000000 |
| ν23 low (0.2) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.426 | -0.0007 % | 1.000000 |
| ν23 high (0.4) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.241 | +0.0002 % | 1.000000 |
| ν23 high (0.4) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.327 | +0.0002 % | 1.000000 |
| ν23 high (0.4) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.429 | +0.0007 % | 1.000000 |
| ν23 low (0.2) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.851 | -0.0002 % | 1.000000 |
| ν23 low (0.2) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 199.976 | -0.0006 % | 1.000000 |
| ν23 high (0.4) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.852 | +0.0002 % | 1.000000 |
| ν23 high (0.4) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 199.979 | +0.0007 % | 1.000000 |
| G13 high (5000) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.245 | +0.0056 % | 0.999999 |
| G13 high (5000) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.338 | +0.0125 % | 1.000000 |
| G13 high (5000) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.452 | +0.0117 % | 1.000000 |
| G13 high (5000) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.861 | +0.0107 % | 1.000000 |
| G13 high (5000) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 200.005 | +0.0138 % | 1.000000 |
| G23 high (5000) | SP02 | R1 (fit) | FE 8 → 8 | 75.241 → 75.246 | +0.0067 % | 1.000000 |
| G23 high (5000) | SP02 | R2 (fit) | FE 10 → 10 | 89.327 → 89.337 | +0.0115 % | 1.000000 |
| G23 high (5000) | SP02 | R3 (holdout) | FE 13 → 13 | 207.427 → 207.483 | +0.0271 % | 1.000000 |
| G23 high (5000) | SP13 | R1 (fit) | FE 10 → 10 | 85.851 → 85.863 | +0.0136 % | 1.000000 |
| G23 high (5000) | SP13 | R2 (holdout) | FE 13 → 13 | 199.977 → 200.048 | +0.0353 % | 1.000000 |

- **Reading:**
  - E3, ν13 and ν23 move the observed frequencies by less than 0.001 %.
  - G13 and G23 (2200 → 5000 MPa) raise them by at most 0.035 %, about 8.5× below the criterion.
  - All five constants are `NEGLIGIBLE_FOR_BUDGET`. None enters the uncertainty budget, and they stay fixed
    (SPEC §5.2).
  - This screening says nothing about the practical 5–10 % real-data agreement target (D-066).
- **Informational all-mode diagnostic** (never used for classification):
  - the largest change over all extracted modes is about 0.12 % (G23-high, SP13);
  - single-mode tracking could not follow SP02 G13-high: modes [29, 30]; SP02 G23-high: modes [29, 30]. These are near-degenerate high modes that are not
    observation rows.
- **Limitation:** the classification is local to the CARBON-4C reference point (E_in 52 000, G12 4 500 MPa).
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run) 1516 OK (2 Abaqus-gated skipped); without data stores 1507 OK (49 skipped); targeted M6.4 + M6 + M5 gate + M4 guard/gate + M3 gate 152 OK; result reproduction from the run store OK
- 16 Abaqus solves and 16 Abaqus Python extractions, all under the D-067 HUMAN gate.

## D-068 M7-entry wiring: active SP-02 / SP-13 inputs on the physical registrations (zero Abaqus)

- **Status:** REVIEW_READY (worker, 2026-10-08; D-068).
- **Active chains:**

| Specimen | Physical passport | Fixture | Registration | Forward manifest |
|---|---|---|---|---|
| SP-02 | `SP02.physical.specimen.json` `bddc5437…` (unchanged) | `SP02/bravo-1-physical` (D-065) | `9b63f6c8…` | `SP02.physical.forward.json` `f53226a0…` (new) |
| SP-13 | `SP13.physical.specimen.json` `8366c163…` (`fixture_id` changed) | `SP13/best-physical` (new) | `2eeeaa86…` | `SP13.physical.forward.json` `ec6f5ee2…` (new) |

- **New fixture `SP13/best-physical`:**
  - the experimental source, modal set (`best`, 12 modes, 289 points) and FE identity are those of `SP13/best`;
  - `physical_specimen_id` "SP-13";
  - `test_run_id` stays unresolved, as in `SP13/best`; no key is invented.
- **New forward manifests:**
  - The forward model ID, model input, material, parameterisation, eigenvalue request and job prefix equal the
    legacy manifests, so the governed solver profiles apply unchanged.
  - Only the passport and the registration differ.
  - At the CARBON-4C point both render the archived baseline jobs `SP02_f3e592281bebce66` and
    `SP13_a46d08b52995e078` byte-identically, so the validated baseline packs stay reusable.
- **Active production input:**
  - `load_production_modal_input("SP02/bravo-1-physical")`: 9 modes, `9b63f6c8…`;
  - `load_production_modal_input("SP13/best-physical")`: 12 modes, `2eeeaa86…`.
  - Both physical registrations rebuild from their passports to the same hash, with no readiness issue.
- **Anti-tuning:** `registration_evidence/SP13_registration_uncertainty.json` was regenerated with the same tool
  and inputs. Only `passport_sha256_lf` changed; every M2.4 value is identical.
- **Unchanged (content hashes compared before and after; 54 records, 0 changed):**
  - the legacy fixtures `SP02/bravo-1` and `SP13/best`, and `SP02/bravo-1-physical`;
  - the legacy passports and the SP-02 physical passport;
  - `SP02.forward.json` (`bc3d9b86…`), `SP13.forward.json` (`f5407900…`), `accepted_forward_jobs.json`;
  - every registration, baseline, FE shape-pack record, twin and solver profile;
  - the SP-02 M2.4 record, the reconstruction and re-evaluation records;
  - the frozen SP-13 260909 set, and the M6.4 envelope, result and run evidence.
  - The archived baselines still reference the legacy forward manifests and registrations.
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run) 1522 OK (2 Abaqus-gated skipped); without data stores 1513 OK (56 skipped); wiring + fixture + registration + catalog + forward + M3/M4/M5 gate + M6.4 tests included
- 0 Abaqus solves, 0 Abaqus Python extractions, no identification run.
