# M8-D2h — Auto-ID Execution Plan (execution NOT_AUTHORISED)

Status: `REVIEW_READY` (branch `feature/m8-d2h-execution-planning`). This page connects a SPEC v1.2 campaign definition
saved by M8-D2g to the existing Auto-ID executor, as a plan only:

**saved campaign definition → Pre-run Validation → existing planning sequence → run manifest and manifest hash →
Execution status `NOT_AUTHORISED`.**

Nothing is run:

- no Abaqus, no Abaqus Python, no FE, no LM;
- no material constant is released;
- production calibration stays `BLOCKED / NOT_AUTHORISED`; the original M8 gate stays `NOT_MET`;
- numerical identifiability of the new campaign stays `NOT_ASSESSED` until a real journalled result exists.

A successful plan is not scientific readiness and not a right to run.

## One planning sequence for the CLI and the GUI

`identification_campaign_run.prepare_campaign_plan` is the planning sequence of the existing executor. The M7 CLI
(`tools/m7_campaign.py`) now calls it as well; its behaviour and hashes are unchanged. It runs:

1. the run-type / question gate (`CampaignDefinition.require_executable`, inside the executor module only);
2. the definition's governed archive-reuse plan (`load_archive_reuse`);
3. `prepare_campaign_specimens`: each specimen is frozen on its active chain; the rows must be exactly the accepted
   rows, otherwise STOP;
4. `prepare_run_manifest`: the initial points, the archived reuse verified against its pins, the budgets and the
   manifest hash.

The campaign, run and manifest hashes and the journal layout are unchanged.

`services/campaign_execution_plan.prepare_execution_plan` puts the M8-D2g checks in front of that sequence. Two entry
points use it:

- the GUI action **Prepare Auto-ID Execution Plan...**;
- the CLI `tools/auto_id_execution_plan.py --definition <file> --work-dir <folder>`, which has no execute command.

It never substitutes the archived M7 campaign for the selected definition.

## Prepare Auto-ID Execution Plan...

The section is on **0. Auto-ID Setup**, below *Finalise & Export / Pre-run Validation*.

1. **Choose:** a saved campaign definition file, then a working directory (the future run root).
2. **Re-check:** the M8-D2g Pre-run Validation runs again. It must give Definition `FORMALLY_VALID` (SPEC v1.2 only) and
   Sources `SHA256_VERIFIED`: the current governed records reproduce the definition, and every pinned file is verified
   now. Otherwise nothing is planned.
3. **Load:** the definition is loaded with `load_campaign_definition`; its campaign hash must equal the one Pre-run
   validated.
4. **Plan:** `prepare_campaign_plan`, as described above.
5. **Cross-check:** the prepared FIT / HOLDOUT rows must equal the definition's rows (which Pre-run proved equal to the
   accepted strict freezes), and the budgets must be consistent.
6. **Write:** the plan is written only if the definition file did not change while the plan was prepared.

### The working directory

- **Allowed:** an existing folder, outside (and not above) the repository and every data store. It must be empty, or
  hold exactly one complete, consistent earlier plan of the same campaign:
  - exactly `plan_jobs/`, `run_manifest.json` and `execution_plan.json`;
  - the record's schema, labels, status, campaign hash, manifest hash and authorisation scope agree with each other and
    with the manifest;
  - `plan_jobs/` holds exactly the manifest's initial-point jobs, each with its generated INP SHA-256.
- **Refused, left untouched:** a folder with other files (for example the `external_models` copies), a forged plan
  record, an altered manifest, scope or job, or a damaged plan. Nothing is written into it and nothing is removed.

### Files written

| File | Content |
|---|---|
| `run_manifest.json` | the manifest exactly as `prepare_run_manifest` gives it (the CLI's format) |
| `plan_jobs/` | the rendered initial-point INPs |
| `execution_plan.json` | the plan record, labelled `NOT_GOVERNED_EVIDENCE` / `AUTHORISES_NOTHING` |

All derived files go only into the working directory. Publication is all or nothing:

1. **Staging:** the complete plan is written into a private staging folder inside the working directory and must pass
   the same consistency check.
2. **Identical plan:** if an earlier identical plan is already in place, nothing is written.
3. **Replacement:** otherwise each earlier entry is moved aside into the staging folder before its replacement is moved
   in.
4. **Write error:** the new entries are moved back out and the earlier ones restored. A new plan leaves the folder empty;
   an earlier plan stays byte for byte.
5. **Incomplete restore:** if a restore itself fails, the earlier files are kept in the staging folder, never deleted,
   and the error says where they are.

A refusal publishes nothing and leaves no partial files.
Original INP, CAE, ODB and UNV files and accepted journals are never opened for writing.

### What is shown

| Section | Content |
|---|---|
| Campaign | the definition file, campaign id, schema, question, run type, file SHA-256 and campaign hash |
| Pre-run Validation | the six D2g sections, as checked now |
| Manifest | the manifest hash, the manifest file and the archive-reuse plan with its reuse hash |
| Observations | FIT / HOLDOUT per specimen, with the observation and registration hashes |
| Initial state | per specimen and point: the job and where its FE state comes from (see below) |
| Budget | the LM evaluation budget (reused / new), the hard Abaqus solve budget, the Abaqus Python extractions |
| Operations | the reused packs, the archive extractions, the new solves and the LM, each with its HUMAN gate |
| Execution | the gates, the authorisation scope hash and the Execution status |

An initial state comes from one of three sources:

- `ARCHIVED_SHAPE_PACK_READY`: a validated governed shape pack;
- `ARCHIVED_ODB_NEEDS_EXTRACTION`: an archived ODB, verified now, that needs a gated extraction;
- `NEW_ABAQUS_SOLVE`: a new Abaqus solve.

## Execution status: NOT_AUTHORISED

**Start Execution (not authorised)** calls the execution entry point `request_execution`. In M8-D2h no authorisation
exists, so every request is refused there, before any executor, archive extraction, run journal or LM.

None of the following is an authorisation:

- a typed manifest, campaign or scope hash;
- a decision or provenance text;
- a matching archived (M7) hash.

The status line shows whether the plan is still current. A changed definition, manifest or plan record makes it
**STALE**.

A later authorisation must bind exactly the plan's **authorisation scope** (`auto-id/execution-authorisation-scope/v1`):

- campaign id and hash;
- definition file SHA-256;
- question and run type;
- manifest hash and archive-reuse hash;
- the archive-extraction jobs;
- the initial-point solves;
- the hard solve budget, the Abaqus Python extractions and the LM evaluation budget;
- the gates.

An M7 authorisation (for example manifest `e4ba607f…`) never carries over to a new campaign.

*Evaluate Stored Run* and the run progress view are unchanged.

## Results (real GUI, SP-02 + SP-13)

### Main scenario

SP-02 + SP-13, `MATERIAL_IDENTIFICATION`, RUN_A (campaign `M8/D2h/SP02+SP13`):

- **Build and export:** the draft is built through the GUI, finalised and exported.
- **Pre-run:** `FORMALLY_VALID`, `SHA256_VERIFIED`, `COUNT_CONDITIONS_MET`, `NOT_ASSESSED`, `NOT_EVALUATED`,
  `NOT_AUTHORISED`.
- **Plan:** prepared; see the table below.

| Item | Value |
|---|---|
| Campaign hash | `300726a3a27ef30d28546987adc0cc9c532772c2082bf3b8a0bffaf14d48486f` |
| Manifest hash | `91df8d01027f7332e6a1e336cdc91e49b94c69d0d01a9a07c482e008364b2364` (reproducible: a second plan gives the same manifest, scope and jobs) |
| Authorisation scope | `0d048be94ab6c6d90bbdc89e99cab7f840534181f175950be98ff53dab0a69e6` |
| FIT / HOLDOUT | SP-02 R1, R2 / R3; SP-13 R1 / R2: 3 FIT + 2 HOLDOUT, equal to the accepted strict freezes |
| Ready archived shape packs | 4 of 6 initial points: SP-02 p0; SP-13 p0, E+, E− |
| Archived ODBs needing extraction | 2: SP-02 E+ `SP02_13363f977809dbff`, SP-02 E− `SP02_84753f636064e192` (gate `ARCHIVE_EXTRACTION`) |
| New solves for the initial points | 0 |
| LM evaluation budget | 11 campaign evaluations (3 initial ones reused, at most 8 new) |
| Hard Abaqus solve budget | 16 (8 evaluations × 2 specimens; gate `CAMPAIGN_RUN`) |
| Abaqus Python extractions | at most 18 (2 archived + one per new solve) |
| Execution status | `NOT_AUTHORISED` |

Real Windows GUI driver: 50/50 checks PASS (after the PR #91 correction, including a forged plan record, an altered earlier manifest and an unchanged byte-for-byte re-plan), 11 screenshots, no process start, no executor reached.

### Refusals

| Scenario | Result |
|---|---|
| Start Execution; a typed manifest / scope / M7 hash, a decision or provenance text | refused, nothing executed, no file written |
| The campaign changed after the plan | the plan is STALE and Start is refused; the changed campaign is never planned into the earlier plan's folder |
| A non-empty folder (user files, `external_models`), the repository, a data store | the working directory is refused |
| The archived M7 RUN_A campaign (v1) | refused (`HISTORICAL_V1_SCHEMA`) |
| A source file with another SHA-256 (an altered copy) | refused: Sources `MISMATCH` |
| An archived ODB with another SHA-256 | refused: differs from its pin |
| The archive data store missing | refused: Sources `NOT_VERIFIED` |
| RUN_B without its own gate | no plan (Pre-run; the backend run-type gate if it is reached) |
| `SPECIMEN_ENGINEERING_CALIBRATION` | no plan (Pre-run; `BLOCKED` by the backend gate if it is reached) |
| A wrong archive-reuse plan (an initial point not covered) | refused: the initial points would need new solves |

In every refusal nothing is written into the working directory. No executor, extraction, journal, LM or process is
reached, and the archived ODBs, the accepted M7 journals and the `external_models` copies are unchanged.

## What a later authorised stage needs

- **A governed authorisation record** that names the scope hash (campaign hash, definition file, manifest hash,
  operations and budgets) and is checked by `request_execution`. A text or a hash typed in the GUI is never one.
- **Gate 1, Abaqus Python:** the two SP-02 archive extractions (`extract_archived_odbs` with this manifest hash).
- **Gate 2, Abaqus:** the bounded LM campaign (`CampaignRun`) within the hard budget of 16 solves and 11 evaluations.
- **The scientific result** is judged afterwards by the existing backend from the journals; until then numerical
  identifiability stays `NOT_ASSESSED`.
