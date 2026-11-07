# REAL-FIT.R5 report: Abaqus S4R forward check of the Ritz minima A and B

**Status: REAL-FIT.R5 REVIEW_READY.** This was a research forward check only:
- **Not a result:** no material property, no identification and no physical mode pairing. The 10 % accuracy target is not
  demonstrated.
- **Unchanged statuses:** M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and Production Auto-ID BLOCKED.

## 1. Starting point and sources

- **Branch:** `feature/materials-offline-v1`.
- **Base:** HEAD `dfab1228ad274a531a33bde45dedb0765c1a85c2`, equal to origin; `origin/main` is `0bea1de6…`.
- **Working tree:** clean apart from the 25 untracked items, which were kept.
- **Processes before the run:** only the Abaqus licence server (`ABAQUSLM`). No solver process was running and none was touched.

All sources were verified before the run and were unchanged after it:

| Source | SHA-256 |
|---|---|
| `runs\real_fit_r4_fe_preflight\decks\M11_RITZ_MINIMUM_A.inp` | `a0668c28bb912ed55591a4847c73a5778fdb39d1811136a1a9d2cc0bf69c0927` |
| `…\M11_RITZ_MINIMUM_B.inp` | `69c485fba9280d19b318ce3867e194d34bf3e940997b725eb3afad2f67913a3a` |
| `…\preflight_manifest.json` | `cc4181a77521d178cea5d6af073132b2c503fb8635e4d2a22510d48b6d164bd7` |
| `I:\sandwich\Abaqus Results\temp\CFRP_S4R_0875_FreeFree.inp` / `.dat` | `962f75f2…81df3` / `f4405925…5de9` |
| `I:\sandwich\exp\SPname_files_ROTATED_261103\300by300_plate_only_1mm_ROTATED_Polymax_261027.unv` | `76db80ae…4bed` |
| `runs\real_fit_r2\proposal_free.json` (the minima) | `11c3c962…68ba6` |
| Baseline ODB copy `runs\real_plate_r1\fe\CFRP_S4R_0875_FreeFree.odb` | `7daeb7e3…b8` |
| Baseline package manifest (byte copy of the authorised M11 R6 extraction) | recorded in the protocol |
| `abaqus_scripts/extract_odb.py` (unchanged extractor) | `039aa067…534d` |

## 2. Protocol frozen before the first solve

`D:\git\abaqus-modal-comparator-work\runs\real_fit_r5_fe\protocol\comparison_protocol.json` has SHA-256
**`8fb11132921f93743142260110bf2674552beac5e694b00a93c19d04fe935aa9`**.

It was written with exclusive create, made read-only and checked by every later script. It also records the SHA-256 of the
comparison scripts: `r5_common.py`, `freeze_protocol.py`, `run_jobs.py`, `extract_r5.py` and `compare_r5.py`. The protocol was
not changed after the solves.

### Correspondence and roles

- **Records:** `Polymax_bravo`, 11 curve-fitted records, re-read from the UNV and identical to the R2 declaration.
- **Roles:** records 1–9 are FIT and records 10–11 are diagnostic HOLDOUT. Record 1 (18.6307 Hz) is included.
- **Hypothesis:** EXP rank k ↔ the k-th elastic mode of each model's ascending elastic spectrum. This is an assumed
  correspondence. It is unchanged, and nothing was re-ranked.
- **HOLDOUT caveat:** earlier analyses have inspected these modes, so HOLDOUT is not fully independent validation.

### Frozen definitions

- **Rigid modes:** classified by shape. `quality_control._rigid_body_residual_fraction` ≤ 0.02 is applied to all 20 extracted
  modes. The two 0 Hz modes, which the program's reader cannot load, are classified by the same criterion from their CSV. No
  frequency cut-off and no first-six rule is used.
- **FE frequency:** the ODB eigenfrequency, with the `.dat` value as a cross-check.
- **Metrics:**
  - ln(f_S4R/f_EXP) and percentages;
  - (f_S4R/f_Ritz − 1) × 100 at identical E1, E2 and G12, with the Ritz model run forward only (degree 14, 15 modes, as in
    the tuning);
  - FIT and HOLDOUT RMS separately, plus maximum errors;
  - Ritz-to-S4R U3 MAC per rank. This compares two models' shapes; it is not an experimental MAC.
- **No experimental-to-FE MAC:** there is no justified physical registration.

### FE-to-FE tracking against the baseline M11

- **Policy:** `auto-id/identification-pairing/strict-v1`, tracking MAC ≥ 0.90 with a unique assignment.
- **Shapes:** U1/U2/U3 at all 10 201 common nodes, unweighted.
- **Pass 1:** `branch_tracker.track_branches` with every mode tracked singly.
- **Pass 2:** the 2-mode groups triggered by `identification_clusters.cluster_triggers` (|Δf|/f < 3 % on the baseline and the
  variant's Ritz frequencies, both known before the solve) are tracked as subspaces, with both cos² > 0.95.
- **Pass 3:** per-row diagnostics and subspace diagnostics.
- **Triggers are not confirmed clusters.** Confirmation needs parameter perturbations, which were not run.

### Pre-run method check, from existing data only

At the INP values the Ritz model reproduces the baseline S4R at 14 ranks within −0.12 % / +0.04 %, with U3 MAC 1.000 at every
rank. The Ritz FIT cost of minimum A reproduces the export bit for bit. For minimum B it differs in the last bit, a relative
1e-16 caused by the summation order.

## 3. Abaqus execution (exactly two solves)

Each job was run with:

`cmd.exe /d /s /c C:\SIMULIA\Commands\abaqus.bat job=R5_<L> input=M11_RITZ_MINIMUM_<L>.inp cpus=1 interactive ask_delete=OFF`

The jobs ran sequentially in the work folders `runs\real_fit_r5_fe\A\` and `…\B\`. Each deck copy was verified against its
source hash before the run.

| | R5_A | R5_B |
|---|---|---|
| Version | Abaqus 2024 (licence: Abaqus/Foundation, 3 tokens) | same |
| Start → end (+08:00) | 2026-11-07 23:46:44.46 → 23:47:00.87 | 23:47:42.51 → 23:47:58.75 |
| Elapsed, exit code | 16.41 s, 0 | 16.23 s, 0 |
| Completion | stdout `Abaqus JOB R5_A COMPLETED`; `.sta` THE ANALYSIS HAS COMPLETED SUCCESSFULLY | same for B |
| Errors / warnings (`.msg`) | 0 / 0 | 0 / 0 |
| Modes requested / obtained | 20 / 20 (6 rigid by shape, 14 elastic) | 20 / 20 (6 rigid, 14 elastic) |
| Total mass (`.dat`) | 1.1836072E-04 t, identical to the baseline | same |
| `.dat` / `.sta` / `.msg` | `b57005a8…debf` / `e613feb8…7b562` / `0d9cacf2…adf2` | `08dcf4d2…5928` / `90c57d68…1427` / `80cb246e…7f16` |
| `.odb` | `7e13db9ceea99ff97cb13c9f3d1e0cc5ba13318bc72f907ed992a46252b95282` | `2044261249382e8f180d588187e9d6df459bebf90cef9f1884c90974bc9c2901` |

The `.com`, `.prt`, `.sim` and launch logs are hashed in `runs\real_fit_r5_fe\jobs_record.json` (`824d23f2…b6d`). No `.log`
file is written in interactive mode; its content is on stdout, kept in `R5_<L>.launch.log`.

**Deviation, stated in full.** The frozen runner `run_jobs.py` judged completion partly by `R5_A.log`, which Abaqus does not
write in interactive mode. It therefore recorded A as FAILED and, following its own A-failure rule, did not start B. A had in
fact completed on every other criterion: exit 0, the COMPLETED line on stdout, a successful `.sta`, no error and the ODB written.

`run_job_b_after_completion_fix.py` then did the following:
1. kept the runner's record byte-for-byte as `jobs_record_runner_initial.json` (`010b7076…7e2d`);
2. re-assessed A with the corrected criterion;
3. ran the authorised R5_B **once**, through the unchanged `run_jobs.run`.

A was not re-run, no third job was started, and the protocol and the comparison rules were not changed. Owner review of this
deviation is requested.

**Extraction:** modes 1–20 of both ODBs were extracted with the program's pinned workflow
(`analyze_model.make_plan/extract` → `odb_import_service` → `extract_odb.py`, Abaqus Python, `readOnly=True`). Each ODB hash was
equal before extraction, after it and at job end.
- Package manifests: A `63f7374d…c8f4`, B `9e40f5f7…2cec`.
- Extraction record: `4580647…df80`.
- `.dat` and ODB frequencies agree within 3.2e-5 relative, which is the `.dat` rounding.

## 4. Frequency comparison

The ranks are each model's ascending elastic order. The FE mode is the Abaqus mode number, 7–20 in every model.

| Rank | EXP rec, Hz, role | Baseline S4R | Ritz A | S4R A | Ritz→S4R A | S4R−EXP A | Ritz B | S4R B | Ritz→S4R B | S4R−EXP B |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1, 18.6307, FIT | 19.0722 | 18.7347 | 18.7131 | −0.115 % | +0.442 % | 18.7234 | 18.7018 | −0.115 % | +0.382 % |
| 2 | 2, 54.6193, FIT | 59.8742 | 53.8523 | 53.8555 | +0.006 % | −1.398 % | 53.8012 | 53.8043 | +0.006 % | −1.492 % |
| 3 | 3, 63.4950, FIT | 62.0092 | 62.7544 | 62.7565 | +0.003 % | −1.163 % | 62.7773 | 62.7794 | +0.003 % | −1.127 % |
| 4 | 4, 66.8467, FIT | 71.8499 | 65.8331 | 65.7995 | −0.051 % | −1.566 % | 65.8570 | 65.8232 | −0.051 % | −1.531 % |
| 5 | 5, 74.2149, FIT | 72.1900 | 73.0942 | 73.0628 | −0.043 % | −1.552 % | 73.0670 | 73.0352 | −0.044 % | −1.590 % |
| 6 | 6, 112.2655, FIT | 116.5804 | 112.9632 | 112.8529 | −0.098 % | +0.523 % | 113.1149 | 113.0036 | −0.098 % | +0.657 % |
| 7 | 7, 145.9357, FIT | 167.4903 | 148.7050 | 148.7423 | +0.025 % | +1.923 % | 148.7746 | 148.8116 | +0.025 % | +1.971 % |
| 8 | 8, 157.8508, FIT | 168.6080 | 158.6059 | 158.5966 | −0.006 % | +0.472 % | 158.6039 | 158.5934 | −0.007 % | +0.470 % |
| 9 | 9, 169.1849, FIT | 174.7977 | 172.7810 | 172.8067 | +0.015 % | +2.141 % | 172.6777 | 172.7038 | +0.015 % | +2.080 % |
| 10 | 10, 180.1363, HOLDOUT | 179.9016 | 181.6758 | 181.6586 | −0.009 % | +0.845 % | 181.7461 | 181.7285 | −0.010 % | +0.884 % |
| 11 | 11, 191.6019, HOLDOUT | 213.1995 | 197.9873 | 197.8362 | −0.076 % | +3.254 % | 198.3704 | 198.2170 | −0.077 % | +3.453 % |
| 12 | none | 213.9528 | 214.0598 | 213.9094 | −0.070 % | — | 214.3109 | 214.1584 | −0.071 % | — |
| 13 | none | 295.7755 | 285.7936 | 285.4783 | −0.110 % | — | 286.5375 | 286.2180 | −0.112 % | — |
| 14 | none | 327.9010 | 291.4941 | 291.6561 | +0.056 % | — | 291.6070 | 291.7675 | +0.055 % | — |

Ritz-to-S4R U3 MAC at the same rank is 1.000 at all 14 ranks for both A and B, and the best-matching Ritz rank is the same
rank every time.

| Summary | A, S4R | A, Ritz | B, S4R | B, Ritz |
|---|---|---|---|---|
| FIT RMS ln(f/f_EXP), records 1–9 | 0.01378 | 0.01371 | 0.01388 | 0.01381 |
| FIT maximum \|error\| | 2.14 % (rec 9) | 2.13 % | 2.08 % (rec 9) | 2.06 % |
| HOLDOUT RMS ln, records 10–11 | 0.02341 | 0.02395 | 0.02479 | 0.02534 |
| HOLDOUT maximum \|error\| | 3.25 % (rec 11) | 3.33 % | 3.45 % (rec 11) | 3.53 % |
| Ritz→S4R RMS / maximum, ranks 1–11 | 0.056 % / 0.115 % | | 0.056 % / 0.115 % | |

**Numerical verification:** at both minima the Abaqus S4R model reproduces the Kirchhoff–Ritz surrogate within 0.12 %, and with
the same shape at every rank. The surrogate error is therefore about 25 times smaller than the remaining 1.4 % misfit to the
PolyMAX frequencies. That misfit belongs to the model, its assumptions and the rank hypothesis, not to the surrogate.

**A and B separately:** they differ by at most 0.2 % per mode. The frequencies do not distinguish them, and neither is selected.

## 5. FE-to-FE tracking against the baseline M11

The service verdicts are the same in kind for A and B.
- **Pass 1:** `BRANCH_LOSS` at baseline ranks 02, 03, 09, 10 and 14.
- **Pass 2:** `BRANCH_LOSS`. The service refuses at the untriggered singles 02 and 03 before it evaluates the subspaces.

Pass 3 diagnostics:

| Baseline row (mode, Hz) | A | B |
|---|---|---|
| 01 (7, 19.07) | → mode 7, MAC 1.000 | → mode 7, 1.000 |
| 02, 03 (8, 9; 59.87 / 62.01) | each splits between modes 8 and 9 (MAC 0.501 / 0.499): **LOST** individually; not triggered (3.5 % spacing), so no subspace test | split 0.717 / 0.283: **LOST** |
| 04, 05 (10, 11) | → modes 11, 10 (MAC 1.000; **order exchanged**); subspace unique, cos² 0.99998 / 0.99995 | → modes 10, 11 (1.000); subspace unique |
| 06 (12) | → mode 12, 1.000 | → mode 12, 1.000 |
| 07, 08 (13, 14; 167.5 / 168.6) | → modes 15, 13 (1.000; order exchanged); subspace {13, 15} unique | → modes 13, 15 (1.000); subspace {13, 15} unique |
| 09, 10 (15, 16; 174.8 / 179.9) | split (0.513 / 0.511): **LOST** individually; subspace {14, 16} unique, cos² 0.99999 / 0.99993 | split (0.714 / 0.712); subspace {14, 16} unique |
| 11, 12 (17, 18) | → modes 18, 17 (1.000; order exchanged); subspace unique | → modes 17, 18 (1.000); subspace unique |
| 13 (19) | → mode 19, 1.000 | → mode 19, 1.000 |
| 14 (20, 327.9) | best MAC 0.169: **LOST**. Subspace (13, 14) lost: a new branch enters at A's mode 20 (291.7 Hz) | best MAC 0.864: **LOST**; subspace (13, 14) lost |

- **Close modes in each S4R spectrum (< 3 %):** only ranks 13/14 (285.5 / 291.7 Hz in A, 286.2 / 291.8 Hz in B).
- **Why branches split:** the nearly square isotropic-like baseline (E1 = E2, 301 × 300 mm) has mode pairs whose individual shapes
  are combinations. The orthotropic variants rotate them inside their pair subspace, and tracking is honest about that.
- **Order changes against the baseline:** these are expected, because each model's rank order is used. The Ritz-to-S4R MAC of
  1.000 at every rank shows that the Ritz rank used in the fit and the S4R rank denote the same shape in each variant.

## 6. Material-axis status

**NOT_SOLVER_VERIFIED.** The decks request only U, so the solver outputs give no direct evidence of the material 1/2 axes. The
INP-based interpretation of R4 is retained: material 1 = FE X and material 2 = FE Y.

**Indirect consistency diagnostic** (declared before the run, and not verification):

| | Ritz, same assignment | Ritz, E1 ↔ E2 exchanged |
|---|---|---|
| RMS ln(f_S4R/f_Ritz), A | 0.00062 | 0.00581 |
| Mean U3 MAC at the same rank, A | 1.000 | 0.227 |
| RMS ln(f_S4R/f_Ritz), B | 0.00063 | 0.00536 |
| Mean U3 MAC at the same rank, B | 1.000 | 0.229 |

Both A and B behave as Ritz does with E1 along FE X. This is consistent with the convention, but it compares two models; it is
not physical evidence.

## 7. Numerical verification versus material identification

**Shown:**
- the two R4 decks solve in Abaqus S4R without errors or warnings;
- at both minima the S4R reproduces the Ritz frequencies within 0.12 % and the Ritz shapes at every rank;
- S4R gives the same FIT misfit (1.38–1.39 % RMS) and HOLDOUT misfit (2.3–2.5 %) against PolyMAX as the surrogate.

**Not shown:**
- that EXP record k is physically FE rank k;
- which plate axis is stiff (A or B);
- that the moduli are accurate. They scale with the assumed thickness 0.875 mm, the density 1.498e-9 t/mm³ and ν12 = 0.05, and
  E3, ν13, ν23, G13 and G23 are taken as given;
- any experimental-to-FE shape agreement;
- the 10 % parameter-accuracy target.

**Fixed model assumptions:** free-free support, the M11 mesh and the S4R section.

## 8. Limitations and further FE verification

- **One mesh, one element type.** Mesh convergence was not studied, and it was not authorised.
- **Tracking:**
  - the baseline pairs 02/03 and 09/10 are lost individually;
  - the 02/03 pair was not triggered, so no subspace diagnostic exists for it under the frozen protocol;
  - baseline mode 20 leaves the 20-mode window.
- **The FE-to-EXP correspondence** remains the declared rank hypothesis.
- **The material axes** are not solver-verified.
- **The runner's completion criterion** was faulty, as described in §3.
- **Not in Git:** raw results, ODB/DAT files, logs, the protocol, extracted shapes, tables and scripts are under
  `D:\git\abaqus-modal-comparator-work\runs\real_fit_r5_fe\` (`results_r5.json` `10e61767…1dbcc`, console outputs).

Abaqus ran exactly two frequency jobs plus two read-only extractions. Nothing else was solved, fitted or optimised.
