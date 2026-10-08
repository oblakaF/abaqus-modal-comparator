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
