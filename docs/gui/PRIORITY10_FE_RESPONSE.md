# PRIORITY-10 — Plate Study > D. FE Response Workbench

Branch `feature/plate-fe-family-explorer-p10`, from `f402b69`. FE-only. No new portable build. RC4-F1 is unchanged.

The user chooses one FE model of a plate: its baseline package and its already solved perturbation states. Then the
user can:

- check where each state comes from;
- follow every FE branch;
- compute the central sensitivities;
- explore the FE-only What-If against the solved FE points;
- save, reopen and export the session.

None of this needs a Python edit. The result on the real M11 packages is in
`docs/research/plate_fe_response_p10/RESULTS.md`.

## 1. Architecture

**Service `src/services/single_plate_fe_response.py` (no Qt).** It reuses:

- the importer (`local_fe_preview`, `importer_runtime`);
- `fe_package_identity`;
- `plate_study.sensitivity_table`: `elastic_modes`, `fe_state`, `branch_tracker.track_branches` under
  `STRICT_IDENTIFICATION_PAIRING`, `identification_clusters.confirm_cluster`;
- `plate_study.parse_inp_material`;
- `research_results_reader`, for the SHA-checked PRIORITY-2 archive;
- the RCOND of `practical_identifiability`.

**Panel `src/new_gui/fe_response_panel.py`.** The fourth tab of the Plate Study page. There is no new navigation and
no `install_*` layer; tabs A, B and C are unchanged.

**Synthetic generator** `research/plate_fe_response/make_synthetic_family.py`. It writes a SYNTHETIC_TEST plate of
another geometry into a folder the user names, never into the repository: extracted packages may not live in `docs`.

## 2. The FE family

**Two routes:**

- **A folder of states** (Choose FE baseline manifest... / Choose baseline INP (optional)... / Choose folder of FE
  states...). Each direct sub-folder with an extracted package (`extraction/manifest.json` or `manifest.json`) and one
  INP is a state.
  - Its parameter and value come from its INP against the baseline INP or the declared baseline values. Exactly one of
    E1 / E2 / G12 must differ, every other constant must be equal.
  - A `SOLVER_RUNS.csv` in the folder gives the run records.
  - Anything else is listed as not used.
  - Only the chosen folder is read.
- **A family declaration** (`amc/fe-family/v1`): model and specimen ids, the baseline values and every state's manifest
  (or a `.dat`), parameter, value and unit. Paths may be relative.

**Identities:**

- the manifest SHA-256 and the package SHA-256 (every file the loader reads);
- the INP, `.dat` and solver log;
- the ODB against its run record.

What cannot be verified is named, for example "no INP" or "the ODB (not present or no recorded SHA-256)".

**Kinds of result:**

- **LIVE_FE_PACKAGE_ANALYSIS:** the shapes read and followed now;
- **ARCHIVED_FE_RESULT:** the SHA-checked PRIORITY-2 table, never a new FE-to-FE MAC;
- **FREQUENCY_ONLY:** no shapes, following not proven;
- **INCOMPLETE_FE_FAMILY:** a parameter lacks its − or + state; the missing side is named and nothing is substituted.

## 3. Tracking, sensitivities, rank

**Tracking:**

- FE-to-FE MAC only, never the nearest frequency;
- a lost branch keeps its exact reason, for example "best FE-to-FE MAC 0.890 < 0.9";
- a confirmed cluster is one term (mean ln f);
- an order exchange is shown as "(order changed)";
- a state on other nodes or coordinates is excluded as INCOMPATIBLE_FE_GEOMETRY before any MAC.

**Central sensitivity:** `s = (ln f₊ − ln f₋) / (ln p₊ − ln p₋)` with the actual values of the nearest − and + states.

- When one side is not followed: **NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE**, never a one-sided value.
- The one-sided values s− / s+ are shown only as a linearity note.

**Rank:**

- the FE-only rank and condition of the complete terms;
- E (E1 = E2) only as **CONDITIONAL_SUPERPOSITION** s_E1 + s_E2;
- for the M11 baseline package only, the comparison with the PRIORITY-2 archive. Another FE model is never compared
  with it.

## 4. The FE-only What-If

`ln f_trial = ln f0 + Σ s_j ln(p_trial_j / p0_j)` — FE_ONLY_LOCAL_PREDICTION, not an Abaqus solve.

**Refused:**

- outside the solved range ("never extrapolated");
- for an INCOMPLETE parameter;
- with sensitivities of another FE model;
- without a result.

**Shown with each prediction:**

- f0, the prediction and the solved FE frequency where the trial equals a solved state, with the error;
- for a branch whose central sensitivity is unavailable: CENTRAL_SENSITIVITY_UNAVAILABLE.

**Joint E (E1 = E2).** E1 and E2 are scaled by the same ratio (the value is E1's), always labelled conditional.

**Never:**

- an optimisation;
- a choice of a parameter from a measured frequency;
- a MAC objective.

## 5. The experiment beside the FE

The records of the modal set read in the Workspace are shown with the nearest FE term and its prediction, as
**FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR**. Changing the modal set changes only this display: the FE results stay
CURRENT.

## 6. Session and export

**Save session...** writes JSON (`amc/fe-response-session/v1`):

- the family, the identities, the results and the what-if;
- the experiment display, the limits and the scientific status;
- no FE data.

**Open session...** hashes every manifest again in the background (never the whole package):

- **STORED** when they verify;
- **STALE** (results hidden, no prediction) when one changed or is missing.

**Choosing another baseline, folder or declaration** makes the shown results STALE.

**Export results...** writes the session JSON, `central_sensitivities.csv`, `branch_tracking.csv`, `what_if.csv` and
`FE_RESPONSE_REPORT.md` into a new folder.

**Background work.** Reading and tracking run in the background and **Cancel** discards the outcome.

## 7. Tests

**`tests/test_single_plate_fe_response.py`: 25 tests.** The items of the PRIORITY-10 list:

1. real M11 values: the archived values always; the live ones where the packages exist;
2. independence from M11;
3. FE8 / FE9 / FE20 and the synthetic FE14 lost, with their reason;
4. the FE10 / FE11 exchange;
5. FE15+FE16 and FE12+FE13 as one term;
6. a state with the baseline frequencies but other shapes: every branch lost, none re-paired by frequency;
7. incompatible geometry;
8. a missing state;
9. ln-p central differences, including an unequal step;
10. the conditional E1 + E2 sum;
11. no change gives the baseline;
12. a prediction against the solved points;
13. no extrapolation;
14. no transfer to another FE model;
15–16. save, reopen, export and STALE on a changed manifest;
17. EXP1 / FE7 proximity only;
18. no subprocess, solver or LM call;
19. tab D beside A / B / C: the synthetic route through the panel, a modal-set change keeps the FE results, a new
    family makes them STALE, reopen STORED, cancel.

**The separation test** lists the new panel.

**Regressions** (item 20):

- A, B, C, SP-02 / SP-10 / SP-13 and Research Results run in the full suite;
- the Windows smoke (see the report).

**A defect found by the Windows smoke and corrected with a test.** The "FE model id" / "Specimen id" captions had
collapsed to zero width.

## Not changed

- SPEC, DECISIONS, ROADMAP, STATUS and EVIDENCE.
- The frozen registrations, the tolerances and the historical results (the PRIORITY-2 CSVs are read, never written).
- M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE; production Auto-ID stays BLOCKED.
- No Abaqus, Abaqus Python, extraction, FE solve, LM or Auto-ID.

## 8. Results of the acceptance

**Tests:**

- targeted: `test_single_plate_fe_response` (25, the real M11 packages included on this computer);
- the 521 tests of the neighbouring suites: NEW-GUI 1–6, Plate Study, Workbench B, Physical Readiness C, Research
  Results, SP-10, the branch tracker, clusters, FE preview and package identity;
- all pass.

**Full suite** on `44fe1df`: **3298 tests, OK, 98 skipped** (the same categories), with isolated LOCALAPPDATA and
nothing else on the screen.

**Windows GUI smoke** (`RUN_NEW_GUI.cmd` of `44fe1df`; Windows 150 %, native dialogs, UI Automation, isolated
LOCALAPPDATA). Evidence: `D:\git\abaqus-modal-comparator-work\research\PRIORITY10_P10_REVIEW\gui smoke cmd 2\`.

**The real M11 route:**

- the verified baseline copy (`354966da…`), its INP and the `s4_central` folder of six states chosen through native
  dialogs;
- LIVE_FE_PACKAGE_ANALYSIS of 14 branches in 6 states, read in the background;
- tracking:
  - 6 lost cells (FE8 / FE9 / FE20 in E1 +5 % and E2 −5 %);
  - 12 "order changed";
  - FE15+FE16 CONFIRMED;
  - FE3–FE6 rigid;
- sensitivities: "PRIORITY-2 archive: AGREES (max |Δs| 4.91e-06)"; rank 3 / 1.83 and 2 / 2.35 CONDITIONAL;
- What-If:
  - G12 5 250 and 4 750 predicted against the solved points;
  - G12 6 000 refused ("never extrapolated");
  - E1 58 800 with 3 branches CENTRAL_SENSITIVITY_UNAVAILABLE;
  - E (E1 = E2) 57 120 conditional;
  - 11 PLATE 261027 records FREQUENCY_PROXIMITY_ONLY;
- session saved and reopened (STORED, sources verified); export (5 files).

**The synthetic route** (another plate, 420 × 260 mm):

- the declaration loaded: the M11 results STALE;
- tracked: 1 loss, 4 "order changed", FE12+FE13;
- G12 4 200 predicted;
- after one of its manifests changed, the reopened session is STALE.

**Window sizes and end:** no page scroll bar at 900 × 680 and 1366 × 768; no Abaqus; exit 0; the real packages and
copies unchanged.

**Smoke finding.** The first run (`gui smoke cmd 1`, `da4f4ab`) found the collapsed captions, corrected in `44fe1df`.

**Regression smokes** (`RUN_NEW_GUI.cmd` of `44fe1df`):

- the RC3 route:
  - SP-02 VERIFIED_COMPARISON 6 pairs;
  - Plate Study A 8 / 8;
  - Research Results PLATE / SP-13 / SP-10;
  - Workbench B on the real copies, the synthetic demonstration CONVERGED;
  - the cancelled 3.1 GB SP-10 read;
  - window sizes;
- the F1 route of tab C:
  - built, revalidated;
  - one source refused → STALE;
  - SP-13 refused.

Both pass. Evidence: `…\PRIORITY10_P10_REVIEW\regression cmd\` and `…\regression tab C cmd\`.
