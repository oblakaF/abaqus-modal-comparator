"""Install the non-GUI reader / comparator layers of the main window (same order as src/main.py).

Used by the stand-alone quick-calibration window and the command-line tool, so that they read UNV/UFF files and
pair modes exactly like the main application.  Idempotent.
"""

from __future__ import annotations


def install_application_layers() -> None:
    from cmif_separation import install_cmif_separation
    from cmif_validation import install_cmif_validation
    from fast_cache import install_fast_cache
    from metrics_normalization import install_metrics_normalization
    from performance_tuning import install_performance_tuning
    from universal_frf_review import install_frf_review
    from universal_hardening import install_universal_hardening

    for install in (install_universal_hardening, install_frf_review, install_cmif_separation, install_cmif_validation,
                    install_fast_cache, install_performance_tuning, install_metrics_normalization):
        install()
