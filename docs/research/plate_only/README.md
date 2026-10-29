# PLATE-ONLY-R1 — effective properties of one CFRP plate (research, non-normative)

**Status: REVIEW_READY (2026-10-30; F1 traceability and notation, see §11; PLATE-ONLY-R2 specimen identity, archived record, FE applicability and orientation, see §12; R2-F1 package identity, the two series and the thickness, see §13). Research only, non-normative.** This report changes no specification, decision,
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

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, registrations, criteria, the 5 / 8 % limits, M8 / D-077, governed records and every
original file.
