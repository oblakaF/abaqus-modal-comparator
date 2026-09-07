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
