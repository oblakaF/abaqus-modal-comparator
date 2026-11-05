# MAT-3 report: working Materials page

Status: **REVIEW_READY**. Not self-accepted. MAT-4 has not started.

For the reviewer of MAT-3. Base: `7f2cd3733b5e68fa5536d20a21336f6764ba2124`; branch `feature/materials-offline-v1`; `origin/main`
at start `0bea1de68dc346d20958e6f53a9e1d634a870f5d`. The final SHA and the CI state of the implementation commit are in the last
section.

The page runs SYNTHETIC software tests through the existing `run_plate_inverse_study()`. A result is at most
`DIAGNOSTIC_OPTIMIZER_CANDIDATE` with `NOT_A_RELEASE_VALUE`, and recovering known values says nothing about a real material. M8
GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged. No Abaqus run, FE calculation, real-data
fit or PR took place.

## Files

| File | Change | Why |
|---|---|---|
| `src/new_gui/materials_study_model.py` | New | Adapter without Qt: form, deterministic synthetic studies, resource check, tables, plots, real-data facts |
| `src/new_gui/materials_study_panel.py` | New | Sections A to F, the worker thread, save and open |
| `src/services/materials_project.py` | New | `.mcproj` v2 content, exact JSON form and strict check |
| `src/services/analysis_project.py` | Changed | `SCHEMA_V2`, `project_schema()`, optional schema and check on the reader and writer. Defaults stay v1 |
| `src/new_gui/materials_workspace.py` | Changed | Holds the study section; registration text; stops it on shutdown |
| `src/new_gui/materials_workspace_model.py` | Changed | Shapes and data type from the importer's records; corrected status text |
| `src/new_gui/production_window.py` | Changed | File > Open Project gives a v2 file to Materials; page subtitle |
| `src/new_gui/analyze_panel.py` | Changed, 3 lines | The routing hook. Outside the listed files; needed so that Open Project stays one command |
| `tests/test_mat3_materials_study.py` | New | 55 focused tests |
| `tests/test_universal_ui2_clean.py` | Changed, 3 lines | See "One existing test changed" |
| `docs/gui/PROJECT_FORMAT.md` | Changed | Version 2 |
| `docs/materials/MAT_3_REPORT.md` | New | This report |

`materials_status_panel.py` and `project_model.py` needed no change: the material status stays apart, and v2 has its own owner. No
MAT-1 or MAT-2 service, normative document, registration, accepted record or tolerance changed.

## What works in the GUI

| Section | Working behaviour |
|---|---|
| A. Input | a, b, mass or surface mass, thickness, with units. SI values and the ratio min(a,b)/h are shown, with the statement that thinness proves nothing |
| B. Method | Ritz or Stage A, explanation, scope, availability. Choosing a package folder shows its identity, ranges and readiness without loading matrices |
| C. Parameters | Known value, start and bounds per parameter; basis degree, modes, HOLDOUT count, sigma |
| D. Observations | Prepare builds and shows the frozen rows with FIT and HOLDOUT, without a fit. Real source: read-only facts and BLOCKED |
| E. Run | Run, Cancel, progress in solves, solve and time limits, resource table, reasons for refusal |
| F. Results | Three separate statuses, parameter, frequency, iteration, rank, HOLDOUT, leave-one-family-out, convergence and uncertainty tables, two plots, Save, Open |

Ritz needs no ODB. Stage A without a compatible package gets the workflow's own refusal, with no Abaqus and no fallback to Ritz. A
worker thread does all the work and touches no widget. Run, Prepare, Open and Save share one slot, so two jobs cannot overlap.
Closing the window cancels the worker and waits up to 5 s for it.

Each synthetic example is computed when requested: known values give the observations, the start values differ, and the fit runs.
The Ritz example solves its own model at the known values. The Stage-A example uses a diagonal matrix fixture with a closed-form
solution and writes a SYNTHETIC package to a temporary folder for that run.

## Two methods: numerical results

Default examples, Python 3.11.17, numpy 2.4.6, scipy 1.17.1, Windows, one BLAS thread. Status of both:
`COMPLETED`, `CONVERGED`, `DIAGNOSTIC_OPTIMIZER_CANDIDATE`, `NOT_A_RELEASE_VALUE`.

| Method | Parameter | Start | Found | Known | Statistical sd |
|---|---|---|---|---|---|
| Ritz, 119 solves | D11 | 13 | 12.0001 | 12 | 0.00153 (ln) |
| | D22 | 6.5 | 7.00009 | 7 | 0.00175 (ln) |
| | D66 | 2.5 | 2.30006 | 2.3 | 0.00173 (ln) |
| | u | 0.10 | 0.149767 | 0.15 | 0.0104 (absolute) |
| | D12, derived | 0.65 | 1.04838 | 1.05 | not propagated |
| Stage A, 86 solves | D | 0.34 | 0.36 | 0.36 | 0.00128 (ln) |
| | D66 | 0.046 | 0.05 | 0.05 | 0.00207 (ln) |
| | r | 0.05 | 0.09 | 0.09 | 0.000591 (absolute) |

Solve counts and values match the MAT-2 report. Ritz: rank 4, condition 8.93, objective 4848 to 7.3e-4, largest frequency error
after the fit below 0.003 %. A test confirms the page's result hash equals a direct call of the workflow with the same declaration.

Other outcomes seen on the page: no, missing, damaged or wrong-model package gives `PACKAGE_REFUSED`; a package stating physical
evidence gives `EVIDENCE_KIND_MISMATCH`; a square plate at D11 = D22 gives `UNRESOLVED_MODAL_CLUSTER`; a solve limit of 12 gives
`BUDGET_EXHAUSTED` and no candidate.

## Save and open

`.mcproj` v2 is a separate version; see `docs/gui/PROJECT_FORMAT.md`. v1 is still what `read_project()` and Analyze read, its check
did not change, and the existing test that v1 refuses a v2 manifest passes unedited.

| Check | Result |
|---|---|
| Save then open, both methods | Every table identical; floats identical; form restored |
| Opening | No build, no workflow call, no package opened, even when the file names one |
| Status | Altered release status, evidence, intent, study identity, restrictions, or unknown fields: refused |
| A refusal rewritten as a candidate, hashes recomputed | Refused |
| Damaged or foreign file | Refused; what was shown stays |
| Failed or cancelled write | Old file intact, no temporary file left |
| A path named in the file as the target | Refused, not overwritten |
| Old v1 project | Opens on Analyze with the same document; Materials refuses it by version |
| File > Open Project with a v2 file | Goes to Materials; Analyze is untouched |

**Decision for review:** a v2 file holds Materials results only. An Analyze result stays in its own v1 file, so synthetic and real
data never share a project. The planned "v2 Materials member" could also mean one combined file; that was not built.

## Read-only inventory of `I:\sandwich`

Only listing to depth 2, two UNV files, `Read me.txt` and one project were read. Nothing was changed, moved or copied: size and
modification time of each read file were compared and are unchanged. No ODB, INP or CAE was opened, the workbook was not opened,
and the disk outside this folder was not searched. The existing importer wrote one 58 KB entry to the program's usual cache under
`%LOCALAPPDATA%\AbaqusModalComparator\cache`, outside `I:`.

| Subfolder, by content | Role |
|---|---|
| `exp` | Experimental UNV files, `Read me.txt`, one workbook |
| `ABM` | One saved project of this program |
| `Abaqus Results` | Abaqus jobs and models in `temp`, about 1030 entries, and a few subfolders |

**Experimental candidates of the single plate**, in `I:\sandwich\exp\SPname_files_ROTATED_261103\`. The sign of belonging is only the
name `300by300_plate_only_1mm_ROTATED`, and the PolyMAX file names the FRF file's project as its model. This does not establish
the orientation, test conditions, date or thickness.

| | `300by300_plate_only_1mm_ROTATED_Polymax_261027.unv` | `300by300_plate_only_1mm_ROTATED_261027.unv` |
|---|---|---|
| Size | 421 096 bytes | 31 383 254 bytes |
| SHA-256 | `76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d` | `d3bc99e9d0fd8261fd878b83fc8eec8b27206cec23eeea240d2a3cd7712b9878` |
| Datasets | 55, 82, 151, 164, 2411 | 58, 151, 164, 2411, 2412 |
| Data type | **Fitted modes** (dataset 55, set `Polymax_bravo`) | **FRF peaks**, not fitted modes (289 FRF channels) |
| Records | 11 | 22 |
| Frequencies (Hz) | 18.631, 54.619, 63.495, 66.847, 74.215, 112.266, 145.936, 157.851, 169.185, 180.136, 191.602 | 3.44, 10.31, 12.50, 18.75, 54.69, 63.44, 67.19, 74.06, 112.19, 122.19, 145.94, 157.81, 169.06, 180.00, 191.56, 281.88, 327.19, 338.44, 365.94, 413.13, 460.63, 485.63 |
| Excluded by the importer | Residuals below 14.9036 Hz and above 240.9527 Hz | None |
| Shapes | Complex, 289 points | Complex, 289 points |
| Measured DOF | Z only, at all 289 points | Z only, at all 289 points |
| Stated units | `USER_DEFINED`, code 9, length scale 1.0 | `METRIC_ABS_(SI)`, length scale 1.0 |

Both files have the same geometry: X from -0.18929 to 0.20227, Y from -0.20264 to 0.18891, Z constant at -1.15, so each axis spans
about 0.3916. **That frame is not the plate-centred material frame**, its span does not by itself fit the 300 in the name, and the
angle is not stated. No physical registration was found or chosen, and none was derived from MAC. The low FRF peaks are listed, not
excluded or explained. The other UNV files in that folder carry SP04, SP05, SP10 or SP13 in their names and were not read.

`Read me.txt` describes rotated and original suspension setups and PolyMAX processing for sp04, sp05, sp10 and sp13. It does not
name this plate. `Experiment_Freq_damping_LMS_Rotated_final.xlsx` (20 760 762 bytes) was not opened, so its relation is UNKNOWN.

**Saved projects:** none for the single plate. The only project, `I:\sandwich\ABM\SP04_CFRP_E1=E2.mcproj` (5 208 923 bytes, SHA-256
`61fd245726de40f2a76f234a57cb311d08a74774b819051a4f55fc4138085abd`), is format v1, saved 2026-11-04, `REGISTRATION_REQUIRED`, no
registration, 16 FE modes and 18 FRF-peak records. It belongs to SP04 and is a historical snapshot; it is not used.

**Abaqus results with a possibly related name**, in `I:\sandwich\Abaqus Results\temp\`, by file name only. Nothing connects any of
them to the UNV files: `Carbon_plate_T300_freefree`, `CFRP_C3D8I_0875_FreeFree`, `CFRP_S4R_0875_FreeFree`,
`CFRP_S4R_WEDGE_FreeFree`, `PlateG15000`, `Plate-15degree`, `Plate-30degree`, `Plate-45degree`, `CFRP_TWILL_FREEFREE_M40` and `M60`,
`CFRP_TWILL_M80`, the `CFRP_TWILL_SENS_*` series, `CFRP_PLAIN_520_STAGEA.inp` (INP only), `plate.cae`, `t300carbonplate.cae` and
`t300carbonplate_27gramm_0.235mm.cae`. No Stage-A matrix package was looked for or found.

## Limits with real measurements

- **Real-data inverse execution stays BLOCKED** in the workflow and on the page. No note text, setting or file enables it.
- Before any real study, the owner would need to decide at least: which series this is, the physical registration into material
  axes, a, b, mass and thickness with sources, the covariance, and the FIT and HOLDOUT plan.
- **The Ritz backend takes coordinates in the plate-centred frame**, and these files are not in it. The page has no registration
  input, by design at this stage.
- **`SYNTHETIC` is a declared label.** A hand-edited project with measured values, a SYNTHETIC label and consistent hashes would not
  be detected. No path in the program builds one.
- A chosen package can only be read for its facts, or run against the built-in example's identity. `.mtx` conversion and ODB matrix
  extraction are not built.

## Other limitations

- **Cancel works between forward solves.** One long solve cannot be interrupted. There is no hard process kill, since the worker is
  a thread. If a worker outlives the 5 s on closing, it is a daemon thread and its outcome is dropped.
- **Memory is an estimate before the start**, plus the backend's own limits. It is not a measurement of the process.
- **The program does not force one BLAS thread.** The tests do, through the environment.
- **The Stage-A example is a diagonal fixture,** so it tests the adapter and the page, not a plate.
- **Observations for the Ritz example** take their frozen identity from a MAC comparison between the known and start states, once,
  before the study, as the MAT-2 tests do. That is building a known synthetic declaration; the fit does not use MAC.
- **Plots** are static pictures redrawn from saved values. The tables hold the same numbers.
- **`docs/gui/GUI_UX_R1.md`** still says no optimizer was added. It describes that stage and was left as history.
- **Not seen on a real display.** The page was checked offscreen, including rendered pictures. The owner's manual check remains.

### One existing test changed

`tests/test_universal_ui2_clean.py` forbids words such as "plate", "Stage" and "Auto-ID" anywhere in the window. The section you
specified must name the methods, their scope and the restrictions, so the scan now skips that one section. It still covers the
rest of the window. This narrows a text-cleanliness test and touches no scientific rule. Please review it.

## Tests

Final code, Python 3.11.17, offscreen Qt, sequential, one process per line, one BLAS thread:

| Module or classes | Tests | Result |
|---|---|---|
| `test_mat3_materials_study` | 55 | PASS |
| `test_universal_ui2_clean`: Materials, Navigation, Separation | 9 | PASS |
| `test_gui_ux_r1`: Materials, SourceGuards | 8 | PASS |
| `test_plate_material_workflow` | 78 | PASS |
| `test_spec_v1_2_normative` | 6 | PASS |
| `test_spec_v1_2_policy_draft` | 16 | PASS |
| `test_v12_i1_campaign_question` | 19 | PASS |
| `test_working_draft_r2_project.DamagedFileTests` | 10 | PASS |

201 tests, 0 failures, 0 skipped.

**NOT_RUN:** full suite; other classes of the listed GUI modules; `test_working_draft_r2_project.MenuTests`, stopped by my budget
guard; Abaqus; real-data fitting.

**Known FAIL, not caused by MAT-3:** `test_new_gui1_workspace.SeparationTests.test_the_new_gui_imports_only_its_own_modules_and_the_read_only_services`
stops at its fixed list of files, which already lacks `review_model.py` and others at the base commit. MAT-3's new modules are also
not on that list. Its import whitelist would need the same update, and I left it alone, as GUI repair is out of scope.

**Budget: exceeded.** About 317 s of the 300 s limit in test runs, plus about 20 s of offscreen rendering and layout probes. The
overrun came from the last run, where one project test class took 52 s. No further test was started after that.

Mapping of the required checks: 1, 2 `TwoMethods`; 3 `WrongPackages`; 4 `test_each_method_calls_the_shared_workflow_once`;
5 `test_the_tables_hold_the_computed_values`, `test_ritz_from_the_button_to_the_tables`; 6, 7 `RunControl`; 8
`test_a_real_file_on_the_page_does_not_enter_a_synthetic_test`, `test_nothing_that_builds_a_study_takes_measured_data`; 9
`RealDataStaysBlocked`, `RealSource`; 10 `SaveAndOpen`; 11 `test_an_old_project_still_opens_on_analyze_unchanged`; 12
`ReleaseStaysRefused`, `test_a_file_cannot_raise_its_status`.

## Preservation

Original files on `I:` are unchanged and were not copied. The 25 untracked items in the working folder were not touched. SPEC,
DECISIONS, ROADMAP, STATUS, registrations, accepted evidence and thresholds did not change. Existing pages keep their behaviour in
the classes run above; Analyze gained only the routing hook.

## Artifacts

Outside the repository, in `D:\git\abaqus-modal-comparator-work\research\MAT_3\`: `final_targeted.log`, `final_code.sha256`,
`inventory.json`, `baseline_gui_subset.log`, `workspace_inventory.log`.

## Final SHA and CI

Recorded after the push of the implementation commit.
