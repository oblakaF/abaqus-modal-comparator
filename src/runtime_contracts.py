from __future__ import annotations

from typing import Callable, Iterable, Tuple


def _owner(value: Callable) -> str:
    return str(getattr(value, "__module__", "<unknown>"))


def verify_runtime_contracts(app_module) -> None:
    """Fail early when import order changes a critical runtime implementation.

    This is a temporary guard while historical install_* layers are folded back
    into explicit components. It makes the current dependency order testable
    instead of allowing a silent collision.
    """
    import abaqus_bridge
    import reporting
    import universal_reader
    from modal_core import compare_modal_datasets as reviewed_facade

    if app_module.compare_modal_datasets is not reviewed_facade:
        raise RuntimeError(
            "Runtime contract failed: app.compare_modal_datasets does not use "
            "the reviewed quality-control facade."
        )

    expected: Iterable[Tuple[str, Callable, str]] = (
        (
            "ModalComparatorApp._worker",
            app_module.ModalComparatorApp._worker,
            "runtime_hardening",
        ),
        (
            "universal_reader.load_universal_modal_file",
            universal_reader.load_universal_modal_file,
            "fast_cache",
        ),
        (
            "abaqus_bridge.load_extracted_odb",
            abaqus_bridge.load_extracted_odb,
            "fast_cache",
        ),
        (
            "reporting.render_pair_images",
            reporting.render_pair_images,
            "amplitude_correlation",
        ),
    )
    failures = [
        f"{name}: expected {module_name}, got {_owner(value)}"
        for name, value, module_name in expected
        if _owner(value) != module_name
    ]
    if failures:
        raise RuntimeError(
            "Runtime patch-stack contract failed:\n- " + "\n- ".join(failures)
        )
