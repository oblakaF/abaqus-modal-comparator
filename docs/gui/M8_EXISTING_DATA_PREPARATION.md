# M8 — Auto-ID campaign preparation on existing data

Status: `REVIEW_READY` (branch `feature/m8-existing-data-preparation`). This page describes how the GUI prepares an
Auto-ID campaign from existing governed records, and what it does not do.

- **Unchanged:** SPEC v1.2, DECISIONS, EVIDENCE, the registrations, frozen pairing, MAC rules, thresholds and gates.
- **Not run:** Abaqus solve, LM.
- **Gates:** production calibration stays `BLOCKED / NOT_AUTHORISED`; the original M8 gate stays `NOT_MET`.

## User path

**Identification › 0. Auto-ID Setup › Campaign draft.** The page now scrolls.

1. **Create Campaign Draft...**, or **Open Campaign Draft...** to reopen a saved draft.
2. Declare:
   - **Question:** `MATERIAL_IDENTIFICATION` or `SPECIMEN_ENGINEERING_CALIBRATION`;
   - **Run type:** RUN_A or RUN_B;
   - **Declare campaign_id...**;
   - **Declare τ_mf...**.
3. Not-fitted parameters:
   - **Declare not_fitted.t_face...** / **...k_core...** — your own description, recorded as written;
   - **k_int: OFF** — the only accepted value; `ENABLED` is refused.
4. **Add governed specimen input...** — a `docs/auto_id/forward_models/*.forward.json` manifest only.
5. **Bind Governed Specimen Records** — solver profile, archived baseline, shape pack and registration evidence.
6. **Bind Accepted FIT / HOLDOUT Observations** — the accepted strict-freeze rows, as recorded.
7. **Check Draft Inputs** — factual availability of the files.
8. **Review Draft Preparation** — the preliminary verdict.
9. **Save Campaign Draft As...** — `auto-id/campaign-draft/v5`, outside the repository and data stores.

Every declaration is validated by the campaign-definition domain rules. Nothing has a default.

## Accepted FIT / HOLDOUT observations

The rows come from the specimen's accepted strict freeze (`accepted_physical_freeze`, the reevaluation record pinned
for the fixture's PHYSICAL registration). For each row the draft records:

- the row id, which is the frozen pair id `<label>:<row>`;
- the experimental and FE mode numbers, with their frequencies;
- the role (the freeze's own holdout split), the M4.3 family, the MAC and Δf/f as frozen.

The freeze's excluded modes are listed with its reasons (no FE mode in the frequency gate, MAC below the policy
minimum). The registration hash, the M2.4 evidence and the freeze fingerprint are shown as provenance.

### When rows are bound

Only when all of the following hold:

- the P11 observation-readiness record counts them: curve-fitted governed modes, a `PHYSICAL` registration, M2.4
  evidence with `registration_limited = false`, and the freeze on that registration;
- the four governed records bound to the draft are the ones the record rests on;
- any cluster group is countable as one term.

### When rows are refused

The draft is left unchanged and the reasons are shown when:

- the registration is legacy (`LEGACY_REPLAY`);
- the modes are peak-derived or unclassifiable (e.g. SP-04 dataset-58 FRF peaks);
- the registration is limited;
- the records are missing or differ.

There is no way to type a row, to assign a role by MAC, frequency or mode number, or to add a weak or unconfirmed
pair. The guided registration of a new mesh never becomes governed evidence here.

Rebinding other records drops that specimen's observations. Reopening re-binds and compares every stored field. An
added, removed or edited row, another registration, or a changed freeze is refused, and nothing is substituted.

For SP-02 and SP-13 the bound rows equal the accepted M7 RUN_A rows exactly:

| Specimen | Rows |
|---|---|
| SP-02 | R1 2↔8 FIT, R2 4↔10 FIT, R3 7↔13 HOLDOUT |
| SP-13 | R1 4↔10 FIT, R2 7↔13 HOLDOUT |

## Draft preparation review

A preliminary review of the exact draft, computed on request and invalidated by any change. It reports:

| Item | Source | Never |
|---|---|---|
| Question consequence | domain rules: calibration has one specimen and is BLOCKED; material needs ≥ 2 specimens | rerouted |
| k | run type: RUN_A 1, RUN_B 2 (the parser's rule) | guessed |
| §8 count per specimen and pooled | `observation_count.count_observations` via P11; family identity by key (D-070) | a rank result |
| k = 9 diagnostic | the same count; no governed nine-constant parameterisation | a fit |
| Numerical sensitivity | archived d ln f / d ln p recorded in the strict freeze: `RECORDED_DIAGNOSTIC_ONLY` | a rank |
| Rank, full leave-one-FIT-family-out, family consistency | `NOT_ASSESSED` (need a campaign run) | PASS |
| Σ_meas | `NOT_AVAILABLE` (D-069) | zero |
| History | M7 RUN_A on the same specimens: D-077, `NO_GLOBAL_PARAMETER_VALUE`, `UNCHANGED` | re-evaluated |
| Missing inputs | each with the reason it is not filled | invented |
| Finalisation | `parse_campaign_definition` (the only validator) | bypassed |

The verdict is one of:

- `DEFINITION_COMPLETE_FOR_FURTHER_REVIEW` — the parser accepts the definition and no count is missing;
- `INCOMPLETE` — with the reasons.

Neither verdict is identifiability, a calibration or an authorisation.

## Readiness on the existing data

| Case | §8 count (k = 1) | k = 9 | Preparation verdict |
|---|---|---|---|
| SP-02 | 2 FIT + 1 HOLDOUT families: met | not met (needs 10 FIT families) | INCOMPLETE (numerical inputs, Σ_setup, budget, decision, provenance missing) |
| SP-13 | 1 FIT + 1 HOLDOUT: **not met** (`INSUFFICIENT_FIT_FAMILIES`) | not met | INCOMPLETE |
| SP-02 + SP-13 (material) | pooled: 2 FIT families (`Px:E|Py:E|nx:0|ny:2`, `Px:O|Py:E|nx:1|ny:2`) + 1 HOLDOUT (`Px:E|Py:O|nx:0|ny:3`): met | not met | INCOMPLETE; history D-077 `NO_GLOBAL_PARAMETER_VALUE` unchanged |
| Nine constants | — | `NOT_SUPPORTED`: only `carbon-property-set/v1` (E_in, G12) exists | nothing fitted |

### Inputs still missing for any new campaign

These have no accepted source for a new campaign and stay missing:

- `parameterisation`, `fitted_parameters` — written only in the final definition;
- `fixed_parameters`, `start`, `bounds`, `engineering_plausibility`, `practical_target`;
- `sigma` (Σ_setup sd_ln and its source), `lm`, `abaqus_solve_budget`;
- `archive_reuse`, `decision`, `provenance`;
- `run_b_gate` — for RUN_B, the SUPERVISOR gate.

## Existing Abaqus models (diagnostic, not governed)

The verified copies in `external_models/` (SP-02 – SP-05, 112 files) were used only through further copies in a
separate run folder.

- **Abaqus:** Abaqus 2024 Python extraction (`extract_odb.py`) in the real main window, one at a time; no solve, no CAE.
- **Integrity:** every ODB copy and every control copy has the same SHA-256 after the run.

| Case | What was checked | Result |
|---|---|---|
| SP-02 INP V01 / V02 / SP2job / 500x500newproperty | block-by-block INP comparison (no Abaqus) | nodes, elements, sets, sections, constraints, step identical. V01 = V02 (job name only). SP2job: face E3, G13, G23 differ. 500x500newproperty: face E1, E2, E3, G12, G13, G23 differ |
| SP-02 V02 ODB (INP = governed `574ae78a…`) | extraction + comparison with the governed UNV | FE geometry `72e8597a…` (1 663 816 nodes) = the accepted SP-02 identity; accepted registration reused. Strict rows reproduced: 2↔8 MAC 0.9176, 4↔10 MAC 0.9508, 7↔13 MAC 0.9754 (as frozen) |
| SP-02 SP2job ODB | extraction; FE-to-FE tracking of R1 – R3 from V02 (`branch_tracker`, strict policy, MAC ≥ 0.90) | same geometry; `TRACKED`: FE-to-FE MAC ≥ 0.99999999, frequency change ≤ 0.017 % |
| SP-02 500x500newproperty ODB | the same | same geometry; `REFUSED` (`BRANCH_LOSS`): R1 (FE mode 8) best FE-to-FE MAC 0.839 (0.163 into mode 9); R2, R3 MAC ≥ 0.9998. A scientific refusal, never re-paired |
| SP-04 `Honeycomb_TPU_FreeFree` | existing CORE-E2E T4 cache against the copy's `.dat` (no extraction) | 19 modes equal within 2.6e-5 (`.dat` precision); dataset-58 FRF peaks stay `PROVISIONAL` |
| SP-05 `SP05_FreeFree` + raw PSV UNV | extraction, no registration | `FREQUENCY_ONLY_DIAGNOSTIC` (8 orientations, no accepted registration); 19 FE modes, 20 `PROVISIONAL` peaks; diagnostic PDF / Excel without MAC or pairs |
| SP-03 `SP03_FreeFree_Modal` + raw PSV UNV | the same | `FREQUENCY_ONLY_DIAGNOSTIC`; 24 FE modes, 21 `PROVISIONAL` peaks; diagnostic PDF / Excel without MAC or pairs |

Limits of these results:

- The property variants are diagnostic FE states, never calibrations.
- No correspondence between an SP-05 model and the specimen is set by frequencies or file names.
- Nothing from SP-03 – SP-05 enters FIT / HOLDOUT.

## Compatibility

- Drafts v1 to v4 open as written, with nothing inferred.
- v4 (PR #80) carries the not-fitted declarations; v5 adds `specimen_observations`.
- A v1–v4 file cannot carry the newer fields.
