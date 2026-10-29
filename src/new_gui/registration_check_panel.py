"""NEW-GUI.5: the Analysis page's archived physical registration applicability check (PySide6).

It uses the FE results and the experimental modal set already chosen for the frequency diagnostic (NEW-GUI.4); it
has no set choice of its own. Check reference registration is disabled, with the reason shown, until both files are
read and a set is chosen, and nothing runs by itself: before a click the result is "Not checked". The service runs in
a worker thread (``new_gui.registration_check_model.run_check``); its outcome comes back to the window's thread
through a queued signal. A replaced or cleared file, Inspect again, another modal set or a closed window cancels the
request and discards its outcome.

A verified registration is shown with the service's specimen, fixture, modal set, FE geometry identity, experimental
source, frozen registration, checks and limits, and the warning that it is not applied. A refusal shows the
service's reason; it does not say the experiment is wrong, and the frequency diagnostic stays available.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from new_gui import diagnostic_model as dm
from new_gui import registration_check_model as rm


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if wrap:
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # long text never widens
        label.setMinimumWidth(0)
    return label


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class _Bridge(QObject):
    """Carries a check's outcome from its worker thread to the window's thread (a queued signal)."""

    done = Signal(object)


FIELDS = (("Specimen and fixture", lambda v: f"{v.specimen} — {v.fixture_id}"),
          ("Modal set chosen", lambda v: v.selected_set),
          ("Archived modal set", lambda v: v.archived_modal_set),
          ("FE geometry", lambda v: v.fe_geometry),
          ("Experimental source", lambda v: v.experimental_source),
          ("Frozen registration", lambda v: f"{v.registration} ({v.registration_file})"))


class RegistrationCheckPanel(QFrame):
    """One card: the inputs it uses, the command, and the verified registration or the service's refusal."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.fe_preview = None
        self.experimental_preview = None
        self.set_index: Optional[int] = None
        self.slot = rm.RegistrationSlot()
        self.discarded = 0  # outcomes of cancelled or stale requests, never shown
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(_label(rm.TITLE, "cardTitle"))
        self.badge = _label(rm.NOT_CHECKED, "badge", wrap=False)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(_label(rm.HINT, "hint"))
        self.chosen_set = _label("", "hint")
        layout.addWidget(self.chosen_set)
        self.provisional = _label(rm.PROVISIONAL_TEXT, "error")
        layout.addWidget(self.provisional)
        buttons = QHBoxLayout()
        self.run_button = QPushButton(rm.RUN)
        self.run_button.setObjectName("primary")
        self.run_button.setToolTip("Check whether an accepted archived physical registration applies to the read "
                                   "data. The registration is not applied.")
        self.run_button.clicked.connect(self.run)
        buttons.addWidget(self.run_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.why_unavailable = _label("", "hint")
        layout.addWidget(self.why_unavailable)
        self.status = _label("", "hint")
        layout.addWidget(self.status)
        self.warning = _label(rm.WARNING, "warnings")
        layout.addWidget(self.warning)
        self.details = QWidget()
        grid = QGridLayout(self.details)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(1, 1)
        self.fields: dict[str, QLabel] = {}
        for row, (caption, _value) in enumerate(FIELDS):
            grid.addWidget(_label(caption, wrap=False), row, 0, Qt.AlignmentFlag.AlignTop)
            self.fields[caption] = _label("", "")
            grid.addWidget(self.fields[caption], row, 1)
        layout.addWidget(self.details)
        self.checks = _label("", "hint")
        layout.addWidget(self.checks)
        self.limits = _label("", "hint")
        layout.addWidget(self.limits)
        self.refusal = _label("", "")
        layout.addWidget(self.refusal)
        self.refusal_note = _label(rm.REFUSAL_NOTE, "hint")
        layout.addWidget(self.refusal_note)
        self._refresh()

    # ------------------------------------------------------------------------------------------ inputs

    def set_inputs(self, fe_preview, experimental_preview, set_index: Optional[int]) -> None:
        """The read previews and the set chosen for the frequency diagnostic; any change discards the result."""
        if (fe_preview is self.fe_preview and experimental_preview is self.experimental_preview
                and set_index == self.set_index):
            return
        self.fe_preview, self.experimental_preview, self.set_index = fe_preview, experimental_preview, set_index
        self.slot.reset()
        self._refresh()

    def unavailable(self) -> tuple:
        return dm.unavailable(self.fe_preview, self.experimental_preview, self.set_index)

    def ready(self) -> bool:
        return not self.unavailable()

    # ------------------------------------------------------------------------------------------ running

    def run(self) -> bool:
        """Run the check in a worker thread; returns False when it cannot run now."""
        if not self.ready() or self.slot.state == rm.RUNNING:
            return False
        request = (self.fe_preview, self.experimental_preview, self.set_index)
        token, cancel_event = self.slot.start(request)
        worker = threading.Thread(target=self._work, args=(*request, token, cancel_event),
                                  name="new-gui-registration-check", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        self._refresh()
        return True

    def _work(self, fe_preview, experimental_preview, set_index, token, cancel_event) -> None:
        outcome = rm.run_check(fe_preview, experimental_preview, set_index, token, cancel_event)  # no widget
        try:
            self._bridge.done.emit(outcome)
        except RuntimeError:  # the panel is already gone
            pass

    def _done(self, outcome: rm.RegistrationOutcome) -> None:
        if not self.slot.finish(outcome):
            self.discarded += 1  # a cancelled or stale request: the current state is kept
            return
        self._refresh()

    def busy(self) -> bool:
        return self.slot.state == rm.RUNNING or any(thread.is_alive() for thread in self._threads)

    def cancel(self) -> None:
        self.slot.reset()
        self._refresh()

    # ------------------------------------------------------------------------------------------ display

    @property
    def view(self) -> Optional[rm.RegistrationView]:
        outcome = self.slot.outcome
        return outcome.view if self.slot.state == rm.VERIFIED_STATE and outcome is not None else None

    def _refresh(self) -> None:
        state = self.slot.state
        experimental = self.experimental_preview
        self.chosen_set.setText(rm.NO_SET if experimental is None or self.set_index is None
                                else f"Modal set: {dm.set_title(experimental, self.set_index)}")
        self.provisional.setVisible(rm.set_is_provisional(experimental, self.set_index))
        reasons = self.unavailable()
        self.run_button.setEnabled(not reasons and state != rm.RUNNING)
        self.why_unavailable.setText("\n".join(reasons))
        self.why_unavailable.setVisible(bool(reasons))
        self.badge.setText({rm.RUNNING: rm.CHECKING, rm.VERIFIED_STATE: rm.VERIFIED, rm.REFUSED: rm.NOT_CONFIRMED,
                            rm.FAILED: rm.CHECK_FAILED}.get(state, rm.NOT_CHECKED))
        self.badge.setProperty("state", {rm.VERIFIED_STATE: "read", rm.REFUSED: "blocked",
                                         rm.FAILED: "blocked", rm.RUNNING: "chosen"}.get(state, "empty"))
        _restyle(self.badge)
        outcome = self.slot.outcome
        self.status.setObjectName("error" if state == rm.FAILED else "hint")
        _restyle(self.status)
        self.status.setText({rm.RUNNING: rm.CHECKING_TEXT,
                             rm.FAILED: outcome.error if outcome is not None else ""}.get(state, ""))
        self.status.setVisible(state in (rm.RUNNING, rm.FAILED))
        view = self.view
        for widget in (self.warning, self.details, self.checks, self.limits):
            widget.setVisible(view is not None)
        for caption, value in FIELDS:
            self.fields[caption].setText(value(view) if view is not None else "")
        self.checks.setText("Checks by the service:\n" + "\n".join(f"• {c}" for c in view.checks) if view else "")
        self.limits.setText("Limits:\n" + "\n".join(f"• {c}" for c in view.limits) if view else "")
        refused = state == rm.REFUSED and outcome is not None
        self.refusal.setText(f"Not confirmed by the service: {outcome.refusal}" if refused else "")
        self.refusal.setVisible(refused)
        self.refusal_note.setVisible(refused)


__all__ = ["RegistrationCheckPanel"]
