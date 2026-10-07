# M6.4 transverse-constant screening (D-066)

FE-only screening of the fixed carbon-face constants E3, ν13, ν23, G13 and G23 (SPEC §5, §5.2).

## Envelope record

`M6_4_transverse_envelope.json`: schema `auto-id/transverse-screening-envelope/v1`, parsed by
`src/domain/transverse_screening.py`.

| Field | Meaning |
|---|---|
| `basis` | `LITERATURE_INTERIM_SCREENING_ENVELOPE`. Not a measured property, a material-specific prior or a calibrated distribution |
| `reference_candidate` | The in-plane point where the screening is done (the CARBON-4C baseline) |
| `criterion` | SPEC §5: max \|Δf/f\| strictly below 0.3 %. Fixed, not configurable. Bookkeeping only |
| `constants` | Baseline (the governed fixed value), low and high endpoint per constant |
| `extraction_modes` | FE modes extracted per job (7–30, as the archived baselines) |
| `specimens` | Forward model, solver profile, archived baseline pack and frozen observation rows per specimen |

| Constant | Baseline | Low | High |
|---|---|---|---|
| E3 | 6700 MPa | 5000 | 10000 |
| ν13 | 0.30 | 0.20 | 0.40 |
| ν23 | 0.30 | 0.20 | 0.40 |
| G13 | 2200 MPa | 2200 (= baseline, no solve) | 5000 |
| G23 | 2200 MPa | 2200 (= baseline, no solve) | 5000 |

## Rule

- **Design:**
  - one constant at a time, at both endpoints;
  - every other constant stays at its baseline;
  - E_in and G12 stay at the reference candidate (no refit).
- **Observations:** the frozen rows, fit and holdout. Each row is followed from the baseline FE state by
  FE-to-FE MAC (M4.5, `track_branches`) and is never re-paired.
- **Classification:**
  - max |Δf/f| < 0.3 % over all rows, specimens and endpoints → `NEGLIGIBLE_FOR_BUDGET`;
  - otherwise → `INCLUDE_IN_UNCERTAINTY_BUDGET`. This is not a failure and never a reason to re-tune.
- **Refusal:** a tracking refusal gives `NOT_CLASSIFIED_TRACKING_REFUSED` and is escalated.
- **Scope of the 0.3 % criterion:** it is not the model-fit target. The M7 real-data interpretation uses
  the practical engineering target of D-066 (correct mode identity / MAC; frequency preferably within
  ~5 %, up to ~10 % acceptable).

## Workflow

Stores are configured with `AUTO_ID_FIXTURE_ROOT_<STORE>`.

| Step | Command | Abaqus |
|---|---|---|
| Plan | `python tools/m6_4_transverse_screening.py plan --run-root <dir>` | no |
| Run | `python tools/m6_4_transverse_screening.py run --run-root <dir> --abaqus <cmd> --authorised-manifest-hash <hash>` | **yes; HUMAN gate only** |
| Evaluate | `python tools/m6_4_transverse_screening.py evaluate --run-root <dir> --result <file>` | no |

- **Plan:**
  - checks that the reference candidate regenerates each archived baseline job byte-identically, so the
    baseline pack is reused and not solved;
  - renders one content-addressed job per perturbation;
  - writes `screening_manifest.json`, the HUMAN Abaqus manifest.
- **Run:**
  - refuses any manifest hash other than the authorised one;
  - solves with the pinned solver profiles and extracts with the pinned `abaqus_scripts/extract_odb.py`;
  - keeps a hash-chained journal: no automatic retry, no duplicate solve on resume.
- **Evaluate:** writes the result record (`auto-id/transverse-screening-result/v1`):
  - the per-row signed Δf/f and log-sensitivity;
  - the tracking MAC;
  - the per-constant classification;
  - an informational all-mode diagnostic that is never used for classification.

Run outputs (INPs, ODBs, packs, journal) are run-store data and are never committed.
