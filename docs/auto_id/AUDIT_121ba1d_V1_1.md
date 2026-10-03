# Audit of Modal Comparator 121ba1d against the Auto-ID goal — v1.1

| Item | Value |
|---|---|
| Version | 1.1, accepted 2026-10-03 after the second reviewer's comments |
| Object | `121ba1d06b7c268b3051f1407a3ea26a9027dca3` (package `Abaqus_Modal_Comparator_Audit_121ba1d.zip`) |
| Goal audited | experiment + model → Abaqus Engineering Constants at 1–5 % precision (8 % maximum) |
| Real data used by the auditor | SP02 (honeycomb, Polytec UNV 2026-08-03), SP13 (auxetic, Polytec UNV 2026-09-09), LMS table `Experiment_Freq_damping_LMS.xlsx` (not in Git) |
| Companion | [SPEC_V1_1.md](SPEC_V1_1.md) |
| Archival source | [source/Audit_ModalComparator_121ba1d_AutoID_v1.1.docx](source/Audit_ModalComparator_121ba1d_AutoID_v1.1.docx) (Russian original) |

This is the accepted audit in Markdown. Finding ids are stable and are cited from
the SPEC, ROADMAP and DECISIONS. Desirable findings are numbered **J1–J3** here
(Ж1–Ж3 in the Russian original).

## 1. Summary

The normal Modal Comparator is carefully built. The key scientific principles claimed
for it are implemented in code: geometry is selected without MAC, admissibility is
applied before Hungarian assignment, MAC is computed only on measured DOFs, and INP
rewriting is deterministic and limited to permitted fields.

The goal "the user supplies two files and gets E1 = 45000 at 1–5 %" is not reachable
in the current form. There are four reasons, and only one of them is a code gap:

1. Identification currently takes experimental frequencies and shapes by a peak
   method on a 0.3125 Hz grid. Resonances are narrower than one spectral line. On
   SP13 one mode is lost and one false mode is created (**K1**).
2. "Rank 2" is computed with machine tolerance and says nothing about achievable
   precision. A criterion tied to the 5 % / 8 % targets is needed (**K2**).
3. Sandwich-only G12 is confounded with adhesive, core and interface. Without
   independent constraints on those it cannot be IDENTIFIED. Torsional-mode scatter
   between nominal repeats is 6–25 % (**K3**).
4. Polytec geometry is uncalibrated and the panels are near-square. Without a
   specimen passport, automatic registration is fundamentally ambiguous, and the
   program correctly refuses (**K4**).

The single missing engineering part is the orchestrator candidate → Abaqus → ODB →
pairing → residual → step (**V1**). All building blocks exist. A realistic target
after the fixes: E_in-plane at 2–5 % per carbon family (with measured face
thickness), and G12 IDENTIFIED from the bare plate (Stage A, already partly
implemented). The sandwich gives secondary G12 evidence.

## 2. Test baseline (corrected in v1.1)

Full suite on **Linux, Python 3.12, tkinter under xvfb**:

| Ran | Passed | Failed | Skipped |
|---:|---:|---:|---:|
| **873** | **870** | **1** | **2** |

`unittest` summary: `Ran 873 tests … FAILED (failures=1, skipped=2)`.

The known failure is **V7**, cross-platform Windows-path handling in a UI test. (v1
erroneously stated 872 passed.)

## 3. What the auditor did

- Ran the full test suite (above).
- Ran `universal_reader.load_universal_modal_file` on the real SP02 and SP13 UNV
  files and compared the result with LMS PolyMAX frequencies and damping.
- Ran `reviewed_core.geometry_alignment_candidates` on the real SP02/SP13 scan grids
  against dense plate grids 510×515 and 510×520 (m and mm).
- Read the code on pairing and gates, registration, ODB cache, identifiability,
  inverse solver, shared-carbon forward, runner and documentation.
- Made an independent Ritz sensitivity estimate (free-free orthotropic Kirchhoff
  plate, 510×515 mm, stiffness from face sheets only, ν12 = 0.05). Core shear and
  adhesive were ignored, so this is an upper bound on parameter distinguishability.

**Not verified in this audit:** analytic eigenvalue sensitivity; details of
`FrozenRegistration.replay`; subspace cluster handling; provenance completeness;
`install_*` architectural coupling. Real ODB/INP files were not supplied, so the
Abaqus path was checked by code reading only.

## 4. What the experimental data show

### 4.1 Polytec file format

Both UNV files contain only dataset 58: 121 points (11×11 grid), H1 velocity/force,
coherence and cross spectrum, 1600 lines over 0–500 Hz, Δf = 0.3125 Hz. There are no
curve-fitted modes (dataset 55/2414). One measurement direction (dir 3). The
measured-DOF mask is detected correctly (U3 only). Coordinates lie in plane z = −1
and are uncalibrated camera coordinates.

### 4.2 Peak method versus PolyMAX on real files

| Specimen / range | LMS PolyMAX | Program (peak method) | Comment |
|---|---|---|---|
| SP02, mode 1 | 28.006 Hz, ζ = 0.24 % | 28.12 Hz, ζ = 0.64 % | +0.4 % in frequency; damping overestimated 2.7× |
| SP13, 200–230 Hz | 206.15 / 212.61 / 228.75 Hz | 212.50 / 217.50 (ζ 2.1 %) / 229.06 Hz | 206.15 lost (only a shoulder); 217.5 Hz peak is false |
| SP02, < 20 Hz | — | 5.00 / 7.81 / 10.31 / 13.75 / 15.62 Hz, ζ up to 49.5 % | suspension and noise; 5.00 Hz sits on the search boundary |
| SP13, 94–97 Hz | 94.43 / 96.55 Hz | 94.38 / 96.56 Hz | pair 4a/4b separated; coherence at peak drops to 0.82 |

Half-power bandwidth is 2ζf. For SP02 mode 1 that is ≈ 0.13 Hz, less than one line.
Half-power damping therefore fails on these data, and peak frequency is quantised by
±0.16 Hz (±0.6 % at mode 1, ±0.2 % near 90 Hz).

### 4.3 Repeatability of nominally identical panels

| Pair | Mode 1 (torsion) | Modes 2–3 | Modes 4–9 | Note |
|---|---|---|---|---|
| SP2 → SP10 (honeycomb, old plain) | 28.01 → 29.72 Hz (+6.1 %) | +3.2 % / +1.9 % | +1.3 … +4.0 % | clean repeat pair (assuming equal dimensions) |
| SP1 → SP13 (auxetic, old plain) | 25.39 → 31.64 Hz (+24.6 %) | labels 2/3 swapped | −3 … +5 % | not a clean repeat: SP1 trimmed to core (≈502×499 mm), SP13 not (≈510×520 mm) |

**Specimen-to-specimen scatter is not Σ_setup.** The 1–4 % (modes 2–9) and ≥ 6 %
(torsional mode 1) differences are specimen-to-specimen scatter, not observation
noise. They belong at family level, as specimen parameters with priors. One
specimen's Σ contains only the repeatability of a repeat test of **the same** panel
(remount, excitation reinstallation). Only repeat testing of the same specimen
estimates setup/retest scatter, and it must be measured separately.

### 4.4 Ritz sensitivities

In a free orthotropic plate each mode splits S = ∂ln f/∂ln p between E and G12 with
S_E + S_G = 0.5. For 510×515 mm, E = 52 GPa, G12 = 4.5 GPa:

| Ritz mode | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| f / f1 | 1.00 | 3.18 | 3.30 | 3.79 | 3.84 | 6.16 | 8.85 | 9.02 | 9.26 |
| S_E | 0.02 | 0.50 | 0.50 | 0.37 | 0.37 | 0.29 | 0.50 | 0.50 | 0.45 |
| S_G12 | 0.48 | 0.00 | 0.00 | 0.14 | 0.13 | 0.21 | 0.00 | 0.00 | 0.05 |

| Frequency noise σ_f per mode | sd(E) | sd(G12) | κ |
|---|---|---|---|
| 0.2 % (measurement only) | 0.17 % | 0.37 % | 2.4 |
| 1 % | 0.83 % | 1.85 % | 2.4 |
| 3 % (with repeatability) | 2.5 % | 5.5 % | 2.4 |

The two-parameter problem is well conditioned (κ ≈ 2.4), but G12 information comes
mainly from mode 1 and partly from modes 4a/4b and 5. Real f2/f1 is 2.65 (SP02) and
2.34 (SP13), against 3.18 for a face-only model. Adhesive, core and edge contact
contribute noticeably to real torsional stiffness. That is the substance of K3.

## 5. Findings summary

| ID | Priority | Category | Finding | Changes prior results? |
|---|---|---|---|---|
| K1 | CRITICAL | scientific / numerical | Peak-derived raw-FRF modes on Δf = 0.3125 Hz used as identification input | **NO** for CARBON-4C/5A (PolyMAX) |
| K2 | CRITICAL | numerical | Rank uses eps tolerance; no criterion tied to 5 % / 8 % precision | interpretation of "rank 2": yes |
| K3 | CRITICAL | scientific | Sandwich-only G12 confounded with core/interface | interpretation of sandwich G12: yes |
| K4 | CRITICAL | UX / architecture | Uncalibrated near-square grids give ambiguous registration (16 distinct candidates) | NO |
| V1 | IMPORTANT | missing integration | No Abaqus-loop orchestrator for direct sandwich Engineering Constants | NO |
| V2 | IMPORTANT | architecture | `shared_carbon_forward` hard-coded to SP02/SP13 and machine paths | NO |
| V3 | IMPORTANT | scientific | Direct E fit does not propagate face thickness / offset uncertainty | uncertainty of E: yes |
| V4 | IMPORTANT | scientific / software | Inverse loop reuses normal-comparator pairing gates at every candidate | UNKNOWN |
| V5 | IMPORTANT | software | Manual ODB cache identity = path + size + mtime | NO (with unique job names) |
| V6 | IMPORTANT | software / UX | Suspension/noise/boundary FRF peaks enter candidate lists | NO |
| V7 | IMPORTANT | software | Linux test baseline has one Windows-path failure | NO |
| J1 | DESIRABLE | tests | No real UNV/PolyMAX regression fixtures | NO |
| J2 | DESIRABLE | architecture | Multiple wrapper layers; Auto-ID must stay a thin explicit service | NO |
| J3 | DESIRABLE | QC / UX | Missing frequency-resolution and coherence-at-resonance flags | NO |

## 6. Findings in detail

### CRITICAL

#### K1 — Peak-derived raw-FRF modes are unsuitable as production identification input

- **Where:** `src/universal_reader.py` (`_detect_frf_peak_indices`,
  `_modes_from_frf_datasets`, `_estimate_half_power_damping`).
- **Observed:** with only dataset 58, modes are built from peaks of the FRF-matrix
  norm after Savitzky–Golay smoothing (≈ 2 Hz window) with minimum peak spacing
  1.25 Hz. On real data: SP13 206.15 Hz lost, false 217.5 Hz created, SP02 mode-1
  damping overestimated 2.7×. Pairs closer than 1.25 Hz cannot be separated (SP1 4a/4b
  spacing is 0.64 Hz).
- **Required:** identification accepts only curve-fitted modes: dataset 55/2414 from
  Testlab PolyMAX, or a built-in multi-mode FRF fit. Peak-derived modes are for
  viewing and screening only.
- **Why it matters:** mode 1 is the main G12 source (S ≈ 0.48). ±0.6 % quantisation
  gives ±1.2 % in G12. A false mode within ±15 % at MAC ≥ 0.5 could partner an FE mode
  and move the optimum.
- **Fix:** (1) refuse peak-derived input to identification with an explicit message;
  (2) make Testlab UNV dataset 55 with shapes the main path; (3) optionally a built-in
  LSCF / rational-fraction fit around each candidate; (4) measurement protocol:
  zoom-FFT or Δf ≤ ζ·f/3.
- **Impact on accepted CARBON-4C/5A: NO.** Their frozen registration/evidence uses
  PolyMAX modal sets:
  - SP02: `SP02_polymax_retry_260803.unv`, modal set `bravo-1`
    ([docs/registrations/SP02_frozen_registration.json](../registrations/SP02_frozen_registration.json));
  - SP13: `SP13_a_polymax.unv`, modal set `best`, 289 points
    ([docs/registrations/SP13_frozen_registration.json](../registrations/SP13_frozen_registration.json)).

  Rule for the future: peak-derived modes are prohibited as production Auto-ID input.
  Any other earlier study is checked against the provenance of its experimental modal
  sets.

#### K2 — Machine-precision rank does not establish useful parameter precision

- **Where:** `src/services/identifiability_service.py` (`_rank_tolerance`; with
  `rcond=None` the tolerance is max(m, n)·eps·σ_max).
- **Observed:** a tolerance of order 1e-15·σ_max. Finite-difference Abaqus
  sensitivities never fall below it, so almost any matrix is full rank. "Rank 2" only
  says the columns are not exactly collinear.
- **Required:** practical identifiability with a verdict against target precision:
  sd(ln p_j) = sqrt([(S̃ᵀS̃)⁻¹]_jj) for S̃ = Σ^(−1/2)·S with realistic Σ (measurement +
  same-panel repeatability), with specimen parameters and their priors in the same
  matrix, and a verdict at 5 % / 8 %. Model form is assessed after fitting (SPEC §14),
  not through Σ. The rank threshold must be no lower than finite-difference noise, for
  example rcond ≥ 1e-3.
- **Why it matters:** with measurement-only Σ (0.2 %) the program would report
  "G12 ± 0.4 %" while specimen scatter is an order of magnitude larger.
- **Reproduction:** any 9×2 S with nearly collinear columns (0.1°) gives rank 2 with
  `rcond=None`.
- **Fix:** `PracticalIdentifiability` with sd_j, verdict ∈ {IDENTIFIED, WIDE,
  NOT_IDENTIFIABLE} and source contributions. Default rcond tied to finite-difference
  noise. Verify no path can override NOT_IDENTIFIABLE.
- **Changes prior results:** the interpretation of "rank 2", yes. Numbers, no.

#### K3 — Sandwich-only G12 is confounded with core/interface

- **Where:** `src/services/shared_carbon_forward.py` (candidate E_in-plane, G12);
  shared-carbon v1 formulation. Class 3 (model-form), not a code defect.
- **Observed:** in a free sandwich panel, mode 1 (torsion) has the largest G12
  sensitivity (S_G ≈ 0.48), modes 4a/4b about 0.13, mode 5 about 0.21, others 0–0.05.
  Real full-Abaqus CARBON-5A sensitivity also shows E and G12 are locally
  distinguishable. **The problem is not absence of sensitivity but confounding** with
  core and interface. Mode-1 scatter between repeats is +6.1 % for SP2 → SP10
  (Δln G ≈ 0.12, about 13 % in G12), +24.6 % for SP1 → SP13 (about 58 %, but
  dimensions differ). Real f2/f1 (2.34–2.65) is far from the face-only model (3.18).
- **Required:** primary G12 source is the bare plate (Stage A: D66 = G·t³/12, torsion
  without adhesive and core). The sandwich gives secondary evidence. Sandwich-only G12
  is IDENTIFIED only with independent core and interface constraints and a passed
  family-consistency test, decided by the full practical-identifiability matrix
  including specimen parameters (SPEC §5.1, §10).
- **Why it matters:** otherwise the optimiser writes the bond quality of a specific
  panel into "carbon property", and two specimens from one sheet get different G12.
  That is exactly the SP02/SP13 conflict.
- **Changes prior results:** the interpretation of any sandwich-derived G12, yes.

#### K4 — Near-square uncalibrated camera grids have physically ambiguous registration

- **Where:** `src/reviewed_core.py` (`geometry_alignment_candidates`,
  `_select_unambiguous_geometry`).
- **Observed:** real SP02/SP13 grids against the dense plate grid give 32 candidates,
  16 physically distinct: two scales (0.79 or 0.85 vs 1.0) × 8 orientations of the
  square group, all with the same normalised RMS (0.0028). The code raises
  `GeometryOrientationAmbiguousError`. Scientifically correct, but in "two files" mode
  the program would stop on every near-square panel.
- **Required:** calibration and orientation set once per specimen from physical data
  (specimen passport), not chosen by a solver. **The correct behaviour is refusal, not
  choosing orientation by MAC.**
- **Fix:** `specimen.json` with measured dimensions, a "grid to edges" flag or grid
  corner coordinates, and an orientation marker (which UNV node is at marked corner
  A). PSV protocol: enter a real distance or reference length, start the grid at
  corner A, photograph it.
- **Changes prior results:** NO.

### IMPORTANT

#### V1 — No complete orchestrator for direct sandwich Engineering Constants

- **Where:** `src/material_identification_runner.py` (explicitly "no … Abaqus process
  integration"), `src/services/matrix_model_service.py`,
  `src/services/shared_carbon_forward.py`, `src/abaqus_bridge.py`.
- **Observed:** all components exist (Abaqus launch with timeout, deterministic INP,
  ODB extraction, FrozenRegistration, Stage-A pairing provider). There is no chain
  candidate → INP → Abaqus → ODB → extraction → registration → residual → step → stop.
  The inverse solver works only with the Stage-A affine matrix model.
- **Required:** an `auto_identification` service with a finite solve count (1 + 2n per
  iteration, at most 4–5 iterations), branch tracking, stop criterion, and resume after
  failure. No new `install_*` layer; a service module and a CLI entry point.
- **Changes prior results:** NO.

#### V2 — `shared_carbon_forward` is hard-coded to SP02/SP13 and machine-specific paths

- **Where:** `shared_carbon_forward.py` (`sp02_forward_baseline`,
  `sp13_forward_baseline`, `_SP0x_SOURCE_INP_SHA256`, `D:\Snadwich\…` source paths,
  material names, eigenvalue counts); `src/sp13_evidence_adapter.py`.
- **Required:** specimen data in a manifest (JSON); one code path for all specimens.
- **Fix:** `domain/specimen_manifest.py` plus a generic
  `write_forward_job_inp(manifest, candidate)`. Acceptance: SP02/SP13 INPs
  byte-for-byte identical to the current builder.
- **Changes prior results:** NO.

#### V3 — Direct E fit does not propagate face thickness / face offset uncertainty

- **Where:** `shared_carbon_forward.py`; compare
  [docs/ROADMAP_Stage_Inverse_Identification.md](../ROADMAP_Stage_Inverse_Identification.md) §1.
- **Observed:** the older roadmap correctly treats q_s = A·d_s² as primary and derives
  E with propagated uncertainty. Shared-carbon v1 fits E directly at the INP thickness
  and does not propagate t and d uncertainty.
- **Required:** for a sandwich δE/E ≈ δt/t + 2·δd/d. At t = 0.45 ± 0.02 mm and
  d = 2.41 ± 0.02 mm this is about 6 %, the whole precision budget. Thickness must be a
  specimen parameter with a measured prior; E is reported with full uncertainty. (The
  manufacturer's 0.4 mm is actually 0.45 mm, a 12 % difference.)
- **Changes prior results:** the uncertainty of any published E, yes.

#### V4 — Identification must not dynamically reuse normal-comparator pairing at every candidate

- **Where:** `src/services/stage_a_identification_service.py` (the production pairing
  provider calls the normal comparator per candidate with its defaults, MAC ≥ 0.50,
  |Δf| ≤ 15 %). The roadmap thresholds (0.7 / 0.85) were not found in code.
  `C3B2_MODE_IDENTITY_CAVEAT` states `cluster_subspace_residual_implemented: False`.
- **Required:** a named `IdentificationPairingPolicy`: MAC ≥ 0.8 at the reference
  point, frozen pair set, then FE-to-FE (mass-)MAC branch tracking. Close pairs (4a/4b,
  6a/6b) are handled as clusters with a mean-ln f residual.
- **Why it matters:** with soft gates, pairs 0.7–3 % apart can swap between
  iterations, the objective jumps, and the optimum can land on a foreign branch.
- **Fix:** pass the policy explicitly, strict by default. Test: a pair exchange
  between iterations stops the optimiser with a refusal.
- **Changes prior results:** UNKNOWN (for synthetic Stage-A campaigns).

#### V5 — Manual ODB cache identity based only on path/size/mtime is insufficient

- **Where:** `abaqus_bridge._source_signature`, `fast_cache._file_signature`.
- **Observed:** if a file is copied preserving timestamps (robocopy /COPY:DAT,
  7z/zip extraction, cloud sync) and the size matches, the cache accepts a foreign
  ODB. Inside shared-carbon, job names contain the INP hash, which protects the loop.
  The manual path is not protected.
- **Required:** content identity: SHA-256 of the ODB, or at least the source-INP hash
  plus the Abaqus job id / completion stamp.
- **Changes prior results:** NO (with unique job names).

#### V6 — Suspension/noise/boundary FRF peak candidates require QC filtering

- **Where:** `universal_reader._detect_frf_peak_indices` (lower_frequency = 5 Hz).
- **Observed:** SP02 has five candidates below 16 Hz with ζ up to 49.5 %; the 5.00 Hz
  peak is the search boundary. Gates prevent pairing, but users see them as unmatched
  experimental modes.
- **Required:** suspension threshold from the passport (or automatically from the
  largest relative frequency gap below the first clean-shape mode); edge maxima and
  candidates with ζ > 5 % rejected with a QC note. **Never use FE frequencies for
  this.**
- **Changes prior results:** NO.

#### V7 — Linux test baseline has one Windows-path failure

- **Where:** `tests/test_material_identification_ui.py::ProjectEvidenceStatusTests::test_selected_and_validated_states_display_correctly`.
- **Observed:** the test expects `panel.odb` from `C:\models\panel.odb`. On Linux
  `Path(...).name` does not split on backslash and returns the whole string. CI
  (ubuntu-latest) is expected to fail at this HEAD.
- **Fix:** platform-neutral file-name display (`ntpath.basename` or
  `PureWindowsPath` for backslash paths), or a platform-neutral test.
- **Changes prior results:** NO.

### DESIRABLE

#### J1 — Real UNV/PolyMAX regression fixtures are missing from automated tests

All 873 tests use synthetic data. Real features (the 206 Hz shoulder, suspension
peaks, uncalibrated grid) are not covered. Fix: add SP02/SP13 UNV fixtures (≈ 8.5 MB
compressed) through git LFS or an external fixture with pinned SHA-256. Reference
values: PolyMAX frequencies and FrozenRegistration hashes.

#### J2 — The application is layered through multiple wrappers

About 78 modules and 33 thousand lines in `src/`, with `*_hardening`, `*_reviewed`,
`final_*` and `install_*` layers. Comparison behaviour is assembled through several
wrappers (`modal_core.compare_modal_datasets` → `quality_control_reviewed` →
`quality_control` → `reviewed_core`), which makes "which gates actually applied" hard
to answer (see V4). **Auto-ID must remain a thin explicit service** (1–2 thousand
lines) with explicit policy passing. Refactoring the rest is not required.

#### J3 — Experimental QC needs explicit resolution and coherence-at-resonance flags

Mean coherence 0.99 hides dips at resonance (0.76 at 212.5 Hz and 0.82 at 96.56 Hz on
SP13), typical of leakage at insufficient resolution. Half-power damping with fewer
than three lines across the resonance is not flagged. Fix: flags *unresolved
resonance (2ζf < 3Δf)* and *coherence at peak < 0.9*, shown beside each mode in the
Auto-ID report.

## 7. Confirmed as correct

| Question | Result | Basis |
|---|---|---|
| Measured-DOF mask | correct | Only U3 detected on real UNV; MAC uses the mask |
| Geometry selected by MAC? | no — correct | `_select_unambiguous_geometry` uses only RMS and matched fraction; refuses when ambiguous |
| Admissibility before Hungarian; can an inadmissible pair pass? | correct | `_admissible_assignment`: forbidden cost + dummy "unmatched" + admissible re-filter |
| Sign of frequency error | correct | `frequency_error_percent = (FE − EXP) / \|EXP\|` |
| MAC in objective | not included | `inverse_solver` keeps MAC as pairing evidence; residual is frequency-only |
| INP determinism; extra lines touched? | correct | Fixed source SHA, original constants checked, only E1/E2/G12 and mode count change; job name = content hash |
| Does the GUI present research as production? | no | Material Identification tab is explicitly presentation-only |
| Stale ODB cache | partly | see V5 |
| Numerical rank | no | see K2 |
| Real data in tests | no | see J1 |

## 8. Recommended work order (archival)

1. V7 (CI) and J1 (real fixtures), so every later change is checked on SP02 and SP13.
2. K1: refuse peak-derived identification input; PolyMAX dataset 55 as main path. In
   parallel, export shapes from Testlab for SP02 and SP13.
3. K4 + V2: specimen passport and universal forward builder. Acceptance: existing
   SP02/SP13 hashes reproduced.
4. K2 + V3 + V4: practical identifiability, uncertainty budget with thickness, strict
   pairing policy.
5. V1: orchestrator and synthetic twin test.
6. K3: twill 350×350 bare plate via Stage A → G12 and D11; then sandwiches of the
   family → E_in; after CARBON-5F, q_G for sandwich G12.

The executable order is [ROADMAP.md](ROADMAP.md).

## 9. Changes in v1.1

- Test count corrected: 873 ran, 870 passed, 1 failed, 2 skipped (v1 wrongly said 872
  passed).
- K1: impact on CARBON-4C/5A is NO, based on the PolyMAX provenance of the frozen
  registrations.
- K3 reworded: not "sandwich G12 prohibited" but "without independent nuisance
  constraints, sandwich-only G12 does not receive IDENTIFIED". Mode 4a/4b and 5
  sensitivities clarified.
- §4.3: specimen-to-specimen scatter (family level) separated from same-panel retest
  repeatability (observation covariance).
