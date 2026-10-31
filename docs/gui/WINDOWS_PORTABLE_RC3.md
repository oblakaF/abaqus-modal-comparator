# WINDOWS PORTABLE RC3 — portable build with the single-plate workbench

**Status: REVIEW_READY.** Branch `feature/generic-single-plate-workbench-rc3`.

**The EXE is built from code commit `602c7c9`** (PRIORITY-8). Later commits change tests or documentation only:

- `8fbef79` replaces one font-dependent layout test;
- the last commit is this record.

The program code of the final SHA equals that of `602c7c9`.

The folder `AbaqusModalComparator_RC3` is the new interface frozen by PyInstaller (onedir), with the approach of RC1 and
RC2. It starts with no Python, VS Code or Abaqus installation, and it starts no Abaqus. It holds:

- the six pages;
- the single-plate workbench (Plate Study > B);
- saving and opening of studies;
- the diagnostics;
- the bounded offline research mechanism;
- the existing comparisons and reports.

**RC1 and RC2 are unchanged:**

- `packaging/portable_rc1` and `packaging/portable_rc2` have the same SHA-256 for their files (test);
- the desktop copies of RC1 and RC2 have the same SHA-256 before and after the RC3 build.

## Build

```
<build venv>\Scripts\python.exe packaging\portable_rc3\build_portable.py --out <build folder> --desktop
```

**Environment.** The versions of RC1 and RC2: Python 3.14.6, PySide6-Essentials 6.12.0, numpy 2.5.1, scipy 1.18.0,
matplotlib 3.11.1, Pillow 12.3.0, openpyxl 3.1.5, pyuff 2.5.6, pypdf 6.14.2, PyInstaller 6.22.3.

**What the script does:**

- It refuses uncommitted program files.
- Hidden imports: the seven report layers, `services.research_results_reader`, `services.sp10_fe_research` and the
  three `services.generic_plate_*` services.
- It puts the tracked `docs` reference files beside the program: 199 files, 3.6 MB, among them the PRIORITY-6 records
  and the synthetic demonstration `docs/examples/generic_single_plate_demo`.
- It refuses the following, where data live:
  - measurement, FE model and solver files;
  - `.dat` and `.npz` files;
  - extracted FE package files.
- It checks in the built folder:
  - the research tables;
  - the SP-10 records;
  - the demonstration: it opens, its evidence is EVIDENCE_COMPLETE_NOT_FROZEN, and its offline study is CONVERGED at
    51 975 / 4 305 MPa, labelled DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE / NOT_A_MATERIAL_PROPERTY.
- It never writes the RC1 / RC2 desktop copies.

| Item | Value |
|---|---|
| Commit | `602c7c9d980e3a284de5b547720bdafc3f153068` (clean tree) |
| Folder | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC3\` — 719 files, 242 996 102 bytes |
| EXE | `AbaqusModalComparator.exe`, 17 505 852 bytes, SHA-256 `68fefa36fbe24381b16b154ddd9639cd1e8c65be969bfbbbc37e48ce7116f783` |
| ZIP | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC3.zip`, 105 577 925 bytes, SHA-256 `a32f7a1110c556f34ee641fa30b8aada6824f98d762632009c9dcee0ef1c96cb` |
| RC1 (unchanged) | ZIP `e1c34b0d…`, EXE `c3fc0576…`, 710 files |
| RC2 (unchanged) | ZIP `3c07d0b9…`, EXE `175e7b1a…`, 712 files |

**Not included:** ODB, UNV, UFF, INP, extracted FE packages (for example SP-10, 3.1 GB), caches and original data.

## Acceptance

Two sessions ran the same route:

1. `RUN_NEW_GUI.cmd` of the final code;
2. the portable EXE, unpacked from the desktop ZIP (SHA-256 checked) into
   `D:\git\abaqus-modal-comparator-work\research\PRIORITY8_RC3_REVIEW\release 602c7c9\Copied to another place\`,
   started directly.

**Common conditions:**

- 150 % scaling (DPI 144), native dialogs, UI Automation;
- isolated LOCALAPPDATA;
- verified moved copies of the inputs;
- the SP-10 package read in place, never written.

**For the EXE run only:**

- no Python or `.venv` on PATH, no `PYTHON*` / `QT_*` variable;
- working directory outside the repository;
- the files opened recorded with `AMC_OPEN_AUDIT`.

| Step | RUN_NEW_GUI.cmd | Portable EXE |
|---|---|---|
| Start, six pages | 3.5 s | 10.0 s (the window is the EXE's process) |
| SP-02: archived reference verified, **VERIFIED_COMPARISON 6 pairs**, pair FE 10 / Exp 4 drawn, XLSX + PDF + JSON | yes | yes |
| `.odb` refused, no Abaqus | yes | yes |
| Plate Study A: moved FE archive 8 / 8 verified, PHYSICAL_REGISTRATION_NOT_VERIFIED, estimation gate disabled, report | yes | yes |
| Research Results PLATE: 11 rows, local record, rank 3 / 1.83 and 2 / 2.35; S0 / H1 / H2 (18.63088 / 158.01732 / 145.95451) still under "Inverse Parameter Study — Research Only", RESEARCH_ONLY | yes | yes |
| SP-13: 12 rows, HYPOTHETICAL_SAME_POINTS, NOT VERIFIED | yes | yes |
| SP-10 (PRIORITY-7): historical A and PRIORITY-6 B, EXP11 262.4545 → FE17 265.0355 +0.98, package NOT LOADED | yes | yes |
| Plate FE first elastic mode FE7 19.0722 Hz drawn independently | yes | yes |
| **Workbench, real copies (PLATE files as a new physical study):** statements without provenance refused; identifiers and set-up applied; a value without provenance refused; length / width / mass with uncertainty MEASURED applied; areal density DERIVED 1.31085 kg/m²; "0 measured thickness points < 9" | yes | yes |
| Link the Workspace inputs: FE `354966da…` and UNV `76db80ae…` MATCH, set Polymax_bravo (11) | yes | yes |
| Modal diagnostics: EXP1–EXP11, FE7…, 11 FREQUENCY_PROXIMITY_ONLY rows, **Pairs: none** | yes | yes |
| Evidence: PHYSICAL_REGISTRATION_NOT_VERIFIED, frozen no, MAC not computed | yes | yes |
| Observability: NOT_READY_FOR_IDENTIFICATION with the reasons and the sensitivity plan | yes | yes |
| Offline study **disabled**: registration not complete, no sensitivity table, no declaration | yes | yes |
| Report exported (MD, JSON, 3 CSV); study saved (41 kB) and reopened (registration recomputed) | yes | yes |
| SP-13 UNV read instead: "experimental CHANGED", diagnostics refused | yes | yes |
| **Synthetic demo** (420 × 260 mm) opened from `docs\examples`: synthetic inputs, sensitivities, declaration → gate empty → **CONVERGED, E_in_plane 51 975.2, G12 4 305.13 MPa**, 5 FIT / 3 HOLDOUT, labels DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE / NOT_A_MATERIAL_PROPERTY / SYNTHETIC; approved values NOT_AVAILABLE; report with offline terms | yes | yes |
| Cancelled read: the 3.1 GB SP-10 package inspected ("Reading the file..."), Clear → "Not chosen", no hang | yes | yes |
| No page scroll bar at 900 × 680 and 1366 × 768 | yes | yes |
| End: no Abaqus process, closed, exit 0, no process left; inputs, SP-10 package and record unchanged | yes | yes |

**Open-file record of the EXE (1973 files):**

- none from the repository, an installed Python or a `.venv`;
- none from the user's LOCALAPPDATA or program cache, from `D:\Snadwich` or from other work folders;
- reference files only from the portable `docs` (84), among them the four demonstration files;
- 3 files of the SP-10 package, during the cancelled read;
- system fonts scanned by matplotlib and one relative `struct.py`, as in RC1 / RC2.

**DLLs:** 147 from the portable folder. The rest come from Windows and the Defender / Ink / Adobe shell extensions.

**Evidence** is in `…\PRIORITY8_RC3_REVIEW\gui smoke cmd final\` and `…\release 602c7c9\smoke run\`
(`rc3_launcher.json`, `open_audit.log`, `open_audit_summary.json`, screenshots). The screenshots include:

- `20` measurements;
- `21` diagnostics;
- `22` readiness;
- `23` demo offline study;
- `30` FE shape;
- `19` SP-10;
- `02` / `03` SP-02;
- `05` PLATE;
- `04` Plate Study A;
- `09` window sizes.

## Tests and CI

**Targeted tests, all pass:**

- `test_generic_single_plate_workbench` (27);
- `test_windows_portable_rc3` (5), `rc2` (6), `rc1` (4);
- `test_new_gui1_workspace`;
- the Plate Study, NEW-GUI 1–6, Research Results and PRIORITY-5/6/7 modules.

Together the regression modules are 399 tests, OK, 2 skipped.

**Full suite.** 3206 tests, OK, 98 skipped, on Windows with Python 3.14 and again with Python 3.11 (the CI version).
The skips:

- about 94 need local data stores that are not configured;
- 2 need the Abaqus integration;
- 1 needs `NEW_GUI6_REAL_INPUTS`;
- 1 needs a font database that offscreen Qt lacks on Windows.

The synthetic tests are no physical validation.

**CI:**

- `602c7c9`: run 41201919114, **failure** in "Run unit tests" (Linux). The log is not readable without
  authentication. The only new font-dependent assertion was the width comparison of sections B and A. It was
  replaced in `8fbef79` by font-independent layout checks. The program code is unchanged.
- `8fbef79`: run 41204310416, **success**. This confirms that the failure came from that test.
- The final SHA (this record, documentation only): see the final report.

## Limits

- **Signing.** The EXE is not signed.
- **Default folders.** The default folders are those of the development computer.
- **The SP-10 package.** It is not included and is chosen by the user.
- **The workbench creates no registration and no material value.** A new plate reaches the offline study only with
  the owner's decision, a sensitivity table of its own FE model (Abaqus under its own gate) and a declared
  observation set.
- **Not part of the build:** the old interface, the Abaqus-side scripts and an installer.
- **Build warning.** PyInstaller warns that the hidden import `scipy.special._cdflib` is not found, as before.
