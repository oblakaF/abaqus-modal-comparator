# Runtime UI audit and responsive workflow

## Scope and scientific boundary

This change audits and hardens the desktop UI assembled by `RUN_PROGRAM.cmd` and `src/main.py`. It does not change MAC mathematics, frequency or coverage gates, Hungarian assignment, FRF extraction mathematics, modal-cluster mathematics, Stage-A inversion/sensitivity/matrix formulation, scientific acceptance criteria, or any Stage-B code. A zero-pair result remains a diagnostic result and is never promoted to success.

## Actual startup and installation order

`RUN_PROGRAM.cmd` changes to the repository directory, creates/reuses `.venv`, runs `src/ensure_dependencies.py`, and starts `src/main.py`. `src/main.py` installs runtime layers in this exact order:

1. `universal_hardening.install_universal_hardening`
2. `universal_frf_review.install_frf_review`
3. `cmif_separation.install_cmif_separation`
4. `cmif_validation.install_cmif_validation`
5. `fast_cache.install_fast_cache`
6. `performance_tuning.install_performance_tuning`
7. `reporting_hardening.install_reporting_hardening`
8. `amplitude_correlation.install_amplitude_correlation`
9. `metrics_normalization.install_metrics_normalization`
10. `enhanced_reporting.install_reporting_enhancements`
11. `advanced_reporting.install_advanced_reporting`
12. `final_reporting_review.install_final_reporting_review`
13. `ui_enhancements.install_app_enhancements`
14. `runtime_hardening.install_runtime_hardening`
15. `advanced_ui.install_advanced_ui`
16. `amplitude_correlation.install_correlation_ui`
17. `figure_export_ui.install_figure_export_ui`
18. `cmif_ui.install_cmif_ui`
19. `cmif_validation_ui.install_cmif_validation_ui`
20. `pair_plot_cache_ui.install_pair_plot_cache_ui`
21. `final_ui_polish.install_final_ui_polish`
22. `responsive_images.install_responsive_images`
23. `project_review.install_project_review`
24. `project_review_polish.install_project_review_polish`
25. `help_ui.install_help_ui`
26. `menu_ui.install_menu_ui`
27. `idle_ui_state.install_idle_ui_state`
28. `responsive_status_bar.install_responsive_status_bar`
29. `ui_workflow.install_responsive_workflow`
30. `runtime_contracts.verify_runtime_contracts`

The outermost final `__init__` chain is therefore `ui_workflow -> responsive_status_bar -> idle_ui_state -> menu_ui -> help_ui -> project_review -> responsive_images -> ModalComparatorApp`. The active `_build` chain is `cmif_ui -> figure_export_ui -> advanced_ui -> ui_enhancements -> ModalComparatorApp`.

## Final runtime ownership

| Area | Final owner or modifier | Notes |
| --- | --- | --- |
| Root window, initial geometry and minimum size | `ModalComparatorApp.__init__`, then `ui_workflow.workflow_init` | Base requests `1500x900`, minimum `1160x720`; final policy uses `1400x860`, minimum `900x650`, and DPI awareness is enabled before `Tk()` on Windows. |
| Notebook and base tabs | `ModalComparatorApp._build` | Creates Files, Comparison, Shapes, MAC/Frequencies, Details. |
| FRF tab | `ui_enhancements.enhanced_build` | Inserts tab 5. |
| AutoMAC/COMAC tab | `advanced_ui.advanced_build` | Inserts before Details. |
| Close modes tab | `cmif_ui.cmif_build` | Inserts before AutoMAC. |
| Manual Review tab | `project_review.reviewed_init` | Installed after `_build` completes. |
| Final nine-tab order and responsive labels | `ui_workflow.apply_responsive_layout` | Full labels in Wide; guaranteed compact labels in Medium/Compact. |
| Input/files tab | `ui_workflow.build_input` | Final sectioned, scrollable SOURCE FILES / ANALYSIS / ABAQUS / GEOMETRY & UNITS / OUTPUT layout. |
| Abaqus configuration | `ui_workflow` | Actual launcher discovery, selection, Browse, Advanced command and non-analysis availability test. |
| Coordinate-scale configuration | `ui_workflow`, passed to `runtime_hardening.hardened_worker` | Unit-based normal workflow; numeric custom scale appears only in Custom mode. Existing alignment implementation receives the derived positive scale. |
| Run action and UI analysis state | `ui_workflow.start_analysis` | Owns Run/Stop button states and explicit NO DATA through ERROR status states. |
| Worker thread | `ui_workflow.start_analysis` starts `runtime_hardening.hardened_worker` | `_worker.__module__` remains `runtime_hardening`, as guarded by `runtime_contracts`. |
| Abaqus subprocess | `abaqus_bridge.run_abaqus_extraction` | Uses `Popen`, records the owned handle, polls cancellation, and writes a persistent extraction log. |
| Cooperative cancellation | `runtime_hardening.hardened_worker` and `ui_workflow` | Checks between six coarse stages and between plot renders; cancellation never calls `_complete`. |
| Project/session persistence | Base implementation in `project_review`, final behavior in `ui_workflow` | Explicit project Save/Save As is distinct from debounced recovery data. |
| Comparison table construction | `final_ui_polish.polished_build_table -> cmif_validation_ui.reviewed_build_table -> ModalComparatorApp._build_table` | Source/Confidence are added inside `_build_table`; Manual/Comment are added later by `project_review.reviewed_init`. |
| Final Comparison headings and widths | `ui_workflow.finalize_tables` | Runs after all 13 runtime columns exist. |
| Comparison population | `ui_workflow.populate -> project_review -> cmif_validation_ui -> cmif_ui -> figure_export_ui -> advanced_ui -> runtime_hardening -> ui_enhancements -> ModalComparatorApp` | Final layer converts metric labels to card values and renders an explicit zero-pair diagnostic state. |
| Top metric summary | `ui_workflow.rebuild_metric_cards` / `populate` | Four responsive blocks; diagnostic replaces the fourth value with an explicit state instead of implying success. |
| Plots/images | Rendering remains in reporting/advanced/CMIF modules; display owner is `responsive_images.responsive_image` | Source images are cached and aspect-fit to the current label on resize/tab changes. |
| Manual Review | `project_review` with final table/layout/text behavior from `ui_workflow` | Automatic and manual decision columns remain separate; comment and decision changes mark the project dirty. |
| Details | Built by `ModalComparatorApp`; content wrappers end at `project_review.reviewed_details`; clipboard policy from `ui_workflow` | Read-only Copy and Select All remain available. |
| Status bar | Built by `ModalComparatorApp`, reordered/resized by `responsive_status_bar`, text/state owned by `ui_workflow` | Footer is packed before the expanding notebook; stage text shares space with a bounded progress indicator. |
| Close-window handler | `ui_workflow.close_requested` | Replaces `project_review.close_with_session_save` as the final `WM_DELETE_WINDOW` protocol. |

## Missing-heading root cause

The defect is an installation-order regression, not missing source strings.

1. `ModalComparatorApp._build_table` creates nine columns and configures all nine headings.
2. `cmif_validation_ui.reviewed_build_table` later calls `table.configure(columns=...)` to append Source and Confidence. Reassigning Treeview columns can clear heading options; it then configures only the appended headings.
3. `final_ui_polish.polished_build_table` correctly restores the eleven headings known at that point.
4. After the full `_build` returns, `project_review.reviewed_init` calls `_install_manual_columns`, reassigns `columns` again to append Manual decision and Comment, and configures only those two new headings.
5. Consequently, early headings may be blank while the newest headings remain visible.

The fix deliberately runs after the complete `__init__` wrapper chain. It enumerates the final active columns and assigns a non-empty heading, width, minimum width, anchor and stretch policy to every column. A fallback title is assigned to any future unknown column. Regression tests cover both the centralized specification and the runtime widget when Tk is available.

## Duplicated/conflicting responsibilities found

- `_build`, `_populate`, `_show_pair`, `_details`, `_image`, `_build_input`, `_build_table`, `_complete`, and `__init__` are each owned by multiple closures. Behavior depends on capture time and exact install order.
- Root sizing was fixed in the base class even though later wrappers add four tabs, multiple action bars and a status footer.
- `final_ui_polish` attempted to be the final table owner, but `project_review` changed columns later from an `__init__` wrapper.
- `runtime_hardening` added a raw `auto`/numeric coordinate field after the base input layout, while project persistence also serialized that implementation string.
- Abaqus execution lived in an uninterruptible `subprocess.run`; the UI only had a boolean `running` flag and no process ownership.
- `project_review` always wrote/restored a last-session file and destroyed the root on close; it did not track dirty state or distinguish recovery from explicit Save.
- `menu_ui` bound Ctrl+S globally, but Save As had no accelerator and the app had no consistent text-edit binding/context-menu policy.
- Fixed `wraplength` values (`1200`, `1300`), fixed table widths, horizontally packed actions and descriptive tab names competed for space at smaller widths and higher Windows scaling.
- Comparison and Manual Review had vertical scrollbars but no horizontal scrollbar. The experimental-candidate dialog originally had neither a complete two-axis scroll layout nor the final scientific headings.
- Style definitions were split between base widgets and individual wrappers, with ad-hoc fonts and spacing.

## Concrete defects and applied UI corrections

- Minimum width blocked the requested 1024-class viewport: reduced the hard minimum and made the input page vertically scrollable.
- Nine long tab labels could run past the right edge: compact labels activate below the Wide breakpoint.
- The metric summary was one packed sentence row: replaced with four semantic metric cards using a 4-column or 2-by-2 grid (and one column below 720 logical pixels).
- A zero-pair result could look like an empty failure: it now shows `0`, unavailable metric placeholders, `Diagnostic — gates not satisfied`, and explicit scientific-gate status text.
- Source paths and help text could dictate window width: entries now expand while Browse remains in a fixed trailing column; help wraplength is recalculated on debounced resize.
- Normal users had to type `auto`, `0.001` or `1000`: unit selection now computes the conversion, labels the Abaqus field exactly `Abaqus model length unit`, and exposes numeric input only for Custom scale.
- The command field assumed an alias: detection only lists launchers found with `PATH`/`PATHEXT` or existing launcher files; zero/one/multiple discovery states are distinct.
- Run had no real Stop: the worker now uses a cancellation event and the Abaqus bridge owns a `Popen` handle; Windows termination targets only that PID tree.
- Close could orphan work: active analysis requires `Stop and close`; the app waits for the cancellation callback and remains open on timeout.
- Text editing was inconsistent: Entry, Spinbox, Combobox and Text class bindings implement Ctrl+C/V/X/A, while context menus expose editable or read-only commands as appropriate.
- Save behavior was unpredictable: persistent fields and manual decisions drive a snapshot-based dirty flag; Save/Save As reset it only after a successful write.
- Recovery masqueraded as Save: recovery has separate preferences, a debounced file, explicit recovered-session text and a one-time controllable notice.
- Dense tables were compressed: columns retain scientific minimum widths and use connected horizontal and vertical scrolling rather than hiding fields.
- Blank pre-analysis panels were ambiguous: the comparison/review tables and existing plot labels now state the action or data required.
- Plot sizing could become stale after tab/viewport changes: the existing `responsive_images` aspect-fit path remains final and is explicitly refreshed after responsive layout changes.

## Central responsive policy

`src/ui_policy.py` is the single source for breakpoints, tab labels, metric and button grid sizes, wrap widths, padding, table headings/minimums, style tokens, unit conversion, installation selection, analysis states, dirty-state snapshots and close decisions.

- WIDE: width at least 1500 logical pixels; full tab labels; four metric columns.
- MEDIUM: 1120–1499; compact tab labels; two metric columns; action rows wrap to at most three columns.
- COMPACT: below 1120; compact tab labels; two metric columns (one only below 720); actions wrap to two columns.

Resize handling is debounced at 90 ms. It does not resize the root, call `update()` recursively or perform rendering inline. Plot refresh is queued after idle, preserving aspect ratio and avoiding hidden-tab 1-by-1 geometry.

## Analysis states and progress

The visible states are NO DATA, READY, RUNNING, STOPPING, STOPPED, SUCCESS, DIAGNOSTIC and ERROR. Progress is coarse and stage-based rather than a fabricated percentage:

1. Abaqus extraction
2. Experimental import
3. Geometry alignment
4. Modal comparison
5. Plot generation
6. Report data generation

Cancellation is checked between stages and between plot renders. An Abaqus launcher is started with `Popen`; only the stored application-owned process tree is terminated. A cancelled run cannot schedule successful completion, clears partial result presentation, leaves logs/cache files available for diagnosis, and returns Run to an idle state.

## Remaining technical debt and follow-up architecture PR

The wrapper stack remains order-sensitive by explicit scope decision. The next architecture PR should introduce composed owners without changing scientific services:

```text
ModalComparatorApp
  InputTab
  ComparisonTab
  ModeShapesTab
  MacTab
  FrfTab
  CloseModesTab
  AutoMacTab
  ManualReviewTab
  DetailsTab

  AnalysisController
  ProjectController
  StatusController
```

That PR should replace closure capture with explicit construction hooks, give each Treeview one schema owner, make tab/action registration declarative, route result publication through `AnalysisController`, and make project/recovery/close decisions the sole responsibility of `ProjectController`. It should preserve the current runtime contracts and scientific service boundaries while migrating one UI surface at a time.

## Validation performed for this change

- The full automated suite was run, including all scientific regression tests.
- A native Tcl/Tk 8.6.15 runtime smoke test instantiated the exact `src/main.py` assembly outside the filesystem sandbox.
- The assembled app exposed all nine tabs and all 13 final Comparison columns with non-empty headings.
- Comparison and Manual Review both reported connected horizontal and vertical scroll commands.
- The native root was repeatedly resized through 1920x1080, 1600x900, 1366x768, 1280x720, and 1024x700; every tab was selected at each pass without a Tk exception.
- The compact policy activated at 1024x700, and all nine compact tab labels remained present.
- A long path Entry and the disabled Details Text were exercised through Select All and Copy dispatch.
- A zero-admissible-pair `ComparisonResult` was rendered through the assembled population chain and showed the explicit diagnostic metric state.
- Abaqus discovery found the existing `abq2024.bat` and `abaqus.bat` launchers rather than assuming either alias. The `Test Abaqus` implementation successfully ran `information=release` against Abaqus 2024 without starting an FE analysis.
- DPI normalization is tested at 100%, 125%, and 150% scaling equivalents. A human visual pass on three separately configured Windows displays remains part of the checklist below; no screenshot pixel-comparison test was introduced.
- Real ODB extraction was intentionally not launched for this UI PR. Owned-process-tree termination and cancellation callbacks are deterministic tests; the manual real-job Stop checks remain below.

## Manual acceptance checklist

### Window

- [ ] 1920x1080
- [ ] 1600x900
- [ ] 1366x768
- [ ] 1280x720
- [ ] ~1024x700
- [ ] maximize -> restore
- [ ] repeated resizing
- [ ] 100% DPI
- [ ] 125% DPI
- [ ] 150% DPI

### Input

- [ ] very long ODB path
- [ ] very long UNV path
- [ ] Browse buttons visible
- [ ] no manual typing of `auto`
- [ ] mm -> m is understandable
- [ ] custom scale remains possible
- [ ] Abaqus detected automatically
- [ ] normal user does not need to type `abaqus`

### Clipboard

- [ ] Ctrl+C
- [ ] Ctrl+V
- [ ] Ctrl+X
- [ ] Ctrl+A
- [ ] right-click Cut/Copy/Paste
- [ ] Details Copy
- [ ] Manual Review comment editing
- [ ] long path editing

### Analysis

- [ ] Run
- [ ] Stop
- [ ] Stop during Abaqus extraction
- [ ] Stop during Python processing
- [ ] close while running
- [ ] rerun after Stop

### Project

- [ ] Save
- [ ] Save As
- [ ] Ctrl+S
- [ ] Ctrl+Shift+S
- [ ] dirty close -> Save / Don't save / Cancel
- [ ] clean close -> no prompt
- [ ] recovery enabled
- [ ] recovery disabled
- [ ] Don't show again works

### Tables

- [ ] all headings visible
- [ ] horizontal scrolling
- [ ] vertical scrolling
- [ ] Comparison
- [ ] Manual Review
- [ ] zero-pair diagnostics
- [ ] Close modes
- [ ] other tables

### States

- [ ] no data
- [ ] ready
- [ ] running
- [ ] stopping
- [ ] stopped
- [ ] successful comparison
- [ ] zero-pair diagnostic
- [ ] real program error

### Plots

- [ ] MAC
- [ ] frequency comparison
- [ ] mode shapes
- [ ] FRF
- [ ] resize while visible
- [ ] switch away and back
