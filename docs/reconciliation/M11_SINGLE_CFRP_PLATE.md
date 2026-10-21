# M11 — Single CFRP plate (frequency diagnostics; analysis only)

**Status: `REVIEW_READY` / outcome `FREQUENCY_DIAGNOSTIC_ONLY`.**

- The plate has free-free FE models and experimental frequencies, but no experimental mode-shape data file, no
  measured thickness, mass or layup record, and no physical registration.
- No mode pairing is confirmed. No constant was fitted.
- No FE solve, Abaqus Python, Auto-ID or LM was run. No original was modified.
- Nothing here is governed evidence.

Work data, figures and tools: `D:\git\abaqus-modal-comparator-work\runs\m11_carbon_plate`; machine summary
[M11_SINGLE_CFRP_PLATE.json](M11_SINGLE_CFRP_PLATE.json).

## 1. Sources found and copied (question 1)

**Real locations:**

- The user's "пластины" folder is `C:\temp\12 sampls\results\Plate`. It contains only the CAE `SInglePlate1mm.cae`
  and its journal `SInglePlate1mm.jnl`.
- The analysis jobs were written to the Abaqus working directory `C:\temp`:
  - `CFRP_S4R_0875_FreeFree`, `CFRP_S4R_WEDGE_FreeFree`, `CFRP_C3D8I_0875_FreeFree` (2026-10-20);
  - `E30E26` (2026-10-21).
- The replay files `C:\temp\abaqus.rpy.66` (session 20.10) and `C:\temp\abaqus.rpy` (session 21.10) record the
  editing history.

**Updated Excel:**

- `results sadwich.xlsx` on the Desktop, modified 2026-10-20 18:37 (101.6 MB; it was 68.5 MB in the 19.10 copy):
  - **new data sheet `Sample (2)`**, titled "Plate 301x300 1mm": frequencies, damping and 48 embedded mode-shape
    screenshots;
  - new sheet `Sample (3)`: an empty template.
- A second new file, `Experiment_Freq_damping_LMS_onlyupdated.xlsx` (Desktop, 20.10 17:31), sheet `Updated_file`
  ("plate only, 300*300, 1mm"), holds the same 10 experimental frequencies and damping values.
- `Образцы_трекер_Abaqus.xlsx` is **unchanged** (SHA-256 equal to the 19.10 copy).

**Copies.** New versioned directories outside git:

- `external_models\v3_20261021\Plate` (`COPY_MANIFEST_V3.json`, 45 files);
- `excel_copies\20261021` (`COPY_MANIFEST.json`, 3 files).

The SHA-256 of each source was taken before copying, of the copy after, and of the source again. All 48 are
`COPIED_VERIFIED`; no source changed during copying. The first copy run stopped on a console encoding error after the
last file was copied and verified, so the manifests were written by a second pass that re-hashed every source and copy.
`v2_20261019` and `excel_copies\20261019` were not touched.

The Excel files were read with openpyxl only, never saved: stored values and formulas were read separately (the plate
sheets contain **no formulas**, only typed text such as "33.4491 Hz"). Images were read from the copy's zip archive.

**Not found anywhere** (`C:\temp`, Desktop, Downloads, `D:\Snadwich`, `I:\Sumin`, the article vault):

- an experimental UNV, SVD or LMS project for the plate;
- a specimen note, photograph, thickness or mass record.

The plate is **not in the specimen catalog**: SP-11 is twill 350 × 347 × 0.45, SP-12 plain 0.25 with no experiment,
and SP-15 a 520 mm plate. Its identity is UNKNOWN.

## 2. The plate: what the data establish (questions 2 and 5)

| Item | Value | Source / status |
|---|---|---|
| Plan | **x 301 × y 300 mm** | owner's measurement sheet (§8); it matches the CAE sketch and the Excel title |
| Thickness | **20 edge readings, 0.71–0.94 mm; mean 0.876, median 0.915** (§8). Side means 0.880 / 0.816 / 0.882 / 0.926 mm | owner's measurement sheet; the instrument is not stated. The model's 0.875 is the mean of these readings; the wedge model 0.93 → 0.81 uses the two extreme side means. `E30E26` (t = 1.0) contradicts them |
| Mass | **118.37 g** | owner's measurement sheet. The models' 118.36 g (ρ 1.498·10⁻⁹ × 0.875 mm) is this mass |
| Areal mass / density | **1 310.9 g/m²**; 1.496 g/cm³ at the mean thickness | DERIVED from the measured mass, plan and mean edge thickness |
| Weave / material | **UNKNOWN**. The material is named `CFRP_T300_TEST` | no record |
| Plies, layup, fibre direction | **UNKNOWN** | all models use one homogeneous material on global axes |
| Experimental conditions (suspension, excitation, scanner) | **UNKNOWN** | the screenshots look like full-field scans; no setup record |

**Abaqus inputs (all assumed, none measured):**

| Job (stored result) | Elements | t, mm | E1 / E2, MPa | ν12 | G12 | E3 / G13 / G23 | ρ, t/mm³ |
|---|---|---|---|---|---|---|---|
| `CFRP_S4R_0875_FreeFree` | S4R, 10 000 elements, 3 mm, 5 integration points | 0.875 | 56 000 / 56 000 | 0.05 | 5 000 | 8 500 / 3 000 / 3 000 | 1.498e-9 |
| `CFRP_S4R_WEDGE_FreeFree` | S4R, nodal thickness | 0.93 → 0.81 | 56 000 / 56 000 | 0.05 | 5 000 | same | 1.498e-9 |
| `CFRP_C3D8I_0875_FreeFree` | C3D8I, 30 000 elements, 3 through the thickness | 0.875 | 60 000 / 60 000 | 0.05 | 5 000 | same | 1.498e-9 |
| `E30E26` | C3D8I, as above | 1.0 | 30 820 / 26 520 | 0.3 | 10 000 | same | 1.31522e-9 |

**Common to all four jobs:**

- Boundary conditions: **none**, i.e. free-free. There are no springs, masses or suspension. Whether this represents
  the test is UNKNOWN.
- One step `Modal_FreeFree_plate`, Lanczos, 20 modes, mass normalisation. The `.dat` gives 6 rigid modes and elastic
  modes 7–20.
- The ODBs were copied but not opened: no extraction was run.

**Editing history from the replay files:**

- `E30E26` was submitted 5 times while the inputs were changed by hand:
  - first G12 6 050 with t 0.875 and ρ 1.31522·10⁻⁹;
  - then t = 1.0;
  - then G12 16 000;
  - finally G12 10 000, which is the stored result.

  This is a manual calibration attempt. Its constants are fitted values, not measurements.
- `CFRP_C3D8I_0875_FreeFree` was first run with E 56 000 and then re-run with E 60 000, overwriting the result.

## 3. Frequencies and their FE sources (question 3)

**Excel column provenance**, checked value for value against the stored `.dat` results:

| Excel `Sample (2)` column | Header | Source | Status |
|---|---|---|---|
| B | Exp freq | LMS text values, identical to `Experiment_Freq_damping_LMS_onlyupdated.xlsx` | experimental frequencies only; no shape data file |
| C, first value | Abaq Freq (shell) | `CFRP_S4R_0875_FreeFree`, modes 7–18 | **12 of 12 exact** |
| C, second value | "shell (thickness)" | `CFRP_S4R_WEDGE_FreeFree` | 9 of 12 exact; **3 transcription slips**: 19.997 for 18.997, 59.383 for 59.389, 61.483 for 61.438 |
| D | Abaq Freq (plate) | not in any stored result | probably the first `CFRP_C3D8I_0875` run with E 56 000 (replay history; the twist frequency 19.09 equals the stored 19.10; that mode depends almost only on G12, t and ρ, not on E); it was **overwritten** and is not reproducible |
| E | Error | empty | — |
| F | Damping | LMS | 0.12–0.58 % |

`E30E26` (21.10) is not in Excel.

**Rank table.** FE frequencies by rank; FE modes 7, 8, … in the `.dat` are elastic ranks 1, 2, …. The deviation is
FE / experiment − 1.

| Exp rank | Exp, Hz | Damping, % | S4R 0.875 | Wedge | C3D8I E 60 000 | `E30E26` | Pairing status |
|---|---|---|---|---|---|---|---|
| 1 | 33.449 | 0.50 | 19.07 (−43.0 %) | 19.00 (−43.2 %) | 19.10 (−42.9 %) | 31.97 (−4.4 %) | rank only; magnitude screenshots resemble the FE twist mode |
| 2 | 55.254 | 0.35 | 59.87 (+8.4 %) | 59.39 (+7.5 %) | 61.95 (+12.1 %) | 48.67 (−11.9 %) | rank only |
| 3 | 68.102 | 0.12 | 62.01 (−9.0 %) | 61.44 (−9.8 %) | 64.16 (−5.8 %) | 59.99 (−11.9 %) | rank only |
| 4 | 71.960 | 0.21 | 71.85 (−0.2 %) | 71.43 (−0.7 %) | 73.68 (+2.4 %) | 82.91 (+15.2 %) | rank only |
| 5 | 80.474 | 0.29 | 72.19 (−10.3 %) | 72.10 (−10.4 %) | 74.03 (−8.0 %) | 85.15 (+5.8 %) | rank only |
| 6 | 116.90 | 0.31 | 116.58 (−0.3 %) | 115.93 (−0.8 %) | 118.93 (+1.7 %) | 145.94 (+24.8 %) | rank only |
| 7 | 144.60 | 0.58 | 167.49 (+15.8 %) | 164.12 (+13.5 %) | 173.21 (+19.8 %) | 152.64 (+5.6 %) | rank only; the screenshots differ |
| 8 | 158.84 | 0.35 | 168.61 (+6.2 %) | 166.42 (+4.8 %) | 174.37 (+9.8 %) | 156.14 (−1.7 %) | rank only; the screenshots differ |
| 9 | 178.04 | 0.13 | 174.80 (−1.8 %) | 174.80 (−1.8 %) | 180.20 (+1.2 %) | 168.53 (−5.3 %) | rank only |
| 10 | 213.17 | 0.28 | 179.90 (−15.6 %) | 180.49 (−15.3 %) | 185.46 (−13.0 %) | 188.96 (−11.4 %) | rank only |

**No pairing is physically confirmed.**

- The only shape information is the screenshots in Excel: magnitude colour maps without phase, with unknown axes and
  orientation.
- MAC needs the experimental shape file (UNV dataset 55 / 58 or the PSV project) and a physical registration; neither
  exists.
- The rank alignment visibly breaks at ranks 7–8.

## 4. Do the experiment and the model agree? (question 4)

**No, for the stored models with E 56 000–60 000 and G12 5 000:**

- **Rank 1:** the experiment is 33.45 Hz and the models give 19.0–19.1 Hz (−43 %).
- **The frequency ratio f1 / f2:** 0.605 in the experiment, against 0.31–0.32 in those models. `E30E26` gives 0.657.
- **Near-degenerate pairs:** the square, E1 = E2 models predict 71.85 / 72.19 Hz and 167.5 / 168.6 Hz. The experiment
  instead shows split pairs, 71.96 / 80.47 Hz and 144.6 / 158.8 Hz. That points to in-plane orthotropy, a thickness
  or geometry imperfection, or a different mode identity — the data cannot tell which.

**The boundary conditions cannot be compared**, because the test setup is not recorded. The FE models are ideal
free-free.

`E30E26` brings rank 1 to −4.4 % but makes other ranks worse (rank 6 +24.8 %, rank 4 +15.2 %). Hand-tuning on rank
order is not converging to a consistent set.

## 5. What the plate test can and cannot constrain (question 6)

**Twist mode.** For a free square plate the first mode is the twist mode. Its frequency is governed by the twisting
stiffness:

> f_twist ≈ (12 / π) · √(D66 / ρh) / (a·b), with D66 = G12·t³ / 12 for a homogeneous plate (a Rayleigh estimate with w = xy).

This estimate reproduces the stored FE results within 2–5 %: FE / Rayleigh = 0.977 for the S4R and solid models,
0.949 for `E30E26`.

**If experimental rank 1 is the twist mode** (consistent with the screenshot, not confirmed):

- **D66/(ρh) of the plate is (33.45 / 19.07)² = 3.08 times the model value.**
- With the model's areal mass, this is D66 ≈ 860 N·mm, i.e. G12_eff·t³ ≈ 10 300 N·mm.
- The equivalent homogeneous G12 is about 19 000 / 15 300 / 13 000 MPa for the measured side mean 0.816, the overall
  mean 0.876 and the side mean 0.926 mm. The model's areal mass equals the measured one (§8).

**This is a scaling consequence, not an identified constant.** These values are 2–4 times the 4 500–6 000 MPa used for
the sandwich faces and unusually high for a 0/90 woven laminate. Either:

- the plate's layup contains ±45° plies; or
- the plate is another material; or
- rank 1 is not the twist mode.

The data cannot decide among them.

**What can be identified once the missing data exist.** The free-free frequencies of a plate with confirmed mode
pairs can identify the effective flexural stiffnesses D11, D22, D12, D66 (normalised by ρh). Today only the D66/(ρh)
scaling above is available, and only conditionally. Converting D to ply E1, E2, G12 additionally needs the layup
(laminate theory), and flexural stiffness is not membrane stiffness for a layered laminate.

**Needed to go further:**

- the experimental shape file (Test.Lab / PSV export with dataset 55 / 58, or the `.svd`) and the stored camera frame
  for a physical registration;
- a thickness map (at least 9 points) and the measured mass;
- the number of plies, their stock and orientation relative to the edges;
- the suspension and excitation record;
- coupon tests if ply constants, not effective plate stiffness, are wanted.

Constants were not fitted, as instructed. A Rayleigh-Ritz or FE-based identification of D11–D66 is a separate,
authorised step.

## 6. Relation to the six sandwich specimens (question 7)

| | Plate | SP-02 | SP-03 | SP-04 | SP-05 | SP-10 | SP-13 |
|---|---|---|---|---|---|---|---|
| Face stock / weave | UNKNOWN | old plain 0.45 | old twill 0.45 | old plain 0.25 | old plain 0.25 | old plain 0.45 | old plain 0.45 |
| Thickness, mm | UNKNOWN (model 0.875; nominal 1) | 0.45 | 0.45 | 0.25 | 0.245 | 0.40 / 0.39 | 0.425 |
| Areal mass, g/m² | about 1 311 (model-implied) | 668.6 | 628–631 | 342–343 | 345–346 | 603–609 | 598–617 |
| FE E1 = E2 / G12, MPa | 56 000–60 000 / 5 000 (template); `E30E26` 30 820 / 26 520 / 10 000 (manual fit) | 52 000–54 400 / 4 500 | 52 000–54 400 / 4 500 | 46 200 / 6 000 | 46 200 / 6 000 | 61 300–62 800 / 5 400 | 52 000–57 600 / 4 500 |

**Observations:**

- The implied areal mass and the 0.875 mm thickness are about twice an old 0.45 plain face (0.9 mm, 1 200–1 340 g/m²).
  This is consistent with, but not evidence of, a two-ply laminate of that stock.
- The batch, weave, ply count and orientation are not recorded, so **no common material can be claimed**. E1, E2,
  G12 and density were not transferred in either direction.
- The plate test is flexural. The faces work mainly in membrane in the sandwich panels, so even for the same material
  the plate's flexural constants are not the faces' membrane constants unless the laminate is homogeneous through the
  thickness.

**Can it check the faces of SP-02 / SP-10 / SP-13? Not now.** It would become useful in three steps:

1. The owner confirms that the plate is made of the same stock as those faces and states its ply count and orientation.
2. The shape file and the thickness and mass measurements exist.
3. D66 and D11 / D22 are identified under an authorised step.

**Hypothesis for later testing, not a finding.** Every PLA-core sandwich model has a low first (twist) mode,
−16 … −28 % (M9). That is consistent in direction with a G12 template that is too low, as the plate test also
suggests. M9 attributed the deficit to core / adhesive model form. The plate cannot discriminate between the two until
its material identity and layup are known.

## 7. Questions for the owner

1. What is the plate, and is it a new specimen ID? Which stock (old plain 0.45, old twill, new plain 0.25 …), how many
   plies, and in what orientations relative to the 301 / 300 mm edges?
2. ~~Were the thickness and the mass measured?~~ **Answered 2026-10-21 (§8)**: mass 118.37 g, 301 × 300 mm, 20
   edge thickness readings. Still open:
   - which physical edge each row 1–4 is, and from which corner;
   - the instrument;
   - whether the interior was measured.
3. Test setup: suspension (cords, positions), excitation (shaker or hammer, point), scanner. Is there an LMS / PSV
   project or a UNV export of the plate test? Where is it?
4. Column D of `Sample (2)` ("Abaqus plate (thinkness)"): which run produced it?
5. Should the Excel transcription slips in column C (wedge) be corrected by the owner?

## 8. Addendum (2026-10-21): the owner's measurement sheet

The owner sent a photograph of the handwritten measurement sheet: "Мерил по 5 точек на стороне", i.e. five points
per side. The copy is `runs\m11_carbon_plate\owner_records\plate_measurements_20261021.jpg`, SHA-256 `df5339cd…`.
The transcription is in `plate_measurements_20261021.json`, and the photograph is not committed. This is a HUMAN
record. It is not governed evidence, and no instrument or resolution is stated.

**Transcription:**

- Header: "Plate – 1mm"; m = 118.37 g; x = 301; y = 300.
- Three draft lines h1–h3 are struck through on the sheet and are not used.
- The sketch shows the measuring points along two edges, about 4.5 and 6.5 mm from the edge. **All readings are
  therefore at the perimeter; the interior thickness is not measured.**

| Row (side) | Readings, mm | Mean |
|---|---|---|
| 1 | 0.94, 0.92, 0.94, 0.89, **0.71** | 0.880 |
| 2 | 0.79, 0.82, 0.84*, 0.81, 0.82 | 0.816 |
| 3 | **0.74**, 0.89, 0.94, 0.92, 0.92 | 0.882 |
| 4 | 0.93, 0.94, 0.93, 0.92, 0.91 | 0.926 |

\* The reading could also be 0.81; the overall mean would then be 0.8745 instead of 0.876.

**Consequences:**

- The mass and the 0.875 mm mean thickness of the stored models are confirmed as measured inputs, not template
  values.
- The thickness varies by −19 % / +7 % around the mean. The two low readings, 0.71 and 0.74, are at the ends of rows
  1 and 3, possibly corners. The flexural stiffness scales with t³, so the plate is not uniform. The wedge model
  represents only one hypothesis: sides 2 and 4 opposite, with a linear taper.
- The twist-mode conclusion of §5 stands: with the measured areal mass and thickness, the equivalent homogeneous
  G12 is about 13–19 GPa, if experimental rank 1 is the twist mode. The elastic constants, weave and layup remain
  UNKNOWN. **Nothing was fitted.**

**Still open:**

- the assignment of rows 1–4 to the physical edges, and the corner each row starts from;
- the instrument;
- the interior thickness;
- the weave and layup;
- the test setup;
- the experimental shape file.

## 9. What did not change

- SPEC, DECISIONS, EVIDENCE, registrations, criteria and gates.
- Every original and every earlier copy.
- Branch `analysis/m10-sp10-registration-prep` and PR #94.
- No FE solve, no Abaqus Python, no Auto-ID or LM, no MAC, no material change.
- M8 original gate `NOT_MET`; production calibration BLOCKED / NOT_AUTHORISED; D-077 NO_GLOBAL_PARAMETER_VALUE.
