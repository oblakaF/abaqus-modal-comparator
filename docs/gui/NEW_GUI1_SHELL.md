# NEW-GUI.1 — first working shell of the new interface (2026-10-28)

Branch `feature/new-gui1-pyside6-shell` from `main` `b27482c` (CI 40689430210 success). **Status: REVIEW_READY.**

A separate Windows program window on **PySide6 (Qt)** for any FE model and any experimental data. It is a new shell,
not another card of the existing Home. The existing Tkinter program (`RUN_PROGRAM.cmd`, `src/main.py`, Home and
Expert) is unchanged and stays the working program until the new interface is accepted.

This first stage only lets the user choose their own files, shows the workspace and opens the research archive on
request.

## Start

- `RUN_NEW_GUI.cmd`:
  - uses the same local `.venv` as `RUN_PROGRAM.cmd` and checks `requirements.txt` the same way;
  - installs PySide6 from `requirements-new-gui.txt` only when it is missing;
  - starts `python -m new_gui` with `src` on `PYTHONPATH`.
- **Separate dependency.** `requirements-new-gui.txt` holds `PySide6-Essentials>=6.8,<7`. It is not in
  `requirements.txt`, so the existing program gets no new dependency.
- **Manual start.** `python -m pip install -r requirements-new-gui.txt`, then `python -m new_gui` with `src` on the
  path, or `python src/new_gui`.

## What the user sees

1. **First launch: an empty workspace.**
   - No file, no specimen, no project, no material, no registration, no preset, and no analysis.
   - A banner says: "No data selected yet. Choose an FE results file and an experimental file to start. Nothing is
     loaded or analysed automatically."
2. **Two source cards, FE results and Experimental data.** Each card has:
   - **Choose file...** (after a choice, **Replace file...**), which opens the Windows file dialog;
   - **Clear**, enabled only when a file is chosen;
   - a status badge below the title, the file name, the real path and the file type. The path is read-only and
     copyable; when it is too long its end (folder and name) is shown, with the whole path in the tooltip.
     Two `manifest.json` files are told apart by their folders.
   - Supported files: FE is an Abaqus `.odb` or an extracted `manifest.json`; experimental is a `.unv` / `.uff`, or
     an `.lms` project with its companion `.unv` / `.uff` beside it (the companion's name is shown).
3. **Status of a chosen file: "File chosen; content not checked".** Only existence and type are checked. The card
   says this is not a statement that the data are ready for analysis.
4. **Refused or cancelled choices.**
   - A missing file, a folder or a file of the wrong type is refused. The reason is shown in red in the card, and
     the previous choice is kept ("Nothing was chosen." when there was none).
   - A cancelled dialog changes nothing.
5. **Specimen name (optional).** A free-text label. It is never looked up in the research archive: "SP-02" typed by
   the user links the files to no archived specimen, registration or status.
6. **Side navigation: Workspace, Analysis, Status.** The research archive has its own command at the bottom of the
   sidebar and in the File menu.
   - **Analysis** shows "Analysis not run": no frequency, MAC value or mode pair is computed, and the page has no
     buttons.
   - **Status** shows the scientific status read from its owners:
     - Production Auto-ID `NOT_AUTHORISED` (from `services.workspace_context.production_auto_id_status`, i.e. the
       blocking authority code);
     - M8 gate `NOT_MET` and D-077 formal output `NO_GLOBAL_PARAMETER_VALUE` (read from
       `docs/auto_id/STATUS.json`; an unreadable record shows `UNKNOWN`).
   - **Status bar:** "Analysis not run · Production Auto-ID NOT_AUTHORISED".
7. **Open research archive...** opens a read-only dialog. It lists the archive's specimen records
   (`services.specimen_catalog_view`) and shows the passport of the record the user clicks.
   - It never opens at start, and no record is selected when it opens.
   - It has only **Close**: no action selects a file, transfers a registration or assigns a modal status.
   - It is read anew each time it is opened.
   - **A missing or damaged archive** shows "The research archive is not available: … The rest of the program works
     without it."

**Layout.**
- One light theme (Fusion style with an explicit palette), the same under the Windows light and dark modes.
- Fonts are in points, and Qt 6 scales them per monitor, so 100 %, 125 % and 150 % keep the layout.
- The window opens at most 90 % of the available screen, with a minimum of 560 × 420.
- Pages scroll. Below a content width of 760 px the two source cards are stacked.
- The sidebar is as wide as its texts need (at least 180 px), so a larger font never cuts the archive button.
- Checked at 100 %, 125 % and 150 % on a 1366 × 768 screen and at the minimum size: no page needs a horizontal
  scroll bar.
- English only.
  - The catalogue service's bilingual unknown marker (`UNKNOWN_TEXT`) is shown as "Unknown" in the archive dialog;
    the service itself is unchanged.
  - Archive data such as store folder names are shown as recorded.

## Architecture

| File | Role |
|---|---|
| `src/new_gui/__init__.py` | Package; application name and stage. |
| `src/new_gui/__main__.py` | Entry point (`python -m new_gui`); a clear message when PySide6 is missing. |
| `src/new_gui/workspace_state.py` | The workspace model, with no Qt: `Workspace`, `FileChoice`, `load_archive`, `scientific_status`. Tested headless. |
| `src/new_gui/window.py` | The main window: sidebar, pages, source cards, menu, status bar, style. |
| `src/new_gui/archive_dialog.py` | The read-only research archive dialog. |

- **Separation from the existing program.** The new GUI does not import `src/main.py`, Home, Tkinter or any
  `install_*` layer, and it adds no layer.
- **Allowed project imports.** It imports only `services.local_input_registry`, `services.specimen_catalog_view`,
  `services.workspace_context` and `universal_reader.resolve_testlab_file`, the same LMS companion rule that
  `check_file` uses.
- **No duplicated science.** Files are checked with the existing read-only contract
  `services.local_input_registry.check_file`. Nothing is written to the input file registry, and the file content is
  not read.
- **Immutable model.** `Workspace` is a frozen dataclass: `choose`, `clear` and `with_label` return a new workspace,
  and a refused or cancelled choice returns the same one.

## Windows smoke (2026-10-28)

The smoke used the existing Tkinter program as LEGACY_GUI and this window as NEW_GUI.

- **Setup.** Windows 10 at 150 % (DPI 144), 3840 × 2160.
- **NEW_GUI through `RUN_NEW_GUI.cmd`**, on verified read-only copies whose SHA-256 was checked against their copy
  record:
  - The empty window appeared after 2.5 s, with no other window.
  - FE chosen through the native dialog ("Choose the FE results file"), then experimental, then the FE replaced by
    another manifest; a cancelled dialog changed nothing.
  - Small (900 × 680) and large windows were checked. The research archive opened from the File menu with no
    record selected, and was closed.
  - The window closed with code 0 and no child process.
  - Inputs, the catalogue and `STATUS.json` were unchanged, and no input file registry was created.
- **LEGACY_GUI.** `RUN_PROGRAM.cmd` (isolated profile) still starts and closes with code 0.

## Not in this stage

- No analysis, no Abaqus, no solver.
- No frequencies, MAC or mode matching.
- No Auto-ID and no material identification.
- No templates and no automatic loading of earlier projects.
- No link of new UNV files to archive specimens.
- No change of any scientific criterion.
- No result is invented, and there is no button without an implementation.

## Tests

### `tests/test_new_gui1_workspace.py` (27; no Qt)

- **Empty start.** The model holds only the two file choices and the label.
- **Arbitrary plate.**
  - Synthetic `.odb`, `.unv`, `.uff`, `manifest.json` and `.lms` (with a companion) are accepted with their types,
    while the archive loader is patched to fail.
  - `check_file` is the contract used. The registry is not written, and file content is not opened.
- **Replace, cancel, clear, refuse.**
  - Replace and clear work. A cancelled dialog changes nothing.
  - A missing file, a folder and a wrong type are refused, and the previous choice is kept.
  - An LMS project without a companion is refused, and an unknown kind is an error.
- **SP-02 label.** It is a label only. A file with an archived name gets no archive wording.
- **Archive.**
  - 14 records are listed read-only; the catalogue SHA-256 is unchanged.
  - A missing, damaged, foreign or empty archive gives a problem, not an error. An unexpected failure or an
    unwordable record does not stop the program.
- **Status.**
  - The values are `NOT_AUTHORISED` (equal to `campaign_execution_plan.NOT_AUTHORISED`; the authority is
    unavailable), `NOT_MET` and `NO_GLOBAL_PARAMETER_VALUE`.
  - An unreadable status record gives `UNKNOWN`, and Auto-ID stays `NOT_AUTHORISED`.
- **Nothing changed.** User files (SHA-256 and modification time), the catalogue and the registry are unchanged.
- **Separation.**
  - Imports are limited to the allowed services, and no `install_*` name is used.
  - A fresh Python process that imports the model loads neither `main`, `home_dashboard` nor `tkinter`.
  - PySide6 is not in `requirements.txt`.

### `tests/test_new_gui1_qt.py` (18; the real window on the Qt `offscreen` platform)

- **First launch.** It is empty, the archive is closed, no SP name or archive word is shown, and the interface is
  English only.
- **Choosing files.**
  - FE and UNV of an arbitrary plate are chosen through the dialog (stubbed), while the archive loader is patched to
    fail.
  - Replace, cancel and clear work. A wrong path is refused visibly, and the previous choice is kept.
  - The real `QFileDialog`, cancelled, changes nothing.
  - The menu commands work.
- **SP-02 label.** No archive link and no archive word.
- **Archive.**
  - It opens only by its button or menu, with 14 records and none selected.
  - Its only button is Close; the workspace and the catalogue are unchanged.
  - A damaged or missing archive shows its problem, and the window keeps working.
- **Nothing computed.** The analysis and status pages have no buttons, "Analysis not run" is shown, and the status
  values are as recorded.
- **Nothing changed.** User files, the catalogue and the registry are unchanged.
- **Layout.** A small window stacks the cards, a wide one places them side by side, the window fits the screen and
  it closes.

**CI.**
- `.github/workflows/tests.yml` installs the system libraries Qt needs offscreen, then installs
  `requirements-new-gui.txt`.
- It runs the suite with `QT_QPA_PLATFORM=offscreen` and `NEW_GUI_REQUIRE_QT=1`. Without that variable, the Qt
  tests skip with an explicit reason when PySide6 is missing; with it, a missing PySide6 is an error.
- A separate step runs the Qt tests on their own. It fails unless at least 18 ran and the result line is a plain
  `OK` (none skipped).
  - It replaced a first check that counted the `... ok` lines of the whole log. That check counted only 13 of 18 in
    CI run 40712738887, because Qt messages written to the same stream can break those lines.

## Limits

- **Selection only.** A chosen file is not imported or read. The status says so, and readiness for analysis is not
  claimed.
- **Nothing remembered.** The label and the choices live only in the open window: they are not saved, and nothing
  is loaded at start.
- **Status-file dependency.** The M8 and D-077 values are read from `docs/auto_id/STATUS.json`. A copy of the
  program without `docs/` shows `UNKNOWN` for them. Production Auto-ID always comes from the code.
- **No functional parity yet.** The new interface does not yet replace any function of the existing program. The
  functional-coverage audit before further migration is a separate task.
