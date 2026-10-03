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
