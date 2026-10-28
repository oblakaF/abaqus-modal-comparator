# NEW-GUI.2 — viewing the loaded FE and experimental data (2026-10-29)

Branch `feature/new-gui2-modal-preview` from `main` `71592ce`. **Status: REVIEW_READY.**

After choosing files, the user of the new interface (`RUN_NEW_GUI.cmd`) can click **Inspect file** on either side.
The window then shows the modal data that was really read: mode numbers, frequencies, modal sets and the importer's
messages. Before this stage it showed only the file name and type.

The content is read with the same importer as the existing program. That needed one shared service, described first.

## One importer for both programs (`services.importer_runtime`)

### The problem

`services.local_experimental_preview` reads with `universal_reader.load_universal_modal_file` "as installed". The
existing program installs that importer when `src/main.py` is imported: five process-level layers replace functions
of `universal_reader` and `abaqus_bridge`. The new interface does not import `main.py`. Without those layers it would
read other data than the analysis does. This was checked on the verified copies before this stage:

- **SP-04 (FRF data only, dataset 58).**
  - The bare importer finds 28 FRF peak records.
  - The application's chain finds 19.
- **Synthetic dataset-2414 file in pyuff's positional layout.**
  - The bare importer reads no mode at all.
  - The chain reads it (`tests/test_importer_runtime.py`).

### The decision

Option 1, with the fast cache, was decided by the owner on 2026-10-29.

`src/services/importer_runtime.py` holds `ensure_application_importers()`. It calls the five existing installs,
strictly in this order:

1. `universal_hardening.install_universal_hardening`: dataset 55/2414 parsing, FRF peaks, FRF group, coherence and
   the loader;
2. `universal_frf_review.install_frf_review`;
3. `cmif_separation.install_cmif_separation`;
4. `cmif_validation.install_cmif_validation`. Layers 2–4 chain `universal_reader._modes_from_frf_datasets`;
5. `fast_cache.install_fast_cache`: the memory and disk cache of the UNV and extracted-package loaders.

How the service behaves:

- **No new layer and no new algorithm.** The service replaces no function itself; it only calls the existing
  installs.
- **Idempotent.** Each install keeps its own `_INSTALLED` flag, so a second call changes nothing.
- **Order guarded on the functions themselves (NEW-GUI.2-F1).**
  - The first version checked only the layers' `_INSTALLED` flags. Those say which layers ran, not in which order:
    with cmif_validation installed before cmif_separation, all five flags are set, but the FRF chain is reversed.
  - `chain_problems()` now compares, before and after installing, every function the layers replace with the chain
    that the application's order gives for the layers installed so far. Those functions are:
    - `universal_reader.load_universal_modal_file`;
    - `universal_reader._modes_from_frf_datasets`;
    - the six hardening functions;
    - `abaqus_bridge.load_extracted_odb`.
  - It also checks the predecessor each layer saved: `universal_hardening._ORIGINAL_LOAD`,
    `cmif_separation._ORIGINAL_MODES_FROM_FRF`, `cmif_validation._ORIGINAL_MODES_FROM_FRF` and the two
    `fast_cache._ORIGINAL_*` references.
  - Any difference is refused (`ImporterOrderError`, naming each wrong link) and nothing more is installed. This
    covers a reversed order, a layer installed out of turn, and a function replaced after a correct installation.
- **Nothing written at install.** The fast cache creates its folder and files only when a file is read.

`src/main.py` now calls `ensure_application_importers()` where it used to call the five installs. The rest of its
initialisation is unchanged:

- performance tuning, reporting hardening, amplitude correlation and metrics normalisation;
- the reporting layers;
- `import app`;
- the UI layers;
- `verify_runtime_contracts`.

The new interface calls the same function. It never imports `main.py`, Tkinter or a UI layer of the existing
program.

### Late binding of the FE loader

`services.local_fe_preview` used to import `load_extracted_odb` by name when the module was first imported. If it was
imported before the chain was installed, it kept the uncached loader.

It now looks up `abaqus_bridge.load_extracted_odb` each time a package is read, through a module function with the
same name. The behaviour is unchanged; existing tests that patch `local_fe_preview.load_extracted_odb` still work.

### Proof of scientific equivalence

**Function owners.**
- After `ensure_application_importers()` the 57 functions of `universal_reader` and `abaqus_bridge` have the same
  owners as after `import main`. For example:
  - `load_universal_modal_file` is `fast_cache._cached_universal_loader`;
  - `_modes_from_frf_datasets` is `cmif_validation._validated_modes_from_frf`;
  - `load_extracted_odb` is `fast_cache._cached_extracted_odb_loader`.
- The old and the new `main.py` give the same owners for all 2402 function attributes of every loaded `src` module.
  The only additions are the two functions of the new service.

**Same previews on synthetic files** (`tests/test_importer_runtime.py`, fresh processes, isolated cache). These
files were read with `ensure_application_importers()` and with `import main`:
- FRF only;
- two dataset-55 sets;
- dataset 2414;
- an extracted package.

Every compared preview field and the scientific dataset metadata are identical between the two, and between the
first read, a read from memory and a read from the disk cache. Only the cache's technical metadata differ
(`unv_cache_reused` False / "memory" / "disk", `binary_odb_cache_reused`).

**Same previews on the verified copies** (read-only scratch copies; SHA-256 checked against their record before and
after; size, mtime and SHA-256 of all 68 files unchanged; cache in isolated folders).

| File | Preview (both ways) | First = memory = disk, `ensure` = `main` |
|---|---|---|
| SP-02 UNV | 3 dataset-55 sets, shown separately | identical |
| SP-13 UNV | 2 dataset-55 sets, shown separately | identical |
| SP-04 UNV (dataset 58 only) | 19 FRF peak-derived records, all PROVISIONAL | identical |
| SP-02 `manifest.json` | 10 modes (6–15), no diagnostic message | identical |
| SP-04 `manifest.json` | 19 modes (7–25), no diagnostic message | identical |
| SP-13 `manifest.json` | 24 modes (7–30), no diagnostic message | identical |
| synthetic FRF | 6 FRF peak-derived records, PROVISIONAL | identical |

- **SP-04.** The new interface reproduces the active chain's 19 records: 9.6875, 15.625, 58.125, 143.4375, 161.25,
  170.625, 185.3125, 273.75, 282.5, 298.125, 384.6875, 408.75, 473.125, 575.3125, 685.625, 741.875, 765.625, 947.5
  and 976.875 Hz.
  - Every record is `FRF_PEAK_RESPONSE_SNAPSHOT`, shown as "PROVISIONAL — NOT A VALIDATED FITTED MODE".
  - None is declared a confirmed mode.

## What the user sees

1. **The start stays empty.**
   - No file, no preset, no automatic reading and no cache: the importer chain is installed only when a file is
     read.
   - **Inspect file** is disabled until a file is chosen.
2. **A file is chosen, not read.**
   - The card says "File chosen; content not checked".
   - A content panel below the cards says "Not read yet. Click Inspect file to read the file's modal data."
3. **Inspect file** (on the card, or File > Inspect FE file Ctrl+Shift+1, File > Inspect experimental file
   Ctrl+Shift+2).
   - The file is read in a background thread, so the window stays usable.
   - The badge says "Reading the file...".
   - Only one read per side runs at a time. After the read, the button offers "Inspect again".
4. **FE content.**
   - The package path and FE source are shown in read-only fields, then the step.
   - A table lists Mode, Frequency (Hz), Frequency source and FE nodes, with the summary and the loader's messages.
   - Rigid-body modes are listed like the others.
   - **A plain `.odb`** is not read, and Abaqus is not started. The panel says that the modes can be read only from an
     existing extracted package, so the user should choose that package's `manifest.json` (with its CSV files) as the
     FE file.
5. **Experimental content.**
   - The panel shows:
     - the file;
     - for an `.lms`, the companion that was read;
     - the content kind;
     - the dataset types;
     - the geometry nodes.
   - Then one table per modal set: Mode, Frequency (Hz), Status (importer), Points, Measured DOFs, Damping (%).
   - **Several dataset-55 sets** are separate tables ("Modal set 1 of 3: ..."). None is chosen, nothing is merged,
     and nothing in a table can be selected or edited.
   - Experimental mode 1 is shown like every other record: nothing is excluded by the interface. Records the
     importer excluded (residual, non-modal) are listed as the importer's exclusions under the set.
   - **Dataset 2414**: each record keeps the importer's classification (physical, ambiguous, non_modal with its
     reason).
   - **FRF data (dataset 58) without a fitted set**: every record is "PROVISIONAL — NOT A VALIDATED FITTED MODE",
     with a note that these are response snapshots at FRF peaks.
6. **Replace, clear, close.**
   - Replacing or clearing a file resets its preview at once and cancels a running read.
   - Closing the window cancels the running reads.
   - An outcome that is not the current read of the current file is discarded and never shown.
7. **Long file names.** A long file name without spaces, such as the SP-04 UNV, no longer widens the page of a small
   window.
   - The card shows as much of the name as fits, and its tooltip holds the full name. The path field shows the end of
     the path.
   - The status-bar messages name the side ("Experimental data: content read"), not the file.
   - A Windows smoke at 150 % (900 × 680) found this; it is a NEW-GUI.1 behaviour that the earlier smoke's shorter
     names did not show.
8. **Unchanged from NEW-GUI.1.**
   - The optional specimen name, the research archive on request, the Analysis page ("Analysis not run") and the
     Status page.
   - English only.

Every panel states that the content is a preview only. Nothing is compared with the other side, no set or mode is
selected, paired or excluded, no MAC is computed, and the data are not declared ready for an analysis.

## Architecture

| File | Role |
|---|---|
| `src/services/importer_runtime.py` | `ensure_application_importers()`, `installed_layers()`, `ImporterOrderError` |
| `src/main.py` | One call of the shared function instead of the five installs |
| `src/services/local_fe_preview.py` | `load_extracted_odb` looked up when a package is read |
| `src/new_gui/preview_model.py` | No Qt. `read_preview` / `run_read` (the services after the chain), `InspectSlot` (current read, stale outcomes refused), the table rows |
| `src/new_gui/preview_panel.py` | The content panel: state, paths, facts, one read-only table per section, messages |
| `src/new_gui/window.py` | Inspect file buttons and menu actions, the background read, reset on replace / clear / close |

The new interface imports, besides NEW-GUI.1's modules, only `services.importer_runtime`,
`services.local_fe_preview` and `services.local_experimental_preview`. Nothing is computed again: the rows are the
services' own output.

## Cache effects

- The cache is the existing `fast_cache`, under `%LOCALAPPDATA%\AbaqusModalComparator\cache`. It is shared with the
  existing program.
- An empty start, choosing files, and installing the chain write nothing.
- Inspect file writes:
  - one `unv_*.pkl.gz` per UNV modal set;
  - one `odb_*.pkl.gz` per extracted package.
- **Existing `fast_cache` behaviour:** it keeps one extracted-package cache only. Reading another package replaces
  the previous package's `odb_*` file, as reading it in the existing program does. The next read of that other
  package is again a first read.
- **First-read times** on this machine:
  - SP-04 package about 35 s; SP-02 about 125 s; SP-13 about 300 s;
  - a UNV about 1–4 s;
  - a second read of the same package from its cache takes 1–20 s.

## Tests

- **`tests/test_importer_runtime.py`** (11 tests):
  - the order and that the service defines no layer;
  - `main.py` calls the shared function before the remaining initialisation;
  - same owners as `import main`, without `main` or Tkinter, and no file written by installing;
  - a foreign order is refused;
  - F1, each in a separate process:
    - cmif_validation installed before cmif_separation is refused although all five layers are installed, and the
      three wrong links are named;
    - a function replaced after a correct installation is refused;
    - the chain matches after `ensure` (also after a partial installation) and after `import main`;
  - the same previews as `import main` from memory and disk;
  - the cached FE loader is used even when the preview module is imported first;
  - late binding.
- **`tests/test_new_gui2_preview.py`** (17 tests, no Qt):
  - FE modes and warnings are the service's; a plain `.odb` is not read; a damaged package gives a message;
  - separate dataset-55 sets and experimental mode 1; dataset 2414 classification; FRF provisional; LMS companion;
    a damaged file;
  - cancellation;
  - `InspectSlot` stale, failed and cancelled reads;
  - importing the model reads, installs and writes nothing;
  - a read in a fresh process creates the cache only then and loads no old program.
- **`tests/test_new_gui2_qt.py`** (16 tests, Qt offscreen):
  - empty start without reading or cache; choosing does not read;
  - the FE table; the `.odb` message; separate, non-selectable set tables; FRF provisional;
  - the window stays usable while reading;
  - replaced, cleared or closed during a read: the read is discarded;
  - a new file shows nothing of the old one;
  - English only;
  - panels and a long file name add no width;
  - F1: every table column is reachable in a 900 × 680 window at 150 %, with a table scroll bar only when the
    columns do not fit, and none in a wide window;
  - F1: glyphs of the English text and of a Cyrillic file name. This test needs a font database, so it skips on
    `offscreen` under Windows, with the reason, and runs with `QT_QPA_PLATFORM=windows`.
- **`tests/test_new_gui1_workspace.py`**: the allowed modules and files of `src/new_gui` now include the three
  services and the two new modules.
- **CI.** The NEW-GUI.2 Qt tests run in the unit-test step with `NEW_GUI_REQUIRE_QT=1`, where a missing PySide6 is
  an error, not a skip.

## Readability on Windows (NEW-GUI.2-F1, 2026-10-29)

- **The □□□ screenshot.** It came from a check snapshot taken on Qt's `offscreen` platform under Windows. That
  platform has an empty font database (0 families, default font "Sans Serif" unresolved), so every glyph is drawn
  as a box.
  - The real `windows` platform has 250 families and resolves the default font to Segoe UI 9 pt.
  - It is not a defect of the interface, its fonts or its encoding, and nothing was changed for it.
  - Offscreen snapshots are not used as visual evidence.
- **The check.**
  - Real `windows` platform.
  - Captured from the Windows screen (ImageGrab of the window rectangle).
  - Cyrillic-named, byte-identical copies of verified inputs: `КЭ_пакет_SP04\manifest.json` and
    `Образец_SP02_эксперимент.unv`.
  - Windows at 150 % (native); 100 % and 125 % through Qt scaling on the same platform (`QT_ENABLE_HIGHDPI_SCALING=0`,
    `QT_SCALE_FACTOR=1` / `1.25`).
  - Windows of 900 × 680 and 1366 × 768 pixels, before and after Inspect file.
- **Result.**
  - No missing glyph in any state, including the Cyrillic names in the cards and the path fields.
  - No page-level horizontal scroll bar.
  - Every row of every table is shown.
- **Defect found and fixed.**
  - In a 900 × 680 window at 150 % the experimental tables need about 550 px, but only 301 px were available.
    Points, Measured DOFs and Damping were cut off with no way to reach them, and the FE header "Frequency source" was
    cut.
  - Now the status column (the FE frequency source) takes the free width, but never less than its header.
  - When the columns do not fit, the table scrolls horizontally per pixel, and its height includes that scroll bar.
  - Where the columns fit, no scroll bar is shown: 100 % and 125 % at 1366 × 768, 100 % at 900 × 680, and 150 % at
    1366 × 768.

## Not in this stage

- No analysis, no Abaqus, no solver, no LM and no Auto-ID.
- No automatic FE↔EXP matching, no MAC and no mode pairing.
- No conclusion about a physical registration.
- No change to the importer, CMIF/FRF algorithms, `fast_cache`, scientific criteria, registrations or frozen
  evidence.
- No mode-shape drawing in the new interface. The services' shape views stay in the existing program.

## Limits

- **Cache size.** A read of a large package fills the shared user cache, and only one package cache is kept.
- **Long first reads.** An extracted package of a fine mesh can take minutes. The window stays usable, and the user
  can replace or clear the file to stop the read.
- **Late cancellation.** Cancellation is checked by the services between steps. A read that is cancelled late still
  finishes in the background, and its outcome is discarded.
- **`application_layers.install_application_layers`** (used by some tests) still calls the same five installs itself,
  followed by two more. It is outside this stage's files. Its order is the same, and the shared function accepts the
  layers it installed.
