# Abaqus Modal Comparator

A desktop application for comparing Abaqus numerical modal-analysis results with experimental modal-test data.

## Current features

- Reads Abaqus and experimental frequencies from CSV files.
- Automatically performs one-to-one frequency-based mode matching.
- Calculates the relative frequency error for every matched pair.
- Detects changes in modal order.
- Displays Abaqus and experimental mode-shape images side by side.
- Exports the comparison table and matched image paths to CSV.
- Uses a fully English-language interface.

## CSV format

Both frequency files must contain these columns:

```csv
mode,frequency_hz
6,122.4
7,156.8
```

The Abaqus mode numbers and experimental mode numbers do not need to be the same.

## Mode-shape images

Select one folder for Abaqus images and another folder for experimental images.

Recommended image names:

```text
Abaqus folder:
abaqus_mode_6.png
abaqus_mode_7.png
...

Experimental folder:
experimental_mode_1.jpg
experimental_mode_2.jpg
...
```

The program also recognizes simpler names such as:

```text
mode_6.png
mode6.png
6.png
```

Supported formats: PNG, JPG, JPEG, BMP, GIF, TIF, and TIFF.

After the comparison is complete, select any row in the results table. The matching Abaqus and experimental mode-shape images will appear in the preview panel.

## Running on Windows

Double-click:

```text
RUN_PROGRAM.cmd
```

On the first run, the launcher installs Pillow from `requirements.txt` so that the application can display and resize images.

Manual launch:

```bash
python -m pip install -r requirements.txt
python src/main.py
```

## Matching limitation

The current version matches modes using frequency error only. Image preview is intended for visual confirmation. A future version can add numerical MAC calculation when experimental mode-shape vectors are available.
