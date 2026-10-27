# APP-CATALOG.2 — local file selection from a specimen passport (2026-10-28)

Branch `feature/app-catalog2-local-file-selection` from `main` `566d0c5`. A user-interface addition: no FE
calculation, import, MAC, registration, Auto-ID, threshold or scientific decision is changed.

## What the user does

In the fifth Home area, **5 Specimen catalogue / Паспорт образца**, below the specimen list, is **Local source
selection**:

1. **Choose a specimen** in the specimen list.
2. **Choose a source.** The list holds the FE and experimental file references of that specimen in the accepted
   catalogue, one per session and data set, for example:
   - `Experiment · 260909 · PolyMAX fitted modes (dataset 55) · SP13_polymax.unv`;
   - `Experiment · 260910 a · PolyMAX fitted modes (dataset 55) · SP13_a_polymax.unv`.

   For the chosen source, Home shows:
   - the source kind and session;
   - the catalogue path, with store, size and short hash;
   - whether a reference SHA-256 exists;
   - the data status recorded in the catalogue (raw FRF or PolyMAX modal fit, the governed set, FREQUENCY_ONLY,
     usability);
   - for SP-15, its AMBIGUOUS identity.
3. **Locate local file....** The standard file dialog opens. The user names the file. The program checks only that
   file (see below).
4. **Use.** Only **Use as FE input** (for an FE source) or **Use as experimental input** (for an experimental source)
   changes one field of 1. Files, which Home shows at once. The other field is never touched.

Nothing is loaded or run by these steps. The analysis still starts only with **Run analysis**.

## Which sources can be used

| Recorded file | Listed as | Can be located and used |
|---|---|---|
| `.unv` / `.uff` experiment (raw FRF or PolyMAX) | experimental source | yes, as experimental input |
| PolyMAX export inside a ZIP (`zip_member`) | experimental source, named by the member | yes: the user extracts the member and locates the extracted `.unv`; its SHA-256 is compared with the member's |
| `.odb` | FE source | yes, as FE input |
| `.inp`, `.cae`, `.jnl`, CAD (`.x_t`, `.SLDPRT`) | FE file, "not an input" | no: not modal results |
| `.svd` camera frame | experimental file, "not an input" | no: a geometry record, not modal or FRF data |

- **No manifest.** An extracted `manifest.json` is never offered as a catalogue source and is never assigned to a
  specimen by its folder name. Choosing a `manifest.json` stays the existing **Choose...** / **Browse** of 1. Files.
- **No archive.** A ZIP is never unpacked and never passed to the UNV reader.

## The check of the located file

Only the file the user names is examined. No disk, store or folder is searched. The file is opened read-only, and
its SHA-256 is computed in 1 MiB blocks.

| Result | When | Use |
|---|---|---|
| `BYTE_VERIFIED` | the full SHA-256 equals the catalogue reference of that source (of the member for a ZIP source) | allowed |
| `HASH_MISMATCH` | a different SHA-256 (a different size already proves it, without hashing) | blocked |
| `NOT_VERIFIED_NO_REFERENCE` | the catalogue records no SHA-256 (for example the large ODB files) | only after a separate warning is confirmed (default **No**); never called verified |
| `FILE_MISSING`, `UNREADABLE` | no such file, a folder, or a read error | blocked |
| `UNSUPPORTED_TYPE` | an extension other than the source's (`.zip` for a member, `manifest.json` or `.inp` for an `.odb` source) | blocked |
| `NOT_AN_INPUT` | the source itself is not an input (INP, CAE, SVD, …) | blocked; **Locate** is disabled |

- **Size and name** are shown for a source without reference as a hint only, never as proof of identity.
- **Checked again before Use (APP-CATALOG.2-F1).**
  - **A `BYTE_VERIFIED` file** gets its full SHA-256 computed again just before **Use**, and compared with the
    reference of the source. Size and modification time are not trusted: other bytes with the same size and the
    same time are found too.
  - **On any other outcome** (another SHA-256 or size, a deleted file, a read error) **Use** is refused. The check
    becomes `HASH_MISMATCH`, `FILE_MISSING` or `UNREADABLE`, so `BYTE_VERIFIED` no longer stands and **Use** is
    disabled. The message asks to locate the file again, and no field of the program changes.
  - **A file without reference** (`NOT_VERIFIED_NO_REFERENCE`) has nothing to hash against. If its size or time
    changed since **Locate**, it is refused before the warning; otherwise the warning and the explicit confirmation
    stay as before. It is never called verified.
- **Byte identity is not a scientific confirmation.** Every `BYTE_VERIFIED` message says so. A verified file
  confirms neither the FE-experiment pairing, the modal set, the registration nor the orientation.

## One contract for changing an input

The owner of `_choose_abaqus` / `_choose_experiment` is `src/app.py`; no install layer replaces them. Each handler
only sets `abaqus_path` / `experimental_path`. **Use** sets the same variable with the checked path, as the File >
Input file registry does. Every existing reaction therefore runs unchanged:

- an established result becomes inactive (P-1);
- the experimental modal sets are discovered again;
- the export is disabled;
- readiness and Home are refreshed.

A test compares the window after **Use** with the window after setting the same path through the Browse contract:
every variable is equal.

## What is never done

- **Inputs:** no automatic FE-experiment pair; both fields are never filled together. No modal set is chosen, and
  no physical or historical registration is applied.
- **Inference:** no orientation is inferred from MAC or frequencies.
- **Processes:** no Abaqus, extraction, solver, LM or Auto-ID starts.
- **Statuses:** no scientific status changes. SP-13 260909 stays FREQUENCY_ONLY and separate from 260910 a *Best*;
  SP-08 stays not governed; SP-15 stays AMBIGUOUS.
- **Files:** nothing is written to an ODB, UNV, INP, CAE or any measurement. `docs/auto_id/specimen_catalog.json` is
  only read.
- **Registry:** the **File > Input file registry**, a separate list of the user's own files, is neither read nor
  changed.
- **During an analysis:** **Locate** and **Use** are disabled, like the other input controls.

## Code

- **`src/services/specimen_catalog_view.py`:** `local_sources`, `source_choice_text`, `source_lines`. These list
  the recorded sources of a specimen; nothing is read from the files.
- **`src/services/specimen_catalog_local_files.py`** (new): `check_local_file`, `sha256_of`, `allowed_suffixes`,
  `unchanged_since`.
- **`src/home_dashboard.py`:** the *Local source selection* controls (`select_source`, `locate_local_file`,
  `use_local_file`). No `install_*` layer was added.

## Validation

- **`tests/test_app_catalog2_home.py`** (27 tests, 5 added by F1, synthetic files; the accepted catalogue is checked unchanged after
  every check test).
  - Sources:
    - SP-02 (PolyMAX reference SHA, ODB without SHA, INP/CAE/JNL/SVD not inputs);
    - SP-13 260909 and 260910 a apart;
    - SP-08 not governed;
    - SP-12 none;
    - SP-15 AMBIGUOUS;
    - all 14 specimens.
  - Checks:
    - `BYTE_VERIFIED`;
    - the real SP-02 reference rejecting another file;
    - a wrong SHA of the same size;
    - no reference;
    - a missing file, a folder, unsupported types;
    - not-an-input sources;
    - a zip member through its extracted copy, the ZIP refused, and the 260909 member refused for 260910 a;
    - block-wise read-only hashing;
    - a changed file;
    - F1: the full re-hash before use (unchanged, other bytes with the same size and time, another size, deleted,
      read error, no reference).
  - Home on the real main window:
    - nothing changes before **Use**;
    - **Use** sets only its field;
    - the old result becomes inactive (P-1);
    - confirmation of an unverified FE file, declined and accepted;
    - mismatch, missing file and cancel change nothing;
    - F1: an unchanged verified file is hashed once more and used. Other bytes with the same size and restored
      time, another size, a deleted file and a read error are refused: BYTE_VERIFIED is withdrawn, and FE/UNV, modal
      set, result, project state and status are unchanged. A file without reference is not hashed and keeps its
      warning (declined, refused after a change, accepted);
    - **Use** equals the Browse contract;
    - locking during an analysis;
    - registry and Run patched to fail; no process (patched).
- **Windows GUI smoke.** `RUN_PROGRAM.cmd`, isolated profile, synthetic FE manifest and UNV at start, SHA-verified
  copies of the SP-02 and SP-13 260910 a PolyMAX exports. The file dialog was answered by a test hook; no native
  dialog was opened.
  - SP-02 PolyMAX: `BYTE_VERIFIED`, then **Use as experimental input**.
  - SP-13 260909 member with the 260910 a copy: `HASH_MISMATCH`, **Use** disabled.
  - SP-13 260910 a: `BYTE_VERIFIED`, then **Use**.
  - SP-02 ODB with a synthetic stand-in: `NOT_VERIFIED_NO_REFERENCE`; the warning answered **No** (nothing changed),
    then **Yes** (FE field set).
  - No modal set was chosen, no analysis ran, and no child process started; exit code 0.
  - The copies and the catalogue are byte-unchanged.

## Limits

- **Hashing time.** Hashing runs on the window's thread, at **Locate** and again at **Use**. Only files whose size
  equals the reference size are hashed; the largest recorded reference is about 40 MB.
- **Between the re-hash and the read.** The file is checked again at **Use**. A change made after **Use** (before
  the analysis reads it) is outside this check, as for any file chosen with **Browse**.
- **No hash for large ODB files.** The catalogue records no SHA-256 for its large ODB files, so these can only be used
  as `NOT_VERIFIED_NO_REFERENCE`.
- **No ZIP extraction.** A ZIP member must be extracted by the user.
