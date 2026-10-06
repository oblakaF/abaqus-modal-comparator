# M6 decision record

**Status:** M6 `IN_PROGRESS` (SUPERVISOR entry decisions 2026-10-06). Durable items are promoted
to DECISIONS.md D-049–D-056.

**Branch:** `auto-id/m6`, from `main` `ab1dc60`.

**Scope of M6:** independent physical calibration (SPEC §5, §5.1, §5.3, §7, §15, §17; ROADMAP M6).

**Authorised so far:**
- checkpoint M6-A: governance, design, and the HUMAN SP-11 experiment checklist;
- checkpoint M6-B: the Stage-A → M5 software adapter with synthetic tests.

**Not authorised:**
- no Abaqus or Abaqus Python, and no FE runs;
- no M6-C (real-data admission);
- no deletion of retained M4 artifacts.

| Item | Status | Readiness |
|---|---|---|
| M6.1 | `IN_PROGRESS` | NEEDS_DATA: real SP-11 data missing; not `REVIEW_READY` |
| M6.2 | `TODO` | NEEDS_DATA |
| M6.3 | `TODO` | NEEDS_DATA |
| M6.4 | `TODO` | NEEDS_DECISION |
| M6 gate | not evaluated | — |
| M7 | `NOT_STARTED` | — |

Checkpoints:
- **M6-A:** governance and the experiment checklist.
- **M6-B:** the adapter.
- **M6-C (not started):** real SP-11 data admission.
- **STOP:** a HUMAN Abaqus gate comes before the first SP-11 Stage-A matrix job.

---

## 1. Entry authorisation (SUPERVISOR, 2026-10-06)

- **Review:** the M6 entry review is accepted.
- **Start:** M6 starts on `auto-id/m6`, branched from `origin/main` `ab1dc60`.
- **Scope:** this task covers M6-A and M6-B only.
- **STOP:** after the M6-A/M6-B report, wait for:
  1. the SUPERVISOR review;
  2. the real SP-11 experimental data.

## 2. SP-11 identity (D-049)

- **Specimen:** `D:\Snadwich\SP-11` is the M6 twill 350×350 bare plate (SPEC §13, §17). Its
  governed identity is:

  | Field | Value |
  |---|---|
  | Name | Old CFRP Twill Plate 350x350 |
  | Nominal geometry | approximately 350 × 347 × 0.45 mm |
  | Mass record | approximately 79.59 g |
  | Family | old T300 twill |

  This is the intended M6 specimen identity.
- **D-017 still applies:** a twill result is not primary G12 for old plain 0.45.
- **Old recordings:** they may be used for planning and modal reconnaissance only. They MUST NOT be
  admitted as identification input.

  | Session | Content | Points | Band | Δf |
  |---|---|---|---|---|
  | 260824 | dataset 58 only: FRF, coherence, cross-spectrum; one reference | 121 | 0–250 Hz | 0.3125 Hz |
  | 260826 a | same | 120 | 0–100 Hz | 0.25 Hz |
  | 260826 b_center | same | 121 | 0–100 Hz | 0.25 Hz |

  Reasons:
  - FRF-only input is refused (D-030);
  - the frequency resolution is insufficient: SPEC §15 requires Δf ≤ 0.05 Hz below 100 Hz;
  - no governed frozen modal set exists (D-026).
- **No synthetic substitute:** no modal data are manufactured from these FRFs.

## 3. New SP-11 acquisition (D-049)

- **Requirement:** M6.1 must use a new experiment. The 260824 and 260826 FRFs are not sufficient
  for M6.1 acceptance.
- **Contract:** the new experiment must satisfy the current SPEC, M1 and M2 contracts. The exact
  HUMAN checklist is [M6_SP11_EXPERIMENT_CHECKLIST.md](M6_SP11_EXPERIMENT_CHECKLIST.md).

## 4. M6.1 verdict context (D-050)

- **Kind of result:** M6.1 is a real Stage-A validation and calibration result, in the typed
  context `STAGE_A_VALIDATION`.
- **It may report:**
  - D11 and D66;
  - D12, if practically identifiable (§5);
  - derived E and G12;
  - separately labelled uncertainties;
  - rank and identifiability diagnostics;
  - repeat agreement, after M6.2.
- **What M6 acceptance does not grant:** a production IDENTIFIED material-property verdict under
  the M5.9 PRODUCTION context while the required family consistency is NOT_AVAILABLE.
  - NOT_AVAILABLE is never mapped to PASS.
  - The result is never relabelled as production IDENTIFIED.
- **Stage boundary:**
  - M6 proves the real Stage-A estimate and its physical uncertainty support.
  - M7 remains responsible for production family consistency and the sandwich verdicts.
  - This resolves the hidden M6/M7 dependency found in the entry review.

## 5. D12 policy (D-051)

- **When D12 is fitted:** only when the full Stage-A system (D11, D12, D66) is practically full
  rank at the M5 rule, rcond = 1e-3. No new rank threshold is introduced.
- **When it cannot be independently supported:**
  - no pseudo-inverse;
  - no conditioning override;
  - no legacy fixed-pair fallback.
- **Instead:** the governed fixed-ν12 formulation of the current Stage-A parameterisation is used
  (D12 = ν12·D11, ν12 = 0.05, SPEC §5/§5.2), and the record states explicitly that D12 was not
  identified.

## 6. Thickness uncertainty (D-052)

- **Not an FE nuisance column:** for the bare plate, thickness is propagated analytically from D to
  E and G12 in ln-parameter space:
  - E = 12·D11·(1 − ν²)/t³;
  - G12 = 12·D66/t³.
- **Data:** the ≥ 9 physical thickness measurements.
- **Spatial contribution:** the measured spatial scatter, not the standard error of the mean. The
  physical plate non-uniformity is never divided by √N.
- **Gauge uncertainty:** if a gauge or instrument uncertainty is known, it stays a separately
  identified measurement component and is combined under the uncertainty model. It is never
  invented.
- **Cubic dependence:** E, G12 ∝ t⁻³ stays explicit, so the thickness uncertainty remains visible.

## 7. M6.2 repeat principle and Σ before M6.2 (D-053)

- **What counts as a repeat:** a valid M6.2 repeat is a genuine remount, re-suspension and
  excitation reinstallation of the SAME SP-11 specimen, under the same governed grid and protocol.
  The `remount_of` provenance is recorded.
- **Old sessions:** on current documentation they do not satisfy this.
- **Estimator:** the final Σ_setup estimator is not defined beyond what SPEC requires.
  - The software interface allows it to be added once the repeat dataset exists.
  - The exact formula is a dedicated M6.2 decision, taken after real repeat data exist.
- **Eventual 1σ agreement:** compares the inferred Stage-A mechanical quantities in ln space.
  Shared systematic quantities of the same plate, above all the same thickness characterisation,
  are not double-counted as independent setup scatter.
- **Before M6.2:**
  - development and testing may use the SPEC-authorised provisional setup term (0.3 %, SPEC §7),
    always flagged PROVISIONAL;
  - final M6 acceptance requires the physically measured M6.2 setup/retest evidence;
  - Σ_meas is not invented;
  - setup scatter is never relabelled as measurement uncertainty.

## 8. Core-tile policy (D-054)

- **Evidence required:** M6.3 requires physical core-tile evidence.
- **CARBON-5F:** sensitivity and context evidence only. It is NOT:
  - a k_core prior;
  - a current M5 sensitivity column;
  - a substitute for the core-tile experiment.
- **Plan:** one governed tile experiment for each lattice topology that will need an independent
  k_core prior in M7. Currently expected: auxetic and honeycomb.
- **Not in this checkpoint:** no manufacturing and no model execution.

## 9. M6.4 ranges; t_face and interface (D-055)

- **M6.4 ranges:**
  - no variation ranges are invented for E3, ν13, ν23, G13 or G23;
  - M6.4 stays NEEDS_DECISION until defensible ranges are supported by an approved source or
    decision;
  - the SPEC 0.3 % frequency-effect criterion is unchanged;
  - no M6.4 FE jobs yet.
- **Sandwich t_face:** no morphing in M6; it is M7 work.
- **Interface:**
  - no interface nuisance experiment in M6 unless a later governing decision requires one;
  - k_int stays off by default, with the holdout semantics preserved.

## 10. Legacy Stage-A rules (D-056)

The governed M6 Stage-A path does not inherit legacy rules that conflict with accepted Auto-ID
policy. It rejects:
- automatic mode-1 exclusion based on presumed suspension influence (D-031);
- the legacy condition-number and collinearity thresholds (D-040);
- the conditioning override (D-040);
- the fixed-pair fallback;
- any route that bypasses the M5 rank and refusal logic.

Unrelated legacy code is not rewritten. The governed path is a new adapter around the accepted
Stage-A machinery (§12).

## 11. Status representation

- **Schema:** STATUS keeps the existing mini-step status values. Readiness is recorded alongside:
  - M6 `IN_PROGRESS`;
  - M6.1 `IN_PROGRESS` / NEEDS_DATA;
  - M6.2 `TODO` / NEEDS_DATA;
  - M6.3 `TODO` / NEEDS_DATA;
  - M6.4 `TODO` / NEEDS_DECISION.
- **Not claimed:**
  - M6.1 is not `REVIEW_READY`, because the real SP-11 data are missing;
  - the M6 gate is not evaluated and is not PASS;
  - M7 is `NOT_STARTED`.
