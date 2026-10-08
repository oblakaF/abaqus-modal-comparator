# M7 decision record

**Status:** M7 `IN_PROGRESS`. M7.1 (RUN_A campaign architecture) is `REVIEW_READY`. Nothing has been
executed. DECISIONS D-069.

**Branch:** `auto-id/m7`, from `main` `9f5f63a`.

**Scope of M7:** the multi-specimen carbon campaign (SPEC §13; ROADMAP M7).

## 1. Accepted M7.1 design (D-069)

| Item | RUN_A |
|---|---|
| Specimens | `SP02/bravo-1-physical`, `SP13/best-physical` |
| Fitted | E_in (E1 = E2), start 52 000 MPa |
| Fixed | G12 4 500 MPa; ν12 0.05; E3, ν13, ν23, G13, G23 (M6.4) |
| Not fitted | t_face (nominal geometry), k_core (INP constants), k_int OFF |
| Search bounds | 26 000–104 000 MPa (solver only) |
| Engineering window | 35–75 GPa (reporting only) |
| Σ | Σ_setup 0.3 % PROVISIONAL; Σ_meas NOT_AVAILABLE |
| FIT vector | `SP02:R1`, `SP02:R2`, `SP13:R1` |
| HOLDOUT (validation only) | `SP02:R3`, `SP13:R2` |
| Budget | 16 new Abaqus solves (hard); LM evaluation budget 11 |

RUN_B (E_in + G12, `EFFECTIVE_MODEL_COMPENSATION_TEST`) is diagnostic only and needs its own later
SUPERVISOR gate.

## 2. M7.1 implementation: RUN_A campaign architecture (zero Abaqus), `REVIEW_READY`

- **Records:**
  - `campaigns/M7_RUN_A.campaign.json` (schema `auto-id/identification-campaign/v1`, campaign hash
    `0a21ad0567901034…`);
  - `campaigns/M7_RUN_A.archive-reuse.json` (`auto-id/campaign-archive-reuse/v1`, `91c8bc547c738a65…`).
- **`src/domain/campaign_definition.py`** (strict parsing):
  - the run-type rules: RUN_A fits E_in only; RUN_B fits E_in + G12 and is refused for execution without
    `run_b_gate`;
  - the explicit `SigmaState`: Σ_meas has no numeric value;
  - search bounds kept separate from the engineering window; the practical target;
  - the archive-reuse plan.
- **`src/services/identification_campaign_run.py`:**
  - **Per specimen:** the active chain is bound and frozen independently:
    - `reregistered_shape_pack_evidence` on the physical registration;
    - the STRICT freeze;
    - the M4.3 holdouts;
    - no cluster trigger.
    The exact accepted rows are reproduced, or the run stops with `ObservationSetMismatch`.
  - **One accepted M4.6 `IdentificationPipeline` per specimen:** content-addressed jobs, archived pack
    reuse, a hash-chained journal, no duplicate solve, M4.5 FE-to-FE tracking of its own rows, holdouts.
  - **`CampaignRun`:**
    - one shared candidate is evaluated on every specimen, and the FIT terms are stacked in definition
      order;
    - a refusal from any specimen refuses the campaign evaluation;
    - resumable campaign journal;
    - the hard Abaqus solve cap is checked before every solve (`SOLVE_BUDGET`);
    - the HUMAN gate is the authorised manifest hash;
    - the optimiser is the accepted M4.8 `run_bounded_lm`.
  - **Archive reuse:**
    - the ODB pin, the status-file pins, the completion and release markers and the excluded attempts are
      checked;
    - the extraction-only job runs the pinned extractor on a SHA-verified copy;
    - the extracted frequencies must equal the accepted CARBON-5A table.
  - **Report:**
    - the engineering estimate (practical target, plausibility, bound, identity);
    - the M5 evidence chain and verdict at p̂ (PRODUCTION context; rules unchanged);
    - the material claim, given only for an M5 IDENTIFIED verdict;
    - "not externally validated".
- **`tools/m7_campaign.py`:** `plan` (no Abaqus), `extract-archive` (Abaqus Python, gated), `run` (Abaqus,
  gated), `report` (no Abaqus).
- **M4.7 additive change:** `RowSigma(measurement_sd=None)` means NOT_AVAILABLE.

**Implementation choices for review:**
- **Σ_meas NOT_AVAILABLE in M4.7.** `RowSigma(measurement_sd=None)` means NOT_AVAILABLE: it is excluded
  from σ and recorded as null in run identities, never as 0.0. The change is additive; numeric σ
  values and their hashes are unchanged.
- **Family identity for the M5 pattern test and leave-one-family-out.** The M4.3 physical family key is
  shared across the campaign: SP-02 R2 and SP-13 R1 are one family (1,2). Each row's term stays
  specimen-qualified (`SP02:R2`).
- **Fitting-pair MAC guard.** It uses the frozen physical strict-pair MACs (baseline). Mode identity at p̂
  is FE-to-FE tracking with MAC ≥ 0.90.
- **M5 system at p̂.** It uses the LM Jacobian reconstructed from the journal: central differences at the
  start plus Broyden updates (`reconstruct_lm_jacobian`, as for the M4.9 twin). No extra solves.
- **Family consistency.** SPEC §13 / ROADMAP M7.4 is not part of RUN_A, so it is `NOT_AVAILABLE`. By D-044
  this blocks a green verdict, so the expected E_in verdict is NOT_IDENTIFIABLE.
- **Effective-estimate rule** (the engineering criterion, separate from M5). `EFFECTIVE_MODEL_PARAMETER_ESTIMATE`
  is given only when all of these hold:
  - LM `CONVERGED`;
  - no tracking refusal;
  - the estimate is not at a numerical bound;
  - every row has tracking MAC ≥ 0.90 and baseline pair MAC ≥ 0.80;
  - max |f_FE/f_EXP − 1| ≤ 10 %;
  - the agreement is no worse than at the start.
  A value outside the engineering window is reported, not rejected.

## 3. Proposed RUN_A execution manifest (not executed)

- **Manifest hash:** `e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6`.
- **Baseline packs reused:** `SP02_f3e592281bebce66` and `SP13_a46d08b52995e078` (p0; 0 solves).
- **±5 % E points reused:**
  - SP-13: governed packs `SP13_0e861d03c333bb0b` (E 54 600) and `SP13_a9df66283a168786` (E 49 400);
  - SP-02: extraction-only jobs `SP02_13363f977809dbff` (E 54 600, ODB `ba38cb69…`) and
    `SP02_84753f636064e192` (E 49 400, ODB `bae6a7c1…`, the technical retry1). The failed first attempt is
    excluded.
- **Maximum new Abaqus solves:** 16, a hard cap with no extension.
- **Maximum Abaqus Python extractions:** 18 (16 after new solves + 2 archive extractions).
- **LM evaluation budget:** 11 (3 reused + at most 8 new; each new evaluation solves both specimens).
- **Executor gate:** `tools/m7_campaign.py extract-archive` and then `run`, each with
  `--authorised-manifest-hash e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6`. RUN_B is not part of the manifest.

**Not done:** no Abaqus, no Abaqus Python, no real LM, no real estimate, no RUN_B.

## 4. HUMAN gate 1: archived SP-02 extraction (D-070), `REVIEW_READY`

- M7.1 (`9c16324`) is ACCEPTED. Gate 1 covered only the 2 archive extractions.
- **Result:** both packs validate, and their frequencies equal CARBON-5A exactly. Tracking from the SP-02
  baseline gives MAC ≥ 0.999998.
- **Manifest:** the executable RUN_A manifest is unchanged (`e4ba607f06a69311…`). The run identity
  `8ed03be3be86aa83…` binds the extracted pack content hashes.
- **Budget remaining:** 16 of 16 new solves.
- **Next:** HUMAN gate 2 (the RUN_A solves) for this exact manifest.
