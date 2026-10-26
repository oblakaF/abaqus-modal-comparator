# APP-IMPORT-2414 — dataset 2414 files read by pyuff (2026-10-26)

Branch `feature/app-import-2414-compatibility` from `main` `bf27ef9`. An importer fix; no scientific rule changes.

## The problem (reproduced)

A dataset-2414 UNV on disk, written and read back with the installed pyuff 2.5.6, gave **no experimental modes**:
"No experimental modal vectors or FRFs were found in the UNV/UFF file. Detected dataset types: 2411, 2414".

**Cause.** `pyuff.UFF.read_sets()` names records 10–13 of dataset 2414 only for frequency response (analysis
type 5). For every other analysis type (normal modes 2, complex eigenvalue 3 and 7, …) it returns them **by
position**:

- `record10_field1` … `record10_field8`, `record11_field1` … `record11_field8`;
- `record12_field1` … `record12_field6`, `record13_field1` … `record13_field6`;
- the nodal values as `data_at_node`.

The importer (`universal_hardening._safe_mode_2414`) looked only for named keys (`mode_number`, `frequency`, `x`,
`y`, `z`, …). It found no frequency, so the record was not imported.

**Reproduction.** A temporary UNV with dataset 2411 and dataset-2414 records of analysis types 2, 3 and 7 (complex
single precision, three values per node), read back by `read_sets()`:

- every 2414 record has the keys `record10_field1..8`, `record11_field1..8`, `record12_field1..6`,
  `record13_field1..6` and `data_at_node`, and no `mode_number`, `frequency`, `x`, `y`, `z`;
- the values are those written: `record10_field6` = mode number, `record12_field2` = frequency;
- `data_at_node` holds six numbers per node (Re X, Im X, Re Y, Im Y, Re Z, Im Z).

## The field definition (not guessed)

The dataset-2414 definition (I-DEAS File Formats Reference) is reproduced in `pyuff.datasets.dataset_2414`
(`get_structure_2414`); the same record order appears in the specification comments quoted by M4 Engineering. It
fixes:

- **Record 9:**
  - data characteristic 2 = 3 DOF global translation vector (3 values), 3 = 6 DOF (6 values);
  - data type 2 / 4 = real, 5 / 6 = complex.
- **Records 10 and 11** — integer analysis-type specific data (1–10): design set ID, iteration number, solution set
  ID, boundary condition, load set, **mode number (record 10 field 6)**, time step number, frequency number;
  creation option, number retained.
- **Record 12** — real analysis-type specific data (1–6): time, **frequency (field 2)**, eigenvalue, **modal mass
  (field 4)**, **viscous damping (field 5)**, **hysteretic damping (field 6)**.
- **Record 13** (7–12): real / imaginary part of the eigenvalue, modal A / mass, modal B / stiffness.
- **The analysis-type chart:**
  - the mode number is defined for normal modes (2), complex eigenvalue first and second order (3, 7) and
    buckling;
  - the frequency is defined only for normal modes (2) and frequency response (5);
  - modal mass and damping are defined only for normal modes;
  - the complex eigenvalue is defined for 3 and 7 (record 13).
- **Record 15** (data at nodes) — NVALDC values per node, in the order X, Y, Z (, Rx, Ry, Rz). Complex data come
  as real part, imaginary part for each value (notes 3 and 4).

pyuff's own frequency-response reader uses the same names at the same positions of records 10–13.

## The fix (`src/universal_hardening.py`)

**When it applies.** A 2414 record in the positional layout: `data_at_node` and `record10_field6`, with no named
shape, mode-number or frequency key. Such a record is read by position before the existing builder runs. A record
with named keys is read exactly as before.

**Normal modes (analysis type 2) only, after checks:**

- the data are at nodes (dataset location 1);
- the data type is real (2, 4) or complex (5, 6);
- the data characteristic and NVALDC agree (3 DOF = 3 values, 6 DOF = 6 values);
- every node has exactly NVALDC (real) or 2 × NVALDC (complex) finite values;
- the translational shape is not zero at every node;
- the mode number (record 10 field 6) is at least 1;
- the frequency (record 12 field 2) is finite and positive.

**What it reads:**

- the mode number from record 10 field 6, as written;
- the frequency from record 12 field 2, as written;
- modal mass, viscous damping and hysteretic damping from record 12 fields 4, 5 and 6;
- X, Y, Z from record 15 (complex pairs as real + j·imaginary). Rotations of 6 DOF data are not used;
- the measured DOFs follow the importer's dataset-55 rule (`reviewed_core._inferred_measurement_mask`). A component
  is measured only when this mode's own vector carries energy in it. A component written as zeros at every node is
  kept as written in the shape but is **not** a measured DOF. Absent nodes are absent; nothing is filled in.

The mode records `dataset_2414_layout = "dataset 2414 records 10-15 read by position (UNV 2414 definition)"`.

**What it refuses.** These records are not imported; the reason is added to the importer warnings:

- **complex eigenvalue records (3, 7):** the definition gives them no frequency, and no frequency is derived from the
  complex eigenvalue;
- any other analysis type in the positional layout;
- any record that fails a check above.

**Unchanged:**

- the record classification physical / ambiguous / non_modal of `universal_reader`;
- named-key 2414 records, dataset 55 and FRF dataset 58;
- `universal_reader.py`, pyuff and the dependencies.

## Verification

| Check | Result |
|---|---|
| `tests/test_universal_hardening.py` | 16 OK, of which 8 new: real pyuff files on disk |
| What the new tests cover | the layout pyuff returns; normal modes (numbers, frequencies, exact complex components, measured DOFs, coordinates, modal mass, damping); real-valued and 6 DOF records; zero-filled components not measured; complex eigenvalue records refused with the classification unchanged; zero shape, value count, data characteristic, mode number and frequency refused; non_modal and ambiguous classification kept; direct rules, including named keys winning |
| `tests/test_polymax_modal_sets.py` | 17 OK; the new real-file test keeps the physical / non_modal / ambiguous classification |
| `tests/test_local_experimental_preview.py` | 16 OK; the new real-file test: APP-DATA.3 shows the 2414 mode and the refusal of the type-3 record |
| The new real-file tests on `bf27ef9` | fail (no mode is imported) |

The regressions, CI and the Windows check are in the task report.

## Limits

- **An ambiguous positional record is not imported.** The loader of `universal_reader` builds a 2414 mode only for a
  modal analysis type or a named mode number. Such a record keeps its "ambiguous" classification but is not
  imported, and no warning is added. `universal_reader.py` is outside this change.
- **pyuff's own limits remain.**
  - pyuff's writer pads record 12/13 values with two spaces whatever their sign, so a negative value written by
    pyuff is misread by its fixed-width reader. This happened to the complex-eigenvalue fields of record 13 in the
    reproduction.
  - pyuff's positional reader expects one line per node in record 15. A file that wraps more than six values per
    node over several lines (complex 6 DOF data written by another program) is not read correctly by pyuff.
  - Neither is changed here; the checks above refuse a record whose node values do not match NVALDC.
- **Earlier parse results stay in the cache.** The installed importer caches parsed UNV files
  (`fast_cache`, `%LOCALAPPDATA%\AbaqusModalComparator\cache`). The cache key holds the file signature and the
  cache version, not the importer code. A file with positional 2414 records **and** dataset-58 FRFs that was parsed
  before this fix (as FRF-derived data) can return the old result from the cache until the cache is cleared or its
  version is raised. `fast_cache.py` is outside this change.
- **Not tested on a Simcenter Testlab export.** The files here are written by pyuff, following the dataset-2414
  definition.
- **Unchanged:**
  - SPEC v1.2, DECISIONS, the specimen catalogue, registrations, frozen evidence, MAC, pairing and QC criteria;
  - M8 GATE `NOT_MET`; D-077 `NO_GLOBAL_PARAMETER_VALUE`; production Auto-ID BLOCKED / NOT_AUTHORISED.
- No Abaqus, no solver, no LM, no Auto-ID.
