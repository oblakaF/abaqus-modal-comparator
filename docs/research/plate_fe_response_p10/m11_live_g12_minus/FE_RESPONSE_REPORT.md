# FE response — M11 S4R_0875_BASELINE (PLATE-300x300x1mm)

Labels: RESEARCH_ONLY / FE_ONLY / NOT_A_MATERIAL_PROPERTY / NO_EXPERIMENTAL_PAIRING

Kind: **LIVE_FE_PACKAGE_ANALYSIS** · status **LIVE_FE_PACKAGE_ANALYSIS**

## Sources

| State | Parameter | Value | Manifest SHA-256 | Not verified |
|---|---|---|---|---|
| baseline | — | — | 354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7 | the ODB (not present or no recorded SHA-256): the package's origin from its solve is not verified |
| M11_S4_E1_MINUS | E1 | 53200.0 | a2ae6efd1f6c707f056b7c915a714b77dd700ebad6bd935c9f01e8d49b1a4d00 | — |
| M11_S4_E1_PLUS | E1 | 58800.0 | 3f7e09810481088f3bf7d77c4e2907c6d53b5252fd9e819f15a1f4450e48b3d9 | — |
| M11_S4_E2_MINUS | E2 | 53200.0 | c658355d7bc57452eb1163a098537d067f6101114c1351b85829a5bcbf99fa58 | — |
| M11_S4_E2_PLUS | E2 | 58800.0 | 988592df1c76d80f4e0ad4ed04ef8c4d9e2d8221f88a8ccb9522d7958c141c2a | — |
| M11_S4_G12_MINUS | G12 | 4750.0 | 36982be350338eafc1b575d3b12fa9c75b034d732711da08e69d6424ad151f89 | — |
| M11_S4_G12_PLUS | G12 | 5250.0 | 56116a4ef13d61c01bdc166e88eb0f8e3a0bc9e241b214383db103a925e6bbd9 | — |

## Central sensitivities

| Term | f0 (Hz) | s_E1 | s_E2 | s_G12 |
|---|---|---|---|---|
| FE7 | 19.07217 | 0.00810 | 0.00827 | 0.48268 |
| FE8 | 59.87416 | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE | 0.00001 |
| FE9 | 62.00917 | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE | 0.00014 |
| FE10 | 71.84985 | 0.35783 | 0.00590 | 0.13555 |
| FE11 | 72.18999 | 0.00384 | 0.36123 | 0.13422 |
| FE12 | 116.58043 | 0.14011 | 0.14867 | 0.21001 |
| FE13 | 167.49026 | 0.49864 | 0.00086 | 0.00012 |
| FE14 | 168.60799 | -0.00086 | 0.50037 | 0.00012 |
| FE15+FE16 | 177.33129 | 0.22420 | 0.22710 | 0.04807 |
| FE17 | 213.19948 | 0.30883 | 0.05285 | 0.13711 |
| FE18 | 213.95276 | 0.04461 | 0.31810 | 0.13608 |
| FE19 | 295.77551 | 0.16280 | 0.17599 | 0.15964 |
| FE20 | 327.90103 | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE | 0.00036 |

## FE-only rank

- E1 / E2 / G12: rank 3 of 3, condition 1.83 — FE_ONLY
- E (E1 = E2) / G12: rank 2 of 2, condition 2.35 — FE_ONLY — CONDITIONAL_SUPERPOSITION (s_E = s_E1 + s_E2; no joint E1 = E2 state solved)

## Archive (PRIORITY-2): AGREES

max |Δs| 4.906181016117728e-06; 

## FE-only What-If {'G12': 4750.0}

FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve

| Term | f0 | predicted | solved FE | error % | status |
|---|---|---|---|---|---|
| FE7 | 19.07217 | 18.60578 | 18.60554 | +0.0013 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE8 | 59.87416 | 59.87411 | 59.87411 | -0.0000 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE9 | 62.00917 | 62.00872 | 62.00872 | +0.0000 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE10 | 71.84985 | 71.35203 | 71.35995 | -0.0111 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE11 | 72.18999 | 71.69471 | 71.70262 | -0.0110 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE12 | 116.58043 | 115.33138 | 115.34624 | -0.0129 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE13 | 167.49026 | 167.48919 | 167.48918 | +0.0000 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE14 | 168.60799 | 168.60692 | 168.60690 | +0.0000 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE15+FE16 | 177.33129 | 176.89460 | 176.90342 | -0.0050 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE17 | 213.19948 | 211.70536 | 211.72850 | -0.0109 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE18 | 213.95276 | 212.46457 | 212.48769 | -0.0109 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE19 | 295.77551 | 293.36351 | 293.39825 | -0.0118 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |
| FE20 | 327.90103 | 327.89501 | 327.89493 | +0.0000 | FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve |

## Limits

- FE-only: sensitivities and predictions describe this FE model, not the physical plate and not a material.
- A prediction is the local log-linear formula, not an Abaqus solve; it is never extrapolated beyond the solved states, and the ±5 % range is not a confirmed linear range without the ±2.5 % repeat.
- E1 and E2 are FE model directions: without a traceable warp / fill orientation they are not independent constants of the physical CFRP.
- E (E1 = E2) is a CONDITIONAL_SUPERPOSITION of the separate E1 and E2 states: no joint state was solved.
- Experimental records are never paired with FE branches here: frequency proximity only, no MAC objective, no parameter chosen from a measured frequency.

M8 GATE NOT_MET · D-077 NO_GLOBAL_PARAMETER_VALUE · production Auto-ID BLOCKED · no material value is released here
