from __future__ import annotations


_INSTALLED = False


def install_performance_tuning() -> None:
    """Apply conservative runtime settings without changing accepted-pair physics.

    It deliberately no longer caps geometry candidates: a cap of eight hid the
    90-degree axis-swapped family of a nearly square planar scan before the
    orientation-ambiguity gate. Only the selected candidate is evaluated
    modally, so the complete plausible set costs no correlation work.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
