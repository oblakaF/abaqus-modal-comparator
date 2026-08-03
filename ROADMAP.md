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

## Required implementation order

The order below is mandatory for an implementation agent:

1. complete scientific hardening;
2. add Polytec and expand the comparison workflow/windows for three sources;
3. implement the current user-requested UI refinements;
4. consolidate the architecture and reproducibility tooling.

Every numerical change must include a reproducing test and a before/after
comparison on the current full 121-point, seven-pair, single-reference result.
Do not silently change MAC/frequency thresholds or the accepted reference
assignment.

---

## Stage 2 — scientific hardening from the code audit

These seven items affect the meaning and reliability of MAC, FRF confidence,
geometry mapping, and coordinate handling. They must be completed before
Polytec support.

### 1. Treat missing coherence as unavailable, not perfect

Current confirmed behavior:

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

### 2. Implement a real multi-reference FRF/CMIF path

Current risk:

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

### 3. Use a separate measured-DOF mask for every experimental mode

Current risk:

- a union of measured DOFs can be reused for all experimental modes;
- a channel present in one mode can be treated as measured in another mode.

Required change:

- carry mode-specific masks through import, geometry mapping, MAC, pair
  construction, AutoMAC, COMAC, manual review, persistence, and reports;
- calculate each pair from that mode's own valid finite measured DOFs;
- do not use a global union as the acceptance mask.

Required tests:

- different missing channels/components by mode;
- inferred-mask fallback;
- AutoMAC and COMAC consistency.

### 4. Add minimum common-DOF and spatial-coverage gates

Current weakness:

- `np.any(dof_mask)` allows MAC to be calculated from one common scalar DOF.

Required change:

- configurable minimum common DOF count;
- minimum unique point count;
- minimum measured-DOF coverage fraction;
- minimum measurement-point coverage fraction;
- pairs below the limits must be unmatched or marked `insufficient coverage`;
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
- resolve duplicate mappings by one-to-one assignment or documented
  aggregation;
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
- report transform source, residuals, inlier fraction, reflections, and
  ambiguity;
- never silently accept a poorly constrained solution.

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
- the seven-pair reference result is compared before and after every change;
- reports record actual masks, coverage, coherence state, geometry filtering,
  and coordinate transformations;
- semantic changes bump the analysis-pipeline cache version.

---

## Stage 3 — add Polytec as a third modal-data source

Goal:

Support one project containing:

- Abaqus numerical modes;
- Simcenter/Testlab experimental modes or FRFs;
- Polytec laser-vibrometer modes or FRFs.

This stage includes both the data/algorithm work and the minimum comparison UI
needed to use all three sources. The Polytec comparison windows must not be
postponed to Stage 4.

### 1. Initial Polytec import path

First implementation phase:

- accept Polytec data exported as ASCII UFF/UNV;
- reuse the hardened universal-file importer;
- identify `Polytec` explicitly in metadata, caches, UI, tables, projects, and
  reports;
- prefer geometry plus curve-fitted modal datasets 55/2414;
- permit dataset-58 FRFs under the Stage-2 confidence and scientific limits.

Native proprietary Polytec-file/API support is deferred until a real sample and
stable supported access method are available.

### 2. Generalize the data model

Replace the fixed conceptual structure:

```text
Abaqus + one Experimental dataset
```

with named modal sources:

```text
Numerical:
  Abaqus
Experimental:
  Simcenter
  Polytec
```

Each dataset must have a stable source ID, display name, source type, import
method, file path/hash, geometry, modes, measured directions, and confidence
metadata. Store results per source pair and migrate existing two-source project
files without changing their results.

### 3. Calculate all three pairwise comparisons

Required pairs:

- Abaqus ↔ Simcenter;
- Abaqus ↔ Polytec;
- Simcenter ↔ Polytec.

For every pair provide:

- signed and absolute frequency differences;
- MAC on valid common measured directions/DOFs;
- common-point and DOF coverage;
- geometry-transform quality;
- source/confidence status;
- damping comparison where available;
- unmatched and reordered modes.

The Simcenter–Polytec pair is essential for separating numerical-model error
from disagreement between the two experimental systems.

### 4. Expand the comparison windows for Polytec

This is a required part of Stage 3.

#### Source-pair selector

Add a persistent selector available from all comparison/diagnostic tabs:

- `Abaqus ↔ Simcenter`;
- `Abaqus ↔ Polytec`;
- `Simcenter ↔ Polytec`;
- optional `Three-source summary`.

The selected source pair must be one shared state used by the table, mode-shape
view, frequency/MAC plots, FRF/quality diagnostics, AutoMAC/COMAC, manual
review, and exports. Do not maintain separate unsynchronized source selections
in each tab.

#### Comparison table window

The table must switch between the selected pair and show source-specific
columns, including:

- left/right source and mode numbers;
- left/right frequencies;
- signed and absolute error;
- MAC;
- common point/DOF coverage;
- geometry quality;
- source type and confidence;
- damping values where available;
- automatic/manual decision.

Add a separate three-source summary table with one row per consolidated mode and
columns for all three frequencies and all three pairwise MAC values.

#### Mode-shape comparison window

For each selected source pair show:

- left source shape;
- right source shape;
- overlay/correlation view;
- explicit source names in titles;
- actual measured direction (Polytec line-of-sight or 3D);
- confidence and coverage information.

For `Simcenter ↔ Polytec`, both sides are experimental and the UI must not label
one side as Abaqus. For the three-source summary, provide either a three-panel
shape view or a clear source-pair switch without losing the consolidated mode
selection.

#### Frequency and MAC windows

Every frequency-regression, MAC matrix, amplitude-correlation, and accepted-pair
plot must identify the selected source pair. The user must be able to compare
all three source pairs without reloading the files or rerunning extraction.

#### AutoMAC/COMAC windows

AutoMAC belongs to an individual source and COMAC/cross-correlation belongs to a
source pair. Therefore the UI must provide:

- Abaqus AutoMAC;
- Simcenter AutoMAC;
- Polytec AutoMAC;
- Abaqus–Simcenter COMAC;
- Abaqus–Polytec COMAC;
- Simcenter–Polytec COMAC, when common spatial coverage is sufficient.

The selected source/pair and valid common grid must be explicit in every title,
legend, interpretation block, and export file name.

#### FRF and quality windows

Show Simcenter and Polytec FRF/coherence/peak diagnostics separately, plus
pair-specific warnings. Do not merge two experimental datasets into one
unlabeled FRF plot.

#### Manual-review window

Manual decisions must be stored per source pair and mode pair. Changing an
Abaqus–Simcenter decision must not overwrite an Abaqus–Polytec or
Simcenter–Polytec decision.

#### Reports and project persistence

Excel, PDF, project files, cached figures, and exported PNG/data files must
record the selected source pair and include all available pairwise results.
File names must not collide between source pairs.

Required UI regression tests:

- switching among all three source pairs updates every linked tab;
- no stale figures or table rows remain from the previous pair;
- source labels are correct for experimental–experimental comparison;
- decisions and selected modes remain independent per source pair;
- reopening a project restores all sources and comparison-window state.

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

### 6. Add three-source tables, plots, and transparent conclusions

The consolidated table must include, where available:

- Abaqus, Simcenter, and Polytec frequencies;
- all three pairwise MAC values;
- damping values;
- coverage/confidence;
- final review state.

Add transparent diagnostic conclusions such as:

- both experiments agree and Abaqus differs;
- Abaqus agrees with Polytec but Simcenter requires review;
- all three agree;
- the experiments disagree, so model calibration should pause.

Do not hide these rules inside one opaque score.

### 7. Polytec validation and regression tests

Before completion:

- test at least one real anonymized Polytec-exported UFF/UNV file;
- test 1D line-of-sight and, when available, 3D data;
- test a Polytec grid different from the Simcenter grid;
- test source-to-source geometry mapping and pairwise MAC;
- verify all expanded comparison windows;
- verify Excel/PDF/project persistence and cache invalidation;
- document exact Polytec export settings.

### Stage 3 completion criteria

- existing Abaqus–Simcenter projects reproduce their results;
- Simcenter and Polytec can coexist in one project;
- all three pairwise comparisons are calculated and visible in the expanded
  comparison windows;
- source-pair switching updates all tabs through one shared state;
- measurement directions and confidence are explicit;
- no Polytec-specific logic is embedded in the MAC core.

---

## Stage 4 — UI/UX backlog from the 2026-08-03 user review

These refinements follow Stage 3 and must work with all source pairs introduced
there. They must not alter numerical values, pairing, confidence, or review
states.

### 1. Previous/next matched-pair navigation on Mode shapes

- add visible **Previous mode** and **Next mode** buttons;
- show position, for example `Pair 2 of 7`;
- use the visible table order;
- update table selection, title, figures, and manual-review selection through
  one shared current-pair state;
- disable the unavailable direction at the first/last pair;
- synchronize after reanalysis, restore, source-pair change, and manual edits;
- test first/middle/last and empty/single-pair cases.

### 2. Restore table headings and make the table responsive

- restore all captions after final runtime assembly, session restore, and
  reanalysis;
- include mode, frequency, signed/absolute error, MAC, coverage, geometry,
  source, confidence, and decision columns;
- test the final assembled `Treeview.heading(..., "text")` values;
- distribute width responsively while preserving numeric minimum widths;
- retain horizontal and vertical scrollbars;
- keep rightmost columns accessible;
- verify minimum size, default `1500x900`, maximized window, and Windows display
  scaling at 100%, 125%, and 150%.

### 3. Combine AutoMAC/COMAC views into one responsive dashboard

- show the selected sources' AutoMAC matrices and selected pair's COMAC in one
  dashboard;
- for a three-source project, clearly select which two source AutoMAC matrices
  and which pair COMAC are displayed;
- use three panels on wide windows and `2 + 1` or vertical reflow on narrow
  windows;
- preserve aspect ratios and full-size/export actions;
- keep interpretation metrics visible in a compact area.

### 4. Add linked previous/next controls to the diagnostics dashboard

- use the same current source-pair/current mode-pair controller as the table,
  mode shapes, and manual review;
- use pair selection for titles, highlighting, and follow-on views without
  changing global metric values;
- do not add another order-dependent monkey-patch layer solely for navigation.

### Stage 4 completion criteria

- no blank headings after startup, restore, or reanalysis;
- all columns remain accessible at supported sizes/scales;
- previous/next navigation is synchronized across tabs and source pairs;
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

Planned approach:

- fold one vertical slice at a time into explicit components;
- introduce explicit source registry, comparison service, and navigation
  controller rather than new hidden patches;
- keep runtime-contract tests until each corresponding patch chain is removed.

## Release and reproducibility work

- Windows CI;
- dependency lock or bounded compatibility set;
- application version in UI/projects/reports;
- changelog, license, `pyproject.toml`, and packaging;
- offline installer;
- cancellation of Abaqus extraction;
- CLI/batch processing;
- compatibility matrix for Abaqus, Testlab, and Polytec exports;
- complete run fingerprint: file hashes, versions, thresholds, masks,
  transformations, source pair, and manual-review state.

## Staged plan summary

- **Stage 1:** current behavior locked in — done.
- **Stage 2:** seven scientific hardening items — test-first.
- **Stage 3:** Polytec, named sources, all three pairwise calculations, and
  fully expanded comparison windows.
- **Stage 4:** user-requested navigation and responsive-layout refinements.
- **Stage 5:** remove patch-chain architecture and split responsibilities.
- **Reproducibility work:** proceed alongside the stages without bypassing
  numerical regression requirements.
