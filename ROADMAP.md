# Roadmap

Working notes for hardening this program toward reproducible scientific use.
Items move between sections as they are reproduced, fixed, or ruled out — this
file is expected to change every stage, not stay static.

## Stage 1 status: done

- `ROADMAP.md` created (this file).
- Direct unit tests added for the two modules with genuinely zero prior
  coverage: `amplitude_correlation.py` (`tests/test_amplitude_correlation.py`)
  and `reporting_hardening.py` (`tests/test_reporting_hardening.py`).
  (`universal_frf_review.py` turned out to already be covered by
  `tests/test_frf_import.py`; `metrics_normalization.py` was covered
  indirectly through AutoMAC/COMAC tests — both were checked against actual
  test-file imports, not assumed from naming.)
- `reporting.py` base `export_excel`/`export_pdf` upgraded from a
  file-size-only smoke test to real characterization tests
  (`tests/test_core.py`): sheet names, header rows, summary cell values, and
  PDF page count are now locked in.
- `tests/test_modal_scaling.py` gained a case proving the AutoMAC/COMAC DOF
  mask is the *intersection* of each pair's own mask, not a union — this is
  a different code path from risk #2 below and was not a defect.
- `advanced_metrics.py:81` — the `RuntimeWarning: Mean of empty slice` from
  `np.nanmean` over a node with no measured DOF at all is now suppressed
  with `warnings.catch_warnings()`; the resulting `NaN` value is unchanged.
- `project_review.py` — the silent `except Exception: pass`/`continue`
  blocks around session persistence, manual-pair construction, and
  plot-cache refresh were replaced: expected failures (`build_manual_pair`'s
  `ValueError` for "no common DOF") are now caught by that specific type only,
  everything else propagates; genuinely best-effort operations (session
  save/restore, plot cache cleanup/re-render) now log to
  `~/.abaqus_simcenter_modal_comparator/project_review_errors.log` via
  `_log_recoverable_error()` instead of disappearing silently, and a failed
  plot re-render after a manual-review change now appends a visible warning
  to the result instead of leaving a stale-looking report.
- Full suite: 76 → 105 collected test executions (new tests plus a few
  cross-file re-collections that already existed via `from test_core import
  ModalCoreTests`-style imports), all passing, no warnings.

Remaining, not yet done:

- `requirements.txt` still pins only lower bounds (`>=`); no lock file.
- `universal_frf_review.py`'s "missing coherence channels → `mean_coherence
  = 1.0`" behavior (line ~63-67) was confirmed by direct code reading — this
  is the same mechanism as scientific risk #5 below, promoted here because
  it no longer needs "reproduction," only a fix decision. No behavior was
  changed.

## UI/UX backlog from the 2026-08-03 application review

These items were observed in the current Windows interface while reviewing a
seven-pair result (`Mean |frequency error| = 1.27%`, `Mean MAC = 0.930`, full
121-point geometry match). They are presentation/navigation changes only and
must not alter MAC values, frequency pairing, quality-control thresholds, or
manual-review decisions.

### 1. Previous/next matched-pair navigation on Mode shapes

- Add clearly visible **Previous mode** and **Next mode** buttons directly on
  the `Mode shapes` tab so the user does not have to return to the comparison
  table for every pair.
- Show the current position, for example `Pair 2 of 7: Abaqus 9 ↔ Experiment
  5`, beside the navigation controls.
- Navigation order must be exactly the current visible order of accepted
  matched pairs in the comparison table.
- Changing the pair from the `Mode shapes` tab must update the table selection,
  the mode title, all three figures, and the active manual-review pair through
  one shared selection state; do not implement an independent second index.
- Disable `Previous` on the first pair and `Next` on the last pair. Reanalysis,
  project restore, and manual pair changes must reset/synchronize this state
  without stale plots.
- Add regression tests for first/middle/last navigation, table synchronization,
  and empty/single-pair results.

### 2. Restore comparison-table headings and make the table responsive

- The current result table can display values while all column captions are
  blank. Restore the headings after the complete `install_*()` UI patch stack,
  session restore, and reanalysis. The final runtime headings must include the
  existing mode, frequency, signed error, MAC, order-change, mapped-point,
  status, source, confidence, and manual-decision columns.
- Add a runtime/GUI regression test that inspects the final assembled
  `Treeview.heading(..., "text")` values rather than testing only an earlier
  pre-patched widget constructor.
- Make the table respond to window width. Distribute extra width among useful
  text columns, preserve sensible minimum widths for numeric columns, and
  prevent the rightmost source/confidence/manual-decision columns from being
  silently clipped.
- Provide a horizontal scrollbar when the window is too narrow instead of
  compressing headings to zero width. The table must remain usable at the
  minimum application size, the default `1500x900` size, and a maximized
  desktop window.
- Keep heading text, rows, and both scrollbars visible when the main window or
  notebook tab is resized. Add layout tests for shrink and grow events.

### 3. Combine the three AutoMAC/COMAC views into one responsive tab

- Replace the nested `Abaqus AutoMAC`, `Experimental AutoMAC`, and `COMAC map`
  sub-tabs with one `AutoMAC & COMAC` dashboard that shows all three figures at
  the same time.
- On a wide window, use a three-panel layout. On a narrower window, reflow to a
  readable `2 + 1` or vertical layout instead of shrinking the figures to
  illegibility. Preserve each figure's aspect ratio and existing full-size and
  export actions.
- Show the interpretation summary (`Abaqus AutoMAC max off-diagonal`,
  `Experimental AutoMAC max off-diagonal`, mean/minimum COMAC) in a compact
  area that remains visible without consuming most of the plotting space.
- Add the same **Previous mode** / **Next mode** matched-pair controls to this
  dashboard and synchronize them with the comparison table and `Mode shapes`
  tab. AutoMAC and COMAC remain global diagnostics; the active-pair controls
  select the linked pair used by any pair-specific title, interpretation,
  highlighting, or follow-on view rather than recomputing a different global
  matrix.
- Where practical, highlight the active matched pair's diagonal cells in both
  AutoMAC matrices and the corresponding measured points/summary context
  without changing the underlying metric values.
- Add tests for the combined dashboard's three figure widgets, responsive
  reflow, linked pair selection, and image refresh after a manual-review
  change.

### 4. Shared implementation requirement

- Introduce one explicit current-pair navigation/controller API used by the
  comparison table, `Mode shapes`, `AutoMAC & COMAC`, and manual review. Avoid
  adding another order-dependent monkey-patch layer solely for navigation.
- Implement these changes as one reviewable UI slice with before/after layout
  screenshots and tests against the final assembled runtime.
- Do not mark this UI stage complete until it is checked manually on Windows
  at 100%, 125%, and 150% display scaling, because Tk font scaling can reproduce
  blank/clipped headings even when fixed pixel-size tests pass.

## Scientific risks requiring reproduction

Raised by review but **not yet confirmed** against this codebase's actual
runtime behavior. Each needs a reproducing test *before* any algorithm
change — see Stage 2 below. Do not treat these as established bugs until a
red test exists.

1. **Multi-reference FRF grouping.** Claim: FRFs are grouped by a key that
   already includes `ref_node`/`ref_dir`, so a selected group is always
   single-reference and CMIF's multi-reference path can never see more than
   one reference — making the multi-reference candidate path effectively
   dead code for genuine multi-reference UFF files.
2. **Union DOF mask across experimental modes.** Claim: MAC masking unions
   measured DOF across the whole experimental set (`union |= mapped_mask`)
   rather than using each experimental mode's own mask, so a channel missing
   in one mode but present in another could be treated as measured for both.
3. **Geometric outliers still enter MAC.** Claim: points outside the
   geometry-mapping tolerance, and duplicate points mapped to the same FE
   node, still contribute to MAC after only producing a warning — no
   `distance_mask` filters them out.
4. **No minimum common-DOF/coverage gate.** Claim: a pair is accepted for
   MAC as soon as `np.any(dof_mask)` is true — a single shared DOF is
   sufficient, with no minimum channel count or coverage fraction.
5. **Missing coherence reads as perfect coherence — confirmed at the code
   level.** `universal_frf_review.py` (`modes_from_frf_datasets`): when
   `coherence_rows` is empty, `mean_coherence = np.ones_like(x_reference,
   dtype=float)` rather than an "unavailable" state; downstream this can read
   as `High peak confidence`. The *code path* is confirmed by direct
   reading; what is still open is (a) a test exercising the zero-coherence-
   channels case end to end (existing tests only cover the
   all-channels-present case) and (b) the fix itself — introducing a
   tri-state `computed`/`unavailable`/`error` status without breaking the
   `_frf_mean_coherence` consumers in `enhanced_reporting.py` and
   `universal_hardening.py`.
6. **Partial/off-center experimental grids.** Claim: geometry alignment
   centers both point clouds on their own bounding-box centers before
   searching scale/axis order/sign, which can misplace a grid covering only
   one corner or half of the part.

None of these are known to affect the user's current full 121-point
single-reference dataset — the program was iterated against exactly that
input. They matter for claiming broader (multi-reference, partial-grid,
missing-coherence) correctness.

## Architecture debt

- `main.py` assembles the app through ~20 order-dependent `install_*()`
  monkey-patch layers (see `main.py:11-70`); `runtime_contracts.py` exists
  only to catch a reordering that silently changes which module owns a given
  function, and its own docstring calls itself a temporary guard pending
  these layers being folded back into explicit components.
- `modal_core.py`, `quality_control.py`, `reporting.py`, `ui_enhancements.py`
  and others have been reduced to thin facades over later-named files
  (`reviewed_core.py`, `quality_control_reviewed.py`,
  `final_reporting_review.py`, ...). Editing an early-named file can have no
  effect if a later layer overwrote the function at import time.
- `project_review.py` (~770 lines) mixes project persistence, manual-review
  domain logic, GUI tab code, and report audit trail in one file.

Planned approach: fold one vertical slice at a time into an explicit
component (reporting first), keep the old names as temporary facades during
the transition, and only delete `runtime_contracts.py` checks once the
corresponding patch chain is actually gone. See Stage 4 below.

## Release and reproducibility gaps

- No Windows CI (only `ubuntu-latest` in `.github/workflows/tests.yml`),
  despite the app being Windows/Tkinter/Abaqus-`cmd.exe` oriented.
- No dependency lock file, no minimum/maximum version pins.
- No application version surfaced in the GUI, project file, or reports.
- No changelog/release notes, no `LICENSE`, no `pyproject.toml`/packaging.
- No offline installer path for a lab machine without internet access.
- No way to cancel a running Abaqus extraction from the GUI.
- No headless/CLI batch mode for processing multiple specimens.
- No compatibility matrix (Abaqus version range, Testlab/pyuff variants).
- Reports do not currently record input file hashes, library versions,
  Abaqus version, thresholds used, or manual-review state as a reproducible
  fingerprint of the run that produced them.

## Staged plan

- **Stage 1 — lock in current behavior.** This file; direct tests for the
  untested modules above; characterization tests over the Excel/PDF export
  chain; fix the empty-slice warning; replace silent excepts in
  `project_review.py` with typed/logged handling. No numerical behavior
  changes.
- **Stage 1B — implement the 2026-08-03 UI/UX review backlog.** Add shared
  previous/next pair navigation, restore final-runtime table headings, make
  the table responsive, and combine all AutoMAC/COMAC views into one linked,
  responsive dashboard. Keep numerical results unchanged and verify the final
  assembled UI on Windows and multiple display scales.
- **Stage 2 — reproduce scientific risks.** For each item above, write a
  reproducing test first. Report which are confirmed, which don't reproduce,
  and only then fix confirmed ones — each fix ships with its test and a
  before/after comparison on the reference dataset.
- **Stage 3 — implement UNV dataset 2420 local coordinate-system
  transform.** Currently detected and warned about, never applied.
- **Stage 4 — fold the `install_*` patch chain into explicit components**,
  one vertical slice at a time, starting with reporting, verified by the
  Stage 1 characterization tests at every step.
- **Reproducibility work** (lock file, version stamping, Windows CI,
  offline installer, CLI, cancellation) proceeds alongside, lowest risk
  first.

Do not change MAC/frequency admissibility thresholds, or the existing
reference dataset's automatic assignment, without a dedicated regression
test proving the change is intentional.
