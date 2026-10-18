"""Auto-ID Execution Plan of a saved SPEC v1.2 campaign definition (M8-D2h): plan only, no Abaqus, no LM.

    python tools/auto_id_execution_plan.py --definition <campaign.json> --work-dir <empty folder>

The same service as "Prepare Auto-ID Execution Plan..." in the GUI (services.campaign_execution_plan): Pre-run
Validation, then the existing planning sequence prepare_campaign_specimens / prepare_run_manifest; writes
run_manifest.json, plan_jobs/ and execution_plan.json into the working directory and prints the manifest hash, the
operations and the budgets.  There is no execute command: execution stays NOT_AUTHORISED.

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
from services.campaign_execution_plan import prepare_execution_plan  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    roots = dict(fixture_roots_from_environment())
    plan = prepare_execution_plan(args.definition, args.work_dir, ROOT, load_fixtures(ROOT), roots,
                                  [ROOT, *roots.values()])
    print(json.dumps({"campaign_id": plan.campaign_id, "campaign_hash": plan.campaign_hash,
                      "manifest_hash": plan.manifest_hash, "authorisation_scope_hash": plan.authorisation_scope_hash,
                      "operations": plan.operations, "gates": list(plan.gates),
                      "execution_status": plan.execution_status}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
