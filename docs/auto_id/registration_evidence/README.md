# Registration evidence

Read-only physical registration reconstructions from stored measurement records (no modal data,
no MAC), and the zero-Abaqus re-evaluations that consume the resulting frozen registrations.

| File | Content |
|---|---|
| `SP13_physical_registration_reconstruction.json` | SP-13 260910a scan → panel reconstruction (`tools/reconstruct_psv_registration.py`) |
| `SP13_registration_reevaluation.json` | Legacy vs physical strict freeze (`tools/sp13_registration_reevaluation.py`) |
| `SP13_registration_uncertainty.json` | M2.4 diagnostic of the SP-13 physical registration after H8 (`tools/registration_uncertainty_evaluation.py`) |
| `SP02_physical_registration_reconstruction.json` | SP-02 260803 scan → panel reconstruction (same tool and method) |
| `SP02_registration_reevaluation.json` | SP-02 legacy vs physical strict freeze and the combined SP-02 + SP-13 picture (`tools/sp02_registration_reevaluation.py`) |
| `SP02_registration_uncertainty.json` | M2.4 diagnostic of the SP-02 physical registration (regenerated 2026-10-07 after the D-065 passport binding; only `passport_sha256_lf` changed) |

Decisions: D-062, D-063, D-064 (`../DECISIONS.md`); M6_DECISION_RECORD §17–§18.
