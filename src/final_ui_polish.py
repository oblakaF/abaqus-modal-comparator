from __future__ import annotations


_INSTALLED = False


TABLE_COLUMN_SPECS = (
    ("am", "Abaqus mode", 100),
    ("em", "Experimental mode", 130),
    ("af", "Abaqus, Hz", 110),
    ("ef", "Experiment, Hz", 120),
    ("err", "Signed error, %", 100),
    ("mac", "MAC", 80),
    ("order", "Order changed", 110),
    ("points", "Mapped points", 105),
    ("status", "Status", 150),
    ("source", "Experimental source", 155),
    ("confidence", "Confidence", 145),
)

MODE_RANGE_HELP = (
    "Default 6–15; rigid/near-zero modes are excluded automatically and "
    "experimental modes are detected from Testlab."
)

WORKFLOW_TEXT = (
    "1. Abaqus Python opens the ODB and extracts natural frequencies, FE coordinates, and U1/U2/U3 mode vectors.\n\n"
    "2. The Testlab importer reads geometry, frequencies, damping, modal mass, complex mode vectors, and FRF data from UNV/UFF.\n\n"
    "3. Coordinate scale, axis order, and axis signs are detected automatically; experimental points are mapped to FE nodes.\n\n"
    "4. The application builds the measured-DOF MAC matrix, pairs admissible modes one-to-one, calculates signed frequency errors, and detects order changes.\n\n"
    "5. Close-frequency regions are checked with local SVD. Candidates unsupported by independent references remain diagnostic and are not promoted automatically.\n\n"
    "6. Mode-shape plots, complex-fit amplitude correlation, FRF diagnostics, AutoMAC, COMAC, Excel, PDF, and image exports are generated automatically."
)


def restore_table_headings(table) -> None:
    """Restore every heading after Treeview columns are extended at runtime."""
    columns = {str(value) for value in table["columns"]}
    for key, title, width in TABLE_COLUMN_SPECS:
        if key not in columns:
            continue
        table.heading(key, text=title)
        table.column(key, width=width, anchor="center")


def _walk_widgets(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk_widgets(child)


def _refresh_input_copy(application) -> None:
    for widget in _walk_widgets(application.input_tab):
        try:
            text = str(widget.cget("text"))
        except Exception:
            continue
        if text.startswith("Default 6–") and "experimental modes" in text:
            widget.configure(text=MODE_RANGE_HELP)
        elif text.startswith("1. Abaqus Python opens the ODB"):
            widget.configure(text=WORKFLOW_TEXT)


def install_final_ui_polish(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_build_input = application_class._build_input
    original_build_table = application_class._build_table

    def polished_build_input(self) -> None:
        # The selected engineering range includes the near-zero mode for automatic
        # rejection and Abaqus elastic modes 7–15 for comparison.
        self.end_mode.set(15)
        original_build_input(self)
        _refresh_input_copy(self)

    def polished_build_table(self) -> None:
        original_build_table(self)
        restore_table_headings(self.table)

    application_class._build_input = polished_build_input
    application_class._build_table = polished_build_table
    _INSTALLED = True
