# M6 SP-11 experiment checklist (HUMAN, before M6-C)

**Purpose:** exactly what the HUMAN must obtain for the new SP-11 bare-plate experiment before
M6-C (real-data admission) can start. The checklist is governed by:
- D-049–D-056 and [M6_DECISION_RECORD.md](M6_DECISION_RECORD.md);
- SPEC §4.1, §6 S1, §7, §11, §15;
- D-019, D-026, D-027, D-030, D-031.

**Specimen (D-049):**

| Field | Value |
|---|---|
| Store folder | `SP-11` |
| Name | Old CFRP Twill Plate 350x350 |
| Nominal geometry | approximately 350 × 347 × 0.45 mm |
| Mass record | approximately 79.59 g |
| Family | old T300 twill |

**How to fill it in:**
- Nothing here is a value for identification until the HUMAN supplies it.
- Fields marked **HUMAN TO SUPPLY** are still missing.
- Nominal and earlier values are listed only so the specimen can be recognised. They are never
  substitutes for measurements.
- The **Software check** column names the M6-B refusal (`domain/stage_a_experiment.py`) that the
  item satisfies.

**Old recordings (260824, 260826 a, 260826 b_center):** reconnaissance only. They are not
identification input and not a setup repeat (D-049, D-053).

---

## A. Measurements before the test

| # | Item | Requirement | Value | Software check |
|---|---|---|---|---|
| A1 | Plate thickness | At least 9 measured points (SPEC §15). Each point is a value in mm. | HUMAN TO SUPPLY | `MISSING_THICKNESS`, `INSUFFICIENT_THICKNESS_POINTS` |
| A2 | Thickness positions | One position per point, for example x, y in mm from corner A. The distribution over the plate is the HUMAN's documented choice: SPEC fixes the count, not the pattern. | HUMAN TO SUPPLY | positions must be unique |
| A3 | Gauge | Gauge identity and resolution, if known. Its standard uncertainty only if it is known from a calibration or specification; otherwise write "not known". A resolution is never converted into an uncertainty, and nothing is invented (D-052). | HUMAN TO SUPPLY | gauge component used only if supplied |
| A4 | Mass | Plate mass in g with its uncertainty (balance identity and resolution). Earlier record: about 79.59 g, not a substitute. | HUMAN TO SUPPLY | `MISSING_SPECIMEN_MEASUREMENTS` |
| A5 | Plan dimensions | Length and width in mm with their uncertainty (passport `plan_mm`: `Lx`, `Ly`, `sd`). Earlier record: 350 × 347 mm, not a substitute. | HUMAN TO SUPPLY | `MISSING_SPECIMEN_MEASUREMENTS` |
| A6 | Identity keys | Distinct `design_id`, `physical_specimen_id` and `test_run_id` (SPEC §4.1). | HUMAN TO SUPPLY | passport validation (M2) |
| A7 | Family id | The passport `family_id` string for the old T300 twill family. | SUPERVISOR TO CONFIRM | passport validation (M2) |
| A8 | Corner A and photographs | Mark corner A. Photograph the plate, corner A, the X-axis direction and the grid (SPEC §15, §4.1). | HUMAN TO SUPPLY | passport `geometry_calibration` (M2) |

## B. Suspension and excitation

| # | Item | Requirement | Value | Software check |
|---|---|---|---|---|
| B1 | Suspension configuration | Soft suspension (SPEC §15): cord/spring type, attachment points on the plate, photograph. | HUMAN TO SUPPLY | — |
| B2 | Suspension threshold | `suspension_max_hz` with its documented physical source, for example the measured suspension (rigid-body) modes of this set-up. It is never guessed from elastic modal frequencies or FE results, and has no default (D-031). | HUMAN TO SUPPLY | `MISSING_SUSPENSION`; modes below it: `MODE_BELOW_SUSPENSION` |
| B3 | Excitation route | Either an attached shaker / force sensor (the attachment mass is then in the FE model, SPEC §15), or a route with no attached mass. A route without an attached mass (non-contact, or any other) needs an explicit SUPERVISOR approval reference **before** the test. | HUMAN TO SUPPLY | `MISSING_EXCITATION_EVIDENCE`, `NON_CONTACT_ROUTE_NOT_APPROVED` |
| B4 | Attachment mass | Contact route only: the measured mass of everything attached to the plate (force-sensor part, stinger tip, stud, adhesive), its source, and its location on the plate. This exact value must be the mass modelled in the Stage-A FE model. | HUMAN TO SUPPLY | `MISSING_ATTACHMENT_MASS`, `ATTACHMENT_MASS_NOT_MODELLED` |
| B5 | Excitation locations | At least 2 locations (SPEC §15), with positions relative to corner A. | HUMAN TO SUPPLY | `INSUFFICIENT_EXCITATION_LOCATIONS` |

## C. Modal acquisition

| # | Item | Requirement | Value | Software check |
|---|---|---|---|---|
| C1 | Frequency band | Must contain every mode intended as a fit or holdout row. SPEC fixes no band. For reference only, the old sessions used 0–250 Hz and 0–100 Hz; this is not a requirement. | HUMAN TO SUPPLY | M1 QC |
| C2 | Resolution | Δf ≤ 0.05 Hz for modes below 100 Hz, for example by zoom-FFT or more lines (SPEC §15). Record the actual Δf. The S1 unresolved-resonance flag (2ζf < 3Δf) applies to every mode. | HUMAN TO SUPPLY | M1 QC (S1) |
| C3 | Measurement grid | Grid identity (`grid_id`, point count). Start at corner A; X axis the same way on every specimen (SPEC §15). The repeat (E) uses the same grid. | HUMAN TO SUPPLY | passport `acquisition.grid` (M2) |
| C4 | Geometry / grid calibration | `geometry_calibration` in mode `corner_coordinates_mm` or `scan_to_panel_edges`, with the measured values and the scale reference (a real distance or reference length). Calibration uncertainty: `translation_mm`, `scale_rel`, `rotation_deg` (SPEC §4.1, §11, §15). | HUMAN TO SUPPLY | `MISSING_GEOMETRY_CALIBRATION` (FrozenRegistration) |
| C5 | Coherence | Coherence recorded with the FRFs. S1 flags coherence < 0.9 at resonance. | HUMAN TO SUPPLY | M1 QC (S1) |
| C6 | Acquisition provenance | Session id and date; instrument and software versions; `protocol_id`; source file names. SHA-256 values are computed at admission (M6-C). | HUMAN TO SUPPLY | passport `acquisition` (M2) |

## D. Modal processing

| # | Item | Requirement | Value | Software check |
|---|---|---|---|---|
| D1 | Fitting route | The accepted external PolyMAX route (Testlab; D-027). No internal FRF fitting (D-030), and no modes derived from the old coarse FRFs. | HUMAN TO SUPPLY | `FRF_ONLY_INPUT`, `NOT_CURVE_FITTED` |
| D2 | Dataset 55 | Export the curve-fitted modes with shapes as UNV dataset 55 (SPEC §15). | HUMAN TO SUPPLY | `NOT_CURVE_FITTED` |
| D3 | Frozen modal set | A documented, hashed selection (D-026): pinned source file, modal-set key, provenance, immutable. No live mode selection during identification. | HUMAN TO SUPPLY | `MISSING_FROZEN_MODAL_SET`, `MODAL_SET_MISMATCH` |
| D4 | QC / S1 admission | Done in software at M6-C (M1 policy and QC). The HUMAN supplies the items above. | — (M6-C) | M1 admission |

## E. Repeat (M6.2)

| # | Item | Requirement | Value | Software check |
|---|---|---|---|---|
| E1 | Genuine remount | Remove the plate, re-suspend it and reinstall the excitation (all three), on the same SP-11 plate (D-053). | HUMAN TO SUPPLY | M2 `classify_setup_repeat` |
| E2 | Same grid and protocol | Same `grid_id` and point count; same `protocol_id`. | HUMAN TO SUPPLY | M2 `classify_setup_repeat` |
| E3 | Remount link | A new `test_run_id`; the same `physical_specimen_id`; `remount_of` = the original `test_run_id`; `remount_kind`; `remount_evidence` (log or photograph). | HUMAN TO SUPPLY | M2 acquisition linkage |
| E4 | Repeat processing | The same D1–D3 route and a frozen modal set for the repeat run. | HUMAN TO SUPPLY | as D |
| E5 | Shared plate quantities | The thickness characterisation belongs to the plate. It is shared by both runs and is not setup scatter (D-053). A re-measurement, if made, is recorded as a separate thickness record. If the attachment changes, record its new mass (B4). | HUMAN TO SUPPLY | M6.2 comparison inputs |

---

## Still needed after the HUMAN data (software / FE, not HUMAN measurements)

- **M6-C:** SP-11 passport, admission of the frozen modal set, FrozenRegistration, M1 QC/S1, and
  the strict pairing at the Stage-A baseline.
- **Before any Stage-A matrix job:** a HUMAN Abaqus gate. It covers the SP-11 Stage-A model (mesh,
  modelled attachment mass, areal density from the measured mass, fixed transverse-shear
  stiffness), the four matrix jobs and the validation points.
- **Open SUPERVISOR items (M6_DECISION_RECORD §12):**
  - the affine-basis validation tolerance;
  - the real-run LM settings and parameter bounds;
  - propagation of the mass and plan-dimension uncertainties.
