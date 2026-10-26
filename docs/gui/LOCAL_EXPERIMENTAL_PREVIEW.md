# APP-DATA.3 — view of experimental modal data (2026-10-26)

Branch `feature/app-data3-experimental-preview` from `main` `dd8dfd5`. A program convenience, not a scientific stage.

## What it does

In **File > Input file registry...**, select an experimental entry (UNV / UFF / LMS) and press **Inspect
experimental data...**. A separate window opens and shows:

- **the file:** the selected file and the UNV / UFF actually read (the companion of an LMS project);
- **the data kind:**
  - fitted modal sets (dataset 55);
  - dataset 2414 records when the file has no usable dataset-55 set;
  - FRF data (dataset 58);
- **the dataset types** in the file and the number of geometry nodes;
- **for each fitted modal set:**
  - its name, key and number of records;
  - its processing name;
  - the residual and non-modal records the importer excluded (with their labels);
  - the importer's warnings;
- **the records of the set chosen in the window:** number, frequency in Hz, classification, measured points and
  measured DOFs;
- **for dataset 2414:** the importer's classification of every record (physical / non_modal / ambiguous, included or
  excluded, with the reason);
- **for FRF-only data:** the FRF channel count. Every peak-derived record is labelled
  **PROVISIONAL — NOT A VALIDATED FITTED MODE**.
- **the importer's classification of each record** (dataset 55 and dataset 2414), from the mode's
  `record_classification`, `record_classification_reason` and record index:
  - a record the importer classified as physical shows its source and, for example,
    "dataset 55 record 1 (physical, importer)";
  - a record the importer preserved as ambiguous shows **AMBIGUOUS (importer) — dataset 55 record 2, not a
    confirmed fitted mode: <reason>**. It is never presented as an unambiguously confirmed fitted mode;
  - "dataset NN record K" is the wording of the importer's warning ("Dataset NN record K was preserved as
    ambiguous: ..."), which is listed below the table;
  - the status line counts the ambiguous records.

  The classification, frequencies, shapes and number of records are the importer's and are not changed.

The window states that it is a view only. Nothing is compared with an FE model, no modal set is selected for an
analysis, no mode is excluded or paired, and no MAC is computed.

## How it reads the file

- **The comparator's importer, unchanged.**
  - `universal_reader.resolve_testlab_file` resolves an LMS project to its companion. Without the companion the
    importer's message is shown.
  - `universal_reader.discover_experimental_modal_sets` lists the dataset-55 sets.
  - Each set is loaded on its own with the importer the analysis uses: `universal_reader.load_universal_modal_file`
    as installed (fast cache → universal hardening → reader), with an explicit `modal_set=<key>`.
  - Without a dataset-55 set, the importer is called without a set. It then uses dataset 2414 (keeping its record
    classification) or derives FRF peak snapshots from dataset 58.
  - The classification of each record is `services.modal_data_viewer.experimental_classification`.
  - There is no second interpretation of modes, residuals, dataset 2414 or FRF peaks.
- **Several modal sets are never merged or chosen.** The list in the window selects which set is displayed. It
  changes nothing in the main window: not the experimental field, the modal set, the result or the registry.
- **The absence of dataset 55 is not "no fitted modes".** When dataset 2414 supplies curve-fitted records, they are
  shown as such.
- **All imported records are shown**, including experimental mode 1. Nothing is excluded or renumbered.
- **The files are only read.**
- **The reading runs on a background thread**, so the main window stays usable.
  - The thread only receives the path, a cancel event and a queue; it never touches a Tk object.
  - The window polls the queue.
  - The importer reads a whole file in one call and cannot be interrupted inside it. Closing the window stops the
    view at its next step (before the next set is read), and a late outcome is discarded. A read in progress
    finishes in the background.
- **A missing file, an LMS project without its companion, or a damaged or unreadable file** is stated in the window,
  and no records are shown.

## Changed files

- `src/services/local_experimental_preview.py` — new service over the existing importer.
- `src/menu_ui.py` — the *Inspect experimental data...* button of the registry dialog and
  `ExperimentalPreviewWindow`.
- `tests/test_local_experimental_preview.py` — 13 tests on synthetic temporary files.
- `tests/test_local_input_registry.py` — the damaged-registry test also checks that the new button is disabled.
- Not changed: `universal_reader.py`, `modal_data_viewer.py`, `polymax_ui.py`, scientific services and `install_*`
  layers.

## Verification

| Check | Result |
|---|---|
| `tests/test_local_experimental_preview.py` | 13 OK |
| Covered by those tests | one dataset-55 set; two sets (shown separately, never merged; the importer still refuses to choose); residual and non-modal records excluded exactly as the importer reports them; dataset 2414 with its record classification; FRF-only dataset 58 (every record PROVISIONAL); LMS with and without its companion; damaged and missing files; cancellation; files unchanged; window: switching sets, main window untouched (fields, modal set, no result, not running), registry unchanged, FRF labels, FE entry and missing file refused, damaged file stated, closing while reading |

The regressions, CI and the Windows check are in the task report.

## APP-DATA.4 — the shape of the selected record (2026-10-26)

Branch `feature/app-data4-experimental-mode-shapes` from `main` `1ab7e39`.

**What it does.** Select a record in the table and press **View selected mode shape**. A *Mode shape* window shows
that record on its own measured points:

- **Components:** out-of-plane (normal to the best-fit plane of the points), magnitude, X, Y or Z (measurement
  axes).
- **Warnings:**
  - an FRF peak-derived record has the banner **PROVISIONAL — NOT A VALIDATED FITTED MODE**;
  - an ambiguous record has the banner **AMBIGUOUS (importer) — dataset NN record K, not a confirmed fitted mode:
    \<reason\>**;
  - the caption repeats the row's wording.
- **Caption:** the record and its set, the component, how many points are drawn, and the measured components.

**How the record is drawn.**

- **The drawing is the main window's.** It uses `services.modal_data_viewer.render_viewer_mode`, as in *3. Mode
  shapes > Individual modes*: phase alignment, best-fit plane, normalisation and colour map are unchanged. There is
  no second conversion or normalisation of shapes.
- **Only the selected record of the set shown.** The view keeps the importer's dataset of each set (the one it listed
  in the table). The record is taken by its position in that set, and its number and frequency are checked against
  the row. Several sets are never merged, and the main window's modal set is not changed.
- **Measured data only.**
  - X, Y or Z are drawn only at the points where the importer recorded that component as a measured DOF.
  - A component that is measured nowhere in the record is refused with its reason, and nothing is drawn.
  - The normal and magnitude views use the points with at least one measured DOF.
  - The values are the imported ones; no point, value, mode or DOF is created.
  - When the importer recorded no measured-DOF mask, the components with data are used and the caption says so.
- **No spatial view, with its reason.** Instead of a picture, the window states:
  - fewer than three measured points with a response;
  - for the out-of-plane component, points that lie on one line: no best-fit plane and no normal to it are defined.
    The X, Y, Z and magnitude views of such points are still drawn.
- **Never a stale picture.**
  - The picture goes as soon as another record, component or set is chosen.
  - A newer request supersedes an older one; a late result of an older request is discarded and its image removed.
  - When the set changes, the window says so until a record of the new set is chosen.
- **Threads.**
  - Drawing runs on a background thread, which never touches a Tk object; the window polls a queue on the Tk
    thread.
  - Closing the window (or the data view) while drawing discards the outcome.
  - The images live in a temporary folder that is removed on close.

| Check | Result |
|---|---|
| `tests/test_local_experimental_preview.py` | 24 OK, of which 8 new |
| What the new service tests cover | the drawn record is the selected record of the selected set (two dataset-55 sets, compared with the importer's own loading); X / Y refused for Z-only data with no image; only the points where a component is measured are drawn (a partial mask); real pyuff dataset 2414 normal modes (including a Z-only record); FRF PROVISIONAL; AMBIGUOUS kept; points on one line refused for the out-of-plane view; fewer than three points, a record not in the set and a cancel stated, with no image |
| `tests/test_app_data4_mode_shape_view.py` | 5 OK, in the real main window |
| What the window tests cover | button state; the drawing follows the selection; set change clears the picture; component change; X refused; main window, file and registry unchanged; a superseded drawing never shown and its image removed; FRF and AMBIGUOUS banners; no spatial view stated; closing while drawing (no Tk error, nothing left behind) |

## Limits

- **A read cannot be interrupted** inside the importer's single call; closing the window only discards its outcome.
- **The importer writes its existing parse cache.** The installed importer (`fast_cache`) stores a parsed copy of
  the file in the user's local cache folder (`%LOCALAPPDATA%\AbaqusModalComparator\cache`), as it does for every
  analysis. The input file, the project file and the registry are not written.
- **The shape view is a picture only.** It is not saved or exported, and a drawing already started is not
  interrupted; closing only discards it.
- **The out-of-plane view needs a plane.** The normal is that of the best-fit plane of the drawn points, as in the
  main window. Points on one line are refused here; for points that are far from a plane, the X / Y / Z views are
  the meaningful ones. The main window's individual-mode viewer is not changed by this step.
- **FRF peak snapshots are not validated fitted modes.** They must not be used as Auto-ID observations; the view
  labels them PROVISIONAL.
- **Unchanged:**
  - SPEC v1.2, DECISIONS, the specimen catalogue, registrations, frozen evidence, MAC, pairing and QC criteria;
  - M8 GATE `NOT_MET`; D-077 `NO_GLOBAL_PARAMETER_VALUE`; production Auto-ID BLOCKED / NOT_AUTHORISED.
- No Abaqus, no solver, no LM, no Auto-ID.
