# M8-D2i — Guarded Auto-ID Execution

Status: `REVIEW_READY` (branch `feature/m8-d2i-guarded-execution`).

M8-D2i joins the whole chain:

**campaign definition → Execution Plan (M8-D2h) → guarded controller → existing executor → journals → progress →
existing scientific backend → result.**

The production executor stays **blocked**: this installation has no trusted HUMAN authorisation source. Nothing has
been run on real specimens:

- no Abaqus solve, no ODB extraction and no LM on SP-02 / SP-13;
- no material constant released;
- production calibration `BLOCKED / NOT_AUTHORISED`;
- the original M8 gate `NOT_MET`;
- the historical `NO_GLOBAL_PARAMETER_VALUE` (D-077) unchanged.

## Architecture

| Part | Where | What it does |
|---|---|---|
| Planning sequence | `identification_campaign_run.prepare_campaign_plan` (M8-D2h) | run-type / question gate, archive-reuse plan, `prepare_campaign_specimens`, `prepare_run_manifest` |
| Execution context | `guarded_execution.open_execution_context` | opens a plan folder and re-checks it (below); writes nothing |
| Controller | `guarded_execution.GuardedExecutionController` | authorisation check, re-check, the existing executor, stop, worker thread, attempt log |
| Executor | `extract_archived_odbs`, `journalled_archive_records`, `reused_pack_records`, `CampaignRun.run` (`run_bounded_lm`) | unchanged; no second optimiser or pipeline |
| Progress | `run_progress.inspect_run_progress` | verified journal counts and budgets |
| Scientific verdict | `stored_run_evidence.evaluate_stored_run` → `campaign_scientific_backend.judge_campaign_run` | unchanged rules |
| GUI | Auto-ID Setup › *Guarded Auto-ID Execution* | the controller; the Stored Run view is reused for the journal |
| CLI | `tools/auto_id_execute.py status / extract-archive / run` | the same controller |

### Opening a plan

`open_execution_context` accepts a plan folder only when:

- it is one complete, consistent plan (`plan_set_problems`), apart from the run entries the executor adds
  (`archive_reuse/`, `campaign/`, `specimens/`, `guarded_execution.json`);
- the definition file is byte for byte the planned one;
- Pre-run Validation passes again (Definition `FORMALLY_VALID`, Sources `SHA256_VERIFIED`);
- the existing planning sequence, run into a temporary folder, gives the recorded manifest hash and authorisation scope
  again.

Otherwise the plan is refused as **STALE**, with the reason.

### The plan folder is the run root

The plan folder becomes the run root, in the executor's own layout:

| Path | Content |
|---|---|
| `archive_reuse/` | archive extraction journal and packs |
| `campaign/<run hash>/journal.json` | the campaign journal |
| `specimens/…/journal.json` | the governed pipeline journals |

## Authorisation contract

`ExecutionAuthorisation` (`auto-id/execution-authorisation/v1`) binds:

- the operation;
- the plan's authorisation scope hash, campaign hash and manifest hash;
- exactly that operation's budget:
  - `ARCHIVE_EXTRACTION`: the archive-extraction jobs, 0 solves, 0 LM evaluations;
  - `CAMPAIGN_RUN`: the hard solve budget, the Abaqus Python extraction cap, the LM evaluation budget and the
    initial-point solves.

An operation runs only when all of the following hold, in this order:

1. **Authority available:** a trusted authority is available. The production `NoTrustedAuthority` never is, so the
   reason is `NO_TRUSTED_AUTHORISATION_SOURCE`.
2. **Right type:** the value is an `ExecutionAuthorisation`. Plain JSON, GUI text, a typed hash, decision or provenance
   text, or an M7 authorisation never is one.
3. **Binding:** every bound field equals the plan's, including the operation and its budget.
4. **Attestation:** the authority attests the record.
5. **Re-check:** immediately before execution the plan is re-checked as current, and the binding is checked again
   against the fresh context.

The two operations are authorised independently. An extraction authorisation never authorises solves or LM, even if
it is relabelled or carries the other budget. Nothing in `src` or `tools` can attest: no trusted record is fabricated.

Tests use `tests/m8_d2i_support.SimulatedAuthority`, which signs with a per-instance random HMAC key. The production
GUI has no way to reach it.

## Running, stopping, resuming

- **Background:** an operation runs in a worker thread and the GUI polls the controller, so the main window stays
  responsive.
- **Stop After Current Step:** the next Abaqus solve or extraction is not started. A running process is not killed;
  this is the existing backend's granularity.
- **Interruption or executor error:** the operation ends `STOPPED` or `FAILED`. The hash-chained journals keep what was
  written, and the run lock is released.
- **Resume:** a later authorised run replays journalled evaluations and never repeats a journalled solve.
- **Budgets:** the hard solve budget (`SOLVE_BUDGET`) and the LM evaluation budget are the executor's own; nothing
  extends them.
- **Attempt log:** every attempt is logged in `guarded_execution.json`, labelled `NOT_GOVERNED_EVIDENCE`. The log holds
  the binding, never the attestation.

### Simulated runs

A run attested by a simulated authority is labelled `SIMULATED_TEST_EXECUTION_NEVER_A_MATERIAL_RESULT`:

- on the outcome;
- in the attempt log;
- by `execution_provenance`, which Evaluate Stored Run shows next to the backend result.

The backend's record itself is unchanged. Nothing is written to the repository or to governed evidence.

## GUI (Auto-ID Setup › Guarded Auto-ID Execution)

| Button | What it does |
|---|---|
| Open Execution Plan... | opens a plan folder and re-checks it in the background |
| Re-check Sources | repeats the re-check |
| Start Archive Extraction / Start Identification Run | disabled without a trusted authority; refused with the reason if called |
| Stop After Current Step | requests a stop before the next solve or extraction |
| Refresh Execution Status | controller state and verified journal progress |
| Show Run Journal in Stored Run View | opens the plan's campaign and run journal in the existing M8.3 / M8.4 view (progress, Evaluate Stored Run) |

## Results

### Synthetic end-to-end (fake executors)

- **Campaign:** a two-specimen SPEC v1.2 campaign that mirrors the real plan. Four initial points come from archived
  packs and two from archived ODBs.
- **Tests:** `tests/test_m8_d2i_guarded_execution.py`.

| Check | Result |
|---|---|
| 1. Authorised extraction of the 2 archived ODBs | 2 extractions, 0 solves; resumable; originals unchanged |
| 2. Extraction authorisation used for the run | refused (operation / budget binding) |
| 3. Full RUN_A through `CampaignRun` | `CONVERGED`, E_in = 48 004 MPa for a synthetic truth of 48 000 MPa (2 new solves) |
| 4. Journal structure | campaign and pipeline journals hash-chain verified; run directory = run hash; manifest / campaign identity |
| 5. Scientific backend | the completed journal is judged by `evaluate_stored_run` (record bound to the run hash) |
| 6. Budgets | hard solve budget 1 → `SOLVE_BUDGET` after 1 solve; LM budget 4 respected |
| 7. Branch tracking | an exchanged FE mode in specimen B → `REFUSED` journalled |
| 8. Executor error, interruption | `FAILED`, journals verified, lock released, plan reopens |
| 9. Resume | completes; journalled steps kept |
| 10. Change after authorisation | definition, archive plan (manifest), plan manifest or a source → refused, nothing executed |
| 11. Repeated run | no solve repeated (both sessions together solve each job once); a completed run replays with 0 solves |
| 12. Separation | simulated outcomes and logs labelled; repository `docs/` unchanged by every test |

### Real SP-02 + SP-13 plan (store-gated)

The real plan opens as current, with the same manifest and scope, and opening writes nothing. The production controller
refuses both operations (`NO_TRUSTED_AUTHORISATION_SOURCE`); no executor is reached.

### Real Windows GUI (34/34 checks, 8 screenshots, no process started)

- **A. Production, real SP-02 + SP-13.**
  - The draft is built in the GUI, exported and planned (M8-D2h): campaign `73edd796…`, manifest `f6478802…`, scope
    `0abf913f…`.
  - *Open Execution Plan...* re-checks it in the background and opens it as current. Both gates and the budgets are
    shown.
  - The status is `NOT_AUTHORISED — NO_TRUSTED_AUTHORISATION_SOURCE`, and both Start buttons stay disabled. Calling
    them is refused.
  - No executor, extraction, journal or LM is reached, and the plan folder is unchanged.
  - After the definition is changed, *Re-check Sources* gives `STALE`.
- **B. Simulated, synthetic campaign.** The test authority is injected by the driver only.
  - The extraction of the 2 archived ODBs completes.
  - The run executes in a worker thread: the window stays responsive and shows `RUNNING`.
  - *Stop After Current Step* ends it `STOPPED` with the journals verified.
  - A second start resumes it to `CONVERGED` without repeating a solve (2 solves in total).
  - The outcome is labelled `SIMULATED_TEST_EXECUTION_NEVER_A_MATERIAL_RESULT`; the verified progress is shown, and the
    journal opens in the Stored Run view.

Tests: `tests/test_m8_d2i_guarded_execution.py` 24 tests, one of them store-gated; full suite 2465 OK (6 skipped).

## What a real Abaqus run needs

1. **A trusted HUMAN authorisation source** decided by the SUPERVISOR: a governed record type with an attestation that
   the software can verify, for example a signature with a key held outside the agent's reach. It would be implemented
   as a new `AuthorisationAuthority` and must never be fabricated.
2. **Two separate authorisations** of the exact plan scope:
   - `ARCHIVE_EXTRACTION`: 2 SP-02 ODBs, Abaqus Python;
   - `CAMPAIGN_RUN`: up to 16 Abaqus solves, 11 LM evaluations.
3. **The machine:** an Abaqus licence and command (`abq2024.bat`), and a run folder outside the repository and the data
   stores.
4. **After the run:** the scientific verdict comes from the existing backend; a result enters governed evidence only by
   SUPERVISOR decision.
