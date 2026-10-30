"""NEW-GUI.1: the main window of the new interface (PySide6).

A side navigation (Workspace, Analysis, Status), a workspace with the FE and experimental sources, clear empty
states, and the research archive behind its own command. The window shows the state of
``new_gui.workspace_state`` and computes nothing itself: reading a file, drawing a shape and the frequency
diagnostic are the existing services' work, and each runs only on the user's explicit command.

NEW-GUI.2: **Inspect file** reads the chosen file of one side in a background thread
(``new_gui.preview_model.run_read``) and shows the read content in that side's ``PreviewPanel``. Replacing or
clearing the file, or closing the window, cancels the read; an outcome that is not the current read of the current
file is discarded, never shown.

NEW-GUI.3: below each content panel, a ``ShapePanel`` draws one chosen FE mode or experimental record of the read
preview with the services' own drawing. It is reset whenever its preview goes (file replaced or cleared, Inspect
again, window closed).

NEW-GUI.4: the Analysis page holds a ``DiagnosticPanel``: once both files are read and the user has chosen an
experimental modal set, the explicit command Run frequency diagnostic calls the existing frequency-only service in a
background thread (FREQUENCY_ONLY_DIAGNOSTIC). Its nearest FE frequencies show frequency proximity only and are not
established mode pairs; no physical registration, MAC or Auto-ID is run. A replaced or cleared file, Inspect again,
another set or a closed window cancels it and discards its outcome.

NEW-GUI.5: below it, a ``RegistrationCheckPanel`` checks, only on the explicit command Check reference registration,
whether an accepted archived physical registration applies to the read FE results and the modal set chosen for the
frequency diagnostic (the existing service ``bind_registration_by_fe_geometry``). The registration is not applied:
no MAC, mode pair or orientation is made. It is cancelled and discarded like the diagnostic.

NEW-GUI.6: below it, the ``ComparisonPanel`` workbench: when the check verified an archived registration for exactly
the current data, Run verified modal comparison verifies it again and runs the project's scientific comparator with
that frozen registration, shows the pairs, the MAC matrix, the warnings and the pair drawings, and Export report...
writes the result's report into a folder the user chooses. The frequency diagnostic's result card follows the
workbench. A Materials page shows the project's existing material records, read-only and classified, and File > Choose
a known new experimental source... offers the three working sources of the provenance map (the path only; Inspect
file still reads it).

PLATE-ONLY-R1: a Plate Study page (``PlateStudyPanel``), the research study of one free-free CFRP plate's effective
bending stiffness on the files read in the Workspace (the plate's working source and a member of its FE family, by
SHA-256). It fits nothing, releases no material value and cannot start the iterative estimation (not authorised).
"""

from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QKeySequence, QPalette
from PySide6.QtWidgets import (QApplication, QBoxLayout, QButtonGroup, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from new_gui import APP_NAME, STAGE
from new_gui.archive_dialog import ArchiveDialog
from new_gui.comparison_panel import WIDE_CONTENT, ComparisonPanel
from new_gui.diagnostic_panel import DiagnosticPanel
from new_gui.known_sources_dialog import KnownSourcesDialog
from new_gui.materials_panel import SUBTITLE as MATERIALS_SUBTITLE, MaterialsPanel
from new_gui.plate_study_panel import PlateStudyPanel
from new_gui.preview_model import FAILED, INSPECT, IDLE, READ, READING, STATE_TEXT, InspectSlot, Outcome, run_read
from new_gui.preview_panel import PreviewPanel
from new_gui.registration_check_panel import RegistrationCheckPanel
from new_gui.research_results_panel import ResearchResultsPanel
from new_gui.shape_panel import ShapePanel
from new_gui.workspace_state import (ANALYSIS_NOT_RUN, CHOSEN_NOTE, EMPTY_TEXT, EXPERIMENTAL, FE, KIND_HELP, KIND_TITLE, KINDS, LABEL_HINT, DIALOG_FILTERS, Workspace,
                                     scientific_status)

PAGES = ("Workspace", "Analysis", "Status", "Materials", "Plate Study", "Research Results")
MATERIALS_PAGE = 3
PLATE_PAGE = 4
RESEARCH_PAGE = 5  # PRIORITY-5A: archived research results, read on the page's first show
KNOWN_SOURCES = "Choose a known new experimental source..."
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
#badge[state="read"] { background: #e3f4e8; color: #1e6b37; }
#sectionTitle { font-weight: 600; }
#warnings { color: #7a4b00; }
QTableWidget { background: #ffffff; border: 1px solid #d9dee5; gridline-color: #e4e7eb; }
QHeaderView::section { background: #eef1f5; border: none; border-right: 1px solid #d9dee5; padding: 4px 6px; }
#error { color: #b42318; }
#fileName { font-weight: 600; }
QLineEdit { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 4px; padding: 4px 6px; }
QLineEdit[readOnly="true"] { background: #f8f9fb; }
QPushButton { background: #ffffff; border: 1px solid #c4cdd5; border-radius: 4px; padding: 5px 12px; }
QPushButton:hover { border-color: #2563eb; }
QPushButton:disabled { color: #9aa5b1; border-color: #e4e7eb; }
QPushButton#primary { background: #2563eb; border-color: #2563eb; color: #ffffff; }
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#primary:disabled { background: #e4e7eb; border-color: #e4e7eb; color: #9aa5b1; }
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
        # A long name without spaces cannot wrap: it never widens the page (NEW-GUI.2); the tooltip holds it in full.
        self.file_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.file_name.setMinimumWidth(0)
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
        self.inspect_button = QPushButton(INSPECT)
        self.inspect_button.setObjectName("inspect")
        self.inspect_button.setToolTip("Read the chosen file's modal data with the analysis importer and show them "
                                       "below. Nothing is compared or selected.")
        self.inspect_button.clicked.connect(lambda: window.inspect_file(kind))
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(lambda: window.clear_file(kind))
        buttons.addWidget(self.choose_button)
        buttons.addWidget(self.inspect_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def show_state(self, workspace: Workspace, message: str, slot: Optional[InspectSlot] = None) -> None:
        choice = workspace.choice(self.kind)
        state = slot.state if slot is not None and choice.chosen else IDLE
        self.badge.setText(STATE_TEXT[state] if state != IDLE else choice.status)
        self.badge.setProperty("state", {READ: "read", FAILED: "blocked"}.get(state, "chosen" if choice.chosen
                                                                               else "empty"))
        _restyle(self.badge)
        self.file_name.setText(choice.path.name if choice.chosen else "—")
        self.file_name.setToolTip(choice.path.name if choice.chosen else "")
        self.path.setText(str(choice.path) if choice.chosen else "")
        self.path.setToolTip(str(choice.path) if choice.chosen else "")
        self.path.setCursorPosition(len(self.path.text()))  # a long path shows its end: folder and file name
        self.file_type.setText(choice.file_type if choice.chosen else "—")
        self.note.setVisible(choice.chosen and state == IDLE)
        self.error.setText(message)
        self.error.setVisible(bool(message))
        self.choose_button.setText("Replace file..." if choice.chosen else "Choose file...")
        self.clear_button.setEnabled(choice.chosen)
        self.inspect_button.setEnabled(choice.chosen and state != READING)
        self.inspect_button.setText("Inspect again" if state in (READ, FAILED) else INSPECT)


class _ReadBridge(QObject):
    """Carries a read's outcome from its worker thread to the window's thread (a queued signal)."""

    done = Signal(object)


class MainWindow(QMainWindow):
    """The new interface's main window. ``ask_path(kind, start)`` returns a chosen path or "" (tests replace it)."""

    def __init__(self, *, ask_path: Optional[Callable[[str, str], str]] = None,
                 archive_path: Optional[Path] = None, status_path: Optional[Path] = None,
                 ask_folder: Optional[Callable[[], str]] = None, known_root: Optional[Path] = None,
                 plate_family_root: Optional[Path] = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {STAGE}")
        self.workspace = Workspace()
        self.messages = {kind: "" for kind in KINDS}
        self._ask_path = ask_path or self._dialog_path
        self._archive_path = archive_path
        self._ask_folder = ask_folder
        self._known_root = known_root
        self._plate_family_root = plate_family_root
        self.known_dialog: Optional[KnownSourcesDialog] = None
        self.archive_dialog: Optional[ArchiveDialog] = None
        self.status_rows = scientific_status(status_path)
        self.slots = {kind: InspectSlot() for kind in KINDS}
        self.discarded = 0  # outcomes of cancelled or stale reads, never shown
        self._threads: list[threading.Thread] = []
        self._bridge = _ReadBridge(self)
        self._bridge.done.connect(self._read_done)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.stack.addWidget(self._scroll(self._build_workspace_page()))
        self.stack.addWidget(self._scroll(self._build_analysis_page()))
        self.stack.addWidget(self._scroll(self._build_status_page()))
        self.stack.addWidget(self._scroll(self._build_materials_page()))
        self.stack.addWidget(self._scroll(self._build_plate_page()))
        self.stack.addWidget(self._scroll(self._build_research_page()))
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self.status_text = _label(f"{ANALYSIS_NOT_RUN} · Production Auto-ID {self.status_rows[0].value}", wrap=False)
        self.statusBar().addPermanentWidget(self.status_text)
        self.diagnostic.changed.connect(self._analysis_changed)
        self.diagnostic.set_combo.currentIndexChanged.connect(self._registration_inputs)  # the one shared set choice
        self.registration.changed.connect(self._registration_changed)
        self.comparison.changed.connect(self._analysis_changed)
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
        known = QHBoxLayout()
        self.known_button = QPushButton(KNOWN_SOURCES)
        self.known_button.setObjectName("knownSourcesButton")
        self.known_button.setToolTip("The three fitted working sources of the 2026-10-29 delivery, checked against the "
                                     "provenance map. Only the path is set; nothing is read until Inspect file.")
        self.known_button.clicked.connect(self.open_known_sources)
        known.addWidget(self.known_button)
        known.addStretch(1)
        layout.addLayout(known)
        self.panels = {kind: PreviewPanel(kind) for kind in KINDS}  # full width: the tables need it
        self.shape_panels = {kind: ShapePanel(kind) for kind in KINDS}  # NEW-GUI.3: below each content panel
        for kind in KINDS:
            layout.addWidget(self.panels[kind])
            layout.addWidget(self.shape_panels[kind])
        layout.addStretch(1)
        return page

    def _build_analysis_page(self) -> QWidget:
        page, layout = self._page("Analysis", "A frequency diagnostic of the read FE results and one experimental "
                                              "modal set, a check of archived physical registrations and, only with "
                                              "a verified registration, the scientific comparison of the mode shapes "
                                              "(MAC and mode pairs).")
        self.diagnostic = DiagnosticPanel()  # NEW-GUI.4
        self.analysis_badge = self.diagnostic.badge
        layout.addWidget(self.diagnostic)
        self.registration = RegistrationCheckPanel()  # NEW-GUI.5: uses the diagnostic's set choice
        layout.addWidget(self.registration)
        self.comparison = ComparisonPanel(ask_folder=self._ask_folder)  # NEW-GUI.6: the verified comparison
        layout.addWidget(self.comparison)
        layout.addWidget(self.diagnostic.result_card)  # the long frequency tables follow the workbench
        layout.addStretch(1)
        return page

    def _build_plate_page(self) -> QWidget:
        page, layout = self._page("Plate Study", "Research study of one free-free CFRP plate (PLATE-300x300x1mm): "
                                                 "frequencies, independent shapes, registration status, FE "
                                                 "sensitivities and readiness. No fit and no material value.")
        self.plate = PlateStudyPanel(ask_folder=self._ask_folder, family_root=self._plate_family_root)
        layout.addWidget(self.plate)
        layout.addStretch(1)
        return page

    def _build_research_page(self) -> QWidget:
        page, layout = self._page("Research Results", "The archived results of the real modal matching, the FE "
                                                      "parameter sensitivities and the inverse parameter study "
                                                      "(PRIORITY-1–4): viewing only, nothing is computed.")
        self.research = ResearchResultsPanel()
        layout.addWidget(self.research)
        layout.addStretch(1)
        return page

    def _build_materials_page(self) -> QWidget:
        page, layout = self._page("Materials / Scientific evidence", MATERIALS_SUBTITLE)
        self.materials = MaterialsPanel()  # NEW-GUI.6: read-only; the records are read when the page is shown
        layout.addWidget(self.materials)
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
                                     ("Choose experimental file...", "Ctrl+2", lambda: self.choose_file(EXPERIMENTAL)),
                                     (KNOWN_SOURCES, "Ctrl+3", self.open_known_sources),
                                     ("Inspect FE file", "Ctrl+Shift+1", lambda: self.inspect_file(FE)),
                                     ("Inspect experimental file", "Ctrl+Shift+2",
                                      lambda: self.inspect_file(EXPERIMENTAL))):
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
        if index == RESEARCH_PAGE:
            self.research.load()  # the archived snapshot is read on first show, not at start-up
        if index == MATERIALS_PAGE:
            self.materials.load()  # the project's material records are read on first show, not at start-up
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
        before = self.workspace
        self.workspace, message = self.workspace.choose(kind, path)
        self.messages[kind] = message
        if self.workspace is not before and not message:  # a new or replaced file: the old preview is gone
            self.slots[kind].reset()
        self.refresh()
        if message:
            self.statusBar().showMessage("File not accepted.", 8000)
        return message

    def clear_file(self, kind: str) -> None:
        self.workspace = self.workspace.clear(kind)
        self.messages[kind] = ""
        self.slots[kind].reset()
        self.refresh()

    def inspect_file(self, kind: str) -> bool:
        """Read the chosen file of ``kind`` in a background thread; returns False when nothing is started."""
        choice = self.workspace.choice(kind)
        if not choice.chosen or self.slots[kind].state == READING:
            return False
        token, cancel_event = self.slots[kind].start(choice.path)
        worker = threading.Thread(target=self._read, args=(kind, choice.path, token, cancel_event),
                                  name=f"new-gui-read-{kind}", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        self.refresh()
        self.statusBar().showMessage(f"{KIND_TITLE[kind]}: reading...", 4000)  # short: the name is in the card
        return True

    def _read(self, kind: str, path: Path, token: int, cancel_event: threading.Event) -> None:
        outcome = run_read(kind, path, token, cancel_event)  # worker thread: no widget is touched here
        try:
            self._bridge.done.emit(outcome)
        except RuntimeError:  # the window is already gone
            pass

    def _read_done(self, outcome: Outcome) -> None:
        if not self.slots[outcome.kind].finish(outcome):
            self.discarded += 1  # a cancelled or stale read: the current state is kept
            return
        self.refresh()
        if not outcome.cancelled:
            self.statusBar().showMessage(f"{KIND_TITLE[outcome.kind]}: "
                                         + ("content not read" if outcome.error else "content read"), 8000)

    def reading(self) -> bool:
        return (any(slot.state == READING for slot in self.slots.values())
                or any(thread.is_alive() for thread in self._threads))

    def busy(self) -> bool:
        """A read, a shape drawing, the frequency diagnostic or the registration check is still running."""
        return (self.reading() or any(panel.busy() for panel in self.shape_panels.values())
                or self.diagnostic.busy() or self.registration.busy() or self.comparison.busy()
                or self.plate.busy())

    def wait_for_reads(self, timeout: float = 120.0) -> bool:
        """Process events until no read or drawing is running (tests and checks); returns whether all ended."""
        end = time.monotonic() + timeout
        while self.busy() and time.monotonic() < end:
            QApplication.processEvents()
            time.sleep(0.02)
        QApplication.processEvents()
        return not self.busy()

    def closeEvent(self, event) -> None:
        for slot in self.slots.values():  # running reads are cancelled and their outcomes discarded
            slot.reset()
        for panel in self.shape_panels.values():  # and so are running drawings
            panel.cancel()
        self.diagnostic.cancel()  # and the frequency diagnostic
        self.registration.cancel()  # and the registration check
        self.comparison.cancel()  # and the verified comparison, its drawings included
        self.plate.cancel()  # and the plate study
        super().closeEvent(event)

    def _analysis_changed(self) -> None:
        if not hasattr(self, "comparison"):
            return
        view = self.diagnostic.view
        self.comparison.set_diagnostic(self.diagnostic.slot.outcome.diagnostic if view is not None else None)
        compared = self.comparison.view
        self.diagnostic.show_summary_values()  # never a removed comparison's MAC or pairs
        if compared is not None:  # the summary states the verified comparison, not only the frequency diagnostic
            self.diagnostic.summary_values["MAC"].setText(
                "computed on the registered measured DOFs only (see Verified modal comparison)")
            self.diagnostic.summary_values["Mode pairs"].setText(
                f"{compared.status}: {len(compared.pair_rows)} pair(s), the comparator's assignment")
        shown = self.comparison.status_text or self.diagnostic.status_text
        self.status_text.setText(f"{shown} · Production Auto-ID {self.status_rows[0].value}")

    def _registration_changed(self) -> None:
        if not hasattr(self, "comparison"):
            return
        registration = self.registration.view
        self.comparison.set_registration(registration, self.registration.refusal_text)
        self.materials.set_context(registration.fixture_id if registration is not None else None,
                                   self.diagnostic.fe_preview is not None
                                   and self.diagnostic.experimental_preview is not None)

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

    def open_known_sources(self) -> KnownSourcesDialog:
        """The known new working sources; a chosen, verified one only sets the experimental file's path."""
        self.known_dialog = KnownSourcesDialog(self, self._known_root)
        self.known_dialog.accepted.connect(self._known_source_chosen)
        self.known_dialog.open()
        return self.known_dialog

    def _known_source_chosen(self) -> None:
        if self.known_dialog is not None and self.known_dialog.chosen_path is not None:
            self.choose_file(EXPERIMENTAL, str(self.known_dialog.chosen_path))
            self.show_page(0)

    def _about(self) -> None:
        QMessageBox.about(self, APP_NAME, f"{APP_NAME}\n{STAGE}\n\nChoose your FE results and experimental data, read "
                                          "them with Inspect file and view single mode shapes. On the Analysis page, "
                                          "Run frequency diagnostic compares the frequencies of one experimental "
                                          "modal set with the FE frequencies, only when you click it. The nearest "
                                          "FE frequencies are not established mode pairs. Check reference "
                                          "registration only checks whether an accepted archived physical "
                                          "registration applies to the read data. Only when it is verified, Run "
                                          "verified modal comparison runs the scientific comparator with it (MAC "
                                          "and mode pairs). The Materials page shows existing records only. No "
                                          "Auto-ID is run.")

    # ---------------------------------------------------------------------------------------------- display

    def refresh(self) -> None:
        self.empty_state.setVisible(self.workspace.empty)
        for kind, card in self.cards.items():
            card.show_state(self.workspace, self.messages[kind], self.slots[kind])
            self.panels[kind].show_slot(self.slots[kind], self.workspace.choice(kind).chosen)
            self.shape_panels[kind].set_preview(self._read_preview(kind))
        self.diagnostic.set_inputs(self._read_preview(FE), self._read_preview(EXPERIMENTAL))
        self._registration_inputs()

    def _registration_inputs(self) -> None:
        inputs = (self.diagnostic.fe_preview, self.diagnostic.experimental_preview, self.diagnostic.chosen_set_index())
        self.registration.set_inputs(*inputs)
        identities = {"fe": self._read_identity(FE), "experimental": self._read_identity(EXPERIMENTAL)}
        self.comparison.set_inputs(*inputs, identities)  # a change removes the comparison and its drawings
        self.plate.set_inputs(inputs[0], identities["fe"], inputs[1], identities["experimental"], inputs[2])
        self.research.set_workspace(identities["experimental"], identities["fe"])  # SHA-256 link only
        self._registration_changed()
        self._analysis_changed()

    def _read_identity(self, kind: str):
        """The identity of the file read for the shown preview of ``kind`` (None when not read or not confirmed)."""
        slot = self.slot_of(kind)
        return slot.identity if self._read_preview(kind) is not None else None

    def slot_of(self, kind: str) -> InspectSlot:
        return self.slots[kind]

    def _read_preview(self, kind: str):
        """The preview of the chosen file of ``kind`` when it was read, else None."""
        slot = self.slots[kind]
        return slot.preview if slot.state == READ and self.workspace.choice(kind).chosen else None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        narrow = self.stack.width() < NARROW_WIDTH
        self.sources.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        # the window's own new width (the stack is laid out only later): the content is the width beside the sidebar
        self.comparison.set_narrow(event.size().width() - self.sidebar.sizeHint().width() < WIDE_CONTENT)
