# APP-WORKSPACE.1 — headless workspace context (2026-10-28)

Branch `feature/app-workspace1-context` from `main` `4cd51a9`. **Status: REVIEW_READY.**

`src/services/workspace_context.py` is an immutable model of the workspace state of one specimen, for a future GUI.

- **No Tkinter.** It imports none, directly or indirectly; a test checks this in a fresh process.
- **No GUI wiring.** It is not connected to any GUI yet; no existing GUI module was changed.
- **No scientific change.** It computes no scientific quantity and changes no algorithm, gate, SPEC or frozen
  evidence.

## Contract

```python
build_workspace_context(specimen_id, *, fe_path=None, experimental_path=None, modal_set=None,
                        registration_basis=None, registration_hash=None, result=None,
                        catalogue_view=None) -> WorkspaceContext
```

All dataclasses are `frozen=True`, and every collection is a tuple.

| Part | Source | Representation |
|---|---|---|
| Specimen ID, type, family, catalogue Auto-ID statuses | **only** the accepted catalogue `docs/auto_id/specimen_catalog.json` (`status` = `ACCEPTED`), read through `services.specimen_catalog_view.load_catalogue` | `SpecimenRecord`: the statuses are kept verbatim and in order. A missing value is `UNKNOWN`. A non-list status is `()`. |
| Unknown specimen | ID not in the catalogue (exact match; `SP02` is not `SP-02`), empty ID, or no accepted catalogue | `specimen = None`; ID, type and family read `UNKNOWN`; `catalogue_problem` says why the catalogue was unusable |
| FE / experimental source | the session's paths | `SourceSelection(role, path, catalogue_name_match)`. The path is recorded, never opened, hashed or changed. `catalogue_name_match` compares the file name with the specimen's catalogue file names only; it is not content identity. |
| Modal set | the session's name, checked against the catalogue's PolyMAX sets of this specimen | `ModalSetStatus`: `NOT_SELECTED`, `GOVERNED` / `OTHER` / `NOT_GOVERNED` / `UNASSIGNED` (the existing `specimen_catalog_view.modal_set_status`), `NOT_IN_CATALOGUE`, `NOT_CHECKED`, `UNKNOWN`. Names match exactly; similar names are never merged. |
| Registration | the session's basis (`domain.specimen_manifest.RegistrationBasisStatus`) and hash, compared with the catalogue's `physical` / `legacy` records | `RegistrationKind`: `PHYSICAL`, `LEGACY_REPLAY`, `INCOMPLETE`, `NONE`, `UNKNOWN`. A contradiction or an unrecorded hash becomes an `issues` entry; a kind is never upgraded. `physical_confirmed_by_catalogue` is true only for a `PHYSICAL` basis whose hash is the catalogue's physical registration, with no issue. |
| Result | the session's state (`ui_policy.AnalysisState`) | `ResultState(state, pair_count, mac_shown)`. Only `SUCCESS` may carry pairs or MAC; anything else raises `WorkspaceContextError`. An unknown pair count stays `None`. |
| Production Auto-ID | the authoritative blocking code: `services.guarded_execution.PRODUCTION_AUTHORITY` and `services.campaign_execution_plan.NOT_AUTHORISED` / `STATEMENT` | `WorkspaceContext.production_auto_id` is a **property** read on every access. It is not a stored field, so it cannot be set or replaced. Today it is `NOT_AUTHORISED`, blocked, with reason `NO_TRUSTED_AUTHORISATION_SOURCE…`. Even with an available authority, the context authorises nothing. |
| Missing items | derived | `missing`: in a fixed order, `specimen`, `FE source`, `experimental source`, `modal set`, `registration`. |

**Catalogue registration mapping.**
- The catalogue's `physical` record maps to `PHYSICAL`, and its `legacy` record (historical frozen registration) to
  `LEGACY_REPLAY`.
- The catalogue's status words (e.g. "ACCEPTED (… D-065) …", "historical provenance only …") are kept as
  `status_text`, not interpreted.

## Tests (`tests/test_app_workspace1_context.py`, 23)

- **Accepted catalogue:**
  - ID, type, family and Auto-ID statuses equal the catalogue for all 14 records;
  - reading leaves the catalogue byte-unchanged;
  - an unaccepted or unreadable catalogue gives no specimen;
  - missing catalogue values stay `UNKNOWN`.
- **Unknown specimen:** `SP-99`, `SP02`, `sp-02`, empty and `None` give no specimen. A modal set is not checked, and
  a known hash is not attributed (kind `UNKNOWN`).
- **Incomplete sources:** the missing list for each combination; file-name matching only; no source file is opened.
- **Modal set:** governed and other sets. A wrong set (`Bravo (2)`, `bravo (1)`, `Bravo(1)`, a set of another
  specimen) is `NOT_IN_CATALOGUE`. A listed set in a non-catalogue file is `NOT_CHECKED`.
- **Registration:**
  - none;
  - physical confirmed (SP-02, SP-13);
  - `LEGACY_REPLAY` kept apart: by basis and by hash, never upgraded, contradiction reported both ways;
  - `INCOMPLETE`;
  - unrecorded and unknown hashes;
  - a malformed input is refused.
- **Result:** only `SUCCESS` carries pairs or MAC, for every other `AnalysisState`; invalid pair counts are refused.
- **Scientific block:**
  - production Auto-ID is `NOT_AUTHORISED` and blocked for every specimen and for the best-case state (physical
    registration, governed set, 6 pairs with MAC);
  - it is not a field and cannot be replaced;
  - an authority reporting "available" still gives `NOT_AUTHORISED`;
  - catalogue statuses stay verbatim.
- **Headless:** no `tkinter` / `_tkinter` in a fresh process after building a context; the dataclasses are frozen.

## Limits

- **File-name matching.** Source matching is by file name only, never content identity. A renamed copy is
  `NOT_CHECKED` for the modal set, and an unrelated file with a catalogue name matches by name.
- **No checks of artefacts.** The context reads only the catalogue. It does not read passports, frozen registrations
  or forward models, and it does not verify hashes of files.
- **Session state as given.** The result state is what the caller reports; the context does not inspect an analysis.
- **Interim vocabulary.** It uses existing enums: `AnalysisState` and `RegistrationBasisStatus`. `WorkspaceContext`
  is an interim contract for the GUI. Wiring it into the program is a separate task.
