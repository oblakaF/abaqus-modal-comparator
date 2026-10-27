# APP-REAL.1 — the Home screen (APP-UI.1) on real verified data (2026-10-27)

Branch `validation/app-ui1-real-data` from `main` `c31f642aa8aaac6c2e85919e5aa53a0384397371` (merge of PR #108,
APP-UI.1). Post-merge CI run `40492228424`: success. This branch adds this report only; no source, test, registration,
gate or governed document is changed. Test artifacts (screenshots, reports, logs) are outside Git.

## Verdict

- **Home on real data.** For SP-02 and SP-13, Home works end to end:
  - file and modal-set choice;
  - readiness;
  - comparison without Abaqus;
  - results summary and links to frequencies, mode shapes and MAC;
  - material-property status;
  - PDF / Excel export to a safe folder;
  - removal of a stale result.
- **Agreement with the archived references** (CORE-E2E T1b, T2):
  - pairs, pair status, order flag and mapped points are identical;
  - FE frequency, experimental frequency, frequency error and MAC are identical (largest absolute difference 0);
  - geometry match, transform and coordinate scales are identical.
- **One finding** (F-1, below): for an extracted `manifest.json` input, Home's readiness row *Abaqus modes* shows the
  mode-range field (6 to 15). The comparison uses every extracted mode (SP-13: 7–30). The results are not affected.
  Not fixed: source changes are outside this task.

## Sources

- **Documents read:**
  - `docs/gui/CORE_E2E_VALIDATION.md` (T1b, T2);
  - `docs/gui/POST_R7_PROGRAM_E2E_ACCEPTANCE.md` (A1, A2);
  - `docs/auto_id/SPECIMEN_CATALOG.md`.
- **Run folder:** `D:\git\abaqus-modal-comparator-work\runs\core_e2e\run_20261016`. It was read only; no file in it
  was changed.

| Record | SHA-256 |
|---|---|
| `copy_verification.json` | `0d47962e5adf0583d1e730d2dd65312cdeba07686caeb14c24b60154a352683a` |
| `output/ws_SP13/analysis_preseeded_m4/PRESEEDED_PROVENANCE.json` | `9a18773ae9e95e936ac0c8cfbe7933458adc88176ad8df826817023ceba2b448` |
| `stageA_SP02_extraction_comparison.json` | `9aefdab1bca31b0d5a25078f1c3dec2c33a69bfe6ed405d63168d823b195db6e` |
| Reference T1b SP-02 `output/ws_SP02/analysis_f72d1650400b8ccd/analysis_summary.json` | `2ad94b15f3791a01841ab1f435c884a3f4e4c1f70ee28ba2501bb0e51591504c` |
| Reference T2 SP-13 `output/ws_SP13/analysis_cc3ae2edc26339e6/analysis_summary.json` | `e68619bfe81b8f031ff95a6333d4766f035f417b20ad3b5557b9c9d7a6f36bfa` |

**Working copies.** The working copies were made from that folder for APP-RC1. Before use, each of the 43 SP-02 /
SP-13 files was hashed again and matched against two things:

- the run's own record: `copy_verification.json` for the UNV files, `stageA_SP02_extraction_comparison.json` for the
  SP-02 extraction, `PRESEEDED_PROVENANCE.json` for the SP-13 extraction;
- the file in the run folder.

All 43 match. Four files have no recorded hash: the SP-02 `manifest.json`, the SP-02 extraction log and both
`extraction_signature.json`. For them only copy = source is shown.

| Input | Size, bytes | SHA-256 | Evidence |
|---|---|---|---|
| SP-02 `SP02_polymax_retry_260803.unv` | 13 597 269 | `2671db01b6401a9a9bbec7d8c2aa2191b0b35b5ae791756b91c7ccd381a41785` | `copy_verification.json` (SP02/bravo-1-physical) |
| SP-02 extraction `manifest.json` (modes 6–15, 14 files, 1.71 GB) | 35 398 | `d1f2ccc73c25e932bf3d5f2cf7569bb9cfdfba2c6361ae7833995f97c808dbca` | copy = run file; geometry and mode files per `stageA_SP02_extraction_comparison.json` |
| SP-13 `SP13_a_polymax.unv` | 38 541 973 | `f268023583972f0a9c1660bc60631587e8f3330e4fb7495e52d8310906af39fe` | `copy_verification.json` (SP13/best-physical) |
| SP-13 extraction `manifest.json` (M4 extraction, 27 files, 3.35 GB) | 38 878 | `91c360b4f603b3261bc5306051dbd15807996af4c40764168f69ceafbc285038` | `PRESEEDED_PROVENANCE.json` |

The four input files had the same size, time stamp and SHA-256 after the run.

## How it was run

- **Program:** `RUN_PROGRAM.cmd` of the working copy at `c31f642` (unchanged), with an isolated Windows profile
  (`USERPROFILE`, `HOME`, `LOCALAPPDATA`).
- **The FE input is the extracted `manifest.json`,** so Abaqus cannot start. No child process of the program was seen
  during either analysis. No solver, LM or Auto-ID was run.
- **Every action went through Home:**
  - **Choose...** for the files;
  - the **Modal set** list;
  - **Run analysis**;
  - the result links: **Frequencies and pairs**, **Mode shapes**, **MAC matrix**.
- **The only dialog during an analysis** was "Confirm experimental calibration", answered OK with the defaults:
  Abaqus model mm, experiment m, calibrated physical geometry.
- **File dialogs:** answered by a test-only `sitecustomize.py` hook on `PYTHONPATH`, only with paths inside the
  temporary acceptance folder. No native Windows file dialog was opened. Reports were written to a temporary
  `reports` folder.
- **Scenario in one session:**
  1. SP-02 (session preset to the SP-02 files): modal set, run, views and reports.
  2. **Choose...** the SP-13 UNV on Home: the SP-02 result is removed.
  3. **Choose...** the SP-13 extraction, modal set, run, views and reports.

## SP-02 (bravo-1-physical, extraction modes 6–15)

| Check | Result |
|---|---|
| Files on Home | `manifest.json`, "Extracted Abaqus results (no Abaqus run is needed)"; `SP02_polymax_retry_260803.unv` |
| Modal set | before the choice: "The file has 3 fitted modal sets: choose the one to compare", *Not ready yet. Still needed: Modal set*, Run disabled. Chosen on Home: **Bravo (1) — 9 modes** (key `bravo-1`) |
| Readiness | *Ready: the analysis can be run*; Abaqus: "Not needed for extracted results" |
| Comparison | 216 s, 0 Abaqus. Registration: reused by FE geometry identity, SP02/bravo-1-physical, registration `9b63f6c89133…` (FE geometry `72e8597a042f…`, 1 663 816 nodes) |
| Home result | "Comparison complete …"; matched mode pairs 6; mean frequency difference 1.21 %; mean MAC 0.948 Excellent/Good (3), 0.775 all admissible (6); geometry match 100.0 % |
| Views from Home | Frequencies and pairs → 2. Compare: 6 rows. Mode shapes → 3. Shapes: pair FE 8 / exp 2, MAC 0.918. MAC matrix → 4. MAC: matrix FE 7–15 × exp 1–9 and regression |
| Reports | Excel 574 786 bytes, PDF 1 409 956 bytes, "Report saved" with the requested path |
| Stale result | **Choose...** SP-13 UNV on Home → "Inputs changed after the analysis: the previous result is no longer active and cannot be exported"; values cleared; links disabled; modal set required again |

| FE mode | Exp. mode | FE Hz | Exp. Hz | Error % | MAC | Status | = T1b |
|---|---|---|---|---|---|---|---|
| 8 | 2 | 75.2411 | 74.3760 | +1.16 | 0.9176 | Excellent match | yes |
| 9 | 3 | 78.2501 | 78.1616 | +0.11 | 0.6224 | Review | yes |
| 10 | 4 | 89.3271 | 90.5749 | −1.38 | 0.9508 | Excellent match | yes |
| 11 | 5 | 90.5440 | 91.9495 | −1.53 | 0.5703 | Poor match | yes |
| 12 | 6 | 144.1767 | 144.7627 | −0.40 | 0.6139 | Review | yes |
| 13 | 7 | 207.4273 | 201.9995 | +2.69 | 0.9754 | Excellent match | yes |

The accepted strict rows R1 (2 / 8), R2 (4 / 10) and R3 (7 / 13) are among these pairs, with the same frequencies
and MAC.

## SP-13 (best-physical, M4 extraction)

| Check | Result |
|---|---|
| Files on Home | **Choose...** → SP-13 extraction `manifest.json` and `SP13_a_polymax.unv` |
| Modal set | "The file has 2 fitted modal sets"; chosen on Home: **Best — 12 modes** (key `best`) |
| Readiness | *Ready*; Abaqus not needed |
| Comparison | 491 s, 0 Abaqus. Registration: reused by FE geometry identity, SP13/best-physical, registration `2eeeaa869885…` (FE geometry `34d69d7920f5…`, 1 585 637 nodes) |
| Home result | "Comparison complete …"; matched mode pairs 5; mean frequency difference 6.68 %; mean MAC 0.953 Excellent/Good (2), 0.714 all admissible (5); geometry match 100.0 % |
| Views from Home | 2. Compare: 5 rows; 3. Shapes: pair view; 4. MAC: FE 7–30 × exp 1–12 and regression |
| Reports | Excel 722 451 bytes, PDF 1 365 161 bytes, "Report saved" with the requested path |

| FE mode | Exp. mode | FE Hz | Exp. Hz | Error % | MAC | Status | = T2 |
|---|---|---|---|---|---|---|---|
| 8 | 3 | 72.7238 | 80.8819 | −10.09 | 0.5279 | Poor match | yes |
| 9 | 2 | 75.9511 | 74.1587 | +2.42 | 0.5785 | Poor match | yes |
| 10 | 4 | 85.8515 | 94.3991 | −9.05 | 0.9585 | Good match | yes |
| 11 | 5 | 87.7713 | 96.5211 | −9.07 | 0.5594 | Poor match | yes |
| 13 | 7 | 199.9771 | 205.6489 | −2.76 | 0.9469 | Excellent match | yes |

The accepted strict rows R1 (4 / 10) and R2 (7 / 13) are among these pairs, with the same frequencies and MAC.

## Differences from the references

| Field | Difference | Why |
|---|---|---|
| Pairs, frequencies, errors, MAC, status, order flag, mapped points, geometry fields, `diagnostic_state` | none (largest absolute difference 0) | — |
| `experimental_source` | path only | the working copy instead of the run copy; same SHA-256 |
| SP-02 warning on the registration reuse | wording only | the current program words the archived-sensitivity note differently ("apply only if 11. Scaling verifies this ODB as the accepted baseline ODB by SHA-256" instead of "do not apply"); same registration, same mapping |
| SP-13 registration notice | "reused by FE geometry identity" instead of "Accepted physical registration applied" | T2 selected the accepted baseline ODB and applied the accepted registration directly. Here the input is the extraction `manifest.json`: the accepted-registration option needs the baseline ODB by SHA-256, so the same registration `2eeeaa869885…` was reused by FE geometry identity |

## Experimental mode 1

The first experimental mode is not excluded. It is in the loaded modal set, in the MAC matrix (column 1) and in the
report.

- **SP-02:** E1 (28.01 Hz) is listed as an "unmatched experimental peak candidate in the Abaqus frequency band".
- **SP-13:** E1 (31.42 Hz) is listed the same way.

It is not paired. Its frequency difference to the nearest compared FE mode is beyond the accepted-pair limit of 15 %
stated in the report's quality control:

- SP-02: FE 7, 23.57 Hz, −15.9 %;
- SP-13: FE 7, 22.49 Hz, −28.4 %.

Pairing is the program's existing rule; nothing was excluded or added by hand. This report does not explain
the frequency differences. Suspension effects are not stated as a cause: the 45° suspension change has been
confirmed only for the single plate, not for the sandwich specimens.

## Material properties on Home

Shown in both runs, unchanged by the analyses:

- **Material constants:** "Not determined. This version does not identify material properties: production Auto-ID
  is not authorised (NOT_AUTHORISED). No elastic constant (E1, E2, G12, …) is shown as identified anywhere in the
  program …";
- **Existing evidence:** "No identification evidence is loaded in this session";
- **Auto-ID selection:** "No specimen or campaign is selected".

No material value appears on Home or in the result summary.

## Findings

**F-1 — Home shows the mode-range field as the compared FE modes for an extracted input.**

- **Steps:** Home → **Choose...** the SP-13 extraction `manifest.json` (M4, modes 7–30) and its UNV, with the mode-range
  field at 6 to 15 (the session value).
- **Observed:** the readiness row *Abaqus modes* shows "6 to 15". The comparison uses every extracted mode (7–30):
  the MAC matrix rows are FE 7–30, and the quality-control list names unmatched FE modes up to 30. The result equals
  T2, which ran with 7–30.
- **Cause (existing):** `abaqus_bridge.load_or_extract_odb` loads a `manifest.json` input completely. The range
  applies only to a new ODB extraction. The 1. Files field shows the same number. Home repeats it in plain language
  as if it were the compared range.
- **Effect:** information only. The pairs, MAC and reports are correct.
- **Status:** not fixed (no source change in this task). A possible correction for the SUPERVISOR is that Home says
  the range applies to `.odb` extraction only and names the extracted range of a manifest.

**O-1 — the window does not repaint during the last analysis stage (existing).** During "6/6 Report data generation" the
window keeps its last picture until the stage ends (the duration was not measured); Home's controls are disabled
during a run anyway. Home then shows the finished result as
expected. This is earlier behaviour, not an APP-UI.1 change. A first scripted attempt of this smoke took its result
pictures during that stage. They were discarded, and the run was repeated with the end detected from Home's own
*Ready* mark.

## Limits

- **No fresh ODB extraction.** The FE inputs are the existing extractions; Abaqus, solver, LM and Auto-ID were not
  run.
- **Accepted-registration option not available.** It needs the accepted baseline ODB by SHA-256. The registration was
  reused by FE geometry identity, so the archived sensitivities of 11. Scaling were not checked in this smoke.
- **Calibration defaults.** The calibration confirmation was answered with the defaults (mm / m, calibrated physical
  geometry).
- **Display.** Windows display scaling 100 %; window 1400 × 860.
- **No scientific changes.** No scientific status, registration, threshold, gate or governed document was changed:
  - M8 GATE `NOT_MET`;
  - D-077 `NO_GLOBAL_PARAMETER_VALUE`;
  - production Auto-ID BLOCKED / NOT_AUTHORISED.
