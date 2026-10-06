# Real-specimen source inventory (`D:\Snadwich`)

**Status:** a factual inventory note, accepted by the SUPERVISOR on 2026-10-06.
- **Basis:** the read-only source audit of 2026-10-06.
- **What it is not:** it creates no passport, fixture, registration or forward model, and imports
  no specimen into Auto-ID.
- **What it governs:** facts only.
  - **AVAILABLE_NOT_YET_GOVERNED:** a value that exists in the curated tree but has no passport or
    fixture yet.
  - **NOT_AVAILABLE:** the information exists in neither the tree nor the repository.

**Sources:** each specimen folder's `spec` file is the curated specimen description; the
experimental files are the UNVs listed. The UNV content was established read-only:
- dataset types;
- dataset-151 header: Polytec PSV 10.2 for raw data, Simcenter Testlab 24A for PolyMAX exports;
- dataset-55 fitted modes;
- dataset-58 resolution.

## Specimens

"Raw FRF" means dataset 58 (FRF, coherence, cross-spectrum), one force reference. Unless stated
otherwise: 121 points, Δf 0.3125 Hz.

| Specimen | Spec description | Type | Experiment | Fitted modes (dataset 55) | FE | Class | Auto-ID governance |
|---|---|---|---|---|---|---|---|
| SP-01 (folder `SP-01 -core mass less`) | old T300 plain, faces 0.45; PLA auxetic; 502.13 × 499.25 × 2.9 mm; spec has an experiment-vs-Abaqus table | sandwich | raw FRF 260624 | no | CAE/JNL only (no INP/ODB) | EXPERIMENT + FE (CAE) | not governed |
| SP-02 | old T300 plain, faces 0.45; PLA honeycomb; "copy of SP-10" | sandwich | raw FRF 260803 retry | yes: `SP02_polymax_retry_260803.unv` (Bravo) | V01 and V02 INP/ODB; CAE | EXPERIMENT + FE | **governed** (fixture SP02/bravo-1) |
| SP-03 | old T300 **twill**, faces 0.45; PLA auxetic | sandwich | raw FRF 260803 | no | none | EXPERIMENT ONLY | not governed |
| SP-04 | old T300 plain, faces 0.25; TPU honeycomb; 300 class | sandwich | raw FRF 260822 (0–1000 Hz) | no | none | EXPERIMENT ONLY | not governed |
| SP-05 | old T300 plain, faces 0.245; TPU auxetic; 300 class | sandwich | raw FRF 260706a (0–1000 Hz) | no | `SP05_modal` INP/ODB; CAE; SAT | EXPERIMENT + FE | **not governed** |
| SP-06 | new T300 plain, faces 0.25/0.235; TPU auxetic; DP190 | sandwich | none | no | none | INSUFFICIENT | — |
| SP-07 | new T300 plain, faces 0.235; TPU honeycomb; DP190 | sandwich | raw FRF 260824 (0–1000 Hz) | no | none | EXPERIMENT ONLY | not governed |
| SP-08 | new T300 plain, faces 0.25/0.24; PLA auxetic | sandwich | raw FRF 260828 | no | none | EXPERIMENT ONLY | not governed |
| SP-09 | new T300 plain, faces 0.235; PLA honeycomb | sandwich | raw FRF 260831 | no | none | EXPERIMENT ONLY | not governed |
| SP-10 | old T300 plain, faces 0.40/0.39; PLA honeycomb; "copy of SP-02" | sandwich | raw FRF 260831; raw FRF 260911 "b_rotated" (323 points, Δf 0.156 Hz) | **yes:** `SP10_b_polymax.unv` (sets "Bestttt", "Processing_polym") | none | EXPERIMENT ONLY (fitted) | **not governed** |
| SP-11 | old T300 **twill** 0.45; 350 × 347 × 0.45 mm; 79.59 g | **bare plate** | raw FRF 260824 / 260826 a / 260826 b_center (inconsistent between sessions, D-057) | **no** | none | EXPERIMENT ONLY | identity only (D-049, D-057) |
| SP-13 (physical registration from stored PSV records, D-062) | old T300 plain, faces 0.425; PLA auxetic; "copy of SP-01" | sandwich | raw FRF 260909; raw FRF 260910 a (289 points, Δf 0.156 Hz) | yes: `SP13_a_polymax.unv` (Best) | SP13_modal and mesh_local_v1 INP/ODB; interface variants; CAE; core CAD | EXPERIMENT + FE | **governed** (fixture SP13/best) |

There is no SP-12 folder.

## Families and topologies (from the spec files)

| Group | Specimens |
|---|---|
| Old T300 twill 0.45 | SP-03 (sandwich), **SP-11 (the only bare plate)** |
| Old T300 plain about 0.4–0.45 | SP-01, SP-02, SP-10, SP-13 (sandwiches) |
| Old T300 plain about 0.25 | SP-04, SP-05 (TPU sandwiches); not named in the SPEC §13 family list |
| New T300 plain about 0.235–0.25 | SP-06, SP-07, SP-08, SP-09 (sandwiches) |
| PLA auxetic core | SP-01, SP-03, SP-08, SP-13 |
| PLA honeycomb core | SP-02, SP-09, SP-10 |
| TPU auxetic core | SP-05, SP-06 |
| TPU honeycomb core | SP-04, SP-07 |
| Adhesive | DP420, except SP-06 and SP-07 (DP190) |

PLA grade and print process are not recorded.

## AVAILABLE_NOT_YET_GOVERNED

- **Nominal spec values for every specimen:** plan dimensions, part masses, single face-thickness
  values, core thickness. The SP02/SP13 passports still carry `null` for these.
- **SP-10:** the PolyMAX set and the 323-point session.
- **SP-05:** the INP/ODB.
- **SP-01:** the CAE and its spec experiment-vs-Abaqus table.
- **SP-13:** the 260909 session and the interface-variant models.
- **SP-02:** the V01 model.
- **PLA density lineage:** spec 9.01e-10 t/mm³ vs INP 1.0475e-9 (SP-02) and 1.1212e-9 (SP-13).

The spec carbon and PLA constants are FE input values, not measurements.

## NOT_AVAILABLE (neither source)

- a ≥ 9-point thickness map (any specimen);
- mass and dimension uncertainties;
- suspension thresholds;
- excitation attachment masses;
- documented remounts;
- fitted SP-11 modes;
- an SP-11 FE model;
- any core-tile specimen or test;
- measured twill material constants;
- a non-contact excitation route;
- a steel validation specimen;
- M6.4 variation ranges.
