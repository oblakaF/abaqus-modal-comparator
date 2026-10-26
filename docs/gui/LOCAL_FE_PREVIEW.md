# APP-DATA.2 — view of extracted FE modes (2026-10-25)

Branch `feature/app-data2-fe-manifest-preview` from `main` `3156cf2`. A program convenience, not a scientific stage.

## What it does

In **File > Input file registry...**, select an FE entry and press **Inspect FE modes...**. A separate window opens
and shows:

- the FE source (`odb_path` recorded in the manifest), the package path and the step;
- each loaded FE mode: number, frequency in Hz, frequency source (EIGFREQ history or frame frequency, with the
  loader's reason when the frame value is kept) and the node count;
- the number of loaded modes, with their range;
- the loader's diagnostic messages:
  - a mode not loaded because its frequency records contradict each other;
  - EIGFREQ not used for the consistency check;
  - a requested range that the extraction frames clipped or left non-contiguous.

The window states that this is a view only. It is not a physical registration and not a mode pairing: no MAC is
computed, nothing is compared with an experiment, and no mode is excluded.

## How it reads the package

- **The existing loader.** `services/local_fe_preview.py` calls `abaqus_bridge.load_extracted_odb` unchanged and
  shows what it returns.
  - A mode the loader refuses is not shown as a mode; its reason is listed.
  - A mode it accepts is shown with the loader's frequency (the EIGFREQ value where the loader takes it).
  - There is no second interpretation of EIGFREQ, of the frame description or of zero-frequency frames.
- **All loaded modes are shown.** Rigid-body frames and the first elastic mode are listed as loaded, without
  classification or renumbering.
- **A plain `.odb`** gets a message: the modes can be viewed only from an existing extracted package (`manifest.json`
  with its CSV files). Abaqus is never started for a preview.
- **The files are only read.** Nothing is written to the manifest, CSV or ODB.
- **The reading runs on a background thread**, so the main window stays usable.
  - The thread only receives the path, a cancel event and a queue; it never touches a Tk object.
  - The window polls the queue.
  - Closing the window sets the cancel event (the loader stops at its next mode). A late outcome is discarded, and a
    poll after closing never touches the window.
- **A missing CSV or geometry file, a damaged manifest, or a package with no usable mode** is stated in the window,
  and no modes are shown.

## Changed files

- `src/services/local_fe_preview.py` — new service over `load_extracted_odb`.
- `src/menu_ui.py` — the *Inspect FE modes...* button of the registry dialog and `FePreviewWindow`.
- `tests/test_local_fe_preview.py` — 13 tests on synthetic temporary packages.
- `tests/test_local_input_registry.py` — the damaged-registry test also checks that the new button is disabled.
- Not changed: `abaqus_bridge.py`, scientific services and accepted algorithms.

## Verification

| Check | Result |
|---|---|
| `tests/test_local_fe_preview.py` | 13 OK |
| Covered by those tests | valid package with rigid-body and elastic modes; EIGFREQ history values; contradictory frequency records (results identical to the loader, its reasons listed); clipped range; missing CSV; missing geometry; damaged manifest in 6 forms; `.odb` never extracted; cancellation; files unchanged; no process started; window: modes and status, `.odb` message, experimental entry, missing file, damaged package, closing while reading |

The regressions and the Windows check are in the task report.

## APP-DATA.5 — the shape of the selected FE mode (2026-10-26)

Branch `feature/app-data5-fe-mode-shapes` from `main` `1252ea0`.

**What it does.** Select a mode in the table and press **View selected FE mode shape**. An *FE mode shape* window
shows that mode on its own FE nodes and coordinates.

- **Components:** out-of-plane (normal to the best-fit plane of the nodes), magnitude |U|, U1, U2, U3.
- **Caption:**
  - the mode number, its frequency and the frequency source, as in the table;
  - the component and the node count;
  - a statement that rigid-body and elastic modes are not classified or excluded here;
  - the loader's diagnostic message for that mode, if any.
- **No analysis is started.** The window draws from the package the view has already loaded.

**How the mode is drawn.**

- **The existing loader and drawing.**
  - The mode is the one `abaqus_bridge.load_extracted_odb` loaded, taken by its position in the table, and its
    number and frequency are checked against the row.
  - It is drawn by `services.modal_data_viewer.render_viewer_mode` with the FE role, as in *3. Mode shapes >
    Individual modes*: phase alignment, best-fit plane, normalisation, display grid for large models and colour map
    unchanged.
  - The mode is passed alone, so the drawing cannot pick another mode of the package.
  - No new FE data are created, and Abaqus is not started.
- **Every loaded mode can be drawn.** Rigid-body frames and the first elastic mode are not excluded or classified.
- **No picture when a spatial view is impossible, with its reason:**
  - fewer than three nodes with a response;
  - for the out-of-plane component, nodes on one line: no best-fit plane and no normal to it are defined, so no
    arbitrary normal is drawn. The U1, U2, U3 and magnitude views of such nodes are still drawn.

  The rule for nodes on one line is the one of the experimental shape view (APP-DATA.4).
- **The shape window of APP-DATA.4 is reused.** `ModeShapeWindow` draws a target (an experimental record or an FE
  mode), so there is one mechanism for both views:
  - a background thread that never touches Tk;
  - a queue polled on the Tk thread;
  - a newer request supersedes an older one, and a late result is discarded and its image removed;
  - the picture goes as soon as another mode or component is chosen;
  - closing the window (or the FE modes view) while drawing is safe;
  - temporary images are removed on close.

  The experimental view behaves as before.
- **A plain `.odb`** still gets the existing message; nothing is extracted.

| Check | Result |
|---|---|
| `tests/test_local_fe_preview.py` | 18 OK, of which 5 new |
| What the new service tests cover | every loaded mode, six rigid-body frames and three elastic modes, drawn on its own nodes with the loader's values (compared with `load_extracted_odb`); all five components; frequency source (EIGFREQ history) and a mode's loader diagnostic kept; two nodes and nodes on one line refused with the reason (no image), U3 and magnitude still drawn on the line; a mode not in the package and a cancel draw nothing; package unchanged, no process |
| `tests/test_app_data5_fe_shape_view.py` | 4 OK, in the real main window |
| What the window tests cover | button state; a rigid-body frame and the first elastic mode drawn; the view follows the selection; component change; deselection clears the picture; main window, package and registry unchanged; nothing run; a superseded drawing never shown; degenerate geometry stated; closing while drawing (no Tk error, nothing left behind) |

## Limits

- **Only what the loader loads is shown.**
  - When the loader refuses the whole package, the window shows its error and no modes. For example, a mode file
    with a zero frequency fails the existing `ModeShape` check.
  - No partial interpretation is attempted.
- **Cancellation is cooperative.**
  - The loader checks the cancel event between modes; a single large CSV is read to its end.
  - The thread is a daemon and holds no window object.
- **The shape view is a picture only.** It is not saved or exported, and a drawing already started is not
  interrupted; closing only discards it.
- **No rigid-body label in the shape view.** The comparator's rigid-body criterion is computed by an analysis run, and
  this view does not compute it. Rigid-body frames are therefore drawn as "Abaqus FE mode N", like any other mode,
  and are neither labelled nor excluded.
- **The main window's individual-mode viewer is unchanged.** It still draws an arbitrary normal for nodes on one
  line; only the new view refuses it.
- **Unchanged:**
  - SPEC v1.2, DECISIONS, the specimen catalogue, registrations, frozen evidence, MAC, pairing and QC criteria;
  - M8 GATE `NOT_MET`; D-077 `NO_GLOBAL_PARAMETER_VALUE`; production Auto-ID BLOCKED / NOT_AUTHORISED.
- No Abaqus, no solver, no LM, no Auto-ID.
