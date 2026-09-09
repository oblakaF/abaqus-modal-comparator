# Current QA / Roadmap Addendum

**Branch:** `feat/ui-responsive-workflow-audit`

**Purpose:** temporary authoritative checkpoint for unresolved HUD/manual-QA items before PR. Stable conclusions should later be folded into `docs/ROADMAP_Stage_Inverse_Identification.md`; unresolved hypotheses must not be presented there as facts.

## 1. Current stable HUD state

Known implemented and previously pushed on the HUD branch:

- responsive WIDE/MEDIUM/COMPACT policy
- table headings and horizontal/vertical scrolling
- unit-based coordinate mapping (`mm -> m = 0.001`, etc.) with custom-scale fallback
- Abaqus launcher discovery, Browse, Test Abaqus, and alias/version deduplication
- Run/Stop state machine and owned-process cancellation
- Save / Save As / dirty state / recovery
- clipboard and context-menu behavior
- zero-pair result as `DIAGNOSTIC`, not application error
- analysis configuration frozen during `RUNNING/STOPPING`, restored afterward

Last explicitly reported committed state before the interrupted performance investigation:

- commit `222ae358e90bb5096998df3ca95cc3dbcd20cc55`
- full suite: `282 passed, 3 skipped`

Do not assume later local scratch work was committed unless verified from Git.

## 2. Manual QA facts already established

### SP15 bare CFRP

Real files:

- `C:\temp\12 sampls\results\SP15\test\CFRP_PLAIN_520_STAGEA_baseline.odb`
- `C:\temp\12 sampls\results\SP15\test\SP15_500by500_bigSP14_with_geometry.unv`

Observed on the HUD branch:

- full run completed in a few seconds
- zero accepted pairs remained a diagnostic result
- MAC/frequency, FRF, close-mode, and Manual Review diagnostics remained available
- Close Modes UI reported one excitation reference for this dataset

Therefore the HUD branch is **not globally slow for every ODB extraction**.

### Sandwich case

Real files:

- Abaqus: `E:\sumin\Job-1.odb`
- Experiment: `E:\sumin\500by500_Glue420_Auxetic_full_scan_260624.unv`

Observed:

- this exact comparison historically completed quickly
- current HUD run stayed a long time at `1/6 Abaqus extraction...`
- user pressed Stop
- cancellation worked correctly and wrote `last_cancellation.log`
- partial Codex investigation stated that a fresh extraction was genuinely running, only one owned Abaqus process was launched, and no retry loop / duplicate extraction had yet been observed
- partial investigation also stated that the slowdown appeared dominated by exporting/reading large per-mode CSV data from the much larger sandwich ODB, not by waiting for nonexistent modes; this remains to be completed and benchmarked
- partial investigation suggested the actual useful mode range is approximately `7-16`; this must be verified and reported from the real ODB before being treated as final

## 3. Critical unresolved numerical regression question

Historical result for the same sandwich comparison showed approximately:

- 8 matched pairs
- mean `|frequency error|` about 1.44%
- mean MAC about 0.895
- geometry match 100%

Historical accepted pairs:

- A7 -> E1, MAC 0.977
- A8 -> E2, MAC 0.979
- A9 -> E3, MAC 0.976
- A10 -> E4, MAC 0.609
- A12 -> E5, MAC 0.989
- A13 -> E6, MAC 0.943
- A14 -> E7, MAC 0.768
- A15 -> E8, MAC 0.918

Current feature screenshots showed only three accepted pairs:

- A7 -> E1, MAC 0.977
- A8 -> E2, MAC 0.932
- A15 -> E8, MAC 0.761

All Abaqus modes remained visible in Manual Review, so this is not simply a display truncation.

This is a **release blocker until explained**.

The required control is:

1. run the exact same ODB/UNV/settings on `main`
2. run the exact same ODB/UNV/settings on the HUD feature branch
3. locate the first numerical divergence before pairing

Compare, in order:

- extracted FE frequencies
- FE coordinates
- FE mode-vector sizes/norms/hashes
- experimental frequencies
- experimental vectors sizes/norms/hashes
- coordinate scale
- chosen transform
- mapped point->FE-node indices
- measured-DOF masks
- raw MAC matrix
- frequency-gate mask
- MAC-gate mask
- Hungarian assignment

Do not weaken gates and do not hard-code a historical mapping to force eight pairs.

If `main` with the same current inputs also produces three pairs, the old eight-pair result came from different inputs/cache/transform/configuration and is not a HUD regression.

If `main` gives eight and feature gives three, fix the first proven feature-branch regression only.

## 4. Sandwich extraction performance task

Benchmark `main` vs feature using the exact same real sandwich files and the actual available elastic mode range.

Report:

- frequency step name
- total frames / actual modal numbers
- highest usable mode
- correct effective comparison range
- Abaqus extraction time on `main`
- Abaqus extraction time on feature before fix
- total comparison time
- effect of an intentionally excessive `7 -> 30` request

Robust UX for an upper mode request beyond available data:

- never fabricate missing modes
- never appear to hang simply because the upper request is too large
- either clip to available modes and show a clear notice, or fail early with a clear validation message

If the slowdown is simply a large-ODB extraction cost, improve progress reporting separately from scientific behavior (e.g. show extraction/export/read progress rather than a visually frozen generic `1/6`).

Any temporary benchmark script such as `__sandwich_postfix_benchmark.py` is diagnostic scratch and must not be committed as production code without an explicit reason.

## 5. Remaining HUD responsiveness blocker

Manual QA still found:

- the app is most comfortable only when nearly maximized/full-screen
- during continuous window resizing, the outer Windows frame moves smoothly but internal widgets/plots visibly catch up in large steps, subjectively around ~2 FPS
- this indicates expensive resize/reflow/redraw work on the Tk `<Configure>` path

Before HUD PR, diagnose and fix resize performance without changing scientific code.

Required targets:

- usable at 1920x1080, 1600x900, 1366x768, 1280x720, and about 1024x700
- smooth continuous resize
- no scientific recomputation on resize
- no repeated heavy Matplotlib rebuild per pixel
- cheap geometry updates during active resize
- one deferred expensive redraw after resize settles (~150-250 ms debounce)
- Treeview contents are not rebuilt on ordinary resize
- maximize/restore remains stable

Add an independent user UI-density/scale preference under Settings, suggested values:

- 80%
- 90%
- 100% (default)
- 110%
- 125%

UI scale affects presentation only (fonts/padding/control density), not scientific coordinates, unit scale, MAC, FE geometry, or numerical results.

## 6. Do not broaden the HUD branch

Until the blockers above are resolved:

- no PR
- no merge
- no SCI-S0 implementation
- no pyFBS
- no Stage B
- no Material-ID GUI
- no broad monkey-patch/controller refactor

The HUD branch should only receive concrete regression/performance/responsiveness fixes needed for release readiness.

## 7. Post-HUD scientific sequence

After HUD manual QA passes, PR is merged, and `main` is updated:

1. SCI-S0: scalar-MAC triage on SP15
2. determine actual dataset-58 reference count from metadata
3. measured-DOF FE Gram/AutoMAC and pre-pair close-mode groups
4. FE-subspace containment / partial-subspace evidence
5. spatial-resolvability / suspension / real-Z availability diagnostics
6. only then decide whether proper FRF modal identification is on the critical path
7. canonical FRF layer
8. synthetic EMA truth + SDyPy oracle
9. pyFBS pLSCF/LSFD adapter if required
10. real Stage-A material identification
11. later Material ID GUI
12. only after defensible Stage A: global/hierarchical Stage B sandwich identification

Scientific gates must not be weakened to make real data pass.

## 8. Sandwich campaign context to retain

Physical campaign currently understood as 15 specimens total:

- 4 bare CFRP plates (very thin; potentially difficult free-free experimental mode shapes)
- 11 sandwich panels

Core families:

- PLA auxetic
- PLA honeycomb
- TPU auxetic
- TPU honeycomb

Sandwich faces include old/new plain T300 CFRP and one twill configuration, with face thicknesses roughly 0.235-0.45 mm. Sizes are roughly 300x300 and 500x500 mm.

For sandwich specimens the project has unusually strong primary measurements: individual face masses, core mass, adhesive masses, mass before adhesive, final mass, face/core/total thicknesses, and panel dimensions.

Important FE fact: auxetic and honeycomb cores are represented with their **explicit cellular wall geometry**, not as a solid equivalent core plate. This makes a future shared printed-material law (especially for PLA) scientifically attractive, subject to global identifiability analysis. TPU should remain a later, likely viscoelastic extension.

Stable specimen relationships already identified include SP-01/SP-13 (related PLA auxetic construction), SP-02/SP-10 (related PLA honeycomb construction), SP-08/SP-09 (thin-face PLA auxetic/honeycomb pair), SP-04..SP-07 (TPU family), and SP-03 (twill-face PLA auxetic control).

Do not start Stage B while the modal-data quality and Stage-A path remain unresolved.
