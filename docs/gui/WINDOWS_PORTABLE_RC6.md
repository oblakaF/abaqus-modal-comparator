# WINDOWS PORTABLE RC6 — direct import of an Abaqus ODB (PRIORITY-0)

RC6 is RC5 (the single-plate research workbench, `WINDOWS_PORTABLE_RC5.md`) plus one operational feature: the new
interface accepts an Abaqus `.odb` as the FE file and extracts its modal results itself, on the user's command, with
the project's existing extractor. The user no longer creates a `manifest.json` by hand or runs a Python script.

RC5 and RC1–RC4-F1 are not changed: their packaging is checked by SHA-256 in `tests/test_windows_portable_rc6.py`, and
`PROTECTED_DESKTOP` refuses to write their desktop copies. The scientific allowances, MAC, SPEC, DECISIONS, Auto-ID,
frozen registrations and research results are untouched; the extractor `abaqus_scripts/extract_odb.py` is unchanged.

## The user scenario

1. **Workspace > FE results > Choose file...** accepts an `.odb` (filter "Abaqus ODB or extracted FE package"). The
   card shows the type "Abaqus output database (.odb) — its modal results are extracted on your command", a note and
   the button **Extract modal results...**. Choosing the file starts nothing; Inspect file on an `.odb` only points to
   the button.
2. **Extract modal results...** opens the dialog. It shows, without starting anything:
   - the ODB and its size;
   - the Abaqus launcher found by name (PATH, `C:\SIMULIA\Commands`, Dassault SimulationServices; the existing
     `ui_policy.discover_abaqus_installations`), or **"No Abaqus launcher was found"** with three fixes (install
     Abaqus here or run the program where it is installed; Browse to a launcher elsewhere; extract on another
     computer and choose the package's manifest.json). Browse... lets the user point to a launcher;
   - the results folder (Choose folder...), the mode range (default 1–30: the first elastic mode, for example FE7, is
     never skipped; rigid-body modes are included and separated later by the comparator), the extraction script and
     the free space (at least 200 MB or half the ODB size).
3. **Extract modal results** asks for an explicit confirmation ("Abaqus Python will be started now ... Start it?").
   **No** starts nothing. **Yes**: the ODB is identified by content (SHA-256, streaming, cancellable), a package of
   the same content and range already in the results folder is **reused without starting Abaqus**, otherwise
   `abaqus_bridge.run_abaqus_extraction` runs the packaged extractor through Abaqus Python (`readOnly=True`) into a
   **new** sub-folder `<odb name>_modes_<first>-<last>[_N]` — nothing is overwritten. The extractor's PROGRESS lines
   are shown; **Cancel extraction** stops the owned process (the bridge's process ownership) and marks the folder
   `INCOMPLETE.txt` (kept for inspection, never reused).
4. The result shows the package, the requested range, the **extracted range** (clipped to the modes the ODB holds),
   the range the extractor reported in the ODB, the ODB SHA-256 and the log. `extraction_source.json` beside the
   package records the ODB path, size, modification time and SHA-256, the launcher, the ranges, the time and the
   extractor's SHA-256.
5. **Use this package** puts the package's `manifest.json` into the Workspace as the FE file and reads it (Inspect
   file): the modes, the frequencies and the shapes (U1 / U2 / U3 of any loaded mode) are those of any extracted
   package, with the package identity recorded as before. Then a UNV / UFF and the frequency diagnostic as before.
6. Errors are messages, never a hang: no modal results in the range (the extractor's "No frequency-extraction
   frames" is explained), an Abaqus failure (the log tail), no space, a cancellation.

A `manifest.json` can still be chosen directly. `services.odb_import_service.verify_source(package)` hashes the ODB
again and reports a change **by content**, also when size and modification time are unchanged.

## Build

```
D:\git\abaqus-modal-comparator-work\build\portable_rc1\venv\Scripts\python.exe packaging\portable_rc6\build_portable.py --out <new folder outside the repository>
```

`packaging/portable_rc6` follows RC5 and adds the extractor: `abaqus_scripts/extract_odb.py` is copied beside the
program (`<portable>\abaqus_scripts\`), where the frozen `abaqus_bridge` resolves it
(`_internal\abaqus_bridge.pyc` → `parents[1]/abaqus_scripts/extract_odb.py`), and checked (byte-identical to the
repository's, `readOnly=True`). The program starts without Abaqus; only the extraction needs its Python.

| Item | Value |
|---|---|
| Base | RC5 `3d4e38be35b0347b4c34c088b0ebbf320c581043` (`main` `0bea1de68dc346d20958e6f53a9e1d634a870f5d`) |
| Build commit | `4a90ea2a6ba0aeae7b5620159a5ad38ea79eb5dc` (`feature/rc6-direct-odb-import`, clean tree) |
| Build folder | `D:\git\abaqus-modal-comparator-work\build\portable_rc6\dist\AbaqusModalComparator_RC6\` — 751 files, 243 926 775 bytes |
| EXE | `AbaqusModalComparator.exe`, 17 715 714 bytes, SHA-256 `a7a5c2304691dd19868dee2a1143899dc52b385e5b88edcb415261748ad2e82d` |
| ZIP | `AbaqusModalComparator_RC6.zip`, 105 974 319 bytes, SHA-256 `f8590e7ca48c6ca5d3eaf77f43b152ed70f59bb4730bdc52cbf984b8db998e86` |
| Extractor in the build | `abaqus_scripts\extract_odb.py`, SHA-256 `039aa067adeac83e457ccacc9036c767f98c41517fb1ffdd5293fdd01dc6534d`, resolved by the bridge at that path |
| Python / PyInstaller / PySide6 | 3.14.6 / 6.22.3 / 6.12.0 (as RC5) |
| Desktop | not copied (the owner keeps RC5.zip there); RC5 unchanged |

Unpacked from the ZIP into a path with spaces (`…\WINDOWS_PORTABLE_RC6_REVIEW\release 4a90ea2\Copied to another
place\`) and into a path without spaces (`…\release_4a90ea2_nospace\`): `--verify` 750 / 750 in both.

## Acceptance of the EXE (no Abaqus started)

The real launcher of this computer (`C:\SIMULIA\Commands\abq2024.bat`) was **never run**: before Extract modal
results was clicked, the dialog's launcher field was set to a fake launcher (a `.cmd` that runs a stand-in script
with the system Python: it writes the worker registration, copies the read-only M11 FE package copy into the output
folder clipped to the requested range, prints the extractor's PROGRESS lines, and never opens the ODB). The harness
aborts unless the dialog names that fake path as the launcher it will run. Clean environment (no Python, repository
or SIMULIA on PATH; isolated LOCALAPPDATA; `AMC_OPEN_AUDIT`), Windows 10 at 150 %, UI Automation. Inputs: the
read-only M11 copies (`…\INTEGRATION_RC1_REVIEW\moved inputs\`: the ODB copy `CFRP_S4R_0875_FreeFree.odb`, the UNV
copy of 261027).

Results: `…\WINDOWS_PORTABLE_RC6_REVIEW\release_4a90ea2_nospace\exe_smoke_run_5\rc6_exe_smoke.json` and screenshots.
(Runs 1–4 stopped on defects of the smoke harness itself — the fake launcher's argument parsing, the cancel timing,
the mode combo, the modal-set choice — and on the quoting defect below; none of the program.)

| Step | Result |
|---|---|
| Start, six pages | PASS |
| The ODB chosen | the type, the note and Extract modal results... shown; nothing started |
| The dialog as opened | "Choose a results folder" (no plan yet); the button disabled |
| With a results folder | plan shown: ODB 5.6 MB, launcher found "Abaqus 2024 — detected ✓" (`abq2024.bat`), script in the portable folder, free space; the button enabled; **nothing ran** |
| Cancel during a run | with the fake launcher (slow marker): confirmed, started, cancelled → CANCELLED, the folder marked INCOMPLETE, no package |
| The extraction | confirmed → progress → package `CFRP_S4R_0875_FreeFree_modes_1-30`, extracted 1–20 (the ODB's 1–20), `extraction_source.json` with SHA-256 `7daeb7e3…` = the ODB copy's content (and the frozen M11 record) |
| Use this package | the FE file is the manifest; "Content read; preview only"; "18 modes loaded (3–20)" — the loader refuses modes 1 and 2 whose manifest frequency is the extractor's frameValue fallback of a zero-frequency frame (its existing rule, shown as messages); FE7 19.0722 Hz; the shape of mode 7 as U3 and as U1 (10201 FE nodes) |
| UNV + frequency diagnostic | the set Polymax_bravo (11 records): FREQUENCY_ONLY_DIAGNOSTIC, EXP1 18.6307 Hz nearest FE7 19.0722 Hz (+2.37 %), as RC5 |
| The same ODB again | the package reused, Abaqus not started |
| Close | exit 0; no Abaqus process at any time; inputs unchanged (SHA-256 of the ODB copy the same) |

Open-file audit: nothing in the repository or an installed Python; the ODB copy opened only for its SHA-256 (by the
program) and by the fake (never); `C:\SIMULIA\Commands\abaqus.bat` and `abq2024.bat` were **read as text** by the
existing launcher detection (`ui_policy._referenced_launcher`, which follows batch wrappers), not executed.

### Not shown on the EXE

- **No Abaqus on this computer**: it has Abaqus, so the dialog's "No Abaqus launcher was found" state is covered by
  the offscreen tests (`test_new_gui_odb_import_qt.py`), not by the EXE smoke.
- **A real ODB end to end**: not run. The owner has not authorised an Abaqus run; RC6 is **not verified on a real ODB
  with Abaqus**. The route up to and after the Abaqus call is verified; the call itself is the unchanged bridge.

## Defect found (not fixed here: outside the allowed files)

`abaqus_bridge._windows_command` wraps the launcher line in `cmd.exe /d /s /c <line>` as a list; `subprocess`
quotes that line again, so a path with a space becomes `\"D:\\a b\\x.odb\"`, `cmd /s` strips the outer quotes and
the launcher receives `\"D:\a` `b\x.odb\"` — the extractor then fails on the arguments (observed with the fake
launcher in a results folder "results folder" and a portable folder "Copied to another place"). It affects the ODB
path, the results folder and the portable folder when any contains a space, and the existing RUN_PROGRAM.cmd route
too. Minimal fix (owner's decision): pass the command to `Popen` as one string, `f'cmd.exe /d /s /c "{line}"'`, so no
second quoting happens. Until then RC6 extracts correctly only when the three paths have no spaces; the dialog does
not yet warn about it.

## Tests and CI

- `tests/test_odb_import_service.py` (16): detection, plan, no confirmation / no Abaqus / no space / bad range refuse,
  a confirmed run with its record, reuse, a changed content extracted again, an incomplete package not reused,
  errors and cancellation, the content re-check.
- `tests/test_new_gui_odb_import_qt.py` (10): the dialog (plan, no Abaqus + Browse, refused confirmation, run with
  progress, failure, cancellation, the user's range) and the window (ODB → dialog → Use → read, U1/U2/U3 offered;
  Inspect of an ODB points to the extraction; a manifest still imported).
- `tests/test_windows_portable_rc6.py` (6): the RC6 build, RC1–RC5 unchanged, the extractor packaged where the bridge
  resolves it and unchanged.
- Regressions: the new GUI tests (1–6), `test_windows_rc1_a`, `test_local_fe_preview`, `test_abaqus_cancellation`,
  `test_process_ownership`, `test_extraction_cache_reuse`, `test_frf_import`, `test_polymax_modal_sets`,
  `test_universal_hardening`: OK.
- Full suite on `4a90ea2`: 3347 tests, 1 failure in `test_app_catalog2_home…test_use_is_exactly_the_browse_contract`
  (the existing Tk home dashboard; timing). Measured alone with a fresh LOCALAPPDATA: 4 / 8 OK on the unchanged RC5
  base `3d4e38b`, 7 / 8 OK on RC6 — flaky before RC6, unrelated to it.
- CI: see the report.
