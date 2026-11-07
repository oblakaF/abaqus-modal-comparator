# REAL-FIT.R4 report: M11 Abaqus S4R validation preflight

**Status: REAL-FIT.R4 — PREFLIGHT_REVIEW_READY. Abaqus execution — NOT_AUTHORIZED; Abaqus was not launched.**

- **Branch:** `feature/materials-offline-v1`.
- **Base:** `496815f2aaa2ce602ae7dabd9f1899db5eb5f62a`. It equalled `origin/feature/materials-offline-v1`; fresh `origin/main` is
  `0bea1de6`.
- **Tree before work:** no tracked changes and the 25 untracked items, none modified in the preceding three hours.

Two trial decks were prepared and statically verified. **They are exploratory FE trial inputs**: diagnostic optimiser candidates, not
release values, material properties, calibration fragments or FE results. No FE result exists for them.

## Categories kept apart

| Category | Here |
|---|---|
| Experimental measurements | PolyMAX curve-fitted frequencies, `Polymax_bravo`, 11 records (UNV below) |
| Assumed M11 inputs | Geometry 301 × 300 mm, thickness 0.875 mm, density 1.498e-9 t/mm³, ν12 = 0.05 and E3/ν13/ν23/G13/G23 from the INP |
| Ritz-derived numerical estimates | The two mirror minima of the orthotropic (E1, E2, G12) Kirchhoff–Ritz tuning, rank-order correspondence (REAL-FIT.R1.F2/R2) |
| Proposed S4R forward inputs | The two decks below |
| FE results for the proposals | **None.** Not run |
| Identified material properties | **None released.** M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and Production Auto-ID BLOCKED are unchanged |

## Sources

All sources were read only. Their hashes were equal before and after the run.

| Source | SHA-256 |
|---|---|
| `I:\sandwich\Abaqus Results\temp\CFRP_S4R_0875_FreeFree.inp` (original M11 S4R deck) | `962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3` |
| `I:\sandwich\Abaqus Results\temp\CFRP_S4R_0875_FreeFree.dat` (reference only) | `f440592598a21bd23dd7fa68f1032ebcd4d0da4d33b48156adc68ec690625de9` |
| `I:\sandwich\exp\SPname_files_ROTATED_261103\300by300_plate_only_1mm_ROTATED_Polymax_261027.unv` | `76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d` |
| `D:\git\abaqus-modal-comparator-work\runs\real_fit_r2\proposal_free.json` (R2 export, the minima source) | `11c3c962d95d1700b6a21b61e97c09f9a22b028cfd24556c4542821190668ba6` |
| `D:\git\abaqus-modal-comparator-work\runs\real_fit_r2\results_r2.json` (R2 service probe) | `861c24a5b3bfef0d6429c74890791371a656a1bb90afd5bcf6157a30e8fb846a` |

The ODB copy used for the mode classification is
`D:\git\abaqus-modal-comparator-work\runs\real_plate_r1\fe\CFRP_S4R_0875_FreeFree.odb`, read through extracted modes as in R2.

**Provenance and agreement of the minima:**
- The R2 GUI export and the R2 service probe hold identical minima.
- A fresh `run_tuning` at the base reproduced them **bit for bit**: the same request, status `E1_E2_AXIS_ASSIGNMENT_NOT_IDENTIFIABLE`,
  347 evaluations and largest relative difference 0.
- The R1 export, which predates F1/F2, differs from them by about 1e-8 relative and was not used.
- Both minima come from the tuning's own independent searches. B is not a swapped copy of A: its E1 differs from A's E2 by 1.3 %, and
  its E2 from A's E1 by 1.5 %.
- The rank correspondence and holdout are exactly R2's. Nothing was re-matched or reoptimised.

## Material parameters, MPa

The values are exact doubles, written as the shortest repr that reads back identically.

| Constant | Original INP | Minimum A (`M11_RITZ_MINIMUM_A`) | Minimum B (`M11_RITZ_MINIMUM_B`) |
|---|---|---|---|
| E1 (material 1 = FE X) | 56000 | **59643.140320162354** | **44170.77433673189** |
| E2 (material 2 = FE Y) | 56000 | **43592.56647783119** | **58724.14887983508** |
| G12 | 5000 | **4824.07010224442** | **4817.417308245888** |
| E3, ν12, ν13, ν23, G13, G23 | 8500, 0.05, 0.3, 0.3, 3000, 3000 | unchanged | unchanged |
| Density, thickness | 1.498e-9 t/mm³, 0.875 mm (5 points) | unchanged | unchanged |
| Ritz cost (Σ ln² over FIT) | — | 0.0008452616410310549 (lowest) | 0.0008576605619306323 |

A and B are the two axis assignments the frequencies cannot distinguish. Which plate axis is stiff remains open, and neither is
preferred.

## Static diff and integrity checks

Each variant differs from the original in exactly one line, INP line 20239:

```
-56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.
+59643.140320162354,43592.56647783119, 8500.,  0.05,   0.3,   0.3, 4824.07010224442, 3000.     (A)
+44170.77433673189,58724.14887983508, 8500.,  0.05,   0.3,   0.3, 4817.417308245888, 3000.    (B)
```

The checks are recorded in the manifest: 111 per variant, all passed. Each one is evaluated in memory, again on the written bytes,
and again through the tuning service's own INP reader.

- **Line structure:** the line count is unchanged (20 264), and only the first `*Elastic` data line changed. CRLF line endings are
  kept, and the second `*Elastic` line ` 3000.,` is unchanged.
- **Material constants:** E1, E2 and G12 read back equal to the source doubles. Every non-target item is identical as text and as a
  number.
- **Model structure:** every keyword's content hash is equal, covering the keyword sequence, nodes (10 201), S4R elements (10 000),
  coordinates, connectivity, sets, `*Shell Section` `0.875, 5`, `*Density`, instance, step (Lanczos, 20 modes) and output requests.
- **Parse check:** `read_inp` returns unchanged E3/ν/G13/G23, density, thickness, plan 301 × 300, material and type, and no orientation.
- **Integrity:** the two decks differ from each other, and every source is unchanged.
- **Not covered:** Abaqus's own input check (datacheck) was not run, so parseability by Abaqus itself is not verified. The checks show
  only that the deck keeps the original's supported structure.

## Material-axis interpretation

The deck has no `*Orientation`, `*Transform` or `*Distribution`, no `orientation=` on the section and no composite section. The
single instance is translated by (251, 270, 0) without a rotation line, and all 10 201 nodes lie at z = 0. The element normals,
computed from the connectivity, are all +Z (10 000 of 10 000), so the smallest angle between a normal and global X is 90°.

Under Abaqus's documented default local shell directions:
- material 1 is the projection of global X onto the shell surface;
- material 2 is the normal × direction 1.

Therefore material 1 = FE global X and material 2 = FE global Y in every element. This matches the Ritz convention: D11 multiplies
w,xx², with x along the 301 mm FE X side.

**Limitation:** this rests on the documented convention plus the deck geometry. No solver output of local material directions has
been inspected. A requested direction output or a CAE orientation display in the authorised run would confirm it. No transformation
was added or invented.

## Generated files

These are outside Git, in `D:\git\abaqus-modal-comparator-work\runs\real_fit_r4_fe_preflight\`.

| File | SHA-256 |
|---|---|
| `decks\M11_RITZ_MINIMUM_A.inp` (871 645 bytes) | `a0668c28bb912ed55591a4847c73a5778fdb39d1811136a1a9d2cc0bf69c0927` |
| `decks\M11_RITZ_MINIMUM_B.inp` (871 645 bytes) | `69c485fba9280d19b318ce3867e194d34bf3e940997b725eb3afad2f67913a3a` |
| `decks\preflight_manifest.json` (every check, diff, source hash, axis analysis, reproduction) | `cc4181a77521d178cea5d6af073132b2c503fb8635e4d2a22510d48b6d164bd7` |
| `prepare_r4.py`, `prepare_r4_console.txt` | the run script and its output |

## Implementation

- **`src/services/research_fe_trial_preflight.py` (new):**
  - reads the two minima from a tuning export, and refuses unless all of the following hold:
    - the schema is right, the request is FREE and the status is MIRROR;
    - the export's INP hash equals the source deck's;
    - there are exactly two finite, distinct minima in ascending cost order;
    - the axis assignments and the fitted values agree with them;
  - accepts only one `*Material` with one `ENGINEERING CONSTANTS` `*Elastic` of 8 + 1 items, with no temperature, dependency or
    other parameters;
  - replaces only the three items, and refuses any value that does not round-trip exactly in 20 characters;
  - runs the structural, line-diff and material checks and the axis analysis;
  - writes only new files (exclusive create), never into the source folder, and fails if any check fails;
  - starts no process and has no Abaqus or matrix-service import.
- **Untouched:** no existing tuning, stability, Auto-ID, evidence or GUI code changed, and there are no `install_*` layers.
- **`tests/test_research_fe_trial_preflight.py` (new, 9 tests):**
  - both minima are transferred exactly;
  - non-target constants are kept;
  - the structure is unchanged and the diff is one line;
  - sources are untouched and outputs are never overwritten or written next to the source;
  - missing or ambiguous minima are refused (9 cases);
  - unsupported material definitions are refused (7 cases);
  - structural tampering fails the checks (6 cases plus the wrong minimum);
  - the axes are not established for a rotated instance or an explicit orientation;
  - an audit hook confirms that no process starts.

## Tests

| Command | Result |
|---|---|
| `python -m unittest tests.test_research_fe_trial_preflight` | 9 tests, OK |
| `python -m unittest tests.test_new_gui1_workspace` (import boundary) | 28 tests, OK |
| `python -m unittest tests.test_real_fit_r1_tuning` (tuning reader and solver, reused) | 27 tests, OK |
| Full suite | NOT_RUN (not authorised) |
| Abaqus datacheck or any solver run | NOT_RUN (not authorised) |

## Remaining blockers before an authorised Abaqus calculation

1. **Authorisation:** an explicit HUMAN gate for two Abaqus/Standard frequency jobs, with a work folder under
   `D:\git\abaqus-modal-comparator-work` and no outputs in Git.
2. **A comparison protocol declared before the run:**
   - which FE elastic modes are compared with which PolyMAX records (the same declared rank hypothesis, and FIT and HOLDOUT kept
     separate);
   - which shape check confirms the rank correspondence;
   - which metrics are reported.
   No tolerance should be chosen after seeing results.
3. **Axis confirmation in the run,** as above. Without it, the A/B labels rest on the default-direction convention.
4. **Model differences to keep in view:**
   - S4R includes transverse shear (G13 = G23 = 3000 MPa assumed) and discretisation; the Ritz surrogate is a Kirchhoff plate. At the
     INP point they agreed within +0.12 % / −0.04 % (REAL-FIT.R1), but agreement at the minima is not shown.
   - ν12 = 0.05, the thickness and the density remain assumptions. The moduli scale as ρ·t⁻² with them (REAL-FIT.R2).
5. **The A/B axis ambiguity stays open** whatever the FE result. Choosing between A and B by FE frequency fit would be the
   correspondence/orientation optimisation this task excludes; the physical orientation of the test plate is needed.

Abaqus was not launched. Static preflight is not FE agreement, and nothing here demonstrates the 10 % engineering-accuracy objective.
