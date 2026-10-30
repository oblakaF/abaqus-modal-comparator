# PLATE-WORKBENCH-RC1 — integrated workbench and physical registration preparation of the single plate

**Status: REVIEW_READY (2026-10-30; final correction §9). Research only, non-normative.** This report changes no specification, decision,
status, evidence, frozen registration or scientific gate. No Abaqus, solver, LM, Auto-ID, FE computation or iterative
estimation was run. No sandwich data were used in the new work.

- **Specimen.** `PLATE-300x300x1mm`, series `NEXP29/PLATE300-1MM/S261027-ROTATED`.
- **Working source.** `…\SPname_files_ROTATED_261028\300by300_plate_only_1mm_ROTATED_Polytec_261027.unv`, set
  `Polymax_bravo` (dataset 55, 11 fitted records, record 1 at 18.6307 Hz).
- **Base FE model.** M11 `S4R_0875_BASELINE`; its first elastic mode is FE 7 at 19.072 Hz.
- **History only.** The 261016 series (record 1 at 33.4491 Hz) is never a fitting target.
- **Identity.** The physical specimen of 261016 and 261027 is the same (`HUMAN_CONFIRMED`, owner, 2026-10-30). This
  confirms neither a registration, nor a mode pair, nor the FE boundary conditions.
- **Precedence.** Where `docs/experimental/new_exp_20261029/README.md` (NEW-EXP-R1, 2026-10-29) calls the identity
  provisional, the owner's later statement applies.

## 1. Git integration

| Item | Value |
|---|---|
| Base | `origin/main` `38929e7` (PR #120 merged; CI run 40955426450 success) |
| Merged | `research/plate-only-effective-properties` `0a61014`: NEW-GUI.6 + F1 (`20677f2`), Plate Study R1 / R2 / R2-F1 (CI run 40952342499 success) |
| Branch | `integration/plate-workbench-rc1`. Merge commit `158b7bb`: ordinary `--no-ff` merge, no conflict. Source branches unchanged; no history rewrite; no PR; no merge to `main` |
| Upstream | unset, so a plain `git push` can never reach `main` |

## 2. The integrated program (new GUI)

The full scenario was run on read-only copies of the real files (§8):

1. `RUN_NEW_GUI.cmd`.
2. Choose the 261027 UNV and the plate's own FE package (native dialogs).
3. Inspect both. The FE identity covers the whole extracted package: `manifest.json`, `geometry.csv` and the 18 mode
   CSV the loader reads (19 files; `odb_sha256: null`).
4. Choose `Polymax_bravo` (11 records); every record is shown, record 1 first.
5. Own Abaqus shapes and experimental shapes, each on its own coordinates (unpaired).
6. Analysis:
   - frequency diagnostic `FREQUENCY_ONLY_DIAGNOSTIC`;
   - the archived registration check refuses: the file is not the source of an accepted registration;
   - the verified comparison stays unavailable.
7. Plate Study:
   - identity and the archived record;
   - frequency table and the **new spectra chart**: two independent rows, no pairs;
   - FE sensitivities and the applicability of the initial model;
   - the **new workbench chain** and **registration readiness**;
   - the ±10 % parts and the prepared campaign;
   - readiness and outcomes;
   - export.
8. A changed UNV, mode CSV or geometry CSV after Inspect refuses Run plate study and Export (§8).

### The workbench chain (shown on the Plate Study page)

| Link | Status for 261027 | Source | Blocking reason |
|---|---|---|---|
| Source UNV | SHA-256 CONFIRMED | working source, identity recorded at Inspect and confirmed before the study | — |
| Physical specimen | HUMAN_CONFIRMED | owner, 2026-10-30; archived record of 2026-10-21 | — |
| Scan orientation | NOT_VERIFIED | lab note; PSV export | face, edges along +u / +v, turn reference, scan-to-edge offsets missing |
| FE model | INITIAL_FE_MODEL_OF_THE_SPECIMEN / APPLICABILITY_NOT_VERIFIED | M11 S4R baseline | suspension, excitation; FE ↔ physical edges |
| Registration | PHYSICAL_REGISTRATION_NOT_VERIFIED | `plate_registration_readiness` | 7 independent facts missing |
| Mode pairs | BLOCKED | comparator with a frozen registration | no MAC without a frozen physical registration |
| Parameter estimation | BLOCKED | bounded LM campaign (prepared) | pairs, S4 sensitivities, owner authorisation; NOT_IDENTIFIABLE |

## 3. PLATE-ONLY-R3: what the sources establish about the physical registration

### 3.1 Sources examined (read-only; originals unchanged)

| Source | Finding | Class |
|---|---|---|
| `…ROTATED_Polytec_261027.unv` (working source) | 289 points (17 × 17) at z = −1.15 m; Testlab dataset 55, Z only | INSTRUMENT_RECORD |
| `…ROTATED_261027.unv` (PSV export, FRF) | dataset 151 names `300by300_plate_only_1mm_ROTATED_261027.svd`, PSV 10.2.1.1, 27-Oct-26 11:38:17; dataset 164 SI metres; the same node coordinates | INSTRUMENT_RECORD |
| the same, dataset 58 (867 records) | response direction 3 (+Z of the scan frame); "Cross Spectrum, Ref1, Force * Velocity": the reference channel is a **force** | INSTRUMENT_RECORD |
| `Read me.txt` | plate turned 45° clockwise as viewed from the Polytec; suspended by bands and strings at two upper points; distance measured 1.15 m | HUMAN (lab note); reference position NOT stated |
| `Experiment_Freq_damping_LMS_Rotated.xlsx` | 65 pictures; the 11 plate-ROTATED ones are Testlab mode displays on the grid; no camera frame, no edge, no mark. The display triad turned 45° is a display convention | INSTRUMENT_RECORD / CONVENTION_ONLY |
| `.lms` Testlab project | binary, not read (its companion UNV is the FRF file) | — |
| plate `.svd` | named by the PSV export, **not delivered** | — |
| M11 §13–§17, figures R6.1–R6.5, owner photographs | edges 1–4 and their thickness rows, marked face (HUMAN); FE frame established in the INP; FE ↔ physical edges NOT_DETERMINED; the 261016 reconstruction is diagnostic | as recorded there |
| R6 extraction (FE geometry) | X 0–301, Y 0–300, Z 0; S4R normal +Z; no physical landmark | ESTABLISHED in the model |

### 3.2 Task A: scanner 261027 → physical plate

| Needed fact | State | Why |
|---|---|---|
| face towards the Polytec | NOT_VERIFIED | no record; the camera frame is in the undelivered `.svd` |
| physical edge along the grid's +u / +v | NOT_VERIFIED | no record links edges 1–4 to the scan frame |
| reference and direction of the 45° turn | NOT_VERIFIED | direction stated (lab note), reference position not; the grid angle 45.24° fixes nothing mod 90° |
| scan window relative to the edges | NOT_VERIFIED | grid 277.7 × 277.0 mm against the 301 × 300 mm plate; how the ≈ 23 mm margins split is unknown. **Superseded (§9.3):** the UNV grid is a representation, not a physical window |
| scale | INSTRUMENT_RECORD | SI metres, measured distance 1.15 m |
| measured DOF | INSTRUMENT_RECORD | +Z of the scan frame, pointing from the plate towards the Polytec |

### 3.3 Task B: physical plate → Abaqus FE

| Needed fact | State |
|---|---|
| FE X along the 301 mm edges 1 / 3 | HUMAN_CONFIRMED (M11 §13.1) |
| physical corner at FE (0, 0) | CANDIDATE only (A–D); NOT_DETERMINED: the FE model has no physical landmark (M11 §15.2) |
| face the S4R normal leaves | follows from the corner by right-handedness; not determined |

- **No selection by numbers.** A–D are symmetry-equivalent for the homogeneous M11 model, so a MAC cannot tell them
  apart, and none is chosen by MAC, frequency or shape.
- **A convention is not evidence.** A convention (for example picture D) stays `CONVENTION_ONLY` and is refused as
  physical evidence.
- **Possible future path (not authorised here).** An FE model carrying a measured physical asymmetry, for example a
  registered thickness map. The edge means 0.816 mm (edge 2) and 0.926 mm (edge 4) already differ by 13 %.

### 3.4 Evidence package

The package is outside git, in `PLATE_WORKBENCH_RC1_REVIEW\figures`:
- `fig_rc1_01_edges_and_faces.png`: edges 1–4 and the two faces;
- `fig_rc1_02_fe_axes.png`: FE X / Y / Z and the S4R normal;
- `fig_rc1_03_polytec_grid_261027.png`: the 261027 grid with its +u / +v axes;
- `fig_rc1_04_candidates_A_D_M11.png`: candidates A–D;
- `fig_rc1_05_spectra.png`: the spectra.

Each item carries its class: MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED, DERIVED, CANDIDATE, CONVENTION_ONLY or
NOT_VERIFIED. No physical coordinate is invented.

**Verdict: `PHYSICAL_REGISTRATION_NOT_VERIFIED`.** No FrozenRegistration was created or changed.

## 4. The registration readiness service

`src/services/plate_registration_readiness.py` (headless):
- **Input.** `Fact` (value, provenance, source, `derived_from`). MEASURED, INSTRUMENT_RECORD and HUMAN_CONFIRMED are
  independent; DERIVED counts only on independent facts; CANDIDATE, CONVENTION_ONLY and NOT_VERIFIED never count.
- **Two links.** It checks both links and returns the exact missing or refused facts.
- **Compatibility checks:**
  - handedness of face + edges, so a mirror image is refused;
  - FE normal against the origin corner;
  - the scan window plus offsets closing the 301 × 300 mm plan to the record's resolution;
  - the FE plan against the specimen;
  - out-of-plane DOF only.
- **Output when complete.** `EVIDENCE_COMPLETE_NOT_FROZEN` and the scan → FE transform the evidence implies.
- **MAC.** `mac_permitted` is False without a frozen registration; the service never freezes one, and no MAC is
  computed.
- **Real series.** `real_261027_evidence()` records today's sources. Result: NOT_VERIFIED, missing `scanned_face`,
  `grid_plus_u_edge`, `grid_plus_v_edge`, `rotation_reference`, `scan_window_offsets_mm`, `fe_origin_corner`,
  `fe_normal_face`. **Superseded by §9.4** (six facts, each naming the candidate it rests on).

**The facts that would close it** (none concerns the identity):
1. Which face faced the Polytec on 27.10, and which numbered edge lies towards the grid's +u and +v (figure 03). A
   photograph of the mounted plate from the Polytec side with the numerals visible would do.
2. A copy of `300by300_plate_only_1mm_ROTATED_261027.svd`, for the camera frame and the scan-to-edge offsets as in
   M11 §15.4.
3. For the FE link: either a decision to build an FE model with a measured physical asymmetry, or an explicit
   SUPERVISOR convention. A convention would still not be a physical registration.
4. The force sensor's position and mass, and the suspension points and bands (for FE applicability).

## 5. The prepared FE campaign (not authorised; nothing run)

`plate_workbench.campaign_specification()`; the template is `plate_campaign_template_rc1.json`.

| Item | Specification |
|---|---|
| Base model | `S4R_0875_BASELINE` (INP `962f75f2…`, extraction `354966da…`) |
| Varied | D (balanced: E1 = E2 scaled together), D66 (G12) |
| Conditional | D12 only if FULL_RANK at rcond 1e-3 (D-051); E1 ≠ E2 not before traceable axes (SPEC v1.1 §5.2) |
| Fixed | E3, G13, G23, ν13, ν23; plan; 3 mm S4R mesh; h = 0.875 mm (thickness is no FE nuisance column, D-052) |
| Mass / surface | ρ·h at the archived areal mass 1.3109 kg/m²; scanned surface ↔ mid-surface only through a frozen registration |
| Non-uniform thickness | uniform baseline; a thickness field only from a measured map of the whole plate; the wedge is a model-form sensitivity |
| Suspension | free-free; two-point strings, soft / stiff bracket; force-sensor attachment mass |
| Tracked modes | FE 7–20 with `track_branches`; clusters with `confirm_cluster` (FE 15 + 16 one term; FE 8 / 9 only as one confirmed cluster) |
| Sensitivities | SPEC §6 S4 central ±5 % in ln p plus the ±2.5 % repeat; the R6.6 / R6.7 secants do **not** replace them |
| FIT / HOLDOUT | declared after the frozen registration, before any fit; record 1 kept |
| Permutations / clusters | a refused tracking removes the term; no re-pairing by frequency |
| Stop / refusal | no frozen registration; MAC < 0.80; RANK_DEFICIENT (SPEC §6 S5); lost branch; LM not converged / bound / budget; pattern / Birge; D-044; M8 GATE NOT_MET; D-077 |
| Result kind | a **specimen calibration parameter** (effective D of this plate), RESEARCH_ONLY / NOT_A_MATERIAL_PROPERTY / NOT_TRANSFERABLE, never a material constant |

**Budget** (counts follow from the specification; no runtime is invented):

| Phase | Abaqus jobs | Prerequisite |
|---|---|---|
| 1. FE applicability: 2 suspension brackets, 1 attachment mass, 1 thickness model-form | 4 | suspension and sensor data |
| 2. S4 central ±5 % (D, D66) | 4 (6 with D12) | frozen registration and confirmed pairs |
| 3. ±2.5 % linearity repeat | 4 (6 with D12) | phase 2 |
| 4. bounded LM | at most 12 FE solves | FIT / HOLDOUT frozen; owner authorisation |

Phase 1 needs no registration. It is the only part a single owner decision could authorise now, given the
suspension and sensor data.

## 6. The ±10 % goal, part by part

| Part | Value | Status |
|---|---|---|
| frequency error, record 1 against FE 7 | +2.37 % | DIAGNOSTIC_ONLY: not a pair, not a material accuracy |
| shape identity | — | NOT_ESTABLISHED (no registration, no MAC) |
| uncertainty of D | — | UNKNOWN (the conditional 0.30–0.54 % is not real) |
| uncertainty of E / G | — | UNKNOWN |
| thickness | 24.5–24.9 % (3 × CV_edges) | ILLUSTRATIVE: edge readings only, the 0.84 / 0.81 mm reading unresolved |
| suspension | — | NOT_QUANTIFIED |
| FE model choice | — | NOT_AVAILABLE |
| ±10 % target | engineering goal | NOT_ACHIEVED |

Every material parameter of this plate is NOT_IDENTIFIABLE. The iterative-estimation button stays disabled, and
`request_iteration` always refuses.

## 7. What can be done now, and what blocks the iterative estimation

**Already possible in the program for this plate:**
- read the 261027 working source and the plate's own FE package, with whole-package identity and refusal on any
  change;
- view all 11 records and the FE shapes, unpaired;
- run the frequency diagnostic and see the spectra;
- check the archived registrations (refused);
- run Plate Study:
  - identity and the archived record;
  - FE sensitivities and the hypothetical design studies;
  - applicability, orientation chain and registration readiness;
  - ±10 % parts and the prepared campaign;
- export the study (JSON and Markdown).

**Still preventing an iterative estimation:**
1. **No physical registration.** The face and the edges of the 261027 scan, the turn reference and the scan-to-edge
   offsets are unknown, and the plate `.svd` is not delivered. FE ↔ physical edges cannot be determined for the
   landmark-free M11 model.
2. **No confirmed mode pair.** Without a frozen registration there is no MAC. 18.6307 vs 19.072 Hz is proximity
   only.
3. **FE applicability.** The suspension (bands, two points) and the force-sensor attachment are not modelled. The
   FRF has peaks up to 0.67 of record 1 (PROVISIONAL).
4. **E / G only.** There is no thickness map of the whole plate.
5. **Governance.** Σ_meas NOT_AVAILABLE; one plate (D-044 blocks PRODUCTION); M8 GATE NOT_MET; D-077
   NO_GLOBAL_PARAMETER_VALUE. The SPEC §6 S4 jobs, the campaign and the LM each need separate owner authorisation.

**Conditions of the next authorisation:**
- The owner can authorise **phase 1** (4 Abaqus jobs, FE applicability) once the suspension and sensor data are
  supplied.
- **Phases 2–4** need, first, the physical registration (§4 facts 1–3), frozen by a separate owner decision.

## 8. Tests and checks

**New tests:**
- `tests/test_plate_registration_readiness.py` (14):
  - the synthetic positive path with an independently known registration: every point maps to its true FE position;
    nothing frozen; no MAC;
  - refusals: unknown face, unknown FE ↔ edges, a convention offered as evidence, a non-independent derivation, a
    mirror image, a wrong normal, a window that does not close, in-plane DOF, another plan;
  - the real 261027 evidence;
  - statuses independent of the data;
  - the chain; the ±10 % parts; the campaign keeps every lock and is a specimen calibration parameter; the stored
    template;
  - the spectra PNG.
- `tests/test_plate_study_qt.py`: the page's chain, registration readiness, spectra, ±10 % parts and campaign; the
  first record kept; NOT_IDENTIFIABLE; the export sections.
- **Existing tests kept:**
  - UNV, mode CSV and geometry CSV changes refuse Run and Export (R2-F1);
  - `tests/test_fe_package_identity.py`;
  - NEW-GUI.1–6.

**Test results:**
- Targeted NEW-GUI.1–6, FE package identity, Plate Study and registration readiness: 258 OK, 1 skipped.
- **Full suite** (isolated LOCALAPPDATA, `NEW_GUI_REQUIRE_QT=1`): **3076 OK, 98 skipped**.
- `test_g2_eigfreq_precision` (16) is NOT_RUN: it reads `-work` data.

**Windows smoke: PASS.**
- **`RUN_NEW_GUI.cmd`** (native dialogs, UI Automation, isolated copies, Windows 150 %):
  - start in 4.0 s;
  - Inspect, `Polymax_bravo` 11 records;
  - FREQUENCY_ONLY_DIAGNOSTIC;
  - the registration check refused, the verified comparison unavailable;
  - Plate Study: HUMAN_CONFIRMED, PHYSICAL_REGISTRATION_NOT_VERIFIED, 2 × BLOCKED, gate disabled;
  - no page scroll bar at 900 × 680 or 1366 × 768;
  - exit 0, no process left.
- **In-process** (Qt `windows`, DPI 96 × DPR 1.5, isolated copies):
  - FE mode 7 and record 1 drawn, unpaired;
  - diagnostic; registration check refused;
  - Plate Study in 6.2 s with the chain, the 7 missing facts, spectra, ±10 % parts and campaign 4 / 4 / 4 / 12;
  - export;
  - export refused after a UNV change and after a mode CSV change, with the earlier reports byte-identical;
  - Run refused after a geometry CSV change;
  - close.
- **LEGACY_GUI (`RUN_PROGRAM.cmd`):** window "Abaqus–Simcenter Modal Comparator" in 3.8 s, closed, exit 0.

## 9. Final correction (2026-10-30)

This section corrects the RC1 interpretation of the test conditions and completes the review. Earlier sections are
kept as written; where §9 supersedes them, they say so.

### 9.1 Owner clarification — suspension and rotation, 2026-10-30

| Fact | 261016 | 261027 |
|---|---|---|
| Physical specimen | the same | the same |
| Suspension | 4 rubber bands | 2 rubber bands |
| Orientation | original | turned 45° |
| Measured physical points | the same | the same |
| Measured face | the same | the same |
| First record | 33.4491 Hz | 18.6307 Hz |
| Role | history (`HISTORY_ONLY`) | primary experiment for M11 (`PRIMARY_EXPERIMENT_FOR_M11_RESEARCH`) |

- **Provenance.** Every row is `HUMAN_CONFIRMED` (owner, 2026-10-30). The first records are `INSTRUMENT_RECORD`.
- **The earlier picture of the setup was wrong.** An earlier paraphrase had the suspension the same in both series.
  The owner's clarification takes precedence.
  - In this branch the code already separated the setups ("four corner straps" against "two upper points").
  - The correction adds the owner's band counts, the roles of the two series and the provenance of each fact.
  - Only the current interpretation in non-normative material changes; no primary measurement is altered.
- **The laboratory note, checked in the original.** `Read me.txt` (SHA-256 `4c03624a…`, read only) states:
  - "the plate was rotated 45° clockwise as viewed from the Polytec system";
  - "suspended using rubber bands and strings attached to two upper points along the nodal line of the first mode";
  - the node numbering changes when the plate is rotated;
  - the Z distance was previously left at the default 1 m; this time it was measured as 1.15 m.

  These facts keep their own provenance, `LAB_RECORD`, and are not mixed with the owner's confirmation.
- **Statuses.**
  - `HUMAN_CONFIRMED_SETUP_CHANGE`: four rubber bands became two, and the plate was turned 45°.
  - `OWNER_EXPLANATION_OF_FREQUENCY_CHANGE`: the two-band suspension is freer.
- **Not established.**
  - The separate numerical contributions of the suspension and of the turn.
  - That record 1 of the two series is the same elastic mode.
  - Any band stiffness derived from 33.4491 → 18.6307 Hz.
  - A Σ_setup repeat: the configuration was changed on purpose (not a D-053 repeat).
  - That 261016 was wrong.
  - The absolute measured face: "the same face" is a relative fact.
  - Any registration evidence.
- **Single source.** The service `plate_study.EXPERIMENT_CONDITIONS` holds these facts; the GUI and the export read
  them from there.

### 9.2 Link of the two scans (instrument geometry only)

`plate_registration_readiness.series_link` compares the two scan geometries. It uses only the point ids and the grid
axes; no mode, frequency or MAC enters.

**Inputs** (read only):
- 261016 PSV export `6d66eafe…`; its POLYMAX file `117c893b…` has the same geometry;
- 261027 `76db80ae…`.

**Result.**

| Item | Result | Status |
|---|---|---|
| Same physical points | owner, 2026-10-30 | `SAME_PHYSICAL_POINTS_HUMAN_CONFIRMED` |
| Point ids | both 1–289 on a 17 × 17 grid; 289 of 289 ids are kept by one proper grid symmetry (the identity) | DERIVED |
| Point-to-point map | id k ↔ id k | `POINT_TO_POINT_MAPPING_DERIVED`, not instrument-verified (needs the scanner angles and camera frames of both sessions; the 261027 `.svd` is not delivered) |
| Turn of the grid | −44.17° in the scan frame, i.e. clockwise as viewed from the Polytec (+Z towards it) | DERIVED. It agrees with the laboratory note (45° clockwise) and the owner (45°). The ids fix the turn modulo 360°, not only modulo 90° |
| Mirror relation | does not fit (no id kept) | consistent with the same face; says nothing about which face |
| UNV pitch ratio | 1.120 (z = −1 m default in 261016, −1.15 m measured in 261027) | a representation, not a physical scale |

The scan-frame numbering changes with the turn, as the laboratory note says, but on the plate each id stays with its
point. Different UNV ids for the same physical points would never make the plate another specimen: the service then
refuses the map and asks for the instrument records.

### 9.3 Correction: the 261027 UNV grid is not the physical window

M11 §15.4 found that the PSV UNV metric geometry is not a physical calibration:
- the 261016 UNV grid is near-square (aspect 0.9951);
- the scanner angles of the same points give an aspect of 0.7747;
- the diagnostic reconstruction gives 215.42 × 285.20 mm.

The 261027 UNV grid is again near-square (277.7 × 277.0 mm). With the owner's same points, the physical 261027 window
is the 261016 one (diagnostic, about 215.4 × 285.2 mm), not 277.7 × 277.0 mm. §3.2's window row is superseded.

The service now has a separate fact `scan_metric_geometry`: the scan coordinates must be physical positions, not a grid
representation. `scan_scale` stays an instrument record of units and distance only.

### 9.4 Physical registration of 261027 now

| Fact | Value | Provenance | State |
|---|---|---|---|
| `rotation_reference` | the 261016 position, turned 45° clockwise | DERIVED from the owner's 45° and the id-preserving turn | **closed** |
| `grid_plus_u_edge` | edge 1 | DERIVED: the 261016 grid +u pointed up (`.svd` video alignment, M11 §14.2) to edge 1 (top, M11 §13.1); id k ↔ id k keeps it | **closed** |
| `scan_scale`, `measured_dof`, `fe_x_along_edges` | SI, 1.15 m; +Z towards the Polytec; X along 1 / 3 | INSTRUMENT_RECORD / HUMAN_CONFIRMED | closed |
| `scanned_face` | unmarked (the 261016 face) | DERIVED, rests on `scanned_face_261016` (CANDIDATE: SCANNER_FACE = HUMAN_CONFIRMATION_PENDING, M11 §15.3) | open |
| `grid_plus_v_edge` | 2 if the unmarked face was scanned, 4 if the marked | DERIVED, rests on the same candidate | open |
| `scan_window_offsets_mm` | −u 7.02, +u 7.78, −v 29.19, +v 56.4 mm (the 261016 offsets) | DERIVED, rests on `window_offsets_261016` (CANDIDATE: DIAGNOSTIC_ONLY reconstruction) | open |
| `scan_metric_geometry` | the 261016 physical positions of the same points | DERIVED, rests on `metric_reconstruction_261016` (CANDIDATE) | open |
| `fe_origin_corner`, `fe_normal_face` | — | CANDIDATE (A–D); the M11 model has no landmark | open |

**Verdict:** `PHYSICAL_REGISTRATION_NOT_VERIFIED` (unchanged). No FrozenRegistration was created, no MAC computed and
no orientation chosen by numbers. The relative facts carry the 261016 evidence over and never raise it.

**What would close the open facts**, from records that already exist (`CLOSING_EVIDENCE`):
1. **`scanned_face` and `grid_plus_v_edge`:** the 261016 SCANNER_FACE answer (M11 §15.3: did the laser see the face
   without marks? one yes / no). The owner's same-face statement then carries it to 261027. This asks for the absolute
   face, not for a second confirmation of the same face.
2. **`scan_window_offsets_mm` and `scan_metric_geometry`:** any one of:
   - a PSV screenshot of a copy of the 261016 `.svd` with the points on the video frame;
   - the SUPERVISOR's decision on deviations 2 and 3 (M11 §15.4);
   - the 261027 `.svd` itself.
3. **`fe_origin_corner` and `fe_normal_face`:** either an FE model built with a measured asymmetry, or a SUPERVISOR
   convention recorded as CONVENTION_ONLY. A convention never becomes a physical registration.

### 9.5 Abaqus M11

M11 `S4R_0875_BASELINE` is the idealised free-free FE base of this study. Record 1 of 261027 (18.6307 Hz) against FE 7
(19.072 Hz) gives +2.37 %, `FREQUENCY_ONLY_DIAGNOSTIC`. This is consistent with a freer suspension. It does not show:
- that the two are the same mode;
- that M11 is physically validated;
- a material accuracy;
- an orientation.

Applicability to the test (two bands, the force sensor) is NOT_VERIFIED.

### 9.6 Program changes (no new GUI, no new service family)

- **`plate_study`:**
  - `EXPERIMENT_CONDITIONS` and `conditions()`;
  - `NOT_ESTABLISHED_BY_THE_CONDITIONS` and `CONDITIONS_CORRECTION`;
  - the roles of the two series;
  - the applicability rows "suspension" and "series difference: cause"
    (`HUMAN_CONFIRMED_SETUP_CHANGE / OWNER_EXPLANATION_OF_FREQUENCY_CHANGE`);
  - the orientation chain and the plan.
- **`plate_registration_readiness`:**
  - `series_link` and `grid_indices`;
  - the recorded link `SERIES_LINK_261016_261027`, with its inputs by SHA-256;
  - the new fact `scan_metric_geometry`;
  - a refusal of a non-positive or non-finite scale;
  - a refusal of a window off the plate (negative offset);
  - the "rests on" list for every non-independent derivation;
  - the supporting facts in the result;
  - `CLOSING_EVIDENCE`.
- **`plate_workbench`:**
  - the chain has six columns: link, status, confirmation, source, missing and blocking, diagnostics available. The
    third link is "Test conditions and scan orientation";
  - the ±10 % parts gain "experimental registration", and the frequency row is `FREQUENCY_ONLY_DIAGNOSTIC`;
  - `APPLICABILITY_VARIANTS` and `applicability_jobs()`.
- **Plate Study page and export:**
  - the conditions table;
  - the link of the two scans;
  - what would close the registration;
  - the six-column chain;
  - record schema `plate-workbench-rc1/study/v2`.

### 9.7 FE applicability variants (prepared; 0 Abaqus solves)

| Variant | Jobs | Role | Confirmed | Assumed / future sensitivity |
|---|---|---|---|---|
| A free-free | — (exists) | reference | M11 package identity | no support |
| B two-band (261027) | `PLATE_RC1_P1_B_TWO_BAND_SOFT`, `…_STIFF` | applicability | 2 bands (owner); two upper points on the nodal line (laboratory note) | band stiffness, length and points not recorded: from the owner or the laboratory, or a RESEARCH_RANGE declared before the run; never from 18.6307 or 33.4491 Hz |
| C four-band (261016) | `PLATE_RC1_P1_C_FOUR_BAND_SOFT`, `…_STIFF` | boundary-condition history only | 4 bands (owner); four corner straps (M11 §13.3) | as B; never a material identification from 33.4491 Hz; no claim that the bands change a mode before the shapes are identified |
| D force sensor | `PLATE_RC1_P1_D_SENSOR_MASS` | applicability | a force reference channel | the sensor's point and mass: needed before the job |
| E thickness / model form | `PLATE_RC1_P1_E_WEDGE` (source `S4R_WEDGE`) | applicability | 20 edge readings | interior thickness not measured; the wedge is a model form, never an invented map |

Each job records:
- the source INP and its SHA-256;
- the changed and the fixed values;
- the expected outputs (`.odb`, `.dat`, `.msg`, `.sta` and the extraction package; the extraction is its own Abaqus
  Python gate);
- the FE-to-FE mode identity (`track_branches`, `confirm_cluster`, rigid modes separated, no experimental MAC);
- the stop rules;
- "authorisation not given".

**Budget:**

| Phase | Jobs | Prerequisite |
|---|---|---|
| 1a. Applicability: B ×2, D ×1, E ×1 | 4 | band data or a declared research range; the sensor's point and mass |
| 1b. Optional history: C ×2 | 2 | phase 1a |
| 2. SPEC §6 S4 central ±5 % | 4 (6 with D12) | frozen registration and confirmed pairs |
| 3. ±2.5 % repeat | 4 (6 with D12) | phase 2 |
| 4. Bounded LM | ≤ 12 | FIT / HOLDOUT frozen; owner authorisation |

The template `plate_campaign_template_rc1.json` was regenerated from the service.

### 9.8 Tests and checks (final correction)

**New tests:**
- **`tests/test_plate_rc1_owner_clarification.py`** (12 tests):
  - the conditions of both series and their roles;
  - 33.4491 Hz never a target;
  - the explanation stays an explanation;
  - the provenance of every fact, with the laboratory note never passing for the owner;
  - a convention or a relative fact never closes the registration;
  - `series_link`: a kept-id turn is DERIVED in both senses and INSTRUMENT_VERIFIED only on both records; the owner's
    statement is kept apart from the map; mirrored, relabelled or missing ids are refused;
  - the recorded link, reproduced from the real files where present (skipped elsewhere);
  - gates: M8, D-077, the iteration refused, no registration written, no `install_*` layer.
- **`tests/test_plate_registration_readiness.py`** gains:
  - wrong scale, missing metric and a window off the plate are refused;
  - a relative fact never becomes an absolute one;
  - test conditions are never registration evidence;
  - the real series now has six open facts, each naming its candidate;
  - the six-column chain; the applicability jobs.
- **`tests/test_plate_study_qt.py`** gains the conditions table with its provenance.

**Updated expectations:**
- the chain link names;
- the "series difference: cause" state;
- `FREQUENCY_ONLY_DIAGNOSTIC`;
- the budget 4 / 2 / 4 / 4 / 12.

**Test results:**
- Targeted: 379 OK, 2 skipped. Covered: NEW-GUI.1–6 (Workspace, Preview, Shapes, Diagnostic, Registration and
  Analysis Qt, Workbench), FE package identity, APP-E2E.3, R7 shell modal safety, Plate Study and its Qt page,
  registration readiness and the owner clarification. Skipped:
  - the glyph test (offscreen has no font database);
  - the real archived comparisons (`NEW_GUI6_REAL_INPUTS` not set).
- **Full unittest:** 3092 OK, 98 skipped (isolated LOCALAPPDATA).
- **Full pytest:** 3029 passed, 114 skipped, 3641 subtests passed. The one warning is the existing collection warning
  for `TestRun` in `src/domain/specimen.py`.
- `test_g2_eigfreq_precision` (16) is NOT_RUN: it reads `-work` data.

**Windows smoke: PASS.**
- **`RUN_NEW_GUI.cmd`** (native dialogs, UI Automation, isolated copies):
  - start in 3.0 s; `Polymax_bravo` with 11 records; FREQUENCY_ONLY_DIAGNOSTIC;
  - the registration check refused and the comparison unavailable;
  - Plate Study:
    - four and two rubber bands, "turned 45° from the 261016 position";
    - "clockwise" as LAB_RECORD; the owner as the source;
    - HISTORY_ONLY and PRIMARY_EXPERIMENT;
    - SAME_PHYSICAL_POINTS and POINT_TO_POINT_MAPPING_DERIVED;
    - 18.6307 / 19.0722;
    - 2 × BLOCKED; the gate disabled;
  - no page scroll at 900 × 680 or 1366 × 768;
  - exit 0, no process left.
- **In-process** (Qt `windows`, DPI 96 × DPR 1.5, isolated copies):
  - FE mode 7 (19.0722 Hz) and record 1 (18.6307 Hz) shown, unpaired;
  - the six-column chain and the state columns visible;
  - export;
  - export refused after a UNV, a mode CSV and a manifest change, with the earlier reports unchanged;
  - Run refused after a geometry CSV change;
  - the originals unchanged.
- **LEGACY_GUI (`RUN_PROGRAM.cmd`):** window in 4.1 s, closed, exit 0.

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, frozen registrations, scientific gates and criteria, M8 / D-077, the 5 / 8 %
limits, every original file and every other branch. No new `install_*` layer. Abaqus solves in the final correction:
0.
