# CARBON-5G: read-only INP audit of the governed SP-02 / SP-13 models (D-076, audit iteration 2 K3)

**Scope.** Read-only comparison of the exact governed Abaqus inputs with the specimen source records. No Abaqus,
no Abaqus Python, no edit. Masses are element volumes × the INP densities plus the INP nonstructural masses; they
are not solver output.

**Governed inputs** (from the forward manifests `docs/auto_id/forward_models/SP0x.physical.forward.json`; the
SHA-256 was re-hashed before parsing):

| Specimen | INP (store `snadwich`) | SHA-256 |
|---|---|---|
| SP-02 | `SP-02/SP02_Modal_V02.inp` (Model-1, Abaqus/CAE 2024) | `574ae78a897f5a666989716c54549969f13ca2919ad3af1f3ca658580a4ba8a5` |
| SP-13 | `SP-13/SP13_mesh_local_v1_modal/SP13_mesh_local_v1_modal.inp` (SP13_mesh_local_v1) | `9d4105840e527354dbd0bb4d0d0012f7708125aa94619b0dcc486fd76dc70571` |

**Source records:** `SP-02/spec.txt` (`39cadf32…`) and `SP-13/spec.txt` (`cf18f58a…`), now pinned in the
additive records `docs/auto_id/specimens/SP0x.physical-measurements.json`. The SP-13 source table writes no units.

## Comparison

| Quantity | SP-02 source | SP-02 INP | SP-13 source | SP-13 INP | Status | Scientific implication |
|---|---|---|---|---|---|---|
| Top face thickness | 0.45 mm | **0.45 mm** (`CFRP_FaceSheet-top`, z 2.45–2.90; C3D8I, 2 layers) | 0.425 | **0.425 mm** (`CFRP_plate_top`, z 2.425–2.85; C3D8I, 2 layers) | agree | Both models use their source value. No 9+ point thickness map exists (SPEC §15 not met) |
| Bottom face thickness | 0.45 mm | **0.45 mm** (z 0–0.45) | 0.425 | **0.425 mm** (z 0–0.425) | agree | as above |
| Section / z geometry | — | solid sections (no shell): face part 0–0.45, instances at z 0 and 2.45; core at z 0.45 | — | solid sections: face part 0–0.425, instances at z 0 and 2.425; core part offset to z 0.425 | — | Face thickness is geometric (solid elements), not a shell-section value |
| Core height | 2 mm | **2.0 mm** (z 0.45–2.45; C3D20R, 4 layers) | 2 | **2.0 mm** (z 0.425–2.425; C3D20R) | agree | |
| Total thickness | 2.9 mm | **2.90 mm** | 2.85 | **2.85 mm** | agree | |
| Plan dimensions | 515 × 510 mm | faces **510 (x) × 515 (y)** | 510 × 520 | faces **510 (x) × 520 (y)** | agree (orientation not stated in SP-02 source) | |
| Core footprint | — | **510 × 515**, equal to the faces | — | **501.9 × 496.0** (x 3.72–505.62, y 12.0–508.0) | **SP-13 differs** | SP-13 faces overhang the core: about 3.7 / 4.4 mm along x and 12.0 / 12.0 mm along y. These strips are face-only (no core between the sheets); SP-02 has none |
| Carbon density | 1.57e-9 t/mm³ | **1.57e-9** | (empty) | **1.429e-9** | SP-02 agrees; SP-13 not in source | SP-13 density reproduces the measured face masses (below); SP-02 uses the nominal value |
| Face mass (each) | 175.60 g / 175.60 g | **185.56 g** each (+5.7 %) | 163.60 / 158.50 | **161.06 g** each (= measured mean) | **SP-02 differs** | Model face areal mass: SP-02 706.5 g/m² vs measured 668.6; SP-13 607.3 g/m² = measured |
| Core density / mass | 9.01e-10 t/mm³; 144.58 g | 1.0475e-9; **144.58 g** | (empty); 179.13 | 1.1212e-9; **179.13 g** | masses agree | Both core densities reproduce the measured core mass with the resolved core volume (SP-02 differs from its spec.txt density) |
| Core relative fill | honeycomb | 0.263 of the core box | auxetic | 0.321 (edge 10 mm band 0.345) | — | Resolved core topologies, not homogenised |
| Adhesive representation | 3M DP420 | **not modelled as material**; Ties core–faces | 3M DP420 | **not modelled as material**; Ties core–faces | same | Adhesive adds no stiffness in either model |
| Adhesive mass | 44.58 + 45.77 = 90.35 g (calculated; real empty) | nonstructural mass **33.2 g per face** (part-level, both faces) = **66.4 g** | real 83.16 g (calculated 44.1 + 44.91) | nonstructural mass **41.98 g (bottom) + 41.22 g (top) = 83.2 g** | **SP-02 differs** | SP-02: 24 g less adhesive mass than calculated, compensated by 20 g more face mass; SP-13: equals the real adhesive mass |
| Where adhesive mass sits | — | volume-proportional on the face sheets | — | volume-proportional on the face sheets | same | |
| Total model mass | 582.71 g | **582.10 g** | real 584.6 | **584.45 g** | agree (−0.1 %, −0.03 %) | Total mass matches in both; the SP-02 split between faces and adhesive does not |
| Materials / sections | CFRP T300 plain; PLA | `CFRP_T300_PlainWeave` (faces), `PLA_Core_Material` (core); E 52 000, G12 4 500, ν12 0.05 | CFRP T300 plain; PLA | `CFRP_Face`, `PLA_Basic_Core`; same constants | same constants | |
| Frequency request (source INP) | — | 15 modes (M3 renders 30) | — | 30 modes | — | No physics difference |

## Answers

1. **SP-02 face thickness in Abaqus:** 0.45 mm, top and bottom (solid C3D8I sheets, z 0–0.45 and 2.45–2.90).
2. **SP-13 face thickness in Abaqus:** 0.425 mm, top and bottom (z 0–0.425 and 2.425–2.85).
3. **Is SP-13's ~0.425 mm already represented?** Yes. The SP-13 FE model uses exactly 0.425 mm, and its face
   density (1.429e-9) reproduces the measured face masses. An unmodelled thinner SP-13 face is therefore **not** an
   explanation of the SP-13 frequency deficit.
4. **Is the SP-13 deficit / the ~5–8 percentage-point specimen shift plausibly connected to model or input
   geometry?** Plausibly in part, through facts this audit found, but not through the SP-13 face thickness:
   - SP-13 has face-only overhang strips (12 mm along both y edges, ~4 mm along x) with no core; SP-02 has none.
     They lower local bending and torsional stiffness at the edges.
   - SP-02 carries 5.7 % more face mass than measured and 24 g less adhesive mass than calculated (total
     matched). Its face thickness (0.45 mm) and face mass are not independently consistent with the measured face
     mass at the nominal density: either the real SP-02 faces are thinner (about 0.426 mm at 1.57e-9) or less
     dense. Bending stiffness scales with E·t_f, so an identified E for SP-02 is effectively an E·t_f statement;
     a few-percent t_f error maps one-to-one into E.
   - The measured face areal mass of SP-13 is 9 % below SP-02 (607 vs 669 g/m²), for nominally the same material.
   - Both models miss torsional mode 1 strongly (SP-02 −15.8 %, SP-13 −28.4 % at the baseline), a model-form
     signal shared by both specimens and larger for SP-13.
   - Read-only data cannot apportion the 5–8 pp gap between these causes; no causal claim is made.
5. **What remains unknowable without new FE solves:** the frequency sensitivity of each governed row to t_f, to the
   SP-02 face/adhesive mass split, to the SP-13 core footprint (overhang strips), to the core material constants
   and to an adhesive layer with stiffness; whether a physically governed t_f and mass layout removes the family
   discrepancy; how much of the torsional mode 1 error is G12, core shear or interface. Sandwich frequencies do not
   scale as √E (SPEC §2), so no hand scaling replaces those solves. None is run or authorised here.

## Not changed

No INP, passport, registration, fixture, freeze, mode pair or result record was modified. The physical facts are
recorded additively in `docs/auto_id/specimens/SP0x.physical-measurements.json` with uncertainty
`NOT_AVAILABLE` (instrument resolution is not an uncertainty).
