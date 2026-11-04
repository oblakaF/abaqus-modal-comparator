# GUI-UX-R1-F1: final GUI correction

For reviewers and engineers using the program. Base: `d6e5d4d`. It corrects GUI defects the owner found. No scientific
algorithm, threshold, registration rule or project format changed.

## FE white gaps: what was found

Geometry files of the two local real packages were checked directly, with several modes of each.

| Candidate cause | Finding |
|---|---|
| True holes in the mesh | None. The plate is a full 101 x 101 grid. The sandwich's skins cover the whole 510 x 520 panel at 3 mm |
| Empty raster cells | **The cause.** The display cell was 2.948 on a 3 mm skin mesh. Whole rows held no node, and the old limit let up to 0.5 % such gaps through |
| Same places in every mode | Explained by the above: the empty cells depend only on the geometry, so all modes share one mask |
| Projection | The best-fit plane is rotated 4.9° on the sandwich, so 13.5 % of its box lies outside the rotated outline. That area is outside the panel, not a hole |
| Through-thickness averaging | Does not cause gaps. It remains a limit: up to about 270 nodes share a cell, and a component that reverses through the depth averages toward zero. The caption states it |
| Old saved PNGs | Earlier pictures inside a `.mcproj` keep their gaps. They are shown as stored, and the note beside them says so |

The grid now coarsens until no empty run of one to three cells lies between occupied cells. A wider empty region counts as a real
hole and stays blank. Every drawn value is a mean of real nodes, and nothing is interpolated. The experimental view's colour
between points is contour drawing, and its caption now says it is for display only.

| Model, source axes | Grid | Cell | Empty cells | Modes drawn |
|---|---|---|---|---|
| Plate | 97 x 97 | 3.10 | 0 | 7, 8, 12, 17 |
| Sandwich | 167 x 170 | 3.05 | 0 | 7, 8, 9 |

The mask is the same for all modes drawn. The sandwich's picture is coarser than a fine mesh could give, because its 3 mm skins set
the common cell.

## Orientation

Each fresh shape view has **View**: Source axes (default), Source XY, XZ or YZ, or Best-fit plane, and **Rotate** and **Mirror**.
Axis labels name the source axis and say that the source states no length unit. These controls change the picture only: no
coordinate, registration, MAC or pairing reads them. Nothing rotates by itself. A saved picture has no such controls.

New project saves draw on source axes. The project format is unchanged.

## Other corrections

- **Review table:** an eighth column, Actions, holds a Swap button on each row with a next row. Reset Row and Reset All are small
  controls outside the table. Conflicts are one short line and a tinted cell.
- **Wheel:** an application event filter stops the wheel changing tabs and closed lists, in all pages and dialogs of this window. An
  open list still scrolls itself.
- **Plots:** engineering labels, an explanation of the equality line, and an outline for the selected row.
- **FRF:** named markers with frequencies. Peak records are triangles and fitted modes are dashed lines, with the selected record in
  orange. Coherence stays on its own axes. If there is no curve, the page says why.
- **All tables:** they fill the pane, scroll by themselves and select their own rows.
- **Copy Image and Save PNG:** on shapes, saved shapes, plots, FRF, MAC, pair pictures, line profiles and the measured-point layout.
  They use the original PNG and are disabled without one.
- **MAC / Points:** the measured points and DOFs are shown independently of any registration. "Registered points" holds the
  FE-to-EXP correspondence.
- **Analyze:** a Loaded data table states the files, modes, sets, record type and what is available.
- **Materials:** states whether an FE package was found, and whether an INP or CAE exists but was not parsed.

## Limits

- Materials still shows no material property: no parser for INP or CAE is added.
- Source axes do not align the two models. Alignment needs a registration.
- Manual choices stay session-only, as in `GUI_UX_R1.md`.
- Pictures inside old projects are not redrawn.
- The wheel filter covers the program's window and its dialogs, not the research window.

## GUI-UX-R1-F2: the two defects of the F1 visible run

- **Mode shapes open scrolled down: corrected.** The cause was focus. Analyze going disabled moved the keyboard focus into the pane,
  and Qt scrolled to the focused widget. A new analysis or opened project now selects Mode shapes at the top and gives the table
  the focus. The Show shape button takes no focus, because it is disabled during each redraw. Ordinary redraws keep the scroll.
- **FRF labels overlapping: corrected.** Close labels are spread apart at no less than one label's width, with a thin leader to the
  record's own frequency. Only the label moves: peak marks, frequencies, FRF values and coherence are unchanged. The selected
  record's label stays bold.

### What was checked

Automated, one completed run on the final code: 18 tests, OK, 90 s. They cover both corrections and the regression interrupted in F1
(`SaveAndReopenTests`).

The visible run confirmed both corrections on real data: the top of Mode shapes on a fresh result and on an opened project, and
separated FRF labels with EXP 5 selected.

**Not verified in that run, because of errors in the driving script:** a real click on Swap, operating View, Rotate and Mirror, the
wheel over an in-table mode selector, and scroll kept after a redraw. Offscreen tests cover Swap and the scroll, and the wheel filter
through a sent event; these are not visible checks. Rotate was exercised offscreen in the F1 tests, not re-run in F2.
