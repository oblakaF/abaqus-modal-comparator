# PLATE-ONLY-R1 — effective properties of one CFRP plate (research, non-normative)

**Status: REVIEW_READY (2026-10-30; F1 traceability and notation, see §11; PLATE-ONLY-R2 specimen identity, archived record, FE applicability and orientation, see §12; R2-F1 package identity, the two series and the thickness, see §13; PLATE-WORKBENCH-RC1 integration, registration readiness and the prepared FE campaign, with the owner's final correction of the test conditions, see §14; the owner's statement of the material family, 2026-11-24, see §15; the owner's confirmation of the scanned face and the four remaining registration facts, 2026-11-24, see §16; the research FE / EXP MAC of 261027 and its geometry sensitivity, 2026-11-24, see §17; the FE applicability check of the existing wedge-thickness model, 2026-11-25, with one owner-authorised ODB extraction and no solve, see §18; the thickness field built from all 20 perimeter readings, 2026-11-25, with one owner-authorised Abaqus solve and one ODB extraction, see §19; the material sensitivity of the existing FE variants, 2026-11-25, see §20; the experimental quality of the 11 fitted records against the stored response data, 2026-11-25, see §21; the directional bending stiffness hypothesis against the existing FE results, with the qualification of §21, 2026-11-25, see §22; the recheck of the 261016 scan window, which finds the 215 mm width of the nominal mapping to be a unit-conversion error, 2026-11-25, see §23; the corrected scan normalisation in the program and the research MAC recomputed with the corrected positions, which supersedes the MAC results of §17–§22 for current research conclusions, 2026-11-26, see §24; the prospective directional stiffness test of §22.8 solved with one owner-authorised Abaqus solve and one ODB extraction, all three criteria met, 2026-11-26, see §25; the combined model with the wedge thickness of §18 and the stiffness ratio of §25, one owner-authorised Abaqus solve and one ODB extraction, record 7 explained, records 3 and 4 not, one record outside ± 5 %, 2026-11-26, see §26). Research only, non-normative.** This report changes no specification, decision,
status, evidence, registration, criterion or catalogue entry. It releases no material constant. No LM, parameter fit
or Auto-ID was run. Abaqus was used only under an explicit owner authorisation and only in four sections: one ODB
extraction of an archived result (§18), and one eigenfrequency solve with one ODB extraction in each of §19, §25
and §26. §1–§17 and
§20–§24 ran no Abaqus; §21 reads experimental files only, §23 reads instrument records only, the others read
existing FE results. §24 is the only section that changes program code (`src/services/psv_video_registration.py`).

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
| `scan_metric_geometry` | 261016: grid shape and scale confirmed by the scanner-angle record (aspect 0.7747 against 0.7553; rms 1.32 mm; M11 §15.4), window about 215.4 × 285.2 mm (**§23: the 215.4 mm is a unit-conversion error, and the scanner-angle check could not detect it; the instrument record gives 287.1 × 285.3 mm**). 261027: no instrument record of the physical positions; the owner's "same points" carries the 261016 positions; the 261027 UNV grid (277.7 × 277.0 mm) is a representation | INSTRUMENT_RECORD for the 261016 shape; OWNER_REPORTED carry-over to 261027 | **open** | the same as above |
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

> **Superseded for current research conclusions (§24, 2026-11-26):** the research MAC values, labels, first-ranked modes and scenario ranges of this section. They were computed with point positions that are wrong along FE X by up to 49.3 mm (§23). The text below is kept as written; §24 gives the values recomputed with the corrected positions.

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
  **§23: the 215.4 mm width and the left and right gaps are a unit-conversion error of the reconstruction; the
  instrument record gives 287.1 × 285.3 mm with gaps of about 7 mm on every side.**
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

> **Superseded for current research conclusions (§24, 2026-11-26):** every FE / EXP MAC value of this section and the comparison of the models by MAC. They were computed with point positions that are wrong along FE X by up to 49.3 mm (§23). The text below is kept as written; §24 gives the values recomputed with the corrected positions.

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

## 19. PLATE-0875-THICKNESS-FIELD-01 — a thickness field from all 20 perimeter readings (2026-11-25)

> **Superseded for current research conclusions (§24, 2026-11-26):** every FE / EXP MAC value of this section and the comparison of the models by MAC. They were computed with point positions that are wrong along FE X by up to 49.3 mm (§23). The text below is kept as written; §24 gives the values recomputed with the corrected positions.

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** The interior thickness
of the model is **`ASSUMED_MODEL_FORM`**: it is an interpolation, not measured geometry. Nothing here is a mode
pairing, a confirmed cluster, a physical registration or a parameter estimate. No material constant, density or
thickness was adjusted, and nothing was optimised against a frequency or a MAC. No FrozenRegistration was created; the
registration guard is unchanged and was not bypassed. M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production
Auto-ID BLOCKED are unchanged.

**Abaqus use (owner authorisation: at most one solve and one extraction).**

| Action | Count | Detail |
|---|---|---|
| Abaqus solves | **1** | `CFRP_S4R_TFIELD20_FreeFree`, Abaqus/Standard 2024, cpus = 1, interactive; 2026-11-25 00:28:40, 14.6 s, exit 0; no retry |
| ODB extractions | **1** | pinned extractor `039aa067…`, modes 1–20; 00:29:01, 4.5 s, exit 0; the ODB is unchanged by it; no retry |

**Short answer.** The 20-reading field behaves almost like the wedge of §18 with its thick side at edge 4: its 14
shapes are the wedge's shapes (FE-to-FE MAC ≥ 0.96). Against the experiment it changes **one** low bending record,
record 2 (0.60 → 0.80), keeps record 7 (0.96), is weaker than the wedge for record 8 (0.53 against 0.65) and leaves
records 3–6 where they were. The frequency errors do not shrink. The result for record 2 rests on assumed reading
positions that could not be varied with one solve.

### 19.1 The readings and their mapping

Source: the owner's handwritten sheet, photograph `plate_measurements_20261021.jpg` (`df5339cd…` = recorded), read
again for this task, and M11 §8–§8.1. Its transcription file `plate_measurements_20261021.json` (`6d52a323…`, hash
first recorded here) and `plate_study.THICKNESS_READINGS_MM` hold the same 20 values. Nothing was changed in them.

| Row = edge | Readings 1 → 5, mm | Mean |
|---|---|---|
| 1 | 0.94, 0.92, 0.94, 0.89, **0.71** | 0.880 |
| 2 | 0.79, 0.82, 0.84\*, 0.81, 0.82 | 0.816 |
| 3 | **0.74**, 0.89, 0.94, 0.92, 0.92 | 0.882 |
| 4 | 0.93, 0.94, 0.93, 0.92, 0.91 | 0.926 |

\* The historical ambiguity is kept: 0.84 as transcribed and as read by the owner (M11 §8.1); it could be read 0.81.
The model uses 0.84. With 0.81 the field would change by at most 0.030 mm (rms 0.004 mm) and the mass by −0.24 g.
The readings 0.71 and 0.74 mm are kept and are reproduced by the field.

**Measured against assumed.**

| Item | Status | Source or assumption |
|---|---|---|
| The 20 values, five per edge | MEASURED (owner's sheet) | caliper of 0.01 mm resolution and an electronic caliper (M11 §8.1) |
| Row → edge | OWNER_REPORTED | rows 1, 2, 3 = edges 1, 2, 3; row 4 = edge 4 (the owner wrote "3 левая" for the left edge; read as row 4, M11 §8.1) |
| Mass 118.37 g, plan 301 × 300 mm | MEASURED (owner's sheet) | — |
| Distance of a row from its edge | PARTLY RECORDED | the sheet sketch shows 4.5 mm on a vertical row and 6.5 mm on a horizontal row. **Assumed:** 4.5 mm for edges 2 and 4, 6.5 mm for edges 1 and 3 |
| Position of each reading along its edge | **ASSUMED** | the centres of five equal segments: 30.1, 90.3, 150.5, 210.7, 270.9 mm along 301 mm; 30, 90, 150, 210, 270 mm along 300 mm. The sheet gives no positions |
| Direction of each row | **ASSUMED** | one continuous circuit in the order of the row numbers 1 → 2 → 3 → 4: row 1 from the edge-4 end to the edge-2 end, row 2 from edge 1 to edge 3, row 3 from the edge-2 end to the edge-4 end, row 4 from edge 3 to edge 1. M11 §8 lists "the corner each row starts from" as open |
| Edges on the FE model | CONVENTION_ONLY (placement D, owner's task text) | edge 2 (thin) at X = 0, edge 4 (thick) at X = 301, edge 1 at Y = 300, edge 3 at Y = 0 |
| Interior thickness | **ASSUMED_MODEL_FORM** | the interpolation below; nothing is measured inside the plate |

With the assumed circuit both low readings fall next to the thin edge 2: 0.71 at (30.1, 293.5) and 0.74 at
(30.1, 6.5) mm. That is a consequence of the assumption, not a finding. With rows 1 and 3 read in the other direction
they would lie next to the thick edge 4.

### 19.2 The thickness field

**Method, fixed before the solve and before any modal comparison** (`build_thickness_field.py`, declaration SHA-256
`7f1bacbf…`): inverse-distance weighting (Shepard), power 2, over all 20 readings, evaluated at the 10 201 nodes and
written as `*Nodal Thickness`.

- It is deterministic and exact at every reading.
- It is a convex combination of the readings, so it is bounded by the smallest and largest reading and positive.
- It is smooth away from the reading positions.
- Its single parameter is the classical value 2. No parameter, position, direction or reading was tuned.

| Check | Result |
|---|---|
| Exact at the 20 readings | error 0.0 analytically; the nodal (bilinear) field at the 20 positions is within 0.00024 mm |
| Bounded and positive | 0.7100–0.9400 mm at the nodes (readings 0.71–0.94 mm) |
| Distribution | area mean 0.8805 mm, sd 0.043 mm; percentiles 5 / 25 / 50 / 75 / 95: 0.804 / 0.848 / 0.894 / 0.916 / 0.928 mm; value at the plate centre 0.882 mm |
| Edge lines | means along the four reading lines 0.880 / 0.814 / 0.884 / 0.925 mm (edges 1 / 2 / 3 / 4); the archived edge means are 0.880 / 0.816 / 0.882 / 0.926 mm |
| Smoothness | largest nodal gradient 0.0048 mm per mm (next to the 0.71 reading) |
| Orientation | mean 0.814 mm for X < 10 and 0.925 mm for X > 291: thin edge at X = 0, thick edge at X = 301, as required |
| **Integrated mass** | **119.109 g** with the unchanged density 1.498e-9 t/mm³ (`.dat` of the solve: 119.109 g; integral of the INP thickness: 119.109 g) |
| **Against the record 118.37 g** | **+0.62 %** (+0.74 g). The uniform model has 118.361 g (−0.01 %), the wedge 117.684 g (−0.58 %). **Neither density nor thickness was adjusted** |
| Centre of mass | X 154.26 mm, Y 149.80 mm (uniform: 150.50, 150.00) |

The mass difference means that the field's mean thickness (0.8805 mm) and the density of the template (set from the
mean of the 20 readings, 0.876 mm) are not exactly consistent. It is reported, not corrected.

**What the assumptions change in the thickness (no solve, no modal quantity).**

| Alternative | Largest change | rms change | Mass |
|---|---|---|---|
| Reading 0.81 instead of 0.84 | 0.030 mm | 0.004 mm | 118.87 g |
| Power 1 / 3 / 4 instead of 2 | 0.071 / 0.030 / 0.046 mm | 0.019 / 0.008 / 0.013 mm | 118.78 / 119.41 / 119.63 g |
| Row 2 or row 4 reversed | 0.03 mm | ≤ 0.006 mm | 119.11 g |
| Row 3 reversed | 0.18 mm | 0.027 mm | 119.11 g |
| Row 1 reversed | 0.23 mm | 0.034 mm | 119.11 g |
| Rows 1 and 3 reversed | 0.23 mm | 0.044 mm | 119.11 g |

The direction of rows 1 and 3 is the assumption that matters: it moves the two low readings to the other side of the
plate. Its effect on the modes is **not known**: only the declared field was solved.

The contour map with the measured values, their assumed positions and the assumed row directions is
`fig_thickness_field.png` (§19.7).

### 19.3 The model and its solve

| Item | Result |
|---|---|
| INP | `CFRP_S4R_TFIELD20_FreeFree.inp` (`d688a272…`): the archived wedge INP with only the 10 201 thickness values, the job-name comment and the description comment replaced (checked line by line) |
| Mesh | 10 201 nodes, 10 000 S4R, plan 301 × 300 mm: identical to the baseline (labels, connectivity, coordinates) |
| Material, step, boundary conditions | density, elastic constants, Lanczos 20 modes, field output U: the same lines as the baseline; no boundary, spring, mass, constraint or load keyword (free-free) |
| Only difference from the baseline | `*Nodal Thickness` and the `nodal thickness` option of the shell section |
| Solver completion | `.sta`: THE ANALYSIS HAS COMPLETED SUCCESSFULLY (25-Nov-2026 00:28:51); `.dat` and `.msg`: 0 errors, 0 warnings, 0 negative-eigenvalue messages; six rigid-body modes at numerical zero (≤ 0.011 Hz); modes 7–20 positive |
| Extraction integrity | 22 files; 20 modes; 10 201 nodes; manifest frequencies = `.dat` (difference 0); modes real; in-plane / U3 ≤ 2.9e-12; the INP nodes reproduce the extracted geometry to 1.5e-05 mm; ODB `ce07142c…` equal before and after |

A first version of the INP was written with the thickness evaluated in the part frame instead of the assembly frame
(the instance is translated). The mass check exposed it (114.4 g) before any solve; it was replaced and never run.
The declaration was not changed.

### 19.4 Frequencies and FE-to-FE branches of the three models

Real MAC over all 10 201 nodes and three components, one-to-one assignment, as in §18.3. "Wedge" is the wedge with
its thick side at edge 4 (§18, mirrored in X), the orientation of the field.

| Baseline mode | Uniform, Hz | Wedge: mode, Hz | Field: mode, Hz | Field against uniform | Field against wedge | MAC field–uniform | MAC field–wedge |
|---|---|---|---|---|---|---|---|
| 7 | 19.07 | 7: 19.00 | 7: 19.47 | +2.10 % | +2.51 % | 0.997 | 1.000 |
| 8 | 59.87 | 8: 59.39 | 8: 60.19 | +0.53 % | +1.35 % | 0.911 | 0.963 |
| 9 | 62.01 | 9: 61.44 | 9: 63.33 | +2.13 % | +3.07 % | 0.920 | 0.961 |
| 10 | 71.85 | 10: 71.43 | **11**: 74.08 | +3.11 % | +3.71 % | 0.984 | 0.985 |
| 11 | 72.19 | 11: 72.10 | **10**: 73.29 | +1.52 % | +1.65 % | 0.973 | 0.983 |
| 12 | 116.58 | 12: 115.93 | 12: 117.82 | +1.06 % | +1.63 % | 0.996 | 0.999 |
| 13 | 167.49 | 14: 166.42 | 14: 169.16 | +1.00 % | +1.65 % | 0.995 | 0.997 |
| 14 | 168.61 | 13: 164.12 | 13: 166.13 | −1.47 % | +1.22 % | **0.743** | 0.998 |
| 15 | 174.80 | 15: 174.80 | 15: 177.73 | +1.68 % | +1.68 % | **0.843** | 0.966 |
| 16 | 179.90 | 16: 180.49 | 16: 182.97 | +1.71 % | +1.37 % | **0.892** | 0.964 |
| 17 | 213.20 | 17: 211.86 | 17: 214.94 | +0.82 % | +1.45 % | 0.959 | 0.963 |
| 18 | 213.95 | 18: 213.10 | 18: 215.26 | +0.61 % | +1.01 % | 0.942 | 0.963 |
| 19 | 295.78 | 19: 294.06 | 19: 297.30 | +0.51 % | +1.10 % | 0.988 | 0.999 |
| 20 | 327.90 | — | — | — | — | 0.155 with field 20 | — |
| (wedge 20) | — | 20: 318.18 | 20: 321.42 | — | +1.02 % | — | 0.997 |

- **Field against wedge.** All 14 field modes track one wedge mode with MAC ≥ 0.96 and second-best ≤ 0.04; the two
  sets span the same space. The field is the wedge plus local detail. Its frequencies are 1.0 % to 3.7 % higher, in
  line with its larger mean thickness (0.8805 against 0.870 mm, +1.2 %) and its thicker right half.
- **Field against uniform.** Frequencies +0.5 % to +3.1 %, one branch −1.5 %. Ten branches keep MAC ≥ 0.91. Baseline
  10 / 11 and 13 / 14 exchange their order. Baseline 14, 15 and 16 are re-mixed (0.74–0.89), as with the wedge.
  Baseline 20 is lost; field 20 is the edge mode of the wedge (97 % of its U3 energy in the thin half).
- **Low pairs.** The field turns the FE 8 / 9 subspace by 9.1° and FE 10 / 11 by 6.9° against the uniform model
  (wedge: 11.5° and 9.7°). Inside the 8 / 9 pair it mixes more than the wedge: off-diagonal MAC 0.07 against 0.01,
  and the pair spacing grows from 3.6 % to 5.2 %.
- **Close groups (3 % trigger) of the field:** FE 10 / 11 (1.1 %), 13 / 14 (1.8 %), 15 / 16 (2.95 %), 17 / 18
  (0.15 %).

Figure: `fig_shapes_three_models.png` (§19.7).

### 19.5 Research FE / EXP MAC with the unchanged mapping

Mapping, metric, levels and labels are exactly those of §17 and §18.4. The matrices of the uniform model and of both
wedge orientations are reproduced with difference 0.0. [min–max] is the range over the same 59 declared geometry
scenarios; no scenario is selected. 289 of 289 points are mapped in every case.

**Nominal matrix, field of the 20 readings.**

| EXP (Hz) | FE 7 | FE 8 | FE 9 | FE 10 | FE 11 | FE 12 | FE 13 | FE 14 | FE 15 | FE 16 | FE 17 | FE 18 | FE 19 | FE 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FE Hz | 19.5 | 60.2 | 63.3 | 73.3 | 74.1 | 117.8 | 166.1 | 169.2 | 177.7 | 183.0 | 214.9 | 215.3 | 297.3 | 321.4 |
| 1 (18.63) | **0.93** | 0.00 | 0.01 | 0.00 | 0.15 | 0.00 | 0.01 | 0.00 | 0.32 | 0.15 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 (54.62) | 0.00 | **0.80** | 0.36 | 0.05 | 0.00 | 0.29 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 |
| 3 (63.50) | 0.00 | 0.07 | 0.21 | **0.25** | 0.00 | 0.03 | 0.00 | 0.14 | 0.00 | 0.00 | 0.11 | 0.00 | 0.00 | 0.00 |
| 4 (66.85) | 0.00 | 0.07 | 0.10 | **0.49** | 0.01 | 0.10 | 0.00 | 0.09 | 0.00 | 0.00 | 0.22 | 0.02 | 0.00 | 0.01 |
| 5 (74.21) | 0.00 | 0.00 | 0.00 | 0.01 | **0.48** | 0.00 | 0.00 | 0.00 | 0.16 | 0.08 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 (112.27) | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | **0.49** | 0.00 | 0.00 | 0.00 | 0.00 | 0.25 | 0.01 | 0.00 | 0.00 |
| 7 (145.94) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.96** | 0.00 | 0.08 | 0.04 | 0.01 | 0.34 | 0.12 | 0.00 |
| 8 (157.85) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.31 | **0.53** | 0.00 | 0.06 | 0.36 | 0.00 |
| 9 (169.18) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.24** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 |
| 10 (180.14) | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | **0.11** | 0.10 | 0.00 | 0.01 | 0.00 | 0.00 |
| 11 (191.60) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 0.03 | **0.43** | 0.24 | 0.00 |

**First-ranked FE mode of each model: FE mode, signed frequency error, MAC [min–max], label.**

| EXP | Hz | Uniform | Wedge, thick at edge 4 | Field of the 20 readings |
|---|---|---|---|---|
| 1 | 18.63 | FE 7, +2.4 %, 0.91 [0.88–0.93], CANDIDATE_ONLY | FE 7, +2.0 %, 0.92 [0.90–0.94], CANDIDATE_ONLY | FE 7, +4.5 %, 0.93 [0.90–0.95], CANDIDATE_ONLY |
| 2 | 54.62 | FE 9, +13.5 %, 0.60 [0.59–0.61], AMBIGUOUS_CLUSTER | FE 8, +8.7 %, 0.64 [0.62–0.65], AMBIGUOUS_CLUSTER | FE 8, +10.2 %, **0.80** [0.79–0.81], AMBIGUOUS_CLUSTER |
| 3 | 63.50 | FE 20, +416 %, 0.31 [0.26–0.35], NO_CANDIDATE | FE 11, +13.6 %, 0.22 [0.21–0.23], NO_CANDIDATE | FE 10, +15.4 %, 0.25 [0.24–0.26], NO_CANDIDATE |
| 4 | 66.85 | FE 11, +8.0 %, 0.55 [0.54–0.56], AMBIGUOUS_CLUSTER | FE 11, +7.9 %, 0.50 [0.48–0.52], AMBIGUOUS_CLUSTER | FE 10, +9.6 %, 0.49 [0.47–0.50], NO_CANDIDATE |
| 5 | 74.21 | FE 10, −3.2 %, 0.48 [0.45–0.51], NO_CANDIDATE | FE 10, −3.8 %, 0.47 [0.44–0.50], NO_CANDIDATE | FE 11, −0.2 %, 0.48 [0.44–0.51], NO_CANDIDATE |
| 6 | 112.27 | FE 12, +3.8 %, 0.52 [0.49–0.55], WEAK_CANDIDATE | FE 12, +3.3 %, 0.48 [0.44–0.51], NO_CANDIDATE | FE 12, +4.9 %, 0.49 [0.46–0.53], NO_CANDIDATE |
| 7 | 145.94 | FE 14, +15.5 %, 0.79 [0.77–0.79], AMBIGUOUS_CLUSTER | FE 13, +12.5 %, 0.97 [0.95–0.97], AMBIGUOUS_CLUSTER | FE 13, +13.8 %, **0.96** [0.95–0.97], AMBIGUOUS_CLUSTER |
| 8 | 157.85 | FE 16, +14.0 %, 0.43 [0.41–0.44], AMBIGUOUS_CLUSTER | FE 16, +14.3 %, 0.65 [0.62–0.66], AMBIGUOUS_CLUSTER | FE 16, +15.9 %, **0.53** [0.51–0.53], AMBIGUOUS_CLUSTER |
| 9 | 169.18 | FE 13, −1.0 %, 0.26 [0.24–0.27], NO_CANDIDATE | FE 14, −1.6 %, 0.24 [0.22–0.26], NO_CANDIDATE | FE 14, −0.0 %, 0.24 [0.22–0.25], NO_CANDIDATE |
| 10 | 180.14 | FE 15, −3.0 %, 0.15 [0.14–0.16], NO_CANDIDATE | FE 15, −3.0 %, 0.16 [0.14–0.17], NO_CANDIDATE | FE 15, −1.3 %, 0.11 [0.10–0.12], NO_CANDIDATE |
| 11 | 191.60 | FE 18, +11.7 %, 0.54 [0.51–0.56], AMBIGUOUS_CLUSTER | FE 18, +11.2 %, 0.46 [0.42–0.49], NO_CANDIDATE | FE 18, +12.3 %, 0.43 [0.38–0.46], NO_CANDIDATE |

The labels are the descriptive ones of §17.4; none is a pairing status. The mode numbers are those of each model
(the field's FE 10 is the branch of baseline 11, §19.4). The wedge with its thick side at edge 2 is in §18.4; it is
not the orientation of this field.

**Two-mode subspaces and the span of all 14 shapes** (descriptive shares; a high share is not a confirmed cluster):

| EXP | Two-mode subspace: uniform | Wedge | Field | All 14: uniform | Wedge | Field |
|---|---|---|---|---|---|---|
| 1 | FE 15 / 16: 0.48 | FE 15 / 16: 0.47 | FE 15 / 16: 0.47 | 0.97 | 0.98 | 0.98 |
| 2 | FE 8 / 9: 0.97 | FE 8 / 9: 0.99 | FE 8 / 9: 0.99 | 1.00 | 1.00 | 1.00 |
| 3 | FE 8 / 9: 0.35 | FE 8 / 9: 0.35 | FE 8 / 9: 0.34 | 0.84 | 0.73 | 0.74 |
| 4 | FE 10 / 11: 0.55 | FE 10 / 11: 0.50 | FE 10 / 11: 0.50 | 0.92 | 0.84 | 0.84 |
| 5 | FE 10 / 11: 0.48 | FE 10 / 11: 0.47 | FE 10 / 11: 0.49 | 0.68 | 0.69 | 0.71 |
| 6 | FE 17 / 18: 0.20 | FE 17 / 18: 0.25 | FE 17 / 18: 0.26 | 1.00 | 1.00 | 1.00 |
| 7 | FE 13 / 14: 0.79 | FE 13 / 14: 0.97 | FE 13 / 14: 0.97 | 0.99 | 0.99 | 0.99 |
| 8 | FE 15 / 16: 0.92 | FE 15 / 16: 0.83 | FE 15 / 16: 0.84 | 0.98 | 0.98 | 0.98 |
| 9 | FE 13 / 14: 0.26 | FE 13 / 14: 0.24 | FE 13 / 14: 0.24 | 0.48 | 0.26 | 0.26 |
| 10 | FE 15 / 16: 0.25 | FE 15 / 16: 0.22 | FE 15 / 16: 0.22 | 0.67 | 0.67 | 0.67 |
| 11 | FE 17 / 18: 0.55 | FE 17 / 18: 0.47 | FE 17 / 18: 0.46 | 0.99 | 0.99 | 0.99 |

Figures: `fig_mac_three_models.png` and `fig_first_ranked_three_models.png` (§19.7).

### 19.6 Does the field explain the low bending modes and records 7 and 8 better?

| Quantity | Uniform | Wedge, thick at edge 4 | Field of the 20 readings |
|---|---|---|---|
| Mean first-ranked MAC, low bending records 2–6 | 0.494 | 0.463 | 0.503 |
| Mean first-ranked MAC, records 7 and 8 | 0.607 | 0.811 | 0.745 |
| Mean first-ranked MAC, all 11 records | 0.504 | 0.520 | 0.519 |
| Records with MAC ≥ 0.80 | 1 | 1, 7 | 1, 2, 7 |
| Records with MAC ≥ 0.50 | 1, 2, 4, 6, 7, 11 | 1, 2, 4, 7, 8 | 1, 2, 7, 8 |
| Integrated mass against 118.37 g | −0.01 % | −0.58 % | +0.62 % |
| Signed frequency error of the first-ranked mode, records 1 / 2 / 7 / 8 | +2.4 / +13.5 / +15.5 / +14.0 % | +2.0 / +8.7 / +12.5 / +14.3 % | +4.5 / +10.2 / +13.8 / +15.9 % |

- **Low bending records: one of five.** Record 2 rises from 0.60 (uniform) and 0.64 (wedge) to 0.80 [0.79–0.81]
  with FE 8. It lies on the 0.80 level, not above it; its frequency error is +10.2 %; its label stays
  `AMBIGUOUS_CLUSTER` because it lies 0.99 in the FE 8 / 9 subspace. Records 3, 4, 5 and 6 change by −0.06 to −0.01
  against the uniform model and by −0.01 to +0.03 against the wedge: **the field does not explain them**. Records 4
  and 6 drop below 0.50.
- **Record 7: as the wedge.** 0.96 [0.95–0.97] against 0.97; still `AMBIGUOUS_CLUSTER` (FE 13 / 14 are 1.8 % apart)
  and +13.8 % in frequency.
- **Record 8: better than uniform, worse than the wedge.** 0.53 against 0.43 and 0.65. It remains a mixture (0.84 in
  FE 15 / 16).
- **Other records.** Record 11 falls to 0.43 (uniform 0.54). Records 3, 5, 9 and 10 have no candidate in any model.
- **Frequencies are not explained.** The field raises every frequency but one against the uniform model. The
  first-ranked errors of the bending records stay at +10 % to +16 %, and record 1 moves from +2.4 % to +4.5 %.
- **Overall** the field equals the wedge (mean 0.519 against 0.520). It trades record 8 and records 4, 6, 11
  against record 2. No model is better on every record, and none is selected.
- **Placement.** For the field the placements A and C differ from D by up to 0.57 in one cell, and B by 0.03: the
  X orientation decides, the Y asymmetry of the readings matters little.

**How far the record-2 result can be trusted.** The difference between the field and the wedge is the local detail
at the two ends of the thin edge, where the assumed circuit puts the readings 0.71 and 0.74. The direction of rows 1
and 3 is assumed, and reversing it changes the field there by up to 0.23 mm. Whether record 2 would still reach 0.80
is not known, and it was not explored: one solve was authorised, and choosing a row direction by MAC is excluded.

### 19.7 Remaining limitations for stiffness identification

1. **The thickness field is assumed.** The interior is not measured. The positions along the edges and the row
   directions are assumed; the low readings may sit on either side. Only a thickness map of the plate removes this.
2. **The mass is not closed.** The field is 0.62 % above the weighed mass with the unchanged density. With a
   non-uniform thickness, density and thickness can no longer both be taken from the template; nothing was adjusted.
3. **The frequencies are off by +10 % to +16 %** for the bending candidates with the template constants, in all
   three models. No thickness form examined here removes that, and no constant was fitted.
4. **Candidates, not pairs.** Record 1 (twist; informs D66 only), record 7 (0.96, in a close FE group) and record 2
   (0.80, on the level, dependent on an assumption). All three rest on a convention placement and an unverified
   registration. Eight of eleven records stay at or below 0.53 with this field. This does not establish
   identifiability of D11 or D22, and no estimate is attempted.
5. **Model form still incomplete.** E1 ≠ E2 with traceable axes, the two-band suspension and the force sensor are
   untested (§14).
6. **Unchanged:** the blockers of §17.7, the registration facts of §16.3, D-044, SPEC §6 S4, M8 GATE NOT_MET and
   D-077.

### 19.8 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `bc0082bc…` and a clean tracked tree before the edit |
| Source hashes | sheet photograph, baseline and wedge INP, the experiment, the nominal geometry, the R6 package, the wedge extraction (22 files) and the results of §17 and §18 equal their recorded hashes; unchanged after the run |
| Measurement mapping | 20 of 20 values equal in the sheet, the transcription file and `plate_study`; every position, offset and direction listed as measured or assumed (§19.1) |
| Interpolation validity | exact at the readings; bounded 0.71–0.94 mm; positive; the solved INP equals the declared field (difference 0.0) |
| Mass | `.dat` = integral of the INP thickness (119.109 g); +0.62 % against the record; no adjustment |
| Solver completion and extraction integrity | §19.3 |
| Branch tracking | one-to-one; row and column maxima agree with the assignment in all three comparisons; the wedge tracking of §18.3 is reproduced to 8e-10; one lost branch reported, not re-paired by frequency |
| Research MAC reproducibility | uniform = §17.3 and both wedge matrices = §18.4 with difference 0.0; identical shapes 1.0; scale and sign ≤ 2.2e-16; in-process repeat 2.8e-16; two complete runs give byte-identical `results.json` and CSV files |
| Tests | `research/m11_r65`: 29 OK. `tests.test_plate_registration_readiness`, `tests.test_plate_rc1_owner_clarification`, `tests.test_plate_study`: 60 OK |

The field, its assumptions and the model were fixed and hashed before the solve. The comparison metrics are those of
§17 and §18. This is not an independent preregistration.

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_THICKNESS_FIELD_01` (outside git):

- `build_thickness_field.py`, `thickness_field.json` (`a48fba73…`), `thickness_field.npz`;
- `solve\` (INP, `.dat` `c7c65550…`, `.odb` `ce07142c…`, `.sta`, `.msg`, logs), `scripts\extract_odb.py`, `logs\`,
  `extraction\`;
- `run_thickness_field_compare.py`, `results.json` (`61947357…`), `shapes_u3.npz`, `mac_nominal_*.csv`,
  `fe_fe_branches_tfield_vs_baseline.csv`;
- `report.py`, `fig_thickness_field.png`, `fig_shapes_three_models.png`, `fig_mac_three_models.png`,
  `fig_first_ranked_three_models.png`.

Nothing is published in the repository except this section. No INP, ODB, solver file or extraction is committed.

## 20. PLATE-0875-MATERIAL-SENSITIVITY-01 — do the existing material-parameter variants explain the remaining discrepancies? (2026-11-25)

> **Superseded for current research conclusions (§24, 2026-11-26):** the FE / EXP MAC tables of this section, the statement of §20.5 that seven records are explained by no model, and the mean frequency errors of §20.3 taken over records with MAC ≥ 0.50. They were computed with point positions that are wrong along FE X by up to 49.3 mm (§23). The text below is kept as written; §24 gives the values recomputed with the corrected positions.

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** No Abaqus solve and no
ODB extraction was run: only FE packages that already exist were read. Nothing was fitted. No registration,
orientation or material value is selected by MAC. E1 and E2 are **directions of the FE model** (E1 along FE X, E2
along FE Y, placement D, `CONVENTION_ONLY`); they are not verified fibre directions. No FrozenRegistration was
created; the registration guard is unchanged and was not bypassed. M8 GATE NOT_MET, D-077
`NO_GLOBAL_PARAMETER_VALUE` and production Auto-ID BLOCKED are unchanged.

**Short answer.**

- **Shapes.** G12 and a common scaling of E1 = E2 do not change any shape (first-ranked MAC changes ≤ 0.04). A
  difference between E1 and E2 changes exactly two records: record 2 (0.60 → 0.81–0.94) and record 8
  (0.43 → 0.69–0.86). It leaves record 7 at 0.79 and the other eight records where they were.
- **Frequencies.** A lower common E (the archived states H1 and H2, E −22 % and −25 %) brings the mean first-ranked
  frequency error of the six records with a supported shape from 9.2 % to 1.6–1.7 %. The thickness models do not.
- **Material against thickness.** Neither explains more than the other; they act on different things. Thickness
  asymmetry is needed for record 7 (0.96–0.97; no material variant moves it). Records 2 and 8 respond to **any**
  break of the X ↔ Y symmetry, material or thickness, so they do not show which one is present. Records 3, 4, 5, 6,
  9, 10 and 11 are explained by none of the 16 models.
- **Lower bending modes.** Material asymmetry helps one of the five records 2–6 (record 2), as the 20-reading
  thickness field does.

### 20.1 The variants and their identities

All are the baseline `S4R_0875_BASELINE` with one changed `*Elastic` line: the same mesh, thickness 0.875 mm, density,
mass 118.361 g and free-free conditions. Checked for each: the INP differs from the baseline in that one line only;
its parsed constants equal the declared ones; INP SHA-256 = the recorded one; ODB or manifest SHA-256 = the recorded
one; the extraction manifest names its own job's ODB; manifest frequencies = `.dat`; the archived run completed
without error.

| Model | E1 / E2 / G12, MPa | Source | Branches tracked (FE-to-FE MAC ≥ 0.90) | Lost | Order exchanges |
|---|---|---|---|---|---|
| G12 −5 % | 56 000 / 56 000 / 4 750 | PRIORITY-2 | 14 of 14 (min 1.00) | none | none |
| S0: G12 4 763 | 56 000 / 56 000 / 4 763.4 | PRIORITY-4 | 14 of 14 (min 1.00) | none | none |
| G12 +5 % | 56 000 / 56 000 / 5 250 | PRIORITY-2 | 14 of 14 (min 1.00) | none | none |
| G12 ×2 | 56 000 / 56 000 / 10 000 | PRIORITY-1 (R6.6) | 13 of 14 | 19 | 20 → 19 |
| G12 ×3 | 56 000 / 56 000 / 15 000 | PRIORITY-1 (R6.6) | 13 of 14 | 19 | 20 → 19 |
| E1 −5 % | 53 200 / 56 000 / 5 000 | PRIORITY-2 | 14 of 14 (min 0.92) | none | none |
| E1 +5 % | 58 800 / 56 000 / 5 000 | PRIORITY-2 | 9 of 14 | 8, 9, 15, 16, 20 | 10 ↔ 11, 13 ↔ 14, 17 ↔ 18 |
| E2 −5 % | 56 000 / 53 200 / 5 000 | PRIORITY-2 | 9 of 14 | 8, 9, 15, 16, 20 | 10 ↔ 11, 13 ↔ 14, 17 ↔ 18 |
| E2 +5 % | 56 000 / 58 800 / 5 000 | PRIORITY-2 | 14 of 14 (min 0.92) | none | none |
| E1 −10 % | 50 400 / 56 000 / 5 000 | PRIORITY-1 (R6.7) | 9 of 14 | 8, 9, 15, 16, 20 | 14 → 15 |
| E2 −10 % | 56 000 / 50 400 / 5 000 | PRIORITY-1 (R6.7) | 9 of 14 | 8, 9, 15, 16, 20 | 10 ↔ 11, 13 ↔ 14, 17 ↔ 18 |
| H1 | 43 467 / 43 467 / 4 804.4 | PRIORITY-4 | 14 of 14 (min 1.00) | none | none |
| H2 | 41 952.8 / 41 952.8 / 4 810.3 | PRIORITY-4 | 14 of 14 (min 1.00) | none | none |

- **Branch stability.** G12 and the common E scaling keep every shape (FE-to-FE MAC ≥ 0.9996 in S0, H1, H2). A
  difference between E1 and E2 is what breaks branches: the pairs FE 8 / 9 and FE 15 / 16 lose their individual
  identity and FE 20 is lost, while their two-mode subspaces stay (largest principal angle below 0.5°).
- **Reuse.** The tracking recomputed here reproduces the stored tables: 66 rows of PRIORITY-2 and 42 rows of
  PRIORITY-4 agree in frequency to 0.005 Hz and in status. The only difference is a name: PRIORITY-2 calls FE 15 / 16
  one cluster term where this run lists two tracked branches (MAC 0.92). The exchanges and losses of PRIORITY-1 §3
  are reproduced.
- **S0, H1 and H2** are the states of the hypothetical inverse fits of PRIORITY-3 / -4. They are used here only as
  existing FE states with a lower G12 or a lower common E. Their pairings are hypotheses and are not adopted.

### 20.2 Shapes: research MAC with the first-ranked FE mode

Mapping, metric and levels exactly as in §17. The baseline row reproduces §17.3 and §19.5 with difference 0.0. The
two thickness rows are copied from §19 (not recomputed). Bold: ≥ 0.80, the existing level, descriptive only.

| Model | EXP 1 | EXP 2 | EXP 3 | EXP 4 | EXP 5 | EXP 6 | EXP 7 | EXP 8 | EXP 9 | EXP 10 | EXP 11 | Mean 2–6 | Mean 7–8 | Mean all |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | **0.91** | 0.60 | 0.31 | 0.55 | 0.48 | 0.52 | 0.79 | 0.43 | 0.26 | 0.15 | 0.54 | 0.494 | 0.607 | 0.504 |
| G12 −5 % | **0.91** | 0.60 | 0.31 | 0.55 | 0.48 | 0.52 | 0.79 | 0.43 | 0.26 | 0.15 | 0.54 | 0.493 | 0.606 | 0.503 |
| S0: G12 4 763 | **0.91** | 0.60 | 0.31 | 0.55 | 0.48 | 0.52 | 0.79 | 0.43 | 0.26 | 0.15 | 0.54 | 0.493 | 0.606 | 0.503 |
| G12 +5 % | **0.91** | 0.60 | 0.31 | 0.55 | 0.48 | 0.52 | 0.79 | 0.43 | 0.26 | 0.15 | 0.54 | 0.494 | 0.607 | 0.504 |
| G12 ×2 | **0.91** | 0.61 | 0.31 | 0.55 | 0.49 | 0.54 | 0.79 | 0.44 | 0.26 | 0.15 | 0.57 | 0.498 | 0.615 | 0.510 |
| G12 ×3 | **0.91** | 0.61 | 0.31 | 0.55 | 0.49 | 0.55 | 0.79 | 0.45 | 0.26 | 0.15 | 0.58 | 0.501 | 0.621 | 0.514 |
| E1 −5 % | **0.91** | **0.82** | 0.36 | 0.55 | 0.48 | 0.52 | 0.79 | 0.70 | 0.26 | 0.21 | 0.54 | 0.547 | 0.741 | 0.557 |
| E1 +5 % | **0.91** | **0.84** | 0.26 | 0.55 | 0.48 | 0.52 | 0.79 | 0.69 | 0.26 | 0.21 | 0.54 | 0.530 | 0.740 | 0.549 |
| E2 −5 % | **0.91** | **0.84** | 0.26 | 0.55 | 0.48 | 0.52 | 0.79 | 0.71 | 0.26 | 0.21 | 0.54 | 0.532 | 0.746 | 0.552 |
| E2 +5 % | **0.91** | **0.81** | 0.36 | 0.55 | 0.48 | 0.52 | 0.79 | 0.69 | 0.26 | 0.21 | 0.54 | 0.545 | 0.737 | 0.556 |
| E1 −10 % | **0.91** | **0.89** | 0.37 | 0.55 | 0.48 | 0.52 | 0.79 | **0.80** | 0.26 | 0.23 | 0.54 | 0.562 | 0.795 | 0.576 |
| E2 −10 % | **0.91** | **0.94** | 0.28 | 0.55 | 0.48 | 0.52 | 0.79 | **0.86** | 0.26 | 0.24 | 0.54 | 0.556 | 0.823 | 0.579 |
| H1: E −22.4 % | **0.91** | 0.61 | 0.31 | 0.55 | 0.49 | 0.52 | 0.79 | 0.43 | 0.26 | 0.15 | 0.55 | 0.495 | 0.609 | 0.505 |
| H2: E −25.1 % | **0.91** | 0.61 | 0.31 | 0.55 | 0.49 | 0.53 | 0.79 | 0.43 | 0.26 | 0.15 | 0.55 | 0.495 | 0.610 | 0.506 |
| Thickness: wedge, thick at edge 4 (§18) | **0.92** | 0.64 | 0.22 | 0.50 | 0.47 | 0.48 | **0.97** | 0.65 | 0.24 | 0.16 | 0.46 | 0.463 | 0.811 | 0.520 |
| Thickness: field of 20 readings (§19, assumed) | **0.93** | **0.80** | 0.25 | 0.49 | 0.48 | 0.49 | **0.96** | 0.53 | 0.24 | 0.11 | 0.43 | 0.503 | 0.745 | 0.519 |

**What happens inside the near-degenerate pairs.** MAC of the record with the lower and the upper mode of the pair,
and its share in the two-mode subspace (in brackets; a share is not a confirmed cluster).

| Model | EXP 2 in FE 8 / 9: lower / upper (share) | EXP 8 in FE 15 / 16: lower / upper (share) | EXP 7 in FE 13 / 14: E1 branch / E2 branch (share) |
|---|---|---|---|
| Baseline, all G12 variants, H1, H2 | 0.57 / 0.60–0.61 (0.97) | 0.36 / 0.43–0.45 (0.92) | 0.00 / 0.79 (0.79) |
| E1 −5 % | 0.29 / 0.82 (0.97) | 0.14 / 0.70 (0.92) | 0.00 / 0.79 (0.79) |
| E2 +5 % | 0.30 / 0.81 (0.97) | 0.15 / 0.69 (0.92) | 0.00 / 0.79 (0.79) |
| E1 −10 % | 0.16 / 0.89 (0.97) | 0.07 / 0.80 (0.92) | 0.00 / 0.79 (0.79) |
| E1 +5 % | 0.84 / 0.28 (0.97) | 0.69 / 0.14 (0.92) | 0.00 / 0.79 (0.79) |
| E2 −5 % | 0.84 / 0.26 (0.97) | 0.71 / 0.13 (0.92) | 0.00 / 0.79 (0.79) |
| E2 −10 % | 0.94 / 0.08 (0.97) | 0.86 / 0.04 (0.92) | 0.00 / 0.79 (0.79) |

- **The pair share never changes** (0.97, 0.92, 0.79 in all 14 models). A material asymmetry only rotates the two
  FE shapes inside a subspace that already contains the record. With E1 ≠ E2 the two shapes of a pair separate into
  one governed by E1 and one governed by E2; records 2 and 8 resemble the one governed by E2 (FE Y).
- **Both signs give a high MAC.** With E1 < E2 the record resembles the upper mode of the pair (0.81–0.89), with
  E1 > E2 the lower one (0.84–0.94). **The MAC therefore does not show the sign of E1 − E2**, and it rises
  monotonically with the size of the step, so it shows no magnitude either. No sign and no value is chosen.
- **Record 7 is untouched.** It resembles the E2-governed bending shape at 0.79 in every material variant, including
  both signs. Only a thickness gradient along X raises it (0.96–0.97), by concentrating the shape in the thin half.
  A homogeneous material cannot do that: every material variant keeps the mirror symmetries of the plate.
- **Records 4, 5, 6 and 11** do not change by more than 0.04 in any material variant; records 3, 9 and 10 by not
  more than 0.09.

### 20.3 Frequencies: signed error of the first-ranked FE mode

(FE − EXP) / EXP. The FE mode number is the variant's own. A record whose MAC is below 0.50 has no supported
correspondence; its error is shown for completeness only.

| Model | EXP 1 | EXP 2 | EXP 3 | EXP 4 | EXP 5 | EXP 6 | EXP 7 | EXP 8 | EXP 9 | EXP 10 | EXP 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | FE 7: +2.4 % | FE 9: +13.5 % | FE 20: outside | FE 11: +8.0 % | FE 10: −3.2 % | FE 12: +3.8 % | FE 14: +15.5 % | FE 16: +14.0 % | FE 13: −1.0 % | FE 15: −3.0 % | FE 18: +11.7 % |
| G12 −5 % | FE 7: −0.1 % | FE 9: +13.5 % | FE 20: outside | FE 11: +7.3 % | FE 10: −3.8 % | FE 12: +2.7 % | FE 14: +15.5 % | FE 16: +13.7 % | FE 13: −1.0 % | FE 15: −3.2 % | FE 18: +10.9 % |
| S0: G12 4 763 | FE 7: +0.0 % | FE 9: +13.5 % | FE 20: outside | FE 11: +7.3 % | FE 10: −3.8 % | FE 12: +2.8 % | FE 14: +15.5 % | FE 16: +13.7 % | FE 13: −1.0 % | FE 15: −3.2 % | FE 18: +10.9 % |
| G12 +5 % | FE 7: +4.8 % | FE 9: +13.5 % | FE 20: outside | FE 11: +8.7 % | FE 10: −2.5 % | FE 12: +4.9 % | FE 14: +15.5 % | FE 16: +14.2 % | FE 13: −1.0 % | FE 15: −2.7 % | FE 18: +12.4 % |
| G12 ×2 | FE 7: +42.7 % | FE 9: +13.5 % | FE 19: outside | FE 11: +21.3 % | FE 10: +8.8 % | FE 12: +23.1 % | FE 14: +15.5 % | FE 16: +19.1 % | FE 13: −1.0 % | FE 15: +1.6 % | FE 18: +25.5 % |
| G12 ×3 | FE 7: +72.7 % | FE 9: +13.5 % | FE 19: outside | FE 11: +32.8 % | FE 10: +19.2 % | FE 12: +38.8 % | FE 14: +15.6 % | FE 16: +23.8 % | FE 13: −1.0 % | FE 15: +5.8 % | FE 18: +37.3 % |
| E1 −5 % | FE 7: +2.3 % | FE 9: +12.8 % | FE 20: outside | FE 11: +8.0 % | FE 10: −4.9 % | FE 12: +3.1 % | FE 14: +15.5 % | FE 16: +13.3 % | FE 13: −3.5 % | FE 15: −4.6 % | FE 18: +11.4 % |
| E1 +5 % | FE 7: +2.4 % | FE 8: +10.8 % | FE 10: +13.7 % | FE 10: +8.0 % | FE 11: −1.5 % | FE 12: +4.6 % | FE 13: +15.5 % | FE 15: +11.8 % | FE 14: +1.4 % | FE 16: +1.1 % | FE 17: +11.9 % |
| E2 −5 % | FE 7: +2.3 % | FE 8: +8.0 % | FE 10: +11.6 % | FE 10: +6.0 % | FE 11: −3.2 % | FE 12: +3.1 % | FE 13: +12.6 % | FE 15: +9.3 % | FE 14: −1.0 % | FE 16: −1.1 % | FE 17: +9.9 % |
| E2 +5 % | FE 7: +2.4 % | FE 9: +15.6 % | FE 20: outside | FE 11: +9.9 % | FE 10: −3.2 % | FE 12: +4.6 % | FE 14: +18.4 % | FE 16: +15.9 % | FE 13: −1.0 % | FE 15: −2.4 % | FE 18: +13.4 % |
| E1 −10 % | FE 7: +2.3 % | FE 9: +12.5 % | FE 20: outside | FE 11: +7.9 % | FE 10: −6.7 % | FE 12: +2.4 % | FE 15: +15.5 % | FE 16: +13.1 % | FE 13: −6.1 % | FE 14: −6.7 % | FE 18: +11.2 % |
| E2 −10 % | FE 7: +2.3 % | FE 8: +5.6 % | FE 9: −3.9 % | FE 10: +4.0 % | FE 11: −3.2 % | FE 12: +2.3 % | FE 13: +9.6 % | FE 15: +7.0 % | FE 14: −1.0 % | FE 16: −1.5 % | FE 17: +8.1 % |
| H1: E −22.4 % | FE 7: −0.0 % | FE 9: +0.0 % | FE 20: outside | FE 11: −1.9 % | FE 10: −12.0 % | FE 12: −4.1 % | FE 14: +1.8 % | FE 16: +1.6 % | FE 13: −12.8 % | FE 15: −13.5 % | FE 18: +1.5 % |
| H2: E −25.1 % | FE 7: −0.0 % | FE 9: −1.7 % | FE 20: outside | FE 11: −3.0 % | FE 10: −13.1 % | FE 12: −4.9 % | FE 14: +0.0 % | FE 16: −0.0 % | FE 13: −14.3 % | FE 15: −14.9 % | FE 18: +0.3 % |
| Thickness: wedge (§18) | FE 7: +2.0 % | FE 8: +8.7 % | FE 11: +13.6 % | FE 11: +7.9 % | FE 10: −3.8 % | FE 12: +3.3 % | FE 13: +12.5 % | FE 16: +14.3 % | FE 14: −1.6 % | FE 15: −3.0 % | FE 18: +11.2 % |
| Thickness: field (§19) | FE 7: +4.5 % | FE 8: +10.2 % | FE 10: +15.4 % | FE 10: +9.6 % | FE 11: −0.2 % | FE 12: +4.9 % | FE 13: +13.8 % | FE 16: +15.9 % | FE 14: −0.0 % | FE 15: −1.3 % | FE 18: +12.3 % |

- **G12 moves record 1 only** (the twist; +2.4 % → 0.0 % at G12 4 763) and leaves the bending errors at +13…+16 %.
- **E1 ≠ E2 at 5–10 % moves the bending errors by a few per cent.** The E2-reduced variants lower them most
  (records 2, 7, 8: +5.6 %, +9.6 %, +7.0 % at E2 −10 %); none closes them.
- **A common E −22 % to −25 % closes them.** Mean absolute error of the six records whose baseline MAC is at least
  0.50 (records 1, 2, 4, 6, 7, 11): 9.2 % (baseline) → 1.6 % (H1) and 1.7 % (H2). In H1, records 1 and 8 were
  fitted; records 2, 4, 7 and 11 were not and come within ±2 %, record 6 within −4.1 %. In H2, records 1 and 7 were
  fitted; records 2, 8 and 11 come within ±2 %, record 4 within −3.0 % and record 6 within −4.9 %.
- **Three records move the other way.** Records 5, 9 and 10 go to −12…−15 % in H1 and H2. Their MAC is 0.48, 0.26
  and 0.15: their first-ranked modes are not supported correspondences, so this is not evidence against a lower E;
  it shows that these records are unexplained.
- **What a lower E means here.** The weighed mass fixes the areal mass, so a frequency fixes D = E h³ / 12(1 − ν12 ν21)
  and not E. "E −22 %" is one way to write a lower bending stiffness; the thickness cubed could carry part of it,
  and so could an added mass (below). The archived values of H1 and H2 remain `HYPOTHETICAL_PAIRING` and
  `NOT_A_MATERIAL_PROPERTY`; none is adopted or re-derived here.

Figure: `fig_material_sensitivity.png` (§20.7): both tables as heat maps, material and thickness models together.

### 20.4 Material asymmetry against thickness, suspension and sensor

| Effect | FE evidence available | What it changes | What it cannot explain |
|---|---|---|---|
| G12 | 5 variants | the frequency of record 1; no shape | any bending record |
| Common E (E1 = E2), equivalently D | 2 variants (H1, H2) | the frequencies of the bending records with a supported shape; no shape | any shape discrepancy |
| E1 ≠ E2 | 6 variants, both signs | the shapes of records 2 and 8 (rotation inside FE 8 / 9 and FE 15 / 16) | record 7; records 3–6, 9–11; the frequency level |
| Thickness gradient along X | wedge (§18), 20-reading field (§19, assumed) | record 7 (0.96–0.97); records 2 (0.64–0.80) and 8 (0.53–0.65) | records 3–6, 9–11; the frequency level |
| Suspension (two bands) | **none** (the prepared jobs of §14 were never run) | unknown | — |
| Force sensor mass | **none** (its mass and point are not recorded) | unknown | — |

- **Material asymmetry and thickness asymmetry are confounded for records 2 and 8.** Both pairs are near-degenerate
  only because the model is nearly square and balanced. Any effect that distinguishes X from Y splits them the same
  way. A high MAC of record 2 or 8 in an E1 ≠ E2 variant is therefore not evidence for a material asymmetry.
- **They are separable for record 7**, which needs a break of the mirror symmetry. That points to a thickness-type
  (or one-sided mass) asymmetry, not to E1 ≠ E2. It stays a candidate with one orientation of an assumed field.
- **Suspension and sensor cannot be assessed from the archive.** General mechanics limits their direction only: an
  added suspension stiffness can only raise the measured frequencies, so it cannot explain FE frequencies that are
  10–16 % too high; an added sensor mass lowers them and could explain part of what is written above as a lower E.
  The size is unknown without the sensor's mass.
- **Existing experimental indication (PRIORITY-1 §4, not new):** by point id, records 1, 2, 6 and 7 of 261016 and
  261027 have the same shape (0.90, 0.82, 0.97, 0.90) although the suspension changed and the plate was turned 45°,
  while the frequency of record 1 moved from 33.45 to 18.63 Hz. The shapes of these records travel with the plate;
  the frequency of record 1 depends on the setup. Where the excitation was attached in 261027 is not recorded.

### 20.5 Remaining identifiability limitations

1. **No material asymmetry can be identified.** The shapes that respond to E1 ≠ E2 respond equally to a thickness
   asymmetry; the MAC gives neither sign nor size; the partner record of each pair is not identified, so the
   frequency split is not observed either. E1 ≠ E2 also stays blocked by SPEC §5.2 (no traceable material axes).
2. **The stiffness level is visible but not assignable.** The records with a supported shape agree with a bending
   stiffness about a fifth to a quarter below the template, in two archived hypothetical states. It cannot be divided
   between E, thickness and added mass, and it rests on shape correspondences of 0.52–0.91 with an unverified
   registration.
3. **Seven records are explained by no model:** the largest first-ranked MAC over all 16 models is 0.37 (record 3),
   0.55 (4), 0.49 (5), 0.55 (6), 0.26 (9), 0.24 (10) and 0.58 (11).
4. **Candidates are not pairs.** Record 1 informs D66 only. Records 2, 7 and 8 reach 0.80 only in models whose
   distinguishing feature is unverified (assumed thickness field, wedge orientation, unidentified E1 ≠ E2).
5. **Unchanged:** the registration facts of §16.3, the thickness limits of §19.7, D-044, SPEC §6 S4, M8 GATE NOT_MET
   and D-077.

### 20.6 Recommended next minimal step

**A thickness map of the plate, with recorded positions. No modal test and no FE run is needed for it.**

- **What:** the thickness at 9 or more interior points and again at the 20 edge points, each with its measured
  position, the edge numbers 1–4 and the marked face noted on the sheet. If available at the same time: the mass of
  the force sensor and where it was attached in 261027.
- **Why this and not a computation:** every open question above ends at the same unmeasured quantity.
  - It is the only way to separate the two explanations of records 2 and 8: thickness can be measured, E1 ≠ E2
    cannot.
  - It decides whether the gradient that explains record 7 exists in the plate, and on which side.
  - It fixes the placement of the FE model on the plate by construction (§16.3), which no MAC may do.
  - It turns the bending-stiffness level into a statement about E instead of E h³.
- **The first computation after it (one solve, separate authorisation):** the baseline with the measured thickness
  and unchanged constants, compared exactly as in §19. Only if records 2 and 8 then remain mixtures is an E1 ≠ E2
  variant of that model justified.
- **Without a new measurement** no further computation is justified by the present data: the archive of material
  variants is exhausted by this section, and another thickness or material variant could only be chosen by its
  effect on MAC or frequency, which is excluded.

### 20.7 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `654db699…` and a clean tracked tree before the edit |
| Input hashes | experiment, nominal geometry, R6 package and the results of §17 (`f8e2d80d…`) and §19 (`61947357…`) equal their recorded hashes; 281 input files have the same size and mtime before and after |
| FE variant identities | 13 of 13: INP hash, ODB or manifest hash, one changed line, parsed constants, own ODB named by the manifest, manifest = `.dat`, completed run (§20.1) |
| Branch tracking | one-to-one assignment; the stored PRIORITY-2 and PRIORITY-4 tables reproduced (108 rows, ≤ 0.005 Hz); PRIORITY-1 exchanges and losses reproduced |
| Research MAC reproducibility | baseline = §17.3 = §19.5 with difference 0.0; identical shapes 1.0; scale and sign ≤ 3.3e-16; in-process repeat 0.0; two complete runs give byte-identical `results.json` and CSV; 289 of 289 points mapped in all 59 scenarios |
| Tests | `research/m11_r65`: 29 OK. `tests.test_plate_registration_readiness`, `tests.test_plate_rc1_owner_clarification`, `tests.test_plate_study`: 60 OK |

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_MATERIAL_SENSITIVITY_01` (outside git):
`run_material_sensitivity.py`, `protocol.json`, `results.json` (`35189ace…`), `mac_nominal_all.npz`,
`material_sensitivity_summary.csv`, `report.py`, `fig_material_sensitivity.png`.

Nothing is published in the repository except this section and the corrected opening statement.

## 21. PLATE-0875-EXPERIMENTAL-MODE-QUALITY-01 — are the poorly matched experimental records supported by the response data? (2026-11-25)

> **Superseded for current research conclusions (§24, 2026-11-26):** the reading of the low FE MAC of records 5, 6, 9, 10 and 11 as a discrepancy of the FE model (already qualified in §22.9); the experimental quantities of this section are not affected. They were computed with point positions that are wrong along FE X by up to 49.3 mm (§23). The text below is kept as written; §24 gives the values recomputed with the corrected positions.

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** Experimental data only:
no FE frequency, shape or MAC enters any diagnostic or label of this section. No Abaqus solve and no ODB extraction
was run. Nothing was fitted to a material parameter. All 11 records are kept: none is excluded, weighted or
re-selected, and no pole is added, removed or moved. No coherence or uncertainty value is invented. No
FrozenRegistration was created. M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production Auto-ID BLOCKED are
unchanged.

**Short answer.**

- **The fitted records are what the response data contain.** With the 11 stored poles held fixed, a refit of the
  residues to the stored transfer functions returns the stored shapes (MAC ≥ 0.998 for all 11).
- **Ten of the eleven records have a clear resonance.** A peak of 10–43 dB within one spectral line, and a response
  shape at that line equal to the fitted shape (MAC 0.93–1.00). The exception is record 4.
- **Of the seven records that no FE model explains (3, 4, 5, 6, 9, 10, 11):**
  - records 5, 6, 9, 10 and 11 are supported by the response data without a limitation of the shape;
  - record 3 is supported, with a low coherence at its peak (0.88);
  - record 4 has weak support: a 4 dB shoulder beside record 3, with the highest damping of the low records.
- **So the response data give no indication that the FE discrepancy of records 5, 6, 9, 10 and 11 is an artefact of
  the modal fit. They do not exclude it** (amended by §22.9: response support and a refit with fixed poles do not
  validate the poles). The other candidate causes are the FE model and the FE-to-scan mapping; §22.4 points to the
  mapping.
- **A pattern that the earlier sections did not use.** Four records are bending in one grid direction only: records 2
  and 7 along one grid index, records 3 and 9 along the other. The second group lies 16 % higher in frequency, in
  both orders. This is a hypothesis about a direction-dependent bending stiffness (§21.5); it is not a material value.

### 21.1 Inputs and what the response file contains

| Input | Content | SHA-256 |
|---|---|---|
| Fitted records 261027 | `…ROTATED_Polytec_261027.unv`, set `Polymax_bravo`: 11 records, 289 points, U3, complex as stored; poles from the dataset-55 headers | `76db80ae…` = recorded |
| Response data 261027 | `…ROTATED_261027.unv` (PSV export of the same session, acquired 27-Oct-26 11:38:17), dataset 58, 867 records | `d3bc99e9…` = recorded |
| History 261016 | `…261016_POLYMAX.unv`, set `Polymax_bravo`: 10 records. Supplementary only | `117c893b…` = recorded |

The response file was inspected before any use (the task requires the quantities and units to be verified first):

| Function (as stored) | Type | Ordinate | Records | Abscissa |
|---|---|---|---|---|
| `Transfer Function H1`, "H1 Velocity / Force" | 4 (frequency response function), complex | Velocity, m/s, over Force, N | 289 | 0.3125 … 500 Hz, 1600 lines of 0.3125 Hz |
| `Coherence` | 6, real | dimensionless, 9.5e-6 … 1.0 | 289 | the same |
| `Cross Spectrum`, "CP Force * Velocity" | 3, complex | N · m/s | 289 | the same |

- **It is a transfer function.** The records are H1 mobilities (velocity per force) with a stored coherence, one per
  scan point, response direction 3, one force reference. They may be read as FRFs. The phase of each H1 equals the
  phase of its cross spectrum (largest difference 6.7e-6 rad over 179 378 cells), as H1 = G_fv / G_ff requires.
- **Same points.** The node tables of the fitted file and of the response file are identical (289 ids; relative rms
  2e-16 after a similarity fit, scale 1.0). Point id k ↔ id k is used.
- **PolyMAX band.** The fitted file stores residual terms below 14.90 Hz and above 240.95 Hz: the fit covered that
  band. Damping ratios are stored for all 11 records (record 11 too, which the workbook does not list).
- **Not in the file.** The number of averages, the window, the excitation signal and position, and any uncertainty
  of a frequency, damping or shape. None is assumed.

### 21.2 Method

The protocol (`protocol.json`) was written before any diagnostic was computed. Two descriptors were added after the
first results and are marked as such in the protocol (the grid pattern of §21.5 and the span check of §21.4); they
change no label.

- **Resonance.** Indicator S(f) = Σ |H1|² over the 289 points. For each record: the nearest local maximum within
  ± 3 lines and its prominence in dB.
- **Coherence.** The stored coherence at that line: |H1|²-weighted mean, median, and share of points below 0.9.
- **Damping and resolution.** Stored ζ; bandwidth 2ζf in lines; half-power damping of the indicator
  (`universal_reader._estimate_half_power_damping`).
- **Phase.** Modal phase collinearity (`experimental_qc._phase_collinearity`); a metric without a limit.
- **Response shape.** H1 at the peak line, and the first singular shape of H1 over ± 8 lines; complex MAC with the
  fitted record.
- **Refit.** Linear least squares of H1 in 15–200 Hz with the 11 stored poles fixed, free residues, and one lower
  and one upper residual per point.
- **Distinctness.** Complex AutoMAC of the 11 records.
- **Levels (descriptive, no gate).** Coherence 0.9, AutoMAC 0.5 and 3 lines are the existing SPEC §6 S1 flag levels;
  MAC 0.80 is the level used in §17; 3 dB of prominence and 0.90 of the window energy are declared here.
- **Labels.** *Supported*: peak ≥ 3 dB, coherence ≥ 0.9, window-shape MAC ≥ 0.80 and AutoMAC ≤ 0.5. *Supported, with
  limitation*: peak and shape, but not the coherence or the AutoMAC. *Weak support*: no such peak, or no such shape.
  Marks: *mixed indication* (AutoMAC > 0.5, or one shape carries < 0.90 of the window energy, or the window shape
  has MAC ≥ 0.5 with another record) and *unresolved* (bandwidth < 3 lines).

### 21.3 Experimental quality of the 11 records

Records in bold are the seven that no FE model of §17–§20 explains.

| Record | Hz | Peak of the response: Hz (prominence) | Coherence at the peak: weighted / median (points < 0.9) | ζ stored, % | Bandwidth, lines | MPC | MAC of the response shape with the record: peak line / window | Refit MAC | Largest AutoMAC | Label |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 18.63 | 18.75 (13 dB) | 0.998 / 0.999 (0 %) | 0.189 | 0.2 | 0.918 | 0.93 / 0.95 | 0.998 | 0.01 | supported; mixed indication, unresolved |
| 2 | 54.62 | 54.69 (21 dB) | 0.986 / 0.988 (0 %) | 0.394 | 1.4 | 0.987 | 1.00 / 1.00 | 1.000 | 0.02 | supported; unresolved |
| **3** | 63.50 | 63.44 (43 dB) | 0.881 / 0.902 (49 %) | 0.159 | 0.6 | 0.927 | 0.99 / 1.00 | 1.000 | 0.04 | supported, with limitation; unresolved |
| **4** | 66.85 | 67.19 (4 dB) | 0.998 / 0.999 (0 %) | 0.923 | 3.9 | 0.903 | 0.90 / 0.60 | 1.000 | 0.04 | weak support; mixed indication |
| **5** | 74.21 | 74.06 (18 dB) | 0.997 / 0.997 (0 %) | 0.271 | 1.3 | 0.994 | 0.99 / 1.00 | 1.000 | 0.01 | supported; unresolved |
| **6** | 112.27 | 112.19 (22 dB) | 0.995 / 0.995 (0 %) | 0.640 | 4.6 | 0.997 | 1.00 / 1.00 | 1.000 | 0.01 | supported |
| 7 | 145.94 | 145.94 (11 dB) | 0.996 / 0.997 (0 %) | 0.783 | 7.3 | 0.977 | 0.99 / 0.99 | 1.000 | 0.01 | supported |
| 8 | 157.85 | 157.81 (35 dB) | 0.871 / 0.899 (50 %) | 0.102 | 1.0 | 0.956 | 0.99 / 1.00 | 1.000 | 0.00 | supported, with limitation; unresolved |
| **9** | 169.18 | 169.06 (12 dB) | 0.999 / 0.999 (0 %) | 0.300 | 3.2 | 0.993 | 0.98 / 0.98 | 0.999 | 0.00 | supported |
| **10** | 180.14 | 180.00 (25 dB) | 0.980 / 0.985 (0 %) | 0.064 | 0.7 | 0.993 | 1.00 / 1.00 | 1.000 | 0.01 | supported; unresolved |
| **11** | 191.60 | 191.56 (10 dB) | 0.992 / 0.995 (0 %) | 0.809 | 9.9 | 0.979 | 0.99 / 0.99 | 0.999 | 0.01 | supported |

Further diagnostics of the same records:

| Record | Window energy in one shape | Second window shape | Half-power ζ of the indicator, % (ratio to stored) | Synthesis error near the record | Roughness | Nearest 261016 record (MAC) |
|---|---|---|---|---|---|---|
| 1 | 0.719 | rigid plane 0.98 | 1.081 (5.7) | 0.15 | 0.001 | #1, 33.45 Hz (0.90) |
| 2 | 0.980 | like record 3 (0.56) | 0.372 (0.9) | 0.13 | 0.001 | #2, 55.25 Hz (0.82) |
| **3** | 0.934 | like record 4 (0.89) | 0.235 (1.5) | 0.33 | 0.011 | #3, 68.10 Hz (0.68) |
| **4** | 0.843 | like record 3 (0.69) | 0.810 (0.9) | 0.42 | 0.002 | #4, 71.96 Hz (0.48) |
| **5** | 0.970 | like record 4 (0.56) | 0.427 (1.6) | 0.10 | 0.001 | #5, 80.47 Hz (0.71) |
| **6** | 0.995 | like record 7 (0.19) | 0.694 (1.1) | 0.10 | 0.001 | #6, 116.90 Hz (0.97) |
| 7 | 0.987 | like record 8 (0.65) | 1.347 (1.7) | 0.23 | 0.002 | #7, 144.60 Hz (0.90) |
| 8 | 0.974 | like record 7 (0.07) | 0.115 (1.1) | 0.18 | 0.009 | #8, 158.84 Hz (0.70) |
| **9** | 0.961 | like record 8 (0.41) | 0.656 (2.2) | 0.34 | 0.002 | none: best is #8 (0.10) |
| **10** | 0.981 | like record 11 (0.66) | 0.132 (2.1) | 0.10 | 0.003 | #9, 178.04 Hz (0.82) |
| **11** | 0.993 | like record 10 (0.43) | 1.593 (2.0) | 0.22 | 0.002 | none: best is #7 (0.01) |

- **Roughness** is the share of a shape's energy in point-to-point variation (2-D cosine terms of index 9 or more on
  the 17 × 17 grid). It is at most 1.1 %: the shapes are spatially smooth.
- **Synthesis error** is the relative difference between the measured H1 and the 11-pole model within ± 5 lines; over
  15–200 Hz it is 0.25. The stored poles reproduce the shapes exactly but not the full response level: narrow peaks
  are sampled by one to three lines.
- **Response without a fitted record.** No peak of 3 dB or more in 15–200 Hz lacks a record. The existing detector
  lists five minor ones: 59.4 Hz (1.3 dB), 76.6 Hz (2.8 dB; shape like record 5, MAC 0.92), 82.2 Hz (0.8 dB),
  122.2 Hz (2.9 dB; shape like record 6, MAC 0.84) and 125.0 Hz (0.6 dB). Below the PolyMAX band there are peaks at
  3.1, 10.3 and 12.5 Hz (6, 22 and 7 dB), as §3 reported.
- **Coherence elsewhere.** A dip at 150.0 Hz (0.87) and a smaller one at 50.0 Hz coincide with no record.

### 21.4 Session 261016 as a supplementary view

Session 261016 used another suspension, another excitation and another scan (§12.4, §13.2). It is not a repeat, and
its records are compared on the same point ids only (id k ↔ id k, DERIVED).

- **Records 1–8 have a 261016 record in the same order** (MAC 0.90, 0.82, 0.68, 0.48, 0.71, 0.97, 0.90, 0.70), and
  record 10 has one (#9, 0.82). Records 9 and 11 have none in the 261016 fitted set; that set has ten records, and it
  does not show whether such modes were absent or not fitted.
- **Record 6** recurs almost exactly (0.97, at 116.90 Hz against 112.27 Hz).
- **Records 3 and 4.** In 261016, #3 (68.10 Hz) and #4 (71.96 Hz) are each nearly pure in one parity class of the
  grid (0.98 and 0.84). In 261027, records 3 and 4 each contain both classes (§21.5). Each lies about three quarters
  in the span of the two 261016 shapes (0.77 and 0.74).
- **Caution.** 261016 #4 and #5 have low phase collinearity (0.59 and 0.44).

### 21.5 Spatial patterns on the scan grid

The descriptors use the grid's own two indices, called u and v here. They refer to no plate edge and no FE axis.
"Parity" is the symmetry (S) or antisymmetry (A) of the shape about the two centre lines of the grid.

| Record | Hz | Share varying along u only (sign changes) | Along v only (sign changes) | Parity SS / AS / SA / AA |
|---|---|---|---|---|
| 1 | 18.63 | 0.01 | 0.01 | 0.00 / 0.00 / 0.00 / **0.99** |
| 2 | 54.62 | **0.98** (2) | 0.01 | **0.98** / 0.00 / 0.02 / 0.00 |
| **3** | 63.50 | 0.01 | **0.72** (2) | 0.72 / 0.01 / 0.27 / 0.00 |
| **4** | 66.85 | 0.01 | 0.42 (2) | 0.43 / 0.00 / 0.57 / 0.00 |
| **5** | 74.21 | 0.01 | 0.00 | 0.00 / **0.99** / 0.00 / 0.00 |
| **6** | 112.27 | 0.00 | 0.00 | **1.00** / 0.00 / 0.00 / 0.00 |
| 7 | 145.94 | **0.80** (3) | 0.00 | 0.00 / 0.80 / 0.00 / 0.19 |
| 8 | 157.85 | 0.17 | 0.00 | 0.00 / 0.17 / 0.00 / 0.82 |
| **9** | 169.18 | 0.00 | **0.99** (3) | 0.00 / 0.01 / **0.99** / 0.00 |
| **10** | 180.14 | 0.00 | 0.00 | 0.00 / 0.01 / 0.00 / **0.98** |
| **11** | 191.60 | 0.01 | 0.01 | 0.00 / **0.97** / 0.01 / 0.01 |

- **Nine records lie in one parity class** (share 0.80–1.00). Records 3 and 4 share two classes between them.
- **Four records are bending in one grid direction.** Records 2 and 7 vary along u only, with two and three nodal
  lines. Records 3 and 9 vary along v only, with two and three nodal lines (record 3 only to 0.72).
- **Their frequencies.** 145.94 / 54.62 = 2.672 and 169.18 / 63.50 = 2.665; a free uniform beam gives 2.757 between
  its first two bending modes. Between the directions: 63.50 / 54.62 = 1.163 and 169.18 / 145.94 = 1.159.
- **In 261016** the u-only records are #2 (55.25 Hz, 0.84) and #7 (144.60 Hz, 0.76), and the v-only record is #3
  (68.10 Hz, 0.88): 68.10 / 55.25 = 1.233. No second v-only record was fitted there.

### 21.6 Verified findings and hypotheses

**Verified** (computed from the stored data; reproducible):

1. The auxiliary file holds H1 mobilities with coherence for the same 289 points (§21.1).
2. The fitted shapes are the residues of that response at the stored poles (refit MAC ≥ 0.998). This does not
   validate the poles themselves (§22.9).
3. Ten records have a peak of 10 dB or more within one line; record 4 has 4 dB, one line away.
4. The response shape at the peak equals the fitted shape for nine records (0.98–1.00); 0.93 for record 1 and 0.90
   for record 4.
5. The weighted coherence at the peak is 0.98 or more for nine records, and 0.88 and 0.87 for records 3 and 8.
6. The 11 shapes are mutually distinct (largest AutoMAC 0.04) and spatially smooth.
7. Six records (1, 2, 3, 5, 8, 10) are narrower than three spectral lines.
8. Records 2 and 7, and records 3 and 9, are one-direction bending patterns in the two grid directions, with the
   frequency ratios of §21.5.
9. The file gives no uncertainty for any frequency, damping or shape.

**The seven poorly matched records:**

| Record | Experimental support | What the FE discrepancy can therefore be |
|---|---|---|
| 5, 6, 10, 11 | supported; clean phase (MPC 0.98–1.00); 5, 6 and 10 recur in 261016 | no indication of a fit artefact, which is not excluded (§22.9); FE model or mapping (§22.4) |
| 9 | supported; MPC 0.99; pure one-direction pattern; no 261016 counterpart | the same; see hypothesis H4 |
| 3 | supported, with low coherence at a very narrow peak; shares two parity classes with record 4 | possibly a mixed mode (H1); otherwise as above |
| 4 | weak: a 4 dB shoulder, ζ 0.92 %, window shape dominated by record 3 | possibly a mixed mode or a measurement limitation (H1) |

**Hypotheses** (not verified; nothing is selected or released on their basis):

- **H1. Records 3 and 4 are a coupled pair.** Two patterns that are separate in 261016 appear mixed in both 261027
  records, and record 4 is the most damped low record. A coupling through the suspension or the force sensor would
  do this. The data do not show the cause.
- **H2. The low coherence at records 3 and 8 is a resolution effect.** They are the two sharpest peaks (43 and
  35 dB; 0.6 and 1.0 lines wide), and the weighted coherence is below 0.9 at the peak line only (0.96–0.99 one line
  away). The number of averages and the window are unknown, so this is not verified.
- **H3. Records 7, 9 and 11 have response beside the fitted pole.** These three are resolved (3–10 lines), and the
  indicator's half-power width is 1.7–2.2 times the stored bandwidth. A single shape still carries 0.96–0.99 of the
  energy. For the unresolved records the same ratio only reflects the line spacing.
- **H4. The bending stiffness differs between the two grid directions.** If records 2, 7 and 3, 9 are beam-like
  bending of a plate with equal sides (301 and 300 mm change a frequency by 0.7 %), the ratio 1.16 of the frequencies
  corresponds to a ratio of about 1.35 of the bending stiffnesses.
  - It agrees with the frequency pattern of §20.3: a common reduction of E by 22–25 % closes the errors of records 2
    and 7 and opens those of record 9, and the unreduced model is within about 1 % of record 9.
  - No archived FE variant has such a difference; the largest is 10 % (§20.1).
  - The cause is not determined. A different in-plane stiffness of the laminate, an initial curvature of the thin
    plate and the suspension would each produce it. The layup is not recorded (§15).
  - The ratio is 1.23 in 261016, so it is not a constant of the specimen alone.
  - It is not a material value, and no direction of the FE model is assigned to u or v here.
- **H5. The remaining discrepancies of records 5, 6, 10 and 11 follow from the same cause.** Untested.

### 21.7 Limitations

- One force reference: closely spaced modes cannot be separated by a multi-reference indicator.
- Line spacing 0.3125 Hz; six records are narrower than three lines, so their damping and peak level are weakly
  supported by the response data. Their frequencies and shapes are not affected in the same way.
- No averages, window, excitation position, sensor mass or uncertainty in the files.
- The labels describe support by the response data. They are not acceptance: `PHYSICAL_REGISTRATION_NOT_VERIFIED`
  stands, and no record becomes an identification row.

### 21.8 Recommended next minimum step

**A pattern-class comparison of the existing FE packages with the experiment; no solve and no extraction.**

- **What.** Apply the grid descriptors of §21.5 (one-direction share, nodal-line count, parity) to the sampled shapes
  of the 16 existing FE models of §17–§20, and compare frequencies class by class: first and second bending in each
  direction, and the parity class of the other records.
- **Why this first.**
  - It tests H4 with data that already exist, and shows whether the FE variants with E1 ≠ E2 already contain the two
    one-direction bending branches.
  - A class is far less sensitive to the unverified point registration than a point-by-point MAC.
  - It gives a per-direction frequency error, which is the quantity an effective bending stiffness per direction
    needs.
- **Then, only on a separate owner authorisation:** one FE solve with a direction-dependent stiffness whose ratio is
  stated beforehand from the experimental frequency ratio alone, with the expected classes and frequencies written
  before the solve. That is a test of one hypothesis, not a fit.
- **Not recommended now.** Any further thickness or material variant chosen by its effect on MAC or frequency.

### 21.9 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `1efdb0b6…` and a clean tracked tree before the edit |
| Input identities | the three inputs equal their recorded SHA-256; size and mtime are the same before and after |
| Response quantities | function type, ordinate labels and units read from every one of the 867 records; one signature per function; H1 phase = cross-spectrum phase |
| Existing diagnostics | the MPC of the 11 records equals §3 and §12.4 (0.918, 0.987, 0.927, 0.903, …); record frequencies equal §3; the low peaks at 10.3 and 12.5 Hz equal §3 (the lowest is at 3.1 Hz here and 3.4 Hz in §3, which used the smoothing detector) |
| Reproducibility | two complete runs give byte-identical `results.json` (`5d93fa1e…`) and `arrays.npz` (`12975ecb…`) |
| Tests | `tests.test_experimental_qc`: 27 OK (4 skipped). `tests.test_frf_import`: 6 OK. `tests.test_plate_study`: 30 OK. `tests.test_polymax_modal_sets`: 17 OK |

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_EXPERIMENTAL_MODE_QUALITY_01` (outside git):
`run_mode_quality.py`, `unv58.py`, `protocol.json` (`40287e89…`), `results.json`, `arrays.npz`, `report.py`,
`fig_response_support.png`, `fig_shapes.png`.

Nothing is published in the repository except this section.

## 22. PLATE-0875-DIRECTIONAL-STIFFNESS-01 — the directional bending stiffness hypothesis against the existing FE results (2026-11-25)

> **Superseded for current research conclusions (§24, 2026-11-26):** the window descriptors of §22.3, the nodal-line control and its MAC table of §22.4, and the expected MAC lists of §22.8; §22.2, §22.5, §22.6 and the falsification criteria are not affected. They were computed with point positions that are wrong along FE X by up to 49.3 mm (§23). The text below is kept as written; §24 gives the values recomputed with the corrected positions.

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** No Abaqus solve and no
ODB extraction was run: only the 16 existing FE packages and the fitted 261027 records were read. Nothing was fitted.
No orientation, mapping or material value is selected by MAC or by frequency. No pairing is confirmed and no material
property is released. "X" and "Y" are **directions of the FE model** under placement D (`CONVENTION_ONLY`); E1 and E2
are effective bending quantities of a homogeneous shell, not verified fibre directions and not laminate constants. No
FrozenRegistration was created. M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production Auto-ID BLOCKED are
unchanged.

**Short answer.**

- **The frequency pattern of all 11 records agrees with one direction-dependent bending stiffness.** In the baseline,
  the FE modes governed by curvature along FE Y are 8–16 % too high, the modes governed by curvature along FE X are
  0–3 % too low, and the two modes governed by neither are 2–4 % too high.
- **Neither the plan nor the thickness can produce it.** 301 × 300 mm gives 0.7 %, in the opposite direction. The two
  thickness models give 1.4–1.8 %. The experiment shows 16 %.
- **A ratio of 1.37 between the two bending stiffnesses is what the experimental frequencies imply.** A reduced-basis
  expectation for E1 = 56 000, E2 = 41 000 MPa (not a solve) puts every record within 4.4 % of the FE mode of its
  class, and gives the experimental order of the classes, which none of the 16 archived models does.
- **The cause is not identified.** A laminate has different bending stiffnesses in two directions even when its
  in-plane moduli are equal; an initial curvature or the suspension would act similarly. This is not a material value.
- **A second finding, about the mapping, not about the stiffness.** The nodal lines of records 3 and 9 do not fit the
  nominal scan window along FE X (215 mm). They fit a grid that covers about 294 mm, as along Y. With such a grid
  (a control, not adopted) four of the seven "unexplained" records reach a research MAC of 0.96–1.00 with the
  unchanged baseline, and a fifth reaches 0.92 once E1 ≠ E2. The owner has to decide how this conflict with the 261016 reconstruction is resolved (§22.4).
- **The conclusion of §21 is qualified** (§22.9): response support and a refit with fixed poles do not validate the
  poles and do not exclude modal-fit errors.

### 22.1 Inputs and method

| Input | Content | SHA-256 |
|---|---|---|
| Experiment 261027 | `…ROTATED_Polytec_261027.unv`, set `Polymax_bravo`, 11 records, 289 points | `76db80ae…` = recorded |
| FE, 16 models | baseline; the 13 material variants of §20.1; the wedge thick at edge 4 (§18); the 20-reading field (§19) | INP, ODB or manifest and extraction files = recorded (§18–§20) |
| Nominal geometry | `plate_reconstruction_W301xH300.json` (261016, diagnostic) | `09be8b88…` = recorded |
| Earlier results | §18 `1fd0965e…`, §19 `61947357…`, §20 `35189ace…`, §21 `5d93fa1e…` | = recorded |

- **Descriptor.** The function of §21.5 (`run_mode_quality.grid_pattern`), imported and unchanged: the share of a
  shape's energy that varies along one grid index only, the sign changes of that mean profile, and the parity shares
  about the two centre lines.
- **Two coverages for FE.** *Window*: FE U3 sampled at the 289 nominal points (mapping of §17) on the 17 × 17 grid.
  *Whole plate*: FE U3 on its own 101 × 101 node grid, which needs no assumption about the scan.
- **Classes.** One-direction bending: share ≥ 0.70 along one axis with two (order 1) or three (order 2) sign changes
  on the whole plate. Parity class: the largest of SS / AS / SA / AA; the first letter refers to FE X.
- **Protocol.** `protocol.json` was written before the first run. Three parts were added after the first results and
  are marked post hoc in `protocol_addendum.json`: the nodal-line check with its control geometry (§22.4), the
  reduced-basis expectation (§22.8) and the class-order table (§22.6).

### 22.2 Axis convention

A least-squares affine map from the grid indices of §21 to the nominal positions of the same point ids, which under
placement D are FE coordinates:

| Grid index of §21 | One step in FE X, Y (mm) | Runs along | §16 |
|---|---|---|---|
| u | −0.02, +17.80 | FE +Y | grid +u → FE +Y: equal |
| v | −13.40, −0.03 | FE −X | grid +v → FE −X: equal |

- Residual of the map: rms 0.31 mm, max 0.65 mm. Point ids fall by 1 per step along u and by 17 per step along v.
- **"Varies along u" in §21.5 therefore means curvature along FE Y**, the direction from edge 3 to edge 1 (the
  300 mm sides). "Varies along v" means curvature along FE X (the 301 mm sides).
- This is a check of a convention against the records of §16. It is not a physical registration.
- With these axes the experimental descriptors of §21.5 are reproduced exactly (difference 0.0).

### 22.3 The descriptor on synthetic directional shapes

Free-free beam functions on the whole plate grid and at the nominal points. Sign changes in brackets.

| Shape | Whole plate: X share, Y share, parity | Nominal window: X share, Y share, parity |
|---|---|---|
| X, order 1 | 1.00 (2), 0.00, SS 1.00 | 1.00 (2), 0.29, SS 0.88 |
| Y, order 1 | 0.00, 1.00 (2), SS 1.00 | 0.00, 1.00 (2), SS 1.00 |
| X, order 2 | 1.00 (3), 0.00, AS 1.00 | 1.00 (**2**), 0.00, AS **0.84** |
| Y, order 2 | 0.00, 1.00 (3), SA 1.00 | 0.00, 1.00 (3), SA 1.00 |
| 0.8 X1 + 0.6 Y1 | 0.64 (2), 0.36 (2), SS 1.00 | 0.53 (2), 0.61 (2), SS 0.94 |
| X1 + Y1 | 0.50, 0.50, SS 1.00 | 0.39, 0.72, SS 0.95 |
| Twist | 0.00, 0.00, AA 1.00 | 0.00, 0.04, AA 0.96 |

- **On the whole plate the descriptor returns the direction, the order and the parity exactly**, and the shares of a
  mixture are the squares of its coefficients. Exchanging the axes exchanges the outputs.
- **The nominal window changes the result along X only.** It covers X = 56.4–271.8 mm of 301 mm, 13.7 mm off centre,
  and Y = 7.0–292.2 mm of 300 mm. An order-2 shape along X then shows two sign changes instead of three, and a parity
  purity of 0.84. A constant offset inside the window is counted as "Y share" (0.29 for X1), so window shares do not
  add to one.
- **Consequence.** Classes are taken from the whole plate for FE. Window values are reported beside them.

### 22.4 Scan coverage: what the nodal lines say

Zero crossings of the mean profiles of the four one-direction records, in grid steps (0 … 16), against the nodal
lines of the FE modes of the same class on the whole plate (order 2 from the baseline; order 1 from the mean of the
E1 −10 % and E2 −10 % variants, where the classes are separated).

| Record | Class | Nodal lines, grid steps | As a fraction of the grid | FE nodal lines, fraction of the side | Implied grid step, mm | Where the nominal mapping puts these lines, mm | FE nodal lines, mm |
|---|---|---|---|---|---|---|---|
| 2 | Y, order 1 | 3.45, 12.48 | 0.216, 0.780 | 0.224, 0.776 | 18.3 | 68.5, 229.4 | 67.2, 232.8 |
| 7 | Y, order 2 | 1.96, 8.02, 14.07 | 0.123, 0.502, 0.879 | 0.132, 0.500, 0.868 | 18.2 | 42.0, 150.0, 257.8 | 39.6, 150.0, 260.4 |
| 3 | X, order 1 | 3.65, 12.61 | 0.228, 0.788 | 0.224, 0.776 | 18.6 | **105.6, 226.1** | 67.5, 233.5 |
| 9 | X, order 2 | 1.94, 7.96, 14.04 | 0.121, 0.497, 0.877 | 0.132, 0.500, 0.868 | 18.3 | **82.5, 163.5, 245.4** | 39.8, 150.5, 261.2 |

| Direction | Fitted from the five nodal lines | Nominal mapping (261016 reconstruction) |
|---|---|---|
| FE X | step 18.39 mm; X = 2.7–296.9 mm (294.2 mm); residual rms 1.5 mm | step 13.46 mm; X = 56.4–271.8 mm (215.4 mm) |
| FE Y | step 18.27 mm; Y = 3.9–296.3 mm (292.4 mm); residual rms 0.6 mm | step 17.82 mm; Y = 7.0–292.2 mm (285.2 mm) |

- **Verified.** In grid steps the nodal lines of the X records and of the Y records lie at the same places. Along Y
  the nominal mapping agrees with them (within 3.4 mm). Along X it does not: it would put the three nodal lines of
  record 9 at 82, 164 and 245 mm, 81 mm apart, where a free bending shape of the 301 mm side has them 111 mm apart.
- **Hypothesis, not adopted.** If records 3 and 9 are free bending of the whole 301 mm side, the 261027 grid covers
  about 294 mm along X, not 215 mm. If the nominal window is right, records 3 and 9 are not such modes, and the
  premise of the directional hypothesis fails for that direction. The data of this section cannot decide between
  the two by themselves; the next two points bear on it.
- **Session 261016, supplementary.** The same computation gives 17.7 and 17.8 mm per step along Y (#2, #7), equal
  to the reconstruction, and 18.8 mm along X (#3), against 13.46 mm. The one X record of 261016 disagrees with the
  reconstruction in the same way.
- **Control geometry `NODAL_LINE_GRID`.** The 289 points on the fitted axis-parallel grid; all inside the plate
  (nearest edge 2.7 mm); 28.5 mm rms and 55.2 mm maximum from the nominal positions. It was fixed from the nodal lines
  before any MAC with it was computed. It is a control like `UNV_REPRESENTATION_CONTROL` of §17.5: **not a
  registration, not adopted, and not selected by MAC or frequency.** Records 2, 3, 7 and 9 enter its construction;
  records 1, 4, 5, 6, 8, 10 and 11 do not.

Research MAC of each record with its first-ranked FE mode, nominal mapping → control geometry:

| Model | EXP 1 | EXP 2 | EXP 3 | EXP 4 | EXP 5 | EXP 6 | EXP 7 | EXP 8 | EXP 9 | EXP 10 | EXP 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline, nominal (§17.3) | 0.91 | 0.60 | 0.31 | 0.55 | 0.48 | 0.52 | 0.79 | 0.43 | 0.26 | 0.15 | 0.54 |
| Baseline, control | 0.97 | 0.52 | 0.45 | 0.56 | **0.99** | **1.00** | 0.80 | 0.43 | **0.99** | 0.57 | **0.96** |
| E2 −10 %, control | 0.97 | 0.92 | 0.62 | 0.56 | 0.99 | 1.00 | 0.80 | 0.76 | 0.99 | **0.92** | 0.96 |
| Wedge (§18), control | 0.97 | 0.54 | 0.40 | 0.57 | 0.99 | 0.99 | 0.97 | 0.74 | 0.99 | 0.77 | 0.95 |
| Field (§19), control | 0.97 | 0.72 | 0.50 | 0.52 | 0.98 | 0.99 | 0.96 | 0.57 | 0.99 | 0.61 | 0.88 |
| Share in the span of the 14 baseline shapes, nominal | 0.97 | 1.00 | 0.84 | 0.92 | 0.68 | 1.00 | 0.99 | 0.98 | 0.48 | 0.67 | 0.99 |
| The same, control | 0.99 | 1.00 | 0.97 | 0.99 | 1.00 | 1.00 | 1.00 | 0.98 | 1.00 | 1.00 | 1.00 |

- **Records 5, 6 and 11 were not used to build the control**, and with it they agree with the unchanged baseline at
  0.99, 1.00 and 0.96 (0.48, 0.52 and 0.54 with the nominal mapping). Record 10 reaches 0.92 once E1 ≠ E2 separates
  the pair FE 15 / 16. Every record then lies 0.97–1.00 inside the span of the 14 FE shapes.
- **This agrees with §17.5**, where the near-square control raised records 5, 6, 9, 10 and 11 and lowered the others:
  that control was fitted to the nominal points, so it was too narrow along Y and still too narrow along X.
- **What it means for §20.5 item 3 and §21.** The seven records "explained by no model" are the records that vary
  along FE X. Their low MAC is at least in large part a property of the nominal X window, not of the FE model and not
  of the modal fit. This is a strong indication, not a registration: a higher MAC is not evidence for a geometry,
  and the M11 reconstruction rests on a camera frame and on the scanner angles (§16.3), which this section did not
  re-examine.
- **Open, for the owner.** The 261027 scan window has no instrument record (§16.4). The two sources now disagree by
  about 80 mm along X. Nothing is changed here: the nominal mapping stays the nominal mapping. **§23 rechecks the
  261016 instrument record without any modal quantity: the window is 287.1 × 285.3 mm, and the 215 mm width is an
  error of the reconstruction.**

### 22.5 Directional bending comparison

Frequencies (Hz) of the FE modes of the four one-direction classes on the whole plate. "Pair" means that the two
modes FE 8 / 9 are mixtures and the class is not separated in that model.

| Model | Y1 | X1 | Y2 | X2 | Y1 / X1 | Y2 / X2 |
|---|---|---|---|---|---|---|
| **Experiment** (records 2, 3, 7, 9) | 54.62 | 63.50 | 145.94 | 169.18 | **0.860** | **0.863** |
| Baseline | pair 59.87 / 62.01 | pair | 168.61 | 167.49 | — | 1.007 |
| G12 −5 %, S0, +5 %, ×2, ×3 | as baseline (≤ 0.02 Hz) | pair | 168.61–168.63 | 167.49–167.51 | — | 1.007 |
| E1 −5 % | 61.61 | 58.74 | 168.62 | 163.26 | 1.049 | 1.033 |
| E1 +5 % | 60.52 | 62.86 | 168.60 | 171.62 | 0.963 | 0.982 |
| E2 −5 % | 59.01 | 61.33 | 164.34 | 167.48 | 0.962 | 0.981 |
| E2 +5 % | 63.15 | 60.25 | 172.77 | 167.50 | 1.048 | 1.032 |
| E1 −10 % | 61.45 | 57.32 | 168.62 | 158.92 | 1.072 | 1.061 |
| E2 −10 % | 57.70 | 61.04 | 159.95 | 167.48 | 0.945 | 0.955 |
| H1 (E −22.4 %) | pair 52.75 / 54.63 | pair | 148.56 | 147.58 | — | 1.007 |
| H2 (E −25.1 %) | pair 51.83 / 53.67 | pair | 145.95 | 144.99 | — | 1.007 |
| Wedge, thick at edge 4 (§18) | pair 59.39 / 61.44 | pair | 164.12 | 166.42 | — | 0.986 |
| Field of 20 readings (§19, assumed) | pair 60.19 / 63.33 | pair | 166.13 | 169.16 | — | 0.982 |
| *Expectation of the proposed test (§22.8)* | *52.23* | *60.81* | *144.25* | *167.45* | *0.859* | *0.861* |

- **Nodal lines and parity.** On the whole plate every FE one-direction mode has two (order 1) or three (order 2)
  nodal lines and a pure parity (SS for order 1; SA for Y2, AS for X2), as records 2, 7 and 9 have on their grid
  (0.98, 0.80, 0.99). Record 3 has the nodal lines of X1 and a parity of SS 0.72 with AS 0.27 (§22.7).
- **Unequal sides.** With E1 = E2 the model gives Y2 / X2 = 1.007: the shorter side is the stiffer in frequency. The
  experiment has the opposite sign and about 20 times the size.
- **Thickness asymmetry.** The two thickness models give 0.986 and 0.982. They also leave the order-1 pair mixed.
- **G12 and a common E** do not change the ratio at all (1.007 in eight models).
- **E1 ≠ E2 does, and by the square root of the ratio:** 0.955 = 1.007 × √0.9 at E2 −10 %. The experimental 0.863
  and 0.860 correspond to E2 / E1 = 0.73, far beyond the ±10 % of the archive.
- **Inside one direction.** Order 2 over order 1 is 2.67 in the experiment in both directions and 2.73–2.79 in the FE
  variants with separated classes. This 3 % is common to both directions and is not explained by a stiffness ratio.
- **The other assignment.** If the two experimental directions were exchanged against FE X and Y, every ratio above
  would be inverted and the conclusion would be the same with E1 and E2 exchanged. The assignment used here is the one
  of §22.2. It is not chosen by frequency or MAC.

### 22.6 All 11 records by class

Class-order correspondence: the k-th record of a parity class against the k-th FE mode of that class in ascending
frequency. It uses no MAC and no frequency closeness, and it is **not a pairing**. "Governing curvature" is the
share of the bending energy of the FE mode in curvature along X, along Y and in twist (from the separated modes of
the reduced basis of §22.8). Errors are (FE − EXP) / EXP.

| Record | Hz | Parity (share) | Governing curvature of the FE class mode | Baseline | H1 (E −22 %) | E2 −10 % | Wedge | Field | *Expectation (§22.8)* |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 18.63 | AA (0.99) | twist 0.97 | FE 7: +2.4 % | −0.0 % | +2.3 % | +2.0 % | +4.5 % | *+2.1 %* |
| 2 | 54.62 | SS (0.98) | **Y** 0.99 (Y1) | FE 8 of the pair: +9.6 % | −3.4 % | +5.6 % | +8.7 % | +10.2 % | *−4.4 %* |
| 3 | 63.50 | SS (0.72) | **X** 0.99 (X1) | FE 9 of the pair: −2.3 % | −14.0 % | −3.9 % | −3.2 % | −0.3 % | *−4.2 %* |
| 4 | 66.85 | AS (0.57) | **Y** 0.65, twist 0.33 | FE 11: +8.0 % | −1.9 % | +4.0 % | +7.9 % | +9.6 % | *−3.0 %* |
| 5 | 74.21 | SA (0.99) | **X** 0.72, twist 0.27 | FE 10: −3.2 % | −12.0 % | −3.2 % | −3.8 % | −0.2 % | *−3.4 %* |
| 6 | 112.27 | SS (1.00) | X 0.31, Y 0.23, twist 0.46 | FE 12: +3.8 % | −4.1 % | +2.3 % | +3.3 % | +4.9 % | *−0.4 %* |
| 7 | 145.94 | SA (0.80) | **Y** 1.00 (Y2) | FE 14: +15.5 % | +1.8 % | +9.6 % | +12.5 % | +13.8 % | *−1.2 %* |
| 8 | 157.85 | AA (0.82) | **Y** 0.86 | FE 15: +10.7 % | −1.3 % | +7.0 % | +10.7 % | +12.6 % | *−2.0 %* |
| 9 | 169.18 | AS (0.99) | **X** 1.00 (X2) | FE 13: −1.0 % | −12.8 % | −1.0 % | −1.6 % | −0.0 % | *−1.0 %* |
| 10 | 180.14 | AA (0.98) | **X** 0.89 | FE 16: −0.1 % | −11.0 % | −1.5 % | +0.2 % | +1.6 % | *−1.8 %* |
| 11 | 191.60 | SA (0.97) | **Y** 0.55, twist 0.33 | FE 18: +11.7 % | +1.5 % | +8.1 % | +11.2 % | +12.3 % | *+1.7 %* |
| Mean / largest absolute error | | | | 6.2 / 15.5 % | 5.8 / 14.0 % | 4.4 / 9.6 % | 5.9 / 12.5 % | 6.4 / 13.8 % | *2.3 / 4.4 %* |
| Class sequence of the first 11 FE modes equals the experimental one | | | | no | no | no | no | no | *yes* |

- **Every record has an FE mode of its parity class, in the same order inside the class.** FE 17 (AS, 213.2 Hz in
  the baseline) is the only one of the first twelve FE modes without a record.
- **Baseline.** The five records whose class mode is governed by Y curvature (2, 4, 7, 8, 11) are +8.0 … +15.5 %.
  The four governed by X curvature (3, 5, 9, 10) are −3.2 … −0.1 % (record 3 inside its mixed pair). Record 1 (twist)
  and record 6 (both and twist) are +2.4 and +3.8 %.
- **A common lower E** (H1, H2) closes the Y group and opens the X group by the same amount. This is the pattern of
  §20.3; here it holds for all 11 records, by class and without a MAC.
- **The thickness models** leave the Y group at +8 … +14 %.
- **The experimental sequence of classes** is AA, SS (Y1), SS (X1), AS, SA, SS, SA (Y2), AA, AS (X2), AA, SA. The
  baseline has SA before AS at records 4 and 5, AS (X2) before SA (Y2), and the two AA modes together. None of the 16
  models reproduces the sequence.

### 22.7 Assessment of the directional stiffness hypothesis

**Supported by the existing data (verified computations):**

1. The grid convention of §21.5 equals §16: the softer direction is curvature along FE Y under placement D.
2. The two experimental one-direction ratios, 0.860 and 0.863, agree with each other.
3. The plan (1.007), G12 and a common E (1.007), and the two thickness models (0.986, 0.982) cannot produce them. A
   difference between E1 and E2 can, with the square-root law of §22.5.
4. The sign and size of the baseline frequency error of all 11 records follow the curvature that governs the FE
   mode of the record's class (§22.6).
5. One ratio, E1 / E2 = 1.37, taken from the experimental frequencies alone, is expected to bring every class within
   4.4 % and to give the experimental class sequence (§22.8). This is an expectation from a reduced basis, not a
   solve.

**Not shown, or against it:**

- **The cause.** A homogeneous shell needs E1 ≠ E2 for this. A real laminate does not: its bending stiffnesses in two
  directions depend on the stacking sequence and differ even when the in-plane moduli are equal. The layup is not
  recorded (§15). An initial curvature of the 0.875 mm plate or the suspension could contribute. The frequencies do
  not separate these.
- **It is not a material value.** A frequency gives D = E h³ / 12 (1 − ν12 ν21) per direction, not E (§20.3). "E2 =
  41 000 MPa" is a way of writing a bending stiffness ratio in the existing model. `NOT_A_MATERIAL_PROPERTY`.
- **Session 261016** gives 0.811 for the order-1 ratio (55.25 / 68.10) against 0.860 here. The ratio is therefore not
  a constant of the specimen alone, or the one X record of 261016 is not comparable.
- **A residual common to both directions.** The order-1 classes are expected 4.2–4.4 % low and the order-2 classes
  1.0–1.2 % low. A stiffness ratio cannot change that.
- **Mixed records.** Records 3 and 4 share the classes SS and AS; records 7 and 8 share SA and AA. In both cases the
  parity about the X centre line is broken and the parity about the Y centre line is kept (0.98–1.00 for all 11
  records). A homogeneous orthotropic plate keeps both. A thickness gradient along X breaks exactly this one, and the
  wedge raises record 7 to 0.97 (§18). So the stiffness ratio and the thickness asymmetry act on different features
  and both may be present. That is a hypothesis.
- **No response between 195 and 241 Hz.** The stored indicator has no local maximum of 1 dB or more there, inside
  the PolyMAX band. The expectation puts an AS mode at 210 Hz, and the baseline puts FE 17 at 213 Hz. Whether that
  mode was not excited or does not exist there is not known; the excitation point is not recorded.
- **The registration.** §22.4 shows that the nominal mapping is doubtful along X. The class comparison of §22.5 and
  §22.6 does not use the point positions; every MAC does.

**Verdict.** The directional stiffness hypothesis (H4 of §21.6) is consistent with every frequency and class
observation available, and no archived alternative is. It is **not confirmed**: no model with such a ratio has been
solved, the cause is undetermined, and no value is released. H5 of §21.6 is answered differently than expected: the
discrepancies of records 5, 6, 10 and 11 are, by the indication of §22.4, mainly a matter of the mapping along X.

### 22.8 One proposed FE test (prepared, not executed)

> **Executed (§25, 2026-11-26):** the test was solved once under the owner's authorisation. Criteria 1, 2 and 3 are met. The text below is kept as written before the solve.

**Model.** `S4R_0875_BASELINE` with one changed constant: **E2 = 41 000 MPa**; E1 = 56 000 MPa, G12 = 5 000 MPa,
ν12 = 0.05, thickness 0.875 mm, density, mesh and free-free conditions unchanged. One eigenfrequency solve and one
ODB extraction, each needing a separate owner authorisation.

- **Where the value comes from.** r = (f_X / f_Y)² × (301 / 300)⁴ from the experimental frequencies and the plan
  alone: 1.370 from records 2 and 3, 1.362 from records 7 and 9, mean 1.366. E2 = 56 000 / 1.366 = 41 003, rounded.
  E1 is the archived template value. No FE frequency enters the value. The direction follows §22.2
  (`CONVENTION_ONLY`). It is a hypothesis test with one declared number, not a fit and not a material constant.
- **How the expectation was obtained.** A reduced basis of the 14 baseline shapes: thin-plate bending energy forms on
  the 101 × 101 node grid and a 14 × 14 eigenproblem. Check: it reproduces the baseline frequencies to 0.22 % before
  any correction, and the frequencies of the eleven archived variants with a changed E1, E2 or small G12 step to
  0.01–0.07 % for FE 7–19 (G12 ×2: 0.6 %; G12 ×3: 1.6 %; FE 20 is outside the use, up to 3.8 %). The step to
  E2 −27 % is larger than any archived one, so the expectation is itself part of what the solve tests.

**Expected frequencies and shapes** (reduced basis; an expectation, not a result):

| FE mode | Expected Hz | Class on the whole plate | Baseline branch content | Record of the class order | Expected error |
|---|---|---|---|---|---|
| 7 | 19.02 | AA, twist | FE 7 | 1 | +2.1 % |
| 8 | 52.23 | SS, **Y1** (Y share 0.99) | FE 8 and 9, separated | 2 | −4.4 % |
| 9 | 60.81 | SS, **X1** (X share 0.99) | FE 8 and 9, separated | 3 | −4.2 % |
| 10 | 64.83 | AS | FE 11, now below FE 10 | 4 | −3.0 % |
| 11 | 71.71 | SA | FE 10 | 5 | −3.4 % |
| 12 | 111.84 | SS | FE 12 | 6 | −0.4 % |
| 13 | 144.25 | SA, **Y2** | FE 14, now below FE 13 | 7 | −1.2 % |
| 14 | 154.72 | AA, Y-governed | FE 15 and 16, separated | 8 | −2.0 % |
| 15 | 167.45 | AS, **X2** | FE 13 | 9 | −1.0 % |
| 16 | 176.83 | AA, X-governed | FE 15 and 16, separated | 10 | −1.8 % |
| 17 | 194.90 | SA | FE 18 | 11 | +1.7 % |
| 18 | 210.16 | AS | FE 17 | none | — |

- **Expected shape changes.** The pairs FE 8 / 9 and FE 15 / 16 separate into one Y-governed and one X-governed
  mode. The Y-governed mode of each close pair moves below the X-governed one (FE 11 below FE 10, FE 14 below
  FE 13, FE 18 below FE 17), and the Y-governed AA mode comes between Y2 and X2. No mode leaves its parity class: a homogeneous
  material cannot mix classes.
- **Expected research MAC (reported, not a criterion).** Nominal mapping: 0.91, 0.97, 0.33, 0.55, 0.48, 0.52, 0.79,
  0.92, 0.26, 0.25, 0.55 for records 1–11. Control geometry of §22.4: 0.97, 0.97, 0.69, 0.56, 0.99, 1.00, 0.80,
  0.80, 0.99, 0.98, 0.96. Records 3, 4, 7 and 8 are expected to stay below 0.9 in either case (§22.7, mixed records).

**Falsification criteria, written before any solve.** Both are whole-plate quantities and do not depend on the point
mapping.

1. **Class sequence.** The parity classes of FE modes 7–17 of the solved model, in ascending frequency, must be AA,
   SS (Y1), SS (X1), AS, SA, SS, SA (Y2), AA, AS (X2), AA, SA. Any other sequence rejects the hypothesis in this form.
2. **Class frequencies.** For each of the 11 records the FE mode of its class order must lie within ± 5 % of the
   record. Records 2, 3, 7 and 9 gave the ratio; records 1, 4, 5, 6, 8, 10 and 11 are the test. One record outside
   ± 5 % rejects a single stiffness ratio as a sufficient description. The expectation leaves 0.6 % of margin at
   records 2 and 3. ± 5 % is the existing descriptive level; it is not a gate.
3. **If the solved frequencies of FE 7–18 differ from the expected ones by more than 1 %,** the reduced basis is not
   valid at this step; criteria 1 and 2 are then judged on the solve alone.

- **What a passed test would mean.** That one bending stiffness ratio describes the frequencies of this plate in the
  261027 setup. Not its cause, not E1 or E2 of the material, and no pairing.
- **What it cannot test.** The mixing of records 3 / 4 and 7 / 8, the 3 % residual between the orders, and the scan
  window.

### 22.9 Qualification of the conclusion of §21

§21 stated that the FE discrepancy of records 5, 6, 9, 10 and 11 "is not an artefact of the modal fit". The checks
of §21 do not carry that statement, and it is withdrawn in that form (§21 is amended accordingly).

- **The refit with fixed poles is not independent.** It is a linear solve on the same transfer functions with the
  same 11 poles. A wrong, missing or spurious pole would still return residues that agree with the stored ones. It
  shows that the stored shapes are the residues of that response at those poles, and nothing about the poles.
- **Response support is not independent either.** The peaks and the response shapes come from the data PolyMAX was
  fitted to. They show that a record corresponds to something in the response. They do not show that it is one mode,
  that its frequency and damping are right, or that no mode was missed.
- **Not available.** One force reference; the stabilisation diagrams exist only as images and were not read; no
  uncertainty of any pole; no second estimator and no repeat of the setup.
- **What §21 does establish.** The stored shapes are consistent with the stored response; ten records have a clear
  resonance; the shapes are distinct and smooth. That is experimental support, not validation of the poles.
- **What this section adds.** Nine records are nearly pure in one parity class, and the four one-direction records
  have nodal lines where free bending shapes have them. This is plausibility of the shapes, again not a validation of
  the poles. The low MAC of the records that vary along FE X has a candidate cause outside the modal fit and outside
  the FE model: the nominal scan window (§22.4).

### 22.10 Limitations

- No model with the stiffness ratio has been solved. §22.8 is an expectation.
- The class of a record is taken on its own grid; the class of an FE mode on the whole plate. For the mixed records
  3, 4, 7 and 8 the dominant class is used (0.72, 0.57, 0.80, 0.82).
- The level 0.70 for a one-direction class was first used for record 3 in §21.5, after its value was known.
- The control geometry assumes that records 2, 3, 7 and 9 are free bending of the whole side, and it neglects any
  rotation of the grid. It conflicts with the M11 reconstruction and is not adopted.
- Suspension, force sensor and interior thickness remain unmodelled (§20.4). `PHYSICAL_REGISTRATION_NOT_VERIFIED`,
  D-044 and SPEC §5.2 (no traceable material axes) stand.

### 22.11 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `e37add12…` and a clean tracked tree before the edit |
| Input hashes | experiment, nominal geometry, baseline package, the results of §18–§21, the wedge and field extraction files and the 13 variant INP, ODB or manifest files equal their recorded hashes; 304 input files have the same size and mtime before and after |
| Shape identity | the research MAC recomputed from the loaded fields equals §20 for 14 models (6.7e-16) and §19 for the two thickness models (3.3e-16) |
| Descriptor consistency | synthetic directional shapes of §22.3; axis exchange exchanges the outputs; the descriptors of the 11 records equal §21.5 (difference 0.0) |
| Axis mapping | §22.2: equal to §16; residual 0.31 mm rms |
| Reduced basis | baseline and 13 archived variants reproduced (§22.8) |
| Reproducibility | two complete runs give byte-identical `results.json` (`e94bd2c9…`), `arrays.npz`, `results_addendum.json` (`e5a0eb69…`) and `arrays_addendum.npz` |
| Tests | `research/m11_r65`: 29 OK. `tests.test_plate_study`: 30 OK. `tests.test_experimental_qc`: 27 OK (4 skipped). `tests.test_plate_registration_readiness`: 18 OK. `tests.test_plate_rc1_owner_clarification`: 12 OK |

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_DIRECTIONAL_STIFFNESS_01` (outside git):
`run_directional.py`, `protocol.json` (`5431bea5…`), `results.json`, `arrays.npz`, `run_addendum.py`,
`protocol_addendum.json` (`3b6b4466…`), `results_addendum.json`, `arrays_addendum.npz`, `report.py`,
`fig_directional_shapes.png`, `fig_directional_frequencies.png`.

Nothing is published in the repository except this section and the amendment of §21.

## 23. PLATE-0875-SCAN-WINDOW-CHECK-01 — the 215 mm and the 294 mm scan width (2026-11-25)

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** The section rechecks
where the 289 scan points of session 261016 lay on the plate. It reads the instrument file of 261016, its stored
camera frame, the instrument exports of both sessions and the measured plate dimensions. **No modal shape, frequency,
MAC or FE result is read, and no geometry is selected by one.** No Abaqus, solve, extraction, fit, LM or Auto-ID was
run. No registration is created or frozen, the nominal mapping file is not changed, and no program code is changed.
M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production Auto-ID BLOCKED are unchanged. The 261027 `.svd`
was not searched for.

**Short answer.**

- **Resolved for 261016.** The scan window is about **287.1 × 285.3 mm**, centred on the plate, with gaps of 7.1 /
  6.8 / 7.0 / 7.7 mm to the left / right / bottom / top edge. The width of 215.4 mm is an error of the
  reconstruction, not a property of the scan.
- **The cause is a coordinate conversion.** The instrument file stores the horizontal video coordinate of the scan
  points in another unit than the stored full-frame rectangle that the reconstruction used for it. The points were
  therefore compressed to 3/4 of their width and shifted to the right (§23.3).
- **The hypothetical 294 mm is not confirmed as a number.** The instrument record gives 287 mm. The nodal-line
  estimate of §22.4 pointed in the right direction and is 7 mm (2.5 %) too wide. It was not used here.
- **261027.** Its instrument export describes a square grid (aspect 0.9999). Its physical size is not recorded:
  279 mm if the export scale is taken as stored, 287 × 285 mm if the points are those of 261016 (owner). That
  difference of about 3 % is **unresolved**. A window of 215 mm along one axis is excluded by either reading.
- **Consequence, not acted on here.** Every research MAC of §17–§22 used point positions that are wrong by 25.7 mm
  rms and up to 49.3 mm along FE X. None was recomputed in this task (§23.7).

### 23.1 Inputs

| Input | Content | SHA-256 |
|---|---|---|
| Instrument file 261016 | `300by300_plate_only_1mm_261016.svd` (verified copy): scan points, scan object, video alignment, camera frame | `0a770b1b…` = recorded |
| PSV export 261016 | `…261016.unv`: the instrument's metric geometry of the 289 points | `6d66eafe…` = recorded |
| PSV export 261027 | `…ROTATED_261027.unv` (acquired 27-Oct-26 11:38:17): node table only | `d3bc99e9…` = recorded |
| Fitted file 261027 | `…ROTATED_Polytec_261027.unv`: node table only | `76db80ae…` = recorded |
| M11 reconstruction | `plate_reconstruction_W301xH300.json`, `plate_scan_px.json` | `09be8b88…`, `bd80b5b7…` = recorded |
| Second edge detector | `reg02_checks.json` (§16.2) | `0bb26277…` = recorded |
| Stored records of two other sessions | `SP13_…reconstruction.json`, `SP02_…reconstruction.json` (repository; read only, their `.svd` files were not opened) | `c30b78d8…`, `f42e69a1…` (first recorded here) |

- The camera frame extracted here is pixel-identical to the M11 frame `plate_frame_raw.png`.
- The M11 reconstruction is reproduced from the instrument file before anything else: the recorded pixel positions
  to 5·10⁻¹³ px and the recorded 289 plate positions to 5·10⁻⁵ mm.
- All ten input files have the same size, modification time and SHA-256 before and after.

### 23.2 What the instrument file stores

All values are normalised video coordinates as stored in the `.svd` of 261016.

| Stream | Stored | Reading |
|---|---|---|
| `VideoSettings` (end) and the header of `MeasPoints` | rectangle u −0.2222 … 1.5556, v 0 … 1 | the full 1920 × 1080 frame in a unit of 1080 px, with u = 0 at pixel 240 |
| `DefaultSettings` | rectangle u −0.2222 … 1.5556, v −2.4667 … 1.0; then a point list that starts (0, 0), (1.3333, 0), (1.3333, 1) | the same u range; the anomalous v range of M11 deviation 1; and the full frame in a unit of 1440 × 1080 px |
| `ScanObjects` | the scan object drawn by the operator: u 0.12599 … 0.91027, v 0.08501 … 0.86929 | spans 0.78428 × 0.78428: **a square** in the unit of the first row |
| `MeasPoints` | the 289 points: u 0.26116 … 0.84937, v 0.08501 … 0.86929; 17 × 17 distinct values | span ratio u / v = **0.7500** |

- **The scan points and the scan object are the same rectangle in two units.** The v extents are identical. The
  u extents obey u(points) = 0.750000 · u(object) + 0.166667, that is 3/4 · u + 1/6, to 8·10⁻⁸ at both ends.
- **That relation is the change of unit between the two stored frames.** A coordinate in the unit of 1080 px with its
  origin at pixel 240 becomes pixel / 1440 by exactly 3/4 · u + 1/6. The scan points are therefore stored as
  pixel / 1440 horizontally and pixel / 1080 vertically, the normalisation of a 4 : 3 frame.
- **In pixels** the scan object lies at x 376.07 … 1223.09 and y 91.81 … 938.83. The scan points read as
  pixel / 1440 lie on it to 0.001 px. The grid is 847.0 × 847.0 px.
- **Deviation 1 of M11 (v 0 … 1) is supported at the source**: two streams store v 0 … 1.

### 23.3 The error in the reconstruction

`reconstruct` in `src/services/psv_video_registration.py` converts both coordinates of the scan points with the
rectangle of `DefaultSettings`: `px = (u − u0) · width / (u1 − u0)`, which is 240 + 1080 · u. For the scan points
the correct conversion is 1440 · u.

| Property of the algorithm | Finding |
|---|---|
| Axes and mirror | correct: plate x grows with pixel x, plate y grows upwards from the bottom edge; no exchange and no mirror |
| Vertical conversion | correct with v 0 … 1 (deviation 1) |
| Horizontal conversion | **wrong unit**: pixel(M11) = 240 + 0.75 · pixel(true), verified on the 289 points to 6·10⁻⁴ px |
| Aspect ratio | the grid becomes 635.3 × 847.0 px instead of 847.0 × 847.0 px: 0.7500 of its width |
| Plate edges and physical scale | not affected: 892.2 × 892.6 px for 301 × 300 mm, 2.964 and 2.975 px / mm |
| Homography from the four corners | not affected; round trip 1·10⁻¹³ mm |

- **Effect on the points.** Every point moves towards pixel 960. On this plate the left column moves 49.3 mm to the
  right and the right column 22.4 mm to the left. The vertical positions change by at most 0.2 mm.
- **Deviation 2 of M11 was a symptom.** The edge search window had to be widened from 150 to 220 px because the
  compressed grid ended 167 px from the left plate edge. Started from the correct grid, the unchanged detector with
  its standard 150 px window finds the left, right and top edges 23, 21 and 26 px from the grid (120, 116 and 112
  samples of 120), at the recorded positions.
- **Deviation 3 remains.** With the standard polarity the bottom search still takes another structure (42 samples,
  42 px away). The bottom edge keeps its low-contrast uncertainty (M11 §13.4, §15.4).

### 23.4 Checks that use neither the plate edges nor any mode

| Check | Scan points read as pixel / 1440 | M11 reading |
|---|---|---|
| Distance of the point extent from the stored scan object | 0.0003 and 0.0008 px | 146.0 px at the left, 65.8 px at the right |
| Instrument geometry of the PSV export against the pixels, mm per px, x over y | **0.9966** (0.2942 and 0.2952) | 1.3288 (0.3923 and 0.2952) |
| Affine residual of that comparison | 0.11 mm rms | the same |
| Grid in laser angles (13 alignment points) | 13.8° × 13.5° | 10.4° × 13.4° |
| The square plate itself, in the same angles | 14.4° × 14.0° | the same |

- **The PSV export is the instrument's own metric geometry.** It is proportional to the pixels with one scale in
  both directions only under the pixel / 1440 reading. Under the M11 reading the instrument would use two scales
  that differ by a factor of 1.33.
- **The plate is square in the frame and subtends nearly equal laser angles** (ratio 1.029, the instrument
  anisotropy seen in every session). A grid that covers the plate to 7 mm on every side must then span nearly the
  same angles as the plate. 13.8° × 13.5° does; 10.4° × 13.4° is the 215 mm window.
- **Chance.** Two unrelated extents would satisfy 3/4 · u + 1/6 to the stored precision with a probability below
  2·10⁻¹¹.

### 23.5 Why the scanner-angle check did not detect this

M11 §15.4 and §16.3 state that the grid shape was confirmed by the scanner angles: aspect 0.7747 against 0.7553,
rms 1.32 mm. That check maps the scan points to angles with the alignment table. The alignment table is stored in
the unit of 1080 px; the scan points were fed to it in the wrong unit, the same one the reconstruction used. Both
sides of the comparison carried the same error.

| Reading of the scan-point u, on both sides | Aspect in angles | Aspect on the plate | Similarity fit, rms / max |
|---|---|---|---|
| M11 | 0.7747 | 0.7553 | 1.32 / 2.35 mm (reproduced) |
| pixel / 1440 | 1.0273 | 1.0064 | 1.56 / 2.78 mm |

Both readings pass. The check confirms that the alignment is nearly isotropic. It cannot tell which reading is
right, and it was not an independent confirmation of the 215 mm window. The statements of §16.3 and §17.6 that rest
on it are withdrawn in this respect.

### 23.6 Scan dimensions

Plate 301 mm (horizontal in the 261016 scanner view, FE X under placement D) × 300 mm.

| Geometry | Window, mm | X range, mm | Y range, mm | Gaps left / right / bottom / top, mm | Status |
|---|---|---|---|---|---|
| M11 reconstruction (nominal mapping of §17–§22) | 215.4 × 285.2 | 56.4 … 271.8 | 7.0 … 292.2 | 56.4 / 29.2 / 7.0 / 7.8 | **wrong along X** (§23.3) |
| Instrument record, M11 edge fit | **287.1 × 285.3** | 7.1 … 294.2 | 7.0 … 292.3 | 7.1 / 6.8 / 7.0 / 7.7 | confirmed for 261016 |
| Instrument record, second edge detector (§16.2) | 286.1 × 284.2 | 8.0 … 294.1 | 7.3 … 291.5 | 8.0 / 6.9 / 7.3 / 8.5 | the same image; not independent |
| Nodal-line control of §22.4 (quoted; not used) | 294.2 × 292.4 | 2.7 … 296.9 | 3.9 … 296.3 | 2.7 / 4.1 / 3.9 / 3.7 | not confirmed: 7 mm too wide in both directions |

- **Grid pitch:** 17.94 mm along X and 17.83 mm along Y, against 13.46 mm along X in the M11 reconstruction.
- **Uncertainty.** The grid in pixels is exact to the stored precision. The plate positions carry the uncertainty of
  the plate edges in the image, 1–3 mm (M11 §15.4), with the largest part at the bottom edge. The two edge
  detectors differ by at most 1.0 mm.
- **The 80 mm conflict of §22.4 is resolved in favour of a full-width scan.** The remaining difference between the
  instrument record and the nodal-line estimate, 3–4 mm on each side, is not resolved here and needs no geometric
  explanation: that estimate assumed that the measured nodal lines lie where those of a uniform FE plate lie.
- **Annotated image:** `fig_scan_window.png` (work directory). It shows the plate edges, the stored scan object, the
  289 points in both readings and the dimensions. It contains the laboratory photograph and is not published.

### 23.7 The 261027 instrument exports

No camera frame and no `.svd` of 261027 are available. The two UNV files carry the instrument's node table; the two
tables are identical.

| Quantity | 261016 | 261027 |
|---|---|---|
| Distance entered in the PSV software (z of every point) | 1.00 m | 1.15 m |
| Grid of the export along its two axes | 249.2 × 250.1 mm | 279.2 × 279.2 mm |
| Aspect of the export | 0.9966 | **0.9999** |
| Angle between the grid axes | 89.96° | 89.99° |
| Physical window | 287.1 × 285.3 mm (§23.6) | not recorded |
| Physical over export | 1.152 and 1.141 | not recorded |

- **Shape.** In 261016 an export aspect of 0.9966 belongs to a physical aspect of 1.0064. The 261027 export is
  square to 0.01 %. A 261027 window with an aspect of 0.755 is excluded by its own export.
- **Size, unresolved.** Two readings exist, and no record decides between them:
  - the export as stored, 279.2 × 279.2 mm, which is physical only if the entered 1.15 m was the true distance and
    the software scale is calibrated; the 261016 export is 14–15 % too small at its entered 1.00 m, which a true
    distance of about 1.15 m would explain, but that distance is not recorded;
  - the points of 261016 carried over by the owner's "same points": 287.1 × 285.3 mm.
- **Per metre of entered distance** the export grid is 249.2 … 250.1 mm in 261016 and 242.8 mm in 261027: 2.7 %
  smaller. Either the grid was drawn slightly smaller in 261027, or the two true distances were not in the ratio
  1.15.
- **Not established for 261027:** the offsets of the grid to the plate edges. They need the camera frame of that
  session.

### 23.8 What is affected, and what stays open

- **Affected in this report.** §17–§22 used the M11 positions as the nominal mapping. Along FE X those positions are
  wrong by up to 49.3 mm (25.7 mm rms over the 289 points); along FE Y they are right to 0.2 mm. The research MAC
  values, the first-ranked FE modes, the "seven records explained by no model" of §20.5 and the window descriptors
  of §22.3 all depend on them. The frequency comparisons and the whole-plate FE classes do not.
- **Not recomputed.** No MAC was computed with the corrected positions in this task (**§24 does it**). The nominal mapping is an
  owner decision (2026-11-24) and stays in force until the owner changes it. The corrected positions are in
  `results.json` and `arrays.npz`, labelled `RESEARCH_ONLY`.
- **Outside this report, flagged only.** The same routine produced the stored reconstruction records of SP-02 and
  SP-13. Both records carry the same signature: a window aspect of 0.739, an instrument scale that differs by 1.33
  to 1.34 between the axes, and side gaps of 61–81 mm against 6–14 mm at the top and bottom. Their `.svd` files were
  not opened here, and nothing was changed. Whether those records are affected has to be checked on their own
  instrument files.
- **Open for the owner.**
  1. Whether the corrected 261016 positions replace the M11 positions as the nominal research mapping, and whether
     §17–§22 are then recomputed.
  2. Whether the reconstruction routine and the SP-02 / SP-13 records are reviewed. That concerns accepted evidence
     and needs a separate authorisation.
  3. The physical size of the 261027 window (279 or 287 mm) and its offsets: only the instrument record of that
     session can settle them.

### 23.9 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `f5b78166…` and a clean tracked tree before the edit |
| Source hashes | seven inputs equal their recorded hashes; all ten unchanged in size, mtime and SHA-256 |
| Reproduction of the M11 result | pixels to 5·10⁻¹³ px, plate positions to 5·10⁻⁵ mm, window and gaps equal |
| Coordinate transformations | pixel(M11) = 240 + 0.75 · pixel(true) on the 289 points (6·10⁻⁴ px); scan object = point extent (0.001 px); homography round trip 1·10⁻¹³ mm; axis and mirror convention checked |
| Synthetic geometry | a known 280 mm grid on a known plate, stored as the instrument stores it: recovered to 2·10⁻¹³ mm by the pixel / 1440 reading; the M11 reading returns 0.7505 of its width with errors up to 48.6 mm. The relation 3/4, 1/6 is recovered from single-precision extents to 2·10⁻⁷ |
| Reproducibility | two complete runs give byte-identical `results.json` (`6c3005b3…`), `arrays.npz` (`20219eec…`) and `fig_scan_window.png` |
| Tests | `tests.test_physical_registration`: 24 OK. `tests.test_sp13_physical_registration`: 17 OK (4 skipped). `tests.test_sp02_physical_registration`: 18 OK (6 skipped). `tests.test_plate_physical_review`: 36 OK. `tests.test_plate_registration_readiness`: 18 OK. `tests.test_plate_study`: 30 OK. `tests.test_plate_rc1_owner_clarification`: 12 OK. `research/m11_r65`: 29 OK. The skips are the suites' own (stores not configured) |

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_SCAN_WINDOW_CHECK_01` (outside git): `run_scan_window.py`,
`results.json`, `arrays.npz`, `report.py`, `fig_scan_window.png`.

Nothing is published in the repository except this section and three pointers to it in §16.3, §17.1 and §22.4.

## 24. PLATE-0875-SCAN-NORMALIZATION-FIX-01 — corrected scan normalisation and the recomputed research MAC (2026-11-26)

**Every number in this section is `RESEARCH_ONLY` and `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** The section corrects
the coordinate normalisation defect of §23 in the program and recomputes the research MAC of the 261027 series with
point positions taken from the instrument record. **The geometry was fixed before any MAC was computed, and no
geometry is selected by MAC, shape or frequency.** No Abaqus solve and no ODB extraction was run; the 16 existing FE
packages and the 11 fitted records were read. Nothing was fitted. No pairing is confirmed, no registration is created
or frozen, and no material value is released. The SP-02 and SP-13 registrations, passports and evidence records are
unchanged and were not opened. M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production Auto-ID BLOCKED are
unchanged.

**Short answer.**

- **The defect is corrected in `src/services/psv_video_registration.py`.** A new reading takes the unit frame of the
  scan points from the metadata stored in the instrument file, checks it against the stored scan object, and refuses
  when the metadata are missing, unsupported or ambiguous. No pixel count and no aspect ratio is assumed.
- **The earlier reading is kept, unchanged, as the default of `reconstruct`.** The governed SP-02 and SP-13 records
  were made with it and must stay reproducible. Whether the governed tool changes to the new reading is an owner
  decision (§24.9).
- **The 261016 window is reproduced: 287.1 × 285.3 mm.**
- **With the corrected positions the baseline agrees with five records at 0.96–0.99** (records 1, 5, 6, 9, 11) instead
  of one. The mean research MAC of the first-ranked mode rises from 0.50 to 0.75. Every record lies 0.96–1.00 inside
  the span of the 14 FE shapes (0.48–1.00 before).
- **The 279.2 mm alternative changes nothing of substance.** With either assumed offset no first-ranked mode changes
  and no first-ranked MAC moves by more than 0.034.
- **The remaining low records are mixtures inside two groups of close modes.** Records 2–5 lie 0.96–0.99 inside the
  span of FE 8–11, and records 7–10 lie 0.97–0.98 inside the span of FE 13–16. The FE model has the shapes; it
  combines them differently.
- **The directional stiffness hypothesis of §22 is strengthened, not confirmed.** The records now identified at
  0.96–0.99 show its frequency pattern directly, a lower E2 separates the mixed pairs the way the experiment does, and
  a common lower E is excluded by records 5 and 9. No model with the ratio has been solved.
- **The proposed test of §22.8, E2 = 41 000 MPa, stands unchanged** and is the recommended next FE step (§24.8).

### 24.1 The correction in the program

The instrument file stores video coordinates in more than one unit frame (§23.2). The corrected reading works from
what the file stores:

| Stored item | Stream | Use |
|---|---|---|
| Full-frame rectangle | `MeasPoints` header, `VideoSettings`, u range of `DefaultSettings` | one candidate frame; the three copies must agree to 1·10⁻⁵ |
| Frame that opens the default point list | `DefaultSettings` | second candidate frame, when present and different |
| Scan object drawn by the operator | `ScanObjects` | the reference: one axis-parallel rectangle |
| Frame size in pixels | the stored JPEG | converts a frame to pixels |

- **Rule.** For each pair of candidate frames (one for the scan object, one for the scan points) the hull of the
  scan points is compared with the scan object in pixels. Exactly one pair must agree to 0.25 px. That pair gives the
  frame of the points.
- **Refusals** (`PSVRegistrationError`, no result): the copies of the full-frame rectangle differ; no pair agrees;
  more than one pair agrees; the scan object is missing, is not a single object, or is not an axis-parallel
  rectangle; an unknown reading is requested.
- **One refusal deserves a note.** When points and scan object are stored in the same unit and the file holds two
  different frames, both same-frame pairs agree. The file then does not say which frame gives pixels, and the routine
  refuses.
- **Record.** The new reading writes schema `…/v2` with the stored rectangles, the decision and every trial. The
  earlier reading writes the `…/v1` record with exactly the earlier content.
- **Not changed:** the parser, the edge fit and its constants, the homography, `tools/reconstruct_psv_registration.py`
  and every stored record.

Session 261016, the four trials of the corrected reading:

| Scan object in | Scan points in | Hull against scan object, px |
|---|---|---|
| full-frame rectangle | full-frame rectangle (the earlier reading) | 146.0 |
| full-frame rectangle | default point-list frame | **0.0004** |
| default point-list frame | full-frame rectangle | 340.6 |
| default point-list frame | default point-list frame | 194.6 |

The points are in the default point-list frame, (0, 0) to (1.3333, 1); on the 1920 × 1080 frame that is 1440.0 px
per unit of u, as §23 found. The value follows from the stored frame; it is not written in the code.

### 24.2 The point geometries

All are fixed without any modal quantity.

| Geometry | Role | Window, mm | Gaps left / right / bottom / top, mm | Distance from the primary positions, rms / max mm |
|---|---|---|---|---|
| Nominal mapping of §17 (M11 record) | **superseded**; kept for the comparison | 215.4 × 285.2 | 56.4 / 29.2 / 7.0 / 7.8 | 25.7 / 49.3 |
| **Corrected 261016 positions** | **primary research mapping** | **287.1 × 285.3** | 7.1 / 6.8 / 7.0 / 7.7 | — |
| Corrected, unattended edge fit | sensitivity | 287.1 × 285.7 | 7.2 / 6.7 / 6.7 / 7.6 | 1.7 / 4.3 |
| 279.2 mm, same centre as the 261016 window | diagnostic, **assumed offsets** | 279.2 × 279.2 | 11.0 / 10.8 / 10.1 / 10.7 | 3.0 / 5.0 |
| 279.2 mm, centred on the plate | diagnostic, **assumed offsets** | 279.2 × 279.2 | 10.9 / 10.9 / 10.4 / 10.4 | 3.1 / 5.3 |

- **Primary.** The corrected pixels of the module with the plate corners of the recorded M11 edge fit. The positions
  equal those of §23 exactly (difference 0.0 mm). They are used for 261027 **on the owner's statement that the same
  points were scanned**, and are conditional on it.
- **Unattended.** The corrected module run by itself finds the left, right and top edges as M11 did. At the bottom it
  takes another structure (19 of 42 samples, tilted 0.96°), the one that M11 deviation 3 replaced. The window height
  differs by 0.4 mm.
- **279.2 mm.** The side comes from the 261027 instrument export at the entered distance of 1.15 m (§23.7). The
  261027 offsets have no instrument record. Two offsets are assumed and both are reported.
- **The earlier reading on this file** stops with an error (no top edge found): the file stores an anomalous v range
  in `DefaultSettings`, which M11 had replaced by hand (deviation 1).
- **Mapping, metric, levels and labels** are those of §17, unchanged: placement D (`CONVENTION_ONLY`), bilinear
  sampling of FE U3, complex MAC, the 59 declared shift and rotation scenarios as a range.

### 24.3 Baseline: before and after

Research MAC of each record with its first-ranked FE mode. "Range" is over the 59 declared scenarios around the
corrected positions. Errors are (FE − EXP) / EXP.

| EXP | Hz | Before: first FE, MAC | After: first FE (Hz) | MAC (range) | Frequency error | Second FE, MAC | Share in the pair | Share in FE 8–11 / FE 13–16 | Share in the 14 shapes, before → after | Label after |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 18.63 | FE 7, 0.91 | FE 7 (19.07) | **0.97** (0.96–0.97) | +2.4 % | FE 9, 0.01 | — | 0.01 / 0.00 | 0.97 → 0.99 | CANDIDATE_ONLY |
| 2 | 54.62 | FE 9, 0.60 | FE 9 (62.01) | 0.52 (0.52–0.52) | +13.5 % | FE 8, 0.45 | 8 / 9: 0.97 | 0.99 / 0.00 | 1.00 → 0.99 | AMBIGUOUS_CLUSTER |
| 3 | 63.50 | FE 20, 0.31 | FE 8 (59.87) | 0.45 (0.44–0.45) | −5.7 % | FE 11, 0.26 | 8 / 9: 0.70 | 0.96 / 0.00 | 0.84 → 0.96 | NO_CANDIDATE |
| 4 | 66.85 | FE 11, 0.55 | FE 11 (72.19) | 0.56 (0.55–0.56) | +8.0 % | FE 8, 0.22 | 10 / 11: 0.57 | 0.98 / 0.00 | 0.92 → 0.99 | AMBIGUOUS_CLUSTER |
| 5 | 74.21 | FE 10, 0.48 | FE 10 (71.85) | **0.99** (0.97–0.99) | −3.2 % | FE 7, 0.00 | 10 / 11: 0.99 | 0.99 / 0.00 | 0.68 → 0.99 | AMBIGUOUS_CLUSTER |
| 6 | 112.27 | FE 12, 0.52 | FE 12 (116.58) | **0.99** (0.97–0.99) | +3.8 % | FE 9, 0.01 | — | 0.01 / 0.00 | 1.00 → 1.00 | CANDIDATE_ONLY |
| 7 | 145.94 | FE 14, 0.79 | FE 14 (168.61) | 0.79 (0.77–0.79) | +15.5 % | FE 16, 0.13 | 13 / 14: 0.79 | 0.00 / 0.98 | 0.99 → 0.99 | AMBIGUOUS_CLUSTER |
| 8 | 157.85 | FE 16, 0.43 | FE 16 (179.90) | 0.43 (0.41–0.45) | +14.0 % | FE 15, 0.37 | 15 / 16: 0.81 | 0.00 / 0.97 | 0.98 → 0.98 | AMBIGUOUS_CLUSTER |
| 9 | 169.18 | FE 13, 0.26 | FE 13 (167.49) | **0.98** (0.96–0.98) | −1.0 % | FE 18, 0.00 | 13 / 14: 0.98 | 0.00 / 0.98 | 0.48 → 0.99 | AMBIGUOUS_CLUSTER |
| 10 | 180.14 | FE 15, 0.15 | FE 15 (174.80) | 0.57 (0.55–0.57) | −3.0 % | FE 16, 0.41 | 15 / 16: 0.97 | 0.00 / 0.98 | 0.67 → 1.00 | AMBIGUOUS_CLUSTER |
| 11 | 191.60 | FE 18, 0.54 | FE 18 (213.95) | **0.96** (0.92–0.96) | +11.7 % | FE 17, 0.01 | 17 / 18: 0.97 | 0.00 / 0.03 | 0.99 → 1.00 | AMBIGUOUS_CLUSTER |

- **Five records agree with one baseline mode at 0.96–0.99:** 1, 5, 6, 9 and 11. Before, only record 1 exceeded 0.80.
- **The first-ranked mode is the same in all 59 scenarios for every record**, and the MAC moves by at most 0.04.
- **Record 3 no longer points to FE 20** (416 % away). Its first-ranked mode is now FE 8, inside the pair it belongs
  to.
- **Labels.** `AMBIGUOUS_CLUSTER` is given whenever the first-ranked mode belongs to a close FE group or a two-mode
  subspace reaches 0.80, whatever the MAC. Records 5, 9 and 11 carry it for that reason. No label is a pairing.
- **Subspaces.** Records 2–5 lie 0.96–0.99 inside the span of the four modes FE 8–11 (0.99, 0.61, 0.76, 0.49
  before). Records 7–10 lie 0.97–0.98 inside the span of FE 13–16 (0.98, 0.97, 0.26, 0.25 before). The four-mode
  shares were added after the first tables had been read and are marked post hoc in `protocol.json`.

### 24.4 All 16 models

Research MAC of each record with its first-ranked FE mode, corrected positions.

| Model | EXP 1 | EXP 2 | EXP 3 | EXP 4 | EXP 5 | EXP 6 | EXP 7 | EXP 8 | EXP 9 | EXP 10 | EXP 11 | Mean, before → after | Records ≥ 0.80, before → after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.57 | 0.96 | 0.50 → 0.75 | 1 → 5 |
| G12 −5 % | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.57 | 0.96 | 0.50 → 0.75 | 1 → 5 |
| S0 (G12 4 850) | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.57 | 0.96 | 0.50 → 0.75 | 1 → 5 |
| G12 +5 % | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.57 | 0.96 | 0.50 → 0.75 | 1 → 5 |
| G12 ×2 | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.56 | 0.96 | 0.51 → 0.75 | 1 → 5 |
| G12 ×3 | 0.97 | 0.52 | 0.45 | 0.56 | 0.98 | 0.99 | 0.79 | 0.43 | 0.98 | 0.56 | 0.96 | 0.51 → 0.75 | 1 → 5 |
| E1 −5 % | 0.97 | 0.77 | 0.61 | 0.56 | 0.99 | 0.99 | 0.79 | 0.65 | 0.98 | 0.82 | 0.96 | 0.56 → 0.83 | 2 → 6 |
| E1 +5 % | 0.97 | 0.76 | 0.48 | 0.56 | 0.99 | 0.99 | 0.79 | 0.65 | 0.98 | 0.75 | 0.96 | 0.55 → 0.81 | 2 → 5 |
| E2 −5 % | 0.97 | 0.77 | 0.49 | 0.56 | 0.99 | 0.99 | 0.79 | 0.66 | 0.98 | 0.76 | 0.96 | 0.55 → 0.81 | 2 → 5 |
| E2 +5 % | 0.97 | 0.76 | 0.60 | 0.56 | 0.99 | 0.99 | 0.79 | 0.64 | 0.98 | 0.81 | 0.96 | 0.56 → 0.82 | 2 → 6 |
| E1 −10 % | 0.97 | 0.87 | 0.66 | 0.56 | 0.99 | 0.99 | 0.79 | 0.73 | 0.98 | 0.90 | 0.96 | 0.58 → 0.85 | 3 → 7 |
| E2 −10 % | 0.97 | 0.91 | 0.61 | 0.56 | 0.99 | 0.99 | 0.79 | 0.77 | 0.98 | 0.90 | 0.96 | 0.58 → 0.86 | 3 → 7 |
| H1 (E −22.4 %) | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.56 | 0.96 | 0.51 → 0.75 | 1 → 5 |
| H2 (E −25.1 %) | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.56 | 0.96 | 0.51 → 0.75 | 1 → 5 |
| Wedge, thick at edge 4 (§18) | 0.97 | 0.54 | 0.39 | 0.57 | 0.99 | 0.98 | 0.96 | 0.74 | 0.98 | 0.75 | 0.94 | 0.52 → 0.80 | 2 → 6 |
| Field of 20 readings (§19) | 0.97 | 0.72 | 0.49 | 0.53 | 0.97 | 0.99 | 0.96 | 0.58 | 0.98 | 0.59 | 0.87 | 0.52 → 0.79 | 3 → 6 |
| *Expectation E2 = 41 000 (§22.8; not a solve)* | *0.97* | *0.97* | *0.68* | *0.56* | *0.99* | *0.99* | *0.79* | *0.81* | *0.98* | *0.97* | *0.96* | *0.59 → 0.88* | *3 → 8* |

- **Records 1, 5, 6, 9 and 11 are at 0.87–0.99 in every model.** They do not distinguish the models.
- **G12 and a common E change no shape.** The eight models with E1 = E2 and uniform thickness give the baseline row.
- **E1 ≠ E2 raises records 2, 8 and 10.** With E2 −10 %: 0.52 → 0.91, 0.43 → 0.77 and 0.57 → 0.90. Both signs of
  E1 − E2 separate the pairs and raise these values; the sign is addressed in §24.6.
- **The thickness models raise record 7** to 0.96 (0.79 in every uniform model), and the wedge raises record 8 to
  0.74.
- **Records 3 and 4 stay low in every archived model** (at most 0.66 and 0.57). Record 8 stays below 0.80 in every
  archived model (at most 0.77).
- **Best archived value per record:** 0.97, 0.91, 0.66, 0.57, 0.99, 0.99, 0.96, 0.77, 0.98, 0.90, 0.96. They come
  from different models; no single archived model reaches them together.

### 24.5 The alternative geometries

Research MAC with the first-ranked FE mode, baseline and expectation.

| Geometry | Model | EXP 1 | EXP 2 | EXP 3 | EXP 4 | EXP 5 | EXP 6 | EXP 7 | EXP 8 | EXP 9 | EXP 10 | EXP 11 | Mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Nominal of §17 (superseded) | Baseline | 0.91 | 0.60 | 0.31 | 0.55 | 0.48 | 0.52 | 0.79 | 0.43 | 0.26 | 0.15 | 0.54 | 0.50 |
| **Corrected 261016** | Baseline | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 0.99 | 0.79 | 0.43 | 0.98 | 0.57 | 0.96 | 0.75 |
| Corrected, unattended edge fit | Baseline | 0.97 | 0.52 | 0.45 | 0.55 | 0.98 | 0.99 | 0.79 | 0.43 | 0.98 | 0.57 | 0.95 | 0.74 |
| 279.2 mm, same centre | Baseline | 0.97 | 0.52 | 0.44 | 0.56 | 0.97 | 0.98 | 0.78 | 0.42 | 0.95 | 0.56 | 0.94 | 0.74 |
| 279.2 mm, plate centre | Baseline | 0.97 | 0.52 | 0.44 | 0.56 | 0.97 | 0.98 | 0.78 | 0.42 | 0.95 | 0.56 | 0.94 | 0.74 |
| Nodal-line control of §22.4 (quoted, built from modal shapes) | Baseline | 0.97 | 0.52 | 0.45 | 0.56 | 0.99 | 1.00 | 0.80 | 0.43 | 0.99 | 0.57 | 0.96 | 0.75 |
| Nominal of §17 (superseded) | *Expectation* | 0.91 | 0.97 | 0.33 | 0.55 | 0.48 | 0.52 | 0.79 | 0.92 | 0.26 | 0.25 | 0.55 | 0.59 |
| **Corrected 261016** | *Expectation* | 0.97 | 0.97 | 0.68 | 0.56 | 0.99 | 0.99 | 0.79 | 0.81 | 0.98 | 0.97 | 0.96 | 0.88 |
| 279.2 mm, same centre | *Expectation* | 0.97 | 0.97 | 0.67 | 0.56 | 0.97 | 0.98 | 0.78 | 0.80 | 0.95 | 0.94 | 0.94 | 0.87 |
| 279.2 mm, plate centre | *Expectation* | 0.97 | 0.97 | 0.67 | 0.56 | 0.97 | 0.98 | 0.78 | 0.80 | 0.95 | 0.94 | 0.94 | 0.87 |

- **The open 3 % of the 261027 window size does not affect any conclusion of this section.** Over the 16 models and
  the expectation, the 279.2 mm geometries change no first-ranked FE mode. The largest change of a first-ranked MAC
  is 0.034 (same centre) and 0.033 (plate centre).
- **The bottom-edge question does not either.** The unattended edge fit changes no first-ranked mode and no
  first-ranked MAC by more than 0.017.
- **No geometry is chosen by these numbers.** The primary geometry was fixed by the instrument record and the owner's
  statement before any of them was computed. The 279.2 mm rows are slightly lower; that is not evidence for or
  against either size.
- **The nodal-line control of §22.4 is no longer needed.** The instrument-based positions give the same values to
  0.01–0.02 without using a mode shape. Where the corrected positions put the experimental nodal lines:

| Record | Class (§22) | FE nodal lines, mm | Corrected positions, mm | Nominal mapping of §17, mm |
|---|---|---|---|---|
| 2 | Y, order 1 | 67.2, 232.8 | 67.7, 228.3 | 67.7, 228.4 |
| 7 | Y, order 2 | 39.6, 150.0, 260.4 | 41.2, 149.1, 256.6 | 41.3, 149.2, 256.7 |
| 3 | X, order 1 | 67.5, 233.5 | 73.3, 233.3 | 106.2, 226.1 |
| 9 | X, order 2 | 39.8, 150.5, 261.2 | 42.7, 150.2, 258.8 | 83.2, 163.8, 245.3 |

  The lines of the X records now lie within 5.9 mm of the FE lines, as those of the Y records do (within 4.5 mm).
  This is a consequence of the correction and was not used to make it.

### 24.6 Frequencies of the first-ranked modes

Signed error of the first-ranked FE mode, corrected positions; research MAC in brackets.

| EXP | Hz | Baseline | H1 (E −22.4 %) | E2 −10 % | Wedge (§18) | Field (§19) | *Expectation E2 = 41 000* |
|---|---|---|---|---|---|---|---|
| 1 | 18.63 | FE 7: +2.4 % (0.97) | FE 7: −0.0 % (0.97) | FE 7: +2.3 % (0.97) | FE 7: +2.0 % (0.97) | FE 7: +4.5 % (0.97) | *FE 7: +2.1 % (0.97)* |
| 2 | 54.62 | FE 9: +13.5 % (0.52) | FE 9: +0.0 % (0.52) | FE 8: +5.6 % (0.91) | FE 8: +8.7 % (0.54) | FE 8: +10.2 % (0.72) | *FE 8: −4.4 % (0.97)* |
| 3 | 63.50 | FE 8: −5.7 % (0.45) | FE 8: −16.9 % (0.45) | FE 9: −3.9 % (0.61) | FE 9: −3.2 % (0.39) | FE 9: −0.3 % (0.49) | *FE 9: −4.2 % (0.68)* |
| 4 | 66.85 | FE 11: +8.0 % (0.56) | FE 11: −1.9 % (0.56) | FE 10: +4.0 % (0.56) | FE 11: +7.9 % (0.57) | FE 10: +9.6 % (0.53) | *FE 10: −3.0 % (0.56)* |
| 5 | 74.21 | FE 10: −3.2 % (0.99) | FE 10: −12.0 % (0.99) | FE 11: −3.2 % (0.99) | FE 10: −3.8 % (0.99) | FE 11: −0.2 % (0.97) | *FE 11: −3.4 % (0.99)* |
| 6 | 112.27 | FE 12: +3.8 % (0.99) | FE 12: −4.1 % (0.99) | FE 12: +2.3 % (0.99) | FE 12: +3.3 % (0.98) | FE 12: +4.9 % (0.99) | *FE 12: −0.4 % (0.99)* |
| 7 | 145.94 | FE 14: +15.5 % (0.79) | FE 14: +1.8 % (0.79) | FE 13: +9.6 % (0.79) | FE 13: +12.5 % (0.96) | FE 13: +13.8 % (0.96) | *FE 13: −1.2 % (0.79)* |
| 8 | 157.85 | FE 16: +14.0 % (0.43) | FE 16: +1.6 % (0.43) | FE 15: +7.0 % (0.77) | FE 16: +14.3 % (0.74) | FE 16: +15.9 % (0.58) | *FE 14: −2.0 % (0.81)* |
| 9 | 169.18 | FE 13: −1.0 % (0.98) | FE 13: −12.8 % (0.98) | FE 14: −1.0 % (0.98) | FE 14: −1.6 % (0.98) | FE 14: −0.0 % (0.98) | *FE 15: −1.0 % (0.98)* |
| 10 | 180.14 | FE 15: −3.0 % (0.57) | FE 15: −13.5 % (0.56) | FE 16: −1.5 % (0.90) | FE 15: −3.0 % (0.75) | FE 15: −1.3 % (0.59) | *FE 16: −1.8 % (0.97)* |
| 11 | 191.60 | FE 18: +11.7 % (0.96) | FE 18: +1.5 % (0.96) | FE 17: +8.1 % (0.96) | FE 18: +11.2 % (0.94) | FE 18: +12.3 % (0.87) | *FE 17: +1.7 % (0.96)* |
| Mean absolute error, records with MAC ≥ 0.50, before → after | | 9.2 → 6.9 % | 1.5 → 5.3 % | 5.6 → 4.4 % | 9.1 → 6.8 % | 11.1 → 7.3 % | *2.1 → 2.3 %* |
| Records with MAC ≥ 0.50, before → after | | 6 → 9 | 6 → 9 | 7 → 11 | 5 → 10 | 4 → 10 | *7 → 11* |

- **The direction-dependent pattern is now carried by identified modes.** In the baseline, record 11 (MAC 0.96, a
  mode governed by curvature along FE Y, §22.6) is 11.7 % too high. Records 5 and 9 (0.99 and 0.98, governed by
  curvature along FE X) are 3.2 % and 1.0 % too low. Records 1 and 6 (twist, and both directions) are 2.4 % and
  3.8 % too high. In §22 this pattern rested on the class order alone.
- **A common lower E is excluded more firmly than before.** With H1 the records 5 and 9 are 12.0 % and 12.8 % too
  low at MAC 0.99 and 0.98. The earlier mean of 1.5 % for H1 (§20.3) was a mean over the six records that reached
  0.50 with the old positions, and those were mostly the Y-governed ones.
- **The thickness models leave the Y-governed records 11–16 % too high** (records 7, 8, 11) while matching the shape
  of record 7.
- **The first-ranked modes of §17–§20 that changed:** record 3 in 15 of the 16 models (all but E2 −10 %). Every
  other first-ranked mode is the one of the earlier tables; what changed is its MAC.

### 24.7 The directional stiffness hypothesis, reassessed

What does not depend on the point positions is unchanged from §22: the whole-plate classes of the FE modes, the
class frequencies and ratios (§22.5), the class-order table (§22.6), the origin of E2 = 41 000 MPa and the
falsification criteria (§22.8). What depends on the positions was recomputed.

**The scan window no longer distorts the classes.**

| Shape | Nominal window of §17: X share, Y share, parity | Corrected window: X share, Y share, parity |
|---|---|---|
| X, order 1 | 1.00 (2), 0.29, SS 0.88 | 1.00 (2), 0.00, SS 1.00 |
| X, order 2 | 1.00 (**2**), 0.00, AS 0.84 | 1.00 (3), 0.00, AS 1.00 |
| 0.8 X1 + 0.6 Y1 | 0.53, 0.61, SS 0.94 | 0.64, 0.36, SS 1.00 |
| Twist | 0.00, 0.04, AA 0.96 | 0.00, 0.00, AA 1.00 |

- The corrected window is centred on the plate to 0.2 mm along X and 1.1 mm along Y. The descriptor of §21.5 then
  returns the direction, order and parity of the synthetic shapes exactly, as on the whole plate (§22.3).
- For the 16 FE models the one-direction class seen in the window equals the whole-plate class for all 224 modes
  (185 of 224 with the old window).
- Axis check of §22.2 with the corrected positions: one step of grid index u is +17.79 mm in FE Y, one step of v is
  −17.86 mm in FE X (−13.40 mm before). The directions are unchanged: curvature along u is curvature along FE Y.

**Research MAC of each record with the FE mode of its class order** (§22.6: the k-th record of a parity class
against the k-th FE mode of that class; no MAC and no frequency closeness enter the correspondence), before → after:

| Model | EXP 1 | EXP 2 | EXP 3 | EXP 4 | EXP 5 | EXP 6 | EXP 7 | EXP 8 | EXP 9 | EXP 10 | EXP 11 | Mean | First-ranked mode = class-order mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | 0.91 → 0.97 | 0.57 → 0.45 | 0.09 → 0.25 | 0.55 → 0.56 | 0.48 → 0.99 | 0.52 → 0.99 | 0.79 → 0.79 | 0.36 → 0.37 | 0.26 → 0.98 | 0.13 → 0.41 | 0.54 → 0.96 | 0.47 → 0.70 | 7 of 11 |
| H1 (E −22.4 %) | 0.91 → 0.97 | 0.57 → 0.45 | 0.09 → 0.25 | 0.55 → 0.56 | 0.49 → 0.99 | 0.52 → 0.99 | 0.79 → 0.79 | 0.36 → 0.38 | 0.26 → 0.98 | 0.13 → 0.41 | 0.55 → 0.96 | 0.47 → 0.70 | 7 of 11 |
| E2 −10 % | 0.91 → 0.97 | 0.94 → 0.91 | 0.28 → 0.61 | 0.55 → 0.56 | 0.48 → 0.99 | 0.52 → 0.99 | 0.79 → 0.79 | 0.86 → 0.77 | 0.26 → 0.98 | 0.24 → 0.90 | 0.54 → 0.96 | 0.58 → 0.86 | 11 of 11 |
| Wedge (§18) | 0.92 → 0.97 | 0.64 → 0.54 | 0.17 → 0.39 | 0.50 → 0.57 | 0.47 → 0.99 | 0.48 → 0.98 | 0.97 → 0.96 | 0.18 → 0.21 | 0.24 → 0.98 | 0.07 → 0.22 | 0.46 → 0.94 | 0.46 → 0.70 | 9 of 11 |
| Field (§19) | 0.93 → 0.97 | 0.80 → 0.72 | 0.21 → 0.49 | 0.49 → 0.53 | 0.48 → 0.97 | 0.49 → 0.99 | 0.96 → 0.96 | 0.31 → 0.36 | 0.24 → 0.98 | 0.10 → 0.38 | 0.43 → 0.87 | 0.50 → 0.75 | 9 of 11 |
| *Expectation E2 = 41 000* | *0.91 → 0.97* | *0.97 → 0.97* | *0.33 → 0.68* | *0.55 → 0.56* | *0.48 → 0.99* | *0.52 → 0.99* | *0.79 → 0.79* | *0.92 → 0.81* | *0.26 → 0.98* | *0.25 → 0.97* | *0.55 → 0.96* | *0.59 → 0.88* | *11 of 11* |

**Supported more strongly than in §22:**

1. **Shapes and class order now agree.** In the three archived models with E2 below E1 (E1 +5 %, E2 −5 %, E2 −10 %)
   the first-ranked FE mode of every record is the mode of its class order: 11 of 11. In the models with E1 = E2 it
   is 7 of 11, in the two thickness models 9 of 11, and in the three models with E1 below E2 it is 7 of 11. The
   class order uses no MAC, and the first rank uses no class.
2. **The softer direction is seen in the shapes, not only in the frequencies.** With E2 below E1 the Y-governed
   member of each mixed pair is the lower one, and the records follow that order. With E1 below E2 the pairs
   separate as well, but in the opposite order, and the class-order MAC falls (mean 0.59 for E1 −10 % against 0.86
   for E2 −10 %).
3. **The frequency pattern is carried by modes identified at 0.96–0.99** (§24.6).
4. **The expectation for E2 = 41 000 MPa improves on every archived model:** mean 0.88, eight records at 0.80 or
   above, every first-ranked mode within 4.4 % in frequency, and records 2 and 10 at 0.97.

**Not shown, or against it (unchanged from §22.7 unless stated):**

- **No model with the ratio has been solved.** The expectation is a reduced-basis estimate.
- **The cause is not identified,** and the ratio is not a material value (`NOT_A_MATERIAL_PROPERTY`).
- **Records 3 and 4 are not explained by a stiffness ratio.** They stay at 0.68 and 0.56 in the expectation. Both
  lie 0.96 and 0.98 inside the span of FE 8–11: they are mixtures of the SS and AS classes, which a homogeneous
  orthotropic plate keeps apart.
- **Record 7 is not explained by a stiffness ratio either** (0.79 in every uniform model). The thickness models
  bring it to 0.96. A stiffness ratio and a thickness asymmetry along X act on different records; both may be
  present. That remains a hypothesis.
- **Record 8 changes its expected value:** 0.92 with the old positions, 0.81 with the corrected ones. The earlier
  value was a product of the compressed window.
- **Session 261016** gives another order-1 ratio (0.811 against 0.860), and the residual between the orders
  (§22.7) is untouched by this section.
- **The mapping is instrument-based for 261016 only.** For 261027 it rests on the owner's statement.
  `PHYSICAL_REGISTRATION_NOT_VERIFIED` stands.

**Verdict.** The directional stiffness hypothesis is consistent with the frequencies, the classes and, with the
corrected positions, the shapes of 8 of the 11 records. A common modulus, G12, and the two thickness models are
each excluded as the single explanation. The hypothesis is **not confirmed**: nothing has been solved with the
ratio, records 3, 4 and 7 need something else, and no value is released.

### 24.8 The proposed test, and the recommendation for the next FE step

> **Executed (§25, 2026-11-26):** the test was solved once under the owner's authorisation. Criteria 1, 2 and 3 are met. The text below is kept as written before the solve.

- **Recommendation: the one test of §22.8, unchanged.** `S4R_0875_BASELINE` with E2 = 41 000 MPa; one
  eigenfrequency solve and one ODB extraction, each under a separate owner authorisation. The value comes from the
  experimental frequencies and the plan alone and does not depend on the point positions.
- **The three falsification criteria of §22.8 stand as written.** They are whole-plate quantities.
- **The reported expectation changes.** Expected research MAC with the corrected positions, records 1–11: 0.97,
  0.97, 0.68, 0.56, 0.99, 0.99, 0.79, 0.81, 0.98, 0.97, 0.96. The two lists of §22.8 (old positions and nodal-line
  control) are superseded. As before, these are reported, not criteria.
- **What the solve can now show that it could not before.** With the old positions seven records could not be
  judged by shape. With the corrected positions the solve is expected to give seven records at 0.96–0.99 and to
  leave 3, 4, 7 and 8 at 0.56–0.81. If the solved shapes of records 2 and 10 stay near the baseline values (0.52,
  0.57), the reduced basis is wrong about the pair separation, whatever the frequencies do.
- **Not recommended now.** A model that combines the ratio with the wedge thickness would address record 7. It
  should wait for the result of the single-parameter test, so that each change can be read by itself.

### 24.9 What is superseded, and what stays open

**Superseded for current research conclusions.** The earlier text and tables are kept as written; each affected
section now carries a note that points here.

| Section | Superseded | Still valid |
|---|---|---|
| §17 | the research MAC table, the labels, the first-ranked modes and the scenario ranges; the reading of the near-square control of §17.5 | the method, the metric, the levels, the placement convention |
| §18, §19 | every FE / EXP MAC value and the comparison of the models by MAC | the extraction, the thickness field, the FE-to-FE tracking, the frequencies |
| §20 | the MAC tables; "seven records explained by no model" (§20.5); the mean frequency errors over records with MAC ≥ 0.50 (§20.3) | variant identities, FE-to-FE tracking, the sensitivity of the FE frequencies |
| §21 | the statement that the low MAC of records 5, 6, 9, 10, 11 is a discrepancy of the FE model (already qualified in §22.9) | every experimental quantity |
| §22 | the window descriptors of §22.3; the nodal-line control and its MAC table (§22.4); the expected MAC lists of §22.8 | §22.2, §22.5, §22.6, the origin of the test value, the falsification criteria |
| §23 | "not recomputed" (§23.8) | everything else |

**Open for the owner.**

1. **The governed tool.** `tools/reconstruct_psv_registration.py` still calls the earlier reading, because the
   SP-02 and SP-13 records and their reproduction tests depend on it and are outside this task. Whether the tool
   moves to the corrected reading, and whether those two records are re-examined on their own instrument files, is
   a decision about accepted evidence (§23.8, item 2).
2. **The nominal mapping file.** `plate_reconstruction_W301xH300.json` is unchanged. This section uses the corrected
   positions for research; any program function that reads that file still reads the old positions.
3. **The 261027 window.** Its size (279 or 287 mm) and offsets stay unrecorded. This section shows that the open
   3 % does not change a conclusion; it does not close the question.
4. **Authorisation of the E2 = 41 000 MPa solve and extraction.** (Given on 2026-11-26; see §25.)

### 24.10 Limitations

- `PHYSICAL_REGISTRATION_NOT_VERIFIED`: the 261027 positions are the 261016 positions on the owner's statement;
  placement D is a convention; D-044 and SPEC §5.2 stand.
- The corrected reading was run on one real instrument file. Its stream offsets are validated on that file and on
  synthetic files. The SP-02 and SP-13 files were not opened, so it is not known whether the reading accepts them.
- The reading supports one axis-parallel rectangular scan object. Every other case is refused, including the case
  where the file does not decide (§24.1).
- The bottom plate edge of the 261016 frame still needs M11 deviation 3. The positions are uncertain at 1–3 mm
  (§23.6); the scenarios of §24.3 cover ± 3 mm and 0.87°.
- The expectation for E2 = 41 000 MPa is not a solve (**solved in §25; the expectation is confirmed**). Suspension, force
  sensor and interior thickness remain unmodelled (§20.4).
- Labels and MAC values are research quantities. No pairing status and no parameter value follows from them.

### 24.11 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `d1da1c00…` and a clean tracked tree before the edit |
| Source hashes | 30 inputs equal their recorded hashes (instrument file, 261016 export, M11 record, baseline package, results and arrays of §19, §20, §22, §23); all unchanged in size, mtime and SHA-256 after the run |
| Governed evidence | `docs/auto_id`, `docs/registrations` and `docs/baseline` have no difference to HEAD; SP-13 record `c30b78d8…` and SP-02 record `f42e69a1…` as recorded in §23 |
| Earlier reading unchanged | on three synthetic instrument files the changed module and the module at `d1da1c0` give byte-identical v1 records and identical points |
| Corrected reconstruction, 261016 | 287.1 × 285.3 mm with the recorded plate corners, equal to §23 (0.0 mm); 287.1 × 285.7 mm unattended; frame of the points resolved from the file (hull against scan object 0.0004 px, the three other trials 146–341 px) |
| Coordinate transformations | corrected pixels reproduce a known synthetic grid to 1·10⁻³ px for four frame layouts (wide frame with a 4 : 3 point frame; one frame only; a 4 : 3 camera; a 1280 × 1024 frame with other rectangles) |
| Defect regression | the earlier reading on a synthetic file returns 0.750 of the true width with unequal side gaps and an unaffected vertical axis; the corrected reading returns the true positions to 0.6 mm |
| Refusals | 9 tests: no consistent frame, undecidable frame, disagreeing rectangles, unsupported or missing scan object, invalid rectangles, unknown reading |
| MAC reproduction | with the old positions the recomputed MAC equals §20 (6.7·10⁻¹⁶), §19 (3.3·10⁻¹⁶) and the expectation of §22.8 (0.0); FE-to-FE assignment equals §20 for every tracked branch |
| Reproducibility | two complete runs give byte-identical `results.json` (`87b8e042…`), `arrays.npz` (`3a7217be…`) and `protocol.json` (`d9b0bf5e…`) |
| Tests | `tests.test_psv_video_registration` (new): 22 OK. `tests.test_physical_registration`: 24 OK. `tests.test_sp13_physical_registration`: 17 OK (4 skipped). `tests.test_sp02_physical_registration`: 18 OK (6 skipped). `tests.test_plate_physical_review`: 36 OK. `tests.test_plate_registration_readiness`: 18 OK. `tests.test_plate_study`: 30 OK. `tests.test_plate_rc1_owner_clarification`: 12 OK. `research/m11_r65`: 29 OK. The skips are the suites' own (stores not configured) |

Changed in the repository: `src/services/psv_video_registration.py`, `tests/test_psv_video_registration.py` (new)
and this report.

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_SCAN_NORMALIZATION_FIX_01` (outside git): `run_fix.py`,
`protocol.json`, `results.json`, `arrays.npz`, `report.py`, `tables.md`, `legacy_equivalence.py`,
`fig_mac_baseline_before_after.png`, `fig_first_ranked_all_models.png`, `fig_point_geometries.png`,
`fig_frequency_error_first_ranked.png`.

## 25. PLATE-0875-DIRECTIONAL-FE-TEST-01 — the prospective test of §22.8 solved: E2 = 41 000 MPa (2026-11-26)

`RESEARCH_ONLY`, `PHYSICAL_REGISTRATION_NOT_VERIFIED`, `NOT_A_MATERIAL_PROPERTY`. One isolated numerical test of the
directional bending stiffness hypothesis. It is not a material identification: no parameter was fitted, no LM or
Auto-ID was run, no value is released, no pairing status and no `FrozenRegistration` were produced. The
identification pipeline is unchanged and still has E1 = E2. M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and
production Auto-ID BLOCKED are unchanged. No program code, test, registration, gate or tool was changed.

**Abaqus use (owner authorisation: exactly one solve and one corresponding extraction).**

| Action | Count | Detail |
|---|---|---|
| Abaqus solves | **1** | `CFRP_S4R_0875_E2_41000_FreeFree`, Abaqus/Standard 2024, cpus = 1, interactive; 2026-11-26 15:13:42, 12.6 s, exit 0; no retry |
| ODB extractions | **1** | pinned extractor `039aa067…`, modes 1–20; 15:14:02, 5.4 s, exit 0; the ODB is unchanged by it; no retry |

**Short answer.** All three prospective criteria of §22.8 are met.

| Criterion (§22.8, written before the solve) | Result | Verdict |
|---|---|---|
| 1. Class sequence of FE 7–17 | AA, SS (Y1), SS (X1), AS, SA, SS, SA (Y2), AA, AS (X2), AA, SA — the required sequence | **PASS** |
| 2. FE mode of the class order within ± 5 % of each of the 11 records | largest error 4.38 % (record 2); mean 2.29 %; no record outside | **PASS** |
| 3. Solved frequencies of FE 7–18 within 1 % of the reduced-basis expectation | largest difference 0.049 % | **PASS** |

- **Frequencies.** With E2 = 41 000 MPa the mean error of the class-order modes falls from 6.2 % (baseline, largest
  15.5 %) to 2.3 % (largest 4.4 %).
- **Shapes.** The predicted separation of the mixed pairs occurs: records 2, 8 and 10 rise from 0.52, 0.43 and 0.57
  to 0.97, 0.81 and 0.97. Eight records are at 0.81–0.99.
- **Not explained.** Records 3, 4 and 7 stay at 0.68, 0.56 and 0.79, exactly as expected. A single stiffness ratio
  does not describe their shapes.
- **What the solve adds.** It confirms the reduced-basis expectation of §22.8 / §24.8 (frequencies to 0.05 %,
  research MAC to 0.0004). It gives no comparison with the experiment that §24 did not already predict.
- **What it does not show.** The cause of the ratio, a value of E1 or E2, or a pairing. Passing the test means that
  one bending stiffness ratio describes the 11 frequencies of this plate in the 261027 setup within ± 5 %.

### 25.1 The model and the single change

| Item | Value |
|---|---|
| Base | `S4R_0875_BASELINE`, `CFRP_S4R_0875_FreeFree.inp`, SHA-256 `962f75f2…` (= `research/m11_r65/expected_inputs.json`), read only |
| Test input | `CFRP_S4R_0875_E2_41000_FreeFree.inp`, SHA-256 `bab9b7ed…`, written before the solve |
| Difference | one line of 20 264, line 20239: `56000.,56000., 8500., …` → `56000.,41000., 8500., …`; equal byte length; every other byte identical |
| Parsed constants | E1 = 56 000, **E2 = 41 000**, E3 = 8 500, ν12 = 0.05, ν13 = ν23 = 0.3, G12 = 5 000, G13 = G23 = 3 000 MPa; only E2 differs from the baseline |
| Unchanged | mesh (10 201 nodes, 10 000 S4R), thickness 0.875 mm, density, free-free conditions, step, 20 requested modes |
| Mass | 118.361 g in the `.dat`, equal to the baseline; centre of mass (150.5, 150.0, 0) |

The criteria, the expectation and the geometry for the research MAC were written to `protocol.json`
(`e1b6b9db…`) before the solve. Nothing in it was edited afterwards.

### 25.2 Solver completion and extraction integrity

| Check | Result |
|---|---|
| Solve | "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in `.sta`; `JOB … COMPLETED` in the console log; exit 0 |
| Messages | 0 errors and 0 warnings in `.dat`; `.msg`: 0 warning messages, 0 error messages |
| Rigid modes | modes 1–6 below 0.01 Hz; no non-positive eigenvalue among modes 7–20 |
| Extraction | exit 0; 22 files (geometry, manifest, 20 modes); 20 "Extracted mode" lines; 10 201 nodes |
| ODB | SHA-256 `4e0f4ef2…` before and after the extraction |
| Frequencies | manifest = `.dat` for modes 7–20 (relative difference 0.0) |
| Geometry | node labels, coordinates and connectivity equal the baseline package; INP nodes reproduce the extracted geometry to 1.5·10⁻⁵ mm |
| Field | in-plane displacement / U3 at most 1.5·10⁻¹¹ |

`.dat` `efcde38b…`, manifest `179a6ef3…`. The 30 solve and extraction files were hashed once after the extraction
(`identity.json`) and are verified at every analysis run.

### 25.3 Actual against predicted frequencies

Whole-plate class as in §22 (parity about the two centre lines; a one-direction class where the share is 0.70 or
more). "Expected" is the reduced-basis value of §22.8.

| FE mode | Solved, Hz | Expected, Hz | Solved − expected | Shape MAC, solved / expected | Class on the whole plate | Baseline branch |
|---|---|---|---|---|---|---|
| 7 | 19.018 | 19.019 | −0.006 % | 1.0000 | AA | FE 7 |
| 8 | 52.229 | 52.230 | −0.001 % | 1.0000 | SS, **Y1** | FE 8 and 9 in equal parts |
| 9 | 60.811 | 60.811 | 0.000 % | 1.0000 | SS, **X1** | FE 8 and 9 in equal parts |
| 10 | 64.817 | 64.834 | −0.027 % | 1.0000 | AS | FE 11 |
| 11 | 71.711 | 71.714 | −0.004 % | 1.0000 | SA | FE 10 |
| 12 | 111.79 | 111.845 | −0.049 % | 0.9999 | SS | FE 12 |
| 13 | 144.26 | 144.249 | +0.007 % | 1.0000 | SA, **Y2** | FE 14 |
| 14 | 154.71 | 154.722 | −0.008 % | 1.0000 | AA | FE 15 and 16 in equal parts |
| 15 | 167.45 | 167.451 | −0.001 % | 1.0000 | AS, **X2** | FE 13 |
| 16 | 176.83 | 176.834 | −0.002 % | 1.0000 | AA | FE 15 and 16 in equal parts |
| 17 | 194.82 | 194.898 | −0.040 % | 0.9999 | SA | FE 18 |
| 18 | 210.07 | 210.155 | −0.040 % | 0.9997 | AS | FE 17 |
| 19 | 281.38 | 281.506 | −0.045 % | 0.9998 | AA | FE 19 |
| 20 | 282.86 | (321.083) | (−11.9 %) | (0.17) | SS | not in the baseline FE 7–20 |

- **Criterion 3: PASS.** The largest difference for FE 7–18 is 0.049 %, against the limit of 1 %. The reduced basis
  is valid at this step, which is larger than any archived one (E2 −27 %).
- **FE 20 is outside the criterion,** as §22.8 stated. The solved FE 20 (282.86 Hz, SS) lies 83 % outside the span
  of the 14 baseline shapes: it is a mode that the baseline has above its FE 20, and a 14-shape basis cannot contain
  it. It is above every record and enters no result.
- The `.dat` and the manifest give five significant digits; the differences are at that resolution.

### 25.4 Whole-plate classes (criterion 1) and branch tracking

**Criterion 1: PASS.** The parity classes of the solved FE 7–17 in ascending frequency are AA, SS, SS, AS, SA, SS,
SA, AA, AS, AA, SA, with FE 8 = Y1, FE 9 = X1, FE 13 = Y2 and FE 15 = X2. This is the required sequence, and the
sequence of the 11 records. The smallest parity share of a mode is 1.000: a homogeneous material keeps the classes
apart. The class of each mode seen in the corrected scan window equals its whole-plate class for all 14 modes.

**Tracking against the baseline** (FE-to-FE real MAC of U3 on all 10 201 nodes, assignment as in §20; tracked at
0.90 or more):

| Baseline | Hz | Class | Solved | Hz | MAC | Status | Frequency change |
|---|---|---|---|---|---|---|---|
| 7 | 19.07 | AA | 7 | 19.02 | 1.00 | tracked | −0.3 % |
| 8 | 59.87 | SS | 8 | 52.23 | 0.50 | lost | (−12.8 %) |
| 9 | 62.01 | SS | 9 | 60.81 | 0.50 | lost | (−1.9 %) |
| 10 | 71.85 | SA | 11 | 71.71 | 1.00 | tracked | −0.2 % |
| 11 | 72.19 | AS | 10 | 64.82 | 1.00 | tracked | −10.2 % |
| 12 | 116.58 | SS | 12 | 111.79 | 1.00 | tracked | −4.1 % |
| 13 | 167.49 | AS | 15 | 167.45 | 1.00 | tracked | −0.0 % |
| 14 | 168.61 | SA | 13 | 144.26 | 1.00 | tracked | −14.4 % |
| 15 | 174.80 | AA | 16 | 176.83 | 0.51 | lost | (+1.2 %) |
| 16 | 179.90 | AA | 14 | 154.71 | 0.51 | lost | (−14.0 %) |
| 17 | 213.20 | AS | 18 | 210.07 | 1.00 | tracked | −1.5 % |
| 18 | 213.95 | SA | 17 | 194.82 | 1.00 | tracked | −8.9 % |
| 19 | 295.78 | AA | 19 | 281.38 | 1.00 | tracked | −4.9 % |
| 20 | 327.90 | SS | — | — | 0.17 | lost | — |

- **9 of 14 branches tracked,** each with MAC 1.00 and none with a changed class. The branches governed by
  curvature along FE Y fall by 8.9–14.4 % (FE 11, 14, 18; √(41 / 56) = 0.856 is −14.4 %). Those governed by
  curvature along FE X and the twist stay within 0.3 % (FE 7, 10, 13). FE 12, 17 and 19 lie between (−1.5 to −4.9 %).
- **Lost: 8, 9, 15, 16 and 20,** the same five as in every archived model with E1 ≠ E2 (§20.1). Each solved mode of
  the pairs is an equal mixture of the two baseline modes (0.50 / 0.50 and 0.49 / 0.51), so no branch can be
  followed individually. The two-mode subspaces are kept: the largest principal angle to the baseline pair is 0.17°
  (FE 8 / 9) and 0.72° (FE 14 / 16). The bracketed frequency changes of lost branches are not branch quantities.
- **Order exchanges:** 10 ↔ 11, 17 ↔ 18, and 14 → 13 with 13 → 15. In each close pair the Y-governed mode is now the
  lower one, as predicted.
- **Close modes.** The baseline has four close pairs among FE 7–18 (10 / 11, 13 / 14, 15 / 16, 17 / 18). The solved
  model has none: the only close group by the existing trigger is FE 19 / 20, above the records.

### 25.5 Class frequencies (criterion 2) and the residuals

The k-th record of a parity class against the k-th FE mode of that class (§22.6). No MAC and no frequency closeness
enter the correspondence. In the solved model it is record k against FE 6 + k.

| EXP | Hz | Class | FE mode | Solved, Hz | Error | Expected error (§22.8) | Baseline error (§22.6) | Role |
|---|---|---|---|---|---|---|---|---|
| 1 | 18.63 | AA | 7 | 19.018 | +2.08 % | +2.1 % | +2.4 % | test |
| 2 | 54.62 | SS | 8 | 52.229 | **−4.38 %** | −4.4 % | +9.6 % | gave the ratio |
| 3 | 63.50 | SS | 9 | 60.811 | −4.23 % | −4.2 % | −2.3 % | gave the ratio |
| 4 | 66.85 | AS | 10 | 64.817 | −3.04 % | −3.0 % | +8.0 % | test |
| 5 | 74.21 | SA | 11 | 71.711 | −3.37 % | −3.4 % | −3.2 % | test |
| 6 | 112.27 | SS | 12 | 111.79 | −0.42 % | −0.4 % | +3.8 % | test |
| 7 | 145.94 | SA | 13 | 144.26 | −1.15 % | −1.2 % | +15.5 % | gave the ratio |
| 8 | 157.85 | AA | 14 | 154.71 | −1.99 % | −2.0 % | +10.7 % | test |
| 9 | 169.18 | AS | 15 | 167.45 | −1.03 % | −1.0 % | −1.0 % | gave the ratio |
| 10 | 180.14 | AA | 16 | 176.83 | −1.84 % | −1.8 % | −0.1 % | test |
| 11 | 191.60 | SA | 17 | 194.82 | +1.68 % | +1.7 % | +11.7 % | test |
| Mean absolute | | | | | 2.29 % | | 6.22 % | |
| Largest absolute | | | | | 4.38 % | | 15.54 % | |

- **Criterion 2: PASS.** No record is outside ± 5 %. The seven test records: mean 2.06 %, largest 3.37 %
  (record 5).
- **The margin is small where it was expected to be small:** 0.62 % at record 2 and 0.77 % at record 3. Both are
  records that gave the ratio. The ratio fixes how the Y-governed modes lie relative to the X-governed ones; it does
  not fix the common level, which comes from the archived E1 = 56 000 MPa.
- **A residual that the ratio does not remove.** The errors are small but not scattered about zero: the signed
  mean is −1.6 %. The order-1 classes (records 2–5) are
  3.0–4.4 % low, the order-2 classes (records 7–10) 1.0–2.0 % low, record 1 (twist) is 2.1 % high and record 11 is
  1.7 % high. §22.7 named this residual between the orders before the solve. A stiffness ratio cannot change it.
- **Both directions are now equal.** Y-governed records 2, 7, 8, 11: −4.4, −1.1, −2.0, +1.7 %. X-governed records
  3, 5, 9, 10: −4.2, −3.4, −1.0, −1.8 %. The direction-dependent pattern of the baseline (§24.6) is gone.
- **FE 18 (210.07 Hz, AS) has no record.** The stored response has no local maximum of 1 dB or more between 195 and
  241 Hz (§22.7). Whether that mode was not excited or is not there is not known.
- ± 5 % is the existing descriptive level. It is not a gate and no pairing follows from it.

### 25.6 Research MAC with the corrected positions

Geometry: `CORRECTED_261016` of §24 only (287.1 × 285.3 mm, from the instrument record of 261016; used for 261027 on
the owner's statement that the same points were scanned). The superseded nominal positions were not used. Mapping,
metric, levels and labels as in §17: placement D (`CONVENTION_ONLY`), bilinear sampling of U3, complex MAC. All 11
records are kept.

**Full matrix, solved model** (values below 0.005 shown as 0.00; bold: first-ranked):

| EXP | FE 7 | FE 8 | FE 9 | FE 10 | FE 11 | FE 12 | FE 13 | FE 14 | FE 15 | FE 16 | FE 17 | FE 18 | FE 19 | FE 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **0.97** | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | 0.00 | **0.97** | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 3 | 0.00 | 0.02 | **0.68** | 0.26 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 4 | 0.00 | 0.01 | 0.41 | **0.56** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 5 | 0.00 | 0.00 | 0.00 | 0.00 | **0.99** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.99** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 7 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.79** | 0.18 | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 |
| 8 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.17 | **0.81** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 9 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.98** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 10 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | **0.97** | 0.01 | 0.00 | 0.00 | 0.00 |
| 11 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | 0.01 | **0.96** | 0.01 | 0.00 | 0.00 |

**First-ranked mode of each record:**

| EXP | Hz | Baseline (§24.3) | Expected (§24.8) | **Solved** | Solved first-ranked FE mode | Frequency error | Range over the 59 scenarios | Share in the four-mode group |
|---|---|---|---|---|---|---|---|---|
| 1 | 18.63 | 0.97 | 0.97 | **0.97** | 7 | +2.1 % | 0.96–0.97 | — |
| 2 | 54.62 | 0.52 | 0.97 | **0.97** | 8 | −4.4 % | 0.96–0.97 | 0.99 (FE 8–11) |
| 3 | 63.50 | 0.45 | 0.68 | 0.68 | 9 | −4.2 % | 0.67–0.68 | 0.96 (FE 8–11) |
| 4 | 66.85 | 0.56 | 0.56 | 0.56 | 10 | −3.0 % | 0.55–0.56 | 0.98 (FE 8–11) |
| 5 | 74.21 | 0.99 | 0.99 | **0.99** | 11 | −3.4 % | 0.97–0.99 | 0.99 (FE 8–11) |
| 6 | 112.27 | 0.99 | 0.99 | **0.99** | 12 | −0.4 % | 0.97–0.99 | — |
| 7 | 145.94 | 0.79 | 0.79 | 0.79 | 13 | −1.2 % | 0.77–0.79 | 0.98 (FE 13–16) |
| 8 | 157.85 | 0.43 | 0.81 | **0.81** | 14 | −2.0 % | 0.76–0.83 | 0.97 (FE 13–16) |
| 9 | 169.18 | 0.98 | 0.98 | **0.98** | 15 | −1.0 % | 0.96–0.98 | 0.98 (FE 13–16) |
| 10 | 180.14 | 0.57 | 0.97 | **0.97** | 16 | −1.8 % | 0.95–0.97 | 0.98 (FE 13–16) |
| 11 | 191.60 | 0.96 | 0.96 | **0.96** | 17 | +1.7 % | 0.92–0.97 | — |
| Mean | | 0.75 | 0.88 | **0.88** | | 2.3 % (absolute) | | |

- **The first-ranked mode of every record is the mode of its class order: 11 of 11.** In the baseline it is 7 of 11
  (§24.7). The first rank uses no class and the class order uses no MAC. In the solved model the first-ranked mode
  is also the one that follows the experimental order: record k with FE 6 + k.
- **Eight records at 0.80 or above** (1, 2, 5, 6, 8, 9, 10, 11), five in the baseline. All 11 are at 0.50 or above
  (nine in the baseline). Mean frequency error of the first-ranked modes: 2.3 %, against 6.9 % in the baseline over
  its nine records at 0.50 or above.
- **Solved against expected:** the largest difference of any matrix element is 0.0004. The research MAC of §24.8
  was a correct prediction of the solve.
- **Stability.** In all 59 declared shift and rotation scenarios the first-ranked mode of every record is
  unchanged. The widest range is 0.76–0.83 (record 8), which crosses 0.80.
- **Span.** Every record lies 0.96–1.00 in the span of the 14 solved shapes, as in the baseline (0.96–1.00): the
  solved shapes span the same space, differently combined.
- **Labels by the unchanged rule of §17:** records 1 and 6 `CANDIDATE_ONLY`; 3, 4 and 7 `WEAK_CANDIDATE`; 2, 5, 8,
  9, 10 and 11 `AMBIGUOUS_CLUSTER`. The last label is given because the rule tests the share in the two-mode
  subspaces of the baseline pairs, and a mode with MAC ≥ 0.80 that belongs to such a pair always passes it. In the
  solved model these pairs are no longer close in frequency (§25.4). The rule was not changed. A label is a research
  quantity; no pairing status follows.

### 25.7 Does the predicted separation of the mixed modes occur?

**Yes.** §24.8 stated the check before the solve: if records 2 and 10 stayed near their baseline values, the reduced
basis would be wrong about the pair separation, whatever the frequencies did.

| EXP | Pair in the baseline | Baseline | Expected | Solved | Solved − expected |
|---|---|---|---|---|---|
| 2 | FE 8 / 9 | 0.52 | 0.970 | 0.970 | −0.000004 |
| 8 | FE 15 / 16 | 0.43 | 0.807 | 0.807 | +0.00006 |
| 10 | FE 15 / 16 | 0.57 | 0.968 | 0.969 | +0.00003 |

- **FE 8 / 9.** The solved FE 8 is Y1 and FE 9 is X1 (one-direction share 0.99 each); in the baseline each of the
  two modes is a combination of both. Record 2 is Y1 (§21.5) and takes FE 8 at 0.97.
- **FE 14 / 16.** The baseline pair FE 15 / 16 separates into two AA modes at 154.71 and 176.83 Hz, on either side
  of X2 (22 Hz apart; 5 Hz in the baseline). By the energy shares of the reduced basis (§22.8), whose shapes equal
  the solved ones at MAC 1.0000, the lower is Y-governed and the upper X-governed. Records 8 and 10 take them at
  0.81 and 0.97.
- **Not separated by this model, as expected (§22.8, §24.7):**
  - Records 3 and 4 (0.68 and 0.56). Each has a second FE mode at 0.26 and 0.41: record 3 with FE 9 (SS) and FE 10
    (AS), record 4 with FE 10 and FE 9. Both lie 0.96 and 0.98 inside the span of FE 8–11. They mix the classes SS
    and AS, which a homogeneous orthotropic plate keeps apart.
  - Records 7 and 8 share FE 13 (SA) and FE 14 (AA) at 0.79 / 0.18 and 0.17 / 0.81.
  - In both cases the parity about one centre line is broken. The thickness models bring record 7 to 0.96 (§24.4).
    That remains a separate hypothesis, and this task makes no combined model.

### 25.8 What the result means, and its limitations

**Established by this task (verified computation):**

1. The hypothesis in the form of §22.8 survives its three prospective falsification criteria.
2. One bending stiffness ratio D11 / D22 = 56 / 41 = 1.366 in the existing shell model gives the experimental class
   sequence and the 11 class frequencies within 4.4 %.
3. With it, the first-ranked FE mode of every record is the mode of its class order, and eight of the 11 shapes
   agree at 0.81–0.99 with the corrected positions.
4. The reduced basis of §22.8 predicts a solve at this step to 0.05 % in frequency and 0.0004 in research MAC.

**Not established, and remaining limitations:**

- **Not a material property.** A frequency gives a bending stiffness per direction, D = E h³ / 12 (1 − ν12 ν21), not
  E (§20.3). "E2 = 41 000 MPa" is a way of writing the ratio in a homogeneous shell of 0.875 mm.
  `NOT_A_MATERIAL_PROPERTY`; D-077 stands and no value is released.
- **The cause is not identified.** A laminate with equal in-plane moduli can have different bending stiffnesses in
  two directions through its stacking sequence. The layup is not recorded (§15). Initial curvature and the
  suspension are not excluded. The frequencies do not separate these.
- **The value was not fitted, but it was taken from four of the 11 records** (2, 3, 7 and 9). For those the test of
  the ratio is weak by construction; the seven others are the test. The common level rests on the archived
  E1 = 56 000 MPa.
- **One model, one value.** No neighbouring ratio was solved, so nothing is known from a solve about how sharply the
  criteria select 1.366. The archived E2 −5 % and −10 % models show the same direction of change (§24.7).
- **Three shapes are not described:** records 3, 4 and 7. (**§26:** the combined model describes record 7; records 3
  and 4 stay.) The model keeps the parity classes apart and these records
  mix them.
- **A residual of 3 % between the orders remains** (§25.5), and the margin of criterion 2 is 0.62 % at record 2.
- **Session 261016** gives another order-1 ratio (0.811 against 0.860, §22.7). The ratio is not shown to be a
  constant of the specimen.
- **The mapping.** The class sequence and the frequencies (criteria 1–3) do not depend on the point positions. Every
  MAC does: the positions are instrument-derived for 261016 and used for 261027 on the owner's statement; placement
  D is a convention. `PHYSICAL_REGISTRATION_NOT_VERIFIED`, D-044 and SPEC §5.2 (no traceable material axes) stand.
- **The direction.** "E2 is the lower one" is "the bending stiffness for curvature along FE Y is the lower one"
  under placement D (`CONVENTION_ONLY`, §22.2). It is not tied to a physical axis of the plate.
- **The experiment.** One force reference, no repeat of the setup and no uncertainty of the poles (§22.9). FE 18 has
  no record (§25.5).
- **Unmodelled:** suspension, force sensor, interior thickness (§20.4).
- **Not done:** a second solve or a retry, any other parameter change, a combined thickness and stiffness model, LM,
  Auto-ID, enabling E1 ≠ E2 in the identification pipeline, a registration.

**Verdict.** The directional stiffness hypothesis passed the one test that was written for it before the solve. It
is the only model examined so far that reproduces the class sequence and all 11 frequencies. It remains a
description of this plate in one setup by one number of a homogeneous shell: **not a confirmed cause, not a material
value, and not a basis for a parameter release.**

### 25.9 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `2d521588…` and a clean tracked tree before the edit |
| Input hashes | 58 inputs equal their recorded hashes (baseline package, test INP, protocol, extractor, the results and arrays of §22 and §24, the 30 solve and extraction files); all unchanged in size, mtime and SHA-256 after the run |
| Single-parameter change | §25.1: one line, one constant, equal byte length |
| Solver completion | §25.2 |
| Extraction integrity | §25.2 |
| Branch tracking | §25.4 |
| Prospective criteria | 1 PASS, 2 PASS, 3 PASS (§25.3–§25.5) |
| Protocol | the expectation used here equals the one stored in `protocol.json` before the solve |
| MAC reproduction | with the same code path the baseline and the expectation reproduce the stored matrices of §24 (difference 0.0) |
| Reproducibility | two complete analysis runs give byte-identical `results.json` (`f047f833…`) and `arrays.npz` (`8be92ee0…`) |
| Tests | `research/m11_r65`: 29 OK. `tests.test_plate_study`: 30 OK. `tests.test_psv_video_registration`: 22 OK. `tests.test_physical_registration`: 24 OK. `tests.test_plate_registration_readiness`: 18 OK. `tests.test_plate_rc1_owner_clarification`: 12 OK. `tests.test_plate_physical_review`: 36 OK. Run one at a time |

Changed in the repository: this report only.

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_DIRECTIONAL_FE_TEST_01` (outside git): `prepare.py`,
`protocol.json`, `solve\` (INP, `.dat`, `.odb`, `.sta`, `.msg`, logs), `scripts\extract_odb.py`, `logs\`,
`extraction\` (manifest, geometry, 20 modes), `identity.json`, `run_test.py`, `results.json`, `arrays.npz`,
`report.py`, `fig_frequency_error_class_order.png`, `fig_mac_matrix_solved.png`, `fig_shapes_exp_vs_fe.png`.

## 26. PLATE-0875-COMBINED-MODEL-01 — thickness gradient and directional stiffness together (2026-11-26)

`RESEARCH_ONLY`, `PHYSICAL_REGISTRATION_NOT_VERIFIED`, `NOT_A_MATERIAL_PROPERTY`, `MODEL_FORM_HYPOTHESIS`. One
combined model is compared with the three existing states. It is a hypothesis about the form of the model, not an
identification: no parameter was fitted or adjusted, no LM or Auto-ID was run, no value is released, no pairing
status and no `FrozenRegistration` were produced. M8 GATE NOT_MET, D-077 `NO_GLOBAL_PARAMETER_VALUE` and production
Auto-ID BLOCKED are unchanged. No program code, test, registration, gate or tool was changed.

**Abaqus use (owner authorisation: one solve and one corresponding extraction).**

| Action | Count | Detail |
|---|---|---|
| Abaqus solves | **1** | `CFRP_S4R_WEDGE_E2_41000_FreeFree`, Abaqus/Standard 2024, cpus = 1, interactive; 2026-11-26 16:11:56, 12.5 s, exit 0; no retry |
| ODB extractions | **1** | pinned extractor `039aa067…`, modes 1–20; 16:12:08, 5.3 s, exit 0; the ODB is unchanged by it; no retry |

**Short answer.** The combination improves the shapes and costs a little in frequency. It explains record 7, it does
not explain records 3 and 4, and one record leaves the ± 5 % level.

| Question of the task | Result |
|---|---|
| EXP 7 | **improved and described:** 0.79 → **0.98** |
| EXP 3 | not improved: 0.68 → 0.72 (rise 0.03, below the declared 0.05) |
| EXP 4 | not improved: 0.56 → 0.58 |
| All class frequency errors within ± 5 % | **no:** record 2 at −5.26 % (−4.38 % in §25); the ten others within, largest −4.80 % (record 3) |
| Deterioration of the eight well-matched records | none: largest fall 0.008 |
| Additive effects | no: the gain of record 8 (0.81 → 0.96) appears only in the combination |

- **Shapes.** Mean first-ranked research MAC 0.75 (baseline), 0.80 (thickness only), 0.88 (directional only),
  **0.92** (combined). Nine records are at 0.95–0.99 in the combined model; records 3 and 4 remain the only ones
  below 0.80.
- **Frequencies.** Mean absolute error 2.3 % → 2.7 %, largest 4.4 % → 5.3 %. The frequency agreement of §25 is
  therefore **not kept in full**. Most of the loss is a common shift of about −0.6 %: the wedge has a mean thickness
  of 0.870 mm against 0.875 mm.
- **The expectation written before the solve was right,** including the failure at record 2: frequencies to 0.09 %,
  research MAC to 0.002.
- **Assessment.** The combined model is the best description of the shapes examined so far, and it answers the
  question about record 7. It is not a better description of the frequencies, and it leaves records 3 and 4
  unexplained.

### 26.1 The model and its exact differences

| Item | Value |
|---|---|
| Source | the archived wedge INP of §18, `CFRP_S4R_WEDGE_FreeFree.inp`, SHA-256 `dcb639f1…`, read only |
| Combined input | `CFRP_S4R_WEDGE_E2_41000_FreeFree.inp`, SHA-256 `819de855…`, written before the solve; 30 466 lines, as the source |
| Difference 1, thickness | the 10 201 archived nodal values reassigned by the reflection X → 301 − X: 10 100 lines differ, the 101 lines of the centre column do not. The set of values is the archived one (a permutation; difference to the reflected archived field 0.0) |
| Difference 2, elastic | line 30441: `56000.,56000., 8500., …` → `56000.,41000., 8500., …`. The elastic lines equal those of the §25 input |
| Nothing else | every other line is identical to the archived wedge INP: same keywords, density, section, step, 20 requested modes, output, no boundary keyword |
| Against the baseline | `*Nodal Thickness` and the `nodal thickness` option of the shell section; E2; the header lines |
| Constants | E1 = 56 000, **E2 = 41 000**, G12 = 5 000 MPa; E3, ν12, ν13, ν23, G13, G23 as in the baseline |

**Thickness orientation.**

| Check | Result |
|---|---|
| Field | linear in X, 0.81 mm at X = 0 to 0.93 mm at X = 301 (deviation from the line 6·10⁻⁹ mm); no Y dependence (0.0) |
| Edges | mean 0.812 mm for X < 10 and 0.928 mm for X > 291; the measured edge means are 0.816 mm (edge 2, at X = 0 under D) and 0.926 mm (edge 4, at X = 301) |
| Source of the orientation | the edge readings under placement D (§18.2, §19.1). No MAC and no frequency entered it |
| Relation to §18 | the archived solve has its thick side at X = 0; §18 reflected its results. Here the reflected field is in the input itself, so the solved fields are used as extracted |
| No new distribution | the values are those of the archived analytical field; nothing was added or re-estimated |

**Integrated mass.**

| Quantity | Value |
|---|---|
| `.dat` of the combined model | 117.684 g |
| Integrated from the INP (ρ × area × mean nodal thickness per element) | 117.684 g |
| Archived wedge `.dat` | 117.684 g (equal) |
| Baseline `.dat` | 118.361 g (combined −0.57 %) |
| Recorded specimen mass | 118.37 g (combined −0.58 %) |
| Centre of mass | (153.96, 150.00, 0) mm; the archived wedge has 147.04: the reflection, as intended |
| Density | 1.498·10⁻⁹ t / mm³, unchanged. **No density correction was made** |

### 26.2 Declared before the solve

`protocol.json` (`b24e74b3…`) and `expectation.json` (`7b626e56…`) were written before the solve and are verified at
every analysis run.

**Correspondence of records and FE modes.** Record k against FE mode 6 + k in ascending frequency, the order
established in §25, cross-checked by FE-to-FE tracking against the directional-only model. No EXP MAC enters it. For
the two archived states the class-order modes of §22.6 are used, as in §24.

**Criteria.**

| | Criterion |
|---|---|
| A | Records 3, 4, 7: first-ranked research MAC in the combined model minus the directional-only one. `IMPROVED` at a rise of 0.05 or more; `DESCRIBED` at 0.80 or more |
| B | All 11 records within ± 5 % of FE mode 6 + k (the existing descriptive level; not a gate) |
| C | Records at 0.80 or above in the directional-only model (1, 2, 5, 6, 8, 9, 10, 11): `DETERIORATED` at a fall of more than 0.05 or below 0.80. Every frequency error that grows by more than 0.5 points is listed |
| D | Interaction: combined − baseline against (thickness only − baseline) + (directional only − baseline), for the frequency and the research MAC of the corresponding mode. `NON-ADDITIVE` above 0.5 points or 0.05. Additivity is assumed nowhere |
| Overall | "improves the model" if A is `IMPROVED` for at least one of records 3, 4, 7 and C shows no deterioration; "keeps the frequency agreement of §25" only if B holds. Reported separately |

**Expected effects** (reduced basis with the thickness field: 14 singular vectors of the 39 shapes FE 7–19 of the
three existing states; largest raw error on those three states 0.23 %; an expectation, itself tested by the solve):

- record 7 rises from 0.79 to about 0.98; record 8 from 0.81 to about 0.96;
- records 3 and 4 change by less than 0.05 (0.72 and 0.58);
- no deterioration of the eight well-matched records;
- most frequencies fall by 0.3–0.9 %, FE 13 by about 2 %;
- **criterion B is expected to fail at record 2** (about −5.3 %), with record 3 near the limit (−4.8 %);
- FE 13 and 14 are expected to interact with the wedge.

**The expectation against the solve.**

| Quantity | Result |
|---|---|
| Frequencies FE 7–18 | largest difference 0.093 % |
| Shapes FE 7–18 | MAC of expected and solved shape at least 0.9986 |
| Research MAC, 11 × 12 | largest difference of an element 0.002; the same first-ranked modes |

### 26.3 Solver completion and extraction integrity

| Check | Result |
|---|---|
| Solve | "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in `.sta`; `JOB … COMPLETED` in the console log; exit 0 |
| Messages | 0 errors and 0 warnings in `.dat`; `.msg`: 0 warning messages, 0 error messages |
| Rigid modes | modes 1–6 below 0.01 Hz; no non-positive eigenvalue among modes 7–20 |
| Extraction | exit 0; 22 files; 20 "Extracted mode" lines; 10 201 nodes |
| ODB | SHA-256 `fefb87e5…` before and after the extraction |
| Frequencies | manifest = `.dat` for modes 7–20 (relative difference 0.0) |
| Geometry | node labels, coordinates and connectivity equal the baseline package; INP nodes reproduce the extracted geometry to 1.5·10⁻⁵ mm |
| Field | in-plane displacement / U3 at most 1.3·10⁻¹¹ |

The 36 files of the solve, the extraction, the protocol and the expectation were hashed once after the extraction
(`identity.json`).

### 26.4 The four states

| State | Model | Source |
|---|---|---|
| Baseline | uniform 0.875 mm, E1 = E2 = 56 000 MPa | archived (§17) |
| Thickness only | wedge 0.81 → 0.93 mm, E1 = E2 = 56 000 MPa | archived solve of §18, results reflected in X |
| Directional only | uniform 0.875 mm, E2 = 41 000 MPa | §25 |
| Combined | wedge 0.81 → 0.93 mm, E2 = 41 000 MPa | this solve |

**Frequencies, Hz.**

| FE mode | Baseline | Thickness only | Directional only | Combined |
|---|---|---|---|---|
| 7 | 19.07 | 19.00 | 19.02 | 18.94 |
| 8 | 59.87 | 59.39 | 52.23 | 51.74 |
| 9 | 62.01 | 61.44 | 60.81 | 60.45 |
| 10 | 71.85 | 71.43 | 64.82 | 64.64 |
| 11 | 72.19 | 72.10 | 71.71 | 71.29 |
| 12 | 116.58 | 115.93 | 111.79 | 111.15 |
| 13 | 167.49 | 164.12 | 144.26 | 141.13 |
| 14 | 168.61 | 166.42 | 154.71 | 155.63 |
| 15 | 174.80 | 174.80 | 167.45 | 166.38 |
| 16 | 179.90 | 180.49 | 176.83 | 175.70 |
| 17 | 213.20 | 211.86 | 194.82 | 193.91 |
| 18 | 213.95 | 213.10 | 210.07 | 208.74 |
| 19 | 295.78 | 294.06 | 281.38 | 273.55 |
| 20 | 327.90 | 318.18 | 282.86 | 279.70 |

The mode numbers are positions in ascending frequency within each state. They are not branches: §26.6.

**Four-model comparison** (corrected positions of §24; all 11 records kept):

| Quantity | Baseline | Thickness only | Directional only | Combined |
|---|---|---|---|---|
| Mean first-ranked research MAC | 0.746 | 0.802 | 0.878 | **0.917** |
| Records at 0.80 or above | 5 | 6 | 8 | **9** |
| Records at 0.50 or above | 9 | 10 | 11 | 11 |
| Records below 0.80 | 2, 3, 4, 7, 8, 10 | 2, 3, 4, 8, 10 | 3, 4, 7 | **3, 4** |
| First-ranked mode = corresponding mode | 7 of 11 | 9 of 11 | 11 of 11 | 11 of 11 |
| Mean absolute frequency error, corresponding modes | 6.22 % | 5.92 % | **2.29 %** | 2.73 % |
| Largest absolute frequency error | 15.54 % | 12.46 % | **4.38 %** | 5.26 % |
| Signed mean frequency error | +5.01 % | +4.35 % | −1.61 % | −2.20 % |
| Records outside ± 5 % | 2, 4, 7, 8, 11 | 2, 4, 7, 8, 11 | **none** | 2 |
| Smallest share of a record in the span of the 14 shapes | 0.96 | 0.96 | 0.96 | 0.96 |

### 26.5 All 11 records

**First-ranked research MAC** (FE mode in brackets; range over the 59 declared scenarios for the combined model):

| EXP | Hz | Baseline | Thickness only | Directional only | **Combined** | Range, combined | Combined − directional only |
|---|---|---|---|---|---|---|---|
| 1 | 18.63 | 0.97 (7) | 0.97 (7) | 0.97 (7) | **0.97** (7) | 0.96–0.97 | +0.00 |
| 2 | 54.62 | 0.52 (9) | 0.54 (8) | 0.97 (8) | **0.99** (8) | 0.98–0.99 | +0.02 |
| **3** | 63.50 | 0.45 (8) | 0.39 (9) | 0.68 (9) | 0.72 (9) | 0.71–0.72 | +0.03 |
| **4** | 66.85 | 0.56 (11) | 0.57 (11) | 0.56 (10) | 0.58 (10) | 0.57–0.59 | +0.02 |
| 5 | 74.21 | 0.99 (10) | 0.99 (10) | 0.99 (11) | **0.99** (11) | 0.97–0.99 | +0.00 |
| 6 | 112.27 | 0.99 (12) | 0.98 (12) | 0.99 (12) | **0.98** (12) | 0.96–0.99 | −0.01 |
| **7** | 145.94 | 0.79 (14) | 0.96 (13) | 0.79 (13) | **0.98** (13) | 0.95–0.98 | **+0.19** |
| 8 | 157.85 | 0.43 (16) | 0.74 (16) | 0.81 (14) | **0.96** (14) | 0.93–0.97 | **+0.16** |
| 9 | 169.18 | 0.98 (13) | 0.98 (14) | 0.98 (15) | **0.98** (15) | 0.96–0.98 | +0.00 |
| 10 | 180.14 | 0.57 (15) | 0.75 (15) | 0.97 (16) | **0.97** (16) | 0.95–0.98 | +0.00 |
| 11 | 191.60 | 0.96 (18) | 0.94 (18) | 0.96 (17) | **0.95** (17) | 0.91–0.96 | −0.01 |

In all 59 scenarios the first-ranked mode of every record is unchanged, in each of the four states.

**Frequency error of the corresponding mode** (signed, FE mode in brackets):

| EXP | Hz | Baseline | Thickness only | Directional only | **Combined** | Growth of the absolute error, combined against directional only |
|---|---|---|---|---|---|---|
| 1 | 18.63 | +2.37 % (7) | +1.97 % (7) | +2.08 % (7) | +1.68 % (7) | −0.40 |
| 2 | 54.62 | +9.62 % (8) | +8.73 % (8) | −4.38 % (8) | **−5.26 %** (8) | **+0.89** |
| 3 | 63.50 | −2.34 % (9) | −3.24 % (9) | −4.23 % (9) | −4.80 % (9) | +0.57 |
| 4 | 66.85 | +7.99 % (11) | +7.86 % (11) | −3.04 % (10) | −3.30 % (10) | +0.27 |
| 5 | 74.21 | −3.19 % (10) | −3.75 % (10) | −3.37 % (11) | −3.94 % (11) | +0.57 |
| 6 | 112.27 | +3.84 % (12) | +3.26 % (12) | −0.42 % (12) | −0.99 % (12) | +0.57 |
| 7 | 145.94 | +15.54 % (14) | +12.46 % (13) | −1.15 % (13) | −3.29 % (13) | **+2.14** |
| 8 | 157.85 | +10.74 % (15) | +10.74 % (15) | −1.99 % (14) | −1.41 % (14) | −0.58 |
| 9 | 169.18 | −1.00 % (13) | −1.63 % (14) | −1.03 % (15) | −1.66 % (15) | +0.63 |
| 10 | 180.14 | −0.13 % (16) | +0.20 % (16) | −1.84 % (16) | −2.46 % (16) | +0.63 |
| 11 | 191.60 | +11.66 % (18) | +11.22 % (18) | +1.68 % (17) | +1.20 % (17) | −0.47 |

**Full research MAC matrix, combined model** (bold: first-ranked):

| EXP | FE 7 | FE 8 | FE 9 | FE 10 | FE 11 | FE 12 | FE 13 | FE 14 | FE 15 | FE 16 | FE 17 | FE 18 | FE 19 | FE 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **0.97** | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | 0.00 | **0.99** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 3 | 0.00 | 0.00 | **0.72** | 0.24 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 4 | 0.00 | 0.02 | 0.38 | **0.58** | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 5 | 0.01 | 0.00 | 0.00 | 0.00 | **0.99** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 | 0.00 | 0.01 | 0.00 | 0.01 | 0.00 | **0.98** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 7 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.98** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 8 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.96** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 9 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.98** | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 |
| 10 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.97** | 0.01 | 0.00 | 0.00 | 0.00 |
| 11 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 | 0.01 | **0.95** | 0.01 | 0.00 | 0.01 |

The matrices of the three other states are those of §24.4 (baseline, thickness only) and §25.6 (directional only);
they are reproduced here with difference 0.0 and shown together in `fig_mac_four_states.png`.

### 26.6 Branches and subspaces

FE-to-FE real MAC of U3 on all 10 201 nodes, assignment as in §20; tracked at 0.90 or more. A lost branch is
reported as lost and is not replaced by another mode.

**Combined against directional only** (the reference of the correspondence):

| Directional only | Hz | Combined | Hz | MAC | Status | Second combined mode | Frequency change | Parity share, combined |
|---|---|---|---|---|---|---|---|---|
| 7 | 19.02 | 7 | 18.94 | 1.00 | tracked | — | −0.39 % | AA 1.00 |
| 8 | 52.23 | 8 | 51.74 | 0.98 | tracked | FE 10: 0.01 | −0.93 % | SS 0.98 |
| 9 | 60.81 | 9 | 60.45 | 1.00 | tracked | — | −0.60 % | SS 1.00 |
| 10 | 64.82 | 10 | 64.64 | 0.99 | tracked | FE 8: 0.02 | −0.28 % | AS 0.99 |
| 11 | 71.71 | 11 | 71.29 | 1.00 | tracked | — | −0.59 % | SA 1.00 |
| 12 | 111.79 | 12 | 111.15 | 1.00 | tracked | — | −0.57 % | SS 1.00 |
| 13 | 144.26 | 13 | 141.13 | **0.83** | **lost** | FE 14: 0.14 | (−2.17 %) | SA 0.83 |
| 14 | 154.71 | 14 | 155.63 | **0.84** | **lost** | FE 13: 0.17 | (+0.59 %) | AA 0.84 |
| 15 | 167.45 | 15 | 166.38 | 1.00 | tracked | — | −0.64 % | AS 1.00 |
| 16 | 176.83 | 16 | 175.70 | 1.00 | tracked | — | −0.64 % | AA 1.00 |
| 17 | 194.82 | 17 | 193.91 | 0.98 | tracked | — | −0.47 % | SA 0.98 |
| 18 | 210.07 | 18 | 208.74 | 1.00 | tracked | — | −0.63 % | AS 1.00 |
| 19 | 281.38 | 20 | 279.70 | 0.99 | tracked | — | −0.60 % | AA 0.99 |
| 20 | 282.86 | 19 | 273.55 | 0.65 | lost | — | (−3.29 %) | SS 0.66 |

- **11 of 14 tracked.** Nine of the 11 modes that correspond to records are tracked to the same position, so the
  correspondence "record k, FE 6 + k" is confirmed by tracking for records 1–6 and 9–11.
- **Lost: FE 13 and FE 14, the modes of records 7 and 8.** The wedge mixes the Y2 mode (SA) with the neighbouring
  AA mode: each combined mode carries 0.83–0.84 of its directional-only counterpart and 0.14–0.17 of the other.
  Their two-mode subspace is kept only approximately (largest principal angle 7.7°). **For records 7 and 8 the
  correspondence is therefore not confirmed by tracking;** it rests on the frequency position and on the dominant
  parity class (SA 0.83, AA 0.84). The frequency changes in brackets are not branch quantities.
- **This loss is the mechanism of the improvement.** The mixing that breaks the two branches is what the shapes of
  records 7 and 8 contain (§25.7: record 7 with FE 13 / 14 at 0.79 / 0.18, record 8 at 0.17 / 0.81).
- **FE 19 and 20 exchange** (the combined FE 19 is the directional-only FE 20, MAC 0.65, lost). Both are above the
  records.

**Combined against the two other states.**

| Reference | Tracked | Lost | Order exchanges among the tracked |
|---|---|---|---|
| Baseline | 8 of 14 | 8, 9, 14, 15, 16, 20 | 10 ↔ 11, 13 → 15, 17 ↔ 18, 19 → 20 |
| Thickness only | 10 of 14 | 8, 9, 15, 16 | 10 ↔ 11, 14 → 15, 17 ↔ 18, 19 ↔ 20 |

- Against the baseline the lost branches are those of §25.4 (8, 9, 15, 16, 20) and, in addition, 14 (MAC 0.83).
- Against the thickness-only state the pairs 8 / 9 and 15 / 16 are redistributed (MAC 0.58 / 0.42 and 0.75 / 0.24),
  and the wedge mode of record 7 (thickness-only FE 13) is kept at 0.985.

**Subspaces** (largest principal angle between the spans of the modes with the same position numbers):

| Group | Against directional only | Against thickness only | Against baseline |
|---|---|---|---|
| FE 8–9 | 8.8° | 2.9° | 8.8° |
| FE 8–11 | 2.9° | 0.6° | 2.9° |
| FE 13–16 | 7.7° | 2.1° | 7.8° |
| FE 7–18 | 4.7° | 1.0° | 4.8° |

- The spans of the combined model are close to those of the thickness-only model and further from the two uniform
  models. The wedge sets the subspace; the stiffness ratio decides how the modes are combined inside it.
- The share of each record in the groups FE 8–11 and FE 13–16 is the same in all four states (records 2–5:
  0.96–0.99; records 7–10: 0.96–0.99).

### 26.7 Records 3, 4 and 7, and the interaction of the two effects

**Record 7: explained by the combination.** 0.79 in both uniform models, 0.96 with the wedge alone, **0.98**
combined (0.95–0.98 over the scenarios). The wedge alone gives the shape but leaves the frequency 12.5 % too high;
the combination gives the shape at −3.3 %. Its mode is the Y2 mode mixed with the neighbouring AA mode.

**Records 3 and 4: not explained.**

| EXP | MAC with FE 9 (SS, X1) | MAC with FE 10 (AS) | Share in the span of FE 8–11 |
|---|---|---|---|
| 3, directional only | 0.68 | 0.26 | 0.96 |
| 3, combined | 0.72 | 0.24 | 0.96 |
| 4, directional only | 0.41 | 0.56 | 0.98 |
| 4, combined | 0.38 | 0.58 | 0.98 |

- Both records remain mixtures of the two modes. The changes (+0.03 and +0.02) are below the declared 0.05. They
  are of the size of the scenario range or a little above it (0.01 wide for both records) and point to a small improvement.
- **The wedge breaks the right symmetry, but far too weakly here.** A thickness gradient along X mixes classes that
  differ in the first parity letter. That is the difference between SS and AS (records 3 / 4) as well as between SA
  and AA (records 7 / 8). In the combined model FE 13 and 14 are mixed (parity share 0.83–0.84), while FE 9 and 10
  stay almost pure (1.00 and 0.99). The records would need a mixing of 0.24–0.41.
- So a linear thickness gradient of this size is not the cause of the mixing of records 3 and 4. What is: not
  known. Both lie 0.96–0.98 inside the span of four FE shapes, so it is a matter of how the model combines them.

**Interaction** (criterion D; the two effects are not assumed to add):

| EXP | Frequency change against the baseline: thickness only / directional only / sum / **combined** | Non-additivity | MAC of the corresponding mode: baseline / thickness only / directional only / additive / **combined** | Non-additivity |
|---|---|---|---|---|
| 1 | −0.39 / −0.28 / −0.68 / **−0.68 %** | 0.00 | 0.97 / 0.97 / 0.97 / 0.97 / **0.97** | 0.00 |
| 2 | −0.81 / −12.77 / −13.58 / **−13.58 %** | 0.00 | 0.45 / 0.54 / 0.97 / 1.06 / **0.99** | **−0.07** |
| 3 | −0.92 / −1.93 / −2.85 / **−2.52 %** | +0.34 | 0.25 / 0.39 / 0.68 / 0.83 / **0.72** | **−0.11** |
| 4 | −0.12 / −10.21 / −10.34 / **−10.46 %** | −0.12 | 0.56 / 0.57 / 0.56 / 0.57 / **0.58** | +0.01 |
| 5 | −0.59 / −0.19 / −0.78 / **−0.78 %** | 0.00 | 0.99 / 0.99 / 0.99 / 0.99 / **0.99** | 0.00 |
| 6 | −0.56 / −4.11 / −4.67 / **−4.66 %** | +0.01 | 0.99 / 0.98 / 0.99 / 0.98 / **0.98** | 0.00 |
| 7 | −2.66 / −14.44 / −17.10 / **−16.30 %** | **+0.81** | 0.79 / 0.96 / 0.79 / 0.96 / **0.98** | +0.02 |
| 8 | 0.00 / −11.49 / −11.49 / **−10.97 %** | **+0.53** | 0.37 / 0.21 / 0.81 / 0.64 / **0.96** | **+0.32** |
| 9 | −0.64 / −0.02 / −0.66 / **−0.66 %** | 0.00 | 0.98 / 0.98 / 0.98 / 0.98 / **0.98** | 0.00 |
| 10 | +0.33 / −1.71 / −1.38 / **−2.33 %** | **−0.96** | 0.41 / 0.22 / 0.97 / 0.78 / **0.97** | **+0.19** |
| 11 | −0.40 / −8.94 / −9.34 / **−9.37 %** | −0.03 | 0.96 / 0.94 / 0.96 / 0.95 / **0.95** | +0.01 |

- **Additive where the modes are isolated:** records 1, 5, 6, 9, 11 and the frequencies of records 2 and 4.
- **Non-additive in the group FE 13–16:** records 7, 8 and 10 in frequency (+0.8, +0.5, −1.0 points), records 8
  and 10 in MAC (+0.32, +0.19).
- **Record 8 is the clearest interaction.** The wedge alone lowers the MAC of its corresponding mode (0.37 → 0.21),
  the stiffness ratio alone raises it to 0.81, and the two together give 0.96. Neither effect alone and no sum of
  them gives that value: the stiffness ratio first separates the pair FE 15 / 16, and only then can the wedge mix
  the lower AA mode with Y2 in the way the record shows.
- **Records 2 and 3 fall short of the additive value** (−0.07, −0.11): both effects act on the same pair FE 8 / 9
  and saturate (record 2 reaches 0.99).
- The correspondence of the two archived states is the class order of §22.6; with the first-ranked modes instead,
  the same records stand out (non-additivity −0.15 for record 8, −0.18 for record 10, +0.09 for record 3). The
  sign depends on that choice; the absence of additivity does not.

### 26.8 Assessment, and limitations

**Verdict by the criteria declared before the solve.**

| Criterion | Verdict |
|---|---|
| A, record 3 | not improved (+0.03), not described (0.72) |
| A, record 4 | not improved (+0.02), not described (0.58) |
| A, record 7 | **IMPROVED (+0.19) and DESCRIBED (0.98)** |
| B, all class frequencies within ± 5 % | **FAIL:** record 2 at −5.26 % |
| C, no deterioration of the well-matched records | **no deterioration** (largest fall 0.008); frequency error grown by more than 0.5 points for records 2, 3, 5, 6, 7, 9, 10 |
| D, interaction | non-additive: frequency of records 7, 8, 10; MAC of records 2, 3, 8, 10 |
| Overall | improves the model in shape (record 7; C holds); **does not keep the frequency agreement of §25 in full** |

**What the result supports.**

1. A stiffness ratio and a thickness gradient along X act together on the group FE 13–16, and only together do they
   give the shapes of records 7 and 8 (0.98 and 0.96). The suggestion of §22.7 and §24.7, that both may be present,
   is supported for these records.
2. The eight records that the directional-only model described are not harmed.
3. The reduced basis with the thickness field predicted this solve to 0.09 % and 0.002.

**What it does not support, and what limits it.**

- **Records 3 and 4 are not explained** by this combination. This is the main open shape discrepancy.
- **The frequency agreement is slightly worse.** Ten of the 11 absolute errors change by less than 1 point, record 7
  by 2.1 points (−1.2 % → −3.3 %), and record 2 crosses the ± 5 % level by 0.26 points. ± 5 % is a descriptive
  level, not a gate.
- **Most of the frequency loss is the common level, which neither hypothesis addresses.** The wedge has a mean
  thickness of 0.870 mm against 0.875 mm, which lowers a bending frequency by about 0.57 %; nine of the 11
  corresponding modes fall by 0.3–0.9 %. The common level rests on the archived E1 = 56 000 MPa and on the mean
  thickness. Neither was adjusted, and no adjustment is proposed here.
- **The mass is 0.58 % below the record** (117.68 g against 118.37 g). No density correction was made, as instructed.
- **Not a material property and not an identified thickness.** E2 = 41 000 MPa writes a bending stiffness ratio in a
  homogeneous shell (§25.8). The wedge is the archived linear field between two edge means; the interior thickness
  is not measured (§13, §19). `NOT_A_MATERIAL_PROPERTY`; D-077 stands; no value is released.
- **Stiffness and thickness are not separable by frequencies.** A frequency gives D = E h³ / 12 (1 − ν12 ν21) per
  direction and place. A gradient of the modulus along X would act like the thickness gradient. The shapes of
  records 7 and 8 show a break of the symmetry about the X centre line of this size; they do not show that its
  cause is thickness.
- **One model.** Neither the gradient nor the ratio was varied, so nothing is known from a solve about how sharply
  the records select them. The field of the 20 readings (§19) was not combined, as instructed.
- **Records 7 and 8: correspondence by position, not by a tracked branch** (§26.6).
- **The direction of the wedge** follows the edge readings under placement D, which is a convention
  (`CONVENTION_ONLY`). §18 found record 7 at 0.45 with the opposite orientation (old positions; a superseded value). That comparison
  used MAC and was not used to choose the orientation here.
- **The mapping.** Frequencies and FE-to-FE tracking do not depend on the point positions; every research MAC does.
  The positions are instrument-derived for 261016 and used for 261027 on the owner's statement.
  `PHYSICAL_REGISTRATION_NOT_VERIFIED`, D-044 and SPEC §5.2 stand.
- **The experiment.** One force reference, no repeat of the setup, no uncertainty of the poles (§22.9). Session
  261016 gives another order-1 ratio (§22.7).
- **Unmodelled:** suspension, force sensor, layup, initial curvature.
- **Not done:** a second solve or a retry, any parameter adjustment, a new thickness distribution, a density
  correction, an orientation or geometry selection by MAC, LM, Auto-ID, a registration.

**Assessment.** The combined hypothesis improves the model where §25 left the shapes of the group FE 13–16
unexplained, and it shows that the two effects interact. It is **not an overall improvement on the criteria as
declared**: the frequencies are slightly worse, one record is outside ± 5 %, and records 3 and 4 are unchanged. It
remains a model-form hypothesis for one plate in one setup.

### 26.9 Verification and files

| Check | Result |
|---|---|
| Git | origin = HEAD = `0809f9c3…` and a clean tracked tree before the edit |
| Input hashes | 66 inputs equal their recorded hashes (baseline package, archived wedge INP, the §25 input, the results and arrays of §22, §24 and §25, the protocol, the 36 own files); all unchanged in size, mtime and SHA-256 after the run |
| Exact model differences | §26.1 |
| Thickness orientation | §26.1 |
| Integrated mass | §26.1 |
| Solver completion, extraction integrity | §26.3 |
| Branch and subspace tracking | §26.6 |
| Expectation and criteria fixed before the solve | §26.2; the protocol hash is checked at every run |
| MAC reproduction | the three existing states reproduce the stored matrices of §24 and §25 (difference 0.0) |
| Reproducibility | two complete analysis runs give byte-identical `results.json` (`d539459f…`) and `arrays.npz` (`aaf488ca…`) |
| Tests | `research/m11_r65`: 29 OK. `tests.test_plate_study`: 30 OK. `tests.test_psv_video_registration`: 22 OK. `tests.test_physical_registration`: 24 OK. `tests.test_plate_registration_readiness`: 18 OK. `tests.test_plate_rc1_owner_clarification`: 12 OK. `tests.test_plate_physical_review`: 36 OK. Run one at a time |

Changed in the repository: this report only.

`D:\git\abaqus-modal-comparator-work\research\PLATE_0875_COMBINED_MODEL_01` (outside git): `build_inp.py`,
`inp_record.json`, `expect.py`, `expectation.json`, `write_protocol.py`, `protocol.json`, `solve\` (INP, `.dat`,
`.odb`, `.sta`, `.msg`, logs), `scripts\extract_odb.py`, `logs\`, `extraction\`, `identity.json`, `run_combined.py`,
`results.json`, `arrays.npz`, `report.py`, `fig_four_models.png`, `fig_mac_four_states.png`,
`fig_shapes_exp_3_4_7_8.png`.

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, registrations, criteria, the 5 / 8 % limits, M8 / D-077, governed records and every
original file.
