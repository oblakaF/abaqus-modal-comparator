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

### 4.0 Coordinate-provenance correction (2026-09-09; supersedes 4.2–4.5)

The operator has since confirmed that no specimen dimensions, reference length,
distance calibration, or CAD geometry were supplied when the 11x11 Polytec
camera-view grid was drawn. The scan covered the full specimen. Consequently,
dataset 164's SI declaration does **not** establish metric calibration of these
camera-grid coordinates. The statements below that interpret the raw spans as
metres, call this a partial scan, or conclude that `coordinate_scale=0.001` is
physically correct are obsolete for this acquisition and retained only as audit
history. `docs/COORDINATE_CALIBRATION_DECISION.md` is the authoritative decision
record.

Production now separates calibrated physical geometry, uncalibrated camera-grid
geometry, manual overrides, and explicitly warned legacy extent fitting. A full
camera-grid scan requires recorded physical width/height; a partial scan requires
physical scan-window width/height and is never stretched from specimen dimensions.

No independent measurement record for the exact
`Job-1.odb` / `500by500_Glue420_Auxetic_full_scan_260624.unv` specimen was found in
the available local records. The validation therefore uses nominal 500 x 500 mm
as a clearly labelled fallback. Raw spans 0.3329370319843292 x
0.3286576420068741 produce independent comparator-convention factors
`scale_x=0.0006658740639686585` and
`scale_y=0.0006573152840137482`.

The real format-v2 extraction diagnostic (modes 7–16, unchanged gates) gave:

- fixed `0.001`: 3 accepted pairs;
- retained legacy extent fit `0.000660345670989`: 9 accepted pairs in the current
  7–16 diagnostic (the frozen historical project records 8 under its earlier
  run context);
- explicit nominal 500 x 500 camera calibration: 9 accepted pairs, independently
  reproducing the full-panel geometric behavior without optimizing scale for MAC.

The explicit camera result used planar axis permutation `[1, 0]`, determinant
`+1`, 100% tolerance match, normalized RMS `0.00145978`, raw-coordinate RMS/max
residual `0.000682926 / 0.00136569`, and Abaqus-unit RMS/max residual
`1.03267 / 2.06677 mm`. The matched FE-node bounding box is
`X 5.45904..505.56833`, `Y -2.88000..496.42496`, `Z 0.45..2.45 mm`
(spans `500.10929 x 499.30496 x 2.00000 mm`). The complete diagnostic,
including all MAC matrices, is reproducible with
`tools/validate_coordinate_calibration.py`. No affine/projective fit was
introduced.

The requested real SP15 rerun used
`CFRP_PLAIN_520_STAGEA_baseline.odb` and
`SP15_500by500_bigSP14_with_geometry.unv`: fresh extraction format 2, modes
1–20, explicit nominal 500 x 500 calibration, X/Y factors `0.001 / 0.001`,
100% geometry match, normalized RMS `1.95e-17`, determinant `+1`, no planar
axis swap, and 0 accepted pairs. This is a real SP15 diagnostic result, not a
proxy, and does not promote zero pairs to a scientific pass.

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

Confirmed dominant cost is the very large full-field export/read path:

- ~977,270 FE nodes
- 10 usable elastic modes present in the ODB (range clips to 1-16; requests above 16 are clipped, not fabricated)
- old per-mode CSV ~150 MB (geometry embedded redundantly in every mode file)

### 5.1 VERIFIED performance measurements (this session)

Real files: `.sandwich_postfix_benchmark\Job-1.odb` (977,270-node sandwich model), same UNV as section 2, range 7->16, `coordinate_scale=0.001`.

**Before optimization** (`format_version=1`, geometry duplicated per mode CSV):

- cold extraction wall-clock: 285 s (12:35:55 -> 12:40:40, ~26-28 s/mode)
- total CSV bytes written: 1,503,342,861 (10 files, ~150.3 MB each, no shared geometry file)

**After optimization** (`format_version=2`, geometry.csv written once, per-mode CSVs carry displacement values only):

- cold extraction wall-clock: 196.13 s (measured directly via `run_abaqus_extraction`)
  - geometry exported once: 10.8 s (977,270 nodes)
  - 10 modes at ~17-18 s each
- in-process parse (`load_extracted_odb`) of the extracted CSVs: 39.41 s
- total CSV bytes written: 1,070,706,233 (geometry.csv 87,429,012 bytes + 10 per-mode files ~98.3 MB each)
- byte reduction vs before: 432,636,628 bytes (28.8%)
- wall-clock speedup: 285 s -> 196.13 s (1.45x on extraction alone)

**Main vs feature branch control** (`control_pipeline.py`, same old-format manifest, `coordinate_scale=0.001`, both against `main`@`cc31b41` in a worktree and this feature branch): `odb_load` 98.78 s (main) vs 99.07 s (feature) — statistically indistinguishable; HUD process-management/progress-callback wiring adds no material overhead.

**Scientific before/after equality** (`format_version=1` extraction vs `format_version=2` extraction of the same ODB/UNV, same code, `coordinate_scale=0.001`): `abaqus_frequencies`, `abaqus_vector_stats` (coord/vector hashes), `experimental_frequencies`/`experimental_vector_stats`, `geometry` transform, `mac_matrix`, `frequency_error_matrix`, `pairs` (3 accepted: A7->E1 MAC 0.977, A8->E2 MAC 0.932, A15->E8 MAC 0.761), and `warnings` were byte-for-byte identical between old- and new-format extraction outputs. **PASS, no scientific regression.**

**SP15 small-case regression** (`CFRP_PLAIN_520_STAGEA_baseline.odb`, range 1-20): extraction 1.82 s, full pipeline 4.43 s total, `format_version=2`, 0 accepted pairs — unchanged from the documented zero-pair diagnostic baseline (section 6.2). Stays fast.

### 5.2 Cancellation regression: NOT CLEAN — orphaned Abaqus worker process found

A live cancel-mid-extraction smoke test (cancel raised during per-mode export, mode 7 in flight) confirmed:

- `AnalysisCancelled` is raised correctly and `manifest.json` is never written, so partial output is correctly never treated as valid cache (existing contract in `fast_cache.py`, unchanged by this work).
- `stop_owned_process_and_wait` / `cancel_owned_process` (`src/abaqus_bridge.py`) reported the owned `cmd.exe` launcher as terminated (`taskkill /PID <pid> /T /F` succeeded, `process.poll()` non-`None`).
- **However the real Abaqus worker (`SMAPython.exe`) kept running after cancellation was reported complete**, and continued writing `mode_0007.csv` to disk for tens of seconds afterward. `taskkill` later reported this survivor's actual parent as a *different*, untracked PID — i.e. the Abaqus launch chain (`abq2024.bat`) re-parents the real worker under a process outside the tree rooted at the PID this code records, so `/T` (tree-kill) does not reach it.

This is a **pre-existing bug**, not introduced by the format-version-2 optimization (`cancel_owned_process`/`stop_owned_process_and_wait` are untouched by this change; `runtime_hardening.py`'s diff only adds a best-effort progress-text callback inside the existing poll loop). It was found while re-verifying the cancellation contract as part of this performance task's release gate. It fails release-gate item 8 in section 7 ("Stop still terminates owned Abaqus work cleanly") and must be fixed (e.g. by recording the real worker PID via a job object / `CREATE_NEW_PROCESS_GROUP` + `taskkill /T` from the true root, or by having `extract_odb.py` write its own PID to a sentinel file the launcher can taskkill directly) before this is considered release-ready. Only the per-mode-export scenario was reproduced live this session; ODB-inspection, geometry-export, and Python-parse cancellation points were not independently re-verified live and should not be assumed clean.

Any `.sandwich_postfix_benchmark` / `_sandwich_postfix_benchmark.py` artifact remains diagnostic scratch unless explicitly promoted with justification.

### 5.1 Resolved: extraction I/O optimization (geometry-once format)

Real-run measurements against `Job-1.odb` (977,270 nodes), range 7-16, using
local read-only copies under `.sandwich_postfix_benchmark/`:

**Bottleneck breakdown (before):** dominant cost is per-mode full-field CSV
export, not ODB open or geometry indexing. Process launch -> ODB
open+node-coordinate indexing ~11s; each of the 10 mode exports ~27-29s
(~274s, 96% of the 285s extraction wall time). Every per-mode CSV repeated
`instance,node_label,x,y,z` for all 977,270 nodes -- static geometry was
~61% of each row's bytes, duplicated across 10 files (1 needed write + 9
redundant writes). Total format-1 CSV output: 1,503,342,861 bytes (10 files,
~150MB each).

**Optimization implemented:** `abaqus_scripts/extract_odb.py` now writes
static node geometry once to `geometry.csv` (`instance,node_label,x,y,z`)
and per-mode CSVs (`mode_%04d.csv`) contain only
`instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag`, joined
back to geometry by `(instance, node_label)` at parse time (not by row
order, so exact identity is preserved independent of any Abaqus field-value
ordering assumption). Manifest gained `format_version: 2` and
`geometry_file`; `src/abaqus_bridge.py::load_extracted_odb` dispatches on
`format_version` and still reads `format_version` 1 (or missing, which
defaults to 1) read-only. `src/fast_cache.py`'s binary-cache signature now
includes the geometry file so a geometry change alone still invalidates that
cache layer.

**Real measured result (same ODB, same range, local copy):**

| Metric | Before (format 1) | After (format 2) | Change |
|---|---|---|---|
| Abaqus extraction wall time | 285.0s (from timestamps) / 216.2s (main-branch control, warm cache) | 196.1s | ~1.1-1.45x faster (see caveat below) |
| Python parse time | 51.5s | 39.4s | 1.31x faster |
| Total CSV bytes written | 1,503,342,861 | 1,070,706,233 (incl. geometry.csv once) | -432.6 MB (-28.8%) |
| Per-mode export time | ~27-29s | ~17.1-18.3s | ~35% faster per mode |

Scientific output was verified bit-for-bit equivalent before vs after
(identical frequencies, identical 3 accepted pairs, identical MAC/frequency
errors to the digits printed -- see section 3's reference numbers).

**Main vs feature control (section B):** main (`subprocess.run`,
blocking, pipe-captured output) produced byte-identical CSV output
(1,503,342,861 bytes) to the feature branch's pre-optimization script, and a
comparable Python parse time (52.4s vs 51.5s). Its measured extraction wall
time (216.2s) was faster than the feature branch's own earlier same-morning
cold run (285.0s), but that comparison spans two different sessions hours
apart on a 291MB ODB, so OS file-cache warmth is a real confound, not a
controlled variable. Architecturally, the only process-management difference
between branches is a `Popen` + 0.1s poll loop with a cancellation check
versus a single blocking `subprocess.run` call -- overhead on that order
(microseconds per iteration, ~2000 iterations over a 200s run) cannot
plausibly explain a two-minute-scale gap. Conclusion: **no evidence that HUD
process-management/cancellation plumbing adds material extraction
overhead**; the observed session-to-session variance is attributed to
disk/OS-cache state, and no UI-plumbing "optimization" was made on that
basis.

**Progress reporting (section H):** `extract_odb.py` now emits
`PROGRESS: ...` lines (ODB opened, available vs requested vs effective mode
range, geometry export start/done with node count and elapsed time, and
per-mode "exporting mode i/N (mode k)..." / "mode i/N done in Xs").
`run_abaqus_extraction` tails the log file for these lines and forwards them
through a new `progress_callback` parameter; `runtime_hardening.py`'s
`hardened_worker` (confirmed the final `_worker` owner in the patch chain)
relays them into the existing `stage(1, ...)` status text, so the GUI shows
real phase text instead of a static "1/6 Abaqus extraction..." for the
entire multi-minute extraction.

**Cancellation (section I):** a real cancellation fired ~20s into a live
`Job-1.odb` extraction (mid-write of the first mode file) via
`load_or_extract_odb`'s `cancel_event`. Result: `AnalysisCancelled` raised
cleanly, `cache/manifest.json` never written (so `_cache_is_valid` correctly
treats the partial cache directory as invalid on any later run), and a
process check by command line (`Get-CimInstance Win32_Process`) found zero
remaining processes referencing the cancelled run's output directory --- the
owned `cmd.exe`/`SMAPython.exe`/`ABQcaeK.exe` tree was fully torn down by the
existing `taskkill /PID <pid> /T /F` scoping. Two unrelated, long-running
Abaqus sessions already present on the machine (an interactive CAE session
from 9/7, and a separate live extraction against `SP-01.odb` from another
session) were correctly left untouched.

**SP15 regression (section K):** re-run against
`C:\temp\12 sampls\results\SP15\test\CFRP_PLAIN_520_STAGEA_baseline.odb`
with the new format-2 extractor: total pipeline 2.15s (extraction 1.51s),
`format_version: 2`, 20 modes extracted, 0 accepted pairs (unchanged
diagnostic result). Still fast, still correct.

**Node-subset extraction (section F):** not implemented. The comparison
pipeline currently builds `mode.measured_dofs` as all-True over the full
field and geometry mapping in `reviewed_core.py` operates over the complete
FE point cloud before any subsetting to the 121 experimental points; Mode
Shapes visualization also renders the full FE field. A two-stage
(geometry-then-selective-displacement) extraction would require either a
second Abaqus invocation (extra process/license startup cost per run, likely
comparable to or exceeding today's ~11s ODB-open/geometry-index overhead) or
a first-stage geometry pass followed by node-filtered field export in the
same session -- a real architecture change to `extract_odb.py`'s frame/field
API usage, `abaqus_bridge.py`'s manifest schema, and the comparison/report
code that currently assumes full-field mode vectors are available for
visualization. Left as a documented future optimization; not attempted in
this pass given the smaller geometry-dedup change in this section already
captured most of the confirmed redundant I/O.

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

## 11. Cancellation-ownership hardening (Stop reliably kills the real Abaqus worker)

**Root cause (observed, not assumed):** In real process-tree captures on this
host (`Get-CimInstance Win32_Process`, full command lines), `run_abaqus_extraction`'s
tracked launcher chain is `python.exe` (app) -> `cmd.exe` (`CREATE_NEW_PROCESS_GROUP`) ->
`SMALauncher.exe` -> `SMAPython.exe` (running `extract_odb.py` directly). In every
run captured during this investigation the real worker stayed a live descendant
of the tracked launcher PID for the run's full duration -- no reparenting away
from the launcher tree was reproduced. The previously reported production
failure (Stop leaves `SMAPython.exe` alive after `taskkill /PID <launcher> /T /F`)
was therefore not caused by a topology change visible in this environment; the
robust fix is to stop depending on tree position at all, since `taskkill /T`
correctness is inherently a function of that position and any future Abaqus
launcher/version change could alter it again without warning.

**Mechanism implemented:** extractor self-registration. `run_abaqus_extraction`
generates a per-run `uuid4` ownership token and a run-specific
`process_registration.json` path inside that run's own output directory (never
a shared/global path). `extract_odb.py` writes an atomic (`MoveFileExW` /
temp+replace) registration record -- token, `os.getpid()`, a Windows
`GetProcessTimes` creation-time fingerprint, timestamp -- as the very first
thing it does, before `openOdb`. On Stop, `abaqus_bridge.stop_owned_extraction`
reads that record, validates token match, and cross-checks the PID's live
creation time against the recorded one before ever calling `taskkill /PID ... /T /F`
against it; it also still tears down the originally-spawned launcher tree.
Termination is verified (bounded wait + one escalation retry) before
cancellation is reported successful; on failure it raises `AbaqusExtractionError`
(an explicit failure state), never a false "stopped." `manifest.json` is now
published via the same atomic replace on success only, so a killed worker can
never leave a partially-written manifest that a later cache read would
misinterpret as valid.

**Windows Job Object (investigated, not adopted as primary):** a
`CreateJobObjectW`/`AssignProcessToJobObject`/`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
probe assigned the tracked launcher `cmd.exe` to a job immediately after
`Popen` and polled `QueryInformationJobObject` every 2s. Contrary to the
"Abaqus probably breaks away from jobs" assumption, the real chain (launcher
`cmd.exe` -> `SMALauncher.exe` -> `SMAPython.exe`) stayed inside the job for
the observed run's entire life -- no breakaway was seen. This is a genuinely
useful secondary signal, but was not further engineered into a production kill
path in this pass (the self-registration mechanism was already live-verified
against all four cancellation points and does not depend on this still-unproven
kill-time behavior); worth revisiting as a belt-and-suspenders layer later.

**Live cancellation matrix (real `Job-1.odb`, local `.sandwich_postfix_benchmark`
copy, byte-identical size to `E:\sumin\Job-1.odb`):**

| Phase | Result | Evidence |
|---|---|---|
| ODB open | PASS | worker pid 17616 + launcher pid 145036 both confirmed dead post-cancel; unrelated baseline CAE session (SMALauncher 118960/SMAPython 119732/ABQcaeK 119852/ABQcaeG 8228) untouched |
| Geometry export | PASS | worker pid 70176 + launcher pid 147120 both confirmed dead; unrelated session untouched |
| Per-mode export (the reported blocker) | PASS | worker pid 144076 + launcher pid 135992 both confirmed dead; `mode_0007.csv` left truncated at 16,181 of 977,270 rows (proves the worker was killed mid-write, not allowed to finish); no `manifest.json` published; a **second, real, concurrent** app extraction (`python.exe` 148560 -> ... -> `SMAPython.exe` 131648, extracting `SP05_modal.odb` for actual real use during this session) and the baseline CAE session both survived completely untouched |
| Python-side parse/read (no Abaqus worker alive) | PASS | added a cooperative `cancel_event` check to `load_extracted_odb`'s per-mode loop; a real cancel fired after 4.57s (1 of 10 modes parsed) instead of waiting out the full ~35-40s parse |

**Unrelated-Abaqus survival:** confirmed live, twice, opportunistically -- a
long-running unrelated Abaqus CAE session already open on this machine, and a
second real concurrent extraction the application itself launched during this
investigation. Neither was touched by any cancellation in the matrix above.

**Partial-cache validity:** no cancelled run ever produced a `manifest.json`
in this session (verified by directory listing after each test); the one
directory with a partially-written mode CSV (`live_cancel_out_mode`) has no
manifest, so `_cache_is_valid` correctly refuses to treat it as usable, and the
next Run into that same directory naturally overwrites the stale partial file.

**Format-v2 regression after the fix:** full uncancelled rerun, real
`Job-1.odb`, modes 7-16, scale 0.001: `format_version=2`, `geometry.csv`
written once (977,270 nodes), frequencies exactly match the previously
verified extraction (24.147, 76.735, 79.619, 91.425, 92.18, 147.52, 212.13,
214.51, 221.13, 227.9 Hz -- byte-identical to the pre-cancellation-fix
baseline), extraction wall time 185.45s (within the ~196s ballpark, no
regression). PROGRESS messages continued to work throughout.

**SP15:** not independently rerun in this session -- no dedicated SP15 `.odb`
file exists on this machine (only its `.svd`/`.unv` experimental files); the
prior agent's SP15 result was not reproducible without that file. As a proxy,
the previously cached format-2 extraction sharing `Job-1.odb`'s content
(`analysis_58959f0d7fa5a73b`, `C:\temp\SP-01.odb`, same size as `Job-1.odb`)
was reloaded end-to-end under the modified parse code and still parsed
correctly (9 modes, 35.67s, `format_version=2`). None of this change's code
paths execute differently on a normal (non-cancelled) run -- the only
functional additions are a small registration-file write/delete and an
atomic-rename manifest publish (both no-ops on the final parsed content) plus
a `cancel_event` check that is inert when no cancellation is requested -- so
there is no plausible mechanism by which SP15's numeric result would change,
but this was not independently re-observed end-to-end.

**Release-blocker status:** the reported failure mode (Stop leaves
`SMAPython.exe` running after `taskkill /T`) is closed for every process shape
observed in this session's real reproductions and live-verified across all
four cancellation points plus two independent unrelated-process survival
checks. The fix no longer depends on process-tree position at all, so it
should remain correct even if a future Abaqus version changes the
launcher/reparenting behavior that caused the original report.

## Part 3 — VERIFIED responsive HUD and interface scale (2026-09-09)

### Resize bottleneck and fix

Native-Tk profiling with eleven cached 2200x1400 plot images showed that the
old resize path did not recreate Matplotlib figures or repopulate Treeviews.
The bottleneck was the interaction of two 90 ms callback systems: each plot
label independently scheduled PIL LANCZOS resampling/`PhotoImage` creation,
while the root responsive callback repeatedly relabelled all nine Notebook
tabs, regridded metric cards/buttons, rewrote every wrap length, and requested
another immediate refresh of every cached image.

One 1600x900 -> 1024x700 -> 1600x900 sweep produced 98 root Configure events,
50 full responsive-policy executions, 450 Notebook tab updates, 646 image
render callbacks, 0 Treeview mutations, 0 Matplotlib draws/figure creations,
and 0 scientific callbacks. Responsive-policy work took 0.301 s and image
work 2.426 s on Tk's UI thread.

The production path now has two phases:

- active drag: native Tk/container geometry and the bounded status-bar length
  track the Windows frame; expensive application reflow is not performed;
- settled resize: a single cancel-and-replace 210 ms callback applies the final
  layout mode, changed wrapping, compact control layout, and one coalesced
  visible-image batch. No queue of per-label jobs remains.

For the same sweep after the fix, all 98 Configure events were retained, 97
stale settled jobs were cancelled, and exactly 1 responsive-policy execution
ran. It caused 0 Notebook relabels, 4 visible-image render checks, 0 Treeview
mutations, 0 Matplotlib draws/figure creations, and 0 scientific callbacks.
Responsive-policy time was 0.000089 s and image work 0.099 s, with no pending
layout/image jobs afterward.

All scientific plots in the current HUD are generated once into PNG assets.
Resize retains their decoded PIL sources and only creates a final presentation
`PhotoImage` after settlement; the underlying scientific arrays and Matplotlib
rendering pipeline are never invoked by Configure events.

### Sizes, density, and navigation

The input tab now has both vertical and horizontal scrolling, the minimum
window was reduced from 900x650 to 760x560, and camera-calibration controls
stack into a compact grid with shorter presentation widths. Native checks at
1920x1080, 1600x900, 1366x768, 1280x720, and 1024x700 confirmed all required
configuration controls plus Run/Stop are managed and reachable, all nine tabs
can be selected, and the 1024x700 compact content fits horizontally (954 px
requested in a 955 px canvas; scrolling remains available for larger UI scale
or OS-DPI combinations).

### Interface scale and DPI

Settings -> Interface scale provides 80%, 90%, 100%, 110%, and 125%, defaulting
to 100%. It updates named Tk fonts, ttk styles, table row height, common padding,
and responsive density without rebuilding the application or rerunning analysis.
It is stored only in the application `ui_preferences.json`, is absent from the
scientific project schema/dirty snapshot, and cannot change coordinate units,
camera factors, geometry, MAC, frequencies, or cached results.

Windows DPI awareness remains enabled. Tk's OS-DPI scaling is not modified by
the Interface scale control; font point sizes are multiplied only by the user
factor. Logical-width tests cover 100%, 125%, and 150% Windows scaling and the
native test confirms changing Interface scale leaves `tk scaling` unchanged,
preventing double multiplication.

### State and stress verification

RUNNING and STOPPING keep every scientific configuration control locked during
responsive/UI-scale updates; Run/Stop state and progress text are not derived
from layout. The completed zero-pair path remains DIAGNOSTIC and replaces all
three Mode Shapes panels' transient running text with `No accepted mode pairs`
guidance to MAC/frequencies and Manual Review.

A six-cycle native Windows/Tk stress harness exercised continuous
1600x900 <-> 1024x700 geometry changes while visiting Input, MAC, FRF, Close
Modes, Mode Shapes, and Manual Review, followed by two maximize/restore cycles.
It processed 592 Configure events, cancelled 586 stale final-layout callbacks,
performed only 6 settled policy executions (0.00154 s total), 8 visible image
renders (0.222 s), no Treeview/scientific/Matplotlib work, no stale jobs, and no
TclErrors. Mean/max event-loop update time was 13.4/81.6 ms. Native mouse-drag
visual observation could not be automated because the available computer-use
surface exposed no native applications; final human visual QA on the target
Windows display remains required before PR preparation.

### Remaining HUD release blockers

No automated Part-3 code/test blocker remains. Final human mouse-drag visual QA
at the intended Windows DPI settings is still required. The separately recorded
PolyMAX dataset-55 modal-set importer remains post-HUD work; SCI-S0 was not
started and neither item is part of this change.

## Final manual-QA cached ODB loader regression - VERIFIED (2026-09-09)

A real GUI run exposed a contract mismatch introduced when
`abaqus_bridge.load_extracted_odb` gained cooperative `cancel_event` support:
`fast_cache._cached_extracted_odb_loader` still accepted only `manifest_path`,
although the installed wrapper replaced the public loader and
`load_or_extract_odb` called it with `cancel_event=...`. The valid extraction-
cache path therefore failed before loading data with an unexpected-keyword
`TypeError`.

The fast-cache wrapper now accepts the same optional argument. Cache misses
pass that exact event to the original CSV loader, preserving cancellation
during Python-side parsing. Cache hits check the event before signature/cache
work, immediately after the potentially expensive pickle read, and again
after cloning just before return. All cancellation exits use the existing
`abaqus_bridge.AnalysisCancelled("Analysis stopped by user.")` exception.
Manifest, mode-file, and format-2 geometry signatures, format-1/format-2
compatibility, stale-cache invalidation, and binary-cache reuse metadata are
unchanged.

Focused fast-cache/cancellation/format tests passed (28). Native Tk tests
passed (35). Full pytest passed (320 passed, 3 skipped, 37 subtests; one
pre-existing collection warning).

A real production-installed-loader smoke used the existing sandwich
format-2 extraction for modes 7-16. The first load populated an isolated
binary cache, the second load reported `binary_odb_cache_reused=True`, and all
10 cached modes matched the original loader exactly for mode number,
frequency, node IDs, coordinates, and vectors. A pre-set Stop event through
the same `load_or_extract_odb` path raised `AnalysisCancelled`; no unexpected-
keyword failure occurred. This closes the reported final-manual-QA loader
regression without changing scientific results.
