"""GUI-UX-R1: the Materials page (PySide6): its own two files, read-only facts and the truthful scientific status.

The files chosen here belong to this page: they change nothing on Analyze, Review or MAC / Points. Reading runs in worker
threads and starts no process. No material value exists here.

MAT-3: the page also holds the diagnostic study (``materials_study_panel``), which runs SYNTHETIC software tests and takes
no value from the files chosen here.

MAT-4.UX1: the page has five tabs. The first four are the study's own pages, and the fifth holds these files and facts.
Changing tabs reads no file and starts no calculation.
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QStackedWidget, QTabBar, QVBoxLayout, QWidget

from new_gui import analyze_model as am
from new_gui import materials_workspace_model as mw
from new_gui.materials_study_panel import MaterialsStudyPanel, Section, TAB_TITLES, scrolled
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import _label
from new_gui.workspace_state import EXPERIMENTAL, FE

CAPTIONS = {FE: "Результаты FE: ODB", EXPERIMENTAL: "Эксперимент: UNV/UFF"}
FACT_TITLES = {FE: "Геометрия FE-модели", EXPERIMENTAL: "Экспериментальные данные"}
USE_ANALYZE = "Взять два файла из Analyze"
READING = "Чтение..."
NO_FILES_TEXT = "В Analyze пока нет файлов."
NO_REGISTRATION = "Нет: физическая регистрация на этой странице не подтверждена"
USED_BY_ANALYZE = "Используется сравнением в Analyze; это не объявление для подбора"
TAB_FILES = 4
ALL_TAB_TITLES = TAB_TITLES + ("FE / Эксперимент",)


def _card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


class _Bridge(QObject):
    done = Signal(str, int, object)


class MaterialsWorkspace(QWidget):
    """``status`` is the fixed state panel; ``ask_path(kind, start)`` is replaced in tests."""

    experimental_kind = EXPERIMENTAL

    def __init__(self, analyze, status: QWidget, ask_path: Optional[Callable[[str, str], str]] = None):
        super().__init__()
        self.analyze = analyze
        self._ask_path = ask_path or self._dialog_path
        self.paths: dict = {FE: None, EXPERIMENTAL: None}
        self.facts: dict = {FE: None, EXPERIMENTAL: None}
        self.reading: dict = {FE: False, EXPERIMENTAL: False}
        self._tokens: dict = {FE: 0, EXPERIMENTAL: 0}
        self._cancels: dict = {FE: None, EXPERIMENTAL: None}
        self._threads: list = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._read_done)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.study = MaterialsStudyPanel(self)
        self.tabs = QTabBar()
        self.tabs.setObjectName("materialsTabs")
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setUsesScrollButtons(True)
        for title in ALL_TAB_TITLES:
            self.tabs.addTab(title)
        layout.addWidget(self.tabs)
        self.pages = QStackedWidget()
        self.pages.setMinimumHeight(420)  # only a very short window scrolls the whole page
        self.pages.addWidget(self.study)
        files = QWidget()
        outer = layout
        layout = QVBoxLayout(files)
        layout.setContentsMargins(0, 10, 8, 10)
        layout.setSpacing(10)
        self.pages.addWidget(scrolled(files))
        outer.addWidget(self.pages, 1)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.study.tab_wanted.connect(self.select_tab)
        layout.addWidget(self._build_inputs())
        layout.addWidget(self.study.real_card)
        self.fact_boxes: dict = {}
        self.fact_tables: dict = {}
        self.fact_notes: dict = {}
        facts = QHBoxLayout()
        facts.setSpacing(10)
        for kind in (FE, EXPERIMENTAL):
            card, inner = _card()
            inner.addWidget(_label(FACT_TITLES[kind], "sectionTitle"))
            self.fact_notes[kind] = _label("Пока не прочитано.", "hint")
            inner.addWidget(self.fact_notes[kind])
            box = QVBoxLayout()
            inner.addLayout(box)
            inner.addStretch(1)
            self.fact_boxes[kind] = box
            facts.addWidget(card, 1)
        layout.addLayout(facts)
        card, inner = _card()
        inner.addWidget(_label("Входные свойства материала", "sectionTitle"))
        self.material_statement = _label(mw.MATERIAL_STATEMENT, "warnings")
        inner.addWidget(self.material_statement)
        self.property_table = DiagnosticTable(mw.PROPERTY_HEADERS, mw.property_rows(), 0, text_columns=(1, 2, 3))
        self.property_table.setObjectName("materialProperties")
        inner.addWidget(self.property_table)
        layout.addWidget(card)
        layout.addWidget(status)
        card, inner = _card()
        self.status_text = _label(mw.STATUS_TEXT, "")
        inner.addWidget(self.status_text)
        self.workflow = Section(mw.WORKFLOW_TITLE, name="materialsWorkflow")
        self.workflow.inner.addWidget(_label("\n".join(mw.WORKFLOW), "hint"))
        inner.addWidget(self.workflow)
        layout.addWidget(card)
        layout.addStretch(1)
        self.select_tab(0)

    def select_tab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        self._tab_changed(index)

    def _tab_changed(self, index: int) -> None:
        """Only shows a page. A real file is read only when it is chosen, and a calculation starts only from its button."""
        if index == TAB_FILES:
            self.pages.setCurrentIndex(1)
        else:
            self.pages.setCurrentIndex(0)
            self.study.setCurrentIndex(index)

    def _build_inputs(self) -> QFrame:
        card, inner = _card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        self.fields, self.choose_buttons = {}, {}
        for row, kind in enumerate((FE, EXPERIMENTAL)):
            grid.addWidget(_label(CAPTIONS[kind]), 2 * row, 0, 1, 2)
            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText("не выбран")
            field.setMinimumWidth(80)
            grid.addWidget(field, 2 * row + 1, 0)
            button = QPushButton("Выбрать файл...")
            button.setObjectName(f"materialsChoose_{kind}")
            button.clicked.connect(lambda _checked=False, k=kind: self.choose_file(k))
            grid.addWidget(button, 2 * row + 1, 1)
            self.fields[kind], self.choose_buttons[kind] = field, button
        inner.addLayout(grid)
        row = QHBoxLayout()
        self.reuse_button = QPushButton(USE_ANALYZE)
        self.reuse_button.setObjectName("materialsUseAnalyze")
        self.reuse_button.clicked.connect(lambda: self.use_analyze_files())
        row.addWidget(self.reuse_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.message = _label("", "error")
        self.message.setVisible(False)
        inner.addWidget(self.message)
        return card

    def registration_text(self) -> str:
        analysis = self.analyze.analysis
        return USED_BY_ANALYZE if analysis is not None and analysis.comparison is not None else NO_REGISTRATION

    def _dialog_path(self, kind: str, start: str) -> str:
        path, _filter = QFileDialog.getOpenFileName(self, CAPTIONS[kind], start, am.FILTERS[kind])
        return path

    # ---------------------------------------------------------------------------------------------- the files

    def choose_file(self, kind: str, path: Optional[str] = None) -> bool:
        if path is None:
            current = self.paths[kind]
            path = self._ask_path(kind, str(current.parent) if current else "")
        if not path:
            return False
        problem = am.file_problem(kind, path)
        self._say(problem)
        if problem:
            return False
        self._set_path(kind, Path(path).resolve())
        self._read(kind)
        return True

    def use_analyze_files(self) -> bool:
        """Reuse what Analyze holds: its data in memory, or a saved result's own file; only otherwise read the files."""
        panel = self.analyze
        self._say("")
        if panel.snapshot is not None:
            saved = mw.saved_facts(panel.snapshot.document)
            for kind, facts in zip((FE, EXPERIMENTAL), saved):
                self._set_path(kind, panel.paths[kind])
                self._stop(kind)
                self._show(kind, facts)
            return True
        if not any(panel.paths.values()):
            self._say(NO_FILES_TEXT)
            return False
        for kind in (FE, EXPERIMENTAL):
            if panel.paths[kind] is not None:
                self._set_path(kind, panel.paths[kind])
                if kind == EXPERIMENTAL and panel.inputs is not None:
                    self._stop(kind)
                    self._show(kind, mw.experimental_facts(panel.inputs.full_experimental))
                elif kind == FE and panel.inputs is not None:
                    odb, manifest = panel.paths[kind], panel.inputs.full_fe.manifest_path
                    self._read(kind, lambda cancel, _say: mw.Facts(mw.source_rows(odb, True) + mw.geometry_facts(manifest, cancel)))
                else:
                    self._read(kind)
        return True

    def _set_path(self, kind: str, path) -> None:
        self.paths[kind] = path
        self.fields[kind].setText(str(path) if path else "")
        self.fields[kind].setToolTip(str(path) if path else "")

    def _say(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    # ---------------------------------------------------------------------------------------------- reading

    def _stop(self, kind: str) -> None:
        if self._cancels[kind] is not None:
            self._cancels[kind].set()
        self._cancels[kind] = None
        self._tokens[kind] += 1
        self.reading[kind] = False

    def _read(self, kind: str, work: Optional[Callable] = None) -> None:
        self._stop(kind)
        cancel = threading.Event()
        self._cancels[kind] = cancel
        token = self._tokens[kind]
        path, bridge = self.paths[kind], self._bridge
        if work is None:
            work = ((lambda c, s: mw.read_fe_facts(path, c, s)) if kind == FE
                    else (lambda c, _s: mw.read_experimental_facts(path, c)))
        self.reading[kind] = True
        self.fact_notes[kind].setText(READING)
        self._clear_table(kind)

        def target() -> None:
            try:
                value = work(cancel, None)
            except (am.StepFailed, am.StepCancelled) as error:
                value = error
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                value = am.StepFailed(f"Файл не прочитан ({type(error).__name__}: {error}).")
            try:
                bridge.done.emit(kind, token, value)
            except RuntimeError:
                pass

        worker = threading.Thread(target=target, name=f"new-gui-materials-{kind}", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()

    def _read_done(self, kind: str, token: int, value) -> None:
        if token != self._tokens[kind]:
            return
        self.reading[kind] = False
        self._cancels[kind] = None
        if isinstance(value, am.StepCancelled):
            self.fact_notes[kind].setText("Отменено.")
        elif isinstance(value, am.StepFailed):
            self.facts[kind] = None
            self.fact_notes[kind].setText("Не прочитано.")
            self._say(str(value))
            self.study.refresh_real()
        else:
            self._show(kind, value)

    def _clear_table(self, kind: str) -> None:
        table = self.fact_tables.pop(kind, None)
        if table is not None:
            table.setParent(None)
            table.deleteLater()

    def _show(self, kind: str, facts: mw.Facts) -> None:
        self.facts[kind] = facts
        self._clear_table(kind)
        table = DiagnosticTable(("Сведение", "Значение"), facts.rows, 1, text_columns=(0,))
        table.setObjectName(f"materialsFacts_{kind}")
        self.fact_tables[kind] = table
        self.fact_boxes[kind].addWidget(table)
        self.fact_notes[kind].setText(facts.note)
        self.fact_notes[kind].setVisible(bool(facts.note))
        self.study.refresh_real()

    def busy(self) -> bool:
        return self.study.busy() or any(thread.is_alive() for thread in self._threads)

    def shutdown(self) -> None:
        self.study.shutdown()
        for kind in (FE, EXPERIMENTAL):
            self._stop(kind)


__all__ = ["MaterialsWorkspace"]
