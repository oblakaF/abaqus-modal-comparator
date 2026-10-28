"""NEW-GUI.2: the application's importer chain, installed once by one shared function.

The UNV/UFF and extracted-package importers the analysis uses are the base functions of ``universal_reader`` and
``abaqus_bridge`` as replaced by five existing process-level layers. ``ensure_application_importers`` installs those
layers, unchanged, strictly in the order the application has always used:

1. ``universal_hardening.install_universal_hardening``: dataset 55/2414 parsing, FRF peaks, FRF group, coherence and
   the loader;
2. ``universal_frf_review.install_frf_review``;
3. ``cmif_separation.install_cmif_separation``;
4. ``cmif_validation.install_cmif_validation``: these three chain ``universal_reader._modes_from_frf_datasets``;
5. ``fast_cache.install_fast_cache``: the memory and disk cache of both loaders.

``src/main.py`` (the existing program) and the new interface both call it, so they read every file with the same
importer. The new interface does not import ``main.py``, Tkinter or any user-interface layer.

It adds no layer and changes no algorithm. Installing writes nothing: the fast cache creates its folder and files only
when a file is read. It is idempotent; a call after some layers were installed out of this order is refused, because
the chained FRF layers would then differ from the application's.
"""

from __future__ import annotations

import cmif_separation
import cmif_validation
import fast_cache
import universal_frf_review
import universal_hardening

# (name, module, install function), in the order of installation; each module records its own ``_INSTALLED``.
IMPORTER_LAYERS = (
    ("install_universal_hardening", universal_hardening, universal_hardening.install_universal_hardening),
    ("install_frf_review", universal_frf_review, universal_frf_review.install_frf_review),
    ("install_cmif_separation", cmif_separation, cmif_separation.install_cmif_separation),
    ("install_cmif_validation", cmif_validation, cmif_validation.install_cmif_validation),
    ("install_fast_cache", fast_cache, fast_cache.install_fast_cache),
)
LAYER_NAMES = tuple(name for name, _, _ in IMPORTER_LAYERS)


class ImporterOrderError(RuntimeError):
    """Some importer layers were installed outside the application's order."""


def installed_layers() -> tuple:
    """The names of the importer layers installed in this process, in the application's order."""
    return tuple(name for name, module, _ in IMPORTER_LAYERS if getattr(module, "_INSTALLED", False))


def ensure_application_importers() -> None:
    """Install the application's importer layers in order; nothing happens when they are already installed."""
    installed = installed_layers()
    if installed != LAYER_NAMES[:len(installed)]:
        raise ImporterOrderError("The importer layers were installed outside the application's order "
                                 f"({', '.join(installed)}); expected a prefix of {', '.join(LAYER_NAMES)}.")
    for _, _, install in IMPORTER_LAYERS:
        install()
