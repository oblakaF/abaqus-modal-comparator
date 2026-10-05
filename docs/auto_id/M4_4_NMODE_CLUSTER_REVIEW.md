# M4.4 N-mode cluster design review (analysis only)

**Status:** PROPOSAL for SUPERVISOR review (2026-10-05). It changes no policy, code, threshold or
acceptance criterion. No Abaqus was run. Until a decision is made, M4_DECISION_RECORD §8.2 stays in
force: UNSTABLE and UNSUPPORTED groups are REFUSED.

**Trigger:** M4.9 truth gate (M4_DECISION_RECORD §9), verdict REFUSED_BEFORE_IDENTIFICATION. Two
frozen trigger groups have more than two modes: FE 13–15 (R7–R9) and FE 20–23 (R14–R17).

---

## 1. Evidence: what the two refused groups are

**Method:** read-only diagnostics on validated packs only:
- p0 `7941545b…`;
- E± and G12± (the validated ±5 % packs);
- truth `758add0c…`.

Shapes are compared on the full surface (U1, U2, U3), the M4.4 primary basis. "Best" is the
best FE-to-FE MAC of each baseline member among perturbed modes. The N-subspace value is the
smallest cos² of the principal angles between the N-mode baseline subspace and the best N-mode
perturbed subspace.

| Group | Members (M4.3 family) | p0 MAC between members | Best individual MAC (E±, G12±, truth) | Counterparts with MAC ≥ 0.9 | N-subspace min cos² | Spanning N-subsets with cos² > 0.95 |
|---|---|---|---|---|---|---|
| FE 13–15 | 13 `E/O 0,3`; 14 `O/E 3,0`; 15 `O/O 1,3` | 0.0000 | ≥ 0.99997 | exactly 1 each, same mode number | ≥ 0.99997 | 1 |
| FE 20–23 | 20 `E/E 0,4`; 21 `E/E 4,0`; 22 `O/E 1,4`; 23 `E/O 4,1` | ≤ 0.00001 | ≥ 0.99987 | exactly 1 each, same mode number | ≥ 0.99991 | 1 |
| For comparison: the 2-mode groups judged INDEPENDENT (FE 10/11, 17/18, 24/25, 26/27, 28/29) | — | 0.0000 | ≥ 0.9957 | 1 each | ≥ 0.9957 | 1 |

**Reading:**
- Every member of both refused groups keeps its own branch identity in every tested direction
  and at the truth point (−13.5 % E, −11.1 % G12).
- The members are mutually orthogonal and belong to different parity classes. The only
  exception is FE 20/21, the near-square (0,4)/(4,0) pair.
- These are **frequency coincidences, not interacting clusters**. By the logic SPEC §12.4
  already applies to pairs, they would be independent observations. They are refused only
  because the implementation does not examine groups of more than two modes (M4.4 docstring;
  M4_DECISION_RECORD §8.2).

**Side observation: the edge of the mode set.**
- FE 30 at p0 is the (4,4) mode. In the E−, G12+ and truth states it moves **above** mode 30,
  outside the extracted range 7–30. Its best MAC within the range is 0.01–0.28.
- This is why experimental mode 24 (truth FE 30) was excluded by the strict freeze. It is an
  edge-of-mode-set effect, not mode mixing.
- In E+ and G12−, FE 29 and FE 30 swap order. That is a crossing with stable shapes, which
  M4.5 tracks.
- **Risk for any later LM loop:** a tracked row near the top of the range (R23 = FE 29, the
  validation holdout) can leave the range. The result would be BRANCH_LOSS, a correct refusal
  but an avoidable one. This is independent of the options below and noted for the
  identification-loop gate.

---

## 2. Options

### A) General N-dimensional subspace examination

**Rule:** the frequency trigger stays a trigger. For a group of N ≥ 2 members, the same decision
tree as the 2-mode rule applies, with N-dimensional principal angles:

1. **UNSTABLE.** The N-dimensional subspace is not stable (any cos² ≤ 0.95) or not uniquely
   spanned in some tested direction.
2. **INDEPENDENT.** Every member has exactly one distinct counterpart with FE-to-FE MAC ≥ 0.9 in
   every tested direction. The group is then N individual observations.
3. **CONFIRMED.** Otherwise: one cluster observation with the assignment-invariant residual
   r_C = (1/N)·Σ ln(f_FE / f_EXP) and σ_C = √(Σσ_i²)/N.

It can be adopted in two stages.

| | A1: INDEPENDENT branch only for N > 2 | A2: full N-mode confirmation |
|---|---|---|
| N > 2 outcome | INDEPENDENT if (2) and the N-subspace check both hold; otherwise UNSUPPORTED, so REFUSED (§8.2 unchanged for this case) | UNSTABLE, INDEPENDENT or CONFIRMED (one N-mode cluster term) |
| Scientific validity | High. It uses exactly the identity evidence of the 2-mode rule; no new quantity is introduced. A group whose every member is individually stable carries no cluster ambiguity. | Sound in principle: principal angles generalise to N dimensions. But a CONFIRMED N-cluster turns N rows into one term (a large loss of information), and the 0.95 threshold has no SPEC basis for N > 2. |
| SPEC §12.4 | Compatible. §12.4 says closeness is "only a trigger" and is "not sufficient by itself". A1 applies the existing identity test and adds no new confirmation criterion. | Goes beyond the SPEC text, which defines **2-mode** confirmation. It needs a SPEC §19-style clarification and a DECISIONS entry. |
| Current decisions | Amends the scope of M4_DECISION_RECORD §8.2: "UNSUPPORTED" would mean "> 2-mode group that is not individually stable". §8.3 is unchanged. | Same as A1, plus N-mode cluster terms, which bring in the §8.3 split rule for N-mode clusters. |
| Effect on M4.7 | None structurally; the members stay individual fit or holdout rows. **Predicted** SP13 twin design (to be confirmed by a re-run, not assumed): 21 fit rows (R2–R22), holdouts R1 (torsion) and R23 (validation), 0 cluster terms. | `build_objective_design` must accept N-member clusters (it now refuses `len != 2`); `cluster_log_residual` and the σ_C formula are already general. |
| Effect on branch tracking (M4.5) | None; the rows are tracked individually at MAC ≥ 0.9, which the data clear by a wide margin. | `track_branches` must follow N-dimensional subspaces: `combinations(free, 2)` becomes `combinations(free, N)`, with a combinatorial cost and a uniqueness check. The data formats of `TrackedCluster` and the journal change. |
| Acceptance criteria | No new numbers: 0.9 (MAC) and 0.95 (cos², every angle) as now. Unchanged M4.9 criteria. | New: N-dimensional cos² threshold(s) and uniqueness for N > 2; to be fixed by the SUPERVISOR. |
| Code changes | `identification_clusters.confirm_cluster` only: generalise `_individual` / `_subspace` to N members (about 30 lines), keeping the 2-mode path byte-for-byte. Tests. No change to the objective, tracker or pipeline. | `identification_clusters`, `identification_objective`, `branch_tracker`, `synthetic_twin` design checks, tests, journal and record formats. |
| Regression risk | Low. 2-mode results must stay identical (existing M4.4 tests and the SP13 R1/R2 record). One fake-twin test needs new data: its `triple` group is individually stable, so it would become INDEPENDENT and a new unstable-triple variant must keep the REFUSED test. | Medium to high: the tracker and objective are shared by the accepted M4.5–M4.8 paths, and the cost of subspace search grows with N. |

**Cost of the subspace search.** An exhaustive N-subset search over 24 modes has
C(24,4) = 10 626 QR factorisations of a 89 262 × 4 matrix per direction. A1 can instead check
the subspace of the unique individual counterparts (already determined by step 2) plus a
uniqueness test. A2 needs the full search or a justified restriction, which would be a new
policy parameter.

### B) Deterministic subdivision of large groups into 2-mode clusters

- **Rule:** split a > 2-mode group by symmetry class (M4.3 parities): modes of different parity
  classes are treated as uncoupled. Same-class pairs go to the existing 2-mode confirmation, and
  single members become individual rows.
- **Scientific validity:** valid only under **exact** structural symmetry (mirror-symmetric
  geometry, material axes aligned with the edges). Then modes of different classes are exactly
  uncoupled and can cross without veering. SP13 supports this empirically (mirror coverage
  100 %, cross-class MAC 0.0000), but the parities come from the **PROVISIONAL** M4.3 classifier.
  - B would make that classifier decisive for the observation structure. Today it only selects
    holdouts.
  - B has no answer for same-class groups of more than two modes.
- **SPEC §12.4:** not covered. The SPEC defines confirmation by subspace stability, not by
  symmetry; a subdivision rule needs a SPEC clarification.
- **Effect on M4.7 and tracking:** none beyond the 2-mode machinery. For SP13:
  - FE 13–15 → three single rows;
  - FE 20–23 → the (20,21) pair, which the existing 2-mode test judges INDEPENDENT (MAC ≥ 0.9998),
    plus single rows 22 and 23.

  This gives the same result as A1.
- **Acceptance:** the classifier's parity threshold (0.80, provisional) and mirror coverage would
  become identification-critical. A misclassified parity gives a wrong subdivision with no
  subspace-level safeguard.
- **Code:** a subdivision step before `confirm_cluster` and a guard for same-class groups larger
  than two.
- **Regression risk:** medium (dependence on the classifier; a new failure mode on asymmetric
  specimens).
- **Recommendation:** not as the rule. It is useful as **corroborating evidence** (the parity
  classes explain the A1 result).

### C) Refuse all > 2-mode groups permanently

- **Scientific validity:** conservative and safe, but it treats frequency closeness alone as
  disqualifying. SPEC §12.4 says closeness is only a trigger and not sufficient by itself. C
  discards observations whose identity is demonstrably stable (MAC ≥ 0.9998).
- **SPEC / decisions:** consistent with the current implementation and §8.2, with no change.
- **Effect:** none on code, tracking or the objective. But the full-mode-set SP13 twin
  (decision §5.2: all modes 7–30, nothing hand-selected) can **never** reach an M4.7 design.
  The M4 gate is then unreachable for SP13 unless another decision changes the mode set or the
  specimen.
- **Regression risk:** none.
- **Recommendation:** not recommended as a permanent rule. It is the default until a decision is
  made.

---

## 3. Recommendation

1. **Adopt A1** by SUPERVISOR decision (amending the scope of §8.2) with a DECISIONS entry.
   - It extends the existing identity test to groups of more than two modes and allows only the
     INDEPENDENT outcome.
   - N-mode **confirmation** stays UNSUPPORTED, and therefore REFUSED.
   - No new thresholds; the 2-mode path is unchanged.
2. **Defer A2** until a real > 2-mode group is shown to be individually unstable but
   subspace-stable. If that case arises, it needs a SPEC clarification with N-mode thresholds.
3. **Use B only as corroborating evidence**, not as a rule.
4. **Keep C** (current behaviour) until the decision.

**Acceptance tests for A1 (proposed; none implemented):**
- **Synthetic 3- and 4-mode groups:**
  - all members stable → INDEPENDENT;
  - one member rotating inside the group → UNSUPPORTED (REFUSED);
  - a member leaking out of the subspace → UNSTABLE;
  - a member without a unique counterpart → UNSUPPORTED.
- **Regressions:**
  - all 2-mode M4.4 tests identical;
  - the SP13 R1/R2 cluster record identical;
  - the fake-twin REFUSED tests kept with an unstable-triple variant.
- **Real data (store-gated, no Abaqus):**
  - FE 13–15 and FE 20–23 → INDEPENDENT on the validated packs;
  - the M4.9 readiness re-run reuses the existing truth journal, so **0 Abaqus solves**, and
    reports the design.

---

## 4. Permanent location of the truth artifacts (proposal, §8.6)

| Artifact | Proposed permanent location | Note |
|---|---|---|
| Truth shape pack | `carbon-project-archive:fe_shapes/SP13_bb3e5d7d131bed4f.npz` (beside the validated SP13 packs) | File SHA `eeebae21…`, content `758add0c…`. A repository record `docs/auto_id/fe_shapes/SP13_bb3e5d7d131bed4f.shape-pack.json` with store `carbon-project-archive` and state `TWIN_TRUTH`, loadable by `load_shape_pack` (verified SHA, content, node set). |
| Truth provenance and run identities | `carbon-project-archive:m4_twin/SP13_truth_gate/`, with `ARCHIVE_MANIFEST.json` pinning each file by SHA-256 | Files: `journal.json` (truth run `926f2f21…`), `readiness_report.json`, `twin_provenance.json`, `truth_extraction_manifest.json`, solve logs (`solve.log`, `.sta`, `.msg`, `.dat`, `.prt`, `.com`). Same pattern as the pending `m4_smoke/` proposal (§7.4). Repository copies already exist in `docs/auto_id/twins/SP13_truth_gate/`. |
| Truth ODB (715 MB) and `.sim` | Stays in `D:\abaqus_m4_truth` until the M4.9 review | Then deleted under §8.6 unless archived by a later decision. |
| Regenerated p0 / ±5 % INPs (`D:\abaqus_m4_truth\twin\jobs`, 552 MB) | Not kept | Deterministic M3 renderings, regenerable. Delete after review. |

Nothing has been moved or deleted. Executing this proposal needs SUPERVISOR approval.
