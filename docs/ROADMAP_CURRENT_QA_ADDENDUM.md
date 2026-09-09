# Current QA / Roadmap Addendum

**Branch:** `feat/ui-responsive-workflow-audit`

**Purpose:** temporary authoritative checkpoint for unresolved HUD/manual-QA items before PR. Stable conclusions should later be folded into `docs/ROADMAP_Stage_Inverse_Identification.md`; unresolved hypotheses must not be presented there as facts.

## 1. Current stable HUD state

Known implemented and already pushed on the HUD branch:

- responsive WIDE/MEDIUM/COMPACT policy
- table headings and horizontal/vertical scrolling
- unit-based coordinate conversion (`mm -> m = 0.001`, etc.) with custom-scale fallback
- Abaqus launcher discovery, Browse, Test Abaqus, alias/version deduplication
- Run/Stop state machine and owned-process cancellation
- Save / Save As / dirty state / recovery
- clipboard and context-menu behavior
- zero-pair result as `DIAGNOSTIC`, not application error
- analysis configuration frozen during `RUNNING/STOPPING`, restored afterward

Last reported source-code commit before the QA investigations:

- `222ae358e90bb5096998df3ca95cc3dbcd20cc55`
- full suite: `282 passed, 3 skipped`

The roadmap addendum itself was then added as docs-only commit `8faf39ffea146d50ff1ddde151bbb332c56e1ff8`.

Do not assume local diagnostic scratch work was committed unless verified from Git.

## 2. Manual QA facts already established

### SP15 bare CFRP

Real files:

- `C:\temp\12 sampls\results\SP15\test\CFRP_PLAIN_520_STAGEA_baseline.odb`
- `C:\temp\12 sampls\results\SP15\test\SP15_500by500_bigSP14_with_geometry.unv`

Observed on the HUD branch:

- full run completed in a few seconds
- zero accepted pairs remained a diagnostic result
- MAC/frequency, FRF, close-mode, and Manual Review diagnostics remained available
- Close Modes UI reported one excitation reference

Therefore the HUD branch is **not globally slow for every ODB extraction**.

### Sandwich case

Real files:

- Abaqus: `E:\sumin\Job-1.odb`
- Experiment: `E:\sumin\500by500_Glue420_Auxetic_full_scan_260624.unv`
- Historical project: `E:\sumin\modal_comparison_project2.amcp.json`

Manual QA established that this case could sit a long time at `1/6 Abaqus extraction...`; Stop worked correctly.

The numerical 8-pair vs 3-pair question and coordinate-scale provenance have now been resolved; see sections 3-4.

## 3. Resolved: 8 historical pairs vs 3 current pairs

Historical result:

- 8 matched pairs
- mean `|frequency error|` about 1.44%
- mean MAC about 0.895

Historical accepted MACs:

- A7 -> E1: 0.977
- A8 -> E2: 0.979
- A9 -> E3: 0.976
- A10 -> E4: 0.609
- A12 -> E5: 0.989
- A13 -> E6: 0.943
- A14 -> E7: 0.768
- A15 -> E8: 0.918

Current fixed-unit-conversion run:

- 3 matched pairs
- A7 -> E1: 0.977
- A8 -> E2: 0.932
- A15 -> E8: 0.761
- mean `|frequency error|` about 1.95%
- mean MAC about 0.890

Strict control established:

- `main` and the HUD feature branch are bit-for-bit identical for the same inputs/settings
- with fixed `coordinate_scale_override=0.001`, both produce the same 3 pairs
- with historical geometric `auto`, both reproduce the old 8-pair result exactly
- extraction, geometry candidates, MAC matrix, gates, and Hungarian assignment do not diverge between branches

Therefore **there is no scientific/main-vs-feature regression in MAC, geometry math, or assignment**.

The historical saved project independently confirms that the 8-pair run used `coordinate_scale="auto"`.

## 4. Resolved: physical coordinate-scale audit

### 4.1 FE geometry

`Job-1.odb` contains a ~500 mm sandwich model:

- whole assembly: X span ~502.132 mm, Y span ~499.750 mm, Z span 2.900 mm
- bottom/top faces: ~502.130 x 499.250 x 0.450 mm
- core instance name explicitly includes `P500x500x2mm core for abaqus`

This independently supports **Abaqus native model units = mm**.

### 4.2 Experimental UNV geometry and units

The UNV contains:

- geometry dataset 2411
- 121 nodes = 11 x 11 scan grid
- raw X span ~0.332937
- raw Y span ~0.328658
- raw Z constant at -1.0 (not real surface flatness/elevation)
- dataset 164 declares `METRIC_ABS_(SI)` with length conversion factor 1.0

Therefore the experimental coordinates are explicitly declared in **metres**.

Physical unit conversion is consequently exact:

`m -> mm = x1000`, equivalent to the application's `coordinate_scale = 0.001` convention.

### 4.3 Partial scan is the decisive point

With fixed physical conversion 0.001:

- experimental scan span becomes ~332.9 x 328.7 mm in FE space
- it maps to an interior ~333 x 329 mm region of the ~502 x 500 mm panel
- margins are roughly 80-90 mm from panel edges

This is physically consistent with a **partial scan**.

With historical geometric `auto` (~0.0006603457):

- the same 121-point scan is stretched to ~504 x 498 mm
- it is forced to span essentially the full panel edge-to-edge

`src/reviewed_core.py::_candidate_scales` was confirmed to be a pure bounding-box extent-ratio heuristic:

- it compares the entire FE assembly point-cloud extent with the experimental scan extent
- sorts spans by magnitude
- takes ratios and their median
- it has no knowledge of file units
- it has no knowledge of which region was actually scanned

For a partial scan this is **not a valid physical unit-identification method**.

### 4.4 Final scale decision

**SCALE-A: fixed 0.001 is physically justified.**

The old ~0.000660 value was a registration artifact that stretched a partial ~330 mm scan to fill a ~500 mm FE panel. The historical 8-pair result therefore should not be treated as the physically correct reference merely because its MACs are higher.

Both fixed and stretched mappings achieve similar ~1 mm nearest-node residuals because 121 scan points are being mapped onto a very dense ~977k-node FE mesh; residual magnitude alone cannot determine the physical scale.

### 4.5 Required coordinate-mapping UX cleanup before PR

The current HUD wording/implementation must make two concepts explicit and separate:

1. **Unit conversion (physical, deterministic)**
   - based on Abaqus model unit + experimental declared/selected unit
   - example: Abaqus mm, experiment m -> 0.001
   - this is the default/normal production path

2. **Geometric best-fit scale (heuristic, optional diagnostic)**
   - estimates arbitrary scale from point-cloud extents
   - must not be presented as a unit conversion
   - should warn when it differs substantially from the physical unit conversion
   - should warn that partial-coverage scans invalidate full-extent scale fitting

The current label `Automatic from units / alignment` conflates these concepts.

There is also a latent internal inconsistency: the UI display sync still stores literal `"auto"` in one state path while the currently active validator recomputes and passes the numeric unit-derived value. Reconcile this to one source of truth so a future patch-chain change cannot silently restore old geometric-auto semantics.

Recommended diagnostic result display: mapped scan-region bounding box vs full FE panel bounding box.

## 5. Remaining sandwich extraction performance task

`Job-1.odb` has only 16 usable modal frames; excessive requests such as `7 -> 30` are clipped to the available range rather than fabricating missing modes.

For this specimen:

- useful benchmark range: `7 -> 15` or `7 -> 16`
- mode 16 does not pair in the historical comparison

Preliminary profiling indicates the dominant cost is the very large full-field export/read path:

- ~977,270 FE nodes
- ~9-10 requested elastic modes
- roughly ~150 MB CSV per mode

A prior controlled parse/hash pass took ~99 s in-process, while real Abaqus CSV export consumed much longer wall-clock time. This is the likely performance target, not geometry/MAC/Hungarian math.

Required next performance work:

- measure main vs feature extraction time using the same real files and effective range
- prove whether HUD process-management adds any material overhead
- preserve correct clipping to available modes
- surface the range notice clearly (`requested 7-30; available through 16; using 7-16`)
- do not leave the user staring at a generic apparently frozen `1/6 Abaqus extraction...`
- add meaningful extraction/export/read progress if technically feasible
- investigate reducing unnecessary repeated full-field CSV I/O without changing scientific results

Any `.sandwich_postfix_benchmark` / `_sandwich_postfix_benchmark.py` artifact remains diagnostic scratch unless explicitly promoted with justification.

## 6. Remaining HUD state/UI blockers

### 6.1 Resize responsiveness

Manual QA found:

- the app is most comfortable only nearly maximized/full-screen
- during continuous resize, Windows frame motion is smooth but internal widgets/plots catch up in large steps, subjectively ~2 FPS

Required targets before PR:

- usable at 1920x1080, 1600x900, 1366x768, 1280x720, and ~1024x700
- smooth continuous resize
- no scientific recomputation on resize
- no repeated heavy Matplotlib rebuild per pixel
- cheap Tk geometry updates during active resize
- one deferred expensive redraw after resize settles (~150-250 ms)
- Treeview contents are not rebuilt during ordinary resize
- maximize/restore stable

Add user UI-density/scale preference under Settings, suggested values:

- 80%
- 90%
- 100% default
- 110%
- 125%

UI scale affects presentation only, never scientific coordinates, FE/EXP unit conversion, MAC, or results.

### 6.2 Completed zero-pair Mode Shapes state

Manual QA previously showed a completed SP15 diagnostic run where the Mode Shapes panels still displayed:

`Analysis is running; previous results are no longer active.`

This must be verified fixed before PR. Correct completed zero-pair text should indicate that there are no accepted pairs and direct the user to MAC/frequency/Manual Review diagnostics. STOPPED/ERROR/RUNNING/SUCCESS/DIAGNOSTIC must remain distinct, and the progress indicator must not look active after completion.

## 7. Final HUD release gate

Do not create the HUD PR until all of the following pass manually:

1. sandwich unit conversion uses physical 0.001 by default
2. geometric best-fit is clearly separated/labelled if retained
3. sandwich extraction no longer looks indefinitely stuck and range clipping is surfaced
4. resize is smooth and usable below fullscreen
5. configuration remains locked during RUNNING/STOPPING
6. Abaqus launcher appears deduplicated
7. SP15 zero-pair completion shows correct Mode Shapes state
8. Stop still terminates owned Abaqus work cleanly
9. full pytest and native Tk suites pass

No scientific thresholds may be weakened to make real data pass.

## 8. Do not broaden the HUD branch

Until the release gate is satisfied:

- no PR
- no merge
- no SCI-S0 implementation
- no pyFBS
- no Stage B implementation
- no Material-ID GUI
- no broad controller/monkey-patch architecture refactor

Only concrete QA, performance, state, coordinate-mapping, and responsiveness fixes needed for release readiness belong in this branch.

## 9. Post-HUD scientific sequence

After HUD PR/CI/manual QA passes and the branch is merged:

1. SCI-S0: scalar-MAC triage on SP15
2. determine actual dataset-58 reference count from metadata
3. measured-DOF FE Gram/AutoMAC and pre-pair close-mode groups
4. FE-subspace containment / partial-subspace evidence
5. spatial-resolvability / suspension / real-Z availability diagnostics
6. decide whether proper FRF modal identification is on the critical path
7. canonical FRF layer
8. synthetic EMA truth + SDyPy oracle
9. pyFBS pLSCF/LSFD adapter if required
10. real Stage-A material identification
11. later Material ID GUI showing primary `D11,D12,D66`, derived apparent flexural properties, identifiability, uncertainty, fit diagnostics, and exports
12. only after defensible Stage A: global/hierarchical Stage B sandwich identification

## 10. Sandwich campaign context to retain

Physical campaign currently understood as 15 specimens total:

- 4 bare CFRP plates
- 11 sandwich panels

Core families:

- PLA auxetic
- PLA honeycomb
- TPU auxetic
- TPU honeycomb

Sandwich faces include old/new plain T300 CFRP and one twill configuration, with face thicknesses roughly 0.235-0.45 mm. Sizes are roughly 300x300 and 500x500 mm.

Primary measurements include individual face masses, core mass, adhesive masses, mass before adhesive, final mass, face/core/total thicknesses, and panel dimensions.

Important FE fact: auxetic and honeycomb cores are represented with their **explicit cellular wall geometry**, not as a solid equivalent core plate. This makes a future shared printed-material law, especially for PLA, scientifically attractive subject to global identifiability analysis. TPU remains a later likely viscoelastic extension.

Stable specimen relationships already identified include SP-01/SP-13, SP-02/SP-10, SP-08/SP-09, SP-04..SP-07, and SP-03 as the twill-face PLA auxetic control.

Do not start Stage B while modal-data quality and Stage-A remain unresolved.
