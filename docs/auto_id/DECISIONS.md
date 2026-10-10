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

## D-033 — Strict identification pairing policy (M4.1)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §12.1; D-008; M4_DECISION_RECORD §12
Decision:
- Identification pairing uses the named, explicitly passed policy
  `auto-id/identification-pairing/strict-v1`. No implicit default is constructed. Its values:
  - baseline MAC ≥ 0.80;
  - |Δf| / f ≤ 15 %;
  - FE-to-FE tracking MAC ≥ 0.90 with a unique assignment;
  - at least 2 strict observations;
  - assignment ties (total-MAC difference < 1e-9) are refused.
- The baseline is frozen only when the strict pairing is final. Otherwise it is NOT_FROZEN,
  with the reasons.
Rationale / scope: the values are those of SPEC §12.1. They are fixed in a hashed policy object
and must not be relaxed to obtain a result.
Supersedes: none

## D-034 — Bounded-LM settings and evaluation-budget accounting (M4.8)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §8; M4_DECISION_RECORD §2, §6.2, §11
Decision:
- **Settings:** `LMSettings(mu_initial=1e-3, mu_decrease=10, max_step_attempts=3, solve_budget=20)`,
  with μ × 10 on a rejected step, central finite differences at ±5 %, and the SPEC §8 stop rules.
- **Budget:** the budget counts identification evaluations: p0, finite-difference points,
  trial steps and reused archived evaluations.
- **Counted separately:** actual Abaqus solves. A twin-truth solve and ODB shape extractions are
  outside the identification budget.
- **Failures:** a failed solve is never retried automatically.
Rationale / scope: these are the approved and applied M4 settings. Parameter bounds are a
per-run input; no general bounds are defined here.
Supersedes: none

## D-035 — Modal-family classifier thresholds remain provisional (M4.3)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §12.2–12.3; D-010; M4_DECISION_RECORD §1, §12
Decision:
- The classifier policy `auto-id/modal-family/v1-provisional` is accepted for use in holdout
  selection. Its values:
  - parity threshold 0.80;
  - mirror tolerance 0.02;
  - minimum mirror coverage 0.95;
  - near-square tolerance 0.05;
  - 41-point nodal grid;
  - amplitude floor 0.05.
- These thresholds remain **PROVISIONAL**: they are not physical constants, and their status is
  shown wherever they are used.
- They are revisited on further real shapes; any change requires a new decision.
Rationale / scope: validated on the real SP13 baseline shapes (24/24 classified) and in the twin.
Supersedes: none

## D-036 — Synthetic-twin gate definition and pass criteria (M4.9)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §17 M4; M4_DECISION_RECORD §4, §5, §8.1, §11
Decision:
- **Twin definition:** `docs/auto_id/twins/SP13.twin.json` (hash `c200b293…`):
  - truth E_in_plane 45000 / G12 4000 MPa; start 52000 / 4500 MPa;
  - frequency noise ε ~ N(0, 0.003²) with the explicit fixed seed 20261005 (no default seed);
  - FE modes 7–30 of the truth solve, read through the FrozenRegistration;
  - σ = 0.003 per row; k_int disabled.
- **Observations:** decided only by the strict freeze, M4.3 holdouts, M4.4 / A1 and the M4.7
  design. Nothing is hand-selected.
- **Pass criteria:**
  1. CONVERGED within the budget;
  2. |ln(p̂/p_true)| ≤ local sd for both parameters;
  3. artificial branch exchange refused;
  4. deterministic provenance;
  5. full provenance record;
  6. M3 contracts unchanged.
- **Bounds:** the accepted run used E 26000–104000 and G12 2250–9000 MPa as **development-only
  twin-gate bounds**. They are not physical or material bounds and do not carry over to other
  runs.
Rationale / scope: the M4 gate definition, as applied and accepted. The twin is model-consistent
(it validates the pipeline, not real-specimen accuracy).
Supersedes: none

## D-037 — Observation-design and tracking refusal rules (M4)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §12.1, §12.4; D-008; D-009; D-032; M4_DECISION_RECORD §8.2–§8.4
Decision:
- **Refused designs:** a trigger group that is UNSTABLE, or UNSUPPORTED under D-032, makes the
  observation design REFUSED. So does a CONFIRMED cluster split between fit and holdout. Groups
  are never guessed, split, merged or silently excluded.
- **Refused evaluations:** branch loss, branch exchange, ambiguous tracking or cluster-subspace
  loss refuses the evaluation, with no re-pairing.
- **Crossings:** a frequency crossing with stable shapes is tracked, not refused.
Rationale / scope: these refusals are regular results (D-001). The branch-exchange acceptance
test is a negative control on validated real packs, not physical FE evidence.
Supersedes: none

## D-038 — M3 forward-builder dependency boundary (M4.6)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: M4_DECISION_RECORD §6.4, §8.5
Decision:
- Only the M4.6 pipeline layer (`services/identification_pipeline.py`) imports the M3 forward
  builder.
- Other M4 services obtain M3 job identities through its `forward_jobs` helper.
- The rule is enforced by `tests/test_m4_generic_guard.py`.
Rationale / scope: keeps the M3 contract behind one controlled path, together with the
`subprocess` and `abaqus_bridge` restrictions of §6.4.
Supersedes: none

## D-039 — M5 data scope, twin positive control and S4 noise control (M5)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §6 S4, §7, §17 M5; M5_DECISION_RECORD §1, §2, §6, §12
Decision:
- **Synthetic gate:** the M5 stage-gate nuisance and identifiability cases are synthetic. Their
  sensitivities, Σ, priors and `registration_limited = false` are explicit parts of each case.
- **Real nuisance work:** real t_face / k_core FE columns and real nuisance priors are not required
  to close M5; they are future real-application work.
- **Twin positive control:** the accepted M4.9 twin is a records-based positive control only, not
  real-specimen evidence. It uses:
  - its Broyden-updated LM Jacobian, reconstructed deterministically from the journal and labelled
    as such;
  - Σ = its synthetic noise (σ = 0.003).
- **Not interchangeable:** M4 `local_sd` is never used as M5 `statistical_sd`.
- **Real data:** a missing Σ_meas stays NOT_AVAILABLE.
- **S4 noise control:** the ±2.5 % noise control is not run in M5. It remains mandatory for real
  FE sensitivity columns, under a separate HUMAN Abaqus gate.
Rationale / scope: the SPEC §17 M5 acceptance is stated on synthetic cases; no Abaqus is needed.
Supersedes: none

## D-040 — Nuisance priors, practical rank and q_G (M5.2–M5.4)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §10; D-006; D-011; M5_DECISION_RECORD §3–§5
Decision:
- **Priors:** prior rows exist only for nuisance parameters, with explicit centre and sd in ln p,
  provenance and a PROVISIONAL flag. There are no default prior values; a missing prior or a
  non-positive prior sd is refused.
- **Rank:** practical rank uses rcond = 1e-3. Rank deficiency is a hard block: no covariance, no
  pseudo-inverse, no override.
- **Diagnostics:** condition number, correlations and pairwise cosines are diagnostics only.
- **q_G:** q_G = ‖(I − P_N) a_G‖ / ‖a_G‖ is diagnostic, with no verdict threshold. The verdict
  follows the full uncertainty and rank calculation.
Rationale / scope: implements SPEC §10 without inventing thresholds.
Supersedes: none

## D-041 — Birge χ² and degrees of freedom (M5.6)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §9; M5_DECISION_RECORD §7
Decision:
- **χ²:** the sum of squared whitened fit residual terms only. Prior rows and holdouts are
  excluded; a confirmed cluster is one term.
- **dof:** n_fit_terms − n_fitted_parameters, counting all estimated parameters, including fitted
  nuisance parameters. dof ≤ 0 refuses the Birge calculation and a green verdict.
- **Scaling:** s_B = √max(1, χ²/dof). `birge_adjusted_sd` = `statistical_sd`·s_B, populated only
  when the residual-pattern test passes.
Rationale / scope: fills a definition the SPEC leaves implicit.
Supersedes: none

## D-042 — Linearised leave-one-family-out model_form_robustness (M5.7)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §9, §14; M5_DECISION_RECORD §8
Decision:
- **Method:** linearised at p̂. For each fitted modal family, remove all of its fit terms and solve
  the reduced local linearised system with the same parameter, nuisance and prior contract. There
  are no nonlinear or Abaqus refits.
- **Refusal:** a reduced system that is rank-deficient (rcond = 1e-3) refuses that case, and the
  result cannot support a green verdict.
- **Reporting:** the range of the estimates in % of p̂. It is not `statistical_sd`, not 1σ, and
  not part of Σ.
- **Holdouts:** never promoted into the fit.
Rationale / scope: the SPEC fixes the quantity, not the refit method.
Supersedes: none

## D-043 — Residual-pattern test for singleton families (M5.8)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §6 S7; M5_DECISION_RECORD §9
Decision:
- **Fit families:** a fit family triggers the systematic-pattern condition only when it has at
  least two fit residual terms, all of the same sign and each with |r| > 2 (whitened).
- **Singletons:** a single fit residual cannot establish a family-wide pattern, and unrelated
  singleton families are never merged.
- **Holdouts:** any holdout with |r| > 3 (whitened) fails the check, and no green verdict is
  allowed.
Rationale / scope: clarifies an ambiguity in the SPEC for single-member families. The 2σ and 3σ
thresholds are unchanged.
Supersedes: none

## D-044 — Family consistency NOT_AVAILABLE and the registration-limited source (M5.9)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §3, §13; M5_DECISION_RECORD §10, §11
Decision:
- **Family consistency:**
  - NOT_AVAILABLE is not PASS;
  - in the explicitly synthetic single-specimen M5 gate it does not by itself stop the M5
    machinery being exercised or passed;
  - for real-data production verdicts the SPEC requirement stands: if the required family
    consistency is unavailable, a green IDENTIFIED verdict is blocked.
- **registration-limited:** the existing M2 registration diagnostic is its only source; no second
  metric or threshold is created.
Rationale / scope: separates synthetic-gate exercise from production verdicts.
Supersedes: none

## D-045 — M5 verdict envelope and semantics (M5.9)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §3, §9; D-012; M5_DECISION_RECORD §19
Decision:
- **Comparison space:** the verdict comparison is made in ln p:
  conservative_ln = max(`birge_adjusted_sd_ln`, model_form_half_range_ln).
  - ≤ 0.05 → IDENTIFIED;
  - > 0.05 and ≤ 0.08 → WIDE;
  - > 0.08 → NOT_IDENTIFIABLE.

  Percent values are for readability only.
- **Green conditions:** a green or WIDE verdict needs every guard to pass: practical rank,
  residual pattern and holdout, Birge available, `model_form_robustness` without refused cases,
  fitting-pair MAC, no branch / pairing loss, not `registration_limited`, no peak-derived input,
  family consistency (D-044) and the sandwich-G12 policy (D-046).
- **Missing evidence:** never an implicit PASS.
- **WIDE:** never hides a block. There is no user override.
- **Reporting:** the three uncertainty quantities stay separately labelled; the reported value is
  given only for IDENTIFIED / WIDE.
Rationale / scope: makes the SPEC §3/§9 verdict decidable without mixing units or labels.
Supersedes: none

## D-046 — Sandwich G12 policy in the verdict engine (SPEC §5.1)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §5.1; D-004; D-017; M5_DECISION_RECORD §19
Decision:
- **Independence:** sandwich G12 may be IDENTIFIED only when every required nuisance quantity
  (core, and interface where relevant) is constrained by provenance independent of the evaluated
  modal fit.
  - Real / production: a PROVISIONAL prior never satisfies this; it may still take part in the
    calculation, but the verdict carries the limitation.
  - Synthetic gate: an explicit synthetic-definition constraint may satisfy it; this never
    generalises to real data.
- **Bare plate:** without bare-plate support and without a complete §5.1 sandwich path, G12 is
  NOT_IDENTIFIABLE (`BARE_PLATE_REQUIRED`). Bare-plate evidence is never inferred from the
  sandwich specimen.
Rationale / scope: a conservative, explicit implementation of SPEC §5.1.
Supersedes: none

## D-047 — sd_ln > 0.08 in the M5 verdict: no automatic refit (SPEC §10)
Date: 2026-10-05 · Accepted by: SUPERVISOR · Source: SPEC §10; M5_DECISION_RECORD §19
Decision:
- **Verdict:** a fitted parameter with `statistical_sd` sd_ln > 0.08 is NOT_IDENTIFIABLE
  (`SD_ABOVE_8_PERCENT`).
- **No refit in M5:** M5 does not launch a refit, modify the accepted fit, or silently fix the
  parameter and recompute the others.
- **Estimate:** preserved for provenance and never promoted as an identified property.
- **Later:** a "fix and refit" is a separate estimation action that needs its own authorised
  workflow.
Rationale / scope: the verdict engine evaluates the accepted fit and its evidence.
Supersedes: none

## D-048 — Cluster family identity for the pattern test and leave-one-family-out (M5.7, M5.8)
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §6 S7, §9, §12.4; D-042; D-043; M5_DECISION_RECORD §18.1
Decision:
- **Shared family:** if all members of a confirmed cluster share one M4.3 modal family, the
  cluster residual is one fit term belonging to that shared family.
- **Mixed families:** if the members belong to different M4.3 families, the cluster term gets one
  unique composite family key. It is attached to neither source family and never merged with
  unrelated families.
- **Pattern test:** the composite cluster is one family term. Alone under its key, it is a
  singleton and cannot trigger the ≥ 2-member systematic-pattern condition (D-043).
- **Robustness:** `model_form_robustness` (leave-one-family-out, D-042) uses the same family
  identity.
Rationale / scope: a durable M5.7/M5.8 semantic rule for clusters. No synthetic or twin-specific
value is promoted.
Supersedes: none

## D-049 — SP-11 is the M6 twill bare plate; new acquisition required (M6.1)
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §13, §15, §17; ROADMAP M6.1; D-017, D-026, D-030; M6_DECISION_RECORD §2–§3
Decision:
- **Identity:** SP-11 "Old CFRP Twill Plate 350x350" is the intended M6 specimen: the twill 350×350
  bare plate (nominal about 350 × 347 × 0.45 mm, mass record about 79.59 g, old T300 twill family).
- **Old recordings (260824, 260826 a, 260826 b_center):** planning and modal reconnaissance only;
  never identification input. Reasons:
  - FRF-only input is refused (D-030);
  - the frequency resolution is insufficient (SPEC §15);
  - no governed frozen modal set exists (D-026).

  No modal data are manufactured from them.
- **New acquisition:** M6.1 uses a new SP-11 experiment that satisfies the current SPEC, M1 and M2
  contracts (M6_SP11_EXPERIMENT_CHECKLIST.md).
Rationale / scope: the SPEC §17 M6 specimen is identified from the records. D-017 is unchanged:
twill G12 is not primary old-plain G12.
Supersedes: none

## D-050 — M6.1 is a STAGE_A_VALIDATION result, not a production verdict
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §3, §13, §17; D-044, D-045; M6_DECISION_RECORD §4
Decision:
- **Context:** M6.1 is a real Stage-A validation and calibration result in the typed context
  `STAGE_A_VALIDATION`.
- **It may report:**
  - D11 and D66;
  - D12 if practically identifiable;
  - derived E and G12;
  - separately labelled uncertainties;
  - rank and identifiability diagnostics;
  - repeat agreement after M6.2.
- **No production verdict:** M6 acceptance does not grant a production IDENTIFIED material-property
  verdict under the M5.9 PRODUCTION context while the required family consistency is
  NOT_AVAILABLE.
  - NOT_AVAILABLE is never mapped to PASS.
  - The result is never relabelled as production IDENTIFIED.
- **Boundary:**
  - M6 proves the real Stage-A estimate and its physical uncertainty support.
  - M7 remains responsible for production family consistency and the sandwich verdicts.
Rationale / scope: resolves the M6/M7 dependency found in the M6 entry review. The M5.9 engine is
unchanged.
Supersedes: none

## D-051 — Stage-A D12 policy (M6.1)
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §5, §5.2, §10; D-040; M6_DECISION_RECORD §5
Decision:
- **When D12 is fitted:** only when the full Stage-A system (D11, D12, D66) is practically full
  rank at the M5 rule rcond = 1e-3. No new rank threshold.
- **Otherwise:**
  - no pseudo-inverse, no conditioning override, no legacy fixed-pair fallback;
  - the governed fixed-ν12 formulation is used: D12 = ν12·D11, ν12 = 0.05 (SPEC §5/§5.2);
  - the record states explicitly that D12 was not identified.
Rationale / scope: implements SPEC §5 "D12/D11 where possible; ν12 default 0.05" with the accepted
rank rule.
Supersedes: none

## D-052 — Bare-plate thickness propagation (M6.1)
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §5, §7, §15; M6_DECISION_RECORD §6
Decision:
- **No FE column:** for the bare plate, thickness is not an FE nuisance column. It is propagated
  analytically from D to E and G12 in ln p, from the ≥ 9 physical thickness measurements.
- **Spatial contribution:** the measured spatial scatter, not the standard error of the mean. It is
  never divided by √N.
- **Gauge:** a known gauge or instrument uncertainty stays a separate measurement component,
  combined under the uncertainty model. It is never invented.
- **Cubic dependence:** E, G12 ∝ t⁻³ stays explicit.
Rationale / scope: SPEC §7 gives δE/E ≈ 3·δt/t for a bare plate; the physical non-uniformity of the
plate is not reduced by sampling it more often.
Supersedes: none

## D-053 — M6.2 repeat principle and Σ before M6.2
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §7, §15; D-003; M6_DECISION_RECORD §7
Decision:
- **Valid repeat:** a genuine remount, re-suspension and excitation reinstallation of the same SP-11
  specimen, under the same governed grid and protocol, with `remount_of` provenance. The old
  sessions do not qualify on current documentation.
- **Estimator:** the final Σ_setup estimator and the 1σ agreement rule are a dedicated M6.2
  decision, taken after real repeat data exist. The software only prepares the interface.
- **Agreement comparison:** in ln space, on the inferred Stage-A mechanical quantities. Shared
  systematic quantities of the same plate (above all its thickness characterisation) are not
  double-counted as setup scatter.
- **Before M6.2:**
  - the SPEC-authorised provisional Σ_setup (0.3 %) may be used and stays PROVISIONAL;
  - final M6 acceptance requires the measured M6.2 evidence;
  - Σ_meas is not invented;
  - setup scatter is never relabelled as measurement uncertainty.
Rationale / scope: keeps Σ explicit and physically grounded (SPEC §7, D-003).
Supersedes: none

## D-054 — Core-tile policy; CARBON-5F scope (M6.3)
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §5.3, §15; D-006; M6_DECISION_RECORD §8
Decision:
- **Evidence:** M6.3 requires physical core-tile evidence.
- **CARBON-5F:** sensitivity and context evidence only. It is not a k_core prior, not a current M5
  sensitivity column, and not a substitute for the core-tile experiment.
- **Plan:** one governed tile experiment per lattice topology that will need an independent k_core
  prior in M7 (currently auxetic and honeycomb).
Rationale / scope: restates D-006 for M6 execution. No manufacturing or model execution is
authorised by this decision.
Supersedes: none

## D-055 — M6.4 ranges not invented; sandwich t_face and interface deferred
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §5, §5.1, §12; M6_DECISION_RECORD §9
Decision:
- **M6.4:**
  - no variation ranges are invented for E3, ν13, ν23, G13 and G23;
  - M6.4 stays NEEDS_DECISION until an approved source or decision supports defensible ranges;
  - the SPEC 0.3 % frequency-effect criterion is unchanged;
  - no M6.4 FE jobs yet.
- **Sandwich t_face:** no morphing in M6; it is M7 work.
- **Interface:** no interface nuisance experiment in M6 unless a later governing decision requires
  one. k_int stays off by default, with the holdout semantics preserved.
Rationale / scope: avoids guessed ranges and keeps the M6/M7 stage boundary.
Supersedes: none

## D-056 — Legacy Stage-A rules are excluded from the governed M6 path
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §6 S1, §10, §12.1; D-031, D-033, D-040; M6_DECISION_RECORD §10
Decision: the governed Stage-A path does not inherit legacy rules that conflict with accepted
Auto-ID policy. It rejects:
- automatic mode-1 exclusion on presumed suspension influence;
- the legacy condition-number and collinearity policy thresholds;
- the conditioning override;
- the fixed-pair fallback;
- any route that bypasses the M5 rank and refusal logic.

Unrelated legacy code is not rewritten. The governed path is a new adapter around the accepted
Stage-A machinery.
Rationale / scope: one scientific rule set (M5) for real Stage-A results.
Supersedes: none

## D-057 — SP-11 M6.1 evidence is BLOCKED_ON_EXPERIMENT (corrects D-049)
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: real-specimen source audit of `D:\Snadwich` (accepted 2026-10-06); HUMAN physical constraint; SPEC §6 S1, §15, §17; D-024, D-026, D-031; M6_DECISION_RECORD §15
Decision:
- **Kept from D-049:**
  - SP-11 (old T300 twill 0.45 bare plate) is the M6 twill bare plate;
  - its existing data are reconnaissance-only for the current M6.1 contract.
- **No longer reasons or requirements:**
  - frequency resolution alone is not a reason to refuse SP-11, because the accepted SP02 and SP13
    lineages also started from raw FRFs coarser than SPEC §15; M1 QC records resolution as a flag;
  - "new acquisition required" is no longer an actionable requirement: the HUMAN has stated that a
    new SP-11 experiment is not physically available with the present setup.
- **Current state:** SP-11 M6.1 evidence is `BLOCKED_ON_EXPERIMENT` because:
  - there is no governed fitted / frozen modal set (dataset 58 only; no dataset 55);
  - the three available sessions (260824, 260826 a, 260826 b_center) are inconsistent with each
    other;
  - required physical support data are incomplete: no ≥ 9-point thickness map, no mass or
    dimension uncertainty, no attachment mass for the contact excitation, no suspension threshold;
  - a new valid SP-11 experiment is not available.
- **Status of the old FRFs:** they are not declared invalid or useless. They remain reconnaissance
  and modal-preparation source data (D-024).
Rationale / scope: records the factual blockers found by the source audit, instead of a resolution
bar that the accepted fixtures do not satisfy either. SPEC §17 and ROADMAP M6.1 are unchanged; any
stage rescope is a separate later decision.
Supersedes: D-049 (in part: the "frequency resolution insufficient" reason and the "new acquisition"
requirement; the identity and the reconnaissance-only scope remain in force)

## D-058 — Setup-repeat wording aligned with SPEC §7; SP-11 M6.2 BLOCKED_ON_EXPERIMENT (corrects D-053)
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §7, §15; M2 `classify_setup_repeat` (M2.5); M6_DECISION_RECORD §15
Decision:
- **Repeat definition (SPEC §7, unchanged in substance):** a setup repeat is a genuine remount,
  re-suspension or excitation reinstallation of the same physical specimen, with `remount_of`
  provenance and a comparable acquisition protocol.
  - On the same grid it supports frequencies, shapes and MAC.
  - A same-panel independent remount on a different grid supports a frequency-only estimate
    (SPEC §7).
  - This replaces D-053's "same governed grid and protocol" wording, which omitted the SPEC §7
    frequency-only case. No new repeat criterion is introduced; the M2 classifier already
    implements this.
- **SP-11 M6.2:** `BLOCKED_ON_EXPERIMENT`. No documented remount links the existing sessions, and a
  new valid repeat is not available. The repeat definition is not weakened to make the old
  sessions qualify.
- **Kept from D-053:**
  - shared plate quantities are never counted as setup scatter;
  - the estimator and agreement rule are a later M6.2 decision;
  - the provisional Σ_setup is flagged;
  - Σ_meas is never invented.
Rationale / scope: governance wording must match SPEC (precedence SPEC > DECISIONS).
Supersedes: D-053 (in part: the "same governed grid and protocol" wording and the expectation of an
SP-11 repeat; everything else remains in force)

## D-059 — M6.1, M6.2 and M6.3 are NOT_AVAILABLE_WITH_CURRENT_SETUP
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: HUMAN experimental constraints; accepted M6 rescope review (F–K); SPEC §19 item 6; M6_DECISION_RECORD §16
Decision:
- **M6.1 (SP-11 bare-plate Stage A):** `NOT_AVAILABLE_WITH_CURRENT_SETUP`. Consequences:
  - no primary twill G12 evidence;
  - no real-data Stage-A validation;
  - the M6-B Stage-A adapter stays in the software, synthetically validated;
  - this alone is not a release failure.
- **M6.2 (SP-11 repeat):** `NOT_AVAILABLE_WITH_CURRENT_SETUP`.
  - The SPEC §7 provisional Σ_setup (0.3 %) stays allowed and FLAGGED.
  - A measured sandwich-remount estimate may replace it later, only if genuine remount provenance
    is established from existing records. No session pair is declared a remount without proof.
- **M6.3 (core tile):** `NOT_AVAILABLE_WITH_CURRENT_SETUP`. Consequences:
  - there is no independently measured k_core prior;
  - the sandwich-only G12 route stays closed (D-046);
  - k_core may later enter M7 only as an explicitly PROVISIONAL nuisance with a
    SUPERVISOR-approved width, which is not chosen here.
- **Records kept:** the M6.1–M6.3 scientific requirements and their history (D-049–D-058) are kept;
  only the expectation of executing them in this project is withdrawn.
Rationale / scope: missing experiments reduce the scientific claims; they do not invent evidence.
Supersedes: D-054 (in part: the active plan of one governed tile experiment per topology; the
requirement that a k_core prior needs physical core-tile evidence remains); D-057 and D-058 (in
part: the `BLOCKED_ON_EXPERIMENT` status labels, now `NOT_AVAILABLE_WITH_CURRENT_SETUP`)

## D-060 — The STEEL validation gate is removed from the release path
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §17, §19 item 6; ROADMAP STEEL gate; M6_DECISION_RECORD §16
Decision:
- **Removal:** no steel or other external known-stiffness validation experiment is part of the
  selected project release path. No replacement experiment is created.
- **Labelling:** final real carbon results are reported as model-calibrated effective constants
  (SPEC §5.2) and labelled **not externally validated**.
Rationale / scope: the steel experiment was an exploratory idea only. Its removal weakens the
claim (no external validation); it does not change any scientific rule.
Supersedes: D-015

## D-061 — Rescoped M6 gate
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SPEC §19 item 6; ROADMAP M6 GATE
Decision: M6 passes when:
- all unavailable physical evidence is explicitly recorded;
- every missing prior has its conservative verdict consequence encoded;
- provisional inputs are explicitly flagged;
- the M6.4 transverse-constant sensitivity budget is closed.

M6 is not accepted by this decision.
Rationale / scope: replaces the former acceptance "D11, D66 → E, G12 with uncertainty; repeat of
the same plate agrees within 1σ", which cannot be executed with the current setup.
Supersedes: none (the SPEC §17 M6 row is superseded by SPEC §19 item 6)

## D-062 — SP-13 physical registration from stored PSV records; the legacy centred registration is historical only
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: SP-13 physical registration gate; SPEC §4.1, §11, §15; D-007, D-045; M6_DECISION_RECORD §17
Decision:
- **Basis:** the SP-13 260910a registration is reconstructed from the stored PSV records alone:
  - camera frame, MeasPoints video coordinates (validated against the UNV) and the default
    full-frame rectangle;
  - fitted panel edges;
  - the measured panel dimensions.

  It is frozen through the unchanged M2 builder:
  - mode `scan_to_panel_edges` with a `camera_grid` per-axis scale;
  - registration `2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823`;
  - passport `SP13.physical.specimen.json` (manifest `943bb3d1946863c61abd39ccac8fa1da625067b9dffdcd6be2c82c3e125d5000`);
  - reconstruction record SHA-256 `6b45fbfbacad0df939b0b12f8496edddff0525855e0de0312ff5f558c71bb0ae`.

  It is production-ready under the M2 contract.
- **Legacy registration `a8970e525d10173af3d3b030b1150ca24432b616e1b52f6e8cfeefe2946f58a4`:** geometrically inconsistent with the stored physical scan
  geometry (point-placement error median 26.0 mm, maximum 47.4 mm; the UNV metric coordinates are
  anisotropic, x 1.195 and y 0.889 of physical). It is kept only as historical provenance and is
  never recorded as physically valid.
- **Face:** the scanner measured the labelled face (HUMAN H3). Binding it to FE TOP is a convention:
  it is not demonstrable from the records, and the FE stack is through-thickness symmetric.
- **FE axis signs:**
  - the nominal +x→+X, +y→+Y continues the accepted legacy convention and was fixed before any
    pairing evaluation;
  - the four physically admissible sign mappings are geometrically indistinguishable (identical
    mapping residuals);
  - the 180° TOP-face alternative gives the same strict pairs;
  - the bottom-face alternatives are not evaluable without an Abaqus Python extraction.

  The ambiguity is preserved, not resolved by modal agreement.
- **Uncertainty:**
  - `translation_mm` 5.72 (maximum residual of the M2 model against the reconstruction);
  - `rotation_deg` 0.49 (maximum axis misalignment);
  - `scale_rel` NOT_AVAILABLE, because no instrument resolution is recorded (HUMAN H5).

  Therefore `registration_limited` stays NOT_AVAILABLE, and no green production verdict may claim
  the registration uncertainty is closed. D-045 is unchanged.
- **Anti-tuning:** the transform is derived without modal data and pinned (the record hash is in the
  passport provenance; the registration hash is pinned by test). A registration change must come
  from a new reconstruction record, never from pairing or MAC results.
- **Out of scope:** wiring the fixture manifest and production modal input to the physical
  registration is later work. The SP-13 fixture still references the legacy registration.
Rationale / scope: physical evidence replaces a documented convention. Thresholds, pairing policy and
modal data are unchanged.
Supersedes: none (the legacy registration stays as historical provenance)

## D-063 — SP-13 260909 → 260910 is a genuine re-suspension: FREQUENCY_ONLY; Σ_setup pending modal preparation
Date: 2026-10-06 · Accepted by: SUPERVISOR · Source: HUMAN H6; SPEC §7; D-058, D-059
Decision:
- **Remount:** 260909 → 260910 is a genuine same-panel independent re-suspension. The panel was
  removed and re-suspended; the laser/scanner and shaker installation did not move; the SP-13
  marking is visible in both stored frames.
- **Recorded in the physical passport:** `remount_of` = the 260909 run, `remount_kind` =
  `re_suspension`, and the HUMAN evidence.
- **Grids differ (121 / 289 points):** FREQUENCY_ONLY repeat evidence. No shape or MAC
  repeatability is claimed. Protocol comparability is accepted for frequency-only setup/retest use.
- **Σ_setup:** stays at the SPEC provisional 0.3 %, flagged. A measured Σ_setup is
  `NOT_AVAILABLE_PENDING_MODAL_PREPARATION`: 260909 is raw FRF only; no internal fitter is used; an
  accepted external PolyMAX route is not currently available. Not a release blocker (D-059).
Supersedes: none

## D-064 — SP-13 gate accepted; HUMAN facts H7–H10 (orientation, instrument readout, modal preparation, repeat scope)
Date: 2026-10-06 · Accepted by: SUPERVISOR (HUMAN facts H7–H10) · Source: SUPERVISOR "SP-13 HUMAN evidence update + SP-02 zero-Abaqus physical registration gate"; D-062, D-063; SPEC §7, §11
Decision:
- **SP-13 gate:** the SP-13 physical registration result at `173af43` is SUPERVISOR-ACCEPTED. The
  strict pairs {94.40 Hz ↔ FE 10, 205.65 Hz ↔ FE 13}, the STRICT policy, the M4.3 holdout rule and
  the anti-tuning provenance are preserved. The transform is not redone or tuned.
- **H7 (orientation):** SP-13 was scanned in the same in-plane orientation as represented in the
  Abaqus model: the auxetic-core directions correspond, the label is at the physical top, and the
  panel was not intentionally flipped or rotated. This is physical evidence for the in-plane FE axis
  signs (+x→+X, +y→+Y); the 180° alternative is excluded. MAC is never used for signs.
- **H8 (instruments):** steel ruler 100 cm, smallest graduation 1 mm; dial caliper resolution
  0.01 mm. These are HUMAN-confirmed instrument/readout resolutions, **not** calibrated instrument
  accuracy. No calibration or operator uncertainty is recorded, and none may be invented.
- **H9 (modal preparation):** Simcenter Testlab is not available. There is no PolyMAX fit of
  260909, so a measured Σ_setup is unavailable. Σ_setup stays at the SPEC provisional 0.3 %, flagged.
- **H10 (repeat scope):** 260909 → 260910 is comparable for FREQUENCY_ONLY use. No cross-grid
  shape or MAC claim is made.
Rationale / scope: records the HUMAN facts and the SUPERVISOR acceptance. The derived quantities
(the readout `scale_rel` contribution, the M2.4 result, the SP-02 registration) are worker results
pending SUPERVISOR review (EVIDENCE; M6_DECISION_RECORD §18). The pairing policy, thresholds,
holdout rule and modal data are unchanged.
Supersedes: none (D-062 and D-063 stand; H7 resolves the in-plane sign alternative D-062 left open)

## D-065 — Specimen catalog accepted; SP-02 identity and physical registration accepted and active; SP-13 260909 PolyMAX frozen; H9 clarified
Date: 2026-10-07 · Accepted by: SUPERVISOR · Source: SUPERVISOR "Catalog acceptance + SP-02 acceptance + SP-13 260909 PolyMAX provenance gate" and its confirmation of 2026-10-07; SPEC §7; D-026, D-027, D-028, D-062, D-063, D-064
Decision:
- **Specimen catalog:** commit `bb62060` (`SPECIMEN_CATALOG.md`, `specimen_catalog.json`) is the canonical
  specimen inventory. Catalog questions already answered there are not reopened. SP-12, SP-14, SP-15 and
  the unnumbered 300×300 panels stay unresolved catalog entries; they are not M7 blockers.
- **SP-02 identity:** the record-based resolution is accepted. "SP2 (old)" is the physical SP-02;
  "SP10 (new SP2)" is the separate physical SP-10. No further HUMAN identity confirmation is required.
- **SP-02 physical registration:** the result of `09c05a0` (`9b63f6c8…`) is accepted.
  - The active SP-02 passport and fixture are bound to it.
  - The legacy registration `9bf736d3…` is kept only as historical provenance.
  - Anti-tuning evidence and the M4 pairing/holdout policies are unchanged.
- **SP-13 260909 PolyMAX:**
  - `SP13_polymax.unv` in `I:\Sumin\SPname_files_260909_polymax.zip` is accepted as the confirmed
    external PolyMAX fit of the physical SP-13 260909 session.
  - Its set "Bravo (1)" (31.64, 74.14, 80.82, 94.43, 96.55, 147.86, 206.15, 212.61, 228.75 Hz) is frozen through the D-026 / D-027 route, with no refit.
  - Per D-028 it is a separate governed fixture, used FREQUENCY_ONLY.
- **H9 clarified:** H9 means only that Simcenter Testlab is not available now, so no new fit or refit can
  be made. It does not deny that a historical PolyMAX fit of 260909 exists. The confirmed historical fit
  does not contradict HUMAN evidence.
- **Σ_setup:** not recomputed. It stays at the SPEC provisional 0.3 %, flagged.
  - No estimator and no cross-grid mode matching are invented.
  - A measured Σ_setup is deferred to a separate decision and blocks neither release nor M7.
- **M6:** not accepted. M6.4 remains the M6 blocker. No M7 fitting.
Rationale / scope: records SUPERVISOR acceptances and the governed updates they authorise. The
implementation (records, tests) is a worker result pending SUPERVISOR review (EVIDENCE).
Supersedes: D-064 (in part: the H9 wording "there is no PolyMAX fit of 260909" is clarified as above;
everything else in D-064 stands)

## D-066 — M6.4 interim screening envelope, screening rule and observation set; practical accuracy target
Date: 2026-10-07 · Accepted by: SUPERVISOR · Source: SUPERVISOR "M6.4 FINAL SCREENING PLAN — SUPERVISOR RANGE DECISION" and "SUPERVISOR CLARIFICATION — PRACTICAL ACCURACY TARGET" (2026-10-07); SPEC §5, §5.2, §19 item 6; D-055, D-061, D-064, D-065
Decision:
- **Basis:** commit `8b4afff` and the D-065 governed updates are accepted as the basis of M6.4.
- **Screening envelope (the M6.4 range source):**
  - E3 5.0–10.0 GPa; ν13 0.20–0.40; ν23 0.20–0.40; G13 2.2–5.0 GPa; G23 2.2–5.0 GPa.
  - Basis `LITERATURE_INTERIM_SCREENING_ENVELOPE`, not `MATERIAL_SPECIFIC`. It is not a measured
    property, not a material-specific prior and not a calibrated uncertainty distribution. It is a
    conservative envelope for deciding whether the fixed constants matter to the Auto-ID result.
  - Literature close-woven analogue: E3 ≈ 5–10 GPa, ν13/ν23 ≈ 0.2–0.4, G13/G23 ≈ 3–5 GPa.
  - The G13/G23 lower bound includes the governed baseline 2.2 GPa on purpose. That value is not claimed
    as literature-supported.
- **Screening rule (SPEC §5 criterion unchanged):**
  - One constant at a time, both envelope endpoints, at the governed reference candidate (E_in 52 000 MPa,
    G12 4 500 MPa; the CARBON-4C baseline). An endpoint equal to the baseline needs no solve (Δf ≡ 0).
    E_in and G12 are not refitted.
  - Output: the frequencies of the frozen observation rows (fit and holdout). Each row is followed from the
    baseline by FE-to-FE MAC tracking (M4.5); it is never re-paired.
  - max |Δf/f| < 0.3 % on every row, specimen and endpoint → `NEGLIGIBLE_FOR_BUDGET`; otherwise
    `INCLUDE_IN_UNCERTAINTY_BUDGET`. A tracking refusal leaves the constant unclassified and is escalated.
  - `INCLUDE_IN_UNCERTAINTY_BUDGET` is bookkeeping. It is not a failure and never a reason to re-tune the
    model. The signed per-row effects are recorded. How they propagate into M7 is decided at M7 entry;
    they are not placed in Σ.
- **Observation set (accepted):**
  - SP-02 physical strict freeze: R1 FE 8 and R2 FE 10 (fit), R3 FE 13 (holdout);
  - SP-13 physical strict freeze: R1 FE 10 (fit), R2 FE 13 (holdout).
  - The forward models `SP02.forward.json` and `SP13.forward.json` serve the FE model only. FE-to-FE
    tracking does not depend on the registration.
- **Practical accuracy target (M7 real-data interpretation):**
  - Acceptance needs:
    - correct physical mode identity and acceptable MAC;
    - frequency agreement preferably within ~5 %. Up to ~10 % is acceptable for the intended engineering
      use when the modal shape is correct and there is no systematic branch mismatch.
  - The goal is useful effective material-property ranges, not metrology-grade constituent constants.
  - Not done:
    - properties are not optimised merely to reduce frequency error (for example from 4 % to 1 %);
    - a useful E_in range is not rejected for lacking sub-percent agreement;
    - identified constants are not reported with excessive numerical precision.
  - The 0.3 % M6.4 criterion is not this target. How the target maps onto the M5 verdict (Σ, pattern test)
    is an M7-entry decision. No M4 threshold or M5 rule is changed here.
- **Thickness context:** face-sheet thickness scatter is physical geometry for the later t_face nuisance,
  not an M6.4 range:
  - old nominal ~0.45 mm: local ~0.40–0.50 mm, mostly ~0.44–0.45 mm;
  - new nominal ~0.25 mm: local ~0.23–0.28 mm, mostly ~0.25 mm.
- **Execution:** M6.4a (zero Abaqus: envelope record, guarded screening path, tests) is authorised. The
  solves need a separate HUMAN Abaqus gate that names the exact manifest hash. M6 is not accepted; no M7.
Rationale / scope: gives M6.4 its approved range source and fixes the screening reading. The SPEC
criterion, geometry, registration, pairing, modal selection, M4 thresholds and M5 rules are unchanged.
Supersedes: D-055 in part. The M6.4 item "NEEDS_DECISION, no M6.4 FE jobs yet" is resolved by this
envelope. The 0.3 % criterion stands, and so do the t_face and interface items of D-055.

## D-067 — M6.4a accepted; HUMAN Abaqus gate M6.4b authorised for manifest 6d34179c…
Date: 2026-10-07 · Accepted by: SUPERVISOR / HUMAN · Source: SUPERVISOR "M6.4a — SUPERVISOR ACCEPT" with "HUMAN ABAQUS GATE — M6.4b" (2026-10-07); D-066
Decision:
- **M6.4a:** commit `403ff94` is accepted. The screening design, the guarded implementation, the frozen
  observation-mode set and `LITERATURE_INTERIM_SCREENING_ENVELOPE` are accepted.
- **HUMAN Abaqus gate M6.4b:** authorised for manifest `6d34179c787c8b0e1619864709290f2824e0435b98fb1ff2689e61d892da3922` only.
  - Scope: exactly 16 Abaqus solves and 16 Abaqus Python shape extractions (SP-02 and SP-13, 8 states each).
  - The archived baseline packs are reused. There are no baseline solves and no extra perturbations.
  - A retry that creates an additional scientific evaluation must be reported first.
  - Only the authorised constant changes, at its authorised endpoint. E_in/E1/E2, G12, ν12, geometry,
    thickness, core, registration, experimental data, pairing thresholds, modal-family rules, holdout rules
    and the M5 verdict policy do not change.
- **Tracking:** the existing FE-to-FE tracking (MAC ≥ 0.90, unique). No mode is identified by number
  alone, and none is substituted manually. A refusal is recorded as `NOT_CLASSIFIED_TRACKING_REFUSED`.
- **Interpretation (restated):**
  - The 0.3 % criterion is only the fixed-constant budget screening rule. A result ≥ 0.3 % is not a failed
    model; it means `INCLUDE_IN_UNCERTAINTY_BUDGET`.
  - The envelope is not a probability distribution, and the effects are not placed in Σ.
  - The real-data engineering target stays: correct mode identity / acceptable MAC; frequency preferably
    within ~5 %, up to ~10 % acceptable. Properties are not tuned for sub-percent agreement.
- **After the screening:** if every constant is classified, the evidence is complete and no tracking
  refusal is unresolved, the rescoped M6 gate is evaluated. The M7 propagation policy is not decided here.
  M7 stays NOT_STARTED. No merge to `main`.
Rationale / scope: records the acceptance and the HUMAN Abaqus authorisation. The execution and the result
are worker results pending SUPERVISOR review (EVIDENCE).
Supersedes: none

## D-068 — M6.4b accepted; M7-entry wiring of the active SP-02 / SP-13 inputs; M6 closure record
Date: 2026-10-08 · Accepted by: SUPERVISOR · Source: SUPERVISOR "M6 FINAL ACCEPTANCE PREPARATION + M7 ENTRY CLEANUP" (2026-10-08); D-062, D-064, D-065, D-066, D-067
Decision:
- **M6.4b:** the screening result (commit `345c06f`) is accepted. E3, ν13, ν23, G13 and G23 are
  `NEGLIGIBLE_FOR_BUDGET`; they stay fixed. M6.4 is CLOSED.
- **M7-entry wiring (active inputs only):**
  - SP-02: the active forward binding uses the physical registration fixture `SP02/bravo-1-physical`
    (new manifest `forward_models/SP02.physical.forward.json`, bound to the physical passport).
  - SP-13: a new active fixture `SP13/best-physical` (same source, modal set and FE as `SP13/best`, on the
    accepted physical registration `2eeeaa86…`). The physical passport names it, and the new manifest
    `forward_models/SP13.physical.forward.json` binds it.
  - **Kept:** all legacy registrations; the M0–M5 frozen baselines; historical provenance. `SP02/bravo-1`,
    `SP13/best`, the legacy passports, `SP02.forward.json` and `SP13.forward.json` are unchanged and still
    bind. Old M4 records are not rewritten.
- **M6 closure record:**
  - M6.1, M6.2 and M6.3 are `NOT_AVAILABLE_WITH_CURRENT_SETUP` (D-059);
  - M6.4 is CLOSED and the transverse constants are fixed;
  - Σ_setup stays provisional 0.3 %, flagged;
  - no new experiments;
  - the M6 gate is a PASS candidate pending final SUPERVISOR acceptance.
- **Not started:** M7 fitting, identification runs, Abaqus.
Rationale / scope: prepares the M7 inputs on the accepted physical registrations without touching the frozen
M0–M5 evidence. The wiring is a worker result pending SUPERVISOR review (EVIDENCE).
Supersedes: none

## D-069 — M7 opened: the accepted M7.1 design; RUN_A is the first executable campaign
Date: 2026-10-08 · Accepted by: SUPERVISOR · Source: SUPERVISOR "M7.1 DESIGN APPROVAL — HUMAN GATE PREPARATION" and "M7 START — RUN A CAMPAIGN ARCHITECTURE" (2026-10-08); SPEC §5, §7, §8, §12.3, §13; D-044, D-046, D-060, D-066, D-068
Decision:
- **Base:** M7 starts on branch `auto-id/m7` from `main` `9f5f63a` (M6 ACCEPTED, gate PASS).
- **Initial campaign:** `SP02/bravo-1-physical` + `SP13/best-physical` only. SP-10 and SP-01 are later
  extensions.
- **RUN_A** (the first executable campaign):
  - Fitted: E_in only (E1 = E2 = E_in); start 52 000 MPa.
  - Fixed: G12 = 4 500 MPa; ν12 = 0.05; E3, ν13, ν23, G13, G23 as accepted after M6.4.
  - Not fitted: t_face (nominal FE geometry; no 9-point prior), k_core (existing INP constants; no
    independent prior), k_int (OFF). No other fitted or nuisance parameter.
  - Numerical search bounds 26 000–104 000 MPa (solver only). Engineering plausibility 35–75 GPa (reporting
    only; never a prior).
- **Observations:**
  - Frozen independently per specimen on the active physical chains, and they must reproduce exactly:
    - SP-02: R1 (2 ↔ 8) FIT, R2 (4 ↔ 10) FIT, R3 (7 ↔ 13) HOLDOUT;
    - SP-13: R1 (4 ↔ 10) FIT, R2 (7 ↔ 13) HOLDOUT.
  - Otherwise STOP. Registration, pairing, thresholds and modal selection are not altered.
  - The M4.3 holdout policy is unchanged, and holdouts stay at specimen level.
  - Only the FIT residuals are combined across the campaign, after branch tracking. Modes are never mixed
    between specimens.
- **Σ:** Σ_setup = 0.3 %, PROVISIONAL; Σ_meas = NOT_AVAILABLE. NOT_AVAILABLE never becomes zero, and no
  PolyMAX measurement uncertainty is invented.
- **Reuse:**
  - p0 uses the archived baseline packs. The SP-13 ±5 % E points reuse the governed shape packs.
  - The SP-02 ±5 % E points reuse the archived CARBON-5A ODBs through extraction-only jobs, with every
    identity checked. That extraction needs the HUMAN Abaqus-Python gate.
- **Budget:** RUN_A has a hard limit of 16 new Abaqus solves and no automatic extension. On exhaustion the
  status is `SOLVE_BUDGET`.
- **Reporting:**
  - RUN_A may give `EFFECTIVE_MODEL_PARAMETER_ESTIMATE`. That is not automatically
    `IDENTIFIED_MATERIAL_PROPERTY`.
  - The M5 verdicts IDENTIFIED / WIDE / NOT_IDENTIFIABLE are unchanged. A useful effective estimate may
    coexist with a formal M5 NOT_IDENTIFIABLE.
  - Every real carbon result carries "not externally validated" (D-060).
  - The engineering target is correct mode identity and acceptable MAC; frequency agreement preferably
    ≤ ~5 %, up to ~10 % acceptable. It is kept separate from the M5 verdict. Properties are never tuned
    merely to turn a useful 5 % mismatch into 1 %.
- **RUN_B** (E_in + G12, `EFFECTIVE_MODEL_COMPENSATION_TEST`): diagnostic only. It needs its own later
  SUPERVISOR gate after RUN_A, and its G12 is never reported as an identified material property.
- **Implementation choices made in M7.1** (for SUPERVISOR review):
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
Rationale / scope: opens M7 with a governed, resumable two-specimen campaign. It reuses the accepted M4.5
tracker, the M4.6 pipeline and the M4.8 LM, and leaves M5 unweakened. No Abaqus has been run.
Supersedes: none

## D-070 — M7.1 accepted; HUMAN gate 1 (archived SP-02 extraction) authorised
Date: 2026-10-08 · Accepted by: SUPERVISOR / HUMAN · Source: SUPERVISOR "M7.1 ARCHITECTURE — SUPERVISOR ACCEPT. HUMAN GATE 1 ONLY: ARCHIVED SP-02 EXTRACTION" (2026-10-08); D-069
Decision:
- **M7.1:** commit `9c16324` is accepted as the RUN_A architecture basis.
- **D-069 implementation choices accepted:**
  - `RowSigma(measurement_sd=None)` means Σ_meas = NOT_AVAILABLE and never silently becomes zero;
  - identical physical modal families across specimens share one campaign family identity where
    appropriate;
  - the baseline MAC and accepted-observation guards stay mandatory;
  - M5 may use the reconstructed LM Jacobian without redundant FE evaluations;
  - family consistency may stay NOT_AVAILABLE at this first RUN_A checkpoint, so a green M5 verdict is not
    required for the engineering pipeline test.
- **Unchanged:** the formal M5 verdict semantics and the engineering target (correct mode identity /
  acceptable MAC; preferably ~5 %, up to ~10 %; no tuning toward sub-percent agreement for appearance).
- **HUMAN gate 1:** authorised for manifest `e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6`, archive-extraction step only.
  - Exactly 2 Abaqus Python extractions: `SP02_13363f977809dbff` (E 54 600 MPa, ODB `ba38cb69…`) and
    `SP02_84753f636064e192` (E 49 400 MPa, ODB `bae6a7c1…`, technical retry1 only).
  - The failed E_MINUS attempt stays excluded.
  - Not authorised: Abaqus solves, the LM RUN_A, RUN_B, any use of the 16-solve allowance, and automatic
    continuation into `run`.
Rationale / scope: records the acceptance and the HUMAN authorisation. The execution is a worker result
pending SUPERVISOR review (EVIDENCE).
Supersedes: none

## D-071 — HUMAN gate 2: RUN_A authorised
Date: 2026-10-08 · Accepted by: SUPERVISOR / HUMAN · Source: SUPERVISOR "M7 RUN A — HUMAN ABAQUS GATE AUTHORISED" (2026-10-08); D-069, D-070
Decision:
- **Gate 1:** commit `0837921` (archived SP-02 extraction) is accepted.
- **RUN_A:** authorised for manifest `e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6` and run identity `8ed03be3be86aa83877367ab505cf2d66ae711c6c9a2a7a4dc47ab6c499923a2`, RUN_A only.
  - Fit E_in only; G12 is fixed at 4 500 MPa.
  - Specimens `SP02/bravo-1-physical` and `SP13/best-physical`, with the accepted FIT / HOLDOUT rows
    unchanged.
  - At most 16 new Abaqus solves and 16 new extractions. No budget extension and no automatic scientific
    retry.
  - The archived baseline and ±5 % points are reused, not recomputed.
- **Not authorised:** RUN_B, G12 fitting, and any change to registration, pairing or holdouts.
- **Reporting:**
  - `EFFECTIVE_MODEL_PARAMETER_ESTIMATE` is allowed if supported;
  - `IDENTIFIED_MATERIAL_PROPERTY` only if M5 permits it;
  - every carbon result is "not externally validated";
  - the engineering interpretation keeps its targets: correct mode identity and acceptable MAC; preferably
    ~5 %, up to ~10 %; no tuning for appearance.
Rationale / scope: records the HUMAN Abaqus authorisation. The run and its result are worker results
pending SUPERVISOR review (EVIDENCE).
Supersedes: none

## D-072 — RUN_A accepted and closed; RUN_B prepared (archive reuse only)
Date: 2026-10-08 · Accepted by: SUPERVISOR · Source: SUPERVISOR "M7 RUN A — SUPERVISOR ACCEPTANCE. PREPARE RUN B, ARCHIVE REUSE ONLY." (2026-10-08); D-046, D-069, D-071
Decision:
- **RUN_A** (`60a83fa`) is accepted and CLOSED.
  - E_in,eff = 55.593 GPa, `EFFECTIVE_MODEL_PARAMETER_ESTIMATE`, not externally validated. The formal M5
    verdict stays NOT_IDENTIFIABLE.
  - 55.593 GPa is not an identified intrinsic material property.
  - RUN_A met the practical engineering target (correct mode identities; acceptable pair MAC; all governed
    FIT + HOLDOUT errors < 10 %; max 6.79 %) but not the formal M5 identification gate.
  - The remaining RUN_A solve budget is not spent.
- **RUN_B** (`EFFECTIVE_MODEL_COMPENSATION_TEST`) is prepared, not executed.
  - Fit E_in and G12 from the original governed start (52 000 / 4 500 MPa). Search bounds: E_in
    26 000–104 000, G12 2 250–9 000 MPa (solver only). E_in reference 35–75 GPa; G12 is diagnostic only.
  - Same frozen observations, holdouts, registration, pairing, family classification, thresholds, Σ_setup
    0.3 % PROVISIONAL and Σ_meas NOT_AVAILABLE (never zero).
  - G12 is never an identified material property (`BARE_PLATE_REQUIRED` / `NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED`).
  - The report gives Δ ln E_in and Δ ln G12 against RUN_A. The D-045 ln bands are descriptive only. Strong
    G12 movement together with a material E_in shift is recorded as parameter freedom absorbing model
    discrepancy, not as improved identification.
  - Hard ceiling of 24 new solves (not yet authorised). Every scientifically identical existing evaluation is
    reused.
  - This decision is the SUPERVISOR RUN_B gate in the campaign definition (`run_b_gate` D-072). Execution
    still needs the HUMAN Abaqus-Python gate (2 archive extractions) and then the HUMAN solve gate.
- **Implementation:** reuse entries may name a `pack_store` for a governed pack whose file lives in another
  run store; the size, SHA-256 and content pins are unchanged. The RUN_B report labels G12 a compensation
  diagnostic.
- **Not done:** no Abaqus, no Abaqus Python, no RUN_B LM, no RUN_B estimate.
Rationale / scope: closes RUN_A with its accepted interpretation and prepares the diagnostic without
executing it.
Supersedes: none

## D-073 — RUN_B HUMAN gate 1: archived SP-02 G12± extraction only
Date: 2026-10-08 · Accepted by: HUMAN · Source: HUMAN "M7 RUN B — HUMAN GATE 1 AUTHORISED. ARCHIVED SP-02 G12 EXTRACTION ONLY." (2026-10-08); D-072
Decision:
- The RUN_B preparation (D-072) is accepted as the basis for this gate.
- **Authorised:** exactly 2 Abaqus Python extractions of archived CARBON-5A ODBs for manifest
  `5fd0946a0c3f4e20562ba97068cdb5b94bf6d10ba789a3b2df20b457882034a1`:
  - `SP02_05239a3b56508244` (E_in 52 000, G12 4 725 MPa; ODB `d3b49b047517d155db88567c57dfb7dab4b83a81f09e7725886c646e2fa7de1a`);
  - `SP02_ade5dffa2fde3903` (E_in 52 000, G12 4 275 MPa; ODB `52f7b740d8b3fe736f6255d8ea1e14dd687e0b76b112bbd4c50f31dca52cba49`).
- **Not authorised:** any Abaqus solve, the RUN_B LM, fitting E_in or G12, reusing the RUN_A final point as a
  governed initial point, changes to M5 or scientific policy, automatic continuation into the solve gate.
- RUN_A stays CLOSED; its records, journals and provenance are unchanged.
- RUN_B solve execution requires a second explicit HUMAN authorisation.
Rationale / scope: records the HUMAN Abaqus-Python authorisation. The extraction result is a worker result
pending review (EVIDENCE).
Supersedes: none

## D-074 — RUN_B HUMAN solve gate (diagnostic only)
Date: 2026-10-08 · Accepted by: HUMAN · Source: HUMAN "M7 RUN B — HUMAN SOLVE GATE AUTHORISED." (2026-10-08); D-072, D-073
Decision:
- Gate 1 / D-073 (`4cc20cc`) is accepted.
- **Authorised:** execution of RUN_B only, for manifest `5fd0946a0c3f4e20562ba97068cdb5b94bf6d10ba789a3b2df20b457882034a1` and run identity `fb5234116c6e9413e4b070e901f97b8c6e210d535daefe15f0cdb5b9f8ad87f0`.
  - Label `EFFECTIVE_MODEL_COMPENSATION_TEST`; fit exactly E_in and G12 from 52 000 / 4 500 MPa (not from the
    RUN_A optimum); bounds 26 000–104 000 / 2 250–9 000 MPa.
  - Fixed inputs, observations, Σ, tracking thresholds and the M4.8/M4.9 LM unchanged; the five governed
    initial evaluations reused (0 solves).
  - At most 24 new solves (12 new campaign evaluations) and 24 new extractions; no extension, no automatic
    scientific retry, no repeat of the gate-1 extractions.
- **Claims:** RUN_B G12 is `COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY` (`BARE_PLATE_REQUIRED`,
  `NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED`); RUN_B E_in is diagnostic as well. The release candidate remains
  the model-calibrated effective E_in = 55.593 GPa, not externally validated, until the SUPERVISOR changes it.
- **Not authorised:** reopening RUN_A, another fit, adding t_face / k_core / k_int, spending unused budget
  after convergence, merging M7.
Rationale / scope: records the HUMAN Abaqus authorisation. The run and its result are worker results
pending SUPERVISOR review (EVIDENCE).
Supersedes: none

## D-075 — RUN_B accepted; M7 scientific campaign complete
Date: 2026-10-08 · Accepted by: SUPERVISOR · Source: SUPERVISOR "M7 RUN B — SUPERVISOR ACCEPTANCE AND M7 CLOSURE PREPARATION." (2026-10-08); D-072, D-074
Decision:
- **RUN_B** (`535141e`) is ACCEPTED, diagnostic only. Conclusion C is accepted: freeing G12 causes strong
  parameter compensation and materially shifts E_in (Δln E_in −0.0885, Δln G12 +0.4234). The improved absolute
  residuals of RUN_B are not improved material identification.
  - RUN_B G12 (6.8721 GPa) stays `COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY`, `BARE_PLATE_REQUIRED`,
    `NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED`; it never enters a recommended-material-property table. RUN_B
    E_in (50.8862 GPa) is diagnostic as well.
  - The specimen-specific family discrepancy is not removed by freeing G12: family (1,2) SP-02 − SP-13
    7.85 → 8.27 percentage points; family (0,3) holdouts
    5.63 → 5.33. RUN_B mainly shifts family means and redistributes
    residuals: MODEL_FORM / PARAMETER_COMPENSATION dependence.
- **RUN_A remains the engineering release candidate:** E_in,eff = 55.593 GPa,
  `EFFECTIVE_MODEL_PARAMETER_ESTIMATE`, not externally validated; not `IDENTIFIED_MATERIAL_PROPERTY`; formal M5
  NOT_IDENTIFIABLE. Practical engineering result: governed modal identities preserved; experimental-pair MAC
  acceptable (min 0.918); all FIT + HOLDOUT errors < 10 % (max
  6.79 %); E_in inside the engineering window; the intended
  engineering-use criterion is met. The RUN_A leave-one-family-out range 50.8–60.3 GPa
  may be reported only as `MODEL_DEPENDENCE_DIAGNOSTIC` (not a confidence interval, not a formal
  material-property uncertainty).
- **Reporting correction (M5 unchanged):** M5 takes model_form_robustness over the VALID leave-one-family-out
  cases only, so an incomplete set can show 0.0. The campaign report adds `model_form_robustness.status`:
  `AVAILABLE_COMPLETE_LOO` (every family case VALID, at least two; labelled `MODEL_DEPENDENCE_DIAGNOSTIC`),
  `UNAVAILABLE_INCOMPLETE_LOO` (any refused case or fewer than two valid cases; no number, no replacement
  value) or `NOT_EVALUATED`. RUN_A: `AVAILABLE_COMPLETE_LOO`; RUN_B: `UNAVAILABLE_INCOMPLETE_LOO`. M5 thresholds,
  algorithms, verdicts and records are unchanged; the accepted RUN_A / RUN_B result records are unchanged.
- **No further M7 FE work:** no further Abaqus execution in M7. The unused solve budgets (RUN_A 14 / 16,
  RUN_B 18 / 24) are abandoned intentionally. The M7 scientific campaign is complete.
- **Roadmap M7.2–M7.8** were not pursued as separate mini-steps; their questions are answered as far as M7
  goes by RUN_A + RUN_B (M7 GATE: one shared carbon vector does not explain the family, so no global material
  number is reported). Recorded as `NOT_PURSUED_IN_M7` for SUPERVISOR confirmation at stage acceptance.
- M8 is not started. M7 is not merged without HUMAN authorisation.
Rationale / scope: accepts RUN_B and closes the M7 campaign with its accepted interpretation.
Supersedes: none

## D-076 — External audit iteration 2: M7 scientific release withdrawn; M7 REWORK
Date: 2026-10-09 · Accepted by: SUPERVISOR · Source: SUPERVISOR "M7b-DIAG — AUDIT CORRECTIVE ITERATION, NO ABAQUS." and "AUDIT ITERATION 2 — M7b CORRECTIVE WORK. M8.1 IS PARKED, NOT REJECTED." (2026-10-09); external audit `Audit_AutoID_0f15db9_iteration2.docx`; supersedes the scientific release interpretation of D-069, D-072 and D-075
Decision:
- **Audit iteration 2 is accepted as corrective evidence** (K1–K3 CONFIRMED; disposition in
  `audit_corrections/AUDIT_ITERATION2_DISPOSITION.md`).
- **K1:** 55.593 GPa is withdrawn as a released common SP-02 / SP-13 parameter under SPEC v1.1 (§1 upper rule:
  M5 is NOT_IDENTIFIABLE). It remains, unchanged in the frozen records, as **HISTORICAL_RUN_A_OPTIMIZER_CANDIDATE**
  (diagnostic). It is not a release candidate, a recommended common family E, an identified material property or
  an approved common engineering parameter. No replacement number is authorised.
- **K2:** the SPEC §13 family-consistency test is required and is now implemented
  (`services/family_consistency.py`; χ² path when every SPEC §13 condition holds, parametric bootstrap on the
  linearised model, explicit `NOT_EVALUABLE_RANK_DEFICIENT` refusal). RUN_A fails it: Δχ² 746.27, Δdof 1, p_χ² 2.6e-164, bootstrap p 0.00025 (4000 samples, seed 20261009). RUN_B is
  `NOT_EVALUABLE_RANK_DEFICIENT`. Campaign verdicts use the computed result instead of the hard-coded
  NOT_AVAILABLE; a FAIL blocks IDENTIFIED, WIDE and every shared released value. M5 thresholds unchanged.
- **Corrected interpretation:** NO GLOBAL E_in VALUE IS RELEASED FOR THE SP-02 / SP-13 FAMILY UNDER SPEC v1.1.
- **Two distinct results (SUPERVISOR review 2026-10-09).** The SPEC §13 family-consistency result is **FAIL** and the
  formal output is **NO_GLOBAL_PARAMETER_VALUE**. That refusal is a valid scientific result (SPEC §1) and is what the
  M7 GATE requires ("if one shared carbon vector cannot explain the family, NO global material number is
  reported"); it is not a failed stage gate. The D-075 acceptance and its release rationale are superseded. M7 is
  `REWORK` while this correction is under SUPERVISOR review; the stage-gate closure (expected `PASS_BY_REFUSAL`) is a
  separate SUPERVISOR decision (expected D-077). The historical merge facts (PR #37, `0f15db9`; PR #38, `7a34ee6`)
  stand unchanged.
- **Audit dispositions:** K1–K3, V1–V8 and J1–J5 in `audit_corrections/AUDIT_ITERATION2_DISPOSITION.md`. V4 and the
  SPECIMEN_ENGINEERING_CALIBRATION class are SPEC v1.2 policy questions (deferred); V7 (SP10) needs a new FE model and
  a HUMAN Abaqus gate (deferred); J1 is deferred to M8.6; J2 / J3 / J4 are recorded technical debt or limitations;
  J5 is addressed by the `uncertainty_basis` reporting.
- **RUN_A and RUN_B frozen numerical records remain historical evidence** of what was computed; they are not
  rewritten. Corrective evidence is additive (`docs/auto_id/audit_corrections/`).
- **No new material property is claimed.** Per-specimen estimates are DIAGNOSTIC_ONLY / NOT_A_MATERIAL_PROPERTY /
  NOT_A_RELEASE_VALUE.
- **K3:** the CARBON-5G read-only INP audit is complete; known physical facts are recorded in additive governed
  measurement records beside the unchanged passports, with uncertainty NOT_AVAILABLE.
- **Reporting:** campaign report v2 separates `optimizer_candidate` from `formal_output`, and adds
  `family_consistency`, `excluded_mode_diagnostics` (best MAC ≥ 0.80, never fitted) and `per_specimen_agreement`
  (no threshold).
- **M8 is ON HOLD** pending corrective review: M8 `NOT_STARTED` / `ON_HOLD_FOR_M7_CORRECTIVE`. The M8.1 work on
  branch `auto-id/m8` (`193db8d`) is `PARKED_PENDING_M7_AUDIT_CORRECTION` — not rejected, not accepted, not merged.
- **SPEC v1.2, SPECIMEN_ENGINEERING_CALIBRATION and τ_mf remain HUMAN decisions;** none is implemented. SPEC v1.1 is
  unchanged.
Rationale / scope: corrects the scientific interpretation and the missing SPEC §13 analysis from frozen evidence
without Abaqus; superseding governance, not a rewrite of D-069–D-075.
Supersedes: the release interpretation of D-069, D-072 and D-075 (their text stays as history)

## D-077 — M7 corrective closure: M7 ACCEPTED, stage gate PASS by scientific refusal
Date: 2026-10-09 · Accepted by: SUPERVISOR · Source: SUPERVISOR "M7b CORRECTION — SUPERVISOR ACCEPTANCE, MERGE PR #39, THEN D-077 CLOSURE." (2026-10-09); D-076; PR #39 (merge `b9db2c1bc5c281d8f126ffe9f2abfec4dbd60e2c`)
Decision:
- **The M7b corrective implementation is accepted** (PR #39, reviewed head `42d8f2f`, merged to `main` as
  `b9db2c1`). External audit iteration 2 findings K1–K3 are resolved; the V1–V8 and J1–J5 dispositions are
  accepted as recorded in `audit_corrections/AUDIT_ITERATION2_DISPOSITION.md`.
- **Scientific results (unchanged):**
  - RUN_A family consistency (SPEC §13): **FAIL** — Δχ² ≈ 746.27, Δdof 1, p_χ² ≈ 2.6e-164, bootstrap p = 1/4001;
  - RUN_B family consistency: **NOT_EVALUABLE_RANK_DEFICIENT**;
  - formal SP-02 / SP-13 family output under SPEC v1.1: **NO_GLOBAL_PARAMETER_VALUE**.
- **55.593 GPa remains historical optimiser evidence only** (HISTORICAL_RUN_A_OPTIMIZER_CANDIDATE): not a release
  parameter, not an identified material property, not a recommended common family E, not an approved engineering
  family constant. D-076 supersedes the release interpretation of D-075; D-075 and D-076 stay as history.
- **No new material-property number is issued.**
- **M7 = ACCEPTED; M7 stage gate = PASS, semantics PASS_BY_REFUSAL.** The family-consistency test itself stays
  FAIL. The M7 GATE ("if one shared carbon vector cannot explain the family, NO global material number is
  reported") is satisfied because the program withholds the global value; this is a successful scientific refusal
  (SPEC §1), not a green material identification.
- **Merges:** PR #37 (`0f15db9`) and PR #38 (`7a34ee6`) stay historical facts; PR #39 is the M7 corrective merge, not
  a new stage.
- **SPEC v1.1 is unchanged.** SPEC v1.2, τ_mf and SPECIMEN_ENGINEERING_CALIBRATION remain unresolved future
  scientific-policy decisions.
- **No Abaqus was run in M7b** (0 solves, 0 Abaqus Python extractions).
- **M8 stays NOT_STARTED.** The M8.1 work on `auto-id/m8` (`193db8d`) was not part of M7b and is
  `PARKED_PENDING_POST_M7_DECISION` (not rebased, not merged, M8.2 not started).
Rationale / scope: closes M7 with the corrected interpretation; no scientific result or code changes.
Supersedes: the interim REWORK / gate-pending state of D-076

## D-078 — SPEC v1.2 accepted as the normative Auto-ID scientific contract
Date: 2026-10-09 · Accepted by: SUPERVISOR · Source: SUPERVISOR "SPEC v1.2 — NORMATIVE ACCEPTANCE AND CLOSURE." (2026-10-09); PR #41 (reviewed head `62903ef899122de9a3585d6cf6551d03442b97e5`, merge `edb3070d2ed5b385f7152b3041ca3e297bdc8423`)
Decision:
- **SPEC v1.2 is accepted as normative.** The accepted policy is the PR #41 reviewed head `62903ef`, merged to `main`
  as `edb3070` (merged tree identical to the reviewed head). `SPEC_V1_2.md` is now the governing Auto-ID scientific
  contract: SPEC v1.1 as amended by SPEC v1.2; unamended v1.1 clauses remain in force.
- **SPEC v1.1 remains archived and immutable** (`SPEC_V1_1.md`, unchanged). The policy draft, review and options stay
  as historical evidence, marked SUPERSEDED_BY_NORMATIVE_SPEC_V1_2.
- **Two-question upper rule accepted:** MATERIAL_IDENTIFICATION and SPECIMEN_ENGINEERING_CALIBRATION, selected before
  execution and part of the campaign / run identity. **No automatic fallback:** a MATERIAL_IDENTIFICATION run that
  ends NOT_IDENTIFIABLE or NO_GLOBAL_PARAMETER_VALUE emits no calibration number.
- **τ_mf maximum 0.02** in |Δ ln f| accepted: one campaign-level value, declared before execution, identity / hash
  bound; smaller allowed, larger only by a future specification revision; never per mode, family or parameter; never
  selected after fit results. Holdout |Δ ln f| ≤ max(3σ, τ_mf); residual-family magnitude max(2σ, τ_mf). τ_mf never
  enters Σ, covariance, Φ, whitening, statistical_sd, birge_adjusted_sd, model_form_robustness,
  conservative_uncertainty or §13. Passing a τ_mf gate does not establish parameter precision.
- **§13 remains unchanged and τ_mf-free:** FAIL → NO_GLOBAL_PARAMETER_VALUE; NOT_EVALUABLE → no global family value;
  τ_mf cannot rescue a FAIL.
- **Specimen calibration class accepted:** SPECIMEN_ENGINEERING_CALIBRATION with NOT_A_MATERIAL_PROPERTY and
  NOT_TRANSFERABLE_WITHOUT_VALIDATION; bound to physical specimen, test run, forward model, INP SHA-256,
  registration, campaign / run and declared τ_mf; never in a material-property field; never written through the
  material-property writer (optional separate fragment only, with a distinct material name and warnings).
- **Calibration gates accepted:** observability (≥ k + 1 FIT families, full rank at the M5 RCOND, complete
  leave-one-FIT-family-out, ≥ 1 HOLDOUT family; k = 1: 2 FIT + 1 HOLDOUT; a cluster counts once); non-degradation
  (max and RMS not worse than the baseline, every governed row ≤ 8 %); precision (conservative_uncertainty =
  max(birge_adjusted_sd, 0.5 · width(model_form_robustness)) ≤ 0.08 in ln p, birge_adjusted_sd available and
  model_form_robustness AVAILABLE_COMPLETE_LOO, otherwise REFUSED with no calibration value; an optimiser candidate only
  as DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE). With incomplete covariance,
  UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE remains visible.
- **Historical RUN_A / RUN_B are not reinterpreted:** RUN_A stays NO_GLOBAL_PARAMETER_VALUE, RUN_B diagnostic only;
  the v1.1 records are immutable and may later be used only as RETROSPECTIVE_DIAGNOSTIC_ONLY. An accepted v1.2
  calibration needs a new v1.2 campaign / run identity with question B and τ_mf declared before that re-analysis.
- **Production implementation is NOT part of D-078.** Implementation status: POLICY_ACCEPTED,
  IMPLEMENTATION_NOT_STARTED; production code does not yet enforce the v1.2 additions. Implementation track
  V12-I1 … V12-I6 (ROADMAP) precedes any SP10 / new FE work; it is not started.
- **No Abaqus was run** for the SPEC v1.2 policy work. M8 stays NOT_STARTED; `auto-id/m8` (`193db8d`) stays parked.
Rationale / scope: closes external audit finding V4 at the policy level (model-form tolerance and specimen calibration
frozen before any new FE result); no scientific result, record or code changes.
Supersedes: none (amends SPEC v1.1 by SPEC v1.2; D-077's "SPEC v1.2 unresolved" note is resolved)

## D-079 — M8 Read-Only Scope Acceptance
Date: 2026-10-10 · Accepted by: SUPERVISOR · Source: SUPERVISOR "FINAL M8 SCOPE DECISION." (2026-10-10) and "RELEASE CHECKPOINT GOVERNANCE CLEANUP"; PR #59 (reviewed head `f31510d87b1bf7d7c774ddba0f0ae074d88be27f`, merge `149debc3172cb4adb3ba6fcc48635b770340783e`)
Decision:
- **M8.1–M8.8 are ACCEPTED** (PRs #51–#58, each merged with SUPERVISOR authorisation), and the final M8 integration
  review is ACCEPTED (PR #59).
- **Accepted scope: `READ_ONLY_EXISTING_JOURNALLED_RUNS`** — campaign preparation, explicit stored-run selection, verified progress, evaluation
  with the shared SPEC v1.2 backend, scientific verdict, recorded uncertainty, governed Engineering Constants preview
  and safe verified JSON export of an existing journalled run.
- **Original M8 GATE: NOT_MET.** The path NEW specimen folder → governed campaign → new journalled scientific run →
  new result cannot be completed in the GUI. The limitation is acknowledged; it is not waived and not marked PASS.
- **M8 stage status: IN_PROGRESS** (original gate still open). M8 is not ACCEPTED as a whole.
- **Production execution: NOT_AUTHORISED.** Production calibration execution stays BLOCKED / NOT_AUTHORISED
  (`CampaignDefinition.require_executable` unchanged); no authorisation for real Abaqus execution, new FE solves, LM
  execution, computational resume, SP10 or t_face. Further work toward the original M8 GATE requires separate explicit
  authorisation.
- `auto-id/m8` (`193db8d`) stays PARKED (historical prototype, untouched).
Rationale / scope: records the SUPERVISOR scope decision as a decision entry; no scientific result, record, threshold,
SPEC or code changes.
Supersedes: the "M8 stays NOT_STARTED" / "M8 ON HOLD" / "`auto-id/m8` parked pending a decision" statements of D-076,
D-077 and D-078 as the current M8 state (those entries remain unchanged as history).
