# M8-D2g — Finalise & Export Campaign Definition, Pre-run Validation

Status: `REVIEW_READY` (branch `feature/m8-d2g-campaign-finalisation`). This page covers the end of the preparation
chain:

**complete Campaign Draft v6 → re-verification → finalisation → saved SPEC v1.2 campaign definition → Pre-run
Validation.**

Nothing is run:

- no optimiser, no LM, no Abaqus, no FE;
- no material constant is released;
- production calibration stays `BLOCKED / NOT_AUTHORISED`; the original M8 gate stays `NOT_MET`.

## Finalise & Export Campaign Definition...

The button is on **0. Auto-ID Setup › Campaign draft › Finalise & Export / Pre-run Validation**.

### Before finalising

The draft is rebuilt from its own document by the existing `draft_from_document` (the reopening path) and must equal
the current draft. That path re-checks:

- the governed specimen identities;
- the bound governed records;
- the accepted FIT / HOLDOUT rows on their strict freeze and physical registration;
- the declared configuration with its repository checks (forward-model parameterisation, archive-reuse plan);
- that no required input is missing.

Then `CampaignDraft.finalise()` — the governed `parse_campaign_definition` — accepts the definition, or the reasons
are shown and nothing is saved. There is no second validator.

### Saving

- **Where:** Save As, chosen by the user, as a `.json` file outside the repository and every data store.
- **Content:** exactly the definition the parser accepted (no extra field), loadable by `load_campaign_definition`.
- **Atomic write:** the temporary file is loaded by `load_campaign_definition` and published only if its campaign hash
  equals the hash that was checked. The published file is then read again.
- **Data changed after the check:** if the data changed between the check and the save (for example while the Save As
  dialog is open), nothing is written.
- **Replacing a file:** only after an explicit confirmation, and only if the existing file is a campaign definition.
- **Cancel, write error, locked file:** nothing is changed, and no partial file is left.
- **Shown to the user:** the path, the campaign id, the campaign hash and the re-read hash.
- **Protocol:** `<name>.export-protocol.json` is a diagnostic record of the checks, labelled
  `NOT_GOVERNED_EVIDENCE` and `AUTHORISES_NOTHING`.

## Pre-run Validation...

Checks a saved definition in six separate sections, each with the status of the existing service:

| Section | How | Statuses |
|---|---|---|
| Definition | `load_campaign_definition` | `FORMALLY_VALID` / `HISTORICAL_V1_SCHEMA` / `INVALID` |
| Sources | the current governed records must reproduce the definition (same campaign hash); pinned files (modal source, FE input, reference ODB, FE geometry, forward-model INP) resolved with SHA-256 verified | `SHA256_VERIFIED` / `NOT_VERIFIED` (stores not configured) / `MISMATCH` |
| Observations | accepted rows and registrations; SPEC v1.2 §8 counts (counting only) | `COUNT_CONDITIONS_MET` / `COUNT_CONDITIONS_NOT_MET` |
| Numerical evidence | sensitivity, rank, leave-one-FIT-family-out, family consistency, Σ_meas | `NOT_ASSESSED`, `NOT_AVAILABLE`, `RECORDED_DIAGNOSTIC_ONLY` |
| Scientific readiness | the scientific backend judges journalled runs only; history shown unchanged | `NOT_EVALUATED` (no run) / `BLOCKED` (calibration) |
| Execution authorisation | a definition carries no authorisation; its decision and provenance text is never one | always `NOT_AUTHORISED` |

The overall result is always `NOT_AUTHORISED_FOR_EXECUTION`. Execution needs its own HUMAN gate.

## Results (real GUI, SP-02 / SP-13)

### Positive scenario

SP-02 + SP-13, `MATERIAL_IDENTIFICATION`, RUN_A:

- **Draft and export:** a complete draft is built through the forms, finalised and exported.
- **Re-read:** `load_campaign_definition` gives the same campaign hash.
- **Pre-run:** Definition `FORMALLY_VALID`, Sources `SHA256_VERIFIED` (10 pinned files), Observations
  `COUNT_CONDITIONS_MET` (pooled, k = 1), Numerical evidence `NOT_ASSESSED`, Scientific readiness `NOT_EVALUATED`,
  Execution authorisation `NOT_AUTHORISED`.

### Negative scenarios

| Scenario | Result |
|---|---|
| SP-13 alone | not finalised: budget and archive plan missing (the only governed plan names SP-02 too); §8 insufficient FIT families |
| SP-02 alone | not finalised: no compatible archive-reuse plan |
| RUN_B | not finalised: `run_b_gate` is never set by a draft |
| Registration evidence changed | not finalised |
| Definition with a registration swapped, or a HOLDOUT row promoted | Pre-run Sources `MISMATCH` |
| A source file with another SHA-256 (an altered copy) | Pre-run Sources `MISMATCH` |
| Corrupted definition | Pre-run Definition `INVALID` |
| Freeze changed while the Save As dialog is open | nothing written |
| Cancel, a file held open, a destination in the repository | nothing written |
| A decision / provenance text claiming acceptance or authorisation | Execution `NOT_AUTHORISED`, Scientific readiness `NOT_EVALUATED` |

### Fix to M8-D2f found here

An archive plan that cannot be checked yet, because no parameterisation is declared, is now a pending input rather
than a mismatch. As a result, a saved draft whose material parameters were cleared reopens. Declaring the budget
before the material parameters is still refused.
