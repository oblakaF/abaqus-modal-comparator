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

## Limits

- **Only what the loader loads is shown.**
  - When the loader refuses the whole package, the window shows its error and no modes. For example, a mode file
    with a zero frequency fails the existing `ModeShape` check.
  - No partial interpretation is attempted.
- **Cancellation is cooperative.**
  - The loader checks the cancel event between modes; a single large CSV is read to its end.
  - The thread is a daemon and holds no window object.
- **Mode shapes are read but not shown.** The view lists numbers, frequencies and node counts only.
- **Unchanged:**
  - SPEC v1.2, DECISIONS, the specimen catalogue, registrations, frozen evidence, MAC, pairing and QC criteria;
  - M8 GATE `NOT_MET`; D-077 `NO_GLOBAL_PARAMETER_VALUE`; production Auto-ID BLOCKED / NOT_AUTHORISED.
- No Abaqus, no solver, no LM, no Auto-ID.
