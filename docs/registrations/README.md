# Primary Carbon Identification Registrations

Accepted `frozen-registration/1` artifacts for the primary shared-carbon pair
(old CFRP T300 plain-weave faces, PLA cores).

## SP-02

- Honeycomb core.
- Experiment: `retry_260803` acquisition, PolyMAX file `SP02_polymax_retry_260803.unv`
  (SHA-256 `2671db01b6401a9a9bbec7d8c2aa2191b0b35b5ae791756b91c7ccd381a41785`).
- Modal set: `bravo-1`.
- FE: `SP02_Modal_V02` (geometry SHA-256 `72e8597a042f08f72ef2b87037f9a09c64539ba5e5a04254c95cb54f8e2d4e6d`).
- FrozenRegistration hash: `9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164`.
- 121 points, U3-only measurement contract, TOP exterior face.

## SP-02 physical registration (M6 gate, 2026-10-06; REVIEW_READY)

- `SP02_physical_registration.json`, hash `9b63f6c891331ba55a6ee2797f142bf0b75117d9bffbf3ab312ee08a418e882c`: `scan_to_panel_edges` + `camera_grid`,
  reconstructed from the stored PSV frame with the SP-13 method (record in
  `docs/auto_id/registration_evidence/`).
- One production-readiness issue: `physical_specimen_id` is not recorded (identity needs one HUMAN
  confirmation).
- The legacy `SP02_frozen_registration.json` below is historical provenance only: it is
  physically inconsistent (point error median 29 mm, max 54 mm).

## SP-13 physical registration (M6 gate, 2026-10-06; D-062)

- `SP13_physical_registration.json`, hash `2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823`: `scan_to_panel_edges` + `camera_grid`,
  reconstructed from the stored PSV frame (record in `docs/auto_id/registration_evidence/`).
  Production-ready. After HUMAN H8: `scale_rel` 0.002 (readout only); `registration_limited` False.
- The legacy `SP13_frozen_registration.json` below is historical provenance only: it is
  physically inconsistent (point error median 26 mm, max 47 mm).

## SP-13

- Auxetic core.
- Experiment: accepted REAL-1 lineage (`analysis/sp13_real_baseline/SOURCE_FREEZE.json`),
  `SP13_a_polymax.unv` (SHA-256 `f268023583972f0a9c1660bc60631587e8f3330e4fb7495e52d8310906af39fe`).
- Modal set: `best`.
- FE: `SP13_mesh_local_v1_modal` (geometry SHA-256 `34d69d7920f5819c49ad5b2ab1aded824055aadbea3cb0244f405ab1a1595826`).
- FrozenRegistration hash: `a8970e525d10173af3d3b030b1150ca24432b616e1b52f6e8cfeefe2946f58a4`.
- 289 points, U3-only measurement contract, TOP exterior face.

The SP-13 production nearest-node mapping was validated against the accepted
REAL-1 bilinear interpolation before freezing. REAL-1 remains the validation
reference.

## Scope

- These files freeze the experimental-to-FE geometry and measurement contracts.
- They do NOT freeze carbon elastic constants.
- They do NOT contain inverse-identification results.
- Raw UNV/ODB files are intentionally not committed.
- Downstream evidence must bind to these registration hashes; do not
  regenerate these files casually.
