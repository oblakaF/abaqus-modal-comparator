"""Start the new interface: ``python -m new_gui`` (with ``src`` on the path) or ``python src/new_gui``."""

from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:  # run as ``python src/new_gui``: the services live in src
    sys.path.insert(0, str(SRC))


RESEARCH_OPTION = "--research"


def main(argv=None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("The new interface needs PySide6. Install it with:\n"
              "    python -m pip install -r requirements-new-gui.txt\n"
              "or start RUN_NEW_GUI.cmd, which installs it into the local .venv.", file=sys.stderr)
        return 2

    from new_gui.theme import create_application

    arguments = list(sys.argv if argv is None else argv)
    research = RESEARCH_OPTION in arguments
    app = QApplication.instance() or create_application([a for a in arguments if a != RESEARCH_OPTION])
    if research:  # the earlier pages and the historical research records; never offered by the normal window
        from new_gui.window import ANALYZE_PAGE, MainWindow

        window = MainWindow(start_page=ANALYZE_PAGE)
    else:
        from new_gui.production_window import ProductionWindow

        window = ProductionWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
