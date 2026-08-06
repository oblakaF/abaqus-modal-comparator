"""Capture a machine-readable baseline snapshot of a real Abaqus/experimental
comparison run, per ROADMAP.md Stage 0 (baseline capture before Stage 2
numerical changes).

This intentionally reuses the exact production pipeline (the same install_*
patches app.py loads, and the same modal_core.compare_modal_datasets facade
app.py calls) rather than re-implementing any numerical logic, so the
baseline reflects what the application actually produces.

Usage (from the repository root, with the project virtualenv active):

    python tools/generate_baseline_snapshot.py \
        --abaqus "E:/sumin/Job-1.odb" \
        --abaqus-cache modal_comparator_output/analysis_31820a8085217a96/abaqus \
        --experiment "E:/sumin/500by500_Glue420_Auxetic_full_scan_260624.unv" \
        --start-mode 6 --end-mode 17 \
        --commit 997e707 \
        --output docs/baseline/job1_auxetic_997e707.json

If --abaqus-cache already contains a manifest.json matching the .odb file's
current size/mtime signature, the cached extraction is reused and Abaqus
itself is not invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from universal_hardening import install_universal_hardening
from universal_frf_review import install_frf_review
from cmif_separation import install_cmif_separation
from cmif_validation import install_cmif_validation
from fast_cache import install_fast_cache
from performance_tuning import install_performance_tuning
from reporting_hardening import install_reporting_hardening
from amplitude_correlation import install_amplitude_correlation
from metrics_normalization import install_metrics_normalization

install_universal_hardening()
install_frf_review()
install_cmif_separation()
install_cmif_validation()
install_fast_cache()
install_performance_tuning()
install_reporting_hardening()
install_amplitude_correlation()
install_metrics_normalization()

from abaqus_bridge import load_or_extract_odb
from advanced_metrics import automac_matrices, comac_by_node
from modal_core import compare_modal_datasets
from universal_reader import load_universal_modal_file, resolve_testlab_file


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _library_versions() -> Dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    for module_name in ("numpy", "scipy", "pyuff", "openpyxl", "matplotlib"):
        try:
            module = __import__(module_name)
            versions[module_name] = getattr(module, "__version__", "unknown")
        except ImportError:
            versions[module_name] = "not installed"
    return versions


def _git_commit(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abaqus", required=True, type=Path)
    parser.add_argument("--abaqus-cache", required=True, type=Path)
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--start-mode", required=True, type=int)
    parser.add_argument("--end-mode", required=True, type=int)
    parser.add_argument("--abaqus-command", default="abaqus")
    parser.add_argument("--commit", default=None, help="Git commit SHA this baseline is frozen at.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    abaqus_path = args.abaqus.resolve()
    experiment_path = args.experiment.resolve()
    if not abaqus_path.exists():
        raise SystemExit(f"Abaqus source not found: {abaqus_path}")
    if not experiment_path.exists():
        raise SystemExit(f"Experimental source not found: {experiment_path}")

    abaqus_data = load_or_extract_odb(
        abaqus_path, args.abaqus_cache, args.abaqus_command, args.start_mode, args.end_mode
    )
    resolved_experiment = resolve_testlab_file(experiment_path)
    experiment_data = load_universal_modal_file(resolved_experiment)
    result = compare_modal_datasets(abaqus_data, experiment_data)

    abaqus_automac, experimental_automac = automac_matrices(result)
    comac_coordinates, comac_scores = comac_by_node(result)

    point_count = len(result.experimental.modes[0].node_ids) if result.experimental.modes else 0

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_at_git_commit": _git_commit(args.commit),
        "purpose": (
            "ROADMAP.md Stage 0 baseline: the accepted reference result to diff "
            "every subsequent Stage 2 numerical change against."
        ),
        "environment": {
            "platform": platform.platform(),
            **_library_versions(),
        },
        "inputs": {
            "abaqus_source_path": str(abaqus_path),
            "abaqus_source_sha256": _sha256(abaqus_path),
            "abaqus_source_size_bytes": abaqus_path.stat().st_size,
            "abaqus_start_mode": args.start_mode,
            "abaqus_end_mode": args.end_mode,
            "experimental_source_path": str(experiment_path),
            "experimental_source_sha256": _sha256(experiment_path),
            "experimental_source_size_bytes": experiment_path.stat().st_size,
        },
        "geometry": {
            "experimental_point_count": point_count,
            "matched_fraction": result.geometry.matched_fraction,
            "normalized_rms_distance": result.geometry.normalized_rms_distance,
            "coordinate_scale": result.geometry.coordinate_scale,
            "mean_mapping_distance": float(result.geometry.distances.mean()),
            "max_mapping_distance": float(result.geometry.distances.max()),
        },
        "pair_count": len(result.pairs),
        "pairs": [
            {
                "abaqus_mode": pair.abaqus_mode,
                "experimental_mode": pair.experimental_mode,
                "abaqus_frequency_hz": pair.abaqus_frequency_hz,
                "experimental_frequency_hz": pair.experimental_frequency_hz,
                "signed_frequency_error_percent": pair.frequency_error_percent,
                "mac": pair.mac,
                "status": pair.status,
                "mapped_points": pair.mapped_points,
            }
            for pair in result.pairs
        ],
        "warnings": list(result.warnings),
        "manual_review_decisions": {},
        "automac": {
            "abaqus": abaqus_automac.tolist(),
            "experimental": experimental_automac.tolist(),
        },
        "comac_by_node_score": [
            None if not (score == score) else float(score)  # NaN -> null
            for score in comac_scores.tolist()
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    print(f"Wrote baseline snapshot: {args.output}")
    print(f"Pairs: {len(result.pairs)}, points: {point_count}")


if __name__ == "__main__":
    main()
