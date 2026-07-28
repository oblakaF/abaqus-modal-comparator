# Figure viewing and export specification

## Goals

The GUI must make every generated diagnostic readable without relying on screenshots and must export publication-quality files directly.

## Full-size viewing

Each plot panel provides an **Open full size** action. It opens the original PNG in a resizable viewer window with:

- fit-to-window display;
- scrollbars when the image is larger than the window;
- zoom controls: Fit, 100%, Zoom in, Zoom out;
- Save as PNG;
- Open containing folder.

## Tab exports

### Comparison table

- Save table as CSV.
- Save table as PNG.

### Mode shapes

For the selected pair:

- Save Abaqus shape PNG.
- Save experimental shape PNG.
- Save amplitude-correlation PNG.
- Save all three images to a selected folder.

For all accepted pairs:

- Batch export one subfolder per matched pair.

### MAC and frequencies

- Save full MAC matrix PNG.
- Save frequency-regression PNG.
- Save both figures to a selected folder.

### FRF and quality

- Save FRF/coherence diagnostics PNG.
- Save verified-pair MAC matrix PNG.
- Save quality-control summary TXT.
- Save the complete tab bundle.

### AutoMAC and COMAC

The combined miniature figure is replaced by three independent large panels:

- Abaqus AutoMAC;
- experimental AutoMAC;
- COMAC map.

Each panel supports full-size viewing and individual PNG export. A bundle action saves all three images and a text summary.

### Details

- Save details as TXT.
- Save metadata as JSON.

## Global export

A global **Export all figures** action saves:

- MAC matrix;
- frequency regression;
- FRF diagnostics;
- verified MAC matrix;
- Abaqus AutoMAC;
- experimental AutoMAC;
- COMAC map;
- all selected-pair or all-pair mode-shape figures;
- quality-control summary;
- details and metadata.

## Resolution

Generated source figures remain at their native analytical resolution. Export copies are written without re-sampling. Figure creation functions use at least 170 dpi for screen files. Existing Excel/PDF reports remain available separately.
