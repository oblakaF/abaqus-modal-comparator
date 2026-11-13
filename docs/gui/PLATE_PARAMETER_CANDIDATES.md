# Plate Study — Calculate parameter candidates

**Status: REVIEW_READY.** Branch `feature/plate-candidate-results-gui`, from `0bea1de`.
RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY / LINEAR_APPROXIMATION.

The page calculates candidates of the FE model's E1, E2 and G12 for the CFRP plate PLATE-300x300x1mm from the
measured frequencies of the UNV you read. It runs offline. No Abaqus, solver or production Auto-ID is started.

## Procedure

1. Start `RUN_NEW_GUI.cmd`.
2. **Workspace → Experimental data → Choose file...**: the plate UNV of 27 October 2026
   (`300by300_plate_only_1mm_ROTATED_Polytec_261027.unv`). Press **Inspect file**.
3. **Workspace → FE results → Choose file...**: `manifest.json` of the baseline M11 FE package
   (`runs\m11_carbon_plate\odb_extraction_r6\output`). Press **Inspect file**.
4. **Analysis → modal set**: choose `Polymax_bravo`.
5. **Plate Study → A. Current PLATE Study → Calculate parameter candidates**.
6. **Export candidates for Abaqus...**: choose a folder. For each calculated scenario the page writes
   `plate_candidate_<scenario>_<time>.csv` and `.txt`.

The button is off until these files are read. The reason is written under the buttons.

## What is calculated

- **Scenarios** (declared before the fit; each EXP ↔ FE row is a hypothesis, never a verified pair):
  - S0: EXP1 ↔ FE7; G12 is fitted; E1 and E2 stay at the FE model's values.
  - H1: EXP1 ↔ FE7 and EXP8 ↔ FE15+FE16; E1 = E2 and G12 are fitted.
  - H2: EXP1 ↔ FE7 and EXP7 ↔ FE14; E1 = E2 and G12 are fitted.
- **Method:** the project's bounded LM (`identification_step.run_bounded_lm`) on the log-linear model of the
  PRIORITY-2 sensitivities of the M11 S4R model (six real Abaqus ±5 % solves). Bounds: 0.5–2 × the baseline. The
  run is deterministic.
- **Fixed inputs:** E3, ν12, ν13, ν23, G13, G23, density and thickness of the FE model.
- No record is paired by its nearest frequency. MAC is not an input. No scenario is ranked or chosen.

## What the page shows for each scenario

- E1, E2, G12 in MPa, the fit status, the rank of the fitted parameters and the rank of E1 / E2 / G12.
- The measured frequency, the baseline and predicted FE frequency and the residual of each declared row.
- The predicted FE frequency of every tracked FE term.
- Warnings: extrapolation beyond the solved ±5 %, a value at a bound, a baseline difference outside the 15 % window,
  another FE term within 3 % of the record.
- What the rows do not determine. In S0, E1 and E2 are not determined; the page gives the range of G12 that fits
  the same record for E1 = E2 inside the bounds. In H1 and H2, E1 and E2 are not separable.
- **Archived records, apart:** the archived PRIORITY-3 set as a regression check and the archived PRIORITY-4 Abaqus
  frequencies of that set. They are never the calculated answer.

A rank-deficient scenario or an ambiguous pairing gives no number; the page states the reason.

## Checks before the calculation

- The experimental file is the plate's working source, by SHA-256.
- The modal set is `Polymax_bravo` and its records are numbered from 1.
- The FE package is the baseline `S4R_0875_BASELINE`, by the SHA-256 of its manifest, and its frequencies are the
  base point of the sensitivity table.
- The files are hashed again on disk before the calculation and before the export.

Any mismatch refuses the calculation and lists every reason.

## The exported files

- `.txt`: the parameters for manual entry, the Abaqus `*Elastic` data lines, the fixed inputs, the hypotheses with
  measured and predicted frequencies, the predicted FE frequencies, the warnings, the limits and the sources.
- `.csv`: the same content as rows of `section, item, value, unit, note`.

The predicted frequencies are values of the log-linear model, not Abaqus results. Run the exported parameters in
Abaqus yourself and compare each FE mode with the predicted value.

## Code

- `src/services/plate_candidate_results.py`: the fit (moved unchanged from `research/plate_inverse/run_inverse.py`,
  which now imports it), the source checks, the archive comparison and the export.
- `src/new_gui/plate_study_model.py`, `src/new_gui/plate_study_panel.py`: the command and the result card.
- Tests: `tests/test_plate_candidate_results.py`, `tests/test_plate_candidates_qt.py`.

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, frozen registrations and tolerances. M8 GATE NOT_MET, D-077
NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED and 261027 PHYSICAL_REGISTRATION_NOT_VERIFIED stay as they
are. The iterative estimation command stays disabled.
