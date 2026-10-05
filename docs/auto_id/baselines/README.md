# Archived baseline records (M4.2)

Schema `auto-id/archived-baseline/v1`. The parser is `src/services/archived_baseline.py`.

By SUPERVISOR decision, the archived CARBON-4C baseline solves (52000 / 4500 MPa) are
the M4.2 reference observation source. No new baseline Abaqus solve is made, and no
Abaqus Python is run on the archived ODBs.

Each record holds content identities only (no machine paths):

| Field | Source |
|---|---|
| `forward_model`, `job` | M3 forward-model manifest hash; baseline job name and generated INP SHA-256 (the M3 regression anchor) |
| `odb` | Archived ODB, pinned by SHA-256 in `carbon-project-archive` (equals the M0.2 fixture `odb_reference`) |
| `source_record` | Archived `carbon4c/post_solve_SP0x.json`, pinned by SHA-256 |
| `fe_geometry_sha256`, `registration_hash` | FE geometry identity and FrozenRegistration of the solve |
| `experimental` | Fixture, source SHA-256, modal set, measured DOFs, and the M1 production mode frequencies |
| `fe_modes` | Elastic FE modes 7–30 and their frequencies |
| `mac_entries` | The MAC values the CARBON-4C post-solve recorded: each accepted-comparator pair, and the best-MAC candidate of each rejected experimental mode |

## Limitation (recorded, not guessed)

The FE mode shapes are not archived, so the full experimental × FE MAC matrix is not
available. MAC entries that were not recorded are **unknown**. The strict freeze
(`IdentificationPairingPolicy`, MAC ≥ 0.80, |Δf| ≤ 15 %) therefore returns
`NOT_FROZEN` with reason `INCOMPLETE_EVIDENCE` for both specimens.

| Specimen | Unknown frequency-admissible entries | Provisional strict pairs (review only) |
|---|---|---|
| SP02 | 17 | exp 2 ↔ FE 8 (MAC 0.958); also below the coverage of 2 |
| SP13 | 28 | exp 4 ↔ FE 10 (0.888), exp 5 ↔ FE 11 (0.889) |

A final frozen set needs the complete MAC matrix. That means re-extracting FE shapes
from the archived ODBs with Abaqus Python, which needs a separate HUMAN gate. SP02 and
SP13 are development and test specimens only (M2 production physical readiness
`NOT_READY`).

## Complete MAC matrix from validated shape packs (M4.2 integration)

After the HUMAN-authorised ODB shape-extraction gate (review: PASS),
`services.archived_baseline.shape_pack_evidence(baseline, pack, registration,
experimental_modes, ...)` builds the **complete** experimental × FE MAC matrix from the
pinned baseline shape pack ([../fe_shapes/](../fe_shapes/README.md)).

- **Binding:** pack and baseline must agree on job, generated INP, ODB, FE geometry,
  registration, node set (= registration subset), FE modes and exact frequencies.
- **MAC:** computed in the experimental frame (FE shapes × R of the FrozenRegistration)
  on the measured-DOF contract, with the comparator's MAC formula.
- **Check:** every archived MAC entry must be reproduced (≤ 1e-9), or the matrix is
  refused.

**Strict freeze result** (`STRICT_IDENTIFICATION_PAIRING`, M1 eligibility, no unknown
entries):

| Specimen | Status | Rows | Reason |
|---|---|---|---|
| SP02 | **NOT_FROZEN** | provisional exp 2 ↔ FE 8 (MAC 0.958) | Only 1 strict pair < required 2. Exp 1 has no FE mode within 15 %; exp 3–9 have MAC < 0.80 for every FE mode within 15 %. |
| SP13 | **FROZEN** | R1 exp 4 ↔ FE 10 (MAC 0.888, Δf −9.05 %), R2 exp 5 ↔ FE 11 (MAC 0.889, Δf −9.07 %) | Complete evidence, unambiguous, coverage 2 |

The record-only replay (without packs) stays INCOMPLETE_EVIDENCE, as before.
