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
