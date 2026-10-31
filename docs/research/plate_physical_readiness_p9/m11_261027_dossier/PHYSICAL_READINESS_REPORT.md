# Physical readiness report — PLATE-300x300x1mm

Labels: RESEARCH_ONLY / NOT_A_MATERIAL_PROPERTY / NO_REGISTRATION_CREATED / NO_MAC_COMPUTED

- Specimen: PLATE-300x300x1mm
- Series: NEXP29/PLATE300-1MM/S261027-ROTATED
- Modal set: Polymax_bravo
- FE model: Abaqus M11 S4R_0875_BASELINE
- Experimental SHA-256: 76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d
- FE manifest SHA-256: 354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7
- INP SHA-256: 962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3
- Review fingerprint: 2029ab4eb8138b27c84f434ec171a3c7fb645f6f9fda212672455d93d142f786

## States

- sources: **SOURCES_VERIFIED**
- registration: **PHYSICAL_REGISTRATION_NOT_VERIFIED**
- mode_pairs: **MODE_PAIRS_NOT_CONFIRMED**
- identification: **NOT_READY_FOR_IDENTIFICATION**
- review_package: **READY_FOR_OWNER_REVIEW**

- READY_FOR_OWNER_REVIEW means that the package for an owner decision is complete; it is not a scientific acceptance, a registration or a permission to identify
- No registration, mode pair, MAC, FIT / HOLDOUT set, fit or material value is created by this review.

Scientific status: M8 GATE NOT_MET · D-077 NO_GLOBAL_PARAMETER_VALUE · production Auto-ID BLOCKED · no material value is released here

## 1. Sources

| Role | Path | SHA-256 | Size | Origin | May support | State |
|---|---|---|---|---|---|---|
| experimental UNV | D:\git\abaqus-modal-comparator-work\research\INTEGRATION_RC1_REVIEW\moved inputs\EXP delivery copy\SPname_files_ROTATED_261028\300by300_plate_only_1mm_ROTATED_Polytec_261027.unv | 76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d | 421096 | Workspace (Inspect file) | the measured modal records and the scan geometry (instrument record) | VERIFIED_SHA256 |
| FE manifest.json | D:\git\abaqus-modal-comparator-work\research\INTEGRATION_RC1_REVIEW\moved inputs\FE package copy\manifest.json | 354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7 | 27786 | Workspace (Inspect file) | the FE modes and geometry of M11 | VERIFIED_SHA256 |
| FE input (INP) | D:\git\abaqus-modal-comparator-work\research\INTEGRATION_RC1_REVIEW\moved inputs\FE archive copy\external_models\v3_20261021\Plate\temp_root\CFRP_S4R_0875_FreeFree.inp | 962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3 | 871611 | chosen by the user (hashed only, never run) | the FE model's input (geometry, material, no physical landmark) | VERIFIED_SHA256 |
| PSV project (.svd) | — | — | — | — | the camera frame and the physical scan geometry of 261027 (300by300_plate_only_1mm_ROTATED_261027.svd) | NOT_AVAILABLE (not delivered; not needed to view the existing diagnostics) |

Archive: the PRIORITY-1–4 archive, each file read with its recorded SHA-256

## 2. Evidence A / B

Registration: **PHYSICAL_REGISTRATION_NOT_VERIFIED**. Open facts: scanned_face, grid_plus_v_edge, scan_metric_geometry, scan_window_offsets_mm, fe_origin_corner, fe_normal_face

| Chain | Fact | Value | Provenance | Status | Blocking reason |
|---|---|---|---|---|---|
| A. scanner → physical plate | scanned_face | unmarked (the 261016 face) | DERIVED | OPEN | DERIVED: not independent evidence (the face of the plate towards the scanner (marked or unmarked)); rests on scanned_face_261016 (CANDIDATE) |
| A. scanner → physical plate | grid_plus_u_edge | 1 | DERIVED | ESTABLISHED | — |
| A. scanner → physical plate | grid_plus_v_edge | 2 | DERIVED | OPEN | DERIVED: not independent evidence (the physical edge (1–4) the scan grid's +v axis points to); rests on scanned_face_261016 (CANDIDATE) |
| A. scanner → physical plate | rotation_reference | the 261016 position, turned 45° clockwise as viewed from the Polytec | DERIVED | ESTABLISHED | — |
| A. scanner → physical plate | scan_metric_geometry | the 261016 physical positions of the same points | DERIVED | OPEN | DERIVED: not independent evidence (the scan coordinates are physical positions on the plate (the instrument's scanner angles and distance, or a camera frame), not only a grid representation); rests on metric_reconstruction_261016 (CANDIDATE) |
| A. scanner → physical plate | scan_window_offsets_mm | -u 7.02, +u 7.78, -v 29.19, +v 56.4 | DERIVED | OPEN | DERIVED: not independent evidence (the distances from the scan window to the physical edges (−u, +u, −v, +v)); rests on window_offsets_261016 (CANDIDATE) |
| A. scanner → physical plate | scan_scale | mm_per_unit 1000.0, units m (dataset 164 METRIC_ABS_(SI)), distance_m 1.15 | INSTRUMENT_RECORD | ESTABLISHED | — |
| A. scanner → physical plate | measured_dof | +Z of the scan frame (response direction 3 in all 867 dataset-58 records); the points lie at z = −1.15 m, so +Z points from the plate towards the scanner | INSTRUMENT_RECORD | ESTABLISHED | — |
| B. physical plate → FE model | fe_x_along_edges | 1/3 | HUMAN_CONFIRMED | ESTABLISHED | — |
| B. physical plate → FE model | fe_origin_corner | — | CANDIDATE | OPEN | CANDIDATE: not independent evidence (the physical corner at FE (0, 0)) |
| B. physical plate → FE model | fe_normal_face | — | CANDIDATE | OPEN | CANDIDATE: not independent evidence (the physical face the S4R normal (+Z) leaves) |
| supporting (relative facts and the 261016 reference) | same_points_as_261016 | the same physical measured points | HUMAN_CONFIRMED | SUPPORTING — independent | — |
| supporting (relative facts and the 261016 reference) | same_face_as_261016 | the same measured face (relative: which face is not stated) | HUMAN_CONFIRMED | SUPPORTING — independent | — |
| supporting (relative facts and the 261016 reference) | turn_from_261016 | turned 45° from the 261016 position | HUMAN_CONFIRMED | SUPPORTING — independent | — |
| supporting (relative facts and the 261016 reference) | scan_geometry_261016 | 289 points, 17 × 17 grid, ids 1–289 | INSTRUMENT_RECORD | SUPPORTING — independent | — |
| supporting (relative facts and the 261016 reference) | scan_geometry_261027 | 289 points, 17 × 17 grid, ids 1–289 | INSTRUMENT_RECORD | SUPPORTING — independent | — |
| supporting (relative facts and the 261016 reference) | point_map_261016_261027 | id k ↔ id k (289 of 289 ids preserved by the grid identity); grid turn -44.17°, clockwise as viewed from the scanner (+Z towards it) | DERIVED | SUPPORTING — DERIVED from independent facts | — |
| supporting (relative facts and the 261016 reference) | scan_axes_261016 | scan +y up and +x right in the camera frame; the grid +u is +y (0.58° tilt) | INSTRUMENT_RECORD | SUPPORTING — independent | — |
| supporting (relative facts and the 261016 reference) | top_edge_261016 | 1 | HUMAN_CONFIRMED | SUPPORTING — independent | — |
| supporting (relative facts and the 261016 reference) | scanned_face_261016 | unmarked | CANDIDATE | SUPPORTING — CANDIDATE: not evidence by itself | — |
| supporting (relative facts and the 261016 reference) | window_offsets_261016 | -u 7.02, +u 7.78, -v 29.19, +v 56.4 | CANDIDATE | SUPPORTING — CANDIDATE: not evidence by itself | — |
| supporting (relative facts and the 261016 reference) | metric_reconstruction_261016 | scanner angles and camera frame: window ≈ 215.4 × 285.2 mm | CANDIDATE | SUPPORTING — CANDIDATE: not evidence by itself | — |
| A. scanner → physical plate | unv_grid_261027 | 277.7 × 277.0 mm at z -1.15 m | INSTRUMENT_RECORD | REPRESENTATION — NOT the physical window | the PSV UNV grid is a representation, not a physical calibration (M11 §15.4); it never closes scan_window_offsets_mm or scan_metric_geometry |
| B. physical plate → FE model | fe_model_geometry | X 0–301, Y 0–300, Z 0 mm; S4R, 3 mm mesh; normal +Z; uniform h 0.875 mm | ESTABLISHED_IN_THE_MODEL | MODEL RECORD — not physical evidence | the model has no physical landmark |
| B. physical plate → FE model | fe_measured_asymmetry | none in M11 (homogeneous, uniform thickness): candidates A–D are symmetry-equivalent; measured edge means 0.816–0.926 mm exist only in the specimen record | NOT_AVAILABLE | NOT_AVAILABLE | no FE variant carries a measured asymmetry; A–D are not chosen by MAC, frequency or shape |

- MEASURED, INSTRUMENT_RECORD and HUMAN_CONFIRMED are independent evidence; DERIVED only when everything it rests on is; CANDIDATE, CONVENTION_ONLY and NOT_VERIFIED never are
- a relative fact (the same face, the same points) carries the reference series' evidence over and never raises it
- the UNV grid is a representation, not the physical window; a diagnostic reconstruction is not a measured geometry; the candidates A–D are not physical facts

What would close the open facts (existing records):

- scanned_face, grid_plus_v_edge: the 261016 SCANNER_FACE answer (M11 §15.3: did the laser see the face without marks? one yes / no); the owner's same face then carries it to 261027. This is the absolute face, not a second confirmation of the same face
- scan_window_offsets_mm, scan_metric_geometry: the 261016 scan calibration: the PSV screenshot of a copy of the 261016 .svd with the points on the video frame, or the SUPERVISOR's decision on deviations 2 and 3 (M11 §15.4); or the 261027 .svd itself
- fe_origin_corner, fe_normal_face: an FE model built with a measured asymmetry (for example the edge thicknesses) or a SUPERVISOR convention recorded as CONVENTION_ONLY (M11 §15.2); a convention never becomes a physical registration

## Test conditions (261016 history, 261027 primary)

| Series | Item | Value | Provenance | Source |
|---|---|---|---|---|
| both | specimen | the same physical plate (PLATE-300x300x1mm) | HUMAN_CONFIRMED | owner, 2026-10-30 |
| both | measured points | the same physical points | HUMAN_CONFIRMED | owner, 2026-10-30 |
| both | measured face | the same face of the plate (which face is not stated) | HUMAN_CONFIRMED | owner, 2026-10-30 |
| both | setup change | four rubber bands → two rubber bands, and the plate turned 45° | HUMAN_CONFIRMED | owner, 2026-10-30 |
| both | why the first frequency is lower | the two-band suspension is freer than the four-band one (the owner's physical explanation; its numerical share is not determined) | HUMAN_CONFIRMED | owner, 2026-10-30 |
| 261016 | role | a separate historical measurement; 33.4491 Hz is never a fitting target | HUMAN_CONFIRMED | owner, 2026-10-30 |
| 261016 | suspension | four rubber bands | HUMAN_CONFIRMED | owner, 2026-10-30 |
| 261016 | orientation | the original position (before the 45° turn); the 301 mm edges horizontal | HUMAN_CONFIRMED | owner, 2026-10-30; M11 §13.1 |
| 261016 | excitation | shaker stinger near the bottom edge, left of centre seen from the shaker side (approximate) | HUMAN_CONFIRMED | owner, 2026-10-21 (M11 §13.1, §13.3) |
| 261016 | first record | 33.4491 Hz (Polymax_bravo, 10 records) | INSTRUMENT_RECORD | 300by300_plate_only_1mm_261016_POLYMAX.unv (M11 §9) |
| 261016 | scan distance | the PSV default 1 m; the real distance was not measured | LAB_RECORD | Read me.txt (laboratory note of the ROTATED delivery), SHA-256 4c03624a7591… |
| 261027 | role | the primary experiment for the free-free M11 FE model | HUMAN_CONFIRMED | owner, 2026-10-30 |
| 261027 | suspension | two rubber bands | HUMAN_CONFIRMED | owner, 2026-10-30 |
| 261027 | suspension detail | rubber bands and strings attached to two upper points along the nodal line of the first mode; stiffness, lengths and exact points not recorded | LAB_RECORD | Read me.txt (laboratory note of the ROTATED delivery), SHA-256 4c03624a7591… |
| 261027 | orientation | turned 45° from the 261016 position | HUMAN_CONFIRMED | owner, 2026-10-30 |
| 261027 | direction of the turn | clockwise as viewed from the Polytec system | LAB_RECORD | Read me.txt (laboratory note of the ROTATED delivery), SHA-256 4c03624a7591… |
| 261027 | turn of the scan grid | −44.17°: clockwise as viewed from the Polytec; every point id kept (289 of 289) | DERIVED | series_link of the 261016 and 261027 UNV geometries (plate_registration_readiness) |
| 261027 | excitation | a force reference channel (dataset 58 'Force * Velocity'); the sensor's point and mass are not recorded | INSTRUMENT_RECORD | SPname_files_ROTATED_261028\300by300_plate_only_1mm_ROTATED_Polytec_261027.unv |
| 261027 | first record | 18.6307 Hz (Polymax_bravo, 11 records) | INSTRUMENT_RECORD | SPname_files_ROTATED_261028\300by300_plate_only_1mm_ROTATED_Polytec_261027.unv |
| 261027 | scan distance | 1.15 m, measured (the PSV export places the points at z = −1.15 m) | LAB_RECORD | Read me.txt (laboratory note of the ROTATED delivery), SHA-256 4c03624a7591… |

Not established by the conditions:

- the separate numerical contributions of the suspension and of the 45° turn to the change of the frequencies
- that record 1 of 261016 (33.4491 Hz) and record 1 of 261027 (18.6307 Hz) are the same elastic mode
- a band stiffness from 33.4491 → 18.6307 Hz: the difference is not a quantitative measure of the suspension
- a Σ_setup repeat: the configuration was changed on purpose (not a D-053 repeat)
- that the 261016 experiment was wrong: it stays a valid measurement under its own conditions
- the absolute face towards the Polytec: 'the same face' is a relative fact
- any geometric registration: test conditions are never registration evidence

## 3. Owner questions

9 questions: see OWNER_EVIDENCE_REQUEST.md (answer fields empty).

- A1 (A. The face of the plate): Which absolute physical face of the plate faced the Polytec in the 261016 series: the face with the marking or the face without it?
- A2 (A. The face of the plate): Which source document or confirmation establishes that face (for example a photograph of the mounted plate from the Polytec side with the marking visible, a laboratory record, the owner's own observation)?
- B1 (B. The physical scan geometry): Which of these existing materials is available: (a) the original 300by300_plate_only_1mm_ROTATED_261027.svd; (b) a PSV screenshot of 261016 with the points on the video frame; (c) the original scanner angles and the camera frame / scale; (d) other independently measured coordinates of the points?
- C1 (C. The FE orientation): Is there a measured physical landmark that ties FE (0, 0) to a specific corner of the plate?
- C2 (C. The FE orientation): If there is none: should a geometrically founded FE variant with a measured asymmetry (for example the measured edge thicknesses) be prepared? Naming a corner by agreement alone stays CONVENTION_ONLY and is never physical evidence.
- D1 (D. The applicability of the model): Please state the actual attachment points of the two suspensions. Recorded now: two upper points along the nodal line of the first mode; the exact points are not recorded.
- D2 (D. The applicability of the model): Please state the length and known characteristics of the two rubber bands and strings. Recorded now: two rubber bands (owner, 2026-10-30); stiffness and lengths not recorded.
- D3 (D. The applicability of the model): Please state the place, mass and attachment of the force sensor. Recorded now: a force reference channel exists (dataset 58 'Force * Velocity'); the point, mass and attachment are not recorded.
- D4 (D. The applicability of the model): Please state the real thickness of the plate, including a possible non-uniformity inside it. Recorded now: 20 perimeter readings 0.71–0.94 mm (2026-10-21); the interior is not measured; edge means differ by about 13 % (edge 2 against edge 4).

## 4. Modal evidence

- Experimental records: 11 (Polymax_bravo — fitted modal records)
- Elastic FE modes: 14; rigid-body excluded: FE3, FE4, FE5, FE6
- Registration: NONE ACCEPTED — PHYSICAL_REGISTRATION_NOT_VERIFIED; MAC: NOT_COMPUTED; pairs: none; FIT / HOLDOUT: NOT_DECLARED

- No mode pair: no physical registration is accepted, so no EXP↔FE MAC is computed and no pair is formed.
- Frequency proximity never raises the status of a correspondence; the nearest FE frequency is diagnostic.
- FIT / HOLDOUT: none declared — no confirmed set exists, and none is formed automatically.
- Rigid-body FE modes are separated by the code's shape criterion: FE3, FE4, FE5, FE6.
- FE modes in the data read: 18 (FE3–FE20); 14 elastic.
- EXP1 = 18.6307 Hz and FE7 = 19.07217 Hz differ by +2.37 %: FREQUENCY_ONLY_DIAGNOSTIC — not a confirmed pair.
- The PRIORITY-1 research MAC rests on the 261016 diagnostic reconstruction carried by the DERIVED point map: it is shown only as RESEARCH_MAC_NOT_ADMISSIBLE and enters no identification.

| Kind | Record | Hz | Nearest | Δf % | Diagnostic | Close group | Research MAC | Pair | History |
|---|---|---|---|---|---|---|---|---|---|
| EXP | EXP1 | 18.630678 | FE7 19.0722 Hz | 2.37 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE7 0.905; next FE15 0.338 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP2 | 54.619271 | FE8 59.8742 Hz | 9.621 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE9 0.605; next FE8 0.566 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP3 | 63.495024 | FE9 62.0092 Hz | -2.34 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE20 0.309; next FE11 0.259 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP4 | 66.846668 | FE9 62.0092 Hz | -7.237 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE11 0.551; next FE17 0.244 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP5 | 74.214905 | FE11 72.1900 Hz | -2.728 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE10 0.484; next FE15 0.137 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP6 | 112.26551 | FE12 116.5804 Hz | 3.843 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE12 0.520; next FE17 0.203 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP7 | 145.935693 | FE13 167.4903 Hz | 14.77 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE14 0.786; next FE18 0.310 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP8 | 157.850827 | FE13 167.4903 Hz | 6.107 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE16 0.427; next FE19 0.379 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP9 | 169.184888 | FE14 168.6080 Hz | -0.341 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE13 0.260; next FE20 0.185 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP10 | 180.136339 | FE16 179.9016 Hz | -0.13 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE15 0.151; next FE16 0.131 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| EXP | EXP11 | 191.601861 | FE16 179.9016 Hz | -6.107 | FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR | — | FE18 0.542; next FE19 0.147 — RESEARCH_MAC_NOT_ADMISSIBLE | NONE — no admissible registration | — |
| FE elastic | FE7 | 19.07217 | — | — | FE frequency (no pair) | — | — | NONE | — |
| FE elastic | FE8 | 59.874157 | — | — | FE frequency (no pair) | — | — | NONE | PRIORITY-2: identity lost in M11_S4_E1_PLUS, M11_S4_E2_MINUS |
| FE elastic | FE9 | 62.009167 | — | — | FE frequency (no pair) | — | — | NONE | PRIORITY-2: identity lost in M11_S4_E1_PLUS, M11_S4_E2_MINUS |
| FE elastic | FE10 | 71.849854 | — | — | FE frequency (no pair) | FE10/FE11 | — | NONE | PRIORITY-2: order exchanged: M11_S4_E1_PLUS → FE11; M11_S4_E2_MINUS → FE11 |
| FE elastic | FE11 | 72.189987 | — | — | FE frequency (no pair) | FE10/FE11 | — | NONE | PRIORITY-2: order exchanged: M11_S4_E1_PLUS → FE10; M11_S4_E2_MINUS → FE10 |
| FE elastic | FE12 | 116.580429 | — | — | FE frequency (no pair) | — | — | NONE | — |
| FE elastic | FE13 | 167.490265 | — | — | FE frequency (no pair) | FE13/FE14 | — | NONE | PRIORITY-2: order exchanged: M11_S4_E1_PLUS → FE14; M11_S4_E2_MINUS → FE14 |
| FE elastic | FE14 | 168.607986 | — | — | FE frequency (no pair) | FE13/FE14 | — | NONE | PRIORITY-2: order exchanged: M11_S4_E1_PLUS → FE13; M11_S4_E2_MINUS → FE13 |
| FE elastic | FE15 | 174.797699 | — | — | FE frequency (no pair) | FE15/FE16 | — | NONE | PRIORITY-2: tracked only as the confirmed cluster term FE15+FE16 (its members exchange when E1 ≠ E2) |
| FE elastic | FE16 | 179.901611 | — | — | FE frequency (no pair) | FE15/FE16 | — | NONE | PRIORITY-2: tracked only as the confirmed cluster term FE15+FE16 (its members exchange when E1 ≠ E2) |
| FE elastic | FE17 | 213.199478 | — | — | FE frequency (no pair) | FE17/FE18 | — | NONE | PRIORITY-2: order exchanged: M11_S4_E1_PLUS → FE18; M11_S4_E2_MINUS → FE18 |
| FE elastic | FE18 | 213.952759 | — | — | FE frequency (no pair) | FE17/FE18 | — | NONE | PRIORITY-2: order exchanged: M11_S4_E1_PLUS → FE17; M11_S4_E2_MINUS → FE17 |
| FE elastic | FE19 | 295.775513 | — | — | FE frequency (no pair) | — | — | NONE | — |
| FE elastic | FE20 | 327.901031 | — | — | FE frequency (no pair) | — | — | NONE | PRIORITY-2: identity lost in M11_S4_E1_PLUS, M11_S4_E2_MINUS |

## 5. Observability

FE-only: the rank says which parameters the FE model distinguishes with the chosen modes. It does not say that the experiment determines them.

| Parameters | Rank | Of | Condition | Terms | Status | Valid for |
|---|---|---|---|---|---|---|
| E1 / E2 / G12 | 3 | 3 | 1.83 | 10 | FE_ONLY_MATHEMATICAL_OBSERVABILITY | S4R_0875_BASELINE (free-free, h 0.875 mm) only |
| E (E1 = E2) / G12 | 2 | 2 | 2.35 | 10 | FE_ONLY_MATHEMATICAL_OBSERVABILITY | S4R_0875_BASELINE (free-free, h 0.875 mm) only |

Experimental identifiability: **NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS** — no accepted physical registration and no admissible mode pair: no physical uncertainty of E or G12 is computed from an unconfirmed pair.

| Scenario | E1 MPa | E2 MPa | G12 MPa | Assumed pairs | Status |
|---|---|---|---|---|---|
| S0 | 56000.0 | 56000.0 | 4763.4 | EXP1 ↔ FE7 | RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY |
| H1 | 43467.0 | 43467.0 | 4804.4 | EXP1 ↔ FE7; EXP8 ↔ FE15+FE16 | RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY |
| H2 | 41952.8 | 41952.8 | 4810.3 | EXP1 ↔ FE7; EXP7 ↔ FE14 | RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY |

## 6. Reuse of the archived sensitivities

| Existing result | Parameterisation | FE identity | Branch tracking | Reuse status | Reason |
|---|---|---|---|---|---|
| PRIORITY-2 M11_S4_E1_MINUS (exit 0, completed True) | E1 = 53200 MPa (one *Elastic field, ±5 % of the baseline) | baseline INP 962f75f2fd5d… → INP 9206031e23f3…, ODB 38c6b0096a90… | 14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 | REUSABLE — FE-only observability at the M11 free-free baseline | a central ±5 % derivative of this FE model; valid only for it (free-free, h 0.875 mm, 3 mm S4R): never carried to a model with the suspension, the force sensor or another thickness without new solves |
| PRIORITY-2 M11_S4_E1_PLUS (exit 0, completed True) | E1 = 58800 MPa (one *Elastic field, ±5 % of the baseline) | baseline INP 962f75f2fd5d… → INP b3a631909ac0…, ODB f70b02982cbc… | 11 of 14 branches tracked at FE-to-FE MAC ≥ 0.90; lost: FE8, FE9, FE20; order exchanged: FE10→FE11, FE11→FE10, FE13→FE14, FE14→FE13, FE17→FE18, FE18→FE17 | REUSABLE — FE-only observability at the M11 free-free baseline | a central ±5 % derivative of this FE model; valid only for it (free-free, h 0.875 mm, 3 mm S4R): never carried to a model with the suspension, the force sensor or another thickness without new solves |
| PRIORITY-2 M11_S4_E2_MINUS (exit 0, completed True) | E2 = 53200 MPa (one *Elastic field, ±5 % of the baseline) | baseline INP 962f75f2fd5d… → INP 4200225bba4d…, ODB 5af4b61c7b90… | 11 of 14 branches tracked at FE-to-FE MAC ≥ 0.90; lost: FE8, FE9, FE20; order exchanged: FE10→FE11, FE11→FE10, FE13→FE14, FE14→FE13, FE17→FE18, FE18→FE17 | REUSABLE — FE-only observability at the M11 free-free baseline | a central ±5 % derivative of this FE model; valid only for it (free-free, h 0.875 mm, 3 mm S4R): never carried to a model with the suspension, the force sensor or another thickness without new solves |
| PRIORITY-2 M11_S4_E2_PLUS (exit 0, completed True) | E2 = 58800 MPa (one *Elastic field, ±5 % of the baseline) | baseline INP 962f75f2fd5d… → INP 3cd0ed6aa60b…, ODB aa5c9b707ddc… | 14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 | REUSABLE — FE-only observability at the M11 free-free baseline | a central ±5 % derivative of this FE model; valid only for it (free-free, h 0.875 mm, 3 mm S4R): never carried to a model with the suspension, the force sensor or another thickness without new solves |
| PRIORITY-2 M11_S4_G12_MINUS (exit 0, completed True) | G12 = 4750 MPa (one *Elastic field, ±5 % of the baseline) | baseline INP 962f75f2fd5d… → INP 909251e1990a…, ODB 8048f391b9f5… | 14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 | REUSABLE — FE-only observability at the M11 free-free baseline | a central ±5 % derivative of this FE model; valid only for it (free-free, h 0.875 mm, 3 mm S4R): never carried to a model with the suspension, the force sensor or another thickness without new solves |
| PRIORITY-2 M11_S4_G12_PLUS (exit 0, completed True) | G12 = 5250 MPa (one *Elastic field, ±5 % of the baseline) | baseline INP 962f75f2fd5d… → INP 1ddbe7fa3849…, ODB ea3e59140035… | 14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 | REUSABLE — FE-only observability at the M11 free-free baseline | a central ±5 % derivative of this FE model; valid only for it (free-free, h 0.875 mm, 3 mm S4R): never carried to a model with the suspension, the force sensor or another thickness without new solves |
| s_E (E1 = E2) = s_E1 + s_E2 (PRIORITY-2 table) | E1 = E2 scaled together | the same six solves (no joint E1 = E2 ±5 % solve exists) | the E1 and E2 jobs above | CONDITIONAL — a superposition of separate perturbations, not an independently solved E1 = E2 perturbation | PRIORITY-4 real solves along E1 = E2 (H1, H2 at −22 / −25 %) agreed with the log-linear approximation to ≤ 0.32 %; that is not a ±5 % central check at the baseline, so a joint ±5 % pair (2 solves) is needed unless the owner accepts the superposition |
| PRIORITY-1 secant S4R_0875_G12_10000 | G12: G12 5 000 → 10 000 | INP 36dce25dc5fb…, manifest 280810115027… | FE-to-FE tracking of PRIORITY-1 (PLATE_FE_SENSITIVITY.csv) | NOT_REUSABLE as a central derivative | a secant over ×2 / ×3: far outside the linear range of G12; it never replaces the S4 central ±5 % values |
| PRIORITY-1 secant S4R_0875_G12_15000 | G12: G12 5 000 → 15 000 | INP b5a504771a1c…, manifest f2b88494a626… | FE-to-FE tracking of PRIORITY-1 (PLATE_FE_SENSITIVITY.csv) | NOT_REUSABLE as a central derivative | a secant over ×2 / ×3: far outside the linear range of G12; it never replaces the S4 central ±5 % values |
| PRIORITY-1 secant S4R_0875_E1_50400 | E1: E1 56 000 → 50 400 | INP fd220f14755f…, manifest 91c523bddb2d… | FE-to-FE tracking of PRIORITY-1 (PLATE_FE_SENSITIVITY.csv) | NOT_REUSABLE as a central derivative | a secant over −10 %: not a central derivative at the baseline; it never replaces the S4 central ±5 % values |
| PRIORITY-1 secant S4R_0875_E2_50400 | E2: E2 56 000 → 50 400 | INP 5c08084b51c8…, manifest 688c0b1e78c5… | FE-to-FE tracking of PRIORITY-1 (PLATE_FE_SENSITIVITY.csv) | NOT_REUSABLE as a central derivative | a secant over −10 %: not a central derivative at the baseline; it never replaces the S4 central ±5 % values |
| PRIORITY-4 real solve S0 | G12 = 4763.4 MPa | INP 02234fe6b594…, ODB 2737f5fffe0f… | 14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 (PRIORITY-4) | VERIFICATION_RECORD_ONLY — not a sensitivity | a check of the approximation at a hypothetical point (RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY); not a derivative at the baseline |
| PRIORITY-4 real solve H1 | E1; E2; G12 = 43467; 43467; 4804.4 MPa | INP 512dec840310…, ODB ee8a250fa62a… | 14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 (PRIORITY-4) | VERIFICATION_RECORD_ONLY — not a sensitivity | a check of the approximation at a hypothetical point (RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY); not a derivative at the baseline |
| PRIORITY-4 real solve H2 | E1; E2; G12 = 41952.8; 41952.8; 4810.3 MPa | INP 553f5dc5623f…, ODB aa8a5de32339… | 14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 (PRIORITY-4) | VERIFICATION_RECORD_ONLY — not a sensitivity | a check of the approximation at a hypothetical point (RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY); not a derivative at the baseline |
| ±2.5 % linearity repeat | E (E1 = E2), G12 | — | — | NOT_AVAILABLE — never run | SPEC §6 S4 asks for it; it is a future stage with its own authorisation |

## 7. FE applicability — PLAN ONLY — not a run order: no Abaqus, solver, extraction, LM or Auto-ID is authorised or started by this program

| Variant | Available inputs | Missing inputs | Existing FE assets | Future runs | Owner authorisation | Purpose |
|---|---|---|---|---|---|---|
| A. free-free reference | the M11 model as extracted (package identity) | no support | the M11 package (manifest 354966dae212…, INP 962f75f2fd5d…, ODB 7daeb7e35adf…) | none (exists) | not needed (no run) | the existing M11 S4R_0875_BASELINE (no new job) |
| B. two-band suspension (261027) | two rubber bands (owner, 2026-10-30); strings at two upper points along the nodal line of the first mode (laboratory note) | band stiffness, length and the exact attachment points are NOT recorded: they come from the owner or the laboratory, or from a research range declared before the run and labelled RESEARCH_RANGE (never from 18.6307 or 33.4491 Hz) | none | PLATE_RC1_P1_B_TWO_BAND_SOFT, PLATE_RC1_P1_B_TWO_BAND_STIFF | NOT_GIVEN — a separate, explicit owner authorisation naming the job | the primary experiment's suspension: does it move the elastic FE modes? |
| C. four-band historical suspension (261016) | four rubber bands (owner, 2026-10-30); four corner straps in the 261016 PSV frame (M11 §13.3) | band stiffness, length and the exact attachment points are NOT recorded: they come from the owner or the laboratory, or from a research range declared before the run and labelled RESEARCH_RANGE (never from 18.6307 or 33.4491 Hz) | none | PLATE_RC1_P1_C_FOUR_BAND_SOFT, PLATE_RC1_P1_C_FOUR_BAND_STIFF | NOT_GIVEN — a separate, explicit owner authorisation naming the job | only the difference of the boundary conditions between the series; never a material identification from 33.4491 Hz, and no claim that the bands turn one mode into another before the shapes are identified — history only |
| D. force sensor / attachment | a force reference channel (dataset 58 'Force * Velocity') | the sensor's point and mass are NOT recorded: needed from the owner or the laboratory before this job | none | PLATE_RC1_P1_D_SENSOR_MASS | NOT_GIVEN — a separate, explicit owner authorisation naming the job | the mass (and rotary inertia, if recorded) of the force sensor at its point |
| E. thickness / model form | 20 archived edge readings (2026-10-21) | the interior thickness is not measured: the existing wedge model is a model-form alternative, never a fitted or invented thickness map | S4R_WEDGE: INP dcb639f14a00… and .dat d545876a72d7… (frequencies only; no extracted shapes) | PLATE_RC1_P1_E_WEDGE | NOT_GIVEN — a separate, explicit owner authorisation naming the job | the effect of the measured edge-thickness pattern on the elastic modes (model form, not a field) |

| Stage | Purpose | Existing results | New FE runs | Prerequisites | Authorisation |
|---|---|---|---|---|---|
| 1. FE applicability | does the test set-up (suspension, sensor, thickness) move the elastic FE modes? | variant A (the M11 package) | 4 (B ×2, D, E) + 2 optional (C, history only) | the suspension and sensor data (questions D), or a research range declared before the run | NOT_GIVEN — a separate, explicit owner authorisation naming the job |
| 2. E / G sensitivities | central ±5 % derivatives of the adopted FE model | PRIORITY-2: E1, E2, G12 ±5 % at the M11 free-free baseline (6 solves; FE8 / FE9 / FE20 lost when E1 ≠ E2) | M11 free-free kept: G12 0 (reuse) + E (E1 = E2) 2 (or 0 if the owner accepts the superposition); another adopted model (B / D / E): 4 | the adopted FE model; for a fit also a frozen registration and confirmed pairs | NOT_GIVEN — a separate, explicit owner authorisation naming the job |
| 3. Linearity of the sensitivities | the ±2.5 % repeat (SPEC §6 S4) | none (PRIORITY-4 checked the approximation far from the baseline, not ±2.5 %) | 4 | stage 2 | NOT_GIVEN — a separate, explicit owner authorisation naming the job |
| 4. Bounded fit (future) | a declared campaign (question, τ_mf, Σ, bounds) and the bounded LM with branch tracking | S0 / H1 / H2 are hypotheses only | ≤ 12 | a frozen registration, confirmed pairs, FIT / HOLDOUT frozen before the fit, stages 2–3 | NOT_GIVEN — a separate, explicit owner authorisation naming the job |
| 5. Check of the final FE model | one real solve of the final candidate with FE-to-FE tracking of every branch (as PRIORITY-4 did for S0 / H1 / H2) | none | 1 per final candidate | stage 4 | NOT_GIVEN — a separate, explicit owner authorisation naming the job |

## 8. What blocks a physical identification

- open registration fact: scanned_face
- open registration fact: grid_plus_v_edge
- open registration fact: scan_metric_geometry
- open registration fact: scan_window_offsets_mm
- open registration fact: fe_origin_corner
- open registration fact: fe_normal_face
- no accepted physical registration: no MAC, no mode pair, no FIT / HOLDOUT
- FE applicability: suspension_points NOT_RECORDED
- FE applicability: suspension_bands NOT_RECORDED
- FE applicability: force_sensor NOT_RECORDED
- FE applicability: thickness_map NOT_MEASURED_INSIDE
- M8 GATE NOT_MET; D-077 NO_GLOBAL_PARAMETER_VALUE; production Auto-ID BLOCKED
