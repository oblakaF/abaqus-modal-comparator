from __future__ import annotations

from pathlib import Path


PAIR_RENDER_VERSION = "pair-render-v3-complex-fit"
PAIR_MARKER_NAME = ".pair_render_version"


def ensure_pair_render_cache(directory: Path) -> bool:
    """Invalidate stale mode-pair images after rendering code changes."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / PAIR_MARKER_NAME
    try:
        current = marker.read_text(encoding="utf-8").strip()
    except OSError:
        current = ""

    invalidated = current != PAIR_RENDER_VERSION
    if invalidated:
        for path in directory.glob("abaqus_*_experiment_*.png"):
            try:
                path.unlink()
            except OSError:
                pass
        marker.write_text(PAIR_RENDER_VERSION, encoding="utf-8")
    return invalidated
