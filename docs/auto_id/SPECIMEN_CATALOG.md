# Specimen catalog (canonical specimen reference)

**Status:** `REVIEW_READY` (worker audit, 2026-10-06; not yet SUPERVISOR-accepted).
**Machine-readable twin:** `specimen_catalog.json`, one deterministic entry per physical specimen, with
source paths, sizes and SHA-256 hashes. It is a governed project-information artifact, **not** a runtime
dependency.

- **What it is:** one place for every real specimen fact found in the records, so that M6/M7 work does not
  ask the HUMAN again for facts that are already written down.
- **What it is not:** it creates no passport, fixture, registration or forward model. It changes no governed
  file and no scientific rule. It accepts nothing.
- **Precedence:** SPEC > DECISIONS > ROADMAP > STATUS > accepted EVIDENCE still apply. Where this catalog
  finds a conflict with them, it is listed in §9 and nothing is silently rewritten.
- **Abaqus:** 0 solves, 0 Abaqus Python extractions.

## 1. Sources audited

Source priority for physical facts: the specimen folder in `D:\Snadwich` (its `spec` file) first, then the
project records below. Values were never reconstructed from secondary documents when the spec file
records them.

| Store id | Location | What it holds |
|---|---|---|
| `snadwich` | `D:\Snadwich` | Curated specimen folders SP-01 … SP-11, SP-13: spec files, raw PSV UNV/SVD, PolyMAX UNVs for SP-02/SP-10/SP-13, FE files |
| `sumin` | `I:\Sumin` | Experiment hand-over: `SPname_files_260909` (raw batch incl. **SP-06** and **SP-15**), `SPname_files_260909_polymax.zip` (13 Testlab PolyMAX exports), `Updated_260911` (SP-10/SP-13 repeats, LMS frequency/damping summaries) |
| `sandwich-article` | `D:\work 2.0\Статьи В работе\Сендвич с индусом` | Article project: Obsidian specimen vault (origin of the spec files; SP-01 … SP-15 notes), `Results/Politec+LMS` copies, reports, photos, adhesive/PLA datasheets |
| `temp-12-sampls` | `C:\temp\12 sampls` | Working folders `results/SP01 … SP15` (FE runs; SP-06 and SP-15 acquisitions; SP03/04/07–12/14 empty) |
| `c-temp` | `C:\temp` | Ungoverned Abaqus working directory (e.g. `SP-01.inp/.odb`, twill plate study, 302×297.5 honeycomb models) |
| `carbon-project-archive` | `D:\carbon_project_archive` | Archived CARBON records (CARBON-5D core provenance) |
| repository | `docs/auto_id/…`, `docs/registrations/…` | Passports, fixtures, forward models, registrations, EVIDENCE, DECISIONS, STATUS |

Of the 108 `.svd`/`.unv` files found outside `D:\Snadwich`, 91 are byte-identical copies of store files.
The other 17 are copies of the SP-06 and SP-15 acquisitions (which exist only outside the store) and two
SP-15 derived UNVs in `C:\temp\12 sampls`.

Also inspected:
- 17 PSV camera frames (labels): all 15 in the store plus SP-06 and SP-15;
- the FE `.dat` eigenvalue tables and the INP material blocks;
- the Obsidian notes, compared value by value with the spec files (identical values; format differences
  only);
- the LMS spreadsheets.

## 2. HUMAN-confirmed context (governed; not re-asked)

- **Test orientation:**
  - the handwritten label was kept at the physical TOP of the panel;
  - the laser/scanner measured the labelled face, and the shaker excited the opposite face;
  - the lattice/core orientation during testing corresponded to the Abaqus model orientation.
- **Dimensions:** 100 cm steel ruler (smallest graduation 1 mm) and two calipers (dial caliper resolution
  0.01 mm). These are HUMAN-confirmed **readout resolutions**, not calibrated instrument accuracy.
- **Face-sheet thickness (physical local variation, not a calibrated map, not a statistical prior):**
  - old nominal ~0.45 mm stock: local values about 0.40–0.50 mm, most locations about 0.44–0.45 mm;
  - new nominal ~0.25 mm stock: local values about 0.23–0.28 mm, most locations about 0.25 mm;
  - neither extreme is taken as the whole-plate thickness.
- **Core:** the printed core geometry is stable relative to the face-sheet variation.
- **SP-02** has a honeycomb core; **SP-13** has an auxetic core.
- **SP-13 remount:**
  - removed from the suspension and re-suspended between 260909 and 260910;
  - laser/scanner and shaker not moved;
  - FREQUENCY_ONLY repeat evidence;
  - Testlab is currently NOT available.

## 3. Distinctions this catalog keeps explicit

| Do not confuse | With |
|---|---|
| Total sandwich thickness (spec "Dimensions", e.g. 2.9 mm) | Face-sheet thickness (0.45, 0.425, 0.25 mm …) |
| Nominal face thickness | A measured statistical thickness prior (none exists; no ≥ 9-point map) |
| FE template constants (E1 = 52 000 MPa, G12 = 4 500 MPa, PLA 2 580 MPa …: status `ASSUMED/TEMPLATE`) | Experimentally measured material properties (**none exist** for any specimen) |
| Model-calibration values (e.g. the June calibration report: E1 = 50 000, G12 = 3 360 MPa) | Measurements |
| Raw FRF (dataset 58) | Governed fitted modal data (dataset 55, frozen fixture) |
| An ungoverned PolyMAX export | A governed fixture (only `SP02/bravo-1`, `SP13/best`) |
| Existence of an INP/ODB | A governed reproducible M3 forward model (only SP-02 `SP02_Modal_V02`, SP-13 `SP13_mesh_local_v1_modal`) |
| Legacy centred registration | Physical registration (stored PSV records; SP-02, SP-13 only) |

## 4. Specimen inventory

- **Physical specimens with records: 14.**
  - SP-01 … SP-13 and SP-15.
  - SP-12 has notes and masses but no acquisition.
  - SP-15 has an acquisition but no specimen-specific facts.
- **SP-14: no physical record.**
  - Its vault note is a byte-identical copy of the SP-12 note.
  - Its results folder is empty.
  - The fragment "bigSP14" appears only in an SP-15 file name. Status AMBIGUOUS; SP-14 is not counted.
- **Unnumbered records (identity AMBIGUOUS, not counted):**
  - **LMS `Sheet1`:** five 300×300 test columns (Auxetic/DP420, Auxetic/DP190, Auxetic/**2216**,
    Honeycomb/DP420, Honeycomb/DP190) match no SP-04/06/07 PolyMAX set, and no spec uses 3M 2216.
    Column 6 is SP-05 exactly.
  - **June calibration report:** a 287 × 288.364 mm CFRP/DP190/PLA-auxetic panel, faces 0.235 mm, 164 g.
  - No raw data, spec or label was found for either.
- **Duplicates / copies:**
  - SP-13 is "copy of SP-01" and SP-10 is "copy of SP-02". These are **design** copies of physically
    different panels: different masses, different spectra.
  - `SP-13/SP-01 A-core 500x500.cae/.jnl` is a copy of the SP-01 CAE; the journal differs.
  - `SP15_500by500_bigSP14.svd` is the same file as `SP15_500by500.svd`.
  - No specimen exists twice under another name.
- **No unnumbered specimen folder exists** in any audited store.

## 5. Asset matrix

"Fit" = PolyMAX dataset-55 export (G = governed fixture; U = ungoverned, location in brackets).
"Phys reg" = physical registration from stored PSV records.

| Specimen | Family | Spec | Raw FRF sessions | PolyMAX | INP | ODB | CAE | Phys reg | Governed FE (M3) | M7 usability |
|---|---|---|---|---|---|---|---|---|---|---|
| SP-01 | old plain 0.45 | yes | 260624 | U (zip) | U (C:\temp) | U (C:\temp) | yes | no | no | after governance + FE + reg |
| SP-02 | old plain 0.45 | yes | 260803 retry | **G** `SP02/bravo-1` | yes | yes | yes | **yes (REVIEW_READY)** | **yes** | **M7 path with SP-13 (governance pending)** |
| SP-03 | old twill 0.45 | yes | 260803 | U (zip) | no | no | no | no | no | twill family only |
| SP-04 | old plain 0.25 | yes | 260822 | U (zip) | candidate (C:\temp, name only) | candidate | no | no | no | after governance + FE + reg |
| SP-05 | old plain 0.25 | yes | 260706a | U (zip) | yes (store) | yes (store) | yes | no | no | after governance + M3 + reg |
| SP-06 | new plain 0.25 | yes | 260824 (**outside store**) | U (zip) | no | no | no | no | no | after governance + FE + reg |
| SP-07 | new plain 0.25 | yes | 260824 (30–1000 Hz) | U (zip) | no | no | no | no | no | after governance + FE + reg |
| SP-08 | new plain 0.25 | yes | 260828 | U (zip) | no | no | no | no | no | after governance + FE + reg |
| SP-09 | new plain 0.25 | yes | 260831 | U (zip) | no | no | no | no | no | after governance + FE + reg |
| SP-10 | old plain 0.45 | yes | 260831; 260911 b_rotated | U (zip 260831; store 260911) | no | no | no | no | no | SP2/SP10 scatter pair after FE + reg + governance |
| SP-11 | old twill 0.45 (bare) | yes | 260824; 260826 a; 260826 b_center | U (zip, session a only) | candidate (C:\temp twill study) | candidate | no | no | no | not M7 (Stage A blocked, D-059) |
| SP-12 | new plain 0.25 (bare) | vault note only | none found | none | none found | none found | none found | no | no | no experiment |
| SP-13 | old plain 0.45 | yes | 260909; 260910 a | **G** `SP13/best` (260910); U (zip, 260909) | yes | yes | yes | **yes (production-ready)** | **yes** | **M7 path with SP-02; alone insufficient** |
| SP-15 | unassigned (bare) | none (note is an SP-12 copy) | 260901 (**outside store**) | U (zip) | U (C:\temp\12 sampls) | U | U (`new_CFRP_PLAIN_520_STAGEA.cae`) | no | no | identity AMBIGUOUS |

**PolyMAX exist for every specimen with an acquisition**, but only `SP02/bravo-1` and `SP13/best` are
governed.

## 6. Specimen records

Values are those of the specimen-folder spec file unless marked otherwise. Masses in g, lengths in mm.
"Template" constants are FE input values (`ASSUMED/TEMPLATE`), never measurements. Dimension source for
every spec: ruler + calipers (§2). Raw sessions are 121 points, Δf 0.3125 Hz, 0–500 Hz,
single force reference, unless stated otherwise.

### SP-01 — old T300 plain / PLA auxetic (folder `SP-01 -core mass less`)

- **Identity:** DERIVED.
  - The label reads "500x500 mm … / Plain fiber / Auxetic / DP420" (first line partly illegible). It
    carries no number; numbering began after 2026-08-03.
  - Folder, file names, PSV header and Testlab project all say SP01.
  - The spec experimental table **equals** the PolyMAX set `Processing_nice` exactly.
  - The LMS summary column is "SP1 (old)".
- **Geometry:** 502.13 × 499.25 × 2.9; faces 0.45/0.45; core 2.0. Core plan 502.132 × 499.75 is a CAE
  sketch (CARBON-5D), not a measurement.
- **Mass:** faces 177 / 177; core 145.3; without adhesive 499 (faces + core = 499.3); adhesive 48.9 /
  41.79, calculated 90.69; finished 588.4.
- **Face:** old T300 plain. Constants are template: E1 = E2 52 000, E3 6 700, ν12 0.05, G12 4 500,
  G13 = G23 2 200 MPa, ρ 1.57e-9.
- **Core:**
  - PLA auxetic, DP420. Grade "PLA Light" is DERIVED: an archived CARBON-5D note citing an earlier HUMAN
    statement, in no spec.
  - Core mass / panel area 579.6 g/m² (DERIVED).
  - PLA template constants.
- **Experiment:** raw 260624 (`snadwich`); PolyMAX `SP01_polymax.unv` (zip) with sets Processing_nice 9,
  Processing (1) 9 and Processing 21 modes. Not governed.
- **FE:**
  - Store: CAE + JNL.
  - `C:\temp\SP-01.inp/.odb`: its `.dat` eigenfrequencies equal the spec Abaqus column (24.147 …
    221.13 Hz). Not governed.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION.

### SP-02 — old T300 plain / PLA honeycomb (folder `SP-02`)

- **Identity:** **DERIVED, resolved from records** (§7). The label reads "500x500 / Plain fiber / honey
  comb / DP420" (no number).
- **Geometry:**
  - 515 × 510 × 2.9; faces 0.45/0.45; core 2.0.
  - The FE orientation (horizontal 510 = X, vertical 515 = Y) is fixed from the frame aspect.
- **Mass:** faces 175.60 / 175.60; core 144.58; without adhesive 495.78; adhesive 44.58 / 45.77,
  calculated 90.35 (real not recorded); finished 582.71.
- **Face:**
  - Old T300 plain, constants template, ρ 1.57e-9.
  - The SP02_Modal_V02 INP uses the same values.
- **Core:**
  - PLA honeycomb, DP420. Grade "non-Light PLA" is DERIVED (CARBON-5D note).
  - Core mass / panel area 550.5 g/m² (DERIVED).
  - The spec PLA density 9.01e-10 is copied from SP-01; the INP uses 1.0475e-9.
- **Experiment:**
  - Raw 260803 retry.
  - PolyMAX `SP02_polymax_retry_260803.unv` (Testlab project `SP02_…_260715`): **governed set `Bravo (1)`,
    9 modes**, fixture `SP02/bravo-1`. A byte-identical copy is in the zip.
  - The spec experimental table (28.1903 … 214.261 Hz) is a different, earlier fit (the LMS
    "500x500 honeycomb 420" column).
- **FE:**
  - `SP02_Modal_V02` is the **governed M3 forward model** (INP sha `574ae78a…`).
  - V01 has identical eigenfrequencies; CAE/JNL are also present.
  - The spec Abaqus column equals V01/V02.
- **Registration:**
  - Legacy `9bf736d3…` is historical only (physically inconsistent: median 28.9 mm, max 54.1 mm).
  - Physical `9b63f6c8…` is REVIEW_READY.
  - UNV/physical distortion: x 1.0917, y 0.8178.
  - `registration_limited` False.
  - Open items: the face convention (TOP by convention); the fixture still references the legacy
    registration; the passport `physical_specimen_id` is null.
- **Strict pairs:** physical FROZEN (2,8), (4,10), (7,13). Validation holdout R3; 2 fit rows; condition
  number 6.1.
- **Status:** NEEDS_GOVERNANCE.

### SP-03 — old T300 twill / PLA auxetic (folder `SP-03`)

- **Identity:** DERIVED.
  - The label reads "500x500 / Twill fiber / Auxetic core / DP420" (no number).
  - Testlab project SP03; LMS column "SP3 TWILL".
- **Geometry:** 515 × 510 × 2.9; faces 0.45/0.45; core 2.0. Manufactured 25/07/2026.
- **Mass:** faces 165 / 165.8; core 178.6; without adhesive 509.4; adhesive 44.1 / 43.89, calculated
  87.99; finished 595.7.
- **Face:** old T300 **twill**. Constants UNKNOWN (spec table blank; no measured twill constants exist).
- **Core:** PLA auxetic, DP420, grade UNKNOWN. 680.0 g/m² (DERIVED). PLA template constants.
- **Experiment:** raw 260803; PolyMAX (zip) with sets Bravo_results 11 and 9 modes, Processing 12.
- **FE:** none found.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION. Twill family only.

### SP-04 — old T300 plain 0.25 / TPU honeycomb (folder `SP-04`)

- **Identity:** CONFIRMED. The label reads "310x310 / Honeycomb / TPU / DP420 / **SP-04**".
- **Geometry:**
  - 302 × 297.5 × 2.8; faces 0.25/0.25; core 2.3.
  - The HUMAN local-variation statements do not cover this old ~0.25 stock.
- **Mass:** faces 30.8 / 30.75; core 63.38; without adhesive 124.93; adhesive 24.46 / 26.06, calculated
  50.52; finished 174.03.
- **Face and core constants:** UNKNOWN.
- **Core:** TPU honeycomb, DP420. 705.4 g/m² (DERIVED).
- **Experiment:** raw 260822 (0–1000 Hz); PolyMAX (zip) with sets nice / nice (1) / nice (2) of 7–8
  modes, polymax 19, Processing 16.
- **FE:** candidates `C:\temp\HONEYCOMB_MODAL_302x297p5_NSM_172g_v01` and `MODAL_HONEYCOMB_302x297p5_NSM`.
  They are linked by file name only (plan size and 172 g), so the association is AMBIGUOUS.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION.

### SP-05 — old T300 plain 0.25 / TPU auxetic (folder `SP-05`)

- **Identity:** DERIVED.
  - The label reads "300x300 / Plain Fiber / Auxetic core (TPU) / DP420" (no number).
  - The spec experimental table equals PolyMAX `Processing_nice` exactly, and LMS column 6.
- **Geometry:** 301.14 × 302 × 2.55; faces 0.245/0.245; core 2.35; total before glue 2.84.
- **Mass:** faces 31.5 / 31.4; core 54; without adhesive 116.9; adhesive 24.97 / 24.53, calculated 49.5.
  "Total calculated" 166.4 **and** finished 161.34 are both recorded.
- **Face:** template constants, ρ 1.416e-9.
- **Core:** TPU auxetic, DP420. Template isotropic E 85 MPa, ν 0.45, ρ 9.18e-10. 593.8 g/m² (DERIVED).
- **Experiment:** raw 260706a (0–1000 Hz); PolyMAX (zip) with sets Processing_nice 7 and Processing 17.
- **FE:**
  - `SP05_modal.inp/.odb`, CAEs and SATs are in the store.
  - The `.dat` equals the spec Abaqus column.
  - There is **no M3 forward-model manifest**.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION.

### SP-06 — new T300 plain / TPU auxetic, DP190 (folder `SP-06`, spec only)

- **Identity:** CONFIRMED. The label reads "**SP-06** / 300x300 / Plain fiber / Auxetic core (TPU) /
  DP-190".
- **Geometry:** 310 × 314 × 2.75; faces 0.25 / 0.235 (asymmetric); core 2.33.
- **Mass:** faces 33.01 / 32.15; core 60.55; without adhesive 125.65 (faces + core = 125.71);
  adhesive 25.51 (grey) / 23.82 (translucent), calculated 49.33, real 47.2; finished 172.82.
- **Constants:** UNKNOWN.
- **Core:** TPU auxetic. 622.0 g/m² (DERIVED).
- **Experiment:**
  - Raw 260824 (0–1000 Hz), **not in `D:\Snadwich`**. It is in `I:\Sumin`, `C:\temp\12 sampls`
    and the article folder, all identical.
  - PolyMAX (zip) with sets polymax 8, soso 6, Processing 19.
- **FE:** none.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION.

### SP-07 — new T300 plain / TPU honeycomb, DP190 (folder `SP-07`)

- **Identity:** CONFIRMED. The label reads "**SP-07** / 300x300 / Plain fiber / Honeycomb (TPU) / DP-190".
- **Geometry:** 317 × 310 × 2.7; faces 0.235/0.235; core 2.3.
- **Mass:** faces 32.39 / 32.65; core 50.65; without adhesive 115.69; adhesive 23.83 / 24.67, calculated
  48.5; finished calculated 164.19, real 160.79.
- **Constants:** UNKNOWN.
- **Core:** 515.4 g/m² (DERIVED).
- **Experiment:** raw 260824, **30–1000 Hz**; PolyMAX (zip) with sets soso 8 and Processing 14.
- **FE:** none.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION.

### SP-08 — new T300 plain / PLA auxetic (folder `SP-08`)

- **Identity:** CONFIRMED. The label reads "**SP-08** / 500x500 / Plain fiber / Auxetic core (PLA) /
  DP-420". The file names say "TPU"; spec and label say PLA, and spec + label are authoritative.
- **Geometry:** 515 × 520 × 2.5; faces 0.25 / 0.24; core 2.0.
- **Mass:** faces 90.65 / 89.65; core 177.19; without adhesive 357.7 (faces + core = 357.49); adhesive
  43.78 / 44.54, calculated 88.32, real 85.7; finished 445.81, real 443.40.
- **Constants:** UNKNOWN.
- **Core:** 661.7 g/m² (DERIVED).
- **Experiment:** raw 260828; PolyMAX (zip) with set Bravo 10 and Processing variants of 11–31 modes.
- **FE:** none.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION.

### SP-09 — new T300 plain / PLA honeycomb (folder `SP-09`)

- **Identity:** CONFIRMED. The label reads "**SP-09** / 500x500 / Plain fiber / Honeycomb (PLA) /
  DP-420". The file names say "TPU" (see SP-08).
- **Geometry:** 520 × 510 × 2.47; faces 0.235/0.235; core 2.0.
- **Mass:** faces 89.6 / 90.3; core 145.17; without adhesive 325; adhesive 44.87 / 44.23, calculated
  89.1; finished real 410.9, calculated 414.17.
- **Constants:** UNKNOWN.
- **Core:** 547.4 g/m² (DERIVED).
- **Experiment:** raw 260831; PolyMAX (zip) with Processing sets of 9 / 11 / 19 modes.
- **FE:** none.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION.

### SP-10 — old T300 plain / PLA honeycomb (folder `SP-10`)

- **Identity:** CONFIRMED.
  - Both frames show "**SP-10** / 500x500 / Plain fiber / Honeycomb / DP-420".
  - The two sessions agree: first six fitted modes within 1.5 %.
  - LMS column "SP10 (new SP2)".
- **Geometry:** 520 × 515 × 2.8; faces 0.40 / 0.39; core 2.0.
  - **Flag:** the recorded faces sit at the lower end of the HUMAN local range of the old ~0.45 stock.
  - Face masses 161.5 / 163 against 175.6 for SP-02.
- **Mass:** core 145.84; without adhesive 470.34; adhesive 43.20 / 41.52, real 84.72; finished 555.23.
- **Constants:** UNKNOWN.
- **Core:** 544.6 g/m² (DERIVED).
- **Experiment:**
  - Raw 260831, with PolyMAX (zip) sets Bravo 10 and Processing 15.
  - Raw **260911 b_rotated**: 323 points, Δf 0.156 Hz. PolyMAX `SP10_b_polymax.unv` (store) has sets
    Bestttt 13, Nice 14, Nice (1) 12, Processing 15 and Processing_polym 37.
  - **Orientation exception (260911):** the label is at the lower right, written vertically, and a red
    "b-top" mark is at the top edge. The panel was rotated 90° in-plane for that session.
- **FE:** none.
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION. It is the SP2/SP10
  reference scatter partner (SPEC §13).

### SP-11 — old T300 twill bare plate (folder `SP-11`)

- **Identity:** CONFIRMED. The label reads "**SP-11** / 350x347x0.45 / Twill" (D-049, D-057).
- **Geometry:** 350 × 347 × 0.45.
- **Mass:** plate 79.59.
- **Constants:** UNKNOWN. "TWILL carbon test" is an FE sensitivity study, not a measurement.
- **Experiment:**
  - Raw 260824 (0–250 Hz).
  - 260826 a: **120** points, Δf 0.25 Hz, 0–100 Hz.
  - 260826 b_center: Δf 0.25 Hz, 0–100 Hz.
  - PolyMAX `SP11a_polymax.unv` (zip, session a only) with sets Processing 11 and Processing (1) 24.
  - All sessions are reconnaissance only (D-049, D-057); the sessions are mutually inconsistent.
- **FE:** candidate `C:\temp` twill free-free plate study (M40/M60/M80, ±10 % sensitivities), linked by
  name only.
- **Registration:** none.
- **Status:** NOT_APPLICABLE (not an M7 sandwich), OBSERVATION_INSUFFICIENT, NEEDS_GOVERNANCE. M6.1 and
  M6.2 are NOT_AVAILABLE_WITH_CURRENT_SETUP (D-059).

### SP-12 — new T300 plain bare plate (no store folder)

- **Identity:** DERIVED.
  - The Obsidian note "SP-12 — new CFRP plain Panel 300x300" records 310x310x0.245 and a face mass of
    30.1 g.
  - The dashboard row says new CFRP, no core, "500x500" (conflict, §9), production and Abaqus
    "Completed".
  - `C:\temp\12 sampls\results\SP12` is empty.
- **Experiment:** none found anywhere.
- **FE:** none identified.
- **Registration:** none.
- **Status:** OBSERVATION_INSUFFICIENT, NOT_APPLICABLE.
- **Potential role:** the only recorded new-plain bare plate (G12), but it has no experiment.

### SP-13 — old T300 plain / PLA auxetic (folder `SP-13`)

- **Identity:** CONFIRMED.
  - The label reads "**SP-13** / 500x500 / Plain fiber / Auxetic core / DP-420" in both frames (D-063).
  - LMS column "SP13 (new SP1)".
- **Geometry:**
  - 510 × 520 × 2.85; faces 0.425/0.425; core 2.0.
  - Core CAD 514.19 × 512 (CAD, not measured).
- **Mass:**
  - Faces 163.60 / 158.50; core 179.13.
  - Without adhesive 501.44 (faces + core = 501.23).
  - Adhesive 44.1 / 44.91, calculated 89.01, real 83.16.
  - Finished real 584.6, calculated 590.24.
- **Face:** template constants from the INP (ρ 1.429e-9); the spec table is blank.
- **Core:**
  - PLA auxetic, DP420. Grade "non-Light PLA" is DERIVED (CARBON-5D).
  - 675.5 g/m² (DERIVED).
  - INP PLA ρ 1.1212e-9.
  - "Copy of SP-01" is a design copy: the core is 179.13 g against 145.3 g, and the spectra differ.
- **Experiment:**
  - Raw 260909.
  - **PolyMAX of 260909 exists**: `SP13_polymax.unv` in the zip, Testlab project `SP13_…_260909`, sets
    Bravo (1) 9, Bravo 8, re 11, Processing 14. **Conflicts with H9** (§9 C1); not used.
  - Raw 260910 a: 289 points, Δf 0.156 Hz. It is a re-suspension of 260909 (H6, D-063) in the same
    orientation as the Abaqus model (H7).
  - PolyMAX `SP13_a_polymax.unv`: **governed set `Best`, 12 modes** (fixture `SP13/best`).
- **FE:**
  - `SP13_mesh_local_v1_modal` is the **governed M3 forward model** (INP sha `9d410584…`).
  - `SP13_modal` (earlier mesh, same eigenfrequencies); interface variants (central and stiff: INP only;
    compliant: no eigenvalue output); CAE variants; core CAD.
- **Registration:**
  - Legacy `a8970e52…` is historical only.
  - Physical `2eeeaa86…` is **production-ready** (D-062, D-064).
  - Distortion x 1.195, y 0.889.
  - `registration_limited` False.
  - Open items: face convention; the fixture still references the legacy registration.
- **Strict pairs:** 4↔10 and 7↔13 are well conditioned; 1 fit row after the M4.3 holdout.
- **Status:** OBSERVATION_INSUFFICIENT (alone), NEEDS_GOVERNANCE.

### SP-15 — CFRP plain bare plate, facts not recorded (no store folder)

- **Identity:** AMBIGUOUS.
  - The acquisition `SP15_500by500` (PSV, 2026-09-01) and Testlab project `SP15_500by500` exist.
  - The camera frame shows a bare plate **without visible handwriting**.
  - The Obsidian note SP-15 is a copy of the SP-12 note (title "SP-12 … 500x500", SP-12 values).
  - The same `.svd` is stored as `SP15_500by500_bigSP14.svd`.
  - Earlier repository docs call it "SP15 bare CFRP".
- **Geometry, mass, stock and thickness:** not recorded.
- **Experiment:**
  - Raw 260901: 121 points, 0–100 Hz, Δf 0.125 Hz, FRF only (no coherence), **not in `D:\Snadwich`**.
  - PolyMAX (zip) with sets Processing (1) 8 (duplicated pairs) and Processing 3.
- **FE:** `CFRP_PLAIN_520_STAGEA` Stage-A template run in `C:\temp\12 sampls\results\SP15` (not governed).
- **Registration:** none.
- **Status:** NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION, NOT_APPLICABLE.

## 7. SP-02 identity: SP02_IDENTITY_RESOLVED_FROM_RECORDS

**Question:** is the unnumbered panel of the 2026-08-03 frame the physical SP-02 of `SP-02/spec.txt`
(515 × 510 × 2.9 mm, 582.71 g)?
**Answer:** yes, from records alone. Confidence DERIVED (not CONFIRMED).

1. **The project's own result table assigns it.**
   - `I:\Sumin\Updated_260911\Experiment_Freq_damping_LMS.xlsx` and its sharing copy, sheet
     "SPname_files 260909", label their columns "SP2 (old)" and "SP10 (new SP2)".
   - The "SP2 (old)" column is **exactly** the governed fixture set Bravo (1) of the 260803 acquisition:
     28.0062, 74.376, 78.1616, 90.575, 91.9496, 144.763, 202, 208.216, 219.444 Hz.
   - The "SP10 (new SP2)" column is SP-10's own 260831 fit.
2. **The dynamics separate the panels** (records only, no MAC).
   - The SP-10-labelled panel gives the same spectrum on 260831 and 260911: first six fitted modes within
     1.5 %, modes 2–6 within 0.5 %.
   - SP-10 is 1.3–6.1 % higher than the 260803 panel (mode 1: 29.72 vs 28.01 Hz). The 260803 panel is
     therefore not SP-10.
   - Spatially averaged |H1| peaks show the same split: 28.1, 74.4, 78.1, 90.6, 91.9, 144.7 Hz (260803)
     against 29.7, 76.9, 79.7, 92.8, 95.6, 146.6 Hz (SP-10 260831).
   - SP-09, the other 500-class PLA honeycomb, sits far lower (22.6, 51.2, 58.1 Hz).
3. **Label chronology.**
   - Every frame up to 2026-08-03 carries no specimen number: SP-01 (260624), SP-05 (260706), and SP-02
     and SP-03 (260803).
   - Every frame from 2026-08-22 on is numbered.
   - The unnumbered 260803 label follows the convention of its date.
4. **No other candidate.**
   - The 500-class PLA-honeycomb panels in the records are SP-02, SP-09 and SP-10; SP-09 and SP-10 are
     excluded above.
   - The 300-class honeycombs (SP-04, SP-07) do not fit the "500x500" label.
5. **Names and lineage.**
   - Store folder SP-02, PSV file name and header SP02, Testlab project
     `SP02_500by500_Glue420_honeycomb_full_scan_260715`.
   - The spec experimental table equals the LMS "500x500 honeycomb 420" column, an earlier fit within
     0.7 % of Bravo (1) for modes 1–8.

**Limits:**
- The frame cannot tell SP-02 from SP-10 by plan size, because the aspect ratios 515/510 and 520/515 are
  equal.
- The assignment rests on the project's records, not on an independent physical mark.
- Writing `physical_specimen_id` into `SP02.physical.specimen.json` is a protected-file change, so it
  needs SUPERVISOR acceptance.

This supersedes the earlier NEEDS_ONE_HUMAN_CONFIRMATION (EVIDENCE, M6_DECISION_RECORD §18), which
was based on the store-only audit; that record is kept as history.

## 8. Families

| Family | Members | Face | Core / adhesive | Real experiment | Fitted modes | Governed FE | Production physical reg | Family consistency | E_in | G12 | Missing evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **old-T300-plain-0.45** (SPEC "old plain 0.45") | SP-01, SP-02, SP-10, SP-13 | old T300 plain, nominal 0.45 (SP-13 0.425; SP-10 0.40/0.39 flagged) | PLA auxetic (SP-01 Light, SP-13), PLA honeycomb (SP-02, SP-10); DP420 | all four | SP-02 G, SP-13 G; SP-01, SP-10 U | SP-02, SP-13 | SP-13 (SP-02 REVIEW_READY) | now SP-02 + SP-13 (N = 2; specimen scatter mixed with core topology); SP-10/SP-01 after governance | SP-02 + SP-13 (3 fit rows, rank 2) | BARE_PLATE_REQUIRED (no old-plain bare plate exists) | SP-02 acceptance and production wiring; SP-10/SP-01 FE + registration + governance; Σ_setup measured |
| **old-T300-twill-0.45** (SPEC "twill 0.45") | SP-03, SP-11 (bare) | old T300 twill 0.45 | PLA auxetic / none | both | U (SP-03; SP-11 session a) | none | none | no | no | BARE_PLATE_REQUIRED; SP-11 blocked (D-057, D-059) | twill constants, FE, registration, consistent SP-11 sessions |
| **old-T300-plain-0.25** (not in SPEC §13) | SP-04, SP-05 | old T300 plain 0.25 / 0.245 | TPU honeycomb / TPU auxetic; DP420 | both | U | none (SP-05 FE ungoverned) | none | no | no | BARE_PLATE_REQUIRED | FE (SP-04), M3 manifests, registrations, TPU constants |
| **new-T300-plain-0.25** (SPEC "new plain 0.25: SP8, SP9, …") | SP-06, SP-07, SP-08, SP-09, SP-12 (bare) | new T300 plain 0.235–0.25 | TPU auxetic/honeycomb (DP190); PLA auxetic/honeycomb (DP420) | SP-06 … SP-09 | U | none | none | no | no | BARE_PLATE_REQUIRED; SP-12 bare plate has no experiment | FE for all; registrations; SP-12 experiment; mixed core/adhesive within the family |
| **unassigned** | SP-15 (bare) | not recorded | none | yes | U | none | none | no | no | n/a | all physical facts |

Different face families are never merged. Within old-plain-0.45, the core topology differs (honeycomb
vs auxetic). Within new-plain-0.25, the core material (PLA/TPU) and the adhesive (DP420/DP190) differ.

## 9. Contradiction audit

| # | Catalog finding | Conflicting record | Class |
|---|---|---|---|
| C1 | A Testlab PolyMAX fit of SP-13 **260909** exists: `SP13_polymax.unv` in `I:\Sumin\SPname_files_260909_polymax.zip` (project `SP13_…_260909`, set Bravo (1), 9 modes; tabulated in the LMS sheet "SP13 (new SP1)") | HUMAN H9 / D-064 / D-063 / STATUS: "no PolyMAX fit of 260909" | **REAL_CONFLICT**: nothing changed; Σ_setup stays provisional 0.3 %; question Q1 |
| C2 | SP-10 260911 "b_rotated": label rotated 90°, not at the physical top | HUMAN general practice "label at physical TOP" | **REAL_CONFLICT** (one session, explicitly named "rotated"; SP-10 is not governed) |
| C3 | SP-06 has an acquisition and a PolyMAX export (outside the store) | SNADWICH_INVENTORY: "SP-06 none / INSUFFICIENT" | STALE_DOC |
| C4 | PolyMAX exports exist for SP-01, 03–09, 10 (260831), 11a, 13 (260909) and 15 | SNADWICH_INVENTORY: fitted modes only SP-02, SP-10, SP-13 | STALE_DOC (store-only audit) |
| C5 | `SP11a_polymax.unv` exists | D-057 "(dataset 58 only; no dataset 55)"; inventory "fitted SP-11 modes NOT_AVAILABLE" | STALE_DOC; "no **governed** fitted set" (D-057) remains true |
| C6 | SP-12 is recorded (vault note, dashboard); SP-15 has an acquisition | SNADWICH_INVENTORY "There is no SP-12 folder" (true for the store only) | STALE_DOC |
| C7 | PLA grade recorded second-hand: SP-01 PLA Light, SP-02/SP-13 non-Light (CARBON-5D citing CARBON-3A) | SNADWICH_INVENTORY "PLA grade … not recorded" | STALE_DOC |
| C8 | SP-07 raw 30–1000 Hz; SP-11 260826 sessions Δf 0.25 Hz, 0–100 Hz, session a 120 points | SNADWICH_INVENTORY "0–1000 Hz"; default 121 points / 0.3125 Hz | STALE_DOC |
| C9 | SP-13 remount documented (H6, D-063) | SNADWICH_INVENTORY NOT_AVAILABLE "documented remounts" | EXPECTED_HISTORICAL |
| C10 | SP-02 identity resolved from records (§7) | EVIDENCE / M6_DECISION_RECORD §18 / STATUS `sp02_registration_gate.identity`: NEEDS_ONE_HUMAN_CONFIRMATION | EXPECTED_HISTORICAL (store-only audit; pending SUPERVISOR) |
| C11 | Spec files record plan, masses and face thickness | `SP02.specimen.json`, `SP13.specimen.json`: "not recorded in accepted evidence (to be measured…)"; `SP13.physical`: face thickness "not recorded" | STALE_DOC (protected passports, not edited; values AVAILABLE_NOT_YET_GOVERNED) |
| C12 | `scale_rel` 0.002 from H8 | D-062: `scale_rel` NOT_AVAILABLE | EXPECTED_HISTORICAL (superseded by D-064) |
| C13 | SP-13 is auxetic (own spec, label, HUMAN) | `SP-01/spec.txt` §9: "SP-13 — CFRP/PLA sandwich panel with honeycomb core" | STALE_DOC (template text in the source spec) |
| C14 | SP-08 and SP-09 cores are PLA (spec and label agree) | File names `…_Auxetic_TPU_…`, `…_Honeycomb_TPU_…` | STALE_DOC (file-name template) |
| C15 | SP-14 note is a byte copy of SP-12; SP-15 note is titled "SP-12 … 500x500" with SP-12 values | Vault notes as specimen records | STALE_DOC (template copies); SP-14/SP-15 facts UNKNOWN |
| C16 | SP-12 note: 300x300 class, 310x310x0.245 | Dashboard: SP-12 "500x500" | UNKNOWN (question Q3) |
| C17 | 14 specimens with records (SP-15 acquired 2026-09-01) | Dashboard "Number of specimens 13" (2026-09-01) | STALE_DOC |
| C18 | Spec PLA density 9.01e-10 (copied from SP-01) | INP 1.0475e-9 (SP-02), 1.1212e-9 (SP-13) | EXPECTED_HISTORICAL (template vs FE value; CARBON-5D) |
| C19 | SP-02 spec experimental table (28.1903 … 214.261 Hz) | Governed set Bravo (1) (28.006 … 219.444 Hz; mode 9 differs 2.4 %) | EXPECTED_HISTORICAL (two different fits; the governed one is Bravo (1)) |
| C20 | Old ~0.25 stock exists (SP-04, SP-05) | HUMAN thickness statements cover old ~0.45 and new ~0.25 only | UNKNOWN (question Q6) |
| C21 | Unnumbered 300×300 records (LMS Sheet1 columns 1–5, 2216 adhesive; June calibration panel 287 × 288) | Dashboard / spec set SP-01 … SP-13 | UNKNOWN (question Q5) |

**No REAL_CONFLICT makes this catalog misleading:**
- C1 is reported with both sides, and nothing is chosen.
- C2 is confined to one ungoverned session.

**Not contradictions:**
- SPEC §13 family lists, ROADMAP M7.2 ("SP1, SP2, SP10, SP13") and the fixture/forward-model hashes all
  agree with this catalog.

## 10. Facts absent from every record (questions for the HUMAN)

Only facts that remain unresolved after the complete audit:

1. **Q1 (M7-relevant, Σ_setup).**
   - `I:\Sumin\SPname_files_260909_polymax.zip` contains `SP13_polymax.unv`: a Testlab PolyMAX fit of
     the SP-13 **260909** session.
   - Details: set "Bravo (1)", 9 modes, 31.64 … 206.15, 212.61, 228.75 Hz. The same values are in the
     LMS summary "SP13 (new SP1)".
   - Is this a valid fit that may be governed for the FREQUENCY_ONLY Σ_setup estimate? Or does H9 ("no
     PolyMAX fit of 260909") stand, for example because this fit was rejected?
2. **Q2 (SP-15).** What is SP-15?
   - Face stock (new/old), weave, thickness, plan size and mass.
   - Is it the same panel as "SP-14 / bigSP14"?
3. **Q3 (SP-12).**
   - Is "310 × 310 × 0.245 mm, 30.1 g" correct? The dashboard says 500x500.
   - Was SP-12 ever tested?
4. **Q4 (SP-14).** Does a physical SP-14 exist?
5. **Q5 (unnumbered 300×300 panels).**
   - Are the five LMS "Sheet1" columns (Auxetic/420, Auxetic/190, Auxetic/2216, Honeycomb/420,
     Honeycomb/190) physical panels outside the SP numbering?
   - The same question applies to the June 287 × 288 mm PLA-auxetic DP190 calibration panel (164 g).
6. **Q6 (old ~0.25 stock).** Does the local face-thickness statement for the ~0.25 mm stock also apply
   to the old ~0.25 sheets of SP-04 and SP-05?

None of these blocks the SP-02 + SP-13 path. Only Q1 touches it, through Σ_setup, which stays
provisional until it is answered.

## 11. One-line summary per specimen

- SP-01 — old T300 plain 0.45 / PLA (Light) auxetic, DP420 / 502.13×499.25×2.9 / 588.4 g / fitted experiment YES (ungoverned) / governed FE NO (INP/ODB in C:\temp) / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-02 — old T300 plain 0.45 / PLA honeycomb, DP420 / 515×510×2.9 / 582.71 g / fitted experiment YES (governed `SP02/bravo-1`) / governed FE YES / physical registration YES (REVIEW_READY) / NEEDS_GOVERNANCE — M7 path with SP-13
- SP-03 — old T300 twill 0.45 / PLA auxetic, DP420 / 515×510×2.9 / 595.7 g / fitted experiment YES (ungoverned) / governed FE NO / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-04 — old T300 plain 0.25 / TPU honeycomb, DP420 / 302×297.5×2.8 / 174.03 g / fitted experiment YES (ungoverned) / governed FE NO (candidate only) / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-05 — old T300 plain 0.245 / TPU auxetic, DP420 / 301.14×302×2.55 / 161.34 g / fitted experiment YES (ungoverned) / governed FE NO (INP/ODB in store) / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-06 — new T300 plain 0.25/0.235 / TPU auxetic, DP190 / 310×314×2.75 / 172.82 g / fitted experiment YES (ungoverned, outside store) / governed FE NO / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-07 — new T300 plain 0.235 / TPU honeycomb, DP190 / 317×310×2.7 / 160.79 g real / fitted experiment YES (ungoverned) / governed FE NO / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-08 — new T300 plain 0.25/0.24 / PLA auxetic, DP420 / 515×520×2.5 / 443.40 g real / fitted experiment YES (ungoverned) / governed FE NO / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-09 — new T300 plain 0.235 / PLA honeycomb, DP420 / 520×510×2.47 / 410.9 g real / fitted experiment YES (ungoverned) / governed FE NO / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-10 — old T300 plain (recorded 0.40/0.39) / PLA honeycomb, DP420 / 520×515×2.8 / 555.23 g / fitted experiment YES (ungoverned, two sessions) / governed FE NO / physical registration NO / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION
- SP-11 — old T300 twill 0.45 bare plate / 350×347×0.45 / 79.59 g / fitted experiment YES (session a, ungoverned; sessions inconsistent) / governed FE NO / physical registration NO / NOT_APPLICABLE, OBSERVATION_INSUFFICIENT, NEEDS_GOVERNANCE
- SP-12 — new T300 plain 0.245 bare plate / 310×310×0.245 (note) / 30.1 g / experiment NONE / governed FE NO / physical registration NO / OBSERVATION_INSUFFICIENT, NOT_APPLICABLE
- SP-13 — old T300 plain 0.425 / PLA (non-Light) auxetic, DP420 / 510×520×2.85 / 584.6 g real / fitted experiment YES (governed `SP13/best`) / governed FE YES / physical registration YES (production-ready) / OBSERVATION_INSUFFICIENT alone, NEEDS_GOVERNANCE — M7 path with SP-02
- SP-15 — CFRP plain bare plate (stock/thickness/size not recorded) / fitted experiment YES (ungoverned, outside store) / governed FE NO / physical registration NO / identity AMBIGUOUS / NEEDS_GOVERNANCE, NEEDS_FORWARD_MODEL, NEEDS_REGISTRATION, NOT_APPLICABLE
