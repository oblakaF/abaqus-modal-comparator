# PLATE-ONLY-R1 — effective properties of one CFRP plate (research, non-normative)

**Status: REVIEW_READY (2026-10-30). Research only, non-normative.** This report changes no specification, decision,
status, evidence, registration, criterion or catalogue entry. It releases no material constant. No Abaqus, solver, LM,
FE computation or Auto-ID was run.

- **Scope (owner).** The sandwich panels are set aside. One specimen is studied: `PLATE-300x300x1mm`, series
  `NEXP29/PLATE300-1MM/S261027-ROTATED`.
- **Branch.** `research/plate-only-effective-properties`, made from the NEW-GUI.6-F1 state `20677f2`
  (`feature/new-gui6-scientific-workbench`).
- **Review folder (outside git).** `D:\git\abaqus-modal-comparator-work\PLATE_ONLY_R1_REVIEW`: reports 01–09, the two
  workbooks, the mode-shape images and `review_data.json`.

## 1. Data used

| Role | File | SHA-256 | Status |
|---|---|---|---|
| Working source | `…\SPname_files_ROTATED_261028\300by300_plate_only_1mm_ROTATED_Polytec_261027.unv`; Testlab dataset 55, set `Polymax_bravo` | `76db80ae…` | `NEW_WORKING_SOURCE`, PHYSICAL_REGISTRATION_NOT_VERIFIED |
| Auxiliary check | `…_ROTATED_261027.unv`, FRF dataset 58, 22 peak records | `d3bc99e9…` | PROVISIONAL — NOT A VALIDATED FITTED MODE |
| Lab notes | `Read me.txt`, `Experiment_Freq_damping_LMS_Rotated.xlsx` | (SOURCE_PROVENANCE.csv) | read only |
| History | M11 `300by300_plate_only_1mm_261016_POLYMAX.unv` (verified copy) | `117c893b…` | `M11_HISTORY_ONLY` |

- **Read-only.** Every original was only read; SHA-256, size and mtime are equal before and after.
- **No other specimen.** No sandwich, SP-02, SP-10 or SP-13 data enter the study.

## 2. Is it the M11 plate?

**NOT_ESTABLISHED.**

| What suggests it | What is missing |
|---|---|
| The file names; the owner's note that a changed suspension moved the first resonance from about 33 Hz to about 19 Hz (M11 §21) | A lab or owner statement of identity |
| Several higher fitted frequencies within about 1 % between the sessions; frequency proximity is not identity | Mass, plan and a thickness map of the tested plate |
| — | A photograph with a corner mark and the face shown |

The M11 measurements (mass 118.37 g, plan 301 × 300 mm, 20 edge thickness readings) belong to the M11 plate. They are
**not** attached to `PLATE-300x300x1mm`.

## 3. The experiment

**Records.** 11 fitted records, all kept, with record 1 first. Out-of-plane Z only, 289 points.

| Record | Hz (UNV) | MPC | Workbook damping ζ | Descriptive pattern (invariants; image) |
|---|---|---|---|---|
| 1 | 18.6307 | 0.918 | 0.00189 | twist: saddle 0.99, nodal lines along the plate's centre lines |
| 2 | 54.6193 | 0.987 | 0.00394 | bending with curvature in one direction (saddle 0.54, dome 0.43) |
| 3 | 63.4950 | 0.927 | 0.00159 | one-direction bending (0.39 / 0.32) |
| 4 | 66.8467 | 0.903 | 0.00923 | mixed (0.17 / 0.24) |
| 5–11 | 74.2149, 112.2655, 145.9357, 157.8508, 169.1849, 180.1363, 191.6019 | 0.956–0.997 | records 5–10 in the workbook; 11 not listed | higher order |

- **Scan grid.** 17 × 17, rotated 45.2° in the camera frame, so it is aligned with the rotated plate. Spacing 17.4 mm at
  the measured distance of 1.15 m.
- **Comparison with 261016.** That grid was at 89.4°, spacing 15.6 mm at 1.0 m; × 1.15 gives 17.9 mm. The two scans
  are similar after the distance correction. This is not identity.
- **Close groups.** None by the existing 3 % trigger.
- **FRF peaks.** The auxiliary file has a peak within 0.4 Hz of each fitted record. It also has low peaks at 3.4,
  10.3 and 12.5 Hz (probably the suspension), and 122.2 Hz, which has no fitted record.
- **Unknown.** The face shown, the plate edge along each scanner axis, the reference of the 45° turn and the
  excitation. The lab's 45° turn is **not** an FE rotation.

## 4. FE models of the plate (CANDIDATE_FE_REFERENCE)

All FE models are M11 models of the M11 plate; none is a confirmed model of this specimen.

| Member | Content | Files (SHA-256 verified) | Elastic modes, Hz |
|---|---|---|---|
| S4R baseline | E1 = E2 = 56 000, G12 = 5 000 MPa, h 0.875, ρ 1.498e-9; free-free | INP `962f75f2…` → ODB `7daeb7e3…` → extraction `354966da…` | 19.07, 59.87, 62.01, 71.85, 72.19, 116.58, 167.49, 168.61, 174.80, 179.90, 213.20, 213.95, 295.78, 327.90 |
| R6.6 G12 10 000 / 15 000 | one field changed | INP + extraction | first 26.58 / 32.18 |
| R6.7 E1 / E2 50 400 | one field changed | INP + extraction | — |
| S4R wedge, C3D8I, E30E26 | `.dat` frequencies only | INP + `.dat` | E30E26 (owner's manual fit to 261016): first 31.97 |

Limits:
- **Material.** One homogeneous orthotropic material on global axes: E1 / E2 are model directions, not fibre
  directions.
- **Boundary conditions.** Free-free, without the two-string suspension.
- **Mesh identity.** INP → ODB mesh identity is not proven (M11 §15.5).

## 5. Frequency comparison (FREQUENCY_ONLY; no pair)

The nearest FE frequency of the S4R baseline for each record:

| Record | Nearest FE mode | Difference |
|---|---|---|
| 1 | FE 7 | +2.4 % |
| 2 | FE 8 | +9.6 % |
| 3 | FE 9 | −2.3 % |
| 4 | FE 9 | −7.2 % |
| 5 | FE 11 | −2.7 % |
| 6 | FE 12 | +3.8 % |
| 7 | FE 13 | +14.8 % |
| 8 | FE 13 | +6.1 % |
| 9 | FE 14 | −0.3 % |
| 10 | FE 16 | −0.1 % |
| 11 | FE 16 | −6.1 % |

- **Registration.** `bind_registration_by_fe_geometry` refuses: the file is not an accepted source.
  PHYSICAL_REGISTRATION_NOT_VERIFIED.
- **No pairing or MAC.** No orientation is chosen by MAC or frequency, no MAC is computed, and the M11 R6.5 research
  MAC is not transferred.

**Which shapes could have physical FE counterparts?** Descriptively, record 1 (twist) and the FE twist mode 7 are the
same shape class. So are records 2 and 3 (one-direction bending) and FE 8 / 9, which are the same pair class. Without
a registration all of them stay **diagnostic candidates**: none is confirmed.

## 6. FE sensitivities (secants; FE-to-FE branch tracking)

Branches are tracked with `branch_tracker.track_branches` (MAC ≥ 0.90). Close pairs are examined with
`confirm_cluster`. s = Δ ln f / Δ ln p.

| Branch | s_E1 | s_E2 | s_G12 | Note |
|---|---|---|---|---|
| FE 7 (19.07) | 0.008 | 0.009 | **0.479** | twist: G12 (D66) only |
| FE 13 (167.49) | **0.499** | 0.001 | 0.000 | E1 (D11, FE X = 301 mm) only |
| FE 14 (168.61) | −0.001 | **0.500** | 0.000 | E2 (D22) only |
| FE 10 / FE 11 | 0.353 / 0.004 | 0.006 / 0.356 | 0.169 / 0.167 | independent pair |
| FE 12 | 0.135 | 0.144 | 0.245 | mixed |
| FE 15 + 16 | 0.223 | 0.226 | 0.065 | **confirmed cluster**: one term |
| FE 17 / FE 18 | 0.303 / 0.043 | 0.051 / 0.312 | 0.169 / 0.168 | independent pair |
| FE 8 / FE 9 | not tracked | not tracked | 0.000 | the shapes rotate when E1 ≠ E2; 3.6 % spacing is above the 3 % trigger, so each is followed alone and lost |

- **Exact D Jacobian.** The D-parameter sensitivities follow from the exact ∂ ln D / ∂ ln E of the homogeneous plate.
  Σ s_D ≈ 0.50–0.53 per term (secants; 0.5 for derivatives).
- **Not SPEC S4.** These are research secants (−10 % for E, × 2 for G12), not SPEC §6 S4 central ±5 %.

## 7. Identifiability (HYPOTHETICAL_PAIRING design study, M5)

Assumptions: Σ_setup 0.3 % PROVISIONAL; Σ_meas NOT_AVAILABLE.

| Case | Status | sd (ln) |
|---|---|---|
| all 9 tracked terms: D (D11 = D22) + D66 | FULL_RANK | 0.30 %, 0.54 % |
| all 9 terms: D11, D22, D66 (research; SPEC v1.1 §5.2 blocks E1 ≠ E2 without traceable axes) | FULL_RANK | 0.44 %, 0.44 %, 0.54 % |
| FE 7 only: D + D66 | **RANK_DEFICIENT** | — |
| FE 13 + FE 14 only: D11, D22, D66 | **RANK_DEFICIENT** | — |
| all terms + thickness h at measured mass | **RANK_DEFICIENT**: s_h = 3·Σ s_D, exactly collinear | — |

**Synthetic twin.** Log-linear SURROGATE from these secants, run through the existing LM, the evidence chain and the
verdicts (SYNTHETIC_GATE):

- D and D66 are recovered within 0.9 % (IDENTIFIED in the synthetic gate);
- with the registration NOT_AVAILABLE every verdict is NOT_IDENTIFIABLE;
- with FE 7 alone the system is RANK_DEFICIENT before any optimisation (SPEC §6 S5).

## 8. Can the parameters be estimated now, and to ±10 %?

**Now: no.** Every parameter is **NOT_IDENTIFIABLE**:

- there is no confirmed pair, because there is no registration;
- the plate identity is NOT_ESTABLISHED, and this plate has no own FE model;
- this plate has no thickness or mass record;
- family consistency is NOT_AVAILABLE for one plate, which blocks PRODUCTION verdicts (D-044).

A research estimate would be a RESEARCH_CANDIDATE_ONLY with its assumptions, never a material constant.

**±10 %.** The statistical part on D is small if pairs are confirmed (≈ 0.3–0.6 % in ln D). E_eff = 12(1 − ν12ν21)·D/h³,
so the thickness contributes 3·cv_h:

| Thickness cv | Contribution in E / G |
|---|---|
| 1 % | 3 % |
| 2 % | 6 % |
| 3.3 % | **10 %** |
| 5 % | 15 % |
| 8.2 % (the M11 edge readings of another plate, illustrative only) | 24 % |

- **D.** About ±10 % is plausible once pairs are confirmed and the model form holds.
- **E / G.** About ±10 % needs a measured thickness map with spatial cv ≲ 3 %, plus the suspension and model-form
  checks.
- **Frequency vs stiffness.** A 5 % frequency error is about 10 % in stiffness (f ∝ √D).

## 9. Program

**New GUI.** A **Plate Study** page:

- it runs only on the working source and a member of the plate's FE family, both recognised by the SHA-256 recorded at
  the read;
- it shows the records, the frequency-only table, the independent unpaired shapes, the registration result, the FE
  family, the sensitivities, the design studies, the outcomes, the missing data and the plan;
- Export plate report... writes JSON and Markdown into a folder the user chooses;
- the button **Run iterative estimation (not authorised)** is never enabled, and the service's `request_iteration`
  always refuses;
- no other specimen's material result is shown.

**Service.** `src/services/plate_study.py`.

**Tests.**
- `tests/test_plate_study.py` (19): the synthetic twin, rank refusal, the close-pair relabelling, thickness
  collinearity, registration, a single frequency, the first record, the M11 substitution, labels, the gate, and the
  real data when present.
- `tests/test_plate_study_qt.py` (6), including the page-width regression.

**Full suite.** 3029 OK, 98 skipped; `test_g2_eigfreq_precision` (16) NOT_RUN: it reads `-work` data.

**Windows smoke** (150 %, isolated LOCALAPPDATA, originals unchanged).
- **In-process (Qt `windows`): PASS.**
  - known source, Inspect, Run plate study in 7.0 s: NOT_READY_FOR_IDENTIFICATION, FREQUENCY_ONLY, 11 records,
    "NOT a mode pair" on every row, every outcome NOT_IDENTIFIABLE;
  - shapes drawn and the report exported;
  - no page scroll bar at 900 × 680 and 1366 × 768, logical and physical;
  - the M11 file is refused.
  - A badge that widened the page at 900 × 680 physical was found and fixed, with a regression test.
- **`RUN_NEW_GUI.cmd` with the native dialog and UI Automation: PASS.** Exit 0, no process left.
- **LEGACY_GUI start / close: PASS.**

## 10. Plan for the first authorised iterative campaign (not started)

1. **Specimen record.** Mass, plan, thickness map (9+ points), photographs with a corner mark, and a statement of
   identity with the M11 plate. Otherwise a separate FE model of this plate.
2. **Registration.** Independent evidence: face, edge per scanner axis, reference of the 45° turn, scan scale. Then
   the guided registration.
3. **Own FE model of the plate** (measured geometry, thickness and mass; free-free and, separately, the two-string
   suspension). Abaqus, HUMAN gate.
4. **Confirmed pairs.** The comparator with the registration (MAC ≥ 0.80 on measured DOFs, families, clusters); freeze
   FIT / HOLDOUT.
5. **SPEC §6 S4 sensitivities** for D (E1 = E2) and G12: 4 jobs plus a 4-job ±2.5 % repeat. E1 ≠ E2 only after
   traceable fibre axes. Abaqus, HUMAN gate.
6. **Optional Stage-A affine basis.** *MATRIX GENERATE, 4 jobs; balanced plate only. Abaqus, HUMAN gate.
7. **Campaign.** A declared campaign (question, τ_mf, Σ, bounds, solve budget) and the bounded LM with branch tracking.
   Separate HUMAN authorisation.

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, registrations, criteria, the 5 / 8 % limits, M8 / D-077, governed records and every
original file.
