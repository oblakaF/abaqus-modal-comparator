"""GUI-UX-R1: the MAC / Points page (PySide6): the comparator's result, what it rests on, and why it may be missing.

The pairs and the MAC table are ``AnalyzePanel``'s, as are the registration commands. The page adds the evidence levels, the
point correspondence, the coverage, the pictures of a chosen pair and the line profiles, from services and the result only.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from new_gui import comparison_model as cm
from new_gui import mac_points_model as mp
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import ImageActions, ImageView, _combo, _label

TAB_POINTS, TAB_PROVENANCE, TAB_PROFILE = "Registered points", "Mapping diagnostics", "Line profile"


class _BoundedTable(DiagnosticTable):
    height_cap = 320

    def __init__(self, headers, rows, stretch, **kwargs):
        super().__init__(headers, rows, stretch, **kwargs)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


def _card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


class _Bridge(QObject):
    done = Signal(object)


class MacPointsPanel(QWidget):
    def __init__(self, analyze):
        super().__init__()
        self.analyze = analyze
        self.pair_token = 0
        self._cancel: Optional[threading.Event] = None
        self._threads: list = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._pair_drawn)
        self.point_table: Optional[DiagnosticTable] = None
        self.coverage_table: Optional[DiagnosticTable] = None
        self.lines: tuple = ()
        self.result = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        card, inner = _card()
        self.badge = QLabel(mp.UNAVAILABLE_BADGE)
        self.badge.setObjectName("badge")
        self.badge.setProperty("state", "blocked")
        inner.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.reason = _label("", "warnings")
        inner.addWidget(self.reason)
        self.evidence_box = QWidget()
        self.evidence_layout = QVBoxLayout(self.evidence_box)
        self.evidence_layout.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(self.evidence_box)
        self.evidence_table: Optional[DiagnosticTable] = None
        layout.addWidget(card)
        card, inner = _card()
        inner.addWidget(_label(mp.MEASURED_TITLE, "sectionTitle"))
        inner.addWidget(_label(mp.MEASURED_NOTE, "hint"))
        self.measured_status = _label("", "hint")
        inner.addWidget(self.measured_status)
        self.measured_box = QHBoxLayout()
        self.measured_box.setSpacing(12)
        picture = QVBoxLayout()
        self.measured_image = ImageView()
        picture.addWidget(self.measured_image)
        self.measured_actions = ImageActions(self.measured_image, "measured_points")
        picture.addWidget(self.measured_actions)
        picture.addStretch(1)
        self.measured_box.addLayout(picture, 1)
        self.measured_table_box = QVBoxLayout()
        self.measured_box.addLayout(self.measured_table_box, 1)
        inner.addLayout(self.measured_box)
        self.measured_table: Optional[DiagnosticTable] = None
        self.measured_card = card
        layout.addWidget(card)
        layout.addWidget(analyze.registration_box)
        layout.addWidget(analyze.comparison_box)
        self.pair_card, inner = _card()
        inner.addWidget(_label("Selected pair on its registered points", "sectionTitle"))
        self.pair_status = _label(mp.PAIR_TEXT, "hint")
        inner.addWidget(self.pair_status)
        images = QGridLayout()
        images.setHorizontalSpacing(8)
        self.pair_images = tuple(ImageView() for _ in cm.PAIR_CAPTIONS)
        self.pair_actions = tuple(ImageActions(image, f"pair_{name}") for image, (name, _caption) in zip(self.pair_images, cm.PAIR_CAPTIONS))
        for column, (image, actions) in enumerate(zip(self.pair_images, self.pair_actions)):
            images.addWidget(image, 0, column)
            images.addWidget(actions, 1, column)
            images.setColumnStretch(column, 1)
        inner.addLayout(images)
        layout.addWidget(self.pair_card)
        layout.addStretch(1)
        analyze.result_shown.connect(self.rebuild)
        analyze.pair_chosen.connect(self.show_pair_images)
        self.rebuild()

    # ---------------------------------------------------------------------------------------------- content

    def rebuild(self) -> None:
        self._stop()
        analysis, panel = self.analyze.analysis, self.analyze
        self.result = analysis.comparison_result if analysis is not None else None
        for image in self.pair_images:
            image.clear_image()
        reason = mp.unavailable_reason(analysis, panel.snapshot is not None)
        self.reason.setText(reason)
        self.reason.setVisible(bool(reason))
        self.badge.setVisible(bool(reason))
        self._rebuild_evidence()
        self._rebuild_measured()
        view = analysis.comparison if analysis is not None else None
        self.pair_card.setVisible(view is not None and bool(view.pair_rows))
        self.pair_status.setText(mp.NEEDS_SOURCE if panel.snapshot is not None else mp.PAIR_TEXT)
        self.point_table = self.coverage_table = None
        if view is not None and panel.comparison_tabs is not None:
            self._add_points_tab(view)
            self._add_provenance_tab(view)
            self._add_profile_tab()

    def refresh_evidence(self) -> None:
        """The manual-choice count follows the Review page; nothing else on this page depends on it."""
        self._rebuild_evidence()

    def _rebuild_evidence(self) -> None:
        while self.evidence_layout.count():
            widget = self.evidence_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.evidence_table = None
        analysis = self.analyze.analysis
        if analysis is None:
            return
        rows = mp.evidence_levels(analysis, self.analyze.review_state, self.analyze.registration_kind())
        self.evidence_table = DiagnosticTable(mp.EVIDENCE_HEADERS, rows, 2, text_columns=(0, 1))
        self.evidence_table.setObjectName("macEvidence")
        self.evidence_layout.addWidget(self.evidence_table)

    def _rebuild_measured(self) -> None:
        """The measurement geometry, whatever the state of the registration."""
        if self.measured_table is not None:
            self.measured_table.setParent(None)
            self.measured_table.deleteLater()
            self.measured_table = None
        self.measured_image.clear_image()
        analysis = self.analyze.analysis
        self.measured_card.setVisible(analysis is not None)
        if analysis is None:
            return
        mode = self.analyze.measured_mode()
        if mode is None:
            self.measured_status.setText(mp.MEASURED_NEEDS_SOURCE if self.analyze.snapshot is not None else mp.NO_DETAIL)
            return
        self.measured_status.setText(mp.measured_summary(mode))
        self.measured_image.set_image(mp.layout_plot(mode))
        self.measured_table = _BoundedTable(mp.MEASURED_HEADERS, mp.measured_rows(mode), 4)
        self.measured_table.setObjectName("macMeasuredPoints")
        self.measured_table_box.addWidget(self.measured_table)

    def _tab(self, title: str) -> QVBoxLayout:
        page = QWidget()
        inner = QVBoxLayout(page)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.setSpacing(8)
        self.analyze.comparison_tabs.addTab(page, title)
        return inner

    def _add_points_tab(self, view) -> None:
        inner = self._tab(TAB_POINTS)
        inner.addWidget(_label(mp.POINT_NOTE, "hint"))
        inner.addWidget(_label("Measured DOFs and coverage per pair", "sectionTitle"))
        self.coverage_table = _BoundedTable(mp.COVERAGE_HEADERS, mp.coverage_rows(view), 4)
        inner.addWidget(self.coverage_table)
        inner.addWidget(_label("FE-to-experimental point correspondence", "sectionTitle"))
        rows = mp.point_rows(self.result) if self.result is not None else ()
        if rows:
            self.point_table = _BoundedTable(mp.POINT_HEADERS, rows, 6)
            self.point_table.setObjectName("macPoints")
            inner.addWidget(self.point_table)
        else:
            inner.addWidget(_label(mp.NEEDS_SOURCE if self.analyze.snapshot is not None else mp.NO_DETAIL, "hint"))
        inner.addStretch(1)

    def _add_provenance_tab(self, view) -> None:
        inner = self._tab(TAB_PROVENANCE)
        rows = tuple((caption, str(value)) for caption, value in view.provenance if caption in mp.MAPPING_FACTS) + tuple(
            (f"Gate: {name}", value) for name, value in view.gates)
        inner.addWidget(_BoundedTable(mp.PROVENANCE_HEADERS, rows, 1, text_columns=(0,)))
        inner.addStretch(1)

    def _add_profile_tab(self) -> None:
        inner = self._tab(TAB_PROFILE)
        self.profile_note = _label(mp.PROFILE_NOTE, "hint")
        inner.addWidget(self.profile_note)
        pairs = self.result.pairs if self.result is not None else ()
        self.pair_combo, self.line_combo, self.axis_combo = _combo("profilePair"), _combo("profileLine"), _combo("profileAxis")
        row = QHBoxLayout()
        for caption, combo in (("Pair", self.pair_combo), ("Line", self.line_combo), ("Component", self.axis_combo)):
            row.addWidget(QLabel(caption))
            row.addWidget(combo, 1)
        inner.addLayout(row)
        self.profile_status = _label("", "hint")
        inner.addWidget(self.profile_status)
        self.profile_image = ImageView()
        inner.addWidget(self.profile_image)
        self.profile_actions = ImageActions(self.profile_image, "line_profile")
        inner.addWidget(self.profile_actions)
        inner.addStretch(1)
        for index, pair in enumerate(pairs):
            self.pair_combo.addItem(f"FE {pair.abaqus_mode} / EXP {pair.experimental_mode}", index)
        for axis, name in enumerate(mp.AXES):
            self.axis_combo.addItem(name, axis)
        self.pair_combo.currentIndexChanged.connect(self._pair_changed)
        self.line_combo.currentIndexChanged.connect(self.draw_profile)
        self.axis_combo.currentIndexChanged.connect(self.draw_profile)
        self.axis_combo.setCurrentIndex(2)
        self._pair_changed()

    def _pair_changed(self) -> None:
        index = self.pair_combo.currentData()
        pair = self.result.pairs[index] if self.result is not None and index is not None else None
        self.lines = mp.profile_lines(pair) if pair is not None else ()
        self.line_combo.blockSignals(True)
        self.line_combo.clear()
        for number, line in enumerate(self.lines):
            self.line_combo.addItem(line.label, number)
        self.line_combo.blockSignals(False)
        self.draw_profile()

    def draw_profile(self, _index=0) -> bool:
        number = self.line_combo.currentData()
        if number is None:
            self.profile_image.clear_image()
            self.profile_status.setText(mp.NEEDS_SOURCE if self.analyze.snapshot is not None else mp.NO_LINE)
            return False
        image = mp.profile_plot(self.result.pairs[self.pair_combo.currentData()], self.lines[number],
                                self.axis_combo.currentData())
        if image is None:
            self.profile_image.clear_image()
            self.profile_status.setText(mp.NOT_MEASURED)
            return False
        self.profile_status.setText("")
        return self.profile_image.set_image(image)

    # ---------------------------------------------------------------------------------------------- the pair's pictures

    def show_pair_images(self, row: int) -> bool:
        """The services' pictures of one pair, on the registered points; a saved result holds none."""
        self._stop()
        for image in self.pair_images:
            image.clear_image()
        view = self.analyze.analysis.comparison if self.analyze.analysis is not None else None
        if self.result is None or view is None or not 0 <= row < len(view.pair_rows):
            return False
        index = view.pair_rows[row].index
        self.pair_token += 1
        token, cancel, result, bridge = self.pair_token, threading.Event(), self.result, self._bridge
        self._cancel = cancel

        def work() -> None:
            outcome = cm.run_pair_images(result, index, token, cancel)
            try:
                bridge.done.emit(outcome)
            except RuntimeError:
                pass

        worker = threading.Thread(target=work, name="new-gui-pair-images", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        return True

    def _pair_drawn(self, outcome: cm.PairImages) -> None:
        if outcome.token != self.pair_token or outcome.cancelled:
            return
        if outcome.error:
            self.pair_status.setText(outcome.error)
            return
        for image, (caption, data) in zip(self.pair_images, outcome.images):
            image.set_image(data)
            image.setToolTip(caption)

    def _stop(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self._cancel = None
        self.pair_token += 1

    def busy(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    def shutdown(self) -> None:
        self._stop()


__all__ = ["MacPointsPanel"]
