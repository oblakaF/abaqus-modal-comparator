# R7 — Zero-frequency safety of extraction packages and the shell mid-surface guard

**Branch:** `fix/r7-shell-modal-safety`, from `origin/main` `aa08ad9`. **Status:** `REVIEW_READY`. It is not merged.

No Abaqus was run. No original was opened. The pinned extractor and every governed rule are unchanged.

## 1. R7-A: zero eigenfrequencies recorded as mode numbers

### Error

The R6 extraction package of the single CFRP plate records modes 1 and 2 at 1 Hz and 2 Hz. The `.dat` file, the
frame descriptions ("`Freq = 0.0000`") and the EIGFREQ history all give 0 Hz.

**Exact cause** (`abaqus_scripts/extract_odb.py`, `frame_frequency`):

- `frame.frequency == 0` is treated as missing, by the test `value not in (None, 0)`;
- the code then falls back to `frame.frameValue`, which in an Abaqus frequency step holds the mode number;
- the fallback search of the description uses `frequency\s*[:=]`, which does not match the actual "`Freq =`" text.

A zero-frequency (rigid-body) frame therefore receives its mode number as its frequency. `select_modal_step` keeps it,
because the value is now positive.

### Why the extractor itself was not edited

`abaqus_scripts/extract_odb.py` is **pinned**:

- `services/shape_extraction.py` holds `PINNED_EXTRACT_SCRIPT_SHA256 = 039aa067…`;
- that hash enters the extraction identity of the governed Auto-ID shape-pack path.

Editing the script would either break that path or require changing the pin, which would change governed extraction
identities. That is a governed-gate change, outside R7's authority. A new test asserts that the pin is unchanged and
documents the root-cause behaviour.

### Fix (loader, `src/abaqus_bridge.py`)

- `described_frequency()` reads the frame description's "`Freq = …`" and the half-unit precision of its printed text.
- `manifest_frequency_problem()` compares the manifest frequency with the independent records of the same frame:
  - first the frame description;
  - if there is none, the EIGFREQ history, but only when the manifest value equals the mode number (the artifact
    signature).
- A contradicted manifest frequency is **refused for that mode**:
  - the mode is not loaded and cannot take part in pairing, MAC or frequency errors;
  - the reason, the manifest value, the described value, the EIGFREQ value and whether the independent records agree
    are stored in `metadata["rejected_frequency_modes"]`.
- **No value is substituted.** If every mode is refused, the package is refused with the reasons.
- A consistent value, or one that cannot be checked (a legacy package with no description and no history), is left
  unchanged.
- The EIGFREQ / EIGVAL refinement (`history_frequencies`) is unchanged and runs only on the modes that are kept.

On the stored R6 package (read only) the loader now:

- refuses modes 1 and 2; description and EIGFREQ agree on 0.0 Hz, which is recorded but not used;
- loads modes 3–20;
- gives mode 7 at 19.07217 Hz from EIGFREQ.

The R6 package itself is not modified.

### Proposed extractor patch (NOT applied; needs a SUPERVISOR decision on the pin)

```python
_DESCRIPTION_FREQUENCY = re.compile(r"\bfreq(?:uency)?\s*[:=]\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[Ee][-+]?\d+)?)", re.I)

def frame_frequency(frame):
    """Physical frequency of a modal frame, or None. frameValue is never used (it can be the mode number)."""
    value = getattr(frame, "frequency", None)          # 0.0 is a valid frequency
    match = _DESCRIPTION_FREQUENCY.search(getattr(frame, "description", "") or "")
    described = float(match.group(1)) if match else None
    if value is not None and described is not None and abs(float(value) - described) > half_unit(match.group(1)):
        raise RuntimeError("frame frequency contradicts its description")   # REFUSE
    return float(value) if value is not None else described
```

The patch also needs these changes:

- select a mode frame by mode number ≥ 1 rather than by frequency > 0, which excludes the base state;
- record zero-frequency modes explicitly (for example `zero_frequency_modes` in the manifest);
- then re-pin the script, with `PINNED_EXTRACT_SCRIPT_SHA256` and extraction identities, as a governed decision.

## 2. R7-B: shell mid-surface and `measured_surface.side`

### Problem

The measured surface is selected by `side` (`max_z` / `min_z`) among one instance's nodes. For a conventional shell
(S4R in the plate model: 10 201 nodes, z = 0, normals +Z) both select the same nodes. **`side` cannot say which
physical face the scanner saw**; only the Z sign of `experimental_axes_in_fe` relative to the element normal does.

### Why the full solution is stopped here (decision required)

An explicit face statement needs a new evidence field, for example `side: "mid_surface"` and
`shell_face: "positive_normal" | "negative_normal"`. The guided evidence is parsed by
`domain.specimen_manifest.parse_geometry_calibration`, the parser of the governed specimen passports
(`auto-id/specimen/v1.1`). A new field or `side` value would change that governed contract. Per the R7 instruction this
part is **stopped and proposed** (§2.3). It is not implemented.

### Implemented (diagnostic only; no format, rule or gate changed)

- **New `src/services/shell_surface.py`:**
  - `is_conventional_shell()`: S…/STRI… element types; the continuum shells SC6R / SC8R are excluded;
  - `surface_is_degenerate(fe, instance, unit)`: true when `max_z` and `min_z` select the same nodes;
  - `inp_element_summary(text)`: per assembly instance, the element types from the FE input text (with its SHA-256)
    and, for flat 3- / 4-node shells, the z sign of the connectivity normal. A rotated instance is reported as
    `unknown`, never guessed.
- **`guided_registration.establish_guided_registration(..., fe_element_summary=None)`:**
  - **refuses** when the supplied FE element summary confirms that the measured instance is a conventional shell
    (field `measured_surface`); this is the R7 rule "no confirmed face → refuse";
  - when the measured surface is degenerate but the element types are not supplied, the registration is built as
    before and **states the limitation** in its warnings: the face is fixed only by the Z sign, and a shell is not
    excluded;
  - equal z coordinates alone are never taken as proof of a shell, because the synthetic single-layer solid fixtures
    have them too;
  - mirrored axes (determinant −1) stay refused;
  - a guided registration stays `governed = false` and `production_ready = false`.
- **Unchanged:**
  - the M2 builder (`physical_registration.py`) and every solid registration rule;
  - the evidence format;
  - the GUI, which does not pass `fe_element_summary`; behaviour there is unchanged apart from the warning.

### Proposed format (for a SUPERVISOR decision)

`measured_surface = {fe_instance, side: "mid_surface", shell_face: "positive_normal" | "negative_normal",
normal_evidence: {inp_sha256, element_types, normal_counts}}`

Accepted only when all of the following hold:

1. the element summary confirms a conventional shell for that instance, from an INP with a pinned SHA-256;
2. every normal of the instance points the same way (all +Z or all −Z), with no rotated instance;
3. the Z sign of `experimental_axes_in_fe` equals the stated face: positive normal side ⇔ the experimental +z axis
   (towards the scanner) maps to the normal's direction; a contradiction is refused;
4. the determinant is +1.

Solid models keep `max_z` / `min_z` unchanged. This would be a change of the governed passport schema, or a
guided-only schema split, and needs a decision.

## 3. Files changed

| File | Change |
|---|---|
| `src/abaqus_bridge.py` | `described_frequency`, `manifest_frequency_problem`; `load_extracted_odb` refuses contradicted manifest frequencies per mode |
| `src/services/shell_surface.py` | new diagnostic service |
| `src/services/guided_registration.py` | optional `fe_element_summary`; shell refusal; degenerate-surface limitation |
| `tests/test_r7_shell_modal_safety.py` | 18 regression tests |
| `docs/reconciliation/R7_SHELL_MODAL_SAFETY.md` | this report |
| `docs/gui/GUIDED_PHYSICAL_REGISTRATION.md` | R7 note |
| `docs/auto_id/STATUS.json`, `docs/auto_id/CHANGELOG.md` | R7 entry |

## 4. Tests

**New (`tests/test_r7_shell_modal_safety.py`, 18 tests):**

- the pinned script is unchanged, and the root cause is documented;
- description parsing for zero, near-zero and elastic modes and for the base state;
- zero, near-zero and elastic consistency;
- the mode-number artifact is caught by the description and, without one, by EIGFREQ;
- unverifiable legacy values are left unchanged; a contradicted value is refused with the disagreement recorded;
- an R6-like package loads modes 3 and 7 without 1 Hz / 2 Hz, the rejections are recorded, and mode 7 takes the
  EIGFREQ value;
- an all-false package is refused, and a correct package is unchanged;
- INP element types and normals per instance; rotated instance → unknown; SC8R is not a conventional shell;
- equal z is detected but is not a shell claim;
- guided: a confirmed shell is refused; a degenerate surface of unknown type states the limitation; solid element
  types keep the same registration hash; mirrored axes are refused; the registration is not governed.

**Existing related tests:** guided, physical, SP-02, SP-13, the loader format and the extractor gave **71 passed,
11 skipped** in this group.

- The 11 skips are the store-gated SP-02 / SP-13 data tests. They need the `snadwich` store, `D:\Snadwich`, which
  is an **original** that R7 forbade opening.
- Those tests were therefore **not run**. The accepted SP-02 / SP-13 registrations, passports and hashes are produced
  by `physical_registration.py`, which R7 does not change; the store-free SP-02 / SP-13 tests pass.

**Full pytest** on this branch: **2411 passed, 112 skipped, 1 failed**. The failure is
`test_v12_i5_contract_closure.py::QuestionContractTests::test_a_calibration_pass_does_not_change_the_material_verdict`
(`KeyError` in a class-level dict). It fails identically on clean `origin/main` `aa08ad9`, so it is pre-existing
and not caused by R7. CI results are given in the SUPERVISOR report.

## 5. Remaining limitations

- The pinned extractor still writes mode numbers for zero-frequency frames. The loader refuses such values, but the
  root-cause fix needs the re-pin decision (§1).
- A shell face cannot yet be stated in evidence. A confirmed shell is refused; an unconfirmed degenerate surface only
  carries a warning, because the element type is not in the extraction package and the synthetic solid fixtures are
  single-layer.
- The store-gated SP-02 / SP-13 regressions should be re-run by the SUPERVISOR with the store roots configured.
