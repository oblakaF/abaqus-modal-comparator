# NEW-GUI.4 — diagnostic comparison of FE and experimental frequencies (2026-10-29)

Branch `feature/new-gui4-frequency-diagnostic` from `main` `9994b0c`. **Status: REVIEW_READY.**

The Analysis page of the new interface is now a diagnostic screen. After **Inspect file** has read the FE results
and the experimental data (NEW-GUI.2), the user chooses one experimental modal set and clicks **Run frequency
diagnostic**. The result is the existing frequency-only diagnostic, FREQUENCY_ONLY_DIAGNOSTIC: frequencies and
frequency differences, with no geometric registration, no MAC and no mode pair.

## Scientific service

- **The existing function.** `services.new_odb_comparison.frequency_only_diagnostic(abaqus, experimental, reason)`,
  unchanged.
- **The data already read.**
  - FE: `FePreview.dataset`.
  - Experimental: `ExperimentalPreview.sets[set_index].dataset`.
  - No file is read again, and no frequency-matching algorithm of its own is added.
- **The reason** given to the service: "no physical registration between the FE model and the experiment has been
  established or verified for this workspace, so no orientation, node correspondence, MAC or mode pair exists."
- **Rigid-body FE modes.**
  - The service separates them by its existing shape criterion: six-vector rigid-body projection, residual ≤ 0.02
    (`quality_control.RIGID_SHAPE_RESIDUAL_THRESHOLD`).
  - No frequency threshold is used.
  - They are listed separately with their residuals and are never nearest-frequency candidates.
- **Not used.** `bind_registration_by_fe_geometry` is not called. No accepted registration (SP-02, SP-13) is looked
  up or carried over to the user's workspace, and the research archive is not read.

## What the user sees

1. **Nothing runs by itself.**
   - The Analysis page shows "Analysis not run" and states that no frequency, MAC value or mode pair has been
     computed.
   - **Run frequency diagnostic** is disabled until the conditions below are met, and the reason is shown under it:
     - "The FE results are not read: ..."
     - "The experimental data are not read: ..."
     - "Choose the experimental modal set to compare."
   - A failed read (for example a plain `.odb`) counts as not read.
   - The modal-set list starts at "Choose a modal set...". Every set of the file is offered as "Modal set i of n:
     ...", and none is preferred.
2. **The result**, after a click:
   - **Status.** FREQUENCY_ONLY_DIAGNOSTIC with the service's statement and reason. The summary reads MAC
     NOT_COMPUTED; Mode pairs NONE (physical modal correspondence not verified).
   - **The chosen set:** "Experimental modal set: Modal set i of n: ...", and the experimental frequency source
     worded by the service.
   - **Table "Nearest by frequency — NOT a mode pair".** One row per experimental record, record 1 included. Columns:
     - experimental record and mode, and the experimental frequency;
     - nearest elastic FE mode and frequency, and their difference;
     - next elastic FE mode and frequency, and their difference;
     - MAC: NOT_COMPUTED in every row (never a zero);
     - the importer's classification, and a note.
   - **Sign of the differences.** The comparator's existing convention: (f FE − f EXP) / f EXP × 100. A positive
     value means the FE frequency is higher.
   - **Separate tables:**
     - extracted FE frequencies (elastic modes);
     - FE rigid-body modes (diagnostic records, with the rigid-body residual and the criterion);
     - experimental frequencies (every record of the set).
   - **Out-of-range warnings.** An experimental frequency below the lowest or above the highest extracted FE mode is
     noted in its row and listed under the table, in the service's words.
   - **Dataset 58.** "PROVISIONAL — NOT A VALIDATED FITTED MODE" is shown in red above the tables, as the
     classification of every row and at the start of every row's note.
   - **Ambiguous records** keep the importer's classification ("AMBIGUOUS (importer) — ...") and the set's importer
     warnings, as written.
3. **Changes remove the result.**
   - Another modal set, a replaced or cleared file, or Inspect again removes the result.
   - It also cancels a running diagnostic.
   - A new result comes only from the next click.
4. **Unchanged.** The Status page (no command; NOT_AUTHORISED, NOT_MET, NO_GLOBAL_PARAMETER_VALUE), the NEW-GUI.3 shape
   panels and the old interface.

## Background work

- **Off the GUI thread.** The service runs in a worker thread (`new_gui.diagnostic_model.run_diagnostic`). The outcome
  comes back through a queued signal, and the tables are made in the window's thread.
- **Stale results never shown.** `DiagnosticSlot` keeps the current request. Another set, a replaced or cleared file,
  Inspect again or a closed window cancels it, and its outcome is discarded.
- **One diagnostic at a time.**
  - The service cannot be stopped midway. On a large FE model its rigid-body projection needs much time and memory:
    SP-02, 1 663 816 nodes, about 16 s and a traced peak of about 1.4 GB on the first run.
  - A new request therefore waits until a discarded one has ended. It is checked for cancellation again, and then
    reuses the residuals the service recorded in the dataset (later runs take well under a second).

## Architecture

| File | Role |
|---|---|
| `src/new_gui/diagnostic_model.py` (new, no Qt) | Set choices; why the diagnostic is unavailable; `diagnose` (the service on the read data); `run_diagnostic` (outcome, cancellation, one at a time); `DiagnosticSlot`; `diagnostic_view` (the service's result worded for display, rows matched to the set's records in the service's order). |
| `src/new_gui/diagnostic_panel.py` (new) | `DiagnosticPanel` (summary, inputs, set choice, Run, result) and `DiagnosticTable` (read-only, as tall as its rows, scrolls horizontally itself). |
| `src/new_gui/window.py` | The Analysis page holds the panel and passes it the read previews; `busy()`, `wait_for_reads` and closing include the diagnostic; the status bar shows its status. |
| `src/new_gui/workspace_state.py` | The Analysis note's static text only. |
| `src/new_gui/__init__.py` | Stage "NEW-GUI.4 preview". |

No scientific service, criterion, importer, SPEC, DECISIONS entry, registration, frozen evidence or Auto-ID block was
changed.

## Checks

### Tests

- **`tests/test_new_gui4_diagnostic.py`** (15 tests, no Qt):
  - The GUI calls the service once with `FePreview.dataset`, the chosen set's dataset (the same objects) and the
    reason. Its result equals the service's.
  - Every displayed value, the sign convention and the experimental list are the service's.
  - **Rigid-body modes by shape.** A translation at 0.0011 Hz and a rotation at 4.5 Hz are rigid-body. A saddle mode
    at 0.0012 Hz is elastic. Rigid-body modes are never nearest candidates.
  - **Out of range.** Frequencies outside the FE range are flagged.
  - **Two dataset-55 sets** are never mixed, and record 1 is kept.
  - **Other experimental data:**
    - dataset 2414;
    - ambiguous records, with the importer's classification and warnings;
    - dataset 58, PROVISIONAL.
  - **Never called:** MAC, comparison or pairing, geometric alignment, registration lookup or reuse, file hashing for
    reuse, the research archive, a second import or a process. No input file changes.
  - **The reasons** the button is unavailable.
  - **Requests:**
    - cancellation before and during the service;
    - one diagnostic at a time, and a request cancelled while it waits never runs;
    - a service error becomes a message;
    - only the current request is shown.
  - **On import** the model loads no service.
- **`tests/test_new_gui4_qt.py`** (14 tests, Qt offscreen):
  - **Availability:** disabled with the reason until FE read, experimental read and set chosen; nothing runs by itself;
    a failed read keeps it disabled.
  - **A click shows:**
    - FREQUENCY_ONLY_DIAGNOSTIC in the badge and the status bar;
    - the chosen set;
    - the "Nearest by frequency — NOT a mode pair" table, with MAC NOT_COMPUTED in every row and record 1;
    - the rigid-body and elastic FE tables;
    - read-only tables;
    - the Status page unchanged.
  - **Changes:** another set removes the result; the first set then gives its own records only.
  - **Special data:** FRF PROVISIONAL; ambiguous warnings.
  - **Shape panels** still draw.
  - **Stale outcomes discarded:** another set, a replaced FE file, a cleared experimental file, Inspect again, a closed
    window.
  - **Narrow window:**
    - every column stays reachable;
    - each table scrolls itself and is as tall as its rows;
    - the result adds no width to the page.
- **`tests/test_new_gui1_qt.py`** (authorised change of one NEW-GUI.1 test,
  `test_the_analysis_page_offers_only_the_diagnostic_command_and_the_status_page_none`):
  - The Analysis page has exactly one command, Run frequency diagnostic, disabled at an empty start.
  - "Analysis not run" and "no frequency, MAC value or mode pair has been computed" remain until it is clicked.
  - Choosing files enables and computes nothing.
  - The Status page has no command, and its three values are unchanged.
- **`tests/test_new_gui1_workspace.py`.** The allowed files of `src/new_gui` and its project imports now include
  `diagnostic_model.py`, `diagnostic_panel.py` and `services.new_odb_comparison`.

### Windows (2026-10-29)

Everything ran on the real Qt `windows` platform (Segoe UI, 150 % native, device pixel ratio 1.5) with an isolated
LOCALAPPDATA, on the verified read-only copies. Their SHA-256 was checked before and after.

**Analysis smoke with real mouse and keyboard input (SendInput).**

- **Empty start.** One command, Run frequency diagnostic, disabled with the two "not read" reasons.
- **SP-02 FE package + SP-02 UNV** (1 663 816 FE nodes, 10 FE modes; three dataset-55 sets).
  - **After Inspect.** "Choose the experimental modal set to compare"; no set chosen.
  - **A stale result discarded.** Set 1 was chosen and Run clicked. Set 3 was chosen while the first diagnostic ran.
    The result was discarded (1 discarded), nothing was shown, and the background computation ended 8 s later. The
    longest GUI timer gap during it was 0.84 s.
  - **Set 3.** 8 rows, record 1 included; FE mode 6 rigid-body (residual 3e-08); 9 elastic FE modes; MAC
    NOT_COMPUTED in every row.
  - **Set 1.** 9 rows; one frequency above the FE range.
- **Sizes.** 1366 × 768 and 900 × 680: no page-level horizontal scroll bar and no missing glyph. Every table shows
  all its rows; a table wider than the window scrolls itself, with every column reachable.
- **Status page.** No command; NOT_AUTHORISED, NOT_MET, NO_GLOBAL_PARAMETER_VALUE.
- **SP-02 replaced by the SP-04 FE package + SP-04 UNV (dataset 58 only).**
  - The result was removed when the files were replaced.
  - After Inspect, set choice and Run (4.8 s; longest GUI gap 0.18 s), the result has 19 rows, PROVISIONAL shown in
    red, and 8 frequencies outside the FE range.
- **End.** The window closed with nothing running. Inputs unchanged; no tracked file under `docs/registrations`,
  `docs/baseline` or `docs/auto_id` changed.

**Other Windows checks:**
- **`RUN_NEW_GUI.cmd`** (native file dialogs; the NEW-GUI.2 scenario on this code). Title "NEW-GUI.4 preview", no
  cache at an empty start, responsive while reading, stale read not shown, exit 0, no child process.
- **Old interface.** `RUN_PROGRAM.cmd` started and closed (exit 0).

## Not in this stage

- No automatic geometric orientation, and no orientation chosen by MAC or by frequency proximity.
- No node correspondence, mode pair, MAC or material optimisation.
- No Abaqus, solver, LM or Auto-ID.

## Limits

- **Late cancellation.** The service is not interruptible. A diagnostic cancelled while it runs ends in the
  background (on SP-02 up to about 16 s), and its outcome is discarded.
- **Memory.** On a fine FE mesh the service's rigid-body projection needs much memory on its first run (SP-02: traced
  peak about 1.4 GB).
- **Proximity only.** The nearest-frequency columns say nothing about modal correspondence. An experimental frequency
  outside the extracted FE range has a nearest FE frequency that is not meaningful, as its note says.
