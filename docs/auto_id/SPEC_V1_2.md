# Auto-ID specification v1.2 — Governing Scientific Specification

| Item | Value |
|---|---|
| Version | 1.2 |
| Status | **NORMATIVE.** This Markdown file is the canonical Auto-ID scientific contract for implementation. |
| Accepted | SUPERVISOR, 2026-10-09 |
| Decision | D-078 |
| Normative predecessor | [SPEC_V1_1.md](SPEC_V1_1.md) (archived and immutable) |
| Scientific origin | External audit iteration 2 (finding V4 and the related V1 / V3 / V5 / V6 / J1 / J3 / J5 dispositions), D-076, D-077 and the accepted SPEC v1.2 policy freeze (PR #41, reviewed head `62903ef899122de9a3585d6cf6551d03442b97e5`, merged to `main` as `edb3070d2ed5b385f7152b3041ca3e297bdc8423`) |
| Review record | [SPEC_V1_2_POLICY_REVIEW.md](SPEC_V1_2_POLICY_REVIEW.md); machine-readable policy [SPEC_V1_2_POLICY_OPTIONS.json](SPEC_V1_2_POLICY_OPTIONS.json) |
| Implementation status | POLICY_ACCEPTED, IMPLEMENTATION_NOT_STARTED (production code does not yet enforce the v1.2 additions; track V12-I1 … V12-I6 in [ROADMAP.md](ROADMAP.md)) |

**Scope.** SPEC v1.2 is SPEC v1.1 as amended by this document. Where a section below amends, replaces or adds a
clause, this document governs. Every SPEC v1.1 clause that is not amended here remains in force unchanged as part of
v1.2. SPEC_V1_1.md itself is kept archived and immutable.

Normative keywords: **MUST**, **MUST NOT**, **MAY**.

**Freeze rule.** τ_mf and the specimen-calibration rules are declared here **before** any new FE calculation (SP10,
t_face sensitivity or a re-run of M7). No value was chosen from, or evaluated on, the historical RUN_A / RUN_B
residuals.

---

## 1. Amended §1 — Upper rule (v1.2 replaces the v1.1 wording)

v1.1 §1 says that no parameter, threshold, override, GUI option or operating mode may turn a scientific refusal into a
numerical result. v1.2 keeps that protection and **amends** the rule, because it adds a second, separately declared
question. The amended rule:

> **§1 Upper rule (v1.2).** Auto-ID answers two separate questions, and a run declares before execution which one it
> asks.
>
> **A. Material identification.** Auto-ID outputs a material-property value only when the material-identification
> evidence supports that parameter at the declared precision. Refusal to output a number is a valid and successful
> scientific result. No parameter, threshold, hidden override, GUI option or operating mode may turn a
> material-identification refusal into a number.
>
> **B. Specimen / FE-model calibration.** A separately declared `SPECIMEN_ENGINEERING_CALIBRATION` may output a
> model-specific calibration parameter only when that calibration question was selected before execution, is part of
> the run / campaign identity, and every calibration-specific gate passes. A calibration result is never a material
> property.
>
> **No automatic fallback.** A material-property refusal must never be relabelled or automatically converted into a
> calibration result. A run started as MATERIAL_IDENTIFICATION that ends NOT_IDENTIFIABLE (or NO_GLOBAL_PARAMETER_VALUE)
> emits no calibration number. When a calibration run is executed, its material verdict is still computed and shown
> separately, first, and unchanged.
>
> Every other clause of this specification is subordinate to this rule.

## 2. Principles kept unchanged from v1.1

1. Refusal of a material-property value remains a valid scientific result (§1 A).
2. No GUI option, mode or override may bypass a refusal, of either question.
3. MAC stays out of the optimisation objective; it is used only for mode and branch identity (§8, §12).
4. Model-form discrepancy stays **out of Σ** (§7, §14).
5. Σ_meas NOT_AVAILABLE never becomes zero and is never invented.
6. Family consistency (§13) remains mandatory for any shared / global parameter.
7. M5 practical-rank and identifiability refusals remain hard blocks without override (§10).
8. The G12 material-property rules remain unchanged (§5.1).

## 3. New §9a — Model-form tolerance τ_mf

**Definition.** τ_mf is a model-form **acceptance tolerance in frequency space only**, on |Δ ln f|, for
model-versus-experiment residual diagnostics (holdouts and the family-pattern magnitude).

**Rule.**

- τ_mf ≤ **0.02** (2 % in |Δ ln f|) is the v1.2 specification maximum.
- One campaign-level value, declared **before execution** and bound into the campaign / run identity hash.
- A campaign may declare a smaller value; a larger one needs a new specification revision.
- Not per mode, not per family, not per parameter, and never selected after seeing a fit result.
- A campaign that declares no τ_mf is evaluated with the v1.1 σ-only rules.

**τ_mf is not:** a measurement uncertainty; a component of Σ or of any covariance matrix; a term of Φ; a whitening
scale; an inflation of statistical_sd, birge_adjusted_sd or the conservative envelope; an input to §13; a parameter
uncertainty or a calibration uncertainty.

**Rationale.**

- τ_mf is a model-form acceptance tolerance in frequency space only;
- 2 % is deliberately conservative relative to the project's desired few-percent model agreement (preferably within
  ~5 %, up to ~10 %; D-066, D-069);
- it is fixed before any new FE result;
- it is stricter than the 3 % alternative;
- a single campaign-level value avoids family-specific tuning freedom.

**No conversion to parameter uncertainty.** Parameter uncertainty remains governed separately by M5 (§9, §10). No
mathematical conversion from τ_mf to a parameter uncertainty is made or used: a frequency discrepancy of τ can
correspond to a parameter change of at least about 2τ for a stiffness parameter (|d ln f / d ln E| ≤ 0.5), and much more
when the sensitivity is lower, so it cannot bound a parameter.

## 4. Amended §12.3 / S7 — Holdout and family-pattern magnitude

- **Holdout:** passes when `|Δ ln f_holdout| ≤ max(3σ, τ_mf)` (σ = the row's Σ standard deviation).
- **Family pattern:** a family is *systematic* when it has at least two members, all of the same sign, and every
  member has `|Δ ln f| > max(2σ, τ_mf)`.

τ_mf is never put into Σ, never into Φ, never used to whiten, never added to statistical_sd or to a covariance matrix.

**Passing a τ_mf residual gate does not itself establish parameter precision.** A parameter verdict still requires
every M5 uncertainty, rank and model-form-robustness requirement. Holdout selection by physical family is unchanged;
holdouts are never fitted. Birge scaling applies only when the pattern test passes.

## 5. §13 — Family consistency, unchanged and τ_mf-free

SPEC §13 is unchanged and completely independent of τ_mf. τ_mf does not enter the Σ used by §13, Δχ², the bootstrap,
the p-values or the shared / separate comparison.

**τ_mf can never convert family_consistency FAIL into PASS.** A family that fails §13 gives
NO_GLOBAL_PARAMETER_VALUE, whatever τ_mf is. §13 not evaluable (rank-deficient separate fits) gives no family value
either. Implementation must guard this with tests.

## 6. New §3a — SPECIMEN_ENGINEERING_CALIBRATION

**Purpose.** A model-specific calibration value for **one physical specimen**, answering question B of §1: which
effective constant makes this governed FE model of this specimen reproduce this specimen's governed modes.

**Declaration.** The calibration intent is declared before execution in the campaign / run definition and is part of
its identity, together with τ_mf. There is no automatic fallback from a material-identification refusal (§1).

**Mandatory labels:** `SPECIMEN_ENGINEERING_CALIBRATION`, `NOT_A_MATERIAL_PROPERTY`,
`NOT_TRANSFERABLE_WITHOUT_VALIDATION`.

**Mandatory identities:** physical specimen; test run; forward model (manifest hash); INP SHA-256; registration;
campaign / run identity; the τ_mf used.

**Never** in a material-property result field, table or block.

**Gates (all required; no manual override, no post-hoc mode substitution, no lowered MAC):**

1. one physical specimen; frozen governed observations only;
2. preserved pair identities (strict baseline pairs MAC ≥ 0.80) and FE-to-FE branch tracking (MAC ≥ 0.90); no branch
   or pairing loss;
3. no active parameter bound;
4. adequate practical rank (M5 full rank);
5. minimum observability (§8);
6. holdouts within `max(3σ, τ_mf)` and no systematic family (§4);
7. non-degradation (§7);
8. registration not limited, no peak-derived input;
9. **calibration precision gate:** `conservative_uncertainty ≤ 0.08` (below);
10. complete reporting: full FIT and HOLDOUT residual table, excluded high-MAC diagnostic modes, uncertainty basis.

**Calibration precision gate (mandatory).** A specimen calibration is a numerical scientific output under §1 B, so the
evidence must support it at a declared precision. Using the M5 conservative-envelope concept, per calibrated parameter
in ln p (as M5):

    conservative_uncertainty = max(birge_adjusted_sd, 0.5 * width(model_form_robustness))
    calibration precision gate: conservative_uncertainty ≤ 0.08

where width(model_form_robustness) = max_shift_ln − min_shift_ln over the complete leave-one-FIT-family-out cases.

- `birge_adjusted_sd` must be available (the pattern test passed); otherwise the calibration is **REFUSED**;
- `model_form_robustness` must be `AVAILABLE_COMPLETE_LOO`; otherwise the calibration is **REFUSED**;
- `conservative_uncertainty > 0.08` → the calibration is **REFUSED**;
- 0.08 is the hard maximum precision envelope of this calibration class. It is a different quantity from the 8 %
  per-row frequency ceiling of the non-degradation rule (§7);
- a calibration that passes is **never** labelled IDENTIFIED or WIDE; its output class stays
  `SPECIMEN_ENGINEERING_CALIBRATION`;
- τ_mf is **not** a component of the envelope; it is never added to `statistical_sd`, `birge_adjusted_sd`,
  `model_form_robustness` or `conservative_uncertainty`.

**The precision gate does not make incomplete covariance complete.** While Σ_meas is NOT_AVAILABLE or any covariance
component is PROVISIONAL, the record keeps `UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE` and states that the
≤ 0.08 result is conditional on the available covariance components. Σ_meas is never invented, no uncertainty is
inflated or shrunk, τ_mf is never added to an uncertainty, and the calibration uncertainty is never called a complete
experimental uncertainty.

**Refused calibration.** If any gate fails — in particular if `conservative_uncertainty` is undefined or exceeds
0.08 — **no SPECIMEN_ENGINEERING_CALIBRATION value is released**. An optimiser candidate may remain visible only as
diagnostic evidence, labelled `DIAGNOSTIC_OPTIMIZER_CANDIDATE` and `NOT_A_RELEASE_VALUE`, never in a calibration-value
or material-property field and never written to a calibration fragment. There is no fallback (§1).

**Uncertainty reporting.** The calibration record reports, separately: the statistical uncertainty with its covariance
basis; the Birge-adjusted uncertainty only when valid; the model-form robustness; the conservative_uncertainty of the
precision gate; the missing Σ components; and τ_mf as an **acceptance tolerance** (never as uncertainty). With Σ_meas
NOT_AVAILABLE it states `UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE` and never calls the result complete
experimental uncertainty. A calibration that passes every gate is a model-calibration output; it must not masquerade as
a statistically complete material-property estimate.

## 7. New rule — Per-specimen non-degradation

For the same governed FIT + HOLDOUT rows of **one** specimen, comparing the candidate with the governed baseline FE
state:

1. `max_i |Δ ln f_i(candidate)| ≤ max_i |Δ ln f_i(baseline)|`, **and**
2. `RMS_i Δ ln f_i(candidate) ≤ RMS_i Δ ln f_i(baseline)`, **and**
3. every governed FIT / HOLDOUT row satisfies `|relative frequency error| ≤ 8 %` (the hard practical ceiling of this
   calibration class).

The max condition prevents sacrificing the worst mode; the RMS condition prevents worsening many modes to improve the
worst one; the 8 % ceiling is separate from the τ_mf holdout / model-form gates. Individual rows are not required to
improve versus the baseline (that would make a multi-mode optimum unnecessarily brittle). Campaign-global maxima are
never used for this decision.

## 8. New rule — Minimum observability for a specimen calibration

For k fitted parameters:

- at least **k + 1 distinct FIT modal families** (M4.3 family keys);
- a full-rank system at the M5 RCOND;
- complete leave-one-FIT-family-out validity (every M5.7 case VALID — reporting status AVAILABLE_COMPLETE_LOO);
- at least **one HOLDOUT family** distinct from every FIT family.

For **k = 1** the minimum is **2 independent FIT families + 1 independent HOLDOUT family**. A single
torsion-sensitive mixed mode is never sufficient by itself. A confirmed cluster counts as **one** governed family
observation, not several. The rule names no specimen.

## 9. Amended S8 — Engineering Constants output

| Output | `*Elastic, type=ENGINEERING CONSTANTS` |
|---|---|
| IDENTIFIED / WIDE material property | existing output rules (§5, §5.1, S8) |
| NOT_IDENTIFIABLE | no material-property block |
| NO_GLOBAL_PARAMETER_VALUE | no material-property block |
| SPECIMEN_ENGINEERING_CALIBRATION | **never** through the ordinary material-property writer. Optional separate calibration INP fragment only with a distinct material name, explicit comment warnings, the specimen and FE model named, `NOT_A_MATERIAL_PROPERTY` and `NOT_TRANSFERABLE_WITHOUT_VALIDATION` stated |

## 10. Amended §9 — Uncertainty wording (mandatory)

Every reported statistical_sd / birge_adjusted_sd states its covariance basis. While any Σ component is
NOT_AVAILABLE or PROVISIONAL, the report says `UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE` (campaign reports
already carry `uncertainty_basis` = `CONDITIONAL_ON_AVAILABLE_COVARIANCE`, D-076) and names the components. No value
is enlarged and Σ_meas is never invented.

## 11. Historical data (no retroactive reinterpretation)

- The historical v1.1 records stay unchanged: RUN_A family = NO_GLOBAL_PARAMETER_VALUE; RUN_B = diagnostic only.
- After v1.2 is accepted, historical evidence may be used only as `RETROSPECTIVE_DIAGNOSTIC_ONLY`; it is never
  silently upgraded into an accepted v1.2 calibration.
- An accepted v1.2 calibration needs a **new v1.2 campaign / run identity** with the calibration question and τ_mf
  declared before that run or re-analysis starts. It may reuse content-addressed archived FE states where
  scientifically and provenance-wise valid; the historical RUN_A / RUN_B records themselves stay unchanged.

## 12. Diagnostics and data-quality conclusions

- **Scan coverage (V2):** data quality / experiment design, never a numerical tolerance; fixed experimentally.
- **High-MAC modes excluded by the frequency gate (V3):** stay visible as diagnostic rows; never fitted.
- **Cross-specimen splits (V5):** handled by §13.
- **Cluster discovery (J3):** should later inspect the full experimental / FE neighbourhood; accepted clusters still
  obey the frozen governed rules.

## 13. Implementation scope (implementation track V12-I1 … V12-I6; not yet implemented)

Campaign definition: declared question (material identification or specimen calibration) and τ_mf, both
identity-bound. M5 holdout and pattern magnitude bounds max(kσ, τ_mf) only when τ_mf is declared. A calibration gate
(including the conservative_uncertainty ≤ 0.08 precision gate) and a separate calibration record / fragment writer. No change to Σ, Φ, §13 or the rank rules.
