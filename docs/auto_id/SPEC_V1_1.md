# Auto-ID v1.1 — Governing Scientific Specification

| Item | Value |
|---|---|
| Version | 1.1, agreed 2026-10-03 after two external reviews |
| Audited snapshot | `121ba1d06b7c268b3051f1407a3ea26a9027dca3` |
| Companion audit | [AUDIT_121ba1d_V1_1.md](AUDIT_121ba1d_V1_1.md) (finding ids K1…, V1…, J1…) |
| Archival source | [source/Spec_AutoID_v1.1.docx](source/Spec_AutoID_v1.1.docx) (Russian original, SHA-256 in [source/SHA256SUMS.txt](source/SHA256SUMS.txt)) |
| Status | **Normative.** This Markdown file is the canonical contract for implementation. |

This document is a faithful English rendering of the accepted v1.1 specification
plus the supervisor's freeze clarifications. It does not redesign the science.
Where the archival DOCX and this file differ, the difference is stated explicitly
(see §19). Older roadmap and design documents yield to this file wherever they
conflict (see [README.md](README.md)).

Normative keywords: **MUST**, **MUST NOT**, **MAY**.

---

## 1. Upper rule

Auto-ID outputs a numerical value **only** when the experiment and the model
support that parameter at the declared precision.

**Refusal to output a number is a valid and successful scientific result.**

No parameter, threshold, hidden override, GUI option or operating mode may turn a
scientific refusal into a numerical result. Every other clause of this
specification is subordinate to this rule.

## 2. Goal

The user points the program at a specimen folder (or a family of specimens) and
presses one button. The program:

1. finds and pairs experimental and FE modes;
2. runs Abaqus as many times as needed;
3. returns one of three verdicts for each identified parameter;
4. for parameters with verdict IDENTIFIED or WIDE, writes a ready
   `*Elastic, type=ENGINEERING CONSTANTS` block.

One ODB is one point in parameter space. Sandwich frequencies do not scale as √E,
because core and adhesive do not change with the carbon. The minimum input is
therefore a **re-solvable model (INP)**. An ODB, if present, is only a cache of the
reference solution. For a bare plate (Stage A) the stiffness matrix is affine in
D11, D12 and D66. That path already exists in
`src/services/matrix_model_service.py` and needs no repeated Abaqus solves.

## 3. Verdicts

| Verdict | Russian | Requirements | What the user sees |
|---|---|---|---|
| `IDENTIFIED` | ОПРЕДЕЛЕНО | conservative uncertainty (§9) **≤ 5 %**; residual pattern test passed; **all fitting pairs MAC ≥ 0.8**; no `registration-limited` flag; for global parameters the family-consistency test passed; no scientific refusal condition active | value ± uncertainty, with breakdown by source |
| `WIDE` | ШИРОКО | conservative uncertainty **> 5 % and ≤ 8 %**; every other IDENTIFIED requirement satisfied | value ± uncertainty and the main source of uncertainty |
| `NOT_IDENTIFIABLE` | НЕ ОПРЕДЕЛЯЕТСЯ | any refusal condition, for example: uncertainty > 8 %; systematic residual / model-form pattern; family inconsistency; branch loss; pairing loss; `registration-limited`; peak-derived modal input used for identification; practical non-identifiability; another explicitly documented scientific block | no number; the reason, and the experiment that would fix it |

The 5 % and 8 % thresholds are the user's target values. The program **MUST
NOT** weaken gates, MAC thresholds or priors to obtain a greener verdict. The user
**cannot** override NOT_IDENTIFIABLE. On current data (for example SP02, where some
pairs have MAC < 0.8) a green verdict may legitimately be impossible: data adequate
for research may be inadequate for a production verdict.

## 4. Input: specimen package

| File | Required | Purpose |
|---|---|---|
| `model.inp` | yes | Abaqus model with a `*Frequency` step. Material names are given in `specimen.json`. |
| `modes.unv` | yes* | Testlab PolyMAX export: geometry dataset 15/2411 plus modal dataset 55 (curve-fitted shapes and frequencies). |
| `frf.unv` | no | Polytec or Testlab dataset 58: FRFs and coherence, for QC and for the built-in multi-mode fit. |
| `specimen.json` | yes | Specimen passport: measurements, calibration and its uncertainty, orientation, what to identify. |
| `photo_*.jpg` | no | Photographs with corner A marked, for manual orientation check. |
| `model.odb` | no | Cache of the reference solution. Identity **MUST** be checked by content (audit V5). |

\* If `modes.unv` is absent and only `frf.unv` exists, modes are built by the
built-in **multi-mode** fit (stage M1). Peak-derived modes are prohibited as
identification input (audit K1). The frozen studies CARBON-4C/5A are unaffected,
because they use PolyMAX modal sets.

### 4.1 `specimen.json` (illustrative example)

```jsonc
{
  "schema": "auto-id/specimen/v1.1",
  "id": "SP-13",
  "family": "CFRP-T300-plain-0.45-oldstock",
  "type": "sandwich",          // sandwich | bare_plate | core_tile
  "plan_mm": {"Lx": 510.0, "Ly": 520.0, "sd": 1.0},
  "masses_g": {"panel": 0, "core": 178.6, "adhesive": 90,
               "face_top": 0, "face_bottom": 0},
  "face_thickness_mm": {"top": [0.45, 0.46, 0.44, ...],   // 9+ points
                        "bottom": [...]},
  "core_height_mm": {"value": 1.96, "sd": 0.02},
  "materials": {"face": "CFRP_Face", "core": "PLA_Auxetic",
                "adhesive": "DP420"},
  "suspension_max_hz": 18.0,
  "geometry_calibration": {
    "mode": "scan_to_panel_edges",         // or "corner_coordinates_mm"
    "corner_A_unv_node": 1,
    "corner_A_fe_xy_mm": [0.0, 0.0],
    "x_axis_towards_unv_node": 11,
    "uncertainty": {"translation_mm": 3.0, "scale_rel": 0.01,
                    "rotation_deg": 0.5}
  },
  "acquisition": {"session": "260909", "grid": "11x11", "remount_of": null},
  "identify": "default"
}
```

The GUI wizard fills the passport once per specimen. Without
`geometry_calibration` the program stops and asks for orientation confirmation from
the photograph. `acquisition.remount_of` links a repeat test of the same panel to
the original test. That link is the source of Σ_setup (§7).

Identity keys **MUST** be distinct: `design_id`, `physical_specimen_id`,
`test_run_id`.

## 5. What is identified (parameter policy)

Each parameter is identified where it dominates and where the fewest foreign
unknowns are present.

| Parameter | Source | Type | Rule |
|---|---|---|---|
| D11, D66 (→ E_flex, G12_flex) | bare plate, Stage A | global for the family | **Primary source of G12.** D12/D11 where possible. ν12 default 0.05. |
| E_in-plane (E1 = E2) | sandwiches of the family | global for the family | E1 ≠ E2 **MUST NOT** be enabled without traceable warp/fill orientation. |
| G12 from sandwich | sandwiches of the family | secondary evidence | May enter the fit. IDENTIFIED only under the conditions of §5.1. |
| t_face | measurement | specimen parameter | Prior from 9+ thickness points. Its uncertainty **MUST** propagate to E (audit V3). |
| k_core | independent experiment | specimen parameter | See §5.3. |
| k_int | sandwich | specimen parameter | Disabled by default. When disabled, the lowest torsional family goes to holdout (§12). |
| E3, ν13, ν23, G13, G23 (carbon) | — | fixed | Verify that reasonable variation changes frequencies by < 0.3 %. Otherwise include them in the uncertainty budget (M6.4). |

Order within a family:

1. bare plate → D11, D66;
2. if available, core tile → k_core prior;
3. sandwiches of the family jointly → E_in and specimen parameters;
4. consistency test.

If there is no bare plate, G12 receives `NOT_IDENTIFIABLE — bare plate required`,
unless the sandwich path itself satisfies §5.1.

### 5.1 G12 policy

- The primary source of carbon G12 is the **bare laminate (Stage A)**.
- Sandwich modal data provide **secondary** G12 evidence.
- Sandwich-only G12 **MAY** receive IDENTIFIED only if **all** of the following hold:
  - core nuisance parameters are independently constrained;
  - interface nuisance parameters are independently constrained where relevant;
  - the practical-identifiability calculation (§10) supports G12, judged by q_G and
    the full nuisance-space analysis;
  - family consistency (§13) passes;
  - all remaining scientific gates pass.
- The specification **MUST NOT** encode a dogmatic statement that sandwich modes
  contain zero G12 information. They can carry real G12 sensitivity. The problem is
  **confounding** with core and interface, not absence of sensitivity.

### 5.2 Current carbon model

- Current v1 research constraint: **E1 = E2 = E_in_plane**.
- **G12 remains a separate physical parameter.**
- E1 ≠ E2 **MUST NOT** be enabled unless warp/fill/material-axis orientation
  becomes physically traceable.
- ν12 is fixed according to the accepted campaign definition (currently 0.05).
- The other transverse constants stay fixed unless sensitivity analysis shows their
  uncertainty is not negligible.
- Reported values mean **effective face-sheet Engineering Constants within the
  calibrated sandwich FE model**. They **MUST NOT** automatically be called fibre
  properties, constituent properties, or coupon-certified lamina constants.

### 5.3 k_core

- k_core is an **effective stiffness multiplier for the explicitly modelled printed
  lattice**, for a defined printing process and topology. It multiplies all moduli of
  that lattice. **It is not bulk PLA.**
- CARBON-5F gives **sensitivity** to k_core. CARBON-5F does **not** establish the
  numerical prior for k_core.
- The numerical prior requires an **independent experiment**. Preferred: a free-free
  modal test of a printed core tile with the same lattice and process
  (`type = core_tile`), modelled with the same explicit lattice as in the sandwich.
- Until such independent evidence exists, the numerical prior is **TBD /
  provisional** and must be configurable and flagged as provisional.

## 6. Pipeline S1–S8

### S1. Experimental reading and QC

- Mode source: dataset 55 (priority) or the built-in multi-mode fit (M1). For each
  mode keep f, ζ, the shape, and these flags:
  - **unresolved resonance:** 2ζf < 3Δf;
  - **coherence at resonance < 0.9;**
  - **phase complexity.**
- Modes below `suspension_max_hz` are discarded. FE frequencies **MUST NOT** be used
  to select experimental modes.
- Experimental AutoMAC: pairs with off-diagonal > 0.5 are flagged as
  indistinguishable by the measurement grid.

### S2. Registration and its uncertainty

See §11. `FrozenRegistration` is built from `geometry_calibration`. The registration
hash is written into the result and **MUST** be identical on repeated runs.

### S3. Reference solve, modal families, frozen pair set

- Run Abaqus at p0 from the INP → extraction → pairing under
  `IdentificationPairingPolicy` (§12): MAC ≥ 0.80, |Δf| ≤ 15 %, admissibility applied
  **before** Hungarian assignment (audit V4).
- Classify modal families (§12.2). Select holdouts by family (§12.3).
- Apply the cluster rule (§12.4).
- **Freeze** the set of pairs and clusters. Later candidates use FE-to-FE branch
  tracking (§12.1).

### S4. Sensitivities

- Central finite differences in ln p with step ±5 %: 2·n_p solves, in parallel when
  licence tokens allow.
- S_ij = (ln f⁺ − ln f⁻) / (ln p⁺ − ln p⁻). Branches are tracked by FE-to-FE MAC.
- Noise control: a repeat with step ±2.5 % must give S within 5 %.

### S5. Practical identifiability, before optimisation

See §10.

### S6. Optimisation

See §8.

### S7. Verification, pattern test, robustness block

- Final solve at p̂: residual table for every family, including holdouts.
- **Pattern test:** residuals are grouped by S3 family. If within a family all
  residuals have the same sign and exceed 2σ, **or** holdout residuals exceed 3σ, the
  result is reported as *systematic pattern — probable model-form error*. A green
  verdict is then impossible.
- Robustness quantities: §9.

### S8. Result

Report per parameter: verdict, value (only when permitted), the three uncertainty
quantities of §9, the registration MAC range and flags, the holdout residuals, and
the `*Elastic, type=ENGINEERING CONSTANTS` block. Any value in that block that was
**not** identified **MUST** be annotated as the unchanged INP value.

Illustrative output (all numbers illustrative):

```text
== SP-13 | family CFRP-T300-plain-0.45-oldstock ==
E_in: IDENTIFIED  45 800 MPa
   statistical_sd 3.6 %  (frequencies 1.0 %, thickness 3.4 %, setup 0.6 %)
   birge_adjusted_sd 4.1 %  (chi2/dof = 1.3)
   model_form_robustness -2.8 ... +3.1 %  (leave-one-family-out)
G12: NOT_IDENTIFIABLE - no bare plate; from sandwich q_G = 0.21
Registration: MAC range within calibration 0.86-0.97, no flag

*Material, name=CFRP_Face
*Elastic, type=ENGINEERING CONSTANTS
 45800., 45800., 6700., 0.05, 0.3, 0.3, 4500., 2200.,
 2200.
** G12 = 4500 - unchanged INP value, NOT identified

Holdout: torsional family df = +7.9 % -> model torsional stiffness too low
```

A `result.json` with full provenance is saved: hashes of INP, UNV, registration,
policies and program version.

## 7. Observation covariance

```
Σ = Σ_meas + Σ_setup
```

| Source | Where it is accounted | Origin |
|---|---|---|
| Modal fit (Σ_meas) | Σ | PolyMAX or the built-in fit; typically < 0.1 % |
| Repeat test of the **same** panel (Σ_setup) | Σ | Genuine remount / re-suspension / excitation reinstallation of the **same physical specimen**, same grid and comparable acquisition protocol. Provisional 0.3 % until measured, flagged as provisional in the report. |
| Specimen-to-specimen scatter | specimen nuisance parameters and family consistency (§13) | Campaign level; reference pair SP2/SP10 |
| Face thickness | prior of t_face | Scatter of 9+ points; δE/E ≈ δt/t (sandwich), 3·δt/t (bare plate) |
| Face separation d | prior (with core height) | 2·δd/d |
| Model form | S7: pattern test, Birge, leave-one-family-out | Not specified in advance |

Rules:

- **Specimen-to-specimen scatter MUST NOT enter one specimen's Σ.** Manufacturing and
  specimen differences belong in hierarchical specimen nuisance parameters and family
  consistency.
- **Model-form discrepancy MUST NOT enter Σ.** It is evaluated after fitting (§14).
- Only repeat testing of the same specimen estimates setup/retest scatter. The SP13
  121-point / 289-point pair is usable only for a frequency-only estimate, and only
  if it is the same panel with an independent remount. Shapes and MAC need a repeat
  on the same grid.

## 8. Optimisation

Notation: r(x) is the whitened residual vector; J_r = ∂r/∂x is the residual
Jacobian; Φ(x) = ½‖r(x)‖² is the objective. **One symbol MUST NOT be used for both
the Jacobian and the objective.**

```
x       = ln p                       # log parameters, with physical bounds
r_i     = (ln f_FE,i(x) − ln f_EXP,i) / σ_i      # pairs and confirmed clusters
r_prior = C_prior^(−1/2) · (x_nuis − x_nuis,0)
J_r     from S4; then Broyden updates; repeat finite differences only on step failure

Δx    = −(J_rᵀ J_r + μ·D)⁻¹ · J_rᵀ r        # D = diag(J_rᵀ J_r)
x_new = x + Δx                               # projected onto bounds
accept if Φ(x_new) < Φ(x)  (one verification solve); otherwise μ ← 10μ
stop:  max|Δx_j| < 0.2·sd_j,  or 5 iterations,  or branch/pair loss
```

- **Do not lose the minus sign** in Δx.
- **MAC does not enter Φ.** MAC is used only for mode/branch identity.
- Candidate acceptance requires an **actual decrease in Φ** and **preserved
  scientific branch identity**.
- Expected Abaqus solve count for two global parameters: about 10–20 per specimen.

## 9. Uncertainty and robustness

Three distinct quantities are kept per parameter. They **MUST NOT** be merged into a
single "1σ".

| Field | Definition | When it applies |
|---|---|---|
| `statistical_sd` | Posterior/statistical sd from the practical-identifiability model (§10) at p̂, using Σ (measurement + setup) and priors | always |
| `birge_adjusted_sd` | `statistical_sd · s_B`, with `s_B = sqrt(max(1, chi2/dof))` | **only** if the pattern test passed, i.e. residuals are compatible with random scatter. Otherwise the field is not filled and the verdict cannot be green. |
| `model_form_robustness` | Range of estimates under leave-one-modal-family-out, in % of p̂ | always. It is a **range, not a standard deviation**, and **MUST NOT** be labelled 1-sigma. |

If a systematic model-form pattern is detected, Birge scaling does **not** turn the
result into a valid uncertainty estimate.

**Conservative envelope used for the verdict:**

```
conservative_uncertainty = max(birge_adjusted_sd, ½ · width(model_form_robustness))
```

If `birge_adjusted_sd` is undefined, the verdict cannot be better than
NOT_IDENTIFIABLE, with reason *model form*.

## 10. Practical identifiability

Identifiability **MUST NOT** be decided from carbon-only, machine-precision matrix
rank.

Use the **full parameter system**: global parameters, specimen nuisance parameters,
and prior rows.

```
S~  = Σ^(−1/2) · [ s_E, s_G, s_t(SP02), s_t(SP13), s_k(SP02), s_k(SP13), ... ]
A   = [ S~ ;  C_prior^(−1/2) · E_nuis ]        # prior rows only for nuisance parameters
C   = (Aᵀ A)⁻¹ ;   sd_j = sqrt(C_jj)            # in units of ln p

# residual information on G12 after all other columns:
q_G = ‖(I − P_N) a_G‖ / ‖a_G‖                   # P_N projects onto span of the other columns of A
sd(ln G12) = 1 / ‖(I − P_N) a_G‖                # when G12 has no prior of its own
```

- Observation sensitivities are whitened with Σ. The augmented system includes
  nuisance priors.
- **Rank deficiency is a hard scientific block.** Condition number and collinearity
  remain diagnostics.
- Numerical rank tolerance **MUST** reflect finite-difference/model noise, not machine
  epsilon. Default for v1.1: **rcond ≈ 1e-3**, unless later justified by measured
  numerical noise (audit K2).
- `a_G` is the whitened G12 column and N the space of the remaining columns.
  **q_G ≈ 0 means G12 information is absorbed by nuisance directions.**
- A pairwise cosine such as `|cos(s~_G, s~_core)| > 0.9` **MAY** be reported as an
  understandable warning. It does **not** replace the full nuisance-space analysis.
  The verdict is decided only by the full calculation.
- A parameter with sd_j > 8 % is not fitted. It is fixed at its starting value and
  receives NOT_IDENTIFIABLE with a reason. The user cannot override this.

## 11. Registration

- Geometry, orientation, translation and scale **MUST NEVER** be selected by
  maximising MAC or frequency agreement, including inside the calibration
  uncertainty.
- Registration comes from **physical calibration** (specimen passport): scale from
  measured dimensions, orientation from the corner-A marker.
- Registration uncertainty **MAY** be propagated diagnostically, by perturbing only
  within the measured physical uncertainty (translation, scale, rotation; a
  deterministic set, for example ±σ per axis). Report the MAC range per pair.
- **Never select the perturbation that produces the best MAC.**
- If physically allowed perturbations make any pair's MAC cross the production
  threshold (0.8) or change the accepted pairing, set **`registration-limited`**.

## 12. Pairing, families and clusters

### 12.1 Pairing

- Pairing for identification uses a named **`IdentificationPairingPolicy`**, passed
  explicitly. The default is strict.
- Baseline identification pairing uses strict gates including **MAC ≥ 0.8**, plus
  explicit frequency (|Δf| ≤ 15 %), admissibility and coverage requirements.
- After the baseline, the observation rows are **frozen**.
- Later candidates **MUST** use **FE-to-FE branch tracking** (FE-to-FE MAC threshold
  0.9, unique assignment).
- Experimental observations **MUST NOT** be added or dropped dynamically because a
  candidate crosses a normal-comparator gate.
- **Branch loss is a scientific refusal condition.** There is no re-pairing by the
  normal comparator.
- MAC is used for mode identity and evidence. MAC **does not** enter the inverse
  frequency objective.

### 12.2 Modal-family classifier

- Works on FE shapes of the outer surface.
- Continuous reflection/parity scores, where R_x and R_y are reflections through the
  mid-lines (node mapping by nearest mirror node):

  ```
  P_x = φᵀ R_x φ / (φᵀ φ)
  P_y = φᵀ R_y φ / (φᵀ φ)
  ```

  P ≈ +1 means even, P ≈ −1 means odd, intermediate values mean mixed/asymmetric.
- Also count nodal lines.
- For near-square panels, also compute parity about the diagonals.

### 12.3 Holdouts

- Holdouts are selected by **physical modal family**, never by FE mode number.
- Default sandwich holdouts: the **lowest torsion-dominated (approximately odd-odd)
  family** when k_int is not enabled, **and** the **highest accepted family** as a
  validation holdout.

### 12.4 Modal clusters

- Frequency closeness **|Δf| / f < 3 %** (experimental or FE) is **only a trigger**
  for cluster examination. It is not sufficient by itself.
- A 2-mode cluster is **confirmed** when, under allowed parameter perturbations
  (±5 % in each relevant direction: E, G12, later k_core):
  - individual branch identity becomes unstable (FE-to-FE MAC of at least one mode
    < 0.9), **but**
  - the two-dimensional modal subspace stays stable, measured with principal angles /
    canonical correlations:

    ```
    cos²(θ1) > 0.95   and   cos²(θ2) > 0.95   for all tested relevant directions
    ```
- Confirmed cluster residual:

  ```
  r_C = (1/n_C) · Σ ln(f_FE / f_EXP)
  ```
- A rotating near-degenerate pair that is confirmed as one cluster **MUST NOT** be
  counted as two fully independent observations.

## 13. Family (campaign) consistency

`family.json` lists the specimens of a family. Global parameters are shared and
specimen parameters are per specimen. The joint Φ is the sum over specimens plus the
prior terms.

```
Δχ²  = χ²_shared − Σ_s χ²_separate,s
Δdof = k · (N_specimens − 1)
```

where k is the number of global material parameters allowed to differ in the
separate fits. The shared set is rejected at **p < 0.01**.

The χ²(Δdof) approximation is valid only when **all** of these hold:

- Σ is fixed;
- the optimum is interior (no active bounds);
- the observation model is comparable across specimens;
- practical identifiability is adequate;
- influential priors or bounds do not invalidate the approximation.

Otherwise use a **parametric bootstrap on the linearised model using J_r** (at least
2000 replicates, **no new Abaqus solves**). The report states which path was used.

If shared consistency fails, report *one carbon material vector does not explain the
family*. **No global material value is produced.** Each specimen is shown
separately.

Natural families in the current set: old plain 0.45 (SP1, SP2, SP10, SP13); twill
0.45 (SP3 and the 350×350 bare plate); new plain 0.25 (SP8, SP9, …). The SP2/SP10
pair is the reference specimen-to-specimen scatter test.

## 14. Model form

Model-form discrepancy is evaluated **after** fitting, through:

- residual-family pattern;
- holdouts;
- leave-one-family-out;
- specimen consistency;
- topology consistency.

It **MUST NOT** be placed into Σ to make residuals look statistically acceptable.

## 15. Experimental requirements

- **Orientation:** mark corner A, start the grid there, point the X axis the same way
  on every specimen, and photograph the grid.
- **Scale and its uncertainty:** in PSV enter a real distance or reference length, or
  record "grid to edges" with measured dimensions. Record calibration uncertainty in
  the passport.
- **Resolution:** for modes below 100 Hz with ζ about 0.1–0.3 %, Δf ≤ 0.05 Hz
  (zoom-FFT or more lines).
- **Curve fit:** export from Testlab PolyMAX to UNV dataset 55 with shapes.
- **Two excitation points:** on SP13 the 206 Hz mode was barely excited.
- **Repeat of the same panel for Σ_setup:** remove, re-suspend, reinstall excitation;
  same grid and same protocol. One panel per family is enough.
- **Thickness:** every sheet at 9+ points before bonding; the finished panel around
  its perimeter.
- **Bare plate:** soft suspension; shaker attachment mass in the model, or
  non-contact excitation.
- **Bare core tile (k_core prior):** same free-free procedure; its model is the same
  explicit lattice as in the sandwich.

## 16. Architecture and prohibitions

- Scientific logic lives in **reusable services**. CLI and GUI call the **same**
  service.
- Planned modules (they do not exist at the audited snapshot):
  - `src/domain/specimen_manifest.py` (planned): specimen and family passport,
    validation, hash;
  - `src/services/auto_identification.py` (planned): S1–S8 pipeline on top of existing
    services. Target size 1–2 thousand lines. Policies (gates, thresholds, priors) are
    explicit objects included in the result hash.
- CLI `python -m auto_id <folder>` (planned) for batch runs and tests. The GUI calls
  the same service.
- Run directory `runs/<family>/<specimen>/<hash>/`. An interrupted run resumes by
  hashes.
- **The GUI is implemented last.** No second scientific implementation in GUI code.
- **No new `install_*` monkeypatch layers for Auto-ID.**

**Prohibited:**

- MAC in the objective function;
- selecting geometry, orientation or grid position by MAC or frequency, including
  inside the calibration uncertainty;
- overriding NOT_IDENTIFIABLE, or weakening gates, thresholds or priors to get a
  result;
- identification from peak-derived modes;
- model form as a term of Σ in the objective;
- E1 ≠ E2 without traceable fabric orientation;
- IDENTIFIED for G12 from sandwich alone without the conditions of §5.1.

## 17. Stages and acceptance criteria (summary)

The executable roadmap is [ROADMAP.md](ROADMAP.md). The archival acceptance criteria
are:

| Stage | Content | Acceptance |
|---|---|---|
| M0 | Green CI (V7); real SP02/SP13 fixtures (J1) | Factual unittest summary on Linux and Windows (before the fix: 873 ran / 870 passed / 1 failed / 2 skipped; after: 0 failed); fixture SHA-256 pinned |
| M1 | Identification modes: PolyMAX dataset 55 as main path; built-in multi-mode fit; peak-derived prohibited (K1) | SP13 from raw FRF: 206.15 and 212.61 Hz found (±0.05 Hz of PolyMAX); no false 217.5 Hz; ζ within 30 % of PolyMAX |
| M2 | Specimen passport, registration from it, registration-uncertainty diagnostic (K4, S2) | SP02/SP13 reproduce existing FrozenRegistration hashes; the diagnostic never changes the chosen registration |
| M3 | Universal forward builder (V2) | SP02 and SP13 INPs byte-for-byte identical to the current builder |
| M4 | Family classifier, cluster rule, strict pairing policy, S3–S6 orchestrator (V1, V4) | Synthetic twin: "experiment" = Abaqus at E = 45 000, G = 4000 MPa + 0.3 % noise; start 52 000 / 4500; recovery within 1σ in ≤ 20 solves. Branch exchange between iterations → refusal |
| M5 | Full identifiability with nuisance and q_G; S7 robustness block (K2, V3) | Synthetic G12 absorbed by k_core gives q_G ≈ 0 and NOT_IDENTIFIABLE; synthetic systematic model error gives no green verdict |
| M6 | Bare plate (twill 350×350) via Stage A; then core tile | D11, D66 → E, G12 with uncertainty; repeat of the same plate agrees within 1σ |
| M7 | Campaign old plain 0.45 (SP1, SP2, SP10, SP13) | Consistency report (Δχ² or bootstrap, stating which) |
| M8 | GUI wizard and Auto-ID button | Folder → `*Elastic` block with no manual numbers except the passport |

An independent steel beam or plate experiment is the validation gate immediately
after M6 (D-015).

## 18. Changes v1 → v1.1 (archival record)

| Item | v1 | v1.1 |
|---|---|---|
| Upper rule | — | refusal to output a number is a regular result |
| LM step | Δx = (JᵀJ+μD)⁻¹Jᵀr, no minus; J used for both Jacobian and objective | Δx = −(J_rᵀJ_r+μD)⁻¹J_rᵀr; Jacobian J_r, objective Φ |
| Σ | σ_fit² + σ_rep² + σ_mf² | Σ_meas + Σ_setup; specimen scatter at family level; model form in S7 |
| Result uncertainty | one sd | statistical_sd, birge_adjusted_sd (only if pattern test passed), model_form_robustness (range); verdict by envelope |
| Identifiability | sd from S without nuisance | full matrix with nuisance and prior rows; q_G |
| G12 from sandwich | prohibited | secondary evidence; IDENTIFIED only with independent nuisance constraints and consistency |
| k_core | lognormal sd 15 % | effective printed-lattice multiplier; prior TBD from core-tile test |
| Cluster | \|Δf\|/f < 2 % | trigger < 3 % + subspace stability in all directions |
| Holdout | "mode 1" | lowest torsional family by continuous parity scores |
| Registration | — | MAC diagnostic within physical uncertainty; `registration-limited` flag; no optimisation |
| Family consistency | "p < 0.01" without statistic | Δχ², Δdof = k(N−1), validity conditions; otherwise bootstrap on linearised model |

## 19. Freeze clarifications (supervisor, 2026-10-03)

These clarifications are part of the governing contract. They resolve points where
the archival DOCX wording could be read more loosely.

1. **CARBON-5F and the k_core prior.** The DOCX mentions that the post-CARBON-5F
   evidence appendix may carry "a proposal for a numerical k_core prior", and that the
   prior is filled "after CARBON-5F and the core-tile test". Under this freeze
   (D-006), CARBON-5F provides **sensitivity only**. A numerical k_core prior requires
   independent evidence (core-tile test or equivalent). Until then the prior stays
   TBD / provisional.
2. **Sandwich G12** is stated positively as conditional secondary evidence (§5.1), not
   as zero information.
3. **Peak-derived modes** are prohibited for production identification. The frozen
   CARBON-4C/5A studies are unaffected (PolyMAX provenance; see the audit, K1).
