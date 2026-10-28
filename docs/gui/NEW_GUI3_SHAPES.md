# NEW-GUI.3 — individual FE and experimental mode shapes (2026-10-29)

Branch `feature/new-gui3-individual-shapes` from `main` `481b269`. **Status: REVIEW_READY.**

After **Inspect file** (NEW-GUI.2), the user of the new interface can choose one loaded FE mode or one experimental
record and see its spatial shape. Each shape is a view of one side's own data. It is not a comparison: there is no
FE↔EXP overlay, orientation, node correspondence, MAC or mode pair.

## What the user sees

Below each content panel there is a shape panel: "FE results: mode shape" and "Experimental data: record shape". It
appears once that side's file has been read.

1. **Nothing is chosen in advance.**
   - The FE mode list starts at "Choose a mode...". The experimental set list starts at "Choose a modal set...", and
     the record list stays disabled until a set is chosen.
   - **Show shape** is disabled until the choice is complete.
   - No image is drawn until the user clicks **Show shape**.
2. **FE.**
   - The list holds every mode the loader accepted, in its order: rigid-body modes, the first elastic mode and the
     rest.
   - The panel shows the mode number, the frequency, the frequency source and the number of FE nodes.
   - Components: Normal, Magnitude, U1, U2, U3.
3. **Experimental.**
   - First a modal set is chosen explicitly, even when the file has only one. Then a record of that set; record 1 is
     offered like every other record.
   - The choice is the set's and the record's position in the preview (`preview.sets[i].records[j]`), never a parsed
     name.
   - The panel shows the record number, frequency, classification (the importer's wording), points, measured DOFs
     and damping.
   - Components: Normal, Magnitude, X, Y, Z.
   - **FRF records (dataset 58).** "PROVISIONAL — NOT A VALIDATED FITTED MODE" is shown in red directly above the
     image, and it is also the first line of the caption.
   - **Ambiguous records.** The importer's warnings for that record are listed, and the caption starts with
     "AMBIGUOUS (importer)".
4. **The image and its caption are the services'.**
   - FE: `services.local_fe_preview.render_fe_mode_shape`.
   - Experimental: `services.local_experimental_preview.render_record_shape`.
   - Each shape is drawn on its own coordinates. The normal is taken to the best-fit plane of that data set alone,
     not to an FE↔EXP registered system.
5. **Refusals are the services' reasons, and no image is made.**
   - A component that was not measured, for example "X (measurement axes) is not a measured component of this
     record ... no value is created".
   - Fewer than three points with data.
   - Points on one line, which have no normal.
   - The panel shows "No shape drawn: " followed by the reason.
6. **Changing a choice removes the shape.** A changed set, mode, record or component removes the shown shape and
   cancels a drawing in progress. A new shape is drawn only on the next Show shape.
7. **The NEW-GUI.2 tables are unchanged** and stay read-only.

## Background work and files

- **Off the GUI thread.** Drawing runs in a worker thread (`new_gui.shape_model.run_render`). The PNG bytes come
  back through a queued signal, and the pixmap is made, and the widgets changed, in the window's thread.
- **One folder per request.**
  - Each request draws into its own temporary folder (`tempfile.mkdtemp(prefix="new_gui_shape_")`).
  - The PNG is read from that folder, and then the folder is removed before the request ends.
  - Nothing else is deleted: no other temporary file, no cache, no input and no untracked file.
- **Nothing read again.** The drawing uses the data already held by the NEW-GUI.2 preview (`FePreview.dataset`,
  `PreviewSet.dataset`); no FE or UNV file is read for an image.
- **Stale results never shown.** `ShapeSlot` keeps the current request.
  - A changed choice, a replaced or cleared file, Inspect again or a closed window resets it: the request is
    cancelled, and its outcome is counted as discarded.
  - Only the outcome of the current request is shown.
- **Image size.** The image is scaled to the panel's width with its proportions kept, and its height is capped at
  560 logical pixels. A large PNG or a long mode name never widens the window: the image and the combo boxes ignore
  their natural width.

## Architecture

| File | Role |
|---|---|
| `src/new_gui/shape_model.py` (new, no Qt) | The choices (`fe_mode_options`, `set_options`, `record_options`) and the facts and warnings of a record; `render` calls the service; `run_render` handles the per-request folder and turns refusals and cancellation into an outcome; `ShapeSlot` holds the current request. |
| `src/new_gui/shape_panel.py` (new) | `ShapePanel` (choices, Show shape, worker thread, display) and `ImageView` (proportional scaling). |
| `src/new_gui/window.py` | A shape panel below each content panel, linked to that side's read preview. `busy()` and `wait_for_reads` include drawings, and closing the window cancels them. |
| `src/new_gui/__init__.py` | Stage "NEW-GUI.3 preview". |

No scientific service, importer, `modal_data_viewer` or criterion was changed.

## Checks

### Tests

- **`tests/test_new_gui3_shapes.py`** (15 tests, no Qt):
  - every loaded FE mode is offered, rigid-body and first elastic included;
  - FE modes 1, 6 and 7 are drawn in all five components, with the service's caption;
  - FE nodes on one line have no normal;
  - two dataset-55 sets are chosen and drawn independently, record 1 included;
  - an unmeasured component is refused;
  - dataset 2414; ambiguous records with the importer's warning; FRF records PROVISIONAL;
  - too few points;
  - cancellation before and during drawing;
  - stale requests; unknown kind or component;
  - no MAC call and no second read;
  - importing the model loads no service and writes nothing;
  - every request folder is removed.
- **`tests/test_new_gui3_qt.py`** (15 tests, Qt offscreen):
  - nothing is chosen or drawn after Inspect;
  - the NEW-GUI.2 tables stay read-only;
  - FE rigid-body and elastic modes are drawn only on Show shape;
  - a changed component removes the shape;
  - an experimental set, then a record;
  - an unmeasured component shows the refusal;
  - FRF PROVISIONAL is beside the image; ambiguous warnings are shown;
  - a changed component or record, a replaced file, Inspect again, a cleared file and a closed window each discard
    a running drawing;
  - the image is proportional and never wider than its panel;
  - a long mode name does not widen the panel.
- **`tests/test_new_gui1_workspace.py`**: the allowed files of `src/new_gui` now include `shape_model.py` and
  `shape_panel.py`. They need no new project imports.

### Windows (2026-10-29)

All on the real Qt `windows` platform, with screen captures from Windows, never `offscreen`.

**Visual check.**
- Inputs: Cyrillic-named, byte-identical copies of verified inputs, `КЭ_пакет_SP04\manifest.json` and
  `Образец_SP02_эксперимент.unv`.
- Drawn: FE mode 7 and record 1 of the first SP-02 set, Normal.
- Scales: 150 % (native), and 100 % and 125 % (Qt scaling); windows of 900 × 680 and 1366 × 768.
- Every image fits its panel width with its proportions, for example 613 × 475 at 1366 × 768 and 303 × 235 at
  900 × 680 (150 %).
- No page-level horizontal scroll bar and no missing glyph; Cyrillic paths are shown.

**Shape smoke with real mouse and keyboard input (SendInput)** on the verified copies:
- **SP-04 FE package.** Mode 7: Normal, then U3. Changing the component removed the shape until Show shape.
- **SP-02 UNV (dataset 55).** Set 2, record 1: X was refused (not measured), then Normal was drawn.
- **SP-04 UNV (dataset 58).** After replacing the file, the old shape was gone. Record 1 was drawn with PROVISIONAL
  beside it.
- No request folder was left, the inputs were unchanged, and the window closed with no drawing running.

The launcher `RUN_NEW_GUI.cmd` and the native file dialogs are covered by the NEW-GUI.2 smoke, run again on this
code.

## Not in this stage

- No FE↔EXP overlay, orientation, node correspondence, MAC or mode pair.
- No identity of modes from frequency closeness or image likeness.
- No analysis, Abaqus, solver, LM or Auto-ID.
- No change to services, importers, `modal_data_viewer`, criteria, registrations, SPEC or frozen evidence.

## Limits

- **One drawing at a time.** Drawings of both sides are serialised by one lock, because matplotlib figures are not
  drawn in parallel.
- **Late cancellation.** The services check cancellation before and after drawing. A drawing cancelled while
  matplotlib draws still ends, and its outcome is discarded.
- **Fine meshes.** For a fine FE mesh the service averages the nodes per display cell, as its caption says (SP-04:
  251385 nodes).
- **Scaling.** 100 % and 125 % were checked with Qt scaling, not by switching the Windows setting.
