# Owner evidence request — PLATE-300x300x1mm

- Specimen: PLATE-300x300x1mm
- Series: NEXP29/PLATE300-1MM/S261027-ROTATED
- Modal set: Polymax_bravo
- FE model: Abaqus M11 S4R_0875_BASELINE
- Experimental SHA-256: 76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d
- FE manifest SHA-256: 354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7
- INP SHA-256: 962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3
- Review fingerprint: 2029ab4eb8138b27c84f434ec171a3c7fb645f6f9fda212672455d93d142f786

States: SOURCES_VERIFIED · PHYSICAL_REGISTRATION_NOT_VERIFIED · MODE_PAIRS_NOT_CONFIRMED · NOT_READY_FOR_IDENTIFICATION · READY_FOR_OWNER_REVIEW

Answer each question with its source; leave a question empty when nothing exists. No value is derived from a frequency.

## A. The face of the plate

### A1. Which absolute physical face of the plate faced the Polytec in the 261016 series: the face with the marking or the face without it?

- Closes: scanned_face, grid_plus_v_edge
- Acceptable evidence: one answer (marked / unmarked) with its source; the owner's same-face statement then carries it to 261027. 'The same face as in 261016' is relative and does not answer it
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

### A2. Which source document or confirmation establishes that face (for example a photograph of the mounted plate from the Polytec side with the marking visible, a laboratory record, the owner's own observation)?

- Closes: scanned_face, grid_plus_v_edge
- Acceptable evidence: the document is chosen in Source Audit; it is recorded by SHA-256 and its reading is confirmed by the owner
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

## B. The physical scan geometry

### B1. Which of these existing materials is available: (a) the original 300by300_plate_only_1mm_ROTATED_261027.svd; (b) a PSV screenshot of 261016 with the points on the video frame; (c) the original scanner angles and the camera frame / scale; (d) other independently measured coordinates of the points?

- Closes: scan_window_offsets_mm, scan_metric_geometry
- Acceptable evidence: any one of (a)–(d); if none is available, both facts stay NOT_VERIFIED (the 277.7 × 277.0 mm UNV grid and the diagnostic 261016 reconstruction are never the physical window)
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

## C. The FE orientation

### C1. Is there a measured physical landmark that ties FE (0, 0) to a specific corner of the plate?

- Closes: fe_origin_corner, fe_normal_face
- Acceptable evidence: a measured landmark recorded with its source
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

### C2. If there is none: should a geometrically founded FE variant with a measured asymmetry (for example the measured edge thicknesses) be prepared? Naming a corner by agreement alone stays CONVENTION_ONLY and is never physical evidence.

- Closes: fe_origin_corner, fe_normal_face
- Acceptable evidence: an owner decision to prepare such a variant (its FE runs need their own authorisation)
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

## D. The applicability of the model

### D1. Please state the actual attachment points of the two suspensions. Recorded now: two upper points along the nodal line of the first mode; the exact points are not recorded.

- Closes: suspension_points
- Acceptable evidence: a measurement or record with its source; never derived from a measured or FE frequency
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

### D2. Please state the length and known characteristics of the two rubber bands and strings. Recorded now: two rubber bands (owner, 2026-10-30); stiffness and lengths not recorded.

- Closes: suspension_bands
- Acceptable evidence: a measurement or record with its source; never derived from a measured or FE frequency
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

### D3. Please state the place, mass and attachment of the force sensor. Recorded now: a force reference channel exists (dataset 58 'Force * Velocity'); the point, mass and attachment are not recorded.

- Closes: force_sensor
- Acceptable evidence: a measurement or record with its source; never derived from a measured or FE frequency
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

### D4. Please state the real thickness of the plate, including a possible non-uniformity inside it. Recorded now: 20 perimeter readings 0.71–0.94 mm (2026-10-21); the interior is not measured; edge means differ by about 13 % (edge 2 against edge 4).

- Closes: thickness_map
- Acceptable evidence: a measurement or record with its source; never derived from a measured or FE frequency
- Answer: 
- Source of the answer: 
- Evidence document (path and SHA-256): 

