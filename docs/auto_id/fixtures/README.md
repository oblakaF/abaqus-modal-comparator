# Real experiment fixture manifest

Roadmap step: M0.2. Schema: `experiment-fixture-manifest/1`.

[real_experiment_fixtures.json](real_experiment_fixtures.json) is the deterministic
identity record of the real experiments that Auto-ID regressions and runs may use.
It replaces knowledge that previously lived only in chats and scripts: which file,
which modal set, which registration, which FE model, which measurement contract,
and where the large files live.

The normative validator is `src/domain/experiment_fixture.py`
(`load_experiment_fixture_manifest`). Tests: `tests/test_experiment_fixture.py`.

**Large files are never committed.** UNV, INP and ODB files stay in external stores.
The manifest holds only their identities.

## Record fields

Every record is checked strictly. Unknown fields are rejected and all listed fields
are required.

| Field | Content |
|---|---|
| `fixture_id` | Unique key, `<specimen_id>/<modal set name>` |
| `specimen_id` | Design/specimen label used in accepted evidence (`SP02`, `SP13`) |
| `physical_specimen_id`, `experiment_id`, `test_run_id` | Provisional identifiers until M2.2. Each may be `null` **only** if it is declared in `unresolved` with a reason. |
| `experimental_source` | External file reference (see below) to the fitted-mode source |
| `modal_set` | `name` (reader key), `display_name`, `source_type`, `mode_count`, `measurement_point_count`, `measured_dofs` (subset of U1/U2/U3), `measured_face` |
| `registration` | Repo-relative `path` of the FrozenRegistration, `schema_version`, `registration_hash`, `fe_geometry_sha256` |
| `fe` | `model_name`, `geometry_identity` (`schema_version`, `sha256`, `node_count`), `model_input` and `odb_reference` (external file references) |
| `provenance` | `created` (ISO date) and `source_of_truth` (non-empty list) |
| `unresolved` | List of `{field, reason}` for identities that accepted evidence does not record |

**External file reference:**

```json
{
  "role": "...",
  "file_name": "...",
  "sha256": "<64 lowercase hex>",
  "size_bytes": 123,
  "location": {"store": "...", "relative_path": "..."}
}
```

The validator also requires that:

- `relative_path` is a relative POSIX path. Drive letters, a leading `/`, backslashes
  and `..` are rejected, so **no local absolute path is ever stored**.
- `relative_path` ends with `file_name`.
- `registration.fe_geometry_sha256` equals `fe.geometry_identity.sha256`.

**Missing values are never invented.** When accepted evidence does not record an
identifier, the record sets it to `null` and states why in `unresolved`.

## External retrieval contract

Each `location.store` names an external data root. Its machine-specific directory is
configured outside git with an environment variable:

| Store | Environment variable | Content |
|---|---|---|
| `snadwich` | `AUTO_ID_FIXTURE_ROOT_SNADWICH` | Canonical experimental data and source INPs (read-only) |
| `carbon-project-archive` | `AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE` | Research archive of accepted CARBON-* ODBs and results |

`resolve_external_file(reference, fixture_roots_from_environment())` returns
`<root>/<relative_path>` only after the file passes three checks:

1. The store is configured. Otherwise it raises `FixtureSourceUnavailableError`.
2. The file exists. Otherwise it raises `FixtureSourceUnavailableError`.
3. Its size and SHA-256 equal the record. Otherwise it raises
   `FixtureSourceMismatchError`.

It never falls back to another file, path or modal set. Real-data regressions
(M0.3) must skip, with an explicit reason, when a store is not configured. They must
fail when a configured file does not match its record.

## Current records

| Fixture | Source | Modal set | Modes / points | DOFs | Registration | FE geometry |
|---|---|---|---|---|---|---|
| `SP02/bravo-1` | `SP02_polymax_retry_260803.unv` | `bravo-1` (Bravo (1)) | 9 / 121 | U3 | `9bf736d3…c164` | `72e8597a…4e6d` |
| `SP13/best` | `SP13_a_polymax.unv` | `best` (Best) | 12 / 289 | U3 | `a8970e52…58a4` | `34d69d79…5826` |

The FE ODB references are the CARBON-4C baseline control ODBs (accepted CARBON-4C
evidence). ODB bytes are not deterministic across solves, so FE identity binds through
`fe.geometry_identity`. The ODB SHA-256 identifies that particular archived reference
result only.

## Regression check (M0.3)

`services.experiment_fixture_regression.verify_experiment_fixture(fixture, roots,
repo_root=...)` checks one manifest record against its real data. It raises on the
first difference and never repairs or substitutes anything.

1. **Experimental source:** it resolves through the store root, and its size and
   SHA-256 match.
2. **Registration:** it loads the FrozenRegistration from its repo path, and
   `from_dict` re-seals the content hash. The check then compares it with the
   record:
   - registration hash and schema;
   - bound source (SHA-256 and size);
   - modal set;
   - FE geometry identity (SHA-256, node count, schema).
3. **PolyMAX import:** it runs the production reader with the pinned modal set name.
   - The reader's mode source must equal the source type's registered value; for
     `polymax-curve-fitted-dataset-55` that is `curve-fitted dataset 55`. A
     peak-derived source therefore never passes.
   - The selected modal set key, mode count and point count must match the record.
4. **Measurement contract replay:**
   - the imported points must equal the registration's `experimental_node_ids`;
   - there must be one mapped FE node per point;
   - the frozen contract's DOF set must equal `measured_dofs`;
   - every mode's measured-DOF mask, computed by
     `reviewed_core.experimental_measurement_masks`, must equal the frozen contract.

`tests/test_experiment_fixture_regression.py` runs the check for **every** manifest
record. The fixture list is never duplicated in the tests. A record whose store is not
configured is skipped with the reason. The refusal paths are covered by a small
synthetic fixture, so they also run in CI.

To run the real-data regression locally:

```
set AUTO_ID_FIXTURE_ROOT_SNADWICH=<local root of the snadwich store>
python -m unittest tests.test_experiment_fixture_regression -v
```

## Production path (M1.2)

`services.production_modal_input.load_production_modal_input(fixture_id, roots=...)`
is the only way Auto-ID takes experimental modes. A record is selected by its
`fixture_id` in this manifest; there is no free file-path entry.

1. It runs the M0.3 `verify_experiment_fixture` checks on the production reader output.
2. It applies the M1.1 input-source policy to every mode, so a peak-derived or
   unclassifiable mode is refused even inside a fitted set.
3. It returns a `ProductionModalInput`:
   - the reader's dataset, unchanged (frequencies, damping, node order, shapes);
   - the hash-sealed `FrozenRegistration`;
   - the verification report;
   - the source classification;
   - a `provenance()` record (fixture, source SHA-256 and store path, modal set,
     mode source, counts, measured DOFs, registration and FE geometry hashes).

Tests: `tests/test_production_modal_input.py`. The real-data test iterates the
manifest. The refusal cases use the shared synthetic workspace in
`tests/fixture_support.py`, so they also run in CI.

## External PolyMAX provider (M1.3)

`services.external_polymax_provider.prepare_external_polymax_modal_dataset(fixture_id)`
runs the modal preparation chain for an accepted fixture. Steps:

1. It prepares the FRFs: the pinned export's dataset-58 FRFs are turned into an
   `FrfInput` by the existing multi-reference FRF builder.
2. It runs `ExternalPolyMAXProvider`. The provider loads the frozen PolyMAX selection
   through the M1.2 production path and keeps frequencies, shapes, point order and
   measured DOFs unchanged.
   - Damping is PolyMAX's own estimate, read from the stored dataset-55 pole.
   - The provenance includes `pole_selection = external_frozen_selection` (D-026).
3. It checks admission (`admitted_provider_registry()`) and validates the output
   against the M1.3.1 boundary rules.
4. It applies the M1.1 policy. The provider label
   `external PolyMAX modal preparation/1` is admitted as curve-fitted.

No FRF fitting, pole extraction or peak picking takes place (D-027). Tests:
`tests/test_external_polymax_provider.py`. The real-data test iterates the manifest.
