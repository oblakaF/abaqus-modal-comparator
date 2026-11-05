"""The look of the program's windows: one light theme, whatever the Windows colour mode."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from new_gui import APP_NAME

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
#detailsToggle { background: transparent; border: none; color: #2563eb; padding: 2px 0; text-align: left; }
#detailsToggle:hover { text-decoration: underline; }
QProgressBar { background: #e4e7eb; border: none; border-radius: 3px; }
QProgressBar::chunk { background: #2563eb; border-radius: 3px; }
QTabWidget::pane { border: none; }
#materialsTabs::tab { background: #e9edf2; border: 1px solid #d9dee5; border-bottom: none; border-top-left-radius: 6px;
                      border-top-right-radius: 6px; padding: 8px 18px; margin-right: 2px; color: #3e4c59; }
#materialsTabs::tab:selected { background: #ffffff; color: #1d4ed8; font-weight: 600; }
#materialsTabs::tab:hover:!selected { background: #f4f6f9; }
QToolButton#sectionToggle { background: transparent; border: none; font-weight: 600; padding: 4px 2px; }
QToolButton#sectionToggle:hover { color: #1d4ed8; }
#summaryCaption { color: #52606d; }
#summaryValue { font-weight: 600; }
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
