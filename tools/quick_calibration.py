"""Quick effective-property calibration from the command line (real Abaqus).

    python tools/quick_calibration.py template my_case.json
        writes an example configuration to edit.

    python tools/quick_calibration.py sets SP13.unv
        lists the dataset-55 modal sets of the experimental file (no Abaqus).

    python tools/quick_calibration.py check my_case.json
        the input preflight only: INP, material constants, INPUT= references, modal set, mode count (no Abaqus).

    python tools/quick_calibration.py run my_case.json
        runs the calibration described by the configuration (paths relative to the file).

    python tools/quick_calibration.py quick --inp SP13.inp --unv SP13.unv --modal-set best --material CFRP_Face \\
        --constants E1,E2 --out SP13_quick [--abaqus abq2024] [--cpus 4] [--g12] [--orientation <id>] [--check-only]
        the same without a configuration file; the configuration used is saved in the output folder.

Every run starts with the input preflight; a refusal stops it before any Abaqus solve. A file with several
dataset-55 modal sets needs --modal-set (or "modal_set" in the configuration); none is chosen automatically.

The result is an EFFECTIVE_MODEL_CALIBRATION of this FE model on this specimen, never a material property.
See src/services/quick_calibration.py for the method.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _quick_config(args) -> dict:
    parameters = [{"name": "E_face", "material": args.material, "constants": args.constants.split(","),
                   "lower": args.lower, "upper": args.upper}]
    if args.g12:
        parameters.append({"name": "G12_face", "material": args.material, "constants": ["G12"],
                           "lower": 0.4, "upper": 2.5})
    return {"model_inp": str(Path(args.inp).resolve()), "experiment": str(Path(args.unv).resolve()),
            "output_dir": str(Path(args.out).resolve()), "abaqus_command": args.abaqus, "cpus": args.cpus,
            "parameters": parameters, "orientation_candidate_id": args.orientation, "modal_set": args.modal_set,
            "min_experimental_hz": args.min_hz, "max_experimental_hz": args.max_hz,
            "coordinate_scale": args.scale, "solve_budget": args.budget}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="write an example configuration")
    template.add_argument("path")
    sets = sub.add_parser("sets", help="list the dataset-55 modal sets of an experimental file (no Abaqus)")
    sets.add_argument("experiment")
    check = sub.add_parser("check", help="input preflight of a configuration file only (no Abaqus)")
    check.add_argument("config")
    run = sub.add_parser("run", help="run a configuration file")
    run.add_argument("config")
    quick = sub.add_parser("quick", help="run without a configuration file")
    quick.add_argument("--inp", required=True)
    quick.add_argument("--unv", required=True)
    quick.add_argument("--modal-set", default=None,
                       help="dataset-55 modal set key or name (required when the file has several)")
    quick.add_argument("--check-only", action="store_true", help="input preflight only (no Abaqus)")
    quick.add_argument("--material", required=True)
    quick.add_argument("--constants", default="E1,E2")
    quick.add_argument("--out", required=True)
    quick.add_argument("--abaqus", default="abaqus")
    quick.add_argument("--cpus", type=int, default=1)
    quick.add_argument("--g12", action="store_true", help="also fit G12 of the same material (second parameter)")
    quick.add_argument("--orientation", default=None, help="orientation candidate id when the panel is symmetric")
    quick.add_argument("--lower", type=float, default=0.5)
    quick.add_argument("--upper", type=float, default=2.0)
    quick.add_argument("--min-hz", type=float, default=None)
    quick.add_argument("--max-hz", type=float, default=None)
    quick.add_argument("--scale", type=float, default=None, help="experiment → FE length factor (default: auto)")
    quick.add_argument("--budget", type=int, default=16)
    args = parser.parse_args(argv)

    from services.quick_calibration import (QuickCalibrationError, config_from_dict, config_template,
                                            discover_modal_sets, load_config, preflight, run_quick_calibration)

    if args.command == "template":
        Path(args.path).write_text(json.dumps(config_template(), indent=2), encoding="utf-8")
        print(f"template written: {args.path}")
        return 0
    from application_layers import install_application_layers

    install_application_layers()
    if args.command == "sets":
        choices = discover_modal_sets(Path(args.experiment))
        for choice in choices:
            print(f"{choice.key}: {choice.label}")
        if not choices:
            print("no dataset-55 modal set (the dataset 2414 / 58 fallback is used)")
        return 0
    try:
        if args.command in ("run", "check"):
            config = load_config(Path(args.config))
        else:
            data = _quick_config(args)
            config = config_from_dict(data)
        report = preflight(config)
        print("\n".join(report.lines()), flush=True)
        if not report.ready:
            print("\nSTOPPED: input preflight refused the run; no Abaqus solve was started.", file=sys.stderr)
            return 2
        if args.command == "check" or getattr(args, "check_only", False):
            return 0
        if args.command == "quick":
            Path(config.output_dir).mkdir(parents=True, exist_ok=True)
            (Path(config.output_dir) / "config.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        print()
        result, paths = run_quick_calibration(config, progress=lambda message: print("  " + message, flush=True))
    except QuickCalibrationError as error:
        print(f"\nSTOPPED: {error}", file=sys.stderr)
        return 2
    print()
    print(Path(paths["report"]).read_text(encoding="utf-8"))
    for key, path in paths.items():
        print(f"{key:>15}: {path}")
    return 0 if result["status"] == "ESTIMATE" else 1


if __name__ == "__main__":
    sys.exit(main())
