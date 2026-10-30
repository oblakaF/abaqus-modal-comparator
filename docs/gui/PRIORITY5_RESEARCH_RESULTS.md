# PRIORITY-5A — Research Results page of the new interface

**Status: REVIEW_READY.** Branch `feature/priority5-research-results-gui`, from `f19fc93`. Viewing only:
RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY.

`RUN_NEW_GUI.cmd` → left menu → **Research Results**. The page shows the archived results of PRIORITY-1–4. Nothing is
computed when it opens, and no Abaqus, Abaqus Python, solver, LM or Auto-ID is started. The archived files are read
on the page's first show, not at start-up.

## What the page shows

- **Specimen chooser:** PLATE (261027, 11 modes; the default), SP-13 (261028, 12 modes), SP-10 (261029, 12 modes).
- **Identity:**
  - the specimen and its series;
  - the research inputs' experimental SHA-256;
  - every archived source file with its SHA-256 and its research commit;
  - the research labels.
- **Workspace link banner.**
  - The archived tables are said to belong to the Workspace inputs only when the experimental file read there has
    the series' SHA-256, and the FE manifest has the research FE package's SHA-256 (PLATE, SP-13).
  - SP-10 has no research FE package, so it is never verified. When its experimental file matches, the banner says
    so, and that the FE identity is not confirmed.
  - Otherwise the banner reads **ARCHIVED RESEARCH SNAPSHOT — NOT VERIFIED FOR CURRENT WORKSPACE INPUTS**, and the
    tables stay viewable.
- **Mode matching — every experimental mode** (11 / 12 / 12 rows), from
  `docs/research/real_modal_matching_202610/*_MODAL_MATCHING.csv`.
  - The published statuses are shown unchanged: CANDIDATE_ONLY, AMBIGUOUS_CLUSTER, NO_MATCH, FE_SHAPES_UNAVAILABLE.
  - Close groups and ambiguous assignments are highlighted.
  - The MAC basis of each specimen is stated: PLATE research MAC on the diagnostic reconstruction; SP-13
    HYPOTHETICAL_SAME_POINTS; SP-10 no FE shapes.
- **Research MAC matrix.**
  - **Load local research record...** reads a `matching_record.json` that the user chooses; nothing is searched for.
  - The reader checks the structure, the matrix sizes, the FE mode numbers, finite values in 0–1, and the
    experimental source SHA-256 of all three series. It shows the SHA-256 of the JSON it read.
  - A record that fails any check is refused with the reason; no other numbers are put in its place.
  - The matrix is drawn as coloured cells (0–1 scale) under the warning **NOT A CONFIRMED MAC**. A click gives the
    cell's value.
  - SP-10 shows **MAC NOT_AVAILABLE — FE shapes not extracted**.
- **FE Parameter Sensitivities (PLATE only)** — `docs/research/plate_s4_central/CENTRAL_SENSITIVITIES.csv`.
  - Shows s_E1, s_E2, s_G12 and s_E for every branch, with the tracking state of each.
  - Highlighted: FE7 (G12), FE13 (E1), FE14 (E2), FE8 / FE9 / FE20 (lost in some ±5 % variants), FE15+FE16 (one
    cluster term).
  - Rank and condition are computed from the shown table: E1 / E2 / G12 rank 3, condition 1.83; E (E1 = E2) / G12
    rank 2, condition 2.35. They describe the FE model, not the accuracy of material parameters.
- **Inverse Parameter Study — Research Only (PLATE only).**
  - Inputs: `PLATE_INVERSE_SCENARIOS.csv` (S0 / H1 / H2 read from the file), `REAL_FE_VS_LM.csv`,
    `REAL_FE_VS_EXPERIMENT.csv` and `REAL_FE_BRANCH_TRACKING.csv`.
  - For the chosen scenario:
    - the assumed correspondences, with the real Abaqus error against the experiment;
    - every tracked branch: baseline, LM prediction, real Abaqus, approximation error, FE-to-FE MAC and tracking
      status;
    - the diagnostic nearest-frequency residuals of the other records (never pairs);
    - the scenario's limits.
  - FE15+FE16 is named the geometric mean of two tracked branches, not a mode. No scenario is ranked or chosen.

## Architecture

- `src/services/research_results_reader.py` (no Qt) reads and checks the archive.
  - Each file must have its recorded SHA-256, taken over the committed content with LF line ends (the same on a
    Windows CRLF checkout and on Linux); a changed or damaged file refuses the snapshot with the reason.
  - It also validates the local record, links to the Workspace by SHA-256, and computes the rank of the table.
- `src/new_gui/research_results_model.py` (no Qt) formats the rows and texts. `src/new_gui/research_results_panel.py`
  is the page.
- `window.py` adds the menu entry, reads the archive on the page's first show, and passes the identities of the files
  read in the Workspace (SHA-256 only).
- No `install_*` layer. No MAC, LM, identification or registration service is changed.

## Tests and Windows acceptance

- **Tests:** `tests/test_priority5_research_results.py` (14 tests) covers:
  - the 35 rows, exact frequencies, S0 / H1 / H2 from the file, unchanged statuses, rank 3 / 1.83 and 2 / 2.35;
  - the same digest for LF and CRLF checkouts;
  - refusal of a changed or damaged CSV and of a damaged, mis-sized, non-finite, out-of-range or foreign JSON;
  - the page with and without a record;
  - no confirmed-MAC wording;
  - the SHA-256 link to the Workspace (PLATE and SP-13 verified only by both SHA-256; SP-10 never verified);
  - no process started when the page opens;
  - switching specimens and scenarios.
- The NEW-GUI.1 separation and start-up tests now include the new modules. The page shows no archived text before
  its first show.
- **Windows smoke** (`RUN_NEW_GUI.cmd`, DPI 144 = 150 %, native file dialog, UI Automation): all 13 steps of the
  acceptance scenario passed, with no page scroll bar at 900 × 680 or 1366 × 768. Screenshots are outside Git in
  `D:\git\abaqus-modal-comparator-work\research\PRIORITY5_GUI_REVIEW\`.

## Not changed

- SPEC, DECISIONS, STATUS, EVIDENCE, frozen registrations, tolerances.
- M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED, 261027
  PHYSICAL_REGISTRATION_NOT_VERIFIED.
- The published research files.
- No branch WINDOWS-RC1-A content is included.
