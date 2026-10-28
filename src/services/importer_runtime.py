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
when a file is read. It is idempotent.

NEW-GUI.2-F1: the order is checked on the functions themselves, before and after installing. The ``_INSTALLED`` flags
only say which layers ran, not in which order: with cmif_validation installed before cmif_separation all five flags
are set, but the FRF chain is reversed. ``chain_problems`` therefore compares every replaced function of
``universal_reader`` and ``abaqus_bridge``, and the predecessor each layer saved, with the chain the application's
order gives for the layers installed so far. Any difference is refused (``ImporterOrderError``), and nothing more is
installed.
"""

from __future__ import annotations

import abaqus_bridge
import cmif_separation
import cmif_validation
import fast_cache
import universal_frf_review
import universal_hardening
import universal_reader

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


def _name(function) -> str | None:
    """A function as ``module.qualname``; None for a reference a layer has not saved yet."""
    if function is None:
        return None
    return f"{getattr(function, '__module__', '?')}.{getattr(function, '__qualname__', repr(function))}"


def _base(module, name: str) -> str:
    return f"{module.__name__}.{name}"


def _expected(stage: int) -> dict:
    """Every link of the chain after the first ``stage`` layers in the application's order."""
    hardening, review = universal_hardening, universal_frf_review
    separation, validation, cache = cmif_separation, cmif_validation, fast_cache
    load = _base(universal_reader, "load_universal_modal_file")
    frf = _base(universal_reader, "_modes_from_frf_datasets")
    odb = _base(abaqus_bridge, "load_extracted_odb")
    if stage >= 1:
        load = _name(hardening.load_universal_modal_file)
    if stage >= 2:
        frf = _name(review.modes_from_frf_datasets)
    if stage >= 3:
        frf = _name(separation._reviewed_modes_from_frf)
    if stage >= 4:
        frf = _name(validation._validated_modes_from_frf)
    if stage >= 5:
        load, odb = _name(cache._cached_universal_loader), _name(cache._cached_extracted_odb_loader)
    links = {
        "universal_reader.load_universal_modal_file": load,
        "universal_reader._modes_from_frf_datasets": frf,
        "abaqus_bridge.load_extracted_odb": odb,
        "universal_hardening._ORIGINAL_LOAD": _base(universal_reader, "load_universal_modal_file") if stage >= 1
        else None,
        "cmif_separation._ORIGINAL_MODES_FROM_FRF": _name(review.modes_from_frf_datasets) if stage >= 3 else None,
        "cmif_validation._ORIGINAL_MODES_FROM_FRF": _name(separation._reviewed_modes_from_frf) if stage >= 4
        else None,
        "fast_cache._ORIGINAL_UNIVERSAL_LOADER": _name(hardening.load_universal_modal_file) if stage >= 5 else None,
        "fast_cache._ORIGINAL_EXTRACTED_ODB_LOADER": _base(abaqus_bridge, "load_extracted_odb") if stage >= 5
        else None,
    }
    for name, replacement in (("_dataset_type", hardening._dataset_type), ("_mode_from_dataset_55",
                              hardening._safe_mode_55), ("_mode_from_dataset_2414", hardening._safe_mode_2414),
                              ("_detect_frf_peak_indices", hardening._relative_peak_detector),
                              ("_select_frf_group", hardening._safe_select_frf_group),
                              ("_coherence_by_dof", hardening._safe_coherence_by_dof)):
        links[f"universal_reader.{name}"] = _name(replacement) if stage >= 1 else _base(universal_reader, name)
    return links


def _actual() -> dict:
    modules = {module.__name__: module for module in (universal_reader, abaqus_bridge, universal_hardening,
                                                      cmif_separation, cmif_validation, fast_cache)}
    links = {}
    for link in _expected(0):
        module, attribute = link.split(".", 1)
        links[link] = _name(getattr(modules[module], attribute, None))
    return links


def chain_problems() -> list:
    """The differences between the installed importer chain and the application's order (empty when it matches)."""
    installed = installed_layers()
    if installed != LAYER_NAMES[:len(installed)]:
        return [f"installed layers ({', '.join(installed)}) are not a prefix of {', '.join(LAYER_NAMES)}"]
    expected, actual = _expected(len(installed)), _actual()
    return [f"{link} is {actual[link]}, expected {expected[link]}" for link in expected
            if actual[link] != expected[link]]


def ensure_application_importers() -> None:
    """Install the application's importer layers in order; nothing happens when they are already installed.
    Raises ImporterOrderError, before and after installing, when the function chain is not the application's."""
    problems = chain_problems()
    if problems:
        raise ImporterOrderError("The importer layers were installed outside the application's order: "
                                 + "; ".join(problems))
    for _, _, install in IMPORTER_LAYERS:
        install()
    problems = chain_problems()
    if problems:
        raise ImporterOrderError("The installed importer chain is not the application's: " + "; ".join(problems))
