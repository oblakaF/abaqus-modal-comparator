"""Write the physical scan-to-panel reconstruction record of one stored PSV measurement (read-only on the store).

Example (SP-13, M6 registration gate):

    python tools/reconstruct_psv_registration.py --store snadwich \
        --svd "SP-13/SP13_a_500by500_Glue420_Auxetic_newSP01_260910.svd" \
        --unv "SP-13/SP13_a_polymax.unv" --width-mm 510 --height-mm 520 \
        --dimension-source "SP-13/spec.txt (510x520x2.85; 100 cm steel ruler + two calipers; no instrument uncertainty recorded)" \
        --out docs/auto_id/registration_evidence/SP13_physical_registration_reconstruction.json

No modal data and no MAC are read. Store roots come from AUTO_ID_FIXTURE_ROOT_<STORE> variables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from services.psv_video_registration import reconstruct  # noqa: E402


def unv_scan_geometry(path: Path) -> tuple[list[int], np.ndarray]:
    """Dataset 2411 node ids and x, y coordinates (metres) as listed in the file."""
    lines = path.read_text(encoding="latin-1").splitlines()
    start = next(k for k in range(1, len(lines)) if lines[k].strip() == "2411" and lines[k - 1].strip() == "-1")
    ids, xy, j = [], [], start + 1
    while lines[j].strip() != "-1":
        ids.append(int(lines[j].split()[0]))
        values = [float(v.replace("D", "E")) for v in lines[j + 1].split()]
        xy.append(values[:2])
        j += 2
    return ids, np.array(xy, dtype=float)


def file_identity(store: str, relative: str, path: Path) -> dict:
    data = path.read_bytes()
    return {"store": store, "relative_path": relative, "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data)}


NO_RESOLUTION = "NOT_AVAILABLE (no instrument resolution recorded)"


def build(store: str, svd: str, unv: str, width_mm: float, height_mm: float, dimension_source: str,
          dimension_uncertainty: str = NO_RESOLUTION) -> dict:
    roots = fixture_roots_from_environment()
    if store not in roots:
        raise SystemExit(f"data store {store!r} is not configured")
    svd_path, unv_path = roots[store] / svd, roots[store] / unv
    ids, xy = unv_scan_geometry(unv_path)
    sources = {"svd": file_identity(store, svd, svd_path), "unv_geometry": file_identity(store, unv, unv_path),
               "panel_dimensions": {"width_mm": width_mm, "height_mm": height_mm, "source": dimension_source,
                                    "uncertainty": dimension_uncertainty}}
    result = reconstruct(svd_path.read_bytes(), xy, ids, width_mm, height_mm, sources=sources)
    record = dict(result.record)
    record["unv_node_ids"] = ids
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True)
    parser.add_argument("--svd", required=True)
    parser.add_argument("--unv", required=True)
    parser.add_argument("--width-mm", type=float, required=True)
    parser.add_argument("--height-mm", type=float, required=True)
    parser.add_argument("--dimension-source", required=True)
    parser.add_argument("--dimension-uncertainty", default=NO_RESOLUTION,
                        help="recorded readout resolution of the dimension measurement (never a calibration claim)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    record = build(args.store, args.svd, args.unv, args.width_mm, args.height_mm, args.dimension_source,
                   args.dimension_uncertainty)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
