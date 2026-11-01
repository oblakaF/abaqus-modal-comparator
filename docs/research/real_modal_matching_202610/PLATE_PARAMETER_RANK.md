# PLATE_PARAMETER_RANK — E1, E2, G12 of the M11 plate model (RESEARCH_ONLY)

Secant sensitivities s = Δ ln f / Δ ln p from the existing FE variants (no new Abaqus solve); branches followed by FE-to-FE MAC (strict tracking 0.90), close pairs by `confirm_cluster`. Basis: `SECANT_RESEARCH_SENSITIVITY (not SPEC §6 S4 central ±5 %)`.

## FE family used (SHA-256 verified)

| Member | Changed | Ratio | Files |
|---|---|---|---|
| S4R_0875_BASELINE | — | 1 | inp VERIFIED, manifest VERIFIED, odb VERIFIED, dat VERIFIED |
| S4R_0875_G12_10000 | G12 | 2 | inp VERIFIED, manifest VERIFIED |
| S4R_0875_G12_15000 | G12 | 3 | inp VERIFIED, manifest VERIFIED |
| S4R_0875_E1_50400 | E1 | 0.9 | inp VERIFIED, manifest VERIFIED |
| S4R_0875_E2_50400 | E2 | 0.9 | inp VERIFIED, manifest VERIFIED |

## Sensitivity matrix (all tracked terms)

| Term | f0 (Hz) | s_E1 | s_E2 | s_G12 | s_E (E1=E2) |
|---|---|---|---|---|---|
| FE7 | 19.072 | +0.0084 | +0.0086 | +0.4788 | +0.0169 |
| FE10 | 71.850 | +0.3527 | +0.0060 | +0.1687 | +0.3587 |
| FE11 | 72.190 | +0.0039 | +0.3562 | +0.1672 | +0.3601 |
| FE12 | 116.580 | +0.1354 | +0.1438 | +0.2451 | +0.2792 |
| FE13 | 167.490 | +0.4986 | +0.0008 | +0.0001 | +0.4994 |
| FE14 | 168.608 | -0.0009 | +0.5004 | +0.0001 | +0.4994 |
| FE15+FE16 | 177.331 | +0.2230 | +0.2259 | +0.0646 | +0.4489 |
| FE17 | 213.199 | +0.3029 | +0.0509 | +0.1694 | +0.3538 |
| FE18 | 213.953 | +0.0429 | +0.3123 | +0.1683 | +0.3552 |

Terms without every sensitivity (tracking refused in a variant): FE8, FE9, FE19, FE20.

Close FE pairs (`confirm_cluster`): FE10/FE11 INDEPENDENT; FE13/FE14 INDEPENDENT; FE15/FE16 CONFIRMED; FE17/FE18 INDEPENDENT

## Rank

| Problem | Singular values | Condition | Rank (rcond 1e-3) | Weakest direction |
|---|---|---|---|---|
| E1, E2, G12 | 0.8931, 0.6630, 0.5036 | 1.8 | 3 | {'E1': -0.3777, 'E2': -0.3732, 'G12': 0.8474} |
| E (E1 = E2), G12 | 1.1865, 0.5360 | 2.2 | 2 | {'E (E1=E2)': -0.3267, 'G12': 0.9451} |

Column cosines (E1, E2, G12): [[1.0, 0.1886, 0.3651], [0.1886, 1.0, 0.3718], [0.3651, 0.3718, 1.0]]

## M5 practical identifiability (design study; provisional Σ_setup 0.3 %)

| Case | Status | Conditional sd (ln) | Refusal |
|---|---|---|---|
| all tracked FE terms, E1 / E2 / G12 | FULL_RANK | 0.44 %, 0.44 %, 0.54 % | — |
| all tracked FE terms, E (E1 = E2) / G12 | FULL_RANK | 0.30 %, 0.54 % | — |
| CANDIDATE_ONLY rows only (hypothetical pairing), E1 / E2 / G12 | RANK_DEFICIENT | — | rank 1 < 3 parameters at rcond 0.001 (smallest/largest singular value 0); SPEC §10 hard block, no override |
| CANDIDATE_ONLY rows only (hypothetical pairing), E (E1 = E2) / G12 | RANK_DEFICIENT | — | rank 1 < 2 parameters at rcond 0.001 (smallest/largest singular value 0); SPEC §10 hard block, no override |

## Bounded LM on a linear surrogate — HYPOTHETICAL_PAIRING / RESEARCH_ONLY

Pairs used (CANDIDATE_ONLY rows of the research matching; not confirmed pairs): EXP1 18.6307 Hz ↔ FE7.

Surrogate: ln f_t(p) = ln f_t0 + Σ s_tj ln(p_j / p_j0) with the secants above; residual / 0.003. Each evaluation is a surrogate evaluation, not an Abaqus solve. The result shows the method; it is NOT a property of the carbon plate (one term, a linear extrapolation of secants, no admissible registration).

```json
{
 "G12": {
  "status": "CONVERGED",
  "parameters": {
   "G12": 4761.544672981767
  },
  "ratio_to_baseline": {
   "G12": 0.9523089345963534
  },
  "objective": 3.040976768184767e-05,
  "evaluations": 4,
  "local_sd_ln": [
   0.006265898233862836
  ],
  "refusal": null
 },
 "E": {
  "status": "CONVERGED",
  "parameters": {
   "E": 28000.0
  },
  "ratio_to_baseline": {
   "E": 0.5
  },
  "objective": 7.594543682706184,
  "evaluations": 4,
  "local_sd_ln": [
   0.17731318885416192
  ],
  "refusal": null
 },
 "E+G12": {
  "status": "STEP_ERROR",
  "reason": "J\u1d40J is not positive definite."
 }
}
```
