# Reference requirements for a valid future SP-11 / bare-plate test

**Status (D-057, D-058; 2026-10-06):** this is a **reference record, not an active HUMAN to-do
list**.
- **Why:** a new SP-11 experiment is not physically available with the present setup.
- **M6.1 and M6.2:** `BLOCKED_ON_EXPERIMENT`.
- **What the document does:** it records what a valid bare-plate Stage-A test needs, and the
  current state of SP-11 against those needs.
- **What it does not do:** it does not ask the HUMAN to perform the unavailable experiment.

**Governance:** D-049 (identity), D-050–D-052, D-054–D-058, and
[M6_DECISION_RECORD.md](M6_DECISION_RECORD.md); SPEC §4.1, §6 S1, §7, §11, §15; D-019, D-024,
D-026, D-027, D-030, D-031.
**Fact source:** `D:\Snadwich` (inventory in
[SNADWICH_INVENTORY.md](SNADWICH_INVENTORY.md)).

## Current SP-11 state

### AVAILABLE_NOT_YET_GOVERNED (`D:\Snadwich\SP-11\spec.txt`; nominal, no uncertainty recorded)

| Item | Value |
|---|---|
| Identity | SP-11, "Old CFRP Twill Plate 350x350" (D-049) |
| Family | old T300 twill weave (0.45) |
| Nominal dimensions | 350 × 347 mm |
| Nominal thickness | 0.45 mm (a single value) |
| Mass | 79.59 g |
| Raw FRF sessions (reconnaissance / modal-preparation source data, D-024, D-057) | 260824: 121 points, 0–250 Hz, Δf 0.3125 Hz. 260826 a: 120 points, 0–100 Hz, Δf 0.25 Hz. 260826 b_center: 121 points, same grid as "a". All are dataset 58 (FRF, coherence, cross-spectrum), one force reference, Polytec PSV acquisition. |

### MISSING (not in any source)

- a ≥ 9-point thickness map;
- the mass uncertainty;
- the dimension uncertainty;
- the attachment mass of the contact (force-sensor) excitation;
- a suspension threshold (D-031);
- a fitted, frozen modal set (dataset 55; D-026);
- a documented valid repeat (`remount_of`; D-058);
- consistency between sessions (the three existing sessions are inconsistent; D-057);
- measured twill material constants (the spec table is blank);
- an SP-11 FE model.

### UNAVAILABLE_FOR_THIS_PROJECT

- a new SP-11 acquisition or re-test under the present physical setup (HUMAN constraint, D-057).

---

## Reference requirements (any future valid bare-plate test)

The **Software check** column names the M6-B refusal (`domain/stage_a_experiment.py`) that the
requirement corresponds to.

### A. Measurements before the test

| # | Requirement | Software check |
|---|---|---|
| A1 | At least 9 thickness points, each a value in mm (SPEC §15) | `MISSING_THICKNESS`, `INSUFFICIENT_THICKNESS_POINTS` |
| A2 | One recorded position per point. SPEC fixes the count, not the pattern. | unique positions |
| A3 | Gauge identity and resolution; a gauge uncertainty only if known, never invented (D-052) | separate gauge component |
| A4 | Mass with its uncertainty | `MISSING_SPECIMEN_MEASUREMENTS` |
| A5 | Length and width with their uncertainty (passport `plan_mm`) | `MISSING_SPECIMEN_MEASUREMENTS` |
| A6 | Distinct `design_id`, `physical_specimen_id` and `test_run_id` (SPEC §4.1) | passport (M2) |
| A7 | Passport `family_id` string for the family (SUPERVISOR) | passport (M2) |
| A8 | Corner A marked; photographs of the plate, orientation and grid (SPEC §15, §4.1) | `geometry_calibration` (M2) |

### B. Suspension and excitation

| # | Requirement | Software check |
|---|---|---|
| B1 | Soft suspension, documented (SPEC §15) | — |
| B2 | `suspension_max_hz` with its documented physical source; never guessed, no default (D-031) | `MISSING_SUSPENSION`, `MODE_BELOW_SUSPENSION` |
| B3 | Either an attached shaker / force sensor whose mass is in the FE model, or an approved route with no attached mass (SPEC §15) | `MISSING_EXCITATION_EVIDENCE`, `NON_CONTACT_ROUTE_NOT_APPROVED` |
| B4 | Contact route: measured attachment mass, its source and its location; the same value is modelled | `MISSING_ATTACHMENT_MASS`, `ATTACHMENT_MASS_NOT_MODELLED` |
| B5 | At least 2 excitation locations (SPEC §15) | `INSUFFICIENT_EXCITATION_LOCATIONS` |

### C. Modal acquisition

| # | Requirement | Software check |
|---|---|---|
| C1 | The band contains every fit and holdout mode | M1 QC |
| C2 | Resolution per SPEC §15. The S1 unresolved-resonance flag (2ζf < 3Δf) is recorded; resolution alone is not a standalone bar (D-057). | M1 QC (S1 flag) |
| C3 | Grid identity (`grid_id`, point count), starting at corner A (SPEC §15) | passport `acquisition.grid` |
| C4 | `geometry_calibration` (`corner_coordinates_mm` or `scan_to_panel_edges`) with its uncertainty (SPEC §4.1, §11) | `MISSING_GEOMETRY_CALIBRATION` |
| C5 | Coherence recorded (S1 flag < 0.9 at resonance) | M1 QC |
| C6 | Session, instrument, software and `protocol_id` provenance | passport `acquisition` |

### D. Modal processing

| # | Requirement | Software check |
|---|---|---|
| D1 | The accepted external PolyMAX route (D-027); no internal FRF fitting (D-030) | `FRF_ONLY_INPUT`, `NOT_CURVE_FITTED` |
| D2 | Curve-fitted modes with shapes as dataset 55 (SPEC §15) | `NOT_CURVE_FITTED` |
| D3 | A documented, hashed, immutable frozen modal set (D-026) | `MISSING_FROZEN_MODAL_SET`, `MODAL_SET_MISMATCH` |
| D4 | M1 admission and QC in software | M1 |

### E. Setup repeat (D-058, SPEC §7)

| # | Requirement | Software check |
|---|---|---|
| E1 | A genuine remount, re-suspension or excitation reinstallation of the same physical specimen | M2 `classify_setup_repeat` |
| E2 | A comparable protocol. The same grid supports frequencies, shapes and MAC; a different grid supports frequency-only. | M2 `classify_setup_repeat` |
| E3 | A new `test_run_id`, the same `physical_specimen_id`, and `remount_of` / `remount_kind` / `remount_evidence` | M2 acquisition linkage |
| E4 | The same D1–D3 processing for the repeat | as D |
| E5 | Shared plate quantities (thickness) are not setup scatter | M6.2 comparison inputs |
