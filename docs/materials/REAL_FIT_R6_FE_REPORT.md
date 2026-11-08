# REAL-FIT.R6.1: authorised Abaqus S4R mesh convergence study

Status: **REAL-FIT.R6.1 REVIEW_READY**. This report verifies the numerical forward model only. It is not material
identification and not production Auto-ID. M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID
BLOCKED are unchanged. A and B were not selected.

## 1. Verified inputs

**Git:**
- branch `feature/materials-offline-v1`; HEAD `2853ef52857a44a7a88a8b1f83a9ed196ae5dbad`, equal to origin;
- `origin/main` `0bea1de68dc346d20958e6f53a9e1d634a870f5d`;
- tracked tree clean; the 25 untracked items are preserved.

**Before the first job:**
- no Abaqus solver process was active;
- the four R6.0 deck hashes matched the authorisation, and the R6.0 protocol matched
  `c04b63eb3802ece0826156e858a543cd4477f7e7ceac23e5b4c2a19eac0c2129`;
- an unchanged read-only copy of the protocol was frozen at 2026-11-08T18:38:26+08:00 in
  `runs\real_fit_r6_fe\protocol\`, with the same SHA-256;
- the launcher `C:\SIMULIA\Commands\abaqus.bat` (SHA `35dddb92…`) calls `abq2024.bat`.

**Mid level reused from R5:** the R5_A and R5_B solves, not repeated.
- Their inputs are byte-identical to the 100×100 member of the R6 family (`a0668c28…`, `69c485fb…`), as established
  in R6.0.
- Solver: Abaqus 2024, same command form, `cpus=1`.
- ODBs: `7e13db9c…`, `20442612…`.
- Packages: extracted with the same pinned extractor (`extract_odb.py` `039aa067…`).
- The reloaded 100×100 frequencies equal `results_r5.json` exactly.

**After the run:** all R4, R5 and R6.0 inputs are unchanged. This covers the original M11 INP and DAT, the UNV, the R4
decks, the R5 records, ODBs and packages, and the R6.0 decks, protocol and frozen code; 21 + 10 files were re-hashed.
No solver process remained.

## 2. Abaqus solver results (exactly four jobs)

Each job ran in its own new folder under `D:\git\abaqus-modal-comparator-work\runs\real_fit_r6_fe\` with the command
`abaqus.bat job=<J> input=<deck> cpus=1 interactive ask_delete=OFF`. The runs were sequential; there was no datacheck
and no retry.

| Job | Start–end (+08:00) | Wall time | Exit code | Status | Modes requested / obtained | Rigid / elastic | Mass (`.dat`, t) | Warnings / errors |
|---|---|---|---|---|---|---|---|---|
| R6_A_M050 | 18:38:32–18:38:43 | 11.4 s | 0 | COMPLETED | 20 / 20 | 6 / 14 | 1.1836073E-04 | 0 / 0 |
| R6_A_M200 | 18:38:43–18:39:04 | 20.1 s | 0 | COMPLETED | 20 / 20 | 6 / 14 | 1.1836072E-04 | 0 / 0 |
| R6_B_M050 | 18:39:04–18:39:22 | 17.9 s | 0 | COMPLETED | 20 / 20 | 6 / 14 | 1.1836073E-04 | 0 / 0 |
| R6_B_M200 | 18:39:22–18:39:42 | 20.0 s | 0 | COMPLETED | 20 / 20 | 6 / 14 | 1.1836072E-04 | 0 / 0 |

**Completion evidence:** every job passed all checks:
- exit code 0;
- stdout "Abaqus JOB <J> COMPLETED" and the version line "Abaqus 2024";
- `.sta` "THE ANALYSIS HAS COMPLETED SUCCESSFULLY";
- no `***ERROR`;
- ODB present.

No `.log` file was required. Stdout is kept in `<J>.launch.log`.

**Resources:**
- 200×200: the `.dat` memory estimate is 130 MB minimum and 2282 MB to minimise I/O;
- disk: 104 MB per 200 folder and 8.4 MB per 50 folder, including the packages.

**Rigid modes:** in every package modes 1–6 are rigid by shape (residual ≤ 5e-8) and modes 7–20 are elastic.

**DAT↔ODB frequency agreement:** within 2.9e-5 relative.

| Job | INP | ODB | DAT | STA | MSG | Package manifest |
|---|---|---|---|---|---|---|
| R6_A_M050 | `f081ab5b…c2096fa0` | `204fd32e7d40778597fe3a7cf974a536702b7f5cce56f4c8f13570fa75a2985b` | `5d1d3ab2…30d72208` | `d9664704…95b4ac2c` | `e89376c1…a0018d82` | `692f46ed…1ab15c29` |
| R6_A_M200 | `da07e092…ba58bc5c` | `ffb5b74c73c6488d7d34a96ffdca6106957fdfd955558569d03f26ff45fe3765` | `8a399350…058a5309` | `8fb42094…8110d40a` | `699eab00…3e567a9a` | `2aafc801…8441692d` |
| R6_B_M050 | `6ead3fc3…867038d8` | `dbd63dd0394fa2c7d0aed063b231d8e5cf9bd773900de13432c5e4d047c057fb` | `3c74c8df…5b93f0af` | `187eb45a…9312ab3a` | `f720d9dc…62ab64e9` | `9741cea2…19b28138` |
| R6_B_M200 | `439858f0…0ed42286` | `76fe3fcb1b85da0f8c0d06b83dde7767e14e30934bd0ed403ae8f68b2b2e16c6` | `2cdc50a3…adbcedf9` | `2b00d6c7…8c77df16` | `cf4d7d0a…28d8148b` | `638d595d…cb821dd8` |

Full hashes are in `jobs_record.json` (`9bce1348…`), `extraction_record.json` (`fd34dfb6…`), `results_r6.json`
(`eb72f34e…`) and the output manifest `hash_manifest.json` (`7d6ab76b…`, 150 files).

**Extraction:** the pinned workflow, `analyze_model` → `odb_import_service` → `extract_odb.py`, with `readOnly=True`.
- The extractor SHA was checked to be equal to R5's.
- All four packages were newly extracted.
- Each ODB SHA-256 was identical before extraction, after it, and as recorded at job end.

## 3. Mesh convergence results

**Method:**
- Code: the R6.0 frozen code, unchanged (`r6_convergence.py`, `r5_common.py`, `r6_mesh.py`; hashes checked against
  the protocol), driven by `analyze_r6.py`.
- Notation: f in Hz; δh = ln(fh/f_ext); GCI uses Fs = 1.25.
- Order: p is observed, never forced.
- MAC: the smallest of the 50↔100, 100↔200 and 50↔200 values on the common 2 601-node lattice.

All 28 branches are MONOTONE (0 < R < 1).

<!-- tables generated from results_r6.json by report_tables.md in the work folder -->

**Variant A**

| Rank | Modes 50/100/200 | f50 | f100 | f200 | (f50−f100)/f100 | (f100−f200)/f200 | p | f_ext | δ100 | δ200 | GCI100 | GCI200 | min MAC U1–U3 / U3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 7/7/7 | 18.7227 | 18.7131 | 18.7053 | +0.051 % | +0.042 % | 0.30 | 18.6716 | +0.222 % | +0.180 % | 0.277 % | 0.225 % | 1.0000000 / 1.0000000 |
| 2 | 8/8/8 | 53.8802 | 53.8555 | 53.8493 | +0.046 % | +0.011 % | 2.00 | 53.8473 | +0.015 % | +0.004 % | 0.019 % | 0.005 % | 0.9999997 / 0.9999997 |
| 3 | 9/9/9 | 62.7856 | 62.7565 | 62.7492 | +0.046 % | +0.012 % | 2.00 | 62.7468 | +0.015 % | +0.004 % | 0.019 % | 0.005 % | 0.9999996 / 0.9999996 |
| 4 | 10/10/10 | 65.8350 | 65.7995 | 65.7823 | +0.054 % | +0.026 % | 1.04 | 65.7659 | +0.051 % | +0.025 % | 0.064 % | 0.031 % | 0.9999997 / 0.9999997 |
| 5 | 11/11/11 | 73.0990 | 73.0628 | 73.0464 | +0.050 % | +0.023 % | 1.14 | 73.0327 | +0.041 % | +0.019 % | 0.052 % | 0.023 % | 0.9999997 / 0.9999997 |
| 6 | 12/12/12 | 112.9205 | 112.8529 | 112.8118 | +0.060 % | +0.036 % | 0.72 | 112.7484 | +0.093 % | +0.056 % | 0.116 % | 0.070 % | 0.9999996 / 0.9999996 |
| 7 | 13/13/13 | 148.9992 | 148.7423 | 148.6781 | +0.173 % | +0.043 % | 2.00 | 148.6567 | +0.058 % | +0.014 % | 0.072 % | 0.018 % | 0.9999984 / 0.9999984 |
| 8 | 14/14/14 | 158.8494 | 158.5966 | 158.5244 | +0.159 % | +0.046 % | 1.81 | 158.4956 | +0.064 % | +0.018 % | 0.080 % | 0.023 % | 0.9999985 / 0.9999985 |
| 9 | 15/15/15 | 173.1051 | 172.8067 | 172.7321 | +0.173 % | +0.043 % | 2.00 | 172.7073 | +0.058 % | +0.014 % | 0.072 % | 0.018 % | 0.9999984 / 0.9999984 |
| 10 | 16/16/16 | 181.9509 | 181.6586 | 181.5777 | +0.161 % | +0.045 % | 1.85 | 181.5467 | +0.062 % | +0.017 % | 0.077 % | 0.021 % | 0.9999980 / 0.9999980 |
| 11 | 17/17/17 | 198.0894 | 197.8362 | 197.7382 | +0.128 % | +0.050 % | 1.37 | 197.6763 | +0.081 % | +0.031 % | 0.101 % | 0.039 % | 0.9999986 / 0.9999986 |
| 12 | 18/18/18 | 214.1885 | 213.9094 | 213.8082 | +0.130 % | +0.047 % | 1.46 | 213.7507 | +0.074 % | +0.027 % | 0.093 % | 0.034 % | 0.9999986 / 0.9999986 |
| 13 | 19/19/19 | 285.8515 | 285.4783 | 285.3251 | +0.131 % | +0.054 % | 1.28 | 285.2184 | +0.091 % | +0.037 % | 0.114 % | 0.047 % | 0.9999982 / 0.9999982 |
| 14 | 20/20/20 | 292.7383 | 291.6561 | 291.3860 | +0.371 % | +0.093 % | 2.00 | 291.2962 | +0.123 % | +0.031 % | 0.154 % | 0.039 % | 0.9999945 / 0.9999945 |

**Variant B**

| Rank | Modes 50/100/200 | f50 | f100 | f200 | (f50−f100)/f100 | (f100−f200)/f200 | p | f_ext | δ100 | δ200 | GCI100 | GCI200 | min MAC U1–U3 / U3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 7/7/7 | 18.7114 | 18.7018 | 18.6940 | +0.051 % | +0.042 % | 0.30 | 18.6601 | +0.223 % | +0.181 % | 0.279 % | 0.226 % | 1.0000000 / 1.0000000 |
| 2 | 8/8/8 | 53.8289 | 53.8043 | 53.7982 | +0.046 % | +0.011 % | 2.00 | 53.7961 | +0.015 % | +0.004 % | 0.019 % | 0.005 % | 0.9999997 / 0.9999997 |
| 3 | 9/9/9 | 62.8087 | 62.7794 | 62.7721 | +0.047 % | +0.012 % | 2.00 | 62.7696 | +0.016 % | +0.004 % | 0.020 % | 0.005 % | 0.9999996 / 0.9999996 |
| 4 | 10/10/10 | 65.8587 | 65.8232 | 65.8059 | +0.054 % | +0.026 % | 1.03 | 65.7893 | +0.051 % | +0.025 % | 0.064 % | 0.031 % | 0.9999997 / 0.9999997 |
| 5 | 11/11/11 | 73.0715 | 73.0352 | 73.0186 | +0.050 % | +0.023 % | 1.13 | 73.0047 | +0.042 % | +0.019 % | 0.052 % | 0.024 % | 0.9999997 / 0.9999997 |
| 6 | 12/12/12 | 113.0709 | 113.0036 | 112.9624 | +0.060 % | +0.036 % | 0.71 | 112.8974 | +0.094 % | +0.058 % | 0.117 % | 0.072 % | 0.9999996 / 0.9999996 |
| 7 | 13/13/13 | 149.0686 | 148.8116 | 148.7472 | +0.173 % | +0.043 % | 2.00 | 148.7258 | +0.058 % | +0.014 % | 0.072 % | 0.018 % | 0.9999984 / 0.9999984 |
| 8 | 14/14/14 | 158.8454 | 158.5934 | 158.5213 | +0.159 % | +0.045 % | 1.81 | 158.4924 | +0.064 % | +0.018 % | 0.080 % | 0.023 % | 0.9999985 / 0.9999985 |
| 9 | 15/15/15 | 173.0020 | 172.7038 | 172.6292 | +0.173 % | +0.043 % | 2.00 | 172.6043 | +0.058 % | +0.014 % | 0.072 % | 0.018 % | 0.9999984 / 0.9999984 |
| 10 | 16/16/16 | 182.0217 | 181.7285 | 181.6470 | +0.161 % | +0.045 % | 1.85 | 181.6157 | +0.062 % | +0.017 % | 0.078 % | 0.022 % | 0.9999978 / 0.9999978 |
| 11 | 17/17/17 | 198.4692 | 198.2170 | 198.1189 | +0.127 % | +0.050 % | 1.36 | 198.0564 | +0.081 % | +0.032 % | 0.101 % | 0.039 % | 0.9999986 / 0.9999986 |
| 12 | 18/18/18 | 214.4365 | 214.1584 | 214.0570 | +0.130 % | +0.047 % | 1.46 | 213.9989 | +0.075 % | +0.027 % | 0.093 % | 0.034 % | 0.9999987 / 0.9999987 |
| 13 | 19/19/19 | 286.5889 | 286.2180 | 286.0648 | +0.130 % | +0.054 % | 1.28 | 285.9569 | +0.091 % | +0.038 % | 0.114 % | 0.047 % | 0.9999982 / 0.9999982 |
| 14 | 20/20/20 | 292.8500 | 291.7675 | 291.4973 | +0.371 % | +0.093 % | 2.00 | 291.4073 | +0.124 % | +0.031 % | 0.154 % | 0.039 % | 0.9999945 / 0.9999945 |

**Frozen subspace {rank 13, rank 14}:** SUBSPACE_TRACKED and unique in all three directions, with cos² ≥ 0.999994.
- members, sorted within the group: p = 1.28 and 2.00, the same as the single branches;
- group mean: MONOTONE, p = 1.78.

**Reading the results:**
- **Mesh 100×100 (R5), discretisation error:** |δ100| ≤ 0.12 % on ranks 2–14, but **0.22 % on rank 1**. All 100×100
  frequencies lie above f_ext, as expected for a converging displacement model.
- **Mesh 200×200:** |δ200| ≤ 0.06 % on ranks 2–14 and 0.18 % on rank 1.
- **Observed order.** p ≈ 2.0 (1.8–2.0) on ranks 2, 3, 7–10 and 14. It is lower on ranks 4, 5 and 11–13 (1.0–1.5),
  rank 6 (0.71) and **rank 1 (0.30)**.
  - Where p < 1, the extrapolation amplifies the last difference (1/(2^p − 1) = 4.3 for rank 1). Such an f_ext and its
    δ are formally valid, but they are weak estimates, not proof of asymptotic convergence.
  - The low order of rank 1, the 18.7 Hz first elastic mode, has not been explained and is not repaired here. A
    shear- or hourglass-related or a pre-asymptotic error term is possible but **unverified**.
- **Asymptotic-range diagnostic:** the frozen ratio GCI_mid/(2^p·GCI_fine) equals 0.999–1.000 for every branch. With
  three grids and p computed from the same two differences, this ratio is ≈ 1 **by construction**, so it does **not**
  test the asymptotic range. This is a weakness of the frozen definition. It is reported, not changed, and no
  asymptotic-range claim is made.
- **Shapes:** the shapes are already converged on the lattice. 1 − MAC is at most 5.5e-6 for 50↔200 and at most
  2.2e-7 for 100↔200; the U3-only values are the same. Second-best MAC values are ≤ 0.006, so every correspondence is
  well separated.

## 4. Modal branches: successful and failed

- **Per variant:** each of A and B has 14 of 14 elastic branches TRACKED_SINGLE in all three directions: M100 → M050,
  M100 → M200 and the M050 → M200 consistency check.
- **Correspondence:** the same mode numbers on every level, no order changes, MAC ≥ 0.999994.
- **Branch tracker:** both pass 1 (singles) and pass 2 (frozen pairs as subspaces) returned TRACKED in every direction.
- **No failures:** there is no BRANCH_LOSS, CLUSTER_LOSS or NOT_EVALUABLE branch, and no branch was replaced by a
  nearest-frequency mode.
- **Additional 3 % triggers** (reported only): {13, 14} in both directions, identical to the frozen group.

## 5. Experimental-frequency diagnostic (unverified rank hypothesis)

**The hypothesis is unchanged from R5:**
- source: PolyMAX `Polymax_bravo`;
- the k-th EXP record corresponds to the k-th elastic branch of the 100×100 mesh, followed to the other meshes by
  shape;
- records 1–9 are FIT, 10–11 are diagnostic HOLDOUT, and record 1 is included.

This is a research hypothesis, not physical mode identity, and there is no experimental-to-FE MAC.

| | A: 50 | A: 100 (R5) | A: 200 | A: f_ext | B: 50 | B: 100 (R5) | B: 200 | B: f_ext |
|---|---|---|---|---|---|---|---|---|
| FIT RMS ln(f/f_EXP), 9 records | 0.01425 | 0.01378 | 0.01369 | 0.01363 | 0.01434 | 0.01388 | 0.01378 | 0.01373 |
| FIT max | 2.32 % | 2.14 % | 2.10 % | 2.08 % | 2.26 % | 2.08 % | 2.04 % | 2.02 % |
| HOLDOUT RMS ln, 2 records | 0.02459 | 0.02341 | 0.02299 | 0.02275 | 0.02597 | 0.02479 | 0.02438 | 0.02413 |
| HOLDOUT max | 3.39 % | 3.25 % | 3.20 % | 3.17 % | 3.58 % | 3.45 % | 3.40 % | 3.37 % |

**Signed S4R−EXP residuals, variant A** (100 → 200 → f_ext; B differs by ≤ 0.2 percentage points):

| Record | Role | Residual |
|---|---|---|
| 1 | FIT | +0.44 → +0.40 → +0.22 % |
| 2 | FIT | −1.40 → −1.41 → −1.41 % |
| 3 | FIT | −1.16 → −1.18 → −1.18 % |
| 4 | FIT | −1.57 → −1.59 → −1.62 % |
| 5 | FIT | −1.55 → −1.58 → −1.59 % |
| 6 | FIT | +0.52 → +0.49 → +0.43 % |
| 7 | FIT | +1.92 → +1.88 → +1.87 % |
| 8 | FIT | +0.47 → +0.43 → +0.41 % |
| 9 | FIT | +2.14 → +2.10 → +2.08 % |
| 10 | HOLDOUT | +0.85 → +0.80 → +0.78 % |
| 11 | HOLDOUT | +3.25 → +3.20 → +3.17 % |

**What changes with refinement:**
- the FIT RMS falls by about 1 % of its value (0.01378 → 0.01363 for A);
- the residual pattern (sign and size per record) does not change;
- mesh refinement does not remove the 1–3 % residuals, which are therefore not a discretisation effect of the
  100×100 mesh;
- this is diagnostic only: no parameter was refitted, and A and B were not compared to select one.

## 6. Numerical uncertainty versus missing experimental uncertainty

- **Discretisation error estimate:** δ100 is 0.015–0.22 % (GCI100 0.019–0.28 %); δ200 is 0.004–0.18 % (GCI200
  0.005–0.23 %).
  - This is a numerical estimate for these two parameter points. It is not a measurement standard deviation.
  - It was not added to any covariance and did not weaken any residual.
- **u(ln f_exp): NOT_AVAILABLE.** The PolyMAX UFF 55 records carry frequency and damping only, from a single estimate.
- **Mesh-acceptance gate: NOT_EVALUABLE.** The plan's uncertainty-relative gate needs u(ln f_exp). It was not replaced
  by damping, fitted residuals, an assumed percentage or the mesh error.
- **No readiness claim:** full numerical readiness is not declared on the basis of stable frequencies.
- **Other uncertainties not addressed:** model-form uncertainty is outside this study (Kirchhoff vs shear-flexible
  shell, S4R element formulation, ν12, transverse constants, thickness, density, free-free idealisation).

## 7. What has and has not been established about the Ritz forward model

Ritz vs S4R, ranks 1–11, using the R5 Ritz frequencies (`ritz_vs_s4r_mesh.json`; A shown, B equal within 0.001 %):

| S4R level | RMS (Ritz/S4R − 1) | Max |
|---|---|---|
| 50 | 0.110 % | 0.197 % |
| 100 (R5) | 0.056 % | 0.116 % |
| 200 | 0.083 % | 0.157 % |
| f_ext | 0.137 % | 0.338 % (rank 1) |

**Established:**
- At the extrapolated S4R values the Ritz frequencies lie 0.01–0.34 % **above** S4R on every rank. That is the
  expected direction for a Kirchhoff (shear-rigid) model against a shear-flexible shell.
- The close R5 agreement on 100×100 (0.056 %) was **partly coincidental**: the remaining 100×100 discretisation
  stiffness offset part of the model difference.
- The Ritz–S4R model difference is about 4–10 times smaller than the 1.4 % FIT residual against PolyMAX.
- The S4R 100×100 values used in R5 carry ≤ 0.12 % discretisation error on ranks 2–14 and 0.22 % on rank 1.
- Mode shapes are mesh-converged on the common lattice.

**Not established:**
- that Ritz or S4R is the correct physical model;
- the source of the low observed order on rank 1 (and rank 6);
- a real asymptotic-range test, because the frozen ratio is tautological;
- element-type convergence (S4 or S8R);
- sensitivity convergence (separate stage, not run);
- any material value, axis assignment or FE↔EXP mode identity;
- the 10 % target.

## 8. Limitations and confirmation

- **Scope:** one element family (S4R), one structured mesh family, two research parameter points, 20 modes.
- **Frozen protocol:** applied unchanged. The only processing note is the tautological asymptotic ratio (§3); no code
  defect occurred.
- **Jobs run:** exactly four Abaqus jobs: R6_A_M050, R6_A_M200, R6_B_M050 and R6_B_M200. Plus four read-only ODB
  extractions. No datacheck, no retry, no other FE job, no optimisation.
- **Git:** the tracked change is this report only. No PR, no merge, no force push.

REAL-FIT.R6.1 REVIEW_READY. STOP: awaiting owner review before any sensitivity calculation is prepared or executed.
