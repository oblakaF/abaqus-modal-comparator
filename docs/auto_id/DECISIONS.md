# Auto-ID Decision Log

**Append-only.** Existing entries are never edited or deleted. A decision is changed
only by appending a new entry that explicitly supersedes an earlier id
(`Supersedes: D-xxx`). Only decisions accepted by the SUPERVISOR or HUMAN are
recorded here.

Entry format:

```
## D-NNN — <short title>
Date: YYYY-MM-DD · Accepted by: <supervisor/human> · Source: <document/section>
Decision: ...
Rationale / scope: ...
Supersedes: none | D-xxx
```

---

## D-001 — Refusal is a valid result
Date: 2026-10-03 · Accepted by: supervisor + human (Auto-ID v1.1 freeze) · Source: SPEC §1
Decision: Refusing to output a parameter value is a valid Auto-ID scientific result.
Supersedes: none

## D-002 — No peak-derived modes for production identification
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §4, AUDIT K1
Decision: Peak-derived modes are prohibited for production identification.
CARBON-4C/5A are unaffected, because their experimental source is PolyMAX
(SP02 `SP02_polymax_retry_260803.unv` / `bravo-1`; SP13 `SP13_a_polymax.unv` / `best`, 289 points).
Supersedes: none

## D-003 — Observation covariance
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §7
Decision: Σ = Σ_meas + Σ_setup. Specimen variation belongs at campaign/specimen
level. Model form does not enter the optimiser Σ.
Supersedes: none

## D-004 — G12 sources
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §5.1, AUDIT K3
Decision: Stage-A G12 is primary. Sandwich G12 is secondary and conditional on
nuisance constraints and practical identifiability.
Supersedes: none

## D-005 — E1 = E2 in carbon v1
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §5.2
Decision: Current carbon v1 uses E1 = E2 until material-axis orientation becomes
physically traceable.
Supersedes: none

## D-006 — k_core prior from independent evidence
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §5.3, §19.1
Decision: k_core is an effective printed-lattice multiplier. Its prior must come from
independent evidence. CARBON-5F provides sensitivity only.
Supersedes: none

## D-007 — Registration from physical calibration only
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §11, AUDIT K4
Decision: Registration is selected from physical calibration only. Never optimise
registration against MAC or frequency.
Supersedes: none

## D-008 — Frozen observation rows and FE-to-FE tracking
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §12.1, AUDIT V4
Decision: Identification observation rows freeze at baseline. Later candidates use
FE-to-FE branch tracking.
Supersedes: none

## D-009 — Cluster rule
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §12.4
Decision: Near-frequency spacing is only a cluster trigger. Subspace stability is
required.
Supersedes: none

## D-010 — Holdout by family
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §12.3
Decision: Holdout is selected by modal family, not mode index.
Supersedes: none

## D-011 — Full-system practical identifiability
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §10, AUDIT K2
Decision: Practical identifiability uses the full global + nuisance + prior system.
Supersedes: none

## D-012 — Three separate uncertainty quantities
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §9
Decision: `statistical_sd`, `birge_adjusted_sd` and `model_form_robustness` are kept
separate.
Supersedes: none

## D-013 — GUI last
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §16
Decision: GUI integration happens only after a validated scientific backend.
Supersedes: none

## D-014 — No new install_* layers
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §16, AUDIT J2
Decision: No new Auto-ID `install_*` runtime monkeypatch layers.
Supersedes: none

## D-015 — Steel validation gate
Date: 2026-10-03 · Accepted by: supervisor + human · Source: SPEC §17, ROADMAP
Decision: A known-property steel beam/plate experiment is the independent validation
gate after M6 and before final carbon conclusions are accepted.
Supersedes: none

## D-016 — Ordered execution without repeated re-audits
Date: 2026-10-03 · Accepted by: supervisor + human · Source: ROADMAP
Decision: After the Auto-ID v1.1 freeze, implementation follows M0→M8 in order. No
general re-audit between stages unless a stage discovers a specific blocking
contradiction.
Supersedes: none

## D-017 — Bare-plate G12 is material-family specific
Date: 2026-10-03 · Accepted by: SUPERVISOR · Source: ROADMAP M6 open point (P0.1 review of commit `3362076`)
Decision: A bare-plate Stage-A G12 obtained from the twill 0.45 carbon family MUST NOT
be used as the primary G12 material value for the old-plain 0.45 carbon family without
independent evidence that the two face materials are equivalent in in-plane shear.

The existing twill 350×350 bare plate may be used to:
- validate the Stage-A identification method;
- identify G12 for the twill family;
- provide an independent real-carbon Auto-ID validation case.

It does NOT by itself establish primary G12 for old plain 0.45.

For the old-plain 0.45 family, the preferred primary G12 source is a bare plate
manufactured from that same material family. If such a plate is unavailable, sandwich
G12 remains secondary/conditional evidence under SPEC §5.1 and the
practical-identifiability rules (SPEC §10).
Rationale / scope: Twill and plain weave are distinct laminate/material architectures.
A successful identification method may transfer between them, but the identified
material constant must not be transferred across families without physical evidence.
Supersedes: none

## D-018 — No internal FRF→modal fitting in Auto-ID v1 production
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 design decision freeze (SUPERVISOR, after review of `ac1e0e3` / `docs/auto_id/M1_3_DESIGN_REVIEW.md`)
Decision: Auto-ID v1 production does not perform internal FRF→modal fitting. It
accepts only validated curve-fitted modal datasets.
Rationale / scope: modal identification uncertainty must be separated from material
identification uncertainty.
Conflict noted, not resolved here: the frozen SPEC still describes a built-in
multi-mode fit in three places: §4 (footnote to `modes.unv`), §6 S1 ("or the built-in
multi-mode fit (M1)") and §17 (M1 acceptance: SP13 from raw FRF). ROADMAP M1.3 and
the M1 GATE do too. By the precedence rule (SPEC > DECISIONS) these need an explicit
SUPERVISOR resolution, either a SPEC amendment or a redefined M1 gate, before the
M1 stage gate is evaluated.
Supersedes: none

## D-019 — Curve-fitted modal datasets are the only production identification input
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 design decision freeze (SUPERVISOR, after review of `ac1e0e3` / `docs/auto_id/M1_3_DESIGN_REVIEW.md`)
Decision: Curve-fitted modal datasets are the only production identification input.
Peak-derived modes are forbidden for production identification.
Rationale / scope: restates and extends D-002. Implemented by M1.1
(`domain.modal_input_source`: only `curve_fitted` is admitted; `peak_derived` and
`unknown` are refused) and M1.2 (`services.production_modal_input`: accepted manifest
fixtures only).
Supersedes: none

## D-020 — Dataset-58 FRF data are QC and future fitting inputs only
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 design decision freeze (SUPERVISOR, after review of `ac1e0e3` / `docs/auto_id/M1_3_DESIGN_REVIEW.md`)
Decision: Dataset-58 FRF data are QC and future fitting inputs only. They are not
direct Auto-ID identification inputs.
Rationale / scope: peak picking and CMIF/SVD candidates built from dataset 58 stay
viewing, diagnostic and QC tools (D-002, D-019).
Supersedes: none

## D-021 — Modal fitting only through a replaceable ModalFittingProvider
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 design decision freeze (SUPERVISOR, after review of `ac1e0e3` / `docs/auto_id/M1_3_DESIGN_REVIEW.md`)
Decision: Future modal fitting must be provided through a replaceable
`ModalFittingProvider` interface.
Rationale / scope: a provider's output becomes production input only as a validated
curve-fitted dataset. That means it is pinned, carries provenance, passes QC, and
carries a provider/version source label that the SUPERVISOR has admitted to the M1.1
policy. No provider is implemented or active in v1.
Supersedes: none

## D-022 — Human modal selection only in research/review workflows
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 design decision freeze (SUPERVISOR, after review of `ac1e0e3` / `docs/auto_id/M1_3_DESIGN_REVIEW.md`)
Decision: Human modal selection is allowed only in research/review workflows.
Production identification cannot depend on manual mode selection.
Rationale / scope: a production identification result must be reproducible from
pinned inputs and recorded rules alone.
Supersedes: none

## D-023 — FRF-to-modal fitting is a separate validated experimental preparation stage
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 decision resolution (SUPERVISOR review of the D-018 / SPEC conflict recorded in `13973b7`)
Decision: FRF-to-modal fitting is a separate validated experimental preparation stage.
Auto-ID material identification does not directly consume raw FRF.

The fitting stage may be implemented as:
- an external `ModalFittingProvider`;
- an internal `ModalFittingProvider`.

Its output becomes production identification input only after:
- provenance;
- QC;
- source classification;
- fixture identity validation.
Rationale / scope: modal identification uncertainty stays separate from material
identification uncertainty, because fitting happens in its own validated stage before
Auto-ID. This resolves the conflict recorded in D-018. A built-in (internal) fit is
allowed as a preparation-stage provider, so SPEC §4, §6 S1 and §17 (the M1 gate: SP13
from raw FRF) remain consistent with the decisions. D-019, D-021 and D-022 are
unchanged.
Supersedes: D-018

## D-024 — Dataset-58 FRF records are modal-preparation inputs
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 decision resolution (SUPERVISOR review of the D-018 / SPEC conflict recorded in `13973b7`)
Decision: Dataset-58 FRF records are valid inputs for the modal preparation stage,
including future multi-mode fitting. They are not direct material-identification
observations.
Rationale / scope: consistent with D-019 (peak-derived modes forbidden for production
identification) and D-023.
Supersedes: D-020

## D-026 — Frozen external modal selections
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 decision resolution — PolyMAX provider architecture (SUPERVISOR review of the M1.3 blocking report)
Decision: A frozen external modal selection created by a documented and hashed workflow
may be used as a production Auto-ID input. Requirements:
- the source file identity is pinned;
- the modal set identity is pinned;
- provenance is stored;
- the selection is not changed during identification;
- the exported modal dataset is immutable.

Live manual mode selection during an Auto-ID identification run remains forbidden.
Rationale / scope: the prohibition concerns hidden human optimization during
identification, not historical documented preparation of a frozen experimental modal
set. Examples are the operator-selected Testlab PolyMAX sets `bravo-1` (SP02) and
`best` (SP13), pinned in the M0.2 manifest.
Supersedes: D-022

## D-027 — First production ModalFittingProvider
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 decision resolution — PolyMAX provider architecture (SUPERVISOR review of the M1.3 blocking report)
Decision: The first production `ModalFittingProvider` will be an external
PolyMAX-compatible adapter. It will not implement a new FRF fitting algorithm.
Rationale / scope: it connects validated external modal preparation with Auto-ID
while preserving provenance. Future internal fitting providers remain possible.
Supersedes: none

## D-028 — M1 FRF gate uses pinned fixture references
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 decision resolution — PolyMAX provider architecture (SUPERVISOR review of the M1.3 blocking report)
Decision: M1 validation gates must use the accepted fixture-specific reference values.
They must not mix values from different acquisitions.

For the accepted SP13 repeat-a fixture (`SP13/best`), use the pinned PolyMAX values:
approximately 205.65 Hz, 212.66 Hz and 228.61 Hz. The older 206.15 / 212.61 /
228.75 Hz values are not used for this fixture. If the older acquisition is needed
later, it must become a separate fixture with its own provenance.
Rationale / scope: the older values come from the audit's PolyMAX on the 2026-09-09
acquisition (AUDIT §4.2). The pinned `SP13_a_polymax.unv` (2026-09-10) gives
205.65 / 212.66 / 228.61 Hz. This decision applies the SPEC §17 / ROADMAP M1 gate
phrase "±0.05 Hz of PolyMAX" to the fixture-specific PolyMAX values.
Supersedes: none

## D-029 — Internal FRF fitting is future provider work
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: M1.3 decision resolution — PolyMAX provider architecture (SUPERVISOR review of the M1.3 blocking report)
Decision: Internal FRF fitting remains a future `ModalFittingProvider`. It is not
required before the first production PolyMAX-compatible provider.
Supersedes: none

## D-030 — M1 modal-preparation scope; internal fitting staged (SPEC §19 item 4)
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: SPEC §19 item 4 (M1 final closure)
Decision: For traceability, record the normative SPEC §19 item 4.
- The "built-in multi-mode fit (stage M1)" wording of §4, §6 S1 and §17 is clarified:
  Auto-ID never consumes raw FRF, and fitting is a separate modal-preparation stage
  behind `ModalFittingProvider`.
- The first production provider is the external frozen PolyMAX-compatible provider.
- FRF-only packages are refused until an internal provider is implemented, admitted
  and validated. An internal fitter is not an M1 closure condition.
- The §17 raw-FRF recovery criterion is the gate of the first internal provider.
- References are fixture-specific (SP13/best ≈ 205.65 / 212.66 / 228.61 Hz).
Rationale / scope: resolves the stage-assignment conflict recorded as
`BLOCKED_SPEC_GATE` (`48e809e`). Consistent with D-023, D-027, D-028 and D-029.
Supersedes: none

## D-031 — Suspension threshold ownership (SPEC §19 item 5)
Date: 2026-10-04 · Accepted by: SUPERVISOR · Source: SPEC §19 item 5 (M1 final closure)
Decision: For traceability, record the normative SPEC §19 item 5.
- `suspension_max_hz` is a physical specimen / test-run property from the M2 passport
  or acquisition data. It is never guessed from modal frequencies, FE results or
  existing modal sets, and has no default.
- M1 QC evaluates it when a trusted value is supplied, and is `NOT_AVAILABLE`
  otherwise.
- Once supplied, modes below it must not enter material identification.
Rationale / scope: implemented in M1.4 as `TrustedSuspensionThreshold`, the
`suspension_threshold` QC check and `ExperimentalModeEligibility` (`ef95cbe`).
SP02/bravo-1 and SP13/best stay `NOT_AVAILABLE` until M2.
Supersedes: none

## D-032 — N-mode trigger groups: independence only (M4.4, option A1)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §12.4; D-009; M4_DECISION_RECORD §10
Decision: A frequency-trigger group of N > 2 modes is INDEPENDENT only if, in every approved
±5 % direction:
- every baseline member has exactly one distinct FE-to-FE match with MAC ≥ 0.90, and no
  competing match at or above that threshold;
- the N-dimensional subspace of the matches is stable, with every principal-angle
  cos² > 0.95.

Consequences:
- Members of an INDEPENDENT group stay independent observation rows. No N-mode cluster
  residual is created.
- If any condition fails, the group is UNSUPPORTED and the observation design is REFUSED.
  Nothing is split, discarded, merged or hand-picked.
- The 2-mode path (D-009) is unchanged. No new thresholds.
- N-mode confirmation (option A2) is not adopted. Symmetry subdivision (B) is corroborating
  evidence only, never a decision rule.

Rationale / scope:
- SPEC §12.4 makes frequency closeness only a trigger and defines confirmation for 2-mode
  clusters. A1 applies the existing identity test and adds no confirmation rule, so no SPEC
  change is required.
- It narrows the §8.2 refusal of N > 2 groups (M4_DECISION_RECORD) to groups that fail the
  test.

Supersedes: none
