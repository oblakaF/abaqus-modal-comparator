from __future__ import annotations

from tkinter import ttk

from advanced_metrics import (
    advanced_metric_summary,
    render_abaqus_automac,
    render_automac_comac,
    render_comac_map,
    render_experimental_automac,
)


_INSTALLED = False


def install_advanced_ui(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_build = application_class._build
    original_populate = application_class._populate

    def advanced_build(self) -> None:
        original_build(self)
        self.advanced_tab = ttk.Frame(self.tabs, padding=10)
        details_index = self.tabs.index(self.details_tab)
        self.tabs.insert(details_index, self.advanced_tab, text="6. AutoMAC & COMAC")
        self.tabs.tab(self.details_tab, text="7. Details")

        self.advanced_notebook = ttk.Notebook(self.advanced_tab)
        self.advanced_notebook.pack(fill="both", expand=True)

        self.abaqus_automac_panel = ttk.Frame(self.advanced_notebook, padding=6)
        self.experimental_automac_panel = ttk.Frame(self.advanced_notebook, padding=6)
        self.comac_panel = ttk.Frame(self.advanced_notebook, padding=6)
        self.advanced_notebook.add(self.abaqus_automac_panel, text="Abaqus AutoMAC")
        self.advanced_notebook.add(
            self.experimental_automac_panel,
            text="Experimental AutoMAC",
        )
        self.advanced_notebook.add(self.comac_panel, text="COMAC map")

        self.abaqus_automac_label = ttk.Label(
            self.abaqus_automac_panel,
            text="Run the analysis to calculate Abaqus AutoMAC.",
            anchor="center",
        )
        self.experimental_automac_label = ttk.Label(
            self.experimental_automac_panel,
            text="Run the analysis to calculate experimental AutoMAC.",
            anchor="center",
        )
        self.comac_label = ttk.Label(
            self.comac_panel,
            text="Run the analysis to calculate COMAC.",
            anchor="center",
        )
        self.abaqus_automac_label.pack(fill="both", expand=True)
        self.experimental_automac_label.pack(fill="both", expand=True)
        self.comac_label.pack(fill="both", expand=True)

        summary_frame = ttk.LabelFrame(
            self.advanced_tab,
            text="Interpretation",
            padding=8,
        )
        summary_frame.pack(fill="x", pady=(8, 0))
        self.advanced_metrics_summary = ttk.Label(
            summary_frame,
            text="No analysis results yet.",
            justify="left",
            anchor="w",
        )
        self.advanced_metrics_summary.pack(fill="x")

    def advanced_populate(self, result) -> None:
        original_populate(self, result)
        if self.cache is None:
            return

        plot_directory = self.cache / "plots"
        abaqus_path = plot_directory / "abaqus_automac.png"
        experimental_path = plot_directory / "experimental_automac.png"
        comac_path = plot_directory / "comac_map.png"
        combined_path = plot_directory / "automac_comac.png"

        if not abaqus_path.exists():
            render_abaqus_automac(result, abaqus_path)
        if not experimental_path.exists():
            render_experimental_automac(result, experimental_path)
        if not comac_path.exists():
            render_comac_map(result, comac_path)
        if not combined_path.exists():
            render_automac_comac(result, combined_path)

        self._image(
            self.abaqus_automac_label,
            abaqus_path,
            "abaqus_automac",
        )
        self._image(
            self.experimental_automac_label,
            experimental_path,
            "experimental_automac",
        )
        self._image(
            self.comac_label,
            comac_path,
            "comac_map",
        )

        values = advanced_metric_summary(result)
        self.advanced_metrics_summary.configure(
            text=(
                f"Abaqus AutoMAC max off-diagonal: {values['abaqus_automac_max_off_diagonal']:.3f}\n"
                f"Experimental AutoMAC max off-diagonal: {values['experimental_automac_max_off_diagonal']:.3f}\n"
                f"Mean COMAC: {values['mean_comac']:.3f} | Minimum COMAC: {values['minimum_comac']:.3f}\n\n"
                "Large off-diagonal AutoMAC means the selected measurement grid cannot clearly distinguish some modes. "
                "Low COMAC points identify local regions where numerical and experimental shapes disagree."
            )
        )

    application_class._build = advanced_build
    application_class._populate = advanced_populate
    _INSTALLED = True
