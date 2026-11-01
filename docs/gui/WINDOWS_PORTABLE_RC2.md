# WINDOWS PORTABLE RC2 — portable build of the new interface with the SP-10 integration

**Status: REVIEW_READY.** Branch `feature/sp10-full-integration-portable-rc2`.

**The EXE is built from code commit `192de01`.** That commit contains:

- PRIORITY-7 `377c9e8`;
- the RC2 packaging fix `192de01`, under which the build's content check refuses `.npz` files only in `docs`.

Later commits on the branch change documentation only.

The folder `AbaqusModalComparator_RC2` is the new interface frozen by PyInstaller (onedir), with the approach of RC1.
It starts with no Python, VS Code or Abaqus installation, and it starts no Abaqus.

It contains the PRIORITY-7 integration (`PRIORITY7_SP10_RC2.md`). Research Results shows, for SP-10:

- the historical PRIORITY-1 table;
- the PRIORITY-6 FE results (FE7–FE25);
- the frequency-only diagnostic of EXP1–EXP12;
- the SHA-256 link to the Workspace inputs.

**RC1 is unchanged:**

- `packaging/portable_rc1` has the same SHA-256 for its five files (test);
- the desktop copies `AbaqusModalComparator_RC1` and its ZIP have the same SHA-256 before and after the RC2 build.

## Build

```
<build venv>\Scripts\python.exe packaging\portable_rc2\build_portable.py --out <build folder> --desktop
```

**Environment.** `packaging/portable_rc2/requirements-build.txt` pins the same versions as RC1: Python 3.14.6,
PySide6-Essentials 6.12.0, numpy 2.5.1, scipy 1.18.0, matplotlib 3.11.1, Pillow 12.3.0, openpyxl 3.1.5, pyuff 2.5.6,
pypdf 6.14.2, PyInstaller 6.22.3. The build used the RC1 build environment, which has those versions.

**Steps.** The script builds as RC1 does:

1. It refuses uncommitted program files.
2. It runs the spec `AbaqusModalComparator_RC2.spec`. Its hidden imports are the seven report layers, plus
   `services.research_results_reader` and `services.sp10_fe_research`.
3. It puts the tracked `docs` reference files beside the program. They are 192 files, 3.5 MB, among them
   `SP10_FE_PACKAGE.json` and `SP10_FE_VS_DAT.csv`.
4. It refuses measurement, FE model and solver files. In `docs` it also refuses `.dat` and `.npz` files and the files
   of an extracted FE package (`manifest.json`, `geometry.csv`, `mode_NNNN.csv`).
5. It loads the research tables of PRIORITY-1–4 and the PRIORITY-6 records from the built folder. The build check
   gives:
   - 19 FE modes;
   - 12 diagnostic rows;
   - EXP11 FE17 +0.98 % and EXP12 FE18 +0.11 %.
6. It writes `BUILD_INFO.json` and `README_PORTABLE.txt`, zips the folder and copies both to the desktop.

**The first build attempt** was refused by the content check. Its `.npz` rule also matched three matplotlib sample
files under `_internal`. Fix `192de01` limits the rule to `docs`.

| Item | Value |
|---|---|
| Commit | `192de0176ef4348d8201838589bb0f5ca340e0fe` (clean tree) |
| Folder | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC2\` — 712 files, 242 841 676 bytes |
| EXE | `AbaqusModalComparator.exe`, 17 395 383 bytes, SHA-256 `175e7b1aba2a9e4c1933a3900703084ce6801bad922d98aa5aaaf10508f20ba9` |
| ZIP | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC2.zip`, 105 451 416 bytes, SHA-256 `3c07d0b9a32f94e354156d0314649b4a7dbe5990371ea116a5032c947eaf8250` |
| RC1 (unchanged) | ZIP `e1c34b0d…`, EXE `c3fc0576…`, 710 files |

**Not included:**

- experimental files;
- Abaqus models and results;
- extracted FE packages, including the 3.1 GB SP-10 package of PRIORITY-6;
- solver files.

The user chooses them in the program.

## Acceptance of the portable EXE

**Setup:**

- the desktop ZIP (SHA-256 checked) was unpacked into
  `D:\git\abaqus-modal-comparator-work\research\PRIORITY7_SP10_RC2_REVIEW\release 192de01\Copied to another place\`,
  a folder outside the repository with spaces in its path;
- the EXE was started directly, with no Python or `.venv` on PATH and no `PYTHON*` / `QT_*` variable;
- isolated LOCALAPPDATA;
- working directory outside the repository;
- 150 % scaling (DPI 144), native dialogs, UI Automation;
- the files opened were recorded with `AMC_OPEN_AUDIT`;
- verified moved copies of the inputs; the SP-10 package was read in place.

| Step | Result |
|---|---|
| Start | 8.5 s; the window belongs to the EXE's own process; six pages |
| SP-02 | archived reference verified; **VERIFIED_COMPARISON, 6 pairs**; pair FE 10 / Exp 4 drawn; XLSX + PDF + JSON report |
| Materials | shown |
| RC1-A | `.odb` refused, no Abaqus; moved plate FE package; known-sources folder; FREQUENCY_ONLY_DIAGNOSTIC; registration not confirmed |
| Plate Study | moved FE archive, 8 / 8 verified; PHYSICAL_REGISTRATION_NOT_VERIFIED; estimation gate disabled; report exported |
| PLATE | 11 rows, verified banner; local record; rank 3 / 1.83 and 2 / 2.35; S0 / H1 / H2 |
| SP-13 | 12 rows, 12 HYPOTHETICAL_SAME_POINTS, NOT VERIFIED (FE only) |
| SP-10 without the package | archived frequencies; LOCAL PACKAGE NOT LOADED; link DO NOT MATCH |
| SP-10 package | Inspect: 19 modes (7–25), step SP_10_MODAL_FREE, EIGFREQ history; 255 s uncached; no Abaqus |
| Independent FE shapes | FE7 23.8859 Hz and FE17 265.036 Hz drawn on 1 667 491 nodes |
| SP-10 261029 | `polymax_bravo` 12 records; 12 experimental, 19 elastic FE; MAC NOT_COMPUTED; mode pairs NONE; registration not confirmed; verified comparison disabled |
| Research Results SP-10 | A: 12 historical rows, FE_SHAPES_UNAVAILABLE, historical banner NOT VERIFIED; B: **MATCH** + PHYSICAL_REGISTRATION_NOT_VERIFIED, package LOADED, FE7–FE25, EXP11 → FE17 +0.98, EXP12 → FE18 +0.11, 12 FREQUENCY_PROXIMITY_ONLY rows |
| Input replaced by the SP-13 UNV | link DO NOT MATCH (experimental file 8abf951dba4b…) at once |
| SP-10 UNV again | MATCH; modal set "none chosen … not claimed" |
| Sizes | no page scroll bar at 900 × 680 and 1366 × 768 |
| End | no Abaqus process; closed, exit 0; no EXE process left; every input unchanged |

**Open-file record (1974 files):**

- none from the repository, an installed Python or a `.venv`;
- none from the user's LOCALAPPDATA or program cache, from `D:\Snadwich` or from other work folders;
- reference files only from the portable `docs` (80 files), among them both PRIORITY-6 records;
- 21 files of the SP-10 package, read only through the Workspace;
- system fonts scanned by matplotlib, as in RC1;
- one relative `struct.py`, as in RC1.

**DLLs:** 147 from the portable folder. The rest come from Windows and from the Defender, Ink and Adobe shell
extensions.

**Evidence** (screenshots, `rc2_launcher.json`, `open_audit.log`, `open_audit_summary.json`) is in
`…\PRIORITY7_SP10_RC2_REVIEW\release 192de01\smoke run\`. It includes:

- `13_research_sp10_priority6.png` and `14_research_sp10_diagnostic_table.png`: the new SP-10 tables;
- `32_sp10_shape_fe17.png`: an SP-10 FE shape;
- `05_research_plate.png`: PLATE;
- `02_sp02_verified_comparison.png`: SP-02.

## Tests and CI

**Targeted tests, all pass:**

- `test_priority7_sp10_research` (23);
- `test_windows_portable_rc2` (6);
- `test_priority6_sp10_fe_shapes` (8);
- `test_priority5_research_results` (14);
- `test_windows_portable_rc1` (4);
- `test_new_gui1_qt`.

**Full suite.** It was run locally on the final code: 3174 tests, OK, 98 skipped:

- about 94 need local data stores that are not configured (snadwich, carbon-project-archive, m7-run…);
- 2 need the Abaqus integration (`ABAQUS_MATRIX_INTEGRATION=1`);
- 1 needs `NEW_GUI6_REAL_INPUTS`;
- 1 needs a font database that offscreen Qt lacks on Windows.

The synthetic tests are no physical validation.

**CI (Python tests):**

- `377c9e8`: run 41191708764, success;
- `192de01`: run 41191851188, success.

## Limits

- **Signing.** The EXE is not signed. SmartScreen may ask on first start.
- **Default folders.** The default folders (known sources, plate FE archive) are those of the development computer.
  Choose the folders in the program.
- **The SP-10 package is not part of the build.** It is about 3.1 GB and is chosen with its `manifest.json`. Its
  first uncached read takes about 4–5 minutes; the fast cache then takes about 0.7 GB in LOCALAPPDATA.
- **No physical registration of SP-10.** The frequency diagnostic is proximity only. No material value comes from it.
- **Not part of the build:** the old interface (`RUN_PROGRAM.cmd`), the Abaqus-side scripts and an installer.
- **Build warning.** PyInstaller warns that the hidden import `scipy.special._cdflib` is not found, as in RC1.
