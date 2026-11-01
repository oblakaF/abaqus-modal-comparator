# WINDOWS PORTABLE RC1 — portable build of the new interface

**Status: REVIEW_READY.** Branch `feature/windows-rc1-portable-release`, from `24b02be` (INTEGRATION-RC1).

The folder `AbaqusModalComparator_RC1` is the integrated new interface frozen by PyInstaller (onedir). It can be
copied to another Windows computer and started with `AbaqusModalComparator.exe`, with no Python, VS Code or Abaqus
installation. The program starts no Abaqus.

The program is unchanged: no file under `src/` is changed by this release. Every scientific status, gate and
registration is as before.

## What the folder holds

| Item | Content |
|---|---|
| `AbaqusModalComparator.exe` | the new interface (no console window) |
| `_internal\` | the frozen program, Python 3.14 and the libraries: PySide6-Essentials (QtCore, QtGui, QtWidgets), numpy, scipy, matplotlib, Pillow, openpyxl, pyuff, pypdf |
| `docs\` | the tracked reference files the program reads (JSON, CSV, Markdown, text): archived research tables, registrations, Auto-ID records, the provenance of the known sources |
| `README_PORTABLE.txt` | how to start, what is not included and how to choose it |
| `BUILD_INFO.json` | commit, versions, sizes and the EXE's SHA-256 |

**Not included:** experimental files (UNV, UFF, LMS, SVD), Abaqus models and results (INP, ODB, DAT, STA…),
extracted FE packages and solver files. The user chooses them in the program:

- the Workspace file dialogs;
- **Choose folder...** of the known-sources dialog;
- **Choose FE archive folder...** of Plate Study;
- **Load local research record...** of Research Results.

## How the reference files are found

The program locates its reference files as `Path(__file__).parents[2] / "docs"`, the repository root in the source
tree. A frozen module's `__file__` is `_internal\<package>\<module>.py`, so the same expression gives the portable
folder. The build puts `docs\` there, and no program path is changed.

The archived research tables are checked by their recorded SHA-256 in the portable folder during the build, exactly as
in the repository.

## Building

1. Make a build environment outside the repository from `packaging/portable_rc1/requirements-build.txt`. It has the
   versions of the tested `.venv`, with PySide6-Essentials only.
2. Run:

   ```
   <build venv>\Scripts\python.exe packaging\portable_rc1\build_portable.py --out <build folder> [--desktop]
   ```

The script does the following:

1. It refuses uncommitted program files, so the build is the commit it reports.
2. It runs PyInstaller with `packaging/portable_rc1/AbaqusModalComparator_RC1.spec`.
3. It copies the tracked `docs` reference files, and refuses any file over 2 MB.
4. It refuses measurement, FE and solver file types.
5. It loads the research tables from the build.
6. It writes `BUILD_INFO.json` and `README_PORTABLE.txt`, then zips the folder.
7. With `--desktop`, it copies the folder and the ZIP to the Windows desktop. An existing copy is replaced only with
   `--replace`.

**Packaging-only additions:**

- `launch_new_gui.py`: the entry script; it calls `new_gui.__main__.main`.
- `rthook_open_audit.py`: inactive unless `AMC_OPEN_AUDIT` names a log file. Then it records the files the program
  opens, for acceptance runs.
- **Hidden imports:** the seven report layers, which `new_gui.report_export` installs by name.

`tests/test_windows_portable_rc1.py` keeps the packaging in step with the program:

- the hidden imports match the report layers;
- the reference files the interface reads are shipped;
- data files are refused.

## Acceptance

The ZIP was unpacked into a folder outside the repository, with spaces in its path. The EXE was started directly:

- with no Python, `.venv` or project folder on PATH;
- with no `PYTHON*` or `QT_*` variable;
- with an isolated LOCALAPPDATA;
- from a working directory outside the repository.

The run used native dialogs, UI Automation and 150 % scaling, with moved read-only copies of the inputs:

1. **SP-02.**
   - The FE package and the UNV were read.
   - The archived reference was verified.
   - The verified modal comparison was run, and a pair was drawn.
   - The report was exported as XLSX, PDF and JSON.
2. **Materials page.**
3. **RC1-A route.**
   - An `.odb` was refused, and no Abaqus was started.
   - The moved plate FE package and the known-sources folder were used.
   - The frequency diagnostic ran, and the registration was refused.
   - Plate Study ran with the moved FE archive, and its report was exported.
4. **Research Results.**
   - PLATE (verified by both SHA-256), SP-13 and SP-10, with the banners of PRIORITY-5A-F1.
   - The local research record.
   - The sensitivities: rank 3 / 1.83 and 2 / 2.35.
   - The scenarios S0 / H1 / H2.
5. **Window sizes and close.** There is no page scroll bar at 900 × 680 or 1366 × 768. The program closed with exit
   code 0.

**The open-file record showed:**

- no file of the repository, an installed Python or a `.venv`;
- nothing from the user's own program cache;
- the reference files came only from the portable `docs\`.

The DLLs loaded came from the portable folder and from Windows.

## Limits

- **Signing.** The EXE is not signed. Windows SmartScreen may ask for confirmation on first start of a copied folder.
- **Default folders.** The default folders of the known sources (`D:\Snadwich\New  EXP results`) and of the plate FE
  archive (`D:\git\abaqus-modal-comparator-work`) are those of the development computer. On another computer, choose
  the folders in the program.
- **Pinned SHA-256.** The FE family of the plate is verified by its recorded SHA-256 wherever it lies.
- **Other entry points.** The old interface (`RUN_PROGRAM.cmd`) and its Abaqus ODB route are not part of the portable
  build. The Abaqus-side scripts are not part of it either.
- **No installer.** Copy or unzip the folder.
