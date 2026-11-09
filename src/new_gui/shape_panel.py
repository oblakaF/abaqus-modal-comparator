"""NEW-GUI.3: the panel that shows one mode shape of an inspected file (PySide6).

FE: a loaded mode and a component (Normal, Magnitude, U1, U2, U3). Experimental: a modal set first, then a record
of that set, and a component (Normal, Magnitude, X, Y, Z). Nothing is chosen in advance, and a shape is drawn only
when the user clicks Show shape. Changing the set, the mode or record, or the component removes the shown shape
until Show shape is clicked again.

The drawing runs in a worker thread (``new_gui.shape_model.run_render``). The PNG bytes come back to the window's
thread, where the pixmap is made. The image is scaled to the panel's width, keeping its proportions, so a large PNG
never widens the window.
"""

from __future__ import annotations

import threading
from typing import Optional

from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from new_gui import shape_model as sm
from new_gui.workspace_state import EXPERIMENTAL, FE, KIND_TITLE

COPY_IMAGE, SAVE_PNG = "Copy Image", "Save PNG"
MAX_IMAGE_HEIGHT = 560  # logical pixels; a tall image is scaled down, never cut
SCROLLBAR_ALLOWANCE = 24  # shrinking by this little keeps the height: see ImageView._fit


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # long text never widens
    label.setMinimumWidth(0)
    return label


class ScrollSafeCombo(QComboBox):
    """The wheel never changes a closed choice: it goes on to the page or table beneath (an open list scrolls itself)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:
        event.ignore()


def _combo(name: str) -> QComboBox:
    combo = ScrollSafeCombo()
    combo.setObjectName(name)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(14)  # a long mode name never widens the window
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return combo


class ImageView(QLabel):
    """A PNG scaled to the available width with its proportions kept (never wider than the panel)."""

    image_changed = Signal(bool)
    clicked = Signal(float, float)  # a left click on the picture, in the original PNG's pixels

    def __init__(self):
        super().__init__()
        self.data = b""  # the original PNG, as drawn or saved: what Copy Image and Save PNG use
        self.setObjectName("shapeImage")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(1, 1)
        self.source: Optional[QPixmap] = None
        self._fitting = False
        self._fitted_width: Optional[int] = None
        self.setFixedHeight(0)

    def set_image(self, data: bytes) -> bool:
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data, "PNG"):
            self.clear_image()
            return False
        self.source = pixmap
        self.data = bytes(data)
        self._fitted_width = None
        self._fit()
        self.image_changed.emit(True)
        return True

    def clear_image(self) -> None:
        self.source = None
        self.data = b""
        self._fitted_width = None
        self.clear()
        self.setFixedHeight(0)
        self.image_changed.emit(False)

    def _fit(self) -> None:
        if self.source is None or self.source.isNull():
            return
        width = max(1, self.width())
        # In a scroll area the height decides the scroll bar, and the scroll bar decides the width. If the height followed
        # every width, the bar would appear and vanish without end, inside one resize, until the stack overflows.
        if self._fitted_width is None or width > self._fitted_width or self._fitted_width - width > SCROLLBAR_ALLOWANCE:
            self._fitted_width = width
            height = max(1, min(MAX_IMAGE_HEIGHT, round(width * self.source.height() / self.source.width())))
        else:
            height = max(1, self.height())
        ratio = self.devicePixelRatioF()
        scaled = self.source.scaled(round(width * ratio), round(height * ratio), Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(ratio)
        self.setPixmap(scaled)
        if self.height() != height:
            self._fitting = True  # setFixedHeight resizes at once; the height follows the width, so no second fit is needed
            try:
                self.setFixedHeight(height)
            finally:
                self._fitting = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._fitting:
            self._fit()

    def image_point(self, x: float, y: float) -> Optional[tuple]:
        """Where (x, y) of this widget falls on the original PNG, in its pixels; None outside the picture."""
        pixmap = self.pixmap()
        if self.source is None or pixmap is None or pixmap.isNull():
            return None
        ratio = pixmap.devicePixelRatio() or 1.0
        width, height = pixmap.width() / ratio, pixmap.height() / ratio
        left, top = (self.width() - width) / 2.0, (self.height() - height) / 2.0
        fx, fy = (x - left) / width, (y - top) / height
        if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
            return None
        return fx * self.source.width(), fy * self.source.height()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            point = self.image_point(event.position().x(), event.position().y())
            if point is not None:
                self.clicked.emit(*point)


class ImageActions(QWidget):
    """Copy Image and Save PNG of one picture: its original bytes, never a capture of the screen. Off without a picture."""

    def __init__(self, view: ImageView, name: str = "picture"):
        super().__init__()
        self.view = view
        self.name = name
        self.ask_path = self._dialog_path
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.copy_button = QPushButton(COPY_IMAGE)
        self.copy_button.setObjectName("imageCopy")
        self.copy_button.clicked.connect(lambda: self.copy())
        self.save_button = QPushButton(SAVE_PNG)
        self.save_button.setObjectName("imageSave")
        self.save_button.clicked.connect(lambda: self.save())
        row.addWidget(self.copy_button)
        row.addWidget(self.save_button)
        row.addStretch(1)
        view.image_changed.connect(self._changed)
        self._changed(bool(view.data))

    def _changed(self, available: bool) -> None:
        self.copy_button.setEnabled(available)
        self.save_button.setEnabled(available)

    def copy(self) -> bool:
        image = QImage.fromData(self.view.data, "PNG") if self.view.data else QImage()
        if image.isNull():
            return False
        QGuiApplication.clipboard().setImage(image)
        return True

    def _dialog_path(self) -> str:
        path, _filter = QFileDialog.getSaveFileName(self, SAVE_PNG, f"{self.name}.png", "PNG image (*.png)")
        return path

    def save(self) -> bool:
        if not self.view.data:
            return False
        path = self.ask_path()
        if not path:
            return False
        target = Path(path)
        target = target if target.suffix else target.with_name(target.name + ".png")
        try:
            target.write_bytes(self.view.data)
        except OSError as error:
            self.save_button.setToolTip(f"Not saved: {error}")
            return False
        return True


class _Bridge(QObject):
    """Carries a drawing's outcome from its worker thread to the window's thread (a queued signal)."""

    done = Signal(object)


class ShapePanel(QFrame):
    """One side's shape view; hidden until that side's file was inspected."""

    def __init__(self, kind: str, compact: bool = False):
        super().__init__()
        self.kind = kind
        self.compact = compact  # the page states the note itself; the long texts wait behind Show details
        self.setObjectName("card")
        self.preview = None
        self.slot = sm.ShapeSlot()
        self.discarded = 0
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        title = _label(f"{KIND_TITLE[kind]}: {'mode' if kind == FE else 'record'} shape", "cardTitle")
        layout.addWidget(title)
        self.hint = _label(sm.NOTHING_CHOSEN[kind], "hint")
        layout.addWidget(self.hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(1, 1)
        row = 0
        self.set_combo: Optional[QComboBox] = None
        if kind == EXPERIMENTAL:
            self.set_combo = _combo("setChoice")
            self.set_combo.currentIndexChanged.connect(self._set_changed)
            grid.addWidget(QLabel("Modal set"), row, 0)
            grid.addWidget(self.set_combo, row, 1)
            row += 1
        self.item_combo = _combo("modeChoice" if kind == FE else "recordChoice")
        self.item_combo.currentIndexChanged.connect(self._choice_changed)
        grid.addWidget(QLabel("Mode" if kind == FE else "Record"), row, 0)
        grid.addWidget(self.item_combo, row, 1)
        row += 1
        self.component_combo = _combo("componentChoice")
        for component in sm.COMPONENTS:
            self.component_combo.addItem(sm.COMPONENT_LABEL[kind][component], component)
        self.component_combo.currentIndexChanged.connect(self._choice_changed)
        grid.addWidget(QLabel("Component"), row, 0)
        grid.addWidget(self.component_combo, row, 1)
        layout.addLayout(grid)
        self.component_note = _label("", "hint")  # ABM-UX5: which components are measured, and what Magnitude hides
        self.component_note.setVisible(False)
        layout.addWidget(self.component_note)
        self.facts = _label("", "hint")
        layout.addWidget(self.facts)
        self.record_warnings = _label("", "warnings")
        layout.addWidget(self.record_warnings)
        buttons = QHBoxLayout()
        self.show_button = QPushButton(sm.SHOW)
        self.show_button.setObjectName("primary")
        self.show_button.clicked.connect(self.show_shape)
        buttons.addWidget(self.show_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.provisional = _label(sm.PROVISIONAL_TEXT, "error")  # beside the image of an FRF peak record
        layout.addWidget(self.provisional)
        self.status = _label("", "")
        layout.addWidget(self.status)
        self.image = ImageView()
        layout.addWidget(self.image)
        self.image_actions = ImageActions(self.image, f"{'fe' if kind == FE else 'experimental'}_shape")
        layout.addWidget(self.image_actions)
        self.caption = _label("", "")
        layout.addWidget(self.caption)
        self.note = _label(sm.SHAPE_NOTE, "hint")
        layout.addWidget(self.note)
        self.projection = _label(sm.view_text(sm.DEFAULT_VIEW[0]), "hint")
        self.projection.setVisible(compact)
        layout.addWidget(self.projection)
        self.view_combo = self.rotation_combo = self.mirror_combo = None
        if compact:
            self._build_view_row(layout, grid)
        self.details_toggle: Optional[QPushButton] = None
        if compact:
            self.show_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # disabled during each redraw: a focused one would scroll the pane
            self.provisional.setText(sm.FRF_PEAK_SHORT)  # the page explains it once; the full wording is in the details
            self.provisional.setToolTip(sm.PROVISIONAL_TEXT)
            for combo in (self.set_combo, self.item_combo, self.component_combo):
                if combo is not None:
                    combo.activated.connect(lambda _row=0: self.show_shape())
            self.details_toggle = QPushButton("Show details")
            self.details_toggle.setObjectName("detailsToggle")
            self.details_toggle.setCheckable(True)
            self.details_toggle.toggled.connect(self._details_toggled)
            layout.insertWidget(layout.indexOf(self.facts), self.details_toggle, 0, Qt.AlignmentFlag.AlignLeft)
            for combo in (self.set_combo, self.item_combo, self.component_combo):
                if combo is not None:
                    combo.setMinimumContentsLength(6)
        self.setVisible(False)
        self._refresh()

    def _build_view_row(self, layout, grid) -> None:
        self.view_combo = _combo("shapeView")
        for plane, text in sm.VIEWS:
            self.view_combo.addItem(text, plane)
        self.rotation_combo = _combo("shapeRotation")
        for degrees in sm.ROTATIONS:
            self.rotation_combo.addItem(f"{degrees}°", degrees)
        self.mirror_combo = _combo("shapeMirror")
        self.mirror_combo.addItem("No", False)
        self.mirror_combo.addItem("Left-right", True)
        row = QHBoxLayout()
        for caption, combo in (("View", self.view_combo), ("Rotate", self.rotation_combo), ("Mirror", self.mirror_combo)):
            row.addWidget(QLabel(caption))
            row.addWidget(combo, 1)
            combo.setMinimumContentsLength(3)
            combo.currentIndexChanged.connect(self._choice_changed)
            combo.activated.connect(lambda _row=0: self.show_shape())
        layout.insertLayout(layout.indexOf(self.hint) + 1, row)

    def display(self):
        """(plane, rotation, mirror) chosen for this picture; None where the panel offers no view choice."""
        if self.view_combo is None:
            return None
        return (self.view_combo.currentData(), self.rotation_combo.currentData(), self.mirror_combo.currentData())

    def _details_toggled(self, shown: bool) -> None:
        self.details_toggle.setText("Hide details" if shown else "Show details")
        self._refresh()

    # ------------------------------------------------------------------------------------------ choices

    def set_preview(self, preview) -> None:
        """Show the choices of a newly read preview (or hide the panel); the same preview keeps its state."""
        if preview is self.preview:
            return
        self.slot.reset()
        self.preview = preview
        combos = [c for c in (self.set_combo, self.item_combo) if c is not None]
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
        if preview is not None:
            if self.kind == FE:
                self.item_combo.addItem(sm.CHOOSE_MODE, None)
                for index, text in sm.fe_mode_options(preview):
                    self.item_combo.addItem(text, index)
            else:
                self.set_combo.addItem(sm.CHOOSE_SET, None)
                for index, text in sm.set_options(preview):
                    self.set_combo.addItem(text, index)
                self.item_combo.addItem(sm.CHOOSE_RECORD, None)
        for combo in combos:
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.setVisible(preview is not None)
        self._refresh()

    def chosen_set(self):
        if self.kind == FE or self.preview is None:
            return None
        index = self.set_combo.currentData()
        return None if index is None else self.preview.sets[index]

    def chosen_index(self) -> Optional[int]:
        return self.item_combo.currentData()

    def chosen_component(self) -> str:
        return self.component_combo.currentData()

    def _set_changed(self) -> None:
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        self.item_combo.addItem(sm.CHOOSE_RECORD, None)
        preview_set = self.chosen_set()
        if preview_set is not None:
            for index, text in sm.record_options(preview_set):
                self.item_combo.addItem(text, index)
        self.item_combo.setCurrentIndex(0)
        self.item_combo.blockSignals(False)
        self._choice_changed()

    def _choice_changed(self) -> None:
        self.slot.reset()  # a changed choice never keeps the previous shape
        self._refresh()

    def ready(self) -> bool:
        if self.preview is None or self.chosen_index() is None:
            return False
        return self.kind == FE or self.chosen_set() is not None

    # ------------------------------------------------------------------------------------------ drawing

    def show_shape(self) -> bool:
        """Draw the chosen mode or record in a worker thread; returns False when the choice is incomplete."""
        if not self.ready() or self.slot.state == sm.DRAWING:
            return False
        source = self.preview if self.kind == FE else self.chosen_set()
        index, component = self.chosen_index(), self.chosen_component()
        set_index = None if self.kind == FE else self.set_combo.currentData()
        display = self.display()
        token, cancel_event = self.slot.start((set_index, index, component))
        worker = threading.Thread(target=self._draw, args=(source, index, component, token, cancel_event, display),
                                  name=f"new-gui-shape-{self.kind}", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        self._refresh()
        return True

    def _draw(self, source, index, component, token, cancel_event, display=None) -> None:
        outcome = sm.run_render(self.kind, source, index, component, token, cancel_event, display)  # no widget here
        try:
            self._bridge.done.emit(outcome)
        except RuntimeError:  # the panel is already gone
            pass

    def _done(self, outcome: sm.ShapeOutcome) -> None:
        if not self.slot.finish(outcome):
            self.discarded += 1  # a cancelled or stale request: the current state is kept
            return
        self._refresh()

    def busy(self) -> bool:
        return self.slot.state == sm.DRAWING or any(thread.is_alive() for thread in self._threads)

    def cancel(self) -> None:
        self.slot.reset()
        self._refresh()

    # ------------------------------------------------------------------------------------------ display

    def _refresh(self) -> None:
        has_preview = self.preview is not None
        if self.set_combo is not None:
            self.set_combo.setEnabled(has_preview)
            self.item_combo.setEnabled(self.chosen_set() is not None)
        else:
            self.item_combo.setEnabled(has_preview)
        self.component_combo.setEnabled(has_preview)
        state = self.slot.state
        self.show_button.setEnabled(self.ready() and state != sm.DRAWING)
        index = self.chosen_index() if self.ready() else None
        if index is None:
            facts, warnings, provisional = (), (), False
        elif self.kind == FE:
            facts, warnings, provisional = sm.fe_mode_facts(self.preview, index), (), False
        else:
            preview_set = self.chosen_set()
            facts = sm.record_facts(preview_set, index)
            warnings = sm.record_warnings(preview_set, index)
            provisional = sm.is_provisional(preview_set, index)
            allowed = sm.record_components(preview_set, index)
            for row, component in enumerate(sm.COMPONENTS):
                item = self.component_combo.model().item(row)
                item.setEnabled(component in allowed)  # a component that was not measured cannot be chosen: no false data
                item.setText(sm.component_text(self.kind, component, allowed))
        if self.kind == FE:
            self.component_note.setText(sm.FE_COMPONENT_NOTE if has_preview else "")
        elif index is None:
            for row, component in enumerate(sm.COMPONENTS):
                self.component_combo.model().item(row).setText(sm.component_text(self.kind, component))
            self.component_note.setText("")
        else:
            self.component_note.setText(sm.measured_note(allowed))
        self.component_note.setVisible(bool(self.component_note.text()))
        self.hint.setVisible(index is None)
        self.facts.setText("\n".join(facts))
        details = not self.compact or self.details_toggle.isChecked()
        if self.compact:
            self.details_toggle.setVisible(bool(facts))
        self.facts.setVisible(bool(facts) and details)
        self.record_warnings.setText("Importer warnings for this record:\n" + "\n".join(f"• {w}" for w in warnings)
                                     if warnings else "")
        self.record_warnings.setVisible(bool(warnings))
        self.provisional.setVisible(provisional)
        outcome = self.slot.outcome
        self.status.setObjectName("error" if state == sm.REFUSED else "hint")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText({sm.DRAWING: sm.DRAWING_TEXT,
                             sm.REFUSED: (f"No shape drawn: {outcome.error}" if outcome else "")}.get(state, ""))
        self.status.setVisible(state in (sm.DRAWING, sm.REFUSED))
        if state == sm.SHOWN and outcome is not None:
            if not self.image.set_image(outcome.image):
                self.status.setText("No shape drawn: the image could not be read.")
                self.status.setVisible(True)
            self.caption.setText("\n".join(outcome.lines))
        else:
            self.image.clear_image()
            self.caption.setText("")
        self.caption.setVisible(state == sm.SHOWN and details)
        self.note.setVisible(has_preview and not self.compact)
        if self.view_combo is not None:
            self.projection.setText(sm.view_text(self.view_combo.currentData()))
