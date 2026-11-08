# REAL-FIT.R6.D1: diagnosis of the low-order mesh convergence of ranks 1 and 6

Status: **REAL-FIT.R6.D1 REVIEW_READY**. This is an offline diagnosis only:
- no Abaqus run, datacheck, FE solve, optimisation or fitting;
- frozen protocols, gates and R4/R5/R6 data unchanged;
- M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged.

## 1. Inputs

**Git state:**
- branch `feature/materials-offline-v1`;
- HEAD `52f354d8d742aa9403573248cd4e4e153419b6cd`, equal to origin;
- `origin/main` `0bea1de68dc346d20958e6f53a9e1d634a870f5d`;
- tracked tree clean; 25 untracked items preserved.

**Governing references:**
- [REAL_FIT_R6_PREFLIGHT_REPORT.md](REAL_FIT_R6_PREFLIGHT_REPORT.md) and [REAL_FIT_R6_FE_REPORT.md](REAL_FIT_R6_FE_REPORT.md);
- §9–10 of [ABM_Materials_Implementation_EN.md](ABM_Materials_Implementation_EN.md): observed order, no forced p = 2,
  numerical error kept separate from measurement uncertainty.

**Data used, read only:** the six existing packages (R6 50 and 200, R5 100, for A and B), their `.dat` and `.msg`
files, the R4 decks and `results_r5.json`.

**Script and outputs** (in `D:\git\abaqus-modal-comparator-work\runs\real_fit_r6_diagnostic\`):
- script `diagnose_r6.py` (SHA `edb81a37…`) reads the raw package manifests directly. It is independent of the frozen
  R6 analysis code;
- results in `diagnostic_r6_d1.json` (SHA `6610f5c3…`), console log in `diagnose_console.txt`.

**Integrity check after the run:**
- all 31 R4/R5/R6.0 inputs listed in the R6.1 manifest are unchanged;
- 149 of 150 R6.1 output files are unchanged. The one exception is `finalize_console.txt`. In R6.1 its hash was taken
  before `tee` wrote the last console line, which is a minor R6.1 manifest defect; no solver or result file differs;
- no solver process is running.

## 2. Independent recalculation

For each branch p, f_ext and δ were recomputed from three sources:
- the full single-precision ODB **EIGFREQ** history, the same source R6.1 used;
- √EIGVAL/2π from the EIGVAL history;
- the 5-significant-digit `.dat` table.

All branches use the same mode numbers on all levels (modes 7–20 elastic, 1–6 rigid).

| Rank (mode) | p, EIGFREQ: A / B | p, √EIGVAL: A | p range, ±2 float32 ulp: A | p from `.dat`, rounding range: A |
|---|---|---|---|---|
| 1 (7) | 0.3006 / 0.2996 | 0.3010 | 0.298–0.303 | 0.32 (0.15–0.65) |
| 6 (12) | 0.7199 / 0.7085 | 0.7199 | 0.718–0.722 | 0.81 (0.26–1.42) |
| 2, 3, 7, 9, 14 | 1.996–2.002 | same | ±0.005 | 1.5–2.4 |
| 4, 5 | 1.03–1.14 | same | ±0.004 | 0.84–1.30 |
| 8, 10 | 1.81–1.85 | same | ±0.002 | 1.4–2.2 |
| 11–13 | 1.28–1.46 | same | ±0.002 | 1.1–1.7 |

**Reproduction:** the R6.1 values of p, f_ext and δ are reproduced exactly from EIGFREQ.

## 3. Candidate causes checked

| Candidate | Evidence | Verdict |
|---|---|---|
| Frequency precision / roundoff | Relative differences between grids are 4.2e-4 to 3.7e-3, against a float32 ulp of about 1e-7 and Lanczos criterion 1.8e-12. A ±2-ulp perturbation moves p by ≤ 0.005. EIGFREQ and √EIGVAL agree within 6e-8 | **Excluded** |
| Wrong frequency source | R6.1 used EIGFREQ (18.70528793 Hz), not the 5-digit frame or `.dat` value (18.705). The `.dat` values alone would give p uncertain by up to ±0.6 | **Excluded**; the `.dat` table is not adequate for p |
| Extraction | All six packages come from the same pinned extractor; ODB hashes were unchanged by extraction; EIGFREQ and EIGVAL are consistent | **Excluded** |
| Node coordinates / refinement ratio | The decks are generated and nested, with ratio exactly 2 in x and y. Lattice coordinates agree within 1.5e-5 mm (float32 output). The elements are identical rectangles | **Excluded** |
| Branch tracking | Rank 1 is the same mode 7 on all levels, MAC 1.0000000 (second-best ≤ 0.005). U3 MAC with the anticlastic field (x−x̄)(y−ȳ) is 1.000. Rank 6 has MAC ≥ 0.9999996 | **Excluded** |
| Solver anomalies | Lanczos converged in one run of 10 steps, block size 7. No warnings or errors. The 6 rigid modes have \|λ\| ≤ 6e-4 (f ≤ 0.004 Hz). The `.dat` echoes no hourglass or transverse-shear keyword; defaults are in force | **No evidence** of a numerical problem |
| Non-monotone or mixed error | All differences are positive and R = e21/e32 is in (0, 1). The rank-1 grid ratio 0.81 means the differences barely shrink | p is an **effective** pre-asymptotic order; see §4 |

## 4. What explains the pattern

**Confirmed association.** The observed order falls as the twisting content of the mode rises. The twisting content is
the Kirchhoff twisting-energy share 2·∂ln f/∂ln G12, taken from the R5 Ritz surrogate. That surrogate is offline and
forward-only, and its frequencies reproduce R5 exactly.

| Rank | Twisting share | p (A) | Ritz above S4R f_ext (A) |
|---|---|---|---|
| 1 | 0.965 (pure twist, xy-MAC 1.000) | 0.30 | +0.34 % |
| 6 | 0.432 | 0.72 | +0.19 % |
| 4, 5, 11, 12, 13 | 0.25–0.33 | 1.04–1.46 | +0.08–0.20 % |
| 8, 10 | 0.09–0.12 | 1.81–1.85 | +0.07 % |
| 2, 3, 7, 9, 14 | 0.000 | 2.00 | +0.01–0.07 % |

- **Correlation of p with twisting share:** Pearson −0.945 (A) and −0.944 (B); Spearman −0.88 and −0.89.
- **Correlation of p with the Ritz−S4R gap:** Pearson −0.88.
- **Modes without twisting** converge at p ≈ 2.0, the textbook value for this element. Low p occurs **only** in modes
  with twisting.

**Hypotheses, not confirmed.** Neither can be separated from the other with the existing data.

- **H1, free-edge boundary layer of the shear-deformable shell.**
  - S4R is a Reissner–Mindlin-type element. At a free edge it carries a twisting-moment / transverse-shear boundary
    layer of width about the thickness, 0.875 mm.
  - All three element sizes (1.5–6 mm) are wider than that layer. The meshes would therefore be pre-asymptotic for
    twisting modes: refinement progressively resolves the edge softening, which the Kirchhoff model lacks.
  - Consistent with this: the Kirchhoff-Ritz value lies above S4R exactly in the twisting modes. The pure-twist gap,
    0.34 %, is of order t/a ≈ 0.003.
  - The size of this effect depends on the **assumed** G13 = G23 = 3000 MPa.
- **H2, S4R reduced integration and its default hourglass control.** The constant-twist field is the hourglass-type
  deformation of a one-point quadrilateral. Artificial hourglass stiffness that converges at a different rate would also
  act mainly on twisting modes. Hourglass energy was not requested in the output, so this cannot be checked.
- **Excluded or unlikely as explanations of the pattern:** precision, extraction, geometry and tracking (§3).

## 5. Sensitivity of f_ext and δ to p

Using f200 and f100 of the same branch:

| Rank (A) | δ200, observed p | δ200 at p = 1 | δ200 at p = 2 | δ100, observed p | δ100 at p = 2 |
|---|---|---|---|---|---|
| 1 | 0.180 % (p 0.30) | 0.042 % | 0.014 % | 0.222 % | 0.056 % |
| 6 | 0.056 % (p 0.72) | 0.036 % | 0.012 % | 0.093 % | 0.049 % |
| 4 | 0.025 % (p 1.04) | 0.026 % | 0.009 % | 0.051 % | 0.035 % |
| 13 | 0.037 % (p 1.28) | 0.054 % | 0.018 % | 0.091 % | 0.072 % |
| 2 | 0.004 % (p 2.00) | 0.011 % | 0.004 % | 0.015 % | 0.015 % |

- **Twisting modes:** the extrapolation depends strongly on p. For rank 1, δ200 varies by a factor of 13 between p = 2
  and the observed p = 0.30. Assuming p = 2 would understate it, which is why p = 2 is not imposed.
- **No rigorous bound:** if the meshes are pre-asymptotic for twisting, the observed p is an effective value. Even
  f_ext(p = 0.30) does not bound the true limit:
  - if convergence accelerates once h < t, the remaining change is smaller;
  - if the boundary layer softening continues, it may be larger.

  The twisting-mode error estimates are therefore indicative only.
- **Modes without twisting** (ranks 2, 3, 7, 9, 14, and approximately 8, 10) are in a credible p ≈ 2 regime. Their
  δ200 ≤ 0.03 % is reliable to the usual three-grid standard.
- **Effect on the R6.1 conclusions:** small.
  - The PolyMAX FIT RMS changes only in the fourth decimal: 0.01378 → 0.01369 → 0.01363 for A.
  - The rank-1 residual moves at most from +0.44 % (100×100) to +0.22 % (f_ext).
  - Even with an unbounded twisting error several times larger, the 1–3 % residual pattern would remain.
  - The Ritz−S4R comparison for twisting modes (up to 0.34 %) is a lower estimate of the Kirchhoff/Mindlin model
    difference under H1.

## 6. Conclusions without further FE runs

**Established:**
- the low p is real;
- it is not caused by precision, extraction, geometry, tracking or solver anomalies;
- it is systematically linked to the twisting content of the modes;
- non-twisting modes converge at p ≈ 2;
- the R5/R6 discretisation error for the 100×100 mesh is ≤ 0.06 % for non-twisting ranks; for twisting ranks it is
  about 0.04–0.22 %, with an unbounded p-dependent component;
- the R6.1 statements about the PolyMAX residuals stand.

**Not established:**
- the physical or numerical mechanism (H1 or H2 or both);
- whether the meshes are in the asymptotic range for twisting modes;
- the true converged frequency of rank 1, to better than about 0.2 %.

**Gate unchanged:** the uncertainty-relative mesh gate remains NOT_EVALUABLE because u(ln f_exp) is unavailable.

## 7. Recommendation: smallest justified verification (not authorised, not run)

**V1, one job (recommended first).** Variant A on a 400×400 S4R mesh.
- **Deck:** the same family, built by the R6.0 generator, which reproduces the R4 deck byte for byte; no other change.
- **Analysis:** the (100, 200, 400) triplet gives a second observed p per branch, using the existing tracking on the
  common lattice.
- **Expected outcome:**
  - if the twisting-mode p rises toward 2 at h = 0.75 mm < t, the meshes were pre-asymptotic, supporting H1, and a
    credible f_ext follows;
  - if p stays about 0.3, the low order persists. That points to an element-formulation effect (H2) or to non-power-law
    error.
- **Estimated cost:** 160 000 elements, about 0.97 M equations, memory about 10 GB to minimise I/O (the 200×200
  figure of 2.3 GB scaled), wall time a few minutes, disk about 0.4 GB.
- **Variant B is not needed:** A and B show the same behaviour within 0.01 in p.

**V2, only if V1 does not decide the question** (1–2 jobs each, separate authorisation):
- **V2a:** the A 200×200 deck with G13 = G23 increased tenfold, as a numerical diagnostic only. Under H1 the
  twisting-mode Ritz−S4R gap and the low-p behaviour should shrink markedly.
- **V2b:** the A 100×100 and 200×200 decks with S4 (full integration, no hourglass control), to test H2.

Neither V2 variant is a parameter change for identification.

**Not recommended:** an R6.1 rerun, a change of the frozen protocol, imposing p = 2, or treating any δ as a measurement
uncertainty.

REAL-FIT.R6.D1 REVIEW_READY. STOP: awaiting owner review.
