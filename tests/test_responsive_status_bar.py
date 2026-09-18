from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from responsive_status_bar import (
    ensure_status_bar_visible,
    progress_length_for_width,
)


class FakeFooter:
    def __init__(self):
        self.forgotten = False
        self.pack_options = None
        self.lift_count = 0
        self.children = []

    def pack_forget(self):
        self.forgotten = True

    def pack(self, **kwargs):
        self.pack_options = kwargs

    def lift(self):
        self.lift_count += 1

    def winfo_children(self):
        return self.children


class FakeStatusLabel:
    def __init__(self):
        self.wraplength = None

    def winfo_class(self):
        return "TLabel"

    def configure(self, **kwargs):
        self.wraplength = kwargs.get("wraplength", self.wraplength)


class FakeProgress:
    def __init__(self, master):
        self.master = master
        self.length = None

    def configure(self, **kwargs):
        self.length = kwargs.get("length", self.length)


class FakeRoot:
    def __init__(self, width=1200):
        self.width = width
        self.bindings = []
        self.after_idle_callbacks = []

    def bind(self, sequence, callback, add=None):
        self.bindings.append((sequence, callback, add))

    def after_idle(self, callback):
        self.after_idle_callbacks.append(callback)
        callback()

    def winfo_width(self):
        return self.width


class FakeApplication:
    def __init__(self, width=1200):
        self.root = FakeRoot(width)
        self.tabs = object()
        self.footer = FakeFooter()
        self.status_label = FakeStatusLabel()
        self.progress = FakeProgress(self.footer)
        self.footer.children = [self.status_label, self.progress]


class ResponsiveStatusBarTests(unittest.TestCase):
    def test_progress_length_is_bounded_and_responsive(self):
        self.assertEqual(progress_length_for_width(100), 170)
        self.assertEqual(progress_length_for_width(1200), 264)
        self.assertEqual(progress_length_for_width(5000), 360)

    def test_footer_is_repacked_before_expanding_notebook(self):
        application = FakeApplication(width=1200)
        changed = ensure_status_bar_visible(application)

        self.assertTrue(changed)
        self.assertTrue(application.footer.forgotten)
        self.assertEqual(application.footer.pack_options["side"], "bottom")
        self.assertEqual(application.footer.pack_options["fill"], "x")
        self.assertIs(application.footer.pack_options["before"], application.tabs)
        self.assertEqual(application.progress.length, 264)
        self.assertEqual(application.status_label.wraplength, 856)
        self.assertGreaterEqual(application.footer.lift_count, 2)
        self.assertEqual(application.root.bindings[0][0], "<Configure>")
        self.assertEqual(application.root.bindings[0][2], "+")


if __name__ == "__main__":
    unittest.main()
