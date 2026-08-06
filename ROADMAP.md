# Roadmap

Working notes for hardening this program toward reproducible scientific use.
Items move between sections as they are reproduced, fixed, or ruled out.

## Stage 1 status: done

- `ROADMAP.md` created.
- Direct tests added for previously uncovered amplitude-correlation and
  reporting-hardening modules.
- Base Excel/PDF behavior is characterized by sheet, header, summary, and page
  checks rather than file-size-only smoke tests.
- AutoMAC/COMAC mask behavior has regression coverage.
- Recoverable project/session/plot errors are typed or logged instead of being
  silently discarded.
- The suite reported 105 collected executions, all passing, when Stage 1 was
  recorded.

Remaining baseline gaps:

- dependencies have lower bounds only; there is no lock file;
- CI runs only on Ubuntu although the application targets Windows and Abaqus;
- real vendor ODB/UNV regression fixtures are not stored in the repository.

The machine-readable baseline snapshot (accepted pairs, signed and absolute
frequency errors, AutoMAC/COMAC matrices, geometry-mapping distances, warning
list, manual-review decisions, input-file SHA-256 hashes, and pinned
Python/NumPy/SciPy/pyuff/openpyxl/matplotlib versions) is captured in
`docs/baseline/stage0_baseline.json`, frozen at commit `997e707` (the last
commit before Stage 2 numerical work began). Regenerate it with
`tools/generate_baseline_snapshot.py` whenever the accepted reference result
is intentionally allowed to change.

## Required implementation order

The order below is mandatory for an implementation agent:

0. diff every numerical change against `docs/baseline/stage0_baseline.json`
   before treating it as accepted;
1. complete scientific hardening;
2. add explicit Polytec/Testlab data lineage and the optional future
   three-source comparison workflow;
3. implement the current user-requested UI refinements;
4. consolidate the architecture and reproducibility tooling;
5. validate against the real-data test matrix (Stage 6) before relying on the
   tool for a new Abaqus version, UNV/UFF variant, or measurement setup.

Every numerical change must include a reproducing test and a before/after
comparison on the current full 121-point, eight-pair, single-reference result
frozen in `docs/baseline/stage0_baseline.json` (Job-1.odb + the Auxetic
Polytec scan, modes 6-17; regenerate with
`tools/generate_baseline_snapshot.py`). This updates the older "seven-pair"
figure used earlier in this document: the real current run of this exact
dataset accepts eight pairs, most likely because the rigid-body detection
method changed from a near-zero frequency threshold to shape-projection
residual filtering before this figure was first written. Do not silently
change MAC/frequency thresholds or the accepted reference
assignment. Do not change a numerical algorithm, its acceptance thresholds,
and its display/reporting together in one step. Every warning that affects
scientific interpretation must surface in the GUI, Excel export, PDF export,
and run metadata alike — not just one of them. Until Stage 2 is complete,
results must be presented with the explicit caveats of the current analysis
scenario rather than as unqualified numbers.

---

## Stage 2 — scientific hardening from the code audit

These seven items affect the meaning and reliability of MAC, FRF confidence,
geometry mapping, and coordinate handling. They must be completed before
Polytec support.

### 0. Data model additions required by this stage

Add explicit fields instead of relying on dynamic attributes:

`ModeShape`:

- `measured_dofs` — this mode's own measured-DOF mask (see item 3);
- `measurement_directions`;
- `coordinate_system_id`;
- `source_confidence`;
- `source_lineage`.

`ModePairResult`:

- `common_dof_mask`, `geometry_valid_mask`;
- `common_dof_count`, `unique_point_count`;
- `dof_coverage_fraction`, `point_coverage_fraction`, `spatial_coverage`;
- `acceptance_reasons`, `rejection_reasons`;
- `automatic_decision`, `manual_decision`.

Remove the critical dynamic `setattr` calls these fields currently replace.
This item lands first because items 1–7 below populate these fields.

### 1. Treat missing coherence as unavailable, not perfect — done

Fixed in `universal_frf_review.py`, `cmif_validation.py`, `enhanced_reporting.py`,
`ui_enhancements.py`, `quality_control.py`, and `fast_cache.py` (analysis
pipeline version bumped to invalidate stale caches). The single-reference
local-SVD path in `cmif_separation.py` keeps its own, separately-reasoned
`unavailable → full weight` choice for now — that weighting feeds the SVD
residual itself rather than a displayed confidence label, so it is left for
item 2 (multi-reference FRF/CMIF) rather than folded into this fix.

Previously confirmed behavior:

- when no dataset-58 coherence channels exist,
  `mean_coherence = np.ones_like(...)`;
- a peak can consequently be labeled `High peak confidence` without measured
  coherence.

Required change:

- introduce `computed`, `unavailable`, and `parse_error` coherence states;
- only computed coherence may increase confidence;
- unavailable coherence must remain unavailable in the UI and reports;
- parsing errors must produce visible warnings;
- peak extraction may continue without coherence, but fabricated values must
  not affect ranking or confidence.

Required tests:

- complete, absent, partially missing, and malformed coherence channels;
- UI/report labels;
- cache invalidation after this semantic change.

### 2. Implement a real multi-reference FRF/CMIF path — landed, one piece deferred

Implemented in `cmif_separation.py`: `_build_multi_reference_frf_block` groups
FRF response channels by the full (response node/direction, reference
node/direction, physical quantity, frequency-axis signature) key instead of
`universal_hardening._safe_select_frf_group`'s single best-scoring group, so
independent references are no longer discarded. It builds a genuine complex
response x reference x frequency matrix. A channel signature match (length,
first/last value, median step) is only the coarse candidate filter; every
individual channel's frequency samples are additionally verified against the
canonical axis with `np.allclose`, since two axes can share that coarse
signature while differing sample-for-sample. A duplicate channel (the same
response/reference key seen twice) is kept once and recorded with status
`"equivalent"` when the two occurrences are numerically identical, or has
every occurrence excluded and recorded with status `"conflicting"` when they
disagree — never silently resolved by picking the first one. A response DOF
not covered by every included reference is excluded rather than fabricated.
`reference_count` now genuinely exceeds 1 when independent references are
present (previously always 1, so
`cmif_validation.validate_close_mode_candidates`'s multi-reference promotion
path was dead code). `_cmif_singular_values` computes the conventional
**per-frequency multi-reference CMIF singular values**, and
`close_mode_separation` metadata reports, per cluster, the matrix rank
capacity and the actual `cmif_max_second_to_first_singular_ratio`, plus
initial/common response-DOF counts, coverage fraction, duplicate-channel
status, and dropped-reference reasons. `validate_close_mode_candidates` now
decides acceptance from that real CMIF ratio, not from the local candidate
shape extractor's own component-energy ratios.

Terminology is kept distinct on purpose: **per-frequency multi-reference CMIF
singular values** are the real evidence of an independent second mode; a
**local snapshot-SVD candidate shape** is what `_local_svd_components` still
extracts (now stacking every included reference's band snapshots as extra
columns, mathematically identical to the prior single-reference computation
when only one reference is present — verified by the pre-existing
`test_close_mode_svd.py` cases, unchanged). A full per-frequency-line CMIF
modal curve fit — deriving shapes directly from the H(f) singular vectors
across frequency with proper residue-based curve fitting, rather than the
local snapshot-SVD method — is **not implemented** and remains a separate,
larger future task; it is not required for this item's completion criteria
below.

Original current risk (now addressed above):

- grouping by `ref_node`/`ref_dir` can separate every reference;
- close-mode data can be keyed only by response DOF;
- the required response-DOF by reference-DOF matrix is not guaranteed.

Required change:

- identify channels by response node/direction and reference node/direction;
- group compatible physical quantities and frequency axes without dropping
  independent references;
- construct the complex response × reference matrix at every frequency line;
- perform conventional multi-reference CMIF/SVD;
- keep single-reference local SVD diagnostic-only;
- report reference count, matrix rank, singular-value ratios, rejected
  candidates, and confidence.

Required tests:

- one-reference and two-reference synthetic data;
- duplicate/missing references;
- incompatible axes;
- confirmation that single-reference candidates are not automatically promoted.

### 3. Use a separate measured-DOF mask for every experimental mode — landed, one gap documented

Fixed in `reviewed_core.py`: `experimental_measurement_mask` (one array,
unioned across every experimental mode) is replaced by
`experimental_measurement_masks` (one array per mode). An explicit Testlab
mask still takes precedence per mode; a mode without one now infers its own
mask from its own vector energy only, via the extracted
`_inferred_measurement_mask` helper — never from another mode's energy, which
would have reintroduced the same leak for the "no explicit mask" case.
`_mac_matrix_for_geometry` and `_build_mode_pairs` index into that per-mode
list by experimental column instead of applying one shared mask to every
column, so a channel measured only in mode A can no longer be scored as
measured for mode B (confirmed by a reproducing test that fails without the
fix: two experimental modes with disjoint measured components and
deliberately anti-correlated "phantom" data in each other's unmeasured
direction — MAC collapses if the leak is present, stays ~1.0 once fixed).
`project_review.build_manual_pair` had the identical leak (it called the same
all-modes union for a single manually chosen pair) and is fixed the same way.
Persistence was already fine: `fast_cache._clone_mode` round-trips the
per-mode `measured_dofs` attribute correctly, and `.amcp.json` project files
never serialize `ModeShape` objects at all — they store scalars and re-import
from the original files on load, so masks are always regenerated fresh.
`advanced_metrics.py` (AutoMAC/COMAC) needed no code change: it already
consumed `pair.measured_dof_mask`, which is now genuinely per-pair-correct,
so ANDing every accepted pair's mask together to get one common AutoMAC/COMAC
grid is now a legitimate reduction over correct inputs rather than
compounding an already-leaked one — confirmed by a test showing two pairs
with genuinely disjoint per-mode masks now correctly make AutoMAC/COMAC raise
instead of silently computing over falsely-shared DOFs, and a second test
showing a genuinely shared mask still produces a valid AutoMAC/COMAC result.

Documented gap, not fixed here: `ModePairResult.abaqus_vector` /
`experimental_vector` / `coordinates` are stored already row-filtered to that
pair's own `valid_rows` (only the measured rows are kept), and
`advanced_metrics._common_pair_data` (plus a duplicated equivalent in
`metrics_normalization.py`) then ANDs masks positionally across pairs,
implicitly assuming every pair kept the *same* rows in the *same* order. That
assumption holds for every current importer (every mode in one loaded dataset
still gets an identical or coincidentally-aligned mask in practice today), so
this is not reachable with current real data, but it is not actually
guaranteed once masks can genuinely differ per mode.

Follow-up landed (minimal guard, not the full realignment): `ModePairResult`
gained a `node_ids` field (set by both `reviewed_core._build_mode_pairs` and
`project_review.build_manual_pair`, sliced by that pair's own `valid_rows`
alongside `coordinates`). Before combining any pairs,
`advanced_metrics._verified_pairs_share_one_measurement_grid` now checks
every accepted pair has the same `node_ids` in the same order, the same
vector shapes, and an explicit `measured_dof_mask` before allowing
`_common_pair_data` to AND them together; a mismatch raises `"AutoMAC/COMAC
unavailable: verified pairs use different measurement grids."` instead of
silently correlating the wrong physical points. `metrics_normalization.py`'s
duplicate `_normalized_common_pair_data` — the function actually installed
in production, found only while wiring this in — now calls the same guard
rather than skip it. A genuine *realignment* of pairs that keep different
node subsets (rather than refusing them) is still the deferred, larger task
described above, touching `reporting.py`, `reporting_hardening.py`,
`amplitude_correlation.py`, and `modal_scaling.py`.

Also fixed in the same pass: `_inferred_measurement_mask` no longer treats an
all-zero mode with no explicit mask as "every finite DOF is measured" — it
now returns an all-False mask, since zero energy and no explicit mask leaves
no reliable basis to claim anything was measured.

Required tests:

- different missing channels/components by mode — done;
- inferred-mask fallback — done, now per-mode, and an all-zero mode no longer
  defaults to fully measured;
- AutoMAC and COMAC consistency — done: different node IDs are rejected with
  a clear error, and the same node IDs/order still compute as before.

### 4. Add minimum common-DOF and spatial-coverage gates

Current weakness:

- `np.any(dof_mask)` allows MAC to be calculated from one common scalar DOF.

Required change:

- configurable minimum common DOF count;
- minimum unique point count;
- minimum measured-DOF coverage fraction;
- minimum measurement-point coverage fraction;
- pairs below the limits must be unmatched or marked with one of the explicit
  statuses `accepted`, `insufficient DOF coverage`,
  `insufficient point coverage`, `insufficient spatial coverage`, or
  `MAC unavailable` — never silently dropped;
- a pair carrying any non-`accepted` status must not participate in automatic
  Hungarian assignment as a valid candidate;
- expose counts, fractions, thresholds, and decisions in UI, projects, Excel,
  PDF, and reproducibility metadata.

Default thresholds must be chosen only after checking the current seven accepted
pairs.

### 5. Exclude geometry outliers and duplicate FE-node mappings from MAC

Current behavior:

- distant and duplicate mappings create warnings but can still enter MAC;
- repeated mapping to one FE node can give that location extra weight.

Required change:

- create an explicit geometry-validity mask;
- exclude out-of-tolerance points from accepted MAC;
- resolve duplicate mappings by one of: one-to-one assignment, documented
  aggregation, or selection of the nearest experimental point;
- retain complete audit diagnostics for rejected points;
- keep any unfiltered MAC only as a diagnostic, not the acceptance value.

Required tests:

- distant outliers;
- duplicate mappings;
- unchanged valid 121-point result;
- warning and export audit tables.

### 6. Make geometry alignment robust for partial or off-center grids

Current risk:

- independently centering bounding boxes can misplace half-panel or corner-only
  measurement grids.

Required change:

- retain the fast complete-grid path;
- add reliable support using anchors, a supplied transform, constrained ICP,
  or stable point identifiers;
- for every solution, record transform source, scale, rotation, translation,
  determinant/reflection, RMS residual, inlier fraction, an ambiguity score,
  and the number of alternative transforms considered;
- never silently accept a poorly constrained or symmetrically ambiguous
  solution — block automatic acceptance instead.

Required tests:

- full, half-panel, and corner grids;
- known translated/rotated subsets;
- ambiguous symmetric geometry.

### 7. Apply UNV dataset-2420/local-coordinate transformations

Current limitation:

- local-coordinate information is detected but vectors are not transformed.

Required change:

- parse supported dataset-2420 definitions;
- resolve node/response coordinate-system references;
- rotate vectors and measurement directions into a documented common global
  system before MAC;
- retain original and transformed directions;
- fail clearly on missing or unsupported references.

Required tests:

- global-only data;
- one and multiple local systems;
- missing references;
- equivalence of known global and local exports.

### Stage 2 completion criteria

- every item has a reproducing test;
- confirmed defects are fixed without unrelated numerical changes;
- the `docs/baseline/stage0_baseline.json` eight-pair reference result is
  compared before and after every change;
- reports record actual masks, coverage, coherence state, geometry filtering,
  and coordinate transformations;
- semantic changes bump the analysis-pipeline cache version.

---

## Stage 3 — explicit Polytec/Testlab lineage and optional three-source analysis

### Current real workflow

The current laboratory data represent one physical experiment:

```text
Measurement system: Polytec scanning laser vibrometer
Processing/database software: Simcenter Testlab
Imported container: LMS / UNV / UFF
Comparison: Abaqus FEM ↔ Polytec experiment processed in Simcenter Testlab
```

Simcenter Testlab is not a second independent experiment in this workflow. It is
software used to store/process the Polytec measurements. Therefore the current
project must not calculate a meaningless `Simcenter ↔ Polytec` comparison from
two exports of the same physical dataset.

The default UI label should be explicit, for example:

```text
Abaqus FEM ↔ Polytec experiment (processed in Simcenter Testlab)
```

Do not label the same dataset once as `Simcenter` and once as `Polytec` merely
because it was imported from a Testlab UNV/UFF file.

### 0. Separate physical source, processing software, and file container

The data model must store these as different concepts:

- `experiment_id` — stable identity of the physical measurement campaign;
- `measurement_system` — e.g. Polytec PSV/laser vibrometer, accelerometers,
  impact hammer, shaker, SCADAS;
- `processing_software` — e.g. Simcenter Testlab;
- `import_format` / `import_adapter` — LMS pointer, UNV/UFF 55/2414, dataset 58,
  future native Polytec API;
- `source_display_name` — human-readable experiment label;
- `parent/raw-data lineage` — enough metadata to identify two exports from the
  same experiment.

Two datasets with the same `experiment_id` or declared common lineage are not
independent sources. The program may compare processing variants diagnostically,
but must label them as reprocessed versions of one experiment rather than as
independent experimental validation.

Existing projects must migrate to the default lineage:

```text
measurement_system = Polytec
processing_software = Simcenter Testlab
experiment_id = existing imported experimental file/campaign
```

unless the user explicitly identifies a different physical measurement system.

### Goal for the future optional mode

Support a project that can later contain two genuinely independent experimental
datasets, for example:

- Abaqus numerical modes;
- a contact/SCADAS/accelerometer experiment processed in Simcenter Testlab;
- a separate Polytec laser-vibrometer experiment, possibly also processed in
  Simcenter Testlab.

Only in that situation should the application enable all three independent
pairwise comparisons.

This stage includes both the data/algorithm work and the minimum comparison UI
needed to use all available sources. The comparison windows must not be
postponed to Stage 4.

### 1. Initial Polytec import path

First implementation phase:

- accept Polytec data exported as ASCII UFF/UNV;
- reuse the hardened universal-file importer;
- record Polytec as the measurement system and Testlab as processing software;
- preserve this lineage in metadata, caches, UI, tables, projects, and reports;
- prefer geometry plus curve-fitted modal datasets 55/2414;
- permit dataset-58 FRFs under the Stage-2 confidence and scientific limits.

Native proprietary Polytec-file/API support is deferred until a real sample and
stable supported access method are available.

### 2. Generalize the data model

Replace the fixed conceptual structure:

```text
Abaqus + one generic Experimental dataset
```

with named numerical and physical experimental datasets, while keeping
processing software separate:

```text
Numerical:
  Abaqus

Physical experiment A:
  Polytec measurement
  processed in Simcenter Testlab

Optional independent physical experiment B:
  accelerometer/SCADAS measurement
  processed in Simcenter Testlab
```

Each dataset must have a stable source ID, experiment ID, display name,
measurement-system type, processing software, import method, file path/hash,
geometry, modes, measured directions, and confidence metadata. Store results
per independent source pair and migrate existing two-source project files
without changing their numerical results.

### 3. Calculate available pairwise comparisons conditionally

#### Current project with one physical experiment

Calculate only:

- Abaqus FEM ↔ Polytec experiment processed in Simcenter Testlab.

Do not create a separate Simcenter–Polytec pair from the same data lineage.

#### Future project with two independent physical experiments

Enable:

- Abaqus ↔ independent Simcenter/contact experiment;
- Abaqus ↔ independent Polytec experiment;
- independent Simcenter/contact experiment ↔ Polytec experiment.

For every valid pair provide:

- signed and absolute frequency differences;
- MAC on valid common measured directions/DOFs;
- common-point and DOF coverage;
- geometry-transform quality;
- source/confidence status;
- damping comparison where available;
- unmatched and reordered modes.

The experimental–experimental comparison is useful only when the two datasets
represent genuinely independent measurements. It then separates numerical-model
error from disagreement between measurement systems.

### 4. Expand the comparison windows for current and future modes

This is a required part of Stage 3.

#### Conditional source-pair selector

The selector must reflect actual independent data, not software names.

For the current project show:

- `Abaqus ↔ Polytec (processed in Testlab)`.

When an independent contact/Simcenter experiment is also loaded, enable:

- `Abaqus ↔ Simcenter contact experiment`;
- `Abaqus ↔ Polytec experiment`;
- `Simcenter contact experiment ↔ Polytec experiment`;
- `Three-source comparison`.

Disable or hide unavailable pairs. Never create a pair merely because one file
was exported by Testlab.

The selected source pair must be one shared state used by the table, mode-shape
view, frequency/MAC plots, FRF/quality diagnostics, AutoMAC/COMAC, manual
review, and exports.

#### Comparison table window

The table must switch between the selected valid pair and show:

- left/right physical source and mode numbers;
- measurement system and processing software;
- left/right frequencies;
- signed and absolute error;
- MAC;
- common point/DOF coverage;
- geometry quality;
- source type and confidence;
- damping values where available;
- automatic/manual decision.

For the future independent three-source case, add a summary table with one row
per consolidated mode and columns for all three frequencies and all three
pairwise MAC values.

#### Mode-shape comparison window — same top-level tab 3

Keep all mode-shape work on the existing top-level tab:

```text
3. Mode shapes
```

Inside that tab provide two view modes:

1. `Pair comparison` — the existing detailed left/right/overlay view for one
   selected source pair;
2. `Three-source comparison` — a dedicated view enabled only when Abaqus and
   two independent experimental datasets are loaded.

The `Three-source comparison` view must keep one consolidated physical mode
selected and show all three comparisons simultaneously on the same tab:

- Abaqus ↔ Simcenter/contact experiment;
- Abaqus ↔ Polytec experiment;
- Simcenter/contact experiment ↔ Polytec experiment.

Recommended wide-window layout:

- top row: the three source mode shapes — Abaqus, Simcenter/contact experiment,
  Polytec;
- bottom row: three pairwise overlay/correlation cards — A–S, A–P, S–P.

Each pairwise card must show at least:

- source names;
- frequencies and signed/absolute error;
- MAC;
- common point/DOF coverage;
- confidence/measurement direction;
- compact overlay or amplitude-correlation figure.

Clicking or double-clicking a pairwise card must open/select that pair in the
full `Pair comparison` view without losing the consolidated mode selection.
At narrow window widths, reflow the six panels vertically or as `2 + 1` rows;
do not reduce plots to unreadable thumbnails.

The existing/future **Previous mode** and **Next mode** controls must navigate
the consolidated mode in both view modes, so all three pairwise cards update
together.

For the current one-experiment project, hide or disable `Three-source
comparison`; retain the normal pair view labeled
`Abaqus ↔ Polytec (processed in Simcenter Testlab)`.

#### Frequency and MAC windows

Every frequency-regression, MAC matrix, amplitude-correlation, and accepted-pair
plot must identify the selected physical source pair. In the independent
three-source case, the user must be able to inspect all three pairs without
reloading files or rerunning extraction.

#### AutoMAC/COMAC windows

AutoMAC belongs to one physical dataset; COMAC/cross-correlation belongs to one
independent source pair.

Current project:

- Abaqus AutoMAC;
- Polytec-experiment AutoMAC;
- Abaqus–Polytec COMAC.

Future independent three-source project:

- Abaqus AutoMAC;
- Simcenter/contact-experiment AutoMAC;
- Polytec-experiment AutoMAC;
- Abaqus–Simcenter/contact COMAC;
- Abaqus–Polytec COMAC;
- Simcenter/contact–Polytec COMAC, when common coverage is sufficient.

The selected source/pair and valid common grid must be explicit in titles,
legends, interpretation blocks, and export file names.

#### FRF and quality windows

Show diagnostics per physical experiment. The current Polytec FRFs may be
processed/imported through Testlab but remain labeled as Polytec experimental
data. In the future independent case, show contact/Simcenter and Polytec
FRF/coherence/peak diagnostics separately, plus pair-specific warnings.

#### Manual-review window

Manual decisions must be stored per independent source pair and mode pair.
Reprocessed exports of the same physical experiment must retain lineage and must
not masquerade as independent validation decisions.

#### Reports and project persistence

Excel, PDF, project files, cached figures, and exported PNG/data files must
record:

- physical measurement system;
- processing software;
- experiment ID/lineage;
- selected valid source pair;
- all available independent pairwise results.

File names must not collide between source pairs.

Required UI regression tests:

- current lineage is displayed as Polytec processed in Testlab;
- no false Simcenter–Polytec pair appears for the same experiment;
- loading a second independent experiment enables all three pair choices and
  the `Three-source comparison` view;
- switching among independent pairs updates every linked tab;
- all three cards on tab 3 update for the same consolidated mode;
- no stale figures or rows remain from the previous pair/mode;
- source labels are correct for experimental–experimental comparison;
- decisions remain independent per valid source pair;
- reopening a project restores lineage, sources, selected view, and current
  consolidated mode.

### 5. Respect Polytec measurement directions

Polytec data must not automatically be interpreted as global `U3`.

Requirements:

- support 1D line-of-sight direction vectors per point;
- support 3D Polytec vectors when exported;
- project compared vectors onto the actual measured direction or transform full
  vectors into the common global frame;
- integrate with mode-specific masks and local-coordinate transformations;
- report whether each comparison uses line-of-sight scalar data or full 3D
  vectors.

### 6. Add conditional three-source tables, plots, and transparent conclusions

When two independent experiments are available, the consolidated table must
include:

- Abaqus, Simcenter/contact, and Polytec frequencies;
- all three valid pairwise MAC values;
- damping values;
- coverage/confidence;
- final review state.

Add transparent diagnostic conclusions such as:

- both independent experiments agree and Abaqus differs;
- Abaqus agrees with Polytec but the contact experiment requires review;
- all three agree;
- the independent experiments disagree, so model calibration should pause.

For the current single Polytec experiment, do not generate three-source
conclusions. Report only the Abaqus–Polytec comparison and its Testlab
processing lineage.

Do not hide these rules inside one opaque score.

### 7. Polytec and lineage validation tests

Before completion:

- test the current real workflow: Polytec measurement processed in Testlab;
- verify that it remains one physical experiment in the data model and UI;
- test at least one real anonymized Polytec-exported UFF/UNV file;
- test 1D line-of-sight and, when available, 3D data;
- test a future independent contact/Simcenter dataset together with Polytec;
- test a Polytec grid different from the contact-experiment grid;
- test source-to-source geometry mapping and pairwise MAC;
- verify the pair view and the dedicated three-source view on tab 3;
- verify Excel/PDF/project persistence and cache invalidation;
- document exact Polytec/Testlab export settings and lineage fields.

### Stage 3 completion criteria

- existing Abaqus–experimental projects reproduce their results;
- the current dataset is labeled as a Polytec experiment processed in Simcenter
  Testlab, not as two independent experiments;
- no false Simcenter–Polytec comparison is created from one experiment;
- an optional second independent experiment can coexist with Polytec;
- all valid independent pairwise comparisons are calculated and visible;
- the same tab `3. Mode shapes` contains both detailed pair comparison and the
  dedicated three-source comparison view;
- source-pair and consolidated-mode switching updates all linked views through
  shared state;
- measurement directions, processing lineage, and confidence are explicit;
- no Polytec-specific logic is embedded in the MAC core.

---

## Stage 4 — UI/UX backlog from the 2026-08-03 user review

These refinements follow Stage 3 and must work with all valid source pairs and
both tab-3 view modes introduced there. They must not alter numerical values,
pairing, confidence, lineage, or review states.

### 1. Previous/next matched-pair navigation on Mode shapes

- add visible **Previous mode** and **Next mode** buttons;
- show position, for example `Pair 2 of 7` or `Consolidated mode 2 of 7`;
- use the visible table/consolidated-mode order;
- update table selection, title, pair figures, all three comparison cards, and
  manual-review selection through one shared current-mode state;
- disable the unavailable direction at the first/last mode;
- synchronize after reanalysis, restore, source-pair change, view-mode change,
  and manual edits;
- test first/middle/last and empty/single-mode cases.

### 2. Restore table headings and make the table responsive

- restore all captions after final runtime assembly, session restore, and
  reanalysis;
- include mode, frequency, signed/absolute error, MAC, coverage, geometry,
  measurement system, processing software, confidence, and decision columns;
- test the final assembled `Treeview.heading(..., "text")` values;
- distribute width responsively while preserving numeric minimum widths;
- retain horizontal and vertical scrollbars;
- keep rightmost columns accessible;
- verify minimum size, default `1500x900`, maximized window, and Windows display
  scaling at 100%, 125%, and 150%.

### 3. Combine AutoMAC/COMAC views into one responsive dashboard

- show the selected physical datasets' AutoMAC matrices and selected valid
  pair's COMAC in one dashboard;
- for an independent three-source project, clearly select which two AutoMAC
  matrices and which pair COMAC are displayed;
- use three panels on wide windows and `2 + 1` or vertical reflow on narrow
  windows;
- preserve aspect ratios and full-size/export actions;
- keep interpretation metrics visible in a compact area.

### 4. Add linked previous/next controls to the diagnostics dashboard

- use the same current source-pair/current consolidated-mode controller as the
  table, tab-3 pair view, tab-3 three-source view, and manual review;
- use pair selection for titles, highlighting, and follow-on views without
  changing global metric values;
- do not add another order-dependent monkey-patch layer solely for navigation.

### Stage 4 completion criteria

- no blank headings after startup, restore, or reanalysis;
- all columns remain accessible at supported sizes/scales;
- previous/next navigation is synchronized across tabs, valid source pairs,
  and both mode-shape views;
- the combined AutoMAC/COMAC dashboard remains readable and correctly labeled;
- Windows checks pass at 100%, 125%, and 150% display scaling.

---

## Stage 5 — architecture consolidation

Current debt:

- `main.py` assembles the app through many order-dependent `install_*()` layers;
- runtime contracts guard patch ownership but do not replace explicit design;
- several modules are facades over later replacements;
- project persistence, domain logic, GUI code, and report audit behavior remain
  mixed in large modules.

Target component layout:

- `domain/` — modal models, masks, coverage, lineage;
- `importers/` — Abaqus ODB, UNV/UFF, Polytec;
- `services/` — geometry alignment, MAC, assignment, FRF/CMIF, quality control;
- `reporting/` — Excel, PDF, figures;
- `persistence/` — projects, cache, migrations;
- `ui/` — controllers, views, navigation.

Mandatory removal order for the `install_*` chain, one vertical slice at a
time:

1. reporting;
2. universal reader;
3. comparison core;
4. project/manual review;
5. UI extensions;
6. cache/runtime hardening.

For each slice: keep a temporary facade at the old call site, move the real
implementation into the explicit component, confirm characterization tests
still pass, remove the corresponding `install_*`, and only then remove its
runtime contract.

Planned approach:

- fold one vertical slice at a time into explicit components, in the order
  above;
- introduce explicit experiment/source registry, lineage model, comparison
  service, and navigation controller rather than new hidden patches;
- inject services into the GUI through the constructor instead of having it
  import globally patched functions;
- keep runtime-contract tests until each corresponding patch chain is removed.

### Stage 5 completion criteria

`main.py` only constructs dependencies and starts the application; no
numerical function's behavior depends on import order.

## Stage 6 — real-data test matrix

**Priority:** P0 before relying on the tool for any new Abaqus version,
UNV/UFF variant, or measurement setup not already covered.
**Goal:** prove portability beyond the single file/version combination the
tool has been validated against so far.

Minimum matrix:

- **Abaqus:** at least two Abaqus versions; real eigenvalue modes; complex
  modes; multiple instances; shell and solid models; different mode ranges.
- **UNV/UFF:** dataset 55; dataset 2414; dataset 58 single-reference; dataset
  58 multi-reference; dataset 2420; incomplete grids; different pyuff
  variants.
- **Geometry:** full grid; half-panel; corner grid; mirrored axes; mm↔m
  scale; duplicate points; outliers.
- **Experiment:** Polytec line-of-sight; Polytec 3D; contact accelerometers;
  two independent experiments.

Required artifacts:

- anonymized fixtures or a fixture generator;
- expected-result JSON per fixture;
- a tolerance specification;
- a regression report;
- a list of the version/format combinations actually verified.

## Reproducibility, dependencies, and platform verification

This program is built for personal research use, not public distribution —
there is no packaging, installer, license, or changelog work on this list.

- Windows CI;
- `pyproject.toml`, `requirements.in`, and a lock/constraints file that pins
  compatible ranges, not just lower bounds; check the Python version at
  startup;
- application version in UI/projects/reports;
- cancellation of Abaqus extraction;
- CLI/batch processing;
- a separate `Validate inputs` action that runs before a full analysis;
- an `Export reproducibility package` action that bundles the full run
  fingerprint below with the inputs needed to reproduce it;
- a `Clear analysis cache` action;
- safe project-file migration across analysis-pipeline versions;
- a compatibility diagnostic for the installed Abaqus, Python, and pyuff
  versions against the supported matrix;
- compatibility matrix for Abaqus, Testlab, and Polytec exports;
- complete run fingerprint: application version, Git commit SHA, analysis
  pipeline version, Python/library/Abaqus versions, input file paths, SHA-256
  hashes, sizes and timestamps, MAC/frequency/coverage thresholds, actual
  masks, geometry transform, coherence status, source lineage, selected
  source pair, manual-review state, and cache-reuse status.

### Cache management

- include the application version and Git commit SHA in the cache key, and
  invalidate automatically after a numerical-pipeline change;
- keep raw-parsed-data, derived-mode, comparison-result, and rendered-figure
  caches separate;
- never unpickle a cache file written by an unknown or incompatible
  application version.

## Staged plan summary

- **Stage 1:** current behavior locked in — done.
- **Stage 2:** data-model additions plus seven scientific hardening items —
  test-first.
- **Stage 3:** explicit Polytec/Testlab lineage, current Abaqus–Polytec mode,
  optional independent three-source mode, expanded comparison windows, and the
  dedicated three-comparison view on tab 3.
- **Stage 4:** user-requested navigation and responsive-layout refinements.
- **Stage 5:** remove patch-chain architecture and split responsibilities
  along explicit `domain/importers/services/reporting/persistence/ui`
  boundaries.
- **Stage 6:** validate against a real-data matrix of Abaqus versions,
  UNV/UFF variants, geometries, and experiment types.
- **Reproducibility work:** proceed alongside the stages without bypassing
  numerical regression requirements.
