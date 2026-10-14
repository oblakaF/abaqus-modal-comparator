# Phase A4 — evidence required for nine independent constants

## Necessary conditions (all of them; none is sufficient alone)

1. **Rank.** At least as many independent, frozen, strictly paired observations as estimated parameters plus
   identified nuisance parameters. A confirmed cluster counts as one observation (SPEC §12.4). The full system
   (whitened data rows plus nuisance prior rows) must be full rank at rcond 1e-3 (SPEC §10). Rank deficiency is a
   hard block.
2. **Families.** SPEC v1.2 §8 asks, for k fitted parameters, for k + 1 distinct FIT modal families and one distinct
   HOLDOUT family. For nine constants that is ≥ 10 FIT families plus 1 HOLDOUT family.
3. **Precision.**
   - Moduli: sd_j ≤ 0.08 in ln p (SPEC §10) from the full system with the explicit Σ.
   - Poisson ratios: no accepted rule exists — see the contract proposal.
4. **Independence of columns.** More modes are not enough when the columns are nearly dependent. The residual
   information q_j after projection on every other column (including nuisance columns with evidence-backed priors)
   must not vanish.
5. **Sensitivity above numerical noise.** The SPEC S4 half-step repeat must agree within 5 %. A sensitivity of
   10⁻⁵ is not resolved, whatever its sign.
6. **Identity and registration.** These are unchanged governed rules:
   - physical registration;
   - strict baseline pairing (MAC ≥ 0.80, |Δf| ≤ 15 %);
   - FE-to-FE tracking (MAC ≥ 0.90);
   - no orientation by MAC;
   - no peak-derived modes.

## Evidence-requirements matrix

| Constant | Evidence that carries it | What usually confounds it | Plausible experiment | SP-13 today |
|---|---|---|---|---|
| E1 | bending / extension along axis 1; modes with large curvature in x | E2 (woven symmetry), t_face, core | free-free modal test with traceable warp axis; a bare laminate plate; off-axis specimens | only E1 = E2 jointly (2 rows) |
| E2 | the same along axis 2 | E1, t_face | same, fill axis traceable | jointly with E1 |
| E3 | through-thickness normal stress: thick specimens (h/L ≳ 0.2), thickness / breathing modes | ν13, ν23 | thick block (resonant ultrasound spectroscopy), through-thickness ultrasonic velocity, compression test | no signal (M6.4: 5·10⁻⁶) |
| ν12 | in-plane Poisson coupling: plate modes with anticlastic curvature, in-plane modes | E1, E2, G12 | bare plate with many families; in-plane modal test; strain-gauged tension test | weak; fixed 0.05 |
| ν13 | coupling of axis-1 stress to thickness strain: thick specimens | E3, ν23 | thick block / RUS; ultrasonic | no signal (M6.4: 1.3·10⁻⁶) |
| ν23 | coupling of axis-2 stress to thickness strain | E3, ν13 | thick block / RUS | no signal (M6.4: 7·10⁻⁶) |
| G12 | torsion-dominated families of plates | k_core, k_int, adhesive (sandwich) | bare plate (SPEC §5.1 primary source); Iosipescu / ±45° tension | partially, secondary (§5.1) |
| G13 | transverse shear: thick plates, higher-order bending modes, short beams | core shear, adhesive, G23 | thick laminate or short-beam modal tests; independent core-tile tests to remove the core | very weak (1.4·10⁻⁴), confounded with the core |
| G23 | the same in the 2–3 plane | core shear, adhesive, G13 | same, other direction | very weak (3.5·10⁻⁴) |

## Nuisance parameters that must be constrained independently for a sandwich

- **Face thickness t_face:** 9+ point measurements per sheet (SPEC §4).
- **Face separation d** (core height).
- **Core stiffness k_core:** needs an independent core-tile experiment (SPEC §5.3; the CARBON-5F scope is limited).
- **Adhesive / interface k_int.**
- **Density and masses.**
- **Suspension and attachment masses.**
- **Material-axis orientation:** traceable warp and fill, photographed.

## Multiple specimens

- Global (shared) constants across a family use SPEC §13 family consistency: Δχ² or bootstrap.
- Thickness and orientation variants, for example 0°/90°/±45° coupons, thick blocks or bare plates, add columns
  with different sensitivity directions. That is the only route that can separate E3, ν13, ν23, G13 and G23 from a
  thin-face sandwich family.

## Quantitative illustration (synthetic, independent block model)

The synthetic block has σ = 0.03 % per mode and 27 separated FIT families:

| Case | Outcome |
|---|---|
| thick block 26 × 12.6 × 8.8 mm, σ 0.03 %, 27 FIT families | all nine supported; recovery within 2σ for two noise seeds |
| same, σ 0.1 % | ν12 sd 0.054 and ν13 sd 0.094 > declared research limit 0.05 → question refused before optimisation (the six moduli and ν23 alone would pass) |
| thin plate 80 × 54 × 1.6 mm, σ 0.3 %, 18 FIT families | rank 6 < 9: E3, ν13, ν23 in the null space (weights ≈ 1) |
| same, E3 / ν13 / ν23 declared fixed | E1, E2, G12 supported; ν12 sd 0.061; G13 sd 9.4 %, G23 sd 22 % (> 8 %) |
| two accepted rows (SP-13-like) | rank ≤ 2: all nine NOT_IDENTIFIABLE, without any FE evaluation |

Synthetic recovery shows that the engine works. It does **not** show that SP-13 is identifiable.
