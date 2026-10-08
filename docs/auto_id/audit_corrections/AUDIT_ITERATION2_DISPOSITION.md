# External audit iteration 2: finding disposition (D-076)

**Audit:** `Audit_AutoID_0f15db9_iteration2.docx`, against snapshot `0f15db9` (M7 merge).
**Corrective branch:** `auto-id/m7b-diag` from `main` `7a34ee65f8a036866961c10dbd685a44ec957671`.
**Rule:** a finding is dispositioned on evidence. A recommendation that changes scientific policy is not
adopted here; it is deferred to a HUMAN / SUPERVISOR decision.

**Limitation of this disposition.** The audit document itself is not in the repository and was not available on
the worker's workstation. K1–K3, the V4 subject (τ_mf) and the SPECIMEN_ENGINEERING_CALIBRATION proposal are known
from the SUPERVISOR's instruction; the texts of V1–V3, V5–V8 and J1–J5 are not. Those findings are recorded as
`DEFERRED` pending the document — not as accepted or rejected.

## Critical findings

| Finding | Disposition | Evidence | Action |
|---|---|---|---|
| **K1** — the common E_in = 55.593 GPa was released as an engineering value although M5 is NOT_IDENTIFIABLE, against the SPEC v1.1 §1 upper rule | **CONFIRMED** | SPEC §1: no operating mode may turn a refusal into a number; SPEC §3: family inconsistency is a refusal condition. D-069/D-072/D-075 nevertheless labelled 55.593 GPa an `EFFECTIVE_MODEL_PARAMETER_ESTIMATE` / release candidate while M5 was NOT_IDENTIFIABLE | D-076 withdraws it: **HISTORICAL_RUN_A_OPTIMIZER_CANDIDATE** (diagnostic). Campaign report v2 separates `optimizer_candidate` from `formal_output`; a value is released only when M5 gives IDENTIFIED / WIDE. RUN_A: **NO GLOBAL PARAMETER VALUE**. Historical records unchanged |
| **K2** — SPEC §13 family consistency was never evaluated | **CONFIRMED** | The campaign verdict hard-coded `family_consistency = NOT_AVAILABLE`. Independent reconstruction from the frozen RUN_A journal: Δχ² **746.27**, Δdof **1**, p_χ² **2.6e-164**, bootstrap p **2.5e-4** (4000 / 4000 below), **FAIL**. Audit: 748.9, 1, ~7e-165 — difference +0.35 %, same conclusion; every admissible local model gives 745.8–747.3 (`M7_FAMILY_CONSISTENCY_CORRECTION.json`) | `services/family_consistency.py` (SPEC §13, χ² + parametric bootstrap, rank refusal); wired into the M5 guard; RUN_B is `NOT_EVALUABLE_RANK_DEFICIENT` (SP13: one FIT row for E_in + G12). M7 gate FAIL; M7 REWORK |
| **K3** — the SP-02 / SP-13 passports do not govern known physical inputs (plan, masses, face thickness, core height) | **CONFIRMED** | Both physical passports declare `plan_mm`, `masses_g`, `face_thickness_mm`, `core_height_mm` unavailable although `spec.txt` records values. CARBON-5G: SP-02 INP uses 0.45 mm faces with 5.7 % more face mass than measured and 24 g less adhesive mass; SP-13 INP uses 0.425 mm and reproduces its measured masses; SP-13 core is smaller than its faces (face-only overhang strips) | Additive governed records `docs/auto_id/specimens/SP0x.physical-measurements.json` (passports unchanged: their hashes are pinned in forward manifests and run identities). Uncertainty `NOT_AVAILABLE` everywhere (resolution is not an uncertainty). No value enters a model or a fit without a later decision |

## Other findings

| Finding | Disposition | Evidence | Action |
|---|---|---|---|
| V1 | DEFERRED | finding text not available to the worker | disposition on receipt of the audit text |
| V2 | DEFERRED | finding text not available to the worker | as above |
| V3 | DEFERRED | finding text not available to the worker | as above |
| **V4** — model-form tolerance τ_mf | **DEFERRED_TO_SPEC_V1_2_DECISION** | a scientific-policy change (new acceptance tolerance) | not implemented; HUMAN / SUPERVISOR decision |
| V5 | DEFERRED | finding text not available to the worker | disposition on receipt of the audit text |
| V6 | DEFERRED | finding text not available to the worker | as above |
| V7 | DEFERRED | finding text not available to the worker | as above |
| V8 | DEFERRED | finding text not available to the worker | as above |
| J1 | DEFERRED | finding text not available to the worker | as above |
| J2 | DEFERRED | finding text not available to the worker | as above |
| J3 | DEFERRED | finding text not available to the worker | as above |
| J4 | DEFERRED | finding text not available to the worker | as above |
| J5 | DEFERRED | finding text not available to the worker | as above |

## Audit observations addressed without a known finding number

These were named in the SUPERVISOR's instruction; their V/J numbers are not known to the worker.

| Subject | Disposition | Evidence | Action |
|---|---|---|---|
| Per-specimen estimates (SP-02 FIT ≈ 51.9, all strict ≈ 50.9; SP-13 4a ≈ 67, both ≈ 59 GPa) | CONFIRMED (independently recomputed) | 51.90 / 50.85 / 67.42 / 59.28 GPa (differences −0.01 / −0.09 / +0.63 / +0.48 %); the two SP-13 rows alone give 67.4 and 55.1 GPa (χ² 384, 1 dof) | `M7_PER_SPECIMEN_DIAGNOSTICS.json`, labelled DIAGNOSTIC_ONLY / NOT_A_MATERIAL_PROPERTY / NOT_A_RELEASE_VALUE |
| Torsional mode 1 excluded from the strict set although MAC ≥ 0.80 | CONFIRMED | SP-02: MAC 0.897, −15.8 %; SP-13: MAC 0.987, −28.4 %; FE mode 7, family Px:O\|Py:O\|nx:1\|ny:1 (torsion-dominated); excluded by the frequency gate | campaign report `excluded_mode_diagnostics` (reporting only; never fitted; 0.80 unchanged) |
| A common candidate can improve one specimen and worsen another | CONFIRMED | RUN_A: SP-02 max \|error\| 2.69 % → 6.06 % (worse), SP-13 9.05 % → 6.79 % (better); the old global `improved_or_consistent` was true | campaign report `per_specimen_agreement` (diagnostic; no threshold until SPEC v1.2) |
| SPECIMEN_ENGINEERING_CALIBRATION reporting class | DEFERRED_TO_SPEC_V1_2_DECISION | a scientific-policy change | not implemented; SPEC v1.1 unchanged; no SPEC v1.2 |
