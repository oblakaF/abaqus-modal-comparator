# PRIORITY-6 — SP-10 FE shapes from the existing ODB

**Status: REVIEW_READY.** Branch `research/sp10-existing-fe-shapes`, from `24b02be` (INTEGRATION-RC1).
Every value here is **RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY**.

The existing ODB of the SP-10 model `SP10_NEW_E1=E2_NSM_DENSITY` was read once with the pinned extractor. The
extracted package opens through the existing import of the new interface. SP-10 now has FE frequencies and FE shapes
up to 457.6 Hz, where before it had `.dat` frequencies only up to 220 Hz.

**What was run:**

- one Abaqus Python run of the unchanged `abaqus_scripts/extract_odb.py`;
- no Frequency solve, no model change, no other FE computation.

**What was not done:**

- no MAC, registration, orientation or mode pairing;
- no change to `src/`, SPEC, DECISIONS, STATUS, EVIDENCE, registrations, tolerances or gates;
- no change to the archived PRIORITY-1 to PRIORITY-5 tables.

Code: `research/sp10_existing_fe_shapes/run_sp10_extraction.py`. Records:

- [SP10_FE_PACKAGE.json](SP10_FE_PACKAGE.json): source, extraction, geometry, frequencies, ODB history and the SHA-256
  of every package file;
- [SP10_FE_VS_DAT.csv](SP10_FE_VS_DAT.csv).

Tests: `tests/test_priority6_sp10_fe_shapes.py`.

## 1. The source ODB and why it is this model

| Level | File | SHA-256 |
|---|---|---|
| A, original | `C:\temp\SP10_NEW_E1=E2_NSM_DENSITY.odb` | not opened (recorded from the copy manifest) |
| B, verified copy V2 | `external_models\v2_20261019\SP-10\temp_root\SP10_NEW_E1=E2_NSM_DENSITY.odb`, 979 511 712 bytes | `87a9036fb5dc314e14a1fcb0d9ef4e0175d80bc6dfb05ceeea926d1ae767302c` before and after |
| C, working copy | `research\PRIORITY6_SP10_FE_SHAPES_202610\input\SP10_NEW_E1=E2_NSM_DENSITY.odb` (read-only) | the same, before and after |

The correspondence of the ODB to the model was established before the run:

1. **Copy manifest.** The ODB and the job's `.dat`, `.inp`, `.sta`, `.log`, `.msg` and `.com` copies equal
   `COPY_MANIFEST_V2.json`. All seven are `COPIED_VERIFIED` from `C:\temp`, with the same job name.
   - `.dat`: `c2ff381c…`
   - `.inp`: `851ed627…`
2. **The job completed.** The `.log` reads "Abaqus JOB SP10_NEW_E1=E2_NSM_DENSITY COMPLETED" (Abaqus 2024,
   2026-10-19 17:24–17:43). The `.sta` reads "THE ANALYSIS HAS COMPLETED SUCCESSFULLY", with two steps.
3. **The INP is the model of M10.** Its SHA-256 `851ed627…` is the FE model of `M10_SP10_REGISTRATION_PREP`.
4. **The materials are M9's record of this model.**
   - `CFRP_BOT` 62 800 MPa, ρ 1.561e-9.
   - `CFRP_TOP` 61 300 MPa, ρ 1.508e-9.
   - G12 5 400, G13 = G23 3 000.
   - Core PLA 2 580 / 2 060 MPa.
5. **Two frequency steps** with field output U:
   - `Modal_FreeFree`, 15 modes;
   - `SP_10_MODAL_FREE`, 25 modes.

   The `.dat` of step 1 (FE7–15) equals the PRIORITY-1 SP-10 table. Step 2 adds FE16–18 = 226.95 / 265.04 /
   267.14 Hz, the values of the M10 erratum.

After the run, the ODB was shown to be this job's output by its own content (§3).

## 2. The run

- Command (one attempt, recorded before it started; a second attempt is refused):

  ```
  abaqus python scripts\extract_odb.py --odb input\SP10_NEW_E1=E2_NSM_DENSITY.odb --output output --start-mode 7 --end-mode 25
  ```

- The working directory and TEMP / TMP were set to `logs\`.
- The extractor is a copy of the pinned `extract_odb.py` (SHA-256 `039aa067…`, equal before and after). It opens the
  ODB with `openOdb(readOnly=True)`.
- Timing: 2026-10-31 16:38:31 → 16:48:24, exit 0.
- The extractor reported "modes available 1–25; requested 7–25; using modes 7–25 (19 frames)" and chose step
  `SP_10_MODAL_FREE`.
- **Mode range.** Modes 7–25 are every elastic mode the ODB holds. Modes 1–6 are the rigid-body modes (marked * in
  the `.dat`, below 0.012 Hz) and were not requested, as in the SP-13 extraction 7–30.

**Postflight:**

- the V2 copy and the working copy are unchanged;
- no unlisted file appeared in the V2 folder;
- no solver artefact is in the run folder, so no FE solve took place;
- no Abaqus process remained.

## 3. Package and frequency check

**Package (outside Git):** `D:\git\abaqus-modal-comparator-work\research\PRIORITY6_SP10_FE_SHAPES_202610\output\`.

- Extraction format 2: `manifest.json`, `geometry.csv` and `mode_0007.csv` … `mode_0025.csv`.
- 21 files, 3 096 077 377 bytes.
- **Package identity:** `manifest.json` SHA-256 `035b274c43fb8b7143bceb4dec99fdb2926a0f094cdafe1a0355faa45d8b1542`.
  The SHA-256 of every file is in `SP10_FE_PACKAGE.json`.
- Geometry: 1 667 491 nodes in three instances, which are exactly the INP's instances:
  - `CFRP_BOT-1`: 90 306;
  - `CFRP_TOP-1`: 90 306;
  - `SP02_HONEYCOMB_CORE-1`: 1 486 879.
- Every mode file holds every node.

**Frequencies against the job's own `.dat`.** The check passed, with no difference:

- the step's ODB history output (EIGFREQ, EIGVAL), for all 25 modes of `SP_10_MODAL_FREE`, rigid ones included,
  agrees with the `.dat` eigenvalue table of step 2 to its printed five significant digits;
- the frame frequency of each extracted mode agrees with the `.dat` as well;
- FE7–15 also agree with the step-1 table.

| FE mode | ODB EIGFREQ (Hz) | `.dat` (Hz) | | FE mode | ODB EIGFREQ (Hz) | `.dat` (Hz) |
|---|---|---|---|---|---|---|
| 7 | 23.885853 | 23.886 | | 17 | 265.03552 | 265.04 |
| 8 | 76.529213 | 76.529 | | 18 | 267.14438 | 267.14 |
| 9 | 79.572243 | 79.572 | | 19 | 364.50046 | 364.50 |
| 10 | 90.784561 | 90.785 | | 20 | 405.83957 | 405.84 |
| 11 | 91.985748 | 91.986 | | 21 | 411.94586 | 411.95 |
| 12 | 146.11609 | 146.12 | | 22 | 415.74905 | 415.75 |
| 13 | 210.88394 | 210.88 | | 23 | 420.85754 | 420.86 |
| 14 | 214.23444 | 214.23 | | 24 | 448.27646 | 448.28 |
| 15 | 220.04440 | 220.04 | | 25 | 457.61301 | 457.61 |
| 16 | 226.94652 | 226.95 | | | | |

**Above 220 Hz:** FE16–25, ten modes, 226.95–457.61 Hz.

## 4. The new interface (RUN_NEW_GUI.cmd)

**Setup.** One session was started by `RUN_NEW_GUI.cmd`:

- isolated LOCALAPPDATA;
- native file dialogs and UI Automation;
- the SP-10 261029 UNV taken from the moved delivery copy of INTEGRATION-RC1, through **Choose folder...** of the
  known-sources dialog.

No `src/` change was needed: the package is chosen as an FE results `manifest.json`.

| Step | Result |
|---|---|
| Start | 5.0 s; no Abaqus process |
| FE package chosen (Ctrl+1) and Inspect | "Content read; preview only", "19 modes loaded (7–25); no diagnostic messages", step `SP_10_MODAL_FREE`, frequency source **EIGFREQ history**, 1 667 491 FE nodes per mode; first read 239 s (uncached 3.1 GB) |
| Independent FE shape, FE7 23.8859 Hz | drawn ("One shape on its own coordinates … no overlay, orientation, node correspondence, MAC or mode pair") |
| Independent FE shape, FE17 265.036 Hz (above 220 Hz) | drawn |
| SP-10 261029 known source, Inspect | read; modal set `polymax_bravo`, 12 records |
| Run frequency diagnostic | **FREQUENCY_ONLY_DIAGNOSTIC**: 12 experimental, 19 elastic FE, 0 rigid FE frequencies; MAC `NOT_COMPUTED`; mode pairs `NONE (physical modal correspondence not verified)`; shapes only as UNPAIRED SHAPES |
| Check reference registration | **Not confirmed**: "the experimental file SHA-256 432adf963085… is not the PolyMAX source of an accepted physical registration"; **Run verified modal comparison** stays disabled |
| Research Results, SP-10 | **NOT VERIFIED**: "the experimental SHA-256 matches the series' 432adf963085…; the FE identity is not confirmed: SP-10 has no research FE package to compare with (the FE manifest read in the Workspace is 035b274c43fb…)" |
| End | no Abaqus process; window closed, exit 0; the package files unchanged |

**Frequency proximity.** These are the nearest FE frequencies shown by the diagnostic. They are **frequency proximity
only, not mode pairs**: no registration exists, and no MAC was computed or used.

| EXP | Hz | nearest FE | Δ % | second | Δ % |
|---|---|---|---|---|---|
| 1 | 26.5014 | FE7 23.8859 | −9.87 | FE8 | +188.77 |
| 2 | 76.3913 | FE8 76.5292 | +0.18 | FE9 | +4.16 |
| 3 | 79.8004 | FE9 79.5722 | −0.29 | FE8 | −4.10 |
| 4 | 92.3388 | FE11 91.9857 | −0.38 | FE10 | −1.68 |
| 5 | 94.9947 | FE11 91.9857 | −3.17 | FE10 | −4.43 |
| 6 | 148.1323 | FE12 146.1161 | −1.36 | FE11 | −37.90 |
| 7 | 207.3311 | FE13 210.8839 | +1.71 | FE14 | +3.33 |
| 8 | 214.4390 | FE14 214.2344 | −0.10 | FE13 | −1.66 |
| 9 | 222.2567 | FE15 220.0444 | −1.00 | FE16 | +2.11 |
| 10 | 228.7088 | FE16 226.9465 | −0.77 | FE15 | −3.79 |
| 11 | 262.4545 | FE17 265.0355 | +0.98 | FE18 | +1.79 |
| 12 | 266.8519 | FE18 267.1444 | +0.11 | FE17 | −0.68 |

**Compared with PRIORITY-1.** EXP11 and EXP12 now have an FE frequency nearby; PRIORITY-1 found none within 15 %,
because its FE range ended at 220 Hz. Close groups remain:

- EXP4 / EXP5 near FE10 / FE11;
- EXP7 / EXP8 near FE13 / FE14;
- EXP11 / EXP12 near FE17 / FE18.

A nearest frequency is not a modal correspondence.

## 5. Limits

- **No physical registration of SP-10.** The FE shapes can be viewed only as independent, unpaired views. A verified
  MAC needs an accepted registration (M10 questions Q1–Q8, owner-dependent), which this task does not create.
- **The archived Research Results of SP-10 are unchanged.** They were made from the `.dat` alone:
  - `FE_SHAPES_UNAVAILABLE`;
  - "no FE frequency within 15 %" for EXP11–12;
  - "MAC NOT_AVAILABLE".

  They are not tied to this package and stay NOT VERIFIED. Linking them would be a new research step.
- **Size.**
  - The package is 3.1 GB. The first read in the interface takes about 4 minutes; the fast cache of about 0.7 GB
    then lies in LOCALAPPDATA.
  - The package, the working ODB copy, logs and screenshots stay outside Git, under
    `D:\git\abaqus-modal-comparator-work\research\PRIORITY6_SP10_FE_SHAPES_202610\`.
- **One model only.** The other SP-10 models (`SP10nemash63000`, `SP10newmash`, `SP10_new_E_NSM_DENS`) were not
  extracted.
- **Frame frequency precision.** The manifest's frame frequency has the five significant digits of the Abaqus frame
  description. The interface shows the full-precision EIGFREQ history.
- **Machine-specific script.** `run_sp10_extraction.py` reads the work folder of this computer. Its tests do not
  need the data or Abaqus.
