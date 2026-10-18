# M8-D2f — complete campaign configuration

Status: `REVIEW_READY` (branch `feature/m8-d2f-complete-configuration`). This page describes how the user declares the
remaining required fields of a campaign definition in the GUI.

- **Not run:** Abaqus, FE, LM.
- **Unchanged:** SPEC, DECISIONS, EVIDENCE, frozen observations, registrations and scientific criteria.
- **Gates:** production calibration `BLOCKED / NOT_AUTHORISED`; the original M8 gate `NOT_MET`.

## User path

**Identification › 0. Auto-ID Setup › Campaign draft › Campaign configuration.** Each group is declared in its own
form:

- the form starts empty, or shows the current declaration;
- **Apply** validates every value and leaves the form open on a refusal;
- **Cancel** changes nothing.

| Group | Fields (parser keys) | Copy from the M7 RUN_A reference |
|---|---|---|
| Material parameters | `parameterisation`, `fitted_parameters`, `fixed_parameters`, `start`, `bounds`, `engineering_plausibility` | allowed, explicit |
| Uncertainty and acceptance | `sigma` (Σ_setup sd / status / source; Σ_meas source — status `NOT_AVAILABLE`, the only supported one), `practical_target` | allowed, explicit |
| Numerical algorithm (LM) | `lm` (8 settings) | allowed, explicit |
| Budget and archive reuse | `abaqus_solve_budget`, `archive_reuse` | allowed, explicit |
| Decision and provenance | `decision`, `provenance` | **never**: the archived decision authorised the archived campaign only |
| run_b_gate | none (RUN_A only) | — |

### Entry rules

- Nothing has a default. An empty field is refused; write `none` for "no fixed parameter" or "no plausibility window".
- Counts must be whole numbers.

### Validation

Each group is validated by the campaign-definition parser's own field validators
(`domain.campaign_definition.declared_*`). `parse_campaign_definition` itself now calls them, so there is one rule,
with unchanged behaviour, messages and campaign hashes. The validators check:

- the run type: RUN_A fits `E_in_plane_mpa` only, RUN_B fits `E_in_plane_mpa` and `G12_mpa`;
- that the start lies within the bounds and that preferred ≤ acceptable < 1;
- that Σ_meas is `NOT_AVAILABLE` (D-069).

The repository checks cover what the parser cannot see:

- the parameterisation equals that of every selected forward model;
- the archive-reuse plan exists, loads with that parameterisation and names only the selected specimens.

### Run type and run_b_gate

- A run-type change that would invalidate a declaration is refused.
- `run_b_gate` is declared as none for RUN_A only. For RUN_B it stays a SUPERVISOR gate that a draft never sets.

### The archived M7 RUN_A reference

**Show archived M7 RUN_A settings** lists the reference with its campaign hash, marked `REFERENCE_ONLY`.

- **Copying:** a copy fills the form but is not applied; every value is validated when you press Apply. The source
  records "copied by an explicit user choice from … ; no M7 result carried over", or "edited after an explicit copy".
- **Results:** M7 results are never read.
- **Identity:** a v1.2 definition built this way has a new campaign identity.

## Persistence

- Drafts are saved as `auto-id/campaign-draft/v6` (`declared.configuration`, `declared.configuration_sources`).
- On reopening, every group is re-validated and the repository checks are repeated. The following are refused:
  - a value outside the rules;
  - a RUN_B gate value;
  - an incomplete group, or a group without a source;
  - a missing archive plan.
- Drafts v1 – v5 open with no configuration; a v5 file saved by the PR #88 GUI opens unchanged.
- This step also fixes the reopening of v5 drafts' bound records under the new schema.

## Results on the existing data

| Case | Completeness | Parser | Review |
|---|---|---|---|
| SP-02 + SP-13, MATERIAL_IDENTIFICATION, RUN_A (settings copied explicitly, decision / provenance typed) | 0 missing | **accepted**: new v1.2 identity, campaign hash ≠ M7 | `DEFINITION_COMPLETE_FOR_FURTHER_REVIEW`; execution `NOT_AUTHORISED`; rank, leave-one-FIT-family-out and family consistency `NOT_ASSESSED`; Σ_meas `NOT_AVAILABLE` |
| SP-13 alone, SPECIMEN_ENGINEERING_CALIBRATION | `abaqus_solve_budget`, `archive_reuse` missing: the only governed plan (M7) names SP-02 too | not accepted | `INCOMPLETE`: §8 `INSUFFICIENT_FIT_FAMILIES`; calibration `BLOCKED` |
| SP-02 alone, SPECIMEN_ENGINEERING_CALIBRATION | the same budget / archive gap | not accepted | `INCOMPLETE` (§8 count met) |
| RUN_B | `run_b_gate` stays missing (SUPERVISOR gate) | not accepted | `INCOMPLETE` |

A complete definition proves neither identifiability nor permission to execute. Execution needs its own HUMAN gate.
