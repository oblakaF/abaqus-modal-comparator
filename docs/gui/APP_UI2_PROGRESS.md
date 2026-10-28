# APP-UI.2-O1 — the window stopped repainting at "6/6 Report data generation" (2026-10-28)

Branch `fix/app-ui2-o1-progress-repaint` from `main` `566d0c5`.

**Status: O1_MAJOR_BLOCK_MITIGATED.** The 28-second block is removed. A pause of about 4–5 s remains: plots and
mode-viewer preparation on the GUI thread (see *Remaining pause*).

- **Step 1 (`9a9baba`):** cause established, no program source changed.
- **Step 2 (APP-UI.2-O1-FIX):** fix in `src/project_review.py` only.

## Observation O-1 (APP-REAL.1)

During the last analysis stage the status reads "6/6 Report data generation...". The window then stops repainting
until the finished result appears.

## Measurement

**Harness.** The harness runs the real main window in-process, with the full install chain, and starts a real analysis
through the program's own Run. Inputs: the SHA-verified APP-REAL.1 copies of SP-02 (extracted `manifest.json` and
PolyMAX UNV, modal set *Bravo (1)*; no Abaqus, no FE calculation). It records:

- a `root.after(10 ms)` heartbeat, with the interval between beats;
- timestamps of every worker stage, of `_write_summary` (stage 6, worker thread), and of `_complete`, `_populate`,
  `_show_loaded_modal_data` and `_set_analysis_state` (GUI thread);
- every call of `_detect_rigid_modes` and `_rigid_body_residual_fraction`, with its thread;
- a `cProfile` of `_complete` (separate run).

Timeline of the program before the fix (step 1):

| Time (s) | Thread | Event |
|---|---|---|
| 1.31 | worker → GUI | 1/6 Abaqus extraction (loading the extracted package) |
| 121.1 – 180.2 | worker → GUI | stages 2–5 |
| 181.2398 | worker | **stage 6: `_write_summary` takes 0.2 ms** |
| 181.30 | GUI | `_complete` starts; the status still reads "6/6 Report data generation..." |
| 181.42 – 196.17 | GUI | `_populate` (14.8 s) |
| 196.17 – 208.30 | GUI | `_apply_manual_reviews` (12.1 s) |
| 208.30 – 210.13 | GUI | `_show_loaded_modal_data` (1.8 s) |
| 210.15 | GUI | `_complete` ends; "Analysis complete – 6 admissible pairs" |

## Cause (profile of `_complete`, 28.8 s)

| Time | Where |
|---|---|
| **24.2 s** | `project_review.refresh_review_table` → `_all_elastic_abaqus_modes` → `quality_control._detect_rigid_modes` → `_rigid_body_residual_fraction`: one `numpy.linalg.lstsq` per FE mode on the full FE mesh (18 calls = 9 modes × 2; 15.0 s in `lstsq`, 7.8 s building the basis). |
| ×2 | It ran **twice** per completion: from `reviewed_populate` (`project_review.py`) and from `polished_apply` (`project_review_polish.py`), each time on the same `result.abaqus`. |
| 2.6 s | plot images in `_populate` (matplotlib `savefig`: CMIF, advanced metrics, pair images) |
| 1.8 s | `_show_loaded_modal_data` → `modal_data_viewer.viewer_modes` |

So O-1 is not the worker stage 6: that stage takes milliseconds. O-1 is the completion on the GUI thread. There the
manual-review table classified the rigid-body FE modes twice, with a full-mesh least-squares fit per mode, while the
status still showed the last worker stage.

## Fix: reuse the comparison's own quality-control classification

**Why this variant.** `quality_control.compare_modal_datasets_with_quality_control` (the only producer of the
program's comparison result, through `modal_core.compare_modal_datasets`) has already classified every FE mode on the
worker. Checked in the code and on data:

- **Filtered set.** It builds the filtered FE set from the retained modes in frequency order. It records in its
  `metadata["quality_control"]`:
  - the method and the threshold;
  - the residual of every FE mode, rigid ones included;
  - the excluded modes;
  - the first elastic frequency.
- **`result.abaqus`.** `reviewed_core.compare_modal_datasets` turns that set into `result.abaqus`: a copy with the
  same `ModeShape` objects and the same metadata.
- **No later rewrite.** Nothing in `src/` replaces or mutates `result.abaqus.modes` or that record afterwards.
- **No second variant needed.** The previous call of `_detect_rigid_modes(result.abaqus)` therefore only re-derived,
  at full cost, a classification already made and recorded. The fallback variant (classify again on the worker at
  stage 6) was not needed and was not implemented.

**Change.** In `src/project_review.py`, `_all_elastic_abaqus_modes(result)` first calls the new
`_quality_controlled_elastic_modes(result)`. It reuses the record only if every check below holds:

1. **Origin and criterion.** `rigid_mode_method` is the quality-control method, and `rigid_shape_residual_threshold`
   is a number equal to the current `RIGID_SHAPE_RESIDUAL_THRESHOLD`.
2. **Completeness.**
   - The residuals form a dict with integer keys and numeric values, and `excluded_abaqus_modes` is a list.
   - Mode numbers are integers with no duplicates.
   - Every recorded mode is either in the current set or excluded, never both, and there is no other mode.
3. **Consistency with the current set.**
   - Each current mode is retained by the same comparison `_detect_rigid_modes` makes; each excluded mode is rigid
     by it.
   - `first_elastic_frequency_hz` equals the lowest current frequency.
   - `result.abaqus_mode_numbers` (the modes the comparison was computed on) equals the current set.
4. **Order.** The modes are returned sorted by frequency, the same stable order `_detect_rigid_modes` gives.

Otherwise it returns `None`, and `_detect_rigid_modes(result.abaqus)` runs exactly as before. Unchanged:

- the criterion, `RIGID_SHAPE_RESIDUAL_THRESHOLD`, the exclusion rules and the first elastic FE mode;
- experimental mode 1, MAC, pairs, frequencies, statuses and registrations;
- `quality_control.py`, `project_review_polish.py` and `runtime_hardening.py`;
- there is no new `install_*` layer and no frequency threshold for rigid modes.

## Before / after (SP-02, *Bravo (1)*, the same verified copies, the same machine)

Both programs ran back to back from identical copies of the tracked tree; they differ only in
`src/project_review.py`.

| | Before (`9a9baba`) | After (fix) |
|---|---|---|
| Largest heartbeat interval (GUI pause) | **28 533 ms** | **3 776 ms** |
| `_complete` on the GUI thread | 28.45 s | 3.70 s |
| `_populate` | 14.23 s | 1.75 s |
| `_detect_rigid_modes` on the GUI thread | 2 calls (18 projections, 24.6 s) | **0** |
| `_detect_rigid_modes` on the worker | 2 calls (unchanged) | 2 calls (unchanged) |
| Stage 6 `_write_summary` (worker) | 0.4 ms | 0.4 ms |
| Run → "Analysis complete" | 92.9 s | 67.3 s |
| `analysis_summary.json` | SHA-256 `f5e4e815…` | **byte-identical** |
| Review table (9 FE modes 7–15, both runs) | identical rows | identical rows |

**Real-data check of the reuse** (SP-02 after the fix):

- The record is accepted. The method is "six-vector rigid-body subspace projection" with threshold 0.02.
- Residuals are recorded for modes 6–15; mode 6 is excluded (residual 0.0).
- The reused list is modes 7–15. It holds the same objects in the same order as `_detect_rigid_modes(result.abaqus)`.
- The first elastic FE mode 7 (23.57 Hz) is retained.

### Remaining pause

| Time | Where |
|---|---|
| 2.7 s | `_populate` → `advanced_ui` / `figure_export_ui` / `cmif_ui`: matplotlib `savefig` (11 figures, 2.2 s) |
| 1.8 s | `_show_loaded_modal_data` → `modal_data_viewer.viewer_modes` |

This is the profiled run (`_complete` 4.75 s; largest pause 4 850 ms with the profiler on, 3 776 ms without). Moving
plots and viewer preparation off the GUI thread is a separate, larger change and is not part of this task.

## Scientific regression against T1b

- **Reference.** `run_20261016/output/ws_SP02/analysis_f72d1650400b8ccd/analysis_summary.json`, SHA-256
  `2ad94b15f3791a01841ab1f435c884a3f4e4c1f70ee28ba2501bb0e51591504c`. The SHA was verified before reading, and the
  file was only read.
- **Method.** Three runs (before, after, after-with-profiler) were compared field by field in the data:

  | Pair | FE | EXP | f FE (Hz) | f EXP (Hz) | Error (%) | MAC | Status |
  |---|---|---|---|---|---|---|---|
  | 1 | 8 | 2 | 75.24107 | 74.37597 | +1.16 | 0.918 | Excellent match |
  | 2 | 9 | 3 | 78.25014 | 78.16163 | +0.11 | 0.622 | Review |
  | 3 | 10 | 4 | 89.32709 | 90.57492 | −1.38 | 0.951 | Excellent match |
  | 4 | 11 | 5 | 90.54398 | 91.94954 | −1.53 | 0.570 | Poor match |
  | 5 | 12 | 6 | 144.17668 | 144.76272 | −0.40 | 0.614 | Review |
  | 6 | 13 | 7 | 207.42729 | 201.99945 | +2.69 | 0.975 | Excellent match |

- **Pairs.** All 6 pairs are identical to T1b in full float precision: FE and EXP numbers, frequencies, errors, MAC
  and statuses.
- **Other fields.** Only two fields differ, the same in all three runs and as in APP-REAL.1:
  - `experimental_source`: the copy's path;
  - `warnings[0]`: the later wording of the registration-reuse warning. T1b says "archived sensitivities do not
    apply"; now it says "apply only if 11. Scaling verifies this ODB…". There are 5 warnings on both sides; the
    other 4 are identical.
- **SP-13** was not run and is not claimed as verified.

## Windows GUI smoke (`RUN_PROGRAM.cmd`)

**Setup.** Isolated profile; the same SP-02 copies; *Bravo (1)* chosen on Home, **Run analysis** on Home; the
calibration confirmation answered OK. During the run the harness asked the window every 0.25 s whether it answers:
`SendMessageTimeout(WM_NULL, 250 ms)` and `IsHungAppWindow`.

| | Before (step 1) | After (fix) |
|---|---|---|
| Longest unresponsive period | **28.1 s** (181.1 → 209.2 s) | **3.3 s** (179.6 → 182.9 s) |
| Starts | right after `analysis_summary.json` | right after `analysis_summary.json` |
| Windows "Not responding" (`IsHungAppWindow`) | 92 samples | **0** samples |
| Other short periods (worker stages) | 43, ≤ 0.39 s | 43, ≤ 0.43 s |
| Result | 6 pairs = T1b | 6 pairs = T1b; summary SHA-256 `f5e4e815…`, the same as the harness runs |
| Process | no child process, exit code 0 | no child process, exit code 0 |
| Inputs | byte-unchanged | byte-unchanged |

After the run Home shows "Comparison complete", 6 matched pairs, mean MAC 0.948 (3) / 0.775 (6). Closing the window
answered "Don't save" once for the recovered session, as before.

## Tests

`tests/test_app_ui2_progress.py`: real main window and synthetic data, with no process. The `expectedFailure` and
the step-1 characterisation test are replaced.

- **`QualityControlRecordTests`.** Synthetic SP-02 world through the real comparison, with an FE set made of:
  - 6 rigid-body modes;
  - a nearly rigid mode on each side of the threshold (residual ~0.01 excluded, ~0.05 kept as the first elastic
    mode);
  - a degenerate pair at the same frequency;
  - modes listed out of frequency order.

  The tests check:
  - the reused list equals the previous function: the same objects in the same order, without any projection;
  - rigid modes stay excluded, the first elastic mode stays available, and both degenerate modes are kept;
  - **the previous path runs** (one `_detect_rigid_modes`, same list) when:
    - metadata is missing or the record is damaged;
    - the method or threshold differs, or the threshold is not a number;
    - the record is incomplete, has JSON-style string keys, or has duplicates;
    - the record contradicts the current set (a retained mode marked rigid, an excluded mode marked elastic, a
      changed first elastic frequency);
    - the FE set changed (a mode added, removed, duplicated, an excluded mode back, a changed frequency);
    - the record or mode list comes from another analysis.
- **`CompletionThreadTests`** (real window):
  - a completion does **no** classification and **no** projection on any thread, and the review table lists the
    previous function's modes;
  - a result without its record is classified as before (2 × `MainThread`) with the same table;
  - a new analysis shows the modes of its own result. A changed FE set falls back; a further valid result reads its
    own record;
  - Stop, an error and inputs changed while running (P-1 `DISCARDED`) end without classification;
  - a result made stale afterwards is cleared (P-1 `STALE`);
  - a completion posted after the window started closing does nothing.

**Reproduction.** Against the old `project_review.py`, the main completion test fails: 2 classifications and 14
projections on `MainThread`. With the fix it passes.

## Limits

- **One machine, one specimen.** The measurement is SP-02 on this machine. SP-13 (more modes, a larger mesh) was not
  measured; its remaining plot/viewer pause may be longer.
- **Undetectable change.** The record carries no fingerprint of each mode shape. A set whose mode numbers, excluded
  modes, first elastic frequency and comparison mode list all match, but whose shapes were swapped under the same
  numbers, cannot be detected. No code path builds such a result: `result.abaqus` is made only by the comparison and
  is never mutated.
- **Remaining pause.** About 4–5 s of plots and viewer preparation remain on the GUI thread (see *Remaining pause*).
- **Stage 1 time** (120 s in the first run, 3.3–3.6 s later) is file-cache dependent and unrelated to O-1.
