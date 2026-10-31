# PRIORITY-9 — Plate Study > C. Physical Readiness Review

Branch `feature/plate-physical-readiness-rc4`, from `be7a07b` (PRIORITY-8-F2). Labels: RESEARCH_ONLY /
NOT_A_MATERIAL_PROPERTY.

The review is a dossier of one single plate's scientific readiness for a physical identification. It shows the owner:

- what is established and what is only supposed;
- what blocks the physical registration;
- whether mode identity can be established;
- which FE sensitivities exist and which parameters the FE model distinguishes;
- which parameters real experimental observations support;
- what the next scientifically admissible action needs.

It produces no new E1, E2 or G12. It creates no registration, mode pair, MAC, FIT / HOLDOUT set or fit, and starts no
Abaqus, solver, extraction, LM or Auto-ID.

The scientific result for the first real plate is in `docs/research/plate_physical_readiness_p9/RESULTS.md`.

## 1. Architecture

**Service: `src/services/plate_physical_review.py` (no Qt).** It reuses:

- `plate_registration_readiness`: `real_261027_evidence`, `evaluate`, `CLOSING_EVIDENCE`, the series link and the
  provenance rule;
- `plate_study`: the identities, the FE family, `EXPERIMENT_CONDITIONS`, the specimen record and `elastic_modes`;
- `plate_workbench`: `APPLICABILITY_VARIANTS` and `applicability_jobs`;
- `generic_plate_workbench`: `modal_diagnostics` (3 % close groups) and `diagnostics_from_previews`, plus the passport
  and evidence fingerprints;
- `generic_plate_evidence` and `generic_plate_offline_study` (sensitivity tables checked for their FE model);
- `research_results_reader`, which reads the PRIORITY-1–4 archive by SHA-256;
- the RCOND of `practical_identifiability`.

The PRIORITY-2 `SOLVER_RUNS.csv` / `BRANCH_TRACKING.csv` and the other files the review cites are read only with
their recorded SHA-256 (`ARCHIVE_FILES`).

**Panel: `src/new_gui/physical_review_panel.py`.** The third tab of the Plate Study page, wired in `window.py`. There
is no new `install_*` layer.

**Two profiles:**

- **`M11-261027`**, built from the Workspace: PLATE-300x300x1mm, NEXP29/PLATE300-1MM/S261027-ROTATED, Polymax_bravo,
  Abaqus M11 `S4R_0875_BASELINE`. The UNV must be `76db80ae…` and the FE manifest `354966da…`. Any other file, a file
  changed on disk since it was read, another modal set or another number of records or elastic modes is refused as
  **SOURCE_NOT_VERIFIED**.
- **`GENERIC`**, built from study B (Single-Plate Workbench RC3-F2): the passport, linked files, registration evidence,
  diagnostics and imported sensitivity table of any other single plate. No M11 identifier or archive enters it.

## 2. The seven sections

| Section | Content |
|---|---|
| 1. Sources | Source audit: role, path, SHA-256, size, origin, what it may support, expected SHA-256, state. The UNV, the FE manifest and the INP (optional, hashed only) are verified. The 261027 `.svd` is NOT_AVAILABLE, which does not prevent viewing the diagnostics. "Add evidence document..." records an owner-chosen file by SHA-256 with a claim type and never confirms its interpretation. |
| 2. Evidence A / B | Fact, topic, value, provenance, source, source SHA-256, dependencies, status and blocking reason, for chain A (scanner → plate) and chain B (plate → FE), with the supporting facts and test conditions. |
| 3. Owner questions | One question package generated from the open facts: A face, B scan geometry, C FE orientation, D applicability. A closed fact asks nothing; the answer fields are empty. |
| 4. Modal evidence | Every record and every elastic FE mode; nearest frequency (diagnostic only); close groups; the PRIORITY-2 branch history; no pair, no MAC, no FIT / HOLDOUT. |
| 5. Observability | (1) FE-only rank of the sensitivity matrix; (2) experimental identifiability; S0 / H1 / H2; the reuse audit of the archived sensitivities. |
| 6. FE applicability | Variants A–E with available and missing inputs, existing FE assets, future runs and authorisation, and the five stages kept apart. PLAN ONLY. |
| 7. Report & export | What blocks the identification; the export. |

**Details of the evidence section:**

- A relative fact (the same face, the same points) carries the 261016 evidence over and never raises it.
- The UNV grid (277.7 × 277.0 mm) is shown as a REPRESENTATION, never as the physical window.
- A diagnostic reconstruction, a candidate A–D and a CONVENTION_ONLY fact never close a fact.

**Details of the modal section:** the PRIORITY-1 research MAC appears only as **RESEARCH_MAC_NOT_ADMISSIBLE**.

**Details of the observability section:**

- The FE-only rank (M11: E1 / E2 / G12 rank 3, condition 1.83; E (E1 = E2) / G12 rank 2, condition 2.35) is labelled
  as such.
- Experimental identifiability is **NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS** without an accepted
  registration.
- S0 / H1 / H2 keep RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY.
- The reuse audit marks every archived sensitivity "not applicable" when the current FE model is not M11.

## 3. States

| State | When |
|---|---|
| SOURCE_NOT_VERIFIED | a required source is missing, foreign, changed on disk or does not verify when a saved review is reopened |
| PHYSICAL_REGISTRATION_NOT_VERIFIED | an independent fact is missing or refused |
| EVIDENCE_COMPLETE_NOT_FROZEN | only with complete independent facts (never a registration) |
| MODE_PAIRS_NOT_CONFIRMED | always here: no frozen registration, no MAC |
| NOT_READY_FOR_IDENTIFICATION | always here |
| READY_FOR_OWNER_REVIEW | the sources verify and the package is complete: a package for a decision, not a scientific acceptance |

A synthetic demonstration study gives SYNTHETIC_DEMONSTRATION_ONLY instead of READY_FOR_OWNER_REVIEW.

**No automatic step exists:**

- no button turns a form into a FrozenRegistration;
- nothing starts a MAC, LM or Auto-ID.

## 4. Freshness (the RC3-F2 rule)

**Fingerprint.** A review records the fingerprint of its inputs:

- the profile and the identity of every document;
- the modal set, the records and the FE modes;
- the facts and the applicability facts;
- for study B, also the passport and evidence fingerprints.

**When the inputs change.** A changed Workspace file, a changed modal set, an added document or a changed study B
makes the shown review **STALE — NOT CURRENT**. Its tables are not shown and it is not exported until it is built again.

**A reopened review** is CURRENT only when its recorded files verify on disk again by SHA-256; otherwise it is
NOT_CURRENT — SOURCE_NOT_VERIFIED.

## 5. Export

"Export dossier..." writes into a new folder inside the folder the user chooses. A folder inside the program is
refused. The sources are confirmed on disk first. The files are written into a temporary folder that is renamed at the
end, and nothing is ever overwritten. A refused export writes nothing.

| File | Content |
|---|---|
| `physical_readiness.json` | the whole dossier |
| `evidence_matrix.csv` | facts and sources |
| `modal_observations.csv` | records and FE modes with their statuses |
| `sensitivity_reuse.csv` | archived sensitivities and their reuse |
| `fe_applicability_plan.json` | the plan only |
| `OWNER_EVIDENCE_REQUEST.md` | the questions with empty answer fields |
| `PHYSICAL_READINESS_REPORT.md` | the readable report |
| `owner_evidence_request.json` | the same questions, machine-readable |

Every CSV row carries the specimen, series, FE model and the experimental and FE manifest SHA-256. Missing data are
NOT_AVAILABLE, NOT_VERIFIED or NOT_ASSESSED. The dossier is reproducible: two builds of the same inputs differ only in
`created`.

## 6. Tests

**`tests/test_plate_physical_review.py` (24):**

- exact identities of PLATE 261027 and M11;
- a foreign UNV, a foreign FE manifest and another modal set are refused;
- EXP1 18.6307 Hz and FE7 19.07217 Hz are kept unpaired (+2.37 %);
- 261016 and 261027 are kept apart: 33.4491 Hz is never a record of the review;
- a relative face never answers the absolute face, while a confirmed absolute 261016 face closes `scanned_face` and
  `grid_plus_v_edge`;
- the UNV grid is never the window;
- the six open facts;
- DERIVED / CANDIDATE provenance, dependencies and source SHA-256;
- a CONVENTION_ONLY corner is never promoted;
- concrete, unanswered questions (and none for recorded applicability facts);
- no MAC and no pair;
- FE-only rank apart from NOT_ASSESSED;
- the PRIORITY-2 runs, branch loss, permutations and the FE15 / FE16 cluster;
- no transfer of sensitivities to another FE model;
- S0 / H1 / H2 as hypotheses;
- the plan only;
- reproducible documents with identity columns;
- an atomic export outside the program with no FE file and no subprocess or LM call;
- a changed source refuses the export and makes a reopened review NOT_CURRENT;
- registrations and archive unchanged;
- a synthetic plate of another geometry (no M11 identifier);
- tab C: shown next to A and B, refused without inputs, a study-B review going STALE, save / reopen;
- the real 261027 / M11 copies (skipped where they are absent).

**Other test changes:**

- `tests/test_new_gui1_workspace.py`: the separation test lists the new module;
- `tests/test_windows_portable_rc4.py` (3): the RC4 packaging.

**Defects found by the Windows smoke and corrected, with tests:**

- the section button "7. Report & export" showed "Report _export" (Qt mnemonic): the "&" is now doubled;
- at 900 × 680 the evidence-claim list and the build button widened the Plate Study page: the list now uses the
  minimum-contents policy and the button reads "Build from the Workspace (PLATE 261027, M11)".

The test results, the Windows smoke and the RC4 build are in `WINDOWS_PORTABLE_RC4.md`.

## Not changed

- SPEC v1.1 / v1.2, DECISIONS, STATUS, ROADMAP and EVIDENCE.
- The frozen registrations and the historical results of PRIORITY-1–8.
- S0 / H1 / H2, M8, D-077 and the scientific thresholds.
- RC1–RC3-F2.

## 7. PRIORITY-9-F1 — integrity of the sources and of a saved dossier

Branch `fix/plate-physical-readiness-rc4-f1`, from `adaa71a`. The scientific content of PRIORITY-9 is unchanged.

### Defects in RC4

- `sources_state` accepted any audit in which every present row of an experimental source or FE manifest verified.
  - An audit missing one of them (built elsewhere, or edited) gave **SOURCES_VERIFIED**.
  - Two experimental files were not refused.
  - A document whose recorded SHA-256 was never hashed on disk could count as verified.
- `reopened_state` called a reopened dossier **CURRENT** when its existing paths hashed correctly.
  - One source was enough.
  - The stored scientific statuses were trusted, so a manual edit of the JSON stayed CURRENT.
- A study-B review did not check that the study's diagnostics belonged to its linked sources and modal set.

### Sources

**Requirement.** A physical plate needs **exactly one** experimental source and **exactly one** FE manifest. Each must
be hashed on disk now (`on_disk_sha256`) and equal its recorded SHA-256, and also the archived one for M11-261027.

**Refused states.** No document of the dossier may be CHANGED, MISSING, FOREIGN or NOT_READ_ON_DISK.

**Contradictions:**

- **study B:** the diagnostics were computed for other sources or another modal set (their recorded input
  fingerprint), or the study links no modal set;
- **Workspace:** the file read is not the file whose SHA-256 was recorded.

**Consequences:**

- Otherwise the state is **SOURCE_NOT_VERIFIED**, with each reason in the dossier (`sources.reasons`) and on the page.
- READY_FOR_OWNER_REVIEW is then not given, and the export is refused.
- Two experimental files or two FE manifests refuse the review. Any problem refuses the M11-261027 review.

**What is hashed.** The UNV, the FE `manifest.json` and an optional INP. The FE package is never hashed as a whole.

### A saved dossier

**Content integrity.** A new dossier carries `integrity.content_sha256`: the SHA-256 of its canonical JSON (sorted keys)
without this field. It detects an accidental or manual change of the saved content. It is not a signature and no proof
of authorship.

**Reopening:**

1. Every recorded document is hashed on disk again. Exactly one experimental source and one FE manifest must verify;
   one source is not enough.
2. The content must match its integrity SHA-256.
3. The stored source state must be SOURCES_VERIFIED.

If any step fails, the dossier is **NOT_CURRENT** with the reasons.

**Recomputation (M11-261027).** When the three steps pass, the dossier is recomputed from its verified files:

- the UNV and the FE package are read again, and only the manifest is hashed;
- the INP and the owner documents are hashed again.

A recomputation equal to the stored dossier (all but `created` and `integrity`) is **CURRENT — REVALIDATED**. Any
difference, for example an edited status with a fresh integrity record, is NOT_CURRENT.

**RECORD_NOT_REVALIDATED.** Other dossiers stay at RECORD_NOT_REVALIDATED: their sources and content verify, but their
statuses are the stored ones. This covers:

- study B (the study is not in the file);
- the synthetic demonstration;
- an RC4 dossier without an integrity record (not rewritten).

They are shown with "(stored, not revalidated)" and are not exported as current.

### Interface

- Building, reopening (hashing, reading, recomputing) and exporting run in the background, so the window stays
  responsive.
- A refused build keeps the review shown before. It becomes STALE, never lost, and the sources line shows the refusal,
  never the stored "verified".
- The state labels say "(stored, NOT CURRENT)" or "(stored, not revalidated)" whenever the review is not current.

### Tests

**`tests/test_plate_physical_review.py`: 35 tests** (24 kept and adapted, 11 new; item 8 extends the real-file test):

1. only the UNV → SOURCE_NOT_VERIFIED, not READY, export refused, the M11 review refused;
2. only the FE manifest → SOURCE_NOT_VERIFIED, also from an audit without the FE row;
3. both correct sources → SOURCES_VERIFIED; a recorded SHA-256 not hashed on disk is NOT_READ and refused;
4. duplicated sources, a changed content and a file read that is not the recorded one are refused;
5. diagnostics of another modal set → SOURCE_NOT_VERIFIED, export refused;
6. a saved dossier with one source, or with the FE row removed → NOT_CURRENT; with both → RECORD_NOT_REVALIDATED, never
   CURRENT from the stored statuses;
7. a manual status edit → MODIFIED_AFTER_SAVE, NOT_CURRENT, export refused; a dossier without an integrity record →
   RECORD_NOT_REVALIDATED; a recomputation that differs → NOT_CURRENT; an equal one → REVALIDATED;
8. the real M11-261027 copies: SOURCES_VERIFIED; saved, reopened and revalidated from the files → CURRENT — REVALIDATED
   (the real-file test, skipped where the copies are absent);
9. the synthetic demonstration keeps SYNTHETIC_DEMONSTRATION_ONLY and is RECORD_NOT_REVALIDATED when reopened;
10. no registration, MAC or mode pair; the registrations are unchanged.

The panel tests check three things:

- an incomplete source is shown with its reason, and the export is refused with nothing written;
- the earlier review is kept after a refused build;
- a refused build never leaves an earlier review shown as verified.

**A defect found by the F1 Windows smoke and corrected with a test.** After a build refused for one missing source, a
reopened and revalidated review stayed labelled "Sources: SOURCES_VERIFIED". A refused build now makes the shown review
STALE: the review is kept, its sources line shows the refusal and nothing is exported.

**The fixtures.** The M11 test documents now state their on-disk SHA-256 explicitly: a recorded SHA-256 alone is no
longer a verification. A foreign INP now refuses the M11 review; before, it gave a dossier marked SOURCE_NOT_VERIFIED.

**Packaging.** `tests/test_windows_portable_rc4_f1.py` (3) checks the separate RC4-F1 packaging (RC1–RC4 unchanged).
