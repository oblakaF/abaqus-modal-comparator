# PolyMAX / Dataset-55 Modal-Set Import Decision

**Status:** post-HUD scientific data-import priority

## Confirmed SP05 file structure

A new experimental file, `SP05_polymax.unv`, contains the data type needed for a more defensible Abaqus comparison: curve-fitted PolyMAX modal results in UNV dataset 55, in addition to raw FRF data.

Confirmed structure from the file audit:

- geometry: dataset 2411;
- 121 points = 11 x 11 camera grid;
- Z is constant at -1 for the grid;
- dataset 164 reports `USER_DEFINED`, consistent with an uncalibrated Polytec camera-grid geometry;
- therefore raw geometry magnitudes must not be assumed to be physical SI coordinates; use the explicit camera-grid calibration workflow introduced in the HUD branch.

## Dataset-55 modal groups

The file contains multiple dataset-55 modal-result groups.

### `Processing_nice`

Operator-selected clean PolyMAX subset, with physical modal frequencies approximately:

- 50.9671 Hz
- 134.2415 Hz
- 149.1728 Hz
- 163.4756 Hz
- 166.9018 Hz
- 259.4555 Hz
- 350.9146 Hz

It also contains residual records around 30 Hz and 500 Hz. Those residual records are not physical structural modes and must be excluded from the physical-mode list.

### `Processing`

Full PolyMAX result, with 17 physical poles. It includes the `Processing_nice` low-order modes plus additional poles approximately at:

- 295.0317 Hz
- 364.9868 Hz
- 380.2709 Hz
- 386.2037 Hz
- 400.5417 Hz
- 425.5452 Hz
- 443.2821 Hz
- 461.6669 Hz
- 468.1345 Hz
- 486.3124 Hz

The laboratory interpretation is therefore:

- `Processing` = full PolyMAX pole set;
- `Processing_nice` = manually selected operator clean subset.

## Scientific consequence

Dataset 55 already contains identified experimental modal frequencies and mode shapes. When a valid dataset-55 modal group is selected, it must be the primary experimental modal source. Raw dataset-58 FRF peak-derived shapes remain diagnostic/fallback data, not the primary modal estimate.

The close pair near 163-167 Hz is especially important: PolyMAX identifies two separate experimental modes (~163.4756 and ~166.9018 Hz), supporting the earlier hypothesis that raw single-reference FRF peak snapshots can mix or fail to separate close modes.

The fact that `Processing_nice` retains only one mode near ~350 Hz means an eventual comparison does not have to produce a complete FE-to-EXP one-to-one set; missing correspondence can be an actual experimental/model-observability result rather than an importer failure.

## Confirmed importer defect

The current `src/universal_reader.py::load_universal_modal_file` loops over all dataset-55 records and appends every valid record into one common `modes` list. It does not preserve/select modal-result group provenance and therefore can mix:

- `Processing_nice` physical modes;
- `Processing_nice` residuals;
- `Processing` physical modes;
- `Processing` residuals.

This is not scientifically acceptable for files containing multiple PolyMAX modal sets.

## Required importer behavior

Before using `SP05_polymax.unv` for scientific comparison, implement explicit modal-set discovery and selection:

1. discover multiple dataset-55 modal-result groups;
2. group records by their stored result/processing identity (for this file, at least `Processing` and `Processing_nice`);
3. identify and exclude residual datasets such as `Residuals below ...` and `Residuals above ...` from physical modes;
4. expose the available modal sets to the user;
5. allow explicit modal-set selection;
6. preserve the selected modal-set name/provenance in `ModalDataset.metadata`, project persistence, and reports;
7. when a valid dataset-55 set is selected, do not use dataset-58 peak-derived modes as the primary source;
8. keep dataset 58 available for FRF/coherence diagnostics and explicit fallback workflows;
9. do not use FE frequencies to select or prune PolyMAX poles.

For `SP05_polymax.unv`, `Processing_nice` is a reasonable default candidate because it is the operator-curated clean set, but the importer should not silently hard-code that string globally. Selection/default policy should be explicit and auditable.

## Test requirements

Add synthetic/fixture coverage for:

- one dataset-55 modal group;
- multiple named dataset-55 groups;
- physical modes plus residual records;
- explicit modal-set selection;
- deterministic default selection when appropriate;
- dataset-55 selected -> dataset-58 remains diagnostic only;
- no dataset-55 -> existing dataset-58 fallback unchanged;
- modal-set provenance survives project save/load and report output.

## Relationship to current HUD work

Do **not** broaden the current HUD/responsive release task with this importer change unless a release-critical regression specifically requires it. Finish HUD responsiveness/manual QA first, merge the HUD branch, then implement this as the first focused scientific-data-import change before relying on SP05 PolyMAX results.

This change should precede any attempt to judge SP05 mode-pair completeness or to implement a new FRF curve fitter for SP05. Proper imported PolyMAX modes are preferred over raw FRF peak snapshots when available and internally consistent.

## Relationship to SCI-S0 / EMA roadmap

The new SP05 file changes priority, not the general architecture:

- SP05: first use selected curve-fitted dataset-55 PolyMAX modes;
- SP15 or files without trustworthy fitted modes: continue SCI-S0 observability/close-mode diagnostics on dataset 58;
- only if fitted modes are unavailable/insufficient should the pyFBS/SDyPy pLSCF/LSFD path become the primary experimental modal estimator.

The 300 x 300 incomplete-match issue remains separate from the 500 x 500 coordinate-calibration issue. Geometry may be fully mapped while modal observability remains limited by single-reference FRF data and close/mixed modes.
