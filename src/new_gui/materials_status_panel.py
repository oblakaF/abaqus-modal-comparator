"""UNIVERSAL-UI-2: the Materials page of the program's window: a fixed, truthful state.

This program compares modal data and identifies no material property, so the page holds no value, no estimate and no
stored record, and it reads nothing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from new_gui.diagnostic_panel import DiagnosticTable

SUBTITLE = "Свойства материала вашей модели."
NOT_AVAILABLE = "НЕДОСТУПНО"
STATE_TEXT = "Свойства материала не идентифицированы. Программа сравнивает модальные данные FE и эксперимента и не оценивает " \
             "свойства материала."
PARAMETERS = ("E1", "E2", "G12")
NOT_IDENTIFIED = "Не идентифицировано"
HEADERS = ("Параметр", "Значение")
LIMIT_TEXT = "Частоты, MAC и пары мод не устанавливают значение материала."


def _text(text: str, name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


class MaterialsStatusPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(8)
        self.badge = QLabel(NOT_AVAILABLE)
        self.badge.setObjectName("badge")
        inner.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addWidget(_text(STATE_TEXT))
        self.table = DiagnosticTable(HEADERS, tuple((name, NOT_IDENTIFIED) for name in PARAMETERS), 1, text_columns=(0,))
        inner.addWidget(self.table)
        inner.addWidget(_text(LIMIT_TEXT, "hint"))
        layout.addWidget(card)


__all__ = ["MaterialsStatusPanel", "SUBTITLE"]
