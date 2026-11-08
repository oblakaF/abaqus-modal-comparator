# Materials readiness R1: can the draft Windows program be used now?

Scope: a check of the existing implementation on existing verified data. No Abaqus, no new FE calculation, no real-material
identification, no change to original data, registrations or scientific statuses. **No program defect was found, so no
code was changed**; the only tracked change is this report.

## 1. Baseline

- **Git:** branch `feature/materials-offline-v1`; HEAD `edb343fdd97c09588ca93aeb7f8ce07321f2b864`, equal to origin.
  `origin/main` is `0bea1de68dc346d20958e6f53a9e1d634a870f5d`. The tracked tree is clean; 25 untracked items are
  preserved.
- **Read beforehand:** AGENTS.md, CLAUDE.md, MAT-1 to MAT-4, MAT-4.UX1.F1 and REAL-FIT.R1.
- **Environment:** Windows 10, `.venv` Python 3.14.6, real `windows` Qt platform. The monitor was 2560 × 1440 at 150 %;
  windows were set to 1366 × 768 and 900 × 700.
- **Evidence** is in `D:\git\abaqus-modal-comparator-work\research\MATERIALS_READINESS_R1\` (drivers, consoles, JSON
  results, 110 screenshots). LOCALAPPDATA was redirected into this folder.

**Inputs:** verified working copies, listed in `inputs_manifest.json` (`43149a81…`). Every hash equals the REAL-FIT.R1
record:

| File | Source | SHA-256 |
|---|---|---|
| `CFRP_S4R_0875_FreeFree.inp` | copy of the original on `I:` (read only) | `962f75f2…` |
| `CFRP_S4R_0875_FreeFree.dat` | copy | `f440592598…` |
| PolyMAX UNV `300by300_plate_only_1mm_ROTATED_Polymax_261027.unv` | copy | `76db80ae…` |
| ODB `real_plate_r1\fe\CFRP_S4R_0875_FreeFree.odb` | existing verified copy with its extracted package | `7daeb7e3…` |

## 2. Results

| # | Function | How checked | Result |
|---|---|---|---|
| 0 | Launch through `RUN_NEW_GUI.cmd` | `launcher_check.ps1`: started the real launcher, found its own window, closed it with its own close message | **PASS**: window "Abaqus–Simcenter Modal Comparator" after 3.5 s; launcher exit code 0; no process left |
| 1 | Open the FE and PolyMAX copies (Analyze) | `readiness_driver.py`, real window | **PASS**: the existing package was found ("Abaqus is not needed"); 11 Polymax_bravo records; 3.3 s. The Abaqus consent hook was never asked |
| 2 | Frequencies and shapes without invented mode pairs | same | **PASS**: the Review page shows **REGISTRATION_REQUIRED**, "No verified physical registration: no mode pairs and no MAC. Frequency comparison only". The rows are labelled "candidates chosen by frequency, not validated mode pairs", and non-one-to-one rows are flagged. 0 MAC pairs; EXP and FE shapes are drawn side by side |
| 3 | Research Tuning (Ritz) with warnings and both A/B alternatives | same | **PASS**: FREE E1/E2/G12, 347 surrogate solves, 3.9 s. Status **E1_E2_AXIS_ASSIGNMENT_NOT_IDENTIFIABLE**. Both rows shown ("none chosen"): A 59643 / 43593 / 4824, B 44171 / 58724 / 4817. Labels shown: EXPLORATORY_FE_INPUT_CANDIDATE, NOT_A_MATERIAL_PROPERTY, NOT_VALIDATED_IN_ABAQUS, the Kirchhoff-surrogate note and the 10 %-not-demonstrated note. No sideways page scroll at 900 |
| 3a | Tuning export | same | **PASS**: the JSON export was read back. Status and both minima are identical (exact doubles) to the accepted REAL-FIT.R2 export (`export_free.json` `143ef89b…`) |
| 4a | Analyze project: save, then reopen in a fresh process | `analyze_project.py save` / `open` | **PASS**: 2.9 MB project; on reopening, the frequency and candidate tables are identical; only the project file is read (no UNV, ODB or package); the file is unchanged; no comparison is invented |
| 4b | Materials study: results, plots, diagnostics, save and reopen | copy of the accepted MAT-4.UX1.F1 driver, phases `main` / `reopen` / `closerun` | **PASS**: 179 / 21 / 3 checks, 0 FAIL, no traceback. On reopening, 13 tables, the summary and the codes are identical, with no calculation run; a path planted inside a saved file is not opened |
| 4c | Reopen a Research Tuning result in the GUI | inspected the panel and menus | **NOT_AVAILABLE**: export only. An exported proposal cannot be opened back into the Research Tuning page (§3) |
| 5 | Stand-alone synthetic example without Abaqus | `materials/smoke_driver.py main` | **PASS**: Ritz 119 solves, CONVERGED, DIAGNOSTIC_OPTIMIZER_CANDIDATE, "Synthetic software test, not a material value". Stage A 86 solves, CONVERGED, D 0.36, D66 0.05, r 0.09, again identical after a cancelled run. Cancel works for both methods; closing during a run ends the worker |
| 6 | Real scientific identification stays blocked | same, FE / Experiment tab with the **real** copies | **PASS**: the real UNV (289 DOFs, 11 records) and the FE package are read and their facts shown. Registration is "Absent". With a real source, Run and Prepare are disabled; a direct call is refused (**BLOCKED, NOT_AUTHORIZED**); an "AUTHORIZED" note unlocks nothing; 0 study calls |
| 7 | English-only GUI | text scans in both drivers | **PASS**: no Cyrillic in visible widgets |
| 8 | Safety | audit hooks in every driver | **PASS**: no process start, no access to `I:\` or KK-VIM; input copies and ODB unchanged |
| 9 | Focused tests (`.venv`, one BLAS thread, one at a time) | `test_real_fit_r1_tuning`, `test_real_fit_r2_stability`, `test_research_fe_trial_preflight` | **PASS**: 48 tests, about 30 s. Full suite NOT_RUN |
| 10 | Abaqus extraction of a new ODB from the GUI | — | **NOT_RUN**: Abaqus is forbidden in this task |
| 11 | Native Windows file dialogs and physical mouse/keyboard | — | **NOT_RUN**: dialogs were replaced by the panels' own hooks and events went to widgets directly; no human viewed the screen during the drivers |

Every driver check is recorded: `readiness_results.json` (15 / 15 PASS, `d1156cac…`), `analyze_project_save.json` and
`analyze_project_open.json`, `materials/console_*.txt`, `console_launcher.txt`.

## 3. What stops the program being used now

**For the software**, nothing in the tested scenario. Every step works: opening the existing data, viewing
frequencies and shapes, research tuning with correct warnings, export, project save and reopen, the synthetic example
and the real-data block.

**Practical gaps.** These are missing functions, not defects; each would need its own owner decision.

1. **Research Tuning results cannot be reopened** in the GUI. They can only be exported to JSON; reproducing a result
   means re-running the tuning, which takes about 4 s.
2. **New ODBs need Abaqus**, through the GUI extraction with user consent. Only already-extracted packages open without
   it. This path was not exercised here.

**Scientific blockers** (by design, not software faults):
- There is **no accepted physical registration** for this plate, so there are no MAC pairs. Mode identity is not
  established, and FE↔EXP stays a frequency-candidate view.
- Real-data inverse execution on the Materials page is **BLOCKED / NOT_AUTHORIZED**.
- u(ln f_exp) is NOT_AVAILABLE.
- The E1/E2 axis assignment is not identifiable from frequencies.
- M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged.

## 4. Conclusion

**The draft Windows program is usable now as a research and visualisation tool on existing data.** That covers:
- opening FE packages and PolyMAX UNV;
- the frequency and shape review, with explicit REGISTRATION_REQUIRED and no invented pairs;
- the exploratory Ritz tuning that keeps both A/B alternatives and every warning;
- export, project save and reopen;
- the synthetic Materials example.

**It is not usable for real material identification.** That is blocked by design until a physical registration, an
experimental uncertainty and the axis assignment exist.

No reproducible program defect was found in the tested scenario, so no fix and no regression test were needed.

STOP.
