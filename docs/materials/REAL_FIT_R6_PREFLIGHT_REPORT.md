# REAL-FIT.R6.0: mesh convergence preflight

Status: **REAL-FIT.R6.0 PREFLIGHT_REVIEW_READY**. Abaqus execution: **NOT_AUTHORIZED, NOT_RUN** (no solve, no datacheck,
no ODB extraction). M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged.

## 1. Git state

- **Branch:** `feature/materials-offline-v1`.
- **Base:** `9443fd4b66d061dc886b74b5ec24bd6a2eec5f56`, equal to `origin/feature/materials-offline-v1` before this commit.
- **`origin/main`:** `0bea1de68dc346d20958e6f53a9e1d634a870f5d`.
- **Working tree:** the tracked tree was clean; the 25 untracked items are preserved.
- **Tracked change:** this report only.
- **Plan source:** the uploaded DOCX "CFRP plate identification plan v2.2" is not in the repository. Section 9 is applied as
  restated in the task and in [ABM_Materials_Implementation_EN.md](ABM_Materials_Implementation_EN.md) §9–10:
  no forced p = 2, and numerical error is kept separate from measurement uncertainty.

## 2. The existing 100×100 mesh, as found in the R4 decks

| Item | Value |
|---|---|
| Decks | `M11_RITZ_MINIMUM_A.inp` `a0668c28…0c927`, `M11_RITZ_MINIMUM_B.inp` `69c485fb…13a3a` (also the R5 solved inputs, same bytes) |
| Topology | One part, 10 201 nodes (101 × 101, row-major in X) and 10 000 S4R elements. Connectivity (a, a+1, a+n+2, a+n+1) is counter-clockwise from +Z |
| Geometry | Part box [−251, 50] × [−270, 30] mm in the plane z = 0. The instance is a translation only (251, 270, 0), so the plate spans 301 × 300 mm. Element size 3.01 × 3.00 mm |
| Section | `*Shell Section` on Set-1, homogeneous, 0.875 mm thick, 5 integration points, no orientation |
| Material | ENGINEERING CONSTANTS. A: E1 59643.140320162354, E2 43592.56647783119, G12 4824.07010224442. B: 44170.77433673189 / 58724.14887983508 / 4817.417308245888. Both: E3 8500, ν12 0.05, ν13 = ν23 0.3, G13 = G23 3000 MPa |
| Density and mass | 1.498e-9 t/mm³. ρ·h·A = 1.18360725e-4 t, equal to the R5 `.dat` TOTAL MASS 1.1836072E-04 |
| Units | mm, t, s, MPa, consistent |
| Step | One perturbation step, `*Frequency` Lanczos, 20 eigenvalues, mass normalisation. Field output U only; history ALLKE, ALLSE |
| Boundary conditions | None: no boundary, load, constraint or orientation keyword (free-free) |
| Material axes | No `*Orientation` and all normals are +Z, so by the Abaqus default convention material 1 = FE X. This is deck-based, NOT_SOLVER_VERIFIED, as in R5 |

## 3. Three-mesh definition

The mesh is a structured, nested family with refinement ratio r = 2:

| Level | Elements | Nodes | Element size (mm) | Source |
|---|---|---|---|---|
| coarse | 50×50 = 2 500 | 2 601 | 6.02 × 6.00 | new, generated |
| mid | 100×100 = 10 000 | 10 201 | 3.01 × 3.00 | existing R4 deck, solved in R5 (reused, not regenerated) |
| fine | 200×200 = 40 000 | 40 401 | 1.505 × 1.500 | new, generated |

**How equivalence was established.** The generator (`r6_mesh.py`) copies every line of the R4 deck verbatim. It replaces
only:
- the node data, written as single-precision values with 9 significant digits, exactly as Abaqus/CAE wrote them;
- the element data;
- the two Set-1 `generate` ranges;
- the heading text.

With n = 100 it reproduces both R4 decks **byte for byte**, for A and B. The 50 and 200 decks are therefore the same
family. Everything else is identical: specimen geometry, thickness, density, all nine constants, section integration,
free-free conditions, modal step and output requests. Parameters were not refitted and the axes were not exchanged.

## 4. Static verification

These are static checks only, by `prepare_r6.py`. The log is `static_verification_log.json`, SHA `94b9b314…`, status
PREFLIGHT_PASSED. The same checks were applied to all six decks, including the two existing 100×100 decks.

**Independent checker:**
- node count (n+1)² and element count n²; contiguous IDs; 4 defined nodes per element; every node used; no coincident
  nodes; all nodes in z = 0; box [−251, 50] × [−270, 30];
- every signed element area > 0, so every normal is +Z. Element areas are uniform to 7.3e-6 relative (single-precision
  coordinates). The total area is 90 300.000 mm²;
- elements are axis-aligned rectangles of 301/n × 300/n mm. The mesh is conforming, with 4n boundary edges;
- S4R only; one homogeneous section `0.875, 5` on Set-1; the Set-1 ranges cover all nodes and elements;
- density 1.498e-9; mass 1.18360725e-4 t on every level, within 1e-6 of the R5 `.dat` value;
- the instance is a translation only;
- no BC, load, constraint, orientation, mass or initial-condition keyword;
- one perturbation step: Lanczos, 20 eigenvalues, mass normalisation.

**Identity checks:**
- all non-mesh lines are identical to the R4 source deck of the same variant;
- the `*Elastic` values equal the R4 minima as exact doubles;
- A and B differ only in the `*Elastic` data line at every level (lines 5139, 20239 and 80439);
- the 100×100 decks are the authorised R4 inputs and the R5 solved inputs.

**Existing project parsers:**
- `research_fe_trial_preflight.structure`: keywords and all section, material, density, step, output and instance
  groups are identical to the source;
- `material_axes`: ESTABLISHED, with n² normals +Z;
- `research_frequency_tuning.read_inp`: a = 301, b = 300, h = 0.875 mm, ρ as above, E1/E2/G12 as R4, no orientation.

**Nesting:** the 51 × 51 lattice of the 50×50 mesh is present, bit-identical, in the 100 and 200 decks of both variants.
The two R5 packages carry 10 201 nodes, and their lattice coordinates agree within 1.5e-5 mm.

**Originals unchanged.** 21 inputs had the same SHA-256 before and after preparation, and again after the dry run:
- the original M11 INP and DAT on `I:`;
- the PolyMAX UNV;
- both R4 decks and the R4 manifest;
- the R5 protocol, Ritz shapes, job, extraction and result records;
- the R5 decks, ODBs and DATs, the R5 package manifests and the baseline package manifest.

**Regression tests:** 4 focused files, 76 tests, about 40 s, all OK. One BLAS thread; no full suite.
- `test_research_fe_trial_preflight`: 10 tests;
- `test_real_fit_r1_tuning`: 27 tests;
- `test_real_fit_r2_stability`: 11 tests;
- `test_new_gui1_workspace`: 28 tests.

**One checker correction.** The first run reported a false failure of the `generate`-range check on every deck,
including the unchanged R4 decks. The cause was that the checker compared text with different leading blanks. It now
compares integers. The decks were byte-identical in both runs. The first-run log is kept as `*_run1_checker_bug.json`.

## 5. Generated INP hashes

All files are in `D:\git\abaqus-modal-comparator-work\runs\real_fit_r6_preflight\decks\`:

| Deck | SHA-256 | Bytes |
|---|---|---|
| `M11_RITZ_MINIMUM_A_M050.inp` | `f081ab5bb2c5e9313aefc9774a288b729c4d4ee61eeca1d36e11da47c2096fa0` | 221 601 |
| `M11_RITZ_MINIMUM_A_M200.inp` | `da07e0922375331fcd853a81256f99427103bc8f90ac48724c33ad97ba58bc5c` | 3 461 905 |
| `M11_RITZ_MINIMUM_B_M050.inp` | `6ead3fc3239a9027436fc994d92487386cb5f1ad55ec78951482221a867038d8` | 221 601 |
| `M11_RITZ_MINIMUM_B_M200.inp` | `439858f02738d5c915d0a701b38570dc60f24c2842f05a75dd686d2e0ed42286` | 3 461 905 |

Other files in the work folder:
- `hash_manifest.json`, SHA `c27bfa4e…`;
- `proposed_execution_protocol.json`, SHA `c04b63eb3802ece0826156e858a543cd4477f7e7ceac23e5b4c2a19eac0c2129`;
- the scripts `r6_mesh.py`, `prepare_r6.py`, `r6_convergence.py` and `write_protocol.py`;
- `r5_common.py`, a byte-identical copy of the frozen R5 helper, SHA `9f26da4f…`.

## 6. Proposed execution and exact job budget (not authorised)

The jobs run sequentially with `cpus=1`, using the R5 command form
`abaqus.bat job=<J> input=<deck> cpus=1 interactive ask_delete=OFF`. Each job gets its own folder under `jobs\`.

| Order | Job | Deck |
|---|---|---|
| 1 | R6_A_M050 | A 50×50 |
| 2 | R6_A_M200 | A 200×200 |
| 3 | R6_B_M050 | B 50×50 |
| 4 | R6_B_M200 | B 200×200 |

**Budget:**
- **New solver jobs: 4.** The R5_A and R5_B mid-level solves are reused, which gives 6 solves in total.
- **Extraction:** 4 read-only calls through the pinned workflow (Abaqus Python, `readOnly=True`).
- **No** datacheck and **no** retry.
- **Minimum alternative:** variant A only, 2 jobs and 2 extractions.

**Reuse of R5 is valid.** The R5 inputs are the same bytes as the mid-level decks, and the R5 packages hold the common
lattice. The condition is that the new jobs report the same "Abaqus 2024" version line, the same launcher and
`cpus=1`; otherwise the run STOPs.

**Stop and completion rules:**
- Any job failure means STOP: no retry and no further job.
- Completion means all of: exit code 0, the stdout line "JOB … COMPLETED", success in `.sta`, no `***ERROR`, and the
  ODB present. No `.log` file is required, which is the correction of the R5 runner defect.
- Each job has a wall-clock cap of 1800 s.

**Resources** (estimates scaled from R5, not measurements):

| Mesh | Equations | Wall time | Memory | ODB |
|---|---|---|---|---|
| 50×50 | 15 606 | about 10 s | under 200 MB | about 1.5 MB |
| 200×200 | 242 406 | about 40–120 s | about 2.5–3 GB to minimise I/O | about 23 MB |

- R5 100×100 measured for comparison: 16.4 s, 567 MB, 5.9 MB ODB.
- Total: about 5 min and about 250 MB of disk.
- Workstation: i7-13700, 31.7 GB RAM, 178 GB free on D:.

## 7. Cross-mesh tracking protocol (frozen in the proposed protocol)

- **Rigid modes:** classified by the shape-based rigid-body residual ≤ 0.02 on the full mesh of each level, exactly as
  in R5.
- **Common reference grid:** the 2 601 nodes of the 51 × 51 lattice. These are exact coincident nodes in all meshes, so
  no interpolation is needed. Shapes are U1–U3, unweighted; package coordinates must agree within 1e-4 mm.
- **Reference:** the R5 100×100 solve of the same variant.
- **Directions:** M100 → M050, M100 → M200, and M050 → M200 as a consistency check.
- **Passes:** the R5 tracker (`r5_common.track`, program `branch_tracker`, STRICT policy, tracking MAC ≥ 0.90, unique),
  in three passes:
  - pass 1: single modes;
  - pass 2: 3 %-triggered pairs as subspaces, which need both principal-angle cos² > 0.95;
  - pass 3: per-row diagnostics.
- **Close-mode groups:**
  - frozen now from the R5 spectra: {rank 13, rank 14} for A and for B;
  - further groups come from the same trigger applied mechanically after the solve; they are reported and never used
    to re-pair modes.
- **Which branches enter convergence:** only those tracked in both directions with a consistent partner. All others
  are NOT_EVALUABLE, with the reason recorded.
- **EXP rows:** they keep the R5 rank hypothesis on the 100×100 mesh: records 1–9 FIT, 10–11 HOLDOUT, diagnostic only.
  Each branch is followed to the other meshes by shape, never by rank number or frequency.
- **Window limit:** 20 eigenvalues as in R5, so ranks 12–14 may leave the window. The EXP rows use ranks 1–11.

**Dry run** (`dry_run_tracking_convergence.json`, plumbing only, no new data):
- A100 → A100 tracks all 14 ranks with MAC 1.000, and the {13, 14} subspace is unique with cos² 1.0.
- A100 → B100 exercises the refusal paths: BRANCH_LOSS / CLUSTER_LOSS, with rank 14 leaving the window. This is not a
  result.

## 8. Convergence metrics (defined, not computed)

**Per tracked branch** (`r6_convergence.richardson`, r = 2):
- e21 = f100 − f200, e32 = f50 − f100, R = e21/e32.
- **MONOTONE** (0 < R < 1):
  - observed order p = ln(e32/e21)/ln 2;
  - Richardson extrapolation f_ext = f200 + (f200 − f100)/(2^p − 1);
  - discretisation error δ_h = ln(f_h/f_ext);
  - GCI_fine = 1.25·|e21/f200|/(2^p − 1) and GCI_mid = 1.25·|e32/f100|/(2^p − 1), plus the asymptotic-range ratio.
- **OSCILLATORY**, **DIVERGENT** or **RESOLUTION_LIMITED** (|e|/f < 1e-6, single-precision EIGFREQ): no p and no
  extrapolation.
- **Not forced:** p = 2 is never assumed.
- **Subspace branches:** members are sorted within the group, plus the group mean.
- **Synthetic self-test:** p = 1.7, 2.0 and 2.6 and f_ext are recovered exactly; the oscillatory, divergent and
  resolution cases are classified correctly.

**FIT and HOLDOUT** are reported separately:
- max |δ_100| and RMS δ_100;
- max |δ_200|;
- the change of the R5 RMS ln(f/f_EXP) when f100 is replaced by f_ext, as a diagnostic.

**Shape convergence** is computed on the common lattice: 1 − MAC for 50↔200, 100↔200 and 50↔100, for U1–U3 and U3
only; subspaces use principal-angle cos². There is no shape extrapolation.

**Numerical error is not measurement error.** δ_h is never added to a covariance and never used to weaken a residual.

## 9. Missing acceptance input: u(ln f_exp)

**Investigation:** the PolyMAX UNV (`76db80ae…`, read only) holds datasets 151, 164, 2411, 31 × 82 trace lines and
13 × 55.
- The 55 records are 11 Polymax_bravo modes, plus two residual pseudo-modes at 14.90 and 240.95 Hz.
- Each record header carries only the frequency and the damping.
- There is one estimate, no repeated or alternative PolyMAX estimates, and no confidence or standard-deviation field.
- The experiment folder holds no other estimate for this specimen; it contains only the raw-FRF UNV.
- The program's QC contract (`experimental_qc`) reports a frequency uncertainty only when the source provides one.

**Result:** u(ln f_exp) is **NOT_AVAILABLE**, so the plan's uncertainty-relative mesh acceptance threshold is
**NOT_EVALUABLE**. No uncertainty is invented, and damping is not used as a substitute. Re-estimating the PolyMAX fit from
the raw FRFs would be a new experimental analysis; it is outside this task.

## 10. Sensitivity convergence (later stage, not authorised)

- **Definition:** S_k,p = ln(f_k(p·1.01)/f_k(p))/ln 1.01 for p ∈ {E1, E2, G12}, with every other constant fixed.
  This is evaluated on each mesh and each variant. The perturbed mode is tracked to the unperturbed one on the same mesh,
  using MAC ≥ 0.90 and the subspace rule.
- **Base points:** the six frequency solves above.
- **Additional FE jobs:**
  - **18** for forward differences, both variants (3 parameters × 3 meshes × 2);
  - **9** for variant A only;
  - **36** for central differences, both variants.
- **Decks:** built with `build_variant`, changing one `*Elastic` line.
- **Analysis:** convergence of S uses the same Richardson rule; comparison with the Ritz R2 sensitivities is a
  diagnostic only.

## 11. Scientific limitations

- The family covers h-refinement of one element type (S4R, reduced integration) only. Element-type error (S4R vs S4 or
  S8R) and the ν12, transverse-shear and thickness assumptions are outside it.
- The equivalence proof covers the structured M11 family. No other meshing would follow from it.
- The convergence numbers are discretisation estimates for the two research minima. They say nothing about the material
  values, the axis assignment (A and B are not selected) or the FE↔EXP correspondence, which remains the R5 rank
  hypothesis without experimental-to-FE MAC.
- Without u(ln f_exp) no mesh-acceptance verdict is possible.
- No identification, no calibration release, and no claim about the 10 % target.

REAL-FIT.R6.0 PREFLIGHT_REVIEW_READY. STOP: awaiting owner review and explicit solver authorisation.
