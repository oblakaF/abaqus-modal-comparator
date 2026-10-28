"""NEW-GUI.1: a separate PySide6 (Qt) shell of the comparator for any FE model and any experimental data.

It is a new program window, independent of the Tkinter program: it never imports ``src/main.py``, Tkinter or a user
interface layer of that program. It lets the user choose an FE results file and an experimental file, shows the
workspace and opens the read-only research archive on request (NEW-GUI.1, ``docs/gui/NEW_GUI1_SHELL.md``).

NEW-GUI.2 (``docs/gui/NEW_GUI2_PREVIEW.md``): **Inspect file** reads a chosen file with the existing preview services
and the application's importer chain (``services.importer_runtime``, the same function ``src/main.py`` calls), and
shows the imported modes, frequencies, modal sets and warnings. It runs no analysis.

Start it with ``RUN_NEW_GUI.cmd`` or ``python -m new_gui`` (with ``src`` on the path). PySide6 is installed from
``requirements-new-gui.txt``, separately from ``requirements.txt``.
"""

APP_NAME = "Abaqus–Simcenter Modal Comparator"
STAGE = "NEW-GUI.2 preview"
