"""APP-DATA.5: View selected FE mode shape in File > Input file registry > Inspect FE modes (real main window).

The mode selected in the FE modes view is drawn on its own FE nodes by services.modal_data_viewer (role FE) in the
shape window of APP-DATA.4, on a background thread; the outcome is posted back to the Tk thread. Every loaded mode can
be drawn (rigid-body frames and the first elastic mode too), nothing in the main window changes, the package is only
read, no process is started, a superseded or cancelled drawing is never shown and degenerate geometry is refused with
its reason. Synthetic temporary packages only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402

import main  # noqa: E402,F401  (the installed chain, as in the application)
import abaqus_bridge  # noqa: E402
from services import local_fe_preview as fe_preview  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from test_app_p1_stale_results import _App  # noqa: E402
from test_local_fe_preview import PLATE_NODES, plate_modes, write_shape_package  # noqa: E402


def fingerprint(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


class FeShapeWindowTests(_App):
    def setUp(self) -> None:
        super().setUp()
        for target in ("subprocess.Popen", "abaqus_bridge.run_abaqus_extraction"):
            patcher = mock.patch(target, side_effect=AssertionError(f"{target} must not run for a preview"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def dialog(self, application):
        import menu_ui

        self.store = self.folder / "profile" / registry.STORE_NAME
        application.local_input_registry_store = self.store
        dialog = menu_ui.InputRegistryDialog(application)
        self.addCleanup(lambda: dialog.window.destroy() if dialog.window.winfo_exists() else None)
        return dialog

    def inspect(self, dialog, manifest, label="Synthetic plate"):
        entry, _ = registry.add_entry(self.store, registry.FE, manifest, label)
        dialog.refresh(select=entry["id"])
        window = dialog.inspect_selected()
        self.addCleanup(window.close)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and window.preview is None and window.error is None:
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(window.error)
        return window

    def pump(self, shape, timeout=60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and (any(t.is_alive() for t in shape.threads) or not shape.results.empty()
                                               or shape.message.startswith("Drawing")):
            self.root.update()
            time.sleep(0.02)
        for _ in range(5):
            self.root.update()

    def select(self, window, position: int) -> None:
        window.tree.selection_set(str(position))
        self.root.update()

    def choose(self, shape, component: str) -> None:
        shape.component.set(fe_preview.COMPONENT_TEXT[component])
        shape.component_box.event_generate("<<ComboboxSelected>>")
        self.pump(shape)

    def plate(self, name="plate"):
        return write_shape_package(self.folder / name, PLATE_NODES, plate_modes(PLATE_NODES))

    def test_the_selected_mode_is_drawn_and_nothing_else_changes(self):
        application = self.application()
        dialog = self.dialog(application)
        manifest = self.plate()
        before_package = fingerprint(manifest.parent)
        fields = (application.abaqus_path.get(), application.experimental_path.get(),
                  application.experimental_modal_set_key.get(), application.result is None, application.running)
        with mock.patch.object(application, "_start", side_effect=AssertionError("nothing is run")):
            window = self.inspect(dialog, manifest)
            before_store = self.store.read_bytes()
            self.assertEqual(str(window.shape_button.cget("state")), "disabled")  # no mode selected
            self.assertIsNone(window.view_selected_shape())
            self.select(window, 0)  # a rigid-body frame
            self.assertEqual(str(window.shape_button.cget("state")), "normal")
            shape = window.view_selected_shape()
            self.pump(shape)
            self.assertEqual(shape.window.title(), "FE mode shape — Synthetic plate")
            self.assertEqual((shape.shown.index, shape.shown.mode), (0, window.preview.modes[0]))
            self.assertIsNotNone(shape.photo)
            self.assertEqual(shape.banner.get(), "")
            self.assertEqual(list(shape.component_box.cget("values")),
                             [fe_preview.COMPONENT_TEXT[key] for key in fe_preview.SHAPE_COMPONENTS])

            self.select(window, 6)  # the first elastic mode: the open view follows the selection
            self.pump(shape)
            self.assertEqual((shape.shown.index, shape.shown.mode.number), (6, 7))
            self.assertIn("FE mode 7 — 19.07 Hz; frequency source: ", shape.caption.get())

            self.choose(shape, "z")
            self.assertEqual((shape.shown.component, shape.shown.mode.number), ("z", 7))
            self.assertIn("Shown: U3 on 20 FE nodes", shape.caption.get())
            self.choose(shape, "x")  # U1 of a bending mode: computed zeros, drawn as they are
            self.assertEqual(shape.shown.component, "x")

            window.tree.selection_remove(window.tree.selection())
            self.root.update()
            self.assertIsNone(shape.shown)
            self.assertEqual(shape.message, "No FE mode is selected.")
            self.assertEqual(str(window.shape_button.cget("state")), "disabled")
        self.assertEqual((application.abaqus_path.get(), application.experimental_path.get(),
                          application.experimental_modal_set_key.get(), application.result is None,
                          application.running), fields)
        self.assertEqual(fingerprint(manifest.parent), before_package)
        self.assertEqual(self.store.read_bytes(), before_store)
        loaded = abaqus_bridge.load_extracted_odb(manifest)
        self.assertEqual([m.number for m in window.preview.modes], [int(m.number) for m in loaded.modes])

    def test_a_superseded_drawing_is_never_shown(self):
        application = self.application()
        window = self.inspect(self.dialog(application), self.plate())
        real = fe_preview.render_fe_mode_shape
        gate, entered = threading.Event(), threading.Event()

        def slow_first(preview, position, *args, **kwargs):
            if position == 0:
                entered.set()
                gate.wait(30)
            return real(preview, position, *args, **kwargs)

        with mock.patch.object(fe_preview, "render_fe_mode_shape", side_effect=slow_first):
            self.select(window, 0)
            shape = window.view_selected_shape()
            self.assertTrue(entered.wait(10))
            self.assertIn("Drawing FE mode 1", shape.message)
            self.select(window, 7)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and shape.shown is None:
                self.root.update()
                time.sleep(0.02)
            self.assertEqual(shape.shown.mode.number, 8)
            gate.set()
            self.pump(shape)
        self.assertEqual(shape.shown.mode.number, 8)  # the late drawing of mode 1 is discarded
        self.assertEqual([p.name for p in shape.folder.iterdir()], [shape.shown.image_path.parent.name])

    def test_degenerate_geometry_states_why_and_draws_no_arbitrary_normal(self):
        application = self.application()
        dialog = self.dialog(application)
        line = [(n, 0.05 * n, 0.0, 0.0) for n in range(1, 7)]
        bending = np.column_stack([np.zeros(6), np.zeros(6), np.sin(np.linspace(0.2, 2.9, 6))])
        window = self.inspect(dialog, write_shape_package(self.folder / "line", line, [(1, 25.0, bending)]), "Beam")
        self.select(window, 0)
        shape = window.view_selected_shape()
        self.pump(shape)
        self.assertIsNone(shape.shown)
        self.assertIsNone(shape.photo)
        self.assertIn("lie on one line: no best-fit plane", shape.message)
        self.choose(shape, "z")
        self.assertEqual(shape.shown.component, "z")
        self.assertIsNotNone(shape.photo)

        two = [(1, 0.0, 0.0, 0.0), (2, 0.3, 0.0, 0.0)]
        window = self.inspect(dialog, write_shape_package(self.folder / "two", two, [
            (1, 21.0, np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]))]), "Two nodes")
        self.select(window, 0)
        shape = window.view_selected_shape()
        self.pump(shape)
        self.assertIsNone(shape.shown)
        self.assertIn("needs at least 3 measured points", shape.message)

    def test_closing_while_drawing_is_safe(self):
        application = self.application()
        window = self.inspect(self.dialog(application), self.plate())
        real = fe_preview.render_fe_mode_shape
        gate, entered = threading.Event(), threading.Event()

        def slow(*args, **kwargs):
            entered.set()
            gate.wait(30)
            return real(*args, **kwargs)

        errors = []
        self.root.report_callback_exception = lambda *exc: errors.append(exc[1])
        with mock.patch.object(fe_preview, "render_fe_mode_shape", side_effect=slow):
            self.select(window, 6)
            shape = window.view_selected_shape()
            self.assertTrue(entered.wait(10))
            window.close()  # the FE modes view and its shape window close while the shape is drawn
            self.assertTrue(shape.closed)
            self.assertFalse(shape.window.winfo_exists())
            gate.set()
            for thread in shape.threads:
                thread.join(30)
        self.assertFalse(any(thread.is_alive() for thread in shape.threads))
        self.assertEqual(shape.results.get_nowait()[1], "cancelled")
        for _ in range(15):
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(shape.shown)
        self.assertFalse(shape.folder.exists())
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
