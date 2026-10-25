# APP-DATA.1 — local input file registry (2026-10-25)

Branch `feature/app-data1-local-input-registry` from `main` `9721668`. A program convenience, not a scientific stage.

## What it does

**File > Input file registry...** opens a small window with the user's own list of input files:

- **FE result:** an Abaqus `.odb` or an extracted `manifest.json`.
- **Experimental result:** `.unv` / `.uff`, or a `.lms` project whose companion UNV / UFF lies beside it (the same
  rule as 1. Files, `universal_reader.resolve_testlab_file`).

The buttons:

- **Add FE file...** / **Add experimental file...** — a person chooses the file in the file dialog and gives it a
  name; the file name is the default.
- **Use in 1. Files** (or a double click) — fills the matching field on 1. Files and shows that tab.
- **Remove from registry** — removes only the reference. The file itself is never touched.

The list shows the kind, the name, whether the file is there now (`found` / `missing`) and the path.

## How it is kept

- One JSON file per user: `~/.abaqus_simcenter_modal_comparator/local_input_registry.json`. It is outside Git, the
  project file and every data store, next to the other per-user files of the comparator.
- An entry holds only its id, kind, name, path and time of adding.
- The file is written atomically (temporary file + replace).
- The project file (`.amcp.json`) and the last session are unchanged. They keep the inputs of one project; the
  registry is a list of files across projects.

## How using an entry works

**Use** sets the field's variable, exactly as the field's Browse button does. The existing reactions therefore apply
unchanged:

- a different file clears the shown result and disables its export (P-1);
- the same file chosen again keeps it;
- the modal sets of an experimental file are discovered as after Browse;
- the series review of 1. Files follows the new file.

Nothing is loaded, compared or run, and no Abaqus or other process is started.

## Rules

- **Not a scientific catalogue.**
  - An FE entry and an experimental entry are independent; no entry refers to another.
  - Two entries do not establish that a model and a measurement belong to the same specimen, test or mode pair.
  - No pair, MAC, orientation or material property is derived. `docs/auto_id/specimen_catalog.json`, registrations
    and evidence are not read or changed.
- **No content is read.** Adding or using an entry checks only the file name, its type and that it exists (for an LMS
  project, that its companion UNV / UFF exists). No drive, data store or folder is scanned.
- **The same file twice is one entry.** The comparison uses the normalised absolute path and the kind; the existing
  name is kept, and the dialog says so.
- **A missing file is a clear message.**
  - Use is refused and the field is left unchanged; nothing is substituted.
  - The entry stays, marked `missing`, until a person removes it.
- **A damaged registry is a clear error.** The file is checked on every read: valid JSON, an object with the schema,
  `entries` a list of complete entries of a known kind with distinct ids.
  - Anything else is an error that names the problem.
  - The dialog disables Add / Use / Remove.
  - The file is never rewritten or replaced; a person repairs or moves it.

## Changed files

- `src/services/local_input_registry.py` — new service.
- `src/menu_ui.py`:
  - `InputRegistryDialog`;
  - the File menu entry. It is added in the existing `_build_menu` of `install_menu_ui`; no new `install_*` layer.
- `tests/test_local_input_registry.py` — 16 tests on temporary synthetic files:
  - 8 service tests;
  - 8 tests in the real main window, which reuse the P-1 window harness.
- `src/ui_workflow.py` is not changed: the final owners of the file choice are `app._choose_abaqus` /
  `_choose_experiment`, which set the same variables, and the stale-result reset of `ui_workflow` reacts to those
  variables.

## Verification

| Check | Result |
|---|---|
| `tests/test_local_input_registry.py` | 16 OK |
| Covered by those tests | add and reopen; supported and refused types; the same file twice; missing file; damaged registry in 9 forms (never rewritten); FE / experimental independence; no file content read; File menu entry; Use fills only its field and runs nothing; another file clears the result, the same file keeps it; adding through the dialog; remove keeps the file |
| Regressions: APP-E2E.3 / P-1 / R7 / guided registration | 19 / 14 / 41 / 24 OK (1 store-gated skip) |
| Full unittest without `test_g2_eigfreq_precision` (it reads machine-local `-work` data: `NOT_RUN`) | 2534 OK, 96 skipped |
| `RUN_PROGRAM.cmd`, isolated profile with a registry of synthetic files | Native File menu: the registry item opens "Input file registry" with the entries, `found` / `missing` shown; the windows close cleanly, exit code 0 |
| Real main window: Use on the FE entry | Abaqus results filled, the experimental field unchanged, 1. Files shown, nothing run, no result, no Tk error |
| 11 tabs | all open, no Tk error |

## Limits

- **`manifest.json` is recognised by its name only.** Its content is not checked when it is added; the analysis checks
  it as before.
- **Identity is the path, not the content.** A file replaced at the same path is the same entry. A file moved or
  renamed outside the program becomes `missing`, and a person adds it again.
- **Single user.** Two windows writing the registry at the same moment may lose one of the two additions: each write
  rewrites the file read just before it.
- **The registry is per user and per machine.** It is not shared through the repository or a project file.
- **Unchanged:**
  - SPEC v1.2, DECISIONS, the specimen catalogue, registrations, frozen evidence, MAC, pairing and QC criteria;
  - M8 GATE `NOT_MET`; D-077 `NO_GLOBAL_PARAMETER_VALUE`; production Auto-ID BLOCKED / NOT_AUTHORISED.
- No Abaqus, no LM, no Auto-ID.
