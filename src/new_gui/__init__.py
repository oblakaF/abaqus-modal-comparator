"""NEW-GUI.1: a separate PySide6 (Qt) shell of the comparator for any FE model and any experimental data.

It is a new program window, independent of the Tkinter program (``src/main.py`` and its ``install_*`` chain, which
it never imports). This first stage lets the user choose an FE results file and an experimental file, shows the
workspace and opens the read-only research archive on request. It runs no analysis. See
``docs/gui/NEW_GUI1_SHELL.md``.

Start it with ``RUN_NEW_GUI.cmd`` or ``python -m new_gui`` (with ``src`` on the path). PySide6 is installed from
``requirements-new-gui.txt``, separately from ``requirements.txt``.
"""

APP_NAME = "Abaqus–Simcenter Modal Comparator"
STAGE = "NEW-GUI.1 preview"
