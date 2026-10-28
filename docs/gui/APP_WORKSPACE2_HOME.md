# APP-WORKSPACE.2 — Current workspace on Home (2026-10-28)

Branch `feature/app-workspace2-home-context` from `main` `c3b4ff6` (PR #111 and #113 merged; CI 40665821825
success). **Status: REVIEW_READY** (`5c7b2a3`, then F1).

Home gets a compact, read-only panel, **Current workspace**: no number, English only. It is placed after the four
areas, above the research archive. The panel shows the program's state through the accepted headless model
`services.workspace_context` (APP-WORKSPACE.1, F1).

## F1: a workspace for any data, independent of the laboratory archive

1. **Empty start.** With no FE and no experimental file chosen, the panel shows an empty workspace: "No data loaded
   yet. Choose an FE results file … and an experimental file … to start." It offers **Choose FE file...** and
   **Choose experimental file...**, the same handlers as 1. Files (`_choose_abaqus` / `_choose_experiment`).
   - No SP specimen list is shown by default.
2. **Any data is a workspace.** As soon as one file is chosen, the workspace rows are shown for any supported
   FE / UNV / UFF file, whether or not the archive records it.
   - **Specimen name** is an optional free-text label of the user's (Home's own `specimen_name`).
   - The label is never looked up in the archive: the context is built with no archive specimen
     (`specimen_id=None`).
3. **Research archive on request.** The specimen catalogue SP-01 … SP-15 (passports, Locate → Verify → Use) is
   shown only after the explicit **Open research archive...**; **Close research archive** hides it again.
   - Its data and records are unchanged; its title `5  Specimen catalogue / Паспорт образца` is unchanged.
   - A passport chosen there stays chosen while the archive is hidden.
4. **A new measurement is not an error.** A new UNV, for example a re-measurement of SP-02, is shown like any other
   file. Nothing of the archive is attributed to it: no archived modal-set status (`GOVERNED` / `OTHER` / …), no
   physical registration, no scientific status. This holds even when the user types "SP-02" as the label, or when
   the file has an archived file name.
5. **No templates.** Templates are not created now. In future they are to be created by the user from a loaded and
   analysed project, not shipped as preset specimens.

## Owners of the data shown

| Row | Read from (owner) | Notes |
|---|---|---|
| Specimen name | Home's own `specimen_name` (an Entry) | Optional; a label only. |
| FE file / Experimental file | `app.abaqus_path` / `app.experimental_path`, the fields of 1. Files | Set by Browse, Use (archive) and the input registry; Home refreshes on their existing traces. The path is shown; it is not compared with archive names. |
| Modal set | `app.available_experimental_modal_sets` and `app.experimental_modal_set_key` (owner `polymax_ui`) | See *Modal set* below. |
| Analysis | `app.analysis_state`, `app.result`, `app._stale_result_notice` (owner `ui_workflow`, P-1) | Pairs and MAC are shown only for `SUCCESS` with a result on display. Running, stopped, diagnostic, error, stale and discarded states show no pairs and no MAC. The P-1 notice is shown as is. |
| Registration | the result's own records: `governed_registration`, `geometry_verified_registration`, `guided_physical_registration` (owner `runtime_hardening`) | See *Registration* below. |
| Production Auto-ID | `WorkspaceContext.production_auto_id` → `guarded_execution.PRODUCTION_AUTHORITY` | Always `NOT_AUTHORISED: blocked.`, with the authority's reason. |

**Modal set.**
- **Source of the name.** It is the `display_name` of the one discovered set whose `key` is the selected key. The
  formatted choice text ("Bravo (1) — 9 modes") is never parsed.
- **No unique match** (no match, or two sets with the same name) gives `NOT_CHECKED` with the reason.
- **No archive status.** A selected set reads "selected in the experimental file. It is not compared with the
  research archive, so no archive status is given to it."

**Refresh.** The panel refreshes in `HomeDashboard.refresh()`, which the existing `WATCHED_VARIABLES` traces call,
and when the label changes. No `install_*` layer was added. Hidden parts (the empty state, the details, a closed
archive) are not waited for when Home wraps its texts.

## Registration: never inferred

A result records the **hash** of the frozen registration it applied, but never its basis
(`RegistrationBasisStatus`). So the panel passes the hash alone, and the model reports it as **UNKNOWN**:
"registration … was applied by …, but its basis is not recorded, so no binding to this working set is confirmed".

- **No archive lookup.** The user's data is not compared with the archive, so no archive record of the hash is
  added.
- **No frozen registration** (automatic geometry alignment, no result, a diagnostic, a stale result) gives `NONE`.
  Conflicting records give `UNKNOWN`.
- **The other kinds.** `PHYSICAL`, `LEGACY_REPLAY` and `INCOMPLETE` appear only with a stated basis. Today the
  program records none. The row renderer keeps all five kinds distinct (tested with stated contexts).
  - `PHYSICAL` reads "(as stated)" with "cross-reference only, not a verification of the data".
  - `PHYSICAL` is never marked green (✔).
- **No other inference.** A file name, a SHA-256, close frequencies or MAC never imply modal identity, physical
  registration or scientific readiness.

## Unchanged

- **Analysis code.** The analysis, MAC, pairing, export, scientific criteria and Auto-ID are unchanged.
- **File choice.** Browse, Home ↔ Expert and Expert mode (11 tabs) are unchanged.
- **Archive.** Locate → Verify → Use is unchanged inside the research archive.
- **Tests changed only for the new behaviour; no check removed or weakened:**
  - `test_app_ui1_home.LayoutTests` checks the exact set of placed cards with the archive closed and open: the
    workspace at `(2, 0)` / `(4, 0)`, the catalogue at `(3, 0)` / `(5, 0)` when open;
  - `test_app_catalog1_home.HomeCatalogueTests` and `test_app_catalog2_home.HomeLocalFileTests` open the archive
    explicitly (catalog1 also asserts it is closed before), then run their unchanged checks.

## Tests (`tests/test_app_workspace2_home.py`, 14; real main window, synthetic data)

- **Empty start.**
  - The empty state and its two Choose buttons (the 1. Files handlers) are shown.
  - No SP list and no archive are shown.
- **Arbitrary files.** A user's own ODB and UNV make a workspace with no archive record and no archive words.
- **Optional label.** The label changes no input. "SP-02" typed by the user is only a label (`specimen_known` false).
- **New SP-02 series.**
  - A re-measured SP-02 UNV, with a result that applied SP-02's registration hash, shows `UNKNOWN` and no archive
    words (`GOVERNED`, `OTHER`, `NOT_GOVERNED`, catalogue, `PHYSICAL`).
  - The same holds for a file with the archived file name.
- **Research archive.**
  - Opened only by its button, placed below the workspace, with all 14 records.
  - Opening it, or choosing a passport, changes no input and no workspace row.
  - Closing hides it and keeps the passport.
- **Locate → Verify → Use from the archive.** Locate and Verify change nothing; Use sets the field, and the panel
  shows the path without any archive status. Nothing is run.
- **Result.** Running shows no pairs; a successful result shows its pairs and MAC; stale and discarded results show
  none.
- **Registration.** Conflicting and missing records are handled. All five kinds render distinctly. The user's data
  gets no catalogue wording.
- **Modal set.** The name comes from the discovered set object, never the display text. Ambiguity gives
  `NOT_CHECKED`. No archive status is given.
- **Auto-ID.** It stays `NOT_AUTHORISED` in every state.
- **Home ↔ Expert.** Switching keeps the label, the inputs, the panel and the archive state; Expert mode keeps 11
  tabs.

## Limits

- **Label not saved.** The specimen label is Home's own session value. It is not saved in projects or the session.
- **Registration on real data.** Real analyses show only `NONE` or `UNKNOWN`, because no result records a
  registration basis. Recording one belongs to the analysis, outside this task.
- **Registration options.** A registration option chosen but not yet run is not shown. The panel shows what the
  result on display applied.
- **Archive and analysis are separate.** The archive is not used to check or enrich the user's data. Comparing new
  data with an archived specimen would be a separate, explicit feature.
- **English only.** The panel is English only. The pre-existing Russian words in the catalogue title and
  `UNKNOWN_TEXT` were left unchanged, as instructed.
