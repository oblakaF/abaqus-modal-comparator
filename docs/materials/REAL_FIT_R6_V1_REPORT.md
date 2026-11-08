# REAL-FIT.R6.V1: authorised 400×400 S4R convergence verification (variant A)

Status: **REAL-FIT.R6.V1 REVIEW_READY**.
- **Scope:** one Abaqus frequency solve (R6_A_M400) and one read-only extraction. This is a numerical forward-model
  check, not material identification.
- **Unchanged:** E1, E2, G12, ν12, the transverse constants, the R6.0/R6.1 protocols and all results.
- **Not selected:** variant A is not chosen as the physical axis assignment.
- **Status flags unchanged:** M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED.

## 1. Verified baseline and sources

**Git:**
- branch `feature/materials-offline-v1`; HEAD `80696b279ac8398a8d262ca3fa279bf8db86d173`, equal to origin;
- `origin/main` `0bea1de68dc346d20958e6f53a9e1d634a870f5d`;
- tracked tree clean; 25 untracked items preserved.

**Solver:** idle before the run.
- Launcher: `C:\SIMULIA\Commands\abaqus.bat`, SHA `35dddb92…`, which calls `abq2024.bat`.
- Free resources at start: 14.3 GB RAM and 190 GB on D:.

**Sources verified before and after the run:**
- the 31 R4/R5/R6.0 inputs from the R6.1 manifest, unchanged;
- the R6.1 outputs, unchanged, except the console log `finalize_console.txt`, already known from R6.D1;
- the R4 A deck `a0668c28…0c927`;
- the R6.1 results `eb72f34e…`;
- the frozen code: `r6_mesh.py` `e61ea6a5…`, `r6_convergence.py` `fdffd1b7…`, `r5_common.py` `9f26da4f…`.

## 2. The 400×400 deck and its static validation

**Generation:**
- the deck is `M11_RITZ_MINIMUM_A_M400.inp`, SHA-256
  `c7ecf90153b8d72b71f37cf49a091e9b63f1dfc9b25877076810c6d1c788de51`, 13 862 310 bytes;
- it was produced by the unchanged R6.0 generator from the immutable R4/R5 A deck;
- the frozen `r6_mesh.py` has heading texts only for n = 50/100/200. The 400 heading was therefore added to the
  imported module's dictionary at run time; the file itself is unchanged and its hash was checked.

**Required checks, all passed** (`static_verification_log.json`):
1. The generator still reproduces the A 100×100 deck byte for byte.
2. Mesh: 160 801 nodes and 160 000 S4R elements, with contiguous labels, defined connectivity and every node used.
   Every signed area is > 0, so every normal is +Z (160 000). The mesh is conforming, with 1 600 boundary edges.
   Element size is 0.7525 × 0.7500 mm.
3. Geometry and material:
   - box [−251, 50] × [−270, 30] mm, translated by (251, 270, 0); total area 90 300.000 mm²;
   - section `0.875, 5`, density 1.498e-9;
   - mass ρhA = 1.18360725e-4 t;
   - `*Elastic` equal to the R4 minimum as exact doubles; all other constants unchanged;
   - `material_axes` ESTABLISHED; `read_inp` 301 × 300 × 0.875 mm.
4. All non-mesh lines are identical to the R4 A deck. The project's `structure()` check finds identical groups.
5. The 51×51, 101×101 and 201×201 lattices are bit-identical between the 50/100/200 decks and the 400 deck.
6. There are no boundary-condition, load, constraint or orientation keywords. The step is the same Lanczos step with
   20 eigenvalues.
7. The R4/R5/R6 inputs were unchanged during preparation.

**Deviation for owner review: one supplementary check failed.**
- The check was the element-area uniformity tolerance, 1e-5 relative; it is not one of the required items. The
  result was a maximum of 1.73e-5.
- `area_precision_check.json` shows the cause is the family's single-precision coordinate convention (the
  Abaqus/CAE 9-significant-digit format):
  - the coordinate error in all decks is ≤ 7.0e-6 mm, below half a float32 ulp at 251 mm (7.6e-6);
  - the area deviation grows as 1/h: 3.3e-6 (100), 7.3e-6 (200), 1.73e-5 (400). The 400 value lies within the float32
    bound of 4.07e-5;
  - the RMS deviation is 5.2e-6 and the total area is exact.
- The 1e-5 tolerance was below the resolution of the coordinate format at this element size. The deck was accepted on
  that basis; the failed check is kept in the log unchanged.

**Frozen before the run:**
- comparison protocol `protocol/comparison_protocol_v1.json`, SHA `ed177007c3b0e349…`, read only;
- pre-run manifest `prerun_manifest.json`, SHA `d2ddccb3…`.

## 3. Abaqus execution evidence

| Item | Value |
|---|---|
| Command | `cmd.exe /d /s /c C:\SIMULIA\Commands\abaqus.bat job=R6_A_M400 input=M11_RITZ_MINIMUM_A_M400.inp cpus=1 interactive ask_delete=OFF` |
| Runner | the R6.1 `run_r6_jobs.run`, unchanged (SHA checked); RAM precondition ≥ 12 GB free; cap 1800 s |
| Version | Abaqus 2024 (stdout) |
| Start → end | 2026-11-08T19:28:27.7 → 19:29:24.2 (+08:00); **56.5 s**, exit code **0** |
| Completion | stdout "Abaqus JOB R6_A_M400 COMPLETED"; `.sta` "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"; no `***ERROR`; ODB present → **COMPLETED** |
| Warnings / errors | 0 / 0 |
| Modes requested / obtained | 20 / 20. Modes 1–6 rigid by shape (residual ≤ 0.02), 7–20 elastic |
| Total mass (`.dat`) | 1.1836073E-04 t |
| Memory estimate (`.dat`) | 501 MB minimum, 9 378 MB to minimise I/O |
| INP / DAT / STA / MSG | `c7ecf901…` / `7f2528bba9cf1441efb74a884f857b40c31411a57c00b7ce8d0581539b5c8af8` / `fe7a3b6319619fc48a1a1921ed7dbf61485a17290de17eb3be3e65fcf474964c` / `1fc88bb2a645501bbe4b8951a4e39e798042d7c33e538abdabe2a8bc7d33f312` |
| ODB | `4b1a0e99e20e101711d5f3f3a354cc6f81d4a0378d1588e1fc932586a27968ed` (89.6 MB) |
| Extraction | pinned workflow, `readOnly=True`, same extractor SHA as R5/R6.1. ODB SHA identical before extraction, after it and at job end. Package manifest `038edd85…` |
| DAT↔ODB agreement | within 3.5e-5 (5-digit DAT table) |

**Record files:** `jobs_record.json` `6da5a27d…`, `extraction_record.json` `01f49ceb…`, `results_v1.json`
`c00cbca5…`, `diagnostic_v1.json` `723635d4…`, `hash_manifest.json` `90e25e72…`.

**Total:** exactly **one** Abaqus job ran. There was no datacheck and no retry; no solver process remained afterwards.

## 4. Frequency and mode-tracking comparison

**Tracking:**
- FE-to-FE on the common 2 601-node lattice, with the frozen R6 tracker (MAC ≥ 0.90, unique);
- reference: R5 A100; consistency check: A200 → A400;
- both directions are TRACKED in pass 1 and pass 2, with no order changes;
- the frozen subspace {13, 14} is unique, cos² ≥ 0.9999997.

**Frequencies:** full-precision ODB EIGFREQ. The √EIGVAL/2π cross-check gives the same p to within 0.002. The `.dat`
table was not used.

| Elastic rank (mode) | p(50/100/200) | p(100/200/400) | f100 | f200 | f400 | Tracking (MAC 100↔400 / 200↔400) |
|---|---|---|---|---|---|---|
| 1 (7) | 0.30 | **1.10** | 18.71310 | 18.70529 | 18.70164 | TRACKED, 1.0000000 / 1.0000000 |
| 2 (8) | 2.00 | 2.00 | 53.85550 | 53.84932 | 53.84777 | TRACKED, 1.0000000 / 1.0000000 |
| 3 (9) | 2.00 | 2.00 | 62.75649 | 62.74920 | 62.74738 | TRACKED, 1.0000000 / 1.0000000 |
| 4 (10) | 1.04 | 1.31 | 65.79955 | 65.78229 | 65.77534 | TRACKED, 1.0000000 / 1.0000000 |
| 5 (11) | 1.14 | 1.35 | 73.06282 | 73.04636 | 73.03992 | TRACKED, 1.0000000 / 1.0000000 |
| 6 (12) | 0.72 | **1.20** | 112.85291 | 112.81184 | 112.79399 | TRACKED, 1.0000000 / 1.0000000 |
| 7 (13) | 2.00 | 2.00 | 148.74234 | 148.67812 | 148.66205 | TRACKED, 0.9999999 / 1.0000000 |
| 8 (14) | 1.81 | 1.79 | 158.59657 | 158.52441 | 158.50357 | TRACKED, 0.9999999 / 1.0000000 |
| 9 (15) | 2.00 | 2.00 | 172.80673 | 172.73215 | 172.71349 | TRACKED, 0.9999999 / 1.0000000 |
| 10 (16) | 1.85 | 1.83 | 181.65862 | 181.57770 | 181.55501 | TRACKED, 0.9999998 / 1.0000000 |
| 11 (17) | 1.37 | 1.47 | 197.83623 | 197.73824 | 197.70287 | TRACKED, 0.9999999 / 1.0000000 |
| 12 (18) | 1.46 | 1.53 | 213.90939 | 213.80823 | 213.77309 | TRACKED, 0.9999999 / 1.0000000 |
| 13 (19) | 1.28 | 1.43 | 285.47830 | 285.32510 | 285.26807 | TRACKED, 0.9999999 / 1.0000000 |
| 14 (20) | 2.00 | 2.00 | 291.65613 | 291.38602 | 291.31851 | TRACKED, 0.9999997 / 1.0000000 |

The second-best MAC is ≤ 0.006 for every row, and all triplets are MONOTONE.

## 5. Old and new convergence estimates

δh = ln(fh/f_ext) for the triplet indicated. ρ is the ratio of consecutive differences: (f100−f200)/(f50−f100), then
(f200−f400)/(f100−f200).

| Rank | ρ old → new | f_ext old (50/100/200) | f_ext new (100/200/400) | Shift of f_ext | δ100 old → new | δ200 old → new | δ400 new | GCI400 |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.812 → 0.467 | 18.6716 | 18.6984 | +0.144 % | 0.222 → 0.078 % | 0.180 → 0.037 % | 0.017 % | 0.021 % |
| 4 | 0.487 → 0.402 | 65.7659 | 65.7707 | +0.007 % | 0.051 → 0.044 % | 0.025 → 0.018 % | 0.007 % | 0.009 % |
| 5 | 0.454 → 0.391 | 73.0327 | 73.0358 | +0.004 % | 0.041 → 0.037 % | 0.019 → 0.014 % | 0.006 % | 0.007 % |
| 6 | 0.607 → 0.435 | 112.7484 | 112.7803 | +0.028 % | 0.093 → 0.064 % | 0.056 → 0.028 % | 0.012 % | 0.015 % |
| 11–13 | 0.36–0.41 → 0.35–0.37 | — | — | +0.002–0.006 % | 0.07–0.09 % | 0.03 % | 0.009–0.012 % | 0.011–0.015 % |
| 2, 3, 7, 9, 14 | 0.250 → 0.250 | — | — | ≤ 0.0001 % | 0.015–0.124 % (unchanged) | 0.004–0.031 % | 0.001–0.008 % | 0.001–0.010 % |
| 8, 10 | 0.28 → 0.28–0.29 | — | — | −0.0003 % | 0.06 % | 0.02 % | 0.005 % | 0.006–0.007 % |

**Sensitivity of the new δ400 to p:**
- **rank 1:** 0.0065 % at p = 2, **0.017 % at the observed 1.10**, 0.047 % at p = 0.5;
- **rank 6:** 0.005 % / 0.012 % / 0.038 %;
- non-twisting modes: unchanged from p = 2.

**Conditional bracket.** Assume that the consecutive-difference ratios do not increase beyond the last observed ρ.
This holds for every twisting mode so far, but it is an assumption. The converged value then lies between f_ext new
and f400:
- rank 1: [18.6984, 18.7016] Hz, a width of 0.017 %;
- rank 6: [112.7803, 112.7940] Hz, a width of 0.012 %.

**Experimental diagnostic.** The unchanged R5 rank hypothesis is unverified; records 1–9 are FIT and 10–11 are
diagnostic HOLDOUT.

| Quantity | f100 | f400 | f_ext old | f_ext new |
|---|---|---|---|---|
| FIT RMS ln(f/f_EXP) | 0.01378 | 0.01367 | 0.01363 | 0.01366 |
| HOLDOUT RMS ln(f/f_EXP) | 0.02341 | 0.02285 | 0.02275 | 0.02277 |
| Record 1 residual | +0.44 % | +0.38 % | +0.22 % | +0.36 % |

The old rank-1 extrapolation (p = 0.30) overstated the remaining mesh correction. The 1–3 % residual pattern is
unchanged.

## 6. Answers on ranks 1 and 6

- **Rank 1: the observed order increases.** p rises from 0.30 to 1.10, and ρ falls from 0.81 to 0.47. The change from
  200 to 400 (1.95e-4) is less than half the change from 100 to 200 (4.18e-4).
- **Rank 6 behaves the same way:** p rises from 0.72 to 1.20, and ρ falls from 0.61 to 0.44. All other twisting modes
  (ranks 4, 5, 11–13) also rise, by 0.07 to 0.27. The non-twisting ranks 2, 3, 7, 9 and 14 stay at p = 2.00, with f_ext
  unchanged to 1e-6 relative.
- **Asymptotic regime:**
  - **Non-twisting modes:** consistent with the asymptotic regime. Two independent triplets give the same p ≈ 2 and
    the same f_ext.
  - **Twisting modes: not demonstrated.** Their p is still changing (1.1–1.5 against an apparent final value of up to
    2), so the 50/100/200 triplet was clearly pre-asymptotic. Whether 100/200/400 has reached the asymptotic range
    cannot be shown with one more level.
- **Effect on the estimated numerical error: material for twisting modes, nil for the others.**
  - The rank-1 error estimate for the R5 100×100 mesh falls from 0.22 % to 0.078 %, and its f_ext moves up by 0.144 %.
  - For the R5/R6 100×100 values every rank now has |δ100| ≤ 0.124 % (rank 14); for 400×400, |δ400| ≤ 0.017 %.
  - These are still discretisation estimates, not measurement uncertainties.
- **Mechanism: not established.**
  - The rise of p when h drops below the thickness (0.75 mm < 0.875 mm) is *consistent with* H1, the free-edge
    boundary layer becoming resolved. It does not prove it.
  - A transition of the element's twisting or hourglass error term (H2) could produce the same pattern.
  - H1 and H2 remain unverified hypotheses.

## 7. Is another FE calculation justified?

- **For numerical error control: no.**
  - The 400×400 values carry ≤ 0.017 % estimated discretisation error, with a conditional bracket of the same size.
  - The 100×100 values used in R5 carry ≤ 0.124 %.
  - Both are one to two orders of magnitude below the 1.4 % FIT residual against PolyMAX.
  - An 800×800 mesh would refine an error that is already negligible for the present research questions, so it is not
    recommended.
- **To identify the mechanism (H1 against H2): only if that question matters for a later decision**, for example a
  choice of model form for twisting modes, or an explanation of the Kirchhoff-Ritz/S4R gap.
  - The R6.D1 options V2a (raised G13/G23, 1 job) or V2b (S4 elements, 2 jobs) would then discriminate.
  - This is optional, needs separate authorisation, and is not needed for numerical readiness of the frequency
    comparison.
- **Uncertainty and the mesh gate:** u(ln f_exp) remains NOT_AVAILABLE, and the uncertainty-relative mesh gate remains
  NOT_EVALUABLE. No uncertainty was invented and none was replaced by the mesh error.

## 8. Demonstrated vs not demonstrated

**Demonstrated:**
- The 400×400 job completed and was extracted without altering the ODB.
- All 14 branches keep their identity across four meshes.
- The observed order of the twisting modes rises with refinement.
- Non-twisting modes converge at p ≈ 2 in two independent triplets.
- The rank-1 extrapolation of R6.1 was too large, and the current error estimates are as in §5.

**Not demonstrated:**
- the asymptotic range for twisting modes;
- the physical or numerical mechanism (H1 or H2);
- the element-type error (S4/S8R);
- the converged model-form values;
- any material property, axis assignment or FE↔EXP mode identity;
- the 10 % target.

Outputs and scripts are in `D:\git\abaqus-modal-comparator-work\runs\real_fit_r6_v1\`; the only tracked change is this
report.

REAL-FIT.R6.V1 REVIEW_READY. STOP: V2 and sensitivity calculations are not started.
