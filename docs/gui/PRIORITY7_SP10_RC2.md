# PRIORITY-7 — SP-10 FE results in the new interface

**Status: REVIEW_READY.** Branch `feature/sp10-full-integration-portable-rc2`.

The branch starts from `37fe476` (WINDOWS PORTABLE RC1). It merges `research/sp10-existing-fe-shapes` at `9b86af4`
(PRIORITY-6) in merge `a5e6dfa`, whose parents are `37fe476` and `9b86af4`. The merge had no conflict and kept the
five PRIORITY-6 files.

All values below are **RESEARCH_ONLY / FREQUENCY_ONLY_DIAGNOSTIC / NOT_A_MATERIAL_PROPERTY**.

**Not done:**

- no new physical registration, MAC, orientation choice or mode pair;
- no solver, Abaqus Python, extraction, LM or Auto-ID.

**Unchanged:**

- M8 GATE NOT_MET;
- D-077 NO_GLOBAL_PARAMETER_VALUE;
- production Auto-ID BLOCKED;
- SP-10 261029 PHYSICAL_REGISTRATION_NOT_VERIFIED.

## 1. Sources (pinned)

| Source | Identity |
|---|---|
| FE model | `SP10_NEW_E1=E2_NSM_DENSITY`, step `SP_10_MODAL_FREE` |
| ODB | SHA-256 `87a9036fb5dc314e14a1fcb0d9ef4e0175d80bc6dfb05ceeea926d1ae767302c` |
| Extracted FE package (outside Git, 3.1 GB) | `manifest.json` SHA-256 `035b274c43fb8b7143bceb4dec99fdb2926a0f094cdafe1a0355faa45d8b1542`; FE7–FE25, 1 667 491 nodes |
| Experiment | `NEXP29/SP-10/S261029-ROTATED`, UNV SHA-256 `432adf963085b012b07a6b235e1dde3c4df83ea87b85326497df0a89a9eeef1f`, set `polymax_bravo`, 12 records |
| `SP10_FE_PACKAGE.json` | SHA-256 `a43637a1…` (LF), research commit `9b86af4` |
| `SP10_FE_VS_DAT.csv` | SHA-256 `647db42e…` (LF), research commit `9b86af4` |
| Historical table `SP10_MODAL_MATCHING.csv` | SHA-256 `037c95a3…` (LF), unchanged, the source of the 12 f_EXP |

## 2. The service `src/services/sp10_fe_research.py` (no Qt)

**`load_results(root)`** reads the two PRIORITY-6 records and checks them.

- **Digest.** Each file is read only with its recorded SHA-256, computed on the text with CRLF read as LF, so the
  digest is the same on every checkout.
- **Refusal.** The whole view is refused, with the reason, when any of the following holds:
  - a file is missing or changed, or is damaged JSON / CSV;
  - the record is not a passed verification;
  - the model, ODB, FE manifest, extractor or step is not the pinned one;
  - the geometry does not have 1 667 491 nodes;
  - the modes are not FE7–FE25 in order;
  - a frequency is non-finite, non-positive or not increasing;
  - a frequency does not equal the `.dat` to its printed five significant digits;
  - the two ODB tables disagree, or the JSON and the CSV disagree;
  - a mode has no recorded shape file.
- **No fallback.** No value is replaced.

**`frequency_diagnostic(results, experimental)`** works on EXP1–EXP12 against the 19 FE frequencies.

- For each record it gives the nearest and the second nearest FE frequency by |Δf|, with
  Δf (%) = 100 × (f_FE − f_EXP) / f_EXP.
- Every row is FREQUENCY_PROXIMITY_ONLY — NOT A CONFIRMED MODE PAIR.
- It makes no MAC, assignment or permutation.

**`workspace_match(...)`** compares the following, by SHA-256 only:

- the experimental file read in the Workspace;
- the FE manifest read there (its exact bytes);
- the modal set chosen on the Analysis page;
- the FE modes read: FE7–FE25 of the step, with the archived frequencies.

It returns one of two headlines:

- **PRIORITY-6 DATA SOURCES MATCH THE WORKSPACE INPUTS**, always beside **PHYSICAL_REGISTRATION_NOT_VERIFIED**;
- **PRIORITY-6 DATA SOURCES DO NOT MATCH THE WORKSPACE INPUTS: …**, naming each source that differs.

Two cases of the modal set:

- **Not chosen:** the files can match, and the line says that its identity with `polymax_bravo` is **not claimed**.
- **Another set chosen:** this is a mismatch.

## 3. Research Results (`research_results_model.py`, `research_results_panel.py`)

When SP-10 is chosen, the page shows two separate groups.

**A. Historical PRIORITY-1 — prior research (FE7–FE15, archived, unchanged)**

- The historical table is shown byte for byte as before: 12 rows, FE_SHAPES_UNAVAILABLE, no MAC.
- Its note says that these statuses describe the FE shapes available at the time of PRIORITY-1, not the current state
  of SP-10.
- The MAC card keeps "MAC NOT_AVAILABLE — FE shapes not extracted". It adds a line: this is the PRIORITY-1 state;
  the shapes are now extracted, but without a registration no FE↔EXP MAC is computed.
- The historical banner of PRIORITY-5A-F1 keeps its meaning: the historical SP-10 table never becomes VERIFIED.

**B. Updated SP-10 FE Results — PRIORITY-6**

Header:

- the labels;
- **FREQUENCY_PROXIMITY_ONLY — NOT A CONFIRMED MODE PAIR**;
- its own Workspace link with **PHYSICAL_REGISTRATION_NOT_VERIFIED**;
- the package status: **FE SHAPES EXTRACTED IN PRIORITY-6 — LOCAL PACKAGE NOT LOADED**, or **… LOCAL PACKAGE LOADED
  IN THE WORKSPACE**.

Identity lines: the model, the step, the ODB and manifest SHA-256, the geometry, the shapes and the source files.

FE table (`FE № | f_FE (Hz) | Step | Shape extracted | Source | Status`):

- FE7–FE25 from the ODB EIGFREQ history;
- FE16–FE25 are marked "added in PRIORITY-6".

The range wording:

- FE7–FE15 is the range of PRIORITY-1;
- FE16–FE25 are the ten modes added beyond it;
- this is not "above 220 Hz": FE15 is 220.044 Hz.

Diagnostic table (`EXP № | f_EXP (Hz) | Nearest FE | f_FE (Hz) | Δf (%) | Second candidate | Δf (%) | Status`):

- all 12 records;
- close groups highlighted, never reassigned;
- nearest FE frequencies in the added range highlighted;
- the EXP11 / EXP12 lines, then the close groups, then the limits.

**Loading.** The page reads only small files under `docs` when it is first shown. It never reads the 3.1 GB package,
and switching specimens reads nothing again. The FE shapes are viewed on the Workspace page with the existing
importer.

**`window.py`.** The only change is one helper. It passes the chosen modal set (name, key, record count) and the FE
modes read to the page, beside the two identities. Every Workspace or set change updates the link at once.

## 4. Frequency diagnostic of SP-10 (all 12 records)

| EXP | f_EXP (Hz) | Nearest FE | f_FE (Hz) | Δf (%) | Second | Δf (%) | Note |
|---|---|---|---|---|---|---|---|
| 1 | 26.5014 | FE7 | 23.8859 | −9.87 | FE8 | +188.77 | |
| 2 | 76.3913 | FE8 | 76.5292 | +0.18 | FE9 | +4.16 | |
| 3 | 79.8004 | FE9 | 79.5722 | −0.29 | FE8 | −4.10 | |
| 4 | 92.3388 | FE11 | 91.9857 | −0.38 | FE10 | −1.68 | close group EXP4/EXP5 near FE10/FE11 |
| 5 | 94.9947 | FE11 | 91.9857 | −3.17 | FE10 | −4.43 | close group EXP4/EXP5 near FE10/FE11 |
| 6 | 148.1323 | FE12 | 146.1161 | −1.36 | FE11 | −37.90 | |
| 7 | 207.3311 | FE13 | 210.8839 | +1.71 | FE14 | +3.33 | close group EXP7/EXP8 near FE13/FE14 |
| 8 | 214.4390 | FE14 | 214.2344 | −0.10 | FE13 | −1.66 | close group EXP7/EXP8 near FE13/FE14 |
| 9 | 222.2567 | FE15 | 220.0444 | −1.00 | FE16 | +2.11 | |
| 10 | 228.7088 | FE16 | 226.9465 | −0.77 | FE15 | −3.79 | FE16 added in PRIORITY-6 |
| 11 | 262.4545 | FE17 | 265.0355 | +0.98 | FE18 | +1.79 | close group EXP11/EXP12 near FE17/FE18; FE17 added |
| 12 | 266.8519 | FE18 | 267.1444 | +0.11 | FE17 | −0.68 | close group EXP11/EXP12 near FE17/FE18; FE18 added |

**Every row: FREQUENCY_PROXIMITY_ONLY — NOT A CONFIRMED MODE PAIR.**

- EXP11 and EXP12 now have FE frequencies nearby. PRIORITY-1 had none within 15 %, because its FE range ended at FE15.
- The close groups show where frequency alone cannot tell modes apart.

## 5. Tests

**`tests/test_priority7_sp10_research.py`: 23 tests.**

Service:

- the 19 FE modes, FE7 and FE25;
- the identity;
- the same digest with CRLF and LF;
- refusals of a changed or missing file, damaged JSON / CSV, wrong mode numbers, changed / NaN / negative /
  non-increasing frequencies, and a foreign model / ODB / manifest / step / shape;
- the 12 rows, the signed Δf, EXP11 and EXP12 exactly, the nearest FE of every row and the close groups;
- no MAC and no confirmed pair.

Workspace match:

- both SHA-256;
- each SHA-256 different alone;
- nothing read;
- no set, a wrong set or a wrong record count;
- FE modes or step different from the archive.

Page and window (Qt offscreen):

- nothing archived at start-up;
- opening the page starts no process, calls no FE preview and reads only small files under `docs`;
- the three specimens, with the historical table unchanged beside the PRIORITY-6 tables;
- SP-10 without a package;
- the link following every Workspace change;
- the window passing the set and the FE modes.

**`tests/test_windows_portable_rc2.py`: 6 tests.**

- the hidden imports;
- every reference file read, the PRIORITY-6 records included, is shipped;
- measurement / FE / solver / extracted-package files are refused;
- the research results load from another folder;
- RC1 is unchanged (SHA-256 of its five files) and its desktop copies are protected.

**Also run.** `test_priority6_sp10_fe_shapes` (8), `test_priority5_research_results` (14), `test_windows_portable_rc1`
(4) and `test_new_gui1_qt` all pass.

**Full suite.** The first full run found two failures in `test_new_gui1_qt`: the new card had archived text
("SP-10", "PHYSICAL…") in hidden labels at start-up. The card's texts are now set on the page's first show, and a
regression test was added. See §6 for the GUI run and `WINDOWS_PORTABLE_RC2.md` for the final numbers.

## 6. Windows GUI smoke before packaging (RUN_NEW_GUI.cmd)

**Setup:**

- one session of `RUN_NEW_GUI.cmd`;
- 150 % scaling (DPI 144), native dialogs, UI Automation;
- isolated LOCALAPPDATA;
- verified moved copies of the inputs;
- the SP-10 package read in place, never written.

**Code version.** The run used the integrated code before the start-up-text fix of §5. That fix only changes which
labels hold text before the page is first shown. The portable smoke (`WINDOWS_PORTABLE_RC2.md`) repeats the same
route on the final code.

| Step | Result |
|---|---|
| Start | 3.0 s; six pages (Workspace, Analysis, Status, Materials, Plate Study, Research Results) |
| SP-02 | FE + UNV read; archived reference verified; **VERIFIED_COMPARISON, 6 pairs**; pair FE 10 / Exp 4 drawn; report XLSX + PDF + JSON |
| Materials | shown |
| RC1-A | `.odb` refused ("Abaqus is not started"); moved plate FE package; known-sources folder chosen; FREQUENCY_ONLY_DIAGNOSTIC; registration not confirmed |
| Plate Study | moved FE archive, 8 / 8 family files verified; PHYSICAL_REGISTRATION_NOT_VERIFIED; estimation gate disabled; report exported |
| Research Results PLATE | 11 rows, verified banner; local record; rank 3 / 1.83 and 2 / 2.35; S0 / H1 / H2 (18.63088 / 158.01732 / 145.95451) |
| SP-13 | 12 rows, 12 HYPOTHETICAL_SAME_POINTS, banner NOT VERIFIED (FE only) |
| SP-10 before the package | archived frequencies shown; LOCAL PACKAGE NOT LOADED; link DO NOT MATCH (the SP-13 file was read) |
| SP-10 package | manifest chosen, Inspect: "19 modes loaded (7–25); no diagnostic messages", step SP_10_MODAL_FREE, EIGFREQ history; 269 s uncached; no Abaqus |
| Independent FE shapes | FE7 23.8859 Hz and FE17 265.036 Hz drawn |
| SP-10 261029 | `polymax_bravo` (12 records); FREQUENCY_ONLY_DIAGNOSTIC: 12 experimental, 19 elastic FE; MAC NOT_COMPUTED; mode pairs NONE; registration not confirmed; verified comparison disabled |
| Research Results SP-10 | A: 12 historical rows, all FE_SHAPES_UNAVAILABLE, historical banner NOT VERIFIED; B: link **MATCH** + PHYSICAL_REGISTRATION_NOT_VERIFIED, package LOADED, FE7…FE25 (457.6130), EXP11 262.4545 → FE17 265.0355 +0.98, EXP12 266.8519 → FE18 267.1444 +0.11, 12 FREQUENCY_PROXIMITY_ONLY rows |
| Input replaced | the SP-13 UNV read instead: link **DO NOT MATCH: the experimental file read in the Workspace is 8abf951dba4b…** at once |
| SP-10 UNV read again | link MATCH; modal set "none chosen … not claimed" |
| Sizes | no page scroll bar at 900 × 680 and 1366 × 768 |
| End | no Abaqus process; closed, exit 0; SP-02, SP-10 package, moved copies and record unchanged |

The screenshots and `rc2_launcher.json` are in
`D:\git\abaqus-modal-comparator-work\research\PRIORITY7_SP10_RC2_REVIEW\gui smoke cmd\`.

## 7. Limits

- **No physical registration of SP-10.** Its FE and experimental shapes can only be viewed independently.
- **No material value.** No E1 / E2 / G12 or other material value comes from these frequencies.
- **The close groups are taken from PRIORITY-1 / PRIORITY-6.** They are highlighted for the reader, not computed by a
  new rule.
- **The package is chosen by the user.** It is about 3.1 GB, and its first read takes about 4–5 minutes. It is never
  searched for and never shipped.
- **One FE model of SP-10.** It has one extraction.
