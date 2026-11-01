# PRIORITY-10 — FE response of the M11 plate model, read live from its FE packages

Labels: RESEARCH_ONLY / FE_ONLY / NOT_A_MATERIAL_PROPERTY / NO_EXPERIMENTAL_PAIRING.

The PRIORITY-2 method (`research/plate_s4/run_s4.py`, analyse step) is now a reusable service,
`src/services/single_plate_fe_response.py`, and a tab of the program (Plate Study > D. FE Response). This folder
holds its result on the real M11 packages.

**What was run.** No Abaqus, Abaqus Python, ODB extraction, FE solve, LM or Auto-ID. The program read the existing
extracted packages and followed the FE branches by FE-to-FE MAC.

## 1. The FE family read

| Member | Parameter | Value (MPa) | Manifest SHA-256 | ODB against its run record |
|---|---|---|---|---|
| baseline (verified copy of the R6 extraction) | — | E1 = E2 = 56 000, G12 = 5 000 (from the baseline INP `962f75f2…`) | `354966dae212…` | not verifiable: no run record for this copy |
| M11_S4_E1_MINUS | E1 | 53 200 | `a2ae6efd1f6c…` | VERIFIED |
| M11_S4_E1_PLUS | E1 | 58 800 | `3f7e09810481…` | VERIFIED |
| M11_S4_E2_MINUS | E2 | 53 200 | `c658355d7bc5…` | VERIFIED |
| M11_S4_E2_PLUS | E2 | 58 800 | `988592df1c76…` | VERIFIED |
| M11_S4_G12_MINUS | G12 | 4 750 | `36982be35033…` | VERIFIED |
| M11_S4_G12_PLUS | G12 | 5 250 | `56116a4ef13d…` | VERIFIED |

**Where the data came from.**

- The six states are the PRIORITY-2 job folders in
  `D:\git\abaqus-modal-comparator-work\runs\m11_carbon_plate\s4_central\`, read in place and never written.
- Each state's parameter and value come from its own INP compared with the baseline INP. Exactly one constant differs
  and every other constant is equal.
- The run records come from that folder's `SOLVER_RUNS.csv`.

**Kind of result:** **LIVE_FE_PACKAGE_ANALYSIS**. The 14 elastic modes of every package were read and followed now;
FE3–FE6 are rigid by the code's criterion.

## 2. Tracking (STRICT_IDENTIFICATION_PAIRING, never by frequency)

**Lost branches** (BRANCH_LOSS: best FE-to-FE MAC < 0.90):

| Branch | Lost in | Central E1 / E2 sensitivity |
|---|---|---|
| FE8 | E1 +5 % and E2 −5 % | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE |
| FE9 | E1 +5 % and E2 −5 % | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE |
| FE20 | E1 +5 % and E2 −5 % | NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE |

**Order exchanges caught by the shapes** (in E1 +5 % and in E2 −5 %):

- FE10 ↔ FE11;
- FE13 ↔ FE14;
- FE17 ↔ FE18.

**Close pairs** (`confirm_cluster`):

- FE10 / FE11, FE13 / FE14 and FE17 / FE18: INDEPENDENT;
- FE15 / FE16: **CONFIRMED**, one term FE15+FE16 (mean ln f).

**FE7**, the first elastic mode, is followed in every state.

## 3. Central sensitivities and the archive

`s = (ln f₊ − ln f₋) / (ln p₊ − ln p₋)` with the actual values of the two states.

**Reproduced archive values** (live against `docs/research/plate_s4_central/CENTRAL_SENSITIVITIES.csv`):

- FE7: s_G12 = 0.48268;
- FE13: s_E1 = 0.49864;
- FE14: s_E2 = 0.50037;
- FE15+FE16: one term, 0.2242 / 0.2271 / 0.04807.

**Comparison.** Every value of every term **AGREES** with the archive: max |Δs| = 4.9 × 10⁻⁶, within the archive's
5 decimals. The historical CSV was not changed.

**FE-only rank** over the 10 complete terms:

| Parametrisation | Rank | Condition | Status |
|---|---|---|---|
| E1 / E2 / G12 | 3 of 3 | 1.83 | FE_ONLY |
| E (E1 = E2) / G12 | 2 of 2 | 2.35 | **CONDITIONAL_SUPERPOSITION** (s_E = s_E1 + s_E2; no joint ±5 % state exists) |

## 4. The FE-only What-If against the solved points

`ln f_trial = ln f0 + Σ s_j ln(p_trial_j / p0_j)`, inside the solved range only.

| Trial | Terms predicted | Largest prediction − solved FE | Not predicted |
|---|---|---|---|
| G12 = 4 750 or 5 250 MPa | 13 | −0.0129 % (FE12) | none |
| E1 = 53 200 or 58 800 MPa | 10 | −0.0144 % (FE17) | FE8, FE9, FE20 (CENTRAL_SENSITIVITY_UNAVAILABLE) |
| E2 = 53 200 or 58 800 MPa | 10 | −0.0140 % (FE18) | FE8, FE9, FE20 |

FE7 at G12 ±5 % is off by +0.0013 %.

**How to read these numbers.** The errors at −5 % and +5 % are equal. The central formula is built from the same two
points, so its error there is half their one-sided difference. This shows how curved the response is between the two
states. It is **not** an independent validation of the formula, and the ±5 % range is not a confirmed linear range:
that needs the ±2.5 % repeat, which was never run.

**Joint E (E1 = E2) +2 %.** E1 = E2 = 57 120 MPa is shown only as a conditional prediction. No joint solved point
exists to compare with.

## 5. The experiment beside it (never a pair)

PLATE 261027 EXP1 (18.6307 Hz) and FE7 (19.07217 Hz) are shown side by side only as FREQUENCY_PROXIMITY_ONLY:
+2.37 %, no pair.

The program does not:

- choose a G12 that brings FE7 onto EXP1;
- use MAC as an objective;
- treat a smaller frequency gap as a better identification.

## 6. Another plate (SYNTHETIC_TEST)

`research/plate_fe_response/make_synthetic_family.py` writes a 420 × 260 mm family with exact power laws:

- E1 = 45 000, E2 = 30 000, G12 = 4 000 MPa ±5 %;
- an order exchange (FE10 / FE11 in E1 +5 % and E2 −5 %);
- a confirmed cluster (FE12 / FE13);
- a branch loss (FE14 in E1 +5 %).

**Result** of the same service, with no M11 constant or name:

- the exponents recovered to 10⁻⁹, including an unequal step 3 800 / 4 300 MPa;
- the exchange, the cluster and the loss found;
- a missing state reported as INCOMPLETE_FE_FAMILY;
- a moved geometry refused (INCOMPATIBLE_FE_GEOMETRY).

## 7. What remains before a real physical calibration

1. **A frozen physical registration** of the plate (PRIORITY-9: the six open facts and the owner's answers), then
   confirmed EXP↔FE pairs by MAC on it.
2. **FE applicability.** An FE model with the two-band suspension and the force sensor, if they move the modes; its
   own ±5 % family, as these sensitivities belong to the free-free M11 only.
3. **The ±2.5 % linearity repeat** and, for E (E1 = E2), a joint ±5 % state (or the owner's explicit acceptance of
   the superposition).
4. **A declared campaign** (question, τ_mf, Σ, FIT / HOLDOUT) and the bounded LM. Each FE run needs its own
   authorisation.

## Files

`m11_live_g12_plus/`, `m11_live_g12_minus/` and `m11_live_e_joint_plus2/` each hold one session's:

- JSON (identities and results; no FE data);
- `central_sensitivities.csv`, `branch_tracking.csv` and `what_if.csv`;
- `FE_RESPONSE_REPORT.md`.
