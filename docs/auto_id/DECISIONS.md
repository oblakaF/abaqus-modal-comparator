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
