# POST-R7 program end-to-end acceptance (APP-E2E.1, 2026-10-23)

This is a program acceptance after R7, not a scientific stage (no M8 / M11 step). It covers four things:

- stabilising the two flaky / order-dependent tests;
- a real Windows launch of the application;
- the documented user path from loading data to the PDF / Excel report;
- the R7 safety behaviour.

No Abaqus solve, no ODB extraction and no Auto-ID / LM fitting were run. No original data store was opened.

**Verdict: `APP_DIAGNOSTIC_E2E_READY`**, with one open program defect (P-1, §6) and the regressions listed as not run
(§5, §7).

**APP-E2E.2 (2026-10-24): P-1 is fixed** (§9). An input change now makes the shown result inactive at once and
disables its export. Verdict of that step: `APP_E2E_P1_READY_FOR_SUPERVISOR_REVIEW`. Sections 1–8 are the APP-E2E.1
record as delivered; only the P-1 status is updated in them.

## 1. Checked state

| Item | Value |
|---|---|
| `main` HEAD | `fb7063ab1342095e24cf3c239e8c865e4e6a618d` (Merge PR #96) |
| PR #96 | closed, merged; head `65e8c3c`; merge commit `fb7063a`. The tree of `fb7063a` equals `65e8c3c` (R7 FINAL), so the R7 FINAL test logs are the `main` baseline |
| CI on `fb7063a` | push run 39941547107: **success** (Run unit tests). It is the only run on that commit |
| Branch | `integration/post-r7-program-smoke` from `fb7063a` |
| R7 status | MERGED; programmatic diagnostics accepted. OD-R7-1 stays open |

## 2. CI stabilisation (test logic only)

| Test | Cause | Fix | Evidence |
|---|---|---|---|
| `test_registration_factory::test_no_full_model_contamination` | Substring search over the serialised registration: `d11` occurred by chance inside the random SHA-256 `registration_hash` (GitHub Actions log of run 39757688944) | Structural check (`full_model_contamination`): every key at every depth by name and word tokens; a string value only when it *is* a forbidden name or embeds JSON. The negative cases are kept: D11, Ex, `basis_km_hash`, stiffness, `material_parameters`, frequency and MAC fields, nested and JSON-embedded. Synthetic positive / negative tests are added | Repeated in fresh fixtures: **new 2400 / 2400 pass**; old logic (`aa08ad9`) 396 / 400 (4 failures) |
| `test_v12_i5_contract_closure::QuestionContractTests::test_a_calibration_pass_does_not_change_the_material_verdict` | Read `FamilyConsistencyTests.campaigns` before the shared campaigns were built. It passed only when `FamilyConsistencyTests` had already run (unittest alphabetical order); it failed under pytest file order and when run alone (`KeyError: (0.02, 1.12)`) | The campaigns are built through `FamilyConsistencyTests.reports()` (which runs its `setUpClass`) before they are used. The asserted conditions are unchanged | Alone, file, class: pass in pytest and unittest |

- **Origin of the first fix.** It is the test logic of PR #95 commit `43fe2e7` only; the file blob is identical
  (`fa9e241`). **The same change is in open PR #95**: when PR #95 is integrated, this file needs no further change, and
  its own commit becomes a no-op for this file.
- **Unchanged.** No production file, threshold, xfail or skip was changed or added.

## 3. Windows application launch (`RUN_PROGRAM.cmd`)

- **Machine.** Windows 10 Pro 10.0.19045; base Python 3.14.6.
- **Clean first launch.** The launch ran with a fresh redirected `USERPROFILE` / `LOCALAPPDATA` / `APPDATA`, so no
  saved session of the user could restore paths to original stores.
- **What `RUN_PROGRAM.cmd` did:**
  - created `.venv`;
  - installed `requirements.txt` (numpy 2.5.4, scipy 1.18.1, matplotlib 3.11.2, Pillow 13.0.0, openpyxl 3.1.5,
    pyuff 2.5.8, pypdf 6.21.2);
  - printed "Program dependencies are ready.";
  - started the main window.

| Check | Result |
|---|---|
| Main window without a Python traceback | **PASS**: the Tk main window "Abaqus–Simcenter Modal Comparator" appeared 86 s after start (including venv creation and installation); console log has no traceback or error; still alive after 28 s |
| Close button (WM_CLOSE) | **PASS**: the process ended within 1 s; `RUN_PROGRAM.cmd` exit code 0 |
| Main tabs open | **PASS**: all 11 tabs (1. Files … 11. Scaling) selected after a real analysis, no Tk callback exception (A1) |
| Input selection | **PASS** for the input fields and modal-set discovery (offered sets: `Polymax_bravo — 10 modes`, `Best — 12 modes`, `bravo-1`). The file dialogs themselves were not clicked: paths are set in the fields the Browse buttons fill |
| Loading / error states | **PASS**: progress, FREQUENCY_ONLY_DIAGNOSTIC, DIAGNOSTIC (experimental file not usable), accepted-registration availability with the reason when unavailable |
| No hang after a failed analysis | **PASS**: damaged UNV ends in 0.2 s with `running = False`; FE modes stay viewable |
| Results cleared after the inputs change | **FAIL (P-1, §6)** in APP-E2E.1: the previous result stays on screen. **Fixed in APP-E2E.2 (§9)** |

- **How it was verified.** The GUI was checked from window captures (PrintWindow), read by the agent, and from the
  widget state. It was not looked at by a human operator.
- **First launch attempt.** It failed because the observer started `cmd` in the wrong working directory ("not
  recognized"). This was a harness error, not a program error, and the launch was repeated with the full script path.

## 4. End-to-end scenarios (real main window, every process start refused)

**Inputs (read only).**

- **V3 copies:** plate PolyMAX UNV `117c893b…`.
- **R6 extraction package:** of the V3 S4R ODB copy.
- **V2 copies:** SP-13 PolyMAX UNV `f2680235…`.
- **CORE-E2E verified copy set:** from `copy_verification.json`, all verified:
  - SP-02 / SP-13 accepted baseline ODBs and the SP-02 UNV;
  - the T3 extraction of `SP13_modal.odb` (the ODB is byte-identical to V2 `befab961…`).
- **Extraction caches:** copied with SHA-256 equality into this run's workspaces, so no Abaqus was needed.

The SP-02 baseline ODB / UNV are not in V2 / V3; they are the earlier verified CORE-E2E copies.

| Scenario | Inputs | Expected | Result |
|---|---|---|---|
| **A1** SP-02, accepted physical registration | CORE-E2E ODB + UNV, set `bravo-1`, FE 6–15 | Accepted registration applied; strict pairs reproduced; report | **PASS** 18 / 19. R1 (exp 2 / FE 8, MAC 0.9176), R2 (4 / 10, 0.9508), R3 (7 / 13, 0.9754): frequencies identical, MAC within 1e-9. Extraction cache reused, 0 processes. 11 tabs open. The **one FAIL is P-1** (input change) |
| **A2** SP-13, accepted physical registration | CORE-E2E ODB + **V2** UNV, set `best`, FE 7–30 | as A1 | **PASS** 16 / 16. R1 (4 / 10, MAC 0.9585), R2 (7 / 13, 0.9469) reproduced |
| **B1** CFRP plate, no physical registration | R6 package (FE 1–20) + **V3** UNV, set `Polymax_bravo` | No pairing, no MAC; frequency diagnostic; R7-A on real data | **PASS** 21 / 22. FREQUENCY_ONLY_DIAGNOSTIC, AMBIGUOUS (8 candidates), MAC not computed, no pair. Modes 1–2 with false 1.0 / 2.0 Hz refused, reason recorded; modes 3–6 kept at their true near-zero values; nearest-frequency rows only for FE ≥ 7. The **one FAIL is P-1** (FE input change) |
| **B2** SP-13, new FE geometry | T3 extraction + **V2** UNV | No registration reuse; frequency diagnostic | **PASS** 17 / 17. FE geometry `b4015d13…` (1 558 721 nodes) is not the accepted `34d69d79…` (1 585 637): no reuse, no MAC |
| **B3** Damaged experimental file | R6 package + damaged UNV (CORE-E2E-D) | Clear refusal, no hang | **PASS** 11 / 11. `EXPERIMENTAL_DATA_NOT_USABLE`, reason stated, FE modes viewable |
| **C** R7 safety | R6 package (real) + synthetic tests | see below | **PASS** |

**Scenario C (R7):**

| Requirement | Evidence | Result |
|---|---|---|
| False rigid-mode frequencies refused | B1 on the real R6 package. Tests: `test_zero_frequency_recorded_as_mode_number_is_refused`, `test_r6_like_package_loads_elastic_modes_without_the_false_rigid_frequencies`, `test_a_package_with_only_false_frequencies_is_refused` | PASS |
| Shell without a confirmed INP / face refused | `test_flat_surface_of_unknown_type_is_refused`, `test_confirmed_shell_without_measured_face_is_refused`, `test_wrong_normal_direction_is_refused`, `test_non_uniform_normals_are_refused`, `test_mirrored_axes_are_refused` | PASS (synthetic) |
| A changed INP or connectivity invalidates a saved registration | `test_changed_fe_input_is_refused`, `test_same_nodes_other_connectivity_is_refused`, `test_same_nodes_other_normals_are_refused`, `test_old_record_without_the_r2_binding_is_refused`, `test_saved_bound_flag_alone_is_not_sufficient` | PASS (synthetic) |
| The worker does not apply a stale registration | `test_an_active_flat_registration_without_its_fe_input_refuses_the_run` (the real `_worker`), `test_a_guided_registration_of_other_files_refuses_the_run` | PASS (synthetic) |

**What the program never did:**

- No orientation and no mode pair was chosen by maximum MAC.
- No Auto-ID was started, and no material value was shown or exported.
- The guided registration was not used: no physical evidence exists for the plate (M11 `PHYSICAL_REGISTRATION_PENDING`).

**Disclosed harness effect.** The scenarios A1, B2 and B3 shared one redirected profile, so they started with the
dialog "Previous session recovered" from the previous scenario. The harness then set its own inputs. The reruns of B1
used their own profile. The first B1 run had a wrong harness expectation (modes 1–6 refused; the package has false
records only for modes 1–2), and the second had an over-strict float comparison of an `.xlsx` value. Both runs are
kept beside the final one.

## 5. Report export (PDF / Excel opened again and checked)

| Scenario | Files | Checks |
|---|---|---|
| A1 | `report.pdf` 14 pages, `report.xlsx` 9 sheets | The Excel report is **cell-for-cell identical** to the accepted CORE-E2E T1 report (all sheets, 0 differing cells); the PDF has 14 pages, as the reference; accepted registration stated; no material / Auto-ID claim |
| A2 | `report.pdf` 13 pages, `report.xlsx` 9 sheets | Identical to CORE-E2E T2 except **one cell**: the experimental path. The V2 copy was used instead of the CORE-E2E copy; both have SHA-256 `f2680235…` |
| B1, B2, B3 | `diagnostic_report.pdf` 4 / 5 / 3 pages, `diagnostic_report.xlsx` | Status FREQUENCY_ONLY_DIAGNOSTIC / FREQUENCY_ONLY_DIAGNOSTIC / EXPERIMENTAL_DATA_NOT_USABLE. MAC `NOT_COMPUTED`, mode pair `NONE` on every row, and no numeric MAC anywhere. No comparator pair status. The banner is present. FE and experimental frequencies equal the loaded data (rel. 1e-14). Only the disclaimer "No material constant is identified or implied" |

An export started after the FE input was changed (B1) still describes the analysed data; every report is a snapshot
of its own inputs. A report is therefore never labelled with the new input. What stays wrong is only the screen (P-1).

## 6. Remaining problems

### Program

- **P-1 (FIXED in APP-E2E.2, §9; medium; pre-existing on `main`, not from R7).** After an analysis, changing the
  experimental file (A1) or the FE input (B1) did not clear the shown result. The table, the metric cards and the
  enabled export buttons stayed as they were, while the status read "Ready to analyze." No wrong report could be
  produced (§5), and the next Analyze cleared everything, but the screen could be read as belonging to the new files.
- **P-2 (minor).** With a mode range that starts at 1, the near-zero rigid modes 3–6 of the plate appear in the
  diagnostic FE list with their true values (≈ 2e-4 – 2e-3 Hz). They never become a nearest-frequency row. The
  Files tab says rigid and near-zero modes are excluded automatically. In the comparison path this holds (A1 excluded
  SP-02 mode 6 by shape projection); in the frequency-only diagnostic list it does not. This is cosmetic, and was not
  further investigated.
- **P-3 (cosmetic, known).** The 11. Scaling tab wraps its text into a narrow column (CORE-E2E open item).
- **Environment note.** `RUN_PROGRAM.cmd` installs unpinned `requirements.txt` versions (here numpy 2.5.4, scipy
  1.18.1). The CI uses Python 3.11 on Linux. The GUI path is verified on Windows / Python 3.14 only.

### Scientific (unchanged, not part of this acceptance)

- **OD-R7-1:** open. `PINNED_EXTRACT_SCRIPT_SHA256` is the CRLF hash.
- **Gates and verdicts:**
  - M8 GATE = NOT_MET;
  - D-077 = NO_GLOBAL_PARAMETER_VALUE;
  - production calibration BLOCKED / NOT_AUTHORISED.
- **Plate:** no physical registration (M11 `PHYSICAL_REGISTRATION_PENDING`), so only the frequency diagnostic is
  admissible.
- **FE model identity:** `FE_MODEL_IDENTITY = NODES_AND_INP_CONTENT`; the INP–ODB connectivity identity is not proven.

## 7. Tests

| Run | Environment | PASS | FAIL | SKIP |
|---|---|---|---|---|
| Two fixes (`test_registration_factory`, `test_v12_i5_contract_closure`), pytest | Windows, Python 3.14.6 | 79 | 0 | 4 (store-gated) |
| Contamination test repeated in fresh fixtures | same | 2400 | 0 | — |
| R7 `test_r7_shell_modal_safety` | same | 41 | 0 | 0 |
| Guided registration / diagnostic report / extraction-cache (GUI and worker paths) | same | 41 | 0 | 1 (store-gated) |
| SP-02 / SP-13 / physical / governed / registration contract / uncertainty / SP-13 readiness | same | 127 | 0 | 18 (store-gated) |
| Loader / extractor / copied bundle | same | 10 | 0 | 0 |
| Full `python -m unittest discover -s tests` | same | 2501 OK | 0 | 96 |
| Full pytest | same | 2440 (+2921 subtests) | **0** | 112 |
| `main` baseline (`fb7063a` = `65e8c3c` tree), R7 FINAL logs | same | unittest 2497 OK; pytest 2435 | pytest **1** (the order-dependent test) | 96 / 112 |
| GitHub Actions, this branch | Linux, Python 3.11 | see the PR | | |

- **The 4 additional unittest tests** are the structural contamination tests.
- **Store-gated tests are `NOT_RUN`.** They need the original stores `snadwich`, `carbon-project-archive`, `sumin`
  and M7 run A / B, which may not be opened. The affected regressions are:
  - SP-02 / SP-13 reconstruction;
  - production-input and strict-freeze reproductions;
  - archived shapes;
  - the guided new-SP-13-mesh test.

  They are **not claimed as passed**. The real SP-02 / SP-13 GUI scenarios (A1, A2) ran on verified copies only.

## 8. Decision

The diagnostic mode of the application is **practically usable**:

- it launches cleanly by the documented route;
- the accepted SP-02 / SP-13 comparisons reproduce their accepted pairs and reports exactly;
- missing physical registration, a new FE geometry and a damaged file all end in a stated, exportable diagnostic
  without pairing or MAC;
- the R7 guards act on real and synthetic data.

The one program defect found (P-1) affects what the screen shows after an input change, not any computed or exported
result. It should be fixed in a separate, authorised program step. (It was fixed in APP-E2E.2, §9.)

Not covered here: the store-gated real-data regressions (`NOT_RUN`), and any human visual inspection of the GUI.

Local evidence: the work root's `runs/post_r7_smoke` holds the scripts, logs, screenshots, `results.json` per scenario,
reports and `export_verification.json`. It is machine-local and not in Git.

## 9. APP-E2E.2 (2026-10-24): P-1 fixed

**Verdict: `APP_E2E_P1_READY_FOR_SUPERVISOR_REVIEW`.**

### Behaviour

After an analysis, a change of any input that defines the computed result makes the shown result inactive at
once. This holds for an established comparison (pairs and MAC) and for a FREQUENCY_ONLY_DIAGNOSTIC or an
unusable-experiment diagnostic.

- **What is cleared:** the comparison table, the metric cards, the plots and the mode views (FE and experimental).
- **What is disabled:** the PDF / Excel / export-all buttons. The Reports menu answers "Run the analysis first".
- **What the user sees:** the status and the cleared panels say *"Inputs changed after the analysis: the previous
  result is no longer active and cannot be exported. Run the analysis again."*
- **What is kept:** reports already written stay on disk. The next successful analysis shows its result and enables
  the export again.

**The inputs that count:**

- the FE file and the experimental file;
- the first and last mode;
- the modal set;
- the calibration fields: the model and experimental units, the unit source, the mapping mode, the custom scale, the
  camera-grid dimensions and coverage, and the provenance;
- the accepted-registration option, the applied guided registration and its FE input, and a confirmed orientation.

**Not counted** (the result is kept): the workspace, the Abaqus command and display preferences. Choosing the same
experimental file again also keeps the result when it has a single modal set. When it has several sets, the set must
be chosen again, so the result becomes inactive.

**Other paths:**

- **Changes during a run.** An outcome whose inputs changed while it ran is discarded when it arrives: *"Inputs
  changed while the analysis was running: its result was discarded …"*. An input changed and restored before the end
  keeps the result.
- **Projects and registrations.** A new project, opening another project, confirming an orientation and clearing a
  guided registration all make the shown result inactive.
- **Unchanged:** MAC, mode pairing, physical / guided registration logic, the pinned extractor, SPEC, thresholds and
  gates. The worker still receives exactly the values validated at Run.

### Implementation (existing state machinery, no parallel state)

- **Where:** `src/ui_workflow.py`, the final owner of `_start`, `_complete`, `_failed`, `_orientation_ambiguous`,
  `_cancelled` and `_refresh_readiness`.
- **At Run:** `_start` records the input signature of the run, the raw values of the variables above, and traces
  them.
- **On a change:** the trace and `_on_persistent_change` call `_check_analysis_inputs`. On a difference,
  `_invalidate_analysis_result` applies the same reset as a new Run or a Stop:
  - `result` and `cache` are set to `None`;
  - `_clear_result_presentation` and `_set_empty_states` run;
  - the export buttons are disabled and `disable_report_export` runs;
  - the notice is kept by `_refresh_readiness`.
- **When the outcome arrives:** the three completion handlers compare the signature with the current inputs, before
  `_populate` echoes the experimental coordinate unit it read into the unit fields. Afterwards the shown result is
  bound to the displayed inputs, including that echo.
- **While the modal-set list is re-read:** the modal set is compared only once the list is known. Re-choosing the
  same file first clears the set key.
- **Guided registration:** `src/guided_registration_ui.py` `clear()` asks for the same check (one call).

### Verification

| Check | Environment | Result |
|---|---|---|
| New regression tests `tests/test_app_p1_stale_results.py` (real main window, synthetic data, real completion handlers) | Windows, Python 3.14.6 | **14 passed** (+11 subtests) |
| The same tests on the unfixed code (`e0e5768`) | same | **20 failed, 5 passed**. Every P-1 case fails; only the controls pass (settings that do not change the result, an input restored during the run, a cancelled run) |
| GUI / worker / project / guided registration / diagnostic export / R7 / G2c / G2d-1 / polymax / idle state / responsive suites | same | 273 passed, 4 skipped (store-gated) |
| Full `python -m unittest discover -s tests`, three consecutive runs | same | **2515 OK, 96 skipped**, each run |
| Full pytest | same | **2454 passed** (+2932 subtests), **0 failed**, 112 skipped |
| GitHub Actions on the PR #97 head | Linux, Python 3.11 | see PR #97 |

**Real Windows window.** The checks ran in the real main window, on verified copies, with every process start
refused.

| Scenario | Change, then new run | Result |
|---|---|---|
| SP-02 accepted comparison (CORE-E2E copies) | Experimental file → SP-13 UNV (V2); then the SP-02 UNV, set `bravo-1` and the accepted registration again | **27 / 27 PASS** |
| SP-13 accepted comparison (V2 UNV) | Last mode 30 → 29. A new run is not possible without a new extraction (Abaqus) | **21 / 21 PASS** |
| CFRP plate FREQUENCY_ONLY_DIAGNOSTIC (R6 + V3) | FE input → T4 extraction bundle; then a new run on it | **29 / 29 PASS** |

What the window checks showed:

- **SP-02:**
  - after the change: no result, no mode views, no pair rows, MAC card "—", exports disabled, Reports menu "Not ready
    yet", earlier reports kept;
  - after the new run: the accepted pairs R1–R3 reproduced (MAC within 1e-9), new PDF / Excel written.
- **SP-13:** cleared immediately, export disabled, earlier reports kept.
- **Plate:**
  - the diagnostic export is cleared and disabled;
  - the new run's frequencies come from the new FE input (58.145 / 144.70 / 161.04 Hz);
  - its diagnostic PDF / Excel were written, and the earlier reports kept.
- **First plate run:** 28 / 29. A harness tolerance (1e-6) was tighter than the 5-digit frequency printed in the
  manifest. It is kept beside the final run.

**Found and fixed during verification:**

- **Completion echo.** The first implementation also reacted to the completion's own echo of the experimental
  coordinate unit (`_populate`). This would have discarded every new result; the new tests found it.
- **Multiple Tk windows.** Tk variables are read through their own interpreter. With several Tk windows in one
  process, `root.globalgetvar` read nothing.
- **Test teardown.** One full unittest run aborted with "Tcl_AsyncDelete: async handler deleted by the wrong
  thread". The new tests had left background discovery / pre-check threads holding a window. The test teardown now
  joins those threads, destroys the window and collects garbage on the main thread. The three following full runs
  are clean.

### Still open

- **Program:** P-2 and P-3 (unchanged, not in scope).
- **Not run:** the store-gated real-data regressions remain `NOT_RUN` (§7).
- **Scientific:** OD-R7-1 is open; M8 GATE NOT_MET; D-077 NO_GLOBAL_PARAMETER_VALUE; production calibration
  BLOCKED / NOT_AUTHORISED.
