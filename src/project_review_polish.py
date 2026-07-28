from __future__ import annotations


_INSTALLED = False


def install_project_review_polish(app_module) -> None:
    """Keep the normal completion path fast until a real manual decision exists."""
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_apply = application_class._apply_manual_reviews

    def polished_apply(self, refresh: bool = True) -> None:
        if not getattr(self, "manual_reviews", {}):
            self._refresh_review_table()
            return
        original_apply(self, refresh=refresh)

    application_class._apply_manual_reviews = polished_apply
    _INSTALLED = True
