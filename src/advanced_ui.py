from __future__ import annotations

from tkinter import ttk

from advanced_metrics import advanced_metric_summary, render_automac_comac


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
        self.advanced_tab = ttk.Frame(self.tabs, padding=12)
        details_index = self.tabs.index(self.details_tab)
        self.tabs.insert(details_index, self.advanced_tab, text="6. AutoMAC & COMAC")
        self.tabs.tab(self.details_tab, text="7. Details")

        image_frame = ttk.LabelFrame(
            self.advanced_tab,
            text="Mode distinguishability and local agreement",
            padding=6,
        )
        image_frame.pack(fill="both", expand=True)
        self.advanced_metrics_label = ttk.Label(
            image_frame,
            text="Run the analysis to calculate AutoMAC and COMAC.",
            anchor="center",
        )
        self.advanced_metrics_label.pack(fill="both", expand=True)

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
        output_path = self.cache / "plots" / "automac_comac.png"
        if not output_path.exists():
            render_automac_comac(result, output_path)
        self._image(
            self.advanced_metrics_label,
            output_path,
            "advanced_metrics",
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
