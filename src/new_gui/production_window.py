"""UNIVERSAL-UI-2: the program's window, for any FE model and any experimental data.

GUI-UX-R1: four pages: Analyze, Review, MAC / Points and Materials, each with its own scrolling.

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
from new_gui.analyze_panel import (AnalyzePanel, CLOSE_PROJECT, OPEN_PROJECT, RUNNING, SAVE_PROJECT, SAVE_PROJECT_AS,
                                   SNAPSHOT_BADGE, SUBTITLE as ANALYZE_SUBTITLE)
from new_gui.mac_points_panel import MacPointsPanel
from new_gui.materials_status_panel import MaterialsStatusPanel, SUBTITLE as MATERIALS_SUBTITLE
from new_gui.materials_workspace import MaterialsWorkspace
from new_gui.review_panel import ReviewPanel
from new_gui.workspace_state import EXPERIMENTAL, FE

PAGES = ("Analyze", "Review", "MAC / Points", "Materials")
ANALYZE_PAGE, REVIEW_PAGE, MAC_PAGE, MATERIALS_PAGE = 0, 1, 2, 3
MAC_SUBTITLE = "Mode pairs and MAC, what they rest on, and why they may be missing. Nothing here is computed from a manual choice."
MATERIALS_PAGE_SUBTITLE = "Choose an ODB and a UNV/UFF for this page, or reuse the two from Analyze. Read-only: no value is issued."
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
        self.analyze = AnalyzePanel(**dict(analyze_options or {}), external_results=True)
        self.materials = MaterialsStatusPanel()
        self.review = ReviewPanel(self.analyze)
        self.mac_points = MacPointsPanel(self.analyze)
        self.materials_workspace = MaterialsWorkspace(self.analyze, self.materials)
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.stack.addWidget(_page(PAGES[ANALYZE_PAGE], ANALYZE_SUBTITLE, self.analyze))
        review = QScrollArea()  # only a very short window scrolls the whole page; the panes scroll by themselves
        review.setWidgetResizable(True)
        self.review.setMinimumHeight(600)
        review.setWidget(self.review)
        self.stack.addWidget(review)
        self.stack.addWidget(_page(PAGES[MAC_PAGE], MAC_SUBTITLE, self.mac_points))
        self.stack.addWidget(_page(PAGES[MATERIALS_PAGE], MATERIALS_PAGE_SUBTITLE, self.materials_workspace))
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self.analyze.changed.connect(self._project_changed)
        self.analyze.analysis_ready.connect(self._result_ready)
        self.analyze.analysis_blocked.connect(lambda: self.show_page(ANALYZE_PAGE))
        self.analyze.message_changed.connect(self.statusBar().showMessage)
        self._project_changed()
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
            button.setObjectName("nav" + "".join(c for c in text if c.isalnum()))
            self.nav.addButton(button, index)
            layout.addWidget(button)
        self.nav.idClicked.connect(self.show_page)
        layout.addStretch(1)
        return bar

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&File")
        self.project_actions = {}
        for key, text, shortcut, slot in (
                ("open", OPEN_PROJECT, "Ctrl+O", lambda: self._project(self.analyze.open_project)),
                ("save", SAVE_PROJECT, "Ctrl+S", lambda: self.analyze.save_project()),  # the status bar shows the outcome
                ("save_as", SAVE_PROJECT_AS, "Ctrl+Shift+S",  # Windows has no standard key for Save As
                 lambda: self.analyze.save_project_as()),
                ("close", CLOSE_PROJECT, None, lambda: self._project(self.analyze.close_project))):
            action = QAction(text, self)
            if shortcut is not None:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            menu.addAction(action)
            self.project_actions[key] = action
        menu.addSeparator()
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

    def _project(self, command) -> None:
        self.show_page(ANALYZE_PAGE)
        command()

    def _result_ready(self) -> None:
        """From Analyze to the result; a comparison started on MAC / Points, or work on Materials, stays where it is."""
        if self.stack.currentIndex() == ANALYZE_PAGE:
            self.show_page(REVIEW_PAGE)
        self.mac_points.refresh_evidence()

    def _project_changed(self) -> None:
        panel = self.analyze
        for key in ("save", "save_as"):
            self.project_actions[key].setEnabled(panel.can_save())
        self.project_actions["open"].setEnabled(panel.state != RUNNING)
        self.project_actions["close"].setEnabled(panel.state != RUNNING)
        name = f"{panel.project_path.name} - " if panel.project_path else ""
        saved = f"{SNAPSHOT_BADGE} - " if panel.snapshot is not None else ""
        self.setWindowTitle(f"{saved}{name}{APP_NAME}")

    def _choose(self, kind: str) -> None:
        self.show_page(ANALYZE_PAGE)
        self.analyze.choose_file(kind)

    def show_page(self, index: int) -> None:
        if index == MAC_PAGE:
            self.mac_points.refresh_evidence()  # the manual-choice count follows the Review page
        self.stack.setCurrentIndex(index)
        self.nav.button(index).setChecked(True)

    def busy(self) -> bool:
        return self.analyze.busy() or self.mac_points.busy() or self.materials_workspace.busy()

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
        self.mac_points.shutdown()
        self.materials_workspace.shutdown()
        super().closeEvent(event)


__all__ = ["ANALYZE_PAGE", "MAC_PAGE", "MATERIALS_PAGE", "PAGES", "ProductionWindow", "REVIEW_PAGE"]
