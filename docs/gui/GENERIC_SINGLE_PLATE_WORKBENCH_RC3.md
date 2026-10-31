# PRIORITY-8 — Universal single-plate research workbench

**Status: REVIEW_READY.** Branch `feature/generic-single-plate-workbench-rc3`, from `939adc3` (PRIORITY-7 / RC2).

Everything here is **RESEARCH_ONLY / NOT_A_MATERIAL_PROPERTY**.

**Not done:**

- no Abaqus solve, Abaqus Python or extractor;
- no automatic registration and no new frozen registration;
- no pair chosen by frequency or MAC, and no MAC in an objective;
- no LM / Auto-ID campaign;
- no change to SPEC v1.1 / v1.2, DECISIONS, gates, frozen evidence or registrations.

**Unchanged:**

- M8 GATE NOT_MET;
- D-077 NO_GLOBAL_PARAMETER_VALUE;
- production Auto-ID BLOCKED.

## 1. What it is

The Plate Study page now has two tabs:

- **A. Current PLATE Study:** the accepted study of PLATE-300x300x1mm (M11), unchanged: its results, statuses, FE
  family and report.
- **B. New Single Plate — Research Workbench:** a research study of **any** single rectangular CFRP plate without a
  core.

The size, identifiers, files, FE model, evidence and sensitivities in B are the user's, and no M11 constant is used. A
second plate goes through the workflow with no change of Python code: the tests use a 420 × 260 mm and a
600 × 300 mm plate.

**Scope of version 1:**

- single rectangular plate, no core;
- parameters E_in_plane (E1 = E2) and G12;
- derived bending stiffnesses: D11 = D22, D66, and D12 only with a FIXED ν12;
- ν12 and the transverse constants are FIXED engineering constants, each with its provenance;
- E1 ≠ E2 is not enabled without a traceable warp / fill orientation (SPEC v1.1 §5.2);
- sandwiches (SP-02, SP-10, SP-13) are out of scope.

## 2. Architecture

The science lives in three services without Qt. The panel only edits and shows. No `install_*` layer was added.

| Module | Content |
|---|---|
| `src/services/generic_plate_workbench.py` | the passport (`Quantity` with unit, provenance, method, uncertainty; `Claim`; `ThicknessReading`; `Constant` FIXED / INITIAL); unit conversion; DERIVED quantities with their basis; the 9-point thickness rule; the `Study` (kinds PHYSICAL / SYNTHETIC_DEMO); sources by SHA-256 (link, status, verify, relocate); modal diagnostics; readiness; sensitivity plan; save / open (JSON); Markdown / JSON / CSV export |
| `src/services/generic_plate_evidence.py` | the physical registration evidence of a plate whose plan comes from its passport: the rules of `plate_registration_readiness` (PLATE-WORKBENCH-RC1), with the plate size and tolerance as inputs; provenance classes; result EVIDENCE_COMPLETE_NOT_FROZEN or PHYSICAL_REGISTRATION_NOT_VERIFIED, never frozen, no MAC |
| `src/services/generic_plate_offline_study.py` | the import of an FE sensitivity table of THIS FE model and specimen (`amc/fe-sensitivity-table/v1`); the declared observation set (`amc/declared-observations/v1`); the gate; the rank check (existing M5 service through `plate_study.design_study`); the bounded offline study with the existing `identification_step.run_bounded_lm` on a log-linear approximation; derived D values; `release_material_values` always refuses |
| `src/new_gui/generic_plate_panel.py` | section B: eight steps (step buttons over the step pages), forms, tables, the independent shape views |
| `src/new_gui/window.py` | the Plate Study page holds A and B as two tabs; the Workspace inputs reach B; B is busy / cancelled with the window |

**Reused, not duplicated:**

- the importers and the FE / experimental previews (Workspace);
- `plate_study.elastic_modes`, the code's rigid-body shape criterion;
- `identification_clusters.cluster_triggers`, the 3 % trigger of SPEC §12.4;
- `plate_registration_readiness.grid_axes` and its provenance classes;
- `plate_study.design_study`, i.e. `practical_identifiability`, with rcond 1e-3;
- `identification_step.run_bounded_lm`;
- `ShapePanel` and `DiagnosticTable`.

## 3. The eight steps

1. **Specimen & Test Setup.**
   - Separate `design_id`, `physical_specimen_id` and `test_run_id`, the test date and the method.
   - The statements below, each with its provenance and source:
     - suspension;
     - excitation;
     - measured face;
     - instrument axes;
     - measured DOF;
     - material orientation;
     - layup;
     - FE model and version.
   - A statement without provenance is refused.
2. **FE and Experimental Inputs.**
   - The files read in the Workspace (FE manifest, experimental file) and the modal set are linked by SHA-256.
   - A different file or set is shown at once (CHANGED / NOT_CHOSEN), and the diagnostics, declaration and offline
     result are removed. A diagnostic of changed inputs is refused.
   - **Verify recorded sources** re-hashes the files. **Choose a moved source file...** accepts a new path only with
     the recorded SHA-256.
   - A synthetic study takes synthetic inputs instead (`amc/synthetic-plate-inputs/v1`).
3. **Measurements & Geometry.**
   - Length, width, mass and density, each with a value, unit (mm / cm / m / in, g / kg, kg/m³ / g/cm³, MPa / GPa / Pa),
     uncertainty, provenance, method and source.
   - The thickness readings: position, value, method, provenance and source.
   - The engineering constants, FIXED or INITIAL.
   - An unknown value stays NOT_AVAILABLE, and a value without provenance is refused.
   - DERIVED values with their basis: areal density, mean thickness, density from mass.
   - The observed thickness scatter is never called an instrument uncertainty.
   - Fewer than 9 measured points blocks the normative thickness prior (SPEC v1.1 §5), not the viewing.
4. **Physical Registration Evidence.**
   - The ten facts of the two links, each with its value, provenance and source.
   - The checks:
     - the edges are adjacent;
     - the handedness (a mirror is refused);
     - the measured DOF is Z only;
     - the FE normal is consistent with the origin corner;
     - the FE plan matches the passport plan within the passport's own length / width uncertainty;
     - the scan window with its offsets closes the plate.
   - A complete set is **EVIDENCE_COMPLETE_NOT_FROZEN**: it is not a registration, no MAC is computed and nothing is
     frozen.
   - SYNTHETIC facts count only in a synthetic study.
5. **Modal Diagnostics.**
   - Every experimental record, EXP1 included. An FRF peak or an ambiguous record is shown as not admissible.
   - Every elastic FE mode, the first elastic included. Rigid-body modes are excluded by the code's shape criterion,
     not by a frequency threshold.
   - For each record, the nearest and second FE frequency with Δf = 100 (f_FE − f_EXP) / f_EXP.
   - Close groups from the 3 % trigger.
   - **Pairs: none**, MAC NOT_AVAILABLE.
   - FE and experimental shapes are shown in independent views.
6. **Parameter Observability.** Every condition is shown apart:
   - source identity;
   - modal-fit quality;
   - geometry and mass;
   - material axes;
   - registration evidence;
   - the owner's registration decision;
   - admissible pairs;
   - close groups;
   - sensitivities of this FE model;
   - rank and condition;
   - FIT / HOLDOUT;
   - uncertainties;
   - FE model applicability.

   The result is **NOT_READY_FOR_IDENTIFICATION** with every reason. Without sensitivities the plan is shown:

   - 2 × n_p Abaqus solves of this plate's own model, each a separate HUMAN gate;
   - the inputs needed;
   - the output schema.

   Nothing is run.
7. **Offline Research Study.** The button is enabled only when the gate is empty:
   - an identified FE model;
   - consistent sources (physical study);
   - diagnostics with admissible records;
   - complete evidence;
   - the owner's decision `ADMISSIBLE_FOR_RESEARCH_COMPUTATION` (HUMAN_CONFIRMED with its reference; SYNTHETIC only in
     a synthetic study), recorded by the program, never made by it;
   - a sensitivity table of this FE model and specimen with every used row tracked;
   - a declared observation set: FIT / HOLDOUT, parameters, start, bounds, σ with provenance, `holdout_declared`;
   - FIT terms ≥ parameters;
   - FULL_RANK.

   The run:

   - `run_bounded_lm` in ln p over the log-linear approximation;
   - HOLDOUT terms are reported and never enter Φ;
   - beyond the table's solved range a value is marked EXTRAPOLATION;
   - D11 / D66 / D12 are DERIVED with the assumptions stated;
   - the result is **DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE / NOT_A_MATERIAL_PROPERTY**, and
     `approved_material_values` is NOT_AVAILABLE.
8. **Report & Save.**
   - The study JSON (`amc/generic-single-plate-study/v1`) holds:
     - the passport, sources (SHA-256), modal set and evidence;
     - the registration *as computed*, recomputed on opening; a stored "frozen" or "accepted" is ignored;
     - the imported files with their SHA-256, checked again at every use;
     - the diagnostics, offline result, refusals and history.
   - No FE file is written into it.
   - Export writes Markdown, JSON and CSV (frequencies, readiness, thickness, offline terms).

## 4. The synthetic demonstration (`docs/examples/generic_single_plate_demo`, made by `research/generic_single_plate_demo/make_demo.py`)

**The plate:** `DEMO-SPB-420x260`, 420 × 260 × 2.2 mm, its own FE model id, 12 experimental records and 10 elastic FE
modes.

**What it holds:**

- the sensitivity table of its own FE model;
- a declared observation set (FIT EXP1, 2, 3, 5, 6; HOLDOUT EXP4, 7, 8) with a SYNTHETIC registration decision;
- a two-row declaration with nearly collinear sensitivities.

**Result:**

- the offline study recovers the declared truth E_in_plane = 52 000 / G12 = 4 300 MPa as 51 975 / 4 305 MPa (CONVERGED,
  6 evaluations);
- the two-row declaration is refused as RANK_DEFICIENT (rank 1 < 2).

Every value is labelled **SYNTHETIC_DEMONSTRATION — NOT A PHYSICAL EXPERIMENT**.

## 5. What works for a new plate now, and what stays blocked

**Works:**

- passport, measurements, units and provenance;
- linking the real files by SHA-256, and detecting changed and moved files;
- frequencies and shapes;
- the frequency-only diagnostics;
- the evidence checklist of the registration;
- the readiness with every reason;
- the sensitivity plan;
- save, reopen and export.

**Works only after the owner's separate decisions and inputs.** The offline research study needs all of these:

- an admissible-registration decision;
- a sensitivity table of the plate's own FE model (Abaqus solves under their own HUMAN gate);
- a declared observation set.

**Blocked:**

- a frozen registration;
- the verified MAC comparison of a new plate (only the existing archived registrations SP-02 / SP-13 apply);
- any released material value;
- production Auto-ID;
- E1 ≠ E2.

**Needed for the first real study of another plate:**

- its own identifiers and FE model (an extracted package) with its SHA-256;
- a fitted modal set (curve-fitted records);
- length, width and mass with their uncertainty;
- 9+ measured thickness points;
- the material orientation;
- the ten registration facts from the instrument and the owner;
- the owner's registration decision;
- the central ±5 % sensitivities of its FE model (2 × n_p Abaqus solves, a separate gate);
- the declared FIT / HOLDOUT set.

## 6. Tests

`tests/test_generic_single_plate_workbench.py` has 27 tests, one or more for each of the 20 required points:

1. two plates;
2. passport and serialisation;
3. units;
4. thickness and incomplete measurements;
5. changed SHA-256 and moved file;
6. a changed modal set;
7. no registration;
8. wrong axes and DOF (opposite edges, mirror, in-plane DOF, FE normal, FE X axis, each weak provenance, a window
   that does not close);
9. close and permuted modes;
10. EXP1 and the first elastic FE mode kept;
11. insufficient rank;
12. no sensitivities, with the plan;
13. sensitivities of another FE model or specimen, including the M11 manifest, E1 ≠ E2 and another baseline;
14. no unconfirmed fit (no decision, open evidence, synthetic declaration in a physical study);
15. an admissible offline run on declared synthetic data;
16. FIT / HOLDOUT kept, with Φ over FIT only;
17. no released material value;
18. save and reopen, with a forged stored status ignored;
19. export;
20. the panel in the window:
    - nothing evaluated at start-up;
    - study A kept;
    - the demo through the panel without any process started;
    - a physical study without inputs;
    - the link following the Workspace;
    - the layout choices that keep the page narrow (font-independent: two columns of step buttons, no buttons side
      by side). The real width is checked by the Windows smoke.

`tests/test_windows_portable_rc3.py` has 5 tests.

The separation test `tests/test_new_gui1_workspace.py` lists the new module `generic_plate_panel.py`.

The regression of Plate Study, NEW-GUI 1–6, SP-02, Research Results, SP-10 PRIORITY-6/7 and RC1 / RC2 packaging
passes.

The full results are in `WINDOWS_PORTABLE_RC3.md`.

## 7. Windows GUI smoke (RUN_NEW_GUI.cmd)

`RUN_NEW_GUI.cmd` on the final code and the portable EXE ran the same route. The table is in
`WINDOWS_PORTABLE_RC3.md` §Acceptance.

**Real moved copies.** The PLATE files were used as a new physical study:

- statements and values without provenance are refused;
- the passport is applied;
- both SHA-256 match;
- EXP1–EXP11 and FE7… are shown, with **Pairs: none**;
- the evidence is NOT_VERIFIED and the readiness NOT_READY;
- the offline study is disabled, with the reasons;
- the report is exported, and the study is saved and reopened;
- after a file change: CHANGED, and the diagnostics are refused.

**The synthetic demo:** CONVERGED at 51 975 / 4 305 MPa, labelled.

**Also checked:**

- a cancelled read of the 3.1 GB package;
- SP-02 VERIFIED_COMPARISON and its export;
- Plate Study A;
- PLATE, S0 / H1 / H2, SP-13 and SP-10;
- 900 × 680 and 1366 × 768;
- no Abaqus process.

**Corrections found by these runs:**

- step tabs are replaced by two columns of step buttons, so no tab hides behind scroll arrows;
- the "&" in step titles is shown, not used as a mnemonic;
- the claim provenance lists are named for UI Automation;
- the tab label "B. New Single Plate" is short, with the full title as its tooltip and in the section.

## 8. Limits

- **Version 1 scope.** A single rectangular plate only: no core, no curved shape, no in-plane DOF registration.
- **Units.** The FE geometry of a package is taken in mm, as everywhere in the project.
- **Diagnostics run synchronously.** They are fast for plate-sized packages. A 1.7 M-node package (SP-10) is not a
  single-plate case.
- **The registration decision.** The program records the owner's decision from a declaration file and never checks
  who made it. Its provenance and reference are shown everywhere the result is.
- **No new frozen registration.** A new plate therefore never reaches a verified MAC comparison in this version.
