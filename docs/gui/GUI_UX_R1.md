# GUI-UX-R1: engineering modal comparison workflow

For reviewers and engineers using the program. Base: `4d8f914`. Code: `src/new_gui/review_model.py`, `review_panel.py`,
`mac_points_model.py`, `mac_points_panel.py`, `materials_workspace_model.py`, `materials_workspace.py`, with changes in
`analyze_panel.py`, `analyze_model.py`, `production_window.py`, `shape_panel.py`, `shape_model.py` and
`services/modal_data_viewer.py`. Tests: `tests/test_gui_ux_r1.py`.

## Pages

| Page | Holds |
|---|---|
| Analyze | The two files, the modal set, the mode range, Analyze and Cancel, Open, Save and Save As, and a saved result's source check |
| Review | The status, the frequency table with manual candidate choices, mode shapes, frequency plots, the FRF spectrum and all tables |
| MAC / Points | The evidence levels, why MAC is missing, the registration commands, pairs, MAC, points, mapping diagnostics, line profiles |
| Materials | Its own two files, read-only facts, what is missing, the scientific status and the future workflow |

A successful analysis and an opened project both go to Review. A comparison started on MAC / Points stays there, and a failure
returns to Analyze. Messages also appear in the status bar, so Save from the menu no longer leaves the page. The Review panes
and each tab scroll by themselves.

The research window (`--research`, `new_gui.window.MainWindow`) keeps the old single-column arrangement of `AnalyzePanel`.

## The frequency table

Columns, in this order: row, EXP mode, EXP frequency, selected FE mode, selected FE frequency, Δf (%), nearest FE mode.
`Δf (%) = 100 × (f_FE − f_EXP) / f_EXP`. It is labelled a frequency-based candidate comparison.

The automatic cells are the frequency diagnostic's own text, as computed or saved. A manual choice:

- offers elastic FE modes only, and keeps the original mode numbers and the automatic suggestion;
- updates the selected frequency and Δf, using full-precision frequencies when known;
- is marked `USER_REVIEW_HYPOTHESIS` by the tint, the tooltip, the line below the table, the plots and MAC / Points;
- asks when the FE mode is taken already: swap, keep both with a diagnostic warning, or cancel. An automatic duplicate is
  also stated;
- can be reset per row or for all rows;
- reaches nothing else. The `Analysis`, its pairs, MAC and status, the saved project, registrations and gates do not read it.

## Saved projects versus source data

| Function | From a saved `.mcproj` | Needs the source files |
|---|---|---|
| Frequency table, manual choices, frequency and difference plots | Yes | |
| FE and experimental tables, status, warnings | Yes | |
| Mode shape, magnitude | Saved picture | |
| Mode shape, other components | | Yes |
| FRF spectrum | | Yes, and only if the file holds dataset 58 |
| Pair table, MAC table and picture, coverage, mapping diagnostics | Yes, when a comparison was saved | |
| Point correspondence, pair pictures, line profiles | | Yes, with the comparison repeated |

Opening still touches no path named in the project, and Analyze stays blocked until Check source files confirms the content.

## Project format: no change; compatibility plan

Schema `universal/analysis-project/v1` is unchanged, and files written by this version are readable by the previous one. Its
reader refuses unknown fields, so manual choices are not saved: they last for the session, and the page says so.

If they should be kept, a later authorized task would:

1. add `universal/analysis-project/v2` with one separate `review` member holding row, EXP mode, FE mode and the tag;
2. keep reading v1 unchanged, and never rewrite a v1 file without Save As;
3. keep `review` out of `result`, `comparison` and `registration`, so it cannot affect a status;
4. let v1 programs refuse v2 by name, as they already do.

## FE drawing artifact: the actual cause

`modal_data_viewer.render_mode` averaged large FE models on a fixed 220-cell display grid, whatever the node spacing. When a
cell is smaller than the mesh pitch, most cells hold no node and are drawn blank, which gives a dotted or striped field.
Measured from the geometry files only, on the local review copies:

| Model | Nodes | Fixed grid: cell, empty cells, holes per occupied cell | New grid: cells, cell, empty cells, holes |
|---|---|---|---|
| Plate, regular 3 mm mesh | 10 201 | 1.37, 78.8 %, 1.61 | 90, 3.34, 0 %, 0 |
| Sandwich, three-dimensional mesh | 1 585 637 | 2.55, 23.1 %, 0.14 | 176, 3.19, 13.5 %, 0 |

The grid now starts at 220 cells and coarsens until holes are at most 0.5 % of the occupied cells. A hole is an empty cell with
occupied cells on both sides. Every drawn value is still a mean of real nodes, and a cell that stays empty, such as a cut-out
or the outside of the model, stays blank. Nothing is interpolated. The caption states the grid.

Two further limits remain and are stated, not changed:

- **Through-depth averaging.** On a thick model all nodes through the depth share one cell, up to 276 in the sandwich. A
  component that reverses through the depth, such as in-plane displacement in bending, is averaged toward zero. The caption
  says so when the model has depth.
- **Display projection.** Each picture uses the best-fit plane of its own data set. On a nearly square model the two principal
  directions are close, so the in-plane orientation may be arbitrary. The FE and experimental pictures are not aligned, and
  the page says so. Nothing is rotated to fit.

Pictures inside existing projects keep the old drawing. A new Save uses the new one.

## MAC / Points

Every value comes from the comparator's result or the saved comparison. The page separates four evidence levels: frequency
candidates, MAC diagnostics, user-confirmed registration and physically validated archived evidence. Without a registration it
gives one reason and shows no MAC, pair or point. No old registration is imported for other geometry.

A line profile uses mapped points that share the two other coordinates in the registered common system. It needs at least three
points and a component measured on all of them. One complex scale, fitted over all mapped DOFs of the pair, is applied for
display. No MAC is shown per point.

## Materials

The FE facts come from an already extracted package: its manifest and `geometry.csv`. The mode files are not read and Abaqus is
never started. Choosing an ODB hashes it, as Analyze does, to find its package.

**Material data.** The extraction stores no material name, section, layup, E1, E2, G12, density, thickness or unit, so the page
says so and guesses nothing. An ODB can hold such definitions, but no reader for them exists here. Showing them needs a separate
INP or CAE source, or an extended ODB extraction with Abaqus Python, which is a separately authorized task. Files with the ODB's
name beside it are named, not opened.

**Scientific status.** No optimizer, FE iteration, solver or production Auto-ID was added or run, and no number is issued. SPEC
v1.2, D-077 and the M8 gate are unchanged. The calibration workflow is shown as future text only.

## Other usability changes

- `FRF peak — not fitted` replaces the long provisional label in tables and compact shape views. The full wording stays in the
  tooltip and the data, and Review gives one explanation.
- The wheel over a closed choice in the program's mode, record, component and modal-set lists changes nothing and scrolls the
  page or table instead.
- X, Y and Z are offered only where the importer recorded measured DOFs or data for that record.
- Changing a shape's mode, record or component redraws it on Review.

## Limits

- Units: the source data read here state no length unit, so none is shown.
- A picture's height depends on its width and a scroll bar changes that width, which caused a stack overflow in the Frequency
  plots layout during development. `ImageView` now keeps its height when it shrinks by at most 24 pixels, with a reproducing test.
- FRF drawing was tested with stored indicator arrays, not with a real dataset 58 file in the GUI.
- Line profiles were tested with synthetic data only.
- `test_universal_ui2_clean.py` still bans research wording, with three allowed phrases this task requires.
