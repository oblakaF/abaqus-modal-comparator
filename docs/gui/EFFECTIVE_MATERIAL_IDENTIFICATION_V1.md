# Effective Material Identification v1

## Purpose

Effective engineering property identification from modal experiments.

This v1 freeze records the completed SP13 workflow and its GUI presentation.
The identified quantities are engineering properties of the FE digital twin;
the freeze does not change the scientific solver, inverse method, sensitivity
method, modal-family mathematics, or historical REAL outputs.

## Supported workflow

```text
Experiment
-> FE model
-> correspondence
-> sensitivity
-> identification
-> validation
-> report
```

The GUI presents existing evidence from each stage. It does not initiate
Abaqus, calculate sensitivities, or run an inverse identification.

## Current identified parameters

- Ex
- Ey
- Gxy

## Fixed parameters

- core
- density
- adhesive
- geometry

## Interpretation

The results are **effective homogeneous face-sheet properties**.

They are not:

- fibre properties;
- ply properties;
- unique laminate constants.

## Current limitations

- Laminate architecture is unknown.
- Model-form limitations remain.
- Gxy is weighting-sensitive.

## Frozen status

- Specimen: SP13.
- GUI workflow: GUI-0 through GUI-6 complete.
- Validation and report-export presentation are complete.
- Scientific backend and validated mathematics are unchanged by the GUI work.
- Acceptance baseline: 462 tests passed and 6 skipped.
