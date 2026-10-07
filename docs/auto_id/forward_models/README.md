# Forward-model manifests (M3)

Schema `auto-id/forward-model/v1` (SPEC §4, §5.2, §16; AUDIT V2). The validator is
`src/domain/forward_model_manifest.py` (`load_forward_model_manifest`,
`bind_forward_model`).

A forward-model manifest binds one accepted Abaqus input to its specimen passport.
Specimen-specific values live here as data, never in code.

| Field | Meaning |
|---|---|
| `forward_model_id` | Stable name of this forward model |
| `specimen_passport` | Repository path of the passport and its canonical `manifest_hash` (pinned) |
| `model_input` | The reference INP: store + relative path, file name, SHA-256 and size (no machine path) |
| `job_prefix` | Prefix of generated job names (`<prefix>_<first 16 hex of the INP SHA-256>`) |
| `material` | Passport material **role** whose `*Elastic, type=ENGINEERING CONSTANTS` record is rewritten, and the accepted source constants the INP must contain |
| `parameterisation` | Which constants a candidate may set (see below) |
| `frequency_request` | Source and requested eigenvalue counts (above the 6 rigid-body modes) |
| `registration` | The FrozenRegistration hash (and path) the forward job is compared through |
| `provenance` | Where each value comes from |

## Material location (M3.1)

- **Name:** the material name is the passport's `materials[<role>]` (SPEC §4: material
  names are given in the specimen passport).
- **Record:** the builder locates that name's unique `*Material` block and its single
  `*Elastic, type=ENGINEERING CONSTANTS` record of nine values.
- **Refused:** a missing or duplicated material, zero or several `*Elastic` options,
  another elastic type, a temperature-dependent record, or source values that differ
  from the manifest.

## Binding

`bind_forward_model(manifest, passport, fixtures)`:
- checks the passport's canonical hash against the pinned one;
- resolves the material name by role;
- when the passport links an experiment fixture, requires the fixture's pinned model
  input, registration hash and path, and FE model name to agree.

## Parameterisation

| Id | Variable | Fixed |
|---|---|---|
| `carbon-property-set/v1` | E1 = E2 = E_in_plane, G12 | E3 = 6700, ν12 = 0.05, ν13 = ν23 = 0.30, G13 = G23 = 2200 MPa |

There is no parameterisation with E1 ≠ E2 (SPEC §5.2). The source constants in a
manifest must carry the fixed values exactly.

## Building forward jobs (M3.2–M3.4)

`services.forward_builder`:

```python
model = load_bound_forward_model(manifest_path, repo_root, fixtures)  # manifest + pinned passport
roots = fixture_roots_from_environment()  # AUTO_ID_FIXTURE_ROOT_<STORE>
evaluation = prepare_forward_jobs([model, ...], carbon_candidate(E_in_plane, G12), roots, output_dir)
```

- **Rewrite:** only the parameterisation's variable constants of the located record,
  plus the eigenvalue count of the single `*Frequency` request when the manifest asks
  for more. A post-check refuses any other changed line.
- **Job name:** `<job_prefix>_<first 16 hex of the generated INP SHA-256>`
  (content-addressed; the accepted naming).
- **Provenance** (`auto-id/forward-job/v1`): manifest, passport, source INP,
  material, candidate, constants, registration, eigenvalue request, generated SHA-256
  and changed lines. It holds no machine path and no timestamp. `job_hash` is its
  canonical SHA-256; `evaluation_hash` covers all jobs of one candidate.
- **No defaults:** there are no default specimens, materials or paths. The reference
  INP is read only from its configured store and verified by size and SHA-256.

## Accepted manifests

| File | Reference INP | Material (passport role `face`) | Eigenvalues (source → job) | Registration |
|---|---|---|---|---|
| `SP02.forward.json` | `SP02_Modal_V02.inp` `574ae78a…` | `CFRP_T300_PlainWeave` | 15 → 30 | `9bf736d3…` |
| `SP13.forward.json` | `SP13_mesh_local_v1_modal.inp` `9d410584…` | `CFRP_Face` | 30 → 30 | `a8970e52…` |

These values are the ones the accepted shared-carbon builder
(`src/services/shared_carbon_forward.py` at `121ba1d`) hard-coded.

## M6.4 screening jobs (D-066)

`forward_builder.prepare_screening_job(model, envelope, perturbation, source, output_directory)` renders
a transverse-constant screening job:
- the candidate is the envelope's reference point;
- exactly one of E3, ν13, ν23, G13 and G23 is set to one approved endpoint of
  `screening/M6_4_transverse_envelope.json`;
- the same post-check applies: only the material record and the eigenvalue line may change;
- the provenance schema is `auto-id/screening-forward-job/v1`, with a `screening` block.

A perturbation that is not one of the envelope's endpoint perturbations is refused. Screening
perturbations are not parameterisations and are never fitted.

## Active forward bindings (D-068)

| File | Passport | Fixture | Registration | Role |
|---|---|---|---|---|
| `SP02.physical.forward.json` | `SP02.physical.specimen.json` | `SP02/bravo-1-physical` | `9b63f6c8…` (physical) | active |
| `SP13.physical.forward.json` | `SP13.physical.specimen.json` | `SP13/best-physical` | `2eeeaa86…` (physical) | active |
| `SP02.forward.json` | `SP02.specimen.json` | `SP02/bravo-1` | `9bf736d3…` (legacy) | historical (M0–M5; unchanged) |
| `SP13.forward.json` | `SP13.specimen.json` | `SP13/best` | `a8970e52…` (legacy) | historical (M0–M5; unchanged) |

- An active manifest has the same forward model ID, model input, material, parameterisation, eigenvalue
  request and job prefix as its historical one. The governed solver profiles therefore apply unchanged.
- Both manifests render the same FE jobs, so the archived CARBON-4C packs stay reusable.
- Only the passport and the registration differ.
