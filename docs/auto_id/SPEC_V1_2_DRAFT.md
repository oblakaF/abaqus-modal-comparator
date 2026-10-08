# Auto-ID specification v1.2 — DRAFT (amendments to v1.1)

| | |
|---|---|
| **Status** | **PROPOSED — NOT NORMATIVE — AWAITING SUPERVISOR ACCEPTANCE** |
| **Normative specification** | `SPEC_V1_1.md` (unchanged). Until a SUPERVISOR decision accepts this draft, every rule below is a proposal only and no code applies it |
| **Origin** | External audit iteration 2, finding V4 (a SPEC v1.1 policy gap), and the related V1 / V3 / V5 / V6 / J1 / J3 / J5 dispositions (D-076, D-077) |
| **Branch** | `auto-id/spec-v1.2-policy` from `main` `9bff6c79ee149e9309c3e3697cb96fff4e937c68` |
| **Review record** | `SPEC_V1_2_POLICY_REVIEW.md`; machine-readable options in `SPEC_V1_2_POLICY_OPTIONS.json` |

**Freeze rule.** The model-form tolerance and the specimen-calibration rules are declared here **before** any new
FE calculation (SP10, t_face sensitivity or a re-run of M7). No candidate value was chosen from, or evaluated on,
the historical RUN_A / RUN_B residuals.

**No retroactive reinterpretation.** If v1.2 is accepted, it does not automatically apply to historical results. Under
v1.1 the SP-02 / SP-13 family stays at NO_GLOBAL_PARAMETER_VALUE and RUN_B stays diagnostic only. Whether historical
data may be re-analysed under v1.2 is a separate HUMAN decision.

---

## 0. Principles kept unchanged from v1.1

1. Refusal to issue a value is a valid and successful scientific result (§1, upper rule).
2. No GUI option, operating mode, parameter or override may turn a scientific refusal into a number.
3. MAC stays out of the optimisation objective; it is used only for mode and branch identity (§8, §12).
4. Model-form discrepancy stays **out of Σ** (§7, §14).
5. Σ_meas NOT_AVAILABLE never becomes zero and is never invented.
6. Family consistency (§13) remains mandatory for any shared / global parameter.
7. M5 practical-rank and identifiability refusals remain hard blocks without override (§10).
8. The G12 material-property rules remain unchanged (§5.1; bare plate or a complete sandwich path required).

## 1. New §9a — Model-form tolerance τ_mf

**Definition.** τ_mf is a declared **acceptance tolerance on |Δ ln f|** for model-versus-experiment residual
*diagnostics* (holdouts and the family pattern test). It expresses how much frequency disagreement the governed FE
model is allowed to show as model form without that alone blocking a result.

**τ_mf is not:**

- a measurement uncertainty, and not a component of Σ;
- a term in the objective Φ (§8) or in the whitening of r;
- an inflation of statistical_sd, birge_adjusted_sd or the conservative envelope (§9);
- an input to the family-consistency test (§13) — see §4 below;
- a per-mode, per-family or per-parameter knob.

**Declaration.** Every future campaign definition declares τ_mf **before execution**. The value is part of the
campaign identity / hash. A campaign that does not declare it is evaluated with the v1.1 rules (σ-only).

**Value.** The proposed v1.2 rule is **τ_mf = 0.02 (2 % in ln f), fixed by the specification** (Option A in the
policy review). A campaign may declare a smaller τ_mf (stricter) but not a larger one without a specification change.
Options B (0.03) and C (family-specific) are analysed and not recommended (`SPEC_V1_2_POLICY_REVIEW.md` §2).

**Rationale for Option A.** The project's engineering target is agreement preferably within ~5 % and up to ~10 %
(D-066, D-069); IDENTIFIED needs a conservative uncertainty ≤ 5 % (§3). Because d ln f / d ln E ≤ 0.5 for any
stiffness-proportional parameter (f ∝ √stiffness), a frequency tolerance τ corresponds to at least 2τ in ln E: 2 % gives
≥ 4 %, inside the IDENTIFIED threshold, whereas 3 % gives ≥ 6 %, beyond it. 2 % is also well inside half of the
preferred engineering target, a common realism scale for calibrated sandwich FE models on their bending families,
simpler than any family-specific scheme, and the smallest freedom that still lifts the σ-only bounds of V4.

## 2. Amended §12.3 — Holdout acceptance

v1.1: a holdout fails when |r| > 3, i.e. |Δ ln f| > 3σ (σ = the holdout row's own Σ standard deviation).

v1.2 (proposed): a holdout passes when

```
|Δ ln f_holdout| ≤ max(3σ, τ_mf)
```

With Σ_setup 0.3 % and Σ_meas NOT_AVAILABLE, 3σ = 0.9 %, so the τ_mf = 2 % bound applies. Holdout selection by
physical modal family (§12.3) is unchanged. Holdouts are never fitted.

## 3. Amended §9 / S7 — Residual family-pattern test

v1.1: a modal family is *systematic* when it has at least two members, all of the same sign, each with |r| > 2
(|Δ ln f| > 2σ).

v1.2 (proposed): a family is *systematic* when it has at least two members, all of the same sign, and each with

```
|Δ ln f| > max(2σ, τ_mf)
```

Birge scaling (§9) still applies only when the pattern test passes. The single-system pattern test keeps its
v1.1 semantics otherwise (same-sign rule within one system). Cross-specimen splits are the job of §13, not of this
test (§4).

## 4. §13 — Family consistency stays separate (explicit)

- Family consistency remains based on the **declared statistical observation model** (Σ only), the χ²(Δdof) path
  when its conditions hold and the parametric bootstrap on the linearised model otherwise; rejection at p < 0.01.
- **τ_mf does not enter §13.** It is not added to Σ, not used to rescale Δχ² and not used to accept a family whose
  specimens demand different shared values.
- **τ_mf can never convert family_consistency FAIL into PASS.** If the specimens of a family demand significantly
  different shared parameter values, the shared family value is refused (NO_GLOBAL_PARAMETER_VALUE), whatever τ_mf is.
- §13 not evaluable (rank-deficient separate fits) produces no family value either.

## 5. New §3a — Output class SPECIMEN_ENGINEERING_CALIBRATION (draft; not implemented)

**Purpose.** A model-specific calibration value for **one physical specimen** when a global material-property claim
is scientifically refused. It answers "which effective constant makes *this* governed FE model of *this* specimen
reproduce *this* specimen's governed modes", nothing more.

**Relation to the upper rule (§1) — the critical point of this class.** Audit finding K1 was exactly a refusal
turned into a released number. A specimen calibration must therefore never *replace* or *soften* a refusal. The
material-property verdict (IDENTIFIED / WIDE / NOT_IDENTIFIABLE, and NO_GLOBAL_PARAMETER_VALUE for a family) is
computed and shown unchanged, first; the calibration answers a different, narrower question in a separate output
with its own refusal conditions. It never appears in a material-property field, table or block. If this separation
cannot be guaranteed in an interface, the class is not offered there. Whether this narrower question is acceptable
at all under §1 is the central SUPERVISOR decision on this draft.

**It is not** IDENTIFIED, WIDE, a material property, a family property or a transferable lamina constant. Every
output carries:

- label `SPECIMEN_ENGINEERING_CALIBRATION`;
- qualifiers `NOT_A_MATERIAL_PROPERTY` and `NOT_TRANSFERABLE_WITHOUT_VALIDATION`;
- the exact governed FE model identity (forward manifest, INP SHA-256, passport hash) and specimen / test-run identity.

**Conditions (all required):**

1. one specimen only; the fit uses only that specimen's governed rows;
2. mode identities preserved (strict baseline pairs MAC ≥ 0.80; FE-to-FE tracking MAC ≥ 0.90), no branch or pairing
   loss, no manual substitution;
3. no parameter at a numerical search bound;
4. practical identifiability adequate for that specimen and model. Only two things differ from a material-property
   verdict: family consistency (§13) does not apply to one specimen, and holdouts / pattern use the v1.2 τ_mf bounds.
   Every other M5 refusal still blocks the calibration: rank deficiency, branch or pairing loss, registration-limited,
   peak-derived input, a systematic pattern under the v1.2 rule, a holdout outside max(3σ, τ_mf), and an unavailable
   birge_adjusted_sd (pattern failed);
5. minimum observability (§7 below);
6. τ_mf declared and fixed before the fit (campaign identity);
7. every holdout within max(3σ, τ_mf) (§2); no systematic family under the v1.2 pattern rule (§3);
8. non-degradation (§6 below);
9. conservative uncertainty ≤ 8 % (the WIDE ceiling of §3), reported with its basis (§9);
10. the full residual table (FIT and HOLDOUT), the excluded high-MAC diagnostic modes (§10 below) and the
    uncertainty basis with its unavailable covariance components are part of the output;
11. no claim outside the exact governed FE model and specimen.

A specimen calibration never feeds a family value; a family value still needs §13.

## 6. New rule — Per-specimen non-degradation (draft)

Evaluated per specimen on its governed FIT + HOLDOUT rows, comparing the calibrated candidate with the governed
baseline FE state (the campaign start point):

**Proposed rule (A):**

```
max_i |Δ ln f_i(candidate)| ≤ max_i |Δ ln f_i(baseline)|
```

plus every row within the declared practical acceptable limit (10 %, D-066).

Rule (B) — RMS no worse **and** max within the acceptable limit — is analysed in the policy review and not
recommended: it lets one row worsen while others improve. Rule (A) is simple, deterministic and cannot hide a
worsening specimen behind another specimen's improvement, because it is applied per specimen. Campaign-level global
maxima are never used for this decision.

## 7. New rule — Minimum observability for a specimen calibration (draft)

For k fitted parameters on one specimen:

- **FIT:** at least **k + 1 distinct modal families** (M4.3 family keys; a confirmed cluster counts once);
- **leave-one-family-out complete:** removing any one FIT family must leave the system at full rank (the existing
  M5.7 cases all VALID — reporting status AVAILABLE_COMPLETE_LOO). No single mode or family may be decisive;
- **HOLDOUT:** at least **one** governed holdout family distinct from every FIT family;
- **rank:** k at the M5 RCOND; parameter count k ≤ number of FIT families − 1.

For a one-parameter E fit this makes **2 independent FIT families + 1 holdout family the minimum acceptable
structure**. One torsion-sensitive mixed mode is never sufficient on its own: it is a single family and would make
the leave-one-family-out case rank-deficient. This rule is generic (no specimen named).

## 8. Amended S8 — Engineering Constants output

| Output | `*Elastic, type=ENGINEERING CONSTANTS` block |
|---|---|
| IDENTIFIED / WIDE | allowed, under the existing material-property rules (§5, §5.1, S8) |
| NOT_IDENTIFIABLE | none |
| NO_GLOBAL_PARAMETER_VALUE (family) | none |
| SPECIMEN_ENGINEERING_CALIBRATION (if ever authorised) | **never as an ordinary material block.** A separate calibration record (JSON) and, optionally, an INP fragment that: uses a distinct material name `<material>__CALIBRATION_<specimen>_<model hash[:8]>`; starts with comment lines stating `SPECIMEN_ENGINEERING_CALIBRATION`, `NOT_A_MATERIAL_PROPERTY`, `NOT_TRANSFERABLE_WITHOUT_VALIDATION`, the specimen / test run and the FE model identity; and is never written by the material-property writer |

## 9. Amended §9 — Uncertainty wording (mandatory)

Every reported statistical_sd / birge_adjusted_sd states its covariance basis. While any Σ component is
NOT_AVAILABLE or PROVISIONAL, the report says `CONDITIONAL_ON_AVAILABLE_COVARIANCE` and names the components
(implemented for campaign reports in D-076 as `uncertainty_basis`). A complete-uncertainty wording requires every
component measured. No value is enlarged and Σ_meas is never invented.

## 10. Diagnostics and data-quality conclusions

- **Scan coverage (V2)** is data quality / experiment design, not a numerical tolerance: it is recorded per specimen and
  improved by experiment (full-edge, denser, symmetric scans), never compensated by τ_mf.
- **High-MAC modes excluded by the frequency gate (V3)** stay visible as diagnostic rows (best MAC ≥ 0.80, exclusion
  reason, signed error); they are never fitted and never re-paired by a tolerance.
- **Cross-specimen splits (V5)** are handled by §13 family consistency.
- **Cluster discovery (J3)** should eventually inspect the full experimental / FE neighbourhood (not only frozen rows);
  accepted clusters still obey the frozen governed rules. Not part of this policy draft's implementation.

## 11. What changes in code if accepted (not done here)

Campaign definition: a required `tau_mf` field for new campaigns (identity-bound). M5 holdout and pattern rules: the
max(kσ, τ_mf) bounds, only when the campaign declares τ_mf. A new output class and its separate record writer. No
change to Σ, to the objective, to §13 or to the rank rules.
