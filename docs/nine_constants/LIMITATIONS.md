# Limitations of the nine-constant research track (state of this batch)

## What it cannot do

- **No real FE evaluation:**
  - the Abaqus adapter is designed, not connected;
  - real-file previews report NOT_EVALUATED (no frozen rows) or a rank bound (frozen rows of a Quick Calibration
    result of the same INP / UNV / modal set).
- **No governed verdict:**
  - no IDENTIFIED / WIDE / SPECIMEN_ENGINEERING_CALIBRATION is produced;
  - no calibrated nine-constant INP is written.
- **SP-13:** the accepted SP-13 evidence has two strict rows. Nine constants are refused from it by rank alone. The
  P5 result (k = 1.14012, E1 = E2 ≈ 59 286 MPa, APPROXIMATE) stays a separate effective-model diagnostic.

## Scientific gaps (need SUPERVISOR decisions)

- **Poisson ratios:**
  - no accepted precision rule (SPEC §10 is in ln p);
  - the ν finite-difference step and noise criterion are proposals;
  - research runs need a caller-declared, UNACCEPTED limit.
- **Nuisance parameters:**
  - sandwich nuisance columns (t_face, core, adhesive / interface, suspension mass) are supported by the M5 engine but
    no evidence-backed priors exist;
  - the synthetic cases assume none.
- **Uncertainty:**
  - the research estimate reports statistical_sd only;
  - the pattern test, birge_adjusted_sd, model_form_robustness (leave-one-family-out) and the conservative envelope
    are not implemented for nine constants.
- **Clusters:**
  - the research engine has no cluster rule;
  - a near-degenerate pair loses identity and refuses;
  - synthetic designs exclude same-class neighbours closer than 3 %.
- **Family keys:** frozen rows read from a Quick Calibration result carry `UNCLASSIFIED` family keys (that record has
  no family classification). The SPEC v1.2 §8 family count is then not assessable from them.
- **Mesh and discretisation noise:** measured for the synthetic model only (basis-order convergence and the
  half-step check). Real FE convergence evidence is required.

## Synthetic-model limits

- The block model is a free-free homogeneous orthotropic parallelepiped with axes along the edges. It is not a
  sandwich and has no core, adhesive or orientation uncertainty.
- Its success (all nine recovered on a thick block at σ 0.03 %) proves the engine logic, not SP-13 identifiability.
- Family keys are exact symmetry classes of the block, not the M4.3 surface classifier.

## Software limits

- GUI tests need Tk with a display; Linux CI skips them (run locally on Windows).
- The research view is a menu item, deliberately not a header button of the two production workflows.
- The FE cost plan's resource figures are an ESTIMATE from the measured SP-13 per-evaluation profile.
