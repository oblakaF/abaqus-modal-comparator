# Research Tuning — SP-13 Sandwich Trial

**Status: REVIEW_READY.** Branch `feature/materials-offline-v1`, from `19df3d0`.
EXPLORATORY SANDWICH TRIAL / UNVERIFIED MODE CORRESPONDENCE / NOT A MATERIAL PROPERTY / NOT VALIDATED IN ABAQUS.

A separate section of the Research Tuning page for the SP-13 sandwich panel. It compares the measured frequencies of the
ROTATED PolyMAX set of 28 October 2026 with the FE baseline of `SP13_mesh_local_v1_modal` and calculates exploratory
face-sheet values **E (E1 = E2)** and **G12** for a manual Abaqus check. It starts no Abaqus and no FE solve, computes
no MAC and writes nothing into the INP, the UNV or the ODB. The Kirchhoff-Ritz plate surrogate is not used.

## Procedure

1. Start `RUN_NEW_GUI.cmd` and open **Research Tuning**.
2. **Load the UNV:** in *1. Model and measurement* choose
   `SP13_500by500_Glue420_Auxetic_ROTATED_Polytec_261028.unv`.
3. **Load the FE model:** choose `SP13_mesh_local_v1_modal.inp` (its `.dat` beside it is read too). The page says that the
   plate tuning cannot use this INP; that is expected. The ODB is not needed.
4. In **SP-13 Sandwich Trial** press **Sensitivity archive folder...** and choose the carbon project archive (the folder
   that holds `fe_shapes`), unless `AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE` is set. Press **Read SP-13 sources**.
5. **Select the trial hypothesis:** *Frequency rank* (the k-th record against the k-th elastic FE mode) or *Declared list*
   (your own `record:FE mode` pairs, for example `1:7, 2:9, 3:8, 4:10`). Nothing is selected for you. Set each record to
   FIT, HOLDOUT or EXCLUDED.
6. Press **Calculate exploratory candidates**.
7. Press **Export for Abaqus (TXT/CSV)...** and choose a folder.

## What is checked before anything is calculated

- **Experimental file:** its SHA-256 must be the recorded series `NEXP29/SP-13/S261028-ROTATED`
  (`docs/experimental/new_exp_20261029/SOURCE_PROVENANCE.csv`). The September frozen dataset, the SP-10 and plate series
  and any unrecorded file are named and not calculated.
- **FE model:** the INP's SHA-256 must be the accepted source input of `docs/auto_id/forward_models/SP13.physical.forward.json`.
  Its face material record (`CFRP_Face`, `*Elastic, type=ENGINEERING CONSTANTS`) is read from the file and must hold the
  baseline values E1 = E2 = 52 000, G12 = 4 500 MPa. The `.dat` must print the accepted baseline frequencies.
- **Sensitivities:** the accepted CARBON-5A ±5 % states of this FE model only: the pinned repository records and the five
  validated shape packs (file SHA-256, content hash, node set, frequencies). Every FE mode 7–30 is followed FE-to-FE
  through E+, E−, G12+ and G12− by the strict branch tracker (MAC ≥ 0.90, unique). The values of FE 10 and FE 13 must
  reproduce the accepted strict freeze. The CARBON-5F core sensitivities are not read.

If the shape packs are not available the section still shows the files, their identity and the frequency comparison,
with `FACE_SENSITIVITY_EVIDENCE_MISSING`; no response model is assumed and nothing is calculated.

## The calculation

`ln f = ln f0 + S_E ln(E / 52000) + S_G12 ln(G12 / 4500)` for each FIT record against the FE mode you stated, solved by
bounded linear least squares (`scipy.optimize.lsq_linear`) inside the ±5 % interval the sensitivities were computed over
(E 49 400–54 600 MPa, G12 4 275–4 725 MPa). The core, the ties, the geometry, the densities, the Poisson ratios, E3, G13
and G23 are not touched.

| Outcome | Meaning |
|---|---|
| `NUMERICAL_CANDIDATE_WITHIN_VERIFIED_RANGE` | the fit ends inside the interval |
| `TRIAL_POINT_AT_VERIFIED_RANGE_LIMIT` | UNSUPPORTED EXTRAPOLATION: the data ask for more than ±5 %. The values are the limit of the interval, a next trial point, **not** a fitted value. The unbounded linear solution is shown as a diagnostic only |
| `NOT_IDENTIFIABLE_RANK_DEFICIENT` | the FIT records cannot separate E and G12 (rank < 2 at rcond 1e-3): no value |
| `REFUSED` | an invalid request, for example a FIT record on an FE mode without a verified sensitivity (FE 30) |

The result lists the measured, FE baseline and predicted frequencies with signed differences, the rank, singular values
and condition number, and the same calculation under every other stated correspondence (`COMPETING SOLUTIONS` when it
gives other values; none is chosen).

## The export

`sp13_face_candidate_abaqus_<time>.txt` and `.csv`; an existing file is never replaced. They hold the status, the nine
constants of the face record (E1, E2, G12 with every digit; the other six exactly as the INP writes them), the data lines
in the INP's own order and layout with the INP line numbers they replace, the frequencies and residuals, the checks and
the sources with SHA-256. Only the face material's `*Elastic` data lines are written: no core material, no density, no
`*Material` block. Nothing is exported without a numerical value or without a verified face record, or when a source
file changed after it was read.

## Limits

- The mode correspondence is the user's hypothesis; no physical registration applies to this series.
- Local ±5 % response of this exact FE model; nothing beyond it is described.
- With the core, the ties and the mass fixed, a face value may compensate a model-form error (D-074 / D-075).
- M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged. SPEC, DECISIONS,
  STATUS, EVIDENCE, registrations and gates were not changed.
- The calculation was tested on synthetic frequencies only. A calculation on the measured set is the owner's to run.

## Code

- `src/services/sandwich_trial_candidates.py`: identity checks, sensitivities, the bounded trial, the export.
- `src/new_gui/research_tuning_model.py`, `src/new_gui/research_tuning_panel.py`: the section.
- `tests/test_sandwich_sp13_trial.py`.
