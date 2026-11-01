# Abaqus–Simcenter Modal Comparator

A Windows desktop application for comparing Abaqus modal results with Siemens LMS / Simcenter Testlab measurements.

The normal workflow requires only:

- Abaqus `*.odb`;
- Simcenter Testlab `*.unv` or `*.uff`.

No manual frequency entry or Abaqus screenshots are required.

## Main functions

- Opens the ODB through the Python interpreter supplied with Abaqus.
- Extracts mode numbers, frequencies, FE coordinates, and complex `U1/U2/U3` vectors.
- Reuses a valid ODB extraction cache when the ODB, mode range, and Abaqus command have not changed.
- Reads UNV/UFF geometry datasets 15/2411.
- Reads curve-fitted modal datasets 55 and 2414 with tolerant key/scalar handling for pyuff variants.
- Reads raw complex FRFs from dataset 58 and derives resonance-peak shapes when a curve-fitted modal dataset is absent.
- Reads coherence, estimates peak damping, and reports the limitations of peak-derived shapes.
- Detects measured experimental degrees of freedom and calculates MAC only on those DOFs.
- Aligns coordinate scale, axis order, and axis signs; a manual scale override is available.
- Reports duplicate nearest-node mappings and reflected coordinate transformations.
- Applies frequency/MAC admissibility limits before one-to-one assignment, so a bad pair cannot consume a good partner.
- Retains the sign of frequency error:
  - positive: Abaqus frequency is higher than experiment;
  - negative: Abaqus frequency is lower than experiment.
- Detects mode-order changes only within accepted matched pairs.
- Calculates full MAC, verified-pair MAC, AutoMAC, and COMAC.
- Displays mode-shape fields, a shared-scale correlation plot, FRF/coherence diagnostics, and frequency regression.
- Exports Excel and PDF reports.

## First launch on Windows

Double-click:

```text
RUN_PROGRAM.cmd
```

The launcher creates a local `.venv` environment and installs the required packages. The first launch can take several minutes.

### New interface preview (NEW-GUI)

A separate PySide6 (Qt) window is being built next to the existing program. Start it with:

```text
RUN_NEW_GUI.cmd
```

The launcher uses the same `.venv` and also installs PySide6 from `requirements-new-gui.txt`, which the existing program
does not need. Without the launcher, run `python -m pip install -r requirements-new-gui.txt`, then
`python -m new_gui` with `src` on `PYTHONPATH`.

The window lets you choose your own FE results file and experimental file, shows what was chosen and opens the
read-only research archive on request (`docs/gui/NEW_GUI1_SHELL.md`). Since NEW-GUI.2, **Inspect file** reads a chosen
file with the same importer chain as the existing program: both call `services.importer_runtime`. It shows the
imported modes, frequencies, modal sets and warnings (`docs/gui/NEW_GUI2_PREVIEW.md`); Inspect file itself runs no
analysis. Since NEW-GUI.3, one chosen FE mode or experimental record can be drawn on its own coordinates
(`docs/gui/NEW_GUI3_SHAPES.md`). Since NEW-GUI.4, the Analysis page runs a frequency-only diagnostic of the read FE
results and one chosen experimental modal set, only when you click **Run frequency diagnostic**
(`docs/gui/NEW_GUI4_FREQUENCY.md`). Its result is FREQUENCY_ONLY_DIAGNOSTIC: the nearest FE frequencies show
frequency proximity only and are not established mode pairs. No physical registration, MAC or Auto-ID is run.
Since NEW-GUI.5, **Check reference registration** checks, only when you click it, whether an accepted archived
physical registration (SP-02, SP-13) applies exactly to the read FE results and the modal set chosen for the frequency
diagnostic (`docs/gui/NEW_GUI5_REGISTRATION.md`). The registration is not applied: no MAC, mode pair or orientation is
made, and modal identity is not established. A refusal does not mean that your experiment is physically wrong.

Since NEW-GUI.6 (`docs/gui/NEW_GUI6_SCIENTIFIC_WORKBENCH.md`), the Analysis page has a scientific workbench. Use it in
this order:

1. Choose and inspect the FE results and the experimental file on the Workspace page.
2. Choose the experimental modal set on the Analysis page.
3. Optionally run the frequency diagnostic.
4. Click **Check reference registration**.
5. Only when the check verifies an archived physical registration for exactly these data, click **Run verified modal
   comparison**. It verifies the registration again and runs the project's comparator (`modal_core.compare_modal_datasets`)
   with that frozen registration. No automatic orientation search runs.

The result shows:

- the comparator's mode pairs: signed frequency error, MAC on the registered measured DOFs, coverage, order changes
  and close modes;
- the full MAC matrix and the unpaired and rejected modes;
- the warnings and the registration provenance;
- the drawing of the pair chosen in the table: FE and experimental shapes on the same registered points, and their
  amplitude correlation.

Without a verified registration (for example the new ROTATED series of 2026-10-29), the shapes stay unpaired
independent views and no MAC exists. **Export report...** writes either the verified comparison report (Excel, PDF and
a JSON record with the sources' SHA-256) or the diagnostic report, into a folder you choose.

The **Materials** page shows the project's existing material records, read-only. It separates material
identification, specimen engineering calibration and model input or diagnostic estimates. It runs no Auto-ID and
creates no material value.

**File > Choose a known new experimental source...** offers the three fitted working sources of the 2026-10-29
delivery. They are checked against `docs/experimental/new_exp_20261029/SOURCE_PROVENANCE.csv` and by SHA-256.

**Working from other folders (WINDOWS-RC1-A, `docs/gui/WINDOWS_RC1_A.md`):**
- In the known-sources dialog, **Choose folder...** points to the delivery folder wherever it lies, or to its
  `SPname_files_ROTATED_261028` subfolder. A file is used only with its declared size and SHA-256; a missing or changed
  file is refused with the reason.
- On the Plate Study page, **Choose FE archive folder...** sets the folder that holds the plate's FE family. Each
  member is verified there by its recorded SHA-256, and a member not found is shown as MISSING. A new folder discards
  the earlier study result.
- **FE input.** The new interface views an extracted FE package: choose its `manifest.json`, with the CSV files
  beside it.
  - An Abaqus `.odb` cannot be viewed in this version of the new interface, and choosing one starts no Abaqus.
  - `RUN_PROGRAM.cmd` keeps its own ODB route.

**Research Results** (PRIORITY-5A, `docs/gui/PRIORITY5_RESEARCH_RESULTS.md`) shows the archived research results of
PRIORITY-1–4 for PLATE (261027), SP-13 (261028) and SP-10 (261029). It reads them only; nothing is computed or started.
- **Mode matching:** every experimental mode, with the published statuses.
- **Research MAC matrices:** shown from a local `matching_record.json` that you choose, checked by its structure and
  SHA-256. They are never a confirmed MAC.
- **PLATE FE sensitivities:** E1, E2, G12 with the rank of the sensitivity matrix.
- **Inverse parameter study:** S0, H1, H2 with their real Abaqus checks.

The tables are archived snapshots: they are tied to your Workspace files only when the SHA-256 match. Every value is
RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY.

**SP-10 FE results** (PRIORITY-7, `docs/gui/PRIORITY7_SP10_RC2.md`). For SP-10, Research Results shows two separate
groups:
- **A. Historical PRIORITY-1:** the archived table, unchanged. Its FE_SHAPES_UNAVAILABLE statuses describe the state
  at that time.
- **B. Updated SP-10 FE Results — PRIORITY-6:**
  - the FE7–FE25 frequencies of `SP10_NEW_E1=E2_NSM_DENSITY`, whose shapes were extracted in PRIORITY-6;
  - a frequency-only diagnostic of EXP1–EXP12, marked FREQUENCY_PROXIMITY_ONLY — NOT A CONFIRMED MODE PAIR.

Both come from small archived records. The 3.1 GB extracted package is never read there: choose its `manifest.json`
on the Workspace page to view the shapes. The page compares the SHA-256 of the files read in the Workspace with the
PRIORITY-6 sources. A match is not a registration: SP-10 261029 stays PHYSICAL_REGISTRATION_NOT_VERIFIED.

**Single-plate research workbench** (PRIORITY-8, `docs/gui/GENERIC_SINGLE_PLATE_WORKBENCH_RC3.md`). The Plate Study page
has two tabs:
- **A. Current PLATE Study:** the accepted study of PLATE-300x300x1mm, unchanged.
- **B. New Single Plate — Research Workbench:** a research study of any single rectangular CFRP plate without a core,
  in eight steps:
  1. **Specimen & Test Setup:** its own identifiers.
  2. **FE and Experimental Inputs:** the files read in the Workspace, linked by SHA-256.
  3. **Measurements & Geometry:** with units and provenance.
  4. **Physical Registration Evidence:** a complete set is never a registration.
  5. **Modal Diagnostics:** frequency proximity only, never pairs.
  6. **Parameter Observability:** NOT_READY_FOR_IDENTIFICATION with the reasons.
  7. **Offline Research Study:** only with a sensitivity table of this FE model, a declared observation set and the
     owner's registration decision. The result is a DIAGNOSTIC_OPTIMIZER_CANDIDATE, not a material property.
  8. **Report & Save:** the study JSON, reopened with its sources checked; a Markdown / JSON / CSV report.

To start:
1. Read the plate's files on the Workspace page and choose the modal set on the Analysis page.
2. Open Plate Study > B and click **New study**.
3. Fill the steps in order.

`docs/examples/generic_single_plate_demo/DEMO_STUDY.json` (**Open study...**) is a SYNTHETIC demonstration of another
plate (420 × 260 mm) that goes through every step, the offline study included. It is never a physical experiment.

**Portable Windows build RC3** (`docs/gui/WINDOWS_PORTABLE_RC3.md`): the folder `AbaqusModalComparator_RC3`, built by
`packaging/portable_rc3/build_portable.py`. RC1 and RC2 are unchanged.

**Portable Windows build RC2** (`docs/gui/WINDOWS_PORTABLE_RC2.md`): the folder `AbaqusModalComparator_RC2`, built by
`packaging/portable_rc2/build_portable.py` from the program with the SP-10 integration. RC1 below is unchanged.

**Portable Windows build** (WINDOWS PORTABLE RC1, `docs/gui/WINDOWS_PORTABLE_RC1.md`): the folder
`AbaqusModalComparator_RC1` holds `AbaqusModalComparator.exe`, the new interface frozen with its libraries and
reference files. It starts with no Python or VS Code installation and starts no Abaqus. Measurement, FE and solver
files are not included; you choose them in the program. The build is made by
`packaging/portable_rc1/build_portable.py`.

## Input procedure

1. Select the Abaqus `*.odb` file.
2. Select the Simcenter Testlab `*.unv` or `*.uff` file.
3. Keep the Abaqus command as `abaqus`, or enter the command used by the installed release, for example `abq2024`.
4. Choose the Abaqus mode range.
5. Leave coordinate scale as `auto`. When the experimental grid covers only part of the specimen and automatic scale is unreliable, enter a known scale such as `0.001` for mm→m.
6. Press **Extract, compare, and build report data**.

## LMS projects

A native `*.lms` database depends on installed/licensed Testlab Automation components and project-version details. The application can use an LMS file as a pointer when a companion UNV/UFF file is beside it. Selecting the supplied UNV/UFF directly remains the most portable workflow.

## Experimental data paths

### Curve-fitted modes

Preferred input contains:

- geometry dataset 15 or 2411;
- modal dataset 55 or 2414.

These modes are the most rigorous input for MAC.

### Raw FRFs

A dataset-58-only file is supported. The program combines the complex FRFs, detects resonance peaks, estimates coherence/damping, and constructs experimental shapes at the selected frequency lines.

Peak-derived shapes are useful for automatic screening and correlation, but they are less rigorous than a full multi-mode curve fit when modes overlap strongly. This distinction is shown in the interface and reports.

## Quality control

Near-zero rigid modes are detected by a relative frequency-gap criterion rather than a fixed 1 Hz limit.

Default admissibility limits are applied **before** the Hungarian assignment:

```text
|frequency error| <= 15%
MAC >= 0.50
```

A pair without calculable MAC can be accepted by frequency only when:

```text
|frequency error| <= 10%
```

Modes that do not satisfy these limits are left unmatched. The FRF & quality tab lists:

- excluded near-zero modes;
- unmatched Abaqus modes;
- unmatched experimental peak candidates;
- closely spaced mode groups;
- selected coordinate scale and transformation warnings.

When no candidate passes the unchanged frequency, MAC, and measured-coverage
gates, the run completes as a **diagnostic result with zero admissible pairs**.
The full MAC and signed frequency-error matrices, geometry transform, candidate
coverage, gate decisions, rejection reasons, and nearest-frequency/best-MAC
cross-checks remain available in the plots and Details view. The analysis cache
also contains `no_pair_diagnostics.json` and `no_pair_candidates.csv`.

This fallback does not accept a rejected candidate, relax a scientific gate, or
constitute successful model validation. It only preserves the evidence needed
to diagnose frequency mismatch, low or unavailable MAC, insufficient coverage,
geometry mapping, or poor experimental mode-shape quality.

## Local coordinate systems

The importer detects dataset 2420 and non-default `def_cs`/`disp_cs` identifiers. It currently warns rather than silently assuming these vectors are global. When such a warning appears, confirm that Testlab exported response directions in the global system before interpreting MAC.

## Reports

Excel includes:

- summary and source files;
- signed and absolute frequency errors;
- mode-pair table;
- full and verified MAC matrices;
- FRF/coherence diagnostics;
- geometry mapping distances;
- quality-control decisions;
- AutoMAC and COMAC;
- Abaqus modal history output.

PDF includes summary pages, frequency regression, MAC, FRF diagnostics, quality-control decisions, AutoMAC/COMAC, and a page for every accepted mode pair.

## Engineering interpretation

- High MAC confirms similarity only over measured DOFs.
- High off-diagonal AutoMAC indicates that the measurement grid cannot distinguish some shapes reliably.
- Low COMAC identifies local regions where Abaqus and experiment disagree repeatedly.
- A frequency-regression slope above 1 means Abaqus is generally higher/stiffer; below 1 means generally lower/softer.

## Data policy

Large or confidential files are ignored by Git:

```text
*.odb
*.lms
*.unv
*.uff
```

Keep laboratory files local and select them through the desktop interface.
