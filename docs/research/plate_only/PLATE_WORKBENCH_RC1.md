# PLATE-WORKBENCH-RC1 — integrated workbench and physical registration preparation of the single plate

**Status: REVIEW_READY (2026-10-30). Research only, non-normative.** This report changes no specification, decision,
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
| scan window relative to the edges | NOT_VERIFIED | grid 277.7 × 277.0 mm against the 301 × 300 mm plate; how the ≈ 23 mm margins split is unknown |
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
  `fe_normal_face`.

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

## Not changed

SPEC, DECISIONS, STATUS, EVIDENCE, frozen registrations, scientific gates and criteria, M8 / D-077, the 5 / 8 %
limits, every original file and every other branch. No new `install_*` layer.
