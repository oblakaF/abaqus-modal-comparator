# Stage — Multi-Specimen Inverse Identification / Hierarchical FE Model Updating

**Status:** proposed
**Depends on:** existing modal comparison core (mode pairing, MAC, DOF masks, geometric registration), architectural consolidation into `domain/ services/ persistence/ ui/`
**Supersedes:** informal "material identification" idea in earlier notes

---

## 1. Scope and framing

This stage does **not** identify "material properties". It identifies **section
stiffness quantities and effective interface parameters** from a campaign of
modal experiments across multiple physical specimens, and reports engineering
constants only as *derived* quantities with propagated uncertainty.

The guiding principle, applied consistently at every level:

> Report the quantity the experiment actually observes. Derive everything else,
> and carry the uncertainty of the derivation.

Concretely:

| Level | Identified (primary) | Derived (secondary) | Carrier of extra uncertainty |
|---|---|---|---|
| Bare laminate | `D11, D12, D66` | `E_flex, G12_flex, nu12_flex` | face thickness `h` |
| Sandwich | `A·d²`, core shear, interface | `A11, A66` | face offset `d` |

Precise statement for the sandwich row: modal data observe the combination
`q_s = A · d_s²` directly, and `A` and `d` are not separable from modal data
alone. `A` is not structurally non-identifiable, however — with `d` measured
independently and entering as a prior, `A` is **conditionally identifiable**,
with a hard floor on its precision set by the precision of `d`:

```
δA/A ≥ 2 δd/d
```

Note also that `q_s` is specimen-specific (each panel has its own `d_s`) while
`A` is the shared global parameter. The report schema must keep these separate
rather than presenting a single global `A·d²`.

A result of the form "identified Young's modulus = 121.6 GPa" is **not** an
acceptable primary output of this stage.

---

## 2. Specimen inventory and factorial structure

The available specimen set is the principal asset of this work. It is a
factorial design, not a list of unrelated tests.

**Face sections (3):** plain-weave 0.45 mm, plain-weave ~0.235 mm, twill 0.45 mm
**Cores (4):** PLA auxetic, PLA honeycomb, TPU auxetic, TPU honeycomb
**Adhesives (4, on nominally identical 300×300 panels):** 2216, DP490, DP420, DP190

Key structural property of the set:

- PLA-auxetic core appears with **three different face sections** (SP-01, SP-03, SP-08)
- Plain 0.45 face appears with **two different core topologies** (SP-01, SP-02)
- One design is built **twice from independent prints** (SP-02, SP-10)
- One core/face combination is built with **four different adhesives**

This is what separates face contribution from core contribution from interface
contribution. On a single panel these are not separable. The identification
layer must therefore be built around a campaign of specimens from the start.

### 2.1 Required identifiers

Three distinct keys, never conflated:

- `design_id` — nominal construction (face section + core + adhesive + nominal geometry)
- `physical_specimen_id` — one manufactured panel
- `test_run_id` — one modal measurement session

SP-02 and SP-10 share a `design_id` and differ in `physical_specimen_id`
(SP-10 uses a third print of the same core file). They therefore quantify
**manufacturing scatter**.

**Gap to close:** no panel has yet been re-measured after full re-suspension.
Setup/retest scatter is currently unmeasured on sandwich panels. At least one
panel (and one bare plate) must be measured twice with the suspension fully
removed and reinstalled before `σ` values in the objective can be justified.

---

## 3. Parameterisation

### 3.1 Bare laminate (Stage A)

Balanced-weave model, enabled by default, with a `general orthotropic` variant
available as a testable alternative:

- `D = D11 = D22 > 0`
- `D66 > 0`
- `r = D12 / D11`, with `|r| < 1` from positive definiteness

Optimisation variables (unconstrained, physically admissible by construction):

```
x1 = ln(D)
x2 = ln(D66)
x3 = atanh(r)
```

Measured separately, entering as priors, not as fixed constants:
`m`, `L`, `W`, `h`.

### 3.2 Sandwich (Stage B)

Global parameters, shared across specimens:

- per face section: `A11 = A22`, `A66`
  `A12` is not a free parameter, but it must **not** be set equal to the
  flexural ratio `r_D = D12/D11` from Stage A either — doing so would assume
  the through-thickness homogeneity that §9 exists to test. Instead:
  `r_A = A12/A11` receives a wide informative prior `N(r_D, σ_r²)` with `σ_r`
  large enough to permit the effect §9 looks for, and Stage B is repeated at
  several plausible fixed `r_A` to confirm that `A11` and `A66` are stable.
  Once an in-plane tensile experiment exists, `A12` comes from there instead.
- per core: `Gxz`, `Gyz`, `Ez`
  (`Ez` is expected to be weakly or non-identifiable from global flexural modes;
  this is a legitimate result, not a solver failure)
- interface: `kn`, `ks` — distributed normal and shear connection stiffness,
  common to all adhesives, applied **only on the actual rib-tip contact
  footprint**, not smeared over the full panel area

Specimen-level nuisance parameters `η_s` — **primary measurements only**, each
with its own measured prior:

```
m, L, W, h_face, H_total
```

Derived geometry never receives an independent prior, or the same uncertainty
enters the model twice:

```
μ = m / (L W)                    areal mass
d = (H_total − h_face) / 2       face offset
```

This rule applies throughout the stage, not only here.

Adhesive Young's modulus is **not** an identification parameter. It is fixed;
the interface is represented by `kn`, `ks`.

---

## 4. FE representation

### 4.1 Face sections

`*SHELL GENERAL SECTION` with explicit stiffness matrix:

- `A` block: fixed at Stage A, identified at Stage B
- `B` block: zero (symmetric layup)
- `D` block: identified at Stage A
- transverse shear: fixed explicitly via `*TRANSVERSE SHEAR STIFFNESS`, never
  left to be computed from the section stiffness being varied

This removes the `D → Q → E, ν, G` round trip entirely: the optimisation
variables are literally the numbers written into the input deck.

### 4.2 Element choice

- Shells: **S4** (fully integrated). This eliminates hourglass stiffness, whose
  dependence on generalised section stiffness would otherwise break exact
  linearity of `K` in the identified parameters. S4 retains drill-rotation
  control and the same transverse shear formulation as S4R, which is why
  §4.1 fixes transverse shear explicitly.
- Solids (core): **C3D8I**, already established as preferred over C3D8R.

Affinity is **not** uniform across the model:

| Block | Affine in its parameters? |
|---|---|
| Shell faces (`*SHELL GENERAL SECTION`, S4) | yes, by construction |
| Linear interface springs (`kn`, `ks`) | yes, by construction |
| C3D8I core | **not guaranteed** |

C3D8I carries incompatible-mode internal DOF that are statically condensed out.
The condensed stiffness is a Schur complement `K_uu − K_ua K_aa⁻¹ K_au`; it is
homogeneous under a single scalar multiplier on `C`, but it is **not additive**
when `C_ij` components vary independently. Affine decomposition of the core
block therefore has to be earned by the proof test (§10.2), not assumed.

**Hybrid fast path.** If the core block fails the proof test, the fast path is
not lost for the whole model. Faces and interface stay exactly affine, and only
the core contribution is replaced by a low-order surrogate in its three
parameters (`Gxz`, `Gyz`, `Ez`). That is a 3-dimensional surrogate, not a
14-dimensional one, and remains cheap. Fallback element choices if the core
surrogate is also unsatisfactory: C3D8 (exactly affine, but shear-locking risk
in thin rib walls) or C3D20R.

### 4.3 Bondline

The adhesive layer must be explicitly represented in mass and in geometric
offset. Order-of-magnitude on SP-01 (to be confirmed against primary weighings):

- faces: 0.25 m² × 0.45 mm × 2 × ~1500 kg/m³ ≈ 337 g
- core: ~178 g
- sum ≈ 515 g against a finished-panel weighing of 588.4 g
- residual ≈ 73 g ≈ **12.4 % of panel mass**

Equivalent full-area bondline thickness at ρ ≈ 1100:

```
V = 0.073 / 1100 = 6.64e−5 m³
t = V / (2 × 0.25 m²) = 0.133 mm per side
```

The two corrections are of different epistemic kinds and must not be treated
alike:

- **Mass: known.** 73 g is a difference of weighings. Effect on frequencies
  `≈ 1/√1.124 → −5.7 %`. The FE model's total mass must simply be constrained
  to equal the weighed panel mass; only its spatial distribution is open.
- **Offset: bounded, not known.** 0.133 mm per side is an *equivalent
  full-area* thickness, not a local bondline thickness. The adhesive sits at
  rib tips and in fillets, and open auxetic/honeycomb cells let a large
  fraction of it spread sideways instead of lifting the face sheet. The real
  increase in `d` therefore lies somewhere in `[0, 0.133]` mm per side:
  - lower bound: `d = 1.205 mm`, no change
  - upper bound: `d = 1.338 mm`, `d²` **+23 %**, `√D → ≈ +11 %`

Net frequency effect of omitting the bondline entirely therefore spans roughly
**−5.7 % to +5 %** depending on where in that interval the true offset lies —
a ~10 % band, comparable to the entire calibration discrepancy this work has
been chasing. Only a measured total panel thickness collapses it.

**Mode-class dependence.** A spatially uniform areal-mass correction shifts all
frequencies by roughly the same factor. The real adhesive mass is bound to the
rib network, so the modal mass `φᵢᵀMφᵢ` shifts differently for different mode
shapes. The homogenised treatment is defensible only while the modal
half-wavelength is much larger than the cell pitch; the report must state the
cell pitch and the mode number at which that ceases to hold. Above it, the
distribution must be represented explicitly or bounded.

A model omitting all of this will absorb the difference into `A_face` and core
shear with a mode-class-dependent bias — i.e. it will corrupt exactly the
diagnostic signal this stage relies on.

**Consequence for measurement (Stage B0 checklist):** bondline geometry must be
measured, never inferred from adhesive mass. Required per audited panel:

```
face masses before assembly
core mass before assembly
finished-panel mass          → adhesive mass by difference
finished-panel thickness map (grid of points)
rib-tip / contact footprint area
cross-section measurements of actual local bondline thickness (where possible)
```

`d` is derived from the measured total thickness, never assembled from nominal
core and face thicknesses.

**Consequence for prior results:** previously calibrated face moduli in the
44–52 GPa range should be re-derived once the bondline is explicit. If those
models omitted bondline mass and offset, the number is an effective value that
absorbed both corrections, not a material property.

---

## 5. Observation model

### 5.1 Mode pairing and clusters

- MAC used for pairing and as a quality gate, **not** in the objective:
  `MAC < 0.7` rejected; `0.7–0.85` flagged for manual review; `> 0.85` accepted.
- Near-degenerate modes (expected on square, balanced specimens) are treated as
  a **modal subspace**, not as independent modes:
  - residual for cluster `C`: `r_C = (1/n_C) Σ_{i∈C} ln(f_i^FE / f_i^EXP)`
    (geometric centre of the cluster, consistent with the log objective)
  - shape correlation via **subspace MAC**
  - information counting: one cluster contributes `n_C = 1` independent
    observation, not `n_C` — otherwise Fisher information is inflated
  - the splitting `Δf_C` within a cluster is recorded as a diagnostic only

### 5.2 Mode inclusion

Every mode carries a status and a reason:
`included` / `downweighted` / `excluded — <reason>`.

Mode 1 is excluded from the fit by default with reason
`probable suspension influence` (observed max error at mode 1 on SP-01 4.89 %,
SP-02 16.38 %, SP-05 16.85 %), but is retained and reported as a
**validation residual**. If the remaining modes fit well and mode 1 does not,
that is positive evidence that the discrepancy is not material.

### 5.3 Objective

```
J(θ, η) = Σ_s r_sᵀ Σ_s⁻¹ r_s  +  Σ_s (η_s − η̂_s)ᵀ C_ηs⁻¹ (η_s − η̂_s)
```

with `r_{s,i} = ln(f_{s,i}^FE(θ, η_s) / f_{s,i}^EXP)`.

The second term is what prevents the optimiser from freely adjusting geometry:
a measured core height of 1.96 ± 0.02 mm may move only within its measured
uncertainty.

`Σ_s` is assembled from three separately estimated components, never merged:

- `σ_measurement` — curve-fit precision from Polytec/Testlab
- `σ_setup` — from repeated tests with full suspension reinstallation
- `σ_manufacturing` — from independently built panels of one `design_id`

**Model-form discrepancy is deliberately excluded from `Σ`.** Folding it in
would let a wrong model be forgiven by inflated error bars. It is handled by
residual diagnostics (§7) instead.

---

## 6. Identifiability analysis (mandatory, precedes optimisation)

Global whitened sensitivity matrix, stacked over all specimens in the stage:

```
S_global = [S_SP01 ; S_SP02 ; ... ]        S̃ = Σ^(−1/2) S_global
S̃_ij = ∂ ln f_i / ∂ ln p_j                (whitened)
```

Computed quantities: singular values, condition number, right singular vectors,
parameter correlation matrix from `(S̃ᵀS̃)⁻¹`, collinearity index `γ_K`,
Fisher information.

Thresholds are **advisory, not automatic**:

- `γ_K > 20` (Brun's heuristic) → the *set* is flagged as not practically
  identifiable. The program does **not** silently fix a parameter. It reports
  the best identifiable subset, the deficient singular direction and its
  dominant parameter, and a recommended additional experiment.
- `cond(S̃) > 100` → warning, not hard failure.

Example of the required output form:

```
3-parameter model not practically identifiable (γ = 34).
Best identifiable subset: D11, D66.
Deficient direction dominated by D12 (0.91 of the singular vector).
Recommended action: add 45° specimen.
```

### 6.0 Effective observation accounting

Raw mode counts overstate the available information. Six PLA panels at ~9 modes
give 54 raw observations, but mode 1 is excluded on every panel, low-MAC pairs
are rejected, and each near-degenerate cluster counts once rather than twice.
The realistic figure is closer to 40, against 14 global parameters plus
prior-constrained nuisances.

The comparison that matters is not `N_modes > N_parameters` but the **rank and
conditioning of the whitened Fisher matrix**. Since exclusions and cluster
merging are data-dependent, this accounting cannot be done before measurement
and must be re-run after every campaign:

```
Raw modal observations:       54
Excluded modes (mode 1 etc.):  6
Merged degenerate clusters:    5
Rejected / low-quality pairs:  3
Effective modal observations: 40

Global fitted parameters:     14
Identifiable rank:            10
```

### 6.1 Experimental design mode

Before specimens are manufactured, the same machinery evaluates candidate
specimen sets and ranks them by minimum singular value or determinant of the
Fisher information:

- 350×350, 0°
- 350×250, 0°
- 350×250, 45°

A 45° cut is expected to be strong: even with `D16 = D26 = 0` in material axes,
rotation into specimen axes introduces coupling terms, so the experiment sees
different combinations of `D11, D12, D66`. This is a hypothesis to be evaluated
numerically, not asserted.

---

## 7. Residual diagnostics and model-form falsification

After every fit, residuals are grouped by mode class
(`bending-X`, `bending-Y`, `torsional`, `mixed`, `cluster`) and reported per
class:

```
Torsional modes:  mean residual +7.8 %
Bending-X:        +0.9 %
Bending-Y:        −0.6 %
→ Possible model-form error: systematic bias isolated to torsional modes.
```

The program must emit this rather than "reduce G12 by 14 %".

### 7.1 Interface falsification test

The four-adhesive series is a falsification experiment, not an identification
experiment. Established facts to reconcile:

- adhesive bulk moduli differ by a factor of ~200 (DP190 ≈ 9.5 MPa,
  DP420 ≈ 1873 MPa)
- free-free modal results across 2216 / DP490 / DP420 / DP190 show no
  discernible difference

These are inconsistent under a bulk-modulus interface model. The likely
resolution is that the connection is governed by rib-tip contact geometry and
is **saturated**:

```
∂f/∂ks ≈ 0   for ks > ks_sat
```

Therefore the honest result is a **lower bound**, `ks > ks_min`, not a point
value with a narrow confidence interval. The program must be able to report
bounds as results.

### 7.2 Stage C as a hypothesis test

Stage C compares two hypotheses rather than asserting a conclusion:

```
H0: kn, ks are common to all adhesives
H1: kn_a, ks_a depend on the adhesive
```

Acceptance criterion for the interface model: after identification, the
residual pattern by mode class is statistically indistinguishable across the
four adhesive variants. If residuals stratify by adhesive, the interface
representation is wrong.

Critically, if the data cannot separate `H0` from `H1` because of saturation
(`∂f/∂k → 0`), the required output is:

```
Data do not resolve adhesive-specific interface stiffness above the
saturation threshold.
```

and **not**:

```
All adhesives have identical interface stiffness.
```

Failure to detect a difference is not proof of equality, and the report schema
must be able to express the former without collapsing it into the latter.

---

## 8. Uncertainty propagation

Local covariance `Cov(θ) ≈ (JᵀWJ)⁻¹` is computed but is **not** the reported
uncertainty by itself.

Reported intervals come from Monte Carlo propagation drawn from **primary
measurements**, preserving their correlations:

```
per realisation k:  m^(k), L^(k), W^(k), h^(k), H_total^(k)
                    μ^(k) = m^(k) / (L^(k) W^(k))
                    d^(k) = (H_total^(k) − h^(k)) / 2
```

Areal mass and offset are never drawn independently of the dimensions they were
computed from.

Derived quantities are propagated through:

```
r = D12/D11
E_flex   = 12 D11 (1 − r²) / h³
G12_flex = 12 D66 / h³
```

Note the useful asymmetry: `r` enters `E_flex` only quadratically. If `r`
turns out small, the report must state both facts together:

```
D12/D11 : weakly identifiable
E_flex  : robust to this uncertainty (quadratic contribution)
```

The value of `r` is **not** to be assumed in advance — reported values for
balanced woven laminates vary considerably with fabric, weave and resin
fraction.

---

## 9. Flexural vs extensional equivalence test

Bending modes of a bare plate observe `D`. Sandwich panels observe primarily
`A`. Reporting both allows a direct test of the homogeneous-through-thickness
assumption:

```
D_measured  ?=  A_measured · h² / 12
```

**Resolution limit:** `D` carries `3 δh/h` and the right-hand side carries
`2 δh/h`, so with `h = 0.45 ± 0.01 mm` the test resolves differences of roughly
5–7 % at best. For 2–3 ply woven CFRP with crimp, the expected effect may or
may not exceed this. The test is worth running, but the program must report the
resolution alongside the verdict and must not declare a difference that lies
inside the propagated interval.

If rejected, the output is:

```
Homogeneous-through-thickness equivalence rejected (Δ = 14 % ± 6 %).
Flexural and extensional effective properties cannot be represented
by a single engineering-constant set.
```

This also means `A` and `D` for a face section are permitted to be independent
inputs to the sandwich model — which is precisely what a general shell section
allows.

---

## 10. Solver architecture

### 10.1 Fast matrix model

Given exact linearity (§4.2):

1. one reference admissible configuration + one small admissible perturbation
   per active affine parameter → `1 + N_active` Abaqus matrix-generation jobs
   (`*MATRIX GENERATE, STIFFNESS, MASS`)

   The count is **per specimen configuration**, and basis matrices are tied to
   that specimen's FE geometry — they cannot be carried from SP-01 to SP-03.

   | Stage | Active affine parameters per specimen | Basis jobs |
   |---|---|---|
   | A (bare plate) | `D11, D12, D66` | 4 |
   | B (sandwich) | `A11, A66, Gxz, Gyz, Ez, kn, ks` | 8 |

   Global parameter count at Stage B after `A12` is constrained:
   3 face sections × 2 + 2 cores × 3 + 2 interface = **14**.

2. recover the affine basis by solving a small linear system (basis vectors are
   *not* constructed from physically inadmissible "pure" sections)
3. all subsequent eigen-solutions run in SciPy

Analytic eigenvalue sensitivity, with correct normalisation:

```
∂λ_i/∂p = φ_iᵀ (K_,p − λ_i M_,p) φ_i / (φ_iᵀ M φ_i)
```

valid for **simple** eigenvalues only. For near-degenerate clusters, use
subspace (block) sensitivity; do not treat two nearly coincident modes as
independent smooth branches.

### 10.2 Verification: matrix decomposition proof test

Regression test, run on every model configuration change:

1. draw ~20 random admissible parameter vectors
2. compare `‖K_Abaqus − K_reconstructed‖_F / ‖K_Abaqus‖_F`
3. more importantly, compare the first 20 eigenfrequencies
4. accept if `|Δf|/f < 1e−4`

Failure of this test means the fast path is disabled for that configuration and
a DOE/response-surface surrogate (30–50 runs) is used instead, with the optimum
verified by a full Abaqus run.

### 10.3 Optimisation

- global stage (differential evolution / CMA-ES) with re-pairing at every
  evaluation
- local refinement (Gauss–Newton / Levenberg–Marquardt) with pairing frozen
- mandatory check that pairing is unchanged at the optimum
- Abaqus requested to extract ~2× the number of measured modes to survive
  reordering

### 10.4 Fallback runner

Where full Abaqus runs are required: parameter-vector hash cache, fixed mesh
across all iterations (otherwise MAC is not comparable), `interactive` mode,
`ask_delete=OFF`, separate scratch directories for parallel jobs, `.lck`
cleanup, timeouts.

---

## 11. Stage sequence

| Stage | Specimens | Output |
|---|---|---|
| **A** — face flexural ID | bare CFRP laminates | `D11, D12, D66`; apparent flexural properties |
| **A2** — experimental design | 0°, rectangular, 45° candidates | improved conditioning; specimen recommendation |
| **B0** — bondline audit | one PLA panel | explicit bondline mass and offset; re-derivation of previous face calibration |
| **B** — joint PLA identification | SP-01/02/03/08/09/10 | `A·d²` → `A_face`, PLA core parameters, interface `kn/ks` |
| **C** — interface falsification | 2216 / DP490 / DP420 / DP190 | common-interface hypothesis; saturation / lower bounds |
| **D** — hold-out prediction | panels excluded from the fit | transferability of parameters |
| **E** — TPU viscoelastic extension | TPU panels | `G*(ω)`, loss behaviour |

**Stage A results enter Stage B as a distribution, not as fixed numbers:**
`D_face ~ N(D̂, C_D)`, or as Monte Carlo samples. Honestly computing an
uncertainty at Stage A and then treating the result as exactly known at Stage B
would defeat the purpose.

TPU panels are excluded from the PLA fit entirely. Measured damping of
0.26–1.47 % (against hundredths of a percent on PLA) together with Abaqus below
experiment at all measured modes is consistent with frequency-dependent
stiffness. A single elastic modulus across the modal range does not exist for
that material. Note that elevated damping alone does not prove the entire
effect belongs to the TPU core; the interface is a candidate as well.

---

## 12. Validation levels

| Level | Purpose |
|---|---|
| **0** | Matrix reconstruction verification (§10.2) |
| **1** | Virtual specimen, known parameters, realistic noise, Monte Carlo 100–1000 repetitions — check that stated 95 % intervals contain the true value ~95 % of the time |
| **2** | Aluminium plate with known `E, ρ, h` — full chain Polytec → comparator → inverse solver |
| **2.5** | Same aluminium plate, two full suspension reinstallations → empirical `σ_setup` per mode |
| **2.6** | One sandwich panel re-measured after full suspension reinstallation → `σ_setup` for sandwich; separates it from `σ_manufacturing` already available from SP-02/SP-10 |
| **3** | Bare twill CFRP — first real identification |
| **4** | Cross-validation: fit modes 2–8, predict 9–15; mode 1 held out as independent diagnostic |

Level 1 is the only test that validates the *uncertainty* rather than the point
estimate, and is therefore not optional.

---

## 13. Acceptable outputs

A number is not the only valid result. The following are first-class outputs
and must be representable in the report schema:

```
D12/D11 weakly identifiable but negligible for E_flex uncertainty
Ez not identifiable from the selected modal set
ks saturated; only a lower bound can be inferred
A_face and core height remain strongly correlated; A·d² reported as primary
PLA core shear parameters become identifiable only when SP-01/03/08 are combined
Systematic torsional residual persists across adhesive variants —
    interface model-form error suspected
Homogeneous-through-thickness equivalence not resolvable at current
    thickness measurement precision
```

The program's willingness to refuse false precision is the acceptance criterion
for this stage.

---

## 14. Report template

```
IDENTIFIED SECTION PROPERTIES  (primary)
  D11 = D22 = ... ± ...        [N·m]
  D12          = ... ± ...
  D66          = ... ± ...
  Identifiability: condition number ..., γ = ...
  Parameter correlation D12/D66: ...

DERIVED ENGINEERING PROPERTIES  (secondary — apparent flexural)
  E_flex   = ... GPa   95 % CI [..., ...]
  G12_flex = ... GPa   95 % CI [..., ...]
  nu12_flex= ...
  Thickness used: 0.xxx ± 0.xxx mm
  NOTE: apparent flexural properties. Not equal to membrane properties
        without a verified homogeneity assumption.

OBSERVATION BUDGET
  Raw / excluded / merged / rejected / effective modal observations
  Global fitted parameters ... , identifiable rank ...

UNCERTAINTY BUDGET
  σ_measurement / σ_setup / σ_manufacturing  per mode
  Floor on δA/A imposed by δd/d: ... %

DIAGNOSTICS
  Mode 1 excluded: probable suspension influence (residual +11.2 %)
  Residuals by mode class: bending-X ..., bending-Y ..., torsional ...
  Model-form check: ...
  Cross-validation error, modes 9–15: ...%
```

---

## 15. Architectural placement

The existing comparison core keeps a single, narrow responsibility:

> given one specimen's experimental and FE modes, return correct pairs and
> clusters, MAC / subspace MAC, and per-mode quality.

The identification layer sits above it and queries it across many specimens.
Suggested decomposition, to be added **after** the architectural consolidation,
not merged into the current comparison module:

```
domain/
    specimen.py                  # design_id / physical_specimen_id / test_run_id
    parameter_model.py           # global θ, specimen-level η, priors, transforms
    identification_campaign.py
    modal_observation.py         # modes, clusters, status, σ components

services/
    specimen_comparison_service.py
    sensitivity_service.py       # S, whitening
    identifiability_service.py   # SVD, γ, FIM, subset search, design mode
    matrix_model_service.py      # basis extraction, proof test, fast eigensolve
    inverse_solver.py            # global + local, pairing management
    uncertainty_service.py       # Monte Carlo from primary measurements
    residual_diagnostics.py      # mode-class grouping, model-form flags
```

---

## 16. Explicit non-goals for this stage

- identifying `E3, ν13, ν23` from thin-plate flexural modes
- identifying face and core properties simultaneously from a single sandwich panel
- identifying adhesive Young's modulus
- FRF- or damping-based updating (deferred to Stage E)
- reporting membrane engineering constants derived from flexural modes
