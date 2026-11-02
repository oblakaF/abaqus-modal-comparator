"""PRIORITY-0 / RC6: the dialog that extracts the modal results of an Abaqus ``.odb`` (PySide6).

It shows the ODB, the Abaqus launcher found (or why none was found and how to fix it), the results folder, the
mode range and the free space; nothing starts until the user clicks Extract modal results and confirms. The
extraction (``services.odb_import_service.run_extraction``) runs in a worker thread with its progress lines and a
Cancel button; its outcome is shown, and the window takes the package's ``manifest.json`` as the FE file.
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from new_gui import odb_import_model as om
from services import odb_import_service as svc


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class _Bridge(QObject):
    progress = Signal(int, str)
    done = Signal(object)


class OdbImportDialog(QDialog):
    """``manifest_path`` holds the extracted package's manifest after a finished run (the dialog stays open until the
    user closes it with Use this package or Close). ``ask_folder`` / ``ask_launcher`` are replaced in tests."""

    def __init__(self, odb_path, parent=None, *, results_folder: Optional[Path] = None,
                 ask_folder: Optional[Callable[[str], str]] = None, ask_launcher: Optional[Callable[[str], str]] = None,
                 runner=None, confirm: Optional[Callable[[], bool]] = None, discover=None):
        super().__init__(parent)
        self.setWindowTitle(om.TITLE)
        self.setObjectName("odbImportDialog")
        self.odb_path = Path(odb_path)
        self._ask_folder = ask_folder or self._dialog_folder
        self._ask_launcher = ask_launcher or self._dialog_launcher
        self._runner = runner
        self._confirm = confirm or self._dialog_confirm
        self._discover = discover
        self.slot = om.ImportSlot()
        self.plan = None
        self.plan_error = ""
        self.manifest_path: Optional[Path] = None
        self._threads: list = []
        self._bridge = _Bridge(self)
        self._bridge.progress.connect(self._progress)
        self._bridge.done.connect(self._done)

        layout = QVBoxLayout(self)
        layout.addWidget(_label(om.TITLE, "cardTitle"))
        layout.addWidget(_label(om.NOTE, "hint"))
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.addWidget(_label("ODB"), 0, 0)
        form.addWidget(_label(str(self.odb_path), "fileName"), 0, 1, 1, 2)
        form.addWidget(_label("Abaqus launcher"), 1, 0)
        self.launcher = QLineEdit()
        self.launcher.setObjectName("abaqusLauncher")
        self.launcher.setPlaceholderText("detected automatically; or Browse to abaqus.bat / abqXXXX.bat")
        self.launcher.editingFinished.connect(self.replan)
        form.addWidget(self.launcher, 1, 1)
        self.launcher_button = QPushButton("Browse...")
        self.launcher_button.setObjectName("browseLauncher")
        self.launcher_button.clicked.connect(lambda: self.choose_launcher())
        form.addWidget(self.launcher_button, 1, 2)
        form.addWidget(_label("Results folder"), 2, 0)
        self.folder = QLineEdit()
        self.folder.setObjectName("resultsFolder")
        self.folder.setPlaceholderText("where the extracted package is written (a new sub-folder each time)")
        self.folder.editingFinished.connect(self.replan)
        form.addWidget(self.folder, 2, 1)
        self.folder_button = QPushButton("Choose folder...")
        self.folder_button.setObjectName("chooseResultsFolder")
        self.folder_button.clicked.connect(lambda: self.choose_folder())
        form.addWidget(self.folder_button, 2, 2)
        form.addWidget(_label("Modes"), 3, 0)
        modes = QHBoxLayout()
        self.start_mode = QSpinBox()
        self.start_mode.setObjectName("startMode")
        self.start_mode.setRange(1, 100000)
        self.start_mode.setValue(svc.DEFAULT_START_MODE)
        self.end_mode = QSpinBox()
        self.end_mode.setObjectName("endMode")
        self.end_mode.setRange(1, 100000)
        self.end_mode.setValue(svc.DEFAULT_END_MODE)
        modes.addWidget(_label("from"))
        modes.addWidget(self.start_mode)
        modes.addWidget(_label("to"))
        modes.addWidget(self.end_mode)
        modes.addStretch(1)
        form.addLayout(modes, 3, 1, 1, 2)
        for spin in (self.start_mode, self.end_mode):
            spin.valueChanged.connect(lambda _v: self.replan())
        form.setColumnStretch(1, 1)
        layout.addLayout(form)
        layout.addWidget(_label(om.RANGE_NOTE, "hint"))
        self.availability = _label("", "warnings")
        layout.addWidget(self.availability)
        self.fixes = _label("", "hint")
        layout.addWidget(self.fixes)
        self.facts = QFormLayout()
        self.facts_widget = QWidget()
        self.facts_widget.setLayout(self.facts)
        layout.addWidget(self.facts_widget)
        self.message = _label("", "error")
        layout.addWidget(self.message)
        self.log = QPlainTextEdit()
        self.log.setObjectName("extractionLog")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setPlaceholderText("The extractor's progress lines appear here.")
        layout.addWidget(self.log, 1)
        self.result = QFormLayout()
        self.result_widget = QWidget()
        self.result_widget.setLayout(self.result)
        layout.addWidget(self.result_widget)
        buttons = QHBoxLayout()
        self.extract_button = QPushButton(om.EXTRACT)
        self.extract_button.setObjectName("extractButton")
        self.extract_button.clicked.connect(self.extract)
        self.cancel_button = QPushButton("Cancel extraction")
        self.cancel_button.setObjectName("cancelExtraction")
        self.cancel_button.clicked.connect(self.cancel_extraction)
        self.use_button = QPushButton("Use this package")
        self.use_button.setObjectName("usePackage")
        self.use_button.clicked.connect(self.accept)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        for button in (self.extract_button, self.cancel_button, self.use_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        if results_folder is not None:
            self.folder.setText(str(results_folder))
        self.resize(760, 640)
        self.replan()

    # -------------------------------------------------------------------------------- dialogs (replaced in tests)

    def _dialog_folder(self, start: str) -> str:
        return QFileDialog.getExistingDirectory(self, "Choose the results folder for the extracted package", start)

    def _dialog_launcher(self, start: str) -> str:
        path, _f = QFileDialog.getOpenFileName(self, "Choose the Abaqus launcher", start,
                                               "Abaqus launcher (abaqus*.bat abq*.bat *.cmd *.exe);;All files (*)")
        return path

    def _dialog_confirm(self) -> bool:
        answer = QMessageBox.question(self, om.TITLE, om.CONFIRM_TEXT,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------------------------------ choices and the plan

    def choose_folder(self, folder: Optional[str] = None) -> bool:
        folder = folder if folder is not None else self._ask_folder(self.folder.text() or str(self.odb_path.parent))
        if not folder or not str(folder).strip():
            return False
        self.folder.setText(str(folder))
        self.replan()
        return True

    def choose_launcher(self, path: Optional[str] = None) -> bool:
        path = path if path is not None else self._ask_launcher(self.launcher.text() or "C:/SIMULIA/Commands")
        if not path or not str(path).strip():
            return False
        self.launcher.setText(str(path))
        self.replan()
        return True

    def replan(self) -> None:
        """Look again (nothing starts): the plan or the reason it cannot be made."""
        if self.slot.state == om.RUNNING:
            return
        self.plan, self.plan_error = None, ""
        try:
            self.plan = svc.plan_extraction(self.odb_path, self.folder.text().strip(), self.start_mode.value(),
                                            self.end_mode.value(), self.launcher.text().strip(),
                                            discover=self._discover)
        except svc.OdbImportRefused as error:
            self.plan_error = str(error)
        except OSError as error:
            self.plan_error = f"The folder cannot be checked ({type(error).__name__}: {error})."
        self._show_plan()

    def _show_plan(self) -> None:
        _clear_form(self.facts)
        plan = self.plan
        if plan is not None:
            if plan.abaqus.available:
                if not self.launcher.text().strip():
                    self.launcher.setPlaceholderText(plan.abaqus.command)
                self.availability.setText(f"Abaqus found: {plan.abaqus.label or plan.abaqus.command}"
                                          + (f" — {plan.abaqus.explanation}" if plan.abaqus.explanation else ""))
                self.availability.setObjectName("hint")
            else:
                self.availability.setText(plan.abaqus.explanation)
                self.availability.setObjectName("warnings")
            self.fixes.setText("" if plan.abaqus.available else "\n".join(f"• {fix}" for fix in plan.abaqus.fixes))
            for caption, value in plan.summary():
                self.facts.addRow(caption, _label(value))
            blockers = list(plan.blockers) + list(plan.warnings)
            self.message.setText("\n".join(b for b in blockers if b not in (plan.abaqus.explanation,)))
        else:
            self.availability.setText("")
            self.fixes.setText("")
            self.message.setText(self.plan_error)
        self.availability.style().unpolish(self.availability)
        self.availability.style().polish(self.availability)
        self._buttons()

    def _buttons(self) -> None:
        running = self.slot.state == om.RUNNING
        self.extract_button.setEnabled(self.plan is not None and self.plan.ready and not running)
        self.cancel_button.setEnabled(running)
        self.use_button.setEnabled(self.slot.manifest_path is not None)
        for widget in (self.launcher, self.launcher_button, self.folder, self.folder_button, self.start_mode,
                       self.end_mode):
            widget.setEnabled(not running)
        self.close_button.setEnabled(not running)

    # ------------------------------------------------------------------------------------------ the run

    def extract(self) -> bool:
        """The user's command: confirm, then run in a worker thread. Returns whether a run started."""
        self.replan()
        if self.plan is None or not self.plan.ready or self.slot.state == om.RUNNING:
            return False
        if not self._confirm():
            self.message.setText("Not started: the extraction was not confirmed.")
            return False
        token, cancel_event = self.slot.start(self.plan)
        self.log.clear()
        self.message.setText("")
        _clear_form(self.result)
        self.manifest_path = None
        plan, runner, bridge = self.plan, self._runner, self._bridge

        def work() -> None:
            outcome = om.run_import(plan, token, cancel_event, lambda text: bridge.progress.emit(token, text), runner)
            try:
                bridge.done.emit(outcome)
            except RuntimeError:
                pass

        thread = threading.Thread(target=work, name="new-gui-odb-import", daemon=True)
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()
        self._buttons()
        return True

    def cancel_extraction(self) -> bool:
        if self.slot.cancel():
            self.log.appendPlainText("cancelling: the owned Abaqus process is being stopped...")
            return True
        return False

    def _progress(self, token: int, text: str) -> None:
        if self.slot.note(token, text):
            self.log.appendPlainText(text)

    def _done(self, outcome: om.ImportOutcome) -> None:
        if not self.slot.finish(outcome):
            return
        if outcome.cancelled:
            self.message.setText(outcome.error or "The extraction was cancelled.")
        elif outcome.error:
            self.message.setText(outcome.error)
        else:
            self.manifest_path = Path(outcome.result.manifest_path)
            for caption, value in om.result_lines(outcome.result):
                self.result.addRow(caption, _label(value))
            self.message.setText("")
        self._buttons()

    def busy(self) -> bool:
        return self.slot.state == om.RUNNING or any(t.is_alive() for t in self._threads)

    def reject(self) -> None:
        if self.slot.state == om.RUNNING:
            self.cancel_extraction()
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self.slot.state == om.RUNNING:
            self.cancel_extraction()
            event.ignore()
            return
        super().closeEvent(event)


def _clear_form(form: QFormLayout) -> None:
    while form.rowCount():
        form.removeRow(0)


__all__ = ["OdbImportDialog"]
