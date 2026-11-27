"""Write the physical scan-to-panel reconstruction record of one stored PSV measurement (read-only on the store).

Example (a new record of the SP-13 session, written under its own name outside the repository):

    python tools/reconstruct_psv_registration.py --store snadwich \
        --svd "SP-13/SP13_a_500by500_Glue420_Auxetic_newSP01_260910.svd" \
        --unv "SP-13/SP13_a_polymax.unv" --width-mm 510 --height-mm 520 \
        --dimension-source "SP-13/spec.txt (510x520x2.85; 100 cm steel ruler + two calipers; no instrument uncertainty recorded)" \
        --out "<work folder>/SP13_260910_reconstruction_v2_DIAGNOSTIC.json"

No modal data and no MAC are read. Store roots come from AUTO_ID_FIXTURE_ROOT_<STORE> variables.

Nothing is overwritten (PSV-SCAN-OBJECT-MARGIN-01). If ``--out`` exists, the tool refuses before it reads
anything, and the file is created exclusively; there is no option to replace a record. An accepted record, such
as ``docs/auto_id/registration_evidence/SP13_physical_registration_reconstruction.json``, is therefore never an
output of this tool: give a new record a new name.

Pixel normalisation. A new reconstruction reads the frame of the scan points from the stored instrument
metadata (``--normalisation instrument-metadata``, the default) and writes a v2 record. If the metadata do
not decide, the tool refuses and writes nothing; it never falls back to the earlier reading. The earlier
reading (``--normalisation legacy-default-rectangle``) exists only to reproduce a stored v1 record and
must be named explicitly; the reproduction is written under a new name and compared with the stored record.
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
from services.psv_video_registration import (  # noqa: E402
    NORMALISATION_BY_SCHEMA,
    NORMALISATION_INSTRUMENT,
    NORMALISATION_LEGACY,
    PSVRegistrationError,
    reconstruct,
)


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


def normalisation_of_record(record: dict) -> str:
    """The pixel normalisation that wrote a stored reconstruction record, named by its schema (for reproduction)."""
    schema = record.get("schema")
    if schema not in NORMALISATION_BY_SCHEMA:
        raise PSVRegistrationError(f"reconstruction record of unknown schema {schema!r}: its pixel normalisation "
                                   "cannot be named")
    return NORMALISATION_BY_SCHEMA[schema]


def build(store: str, svd: str, unv: str, width_mm: float, height_mm: float, dimension_source: str,
          dimension_uncertainty: str = NO_RESOLUTION, *, normalisation: str = NORMALISATION_INSTRUMENT) -> dict:
    """Reconstruction record of one stored measurement.

    The default normalisation is the instrument-metadata reading. A refusal is raised to the caller; nothing
    here retries with another reading. ``NORMALISATION_LEGACY`` reproduces a v1 record and is never implied.
    """
    roots = fixture_roots_from_environment()
    if store not in roots:
        raise SystemExit(f"data store {store!r} is not configured")
    svd_path, unv_path = roots[store] / svd, roots[store] / unv
    ids, xy = unv_scan_geometry(unv_path)
    sources = {"svd": file_identity(store, svd, svd_path), "unv_geometry": file_identity(store, unv, unv_path),
               "panel_dimensions": {"width_mm": width_mm, "height_mm": height_mm, "source": dimension_source,
                                    "uncertainty": dimension_uncertainty}}
    result = reconstruct(svd_path.read_bytes(), xy, ids, width_mm, height_mm, sources=sources,
                         normalisation=normalisation)
    record = dict(result.record)
    record["unv_node_ids"] = ids
    return record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True)
    parser.add_argument("--svd", required=True)
    parser.add_argument("--unv", required=True)
    parser.add_argument("--width-mm", type=float, required=True)
    parser.add_argument("--height-mm", type=float, required=True)
    parser.add_argument("--dimension-source", required=True)
    parser.add_argument("--dimension-uncertainty", default=NO_RESOLUTION,
                        help="recorded readout resolution of the dimension measurement (never a calibration claim)")
    parser.add_argument("--normalisation", choices=(NORMALISATION_INSTRUMENT, NORMALISATION_LEGACY),
                        default=NORMALISATION_INSTRUMENT,
                        help="pixel normalisation; the default reads the stored instrument metadata and refuses "
                             "when they do not decide. The legacy reading only reproduces a stored v1 record")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists() or args.out.is_symlink():  # before anything is read: an existing record is never replaced
        raise SystemExit(f"REFUSED: {args.out} exists; an existing record is never overwritten (choose a new name)")
    try:
        record = build(args.store, args.svd, args.unv, args.width_mm, args.height_mm, args.dimension_source,
                       args.dimension_uncertainty, normalisation=args.normalisation)
    except PSVRegistrationError as exc:  # a refusal is the result: no record, no other reading is tried
        raise SystemExit(f"REFUSED ({args.normalisation}): {exc}") from exc
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(args.out, "x", encoding="utf-8", newline="\n") as stream:  # exclusive: a file made meanwhile is kept
            stream.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        raise SystemExit(f"REFUSED: {args.out} exists; an existing record is never overwritten") from None
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
