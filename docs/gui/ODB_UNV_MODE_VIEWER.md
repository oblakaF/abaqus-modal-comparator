# ODB + UNV/UFF: frequencies and individual modes without a physical registration

Workflow 1 (Compare modes, ODB + UNV/UFF) always gives a usable result. This holds even when the physical
orientation of the measurement relative to the FE model cannot be established.

## What the user does

1. Start the program with `RUN_PROGRAM.cmd`.
2. Select the Abaqus `.odb` (or a previously extracted `manifest.json`).
3. Select the experimental `.unv` / `.uff`.
4. If the file has several fitted modal sets, choose one. Sets are never mixed.
5. Press **Run analysis**.

## What the program shows

| Situation | 2. Comparison table | 3. Mode shapes |
|---|---|---|
| Physical registration established (unique automatic orientation, accepted registration or a user-confirmed orientation) | Gated FE–experiment pairs with MAC (unchanged) | **Verified pair** view (unchanged); **Individual modes** also available |
| Orientation ambiguous (several equally plausible candidates from geometry alone) | `FREQUENCY_ONLY_DIAGNOSTIC`: FE and experimental frequencies, nearest-frequency differences. These are proximity only: no MAC, not mode pairs | **Individual modes** opens automatically. FE and experimental views are separate, with no overlay and no MAC |
| Experimental file has no usable modal/FRF data | Empty, with the reason | FE modes remain viewable; the experimental limitation is stated |

The orientation dialog no longer opens by itself. Use **Confirm physical orientation (independent evidence)…** in
3. Mode shapes only when independent setup evidence identifies the orientation. Then run the analysis again.

## Individual modes view

### FE pane

- Shows every extracted Abaqus mode by number and frequency, on its own FE nodes.
- ◀ / ▶ step through the modes.
- The component can be out-of-plane, magnitude, U1, U2 or U3.
- Large models (more than 5 000 nodes) are averaged on a display grid.

### Experimental pane

The pane shows the imported records with their source:

- **curve-fitted experimental mode (dataset 55 / 2414, modal set …)**: actual imported fitted modes.
- **FRF peak N — FRF peak-derived response snapshot — NOT a validated fitted mode shape**: shown when the UNV holds
  only dataset 58. It is the complex FRF at a detected resonance peak, phase-aligned (real part), on the measured
  points. Mean coherence, phase complexity and the half-power damping estimate are shown with it.
- If fewer than three measured points respond, the pane says that there are not enough nodal channels for a spatial
  view.

FRF peaks are never turned into governed experimental modal evidence. Their frequencies are labelled **PROVISIONAL**
wherever they appear.

### Save diagnostic output…

Writes these files to a chosen folder:

- `modal_data_inventory.json` and `modal_data_frequencies.csv`: what each file contains and how each record is
  classified;
- the frequency-only diagnostic (`.json` and `.txt`), when the orientation is ambiguous;
- the two views currently shown.

No INP is ever written.

## What still requires a physical registration

The following need a physical registration (an accepted registration, a unique automatic orientation, or a
user-confirmed orientation backed by independent evidence):

- MAC;
- FE–experiment mode pairs;
- overlay or correlation plots;
- frequency errors of *paired* modes;
- everything that builds on pairs: COMAC, manual pair review, frequency scaling and calibration.

Frequency proximity is never used to choose an orientation or to pair modes.
