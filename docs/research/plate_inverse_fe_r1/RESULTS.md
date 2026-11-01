# PRIORITY-4 — real Abaqus verification of the inverse parameter sets S0, H1, H2 (M11 S4R plate)

Labels of every number: RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY / NOT_TRANSFERABLE_WITHOUT_VALIDATION.

| Сценарий | E1, МПа | E2, МПа | G12, МПа | Основные частоты Abaqus, Гц | Эксперимент, Гц | Ошибка | FE-ветви |
|---|---|---|---|---|---|---|---|
| S0 | 56000 | 56000 | 4763.4 | FE7 18.6309; FE13 167.4892; FE14 168.6070; FE15+FE16 176.9264 | EXP1 18.6307 | EXP1↔FE7 +0.001 % | 14 of 14 tracked at MAC ≥ 0.90; permutations 0; lost 0 |
| H1 | 43467 | 43467 | 4804.4 | FE7 18.6266; FE13 147.5781; FE14 148.5630; FE15+FE16 158.0173 | EXP1 18.6307; EXP8 157.8508 | EXP1↔FE7 -0.022 %; EXP8↔FE15+FE16 +0.105 % | 14 of 14 tracked at MAC ≥ 0.90; permutations 0; lost 0 |
| H2 | 41952.8 | 41952.8 | 4810.3 | FE7 18.6251; FE13 144.9869; FE14 145.9545; FE15+FE16 155.5754 | EXP1 18.6307; EXP7 145.9357 | EXP1↔FE7 -0.030 %; EXP7↔FE14 +0.013 % | 14 of 14 tracked at MAC ≥ 0.90; permutations 0; lost 0 |

## 1. The three real Abaqus solves (owner-authorised maximum: 3)

| # | State | Changed | Values | INP SHA-256 | Exit | Completed | s | ODB SHA-256 | Extraction manifest SHA-256 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | S0 | G12 | 4763.4 | `02234fe6b594229c…` | 0 | True | 13.0 | `2737f5fffe0f09b8…` | `351fe6b850f93d73…` |
| 2 | H1 | E1; E2; G12 | 43467; 43467; 4804.4 | `512dec840310ea49…` | 0 | True | 12.2 | `ee8a250fa62a3a67…` | `6297b9219090015b…` |
| 3 | H2 | E1; E2; G12 | 41952.8; 41952.8; 4810.3 | `553f5dc5623f17d5…` | 0 | True | 12.1 | `aa8a5de32339c57e…` | `4ed79aac37d3136d…` |

Baseline INP `CFRP_S4R_0875_FreeFree.inp` `962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3`; only the *Elastic line 20239 differs (`56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.` →):
- S0: `56000.,56000., 8500.,  0.05,   0.3,   0.3,4763.4, 3000.` — parsed E3 8500, ν12 0.05, ν13 0.3, ν23 0.3, G13 3000, G23 3000, ρ 1.498e-09, h 0.875 (all as the baseline).
- H1: `43467.,43467., 8500.,  0.05,   0.3,   0.3,4804.4, 3000.` — parsed E3 8500, ν12 0.05, ν13 0.3, ν23 0.3, G13 3000, G23 3000, ρ 1.498e-09, h 0.875 (all as the baseline).
- H2: `41952.8,41952.8, 8500.,  0.05,   0.3,   0.3,4810.3, 3000.` — parsed E3 8500, ν12 0.05, ν13 0.3, ν23 0.3, G13 3000, G23 3000, ρ 1.498e-09, h 0.875 (all as the baseline).

Each extraction manifest names its own job's ODB (`odb_path`), and the ODB SHA-256 equals the one recorded after the solve: the shapes belong to the new solves, not to the baseline. Pinned extractor `039aa067…` unchanged. No attempt was repeated.

## 2. Real Abaqus against the PRIORITY-3 predictions, branch by branch

| Сценарий | FE-ветвь | База, Гц | Прогноз LM, Гц | Abaqus, Гц | Ошибка прогноза, % | Эксперимент (объявленная гипотеза) | FE-to-FE MAC | Статус ветви |
|---|---|---|---|---|---|---|---|---|
| S0 | FE7 | 19.07217 | 18.63109 | 18.63088 | -0.0011 | EXP1 18.6307 | 1.0000 | TRACKED |
| S0 | FE10 | 71.84985 | 71.37928 | 71.38634 | 0.0099 | — | 1.0000 | TRACKED |
| S0 | FE11 | 72.18999 | 71.72181 | 71.72887 | 0.0098 | — | 1.0000 | TRACKED |
| S0 | FE12 | 116.58043 | 115.39961 | 115.41286 | 0.0115 | — | 1.0000 | TRACKED |
| S0 | FE13 | 167.49026 | 167.48929 | 167.48924 | -0.0 | — | 1.0000 | TRACKED |
| S0 | FE14 | 168.60799 | 168.60701 | 168.60696 | -0.0 | — | 1.0000 | TRACKED |
| S0 | FE15+FE16 | 177.33129 | 176.91854 | 176.92643 | 0.0045 | — | 1.0000 / 1.0000 | centroid of FE15 and FE16, each TRACKED |
| S0 | FE17 | 213.19948 | 211.78713 | 211.80777 | 0.0097 | — | 1.0000 | TRACKED |
| S0 | FE18 | 213.95276 | 212.54603 | 212.56664 | 0.0097 | — | 1.0000 | TRACKED |
| S0 | FE19 | 295.77551 | 293.49541 | 293.52643 | 0.0106 | — | 1.0000 | TRACKED |
| H1 | FE7 | 19.07217 | 18.63089 | 18.62655 | -0.0233 | EXP1 18.6307 | 1.0000 | TRACKED |
| H1 | FE10 | 71.84985 | 65.17125 | 65.30467 | 0.2047 | — | 1.0000 | TRACKED |
| H1 | FE11 | 72.18999 | 65.46102 | 65.59438 | 0.2037 | — | 1.0000 | TRACKED |
| H1 | FE12 | 116.58043 | 107.45138 | 107.69914 | 0.2306 | — | 0.9999 | TRACKED |
| H1 | FE13 | 167.49026 | 147.58027 | 147.57812 | -0.0015 | — | 1.0000 | TRACKED |
| H1 | FE14 | 168.60799 | 148.56476 | 148.56303 | -0.0012 | — | 1.0000 | TRACKED |
| H1 | FE15+FE16 | 177.33129 | 157.86886 | 158.01732 | 0.094 | EXP8 157.8508 | 1.0000 / 0.9999 | centroid of FE15 and FE16, each TRACKED |
| H1 | FE17 | 213.19948 | 193.47054 | 193.85704 | 0.1998 | — | 0.9998 | TRACKED |
| H1 | FE18 | 213.95276 | 194.11144 | 194.4976 | 0.1989 | — | 0.9998 | TRACKED |
| H1 | FE19 | 295.77551 | 269.72364 | 270.30035 | 0.2138 | — | 0.9997 | TRACKED |
| H2 | FE7 | 19.07217 | 18.63112 | 18.62512 | -0.0322 | EXP1 18.6307 | 1.0000 | TRACKED |
| H2 | FE10 | 71.84985 | 64.34686 | 64.52924 | 0.2834 | — | 0.9999 | TRACKED |
| H2 | FE11 | 72.18999 | 64.62979 | 64.81207 | 0.282 | — | 0.9999 | TRACKED |
| H2 | FE12 | 116.58043 | 106.38419 | 106.7224 | 0.3179 | — | 0.9999 | TRACKED |
| H2 | FE13 | 167.49026 | 144.98955 | 144.98689 | -0.0018 | — | 1.0000 | TRACKED |
| H2 | FE14 | 168.60799 | 145.95671 | 145.95451 | -0.0015 | EXP7 145.9357 | 1.0000 | TRACKED |
| H2 | FE15+FE16 | 177.33129 | 155.37197 | 155.57542 | 0.1309 | — | 1.0000 / 0.9998 | centroid of FE15 and FE16, each TRACKED |
| H2 | FE17 | 213.19948 | 191.03746 | 191.56613 | 0.2767 | — | 0.9998 | TRACKED |
| H2 | FE18 | 213.95276 | 191.66305 | 192.19131 | 0.2756 | — | 0.9998 | TRACKED |
| H2 | FE19 | 295.77551 | 266.5552 | 267.34393 | 0.2959 | — | 0.9996 | TRACKED |

The branches FE8, FE9 and FE20 have no PRIORITY-2 central derivative (they were lost when E1 ≠ E2), so no LM prediction exists for them; their real frequencies are in `REAL_FE_FREQUENCIES.csv` and their tracking in `REAL_FE_BRANCH_TRACKING.csv`.

## 3. Permutations, lost and mixed branches

- Tracked at FE-to-FE MAC ≥ 0.90: 42 of 42 branch × state cells; lowest MAC 0.9996.
- Permutations: none. Lost or ambiguous: none.
- Close pairs (`confirm_cluster` over S0 / H1 / H2): FE10/FE11 INDEPENDENT; FE13/FE14 INDEPENDENT; FE15/FE16 INDEPENDENT; FE17/FE18 INDEPENDENT. FE15 / FE16, a confirmed cluster in PRIORITY-2 (where E1 ≠ E2 exchanged them), keep their individual identity here, because E1 = E2 keeps the square symmetry; the PRIORITY-3 term FE15+FE16 is compared as the geometric mean of the two tracked branches.
- FE8 / FE9 stay separate and keep their order in every state for the same reason (they mixed only when E1 ≠ E2).

## 4. Declared experimental hypotheses and diagnostic residuals

| State | Hypothesis | f_EXP, Hz | f_Abaqus, Hz | Error | f_LM, Hz |
|---|---|---|---|---|---|
| S0 | EXP1 ↔ FE7 | 18.6307 | 18.63088 | +0.0011 % | 18.63109 |
| H1 | EXP1 ↔ FE7 | 18.6307 | 18.62655 | -0.0221 % | 18.63089 |
| H1 | EXP8 ↔ FE15+FE16 | 157.8508 | 158.01732 | +0.1055 % | 157.86886 |
| H2 | EXP1 ↔ FE7 | 18.6307 | 18.62512 | -0.0298 % | 18.63112 |
| H2 | EXP7 ↔ FE14 | 145.9357 | 145.95451 | +0.0129 % | 145.95671 |

Other records against the nearest tracked FE frequency (diagnostic only, never a pair; nearest frequency is not shape identity):

| State | EXP1 | EXP2 | EXP3 | EXP4 | EXP5 | EXP6 | EXP7 | EXP8 | EXP9 | EXP10 | EXP11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | hyp. | FE8 +9.62 % | FE9 -2.34 % | FE10 +6.79 % | FE11 -3.35 % | FE12 +2.80 % | FE13 +14.77 % | FE13 +6.11 % | FE14 -0.34 % | FE16 -0.36 % | FE16 -6.32 % |
| H1 | hyp. | FE9 +0.03 % | FE10 +2.85 % | FE11 -1.87 % | FE11 -11.62 % | FE12 -4.07 % | FE13 +1.13 % | hyp. | FE16 -5.25 % | FE17 +7.62 % | FE17 +1.18 % |
| H2 | hyp. | FE9 -1.73 % | FE10 +1.63 % | FE11 -3.04 % | FE11 -12.67 % | FE12 -4.94 % | hyp. | FE16 -0.02 % | FE16 -6.72 % | FE17 +6.35 % | FE17 -0.02 % |

## 5. Answers

1. **S0:** the real FE7 is 18.63088 Hz against the predicted 18.63109 Hz (-0.0011 %), and 0.0011 % from EXP1 (18.6307 Hz); FE-to-FE MAC with the baseline FE7 1.0000. The one-mode fit is reproduced by the real solve.
2. **Accuracy of the log-linear approximation:** largest |δ| S0 0.011 %, H1 0.231 %, H2 0.318 % over all tracked branches. Branches driven by E alone (FE13, FE14) stay within 0.002 % even at E −22 % / −25 % (f ∝ E^0.5 is exactly log-linear); the branches that mix E with G12 (FE10–FE12, FE17–FE19) are under-predicted by 0.2–0.32 %, because their share of E and G12 changes along the path; FE7 −0.02 / −0.03 %.
3. **Kept identity:** every elastic branch FE7–FE20 in S0, H1 and H2 (lowest FE-to-FE MAC 0.9996).
4. **Exchanged order:** none in these three states.
5. **Lost or mixed:** none; FE15 / FE16 are individually stable here (INDEPENDENT), unlike in the E1 ≠ E2 variants of PRIORITY-2.
6. **H1 / H2 against the declared records:** H1 EXP1 -0.022 %, EXP8 ↔ FE15+FE16 centroid +0.105 % (real centroid 158.01732 Hz; the two real branches are FE15 155.767578 and FE16 160.299561 Hz). H2 EXP1 -0.030 %, EXP7 ↔ FE14 +0.013 %. These agreements follow from fitting two frequencies with two parameters; they test the approximation, not the pairings, and H1 / H2 are not ranked by them.
7. **Using the PRIORITY-2 central derivatives far from the base point:** along E1 = E2 with G12 almost fixed they predicted the real solves to ≤ 0.32 % at E −25 %, which is adequate for a first iteration in that direction. They are not adequate for precise residuals of the E–G12 mixed branches (bias 0.2–0.3 %, the size of the provisional Σ_setup) and they say nothing reliable in E1 ≠ E2 directions, where the PRIORITY-2 branches FE8 / FE9 / FE20 were lost and order exchanges occur. An iteration far from the base needs updated derivatives at the new point (a new ±5 % set: separate authorisation).
8. **Enough independent experimental correspondences for E1, E2, G12?** No. The only shape-supported row is EXP1 ↔ FE7 (CANDIDATE_ONLY, research MAC on an unadmitted registration) and it informs G12 only. H1 and H2 add one hypothetical row each and give rank 2 of 3 (E1 and E2 not separable); E1 ≠ E2 stays blocked by SPEC v1.1 §5.2.

## 6. Kept apart (one status each)

| Question | Outcome |
|---|---|
| Optimiser (PRIORITY-3 `run_bounded_lm`) | worked: CONVERGED in all three scenarios, inside the bounds |
| Approximation against real Abaqus | verified: |δ| ≤ 0.012 % (S0), ≤ 0.23 % (H1), ≤ 0.32 % (H2) |
| Calculated against experimental frequencies | the declared records agree to ≤ 0.11 % by construction (two frequencies, two parameters); the other records are NOT fitted and are not pairs |
| Correctness of the shape correspondence (EXP ↔ FE) | NOT ESTABLISHED: no admissible physical registration; EXP8 ↔ FE15+16 and EXP7 ↔ FE14 are hypotheses |
| Engineering calibration of this FE model | not made: no confirmed pairs, no FIT / HOLDOUT, no campaign |
| Material property identification | NOT_A_MATERIAL_PROPERTY; NOT_TRANSFERABLE_WITHOUT_VALIDATION; M8 GATE NOT_MET and D-077 NO_GLOBAL_PARAMETER_VALUE unchanged; production Auto-ID blocked |

## Files

In this folder: `REAL_FE_SOLVER_RUNS.csv`, `REAL_FE_FREQUENCIES.csv`, `REAL_FE_BRANCH_TRACKING.csv`, `REAL_FE_VS_LM.csv`, `REAL_FE_VS_EXPERIMENT.csv`. Outside Git: the jobs, ODB, DAT, STA, logs and extractions in `D:\git\abaqus-modal-comparator-work\runs\m11_carbon_plate\inverse_fe_r1\{S0,H1,H2}`; the figures (spectra, FE shapes, FE-to-FE MAC matrices, branch permutations) in `D:\git\abaqus-modal-comparator-work\research\PLATE_INVERSE_FE_R1_202610\figures`.
