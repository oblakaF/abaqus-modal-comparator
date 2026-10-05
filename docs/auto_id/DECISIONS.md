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
