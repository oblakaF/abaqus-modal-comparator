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
