# M9 — Scientific reconciliation of SP-02, SP-03, SP-04, SP-05, SP-10, SP-13

Status: `REVIEW_READY` (branch `analysis/m9-six-specimens`; SUPERVISOR analysis task 2026-10-20, outside the Auto-ID
mini-step sequence).

This is an analysis of recorded data only:

- no FE solve, no Abaqus Python extraction, no Auto-ID / LM;
- no registration, criterion, frozen observation or governed record was changed;
- nothing here is governed evidence, an accepted FIT / HOLDOUT row or an accepted mode pairing;
- INP properties are model inputs, never experimentally determined values.

**Sources.**

| Source | Location / state |
|---|---|
| Inventory v2 | `external_models/v2_20261019` |
| Excel copies | `excel_copies/20261019` |
| Specimen catalog | the accepted `docs/auto_id/specimen_catalog.json` (D-065) |
| PolyMAX zip | `I:\Sumin\SPname_files_260909_polymax.zip`; the members were extracted as copies and their SHA-256 equals the catalog |
| Governed records | `docs/auto_id/specimens`, `forward_models`, `registration_evidence` |

Derived arithmetic: `runs/m9/m9_tables.json`; PolyMAX sets: `runs/m9/polymax_sets.json`.

## 1. Verdicts

The verdict depends on what the data are used for, so there are two columns: comparison with Abaqus, and Auto-ID
(material identification).

| Specimen | Comparison with Abaqus | Auto-ID | Reason |
|---|---|---|---|
| **SP-02** | **READY_FOR_COMPARISON** | governed (historical M7, D-077 `NO_GLOBAL_PARAMETER_VALUE`) | accepted model, governed PolyMAX and accepted registration; the control regression reproduces the accepted rows (§4). The new ODB `SP02_NSM_CORE_NEWCFRPE1E2` is DIAGNOSTIC_ONLY until its FE frame is verified against the accepted measured surface |
| **SP-13** | **READY_FOR_COMPARISON** | governed (as SP-02) | the same: R1 / R2 MAC 0.958 / 0.947 reproduced in the real GUI on 19.10. The new models (another mesh) are DIAGNOSTIC_ONLY |
| **SP-10** | **DIAGNOSTIC_ONLY** | **MISSING_EVIDENCE** | PolyMAX of two sessions exists; there is no physical registration and no governed record (§6) |
| **SP-03** | **DIAGNOSTIC_ONLY** | **MISSING_EVIDENCE** | PolyMAX shapes exist in the zip (121 points, z), but there is no physical registration, the twill constants are blank and the stock differs |
| **SP-04** | **DIAGNOSTIC_ONLY** | **MISSING_EVIDENCE** | PolyMAX in the zip; LMS remark "not good"; TPU and old 0.25 mm carbon constants unknown; adhesive is 29 % of the mass |
| **SP-05** | **DIAGNOSTIC_ONLY** | **MISSING_EVIDENCE** | PolyMAX in the zip; the same unknowns as SP-04; the Excel damping is SP-04's (§5.3); mass 166.4 g calculated against 161.34 g measured |

**Correction to the inventory of 19.10:** SP-03, SP-04, SP-05 and SP-10 260831 **do have PolyMAX fitted modes**
(dataset 55). They are in the PolyMAX zip in the `sumin` store, not in `C:\temp` or `D:\Snadwich`. They are not in a
governed store, and none of them has a physical registration.

## 2. Unified specimen table

Physical data come from the passports / accepted catalog. Densities and areal masses are derived as recorded mass /
(plan area × recorded thickness).

| | SP-02 | SP-03 | SP-04 | SP-05 | SP-10 | SP-13 |
|---|---|---|---|---|---|---|
| Plan, mm | 515×510 | 515×510 | 302×297.5 | 301.14×302 | 520×515 | 510×520 |
| Total thickness, mm | 2.9 | 2.9 | 2.8 | 2.55 | 2.8 | 2.85 |
| Face stock / weave | old T300 plain | old T300 **twill** | old T300 plain | old T300 plain | old T300 plain | old T300 plain |
| Face t top / bottom, mm | 0.45 / 0.45 | 0.45 / 0.45 | 0.25 / 0.25 | 0.245 / 0.245 | **0.40 / 0.39** | 0.425 / 0.425 |
| Face mass top / bottom, g | 175.6 / 175.6 | 165 / 165.8 | 30.8 / 30.75 | 31.5 / 31.4 | 161.5 / 163 | 163.6 / 158.5 |
| Face areal mass, g/m² | 668.6 | 628 / 631 | 343 / 342 | 346 / 345 | 603 / 609 | 617 / 598 |
| Face density (derived), g/cm³ | 1.486 | 1.396 / 1.403 | 1.371 / 1.369 | 1.414 / 1.409 | 1.508 / 1.561 | 1.452 / 1.406 |
| Core | PLA honeycomb 2 mm | PLA auxetic 2 mm | TPU honeycomb 2.3 mm | TPU auxetic 2.35 mm | PLA honeycomb 2 mm | PLA auxetic 2 mm |
| Core mass, g (g/m²) | 144.58 (551) | 178.6 (680) | 63.38 (705) | 54 (594) | 145.84 (545) | 179.13 (676) |
| Adhesive (DP420), g (g/m²; share of mass) | 90.35 (344; 15.5 %) | 87.99 (335; 14.8 %) | 50.52 (562; **29.0 %**) | 49.5 (544; **30.7 %**) | 84.72 (316; 15.3 %) | 83.16 (314; 14.2 %) |
| Finished mass, g | 582.71 | 595.7 | 174.03 | 161.34 (calculated 166.4) | 555.23 | 584.6 (calculated 590.24) |
| Accepted FE model | `SP02_Modal_V02` | — | — | — | — | `SP13_mesh_local_v1_modal` |
| Latest user model | `SP02_NSM_CORE_NEWCFRPE1E2` | `SP03_NEWCFRP_NSM` | `SP04_CFRP_E1=E2`, `SP04TPU320` | `SP05_FreeFree` | `SP10_NEW_E1=E2_NSM_DENSITY` | `SP13FINAL` (= `SP13NEWE`) |
| FE total mass against measured | V02 −0.10 %, new +0.01 % | +0.30 %, new +0.01 % | −0.01 % | 0.00 % | −0.02 %; **`SP_10` +5.1 % (an SP-02 model, not SP-10)** | accepted −0.02 %; FINAL −0.03 %; shaker models **+27.5 %** (+161 g) |
| Experimental modal data | PolyMAX retry 260803 Bravo(1), 9 modes, 121 pt, governed | PolyMAX zip Bravo_results(1), 9 modes, 121 pt | PolyMAX zip "nice (2)" / "nice (1)", 7 / 8 modes, 121 pt | PolyMAX zip "Processing_nice", 7 modes, 121 pt | 260831: PolyMAX zip Bravo, 10 modes, 121 pt; 260911 b (rotated 90°): `SP10_b_polymax` "Bestttt", 13 modes, 323 pt | 260910 a: `SP13_a_polymax` Best, 12 modes, 289 pt, governed; 260909: Bravo(1), 9 modes, 121 pt, governed |
| Physical registration | accepted (`9b63f6c8…`) | none | none | none | none | accepted (`2eeeaa86…`) |

Every FE model calibrates its total mass to the measured mass within 0.3 %, through face density and non-structural
mass. The exceptions are `SP_10` (an SP-02 mesh and mass) and the SP-13 shaker models.

All experimental data are out-of-plane (z) on the measured face. All models use mm / tonne / s / MPa.

## 3. Carbon properties

### 3.1 Values

| Specimen / model | E1 / E2, MPa | E3 | G12 | G13 = G23 | ρ, g/cm³ (model) | E1·t, N/mm |
|---|---|---|---|---|---|---|
| Excel "Карбон", old plain 0.45 (effective, "not a test result") | 52 000 / 52 000 | 8 500 | 4 500 | 3 000 | — | 23 400 (t 0.45) |
| SP-02 accepted `SP02_Modal_V02` | 52 000 / 52 000 | 6 700 | 4 500 | 2 200 | 1.570 | 23 400 |
| SP-02 `SP2job` (= Excel "Abaq Freq") | 52 000 / 52 000 | 8 500 | 4 500 | 3 000 | 1.570 | 23 400 |
| SP-02 `500x500newpropertySP02` | 46 000 / 37 800 | 8 500 | 6 000 | 3 000 | 1.570 | 20 700 |
| SP-02 `SP02_NSM_CORE_NEWCFRPE1E2` | 54 400 / 54 400 | 8 500 | 4 500 | 3 000 | 1.486 (= measured) | **24 480** |
| SP-03 `SP03_FreeFree_Modal` → `SP03_NEWCFRP_NSM` (twill) | 52 000 → 54 400 | 8 500 | 4 500 | 3 000 | 1.400 | 23 400 → **24 480** |
| SP-04 `Honeycomb_TPU_FreeFree` → `SP04_CFRP_E1=E2` | 46 200 / 37 800 → 46 200 / 46 200 | 8 500 | 6 000 | 3 000 | 1.280 (measured 1.37) | 11 550 |
| SP-05 `SP05_FreeFree` (`SP05_modal`) | 46 200 / 37 800 (52 000) | 8 500 (6 700) | 6 000 (4 500) | 3 000 (2 200) | 1.362 (1.416) | 11 319 (12 740) |
| SP-10 `SP10nemash63000` → `SP10_NEW_E1=E2_NSM_DENSITY` | 63 000 → **62 800 (bottom) / 61 300 (top)** | 8 500 | 5 400 | 3 000 | 1.561 / 1.508 (= measured) | 24 490 / 24 520 |
| SP-13 accepted `SP13_mesh_local_v1_modal` | 52 000 / 52 000 | 6 700 | 4 500 | 2 200 | 1.429 | 22 100 |
| SP-13 `SP13FINAL` | 57 600 / 57 600 | 8 500 | 4 500 | 3 000 | 1.414 / 1.460 (= measured) | **24 480** |

Further SP-13 variants:

- `SP13E1E2`: 54 900 / 60 400;
- `SP13G9000*`: G12 9 000;
- `SP13NEWPLA`: PLA ×2;
- `SP13ANGLE`: faces rotated +10°.

Every face is one homogenised solid layer with its 0/90 axes on the global X / Y.

### 3.2 Why the carbon values differ

1. **Model tuning and thickness dependence, not independent material measurement.** The nominal old plain stock
   appears with E between 52 000 and 63 000 MPa, while the latest models (including the distinct twill SP-03) keep
   almost the same face membrane stiffness: **E·t ≈ 24 480 N/mm**. The inverse E-versus-t pattern is consistent with
   compensation for recorded face thicknesses (0.45 / 0.425 / 0.40 / 0.39 mm), but it does not establish that the
   underlying materials are identical.
   Sandwich frequencies depend strongly on E·t and face spacing; E and t cannot be reliably separated by these
   frequency fits alone without independent, well-characterised thickness and model-form inputs. This is a practical
   limitation of the present evidence, not a proof of mathematical non-identifiability. SP-03 is twill and cannot be
   classified as the same carbon stock on the basis of E·t.
2. **Lowest-frequency discrepancy; cause not yet established.** In the present frequency-by-rank comparisons for
   PLA-core panels the lowest listed FE elastic frequency is 16–28 % below the experimental one. Those entries are
   not all MAC-confirmed correspondences, so first verify the modal branch / physical correspondence:

   | Specimen | First experimental mode against FE |
   |---|---|
   | SP-02 | −15.8 % |
   | SP-03 | −17.1 % |
   | SP-10 | −18.4 % |
   | SP-13 accepted model | −28.0 % (−17.2 % with the shaker model) |

   The repeated discrepancy makes core shear, adhesive/bonding representation, face orientation and test-fixture
   dynamics worth testing as competing explanations; it does not identify one cause. The Excel "Карбон" sheet notes
   that G12 values of 6 500–9 300 MPa would be "needed" in its effective fits, but this does not prove core
   compensation. D-077 separately records the family-consistency FAIL for SP-02 + SP-13.
3. **Face areal mass differs within the same stock.** SP-02 668.6 g/m², against 598–631 g/m² for SP-03, SP-10 and
   SP-13. SP-02 is 6–11 % heavier per area: thicker sheet or more resin. The derived densities spread
   1.40–1.56 g/cm³.
4. **The 0.25 mm stock (SP-04, SP-05) has no estimate.**
   - The models use 46 200 / 37 800 MPa and G12 6 000, of unrecorded origin; the same set appears in
     `500x500newpropertySP02`.
   - SP-04's model density is 1.28 against 1.37 derived.
   - Excel "Карбон" gives no value for this stock.
5. **Twill (SP-03).** Its model uses the plain-weave constants; the passport table is blank.
6. **Two template sets for E3 / G13 / G23** (6 700 / 2 200 / 2 200 against 8 500 / 3 000 / 3 000). According to the
   Excel note their influence is below 0.04 %; they are not identifiable from these tests.
7. **Orientation.** All models assume a balanced 0/90 weave aligned with the panel edges. `SP13ANGLE` (+10°) raises
   mode 1 from 22.61 to 23.48 Hz (+3.9 %), so the fibre angle relative to the edges matters for torsion. It is not
   recorded for any panel.

## 4. Control regression: SP-02 and SP-13 on the accepted models

The accepted models are identified by SHA-256 of the forward-model INP:

| Specimen | Accepted INP | Location |
|---|---|---|
| SP-02 | `SP02_Modal_V02.inp` (`574ae78a…`) | `C:\temp\12 sampls\results\SP02`; also in the v1 copies |
| SP-13 | `SP13_mesh_local_v1_modal.inp` (`9d410584…`) | `SP13_mesh_local_v1_modal` folder |

The new ODBs are different models and do not replace them.

Store-gated tests: 103 tests OK, 0 skipped, on 20.10:

- `test_experiment_fixture_regression`, `test_m2_stage_gate`, `test_sp02_physical_registration`,
  `test_sp13_physical_registration`, `test_g2d1_governed_registration`, `test_m4_3_real_classification`;
- `test_m7_campaign` (active chains reproduce the accepted rows, pinned manifest `e4ba607f…`) and `test_m7_entry_wiring`.

The real-GUI SP-13 comparison of 19.10 on the accepted ODB gave R1 0.9585 and R2 0.9469.

Accepted strict pairs (governed PolyMAX against the accepted FE model):

| Specimen | Row | Role | Exp mode / Hz | FE mode / Hz | Error |
|---|---|---|---|---|---|
| SP-02 | R1 | FIT | 2 / 74.376 | 8 / 75.241 | +1.16 % |
| SP-02 | R2 | FIT | 4 / 90.575 | 10 / 89.327 | −1.38 % |
| SP-02 | R3 | HOLDOUT | 7 / 202.000 | 13 / 207.43 | +2.69 % |
| SP-13 | R1 | FIT | 4 / 94.399 | 10 / 85.851 | −9.06 % |
| SP-13 | R2 | HOLDOUT | 7 / 205.649 | 13 / 199.98 | −2.76 % |

For SP-02 the Excel rank alignment (`SP2job`) agrees with these pairs at modes 2, 4 and 7 (+1.16 / −1.37 / +2.70 %). For
SP-13 the Excel column is `SP13FINAL`, not the accepted model: its rank-4 value 89.72 Hz (−4.95 %) is not the accepted
R1.

## 5. Contradictions from the inventory, checked

### 5.1 SP-10 rows 10–12

- **Findings.**
  - All completed SP-10 jobs requested 15 modes (9 elastic).
  - The SP-10 CAE journals also contain `numEigen=25`.
  - The job name `SP10` was submitted 7 times, and its stored result has 15 modes.
- **Conclusion.** The FE values of rows 10–12 (228.43 / 266.44 / 268.56 and 226.95 / 265.04 / 267.14) come from an
  overwritten run and are **not reproducible** from the stored results. They are not used.
- **Rank alignment.** Row 11 also shows that rank alignment fails at higher modes: +17 % against the experimental
  227.28 Hz.
- **Experimental side.** Rows 10–12 are PolyMAX "Bestttt" of session 260911 b: 224.854, 227.276, 261.563 Hz.

### 5.2 SP-13 suspension / shaker modes

`SP13Spring0_1` and `SP13_SHAKER_*` add:

- a lumped "shaker" mass of 160 g on an axial stinger spring of 1 336 N/mm;
- a 1 g sensor mass;
- a shaker suspension of 5.6 N/mm;
- four support springs of 0.1 N/mm (0.08 in `STRINGS4`).

None of these values is documented as measured, and `suspension_max_hz` is null in both accepted passports.

The Excel column "Abaq+shaker+string" is `SP13Spring0_1` after its 6 lowest modes: 3 rigid modes and the suspension
modes 5.48, 7.01 and 18.16 Hz. Its rank 7 (155.58 Hz, a mode the attachment model creates) stands beside the
experimental 205.65 Hz (−24 %), so the rank alignment is broken from row 7 on.

The attachment model moves mode 1 from −28 % to −17 %. Whether a 160 g armature on a stiff stinger is physical is
**unverified**.

### 5.3 Damping SP-04 / SP-05

The Excel SP-05 damping equals the LMS SP4 column value for value (0.0063538 … 0.010164). The LMS SP5 column is
0.0035503, 0.0031021, 0.0072477, 0.0049421, 0.0025674, 0.014665, 0.013501 (0.26–1.47 %), which is what the tracker
note states. **The Excel SP-05 damping is a copy error**; the LMS values are the source.

### 5.4 PolyMAX against LMS (SP-13, SP-10)

These are **different sessions, not conflicting fits**:

- **SP-13:** 260909 (Bravo(1), 121 pt; tracker "Частоты LMS") and 260910 a (Best, 289 pt; `results sadwich`). This is
  the accepted re-suspension H6.
- **SP-10:** 260831 (Bravo, 121 pt) and 260911 b (Bestttt, 323 pt; the panel was rotated 90°).

The "swapped" modes 2 / 3 in the LMS sheet are the user's shape labels, not a sort order.

Repeatability by rank (frequency only; same specimen, remounted):

| Pair | Modes 1–8, % |
|---|---|
| SP-13 260909 → 260910 a | −0.69, +0.03, +0.08, −0.03, −0.03, −0.24, −0.24, +0.03 |
| SP-10 260831 → 260911 b | −1.47, +0.04, +0.13, +0.21, −0.34, −0.44, +0.08, −0.29 |

Mode 1 (torsion) is the most mount-sensitive: 0.7–1.5 %.

Specimen to specimen (SP-02 → SP-10 b, nominal copies, frequency by rank, no MAC): +4.6, +3.3, +2.0, +2.5, +3.6, +0.9,
+2.4, +2.6, +0.2 %. SP-10 is 4.7 % lighter and has thinner faces.

### 5.5 Carbon in Excel against the INPs

Section 3. The Excel "E1=E2 для модели" (52 000) is not the value of the latest models (54 400–63 000). The Excel itself
labels its constants as effective model constants, not test results.

## 6. SP-10 as a candidate for a new physical comparison

**What exists:**

- the passport;
- two PolyMAX sessions with stored PSV camera frames (`.svd`);
- in the catalog, the frame of session b shows the label at the lower right, written vertically, and a red "b-top"
  mark at the top edge;
- FE models whose total mass equals the measured mass.

**What is missing for an independent physical registration** (the accepted M2.3 / CORE-E2E-C evidence standard;
frequency proximity is never used):

1. **The scan window in physical coordinates.** For SP-02 and SP-13 it was reconstructed from the PSV frame (panel
   edges fitted, scale from the measured plan). The method is recorded in the accepted reconstruction records, but it
   has **not been done for SP-10**: neither for session 260831 (121 pt) nor for session 260911 b (323 pt).
2. **The in-plane orientation of the panel and its honeycomb lattice relative to the FE axes.**
   - The FE model (an SP-02 copy) has faces 515 (X) × 520 (Y) mm and the SP-02 core part of 510 × 515 mm.
   - The panel is near-square (520 / 515, 1 %).
   - Session b is rotated 90°.
   - The four sign alternatives must be resolved by a physical statement (corner-A marker or a HUMAN orientation
     record such as SP-13's H7, which links the label and the lattice to the model). No such record exists for SP-10;
     for SP-02 a documented convention was used.
3. **The FE frame.** The SP-10 meshes are new (2 262 611 nodes). The evidence must be stated for this FE geometry
   identity; the SP-02 registration cannot be reused.
4. **The measured face** (label side) bound to FE TOP or BOTTOM. The faces are 0.40 and 0.39 mm, almost symmetric.

**What blocks Auto-ID for SP-10.** Beyond the registration, every SPEC v1.2 §11 record is missing:

- physical passport (`specimens/SP10.physical.specimen.json`);
- fixture with pinned UNV / INP / ODB;
- forward-model manifest;
- solver profile;
- an M3-rendered archived baseline solve, its shape pack and the M2.4 registration evidence;
- then the strict freeze.

In addition:

- the SP-10 models were tuned against SP-10's own frequencies (E 61 300–63 000), so they cannot be an independent
  start;
- the FE rows 10–12 are not reproducible;
- the face thickness uncertainty enters E directly (§3.2.1).

## 7. SP-03, SP-04, SP-05 by frequency

Rank alignment as the user typed it, not a MAC pairing (FE / experiment − 1, %):

| Specimen (FE column → job) | Ranks 1–9 |
|---|---|
| SP-03 C `SP03_FreeFree_Modal` | −17.3, −2.7, −3.0, −3.3, −4.7, −2.7, −1.1, −2.6, −1.5 |
| SP-03 D `SP03_NEWCFRP_NSM` | −17.1, −0.3, −0.7, −1.5, −3.0, −1.2, +1.2, −0.3, +0.7 |
| SP-04 C `Honeycomb_TPU_FreeFree` | −0.04, +0.9, −0.2, +4.2, +2.6, +3.3, −10.8 |
| SP-05 C `SP05_FreeFree` | +7.8, +0.5, −0.3, +2.3, +6.5, +3.4, −9.0 |

For SP-04 / SP-05, rank 7 is a non-standard shape (LMS "Fig3"). For a TPU core the core and the adhesive (29–31 % of
the mass) dominate, and both are unknown. With the same faces, the new SP-04 jobs (TPU 160 → 320 MPa) shift the frequencies by
up to +10 % (rank 7: 366.9 → 403.6 Hz), so E_core is the governing unknown there.

## 8. Plan

### 8.1 Data and experiments

| # | Action | Abaqus needed | Purpose |
|---|---|---|---|
| 1 | Bring the PolyMAX zip members (SP-03 / 04 / 05 / 10 260831) into the curated store as pinned copies; record the set chosen per specimen | no | experimental shapes for SP-03 / 04 / 05 / 10 |
| 2 | SP-10: a HUMAN orientation record per session (which edge is 520 mm, label and "b-top" position, lattice direction against the label, measured face); a corner-A marker or measured scan-to-edge offsets; photographs | no | independent physical registration (§6) |
| 3 | Face thickness maps (≥ 9 points per face) and face areal mass for SP-02, SP-10, SP-13 | no | separate E from t; explain the 6–11 % areal-mass difference of SP-02 |
| 4 | Coupon tests of the face stocks (old plain 0.45, old plain 0.25, twill 0.45): in-plane tensile E1 / E2, areal mass, fibre angle against the edge | no | carbon constants as test results (none exist) |
| 5 | Core and adhesive tests: PLA (printed honeycomb / auxetic) and TPU modulus (DMA or compression); DP420 bond-line thickness / mass | no | the dominant unknown for SP-04 / 05 and the torsion-mode model form |
| 6 | Shaker / suspension record for each session: armature and stinger, attachment point, suspension frequencies (`suspension_max_hz`), drive-point FRF | no | decide whether attachment modelling (§5.2) is physical |
| 7 | Bare face-plate modal tests (SP-11 twill, SP-12) with a single, documented session | no | in-plane G12 of the weave, which sandwich panels cannot give |

### 8.2 Abaqus runs that make scientific sense (none was run; each needs its own authorisation)

1. **Extraction only, no solve.** Abaqus Python on a copy of `SP02_NSM_CORE_NEWCFRPE1E2.odb`. It checks whether its
   measured surface is the accepted SP-02 surface node for node. If so, the accepted calibration can be reused through
   the guided path, and MAC is available for the new SP-02 model.
2. **SP-10 governed baseline**, only after item 8.1-2 and the §11 records: one M3-rendered baseline solve plus E ±5 %
   (3 solves, the D2h / D2i guarded path). This turns SP-10 into a second honeycomb specimen for a specimen-to-specimen
   consistency test with SP-02.
3. **Diagnostic sensitivity study of the low-frequency discrepancy (rank-1, −16…−28 % in the current PLA-core comparisons):**
   - core shear stiffness;
   - explicit adhesive layer / fillets (the `SP13_interface_*` work exists but has no completed jobs);
   - face fibre angle (as `SP13ANGLE`).

   These are diagnostic sensitivity runs, not identification.
4. **Mesh-convergence check of the new SP-10 / SP-13 meshes** against the accepted ones, frequency only.

### 8.3 Runs without scientific value now

- Further manual E tuning per specimen: it absorbs thickness and model-form errors; the E·t of the latest models is
  already constant.
- E1 ≠ E2 or G12 tuning without in-plane tests: G12 is not identifiable from these panels (Excel note, D-077).
- Shaker / spring models with undocumented parameters.
- A six-specimen material campaign. Commonality is not shown: three stocks (old plain 0.45, old plain 0.25, twill),
  two core materials and two topologies; adhesive is 14–31 % of the mass; and SP-02 / SP-13 already fail family
  consistency (D-077).

## 9. Unchanged

- SPEC v1.2, DECISIONS, EVIDENCE, registrations, frozen observations, MAC / pairing rules, thresholds, gates.
- M8 original gate `NOT_MET`; production calibration `BLOCKED / NOT_AUTHORISED`; D-077 `NO_GLOBAL_PARAMETER_VALUE`.
- No original file was changed. No Abaqus, Abaqus Python or LM was run.
