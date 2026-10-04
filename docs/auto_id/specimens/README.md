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
`TestRunId`). The type is the namespace: `DesignId("X")` is not
`PhysicalSpecimenId("X")`, so the same token in two namespaces is allowed and never
conflated. A remount shares `physical_specimen_id` and has a new `test_run_id`. A
different panel always has a different `physical_specimen_id`, even with the same
design and family. One physical specimen cannot carry two different design or family
identities.

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

| Mode | Physical basis | Registration basis status |
|---|---|---|
| `corner_coordinates_mm` | Documented axes checked by the corner-A → x-axis marker; translation from the corner-A correspondence; scale from the physical calibration | `PHYSICAL` |
| `scan_to_panel_edges` | Documented axes; translation from measured scan-grid-to-panel-edge offsets | `PHYSICAL` |
| `documented_centered_alignment` | Historical accepted basis: documented axis convention + centre-to-centre placement | `LEGACY_REPLAY` with an accepted registration reference, otherwise `INCOMPLETE`; **never** `PHYSICAL` |

**Units.** Passport lengths are physical millimetres: `corner_A.fe_xy_mm`,
`panel_edges.x_mm/y_mm`, `uncertainty.translation_mm` and the surface tolerance. They
are converted to the Abaqus model unit `coordinate_calibration.abaqus_unit` (mm, cm, m
or µm). Experimental raw units are unchanged; the comparator convention
experimental = (FE · R) · scales + translation is kept.

**Two separate facts.**
- **Registration basis status** describes the nominal registration only.
- **Uncertainty availability** (`AVAILABLE` / `PARTIAL` / `NOT_AVAILABLE`) records
  whether the calibration uncertainty was measured. A physical registration without
  measured uncertainty is still `PHYSICAL`; only the M2.4 diagnostic becomes
  `NOT_AVAILABLE` / `PARTIAL`.

**Production readiness.** `PhysicalRegistrationResult.require_production_ready()`
returns the registration for production Auto-ID, or raises
`ProductionReadinessRefusal` with its reasons. It refuses:
- a basis that is not `PHYSICAL` (`LEGACY_REPLAY` or `INCOMPLETE`);
- a missing physical reference;
- an orientation reference other than `corner_A_marker` / `panel_edges`;
- an experimental source identity that is the legacy path/mtime record;
- a missing `physical_specimen_id`.

It never refuses for missing uncertainty alone, and a replay is never upgraded to
`PHYSICAL`.

## Registration uncertainty (M2.4)

`services.registration_uncertainty.evaluate_registration_uncertainty` is diagnostic
only.
- It perturbs within the measured uncertainty (±translation X/Y, ±scale, ±in-plane
  rotation).
- Translation uncertainty is in mm and is converted to the FE model unit.
- It reports nominal, minimum and maximum MAC per accepted pair.
- A MAC that cannot be evaluated (missing or non-finite) marks that perturbation
  invalid. It never enters the minimum/maximum or the crossing, and the status becomes
  `PARTIAL`.
- It sets `registration_limited = True` on a real 0.8 crossing. It sets `False` only
  when every component and every MAC was evaluated; otherwise the flag is `None`.
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
- cycles;
- one `physical_specimen_id` with contradictory `design_id` / `family_id`.

A run that is a remount of itself is refused when the passport is parsed.

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

**Historical accepted-registration replay (regression compatibility).** The passport
path reproduces the accepted registrations with full content equality: SP02
`9bf736d3…c164`, SP13 `a8970e52…58a4` (`tests/test_m2_stage_gate.py`;
`source_identity_basis = legacy_accepted_registration`).

| Fact | SP02 / SP13 |
|---|---|
| Software / regression gate | PASS |
| Registration basis status | `LEGACY_REPLAY` (not SPEC §11 evidence) |
| Uncertainty availability | `NOT_AVAILABLE` |
| Production physical readiness | **NOT_READY** (`require_production_ready()` refuses) |

**Missing physical evidence (the readiness refusal names these):**
- **A physical reference:** either
  - a corner-A marker: the UNV node at corner A, its FE x/y coordinates, and the UNV
    node towards FE +X; or
  - measured scan-grid-to-panel-edge offsets.
- **A physically traceable orientation reference** (`corner_A_marker` or
  `panel_edges`).
- **The physical panel id** (`physical_specimen_id`).
- **A content-based experimental source identity:** a new physical registration
  records it; the replay keeps the legacy path/mtime record.

**Missing uncertainty (separate; does not block readiness on its own):** translation
(mm), scale (relative) and rotation (deg).

**Also not recorded in accepted evidence** (all declared `unavailable`):
- measured plan dimensions, masses, face thickness and core height;
- the suspension threshold;
- the acquisition protocol id.

The SP13 121-point / 289-point pair is **not** established as the same panel with an
independent remount. It is therefore not eligible for Σ_setup (SPEC §7).
