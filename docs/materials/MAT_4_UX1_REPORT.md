# MAT-4.UX1 report: Materials GUI overhaul

Status: **MAT-4.UX1 REVIEW_READY**. Not self-accepted. The owner's visible Windows check is **NOT_RUN**.

For the owner and the reviewer. Base and parent: `d2bd6ea125117e798762d0625c4e474758b6a4e5`; branch `feature/materials-offline-v1`;
`origin/main` `0bea1de68dc346d20958e6f53a9e1d634a870f5d`. The final SHA and its CI state are in the hand-over, since a file cannot name the
commit that contains it.

M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged. Real-data inverse execution stays BLOCKED. No
Abaqus run, FE calculation, real-data fit or material release took place.

## Before and after

**Before:** one page with sections A to F, then the file facts, about ten full-width tables in a row, and two plots fixed at 480 pixels wide.

**After:** five tabs. Only a very short window scrolls the whole page.

| Tab | Holds |
|---|---|
| Расчёт | Method, data, plate, `Запустить расчёт`, `Отмена`, progress and status. All other settings are under a closed `Расширенные настройки` |
| Результаты | Status codes, a five-line summary, `Сохранить результат`, `Открыть результат`, the parameter table, frequencies and HOLDOUT |
| Графики | Two large plots and `Сохранить график (PNG)...` |
| Диагностика | Eight named groups that open and close, with short explanations. One is open at the start |
| FE / Эксперимент | ODB and UNV/UFF selection, reuse from Analyze, read-only facts, input properties, material status and limits |

## Usability changes

- **Results open by themselves** after a run or an opened file. A cancelled run stays on Расчёт and says so; a form that cannot be built also
  stays there, with the reason.
- **Each method shows its own inputs.** Stage A shows no geometry or mass, and its package choice is under the advanced settings.
- **Advanced settings keep working.** They keep their values across closing and tab changes and reach the same workflow. A test sets a solve
  limit of 12 with the section closed and gets `BUDGET_EXHAUSTED`. A mistake in a closed field is reported on the Run screen.
- **Results state their meaning once,** in short Russian, with the exact code beside each sentence.
- **Older results are marked.** Changing a setting says the result belongs to the previous settings; a saved result says it is saved.
- **Tiny errors keep their size and sign.** The value that read `-0.0000 %` now reads, for example, `-3.00e-07 %`. Values from 5e-5 % up keep their
  earlier four-decimal form.
- **Terms are explained** in tooltips and section texts: MAC, HOLDOUT, rank, sigma and uncertainty.

## Plots

- **Drawn from the numbers.** Each plot is drawn at the width it is shown and the screen's own scale, and again after a resize or a move to
  another screen. The fixed `PLOT_WIDTH` and the scaling of a small picture are gone.
- **Measured pixels.** The objective and error plots at a width of 1102 logical pixels gave 1102, 2204 pixels at 100 % and 200 %; at 636 logical
  pixels and 150 %, 954. A test also runs a real process with `QT_SCALE_FACTOR=2`.
- **Saved plots** are drawn anew at 3200 x 1800 pixels, whatever the window size.
- **Error plot:** signed error of the model against the observation, as two panels, before and after the fit. Each has its own scale, stated on
  its axis and in its title, since residuals after the fit are far smaller. Zero is in the middle and marked. Bars carry values when there is room.
- **FIT and HOLDOUT** differ by colour, hatching, a band and the legend. The two colours passed the palette check, including colour blindness.
- **Objective plot:** the same points as before, on a log scale, with the first and last values labelled.

## Files

| File | Why |
|---|---|
| `src/new_gui/materials_study_panel.py` | Tabs, summary, sections, `PlotView`; the run, cancel, save and open logic is kept |
| `src/new_gui/materials_workspace.py` | Tab bar, fifth tab, Russian text |
| `src/new_gui/materials_study_model.py` | Russian labels, summary and error rows, plots drawn to a size. No calculation changed |
| `src/new_gui/materials_workspace_model.py`, `materials_status_panel.py` | Russian labels |
| `src/new_gui/production_window.py` | The page's content fills its height; subtitle |
| `src/new_gui/theme.py` | Tab, section and summary styles |
| `tests/test_mat4_ux1_materials_gui.py` | New, 42 focused tests |
| `tests/test_mat3_materials_study.py`, `tests/test_gui_ux_r1.py` | Expected texts now Russian, one obsolete section check removed. No execution or governance check was removed |
| `tests/test_new_gui1_workspace.py` | `matplotlib.patches` and `matplotlib.ticker` allowed for `materials_study_model.py` only, for drawing |
| `docs/materials/MAT_4_UX1_REPORT.md` | This report |

No file under `src/services` or `src/domain` changed. The F2 test isolation was not touched.

## What did not change

- **Calculations:** the owner's Stage A example gives 86 solves, `CONVERGED`, D = 0.36, D66 = 0.05 and r = 0.09, checked by a test. Ritz gives 119 solves.
- **Workflow:** the same MAT-2 service for both methods, frozen FIT and HOLDOUT, MAC as identity only, safe-point cancel, one job at a time, and no
  widget touched by the worker. The widgets import no numerics.
- **Formats:** `.mcproj` v2 and v1 schemas are unchanged. Reopening recalculates nothing and opens no saved path.
- **Saved text:** the English statement and provenance stay as they are. They are part of saved results, and provenance is in the declaration hash.
  The page shows a Russian statement and keeps the original under Диагностика.
- **Codes:** all machine statuses are unchanged in data, diagnostics and files.

## Tests

Final source code, Python 3.11.17, offscreen Qt, one process at a time, one BLAS thread. From `tests`: `python -X faulthandler -m unittest <module>`.
The list was fixed before the run.

| Module | Tests | Result | Time |
|---|---|---|---|
| `test_mat4_ux1_materials_gui` | 42 | PASS | 66 s |
| `test_mat3_materials_study` | 55 | PASS | 44 s |
| `test_new_gui1_workspace` | 28 | PASS on the second run, see below | 6 s |
| `test_universal_ui2_clean` | 20 | PASS | 33 s |
| `test_gui_ux_r1` | 79 | PASS | 180 s |
| `test_process_shutdown` | 1 (six cases) | PASS | 14 s |
| `test_plate_material_workflow` | 78 | PASS | 7 s |
| `test_spec_v1_2_normative` | 6 | PASS | 0.1 s |
| `test_spec_v1_2_policy_draft` | 16 | PASS | 0.05 s |
| `test_v12_i1_campaign_question` | 19 | PASS | 5 s |
| `test_universal_two_file_analysis.PrimaryWorkflowTextTests` | 3 | PASS | 0.1 s |
| `test_working_draft_r2_project.MenuTests` | 7 | PASS | 13 s |
| `test_working_draft_r2_project.SaveAndReopenTests` | 9 | PASS | 73 s |

363 tests, 0 failures, 0 skipped, exit code 0.

**Failures on the way:**
- The first `test_new_gui1_workspace` run failed twice, on the two new matplotlib imports. I allowed them for that one module and reran it.
- The new tests found real sideways scrolling, 427 pixels at 900 wide, from the status codes in one row with the buttons, and long section titles.
  Fixed in the layout.
- Viewing the screenshots found a cut plot title, labels against the axis, plate fields shown for Stage A, and `-0.0000 %`. All fixed.

**NOT_RUN:** full suite locally; other classes of `test_working_draft_r2_project`, including `OfflineOpenTests`; a real display.

## Screenshots

Reviewed by me, in `D:\git\abaqus-modal-comparator-work\research\MAT_4_UX1\screens\`, at 1366 x 768, 900 x 700 and 1920 x 1080 at 100 %, 1366 x 768 at 200 %
and 900 x 700 at 150 %. Names give the tab, size and scale, for example `1_run_ritz_1366x768_s1.png`, `2_results_stage_...`, `3_plots_stage_...`,
`3_error_ritz_...`, `4_diagnostics_open_...`, `5_files_...`. The script is `shots.py` beside that folder.

They are offscreen renderings with Segoe UI loaded by the script. **That is not a visible Windows check.**

## Limits

- **Not seen on a real display.** Fonts, real 150 % and 200 % screens and keyboard use remain for the owner.
- **Some English remains:** workflow refusal reasons, the saved statement and provenance, messages from file readers such as `file_problem`, the
  File and Help menus, the sidebar and the page title. The first two are saved scientific text; the others belong to other parts of the program.
- **The real-file summary table** appears only when `Реальный файл: только просмотр` is chosen on Расчёт, since building it asks the workflow.
- **Plots** are not interactive and have no copy command. They are saved as PNG.
- **Changing the method resets the model and observation numbers** to that method's defaults, as before.
- **`MAT_4_REPORT.md`'s manual checklist** uses the older English labels. The list below replaces it.
- **Project formats** stay separate; there is no combined file.
- **Linux CI:** the unit-test step of `d2bd6ea` ended with exit code 134, so isolating the audit hook did not remove the crash. Not investigated here,
  and its log was not read. The cause is still unknown.

## Owner's manual check (NOT_RUN)

1. Start `RUN_NEW_GUI.cmd` and open Materials. The tab Расчёт is short, and the run button is in view.
2. Keep `Метод Ритца`, press `Запустить расчёт`. Результаты opens by itself with the summary and parameters.
3. On Графики, check sharpness and text size. Resize the window, and save a plot.
4. On Расчёт, choose `Матричная модель Stage A`; plate fields disappear. Run it: 86 solves, D = 0.36, D66 = 0.05, r = 0.09.
5. Press `Сохранить результат`, exit, start again, press `Открыть результат`. The same numbers appear with a saved-result note and no run.
6. Open Диагностика and `Расширенные настройки`, and change a value. Результаты then marks the result as older.
7. Press run and then `Отмена`, and close the program during a run. A short run may finish first; report that if it does.
8. On FE / Эксперимент, choose real files. Facts appear, and no fit becomes available.
