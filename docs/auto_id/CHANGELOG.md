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
