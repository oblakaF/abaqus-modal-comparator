"""Initial folder of the PDF / Excel report save dialogs (APP-UX.1).

Without an initial folder the Windows save dialog opens in the folder Python last used, taken from the user's dialog
history; that can be a folder of source measurements or of an ODB. The report dialogs therefore always start in one
predictable folder of the user: ``Documents\\Abaqus Modal Comparator Reports`` (created when missing). The user can
still choose any other place in the dialog. No folder of the analysed files (ODB, UNV, UFF, manifest) is ever used.

If the folder cannot be created, the dialog starts in ``Documents``, else in the user's home folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

REPORT_FOLDER_NAME = "Abaqus Modal Comparator Reports"


def default_report_directory(home: Optional[Path] = None) -> Path:
    """The existing folder a report save dialog opens in (see the module text)."""
    home = Path.home() if home is None else Path(home)
    documents = home / "Documents"
    base = documents if documents.is_dir() else home
    folder = base / REPORT_FOLDER_NAME
    try:
        folder.mkdir(exist_ok=True)  # only the report folder itself; never a missing Documents or home folder
    except OSError:
        return base
    return folder if folder.is_dir() else base


def save_dialog_options(home: Optional[Path] = None) -> dict:
    """Keyword options for ``filedialog.asksaveasfilename`` of a report."""
    return {"initialdir": str(default_report_directory(home))}
