"""NEW-GUI.1: a separate PySide6 (Qt) shell of the comparator for any FE model and any experimental data.

It is a new program window, independent of the Tkinter program: it never imports ``src/main.py``, Tkinter or a user
interface layer of that program. It lets the user choose an FE results file and an experimental file, shows the
workspace and opens the read-only research archive on request (NEW-GUI.1, ``docs/gui/NEW_GUI1_SHELL.md``).

NEW-GUI.2 (``docs/gui/NEW_GUI2_PREVIEW.md``): **Inspect file** reads a chosen file with the existing preview services
and the application's importer chain (``services.importer_runtime``, the same function ``src/main.py`` calls), and
shows the imported modes, frequencies, modal sets and warnings. Inspect file itself runs no analysis.

NEW-GUI.3 (``docs/gui/NEW_GUI3_SHAPES.md``): after Inspect file, one chosen FE mode or experimental record is drawn
on its own coordinates with the existing services' drawing. Nothing is compared, paired or overlaid.

NEW-GUI.4 (``docs/gui/NEW_GUI4_FREQUENCY.md``): on the user's explicit command (Run frequency diagnostic), the
Analysis page runs the existing frequency-only diagnostic of the read FE results and one chosen experimental modal
set: FREQUENCY_ONLY_DIAGNOSTIC. Its nearest FE frequencies show frequency proximity only and are not established
mode pairs. No physical registration, MAC or Auto-ID is run.

Start it with ``RUN_NEW_GUI.cmd`` or ``python -m new_gui`` (with ``src`` on the path). PySide6 is installed from
``requirements-new-gui.txt``, separately from ``requirements.txt``.
"""

APP_NAME = "Abaqus–Simcenter Modal Comparator"
STAGE = "NEW-GUI.4 preview"
