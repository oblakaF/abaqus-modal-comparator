# WINDOWS PORTABLE RC5 — working version of the program for one single plate

RC5 is the portable new interface built from `main` after PR #122 (PRIORITY-1 to 10, the single-plate research
workbench). It is a **WORKING RESEARCH PREVIEW**: it shows, checks and exports research results of one single CFRP
plate, and it identifies no material value.

It contains the six pages (Workspace, Analysis, Status, Materials, Plate Study, Research Results) and the four Plate
Study tabs:

- **A. Current PLATE Study** — the archived PLATE study; the iterative estimation is NOT AUTHORISED;
- **B. New Single Plate** — the research workbench of any single rectangular CFRP plate, with its synthetic
  demonstration;
- **C. Physical Readiness** — the readiness review and dossier;
- **D. FE Response** — FE-to-FE branch tracking, central sensitivities and the G12 / E What-If.

RC1, RC2, RC3, RC3-F1, RC3-F2, RC4 and RC4-F1 are not changed:

- their 35 packaging files are checked by SHA-256 in `tests/test_windows_portable_rc5.py`;
- their desktop copies (folder digest, EXE and ZIP) are identical before the RC5 build, after it and after the EXE
  smoke;
- `PROTECTED_DESKTOP` refuses to write them.

## Build

```
D:\git\abaqus-modal-comparator-work\build\portable_rc1\venv\Scripts\python.exe packaging\portable_rc5\build_portable.py --out <new folder outside the repository> --desktop
```

`packaging/portable_rc5` follows the RC4-F1 approach:

- PyInstaller onedir, no console window;
- the tracked reference files (JSON / CSV / Markdown / text) are placed in `docs` beside the program;
- the build refuses measurements, FE models and results, extracted FE packages and solver files.

**What is new in the RC5 build script:**

- **Nothing is deleted or replaced.** There is no `--replace`. The build folder must be new or empty. An existing RC5
  desktop folder, ZIP or `.zip.sha256` is refused, and so is an existing ZIP.
- **Package list.** `PACKAGE_SHA256.txt` lists the SHA-256 of every file of the folder. `--verify <folder>` checks a
  copied or unpacked folder against it: missing, extra and changed files.
- **ZIP check.** The ZIP must hold exactly the files of the folder, each with an intact CRC.
- **FE Response check.** The PRIORITY-2 table that tab D compares with loads from the portable folder: 13 terms,
  FE7 f0 = 19.07217 Hz, source SHA-256 `5cba4070…`, rank 3 / 3 (condition 1.83) and 2 / 2 (2.35).
- **BUILD_INFO.json.** It records the full commit SHA, the dirty flag, the platform, the Python and package versions,
  the EXE size and SHA-256, the file count and the research checks.

| Item | Value |
|---|---|
| `main` | `0bea1de68dc346d20958e6f53a9e1d634a870f5d` (PR #122 merged) |
| Build commit | `a110867a8260e23a9cd1def7b593e6e2b03de72f` (`release/windows-portable-rc5-single-plate`, clean tree) |
| Built | 2026-11-01T18:33:32Z, Windows-10-10.0.19045-SP0 |
| Build folder | `D:\git\abaqus-modal-comparator-work\build\portable_rc5\dist\AbaqusModalComparator_RC5\` |
| Desktop copy | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC5\` and `AbaqusModalComparator_RC5.zip` (+ `.zip.sha256`) |
| Folder | 749 files (748 listed in `PACKAGE_SHA256.txt` + the list) |
| EXE | `AbaqusModalComparator.exe`, 17 679 674 bytes, SHA-256 `1db791e7a3bc0c42d7e9667986eb5dcc19981a88b514ad0e79e41375d415b62d` |
| ZIP | 105 928 208 bytes, SHA-256 `5fb2fe28ccfc3ecefa6e877b95cdc4a0c395502024853d02a292adb70881de21`; 749 entries, CRC OK |
| Package list | `PACKAGE_SHA256.txt`, SHA-256 `011e97d4fa4ac7f431d0bb7829f0a605442789e1b7170fa8032e36647734e241` |
| Python / PyInstaller | 3.14.6 / 6.22.3 (hooks-contrib 2026.9) |
| Libraries | PySide6-Essentials 6.12.0, shiboken6 6.12.0, numpy 2.5.1, scipy 1.18.0, matplotlib 3.11.1, pillow 12.3.0, openpyxl 3.1.5, pyuff 2.5.6, pypdf 6.14.2 |
| RC1 … RC4-F1 (unchanged) | ZIP `e1c34b0d…` / `3c07d0b9…` / `a32f7a11…` / `afee5e44…` / `2f12f095…` / `434e594c…` / `7e1cacad…`; EXE `c3fc0576…` / `175e7b1a…` / `68fefa36…` / `9e990df9…` / `84ed095e…` / `92967d5e…` / `11c73c11…` |

**Not included:** ODB, UNV, UFF, SVD, INP, Abaqus `.dat`, extracted FE packages (for example SP-10, 3.1 GB),
original data, solver scratch, caches and user data. The build refused none of these because none was present.

**Correction after the build** (packaging and tests only; the EXE and ZIP are not affected). The ZIP guard relied on
`os.rename`, which refuses an existing target on Windows but replaces it on POSIX. The CI run on `a110867` (Ubuntu)
failed on that test. `make_zip` now refuses an existing ZIP before anything is written. A test reproduces the POSIX
behaviour by replacing `os.rename` with `os.replace`. On Windows the build behaves as before, so the RC5 build from
`a110867` stands.

## Acceptance of the EXE

**Conditions:**

- Windows 10 Pro 19045, 150 % (DPI 144), native dialogs, UI Automation.
- The ZIP SHA-256 was confirmed and the ZIP unpacked into
  `D:\git\abaqus-modal-comparator-work\research\WINDOWS_PORTABLE_RC5_REVIEW\release a110867\Copied to another place\`
  (a path with spaces). `--verify` gives 748 / 748 verified, before and after the smoke.
- The EXE was started directly, with the working folder set to the output folder:
  - no Python, venv, repository, conda, WindowsApps or SIMULIA folder on PATH;
  - no `PYTHON*` / `QT_*` variable;
  - an isolated LOCALAPPDATA;
  - `AMC_OPEN_AUDIT` set.
- Only verified read-only copies were chosen:
  - `…\research\INTEGRATION_RC1_REVIEW\moved inputs\`: the M11 package `354966da…`, the 261027 UNV `76db80ae…`, the
    FE archive copy and its INP `962f75f2…`;
  - `…\research\WINDOWS_PORTABLE_RC5_REVIEW\inputs\S4 states copy\`: 157 files, the six S4 states of M11, copied with
    SHA-256 verification.
- Outputs went only into the smoke folder.

Results of run 2: `…\WINDOWS_PORTABLE_RC5_REVIEW\release a110867\exe smoke run 2\rc5_exe_smoke.json` and screenshots.

| # | Scenario | Result |
|---|---|---|
| 1 | Start (4.5 s) and close, twice | PASS: exit 0 both times, no EXE process left |
| 2 | All 6 pages | PASS: each shown with its content |
| 3 | Import of an FE package and a UNV / UFF | PASS for the FE package and the UNV: both "Content read; preview only"; Analysis: Polymax_bravo (11 records), FREQUENCY_ONLY, MAC NOT_COMPUTED, registration "Not checked". UFF: NOT_RUN, because no UFF copy is among the authorised inputs |
| 4 | Plate Study tabs A–D | PASS. Tab A with the FE archive copy: NOT_READY_FOR_IDENTIFICATION, FREQUENCY_ONLY, PHYSICAL_REGISTRATION_NOT_VERIFIED, the iterative estimation NOT AUTHORISED and its button disabled |
| 5 | Tab B, synthetic scenario | PASS: the DEMO study from the portable `docs`; CONVERGED, E_in_plane 51 975.2 MPa, G12 4 305.13 MPa, 5 FIT / 3 HOLDOUT; labels DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE / NOT_A_MATERIAL_PROPERTY / SYNTHETIC_DEMONSTRATION; report of 6 files |
| 6 | Tab C, no false confirmation | PASS: built from the Workspace (each file hashed again); SOURCES_VERIFIED, PHYSICAL_REGISTRATION_NOT_VERIFIED, MODE_PAIRS_NOT_CONFIRMED, NOT_READY_FOR_IDENTIFICATION, READY_FOR_OWNER_REVIEW |
| 7 | Tab D with the M11 baseline, INP and 6 S4 states | PASS: 14 elastic FE branches (FE7–FE20) followed into 6 states, LIVE_FE_PACKAGE_ANALYSIS. Before that, a synthetic declaration: 8 branches, 6 states |
| 8 | FE7 | PASS: 19.07217 Hz |
| 9 | G12 5 000 → 5 250 → 5 000 → 5 250 | PASS: 19.07217 (BASELINE) → 19.52665 (solved FE point 19.52640, 0.00129 %, FE_ONLY_LOCAL_PREDICTION) → 19.07217 → 19.52665; no accumulation, f0 unchanged; "FE sources verified again" each time |
| 10 | Another FE family keeps no Model ID / Specimen ID | PASS: after the synthetic family, the M11 baseline shows the defaults "FE model" / "specimen" and STALE; then the ids are M11 S4R_0875_BASELINE / PLATE-300x300x1mm |
| 11 | STALE, save, reopen, export of 5 files | PASS: session saved (93 463 bytes); export of `branch_tracking.csv`, `central_sensitivities.csv`, `FE_RESPONSE_REPORT.md`, `fe_response_session.json` and `what_if.csv` with SOURCES_VERIFIED; another FE family gives STALE — NOT CURRENT; after a restart the session reopens with its own ids, STORED (sources verified), FE7 and the What-If |
| 12 | No Abaqus and no source changes | PASS: no Abaqus process, no child process of the EXE; every watched file unchanged: 150 moved copies, 157 S4 copies, 195 S4 originals and 126 recorded originals, which match their record |

**Window sizes.** No page scroll bar on any page or tab at 1366 × 768 or 900 × 680.

- At 900 × 680 the Plate Study tab bar does not hold all four tabs. Qt shows its scroll arrows: C and D are reached
  with one press of the right arrow.
- The run-2 size check clicked tabs C and D behind the arrows and reported "not reachable". A separate run of the same
  EXE (`…\release a110867\tabs at 900x680 run 2\`) used the arrows: tabs B, C and D were each shown, with no page
  scroll bar, and the program closed with exit 0.

**Open-file record of the EXE** (3 313 files):

- nothing in the repository, in a Python installation outside the portable folder, in a venv, in `D:\Snadwich`, in a
  part of the work root that was not chosen, in SIMULIA / Abaqus or in a user cache;
- 169 reference files of the portable `docs`;
- of the inputs, only the chosen copies.

Tab A reads the files of the FE archive copy to verify their SHA-256 against the FE family. These include its `.odb`,
which is read only and is unchanged.

**Without the local paths.** `D:\Snadwich` and `D:\git\abaqus-modal-comparator-work` exist on this computer, so their
absence could not be simulated for the EXE itself. The evidence is:

- the open-file record above: the EXE opened nothing in them except the chosen copies;
- tab A was run on the FE archive copy, not on the default path;
- an offscreen run of the same `src` with every default local path replaced by a missing folder
  (`…\release a110867\no local paths (offscreen)\`). All six pages and tabs A–D were built with 0 errors. Tab A without
  inputs refused without an error, and the known-sources dialog reported the missing folder.

**Earlier smoke run 1** stopped at the tab B export. The smoke script typed a folder that did not exist into the native
folder dialog, and its blocking button press waited on the "Path does not exist" box. That was a defect of the smoke
script, not of the program. Run 2 creates the export folder first.

## Tests and CI

The tests were run sequentially on Windows with Python 3.11 (as in CI), offscreen Qt and an isolated LOCALAPPDATA:

| Tests | Result |
|---|---|
| `test_windows_portable_rc5` | 5 OK |
| `test_windows_portable_rc4_f1`, `test_windows_portable_rc4` | 3 OK, 3 OK |
| `test_single_plate_fe_response` | 37 OK (real M11 tests included) |
| `test_plate_physical_review` | 35 OK |
| `test_new_gui6_workbench` | 48 OK, 1 skipped |
| Full suite (`python -m unittest discover -s tests`) on `6f2f24c` | 3 315 OK, 98 skipped (unconfigured external data stores, no Abaqus, no font database offscreen) |

Two earlier full runs failed falsely and are not counted. In both, files changed in the working tree while the suite
ran:

- in the first, the build script was changed while the old test was loaded;
- in the second, this document was edited, which `test_m8_d2i_guarded_execution` reports as a change of `docs`.

CI (`Python tests`, Ubuntu):

- `0bea1de` (`main`): success;
- `a110867`: failure in the unit-test step (run 41337383848), the ZIP guard on POSIX (see the correction above);
- `6f2f24cc0399d1a7500bbaa10b3ec8db1845e940` (the correction): success (run 41348058459), all steps.

## Scientific status (unchanged)

- WORKING RESEARCH PREVIEW: no material value is identified or released.
- 261027 is FREQUENCY_ONLY, MODE_PAIRS_NOT_CONFIRMED and NOT_READY_FOR_IDENTIFICATION.
- The M11 FE7 19.07217 Hz and the PolyMAX 18.6307 Hz record of 2026-10-27 are not a confirmed mode pair.
- The tab D What-If is FE_ONLY_LOCAL_PREDICTION, not an Abaqus solve.
- M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED.
