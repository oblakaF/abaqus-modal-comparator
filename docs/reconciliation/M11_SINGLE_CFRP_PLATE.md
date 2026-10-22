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

**Update R5:** the archive arrived later in `runs\m11_carbon_plate\owner_records\` (not `incoming\`). Both
photographs were verified against its SHA-256 manifest; see §11.1. (In R4 the archive was absent; that status is
superseded.) When the files
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
| **One** vertical attachment spring at a corner (hypothetical; R6.1: the shaker was **not** at a corner, §13.3) | Control: one corner spring of 384 N/m gives a non-zero rigid-subspace frequency of **23.98 Hz**, not 9.06 Hz; the 384 N/m (1-D translation) cannot be placed in a corner. To raise the coupled twist to 33.45 Hz a single spring needs 257.1 N/m at a corner, 507.5 N/m at (0.4a, 0.4b) or 1568.5 N/m at (a/4, b/4). The resulting twist-like mode would then contain 31%–70% rigid-plane content, against 1.6% measured | **not supported as the main cause** by the measured mode-1 shape; a smaller contribution is not excluded |
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

## 11. R5 (2026-10-21): photographs, rocking directions and the support-model shape check

### 11.1 Photographs (HUMAN supporting evidence, verified copies outside git)

The owner placed the archive `M11_plate_photos_verified.zip` directly in `runs\m11_carbon_plate\owner_records\`
(not in `incoming\`). Archive SHA-256 `070d7ccda2eaea3d…`. It was extracted into a new folder
`owner_records\photos_20261021`, and both JPEGs match the archive's manifest:

| File | Manifest description | SHA-256 |
|---|---|---|
| `plate_visible_surface.jpeg` | visible face, plain weave | `4730cd23815f6000…` |
| `plate_edge_detail.jpeg` | edge close-up | `5f7ce39f3b8cccf9…` |

The record is `owner_records\photos_20261021_verification.json`. The photographs are not committed.

**Confirmed visually, and only this:**

- the photographed face is **plain weave**;
- its tows run approximately **parallel to the plate edges** (0°/90°); no ±45° pattern is visible on that face;
- the edge photograph shows the plate edge but is out of focus: **plies are not resolvable**, as its manifest also says;
- handwritten marks (numerals) near the edges are visible on the photographed face; they are not interpreted here.

**Not established by the photographs:**

- whether the photographed face is the one the scanner measured;
- the back face;
- the number of plies and the layup;
- any thickness.

### 11.2 Rocking directions near 15.6 Hz

This check uses the existing FRF / ODS only (`plate_rocking_band.json`, `fig_plate_rocking_band.png`): per frequency
line, the phase-aligned ODS, its least-squares plane and the direction of the plane's tilt.

- 9.4–13.4 Hz: the ODS stays rigid (plane share 0.93–0.99), with a stable
  tilt direction of about 130°. The uniform-to-tilt ratio falls from 2.742 to
  0.325, a smooth transition between the translation and the tilt response.
- 14.06–14.69 Hz: the plane share is 0.10–0.35 and the coherence
  0.34–0.39. These lines are **not interpretable**.
- 15.0–16.25 Hz: the tilt direction **rotates line by line**:

  | Hz | Tilt direction (gradient angle) | Coherence |
  |---|---|---|
  | 15.00 | 150.1° | 0.594 |
  | 15.31 | 160.0° | 0.656 |
  | 15.625 | 18.3° (mainly along scanner x) | 0.668 |
  | 15.94 | 76.0° (mainly along scanner y) | 0.767 |
  | 16.25 | 102.2° | 0.816 |

  It then settles at 110–118° up to 18.75 Hz.
- **Result:**
  - the data *suggest* two close rocking responses with different tilt axes, about 0.3 Hz apart near 15.6–15.9 Hz;
  - they **cannot separate or identify two rocking modes**: the frequency resolution is 0.3125 Hz, there is one
    reference (one shaker), the coherence is 0.67–0.77, and these are ODS, not poles;
  - the band SVD (second singular value 0.6584 of the first) is only
    indicative, because it mixes response shape with modal rank.

### 11.3 Shape check of the four-equal-corner-support model

The model predicts (§10.2): a pure uniform translation at 9.06 Hz, a degenerate rocking pair about both axes at
15.70 Hz, and a twist with no rigid content at about 33.2 Hz.

| Prediction | Observation (ODS / PolyMAX) | Agreement |
|---|---|---|
| pure translation, zero tilt, at the lowest rigid frequency | plane share 0.937, uniform-to-tilt about 5.027:1 at 9.06 Hz; the tilt fraction grows towards 13 Hz | **partial**: mostly uniform, but a residual tilt shows the supports are not equal or symmetric (e.g. the stinger), or a tilt response is overlapping |
| degenerate rocking about x and y, ratio √3 to the translation | tilt about one axis at 15.625 Hz and about the other at 15.94 Hz (§11.2); 15.625 / 9.0625 = 1.724 | **consistent, not confirmed**: the ODS are not modes, and the pair is not separable |
| twist without rigid content | rigid-plane share 1.6 % in PolyMAX mode 1; xy share 0.95–0.99 over 31–35 Hz | **consistent, but not discriminating**: a stiffer laminate in a truly free plate gives the same pure twist |
| other elastic modes shifted according to their corner amplitude | not checkable without FE mode shapes (no ODB extraction) | **unchecked** |

**Verdict: the four-corner model is not contradicted by the observed ODS, but it is not confirmed.**

- The frequency coincidence (√3) and the qualitative shapes are its only support.
- The residual tilt at 9.06 Hz departs from the equal-support form.
- The twist shape cannot distinguish support stiffness from material stiffness.
- The strap tension, the strap lengths and angles, and the stinger stiffness and position are unmeasured.

The §10.2 conclusion stands: no cause of the twist gap is established.

### 11.4 Data needed for a diagnostic physical registration and MAC of the plate

These follow the CORE-E2E-C evidence requirements (`docs/gui/GUIDED_PHYSICAL_REGISTRATION.md`). Nothing below
relaxes a check.

**FE side (HUMAN gate):**

1. The choice of the FE model to compare (`CFRP_S4R_0875_FreeFree`, the wedge, the C3D8I or `E30E26`), and an
   **authorised Abaqus Python extraction** of its ODB: node geometry (`geometry.csv`) and mode shapes. This gives the
   FE geometry identity the evidence must name.
2. For the shell models, every node lies at z = 0. The measured-surface rule (`max_z` / `min_z`) and the
   one-point-per-node mapping must be checked for a shell mid-surface before use. The 3 mm mesh against the
   13–18 mm scan pitch is not expected to be a problem.

**Physical orientation (owner statements; a convention is not evidence):**

3. Which face faced the scanner on 2026-10-16. Is it the photographed face with the numerals?
4. Which physical edge was horizontal: the 301 mm or the 300 mm edge? The frame aspect cannot decide (0.996 against
   1.003).
5. A corner reference visible in the stored PSV frame, or a corner-A statement linking a frame corner to a marked
   physical corner. This must also fix how the FE X / Y axes (301 / 300) and their signs map onto the frame.
6. Confirmation of the thickness-row mapping (row 4 = left edge seen from the shaker side).

**Scan calibration:**

7. SUPERVISOR acceptance of the three reconstruction deviations of §9 (anomalous stored rectangle, wider edge
   search, inverted bottom edge), or an independent measurement of the scan-to-edge offsets.
8. The instrument and resolution of the plan dimensions 301 × 300.

**Experimental data for MAC:**

9. Use of the set `Polymax_bravo`: 289 points, measured DOF U3. Modes 4 and 5 (MPC 0.59 / 0.44) are strongly
   complex and need a marking that limits their MAC interpretation.
10. The PolyMAX damping values are not read by the comparator's reader; LMS damping is in Excel.

**Setup, for the frequency comparison (not for MAC):**

11. The suspension: strap positions, lengths and tension. The shaker / stinger: point, stiffness and armature mass.
    Photographs of the test setup.

Until items 1, 3–5 and 7 exist, the comparison stays **FREQUENCY_DIAGNOSTIC** plus experimental mode types.

## 12. R6 (2026-10-21): authorised FE extraction from a copy of `CFRP_S4R_0875_FreeFree.odb`

**Authorisation and scope.** HUMAN / SUPERVISOR allowed **one** diagnostic Abaqus Python run, for extraction only. No
FE solve, no job, no model, INP or CAE change, no Auto-ID / LM and no change of material constants were made. No
original was opened: the run used the level-C working copy below.

### 12.1 Three-level protection and the run

| Level | File | SHA-256 |
|---|---|---|
| A, original | `C:\temp\CFRP_S4R_0875_FreeFree.odb` | **not accessed** |
| B, verified copy (V3) | `external_models\v3_20261021\Plate\temp_root\CFRP_S4R_0875_FreeFree.odb` (from `COPY_MANIFEST_V3.json`) | `7daeb7e35adf6bd6…` before, `7daeb7e35adf6bd6…` after: equal to the expected value |
| C, working copy | `runs\m11_carbon_plate\odb_extraction_r6\input\CFRP_S4R_0875_FreeFree.odb` | `7daeb7e35adf6bd6…` before, `7daeb7e35adf6bd6…` after: unchanged |

**The run** (`logs\abaqus_python_run.log`, `logs\run_meta.txt`):

- command `abaqus python scripts\extract_odb.py --odb input\… --output output --start-mode 1 --end-mode 20`, with
  the working directory and TEMP / TMP set to `logs\`;
- the script is the repository's existing extractor `abaqus_scripts/extract_odb.py`, unchanged (SHA-256
  `039aa067adeac83e…`). It opens the ODB with `openOdb(path, readOnly=True)` and writes only to
  `--output`;
- start=2026-10-21T18:52:45.3588390+08:00, end=2026-10-21T18:52:51.8809042+08:00, exit=0: one run, with no retry.

**Checks after the run:**

- all V3 and Excel copies are equal to their manifests;
- no unlisted file appeared in the V3 folder;
- the workspace contains no solver artefact (`.sta`, `.msg`, `.dat`, `.lck`, …): no FE solve took place.

The created files are listed in `logs\postflight.json`. The post-run analysis files (`output_analysis\`: the shell diagnostic and the candidates) were
created afterwards with ordinary Python from the output and the V3 INP text, without Abaqus. All copies were
re-verified unchanged after them.

**Output, in the comparator's extraction format 2 (outside git):**

- `output\geometry.csv`: instance `CFRP_301X300_SHELL-1`, 10201 nodes, X 0–301,
  Y 0–300, Z 0 (mid-surface);
- `output\mode_0001.csv` … `mode_0020.csv`: U1 / U2 / U3 per node, real and imaginary parts;
- `output\manifest.json`: step `Modal_FreeFree_plate`, modes 1–20.

It can be loaded as an extraction `manifest.json`.

**Frequencies against the stored `.dat` (V3 copy):** elastic modes 7–20 are identical, maximum difference
0.0 Hz. The extractor reports the rigid modes 1 and 2 as "1 Hz" and "2 Hz": these are
mode numbers parsed from the frame description because the `.dat` frequency is 0. This is a known parser quirk for
zero-frequency frames; it was noted and not fixed, and it affects no elastic mode.

| Mode | ODB (manifest), Hz | `.dat`, Hz |
|---|---|---|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 0.000218304 | 0.000218304 |
| 4 | 0.000331046 | 0.000331046 |
| 5 | 0.00191413 | 0.00191413 |
| 6 | 0.00208984 | 0.00208984 |
| 7 | 19.072 | 19.072 |
| 8 | 59.874 | 59.874 |
| 9 | 62.009 | 62.009 |
| 10 | 71.85 | 71.85 |
| 11 | 72.19 | 72.19 |
| 12 | 116.58 | 116.58 |
| 13 | 167.49 | 167.49 |
| 14 | 168.61 | 168.61 |
| 15 | 174.8 | 174.8 |
| 16 | 179.9 | 179.9 |
| 17 | 213.2 | 213.2 |
| 18 | 213.95 | 213.95 |
| 19 | 295.78 | 295.78 |
| 20 | 327.9 | 327.9 |

### 12.2 Shell measured-surface diagnostic (no rule changed)

The existing rule (`physical_registration.FEGeometry.surface_node_ids`) selects the nodes of the instance at
z = max(z) (`max_z`) or z = min(z) (`min_z`), within 1·10⁻⁴ mm.

- All 10201 shell nodes lie at z = 0. **`max_z` and `min_z` select the same 10201 nodes,
  with an identical surface identity** (`02fb9f9925aab3ce…`), checked with the existing
  `guided_registration.geometry_file_surface_identity`.
- The S4R normals from the INP connectivity: 10000 of
  10000 elements point to **+Z**.
- **Consequence:** for this shell, `measured_surface.side` cannot express which face was measured. The face is
  expressed only by the Z sign in `experimental_axes_in_fe`: +Z if the scanner looked at the side of the +Z shell
  normal, −Z otherwise, together with the matching in-plane mapping (determinant +1). The current code does **not**
  check that `side` agrees with that sign. For a solid this is implicit; for a mid-surface shell any `side` label
  passes.
- **Diagnostic blocker (to fix separately, not changed here):** for an instance whose z-range is within the surface
  tolerance, the guided path should record `side: mid_surface` and require an explicit statement of the measured face
  relative to the shell normal (positive or negative side). It should refuse an `experimental_axes_in_fe` Z sign that
  contradicts that statement.
- Mapping the points to mid-surface nodes is geometrically sound: U3 of the mid-surface is the out-of-plane
  displacement the vibrometer measures, ignoring thickness offset. The 3 mm mesh gives every point its own node.

### 12.3 Geometric candidates of the 289-point grid on the FE mid-surface (not confirmed)

This uses the reconstructed scan window of §9, which needs SUPERVISOR acceptance of its three deviations. The panel
frame P (scanner view) is mapped onto the FE plan (301 along FE X, 300 along FE Y). Only the candidates whose
rectangle coincides with the FE plan are admissible. No MAC and no frequency were used.

| Candidate (horizontal edge in the frame, face, rotation) | Experimental axes in FE | Nearest node, median / max, mm | Distinct nodes / points |
|---|---|---|---|
| H301 +Z rot0 | +X +Y +Z | 1.246 / 2.059 | 289 / 289 |
| H301 +Z rot180 | -X -Y +Z | 1.246 / 2.059 | 289 / 289 |
| H301 -Z rot0 | +X -Y -Z | 1.246 / 2.059 | 289 / 289 |
| H301 -Z rot180 | -X +Y -Z | 1.246 / 2.059 | 289 / 289 |
| H300 +Z rot90 | +Y -X +Z | 1.25 / 2.059 | 289 / 289 |
| H300 +Z rot270 | -Y +X +Z | 1.25 / 2.059 | 289 / 289 |
| H300 -Z rot90 | +Y +X -Z | 1.25 / 2.059 | 289 / 289 |
| H300 -Z rot270 | -Y -X -Z | 1.25 / 2.059 | 289 / 289 |

**Geometry does not discriminate.** Every candidate puts each point on its own node within 2.06 mm.

For this FE model (homogeneous, E1 = E2, plan 301 × 300) the four candidates within each group (H301 or H300) are
**symmetry-equivalent**: 180° rotation and mirrors about the centre lines map the model onto itself, so its modes map
onto ±themselves. The physically relevant open choices are therefore:

1. which physical edge (301 or 300 mm) lay along scanner x;
2. the face convention, needed for traceability.

This is an observation about the model's symmetry, not a selection. **Orientation is never chosen by MAC.**

### 12.4 Status and what is still needed

**Status: `FE_EXTRACTION_READY / PHYSICAL_REGISTRATION_PENDING`.** No registration was built or accepted, and nothing
is governed evidence.

**Physical registration may proceed only after:**

1. the owner states which face faced the scanner on 2026-10-16, relative to a physical mark (e.g. the photographed
   face with the numerals);
2. the owner states which physical edge (301 or 300 mm) was horizontal in the test, and a corner reference fixing the
   signs; for the CAE model, also how the sketch's X (301) relates to the physical plate, if it was built with
   intent;
3. SUPERVISOR accepts the three reconstruction deviations of §9, or an independent scan-to-edge measurement exists;
4. the shell-side rule of §12.2 is either fixed in a separate change, or the evidence states the face explicitly
   through the Z sign, with that limitation recorded.

**MAC interpretation caveats** for later:

- modes 4 and 5 are strongly complex (MPC 0.59 / 0.44);
- the experiment shows split bending modes (55.25 / 68.10 Hz), while the E1 = E2 model has near-degenerate pairs, so
  MAC of near-degenerate FE pairs needs subspace treatment;
- the free-free model does not represent the suspension (§10.2).

## 13. R6.1 (2026-10-21): owner orientation and shaker evidence; preparation for a diagnostic registration

Part B of the combined SUPERVISOR task R7 + M11 R6.1. These are scientific documents and evidence only: no code
change, no Abaqus, no extraction, no MAC and no fitting. No original was opened.

### 13.1 HUMAN evidence (verified copies outside git)

| Archive | Archive SHA-256 | Content | Manifest check |
|---|---|---|---|
| `M11_R6_owner_orientation_evidence.zip` | `07c4d59b42c6ee1f…` | `plate_orientation_shaker_view.png` (`40db5103f28f1ec0…`) + `ORIENTATION_MANIFEST.json` | match |
| `M11_shaker_location_owner_evidence.zip` | `1a248d388d71cef8…` | `owner_shaker_location_schema.png` (`e8a569459d3b2325…`) + `MANIFEST_SHA256.json` | match |

The archives were extracted to `owner_records\orientation_r61` and `owner_records\shaker_location_r61`; the record is
`owner_records\owner_archives_r61_verification.json`.

**Owner statements**, recorded as HUMAN supporting evidence, not governed and not a registration:

- The plate is 301 × 300 mm. **Abaqus X corresponds to the 301 mm dimension and Y to the 300 mm dimension.**
- The real orientation of the plate in the test is reproduced in the Abaqus model.
- The sketches are drawn **from the shaker side, which is the side with the handwritten marks**.
- Thickness rows in that view: **1 = top, 2 = right, 3 = bottom, 4 = left.** The last item is now confirmed by the
  sketch; earlier the owner's text read "3 left".
- The shaker was **not at a corner**. Its attachment (red circle, approximate) is near the bottom edge, left of the
  midline, in the shaker-side view.
- The orange dot near the bottom-left corner has an **unconfirmed role**. It is not taken as the Abaqus origin and
  not as corner A.

The orientation sketch also shows the scanner camera and the shaker on opposite sides of the plate, schematically.

### 13.2 Orientation: closed and open questions

**Three frames are kept separate:**

- (a) the shaker-side view of the owner's sketches;
- (b) the scanner (PSV camera) view;
- (c) the positive side of the S4R shell normal (+Z for all 10 000 elements, from the INP copy).

**FE geometry (R6 extraction):**

- X 0–301 mm and Y 0–300 mm; Z = 0;
- corners (0, 0), (301, 0), (301, 300) and (0, 300); positive axes +X along the 301 mm edge and +Y along the 300 mm
  edge;
- FE geometry identity `02fb9f9925aab3ce…` (10 201 nodes, `CFRP_301X300_SHELL-1`).

| Question | Status |
|---|---|
| Which plate dimension lies along FE X / Y | **closed (HUMAN):** X = 301 mm, Y = 300 mm |
| Which edge was horizontal in the test | **closed (HUMAN):** 301 mm horizontal in the shaker-side view, hence also in the scanner view (opposite views of a hanging plate share the horizontal). The 300-mm-horizontal candidate group of §12.3 is excluded; the reconstruction `W301xH300` applies |
| Thickness row ↔ edge | **closed (HUMAN):** shaker view 1 top, 2 right, 3 bottom, 4 left. In the scanner view left and right swap: the thin side (row 2, mean 0.816 mm) is on the scanner's left, the thick side (row 4, 0.926 mm) on its right |
| Which face the scanner saw | **supported, not established.** In the stored PSV frame (scanner view) the plate occludes the shaker body visible at the lower right, so the scanner faced the side opposite the shaker. With the owner's statement that the marks are on the shaker side, the scanner saw the unmarked face. Owner confirmation against the recorded setup is still requested |
| FE axis signs and origin relative to a physical corner | **open.** The 2-D sketch does not pin them; corner A is not assigned; the orange dot is not used |
| FE +Z (shell normal) relative to a physical face | **open.** "Abaqus reproduces the experiment" does not fix which physical face is +Z |

**Consequence:** of the 8 geometric candidates of §12.3, the four with 300 mm horizontal are excluded. Four remain,
with experimental axes in FE:

- [+X, +Y, +Z]
- [−X, −Y, +Z]
- [+X, −Y, −Z]
- [−X, +Y, −Z]

All four have determinant +1. They are symmetry-equivalent for this homogeneous E1 = E2 model, but they are **not**
physically chosen. **No choice is made by MAC.**

### 13.3 Shaker, suspension and marks: kept separate

1. **Four corner straps (suspension).** Visible in the PSV frame. The "four equal corner supports" model (§10.2,
   §11.3) remains an **unconfirmed hypothesis**: the strap stiffness, length and tension are unmeasured.
2. **Shaker stinger.** Off-corner, near the bottom edge, left of the midline in the shaker view (right of it in the
   scanner view, consistent with the shaker body seen at the lower right behind the plate in the PSV frame). The
   position is approximate; the stiffness and armature mass are unmeasured.
   - **The single-corner-spring scenarios of §10.2 do not represent the shaker and are not a model of this
     experiment.** They remain only as parametric statements about a hypothetical corner spring.
   - At an off-corner bottom-edge point the twist shape has a non-zero but smaller amplitude than at a corner. The
     stinger's effect on the 33.45 Hz twist is **not quantified**.
3. **Physical marks.** Handwritten numerals near the edges on the shaker-side face (photograph, §11.1); the orange dot
   in the sketch, role unconfirmed.

**The rigid-body / ODS frequencies 9.06 / 15.6 Hz and the twist at 33.45 Hz are not evidence that any support model
is correct.** No E1, E2 or G12 is derived from them.

### 13.4 The three scan-reconstruction deviations (§9): justification for a SUPERVISOR decision

They are **not accepted**, and no normative threshold is changed retroactively. All numbers are from
`plate_reconstruction_W301xH300.json`.

**1. Stored full-frame rectangle**

| Aspect | Content |
|---|---|
| Observation | the `.svd` stores u −0.2222…1.5556, v **−2.4667…1.0**; every other stored session (SP-02, SP-10 ×2, SP-13) has the same u range with v 0…1 |
| Why the standard failed | with the stored v range the 289 MeasPoints map to image rows 795–1039 (244 px), while the plate occupies about 890 px. The grid would be compressed about 3.5 times vertically and partly lie below the plate edge (row 960), which is geometrically impossible |
| Why the change is justified | the frame is 1920 × 1080 as in the other sessions, and u is identical. v 0…1 maps the points to rows 92–939, inside the plate. The scanner-angle isotropy is 0.972, against SP-02 0.973 and SP-13 0.966 |
| Independent control | MeasPoints ↔ UNV parser residual max 1.1e-03 (independent of the rectangle); camera-grid model residual 1.29 / 3.23 mm (median / max), better than the accepted SP-02 2.83 / 5.93 and SP-13 2.68 / 5.72 |
| Remaining uncertainty | why the PSV software stored that rectangle is unknown. A different crop or zoom would shift points against the edges; only the small residual argues against it |

**2. Edge search window**

| Aspect | Content |
|---|---|
| Observation | the scan grid ends about 167 px (56 mm) from the left plate edge |
| Why the standard failed | `EDGE_SEARCH_WINDOW_PX` = 150 does not reach the edge ("too few edge samples") |
| Why the change is justified | only the search range grows (220 px). The edge criterion (step, gradient, clustering) is unchanged |
| Independent control | left edge RMS 0.289 px, 108/120 samples, angle -0.39° (right edge 0.18°); plate 892.2 × 892.6 px, i.e. 301 / 300 within 0.4 % |
| Remaining uncertainty | a wider band could catch another structure; the edge-sample cluster and the visual overlay show the plate edge |

**3. Bottom-edge polarity**

| Aspect | Content |
|---|---|
| Observation | behind the bottom edge lie the dark shaker and fixture. The plate is about 22 grey levels, the background about 10: a step of the opposite sign to the detector's assumption |
| Why the standard failed | with constants unchanged the fit took other structures: RMS 16.9 px, 29 samples, bottom gap −17 mm |
| Why the change is justified | the physical edge exists as a dark-to-darker step. On the inverted image with a step threshold of 8 and a minimum gradient of 2, the same detector finds it |
| Independent control | bottom edge RMS 0.213 px, 82/108 samples, angle -0.004° (top edge 0.25°); plate aspect consistent with 301 × 300; residual as above |
| Remaining uncertainty | low contrast, so a shadow could bias the line by a pixel or two (about 0.3–0.7 mm). The threshold is specific to this frame |

### 13.5 Evidence draft for a future diagnostic registration

The draft is `runs\m11_carbon_plate\evidence_r61\evidence_DRAFT_plate_r61.json` (`auto-id/guided-physical-evidence/v1`).

**Filled:**

- FE instance `CFRP_301X300_SHELL-1` and FE geometry identity `02fb9f9925aab3ce…`;
- experimental source `300by300_plate_only_1mm_261016_POLYMAX.unv` (SHA-256 `117c893bafbbeba2…`), set
  `polymax-bravo`, 289 points, U3;
- scan window 215.42 × 285.20 mm, with provenance naming the
  three unaccepted deviations;
- the X / Y dimensions and the HUMAN orientation statements, the marked face and the shaker location.

**Explicitly empty:**

- the scanned face (`side`), the axis signs (`experimental_axes_in_fe`) and the orientation reference;
- the panel-edge offsets and the uncertainty.

The existing parser **refuses** the draft (`measured_surface.side` must be `max_z` / `min_z`). No registration was
built and no MAC was computed.

### 13.6 Remaining obstacles before a diagnostic registration and MAC

| # | Obstacle | Who / what closes it |
|---|---|---|
| 1 | Scanned face relative to the marked face, confirmed against the recorded setup (the PSV frame supports "unmarked face") | owner |
| 2 | FE axis signs and origin relative to a physical corner (corner reference; corner A not assigned) | owner, with a marked photograph |
| 3 | FE +Z (shell normal) relative to a physical face | owner statement on the CAE model, or the R7 shell-face design |
| 4 | The shell-face evidence field (`side` cannot name the face of an S4R mid-surface) | SUPERVISOR decision on the R7 design (governed passport schema) |
| 5 | Acceptance or rejection of the three reconstruction deviations (§13.4), or independent scan-to-edge offsets | SUPERVISOR |
| 6 | Instrument and resolution of the plan dimensions 301 × 300 | owner |
| 7 | Zero-frequency rigid modes 1–2 of the R6 package carry false 1 Hz / 2 Hz | R7 loader (review) refuses them; the R6 package is not modified |
| 8 | MAC caveats: complex modes 4 / 5; split experimental bending vs near-degenerate FE pairs; no support in the FE model | to be handled in the MAC step |

**Status: `FE_EXTRACTION_READY / PHYSICAL_REGISTRATION_PENDING`** (unchanged).

## 14. R6.2 (2026-10-22): final physical orientation scheme (preparation; nothing registered)

Derived materials only, from the verified V3 copies, the R6 extraction, the HUMAN records of §8, §11 and §13, and the
PSV frame extracted earlier from the V3 `.svd` copy. No Abaqus, extraction, MAC or fitting was used, and orientation
was not chosen from shapes or frequencies. The figures and the owner's question sheet were made in
`runs\m11_carbon_plate\r62\`.

### 14.0 Published figures (R6.2a)

> **Diagnostic reconstruction only.** These pictures illustrate the candidates and the open questions. They are
> **not** an approved physical registration, and none of the pictures A–D is selected.

Copies, unchanged byte for byte, are in [`figures/m11_r62/`](figures/m11_r62/):

**Figure 14.1 — the plate seen from the shaker side** (the marked face; edges 1 top, 2 right, 3 bottom, 4 left;
shaker position approximate).

[![The plate seen from the shaker side](figures/m11_r62/fig_r62_view_shaker.png)](figures/m11_r62/fig_r62_view_shaker.png)

**Figure 14.2 — the four possible orientations A–D of the FE axes**, seen from the shaker side. Red = FE X, green =
FE Y, white circle = FE origin X = 0, Y = 0, centre text = FE +Z towards or away from the viewer. Same as the table in
§14.2.

R6.2b: the figure was re-rendered with the same arrows, origins and texts. Only the letters "X" and "Y" moved
22 mm into the plate, so they no longer cover the edge captions. The R6.2a version had SHA-256 `6454cefa768ae60e…`.

[![The four possible orientations A-D](figures/m11_r62/fig_r62_candidates.png)](figures/m11_r62/fig_r62_candidates.png)

**Figure 14.3 — the same plate seen from the scanner side, diagram only** (R6.2b, SUPERVISOR option (b)).

- Mirror of Figure 14.1: edges 2 and 4 swap.
- The 289 points, the scan window 215.4 × 285.2 mm and the gaps to the edges are as in §14.3.
- The caption "сторона БЕЗ меток (шейкер — за пластиной)" on the figure is the **hypothesis** of §14.4, which needs
  HUMAN confirmation. It is not an established fact.

[![The plate seen from the scanner side, diagram only](figures/m11_r62/fig_r62_view_scanner_diagram_only.png)](figures/m11_r62/fig_r62_view_scanner_diagram_only.png)

The file is a pure pixel crop of panel 2b of `fig_r62_view_scanner.png`:

- crop box x 930–1710, y 10–780 px;
- the pixels are identical to the source region;
- source SHA-256 `c48278fb8883aead768838fa0921b1e2f19d77bb57664dd0a83c32915ec18a44`.

The PSV camera photograph (panel 2a) is **not published**. It shows a person and equipment asset labels in the
laboratory background, and it remains only in `runs\m11_carbon_plate\r62\`.

The owner's question sheet: [`M11_R62_OWNER_QUESTIONS.md`](figures/m11_r62/M11_R62_OWNER_QUESTIONS.md).

Revised in R6.2b:

- it refers to the diagram-only scanner figure;
- the scanner on the far side, facing the unmarked face, is stated as a hypothesis that needs HUMAN confirmation;
- the owner is not asked to open the original Abaqus model; the answer rests on an existing model screenshot
  (axis triad and the X = 0, Y = 0 corner) or an authorised copy;
- the Abaqus standard view is stated not to establish the physical origin.

| File | SHA-256 |
|---|---|
| `fig_r62_view_shaker.png` | `7702df3925e5818c4eee1ad4750578741ecc9e7b0d1610e0ea280a970e45546b` |
| `fig_r62_view_scanner_diagram_only.png` | `81b2e26f7dcf99a78ded529be209186ebefdb96e83fba3c252a407e0999ae887` |
| `fig_r62_candidates.png` | `5efc9b8843480cd93715b049942e3f19e2c83f31160ed1adc5dd26efe87669f0` |
| `M11_R62_OWNER_QUESTIONS.md` | `8f9f2e91c246bbcdb655bab1e49794831ba9acfaf95d8424ae3f95472a71261e` |

### 14.1 The two views

| | Shaker-side view (owner's sketches) | Scanner-side view (PSV camera) |
|---|---|---|
| Face seen | the marked face (handwritten numerals) | the face without marks (supported, §14.4) |
| Edge labels | 1 top, 2 right, 3 bottom, 4 left | 1 top, **4 right**, 3 bottom, **2 left** (mirror) |
| Edge mean thickness, mm | 1: 0.880, 2: 0.816, 3: 0.882, 4: 0.926 | the same edges, mirrored left / right |
| Shaker (approximate) | bottom edge, left of the midline | bottom edge, right of the midline; the shaker disc in the frame is centred at about 0.77 of the plate width from the left |
| FE X / Y | X along the horizontal 301 mm edge, Y along the vertical 300 mm edge; **signs and origin unknown** | the same lines, mirrored |
| FE +Z (shell normal) | towards or away from the viewer: **unknown** | the opposite of the shaker view |

The FE geometry (R6): X 0–301 mm, Y 0–300 mm, Z = 0. The S4R normals are +Z for all 10 000 elements (V3 INP copy,
bound node for node to R6 in R7 R1).

### 14.2 The four remaining candidates

The experimental axes are those of the scanner view: x right, y up, z towards the scanner.

| Picture | Experimental axes in FE | det | Shaker view: FE axes and origin (physical corner) | FE +Z points | Scanned face vs normal | Scan-window offsets to the FE origin, mm | Confirmation needed |
|---|---|---|---|---|---|---|---|
| **A** | -X +Y -Z | +1 | X right, Y up; origin bottom-left (between edges 3 and 4) | towards the shaker (marked side) | negative_normal | x 29.19, y 7.02 | owner picks picture A |
| **B** | +X -Y -Z | +1 | X left, Y down; origin top-right (between edges 1 and 2) | towards the shaker (marked side) | negative_normal | x 56.4, y 7.78 | owner picks picture B |
| **C** | -X -Y +Z | +1 | X right, Y down; origin top-left (between edges 1 and 4) | towards the scanner (unmarked side) | positive_normal | x 29.19, y 7.78 | owner picks picture C |
| **D** | +X +Y +Z | +1 | X left, Y up; origin bottom-right (between edges 3 and 2) | towards the scanner (unmarked side) | positive_normal | x 56.4, y 7.02 | owner picks picture D |

**Notes:**

- The four candidates are symmetry-equivalent for this homogeneous E1 = E2 model (§12.3), but they are physically
  different. The choice is the owner's: one picture.
- The offsets follow from the scanner-view gaps (left 56.4, right 29.19, bottom
  7.02, top 7.78 mm). They inherit the status of the reconstruction (§14.3).
- Picture A corresponds to the Abaqus default front view (X right, Y up, Z towards the viewer) seen from the shaker
  side. That it would place the origin at the orange dot of the owner's sketch is **not** evidence, and A is not
  pre-selected.

### 14.3 The 289-point reconstruction against the plate geometry

- All 289 points lie inside the 301 × 300 mm plate.
- Scan window 215.42 × 285.2 mm. The gaps close the plate exactly:
  301.0 mm horizontally and 300.0 mm vertically.
- Camera-grid residual median 1.29 mm, max
  3.23 mm.
- Axis misalignment 0.87°; MeasPoints ↔ UNV parser residual
  1.1e-03.
- Under every remaining candidate each point lands on its own FE node within 2.06 mm (§12.3).
- **This is a diagnostic reconstruction.** The three deviations of §9 and §13.4 are **not** accepted as a physical
  calibration; that remains a SUPERVISOR decision.

### 14.4 Status of the information

| Status | Items |
|---|---|
| **Proven** (verified copies / data, or HUMAN-confirmed by the owner) | plate 301 × 300 mm and mass 118.37 g (HUMAN sheet); edge thickness (20 readings); FE geometry X 0–301, Y 0–300, Z 0 and S4R normals +Z (R6 + V3 INP, bound); FE X = 301 mm, Y = 300 mm (HUMAN); 301 mm horizontal in the test (HUMAN); edge labels 1–4 in the shaker view (HUMAN); marks on the shaker side (HUMAN); shaker not at a corner (HUMAN); experimental axes of the PSV grid (data); 289 points with DOF U3, set `polymax-bravo` (data) |
| **Supported by observation, not established** | the scanner saw the face opposite the shaker, i.e. the unmarked face (the shaker is occluded by the plate in the PSV frame and no numerals are visible); the shaker position right of centre in the scanner view (the disc behind the plate) |
| **Unknown** | the FE axis signs and origin relative to a physical corner, i.e. which of A–D; hence the FE +Z relative to a physical face; the reconstruction's three deviations (SUPERVISOR decision, not an owner question); the INP-to-ODB link (R7 R2: node match only) |

### 14.5 Minimum additional confirmations for an unambiguous diagnostic registration

From the owner:

1. **Which picture, A, B, C or D**, matches the Abaqus model when the real plate is seen from the shaker side.
   This fixes the axis signs, the origin corner (between two numbered edges) and the side of the shell normal.
2. **Yes / no:** the laser looked at the face without marks.

The face relative to the normal then follows from the table: `negative_normal` for A / B, `positive_normal` for C / D.

From the SUPERVISOR, not the owner:

3. A decision on the three reconstruction deviations, or an independent check of the scan-to-edge offsets.

**Not needed again:** plan, mass, thickness, weave photographs and shaker coordinates; they are already recorded, or not
needed for the registration.

After 1–3, the evidence draft `evidence_r61/evidence_DRAFT_plate_r61.json` can be completed:

- the axes from the table;
- `shell_measured_face` with normal +Z and the face from the table;
- the panel-edge offsets from the table.

It would then go through the R7 gate (PR #96, not merged). **The registration is not completed here.**

## 15. R6.3 (2026-10-22): FE coordinate frame and independent scan calibration audit

Read-only work on:

- the verified V3 copies: S4R INP, CAE journal `SInglePlate1mm.jnl`, replay files, job files `.com` / `.dat` / `.msg` /
  `.log`, `.svd`, POLYMAX `.unv`;
- the R6 extraction package.

No Abaqus, no new extraction, no FE solve, no MAC, no frequency fitting, no material estimation. Owner clarification
(SUPERVISOR, R6.3 §0): the owner recognised the physical edge layout in picture D but **does not know where the
Abaqus axes lie**. Picture D is therefore **not** selected, accepted or HUMAN-confirmed.

Derived files are in `runs\m11_carbon_plate\r63\`:

- `r63_fe_frame.json`
- `r63_candidate_edge_map.json`
- `r63_scan_sensitivity.json`
- `r63_scan_angle_check.json`
- the scripts in `tools\r63_*.py`

### 15.1 FE coordinate frame (established from the model files)

[![FE coordinate frame (schematic, not an Abaqus screenshot)](figures/m11_r63/fig_r63_fe_frame.png)](figures/m11_r63/fig_r63_fe_frame.png)

*Figure 15.1 — the FE coordinate frame.*

- It is a Matplotlib schematic drawn from the INP and R6 node coordinates, **not an Abaqus screenshot**.
- SHA-256 `51c0feb277b6d7e035ea5e73f269df1ee354cbd628ad9f54c830456b2c67c4be`.
- It contains no personal data, host names or paths.

| Question | Finding | Source |
|---|---|---|
| Part or Assembly | The INP Part `CFRP_301x300_SHELL` has nodes at X -251…50, Y -270…30, Z 0. The Instance `CFRP_301x300_SHELL-1` carries **one data line: translation (251, 270, 0)**. The R6 coordinates (X 0–301, Y 0–300) are the **Assembly** frame: R6 = INP Part + translation, max 1.5e-05 mm, all 10 201 labels equal. | INP `962f75f2fd5d…`, R6 `geometry.csv` `8bb5319fd759…` |
| X = 0, Y = 0 | Assembly corner (0, 0) = Part point (−251, −270). The Part origin (0, 0) lies inside the plate, 50 mm and 30 mm from two edges. | INP, journal |
| +X, +Y | +X along the 301 mm side, +Y along the 300 mm side; 101 × 101 nodes, uniform 3.01 × 3.00 mm. | INP |
| +Z normal | S4R element 1 has nodes 1 → 2 → 103 → 102 at (0,0) → (3.01,0) → (3.01,3) → (0,3), counter-clockwise seen from +Z. The right-hand rule gives normal +Z: SPOS on +Z, SNEG on −Z. All 10000 elements have +Z; 0 have −Z. | INP |
| Instance rotation, reflection, transfer | Translation only. No rotation line, no reflection. The journal records `translate (251, 270, 0)`, then `(0, −300, 0)` and `(0, +300, 0)`: net (251, 270, 0). | INP, journal `223643adb947…` |
| How the geometry was built | The journal sketches a rectangle (0, 0)–(50, 30), then dimensions it 301 × 300. The vertex (50, 30) stayed fixed and the outline grew to −251 / −270. The Instance was then translated to put that corner at 0, 0. | journal |
| Physical references in the model | **None.** The only set is `Set-1` (the whole face). There are no surfaces, partitions, datum points, reference points, named edges, holes or attachment points, and no boundary conditions (free-free). The material orientation is GLOBAL, the shell section homogeneous (0.875 mm, 5 Simpson points, middle surface), the density uniform. The replay files contain display commands only (Front / Bottom / Iso views). | INP, journal, `abaqus.rpy*` |
| Symmetry of the FE model | The node set is invariant under x → 301 − x, y → 300 − y and both (verified). Together with the uniform orthotropic GLOBAL material, the mid-plane-symmetric section and the free-free supports, the FE model is invariant under the three 180° rotations about axes through its centre. | `r63_fe_frame.json` |

**Conclusion.** The FE axes are established **in the model**. The INP and the supporting materials contain **no**
evidence linking an FE edge or the FE origin to a physical edge 1–4. The origin corner is an artefact of how the sketch
was dimensioned. A featureless rectangular mesh cannot identify a corner of the real specimen.

### 15.2 FE-to-physical correspondence: candidates A–D and their evidence

Pictures A–D (§14) are physical placements of the FE model on the plate, with the 301 mm side horizontal.

| Picture | Physical edge at FE X = 0 | FE X = 301 | FE Y = 0 | FE Y = 300 | FE +Z (SPOS) points out of | Experimental axes in FE if the scanner was opposite the shaker | … if the scanner was on the shaker side |
|---|---|---|---|---|---|---|---|
| **A** | 4 | 2 | 3 | 1 | marked face (towards the shaker) | -X +Y -Z | +X +Y +Z |
| **B** | 2 | 4 | 1 | 3 | marked face (towards the shaker) | +X -Y -Z | -X -Y +Z |
| **C** | 4 | 2 | 1 | 3 | unmarked face (away from the shaker) | -X -Y +Z | +X -Y -Z |
| **D** | 2 | 4 | 3 | 1 | unmarked face (away from the shaker) | +X +Y +Z | -X +Y -Z |

The experimental-axes column of §14.2 holds **only** if the scanner was opposite the shaker. Otherwise the rows A↔D and
B↔C swap. The set of the four admissible matrices is the same in both cases.

| Item | Supported by FE coordinates | Supported by physical records (HUMAN) | Assumption | What distinguishes the candidates |
|---|---|---|---|---|
| All of A–D | X along 301, Y along 300, +Z normal, determinant +1 | 301 × 300; 301 mm horizontal; edges 1 top / 2 right / 3 bottom / 4 left from the shaker side; marks on the shaker side; shaker near edge 3, left of centre (approximate) | The scanner was opposite the shaker; this is needed only for the experimental-axes column | **Only** which physical corner is FE (0, 0) and which face +Z leaves. No FE or physical record fixes either. |

- **The owner's recognition of picture D does not discriminate.** All four pictures show the same physical edge
  layout, so the recognition confirms only that layout, which was already HUMAN.
- **No photograph of the plate can close the question.** The FE origin is not a physical feature: the model was
  sketched with no reference to the specimen and has no physical landmark.
- **What could close it:**
  - (i) a record made when the model was built of the intended correspondence. The owner states none exists.
  - (ii) a **SUPERVISOR convention** that declares one placement and records it as `CONVENTION`, not as a physical or
    HUMAN fact.
  - (iii) a future FE model that carries a physical asymmetry, such as the measured edge thicknesses 1–4. Its
    construction would fix the correspondence.
- **Property of this model (stated, not computed).** The four admissible exp→FE matrices are related by the exact
  symmetries of the FE model in §15.1. A diagnostic comparison with this model is therefore mathematically
  independent of the choice among A–D, apart from the global sign of each mode. This is not used to select anything.

**PHYSICAL_FE_ORIENTATION = NOT_DETERMINED.**

### 15.3 Scanner face

| Level | Finding |
|---|---|
| Established by instrument record | The stored frame (`Info/VideoBitmap`) shows the **scanned** face. Three records support this: (1) the 2D video alignment (`Info/VideoSettings`, 13 points) ties the scanner mirror angles to positions in this frame, with residuals ≤ 2.37 px (≈ 0.8 mm); (2) the scanner angles of the 289 points match the reconstructed grid by a similarity transform, rms 1.32 mm (§15.4); (3) the scan head is `PSV-I-680` (`Info/ScanHead`). No stored record names the marked or unmarked face. |
| Confirmed by the owner (HUMAN) | The marks are on the shaker-facing side. The shaker is near edge 3, left of centre seen from the shaker side (approximate). |
| Inferred from the photograph | (a) The shaker body is behind the plate: the plate occludes it and the bottom plate edge lies in front of the dark shaker. (b) The shaker appears **right** of centre at ≈ 0.77 of the width, the mirror of the owner's "left of centre" from the shaker side, so the camera looked from the other side. Both point to the face opposite the shaker, i.e. the unmarked face. No numerals are visible, but on its own that is not evidence. |
| Unknown | No instrument record of the side. |

**SCANNER_FACE = HUMAN_CONFIRMATION_PENDING.** One owner yes/no answer closes it. No photograph showing people or
equipment labels is published.

### 15.4 Independent audit of the three reconstruction deviations

The scale is 2.964 px/mm in the 1920 × 1080 frame.

**The sum of the offsets and the window equal 301 / 300 mm by construction; this is not used as evidence.**

| Deviation | Independent evidence | Sensitivity | Verdict |
|---|---|---|---|
| **1. v range 0..1 instead of the stored −2.4667..1.0** | **Scanner angles (`Info/VideoSettings`):** this uses neither the frame rectangle nor the plate edges. Inverting the alignment model for the 289 points gives a grid aspect (width / height) of 0.7747 in angle space. The reconstruction with v 0..1 gives 0.7553. A similarity fit of angle to reconstruction leaves rms 1.32 mm, max 2.34 mm, and implies a standoff of ≈ 1209 mm. The stored v range would give an aspect of 2.6; a 4:3 u normalisation would give 1.0. Both are contradicted by the angles. **Frame:** the stored u range spans exactly 1920/1080 (ratio 1.0), so v 0..1 gives square pixels; the stored v range gives 3.4667:1. The alignment isotropy is 0.9721. The alignment points lie in v 0.0952–0.8659. | With the stored range the reconstruction fails ("top edge: too few samples"). | **Independently confirmed by an existing source** (the scanner-angle record) for the scale and shape of the grid. The vertical position then follows from the stored v1 = 1.0. Why the stored field holds v0 = −2.4667 is not documented. |
| **2. Edge search window 220 px instead of 150** | None beyond the image. Two checks: the plate in the frame measures 892.2 × 892.6 px for 301 × 300 mm (px/mm x/y 0.9962); the green edge lines coincide visually with the plate edges. | 150–200 px: the left edge is not found ("too few samples"); no other edge is found instead. 220, 250 and 300 px give the same edges and offsets to 0.01 mm. | **Supported, no independent confirmation.** The value is immaterial at 220 px and above. |
| **3. Bottom edge on the inverted image, step 8** | None beyond the image. Cross-check: the bottom edge predicted from the top edge plus 300 mm at the horizontal px/mm (square pixels, plate facing the camera) differs from the detected edge by 1.13 mm. | The accepted polarity puts the "bottom edge" at -17.37 mm, with scan points outside the plate: physically impossible. Inverted steps 6, 8, 10 and 12 give the same result within 0.01 mm. Step 16 moves to another feature (bottom offset 1.01 mm). | **Supported, no independent confirmation.** A competing image feature lies ≈ 6 mm away. |

**Credibility of the offsets** (left 56.4 / right 29.19 / bottom 7.02 / top 7.78 mm).

Diagnostic error contributions, not acceptance criteria:

| Contribution | Size |
|---|---|
| Edge-line fit | ≤ 0.097 mm rms |
| Video-to-scanner alignment residual | u ≤ 0.38 mm, v ≤ 0.80 mm |
| Projective reconstruction vs the per-axis scan model | median 1.29 mm, max 3.23 mm |
| Angle-to-reconstruction shape | rms 1.32 mm, max 2.34 mm |
| Bottom-edge cross-check | 1.13 mm |

- Together these indicate offsets **uncertain at the level of 1–3 mm**, comparable to the FE mesh spacing of 3 mm.
- The left / right asymmetry (56.4 vs 29.2 mm) comes from the image edges and is not checked by any independent
  record.
- The UNV metric geometry is **not** a physical calibration and gives no confirmation either way: its grid is nearly
  square (0.9951), and fitted to the reconstruction it leaves rms 15.04 mm.

**Minimal evidence to close the calibration without a new experiment.** A screenshot from the Polytec PSV software
opening a **copy** of the `.svd`, with the scan points overlaid on the stored video frame. It shows the
instrument's own point-to-image mapping, which closes deviation 1 at the source, and lets the edges of deviations 2
and 3 be judged against the instrument's display. It would contain the laboratory photograph and must not be
published.

Alternatively, the SUPERVISOR can accept deviations 2 and 3 on the sensitivity evidence above. That is a decision, not
evidence.

**SCAN_WINDOW_CALIBRATION = DIAGNOSTIC_ONLY.** Deviation 1 is independently confirmed; deviations 2 and 3 are
supported without independent confirmation.

### 15.5 INP–ODB provenance (limit of the evidence)

Without opening the ODB, the job records in the V3 copies and the R6 package agree.

- **Job and input:** `.com` names job `CFRP_S4R_0875_FreeFree` with input `CFRP_S4R_0875_FreeFree`, format INP. The
  INP header says "Generated by Abaqus/CAE 2024", and the journal creates and submits this job from `Model-1`.
- **Timing** (source mtimes in `COPY_MANIFEST_V3.json`, preserved in the copies):
  - INP written 17:29:17;
  - input processing 17:29:25–29 (`.log`);
  - analysis 17:29:29–34;
  - ODB written 17:29:34.
- **Model data:**
  - the heading "CFRP 301x300x0.875, S4R, mesh 3mm" is the same in the INP, `.dat`, `.msg` and the ODB title (R6
    manifest);
  - `.dat`: 10 000 elements and 10 201 nodes, `*Element, type=S4R`, elset `ASSEMBLY_CFRP_301X300_SHELL-1_SET-1`;
  - the `.dat` eigenfrequencies of modes 3–20 equal those read from the ODB (R6 postflight, max difference 0 Hz). This
    is a record comparison, not fitting.
- **Not available:** the `.dat` was written with `model=NO`, so no mesh echo. The R6 package holds no ODB element
  types or connectivity. The `.sim` / `.prt` are binary and need Abaqus tools.

**Status:** the records are consistent with the ODB having been produced by this job from an INP with this name,
heading, size and element type. **Mesh identity is not proven.** `FE_MODEL_IDENTITY = NODES_AND_INP_CONTENT` is
unchanged, R7 / PR #96 is not modified, and closing the gap needs option (a) or (b) of R7 R2.

### 15.6 What was closed without the owner, and what remains

| Item | Status after R6.3 | Closed by | Still needed |
|---|---|---|---|
| FE frame (Part / Assembly, origin, +X / +Y, +Z normal, Instance) | **Closed** | INP, journal, R6 | — |
| Physical references inside the FE model | **Closed: none exist** | INP, journal, replay | — |
| FE ↔ physical edges (A–D) | Not determined; cannot be determined from the model | — | SUPERVISOR convention, or a model with physical asymmetry |
| Scanner face | Instrument: the frame is the scanned face. Photograph: unmarked face. | VideoSettings, frame | Owner yes / no |
| Deviation 1 (v range) | **Independently confirmed** (shape and scale) | Scanner angles | Optional: PSV software overlay |
| Deviations 2, 3 (edges) | Supported, insensitive within the tested range | Sensitivity runs | SUPERVISOR decision, or PSV overlay |
| INP–ODB mesh identity | Job records consistent; identity not proven | `.com` / `.log` / `.dat` / `.msg`, R6 | R7 R2 option (a) or (b) |

**What prevents a diagnostic MAC.** The first three are hard blockers; the fourth only requires a recorded decision.

1. MAC is not authorised; that is a SUPERVISOR gate.
2. The R7 shell gate (PR #96) is not merged, and a shell registration needs it.
3. The evidence record cannot be completed: it needs the axes, `shell_measured_face` and the panel-edge offsets, and
   no FE↔physical placement is declared. This model's symmetry makes the numerical result independent of the
   placement, so a SUPERVISOR **convention** plus the SCANNER_FACE answer would be enough.
4. The scan calibration is diagnostic only: deviations 2 and 3 need a decision.

The INP–ODB identity limit is not a blocker: R7 records it as a warning.

**Verdicts:**

- FE_MODEL_AXES = **ESTABLISHED**
- FE_TO_PHYSICAL_EDGES = **NOT_DETERMINED**
- SCANNER_FACE = **HUMAN_CONFIRMATION_PENDING**
- SCAN_WINDOW_CALIBRATION = **DIAGNOSTIC_ONLY**

M11 stays FE_EXTRACTION_READY / PHYSICAL_REGISTRATION_PENDING.

## 16. R6.4 (2026-10-22): FE modal symmetry and scan-mapping sensitivity

Read-only inputs:

- the R6 extraction: `geometry.csv`, `mode_0007…0020.csv`;
- the **diagnostic** reconstruction `plate_reconstruction_W301xH300.json`.

**No experimental modal data and no experimental frequencies are used, and no MAC is computed** (neither the
existing implementation nor a new one). FE fields are compared only by relative L2 norms of differences and by
principal angles between FE subspaces.

The R6.3 statuses are unchanged:

- FE frame established;
- PHYSICAL_FE_ORIENTATION = NOT_DETERMINED;
- SCANNER_FACE = HUMAN_CONFIRMATION_PENDING;
- reconstruction diagnostic;
- FE_MODEL_IDENTITY = NODES_AND_INP_CONTENT.

The SUPERVISOR decision of R6.4 §4 applies: the three reconstruction deviations are **diagnostic algorithmic
assumptions for sensitivity studies only**, not a physical calibration.

Derived files are in `runs\m11_carbon_plate\r64\`: `r64_fe_symmetry.json` and `r64_mapping_sensitivity.json`.
Scripts: `tools\r64_*.py`.

### 16.1 FE modal symmetry, checked on the extracted modes 7–20

**Node maps.** The three 180° rotations about axes through the plate centre are:

- Rx: Y → 300 − Y, Z → −Z; displacement (u1, −u2, −u3);
- Ry: X → 301 − X, Z → −Z; displacement (−u1, u2, −u3);
- Rz: X → 301 − X, Y → 300 − Y; displacement (−u1, −u2, u3).

Each is a bijection and an involution on the 10 201 nodes. The maximum coordinate mismatch is
1.5e-05 mm, which is single-precision ODB
coordinates.

**Test.** For each mode φ, the field is transformed (Tφ)ᵢ = Q φ_g(i), the parity p = ⟨φ, Tφ⟩ / ⟨φ, φ⟩ is taken, and
the residual is ‖Tφ − sign(p) φ‖ / ‖φ‖ over all three components. The modes are real (imaginary parts 0), so
"arbitrary phase" reduces to the sign.

**Negative control:** a shift by one node pitch, which is not a symmetry, gives residuals
0.03–0.10. The test therefore discriminates.

| Mode | FE Hz | Rx | Ry | Rz | residual Rx | residual Ry | residual Rz | Rz = Rx·Ry | in-plane / out-of-plane norm | Symmetry |
|---|---|---|---|---|---|---|---|---|---|---|
| 7 | 19.072 | + | + | + | 2.9e-10 | 5.7e-08 | 5.7e-08 | yes | 2e-14 | holds |
| 8 | 59.874 | − | − | + | 1.4e-13 | 8.4e-08 | 8.4e-08 | yes | 6e-15 | holds |
| 9 | 62.009 | − | − | + | 2.6e-09 | 7.0e-08 | 7.0e-08 | yes | 6e-15 | holds |
| 10 | 71.850 | + | − | − | 6.6e-09 | 1.0e-07 | 1.0e-07 | yes | 4e-15 | holds |
| 11 | 72.190 | − | + | − | 6.0e-09 | 5.7e-08 | 5.7e-08 | yes | 3e-15 | holds |
| 12 | 116.580 | − | − | + | 2.7e-15 | 1.0e-07 | 1.0e-07 | yes | 4e-15 | holds |
| 13 | 167.490 | − | + | − | 2.4e-09 | 1.4e-07 | 1.4e-07 | yes | 6e-15 | holds |
| 14 | 168.610 | + | − | − | 6.4e-10 | 9.7e-09 | 9.7e-09 | yes | 2e-15 | holds |
| 15 | 174.800 | + | + | + | 1.1e-09 | 1.1e-07 | 1.1e-07 | yes | 7e-15 | holds |
| 16 | 179.900 | + | + | + | 8.0e-13 | 9.6e-08 | 9.6e-08 | yes | 1e-14 | holds |
| 17 | 213.200 | − | + | − | 3.2e-09 | 1.4e-07 | 1.4e-07 | yes | 5e-15 | holds |
| 18 | 213.950 | + | − | − | 9.1e-10 | 1.0e-07 | 1.0e-07 | yes | 1e-14 | holds |
| 19 | 295.780 | + | + | + | 2.1e-08 | 1.4e-07 | 1.4e-07 | yes | 2e-11 | holds |
| 20 | 327.900 | − | − | + | 2.6e-08 | 1.8e-07 | 1.8e-07 | yes | 3e-11 | holds |

- Every elastic mode is exactly symmetric or antisymmetric under all three rotations. The largest residual is
  1.8e-07, the order of single-precision data.
- The modes are pure out-of-plane bending: in-plane / out-of-plane ≤ 3e-11.
- No transformation and no mode is non-equivalent.

**Adjacent pairs: subspace invariance.** The maximum principal angle between span{φᵢ, φⱼ} and its transformed
span is ≤ 1.1e-05° for every adjacent pair.

| Pair | FE Hz | Relative gap | Parity class (Rx Ry Rz) | Max principal angle |
|---|---|---|---|---|
| 7–8 | 19.07 / 59.87 | 213.94 % | +++ / −−+ | 4.8e-06° |
| 8–9 | 59.87 / 62.01 | 3.57 % | −−+ / −−+ | 6.0e-06° |
| 9–10 | 62.01 / 71.85 | 15.87 % | −−+ / +−− | 5.9e-06° |
| 10–11 | 71.85 / 72.19 | 0.47 % | +−− / −+− | 5.9e-06° |
| 11–12 | 72.19 / 116.58 | 61.49 % | −+− / −−+ | 5.9e-06° |
| 12–13 | 116.58 / 167.49 | 43.67 % | −−+ / −+− | 7.9e-06° |
| 13–14 | 167.49 / 168.61 | 0.67 % | −+− / +−− | 7.9e-06° |
| 14–15 | 168.61 / 174.80 | 3.67 % | +−− / +++ | 6.6e-06° |
| 15–16 | 174.80 / 179.90 | 2.92 % | +++ / +++ | 8.0e-06° |
| 16–17 | 179.90 / 213.20 | 18.51 % | +++ / −+− | 7.8e-06° |
| 17–18 | 213.20 / 213.95 | 0.35 % | −+− / +−− | 7.8e-06° |
| 18–19 | 213.95 / 295.78 | 38.25 % | +−− / +++ | 7.8e-06° |
| 19–20 | 295.78 / 327.90 | 10.86 % | +++ / −−+ | 1.1e-05° |

- **Three near-degenerate pairs stand out** by an order of magnitude: **10–11** (0.47 %), **13–14** (0.67 %) and
  **17–18** (0.35 %). Every other adjacent gap is ≥ 2.9 %. This is a natural grouping, not a new threshold.
- In each of these pairs the two FE modes belong to **different** symmetry classes, so the FE model cannot mix them.
- The real plate is not exactly symmetric: the edge thicknesses are 0.816–0.926 mm. Its modes may therefore be mixed
  within these pairs. A future comparison should treat them **as two-dimensional subspaces**.
- Two adjacent pairs share a class and could mix in the real plate: **8–9** (−−+, 3.6 %) and **15–16** (+++,
  2.9 %). They should be watched.

### 16.2 The four candidates A–D (no physical orientation chosen)

- A–D map to one another exactly through the FE symmetries: B = Rz·A, C = Rx·A, D = Ry·A.
- In all 59 mapping scenarios of §16.3, the node chosen for each point under B, C and D is **exactly** the symmetric
  image of the node chosen under A: 100 % of points, minimum
  1.00.
- The FE U3 vectors sampled at the 289 points are identical across A–D up to sign: largest relative difference
  1.5e-07.
- All mapping metrics in §16.3 are identical for A, B, C and D.
- **Consequence:** for this FE model, a shape comparison is mathematically invariant to the choice among A–D. The set
  of four admissible matrices is also the same under both scanner-face hypotheses (§15.2), so the comparison is
  invariant to SCANNER_FACE too.
- Where a label is needed for illustration, D is used **only as `COMPUTATIONAL_CONVENTION_ONLY`**, never as
  `HUMAN_CONFIRMED`, `PHYSICALLY_ESTABLISHED` or `ACCEPTED_REGISTRATION`.
- PHYSICAL_FE_ORIENTATION = NOT_DETERMINED is unchanged.
- The convention is **not** written as `panel_edges` or `corner_A_marker` evidence, and the R7 guided
  physical-registration gate is not used or changed.

### 16.3 Sensitivity of the 289-point mapping (diagnostic reconstruction)

[![Mapping sensitivity](figures/m11_r64/fig_r64_mapping_sensitivity.png)](figures/m11_r64/fig_r64_mapping_sensitivity.png)

*Figure 16.1 — mapping sensitivity.* SHA-256 `a06834f13709b0b6862a649885e757a22d093c1bfd5d9d8a1a208a8dfaf394bc`. Generated from the FE data alone; it contains no
photograph or personal data.

**Inputs:**

| Quantity | Value |
|---|---|
| Nominal window | 215.42 × 285.2 mm, offsets 56.40 / 29.19 / 7.02 / 7.78 mm (scanner view). Diagnostic, **not** measured. |
| Scan pitch | 13.464 × 17.825 mm |
| FE pitch | 3.01 × 3.0 mm |
| Shifts | ±1, ±2, ±3 mm in X and Y, separately and together (49 cases) |
| Rotation | ±0.874° about the window centre (the observed axis misalignment, used as a scenario, not as an established error), alone and with corner shifts of ±3 mm |
| Existing method | `services.physical_registration`: nearest measured-surface node; the limits `matched_fraction` ≥ 0.90 within 0.03 × scan diagonal (10.72 mm) and normalised RMS ≤ 0.03 are **unchanged** |

The table is for candidate A; B, C and D are identical.

| Scenario | Inside FE plate | Without admissible binding | Nearest-node RMS, mm | Max, mm | Points assigned another node | Expected for uniform sub-cell positions | Repeated node assignments | Existing method: matched fraction / normalised RMS |
|---|---|---|---|---|---|---|---|---|
| `dx+0_dy+0` | 289 / 289 | 0 | 1.26 | 2.06 | 0.0 % | 0.0 % | 0 | 1.00 / 0.0035 |
| `dx+1_dy+0` | 289 / 289 | 0 | 1.29 | 2.07 | 36.0 % | 33.2 % | 0 | 1.00 / 0.0036 |
| `dx-1_dy+0` | 289 / 289 | 0 | 1.29 | 2.08 | 31.1 % | 33.2 % | 0 | 1.00 / 0.0036 |
| `dx+0_dy+1` | 289 / 289 | 0 | 1.24 | 1.98 | 51.6 % | 33.3 % | 0 | 1.00 / 0.0035 |
| `dx+0_dy-1` | 289 / 289 | 0 | 1.11 | 2.02 | 26.6 % | 33.3 % | 0 | 1.00 / 0.0031 |
| `dx+1_dy+1` | 289 / 289 | 0 | 1.26 | 2.04 | 69.2 % | 55.5 % | 0 | 1.00 / 0.0035 |
| `dx+2_dy+0` | 289 / 289 | 0 | 1.29 | 2.07 | 68.9 % | 66.5 % | 0 | 1.00 / 0.0036 |
| `dx+0_dy+2` | 289 / 289 | 0 | 1.11 | 2.02 | 73.4 % | 66.7 % | 0 | 1.00 / 0.0031 |
| `dx+2_dy+2` | 289 / 289 | 0 | 1.14 | 2.04 | 92.0 % | 88.8 % | 0 | 1.00 / 0.0032 |
| `dx+3_dy+0` | 289 / 289 | 0 | 1.26 | 2.07 | 100.0 % | 99.7 % | 0 | 1.00 / 0.0035 |
| `dx+0_dy+3` | 289 / 289 | 0 | 1.26 | 2.06 | 100.0 % | 100.0 % | 0 | 1.00 / 0.0035 |
| `dx+3_dy+3` | 289 / 289 | 0 | 1.26 | 2.07 | 100.0 % | 100.0 % | 0 | 1.00 / 0.0035 |
| `dx-3_dy-3` | 289 / 289 | 0 | 1.26 | 2.05 | 100.0 % | 100.0 % | 0 | 1.00 / 0.0035 |
| `rot-0.874_dx+0_dy+0` | 289 / 289 | 0 | 1.24 | 2.07 | 63.0 % | — | 0 | 1.00 / 0.0035 |
| `rot+0.874_dx+0_dy+0` | 289 / 289 | 0 | 1.21 | 2.08 | 56.8 % | — | 0 | 1.00 / 0.0034 |
| `rot+0.874_dx+3_dy+3` | 289 / 289 | 0 | 1.21 | 2.09 | 100.0 % | — | 0 | 1.00 / 0.0034 |
| `rot-0.874_dx-3_dy-3` | 289 / 289 | 0 | 1.24 | 2.06 | 95.9 % | — | 0 | 1.00 / 0.0035 |

1. **The geometry is never the problem.**
   - In all 59 scenarios every point lies on the plate.
   - No point lacks a binding, and no FE node receives two points.
   - The nearest-node distance is RMS 1.1–1.3 mm and at most 2.09 mm, bounded by the half-diagonal of the
     3.01 × 3.00 mm cell (2.12 mm).
   - The existing method's limits pass in **every** scenario. They are 3–4 times looser than the uncertainty studied,
     so they **cannot detect** a 1–3 mm window error. The limits are not changed.
2. **The node assignment is not stable at the 1–3 mm level, as stated plainly.**
   - A 1 mm shift reassigns 27–52 % of the points; 2 mm reassigns 69–92 %.
   - A 3 mm shift, one FE pitch, reassigns **100 %**: every point moves to the neighbouring node.
   - The 0.87° rotation alone reassigns 57–63 %.
   - The fractions follow the estimate for sub-cell positions spread uniformly within a cell, except in Y. There
     17.825 / 3.0 ≈ 5.94 mesh cells, so the sub-cell positions are not uniform and +1 mm and −1 mm differ
     (52 % vs 27 %).
3. **What the reassignment means for the shapes.** The FE U3 field sampled at the 289 points changes smoothly. The
   relative L2 change, FE against itself (not MAC, no experimental data), is:

| FE mode | 1 mm X | 1 mm Y | 1 mm X+Y | 2 mm X+Y | 3 mm X+Y | rotation 0.87° |
|---|---|---|---|---|---|---|
| 7 | 2.6 | 2.3 | 3.8 | 4.9 | 5.6 | 3.4 |
| 8 | 3.5 | 4.0 | 4.9 | 6.3 | 7.3 | 5.1 |
| 9 | 2.8 | 4.6 | 5.7 | 6.8 | 7.2 | 3.1 |
| 10 | 4.8 | 2.4 | 5.4 | 6.7 | 8.3 | 5.7 |
| 11 | 2.6 | 5.4 | 6.3 | 7.9 | 8.2 | 5.3 |
| 12 | 5.0 | 5.6 | 7.5 | 9.0 | 10.1 | 5.3 |
| 13 | 5.2 | 0.2 | 5.2 | 7.2 | 9.1 | 5.5 |
| 14 | 0.1 | 8.3 | 8.3 | 9.6 | 10.4 | 5.8 |
| 15 | 4.5 | 5.6 | 6.8 | 9.2 | 10.6 | 8.5 |
| 16 | 3.9 | 5.5 | 7.5 | 8.7 | 10.2 | 5.6 |
| 17 | 5.4 | 5.3 | 7.8 | 9.7 | 11.5 | 6.8 |
| 18 | 4.8 | 8.5 | 9.7 | 11.2 | 12.8 | 6.8 |
| 19 | 5.3 | 8.0 | 9.8 | 12.0 | 13.9 | 8.2 |
| 20 | 6.7 | 4.4 | 8.0 | 10.3 | 11.8 | 7.6 |

- The change grows with mode order: 0.1–9.8 % at 1 mm and up to 13.9 %
  at 3 mm.
- Some modes are insensitive in one direction: mode 13 to Y and mode 14 to X.
- For two vectors whose relative difference is ε, any normalised shape-correlation measure degrades only at second
  order, at most about ε² / (1 − ε)². For ε ≤ 0.14 that is ≈ 0.02. This is an analytical bound; no MAC was computed.
- **The nearest-node quantisation itself** (RMS 1.26 mm, max 2.06 mm at the nominal position) is as large as the
  calibration uncertainty under study.
- Interpolating the FE field with the S4R bilinear shape functions at the point positions would remove the
  discontinuous node jumps. This is proposed only, not implemented.

### 16.4 The three reconstruction deviations in this light

| Deviation | Status (SUPERVISOR, R6.4 §4) | Effect on this analysis |
|---|---|---|
| 1. v range 0..1 | Consistent with the image-independent scanner-angle record of the same measurement system. The absolute window position is not fully confirmed. | Fixes the grid shape and scale. Position errors are covered by the ±3 mm and ±0.87° scenarios. |
| 2. Edge window 220 px | Supported by identical results at 220–300 px | No separate effect: the left edge is the same line. |
| 3. Bottom edge, inverted polarity | Supported by the polarity checks; no external physical control | Its main risk is a Y offset of ≈ 1 mm (cross-check 1.13 mm), within the ±3 mm scenarios. The competing feature about 6 mm away (§15.4) lies **outside** the studied range and would need a physical check. |

The 1–3 mm engineering estimate is **not** a confidence interval and not a criterion.

### 16.5 Proposal to the SUPERVISOR for the next step (nothing implemented)

**Readiness verdict.** The current data are sufficient to **propose** a research, non-governed, non-production
diagnostic shape comparison that is invariant to A–D and to SCANNER_FACE. It is not a physical registration. It cannot
use the R7 guided-registration gate, because that gate admits physical references only. **It needs a SUPERVISOR
decision before any experimental–FE MAC is computed.**

Outline of a separate research protocol, proposed only:

1. **Status.** It runs outside the guided registration and outside `panel_edges` / `corner_A_marker`. It is labelled
   `DIAGNOSTIC_NOT_REGISTERED / COMPUTATIONAL_CONVENTION_ONLY`. It writes no `FrozenRegistration` and changes no
   evidence schema, gate, threshold, SPEC or R7 code.
2. **Fixed in advance,** before any experimental shape is read:
   - the mapping: nearest node, as in the existing method, plus bilinear interpolation as a declared secondary
     result;
   - the sensitivity scenarios: ±1/2/3 mm and ±0.87°;
   - the subspace groups: 10–11, 13–14, 17–18, and 8–9 and 15–16 to be watched;
   - the rule that every result is reported as a range over the scenarios. It is never re-tuned, and no shift is
     selected by agreement.
3. **Built-in self-check:** the computation is repeated for A, B, C and D and must give identical results up to mode
   sign. §16.2 shows this holds exactly for this model.
4. **Data checks before the first experimental–FE MAC:**
   - experimental set `polymax-bravo`: 10 modes, 289 points, U3 only, point order validated (MeasPoints ↔ UNV);
   - the handling of complex experimental modes, i.e. the real-normalisation convention, is declared;
   - the beam inclination (scan angles ≤ about 7°, cos ≥ 0.99) is noted;
   - the FE U3 component only; rigid modes 1–6 excluded;
   - no pairing by frequency.
5. **Output:** diagnostic only. It does not feed Auto-ID, LM, material constants or any governed gate.

**What this does not replace** (independent physical data still needed for a physical registration):

- SCANNER_FACE: owner yes / no;
- the FE ↔ physical correspondence: not determinable from this model; only by convention or by a model with a
  physical asymmetry;
- an independent check of the window position: a Polytec PSV overlay screenshot of a copy of the `.svd`, not
  published;
- the INP–ODB mesh identity: R7 R2 option (a) or (b).

M11 remains FE_EXTRACTION_READY / PHYSICAL_REGISTRATION_PENDING.

## 17. What did not change

- SPEC, DECISIONS, EVIDENCE, registrations, criteria and gates.
- Every original and every earlier copy.
- Branch `analysis/m10-sp10-registration-prep` and PR #94.
- No FE solve, no Auto-ID or LM, no MAC, no material change. Abaqus Python: exactly one authorised extraction run
  (R6) on a working copy of `CFRP_S4R_0875_FreeFree.odb`; no other ODB was opened.
- M8 original gate `NOT_MET`; production calibration BLOCKED / NOT_AUTHORISED; D-077 NO_GLOBAL_PARAMETER_VALUE.
