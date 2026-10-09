# Auto-ID Changelog

**Append-only.** New entries go at the bottom. Existing entries are never edited,
except to fill in a commit SHA that could not be known before the commit existed.

Every mini-step entry contains: date · stage · mini-step · status · branch · commit
SHA · files changed · scientific behaviour changed (YES/NO) · tests run · test result
· Abaqus run count · evidence produced · known limitations · next gate.

---

## 2026-10-03 — PRE-M0 P0.1 + P0.3 — Freeze v1.1 specification, roadmap and governance

- **Stage:** PRE-M0
- **Mini-step:** P0.1 (freeze SPEC/AUDIT/roadmap/governance) + P0.3 (branch / mini-step
  / GitHub reporting protocol)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/v1.1-roadmap` (separate worktree; based on
  `121ba1d06b7c268b3051f1407a3ea26a9027dca3`)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): freeze v1.1 roadmap and execution protocol`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - created: `docs/auto_id/README.md`, `docs/auto_id/SPEC_V1_1.md`,
    `docs/auto_id/AUDIT_121ba1d_V1_1.md`, `docs/auto_id/ROADMAP.md`,
    `docs/auto_id/STATUS.json`, `docs/auto_id/DECISIONS.md`,
    `docs/auto_id/CHANGELOG.md`, `docs/auto_id/EVIDENCE.md`,
    `docs/auto_id/source/Spec_AutoID_v1.1.docx`,
    `docs/auto_id/source/Audit_ModalComparator_121ba1d_AutoID_v1.1.docx`,
    `docs/auto_id/source/SHA256SUMS.txt`, `CLAUDE.md`, `AGENTS.md`
  - updated (pointer only; historical content untouched): `ROADMAP.md`,
    `docs/ROADMAP_Stage_Inverse_Identification.md`,
    `docs/gui/EFFECTIVE_MATERIAL_IDENTIFICATION_V1.md`
- **Scientific behaviour changed:** NO (documentation only; no Python source changed)
- **Tests run:** none. The full suite was intentionally not run while CARBON-5F Abaqus
  solves were active on the machine. Lightweight validation only: JSON parse, internal
  link/path check, `git diff --check`, DOCX SHA-256 verification, staged-file review.
- **Test result:** not applicable. Reference baseline at the audited snapshot
  (from the audit, Linux): 873 ran / 870 passed / 1 failed (V7) / 2 skipped.
- **Abaqus run count:** 0
- **Evidence produced:** archival DOCX copies with SHA-256
  (`docs/auto_id/source/SHA256SUMS.txt`). No scientific evidence.
- **Archival source:** found locally and copied unchanged:
  - `Spec_AutoID_v1.1.docx` —
    `a8f4dda8abee2da09c17aab1a96a2d49cdf4ff75bde67820d31059e65b49d84b`
  - `Audit_ModalComparator_121ba1d_AutoID_v1.1.docx` —
    `453245e179b986e3c875d525a6adb600738b0d7d69c7b5f4cd5cb406f3d44908`
- **CARBON-5F:** untouched by this mini-step. Status IN_PROGRESS, scientific result
  PENDING, supervisor acceptance PENDING.
- **Known limitations:**
  - P0.2 (CARBON-5F evidence appendix) is BLOCKED_WAITING_FOR_CARBON_5F.
  - EVIDENCE archive locations for CARBON-4C…5D are not recorded in Git.
  - Open point recorded in ROADMAP M6 (twill bare plate vs old-plain family) for a
    supervisor decision.
- **Next gate:** SUPERVISOR review of P0.1/P0.3. PRE-M0 gate requires P0.1 + P0.2 +
  P0.3 ACCEPTED before M0.

## 2026-10-03 — PRE-M0 P0.1 + P0.3 — Supervisor acceptance recorded; D-017

- **Stage:** PRE-M0
- **Mini-step:** acceptance record for P0.1 + P0.3 (no new mini-step started)
- **Status:** P0.1 ACCEPTED · P0.3 ACCEPTED · P0.2 BLOCKED_WAITING_FOR_CARBON_5F.
  PRE-M0 is **not** complete; M0 not started.
- **Review basis:** the SUPERVISOR reviewed the actual pushed GitHub commit
  `3362076253a63bc94e9414733e5f4d467e446419` on `auto-id/v1.1-roadmap`.
- **Branch:** `auto-id/v1.1-roadmap` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): record P0.1 P0.3 acceptance`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:** `docs/auto_id/ROADMAP.md` (P0.1/P0.3 status; M6 note replaced by
  the D-017 decision), `docs/auto_id/DECISIONS.md` (D-017 appended),
  `docs/auto_id/STATUS.json`, `docs/auto_id/CHANGELOG.md` (this entry)
- **Decision accepted:** D-017, bare-plate G12 is material-family specific. The twill
  350×350 bare plate is the Stage-A validation / twill-family specimen and does not
  provide primary G12 for old plain 0.45.
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (CARBON-5F Abaqus solves active). Lightweight validation only:
  JSON parse, status consistency check, append-only diff check, `git diff --check`.
- **Test result:** not applicable
- **Abaqus run count:** 0
- **Evidence produced:** none
- **CARBON-5F:** untouched. IN_PROGRESS, scientific result PENDING, supervisor
  acceptance PENDING.
- **Known limitations:** P0.2 remains blocked until a final CARBON-5F report is
  SUPERVISOR-ACCEPTED.
- **Next gate:** CARBON-5F completion → supervisor acceptance of its final report →
  P0.2.

## 2026-10-03 — PRE-M0 P0.2 — CARBON-5F evidence appendix

- **Stage:** PRE-M0
- **Mini-step:** P0.2 (record final accepted CARBON-5F evidence appendix)
- **Status:** REVIEW_READY. P0.1 ACCEPTED · P0.3 ACCEPTED. PRE-M0 is **not** accepted
  until the SUPERVISOR reviews this P0.2 commit. M0 not started.
- **Branch:** `auto-id/v1.1-roadmap` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): record CARBON-5F core sensitivity evidence`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/EVIDENCE.md` (CARBON-5F entry IN_PROGRESS → ACCEPTED)
  - `docs/auto_id/ROADMAP.md` (P0.2 → REVIEW_READY)
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **CARBON-5F:** SUPERVISOR-ACCEPTED (diagnostic sensitivity evidence).
  - Exactly 4 authorized Abaqus solves: SP02/SP13 × CORE_MINUS/CORE_PLUS.
  - k_core = 0.90 / 1.10.
  - No retries and no extra solves.
  - All runs had exact FE geometry identity and exact FrozenRegistration replay. All 19
    post-run checks passed. Mass was unchanged and production pairing was unchanged.
- **s_core summary:**
  - Mean S_core over fit rows: SP02 0.0109, SP13 0.0139 (ratio ≈ 1.28).
  - FE7 holdout: SP02 0.0152, SP13 0.0183.
  - ±10 % frequency changes ≈ 0.06–0.21 %.
  - SP13 FE8/FE9 ordering and mixing were unchanged.
- **Conclusion scope:** the tested common scalar k_core is ruled out as a realistic
  cause of the SP13 common ~6 % deficit and of the FE7 deficit. Here k_core is the
  proportional scaling of all six current core stiffness constants.
  - The conclusion is **not** generalised to:
    - core model-form effects in general;
    - core geometry;
    - anisotropic changes of individual core constants;
    - interface/contact effects.
  - k_core ≈ 77 (and any k_core = 0.5 / 1.5 statement) is labelled a first-order
    extrapolation, not an Abaqus-verified state.
- **q_G:** NOT YET PRODUCTION-VALID / DEFERRED TO M5. No value was recorded.
  CARBON-5F provides the s_k column only.
- **k_core prior:** not provided by CARBON-5F. Independent core-tile evidence is still
  required (D-006, M6.3).
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (documentation-only step). Lightweight validation only: JSON
  parse, status consistency check, scope/overclaim check, append-only diff check,
  `git diff --check`.
- **Test result:** not applicable
- **Abaqus run count:**
  - 0 by this documentation worker.
  - The 4 CARBON-5F solves were run earlier under the human Abaqus gate.
- **Evidence produced:** CARBON-5F EVIDENCE entry (compact summary and identities
  only; ODBs not in Git).
- **Known limitations:**
  - The CARBON-5F archive location is local research scratch and is not recorded in
    Git.
  - q_G is deferred to M5.
- **Next gate:** SUPERVISOR review of P0.2. Once P0.1, P0.2 and P0.3 are all ACCEPTED,
  the PRE-M0 gate is met. M0 must not start before that.

## 2026-10-03 — PRE-M0 — Supervisor acceptance of P0.2; PRE-M0 gate closed

- **Stage:** PRE-M0
- **Mini-step:** acceptance record for P0.2 (no new mini-step started)
- **Status:** P0.1 ACCEPTED · P0.2 ACCEPTED · P0.3 ACCEPTED. **PRE-M0 gate ACCEPTED.**
  M0 has **not** begun.
- **Review basis:** the SUPERVISOR reviewed the actual pushed GitHub commit
  `ec86a772b32a1aaa318b3bc4e9091f7d3f59642e` on `auto-id/v1.1-roadmap`.
- **Branch:** `auto-id/v1.1-roadmap` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): close PRE-M0 freeze gate`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/ROADMAP.md` (P0.2 → ACCEPTED; PRE-M0 gate ACCEPTED)
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **CARBON-5F:** evidence ACCEPTED, scope as recorded in [EVIDENCE.md](EVIDENCE.md).
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (documentation only). Lightweight validation only: JSON parse,
  status consistency check, append-only diff check, `git diff --check`.
- **Test result:** not applicable
- **Abaqus run count:** 0 by this worker
- **Evidence produced:** none
- **Known limitations:** M0.1–M0.4 remain TODO. `main` is unchanged.
- **Next gate:** merge the freeze branch `auto-id/v1.1-roadmap` to `main` under explicit
  HUMAN authorization. After the merge, record the main SHA, then begin M0.1.

## 2026-10-03 — M0 — Freeze merge recorded; M0.1 started

- **Stage:** M0
- **Mini-step:** stage transition record + M0.1 → IN_PROGRESS (no implementation in
  this commit)
- **Status:** PRE-M0 ACCEPTED and merged. M0.1 IN_PROGRESS. M0.2–M0.4 TODO.
- **Freeze merge:** PR #25 (`auto-id/v1.1-roadmap` → `main`), merged manually by the
  HUMAN. The `main` merge SHA is `05b4e2cad5c68ad7092f25c381b836e291184079`.
- **Authorization:** SUPERVISOR authorized "START M0.1 ONLY".
- **Branch:** `auto-id/m0` (separate worktree; based on `05b4e2c`)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): record freeze merge and start M0.1`
- **Files changed:**
  - `docs/auto_id/STATUS.json` (`freeze_merge`, `m0`, current stage/mini-step)
  - `docs/auto_id/ROADMAP.md` (M0.1 → IN_PROGRESS)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** pre-change baseline on Windows at `05b4e2c`:
  `python -m unittest discover -s tests`. Ran 873, OK (skipped=2). V7 does not fail on
  Windows; it is Linux-only.
- **Abaqus run count:** 0
- **Next gate:** M0.1 implementation, then SUPERVISOR review.

## 2026-10-03 — M0 M0.1 — Fix V7 cross-platform path failure

- **Stage:** M0
- **Mini-step:** M0.1 (fix V7 cross-platform path failure; AUDIT V7)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m0` (separate worktree; based on `main` `05b4e2c`)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M0.1): fix cross-platform path failure`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Earlier commits on this branch:**
  - `fc20ab3` records the freeze merge SHA and moves M0.1 to IN_PROGRESS in
    STATUS.json.
  - `c0a9902` completes `fc20ab3` with the ROADMAP IN_PROGRESS change. It was left out
    of `fc20ab3` because that edit failed; history was not rewritten.
- **Cause:** `material_identification_ui._selected_source_status` displayed the
  selected FE/experimental file name with `pathlib.Path(text).name`. On POSIX hosts
  `Path` does not split on `\`, so a Windows path such as `C:\models\panel.odb` was
  displayed whole. The failing test was
  `ProjectEvidenceStatusTests.test_selected_and_validated_states_display_correctly`,
  on Linux CI.
- **Fix:** the display uses `PureWindowsPath(text).name`, which splits on both `\` and
  `/` on every host. It is a one-line display change in the single owner of the
  function; no `install_*` layer redefines it. Windows output is unchanged.
- **Files changed:**
  - `src/material_identification_ui.py` (import plus the display line)
  - `tests/test_material_identification_ui.py` (new reproducing test)
  - `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md` (M0.1 → REVIEW_READY)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Reproducing test:** `test_selected_source_name_is_independent_of_host_path_flavour`
  simulates a POSIX host on any OS by patching the module's `Path` with
  `PurePosixPath`.
  - Against the old source on Windows it fails for the `C:\...` and UNC cases.
  - With the fix it passes. It also covers POSIX, forward-slash, bare-name and blank
    inputs.
- **Scientific runtime behaviour changed:** NO. The change only affects how the
  selected file name is displayed in the evidence status. No identification
  mathematics, modal algorithm, extraction, threshold or gate changed.
- **Production code changed:** YES, display only (`src/material_identification_ui.py`).
- **Tests run (Windows, local):**
  - Before, at `05b4e2c`: `python -m unittest discover -s tests` ran 873, OK
    (skipped=2). V7 does not reproduce natively on Windows.
  - After: the targeted `ProjectEvidenceStatusTests` ran 2, OK. The
    `test_material_identification_ui` module ran 42, OK. The full suite ran 874, OK
    (skipped=2).
- **Linux:** no local Linux runtime. GitHub Actions (ubuntu-latest) on the pushed
  branch verifies it, and the result is reported to the SUPERVISOR. The pre-fix Linux
  CI at `121ba1d` / `6868692` ran 870 with 1 failure (V7) and skipped=6.
- **Abaqus run count:** 0
- **Evidence produced:** none
- **Known limitations:** the Linux CI skip count (6) differs from the audit's Linux
  count (2). That is a Tk/GUI availability difference to document in M0.4, not M0.1.
- **Next gate:** SUPERVISOR review of M0.1. M0.2 must not start before acceptance.

## 2026-10-03 — M0 M0.1 — Supervisor acceptance recorded

- **Stage:** M0
- **Mini-step:** acceptance record for M0.1 (no new mini-step started)
- **Status:** M0.1 ACCEPTED. M0 IN_PROGRESS. M0.2–M0.4 TODO. PRE-M0 ACCEPTED.
  CARBON-5F ACCEPTED.
- **Review basis:** the SUPERVISOR reviewed commit
  `15d6c534031f310b5f26a5e720a59d0e0d2bc070` on `auto-id/m0`.
- **Accepted scope:**
  - The Linux V7 cross-platform path failure is fixed.
  - The fix uses `PureWindowsPath` for the displayed file name.
  - No scientific behaviour changed. No identification mathematics changed.
  - No Abaqus.
  - No `install_*` layer introduced.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept M0.1 cross-platform fix`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/ROADMAP.md` (M0.1 ACCEPTED; M0 stage status)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization to start M0.2. `main` is unchanged; the
  stage PR comes only at the end of M0.

## 2026-10-03 — M0 M0.2 — Real experiment fixture manifest

- **Stage:** M0
- **Mini-step:** M0.2 (real experimental fixture manifest; AUDIT J1 groundwork)
- **Status:** REVIEW_READY. M0.1 ACCEPTED. M0.3–M0.4 TODO.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M0.2): add real experiment fixture manifest`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **What was added:** a deterministic identity layer for real experiments, with schema
  `experiment-fixture-manifest/1`. It records:
  - specimen, physical specimen, experiment and test-run identifiers;
  - the experimental source (file name, SHA-256, size, external location);
  - the modal set (name, source type, mode count, point count, measured DOFs, face);
  - the FrozenRegistration identity (path, schema, hash, FE geometry hash);
  - the FE identity (geometry identity, source INP and reference ODB);
  - provenance and unresolved fields with reasons.
- **No local absolute paths:** external files are referenced as a store plus a
  relative path. The retrieval contract is documented: store roots come from
  `AUTO_ID_FIXTURE_ROOT_<STORE>`, and files are verified by size and SHA-256. A missing
  or mismatched file is refused, never substituted.
- **Records:**
  - **`SP02/bravo-1`:** `SP02_polymax_retry_260803.unv`, 9 modes, 121 points, U3 only,
    registration `9bf736d3…c164`, FE geometry `72e8597a…4e6d`.
  - **`SP13/best`:** `SP13_a_polymax.unv`, 12 modes, 289 points, U3 only, registration
    `a8970e52…58a4`, FE geometry `34d69d79…5826`.
  - **Model inputs:** the accepted source INPs (SHA-256 as in the CARBON-5F evidence).
  - **ODB references:** the CARBON-4C baseline control ODBs.
- **Unresolved values:** `physical_specimen_id` is null for both records, and
  `test_run_id` is null for SP13, because accepted evidence does not record them. Each
  is declared in `unresolved` with its reason; the key model is defined in M2.2.
- **Files changed:**
  - added `src/domain/experiment_fixture.py` (schema validator and external-file
    resolver)
  - added `docs/auto_id/fixtures/real_experiment_fixtures.json` (manifest)
  - added `docs/auto_id/fixtures/README.md` (schema and retrieval contract)
  - added `tests/test_experiment_fixture.py` (19 tests)
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M0.2 → REVIEW_READY)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Large data committed:** NO. No UNV, INP, ODB, scratch or cache files.
- **Scientific runtime behaviour changed:** NO. The module is new and nothing calls it
  yet. No pairing, registration, extraction, threshold or gate changed. The
  registration files are unchanged.
- **Tests run (Windows):**
  - New `test_experiment_fixture`: 19 ran, OK. It covers manifest parsing, required
    fields, unknown fields, hash format, refusal of absolute paths and `..`,
    registration/FE consistency, unresolved-identifier rules, refusal of missing or
    mismatched sources, environment roots, and cross-checks against the frozen
    registration JSONs.
  - Full suite: 893 ran, OK (skipped=2). Before this step: 874 ran, OK (skipped=2).
- **One-off local verification (not a committed test):** with the two store roots
  configured, all 6 external files resolved with size and SHA-256 verified. Real-data
  regressions belong to M0.3.
- **Abaqus run count:** 0
- **Evidence produced:** none (identity records of existing accepted evidence only)
- **Known limitations:**
  - The provisional identifiers are replaced by the M2.2 key model.
  - The ODB SHA-256 identifies one archived reference result; FE identity binds
    through the geometry identity.
- **Next gate:** SUPERVISOR review of M0.2. M0.3 must not start before acceptance.

## 2026-10-04 — M0 M0.2 — Supervisor acceptance recorded

- **Stage:** M0
- **Mini-step:** acceptance record for M0.2 (no new mini-step started)
- **Status:** M0.2 ACCEPTED. M0 IN_PROGRESS. M0.1 ACCEPTED. M0.3–M0.4 TODO.
- **Review basis:** the SUPERVISOR reviewed commit
  `66dfe45a5d3a0a7b023c7c5eb9919ba737033b34` on `auto-id/m0`.
- **Accepted scope:**
  - The real experiment fixture manifest is created.
  - The SP02 `bravo-1` and SP13 `best` identities are pinned.
  - The experimental source hashes are verified.
  - The FrozenRegistration hashes and FE geometry identities are linked.
  - The U3 measurement contracts are recorded.
  - External large data stays outside git, and SHA verification is required before
    use.
  - Missing identifiers are explicitly unresolved, not invented.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept M0.2 fixture manifest`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/ROADMAP.md` (M0.2 ACCEPTED; M0 stage status)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization to start M0.3. `main` is unchanged.

## 2026-10-04 — M0 M0.3 — PolyMAX / FrozenRegistration regressions

- **Stage:** M0
- **Mini-step:** M0.3 (real PolyMAX / FrozenRegistration regressions)
- **Status:** REVIEW_READY. M0.1 and M0.2 ACCEPTED. M0.4 TODO.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M0.3): add PolyMAX FrozenRegistration regressions`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **What was added:** `verify_experiment_fixture` checks one M0.2 manifest record
  against its real data. It raises on the first difference and never repairs or
  substitutes anything.
  - **Experimental source:** it resolves through the store root, with the pinned size
    and SHA-256.
  - **FrozenRegistration:** it is restored with its content hash re-sealed. The
    registration hash and schema, the bound source (SHA-256 and size), the modal set
    and the FE geometry identity (SHA-256, node count, schema) must equal the record.
  - **PolyMAX import:** it uses the production reader with the pinned modal set. The
    reader's mode source must equal the pinned source type, so a peak-derived source
    cannot substitute. The modal set key, mode count and point count must match.
  - **Measurement contract replay:** the imported points must equal the
    registration's points, with one mapped FE node per point. The frozen DOF set must
    equal `measured_dofs`, and every mode's measured-DOF mask (production
    `experimental_measurement_masks`) must equal the frozen contract.
- **Single source of fixture identity:** the tests iterate the M0.2 manifest. No
  second fixture list exists. A record whose store root is not configured is skipped
  with the reason.
- **Files changed:**
  - added `src/services/experiment_fixture_regression.py`
  - added `tests/test_experiment_fixture_regression.py` (15 tests: 1 real-data test
    over all manifest records, 14 synthetic contract tests)
  - updated `docs/auto_id/fixtures/README.md` (regression check section)
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M0.3 → REVIEW_READY)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Reproduced identities (Windows, real data):**
  - **`SP02/bravo-1`:** curve-fitted dataset 55, 9 modes, 121 points, U3 only,
    registration `9bf736d3…c164`, FE geometry `72e8597a…4e6d`.
  - **`SP13/best`:** curve-fitted dataset 55, 12 modes, 289 points, U3 only,
    registration `a8970e52…58a4`, FE geometry `34d69d79…5826`.
  - **Tampered real records are refused:** a wrong mode count, a wrong DOF set and
    another modal set (`processing`) are each refused.
- **Refusal paths tested (synthetic, CI-capable):**
  - missing store root, missing file, wrong SHA-256;
  - wrong mode count, wrong point count, wrong modal set;
  - peak-derived mode source, unregistered source type;
  - wrong registration hash, edited registration file;
  - wrong FE identity (SHA-256 or node count);
  - wrong DOF set, and imported DOFs outside the frozen contract.
- **Scientific runtime behaviour changed:** NO. Nothing in production calls the new
  service. No reader, pairing, registration, threshold or gate changed. The
  registrations are untouched.
- **Tests run (Windows):**
  - `test_experiment_fixture_regression` with no store root: 15 ran, OK (the 2
    real-data subtests skipped with the reason). With `AUTO_ID_FIXTURE_ROOT_SNADWICH`
    set: both real fixtures reproduced.
  - Full suite: 908 ran, OK. With no store root, skipped=4; with the store root,
    skipped=2. Before this step: 893 ran, OK (skipped=2).
- **Linux CI:** has no real data store, so the real-data subtests skip there and the
  synthetic contract tests run.
- **Abaqus run count:** 0
- **Large data committed:** NO
- **Known limitations:**
  - FE geometry identity is checked at the record and registration level. Recomputing
    it from the ODB would need Abaqus-side extraction, which is out of scope here.
  - Real-data regressions run only where a store root is configured.
- **Next gate:** SUPERVISOR review of M0.3. M0.4 must not start before acceptance.

## 2026-10-04 — M0 M0.3 — Supervisor acceptance recorded

- **Stage:** M0
- **Mini-step:** acceptance record for M0.3 (no new mini-step started)
- **Status:** M0.3 ACCEPTED. M0 IN_PROGRESS. M0.1 and M0.2 ACCEPTED. M0.4 TODO.
- **Review basis:** the SUPERVISOR reviewed commit
  `b3e080f50dc7ce66c42101b933f8631bf2249782` on `auto-id/m0`.
- **Accepted scope:**
  - Real PolyMAX fixture regressions are added, and the tests consume only the M0.2
    manifest.
  - Protected identities: SP02/bravo-1 and SP13/best, the FrozenRegistration hashes,
    the FE geometry identity references, the modal source type and the measurement
    DOF contract.
  - No Abaqus is required, and no scientific algorithm changed.
  - Modal pairing, registration, thresholds, identification logic and extraction are
    unchanged.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept M0.3 fixture regressions`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/ROADMAP.md` (M0.3 ACCEPTED; M0 stage status)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization to start M0.4. `main` is unchanged.

## 2026-10-04 — M0 M0.4 — Hidden test module fixed (part 1 of 2)

- **Stage:** M0
- **Mini-step:** M0.4 (Windows + Linux CI baseline), part 1: a test-infrastructure
  defect found while collecting the baseline
- **Status:** M0.4 IN_PROGRESS. Part 2 records the baseline from the CI run of this
  commit.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M0.4): collect hidden CMIF UI layout tests`
- **Defect:** `tests/cmif_ui_layout_test.py` was tracked since `bccd19e`
  (2026-07-28) and defines `CmifUiLayoutTests` (2 tests). Its name does not match the
  `test*.py` pattern of `python -m unittest discover -s tests`, so neither local runs
  nor CI ever collected it. Run directly, both tests pass.
  - Classification: real defect (test infrastructure), not a platform difference.
- **Fix:**
  - The file is renamed to `tests/test_cmif_ui_layout.py` (pure rename, content
    unchanged).
  - A new guard `tests/test_suite_discovery.py` fails if any `tests/*.py` file
    outside the discovery pattern defines a `TestCase`. It fails on the old name and
    passes after the rename.
- **Other disabled-test search:**
  - No `expectedFailure`, no disabled or renamed test methods, and no early-return
    tests were found. The `_test_registration` helpers are fixtures, not tests.
  - The only skips are the explicit environment gates documented in part 2.
- **Files changed:**
  - renamed `tests/cmif_ui_layout_test.py` → `tests/test_cmif_ui_layout.py`
  - added `tests/test_suite_discovery.py`
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M0.4 → IN_PROGRESS)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO. Tests only; no `src/` change.
- **Production code changed:** NO
- **Tests run (Windows, Python 3.14.6):**
  - Before the fix: 908 ran, OK. With `AUTO_ID_FIXTURE_ROOT_SNADWICH` set, 2 skipped;
    without it, 4 skipped.
  - After the fix: 911 ran, OK, with the same skips.
- **Abaqus run count:** 0
- **Next:** part 2 records the Windows/Linux baseline (M0.4 → REVIEW_READY).

## 2026-10-04 — M0 M0.4 — Windows + Linux CI baseline (part 2 of 2)

- **Stage:** M0
- **Mini-step:** M0.4 (Windows + Linux CI baseline), part 2: the baseline record
- **Status:** REVIEW_READY. M0.1, M0.2 and M0.3 ACCEPTED.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): record M0.4 CI baseline`
- **Reference commit for the baseline:** `afa218141957d573877e39f6157a4f6ff013dfa9`
  (part 1). The command on both platforms is
  `python -m unittest discover -s tests -v`.
- **Verification of the M0.3 starting numbers:**
  - Windows 908 OK / 2 skipped and Linux 905 OK / 8 skipped were confirmed at
    `e40487e`. On Windows, 2 skipped holds with the fixture store configured; without
    it, 4 skips are reported (2 tests and 2 subtests).
  - The 3-test gap between them is `MaterialIdentificationGuiShellTests`. It is
    skipped at `setUpClass` on Linux, so its 3 tests are not counted as run.
- **Windows baseline** (local; Windows 10 19045, Python 3.14.6, numpy 2.5.1, scipy
  1.18.0, Tk 8.6):

  | Condition | Ran | Passed | Failed | Errors | Skipped tests | Skipped subtests |
  |---|---|---|---|---|---|---|
  | `AUTO_ID_FIXTURE_ROOT_SNADWICH` set | 911 | 909 | 0 | 0 | 2 | 0 |
  | no fixture store | 911 | 908 | 0 | 0 | 2 | 2 |

- **Linux CI baseline:** GitHub Actions `ubuntu-latest`, workflow
  `.github/workflows/tests.yml`, run 37138643253, conclusion **success**. Python
  3.11, numpy 2.4.6, scipy 1.17.1.

  | Ran | Passed | Failed | Errors | Skipped (unittest count) | Not collected |
  |---|---|---|---|---|---|
  | 908 | 902 | 0 | 0 | 8 | 3 |

  - The 8 skips are 5 skipped tests, 2 skipped subtests and 1 class-level skip.
  - The class-level skip is `MaterialIdentificationGuiShellTests.setUpClass`, which
    leaves its 3 tests uncollected.
  - The fixture-regression test, whose subtests all skip, is not counted as passed.
- **Every skip, classified:**

  | Skipped | Platform | Classification | Enabling condition |
  |---|---|---|---|
  | `test_stage_a_matrix_abaqus_integration`: 2 tests | Windows, Linux | Missing optional external tool (opt-in Abaqus integration; Auto-ID also requires a HUMAN gate for Abaqus) | `ABAQUS_MATRIX_INTEGRATION=1` and an Abaqus executable |
  | `test_experiment_fixture_regression`: 2 real-data subtests | Linux; Windows without the store | Missing external fixture (large data stays outside git, M0.2) | `AUTO_ID_FIXTURE_ROOT_SNADWICH` |
  | Tk GUI tests: `MaterialIdentificationGuiShellTests` (class, 3), `PolymaxNativeTkTests` (2), `TkRuntimeSmokeTests` (1) | Linux | GUI/headless limitation (no `$DISPLAY`). All 6 run and pass on Windows. | A display for Tk |

  No skip is a real defect, an environment issue or a missing Python dependency.
- **Failures:** none on either platform.
- **Hidden or disabled tests:** one hidden module was found and fixed in part 1
  (`cmif_ui_layout_test.py`, 2 tests; now guarded). No `expectedFailure`, renamed or
  early-return tests exist. All skips are the explicit gates above.
- **Platform behaviour that is explicit, not a failure:**
  - **Different Python stacks:** Windows uses Python 3.14 and CI uses 3.11, and
    `requirements.txt` sets lower bounds only, so the numpy/scipy versions differ.
  - **Windows CI:** there is no Windows CI job. The Windows baseline is local.
- **STATUS.json:**
  - New `ci_baseline` is the CI reference for future Auto-ID work.
  - The audit's original `test_baseline` (873/870/1/2 at `121ba1d`) is kept unchanged
    as `audit_test_baseline`; nothing reads either key.
- **Files changed:**
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/ROADMAP.md` (M0.4 → REVIEW_READY)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO (over the whole of M0.4)
- **Abaqus run count:** 0
- **Open options for the SUPERVISOR (not implemented):**
  - run the Tk tests on CI under a virtual display (for example `xvfb-run`);
  - add a `windows-latest` CI job;
  - pin dependency versions.
- **Next gate:** SUPERVISOR review of M0.4. M1 must not start before M0.4 is accepted
  and the M0 gate is decided.

## 2026-10-04 — M0 — Supervisor acceptance of M0.4; M0 stage ACCEPTED

- **Stage:** M0
- **Mini-step:** acceptance record for M0.4 and the M0 stage (no new mini-step
  started)
- **Status:** M0.1, M0.2, M0.3 and M0.4 are ACCEPTED. **M0 ACCEPTED (M0 gate
  ACCEPTED).** M1 TODO, not started.
- **Review basis:** the SUPERVISOR reviewed commits `afa2181` and
  `ad623286a583dc83f08a948bdd8d4967b25486bd` on `auto-id/m0`.
- **Accepted scope:**
  - The Windows and Linux CI baselines are recorded.
  - The test discovery gap is fixed: the hidden CMIF UI layout tests are now
    collected, and a discovery guard is added.
  - All remaining skips are classified, and no unexplained failures remain.
  - No scientific behaviour changed. Modal algorithms, Abaqus, identification,
    registration and Auto-ID mathematics are unchanged.
- **CI reference for later Auto-ID work:** `STATUS.json` `ci_baseline`, at
  `afa2181`.
- **Branch:** `auto-id/m0` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept M0 CI baseline`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/ROADMAP.md` (M0.4 ACCEPTED; M0 stage and gate ACCEPTED)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** prepare the M0 stage PR (`auto-id/m0` → `main`). Merge it only under
  explicit HUMAN authorization, then record the `main` merge SHA. M1 begins only on
  SUPERVISOR authorization after that. `main` is unchanged (`05b4e2c`).

## 2026-10-04 — M0 — M0 stage merged to main

- **Stage:** M0 (stage completion record; no new mini-step started)
- **Status:** M0 merged to `main` and ACCEPTED. `current_stage` is `M0_COMPLETE`.
  M1 NOT_STARTED.
- **Merge:** PR #26 (`auto-id/m0` → `main`), a normal merge commit
  `4ec80abd3110b41aea586387faf42d4ad90fa9d0`.
  - Its parents are `05b4e2c` (previous `main`) and `63fa250` (the reviewed M0 head).
  - The merged tree is identical to the reviewed head.
  - The HUMAN authorized the merge and the SUPERVISOR accepted it.
- **Accepted mini-steps:**
  - M0.1 (`15d6c53`)
  - M0.2 (`66dfe45`)
  - M0.3 (`b3e080f`)
  - M0.4 (`afa2181`, `ad62328`)
  - Stage acceptance: `63fa250`
- **Production changes in the merge:** limited to the accepted M0 infrastructure:
  - the M0.1 display line in `src/material_identification_ui.py`;
  - new `src/domain/experiment_fixture.py` (M0.2);
  - new `src/services/experiment_fixture_regression.py` (M0.3).
  No scientific behaviour changed.
- **Branch:** this record is committed directly on `main`, by explicit SUPERVISOR
  instruction ("documentation synchronization commit only"). This is an authorized
  exception to the no-direct-push-to-`main` rule. `auto-id/m0` is kept.
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): record M0 main merge completion`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json` (`main_merge`, `m1`, `current_stage`, `next_action`)
  - `docs/auto_id/ROADMAP.md` (merge note)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO (in this commit)
- **Tests run:** none (not requested)
- **Abaqus run count:** 0 (merge step and this record)
- **Next gate:** create `auto-id/m1` and begin M1.1 only after SUPERVISOR
  authorization.

## 2026-10-04 — M1 M1.1 — Identification input-source policy

- **Stage:** M1
- **Mini-step:** M1.1 (identification input-source policy; SPEC §4, D-002, AUDIT K1)
- **Status:** REVIEW_READY. M1.2–M1.4 TODO.
- **Branch:** `auto-id/m1` (separate worktree; based on `main` `9d30caf`)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M1.1): enforce identification input source policy`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Policy:** `src/domain/modal_input_source.py` classifies experimental modes as
  `curve_fitted`, `peak_derived` or `unknown`.
  - It uses only the exact `mode_source` labels and dataset types the readers emit;
    unrecognised labels are never guessed from substrings.
  - **`curve_fitted`:** `curve-fitted modal dataset` and `curve-fitted dataset 55`, or
    datasets 55/2414 without a label.
  - **`peak_derived`:** `FRF peak-derived experimental shape`,
    `dataset 58 FRF peak extraction`, `local response-matrix SVD close-mode candidate`,
    or dataset 58. A dataset-58 type outranks a contradictory curve-fitted label.
  - **Datasets:** every mode must be curve-fitted. One peak-derived mode or a
    peak-derived dataset label makes the dataset `peak_derived`. Any unclassifiable
    mode, an unknown dataset label, or an empty dataset makes it `unknown`.
  - `require_identification_input` accepts only `curve_fitted`. It raises
    `IdentificationInputSourceRefusal` for `peak_derived` (citing SPEC §4 / D-002 /
    K1) and for `unknown`.
  - That exception is deliberately neither `ValueError` nor `RuntimeError`, so
    generic fallback handlers never catch it.
- **Enforcement boundary:** `identify_stage_a` is the single production entry where
  experimental modes enter identification; `uncertainty_service` reaches it too. The
  policy check now runs there before any clustering, pairing or eigen-solve, and
  applies with or without an injected pairing provider.
  - The lifecycle runner (`material_identification_runner`) only calls injected
    executors with typed evidence and has no live executor in `src`.
  - Later Auto-ID orchestration (M4.6) must call the same domain function.
- **Not changed:**
  - Readers, peak extraction, CMIF, MAC, pairing, registration, Abaqus extraction,
    thresholds and gates are unchanged.
  - Normal modal comparison still accepts peak-derived modes. Peak-derived modes
    remain available for viewing, diagnostics and QC.
  - No raw-FRF fitting was started (M1.3).
- **Files changed:**
  - added `src/domain/modal_input_source.py`
  - updated `src/services/stage_a_identification_service.py` (import, docstring, one
    policy call at the identification entry)
  - added `tests/test_modal_input_source.py` (14 tests)
  - updated `tests/test_stage_a_identification_service.py`: the synthetic experiment
    now declares itself a curve-fitted set (`dataset_type` 55, `mode_source`). Without
    a label the new policy correctly refuses it as `unknown`; no assertion changed.
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M1 IN_PROGRESS, M1.1 → REVIEW_READY)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** YES, for identification input only.
  `identify_stage_a` now refuses peak-derived or unclassifiable experimental modes.
  - Accepted evidence is unaffected: CARBON-4C/5A use PolyMAX curve-fitted sets
    (D-002), and the real SP02/bravo-1 and SP13/best imports classify as
    `curve_fitted`.
  - Comparison results are unchanged.
- **Tests (Windows):**
  - New `test_modal_input_source`: 14 ran, OK. With the fixture store configured both
    real fixtures are curve-fitted; without it, 2 subtests skip.
  - What it covers:
    - acceptance of the real reader's dataset-55 modal set and dataset-2414 modes;
    - refusal of the real FRF peak extraction (`universal_frf_review`) and of CMIF SVD
      candidates;
    - five unknown cases;
    - mixed sets, and a peak dataset type outranking a contradictory label;
    - `identify_stage_a` accepting curve-fitted input and refusing peak-derived and
      unknown input before any computation, also with an injected provider;
    - comparison of peak-labelled modes giving identical pairs, status, MAC and
      frequency error.
  - Stage-A suites (`test_stage_a_identification_service`,
    `test_uncertainty_and_stage_a_report`): 104 ran, OK.
  - Full suite: 925 ran, 0 failures. With the store configured, 923 passed and 2
    skipped (opt-in Abaqus); without it, 921 passed with the same 2 skipped tests plus
    4 skipped real-data subtests.
- **Abaqus run count:** 0
- **Known limitations:** the policy guards the current production identification
  entry. Later identification entry points must call `require_identification_input`.
- **Next gate:** SUPERVISOR review of M1.1. M1.2 must not start before acceptance.

## 2026-10-04 — M1 M1.1 — Supervisor acceptance recorded

- **Stage:** M1
- **Mini-step:** acceptance record for M1.1 (no new mini-step started)
- **Status:** M1.1 ACCEPTED. M1 IN_PROGRESS. M1.2–M1.4 TODO.
- **Review basis:** the SUPERVISOR reviewed commit
  `2fa48c27b6aa6b5c5e989d6a4523f21224403183` on `auto-id/m1`.
- **Accepted scope:**
  - The identification input-source policy is implemented: `curve_fitted` is
    accepted; `peak_derived` and `unknown` are refused for identification.
  - Normal modal comparison is unchanged, and peak-derived data remains available for
    diagnostics/QC.
  - The existing SP02/bravo-1 and SP13/best PolyMAX evidence remains valid.
  - No Abaqus. No change to registration, MAC, pairing, thresholds or modal
    algorithms.
  - No raw-FRF fitting is implemented yet (M1.3).
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept M1.1 input source policy`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/ROADMAP.md` (M1.1 ACCEPTED; M1 stage status)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization to start M1.2. `main` is unchanged
  (`9d30caf`).

## 2026-10-04 — M1 M1.2 — PolyMAX fixture production path

- **Stage:** M1
- **Mini-step:** M1.2 (production PolyMAX dataset 55/2414 path)
- **Status:** REVIEW_READY. M1.1 ACCEPTED. M1.3 and M1.4 TODO (M1.3 not
  implemented).
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M1.2): enforce PolyMAX fixture production path`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **What was added:** `services.production_modal_input.load_production_modal_input`.
  - **Single entry:** it is the only Auto-ID entry for experimental modes. A record is
    selected only by `fixture_id` in the accepted M0.2 manifest; there is no free
    file-path entry, and an unknown id raises `KeyError`.
  - **Checks, all reused without duplication:**
    - the M0.3 `verify_experiment_fixture` checks, run on the production reader
      output (captured through its injectable loader): source store, size and
      SHA-256; hash-sealed FrozenRegistration and its source, modal set and FE
      geometry bindings; modal set; mode source; mode and point counts; measured-DOF
      contract replay;
    - then the M1.1 input-source policy on every mode.
  - **Returned:** a `ProductionModalInput` with the reader's dataset unchanged
    (frequencies, damping, node order, shapes), the FrozenRegistration, the report,
    the source classification and a `provenance()` record.
- **Refused:**
  - wrong or missing source;
  - wrong SHA-256;
  - wrong modal set;
  - wrong point count;
  - wrong DOF contract, as a record or as imported data;
  - a peak-derived dataset;
  - a peak-derived or unclassifiable mode inside a fitted set.
- **Real fixtures through the production path (Windows):**
  - **SP02/bravo-1:** curve-fitted dataset 55, 9 modes, 121 points, U3, registration
    `9bf736d3…`, FE `72e8597a…`, source `2671db01…`.
  - **SP13/best:** 12 modes, 289 points, U3, `a8970e52…`, `34d69d79…`, `f2680235…`.
  - The production dataset equals a direct reader load mode by mode: frequency,
    damping, node order and shapes.
- **Test refactor:** the M0.3 synthetic-fixture builder moved unchanged into
  `tests/fixture_support.py`, a helper module with no `TestCase`. It is shared by
  `test_experiment_fixture_regression.py` (same tests and assertions) and the new
  tests.
  - The synthetic modes now carry the reader's per-mode curve-fitted labels, so the
    M1.1 policy sees realistic input.
- **Files changed:**
  - added `src/services/production_modal_input.py`
  - added `tests/test_production_modal_input.py` (13 tests)
  - added `tests/fixture_support.py`
  - updated `tests/test_experiment_fixture_regression.py` (uses the shared helper)
  - updated `docs/auto_id/fixtures/README.md` (production path section)
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M1.2 → REVIEW_READY)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO for existing paths. The new service is
  not yet called by any existing code. Readers, peak extraction, modal algorithms,
  registration, pairing, MAC, thresholds and `identify_stage_a` are unchanged.
- **Tests (Windows):**
  - New `test_production_modal_input`: 13 ran, OK. With the store configured the real
    fixtures load; without it, 2 subtests skip.
  - `test_experiment_fixture_regression`: 15 ran, OK, both with and without the store.
  - Full suite: 938 ran, 0 failures. With the store, 936 passed and 2 skipped (opt-in
    Abaqus); without it, 933 passed with the same 2 skipped tests plus 6 skipped
    real-data subtests.
- **Abaqus run count:** 0
- **Known limitation (for a later step, not changed here):** production Stage-A
  pairing (`_verified_experimental_source`) compares the registration's legacy
  source identity, which includes the original path and modification time. It
  therefore binds to the original machine location, while this production input
  binds by store + SHA-256. Reconciling the two is outside M1.2.
- **Next gate:** SUPERVISOR review of M1.2. M1.3 implementation must not start; a
  design review follows separately.

## 2026-10-04 — M1 — M1.3 design review added (docs only)

- **Stage:** M1
- **Mini-step:** none. This is a design review for M1.3, which stays `TODO`; M1.3 is
  not implemented.
- **Status:** M1.2 REVIEW_READY (`bc2ffce`). M1.3 TODO. M1.4 TODO.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): add M1.3 design review`
- **Content:** `docs/auto_id/M1_3_DESIGN_REVIEW.md` covers:
  - the purpose, and the current limitation (peak-derived and CMIF candidates are
    refused; M1.2 accepts only PolyMAX fixtures);
  - the proposed architecture: dataset 58 → FRF block → multi-mode fit →
    content-hashed curve-fitted artifact → M1.1 policy (new label refused as
    `unknown` until accepted) → M1.2 production input;
  - code locations, interface sketches, required provenance and QC;
  - the tests needed, including the SPEC §17 M1 gate on SP13 raw FRF;
  - refusal conditions, non-goals and risks;
  - nine decisions left to the SUPERVISOR: method family, bands, orders and
    stabilisation, pole selection and human review, uncertainty model, QC
    thresholds, raw-FRF fixtures, dependencies, and the M1.3/M1.4 split.
  - No algorithm is chosen.
- **Files changed:**
  - added `docs/auto_id/M1_3_DESIGN_REVIEW.md`
  - updated `docs/auto_id/ROADMAP.md` (pointer only; statuses unchanged)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (documentation only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR review of M1.2, and of the M1.3 design decisions before any
  M1.3 implementation.

## 2026-10-04 — M1 M1.2 — Supervisor acceptance recorded

- **Stage:** M1
- **Mini-step:** acceptance record for M1.2 (no new mini-step started)
- **Status:** M1.2 ACCEPTED. M1 IN_PROGRESS. M1.1 ACCEPTED. M1.3 and M1.4 TODO.
- **Review basis:** the SUPERVISOR reviewed commits
  `bc2ffcec3ab5dee876545c2d20faa2bc19fc87cc` (M1.2) and
  `ac1e0e30a7b69cf2c5601b5b649fe13478290725` (M1.3 design review) on `auto-id/m1`.
- **Accepted scope:**
  - The production PolyMAX fixture loading path is implemented, with fixture
    identity taken from the M0.2 manifest.
  - SHA, source, modal set, DOF and registration checks are enforced.
  - SP02 bravo-1 and SP13 best are validated.
  - The M1.1 source policy is reused, and peak-derived input remains refused.
  - No Abaqus. No registration, pairing or modal-algorithm changes.
- **M1.3 design review:** RECORDED ONLY. Not approved and not implemented; M1.3 stays
  TODO.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept M1.2 PolyMAX production path`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/ROADMAP.md` (M1.2 ACCEPTED; M1 stage status; design-review note)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR decisions on the M1.3 design, and authorization to start
  M1.3. `main` is unchanged (`9d30caf`).

## 2026-10-04 — M1 — M1.3 modal input architecture frozen (docs only)

- **Stage:** M1
- **Mini-step:** none. M1.3 design decision freeze; M1.3 implementation NOT STARTED
  and still `TODO`.
- **Status:** M1.1 and M1.2 ACCEPTED. M1.3 design DESIGN_ACCEPTED. M1.3
  implementation and M1.4 TODO.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): freeze M1.3 modal input architecture`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Decisions appended (SUPERVISOR):**
  - **D-018:** no internal FRF→modal fitting in Auto-ID v1 production; only validated
    curve-fitted datasets are accepted.
  - **D-019:** curve-fitted datasets are the only production identification input;
    peak-derived modes are forbidden.
  - **D-020:** dataset-58 FRFs are QC and future fitting inputs only.
  - **D-021:** future fitting goes through a replaceable `ModalFittingProvider`.
  - **D-022:** human modal selection only in research/review workflows.
- **Design review:** `M1_3_DESIGN_REVIEW.md` is marked DESIGN_ACCEPTED.
  - A new section 0 records the approved architecture (FRF → QC → optional fitting
    provider → validated curve-fitted dataset → Auto-ID), the decisions, the
    provider interface intent and which open decisions remain.
  - The original proposal is kept below and is superseded where it differs.
- **Conflict recorded, not resolved:** D-018 conflicts with SPEC §4, §6 S1 and §17,
  and with the ROADMAP M1 GATE (SP13 from raw FRF), all of which describe a built-in
  fit. By precedence (SPEC > DECISIONS), the SUPERVISOR must resolve this by a SPEC
  amendment or a redefined M1 gate before the M1 stage gate. The SPEC and the gate
  text are unchanged.
- **Files changed:**
  - `docs/auto_id/DECISIONS.md` (D-018 to D-022 appended)
  - `docs/auto_id/M1_3_DESIGN_REVIEW.md`
  - `docs/auto_id/ROADMAP.md` (M1.3 design note; conflict note)
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO. No FRF processing changed and no fitting algorithm
  was added.
- **Tests run:** none (documentation only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR resolution of the D-018 / SPEC / M1-gate conflict, and
  authorization of the next M1 step.

## 2026-10-04 — M1 — M1.3 FRF fitting architecture resolved (docs only)

- **Stage:** M1
- **Mini-step:** none. This is a design decision resolution; M1.3 implementation is
  NOT STARTED.
- **Status:** M1.1 and M1.2 ACCEPTED. **M1.3 DESIGN_ACCEPTED**, implementation NOT
  STARTED. M1.4 TODO.
- **Branch:** `auto-id/m1` (separate worktree). Commit `13973b7` is kept, not reverted.
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): resolve M1.3 FRF fitting architecture`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **SUPERVISOR resolution of the conflict recorded in `13973b7`:**
  - **D-023 (supersedes D-018):** FRF-to-modal fitting is a separate validated
    experimental preparation stage. Auto-ID material identification does not directly
    consume raw FRF.
    - The stage may be an external or an internal `ModalFittingProvider`.
    - Its output becomes production identification input only after provenance, QC,
      source classification and fixture identity validation.
  - **D-024 (supersedes D-020):** dataset-58 FRF records are valid modal-preparation
    inputs, including future multi-mode fitting. They are not direct
    material-identification observations.
  - **Kept unchanged:** D-019 (peak-derived modes forbidden for production
    identification), D-021 (replaceable `ModalFittingProvider`), D-022 (human mode
    selection only in research/review).
- **How "replace" was done:** `DECISIONS.md` is append-only, so D-018 and D-020 were
  not edited. They are superseded by the appended D-023 and D-024, as the decision-log
  rules require.
- **Conflict removed:** a built-in fit is an internal provider in the preparation
  stage. SPEC §4, §6 S1 and §17 and the ROADMAP M1 GATE are therefore consistent with
  the decisions, and the gate validates an internal provider.
  - The open-conflict note in ROADMAP and the `open_items` entry in STATUS.json are
    removed. The SPEC and the gate text are unchanged.
- **Status values:**
  - ROADMAP M1.3 row: `DESIGN_ACCEPTED` (implementation NOT STARTED).
  - STATUS.json: `m1.M1.3 = DESIGN_ACCEPTED`, `m1.M1.3_implementation = NOT_STARTED`.
  - `DESIGN_ACCEPTED` is a SUPERVISOR-set design status, used as instructed.
- **Files changed:**
  - `docs/auto_id/DECISIONS.md` (D-023, D-024 appended)
  - `docs/auto_id/M1_3_DESIGN_REVIEW.md` (section 0 rewritten for the resolved
    architecture)
  - `docs/auto_id/ROADMAP.md`
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (documentation only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization of the next M1 step.

## 2026-10-04 — M1 M1.3.1 — ModalFittingProvider interface boundary

- **Stage:** M1
- **Mini-step:** M1.3.1 (first M1.3 implementation sub-step: the provider boundary
  only)
- **Status:** M1.3.1 REVIEW_READY. M1.3 design DESIGN_ACCEPTED; M1.3 implementation
  IN_PROGRESS. M1.1 and M1.2 ACCEPTED. M1.4 TODO.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M1.3.1): add modal fitting provider interface`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **What was added:** `src/domain/modal_fitting.py`, the D-021/D-023 boundary with no
  fitting algorithm.
  - **`FrfInput`:** the validated H[response, reference, frequency] contract. It
    requires a strictly increasing finite axis, matching shape, finite values, unique
    keys, a declared quantity, consistent coherence and coherence status, and a source
    SHA-256. It has a deterministic `content_hash`.
  - **`ModalFittingProviderIdentity`:**
    - name, version, kind (`external` / `internal`) and an exact `mode_source` label;
    - a provider may not borrow a reader's curve-fitted label or a peak-derived label.
  - **`ModalFittingProvider`:** a runtime-checkable protocol with an `identity`
    attribute and `fit(frf, configuration)`.
  - **`ModalFittingOutput`:**
    - the `ModalDataset`;
    - the provider identity;
    - the provenance;
    - a QC-summary placeholder (`status` in NOT_EVALUATED / PASSED / FLAGGED /
      FAILED, filled by M1.4);
    - per-mode confidence placeholders (`frequency_sd_hz`, `damping_sd`, `None` while
      not evaluated).
  - **`ModalFittingProviderRegistry`:** explicit, with no global state. The default is
    empty, so no provider is admitted in v1.
  - **`validate_fitting_output` / `run_modal_fitting`:** refuse with
    `ModalFittingRefusal`, which is not a `ValueError` / `RuntimeError`. Refused:
    - unknown, impersonating or non-protocol providers;
    - output from another provider;
    - a non-`ModalDataset`, empty or non-finite dataset, missing damping, inconsistent
      points, or mislabelled modes;
    - missing provenance (FRF source SHA-256, FRF content hash, configuration and its
      hash, frequency band, pole selection);
    - provenance that does not match the actual FRF input or configuration;
    - a band outside the FRF axis;
    - manual pole selection in a production workflow (D-022);
    - a missing or invalid QC placeholder, or invalid confidence entries.
- **Not production input yet (D-023):** a validated output records its M1.1
  classification. A provider label is `unknown` until the SUPERVISOR admits it, so M1.1
  still refuses it. It must also be pinned as a fixture and pass the M1.2 path.
- **Not done (by instruction):**
  - no fitting algorithm (no PolyMAX, RFP or stabilisation diagram);
  - no pole selection;
  - no dataset-58 processing into modes;
  - no change to readers or identification;
  - no adapter from the existing FRF builder yet.
- **Files changed:**
  - added `src/domain/modal_fitting.py`
  - added `tests/test_modal_fitting.py` (20 tests; a mock provider returns a fixed
    synthetic result and does no fitting)
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M1.3 implementation IN_PROGRESS; M1.3.1 REVIEW_READY)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO. The new module is not called by any
  existing code.
- **Tests (Windows):**
  - New `test_modal_fitting`: 20 ran, OK. Coverage:
    - the provider contract;
    - that a validated output is not yet production input;
    - unknown, empty-registry, impersonating, non-protocol and label-borrowing
      providers;
    - invalid outputs;
    - missing and mismatched provenance;
    - D-022 manual selection;
    - the FRF input contract.
  - Full suite: 958 ran, 0 failures. With the store configured, 956 passed and 2
    skipped (opt-in Abaqus); without it, 953 passed with the same 2 skipped tests plus
    6 skipped real-data subtests.
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR review of M1.3.1.

## 2026-10-04 — M1 M1.3.1 — Supervisor acceptance recorded

- **Stage:** M1
- **Mini-step:** acceptance record for M1.3.1 (no new mini-step started)
- **Status:** M1.3.1 ACCEPTED. M1.3 IN_PROGRESS (design DESIGN_ACCEPTED). M1.1 and
  M1.2 ACCEPTED. M1.4 TODO.
- **Review basis:** the SUPERVISOR reviewed commit
  `f77045d165784244ad731792035398b4e3217421` on `auto-id/m1`.
- **Accepted scope:**
  - The `ModalFittingProvider` boundary is created, with provider identity and
    provenance contracts.
  - The registry is explicit, with no global provider state; unknown providers remain
    unadmitted.
  - Manual production mode selection remains forbidden.
  - No fitting algorithm is implemented. FRF processing, readers and identification
    are unchanged.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept modal fitting provider interface`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json` (`m1.M1.3` now `IN_PROGRESS`, as instructed; design
    acceptance kept in `M1.3_design_review`)
  - `docs/auto_id/ROADMAP.md` (M1.3 row and stage status; M1.3.1 ACCEPTED)
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization of the next M1.3 sub-step. M1.3.2 must not
  start automatically. `main` is unchanged (`9d30caf`).

## 2026-10-04 — M1 — PolyMAX provider decisions resolved (docs only)

- **Stage:** M1
- **Mini-step:** none. This is a design decision resolution after the M1.3 blocking
  report. M1.3 provider implementation is NOT STARTED.
- **Status:**
  - M1.1 and M1.2 ACCEPTED.
  - **M1.3 design ACCEPTED** (`DESIGN_ACCEPTED`).
  - M1.3 provider implementation NOT STARTED; the M1.3.1 interface boundary stays
    ACCEPTED.
  - M1.4 TODO.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): resolve PolyMAX provider decisions`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Decisions appended (SUPERVISOR).** D-018, D-020 and D-022 are not edited.
  - **D-026 (supersedes D-022):** frozen external modal selections made by a
    documented, hashed workflow may be production input. Live manual mode selection
    during an identification run remains forbidden.
  - **D-027:** the first production `ModalFittingProvider` is an external
    PolyMAX-compatible adapter, with no new FRF fitting algorithm.
  - **D-028:** M1 gates use fixture-specific reference values. For SP13 repeat-a these
    are about 205.65 / 212.66 / 228.61 Hz, not the 2026-09-09 values 206.15 / 212.61 /
    228.75 Hz.
  - **D-029:** internal FRF fitting is a future provider, not required before the first
    PolyMAX-compatible provider.
- **Design review:** `M1_3_DESIGN_REVIEW.md` stays DESIGN_ACCEPTED.
  - Section 0 now records the final architecture: Dataset-58 FRF → FRF preparation /
    external PolyMAX-compatible provider → validated curve-fitted modal dataset → M1.1
    source policy → M1.2 production loader → Auto-ID.
  - It also records the decision table, implementation notes from the blocking
    report, "M1.3 implementation is NOT STARTED", and "No unresolved conflict
    remains".
  - Implementation notes: FRFs and fit share one pinned export; damping comes from the
    stored PolyMAX pole without a reader change; a frozen-external value for
    `pole_selection` is needed; label admission is still required.
- **ROADMAP:**
  - the M1.3 row reads DESIGN_ACCEPTED with the provider implementation NOT STARTED;
  - the final architecture and the next step are recorded;
  - a D-028 reference-value note sits beside the M1 GATE, whose original text is
    unchanged.
- **STATUS.json:** `m1.M1.3 = DESIGN_ACCEPTED`, `m1.M1.3_implementation = NOT_STARTED`,
  `m1.M1.3.1 = ACCEPTED`, and a new `next_action`.
- **Files changed:**
  - `docs/auto_id/DECISIONS.md`
  - `docs/auto_id/M1_3_DESIGN_REVIEW.md`
  - `docs/auto_id/ROADMAP.md`
  - `docs/auto_id/STATUS.json`
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO. No code files changed.
- **Tests run:** none (documentation only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization for the PolyMAX provider implementation.

## 2026-10-04 — M1 M1.3 — External PolyMAX modal preparation provider

- **Stage:** M1
- **Mini-step:** M1.3 (the first production `ModalFittingProvider`; D-026, D-027)
- **Status:** M1.3 REVIEW_READY (design DESIGN_ACCEPTED; M1.3.1 interface ACCEPTED).
  M1.1 and M1.2 ACCEPTED. M1.4 TODO, not started.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M1.3): implement external PolyMAX modal preparation provider`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Chain implemented** (`services.external_polymax_provider`):
  1. **FRF preparation (`prepare_frf_input`):** the pinned export's dataset-58 FRFs
     become an `FrfInput`, using the existing `cmif_separation` multi-reference block
     builder unchanged. The quantity comes from the UFF spec types; both real exports
     are `velocity/force`.
  2. **`ExternalPolyMAXProvider.fit`:**
     - The configuration is exactly `fixture_id`, `modal_set` and
       `frequency_band_hz`.
     - It refuses an unknown fixture, a modal set other than the frozen one, a band
       outside the FRF axis or one that would trim a frozen mode, and FRFs from a
       different export.
     - It loads the frozen PolyMAX selection through M1.2 `load_production_modal_input`
       and keeps frequencies, shapes, point order and measured DOFs.
     - Damping comes from the stored dataset-55 pole, zeta = -Re(lambda)/|lambda|. The
       provider checks that each pole reproduces the reader frequency exactly.
     - Provenance holds the provider name and version, fitting method, fixture id,
       modal set, source file identity (name, SHA-256, size, store path), FRF source
       SHA-256 and content hash, quantity, coherence status, configuration and its
       hash, band, `pole_selection = external_frozen_selection`, registration and FE
       geometry hashes, measured DOFs, and damping source.
     - QC hooks only: per mode, raw frequency resolution, 2*zeta*f and coherence at
       resonance, with `status = NOT_EVALUATED`; M1.4 defines the policy. Confidence
       fields are `None` because the export carries no uncertainty.
  3. **Admission:** `admitted_provider_registry()` explicitly contains
     `external-polymax` / `1` (external). Other providers stay refused.
  4. **Validation:** the M1.3.1 `run_modal_fitting` checks, then the M1.1
     `require_identification_input`.
- **Accepted modules changed (minimal, required by D-026 and D-027):**
  - **`domain/modal_input_source.py`:**
    - the curve-fitted table is split into reader labels and admitted provider labels;
    - `external PolyMAX modal preparation/1` is admitted;
    - the classification rules are unchanged.
  - **`domain/modal_fitting.py`:**
    - `PoleSelection.EXTERNAL_FROZEN_SELECTION` is added. It is valid only for external
      providers with a pinned `fixture_id`, `modal_set` and `source_file` (name and
      SHA-256).
    - Live `manual_review` stays refused in production (D-026).
    - Provenance must name the producing provider (`provider_name` /
      `provider_version`).
    - Provider identities may not use reader or peak labels; admitted provider labels
      are allowed.
- **Real validation (Windows, data store configured):**
  - **SP02/bravo-1:**
    - 9 modes, 121 points, U3, registration `9bf736d3...`, FE `72e8597a...`;
    - classified `curve_fitted`;
    - frequencies 28.01 ... 219.44 Hz identical to M1.2;
    - damping equals PolyMAX's stated values (mode 1 zeta = 0.2378 %);
    - FRF frequency resolution 0.3125 Hz, coherence computed.
  - **SP13/best:**
    - 12 modes, 289 points, U3, registration `a8970e52...`, FE `34d69d79...`;
    - classified `curve_fitted`;
    - frequencies identical to M1.2, including 205.65 / 212.66 / 228.61 Hz;
    - damping equals PolyMAX's stated values (mode 1 zeta = 0.2341 %);
    - FRF frequency resolution 0.15625 Hz.
  - **SP13 gate (D-028):** the fixture-specific references 205.65 / 212.66 /
    228.61 Hz are reproduced within +/-0.05 Hz (they are the frozen PolyMAX values),
    and no mode lies within 1 Hz of the known false 217.5 Hz peak. The old 206.15 /
    212.61 / 228.75 Hz values are not used.
  - **Deterministic:** repeated runs give identical provenance.
- **Files changed:**
  - added `src/services/external_polymax_provider.py`
  - added `tests/test_external_polymax_provider.py` (17 tests)
  - updated `src/domain/modal_fitting.py`
  - updated `src/domain/modal_input_source.py`
  - updated `tests/test_modal_fitting.py` (mock provenance names its provider; 3 D-026
    tests added)
  - updated `docs/auto_id/fixtures/README.md` (provider section)
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M1.3 -> REVIEW_READY)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:**
  - **YES, admission:** a curve-fitted provider label is newly admitted to the M1.1
    policy, and frozen external selections are accepted by the provider boundary
    (D-026).
  - **NO, everything else:** readers, FRF processing, peak extraction, pairing,
    registration, identification, thresholds and gates are unchanged, and no existing
    production path calls the provider. M1.2 output is unchanged.
- **Tests (Windows):**
  - `test_external_polymax_provider`: 17 ran, OK. With the store configured both real
    fixtures pass the full chain; without it, 2 subtests skip.
    - **Provider:** success, registry admission, provenance, determinism, QC hooks.
    - **Refusals:**
      - wrong SHA-256, wrong FRF, wrong fixture;
      - wrong configuration: modal set, band outside the axis, band trimming a frozen
        mode, extra key;
      - wrong provider identity;
      - missing provenance;
      - wrong pole-selection type;
      - a peak-derived source: an FRF-only export is refused by the reader with no
        peak fallback, and a peak source type is refused by M1.2;
      - an unknown source type;
      - a mode without a stored pole.
    - **Compatibility:** M1.1 policy.
    - **Real-data regression:** SP02/SP13 compatibility, M1.2 equality, damping
      against PolyMAX's text, determinism, and the D-028 gate.
  - `test_modal_fitting`: 23 ran, OK.
  - Full suite: 978 ran, 0 failures. With the store configured, 976 passed and 2
    skipped (opt-in Abaqus); without it, 972 passed with the same 2 skipped tests plus
    8 skipped real-data subtests.
- **Abaqus run count:** 0
- **Known limitations:**
  1. **SP13 coherence.** The existing FRF builder reports SP13 coherence as
     `unavailable` although the export holds 289 coherence records. The SP13
     coherence-at-resonance hook is therefore `None`. FRF processing was not changed
     (out of scope); recorded for M1.4.
  2. **FRF-only exports.** These are refused through the reader's `ValueError` ("no
     valid dataset-55 modal sets"), not a typed refusal, because the accepted M0.3
     loader is unchanged.
  3. **No raw-FRF recovery.** The provider reproduces the frozen PolyMAX result and
     does not recover modes from raw FRF; that is future internal-provider work
     (D-027, D-029).
  4. **No uncertainty.** Confidence fields are `None` because the PolyMAX exports carry
     no uncertainty.
  5. **Legacy source identity in Stage-A pairing.** The Stage-A production pairing
     limitation recorded in M1.2 is unchanged.
- **Next gate:** SUPERVISOR review of M1.3. M1.4 must not start before authorization.

## 2026-10-04 — M1 M1.3 — Supervisor acceptance recorded

- **Stage:** M1
- **Mini-step:** acceptance record for M1.3 (no new mini-step started)
- **Status:** M1.3 ACCEPTED. M1 IN_PROGRESS. M1.1, M1.2, M1.3.1 and M1.3 ACCEPTED.
  M1.4 TODO.
- **Review basis:** the SUPERVISOR reviewed commit
  `4b8d73e48e2faaf8b284c148d25a687d584c69cd` on `auto-id/m1`.
- **Accepted scope:**
  - `ExternalPolyMAXProvider` is implemented, with no new fitting algorithm.
  - Frozen external PolyMAX selections are supported (D-026 implemented).
  - Provider provenance is implemented, and damping is recovered from the stored
    pole.
  - M1.1 compatibility and M1.2 fixture compatibility are verified.
  - SP02 bravo-1 validation passed. SP13 best validation passed using the pinned
    repeat-a values (D-028).
  - No Abaqus. Registration, pairing, the identification solver and thresholds are
    unchanged.
- **Accepted limitations:**
  - coherence evaluation is deferred to M1.4;
  - internal FRF fitting remains a future provider;
  - registration source path/timestamp reconciliation remains future work.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept external PolyMAX provider milestone`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Files changed:**
  - `docs/auto_id/STATUS.json` (adds `m1.accepted_limitations`)
  - `docs/auto_id/ROADMAP.md`
  - `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR authorization to start M1.4. `main` is unchanged
  (`9d30caf`).

## 2026-10-04 — M1 M1.4 — Experimental QC subsystem

- **Stage:** M1
- **Mini-step:** M1.4 (experimental QC)
- **Status:** M1.4 REVIEW_READY. M1.1, M1.2, M1.3.1 and M1.3 ACCEPTED.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M1.4): implement experimental QC subsystem`
  (`git log --format=%H -1 -- docs/auto_id/CHANGELOG.md`)
- **Domain (`src/domain/experimental_qc.py`):**
  - `ExperimentalQCStatus`: PASS / WARNING / FAIL / NOT_AVAILABLE.
  - `ExperimentalQCMetric`: a value of `None` means not available.
  - `QCWarning`: code, check, modes, and the SPEC rule it comes from.
  - `ExperimentalQCCheck`: carries `hard`; a diagnostic check cannot FAIL by
    construction.
  - `ExperimentalQCReport`: fixture id, modal source, provider identity, provenance
    reference, checks, warnings, metrics, `not_available`, policy, overall status,
    `admissible`, and a deterministic `content_hash`.
  - `ExperimentalQCRefusal`: raised for a hard failure; it is not a `ValueError` /
    `RuntimeError`.
- **Service (`src/services/experimental_qc.py`):**
  - `evaluate_experimental_qc(validated, frf, fixture)` builds the report and only
    reads the dataset.
  - `prepare_auto_id_experimental_input(fixture_id)` integrates QC after M1.3:
    M1.2 loader → `ExternalPolyMAXProvider` → M1.1 → QC.
  - It returns the provider dataset unchanged plus the report. It refuses only on a
    hard failure, and M1.1 and M1.2 are not bypassed.
- **Checks:**
  1. **`provenance` (hard):**
     - the provider is admitted and the required provenance keys are present
       (including the D-026 frozen-selection keys);
     - fixture id, source SHA-256, FRF content hash, configuration hash, registration
       hash and the dataset label are consistent.
  2. **`measurement_contract` (hard):**
     - the FrozenRegistration restores with the pinned hash;
     - mode and point counts, modal set, shared point list and point order match the
       registration;
     - the frozen DOF contract equals the fixture's, and every mode's measured-DOF
       mask (production `experimental_measurement_masks`) equals the frozen contract;
     - shapes are finite.
  3. **`frf_completeness`:** the FRF source identity is hard. Missing or empty
     channels and an FRF point-count mismatch are warnings. Channel, point, line and
     band metrics are recorded.
  4. **`coherence_quality` (diagnostic):** coherence at resonance below 0.9 is flagged
     (SPEC §6 S1). Missing coherence gives `NOT_AVAILABLE` plus a warning, never
     FAIL.
  5. **`frequency_resolution` (diagnostic):**
     - Δf and its non-uniformity; per mode the half-power bandwidth 2ζf and the
       bandwidth in lines; per adjacent pair the gap in Hz, relative and in lines, plus
       the modal overlap.
     - Flags: unresolved resonance 2ζf < 3Δf (SPEC §6 S1), close modes |Δf|/f < 3 %
       (SPEC §12.4, "only a trigger"), and damping not available.
  6. **`modal_confidence` (diagnostic):**
     - frequency, damping and shape uncertainty are recorded as `NOT_AVAILABLE` when
       the source has none; nothing is fabricated;
     - damping ratio;
     - phase collinearity as a metric only (the SPEC gives no limit);
     - experimental AutoMAC off-diagonal > 0.5 flagged (SPEC §6 S1).
  - **No other threshold is applied.**
- **Real fixtures (Windows, data store configured):**
  - **SP02/bravo-1:**
    - overall WARNING, admissible; provenance, contract and FRF completeness PASS;
    - coherence PASS: computed, every mode ≥ 0.917 at resonance;
    - resolution WARNING: Δf 0.3125 Hz, modes 1–8 unresolved by 2ζf < 3Δf, and modes
      4/5 close (90.57 / 91.95 Hz);
    - modal confidence NOT_AVAILABLE (no uncertainty in the export);
    - AutoMAC maximum off-diagonal 0.043.
  - **SP13/best:**
    - overall WARNING, admissible; provenance, contract and FRF completeness PASS;
    - coherence NOT_AVAILABLE (the FRF builder reports coherence unavailable; reader
      not modified);
    - resolution WARNING: Δf 0.15625 Hz, modes 1–5 unresolved, close pairs 4-5, 9-10
      and 10-11;
    - modal confidence NOT_AVAILABLE;
    - AutoMAC maximum off-diagonal 0.426.
  - **Metrics available on both:** FRF channels, points, lines and band; Δf;
    bandwidths; mode gaps and modal overlap; damping; phase collinearity; AutoMAC.
    SP02 also has coherence at resonance.
  - **Metrics not available:** coherence at resonance (SP13); frequency, damping and
    shape uncertainty (both).
- **Files changed:**
  - added `src/domain/experimental_qc.py`
  - added `src/services/experimental_qc.py`
  - added `tests/test_experimental_qc.py` (18 tests)
  - updated `tests/test_external_polymax_provider.py` (`synthetic_export` gains an
    optional `with_coherence`)
  - updated `docs/auto_id/fixtures/README.md` (QC section)
  - updated `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`
    (M1.4 → REVIEW_READY)
  - updated `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO for existing paths.
  - QC is new and observes only.
  - The provider, readers, FRF processing, registrations, pairing, identification
    mathematics and the solver are unchanged.
  - The new chain `prepare_auto_id_experimental_input` adds a refusal only for hard
    QC failures (broken provenance, fixture identity or measurement contract).
- **Tests (Windows):**
  - New `test_experimental_qc`: 18 ran, OK, with real fixtures when the store is
    configured. Coverage:
    - **core:** valid report, determinism, provenance preserved, dataset untouched;
    - **hard failures:** missing source, invalid fixture, invalid DOF contract,
      broken provenance (FRF hash, missing source file, configuration hash,
      unadmitted provider), wrong FRF source, refusal raised by the chain;
    - **diagnostics:** missing coherence, unavailable uncertainty and AutoMAC, close
      modes, insufficient resolution, missing damping, low coherence, phase
      collinearity, a diagnostic check unable to FAIL;
    - **regression:** SP02 and SP13 QC, M1.3/M1.2 compatibility, determinism.
  - **Test-order note:** the DOF-contract test sets an explicit measured mask. When
    the app's `install_*` layers are active in the same process (as in the full
    suite), the reader attaches explicit masks, which take precedence over vector
    data.
  - Full suite: 996 ran, 0 failures. With the store configured, 994 passed and 2
    skipped (opt-in Abaqus); without it, 989 passed with the same 2 skipped tests
    plus 10 skipped real-data subtests.
- **Abaqus run count:** 0
- **Limitations (not claimed):**
  - no automatic mode rejection: QC never removes modes;
  - no complete uncertainty estimation: uncertainty is reported as available or
    `NOT_AVAILABLE`;
  - no universal QC thresholds: only the SPEC flag rules above, as warnings, pending
    scientific validation;
  - phase complexity has no limit;
  - SP13 coherence evaluation is limited by the unchanged FRF builder.
- **Next gate:** SUPERVISOR review of M1.4.

## 2026-10-04 — M1 M1.4 — Supervisor acceptance recorded

- **Stage:** M1
- **Mini-step:** acceptance record for M1.4 (no new mini-step started)
- **Status:** M1.4 ACCEPTED. M1.1, M1.2, M1.3.1 and M1.3 ACCEPTED. M1 stage closure
  follows separately.
- **Review basis:** the SUPERVISOR reviewed commit
  `c411bb9842fbdb6feb546fbdf3cbf3ae7ba6634f` on `auto-id/m1`.
- **Accepted scope:**
  - The experimental QC subsystem is implemented. QC is observational and never
    modifies modal datasets.
  - Provenance, fixture identity and the measurement contract are hard checks.
    Coherence, frequency resolution, the close-mode trigger, AutoMAC and phase
    complexity are diagnostic.
  - `NOT_AVAILABLE` remains explicit, and no uncertainty values are invented.
  - SP02/bravo-1 and SP13/best pass all hard checks.
  - No Abaqus. No pairing, registration or identification-solver changes.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): accept M1.4 experimental QC`
- **Files changed:** `docs/auto_id/STATUS.json`, `docs/auto_id/ROADMAP.md`,
  `docs/auto_id/CHANGELOG.md` (this entry)
- **Scientific runtime behaviour changed:** NO
- **Production code changed:** NO
- **Tests run:** none (status record only)
- **Abaqus run count:** 0

## 2026-10-04 — M1 — Stage-closure verification; M1 BLOCKED_SPEC_GATE

- **Stage:** M1 (stage closure)
- **Status:** M1.1, M1.2, M1.3.1, M1.3 and M1.4 ACCEPTED. **M1 stage
  `BLOCKED_SPEC_GATE`.** M2 NOT STARTED. No stage PR created.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commits in this closure:**
  - `b41af39` — M1.4 acceptance record.
  - `f5279dd` — `tests/test_m1_stage_gate.py`.
  - The commit that introduces this entry — M1 gate rewrite and stage state.
- **M1 gate text rewritten (ROADMAP)** without changing scientific intent:
  - fixture-specific references (D-028);
  - the old 206.15 / 212.61 / 228.75 Hz values marked as historical (2026-09-09
    acquisition);
  - **Gate A**, the external PolyMAX provider: **PASS**;
  - **Gate B**, raw-FRF recovery by an internal provider: **not claimed**, future
    work (D-029);
  - the external provider is stated explicitly not to re-fit raw FRF.
- **Gate A evidence** (Windows, data store configured; `test_m1_stage_gate`, plus the
  per-milestone real-data tests):
  - **SP02/bravo-1:**
    - source SHA-256 `2671db01…`, modal set `bravo-1`, 9 modes, 121 points, U3;
    - registration `9bf736d3…`, FE `72e8597a…`;
    - provider `external-polymax/1`, `external_frozen_selection`, damping equals the
      stored poles;
    - QC overall WARNING, with provenance, contract and FRF completeness PASS;
    - dataset identical to M1.2 and unchanged through QC;
    - the real FRF peak path (26 candidates) is refused by M1.1.
  - **SP13/best:**
    - source SHA-256 `f2680235…`, modal set `best`, 12 modes, 289 points, U3;
    - registration `a8970e52…`, FE `34d69d79…`;
    - provider and damping as for SP02;
    - QC overall WARNING, hard checks PASS (coherence NOT_AVAILABLE);
    - D-028 references 205.65 / 212.66 / 228.61 Hz reproduced, no mode within 1 Hz of
      217.5 Hz;
    - the real FRF peak path (22 candidates; 205.62 / 212.66 / 222.66 / 228.59 Hz in
      195–235 Hz, 230.89 Hz missed) is refused by M1.1.
- **Why the stage is blocked.** SPEC §4, footnote to `modes.unv`: "If `modes.unv` is absent and only `frf.unv` exists, modes are built by the built-in **multi-mode** fit (stage M1)."
  - This normative sentence assigns the built-in multi-mode fit (FRF-only packages) to
    stage M1. The accepted M1 refuses FRF-only packages, and D-029 defers internal
    fitting.
  - By document precedence, SPEC (1) outranks DECISIONS (2), so no new decision can
    supersede it. The SPEC's own mechanism is a SUPERVISOR clarification in §19.
  - The §17 M1 row ("built-in multi-mode fit"; "SP13 from raw FRF … found") conflicts
    too, although §17 labels its criteria archival.
  - §6 S1 ("dataset 55 (priority) or the built-in multi-mode fit") is satisfied.
- **Proposed SPEC §19 clarification** (for SUPERVISOR decision; not applied):

**4. Modal preparation stage and the M1 gate (D-023, D-027, D-028, D-029).**
The built-in multi-mode fit named in §4 (footnote to `modes.unv`), §6 S1 and the §17 M1
row is an internal `ModalFittingProvider` of the separate modal preparation stage
(D-023). It is future provider work (D-029) and not a condition for closing stage M1.

Stage M1 closes on the external PolyMAX-compatible provider (D-027). Its conditions:
- the pinned FRF and the frozen PolyMAX selection come from the same accepted export;
- fixture and source provenance is exact;
- the provider reproduces the frozen modal dataset, with damping from the stored
  poles;
- no peak-derived input enters identification;
- the experimental QC hard checks pass.

Until an internal provider is accepted, a package with only `frf.unv` is refused.

M1 gate reference values are fixture-specific (D-028). For SP13 repeat-a (`SP13/best`)
they are about 205.65 / 212.66 / 228.61 Hz. The §17 values 206.15 / 212.61 Hz belong
to the 2026-09-09 acquisition.

The raw-FRF recovery criterion of the §17 M1 row becomes the acceptance gate of the
first internal provider.

- **Tests:**
  - **Focused M1 suites** (fixture, regression, source policy, production input,
    modal fitting, provider, QC, stage gate, Stage-A identification, discovery guard),
    store configured: 211 ran, OK.
  - **Full Windows suite** (Python 3.14.6): 997 ran, 0 failures. With the store
    configured, 995 passed and 2 skipped (opt-in Abaqus). Without it, 989 passed with
    2 skipped tests and 12 skipped real-data subtests.
  - **Linux CI** on `f5279dd` (ubuntu-latest, Python 3.11, run 37164499562): 994 ran,
    OK, skipped=18.
    - 12 real-fixture subtests: 6 real-data tests × 2 fixtures, no store on CI;
    - 2 opt-in Abaqus tests;
    - 4 headless-Tk skips, one of them class-level.
    - These are the categories classified in M0.4; none are new.
- **Scientific runtime behaviour changed:** NO (documentation and tests only)
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR resolution of `BLOCKED_SPEC_GATE`. No M1 stage PR before
  then. M2 not started.

## 2026-10-04 — M1 — Final closure: SPEC §19 items 4–5, suspension-aware QC, M1 ACCEPTED

- **Stage:** M1 (final stage closure)
- **Status:** M1.1, M1.2, M1.3 and M1.4 ACCEPTED. **M1 Gate A PASS. M1 Gate B
  `FUTURE_INTERNAL_PROVIDER`. M1 stage ACCEPTED** (SUPERVISOR-authorized conditional
  closure). `BLOCKED_SPEC_GATE` is removed. M2 NOT STARTED.
- **Branch:** `auto-id/m1` (separate worktree)
- **Commits:**
  - `ef95cbe` — `auto-id(M1.4): add suspension-aware QC and mode eligibility`.
  - The commit that introduces this entry — the normative SPEC amendment and the
    stage-closure documents.
- **SPEC §19 (normative; SUPERVISOR-authorized):**
  - **Item 4, M1 modal-preparation scope and staged internal fitting:**
    - Auto-ID never consumes raw FRF.
    - Fitting is a separate stage behind `ModalFittingProvider`.
    - The first provider is the external frozen PolyMAX-compatible provider.
    - FRF-only packages are refused until an internal provider is implemented,
      admitted and validated. An internal fitter is not an M1 closure condition.
    - The §17 raw-FRF recovery criterion is the gate of the first internal provider.
    - Peak-derived modes are prohibited without exception.
    - Fixture references are not mixed; SP13/best is about 205.65 / 212.66 /
      228.61 Hz, and the 2026-09-09 values are historical.
    - It supersedes the earlier stage-assignment wording of §4, §6 S1 and §17 where
      they differ. The historical text is unchanged.
  - **Item 5, suspension threshold ownership:**
    - `suspension_max_hz` is a physical passport / acquisition property (M2) and is
      never guessed.
    - The §4.1 example value 18.0 is illustrative, not a default.
    - QC evaluates the threshold when a trusted value exists, and is `NOT_AVAILABLE`
      otherwise.
    - Modes below the threshold must not enter material identification once M2
      supplies it.
    - M1 closes without inventing the value; one-button readiness needs M2.
- **DECISIONS:** D-030 and D-031 appended for traceability. Earlier entries are
  unchanged.
- **Suspension-aware QC (`ef95cbe`):**
  - **`TrustedSuspensionThreshold`:** a finite positive value plus its documented
    physical source. It is the only accepted input; nothing infers the value from
    modal or FE frequencies, and there is no default.
  - **QC check `suspension_threshold` (diagnostic):** `NOT_AVAILABLE` without a
    trusted value. With one, it reports the threshold, the modes below it and the
    lowest mode at or above it.
  - **`ExperimentalModeEligibility`:** kept separate from the observational QC
    report, on `AutoIDExperimentalInput`.
    - `identification_dataset()` is the explicit view without the excluded modes.
    - `require_eligible()` raises `ExperimentalModeEligibilityRefusal`.
    - The provider dataset is never changed.
  - **`prepare_auto_id_experimental_input`** takes an optional
    `suspension_threshold`. The M0.2 manifest is not changed.
- **M1 gate (ROADMAP) rewritten:**
  - **Gate A**, the initial production modal-input layer, has explicit conditions,
    including honest suspension handling: **PASS**.
  - **Gate B**, the first internal provider, keeps the original raw-FRF scientific
    requirement: `FUTURE_INTERNAL_PROVIDER`, not passed.
- **Stage verification** (`test_m1_stage_gate`, Windows, data store configured): the
  chain is manifest → M1.1 → M1.2 → M1.3 → M1.4 QC → mode eligibility → Auto-ID
  input.
  - **SP02/bravo-1:**
    - source SHA-256 `2671db01…`, modal set `bravo-1`, 9 modes, 121 points, U3;
    - registration `9bf736d3…`, FE `72e8597a…`;
    - `external-polymax/1` with `external_frozen_selection`, damping equals the
      stored poles;
    - QC hard checks PASS, suspension `NOT_AVAILABLE`, all modes eligible pending M2;
    - dataset unchanged and equal to M1.2;
    - real peak-derived modes refused;
    - deterministic.
  - **SP13/best:**
    - source SHA-256 `f2680235…`, modal set `best`, 12 modes, 289 points, U3;
    - registration `a8970e52…`, FE `34d69d79…`;
    - provider and damping as for SP02;
    - QC hard checks PASS, coherence and suspension `NOT_AVAILABLE`;
    - D-028 references 205.65 / 212.66 / 228.61 Hz reproduced, no mode within 1 Hz of
      217.5 Hz;
    - real peak-derived modes refused;
    - deterministic.
- **Tests:**
  - **`test_experimental_qc`:** 27 tests, 9 of them new suspension tests. They cover:
    - an absent threshold giving `NOT_AVAILABLE`;
    - a supplied threshold identifying the modes below it;
    - a threshold below all modes giving PASS;
    - identification blocking modes below the threshold;
    - the dataset staying unchanged;
    - no inference from modal frequencies;
    - no FE input, and untrusted plain values refused;
    - a trusted threshold requiring a physical source;
    - deterministic reports.
  - **`test_m1_stage_gate`:** now also checks suspension `NOT_AVAILABLE`, full
    eligibility and determinism.
  - **Focused M1 suites, store configured:** 220 ran, OK.
  - **Full Windows suite** (Python 3.14.6): 1006 ran, 0 failures. With the store
    configured, 1004 passed and 2 skipped (opt-in Abaqus). Without it, 998 passed
    with 2 skipped tests and 12 skipped real-data subtests.
  - **Linux CI** on `ef95cbe` (ubuntu-latest, Python 3.11, run 37167897161): 1003
    ran, OK, skipped=18 — 12 real-fixture subtests, 2 opt-in Abaqus, 4 headless Tk.
    These are the categories classified in M0.4.
- **Accepted limitations:**
  - historical fixtures have suspension `NOT_AVAILABLE` until M2;
  - SP13 coherence is `NOT_AVAILABLE` with the unchanged FRF builder;
  - the exports carry no modal uncertainty;
  - internal fitting is future work (Gate B);
  - registration source path/timestamp reconciliation remains future work;
  - there is no automatic mode rejection beyond the explicit suspension eligibility,
    and no universal QC thresholds.
- **Scientific runtime behaviour changed:**
  - **YES, for the Auto-ID input only:** a trusted suspension threshold now excludes
    modes below it from `identification_dataset()`.
  - **NO, everything else:** no trusted value exists yet, so the historical fixtures
    are unaffected. Readers, the provider, registration, pairing and identification
    are unchanged.
- **Abaqus run count:** 0
- **Next gate:** the M1 stage PR (`auto-id/m1` → `main`) merges only under explicit
  HUMAN authorization. Afterwards, record the main merge SHA. M2 starts only on
  SUPERVISOR authorization.

## 2026-10-04 — M1 merged to main; M2 started

- **Stage:** M1 → M2
- **M1 merge:** PR #27 (`auto-id/m1` → `main`), merge commit `d00120514bdd75bc4421891486218c3cf87d3438`, recorded
  in `STATUS.json` (`main_merges`, `m1.merged_to_main`) and in the ROADMAP.
- **M2 branch:** `auto-id/m2`, created from exactly `d00120514bdd75bc4421891486218c3cf87d3438` (separate worktree).

## 2026-10-04 — M2 — Specimen passport and physical registration (M2.1–M2.5)

- **Stage:** M2
- **Status:** M2.1–M2.5 REVIEW_READY. M2 stage REVIEW_READY. Not accepted by the
  worker.
- **Branch:** `auto-id/m2`
- **Commits:**
  - `ab728a2` — passport, identities and remount linkage.
  - `a00817c` — physical registration, uncertainty diagnostic, path/timestamp
    reconciliation, M1 integration and the stage gate.
  - The commit that introduces this entry — documentation.
- **M2.1 — `domain.specimen_manifest`:**
  - **Schema:** strict `auto-id/specimen/v1.1` passport.
  - **Specimen types:** sandwich, bare_plate, core_tile.
  - **Physical measurements:** plan, masses, face thickness (9+ points per sheet),
    core height, materials, and `suspension_max_hz` with its source.
  - **Geometry calibration:** mode, coordinate calibration with provenance, measured
    FE surface, traceable orientation (axes, reference, source), measured uncertainty,
    corner A or panel-edge offsets.
  - **FE geometry reference:** identity plus a pinned file.
  - **Acquisition:** session, grid, fixture link, protocol, remount link with kind and
    evidence.
  - **Refused:**
    - missing schema, unknown fields or unsupported types;
    - collapsed or empty identities;
    - invalid values, or nulls without a declared reason;
    - incomplete calibration or unknown modes;
    - untraceable orientation;
    - absolute paths;
    - legacy extent-fit calibration.
  - **No defaults:** the illustrative 18 Hz is never used.
  - **Hash:** a deterministic canonical `manifest_hash`, independent of key order.
- **M2.2 — identities:** typed `FamilyId`, `DesignId`, `PhysicalSpecimenId`,
  `TestRunId`, which must be distinct.
  - A remount keeps `physical_specimen_id` and gets a new `test_run_id`.
  - The SP02/SP13 `test_run_id` values are the recorded acquisition container names.
    They supersede the provisional M0.2 run labels; the M0.2 manifest is unchanged.
- **M2.3 — `services.physical_registration`:**
  - **Inputs:** a FrozenRegistration built from the passport calibration, the pinned
    experimental geometry and the identity-verified FE geometry. No MAC, frequency,
    mode-shape or identification input.
  - **Modes:**
    - `corner_coordinates_mm`: documented axes checked by the corner-A marker; the
      marker cannot override them, and a contradictory marker is refused.
    - `scan_to_panel_edges`: measured offsets.
    - `documented_centered_alignment`: historical. It uses the existing geometric
      candidate whose rotation **equals** the documented one, never ranked by modal
      agreement, and is never physically complete.
  - **Deterministic.**
  - **FE geometry for SP02/SP13:** the authenticated CARBON-4C extraction, copied to
    the `carbon-project-archive` store (`fe_geometry/SP02_fe_geometry.csv` sha
    `79bffd96…`, `fe_geometry/SP13_fe_geometry.csv` sha `78d19737…`) and recorded in
    `ARCHIVE_MANIFEST.json`. The FE identities equal the accepted `72e8597a…` /
    `34d69d79…`.
- **M2 gate — accepted FrozenRegistration reproduction: PASS.**
  - **SP02:** `9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164`.
  - **SP13:** `a8970e525d10173af3d3b030b1150ca24432b616e1b52f6e8cfeefe2946f58a4`.
  - Both are reproduced exactly (hash and full content) from the passports.
  - **Legacy source identity:** the experimental source's legacy path/mtime come from
    the referenced accepted registration, verified by its hash and by the fixture
    SHA-256/size. They are not stored in the passport.
  - **Physical basis:** the historical documented centred alignment. **Not physically
    complete:** missing a corner-A marker or measured edge offsets, and measured
    translation/scale/rotation uncertainty.
- **M2.4 — `services.registration_uncertainty`:**
  - It uses a deterministic ±σ perturbation set from measured uncertainty only, and
    reports nominal, minimum and maximum MAC per accepted pair.
  - `registration_limited` is true on a 0.8 crossing; false only when every component
    was evaluated; null when not evaluable.
  - It never returns, selects or feeds back a best perturbation. The nominal
    registration is unchanged.
  - **Executable now:** the MAC-threshold trigger.
  - **Deferred:** the pairing-change trigger (`DEFERRED_M4`).
  - **SP02/SP13:** `NOT_AVAILABLE`.
- **M2.5 — `domain.acquisition_linkage`:**
  - **Classification:** frequency + shape, frequency only (different grid), not
    eligible (different panel, same run or different protocol), insufficiently
    documented (no panel id, remount link or protocol).
  - **Link validation:** unique run ids; remounts of known runs on the same recorded
    panel; no cycles.
  - No Σ_setup value is computed, and specimen scatter is never Σ_setup.
  - **SP13 121/289:** UNCONFIRMED (same panel / independent remount not established);
    at most frequency-only once documented.
- **M1 integration:** `prepare_auto_id_experimental_input(..., specimen_passport=)`
  takes the trusted suspension threshold from the passport. It refuses a passport for
  another fixture and a passport combined with an explicit threshold.
  - **SP02/SP13:** suspension remains `NOT_AVAILABLE`; hard QC passes.
- **Path/timestamp debt (M1 accepted limitation): resolved for content-hashed
  registrations.**
  - `FrozenRegistration.check_content_compatible` checks SHA-256 + size and ignores
    path/mtime.
  - Stage-A pairing uses it when the registration has a content hash, and the legacy
    exact check otherwise.
  - New physical registrations record `store:relative_path` and no mtime.
  - The accepted `check_compatible` contract is unchanged.
- **Files:**
  - **added code:** `src/domain/specimen_manifest.py`,
    `src/domain/acquisition_linkage.py`, `src/services/physical_registration.py`,
    `src/services/registration_uncertainty.py`;
  - **added data and docs:** `docs/auto_id/specimens/{SP02,SP13}.specimen.json`,
    `docs/auto_id/specimens/README.md`;
  - **added tests:** `tests/m2_support.py`, `tests/test_specimen_manifest.py` (23),
    `tests/test_acquisition_linkage.py` (14), `tests/test_physical_registration.py`
    (17), `tests/test_registration_uncertainty.py` (9),
    `tests/test_passport_qc_integration.py` (4), `tests/test_m2_stage_gate.py` (1, real
    data);
  - **updated:** `src/domain/registration.py` (content check),
    `src/services/stage_a_identification_service.py` (content-based registration
    check), `src/services/experimental_qc.py` (passport threshold), and
    `docs/auto_id/STATUS.json`, `ROADMAP.md`, `CHANGELOG.md`.
- **Scientific runtime behaviour changed:**
  - **YES, in two places:**
    - Stage-A pairing now accepts a registration whose experimental source has the
      same content at another path/mtime; different content is still refused.
    - A passport-supplied suspension threshold reaches M1.4 eligibility.
  - **NO:** no M1 threshold, pairing, registration content, modal algorithm or
    material parameter changed.
- **Tests:**
  - **Focused M2 + related M1 suites:** 254 ran, OK.
  - **Full Windows suite** (Python 3.14.6): 1074 ran, 0 failures. With both data
    stores configured, 1072 passed and 2 skipped (opt-in Abaqus). Without stores, 1065
    passed with 2 skipped tests and 14 skipped real-data subtests.
  - **Linux CI** on `a00817c` (ubuntu-latest, Python 3.11, run 37171058455):
    1071 ran, OK, skipped=20 — 14 data-store subtests, 2 opt-in Abaqus, 4 headless Tk.
    These are the categories classified in M0.4.
- **Abaqus run count:** 0
- **Not done (by instruction):** M3 not started; no optimisation; no Σ_setup value; no
  invented measurements.
- **Next gate:** SUPERVISOR review of M2 (stage PR `auto-id/m2` → `main`).

## 2026-10-04 — M2 — Final supervisor rework: units, registration basis, production readiness

- **Stage:** M2
- **Status:** M2.1–M2.5 REVIEW_READY. M2 stage REVIEW_READY. Not accepted by the
  worker.
- **Branch:** `auto-id/m2` (PR #28)
- **Commit:** the commit that introduces this entry.
- **Unit-safe physical registration:**
  - Passport lengths are physical mm: `corner_A.fe_xy_mm`, `panel_edges.x_mm/y_mm`,
    `uncertainty.translation_mm` and the surface tolerance.
  - They are converted to the Abaqus model unit `coordinate_calibration.abaqus_unit`
    (mm/cm/m/µm) with `coordinate_calibration.millimetres_to_model_units`
    (`UNIT_TO_METRES`).
  - Experimental raw units and the comparator convention are unchanged.
- **Status model:**
  - `GeometryCalibration.physically_complete` is replaced by two separate facts:
    - `registration_basis_status`: `PHYSICAL` / `LEGACY_REPLAY` / `INCOMPLETE`;
    - `uncertainty_availability`: `AVAILABLE` / `PARTIAL` / `NOT_AVAILABLE`.
  - `missing_physical_evidence` now lists nominal-registration gaps only;
    `missing_uncertainty` is separate.
  - A physical registration without measured uncertainty stays `PHYSICAL`.
  - `documented_centered_alignment` is `LEGACY_REPLAY` (with an accepted registration
    reference) or `INCOMPLETE`, never `PHYSICAL`.
- **Production readiness guard:**
  - `PhysicalRegistrationResult.require_production_ready()` and
    `require_production_physical_registration()` raise `ProductionReadinessRefusal`
    with explicit reasons.
  - They refuse a non-physical basis, a missing physical reference, a non-traceable
    orientation, a legacy path/mtime source identity, or a missing
    `physical_specimen_id`.
  - Missing uncertainty alone is never a refusal.
  - A replay is never upgraded.
- **Identity namespaces:**
  - The cross-namespace string-inequality rule is removed; the typed IDs are the
    namespaces, so `DesignId("X") ≠ PhysicalSpecimenId("X")`.
  - `validate_acquisition_links` now also refuses one `physical_specimen_id` with
    contradictory `design_id`/`family_id`.
  - Duplicate run ids, impossible remount links and same-run remounts are still
    refused.
- **Non-finite MAC:**
  - A missing or non-finite MAC is recorded as an invalid perturbation
    (`PairMacRange.invalid_perturbations`, value `None`) and never enters min/max or
    the crossing.
  - A missing nominal MAC cannot cross.
  - Incomplete evidence gives `PARTIAL` with `registration_limited = None`; a real
    crossing among valid values still gives `True`.
- **Historical replay:**
  - SP02 `9bf736d3…c164` and SP13 `a8970e52…58a4` still reproduce with full content
    equality (`source_identity_basis = legacy_accepted_registration`).
  - Both are `LEGACY_REPLAY` with uncertainty `NOT_AVAILABLE`.
  - `require_production_ready()` refuses both.
- **Gate framing:**
  - SOFTWARE / REGRESSION GATE = PASS.
  - CURRENT SP02/SP13 PRODUCTION PHYSICAL READINESS = NOT_READY.
- **Files:**
  - **code:** `src/coordinate_calibration.py`, `src/domain/specimen_manifest.py`,
    `src/domain/acquisition_linkage.py`, `src/services/physical_registration.py`,
    `src/services/registration_uncertainty.py`;
  - **tests:** `tests/m2_support.py`, `tests/test_specimen_manifest.py`,
    `tests/test_acquisition_linkage.py`, `tests/test_physical_registration.py`,
    `tests/test_registration_uncertainty.py`, `tests/test_m2_stage_gate.py`;
  - **docs:** `docs/auto_id/STATUS.json`, `ROADMAP.md`, `CHANGELOG.md`,
    `specimens/README.md`.
- **SPEC / DECISIONS:** unchanged (no contradiction found; implementation fixes only).
- **Scientific runtime behaviour changed:**
  - **YES:**
    - Physical registration in a non-mm FE model now uses the correct physical
      lengths.
    - Non-finite MACs no longer reach the uncertainty range or crossing.
    - Equal tokens across identity namespaces are accepted.
  - **NO:** no accepted registration, M1 threshold, pairing, modal algorithm or
    material parameter changed.
- **Tests:**
  - **Focused M2:** 84 ran, OK, including the real-data stage gate.
  - **Related M1 + Stage-A:** 209 ran, 207 passed, 2 skipped (opt-in Abaqus).
  - **Full Windows suite** (Python 3.14.6): 1090 ran, 0 failures, 0 errors. With both
    data stores, 1088 passed and 2 skipped (opt-in Abaqus). Without stores, 1081
    passed with 2 skipped tests and 14 skipped real-data subtests.
  - **Linux CI:** recorded in the follow-up entry.
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR review of M2 (PR #28).

## 2026-10-04 — M2 — Final rework: Linux CI recorded

- **Stage:** M2 (REVIEW_READY; not accepted by the worker)
- **Linux CI** on `a9e6322` (ubuntu-latest, Python 3.11, run 37172600996): success.
  1087 ran, OK, skipped=20 (14 data-store subtests, 2 opt-in Abaqus, 4 headless Tk).
  These are the categories classified in M0.4.
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR review of M2 (PR #28).

## 2026-10-04 — M2 merged to main; M3 branch created; supervised stage batches

- **Stage:** M2 → M3
- **M2 acceptance:**
  - M2.1–M2.5 and the M2 stage are ACCEPTED by the SUPERVISOR, before the HUMAN
    merge.
  - Accepted head: `5c60abc`. Last implementation commit: `a9e6322`.
- **M2 merge:** PR #28 (`auto-id/m2` → `main`), merge commit `7af9038c5486560c5d2d0b6d571a354766e29d77`.
  - Recorded in `STATUS.json` (`main_merges`, `m2.merged_to_main`,
    `last_accepted_stage = M2`) and in the ROADMAP.
- **M2 conclusions (unchanged, intentionally separate facts):**
  - software / regression gate PASS;
  - SP02/SP13 historical accepted-registration replay PASS;
  - SP02/SP13 production physical readiness NOT_READY.
- **M3 branch:** `auto-id/m3`, created from exactly `7af9038c5486560c5d2d0b6d571a354766e29d77` (separate worktree).
  - M3 is `NOT_STARTED`; M3.1–M3.5 are `TODO`.
- **Governance (execution granularity only):** `CLAUDE.md` and `AGENTS.md` are
  updated identically.
  - **Default:** one mini-step at a time.
  - **Exception:** a SUPERVISOR-authorised batch of named mini-steps within one stage
    may run without stopping between mini-steps. Roadmap order is kept, and each
    mini-step only reaches `REVIEW_READY`. There is no self-acceptance and no future
    stage.
  - **Unchanged:** the Abaqus, destructive-git and merge HUMAN gates.
  - **Stage PR:** only after the whole batch is `REVIEW_READY`, then STOP.
  - No scientific rule changed; no DECISIONS entry is required.
- **Code changed:** none.
- **Abaqus run count:** 0

## 2026-10-04 — M3.1 — Manifest-driven material location

- **Stage:** M3 (SUPERVISOR-authorised batch M3.1–M3.5)
- **Status:** M3.1 REVIEW_READY; M3 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m3`
- **Commit:** the commit that introduces this entry.
- **Added — `domain.forward_model_manifest`** (schema `auto-id/forward-model/v1`):
  - **Contents:** the pinned reference INP (store + relative path, SHA-256, size), the
    passport (path + canonical hash), job prefix, material role and accepted source
    Engineering Constants, parameterisation, eigenvalue request, registration, and
    provenance.
  - **Parameterisation registry:** `carbon-property-set/v1`, with E1, E2 and G12
    variable and E3, ν12, ν13, ν23, G13, G23 fixed. There is no E1 ≠ E2 entry.
  - **Refused:**
    - unknown fields;
    - machine paths;
    - a bad job prefix;
    - an unknown parameterisation or role;
    - source fixed constants that differ from the property set;
    - eigenvalue counts of 6 or fewer.
  - **`bind_forward_model`:** pins the passport by hash and resolves the material name
    from the passport `materials` by role (SPEC §4). For a linked fixture it requires
    the model input, registration and FE model name to agree.
- **Added — `services.forward_builder.locate_engineering_constants`:** locates the
  named material's unique nine-value `*Elastic, type=ENGINEERING CONSTANTS` record.
  It refuses missing or duplicate materials, several or zero `*Elastic` options, other
  types and temperature-dependent or unreadable records. INP splitting and joining is
  lossless (latin-1, line endings kept).
- **Added — data:** `docs/auto_id/forward_models/{SP02,SP13}.forward.json` and
  `README.md`. They hold the values the accepted builder hard-coded, now bound to the
  passports and the M0.2 fixture records.
- **Checked on the real reference INPs** (read-only; no Abaqus): the located records
  are 0-based lines 2077229–2077230 (SP02) and 1957764–1957765 (SP13). The CARBON-4C
  archive records these as 1-based lines 2077230–2077231 and 1957765–1957766.
- **Governance:** the ROADMAP execution rule notes the supervised-batch exception
  (CLAUDE.md / AGENTS.md).
- **Unchanged:** `src/services/shared_carbon_forward.py`, the regression oracle.
- **Tests:** `tests/m3_support.py`, `tests/test_forward_model_manifest.py`,
  `tests/test_forward_builder.py` (location): 20 ran, OK.
- **Abaqus run count:** 0

## 2026-10-04 — M3.2 — Generic candidate rewrite

- **Stage:** M3 (SUPERVISOR-authorised batch M3.1–M3.5)
- **Status:** M3.2 REVIEW_READY; M3 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m3`
- **Commit:** the commit that introduces this entry.
- **Domain (`domain.forward_model_manifest`):**
  - A `Parameterisation` maps candidate parameters to the constants they set.
    `carbon-property-set/v1` maps `E_in_plane_mpa` → E1 and E2, and `G12_mpa` → G12;
    E3, ν12, ν13, ν23, G13 and G23 are fixed. A parameterisation must determine all
    nine constants, and no constant may be both set and fixed.
  - `ForwardCandidate` and `carbon_candidate`: exactly the parameterisation's
    parameters, each finite and positive. Fixed constants are not candidate fields.
- **Service (`services.forward_builder`):**
  - `rewrite_engineering_constants` writes only the variable constants. A fixed
    constant that would change is refused.
  - `rewrite_eigenvalue_request` sets the count on the single `*Frequency` request.
  - `render_forward_input(model, candidate, source_bytes)`:
    - checks the source SHA-256/size, the source constants and the eigenvalue request
      against the manifest;
    - rewrites the record and the request;
    - **independent post-check:** same line count, changed lines limited to the record
      and the eigenvalue request, and the re-read record equal to the candidate.
  - Mesh, geometry, core, density, adhesive, ties and every other line are copied
    unchanged.
- **Oracle equivalence:** on 8 synthetic INP variants × 7 candidates, the output is
  byte-identical to the accepted builder (`shared_carbon_forward.write_forward_job_inp`).
  - **Variants:** LF, CRLF, a comment inside the record, no trailing comma, trailing
    spaces, a one-line record, an unchanged eigenvalue request, lower-case keywords.
  - **Candidates:** include awkward floats.
- **Real-data sanity check** (read-only; no Abaqus): the CARBON-4C baseline candidate
  (52000/4500) reproduces the archived generated INP SHA-256 for SP02 (`f3e59228…`)
  and SP13 (`a46d08b5…`), with the archived changed-line numbers.
- **Unchanged:** `src/services/shared_carbon_forward.py`, the regression oracle.
- **Tests:** `tests/test_forward_builder.py` + `tests/test_forward_model_manifest.py`:
  30 ran, OK (83 subtests).
- **Abaqus run count:** 0

## 2026-10-04 — M3.3 — Generic provenance and job hash

- **Stage:** M3 (SUPERVISOR-authorised batch M3.1–M3.5)
- **Status:** M3.3 REVIEW_READY; M3 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m3`
- **Commit:** the commit that introduces this entry.
- **Provenance** (`services.forward_builder.forward_job_provenance`, schema
  `auto-id/forward-job/v1`, builder `auto-id/forward-builder/v1`). It records:
  - the forward model id and manifest hash;
  - the passport hash and identities (design, physical specimen, test run);
  - the source INP name, SHA-256 and size;
  - material role, name and elastic type;
  - parameterisation, candidate and all nine constants;
  - registration hash and eigenvalue request;
  - generated INP SHA-256, size, job name and 1-based changed lines.

  It records no machine path and no timestamp.
- **Job hash:** the canonical SHA-256 of the provenance (`job_hash`).
- **Job name:** content-addressed, `<job_prefix>_<first 16 hex of the generated SHA-256>`.
  This is the accepted naming, so existing ODB names (for example
  `SP02_f3e592281bebce66`) stay valid.
- **Writing:** `prepare_forward_job` writes `<job_name>.inp` atomically. It refuses an
  existing file with different content.
- **Evaluation:** `prepare_forward_evaluation` makes one job per forward model for one
  shared candidate. Its `evaluation_hash` covers schema, parameterisation, candidate
  and each model's job hash. Duplicate forward models or job prefixes are refused.
- **Equivalence:** on the synthetic model the job name, source and generated SHA-256,
  registration hash, eigenvalue counts and constants equal the accepted builder's.
  The generic provenance schema is new by design. Reproduction of the accepted
  builder's historical provenance and evaluation hashes is checked in the M3.5
  regression.
- **Unchanged:** `src/services/shared_carbon_forward.py`, the regression oracle.
- **Tests:** `tests/test_forward_builder.py` + `tests/test_forward_model_manifest.py`:
  37 ran, OK (83 subtests).
- **Abaqus run count:** 0

## 2026-10-04 — M3.4 — No SP02/SP13/`D:\Snadwich` hard-coding in the generic forward path

- **Stage:** M3 (SUPERVISOR-authorised batch M3.1–M3.5)
- **Status:** M3.4 REVIEW_READY; M3 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m3`
- **Commit:** the commit that introduces this entry.
- **Manifest-driven inputs (`services.forward_builder`):**
  - `load_bound_forward_model(manifest_path, repo_root, fixtures)` loads a manifest
    and its repository-relative pinned passport, then binds them.
  - `read_reference_input(model, roots)` reads the reference INP only from its
    configured store (`AUTO_ID_FIXTURE_ROOT_<STORE>`). It refuses an unconfigured
    store, a missing file or a size mismatch. The SHA-256 is verified on the bytes
    used.
  - `prepare_forward_jobs(models, candidate, roots, output_directory)` takes explicit
    forward models only; there are no default specimens.
- **Where the old hard-coded values now live:**

  | Accepted builder | Generic path |
  |---|---|
  | `sp02_forward_baseline` / `sp13_forward_baseline` | `docs/auto_id/forward_models/{SP02,SP13}.forward.json` |
  | `D:\Snadwich\…` source paths | store + relative path |
  | `_SP0x_SOURCE_INP_SHA256` | pinned `model_input` |
  | material names | passport `materials.face` |
  | eigenvalue counts | manifest `frequency_request` |
  | `SP0x_REGISTRATION_HASH` | manifest `registration`, cross-checked with the fixture |

- **Guard tests** (`tests/test_forward_builder_generic.py`):
  - The generic modules contain no specimen, material, store or machine-path literal
    and do not import the legacy builder.
  - No builder entry point has a default.
  - The accepted manifests hold no machine path.
  - A never-seen third specimen (another store, material, prefix and eigenvalue
    request) builds from manifest + store alone.
- **Scope:**
  - The accepted builder `src/services/shared_carbon_forward.py` keeps its hard-coded
    values unchanged as the M3.5 regression oracle; it is not on the generic path.
  - Historical SP13 evidence viewers (`sp13_evidence_adapter.py`,
    `material_identification_*`) and the older `family_residual_service.py` are not
    forward-builder code and are unchanged.
- **Tests:** M3 suites 44 ran, OK (121 subtests).
- **Abaqus run count:** 0

## 2026-10-04 — M3.5 — Byte-for-byte regression; M3 stage REVIEW_READY

- **Stage:** M3 (SUPERVISOR-authorised batch M3.1–M3.5)
- **Status:**
  - M3.1–M3.5 REVIEW_READY.
  - M3 stage REVIEW_READY.
  - Not accepted by the worker.
  - M4 not started.
- **Branch:** `auto-id/m3`
- **Commit:** the commit that introduces this entry.
- **Regression anchors** (`docs/auto_id/forward_models/accepted_forward_jobs.json`):
  - **Contents:** the 5 accepted CARBON-4C / CARBON-5A candidates (52000/4500,
    49400/4500, 54600/4500, 52000/4275, 52000/4725 MPa) with, per specimen, the
    archived generated INP SHA-256, the accepted provenance hash, the 1-based changed
    lines and the evaluation hash.
  - **Source:** `carbon-project-archive:carbon4c/step1_prepare.json` and
    `carbon5a/prepare.json`, pinned by SHA-256.
- **Stage gate** (`tests/test_m3_stage_gate.py`, real data, store `snadwich`;
  skipped without it). For every archived candidate × SP02/SP13:
  - the universal builder's bytes are identical to the live accepted builder
    (`shared_carbon_forward.write_forward_job_inp`, unchanged since `121ba1d`) on the
    same pinned reference INP;
  - the generated SHA-256 and the changed-line numbers equal the archive;
  - the job name equals the accepted name (the archived ODB names);
  - the accepted `shared-carbon-forward-job/1` provenance hash and the evaluation hash,
    rebuilt from the generic provenance, equal both the archive and the live builder.

  End-to-end `prepare_forward_jobs` writes the archived baseline files and names
  deterministically.
- **Result:** **PASS** — 10/10 archived jobs byte-identical; 17 subtests OK.
- **Extended check (one-off, read-only):** 12 further candidates × 2 specimens gave
  24 / 24 byte-identical files. The candidates include awkward floats, 45000/4000,
  100000/1000 and 1234.5678/9.875.
- **Physics:** unchanged. The only changed lines are the carbon E1/E2/G12 record and,
  for SP02, the accepted eigenvalue request 15 → 30. There is no INP metadata
  difference.
- **EVIDENCE.md:** new entry "M3 — Universal forward builder byte-for-byte
  regression", PENDING SUPERVISOR REVIEW.
- **Unchanged:** `src/services/shared_carbon_forward.py` (oracle), SPEC, DECISIONS,
  the M0.2 fixture manifest, passports and registrations.
- **Tests (Windows, Python 3.14.6):**
  - **Full suite with stores:** 1136 ran; 1134 passed, 0 failures, 0 errors, 2 skipped
    (opt-in Abaqus).
  - **Full suite without stores:** 1134 ran; 1125 passed, 0 failures. Skipped: the
    M3 gate class, the 2 Abaqus tests and 14 real-data subtests.
  - **Linux CI:** recorded with the stage PR.
- **Abaqus run count:** 0
- **Next gate:** SUPERVISOR review of the M3 batch (stage PR `auto-id/m3` → `main`).

## 2026-10-04 — M3 — Linux CI recorded; stage PR

- **Stage:** M3 (REVIEW_READY; not accepted by the worker; M4 not started)
- **Linux CI** on `3d86251` (ubuntu-latest, Python 3.11, run 37178115819): success.
  - 1131 ran, OK, skipped=21.
  - Skips: 14 data-store subtests, the M3 gate class (no `snadwich` store on CI),
    2 opt-in Abaqus tests and 4 headless-Tk tests.
- **Stage PR:** `auto-id/m3` → `main`. Not merged; merge only under HUMAN
  authorisation.
- **Abaqus run count:** 0

## 2026-10-04 — M3 accepted and merged to main; M4 not started

- **Stage:** M3 → (M4 NOT_STARTED)
- **M3 acceptance:**
  - M3.1–M3.5 and the M3 stage are ACCEPTED by the SUPERVISOR after review.
  - Accepted head: `febfa5b`. Last implementation commit: `3d86251`.
- **M3 merge:** PR #29 (`auto-id/m3` → `main`), merge commit `0fd63d69a78f251bd51721880bae9b425b98951e`.
  - The HUMAN supervisor explicitly authorised it; it used the normal merge-commit
    method.
  - Recorded in `STATUS.json` (`main_merges`, `m3.merged_to_main`,
    `last_accepted_stage = M3`) and in the ROADMAP.
- **M3 conclusions (unchanged):**
  - byte-for-byte regression against the accepted shared-carbon builder PASS;
  - no physics change;
  - the generic forward path has no SP02/SP13/`D:\Snadwich` literals;
  - `shared_carbon_forward.py` stays as the regression oracle.
- **EVIDENCE.md:** "M3 — Universal forward builder byte-for-byte regression" moves
  from PENDING SUPERVISOR REVIEW to ACCEPTED.
- **M4:** NOT_STARTED; M4.1–M4.9 are `TODO`. No M4 work has been done.
- **Bookkeeping branch:** `auto-id/m3-closure`, created from exactly `0fd63d69a78f251bd51721880bae9b425b98951e`.
- **Code / scientific logic changed:** none.
- **Abaqus run count:** 0

## 2026-10-04 — M4.1 — IdentificationPairingPolicy

- **Stage:** M4, first development batch (SUPERVISOR-authorised: M4.1–M4.5, M4.7,
  M4.8; no Abaqus; M4.6 and M4.9 not authorised)
- **Status:** M4.1 REVIEW_READY; M4 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m4`, created from `main` `6185b05`.
- **Commit:** the commit that introduces this entry.
- **Added — `domain.identification_pairing_policy`:**
  - `IdentificationPairingPolicy` is immutable and hashed (`policy_hash`); its schema
    is `auto-id/identification-pairing-policy/v1`.
  - **`STRICT_IDENTIFICATION_PAIRING`** (SPEC §12.1):
    - MAC ≥ 0.80;
    - |Δf|/f_EXP ≤ 15 %;
    - FE-to-FE tracking MAC ≥ 0.90;
    - coverage ≥ 2 rows, the number of free parameters of carbon-property-set/v1;
    - assignment tie tolerance 1e-9.
  - `is_strict` and `require_strict()` reject weaker policies.
- **Added — `services.identification_pairing.pair_baseline(policy, experimental, fe, mac)`:**
  - The policy is a required argument.
  - The gates (MAC, frequency) are applied to every pair **before** the assignment.
  - The assignment is Hungarian: maximum number of pairs first, then maximum total MAC.
  - **Status:**
    - `AMBIGUOUS` when the optimal assignment is not unique within the tie tolerance;
    - `INCOMPLETE_EVIDENCE` when a frequency-admissible MAC entry is unknown (NaN);
    - `INSUFFICIENT_COVERAGE` when there are fewer pairs than the policy requires;
    - otherwise `COMPLETE`. Only `COMPLETE` is final.
  - Each unpaired experimental mode carries a reason.
- **Unchanged:**
  - the normal comparator and its defaults;
  - the Stage-A pairing provider (MAC ≥ 0.50);
  - `inverse_solver`;
  - all M3 contracts.
- **Added — `tests/test_m4_generic_guard.py`:** for every new M4 module, no specimen,
  material or machine-path literal, and no import of `subprocess`, `abaqus_bridge`,
  `matrix_model_service`, `forward_builder`, `shared_carbon_forward` or `modal_core`.
- **Tests:** `tests/test_identification_pairing.py` +
  `tests/test_m4_generic_guard.py`: 15 ran, OK.
- **Abaqus run count:** 0

## 2026-10-04 — M4.2 — Baseline observation / pair freeze

- **Stage:** M4 first development batch
- **Status:** M4.2 REVIEW_READY; M4 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Added — `domain.frozen_observations`** (schema `auto-id/frozen-observations/v1`):
  - **`BaselineIdentity`** records content identities only: forward model, M3 job name
    and generated INP SHA-256, FE geometry, registration, experimental source, modal
    set, measured DOFs and evidence source.
  - **`FrozenObservationSet`:**
    - status `FROZEN` / `NOT_FROZEN` with reasons;
    - rows (`R1…`), only when FROZEN;
    - provisional rows, for review;
    - excluded modes with reasons;
    - unknown MAC entries;
    - `observation_hash`.
  - **`require_frozen()`** raises `ObservationFreezeRefusal`, which is not a
    ValueError/RuntimeError.
- **Added — `services.baseline_freeze`:**
  - `BaselineEvidence` carries the experimental modes, the M1
    `ExperimentalModeEligibility`, the elastic FE modes, and a MAC matrix with NaN for
    unknown entries.
  - `freeze_baseline(evidence, policy)` requires a strict policy.
  - Modes that M1 eligibility excludes never enter, even with a perfect match. FE
    frequencies never select experimental modes.
  - The set is FROZEN only when the M4.1 pairing is COMPLETE.
- **Added — `services.archived_baseline`** and
  `docs/auto_id/baselines/{SP02,SP13}.carbon4c-baseline.json` + `README.md` (the
  approved replay source).
  - **Sources:** the archived CARBON-4C post-solve records and ODBs (pinned by
    SHA-256), the M3 baseline generated INP SHA-256 and job name, and the M1 production
    mode frequencies.
  - **Record hash:** canonical, independent of key order and line endings.
  - **Not run:** no Abaqus, no Abaqus Python.
- **Finding — archived replay is not final:**
  - The FE mode shapes are not archived. Only the recorded MACs exist: the
    accepted-comparator pairs and the best candidate of each rejected mode.
  - Under the strict policy both baselines are **NOT_FROZEN (INCOMPLETE_EVIDENCE)**.
    - SP02: 17 unknown frequency-admissible entries; provisional pair exp 2 ↔ FE 8;
      below coverage.
    - SP13: 28 unknown entries; provisional pairs 4↔10 and 5↔11.
  - A final freeze needs FE shapes from the archived ODBs, i.e. Abaqus Python, which
    needs a separate HUMAN gate.
- **Tests:** `tests/test_baseline_freeze.py`:
  - synthetic freeze behaviour;
  - record identity links to M0–M3 (no store needed);
  - store-gated agreement with the archive and the M1 modal input;
  - the M4 guard extended.

  M4 suites: 27 ran, OK.
- **Unchanged:** M3 contracts (`shared_carbon_forward.py`, `forward_builder.py`,
  manifests), the normal comparator and Stage-A pairing.
- **Abaqus run count:** 0

## 2026-10-04 — M4.3 — Physical modal-family classifier and family holdouts

- **Stage:** M4 first development batch
- **Status:** M4.3 REVIEW_READY; M4 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Added — `services.modal_family_classifier`** (SPEC §12.2):
  - `classify_surface_mode(coordinates, values, policy)` works on outer-surface FE
    shapes: in-plane (x, y) and the out-of-plane component.
  - **Parities:** continuous P_x = φᵀR_xφ/φᵀφ and P_y about the mid-lines, using
    nearest-mirror-node mapping in normalised coordinates.
  - **Near-square panels:** diagonal and antidiagonal parities as well.
  - **Nodal lines:** counted as median sign changes along the rows and columns of a
    resampling grid.
  - **Family key:** parities plus nodal-line counts. Torsion-dominated means odd-odd.
  - **Refused:** a mesh that is not symmetric enough (mirror coverage below the
    policy), and degenerate input.
- **`FamilyClassifierPolicy`:**
  - SPEC §12.2 gives no numbers, so the thresholds are explicit, hashed and marked
    **provisional**: `auto-id/modal-family/v1-provisional`.
  - **Values:** parity threshold 0.80, mirror tolerance 2 % of min(Lx, Ly), mirror
    coverage ≥ 95 %, near-square ≤ 5 %, 41 × 41 nodal grid, amplitude floor 5 %.
  - The policy hash is recorded in every `ModeFamily`.
- **Added — `select_holdouts(rows, k_int_enabled)`** (SPEC §12.3, D-010):
  - **Torsion holdout:** the lowest torsion-dominated (≈ odd-odd) family, when k_int
    is not enabled.
  - **Validation holdout:** the highest accepted family.
  - Every row of a held-out family is held out.
  - Order is by experimental frequency, never by FE mode number.
- **Real shapes:** not available in this batch (FE shapes are not archived;
  extraction needs the HUMAN gate). Tests use analytic plate shapes:
  - odd-odd torsion, even-even bending, odd-even, even-odd and mixed shapes;
  - shuffled node order and a jittered mesh;
  - near-square versus rectangular panels;
  - a non-symmetric mesh.
- **Tests:** `tests/test_modal_family_classifier.py`: 11 ran, OK. M4 guard extended.
- **Unchanged:** M3 contracts and the existing comparator, cluster and Stage-A
  services.
- **Abaqus run count:** 0

## 2026-10-04 — M4.4 — Cluster trigger and principal-angle confirmation

- **Stage:** M4 first development batch
- **Status:** M4.4 REVIEW_READY; M4 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Added — `services.identification_clusters`** (SPEC §12.4, D-009):
  - **`cluster_triggers(rows)`:** |Δf|/f < 3 % in experimental **or** FE frequency is
    only a trigger. Rows that link transitively form one group.
  - **`confirm_cluster(row_ids, baseline_shapes, perturbed_shapes, weights)`:**
    - Requires all directions of carbon v1: E_in_plane ± 5 % and G12 ± 5 %.
    - **CONFIRMED** when individual identity is unstable (best FE-to-FE MAC < 0.9, or
      no unique counterpart) in at least one direction, **and** the 2-mode subspace is
      stable (both principal-angle cos² > 0.95) and uniquely identified in **every**
      direction.
    - **INDEPENDENT** when identity is stable everywhere: two observations.
    - **UNSTABLE** when the subspace is unstable or ambiguous: a refusal.
    - **UNSUPPORTED** for groups of more than two modes: reported, not confirmed.
    - Optional mass weighting.
  - **`cluster_log_residual(fe_hz, experimental_hz)`:** r_C = (1/n_C)·Σ ln(f_FE/f_EXP),
    independent of the pairing of members. A confirmed cluster is one residual, never
    two independent observations.
- **Thresholds:** 3 %, 0.95 and 0.9 are the SPEC values, as named constants. The
  directions follow carbon v1. k_core directions are outside M4 (no new
  parameterisation; M3 contracts unchanged).
- **Real shapes:** not available in this batch. The ±5 % CARBON-5A ODBs are archived,
  but extracting shapes is Abaqus Python, which needs the HUMAN gate. Tests use
  synthetic orthonormal shapes:
  - a rotating pair confirms;
  - a close but distinct pair stays two observations;
  - a single unstable direction is enough;
  - subspace leakage or ambiguity is refused;
  - 3-mode groups are unsupported;
  - weighting is applied;
  - the residual is assignment-invariant.
- **Tests:** `tests/test_identification_clusters.py`: 13 ran, OK. M4 guard extended.
- **Unchanged:** `modal_cluster_service.py`, `family_residual_service.py` (not
  imported), and the M3 contracts.
- **Abaqus run count:** 0

## 2026-10-04 — M4.5 — FE-to-FE branch tracker

- **Stage:** M4 first development batch
- **Status:** M4.5 REVIEW_READY; M4 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Added — `services.branch_tracker`** (SPEC §12.1, D-008, AUDIT V4):
  - `FEModalState` holds the modes of one solved state on one node/DOF set, with the
    FE geometry and node-set identities.
  - `track_branches(policy, reference, candidate, rows, clusters, weights)`:
    - follows each frozen row (row → reference FE mode) by **FE-to-FE MAC only**;
    - requires MAC ≥ the policy's `tracking_minimum_mac` (0.90) and a unique
      assignment;
    - follows confirmed 2-mode clusters as a subspace (exactly one candidate pair with
      both cos² > 0.95);
    - optional mass weighting.
  - **Refusals** (`BranchTrackingRefusal`, which is not a ValueError/RuntimeError):
    - `BRANCH_LOSS`: no candidate reaches 0.90;
    - `AMBIGUOUS`: several candidates reach 0.90 for one branch;
    - `BRANCH_EXCHANGE`: one candidate is claimed by several branches;
    - `CLUSTER_LOSS`: no unique candidate pair spans the cluster subspace.
  - Rows are never added or dropped. Experimental data are not an input (checked by
    signature), so the normal comparator never re-pairs.
  - A frequency-order change with stable shapes is tracked correctly and recorded
    (`order_changes`) as evidence.
  - States on different FE geometry or node sets are refused.
- **M4 gate element (tested here on synthetic shapes):** an artificial branch exchange
  — two tracked modes exchanging character (45° mixing) between iterations — gives a
  refusal, not silent re-pairing.
- **Tests:** `tests/test_branch_tracker.py`: 11 ran, OK. M4 guard extended.
- **Unchanged:** `inverse_solver.py` (Stage-A tracking), the comparator, and the M3
  contracts.
- **Abaqus run count:** 0

## 2026-10-04 — M4.7 — Log-frequency objective

- **Stage:** M4 first development batch (M4.6 not authorised; skipped by SUPERVISOR
  decision)
- **Status:** M4.7 REVIEW_READY; M4 stage IN_PROGRESS. Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Added — `services.identification_objective`** (SPEC §7, §8, §12.3–12.4):
  - **Residuals:** r_i = (ln f_FE − ln f_EXP)/σ_i for frozen fit rows. Each confirmed
    cluster is **one** term, r_C = mean ln(f_FE/f_EXP), with σ_C = √(Σσ_i²)/n_C.
  - **Objective:** Φ = ½‖r‖² over fit terms only. Notation follows SPEC §8: the
    objective is never named like the Jacobian.
  - **Inputs:** FE frequencies come only from FE-to-FE tracking (M4.5). MAC is not an
    input; it never enters Φ.
  - **Holdouts:** holdout rows and clusters are evaluated and reported, never part of
    Φ.
  - **`RowSigma`:** σ² = σ_meas² + σ_setup², explicit per row, never defaulted.
    `PROVISIONAL_SETUP_SD` (0.3 %, SPEC §7) is a named constant. It must be passed
    explicitly and is flagged (`provisional_uncertainty`).
  - **`build_objective_design`** requires a FROZEN set and refuses:
    - missing σ;
    - an unconfirmed or split cluster;
    - unknown holdout rows;
    - fewer fit terms than parameters.
  - **`evaluate_objective`** refuses tracking that does not cover exactly the design's
    rows and clusters.
- **Tests:** `tests/test_identification_objective.py`: 6 ran, OK.
  - residuals and Φ computed by hand;
  - a cluster is one term;
  - holdouts are excluded from Φ;
  - Φ does not change with tracking MAC;
  - refusals.

  M4 guard extended.
- **Abaqus run count:** 0

## 2026-10-04 — M4.8 — Bounded LM / trust step; first M4 development batch REVIEW_READY

- **Stage:** M4 first development batch
- **Status:**
  - M4.8 REVIEW_READY.
  - The batch M4.1–M4.5, M4.7 and M4.8 is REVIEW_READY.
  - The M4 stage remains IN_PROGRESS: M4.6 and M4.9 are `TODO` and not authorised.
  - Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Added — `services.identification_step`** (SPEC §6 S4, §8):
  - **Step:** `lm_step` computes Δx = −(J_rᵀJ_r + μ·diag(J_rᵀJ_r))⁻¹J_rᵀr in x = ln p
    (minus sign tested). A parameter without sensitivity is refused.
  - **`run_bounded_lm(evaluate, start, bounds, settings)`:**
    - one call of the caller's residual function is one authorised solve;
    - the Jacobian comes from central finite differences at exactly p·(1 ± 0.05),
      2·n_p solves (for p0 these are the CARBON-5A E± / G± candidates), then Broyden
      updates;
    - finite differences are repeated only after a step failure;
    - steps are projected onto the physical bounds;
    - a step is accepted only if Φ actually decreases; otherwise μ ← 10μ.
  - **Stop rules:**
    - `CONVERGED` when max|Δx_j| < 0.2·sd_j, with local sd from (JᵀJ)⁻¹;
    - `MAX_ITERATIONS` after 5 iterations;
    - `REFUSED` on `BranchTrackingRefusal` or `ObservationFreezeRefusal`: no further
      solves, no re-pairing;
    - `STEP_REJECTED`;
    - `SOLVE_BUDGET`.
  - **Exact physical values:** physical parameter values are the source of truth.
    Solves get p0 and the ±5 % points exactly, never exp(ln p), so candidate INPs keep
    their accepted M3 identities.
  - **Settings:** the SPEC values are defaults (5 iterations, 0.2·sd, μ × 10, ±5 %).
    μ₀, μ decrease, step attempts and the solve budget have no SPEC value and must be
    given explicitly.
- **Tests:** `tests/test_identification_step.py`, analytic log-linear models only (no
  solver):
  - synthetic recovery from 52000/4500 to 45000/4000 with 0.3 % noise, within the
    local 1σ in ≤ 20 evaluations;
  - exact finite-difference points;
  - a rejected step gives μ × 10 and a Jacobian refresh after a Broyden update;
  - Φ never increases;
  - refusal propagation;
  - budget and iteration stops;
  - validation.

  13 ran, OK. M4 guard extended.
- **Batch verification (Windows, Python 3.14.6):**
  - **Full suite with stores:** 1217 ran; 1215 passed, 0 failures, 2 skipped (opt-in
    Abaqus).
  - **Full suite without stores:** 1215 ran; 1205 passed, 0 failures. Skipped: the M3
    gate class, the M4.2 store test, 2 Abaqus tests and 14 real-data subtests.
  - **Linux CI:** recorded after push.
- **Batch findings for review:**
  - The archived CARBON-4C baseline cannot be strictly frozen (M4.2): FE shapes are
    not archived, so both baselines are NOT_FROZEN (INCOMPLETE_EVIDENCE).
  - The thresholds of the M4.3 family classifier are provisional; SPEC §12.2 gives
    none.
- **Not done (by instruction):** M4.6 (solve pipeline), M4.9 (digital twin), any
  Abaqus or Abaqus Python run.
- **Unchanged:** the M3 contracts (`shared_carbon_forward.py`, `forward_builder.py`,
  manifests, INP generation), the comparator, Stage-A services and `inverse_solver`.
- **Abaqus run count:** 0

## 2026-10-04 — M4 first batch — Linux CI test fix (M4.3 test only)

- **Linux CI** on `4ad6379` (run 37182692754) reported one failure:
  `test_modal_family_classifier.ParityTests.test_independent_of_node_order_and_mild_mesh_irregularity`.
  - **Cause:** under node reordering the summation order changes, so P_x came out as
    −1.0000000000000002 on Linux and −1.0 on Windows. The test compared the whole
    result exactly, floats included.
  - **Unchanged:** the family key, parities and nodal-line counts.
- **Fix (test only):** classification fields are compared exactly, and the parity
  scores to 1e-12. No change to `services.modal_family_classifier`.
- **Abaqus run count:** 0

## 2026-10-04 — M4 first batch — verification recorded

- **Linux CI** on `a322484` (ubuntu-latest, Python 3.11, run 37182809657): success.
  - 1212 ran, OK, skipped=22.
  - Skips: 14 data-store subtests, the M3 gate class, the M4.2 store test, 2 opt-in
    Abaqus tests and 4 headless-Tk tests.
- **Windows:** full suite with stores 1217 ran, 1215 passed, 2 skipped.
- **Status:**
  - The first M4 batch (M4.1–M4.5, M4.7, M4.8) is REVIEW_READY.
  - M4.6 and M4.9 remain `TODO` and need new SUPERVISOR authorisation.
  - The M4 stage stays IN_PROGRESS.
- **Abaqus run count:** 0

## 2026-10-04 — M4 first batch — SUPERVISOR review recorded; decision record prepared

- **Stage:** M4 (IN_PROGRESS)
- **Review:**
  - M4.1, M4.3, M4.4, M4.5, M4.7 and M4.8 are acknowledged as REVIEW_READY. They are
    not ACCEPTED.
  - M4.2 is **not accepted** and is now `BLOCKED_WAITING_FOR_ODB_SHAPE_EXTRACTION`.
    The archived baseline lacks the FE mode shapes that strict frozen observation
    generation needs. Abaqus Python extraction needs a separate HUMAN gate, which has
    not been given; no extraction was run.
  - M4.6 and M4.9 have not started.
- **Added — `docs/auto_id/M4_DECISION_RECORD.md`** (PROPOSED, awaiting SUPERVISOR
  decision; not a DECISIONS.md entry). It covers:
  1. the M4.3 provisional classifier values, with rationale, risks and a proposed
     real-shape validation once extraction is authorised;
  2. the M4.8 LM hyperparameters: μ₀ = 1e-3, μ ÷ 10 after an accepted step, 3 step
     attempts per iteration, and a solve budget of 20 per specimen counting every
     evaluation. The SPEC-fixed values are unchanged. Two questions are open: whether
     the reference solve counts, and whether archived ±5 % solves can be reused;
  3. exact M4.9 acceptance requirements:
     - **prerequisites:** M4.2 unblocked, M4.6 authorised, the solve command pinned
       to the CARBON-4C/5A convention, and a HUMAN gate;
     - **twin definition:** truth, a noise seed and σ;
     - **pass criteria:** convergence within budget, 1σ recovery (with an open point
       on the weak G12 direction), branch-exchange refusal, determinism, provenance,
       and unchanged M3 contracts.
- **Code changed:** none.
- **Abaqus run count:** 0

## 2026-10-04 — M4.2 — Validated shape packs integrated; complete-MAC baseline freeze

- **Stage:** M4 (IN_PROGRESS)
- **Status:**
  - M4.2 moves from `BLOCKED_WAITING_FOR_ODB_SHAPE_EXTRACTION` to REVIEW_READY.
  - Not accepted by the worker.
  - Not started: M4.3 real validation, M4.4 real cluster confirmation, M4.6, M4.9.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **ODB shape-extraction gate** (HUMAN-authorised 2026-10-04; supervisor review PASS):
  - 6 Abaqus 2024 Python extractions (Tier A: SP02 and SP13 baselines; Tier B: SP13
    E± and G±), with the pinned, unchanged `extract_odb.py`, on SHA-verified scratch
    copies.
  - The archived ODBs are unchanged. No solver runs.
  - V1–V8 all PASS.
  - Shape packs and provenance are in `carbon-project-archive/fe_shapes/`. Raw
    extractions are temporary (`D:\abaqus_scratch_m4`, kept unchanged for now).
- **Added — `services.fe_shape_pack`:**
  - pack record parser (`auto-id/fe-shape-pack-record/v1`);
  - deterministic content hash, independent of the zip layout;
  - node-set hash, defined like the registration subset fingerprint;
  - `load_shape_pack(record, roots)`, which verifies file SHA-256, content, node set,
    modes and frequencies, and refuses any difference.
- **Added — `docs/auto_id/fe_shapes/`:** six pinned `<job>.shape-pack.json` records and
  a README. They bind to the M3 accepted-job anchors, the fixture ODB references, the
  passports' FE geometry and the registration subsets.
- **`services.archived_baseline`:**
  - `complete_mac_matrix` and `shape_pack_evidence` bind pack, baseline record,
    FrozenRegistration and M1 experimental modes by identity: job, generated INP, ODB,
    FE geometry, registration, node set, FE modes and exact frequencies.
  - The full experimental × FE MAC matrix is computed in the experimental frame on the
    measured-DOF contract (comparator formula).
  - Every archived MAC entry must be reproduced (≤ 1e-9).
  - `BaselineIdentity` gains `shape_pack_content_sha256`.
  - The M4.2 freeze logic is unchanged: with complete evidence the strict policy now
    decides.
- **M4.2 result** (strict policy, M1 eligibility, no unknown MAC entries):
  - **SP13 FROZEN:** R1 exp 4 ↔ FE 10 (MAC 0.888) and R2 exp 5 ↔ FE 11 (MAC 0.889).
    Observation hash `922888c7…`.
  - **SP02 NOT_FROZEN:** only exp 2 ↔ FE 8 (MAC 0.958) passes the strict gates, below
    the required 2.
  - **Observation:** SP13 R1/R2 are 2.2 % apart, which would trigger the M4.4 cluster
    check. Real cluster confirmation is not started.
- **Tests:**
  - `tests/test_fe_shape_pack.py`: hash, loader, refusals, pinned records; store-gated
    load of all six packs.
  - `tests/test_baseline_freeze.py`: synthetic complete-matrix binding and refusals;
    store-gated real freeze of SP02/SP13.
  - The M4 guard covers `fe_shape_pack.py`.
- **Unchanged:**
  - the M3 contracts (`shared_carbon_forward.py`, `forward_builder.py`, manifests);
  - the M4.1 policy, the freeze algorithm, and the v1 baseline records;
  - SPEC and DECISIONS.
- **Abaqus run count in this step:** 0. The extraction gate's 6 Abaqus Python runs are
  recorded above.

## 2026-10-04 — M4.2 — SUPERVISOR review note recorded

- **Stage:** M4 (IN_PROGRESS)
- **Review of the M4.2 shape-pack integration:** result acknowledged. M4.2 stays
  **REVIEW_READY**, not ACCEPTED.
  - M4.2 is **unblocked**: complete MAC evidence for SP13 is available.
  - **SP13** is the **candidate frozen observation set**: R1 exp 4 ↔ FE 10, R2 exp 5 ↔
    FE 11 (observation hash `922888c7…`).
  - **SP02** remains **NOT_FROZEN** and is **excluded from identification**. The strict
    policy requires at least 2 valid observation rows; SP02 has 1.
- **Unchanged:** freeze criteria and MAC/frequency thresholds.
- **Not started:** M4.3 real validation, M4.4 real cluster confirmation, M4.6, M4.9.
- **Code changed:** none.
- **Abaqus run count:** 0

## 2026-10-04 — M4.3 — Real validation of the modal-family classifier on SP13 shapes

- **Stage:** M4 (IN_PROGRESS); SUPERVISOR-authorised M4.3 real validation only
- **Status:** M4.3 REVIEW_READY. Not accepted by the worker. Thresholds unchanged and
  still **PROVISIONAL**.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Input:**
  - the validated SP13 baseline shape pack `SP13_a46d08b52995e078` (content
    `7941545b…`): measured outer surface, 29 754 nodes, U3 out-of-plane;
  - the M4.2 candidate frozen set (observation hash `922888c7…`).
- **Added — `services.modal_family_classifier`:** the reporting helpers
  `mirror_coverage` and `classify_shape_pack_modes`. Classification logic and policy
  values are unchanged.
- **Added — `docs/auto_id/fe_shapes/SP13_a46d08b52995e078.families.json`** (schema
  `auto-id/modal-family-classification/v1`, PENDING SUPERVISOR REVIEW): parity scores,
  nodal-line counts and family keys for modes 7–30, the frozen-row families and the
  holdout selection.
- **Results:**
  - **Coverage:** mirror coverage is 1.0 for x, y, diagonal and antidiagonal. The panel
    is 510 × 520 mm (near-square 1.9 %), so diagonal parities are computed. No refusal.
  - **All 24 modes classified.** The parity and nodal-line parity are consistent for
    every mode (odd parity ↔ odd nodal count).
  - **Lowest torsion-dominated (odd-odd) family:** FE 7 (22.49 Hz), `Px:O|Py:O|nx:1|ny:1`.
  - **Frozen rows:**
    - R1 = FE 10 (85.85 Hz): `Px:O|Py:E|nx:1|ny:2` (P_x −1.000, P_y +1.000);
    - R2 = FE 11 (87.77 Hz): `Px:E|Py:O|nx:2|ny:1` (P_x +1.000, P_y −1.000).

    They are the odd-even / even-odd counterpart families of the near-square panel.
  - **Holdout selection (k_int not enabled) behaves as defined:**
    - no torsion-family holdout, because no odd-odd family is among the frozen rows;
    - the validation holdout is the highest accepted family, R2;
    - one fit row remains (R1), fewer than the 2 parameters. M4.7 would refuse this
      objective design.
- **Tests:** `tests/test_m4_3_real_classification.py`:
  - unit tests for the helpers;
  - record checks without a store;
  - a store-gated recomputation from the pack.

  The M4.3 and M4 guard suites pass.
- **Not started:** M4.4, M4.6, M4.9. M4.2 freeze criteria are unchanged.
- **Abaqus run count:** 0

## 2026-10-04 — M4.4 — Real cluster confirmation of SP13 R1/R2: INDEPENDENT

- **Stage:** M4 (IN_PROGRESS); SUPERVISOR-authorised M4.4 real confirmation only
- **Status:** M4.4 REVIEW_READY. Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Input:**
  - the validated SP13 shape packs: baseline, plus the CARBON-5A ±5 % E_in_plane and
    G12 states;
  - the M4.2 frozen candidate rows R1 (exp 4 ↔ FE 10) and R2 (exp 5 ↔ FE 11);
  - the M4.3 families: R1 `Px:O|Py:E|nx:1|ny:2`, R2 `Px:E|Py:O|nx:2|ny:1`.
- **Method:** `services.identification_clusters` unchanged, with the approved criteria
  only:
  - |Δf|/f < 3 % is a trigger only;
  - CONFIRMED only if individual identity is unstable (FE-to-FE MAC < 0.9, or no
    unique counterpart) in at least one direction, while the 2-mode subspace is stable
    (both cos² > 0.95) and unique in every direction.
  - All 24 perturbed modes were candidates; there was no preselection.
- **Basis:** primary, the full outer-surface U1–U3 vectors; sensitivity check, U3 only.
- **Result:**
  - **Trigger fired:** experimental spacing 2.25 %, FE spacing 2.24 %.
  - **Decision: INDEPENDENT.** In each of E+, E−, G12+, G12−:
    - each branch has exactly one counterpart ≥ 0.9 (FE 10 → 10, FE 11 → 11) with
      MAC 0.999998;
    - the cross-MAC to the other branch is ≈ 0;
    - subspace cos² is 0.999998.

    The same decision holds on the U3 basis.
  - Perturbed frequencies move as expected (FE 10: 84.27 Hz at E−, 87.40 Hz at E+).
- **Interpretation:** R1 (odd-even) and R2 (even-odd) are different symmetry classes;
  the symmetric E/G12 perturbations do not mix them. R1 and R2 stay **two independent
  observations**; no cluster residual applies.
- **Added:**
  - `docs/auto_id/fe_shapes/SP13.R1-R2.cluster.json` (schema
    `auto-id/cluster-confirmation/v1`, PENDING SUPERVISOR REVIEW);
  - `tests/test_m4_4_real_cluster.py`: record checks, plus a store-gated recomputation.
- **Unchanged:** cluster thresholds, M4.2 freeze criteria, the M4.3 provisional policy,
  and the M3 contracts. M4.6 and M4.9 not started.
- **Abaqus run count:** 0. The existing gate shape packs were enough.

## 2026-10-04 — M4.4 — SUPERVISOR review note recorded

- **Stage:** M4 (IN_PROGRESS)
- **Review of M4.4:** M4.4 stays **REVIEW_READY**, not ACCEPTED.
  - R1/R2 are confirmed **independent branches, not a cluster**.
  - No cluster residual merging applies.
  - **Unresolved:** the M4.3 holdout consequence. The current holdout selection (no
    torsion holdout; validation holdout R2) leaves one fit row (R1) for two parameters.
- **Unchanged:** cluster criteria, M4.3 thresholds, M4.2 freeze criteria.
- **Not started:** M4.6, M4.9.
- **Code changed:** none.
- **Abaqus run count:** 0

## 2026-10-04 — M4.6 — Resumable identification pipeline (architecture, fake solver)

- **Stage:** M4 (IN_PROGRESS); SUPERVISOR-authorised M4.6 only
- **Status:** M4.6 REVIEW_READY. Not accepted by the worker.
- **Branch:** `auto-id/m4`
- **Commit:** the commit that introduces this entry.
- **Scope** (M4_DECISION_RECORD.md §6): architecture and fake-solver tests only. No real
  Abaqus, no Abaqus Python, no M4.9.
- **Added — `domain.identification_run`:**
  - `SolverProfile` (schema `auto-id/solver-profile/v1`): separate data with an exact
    template, no machine paths, and a profile hash that excludes provenance.
  - `RunJournal`: atomic (`.partial` + replace), append-only, SHA-256 hash-chained, and
    bound to the run identity; a broken chain or another run's identity is refused.
  - `RunLock`: one writer per run directory.
- **Added — `services.forward_solver`:**
  - the only M4 module importing `subprocess`;
  - renders the pinned profile command;
  - verifies the M3 INP SHA before solving;
  - accepts a solve only with the `.sta` completion marker, the `.dat` version marker
    and an ODB, identified by SHA-256 and size;
  - `SolveFailure` with no automatic retry;
  - `verify_solve` re-checks the content on reuse;
  - the executor is injectable (real `subprocess` only under a HUMAN gate).
- **Added — `services.shape_extraction`:**
  - the gate's validated pack build in the repository: format 2 from the pinned,
    unchanged `extract_odb.py` (SHA `039aa067…`);
  - checks: modes and history, finite and real values, FE geometry identity, exact
    EIGFREQ frequencies, node set = expected registration subset, lossless storage, and
    the content hash stable on reload;
  - the extraction identity is content-only;
  - raw extraction is deleted after validation (retention rule);
  - the real executor uses `abaqus_bridge.run_abaqus_extraction` only as an execution
    helper (no `abaqus_bridge` cache); no new extractor.
- **Added — `services.identification_pipeline`:** the M4.8 residual function, chaining
  candidate → M3 `prepare_forward_job` → validated archived pack, journalled solve or
  new solve → validated pack → FE state → FE-to-FE tracking (M4.5) → objective (M4.7).
  - **Run hash** binds: forward model and passport, solver profile, frozen set,
    objective design, pairing policy, LM settings, bounds, start, extraction expectation,
    archived packs and extra identity.
  - **Journal:** each evaluation is journalled once and replayed on resume (refusals
    included). Identification evaluations (reused and new) and actual Abaqus solves are
    counted separately; reused archived evaluations count toward the budget.
  - **Identity checks:** the start point's M3 job must equal the frozen baseline job;
    the pack must match job, FE geometry, node set and modes.
- **Added — `docs/auto_id/solver_profiles/{SP02,SP13}.json` + README:** the archived
  CARBON-4C/5A convention (SP02 cpus 8 with a scratch store; SP13 cpus 1).
- **Fake-solver results** (`tests/test_identification_pipeline.py`, `tests/m4_6_support.py`):
  - **End to end:** from 52000/4500 to 45006/4000.2 (truth 45000/4000), CONVERGED in 6
    evaluations (p0, 4 finite differences, 1 trial). Each INP is byte-identical to the M3
    rendering.
  - **Determinism:** identical run hash, evaluation hashes and result across run roots.
  - **Resume:**
    - after an interruption (crash after 3 solves), every job is solved exactly once
      across sessions;
    - after completion, all evaluations are replayed with 0 solves;
    - after an interrupted extraction, the journalled solve is reused.
  - **Content identity:** a tampered ODB (same mtime) and a tampered pack are refused.
  - **Reuse:** with archived p0 and ±5 % packs, 5 evaluations are reused, and
    solves = evaluations − 5.
  - **Budget:** reused evaluations count toward it (budget 5 → SOLVE_BUDGET with 0
    solves).
  - **Refusals:**
    - a branch exchange gives REFUSED, no further solves, and REFUSED again on resume
      with 0 solves;
    - a failed solve gives SolveFailure, no journal entry and the lock released;
    - configuration identity mismatches are refused.
  - **Profiles:** the accepted profiles render the archived command exactly.
- **M4 guard (allow-list):**
  - `subprocess` only in `forward_solver.py`;
  - `abaqus_bridge.run_abaqus_extraction` only in `shape_extraction.py`;
  - `forward_builder` only in the pipeline;
  - no `load_or_extract_odb`, `_source_signature`, `_cache_is_valid` or `fast_cache`;
  - no specimen literals.
- **Unchanged:** M3 contracts, `abaqus_bridge.py`, `extract_odb.py`, M4.1–M4.5, M4.7,
  M4.8 logic, SPEC, DECISIONS.
- **Abaqus run count:** 0

## 2026-10-04 — M4.6 — No silent retry of failed solves on resume

- **Stage:** M4 (IN_PROGRESS); M4.6 REVIEW_READY
- **Gap found during worker review of M4.6 (`a0bc28b`):** after a `SolveFailure`, a
  plain resume would have re-run the failed solve. That is an implicit retry, contrary
  to "no automatic retries".
- **Fix (`services.identification_pipeline`):**
  - a failed solve is journalled (`solve_failure`);
  - a resumed run refuses that job with `SolveFailure` unless
    `PipelineConfig.retry_failed_solves` is set explicitly;
  - each authorised retry is journalled (`solve_retry`);
  - failed attempts count as executed Abaqus solves (`failed_solves`,
    `abaqus_solves_executed_total`).
- **Test:** `test_failed_solve_is_not_retried_on_resume_without_authorisation`.
- **Abaqus run count:** 0

## 2026-10-05 — M4.6 — SP13 p0 smoke gate: REPRODUCED

- **Stage:** M4 (IN_PROGRESS); M4.6 REVIEW_READY
- **Authorisation:** HUMAN supervisor.
  - **Scope:** exactly 1 Abaqus 2024 solve and 1 pinned `extract_odb.py` extraction for
    `SP13_a46d08b52995e078` (p0). No LM loop, no M4.9, no other candidates, no retry
    on failure.
  - **Run directory:** `D:\abaqus_m4_smoke` (`D:\abaqus_scratch_m4` untouched).
  - **Memory:** the first pre-flights stopped at about 9.4–9.9 GB available against the
    archived 19 GB peak. The human supervisor then closed applications and ruled that
    19 GB was a conservative reference peak, not a hard requirement. Grounds: the
    Abaqus minimum memory estimate (3.9 GB, archived `.dat`), the archived SP13
    behaviour, and the available virtual memory and disk. About 15.75 GB available
    was accepted.
- **Pre-flight:** all PASS.
  - job identity: generated INP SHA `a46d08b5…`;
  - solver profile `SP13/abaqus-2024/v1` (`79aebbfe…`);
  - Abaqus executable;
  - pinned script `039aa067…`;
  - archived reference pack;
  - fresh run directory;
  - disk.
- **Solve:** completed (`.sta` completion marker, `.dat` "Abaqus 2024").
  - ODB 715 614 536 bytes, the same size as the archive. SHA `56da620e…` differs from
    the archived `8c89585d…`, as expected, because of the ODB run metadata.
  - Wall-clock 620 s (archive 584 s); memory peak 18 GB.
- **Extraction:** pinned `extract_odb.py` through the controlled M4.6 path.
  - All checks PASS: modes and history, finite and real values, FE geometry identity,
    node set = registration subset (29 754), deterministic content.
  - The raw extraction was deleted after validation (retention rule).
- **Verdict: REPRODUCED.**
  - **30/30** EIGFREQ values (modes 1–30) are exactly equal to
    `carbon4c/post_solve_SP13.json` (maximum relative difference 0.0).
  - The new shape-pack content SHA `7941545b59390a65…` is **identical** to the
    validated baseline pack; the minimum FE-to-FE MAC is 1.0.
- **Unchanged:** M3 contracts, all code (HEAD `7f9d4b1` at run time), `abaqus_bridge.py`,
  `extract_odb.py`, solver profiles.
- **Evidence:** EVIDENCE.md entry "M4.6 — SP13 p0 smoke gate", PENDING SUPERVISOR REVIEW.
- **Archive proposal** (not executed): archive smoke provenance only (journal,
  comparison, extraction manifest, logs) under `carbon-project-archive/m4_smoke/`,
  referencing the existing `fe_shapes/SP13_a46d08b52995e078.npz`; no duplicate pack.
  The ODB stays in `D:\abaqus_m4_smoke` until review.
- **Abaqus run count:** 1 solve plus 1 Abaqus Python extraction (authorised).

## 2026-10-05 — M4.6 — SP13 smoke gate ACCEPTED by the SUPERVISOR

- **Stage:** M4 (IN_PROGRESS)
- **Review:** the SUPERVISOR accepts the SP13 p0 smoke gate.
  - The real M4.6 smoke-gate verdict is confirmed as **REPRODUCED**: 30/30 eigenfrequencies
    exact, and the shape-pack content SHA `7941545b…` identical to the validated baseline pack.
  - EVIDENCE.md "M4.6 — SP13 p0 smoke gate" moves from PENDING SUPERVISOR REVIEW to
    **ACCEPTED**.
- **Archive action:** remains a **proposal** until separately approved (provenance only,
  under `carbon-project-archive/m4_smoke/`; no duplicate pack). The ODB stays in
  `D:baqus_m4_smoke`.
- **Not started:** M4.9. No additional Abaqus.
- **Code changed:** none.

## 2026-10-05 — M4.9 preparation (fake solver only): REVIEW_READY; real gate NOT STARTED

- **Stage:** M4 (IN_PROGRESS); M4.9 `IN_PROGRESS` (preparation `REVIEW_READY`).
- **Authorisation:** SUPERVISOR, M4.9 PREPARATION ONLY. Excluded: real Abaqus truth solve,
  identification solves, Abaqus Python, M4.9 gate execution, changes to acceptance criteria,
  M4_DECISION_RECORD decisions or M3 contracts.
- **New module** `src/services/synthetic_twin.py`:
  - `TwinDefinition`: truth, start, noise sd, **explicit noise seed** (no default), FE modes, σ,
    k_int; content-hashed (free-text provenance excluded).
  - Deterministic noise: SHA-256(seed, mode) with Box–Muller, independent of NumPy.
  - `solve_truth`: the truth M3 job solved and extracted through the M4.6 components in its own
    journal. Resumable; a failed truth solve is not retried without authorisation; never counted
    in the 20 identification evaluations.
  - `build_synthetic_experiment`: truth FE modes 7–30 on the measured grid through the
    registration (R, measured-DOF contract), frequencies × (1 + sd·ε). Modes are numbered by
    synthetic frequency; FE numbers appear in provenance only. No real PolyMAX data.
  - `design_twin_observations`: strict freeze at p0, then M4.3 families and holdouts, then M4.4
    triggers and confirmation with the ±5 % packs (surface U1U2U3), then the M4.7 design
    (σ = 0.003, no provisional setup term).
    - Nothing is hand-selected.
    - UNSTABLE or UNSUPPORTED groups, or a design that `build_objective_design` refuses, make the
      twin design REFUSED.
  - `prepare_twin`: the twin's `PipelineConfig`. The twin definition hash, seed, experiment hash,
    truth-pack hash and provenance hash go into the run identity; p0 and ±5 % must be validated
    archived packs (otherwise refused). It writes a deterministic `twin_provenance.json`.
  - `assess_recovery`: M4.9 criteria 1–2 unchanged (CONVERGED; |ln(p̂/p_true)| ≤ local sd).
- **Unchanged:** M3 (`forward_builder.py`, `forward_model_manifest.py`, `shared_carbon_forward.py`,
  manifests), `extract_odb.py`, all M4.1–M4.8 modules, acceptance criteria, M4_DECISION_RECORD, the
  smoke-gate records, EVIDENCE.
- **Guard:** `tests/test_m4_generic_guard.py` now also checks `synthetic_twin.py`;
  `forward_builder` is allowed there read-only (SUPERVISOR to confirm, §6.4).
- **Tests:** `tests/test_synthetic_twin.py` (26, with the plate-like fake in
  `tests/m4_9_twin_support.py`) and `tests/test_m4_9_sp13_readiness.py` (3; 1 store-gated).
  - Fake twin: 24 rows FROZEN; the torsion holdout is found by the policy; the rotating
    near-degenerate pair is CONFIRMED (one cluster term); the stable close pair is INDEPENDENT.
    CONVERGED in 6 evaluations (5 reused archived packs, 1 solve).
  - A determinism; B resume without duplicate evaluations; C budget (p0 counts, reused packs
    count, the truth solve is separate); D injected exchange REFUSED with no re-pairing and no
    solve on resume; E cluster residual only when CONFIRMED.
  - SP13 readiness (no Abaqus): the start and ±5 % points render exactly to the validated pack
    jobs; the truth job has no pack.
  - Full suite: Windows 1290 tests OK (23 skipped) without data stores; 1292 OK (2 skipped) with both stores.
- **Decisions needed (not decided by the worker):**
  1. Noise seed of the real SP13 twin: the definition requires an explicit seed (no default); no SP13 twin definition is committed until the SUPERVISOR fixes it.
  2. UNSTABLE or UNSUPPORTED (>2-mode) trigger groups in the twin: implemented as a REFUSED design (no row is dropped silently); confirm, or define another rule.
  3. A CONFIRMED cluster split by the holdout selection: build_objective_design refuses, so the twin design is REFUSED; confirm, or define a rule.
  4. Real-gate criterion 3 (artificial branch exchange): the fake tests inject the exchange through the extraction executor; the mechanism and evidence for the real gate are not decided.
  5. Guard allow-list (M4_DECISION_RECORD.md §6.4): services/synthetic_twin.py imports forward_builder read-only (truth job, ±5 % job names); confirm the extension.
  6. Retention of the real truth ODB and pack after the M4.9 gate (archive or delete) is not decided.
- **Status discrepancies (recorded, not changed):**
  - The M4.9-preparation instruction says 'main: M4.6 ACCEPTED'; recorded state: M4.6 REVIEW_READY (only the SP13 smoke gate is ACCEPTED) and M4 is not merged to main. Not changed by the worker.
  - The instruction says 'M4.7 waiting for M4.9 observation pipeline'; recorded state: M4.7 REVIEW_READY. Not changed by the worker.
- **Correction note:** the previous entry's run directory `D:\abaqus_m4_smoke` contains a
  stray control character. Not edited (append-only); this note is the correction.
- **Abaqus runs:** 0. **Real Abaqus M4.9 gate NOT STARTED.**

## 2026-10-05 — M4.9 preparation: SUPERVISOR decisions recorded; dependency boundary restored

- **Stage:** M4 (IN_PROGRESS); M4.9 `IN_PROGRESS`; preparation `REVIEW_READY`. **Real M4.9 gate
  NOT STARTED** (unauthorised).
- **Decisions** recorded in M4_DECISION_RECORD.md §8:
  - fixed seed 20261005;
  - UNSTABLE / UNSUPPORTED groups are REFUSED;
  - a CONFIRMED cluster split by the holdout selection is REFUSED;
  - branch-exchange negative control on the real SP13 packs;
  - no direct twin → M3 import;
  - truth artifact retention;
  - factual status.
- **Dependency boundary (§8.5):**
  - `identification_pipeline.py` gains `forward_candidate` and `forward_jobs`. This is
    additive; the pipeline's own candidate creation now calls `forward_candidate`, with no
    behaviour change.
  - `synthetic_twin.py` no longer imports `forward_builder`.
  - The guard is restored, plus an explicit test that only the pipeline imports it.
- **SP13 twin definition:** `docs/auto_id/twins/SP13.twin.json`.
  - Seed 20261005; definition hash `c200b293…`.
  - Truth/start/noise/σ/modes follow §4–§5.
- **Truth retention (§8.6):** the provenance carries the retention rule. The twin work
  directory holds only the truth pack; archived packs are referenced by hash only.
- **New tests:**
  - UNSTABLE group REFUSED;
  - UNSUPPORTED group REFUSED (no row excluded);
  - CONFIRMED cluster split by the validation holdout REFUSED;
  - SP13 twin definition (seed explicit, pinned hash, seed changes the hash);
  - retention / no duplicate packs;
  - the forward-builder boundary;
  - **real-pack negative control (store-gated):**
    - the M4.2 SP13 frozen rows (R1 ↔ FE 10, R2 ↔ FE 11);
    - 45° in-memory mixing of FE 10/11 in the archived E−5 % candidate, immediately before
      M4.5, gives REFUSED (`BRANCH_LOSS`);
    - frozen rows unchanged, 0 solves, pack files unchanged, still refused on replay;
    - controls: without injection the candidate tracks (R1 → 10, R2 → 11); a pure
      relabelling is tracked as a crossing (R1 → 11, R2 → 10), not refused;
    - recorded as a negative control, **not physical FE evidence**.
- **Full suite:** Windows 1296 tests OK (24 skipped) without data stores; 1301 OK (2 skipped) with both stores.
- **Worker observation (§8.8, diagnostic):** the pinned SP13 p0 frequencies alone trigger
  > 2-mode groups (FE 13–15, 20–23, 28–30). If all members freeze in the twin, §8.2 makes
  the design REFUSED. This is for the SUPERVISOR / HUMAN to weigh before any real gate.
- **Unchanged:** M3 contracts and files, `extract_odb.py`, acceptance criteria, smoke-gate
  records, EVIDENCE.
- **Abaqus runs:** 0 (no Abaqus Python). **Real Abaqus M4.9 gate NOT STARTED.**

## 2026-10-05 — M4.9 truth / observation-readiness gate: REFUSED_BEFORE_IDENTIFICATION

- **Stage:** M4 (IN_PROGRESS); M4.9 `IN_PROGRESS`. The identification loop was **not started**.
- **Authorisation:** HUMAN. Exactly 1 SP13 truth Abaqus 2024 solve (45000 / 4000 MPa) and
  1 pinned extraction, outside the 20-evaluation budget.
- **Executed:** 1 solve plus 1 Abaqus Python extraction.
  - Both were hard-limited to one call each. The identification executors refused any call.
  - Run directory: `D:\abaqus_m4_truth`.
  - Pre-flight: all 5 archived packs verified; the truth job has no existing pack; 16.8 GB
    RAM free.
- **Truth:**
  - job `SP13_bb3e5d7d131bed4f`, INP `bb3e5d7d…`;
  - solve completed in 621 s, ODB `57282e50…`;
  - pack `758add0c…`, all extraction checks PASS.
- **Pipeline:** `services.synthetic_twin.prepare_twin`, unchanged; the twin definition is
  unchanged.
  - Synthetic experiment `5b0450d8…` (seed 20261005).
  - Strict freeze FROZEN with 23 rows (exp 24 / FE 30 excluded by the policy).
  - Holdouts: R1 (FE 7, torsion) and R23 (FE 29, validation).
- **Trigger groups:** ['R11', 'R12'] = FE [17, 18] INDEPENDENT; ['R14', 'R15', 'R16', 'R17'] = FE [20, 21, 22, 23] UNSUPPORTED; ['R18', 'R19'] = FE [24, 25] INDEPENDENT; ['R20', 'R21'] = FE [26, 27] INDEPENDENT; ['R22', 'R23'] = FE [28, 29] INDEPENDENT; ['R4', 'R5'] = FE [10, 11] INDEPENDENT; ['R7', 'R8', 'R9'] = FE [13, 14, 15] UNSUPPORTED.
- **Verdict: REFUSED_BEFORE_IDENTIFICATION.**
  - Groups FE 13–15 and FE 20–23 are UNSUPPORTED (§8.2).
  - The M4.7 design is not built. Parameter count 2.
- **Records:**
  - EVIDENCE "M4.9 — SP13 truth gate" (PENDING SUPERVISOR REVIEW);
  - M4_DECISION_RECORD §9;
  - provenance copies in `docs/auto_id/twins/SP13_truth_gate/`.
- **Unchanged:** code, M3 contracts, policies, thresholds, acceptance criteria, twin
  definition.
- **Full suite:** docs/provenance only; code unchanged since 4ce5e6a (Windows 1296 OK/24 skipped without stores, 1301 OK/2 skipped with stores; Linux CI 1293 OK).
- **Decision needed:** how M4.9 proceeds.

## 2026-10-05 — M4.4 N-mode cluster design review (analysis only)

- **Stage:** M4 (IN_PROGRESS); M4.9 `IN_PROGRESS`. The SUPERVISOR acknowledged the truth-gate
  verdict REFUSED_BEFORE_IDENTIFICATION. Policy is unchanged.
- **Document:** `docs/auto_id/M4_4_NMODE_CLUSTER_REVIEW.md` (PROPOSAL).
  - Compares the options:
    - A, N-dimensional subspace examination (A1: INDEPENDENT only; A2: full N-mode confirmation);
    - B, symmetry subdivision;
    - C, permanent refusal.
  - For each: validity, SPEC §12.4 compatibility, the M4.7 and M4.5 effects, acceptance, code
    and risk.
- **Evidence** (read-only diagnostics on validated packs; no Abaqus):
  - the members of FE 13–15 and FE 20–23 are mutually orthogonal (p0 MAC 0.0000) and of
    distinct parity classes, except the (0,4)/(4,0) pair;
  - each is individually stable (MAC ≥ 0.9998, unique counterpart) in E±, G12± and at the truth;
  - the N-subspace cos² is ≥ 0.9999.
- **Side finding:** the (4,4) mode at FE 30 leaves the extracted range 7–30 in some states.
  That is why exp 24 was excluded. It is an edge-of-mode-set risk for a later LM loop.
- **Recommendation:** A1. A2 deferred; B only as corroborating evidence; C until decided.
- **Truth artifacts (proposal):**
  - pack → `carbon-project-archive:fe_shapes/SP13_bb3e5d7d131bed4f.npz`;
  - provenance → `carbon-project-archive:m4_twin/SP13_truth_gate/` (SHA-pinned);
  - ODB temporary (§8.6).
- **Code changed:** none. **Abaqus runs:** 0.

## 2026-10-05 — M4.4 A1 (N-mode independence) implemented; M4.9 readiness re-run: READY_FOR_IDENTIFICATION

- **Stage:** M4 (IN_PROGRESS); M4.4 `REVIEW_READY` (extended); M4.9 `IN_PROGRESS`. The
  identification loop was **not started**.
- **Decision:** SUPERVISOR approved option A1. Recorded as DECISIONS.md D-032 and
  M4_DECISION_RECORD §10. No SPEC change is required.
- **Code:** `src/services/identification_clusters.py`.
  - N > 2 trigger groups are INDEPENDENT only with unique matches (MAC ≥ 0.9) and a stable
    N-subspace (cos² > 0.95) in every direction; otherwise UNSUPPORTED.
  - The 2-mode path is unchanged; no new thresholds.
- **Tests:**
  - 7 new cluster tests: 3- and 4-mode INDEPENDENT; ambiguous, rotating and unstable-subspace
    → UNSUPPORTED; validation; 2-mode unchanged.
  - Twin: a stable triple → INDEPENDENT with the design USABLE; a rotating triple →
    UNSUPPORTED with the design REFUSED.
  - TWIN_TRUTH pack record tests.
- **Truth artifacts archived (approved):**
  - `carbon-project-archive/fe_shapes/SP13_bb3e5d7d131bed4f.npz`;
  - `m4_twin/SP13_truth_gate/` with `ARCHIVE_MANIFEST.json` (SHA-256 per file), indexed in the
    global archive manifest under `m4_twin`;
  - repository record `fe_shapes/SP13_bb3e5d7d131bed4f.shape-pack.json` (TWIN_TRUTH).

  The ODB was not archived; the p0/±5 % packs were not duplicated.
- **Readiness re-run (0 Abaqus solves, 0 extractions; resumed truth journal):**
  - same freeze (`05a5443a…`);
  - FE 13–15 INDEPENDENT; FE 20–23 INDEPENDENT;
  - 23 frozen rows: 2 holdouts (R1, R23) and 21 fit rows; 0 cluster terms;
  - the M4.7 design is **valid**. Verdict **READY_FOR_IDENTIFICATION**.
  - Evidence: EVIDENCE "M4.9 — SP13 observation readiness after A1" (PENDING SUPERVISOR REVIEW).
- **Open risk (recorded):** R23 (FE 29) sits at the upper extracted-mode boundary. The range is
  not expanded.
- **Full suite:** Windows 1306 OK (25 skipped) without data stores; 1311 OK (2 skipped) with both stores.
- **Abaqus runs:** 0.

## 2026-10-05 — M4.9 pre-loop decision review (analysis only)

- **Document:** `docs/auto_id/M4_9_PRELOOP_REVIEW.md` (PROPOSAL).
- **Bounds:** no authoritative E_in_plane / G12 bounds exist; the SPEC requires bounds but gives
  no values. Proposed development-only bounds: a factor-2 box around p0 in ln p (E 26000–104000,
  G12 2250–9000).
- **FE 29 / R23:** in range (mode 29 or 30) in all six validated states; MAC ≥ 0.986; no
  ambiguity. FE 30 (4,4) leaves the range in E−, G12+ and at the truth. Option A recommended
  (keep modes 7–30 and accept a refusal).
- **Run root:** `D:baqus_m4_twin_loop`, with a retention proposal.
- **Loop gate:** ≤ 20 evaluations including 5 reused; ≤ 15 new solves and 15 extractions.
- **Unchanged:** code, status, DECISIONS, EVIDENCE. **Abaqus runs:** 0.

## 2026-10-05 — M4.9 real identification loop: CONVERGED (REVIEW_READY)

- **Stage:** M4 (IN_PROGRESS); **M4.9 `REVIEW_READY`**. Not accepted by the worker; no merge;
  no M5.
- **Authorisation:** HUMAN gate. Development-only bounds E 26000–104000 / G12 2250–9000;
  extraction range 7–30 (option A); run root `D:\abaqus_m4_twin_loop`; at most 20 evaluations
  (5 reused), at most 15 new solves.
- **Result: CONVERGED.**
  - Estimate: E 45005.45 / G12 4012.20 MPa (truth 45000 / 4000).
  - |ln error| / sd: E 0.000121 / 0.002064; G12 0.003046 / 0.009951. Both are within 1σ.
- **Effort:** 6 evaluations (5 reused); **1 new Abaqus solve plus 1 extraction** (614 s solve).
- **History:** iteration 1 accepted (Φ 5260.09 → 9.97); iteration 2 step below 0.2·sd, so
  CONVERGED.
- **Run quality:**
  - no rejected step, no refusal, no active bound;
  - R23 tracked in every evaluation (minimum MAC 0.9861);
  - holdout residuals at p̂: R1 +0.031, R23 −0.311.
- **Determinism:** zero-Abaqus journal replay gives an identical result; the journal is unchanged.
- **Archived (approved):** `carbon-project-archive/m4_twin/SP13_identification_loop/` (manifest
  `11eb6493…`, indexed globally). The ODB is kept in the run directory until review.
- **Records:**
  - EVIDENCE "M4.9 — SP13 synthetic-twin identification loop" (PENDING SUPERVISOR REVIEW);
  - M4_DECISION_RECORD §11;
  - `docs/auto_id/twins/SP13_identification_loop/`.
- **Unchanged:** code, M3 contracts, thresholds, bounds, observation set.
- **Full suite:** code unchanged since 7597b60 (Windows 1306 OK/25 skipped without stores, 1311 OK/2 skipped with stores; Linux CI 1303 OK); docs-only rerun below.

## 2026-10-05 — M4 SUPERVISOR acceptance and stage closure

- **Stage:** M4 `REVIEW_READY`. M4.1–M4.9 **ACCEPTED** (SUPERVISOR); **M4 gate PASS**; stage PR
  `auto-id/m4` → `main` prepared, **not merged**. `last_accepted_stage` stays M3 until the HUMAN
  merge. **M5 not started.**
- **Evidence:** six pending M4 entries **ACCEPTED** (SUPERVISOR, 2026-10-05):
  - ODB shape-extraction gate with the M4.2 complete-MAC freeze;
  - M4.3 real classification;
  - M4.4 R1/R2;
  - M4.9 truth gate;
  - readiness after A1;
  - M4.9 identification loop.

  The scientific text is unchanged. The M4.6 smoke-gate entry stays ACCEPTED.
- **M4.9 gate result:**
  - Recovered E = 45005.45 MPa, G12 = 4012.20 MPa; truth E = 45000 MPa, G12 = 4000 MPa. Both
    within 1σ.
  - 6/20 evaluations: 5 reused, 1 new identification solve plus 1 extraction.
  - Deterministic replay PASS.
  - The branch-exchange negative control is REFUSED, as required.
  - M3 contracts unchanged.
- **Qualifications:**
  - M4.3 classifier thresholds remain PROVISIONAL;
  - real SP13 identification stays refused (option C);
  - SP02 stays NOT_FROZEN;
  - the M4.9 bounds are development-only twin bounds.
- **Governance:**
  - M4_DECISION_RECORD §12, plus the stale header and batch table corrected;
  - DECISIONS.md D-033–D-038 promoted (pairing policy, LM and budget, provisional classifier,
    twin gate, refusal rules, M3 dependency boundary). The bounds are not promoted.
- **Stage-gate test:** `tests/test_m4_stage_gate.py` (records only).
  - Pinned provenance copies, the archive-manifest binding, run identity, journal hash chain,
    budget, the 1σ result, no active bound, deterministic replay, the negative-control binding;
  - store-gated M3 re-rendering and archive verification.
  - The committed copies of the two archive manifests were added.
- **Full suite:** Windows 1325 OK (27 skipped) without data stores; 1330 OK (2 skipped) with both stores; tests/test_m4_stage_gate.py 17 passed + 2 store-gated skipped (no stores) / 19 passed (stores); targeted M4 + M3 gate 196 passed.
- **Abaqus runs during closure:** 0. No artifacts deleted.

## 2026-10-05 — M4 merged to main (PR #31)

- **Stage:** M4 **ACCEPTED** and merged. PR #31 (`auto-id/m4` → `main`), merged with a merge commit
  under explicit HUMAN authorisation.
  - **Merge commit:** `ee22e3389127a49ada2bc4d887fc757bcea9d69d`. Parents: `main` `6185b05` and the reviewed head `7a54864`.
  - **Tree:** identical to the reviewed head.
- **STATUS:**
  - `last_accepted_stage` = M4, `last_accepted_ministep` = M4.9, `last_accepted_commit` = the
    merge commit;
  - `main_merges` gains M4 / PR #31.
- **Qualifications kept:**
  - the M4.3 classifier thresholds remain PROVISIONAL;
  - real SP13 identification remains refused (option C);
  - SP02 remains NOT_FROZEN;
  - the M4.9 bounds remain development-only twin bounds.
- **M5:** `NOT_STARTED`; M5.1–M5.9 `TODO`.
- **Bookkeeping branch:** `auto-id/m4-closure`, created from the merge commit.
- **Unchanged:** code and scientific logic. No Abaqus. Retained ODB / INP artifacts are not
  deleted.

## 2026-10-05 — M5 started; checkpoint M5-A (M5.1–M5.4) REVIEW_READY

- **Stage:** M5 `IN_PROGRESS` on branch `auto-id/m5` (from `main` `8f405c3`).
  - M5.1–M5.4: `REVIEW_READY`.
  - M5.5–M5.9: `TODO`.
- **SUPERVISOR entry decisions:** M5_DECISION_RECORD.md §1–§16; DECISIONS.md D-039–D-044.
  - synthetic gate scope;
  - Broyden J for the twin control;
  - explicit priors;
  - rcond 1e-3 as a hard block;
  - q_G as a diagnostic;
  - Birge χ² and dof;
  - linearised leave-one-family-out;
  - the singleton pattern rule;
  - family consistency NOT_AVAILABLE ≠ PASS;
  - the registration-limited source;
  - S4 deferred but mandatory later.
- **New module:** `src/services/practical_identifiability.py`. SPEC §10 in ln p:
  - typed global / nuisance sensitivity matrix (fit terms only; a cluster is one term);
  - explicit Σ (Cholesky whitening);
  - explicit nuisance prior rows;
  - rank at rcond 1e-3 as a hard block with no override;
  - C and sd foundation;
  - SPEC §10 sd > 8 % evidence;
  - q projections (q_G);
  - diagnostics (condition number, correlation, S~ cosines);
  - deterministic hashes;
  - reconstruction of the Broyden-updated LM Jacobian from a journal.

  Legacy Stage-A modules are unchanged.
- **Tests:** `tests/test_practical_identifiability.py` (16, synthetic).
  - Cases A–N; a weak-nuisance contrast; a module-boundary guard.
  - The M4.9 twin positive control: deterministic Broyden reconstruction from the committed
    journal; the M5 posterior sd of that global-only system equals the recorded value.
  - Absorption case: q_G ≈ 0.018 and sd(ln G12) ≈ 0.50, above the 0.08 limit, so the evidence is
    NOT_IDENTIFIABLE-compatible.
- **Full suite:** Windows 1341 OK (27 skipped) without data stores; 1346 OK (2 skipped) with both stores; M5-A 16 passed; targeted M4 regression + M4 and M3 stage gates 120 passed.
- **Abaqus runs:** 0. No M4 artifact deleted. No M4 scientific result changed.

## 2026-10-05 — M5 checkpoint M5-B (M5.5, M5.8, M5.6) REVIEW_READY

- **Stage:** M5 `IN_PROGRESS` (branch `auto-id/m5`).
  - M5.1–M5.4 `REVIEW_READY` (acknowledged by the SUPERVISOR).
  - M5.5, M5.6, M5.8 `REVIEW_READY`.
  - M5.7, M5.9 `TODO`.
- **SUPERVISOR M5-A confirmations** recorded (M5_DECISION_RECORD §17.1): sd_ln > 0.08; S~
  cosines; q on the augmented system; Cholesky whitening; the Linux flake recorded as unrelated
  debt.
- **New module:** `src/services/identification_uncertainty.py`.
  - **M5.5:** `statistical_sd` from the full M5 system only (never an M4 local_sd), with Σ and
    prior provenance and a context label; rank deficiency refused.
  - **M5.8:** residual-pattern test per D-043, with strict inequalities and cluster = one term.
  - **M5.6:** conditional Birge per D-041, populated only when the pattern test passed;
    `statistical_sd` kept separately.
- **Tests:** `tests/test_identification_uncertainty.py` (19, A–P).
- **M4.9 twin synthetic records-based control:**
  - `statistical_sd_ln`: E 0.002064, G12 0.009951;
  - pattern PASS; χ²/dof 19.946/19, s_B 1.0246;
  - `birge_adjusted_sd_ln`: E 0.002115, G12 0.010195.

  Not refused, and not real-specimen uncertainty.
- **Full suite:** Windows 1360 OK (27 skipped) without data stores; 1365 OK (2 skipped) with both stores; M5-A+M5-B 35 passed; targeted M4 regression + M4 and M3 stage gates 139 passed.
- **Abaqus runs:** 0. No policy change.

## 2026-10-05 — M5 checkpoint M5-C (M5.7 model_form_robustness) REVIEW_READY

- **Stage:** M5 `IN_PROGRESS` (branch `auto-id/m5`).
  - M5.1–M5.8: `REVIEW_READY`.
  - M5.9: `TODO`.
- **SUPERVISOR confirmation:** the cluster family rule (shared family, or a unique composite key;
  a singleton when alone), recorded in M5_DECISION_RECORD §18.1.
- **New module:** `src/services/model_form_robustness.py`. Linearised leave-one-family-out at p̂
  (D-042):
  - remove all fit terms of a family (re-whitened with the reduced Σ);
  - keep every prior row;
  - the same M5.3 rank rule (rcond = 1e-3); a rank-deficient reduced system is refused, with no
    pseudo-inverse and no override;
  - range of the estimates in % of p̂;
  - hash-bound;
  - labelled `model_form_robustness`, not uncertainty or 1σ.
- **Tests:** `tests/test_model_form_robustness.py` (15, A–O).
- **M4.9 twin synthetic records-based control:** 21 families, none refused.
  - E range 0.222 % (half-range 0.111 %).
  - G12 range 1.058 % (half-range 0.529 %).
  - Not real-specimen evidence.
- **Full suite:** Windows 1375 OK (27 skipped) without data stores; 1380 OK (2 skipped) with both stores; M5-A+B+C 50 passed; targeted M4 regression + M4 and M3 stage gates 154 passed.
- **Abaqus runs:** 0. No policy change.

## 2026-10-05 — M5 checkpoint M5-D (M5.9 verdict engine + M5 stage gate): M5 REVIEW_READY

- **Stage:** M5 `REVIEW_READY`.
  - M5.1–M5.9 `REVIEW_READY`.
  - **M5 stage gate PASS** (`tests/test_m5_stage_gate.py`).
  - Not self-accepted. Last accepted merged stage remains M4. **M6 NOT STARTED.**
- **SUPERVISOR decisions:** M5_DECISION_RECORD §19; DECISIONS.md D-045 (ln-space envelope and
  verdict semantics), D-046 (sandwich G12), D-047 (sd > 8 % without refit).
- **New module:** `src/services/identification_verdict.py`. A pure verdict engine on explicit
  evidence records:
  - guards with PASS / FAIL / NOT_AVAILABLE;
  - D-044 context handling;
  - the SPEC §5.1 sandwich-G12 policy;
  - no implicit PASS, no override;
  - separately labelled uncertainties;
  - `compute_evidence_chain` (M5.3 → M5.5 → M5.8 → M5.6 → M5.7, no refit).
- **Tests:**
  - `tests/test_identification_verdict.py` (9);
  - `tests/test_m5_stage_gate.py` (9);
  - `tests/m5_gate_support.py` (synthetic cases A–F, twin control).
- **Gate outcomes:**
  - A: IDENTIFIED;
  - B: q_G 0.0145, G12 NOT_IDENTIFIABLE (sd_ln 0.50);
  - C: hard block;
  - D: no green verdict;
  - E: WIDE (0.0632);
  - F: G12 BARE_PLATE_REQUIRED / nuisance not independent;
  - G: labels separate.
- **M4.9 twin synthetic records-based control:**
  - conservative_ln E 0.002115 / G12 0.010195;
  - both IDENTIFIED in the synthetic-gate context, both NOT_IDENTIFIABLE in the production
    context;
  - not real-specimen identification.
- **Full suite:** Windows 1393 OK (27 skipped) without data stores; 1398 OK (2 skipped) with both stores; all M5 tests 68 passed; targeted M4 regression + M5, M4 and M3 stage gates 172 passed.
- **Abaqus runs:** 0. No refit, no policy change beyond the recorded SUPERVISOR decisions.

## 2026-10-06 — M5 SUPERVISOR acceptance and stage closure

- **Stage:** M5.1–M5.9 **ACCEPTED** (SUPERVISOR); **M5 gate PASS**.
  - Stage status `REVIEW_READY`; stage PR `auto-id/m5` → `main` prepared, **not merged**.
  - `last_accepted_stage` stays M4 until the HUMAN merge.
  - **M6 NOT_STARTED.**
- **Scope:** synthetic stage-gate machinery and software / scientific-pipeline evidence only.
  **Not** a real-specimen material identification.
- **Gate results:**
  - q_G absorption case: q_G ≈ 0 diagnostically; G12 NOT_IDENTIFIABLE from the full uncertainty
    calculation;
  - rank-deficient case: hard-blocked, no override;
  - systematic model error / holdout failure: no green verdict;
  - WIDE only when every guard passes;
  - `statistical_sd`, `birge_adjusted_sd` and `model_form_robustness` stay separate.
- **M4.9 twin records-based synthetic control:** IDENTIFIED in the synthetic-gate context only.
- **Records:**
  - EVIDENCE.md "M5 — Practical-identifiability and verdict machinery: synthetic stage gate and
    M4.9 twin records-based control" (ACCEPTED);
  - DECISIONS.md D-048 (cluster family identity, promoted from M5_DECISION_RECORD §18.1);
  - M5_DECISION_RECORD §20 (acceptance), plus the stale header and table refreshed.
- **Qualifications kept:**
  - real t_face / k_core columns and priors not available;
  - real Σ_meas NOT_AVAILABLE;
  - S4 noise control is future HUMAN-gated work;
  - production family consistency is later real-data work;
  - sandwich G12 needs bare-plate and/or independent nuisance evidence;
  - M4.3 thresholds PROVISIONAL;
  - real SP13 refused; SP02 NOT_FROZEN.
- **Full suite:** Windows 1393 OK (27 skipped) without data stores; 1398 OK (2 skipped) with both stores; M5 tests 68 passed (test_m5_stage_gate 9); M5/M4/M3 stage gates + M4 regression 144 passed.
- **Abaqus:** 0 solves and 0 extractions in M5. M3 and M4 unchanged. No retained artifact
  deleted. No code change in the closure.

## 2026-10-06 — M5 merged to main (PR #33)

- **Stage:** M5 **ACCEPTED** and merged. PR #33 (`auto-id/m5` → `main`), merged with a merge commit
  under explicit HUMAN authorisation.
  - **Merge commit:** `ab75315b5977082599e9af181c6c1c41c1d82a70`. Parents: `main` `8f405c3` and the reviewed head `3341568`.
  - **Tree:** identical to the reviewed head.
- **STATUS:**
  - `last_accepted_stage` = M5, `last_accepted_ministep` = M5.9, `last_accepted_commit` = the
    merge commit;
  - `main_merges` gains M5 / PR #33.
- **Qualifications kept:**
  - the M5 gate is synthetic only;
  - no real t_face / k_core sensitivity columns or priors;
  - real Σ_meas NOT_AVAILABLE;
  - the real S4 ±2.5 % FE noise control needs a HUMAN gate;
  - production family consistency needs later stages;
  - sandwich G12 needs bare-plate / independent nuisance evidence;
  - M4.3 thresholds PROVISIONAL;
  - real SP13 refused; SP02 NOT_FROZEN.
- **M6:** `NOT_STARTED`; M6.1–M6.4 `TODO`.
- **Bookkeeping branch:** `auto-id/m5-closure`, created from the merge commit.
- **Unchanged:** code and scientific logic. No Abaqus. Retained M4 artifacts untouched.

## 2026-10-06 — M6 started; checkpoint M6-A (entry decisions, SP-11 experiment checklist)

- **Stage:** M6 `IN_PROGRESS` on branch `auto-id/m6` (from `main` `ab1dc60`).
  - M6.1 `IN_PROGRESS`, readiness NEEDS_DATA (not `REVIEW_READY`).
  - M6.2 and M6.3 `TODO`, NEEDS_DATA.
  - M6.4 `TODO`, NEEDS_DECISION.
  - M6 gate not evaluated; M7 `NOT_STARTED`.
- **SUPERVISOR entry decisions:** M6_DECISION_RECORD.md §1–§11; DECISIONS.md D-049–D-056.
  - SP-11 is the M6 twill bare plate; its old FRFs are reconnaissance only; a new acquisition is
    required;
  - `STAGE_A_VALIDATION` context, never production IDENTIFIED while family consistency is
    NOT_AVAILABLE (M7);
  - D12 fitted only at full practical rank (rcond 1e-3), otherwise governed fixed ν12;
  - analytic thickness propagation, spatial scatter not divided by √N, t⁻³ explicit;
  - M6.2 repeat principle, with the estimator deferred; provisional Σ_setup flagged; Σ_meas never
    invented;
  - core tiles per topology (CARBON-5F is context only);
  - M6.4 ranges not invented; sandwich t_face and interface deferred;
  - legacy Stage-A rules excluded.
- **New document:** M6_SP11_EXPERIMENT_CHECKLIST.md, the exact HUMAN measurements before M6-C,
  sections A–E.
- **Code:** none in this checkpoint.
- **Abaqus runs:** 0. No retained M4 artifact deleted.

## 2026-10-06 — M6 checkpoint M6-B (Stage-A → M5 adapter) REVIEW_READY

- **Status:**
  - M6-B `REVIEW_READY`;
  - M6.1 stays `IN_PROGRESS` / NEEDS_DATA, not `REVIEW_READY`: no real SP-11 data, and M6-C is not
    authorised;
  - M6.2–M6.4 unchanged.
- **New modules:**
  - `src/domain/stage_a_experiment.py`: typed Stage-A experimental evidence. Every gap is refused
    together, with typed codes: FRF-only, not curve-fitted, no frozen modal set, < 9 thickness
    points, attachment / non-contact route, < 2 excitation locations, suspension, mass / plan,
    geometry calibration, fixed-pair fallback, non-strict policy.
  - `src/services/stage_a_validation.py`: `run_stage_a_validation`. It runs:
    - the verified affine Stage-A basis;
    - strict FE-to-FE tracking;
    - the M4.8 LM with explicit settings and bounds;
    - the D12 rank policy (D-051);
    - ±5 % ln-p sensitivities;
    - the M5 chain: rank, `statistical_sd`, pattern, Birge, leave-one-family-out;
    - the M5.9 PRODUCTION verdict embedded (always NOT_IDENTIFIABLE while family consistency is
      NOT_AVAILABLE);
    - derived E and G12 with separately labelled frequency, thickness-spatial and gauge components
      (t⁻³ explicit);
    - the `STAGE_A_VALIDATION` report with deterministic hashes;
    - the M6.2 comparison interface (no agreement rule yet).
- **Unchanged:** the M1–M5 modules and the legacy Stage-A modules.
- **Worker design choices and open items:** M6_DECISION_RECORD.md §12–§14.
- **Tests:**
  - `tests/test_stage_a_validation.py`: 27, synthetic (SUPERVISOR items 1–20 plus 7 more).
  - Targeted: M6-B + Stage-A + M5 + M4 guard, 261 passed (2 Abaqus-gated tests skipped); M3/M4/M5
    stage gates with stores, 30 passed.
  - Full suite, Windows: 1420 OK (27 skipped) without data stores; 1425 OK (2 skipped) with both
    stores.
- **Abaqus:** 0 solves and 0 Abaqus Python extractions. No retained M4 artifact deleted.

## 2026-10-06 — M6 corrective governance after the D:\Snadwich source audit (M6-A correction)

- **Basis:** the read-only `D:\Snadwich` source audit, accepted by the SUPERVISOR as the factual
  basis.
- **Decisions (append-only):**
  - **D-057 corrects D-049.** Kept: SP-11 is the twill bare plate, and its data are
    reconnaissance-only. Removed: "resolution insufficient" as a standalone bar, and "new
    acquisition required". M6.1 is `BLOCKED_ON_EXPERIMENT` because there is no fitted/frozen
    modal set, the sessions are inconsistent, the support data are incomplete, and no new
    experiment is available.
  - **D-058 corrects D-053.** The repeat wording now follows SPEC §7: the same grid supports
    frequencies, shapes and MAC; a different grid supports frequency-only. M6.2 is
    `BLOCKED_ON_EXPERIMENT`; the definition is not weakened.
- **Documents:**
  - M6_DECISION_RECORD.md §15 added, with superseded / corrected notes in §3, §7 and §14;
  - M6_SP11_EXPERIMENT_CHECKLIST.md re-labelled as reference requirements (AVAILABLE_NOT_YET_GOVERNED
    / MISSING / UNAVAILABLE_FOR_THIS_PROJECT);
  - new SNADWICH_INVENTORY.md (a factual inventory; no passports).
- **Status:**
  - M6 `IN_PROGRESS`; M6-A `REVIEW_READY` (corrected); M6-B `REVIEW_READY`;
  - M6.1 and M6.2 `BLOCKED_ON_EXPERIMENT`;
  - M6.3 `TODO` (NEEDS_DATA, feasibility unresolved); M6.4 `TODO` (NEEDS_DECISION);
  - gate `NOT_EVALUATED`; M7 `NOT_STARTED`.
- **Unchanged:** SPEC, the ROADMAP mini-step definitions, and all code. M6-B is unchanged.
- **Abaqus:** none.

## 2026-10-06 — M6 / STEEL normative rescope (SPEC §19 item 6; D-059–D-061)

- **SPEC §19 item 6 (new, normative):** supersedes the §17 M6 acceptance row and the §17 STEEL
  sentence. SPEC §5, §5.1, §5.3 and §7 are unchanged.
- **Decisions:**
  - **D-059:** M6.1, M6.2 and M6.3 are `NOT_AVAILABLE_WITH_CURRENT_SETUP`, with their
    consequences kept. It supersedes D-054 in part (the tile plan) and the status labels of D-057
    and D-058.
  - **D-060:** STEEL is removed; supersedes D-015. Results are labelled not externally validated.
  - **D-061:** the rescoped M6 gate.
- **Documents:** ROADMAP (M6 table and gate; STEEL `SUPERSEDED`), STATUS (`steel_gate`, M6
  readiness, M6.4 NEEDS_SOURCE), M6_DECISION_RECORD §16.
- **Status:**
  - M6 `IN_PROGRESS`;
  - M6.1–M6.3 `NOT_AVAILABLE_WITH_CURRENT_SETUP`;
  - M6.4 `TODO` (NEEDS_SOURCE);
  - gate `NOT_EVALUATED`;
  - M7 `NOT_STARTED`.
- **Unchanged:** code (M6-B unchanged). No Abaqus.

## 2026-10-06 — SP-13 physical registration gate (zero Abaqus; D-062, D-063)

- **New code:** `services/psv_video_registration.py` (read-only `.svd` reconstruction; no modal
  imports), `archived_baseline.reregistered_mac_matrix` / `reregistered_shape_pack_evidence`
  (existing archived path unchanged), and three tools (reconstruct, build registration,
  re-evaluate).
- **Governed files:**
  - the reconstruction record;
  - `SP13.physical.specimen.json` (`scan_to_panel_edges` + `camera_grid`; physical_specimen_id
    SP-13; remount 260909 → 260910 `re_suspension`);
  - `SP13_physical_registration.json` (`2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823`, production-ready);
  - the re-evaluation record.
- **Legacy:** the legacy registration and passport are unchanged, kept as historical provenance.
- **Result:**
  - strict pairs legacy (4,10),(5,11) → physical (4,10),(7,13);
  - MAC 0.888 → 0.958 for 4 ↔ 10; condition number 252 → 6.3;
  - after the unchanged M4.3 holdout, one fit row: SP-13 alone still insufficient.
- **Uncertainty:** translation 5.72 mm and rotation 0.49° derived; `scale_rel` NOT_AVAILABLE, so
  `registration_limited` is NOT_AVAILABLE.
- **Σ_setup:** provisional 0.3 %; measured `NOT_AVAILABLE_PENDING_MODAL_PREPARATION`.
- **Tests:** `tests/test_sp13_physical_registration.py` (anti-tuning static checks; pinned files;
  re-registration binding; store-gated reproduction of the reconstruction, the registration and both
  freezes).
- **Abaqus:** 0 solves and 0 extractions. Pairing policy, thresholds and modal data unchanged.

## 2026-10-06 — SP-13 HUMAN evidence update (H7–H10) and SP-02 physical registration gate (zero Abaqus; D-064)

- **SP-13:**
  - The gate at `173af43` is recorded as SUPERVISOR-ACCEPTED.
  - The passport takes the H7 orientation source and `scale_rel` 0.002 (H8 readout only). The
    manifest is now `b857724a…`; the registration hash `2eeeaa86…` is unchanged.
  - New M2.4 record: EVALUATED, `registration_limited` False (MAC crossing and pairing change both
    evaluated).
  - Σ_setup stays at the provisional 0.3 %, flagged (H9). 260909 → 260910 is FREQUENCY_ONLY (H10).
- **Code:**
  - `psv_video_registration.alignment_points` reads the stored point count (behaviour change,
    tested). The SP-13 record is rebuilt bit-identically.
  - `reconstruct_psv_registration.py`: optional `--dimension-uncertainty`.
  - New tools: `build_physical_registration.py`, `registration_uncertainty_evaluation.py`,
    `sp02_registration_reevaluation.py`.
- **SP-02 governed files (new):**
  - the reconstruction record (`b9234f57…`);
  - `SP02.physical.specimen.json` (manifest `83739ecd…`; `physical_specimen_id` null);
  - `SP02_physical_registration.json` (`9b63f6c8…`);
  - the re-evaluation and M2.4 records.
  - The legacy SP-02 registration, passport and fixture are unchanged.
- **SP-02 result:**
  - Anisotropy x 1.092 / y 0.818; legacy vs physical median 28.9 mm, max 54.1 mm.
  - Strict pairs: legacy (2,8) NOT_FROZEN → physical (2,8),(4,10),(7,13) FROZEN.
  - M4.3 validation holdout R3; fit rows R1, R2 (condition number 6.1). `registration_limited`
    False.
  - Identity: NEEDS_ONE_HUMAN_CONFIRMATION.
- **Combined SP-02 + SP-13 (diagnostic):** 5 strict rows, 3 fit rows, rank 2, condition number 6.0.
- **Holdout semantics** documented read-only (M6_DECISION_RECORD §18.1); the rule is unchanged.
- **Tests:** `tests/test_sp02_physical_registration.py` (new); `tests/test_sp13_physical_registration.py`
  updated.
- **Abaqus:** 0 solves, 0 extractions. Pairing policy, thresholds, holdouts and modal data unchanged.

## 2026-10-06 — Specimen catalog: authoritative inventory of every real specimen (documentation checkpoint; zero Abaqus)

- **New:**
  - `docs/auto_id/SPECIMEN_CATALOG.md`, the canonical readable specimen reference;
  - `docs/auto_id/specimen_catalog.json`, one deterministic entry per physical specimen with source
    paths, sizes and SHA-256 (not a runtime dependency);
  - `tests/test_specimen_catalog.py`.
- **Sources audited (read-only):**
  - `D:\Snadwich` (primary);
  - `I:\Sumin`: raw batch 260909, PolyMAX zip, LMS summaries;
  - the article project folder (Obsidian specimen vault, reports, photos);
  - `C:\temp\12 sampls`, `C:\temp`, the CARBON archive;
  - all repository records.
- **Results:**
  - 14 physical specimens with records (SP-01 … SP-13, SP-15). SP-14 is AMBIGUOUS (template note only).
  - 5 face families; different families are not merged.
  - SP-06 and SP-15 acquisitions exist outside the store.
  - Ungoverned PolyMAX exports exist for every specimen with an acquisition.
  - SP-01 INP/ODB exists in `C:\temp`.
- **SP-02 identity:** SP02_IDENTITY_RESOLVED_FROM_RECORDS (DERIVED). Evidence: the LMS sheet "SP2 (old)" /
  "SP10 (new SP2)", the spectrum separation, label chronology and lineage. Pending SUPERVISOR. The
  passport is not edited.
- **Contradiction audit:** 21 items. Two are REAL_CONFLICT:
  - C1: a PolyMAX fit of SP-13 260909 exists, against H9; nothing is changed and Σ_setup stays
    provisional;
  - C2: SP-10 260911 is a rotated session.
- **HUMAN questions:** 6, collected in one section; only Q1 touches the M7 path.
- `SNADWICH_INVENTORY.md`: pointer to the catalog and a list of superseded statements; history kept.
- No governed passport, fixture, registration, forward model, baseline, rule or threshold changed.
  0 Abaqus solves, 0 extractions.

## 2026-10-07 — D-065: catalog accepted; SP-02 active on the physical registration; SP-13 260909 PolyMAX frozen (zero Abaqus)

- **DECISIONS:** D-065 records the SUPERVISOR acceptances, the H9 clarification and that Σ_setup stays
  provisional.
- **SP-02:**
  - new active fixture `SP02/bravo-1-physical` (physical registration `9b63f6c8…`);
  - `SP02.physical.specimen.json` takes `physical_specimen_id` "SP-02" and the new fixture;
  - the legacy chain (`SP02/bravo-1`, legacy passport, forward manifest, archived baseline) is unchanged
    as historical provenance;
  - the M2.4 record was regenerated (only the passport hash changed).
- **SP-13 260909:**
  - provenance audit CONFIRMED;
  - frozen FREQUENCY_ONLY record `fixtures/SP13_260909.frozen-modal-set.json` (fixture
    `SP13/260909-bravo-1`, set "Bravo (1)", 9 modes); no refit.
- **Catalog:** status ACCEPTED; C1 resolved (EXPECTED_HISTORICAL); Q1 answered; SP-02/SP-13 entries
  updated.
- **Tests:**
  - new `tests/test_sp13_260909_frozen_modal_set.py`;
  - updated `test_experiment_fixture`, `test_sp02_physical_registration`, `test_specimen_catalog`.
- Σ_setup provisional 0.3 %. M6 not accepted (M6.4). 0 Abaqus solves, 0 extractions.

## 2026-10-07 — M6 — M6.4a: screening envelope and guarded screening path (zero Abaqus)

- **Stage:** M6
- **Mini-step:** M6.4a (M6.4 `IN_PROGRESS`)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m6`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M6.4a): transverse screening envelope, guarded screening path and HUMAN Abaqus manifest (zero Abaqus)`
- **Files changed:**
  - created:
    - `src/domain/transverse_screening.py`, `src/services/transverse_screening.py`;
    - `tools/m6_4_transverse_screening.py`;
    - `tests/test_m6_4_transverse_screening.py`;
    - `docs/auto_id/screening/M6_4_transverse_envelope.json`, `docs/auto_id/screening/README.md`.
  - updated:
    - `src/services/forward_builder.py` (additive screening path);
    - `docs/auto_id/DECISIONS.md` (D-066), `docs/auto_id/M6_DECISION_RECORD.md` (§19);
    - `docs/auto_id/EVIDENCE.md`, `docs/auto_id/ROADMAP.md`, `docs/auto_id/STATUS.json`;
    - `docs/auto_id/forward_models/README.md`.
- **Scientific behaviour changed:** YES, additively: a new screening path. The fitting path,
  parameterisations, thresholds, pairing and M5 rules are unchanged.
- **Decision:** D-066:
  - envelope `LITERATURE_INTERIM_SCREENING_ENVELOPE`;
  - the SPEC §5 rule on the frozen rows;
  - the practical 5–10 % target for M7 interpretation;
  - the D-065 updates accepted as the basis.
- **Tests run:**
  - the full suite on Windows, with and without data stores;
  - `test_m6_4_transverse_screening` (28);
  - a targeted mutation check (6 of 6 killed).
- **Test result:** Windows with the snadwich and carbon-project-archive stores 1511 OK (5 skipped: 3 need the sumin store and pass with it, 24 OK; 2 are Abaqus-gated); without data stores 1502 OK (48 skipped); test_m6_4_transverse_screening 28 OK (24 OK, 1 class skipped without stores)
- **Abaqus run count:** 0 (0 Abaqus Python extractions).
- **Evidence produced:** the HUMAN Abaqus manifest `6d34179c787c8b0e…` (EVIDENCE).
- **Known limitations:**
  - no screening result yet;
  - the classification is local to the CARBON-4C reference point;
  - the M7 propagation mechanism for a budgeted constant is not chosen.
- **Next gate:** SUPERVISOR review of M6.4a. Then the HUMAN Abaqus gate for M6.4b: 16 solves and
  16 extractions under manifest `6d34179c787c8b0e…`.

## 2026-10-08 — M6 — M6.4b: transverse-constant screening result; M6 gate evaluated (HUMAN Abaqus gate)

- **Stage:** M6
- **Mini-step:** M6.4b (M6.4 `REVIEW_READY`; M6.4a ACCEPTED, D-067)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m6`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M6.4b): transverse-constant screening result - all five NEGLIGIBLE_FOR_BUDGET; M6 gate evaluated`
- **Files changed:**
  - created:
    - `docs/auto_id/screening/M6_4_transverse_screening_result.json`;
    - `docs/auto_id/screening/M6_4_run_evidence.json`;
    - `tests/test_m6_4_screening_result.py`.
  - updated:
    - `docs/auto_id/DECISIONS.md` (D-067), `docs/auto_id/M6_DECISION_RECORD.md` (§20);
    - `docs/auto_id/EVIDENCE.md`, `docs/auto_id/ROADMAP.md`, `docs/auto_id/STATUS.json`;
    - `docs/auto_id/screening/README.md`.
- **Scientific behaviour changed:** NO. The tool is unchanged from `403ff94`; this mini-step only records the
  result.
- **Tests run:**
  - the M6.4 tests, the M6 tests, the M5 gate, the M4 guard and gates, the M3 gate;
  - the full suite on Windows, with and without data stores;
  - the result reproduction from the run store.
- **Test result:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run) 1516 OK (2 Abaqus-gated skipped); without data stores 1507 OK (49 skipped); targeted M6.4 + M6 + M5 gate + M4 guard/gate + M3 gate 152 OK; result reproduction from the run store OK
- **Abaqus run count:** 16 solves and 16 Abaqus Python extractions (HUMAN gate D-067; 0 failures, 0 retries).
- **Evidence produced:** EVIDENCE "M6.4b". All five constants are `NEGLIGIBLE_FOR_BUDGET` (max 0.0353 %);
  the M6 gate worker evaluation is PASS.
- **Known limitations:**
  - the classification is local to the CARBON-4C reference point;
  - the open items, which are not gate conditions, are listed in M6_DECISION_RECORD §20.
- **Next gate:** SUPERVISOR review of M6.4b and of the M6 gate. Then the M6 stage PR. A merge needs explicit
  HUMAN authorisation. M7 NOT_STARTED.

## 2026-10-08 — M6 — D-068: M7-entry wiring of the active SP-02 / SP-13 inputs; M6 closure record (zero Abaqus)

- **Stage:** M6 (closure preparation)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m6`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M6): D-068 - active SP-02/SP-13 inputs on the physical registrations; M6 closure record (zero Abaqus)`
- **Decision:** D-068:
  - M6.4b accepted, M6.4 CLOSED;
  - the M7-entry wiring of the active inputs only;
  - the M6 closure record, with the M6 gate a PASS candidate.
- **Files changed:**
  - created:
    - `docs/auto_id/forward_models/SP02.physical.forward.json`, `docs/auto_id/forward_models/SP13.physical.forward.json`;
    - `tests/test_m7_entry_wiring.py`.
  - updated:
    - `docs/auto_id/fixtures/real_experiment_fixtures.json` (new fixture `SP13/best-physical`; insertion only);
    - `docs/auto_id/specimens/SP13.physical.specimen.json` (`acquisition.fixture_id`);
    - `docs/auto_id/registration_evidence/SP13_registration_uncertainty.json` (regenerated; passport hash only);
    - `tests/test_experiment_fixture.py`, `tests/test_sp13_physical_registration.py`, `tests/test_specimen_catalog.py`;
    - `docs/auto_id/SPECIMEN_CATALOG.md`, `docs/auto_id/specimen_catalog.json`;
    - DECISIONS, M6_DECISION_RECORD (§21), EVIDENCE, ROADMAP, STATUS;
    - the fixtures, forward-model and specimens READMEs.
- **Scientific behaviour changed:** NO. These are new governed bindings. The frozen M0–M5 records, legacy chains
  and rules are unchanged (54 content hashes compared, 0 changed).
- **Tests run:** the full suite on Windows, with and without data stores; the wiring, fixture, registration,
  catalog, forward, M3/M4/M5 gate and M6.4 tests.
- **Test result:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run) 1522 OK (2 Abaqus-gated skipped); without data stores 1513 OK (56 skipped); wiring + fixture + registration + catalog + forward + M3/M4/M5 gate + M6.4 tests included
- **Abaqus run count:** 0 (no identification run).
- **Next gate:** SUPERVISOR review of D-068 and final M6 acceptance. Then the M6 stage PR; a merge needs
  explicit HUMAN authorisation. M7 NOT_STARTED.

## 2026-10-08 — M6 — SUPERVISOR acceptance and stage closure; stage PR prepared

- **Stage:** M6
- **Status:** ACCEPTED (SUPERVISOR 2026-10-08). M6 gate PASS. Stage PR `auto-id/m6` → `main` prepared, not
  merged.
- **Branch:** `auto-id/m6`
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): M6 SUPERVISOR acceptance and stage closure`
- **Accepted scope:**
  - M6.1, M6.2 and M6.3 are `NOT_AVAILABLE_WITH_CURRENT_SETUP` (intentional);
  - M6.4 is `ACCEPTED` (M6.4a + M6.4b): E3, ν13, ν23, G13, G23 are `NEGLIGIBLE_FOR_BUDGET` and stay fixed;
  - the active fixtures are `SP02/bravo-1-physical` and `SP13/best-physical`; the legacy registrations are
    historical;
  - Σ_setup 0.3 % PROVISIONAL, Σ_meas NOT_AVAILABLE.
- **Files changed:** `docs/auto_id/STATUS.json`, `ROADMAP.md`, `CHANGELOG.md`, `M6_DECISION_RECORD.md` (§22) and
  `EVIDENCE.md` (governance records only).
- **Scientific behaviour changed:** NO (docs only).
- **Verification before the PR:** no Abaqus artifacts; M3/M4 changes additive only; no M5 change; frozen M0–M5
  records unchanged.
- **Test result:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run) 1522 OK (2 Abaqus-gated skipped); without data stores 1513 OK (56 skipped); M6 test modules 143 OK; M5 + M4 + M3 stage gates and M4 guard 34 OK
- **Abaqus run count:** 0.
- **Limitations kept:** see M6_DECISION_RECORD §22.
- **Next gate:** HUMAN merge authorisation for the stage PR. After the merge, the `main` merge SHA is recorded.
  M7 `NOT_STARTED`.

## 2026-10-08 — M6 — merged to `main` (PR #35)

- **Stage:** M6
- **Status:** ACCEPTED and merged. The merge was explicitly authorised by the HUMAN supervisor.
- **Branch:** `auto-id/m6-closure` (from `main` `f1274ca`)
- **Merge:** PR #35 `auto-id/m6` → `main`, merge commit `f1274cae80a6b3972cef04fd9c1bee0505920311`.
  - Reviewed head: `e5f3fbc14cb71b2281c5a7bc1aaef88f08d9cfc6`.
  - The merged tree equals the reviewed head.
- **Recorded:** `STATUS.json`: `last_accepted_stage` M6, `main_merges` += M6 / PR #35, and the M6 `stage_pr`,
  `merged_to_main`, `accepted_head` and `accepted_by` fields.
- **CI:** Linux CI on the reviewed head e5f3fbc: 1510 OK (60 skipped); on main f1274ca: 1510 OK (60 skipped), success
- **Limitations kept:** see M6_DECISION_RECORD §22.
- **Abaqus run count:** 0. Docs only.
- **Next:** M7 `NOT_STARTED`. No M7 branch and no M7 records; the next step needs SUPERVISOR instruction.

## 2026-10-08 — M7 — M7.1: RUN_A campaign architecture (zero Abaqus)

- **Stage:** M7 (opened by D-069)
- **Mini-step:** M7.1
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m7` (from `main` `9f5f63a968759d6237facda00a4415cfe29c2257`)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): RUN_A campaign architecture - two-specimen shared E_in on the active physical chains (zero Abaqus)`
- **Decision:** D-069 (the accepted M7.1 design; RUN_A first; RUN_B gated).
- **Files changed:**
  - created:
    - `src/domain/campaign_definition.py`, `src/services/identification_campaign_run.py`;
    - `tools/m7_campaign.py`;
    - `tests/test_m7_campaign.py`;
    - `docs/auto_id/campaigns/M7_RUN_A.campaign.json`, `docs/auto_id/campaigns/M7_RUN_A.archive-reuse.json`,
      `docs/auto_id/campaigns/README.md`;
    - `docs/auto_id/M7_DECISION_RECORD.md`.
  - updated:
    - `src/services/identification_objective.py` (additive: `RowSigma(measurement_sd=None)` =
      NOT_AVAILABLE);
    - DECISIONS (D-069), EVIDENCE, ROADMAP, STATUS.
- **Scientific behaviour changed:** YES, additively:
  - a new campaign path;
  - the M4.7 NOT_AVAILABLE Σ_meas representation.
  The M4/M5 rules, thresholds and existing hashes are unchanged.
- **Tests run:**
  - `test_m7_campaign`;
  - the M6 regression and gate tests;
  - the M5 gate, the M4 gate and guard, the M3 gate;
  - the full suite on Windows, with and without data stores;
  - a targeted mutation check (9 of 9 killed).
- **Test result:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run) 1550 OK (2 Abaqus-gated skipped); without data stores 1537 OK (57 skipped); test_m7_campaign 28 OK (4 store-gated); M6 regression and gate modules 143 OK; M5 / M4 / M3 stage gates, M4 guard, M4.7 objective and M4.6 pipeline 62 OK
- **Abaqus run count:** 0 (0 Abaqus Python extractions, no LM run).
- **Evidence produced:** the proposed RUN_A manifest `e4ba607f06a69311…` (EVIDENCE).
- **Known limitations:**
  - family consistency (SPEC §13 / M7.4) is NOT_AVAILABLE, so no green M5 verdict is possible;
  - the M4.3 thresholds are PROVISIONAL;
  - Σ_setup is provisional;
  - "not externally validated" applies.
- **Next gate:** SUPERVISOR review of M7.1. Then the HUMAN gates: archive extraction, then the RUN_A run.

## 2026-10-08 — M7 — RUN_A HUMAN gate 1: archived SP-02 CARBON-5A extraction

- **Stage:** M7
- **Mini-step:** M7.1 (ACCEPTED, D-070); RUN_A gate 1
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m7`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): RUN_A gate 1 - archived SP-02 CARBON-5A extraction (2 Abaqus Python, 0 solves)`
- **Decision:** D-070 (M7.1 accepted; gate 1 authorised for manifest `e4ba607f06a69311…`).
- **Files changed:**
  - created: `docs/auto_id/campaigns/M7_RUN_A.archive-extraction.json`,
    `docs/auto_id/campaigns/archive_extraction/SP02_13363f977809dbff.shape-pack.json` and
    `SP02_84753f636064e192.shape-pack.json`, `tests/test_m7_archive_extraction.py`;
  - updated: DECISIONS (D-070), EVIDENCE, M7_DECISION_RECORD (§4), STATUS.
- **Scientific behaviour changed:** NO. No code changed; the governed result is recorded.
- **Abaqus run count:** 0 solves, 2 Abaqus Python extractions (gate 1).
- **Result:**
  - both packs validate; their frequencies equal CARBON-5A exactly; tracking MAC ≥ 0.999998;
  - the manifest is unchanged (`e4ba607f06a69311…`); the run identity is `8ed03be3be86aa83…`;
  - the solve budget remaining is 16 of 16.
- **Test result:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a) 1554 OK (2 Abaqus-gated skipped); without data stores 1541 OK (58 skipped); test_m7_archive_extraction 4 OK (1 store-gated) + test_m7_campaign 28 OK
- **Next gate:** HUMAN gate 2 (RUN_A solves). RUN_A and RUN_B are not started.

## 2026-10-08 — M7 — RUN_A executed (HUMAN gate 2): shared E_in for SP-02 + SP-13

- **Stage:** M7
- **Mini-step:** RUN_A (M7.1 campaign)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m7`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): RUN_A result - shared E_in 55.6 GPa, EFFECTIVE_MODEL_PARAMETER_ESTIMATE, M5 NOT_IDENTIFIABLE`
- **Decision:** D-071 (gate 1 accepted; RUN_A authorised for manifest `e4ba607f06a69311…`, run `8ed03be3be86aa83…`).
- **Files changed:**
  - created: `docs/auto_id/campaigns/M7_RUN_A.result.json`, `tests/test_m7_run_a_result.py`;
  - updated: DECISIONS (D-071), EVIDENCE, M7_DECISION_RECORD (§5), ROADMAP, STATUS.
- **Scientific behaviour changed:** NO. No code changed; the result is recorded.
- **Abaqus run count:** 2 solves and 2 extractions (gate 2). With gate 1, the RUN_A totals
  are 2 solves and 4 Abaqus Python extractions.
- **Result:**
  - CONVERGED; Ê_in = 55593 MPa; max |error| 6.79 % (all within 10 %, not all
    within 5 %); minimum tracking MAC 0.999997.
  - `EFFECTIVE_MODEL_PARAMETER_ESTIMATE`; M5 NOT_IDENTIFIABLE (family consistency NOT_AVAILABLE; holdout
    `SP02:R3`; Birge blocked); not externally validated.
- **Test result:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a) 1559 OK (2 Abaqus-gated skipped); without data stores 1546 OK (59 skipped); test_m7_run_a_result 5 OK (1 store-gated; the report rebuilds identically from the run journals)
- **Next gate:** SUPERVISOR review of RUN_A. RUN_B only under its own later gate.

## 2026-10-08 — M7 — RUN_A closed; RUN_B prepared (archive reuse only, zero Abaqus)

- **Stage:** M7
- **Status:** REVIEW_READY (RUN_B preparation); RUN_A ACCEPTED and CLOSED
- **Branch:** `auto-id/m7`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): RUN_A closed; RUN_B prepared - EFFECTIVE_MODEL_COMPENSATION_TEST manifest (zero Abaqus)`
- **Decision:** D-072.
- **Files changed:**
  - created:
    - `docs/auto_id/campaigns/M7_RUN_B.campaign.json` (`7c1f5db24fa9c4f4…`);
    - `docs/auto_id/campaigns/M7_RUN_B.archive-reuse.json` (`fa19cfbb4f818c66…`);
    - `tests/test_m7_run_b_preparation.py`.
  - updated:
    - `src/domain/campaign_definition.py` (optional `pack_store` on a reused pack);
    - `src/services/identification_campaign_run.py` (store override with unchanged pins; RUN_B report label,
      G12 compensation role, Δ ln comparison with descriptive D-045 bands);
    - `tools/m7_campaign.py` (`--campaign run-a | run-b`);
    - DECISIONS (D-072), EVIDENCE, M7_DECISION_RECORD (§6), ROADMAP, STATUS, `campaigns/README.md`.
- **Scientific behaviour changed:** YES, additively: RUN_B report semantics and the store override. The RUN_A
  records and hashes are unchanged.
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a, m7-run-a-archive) 1570 OK (2 Abaqus-gated skipped); without data stores 1556 OK (60 skipped); test_m7_run_b_preparation 12 OK (1 store-gated class) and the M7 suites 48 OK
- **Abaqus run count:** 0.
- **Proposed RUN_B manifest:** `5fd0946a0c3f4e20…`.
- **Next gate:** HUMAN gate for the 2 SP-02 G12± archive extractions, then the HUMAN RUN_B solve gate.

## 2026-10-08 — M7 — RUN_B HUMAN gate 1: archived SP-02 G12± extraction (0 solves)

- **Stage:** M7
- **Mini-step:** RUN_B gate 1 (M7.1 campaign)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m7`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): RUN_B gate 1 - archived SP-02 G12 extraction (2 Abaqus Python, 0 solves)`
- **Decision:** D-073.
- **Files changed:**
  - created: `docs/auto_id/campaigns/M7_RUN_B.archive-extraction.json`,
    `docs/auto_id/campaigns/archive_extraction/SP02_05239a3b56508244.shape-pack.json`,
    `docs/auto_id/campaigns/archive_extraction/SP02_ade5dffa2fde3903.shape-pack.json`,
    `tests/test_m7_run_b_archive_extraction.py`;
  - updated: DECISIONS (D-073), EVIDENCE, M7_DECISION_RECORD (§7), ROADMAP, STATUS, `campaigns/README.md`.
- **Scientific behaviour changed:** NO. No code changed; the extraction is recorded.
- **Abaqus run count:** 0 solves, 2 Abaqus Python extractions.
- **Manifest:** `5fd0946a0c3f4e20562ba97068cdb5b94bf6d10ba789a3b2df20b457882034a1` (unchanged). RUN_B run identity `fb5234116c6e9413e4b070e901f97b8c6e210d535daefe15f0cdb5b9f8ad87f0`.
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a, m7-run-a-archive, m7-run-b) 1574 OK (2 Abaqus-gated skipped); without data stores 1560 OK (61 skipped); test_m7_run_b_archive_extraction 4 OK (1 store-gated; packs re-verified and re-tracked from the RUN_B run store)
- **Next gate:** HUMAN RUN_B solve gate (not started).

## 2026-10-08 — M7 — RUN_B result: EFFECTIVE_MODEL_COMPENSATION_TEST (diagnostic)

- **Stage:** M7
- **Mini-step:** RUN_B (M7.1 campaign)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m7`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): RUN_B result - compensation test, G12 +52.7 %, E_in -8.5 %, M5 NOT_IDENTIFIABLE`
- **Decision:** D-074 (gate 1 accepted; RUN_B authorised for manifest `5fd0946a0c3f4e20…`, run `fb5234116c6e9413…`).
- **Files changed:**
  - created: `docs/auto_id/campaigns/M7_RUN_B.result.json`, `tests/test_m7_run_b_result.py`;
  - updated: DECISIONS (D-074), EVIDENCE, M7_DECISION_RECORD (§8), ROADMAP, STATUS, `campaigns/README.md`.
- **Scientific behaviour changed:** NO. No code changed; the result is recorded.
- **Abaqus run count:** 6 solves and 6 extractions (budget 24; 0 failures). With gate 1, the RUN_B totals are
  6 solves and 8 Abaqus Python extractions.
- **Result (diagnostic):** CONVERGED; E_in = 50886.2 MPa (-8.47 % vs RUN_A),
  G12 = 6872.1 MPa (+52.71 %); max |error| 4.17 %; minimum tracking MAC
  0.999834; M5 NOT_IDENTIFIABLE for both; G12 a compensation diagnostic; not externally validated.
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a, m7-run-a-archive, m7-run-b) 1581 OK (2 Abaqus-gated skipped); without data stores 1567 OK (62 skipped); test_m7_run_b_result 7 OK (1 store-gated; the report rebuilds identically from the RUN_B journals)
- **Next gate:** SUPERVISOR review of RUN_B. No further fit; M7 not merged.

## 2026-10-08 — M7 — RUN_B accepted; reporting correction; M7 closure prepared

- **Stage:** M7
- **Mini-step:** M7 closure
- **Status:** REVIEW_READY (stage)
- **Branch:** `auto-id/m7`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): M7 closure - RUN_B accepted, model_form_robustness reporting status, campaign complete`
- **Decision:** D-075.
- **Files changed:**
  - created: `docs/auto_id/campaigns/M7_CLOSURE.json`, `tests/test_m7_closure.py`;
  - updated: `src/services/identification_campaign_run.py` (campaign-layer `model_form_robustness_reporting`;
    report field `model_form_robustness`), `tests/test_m7_campaign.py`, `tests/test_m7_run_a_result.py`,
    `tests/test_m7_run_b_result.py`, DECISIONS (D-075), EVIDENCE, M7_DECISION_RECORD (§9), ROADMAP, STATUS,
    `campaigns/README.md`.
- **Scientific behaviour changed:** reporting only (additive report field). M5 thresholds, algorithms,
  verdicts and records unchanged; accepted result records unchanged.
- **Abaqus run count:** 0.
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a, m7-run-a-archive, m7-run-b) 1592 OK (2 Abaqus-gated skipped); without data stores 1578 OK (62 skipped); all M7 modules 70 OK with stores (RUN_A and RUN_B reports rebuilt from the journals; archive-extraction evidence re-verified); test_m7_closure 11 OK; M6 regression and gate modules 210 OK (2 Abaqus-gated skipped); M5 gate, verdict, robustness, uncertainty and identifiability 68 OK; M4 gate, guard, step, objective, pipeline, twin and SP13 readiness 102 OK; M3 gate 2 OK
- **Next gate:** SUPERVISOR review of the M7 stage PR. Not merged; M8 not started.

## 2026-10-08 — M7 — closure: result-record binding made platform-independent

- **Stage:** M7
- **Mini-step:** M7 closure (correction)
- **Status:** REVIEW_READY (stage)
- **Branch:** `auto-id/m7`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7.1): M7 closure - bind result records by canonical content hash`
- **Decision:** D-075.
- **Files changed:** `docs/auto_id/campaigns/M7_CLOSURE.json` (`canonical_content_sha256` instead of the
  checkout-dependent byte SHA-256), `tests/test_m7_closure.py`, EVIDENCE.
- **Reason:** Linux CI on `5ed6cf0`: byte hashes of CRLF working copies differ from the LF blobs.
- **Scientific behaviour changed:** NO.
- **Abaqus run count:** 0.
- **Tests:** test_m7_closure 11 OK; full suites in the stage PR report.
- **Known limitation:** pre-existing flaky `test_registration_factory` token check (unrelated; not changed).

## 2026-10-08 — M7 — merged to `main` (PR #37)

- **Stage:** M7
- **Status:** ACCEPTED, M7 gate PASS (SUPERVISOR 2026-10-08). The merge was explicitly authorised by the HUMAN
  supervisor.
- **Branch:** `auto-id/m7-closure` (from `main` `0f15db9`)
- **Merge:** PR #37 `auto-id/m7` → `main`, merge commit `0f15db9acf29b7d3a7b20350982440015e177e94`.
  - Reviewed head: `87c05da051abb272a8f52eb579bcca0ce180f12b`.
  - The merged tree equals the reviewed head.
- **Recorded:** `STATUS.json`: `status` ACCEPTED, `last_accepted_stage` M7, `main_merges` += M7 / PR #37, the M7
  `status`, `gate`, `merged_to_main`, `accepted_head`, `accepted_by`, `merge_ci` fields, M7.2–M7.8, and
  `m8.status` NOT_STARTED. `ROADMAP.md`: M7 stage status ACCEPTED / gate PASS with PR #37 and the merge SHA;
  M8 stage status NOT_STARTED.
- **M7.2–M7.8:** `NOT_PURSUED_IN_M7` (D-075), confirmed by the SUPERVISOR: superseded by the D-075 M7 stage conclusion and not required for M7 acceptance. Not DONE.
- **CI:** Linux CI on the reviewed head 87c05da: 1575 OK (66 skipped), success (run 37783691289); on main 0f15db9: 1575 OK (66 skipped), success (run 37784347770)
- **Scientific results unchanged:** RUN_A E_in,eff = 55.593 GPa, `EFFECTIVE_MODEL_PARAMETER_ESTIMATE`, not
  externally validated, M5 NOT_IDENTIFIABLE (50.8–60.3 GPa only as `MODEL_DEPENDENCE_DIAGNOSTIC`); RUN_B
  diagnostic only (E_in 50.886 GPa, G12 6.872 GPa as `COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY`). Result
  records, `M7_CLOSURE.json` and the run journals are unchanged.
- **Abaqus run count:** 0. Docs only.
- **Next:** M8 `NOT_STARTED`. No M8 branch; the next step needs SUPERVISOR instruction.

## 2026-10-08 — M6 — ROADMAP stage-status line brought up to date

- **Stage:** M6 (bookkeeping only; recorded with the M7 closure, PR #38)
- **Branch:** `auto-id/m7-closure`
- **Change:** `ROADMAP.md` M6 stage status no longer reads "stage PR … prepared, not merged; M7 `NOT_STARTED`".
  It now records the factual state: M6 `ACCEPTED`, M6 gate PASS, merged to `main` by PR #35, merge commit
  `f1274cae80a6b3972cef04fd9c1bee0505920311` (as already recorded in `STATUS.json` `main_merges` since PR #36).
- **Scientific behaviour changed:** NO. No M6 result, evidence, decision or scientific text changed.
- **Abaqus run count:** 0. Docs only.

## 2026-10-09 — M7 — M7b-DIAG: external audit iteration 2 corrective diagnostics (D-076)

- **Stage:** M7 (REWORK)
- **Mini-step:** M7b-DIAG (audit corrective)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m7b-diag` (from `main` `7a34ee65f8a036866961c10dbd685a44ec957671`)
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7b): audit iteration 2 corrective - SPEC 13 family consistency FAIL, no global E released, CARBON-5G`
- **Decision:** D-076 (supersedes the release interpretation of D-069 / D-072 / D-075; M7 gate FAIL).
- **Files changed:**
  - created: `src/services/family_consistency.py`, `src/services/campaign_diagnostics.py`,
    `src/domain/physical_measurements.py`, `tests/test_m7b_corrective.py`,
    `docs/auto_id/audit_corrections/` (4 records), `docs/auto_id/specimens/SP0x.physical-measurements.json`;
  - updated: `src/services/identification_campaign_run.py` (SPEC §13 guard; report v2), `src/domain/campaign_definition.py`
    (optional identity-bound `family_consistency` policy), `tools/m7_campaign.py`, `tests/test_m7_campaign.py`,
    `tests/test_m7_run_a_result.py`, `tests/test_m7_run_b_result.py`, DECISIONS (D-076), EVIDENCE,
    M7_DECISION_RECORD (§10), ROADMAP, STATUS.
- **Scientific behaviour changed:** YES. The campaign verdict now evaluates SPEC §13 instead of a hard-coded
  NOT_AVAILABLE; the report no longer presents an unreleased optimiser output as an effective estimate. M5
  thresholds unchanged; no gate weakened.
- **Result:** RUN_A family consistency FAIL (Δχ² 746.27, Δdof 1, p_χ² 2.6e-164, bootstrap p 0.00025 (4000 samples, seed 20261009)); RUN_B NOT_EVALUABLE_RANK_DEFICIENT; no global E_in released.
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a, m7-run-a-archive, m7-run-b) 1616 OK (2 Abaqus-gated skipped); without data stores 1602 OK (64 skipped); test_m7b_corrective 23 OK (store-gated: spec.txt source lines, live excluded-mode diagnostics); M7 modules with stores 94 OK (RUN_A / RUN_B rebuilt from the journals: unchanged except the D-076 family-consistency and release fields); M5 gate, verdict, robustness, uncertainty, identifiability 68 OK; M4 gate, guard, step, objective, pipeline, twin, SP13 readiness 102 OK; M3 gate 2 OK
- **Abaqus run count:** 0 solves, 0 Abaqus Python extractions.
- **Unchanged:** RUN_A / RUN_B result records and journals; passports, registrations, fixtures, freezes, mode pairs;
  SPEC v1.1; branch `auto-id/m8` (parked).
- **Next gate:** SUPERVISOR review of the corrective diagnostics; SPEC v1.2 / τ_mf are HUMAN decisions.

## 2026-10-09 — M7 — M7b: SUPERVISOR review corrections before PR (D-076)

- **Stage:** M7 (REWORK)
- **Mini-step:** M7b-DIAG (review corrections)
- **Status:** REVIEW_READY
- **Branch:** `auto-id/m7b-diag`
- **Commit SHA:** the commit that introduces this entry, message
  `auto-id(M7b): review corrections - refusal is not a failed gate, full audit disposition, J5 uncertainty basis`
- **Changes:**
  - gate semantics: family consistency FAIL / NO_GLOBAL_PARAMETER_VALUE kept apart from the stage gate; STATUS
    `m7.gate` = `PENDING_SUPERVISOR_CLOSURE` (expected `PASS_BY_REFUSAL`); the "M7 gate FAIL" wording of the previous
    M7b entry is superseded; D-076 (unmerged, under review) clarified accordingly;
  - `AUDIT_ITERATION2_DISPOSITION.md`: K3 hypothesis narrowed (SP-13 0.425 mm is in its INP); V1–V8 and J1–J5
    dispositioned from the supplied audit text;
  - J5: campaign report `uncertainty_basis` (reporting only) with a regression test.
- **Scientific behaviour changed:** reporting only (`uncertainty_basis`). Family-consistency numbers unchanged.
- **Tests:** Windows with all stores (snadwich, carbon-project-archive, sumin, m6-4-screening-run, m7-run-a, m7-run-a-archive, m7-run-b) 1617 OK (2 Abaqus-gated skipped); without data stores 1603 OK (64 skipped); M7 and corrective modules with stores 95 OK (incl. test_m7b_corrective 24 OK; RUN_A / RUN_B rebuilt from the journals); M5 gate, verdict, robustness, uncertainty, identifiability 68 OK; M4 gate, guard, step, objective, pipeline, twin, SP13 readiness 102 OK; M3 gate 2 OK
- **Abaqus run count:** 0.
- **Next gate:** SUPERVISOR review of the M7b PR; stage-gate closure as a separate decision.

## 2026-10-09 — M7 — M7b: cross-platform tolerance in the corrective record tests

- **Branch:** `auto-id/m7b-diag`
- **Commit SHA:** the commit that introduces this entry, message
  `test(M7b): compare corrective family-consistency records within floating-point tolerance`
- **Reason:** Linux CI on `59fef94`: the family-consistency Δχ² differs from the Windows-generated record in the last
  digit (`…853167` vs `…853168`; numpy / BLAS builds). The test compared floats exactly.
- **Change:** `tests/m7b_support.assert_records_close` (structure and text exact, floats rel 1e-9), used in
  `test_m7b_corrective`, `test_m7_run_a_result`, `test_m7_run_b_result`. No code or record changed; the result is the
  same (RUN_A FAIL, Δχ² 746.27).
- **Tests:** Windows M7 and corrective modules with stores 95 OK; full suite without data stores 1603 OK (64 skipped).
- **Abaqus run count:** 0.

## 2026-10-09 — M7 — M7b corrective merged (PR #39); M7 closed by D-077

- **Stage:** M7
- **Status:** ACCEPTED (D-077); M7 stage gate PASS (PASS_BY_REFUSAL). The PR #39 merge was explicitly authorised by
  the HUMAN supervisor.
- **Branch:** `auto-id/m7b-closure` (from `main` `b9db2c1`)
- **Merge:** PR #39 `auto-id/m7b-diag` → `main`, merge commit `b9db2c1bc5c281d8f126ffe9f2abfec4dbd60e2c`.
  - Reviewed head: `42d8f2ff7b98b12e6f5cde99cdd22f1d82ff3f7d`; the merged tree equals the reviewed head.
- **Recorded:** D-077; `STATUS.json`: `status` ACCEPTED, `last_accepted_stage` M7 (`last_accepted_commit` `b9db2c1`),
  `main_merges` += M7 corrective / PR #39, M7 `gate` PASS with `gate_semantics` PASS_BY_REFUSAL, `family_consistency`
  FAIL, `formal_output` NO_GLOBAL_PARAMETER_VALUE, `m8` parked status; ROADMAP M7 / M8 stage status;
  M7_DECISION_RECORD §11.
- **Scientific results unchanged:** RUN_A family consistency FAIL (Δχ² ≈ 746.27, Δdof 1); RUN_B
  NOT_EVALUABLE_RANK_DEFICIENT; formal output NO_GLOBAL_PARAMETER_VALUE; 55.593 GPa historical optimiser evidence only;
  no new material property.
- **CI:** Linux CI on the reviewed head 42d8f2f: 1600 OK (68 skipped), success (run 37821433187); on main b9db2c1: 1600 OK (68 skipped), success (run 37825521366)
- **Tests:** docs-only closure: Windows M7, corrective, M5 / M4 / M3 gate modules with stores 125 OK (family consistency still FAIL; formal output NO_GLOBAL_PARAMETER_VALUE; RUN_A / RUN_B rebuilt from the journals); full suite without data stores 1603 OK (64 skipped); governance check 12/12 PASS
- **Abaqus run count:** 0. Docs only.
- **Next:** M8 `NOT_STARTED`; `auto-id/m8` parked (`PARKED_PENDING_POST_M7_DECISION`); SPEC v1.2 / τ_mf /
  SPECIMEN_ENGINEERING_CALIBRATION are future SUPERVISOR decisions.

## 2026-10-09 — Policy — SPEC v1.2 policy freeze draft (PROPOSED; M7 closure merged)

- **M7 closure merge:** PR #40 `auto-id/m7b-closure` → `main`, merge commit `9bff6c79ee149e9309c3e3697cb96fff4e937c68` (reviewed head `f4c1ba4`,
  merged tree identical; HUMAN-authorised). Linux CI on main 9bff6c7: 1600 OK (68 skipped), success (run 37828742325).
- **Stage:** policy track (no roadmap stage started; M8 NOT_STARTED)
- **Status:** REVIEW_READY (proposal; not normative)
- **Branch:** `auto-id/spec-v1.2-policy` (from `main` `9bff6c7`)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): SPEC v1.2 policy freeze draft - tau_mf, specimen calibration class (proposed, not normative)`
- **Files:** created `docs/auto_id/SPEC_V1_2_DRAFT.md`, `docs/auto_id/SPEC_V1_2_POLICY_REVIEW.md`,
  `docs/auto_id/SPEC_V1_2_POLICY_OPTIONS.json`, `tests/test_spec_v1_2_policy_draft.py`; updated STATUS, ROADMAP,
  CHANGELOG.
- **Content:** τ_mf options A (2 %, recommended as specification maximum), B (3 %), C (per family, rejected); holdout
  and pattern bounds max(3σ, τ_mf) / max(2σ, τ_mf); §13 explicitly τ_mf-free; drafted SPECIMEN_ENGINEERING_CALIBRATION
  class (conditions, minimum observability k + 1 FIT families + 1 holdout, non-degradation rule A); S8 output
  separation; mandatory uncertainty-basis wording. Declared before any new FE result; no historical data used.
- **Scientific behaviour changed:** NO. SPEC v1.1 unchanged; M5, M7 records and the family-consistency implementation
  unchanged.
- **Tests:** test_spec_v1_2_policy_draft 6 OK; test_m7b_corrective + M5 gate + policy 39 OK; full suite without data stores 1609 OK (64 skipped)
- **Abaqus run count:** 0.
- **Next gate:** SUPERVISOR decision on the draft.

## 2026-10-09 — Policy — SPEC v1.2 policy draft revised after SUPERVISOR policy decision (PROPOSED)

- **Stage:** policy track (no roadmap stage started; M8 NOT_STARTED)
- **Status:** REVIEW_READY (revised proposal; not normative; no decision number assigned)
- **Branch:** `auto-id/spec-v1.2-policy` (previous commit `72524ae`)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): SPEC v1.2 policy revision - amended upper rule, no fallback, tau_mf frequency-only, max+RMS non-degradation (proposed)`
- **Files:** updated `docs/auto_id/SPEC_V1_2_DRAFT.md`, `docs/auto_id/SPEC_V1_2_POLICY_REVIEW.md`,
  `docs/auto_id/SPEC_V1_2_POLICY_OPTIONS.json` (schema v2), `tests/test_spec_v1_2_policy_draft.py`; STATUS, ROADMAP,
  CHANGELOG.
- **Content:** §1 amended (A material identification / B specimen-FE-model calibration, pre-declared and
  identity-bound; no automatic fallback; material verdict always computed and shown separately). τ_mf Option A
  (0.02 specification maximum, one campaign-level predeclared identity-bound value); the "2 % ⇒ ~4 % in E" argument and
  `implied_min_parameter_scale_ln_e` withdrawn — τ_mf is a frequency-space model-form tolerance only and passing it does
  not establish parameter precision. §13 unchanged and τ_mf-free. Calibration labels, identities, gates (no override,
  no post-hoc mode substitution, no lowered MAC) and uncertainty reporting (τ_mf as ACCEPTANCE_TOLERANCE;
  UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE). Non-degradation: max AND RMS not worse AND every row ≤ 8 %.
  Observability: k + 1 FIT families, full rank, complete leave-one-FIT-family-out, ≥ 1 HOLDOUT (k = 1: 2 FIT + 1
  HOLDOUT). Historical RUN_A / RUN_B unchanged; RETROSPECTIVE_DIAGNOSTIC_ONLY after v1.2; a new v1.2 identity is needed
  for an accepted calibration.
- **Scientific behaviour changed:** NO. SPEC v1.1 unchanged; no production source changed.
- **Tests:** test_spec_v1_2_policy_draft 10 OK; test_m7b_corrective + test_m5_stage_gate + policy 43 OK (2 skipped without data stores); full suite without data stores 1613 OK (64 skipped)
- **Abaqus run count:** 0.
- **Next gate:** final SUPERVISOR acceptance of the revised draft.

## 2026-10-09 — Policy — SPEC v1.2 final correction: calibration precision gate (PROPOSED; policy PR)

- **Stage:** policy track (no roadmap stage started; M8 NOT_STARTED)
- **Status:** REVIEW_READY (proposal; normative only after SUPERVISOR merge acceptance; no decision number assigned)
- **Branch:** `auto-id/spec-v1.2-policy` (previous commit `06a6162`)
- **Commit SHA:** the commit that introduces this entry, message
  `docs(auto-id): SPEC v1.2 calibration precision gate - conservative uncertainty <= 0.08 (proposed)`
- **Files:** updated `docs/auto_id/SPEC_V1_2_DRAFT.md`, `docs/auto_id/SPEC_V1_2_POLICY_REVIEW.md`,
  `docs/auto_id/SPEC_V1_2_POLICY_OPTIONS.json`, `tests/test_spec_v1_2_policy_draft.py`; STATUS, CHANGELOG.
- **Content:** mandatory calibration gate `conservative_uncertainty = max(birge_adjusted_sd,
  0.5 * width(model_form_robustness)) ≤ 0.08` (ln p, the M5 envelope concept). birge_adjusted_sd must be available and
  model_form_robustness AVAILABLE_COMPLETE_LOO, otherwise REFUSED; > 0.08 REFUSED. A refused calibration releases no
  value; an optimiser candidate may stay visible only as DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE. Never
  labelled IDENTIFIED / WIDE. τ_mf is not part of the envelope. With incomplete covariance the ≤ 0.08 result stays
  UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE. Nothing else redesigned.
- **Scientific behaviour changed:** NO. SPEC v1.1, DECISIONS, production source, M5, M7 records and the
  family-consistency implementation unchanged.
- **Tests:** test_spec_v1_2_policy_draft 16 OK; test_m7b_corrective + test_m5_stage_gate + policy 49 OK (2 skipped without data stores); full suite without data stores 1619 OK (64 skipped)
- **Abaqus run count:** 0.
- **Next gate:** SUPERVISOR normative acceptance of the policy PR (not merged).
