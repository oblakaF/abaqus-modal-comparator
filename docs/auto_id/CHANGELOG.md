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
