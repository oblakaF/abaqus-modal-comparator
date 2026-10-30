# INTEGRATION-RC1 — one Windows program with portable inputs and Research Results

**Status: REVIEW_READY.** Branch `feature/windows-rc1-integrated`. Merge commit `b675b47` of:

- `feature/priority5-research-results-gui` at `1a90469`: the Research Results page (PRIORITY-5A) and its SP-10 fix
  (PRIORITY-5A-F1);
- `feature/windows-rc1-portable-inputs` at `1494bba`: WINDOWS-RC1-A, which adds:
  - the known-source folder;
  - the plate FE archive folder;
  - the honest `.odb` handling.

Start the program with `RUN_NEW_GUI.cmd`. It has six pages: Workspace, Analysis, Status, Materials, Plate Study and
Research Results. Every scientific status is unchanged:

- M8 GATE NOT_MET;
- D-077 NO_GLOBAL_PARAMETER_VALUE;
- production Auto-ID BLOCKED;
- 261027 PHYSICAL_REGISTRATION_NOT_VERIFIED.

## What the merge changed

- **One conflict, in `README.md`.** Both sections are kept: first RC1-A "Working from other folders", then Research
  Results.
- **`src/new_gui/window.py` merged without a conflict.** The RC1-A `.odb` note and the session's known-source folder
  sit beside the Research Results page.
- **The Research Results page takes the identities of the files read in the Workspace (SHA-256 only).**
  - Files chosen from another folder link to the archived research by their content, wherever they lie.
  - A file that is only chosen, such as an `.odb`, gives no identity.
- **Tests.** The NEW-GUI.1 tests merged without a conflict and keep both sets of changes:
  - the new interface modules;
  - the `.odb` file type text.
- No scientific file, result, tolerance, MAC, LM or registration service is changed. No `install_*` layer.

## Windows acceptance (merge commit `b675b47`)

The program was tested with `RUN_NEW_GUI.cmd` at 150 % scaling (DPI 144). The test used native file and folder
dialogs and UI Automation. The real inputs were read-only copies in a moved folder, with spaces in its path.

1. **`.odb`.** The `.odb` copy was explained as not viewable, and Inspect refused it. No Abaqus process was started.
2. **PLATE inputs.**
   - The moved plate FE package was chosen.
   - The known-sources dialog was pointed at the moved delivery with a folder dialog. All three ROTATED working
     sources were available there.
   - The PLATE UNV was chosen and read.
3. **Analysis.**
   - The frequency-only diagnostic ran.
   - The registration was refused by the service, and the verified comparison stayed disabled.
4. **Plate Study.**
   - The moved FE archive was chosen. All 8 family members were VERIFIED.
   - The study gave NOT_READY_FOR_IDENTIFICATION, and the report was exported.
5. **Research Results, PLATE.** Both SHA-256 of the research were read in the Workspace, so the banner reads "the
   Workspace inputs have the research inputs' SHA-256". The page also showed:
   - the local research record;
   - the sensitivities, rank 3 / 1.83 and 2 / 2.35;
   - the scenarios S0, H1 and H2.
6. **Research Results, SP-13.** The SP-13 UNV was chosen from the same folder, which was kept for the session.
   - The banner reads NOT VERIFIED.
   - The only reason is the FE manifest: the plate package is not the research FE package of SP-13.
7. **Research Results, SP-10.** The SP-10 UNV was chosen and read.
   - The banner reads NOT VERIFIED.
   - It explains that the experimental SHA-256 matches and that the FE identity is not confirmed.
   - The MAC reads NOT_AVAILABLE.
8. **Window sizes.** There is no page scroll bar at 900 × 680 or 1366 × 768.
9. **Close.** The program closed with exit code 0. The copies, the originals and the local record are unchanged.

The screenshots and the run record are outside Git, in
`D:\git\abaqus-modal-comparator-work\research\INTEGRATION_RC1_REVIEW\`.

## Not done

- **SP-13 FE package.** The 3.2 GB research FE package of SP-13 was not read in this check. The verified SP-13 state
  is covered by the tests only.
- No PR, no merge into `main`.
