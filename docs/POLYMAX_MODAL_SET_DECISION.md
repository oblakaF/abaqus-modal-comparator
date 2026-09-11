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

## Part 1 backend implementation — VERIFIED (2026-09-10)

The raw `SP05_polymax.unv` audit found 28 consecutive dataset-55 records at
zero-based pyuff indices 15–42. Physical fitted records use `id1` as the
processing-set identity (`Processing_nice` or `Processing`), `analysis_type=3`,
`mode_n`, and `eig`. Residual records retain the parent processing name in
`id1` and append the semantic marker `Residuals below ...` or
`Residuals above ...`; they use `analysis_type=5`, `freq_step_n`, and `freq`.
Every record contains 121 nodes and three 121-value response components.

The importer now exposes `ExperimentalModalSet` and
`discover_experimental_modal_sets(path)`. Stable keys are derived
deterministically from the normalized processing name, with
`Dataset 55 modal set` / `dataset-55` used for a single unnamed group. No
pyuff record object escapes the importer. Each fitted mode records its modal-set
key/name, processing name, zero-based pyuff record index, stable record ID, and
source frequency.

Residual filtering is semantic, not frequency-based. The classifier applies an
anchored, case-insensitive `id1` pattern whose form is
`<processing name> Residuals <below|above> ...`. The processing-name prefix
associates each excluded residual with its fitted set. Labels, record indices,
and excluded counts remain in modal-set and returned-dataset metadata.

`load_universal_modal_file(..., modal_set=...)` accepts either the stable key or
literal processing/display name. One valid set remains an auditable implicit
single-set compatibility case. Multiple valid sets without selection raise a
validation error listing the available sets; they are never concatenated. A
missing requested set also raises a validation error.

When dataset 55 is selected, only its physical modes populate
`ModalDataset.modes`. Dataset-58 response and coherence arrays are still parsed
into diagnostic metadata (`dataset_58_role=diagnostic_only`) without running
peak-derived-mode or CMIF candidate selection and without changing fitted
frequencies/shapes. Files with no valid dataset 55 retain the existing
dataset-2414/dataset-58 fallback path. The fast-cache key includes the selected
modal-set value, preventing cross-set cache reuse.

Real-file validation discovered:

- `Processing_nice` (`processing-nice`): 7 physical modes; 2 residuals excluded;
- `Processing` (`processing`): 17 physical modes; 2 residuals excluded.

Both selections loaded explicitly through the installed hardening and cache
stack. Dataset 58 remained diagnostic-only with 121 parsed FRF channels and no
coherence channels present in the selected group. That checkpoint completed
backend Part 1 only; the subsequent Part 2 work is recorded below.

## Part 2 GUI selection and SP05 validation — VERIFIED (2026-09-10)

The Files page now discovers dataset-55 sets asynchronously when the
experimental path changes. A generation token binds each completion to the
exact resolved file, so a stale worker cannot repopulate the selector after a
later path change. Discovery is not connected to Configure/resize events.

The `Experimental modal set` selector shows processing names and physical-mode
counts, plus a compact summary of dataset source, selected set, physical modes,
and excluded residual count. Zero sets visibly retain the dataset-2414/58
fallback; one set is selected visibly and automatically; multiple sets require
an explicit selection before Run. Changing the experimental path clears the
old choice before rediscovery. The control is frozen with the other scientific
configuration controls during RUNNING/STOPPING.

Project schema version 2 remains backward compatible and now carries optional
`inputs.experimental_modal_set` (authoritative stable key) and
`inputs.experimental_modal_set_name` (display provenance). A valid saved key is
restored after rediscovery. A missing saved key produces a warning and requires
reselection. Old projects follow the same zero/one/multiple policy. Modal-set
changes participate in the persistent dirty snapshot; Interface Scale remains
presentation-only.

The selected key is included in both the runtime analysis-directory signature
and the Part-1 UNV binary-cache key, and is passed unchanged to
`load_universal_modal_file`. Comparison-table source cells, Details, quality
summary, Excel quality sheet, and PDF quality page identify dataset 55 and the
selected modal-set name/key. Details and reports also expose excluded residuals
and dataset-58 diagnostic-only provenance. The FRF plot remains populated from
121 dataset-58 channels and labels dataset 55 / the selected set as the fitted
modal source; absent coherence remains `unavailable`, never perfect.

### Real SP05 run — unchanged gates and explicit camera calibration

Inputs were the existing format-2 extraction of `SP05_modal.odb`, Abaqus modes
7–15, and `SP05_polymax.unv`. Geometry used `camera_grid`, full scan, 301 ×
302 mm, never legacy extent-auto. Both runs mapped all 121 points (100%), with
normalized RMS 0.00174931, Abaqus-unit RMS/max residual 0.74555/2.11099 mm,
and independent X/Y comparator-convention factors
0.0007769505/0.0007804594 (planar axes swapped).

`Processing_nice` loaded exactly 7 physical modes and excluded 2 residuals.
Unchanged gates accepted 6 pairs:

- A7 47.747 Hz → E1 50.966983 Hz: −6.3178%, MAC 0.91493;
- A8 148.570 Hz → E2 134.241465 Hz: +10.6737%, MAC 0.95779;
- A9 152.870 Hz → E3 149.172904 Hz: +2.4784%, MAC 0.82977;
- A10 172.400 Hz → E5 166.901014 Hz: +3.2948%, MAC 0.96358;
- A11 172.500 Hz → E4 163.476000 Hz: +5.5201%, MAC 0.83440;
- A12 260.590 Hz → E6 259.455980 Hz: +0.4371%, MAC 0.73289.

The 163.476 and 166.901 Hz fitted records remain two distinct mode shapes and
pair independently to A11 and A10 respectively. E7 at 350.914368 Hz remains
unmatched. Its A15 candidate has +0.22958% signed frequency error but raw MAC
0.31334, so it is rejected by the unchanged MAC gate. A13, A14, and A15 are
unmatched.

`Processing` loaded exactly 17 physical modes and excluded 2 residuals. It also
accepted 6 pairs with the same identities; corresponding MAC values were
0.91481, 0.95819, 0.82912, 0.96615, 0.83435, and 0.70308. The additional
Processing-only in-band unmatched candidates were 295.031884, 364.986848,
380.270497, 386.203793, 400.542062, and 425.545304 Hz. Higher physical modes
443.281531, 461.667110, 468.135167, and 486.312253 Hz remained loaded but lay
outside the FE comparison band. No extra pair was inferred merely from the
larger set.

A native-Tk single-session `Processing_nice → Processing → Processing_nice`
run changed MAC dimensions 9×7 → 9×17 → 9×7, refreshed table source labels and
both MAC/FRF plot files, and returned the first and third runs to identical
pairs and MAC data. The third load reused the `processing-nice` memory-cache
entry. No residual appeared in any physical-mode list, matrix, or table.

## Relationship to SCI-S0 / EMA roadmap

The new SP05 file changes priority, not the general architecture:

- SP05: first use selected curve-fitted dataset-55 PolyMAX modes;
- SP15 or files without trustworthy fitted modes: continue SCI-S0 observability/close-mode diagnostics on dataset 58;
- only if fitted modes are unavailable/insufficient should the pyFBS/SDyPy pLSCF/LSFD path become the primary experimental modal estimator.

The 300 x 300 incomplete-match issue remains separate from the 500 x 500 coordinate-calibration issue. Geometry may be fully mapped while modal observability remains limited by single-reference FRF data and close/mixed modes.
