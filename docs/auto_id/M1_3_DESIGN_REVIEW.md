# M1.3 Design Review — Raw-FRF multi-mode fitting path

- **STATUS: DESIGN_ACCEPTED** (SUPERVISOR, 2026-10-04; decisions D-018 to D-022 in
  [DECISIONS.md](DECISIONS.md)).
- **M1.3 implementation is NOT STARTED.** No production code exists for M1.3.
- **Prepared on:** branch `auto-id/m1` (design review `ac1e0e3`; frozen in the commit
  `docs(auto-id): freeze M1.3 modal input architecture`).
- **Governing:** DECISIONS D-002 and D-018 to D-022; SPEC §4, §6 S1, §17; AUDIT K1;
  ROADMAP M1.3 and M1.4.

## 0. Accepted design (supersedes the proposal below where they differ)

**Approved architecture:**

```
FRF (dataset 58)
        |
        v
QC
        |
        v
optional fitting provider   (replaceable ModalFittingProvider; none active in v1)
        |
        v
validated curve-fitted dataset   (pinned, provenance, QC passed, admitted source label)
        |
        v
Auto-ID   (M1.1 source policy + M1.2 production input)
```

**Accepted decisions:**

| Id | Decision | Consequence for this design |
|---|---|---|
| D-018 | Auto-ID v1 production does not perform internal FRF→modal fitting; it accepts only validated curve-fitted modal datasets, so modal-identification uncertainty stays separate from material-identification uncertainty. | No built-in fit runs inside production Auto-ID v1. Section 3's "built-in multi-mode fit" becomes an optional provider outside the production path. |
| D-019 | Curve-fitted modal datasets are the only production identification input; peak-derived modes are forbidden. | Already enforced (M1.1 policy, M1.2 production input). |
| D-020 | Dataset-58 FRF data are QC and future fitting inputs only, never direct identification inputs. | FRF data feed QC (M1.4) and, later, a provider. |
| D-021 | Future modal fitting goes through a replaceable `ModalFittingProvider` interface. | The service sketched in section 5 becomes one implementation of a provider interface (section 0.1). |
| D-022 | Human modal selection only in research/review workflows; production cannot depend on manual mode selection. | Decision 9.4: a provider used for production must select poles by recorded rules only. Manual selection belongs to research/review results. |

### 0.1 `ModalFittingProvider` (interface intent; not implemented)

A provider takes a pinned FRF block and a recorded configuration. It returns a fitted
modal result with full provenance (section 6), per-mode QC (section 7) and a
deterministic content hash, or it refuses. Its output reaches Auto-ID only as a
**validated curve-fitted dataset**:

- the result is pinned as a fixture (store + SHA-256), like PolyMAX sets in M0.2;
- the result passes the M0.3/M1.2 checks;
- the result carries an exact provider/version `mode_source` label;
- the SUPERVISOR has admitted that label to the M1.1 policy. Until then it is
  `unknown` and refused.

External tools such as Testlab PolyMAX are, in effect, providers whose output already
arrives as dataset 55.

### 0.2 Status of the open decisions in section 9

- **Resolved:**
  - **9.4 human review:** D-022.
  - **Whether a fit runs inside production v1:** D-018 — it does not.
  - **How fitting plugs in:** D-021.
- **Still open, needed only when a provider is actually built:** 9.1 method family,
  9.2 bands, 9.3 orders and stabilisation, 9.5 uncertainty model, 9.8 dependencies.
- **Still relevant to QC (M1.4) and to fixtures:** 9.6 QC thresholds, 9.7 raw-FRF
  fixtures, 9.9 split of M1.3/M1.4 scope.

### 0.3 Conflict to resolve (recorded in D-018)

The frozen SPEC still describes a built-in multi-mode fit in three places:

- §4, the footnote to `modes.unv`;
- §6 S1, "or the built-in multi-mode fit (M1)";
- §17, the M1 acceptance criterion "SP13 from raw FRF".

ROADMAP M1.3 and the **M1 GATE** do too. Under D-018, production v1 cannot meet that
gate as written. Under the precedence rule (SPEC > DECISIONS), the SUPERVISOR must
explicitly resolve this, by a SPEC amendment or a redefined M1 gate, before the M1
stage gate is evaluated. This document does not change the SPEC or the gate.

---

*The sections below are the original proposal (`ac1e0e3`), kept for the record. Where
they describe a built-in fit inside production Auto-ID or manual pole selection, they
are superseded by section 0.*

## 1. Purpose

Some experiments exist only as raw FRFs (UNV dataset 58, Polytec or Testlab) with no
PolyMAX dataset 55. For those, an accepted built-in **multi-mode fit** turns the FRFs
into **curve-fitted** modal estimates. These estimates can then enter Auto-ID through
the same gates as PolyMAX data. Per ROADMAP M1.3, dataset 58 may be used for
identification only through an accepted multi-mode fit; peak-only results stay
QC/screening.

## 2. Current state and limitation

| Path | Code | Status for identification |
|---|---|---|
| Dataset 55/2414 (PolyMAX) | `universal_reader` (dataset-55 modal-set discovery, 2414 reader) | Accepted (`curve_fitted`) |
| Dataset 58 peak picking | `universal_reader._modes_from_frf_datasets`, `universal_frf_review.modes_from_frf_datasets` | Refused (`peak_derived`, M1.1) |
| CMIF close-mode SVD candidates | `cmif_separation`, `cmif_validation` | Refused (`peak_derived`, M1.1) |
| Production input | `services.production_modal_input` (M1.2) | Only manifest fixtures with source type `polymax-curve-fitted-dataset-55` |

**Consequence:** a raw-FRF-only experiment cannot currently enter Auto-ID. This is
intentional. AUDIT K1 recorded the failure modes of peak picking on real data:

- SP13 206.15 Hz is lost and a false 217.5 Hz mode is created;
- SP02 mode-1 damping is overestimated 2.7×;
- the 1.25 Hz minimum peak spacing cannot separate SP1 4a/4b (0.64 Hz apart).

**Existing assets a fit can reuse, without changing them:**

- `cmif_separation._build_multi_reference_frf_block` already builds a genuine
  response × reference × frequency FRF matrix. The block carries channel keys,
  coordinates, measured mask, mean coherence, coherence status and dropped or
  excluded channel bookkeeping.
- The pinned PolyMAX files of both accepted fixtures also contain dataset-58 records
  (dataset types 55, 58, 82, 151, 164, 2411). Whether these are the complete measured
  FRFs or a PolyMAX-processed subset must be checked before they are used (decision
  9.7).

## 3. Proposed architecture

```
dataset 58 FRF (pinned source: store + SHA-256)
        |
        v
FRF block (domain contract; built by the existing multi-reference builder)
        |
        v
multi-mode fitting  (pole estimation -> stabilisation/selection -> residues/shapes)
        |
        v
curve-fitted modal estimate  (f, zeta, complex shape per DOF, fit uncertainty,
                              QC flags, full provenance, deterministic content hash)
        |
        v
M1.1 source policy  (new exact mode_source label, admitted only after acceptance)
        |
        v
Auto-ID input  (M1.2 production path: manifest record with a fitted-set source type)
```

Principles:

1. **The fit is a reproducible artifact, not a live side effect.** A fitted modal
   set is written as a versioned, content-hashed result file outside git (like UNV
   and ODB files). It is pinned in the fixture manifest with its own SHA-256 and with
   the FRF source SHA-256 it was derived from. Auto-ID then consumes it through M1.2
   exactly like a PolyMAX set, and re-running the fit with the same inputs and
   configuration must give the same hash.
2. **The policy gate stays explicit.** The fit emits a new, exact `mode_source` label
   (proposal: `auto-id multi-mode FRF fit/<method>/<version>`).
   - M1.1 classifies it as `unknown`, and therefore refuses it, until the SUPERVISOR
     accepts that method and version.
   - Acceptance is a reviewed one-line change to `CURVE_FITTED_MODE_SOURCES` and
     `SOURCE_TYPE_MODE_SOURCES`, with its own changelog entry.
3. **No fallback.** If a fit fails or a QC refusal fires, the result is a refusal.
   Peak-derived modes are never substituted.
4. **FE never selects experimental modes** (SPEC S1). FE frequencies must not seed,
   select or reject poles. The current peak path's `target_frequencies` /
   `target_count` hints must not be used by the production fit.

## 4. Where the code should live

| Concern | Proposed location | Notes |
|---|---|---|
| FRF block domain contract | `src/domain/frf_block.py` | Immutable: frequency axis (Hz), complex H[response, reference, frequency], channel keys, units/quantity, coherence and its status, measured mask, source identity. A public adapter wraps the existing `_build_multi_reference_frf_block`; that builder is not copied. |
| Multi-mode fit service | `src/services/frf_multimode_fit.py` (a package if it grows) | Pure numerical service. No UI, no `install_*` layer, no global state, no Abaqus. |
| Fit result contract | `src/domain/modal_fit_result.py` | Fitted modes, per-mode QC, fit uncertainty, provenance, content hash, schema version. |
| Result serialisation | `src/services/modal_fit_artifact.py` | Write and read the result file deterministically (canonical JSON + NPZ or similar). Verify the hash on read. |
| Production integration | `src/services/production_modal_input.py` + manifest schema | A new source type maps to a loader for fitted-set artifacts. Same M0.3/M1.2 checks; M1.1 policy last. |
| CLI entry (optional) | `tools/` or a service function | "Fit this pinned FRF source with this configuration", producing an artifact plus a report. |
| GUI | none in M1 | The GUI comes last (M8). The existing peak and CMIF views stay diagnostic. |

## 5. Required interfaces (sketch, not final)

```python
# domain/frf_block.py
@dataclass(frozen=True)
class FrfBlock:
    frequency_hz: np.ndarray          # (n_f,), strictly increasing, uniform or declared non-uniform
    h: np.ndarray                     # complex (n_resp, n_ref, n_f)
    response_keys: tuple[tuple[int, int], ...]   # (node, direction)
    reference_keys: tuple[tuple[int, int], ...]
    quantity: str                     # e.g. "displacement/force"
    coherence: np.ndarray | None      # (n_resp, n_ref, n_f) or (n_f,), with status
    coherence_status: str             # "computed" | "unavailable" | "parse_error"
    source_sha256: str
    content_hash: str

def frf_block_from_datasets(datasets, geometry, *, source_sha256) -> FrfBlock: ...

# services/frf_multimode_fit.py
@dataclass(frozen=True)
class MultiModeFitConfiguration:
    method: str                       # decision 9.1
    method_version: str
    bands_hz: tuple[tuple[float, float], ...]   # decision 9.2
    model_orders: tuple[int, ...]               # decision 9.3
    stabilisation: Mapping[str, float]          # decision 9.3
    selection_rule: str                         # decision 9.4
    suspension_max_hz: float                    # SPEC S1 / passport

def fit_multimode(block: FrfBlock, config: MultiModeFitConfiguration) -> ModalFitResult: ...
    # raises MultiModeFitRefusal(reason, evidence) instead of returning partial results

# domain/modal_fit_result.py
@dataclass(frozen=True)
class FittedMode:
    frequency_hz: float
    damping_ratio: float
    shape: np.ndarray                 # complex, (n_points, 3) with an explicit measured mask
    frequency_sd_hz: float | None     # contribution to Sigma_meas (SPEC uncertainty table)
    damping_sd: float | None
    qc: Mapping[str, object]          # section 7 flags and values

@dataclass(frozen=True)
class ModalFitResult:
    modes: tuple[FittedMode, ...]
    provenance: Mapping[str, object]  # section 6
    content_hash: str
    def to_modal_dataset(self) -> ModalDataset: ...   # exact mode_source label, dataset_type marker
```

## 6. Required provenance (per fitted set)

- **FRF source:** file name, SHA-256, size, store-relative location (as in M0.2); the
  dataset-58 channel inventory (keys, count) and its hash; reference DOFs used and
  dropped; the coherence source.
- **Signal properties:** frequency band(s), Δf, the number of spectral lines, units /
  quantity, and any windowing or zoom information present in the file.
- **Method:** name, version, every configuration parameter, model orders tried,
  stabilisation thresholds, and the pole-selection rule with each decision (accepted
  and rejected poles, with the reason).
- **Human review:** if any manual pole decision is allowed (decision 9.4), who made it,
  when, and why, stored in the artifact so the result stays reproducible.
- **Code identity:** git commit of the fitting code and numeric library versions.
- **Result:** per-mode estimates with uncertainty, all QC values and flags, the
  content hash, and the schema version.
- **Determinism:** no random seeds, or recorded fixed seeds; the same inputs and
  configuration must give the same content hash.

## 7. Required QC (shared with M1.4; flags recorded per mode)

| Check | Rule source | Proposed consequence |
|---|---|---|
| Unresolved resonance | SPEC S1: 2ζf < 3Δf | Flag; refuse the mode as identification input unless a resolution decision says otherwise |
| Coherence at resonance | SPEC S1: < 0.9 | Flag; a missing or unparsable coherence channel is a flag, never a pass (same rule as the current peak path) |
| Phase complexity | SPEC S1 (MPC/MPD-type metric; definition is decision 9.6) | Flag |
| Suspension band | SPEC S1: f < `suspension_max_hz` | Discard (never identification input) |
| Fit quality | New: normalised FRF reconstruction error per band | Flag or refuse above a threshold (decision 9.6) |
| Stabilisation | New: pole stable across orders (f, ζ, shape) | A pole that is not stable is never selected |
| Experimental AutoMAC | SPEC S1: off-diagonal > 0.5 | Flag "indistinguishable by grid" |
| Excitation adequacy | SPEC §15 (SP13 206 Hz barely excited) | Flag modes with low participation at every reference |
| Agreement with PolyMAX | Validation only, where both exist | Report Δf, Δζ and MAC; never used to tune or select |

## 8. Tests needed

1. **Synthetic FRFs with known poles:** single mode, well separated, and closely
   spaced pairs below the current 1.25 Hz peak spacing (including about 0.64 Hz).
   Light damping (0.1–0.3 %), multiple references, and several noise levels.
   - Recover f, ζ and shape within stated tolerances.
   - Produce no spurious modes.
   - Leave unresolved pairs flagged rather than merged.
2. **Determinism:** the same input and configuration give an identical content hash;
   changing any configuration field changes it.
3. **Refusals:**
   - missing or unparsable coherence (as flag or refusal, per decision);
   - insufficient Δf;
   - no stable poles;
   - a band containing only suspension modes;
   - a corrupted artifact (hash mismatch);
   - an unaccepted method label, which M1.1 must refuse as `unknown`.
4. **Policy integration:**
   - before acceptance the label is refused;
   - after the reviewed policy-table change, a pinned fitted-set fixture passes M1.2;
   - peak-derived output is still refused.
5. **Real-data M1 gate (SPEC §17 / ROADMAP), SP13 from raw FRF:**
   - 206.15 Hz and 212.61 Hz are found within ±0.05 Hz of PolyMAX;
   - no false mode near 217.5 Hz;
   - ζ within 30 % of PolyMAX.

   It also needs a fixture record for the raw FRF source; see decision 9.7.
6. **SP02 check:** mode-1 damping against PolyMAX (the K1 2.7× overestimate must not
   recur).
7. **No regression:** the existing peak and CMIF diagnostics and normal comparison
   stay unchanged.

## 9. Decisions required before implementation (not made here)

1. **Fitting method family.** Candidates: (p)LSCF / PolyMAX-like, rational-fraction
   polynomial, LSCE, a frequency-domain subspace method. Shapes come from an LSFD-type
   residue estimate.
2. **Band strategy.** Global fit, or local bands around candidate regions. If local,
   how bands are chosen without FE input, for example from CMIF or indicator peaks
   used only for band placement.
3. **Model orders and stabilisation criteria:** tolerances on f, ζ and MAC across
   orders.
4. **Pole selection:**
   - fully automatic rule, or human-reviewed;
   - if human-reviewed, how the review is recorded and kept reproducible.
5. **Uncertainty model** for Σ_meas (the SPEC expects a fit contribution typically
   < 0.1 %).
6. **QC thresholds and consequences.**
   - Fixed by the SPEC: 0.9 coherence and 2ζf < 3Δf.
   - Still to set: the phase-complexity metric and its limit, the reconstruction-error
     limit, and which flags refuse versus warn.
7. **Real raw-FRF fixtures:**
   - Which files are pinned for the M1 gate: the SP13 Polytec parent UNV (SHA-256
     `72547f4d…` in the REAL-1 SOURCE_FREEZE), or the dataset-58 records inside the
     pinned PolyMAX file.
   - Which store holds them.
   - How the manifest schema represents a fitted-set fixture (schema
     `experiment-fixture-manifest/2` or a new source type).
8. **Dependencies:** pure NumPy/SciPy, or a third-party modal-analysis library
   (licence, maintenance, determinism).
9. **M1.3 / M1.4 split:** whether QC is implemented with the fit (M1.3) or separately
   (M1.4) with M1.3 recording raw values only.

## 10. Non-goals

- No change to the peak-picking or CMIF code paths; they remain diagnostics.
- No change to PolyMAX import, registration, pairing, MAC, thresholds or modal
  algorithms.
- No use of FE results to select, seed or validate experimental poles.
- No GUI work (M8).
- No Abaqus.

## 11. Risks

- **Close modes:** lightly damped close modes (SP1 0.64 Hz, SP13 206/212 Hz) are the
  hardest case. Without enough Δf or reference diversity, the honest result is
  "unresolved". The design must make that outcome easy to report and impossible to
  mask.
- **Dependence on Testlab:** a method validated only against PolyMAX could inherit its
  biases. PolyMAX agreement is a validation check, not a tuning target.
- **Missing raw data:** raw-FRF quality and channel coverage vary between files.
  Fixture pinning (decision 9.7) is a prerequisite for a credible M1 gate.
