# Coordinate Calibration Decision — Polytec Camera-Grid Geometry

**Status:** authoritative correction for current HUD QA

**Supersedes:** the earlier `SCALE-A = fixed 0.001` conclusion in `docs/ROADMAP_CURRENT_QA_ADDENDUM.md` for the 500x500 Polytec sandwich case.

## Operator provenance

The Polytec operator confirmed that, for the 500x500 sandwich test:

- no physical specimen dimensions were entered into Polytec;
- no reference length / distance calibration was entered;
- no CAD geometry was supplied;
- no physical geometry calibration was performed;
- the suspended plate was viewed through the camera;
- an 11x11 scan grid was drawn manually in the camera view;
- the scan covered the full specimen.

Therefore the UNV geometry coordinates are **uncalibrated camera-grid coordinates**, not independently verified physical coordinates.

## Consequence for UNV dataset 164

The UNV file contains dataset 164 declaring `METRIC_ABS_(SI)` with length conversion factor 1.0. That metadata is not sufficient evidence that this particular camera-grid geometry is metrically calibrated. For this acquisition provenance, the geometry coordinates must not be interpreted as physical metres merely from the SI declaration.

The previously observed raw spans:

- X ~0.332937
- Y ~0.328658

must therefore **not** be interpreted as proof of a physical ~333x329 mm partial scan.

The previous `partial scan` interpretation is rejected for this specimen.

## Known physical geometry

The specimen/full scan is the ~500x500 mm sandwich panel. The corresponding FE model is ~502x499 mm in-plane, consistent with the measured specimen family and model geometry.

For a full scan of a known rectangular specimen, camera-grid geometry should be calibrated from known physical dimensions (preferably the actual measured specimen width/height for that physical panel, not nominal 500x500 if better measurements exist).

The old geometric scale ~0.0006603457 now has a physical explanation: it is approximately the factor required to map the uncalibrated camera-grid extent onto the known ~500x500 mm specimen extent. This explains why the historical geometric-auto registration produced a physically plausible full-panel map and 8 accepted modal pairs.

However, the historical 8-pair result is **not automatically promoted to the final scientific baseline**. It must be reproduced using an explicit, provenance-based camera-grid calibration rather than an opaque extent-fit heuristic, and the result must remain independent of MAC thresholds/pairing tuning.

## Required production distinction

The program must distinguish at least these geometry-provenance cases:

### 1. Physically calibrated experimental geometry

Use the declared/known physical units directly.

Examples:

- calibrated scanner/CAD geometry;
- geometry with independently known physical coordinates;
- trusted UNV geometry where calibration provenance is documented.

In this mode, unit conversion is deterministic and no arbitrary geometric rescaling is permitted by default.

### 2. Uncalibrated Polytec camera grid

Do **not** trust raw UNV coordinate magnitude as physical length.

Require explicit calibration information, such as:

- actual specimen width;
- actual specimen height;
- full-scan vs partial-scan status;
- for partial scan, physical scan-window width/height or control-point coordinates.

For a known full rectangular scan, calibrate the camera-grid X/Y extents to the known physical rectangle. Prefer separate X/Y scale factors rather than forcing one isotropic scalar if the camera-grid axes have slightly different scale.

Rotation, axis swap, and reflection remain separate registration degrees of freedom.

### 3. Unknown/insufficient calibration provenance

Do not silently interpret camera-grid coordinates as physical units and do not silently stretch them to the FE bounding box.

Report that physical geometry calibration is unresolved and require additional user information.

## Recommended calibration hierarchy

For the current 500x500 case:

1. use the actual measured specimen width/height if available (preferred over nominal 500x500);
2. confirm scan = full specimen;
3. calibrate raw camera-grid X/Y extents to that rectangle;
4. then solve only orientation/translation/reflection registration;
5. compare modal shapes using unchanged MAC/pairing thresholds.

If residual geometry indicates camera perspective/shear that independent X/Y scaling cannot explain, support an advanced 2D affine calibration based on known control points/corners. Do not introduce unconstrained affine fitting solely to maximize MAC.

## UI requirements before HUD PR

Replace the ambiguous `Automatic from units / alignment` concept with explicit geometry-provenance choices, for example:

- `Calibrated physical geometry` — trust units;
- `Uncalibrated camera grid` — calibrate from known specimen/scan dimensions;
- optional advanced/manual calibration.

For uncalibrated camera-grid mode show fields for:

- specimen/scan width;
- specimen/scan height;
- full scan / partial scan;
- calibration provenance/status.

Persist the chosen calibration mode and dimensions in the project file so a later rerun cannot silently change semantics.

Reports should record:

- raw UNV extents;
- calibration mode;
- target physical dimensions;
- X/Y scale factors;
- rotation/axis/reflection transform;
- mapped-region bounding box;
- calibration warnings.

## Scientific rule

Do not change MAC thresholds, frequency gates, coverage thresholds, or Hungarian pairing to recover more matches. Coordinate calibration is a geometry/provenance problem and must be solved before interpreting modal-correlation quality.

## Separate 300x300 issue

The incomplete modal matching observed in the separate 300x300 specimen is not explained by this 500x500 coordinate-calibration issue. Its geometry is already reported as mapping at 100%; its remaining limitations concern experimental FRF/modal observability (dataset 58, single reference, close/mixed modes) and belong to the later SCI-S0 / EMA work.
