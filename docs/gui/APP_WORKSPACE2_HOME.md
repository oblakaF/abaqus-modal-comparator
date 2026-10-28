# APP-WORKSPACE.2 — Current workspace on Home (2026-10-28)

Branch `feature/app-workspace2-home-context` from `main` `c3b4ff6` (PR #111 and #113 merged; CI 40665821825
success). **Status: REVIEW_READY.**

Home gets a compact, read-only panel, **Current workspace**: no number, English only. It is placed after the four
areas and before the specimen passport (`5  Specimen catalogue / Паспорт образца`, unchanged). The panel shows the
program's state through the accepted headless model `services.workspace_context` (APP-WORKSPACE.1, F1).

## Owners of the data shown

| Row | Read from (owner) | Notes |
|---|---|---|
| Working specimen | Home's own choice `working_specimen_choice` / `working_specimen_id` | A separate list from the passport's `specimen_choice`. ID, type and family come from the accepted catalogue only. |
| FE file / Experimental file | `app.abaqus_path` / `app.experimental_path`, the fields of 1. Files | Browse, Use (APP-CATALOG.2) and the input registry all set them. Home refreshes on their existing traces. A file name equal to one recorded for the working specimen is reported as "name only: the file is not verified by this". |
| Modal set | `app.available_experimental_modal_sets` and `app.experimental_modal_set_key` (owner `polymax_ui`) | The name is the `display_name` of the one discovered set whose `key` is the selected key. The formatted choice text ("Bravo (1) — 9 modes") is never parsed. No unique match, or two sets with the same name, gives `NOT_CHECKED` with the reason. The status itself is the workspace model's, against the catalogue. A catalogue status found by the set name in a file of the same name is shown neutrally (ℹ, never ✔) with "Matched by the set name and the file name only; the file content is not verified by this". |
| Analysis | `app.analysis_state`, `app.result`, `app._stale_result_notice` (owner `ui_workflow`, P-1) | Pairs and MAC are shown only for `SUCCESS` with a result on display. Running, stopped, diagnostic, error, stale and discarded states show no pairs and no MAC. The P-1 notice is shown as is. |
| Registration | the result's own records: `governed_registration`, `geometry_verified_registration`, `guided_physical_registration` (owner `runtime_hardening`) | See below. |
| Production Auto-ID | `WorkspaceContext.production_auto_id` → `guarded_execution.PRODUCTION_AUTHORITY` | Always `NOT_AUTHORISED: blocked.`, with the authority's reason. |

**Refresh.** The panel refreshes in `HomeDashboard.refresh()`, which the existing `WATCHED_VARIABLES` traces call.
Changing the working specimen refreshes the panel alone. No `install_*` layer was added.

## Registration: never inferred

A result records the **hash** of the frozen registration it applied, but never its basis
(`RegistrationBasisStatus`). So the panel passes the hash alone, and the model reports it as **UNKNOWN**:
"registration … was applied by …, but its basis is not recorded, so no binding to this working set is confirmed".

- **Catalogue reference.** When the working specimen's catalogue records the hash, that record is added as
  "Catalogue (reference only)". It never makes the kind `PHYSICAL`. The hash of another specimen is not attributed
  and is reported as not recorded for this specimen.
- **No frozen registration** (automatic geometry alignment, no result, a diagnostic, a stale result) gives
  `NONE`. Conflicting records give `UNKNOWN`.
- **The other kinds.** `PHYSICAL`, `LEGACY_REPLAY` and `INCOMPLETE` appear only when a stated basis exists. Today
  the program records none. The panel shows each of the five kinds distinctly (tested with stated contexts).
  - `PHYSICAL` reads "(as stated)" with "cross-reference only, not a verification of the data".
  - `PHYSICAL` is never marked green (✔).
- **No other inference.** A file name, a SHA-256, close frequencies or MAC never imply modal identity, physical
  registration or scientific readiness.

## Unchanged

- **Analysis code.** The analysis, MAC, pairing, export, scientific criteria and Auto-ID are unchanged.
- **Inputs and runs.** Choosing a working specimen changes no input and starts nothing.
- **Passport and local files.** The passport and Locate → Verify → Use of APP-CATALOG.2 are unchanged.
- **Expert mode.** Expert mode (11 tabs) is unchanged.
- **Layout test.** `tests/test_app_ui1_home.py` changes only the expected layout (authorised): the workspace at
  `(2, 0)` and the catalogue at `(3, 0)` in two columns; `(4, 0)` and `(5, 0)` in one. Both span all columns.

## Tests (`tests/test_app_workspace2_home.py`, 15; real main window, synthetic data)

- **Placement and title.** The panel sits between the four areas and the passport; the catalogue title is unchanged.
- **Initial state.** Shown without guessing: no specimen, the program's own file fields, `NONE`, `NOT_AUTHORISED`.
- **Separation.** Choosing the working specimen changes no input, result, state or passport. Viewing a passport
  changes no working specimen. Choosing "(no working specimen)" resets it.
- **Use.** Locate → Verify changes nothing; Use sets the experimental file, and the panel shows it. No analysis is
  started.
- **Result.** Running shows no pairs. A successful result shows its pair count and MAC. After an input change, the
  stale notice shows and no pairs remain. A result discarded while running is never shown.
- **Registration.**
  - A result's hash is `UNKNOWN`, never `PHYSICAL`, with the catalogue record as reference only.
  - Another specimen gets no reference.
  - Conflicting and missing records are handled.
  - All five kinds render distinctly.
- **Modal set.** The name comes from the discovered set object, never the display text. Ambiguity gives
  `NOT_CHECKED`. A non-catalogue file gets no `GOVERNED`. A catalogue status reached by names is never shown as
  confirmed (ℹ), and a wrong set is `NOT_IN_CATALOGUE` (⚠).
- **Unknown data.** An unknown specimen and an unusable catalogue show `UNKNOWN`, and the choice list is disabled.
- **Auto-ID.** It stays `NOT_AUTHORISED` in every state.
- **Home ↔ Expert.** Switching keeps the working specimen, the inputs and the panel; Expert mode keeps 11 tabs.

## Limits

- **Working specimen not saved.** The working specimen is Home's own session choice. It is not saved in projects or
  the session, and it is lost when the program closes.
- **Registration on real data.** Real analyses show only `NONE` or `UNKNOWN`, because no result records a
  registration basis. Recording one belongs to the analysis, outside this task.
- **Registration options.** A registration option chosen but not yet run (accepted physical registration, guided
  registration) is not shown. The panel shows what the result on display applied.
- **File-name matching.** Matching a file to the catalogue is by name only (see APP-WORKSPACE.1).
- **English only.** The panel is English only. The pre-existing Russian words in the catalogue title and
  `UNKNOWN_TEXT` were left unchanged, as instructed.
