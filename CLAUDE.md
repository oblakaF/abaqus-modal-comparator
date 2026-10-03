# CLAUDE.md — instructions for Claude Code sessions

Permanent project instructions. The same rules are in `AGENTS.md` for other agents;
keep the two files in sync.

## Before any Auto-ID work

Read, in this order:

1. `docs/auto_id/SPEC_V1_1.md`: governing scientific contract
2. `docs/auto_id/ROADMAP.md`: execution order and git protocol
3. `docs/auto_id/STATUS.json`: current stage, mini-step and status
4. `docs/auto_id/DECISIONS.md`: accepted decisions (append-only)
5. the latest entry in `docs/auto_id/CHANGELOG.md`
6. the relevant accepted entries in `docs/auto_id/EVIDENCE.md`

Precedence when documents disagree: SPEC > DECISIONS > ROADMAP > STATUS > accepted
EVIDENCE > older roadmap/design/history documents (`docs/auto_id/README.md`).

## Work rules

- One mini-step only: the one named in STATUS/ROADMAP.
- Never skip roadmap order. Never invent the next stage.
- Do not reopen global architecture audits unless a specific blocker demands it.
- Small, coherent diffs. No unrelated refactor or opportunistic cleanup.
- A behaviour change requires a reproducing test.
- No Abaqus run without an explicit HUMAN gate.
- No force push. No destructive git (reset --hard, clean, branch deletion, history
  rewrite). No direct push to `main`.
- No new `install_*` monkeypatch layers for Auto-ID. Scientific logic lives in
  reusable services that the CLI and GUI both call. The GUI comes last.
- Do not modify protected scientific/reference data (for example
  `docs/registrations/*.json`, `docs/baseline/`, frozen evidence) unless explicitly
  authorised.
- Never commit ODB/UNV/UFF files, solver scratch, caches or user data.
- Update ROADMAP, STATUS.json and CHANGELOG in the same mini-step commit.
- Commit message form: `auto-id(M<n>.<k>): <summary>` (docs-only: `docs(auto-id): ...`).
- Push the mini-step's `auto-id/*` branch before reporting.
- STOP after the report. Wait for SUPERVISOR ACCEPT / REWORK / ESCALATE.

## Status rule

- A worker may move: `TODO → IN_PROGRESS → REVIEW_READY`.
- Only explicit SUPERVISOR/HUMAN acceptance may move: `REVIEW_READY → ACCEPTED`.
- If the supervisor requests a correction: `REVIEW_READY → REWORK`.
- Never mark a future stage ACCEPTED. Never pre-fill pending scientific results.

## Branches and merges

- Stage branches: `auto-id/m0` … `auto-id/m8`. The freeze branch is `auto-id/v1.1-roadmap`.
- At stage end: all mini-steps ACCEPTED, gate tests pass, PR to `main` prepared, STOP.
- Never merge a stage PR without explicit HUMAN authorisation. After a merge, record
  the `main` merge SHA in STATUS.json and CHANGELOG.md before starting the next stage.

## Codebase orientation

- Entry point `src/main.py` builds the app from an ordered chain of `install_*`
  layers. The base definition of a function is often not its final owner. Check the
  chain (and `src/runtime_contracts.py`) before editing comparator behaviour.
- Domain contracts: `src/domain/`. Services: `src/services/`. Tests: `tests/`
  (`python -m unittest discover -s tests -v`).
