# APP-UI.1 — Home screen (2026-10-27)

Branch `feature/app-ui1-friendly-home` from `main` `e47fe75`. A user-interface addition: no scientific rule, MAC,
registration, import, Auto-ID or report changes.

## What the user sees

The window opens on **Home**. A switch at the left of the header changes between **Home** and **Expert mode (all 11
tabs)**.

**Expert mode** is the notebook exactly as before:

- the same 11 tabs, in the same order (1. Files … 11. Scaling);
- no tab added or removed, so every tab index stays valid.

Switching keeps every input, the result, the selected expert tab and the project state (switching does not mark the
project as changed).

Home has four areas, two per row on a wide window and one per row on a narrow one. The page scrolls when the window
is short.

| Area | Shows | Actions |
|---|---|---|
| 1 Source data | the chosen Abaqus results and Simcenter experiment: file name, kind (extracted `manifest.json` needs no Abaqus; an `.odb` is extracted with Abaqus), folder | **Choose...** for each file; **Modal set** list; **All settings...** (opens 1. Files) |
| 2 Analysis readiness | checklist: Abaqus results, experiment, modal set, Abaqus, units, Abaqus mode range; one verdict: *Ready* / *Not ready yet. Still needed: …* / *Wait* / *running* | **Run analysis**, **Stop** |
| 3 Results | plain-language state of the last analysis, with the values of the metric cards of 2. Comparison table | **Frequencies and pairs** (2.), **Mode shapes** (3.), **MAC matrix** (4.) |
| 4 Material properties | material constants: *Not determined* (production Auto-ID `NOT_AUTHORISED`); the identification evidence loaded in this session (records, historical or bound); the Auto-ID selection | **Open the expert Auto-ID section** (9., page 0) |

## One program, not two

Home owns no data and starts nothing of its own.

- **File choice:** **Choose...** calls the same handlers as **Browse** on 1. Files (`_choose_abaqus`,
  `_choose_experiment`). The chosen path is the variable of 1. Files.
- **Modal set:** the list shows the discovered sets of the existing modal-set discovery. A choice calls its handler
  (`_experimental_modal_set_selected`).
- **Run analysis / Stop:** the existing `_start` / `_request_stop`, with the same calibration confirmation and the same
  checks. **Run analysis** on Home is enabled only when Home says *Ready*. When pressed, the existing run checks every
  input again.
- **Locking:** while an analysis runs, **Choose...** and the modal-set list on Home are disabled, like the controls of
  1. Files.
- **Shown values:** every value is read from the window's state when it changes:
  - the input variables;
  - `analysis_state` and `status`;
  - `result`;
  - the diagnostic report source;
  - the metric cards.

  A result that becomes inactive therefore leaves Home at the same moment it leaves the expert tabs. This covers an
  input changed after the analysis, a run whose inputs changed while it ran, a new or opened project, and a stopped
  run.

## Plain language and status

- **Readiness states.** Green ✔ = present. Red ✖ = still needed, and named in the verdict. Amber ⚠ = warning that does
  not block the run. Amber … = wait. Blue ℹ = information.
- **No Abaqus for an `.odb`.** This is a warning, not a block: the run can reuse modes already extracted into the
  output workspace, and an extracted `manifest.json` needs no Abaqus.
- **Two diagnostics, two explanations.** Home tells them apart with the rule of the diagnostic report: the loaded
  data of the analysis have an experimental dataset or not. No new classification is made.
  - *Frequency-only diagnostic* (`FREQUENCY_ONLY_DIAGNOSTIC`): the physical orientation could not be established; no
    mode pairs and no MAC. **Frequencies and pairs** and **Mode shapes** are enabled, **MAC matrix** is disabled.
  - *Experimental data not usable* (`ExperimentalDataUnavailable`): the experimental file gave no usable modal or FRF
    data, with the reason the window has for it. Only the FE frequencies and mode shapes exist. Only **Mode shapes**
    is enabled.
- **Reading files before Run.** Choosing an experimental file reads its list of fitted modal sets (the existing
  modal-set discovery). The analysis itself runs only on **Run analysis**.
- **Material properties.** Home never shows a material property value. The constants are stated as *Not
  determined*, whatever evidence is loaded. Evidence is named as evidence (historical or bound to a model), never as
  an identified value.

## Layout on Windows

- **Fonts and scale.** Fonts follow the existing styles, so **Settings > Interface scale** (80–125 %) applies to Home.
- **Columns.** The column count follows the existing layout width rule (`select_layout_mode` on the logical width):
  two areas per row unless the layout is compact.
- **Wrapping.** Texts wrap at the right edge of their area once the layout has settled after a resize or a scale
  change.
- **Long folders.** They are shortened in the middle (`C:\Users\…\SP02\fe_extraction`).

## Code

- **`src/home_dashboard.py`.** `HomeDashboard` and the plain-language state functions: `readiness_rows`,
  `readiness_verdict`, `result_summary`, `material_summary`. It is built from `ui_workflow.workflow_init`; no new
  `install_*` layer was added.
- **`src/ui_workflow.py`.**
  - `build_home` builds Home in the window's middle row and the switch in the header.
  - `show_view` shows either Home or the notebook (`grid_remove` / `grid`: the notebook is hidden, never rebuilt).
  - `show_expert(tab)` shows the expert mode, on a given tab.

## Validation

- **`tests/test_app_ui1_home.py`.** Uses the real main window, synthetic data, no process. It covers:
  - start on Home and the unchanged 11-tab notebook;
  - switching, which keeps inputs, the result, the tab and the project state;
  - the header switch;
  - files chosen on Home being the files of 1. Files;
  - missing, ready, several modal sets and Abaqus warning states;
  - Run on Home and the input locking;
  - the result summary and the navigation;
  - a stale result removed;
  - the frequency-only diagnostic and the unusable experimental file, each with its own explanation;
  - a new project;
  - material status and evidence;
  - the layout at several window sizes and interface scales.
- **Existing Tk tests of the expert tabs.** Six test modules now switch to the expert mode first (one line per window
  they build), because the window opens on Home.
- **Windows GUI smoke.** `RUN_PROGRAM.cmd`, isolated profile, synthetic data. The program's file dialogs were answered
  by a test hook; no native dialog was opened.
  - Start on Home.
  - Choose the modal set on Home; *Ready*.
  - Run on Home: frequency-only diagnostic shown on Home; **Frequencies and pairs** opens 2. Compare.
  - All 11 tabs.
  - Back to Home; choose another experiment on Home: the result is removed on Home and on 2. Compare.
  - Save the project; close.
  - Restart on Home, with no stale result; 11 tabs; close.
  - No child process; exit code 0.

## Limits

- **Display scaling.** Windows display scaling other than 100 % was not tried on this computer (the interface scale
  80–125 % was).
- **Language.** Home is in English, like the rest of the program.
