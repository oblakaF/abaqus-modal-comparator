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

- **Status:** IN_PROGRESS
- **Scientific conclusion:** PENDING
- **Supervisor acceptance:** PENDING
- **Purpose:** shared PLA/core-stiffness sensitivity for SP02/SP13.
- **Compact result:** none recorded. S_core, q_G, [s_E, s_G, s_k] and the final
  conclusion are intentionally **not** pre-filled.
- **Scope limit (D-006):** CARBON-5F provides k_core **sensitivity** only. It does not
  establish a numerical k_core prior.
- This entry may change only through roadmap step P0.2, after a final report is
  SUPERVISOR-ACCEPTED.
