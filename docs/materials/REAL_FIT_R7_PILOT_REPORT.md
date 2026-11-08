# REAL-FIT.R7.1: FE sensitivity pilot (G12, variant A, mesh 100×100)

Status: **REAL-FIT.R7.1 REVIEW_READY**.
- **Scope:** four authorised Abaqus jobs and four read-only extractions. This is a research verification of the
  sensitivity pipeline, not identification, calibration or an inverse fit.
- **Status flags unchanged:** M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED.
- **u(ln f_exp):** NOT_AVAILABLE.

## 1. Baseline and sources

**Git:**
- branch `feature/materials-offline-v1`; HEAD `c24257a1e9d7d9dc9024b480aac269945cec3d55`, equal to origin;
- `origin/main` `0bea1de68dc346d20958e6f53a9e1d634a870f5d`;
- tracked tree clean; 25 untracked items preserved.

**Solver:** no Abaqus process was running before the jobs. Free resources were 15.6 GB RAM and 177 GB on D:.

**Sources:**
- **R7.0 protocol** `proposed_protocol_r7.json` `a41bb5c79c3b27ded294716acded5d7fc74a5e34df6a36349d25d13043628d3f`.
  A read-only copy is frozen in `real_fit_r7_pilot\protocol\`.
- **Frozen analysis code:** `r7_sensitivity.py` `e3a20505…` and `r5_common.py` `9f26da4f…`, both checked against the
  protocol.
- **Base state R5_A:**
  - deck `a0668c28…0c927`, identical to the R4 deck;
  - ODB `7e13db9c…5282`, unchanged by its R5 extraction;
  - package manifest `63f7374d…`;
  - extractor `039aa067…`.

**Pilot protocol:** frozen before the first solve as `protocol/pilot_protocol.json`
`acddfde30c5a90e6bd0a132ab70c3358e9ac55cfb4387900c29c324b5e5c579a`. The pre-run manifest `prerun_manifest.json` lists
every hash.

## 2. Input perturbations (independent pre-run check)

`prerun_r7p.py` compared each deck byte for byte with the R5_A base deck (`prerun_verification.json` `cbce5537…`).
Every deck passed:
- the line count is the same;
- only the `*Elastic` data line changed, and in it only item 7 (G12);
- the E1 and E2 text is unchanged;
- all mesh and step bytes are identical (10 201 nodes, 10 000 S4R elements, `*Frequency` 20 modes);
- G12 equals `repr(G0·factor)`, with G0 = 4824.07010224442 MPa.

| Job | Factor | G12 written (MPa) | ln(G12/G0) | INP SHA-256 |
|---|---|---|---|---|
| R7_A_M100_G12_P1 | 1.05 | 5065.273607356641 | +0.04879016416943204 | `760a234073209137eed6f9a81f655dff79f0fdbca534a0b4d6bde9868dcdac04` |
| R7_A_M100_G12_M1 | 1/1.05 | 4594.352478328019 | −0.048790164169432056 | `04f03f9e51d815ccd29febfc9c6b3aece5372dd8a0b84831f0b89e6d5167cce8` |
| R7_A_M100_G12_P2 | √1.05 | 4943.2008829236265 | +0.02439508208471609 | `f871e9b09594b4f0572209fe5c04f2ce9b39f1ff92d35bbb8447367cb745342f` |
| R7_A_M100_G12_M2 | 1/√1.05 | 4707.810364689167 | −0.02439508208471609 | `0f5a4586a9a44894fa44e5457dbfdf94a5d6d648dff087cb1b0501039441301e` |

The steps equal ±ln 1.05 and ±ln(1.05)/2 within 1e-14. The denominators use these written values.

## 3. Solver execution (exactly four jobs)

**Command:**
`cmd.exe /d /s /c C:\SIMULIA\Commands\abaqus.bat job=<J> input=<J>.inp cpus=1 interactive ask_delete=OFF`.
- **Runner:** the unchanged R6.1 `run_r6_jobs.run` (SHA checked), cap 1800 s.
- **Order:** sequential, in the authorised order. Each job had a new folder `real_fit_r7_pilot\<J>\`.
- **No** datacheck, **no** retry, and no solver configuration change.

| Job | Start–end (+08:00) | Wall time | Exit code | Status | Modes: obtained / rigid / elastic | Mass (t) | Warnings / errors | ODB SHA-256 |
|---|---|---|---|---|---|---|---|---|
| P1 | 20:09:47–20:09:59 | 12.2 s | 0 | COMPLETED | 20 / 6 / 14 | 1.1836072E-04 | 0 / 0 | `2b196a7d9f410d776c2c430227613ec4b5e286cf4ee1961a27e58122851379e7` |
| M1 | 20:09:59–20:10:13 | 14.2 s | 0 | COMPLETED | 20 / 6 / 14 | 1.1836072E-04 | 0 / 0 | `8bc3a5650292b4a1a68322c405069312c07b1962c6999584bd712d99d3332f33` |
| P2 | 20:10:14–20:10:27 | 13.8 s | 0 | COMPLETED | 20 / 6 / 14 | 1.1836072E-04 | 0 / 0 | `8d3ae3f858b5ddd201766a2f498deae43835fcbe83c8c01e6a63fb124cdc7d72` |
| M2 | 20:10:28–20:10:40 | 12.2 s | 0 | COMPLETED | 20 / 6 / 14 | 1.1836072E-04 | 0 / 0 | `a5b8ccf6077242787c3a8ff754a83bfa298a54616eb4d91be954fa4a9b739653` |

**Completion evidence for every job:**
- exit code 0;
- stdout "Abaqus JOB <J> COMPLETED" and "Abaqus 2024";
- `.sta` reports success;
- no `***ERROR`;
- ODB present.

Stdout is preserved in `<J>.launch.log`. The DAT, STA and MSG hashes are in `jobs_record.json` (`8ded040d…`), for
example P1 `7b375fef…` / `235f59c4…` / `7dd7d6ae…`.

**Extraction:**
- pinned workflow, `readOnly=True`, extractor SHA equal to R5/R6;
- ODB SHA-256 identical before extraction, after it and at job end, for all four jobs;
- package manifests: P1 `a999340f…`, M1 `4e80919a…`, P2 `af3fef27…`, M2 `b75f44ce…` (`extraction_record.json`
  `19db3096…`).

**Data checks:**
- frequencies: the reader frequencies equal the raw EIGFREQ history exactly;
- √EIGVAL/2π agrees within 6e-8;
- the `.dat` table (5 digits, within 3.4e-5) was not used;
- rigid modes 1–6: shape residual ≤ 5.1e-8; elastic modes 7–20: residual ≥ 0.9994.

**Totals:** exactly four Abaqus jobs ran, and no solver process remains. The R7.0 files, the R4/R5/R6.0 inputs and the
R5_A ODB are unchanged. The output manifest is `hash_manifest.json` `11c47e39…`, covering 152 files.

## 4. FE-to-FE tracking (reference R5_A, full mesh)

| State | Pass 1 singles | Pass 2 subspaces | Order changes | Smallest best MAC | Largest second MAC | {13, 14} subspace cos² |
|---|---|---|---|---|---|---|
| G12 ×1.05 | TRACKED | TRACKED | none | 0.999987 | 0.0015 | 0.999999 / 0.999987, unique |
| G12 /1.05 | TRACKED | TRACKED | none | 0.999987 | 0.0015 | 0.999999 / 0.999987, unique |
| G12 ×√1.05 | TRACKED | TRACKED | none | 0.999997 | 0.0015 | unique |
| G12 /√1.05 | TRACKED | TRACKED | none | 0.999997 | 0.0015 | unique |

- All 14 elastic ranks, including rank 1, are uniquely tracked as singles at both steps.
- Plus and minus states match the same base branch, with MAC(+, −) ≥ 0.99995.
- The close pair 13/14 resolves individually; its subspace is also unique.
- **No branch was refused**, and there is no SUBSPACE_ONLY branch, swap or ambiguity. The only triggered group was the
  frozen {13, 14}.

## 5. G12 sensitivities (all 14 elastic ranks)

**Columns:**
- S(δ): δ = ln 1.05. S(δ/2): δ/2 = ln(1.05)/2.
- Δ = S(δ) − S(δ/2).
- S_ext = S(δ/2) − Δ/3, the central-difference step extrapolation.
- Curvature: d²ln f/d(ln G12)² from (+, R5_A base, −) at δ.
- Resolution: the propagated 2-ulp float32 bound on S(δ/2).
- Ritz: the R5 Kirchhoff surrogate at the same point, h → 0 (R7.0); it is a diagnostic reference, not a target.

| Rank (mode) | f0 (Hz) | S(δ) | S(δ/2) | Δ | S_ext | Curvature | Resolution | Ritz S | FE − Ritz |
|---|---|---|---|---|---|---|---|---|---|
| **1 (7)** | 18.713 | 0.481978 | 0.481980 | −1.6e-6 | 0.481980 | −0.011 | 8.4e-6 | 0.482715 | **−0.00073** |
| 2 (8) | 53.856 | 0.000048 | 0.000048 | ~0 | 0.000048 | ~0 | 5.8e-6 | 0.000048 | 0.000000 |
| 3 (9) | 62.757 | 0.000063 | 0.000062 | +6.2e-7 | 0.000062 | ~0 | 5.0e-6 | 0.000063 | 0.000000 |
| 4 (10) | 65.800 | 0.155861 | 0.155855 | +6.9e-6 | 0.155852 | +0.096 | 9.5e-6 | 0.156504 | −0.00065 |
| 5 (11) | 73.063 | 0.125211 | 0.125200 | +1.0e-5 | 0.125197 | +0.085 | 8.6e-6 | 0.125741 | −0.00054 |
| **6 (12)** | 112.853 | 0.214922 | 0.214923 | −1.2e-6 | 0.214924 | +0.103 | 5.5e-6 | 0.215824 | **−0.00090** |
| 7 (13) | 148.742 | 0.000094 | 0.000095 | −1.1e-6 | 0.000095 | ~0 | 8.4e-6 | 0.000094 | 0.000000 |
| 8 (14) | 158.597 | 0.057660 | 0.057651 | +9.3e-6 | 0.057648 | +0.047 | 7.9e-6 | 0.058016 | −0.00037 |
| 9 (15) | 172.807 | 0.000083 | 0.000085 | −1.8e-6 | 0.000086 | ~0 | 7.2e-6 | 0.000085 | 0.000000 |
| 10 (16) | 181.659 | 0.043907 | 0.043900 | +7.2e-6 | 0.043898 | +0.037 | 6.9e-6 | 0.044175 | −0.00028 |
| 11 (17) | 197.836 | 0.153485 | 0.153479 | +6.8e-6 | 0.153476 | +0.092 | 6.3e-6 | 0.154339 | −0.00086 |
| 12 (18) | 213.909 | 0.129908 | 0.129898 | +1.0e-5 | 0.129895 | +0.085 | 5.8e-6 | 0.130647 | −0.00075 |
| **13 (19)** | 285.478 | 0.164416 | 0.164411 | +5.5e-6 | 0.164409 | +0.095 | 8.8e-6 | 0.165366 | **−0.00096** |
| **14 (20)** | 291.656 | 0.000110 | 0.000112 | −1.1e-6 | 0.000112 | ~0 | 8.6e-6 | 0.000111 | 0.000000 |

The S computed from √EIGVAL agrees with the EIGFREQ values within 2e-6.

**Step stability** (indicator labelled **PROPOSED_DIAGNOSTIC**, not SCIENTIFIC_ACCEPTED):
- every rank is STEP_STABLE under the R7.0 indicator;
- the largest |Δ| is 1.0e-5. That equals the float32 resolution of the δ/2 difference (5–10e-6), so the
  step-truncation error is **not resolved** and is ≲ 1e-5;
- S_ext therefore adds nothing beyond the resolution;
- the proposed 0.005 / 2 % limits were neither used as acceptance nor adjusted.

**Ranks with S ≈ 5e-5 to 1e-4** (2, 3, 7, 9, 14, modes driven by E1 or E2):
- they lie about 10× above the resolution floor and are reported as resolved;
- their **relative** precision is limited (about 5–15 %);
- they correctly show negligible G12 influence.

## 6. Comparison with Ritz

**Highlighted ranks:**
- **Rank 1** (the twist mode): FE 0.48198 against Ritz 0.48272, a difference of −0.15 %. FE and Ritz agree closely on
  the dominant G12 dependence.
- **Rank 6:** 0.21492 against 0.21582, −0.42 %.
- **Ranks 13 and 14:** 0.16441 (−0.58 %) and 0.00011.

**Pattern:**
- every twisting-coupled rank has FE S below Ritz by 0.0003–0.0010 (0.2–0.6 % relative);
- E1/E2-dominated ranks agree within resolution.

**Interpretation, as a hypothesis only:** the difference is consistent with the shear-deformable S4R against
Kirchhoff-Ritz model gap seen in R6 (twisting modes about 0.1–0.3 % softer). It may also include 100×100
discretisation error. Twisting modes were pre-asymptotic in R6.1/V1, and the mesh convergence of S was **not** studied
here.

**Curvature:** small. Twisting-coupled ranks show +0.04 to +0.10 and rank 1 shows −0.011. At δ the second-order term is
≤ 1.2e-4 in ln f, consistent with the step stability.

## 7. Numerical and scientific limitations

- **Coverage:** one parameter (G12), one point (variant A) and one mesh (100×100). FE sensitivities to E1 and E2, the
  B point and other meshes are **NOT_RUN**.
- **Not established:** the mesh convergence of S, identifiability, material properties, A/B selection, FE↔EXP mode
  identity and the 10 % target.
- **Resolution:** the S values are limited by single-precision EIGFREQ (about 1e-5 absolute). Step-truncation error is
  below that floor at both steps.
- **Proposed limits:** the step and mesh limits remain proposals.
- **Mesh gate:** u(ln f_exp) is NOT_AVAILABLE, so the uncertainty-relative mesh gate is NOT_EVALUABLE.
- **Repository:** no repository code was changed, so no repository tests were run (NOT_RUN). The offline pipeline used
  only the frozen R7.0 code and existing services.

## 8. Recommendation

**The pipeline is technically ready for the next authorised batch, R7.0 stage 2:** A100 E1 and E2, 8 jobs. It ran end
to end on real Abaqus output:
- perturbed decks and solves;
- read-only extraction;
- full-mesh shape tracking, including rank 1 and the 13/14 pair;
- central differences at δ and δ/2;
- curvature from the base;
- the Ritz comparison.

No branch was lost, steps agree to the float32 floor, and no defect occurred.

**Recommendations for later batches:**
- Keep δ and δ/2 as the plan requires; dropping δ/2 needs an explicit owner decision.
- E1 and E2 are the parameters for which R7.0 predicted the 3/4 approach (2.4 %) and strong 13/14 near-degeneracy. The
  subspace path may therefore be exercised there for the first time.
- The meshes in stages 3–5 should only follow after stage 2 has been reviewed.

REAL-FIT.R7.1 REVIEW_READY. STOP: the remaining 80 jobs and the next stage are not started.
