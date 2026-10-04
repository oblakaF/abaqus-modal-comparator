# M4 decision record — open parameters before M4.6 / M4.9

**Status:** PROPOSED. This document is the worker's preparation and awaits a
SUPERVISOR decision. It is not a DECISIONS.md entry; accepted items are appended there
by the supervisor's decision.

**Date:** 2026-10-04. **Branch:** `auto-id/m4`.

**Scope:** three items the first M4 batch left as explicit inputs or provisional
values. No code changes are proposed here. Every value below is already explicit in
code (hashed policy or required argument), so a decision changes data, not logic.

**Batch review status:**

| Mini-step | Status |
|---|---|
| M4.1, M4.3, M4.4, M4.5, M4.7, M4.8 | REVIEW_READY (acknowledged) |
| M4.2 | `BLOCKED_WAITING_FOR_ODB_SHAPE_EXTRACTION` |
| M4.6, M4.9 | TODO; not authorised |

---

## 1. M4.3 — modal-family classifier policy (`auto-id/modal-family/v1-provisional`)

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

**Options:**
- **(A) Accept the values as provisional v1.** They are frozen by policy hash and
  revisited once real FE shapes exist.
- **(B) Defer acceptance** until the classifier has been run on real SP02/SP13
  outer-surface shapes. This needs the same gated ODB shape extraction as M4.2.

**Worker recommendation: (B), with (A) as the interim state.**
- Keep the values as provisional (already hashed).
- When the extraction gate is authorised, run the classifier on the baseline shapes of
  every frozen row and record P_x, P_y, the diagonal parities, nodal counts and mirror
  coverage per mode, as evidence.
- Then fix v1 (or a v2 with justified changes) by decision.

**Acceptance check proposed for that run:**
- every frozen row classifies without a coverage refusal;
- the lowest torsion-dominated (odd-odd) family is identified.

---

## 2. M4.8 — LM hyperparameters

The SPEC-given values stay fixed:

| Value | Source |
|---|---|
| μ increase × 10 on a rejected step | SPEC §8 |
| ≤ 5 iterations | SPEC §8 |
| Stop when max\|Δx_j\| < 0.2·sd_j | SPEC §8 |
| ±5 % central differences | SPEC §6 S4 |

The SPEC gives no values for the following; the code requires them explicitly.

| Parameter | Proposed | Rationale | Alternatives |
|---|---|---|---|
| `mu_initial` (μ₀) | **1e-3** | D = diag(JᵀJ) makes μ dimensionless. 1e-3 starts close to Gauss–Newton (the classic Marquardt choice). The problem is nearly log-linear (CARBON-5A: smooth ±5 % response). | 1e-2 (more conservative first step) |
| `mu_decrease` | **10** (μ ← μ/10 after an accepted step) | Standard Marquardt / Nielsen schedule, symmetric to the SPEC × 10 increase | 1 (keep μ): fewer large steps, but slower |
| `max_step_attempts` | **3 per iteration** | μ can rise to 1 (three × 10 increases from 1e-3), which is already strongly damped. After a first rejection the finite-difference Jacobian is refreshed (2·n_p = 4 solves), so 3 attempts can cost up to 3 + 4 solves. | 2 (cheaper); 4 (more robust) |
| `solve_budget` | **20 per specimen per identification run, counting every evaluation the loop requests** (reference r(x₀), all finite-difference solves and every trial step) | Matches the M4 gate (≤ 20 authorised solves) and SPEC §8 ("about 10–20 per specimen" for two global parameters) | 15 (tighter); 20 excluding the reference solve |

**Expected solve count for the nearly linear two-parameter case:**
- 1 reference solve;
- 4 finite-difference solves;
- about 1 trial per iteration for 2–4 iterations;
- **about 7–9 in total.**

**Worst case inside the budget:** a refresh (4) plus 3 rejected attempts in one
iteration. The budget ends the run with `SOLVE_BUDGET`, which is a non-result and
never an identification.

**Questions for the supervisor:**
1. Does the reference solve at p0 count toward the 20? Proposed: yes. If an archived
   baseline is reused, it counts as 0 solves but is still recorded.
2. Can the four archived CARBON-5A ±5 % solves serve as the first finite-difference
   Jacobian, as zero new solves? Their INPs are byte-identical to the jobs the loop
   would generate (M3).

   This is possible only after shape extraction (Abaqus Python, gated), because
   tracking needs shapes.

---

## 3. M4.9 — exact acceptance requirements (proposal)

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
3. **HUMAN gate for M4.9,** stating the specimen(s), the solve budget and the
   extraction runs.

### Synthetic-twin definition (SPEC §17 M4)

| Item | Requirement |
|---|---|
| Specimen | **One specimen first; worker proposal SP13** (stronger E/G12 response in CARBON-5A; 12 PolyMAX modes). SP02 only by a separate decision. |
| Truth | E_in_plane = 45000 MPa, G12 = 4000 MPa (carbon-property-set/v1; everything else unchanged) |
| Synthetic experiment | The truth solve's FE modes, read through the accepted FrozenRegistration onto the measured grid (U3). Frequencies multiplied by (1 + ε_i), ε_i ~ N(0, 0.003²), with a fixed recorded seed. |
| Start | E = 52000, G12 = 4500 MPa (p0) |
| Observations | Frozen at p0 under `STRICT_IDENTIFICATION_PAIRING` against the synthetic experiment. FROZEN status required. Holdouts by family (M4.3). At least 2 fit terms. |
| σ | Per row σ = 0.003 (the injected noise), explicit. No provisional setup term in the twin, because the data are synthetic. |
| Solve budget | ≤ 20 identification solves, counted as in §2. The truth solve and the extraction runs are authorised and recorded separately. |

### Pass criteria (all required)

1. **Convergence:** status `CONVERGED`, within the budget.
2. **Recovery within 1σ:** |ln(p̂_j / p_true,j)| ≤ sd_j for both E_in_plane and G12.
   sd_j is the local sqrt(diag((JᵀJ)⁻¹)) at p̂ from the whitened residuals; this is the
   M4 stop-rule sd, not the M5 `statistical_sd`.
   - **Open point:** CARBON-5A shows G12 is the weak direction, so sd_G may be large
     and a 1σ check of G12 nearly empty.
   - **Proposal:** report sd_G. If sd_G > 8 % (the SPEC §10 fit threshold), record
     G12 as "not identifiable in this twin", and require the 1σ recovery for E alone.
     The full verdict remains M5's.
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
