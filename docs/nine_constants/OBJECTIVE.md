# Nine orthotropic Engineering Constants — objective (research track NINE-EC)

| Item | Value |
|---|---|
| Status | **PROPOSAL / RESEARCH.** Not an amendment of SPEC v1.2 and not accepted policy. |
| Branch | `research/orthotropic-nine-constants` (from Quick Calibration `aa76de3`) |
| Governing contract | [docs/auto_id/SPEC_V1_2.md](../auto_id/SPEC_V1_2.md) stays authoritative; nothing here changes it |

## Product goal

1. The user opens the Windows application.
2. They select an Abaqus `.inp` and a Polytec / Simcenter `.unv` / `.uff` of the same specimen.
3. They press Run.
4. They receive a clear report on the nine Engineering Constants of one orthotropic material:
   E1, E2, E3, ν12, ν13, ν23, G12, G13 and G23.

The nine constants are nine **independent unknowns** in the parameterisation. Independence of the parameterisation
is **not** identifiability: the report always has nine rows, and a constant the evidence cannot support carries a
status, never an invented number.

## Three different claims (never converted into each other)

| Claim | Meaning | Where it lives |
|---|---|---|
| A. Material-property identification | a property of the material, at declared precision (SPEC v1.2 §1 A) | governed Auto-ID only; **no nine-constant path exists** |
| B. Effective FE-model calibration | constants that make this model reproduce this specimen (SPEC v1.2 §1 B, §3a; Quick Calibration) | Quick Calibration (one common E1 = E2 multiplier, optional G12) |
| C. Diagnostic sensitivity / identifiability | which constants this evidence can determine, and why not | **this research track** |

A refusal in A is never turned into a number from B. A research estimate of C is labelled
`RESEARCH_DIAGNOSTIC_ONLY` and `NOT_A_VALIDATED_MATERIAL_PROPERTY`.

## Per-constant statuses

| Status | Meaning |
|---|---|
| `SUPPORTED_RESEARCH_ESTIMATE` | value and uncertainty from a completed research estimation, every applicable gate passed |
| `NOT_IDENTIFIABLE` | the evidence cannot determine it (rank, sd, confounding, no sensitivity, element formulation) |
| `NOT_EVALUATED` | not assessed (no FE sensitivities, a column could not be evaluated, or the question was refused) |
| `FIXED_INPUT_NOT_IDENTIFIED` | declared fixed for the question; the input value is kept and never shown as an estimate |
| `POLICY_OR_EVIDENCE_BLOCKER` | a scientific rule is missing or not satisfied (e.g. no accepted Poisson precision rule) |
| `INVALID_OR_UNSUPPORTED_MODEL` | inadmissible constants, ambiguous or unsupported material record |

## Success criterion

A technically credible, testable route towards nine independent constants that never confuses
**nine input fields** with **nine identified material properties**. Reporting a subset, or no values, is a
successful outcome when the evidence cannot support more.
