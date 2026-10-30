"""NEW-GUI.6: the Materials / Scientific evidence page (PySide6).

A read-only view of the project's existing material records (``new_gui.materials_model``), in the three classes that
are never mixed: material identification (governed verdicts), specimen engineering calibration, and model input /
diagnostic estimates. On top, what applies to the data read now: related only through the archived fixture the
registration check verified, otherwise NOT_AVAILABLE. The page runs nothing: no Auto-ID, no identification and no
fit; it has no command. The records are read when the page is first shown, not at start-up.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from new_gui import materials_model as mm
from new_gui.diagnostic_panel import DiagnosticTable

SUBTITLE = ("The project's existing results about material parameters, read-only and classified. Nothing is "
            "identified, fitted or run here, and no value is derived from a frequency.")


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if wrap:
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setMinimumWidth(0)
    return label


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class MaterialsPanel(QWidget):
    """The page's content: the relevance for the read data, then one card per evidence class."""

    def __init__(self, repo_root=None):
        super().__init__()
        self._repo_root = repo_root
        self.evidence: Optional[mm.MaterialsView] = None
        self.error = ""
        self.verified_fixture: Optional[str] = None
        self.data_read = False
        self.tables: dict[str, DiagnosticTable] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        card, inner = _card()
        inner.addWidget(_label("For the data read now", "cardTitle"))
        self.relevance_badge = _label(mm.NOT_AVAILABLE, "badge", wrap=False)
        inner.addWidget(self.relevance_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.relevance = _label("", "")
        inner.addWidget(self.relevance)
        self.historical = _label("", "hint")  # NEW-GUI.6-F1: a historical record, named with its own provenance
        inner.addWidget(self.historical)
        layout.addWidget(card)
        self.classes_box = QWidget()
        self.classes_layout = QVBoxLayout(self.classes_box)
        self.classes_layout.setContentsMargins(0, 0, 0, 0)
        self.classes_layout.setSpacing(12)
        layout.addWidget(self.classes_box)
        self._refresh_relevance()

    def load(self) -> None:
        """Read the project's material records once (first show of the page)."""
        if self.evidence is not None or self.error:
            return
        try:
            self.evidence = mm.load_material_evidence(self._repo_root)
        except Exception as error:  # noqa: BLE001  (a record that cannot be read is stated, never invented)
            self.error = f"The material records could not be read ({type(error).__name__}: {error})."
        self._build_classes()
        self._refresh_relevance()

    def set_context(self, verified_fixture: Optional[str], data_read: bool) -> None:
        """The archived fixture verified for the read data (or None) and whether both sides are read."""
        if (verified_fixture, data_read) != (self.verified_fixture, self.data_read):
            self.verified_fixture, self.data_read = verified_fixture, data_read
            self._refresh_relevance()

    def _refresh_relevance(self) -> None:
        historical = ""
        if self.evidence is None:
            status, text = mm.NOT_AVAILABLE, (self.error or "The project's material records are read when this "
                                              "page is shown.")
        else:
            relevance = mm.current_relevance(self.evidence, self.verified_fixture, self.data_read)
            status, text, historical = relevance.status, relevance.text, relevance.historical
        self.historical.setText(historical)
        self.historical.setVisible(bool(historical))
        self.relevance_badge.setText(status)
        self.relevance_badge.setProperty("state", "blocked")
        _restyle(self.relevance_badge)
        self.relevance.setText(text)

    def _build_classes(self) -> None:
        if self.evidence is None:
            self.classes_layout.addWidget(_label(self.error, "error"))
            return
        for klass in mm.CLASSES:
            card, inner = _card()
            inner.addWidget(_label(mm.CLASS_TITLE[klass], "cardTitle"))
            badge = _label(klass, "badge", wrap=False)
            inner.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
            inner.addWidget(_label(mm.CLASS_NOTE[klass], "hint"))
            rows = [row.cells() for row in self.evidence.of(klass)]
            if rows:
                table = DiagnosticTable(mm.HEADERS, rows, stretch=5, capped=(3, 4, 6, 8, 9),
                                        text_columns=(0, 3, 4, 6, 7, 8, 9))
                table.setObjectName(f"evidence{klass}")
                self.tables[klass] = table
                inner.addWidget(table)
            else:
                inner.addWidget(_label("None.", "hint"))
            self.classes_layout.addWidget(card)
        if self.evidence.problems:
            self.classes_layout.addWidget(_label("Records not shown:\n" + "\n".join(
                f"• {line}" for line in self.evidence.problems), "error"))
        self.classes_layout.addWidget(_label("\n".join(self.evidence.notes), "hint"))


__all__ = ["MaterialsPanel", "SUBTITLE"]
