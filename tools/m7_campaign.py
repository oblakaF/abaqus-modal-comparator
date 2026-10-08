"""M7 identification campaign (D-069): plan (no Abaqus), gated archive extraction, gated run, report (no Abaqus).

    All commands take --campaign run-a (default) or run-b.

    python tools/m7_campaign.py plan --run-root <dir>
        Freezes every specimen on its active physical chain (exact accepted rows or STOP), renders the initial
        points, verifies every archived reuse and writes <dir>/run_manifest.json (the HUMAN execution manifest).

    python tools/m7_campaign.py extract-archive --run-root <dir> --abaqus <command> --authorised-manifest-hash <h>
        ABAQUS PYTHON (HUMAN gate only): extraction-only reuse of the archived accepted ODBs.

    python tools/m7_campaign.py run --run-root <dir> --abaqus <command> --authorised-manifest-hash <h>
        REAL ABAQUS (HUMAN gate only): the bounded LM campaign with the hard solve budget; resumable.

    python tools/m7_campaign.py report --run-root <dir> --result <file>
        The engineering estimate and the formal M5 verdict from the journals (no Abaqus).

Stores: AUTO_ID_FIXTURE_ROOT_<STORE> (snadwich, carbon-project-archive; abaqus-scratch for SP02 solves).
RUN_B is never executable here without its own later SUPERVISOR gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.campaign_definition import load_archive_reuse, load_campaign_definition  # noqa: E402
from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest  # noqa: E402
from domain.identification_run import RunJournal  # noqa: E402
from services.identification_campaign_run import (  # noqa: E402
    ARCHIVE_RUN_STORE,
    CampaignGateRefusal,
    CampaignRun,
    CampaignRunConfig,
    build_campaign_report,
    extract_archived_odbs,
    journalled_archive_records,
    prepare_campaign_specimens,
    prepare_run_manifest,
    reused_pack_records,
)


CAMPAIGNS = {"run-a": ROOT / "docs" / "auto_id" / "campaigns" / "M7_RUN_A.campaign.json",
             "run-b": ROOT / "docs" / "auto_id" / "campaigns" / "M7_RUN_B.campaign.json"}
RUN_A_RESULT = ROOT / "docs" / "auto_id" / "campaigns" / "M7_RUN_A.result.json"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"


def build(run_root: Path, roots, campaign: str = "run-a"):
    definition = load_campaign_definition(CAMPAIGNS[campaign])
    definition.require_executable()
    reuse = load_archive_reuse(ROOT / definition.archive_reuse, definition.parameterisation_id)
    specimens = prepare_campaign_specimens(definition, ROOT, load_experiment_fixture_manifest(FIXTURES), roots)
    manifest, manifest_hash = prepare_run_manifest(definition, reuse, specimens, roots, ROOT, run_root / "plan_jobs")
    return definition, reuse, specimens, manifest, manifest_hash


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    extract = commands.add_parser("extract-archive")
    run = commands.add_parser("run")
    report = commands.add_parser("report")
    for item in (plan, extract, run, report):
        item.add_argument("--run-root", type=Path, required=True)
        item.add_argument("--campaign", choices=sorted(CAMPAIGNS), default="run-a")
    for item in (extract, run):
        item.add_argument("--abaqus", required=True, help="Abaqus command (machine-specific)")
        item.add_argument("--authorised-manifest-hash", required=True)
        item.add_argument("--timeout-seconds", type=int, default=7200)
    report.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)

    run_root = args.run_root.resolve()
    roots = dict(fixture_roots_from_environment())
    roots[ARCHIVE_RUN_STORE] = run_root / "archive_reuse"
    definition, reuse, specimens, manifest, manifest_hash = build(run_root, roots, args.campaign)
    if args.command == "plan":
        (run_root / "run_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(json.dumps({"manifest_hash": manifest_hash, **manifest["budgets"]}, indent=1))
        return 0
    if args.command in ("extract-archive", "run"):
        if args.authorised_manifest_hash != manifest_hash:
            raise CampaignGateRefusal("the authorised manifest hash differs from this plan; nothing is executed.")
        from services.shape_extraction import pinned_script_executor

        extraction_executor = pinned_script_executor(ROOT, args.abaqus, args.timeout_seconds)
        if args.command == "extract-archive":
            records = extract_archived_odbs(reuse, specimens, run_root, roots, extraction_executor, manifest_hash,
                                            args.authorised_manifest_hash)
            print(json.dumps({job: r.content_sha256 for job, r in records.items()}, indent=1))
            return 0
        from services.forward_solver import subprocess_executor

        extracted = journalled_archive_records(reuse, run_root, manifest_hash)  # run extract-archive first
        config = CampaignRunConfig(run_root, roots, args.abaqus, subprocess_executor(args.timeout_seconds),
                                   extraction_executor, reused_pack_records(reuse, ROOT, extracted, specimens),
                                   args.authorised_manifest_hash)
        print(json.dumps(CampaignRun(definition, specimens, manifest_hash, config).run(), indent=1, default=str))
        return 0
    extracted = journalled_archive_records(reuse, run_root, manifest_hash)
    config = CampaignRunConfig(run_root, roots, "not-used", _refuse_solve, _refuse_new_extraction,
                               reused_pack_records(reuse, ROOT, extracted, specimens), manifest_hash)
    campaign = CampaignRun(definition, specimens, manifest_hash, config)
    journal = RunJournal(campaign.run_dir / "journal.json", campaign.identity)
    results = journal.records("result")
    if not results:
        raise SystemExit("no campaign result is journalled yet.")
    reference, label = None, ""
    if definition.run_type == "RUN_B":  # the diagnostic is reported against the accepted RUN_A result
        run_a = json.loads(RUN_A_RESULT.read_text(encoding="utf-8"))
        reference = {**run_a["parameters"], **run_a["fixed_parameters"]}
        label = f"RUN_A {run_a['run_hash']}"
    document = build_campaign_report(definition, specimens, journal.records("evaluation"), results[-1], reference,
                                     label)
    document["manifest_hash"] = manifest_hash
    args.result.write_text(json.dumps(document, indent=1), encoding="utf-8")
    summary_keys = ("lm_status", "optimizer_candidate", "formal_output", "material_claim", "validation")
    print(json.dumps({k: document[k] for k in summary_keys}, indent=1))
    return 0


def _refuse_new_extraction(*_args, **_kwargs):
    raise CampaignGateRefusal("a new extraction is not allowed in this command (run extract-archive under its gate).")


def _refuse_solve(*_args, **_kwargs):
    raise CampaignGateRefusal("no Abaqus solve is allowed while reporting.")


if __name__ == "__main__":
    raise SystemExit(main())
