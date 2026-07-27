# Code review implementation

This update applies the engineering code review before the next laboratory test.

## Implemented critical corrections

- MAC is calculated only on experimentally measured DOFs.
- Frequency error is signed; absolute value is used only for gates and summary magnitude.
- Frequency/MAC admissibility is applied before one-to-one assignment.
- Assignment allows both Abaqus and experimental modes to remain unmatched.
- Mode-order changes are calculated only within accepted pairs.

## Robustness and architecture

- Quality control is imported explicitly rather than enabled by import-order monkey patching.
- UNV scalar fields tolerate NumPy arrays and multiple pyuff key variants.
- Dataset 55 and 2414 parsers have regression tests.
- Dataset 2420 and non-default local coordinate-system IDs produce a visible warning.
- ODB extraction cache checks path, size, modification time, Abaqus command, and mode range.
- GUI validation handles invalid Spinbox and scale input.
- Worker cleanup is scheduled in every success/failure path, even when log writing fails.
- Matplotlib work is serialized and the main mode-shape renderers use explicit Figure objects.
- Mode-pair images are cached between table selections.

## Geometry and performance

- A single FE-node KD-tree is reused for all signed axis permutations.
- Mode node-index dictionaries are cached on each ModeShape.
- Experimental mode vectors are mapped once outside the Abaqus-mode loop.
- Only the best geometry candidates proceed to modal evaluation.
- Duplicate mapped FE nodes and mirrored transforms are reported.
- Manual coordinate-scale override is available.

## Diagnostics

- Frequency regression with a 45-degree reference and fitted slope.
- AutoMAC for numerical and experimental mode sets.
- COMAC by measurement point.
- Shared-scale Abaqus/experiment amplitude-correlation plot.
- FRF/coherence and verified-MAC dashboards retained.

## Remaining limitation

Local UNV coordinate systems are detected but not yet transformed from dataset 2420. Results are therefore blocked by a warning rather than being silently interpreted as global vectors.
