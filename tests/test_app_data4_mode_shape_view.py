"""APP-DATA.4: View selected mode shape in File > Input file registry > Inspect experimental data (real main window).

The shape of the record selected in the experimental data view is drawn on its own measured points by
services.modal_data_viewer, on a background thread; the outcome is posted back to the Tk thread. Only the set shown in
the view is used, nothing in the main window changes, a superseded or cancelled drawing is never shown, a component
that is not measured is refused, FRF records stay PROVISIONAL and ambiguous records keep their warning. Synthetic
temporary files only; no process is started.
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

import main  # noqa: E402,F401  (the installed importer chain, as in the application)
import universal_reader  # noqa: E402
from services import local_experimental_preview as preview_service  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from test_app_p1_stale_results import _App  # noqa: E402
from test_local_experimental_preview import geometry_4, mode_55_4  # noqa: E402


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModeShapeWindowTests(_App):
    def dialog(self, application):
        import menu_ui

        self.store = self.folder / "profile" / registry.STORE_NAME
        application.local_input_registry_store = self.store
        dialog = menu_ui.InputRegistryDialog(application)
        self.addCleanup(lambda: dialog.window.destroy() if dialog.window.winfo_exists() else None)
        return dialog

    def inspect(self, dialog, path, label="entry"):
        entry, _ = registry.add_entry(self.store, registry.EXPERIMENTAL, path, label)
        dialog.refresh(select=entry["id"])
        window = dialog.inspect_experimental_selected()
        self.addCleanup(window.close)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and window.preview is None and window.error is None:
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(window.error)
        return window

    def pump(self, shape, timeout=60.0) -> None:
        """Process events until every drawing of the shape window has finished and been taken from its queue."""
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

    def main_state(self, application):
        return (application.abaqus_path.get(), application.experimental_path.get(),
                application.experimental_modal_set_key.get(), application.result is None, application.running)

    def test_the_selected_record_of_the_selected_set_is_drawn_and_the_main_window_is_untouched(self):
        application = self.application()
        dialog = self.dialog(application)
        unv = S.write_experiment(self.folder / "two_sets.unv", S.E0, S.G0, sets=(("PolyMAX bravo", 4),
                                                                                  ("PolyMAX alpha", 6)))
        before_file, before_main = fingerprint(unv), self.main_state(application)
        with mock.patch.object(application, "_start", side_effect=AssertionError("nothing is run")):
            window = self.inspect(dialog, unv, "Two sets")
            before_store = self.store.read_bytes()
            self.assertEqual(str(window.shape_button.cget("state")), "disabled")  # no record selected
            self.assertIsNone(window.view_selected_shape())
            first, second = window.preview.sets
            self.select(window, 2)
            self.assertEqual(str(window.shape_button.cget("state")), "normal")
            shape = window.view_selected_shape()
            self.pump(shape)
            self.assertEqual(shape.window.title(), "Mode shape — Two sets")
            self.assertEqual((shape.shown.set_title, shape.shown.index, shape.shown.record),
                             (first.title, 2, first.records[2]))
            self.assertIsNotNone(shape.photo)
            self.assertIn(f"Record 3 of {first.title}", shape.caption.get())

            window.set_box.current(1)  # another set: the drawing of the first set goes at once
            window.set_box.event_generate("<<ComboboxSelected>>")
            self.root.update()
            self.assertIsNone(shape.shown)
            self.assertIsNone(shape.photo)
            self.assertIn(f"The modal set changed to {second.title}", shape.message)
            self.assertEqual(str(window.shape_button.cget("state")), "disabled")

            self.select(window, 5)  # the open view follows the selection
            self.pump(shape)
            self.assertEqual((shape.shown.set_title, shape.shown.record), (second.title, second.records[5]))

            shape.component.set(preview_service.COMPONENT_TEXT["z"])
            shape.component_box.event_generate("<<ComboboxSelected>>")
            self.pump(shape)
            self.assertEqual((shape.shown.component, shape.shown.record), ("z", second.records[5]))

            shape.component.set(preview_service.COMPONENT_TEXT["x"])  # U3-only data: X is not measured
            shape.component_box.event_generate("<<ComboboxSelected>>")
            self.pump(shape)
            self.assertIsNone(shape.shown)
            self.assertIsNone(shape.photo)
            self.assertIn("is not a measured component of this record", shape.message)
        self.assertEqual(self.main_state(application), before_main)  # fields, modal set, no result, not running
        self.assertEqual(fingerprint(unv), before_file)
        self.assertEqual(self.store.read_bytes(), before_store)

    def test_a_superseded_drawing_is_never_shown(self):
        application = self.application()
        dialog = self.dialog(application)
        window = self.inspect(dialog, S.write_experiment(self.folder / "one.unv", S.E0, S.G0))
        real = preview_service.render_record_shape
        gate, entered = threading.Event(), threading.Event()

        def slow_first(preview_set, position, *args, **kwargs):
            if position == 0:
                entered.set()
                gate.wait(30)
            return real(preview_set, position, *args, **kwargs)

        with mock.patch.object(preview_service, "render_record_shape", side_effect=slow_first):
            self.select(window, 0)
            shape = window.view_selected_shape()
            self.assertTrue(entered.wait(10))
            self.assertIn("Drawing record", shape.message)
            self.select(window, 1)  # a newer request while the first is still drawing
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and shape.shown is None:
                self.root.update()
                time.sleep(0.02)
            self.assertEqual(shape.shown.record, window.preview.sets[0].records[1])
            gate.set()
            self.pump(shape)
        self.assertEqual(shape.shown.record, window.preview.sets[0].records[1])  # the late first one is discarded
        self.assertEqual([p.name for p in shape.folder.iterdir()], [shape.shown.image_path.parent.name])

    def test_frf_records_are_provisional_and_ambiguous_records_keep_their_warning(self):
        application = self.application()
        dialog = self.dialog(application)
        window = self.inspect(dialog, F.write_frf_only(self.folder / "frf.uff"), "FRF")
        self.select(window, 0)
        shape = window.view_selected_shape()
        self.pump(shape)
        self.assertEqual(shape.banner.get(), preview_service.PROVISIONAL)
        self.assertTrue(shape.caption.get().startswith(preview_service.PROVISIONAL))
        self.assertIsNotNone(shape.photo)

        path = self.folder / "ambiguous.unv"
        path.write_text("synthetic records", encoding="utf-8")
        with mock.patch.object(universal_reader, "_read_universal_datasets",
                               return_value=[geometry_4(), mode_55_4(1, 10.0), mode_55_4(2, 20.0, ambiguous=True)]):
            window = self.inspect(dialog, path, "Ambiguous")
        self.select(window, 1)
        shape = window.view_selected_shape()
        self.pump(shape)
        self.assertTrue(shape.banner.get().startswith(f"{preview_service.AMBIGUOUS} — dataset 55 record 2"))
        self.assertIsNotNone(shape.photo)
        self.select(window, 0)
        self.pump(shape)
        self.assertEqual(shape.banner.get(), "")  # a physical record carries no warning banner
        self.assertIn("dataset 55 record 1 (physical, importer)", shape.caption.get())

    def test_a_record_without_a_spatial_view_states_why(self):
        application = self.application()
        dialog = self.dialog(application)
        window = self.inspect(dialog, F.write_frf_only(self.folder / "two_points.uff", points=2))
        self.select(window, 0)
        shape = window.view_selected_shape()
        self.pump(shape)
        self.assertIsNone(shape.shown)
        self.assertIsNone(shape.photo)
        self.assertIn("needs at least 3 measured points", shape.message)
        self.assertEqual(shape.banner.get(), preview_service.PROVISIONAL)

    def test_closing_while_drawing_is_safe(self):
        application = self.application()
        dialog = self.dialog(application)
        window = self.inspect(dialog, S.write_experiment(self.folder / "close.unv", S.E0, S.G0))
        real = preview_service.render_record_shape
        gate, entered = threading.Event(), threading.Event()

        def slow(*args, **kwargs):
            entered.set()
            gate.wait(30)
            return real(*args, **kwargs)

        errors = []
        self.root.report_callback_exception = lambda *exc: errors.append(exc[1])
        with mock.patch.object(preview_service, "render_record_shape", side_effect=slow):
            self.select(window, 0)
            shape = window.view_selected_shape()
            self.assertTrue(entered.wait(10))
            window.close()  # the data view and its shape window close while the shape is drawn
            self.assertTrue(shape.closed)
            self.assertFalse(shape.window.winfo_exists())
            gate.set()
            for thread in shape.threads:
                thread.join(30)
        self.assertFalse(any(thread.is_alive() for thread in shape.threads))
        self.assertEqual(shape.results.get_nowait()[1], "cancelled")  # stopped before drawing, discarded
        for _ in range(15):
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(shape.shown)
        self.assertFalse(shape.folder.exists())  # nothing is left behind
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
