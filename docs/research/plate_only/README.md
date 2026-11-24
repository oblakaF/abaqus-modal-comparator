# PLATE-ONLY-R1 — effective properties of one CFRP plate (research, non-normative)

**Status: REVIEW_READY (2026-10-30; F1 traceability and notation, see §11; PLATE-ONLY-R2 specimen identity, archived record, FE applicability and orientation, see §12; R2-F1 package identity, the two series and the thickness, see §13; PLATE-WORKBENCH-RC1 integration, registration readiness and the prepared FE campaign, with the owner's final correction of the test conditions, see §14; the owner's statement of the material family, 2026-11-24, see §15; the owner's confirmation of the scanned face and the four remaining registration facts, 2026-11-24, see §16; the research FE / EXP MAC of 261027 and its geometry sensitivity, 2026-11-24, see §17; the FE applicability check of the existing wedge-thickness model, 2026-11-25, with one owner-authorised ODB extraction and no solve, see §18). Research only, non-normative.** This report changes no specification, decision,
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

> **Superseded by PLATE-ONLY-R2 (§12.1):** the owner confirmed the identity on 2026-10-30 (HUMAN_CONFIRMED). The R1 assessment below is kept as history.

**R1: NOT_ESTABLISHED.**

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

## 4. FE models of the plate (CANDIDATE_FE_REFERENCE in R1)

> **PLATE-ONLY-R2 (§12.3):** the M11 plate is this specimen, so the S4R baseline is the **initial FE model** of the specimen (`INITIAL_FE_MODEL_OF_THE_SPECIMEN`). Its applicability to the 261027 test is checked apart and is `APPLICABILITY_NOT_VERIFIED`.

R1: all FE models are M11 models of the M11 plate; none is a confirmed model of this specimen.

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

Four kinds of numbers appear in this report and are never mixed:

| Kind | Meaning |
|---|---|
| Measured frequencies | The fitted records of the working source |
| FE frequencies | The **candidate** FE model of the M11 plate (CANDIDATE_FE_REFERENCE), not a model confirmed for this plate |
| Hypothetical distinguishability | A design study as if pairs were confirmed (§7) |
| Uncertainty of the effective properties | Unknown today (§8) |

For each **measured** record, the nearest frequency of the **candidate** S4R baseline:

| Record | Nearest candidate FE mode | Difference |
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

## 7. Hypothetical distinguishability (HYPOTHETICAL_PAIRING design study, M5)

This is **not** an accuracy of the real experiment. The study asks which parameters the candidate FE model's
sensitivities could separate **if** the listed terms were confirmed mode pairs. The sd values below are
**conditional**: they use the provisional Σ_setup 0.3 % (Σ_meas NOT_AVAILABLE) and assume pairs that do not exist.

| Case | Status | Conditional sd (ln), provisional Σ_setup |
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
- R1: the plate identity was NOT_ESTABLISHED; R2: HUMAN_CONFIRMED, and the M11 model is the initial model, its applicability to the 261027 test NOT_VERIFIED (§12.3);
- R1: no thickness or mass record; R2: the archived M11 record is attached, with the thickness only at the perimeter (§12.2);
- family consistency is NOT_AVAILABLE for one plate, which blocks PRODUCTION verdicts (D-044).

A research estimate would be a RESEARCH_CANDIDATE_ONLY with its assumptions, never a material constant.

**Real uncertainty: unknown.** The real uncertainty of the plate's effective properties is not known today:
- there is no registration and no confirmed pair;
- the thickness is known only at the perimeter (R2: archived record, §12.2);
- Σ_meas is NOT_AVAILABLE;
- the suspension and the model form are not assessed.

The conditional 0.30–0.54 % of §7 are **not** the expected accuracy of the real experiment.

**The ±10 % target is an engineering goal, not an achieved result.** What it would need follows from the plate model.
E_eff = 12(1 − ν12ν21)·D/h³, so the thickness alone contributes 3·cv_h:

| Thickness cv | Contribution in E / G |
|---|---|
| 1 % | 3 % |
| 2 % | 6 % |
| 3.3 % | **10 %** |
| 5 % | 15 % |
| 8.2 % (the 20 archived perimeter readings; R1: another plate, R2: this specimen) | 24 % |

- **D.** About ±10 % may become reachable once pairs are confirmed and the suspension and model form hold. This is
  not shown yet.
- **E / G.** About ±10 % would at least need a measured thickness map with spatial cv ≲ 3 %, plus the suspension and
  model-form checks.
- **Now.** Every material parameter of this plate stays NOT_IDENTIFIABLE.
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

## 11. PLATE-ONLY-R1-F1 — traceability of the inputs and notation (2026-10-30)

### Input checks

The page uses the NEW-GUI.6-F1 checks.

- **Before Run plate study.** `plate_study_model.confirm_inputs` identifies the FE manifest and the experimental file
  again. It uses `preview_model.file_identity`: a fresh SHA-256 and size, no re-import. Both are compared with the
  identities recorded by Inspect file. A missing or different identity refuses the study before any computation, with
  "changed since Inspect file read it … Inspect it again".
- **Before Export plate report.** `report_export.confirmed_sources` checks the identities the study used. A changed
  file refuses the export: nothing is written, and earlier reports stay byte-identical. A later content is never given
  the result of the content read earlier.
- **Inspect file again, even of the same paths.** It removes the previous result and its export status. Previews are
  compared by object, never by value; a new read is always a new preview.

### Notation

In the GUI, the exported report and this document, these are named apart:
- measured frequencies;
- the candidate FE model's frequencies;
- the hypothetical distinguishability and its conditional sd (provisional Σ_setup);
- the real, unknown uncertainty.

The ±10 % target is an engineering goal; every material parameter stays NOT_IDENTIFIABLE.

### Tests

New tests `tests/test_plate_study_qt.py::InputTraceabilityTests`:
- the UNV or the FE manifest changed after Inspect, before Run: refused, nothing computed, the source untouched;
- the UNV or the FE manifest changed after Run, before Export: refused, no new file, earlier reports byte-identical;
- Inspect again of the same paths resets the result and the export status, and the unchanged files pass;
- a new preview equal in value still resets;
- the conditional figures are never shown as the real accuracy.

Four of the five fail on `54f5b8f` (six failures with subtests). The re-Inspect test also passed before, because the
read resets the inputs while it runs.

**Full suite.** 3034 OK, 98 skipped; `test_g2_eigfreq_precision` (16) NOT_RUN.

### Windows smoke F1: PASS

Conditions: Qt platform `windows`, 150 %, isolated LOCALAPPDATA, **isolated copies** of the plate UNV and the FE
package. The originals were only copied; they are unchanged.

1. **The UNV copy changed after Inspect, before Run.** Refused (InputsChanged), nothing computed, no report.
2. **Inspect again, then Run plate study** (6.2 s):
   - NOT_READY_FOR_IDENTIFICATION, FREQUENCY_ONLY, 11 measured records;
   - the column "Conditional sd (ln), provisional Σ_setup" and the conditional note shown;
   - every outcome NOT_IDENTIFIABLE;
   - the export wrote JSON and Markdown.
3. **The FE manifest copy changed after Run, before Export.** "The report was not written (… changed since it was
   read …)"; the earlier reports are byte-identical.
4. **Inspect again of the same paths.** The result and its export status are gone.
5. **Close.** No task left.

## 12. PLATE-ONLY-R2 — the confirmed specimen, its archived record, the initial FE model and the orientation (2026-10-30)

Research only, non-normative. No SPEC, decision, status, evidence, frozen record, registration or criterion changed.
No Abaqus, FE computation, LM, Auto-ID or iterative calibration was run. Every material parameter stays
NOT_IDENTIFIABLE.

### 12.1 Specimen identity: HUMAN_CONFIRMED

| Item | Content |
|---|---|
| Statement | The physical plate of the experimental series 261016 (M11) and 261027 ROTATED is one and the same specimen |
| By, date | the owner, 2026-10-30 |
| Provenance | the owner's supplement to the PLATE-ONLY-R2 task. This is a HUMAN record, not governed evidence |
| Scope | physical identity of the specimen only. The 2026-10-18 retry FRF file of the delivery is not named in the statement and is not used |
| Not established by it | a mode pair or a mode correspondence between the sessions or with the FE model; the registration of either scan; the applicability of the M11 FE model to the 261027 test; that the plate was unchanged between the archived measurements and 27.10 |

The confirmation is final; no further confirmation of the identity is requested. The M11 file 261016 stays history
as an experimental source: it never replaces the 261027 working source.

In the service: `PLATE_IDENTITY = HUMAN_CONFIRMED`, `IDENTITY_RECORD`, `IDENTITY_EVIDENCE`. The R1 request for an
identity statement (`IDENTITY_NEEDED`) is removed.

### 12.2 The archived record of the specimen

The M11 measurements now belong to this specimen. They keep their date, method and uncertainty. They are **not**
measurements of 27.10.2026; the plate is taken as unchanged since then, which is not verified.

| Quantity | Value | Recorded | Method | Uncertainty |
|---|---|---|---|---|
| Mass | 118.37 g | by 2026-10-21 (owner's sheet, M11 §8; day not stated); before the 261027 session | scale; instrument not stated | not stated; record resolution 0.01 g |
| Plan | 301 × 300 mm (x × y; FE X = 301 mm) | as above | instrument not stated (M11 §13.6) | not stated; record resolution 1 mm |
| Thickness | 20 perimeter readings, 5 per edge, 0.71–0.94 mm; mean 0.876, spatial sd 0.071 mm (cv 8.2 %); edge means 1: 0.880, 2: 0.816, 3: 0.882, 4: 0.926 mm | as above | caliper of 0.01 mm resolution and an electronic caliper (M11 §8.1); about 4.5–6.5 mm from the edge; **the interior is not measured** | gauge uncertainty not stated; spatial scatter as given (D-052: not divided by √N). R2-F1: edge 2, reading 3 is 0.84 as transcribed or 0.81 (M11 §8), kept, not resolved (§13.3) |
| Areal mass | 1.3109 kg/m² | derived | mass / (x · y) | from the records above |

- **Edge labels.** Edges 1 top, 2 right, 3 bottom and 4 left are seen from the shaker side of the 261016 mounting
  (M11 §13.1).
- **Sheet photograph.** SHA-256 `df5339cd…`; the photograph is in the work directory only.

### 12.3 The initial FE model and its applicability to the 261027 test

The M11 S4R model (`S4R_0875_BASELINE`) is the **initial FE model of the same specimen**
(`INITIAL_FE_MODEL_OF_THE_SPECIMEN`). Its controlled variants and the other three models are models of the same
specimen too. The applicability check (`fe_applicability`) states `APPLICABILITY_NOT_VERIFIED`. A value is called
consistent only within the record's resolution; no new criterion is used.

| Aspect | State | FE model | Specimen / test |
|---|---|---|---|
| Plan | CONSISTENT_WITH_THE_RECORD | 301 × 300 | 301 × 300 mm |
| Mass | CONSISTENT_WITH_THE_RECORD | 118.36 g (ρ·h·A; ρ was set from this mass) | 118.37 g |
| Thickness | NOT_VERIFIED | uniform 0.875 mm | perimeter mean 0.876 mm, cv 8.2 %, edge means 0.816–0.926 mm; interior unknown |
| Material axes | NOT_VERIFIED | one orthotropic material on the global axes | fibre and weave directions not evidenced (SPEC v1.1 §5.2) |
| Suspension | NOT_VERIFIED | free-free | rubber bands and strings at two upper points along the nodal line of the first mode. The auxiliary FRF has peaks at 3.44, 10.31 and 12.5 Hz (PROVISIONAL, probably the suspension); the highest is 0.67 of record 1. SPEC §15 asks for a soft suspension; softness is not demonstrated |
| Excitation | UNKNOWN | none | not stated in the lab note. SPEC §15 needs the shaker attachment mass in the model, or non-contact excitation |
| Setup sensitivity | ~~SETUP_SENSITIVE~~ R2-F1: MODE_IDENTITY_NOT_VERIFIED and SETUP_DEPENDENCE_SUSPECTED (§13.2) | — | measured: record 1 at 33.45 Hz (261016) and 18.63 Hz (261027); the cause is not established |
| Registration | PHYSICAL_REGISTRATION_NOT_VERIFIED | FE X = 301 mm edge, +Z shell normal | §12.5 |
| Mode correspondence | NOT_ESTABLISHED | 19.07 Hz (first elastic FE mode) | 18.6307 Hz (record 1): +2.4 %. Proximity and a common shape class are **not** a mode pair |

**Consequence.** The model is the right starting point: its geometry and mass are the specimen's. It is not yet
shown to represent the 261027 test. That needs:
- the excitation of 261027;
- an FE variant with the two-point suspension, and the attachment if a shaker was used. This is an Abaqus job and
  needs a separate HUMAN gate.

### 12.4 Shapes of the two sessions of the same plate (descriptive)

`grid_saddle_split` (new, descriptive) splits the saddle fraction about each scan's **own grid**:
- uv has its nodal lines along the grid axes;
- u² − v² has them along the grid diagonals.

It relates a shape to its measurement grid only. It does not relate it to the plate edges or the FE axes, chooses no
orientation and pairs nothing. The grid lies at 45.2° in the 261027 camera frame and at 89.4° in the 261016 frame.

| Session | Record | Hz | MPC | Saddle uv | Saddle u² − v² | Dome |
|---|---|---|---|---|---|---|
| 261027 | 1 | 18.6307 | 0.918 | **0.988** | 0.000 | 0.000 |
| 261027 | 2 | 54.6193 | 0.987 | 0.000 | 0.541 | 0.427 |
| 261027 | 3 | 63.4950 | 0.927 | 0.000 | 0.388 | 0.318 |
| 261027 | 4 | 66.8467 | 0.903 | 0.000 | 0.172 | 0.240 |
| 261016 | 1 | 33.4491 | 0.848 | **0.947** | 0.002 | 0.000 |
| 261016 | 2 | 55.2538 | 0.876 | 0.011 | 0.804 | 0.155 |
| 261016 | 3 | 68.1022 | 0.921 | 0.000 | 0.185 | 0.764 |

The higher records of both sessions have almost no quadratic content: these fractions say nothing about them.

**Observations.** These are descriptions, not pairs.

1. **Record 1 in both sessions is a twist about the scan-grid axes.** On the same specimen it lies at 33.45 Hz with
   four corner straps and an attached shaker stinger (261016, M11 §13.3), and at 18.63 Hz with the two-point
   suspension (261027), a ratio of 0.56. *(R2 concluded "strongly setup-sensitive"; R2-F1 withdraws this: the same
   mode is not verified and the cause is not established; a setup dependence is only suspected, §13.2.)*
   - This is not a Σ_setup repeat (D-053): the protocol, suspension and grid differ.
   - It does not show that 261027 is free-free.
2. **Records 2–3 mix the same two quadratic patterns** (saddle on the grid diagonals, and dome) in different
   proportions in the two sessions.
   - 261027 records 2 and 3 are near one-direction bending (u² − v² ≈ dome).
   - 261016 records 2 and 3 are near the saddle and the dome.
   - This is the behaviour of the near-degenerate bending pair FE 8 / 9 (§6), whose shapes rotate with small changes.
     Such records can enter an estimate only as one confirmed cluster term, never as two single rows.
3. **Item 5 of R2.** The proximity of 18.6307 Hz and 19.07 Hz, and the common twist class, confirm no mode pair. No
   registration and no MAC exist.

### 12.5 Physical orientation: the chain scanner → plate → FE

| Link | State | Known | Open |
|---|---|---|---|
| scanner (261027 ROTATED) → plate | PHYSICAL_REGISTRATION_NOT_VERIFIED | grid 17 × 17 at about 45° in the camera frame; the lab turned the plate 45° clockwise as viewed from the Polytec; distance 1.15 m; the Polytec node numbering changes with the rotation | the reference of the 45° turn; the face towards the Polytec; which numbered edge lies along each grid side; the scan-to-edge offsets (the delivery has no camera frame of the plate session) |
| plate → FE (M11 model, same specimen) | PENDING (owner's choice A–D) | FE X = 301 mm, Y = 300 mm; edges 1–4, their thickness rows and the marked face (M11 §13.1); candidates A–D (M11 §14.2) | which of A–D (M11 §14.5), hence FE +Z against a physical face. Because the specimen is the same, this link is shared with M11 |
| scanner (261016) → plate | HISTORY_ONLY | diagnostic reconstruction W301xH300 with three deviations not accepted (M11 §13.4) | not transferable: another session, grid and node numbering |

- **No choice is made.** No orientation is chosen by MAC, frequency or shape.
- **Candidates.** The two open links leave 8 maps of the 261027 scan axes into the FE axes (4 in-plane turns × 2
  faces).
- **Why the registration still matters for a balanced D.** The edge means of the same plate differ: 0.816 mm on
  edge 2 and 0.926 mm on edge 4, about 13 %. With D ∝ h³ the plate is not physically symmetric. The near-degenerate
  bending pair, and any later E1 ≠ E2, therefore depend on the registration.

### 12.6 Preparation of the effective stiffnesses

| Route | Needs | Status now |
|---|---|---|
| **D11 = D22 (balanced D), D66** | Frequencies of confirmed pairs and the areal mass, f² ∝ D / (ρh). No thickness | The areal mass is known (1.3109 kg/m², archived) and equals the initial model's (1.3108 kg/m²). Still missing: registration, confirmed pairs, the suspension check |
| **E1, E2, G12 (equivalent homogeneous)** | D and h³: E = 12(1 − ν12ν21)·D / h³ (D-052) | `effective_moduli_from_d` is prepared and exact; it is applied to no value. With the 20 perimeter readings 3·cv = 24 % in ln E / ln G12 (R2-F1: illustrative only, not the real uncertainty, which is UNKNOWN; §13.3). The ±10 % goal for E / G cannot be judged on edge readings alone; a thickness map of the whole plate is needed |

- **The initial model's constants.** E 56 000, G12 5 000 MPa and h 0.875 mm give D11 = D22 = 3 134 N·mm and
  D66 = 279.1 N·mm (`plate_d`). These are the **starting point** of a future authorised iteration, not measurements
  or estimates.
- **The uncertainty budget** (`specimen_budget`):
  - thickness 24.5 % (perimeter scatter, interior unknown); R2-F1: illustrative only, the established value is UNKNOWN
    (§13.3);
  - mass: the scale uncertainty is not stated and is not invented;
  - the statistical part, the setup and the model form are NOT_AVAILABLE until confirmed pairs exist.
- **Unchanged from R1.** The conditional design-study figures of §7 are unchanged and stay conditional. The real
  uncertainty of the effective properties is still **unknown**.
- **Readiness** (`plate_readiness`): NOT_READY_FOR_IDENTIFICATION.
  - The identity line is gone, and the archived record is present.
  - A new line states APPLICABILITY_NOT_VERIFIED.
  - Every outcome is NOT_IDENTIFIABLE. E / G name the perimeter-only thickness as the first reason.

**Data still open** (none of it concerns the identity):
1. For 261027: the face towards the Polytec and which numbered edge is at the top, for example a photograph of the
   mounted plate from the Polytec side. Alternatively, confirmation that the 45° turn started from the 261016
   mounting without turning the plate over.
2. The owner's choice of picture A–D (M11 §14.5).
3. The 261027 excitation: a shaker (point, stinger) or non-contact.
4. The suspension points and band lengths, for an FE suspension variant.
5. For E / G only: an interior thickness map.
6. The scan-to-edge offsets: a camera frame of the plate session.

### 12.7 Program, tests and checks

**Service** (`src/services/plate_study.py`):
- `IDENTITY_RECORD`, `SPECIMEN_RECORD`, `thickness_statistics`, `areal_mass_kg_m2`;
- `fe_applicability`, `ORIENTATION_CHAIN` / `ORIENTATION_NOTES`, `grid_saddle_split` (also in each experimental
  record);
- `specimen_budget`, `effective_moduli_from_d`, `plate_d`;
- the updated `plate_readiness`, `FE_LIMITS` and `ITERATION_PLAN`.
- `request_iteration` still always refuses.

**New GUI, Plate Study page.** It shows:
- the identity, with its provenance and limits;
- the archived record, with its date and the note "NOT new measurements of 27.10.2026";
- the applicability table, with the state next to the aspect;
- the orientation chain and its notes;
- the uncertainty budget;
- two descriptive grid columns in the experimental table.

The labels read "initial FE model" instead of "candidate". The exported JSON (`plate-only-r2/study/v1`) and the
Markdown carry the same sections.

**Tests.** 39 in the two plate files; in R1-F1 there were 30.
- `tests/test_plate_study.py::SpecimenR2Tests` (7):
  - identity and provenance; nothing asks for the identity again;
  - archived record with its date, method and uncertainty, never 27.10;
  - FE applicability apart;
  - 18.63 / 19.07 Hz never a pair;
  - D needs the areal mass only and E / G the thickness;
  - the grid split;
  - open orientation.
- `RealPlateTests`: record 1 of both sessions and the FE plan and mass on the real data.
- `tests/test_plate_study_qt.py`: the page, the export and the visible State columns.

The R1 assertion of identity NOT_ESTABLISHED is replaced by HUMAN_CONFIRMED, and the M11 file is still refused.

**Full suite.** 3043 OK, 98 skipped; `test_g2_eigfreq_precision` (16) NOT_RUN: it reads `-work` data. The nine new tests fail on `45e0f7c`.

**Windows smoke R2: PASS.** Conditions: Qt `windows`, 150 % (DPI 96 × DPR 1.5), isolated LOCALAPPDATA, isolated
copies of the plate UNV, the M11 UNV and the FE package. The originals are unchanged.

1. **Run plate study** (7.0 s):
   - NOT_READY_FOR_IDENTIFICATION, FREQUENCY_ONLY, every frequency row "NOT a mode pair";
   - identity HUMAN_CONFIRMED;
   - archived record "by 2026-10-21", with the note "NOT new measurements of 27.10.2026";
   - applicability: plan and mass consistent; thickness, axes and suspension NOT_VERIFIED; excitation UNKNOWN;
     mode correspondence NOT_ESTABLISHED (+2.4 %);
   - orientation open;
   - every outcome NOT_IDENTIFIABLE; the gate is disabled.
2. **Export.** JSON and Markdown with the R2 sections.
3. **Window sizes.** No page scroll bar at 1366 × 768 or 900 × 680.
   - Found and fixed in the smoke: the State and Value columns were pushed out of view by long texts. They now come
     right after the first column, and the long texts are elided with a tooltip. A regression test was added.
4. **M11 file as the experiment.** Refused.
5. **Close.** No task left.

## 13. PLATE-ONLY-R2-F1 — package identity, the two series and the thickness (2026-10-30)

Research only, non-normative. No SPEC, decision, status, evidence, frozen record, registration or criterion changed.
No Abaqus, solver, FE computation, LM or Auto-ID was run. No sandwich data were used. Every material parameter stays
NOT_IDENTIFIABLE. Where §12 said otherwise, this section replaces it; §12 is kept as the R2 record.

### 13.1 The identity of the whole extracted FE package

**R1 / NEW-GUI.6-F1 hashed only `manifest.json`.** A changed geometry or mode CSV was not detected.

**New service: `src/services/fe_package_identity.py`.** It uses the actual format read by
`abaqus_bridge.load_extracted_odb`:
- `manifest.json`;
- its `geometry_file` (format 2 and later);
- the `modes[].file` of every entry the loader keeps. An entry the loader refuses (contradicting frequency records)
  is not read and is not a dependency; the loader's own selection functions are used. For the plate baseline this is
  19 files: the geometry and 18 modes. Modes 1–2 are refused by the loader.

**How it works:**
- The manifest is hashed and parsed from the same bytes.
- Every dependency is hashed with a streaming SHA-256 (`fresh_content_identity`: chunked, cancellable; a file that
  changes while it is hashed is refused). No mode shape is imported again.
- **Refusals.** A missing file, an unreadable file, a cancellation and an invalid dependency path are refused
  separately. An invalid path is an absolute path, a drive, `..` or a path that resolves outside the package folder.
- **ODB.** The ODB named in the manifest is never read. The identity states `odb_sha256: null` and the declared ODB
  path; a package hash is never presented as the ODB's, and an `.odb` gets no package identity.

**Where it is checked:**

| Step | Check |
|---|---|
| Inspect file (`preview_model.run_read`, FE) | The package's files are listed (size, mtime) before the read and hashed after it. If any file changed during the read, or the package cannot be identified, no identity is recorded. The manifest's path, size and SHA-256 stay at the top level; the whole package is under `"package"` |
| Verified comparison (`comparison_model.check_sources`) | The package is confirmed file by file before the comparator runs |
| Report export (`report_export.confirmed_sources`; verified and diagnostic reports) | The same, before anything is written. The report's `identity_basis` now names the package's files and says that it is not the ODB's hash |
| Plate Study, before Run and before Export | The same, in `confirm_inputs` and `export_report` |

A refusal names the file, for example "mode 7 (mode_0007.csv) changed", "geometry (geometry.csv) changed",
"manifest.json changed" or "… cannot be identified now".

**Test fixtures.** The NEW-GUI.5 / 6 world tests used the world's `.odb` file as the FE "manifest"; the plate tests
used text files. Since an ODB's hash must not stand for a package, both now read a small real extracted package
(`write_fe_package`). What the tests check is unchanged.

### 13.2 The two experimental series

The measured values and the descriptive twist indicators are kept: record 1 is at 18.6307 Hz in 261027 and at
33.4491 Hz in 261016; the uv fractions are 0.988 and 0.947. The R2 state `SETUP_SENSITIVE` (§12.3, §12.4) is
withdrawn, together with "the setup changed … by a factor 0.56" and "strongly setup-sensitive".

| Aspect | State | Meaning |
|---|---|---|
| series difference: mode identity | `MODE_IDENTITY_NOT_VERIFIED` | Whether the two records are the same mode is not verified: no registration and no MAC between the series. No cross-series mode pair |
| series difference: cause | `SETUP_DEPENDENCE_SUSPECTED` | The cause of the difference is not established. A dependence on the test setup (suspension, shaker attachment) is suspected, not proven. Not a Σ_setup repeat (D-053) |

The report states them together as `SETUP_DEPENDENCE_SUSPECTED / MODE_IDENTITY_NOT_VERIFIED`.

### 13.3 Thickness and its uncertainty

- **The 20 archived edge readings are kept** unchanged (M11 §8; by 2026-10-21).
- **The ambiguous reading.** Edge 2, reading 3 is 0.84 mm as transcribed and could be read 0.81 mm (M11 §8). The
  owner read it as 0.84 (M11 §8.1); that is a reading of the same sheet, not an independent re-measurement. The
  record keeps the transcription, shows both readings and does not choose a new value. The sheet and the
  transcription are not changed.

| Item | Value | Status |
|---|---|---|
| Observed edge scatter | mean 0.8760 / 0.8745 mm; sd 0.0714 / 0.0725 mm; CV_edges 8.2 % / 8.3 % (as transcribed / with 0.81) | OBSERVED (edges only) |
| 3 × CV_edges | 24.5 % / 24.9 % in ln E / ln G12 | ILLUSTRATIVE: not the real uncertainty |
| Thickness map of the whole plate | not measured; the interior is unknown | NOT_MEASURED |
| Real uncertainty of E / G | unknown | UNKNOWN |
| ±10 % target | an engineering goal | NOT_ACHIEVED |

- **The budget** (`specimen_budget`) no longer gives the thickness an established contribution. Its value is "—",
  and 24.5 % appears only in a separate "Illustrative" column. The R2 lines "3·cv = 24 %" and "thickness 24.5 %"
  (§12.6) are read as this illustration.
- **±10 % for E / G** cannot be judged on the edge readings alone. It stays an engineering goal, not an achieved
  result.

### 13.4 Program, tests and checks

**Changed files:**
- **Service:** `src/services/fe_package_identity.py` (new) and `src/services/plate_study.py` (the series states,
  `THICKNESS_READING_AMBIGUITY`, `thickness_variants`, `thickness_rows`, the illustrative budget column).
- **New GUI:** `preview_model`, `comparison_model`, `report_export`, `plate_study_model`, `plate_study_panel`. The
  Plate Study page gains a "Thickness" table, two series rows in the applicability table, an "Illustrative" budget
  column and a series section in the exported report.

**New tests:**
- `tests/test_fe_package_identity.py` (13):
  - an unchanged package is confirmed;
  - one mode CSV changed, the geometry CSV changed, a file deleted, and another manifest with the same CSV files are
    each refused;
  - fewer modes read is refused;
  - a mode the loader refuses is not a dependency;
  - invalid paths are refused, and a cancellation is a cancellation;
  - the ODB is never read and gets no package identity;
  - Inspect file records the package, and records nothing when a CSV changes during the read.
- `tests/test_new_gui6_workbench.py`: a changed mode CSV refuses the verified comparison, and both CSV and manifest
  changes refuse the export.
- `tests/test_plate_study.py`: the ambiguous reading, the illustrative figure, the series as a suspicion.
- `tests/test_plate_study_qt.py`: Run and Export are refused after a mode CSV or geometry CSV change; the page and the
  report show the series states, the thickness table and the illustrative budget.

On `636b73e` the Plate Study Run and Export pass with a changed mode or geometry CSV (the defect reproduced); the
other new tests fail because their functions do not exist there.

**Tests.**
- Targeted (FE package identity, NEW-GUI.1 / 2 / 4 / 5 / 6, Plate Study): 228 OK, 1 skipped.
- **Full suite:** 3061 OK, 98 skipped. `test_g2_eigfreq_precision` (16) is NOT_RUN: it reads `-work` data.

**Windows smoke R2-F1: PASS.** Conditions: Qt `windows`, 150 % (DPI 96 × DPR 1.5), isolated LOCALAPPDATA, isolated
copies of the plate UNV and the FE package. The originals are unchanged.

1. **Unchanged package.** Inspect recorded 19 package files and `odb_sha256: null`. The study ran in 6.5 s:
   - NOT_READY_FOR_IDENTIFICATION;
   - the series rows MODE_IDENTITY_NOT_VERIFIED and SETUP_DEPENDENCE_SUSPECTED;
   - the thickness table;
   - the budget "— / 24.5 % (illustrative)";
   - no "SETUP_SENSITIVE" anywhere; every outcome NOT_IDENTIFIABLE.

   The export was written; the report carries the series section and the thickness section.
2. **A mode CSV changed after the study** (same size, one digit). The export was refused: "mode 9 (mode_0009.csv)
   changed". The earlier reports are byte-identical.
3. **Inspect again.** The changed CSV is read with a new package identity under the same manifest, and the earlier
   result is removed.
4. **The CSV changed again after Inspect.** Run plate study is refused before any computation.
5. **The restored package.** Its identity equals the first one; the study passes.
6. **Close.** No task left.

## 14. PLATE-WORKBENCH-RC1 (2026-10-30)

See [`PLATE_WORKBENCH_RC1.md`](PLATE_WORKBENCH_RC1.md). In short:
- **Integration.** NEW-GUI.6 and the Plate Study are integrated on `integration/plate-workbench-rc1`, made from
  `origin/main`.
- **Instrument records found.** The physical-registration audit of 261027 found:
  - SI scale, measured distance 1.15 m;
  - +Z DOF towards the Polytec;
  - a force reference channel;
  - the plate `.svd`, named by the PSV export but not delivered.
- **Verdict.** `PHYSICAL_REGISTRATION_NOT_VERIFIED`. Seven independent facts are missing, and no FrozenRegistration
  was created.
- **New services:**
  - `plate_registration_readiness` (evidence with provenance, no orientation from numbers, no MAC without a frozen
    registration);
  - `plate_workbench` (the chain, the ±10 % parts, the prepared FE campaign and its budget, the spectra chart).
- **Template.** `plate_campaign_template_rc1.json` is the campaign template; nothing was run.
- **Final correction (owner, 2026-10-30; RC1 §9).**
  - Test conditions: 261016 had four rubber bands, 261027 two, and the plate was turned 45°. The plate, the measured
    points and the measured face are the same. 261027 is the primary experiment for M11; 261016 is history only.
  - The earlier picture of the setup as identical was wrong; only the interpretation is corrected.
  - The two scans keep every point id under a −44.17° (clockwise) grid turn: `POINT_TO_POINT_MAPPING_DERIVED`.
  - The UNV grid is a representation, not the physical window.
  - Six registration facts stay open, each resting on a 261016 candidate or on A–D. The verdict is unchanged:
    `PHYSICAL_REGISTRATION_NOT_VERIFIED`.
  - FE applicability variants A–E are prepared; 0 Abaqus solves were run.

## 15. PLATE-0875-OWNER-MATERIAL-CONFIRMATION-01 — the owner's statement of the material family (2026-11-24)

Documentation only. No file was read again, and no provenance audit was repeated. No Abaqus, solver, FE computation,
LM or Auto-ID was run. No material constant is released; every material parameter stays NOT_IDENTIFIABLE.

| Item | Content | Kind |
|---|---|---|
| Statement | The existing 0.875 mm CFRP plate is old T300, from the same material family and supplier as the sandwich face sheets | OWNER_REPORTED |
| By, date | the owner, 2026-11-24 |  |
| Provenance | the owner's statement in the PLATE-0875-OWNER-MATERIAL-CONFIRMATION-01 task. A HUMAN record, not governed evidence; no laboratory, supplier or manufacturing record accompanies it |  |
| Exact batch | not recorded | NOT_VERIFIED |
| Layup: number of plies, stacking sequence, orientation | not recorded | NOT_VERIFIED |
| Manufacturing process | not recorded | NOT_VERIFIED |

- **"0.875 mm".** This is the FE model thickness, set to the perimeter mean of the archived readings (§12.2, §13.3).
  The interior thickness is not measured.
- **Not established by the statement.** Equal laminate properties of the plate and the SP-02 / SP-13 face sheets;
  any material constant; a transfer of a plate result to a sandwich. Equivalence is not inferred from thickness,
  mass, frequency similarity or MAC.
- **Earlier audits.** PLATE-0875-LOCAL-PROVENANCE-01 and PLATE-0875-ARCHIVED-MANUFACTURING-EVIDENCE-01 (read-only)
  found no record of the plate's stock, batch, ply count, layup or process. They are closed and are not repeated.
- **Scope of §1.** The study still uses no sandwich data.
- **Next.** The physical registration and the experimental readiness of the existing plate: the open items of §12.6
  and §14 ([roadmap](../../auto_id/ROADMAP.md), owner priority).

## 16. PLATE-0875-PHYSICAL-REGISTRATION-02 — the scanned face and the four remaining registration facts (2026-11-24)

Research only, non-normative. No Abaqus, solver, FE computation, LM, Auto-ID or MAC was run. No orientation was chosen
by MAC, frequency or shape. No FrozenRegistration was created, and none of the pictures A–D is selected. The verdict
stays `PHYSICAL_REGISTRATION_NOT_VERIFIED`. Every original was only read; size and mtime are equal before and after.

### 16.1 The owner's confirmation of the scanned face

| Item | Content |
|---|---|
| Statement | The laser scanned the face without handwritten markings. The handwritten markings were on the rear face, opposite the laser |
| By, date | the owner, 2026-11-24 |
| Kind | OWNER_REPORTED physical evidence (variant U of the PLATE-0875-PHYSICAL-REGISTRATION-01 review image). A HUMAN record, not governed evidence |
| Agrees with | the 261016 camera frame: the plate occludes the shaker body, and no numeral is visible (M11 §15.3). These supported the statement; they did not establish it |
| The two bright dots | near the lower-left corner of the 261016 frame. They are no longer needed for the scanned face. Their physical nature is unknown |

Consequences for 261027, through the owner's "same face, same points, 45° turn" of 2026-10-30 (§14):

| Fact | Value | Provenance | State |
|---|---|---|---|
| `scanned_face` | unmarked | OWNER_REPORTED (2026-11-24) for 261016; carried to 261027 by the owner's "same face" (2026-10-30) | **established** |
| `grid_plus_u_edge` | edge 1 | DERIVED: 261016 grid +u is up in the camera frame; edge 1 is at the top (owner, M11 §13.1); the ids keep it | established (unchanged) |
| `grid_plus_v_edge` | edge 2 | DERIVED: 261016 grid +v points to the scanner's left; with the unmarked face towards the scanner that side is edge 2 | **established** |
| `rotation_reference` | the 261016 position, turned 45° clockwise as viewed from the Polytec | DERIVED: the owner's 45°, the laboratory note and the id-preserving grid turn | established (unchanged) |
| `scan_scale`, `measured_dof` | SI metres, distance 1.15 m; +Z of the scan frame | INSTRUMENT_RECORD | established (unchanged) |
| `fe_x_along_edges` | edges 1 / 3 (301 mm) | HUMAN_CONFIRMED (M11 §13.1) | established (unchanged) |

### 16.2 Checks made on the existing records

Script and results: `research\PLATE_0875_PHYSICAL_REGISTRATION_01\reg02_checks.py`, `reg02_checks.json` (work
directory, outside git).

| Check | Result |
|---|---|
| Source identities | 261027 UNV `76db80ae…` and 261016 UNV `6d66eafe…` equal the recorded hashes; the 261016 `.svd` `0a770b1b…` equals M11 §17.2; the camera frame used here (`e2c42802…`, extracted from that `.svd`) is pixel-identical to the M11 frame `plate_frame_raw.png` |
| Point map 261016 → 261027 | 289 of 289 ids common. An id-preserving similarity without a mirror fits with a turn of −44.19° (documented: −44.17°), scale 1.1186 and residual rms 0.68 mm, max 1.78 mm. A mirrored map does not fit (it collapses to scale 0.002). The turn is clockwise as viewed from the scanner. The scale is a ratio of two UNV representations, not a physical calibration |
| Handedness of the scan frame | In the 261016 camera frame UNV +x maps to image right and +y to image up; the points lie at z = −1.0 m, so +Z points from the plate to the scanner. The frame is right-handed as the camera sees it. With +u up and +v to the scanner's left, u × v = +Z |
| Edge numbering | Seen from the scanner with the unmarked face in front: edge 1 top, edge 3 bottom, edge 2 left (thin, mean 0.816 mm), edge 4 right (0.926 mm). This is the mirror of the owner's shaker-side sketch (M11 §14.1) |
| Plate edges in the 261016 frame, second method | Median positions of the strongest profile step in 25 strips per edge: left 352.5, right 1243.5, top 66.5, bottom 960.5 px (recorded reconstruction: 352, 1244, 67, 960). With the recorded scan-point pixels and the v range of deviation 1, the gaps are 57.3 / 29.1 / 8.5 / 7.3 mm (left / right / top / bottom) against the recorded 56.4 / 29.2 / 7.8 / 7.0 mm: differences ≤ 0.9 mm, inside the 1–3 mm of M11 §15.4. **Same image, another detector: not an independent source** |

### 16.3 The four remaining facts

| Fact | What exists | Kind | State | What would close it |
|---|---|---|---|---|
| `scan_window_offsets_mm` | 261016: gaps to edge 2 / 4 / 1 / 3 = 56.4 / 29.19 / 7.78 / 7.02 mm (+v / −v / +u / −u). The assignment of each gap to a numbered edge now follows from §16.1. The values are the M11 diagnostic reconstruction: deviation 1 is confirmed by the scanner angles; deviations 2 and 3 rest on the image only (M11 §15.4); uncertain at 1–3 mm | DIAGNOSTIC (values); DERIVED (edge assignment) | **open** | the 261027 `.svd` (its own frame and alignment), or a PSV screenshot of the points over the video; or a SUPERVISOR decision to accept the 261016 reconstruction with its stated uncertainty. A decision is not evidence |
| `scan_metric_geometry` | 261016: grid shape and scale confirmed by the scanner-angle record (aspect 0.7747 against 0.7553; rms 1.32 mm; M11 §15.4), window about 215.4 × 285.2 mm. 261027: no instrument record of the physical positions; the owner's "same points" carries the 261016 positions; the 261027 UNV grid (277.7 × 277.0 mm) is a representation | INSTRUMENT_RECORD for the 261016 shape; OWNER_REPORTED carry-over to 261027 | **open** | the same as above |
| `fe_origin_corner` | none. The M11 model has no physical landmark; its origin is an artefact of the sketch (M11 §15.1); the owner does not know where the Abaqus axes lie (M11 §15) | not a physical fact | **open — CONVENTION required** | a declared placement recorded as `CONVENTION_ONLY`; or an FE variant that carries a measured asymmetry (the edge thicknesses 1–4), whose construction fixes the correspondence |
| `fe_normal_face` | none; it follows from the placement: +Z leaves the marked face in A / B and the unmarked face in C / D (M11 §15.2) | not a physical fact | **open — CONVENTION required** | the same placement decision |

**Coordinate convention against physical evidence.**

- With the unmarked face towards the scanner, the experimental axes of the 261016 scan (x right, y up, z to the
  scanner) in FE are −X +Y −Z (A), +X −Y −Z (B), −X −Y +Z (C) and +X +Y +Z (D). All four have determinant +1.
- Nothing physical tells them apart: no photograph, scanner record or model file ties FE (0, 0) to a corner. Naming
  one of them is a convention. It is not established by being named, and it is not selected here.
- For the homogeneous, uniform M11 model the four are related by the model's own symmetries (M11 §15.1, §15.2), so a
  comparison with this model does not depend on the choice. This is a property of the model, not evidence for a
  placement.
- A placement acquires a physical meaning only in a model that carries a measured asymmetry. Such a model must be
  built in the declared convention.

### 16.4 Exact remaining blockers

1. **Scan window and metric geometry of 261027** (`scan_window_offsets_mm`, `scan_metric_geometry`): no instrument
   record of 261027 is available. Needed: the file `300by300_plate_only_1mm_ROTATED_261027.svd` named by the PSV
   export, or a PSV screenshot; otherwise a SUPERVISOR decision on the 261016 reconstruction (deviations 2 and 3).
2. **FE placement** (`fe_origin_corner`, `fe_normal_face`): a SUPERVISOR convention, recorded as `CONVENTION_ONLY`.
   Proposal only: D, where the FE axes equal the 261016 scan axes (X to edge 4, Y to edge 1, +Z to the scanner).
3. Unchanged and outside this task: the physical-readiness items D1–D4 (suspension, force sensor, interior
   thickness) and the setup repeat.

The diagram with the two questions is `PLATE_0875_registration_remaining_decisions.png` in the same work directory.
It is not published: it is a decision aid, not evidence.

## 17. PLATE-0875-RESEARCH-MAC-01 — research FE / EXP MAC of 261027 and its geometry sensitivity (2026-11-24)

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** It is an offline
diagnostic comparison authorised by the owner. It is not a physical registration, not a governed comparison and not a
mode pairing. No FrozenRegistration was created. No Abaqus, FE solve, LM, parameter fit or Auto-ID was run, and no
material constant is released. The registration guard of the program (`mac_permitted` is False without a frozen
registration) is unchanged and was not bypassed: the computation uses the separate research path of M11 R6.5
(`research/m11_r65/cmac_research.py`). M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production Auto-ID
BLOCKED are unchanged.

**Owner decisions used (2026-11-24).** Scanned face: unmarked. FE placement: picture D, `CONVENTION_ONLY` (X towards
edge 4, Y towards edge 1, Z towards the scanner). Nominal research mapping: the existing 261016 geometric
reconstruction. The comparison does not wait for the 261027 `.svd`, and that file was not searched for again. A
convention and a decision are not physical evidence; the verdict stays `PHYSICAL_REGISTRATION_NOT_VERIFIED`.

### 17.1 Inputs and mapping

| Input | Content | SHA-256 |
|---|---|---|
| Experiment 261027 | `…ROTATED_Polytec_261027.unv`, set `Polymax_bravo`: 11 fitted records, 289 points, U3 only, complex as stored. Record 1 (18.6307 Hz) kept | `76db80ae…` = recorded |
| FE | `S4R_0875_BASELINE` extracted package (R6): `geometry.csv`, `manifest.json`, modes 7–20 (all 14 elastic modes of the package; FE 7 is the first elastic mode; rigid modes 1–6 excluded); `CFRP_S4R_0875_FreeFree.inp` for the connectivity | all 17 files = `research/m11_r65/expected_inputs.json` |
| Nominal geometry | `plate_reconstruction_W301xH300.json` (261016, diagnostic) | `09be8b88…` = recorded |
| Geometry alternatives | `…_ALT_BOTTOM.json` `1c3b2075…` = recorded; 261016 `.svd` copy `0a770b1b…` and POLYMAX UNV `117c893b…` = recorded; `plate_reconstruction_W300xH301.json` `1dfe211f…`, `plate_scan_px.json` `bd80b5b7…` and `reg02_checks.json` `0bb26277…` (derived files; hashes first recorded here) | as stated |

- **Session 261016** enters as geometry only. None of its modes or frequencies is used.
- **Point map.** id k ↔ id k, 289 of 289 (DERIVED, §14, §16.2). The experimental records are ordered by the
  reconstruction's point ids; a missing, extra or duplicate id is refused.
- **Positions.** The 261016 reconstructed positions of the same points on the 301 × 300 mm plate (window about
  215.4 × 285.2 mm; gaps 56.4 / 29.2 / 7.0 / 7.8 mm to the left / right / bottom / top edge in the scanner view).
- **Placement D.** Scan +x → FE +X, +y → +Y, +z → +Z.
- **Metric.** Complex MAC |eᴴf|² / ((eᴴe)(fᴴf)) over the 289 measured U3 values, bilinear S4R interpolation of the
  FE U3 field (primary) and nearest node (check). No phase is optimised per cell.

### 17.2 Verification

| Check | Result |
|---|---|
| Input identities | every input lies in a declared copy root (no original store is read) and equals its recorded SHA-256; three derived files had no earlier record (above) |
| Originals and copies unchanged | size, mtime and SHA-256 of all 25 inputs equal before and after |
| Handedness | scan frame right-handed (x right, y up, +Z to the scanner); the affine map scan → panel has determinant +0.98 (no mirror); D has determinant +1; the S4R node order gives +Z for all 10 000 elements |
| Session link | id-preserving similarity 261016 → 261027: turn −44.19°, rms 0.68 mm, max 1.78 mm; a mirrored map does not fit (rms 121 mm) |
| FE package | 10 201 nodes, flat, plan 301 × 300 mm; the INP nodes reproduce the extraction to 1.5e-05 mm; modes real; in-plane / U3 ≤ 1.7e-11 |
| Mapping coverage | 289 of 289 points inside the mesh in all 64 geometries (the bilinear transfer refuses a point outside; no extrapolation). Smallest distance to a plate edge 1.01 mm (ALT_BOTTOM_EDGE); 2.41 mm in the declared range |
| Interpolation validity | a linear field is reproduced on the real mesh at the real points to 1.6e-15; local coordinates within [−1, 1]; nearest node at most 2.11 mm away (3 mm mesh); bilinear against nearest-node MAC differ by at most 0.004 |
| MAC implementation | identical shapes 1.0; orthogonal synthetic shapes 1.5e-34; scale, sign and global complex factor change the value by at most 3.3e-16 |
| A–D on the homogeneous model | maximum difference against D 7.8e-08 (single-precision FE data), as in M11 §17.6. This is a property of the model, not evidence for D |
| Reproducibility | two complete runs give byte-identical `results.json` and CSV files; an in-process repeat differs by at most 2.8e-16 |
| Against the archive | the nominal matrix equals the PRIORITY-1 research matrix (`real_modal_matching_202610/RESULTS.md`, printed to two decimals) within 0.005 |
| Real part against complex | real-normalised experimental shapes change a cell by at most 0.019 (MPC 0.90–1.00) |
| Tests | `research/m11_r65`: 29 OK. `tests.test_plate_registration_readiness`, `tests.test_plate_rc1_owner_clarification`, `tests.test_plate_study`: 60 OK |

The scenarios, alternatives, levels and labels were fixed in the script before its first run (protocol SHA-256
`725223cc…`, local execution log). This is **not an independent preregistration**: the nominal matrix was already known
from PRIORITY-1.

### 17.3 Nominal research MAC, 11 × 14

Bold marks the row maximum. It is descriptive, not a pairing.

| EXP (Hz, MPC) | FE 7 | FE 8 | FE 9 | FE 10 | FE 11 | FE 12 | FE 13 | FE 14 | FE 15 | FE 16 | FE 17 | FE 18 | FE 19 | FE 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FE Hz | 19.1 | 59.9 | 62.0 | 71.8 | 72.2 | 116.6 | 167.5 | 168.6 | 174.8 | 179.9 | 213.2 | 213.9 | 295.8 | 327.9 |
| 1 (18.63, 0.92) | **0.91** | 0.00 | 0.01 | 0.15 | 0.00 | 0.00 | 0.00 | 0.00 | 0.34 | 0.21 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 (54.62, 0.99) | 0.00 | 0.57 | **0.60** | 0.00 | 0.00 | 0.30 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 |
| 3 (63.50, 0.93) | 0.00 | 0.19 | 0.09 | 0.00 | 0.26 | 0.02 | 0.13 | 0.00 | 0.00 | 0.00 | 0.11 | 0.00 | 0.00 | **0.31** |
| 4 (66.85, 0.90) | 0.00 | 0.08 | 0.09 | 0.00 | **0.55** | 0.07 | 0.07 | 0.00 | 0.00 | 0.00 | 0.24 | 0.00 | 0.00 | 0.20 |
| 5 (74.21, 0.99) | 0.00 | 0.00 | 0.00 | **0.48** | 0.00 | 0.00 | 0.00 | 0.00 | 0.14 | 0.09 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 (112.27, 1.00) | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 | **0.52** | 0.00 | 0.00 | 0.00 | 0.00 | 0.20 | 0.00 | 0.00 | 0.00 |
| 7 (145.94, 0.98) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.79** | 0.02 | 0.03 | 0.00 | 0.31 | 0.13 | 0.00 |
| 8 (157.85, 0.96) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.17 | 0.36 | **0.43** | 0.00 | 0.00 | 0.38 | 0.00 |
| 9 (169.18, 0.99) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.26** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.18 |
| 10 (180.14, 0.99) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.15** | 0.13 | 0.00 | 0.01 | 0.00 | 0.00 |
| 11 (191.60, 0.98) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | 0.00 | **0.54** | 0.15 | 0.00 |

The heatmap is `fig_mac_nominal.png` in the work directory (§17.8). FE frequencies are metadata of the template
constants (E 56 000, G12 5 000 MPa); they are not fitted.

### 17.4 Candidate correspondences (not verified mode pairs)

- **Signed error** is (f_FE − f_EXP) / f_EXP.
- **[min–max]** is the range over the 59 declared scenarios of §17.5 (max − min; not a confidence interval).
- **Two-mode subspace** is the share of the record in the span of the named FE pair; **all 14** is its share in the
  span of FE 7–20 at the 289 points (a random shape gives about 14 / 289 = 0.05). Both are descriptive.
- **Labels** use the existing levels 0.80, 0.50, the 15 % frequency window and the 3 % spacing trigger, descriptively
  only. `CANDIDATE_ONLY`: MAC ≥ 0.80 inside the window, not ambiguous. `AMBIGUOUS_CLUSTER`: MAC ≥ 0.50 with a member of
  a close FE group, or two FE modes ≥ 0.50, or a two-mode subspace ≥ 0.80. `WEAK_CANDIDATE`: 0.50–0.80 with one FE
  mode. `NO_CANDIDATE`: below 0.50. No label is a pairing status.

| EXP | Hz | First-ranked FE (Hz) | Signed error | MAC [min–max] | Second FE: MAC [min–max] | Two-mode subspace [min–max] | All 14 [min–max] | First rank unchanged | Label (unchanged in) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 18.6307 | FE 7 (19.07) | +2.37 % | 0.91 [0.88–0.93] | FE 15: 0.34 [0.30–0.37] | FE 15 / 16: 0.48 [0.42–0.52] | 0.97 [0.97–0.98] | 59 / 59 | CANDIDATE_ONLY (59 / 59) |
| 2 | 54.6193 | FE 9 (62.01) | +13.53 % | 0.60 [0.59–0.61] | FE 8: 0.57 [0.55–0.58] | FE 8 / 9: 0.97 [0.96–0.98] | 1.00 [0.99–1.00] | 59 / 59 | AMBIGUOUS_CLUSTER (59 / 59) |
| 3 | 63.4950 | FE 20 (327.90) | +416 %: outside the window | 0.31 [0.26–0.35] | FE 11: 0.26 [0.25–0.26]; it is the best inside the window (+13.69 %) | FE 8 / 9: 0.35 [0.33–0.36] | 0.84 [0.83–0.86] | 59 / 59 | NO_CANDIDATE (59 / 59) |
| 4 | 66.8467 | FE 11 (72.19) | +7.99 % | 0.55 [0.54–0.56] | FE 17: 0.24 [0.21–0.27] | FE 10 / 11: 0.55 [0.54–0.56] | 0.92 [0.91–0.92] | 59 / 59 | AMBIGUOUS_CLUSTER (59 / 59) |
| 5 | 74.2149 | FE 10 (71.85) | −3.19 % | 0.48 [0.45–0.51] | FE 15: 0.14 [0.09–0.19] | FE 10 / 11: 0.48 [0.46–0.51] | 0.68 [0.64–0.72] | 59 / 59 | NO_CANDIDATE (42 / 59; else AMBIGUOUS_CLUSTER) |
| 6 | 112.2655 | FE 12 (116.58) | +3.84 % | 0.52 [0.49–0.55] | FE 17: 0.20 [0.13–0.28] | FE 17 / 18: 0.20 [0.14–0.29] | 1.00 [0.99–1.00] | 59 / 59 | WEAK_CANDIDATE (43 / 59; else NO_CANDIDATE) |
| 7 | 145.9357 | FE 14 (168.61) | +15.54 %: outside the window | 0.79 [0.77–0.79] | FE 18: 0.31 [0.29–0.33] | FE 13 / 14: 0.79 [0.77–0.79] | 0.99 [0.99–0.99] | 59 / 59 | AMBIGUOUS_CLUSTER (59 / 59) |
| 8 | 157.8508 | FE 16 (179.90) | +13.97 % | 0.43 [0.41–0.44] | FE 19: 0.38 [0.33–0.41] | FE 15 / 16: 0.92 [0.88–0.94] | 0.98 [0.97–0.98] | 58 / 59 (else FE 19) | AMBIGUOUS_CLUSTER (59 / 59) |
| 9 | 169.1849 | FE 13 (167.49) | −1.00 % | 0.26 [0.24–0.27] | FE 20: 0.18 [0.11–0.27] | FE 13 / 14: 0.26 [0.24–0.28] | 0.48 [0.42–0.55] | 48 / 59 (else FE 20) | NO_CANDIDATE (59 / 59) |
| 10 | 180.1363 | FE 15 (174.80) | −2.96 % | 0.15 [0.14–0.16] | FE 16: 0.13 [0.12–0.14] | FE 15 / 16: 0.25 [0.23–0.26] | 0.67 [0.58–0.77] | 59 / 59 | NO_CANDIDATE (59 / 59) |
| 11 | 191.6019 | FE 18 (213.95) | +11.66 % | 0.54 [0.51–0.56] | FE 19: 0.15 [0.08–0.22] | FE 17 / 18: 0.55 [0.52–0.56] | 0.99 [0.99–0.99] | 59 / 59 | AMBIGUOUS_CLUSTER (59 / 59) |

**Ambiguous and closely spaced modes.**

- **Close FE groups (3 % trigger):** FE 10 / 11, 13 / 14, 15 / 16 and 17 / 18. FE 8 / 9 are 3.5 % apart and behave as
  a near-degenerate pair (M11 §17.7, §6). In a balanced, uniform model the two shapes of such a pair are fixed only by
  the model's exact symmetry; a small asymmetry of the real plate mixes or exchanges them.
- **Experimental records:** none within 3 %; the closest are records 3 and 4 (5.3 %). The experimental AutoMAC has no
  off-diagonal value above 0.04.
- **FE AutoMAC on the 289 measured points:** largest off-diagonal value 0.45 (below 0.50). The scan window
  distinguishes all 14 FE shapes; the incomplete, off-centre window is not what limits the comparison.
- **No FE mode is first-ranked for two records.**
- **Record 1 ↔ FE 7** is the only `CANDIDATE_ONLY` row: the twist shape, +2.37 %. It is a candidate, not a pair.
- **Record 2** lies in the FE 8 / 9 pair (0.97) but in neither shape alone (0.57, 0.60). **Record 8** lies in FE 15 / 16
  (0.92; single 0.43). These can only ever be cluster terms.
- **Record 7** resembles FE 14 alone (0.79; FE 13 0.00), stays below 0.80 in every scenario, and is +15.5 % off.
  Which of FE 13 / 14 carries this shape depends on E1 against E2 (they exchange, PRIORITY-1 §3).
- **Records 3, 5, 9 and 10** have no FE shape above 0.50. Records 5, 9 and 10 lie only 0.68, 0.48 and 0.67 in the
  span of all 14 FE shapes.

### 17.5 Geometry sensitivity

These are deterministic diagnostic scenarios. **They are not a validated uncertainty bound for 261027**, whose own
scan window has no instrument record (§16.4). No scenario or alternative is selected, and none is preferred because
its MAC is higher.

- **Declared range (59 scenarios, as in M11 R6.4 / R6.5):** X and Y shifts of 0, ±1, ±2 and ±3 mm in every
  combination, and ±0.874° about the grid centroid alone and with ±3 mm corner shifts.
- **Separate documented alternatives (not merged into the range):**
  - `ALT_BOTTOM_EDGE`: the competing bottom-edge image feature (M11 §17.5);
  - `PLAN_W300xH301`: the M11 reconstruction with the plan sides exchanged; it contradicts the owner's X = 301 mm;
  - `SCANNER_ANGLE_SHAPE`: the grid shape from the scanner angles, similarity-fitted to the nominal points
    (M11 §15.4; reproduced: rms 1.32 mm, max 2.34 mm);
  - `EDGES_SECOND_METHOD`: the axis-parallel plate edges of §16.2.
- **Control (in no range):** `UNV_REPRESENTATION_CONTROL`, the near-square 261016 UNV grid fitted to the nominal
  points. M11 §15.4 documents it as **not** a physical calibration (rms 15.04 mm, max 24.73 mm; reproduced).

| Geometry | Point shift, rms / max | Points mapped | Max abs ΔMAC, any cell | Max abs ΔMAC, first-ranked cells | First rank changes |
|---|---|---|---|---|---|
| Shifts within ±1 mm (9) | ≤ 1.41 mm | 289 / 289 | 0.026 | 0.015 | none |
| Shifts within ±3 mm (49) | ≤ 4.24 mm | 289 / 289 | 0.082 | 0.046 | record 9 |
| ±0.874° alone and with ±3 mm (10) | ≤ 6.96 mm | 289 / 289 | 0.083 | 0.049 | records 8, 9 |
| All 59 declared | ≤ 6.96 mm | 289 / 289 | 0.083 | 0.049 | records 8 (1 scenario), 9 (11 scenarios) |
| ALT_BOTTOM_EDGE | 3.25 / 6.01 mm | 289 / 289 | 0.035 | 0.021 | none |
| PLAN_W300xH301 | 0.82 / 1.33 mm | 289 / 289 | 0.016 | 0.010 | none |
| SCANNER_ANGLE_SHAPE | 1.32 / 2.34 mm | 289 / 289 | 0.037 | 0.027 | none |
| EDGES_SECOND_METHOD | 0.69 / 0.92 mm | 289 / 289 | 0.010 | 0.005 | none |
| UNV_REPRESENTATION_CONTROL | 15.04 / 24.73 mm | 289 / 289 | 0.335 | 0.306 | records 2, 3, 8 |

- **Nominal, minimum and maximum** of every first-ranked cell are in §17.4; the full minimum and maximum matrices are
  in `results.json`. Over the declared range and the four alternatives together the first-ranked values span:
  record 1 0.88–0.93, record 2 0.59–0.62, record 7 0.77–0.79.
- **Largest ranges** are in weak off-candidate cells: record 9–FE 20 0.11–0.27, record 6–FE 17 0.13–0.28,
  record 11–FE 19 0.08–0.22.
- **Stability.** The first-ranked FE mode is the same in all 59 scenarios and all four alternatives for 9 of 11
  records. It changes for record 8 (FE 16 / FE 19, both ≤ 0.44) and record 9 (FE 13 / FE 20, both ≤ 0.27). The label
  changes only for records 5 and 6, whose values (0.48 and 0.52) lie on the 0.50 level.
- **The control** changes the first-ranked cells by up to 0.31 in both directions: six go up (records 1, 5, 6, 9, 10,
  11: 0.92, 0.74, 0.69, 0.57, 0.41, 0.62) and five go down (records 2, 3, 4, 7, 8: 0.42, 0.11, 0.52, 0.59, 0.30). A
  higher MAC is not evidence for a geometry, and the control is not adopted. It shows only the size of the effect of
  a centimetre-level error.

### 17.6 Is the geometry a significant limitation?

**Within millimetres: no. At the centimetre level: yes; and which of the two holds for 261027 is not verified.**

- **Geometry.** A shift of ±1 mm moves a first-ranked value by at most 0.015, and ±3 mm with ±0.874° by at most
  0.049. The four documented alternatives move it by at most 0.027. No such change brings a second record to 0.80,
  takes record 1 below 0.80, or changes a first-ranked mode above 0.45. The descriptive picture of §17.4 therefore
  does not depend on the 1–3 mm uncertainty of the 261016 reconstruction.
- **What this rests on.** The 261027 positions are the 261016 ones only through the owner's "same points" and the
  DERIVED id map. The 261016 grid shape is confirmed by the scanner angles; its offsets to the edges rest on one
  image. If the true 261027 positions differed by centimetres, the comparison would change materially (the control).
  Only the 261027 instrument record can exclude that. The scenarios do not.
- **FE applicability (separate, and larger).** With the nominal mapping and in every scenario, only record 1 reaches
  0.80. The other shortfalls (0.2–0.85 from unity) are 4 to 17 times the geometric range. They have the signature of
  the model, not of the mapping:
  - records 2, 4, 6, 7, 8 and 11 lie 0.92–1.00 in the span of the FE shapes but 0.43–0.79 in one shape: the measured
    shapes are **mixtures** of FE shapes, mostly inside the near-degenerate pairs;
  - the first-ranked frequencies are off by −3 % to +16 %, with no common sign or factor;
  - the model is uniform (0.875 mm), balanced (E1 = E2) and free-free. The plate's edge thickness varies by 13 %, its
    material axes are not evidenced, and the two-band suspension and the force sensor are not modelled (§12.3).
- **Experimental limits (separate).** Records 5, 9 and 10 are only partly inside the FE basis (0.48–0.68). Whether
  that is measurement noise, a local or suspension effect, or content the model lacks is not established.

### 17.7 Remaining blockers for the effective-stiffness research

1. **One candidate only.** Record 1 ↔ FE 7 is a twist shape: it informs D66 (G12; sensitivity 0.48) and almost not
   D11 / D22 (0.02; PRIORITY-1 §5–§6). With it alone the estimation problem has rank 1. No candidate informs the
   bending stiffness.
2. **Bending records are mixtures in near-degenerate FE pairs.** They can enter only as confirmed cluster terms, and
   only with an FE model whose pairs are split physically: the measured edge-thickness asymmetry, E1 ≠ E2 with
   traceable axes, the two-band suspension and the force sensor (the prepared applicability jobs of §14; Abaqus,
   separate HUMAN gate).
3. **Physical registration not verified.** The 261027 scan window and metric geometry have no instrument record
   (§16.4); the FE placement is a convention. Without a frozen registration there is no admissible MAC and no pair.
   This section changes none of that.
4. **Thickness.** The interior is not measured, so E and G cannot be separated from D (§13.3).
5. **Unchanged governance.** SPEC §6 S4 central sensitivities, the setup repeat, D-044 (one plate), M8 GATE NOT_MET
   and D-077 `NO_GLOBAL_PARAMETER_VALUE`.

### 17.8 Files (work directory, outside git)

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_RESEARCH_MAC_01`:

- `run_research_mac.py`, `protocol.json`, `execution_log.txt`;
- `results.json` (`f8e2d80d…`): all matrices, checks and tables; `all_matrices.npz`: the 64 matrices;
- `mac_nominal.csv`, `candidates.csv`, `geometry_sensitivity.csv`;
- `report.py`, `fig_mac_nominal.png`, `fig_geometry_sensitivity.png`.

Nothing is published in the repository except this section.

## 18. PLATE-0875-FE-APPLICABILITY-01 — does the existing wedge-thickness model explain part of the shape discrepancy? (2026-11-25)

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** The wedge is a
**model-form sensitivity scenario**, not a measured interior thickness field. Nothing here is a mode pairing, a
confirmed cluster, a physical registration or a parameter estimate. No material constant was changed, fitted or
released. No FrozenRegistration was created; the program's registration guard is unchanged and was not bypassed (the
research path of §17 is reused). M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production Auto-ID BLOCKED are
unchanged.

**Abaqus use (owner authorisation: at most one solve and one extraction).**

| Action | Count | Detail |
|---|---|---|
| Abaqus solves | **0** | The archived `CFRP_S4R_WEDGE_FreeFree.odb` of 2026-10-20 exists and is complete, so the authorised solve was not used. It is not carried over to another task |
| ODB extractions | **1** | Abaqus Python, pinned extractor `abaqus_scripts/extract_odb.py` (`039aa067…`, the one of R6 / R6.6 / R6.7), modes 1–20, on a verified work copy of the ODB; 2026-11-24 23:56:49, 5.3 s, exit 0; no retry |

**Short answer.** The wedge explains a **part** of the shape discrepancy, and only in one group of modes
(164–180 Hz, records 7 and 8). It does not explain the frequency errors and does not help the low bending records.
Its effect has **opposite sign for the two orientations** of the wedge on the plate, so it cannot be used before the
placement of the FE model on the plate is physical. Thickness asymmetry **warrants further investigation** (§18.6).

### 18.1 Inputs and identities

| Input | Content | SHA-256 |
|---|---|---|
| Wedge model | `CFRP_S4R_WEDGE_FreeFree.inp`, `.dat` | `dcb639f1…`, `d545876a…` = `plate_study.PLATE_FE_FAMILY` |
| Wedge result | `.odb`, `.sta`, `.msg` of the archived run | `6f26bd19…`, `c41de675…`, `11b4ac74…` = `M11_SINGLE_CFRP_PLATE.json` |
| Work copy of the ODB | the only file opened by Abaqus Python | `6f26bd19…`; the source copy and the work copy are unchanged after the extraction |
| Baseline | the R6 package and INP of §17.1; `CFRP_S4R_0875_FreeFree.dat` `f4405925…` | = recorded |
| Experiment and mapping | 261027 UNV `76db80ae…`; nominal geometry `09be8b88…` | = recorded (§17.1) |
| Previous results | `PLATE_0875_RESEARCH_MAC_01\results.json` `f8e2d80d…` | = §17.8 |

No original store was read. Every input lies in a declared copy root; size, mtime and SHA-256 of all 28 inputs are
equal before and after.

### 18.2 The wedge model against the baseline

| Item | Baseline `S4R_0875_BASELINE` | Wedge `S4R_WEDGE` | Verdict |
|---|---|---|---|
| Mesh | 10 201 nodes, 10 000 S4R, plan 301 × 300 mm | the same labels, connectivity and coordinates (difference 0) | identical |
| Material | ρ 1.498e-9 t/mm³; E1 = E2 = 56 000, G12 5 000 MPa, ν12 0.05 | the same line, character for character | **unchanged** |
| Step | Lanczos, 20 modes, mass normalisation, field output U | the same | identical |
| Boundary conditions | none (no `*Boundary`, spring, mass, constraint or load keyword) | none | free-free in both |
| Section | `*Shell Section`, 0.875 mm, 5 points | `*Shell Section, nodal thickness`, 5 points | the only difference: one keyword, `*Nodal Thickness` |
| Thickness | uniform 0.875 mm | exactly linear in X (deviation from a plane 6e-9 mm, no Y term): **0.93 mm at X = 0 to 0.81 mm at X = 301**; area mean 0.870 mm | as documented (M11 §2) |
| Mass | 118.361 g (`.dat`; ρ·h·A from the INP: 118.361 g) | 117.684 g (`.dat`; integrated from the INP: 117.684 g) | wedge −0.57 % against the baseline and −0.58 % against the record 118.37 g |
| Centre of mass, X | 150.50 mm | 147.04 mm (`.dat` and INP) | shifted to the thick side |
| Solver completion | — | `.sta`: THE ANALYSIS HAS COMPLETED SUCCESSFULLY (20-Oct-2026 18:03:07); `.dat` and `.msg`: 0 errors, 0 warnings, 0 negative-eigenvalue messages; six rigid-body modes at numerical zero (≤ 0.009 Hz); modes 7–20 positive | complete |
| Extraction integrity | — | 22 files; 20 modes; 10 201 nodes; format 2; the manifest frequencies equal the `.dat` (difference 0); modes real; in-plane / U3 ≤ 4.4e-12; the INP nodes reproduce the extracted geometry to 1.5e-05 mm | PASS |

**Thickness definition against the record.** The wedge is built from the two extreme edge means only (M11 §2):

- 5 mm from its edges it has 0.928 and 0.812 mm; the archived means of edges 4 and 2 are 0.926 and 0.816 mm;
- along edges 1 and 3 it averages 0.870 mm; the archived means are 0.880 and 0.882 mm;
- it does not contain the single low readings 0.71 and 0.74 mm near two corners, and nothing in the interior, which
  is not measured (§12.2).

**Orientation of the wedge on the plate.** The archived model is thick at FE X = 0. Under the declared placement D,
FE X = 0 lies at edge 2, whose readings are the **thin** ones (0.816 mm), and X = 301 at edge 4 (0.926 mm). So the
archived wedge under D has its gradient opposite to the edge readings. Two orientations were therefore declared
before any FE / EXP value of this task was computed, and neither is selected by MAC:

- `WEDGE_AS_ARCHIVED`: the model as solved, under D exactly as in §17 (thick at edge 2);
- `WEDGE_MIRRORED_X`: the same solution reflected X → 301 − X (thick at edge 4, as the edge readings under D). The
  reflection is an exact symmetry of the plan, the mesh and the axis-aligned material, so it equals the model with
  the reversed gradient; no solve is needed. Checks: the baseline shapes are unchanged by it (MAC ≥ 1 − 7e-14); the
  result equals the archived wedge under placements A and C to 7.2e-08.

Which orientation agrees with the thickness record is read from that record and from the convention D. D itself is
`CONVENTION_ONLY`, so this is not a physical statement about the plate.

### 18.3 Baseline against wedge: frequencies and branches (FE to FE)

Real MAC over all 10 201 nodes and three displacement components; one-to-one assignment (Hungarian), as in M11 R6.6.
The table is the same for both orientations (difference 8e-10).

| Baseline mode | Baseline, Hz | Wedge mode | Wedge, Hz | Change | FE-to-FE MAC | Second-best |
|---|---|---|---|---|---|---|
| 7 | 19.07 | 7 | 19.00 | −0.39 % | 0.998 | 0.002 |
| 8 | 59.87 | 8 | 59.39 | −0.81 % | 0.978 | 0.008 |
| 9 | 62.01 | 9 | 61.44 | −0.92 % | 0.968 | 0.017 |
| 10 | 71.85 | 10 | 71.43 | −0.59 % | 0.999 | 0.001 |
| 11 | 72.19 | 11 | 72.10 | −0.12 % | 0.972 | 0.024 |
| 12 | 116.58 | 12 | 115.93 | −0.56 % | 0.997 | 0.003 |
| 13 | 167.49 | **14** | 166.42 | −0.64 % | 0.998 | 0.000 |
| 14 | 168.61 | **13** | 164.12 | −2.66 % | **0.744** | 0.148 |
| 15 | 174.80 | 15 | 174.80 | +0.00 % | **0.815** | 0.151 |
| 16 | 179.90 | 16 | 180.49 | +0.33 % | **0.797** | 0.104 |
| 17 | 213.20 | 17 | 211.86 | −0.63 % | 0.997 | 0.002 |
| 18 | 213.95 | 18 | 213.10 | −0.40 % | 0.974 | 0.020 |
| 19 | 295.78 | 19 | 294.06 | −0.58 % | 0.991 | 0.008 |
| 20 | 327.90 | — | — | — | 0.176 with wedge 20 | 0.001 |

- **Frequencies.** Ten branches move by −0.1 % to −0.9 %, the size of the mean-thickness change (0.870 against
  0.875 mm, −0.57 %). Baseline 15 and 16 move by 0.00 % and +0.33 %, and baseline 14 by −2.66 %. With the same
  constants the wedge changes no tracked frequency by more than 3 %.
- **Branches kept (MAC ≥ 0.97): 10 of 14.** Baseline 13 and 14 exchange their order.
- **Branches changed: baseline 14, 15 and 16** (MAC 0.74–0.81). They are not lost: wedge modes 13, 15 and 16 lie
  0.977–0.996 inside the span of baseline 13–16. The wedge re-mixes a three-mode group, not a single pair. Wedge 13
  (164.1 Hz) carries 89 % of its U3 energy in the thin half of the plate.
- **Branch lost: baseline 20.** It has no counterpart among wedge modes 7–20. Wedge 20 (318.2 Hz) is another mode,
  96 % in the thin half, and lies only 0.18 in the span of the 14 baseline modes. It is reported as lost and is not
  re-paired by frequency. The two 14-mode sets therefore do not span the same space.

**Close modal subspaces.**

| Group | Spacing, baseline / wedge | Principal angles between the two subspaces | Share of each wedge mode in the baseline group |
|---|---|---|---|
| FE 8 / 9 | 3.57 % / 3.45 % | 2.4°, 11.5° | 0.983, 0.975 |
| FE 10 / 11 | 0.47 % / 0.94 % | 2.0°, 9.7° | 0.999, 0.972 |
| FE 13 / 14 | 0.67 % / 1.40 % | 2.4°, 30.4° | 0.744, 0.998 |
| FE 15 / 16 | 2.92 % / 3.26 % | 3.3°, 30.1° | 0.919, 0.829 |
| FE 17 / 18 | 0.35 % / 0.59 % | 3.1°, 9.3° | 0.997, 0.974 |
| FE 13–16 | — | 0.2°, 2.4°, 2.5°, 9.8° | 0.996, 0.998, 0.995, 0.977 |

- The wedge widens every close pair except 8 / 9. It lifts FE 15 / 16 just above the 3 % trigger; FE 10 / 11,
  13 / 14 and 17 / 18 stay close groups.
- In the low pairs (8 / 9, 10 / 11) and in 17 / 18 the wedge turns the pair by about 10° and mixes almost nothing
  inside it (off-diagonal MAC ≤ 0.02). The 13 % edge-thickness asymmetry therefore **does not re-mix the low
  near-degenerate bending pairs** in which records 2 and 4 lie.

Figures: `fig_shapes_baseline_vs_wedge.png` (the 14 shapes of both models) and `fig_fe_fe_tracking.png` (§18.7).

### 18.4 Research FE / EXP MAC with the nominal mapping of §17

Mapping, metric, levels and labels are exactly those of §17 (point id k ↔ k, the 261016 reconstruction, placement D,
complex MAC over 289 U3 values, bilinear transfer). The baseline matrix of §17.3 is reproduced with difference 0.0,
and its minimum matrix over the 59 scenarios also with 0.0. [min–max] is the range over the same 59 declared geometry
scenarios; no scenario is selected. 289 of 289 points are mapped in every case.

| EXP | Hz | Baseline: FE, signed error, MAC [min–max], label | Wedge as archived (thick at edge 2 under D) | Wedge mirrored in X (thick at edge 4 under D) |
|---|---|---|---|---|
| 1 | 18.63 | FE 7, +2.4 %, 0.91 [0.88–0.93], CANDIDATE_ONLY | FE 7, +2.0 %, 0.88 [0.85–0.91], CANDIDATE_ONLY | FE 7, +2.0 %, 0.92 [0.90–0.94], CANDIDATE_ONLY |
| 2 | 54.62 | FE 9, +13.5 %, 0.60 [0.59–0.61], AMBIGUOUS_CLUSTER | FE 8, +8.7 %, 0.61 [0.60–0.62], AMBIGUOUS_CLUSTER | FE 8, +8.7 %, 0.64 [0.62–0.65], AMBIGUOUS_CLUSTER |
| 3 | 63.50 | FE 20, +416 %, 0.31 [0.26–0.35], NO_CANDIDATE | FE 11, +13.6 %, 0.27 [0.26–0.27], NO_CANDIDATE | FE 11, +13.6 %, 0.22 [0.21–0.23], NO_CANDIDATE |
| 4 | 66.85 | FE 11, +8.0 %, 0.55 [0.54–0.56], AMBIGUOUS_CLUSTER | FE 11, +7.9 %, 0.54 [0.53–0.55], AMBIGUOUS_CLUSTER | FE 11, +7.9 %, 0.50 [0.48–0.52], AMBIGUOUS_CLUSTER |
| 5 | 74.21 | FE 10, −3.2 %, 0.48 [0.45–0.51], NO_CANDIDATE | FE 10, −3.8 %, 0.50 [0.47–0.52], NO_CANDIDATE | FE 10, −3.8 %, 0.47 [0.44–0.50], NO_CANDIDATE |
| 6 | 112.27 | FE 12, +3.8 %, 0.52 [0.49–0.55], WEAK_CANDIDATE | FE 12, +3.3 %, 0.56 [0.53–0.58], WEAK_CANDIDATE | FE 12, +3.3 %, 0.48 [0.44–0.51], NO_CANDIDATE |
| 7 | 145.94 | FE 14, +15.5 %, 0.79 [0.77–0.79], AMBIGUOUS_CLUSTER | FE 16, +23.7 %, **0.45** [0.42–0.49], NO_CANDIDATE | FE 13, +12.5 %, **0.97** [0.95–0.97], AMBIGUOUS_CLUSTER |
| 8 | 157.85 | FE 16, +14.0 %, 0.43 [0.41–0.44], AMBIGUOUS_CLUSTER | FE 13, +4.0 %, 0.55 [0.53–0.55], AMBIGUOUS_CLUSTER | FE 16, +14.3 %, 0.65 [0.62–0.66], AMBIGUOUS_CLUSTER |
| 9 | 169.18 | FE 13, −1.0 %, 0.26 [0.24–0.27], NO_CANDIDATE | FE 14, −1.6 %, 0.28 [0.26–0.29], NO_CANDIDATE | FE 14, −1.6 %, 0.24 [0.22–0.26], NO_CANDIDATE |
| 10 | 180.14 | FE 15, −3.0 %, 0.15 [0.14–0.16], NO_CANDIDATE | FE 15, −3.0 %, 0.23 [0.22–0.24], NO_CANDIDATE | FE 15, −3.0 %, 0.16 [0.14–0.17], NO_CANDIDATE |
| 11 | 191.60 | FE 18, +11.7 %, 0.54 [0.51–0.56], AMBIGUOUS_CLUSTER | FE 18, +11.2 %, 0.61 [0.59–0.61], AMBIGUOUS_CLUSTER | FE 18, +11.2 %, 0.46 [0.42–0.49], NO_CANDIDATE |

The labels are the descriptive ones of §17.4; none is a pairing status. The mode numbers of the wedge are its own
(wedge 13 is the changed branch of baseline 14, §18.3).

**Nominal matrix, wedge as archived (placement D as declared).**

| EXP (Hz) | FE 7 | FE 8 | FE 9 | FE 10 | FE 11 | FE 12 | FE 13 | FE 14 | FE 15 | FE 16 | FE 17 | FE 18 | FE 19 | FE 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FE Hz | 19.0 | 59.4 | 61.4 | 71.4 | 72.1 | 115.9 | 164.1 | 166.4 | 174.8 | 180.5 | 211.9 | 213.1 | 294.1 | 318.2 |
| 1 (18.63) | **0.88** | 0.00 | 0.01 | 0.14 | 0.00 | 0.00 | 0.01 | 0.00 | 0.41 | 0.09 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 (54.62) | 0.00 | **0.61** | 0.50 | 0.00 | 0.03 | 0.29 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 |
| 3 (63.50) | 0.00 | 0.21 | 0.07 | 0.00 | **0.27** | 0.02 | 0.00 | 0.11 | 0.00 | 0.00 | 0.12 | 0.00 | 0.00 | 0.01 |
| 4 (66.85) | 0.00 | 0.04 | 0.17 | 0.00 | **0.54** | 0.05 | 0.00 | 0.06 | 0.00 | 0.00 | 0.25 | 0.00 | 0.00 | 0.00 |
| 5 (74.21) | 0.00 | 0.00 | 0.00 | **0.50** | 0.00 | 0.00 | 0.00 | 0.00 | 0.15 | 0.04 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 (112.27) | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 | **0.56** | 0.00 | 0.00 | 0.00 | 0.00 | 0.16 | 0.00 | 0.00 | 0.00 |
| 7 (145.94) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.40 | 0.00 | 0.13 | **0.45** | 0.00 | 0.23 | 0.14 | 0.00 |
| 8 (157.85) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.55** | 0.00 | 0.04 | 0.27 | 0.00 | 0.01 | 0.39 | 0.00 |
| 9 (169.18) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.28** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 10 (180.14) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.23** | 0.05 | 0.00 | 0.01 | 0.00 | 0.00 |
| 11 (191.60) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.02 | 0.00 | **0.61** | 0.08 | 0.00 |

**Nominal matrix, wedge mirrored in X (thick side at edge 4 under D).** FE frequencies as above.

| EXP (Hz) | FE 7 | FE 8 | FE 9 | FE 10 | FE 11 | FE 12 | FE 13 | FE 14 | FE 15 | FE 16 | FE 17 | FE 18 | FE 19 | FE 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 (18.63) | **0.92** | 0.00 | 0.01 | 0.15 | 0.00 | 0.00 | 0.01 | 0.01 | 0.39 | 0.08 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 (54.62) | 0.00 | **0.64** | 0.53 | 0.00 | 0.08 | 0.30 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 |
| 3 (63.50) | 0.00 | 0.13 | 0.17 | 0.00 | **0.22** | 0.03 | 0.00 | 0.14 | 0.00 | 0.00 | 0.11 | 0.00 | 0.00 | 0.01 |
| 4 (66.85) | 0.00 | 0.11 | 0.05 | 0.00 | **0.50** | 0.10 | 0.00 | 0.08 | 0.00 | 0.00 | 0.23 | 0.00 | 0.00 | 0.01 |
| 5 (74.21) | 0.00 | 0.00 | 0.00 | **0.47** | 0.00 | 0.00 | 0.00 | 0.00 | 0.19 | 0.04 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 (112.27) | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | **0.48** | 0.00 | 0.00 | 0.00 | 0.00 | 0.25 | 0.00 | 0.00 | 0.00 |
| 7 (145.94) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.97** | 0.00 | 0.05 | 0.07 | 0.00 | 0.35 | 0.12 | 0.00 |
| 8 (157.85) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.18 | **0.65** | 0.00 | 0.06 | 0.36 | 0.00 |
| 9 (169.18) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.24** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 |
| 10 (180.14) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | **0.16** | 0.07 | 0.00 | 0.01 | 0.00 | 0.00 |
| 11 (191.60) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 0.00 | **0.46** | 0.23 | 0.00 |

**Close subspaces and the span of all 14 shapes** (descriptive shares at the 289 points; a high share is **not** a
confirmed cluster):

| EXP | Best two-mode subspace: baseline | Wedge as archived | Wedge mirrored | All 14: baseline | As archived | Mirrored |
|---|---|---|---|---|---|---|
| 1 | FE 15 / 16: 0.48 | FE 15 / 16: 0.47 | FE 15 / 16: 0.47 | 0.97 | 0.96 | 0.98 |
| 2 | FE 8 / 9: 0.97 | FE 8 / 9: 0.91 | FE 8 / 9: 0.99 | 1.00 | 1.00 | 1.00 |
| 3 | FE 8 / 9: 0.35 | FE 8 / 9: 0.35 | FE 8 / 9: 0.35 | 0.84 | 0.72 | 0.73 |
| 4 | FE 10 / 11: 0.55 | FE 10 / 11: 0.54 | FE 10 / 11: 0.50 | 0.92 | 0.83 | 0.84 |
| 5 | FE 10 / 11: 0.48 | FE 10 / 11: 0.50 | FE 10 / 11: 0.47 | 0.68 | 0.67 | 0.69 |
| 6 | FE 17 / 18: 0.20 | FE 17 / 18: 0.16 | FE 17 / 18: 0.25 | 1.00 | 1.00 | 1.00 |
| 7 | FE 13 / 14: 0.79 | FE 15 / 16: 0.65 | FE 13 / 14: 0.97 | 0.99 | 0.99 | 0.99 |
| 8 | FE 15 / 16: 0.92 | FE 13 / 14: 0.55 | FE 15 / 16: 0.83 | 0.98 | 0.98 | 0.98 |
| 9 | FE 13 / 14: 0.26 | FE 13 / 14: 0.28 | FE 13 / 14: 0.24 | 0.48 | 0.29 | 0.26 |
| 10 | FE 15 / 16: 0.25 | FE 15 / 16: 0.27 | FE 15 / 16: 0.22 | 0.67 | 0.68 | 0.67 |
| 11 | FE 17 / 18: 0.55 | FE 17 / 18: 0.61 | FE 17 / 18: 0.47 | 0.99 | 0.99 | 0.99 |

The lower "all 14" shares of records 3, 4 and 9 with the wedge come from the lost baseline mode 20 (§18.3): the wedge
set no longer contains that shape. It is a change of the basis, not a worse model.

Figures: `fig_mac_three_models.png` and `fig_first_ranked_three_models.png` (§18.7).

### 18.5 Comparison with PLATE-0875-RESEARCH-MAC-01

| Quantity | Baseline (§17) | Wedge as archived | Wedge mirrored in X |
|---|---|---|---|
| Records with a first-ranked MAC ≥ 0.80 | 1 (record 1) | 1 (record 1) | 2 (records 1 and 7) |
| Records with a first-ranked MAC ≥ 0.50 | 6 | 6 | 5 |
| Mean of the 11 first-ranked values | 0.504 | 0.498 | 0.520 |
| Change of the first-ranked value, record 7 | — | −0.33 | +0.19 |
| Change, record 8 | — | +0.12 | +0.22 |
| Change, the other nine records | — | −0.04 to +0.08 | −0.09 to +0.04 |
| First-ranked FE mode changes for records | — | 2, 3, 7, 8, 9 | 2, 3, 7, 9 |
| Signed frequency error of the first-ranked mode, records 2, 4, 11 | +13.5 %, +8.0 %, +11.7 % | +8.7 %, +7.9 %, +11.2 % | the same as archived |
| Largest change of any cell | — | 0.79 | 0.97 |

- **Against the geometry range of §17.5** (0.049 on the first-ranked cells): the wedge moves records 7 and 8 by 2 to
  7 times that range, and the other records by at most twice it. For modes 13–16 the model form matters more than
  the millimetre geometry; for the rest it is of similar size.
- **Record 7** (145.94 Hz). The measured shape resembles wedge 13, a Y-bending shape concentrated in the thin half:
  0.97 [0.95–0.97] with the thick side at edge 4, and 0.45 with the thick side at edge 2. It is **one record and one
  orientation**. Its label stays `AMBIGUOUS_CLUSTER` (wedge 13 / 14 are 1.4 % apart), and its frequency error stays
  +12.5 %. It is a candidate, not a pair and not a confirmed cluster term.
- **Record 8** rises to 0.55 or 0.65 and remains a mixture (two-mode share 0.83 with the mirrored wedge).
- **Record 2.** The first-ranked mode changes from FE 9 to FE 8 only because the two values exchange their order
  (0.57 / 0.60 → 0.61–0.64 / 0.50–0.53). The record still lies in the pair (0.91–0.99) and in neither shape
  alone.
- **Records 3, 5, 9 and 10** stay without a candidate in both orientations (≤ 0.50).
- **Records 4, 6 and 11** fall by 0.04–0.08 with the mirrored wedge and change by −0.01 to +0.06 with the archived
  one: the two orientations trade these records against record 7. Neither orientation improves every record.
- **Placement.** With the uniform baseline the placements A–D agreed to 7.8e-08 (§17.2). With the wedge they split
  into two classes, B = D (difference 4e-10) and A = C, which differ by up to 0.57 in one cell. A model with a
  thickness gradient is the first one here for which the placement convention changes the result.

### 18.6 Does thickness asymmetry warrant further investigation?

**Yes, as a model-form question tied to the physical registration. Not as an explanation of the whole discrepancy,
and not as a route to a parameter value.**

What the existing wedge shows:

1. **It is a first-order effect for one mode group.** A 13 % edge-to-edge gradient with unchanged constants re-mixes
   baseline modes 14–16, replaces mode 20 and turns the 13 / 14 and 15 / 16 subspaces by 30°. A uniform model cannot
   represent the shapes of records 7 and 8 between 146 and 158 Hz.
2. **It does not explain the frequencies.** It moves no frequency by more than 3 %, and the first-ranked errors of
   records 2, 4, 7, 8 and 11 remain +8 % to +14 %.
3. **It does not explain the low bending records.** Records 2, 4 and 5 (55–74 Hz) change by at most 0.05. Whatever
   mixes the FE 8 / 9 and 10 / 11 pairs in the experiment, this thickness gradient is not it. E1 ≠ E2, the two-band
   suspension and the force sensor remain untested (§14).
4. **Its sign depends on the orientation.** Record 7 is 0.97 with one orientation and 0.45 with the other. The
   orientation that agrees with the edge readings under D gives the higher value. That is consistent with the
   thickness record. It is **not** evidence for placement D, for the 261016 reconstruction or for the wedge as the
   true thickness field. An added mass or stiffness on one side (sensor, suspension) could produce a similar
   one-sided shape and is not modelled.
5. **It is not the plate.** The wedge uses two edge means, ignores the interior and the low corner readings, and its
   mass is 0.58 % below the record.

What follows for the research (nothing below is started; each item needs its own authorisation):

- **Measure the thickness inside the plate** (a map of 9 or more points, §10). This is the step with the highest
  value: without it any thickness model is a scenario.
- **Fix the FE placement physically before using a non-uniform model.** A thickness model built from the numbered
  edge readings carries the plate's own asymmetry and fixes the correspondence by construction (§16.3). Until then
  both orientations must be reported side by side, as here.
- **Do not combine the candidates.** Record 1 informs D66 only (§17.7). Record 7 is a candidate with one orientation
  of a scenario model, with a +12.5 % frequency error and an unverified registration. Two candidates of this kind do
  not make the bending stiffness identifiable, and no estimate is attempted.
- The blockers of §17.7 are unchanged.

### 18.7 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `51d6b84f…` and a clean tracked tree before the edit |
| Input hashes | all 28 inputs equal their recorded SHA-256 (§18.1); unchanged after the run |
| Mass consistency | `.dat` mass = mass integrated from the INP thickness, for both models, to 1e-5 g; centre of mass reproduced (147.04 mm) |
| Solver completion | archived run complete, no error, warning or negative eigenvalue (§18.2). No solve in this task |
| Extraction integrity | exit 0; 22 files; frequencies = `.dat`; node set and geometry = baseline; real modes (§18.2) |
| Branch tracking | assignment one-to-one; row and column maxima agree with it for all 14 rows; one lost branch and three changed branches reported, none re-paired by frequency |
| Mirror | the node map is an involution over all 10 201 nodes; mirroring the field equals mirroring the points to 7.2e-08 |
| Research MAC reproducibility | baseline = §17.3 with difference 0.0; identical shapes 1.0; scale, sign and complex factor ≤ 3.3e-16; in-process repeat 3.3e-16; two complete runs give byte-identical `results.json` and CSV files |
| Tests | `research/m11_r65`: 29 OK. `tests.test_plate_registration_readiness`, `tests.test_plate_rc1_owner_clarification`, `tests.test_plate_study`: 60 OK |

The models, both wedge orientations, the metrics and the rules were written into the script before its first run
(`protocol.json`). Two checks were added after the first results were seen: the three-mode group FE 13–16 and the
wedge under placements A–D. They add descriptions and change no reported MAC. This is not an independent
preregistration.

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_FE_APPLICABILITY_01` (outside git):

- `input\CFRP_S4R_WEDGE_FreeFree.odb` (verified copy), `scripts\extract_odb.py`, `logs\`, `extraction\` (manifest,
  geometry, 20 modes);
- `run_fe_applicability.py`, `protocol.json`, `results.json` (`1fd0965e…`), `shapes_u3.npz`;
- `fe_fe_branches.csv`, `mac_nominal_BASELINE.csv`, `mac_nominal_WEDGE_AS_ARCHIVED.csv`,
  `mac_nominal_WEDGE_MIRRORED_X.csv`;
- `report.py`, `fig_shapes_baseline_vs_wedge.png`, `fig_fe_fe_tracking.png`, `fig_mac_three_models.png`,
  `fig_first_ranked_three_models.png`.

Nothing is published in the repository except this section. No ODB, solver file or extraction is committed.

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, registrations, criteria, the 5 / 8 % limits, M8 / D-077, governed records and every
original file.
