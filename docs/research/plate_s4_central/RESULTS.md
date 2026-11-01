# PRIORITY-2 — SPEC §6 S4 central sensitivities of the M11 S4R plate (RESEARCH_ONLY)

Owner-authorised: at most six Abaqus Frequency solves of `S4R_0875_BASELINE`. **Six were run, each once; all completed.** No LM, no experimental fit, no Auto-ID; no normative file, registration or gate changed. Branch `research/plate-s4-central-sensitivities` (from `1dd29d5`). Script `research/plate_s4/run_s4.py`.

## 1. Inputs and the six jobs

- Baseline INP `CFRP_S4R_0875_FreeFree.inp` SHA-256 `962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3`; *Elastic line 20238 `56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.` (E1, E2, E3, ν12, ν13, ν23, G12, G13; G23 on the next line).
- Baseline extraction manifest SHA-256 `354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7`; extractor `abaqus_scripts/extract_odb.py` SHA-256 `039aa067adeac83e457ccacc9036c767f98c41517fb1ffdd5293fdd01dc6534d` (pinned, unchanged).
- Each copy changes one field of that line, same width; every other byte is checked equal; mass, thickness, mesh, free-free boundary and the *Frequency step are unchanged. Jobs in `D:\git\abaqus-modal-comparator-work\runs\m11_carbon_plate\s4_central\`.

| # | Job | Changed | Value (MPa) | INP SHA-256 | Exit | Completed | Seconds | ODB SHA-256 |
|---|---|---|---|---|---|---|---|---|
| 1 | M11_S4_E1_MINUS | E1 | 53200 | `9206031e23f3d44a…` | 0 | True | 16.5 | `38c6b0096a9062c4…` |
| 2 | M11_S4_E1_PLUS | E1 | 58800 | `b3a631909ac0117e…` | 0 | True | 12.2 | `f70b02982cbcc58c…` |
| 3 | M11_S4_E2_MINUS | E2 | 53200 | `4200225bba4d17cf…` | 0 | True | 12.4 | `5af4b61c7b907bb6…` |
| 4 | M11_S4_E2_PLUS | E2 | 58800 | `3cd0ed6aa60bc946…` | 0 | True | 12.1 | `aa5c9b707ddc526b…` |
| 5 | M11_S4_G12_MINUS | G12 | 4750 | `909251e1990ae03d…` | 0 | True | 12.3 | `8048f391b9f5c5ed…` |
| 6 | M11_S4_G12_PLUS | G12 | 5250 | `1ddbe7fa38498f56…` | 0 | True | 12.3 | `ea3e591400357ff5…` |

## 2. Frequencies: baseline and the ±5 % variants (branches followed by FE-to-FE MAC, not by order)

| Term | f0 Hz | E1 −5 % | E1 +5 % | E2 −5 % | E2 +5 % | G12 −5 % | G12 +5 % |
|---|---|---|---|---|---|---|---|
| FE7 | 19.07217 | 19.06413 | 19.07959 | 19.06395 | 19.07974 | 18.60554 | 19.5264 |
| FE8 | 59.87416 | 58.73562 | lost | lost | 60.2495 | 59.87411 | 59.8742 |
| FE9 | 62.00917 | 61.61434 | lost | lost | 63.14716 | 62.00872 | 62.00959 |
| FE10 | 71.84985 | 70.55189 | 73.12437 | 71.8279 | 71.87035 | 71.35995 | 72.33463 |
| FE11 | 72.18999 | 72.17565 | 72.20339 | 70.87336 | 73.48256 | 71.70262 | 72.67229 |
| FE12 | 116.58043 | 115.75915 | 117.39381 | 115.70854 | 117.44314 | 115.34624 | 117.79625 |
| FE13 | 167.49026 | 163.26083 | 171.61526 | 167.48303 | 167.4975 | 167.48918 | 167.49127 |
| FE14 | 168.60799 | 168.61563 | 168.60107 | 164.33568 | 172.77495 | 168.6069 | 168.60899 |
| FE15+FE16 | 177.33129 | 175.30883 | 179.28692 | 175.28245 | 179.312 | 176.90342 | 177.75654 |
| FE17 | 213.19948 | 209.87898 | 216.46733 | 212.63242 | 213.76009 | 211.7285 | 214.65393 |
| FE18 | 213.95276 | 213.4729 | 214.42816 | 210.51965 | 217.32974 | 212.48769 | 215.40143 |
| FE19 | 295.77551 | 293.35425 | 298.17307 | 293.1568 | 298.36621 | 293.39825 | 298.1235 |
| FE20 | 327.90103 | 319.98279 | lost | lost | 328.27277 | 327.89493 | 327.90668 |

FE15+FE16 is one CONFIRMED cluster term (mean ln f): individually its branches exchange in E1 +5 % and E2 −5 %, the two-mode subspace is stable in every direction. Rigid modes 1–6 are excluded by the shape criterion.

## 3. Central sensitivities s = (ln f₊ − ln f₋) / (ln 1.05 − ln 0.95)

| Term | s_E1 | s_E2 | s_G12 | s_E (E1=E2) | curvature E1 / E2 / G12 (s₊ − s₋) | PRIORITY-1 secant E1 / E2 / G12 |
|---|---|---|---|---|---|---|
| FE7 | 0.0081 | 0.00827 | 0.48268 | 0.01638 | -0.00025 / -0.00027 / -0.00052 | 0.0084 / 0.0086 / 0.4788 |
| FE8 | — | — | 1e-05 | — | NOT_TRACKED / NOT_TRACKED / 0.0 | — / — / 0.0 |
| FE9 | — | — | 0.00014 | — | NOT_TRACKED / NOT_TRACKED / -0.0 | — / — / 0.0001 |
| FE10 | 0.35783 | 0.0059 | 0.13555 | 0.36374 | 0.00497 / -0.00011 / 0.00444 | 0.3527 / 0.006 / 0.1687 |
| FE11 | 0.00384 | 0.36123 | 0.13422 | 0.36507 | -7e-05 / 0.00488 / 0.00441 | 0.0039 / 0.3562 / 0.1672 |
| FE12 | 0.14011 | 0.14867 | 0.21001 | 0.28878 | 0.00468 / 0.00476 / 0.00515 | 0.1354 / 0.1438 / 0.2451 |
| FE13 | 0.49864 | 0.00086 | 0.00012 | 0.49951 | 4e-05 / 4e-05 / -0.0 | 0.4986 / 0.0008 / 0.0001 |
| FE14 | -0.00086 | 0.50037 | 0.00012 | 0.49951 | 4e-05 / 1e-05 / -0.0 | -0.0009 / 0.5004 / 0.0001 |
| FE15+FE16 | 0.2242 | 0.2271 | 0.04807 | 0.45129 | 0.00117 / 0.0011 / 0.00199 | 0.223 / 0.2259 / 0.0646 |
| FE17 | 0.30883 | 0.05285 | 0.13711 | 0.36168 | 0.00574 / 0.0019 / 0.00437 | 0.3029 / 0.0509 / 0.1694 |
| FE18 | 0.04461 | 0.3181 | 0.13608 | 0.36271 | 0.00172 / 0.00561 / 0.00435 | 0.0429 / 0.3123 / 0.1683 |
| FE19 | 0.1628 | 0.17599 | 0.15964 | 0.33879 | 0.00522 / 0.00536 / 0.00474 | 0.1575 / 0.1705 / — |
| FE20 | — | — | 0.00036 | — | NOT_TRACKED / NOT_TRACKED / -1e-05 | — / — / 0.0003 |

**Against the PRIORITY-1 secants:** E1 and E2 (secant over −10 %) agree with the central values to within a few per cent of s; the G12 secants (over ×2) are too large for the G12-coupled branches (FE10 / FE11 0.169 / 0.167 → 0.136 / 0.134; FE12 0.245 → 0.210; FE15+16 0.065 → 0.048; FE17 / FE18 0.169 / 0.168 → 0.137 / 0.136): the ×2 step is far outside the linear range. FE7's G12 sensitivity is almost unchanged (0.479 → 0.483).

## 4. Branches that lose identity, and permutations

- **Lost (not tracked at MAC ≥ 0.90 in at least one variant; no central value):** FE20, FE8, FE9. FE8 / FE9 (59.87 / 62.01 Hz) mix as soon as E1 ≠ E2 (each is tracked on one side only); FE20 is lost in E1 +5 % and E2 −5 %. Their G12 sensitivity is ~0 on both sides.
- **Permutations caught by the tracking (would be wrong by frequency order):** FE10 -> FE11 in M11_S4_E1_PLUS; FE10 -> FE11 in M11_S4_E2_MINUS; FE11 -> FE10 in M11_S4_E1_PLUS; FE11 -> FE10 in M11_S4_E2_MINUS; FE13 -> FE14 in M11_S4_E1_PLUS; FE13 -> FE14 in M11_S4_E2_MINUS; FE14 -> FE13 in M11_S4_E1_PLUS; FE14 -> FE13 in M11_S4_E2_MINUS; FE17 -> FE18 in M11_S4_E1_PLUS; FE17 -> FE18 in M11_S4_E2_MINUS; FE18 -> FE17 in M11_S4_E1_PLUS; FE18 -> FE17 in M11_S4_E2_MINUS.
  In every case E1 > E2 (E1 +5 % or E2 −5 %) puts the E1-dominated branch above the E2-dominated one.
- Close pairs (`confirm_cluster`): FE10/FE11 INDEPENDENT; FE13/FE14 INDEPENDENT; FE15/FE16 CONFIRMED; FE17/FE18 INDEPENDENT.

## 5. Sensitivity matrices, rank and condition

- **E1 / E2 / G12** over the 10 tracked terms: singular values 0.9171, 0.6673, 0.5023; condition 1.83; rank 3 at rcond 1e-3; weakest direction {'E1': -0.3288, 'E2': -0.3264, 'G12': 0.8862}; column cosines [[1.0, 0.2319, 0.3606], [0.2319, 1.0, 0.3685], [0.3606, 0.3685, 1.0]].
- **E (E1 = E2) / G12** over the 10 tracked terms: singular values 1.2371, 0.5265; condition 2.35; rank 2 at rcond 1e-3; weakest direction {'E (E1=E2)': -0.2844, 'G12': 0.9587}; column cosines [[1.0, 0.4646], [0.4646, 1.0]].

| M5 design study (all tracked terms as if they were confirmed pairs; provisional Σ_setup 0.3 %) | Status | Conditional sd (ln) |
|---|---|---|
| E1 / E2 / G12 | FULL_RANK | 0.43 %, 0.42 %, 0.55 % |
| E (E1 = E2) / G12 | FULL_RANK | 0.28 %, 0.55 % |

## 6. What is mathematically distinguishable

- **In the FE model:** E1, E2 and G12 are separable (rank 3, condition 1.83). Each has its own branch: FE13 is pure E1 (s 0.499), FE14 pure E2 (0.500), FE7 almost pure G12 (0.483; s_E 0.016); FE10 / FE17 mix E1 with G12, FE11 / FE18 mix E2 with G12. The restricted E (E1 = E2) / G12 is rank 2, condition 2.35.
- **With the experiment as it stands (PRIORITY-1):** only EXP1 ↔ FE7 is CANDIDATE_ONLY, and it informs G12 only; E1, E2 and E stay unidentifiable until branches such as FE13 / FE14 or FE10 / FE11 can be paired. Those pairs need the physical registration, because E1 ↔ E2 swap the members of each pair.
- **E1 ≠ E2** stays blocked by SPEC v1.1 §5.2 (no traceable material axes), although the model separates them.
- The conditional sd values above assume every FE term is a confirmed pair and the provisional Σ_setup: they are not the accuracy of the real plate.

## Files

`CENTRAL_SENSITIVITIES.csv`, `BRANCH_TRACKING.csv`, `SOLVER_RUNS.csv` (this folder); the ODB, extraction packages and logs stay in `runs\m11_carbon_plate\s4_central\` (outside Git).
