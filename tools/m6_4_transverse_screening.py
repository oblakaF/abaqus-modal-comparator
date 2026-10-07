"""M6.4 transverse-constant screening: plan (no Abaqus), HUMAN-gated run, evaluation (no Abaqus).

    python tools/m6_4_transverse_screening.py plan --run-root <dir>
        Renders the screening jobs into <dir>/jobs and writes <dir>/screening_manifest.json (the HUMAN
        Abaqus manifest).  Needs the 'snadwich' store.  No Abaqus.

    python tools/m6_4_transverse_screening.py run --run-root <dir> --abaqus <command> \
        --authorised-manifest-hash <hash>
        REAL ABAQUS: solves and extracts every job.  Only under an explicit HUMAN gate that names the
        exact manifest hash printed by 'plan'.  SP02 also needs the 'abaqus-scratch' store.

    python tools/m6_4_transverse_screening.py evaluate --run-root <dir> --result <file>
        Tracks the frozen rows into every perturbed state and classifies each constant.  Needs the
        'carbon-project-archive' store (baseline packs).  No Abaqus.

Stores are configured by AUTO_ID_FIXTURE_ROOT_<STORE> environment variables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest  # noqa: E402
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING  # noqa: E402
from domain.transverse_screening import load_screening_envelope  # noqa: E402
from services.transverse_screening import (  # noqa: E402
    ScreeningError,
    ScreeningRunConfig,
    bind_screening_specimens,
    evaluate_screening,
    expected_jobs,
    load_screening_states,
    prepare_screening_plan,
    run_screening,
)


ENVELOPE = ROOT / "docs" / "auto_id" / "screening" / "M6_4_transverse_envelope.json"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"


def build_plan(run_root: Path, roots):
    envelope = load_screening_envelope(ENVELOPE)
    specimens = bind_screening_specimens(envelope, ROOT, load_experiment_fixture_manifest(FIXTURES))
    return prepare_screening_plan(envelope, specimens, roots, run_root / "jobs")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan")
    run_parser = commands.add_parser("run")
    evaluate_parser = commands.add_parser("evaluate")
    for item in (plan_parser, run_parser, evaluate_parser):
        item.add_argument("--run-root", type=Path, required=True)
    run_parser.add_argument("--abaqus", required=True, help="Abaqus command (machine-specific)")
    run_parser.add_argument("--authorised-manifest-hash", required=True)
    run_parser.add_argument("--timeout-seconds", type=int, default=7200)
    evaluate_parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)

    roots = fixture_roots_from_environment()
    run_root = args.run_root.resolve()
    plan = build_plan(run_root, roots)
    if args.command == "plan":
        (run_root / "screening_manifest.json").write_text(json.dumps(plan.manifest, indent=1), encoding="utf-8")
        print(json.dumps({"manifest_hash": plan.manifest_hash, **plan.manifest["counts"]}, indent=1))
        return 0
    if args.command == "run":
        if args.authorised_manifest_hash != plan.manifest_hash:
            raise ScreeningError("the authorised manifest hash differs from this plan; nothing is solved.")
        from services.forward_solver import subprocess_executor
        from services.shape_extraction import pinned_script_executor

        config = ScreeningRunConfig(run_root, roots, args.abaqus, subprocess_executor(args.timeout_seconds),
                                    pinned_script_executor(ROOT, args.abaqus, args.timeout_seconds),
                                    args.authorised_manifest_hash)
        print(json.dumps(run_screening(plan, config), indent=1))
        return 0
    baselines, candidates = load_screening_states(plan, run_root, roots)
    result = evaluate_screening(plan.envelope, STRICT_IDENTIFICATION_PAIRING, baselines, candidates,
                                expected_jobs(plan), plan.manifest_hash)
    args.result.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("negligible", "include_in_uncertainty_budget", "not_classified",
                                            "budget_closed")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
