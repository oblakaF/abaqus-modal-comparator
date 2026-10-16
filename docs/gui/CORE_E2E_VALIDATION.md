# CORE-E2E — end-to-end validation of the ODB + UNV comparator (2026-10-16)

Branch `validation/core-modal-e2e` from `main` `eaaf60a` (PR #83 merged). Run root (machine-local, not in Git):
`D:\git\abaqus-modal-comparator-work\runs\core_e2e\run_20261016`.

## What this branch contains

| Commit | Content |
|---|---|
| `b183b45`, `05658c3`, `98ceab6`, `fff2e30`, `ac44f30` | The P7 commits of PR #82 (`137574e`, `be88a08`, `35533d8`, `ccc1b21`, `7c697d8`; `137574e` is the port of PR #81), cherry-picked **without** the Quick Calibration commits that PR #82 is stacked on |
| `f20d69f` | The P7 tests without the Quick Calibration modules (`tests/synthetic_plate_support.py`, `src/application_layers.py`) |
| `94d5f36` | Fix: a completed Abaqus extraction is reused across analysis folders of one workspace |
| `5c4ffef` | Fix: the FE-geometry reuse no longer denies archived sensitivities it does not check |
| `0507d14` | Fix: frequency-only rows outside the extracted FE mode range are marked |

No SPEC, DECISIONS, EVIDENCE, registration, threshold or gate is changed. Production calibration execution stays
BLOCKED / NOT_AUTHORISED (D-079, D-080).

## Inputs (verified copies; the originals were only read)

`copy_verification.json` in the run root: SHA-256 of each source before, of the copy, and of the source after.

| File | SHA-256 | Governed match |
|---|---|---|
| SP02 baseline ODB `SP02_f3e592281bebce66.odb` | `67f581af…` | accepted CARBON-4C baseline |
| SP13 baseline ODB `SP13_a46d08b52995e078.odb` | `8c89585d…` | accepted CARBON-4C baseline |
| `SP02_polymax_retry_260803.unv` | `2671db01…` | SP02/bravo-1-physical |
| `SP13_a_polymax.unv` | `f2680235…` | SP13/best-physical |
| `SP02_Modal_V02.inp`, `SP13_mesh_local_v1_modal.inp` | `574ae78a…`, `9d410584…` | M3 forward models |
| T3 `SP13_modal.odb` (new FE geometry) and its existing GUI extraction (modes 7–25) | `befab961…` (ODB copy) | not governed |
| T4 SP-04 dataset-58 UNV and the P8 extraction bundle of `Honeycomb_TPU_FreeFree.odb` | `f7c46dad…` | not governed |

## Real GUI scenarios (main window, `gui_e2e.py`, user profile redirected, every other process refused)

| Scenario | Abaqus | Result |
|---|---|---|
| T1 SP-02, accepted registration | 1 real Abaqus 2024 Python extraction (modes 6–15, 1 663 816 nodes) | ALL PASS. The fresh extraction is **byte-identical** to the archived 2026-10-12 extraction (geometry and all 10 mode files). Strict pairs R1 (exp 2 / FE 8), R2 (4 / 10), R3 (7 / 13): FE Hz identical, MAC within 1e-9. Archived sensitivities VERIFIED; PDF and Excel reports written |
| T1b SP-02, automatic registration | 0 (extraction reused; 91 s instead of 551 s) | ALL PASS. Ambiguous orientation → registration reused by FE geometry identity; the same 6 pairs as T1 |
| T2 SP-13, accepted registration | 0 (archived M4 extraction PRE-SEEDED, disclosed) | ALL PASS. R1 (4 / 10) −9.05 %, MAC 0.958; R2 (7 / 13) −2.76 %, MAC 0.947. Observation readiness: §8 count NOT MET (1 FIT family) |
| T3 new SP13 ODB | 0 (existing extraction, manifest) | ALL PASS. FE geometry `b4015d13…` (1 558 721 nodes) ≠ accepted `34d69d79…` (1 585 637): no registration reuse, FREQUENCY_ONLY_DIAGNOSTIC, no MAC, no pair; individual modes viewable |
| T4 SP-04, dataset 58 only | 0 (P8 bundle) | ALL PASS. 19 FRF peaks labelled PROVISIONAL; FREQUENCY_ONLY_DIAGNOSTIC; no MAC, no pair, no orientation chosen |

## Stage B (two diagnostic E_in +2 % solves)

Planned with the accepted M3 builder and the M4.6 pipeline (`IdentificationPipeline.evaluate`, one candidate, no LM):
manifest `stage_b_manifest.json`, hash `104583b845dab985db949f0fec109254f51a9b158a447f81cc6ec1e9e992ae52`; jobs
`SP02_c3a8d68e81ca46c2`, `SP13_c8f5b51e3863775f` (one changed INP line each: E1 = E2 52 000 → 53 040 MPa; the
baseline point reproduces the archived baseline jobs exactly). **Not executed:** the session's permission system
refused the real solve command; it awaits explicit authorisation
(`python tools/stage_b.py run <run root> 104583b8…`).

Archived replacement check (no Abaqus): central differences of the archived ±5 % states predict the RUN_A solve at
E 55 593 MPa (+6.9 %) within 0.02 % on all five strict rows (`archived_linearity_check.json`).

## Open items

- Quick Calibration (PR #82 base, `aa76de3`) is a second optimiser path; it is not on this branch and needs its own
  SUPERVISOR decision.
- The 11. Scaling tab wraps its text into a narrow column (known narrow-wrap behaviour of hidden tabs).
- The "Mean MAC" card averages every admissible pair, including Review / Poor ones.
