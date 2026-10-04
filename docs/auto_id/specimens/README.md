# Specimen passports (M2)

Schema `auto-id/specimen/v1.1` (SPEC §4, §4.1, §7, §11, §19). The validator is
`src/domain/specimen_manifest.py` (`load_specimen_manifest`). A passport separates
four things:

| Identity | Meaning |
|---|---|
| `family_id` | material / campaign family |
| `design_id` | nominal design / geometry |
| `physical_specimen_id` | the manufactured panel, plate or tile |
| `test_run_id` | one experimental acquisition |

The four identity keys are typed (`FamilyId`, `DesignId`, `PhysicalSpecimenId`,
`TestRunId`) and must be distinct. A remount shares `physical_specimen_id` and has a
new `test_run_id`. A different panel always has a different `physical_specimen_id`,
even with the same design and family.

## Rules

- **No unknown fields.** Unknown keys are refused.
- **No defaults for physical values.** A value may be `null` only when it is declared
  in `unavailable` with a reason. The 18 Hz in the SPEC §4.1 example is illustrative;
  `suspension_max_hz` is a measured value with its documented `source`
  (SPEC §19 item 5).
- **Face thickness:** at least 9 points per sheet (SPEC §15).
- **No local absolute paths.** External files are a store plus a relative path, as in
  the fixture manifest.
- **Canonical hash.** `manifest_hash` is the SHA-256 of the validated canonical
  content; key order does not change it.

## Geometry calibration and registration (M2.3)

`services.physical_registration.build_physical_registration(passport)` builds the
`FrozenRegistration` from the passport alone.
- **Inputs:** the geometry calibration, the pinned experimental geometry (M0.2
  fixture) and the FE geometry file, whose identity is verified.
- **Never used:** MAC, frequencies, mode shapes, or trying orientations against modal
  agreement.

| Mode | Physical basis | Physically complete |
|---|---|---|
| `corner_coordinates_mm` | Documented axes checked by the corner-A → x-axis marker; translation from the corner-A correspondence; scale from the physical calibration | yes, if the uncertainty is measured |
| `scan_to_panel_edges` | Documented axes; translation from measured scan-grid-to-panel-edge offsets | yes, if the uncertainty is measured |
| `documented_centered_alignment` | Historical accepted basis: documented axis convention + centre-to-centre placement | **never** |

## Registration uncertainty (M2.4)

`services.registration_uncertainty.evaluate_registration_uncertainty` is diagnostic
only.
- It perturbs within the measured uncertainty (±translation X/Y, ±scale, ±in-plane
  rotation).
- It reports nominal, minimum and maximum MAC per accepted pair.
- It sets `registration_limited` on a 0.8 crossing.
- It never selects or returns a "best" perturbation.
- It is `NOT_AVAILABLE` without measured uncertainty.
- The pairing-change trigger of SPEC §11 needs the M4 pairing policy
  (`DEFERRED_M4`).

## Acquisition linkage (M2.5)

`domain.acquisition_linkage.classify_setup_repeat` returns one of:

| Result | Meaning |
|---|---|
| frequency + shape | eligible for both |
| frequency only | different grid |
| not eligible | different panel, same run or different protocol |
| insufficiently documented | no panel id, remount link or protocol |

`validate_acquisition_links` refuses:
- reused run ids;
- remounts of unknown runs or of other panels;
- cycles.

No Σ_setup value is computed.

## Accepted SP02 / SP13 passports

`SP02.specimen.json` and `SP13.specimen.json` are built only from accepted evidence:
- **calibration and orientation convention:** from the accepted FrozenRegistrations;
- **fixture link and grid:** from the M0.2 fixture manifest;
- **FE geometry:** the CARBON-4C extraction, pinned in the `carbon-project-archive`
  store by SHA-256 and FE identity;
- **identifiers:**
  - `family_id`: SPEC §4.1's family name;
  - `design_id`: the registration names;
  - `test_run_id`: the recorded acquisition container names. These replace the
    provisional M0.2 run labels.

The passport path reproduces the accepted registrations exactly: SP02 `9bf736d3…c164`,
SP13 `a8970e52…58a4` (`tests/test_m2_stage_gate.py`). Their physical basis is the
**historical documented centred alignment**, so they are **not** physically complete.

**What is missing for a physically complete (SPEC §11) registration of these panels:**
- **A physical reference:** either
  - a corner-A marker: the UNV node at corner A, its FE x/y coordinates, and the UNV
    node towards FE +X; or
  - measured scan-grid-to-panel-edge offsets.
- **Measured calibration uncertainty:** translation (mm), scale (relative) and
  rotation (deg).

**Also not recorded in accepted evidence** (all declared `unavailable`):
- the physical panel id;
- measured plan dimensions, masses, face thickness and core height;
- the suspension threshold;
- the acquisition protocol id.

The SP13 121-point / 289-point pair is **not** established as the same panel with an
independent remount. It is therefore not eligible for Σ_setup (SPEC §7).
