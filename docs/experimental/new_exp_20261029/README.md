# NEW-EXP-R1 — new experimental delivery of 2026-10-29: inventory and working-source map (non-normative)

**Status: analysis report, REVIEW_READY for the owner. Non-normative.** It changes no specification, decision,
evidence, status, registration, catalogue entry, criterion or regression. A working-source entry is not a scientific
acceptance of a measurement.

- **Delivery:** `D:\Snadwich\New  EXP results`. The folder name has **two spaces**.
- **Contents:** 16 files, 461 502 587 bytes, no byte duplicates. Every file was only read, and its SHA-256, size and
  modification time are the same before and after this work.
- **File provenance:** [SOURCE_PROVENANCE.csv](SOURCE_PROVENANCE.csv) gives the path, size, SHA-256, specimen,
  series, PSV acquisition time, type, readability and source status of each file.
- **Measurement tables:** kept outside git, with the owner (`NEW_EXP_20261029_REVIEW` on the Desktop). They include
  frequencies, damping, records and Excel cell provenance.

## Lab notes (`Read me.txt` and the workbook's text box)

- **ROTATED.** The plate was rotated **45° clockwise as viewed from the Polytec system**. It was suspended with rubber
  bands and strings at **two upper points on the nodal line of the first mode**.
- **Node numbering** in the Polytec data changes with the rotation; each file must be read with its own geometry.
- **Polytec Z distance.**
  - It was measured as **1.15 m**; earlier sessions used the 1 m default.
  - The UNV files exported directly from Polytec carry it.
  - In the data: z = −1.15 m in every delivered UNV, against −1.0 m in the archived exports. The in-plane scan
    geometry of the same session (SP-13 260910) is about 1.145× larger in the new export.
- **What ROTATED means here.** A new mounting and view: it is **not** a known FE↔EXP coordinate transformation. The
  reference orientation of the turn, the face shown, the excitation and the suspension details are UNKNOWN.

## Series

The acquisition times come from the PSV header (dataset 151).

| Series | Specimen | Acquired | Content |
|---|---|---|---|
| `NEXP29/PLATE300-1MM/S261027-ROTATED` | single 300 × 300 × 1 mm plate (M11 plate by name; not in the specimen catalogue) | 27-Oct-26 11:38:17 | FRF (dataset 58) + Testlab PolyMAX set `Polymax_bravo`, 11 records, 18.63–191.60 Hz, 289 points, Z |
| `NEXP29/SP-13/S261028-ROTATED` | SP-13 | 28-Oct-26 10:15:31 | FRF + `polymax_bravo`, 12 records, 28.80–267.36 Hz, 289 points, Z |
| `NEXP29/SP-10/S261029-ROTATED` | SP-10 | 29-Oct-26 09:20:02 | FRF + `polymax_bravo`, 12 records, 26.50–266.85 Hz, 289 points, Z |
| `NEXP29/PLATE300-1MM/S261018-RETRY` | plate | 18-Oct-26 17:02:20 | FRF only (27 peak records, PROVISIONAL); no fitted set; not in the workbook |
| `NEXP29/SP-13/S260910-A-REEXPORT` | SP-13 | 10-Sep-26 17:38:17 (= catalogue) | archived session, new FRF export with Z 1.15 m |
| `NEXP29/SP-10/S260911-B-REEXPORT` | SP-10 | 11-Sep-26 12:21:25 (= catalogue) | archived session, new FRF export with Z 1.15 m |

- **Naming caution.** The files named `*_Polytec_*.unv` are **Simcenter Testlab** exports (dataset 55 PolyMAX sets),
  not Polytec exports.
- **Damping** is not recorded in their dataset-55 records; it is only in the workbook, as a ratio.

## Workbook `Experiment_Freq_damping_LMS_Rotated.xlsx`

The workbook has one sheet, `Rotated_test`: typed text, no formulas, 66 pictures and a setup sketch.

**Old-series columns are archived sessions:**

| Columns | Archived session | Agreement |
|---|---|---|
| B / C, "plate only" | plate 261016 (M11) | 9 of 10 records |
| H / I / J, "SP13 retry(a)" | SP-13 260910 a, set `Best` | all 12 |
| K / L / M, "SP10 retry(b)" | SP-10 260911, set `Bestttt` | 12 of 13 |

Each listed value agrees with its fit within 0.001 Hz.

**New-series columns:** E / F (plate ROTATED), N / O (SP-13 ROTATED) and Q / R (SP-10 ROTATED). They agree with the
delivered dataset-55 records of the same fit within 0.0012 Hz; the last record of each fit is not listed.

**Mode identity.** `MODE_IDENTITY_NOT_VERIFIED`: no old mode is paired with a new one. The lowest fitted frequency
changed (old → new):
- plate 33.45 → 18.63 Hz;
- SP-13 31.42 → 28.80 Hz;
- SP-10 29.29 → 26.50 Hz.

That these are the same shapes is not established. A value closer to an FE result is not thereby more correct.

## Importer

All 9 UNV and the 3 LMS projects are read by the project's own importer chain (`services.importer_runtime` with
`services.local_experimental_preview`, as in the new interface) without an error. Each LMS project is read through
its companion UNV. The `.svd` PSV projects are not an importer format.

**Records.**
- 201 FRF peak records are labelled `PROVISIONAL — NOT A VALIDATED FITTED MODE`; the first record is never
  excluded.
- The 35 dataset-55 records are curve-fitted.
- The importer excluded only the residual records of each PolyMAX set ("below / above").

## Working-source map (owner's rule of 2026-10-29)

| Specimen | Old source | New source | New modal set | Working status | Registration |
|---|---|---|---|---|---|
| SP-13 | `OLD_HISTORICAL_SOURCE`: 260910 a `SP13_a_polymax.unv` set `Best` (accepted physical registration) and 260909 `Bravo (1)` (frozen frequency-only fixture), unchanged | `SP13_500by500_Glue420_Auxetic_ROTATED_Polytec_261028.unv` (+ FRF UNV) | `polymax_bravo` | `NEW_WORKING_SOURCE` for research viewing and frequency diagnostics | `PHYSICAL_REGISTRATION_NOT_VERIFIED`; the accepted SP-13 registration is not transferable |
| SP-10 | `OLD_HISTORICAL_SOURCE`: 260911 `SP10_b_polymax.unv`, 260831 PolyMAX zip | `SP10_b_rotated_500by500_Glue420_Honeycomb_ROTATED_Polytec_261029.unv` (+ FRF UNV) | `polymax_bravo` | `NEW_WORKING_SOURCE` (same scope) | `PHYSICAL_REGISTRATION_NOT_VERIFIED` (none exists) |
| plate 300 × 300 × 1 mm | `OLD_HISTORICAL_SOURCE`: 261016 `_POLYMAX.unv` (M11) | `300by300_plate_only_1mm_ROTATED_Polytec_261027.unv` (+ FRF UNV) | `Polymax_bravo` | `NEW_WORKING_SOURCE` (same scope) | `PHYSICAL_REGISTRATION_NOT_VERIFIED` (M11: pending) |
| SP-01 … SP-09, SP-11, SP-12, SP-15 | unchanged | none | — | unchanged | unchanged |

**Other entries:**
- **Old-session re-exports and the 261018 retry** are not working sources and replace no archived file.
- **`SETUP_UNDER_REVIEW`** is a human flag only, and it is not set by this report.

## Open points

These need the lab or the owner:
1. The reference orientation of the 45° turn, especially for SP-10, whose 260911 session was already rotated 90°.
2. The face shown to the camera.
3. The first-mode nodal line and the suspension points (the old-series suspension is not described).
4. Whether the 1.15 m correction applies to the PolyMAX shapes.
5. The excitation.
6. The `.svd` of the plate ROTATED session.
7. A fitted set for the 261018 retry.
8. Whether the plate is the same physical plate as in M11.

No Abaqus, solver, MAC, registration, orientation, Auto-ID or LM was run.
