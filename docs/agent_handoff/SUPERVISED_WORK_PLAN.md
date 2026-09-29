# Supervised Work Plan — Source-Bound Material Identification Pipeline

**Audience:** a SUPERVISOR agent that controls a separate WORKER agent, step by
step. The human owner of the repository relays or observes the exchange and
makes the decisions marked **HUMAN GATE**.

**Plan date:** 2026-09-28. Repository: `abaqus-modal-comparator`, branch `main`.
Local `main` is 1 commit ahead of `origin/main` (`97b5c1f`), with a large
amount of uncommitted work (see §2).

**Roadmap v2 update:** 2026-09-29, at HEAD `0f40c65`. The live status and the
execution queue are in the next section. §2 below is the original 2026-09-28
snapshot and is kept as history.

---

## Current state and execution queue (roadmap v2, 2026-09-29)

A new agent should read this section first, then §0–§1 for the workflow rules,
which are unchanged.

### Checkpoint

- Accepted HEAD: `0f40c65c4326550c94557377502591a24d2e17ef`
  (`feat(evidence): separate SP13 historical import from execution`).
- `origin/main` is still `05928dc`; local `main` is 22 commits ahead. Nothing
  has been pushed.
- Recent checkpoints:
  - `5cb5fd9` feat(runner): enforce scientific evidence provenance
  - `0f40c65` feat(evidence): separate SP13 historical import from execution

### Execution queue

```
CURRENT: C5 = CLOSED
NEXT:    C6-R1     — model-driven evidence view
THEN:    C6-R2     — model-driven UI
         C6-R3     — clean-checkout presentation tests
         C6-HARDEN — unit provenance audit
THEN:    Phase 7.1 — mode pairing / tracking stability audit
         Phase 7.2 — objective policy audit
         Phase 7.3 — identifiability threshold policy
         Phase 7.4 — close / repeated mode policy
THEN:    Phase 8   — uncertainty and independent validation
```

Open v1 items that this queue does **not** cancel (see "Status of v1 steps"
below). The SUPERVISOR places them in the queue:

- Step 4.3 remnants (A-2, A-15) that C6-R2 does not cover.
- Step 4.4 (A-7, stale state).
- Phase 5 (persistence v3, A-8 to A-10).
- Phase 6 (A-11 to A-14).
- Phase 7P (production connection of the GUI pages; this was Phase 7 in v1).

The v1 boundary still holds. Phases 0–5 are the software/data-integrity
acceptance, and they must be ACCEPTED before Phase 7P and before any Phase 8
material-property claim. The Phase 7 audits are read-only and may run before
Phase 5.

### C5 status: CLOSED

- C5 production provenance: CLOSED (`5cb5fd9`).
- C5 historical import: CLOSED (`0f40c65`).
- C5: CLOSED. Do not reopen C5 unless a later, explicit hardening step
  requires it, for example C6-HARDEN.

The C5 architecture has two paths, which must stay separate.

**BOUND production evidence:**

```
FrozenRegistration-bound session -> production runner -> BOUND evidence
```

- The runner derives the `EvidenceScientificBinding` only from the session's
  model id, model hash, `registration_hash` and experimental SHA-256.
- It refuses UNBOUND or mismatched evidence and mismatched input chains.
- It requires `parent_ids == (sensitivity_id, identifiability_id)` exactly.

**Historical SP13:**

```
historical artifacts -> load_frozen_sp13_evidence()
  -> UNBOUND / HISTORICAL_NOT_REVALIDATED evidence -> presentation/view
```

- Historical SP13 **must not** go through the production runner.
- There is no historical bypass and no `allow_unbound_evidence`.
- **SP13 is a specimen and a data source, not an identification method.**

### Inherited uncommitted C6 work (do not reset, clean, revert or overwrite)

- Modified: `src/material_identification_ui.py`, `src/ui_policy.py`,
  `tests/test_material_identification_ui.py`.
- Untracked: `src/material_identification_evidence_view.py`,
  `tests/test_material_identification_evidence_view.py`,
  `tests/test_material_identification_evidence_view_integration.py`,
  `tests/test_material_identification_application_wiring.py`.

### C6-EVIDENCE-VIEW-GATE = READY

- Baseline: the combined C4–C6 suite (12 modules) gives **141 tests OK, 2 skips,
  0 failures**. The full suite was not re-measured for v2.
- The two skips are both in
  `tests/test_material_identification_evidence_view_integration.py`:
  1. Stage A sensitivity rendering;
  2. Stage A identification rendering.

The gate found **three** Stage A presentation defects in
`src/material_identification_evidence_view.py`:

- **A. Sensitivity.**
  - The view requires `face_Ex/face_Ey/face_Gxy` columns in
    `raw_sensitivity_matrix`, and fails with
    `InvalidEvidenceError: raw_sensitivity_matrix row.face_Ex is required.`
  - Stage A evidence already contains `parameter_ids`, `observation_ids` and
    `scaled_sensitivity`.
  - No evidence-schema change is required.
- **B. Identification.**
  - The view hardcodes Ex/Ey/Gxy and MPa, so Stage A renders as empty
    `('Ex', None, 'MPa')` rows.
  - Stage A evidence contains the D11/D12/D66 values and `parameter_unit`.
  - No evidence-schema change is required.
- **C. Identifiability (hidden defect; no test yet).**
  - Stage A identifiability does not raise.
  - It silently renders observability as Ex/Ey/Gxy "unavailable" instead of
    the actual D11/D12/D66 statuses.
  - Rank, condition number, singular values and the weakest direction are
    already generic, because they read the stored `parameter_order`.

### Status of v1 steps (2026-09-29)

| v1 step | Status | Checkpoint |
|---|---|---|
| 0.1 Inventory | done | — |
| 0.2 Tk tests | done | `3596c4f` |
| 0.3 D-COMMIT | done; continues for every commit | `e708bac`, `4c949f7`, … |
| 0.4 D-ANALYSIS | done (manifest + `.gitignore`) | `84d8ec4` |
| 1.1 Content-hash identity | done | `287d618` |
| 1.2 FE geometry identity | done (v2 = nodes + coordinates only) | `fbf9263`, `b12953a` |
| 1.3 `FrozenRegistration` | done | `4cfd96b` |
| 1.4 Registration factory | done | `6f1ec3c` |
| 1.5 Registration in re-pairing (A-1) | done: explicit node map, Policy B FE availability, frozen production pairing | `490ec85`, `424a0ca`, `a2b211b` |
| 2.1 D-FREQONLY (A-3) | done | `e224b5c` |
| 2.2 Identifiability split (A-5) | rank-deficiency hard block done. The reason-string override for poor conditioning is **not implemented**; the human requires a reason before it is persisted | `34a2894` |
| 3.1 Complex, rank-aware family residual (A-4) | done | `151f658` |
| 4.0 D-WORKFLOW | decided (§2.4) | — |
| 4.1 `IdentificationModelDefinition` (A-6) | domain and session done; evidence view → C6-R1; UI → C6-R2 | `40616be`, `c8e8d51` |
| 4.2 Evidence binding | done (session → registration, evidence → model + registration, runner provenance) | `1875d68`, `de8f192`, `5cb5fd9` |
| 4.3 GUI presentation (A-2, A-15) | open; overlaps C6-R2 | — |
| 4.4 Stale state (A-7) | open | — |
| Phase 5 (A-8, A-9, A-10) | open | — |
| Phase 6 (A-11 to A-14) | open | — |
| Phase 7P (was v1 Phase 7) | open; requires Phases 0–5 ACCEPTED | — |
| Phase 8 (A-16) | open; D-ABAQUS gate per run | — |

### Known issues

- **Flaky committed test.**
  `test_registration_factory.test_no_full_model_contamination` fails about
  1 run in 6. It checks that "d11" is absent from a serialized registration,
  but a random SHA-256 hex digest can contain "d11". Not fixed; out of scope
  so far.
- **The runner does not check `parameter_unit`.**
  `IdentificationExecutionOutput.parameter_unit` (default `"MPa"`) is not
  enforced against the model. See C6-HARDEN.
- **Misleading committed key name.** The identification content key
  `properties_MPa` can hold N·m values for Stage A. Never infer units from
  this key name.

---

## 0. How to use this document

### Roles

| Role | Responsibility |
|---|---|
| **SUPERVISOR** | Reads this plan and the repository. Issues exactly **one step at a time** to the WORKER using the command template (§1.3). Verifies every report independently (§1.5) before issuing the next step. Stops at every HUMAN GATE and asks the human. Never edits code itself. |
| **WORKER** | Executes only the step it was given, inside the allowed files. Reports using the report template (§1.4). Never starts the next step on its own. |
| **HUMAN** | Owns the decisions marked HUMAN GATE, approves commits, and is the only party allowed to authorize any Abaqus execution or any `git push`. |

### Loop

```
SUPERVISOR reads plan + repo
  -> SUPERVISOR sends STEP n command
  -> WORKER executes, sends STEP n REPORT
  -> SUPERVISOR verifies (diff, tests, rules)
       ACCEPT   -> next step
       REWORK   -> same step again, with a numbered list of defects
       ESCALATE -> stop, ask HUMAN
```

A step is finished only when the SUPERVISOR has written `ACCEPT` for it.
Communicate with the human in Russian. Code, comments, commit messages and
documentation stay in English, matching the repository.

---

## 1. Global rules

### 1.1 Hard constraints (violating any of these → REWORK or ESCALATE)

1. **No Abaqus execution.** Do not launch `abaqus`, `abq20xx`, any `.bat/.cmd`
   launcher, or any `run_abaqus_*` function. Tests must use fakes or injected
   executors. Phase 8 is the only exception, and it needs an explicit HUMAN
   GATE for every run.
2. **Frozen history is read-only.** Never modify, move, delete, regenerate or
   re-extract anything under `analysis/`, `_sp13_real1_cache/`,
   `_sp13_orientation_extraction/`, `References/`, or the root `_sp*.py`
   research scripts.
3. **No destructive git operations.** No `git reset --hard`, `git checkout --`,
   `git clean`, `git stash drop`, `rebase`, `--amend` or force-push. Commit only
   when the SUPERVISOR instructs it after a HUMAN GATE. Never `push`.
4. **No change to scientific mathematics or thresholds** unless the step
   explicitly says so: MAC formulas, eigen solvers, sensitivity formulas,
   optimizer settings, the default `cond=100` / `γ=20` values, and pairing gates.
5. **No new `install_*` monkeypatch layers.** New behaviour goes into explicit
   modules. If a patched function must change, first find its final owner in
   `src/runtime_contracts.py`.
6. **One writer at a time.** Before Phase 0, the SUPERVISOR confirms with the
   human that no other agent or session is editing this working tree.
7. **Small diffs.** One step aims for ≤ ~300 changed lines of production code,
   excluding tests. If a step grows beyond that, the WORKER stops and reports
   `NEEDS_DECISION` with a proposed split.
8. **Scope discipline.** Touch only the files listed in `FILES ALLOWED`. If
   another file must change, report it as a deviation and do not proceed
   silently.
9. **Line endings and style.** Preserve the existing line endings (the repo
   shows LF→CRLF warnings; do not mass-convert files). Match the surrounding
   code: frozen dataclasses, explicit validation, `from __future__ import
   annotations`, and the same naming and comment density.

### 1.2 Test commands

- Full suite (same as CI): `python -m unittest discover -s tests`
- Focused run: `python -m unittest tests.<module> -v`
- Baseline on 2026-09-28: **515 tests, 1 failure, 1 error, 2 skipped**. Both
  problems are real-Tk layout tests (see Step 0.2). The full suite takes about
  2 minutes.
- Focused C4–C6 baseline on 2026-09-29 (roadmap v2): **141 tests OK, 2 skips**.
  The modules are `test_evidence_contracts`,
  `test_material_identification_session`, `test_identification_model`, the
  four `test_material_identification_*runner` modules,
  `test_sp13_evidence_adapter`, `test_material_identification_evidence_view`,
  `test_material_identification_evidence_view_integration`,
  `test_material_identification_application_wiring` and
  `test_material_identification_ui`. If plain `python` is unavailable, use
  `.venv\Scripts\python.exe`.
- Every step that changes behaviour must add tests that **fail on the old code
  and pass on the new code**. The WORKER must show this (red → green), for
  example by running the new test once with the change reverted locally, or by
  explaining precisely why it would fail.

### 1.3 Command template (SUPERVISOR → WORKER)

```
STEP <id>: <title>
CONTEXT: <why; the relevant facts from this plan, with file:line references>
DO:
  1. ...
DO NOT:
  - ...
FILES ALLOWED: <explicit list; "new file" where applicable>
ACCEPTANCE:
  - <checkable criteria>
TESTS REQUIRED: <new tests and the exact behaviour they must pin down>
REPORT: use the standard STEP REPORT format
```

### 1.4 Report template (WORKER → SUPERVISOR)

```
STEP <id> REPORT
STATUS: DONE | BLOCKED | NEEDS_DECISION
CHANGED FILES: <path (+added/-removed)> ...
WHAT CHANGED: <short, factual>
TESTS:
  command: ...
  result: Ran N tests, failures=F, errors=E, skipped=S
  new tests: <names> — red->green evidence: <how shown>
DEVIATIONS: <anything outside the instructions, or "none">
OPEN QUESTIONS / RISKS: <or "none">
```

### 1.5 SUPERVISOR verification checklist (every step)

1. `git status --short` and `git diff --stat`: only the allowed files changed,
   and nothing under frozen paths (§1.1 rule 2).
2. Read the full diff. Check the mathematics and thresholds are unchanged
   unless the step targets them.
3. Grep the diff for forbidden additions: `subprocess`, `Popen`,
   `run_abaqus`, `os.system`, `def install_`, `shutil.rmtree`, `.unlink(`
   outside tests' temporary directories.
4. Run the focused tests and then the full suite yourself. Do not trust the
   report's numbers.
5. Confirm the new tests actually pin down the defect: they fail when the fix
   is reverted.
6. Verdict: `ACCEPT`, or `REWORK` with a numbered defect list, or `ESCALATE`
   with a question for the human.

### 1.6 Stop conditions (SUPERVISOR must ESCALATE)

- Any HUMAN GATE.
- A step would need a forbidden action (§1.1).
- Tests that were green before the step become red and the fix is not obvious.
- The WORKER reports that the plan's facts do not match the code. The
  repository may have moved; re-verify before continuing.
- Two consecutive REWORK rounds on the same step.

---

## 2. Current state (verified 2026-09-28 — re-verify in Step 0.1)

> **History (v1 snapshot).** §2.1 and §2.2 describe the state as of
> 2026-09-28. Most of §2.1 has since been reworked and committed. The live
> status is in "Current state and execution queue" at the top of this
> document; §2.3 to §2.5 are still in force.

### 2.1 Uncommitted work that already exists

A parallel session added the following between 2026-09-27 19:18 and 21:57.
None of it is committed yet.

- Modified: `src/domain/__init__.py`, `src/material_identification_ui.py`,
  `src/ui_policy.py`, `src/ui_workflow.py`,
  `tests/test_material_identification_ui.py`, `tests/test_polymax_ui.py`,
  `tests/test_ui_workflow.py`.
- New modules:
  - `src/domain/evidence.py`: versioned `EvidenceRecord` envelopes with a
    content hash, `EvidenceProvenance` and `EvidenceSourceIdentity`, plus
    `Sensitivity/Identifiability/Identification/ValidationEvidence`.
  - `src/domain/material_identification_session.py`: task definition,
    parameter bounds, source identities (experimental, fe_model,
    calibration), evidence references and readiness. **Hardcodes
    `UNKNOWN_PARAMETER_IDS = ("Ex", "Ey", "Gxy")`.**
  - `src/material_identification_runner.py`: run lifecycle with explicitly
    injected executors, and source-mismatch errors.
  - `src/sp13_evidence_adapter.py`: reads the frozen SP13 package in
    `analysis/` (SHA-256 per artifact) into evidence records;
    `FrozenSP13IdentificationExecutor`.
  - `src/identification_evidence_adapter.py`,
    `src/identifiability_evidence_adapter.py`: lossless service output →
    evidence content.
  - `src/material_identification_evidence_view.py`: typed view model for
    the GUI. **Hardcodes `_PARAMETERS = ("Ex", "Ey", "Gxy")`.**
- New tests: `test_evidence_contracts`, `test_material_identification_session`,
  `test_material_identification_runner`,
  `test_material_identification_sensitivity_runner`,
  `test_material_identification_identifiability_runner`,
  `test_material_identification_identification_runner`,
  `test_material_identification_evidence_view`,
  `test_material_identification_application_wiring`.
- `material_identification_ui.py` now reads a
  `material_identification_evidence_view_model` instead of guessing attribute
  names for sensitivity, identification and validation. Check this in Step 0.1;
  it partially addresses audit finding A-2 below.

### 2.2 Audit findings this plan addresses

Findings were reconciled between two independent audits. IDs are used in the
steps below.

| ID | Finding | Location |
|---|---|---|
| A-1 | Inverse re-pairing calls the comparator **without** the confirmed `orientation_selection` or `geometry_calibration`; only `coordinate_scale_override` is passed. The production provider is the **default** path. | `src/services/stage_a_identification_service.py:488-492`, `:818-823`; the comparator accepts both: `src/quality_control.py:134-135` |
| A-2 | The GUI↔backend contract was attribute-name guessing (partly replaced by the evidence view model; remnants must be checked). | `src/material_identification_ui.py` |
| A-3 | `"frequency match"` (MAC unavailable) becomes `InclusionStatus.INCLUDED`, and nothing in the inverse chain filters `MAC is None`. | `src/services/specimen_comparison_service.py:20`, used via `modal_cluster_service.cluster_comparison_result` |
| A-4 | `family_residual_service` casts mode vectors to `float` (imaginary part lost), has no `.conj()`, and uses QR without a rank check. A correct rank-aware complex SVD primitive already exists. Not yet called from `src/`. | `src/services/family_residual_service.py:169-185`; correct version: `src/services/modal_cluster_service.py:48-64, 83-84` |
| A-5 | Identifiability: one override flag (`allow_non_identifiable_subset`) covers both rank deficiency (should be a hard block) and `cond>100` / `γ>20` (should be a soft block with a recorded reason). | `src/services/stage_a_identification_service.py:904-922`; `src/services/identifiability_service.py:473-477, 720-722` |
| A-6 | Parameter names differ: production backend Stage A uses `D11/D12/D66`, while GUI and session use `Ex/Ey/Gxy` (SP13, produced by untracked research scripts plus `analysis/`). | `src/services/sensitivity_service.py:28-32`; `src/domain/material_identification_session.py`; `src/material_identification_evidence_view.py` |
| A-7 | Opening a project does not clear `self.result`, so the old comparison can be shown under new sources. | `src/project_review.py:379-395` plus the wrapper at `src/ui_workflow.py:1656-1716` |
| A-8 | `write_project` is not atomic (`Path.write_text`). | `src/project_review.py:154-158` |
| A-9 | Project loading is applied field by field. It switches `project_path` before later fields can fail, so Ctrl+S after a failed open can overwrite that file with mixed state. | `src/project_review.py:381-389`, `src/ui_workflow.py:1665` |
| A-10 | Project schema v2 has no place for identification state; `last_result` is written but never read back. | `src/project_review.py:28, 87-151` |
| A-11 | The ODB step is chosen by maximum frame count; on a tie it is chosen silently. | `abaqus_scripts/extract_odb.py:193-210` |
| A-12 | The ODB extraction cache signature has no extractor-script hash, schema version or `step_name` (the general `fast_cache` *is* versioned). | `src/abaqus_bridge.py:604-618` |
| A-13 | A missing node coordinate becomes `[0, 0, 0]`. | `src/abaqus_bridge.py:521` |
| A-14 | Missing coherence becomes `1.0` in the metadata `mean_coherence` (peak ranking is unaffected, because a constant shift doesn't change the order). The CMIF error path uses `0`. | `src/universal_reader.py:779-781, 818`; `src/cmif_separation.py:286-289` |
| A-15 | The Validation page status falls back to the identification recommendation; readiness `overall_status` overrides the per-row states; `UNOBSERVABLE` is shown as "unavailable"; limitations are hardcoded; `boundary_status` and `solver_health` are dropped from the report. | `src/material_identification_ui.py` (re-locate after Step 0.1; line numbers changed) |
| A-16 | Stage A is not validated against real Abaqus: direct FE validation, hold-out modes and the 20-point affine proof have not been run. | ROADMAP; `stage_a_identification_service` metadata |

Already fixed, do not redo: the earlier audit's orientation tie-break by MAC
(`docs/scientific_audit`, P0-1). It was fixed in commit `4820566`.

### 2.3 Design decisions already taken (do not re-litigate)

- **`FrozenRegistration`** is created once, after the user confirms the
  orientation, and is immutable. Downstream code may only check compatibility,
  apply it, or refuse on mismatch. **Nothing downstream may select the
  geometry or orientation again.**
- `FrozenRegistration` binds to the **FE geometry identity** (node coordinates
  + DOF map), **not** to the full FE model identity. The inverse solver changes
  stiffness at every evaluation while the mesh stays the same. The full model
  identity (template hash, `basis_km_hash`, parameter values) belongs to the
  identification result.
- Content hashes: SHA-256, computed once and cached, keyed by
  `(path, size, mtime_ns)`. Never re-hash a multi-GB ODB on every UI event.
  For an ODB, prefer hashing the normalized extracted package.
- The identification contract is **model-independent**:
  `IdentificationModelDefinition` is data in `src/domain` (parameter ids,
  units, bounds, meaning, frozen assumptions, limitations). Execution stays in
  injected executors, which is the existing runner pattern. A model definition
  never contains a solver.
- The coherence state is three-way: `AVAILABLE | UNAVAILABLE | INVALID`. A
  numeric value exists only for `AVAILABLE`.
- Identifiability policy: rank deficiency is a hard block with no generic
  override. Full rank with poor conditioning or collinearity needs an explicit
  override **with a reason string stored in provenance**. The default
  threshold values stay unchanged.
- Persistence: atomic save (temp file → flush → fsync → `os.replace`, with a
  short retry on Windows `PermissionError`), and transactional load (read →
  validate the schema → resolve sources → check hashes → build the complete
  candidate state → check cross-references → only then swap it in). Evidence
  files are append-only and never overwritten.
- Two acceptance boundaries, never merged:
  **software/data-integrity acceptance** = Phases 0–5;
  **scientific/model acceptance** = Phase 8. Until Phase 8 is complete, every
  output keeps `NOT_VALIDATED` for material-property claims.

### 2.4 Decisions recorded after 2026-09-28 (roadmap v2; do not re-litigate)

**Human decisions:**
- **D-WORKFLOW (Step 4.0):**
  - Stage A (`D11/D12/D66`) is the production model.
  - The effective face-sheet model (`Ex/Ey/Gxy`) is a research model with no
    live production engine.
  - SP13 is a specimen only, never a method.
  - These decisions are recorded here; `DECISIONS.md` was not created.
- **D-FREQONLY (Step 2.1):** MAC-less pairs are never inverse-fit
  observations, with no override. A MAC-less initial production pairing is
  refused; during an optimizer trial it counts only as a failed evaluation.
- **Design B:** an explicit Stage A matrix-node → `INSTANCE:label` map. Never
  guess labels or instances.
- **Policy B:** a missing matrix FE DOF is UNAVAILABLE, never zero.
  `KNOWN_ZERO` is not allowed until an Abaqus probe proves the BC export
  semantics.
- **Hard refusals:** node-map, geometry-identity and Policy B failures are
  hard scientific refusals. They are never converted into, or swallowed by,
  the fixed-pair fallback.
- **Conditioning override:** the override for full-rank but poorly
  conditioned subsets needs a human reason before it is persisted. This is not
  implemented yet.
- **D-ANALYSIS:** calculation data and derived analysis outputs stay local.
  Presentation tests that depend on the local `analysis/` may skip when the
  data is absent. Do not commit REAL-4 numerical data to make tests pass.

**Architecture decision: the authoritative model definition.**

`IdentificationModelDefinition` (`src/domain/identification_model.py`) is the
authoritative source for each parameter's:

- parameter id;
- display name;
- unit;
- meaning;
- parameter order (the parameter-vector order, which is hashed into
  `definition_hash`).

Do **not** duplicate these definitions in the evidence view, the UI, runner
presentation code, or another registry.

- **BOUND evidence** carries the model id and hash in its
  `EvidenceScientificBinding`. That is enough to **verify** a supplied model
  definition, but not enough to reconstruct it. BOUND production presentation
  must therefore receive or resolve the authoritative definition and verify
  its id and hash. The legal routes are `session.task_definition.model` and
  `resolve_identification_model(model_id, model_hash, models)`.
- **Historical UNBOUND SP13** stays a separate legacy presentation path. Do
  not pretend historical SP13 corresponds to `EFFECTIVE_FACE_SHEET_MODEL`:
  - Historical SP13 is a four-parameter study (`face_Ex`, `face_Ey`,
    `face_Gxy`, `core_scale`) in sensitivity and identifiability.
  - The current effective-face model has three parameters.
  - Historical records carry no model id or hash to verify against.

### 2.5 Literature status

The Consensus literature review is supporting research input, **not** an
authoritative specification. It was supplied to the supervisor and is not
stored under `docs/`. Some of its sources are indirect: general inverse
problems, identifiability, and other inverse-design fields. The curated notes
in `docs/literature/` and `docs/scientific_audit/` are separate earlier
inputs.

Before production mathematics changes for any of the following, the
SUPERVISOR requires targeted primary literature from experimental modal
analysis, FE model updating, structural dynamics, and composite or plate modal
identification:

- continuous mode tracking;
- a combined frequency/MAC objective;
- numerical identifiability thresholds;
- uncertainty acceptance criteria.

Existing, mathematically established decisions must not be weakened because
of a generic literature summary. This includes the rank-deficiency hard
block, D-FREQONLY, and the Hermitian, rank-aware subspace work.

---

## 3. Phases and steps

Order is mandatory. A phase starts only after all steps of the previous phase
are ACCEPTED, except where noted.

### Phase 0 — Baseline and checkpoint

**Step 0.1 — Read-only inventory.** *(no file changes)*
- DO: run `git status`, `git log --oneline -5` and the full suite. For every
  item in §2.1 and every finding A-1…A-16, report **present / partially
  addressed / fixed**, with current file:line. List every place that still
  hardcodes `Ex`, `Ey`, `Gxy`, `D11`, `D12`, `D66` outside services mathematics.
- ACCEPTANCE: a table that the SUPERVISOR can spot-check against the code.
  No diff.

**Step 0.2 — Make the two Tk runtime tests deterministic.**
- CONTEXT: `test_ui_workflow.TkRuntimeSmokeTests.test_runtime_builds_ten_resizable_tabs_with_complete_headings`
  raises a `ValueError` on `wraplength` `''`.
  `test_material_identification_ui.MaterialIdentificationGuiShellTests.test_existing_tabs_remain_present_and_ordered`
  gets the compact tab labels instead of `FULL_TAB_LABELS`. Both likely
  depend on the real window size or DPI of the machine.
- DO: find the root cause first and report it before changing anything. Then
  make the tests deterministic by fixing the geometry or layout mode in the
  test setup, **or** fix a real bug if one is found.
- DO NOT: weaken the assertions or add skips to make the tests pass.
- ACCEPTANCE: full suite green (skips allowed only for "no display" / "no
  Abaqus" conditions).

**Step 0.3 — HUMAN GATE D-COMMIT: checkpoint commits.**
- The SUPERVISOR proposes a commit split to the human, for example:
  (a) GUI-6 / calibration-loop fix + Tk test fix;
  (b) evidence contracts + session + runner + adapters + their tests.
  Commit only after approval. Do not push.

**Step 0.4 — HUMAN GATE D-ANALYSIS: protect frozen evidence.**
- DO (after approval): create
  `docs/agent_handoff/ANALYSIS_MANIFEST.sha256`, containing SHA-256 + path +
  size for the small record files under `analysis/` (`*.json`, `*.md`,
  `*.csv` below ~5 MB, all `manifest.json`). Propose `.gitignore` rules for the
  bulky derived artifacts, but present the rules to the human before applying
  them.
- DO NOT: move, delete or modify anything in `analysis/`.
- ACCEPTANCE: the manifest is reproducible (running it twice gives an
  identical file); the human has approved the `.gitignore` decision.

### Phase 1 — Scientific-state foundation

**Step 1.1 — Content-hash source identity.**
- DO: add a content identity (SHA-256 + size + mtime_ns + normalized path) with
  a hash cache keyed by `(path, size, mtime_ns)`, as a **new** function next
  to `scientific_state.experimental_source_identity`. Keep the existing
  function and its format unchanged, because saved projects contain bindings
  in the old format.
- FILES ALLOWED: `src/scientific_state.py`, new test module.
- TESTS: same content at a different path gives the same hash; modified
  content gives a different hash; the cache avoids re-reading (count reads
  through a spy); a missing file gives `None`.

**Step 1.2 — FE geometry identity.**
- DO: compute a deterministic hash of the FE geometry: node ids with instance
  names, coordinates in canonical float formatting, and the DOF map. Take it
  from an already extracted package or a `ModalDataset`. Independent of mode
  shapes and frequencies.
- TESTS: same mesh with different frequencies gives the same identity; a moved
  node or a missing node gives a different identity; the result does not
  depend on ordering.

**Step 1.3 — `FrozenRegistration` domain type.**
- DO: new `src/domain/registration.py`. It is a frozen dataclass with these
  fields:
  - identities: `experimental_source_identity`,
    `experimental_modal_set_identity`, `fe_geometry_identity`
  - calibration: `calibration` (dict + fingerprint)
  - orientation: `orientation_candidate_id`, `rotation`, `translation`,
    `coordinate_scales`
  - node mapping: `experimental_node_ids`, `mapped_fe_node_ids`,
    `measured_dof_contract`
  - quality and versioning: `registration_metrics`,
    `registration_schema_version`, `registration_hash`

  Plus `to_dict` / `from_dict`, a deterministic hash, and
  `check_compatible(experimental_identity, fe_geometry_identity)`, which
  raises a dedicated `RegistrationMismatchError`.
- DO NOT: wire it into anything yet.
- TESTS: immutability; round-trip; stable hash; any field change changes the
  hash; compatibility errors on either identity mismatch.

**Step 1.4 — Build `FrozenRegistration` from a confirmed comparison.**
- DO: a factory in an application-level module (not in `domain`, not in the
  GUI). It builds the registration from a finished `ComparisonResult` plus the
  user-confirmed orientation and calibration binding, reusing
  `orientation_registration_valid`. It refuses to build when the orientation
  was not user-confirmed and more than one candidate exists.
- TESTS: builds for an unambiguous geometry; refuses for an ambiguous geometry
  without confirmation; builds with confirmation and records the candidate id.

**Step 1.5 — Use `FrozenRegistration` in inverse re-pairing (fixes A-1).**
- DO: `ProductionComparisonPairingProvider` and
  `create_production_pairing_provider` take a `FrozenRegistration`. Every
  comparator call receives `geometry_calibration` and `orientation_selection`
  from it. Before each call, check the candidate dataset's FE geometry identity
  against the registration and raise on mismatch. Record the
  `registration_hash` in the result metadata. If no registration is supplied,
  the production path must fail explicitly. The synthetic fixed-pair mode may
  continue to run without one, but only when the caller selects it explicitly.
- FILES ALLOWED: `src/services/stage_a_identification_service.py`, tests.
- TESTS: a synthetic, symmetric (square) plate where orientation is ambiguous:
  the old path raised `GeometryOrientationAmbiguousError` during re-pairing,
  and the new path completes with the frozen orientation. A spy comparator
  proves `orientation_selection` and `geometry_calibration` are passed on
  **every** call. A geometry mismatch raises.

### Phase 2 — Inverse safety

**Step 2.1 — HUMAN GATE D-FREQONLY, then exclude frequency-only identity from fitting (A-3).**
- Ask the human: may a `MAC is None` observation **ever** enter the fit?
  The recommended answer is: only with an explicit per-observation override,
  a recorded reason, and independent identity evidence.
- DO: in the Stage A observation path (`comparison_to_observations` /
  `cluster_comparison_result`, or a Stage A policy layer on top of them),
  observations with `mac is None` or status `"frequency match"` become
  `EXCLUDED`, with the reason `"frequency-only identity is not admissible for
  fitting"`, unless the human-approved override applies.
- DO NOT: change the comparator's own acceptance or report behaviour. The
  frequency-only fallback remains valid for **diagnostic comparison**.
- TESTS: a frequency-only pair is excluded from Stage A; a MAC-backed pair is
  still included; the override (if approved) needs a reason and appears in the
  metadata; the comparator report output is unchanged.

**Step 2.2 — Split identifiability policy (A-5).**
- DO: a rank-deficient requested subset is always refused, with no generic
  override. Full rank with `cond > threshold` or collinearity warning is
  refused unless there is an explicit override **with a non-empty reason**;
  store the reason and the metrics that triggered it in the result metadata.
  Keep the default threshold values. Keep `approve_recommended_subset`. Document
  the changed meaning of `allow_non_identifiable_subset`, or replace it with
  two explicit fields.
- TESTS: rank deficiency plus override → still refused; poor conditioning
  without a reason → refused; with a reason → allowed, and the reason is
  recorded; the existing tests keep passing, or are updated with a stated
  justification.

### Phase 3 — Close-mode safety

**Step 3.1 — Replace the subspace implementation in `family_residual_service` (A-4).**
- DO: expose the rank-aware complex SVD subspace primitive from
  `modal_cluster_service` as a public helper, then use it in
  `two_mode_subspace_evidence`. Keep complex dtype and use the conjugate
  transpose. A rank below 2 → explicit failure or `REVIEW` status, never a
  fabricated 2-D basis.
- DO NOT: change the family-residual formula (`m = (ln f1 + ln f2)/2`,
  splitting).
- TESTS: complex vectors where a float cast would change the result (show
  both values); a nearly rank-1 pair is flagged; real-valued inputs reproduce
  the existing test numbers.

### Phase 4 — Backend contract and workflow decision

**Step 4.0 — HUMAN GATE D-WORKFLOW (mandatory; the WORKER idles).**
- The SUPERVISOR presents to the human:
  - Stage A: `D11/D12/D66` bare-plate matrix model, fully in `src/services`,
    not yet validated against Abaqus.
  - SP13: effective face-sheet `Ex/Ey/Gxy` with the U/P models, produced by
    research scripts plus `analysis/`, frozen as v1, and not a reproducible
    `src/` pipeline.
  - Note: the uncommitted session and view model already hardcode SP13
    (`Ex/Ey/Gxy`). That is an implicit choice that has not been approved yet.
- Options:
  - (a) Stage A is production and SP13 is shown as a frozen historical record;
  - (b) SP13 is production, which then needs a porting plan into `src/`;
  - (c) both are shown through the common contract, with exactly one marked
    production.
- Record the decision in `docs/agent_handoff/DECISIONS.md` (new).
- **Status (v2):** decided as option (a). Stage A is production, the effective
  face-sheet model is research, and SP13 is shown as a frozen historical
  record. The decision is recorded in §2.4.

**Step 4.1 — `IdentificationModelDefinition` (A-6).**
- DO: new data type in `src/domain`: `model_id`, parameter definitions (id,
  unit, bounds, human meaning such as "effective face-sheet Ex"), frozen
  assumptions, limitations, and status (`production` / `historical` /
  `research`). Define the models chosen in D-WORKFLOW. Remove the hardcoded
  parameter tuples from the session, the evidence view and the GUI; they must
  read the definition.
- TESTS: the GUI view renders a `D11/D12/D66` result with real values (a
  regression test for the "all —" failure); the SP13 frozen evidence still
  renders; an unknown `model_id` → explicit error.
- **Status (v2):**
  - Done: the domain definition (`40616be`) and the model-driven session
    (`c8e8d51`).
  - The evidence view still hardcodes `Ex/Ey/Gxy`; that is **C6-R1**.
  - The GUI still hardcodes them too; that is **C6-R2**.

**Step 4.2 — Bind evidence to `model_id` + `registration_hash` + source identities.**
- DO: every evidence record carries these fields. The runner and the session
  refuse evidence whose identities do not match the current session (extend
  the existing `MaterialIdentificationSourceMismatchError` paths).
- TESTS: evidence from another experiment, another registration or another
  model is refused, with a clear error.
- **Status (v2):** done, and C5 is CLOSED.
  - The session is bound to a `FrozenRegistration` (`1875d68`).
  - Evidence schema 2.0 carries an `EvidenceScientificBinding` with the model
    id and hash, the `registration_hash` and the experimental SHA-256
    (`de8f192`).
  - The runner enforces binding and parent provenance (`5cb5fd9`).
  - The historical SP13 import is separate from execution (`0f40c65`).
  - Descriptive source labels remain as an additional check only.

**Step 4.3 — GUI presentation correctness (A-2 remnants, A-15).**
- DO: first verify which of A-15 is still present after the parallel work;
  report before editing. Then:
  - validation status never falls back to the identification recommendation;
  - readiness overall status is derived from the rows, and a stored
    `overall_status` may only be *stricter*;
  - `UNOBSERVABLE` is distinct from "no evidence";
  - limitations, frozen assumptions and unknowns come from the model
    definition and the record;
  - `boundary_status`, `solver_health` and the evaluation key are shown and
    exported;
  - no `getattr` alias guessing remains for readiness or evidence;
  - the empty `_STEP_DESCRIPTIONS` crash path is removed (page registry instead
    of an `if/elif` on labels).
- TESTS: one per bullet.
- **Status (v2):** open. The "limitations, frozen assumptions and unknowns
  come from the model definition" bullet overlaps C6-R2. The other bullets
  stay open unless C6-R2 explicitly covers them.

**Step 4.4 — Stale state on project open or source change (A-7).**
- DO: opening a project, or changing the experimental or FE source, clears
  `self.result`, the cache, the registration and the session evidence, or
  marks them `STALE` so they cannot be used.
- TESTS: open project B after project A has a result → no A data on any page
  or in any export.

### Phase 5 — Persistence v3

**Step 5.1 — Atomic save (A-8).**
- DO: `write_project` writes a temp file in the same directory, flushes,
  fsyncs, then calls `os.replace`, with a bounded retry on `PermissionError`.
  Use the same writer for `last_session.json`.
- TESTS: a failure during serialization or during replace leaves the original
  file byte-identical; no temp file remains.

**Step 5.2 — Schema v3 design (document only, SUPERVISOR review + HUMAN GATE D-SCHEMA).**
- DO: `docs/agent_handoff/PROJECT_SCHEMA_V3.md` with these sections:
  - `sources` (with hashes)
  - `registration` (`FrozenRegistration`)
  - `comparison` (result identity + manual decisions)
  - `material_identification` (session + evidence references by id + hash)
  - `validation`
  - `ui` (presentation only)

  Evidence goes in append-only files `<project>.evidence/<record_id>.json`,
  never overwritten; writing a different hash under an existing id is
  refused. Include the v2 → v3 migration: read-only, never rewrite a v2 file
  silently.

**Step 5.3 — Transactional load (A-9, A-10).**
- DO: implement v3 read/write per the approved design. Loading builds a
  complete candidate state and swaps it in only on success;
  `project_path` changes only after the swap.
- TESTS: corrupted JSON, wrong field types, missing sections, evidence hash
  mismatch, missing evidence file → error dialog path, with the application
  state **and** `project_path` unchanged; Ctrl+S after a failed open does not
  write to the failed file; v2 files still open, with a migration warning.

**Step 5.4 — Persist and restore session and evidence.**
- DO: save/open round-trips the registration, session and evidence
  references; recovery (`last_session.json`) uses the same code path.
- TESTS: a full round trip gives identical hashes; a changed source file on
  disk → the loaded evidence is marked stale (Step 4.4 behaviour).

### Phase 6 — Hardening (can start after Phase 2 if the human wants, since it doesn't depend on Phases 3–5)

**Step 6.1 — Explicit ODB modal step (A-11).**
- DO: when more than one frequency step with U output exists and no
  `step_name` is given → an error listing the steps. Put `step_name` into the
  project inputs and the extraction manifest.
- NOTE: `abaqus_scripts/extract_odb.py` runs inside Abaqus Python. Test only
  the pure-Python selection logic, with fake ODB objects. Never run Abaqus.

**Step 6.2 — ODB extraction cache signature (A-12).**
- DO: add the extractor schema version, the SHA-256 of `extract_odb.py`,
  the Abaqus command, the ODB content identity (from Step 1.1), the mode range
  and `step_name` to `_source_signature`.
- TESTS: changing any of these invalidates the cache.

**Step 6.3 — Missing node coordinate → error (A-13).**
- TESTS: a mode CSV that references a node absent from the geometry → a clear
  error naming the instance and node.

**Step 6.4 — Coherence tri-state (A-14).**
- DO: `AVAILABLE | UNAVAILABLE | INVALID` in `universal_reader` and
  `cmif_separation`. No numeric `mean_coherence` in metadata unless
  `AVAILABLE`. Reports show "unavailable" or "invalid".
- TESTS: FRF without coherence → no `1.0` anywhere in the metadata or the
  report; the peak order is unchanged versus the current behaviour.

### C6 — Model-driven evidence presentation (roadmap v2; continues Steps 4.1 and 4.3)

These steps come next in the queue. Each one is a separate small step with
red → green tests. C5 (runner, adapters, evidence schema) stays closed.

The C4, C5 and C6 labels come from the Step 4.0 audit track:

- C4: domain session and model;
- C5: runner and evidence provenance;
- C6: presentation.

They are **not** Phases 4–6. In particular, `C6-HARDEN` is unrelated to
"Phase 6 — Hardening".

**C6-R1 — Model-driven evidence view.**
- GOAL: make `MaterialIdentificationEvidenceViewModel` model-driven for BOUND
  evidence.
- FILES ALLOWED (expected):
  - `src/material_identification_evidence_view.py`
  - `tests/test_material_identification_evidence_view.py`
  - `tests/test_material_identification_evidence_view_integration.py`
- REQUIRED BEHAVIOUR:
  - BOUND evidence takes an optional, explicit `IdentificationModelDefinition`.
  - The view verifies each binding's model id and hash against it.
  - It refuses:
    - BOUND evidence without a model;
    - a model mismatch;
    - a presentation that mixes BOUND and UNBOUND records.
  - Sensitivity renders from `parameter_ids`, `observation_ids` and
    `scaled_sensitivity`.
  - Identifiability renders over the model's parameter ids, in model order.
  - Identification renders over the model's parameter ids, order and units.
    A stored `parameter_unit` that differs from the model unit is refused.
    Values are read from the committed `properties_MPa` key, but no unit is
    inferred from that key name.
  - The historical UNBOUND `from_bundle` path stays compatible, with the same
    output as today.
- TESTS:
  - Remove both existing Stage A skips; keep every assertion.
  - Add a test for the hidden Stage A identifiability defect (C).
- DO NOT: change C5, the evidence schema or the UI.
- TARGET: the C6 integration tests run with **0 skips**.

**C6-R2 — Model-driven UI.** *(only after C6-R1 is ACCEPTED)*
- Remove UI presentation hardcodes:
  - fixed `Ex/Ey/Gxy` parameter lists (for example
    `_EFFECTIVE_PARAMETER_IDS` and the "Unknown" list on the Task Definition
    page);
  - fixed sensitivity table headers;
  - fixed MPa assumptions;
  - report text that assumes `Ex/Ey/Gxy`.
- The UI derives its presentation from the model definition and the view.
- Keep specimen and source identity separate from identification model
  identity. Do not mix SP13 into model naming.
- Reconcile with the open Step 4.3 bullets: state explicitly which ones this
  step covers.

**C6-R3 — Clean-checkout presentation tests.**
- Remove the remaining mandatory dependence of presentation tests on the local
  `analysis/`. For example,
  `tests/test_material_identification_evidence_view.py` loads SP13 in
  `setUpClass` without a skip.
- Use synthetic, self-contained fixtures to test schema and behaviour.
- Real SP13 numerical artifacts remain local research data. Do not commit
  REAL-4 numerical data merely to make tests pass.

**C6-HARDEN — Unit provenance.** *(a separate small step after the main C6
work)*
- **Known issue:** `IdentificationExecutionOutput.parameter_unit` is not
  enforced against the `IdentificationModelDefinition`. The view refuses a
  mismatch from C6-R1 onwards.
- Audit later whether the producer or runner should also refuse the mismatch
  at creation time. That would reopen C5 narrowly and needs explicit
  SUPERVISOR approval.
- The committed key name `properties_MPa` is misleading for Stage A, because
  it can hold N·m values. Never infer units from it. Renaming or migrating
  this key is **not** currently approved.

### Phase 7 — Scientific identification hardening (roadmap v2; audit targets)

These are **audit targets** informed by a literature review (§2.5). They are
**not** automatically accepted implementation requirements. No mathematical
behaviour changes until each audit is completed, reviewed by the SUPERVISOR,
and accepted. Each audit starts read-only and produces testable examples. Any
implementation follows as separate, explicitly approved steps.

**7.1 — Mode pairing / tracking stability audit.**
- Audit the current inverse behaviour as `D11/D12/D66` change. Can the
  experimental mode identity jump between FE branches?
- Study:
  - fixed pairing;
  - dynamic global re-pairing;
  - continuous branch tracking;
  - eigenvalue crossing;
  - veering;
  - close or repeated modes;
  - invariant modal subspace tracking.
- **Key question:** can `ProductionComparisonPairingProvider` change the
  physical mode identity during optimization in a way that creates
  circularity, given that frequency is also part of the inverse objective?
- Output first: a read-only audit plus testable examples. The implementation
  is **not** decided in this roadmap.

**7.2 — Objective policy audit.**
- The current architecture is approximately:
  - MAC / modal evidence → identity gate;
  - frequency residual → inverse parameter objective.
- Audit whether this is sufficient for the actual Stage A `D11/D12/D66`
  campaign. Compare it against:
  - a combined frequency + mode-shape objective;
  - a MAC residual;
  - a subspace/family residual.
- Do **not** automatically add MAC to the objective. First prove whether the
  existing objective has a practical ambiguity after identifiability
  screening.

**7.3 — Identifiability threshold policy.**
- Preserve the rule that **rank deficiency is a hard scientific block**.
- Document that finite thresholds, such as condition-number limits and
  collinearity/γ limits, are engineering or campaign policies unless they are
  separately justified. Do not describe `cond=100`, `γ=20` or similar values
  as universal mathematical laws.
- Audit their provenance and their sensitivity to experimental uncertainty.
- The defaults stay unchanged (§1.1 rule 4) until this audit is accepted.

**7.4 — Close / repeated mode policy.**
- Preserve the existing complex, rank-aware family residual work (`151f658`).
- Audit when the workflow should switch from individual mode identity to
  family/subspace identity.
- Complex inner products must remain Hermitian.
- No implementation change until the audit is accepted.

### Phase 7P — Production connection of the GUI identification pages (was Phase 7 in v1)

> Renumbered in roadmap v2 so that Phase 7 can hold the scientific hardening
> audits. The content is unchanged, and it is still open.

Starts only when Phases 0–5 are ACCEPTED (the software/data-integrity boundary).

**Step 7P.1 (v1: 7.1) — Gated run action.** A "Run" action is enabled only when readiness
is `READY`, the identities match the session, no evidence is stale, and the
model definition is `production`. The executor is injected and runs in a
worker thread. Any executor that could start Abaqus requires an explicit
confirmation dialog, and defaults to disabled.

**Step 7P.2 (v1: 7.2) — GUI test safety net.** Add a shared test fixture that makes
`subprocess.run`, `subprocess.Popen` and `os.system` raise in all GUI and
runner tests.

**Step 7P.3 (v1: 7.3) — Report provenance.** Exports include `model_id`,
`registration_hash`, source hashes, evidence ids and hashes, app git commit,
package versions (numpy, scipy, pyuff, …), a timestamp, and the validation
status (`NOT_VALIDATED` until Phase 8).

### Phase 8 — Scientific acceptance (HUMAN GATE for every Abaqus run)

The WORKER prepares scripts and protocols only. The human runs, or authorizes
each run, on the Windows + Abaqus machine. The results are stored as
`ValidationEvidence`.

1. Real 20-point affine decomposition proof (currently skipped in CI).
2. Direct FE validation at the optimum, plus several nearby points.
3. Hold-out modes (for example, fit the lower modes and predict the higher
   ones), declared **before** the fit is run.

Until all three are accepted, material-property outputs stay `NOT_VALIDATED`.

**Roadmap v2 additions: uncertainty and independent validation.** These
clarify the items above; they do not replace them.

- **Convergence is not identification.** Optimizer convergence alone does
  **not** mean material properties are scientifically identified.
- **Conceptual statuses.** These names are roadmap concepts only; do **not**
  add enums or code for them now:
  - `BEST_FIT`: the optimizer found a best fit.
  - `IDENTIFIABLE`: identifiability screening passed; rank deficiency is a
    hard block.
  - `UNCERTAINTY_QUANTIFIED`: parameter uncertainty is estimated from stated
    experimental uncertainty.
  - `INTERNALLY_VALIDATED`: predictions agree on data not used in the fit.
  - `INDEPENDENTLY_VALIDATED`: an independent experiment or specimen agrees.
- **Validation hierarchy to audit**, from weakest to strongest:
  1. fitted modes: not validation;
  2. unused modes from the same experiment: internal validation, which is
     item 3 above (hold-out modes declared before the fit);
  3. a different frequency range or load case: stronger validation;
  4. an independent experiment or specimen: independent validation.
- **Abaqus gate unchanged.** Direct Abaqus validation (items 1–2 above) stays
  behind the explicit HUMAN GATE D-ABAQUS for every run. This roadmap edit
  authorizes **no** Abaqus runs.

### Phase 9 — Out of scope for this plan (backlog)

Folding the `install_*` layers into their base modules, Windows CI,
dependency lockfile, UNV dataset 2420 transform, FE shape-function
interpolation / duplicate-node weighting, full PolyMAX (not planned).

---

## 4. Human gates summary

| Gate | When | Question | Status (2026-09-29) |
|---|---|---|---|
| D-COMMIT | Step 0.3 and every later commit | Approve the commit split and messages? (Never push.) | ongoing, per commit |
| D-ANALYSIS | Step 0.4 | Git policy for `analysis/` (manifest + `.gitignore` rules)? | decided: data stays local (`84d8ec4`) |
| D-FREQONLY | Step 2.1 | May a MAC-less observation ever enter the fit, and under what evidence? | decided: never (§2.4) |
| D-WORKFLOW | Step 4.0 | Which identification model is production: Stage A, SP13, or both via the contract? | decided: Stage A (§2.4) |
| D-SCHEMA | Step 5.2 | Approve the project schema v3 and the migration policy? | open |
| D-ABAQUS | Every Phase 8 run | Authorize this specific Abaqus execution? | open, per run; none authorized |

## 5. First message the SUPERVISOR should send

> **History (v1 bootstrap).** Step 0.1 is done. A supervisor continuing from
> roadmap v2 starts at the top of the execution queue (currently C6-R1), after
> confirming §1.1 rule 6 (one writer) and that the inherited C6 working tree
> is intact.

After reading this document and spot-checking §2 against the repository, the
SUPERVISOR asks the human to confirm rule §1.1-6 (no other agent is editing
the tree), and then sends:

```
STEP 0.1: Read-only inventory
CONTEXT: See SUPERVISED_WORK_PLAN.md §2. A parallel session left uncommitted
  work; the audit findings A-1..A-16 may be partially addressed already.
DO:
  1. Run git status, git log --oneline -5, and
     python -m unittest discover -s tests; report the summary line and every
     failure/error name.
  2. For each item in §2.1 confirm it exists and summarize its public API.
  3. For each finding A-1..A-16 report present / partially addressed / fixed,
     with the current file:line evidence.
  4. List every hardcoded occurrence of Ex, Ey, Gxy, D11, D12, D66 outside
     src/services mathematics.
DO NOT: modify, create, or delete any file.
FILES ALLOWED: none
ACCEPTANCE: complete tables; no diff in git status.
REPORT: standard STEP REPORT format
```
