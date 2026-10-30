# PRIORITY-1 — real modal matching and the plate's E1 / E2 / G12 parameter study (RESEARCH_ONLY)

Branch `research/real-modal-matching-202610` from `main` `4abfbca`. Inputs read-only; no Abaqus, solver, LM campaign or Auto-ID; no SPEC / DECISIONS / STATUS / EVIDENCE / registration / gate changed. Scripts: `research/real_modal_matching/` (`inputs.py`, `run_real_matching.py`, `plate_parameters.py`, this file).

**Statuses never claimed here:** no row is MATCH_CONFIRMED (no admissible physical registration exists for these three ROTATED series), and no number is a property of the carbon material.

## 1. What was read

| Specimen | Series | File (SHA-256 vs SOURCE_PROVENANCE.csv) | Set | Records | Points |
|---|---|---|---|---|---|
| PLATE | NEXP29/PLATE300-1MM/S261027-ROTATED | `300by300_plate_only_1mm_ROTATED_Polytec_261027.unv` 76db80aed1b4… MATCH | Polymax_bravo | 11 | 289 |
| SP13 | NEXP29/SP-13/S261028-ROTATED | `SP13_500by500_Glue420_Auxetic_ROTATED_Polytec_261028.unv` 8abf951dba4b… MATCH | polymax_bravo | 12 | 289 |
| SP10 | NEXP29/SP-10/S261029-ROTATED | `SP10_b_rotated_500by500_Glue420_Honeycomb_ROTATED_Polytec_261029.unv` 432adf963085… MATCH | polymax_bravo | 12 | 289 |

| FE source | Content |
|---|---|
| PLATE: M11 `S4R_0875_BASELINE` extracted package (R6) | elastic FE 7–20 (14 modes), shapes on 10 201 nodes |
| SP-13: `SP13_mesh_local_v1_modal` extracted package (M4, verified copy) | elastic FE 7–30 (24 modes), shapes on 1 585 637 nodes |
| SP-10: four own models (`SP10_NEW_E1=E2_NSM_DENSITY` primary, `SP10nemash63000`, `SP10newmash`, `SP10_new_E_NSM_DENS`), `.dat` eigenvalue tables | elastic FE 7–15 only (≤ 220 Hz); **no extracted package: no FE shapes** |

Literature actually applied (repository `References/`, summaries in `docs/literature/`): Allemang 2002 (MAC, close-mode caution) → MAC / AutoMAC thresholds; Brincker et al. 2014 (local correspondence, S2MAC) → two-mode subspace projections for close FE groups; Peeters et al. 2004 (PolyMAX) → fitted dataset-55 records, MPC; Mottershead, Link & Friswell 2011 and Mottershead & Friswell 1993 → secant sensitivity matrix, rank / conditioning, bounded LM with pairing kept by shape; Greś et al. 2021 → MAC values near the thresholds read as uncertain. No other source is used; nothing is attributed to a paper that is not in the folder.

## 2. All frequencies and the FE candidates of each mode (frequency window 15 %, close groups 3 %)

### PLATE-300x300x1mm, 261027 vs M11

| EXP | f_EXP Hz | FE candidates (Δf) | nearest FE | Δf % | shape MAC (research / hypothetical) | cluster / permutation | status |
|---|---|---|---|---|---|---|---|
| 1 | 18.6307 | FE7 19.072 (+2.37 %) | FE7 | 2.37 | FE7 0.905; next FE15 0.338 | — | CANDIDATE_ONLY |
| 2 | 54.6193 | FE8 59.874 (+9.62 %); FE9 62.009 (+13.53 %) | FE8 | 9.62 | FE9 0.605; next FE8 0.566 | two best FE9/FE8 subspace 0.97 | AMBIGUOUS_CLUSTER |
| 3 | 63.495 | FE8 59.874 (-5.70 %); FE9 62.009 (-2.34 %); FE10 71.850 (+13.16 %); FE11 72.190 (+13.69 %) | FE9 | -2.34 | FE20 0.309; next FE11 0.259 | FE FE10/FE11 | NO_MATCH |
| 4 | 66.8467 | FE8 59.874 (-10.43 %); FE9 62.009 (-7.24 %); FE10 71.850 (+7.48 %); FE11 72.190 (+7.99 %) | FE9 | -7.24 | FE11 0.551; next FE17 0.244 | FE FE10/FE11 / subspace FE10/FE11: 0.55 | AMBIGUOUS_CLUSTER |
| 5 | 74.2149 | FE10 71.850 (-3.19 %); FE11 72.190 (-2.73 %) | FE11 | -2.73 | FE10 0.484; next FE15 0.137 | FE FE10/FE11 | NO_MATCH |
| 6 | 112.2655 | FE12 116.580 (+3.84 %) | FE12 | 3.84 | FE12 0.520; next FE17 0.203 | — | NO_MATCH |
| 7 | 145.9357 | FE13 167.490 (+14.77 %) | FE13 | 14.77 | FE14 0.786; next FE18 0.310 | FE FE13/FE14 / subspace FE13/FE14: 0.79 | AMBIGUOUS_CLUSTER |
| 8 | 157.8508 | FE13 167.490 (+6.11 %); FE14 168.608 (+6.81 %); FE15 174.798 (+10.74 %); FE16 179.902 (+13.97 %) | FE13 | 6.11 | FE16 0.427; next FE19 0.379 | FE FE13/FE14; FE FE15/FE16 / subspace FE15/FE16: 0.92 | AMBIGUOUS_CLUSTER |
| 9 | 169.1849 | FE13 167.490 (-1.00 %); FE14 168.608 (-0.34 %); FE15 174.798 (+3.32 %); FE16 179.902 (+6.33 %) | FE14 | -0.34 | FE13 0.260; next FE20 0.185 | FE FE13/FE14; FE FE15/FE16 | NO_MATCH |
| 10 | 180.1363 | FE13 167.490 (-7.02 %); FE14 168.608 (-6.40 %); FE15 174.798 (-2.96 %); FE16 179.902 (-0.13 %) | FE16 | -0.13 | FE15 0.151; next FE16 0.131 | FE FE13/FE14; FE FE15/FE16 | NO_MATCH |
| 11 | 191.6019 | FE13 167.490 (-12.58 %); FE14 168.608 (-12.00 %); FE15 174.798 (-8.77 %); FE16 179.902 (-6.11 %); FE17 213.199 (+11.27 %); FE18 213.953 (+11.67 %) | FE16 | -6.11 | FE18 0.542; next FE19 0.147 | FE FE13/FE14; FE FE15/FE16; FE FE17/FE18 / subspace FE17/FE18: 0.55 | AMBIGUOUS_CLUSTER |

### SP-13, 261028 vs SP13_mesh_local_v1_modal

| EXP | f_EXP Hz | FE candidates (Δf) | nearest FE | Δf % | shape MAC (research / hypothetical) | cluster / permutation | status |
|---|---|---|---|---|---|---|---|
| 1 | 28.8015 | — | FE7 | -21.92 | HYPOTHETICAL_SAME_POINTS: FE7 0.973; next FE16 0.193 | — | NO_MATCH |
| 2 | 73.877 | FE8 72.724 (-1.56 %); FE9 75.951 (+2.81 %) | FE8 | -1.56 | HYPOTHETICAL_SAME_POINTS: FE9 0.462; next FE8 0.186 | — | NO_MATCH |
| 3 | 80.7272 | FE8 72.724 (-9.91 %); FE9 75.951 (-5.92 %); FE10 85.851 (+6.35 %); FE11 87.771 (+8.73 %) | FE9 | -5.92 | HYPOTHETICAL_SAME_POINTS: FE8 0.724; next FE9 0.245 | FE FE10/FE11 | NO_MATCH |
| 4 | 93.5849 | FE10 85.851 (-8.26 %); FE11 87.771 (-6.21 %) | FE11 | -6.21 | HYPOTHETICAL_SAME_POINTS: FE10 0.869; next FE22 0.205 | EXP EXP4/EXP5; FE FE10/FE11 | AMBIGUOUS_CLUSTER |
| 5 | 96.0717 | FE10 85.851 (-10.64 %); FE11 87.771 (-8.64 %) | FE11 | -8.64 | HYPOTHETICAL_SAME_POINTS: FE11 0.879; next FE23 0.182 | EXP EXP4/EXP5; FE FE10/FE11 | AMBIGUOUS_CLUSTER |
| 6 | 149.2211 | FE12 137.985 (-7.53 %) | FE12 | -7.53 | HYPOTHETICAL_SAME_POINTS: FE12 0.784; next FE25 0.297 | — | NO_MATCH |
| 7 | 206.0277 | FE13 199.977 (-2.94 %); FE14 204.857 (-0.57 %); FE15 208.950 (+1.42 %); FE16 216.145 (+4.91 %) | FE14 | -0.57 | HYPOTHETICAL_SAME_POINTS: FE13 0.725; next FE28 0.272 | FE FE13/FE14/FE15 | AMBIGUOUS_CLUSTER |
| 8 | 213.0846 | FE13 199.977 (-6.15 %); FE14 204.857 (-3.86 %); FE15 208.950 (-1.94 %); FE16 216.145 (+1.44 %) | FE16 | 1.44 | HYPOTHETICAL_SAME_POINTS: FE14 0.753; next FE18 0.070 | FE FE13/FE14/FE15 | AMBIGUOUS_CLUSTER |
| 9 | 222.5384 | FE13 199.977 (-10.14 %); FE14 204.857 (-7.95 %); FE15 208.950 (-6.11 %); FE16 216.145 (-2.87 %); FE17 250.096 (+12.38 %); FE18 252.632 (+13.52 %) | FE16 | -2.87 | HYPOTHETICAL_SAME_POINTS: FE15 0.534; next FE16 0.228 | EXP EXP9/EXP10; FE FE13/FE14/FE15; FE FE17/FE18 | AMBIGUOUS_CLUSTER |
| 10 | 228.8839 | FE13 199.977 (-12.63 %); FE14 204.857 (-10.50 %); FE15 208.950 (-8.71 %); FE16 216.145 (-5.57 %); FE17 250.096 (+9.27 %); FE18 252.632 (+10.38 %) | FE16 | -5.57 | HYPOTHETICAL_SAME_POINTS: FE16 0.408; next FE15 0.390 | EXP EXP9/EXP10; FE FE13/FE14/FE15; FE FE17/FE18 | NO_MATCH |
| 11 | 263.0513 | FE17 250.096 (-4.93 %); FE18 252.632 (-3.96 %) | FE18 | -3.96 | HYPOTHETICAL_SAME_POINTS: FE17 0.558; next FE27 0.112 | EXP EXP11/EXP12; FE FE17/FE18 | AMBIGUOUS_CLUSTER |
| 12 | 267.3612 | FE17 250.096 (-6.46 %); FE18 252.632 (-5.51 %) | FE18 | -5.51 | HYPOTHETICAL_SAME_POINTS: FE18 0.512; next FE26 0.136 | EXP EXP11/EXP12; FE FE17/FE18 | AMBIGUOUS_CLUSTER |

### SP-10, 261029 vs SP10_NEW_E1=E2_NSM_DENSITY (.dat)

| EXP | f_EXP Hz | FE candidates (Δf) | nearest FE | Δf % | shape MAC (research / hypothetical) | cluster / permutation | status |
|---|---|---|---|---|---|---|---|
| 1 | 26.5014 | FE7 23.886 (-9.87 %) | FE7 | -9.87 | — | — | FE_SHAPES_UNAVAILABLE |
| 2 | 76.3913 | FE8 76.529 (+0.18 %); FE9 79.572 (+4.16 %) | FE8 | 0.18 | — | — | FE_SHAPES_UNAVAILABLE |
| 3 | 79.8004 | FE8 76.529 (-4.10 %); FE9 79.572 (-0.29 %); FE10 90.785 (+13.77 %) | FE9 | -0.29 | — | FE FE10/FE11 | FE_SHAPES_UNAVAILABLE |
| 4 | 92.3388 | FE9 79.572 (-13.83 %); FE10 90.785 (-1.68 %); FE11 91.986 (-0.38 %) | FE11 | -0.38 | — | EXP EXP4/EXP5; FE FE10/FE11 | FE_SHAPES_UNAVAILABLE |
| 5 | 94.9947 | FE10 90.785 (-4.43 %); FE11 91.986 (-3.17 %) | FE11 | -3.17 | — | EXP EXP4/EXP5; FE FE10/FE11 | FE_SHAPES_UNAVAILABLE |
| 6 | 148.1323 | FE12 146.120 (-1.36 %) | FE12 | -1.36 | — | — | FE_SHAPES_UNAVAILABLE |
| 7 | 207.3311 | FE13 210.880 (+1.71 %); FE14 214.230 (+3.33 %); FE15 220.040 (+6.13 %) | FE13 | 1.71 | — | FE FE13/FE14/FE15 | FE_SHAPES_UNAVAILABLE |
| 8 | 214.439 | FE13 210.880 (-1.66 %); FE14 214.230 (-0.10 %); FE15 220.040 (+2.61 %) | FE14 | -0.1 | — | FE FE13/FE14/FE15 | FE_SHAPES_UNAVAILABLE |
| 9 | 222.2567 | FE13 210.880 (-5.12 %); FE14 214.230 (-3.61 %); FE15 220.040 (-1.00 %) | FE15 | -1.0 | — | EXP EXP9/EXP10; FE FE13/FE14/FE15 | FE_SHAPES_UNAVAILABLE |
| 10 | 228.7088 | FE13 210.880 (-7.80 %); FE14 214.230 (-6.33 %); FE15 220.040 (-3.79 %) | FE15 | -3.79 | — | EXP EXP9/EXP10; FE FE13/FE14/FE15 | FE_SHAPES_UNAVAILABLE |
| 11 | 262.4545 | — | FE15 | -16.16 | — | EXP EXP11/EXP12 | FE_SHAPES_UNAVAILABLE |
| 12 | 266.8519 | — | FE15 | -17.54 | — | EXP EXP11/EXP12 | FE_SHAPES_UNAVAILABLE |

Full rows with the shape descriptors and the reasons: `PLATE_MODAL_MATCHING.csv`, `SP13_MODAL_MATCHING.csv`, `SP10_MODAL_MATCHING.csv`.

## 3. Close groups and permutations

- **PLATE:** experimental none; FE [['FE10', 'FE11'], ['FE13', 'FE14'], ['FE15', 'FE16'], ['FE17', 'FE18']].
- **SP13:** experimental [['EXP11', 'EXP12'], ['EXP4', 'EXP5'], ['EXP9', 'EXP10']]; FE [['FE10', 'FE11'], ['FE13', 'FE14', 'FE15'], ['FE17', 'FE18'], ['FE20', 'FE21', 'FE22', 'FE23'], ['FE24', 'FE25'], ['FE26', 'FE27'], ['FE28', 'FE29', 'FE30']].
- **SP10:** experimental [['EXP11', 'EXP12'], ['EXP4', 'EXP5'], ['EXP9', 'EXP10']]; FE [['FE10', 'FE11'], ['FE13', 'FE14', 'FE15']].
- **FE permutations found by FE-to-FE tracking (plate variants, `PLATE_FE_SENSITIVITY.csv`):** E2 ×0.9 swaps FE10↔FE11, FE13↔FE14 and FE17↔FE18; E1 ×0.9 moves FE14 to FE15; G12 ×2 and ×3 move FE20 to FE19. Matching by mode number would have mixed these branches.
- **Near-degenerate FE8 / FE9 (59.87 / 62.01 Hz):** insensitive to G12 and lost (BRANCH_LOSS) under E1 ×0.9 and E2 ×0.9: the two shapes mix when E1 ≠ E2. Plate EXP2 (54.62 Hz) lies in their span (two-mode subspace 0.97).

## 4. Where a MAC exists and where it may not be computed

- **Admissible MAC: none.** No accepted physical registration applies to any of the three ROTATED series; the `mac_admissible` column is NOT_PERMITTED in every row.
- **PLATE — research MAC (M11 R6.5 method):** the 261016 diagnostic reconstruction (DIAGNOSTIC_ONLY; SCANNER_FACE pending) carried to 261027 by the DERIVED point map id k ↔ id k (owner: same points; geometry: 289/289 ids kept under a −44.17° turn). Invariant to the FE candidates A–D (max difference 7.8e-08); nearest-node vs bilinear transfer differ by ≤ 0.004. Not a registration.
- **SP-13 — HYPOTHETICAL_SAME_POINTS MAC:** the accepted SP-13 frozen registration (session 260910 a) applied to 261028 by point id. Geometry supports it (registered UNV ↔ 260910 re-export: same ids, scale 1.143; 260910 ↔ 261028: 289/289 ids kept under a −45.34° clockwise turn), but the owner has not confirmed the same points for SP-13. Control on the registered session itself: A1→FE7 0.99, A2→FE9 0.60, A3→FE8 0.73, A4→FE10 0.89, A5→FE11 0.89, A6→FE12 0.51 …
- **SP-10 — no MAC:** no extracted FE package (shapes would need Abaqus Python on its ODB: a separate gate); the 260911 b session has 323 points against 289, so no id map either.

### Plate research MAC (rows EXP 261027, columns FE M11)

| EXP | FE7 | FE8 | FE9 | FE10 | FE11 | FE12 | FE13 | FE14 | FE15 | FE16 | FE17 | FE18 | FE19 | FE20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **0.91** | 0.00 | 0.01 | 0.15 | 0.00 | 0.00 | 0.00 | 0.00 | 0.34 | 0.21 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | 0.00 | **0.57** | **0.60** | 0.00 | 0.00 | 0.30 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 |
| 3 | 0.00 | 0.19 | 0.09 | 0.00 | 0.26 | 0.02 | 0.13 | 0.00 | 0.00 | 0.00 | 0.11 | 0.00 | 0.00 | 0.31 |
| 4 | 0.00 | 0.08 | 0.09 | 0.00 | **0.55** | 0.07 | 0.07 | 0.00 | 0.00 | 0.00 | 0.24 | 0.00 | 0.00 | 0.20 |
| 5 | 0.00 | 0.00 | 0.00 | 0.48 | 0.00 | 0.00 | 0.00 | 0.00 | 0.14 | 0.09 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 | **0.52** | 0.00 | 0.00 | 0.00 | 0.00 | 0.20 | 0.00 | 0.00 | 0.00 |
| 7 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.79** | 0.02 | 0.03 | 0.00 | 0.31 | 0.13 | 0.00 |
| 8 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.17 | 0.36 | 0.43 | 0.00 | 0.00 | 0.38 | 0.00 |
| 9 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.26 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.18 |
| 10 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.15 | 0.13 | 0.00 | 0.01 | 0.00 | 0.00 |
| 11 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | 0.00 | **0.54** | 0.15 | 0.00 |

**261016 × 261027 by point id (same physical points, DERIVED map; research):** the diagonal-like maxima are 16:E1→27:E1 0.90, 16:E2→27:E2 0.82, 16:E3→27:E3 0.68, 16:E4→27:E4 0.48, 16:E5→27:E5 0.71, 16:E6→27:E6 0.97, 16:E7→27:E7 0.90, 16:E8→27:E8 0.70, 16:E9→27:E10 0.82, 16:E10→27:E10 0.04. Record 1 of both series has the same shape (0.90) while the frequency moved 33.45 → 18.63 Hz: consistent with the owner's freer-suspension explanation (research, not a proof).

## 5. Plate FE frequencies against E1, E2 and G12 (existing variants; no new solve)

| Branch | f0 Hz | G12 ×2 | G12 ×3 | E1 ×0.9 | E2 ×0.9 | s_E1 | s_E2 | s_G12 | s_E (E1=E2) |
|---|---|---|---|---|---|---|---|---|---|
| FE7 | 19.0722 | 26.5783 | 32.1826 | 19.0554 | 19.055 | 0.0084 | 0.0086 | 0.4788 | 0.0169 |
| FE8 | 59.8742 | 59.8749 | 59.8754 | lost | lost |  |  | 0.0 |  |
| FE9 | 62.0092 | 62.0145 | 62.0169 | lost | lost |  |  | 0.0001 |  |
| FE10 | 71.8499 | 80.7598 | 88.4699 | 69.2291 | 71.8044 | 0.3527 | 0.006 | 0.1687 | 0.3587 |
| FE11 | 72.19 | 81.0594 | 88.7419 | 72.1603 | 69.5313 | 0.0039 | 0.3562 | 0.1672 | 0.3601 |
| FE12 | 116.5804 | 138.1658 | 155.8081 | 114.9295 | 114.8269 | 0.1354 | 0.1438 | 0.2451 | 0.2792 |
| FE13 | 167.4903 | 167.5031 | 167.5093 | 158.9187 | 167.4758 | 0.4986 | 0.0008 | 0.0001 | 0.4994 |
| FE14 | 168.608 | 168.6208 | 168.6271 | 168.6241 | 159.9496 | -0.0009 | 0.5004 | 0.0001 | 0.4994 |
| FE15 | 174.7977 | 182.9328/188.0098 | 190.6055/195.4325 | 168.0620/178.5238 | 168.9622/177.4616 | 0.223 | 0.2259 | 0.0646 | 0.4489 |
| FE16 | 179.9016 | 182.9328/188.0098 | 190.6055/195.4325 | 168.0620/178.5238 | 168.9622/177.4616 | 0.223 | 0.2259 | 0.0646 | 0.4489 |
| FE17 | 213.1995 | 239.759 | 262.4908 | 206.5031 | 212.0583 | 0.3029 | 0.0509 | 0.1694 | 0.3538 |
| FE18 | 213.9528 | 240.4191 | 263.09 | 212.9881 | 207.0274 | 0.0429 | 0.3123 | 0.1683 | 0.3552 |
| FE19 | 295.7755 | lost | lost | 290.9082 | 290.5086 | 0.1575 | 0.1705 |  | 0.328 |
| FE20 | 327.901 | 327.9666 | 327.9926 | lost | lost |  |  | 0.0003 |  |

Secant sensitivities s = Δ ln f / Δ ln p (E1, E2: −10 %; G12: ×2, the smaller step kept). FE15+FE16 is one confirmed cluster term. Empty cells: the branch was not tracked in that variant (no value is guessed).

## 6. Rank and what can be determined separately

- **E1, E2, G12:** singular values 0.893, 0.663, 0.504; condition 1.8; rank 3 at rcond 1e-3; weakest direction {'E1': -0.3777, 'E2': -0.3732, 'G12': 0.8474}.
- **E (E1 = E2), G12:** singular values 1.187, 0.536; condition 2.2; rank 2 at rcond 1e-3; weakest direction {'E (E1=E2)': -0.3267, 'G12': 0.9451}.

| M5 design study (provisional Σ_setup 0.3 %) | status | conditional sd (ln) | refusal |
|---|---|---|---|
| all tracked FE terms, E1 / E2 / G12 | FULL_RANK | 0.44 %, 0.44 %, 0.54 % | — |
| all tracked FE terms, E (E1 = E2) / G12 | FULL_RANK | 0.30 %, 0.54 % | — |
| CANDIDATE_ONLY rows only (hypothetical pairing), E1 / E2 / G12 | RANK_DEFICIENT | — | rank 1 < 3 parameters at rcond 0.001 (smallest/largest singular value 0); SPEC §10 hard block, no override |
| CANDIDATE_ONLY rows only (hypothetical pairing), E (E1 = E2) / G12 | RANK_DEFICIENT | — | rank 1 < 2 parameters at rcond 0.001 (smallest/largest singular value 0); SPEC §10 hard block, no override |

**Reading:**
- With the FE terms the model offers (FE7, FE10, FE11, FE12, FE13, FE14, FE15+16, FE17, FE18), E1, E2 and G12 are separable in the model (full rank, condition 1.8): FE7 carries G12 (s 0.48, s_E 0.02), FE13 only E1 (0.50), FE14 only E2 (0.50), FE10 / FE17 mostly E1 and FE11 / FE18 mostly E2 with G12.
- With the observations that are usable now (one CANDIDATE_ONLY row, EXP1 ↔ FE7), the problem has rank 1: only G12 (as D66) is informed; E1, E2 and E (E1 = E2) are not. The design study refuses (SPEC §10 hard block).
- E1 ≠ E2 stays blocked by SPEC v1.1 §5.2 (no traceable material axes) even though the model separates them: FE13 / FE14 and FE10 / FE11 swap under E1 / E2, so the assignment needs the physical registration.

### Bounded LM on a linear surrogate — HYPOTHETICAL_PAIRING (method demonstration only)

- **G12:** CONVERGED, ratio to baseline G12 ×0.9523, objective 3.04e-05, 4 surrogate evaluations, local sd(ln) 0.0063.
- **E:** CONVERGED, ratio to baseline E ×0.5000, objective 7.59, 4 surrogate evaluations, local sd(ln) 0.1773.
- **E+G12:** STEP_ERROR — JᵀJ is not positive definite..

G12 alone from EXP1 ↔ FE7 moves G12 by ×0.952 in the linear surrogate; E alone runs to its lower bound (the twist mode does not inform E); E + G12 together is singular. These numbers demonstrate the method and its limits; they are not carbon properties (one unconfirmed pair, secant extrapolation, no admissible registration).

## 7. The FE computations needed for the next iterative step, and why

1. **SPEC §6 S4 central sensitivities of the M11 baseline** (4 jobs: E (E1 = E2) and G12 at ±5 %, plus the ±2.5 % repeat, 4 jobs): the secants above use −10 % / ×2 steps; the LM needs central derivatives at the working point and their linearity check.
2. **FE applicability of the two-band suspension and the force sensor** (prepared jobs B ×2, D ×1): EXP2–EXP5 and EXP8–EXP11 sit in FE groups whose ordering depends on small asymmetries; a suspension or attachment that splits them changes which records can become pairs.
3. **An FE model carrying the measured edge-thickness asymmetry** (or the owner's FE corner): it fixes the FE ↔ physical corner (A–D) and splits FE8 / FE9, FE10 / FE11, FE13 / FE14 physically, which E1 / E2 need.
4. **Extraction of the SP-10 ODB** (`SP10_NEW_E1=E2_NSM_DENSITY`, Abaqus Python, separate gate) and modes above 220 Hz: without them SP-10 has no FE shapes and EXP11–12 no FE frequency.
5. **Owner input that unlocks admissible MAC (no computation):** SCANNER_FACE of 261016 and the 261016 scan calibration (plate); the same-points confirmation for SP-13 261028 (then its frozen registration can be carried by point id).

## 8. Rule refinements made after the first run (disclosed)

The status rules were declared in `run_real_matching.py` before the first run. Two refinements were made after it, both making the result more conservative or more consistent, none adding a confirmed pair:
1. A record whose best single MAC is below 0.50 is no longer called AMBIGUOUS only because its nearest FE mode belongs to a close group (first run: plate EXP9 / EXP10 with MAC 0.26 / 0.15). AMBIGUOUS now needs shape agreement >= 0.50 with a group member, or two FE modes >= 0.50.
2. A record inside the span of a close two-mode FE group (two-mode subspace projection >= 0.80, S2MAC idea of Brincker et al. 2014) is AMBIGUOUS_CLUSTER even when no single FE mode reaches 0.50 (plate EXP8: FE15 / FE16 subspace 0.92).

## Figures (`figures/`, independent views unless stated)

- `plate_261016_vs_261027_mac.png`
- `plate_experimental_shapes.png`
- `plate_fe_shapes.png`
- `plate_frequencies.png`
- `plate_research_mac.png`
- `plate_side_by_side_research.png`
- `sp10_experimental_shapes.png`
- `sp10_frequencies.png`
- `sp13_experimental_shapes.png`
- `sp13_fe_shapes.png`
- `sp13_frequencies.png`

`plate_side_by_side_research.png` and `plate_research_mac.png` use the 261016 diagnostic reconstruction: research only, never a registered pair.
