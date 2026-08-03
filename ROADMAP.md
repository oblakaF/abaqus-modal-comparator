# Roadmap

Working notes for hardening this program toward reproducible scientific use.
Items move between sections as they are reproduced, fixed, or ruled out — this
file is expected to change every stage, not stay static.

## Stage 1 status: done

- `ROADMAP.md` created.
- Direct unit tests added for the two modules with genuinely zero prior
  coverage: `amplitude_correlation.py` and `reporting_hardening.py`.
- Base Excel/PDF export behavior is characterized by tests that check sheet
  names, headers, summary values, and PDF page count rather than only file size.
- The AutoMAC/COMAC pair-mask intersection behavior has a regression test.
- The benign empty-slice COMAC warning is suppressed without changing the
  resulting `NaN` value for an unmeasured node.
- Silent project/session/plot-refresh exceptions were replaced by typed or
  logged handling.
- The full current suite reports 105 collected executions, all passing, with
  no warnings at the time Stage 1 was recorded.

Remaining baseline gaps:

- `requirements.txt` still pins only lower bounds (`>=`); there is no lock file.
- CI runs only on Ubuntu although the application is Windows/Tkinter/Abaqus
  oriented.
- Real ODB/UNV vendor-file regression fixtures are not part of the repository.

## Required implementation order

The following order is intentional. An implementation agent must complete and
validate the scientific hardening work first, then add Polytec as a third data
source, and only after that implement the UI changes requested from the current
Windows screenshots.

Do not begin a later stage by silently changing algorithms required by an
earlier stage. Each numerical change must ship with a reproducing test and a
before/after comparison on the current full 121-point single-reference
reference dataset.

---

## Stage 2 — scientific hardening from the code audit

These are the seven technical recommendations from the audit. They take
priority over the Polytec and UI work because they affect the meaning and
reliability of MAC, FRF confidence, geometry mapping, and coordinate handling.

### 1. Treat missing coherence as unavailable, not perfect

Current confirmed code behavior:

- when no dataset-58 coherence channels are found,
  `mean_coherence = np.ones_like(...)`;
- downstream a peak can therefore receive `High peak confidence` although no
  coherence was actually measured or exported.

Required change:

- introduce an explicit coherence state with at least:
  `computed`, `unavailable`, and `parse_error`;
- only `computed` coherence may contribute a positive confidence score;
- `unavailable` must be displayed and reported as unavailable, not as 1.0;
- `parse_error` must surface a warning and must not be silently converted to
  perfect confidence;
- preserve the FRF peak detector's ability to work when coherence is absent,
  but do not use fabricated coherence to rank or label peaks.

Required tests:

- complete coherence channels;
- zero coherence channels;
- partially missing coherence channels;
- malformed coherence data;
- report/UI labels and cache invalidation after the semantic change.

### 2. Implement a real multi-reference FRF/CMIF data path

Current risk to reproduce and then fix:

- FRF grouping includes `ref_node`/`ref_dir` in the group key, which can make
  every selected group single-reference;
- FRFs are effectively keyed by response DOF only in the close-mode path, so
  channels with different references can overwrite or remain separated;
- the present matrix is not guaranteed to be the required
  `response DOF × reference DOF` matrix at each frequency line.

Required change:

- represent each channel by
  `(response node, response direction, reference node, reference direction)`;
- group compatible channels by frequency axis and physical quantity without
  discarding independent references;
- construct the true complex FRF matrix for every frequency line;
- run conventional multi-reference CMIF/SVD on that matrix;
- retain the present conservative rule that single-reference local SVD is
  diagnostic only and cannot automatically prove an additional independent
  mode;
- expose reference count, matrix rank, singular-value ratios, rejected
  candidates, and confidence in diagnostics and reports.

Required tests:

- synthetic one-reference data;
- synthetic two-reference data with two independently recoverable modes;
- duplicate and missing reference channels;
- incompatible frequency axes;
- confirmation that a single-reference candidate remains diagnostic only.

### 3. Use a separate measured-DOF mask for each experimental mode

Current risk to reproduce and then fix:

- the core constructs a union of measured DOFs across the entire experimental
  modal set and then reuses that union for every experimental mode;
- a channel present in one mode can therefore be treated as measured for a
  different mode where it is absent.

Required change:

- carry a mode-specific measured-DOF mask through import, mapping, MAC matrix
  construction, pair construction, AutoMAC, COMAC, manual review, and reports;
- for a particular Abaqus/experimental pair, use only the intersection of that
  experimental mode's own measured mask, finite values, and valid geometry
  mapping;
- do not use the global union as the pair acceptance mask.

Required tests:

- different missing channels in different modes;
- different measured components by mode;
- no explicit masks with inference fallback;
- AutoMAC and COMAC consistency with pair-specific masks.

### 4. Add minimum common-DOF and spatial-coverage acceptance gates

Current confirmed weakness:

- MAC is considered calculable when `np.any(dof_mask)` is true;
- one common scalar DOF can therefore produce a formally high MAC with almost
  no spatial evidence.

Required change:

- define explicit, configurable gates for:
  - minimum common measured DOF count;
  - minimum unique measurement-point count;
  - minimum fraction of the experimental mode's measured DOFs;
  - minimum fraction of the experimental measurement points;
- pairs failing these gates must remain unmatched or explicitly
  `insufficient coverage`; they must not be labeled good/excellent solely from
  MAC and frequency;
- record counts, fractions, thresholds, and the acceptance decision in the UI,
  project file, Excel, PDF, and reproducibility metadata.

Threshold policy:

- introduce conservative defaults only after tests demonstrate behavior on the
  current reference dataset;
- do not alter the existing seven accepted reference pairs without an explicit
  documented reason and regression update.

### 5. Exclude geometry outliers and duplicate FE-node mappings from MAC

Current confirmed behavior:

- mapping distance and duplicate nearest-node mappings generate warnings;
- those points can still contribute to MAC;
- multiple experimental points mapped to one FE node can give that FE location
  repeated statistical weight.

Required change:

- create an explicit geometry-validity mask;
- exclude points outside the accepted mapping tolerance from numerical MAC;
- resolve duplicate FE-node mappings by a documented policy, preferably
  one-to-one assignment or controlled aggregation, rather than repeated
  weighting;
- retain complete diagnostics for rejected/outlier/duplicate points;
- provide MAC before filtering only as a diagnostic when useful, while the
  accepted pair decision must use filtered data.

Required tests:

- one distant outlier;
- several duplicated nearest-node mappings;
- a valid full 121-point grid whose numerical results remain unchanged;
- mapping warnings and exported audit tables.

### 6. Make geometry alignment robust for partial or off-center grids

Current risk to reproduce and then fix:

- Abaqus and experimental clouds are independently centered by their own
  bounding-box centers;
- a grid covering only one corner or one half of a specimen can therefore be
  shifted to an incorrect location while still finding a plausible axis/sign
  transformation.

Required change:

- preserve the current fast full-grid path for complete aligned scans;
- add at least one reliable partial-grid strategy, such as:
  - user-defined anchor-point correspondences;
  - a user-supplied rigid transform;
  - constrained ICP initialized from known axes/scale;
  - mapping by stable measurement-point identifiers when available;
- report transform source (`automatic full-grid`, `anchors`, `manual`, `ICP`),
  residuals, inlier fraction, and ambiguity warnings;
- never silently accept a reflected or poorly constrained solution.

Required tests:

- full centered grid;
- half-panel grid;
- corner-only grid;
- known translated and rotated subsets;
- ambiguous symmetric geometry requiring user confirmation.

### 7. Apply UNV dataset 2420/local coordinate-system transformations

Current confirmed limitation:

- dataset 2420 and non-default `def_cs`/`disp_cs` identifiers are detected;
- the importer currently warns but does not rotate modal vectors or measured
  directions into the global comparison system.

Required change:

- parse the supported dataset-2420 coordinate definitions;
- resolve each node/response DOF's local coordinate system;
- rotate modal vectors and measurement directions into one documented global
  system before geometry mapping and MAC;
- retain original and transformed directions for auditability;
- fail clearly when a referenced coordinate system is missing or unsupported
  rather than silently assuming global directions.

Required tests:

- global-only file;
- one rotated local system;
- multiple local systems;
- missing coordinate-system reference;
- equivalence between a globally exported file and the same data exported in a
  known local system.

### Stage 2 completion criteria

Stage 2 is complete only when:

- every item above has a reproducing test;
- confirmed defects are fixed without changing unrelated behavior;
- the current seven-pair, 121-point reference result is compared before and
  after every numerical change;
- reports record the actual masks, coverage, coherence state, geometry
  filtering, and coordinate transformations used;
- old analysis caches are invalidated through a pipeline-version bump.

---

## Stage 3 — add Polytec as a third modal-data source

Goal:

Support a three-source comparison workflow:

- Abaqus numerical modes;
- Simcenter/Testlab experimental modes or FRFs;
- Polytec laser-vibrometer experimental modes or FRFs.

The program must no longer assume exactly one generic `experimental` dataset.
It should represent named modal datasets and calculate pairwise comparisons
without duplicating the numerical algorithms.

### 1. Initial supported Polytec import path

First implementation phase:

- accept Polytec data exported as ASCII UFF/UNV;
- reuse and harden the existing universal-file importer;
- identify the source as `Polytec` in metadata, UI, caches, tables, and reports;
- prefer exports containing geometry plus curve-fitted modal datasets 55/2414;
- also permit dataset-58 FRFs under the same scientific limitations and
  confidence rules established in Stage 2.

Do not make native proprietary Polytec project-file reading a requirement for
the first phase. Add a native API/file-access adapter later only when a real
sample file and a stable supported Polytec access method are available.

### 2. Generalize the data model

Replace the fixed conceptual structure:

```text
Abaqus + one Experimental dataset
```

with named sources, for example:

```text
Numerical:
  Abaqus
Experimental:
  Simcenter
  Polytec
```

Requirements:

- each dataset has a stable source identifier, display name, source type,
  import method, file path/hash, geometry, modes, measured directions, and
  confidence metadata;
- comparison results are stored per ordered source pair;
- the existing Abaqus–Simcenter behavior remains backward compatible;
- project files can be migrated from the old two-source format.

### 3. Calculate all three pairwise comparisons

Required outputs:

- Abaqus ↔ Simcenter;
- Abaqus ↔ Polytec;
- Simcenter ↔ Polytec.

For every accepted common mode, provide:

- signed and absolute frequency differences;
- MAC on valid common measured DOFs;
- point/DOF coverage;
- geometry-transform quality;
- source and confidence status;
- damping comparison when both sources provide valid damping;
- unmatched and reordered modes.

The Simcenter ↔ Polytec comparison is essential because it distinguishes a
numerical-model disagreement from disagreement between two experimental
systems.

### 4. Respect Polytec measurement directions

Polytec data must not automatically be interpreted as global `U3`.

Requirements:

- support 1D line-of-sight measurements as a measured direction vector per
  point;
- support 3D Polytec vector measurements when exported;
- project the compared modal vectors onto the actual measured direction or
  transform complete 3D vectors into the common global frame;
- integrate this with the Stage-2 mode-specific DOF masks and local-coordinate
  transformations;
- report whether each comparison used line-of-sight scalar data or full 3D
  vectors.

### 5. Three-source tables, plots, and conclusions

Add a consolidated mode table containing, where available:

- Abaqus frequency;
- Simcenter frequency;
- Polytec frequency;
- Abaqus–Simcenter MAC;
- Abaqus–Polytec MAC;
- Simcenter–Polytec MAC;
- damping values;
- coverage/confidence and final review state.

Add diagnostic conclusions such as:

- both experiments agree and Abaqus differs;
- Abaqus agrees with Polytec but Simcenter requires review;
- all three agree;
- the two experiments disagree, so model calibration must not proceed until
  the measurement discrepancy is resolved.

These conclusions must remain transparent rules based on reported metrics, not
an opaque single score.

### 6. Polytec validation and regression tests

Before marking Polytec support complete:

- test at least one real anonymized Polytec-exported UFF/UNV file;
- test 1D line-of-sight data and, when available, 3D data;
- test a different Polytec point grid from the Simcenter grid;
- test source-to-source geometry mapping and pairwise MAC;
- verify Excel/PDF/project persistence and cache invalidation;
- document the exact Polytec export settings needed for a reliable import.

### Stage 3 completion criteria

- existing Abaqus–Simcenter projects still open and reproduce their results;
- a project can contain both Simcenter and Polytec simultaneously;
- all three pairwise comparisons are available;
- measurement directions and source confidence are explicit;
- no Polytec-specific parsing logic is embedded in the MAC core.

---

## Stage 4 — UI/UX backlog from the 2026-08-03 user review

These items were observed in the current Windows interface while reviewing a
seven-pair result (`Mean |frequency error| = 1.27%`, `Mean MAC = 0.930`, full
121-point geometry match). They are presentation/navigation changes and must
not alter numerical values, pairing, confidence, or manual-review decisions.

### 1. Previous/next matched-pair navigation on Mode shapes

- Add clearly visible **Previous mode** and **Next mode** buttons directly on
  the `Mode shapes` tab so the user does not have to return to the comparison
  table for every pair.
- Show the current position, for example
  `Pair 2 of 7: Abaqus 9 ↔ Experiment 5`.
- Navigation order must match the current visible accepted-pair order in the
  comparison table.
- Changing the pair must update the table selection, mode title, all three
  figures, and the active manual-review pair through one shared state.
- Disable `Previous` on the first pair and `Next` on the last pair.
- Reanalysis, project restore, manual pair changes, and the future selection of
  a source pair (Abaqus–Simcenter, Abaqus–Polytec, Simcenter–Polytec) must
  reset/synchronize this state without stale plots.
- Add tests for first/middle/last navigation and empty/single-pair results.

### 2. Restore comparison-table headings and make the table responsive

- The current table can display values while all column captions are blank.
  Restore headings after the complete final runtime UI assembly, session
  restore, and reanalysis.
- The final headings must include the existing mode, frequency, signed error,
  MAC, order-change, mapped-point, status, source, confidence, and
  manual-decision columns; later three-source columns must also remain visible.
- Add a final-runtime regression test that inspects
  `Treeview.heading(..., "text")`, not only an earlier widget constructor.
- Make the table respond to window width while preserving sensible minimum
  widths for numeric columns.
- Prevent rightmost source/confidence/manual-decision columns from being
  silently clipped.
- Provide a horizontal scrollbar for narrow windows.
- Verify minimum size, default `1500x900`, maximized window, and Windows display
  scaling at 100%, 125%, and 150%.

### 3. Combine all AutoMAC/COMAC views into one responsive tab

- Replace the nested `Abaqus AutoMAC`, `Experimental AutoMAC`, and `COMAC map`
  sub-tabs with one `AutoMAC & COMAC` dashboard showing all three figures at
  the same time.
- On a wide window, use a three-panel layout.
- On a narrower window, reflow to a readable `2 + 1` or vertical layout rather
  than shrinking figures to illegibility.
- Preserve aspect ratio and existing full-size/export actions.
- Keep the interpretation summary visible in a compact area:
  - Abaqus AutoMAC maximum off-diagonal;
  - experimental AutoMAC maximum off-diagonal;
  - mean and minimum COMAC.
- When Stage 3 introduces more than one experimental source, the dashboard must
  clearly identify which source and source pair each matrix/map belongs to.

### 4. Add linked previous/next controls to the combined diagnostics tab

- Add the same **Previous mode** and **Next mode** controls to the combined
  AutoMAC/COMAC dashboard.
- Synchronize them with the comparison table, `Mode shapes`, and manual review.
- AutoMAC and COMAC remain global diagnostics; the active pair controls select
  the linked pair for titles, highlighting, interpretation, or follow-on views
  rather than recomputing a different global matrix.
- Where practical, highlight the active pair's diagonal context and associated
  measured points without changing metric values.

### 5. Shared implementation requirement

- Introduce one explicit current-source-pair/current-mode-pair navigation
  controller used by the table, `Mode shapes`, `AutoMAC & COMAC`, and manual
  review.
- Do not add another order-dependent monkey-patch layer solely for navigation.
- Implement these UI changes as one reviewable slice with before/after Windows
  screenshots and tests against the final assembled runtime.

### Stage 4 completion criteria

- no blank headings after startup, restore, or reanalysis;
- all required columns remain accessible at supported window sizes;
- previous/next navigation is synchronized across tabs;
- all three AutoMAC/COMAC plots are visible in one responsive dashboard;
- Windows manual checks pass at 100%, 125%, and 150% display scaling.

---

## Architecture debt

- `main.py` assembles the app through roughly 20 order-dependent `install_*()`
  monkey-patch layers.
- `runtime_contracts.py` is a temporary guard against silent ownership changes,
  not a substitute for explicit architecture.
- Several early-named modules are thin facades over later replacement modules;
  editing the wrong layer can have no runtime effect.
- `project_review.py` mixes persistence, domain logic, GUI code, and report
  audit-trail behavior in one large module.

Planned approach:

- fold one vertical slice at a time into explicit components;
- do not add new scientific, Polytec, or navigation behavior as another hidden
  patch layer when an explicit service/controller can be introduced;
- retain runtime-contract tests until each corresponding patch chain is
  actually removed.

## Release and reproducibility gaps

- No Windows CI.
- No dependency lock file or bounded compatibility set.
- No application version in the GUI, project files, or reports.
- No changelog/release notes, license, `pyproject.toml`, or packaging.
- No offline installer for an isolated laboratory computer.
- No cancellation of a running Abaqus extraction.
- No headless/CLI batch mode for multiple specimens.
- No compatibility matrix for Abaqus and Testlab/Polytec export variants.
- Reports do not yet record complete input hashes, library versions, Abaqus
  version, thresholds, masks, coordinate transformations, and manual-review
  state as one reproducible run fingerprint.

## Staged plan summary

- **Stage 1 — lock in current behavior:** done.
- **Stage 2 — scientific hardening:** implement the seven audited items in the
  exact order above, test-first.
- **Stage 3 — Polytec:** generalize to named datasets and add the third source
  with all three pairwise comparisons.
- **Stage 4 — user-requested UI changes:** linked mode navigation, restored and
  responsive table headings, and one combined responsive AutoMAC/COMAC tab.
- **Stage 5 — architecture consolidation:** progressively remove the
  `install_*` patch chain and split mixed-responsibility modules.
- **Reproducibility work:** proceed alongside the stages, but never bypass the
  numerical regression requirements.

Do not change MAC/frequency admissibility thresholds or the current reference
dataset's automatic assignment without a dedicated regression test proving the
change is intentional.
