# NEW-GUI.6 — scientific workbench of the new interface

Status: REVIEW_READY (2026-10-29), not accepted.

Branch `feature/new-gui6-scientific-workbench`. It was made from `feature/new-gui5-registration-readiness` at `f9bff49`
(PR #120 open), with `origin/main` `249ac5e` (PR #119) merged into it by a normal merge (`65fdecb`). The PR #120 branch
itself is unchanged.

## What the user can do

1. **Workspace.** Choose and inspect the FE results (an extracted package `manifest.json`) and the experimental
   UNV / UFF. **File > Choose a known new experimental source...** (Ctrl+3) can set the experimental file to one of
   the three fitted working sources of 2026-10-29.
2. **Analysis.** Choose the experimental modal set. **Run frequency diagnostic** is optional (NEW-GUI.4).
3. **Check reference registration** (NEW-GUI.5). The service decides whether an archived physical registration applies
   exactly to these data.
4. **Run verified modal comparison.** It is enabled only when the check verified a registration for the current FE
   results, experimental file and modal set.
5. **Inspect the result** in the workbench, from top to bottom:
   - the shapes;
   - the mode pairs (the table chooses the pair drawn);
   - the scientific diagnostics.
6. **Export report...** into a folder the user chooses.
7. **Materials.** The project's existing material records, read-only and classified.

Nothing runs by itself, and nothing is loaded at start-up.

## Scientific core used (nothing re-implemented)

| Step | Existing owner |
|---|---|
| Registration, verified again at run time | `services.new_odb_comparison.bind_registration_by_fe_geometry`: fresh SHA-256 and size of the experimental file, FE geometry identity, the set's replay of the frozen registration, content compatibility, mapped FE nodes |
| Comparison | `modal_core.compare_modal_datasets(abaqus, experimental, frozen_registration=...)`, the reviewed quality-control facade that `runtime_contracts` requires of the program. It runs `quality_control.compare_modal_datasets_with_quality_control`, then `reviewed_core.compare_modal_datasets` |
| Provenance on the result | `metadata["geometry_verified_registration"] = provenance()` and the registration warning first, exactly as `runtime_hardening` attaches them |
| Pair drawings | `amplitude_correlation.render_pair_images`: the final owner of `reporting.render_pair_images` (runtime contract). It draws FE and experimental on the pair's registered points, plus the amplitude correlation |
| MAC matrix drawing | `reporting_hardening.render_mac_matrix`: the final owner of `reporting.render_mac_matrix` in `src/main.py` |
| Verified report | `reporting.export_excel` / `export_pdf` as `src/main.py` composes them. `new_gui.report_export.ensure_application_reporting` installs the seven existing report layers in `main.py`'s order (a test compares the order with `main.py`) and checks the final owners |
| Diagnostic report | `services.diagnostic_report` (CORE-E2E-D) with the frequency diagnostic shown |
| Material records | committed records only: `M7_RUN_A/B.result.json`, the D-076 correction and per-specimen records, `load_campaign_definition`, `load_forward_model_manifest`, `canonical_hash` |

The comparison applies only the frozen registration:

- **No automatic search.** No automatic orientation search runs, and no rotation, reflection, scale or point map is
  chosen by MAC or frequency. A test makes `geometry_alignment_candidates` fail and the comparison still runs.
- **Unchanged rules.** The comparator's rigid-body shape criterion, its frequency (|Δf| ≤ 15 %), MAC (≥ 0.50) and coverage gates and its
  one-to-one assignment are unchanged; no threshold is added.

## Scientific conditions, as implemented

- **Rigid-body FE modes.** They are separated by the comparator's shape criterion. The first elastic mode is kept, and
  the separated modes are listed with their residual.
- **Experimental record 1.** It is never removed; every record appears in the MAC matrix and in the candidate table.
- **Dataset 58 (FRF peaks).** It stays PROVISIONAL, and the verified comparison is not offered for it.
- **MAC.** It is computed only on the registered measured DOFs. The table shows measured DOFs, DOF coverage and
  points per pair.
- **A pair without MAC** (a frequency-only assignment by the comparator) is shown as `NOT_COMPUTED (frequency-only
  assignment: MAC not computed, shape identity NOT established)`.
- **No admissible pair.** It is shown as `NO_ADMISSIBLE_PAIR`, a valid scientific result: no correlation, no drawing.
- **Order changes and close or degenerate modes.** They are shown per pair and in the warnings, as the comparator
  reports them.
- **Pair assignment versus Auto-ID suitability.** The pairs are the comparator's numerical assignment. Every pair has
  *Auto-ID use: NOT ASSESSED*: a pair enters Auto-ID only as a governed FIT / HOLDOUT observation of an accepted strict
  freeze, which the workbench neither creates nor checks.
- **The engineering target of about 5 % (up to 10 %).** It is shown as a count, for orientation only, and is not a
  criterion.
- **Stale results.** Another set, a replaced or cleared file, Inspect again, a new check or a closed window removes
  the result and its drawings and cancels a running comparison. A request cancelled while it waits for the shared
  lock never runs the comparator. The comparator cannot stop midway, so a late cancellation discards its result.
- **One heavy operation at a time.** The comparison shares one lock with the frequency diagnostic and the check.

## Materials / Scientific evidence

The page reads the records when it is first shown. It runs nothing, has no command, and derives no value from a
frequency.

| Class | Content | Status |
|---|---|---|
| MATERIAL_IDENTIFICATION | M7 RUN_A verdict for `E_in_plane_mpa` and the SP-02 / SP-13 family consistency | NOT_IDENTIFIABLE; formal output **NO_GLOBAL_PARAMETER_VALUE** (D-076, D-077); no value shown |
| SPECIMEN_ENGINEERING_CALIBRATION | the committed records searched for the calibration record schema | **NOT_AVAILABLE**: no released calibration exists |
| MODEL_INPUT | `*Elastic, ENGINEERING CONSTANTS` of the SP-02 / SP-13 physical forward models (E1 … G23), pinned to their INP SHA-256 | MODEL_INPUT, not identified, not validated |
| DIAGNOSTIC_ESTIMATE | the RUN_A optimizer candidate (55 593 MPa), RUN_B (diagnostic only, SPEC v1.2 §11), the D-076 per-specimen estimates | DIAGNOSTIC_ONLY / NOT_A_MATERIAL_PROPERTY / NOT_A_RELEASE_VALUE |

- **Integrity.** The M7 result records are checked against the canonical hashes pinned by D-076. A changed record is
  NOT VERIFIED and its values are not shown.
- **"For the data read now".** Records are related to the read data only through the archived fixture the
  registration service verified (SP02/bravo-1-physical, SP13/best-physical), giving NO_GLOBAL_PARAMETER_VALUE.
  Otherwise the answer is NOT_AVAILABLE; this applies to the new ROTATED series. Nothing is related by a name, a file
  name or a frequency.
- **Not shown.** The frozen SP13 REAL-4 artefacts under `analysis/` (git-ignored, HISTORICAL_NOT_REVALIDATED) are
  not read.
- **The ±10 % wish.** The owner's engineering wish does not change the IDENTIFIED / WIDE / NOT_IDENTIFIABLE limits, the
  M8 block or D-077.

## Known new experimental sources

`new_gui.known_sources` declares the three fitted dataset-55 files. Each has its series identity, relative path, size,
SHA-256 and modal-set type. An entry is offered only under all of these conditions:

- the row of `docs/experimental/new_exp_20261029/SOURCE_PROVENANCE.csv` with the same relative path has the same
  series, size and SHA-256;
- the row's status token is exactly `NEW_WORKING_SOURCE`, never a substring of the description;
- the row's dataset list holds 55;
- the map has no other working source.

When a source is chosen, its local size and fresh SHA-256 are checked. Only the path goes into the experimental file;
Inspect file still reads it. Without the folder `D:\Snadwich\New  EXP results` the dialog says so, and the usual
**Choose file...** works. No registration, FE model or material record is assigned from a specimen identifier.

## Export

| Result shown | Files (time-stamped, never replacing a file) |
|---|---|
| Verified comparison | `verified_modal_comparison_<stamp>.xlsx` / `.pdf` from the program's comparison report writers, and `.json`. The JSON holds the FE / experimental sources with fresh SHA-256, the modal set, the registration provenance, the pairs with MAC and signed errors, the MAC matrix, the unpaired modes, the gates, the warnings, the status, the suitability statements and the limits |
| No verified comparison, frequency diagnostic shown | `modal_diagnostic_report_<stamp>.pdf` / `.xlsx` (CORE-E2E-D): MAC NOT_COMPUTED, no pairs |

- **Where files go.** Only the folder chosen in the dialog, which starts in the APP-UX.1 report folder. A cancelled
  choice writes nothing.
- **Changed files.** Before writing, the experimental file is identified again; a file changed since the comparison is
  refused.
- **Pair images** are drawn into a temporary folder of each request, read into memory and the folder removed.

## Results on real data (2026-10-29)

Read-only inputs:

- **Archived references.** SHA-verified copies of the archived SP-02 and SP-13 extracted FE packages and PolyMAX UNV.
- **New ROTATED series.** The three files were read directly from `D:\Snadwich\New  EXP results`.
- **Integrity.** Every input has the same SHA-256, size and mtime before and after every run.

| Data | Modal set | Registration (service) | Verified comparison |
|---|---|---|---|
| SP-02 archived | 1: Bravo (1) `bravo-1` | verified, SP02/bravo-1-physical, `9b63f6c8…` | VERIFIED_COMPARISON, **6 pairs** |
| SP-02 archived | 2: `bravo`, 3: `processing` | refused: the pinned set is `bravo-1` | not offered |
| SP-13 archived | 1: `best` | verified, SP13/best-physical, `2eeeaa86…` | VERIFIED_COMPARISON, **5 pairs** |
| SP-13 archived | 2: `processing` | refused: the pinned set is `best` | not offered |
| SP-13 ROTATED 28.10 (`polymax_bravo`, 12 records) | 1 | refused: SHA-256 `8abf951d…` is not an accepted source | not offered; FREQUENCY_ONLY_DIAGNOSTIC |
| SP-10 ROTATED 29.10 (`polymax_bravo`, 12) | 1 | refused: `432adf96…` | not offered; FREQUENCY_ONLY_DIAGNOSTIC |
| PLATE-300x300x1mm ROTATED 27.10 (`Polymax_bravo`, 11) | 1 | refused: `76db80ae…` | not offered; FREQUENCY_ONLY_DIAGNOSTIC |

Signed error = (f FE − f EXP) / f EXP × 100. MAC is computed on the registered measured DOFs: 121 for SP-02 and 289
for SP-13, all with 100 % DOF coverage.

**SP-02 `bravo-1`.**

- Pairs (FE mode / Exp record, error, MAC, comparator status):
  - 8 / 2: +1.16 %, 0.918, Excellent match;
  - 9 / 3: +0.11 %, 0.622, Review;
  - 10 / 4: −1.38 %, 0.951, Excellent match;
  - 11 / 5: −1.53 %, 0.570, Poor match;
  - 12 / 6: −0.40 %, 0.614, Review;
  - 13 / 7: +2.69 %, 0.975, Excellent match.
- FE mode 6 (0.0076 Hz) was excluded as rigid-body by shape.
- Unpaired: FE 7, 14, 15 and Exp 1, 8, 9.
- Close modes: FE 10 / 11, FE 13 / 14 / 15 and Exp 4 / 5.

**SP-13 `best`.**

- Pairs:
  - 8 / 3: −10.09 %, 0.528, Poor match, order changed;
  - 9 / 2: +2.42 %, 0.578, Poor match, order changed;
  - 10 / 4: −9.05 %, 0.958, Good match;
  - 11 / 5: −9.07 %, 0.559, Poor match;
  - 13 / 7: −2.76 %, 0.947, Excellent match.
- There is no rigid-body FE mode in this extraction (it starts at mode 7).
- Unpaired: 19 FE elastic modes and Exp 1, 6, 8–12.
- Close FE and experimental groups are listed.

These are the comparator's numerical assignments. A low MAC (for example SP-13 8 / 3: 0.528) is shown as the
comparator rated it. The workbench neither hides it nor makes it an Auto-ID observation; Auto-ID use is NOT ASSESSED.

The SP-13 FE package stands in for SP-10 and the plate only to test the interface's behaviour. Their own FE packages
are not confirmed, so no FE↔EXP result is claimed for them. The registration is refused by the experimental file's
SHA-256 alone, whatever FE is read.

**Materials page.**

- **SP-02 and SP-13 (verified fixtures):** "For the data read now" = NO_GLOBAL_PARAMETER_VALUE (D-077).
- **ROTATED series:** NOT_AVAILABLE ("not transferred by name, file name or frequency").
- **Records:** the M7 result records match their pinned canonical hashes, and no record is NOT VERIFIED.

## Performance and memory (measured, one process per specimen)

| | SP-02 | SP-13 |
|---|---|---|
| FE nodes / modes | 1 663 816 / 10 | 1 585 637 / 24 |
| FE read (existing importer, NEW-GUI.2) | 137–164 s; working set 3.0 GB | 315–324 s; working set 5.8 GB |
| Verified comparison (registration verified again + comparator) | 35–46 s; +0.8 GB; peak working set 4.4 GB (peak private 5.9 GB) | 84–88 s; +2.5 GB; peak working set 8.3 GB (peak private 9.8 GB) |
| Drawing one pair | 0.4–0.5 s (then kept; selecting it again draws nothing) | 0.4 s |
| Export (xlsx + pdf + json) | 7.9 s | 7.2 s |

- **Mesh copies.** The comparator copies the FE mesh coordinates and the mode vectors it needs; this extra memory is
  the comparator's own.
- **Pairs and images.** The workbench keeps the pairs' measured-point data and the PNG bytes of the drawn pairs; it
  does not copy the full mesh.
- **Stopping.** A running comparison cannot be stopped midway (the comparator has no cancellation). A cancelled or
  replaced request is discarded when it ends, 61–85 s later on SP-13, and never shown.

## Tests

| Run | PASS | SKIPPED | NOT_RUN |
|---|---|---|---|
| New headless tests `tests/test_new_gui6_workbench.py` (38) | 37 | 1 (the real archived test, without `NEW_GUI6_REAL_INPUTS`) | — |
| The real archived test with `NEW_GUI6_REAL_INPUTS` (SP-02 + SP-13) | 1 (635 s): pairs and MAC equal to a direct `compare_modal_datasets` call | — | — |
| New Qt tests `tests/test_new_gui6_qt.py` (20, offscreen) | 20 | — | — |
| Targeted: NEW-GUI.1–6, `test_new_odb_comparison`, importers, shape views, G2d-1, the SPEC v1.2 guards | 405 | 5 (offscreen glyph test; FE shape-pack and G2d-1 archive stores not configured; the real archived test) | — |
| The glyph test on the `windows` platform | 1 | — | — |
| The NEW-GUI tests on Python 3.11 (CI's version, Windows) | 140 | 1 | — |
| Full suite (the code of `fdcd2ec` without its registration note; before the report-message fix) | 2992 | 98 | `test_g2_eigfreq_precision` (16): it reads machine-local `-work` data |

Every defect fixed in this stage has a test that fails without the fix:

- the summary kept a removed comparison's MAC text;
- a disabled primary command looked enabled;
- a report message stayed after its result went.

The first CI run (`2f63328`) failed on three SPEC v1.2 guard tests (`test_spec_v1_2_normative`,
`test_spec_v1_2_policy_draft`, `test_v12_i1_campaign_question`). They forbid the calibration question's literal name
outside the sanctioned modules. The fix takes the name from its owner, `domain.campaign_definition`. The guard tests
are unchanged, and no calibration gate or output service is imported.

Minimal adaptations of the historical GUI tests (authorised):

- the NEW-GUI.1 separation allow-list: the new modules; `modal_core` only in `comparison_model.py`; the final drawing
  and report owners only where they are called;
- the NEW-GUI.1 / NEW-GUI.5 lists of the Analysis page's commands;
- the NEW-GUI.4 narrow-window check: five event-loop passes instead of three, because the workbench adds layout
  passes.

## Windows E2E smoke

Windows 10, screen scaling 150 % (DPI 144). Each run used an isolated `LOCALAPPDATA`. The user's cache was unchanged
(14 345 files, same fingerprint before and after).

**NEW_GUI in-process, Qt platform `windows`, code `fdcd2ec` (before the report-message fix): PASS.**

- **Empty start.** Every command is disabled with its reason, and the Independent views tab is shown.
- **SP-02, set 1.** Diagnostic, then check verified, then verified comparison: 6 pairs, the first pair drawn (three
  images). Row 3 of the table draws FE 10 / Exp 4; choosing it again draws nothing.
- **Diagnostics and export.** MAC table 9 × 9 with the pairs marked, then the diagnostics tabs and the export (xlsx,
  pdf, json). The Materials page shows NO_GLOBAL_PARAMETER_VALUE.
- **SP-02, set 2.** The result, the images and the summary go at once ("not computed" / "none"). The check refuses,
  the comparison stays disabled, and the diagnostic export is written.
- **SP-13 `best`.** 5 pairs; MAC table 24 × 12; export.
- **Window sizes with the SP-13 result.** Logical 900×680 and 1366×768, and physical 900×680 and 1366×768: no
  horizontal scroll bar on the Analysis or Materials page. Narrow windows stack the views; 1366 logical places them
  side by side.
- **One heavy operation at a time.** A frequency diagnostic started during a comparison waited and then completed.
- **Stale requests.** A set change during a comparison: result removed at once, worker ended after 61 s, discarded
  +1. Inspect again during a comparison: discarded +1.
- **ROTATED series.** The known-source dialog with SP-13 ROTATED, then Inspect, each series in turn:
  - SP-13 / SP-10 / plate read 12 / 12 / 11 records;
  - FREQUENCY_ONLY_DIAGNOSTIC;
  - check Not confirmed, with the service's SHA-256 reason;
  - Run verified modal comparison disabled, with its reason;
  - both unpaired views drawn: FE mode 7, and Exp record 1 on its own coordinates;
  - the Computed pair tab disabled;
  - the diagnostic report exported;
  - Materials NOT_AVAILABLE.
- **Close during an SP-13 comparison.** The thread ended, discarded +1, nothing shown, not busy.

**NEW_GUI through `RUN_NEW_GUI.cmd`: PASS.** Native dialogs and real mouse and keyboard input; the window's state was
read through UI Automation. The code was `fdcd2ec` without its registration note and before the report-message
fix.

- Start 3 s.
- **SP-02.**
  - FE and UNV were chosen in the native file dialogs (Ctrl+1 / Ctrl+2) and inspected.
  - Set 1 checked: verified.
  - **Run verified modal comparison**: 45.9 s, VERIFIED_COMPARISON.
  - A click on the table row for FE mode 10 drew COMPUTED PAIR FE 10 / Exp 4.
  - **Export report...** used the native folder dialog. It opened in `Documents\Abaqus Modal Comparator Reports`, and
    the files were written into the chosen folder.
- **Materials.** NO_GLOBAL_PARAMETER_VALUE.
- **Sizes.** 900×680, 1366×768, 1350×1020 and 2049×1152 physical: no page scroll bar.
- **Known sources (Ctrl+3).** Three entries; SP-13 ROTATED chosen and only its path set ("File chosen; content not
  checked"). Then Inspect, the check refused with the SHA-256 reason, the comparison disabled, the frequency
  diagnostic, and the diagnostic export through the native folder dialog.
- **SP-13 `best`.** Verified. The window was closed during the comparison: it closed in 1.5 s with cmd exit code 0,
  no child process and no `new_gui` process left.
- **Click retries.** The harness may retry a click once when it did not start a command. None was recorded.
- **Earlier attempt.** A first run aborted in the harness: a click on Check reference registration did not reach
  the window. The cause was not determined; a separate run of the same click verified the registration. It is not
  counted.

**LEGACY_GUI through `RUN_PROGRAM.cmd`: PASS** (start and close only, isolated profile):

- main window after 7 s;
- closed with no prompt, exit code 0, no child or program process left;
- the catalogue unchanged.

## Limits

- **SP-10 and the plate.** They have no confirmed FE package, so the SP-13 FE package stood in for their GUI checks
  only. No FE↔EXP result exists for them.
- **No registration for the new series.** None of the three ROTATED series has an accepted physical registration, so
  no MAC or mode pair exists for them. This is the service's refusal, not an application defect.
- **A running comparison cannot be stopped.** The comparator has no cancellation. A cancelled comparison runs to its
  end in the background (≈ 1–1.5 min on SP-13) and is discarded. A new heavy request waits for it.
- **Memory.** On SP-13 the verified comparison needs about 2.5 GB beyond the read FE results, and the process peaks
  near 10 GB of private memory.
- **Report text.** The diagnostic report is the CORE-E2E-D writer. Its "What is needed" text names the existing
  program's registration command.
- **The report folder rule.** The folder dialog follows APP-UX.1. The launcher smoke had no isolated `USERPROFILE`,
  and the rule created the empty folder `Documents\Abaqus Modal Comparator Reports` in the real profile (2026-10-29
  21:49). It is left in place.
- **Not read.** The frozen SP13 REAL-4 artefacts under `analysis/` are not shown, and no BOUND evidence record exists
  in the repository.
- **Last display fixes.** The cleared report message came after the full suite and both smokes. The note under the
  registration check came after the full suite and the launcher smoke. Both are covered by tests, and the targeted
  tests ran after them.
