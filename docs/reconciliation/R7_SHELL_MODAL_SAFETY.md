# R7 — Frequency-record safety of extraction packages and the fail-closed shell gate

**Branch:** `fix/r7-shell-modal-safety`, from `origin/main` `aa08ad9`; PR #96. **Status:** `REVIEW_READY` (R7 R1). It
is not merged.

No Abaqus was run and no original was opened. The pinned extractor, `PINNED_EXTRACT_SCRIPT_SHA256`,
`parse_geometry_calibration`, the governed passports, SPEC v1.2, every threshold and every production gate are
unchanged.

**History:**

- R7: `7d46a2f`, `ae0fb6a`.
- R7 R1, after the SUPERVISOR audit: this revision. It closes the remaining frequency gap, replaces the optional shell
  hint by a fail-closed gate in the real GUI path, and records the pin's line-ending dependence as an open decision.

## 1. R7-A: frequency records of an extraction package

### Error and cause

The R6 plate package records modes 1 and 2 at 1 Hz and 2 Hz. Their `.dat` values, the frame descriptions
("`Freq = 0.0000`") and EIGFREQ all give 0 Hz.

The pinned `abaqus_scripts/extract_odb.py` (`frame_frequency`) treats `frame.frequency == 0` as missing and writes
`frame.frameValue`, which in an Abaqus frequency step is the mode number. Its description fallback (`frequency\s*[:=]`)
does not match "`Freq =`".

### Fix (loader `src/abaqus_bridge.py`; the pinned script is unchanged)

**Three records of the same mode:**

- the manifest value;
- the frame description "`Freq = …`" (`described_frequency`, with the half-unit precision of the printed text);
- a **reliable** EIGFREQ value (`reliable_eigfreq`).

EIGFREQ is reliable only when its history is single and well formed and, when an EIGVAL history exists, EIGVAL agrees
for that mode: sqrt(max(EIGVAL, 0))/2π within the existing four single-precision ulps. A rigid mode's non-positive
EIGVAL agrees with EIGFREQ = 0. This is the existing EIGFREQ/EIGVAL policy, used here only to judge consistency.

**`manifest_frequency_problem`:**

- the manifest must agree with the description;
- the frame frequency (the description, or the manifest when there is no description) must agree with the reliable
  EIGFREQ;
- tolerances are the printed precision plus float32 resolution;
- **R7 R1:** a manifest and description that agree while EIGFREQ contradicts them are now **refused**. In R7 this
  case passed silently.

**Refusal is per mode:**

- the mode is not loaded and cannot take part in pairing, MAC or frequency errors;
- the reason, all records and whether the independent records agree are stored in
  `metadata["rejected_frequency_modes"]`;
- nothing is chosen between the records and nothing is substituted;
- a package whose every mode is refused is refused;
- EIGFREQ values not usable for the check are listed in `metadata["eigfreq_not_used_for_consistency"]`.

**Compatibility:** a value with no second record (a legacy package without description or history) is unchanged. The
EIGFREQ refinement of kept modes (`history_frequencies`, G2) is unchanged.

**On the stored R6 package** (read only; `runs\r7_r1`):

- modes 1 and 2 are refused; description and EIGFREQ agree on 0.0 Hz, which is recorded but not used;
- modes 3–20 load, with the EIGFREQ refinement; for example mode 7 is 19.07217 Hz.

### Open decision OD-R7-1: the pinned extractor hash depends on line endings

`PINNED_EXTRACT_SCRIPT_SHA256 = 039aa067…` is the hash of a **CRLF** (Windows) checkout. The git blob is **LF**
(`* text=auto`, hash `043e89e1…`). On a Linux checkout `services/shape_extraction.pinned_script_executor` would refuse
the unchanged script.

This is not hidden:

- `tests/test_r7_shell_modal_safety.py` asserts both facts: the CRLF content equals the pin, and the LF blob hash
  differs;
- the pin and the executor are unchanged.

**Options for the SUPERVISOR:**

- (a) pin the content hash after line-ending normalisation;
- (b) pin the LF blob hash and keep a `.gitattributes` rule `abaqus_scripts/extract_odb.py -text` / `eol=lf`;
- (c) keep the CRLF pin and declare governed extraction Windows-only.

Each is a governed decision, because the hash enters the extraction identity.

The root-cause extractor patch (no `frameValue`; a zero frequency stays 0; refuse a frame contradicting its
description; select mode frames by mode number) remains a proposal that depends on the same re-pin decision.

## 2. R7-B: fail-closed shell gate of guided registration

### Problem and the defect found by the audit

For a conventional shell (S4R in the plate model: 10 201 nodes, z = 0, normals +Z), `max_z` and `min_z` select the
same nodes, so `side` cannot name the measured face. In R7, `fe_element_summary` was optional and the GUI never passed
it, so a flat surface was still registered, with only a warning.

### Architecture (SUPERVISOR-authorised diagnostic extension; no governed contract changed)

**`src/services/shell_surface.py`:**

- `load_fe_input` / `parse_fe_input`: the model's INP, with its SHA-256. For the measured instance's part only it
  reads the element types, the node coordinates with the instance translation, and the connectivity normals of flat
  3- / 4-node conventional shells. A rotated instance is marked.
- `bind_fe_input`: **the INP is accepted only if the instance's node labels AND coordinates equal the loaded FE
  geometry, node for node** (tolerance 1·10⁻³ mm). A matching SHA-256 of some INP is not enough. Rotated instances,
  missing instances and mixed shell / solid types are refused. The binding yields `kind` (shell or non-shell) and a
  uniform normal direction (+Z / −Z, or none).
- `parse_shell_face`: the guided-only evidence block `shell_measured_face` (`auto-id/guided-shell-face/v1`), with
  fields `fe_instance`, `fe_input_sha256`, `normal_direction`, `measured_face` (`positive_normal` /
  `negative_normal`) and `face_evidence`.

**`src/services/guided_registration.py`:**

- `PhysicalEvidence.shell_face` is optional. `document()` adds `shell_measured_face` only when it is present, so every
  pre-R7 evidence hash is unchanged.
- `evidence_from_document` parses the block separately. **`parse_geometry_calibration` is not touched.**
- `establish_guided_registration(..., fe_input=None)` calls `_shell_gate`. It runs after the existing orientation,
  determinant, experimental-source, modal-set and FE-frame checks, and before the M2 builder:
  1. **A flat measured surface (one z level) without a bound FE input → REFUSE** (`fe_input`). Equal z alone is never
     taken as proof of a shell.
  2. An FE input that does not bind node for node → REFUSE (`fe_input`).
  3. A bound non-shell: proceeds as before. A flat one carries a warning. A shell-face statement for it → REFUSE.
  4. A bound conventional shell:
     - the `shell_measured_face` block is required;
     - its `fe_input_sha256` and `fe_instance` must be the bound ones;
     - the element normals must be uniform, and the stated normal must equal them;
     - the experimental +z axis (towards the scanner) must map to the normal for `positive_normal`, or to its opposite
       for `negative_normal`, as stated in `experimental_axes_in_fe`;
     - any contradiction → REFUSE.
  5. Mirrored axes (determinant −1): refused, as before.
  6. The binding and the face statement are recorded in `metrics["fe_input"]`, inside the hash-sealed record.
- `verify_for_files`, which runs when a saved registration is opened and before every analysis, **refuses a record of
  a flat measured surface that carries no bound FE input**: records made before R7, or without the INP.

**GUI (`src/guided_registration_ui.py`) — the real path:**

- the new button **Locate FE input (INP)...**;
- a files-table row "FE input (INP)";
- *Check and build* loads the INP and passes it to `establish_guided_registration`;
- without it, a flat surface is shown as `REFUSED (fe_input)`;
- the evidence table shows the "shell measured face" row.

This is exercised by `DialogTests` in `tests/test_guided_registration.py`.

**Unchanged:**

- the M2 builder (`physical_registration.py`) and `parse_geometry_calibration`;
- the governed passports (`auto-id/specimen/v1.1`), SPEC v1.2, the MAC and geometry thresholds and production gates;
- a guided registration stays `governed = false` and `production_ready = false`.

### Effect on existing data

| Case | Effect |
|---|---|
| Accepted SP-02 / SP-13 (solid face instances with two z levels) | not degenerate; no FE input is required; built by the unchanged builder |
| Synthetic M2 fixtures (single-layer "solid" instances) | flat, so now need a bound FE input. The guided tests supply a generated solid INP bound to the same geometry (`tests/r7_support.py`). The governed builder tests (`test_physical_registration`, `test_registration_uncertainty`) do not use the guided path and are unchanged |
| Real plate (diagnostic, `runs\r7_r1\real_plate_binding.json`) | V3 INP copy (SHA-256 equal to its manifest) bound to the R6 extraction: 10 201 nodes, max difference 1.5·10⁻⁵ mm, S4R, normals +Z (10 000 / 10 000) → `shell` |

## 3. Files changed (R7 + R7 R1)

| File | Change |
|---|---|
| `src/abaqus_bridge.py` | `described_frequency`, `reliable_eigfreq`, `manifest_frequency_problem`; per-mode refusal in `load_extracted_odb` |
| `src/services/shell_surface.py` | FE-input parsing, node-for-node binding, shell-face block |
| `src/services/guided_registration.py` | `shell_face` evidence field; `_shell_gate`; `fe_input`; `verify_for_files` binding rule; evidence row |
| `src/guided_registration_ui.py` | Locate FE input (INP)...; passed to the build |
| `tests/test_r7_shell_modal_safety.py`, `tests/r7_support.py` | 31 R7 tests and the INP generator |
| `tests/test_guided_registration.py` | the synthetic flat instances get a bound solid INP; the GUI fail-closed case is added |
| `docs/reconciliation/R7_SHELL_MODAL_SAFETY.md`, `docs/gui/GUIDED_PHYSICAL_REGISTRATION.md`, `docs/auto_id/STATUS.json`, `docs/auto_id/CHANGELOG.md` | documentation |

## 4. Tests

**R7 (`tests/test_r7_shell_modal_safety.py`, 31 tests):**

- pinned script content and OD-R7-1, documented as a fact;
- all records agree;
- **manifest and description agree but EIGFREQ contradicts → refused** (function and loader);
- the zero mode recorded as the mode number is refused;
- without a description, the manifest is checked against EIGFREQ, and the rounded frame value 207.43 against EIGFREQ
  207.4273 is accepted;
- single records are unchanged;
- an EIGVAL-inconsistent EIGFREQ is not a reliable record; a rigid negative EIGVAL agrees with 0;
- an R6-like package loads 3 and 7 without the false 1 / 2 Hz, and the elastic value is kept;
- correct old packages are unchanged; an all-false package is refused;
- INP element types and normals; node-for-node binding; shifted, rotated and other-instance inputs refused;
- flat geometry is not a shell claim;
- a flat surface without an FE input is refused;
- a bound non-shell builds and is not governed;
- a shell without a face is refused; a shell with a consistent face passes;
- a wrong normal, a face contradicting the axes' Z sign, a statement for another FE input, a shell statement for a
  non-shell and non-uniform normals are all refused;
- mirrored axes are refused, and an invalid block is refused;
- the pre-R7 evidence hash is unchanged;
- a saved flat-surface record without a binding is not applied.

The results of the existing guided, physical, SP-02 / SP-13, loader and full-suite runs are given in §6.

## 5. Baseline issue (not fixed): `test_v12_i5_contract_closure`

The test `QuestionContractTests.test_a_calibration_pass_does_not_change_the_material_verdict` reads
`FamilyConsistencyTests.campaigns`, a class attribute filled in **another class's** `setUpClass`.

- `unittest` loads a module's test classes in alphabetical order (`FamilyConsistencyTests` first), so CI passes.
- pytest collects them in definition order (`QuestionContractTests` first), so the dict is empty and a `KeyError`
  follows.

It fails identically on clean `origin/main` `aa08ad9`. It is a test-order dependency outside R7's scope. No scientific
logic was changed.

## 6. Test results (R7 R1)

| Run | Result |
|---|---|
| `tests/test_r7_shell_modal_safety.py` | 31 passed |
| `tests/test_guided_registration.py` | 22 passed, 1 skipped (store-gated real SP-13 frame test) |
| Full `python -m unittest discover -s tests` (the CI command) | **2486 tests, OK, 96 skipped** |
| Full pytest | **2424 passed, 112 skipped, 1 failed**; the failure is the baseline `test_v12_i5_contract_closure` (§5) |

**Executed, not skipped:**

- the store-free SP-02 / SP-13 tests: frozen registration hashes, passports, re-evaluation records and the G2
  precision tests;
- the governed builder tests (`test_physical_registration`, `test_registration_uncertainty`), which are unchanged by R7.

**Skipped (92 store-gated tests in pytest):** these need `snadwich` (the original `D:\Snadwich`),
`carbon-project-archive` or `m7-run-*`. Among them are the real-data SP-02 / SP-13 registration, fixture, QC and
what-if regressions.

- They were **not run**. Their inputs `SP02_polymax_retry_260803.unv`, `SP02_fe_geometry.csv` and
  `SP13_fe_geometry.csv` are not in the verified V2 / V3 copies (only `SP13_a_polymax.unv` is), and originals may not
  be opened.
- The accepted SP-02 / SP-13 registrations are produced by `physical_registration.py`, which R7 does not change.
  Their guided path ("Use accepted scan calibration") selects non-degenerate solid face surfaces, which the shell gate
  does not affect.

## 7. Remaining limitations

- **OD-R7-1** (§1) and the extractor re-pin are open governed decisions.
- The shell gate supports flat conventional shells with uniform normals and unrotated instances; curved or rotated
  shells are refused.
- The store-gated SP-02 / SP-13 data tests need the original store `D:\Snadwich` and were not run (§6).
