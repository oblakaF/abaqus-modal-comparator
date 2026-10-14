# Quick material calibration (Abaqus INP + Polytec / Testlab UNV-UFF)

A fast, honest engineering answer to: *which elastic constants make this FE model reproduce
this specimen's measured modes, and how well are they constrained?*

It is **not** the governed Auto-ID material identification (`docs/auto_id/SPEC_V1_2.md`). The
result is always labelled `EFFECTIVE_MODEL_CALIBRATION` / `NOT_A_MATERIAL_PROPERTY`: effective
constants of *this* model for *this* specimen, not transferable without validation.

## Start

- Main application (`RUN_PROGRAM.cmd`): it offers two workflows, in the **Workflow** menu and
  as buttons under the title. **1. Compare modes (ODB + UNV/UFF)** is the main window itself
  (tab "1. Files"). **2. Calibrate effective material properties (INP + UNV/UFF)** opens this
  calibration window inside the application (one window; pressing it again brings it to the
  front). Closing the application (window "X" or File > Exit) while a calibration runs, or
  while the termination of its Abaqus processes is unconfirmed, first stops the calibration
  (see *Stop, timeout and closing the window*); the application stays open until the
  calibration window has closed.
- The result line under **Run / Stop** states the status first: `ESTIMATE, grade ...` (effective
  constants, multiplier, band; always *NOT A MATERIAL PROPERTY*; APPROXIMATE and UNRELIABLE are
  marked as not validated / not to be used), `REFUSED (no value): ...` or `BASELINE_ONLY ...`.
  **Open report** opens `report.txt`, **Open output folder** the run folder.
- Window alone: double-click `RUN_QUICK_CALIBRATION.cmd`. Choose the INP, the UNV/UFF, the
  **experimental modal set** (listed from the file), the material (filled from the INP), press
  **Check inputs** (no Abaqus run), then **Run calibration**.
- Command line:

```text
python tools/quick_calibration.py sets SP13.unv           # list the dataset-55 modal sets (no Abaqus)
python tools/quick_calibration.py quick --inp SP13.inp --unv SP13.unv --modal-set best --material CFRP_Face --out SP13_quick --abaqus abq2024 --cpus 4 --check-only
python tools/quick_calibration.py quick --inp SP13.inp --unv SP13.unv --modal-set best --material CFRP_Face --out SP13_quick --abaqus abq2024 --cpus 4
python tools/quick_calibration.py template case.json      # editable configuration
python tools/quick_calibration.py check case.json         # input preflight only
python tools/quick_calibration.py run case.json
```

## Input readiness (checked before any Abaqus solve)

Every run starts with the input preflight (also available alone: **Check inputs** / `check` /
`--check-only`). Any `REFUSED` line stops the run before the first solve.

| Check | Refused when |
|---|---|
| Model INP | the file cannot be read |
| Material and elastic constants | the material, its single temperature-independent `*Elastic` record or a listed constant is missing, a value is not positive, or the INP has not exactly one `*Frequency` step |
| INP file references | an `INPUT=` reference (`*Include`, `*Node, input=...`, ...) is relative — Abaqus resolves it from the newly generated job folder, where the file is not — or an absolute one does not exist / cannot be read (nested references too) |
| Experimental file | it cannot be read |
| Experimental modal set | the file has several dataset-55 modal sets and none is selected, or the selection is unknown / matches several sets (selection by key is exact). The first set is never chosen automatically; a file with one set uses it and says so |
| Experimental modes | no mode remains after the set, mode and frequency selection (the count used is reported) |

The physical orientation needs the baseline FE geometry: it is checked after the single baseline
solve and before any optimisation step. If it is ambiguous the run stops there and lists the
candidates.

Example — the real SP-13 PolyMAX UNV has two modal sets, `Best — 12 modes` and
`Processing — 21 modes`; without a selection the run is refused before Abaqus starts.

## Inputs

| Input | Notes |
|---|---|
| Abaqus model `.inp` | Re-solvable model with one `*Frequency` step. The calibrated material's `*Elastic` must be in this file (not in an `*Include`), temperature-independent, type `ENGINEERING CONSTANTS`, `LAMINA` or `ISOTROPIC`. An ODB is not enough: sandwich frequencies do not scale as √E. |
| Polytec / Testlab `.unv` / `.uff` | Preferred: curve-fitted modes (PolyMAX, dataset 55/2414). Dataset 58 FRFs are accepted; their peak-derived modes cap the grade at APPROXIMATE. |
| Experimental modal set | Required when the file holds several dataset-55 modal sets (e.g. PolyMAX `Best` and `Processing`). |
| Material and constants | A multiplier k scales the listed constants together (default `E1,E2` for a face sheet). Optional second parameter: `G12` of the same material. |
| Mode range | Set "from" above the suspension modes. |
| Orientation | For a symmetric panel the scan orientation cannot be found from geometry; the program stops and lists the candidates. Choose from the photograph / corner marker, never from MAC. |

## Method

1. Read the experiment with the application's reader.
2. Solve the unchanged INP; pair modes with the application's comparator (geometry-only
   registration, rigid modes removed). Pairs with MAC ≥ 0.80 become the fitted rows and are frozen.
3. Each candidate k: write the INP, solve, extract, follow every row by FE-to-FE MAC ≥ 0.90 on the
   scanned surface. Loss of identity stops the run (no re-pairing).
4. Bounded Levenberg–Marquardt in ln k (`run_bounded_lm`, SPEC §8 constants) on
   r = ln(f_FE/f_EXP)/σ, σ = 0.3 %. Typically 6–10 Abaqus solves for one parameter.
5. At the optimum: a fresh central-difference Jacobian, then
   - statistical sd and scatter-scaled sd (×√(χ²/dof));
   - linearised leave-one-mode-out range;
   - **mode spread**: how far apart the single modes are about the value (sensitivity-weighted).
   The reported **band** is the largest of the three.

## Result

| Status / grade | Meaning |
|---|---|
| `NO VALUE` | optimum on a search bound; mode identity lost; not converged; parameter not observable; too few MAC ≥ 0.8 pairs. |
| `GOOD` | band ≤ 5 %, every mode within 5 % after calibration, ≥ k+2 modes, curve-fitted experiment. |
| `APPROXIMATE` | band ≤ 10 % and every mode within 10 %. |
| `UNRELIABLE` | a value is shown, but the modes disagree about it (model-form discrepancy: core, adhesive, thickness, boundary conditions). |

Because frequencies depend weakly on E (d ln f / d ln E ≈ 0.2–0.5 in a sandwich), a ±5 %
frequency disagreement between modes means a ±10–25 % spread in E. The grade reports that
honestly instead of the much smaller sd of a mean.

Output folder: `report.txt`, `result.json`, `modes.csv` (per mode: start/final error, MAC,
sensitivity, the multiplier this mode alone asks for), `<model>_calibrated.inp` (only when a value
is shown), `config.json`, and `work/` with the Abaqus jobs (a repeated run reuses a finished job only when its
provenance is verified, see below).

## Accepted physical registration and baseline-only mode

`physical_registration_fixture` (window: **Physical registration**; CLI: `--physical-registration-fixture`; never
preselected) applies the frozen measured-point-to-FE-node mapping and rotation of an accepted fixture, e.g.
`SP13/best-physical` (`docs/registrations/SP13_physical_registration.json`). It excludes a manual orientation and a
coordinate scale. Before Abaqus the preflight verifies the fixture and the registration seal, the model INP SHA-256
against the fixture's model input, the experimental file content and the modal set / points / measured-DOF contract.
After the baseline, the FE geometry identity is recomputed from the full extracted dataset and must equal the
registration's (for SP-13 `34d69d79…`, 1,585,637 nodes); the registration must be content-compatible and every mapped
FE node present. Otherwise the run is refused (`REGISTRATION_IDENTITY_MISMATCH`) before any optimiser step; there is
no automatic fallback. Pairing then uses `compare_modal_datasets(..., frozen_registration=...)` with the unchanged
MAC and frequency gates.

**Baseline only** (window checkbox; CLI `--baseline-only`; requires `max_new_fe_solves = 1`) runs the preflight,
obtains one verified baseline FE dataset (or reuses a verified one), verifies the registration and writes the
baseline frequency / MAC table as `BASELINE_ONLY`: no optimiser evaluation, no material update, no estimate and no
calibrated INP. For SP-13 the archived regression references are EXP 4 <-> FE 10 (MAC 0.958458) and EXP 7 <-> FE 13
(MAC 0.946904); they are references, not an independent validation.

## Verified FE job cache

Each finished job in `work/<job>/` has `provenance.json` (schema `quick-calibration/fe-job-provenance/v1`),
written atomically only after a complete solve, extraction and mode-data write. It records the SHA-256 of
the generated INP, every `INPUT=` file (nested includes) with its SHA-256 and size, the requested FE modal
range (`fe_last_mode`), the Abaqus command and the SHA-256 of the launcher it resolves to (and the release
read from the job's `.dat`/`.msg` when present), the extraction script SHA-256 and settings, the stored FE
node set (all nodes for the baseline, the tracking subset for candidates), solve/extraction completion,
the SHA-256 of `fe_modes.npz`, and a hash of the record itself.

A job is reused (`VERIFIED_REUSE`) only when the record is intact, every field matches the current run and
the mode data is the recorded data. `fe_modes.npz` alone is never enough. An old cache without a record, a
changed include, modal range, Abaqus launcher, extraction script or setting, tracking subset, a corrupted or
partial file, an interrupted job, or an identity that cannot be determined gives `INVALIDATED` (fail closed);
the job is then solved again at the same path (`NEW_SOLVE`), which needs the FE solve budget. If a stop of a
job's processes was not confirmed, `TERMINATION_UNCONFIRMED.json` stays in the job folder: the job is neither
reused, deleted nor overwritten until the recorded processes are confirmed gone. Before every new solve the
job folder gets `JOB_IN_PROGRESS.json` (if it cannot be written, Abaqus is not started); it is removed only
after a completed job or a confirmed end. A folder with this marker (an interrupted run, a crash, an
unrecorded stop) or an incomplete folder without any completion or termination record (for example from
an older version) is never reused, deleted or overwritten automatically: check Task Manager, then delete
the folder manually. `INPUT=` nesting deeper than 10 levels is refused by the preflight. Every decision is listed
in `report.txt` and `result.json` (`fe_job_cache`) with its reason and fingerprints. The CPU count is not part
of the identity (it does not change the model).

## FE solve budget

`max_new_fe_solves` (window: **Max new FE solves**; CLI: `--max-new-fe-solves`; default **24**,
never unlimited) is a hard cap on NEW Abaqus solve attempts in one run: baseline, optimiser
evaluations, the final evaluation and the central-difference sensitivities together. It is checked
immediately before every solve; a failed attempt counts, a finished job reused from `work/` does
not. When it is reached no further solve starts and the run ends as `NO VALUE (BUDGET_EXHAUSTED)`
with the attempted / completed counts and the limit: no calibrated value, no calibrated INP (one
left by an earlier run in the same folder is removed), and the optimiser's point is not reported.
The optimiser's own evaluation budget (`solve_budget`, default 16) is separate. The default 24 =
1 baseline + 16 optimiser evaluations + 2 central differences for each of up to 2 parameters + 3 spare.

## Stop, timeout and closing the window

- **Stop** terminates only the processes this run started: the Abaqus launcher and every child
  observed while its parent was still the recorded process (same PID and creation time) and created
  after it. Each kill re-checks that identity on the process itself, so a reused PID is never killed;
  a process whose identity cannot be read is never killed and never counted as stopped. The window
  shows `STOPPING` until termination is confirmed, then `STOPPED by the user ... (confirmed)`. If
  termination cannot be confirmed it shows `STOP NOT CONFIRMED` with the PIDs; closing and new runs
  stay blocked until the processes are confirmed gone, or until the user confirms after checking Task
  Manager (an unknown state, e.g. no tracker, always needs that confirmation).
- A per-solve **timeout** stops the owned processes the same way and says whether termination was
  confirmed.
- **Closing the window** during a run requests Stop and closes only after confirmed termination; if
  it cannot be confirmed the window stays open with the reason.
- A stopped or failed job leaves no completed-job marker (`fe_modes.npz` is written atomically and
  only after a complete solve and extraction) and its job folder is removed; a later run never
  reuses it.

## Implementation

`src/services/quick_calibration.py` (service), `tools/quick_calibration.py` (CLI),
`src/quick_calibration_window.py` (window), `src/application_layers.py` (reader/comparator layers
shared with the main window). Tests: `tests/test_quick_calibration.py`,
`tests/test_quick_calibration_window.py`, `tests/test_quick_calibration_preflight.py` (synthetic
plate, synthetic multi-modal-set UNV and a fake Abaqus; the real SP-13 UNV when the data store is
configured), `tests/test_quick_calibration_cancellation.py` (Stop, timeout and window closing with a
dummy Abaqus process tree and mocked termination failures). Process ownership:
`src/services/owned_processes.py`.
