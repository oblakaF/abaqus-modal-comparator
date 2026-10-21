# M11 — Single CFRP plate (frequency diagnostics; analysis only)

**Status: `REVIEW_READY` / outcome `FREQUENCY_DIAGNOSTIC_ONLY`.**

- The initial frequency-only review was supplemented by the owner's mass and 20 perimeter thickness readings (§8)
  and verified copies of the LMS/PSV/PolyMAX modal and FRF data (§9): **10 experimental shapes at 289 points**.
- The experimental first shape is twist-dominated, but no physical FE registration or experimental/FE MAC pairing
  exists. Laminate layup, measured interior thickness and the complete shaker/suspension setup remain unknown.
- No material constant was fitted.
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
| Weave / material | **Plain weave, stated by the owner (§8.1)**; batch and equivalence to sandwich-face stock UNKNOWN. Abaqus names the material `CFRP_T300_TEST` | HUMAN statement; ply count and orientation UNKNOWN |
| Plies, layup, fibre direction | **UNKNOWN** | all models use one homogeneous material on global axes |
| Experimental conditions (suspension, excitation, scanner) | **Partially known**: the experiment used PSV scanning with a shaker and suspension; the exact attachment geometry, support stiffness and excitation record are UNKNOWN | LMS/PSV/UNV source (§9), owner statement |

**Abaqus inputs:** the elastic constants are assumed/fitted rather than measured; the S4R mass and nominal thickness reflect the owner's measurements (§8), but this is not a validated interior thickness field.

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

**No experimental/FE pairing is physically confirmed.** This rank table documents the original frequency-only
screen; it predates the recovery of the experimental PolyMAX shapes (§9).

- The experimental shape file and PSV project **are now available** (10 PolyMAX modes, 289 points); their diagnostic
  shape types and FRF checks are in §9.
- FE shape extraction from a verified ODB copy, an independently supported physical registration, and MAC are still
  missing; no experimental-to-FE pair has been accepted.
- Frequency rank alignment visibly breaks at ranks 7–8.

## 4. Do the experiment and the model agree? (question 4)

**Not established as a physically paired comparison.** The frequency-by-rank spectra of the stored models with E 56 000–60 000 and G12 5 000 differ substantially from the listed experimental spectrum:

- **Rank 1:** the experiment is 33.45 Hz and the models give 19.0–19.1 Hz (−43 %).
- **The frequency ratio f1 / f2:** 0.605 in the experiment, against 0.31–0.32 in those models. `E30E26` gives 0.657.
- **Near-degenerate ranks:** the near-square E1 = E2 models predict 71.85 / 72.19 Hz and 167.5 / 168.6 Hz, whereas
  the experimental list has 71.96 / 80.47 Hz and 144.6 / 158.8 Hz. These are **not confirmed paired doublets**:
  experimental modes 4 and 5 have low modal phase collinearity (MPC 0.59 and 0.44; §9), so their shapes are not
  reliable grounds for inferring material orthotropy. Thickness variation, fixture effects and mode identity all
  remain possible explanations.

**The boundary conditions are not equivalent by evidence:** the models are ideal free-free, whereas the test involved
suspension and a shaker. The recorded FRF contains rigid-body-like peaks at 9.06 and 15.6 Hz (§9); their influence
on elastic modes is unknown because support and attachment details have not been measured.

`E30E26` brings the first listed rank difference to −4.4 % but worsens others (rank 6 +24.8 %, rank 4 +15.2 %).
These frequency-by-rank comparisons do not establish a consistent modal fit or a converged identification.

## 5. What the plate test can and cannot constrain (question 6)

**Twist-mode hypothesis.** In the stored ideal free-free FE models the first *elastic* mode is twist-dominated.
This is not a universal ordering for every laminate or set of test conditions, and **the first listed experimental
frequency may not be the lowest physical mode**. The modeled twist frequency is governed by the twisting stiffness:

> f_twist ≈ (12 / π) · √(D66 / ρh) / (a·b), with D66 = G12·t³ / 12 for a homogeneous plate (a Rayleigh estimate with w = xy).

This estimate reproduces the stored FE results within 2–5 %: FE / Rayleigh = 0.977 for the S4R and solid models,
0.949 for `E30E26`.

**Only if experimental rank 1 is the same twist-mode branch**, the real test is sufficiently close to free-free,
and the model and test have sufficiently similar modal-shape factors, can a like-for-like frequency scaling be
considered. The available FRF/PolyMAX evidence (§9) does **not identify** an elastic mode near 19 Hz, but cannot
by itself validate the free-free test assumption:

- The **squared frequency ratio** is (33.45 / 19.07)² ≈ 3.08. A model with the same geometry, mode branch and
  comparable modal-shape factor would need roughly 3.08 times the modeled D66/(ρh) to match this rank.
  **This is not an experimental determination of the plate's D66/(ρh).**
- The owner's measured mass and plan area now substantiate the **areal mass** used by the model (§8). However,
  the comparable modal-shape factor and negligible support/attachment effects are **not established**. Conditional
  on both, the illustration is D66 ≈ 860 N·mm, i.e. G12_eff·t³ ≈ 10 300 N·mm.
- The equivalent homogeneous G12 is about 19 000 / 15 300 / 13 000 MPa for the measured side mean 0.816, the overall
  mean 0.876 and the side mean 0.926 mm. The model's areal mass equals the measured one (§8).

**This is a conditional model-scaling illustration, not an identified constant.** These values are 2–4 times the
4 500–6 000 MPa assumed for the sandwich faces. Possible explanations include:

- the plate's layup contains ±45° plies; or
- the plate is another material;
- a lower torsional mode was absent from the reported modal set;
- rank 1 is not the twist mode, or the experimental suspension is not well represented by free-free.

The data cannot decide among them.

**What could be constrained once the missing data exist.** Correctly paired free-free frequencies and shapes,
with measured mass, thickness, orientation and boundary conditions, may constrain effective flexural stiffnesses
D11, D22, D12 and D66 (relative to areal mass). **Separately identifying all four is not guaranteed**: an
identifiability/sensitivity-rank check is required before any fit. The D66/(ρh) scaling above remains conditional,
not a released experimental property. Converting D to ply E1, E2 and G12 additionally needs the layup (laminate
theory); flexural and membrane stiffness of a layered laminate need not have identical effective constants.

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
| Face stock / weave | plain (owner); batch/layup UNKNOWN | old plain 0.45 | old twill 0.45 | old plain 0.25 | old plain 0.25 | old plain 0.45 | old plain 0.45 |
| Thickness, mm | 0.71–0.94 edge readings, mean 0.876; interior UNKNOWN | 0.45 | 0.45 | 0.25 | 0.245 | 0.40 / 0.39 | 0.425 |
| Areal mass, g/m² | 1 310.9 (measured mass / measured plan area) | 668.6 | 628–631 | 342–343 | 345–346 | 603–609 | 598–617 |
| FE E1 = E2 / G12, MPa | 56 000–60 000 / 5 000 (template); `E30E26` 30 820 / 26 520 / 10 000 (manual fit) | 52 000–54 400 / 4 500 | 52 000–54 400 / 4 500 | 46 200 / 6 000 | 46 200 / 6 000 | 61 300–62 800 / 5 400 | 52 000–57 600 / 4 500 |

**Observations:**

- The **measured** areal mass and mean edge thickness are about twice an old 0.45 plain face (0.9 mm, 1 200–1 340 g/m²).
  This is consistent with, but not evidence of, a two-ply laminate of that stock.
- The owner reports a plain weave, but the batch, ply count and fibre orientation are not recorded, so **no common
  material can be claimed**. E1, E2,
  G12 and density were not transferred in either direction.
- The plate test is flexural. The faces work mainly in membrane in the sandwich panels, so even for the same material
  the plate's flexural constants are not the faces' membrane constants unless the laminate is homogeneous through the
  thickness.

**Can it check the faces of SP-02 / SP-10 / SP-13? Not now.** It would become useful in three steps:

1. The owner confirms the plate is from the same stock as those faces and states its ply count and orientation.
2. The already recovered shape data (§9) receive a defensible physical FE registration; the thickness **interior**
   field and shaker/suspension influence are independently assessed.
3. A separate authorised identifiability study establishes which effective flexural stiffness combinations can be
   constrained; no membrane material constants are inferred merely from the plate-frequency match.

**Hypothesis for later testing, not a finding.** The lowest frequency-by-rank FE entry of the PLA-core sandwich
models is 16–28 % below the corresponding experimental entry (M9); these are not universally MAC-confirmed twist
pairings. A low G12 template is one *possible* explanation, but the unregistered plate does not establish it.
M9 explicitly retained core/bond modelling, face orientation, modal correspondence and fixture effects as competing
explanations. The plate cannot discriminate among them until its modal identity, test setup, material and layup are known.

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
5. Can the owner confirm that the three wedge-column entries differing from saved `.dat` values are transcription
   mistakes? **Do not edit the original Excel;** any corrected values belong only in a separately traced analytical copy.
6. What was the acquisition/PolyMAX identification frequency range and stabilization selection? Specifically, was a
   peak or torsional mode around 19 Hz searched for and excluded, or could a lower mode have been missed?

## 8. Addendum (2026-10-21): the owner's measurement sheet

The owner sent a photograph of the handwritten measurement sheet: "Мерил по 5 точек на стороне", i.e. five points
per side. The copy is `runs\m11_carbon_plate\owner_records\plate_measurements_20261021.jpg`, SHA-256 `df5339cd…`.
The transcription is in `plate_measurements_20261021.json`, and the photograph is not committed. This is a HUMAN
record, not governed evidence. The measurement **photograph alone** does not state the instrument; the owner later
specified a caliper of 0.01 mm resolution and an electronic caliper (§8.1).

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

- The stored models' mass equals the measured mass (118.37 g), and their 0.875 mm equals the mean of the 20 edge
  readings. **This mean is not the plate's thickness**: the interior is not measured (R4).
- The thickness varies by −19 % / +7 % around the mean. The two low readings, 0.71 and 0.74, are at the ends of rows
  1 and 3; according to the owner they are not corners but edge readings about 0.5 mm from the edge (§8.1). The flexural stiffness scales with t³, so the plate is not uniform. The wedge model
  represents only one hypothesis: sides 2 and 4 opposite, with a linear taper.
- The §5 scaling remains conditional (see §9): with the measured areal mass and thickness, the equivalent
  homogeneous G12 would be about 13–19 GPa, only under the §5 conditions. The elastic constants, weave and layup remain
  UNKNOWN. **Nothing was fitted.**

**Still open:**

- the assignment of rows 1–4 to the physical edges, and the corner each row starts from;
- the instrument;
- the interior thickness;
- the weave and layup;
- the test setup;
- the experimental shape file.

### 8.1 Owner's answers (2026-10-21, second message)

These are HUMAN statements and are not governed evidence.

- **Rows:** 1 = top, 3 = bottom, 2 = right; the owner wrote "3 левая" for the left edge, presumably row 4 (to be
  confirmed). Left and right are **seen from the shaker side**.
- **Reading:** row 2, column 3 = 0.84.
- **Low values 0.71 / 0.74:** "not in the corners, but at the edge, about 0.5 mm from it".
- **Instrument:** a caliper with 0.01 mm resolution, plus an electronic one.
- **Material:** plain carbon; the number of plies is unknown to the owner.
- **Experiment files:** the experiment is in `D:\Snadwich\Plate`.

## 9. Addendum (2026-10-21): the plate experiment `D:\Snadwich\Plate`

**Copies.** `external_models\v3_20261021\Plate\snadwich_Plate` (`COPY_MANIFEST_V3_SNADWICH_PLATE.json`), 5 files,
SHA-256 equal before copying, after copying and at the source again:

| File | SHA-256 |
|---|---|
| `300by300_plate_only_1mm_261016.lms` (Test.Lab project) | `d862ee20…` |
| `300by300_plate_only_1mm_261016.svd` (PSV) | `0a770b1b…` |
| `300by300_plate_only_1mm_261016.unv` (PSV export, 289 points) | `6d66eafe…` |
| `300by300_plate_only_1mm_261016_POLYMAX.unv` | `117c893b…` |
| `Experiment_Freq_damping_LMS_onlyupdated.xlsx` | identical to the Desktop copy |

**Modal data.** The PolyMAX set `Polymax_bravo` has 10 modes, 289 points (17 × 17) and the Z component only. Its
frequencies equal the Excel and LMS values to 4 decimals. The session is 2026-10-16.

**Physical scan reconstruction** (M2.3 code; diagnostic):

- The PSV MeasPoints validate against the UNV geometry: maximum residual 1.1·10⁻³, limit 2·10⁻³.
- **Three recorded deviations** from the accepted constants were needed:
  1. the `.svd` stores an anomalous full-frame rectangle, v −2.4667…1.0 instead of the 0…1 of every other session;
     the standard v 0…1 is used;
  2. the scan grid ends about 167 px from the left plate edge, so `EDGE_SEARCH_WINDOW_PX` is 220 instead of 150;
  3. the bottom edge lies in front of the dark shaker with the opposite brightness polarity, so it is fitted on the
     inverted image with a step threshold of 8.
- **Result:**
  - edge RMS 0.13–0.29 px;
  - scan window 215.4 × 285.2 mm;
  - gaps to the edges, left / right / bottom / top: 56.4 / 29.2 / 7.0 / 7.8 mm;
  - camera-grid model residual 1.29 / 3.23 mm (median / maximum);
  - axis misalignment 0.87°.
- Whether the 301 mm side was horizontal cannot be resolved from the frame: the aspect test gives 0.996 against
  1.003.
- In the frame the shaker is behind the plate, so the scanner saw the face opposite the one the thickness rows were
  described from. Seen by the scanner, the thin side (row 2, mean 0.816) is on the **left** and the thick side
  (row 4, 0.926) on the **right**.

**Experimental mode types** (experimental data only; no FE shape, no MAC): see `fig_plate_modes.png` and
`plate_modes.json`.

| Mode | Hz | MPC | Pattern |
|---|---|---|---|
| 1 | 33.45 | 0.85 | **twist**: nodal lines along both centre lines, quadrant signs alternate, 96 % of the shape (after removing the rigid plane) is the xy twist function |
| 2 | 55.25 | 0.88 | two curved nodal lines parallel to the scanner x axis: bending with curvature along y |
| 3 | 68.10 | 0.92 | two curved nodal lines parallel to the scanner y axis: bending with curvature along x |
| 4, 5 | 71.96, 80.47 | 0.59, 0.44 | strongly complex (close or coupled modes); the shapes are not reliable |
| 6–10 | 116.9–213.2 | 0.86–0.95 | higher-order patterns |

**Missed-low-mode check** (raw PSV H1 FRFs, 289 points, 0.3125–500 Hz; experimental data only; files
`plate_frf_peaks.json`, `plate_ods.json`, `fig_plate_frf.png`, `fig_plate_ods.png`). This answers question 6 of §7 as
far as the data allow.

- The point-averaged |H1| has two strong peaks below the first PolyMAX mode: **9.06 Hz** and **15.6 Hz**. The 15.6 Hz
  peak is as high as the 33.45 Hz peak.
- The operating deflection shape at **9.06 Hz** is a **rigid translation**: 94 % of the shape is a plane, essentially
  constant. Mean coherence 0.75.
- At **15.6 Hz** the out-of-plane ODS is **rigid-body-like rocking**: 81 % is approximated by a plane tilted
  mainly along scanner x, with negligible twist. Such a vertical-displacement tilt corresponds primarily to rotation
  about the **in-plane y axis**, **not** the vertical z axis. Mean coherence 0.67; the full 3D rotation axis cannot
  be recovered from U3 alone.
- At 33.44 Hz the ODS is twist-like.
- **No additional elastic mode was identified between 0.3 Hz and 33.45 Hz in the analysed PolyMAX and FRF data.**
  The low peaks have rigid-body-like ODS patterns consistent with suspension/attachment motion, not independently
  identified modal poles. This does not prove that a weaker elastic mode cannot have been missed.
- Their frequencies are **27 % and 47 % of the first elastic frequency**. That is not a negligible suspension or
  attachment stiffness. **The free-free idealisation of mode 1 is therefore not verified**: its effect on 33.45 Hz is
  UNKNOWN without the shaker attachment and suspension records.

These are operating deflection shapes at single frequency lines, not identified modes.

**Consequences.**

- **Experimental mode 1 (33.45 Hz) has a twist-dominated measured U3 pattern.** PolyMAX has 96 % xy projection
  after removing the rigid plane and alternating quadrant signs. No lower elastic modal pole was identified in the
  available data, subject to the FRF/ODS limitations above.
- Every stored FE model's first elastic mode is the twist mode (Rayleigh consistency 2–5 % and the Abaqus
  screenshots). The squared ratio (33.45 / 19.07)² ≈ 3.08 therefore compares the same mode family. Three conditions of
  §5 remain unverified:
  - the test is close enough to free-free (rigid-body modes at 9.1 / 15.6 Hz, attachment unknown);
  - the modal-shape factor is comparable, given the orthotropy and the measured thickness variation;
  - the equivalent G12 assumes a homogeneous plate.

  The scaling therefore stays a **conditional illustration, not an experimental D66 or G12**.
- Modes 2 and 3 show distinct measured bending patterns at 55.25 and 68.10 Hz. The current near-square E1 = E2
  models predict different frequency groupings. This indicates **direction-dependent behaviour of the tested
  plate/fixture system**, potentially arising from laminate stiffness, nonuniform thickness (opposing side means
  0.816 / 0.926 mm), support/attachment, or modal classification. Neither pure material orthotropy nor one
  thickness profile is established by this observation alone.
- **The FE pairing is still not confirmed formally.** MAC needs the FE shapes (an Abaqus Python extraction of the
  ODB, which needs separate authorisation) and a registration that uses this reconstruction. The reconstruction
  itself relies on three deviations.
- **Consistent hypothesis, not a finding:** plain-weave fabric (E = 56 GPa, G12 = 5 GPa) rotated 45° to the edges
  would give G ≈ 27 GPa and E ≈ 17 GPa. A laminate mixing 0/90 and ±45 plies lies in between, which is close to the
  owner's manual fit `E30E26` (30.8 / 26.5 / 10 GPa). The weave direction relative to the edges cannot be read from
  the PSV frame (texture at about 2 mm per 6 px). **Updated in §10:** on the photographed surface the plain weave runs
  about 0/90° to the edges, so an outer ±45° ply on that face is excluded; the hidden face and the interior remain
  UNKNOWN.

**Open questions for the owner:**

1. Row 4 is the left edge (seen from the shaker side)?
2. ~~Do the fibres / weave run parallel to the edges or at 45°?~~ The photographed face is 0/90 (§10.1). Still open:
   the other face, and the number of plies.
3. Was 301 or 300 mm horizontal in the test?
4. Where was the shaker attached (point, stinger), and how was the plate suspended (cords, points)? The rigid-body
   modes at 9.1 and 15.6 Hz depend on it.

## 10. Addendum (2026-10-21): plate photographs and an updated assessment of the twist gap

### 10.1 Photographs: SUPERVISOR's visual assessment (copies PENDING)

The owner provided two photographs of the plate: the surface and the edge. The SUPERVISOR's visual assessment,
recorded as a HUMAN statement:

- the outer fabric is **plain weave**;
- the visible tow directions are approximately **parallel to the edges (0°/90°)**;
- no ±45° orientation is visible on that surface;
- the number of plies and the internal layup remain **UNKNOWN**;
- the local thickness is not to be determined from a photograph.

**The photograph files have not reached this session.** On 2026-10-21 (R4) the archive
`M11_plate_photos_verified.zip` was absent from `runs\m11_carbon_plate\owner_records\incoming` (the folder does
not exist) and from the other searched locations. No verified copy and no SHA-256 exist; the status is **PENDING**. When the files
arrive they will be copied outside git with SHA-256, as for the measurement sheet. These photographs are supporting
HUMAN material, not proof of the laminate structure. The information is not transferred to other specimens without
confirmation that the material is common.

### 10.2 The twist gap, 33.45 Hz (test) against 19.07 Hz (FE): corrected assessment (R4)

The first version of this subsection (commit `1c42e84`) is **withdrawn** on two points:

- its corner-spring estimate put the 1-D translation stiffness into a corner without the coupled rigid-body motion;
- its hidden-45°-ply numbers compared D66 ratios with the frequency gap, ignoring bending-extension coupling.

All numbers below are parametric estimates in `runs\m11_carbon_plate\twist_causes_r4.json` (4-DOF Ritz and
laminate A–B–D). Nothing is fitted, no FE solve was run, and no constant is identified.

**A. Experimentally established (from the copies)**

- Mode 1 of `Polymax_bravo` is 33.4491 Hz with a twist pattern: 96 % xy projection after removing the rigid plane;
  its own rigid-plane content on the grid is 0.016.
- The averaged PSV FRFs have two lower peaks, 9.06 Hz and 15.6 Hz. Their operating deflection shapes are a uniform
  translation and a tilt about the in-plane y axis. **They are ODS at single frequency lines, not identified modes.**
- The measured mass is 118.37 g and the plan 301 × 300 mm.
- The thickness is known only at the edges: 20 readings, 0.71–0.94 mm, mean 0.876 mm. **The interior thickness is not
  measured.**
- The PSV frame shows elastic straps at all four plate corners and the shaker behind the plate. The attachment point
  and the strap / stinger stiffnesses are **not measured**.
- Photographs: the SUPERVISOR's visual assessment says the visible face is plain weave at about 0/90° (§10.1).

**B. Model assumptions used in the estimates**

- The plate is uniform: a rigid plane plus one twist shape (2x/a)(2y/b) (4-DOF Ritz).
- The free twist is 19.07 Hz, taken from the stored S4R model.
- Supports are vertical point springs.
- Laminate estimates use the TEMPLATE fabric constants E = 56 000 MPa, ν12 = 0.05, G12 = 5 000 MPa, with t = 0.875 mm
  and equal ply thicknesses.

**C. Hypotheses and what the estimates say about them**

| Hypothesis | Estimate (under B) | Status |
|---|---|---|
| **One** vertical attachment spring (e.g. the stinger) | Control: one corner spring of 384 N/m gives a non-zero rigid-subspace frequency of **23.98 Hz**, not 9.06 Hz; the 384 N/m (1-D translation) cannot be placed in a corner. To raise the coupled twist to 33.45 Hz a single spring needs 257.1 N/m at a corner, 507.5 N/m at (0.4a, 0.4b) or 1568.5 N/m at (a/4, b/4). The resulting twist-like mode would then contain 31%–70% rigid-plane content, against 1.6% measured | **not supported as the main cause** by the measured mode-1 shape; a smaller contribution is not excluded |
| **Four equal corner supports** (the straps visible in the frame) | Total 383.8 N/m gives a translation at 9.06 Hz, rocking about both axes at 15.697 Hz (ratio √3 = 1.7322; the observed ODS ratio is 1.7241), no rigid content in the twist by symmetry, and a twist at 33.21 Hz | **open hypothesis, consistent with the two ODS frequencies.** Not established: the ODS are not identified modes; the strap stiffness and geometry, the stinger and the effect on the other modes are unchecked. **33.21 Hz is not a bound or a proof** |
| A 45° ply on the hidden face (unsymmetric laminate) | With the template constants the B-coupling reduces D66 to D66* = D66 − (B A⁻¹ B)66: ×2.055 for [0/90 \| 45] and ×1.945 for [0,0,0,45], i.e. a Rayleigh twist-frequency ratio of 1.433 / 1.395 against the required 1.754. At exactly 45° a balanced fabric gives D16 = D26 = 0; off-45° plies give D16, D26 ≠ 0 (e.g. ±0.3574 D66 at 30°) | **parametric only.** Under the template constants it does **not** reach the gap. With the real (unknown) ply constants, thicknesses and angles no numerical claim is made. The earlier ×2.9–3.2 D66 figures are withdrawn as frequency evidence |
| Interior 45° plies (symmetric) | D66 ×1.16–1.542, i.e. a twist-frequency ratio of 1.077–1.242 | insufficient alone under B |
| Plain-weave G12 above the 5 000 MPa template | not measured; the literature range is a few GPa | a partial contribution is possible; not quantified |
| **Unknown interior thickness** | With the mass fixed (ρh known on average) the twist frequency scales with √⟨E t³⟩. If the interior were 0.95 or 1.0 mm instead of the 0.876 mm edge mean, the frequency ratio would be ×1.129 or ×1.22; if 0.80 mm, ×0.873 | **not excluded**: the edge mean is not the plate's thickness distribution (the nominal value is 1 mm) |
| Mode identity, lower missed mode | experimental mode 1 is twist-like; no lower elastic mode was identified (not a proof) | consistent; not a cause |

**Conclusion (R4).**

- No single cause is established.
- A single point attachment as the main cause is not supported by the measured mode-1 shape.
- Three explanations remain open and cannot be ranked with the data in hand:
  - symmetric four-corner support stiffness, consistent with the two ODS frequencies;
  - an unknown interior thickness;
  - the unknown laminate and fabric constants, including asymmetric or off-axis plies.
- The twist scaling of §5 stays a conditional illustration. No E1, E2 or G12 is inferred.

**Discriminating data** (none needs Abaqus):

- strap positions, lengths and tension, and the stinger point, with photographs;
- interior thickness at several points (e.g. a 3 × 3 grid, by micrometer through an access point or by ultrasonic
  gauge);
- the other face and the ply count;
- a repeat test with softer suspension or a different support (e.g. impact excitation on soft cords at the nodal
  lines of the twist mode).

Comparing the twist frequency between two support conditions separates the support effect from the material and
thickness effects.

## 11. What did not change

- SPEC, DECISIONS, EVIDENCE, registrations, criteria and gates.
- Every original and every earlier copy.
- Branch `analysis/m10-sp10-registration-prep` and PR #94.
- No FE solve, no Abaqus Python, no Auto-ID or LM, no MAC, no material change.
- M8 original gate `NOT_MET`; production calibration BLOCKED / NOT_AUTHORISED; D-077 NO_GLOBAL_PARAMETER_VALUE.
