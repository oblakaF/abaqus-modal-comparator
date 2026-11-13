# Research Tuning — Export for Abaqus (TXT/CSV)

**Status: REVIEW_READY.** Branch `feature/materials-offline-v1`, from `29b4cfd`.
EXPLORATORY_FE_INPUT_CANDIDATE / NOT_A_MATERIAL_PROPERTY / NOT_VALIDATED_IN_ABAQUS.

The Research Tuning page already fits E1, E2 and G12 of a plate INP to the measured frequencies with the Kirchhoff-Ritz
surrogate. This command writes the numerical candidates of that fit as files you can use for a manual Abaqus run. It fits
nothing, starts no process and writes nothing into the INP, the UNV or the ODB.

## Procedure

1. Start `RUN_NEW_GUI.cmd` and open **Research Tuning**.
2. **1. Files**: choose the Abaqus INP and the experimental file (UNV). The ODB is optional.
3. **2. Setup**: choose the parameters to fit (`E1, E2, G12` for an orthotropic plate) and press **Run tuning**.
4. **3. Result**: press **Export for Abaqus (TXT/CSV)...** and choose a folder.

The line under the buttons says what will be written, or why nothing can be.

## What is written

- A mirror result (`E1_E2_AXIS_ASSIGNMENT_NOT_IDENTIFIABLE`): `ritz_candidate_A_abaqus_<time>.txt/.csv` and
  `ritz_candidate_B_abaqus_<time>.txt/.csv`. A and B are the two axis assignments; neither is selected or preferred.
- One oriented candidate (`NUMERICALLY_SUPPORTED`): `ritz_candidate_abaqus_<time>.txt/.csv`.
- An existing file is never replaced.

Each `.txt` holds:

1. The candidate status: the label, the optimizer status, the cost, the FIT and HOLDOUT residual RMS of this candidate.
2. The parameter table with every digit: E1, E2, E3, nu12, nu13, nu23, G12, G13, G23, density and shell thickness, each
   with its origin (fitted, or the INP's own value).
3. The Abaqus lines:
   ```
   *Elastic, type=ENGINEERING CONSTANTS
   E1, E2, E3, nu12, nu13, nu23, G12, G13
   G23,
   *Density
   density,
   ```
4. Each measured record with the Ritz frequency of its declared rank at this candidate, and the residual.
5. The fixed assumptions, the tuning's reasons and warnings, and the source files with their SHA-256.

The `.csv` holds the same content as rows of `section, item, value, unit, note`.

## How to use the lines

Put the `*Elastic` data lines into a **copy** of the INP in place of the data lines of its `*Elastic` block, and run that
copy yourself. Units are those of the INP (MPa, t/mm^3, mm). The Ritz frequencies are surrogate values, not FE results;
only the Abaqus run can check a candidate.

## When nothing is written

- No result yet, a cancelled run, or a saved result opened from a file.
- A result of the registered route, which has no INP material block.
- An optimizer status without a candidate (not identifiable, at a bound, not converged, starts disagree).
- A HIGH MISFIT fit: its numbers stay diagnostic, as on the page.
- An INP whose `*Elastic` is not `type=ENGINEERING CONSTANTS`.
- The INP or the experimental file changed on disk after the calculation.

## Check against the archive

On the real M11 S4R deck and the PolyMAX file of 27 October 2026 the page reproduces the REAL-FIT.R4 minima bit for bit
(`tests/test_ritz_abaqus_export.py`, class `RealPlate`; it runs only where those files are):

| | E1 (MPa) | E2 (MPa) | G12 (MPa) |
|---|---|---|---|
| A | 59643.140320162354 | 43592.56647783119 | 4824.07010224442 |
| B | 44170.77433673189 | 58724.14887983508 | 4817.417308245888 |

## Code

- `src/new_gui/research_tuning_model.py`: `abaqus_candidates`, `abaqus_lines`, `abaqus_documents`, `export_abaqus`.
- `src/new_gui/research_tuning_panel.py`: the button and `export_abaqus`.
- `src/services/research_frequency_tuning.py` is unchanged: no solver, optimiser or threshold was touched.

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, gates and thresholds. M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production
Auto-ID BLOCKED stay as they are. No candidate is a validated material property.
