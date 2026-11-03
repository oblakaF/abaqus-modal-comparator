"""UNIVERSAL-UI-2: the program's window: the Analyze and Materials pages, for any FE model and any experimental data.

It imports none of the earlier pages, so nothing of them can appear here. ``new_gui.window.MainWindow`` keeps them and
opens only with an explicit command-line option (``new_gui.__main__``).
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from new_gui import APP_NAME
from new_gui.analyze_panel import AnalyzePanel, SUBTITLE as ANALYZE_SUBTITLE
from new_gui.materials_status_panel import MaterialsStatusPanel, SUBTITLE as MATERIALS_SUBTITLE
from new_gui.workspace_state import EXPERIMENTAL, FE

PAGES = ("Analyze", "Materials")
ANALYZE_PAGE, MATERIALS_PAGE = 0, 1
ABOUT = ("Choose an Abaqus .odb and an experimental .unv or .uff, then click Analyze. Mode pairs and MAC appear only "
         "with a verified physical registration; otherwise the result is a frequency comparison. No FE analysis is "
         "solved.")


def _page(title: str, subtitle: str, content: QWidget) -> QScrollArea:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    layout.addWidget(heading)
    note = QLabel(subtitle)
    note.setObjectName("subtitle")
    note.setWordWrap(True)
    layout.addWidget(note)
    layout.addWidget(content)
    layout.addStretch(1)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(page)
    return area


class ProductionWindow(QMainWindow):
    """``analyze_options`` are ``AnalyzePanel``'s hooks (tests replace the dialogs and the Abaqus runner)."""

    def __init__(self, *, analyze_options: Optional[dict] = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.analyze = AnalyzePanel(**dict(analyze_options or {}))
        self.materials = MaterialsStatusPanel()
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.stack.addWidget(_page(PAGES[ANALYZE_PAGE], ANALYZE_SUBTITLE, self.analyze))
        self.stack.addWidget(_page(PAGES[MATERIALS_PAGE], MATERIALS_SUBTITLE, self.materials))
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self.setMinimumSize(560, 420)
        self._fit_to_screen()
        self.show_page(ANALYZE_PAGE)

    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setMinimumWidth(160)
        bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)
        name = QLabel("Modal Comparator")
        name.setObjectName("appName")
        layout.addWidget(name)
        layout.addSpacing(16)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for index, text in enumerate(PAGES):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName(f"nav{text}")
            self.nav.addButton(button, index)
            layout.addWidget(button)
        self.nav.idClicked.connect(self.show_page)
        layout.addStretch(1)
        return bar

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&File")
        for text, shortcut, slot in (("Choose FE file...", "Ctrl+1", lambda: self._choose(FE)),
                                     ("Choose experimental file...", "Ctrl+2", lambda: self._choose(EXPERIMENTAL))):
            action = QAction(text, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.addSeparator()
        close = QAction("Exit", self)
        close.setShortcut(QKeySequence.StandardKey.Quit)
        close.triggered.connect(self.close)
        menu.addAction(close)
        about = QAction("About", self)
        about.triggered.connect(lambda: QMessageBox.about(self, APP_NAME, f"{APP_NAME}\n\n{ABOUT}"))
        self.menuBar().addMenu("&Help").addAction(about)

    def _fit_to_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1100, 760)
            return
        free = screen.availableGeometry()
        self.resize(max(self.minimumWidth(), min(1180, int(free.width() * 0.9))),
                    max(self.minimumHeight(), min(800, int(free.height() * 0.9))))

    def _choose(self, kind: str) -> None:
        self.show_page(ANALYZE_PAGE)
        self.analyze.choose_file(kind)

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav.button(index).setChecked(True)

    def busy(self) -> bool:
        return self.analyze.busy()

    def wait_for_reads(self, timeout: float = 120.0) -> bool:
        """Process events until nothing runs (tests and checks); returns whether all ended."""
        end = time.monotonic() + timeout
        while self.busy() and time.monotonic() < end:
            QApplication.processEvents()
            time.sleep(0.02)
        QApplication.processEvents()
        return not self.busy()

    def closeEvent(self, event) -> None:
        self.analyze.shutdown()  # the running step, its owned Abaqus process and its drawings
        super().closeEvent(event)


__all__ = ["ANALYZE_PAGE", "MATERIALS_PAGE", "PAGES", "ProductionWindow"]
