# APP-UX.1 — initial folder of the report save dialogs (2026-10-27)

Branch `feature/app-ux1-report-export-directory` from `main` `a1cf282`. A user-interface fix; no report content,
MAC, registration or scientific rule changes.

## The problem

The PDF / Excel report dialogs passed no initial folder. The Windows save dialog then opens in the folder the program
(python.exe) last used, taken from the user's dialog history in the registry (HKCU). That can be a folder of source
measurements or of an ODB, so a report could be saved next to the source data without the user noticing. This
happened in the stopped first RC1 acceptance attempt.

## The rule

Both report paths start the save dialog in one predictable folder of the user:

`%USERPROFILE%\Documents\Abaqus Modal Comparator Reports`

- **Comparison report.** **Export Excel report** / **Export PDF report** and **Reports** (`ModalComparatorApp._excel`
  / `_pdf`).
- **Diagnostic report.** **Export diagnostic Excel** / **Export diagnostic PDF** (`diagnostic_report_ui`).
- **Final owner.** Both buttons and the **Reports** menu end in the `ui_workflow` wrapper of `_excel` / `_pdf`. It calls
  the comparison handler when a comparison result exists and the diagnostic export otherwise; both pass the folder.
- **Folder creation.** The folder is created when it is missing, and only that folder: a missing `Documents` or home
  folder is never created. If `Documents` does not exist, the folder is made in the home folder. If the folder cannot
  be created, the dialog starts in `Documents`, else in the home folder.
- **Never a data folder.** No folder of the analysed files (ODB, UNV, UFF, manifest) or of the output workspace is used.
- **The user still decides.** Any other place can be chosen in the dialog. Cancel writes nothing. The suggested file
  names, the extension handling and the replace confirmation are unchanged.

The shared rule is `services/report_directory.py` (`default_report_directory`, `save_dialog_options`). Other save
dialogs (project, figures, CMIF, Auto-ID evidence) are not changed by APP-UX.1.

## Validation (2026-10-27)

No native Windows dialog was opened in any check; the dialog was always intercepted.

- **Unit tests** (`tests/test_app_ux1_report_directory.py`):
  - the folder rule: created, kept, without `Documents`, not creatable, missing home;
  - comparison Excel / PDF through the final owner: initial folder, cancel writes nothing, a place the user chose is
    written with the same result and writer;
  - diagnostic PDF / Excel: the same checks, with the real report writer;
  - the real main window: the export buttons of an established comparison and of a frequency-only diagnostic.
- **Without the fix,** the dialog checks of these tests fail.
- **Windows GUI smoke.** `RUN_PROGRAM.cmd` in an isolated profile on synthetic data only (`FREQUENCY_ONLY_DIAGNOSTIC`):
  - every report dialog call received `<profile>\Documents\Abaqus Modal Comparator Reports`;
  - a cancelled Excel export wrote and showed nothing;
  - PDF and Excel written to another chosen folder, with "Report saved";
  - the folder stayed empty, the inputs unchanged, no child process, exit code 0.

## Limit

The Windows dialog itself was not opened, so the honouring of the initial folder by the native dialog is not observed
here. Tk passes `initialdir` to the Windows file dialog as its folder. A manual check is: Reports > Export PDF report,
look at the folder shown, then Cancel.
