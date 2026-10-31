# WINDOWS PORTABLE RC4 — portable build with the physical readiness review

RC4 is the portable new interface with **Plate Study > C. Physical Readiness** (PRIORITY-9; see
`PRIORITY9_PLATE_PHYSICAL_READINESS.md`). It keeps everything of RC3-F2: Plate Study A, the Single-Plate Workbench B
with the F1 / F2 corrections, Research Results, SP-02 / SP-10 / SP-13 and the synthetic demonstration.

RC1, RC2, RC3, RC3-F1 and RC3-F2 are not changed:

- their packaging is checked by SHA-256 in `tests/test_windows_portable_rc4.py`;
- their desktop copies have the same SHA-256 before and after the RC4 builds;
- `PROTECTED_DESKTOP` refuses to write them.

## Build

```
D:\git\abaqus-modal-comparator-work\build\portable_rc1\venv\Scripts\python.exe packaging\portable_rc4\build_portable.py --out <folder outside the repository> --desktop
```

`packaging/portable_rc4` follows the RC3 approach:

- PyInstaller onedir, no console window;
- the tracked reference files (JSON / CSV / Markdown) are placed in `docs` beside the program;
- the build refuses measurements, FE models and results, extracted FE packages and solver files.

**A new check.** The build verifies the review's archive in the portable folder: 9 cited files by their recorded
SHA-256. It also builds the review of the synthetic demonstration there.

| Item | Value |
|---|---|
| Commit | `4571e9db96160414ab588a129bbe93b47b81a2c6` (clean tree) |
| Folder | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC4\` — 729 files, 243 316 690 bytes |
| EXE | `AbaqusModalComparator.exe`, 17 593 805 bytes, SHA-256 `92967d5ee0fb405b9a8f5b933f308a71e1b00ec1aaa1a215821f68e4183658a5` |
| ZIP | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC4.zip`, 105 723 245 bytes, SHA-256 `434e594c659b82ed8b890a409ba57f21acfc89dba71008a3dd492ecd14c77a68` |
| RC1 / RC2 / RC3 / RC3-F1 / RC3-F2 (unchanged) | ZIP `e1c34b0d…` / `3c07d0b9…` / `a32f7a11…` / `afee5e44…` / `2f12f095…`; EXE `c3fc0576…` / `175e7b1a…` / `68fefa36…` / `9e990df9…` / `84ed095e…` |

**Not included:** ODB, UNV, UFF, INP, SVD, extracted FE packages (for example SP-10, 3.1 GB), caches and original data.

**An earlier RC4 build** from `2b8e108` (EXE `1dbd5396…`) was replaced by this one with `--replace`, after the two
smoke findings below. Only the RC4 copy was replaced.

## Acceptance

**Conditions:**

- Windows 150 % (DPI 144), native dialogs, UI Automation;
- isolated LOCALAPPDATA;
- verified read-only copies in `…\research\INTEGRATION_RC1_REVIEW\moved inputs\`: the UNV `76db80ae…`, the M11 package
  `354966da…`, the INP `962f75f2…` and the SP-13 UNV;
- for the EXE: unpacked from the desktop ZIP into
  `D:\git\abaqus-modal-comparator-work\research\PRIORITY9_P9_REVIEW\release 4571e9d\Copied to another place\` (a path
  with spaces), started directly with no Python on PATH and no `PYTHON*` / `QT_*` variable, with `AMC_OPEN_AUDIT`.

### PRIORITY-9 route (`p9_smoke.py`)

| Step | RUN_NEW_GUI.cmd (`4571e9d`) | RC4 EXE |
|---|---|---|
| 1. Start | 3.5 s | 10.5 s |
| 2–3. PLATE 261027 and M11 read, Polymax_bravo (11); the review verifies UNV `76db80ae…`, manifest `354966da…` and INP `962f75f2…` (VERIFIED_SHA256); `.svd` NOT_AVAILABLE | yes | yes |
| 4. 11 experimental records, 14 elastic FE modes (FE3–FE6 rigid) | yes | yes |
| 5. FE mode 7 (19.0722 Hz) and record 1 (18.6307 Hz) drawn independently | yes | yes |
| 6. Tab C: SOURCES_VERIFIED · PHYSICAL_REGISTRATION_NOT_VERIFIED · MODE_PAIRS_NOT_CONFIRMED · NOT_READY_FOR_IDENTIFICATION · READY_FOR_OWNER_REVIEW | yes | yes |
| 7. Six open facts | yes | yes |
| 8. Questions A1, A2, B1, C1, C2, D1–D4 | yes | yes |
| 9. FE-only rank 3 / 1.83 and 2 / 2.35, apart from NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS | yes | yes |
| 10. S0 / H1 / H2 only as RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY | yes | yes |
| 11. FE applicability: PLAN ONLY, variants A–E; no Abaqus process | yes | yes |
| 12. Export: the 7 documents + `owner_evidence_request.json` in a new folder; the JSON states as on the page | yes | yes |
| 14. Review saved, reopened: sources verified on disk → states kept | yes | yes |
| 13. The SP-13 UNV read instead: build refused SOURCE_NOT_VERIFIED (`8abf951d…` is not the working source) | yes | yes |
| 13. Plate UNV again, review built, SP-13 read again: STALE — NOT CURRENT, tables hidden, export disabled | yes | yes |
| 15. New physical study B: the offline fit disabled with PHYSICAL_OFFLINE_FIT_BLOCKED; "Run verified modal comparison" disabled | yes | yes |
| No page scroll bar at 900 × 680 and 1366 × 768 (tab C) | yes | yes |
| No Abaqus process; closed, exit 0; inputs unchanged | yes | yes |

**Open-file record of the EXE (1353 files):**

- none from the repository, an installed Python, a `.venv` or the user's cache;
- reference files only from the portable `docs` (18);
- the inputs only from the copies.

### Regression route of RC3 (`rc3_launcher.py`, unchanged)

| Step | RUN_NEW_GUI.cmd | RC4 EXE |
|---|---|---|
| SP-02: archived reference verified, VERIFIED_COMPARISON 6 pairs, pair FE 10 / Exp 4 drawn, XLSX + PDF + JSON | yes | yes |
| `.odb` refused, no Abaqus | yes | yes |
| Plate Study A: FE archive 8 / 8 verified, PHYSICAL_REGISTRATION_NOT_VERIFIED, gate disabled, report | yes | yes |
| Research Results PLATE 11 rows (rank 3 / 1.83, 2 / 2.35; S0 / H1 / H2 18.63088 / 158.01732 / 145.95451); SP-13 12 rows HYPOTHETICAL_SAME_POINTS; SP-10 historical and PRIORITY-6, EXP11 → FE17 +0.98 % | yes | yes |
| Plate FE7 19.0722 Hz drawn | yes | yes |
| Workbench B on the real copies: provenance refusals, measurements, link (`354966da…` / `76db80ae…`), diagnostics EXP1–EXP11 with no pairs, evidence NOT_VERIFIED, NOT_READY, offline fit blocked, export, save / reopen, SP-13 change refused | yes | yes |
| Synthetic demonstration: CONVERGED with its labels, export | yes | yes |
| Cancelled read of the 3.1 GB SP-10 package; Clear | yes | yes |
| No page scroll bar at 900 × 680 and 1366 × 768 (tab B) | yes | yes |
| End: no Abaqus, exit 0; SP-02 inputs, SP-10 package, copies and research record unchanged | yes | yes |

**Open-file record of the EXE (1973 files):**

- none from the repository or an installed Python; the only "python" paths are the build's own
  `_internal\python3.14`;
- reference files from the portable `docs` (84);
- system fonts scanned by matplotlib, as in RC1–RC3.

**SP-02** was checked on the verified RC1 input copies of the smoke tool. **No scenario was NOT_RUN.**

### Smoke findings, corrected before the final build (with tests)

1. The section button "7. Report & export" showed "Report _export" (Qt mnemonic).
2. At 900 × 680 a page scroll bar appeared, on tab C and also on tab B: the tab widget is as wide as its widest page.
   The evidence-claim list sized itself to its longest item, and the build button was wider than section B.

**Evidence:**

- `…\PRIORITY9_P9_REVIEW\gui smoke cmd 4\` (P9 route, final code);
- `…\regression cmd\`;
- `…\release 4571e9d\p9 smoke run\` and `…\release 4571e9d\regression smoke run\`: JSON results, open-file record and
  screenshots.

**Earlier runs:**

- runs 1–3 of the cmd route stopped at a screenshot scroll, at the mnemonic button and at the 900 × 680 check;
- their findings are the two corrections above.

## Tests and CI

**Targeted tests:**

- `test_plate_physical_review` (24);
- `test_windows_portable_rc4` (3) and `test_windows_portable_rc3_f2` (3);
- NEW-GUI 1–6, Plate Study, the Single-Plate Workbench (47) and Research Results;
- all pass.

**Full suite on `4571e9d`:** 3259 tests, OK, 98 skipped (the categories of RC3-F2). It ran with isolated
LOCALAPPDATA and nothing else on the screen.

**`RealInputsTests`** read the verified copies on this computer and ran here. In CI they are skipped.

**CI:**

- `2b8e108`: run 41224909640, success;
- the final documentation commit: see the report.

## Limits

- The 261027 `.svd` is not delivered, so `scan_window_offsets_mm` and `scan_metric_geometry` stay NOT_VERIFIED.
- A wide table of tab C scrolls inside itself (never the page).
- The plan is not an authorisation: every FE run needs the owner's explicit authorisation.

## RC4-F1 — the corrected build (PRIORITY-9-F1)

**Built from code commit `07c4b2f`** (branch `fix/plate-physical-readiness-rc4-f1`) with `packaging/portable_rc4_f1`.

- It is a separate folder and ZIP.
- RC1, RC2, RC3, RC3-F1, RC3-F2 and RC4 have the same SHA-256 before and after the build. `PROTECTED_DESKTOP` refuses
  to write them, and their packaging is checked by `tests/test_windows_portable_rc4_f1.py`.
- The build's own checks passed:
  - the review's archive verifies (9 files);
  - the synthetic review builds with an INTACT integrity record.

| Item | Value |
|---|---|
| Commit | `07c4b2f136f233c5bd01a4b9ca32dd7f84f4ae31` (clean tree) |
| Folder | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC4_F1\` — 731 files, 243 353 687 bytes |
| EXE | `AbaqusModalComparator.exe`, 17 607 020 bytes, SHA-256 `11c73c1149edeb94283e676ce3988cd300d17f77d7a2646b97db90b1069e4427` |
| ZIP | `C:\Users\VadimKrysko\Desktop\AbaqusModalComparator_RC4_F1.zip`, 105 753 127 bytes, SHA-256 `7e1cacad1bba9e0eefe9487a1b422fbe29ff00af5abb5ac194143c05c351e4af` |
| RC4 (unchanged) | ZIP `434e594c…`, EXE `92967d5e…` |

**An earlier RC4-F1 build** from `b522f59` (EXE `00be4abc…`) was replaced with `--replace` after the smoke finding
below. Only the RC4-F1 copy was replaced.

### F1 acceptance

**Conditions.** As for RC4:

- Windows 150 %, native dialogs, UI Automation, isolated LOCALAPPDATA;
- verified read-only copies;
- the EXE unpacked from the ZIP into
  `D:\git\abaqus-modal-comparator-work\research\PRIORITY9_F1_REVIEW\release 07c4b2f\Copied to another place\` (a path
  with spaces), started without Python on PATH and with `AMC_OPEN_AUDIT`.

The route is `p9f1_smoke.py`: the P9 route with the background work, one missing source and the revalidation.

| Step | RUN_NEW_GUI.cmd (`07c4b2f`) | RC4-F1 EXE |
|---|---|---|
| PLATE 261027 + M11 read; FE7 and EXP1 drawn independently | yes | yes |
| Review built in the background: SOURCES_VERIFIED · PHYSICAL_REGISTRATION_NOT_VERIFIED · MODE_PAIRS_NOT_CONFIRMED · NOT_READY_FOR_IDENTIFICATION · READY_FOR_OWNER_REVIEW | yes | yes |
| Six open facts, questions A1–D4, FE-only rank apart from NOT_ASSESSED, S0 / H1 / H2 research only, plan only | yes | yes |
| Export: 8 files, the JSON with SOURCES_VERIFIED and its integrity record | yes | yes |
| Saved and reopened: both sources hashed again, content intact, recomputed from the files → **CURRENT — REVALIDATED** | yes | yes |
| **One source only** (FE package cleared): build refused SOURCE_NOT_VERIFIED; the earlier review kept but **STALE**, "Sources (stored, NOT CURRENT): SOURCE_NOT_VERIFIED — …", tables hidden, export disabled | yes | yes |
| UNV replaced by SP-13: build refused SOURCE_NOT_VERIFIED, the review STALE, export disabled | yes | yes |
| Reopened again after the change: its own two files verify and recompute → CURRENT — REVALIDATED | yes | yes |
| Built again, then UNV replaced: STALE — NOT CURRENT, tables hidden, export disabled | yes | yes |
| Physical offline fit blocked; verified comparison disabled | yes | yes |
| No page scroll bar at 900 × 680 and 1366 × 768; no Abaqus; exit 0; inputs unchanged | yes | yes |

**Open-file record of the EXE (1355 files):**

- none from the repository, an installed Python, a `.venv` or the user's cache;
- the inputs only from the copies (the FE package's mode files are read by the importer; only the manifest is
  hashed).

### Regression of tabs A / B (the RC3 route, unchanged)

The route passed with `RUN_NEW_GUI.cmd` and with the RC4-F1 EXE:

- **SP-02:** VERIFIED_COMPARISON 6 pairs, pair FE 10 / Exp 4, export;
- **`.odb`:** refused;
- **Plate Study A:** 8 / 8 verified;
- **Research Results:** PLATE 11 rows, SP-13 12 HYPOTHETICAL_SAME_POINTS, SP-10 EXP11 +0.98 %;
- **Plate FE7:** drawn;
- **Workbench B on the real copies:** diagnostics with no pairs, offline fit blocked, the SP-13 change refused;
- **Synthetic demonstration:** CONVERGED;
- **SP-10:** the cancelled read of the 3.1 GB package;
- **Window sizes:** no page scroll bar;
- **End:** inputs and the SP-10 package unchanged, exit 0.

The EXE's open-file record has 1973 files, none from the repository.

### The F1 smoke finding

The first F1 cmd run (`gui smoke cmd 1`, code `b522f59`) found a defect. After a build refused for one missing
source, the reopened, revalidated review stayed labelled "Sources: SOURCES_VERIFIED".

It was corrected in `07c4b2f`, with a test: a refused build makes the shown review STALE.

**Evidence** (in `…\research\PRIORITY9_F1_REVIEW\`):

- `gui smoke cmd 2\`;
- `regression cmd\`;
- `release 07c4b2f\p9f1 smoke run\` and `release 07c4b2f\regression smoke run\`.

### F1 tests and CI

**Tests:**

- targeted: `test_plate_physical_review` (35), `test_windows_portable_rc4_f1` (3), `test_windows_portable_rc4` (3),
  NEW-GUI 1, Plate Study and the Single-Plate Workbench — all pass;
- full suite on `07c4b2f`: **3273 tests, OK, 98 skipped** (the same categories), with isolated LOCALAPPDATA and nothing
  else on the screen.

**CI:**

- `b522f59`: run 41240647933, success;
- the final documentation commit: see the report.
