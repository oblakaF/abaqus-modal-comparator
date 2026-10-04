# M4 decision record — open parameters before M4.6 / M4.9

**Status:** PROPOSED, with SUPERVISOR review decisions recorded (2026-10-04). It is not
yet a DECISIONS.md entry. The supervisor transfers accepted items there by a later
decision.

**Branch:** `auto-id/m4`.

**Scope:** three items the first M4 batch left as explicit inputs or provisional
values. No code changes are made or proposed here; every value is already explicit in
code (hashed policy or required argument).

**Batch status:**

| Mini-step | Status |
|---|---|
| M4.1, M4.3, M4.4, M4.5, M4.7, M4.8 | REVIEW_READY (acknowledged) |
| M4.2 | `BLOCKED_WAITING_FOR_ODB_SHAPE_EXTRACTION` (kept) |
| M4.6, M4.9 | TODO; not authorised; implementation not started |

No Abaqus or Abaqus Python runs.

## SUPERVISOR review decisions (2026-10-04)

| # | Topic | Decision |
|---|---|---|
| 1 | M4.3 classifier | The current thresholds stay **PROVISIONAL** and are not promoted to final policy. They are validated after real FE shape extraction. Any change needs a separate decision. |
| 2 | M4.8 LM | **Approved:** μ₀ = 1e-3; accepted step μ ← μ/10; rejected step μ ← 10μ; at most 3 step attempts per iteration. **Solve budget: 20 Abaqus solves in total; the initial p0 reference evaluation counts toward it.** |
| 3 | Archived CARBON-5A ±5 % solves | **Not allowed** as Jacobian or branch evidence until a gated ODB shape extraction is approved **and** completed. M3 byte identity alone is not sufficient. |
| 4 | M4.9 | SP13 stays the first twin specimen. G12 identifiability is an **observed result, not a modified acceptance criterion**. The proposed 8 % rule is **not** added. |
| 5 | Status | M4.2 stays BLOCKED_WAITING_FOR_ODB_SHAPE_EXTRACTION. M4.6 and M4.9 stay TODO. No Abaqus. No implementation of M4.6 / M4.9. |
| 8 | M4.6 design (see §6) | **Approved:** solver profiles as separate data; reuse of the validated p0 and ±5 % pack evaluations (counted in the 20; identification evaluations and actual Abaqus solves tracked separately); the validated full extraction only; guards (`subprocess` only in `forward_solver.py`, no `abaqus_bridge` cache path, `run_abaqus_extraction` only as a controlled helper); retention rules. **M4.6 scope:** architecture plus fake-solver tests, no real solve, no M4.9. |
| 7 | Observation design (see §5) | Real SP13 identification is **refused** (option C). The M4.9 twin follows option B, with a synthetic experiment of truth FE modes 7–30. Observations come from the normal M4.3 / M4.4 policies, the torsion holdout from policy (not hard-coded), and twin clusters from the validated SP13 ±5 % packs (no new extraction). |
| 6 | M4.9 budget clarification | The truth-generation solve is a **separate** authorised Abaqus solve and does **not** count toward the 20. The identification loop has at most **20** Abaqus solves in total, p0 included. Abaqus Python ODB shape extraction needs a **separate HUMAN Abaqus gate**, does **not** count toward the 20, and is data preparation, not optimisation. |

---

## 1. M4.3 — modal-family classifier policy (`auto-id/modal-family/v1-provisional`)

**Decision:** PROVISIONAL, not final. The values below stay frozen by policy hash.

SPEC §12.2 fixes the quantities (P_x, P_y, diagonal parities for near-square panels,
nodal-line counts) but no numbers.

| Field | Provisional value | Meaning | Rationale | Risk if wrong |
|---|---|---|---|---|
| `parity_threshold` | 0.80 | \|P\| ≥ 0.80 counts as a definite even/odd parity; below it, MIXED | P = (E_sym − E_anti)/E_total, so \|P\| ≥ 0.8 means ≥ 90 % of the shape energy has that symmetry | Too high: real modes of imperfect panels become MIXED and no torsion family is found. Too low: mixed shapes get a definite family. |
| `mirror_tolerance` | 2 % of min(Lx, Ly) | Largest distance between a reflected node and its mirror node | ≈ 10 mm on 500–520 mm panels; covers non-matching but symmetric meshing | Too small: an asymmetric local mesh (SP13 `mesh_local`) fails coverage. Too large: mirror pairs are wrong. |
| `minimum_mirror_coverage` | 0.95 | Share of surface nodes that must have a mirror node | Refuse rather than classify on a partly matched mesh | Too strict: the classifier refuses real meshes. |
| `near_square_tolerance` | 0.05 | Diagonal parities when \|Lx − Ly\|/max ≤ 5 % | SP02 (500 × 500) and SP13 (510 × 520, 1.9 %) both qualify | Only affects whether diagonal parities are computed and reported. |
| `nodal_grid_points` | 41 | Resampling grid for counting nodal lines | ≈ 12.5 mm spacing on a 500 mm panel; resolves about 8 half-waves | Too coarse: higher families are miscounted. |
| `nodal_amplitude_floor` | 0.05 | \|w\| < 5 % of max is treated as zero when counting sign changes | Suppresses noise crossings near nodal lines | Too high: weak lobes are missed. |

**Validation after the extraction gate.**
- **Run:** the classifier on the baseline outer-surface shapes of every frozen row.
- **Record as evidence:** P_x, P_y, the diagonal parities, nodal counts and mirror
  coverage per mode.
- **Proposed check:**
  - every frozen row classifies without a coverage refusal;
  - the lowest torsion-dominated (odd-odd) family is identified.

Promoting the values to final, or changing them, needs a separate decision.

**Validation run (2026-10-04, SP13 baseline shape pack; values unchanged).** The
proposed check is met:
- every frozen row classifies, with mirror coverage 1.0 on all four reflections;
- the lowest odd-odd family is identified (FE 7, 22.49 Hz).

Details are in `docs/auto_id/fe_shapes/SP13_a46d08b52995e078.families.json`. The values
remain PROVISIONAL.

---

## 2. M4.8 — LM hyperparameters

**Decision: approved.**

| Parameter | Value | Source |
|---|---|---|
| `mu_initial` (μ₀) | **1e-3** | SUPERVISOR decision. D = diag(JᵀJ) makes μ dimensionless; starts near Gauss–Newton. |
| `mu_decrease` (accepted step) | **10** (μ ← μ/10) | SUPERVISOR decision |
| `mu_increase` (rejected step) | **10** (μ ← 10μ) | SPEC §8; confirmed |
| `max_step_attempts` | **3 per iteration** | SUPERVISOR decision |
| `solve_budget` | **20 Abaqus solves in total, including the initial p0 reference evaluation** | SUPERVISOR decision |
| `max_iterations` | 5 | SPEC §8 (unchanged) |
| stop rule | max\|Δx_j\| < 0.2·sd_j | SPEC §8 (unchanged) |
| finite differences | central, p·(1 ± 0.05) | SPEC §6 S4 (unchanged) |

**How this maps to the existing code** (M4.8, no change needed):
- `LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=20)`;
  the SPEC defaults cover the rest.
- The loop's budget already counts every evaluation it requests: the reference r(x₀),
  all finite-difference solves and every trial step. That matches "p0 counts".

**Solve count:**
- **Expected**, for the nearly linear two-parameter case: 1 reference + 4
  finite-difference solves + about 1 trial per iteration over 2–4 iterations, about
  7–9 solves.
- **Over budget:** reaching 20 ends the run with `SOLVE_BUDGET`. That is a non-result,
  never an identification.

**Budget clarification (SUPERVISOR decision, 2026-10-04):**

| Abaqus activity | Counts toward the 20? | Authorisation |
|---|---|---|
| Identification-loop solves: the p0 evaluation, all finite-difference solves, every trial step | **Yes — at most 20 in total, p0 included** | M4.9 HUMAN gate |
| Twin truth-generation solve (45000 / 4000) | **No** | A separate authorised Abaqus solve |
| Abaqus Python ODB shape extraction | **No** | A separate HUMAN Abaqus gate. It is data preparation, not optimisation. |

---

## 3. Archived CARBON-5A ±5 % solves

**Decision:** not allowed as Jacobian or branch evidence until a gated ODB shape
extraction is approved **and** completed.
- M3 byte identity of their INPs is not sufficient on its own.
- The same holds for the archived CARBON-4C baseline (M4.2 stays blocked).

---

## 4. M4.9 — acceptance requirements

The SUPERVISOR decisions (SP13 first; G12 identifiability observed; no 8 % rule) are
applied below. The remaining items are the worker's proposal; the review did not
contradict them. They become final with the DECISIONS entry.

### Prerequisites (each separately authorised)

1. **M4.2 unblocked:** FE shapes for the baseline, by gated Abaqus Python extraction
   from the archived ODBs or by a new authorised solve.
2. **M4.6 authorised and REVIEW_READY:**
   - a resumable pipeline: candidate → M3 `prepare_forward_jobs` → Abaqus → ODB →
     extraction → tracking → objective;
   - content-based ODB identity (audit V5);
   - the solve command pinned to the accepted CARBON-4C/5A convention. From the
     archive:

     ```
     abq2024.bat job=<job_name> input=<inp> cpus=<n> interactive ask_delete=OFF
     ```

     with cpus = 8 for SP02 and 1 for SP13.
3. **HUMAN gate for M4.9,** stating the specimen, the solve budget and the extraction
   runs.

### Synthetic-twin definition (SPEC §17 M4)

| Item | Requirement |
|---|---|
| Specimen | **SP13** (SUPERVISOR decision). SP02 only by a separate decision. |
| Truth | E_in_plane = 45000 MPa, G12 = 4000 MPa (carbon-property-set/v1; everything else unchanged) |
| Synthetic experiment | The truth solve's FE modes, read through the accepted FrozenRegistration onto the measured grid (U3). Frequencies multiplied by (1 + ε_i), ε_i ~ N(0, 0.003²), with a fixed recorded seed. **Built from the truth solve, never from real PolyMAX observations. Initial mode set: all available FE modes 7–30** (SUPERVISOR decision, §5). |
| Start | E = 52000, G12 = 4500 MPa (p0) |
| Observations | Frozen at p0 under `STRICT_IDENTIFICATION_PAIRING` against the synthetic experiment. FROZEN status required. Holdouts by family (M4.3, provisional policy). At least 2 fit terms. **The usable observations are decided by the normal M4.3 family policy and M4.4 cluster confirmation; nothing is hand-picked** (§5). |
| σ | Per row σ = 0.003 (the injected noise), explicit. No provisional setup term in the twin, because the data are synthetic. |
| LM | The approved settings of §2. |
| Solve budget | At most 20 Abaqus solves for the identification loop, p0 included (§2). The truth-generation solve and the ODB shape extractions are authorised separately and do not count. |

### Pass criteria (all required)

1. **Convergence:** status `CONVERGED`, within the budget.
2. **Recovery within 1σ (SPEC §17), unmodified:** |ln(p̂_j / p_true,j)| ≤ sd_j for
   **both** E_in_plane and G12. sd_j is the local sqrt(diag((JᵀJ)⁻¹)) at p̂ from the
   whitened residuals; this is the M4 stop-rule sd, not the M5 `statistical_sd`.
   - **Observed, not a criterion change (SUPERVISOR decision):** G12 identifiability.
     Report sd_G and sd_E as observed results. No 8 % rule or other threshold is
     added. The production identifiability verdict stays with M5.
3. **Branch-exchange refusal:**
   - **Setup:** an artificial exchange (shape mixing ≥ 45° between two tracked modes)
     injected into one candidate's FE state between iterations, without an extra
     solve.
   - **Required result:** status `REFUSED` (`BRANCH_LOSS`, `AMBIGUOUS` or
     `BRANCH_EXCHANGE`), no further solves, unchanged frozen rows, no re-pairing.
   - **Frequency crossing:** a crossing with stable shapes is **not** an exchange and
     must be tracked (M4.5 behaviour).
4. **Determinism:** a rerun with the same inputs gives identical job hashes,
   observation hash, policy hashes and result. Reruns reuse existing solves by content
   hash, with no new solves.
5. **Provenance:** a result record with:
   - INP and ODB SHA-256 for every solve;
   - the noise seed;
   - all policy hashes (pairing, classifier, LM settings);
   - the Abaqus version and command convention;
   - the solve count.

   It is added to EVIDENCE.md as PENDING SUPERVISOR REVIEW.
6. **No change to M3 contracts:** every candidate INP is generated by
   `forward_builder`, and the M3 byte-for-byte gate still passes.

### Explicitly not part of M4.9

- **M5:** practical identifiability, q_G, `statistical_sd`, Birge and model-form
  robustness.
- **Real SP02/SP13 identification:** production physical readiness is `NOT_READY`.

---

## 5. Observation design (SUPERVISOR decisions, 2026-10-04)

**Context:**
- **Frozen set:** the SP13 candidate frozen set has R1 (exp 4 ↔ FE 10) and R2 (exp 5 ↔
  FE 11).
- **M4.4 result:** the two are independent branches, not a cluster.
- **M4.3 holdout result:** no torsion family among the rows; the validation holdout is
  R2, which leaves R1 as the only fit row.
- **Worker estimate** (diagnostic, local, carbon-only, σ = 0.3 %; from the ±5 %
  central differences of the pinned SP13 pack frequencies): the R1/R2 sensitivity
  rows are near-collinear.
  - R1 (FE 10): S_E 0.3646, S_G12 0.1234. R2 (FE 11): S_E 0.3662, S_G12 0.1207.
  - The rows are 0.45° apart, with condition number about 250.
  - sd(ln E) ≈ 0.44 and sd(ln G12) ≈ 1.32, even with both rows fitted.
  - This is not the SPEC §10 verdict, which belongs to M5.

### 5.1 Real SP13: option C accepted

- Real SP13 identification is **refused**.
- **Reason:** insufficient strict observations, and near-collinear sensitivity
  directions of R1/R2.
- MAC and frequency gates are **not** relaxed.
- The holdout policy is **not** overridden for real data.
- Option A (fitting both R1 and R2) is not adopted.

### 5.2 M4.9 synthetic twin: option B

- The synthetic experiment is built from the **truth solve**, never from real PolyMAX
  observations.
- **Initial synthetic mode set:** all available FE modes 7–30 of the truth solve.
- The usable observations are decided by the normal pipeline:
  - the strict M4.1/M4.2 freeze at p0 against the synthetic experiment;
  - the M4.3 family policy (provisional thresholds, holdouts by family);
  - M4.4 cluster confirmation for triggered pairs.
- Nothing is hand-selected.

### 5.3 Torsion holdout

- With k_int disabled, the normal M4.3 policy (`select_holdouts`) picks the **lowest
  torsion-dominated (odd-odd) family among the frozen rows** as the torsion holdout.
- On the validated SP13 baseline shapes, the lowest odd-odd family is FE 7 (22.49 Hz,
  `Px:O|Py:O|nx:1|ny:1`; M4.3 record). It is therefore the expected torsion-holdout
  candidate once it is a frozen twin row.
- FE 7 is **not hard-coded**. The selection follows from the policy and the twin's
  frozen rows.

### 5.4 Twin clusters

- M4.4 confirmation inside the twin may reuse the validated SP13 ±5 % shape packs
  (E±, G12±).
- **No new extraction is authorised.**
- Expected triggered pairs (from the baseline frequencies; to be confirmed, not
  assumed) include FE 13/14, 17/18, 20–22 and 26/27.

### 5.5 Status

- M4.6 and M4.9 are not started; each needs its own authorisation.
- No code change follows from these decisions at this point.

---

## 6. M4.6 design (SUPERVISOR decisions, 2026-10-04)

Source: the M4.6 preparation review (worker, review only). Implementation has not
started.

### 6.1 Solver profiles

- **Approved as separate data**, for example `docs/auto_id/solver_profiles/<specimen>.json`.
- Abaqus version, `cpus`, the command template and the scratch policy stay **outside**
  the M3 forward-model manifests.
- The M3 forward contracts are unchanged (`forward_builder.py`, `forward_model_manifest.py`,
  forward-model JSONs, and `shared_carbon_forward.py` as the oracle).

### 6.2 Reuse of archived evaluations

- **Approved.** The validated p0 (CARBON-4C baseline) and ±5 % (CARBON-5A E± / G12±)
  shape-pack evaluations may be reused.
- **Reused evaluations count toward the 20-evaluation budget.**
- Two counts are tracked separately:
  - **(a)** identification evaluations (reused and new);
  - **(b)** actual Abaqus solves executed.

### 6.3 Extraction

- Keep the **validated full extraction path**: the pinned, unchanged
  `abaqus_scripts/extract_odb.py` (`039aa067…`) plus the validated pack build and checks.
- **No surface-only extractor in M4.6.** Any new Abaqus Python extractor needs a
  separate gate.

### 6.4 Guards

- `subprocess` may be imported **only** in `forward_solver.py`.
- The existing `abaqus_bridge` cache path (`load_or_extract_odb`, path/size/mtime
  signature) must **not** be used.
- `run_abaqus_extraction` may be reused **only** as an execution helper under the new
  controlled path, with content identities and no path/mtime cache.

### 6.5 Retention

- Temporary raw extractions are deleted after the pack validates.
- Validated ODBs are kept until the run review is complete.
- Shape packs and provenance are kept permanently.

### 6.6 M4.6 scope

- Implement and test the **architecture only**.
- Fake-solver tests are allowed.
- **No real Abaqus solve.**
- **No M4.9.**

---

## 7. M4.6 SP13 smoke gate (HUMAN authorisation and result, 2026-10-04/05)

### 7.1 Authorisation

- **Scope:** exactly **1 Abaqus 2024 solve** and **1 pinned `extract_odb.py`
  extraction** for `SP13_a46d08b52995e078` (p0, 52000 / 4500 MPa).
- **Constraints:**
  - the approved SP13 solver profile;
  - run directory `D:\abaqus_m4_smoke`;
  - no LM loop, no M4.9, no other candidates;
  - no code or M3 changes;
  - no retry on failure.
- **Expected verdict:** REPRODUCED, meaning all 30 EIGFREQ values match the archive
  and the generated shape-pack content SHA matches the validated baseline pack.
  NUMERICALLY CONSISTENT or NOT REPRODUCED means stop and report.

### 7.2 Memory threshold (HUMAN decision)

- **Initial threshold:** 19 GB available RAM, the archived peak of this job.
- **Updated:** 19 GB was a conservative reference peak, not a hard requirement.
  About 15.75 GB available was accepted.
- **Grounds:**
  - the Abaqus minimum memory estimate of 3.9 GB (archived `.dat`; memory to minimise
    I/O is 43.6 GB);
  - the archived SP13 behaviour;
  - the available virtual memory (commit limit 77 GB) and disk.
- **Observed:** a memory peak of 18 GB and 620 s wall-clock (archive 584 s).

### 7.3 Result: **REPRODUCED**

| Check | Result |
|---|---|
| Solve | Completed: `.sta` marker, Abaqus 2024; ODB 715 614 536 bytes (SHA `56da620e…`; it differs from the archive only through ODB run metadata) |
| Extraction | Pinned script `039aa067…`; all checks PASS; raw deleted after validation |
| Frequencies | **30/30 EIGFREQ exactly equal** to `carbon4c/post_solve_SP13.json` |
| Shape pack | Content SHA **`7941545b59390a65…` identical** to the validated baseline pack; minimum MAC 1.0 |
| M3 contracts | Unchanged |

### 7.4 Archive proposal (pending)

- **Do not duplicate** the identical shape pack. Reference the existing
  `carbon-project-archive:fe_shapes/SP13_a46d08b52995e078.npz`.
- **Archive smoke provenance only**, under `carbon-project-archive/m4_smoke/`:
  - `journal.json` (hash-chained: solve, extraction, comparison);
  - `comparison.json`;
  - `extraction_manifest.json`;
  - logs: `solve.log`, `.sta`, `.msg`, `.dat`, `.prt`, `.com`.

  Each file is pinned by SHA-256 in `ARCHIVE_MANIFEST.json`.
- **ODB:** kept in `D:\abaqus_m4_smoke` until the run review is complete (retention
  rule). Its later archiving or deletion needs a decision.
