"""NEW-GUI.1: the main window of the new interface (PySide6).

A side navigation (Workspace, Analysis, Status), a workspace with the FE and experimental sources, clear empty
states, and the research archive behind its own command. The window shows the state of
``new_gui.workspace_state``; it runs no analysis and computes nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QGuiApplication, QKeySequence, QPalette
from PySide6.QtWidgets import (QApplication, QBoxLayout, QButtonGroup, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from new_gui import APP_NAME, STAGE
from new_gui.archive_dialog import ArchiveDialog
from new_gui.workspace_state import (ANALYSIS_NOTE, ANALYSIS_NOT_RUN, CHOSEN_NOTE, EMPTY_TEXT, EXPERIMENTAL, FE,
                                     KIND_HELP, KIND_TITLE, KINDS, LABEL_HINT, DIALOG_FILTERS, Workspace,
                                     scientific_status)

PAGES = ("Workspace", "Analysis", "Status")
DIALOG_TITLES = {FE: "Choose the FE results file", EXPERIMENTAL: "Choose the experimental data file"}
OPEN_ARCHIVE = "Open research archive..."
NARROW_WIDTH = 760  # below this content width the two source cards are stacked
STYLE = """
QWidget { color: #1f2933; font-size: 10pt; }
QMainWindow, #content, QScrollArea, QScrollArea > QWidget > QWidget { background: #f4f6f9; }
QScrollArea { border: none; }
#sidebar { background: #1f2a37; }
#sidebar QLabel { color: #e4e7eb; }
#appName { font-size: 11pt; font-weight: 600; }
#stage { color: #9aa5b1; font-size: 9pt; }
#sidebar QPushButton { color: #e4e7eb; background: transparent; border: none; border-radius: 6px;
                       padding: 8px 12px; text-align: left; }
#sidebar QPushButton:hover { background: #323f4b; }
#sidebar QPushButton:checked { background: #3e4c59; font-weight: 600; }
#sidebar QPushButton#archiveButton { border: 1px solid #52606d; text-align: center; }
#pageTitle { font-size: 16pt; font-weight: 600; }
#subtitle, #hint { color: #52606d; }
#card, #emptyState { background: #ffffff; border: 1px solid #d9dee5; border-radius: 8px; }
#emptyState { background: #eef4ff; border-color: #bcd0f7; }
#cardTitle { font-size: 12pt; font-weight: 600; }
#badge { border-radius: 10px; padding: 2px 10px; background: #e4e7eb; color: #3e4c59; }
#badge[state="chosen"] { background: #fff4d6; color: #7a5200; }
#badge[state="blocked"] { background: #fde8e8; color: #9b1c1c; }
#error { color: #b42318; }
#fileName { font-weight: 600; }
QLineEdit { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 4px; padding: 4px 6px; }
QLineEdit[readOnly="true"] { background: #f8f9fb; }
QPushButton { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 4px; padding: 5px 12px; }
QPushButton:hover { border-color: #2563eb; }
QPushButton:disabled { color: #9aa5b1; border-color: #e4e7eb; }
QPushButton#primary { background: #2563eb; border-color: #2563eb; color: #ffffff; }
QPushButton#primary:hover { background: #1d4ed8; }
QStatusBar { background: #e9edf2; color: #3e4c59; }
QMenuBar { background: #ffffff; border-bottom: 1px solid #d9dee5; }
QMenuBar::item:selected, QMenu::item:selected { background: #2563eb; color: #ffffff; }
QMenu { background: #ffffff; border: 1px solid #d9dee5; }
QDialog { background: #f4f6f9; }
"""


PALETTE = {  # one light theme, whatever the Windows colour mode (a dark system palette would hide dark text)
    QPalette.ColorRole.Window: "#f4f6f9", QPalette.ColorRole.WindowText: "#1f2933",
    QPalette.ColorRole.Base: "#ffffff", QPalette.ColorRole.AlternateBase: "#f8f9fb",
    QPalette.ColorRole.Text: "#1f2933", QPalette.ColorRole.Button: "#ffffff",
    QPalette.ColorRole.ButtonText: "#1f2933", QPalette.ColorRole.Highlight: "#2563eb",
    QPalette.ColorRole.HighlightedText: "#ffffff", QPalette.ColorRole.ToolTipBase: "#ffffff",
    QPalette.ColorRole.ToolTipText: "#1f2933", QPalette.ColorRole.PlaceholderText: "#7b8794",
    QPalette.ColorRole.Link: "#2563eb", QPalette.ColorRole.BrightText: "#ffffff",
}


def light_palette() -> QPalette:
    palette = QPalette()
    for role, colour in PALETTE.items():
        palette.setColor(role, QColor(colour))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#9aa5b1"))
    return palette


def create_application(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    if hasattr(app.styleHints(), "setColorScheme"):  # Qt 6.8+
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")  # the same look under any Windows theme; the colours are set by PALETTE and STYLE
    app.setPalette(light_palette())
    app.setStyleSheet(STYLE)
    return app


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


class SourceCard(QFrame):
    """One source of the workspace: its state, path, type and the choose / replace / clear actions."""

    def __init__(self, kind: str, window: "MainWindow"):
        super().__init__()
        self.kind = kind
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(_label(KIND_TITLE[kind], "cardTitle"))
        self.badge = _label("", "badge", wrap=False)  # below the title: a narrow window keeps both readable
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(_label(KIND_HELP[kind], "hint"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.addWidget(_label("File", wrap=False), 0, 0, Qt.AlignmentFlag.AlignTop)
        self.file_name = _label("", "fileName")  # the name stays readable when a long path is cut off
        grid.addWidget(self.file_name, 0, 1)
        grid.addWidget(_label("Path", wrap=False), 1, 0)
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setObjectName("path")
        self.path.setPlaceholderText("No file chosen")
        grid.addWidget(self.path, 1, 1)
        grid.addWidget(_label("Type", wrap=False), 2, 0, Qt.AlignmentFlag.AlignTop)
        self.file_type = _label()
        grid.addWidget(self.file_type, 2, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.note = _label(CHOSEN_NOTE, "hint")
        layout.addWidget(self.note)
        self.error = _label("", "error")
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        self.choose_button = QPushButton()
        self.choose_button.setObjectName("primary")
        self.choose_button.clicked.connect(lambda: window.choose_file(kind))
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(lambda: window.clear_file(kind))
        buttons.addWidget(self.choose_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def show_state(self, workspace: Workspace, message: str) -> None:
        choice = workspace.choice(self.kind)
        self.badge.setText(choice.status)
        self.badge.setProperty("state", "chosen" if choice.chosen else "empty")
        _restyle(self.badge)
        self.file_name.setText(choice.path.name if choice.chosen else "—")
        self.path.setText(str(choice.path) if choice.chosen else "")
        self.path.setToolTip(str(choice.path) if choice.chosen else "")
        self.path.setCursorPosition(len(self.path.text()))  # a long path shows its end: folder and file name
        self.file_type.setText(choice.file_type if choice.chosen else "—")
        self.note.setVisible(choice.chosen)
        self.error.setText(message)
        self.error.setVisible(bool(message))
        self.choose_button.setText("Replace file..." if choice.chosen else "Choose file...")
        self.clear_button.setEnabled(choice.chosen)


class MainWindow(QMainWindow):
    """The new interface's main window. ``ask_path(kind, start)`` returns a chosen path or "" (tests replace it)."""

    def __init__(self, *, ask_path: Optional[Callable[[str, str], str]] = None,
                 archive_path: Optional[Path] = None, status_path: Optional[Path] = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {STAGE}")
        self.workspace = Workspace()
        self.messages = {kind: "" for kind in KINDS}
        self._ask_path = ask_path or self._dialog_path
        self._archive_path = archive_path
        self.archive_dialog: Optional[ArchiveDialog] = None
        self.status_rows = scientific_status(status_path)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.stack.addWidget(self._scroll(self._build_workspace_page()))
        self.stack.addWidget(self._scroll(self._build_analysis_page()))
        self.stack.addWidget(self._scroll(self._build_status_page()))
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self.status_text = _label(f"{ANALYSIS_NOT_RUN} · Production Auto-ID {self.status_rows[0].value}", wrap=False)
        self.statusBar().addPermanentWidget(self.status_text)
        self.setMinimumSize(560, 420)
        self._fit_to_screen()
        self.show_page(0)
        self.refresh()

    # ---------------------------------------------------------------------------------------------- building

    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setMinimumWidth(180)  # otherwise as wide as its widest text needs, whatever the font size
        bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)
        layout.addWidget(_label("Modal Comparator", "appName"))
        layout.addWidget(_label(STAGE, "stage"))
        layout.addSpacing(16)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for index, name in enumerate(PAGES):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setObjectName(f"nav{name}")
            self.nav.addButton(button, index)
            layout.addWidget(button)
        self.nav.idClicked.connect(self.show_page)
        layout.addStretch(1)
        self.archive_button = QPushButton(OPEN_ARCHIVE)
        self.archive_button.setObjectName("archiveButton")
        self.archive_button.setToolTip("Read-only list of the laboratory's specimen records. It changes nothing in "
                                       "your workspace.")
        self.archive_button.clicked.connect(self.open_research_archive)
        layout.addWidget(self.archive_button)
        return bar

    @staticmethod
    def _scroll(page: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(page)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # a last resort on very small screens
        return area

    @staticmethod
    def _page(title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(_label(title, "pageTitle"))
        layout.addWidget(_label(subtitle, "subtitle"))
        return page, layout

    def _build_workspace_page(self) -> QWidget:
        page, layout = self._page("Workspace", "Your own FE results and experimental data. No laboratory archive "
                                               "record is needed.")
        self.empty_state = QFrame()
        self.empty_state.setObjectName("emptyState")
        empty = QVBoxLayout(self.empty_state)
        empty.setContentsMargins(16, 12, 16, 12)
        self.empty_text = _label(EMPTY_TEXT)
        empty.addWidget(self.empty_text)
        layout.addWidget(self.empty_state)

        label_card, label_layout = _card()
        label_layout.addWidget(_label("Specimen name (optional)", "cardTitle"))
        self.label_edit = QLineEdit()
        self.label_edit.setObjectName("specimenLabel")
        self.label_edit.setPlaceholderText("For example: plate A, second measurement")
        self.label_edit.setClearButtonEnabled(True)
        self.label_edit.textChanged.connect(self._label_changed)
        label_layout.addWidget(self.label_edit)
        label_layout.addWidget(_label(LABEL_HINT, "hint"))
        layout.addWidget(label_card)

        self.cards = {kind: SourceCard(kind, self) for kind in KINDS}
        self.sources = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.sources.setSpacing(12)
        for kind in KINDS:
            self.sources.addWidget(self.cards[kind], 1, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(self.sources)
        layout.addStretch(1)
        return page

    def _build_analysis_page(self) -> QWidget:
        page, layout = self._page("Analysis", "The comparison of FE and experimental modes.")
        card, inner = _card()
        head = QHBoxLayout()
        head.addWidget(_label("Result", "cardTitle"), 1)
        head.addStretch(1)
        self.analysis_badge = _label(ANALYSIS_NOT_RUN, "badge", wrap=False)
        head.addWidget(self.analysis_badge)
        inner.addLayout(head)
        inner.addWidget(_label(ANALYSIS_NOTE))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        for row, (caption, value) in enumerate((("Frequencies", "not computed"), ("MAC", "not computed"),
                                                ("Mode pairs", "none"))):
            grid.addWidget(_label(caption, wrap=False), row, 0)
            grid.addWidget(_label(value, "hint"), row, 1)
        grid.setColumnStretch(1, 1)
        inner.addLayout(grid)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_status_page(self) -> QWidget:
        page, layout = self._page("Status", "The scientific status as recorded by the project. This interface shows "
                                            "it and changes none of it.")
        self.status_badges = {}
        for row in self.status_rows:
            card, inner = _card()
            inner.addWidget(_label(row.caption, "cardTitle"))
            badge = _label(row.value, "badge", wrap=False)
            badge.setProperty("state", "blocked")
            self.status_badges[row.caption] = badge
            inner.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
            inner.addWidget(_label(row.note, "hint"))
            layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&File")
        for text, shortcut, slot in (("Choose FE file...", "Ctrl+1", lambda: self.choose_file(FE)),
                                     ("Choose experimental file...", "Ctrl+2", lambda: self.choose_file(EXPERIMENTAL))):
            action = QAction(text, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.addSeparator()
        archive = QAction(OPEN_ARCHIVE, self)
        archive.triggered.connect(self.open_research_archive)
        menu.addAction(archive)
        menu.addSeparator()
        close = QAction("Exit", self)
        close.setShortcut(QKeySequence.StandardKey.Quit)
        close.triggered.connect(self.close)
        menu.addAction(close)
        about = QAction("About", self)
        about.triggered.connect(self._about)
        self.menuBar().addMenu("&Help").addAction(about)

    def _fit_to_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1100, 760)
            return
        free = screen.availableGeometry()
        self.resize(max(self.minimumWidth(), min(1180, int(free.width() * 0.9))),
                    max(self.minimumHeight(), min(800, int(free.height() * 0.9))))

    # ---------------------------------------------------------------------------------------------- actions

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav.button(index).setChecked(True)

    def _dialog_path(self, kind: str, start: str) -> str:
        path, _filter = QFileDialog.getOpenFileName(self, DIALOG_TITLES[kind], start, DIALOG_FILTERS[kind])
        return path

    def choose_file(self, kind: str, path: Optional[str] = None) -> str:
        """Choose (or replace) the file of one side; with no path the file dialog asks. Returns the message shown."""
        if path is None:
            current = self.workspace.choice(kind)
            path = self._ask_path(kind, str(current.path.parent) if current.chosen else "")
        if path is None or not str(path).strip():  # the dialog was cancelled: nothing changes
            return ""
        self.workspace, message = self.workspace.choose(kind, path)
        self.messages[kind] = message
        self.refresh()
        if message:
            self.statusBar().showMessage("File not accepted.", 8000)
        return message

    def clear_file(self, kind: str) -> None:
        self.workspace = self.workspace.clear(kind)
        self.messages[kind] = ""
        self.refresh()

    def _label_changed(self, text: str) -> None:
        self.workspace = self.workspace.with_label(text)

    def open_research_archive(self) -> ArchiveDialog:
        """Open the read-only archive (it is read anew each time it is opened). Nothing in the workspace changes."""
        if self.archive_dialog is not None and self.archive_dialog.isVisible():
            self.archive_dialog.raise_()
            self.archive_dialog.activateWindow()
            return self.archive_dialog
        self.archive_dialog = ArchiveDialog(self, self._archive_path)
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            free = screen.availableGeometry()
            self.archive_dialog.resize(min(self.archive_dialog.width(), int(free.width() * 0.9)),
                                       min(self.archive_dialog.height(), int(free.height() * 0.9)))
        self.archive_dialog.show()
        return self.archive_dialog

    def _about(self) -> None:
        QMessageBox.about(self, APP_NAME, f"{APP_NAME}\n{STAGE}\n\nChoose your FE results and experimental data. "
                                          "This preview runs no analysis.")

    # ---------------------------------------------------------------------------------------------- display

    def refresh(self) -> None:
        self.empty_state.setVisible(self.workspace.empty)
        for kind, card in self.cards.items():
            card.show_state(self.workspace, self.messages[kind])

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        narrow = self.stack.width() < NARROW_WIDTH
        self.sources.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
