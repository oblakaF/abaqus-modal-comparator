# Quick material calibration (Abaqus INP + Polytec / Testlab UNV-UFF)

A fast, honest engineering answer to: *which elastic constants make this FE model reproduce
this specimen's measured modes, and how well are they constrained?*

It is **not** the governed Auto-ID material identification (`docs/auto_id/SPEC_V1_2.md`). The
result is always labelled `EFFECTIVE_MODEL_CALIBRATION` / `NOT_A_MATERIAL_PROPERTY`: effective
constants of *this* model for *this* specimen, not transferable without validation.

## Start

- Window: double-click `RUN_QUICK_CALIBRATION.cmd`. Choose the INP, the UNV/UFF, the material
  (filled from the INP), press **Run calibration**.
- Command line:

```text
python tools/quick_calibration.py quick --inp SP13.inp --unv SP13.unv --material CFRP_Face --out SP13_quick --abaqus abq2024 --cpus 4
python tools/quick_calibration.py template case.json      # editable configuration
python tools/quick_calibration.py run case.json
```

## Inputs

| Input | Notes |
|---|---|
| Abaqus model `.inp` | Re-solvable model with one `*Frequency` step. The calibrated material's `*Elastic` must be in this file (not in an `*Include`), temperature-independent, type `ENGINEERING CONSTANTS`, `LAMINA` or `ISOTROPIC`. An ODB is not enough: sandwich frequencies do not scale as √E. |
| Polytec / Testlab `.unv` / `.uff` | Preferred: curve-fitted modes (PolyMAX, dataset 55/2414). Dataset 58 FRFs are accepted; their peak-derived modes cap the grade at APPROXIMATE. |
| Material and constants | A multiplier k scales the listed constants together (default `E1,E2` for a face sheet). Optional second parameter: `G12` of the same material. |
| Mode range | Set "from" above the suspension modes. |
| Orientation | For a symmetric panel the scan orientation cannot be found from geometry; the program stops and lists the candidates. Choose from the photograph / corner marker, never from MAC. |

## Method

1. Read the experiment with the application's reader.
2. Solve the unchanged INP; pair modes with the application's comparator (geometry-only
   registration, rigid modes removed). Pairs with MAC ≥ 0.80 become the fitted rows and are frozen.
3. Each candidate k: write the INP, solve, extract, follow every row by FE-to-FE MAC ≥ 0.90 on the
   scanned surface. Loss of identity stops the run (no re-pairing).
4. Bounded Levenberg–Marquardt in ln k (`run_bounded_lm`, SPEC §8 constants) on
   r = ln(f_FE/f_EXP)/σ, σ = 0.3 %. Typically 6–10 Abaqus solves for one parameter.
5. At the optimum: a fresh central-difference Jacobian, then
   - statistical sd and scatter-scaled sd (×√(χ²/dof));
   - linearised leave-one-mode-out range;
   - **mode spread**: how far apart the single modes are about the value (sensitivity-weighted).
   The reported **band** is the largest of the three.

## Result

| Status / grade | Meaning |
|---|---|
| `NO VALUE` | optimum on a search bound; mode identity lost; not converged; parameter not observable; too few MAC ≥ 0.8 pairs. |
| `GOOD` | band ≤ 5 %, every mode within 5 % after calibration, ≥ k+2 modes, curve-fitted experiment. |
| `APPROXIMATE` | band ≤ 10 % and every mode within 10 %. |
| `UNRELIABLE` | a value is shown, but the modes disagree about it (model-form discrepancy: core, adhesive, thickness, boundary conditions). |

Because frequencies depend weakly on E (d ln f / d ln E ≈ 0.2–0.5 in a sandwich), a ±5 %
frequency disagreement between modes means a ±10–25 % spread in E. The grade reports that
honestly instead of the much smaller sd of a mean.

Output folder: `report.txt`, `result.json`, `modes.csv` (per mode: start/final error, MAC,
sensitivity, the multiplier this mode alone asks for), `<model>_calibrated.inp` (only when a value
is shown), `config.json`, and `work/` with the Abaqus jobs (a repeated run reuses finished jobs).

## Implementation

`src/services/quick_calibration.py` (service), `tools/quick_calibration.py` (CLI),
`src/quick_calibration_window.py` (window), `src/application_layers.py` (reader/comparator layers
shared with the main window). Tests: `tests/test_quick_calibration.py`,
`tests/test_quick_calibration_window.py` (synthetic plate and a fake Abaqus).
