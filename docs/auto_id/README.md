# Auto-ID — Canonical Project Record

This directory is the durable record of the Auto-ID (automatic material
identification) work. **GitHub, not chat memory, is the project record.** Every
session or agent starts here.

Audited baseline: `121ba1d06b7c268b3051f1407a3ea26a9027dca3`.

## Documents

| File | Role |
|---|---|
| [SPEC_V1_2.md](SPEC_V1_2.md) | Governing scientific contract (normative, D-078): SPEC v1.1 as amended by v1.2 |
| [SPEC_V1_1.md](SPEC_V1_1.md) | Normative predecessor (archived, immutable); clauses not amended by v1.2 remain in force through v1.2 |
| [SPEC_V1_2_DRAFT.md](SPEC_V1_2_DRAFT.md), [SPEC_V1_2_POLICY_REVIEW.md](SPEC_V1_2_POLICY_REVIEW.md), [SPEC_V1_2_POLICY_OPTIONS.json](SPEC_V1_2_POLICY_OPTIONS.json) | SPEC v1.2 policy-development history (SUPERSEDED_BY_NORMATIVE_SPEC_V1_2) |
| [DECISIONS.md](DECISIONS.md) | Append-only log of accepted design decisions |
| [ROADMAP.md](ROADMAP.md) | Canonical execution roadmap: PRE-M0, M0–M8, steel gate |
| [STATUS.json](STATUS.json) | Machine-readable current state |
| [EVIDENCE.md](EVIDENCE.md) | Index of scientific evidence (identities and compact results only) |
| [CHANGELOG.md](CHANGELOG.md) | Append-only per-mini-step history |
| [AUDIT_121ba1d_V1_1.md](AUDIT_121ba1d_V1_1.md) | Accepted external audit of the baseline (findings K1–K4, V1–V7, J1–J3) |
| [source/](source/) | Archival original DOCX files (Russian) with [SHA256SUMS.txt](source/SHA256SUMS.txt) |

The Markdown files are canonical for implementation, because they can be reviewed in
Git diffs. The DOCX files are archival evidence of what was accepted.

## Document precedence

When documents disagree, the higher item wins:

1. [docs/auto_id/SPEC_V1_2.md](SPEC_V1_2.md) (with the unamended clauses of [SPEC_V1_1.md](SPEC_V1_1.md))
2. [docs/auto_id/DECISIONS.md](DECISIONS.md)
3. [docs/auto_id/ROADMAP.md](ROADMAP.md)
4. [docs/auto_id/STATUS.json](STATUS.json)
5. accepted entries in [docs/auto_id/EVIDENCE.md](EVIDENCE.md)
6. older roadmap / design / history documents

**If an older document conflicts with SPEC v1.2, SPEC v1.2 wins.** Historical
documents stay useful for rationale and previous work, but they cannot silently
override the current accepted scientific contract. Historical documents include:

- [ROADMAP.md](../../ROADMAP.md) (repository root);
- [docs/ROADMAP_Stage_Inverse_Identification.md](../ROADMAP_Stage_Inverse_Identification.md);
- [docs/gui/EFFECTIVE_MATERIAL_IDENTIFICATION_V1.md](../gui/EFFECTIVE_MATERIAL_IDENTIFICATION_V1.md).

The audit records the baseline's findings. Where the SPEC or a later accepted decision
says what to do about a finding, that wins.

## Development model

```
SPEC → ROADMAP → one mini-step → tests/evidence → STATUS/CHANGELOG update
     → commit → push → STOP → SUPERVISOR review → ACCEPT / REWORK / ESCALATE
     → only then the next mini-step
```

Roles: the WORKER implements one mini-step. The SUPERVISOR reviews. The HUMAN is the
final authority at gates (Abaqus runs, merges to `main`, scientific acceptance). The
full protocol is in [ROADMAP.md](ROADMAP.md). Short-form instructions for agents are
in [CLAUDE.md](../../CLAUDE.md) and [AGENTS.md](../../AGENTS.md).

## Where things stand

Read [STATUS.json](STATUS.json). Do not infer state from chat history.
