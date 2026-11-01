# PRIORITY-9 — Physical readiness of PLATE-300x300x1mm 261027 for an identification with M11

Labels: RESEARCH_ONLY / NOT_A_MATERIAL_PROPERTY / NO_REGISTRATION_CREATED / NO_MAC_COMPUTED.

This is the dossier of what the project holds about the first real single plate. It joins the existing evidence and
research and checks their state. It does **not** contain:

- a new E1, E2 or G12;
- a registration, a mode pair or a MAC;
- a FIT / HOLDOUT set or a fit;
- an FE run (no Abaqus, Abaqus Python, ODB extraction, LM or Auto-ID was started).

The dossier was built by `services.plate_physical_review` from verified read-only copies of the sources. The program
builds the same dossier in Plate Study > C. Physical Readiness. The seven documents (and the owner request as JSON) are
in `m11_261027_dossier/`:

| File | Content |
|---|---|
| `physical_readiness.json` | the whole dossier (states, sources, evidence, questions, modal evidence, observability, reuse, plan) |
| `evidence_matrix.csv` | every fact of chains A and B and its supporting facts |
| `modal_observations.csv` | the 11 records and the 14 elastic FE modes with their statuses |
| `sensitivity_reuse.csv` | the archived sensitivities and whether each can be reused |
| `fe_applicability_plan.json` | the plan only (no run order) |
| `OWNER_EVIDENCE_REQUEST.md`, `owner_evidence_request.json` | the owner's questions; the answer fields are empty |
| `PHYSICAL_READINESS_REPORT.md` | the readable report |

## 1. Object and states

| Item | Value |
|---|---|
| Specimen | PLATE-300x300x1mm |
| Test run | NEXP29/PLATE300-1MM/S261027-ROTATED |
| Experimental modal set | Polymax_bravo, 11 fitted records, 289 points; EXP1 = 18.6307 Hz |
| FE model | Abaqus M11 `S4R_0875_BASELINE`, 14 elastic modes FE7–FE20; FE7 = 19.07217 Hz |
| EXP1 against FE7 | +2.37 %: FREQUENCY_ONLY_DIAGNOSTIC, not a confirmed pair |

**States:**

- sources: **SOURCES_VERIFIED**;
- registration: **PHYSICAL_REGISTRATION_NOT_VERIFIED**;
- mode pairs: **MODE_PAIRS_NOT_CONFIRMED**;
- identification: **NOT_READY_FOR_IDENTIFICATION**;
- review package: **READY_FOR_OWNER_REVIEW**.

READY_FOR_OWNER_REVIEW means only that the package for an owner decision is complete. It is not a scientific
acceptance, a registration or a permission to identify.

## 2. Sources verified by SHA-256

| Source | SHA-256 | State |
|---|---|---|
| `300by300_plate_only_1mm_ROTATED_Polytec_261027.unv` (copy) | `76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d` | VERIFIED |
| M11 `manifest.json` (copy of the R6 extraction) | `354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7` | VERIFIED |
| `CFRP_S4R_0875_FreeFree.inp` (copy; hashed only, never run) | `962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3` | VERIFIED |
| `300by300_plate_only_1mm_ROTATED_261027.svd` | — | NOT_AVAILABLE (not delivered) |

The archive the dossier cites was read only with its recorded SHA-256:

- the PRIORITY-1–4 files of `research_results_reader`;
- PRIORITY-2 `SOLVER_RUNS.csv`, `BRANCH_TRACKING.csv` and `RESULTS.md`;
- PRIORITY-1 `PLATE_FE_SENSITIVITY.csv` and `RESULTS.md`;
- PRIORITY-3 and PRIORITY-4 results;
- `PLATE_WORKBENCH_RC1.md`.

## 3. Facts: established and not established

**Chain A — scanner → physical plate:**

| Fact | Value | Provenance | State |
|---|---|---|---|
| `grid_plus_u_edge` | edge 1 | DERIVED from independent facts | established |
| `rotation_reference` | the 261016 position, turned 45° clockwise | DERIVED from independent facts | established |
| `scan_scale` | SI metres, distance 1.15 m | INSTRUMENT_RECORD | established |
| `measured_dof` | +Z of the scan frame | INSTRUMENT_RECORD | established |
| `scanned_face` | "unmarked" (the 261016 face) | DERIVED, rests on `scanned_face_261016` (CANDIDATE) | **open** |
| `grid_plus_v_edge` | 2 if unmarked, 4 if marked | DERIVED, rests on the same candidate | **open** |
| `scan_window_offsets_mm` | the 261016 offsets | DERIVED, rests on `window_offsets_261016` (CANDIDATE) | **open** |
| `scan_metric_geometry` | the 261016 positions | DERIVED, rests on `metric_reconstruction_261016` (CANDIDATE) | **open** |

**Chain B — physical plate → FE M11:**

| Fact | Value | Provenance | State |
|---|---|---|---|
| `fe_x_along_edges` | 1 / 3 (the 301 mm edges) | HUMAN_CONFIRMED | established |
| `fe_origin_corner` | — | CANDIDATE (A–D) | **open** |
| `fe_normal_face` | — | CANDIDATE | **open** |

**Supporting facts:**

- the owner's same points, same face and 45° turn: HUMAN_CONFIRMED;
- the two scan geometries: INSTRUMENT_RECORD;
- the point map id k ↔ id k: DERIVED, not instrument-verified.

**Kept apart from the facts:**

- "The same face as in 261016" is relative. It does not say which face is absolute.
- The 277.7 × 277.0 mm UNV grid is a representation, not the physical window.
- The 261016 window reconstruction is diagnostic, not a measured geometry.
- The candidates A–D are not physical facts.
- The M11 model has no physical landmark and no measured asymmetry. The measured edge means (0.816–0.926 mm) exist
  only in the specimen record.

## 4. Exactly what blocks the physical registration

The six open facts are `scanned_face`, `grid_plus_v_edge`, `scan_window_offsets_mm`, `scan_metric_geometry`,
`fe_origin_corner` and `fe_normal_face`. Each rests on a candidate or has no value.

Consequences:

- no FrozenRegistration exists;
- so no EXP↔FE MAC may be computed;
- so no mode pair and no FIT / HOLDOUT set exist.

## 5. The modal evidence

| Item | State |
|---|---|
| Experimental records | 11, unpaired |
| Elastic FE modes | 14 (FE3–FE6 rigid by the code's shape criterion; FE1–FE2 are not in the data read) |
| Pairs | none |
| MAC | NOT_COMPUTED |
| FIT / HOLDOUT | NOT_DECLARED |
| PRIORITY-1 research MAC | shown only as RESEARCH_MAC_NOT_ADMISSIBLE |

**Close FE groups (3 % trigger):** FE10/FE11, FE13/FE14, FE15/FE16 and FE17/FE18.

**History of the FE branches in PRIORITY-2:**

- FE8, FE9 and FE20 were lost in E1 +5 % and E2 −5 %;
- FE10↔FE11, FE13↔FE14 and FE17↔FE18 exchanged order;
- FE15 / FE16 were tracked only as one confirmed cluster term.

## 6. Observability

**1. In the FE model (FE-only).** From the PRIORITY-2 central ±5 % sensitivities over 10 tracked terms:

- E1 / E2 / G12: rank 3, condition 1.83;
- the restricted E (E1 = E2) / G12: rank 2, condition 2.35.

This holds for M11 free-free, h 0.875 mm, with the chosen modes only. It does not mean that the experiment determines
these parameters.

**2. With the experiment.** **NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS**. No physical uncertainty of E or G12 is
computed from an unconfirmed pair.

**S0 / H1 / H2** stay RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY:

| Scenario | E1 = E2 (MPa) | G12 (MPa) |
|---|---|---|
| S0 | 56 000 | 4 763.4 |
| H1 | 43 467 | 4 804.4 |
| H2 | 41 952.8 | 4 810.3 |

## 7. Audit of the archived sensitivities

| Existing result | Reuse status |
|---|---|
| PRIORITY-2 E1 ±5 %, E2 ±5 %, G12 ±5 % (6 solves; baseline INP `962f75f2…`) | REUSABLE for FE-only observability at the M11 free-free baseline only |
| s_E (E1 = E2) = s_E1 + s_E2 | CONDITIONAL |
| PRIORITY-1 secants (G12 ×2 / ×3, E1 / E2 −10 %) | NOT_REUSABLE as central derivatives |
| PRIORITY-4 real solves S0 / H1 / H2 | VERIFICATION_RECORD_ONLY (not sensitivities) |
| ±2.5 % linearity repeat | NOT_AVAILABLE (never run) |

**Branch tracking of the PRIORITY-2 solves:**

- E1 −5 %, E2 +5 % and G12 ±5 %: 14 of 14 branches tracked;
- E1 +5 % and E2 −5 %: 11 of 14 (FE8, FE9 and FE20 lost; three pairs exchanged).

**Why s_E is conditional.** It is a superposition of separate E1 and E2 perturbations, not a solved joint E1 = E2
perturbation. PRIORITY-4 agreed with the approximation to ≤ 0.32 % far from the baseline, which is not a ±5 % central
check.

**No transfer.** None of these sensitivities is carried to a model with the suspension, the force sensor or another
thickness without new solves. With another FE input the dossier marks them "not applicable".

## 8. Plan of future actions (each needs its own owner authorisation; none is given)

| Stage | New FE runs (after the reuse audit) | Prerequisite |
|---|---|---|
| 1. FE applicability | 4 (B two-band ×2, D sensor, E wedge) + 2 optional (C four-band, history only) | the answers D1–D4, or a research range declared before the run |
| 2. E / G sensitivities | M11 free-free kept: G12 0 (reuse) + E (E1 = E2) 2 (0 if the owner accepts the superposition); another adopted model: 4 | the adopted FE model |
| 3. Linearity (±2.5 %) | 4 | stage 2 |
| 4. Bounded fit | ≤ 12 | a frozen registration, confirmed pairs, FIT / HOLDOUT frozen first |
| 5. Final model check | 1 per final candidate | stage 4 |

The plan is a declaration, never a run order. No INP is written with invented suspension or sensor characteristics. No
value is fitted from 18.6307 Hz or 33.4491 Hz.

## 9. Answers that remain with the owner (OWNER_EVIDENCE_REQUEST.md)

**A. The face of the plate.**

- A1: which absolute face faced the Polytec in 261016 (with or without the marking)?
- A2: which document or confirmation establishes it?

**B. The physical scan geometry.**

- B1: which of these exists: the 261027 `.svd`, a PSV screenshot of 261016 with the points on the video frame, the
  scanner angles and the camera / scale, or other independent coordinates? If none, the two facts stay NOT_VERIFIED.

**C. The FE orientation.**

- C1: is there a measured landmark that ties FE (0, 0) to a corner?
- C2: if not, should an FE variant with a measured asymmetry be prepared? A named corner alone stays CONVENTION_ONLY.

**D. The applicability of the model.** None of these is derived from frequencies.

- D1: the attachment points of the two suspensions.
- D2: the length and characteristics of the bands and strings.
- D3: the place, mass and attachment of the force sensor.
- D4: the real thickness, including the interior.

## Not changed

- SPEC, DECISIONS, STATUS, ROADMAP and EVIDENCE.
- The frozen registrations and the historical results of PRIORITY-1–8.
- S0 / H1 / H2.
- M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and the scientific thresholds.
- Production Auto-ID stays BLOCKED.
