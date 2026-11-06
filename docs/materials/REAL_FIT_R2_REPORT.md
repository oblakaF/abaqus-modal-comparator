# REAL-FIT.R2 report: stability of the frequency-based parameter estimates

Status: **REAL-FIT.R2 REVIEW_READY**. Not self-accepted.

For the owner and the reviewer. Base `b52e7d757025ad7375a9354d2cb83f216b12cc6a`; branch `feature/materials-offline-v1`. The commit
SHA is in the hand-over.

Every result is labelled **EXPLORATORY_FE_INPUT_CANDIDATE — NOT_A_MATERIAL_PROPERTY — NOT_VALIDATED_IN_ABAQUS**.

**Governance.**
- This is the research tool of REAL-FIT.R1, unchanged in status. The governed inverse workflow still refuses real data
  (`NOT_AUTHORIZED`).
- Production Auto-ID was not used. SPEC v1.2, M8 GATE NOT_MET and D-077 NO_GLOBAL_PARAMETER_VALUE are unchanged.
- No Abaqus run, FE solve, file change or new data request took place. The INP, .dat and UNV were only read; their hashes
  were equal before and after.
- No material value, measurement uncertainty or target frequency was introduced.

## Answer

**The 10 % target is not demonstrated, and these data cannot demonstrate it.**

- **Numerical stability: within 10 %.** No single FIT record moves any estimate by more than 10 %. The largest change is G12 of
  the tied model, +9.4 % without record 1, which leaves little margin.
- **Frequency fit: does not decide it.** The orthotropic fit reproduces the FIT frequencies to 1.4 % RMS. The tied fit leaves
  4.8 % RMS, which is model-form error.
- **Parameter accuracy: not demonstrated.** No independent reference value exists. The absolute moduli also scale exactly with
  the assumed thickness and density, which are not measured here.

**Control by one record.** One record controls each of these estimates disproportionately:
- **G12 in both models:** record 1, the lowest mode at 18.63 Hz.
- **E_stiff:** record 9.
- **E_soft:** record 7.

## Baseline preserved

Full-data fits on the real files, with the default rank hypothesis, records 1–9 FIT and 10–11 HOLDOUT, gave the same output
as REAL-FIT.R1.F2 for both models. The serialised results were compared field by field, solve counts included, and no field
differs. Record 1 stays in the full-data fit.

| Model | Status | Full-data estimates (MPa) | FIT / HOLDOUT RMS (ln f) |
|---|---|---|---|
| E1 = E2, G12 | NUMERICALLY_SUPPORTED, with misfit warning | E 50 006, G12 4 903 | 0.0480 / 0.0590 |
| E1, E2, G12 | E1_E2_AXIS_ASSIGNMENT_NOT_IDENTIFIABLE | E_stiff 59 643, E_soft 43 593, G12 4 824 | 0.0137 / 0.0239 |

The only change to existing code paths:
- `_solve` accepts optional bounds. With no bounds, as in every existing call, it behaves exactly as before.
- `export_document` accepts an optional stability block. With none, the export holds `"stability": null`.

## Method

In `src/services/research_frequency_stability.py`:

1. **One refit per FIT record.**
   - Only that record leaves the fit.
   - Every other record keeps its declared surrogate rank and its role. Nothing is renumbered, rematched or optimized, and
     a test records the rank of every observation in every problem solved.
   - Each refit uses the full fit's bounds and parameterization and starts from the full-data minimum, with the same start
     pattern.
   - The orthotropic model also searches for the exchanged E1/E2 minimum, as the full fit does.
2. **Comparison without an axis.**
   - Tied model: `E (E1 = E2)` and `G12`. Orthotropic model: `E_stiff`, `E_soft` and `G12`.
   - The primary change uses the refit's minimum in the full fit's own axis assignment, so it measures the record's
     influence.
   - When the lowest cost of a refit lies in the exchanged assignment, that minimum is also reported. It is included in the
     largest change used for the 10 % check. The two mirror minima are not exactly symmetric, by about 1.5 % in E_stiff.
3. **Reported for every refit:**
   - changes of the estimates;
   - FIT RMS;
   - the left-out record's own prediction error;
   - HOLDOUT RMS;
   - practical rank and condition number;
   - convergence of every start;
   - active bounds;
   - mirror pair, exchanged lowest cost, and any further minimum with its cost ratio.
4. **Control by one record**, a numerical reporting policy and not an accepted scientific threshold. A record is flagged when
   its own leave-out change carries more than 50 % of the parameter's summed squared leave-out changes and is at least 1 %.
5. **Local influence coefficients.**
   - Source: the full fit's own sensitivity matrix J = d ln f / d ln p.
   - Coefficients: d ln p / d ln f_exp = J⁺, truncated at the full fit's practical rank.
   - Under rank deficiency, the parameters with a share of the undetermined directions are marked "not determined". Their
     coefficients are then the minimum-norm convention, not a result.
   - Also reported: leverage and the linearized leave-one-out change.
6. **Thickness and density**: the exact surrogate scaling, verified on the surrogate. No distribution or interval is given.
7. **The 10 % objective**, answered as three separate questions.

## Leave-one-FIT-record-out results (real data)

Every refit converged, kept full practical rank and had no active bound.

**E1 = E2, G12** (full: E 50 006, G12 4 903 MPa; FIT RMS 0.0480)

| Left out | Hz | Rank | E change | G12 change | FIT RMS | Left-out error | Cond. |
|---|---|---|---|---|---|---|---|
| 1 | 18.631 | 1 | −1.13 % | **+9.42 %** | 0.0500 | +5.64 % | 4.45 |
| 2 | 54.619 | 2 | +1.53 % | −0.94 % | 0.0490 | +4.28 % | 2.15 |
| 3 | 63.495 | 3 | −3.46 % | +2.26 % | 0.0401 | −9.79 % | 2.12 |
| 4 | 66.847 | 4 | +0.62 % | +1.11 % | 0.0497 | +3.30 % | 2.23 |
| 5 | 74.215 | 5 | −1.52 % | −2.56 % | 0.0434 | −7.99 % | 2.23 |
| 6 | 112.266 | 6 | +0.03 % | +0.18 % | 0.0509 | +0.28 % | 2.37 |
| 7 | 145.936 | 7 | +3.54 % | −2.12 % | 0.0400 | +9.84 % | 2.16 |
| 8 | 157.851 | 8 | +0.40 % | −0.25 % | 0.0508 | +1.11 % | 2.15 |
| 9 | 169.185 | 9 | −0.65 % | +0.05 % | 0.0504 | −2.20 % | 2.15 |

The left-out error is ln(f_model / f_exp) shown as per cent. In the tied model, records 3, 5 and 7 are predicted only to about
8–10 % when left out. The single tied modulus cannot reproduce the split pairs that the orthotropic model resolves.

**E1, E2, G12** (full: E_stiff 59 643, E_soft 43 593, G12 4 824 MPa; FIT RMS 0.0137)

| Left out | Rank | E_stiff | E_soft | G12 | FIT RMS | Left-out error | Cond. | Minima |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | −0.47 % | −0.50 % | **+4.04 %** | 0.0139 | +2.46 % | 3.49 | mirror pair |
| 2 | 2 | −0.01 % | −1.31 % | +0.47 % | 0.0132 | −2.07 % | 1.62 | mirror pair; lowest cost exchanged: −1.56 / −0.11 / +0.35 % |
| 3 | 3 | −1.49 % | −0.01 % | +0.41 % | 0.0135 | −1.91 % | 1.80 | mirror pair |
| 4 | 4 | +0.11 % | −0.68 % | −0.70 % | 0.0133 | −1.87 % | 1.64 | mirror pair |
| 5 | 5 | −1.04 % | +0.10 % | −0.53 % | 0.0132 | −1.97 % | 1.73 | mirror pair |
| 6 | 6 | +0.12 % | +0.05 % | +0.45 % | 0.0143 | +0.74 % | 1.78 | mirror pair |
| 7 | 7 | −0.01 % | **+1.80 %** | −0.61 % | 0.0121 | +2.77 % | 1.62 | mirror pair; lowest cost exchanged: −1.55 / **+3.21** / −0.75 % |
| 8 | 8 | −0.01 % | +0.33 % | −0.00 % | 0.0144 | +0.62 % | 1.59 | mirror pair |
| 9 | 9 | **+2.77 %** | −0.00 % | −0.72 % | 0.0110 | +3.47 % | 1.81 | mirror pair; further minimum at cost × 2.10 |

**Competing minimum without record 9.** A further, non-mirror minimum appears at E1 65 686, E2 42 784, G12 4 618 MPa. Its
cost is 2.10 times the lowest. The minimum is therefore not unique within the search range there. It is reported, not
hidden.

**Linear approximation.** For every record, the linearized leave-one-out change from J agrees with the refit, for example
+9.54 % against +9.42 % for G12 without record 1. That agreement holds once the refit stays in the same axis assignment.

## Which observed modes control each estimate

The shares for the local coefficients are shares of the squared coefficients. They would be variance shares only if every
frequency had the same independent error, which is not assumed.

| Estimate | Largest leave-out change | Its share of the squared changes | Controlled by one record | Strongest local coefficients (d ln p / d ln f_exp) |
|---|---|---|---|---|
| E (E1 = E2) | +3.54 % (record 7) | 40 % | no | records 2, 3, 7, 8: +0.354 each; 9: +0.294 |
| G12, tied | +9.42 % (record 1) | 83 % | **yes, record 1** | record 1: +1.597 (77 % of the squared sum); 6: +0.615 |
| E_stiff | +2.77 % (record 9) | 68 % | **yes, record 9** | records 9: +0.791, 3: +0.782, 5: +0.531 |
| E_soft | +1.80 % (record 7); +3.21 % at the exchanged lowest cost | 56 % | **yes, record 7** | records 7: +0.644, 2: +0.636, 8: +0.535 |
| G12, orthotropic | +4.04 % (record 1) | 88 % | **yes, record 1** | record 1: +1.612 (77 % of the squared sum); 6: +0.603 |

**How to read the coefficients:**
- A 1 % shift of the 18.63 Hz record alone moves G12 by about 1.6 %. No other record moves it by more than 0.6 % per 1 %.
- Record 1 has leverage 0.77–0.78 in the two models; every other record has 0.39 or less.
- The coefficients of each modulus sum to 2.000, because a common frequency factor c moves every modulus by c².
- Both models have full practical rank (2 of 2, 3 of 3). No parameter is undetermined locally.

## Exact dependence on thickness and density

With the measured frequencies, plan and nu12 fixed, every D_ij of the surrogate is proportional to E t³ and the mass per area
is ρ t. Therefore:

- **E_i(t, ρ) = E_i,fit × (ρ / ρ_INP) × (t / t_INP)^−2** with the density held.
- With a weighed plate, where the surface mass ρ·t is held, the factor is **(t / t_INP)^−3**.
- E1, E2 and G12 take the same factor. E_stiff / E_soft (1.368), E_stiff / G12 (12.36) and E / G12 (10.20) do not depend
  on t or ρ.
- The INP values are t = 0.875 mm and ρ = 1.498e-9 t/mm³.

| Input changed alone | Input factor that moves the absolute moduli by −10 % … +10 % |
|---|---|
| Thickness, density held | 0.9535 … 1.0541 (about −4.7 % … +5.4 %) |
| Thickness, surface mass held | 0.9687 … 1.0357 (about −3.1 % … +3.6 %) |
| Density | 0.9 … 1.1 |

**What these factors are not.** They are not uncertainties of the inputs; the evidence gives none.

**Surrogate check.** The scaling was checked on the surrogate at factor 1.03 for all three cases. The largest frequency
difference was 2.0e-15.

## The 10 % objective

| Question | Answer from these data | Basis |
|---|---|---|
| **Numerical stability**: does one frequency move an estimate by more than 10 %? | No. Tied: E 3.5 %, G12 9.4 %. Orthotropic: E_stiff 2.8 %, E_soft 3.2 %, G12 4.0 %. | Leave-one-out refits; all converged, full rank, no bound. Caveats: a further minimum without record 9; lowest cost in the exchanged assignment without records 2 and 7. |
| **Frequency fit**: does the surrogate reproduce the spectrum? | Orthotropic: FIT 1.4 %, HOLDOUT 2.4 % RMS. Tied: FIT 4.8 % RMS, a misfit warning. | Residuals; not a parameter error. |
| **Parameter accuracy**: are the moduli within 10 % of the truth? | **NOT_DEMONSTRATED** | See the reasons below. |

Why accuracy is not demonstrated:
- No independent reference value exists.
- Thickness and density are assumed. A thickness error of −4.7 % or +5.4 % alone would use the whole 10 %, or −3.1 % / +3.6 %
  for a weighed plate.
- The Kirchhoff-Ritz surrogate, the free-free support, nu12, the specimen identity and the rank correspondence are
  assumptions.
- The tied model's misfit enters its values.
- The orthotropic E1/E2 axis is unresolved.

**What could support the target.** Measured thickness and density would remove the largest named source. An independent
determination of G12 would check the record-1 dependence. Neither is available in this evidence, and this task does not
request them.

## GUI: the Research Tuning page

A fourth section, "4. Stability: leave one FIT record out", follows the result.

- **Check stability** runs the refits in the page's worker thread. It can be cancelled, and the other controls are locked
  while it runs. A new fit clears the old check.
- **Shown:**
  - the statement with the label;
  - the 10 % table with its three questions;
  - the refit table;
  - which records control each estimate;
  - the influence coefficients with the rank note;
  - the thickness/density table.
- **Export:** "Export proposal (JSON)..." writes the whole check under `stability`. `null` means no check was run for the
  shown result.

## Changed files

| File | Change |
|---|---|
| `src/services/research_frequency_stability.py` | New: refits, control, influence, thickness/density dependence, the 10 % assessment |
| `src/services/research_frequency_tuning.py` | `_solve(..., bounds=None)`; `export_document(..., stability=None)`; nothing else |
| `src/new_gui/research_tuning_model.py` | Row builders and headers for the stability tables |
| `src/new_gui/research_tuning_panel.py` | Section 4, the Check stability job, cancel, clear, export |
| `tests/test_real_fit_r2_stability.py` | New: 11 focused tests |
| `tests/test_new_gui1_workspace.py` | The new read-only service allowed for the page |
| `docs/materials/REAL_FIT_R2_REPORT.md` | This report |

## Tests and verification

Python 3.14 on Windows, one process at a time, one BLAS thread. The full suite was not run, as instructed.

**`test_real_fit_r2_stability`: 11 tests.**
- Exact data give stable refits, the baseline object stays unchanged, and accuracy is still `NOT_DEMONSTRATED`.
- A custom declared mapping keeps every rank and role in every problem solved. HOLDOUT never enters a fit.
- A record shifted by 3 % is found to control G12. Leaving it out recovers the generating values, and the linear and refit
  changes agree.
- Influence: J⁺J = I, coefficient sums equal 2, and the leverage trace equals the parameter count.
- A rank-deficient J marks both parameters undetermined.
- The thickness/density scaling holds to 1e-10 on the surrogate, and no distribution appears.
- The orthotropic model is compared without an axis.
- A 15 % shift gives `CHANGE_EXCEEDS_TARGET`.
- Refusals and cancellation work.
- The export carries the check.
- The page runs, cancels, shows and exports the check and clears it on a new fit.

**Earlier modules re-run.**

| Module | Tests | Result |
|---|---|---|
| `test_real_fit_r1_tuning` | 27 | unchanged, pass |
| `test_new_gui1_workspace` | 28 | pass |
| `test_universal_ui2_clean` | 20 | pass |
| `test_gui_ux_r1` | 79 | pass |

**Real data:** `D:\git\abaqus-modal-comparator-work\runs\real_fit_r2\probe_r2.py`, with results in `results_r2.json`.

**Windows GUI** (`gui_r2.py`, real `windows` platform, 1366 × 768):
- Both models ran: the fit, then Check stability, in 7.7 s and 19.5 s.
- The refit results equal the service probe exactly.
- While the check ran, Run was disabled and Cancel enabled.
- Both exports hold the check.
- No horizontal page scroll at 900 px; the wide refit table scrolls inside itself.
- No Cyrillic text.
- The source hashes are unchanged, and no process was started.
- Screenshots and exports are in the same folder.

## Limitations

- **Single-record refits only.** A leave-one-out refit tests dependence on one record. It does not test a missed or extra mode
  below the highest one, a wrong rank hypothesis, or errors shared by all records.
- **Thresholds are reporting policy.** The 50 % / 1 % control criterion and the 10 % comparison are numerical reporting
  policy; no scientific threshold was added or changed.
- **Exchanged assignment.** Comparing within the full fit's axis assignment isolates the record's influence. The exchanged
  lowest-cost minimum is shown beside it and is counted in the 10 % check.
