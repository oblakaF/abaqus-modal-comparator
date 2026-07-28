from __future__ import annotations


_INSTALLED = False


def restore_idle_controls(application, *, force: bool = False) -> bool:
    """Restore controls that must be available whenever no analysis is running."""
    if not force and bool(getattr(application, "running", False)):
        return False

    application.running = False

    progress = getattr(application, "progress", None)
    if progress is not None:
        try:
            progress.stop()
        except Exception:
            pass

    run_button = getattr(application, "run_button", None)
    if run_button is not None:
        run_button.configure(state="normal")

    # Opening the workspace does not depend on a completed calculation: the
    # existing handler creates the selected directory when it is missing.
    folder_button = getattr(application, "folder_button", None)
    if folder_button is not None:
        folder_button.configure(state="normal")

    return True


def install_idle_ui_state(app_module) -> None:
    """Ensure project/session restoration cannot leave the main controls disabled."""
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__
    original_apply_project = getattr(application_class, "_apply_project_payload", None)
    original_new_project = getattr(application_class, "_new_project", None)

    def idle_init(self, root) -> None:
        original_init(self, root)
        # No worker can legitimately survive application construction. Always
        # enter the event loop in an explicit idle state.
        restore_idle_controls(self, force=True)

    application_class.__init__ = idle_init

    if original_apply_project is not None:
        def idle_apply_project(self, *args, **kwargs):
            value = original_apply_project(self, *args, **kwargs)
            restore_idle_controls(self)
            return value

        application_class._apply_project_payload = idle_apply_project

    if original_new_project is not None:
        def idle_new_project(self, *args, **kwargs):
            value = original_new_project(self, *args, **kwargs)
            restore_idle_controls(self)
            return value

        application_class._new_project = idle_new_project

    _INSTALLED = True
