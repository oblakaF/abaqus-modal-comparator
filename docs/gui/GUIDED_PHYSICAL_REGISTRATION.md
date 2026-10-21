# Guided physical registration of a new FE mesh (CORE-E2E-C)

A new ODB whose FE geometry differs from an accepted one is no longer a dead end: when independent physical evidence
of the scan exists, the user builds a physical registration for exactly that FE geometry in the GUI. Without that
evidence the comparison stays a `FREQUENCY_ONLY_DIAGNOSTIC` with separate mode views.

## User path

1. **1. Files**: choose the ODB (or an extraction `manifest.json`), the UNV/UFF and the modal set; run the analysis.
   With an ambiguous orientation and no reusable accepted registration the result is `FREQUENCY_ONLY_DIAGNOSTIC`.
2. **3. Mode shapes**: press **Establish physical registration...**. The dialog shows the files of the last analysis:
   the ODB, FE nodes and modes, FE geometry identity, the experimental file and its SHA-256, points, modal set and
   measured DOFs.
3. Choose the physical evidence:
   - **Use accepted scan calibration of this file**: offered when the experimental file is, by SHA-256 and size, the
     source of an accepted physical passport (`docs/auto_id/specimens/*.physical.specimen.json`) with a physical
     calibration;
   - **Load evidence file...**: a `auto-id/guided-physical-evidence/v1` record; **Write evidence template...** writes one
     with every physical field explicit and empty (an unfilled template is refused).
   The table lists every field with `PROVIDED` / `MISSING`.
4. **Check and build**. The checks are listed; a refusal names the field and the reason. When the accepted evidence
   refers to another FE model, the reference FE geometry is needed: from the data store, or **Locate reference FE
   geometry file...** (its pinned SHA-256 is checked; the `geometry.csv` of an extraction of the accepted ODB is the
   same file).
5. **Apply and run analysis**: the gated comparison (pairs, MAC, frequency errors, manual review, mode views, reports)
   runs with the registration; the warning and the status line name it. The extraction is reused (no Abaqus).
6. **Save registration...** / **Open saved registration...**: the record is hash-sealed and re-verified against the
   loaded files when opened and before every analysis; **Clear guided registration** returns to automatic geometry.

## Required physical evidence

| Item | Content |
|---|---|
| Orientation | corner-A marker, or measured scan-to-panel-edge offsets, with the photograph / marker record (`experimental_axes_in_fe`, reference `corner_A_marker` or `panel_edges`) |
| Coordinates and units | physical scan window (camera grid) or metric coordinates, units, provenance |
| Measured surface | FE instance and side (`max_z` / `min_z`) of the face the scanner measured |
| Measured DOFs | for example `U3` |
| FE frame | the FE geometry identity the orientation is stated for, or a reference FE geometry in the same frame |
| Experimental source | SHA-256, size and modal set of the experimental file the evidence describes |

## Checks

- Physical calibration mode (`corner_coordinates_mm`, `scan_to_panel_edges`); `documented_centered_alignment` is refused.
- Orientation reference physically traceable; mirrored axes (determinant −1) refused; the corner-A marker must agree with
  the stated axes (existing M2.3 rule).
- The loaded experimental content (SHA-256, size), modal set, point count and measured-DOF contract are those the
  evidence describes.
- FE frame: the loaded model is the FE model the evidence refers to (exact FE geometry identity), or its measured
  surface (selected exactly as the M2 builder selects it) is node for node and coordinate for coordinate the measured
  surface of the reference FE geometry: the canonical identity of the surface node labels and x, y, z must be equal,
  and the reference surface's label set must be the accepted registration's `fe_mapping_node_subset`. Bounding boxes
  are not evidence (a mirrored, rotated or relabelled mesh of a symmetric panel keeps them). Otherwise
  `FE_FRAME_NOT_VERIFIED`; a different surface mesh needs an evidence record stated for that FE model. The old node
  mapping is never reused.
- The registration is built by the accepted M2.3 core (`physical_registration.register_from_physical_calibration`);
  it reads no MAC, frequency or mode shape and never chooses among geometric candidates.
- Mapping: matched fraction ≥ 0.90 and normalised RMS ≤ 0.03 (the comparator's existing geometry limits), every point
  on its own FE node.

## Scientific scope

A guided registration is a diagnostic engineering registration of these exact files: it enables pairs and MAC. It is
not governed evidence, adds no Auto-ID observation, is never production-ready and does not replace the SPEC v1.2 §11
passport / fixture route. Choosing one of the geometric orientation candidates is never evidence.

## Validation (CORE-E2E-C, 2026-10-16)

- On the accepted SP-13 mesh the guided path reproduces the accepted registration hash `2eeeaa86…` exactly.
- New `SP13_modal.odb` (1 558 721 nodes; faces identical, refined core): with the accepted SP-13 scan calibration and
  the reference FE geometry `SP13_fe_geometry.csv` (`78d19737…`), the measured surface CFRP_PLATE_TOP max_z of both
  models is identical (29 754 nodes, labels and coordinates `3087cba5…`, labels `bdfec8bf…` = the accepted
  registration's subset); registration
  `e9c8dc5d…`, matched 100 %, RMS 1.23 mm. The comparison gives the five SP-13 pairs, MAC within 1e-5 of the accepted
  model.
- SP-04 (dataset 58, no physical record): no evidence, every field `MISSING`; the analysis stays
  `FREQUENCY_ONLY_DIAGNOSTIC`.

## Closure (2026-10-17)

**CORE-E2E-C: ACCEPTED / CLOSED** (PR #85, merge `24c755d`): implementation `0ccfdd8`; R1 `6a893f6` (FE frame by the
identity of the measured surface, not bounding boxes; otherwise `FE_FRAME_NOT_VERIFIED`) and R2 (dialog recovery from
any background error); R3 `13af39a` (no stale registration: every input change invalidates the shown result, a
generation counter discards overtaken background builds). The guided registration remains a diagnostic engineering
registration: `governed = false`, `production_ready = false`, no Auto-ID observation.

## R7 (2026-10-21): shell mid-surface guard (diagnostic; branch `fix/r7-shell-modal-safety`)

For a conventional shell (S4R …) all nodes lie on the mid-surface, so `max_z` and `min_z` select the same nodes and
`side` cannot name the measured face.

- The guided path **refuses** a measured instance that a supplied FE element summary (INP text, with its SHA-256)
  confirms to be a conventional shell.
- A degenerate measured surface of unknown element type is registered as before, with a stated limitation: the face
  is fixed only by the Z sign of the axes.
- An explicit face-versus-normal field is proposed, not implemented, because it would change the governed passport
  schema. See `docs/reconciliation/R7_SHELL_MODAL_SAFETY.md`.
