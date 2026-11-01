# WINDOWS-RC1-A — portable inputs of the new interface

**Status: REVIEW_READY.** Program change on `feature/windows-rc1-portable-inputs`, made from `main` `4abfbca`
(PR #121 merged; CI run 41028360843 success). Not a scientific stage. No EXE, installer or data archive.

The new interface (`RUN_NEW_GUI.cmd`) can now be used after the project or the data move to other Windows folders.
Three practical problems are fixed.

## 1. Known experimental sources in any folder

`src/new_gui/known_sources.py`, `src/new_gui/known_sources_dialog.py`, `src/new_gui/window.py`.

- **Where the dialog looks.** It starts in the historical folder `D:\Snadwich\New  EXP results` (two spaces). **Choose
  folder...** points it at another folder, but only when the user clicks it; no disk is scanned. The folder chosen is
  offered again for the rest of the session.
- **Accepted folder.** Either the delivery folder (holding `SPname_files_ROTATED_261028`) or that subfolder itself
  (`known_sources.locate`).
- **Checks are unchanged:**
  - the provenance map `SOURCE_PROVENANCE.csv` must confirm the three declared sources;
  - a file is offered only with the declared size;
  - a file is used only with a fresh SHA-256 equal to the declared one.
- **Refusals.** A missing file reads "Not found in the chosen folder". A changed size or content is refused with the
  reason. A file of the right name in another place, or of the right name and size with another content, is never
  accepted.
- **Unchanged behaviour.** Choosing a known source only sets the experimental path; nothing is read before Inspect
  file. Choosing one's own UNV / UFF works as before.

## 2. The plate's FE archive root

`src/new_gui/plate_study_panel.py` (the existing `family_root` of `plate_study_model.run_study`; the service is
unchanged).

- **Shown and chosen.** The Plate Study page shows the FE archive folder; the default is the historical
  `D:\git\abaqus-modal-comparator-work`. **Choose FE archive folder...** sets another one. A folder that does not
  exist is shown as not found on this computer.
- **Verification.** When the study runs, `plate_study.verify_member` checks each family member under that folder by
  its recorded SHA-256 (INP, manifest, ODB, `.dat` where recorded):
  - a member that is not there is **MISSING**;
  - a member with another content is **CHANGED**;
  - neither contributes a sensitivity, and a file name is never taken as identity.
- **Reset.** A new folder discards the earlier result and the export status. The same folder, or a cancelled choice,
  changes nothing.
- **Unchanged.** The whole extracted FE package identity (manifest, geometry and mode CSV) still guards Run plate
  study and Export.

## 3. Honest handling of an .odb

`src/new_gui/workspace_state.py`, `src/new_gui/preview_model.py`, `src/new_gui/window.py`.

- **File dialog.** It offers "Extracted FE package (manifest.json)" first, and "Abaqus ODB - not viewable in this
  interface" second.
- **Card text.** The FE card's help, type and a warning say three things:
  - an `.odb` cannot be viewed in this version of the new interface;
  - to view it, choose the `manifest.json` of an existing extracted package (with its CSV files);
  - `RUN_PROGRAM.cmd` keeps its own ODB route, and choosing an `.odb` starts no Abaqus.
- **Inspect file on an `.odb`** refuses with that reason before the importer chain is installed: no Abaqus, no
  subprocess.
- **Not changed:** no ODB extraction is added. The scientific import, the extracted modes, the Abaqus parameters and
  the registration rules are unchanged.

## Tests

`tests/test_windows_rc1_a.py` (10 tests):
- a moved source is found in the delivery folder or its subfolder, with the right SHA-256;
- a changed, missing or same-named file is refused;
- another folder layout is not accepted;
- the provenance map is still required;
- the dialog's folder is chosen by the user and remembered for the session;
- the real 261027 working source copied to another folder is accepted, then refused after a change (skipped where
  the file is absent);
- the FE family is used from another root, and a new root resets the result and the export;
- members are MISSING in an empty root;
- the package identity still refuses a changed geometry CSV;
- an `.odb` is explained and never read (no `subprocess.Popen`, no importer chain), while `manifest.json` and UNV are
  still read;
- FREQUENCY_ONLY, PHYSICAL_REGISTRATION_NOT_VERIFIED and NOT_IDENTIFIABLE are kept;
- production Auto-ID stays BLOCKED, with M8 NOT_MET and D-077.

Updated expectations:
- the `.odb` type text (`test_new_gui1_qt`, `test_new_gui1_workspace`);
- the dialog's "not in this folder" message (`test_new_gui6_qt`).

## Verification (Windows, Python 3.14, isolated LOCALAPPDATA)

**Tests:**
- **Targeted:** NEW-GUI.1–6, FE package identity, APP-E2E.3, R7, Plate Study (+ Qt), registration readiness, owner
  clarification and WINDOWS-RC1-A. Result: 390 OK, 2 skipped (no font database offscreen; `NEW_GUI6_REAL_INPUTS`
  not set).
- **Full unittest:** 3103 OK, 98 skipped. **Full pytest:** 3040 passed, 114 skipped, 3689 subtests passed.
- `test_g2_eigfreq_precision` (16) is NOT_RUN: it reads machine-local `-work` data.

**Inputs of the smoke tests.** Read-only copies of the real inputs, placed in moved folders whose names contain
spaces:
- the 261027 UNV in a copied delivery folder;
- the M11 FE package;
- the whole plate FE family in a copied archive;
- a copy of the M11 ODB.

All copies and sources were unchanged after the runs (SHA-256).

**`RUN_NEW_GUI.cmd` (Windows 150 %, window DPI 144; native dialogs and UI Automation): PASS.**
1. Start in 3.0 s.
2. The `.odb` copy is explained on the card and Inspect refuses it ("Abaqus is not started"). No Abaqus process
   appears.
3. The moved FE `manifest.json` is chosen.
4. The known-sources dialog is pointed at the moved delivery through the native folder dialog:
   - the plate is Available;
   - SP-13 and SP-10 read "Not found in the chosen folder";
   - Use this file sets the path.
5. Inspect both files: `Polymax_bravo`, 11 records.
6. FREQUENCY_ONLY_DIAGNOSTIC; the 261027 registration check is refused; the verified comparison is unavailable.
7. Plate Study: the moved FE archive is chosen through the native folder dialog. Every member is VERIFIED.
   PHYSICAL_REGISTRATION_NOT_VERIFIED; 2 × BLOCKED; the gate is disabled.
8. Export into a chosen folder.
9. No page scroll bar at 900 × 680 or 1366 × 768.
10. Close with exit 0; no process left.

**In-process (Qt `windows`, DPR 1.5): PASS.** The same scenario, plus:
- FE mode 7 at 19.0722 Hz and record 1 at 18.6307 Hz are drawn;
- 14 sensitivity rows come from the moved archive;
- an empty archive gives every member MISSING and no sensitivity, after the earlier result and export status were
  cleared;
- no page scroll bar on the Workspace, Analysis or Plate Study page at either size.

**LEGACY_GUI (`RUN_PROGRAM.cmd`):** window in 3.8 s, closed, exit 0.

## Not changed

SPEC v1.1 / v1.2, DECISIONS, STATUS, EVIDENCE, frozen registrations, tolerances, the accepted SP-02 / SP-13 pairs,
the 261016 / 261027 results, physical orientations, M8 GATE NOT_MET and D-077 NO_GLOBAL_PARAMETER_VALUE. No Abaqus,
solver, LM or Auto-ID was run, and no `install_*` layer was added.

## Limits

- The chosen folders are remembered only for the session. They are not saved between runs.
- The FE archive must keep the family's recorded relative layout under the chosen root (as in
  `plate_study.PLATE_FE_FAMILY`).
- The known-sources dialog accepts the delivery folder or its one declared subfolder, not an arbitrary
  reorganisation.
