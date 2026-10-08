# Identification campaigns (M7, D-069)

| File | Schema | Content |
|---|---|---|
| `M7_RUN_A.campaign.json` | `auto-id/identification-campaign/v1` | The RUN_A definition: specimens and exact rows, fitted and fixed parameters, Σ, bounds, engineering window, LM, budget |
| `M7_RUN_A.archive-reuse.json` | `auto-id/campaign-archive-reuse/v1` | The archived FE results reused for RUN_A's initial points, pinned by content |

**Run types:**
- `RUN_A` is executable only through the HUMAN gate.
- `RUN_B` (`EFFECTIVE_MODEL_COMPENSATION_TEST`) is refused for execution unless its own later SUPERVISOR
  gate exists.

**Σ:** Σ_setup has its status. Σ_meas is `NOT_AVAILABLE`: it has no numeric value and enters run identities
as null, never as zero.

**Bounds:** `bounds` are numerical solver bounds only. `engineering_plausibility` is reporting context: a
value outside it is reported, never rejected and never a prior.

**Workflow** (`tools/m7_campaign.py`):

| Step | Abaqus | Command |
|---|---|---|
| Plan | no | `plan --run-root <dir>` |
| Archive extraction | Abaqus Python, **HUMAN gate** | `extract-archive --run-root <dir> --abaqus <cmd> --authorised-manifest-hash <h>` |
| Run | Abaqus, **HUMAN gate** | `run --run-root <dir> --abaqus <cmd> --authorised-manifest-hash <h>` |
| Report | no | `report --run-root <dir> --result <file>` |

- **Plan:** freezes every specimen on its active physical chain (the exact accepted rows, or STOP),
  renders the LM's initial points and verifies every archived reuse.
- **Archive extraction:** extraction-only reuse of the archived ODBs.
- **Run:** the bounded M4.8 LM on the shared E_in, with the hard solve budget; resumable.
- **Report:** the engineering estimate and the formal M5 verdict, kept separate, with
  "not externally validated".

The proposed RUN_A manifest hash is `e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6`. Run-store data (INPs, ODBs, packs, journals) is never
committed.

## RUN_B (D-072)

- **Files:** `M7_RUN_B.campaign.json` and `M7_RUN_B.archive-reuse.json`.
- **Purpose:** the diagnostic `EFFECTIVE_MODEL_COMPENSATION_TEST`: E_in + G12 from the governed start, with
  the same observations, holdouts and Σ as RUN_A.
- **Tool:** `--campaign run-b` on every command.
- **Reports:**
  - the label `EFFECTIVE_MODEL_COMPENSATION_TEST`;
  - G12 as `COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY`;
  - Δ ln E_in and Δ ln G12 against RUN_A, with the D-045 bands used descriptively only.
- **`pack_store`:** a reused pack may name the store that holds its file (for example `m7-run-a-archive`, the
  RUN_A extraction store). The file size, SHA-256 and content hash pins are unchanged.
- **Proposed manifest:** `5fd0946a0c3f4e20562ba97068cdb5b94bf6d10ba789a3b2df20b457882034a1` (not executed).


### RUN_B gate 1 (D-073)

- `M7_RUN_B.archive-extraction.json` records the 2 SP-02 G12± archive extractions (0 solves) and the final
  RUN_B run identity `fb5234116c6e9413e4b070e901f97b8c6e210d535daefe15f0cdb5b9f8ad87f0`.
- The store-gated re-verification uses `AUTO_ID_FIXTURE_ROOT_M7_RUN_B` (the RUN_B run root).
