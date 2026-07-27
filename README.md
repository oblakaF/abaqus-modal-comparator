# Abaqus–Simcenter Modal Comparator

A Windows desktop application that compares numerical modal results from an Abaqus output database with experimental modal results from Siemens LMS / Simcenter Testlab.

The normal workflow requires only two result files:

- Abaqus: `*.odb`
- Simcenter Testlab: `*.unv` or `*.uff`

No manual frequency entry and no manual Abaqus screenshots are required.

## Main functions

- Runs an Abaqus Python extraction script against the selected ODB.
- Extracts Abaqus mode numbers, natural frequencies, FE-node coordinates, and complex `U1/U2/U3` mode-shape vectors.
- Preserves useful modal history outputs when they are present in the ODB.
- Reads Testlab Universal File Format geometry and modal datasets.
- Supports UNV/UFF geometry datasets 15 and 2411.
- Supports modal datasets 55 and 2414.
- Reads experimental mode number, frequency, damping, modal mass, node coordinates, and complex modal vectors when available.
- Automatically detects coordinate-unit scale and signed axis permutations.
- Maps experimental measurement points to Abaqus FE nodes.
- Calculates the full MAC matrix.
- Performs one-to-one mode assignment using MAC and frequency error.
- Detects mode-order changes.
- Displays Abaqus, experimental, and overlaid mode-shape plots.
- Exports an Excel workbook and a multipage PDF report.

## First launch on Windows

Double-click:

```text
RUN_PROGRAM.cmd
```

The launcher creates a private `.venv` folder and installs the required Python packages. This can take several minutes on the first run.

## Input procedure

1. Select the Abaqus `*.odb` file.
2. Select the Simcenter Testlab `*.unv` or `*.uff` file.
3. Keep the default Abaqus command as `abaqus`, or enter the command used by the installed version, for example:

```text
abq2024
```

A full path to an Abaqus batch command can also be entered.

4. Keep Abaqus modes `6` to `14`, or change the range.
5. Press **Extract, compare, and build report data**.

The experimental modes are detected automatically.

## Selecting an LMS project

The native `*.lms` database requires installed and licensed Simcenter Testlab Automation libraries and its internal database layout varies by Testlab version and project template.

The application therefore accepts the `*.lms` file only as a project pointer and automatically looks for a companion `*.unv` or `*.uff` file in the same folder. Since the supplied test data include both LMS and UNV files, select the UNV file directly for the most reliable import.

## Required Testlab UNV/UFF contents

For numerical MAC, the universal file must contain:

- geometry: dataset 15 or 2411;
- experimental modal vectors: dataset 55 or modal dataset 2414.

A file containing only FRFs in dataset 58 is not yet sufficient for MAC because modal parameter identification and curve fitting would still be required.

## Abaqus extraction

The ODB is proprietary and is read by the Python interpreter installed with Abaqus. The desktop application calls:

```text
abaqus python abaqus_scripts\extract_odb.py ...
```

The extractor writes a reusable local package containing `manifest.json` and one CSV file per mode. A previously extracted `manifest.json` can be selected instead of rerunning Abaqus.

## Reports

The Excel report contains:

- summary and source files;
- mode-pair table;
- frequency errors;
- MAC values;
- mode-order changes;
- MAC matrix;
- geometry mapping distances;
- Abaqus modal history output;
- frequency and MAC figures.

The PDF report contains the summary, frequency comparison, MAC matrix, and one page for every matched Abaqus–experimental mode pair.

## Current engineering assumptions

- The experimental geometry and Abaqus geometry describe the same physical panel.
- Their coordinate systems may differ by unit scale, axis order, and axis signs.
- Experimental points are mapped to nearest Abaqus nodes after automatic alignment.
- Mode-shape comparison uses available translational components.
- For the best result, export the experimental mode-shape vectors and geometry together from Testlab.

## Repository data policy

Large or confidential project files are intentionally ignored by Git:

```text
*.odb
*.lms
*.unv
*.uff
```

Keep these files on the laboratory computer and select them through the program interface.
