# REAL-FIT.R3 report: Stage A applicability and cross-check

Base: `fb169a8e249aaf33c76ec5125f2aae0643b17f18`, branch `feature/materials-offline-v1`.

## Result

**STAGE_A_CROSS_CHECK: NOT_AVAILABLE.** No second numerical-method result was obtained.

No complete, provenance-verified `STAGE_A_MATRIX_3D` package for the M11 single CFRP plate exists in the authorised local assets.
Without one, the backend cannot compute or fit frequencies of that plate. I did not substitute a synthetic package or matrices of
another FE model, and I wrote no new package. There was no Abaqus run, no new FE matrix, no source change and no code change.

## What the backend requires

The requirements come from `src/services/plate_forward_adapter.py` and `src/services/matrix_model_service.py`.

- **A package folder with `stage_a_package.json`**:
  - schema `abm/stage-a-matrix-package/v1`;
  - `model_kind = STAGE_A_AFFINE_BASIS` and parameters `(D11, D12, D66)` with constraint `D22=D11`;
  - matching `specimen_id`/`model_id`, the units, the evidence kind and the validity domain;
  - one matrix archive whose SHA-256 and size match the manifest.
- **An affine basis** `K_ref, dK/dD11, dK/dD12, dK/dD66` with `M_ref` (and `dM/dD11` if one is stored). `build_stage_a_affine_basis`
  recovers it from four Abaqus `*MATRIX GENERATE, STIFFNESS, MASS` jobs on the same mesh: the reference point plus 1 % perturbations of
  D11, D12 and D66, with a general shell section given as an A/B/D matrix.
- **A normal ODB modal extraction does not satisfy this,** and the adapter cannot build the package from one.

## Search and candidates

**Where I searched:** by file name, for `stage_a_package.json`, `*.mtx`, `*.npz`, `*stage_a*` and `*_STIF*`/`*_MASS*`. I did not
scan `D:\` or `D:\git` as a whole. The folders:

- `D:\git\abaqus-modal-comparator`;
- `D:\git\abaqus-modal-comparator-work`;
- `I:\sandwich`, read only.

I also searched `*.inp` files in the M11 run folders, `external_models` and `I:\sandwich` for `MATRIX GENERATE`.

**Results:**
- **No `stage_a_package.json` exists anywhere** in these locations.
- **The only `MATRIX GENERATE` deck** is SP15 (row 2 below).
- **No such deck exists for M11.**

| # | Candidate | SHA-256 | Why it is not usable |
|---|---|---|---|
| 1 | `…-work\runs\m11_carbon_plate\r65\out\r65_all_matrices.npz` | `ab660d5e…6c32` | Holds 480 arrays of shape 10×14: MAC matrices, experimental against FE modes. No stiffness or mass. |
| 2 | `I:\sandwich\Abaqus Results\temp\12 sampls\results\SP15\test\CFRP_PLAIN_520_STAGEA_baseline_{STIF1,MASS1}.mtx` | STIF `f297c913…5dfc`, MASS `68be7713…50b6` | A different specimen (SP15, 500×500 mm, deck `CFRP_PLAIN_520_STAGEA`). It is only one reference pair, with none of the three perturbation pairs and no manifest. |
| 3 | `analysis\stage_a_synthetic_recovery_c2d\…_{STIF1,MASS1}.mtx`, and the identical files in `c2e` | STIF `4fbce40c…7af2`, MASS `c21e249b…0b6` | A synthetic recovery campaign on the SP15 template, with synthetic truth `D = 57.096 N·mm`, `r = 0.05`. It is a single optimum check pair. The basis it used (`stage_b2`, in an old session scratchpad) no longer exists, and it was SP15 in any case. |

The M11 FE model is
`I:\sandwich\Abaqus Results\temp\CFRP_S4R_0875_FreeFree.inp` (SHA-256 `962f75f2…81df3`).

- **It is a normal Lanczos modal step:** S4R elements; `*Shell Section` 0.875 mm with 5 integration points; engineering constants
  E1 = E2 = 56 000, E3 = 8 500 MPa, ν12 = 0.05, G12 = 5 000 MPa; density 1.498e-9 t/mm³.
- **It has no matrix-generation step** and no general A/B/D section.

## Model and assumption differences

These differences would govern a Stage A cross-check. They are recorded for review; none was evaluated.

| Aspect | Ritz E1 = E2 study (R1/R2) | Stage A, if a package existed |
|---|---|---|
| Kinematics | Kirchhoff plate, Ritz series | Abaqus S4R shell matrices (affine basis): first-order shear and the FE discretisation |
| Parameters | E, G12 with ν12 fixed at 0.05; thickness and density fixed from the INP | (D, D66, r) with D22 = D11 and r = D12/D fitted freely; thickness and mass come from the mesh and the stored M |
| Comparison | E1 = E2 means D11 = D22 and D12/D11 = ν12, so r ↔ ν12 maps exactly | A Stage A r ≠ 0.05 would be a difference in the model hypothesis, not in the data |
| Mass | ρ·t fixed | M_ref, plus `dM/dD11` if stored (an artefact of the section definition, which would have to be reported) |

Both methods would use the same PolyMAX frequencies, the same rank hypothesis and the same FIT/HOLDOUT records. Even so, agreement
would show only that two numerical models agree. It would be neither physical validation nor 10 % property accuracy.

## What is possible without new Abaqus calculations

1. **Surrogate against Abaqus at the INP point.** This is already done (REAL-FIT.R1): Ritz reproduces the 14 stored S4R elastic
   frequencies within +0.12 % / −0.04 %. It is a forward check at one point, not a fit.
2. **A one-parameter FE scaling fit from the existing `.dat` frequencies.** This is possible but not run. If every modulus scales by a
   common s, with ν, thickness and mass fixed, the S4R frequencies scale exactly as √s. The existing frequencies therefore give an
   exact FE fit of one parameter: the modulus level at the INP's fixed ratio E:G12 = 56 000:5 000. It can be compared with the same
   one-parameter Ritz fit. It cannot separate E and G12, so it does not replace Stage A.
3. **A Ritz refit in the Stage A coordinates (D, D66, r) with r free.** This is possible through the existing Ritz backend, but it is
   the same numerical method (Kirchhoff–Ritz) and therefore not an independent second method.

## What a real Stage A cross-check would need

All of the following require the owner's decision, and items 1–3 include a HUMAN gate for Abaqus:

1. Four `MATRIX GENERATE` jobs on the M11 mesh, with a general shell section equivalent to the INP section at the reference point,
   plus the 1 % D11, D12 and D66 perturbations. This means new Abaqus runs, which this task did not authorise.
2. Building the basis with `build_stage_a_affine_basis`, then writing the package with `write_stage_a_package`. The package needs
   specimen/model identities, a node map and a declared validity domain.
3. Verifying the package's reference-point frequencies against the existing S4R `.dat`, which differs from the package's own deck in
   its section definition.
