# APP-UI.2-O1 — the window stops repainting at "6/6 Report data generation" (2026-10-28)

Branch `fix/app-ui2-o1-progress-repaint` from `main` `566d0c5`. **Status: cause established, fix not made.** The fix
needs files outside the scope authorised for this task (see *Proposed fix*). No program source was changed.

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
- a `cProfile` of `_complete`.

Timeline of the current program:

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

**Heartbeat:**
- **Largest interval: 28 926 ms**, exactly the GUI-thread completion.
- During the worker stages the largest intervals are 0.77–0.82 s (stage 3, registration). The window stays
  responsive there.

## Cause (profile of `_complete`, 28.8 s)

| Time | Where |
|---|---|
| **24.2 s** | `project_review.refresh_review_table` → `_all_elastic_abaqus_modes` → `quality_control._detect_rigid_modes` → `_rigid_body_residual_fraction`: one `numpy.linalg.lstsq` per FE mode on the full FE mesh (18 calls = 9 modes × 2; 15.0 s in `lstsq`, 7.8 s building the basis). |
| ×2 | It runs **twice** per completion: from `reviewed_populate` (`project_review.py`) and from `polished_apply` (`project_review_polish.py`), each time on the same `result.abaqus`. |
| 2.6 s | plot images in `_populate` (matplotlib `savefig`: CMIF, advanced metrics, pair images) |
| 1.8 s | `_show_loaded_modal_data` → `modal_data_viewer.viewer_modes` |

So O-1 is not the worker stage 6: that stage takes milliseconds. O-1 is the completion on the GUI thread. The
manual-review table classifies the rigid-body FE modes there, twice, with a full-mesh least-squares fit per mode,
while the status still shows the last worker stage. The classification is already made once on the worker by
`quality_control.compare_modal_datasets_with_quality_control`, but its result is not kept for the review table.

## Proposed fix (needs authorisation for `src/project_review.py`)

1. **Compute once, off the GUI thread.** At stage 6 (worker, `runtime_hardening.hardened_worker`), compute the
   elastic FE modes once: `project_review._all_elastic_abaqus_modes(result)`, unchanged. Keep them with the result,
   for example as an attribute or a `metadata` entry tied to that `result.abaqus`.
2. **Read it on the GUI thread.** `project_review._all_elastic_abaqus_modes` returns that kept value when it belongs
   to the same dataset; otherwise it computes as today. One function in `project_review.py`.
3. **Unchanged:**
   - the classification itself (same function, same threshold) and the pairs, MAC, statuses;
   - Stop: the computation is inside the worker, before `check_cancelled()`;
   - closing the window and P-1 (`discarding_stale` around `_complete`);
   - no Tk call from the worker, no `root.update()`, no new `install_*` layer.

   A second completion can never reuse a value of another result, because the value is tied to the dataset object.

**Prototype measurement.** The prototype was applied only in the measuring harness (scratchpad): steps 1–2 by
wrapping the two functions. The program source was not changed.

| | Current | Prototype |
|---|---|---|
| Largest heartbeat interval | 28 926 ms | **4 784 ms** |
| Classification | GUI thread, 2 × 12 s | worker, stage 6, 1 × 12.1 s (status "6/6 Report data generation" correct while it runs) |
| GUI-thread completion | 28.8 s | 4.7 s (2.7 s plots, 1.8 s viewer) |
| Pairs, frequencies, errors, MAC, statuses vs archived T1b | identical (6 pairs) | identical (6 pairs) |

- **T1b reference.** `run_20261016/.../analysis_f72d1650400b8ccd/analysis_summary.json`, SHA-256 `2ad94b15…`
  (verified before reading). Besides the pairs, only `experimental_source` (the copy's path) and the wording of
  `warnings` differ, exactly as in APP-REAL.1.
- **The remaining 4.8 s** is matplotlib rendering and modal-viewer preparation on the GUI thread, in
  `advanced_ui` / `figure_export_ui` / `cmif_ui` / `ui_workflow`. Moving them off the GUI thread is a separate,
  larger change and is not proposed here.

## Windows GUI smoke (`RUN_PROGRAM.cmd`, current program)

**Setup.** Isolated profile; the same SP-02 copies; *Bravo (1)* chosen on Home, **Run analysis** on Home; the
calibration confirmation answered OK. During the run the harness asked the window every 0.25 s whether it answers:
`SendMessageTimeout(WM_NULL, 250 ms)` and `IsHungAppWindow`.

**Result:**
- **One long unresponsive period: 28.1 s** (181.1 → 209.2 s after Run). It starts right after
  `analysis_summary.json` was written (stage 6). During it Windows reports the window as hung ("Not responding",
  92 samples).
- **43 short periods** of at most 0.39 s during the worker stages.
- **Result:** 6 pairs, identical to T1b.
- **Process:** no child process, exit code 0, inputs byte-unchanged.

## Tests

`tests/test_app_ui2_progress.py` uses the real main window, synthetic data, no process.

- **`test_the_completion_classifies_the_fe_modes_on_the_gui_thread`** (passes): the completion of an established
  comparison classifies the rigid modes twice, on `MainThread`. This characterises O-1.
- **`test_the_gui_thread_completion_does_no_rigid_mode_classification`** (`expectedFailure`): the reproducer of the
  proposed fix. It becomes an ordinary test once the classification leaves the GUI thread.

## Limits

- **One machine, one specimen.** The measurement is SP-02 on this machine. The time scales with the FE mesh size and
  the number of FE modes. SP-13 (more modes, a larger mesh) is expected to be slower; it was not measured.
- **Stage 1 time** (120 s in the first run, 3.3 s in the second) is file-cache dependent and unrelated to O-1.
