# MAT-4 report: stabilization and owner handoff

Status: **REVIEW_READY**. Not self-accepted. The owner's visible Windows check is **NOT_RUN**.

For the reviewer and the owner. Base: accepted MAT-3.F1 `5f398e85f8368a0fd5358801de1a01e8922407a8`; branch
`feature/materials-offline-v1`; `origin/main` `0bea1de68dc346d20958e6f53a9e1d634a870f5d`. The final SHA and its CI state are in the
hand-over, since a file cannot name the commit that contains it.

M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged. Real-data inverse execution stays
BLOCKED. No Abaqus run, FE calculation, real-data fit or material release took place.

## Result

All 15 baseline failures were reproduced locally, and each has a cause and a fix. **No production code changed:** in every case the
accepted behaviour was correct and the test was out of date.

**The `bool_dealloc` crash is not resolved.** It did not reproduce on Windows, its cause is unknown, and this report does not claim a
clean shutdown on Linux. A new test now runs small shutdown cases on CI.

## Files

| File | Why |
|---|---|
| `tests/test_local_experimental_preview.py` | Helper follows the renderer's real arguments; new display-only test |
| `tests/test_local_fe_preview.py` | The same for FE |
| `tests/test_generic_single_plate_workbench.py` | Copy Image and Save PNG allowed as one named row; a width check that detects a wide row |
| `tests/test_new_gui1_qt.py` | Exact button list includes the accepted commands; all are still disabled at start |
| `tests/test_new_gui5_qt.py` | The same, and the image commands are disabled before any drawing |
| `tests/test_new_gui1_workspace.py` | Reviewed file and import lists; two checks stricter than before |
| `tests/test_process_shutdown.py` | New: small processes must end normally |
| `docs/materials/MAT_4_REPORT.md` | This report |

## Baseline failures

The archive `mat3_f1_5f398e8_ci_logs.zip` was not available to me: no such file was attached to the session or found in the folders
searched. **Its SHA-256 was not verified and its logs were not read.** The failures and the crash are taken from the task text, and
the 15 failures were reproduced locally at the base.

### Eleven preview errors: `too many values to unpack`

**Cause: outdated helpers.** GUI-UX-R1 added the optional `display` argument to `render_viewer_mode`, and both services pass it as a
sixth positional argument. The helpers unpacked five.

**Fix:** they unpack six and check the rest explicitly: one call only, no keyword arguments, the target folder, and that `display`
reaches the renderer as the very object given. All earlier checks stay.

**Added:** one test per service. With rotation and mirror, the picture changes, while the mode's number, frequency, values, node IDs,
coordinates, view fields and text lines stay identical.

### Two button lists

**Cause: outdated lists.** Each shape view gained Copy Image and Save PNG in GUI-UX-R1-F1, at the owner's request.

**Fix:** the exact ordered lists now name them. The checks that nothing is enabled at start, that choosing files enables nothing and
that neither command ran are unchanged.

### Layout

**Cause: outdated rule.** "No row of two buttons" conflicts with the accepted row.

**Fix:** only an `ImageActions` row may hold two buttons, and exactly these two. Any other row still holds at most one. New check: with
the page shown, hiding both rows does not change the minimum width of the step pages, so these commands do not set the page's width.

**Checked by breaking it:** a row forced to 2000 wide fails with `476 != 2068`, and a third button in the row fails. My first versions
of the width check did not detect the wide row, and I replaced them.

**Seen while measuring, not changed:** in the older research window at 900 wide, here and offscreen, the page scrolls sideways by 160.
Its tab bar sets a minimum of 636; the step pages need 476. This is not caused by these commands.

### Module separation

**Cause: outdated inventory.** Nine modules were missing: `analyze_summary`, `mac_points_model`, `mac_points_panel`,
`materials_study_model`, `materials_study_panel`, `materials_workspace`, `materials_workspace_model`, `review_model`, `review_panel`.

**Fix:** I reviewed the imports of each and named it in the list, which stays exact. Only four needed new import permissions, per module:

| Module | Allowed | Use |
|---|---|---|
| `review_model.py` | matplotlib, numpy | Drawing loaded values |
| `mac_points_model.py` | matplotlib, numpy, `modal_scaling` | Drawing; display scaling of a pair |
| `materials_study_model.py` | matplotlib, numpy, scipy, the plate problem and workflow modules | The one adapter over the shared workflow |
| `materials_study_panel.py` | `domain.plate_material_problem` | One refusal type |

**Two checks are stricter than before:**
- A whitelist entry `services` let `from services import anything` pass. The nine modules now have exact lists of what they take from
  that package.
- New: `run_plate_inverse_study` is used only in `materials_study_model.py`, and `execute_study` only in `materials_study_panel.py`.

The older checks are unchanged, including the ban on `subprocess`, `abaqus_bridge`, Tkinter and `install_*`.

## Python finalization crash

**Unknown:** the cause. It may need Linux, the full suite, or something not checked here. No cause is claimed.

**Known from the evidence I have:**
- The task records `bool_dealloc` after the full CI suite at `5f398e8`.
- At the earlier commit `52e296c`, the Qt step, which runs only `test_new_gui1_qt`, ended with exit code 134. That hints at a small case
  on Linux, but I have not seen its log, so it is not proof.
- The message generally means that `True` or `False` lost too many references, which [CPython's check](https://bugs.python.org/msg400728)
  attributes to refcount bugs in C extensions. This describes the message, not this crash. One web search found no matching PySide6
  report, and no dependency was changed.

**Checked on Windows, Python 3.11.17, PySide6 6.12.0, offscreen. No crash and no drop that points to a cause:**

| Check | Result |
|---|---|
| 25 single Qt operations, 2000 times each: signals with bool, clicks, event filters, overrides, timers | True change 0; False change 0 to +5 |
| `test_new_gui1_qt`, count before and after each test | No sustained drop; one single -1; exit code 1 from the then-failing test, no crash |
| Program window built and closed 4 times | Counts rise slightly, no drop |
| Application only; older and program windows, closed or left open; `app.quit` | Exit 0, stderr empty |
| Materials worker: waiting at close, cancelled, outliving the window, left at exit, in numpy at exit | Exit 0, stderr empty |

**No lifecycle defect was demonstrated, so no lifecycle code changed.** I read the close paths of both windows and the Materials and
shape workers. Other panels' workers were not exercised. There is no Linux environment here, and I ran no full suite to chase this.

**New test:** `test_process_shutdown` runs six of these cases as separate processes and checks the exit code and stderr. It fails on an
abort, a nonzero exit and a fatal-error message, each confirmed by a deliberately broken case. If a case crashes on CI, the test will name
it and show the stack, so it may add a failure identity. If all pass there, the crash needs more than these cases.

## Tests

Final test code, Python 3.11.17, offscreen Qt, one process at a time, one BLAS thread. The list was declared before the run.

**Regressions first:** the 15 baseline tests, their classes and the new tests: 21 tests, OK, 29 s. The layout test was then changed as
above, so its final result is in the module run below.

| Module | Tests | Result | Test time |
|---|---|---|---|
| `test_local_experimental_preview` | 25 | PASS | 33 s |
| `test_local_fe_preview` | 19 | PASS | 22 s |
| `test_generic_single_plate_workbench` | 47 | PASS | 12 s |
| `test_new_gui1_qt` | 18 | PASS | 21 s |
| `test_new_gui1_workspace` | 28 | PASS | 4 s |
| `test_new_gui5_qt` | 12 | PASS | 37 s |
| `test_process_shutdown` | 1 (six cases) | PASS | 14 s |
| `test_mat3_materials_study` | 55 | PASS | 45 s |
| `test_working_draft_r2_project` | 66 | PASS on the second run, see below | 442 s |
| `test_universal_ui2_clean` | 20 | PASS | 24 s |
| `test_gui_ux_r1` | 79 | PASS | 157 s |
| `test_spec_v1_2_normative` | 6 | PASS | 0.1 s |
| `test_spec_v1_2_policy_draft` | 16 | PASS | 0.05 s |
| `test_v12_i1_campaign_question` | 19 | PASS | 6 s |

411 tests, 0 failures, 0 skipped, each with exit code 0.

**One truncated run:** the first run of `test_working_draft_r2_project` was stopped by my own 400 s process limit (exit code 124) after 61
of 66 tests, with no failure shown. It was not a PASS. I raised the limit and ran it once to completion.

**Coverage of the required items:**
- Both methods, run, cancel and close, save and open of v2 without recalculation, and Analyze v1 compatibility: `test_mat3_materials_study`.
- The previously unrun `MenuTests`: `test_working_draft_r2_project`.
- The three governance modules: the last three rows.

**NOT_RUN:** full suite locally; Linux locally; the owner's visible check; other GUI modules; `test_plate_material_workflow`, whose code
did not change.

## Limits

- **Shutdown:** see above. Unresolved until CI shows otherwise.
- **Project formats:** a Materials-only `.mcproj` v2 and an Analyze `.mcproj` v1 are separate files. There is no combined format, so a
  session's Materials and Analyze results are saved and opened separately.
- **Plan item not done:** the plan's MAT-4 row mentions a numerical comparison against independent published references. This task
  excluded new scientific development, so none was made.
- **Skips on CI:** environment- or store-gated skips are SKIPPED, not PASS.
- **Offscreen is not a visible check.** The earlier limits in `MAT_3_REPORT.md` stand, including the narrowed text scan in
  `test_universal_ui2_clean`.

## Owner's manual check (NOT_RUN)

Run these yourself on Windows; nothing here was automated.

1. In `D:\git\abaqus-modal-comparator`, start `RUN_NEW_GUI.cmd`. The window has Analyze, Review, MAC / Points and Materials.
2. **Ritz.** Open Materials. Keep source `Built-in SYNTHETIC example` and method `KIRCHHOFF_RITZ_4D: thin plate, computed here`. In **E. Run**,
   press **Run**. In **F. Results**, expect the known values recovered and `NOT_A_RELEASE_VALUE`.
3. **Stage A.** Choose method `STAGE_A_MATRIX_3D: prepared matrix package`, package `Built-in SYNTHETIC test package`, and press **Run**.
4. **Save and open.** After each run, press **Save results...** and use two different files. Exit with File > Exit, start again, and use
   **Open results...** for each. The tables must match, with no progress or run shown.
5. **Old project.** Open an existing Analyze v1 project separately with File > Open Project. It must open on Analyze as before.
6. **Cancel.** Press **Run**, then **Cancel** at once. A short run may finish first; that is not a failure, so just report it.
7. **Close.** Press **Run** and close the window with File > Exit during the run. The program must end with no error, and the launcher
   window must not report one.

## Preservation

No original experimental file or saved project was opened or changed. `I:\sandwich` was not read and no ODB was opened. The untracked items
present at the start were not touched. No SPEC, DECISIONS, registration, threshold, frozen evidence, launcher or CI file changed.

## Artifacts

Outside the repository, in `D:\git\abaqus-modal-comparator-work\research\MAT_4\`: `baseline_repro.log`, `step1_regressions.log`, `final.log`
and `final_*.log`, `probe_ops.log`, `ref_gui1.jsonl`, `shutdown_probe.log`, `shutdown_probe2.log`, `mutation_probe.log`, `geom_probe.log`.
