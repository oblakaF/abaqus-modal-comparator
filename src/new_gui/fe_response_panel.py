"""PRIORITY-10: D. FE Response of the Plate Study page (PySide6; RESEARCH_ONLY, FE-only).

``services.single_plate_fe_response`` on one FE model of a plate: choose its baseline package and its solved states
(a folder of states, or a family declaration), check their origin, follow every FE branch, compute the central
sensitivities and explore the FE-only What-If inside the solved range, against the solved FE points. Reading and
tracking run in the background and can be cancelled. The experimental records read in the Workspace are shown beside
the FE frequencies only as FREQUENCY_PROXIMITY_ONLY: never a pair, never a target. Nothing here runs Abaqus, an LM or
Auto-ID, and no disk is searched.
"""

from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from new_gui.diagnostic_panel import DiagnosticTable
from services import single_plate_fe_response as fr

TITLE = "D. FE Response Workbench"
INTRO = ("FE-only: one FE model of a plate, its baseline and its solved perturbation states. Every elastic FE branch is "
         "followed by FE-to-FE MAC (never by frequency); the central sensitivities use the actual parameter values of "
         "the two solved states; the What-If is a local log-linear prediction inside the solved range, compared with "
         "the solved FE points. Not an Abaqus solve, not a material identification; experimental records are never "
         "paired here.")
SECTIONS = ("1. Sources", "2. Tracking", "3. Sensitivities", "4. What-If", "5. Report")


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def _card(title: str) -> tuple:
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    if title:
        layout.addWidget(_label(title, "cardTitle"))
    return card, layout


def _edit(name: str, text: str = "") -> QLineEdit:
    edit = QLineEdit(text)
    edit.setObjectName(name)
    edit.setMinimumWidth(0)
    return edit


def _num(value, digits=5) -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, tuple)):
        return " / ".join(_num(v, digits) for v in value)
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


class _Bridge(QObject):
    done = Signal(object)


class FEResponsePanel(QWidget):
    """Section D of the Plate Study page."""

    def __init__(self, ask_file: Optional[Callable[[str, str], str]] = None,
                 ask_folder: Optional[Callable[[str], str]] = None, ask_save: Optional[Callable[[], str]] = None):
        super().__init__()
        self._ask_file = ask_file or self._dialog_file
        self._ask_folder = ask_folder or self._dialog_folder
        self._ask_save = ask_save or self._dialog_save
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)
        self._token, self._threads, self._cancel_event, self.running = 0, [], None, None
        self.baseline_manifest: Optional[str] = None
        self.baseline_inp: Optional[str] = None
        self.family: Optional[fr.Family] = None
        self.analysed_family: Optional[dict] = None  # the family the shown result belongs to
        self.identity_rows: list = []
        self.result: Optional[dict] = None
        self.comparison: Optional[dict] = None
        self.prediction: Optional[dict] = None
        self.reopened: Optional[dict] = None
        self.invalidated: Optional[str] = None  # why the shown results stopped being current (a new choice)
        self.source_check: Optional[dict] = None  # the last check of the FE sources before a prediction or export
        self.last_export: tuple = ()
        self.records: list = []  # experimental records (number, hz) read in the Workspace: proximity only
        self.tables: dict = {}
        self.active = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        head, head_layout = _card(TITLE)
        head_layout.addWidget(_label(INTRO, "hint"))
        head_layout.addWidget(_label(fr.SCIENTIFIC_STATUS, "warnings"))
        grid = QGridLayout()
        self.model_edit, self.specimen_edit = _edit("frModel", "FE model"), _edit("frSpecimen", "specimen")
        # plain captions: a wrapping label (Ignored width) collapses in a column that does not stretch
        grid.addWidget(QLabel("FE model id"), 0, 0)
        grid.addWidget(self.model_edit, 0, 1)
        grid.addWidget(QLabel("Specimen id"), 1, 0)
        grid.addWidget(self.specimen_edit, 1, 1)
        grid.setColumnStretch(1, 1)
        head_layout.addLayout(grid)
        buttons = QVBoxLayout()  # a column: no page width; clicked(bool) never reaches an optional argument
        for text, slot, name in (("Choose FE baseline manifest...", lambda: self.choose_baseline(), "frBaseline"),
                                 ("Choose baseline INP (optional)...", lambda: self.choose_baseline_inp(), "frBaseInp"),
                                 ("Choose folder of FE states...", lambda: self.choose_states_folder(), "frFolder"),
                                 ("Load FE family declaration...", lambda: self.load_declaration(), "frDeclaration"),
                                 ("Run FE-to-FE tracking", lambda: self.run(), "frRun"),
                                 ("Cancel", lambda: self.cancel(), "frCancel"),
                                 ("Save session...", lambda: self.save_session(), "frSave"),
                                 ("Open session...", lambda: self.open_session(), "frOpen"),
                                 ("Export results...", lambda: self.export(), "frExport")):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            buttons.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            setattr(self, f"_{name}", button)
        head_layout.addLayout(buttons)
        self.family_line = _label("", "")
        self.family_line.setObjectName("frFamily")
        head_layout.addWidget(self.family_line)
        self.state_line = _label("", "")
        self.state_line.setObjectName("frState")
        head_layout.addWidget(self.state_line)
        self.message = _label("", "hint")
        self.message.setObjectName("frMessage")
        head_layout.addWidget(self.message)
        layout.addWidget(head)
        steps_card, steps_layout = _card("Sections")
        sgrid = QGridLayout()
        self.step_buttons = QButtonGroup(self)
        self.pages = QStackedWidget()
        self.bodies = []
        for index, title in enumerate(SECTIONS):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.addWidget(_label(title, "sectionTitle"))
            if index == 3:
                self._build_what_if(page_layout)
            body = QVBoxLayout()
            page_layout.addLayout(body)
            page_layout.addStretch(1)
            self.bodies.append(body)
            self.pages.addWidget(page)
            button = QPushButton(title)
            button.setObjectName(f"frStep{index + 1}")
            button.setCheckable(True)
            self.step_buttons.addButton(button, index)
            sgrid.addWidget(button, index // 2, index % 2)
        self.step_buttons.button(0).setChecked(True)
        self.step_buttons.idClicked.connect(self.show_step)
        steps_layout.addLayout(sgrid)
        layout.addWidget(steps_card)
        layout.addWidget(self.pages)
        self._refresh()

    def _build_what_if(self, layout) -> None:
        card, inner = _card("FE-only What-If (inside the solved range; never extrapolated)")
        self.parameter_choice = QComboBox()
        self.parameter_choice.setObjectName("frParameter")
        self.parameter_choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.parameter_choice.setMinimumContentsLength(10)
        inner.addWidget(self.parameter_choice, 0, Qt.AlignmentFlag.AlignLeft)
        self.value_edit = _edit("frValue")
        self.value_edit.setPlaceholderText("trial value (MPa)")
        inner.addWidget(self.value_edit)
        self.range_line = _label("", "hint")
        self.range_line.setObjectName("frRange")
        inner.addWidget(self.range_line)
        predict = QPushButton("Predict FE frequencies")
        predict.setObjectName("frPredict")
        predict.clicked.connect(lambda: self.predict())
        inner.addWidget(predict, 0, Qt.AlignmentFlag.AlignLeft)
        self.parameter_choice.currentIndexChanged.connect(lambda _i: self._show_range())
        layout.addWidget(card)

    # ------------------------------------------------------------------------------------------ dialogs

    def _dialog_file(self, title: str, pattern: str) -> str:
        return QFileDialog.getOpenFileName(self, title, "", pattern)[0]

    def _dialog_folder(self, title: str) -> str:
        return QFileDialog.getExistingDirectory(self, title)

    def _dialog_save(self) -> str:
        return QFileDialog.getSaveFileName(self, "Save the FE response session", "fe_response_session.json",
                                           "Session (*.json)")[0]

    # ------------------------------------------------------------------------------------------ state

    def activate(self) -> None:
        if not self.active:
            self.active = True
            self._refresh()

    def show_step(self, index: int) -> None:
        self.activate()
        self.pages.setCurrentIndex(index)
        self.step_buttons.button(index).setChecked(True)

    def _say(self, text: str) -> None:
        self.message.setText(text)

    def set_inputs(self, fe_preview, fe_identity, experimental_preview, experimental_identity, set_index) -> None:
        """The Workspace's experimental records (proximity only). A change of the modal set never invalidates the FE
        results: only the experimental display changes."""
        records = []
        sets = getattr(experimental_preview, "sets", None) or ()
        if set_index is not None and 0 <= set_index < len(sets):
            records = [{"number": int(r.number), "hz": float(r.frequency_hz)} for r in sets[set_index].records]
        self.records = records
        self._refresh()

    def freshness(self) -> tuple:
        """CURRENT, STALE (another baseline, INP or family was chosen, the chosen family is not the one analysed, or
        the FE sources changed on disk), STORED (a reopened session whose FE sources verify) or NONE."""
        if self.result is None:
            return "NONE", ""
        if self.invalidated:
            return "STALE", self.invalidated
        if self.source_check is not None and self.source_check.get("state") == "STALE":
            return "STALE", "the FE sources changed on disk: " + "; ".join(self.source_check.get("reasons", ()))
        if self.reopened is not None:
            if self.reopened.get("state") == "STALE":
                return "STALE", "; ".join(self.reopened.get("reasons", ()))
            if self.family is None:
                return "STORED", self.reopened.get("note", "")
        if self.family is None or fr.family_to_dict(self.family) != self.analysed_family:
            return "STALE", "the FE baseline, the states or their parameters changed since the tracking"
        return "CURRENT", ""

    # ------------------------------------------------------------------------------------------ background work

    def _start(self, label: str, work, finish) -> None:
        self._token += 1
        token, cancel_event = self._token, threading.Event()
        self._cancel_event, self.running = cancel_event, label

        def run():
            try:
                outcome = work(cancel_event)
            except Exception as error:  # noqa: BLE001  (shown to the user)
                outcome = error
            try:
                self._bridge.done.emit((token, finish, outcome))
            except RuntimeError:
                pass

        thread = threading.Thread(target=run, daemon=True, name="new-gui-fe-response")
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        self._say(label)
        self._refresh()
        thread.start()

    def _done(self, payload) -> None:
        token, finish, outcome = payload
        if token != self._token:
            return
        self.running, self._cancel_event = None, None
        finish(outcome)

    def busy(self) -> bool:
        return self.running is not None or any(t.is_alive() for t in self._threads)

    def cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        if self.running is not None:
            self._token += 1
            self.running = None
            self._say("Cancelled: nothing was kept from the cancelled work.")
            self._refresh()

    def wait_idle(self, timeout: float = 300.0) -> bool:
        from PySide6.QtWidgets import QApplication

        end = time.monotonic() + timeout
        while self.busy() and time.monotonic() < end:
            QApplication.processEvents()
            time.sleep(0.02)
        QApplication.processEvents()
        return not self.busy()

    # ------------------------------------------------------------------------------------------ commands

    def _invalidate(self, reason: str) -> None:
        """A new baseline, baseline INP or family: the shown results stop being current at once and running work is
        discarded. Nothing is predicted, saved or exported from them until the tracking runs again."""
        if self._cancel_event is not None:
            self._cancel_event.set()
        if self.running is not None:
            self._token += 1
            self.running, self._cancel_event = None, None
        if self.result is not None:
            self.invalidated = reason
        self.prediction = None

    def choose_baseline(self, path: Optional[str] = None) -> bool:
        self.activate()
        path = path if path is not None else self._ask_file("Choose the FE baseline package (manifest.json)",
                                                            "FE package (manifest.json)")
        if not path:
            return False
        self._invalidate(f"the FE baseline was chosen again ({path}): the results belong to the previous choice")
        self.baseline_manifest, self.family = path, None  # the family belonged to the previous baseline
        self._say(f"Baseline: {path}. Choose the folder of its solved states (or load a declaration)."
                  + (" The previous FE results are STALE." if self.result is not None else ""))
        self._refresh()
        return True

    def choose_baseline_inp(self, path: Optional[str] = None) -> bool:
        self.activate()
        path = path if path is not None else self._ask_file("Choose the baseline INP (read for its parameters only)",
                                                            "Abaqus input (*.inp)")
        if not path:
            return False
        self._invalidate(f"the baseline INP was chosen again ({path}): the results belong to the previous choice")
        self.baseline_inp, self.family = path, None  # the states' parameters were read against the previous INP
        self._say(f"Baseline INP: {path} (its constants give the baseline parameter values; never run). Choose the "
                  "folder of the solved states again." + (" The previous FE results are STALE." if self.result
                                                          is not None else ""))
        self._refresh()
        return True

    def choose_states_folder(self, folder: Optional[str] = None) -> bool:
        """The family of a folder: each sub-folder with an extracted package and one INP is a state."""
        self.activate()
        if not self.baseline_manifest:
            self._say("Choose the FE baseline manifest first.")
            return False
        folder = folder if folder is not None else self._ask_folder("Choose the folder of the solved FE states")
        if not folder:
            return False
        try:
            self.family = fr.family_from_folder(folder, self.baseline_manifest, self.model_edit.text().strip() or
                                                "FE model", self.specimen_edit.text().strip() or "specimen",
                                                baseline_inp=self.baseline_inp)
        except fr.FamilyRefused as error:
            self._say(f"Not read: {error}")
            return False
        self._invalidate(f"another FE family was chosen (the folder {folder})")
        self.reopened = None
        self._say(f"{len(self.family.variants)} FE states found in {folder}"
                  + (f"; not used: {'; '.join(f'{a}: {b}' for a, b in self.family.problems)}" if self.family.problems
                     else "") + ". Run the FE-to-FE tracking.")
        self._refresh()
        return True

    def load_declaration(self, path: Optional[str] = None) -> bool:
        self.activate()
        path = path if path is not None else self._ask_file("Load an FE family declaration", "FE family (*.json)")
        if not path:
            return False
        try:
            family = fr.family_from_declaration(path)
        except fr.FamilyRefused as error:
            self._say(f"Not read: {error}")
            return False
        self._invalidate(f"another FE family was chosen (the declaration {path})")
        self.family = family
        self.baseline_manifest, self.baseline_inp = family.baseline.manifest, family.baseline.inp
        self.model_edit.setText(self.family.model_id)
        self.specimen_edit.setText(self.family.specimen_id)
        self.reopened = None
        self._say(f"FE family {self.family.model_id}: {len(self.family.variants)} states ({self.family.kind}). Run the "
                  "FE-to-FE tracking.")
        self._refresh()
        return True

    def run(self) -> bool:
        """Hash the sources, read every package and follow the branches (in the background, cancellable)."""
        self.activate()
        if self.family is None or self.busy():
            self._say("Choose an FE family first." if self.family is None else "Busy.")
            return False
        family = self.family

        def work(cancel):
            rows = fr.identities(family, cancel)
            progress = lambda text: None  # noqa: E731
            result = fr.analyse(family, cancel, progress)
            # the identities were taken before the read: the files read must still be those files
            check = fr.verify_sources(rows, fr.used_states(result), cancel=cancel)
            if check["state"] == "STALE":
                raise fr.FamilyRefused("the FE sources changed or cannot be verified: " + "; ".join(check["reasons"]))
            comparison = fr.compare_with_archive(result, rows[0]["manifest_sha256"])
            return rows, result, comparison

        def finish(outcome):
            if isinstance(outcome, Exception):
                self._say(f"Not computed: {outcome}")
            else:
                self.identity_rows, self.result, self.comparison = outcome
                self.analysed_family, self.prediction, self.reopened = fr.family_to_dict(family), None, None
                self.invalidated, self.source_check = None, None
                self._fill_parameters()
                self._say(f"{self.result['kind']}: {len(self.result['branches'])} elastic FE branches followed into "
                          f"{len(self.result['states_used'])} states — status {self.result['status']}.")
            self._refresh()

        self._start("Reading the FE packages and following the branches (cancellable)...", work, finish)
        return True

    def _fill_parameters(self) -> None:
        self.parameter_choice.blockSignals(True)
        self.parameter_choice.clear()
        params = list((self.result or {}).get("baseline_parameters") or {})
        for p in params:
            self.parameter_choice.addItem(p, p)
        if "E1" in params and "E2" in params:
            self.parameter_choice.addItem(f"{fr.JOINT_E} — {fr.CONDITIONAL}", fr.JOINT_E)
        self.parameter_choice.blockSignals(False)
        self._show_range()

    def _show_range(self) -> None:
        parameter = self.parameter_choice.currentData()
        if not parameter or not self.result:
            self.range_line.setText("")
            return
        try:
            low, high = fr._range(self.result, "E1" if parameter == fr.JOINT_E else parameter)
            p0 = self.result["baseline_parameters"]["E1" if parameter == fr.JOINT_E else parameter]
            self.range_line.setText(f"Solved range {low:g}–{high:g} MPa (baseline {p0:g}); outside it nothing is "
                                    "predicted.")
        except fr.WhatIfRefused as error:
            self.range_line.setText(str(error))

    def _verified(self, label: str, then) -> None:
        """Verify the FE sources of the shown results again in the background (manifests, packages, INPs, every used
        state), then ``then(check)``; a changed source makes the results STALE instead."""
        rows, used = list(self.identity_rows), fr.used_states(self.result)
        family = self.analysed_family or {}
        paths = {m.get("id"): m for m in [family.get("baseline") or {}] + list(family.get("variants") or ())
                 if isinstance(m, dict)}

        def finish(outcome):
            if isinstance(outcome, Exception):
                self._say(f"Not done: the FE sources cannot be verified now ({outcome}).")
            else:
                self.source_check = outcome
                if outcome["state"] == "STALE":
                    self.prediction = None
                    self._say("Not done: the FE sources changed on disk, the FE results are STALE: "
                              + "; ".join(outcome["reasons"]) + ". Run the tracking again.")
                else:
                    then(outcome)
            self._refresh()

        self._start(label, lambda cancel: fr.verify_sources(rows, used, paths, cancel), finish)

    def predict(self, parameter: Optional[str] = None, value: Optional[float] = None) -> bool:
        """A refusal (results not current, out of range, ...) is immediate (False). An accepted prediction (True) is
        shown only after the FE sources verify again in the background (``wait_idle``)."""
        self.activate()
        state, reason = self.freshness()
        if state not in ("CURRENT", "STORED"):
            self._say(f"No prediction: the FE results are {state} ({reason}).")
            return False
        if self.busy():
            self._say("Busy.")
            return False
        parameter = parameter or self.parameter_choice.currentData()
        try:
            value = float(value if value is not None else self.value_edit.text().replace(",", "."))
        except (TypeError, ValueError):
            self._say("Give the trial value as a number of MPa.")
            return False
        try:
            prediction = fr.what_if(self.result, {parameter: value})
        except fr.WhatIfRefused as error:
            self.prediction = None
            self._say(f"No prediction: {error}")
            self._refresh()
            return False

        def then(_check):
            self.prediction = prediction
            self._say(f"FE-only prediction for {parameter} = {value:g} MPa — {fr.PREDICTION} (FE sources verified "
                      "again).")
            self.show_step(3)

        self._verified("Verifying the FE sources before the prediction (cancellable)...", then)
        return True

    def session(self) -> dict:
        family = self.family or fr.family_from_record(self.analysed_family)
        return fr.session_record(family, self.identity_rows, self.result, self.prediction,
                                 fr.experiment_rows(self.records, self.result, self.prediction) if self.records else None,
                                 self.comparison)

    def save_session(self, path: Optional[str] = None) -> bool:
        self.activate()
        state, reason = self.freshness()
        if self.result is None or state not in ("CURRENT", "STORED"):
            self._say("No FE results to save." if self.result is None else
                      f"Not saved: the FE results are {state} ({reason}).")
            return False
        path = path if path is not None else self._ask_save()
        if not path:
            return False
        fr.save_session(self.session(), path)
        self._say(f"Session saved: {path} (no FE data inside; identities and results only).")
        return True

    def open_session(self, path: Optional[str] = None) -> bool:
        self.activate()
        if self.busy():
            return False
        path = path if path is not None else self._ask_file("Open an FE response session", "Session (*.json)")
        if not path:
            return False
        try:
            record = fr.open_session(path)
        except fr.FamilyRefused as error:
            self._say(f"Not opened: {error}")
            return False

        def finish(outcome):
            if isinstance(outcome, Exception):
                self._say(f"Not opened: {outcome}")
            else:
                self.family = None
                self.result, self.identity_rows = record.get("result"), record.get("identities") or []
                self.comparison, self.prediction = record.get("archive_comparison"), record.get("what_if")
                self.analysed_family, self.reopened = record.get("family"), outcome
                self.invalidated, self.source_check = None, None
                self.model_edit.setText((record.get("family") or {}).get("model_id") or "")
                self.specimen_edit.setText((record.get("family") or {}).get("specimen_id") or "")
                self._fill_parameters()
                self._say(f"Session opened: {path}. {outcome['note']}.")
            self._refresh()

        self._start("Verifying the session's FE sources (manifests, packages, INPs, used states)...",
                    lambda cancel: fr.session_state(record, cancel), finish)
        return True

    def export(self, folder: Optional[str] = None) -> bool:
        """A refusal is immediate (False); an accepted export (True) is written only after the FE sources verify
        again in the background (``wait_idle``)."""
        self.activate()
        state, reason = self.freshness()
        if self.result is None or state not in ("CURRENT", "STORED"):
            self._say(f"Not exported: the FE results are {state} ({reason}).")
            return False
        if self.busy():
            self._say("Busy.")
            return False
        folder = folder if folder is not None else self._ask_folder("Choose the folder for the FE response report")
        if not folder:
            return False
        record = self.session()

        def then(check):
            try:
                written = fr.export_session({**record, "source_check": check}, folder)
            except (fr.FamilyRefused, OSError) as error:
                self._say(f"Not exported: {error}")
                return
            self.last_export = written
            self._say("Written (FE sources verified again):\n" + "\n".join(str(p) for p in written))

        self._verified("Verifying the FE sources before the export (cancellable)...", then)
        return True

    # ------------------------------------------------------------------------------------------ display

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _table(self, body, key, title, headers, rows, stretch, text_columns=()) -> None:
        body.addWidget(_label(title, "sectionTitle"))
        if not rows:
            body.addWidget(_label("None.", "hint"))
            return
        table = DiagnosticTable(headers, [tuple(_num(v) for v in row) for row in rows], stretch, (), text_columns)
        table.setObjectName(f"fr_{key}")
        self.tables[key] = table
        body.addWidget(table)

    def _refresh(self) -> None:
        for body in self.bodies:
            self._clear(body)
        self.tables = {}
        f = self.family
        self.family_line.setText(
            (f"FE family: {f.model_id} · specimen {f.specimen_id} · {f.kind} · baseline {f.baseline.manifest} · "
             f"{len(f.variants)} states") if f else (f"Baseline: {self.baseline_manifest}" if self.baseline_manifest
                                                     else "No FE family chosen."))
        state, reason = self.freshness()
        result = self.result
        if self.running:
            self.state_line.setText(self.running)
        elif result is None:
            self.state_line.setText("")
        elif state in ("CURRENT", "STORED"):
            self.state_line.setText(f"{result.get('kind')} · status {result.get('status')}"
                                    + (" · STORED (sources verified)" if state == "STORED" else ""))
        else:
            self.state_line.setText(f"FE results {state} — NOT CURRENT: {reason}. Run the tracking again.")
        if result is None or state not in ("CURRENT", "STORED"):
            if self.records:
                self._show_experiment(self.bodies[3], {"central": []})
            return
        self._show_sources(self.bodies[0])
        self._show_tracking(result, self.bodies[1])
        self._show_sensitivities(result, self.bodies[2])
        self._show_prediction(result, self.bodies[3])
        self._show_report(result, self.bodies[4])

    def _show_sources(self, body) -> None:
        self._table(body, "sources", "Sources (SHA-256; what cannot be verified is named)",
                    ("State", "Parameter", "Value (MPa)", "Manifest SHA-256", "Package SHA-256", "INP SHA-256",
                     "ODB", "Not verified"),
                    [(r["id"], r["parameter"] or "—", r["value"], r["manifest_sha256"], r["package_sha256"],
                      r["inp_sha256"], r.get("odb_state") or "—", "; ".join(r["not_verified"]) or "—")
                     for r in self.identity_rows], 7, (0, 1, 3, 4, 5, 6, 7))
        checks = (self.analysed_family or {}).get("checks") or []
        if checks:
            body.addWidget(_label("Declared values against the INPs:\n" + "\n".join(f"• {c}" for c in checks), "hint"))
        if self.source_check is not None:
            body.addWidget(_label(f"FE sources verified again before the last prediction / export: "
                                  f"{self.source_check['state']} ({self.source_check.get('basis', '')})", "hint"))
        excluded = (self.result or {}).get("excluded") or []
        problems = (self.result or {}).get("family_problems") or []
        if excluded or problems:
            body.addWidget(_label("Not used:\n" + "\n".join(f"• {a}: {b}" for a, b in excluded + problems), "error"))

    def _show_tracking(self, result, body) -> None:
        states = result.get("states_used", [])
        rows = []
        for b in result["branches"]:
            cells = []
            for vid in states:
                v = b["variants"].get(vid) or {}
                if v.get("status") in fr.TRACKED_STATES:
                    cells.append(f"{v['candidate']}{' (order changed)' if v.get('permutation') else ''} "
                                 f"MAC {_num(v.get('mac'), 3)}")
                else:
                    cells.append(f"LOST — {v.get('reason') or v.get('status')}")
            rows.append((b["branch"], b["hz"], b["cluster"] or "—", *cells))
        self._table(body, "tracking", "FE-to-FE tracking (STRICT_IDENTIFICATION_PAIRING; never by frequency)",
                    ("Branch", "Baseline Hz", "Cluster", *states), rows, 2, tuple(range(len(states) + 3)))
        body.addWidget(_label("Close pairs (confirm_cluster): " + "; ".join(
            f"{'/'.join(c['rows'])} {c['status']}" for c in result.get("clusters", ())) + " · rigid-body modes "
            "excluded by the code's criterion: " + (", ".join(f"FE{n}" for n in result.get("rigid_excluded", ()))
                                                    or "none"), "hint"))

    def _show_sensitivities(self, result, body) -> None:
        params = list(result.get("baseline_parameters") or {})
        rows = []
        for t in result["central"]:
            rows.append((t["term"], t["f0_hz"], *[
                (t["parameters"][p]["s"] if t["parameters"][p].get("s") is not None
                 else t["parameters"][p].get("status")) for p in params]))
        self._table(body, "central", "Central sensitivities s = Δ ln f / Δ ln p (actual parameter values)",
                    ("Term", "f0 (Hz)", *[f"s_{p}" for p in params]), rows, 0, (0,))
        for r in result.get("rank", ()):
            body.addWidget(_label(f"{' / '.join(r['parameters'])}: rank {r['rank']} of {r['of']}, condition "
                                  f"{_num(r['condition'], 2)} over {len(r['terms'])} terms — {r['status']}", "hint"))
        c = self.comparison or {}
        if c:
            body.addWidget(_label(f"PRIORITY-2 archive: {c.get('state')}"
                                  + (f" (max |Δs| {c['max_abs_difference']:.2e}; {c.get('tolerance')})"
                                     if c.get("max_abs_difference") is not None else f" — {c.get('reason', '')}"),
                                  "warnings" if c.get("state") == "DIFFERS" else "hint"))

    def _show_prediction(self, result, body) -> None:
        p = self.prediction
        if p:
            body.addWidget(_label(" · ".join(p["labels"]), "warnings"))
            self._table(body, "what_if", f"FE-only prediction {p['trial']}",
                        ("Term", "f0 (Hz)", "Predicted (Hz)", "Solved FE (Hz)", "Error (%)", "Status", "Linearity"),
                        [(r["term"], r["f0_hz"], r["predicted_hz"], r["solved_hz"], r["error_percent"], r["status"],
                          r.get("linearity") or "—") for r in p["rows"]], 5, (0, 5, 6))
        self._show_experiment(body, result)

    def _show_experiment(self, body, result) -> None:
        if not self.records:
            return
        rows = fr.experiment_rows(self.records, result, self.prediction)
        self._table(body, "experiment", f"Experimental records beside the FE — {fr.PROXIMITY_ONLY}",
                    ("Record", "Measured (Hz)", "Nearest FE term", "FE (Hz)", "Δ (%)", "FE-only prediction (Hz)",
                     "Status"),
                    [(r["record"], r["hz"], r.get("nearest_fe") or "—", r.get("fe_hz"), r.get("difference_percent"),
                      r.get("predicted_hz"), r["status"]) for r in rows], 6, (0, 2, 6))

    def _show_report(self, result, body) -> None:
        body.addWidget(_label("\n".join(f"• {x}" for x in fr.LIMITS), "hint"))
        body.addWidget(_label(f"Basis: {result.get('basis', '—')}", "hint"))


__all__ = ["FEResponsePanel", "SECTIONS", "TITLE"]
