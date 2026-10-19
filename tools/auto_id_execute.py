"""Guarded Auto-ID execution of a prepared Execution Plan (M8-D2i): the same controller as the GUI.

    python tools/auto_id_execute.py status --work-dir <plan folder>
        Re-checks the plan against the current sources and prints the gates, the budgets, the authorisation status and
        the verified progress of its run journals (no Abaqus, nothing written).

    python tools/auto_id_execute.py extract-archive --work-dir <plan folder> --authorisation <file> [--abaqus <cmd>]
    python tools/auto_id_execute.py run --work-dir <plan folder> --authorisation <file> [--abaqus <cmd>]
        ARCHIVE_EXTRACTION / CAMPAIGN_RUN through services.guarded_execution.  An authorisation counts only when a
        trusted HUMAN authority attests it.  No trusted authority exists in this installation, so both commands refuse
        (exit code 2) before any executor is created: no Abaqus, no extraction, no LM.

Stores: AUTO_ID_FIXTURE_ROOT_<STORE> (snadwich, carbon-project-archive, ...).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from services.auto_id_wizard import load_fixtures  # noqa: E402
from services.campaign_execution_plan import ExecutionNotAuthorised  # noqa: E402
from services.guarded_execution import (  # noqa: E402
    ARCHIVE_EXTRACTION,
    CAMPAIGN_RUN,
    PRODUCTION_AUTHORITY,
    ExecutionAuthorisation,
    GuardedExecutionController,
    campaign_journals,
    open_execution_context,
)
from services.run_progress import inspect_run_progress  # noqa: E402


def _authorisation(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        return ExecutionAuthorisation(**data)
    except TypeError:
        return data  # not even the contract's shape: refused by the controller as "not an execution authorisation"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "extract-archive", "run"):
        command = commands.add_parser(name)
        command.add_argument("--work-dir", type=Path, required=True)
        if name != "status":
            command.add_argument("--authorisation", type=Path, required=True)
            command.add_argument("--abaqus", default="abaqus")
    args = parser.parse_args(argv)
    roots = dict(fixture_roots_from_environment())
    fixtures = load_fixtures(ROOT)

    def recheck():
        return open_execution_context(args.work_dir, ROOT, fixtures, roots)

    context = recheck()

    def solve_executor():
        from services.forward_solver import subprocess_executor

        return subprocess_executor(7200)

    def extraction_executor():
        from services.shape_extraction import pinned_script_executor

        return pinned_script_executor(ROOT, args.abaqus, 7200)

    controller = GuardedExecutionController(context, PRODUCTION_AUTHORITY, abaqus_command=getattr(args, "abaqus", ""),
                                            solve_executor_factory=solve_executor,
                                            extraction_executor_factory=extraction_executor, recheck=recheck)
    if args.command == "status":
        progress = [dict(inspect_run_progress(context.definition, path, context.specimens).rows)
                    for path in campaign_journals(context)]
        print(json.dumps({"campaign_hash": context.campaign_hash, "manifest_hash": context.manifest_hash,
                          "authorisation_scope_hash": context.scope_hash, "gates": controller.gate_rows(),
                          "start_available": controller.start_available(), "progress": progress}, indent=1))
        return 0
    operation = ARCHIVE_EXTRACTION if args.command == "extract-archive" else CAMPAIGN_RUN
    try:
        outcome = controller.execute(operation, _authorisation(args.authorisation))
    except ExecutionNotAuthorised as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    print(json.dumps({"operation": outcome.operation, "state": outcome.state.value, "detail": outcome.detail,
                      "summary": outcome.summary}, indent=1, default=str))
    return 0 if outcome.state.value == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
