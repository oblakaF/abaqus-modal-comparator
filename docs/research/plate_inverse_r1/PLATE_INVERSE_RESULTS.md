# PLATE_INVERSE_RESULTS — first bounded inverse fit of the M11 plate (RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY)

| Сценарий | Использованные моды | E1 (МПа) | E2 (МПа) | G12 (МПа) | Ошибка частот | Ранг | Ограничения |
|---|---|---|---|---|---|---|---|
| S0 | EXP1 ↔ FE7 | 56000 (fixed) | 56000 (fixed) | 4763 | EXP1 +2.37 % → +0.0023 % | 1 of 1 (cond 1.00) | linear approximation (not an Abaqus solve); hypothetical pairing; E1, E2 fixed (not fitted); square system: zero residual by construction, no test of fit |
| H1 | EXP1 ↔ FE7; EXP8 ↔ FE15+FE16 | 43467 | 43467 | 4804 | EXP1 +2.37 % → +0.0008 %; EXP8 +12.34 % → +0.0114 % | 2 of 2 (cond 1.17) | linear approximation (not an Abaqus solve); hypothetical pairing; E1 = E2 imposed (SPEC v1.1 §5.2); E1 / E2 not separable: rank 2 of 3 on these modes; EXTRAPOLATION beyond ±5 %: E ×0.776; square system: zero residual by construction, no test of fit |
| H2 | EXP1 ↔ FE7; EXP7 ↔ FE14 | 41953 | 41953 | 4810 | EXP1 +2.37 % → +0.0019 %; EXP7 +15.54 % → +0.0144 % | 2 of 2 (cond 1.05) | linear approximation (not an Abaqus solve); hypothetical pairing; E1 = E2 imposed (SPEC v1.1 §5.2); E1 / E2 not separable: rank 2 of 3 on these modes; EXTRAPOLATION beyond ±5 %: E ×0.749; square system: zero residual by construction, no test of fit |

Every number above is RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY: the pairings are hypotheses (no admissible physical registration exists for 261027), and the forward model is the log-linear approximation of the PRIORITY-2 central sensitivities, not a new Abaqus solve.

## Real FE result against the approximation

- **Real Abaqus solve** `M11_S4_G12_MINUS` (G12 = 4 750 MPa, PRIORITY-2): FE7 = 18.60554 Hz.
- **Linear approximation** at the same point: 18.60577 Hz (difference +0.0013 %).
- EXP1 = 18.6307 Hz: the real FE7 at 4 750 MPa is -0.135 % from it (baseline +2.37 %).
- S0 lies inside the solved ±5 % range (G12 ×0.9527): an interpolation between real solves. H1 / H2 need E far outside it: an extrapolation that only a real solve at that point can check.

## Scenarios in detail

### S0 — EXP1 ↔ FE7

- Note: one-mode research problem; E1, E2 fixed at 56 000 MPa.
- Status of `run_bounded_lm`: **CONVERGED**; evaluations of the approximation 4; objective Φ = 3.04e-05; at bound: none.
- Solution: G12 ×0.9527; direct solve of the same equations: G12 ×0.9526.
- Local sd(ln p) with the provisional σ 0.3 % (a scale, not the real accuracy): 0.62 %.
- Rank of the fitted parameters: 1, singular values 0.4827; rank for E1 / E2 / G12 on the same modes: 1.

### H1 — EXP1 ↔ FE7; EXP8 ↔ FE15+FE16

- Note: EXP8 lies in the FE15/FE16 span (two-mode subspace 0.92, single MAC 0.43): a hypothesis, not a pair.
- Status of `run_bounded_lm`: **CONVERGED**; evaluations of the approximation 6; objective Φ = 0.000728; at bound: none.
- Solution: E ×0.7762, G12 ×0.9609; direct solve of the same equations: E ×0.7760, G12 ×0.9609.
- Local sd(ln p) with the provisional σ 0.3 % (a scale, not the real accuracy): 0.67 %, 0.62 %.
- Rank of the fitted parameters: 2, singular values 0.5031, 0.4314; rank for E1 / E2 / G12 on the same modes: 2.

### H2 — EXP1 ↔ FE7; EXP7 ↔ FE14

- Note: stress test: EXP7 ↔ FE14 research MAC 0.79 < 0.80 and |Δf| 15.5 % > the 15 % window.
- Status of `run_bounded_lm`: **CONVERGED**; evaluations of the approximation 6; objective Φ = 0.00117; at bound: none.
- Solution: E ×0.7492, G12 ×0.9621; direct solve of the same equations: E ×0.7489, G12 ×0.9620.
- Local sd(ln p) with the provisional σ 0.3 % (a scale, not the real accuracy): 0.60 %, 0.62 %.
- Rank of the fitted parameters: 2, singular values 0.5029, 0.4794; rank for E1 / E2 / G12 on the same modes: 2.

## H1 against H2 (no scenario is chosen)

- E: H1 ×0.7762, H2 ×0.7492 (difference -3.5 %); G12: H1 ×0.9609, H2 ×0.9621.
- G12 is set by FE7 in both (s_G12 0.483, s_E 0.016), so it barely depends on the second assignment; E is set entirely by the second, hypothetical assignment. Both ask for E about 22–25 % below the baseline, far outside the ±5 % that was solved.
- Both are square systems (two modes, two parameters): their zero residual says nothing about which assignment is right. No scenario is selected by frequency error or MAC.
- Cross-check of the two hypotheses (not used to choose): at the H1 solution FE14 = 148.56 Hz against EXP7 145.94 Hz (+1.8 %); at the H2 solution FE15+FE16 = 155.37 Hz against EXP8 157.85 Hz (-1.6 %). The two hypotheses ask for nearly the same E shift; this is their mutual consistency inside the approximation, not evidence for either assignment.

## E1, E2, G12: rank of the observations actually available

| Observation set | Terms | Rank (of 3) | Condition |
|---|---|---|---|
| CANDIDATE_ONLY rows (EXP1 ↔ FE7) | FE7 | 1 | 1.00 |
| H1 rows | FE7, FE15+FE16 | 2 | 1.55 |
| H2 rows | FE7, FE14 | 2 | 1.04 |
| H1 ∪ H2 rows (not a scenario) | FE7, FE15+FE16, FE14 | 3 | 2.81 |
| every tracked FE term (model capacity, not observations) | FE7, FE10, FE11, FE12, FE13, FE14, FE15+FE16, FE17, FE18, FE19 | 3 | 1.83 |

- With EXP1 ↔ FE7 alone (the only CANDIDATE_ONLY row) only G12 is determined.
- H1 and H2 each give rank 2: E1 and E2 move together on FE7 and FE15+16, and FE14 informs E2 only. No independent E1 / E2 is given.
- The union of H1 and H2 would reach rank 3 only by joining two unconfirmed hypotheses; it is not fitted.

## FE predictions at each solution (FE values only; never paired with a record)

| Term | f0 Hz | S0 | H1 | H2 |
|---|---|---|---|---|
| FE7 | 19.072 | 18.631 | 18.631 | 18.631 |
| FE10 | 71.850 | 71.379 | 65.171 | 64.347 |
| FE11 | 72.190 | 71.722 | 65.461 | 64.630 |
| FE12 | 116.580 | 115.400 | 107.451 | 106.384 |
| FE13 | 167.490 | 167.489 | 147.580 | 144.990 |
| FE14 | 168.608 | 168.607 | 148.565 | 145.957 |
| FE15+FE16 | 177.331 | 176.919 | 157.869 | 155.372 |
| FE17 | 213.199 | 211.787 | 193.470 | 191.037 |
| FE18 | 213.953 | 212.546 | 194.111 | 191.663 |
| FE19 | 295.776 | 293.496 | 269.723 | 266.555 |

Experimental 261027 records for reference: EXP1 18.6307, EXP2 54.6193, EXP3 63.4950, EXP4 66.8467, EXP5 74.2149, EXP6 112.2655, EXP7 145.9357, EXP8 157.8508, EXP9 169.1849, EXP10 180.1363, EXP11 191.6019 Hz.

## Settings

`identification_step.run_bounded_lm`, ln p, bounds [0.5, 2] × baseline, σ = 0.003 (scale), settings {"mu_initial": 0.001, "mu_decrease": 10.0, "max_step_attempts": 8, "solve_budget": 200, "max_iterations": 50, "stop_fraction": 0.2, "mu_increase": 10.0, "finite_difference_step": 0.05}. Sensitivity table SHA-256 `50136be13b38021251feb9c8f4fb74cfb052801bbeeba99e9b7f3efd90864ee8`; experiment SHA-256 `76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d` (refused on any other content). No Abaqus solve, no production Auto-ID, no change to SPEC, DECISIONS, STATUS or registrations.
