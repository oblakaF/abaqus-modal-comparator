from __future__ import annotations

import reviewed_core


_INSTALLED = False


def install_performance_tuning() -> None:
    """Apply conservative runtime settings without changing accepted-pair physics."""
    global _INSTALLED
    if _INSTALLED:
        return
    # A square panel has at most eight physically relevant in-plane signed/permuted
    # orientations after geometry screening. Evaluating 16 modal candidates doubled the
    # expensive correlation stage without improving the selected orientation in tests.
    reviewed_core.GEOMETRY_CANDIDATE_LIMIT = 8
    _INSTALLED = True
