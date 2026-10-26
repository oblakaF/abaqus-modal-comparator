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

## Limits

- **A read cannot be interrupted** inside the importer's single call; closing the window only discards its outcome.
- **The importer writes its existing parse cache.** The installed importer (`fast_cache`) stores a parsed copy of
  the file in the user's local cache folder (`%LOCALAPPDATA%\AbaqusModalComparator\cache`), as it does for every
  analysis. The input file, the project file and the registry are not written.
- **Mode shapes are read but not drawn.** The view lists numbers, frequencies, classifications, points and measured
  DOFs.
- **FRF peak snapshots are not validated fitted modes.** They must not be used as Auto-ID observations; the view
  labels them PROVISIONAL.
- **Unchanged:**
  - SPEC v1.2, DECISIONS, the specimen catalogue, registrations, frozen evidence, MAC, pairing and QC criteria;
  - M8 GATE `NOT_MET`; D-077 `NO_GLOBAL_PARAMETER_VALUE`; production Auto-ID BLOCKED / NOT_AUTHORISED.
- No Abaqus, no solver, no LM, no Auto-ID.
